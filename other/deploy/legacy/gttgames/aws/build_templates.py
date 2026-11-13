"""Generate reviewable AWS stacks and an existing-bucket recovery variant. No AWS calls."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DISABLED = '4135ea2d-6df8-44a3-9df3-4b5a84be39ad'
ALL_VIEWER = '216adef6-5c7f-47e4-b989-5492eafa07d3'


def ref(name): return {'Ref': name}
def attr(name, field): return {'Fn::GetAtt': [name, field]}
def sub(value): return {'Fn::Sub': value}
def imported(name): return {'Fn::ImportValue': sub('${FoundationStackName}-' + name)}
def resource(kind, **properties): return {'Type': 'AWS::' + kind, 'Properties': properties}
def output(value, exported=False, name=None):
    result = {'Value': value}
    if exported: result['Export'] = {'Name': sub('${AWS::StackName}-' + name)}
    return result
def string(default=None, **extra):
    result = {'Type': 'String', **extra}
    if default is not None: result['Default'] = default
    return result
def base(description, parameters):
    return {'AWSTemplateFormatVersion': '2010-09-09', 'Description': description,
            'Parameters': parameters, 'Resources': {}, 'Outputs': {}}
def domain_parameter():
    return string('gttgames.com', AllowedPattern=r'[a-z0-9][a-z0-9.-]+\.[a-z]{2,}')


def certificate():
    t = base('GTT ACM public certificate. Deploy in us-east-1; validate DNS at your DNS provider.',
             {'DomainName': domain_parameter()})
    t['Resources']['Certificate'] = resource('CertificateManager::Certificate',
        DomainName=ref('DomainName'), SubjectAlternativeNames=[sub('*.${DomainName}')],
        ValidationMethod='DNS', Tags=[{'Key': 'Project', 'Value': 'GTT'}])
    t['Outputs']['CertificateArn'] = output(ref('Certificate'))
    return t


def private_bucket():
    value = resource('S3::Bucket',
        PublicAccessBlockConfiguration={k: True for k in
            ('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets')},
        OwnershipControls={'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]},
        VersioningConfiguration={'Status': 'Enabled'},
        BucketEncryption={'ServerSideEncryptionConfiguration': [
            {'ServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]},
        LifecycleConfiguration={'Rules': [{'Id': 'AbortIncompleteUploads', 'Status': 'Enabled',
            'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 7}}]},
        Tags=[{'Key': 'Project', 'Value': 'GTT'}])
    value.update(DeletionPolicy='Retain', UpdateReplacePolicy='Retain')
    return value


def tls_deny(bucket):
    return {'Sid': 'RequireTLS', 'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
            'Resource': [attr(bucket, 'Arn'), sub('${' + bucket + '.Arn}/*')],
            'Condition': {'Bool': {'aws:SecureTransport': 'false'}}}


def foundation():
    t = base('GTT existing-EC2 foundation: private buckets, instance identity, protected ALB and monitoring. No EC2 replacement.', {
        'VpcId': {'Type': 'AWS::EC2::VPC::Id'},
        'AlbSubnetA': {'Type': 'AWS::EC2::Subnet::Id'},
        'AlbSubnetB': {'Type': 'AWS::EC2::Subnet::Id'},
        'InstanceId': {'Type': 'AWS::EC2::Instance::Id'},
        'InstanceSecurityGroupId': {'Type': 'AWS::EC2::SecurityGroup::Id'},
        'CertificateArn': string(AllowedPattern=r'arn:aws:acm:us-east-1:[0-9]{12}:certificate/[a-f0-9-]+'),
        'CloudFrontPrefixListId': string(AllowedPattern=r'pl-[a-f0-9]+',
            Description='us-east-1 AWS managed com.amazonaws.global.cloudfront.origin-facing prefix list.'),
        'DomainName': domain_parameter(),
        'NotificationEmail': string('', Description='Optional alarm email; SNS confirmation is required.'),
        'EnableBackupMonitoring': string('false', AllowedValues=['true', 'false'],
            Description='Enable only after a daily consistent backup job has been installed and tested.')})
    t['Conditions'] = {'HasEmail': {'Fn::Not': [{'Fn::Equals': [ref('NotificationEmail'), '']}]},
        'MonitorBackup': {'Fn::Equals': [ref('EnableBackupMonitoring'), 'true']}}
    r = t['Resources']
    r['WebsiteBucket'], r['BackupBucket'] = private_bucket(), private_bucket()
    r['BackupBucketPolicy'] = resource('S3::BucketPolicy', Bucket=ref('BackupBucket'),
        PolicyDocument={'Version': '2012-10-17', 'Statement': [tls_deny('BackupBucket')]})
    r['OriginSecret'] = resource('SecretsManager::Secret',
        Description='GTT CloudFront to ALB origin verification. Never put its plaintext in source or outputs.',
        GenerateSecretString={'PasswordLength': 48, 'ExcludePunctuation': True},
        Tags=[{'Key': 'Project', 'Value': 'GTT'}])
    r['OriginSecret'].update(DeletionPolicy='Retain', UpdateReplacePolicy='Retain')
    r['AppLogGroup'] = resource('Logs::LogGroup', LogGroupName=sub('/gtt/${AWS::StackName}/application'), RetentionInDays=14)
    r['AppLogGroup'].update(DeletionPolicy='Retain', UpdateReplacePolicy='Retain')
    r['AlarmTopic'] = resource('SNS::Topic')
    r['AlarmEmail'] = resource('SNS::Subscription', Protocol='email', Endpoint=ref('NotificationEmail'), TopicArn=ref('AlarmTopic'))
    r['AlarmEmail']['Condition'] = 'HasEmail'
    r['InstanceRole'] = resource('IAM::Role',
        AssumeRolePolicyDocument={'Version': '2012-10-17', 'Statement': [{
            'Effect': 'Allow', 'Principal': {'Service': 'ec2.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]},
        ManagedPolicyArns=[sub('arn:${AWS::Partition}:iam::aws:policy/AmazonSSMManagedInstanceCore')],
        Policies=[{'PolicyName': 'GttBackupAndTelemetry', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
            {'Effect': 'Allow', 'Action': ['s3:PutObject', 's3:GetObject', 's3:AbortMultipartUpload'],
             'Resource': [sub('${BackupBucket.Arn}/backups/*'), sub('${BackupBucket.Arn}/releases/*')]},
            {'Effect': 'Allow', 'Action': ['s3:ListBucket'], 'Resource': attr('BackupBucket', 'Arn'),
             'Condition': {'StringLike': {'s3:prefix': ['backups/*', 'releases/*']}}},
            {'Effect': 'Allow', 'Action': ['logs:CreateLogStream', 'logs:PutLogEvents', 'logs:DescribeLogStreams'],
             'Resource': attr('AppLogGroup', 'Arn')},
            {'Effect': 'Allow', 'Action': 'cloudwatch:PutMetricData', 'Resource': '*',
             'Condition': {'StringEquals': {'cloudwatch:namespace': ['GTT.Instance', 'GTT.Backup']}}},
            {'Effect': 'Allow', 'Action': 'ssm:GetParameter',
             'Resource': sub('arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter/gtt/${AWS::StackName}/cloudwatch-agent')}
        ]}}], Tags=[{'Key': 'Project', 'Value': 'GTT'}])
    r['InstanceProfile'] = resource('IAM::InstanceProfile', Roles=[ref('InstanceRole')])
    agent = {'agent': {'metrics_collection_interval': 60}, 'metrics': {
        'namespace': 'GTT.Instance', 'append_dimensions': {'InstanceId': '${!aws:InstanceId}'},
        'aggregation_dimensions': [['InstanceId']],
        'metrics_collected': {'mem': {'measurement': ['mem_used_percent']},
                              'disk': {'measurement': ['used_percent'], 'resources': ['/'], 'drop_device': True},
                              'procstat': [{'pattern': r'py\.merchant\.rtp_worker', 'measurement': ['pid_count']}]}},
        'logs': {'logs_collected': {'files': {'collect_list': [
            {'file_path': '/var/log/gtt/gtt-gateway.log', 'log_group_name': '${AppLogGroup}', 'log_stream_name': '{instance_id}/gateway'},
            {'file_path': '/var/log/gtt/gtt-admin.log', 'log_group_name': '${AppLogGroup}', 'log_stream_name': '{instance_id}/admin'},
            {'file_path': '/www/wwwlogs/gtt-alb-access.log', 'log_group_name': '${AppLogGroup}', 'log_stream_name': '{instance_id}/nginx'}]}}}}
    r['AgentConfig'] = resource('SSM::Parameter', Name=sub('/gtt/${AWS::StackName}/cloudwatch-agent'),
        Type='String', Value=sub(json.dumps(agent, separators=(',', ':'))),
        Description='Non-secret CloudWatch agent configuration. Install/start the agent separately.')
    r['AlbSecurityGroup'] = resource('EC2::SecurityGroup', GroupDescription='GTT ALB HTTPS only from CloudFront',
        VpcId=ref('VpcId'), SecurityGroupIngress=[{'IpProtocol': 'tcp', 'FromPort': 443, 'ToPort': 443,
            'SourcePrefixListId': ref('CloudFrontPrefixListId')}],
        SecurityGroupEgress=[{'IpProtocol': 'tcp', 'FromPort': 8080, 'ToPort': 8081,
            'DestinationSecurityGroupId': ref('InstanceSecurityGroupId')}], Tags=[{'Key': 'Project', 'Value': 'GTT'}])
    for name, port in [('GatewayIngress', 8080), ('ConsoleIngress', 8081)]:
        r[name] = resource('EC2::SecurityGroupIngress', GroupId=ref('InstanceSecurityGroupId'),
            IpProtocol='tcp', FromPort=port, ToPort=port, SourceSecurityGroupId=ref('AlbSecurityGroup'),
            Description='GTT internal Nginx from managed ALB only')
    r['LoadBalancer'] = resource('ElasticLoadBalancingV2::LoadBalancer', Type='application', Scheme='internet-facing',
        IpAddressType='ipv4', Subnets=[ref('AlbSubnetA'), ref('AlbSubnetB')], SecurityGroups=[ref('AlbSecurityGroup')],
        LoadBalancerAttributes=[{'Key': 'routing.http.preserve_host_header.enabled', 'Value': 'true'},
            {'Key': 'routing.http.drop_invalid_header_fields.enabled', 'Value': 'true'},
            {'Key': 'idle_timeout.timeout_seconds', 'Value': '60'},
            {'Key': 'access_logs.s3.enabled', 'Value': 'false'}], Tags=[{'Key': 'Project', 'Value': 'GTT'}])
    for name, port in [('GatewayTargetGroup', 8080), ('ConsoleTargetGroup', 8081)]:
        r[name] = resource('ElasticLoadBalancingV2::TargetGroup', VpcId=ref('VpcId'), TargetType='instance',
            Protocol='HTTP', Port=port, Targets=[{'Id': ref('InstanceId'), 'Port': port}],
            HealthCheckProtocol='HTTP', HealthCheckPort='traffic-port', HealthCheckPath='/health',
            HealthCheckIntervalSeconds=30, HealthCheckTimeoutSeconds=5,
            HealthyThresholdCount=2, UnhealthyThresholdCount=2, Matcher={'HttpCode': '200'},
            TargetGroupAttributes=[{'Key': 'deregistration_delay.timeout_seconds', 'Value': '60'}])
    r['HttpsListener'] = resource('ElasticLoadBalancingV2::Listener', LoadBalancerArn=ref('LoadBalancer'),
        Port=443, Protocol='HTTPS', Certificates=[{'CertificateArn': ref('CertificateArn')}],
        SslPolicy='ELBSecurityPolicy-TLS13-1-2-2021-06',
        DefaultActions=[{'Type': 'fixed-response', 'FixedResponseConfig': {
            'ContentType': 'text/plain', 'MessageBody': 'Forbidden', 'StatusCode': '403'}}])
    for name, priority, hosts, target in [
        ('GatewayRule', 10, ['api', 'play'], 'GatewayTargetGroup'),
        ('ConsoleRule', 20, ['merchant', 'admin'], 'ConsoleTargetGroup')]:
        r[name] = resource('ElasticLoadBalancingV2::ListenerRule', ListenerArn=ref('HttpsListener'), Priority=priority,
            Conditions=[{'Field': 'host-header', 'HostHeaderConfig': {'Values': [sub(h + '.${DomainName}') for h in hosts]}},
                {'Field': 'http-header', 'HttpHeaderConfig': {'HttpHeaderName': 'X-GTT-Origin-Verify',
                    'Values': [sub('{{resolve:secretsmanager:${OriginSecret}:SecretString}}')]}}],
            Actions=[{'Type': 'forward', 'TargetGroupArn': ref(target)}])
    def alarm(name, namespace, metric, dimensions, threshold, comparison='GreaterThanOrEqualToThreshold', statistic='Average', period=300):
        r[name] = resource('CloudWatch::Alarm', Namespace=namespace, MetricName=metric,
            Dimensions=dimensions, Threshold=threshold, ComparisonOperator=comparison,
            Statistic=statistic, Period=period, EvaluationPeriods=2, TreatMissingData='missing',
            AlarmActions=[ref('AlarmTopic')], OKActions=[ref('AlarmTopic')])
    instance_dimension = [{'Name': 'InstanceId', 'Value': ref('InstanceId')}]
    alarm('InstanceStatusAlarm', 'AWS/EC2', 'StatusCheckFailed', instance_dimension, 1, statistic='Maximum', period=60)
    alarm('CpuAlarm', 'AWS/EC2', 'CPUUtilization', instance_dimension, 85)
    alarm('MemoryAlarm', 'GTT.Instance', 'mem_used_percent', instance_dimension, 85)
    alarm('DiskAlarm', 'GTT.Instance', 'disk_used_percent', instance_dimension, 80)
    alarm('RtpProcessAlarm', 'GTT.Instance', 'procstat_lookup_pid_count', instance_dimension, 1,
          comparison='LessThanThreshold', statistic='Minimum', period=60)
    alarm('BackupAlarm', 'GTT.Backup', 'BackupSuccess', instance_dimension, 1,
          comparison='LessThanThreshold', statistic='Minimum', period=86400)
    r['BackupAlarm']['Condition'] = 'MonitorBackup'
    r['BackupAlarm']['Properties'].update(EvaluationPeriods=1, TreatMissingData='breaching')
    for target in ('GatewayTargetGroup', 'ConsoleTargetGroup'):
        alarm(target + 'HealthAlarm', 'AWS/ApplicationELB', 'UnHealthyHostCount', [
            {'Name': 'LoadBalancer', 'Value': attr('LoadBalancer', 'LoadBalancerFullName')},
            {'Name': 'TargetGroup', 'Value': attr(target, 'TargetGroupFullName')}], 1, statistic='Maximum', period=60)
    alarm('AlbServerErrorAlarm', 'AWS/ApplicationELB', 'HTTPCode_ELB_5XX_Count', [
        {'Name': 'LoadBalancer', 'Value': attr('LoadBalancer', 'LoadBalancerFullName')}], 5, statistic='Sum')
    values = {'CertificateArn': ref('CertificateArn'), 'DomainName': ref('DomainName'),
        'WebsiteBucketName': ref('WebsiteBucket'), 'WebsiteBucketArn': attr('WebsiteBucket', 'Arn'),
        'WebsiteBucketDomain': attr('WebsiteBucket', 'RegionalDomainName'),
        'BackupBucketName': ref('BackupBucket'), 'OriginSecretArn': ref('OriginSecret'),
        'AlbDomainName': attr('LoadBalancer', 'DNSName'), 'AlbSecurityGroupId': ref('AlbSecurityGroup'),
        'GatewayTargetGroupArn': ref('GatewayTargetGroup'), 'ConsoleTargetGroupArn': ref('ConsoleTargetGroup'),
        'InstanceProfileName': ref('InstanceProfile'), 'InstanceRoleName': ref('InstanceRole'),
        'AgentParameterName': ref('AgentConfig'),
        'AlarmTopicArn': ref('AlarmTopic'), 'AppLogGroupName': ref('AppLogGroup')}
    t['Outputs'] = {name: output(value, True, name) for name, value in values.items()}
    return t


def foundation_existing_buckets():
    """Reference verified private buckets; their configuration remains externally managed."""
    template = foundation()
    template['Description'] = ('GTT existing-EC2 foundation using two verified existing private S3 buckets. '
                               'Does not create buckets or manage their configuration. No EC2 replacement.')
    for logical in ('WebsiteBucket', 'BackupBucket'):
        del template['Resources'][logical]
        template['Parameters']['Existing' + logical + 'Name'] = string(
            AllowedPattern=r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]',
            Description='Same-account us-east-1 private bucket, verified with recovery_preflight.py before deployment.')

    def rewrite(value):
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if not isinstance(value, dict):
            return value
        for logical in ('WebsiteBucket', 'BackupBucket'):
            parameter = 'Existing' + logical + 'Name'
            arn = 'arn:${AWS::Partition}:s3:::${' + parameter + '}'
            if value == ref(logical):
                return ref(parameter)
            if value == attr(logical, 'Arn'):
                return sub(arn)
            if value == attr(logical, 'RegionalDomainName'):
                return sub('${' + parameter + '}.s3.${AWS::Region}.${AWS::URLSuffix}')
        if isinstance(value.get('Fn::Sub'), str):
            expression = value['Fn::Sub']
            for logical in ('WebsiteBucket', 'BackupBucket'):
                expression = expression.replace('${' + logical + '.Arn}',
                    'arn:${AWS::Partition}:s3:::${Existing' + logical + 'Name}')
            return sub(expression)
        return {key: rewrite(item) for key, item in value.items()}

    return rewrite(template)


def behavior(policy, origin, function, dynamic=False, pattern=None, origin_policy=None):
    value = {'TargetOriginId': origin, 'ViewerProtocolPolicy': 'redirect-to-https',
        'AllowedMethods': ['GET', 'HEAD', 'OPTIONS', 'PUT', 'PATCH', 'POST', 'DELETE'] if dynamic else ['GET', 'HEAD'],
        'CachedMethods': ['GET', 'HEAD'], 'CachePolicyId': policy, 'Compress': True,
        'FunctionAssociations': [{'EventType': 'viewer-request', 'FunctionARN': attr(function, 'FunctionMetadata.FunctionARN')}]}
    if dynamic: value['OriginRequestPolicyId'] = ALL_VIEWER
    if origin_policy: value['OriginRequestPolicyId'] = origin_policy
    if pattern: value['PathPattern'] = pattern
    return value


def edge():
    t = base('GTT two CloudFront distributions: private S3 website and protected ALB business origins. No DNS changes.', {
        'FoundationStackName': string('gtt-foundation'), 'DomainName': domain_parameter(),
        'PriceClass': string('PriceClass_All', AllowedValues=['PriceClass_All', 'PriceClass_200', 'PriceClass_100']),
        'WafManagedRulesMode': string('COUNT', AllowedValues=['COUNT', 'BLOCK'])})
    t['Conditions'] = {'ObserveWaf': {'Fn::Equals': [ref('WafManagedRulesMode'), 'COUNT']}}
    r = t['Resources']
    r['WebsiteOac'] = resource('CloudFront::OriginAccessControl', OriginAccessControlConfig={
        'Name': sub('${AWS::StackName}-website'), 'OriginAccessControlOriginType': 's3',
        'SigningBehavior': 'always', 'SigningProtocol': 'sigv4'})
    for name, ttl, host, query in [('WebsiteCache', 300, False, 'none'), ('GameAssetCache', 86400, True, 'all')]:
        r[name] = resource('CloudFront::CachePolicy', CachePolicyConfig={'Name': sub('${AWS::StackName}-' + name),
            'MinTTL': 0, 'DefaultTTL': ttl, 'MaxTTL': 604800,
            'ParametersInCacheKeyAndForwardedToOrigin': {
                'EnableAcceptEncodingGzip': True, 'EnableAcceptEncodingBrotli': True,
                'CookiesConfig': {'CookieBehavior': 'none'},
                'HeadersConfig': {'HeaderBehavior': 'whitelist', 'Headers': ['Host']} if host else {'HeaderBehavior': 'none'},
                'QueryStringsConfig': {'QueryStringBehavior': query}}})
    r['AssetOriginPolicy'] = resource('CloudFront::OriginRequestPolicy', OriginRequestPolicyConfig={
        'Name': sub('${AWS::StackName}-asset-viewer-ip'), 'CookiesConfig': {'CookieBehavior': 'none'},
        'QueryStringsConfig': {'QueryStringBehavior': 'none'},
        'HeadersConfig': {'HeaderBehavior': 'whitelist', 'Headers': ['X-GTT-Client-IP']}})
    for name, filename in [('WebsiteFunction', 'website.js'), ('ViewerIpFunction', 'viewer-ip.js')]:
        code = (HERE / 'functions' / filename).read_text(encoding='utf-8')
        r[name] = resource('CloudFront::Function', Name=sub('${AWS::StackName}-' + name), AutoPublish=True,
            FunctionConfig={'Comment': 'GTT ' + name, 'Runtime': 'cloudfront-js-2.0'},
            FunctionCode=sub(code) if '${DomainName}' in code else code)
    r['BusinessWaf'] = resource('WAFv2::WebACL', Scope='CLOUDFRONT', DefaultAction={'Allow': {}},
        VisibilityConfig={'CloudWatchMetricsEnabled': True, 'MetricName': sub('${AWS::StackName}-business'), 'SampledRequestsEnabled': False},
        Rules=[{'Name': 'AwsCommon', 'Priority': 1,
            'OverrideAction': {'Fn::If': ['ObserveWaf', {'Count': {}}, {'None': {}}]},
            'Statement': {'ManagedRuleGroupStatement': {'VendorName': 'AWS', 'Name': 'AWSManagedRulesCommonRuleSet'}},
            'VisibilityConfig': {'CloudWatchMetricsEnabled': True, 'MetricName': sub('${AWS::StackName}-common'), 'SampledRequestsEnabled': False}}])
    errors = [{'ErrorCode': code, 'ErrorCachingMinTTL': 0} for code in (400, 403, 404, 405, 414, 416, 500, 501, 502, 503, 504)]
    common = {'Enabled': True, 'IPV6Enabled': False, 'HttpVersion': 'http2and3', 'PriceClass': ref('PriceClass'),
        'CustomErrorResponses': errors, 'ViewerCertificate': {'AcmCertificateArn': imported('CertificateArn'),
            'SslSupportMethod': 'sni-only', 'MinimumProtocolVersion': 'TLSv1.2_2021'}}
    r['WebsiteDistribution'] = resource('CloudFront::Distribution', DistributionConfig={**common,
        'Comment': 'GTT website, private S3 origin', 'Aliases': [ref('DomainName'), sub('www.${DomainName}')],
        'DefaultRootObject': 'index.html',
        'Origins': [{'Id': 'website', 'DomainName': imported('WebsiteBucketDomain'), 'OriginAccessControlId': ref('WebsiteOac'),
            'S3OriginConfig': {'OriginAccessIdentity': ''}}],
        'DefaultCacheBehavior': behavior(ref('WebsiteCache'), 'website', 'WebsiteFunction')})
    secret = {'Fn::Sub': ['{{resolve:secretsmanager:${SecretArn}:SecretString}}', {'SecretArn': imported('OriginSecretArn')}]}
    r['BusinessDistribution'] = resource('CloudFront::Distribution', DistributionConfig={**common,
        'Comment': 'GTT business, dynamic requests never cached',
        'Aliases': [sub(name + '.${DomainName}') for name in ('play', 'api', 'merchant', 'admin')],
        'WebACLId': attr('BusinessWaf', 'Arn'),
        'Origins': [{'Id': 'business', 'DomainName': imported('AlbDomainName'), 'ConnectionAttempts': 1,
            'ConnectionTimeout': 3, 'OriginCustomHeaders': [{'HeaderName': 'X-GTT-Origin-Verify', 'HeaderValue': secret}],
            'CustomOriginConfig': {'HTTPSPort': 443, 'OriginProtocolPolicy': 'https-only',
                'OriginSSLProtocols': ['TLSv1.2'], 'OriginReadTimeout': 30}}],
        'DefaultCacheBehavior': behavior(DISABLED, 'business', 'ViewerIpFunction', dynamic=True),
        'CacheBehaviors': [behavior(ref('GameAssetCache'), 'business', 'ViewerIpFunction', pattern=pattern,
            origin_policy=ref('AssetOriginPolicy')) for pattern in ('/assets/*', '/shared/*')]})
    r['WebsiteBucketPolicy'] = resource('S3::BucketPolicy', Bucket=imported('WebsiteBucketName'),
        PolicyDocument={'Version': '2012-10-17', 'Statement': [
            {'Sid': 'RequireTLS', 'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
             'Resource': [imported('WebsiteBucketArn'), {'Fn::Join': ['', [imported('WebsiteBucketArn'), '/*']]}],
             'Condition': {'Bool': {'aws:SecureTransport': 'false'}}},
            {'Sid': 'AllowWebsiteDistributionOnly', 'Effect': 'Allow', 'Principal': {'Service': 'cloudfront.amazonaws.com'},
             'Action': 's3:GetObject', 'Resource': {'Fn::Join': ['', [imported('WebsiteBucketArn'), '/*']]},
             'Condition': {'StringEquals': {'AWS:SourceArn': sub('arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${WebsiteDistribution}')}}}]})
    for name in ('WebsiteDistribution', 'BusinessDistribution'):
        t['Outputs'][name + 'Id'] = output(ref(name))
        t['Outputs'][name + 'Domain'] = output(attr(name, 'DomainName'))
    t['Outputs']['BusinessWafArn'] = output(attr('BusinessWaf', 'Arn'))
    return t


def generate():
    files = {'01-certificate.json': certificate(), '02-foundation.json': foundation(),
             '02-foundation-existing-buckets.json': foundation_existing_buckets(), '03-edge.json': edge()}
    for name, body in files.items():
        (HERE / name).write_text(json.dumps(body, indent=2) + '\n', encoding='utf-8', newline='\n')
    return {name: len(body['Resources']) for name, body in files.items()}


if __name__ == '__main__':
    print(json.dumps({'generated': generate(), 'deployed': False}))
