"""Read-only inventory of failed-stack remnants and the two existing GTT S3 buckets."""
import argparse
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
BUCKETS = {
    'website': 'gtt-foundation-websitebucket-5q89fgxgjfpz',
    'backup': 'gtt-foundation-backupbucket-gkey3lhv1ajm',
}
ALLOWED = {
    ('sts', 'get-caller-identity'), ('cloudformation', 'describe-stacks'),
    ('cloudformation', 'list-stack-resources'),
    *{('s3api', action) for action in (
        'get-bucket-location', 'get-public-access-block', 'get-bucket-versioning',
        'get-bucket-encryption', 'get-bucket-ownership-controls',
        'get-bucket-lifecycle-configuration', 'get-bucket-policy')},
}
ABSENT = {'get-bucket-lifecycle-configuration': 'NoSuchLifecycleConfiguration',
          'get-bucket-policy': 'NoSuchBucketPolicy'}


class Aws:
    def __init__(self, region, profile=None):
        self.base = ['aws', '--region', region, '--no-cli-pager', '--output', 'json']
        if profile:
            self.base += ['--profile', profile]

    def __call__(self, service, action, *arguments):
        if (service, action) not in ALLOWED:
            raise ValueError('Only explicitly allowed read-only operations are supported.')
        result = subprocess.run(self.base + [service, action, *arguments], capture_output=True,
                                text=True, timeout=60)
        if result.returncode:
            code = re.search(r'\(([^()]+)\) when calling', result.stderr)
            if code and code.group(1) == ABSENT.get(action):
                return {}
            raise RuntimeError(service + ':' + action + ': ' + result.stderr.strip()[:1600])
        return json.loads(result.stdout)


def inspect(aws, environment, buckets=None):
    buckets = BUCKETS if buckets is None else buckets
    if environment['region'] != 'us-east-1' or len(set(buckets.values())) != 2:
        raise ValueError('Recovery requires two distinct project buckets in us-east-1.')
    account = environment['account_id']
    if aws('sts', 'get-caller-identity')['Account'] != account:
        raise ValueError('Wrong AWS account; stopped before reading project resources.')
    stack_name = environment['stacks']['foundation']
    stacks = aws('cloudformation', 'describe-stacks', '--stack-name', stack_name)['Stacks']
    stack = stacks[0]
    summaries = aws('cloudformation', 'list-stack-resources', '--stack-name', stack_name)['StackResourceSummaries']
    remnants = [{key: row.get(key) for key in (
        'LogicalResourceId', 'PhysicalResourceId', 'ResourceType', 'ResourceStatus')}
        for row in summaries if row['ResourceStatus'] != 'DELETE_COMPLETE']
    issues = []
    if stack['StackStatus'] != 'ROLLBACK_COMPLETE':
        issues.append('Wait for/review the failed stack state before recovery: ' + stack['StackStatus'])
    report = {'read_only': True, 'account_id': account, 'region': environment['region'],
              'failed_stack': stack_name, 'stack_status': stack['StackStatus'],
              'not_confirmed_deleted_resources': remnants, 'buckets': {}, 'issues': issues}
    for purpose, name in buckets.items():
        row = {'name': name, 'checks': {}, 'errors': []}
        report['buckets'][purpose] = row
        data = {}
        arguments = ('--bucket', name, '--expected-bucket-owner', account)
        for action in ('get-bucket-location', 'get-public-access-block', 'get-bucket-versioning',
                       'get-bucket-encryption', 'get-bucket-ownership-controls',
                       'get-bucket-lifecycle-configuration', 'get-bucket-policy'):
            try:
                data[action] = aws('s3api', action, *arguments)
            except RuntimeError as error:
                row['errors'].append(str(error))
        if row['errors']:
            issues.append(purpose + ': some settings could not be verified; read errors are not absence.')
        checks = row['checks']
        if 'get-bucket-location' in data:
            row['region'] = data['get-bucket-location'].get('LocationConstraint') or 'us-east-1'
            checks['same_region'] = row['region'] == environment['region']
        if 'get-public-access-block' in data:
            row['public_access_block'] = data['get-public-access-block'].get('PublicAccessBlockConfiguration', {})
            checks['all_public_access_blocks_enabled'] = all(row['public_access_block'].get(key) is True
                for key in ('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets'))
        if 'get-bucket-versioning' in data:
            row['versioning'] = data['get-bucket-versioning'].get('Status', 'NotEnabled')
            checks['versioning_enabled'] = row['versioning'] == 'Enabled'
        if 'get-bucket-encryption' in data:
            rules = data['get-bucket-encryption'].get('ServerSideEncryptionConfiguration', {}).get('Rules', [])
            row['encryption_algorithms'] = [rule.get('ApplyServerSideEncryptionByDefault', {}).get('SSEAlgorithm') for rule in rules]
            checks['sse_s3'] = row['encryption_algorithms'] == ['AES256']
        if 'get-bucket-ownership-controls' in data:
            rules = data['get-bucket-ownership-controls'].get('OwnershipControls', {}).get('Rules', [])
            row['ownership'] = [rule.get('ObjectOwnership') for rule in rules]
            checks['acl_disabled'] = row['ownership'] == ['BucketOwnerEnforced']
        if 'get-bucket-lifecycle-configuration' in data:
            rules = data['get-bucket-lifecycle-configuration'].get('Rules', [])
            row['lifecycle_rules'] = rules
            checks['abort_incomplete_uploads'] = any(rule.get('Status') == 'Enabled'
                and rule.get('Filter', {}) in ({}, {'Prefix': ''}) and not rule.get('Prefix')
                and 0 < rule.get('AbortIncompleteMultipartUpload', {}).get('DaysAfterInitiation', 0) <= 7
                for rule in rules)
            checks['no_unreviewed_lifecycle_rules'] = all(set(rule) <= {
                'ID', 'Status', 'Filter', 'Prefix', 'AbortIncompleteMultipartUpload'} for rule in rules)
        if 'get-bucket-policy' in data:
            # Do not print policy contents or overwrite an existing policy without review.
            row['bucket_policy_present'] = bool(data['get-bucket-policy'].get('Policy'))
            checks['no_existing_policy_to_overwrite'] = not row['bucket_policy_present']
        for check, passed in checks.items():
            if not passed:
                issues.append(purpose + ': ' + check)
    report['status'] = 'passed' if not issues else 'review_required'
    report['remaining_work'] = [
        'Review non-deleted resource summaries; these statuses do not prove physical existence.',
        'Existing bucket configuration stays externally managed; retain all four public-access blocks.',
        'Passed read checks do not prove deployment write permissions or SCP allowances.',
        'Do not update the ROLLBACK_COMPLETE stack; review a new recovery stack change set separately.',
    ]
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', type=Path, default=HERE / 'environment.json')
    parser.add_argument('--profile')
    args = parser.parse_args()
    try:
        environment = json.loads(args.environment.read_bytes())
        report = inspect(Aws(environment['region'], args.profile), environment)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report['status'] == 'passed' else 2)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'status': 'failed', 'read_only': True, 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(1)
