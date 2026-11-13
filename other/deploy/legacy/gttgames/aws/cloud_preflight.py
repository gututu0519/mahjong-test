"""Read-only control-plane checks and optional foundation parameter generation."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent


class Aws:
    def __init__(self, region, profile=None):
        self.base = ['aws', '--region', region, '--no-cli-pager', '--output', 'json']
        if profile:
            self.base += ['--profile', profile]

    def __call__(self, service, action, *arguments):
        if not (action.startswith(('describe-', 'list-')) or (service, action) == ('sts', 'get-caller-identity')):
            raise ValueError('Read-only inventory operation required.')
        value = subprocess.run(self.base + [service, action, *arguments], capture_output=True, text=True, timeout=60)
        if value.returncode:
            raise RuntimeError(service + ':' + action + ': ' + value.stderr.strip()[:2000])
        return json.loads(value.stdout)


def inspect(aws, environment, certificate_arn=None):
    identity = aws('sts', 'get-caller-identity')
    if identity['Account'] != environment['account_id']:
        raise ValueError('AWS account differs from the confirmed project account; stopped.')
    if environment['region'] != 'us-east-1':
        raise ValueError('This deployment requires us-east-1.')
    reservations = aws('ec2', 'describe-instances', '--instance-ids', environment['instance_id'])['Reservations']
    instances = [item for row in reservations for item in row['Instances']]
    if len(instances) != 1:
        raise ValueError('Expected the single existing EC2 instance.')
    instance = instances[0]
    if instance['VpcId'] != environment['vpc_id'] or instance['State']['Name'] != 'running':
        raise ValueError('Existing EC2 must be running in the confirmed VPC.')
    groups = {row['GroupId'] for row in instance['SecurityGroups']}
    if environment['instance_security_group_id'] not in groups:
        raise ValueError('Confirmed application security group is not attached to the instance.')
    subnets = aws('ec2', 'describe-subnets', '--subnet-ids', *environment['alb_subnets'])['Subnets']
    if len(subnets) != 2 or len({row['AvailabilityZone'] for row in subnets}) != 2:
        raise ValueError('ALB needs exactly two selected subnets in different Availability Zones.')
    if instance['Placement']['AvailabilityZone'] not in {row['AvailabilityZone'] for row in subnets}:
        raise ValueError('An ALB subnet must enable the existing target instance Availability Zone.')
    for row in subnets:
        if (row['VpcId'] != environment['vpc_id'] or ipaddress.ip_network(row['CidrBlock']).prefixlen > 27
                or row['AvailableIpAddressCount'] < 8 or row['State'] != 'available'):
            raise ValueError('Selected ALB subnet fails VPC, CIDR, free-IP or state requirement: ' + row['SubnetId'])
    filters = 'Name=vpc-id,Values=' + environment['vpc_id']
    tables = aws('ec2', 'describe-route-tables', '--filters', filters)['RouteTables']
    gateways = aws('ec2', 'describe-internet-gateways', '--filters',
        'Name=attachment.vpc-id,Values=' + environment['vpc_id'])['InternetGateways']
    gateway_ids = {row['InternetGatewayId'] for row in gateways}
    routes = []
    for subnet in subnets:
        chosen = [table for table in tables if any(a.get('SubnetId') == subnet['SubnetId'] for a in table['Associations'])]
        if not chosen:
            chosen = [table for table in tables if any(a.get('Main') for a in table['Associations'])]
        if len(chosen) != 1:
            raise ValueError('Cannot determine unique effective route table: ' + subnet['SubnetId'])
        defaults = [route for route in chosen[0]['Routes'] if route.get('DestinationCidrBlock') == '0.0.0.0/0']
        if not any(route.get('State') == 'active' and route.get('GatewayId') in gateway_ids for route in defaults):
            raise ValueError('Selected ALB subnet lacks an active default route to an attached IGW: ' + subnet['SubnetId'])
        routes.append({'subnet_id': subnet['SubnetId'], 'route_table_id': chosen[0]['RouteTableId'], 'default_routes': defaults})
    prefix_lists = aws('ec2', 'describe-managed-prefix-lists', '--filters',
        'Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing')['PrefixLists']
    if len(prefix_lists) != 1:
        raise ValueError('Cannot resolve the AWS CloudFront origin-facing managed prefix list.')
    volumes = aws('ec2', 'describe-volumes', '--volume-ids',
        *[row['Ebs']['VolumeId'] for row in instance['BlockDeviceMappings'] if 'Ebs' in row])['Volumes']
    security = aws('ec2', 'describe-security-groups', '--group-ids', environment['instance_security_group_id'])['SecurityGroups']
    acls = aws('ec2', 'describe-network-acls', '--filters', filters)['NetworkAcls']
    selected_subnets = set(environment['alb_subnets']) | {instance['SubnetId']}
    acls = [row for row in acls if any(a['SubnetId'] in selected_subnets for a in row['Associations'])]
    warnings = []
    if any(not row['Encrypted'] for row in volumes):
        warnings.append('Existing EBS volume is unencrypted; resolve this separately before production cutover.')
    for acl in acls:
        for outbound in (False, True):
            ipv4 = sorted((rule for rule in acl['Entries'] if rule['Egress'] == outbound and 'CidrBlock' in rule), key=lambda row: row['RuleNumber'])
            if not ipv4 or not (ipv4[0]['RuleAction'] == 'allow' and ipv4[0]['Protocol'] == '-1' and ipv4[0]['CidrBlock'] == '0.0.0.0/0'):
                warnings.append('Custom IPv4 network ACL requires scoped traffic-rule review: ' + acl['NetworkAclId'])
                break
    if certificate_arn:
        expected = r'arn:aws:acm:us-east-1:' + re.escape(environment['account_id']) + r':certificate/[a-f0-9-]+'
        if not re.fullmatch(expected, certificate_arn):
            raise ValueError('Certificate must belong to this account in us-east-1.')
        cert = aws('acm', 'describe-certificate', '--certificate-arn', certificate_arn)['Certificate']
        names = set(cert.get('SubjectAlternativeNames', [])) | {cert['DomainName']}
        if cert['Status'] != 'ISSUED' or not {environment['domain_name'], '*.' + environment['domain_name']} <= names:
            raise ValueError('Expected an ISSUED ACM certificate covering the root and wildcard domains.')
    values = {'VpcId': environment['vpc_id'], 'AlbSubnetA': environment['alb_subnets'][0],
        'AlbSubnetB': environment['alb_subnets'][1], 'InstanceId': environment['instance_id'],
        'InstanceSecurityGroupId': environment['instance_security_group_id'],
        'CloudFrontPrefixListId': prefix_lists[0]['PrefixListId'], 'DomainName': environment['domain_name']}
    if certificate_arn:
        values['CertificateArn'] = certificate_arn
    report = {'status': 'passed' if not warnings else 'review_required', 'read_only': True,
        'account_id': identity['Account'], 'region': environment['region'],
        'instance_id': instance['InstanceId'], 'instance_profile': instance.get('IamInstanceProfile'),
        'subnets': [{key: row[key] for key in ('SubnetId', 'AvailabilityZone', 'CidrBlock', 'AvailableIpAddressCount')} for row in subnets],
        'routes': routes, 'security_groups': security,
        'volumes': [{key: row.get(key) for key in ('VolumeId', 'VolumeType', 'Size', 'Encrypted', 'KmsKeyId')} for row in volumes],
        'network_acls': acls, 'warnings': warnings,
        'foundation_parameters': [{'ParameterKey': key, 'ParameterValue': value} for key, value in values.items()]}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', type=Path, default=HERE / 'environment.json')
    parser.add_argument('--profile')
    parser.add_argument('--certificate-arn')
    parser.add_argument('--parameters-output', type=Path)
    args = parser.parse_args()
    environment = json.loads(args.environment.read_bytes())
    try:
        report = inspect(Aws(environment['region'], args.profile), environment, args.certificate_arn)
        if args.parameters_output:
            if report['status'] != 'passed' or not args.certificate_arn:
                raise ValueError('Parameter export requires passed checks and an issued certificate.')
            with args.parameters_output.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(report['foundation_parameters'], stream, indent=2)
                stream.write('\n')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (RuntimeError, ValueError) as error:
        print(json.dumps({'status': 'failed', 'read_only': True, 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(1)
