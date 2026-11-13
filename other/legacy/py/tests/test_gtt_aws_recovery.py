import copy
import json
import subprocess
import unittest
from unittest.mock import patch

from deploy.gttgames.aws.build_templates import foundation, foundation_existing_buckets
from deploy.gttgames.aws.recovery_preflight import Aws, inspect


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.environment = {'account_id': '123456789012', 'region': 'us-east-1',
                            'stacks': {'foundation': 'gtt-foundation'}}
        self.data = {
            ('sts', 'get-caller-identity'): {'Account': '123456789012'},
            ('cloudformation', 'describe-stacks'): {'Stacks': [{'StackStatus': 'ROLLBACK_COMPLETE'}]},
            ('cloudformation', 'list-stack-resources'): {'StackResourceSummaries': [
                {'LogicalResourceId': 'OriginSecret', 'PhysicalResourceId': 'arn:secret:metadata-only',
                 'ResourceType': 'AWS::SecretsManager::Secret', 'ResourceStatus': 'DELETE_SKIPPED'},
                {'LogicalResourceId': 'AlarmTopic', 'ResourceStatus': 'DELETE_COMPLETE'}]},
            ('s3api', 'get-bucket-location'): {'LocationConstraint': None},
            ('s3api', 'get-public-access-block'): {'PublicAccessBlockConfiguration': dict.fromkeys((
                'BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets'), True)},
            ('s3api', 'get-bucket-versioning'): {'Status': 'Enabled'},
            ('s3api', 'get-bucket-encryption'): {'ServerSideEncryptionConfiguration': {'Rules': [
                {'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]}},
            ('s3api', 'get-bucket-ownership-controls'): {'OwnershipControls': {'Rules': [
                {'ObjectOwnership': 'BucketOwnerEnforced'}]}},
            ('s3api', 'get-bucket-lifecycle-configuration'): {'Rules': [
                {'ID': 'Abort', 'Status': 'Enabled', 'Filter': {'Prefix': ''},
                 'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 7}}]},
            ('s3api', 'get-bucket-policy'): {},
        }
        self.calls = []

    def aws(self, service, action, *arguments):
        self.calls.append((service, action, arguments))
        value = self.data[(service, action)]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    def test_verified_buckets_pass_and_remnants_remain_visible_without_secret_reads(self):
        report = inspect(self.aws, self.environment)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(len(report['not_confirmed_deleted_resources']), 1)
        for service, action, args in self.calls:
            self.assertNotEqual(service, 'secretsmanager')
            if service == 's3api':
                self.assertEqual(args[-2:], ('--expected-bucket-owner', '123456789012'))

    def test_wrong_account_stops_before_resource_reads(self):
        self.data[('sts', 'get-caller-identity')]['Account'] = '999999999999'
        with self.assertRaisesRegex(ValueError, 'Wrong AWS account'):
            inspect(self.aws, self.environment)
        self.assertEqual(len(self.calls), 1)

    def test_partial_bucket_configuration_cannot_pass(self):
        self.data[('s3api', 'get-bucket-versioning')] = {}
        self.data[('s3api', 'get-bucket-lifecycle-configuration')] = {}
        report = inspect(self.aws, self.environment)
        self.assertEqual(report['status'], 'review_required')
        self.assertIn('website: versioning_enabled', report['issues'])
        self.assertIn('backup: abort_incomplete_uploads', report['issues'])

    def test_weak_public_access_protection_cannot_pass(self):
        self.data[('s3api', 'get-public-access-block')]['PublicAccessBlockConfiguration']['BlockPublicPolicy'] = False
        self.assertEqual(inspect(self.aws, self.environment)['status'], 'review_required')

    def test_read_access_denied_is_not_treated_as_missing_configuration(self):
        self.data[('s3api', 'get-bucket-policy')] = RuntimeError('AccessDenied')
        report = inspect(self.aws, self.environment)
        self.assertEqual(report['status'], 'review_required')
        self.assertEqual(report['buckets']['website']['errors'], ['AccessDenied'])
        self.assertNotIn('no_existing_policy_to_overwrite', report['buckets']['website']['checks'])

    def test_existing_policy_requires_review_and_is_not_printed(self):
        self.data[('s3api', 'get-bucket-policy')] = {'Policy': 'private policy text fixture'}
        report = inspect(self.aws, self.environment)
        self.assertEqual(report['status'], 'review_required')
        self.assertNotIn('private policy text fixture', json.dumps(report))

    def test_prefix_lifecycle_and_unreviewed_expiration_require_review(self):
        rules = self.data[('s3api', 'get-bucket-lifecycle-configuration')]['Rules']
        rules[0]['Filter'] = {'Prefix': 'only-this-prefix/'}
        rules.append({'ID': 'Delete', 'Status': 'Enabled', 'Expiration': {'Days': 1}})
        checks = inspect(self.aws, self.environment)['buckets']['website']['checks']
        self.assertFalse(checks['abort_incomplete_uploads'])
        self.assertFalse(checks['no_unreviewed_lifecycle_rules'])

    def test_cli_allows_known_absence_but_propagates_access_denied(self):
        aws = Aws('us-east-1')
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 254, '',
                'An error occurred (NoSuchBucketPolicy) when calling the GetBucketPolicy operation: absent')):
            self.assertEqual(aws('s3api', 'get-bucket-policy'), {})
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 254, '',
                'An error occurred (AccessDenied) when calling the GetBucketPolicy operation: denied')):
            with self.assertRaisesRegex(RuntimeError, 'AccessDenied'):
                aws('s3api', 'get-bucket-policy')

    def test_cli_rejects_mutations_and_secret_reads_before_execution(self):
        with patch('subprocess.run') as process:
            for service, action in [('s3api', 'put-public-access-block'), ('cloudformation', 'delete-stack'),
                                    ('secretsmanager', 'get-secret-value')]:
                with self.assertRaises(ValueError):
                    Aws('us-east-1')(service, action)
            process.assert_not_called()

    def test_existing_bucket_template_preserves_ingress_and_narrow_backup_scopes(self):
        original, recovery = foundation(), foundation_existing_buckets()
        self.assertEqual(len(recovery['Resources']), len(original['Resources']) - 2)
        self.assertNotIn('AWS::S3::Bucket', [r['Type'] for r in recovery['Resources'].values()])
        for logical in ('AlbSecurityGroup', 'GatewayIngress', 'ConsoleIngress', 'HttpsListener',
                        'GatewayRule', 'ConsoleRule'):
            self.assertEqual(recovery['Resources'][logical], original['Resources'][logical])
        serialized = json.dumps(recovery)
        for token in ('"Ref": "WebsiteBucket"', '"Ref": "BackupBucket"',
                      '${BackupBucket.Arn}', '${WebsiteBucket.Arn}'):
            self.assertNotIn(token, serialized)
        self.assertIn('arn:${AWS::Partition}:s3:::${ExistingBackupBucketName}/backups/*', serialized)
        self.assertIn('${ExistingWebsiteBucketName}.s3.${AWS::Region}.${AWS::URLSuffix}', serialized)
        self.assertEqual(set(recovery['Outputs']), set(original['Outputs']))
        self.assertEqual(recovery['Resources']['BackupBucketPolicy']['Properties']['Bucket'],
                         {'Ref': 'ExistingBackupBucketName'})


if __name__ == '__main__':
    unittest.main()
