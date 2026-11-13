import base64
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from deploy.gttgames.aws.game_assets import (ACCOUNT, BUCKET, DISTRIBUTION, CACHE_CONTROL, HERE,
    build, digest, eligible, json_bytes, migration_template, validate_manifest)
from deploy.gttgames.aws.publish_game_assets import ensure_bucket, publish
from deploy.gttgames.aws.asset_change_set import plan


class AwsError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {'Error': {'Code': code}}


class FakeS3:
    def __init__(self):
        self.objects, self.writes = {}, []
        self.blocks = dict.fromkeys(('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets'), True)

    def head_bucket(self, **kw): pass
    def get_bucket_location(self, **kw): return {'LocationConstraint': None}
    def get_public_access_block(self, **kw): return {'PublicAccessBlockConfiguration': self.blocks}
    def get_bucket_ownership_controls(self, **kw): return {'OwnershipControls': {'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]}}
    def get_bucket_encryption(self, **kw): return {'ServerSideEncryptionConfiguration': {'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]}}
    def get_bucket_policy(self, **kw): raise AwsError('NoSuchBucketPolicy')
    def get_bucket_versioning(self, **kw): return {'Status': 'Enabled'}
    def get_bucket_lifecycle_configuration(self, **kw):
        return {'Rules': [{'ID': 'AbortIncompleteUploads', 'Filter': {'Prefix': ''}, 'Status': 'Enabled',
                           'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 7}}]}
    def head_object(self, **kw):
        if kw['Key'] not in self.objects: raise AwsError('404')
        obj = self.objects[kw['Key']]
        return {'ContentLength': len(obj['Body']), **{k: obj[k] for k in ('ChecksumSHA256', 'ContentType', 'CacheControl', 'Metadata')}}
    def put_object(self, **kw):
        self.writes.append(kw['Key'])
        self.objects[kw['Key']] = kw
        return {}


class GameAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'source.zip'
        self.contents = {'clients/buffalo-win/assets/test.png': b'image bytes',
            'clients/buffalo-win/shared/test/index.js': b'raw module',
            'clients/buffalo-win/style.css': b'body{}',
            'clients/buffalo-win/index.html': b'entry must stay on EC2',
            'clients/buffalo-win/fixtures/secret.json': b'private fixture',
            'clients/buffalo-win/notes.txt': b'not public',
            'py/adapters/pg/client_modules.py': (HERE.parents[2] / 'py/adapters/pg/client_modules.py').read_bytes()}
        self.make_archive()
        self.folder, self.manifest = build(self.archive, self.root / 'build', processor=lambda b: (b'prepared ' + b, 'unused'))
        self.base = json.loads((HERE / '03-edge.json').read_bytes())

    def make_archive(self, corrupt=False):
        manifest = {'files': {name: digest(body) for name, body in self.contents.items()}}
        if corrupt: manifest['files']['clients/buffalo-win/assets/test.png'] = '0' * 64
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for name, body in self.contents.items(): archive.writestr(name, body)
            archive.writestr('release-manifest.json', json_bytes(manifest))

    def test_export_is_pinned_and_excludes_entry_private_fixtures_and_non_assets(self):
        self.assertEqual(len(self.manifest['files']), 3)
        self.assertEqual((self.folder / 'objects/shared/test/index.js').read_bytes(), b'prepared raw module')
        for name in ('index.html', 'fixtures/secret.json', 'notes.txt'):
            self.assertFalse((self.folder / 'objects' / name).exists())
        second, _ = build(self.archive, self.root / 'build', processor=lambda b: (b'prepared ' + b, 'unused'))
        self.assertEqual(second, self.folder)

    def test_corrupted_release_file_is_rejected(self):
        self.make_archive(corrupt=True)
        with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
            build(self.archive, self.root / 'bad', processor=lambda b: (b, ''))

    def test_historical_server_root_archive_remains_readable(self):
        self.contents['server/adapters/pg/client_modules.py'] = self.contents.pop('py/adapters/pg/client_modules.py')
        self.make_archive()
        folder, manifest = build(self.archive, self.root / 'historical',
                                 processor=lambda b: (b'prepared ' + b, 'unused'))
        self.assertEqual(manifest['files'], self.manifest['files'])
        self.assertEqual((folder / 'objects/shared/test/index.js').read_bytes(), b'prepared raw module')

    def test_unsafe_paths_and_modified_manifest_are_rejected(self):
        for path in ('../secret.js', '/assets/x.js', 'assets/../../config.json', 'assets\\x.js', 'fixtures/x.json'):
            self.assertFalse(eligible(path))
        bad = copy.deepcopy(self.manifest)
        bad['files'][0]['sha256'] = 'a' * 64
        with self.assertRaises(ValueError): validate_manifest(bad)

    def test_prepare_keeps_all_current_business_routes_and_adds_only_probe(self):
        prepared = migration_template(self.base, self.manifest, 'prepare')
        before = self.base['Resources']['BusinessDistribution']['Properties']['DistributionConfig']
        after = prepared['Resources']['BusinessDistribution']['Properties']['DistributionConfig']
        self.assertEqual(after['DefaultCacheBehavior'], before['DefaultCacheBehavior'])
        self.assertEqual(after['CacheBehaviors'][1:], before['CacheBehaviors'])
        self.assertEqual(after['CacheBehaviors'][0]['PathPattern'], '/__gtt-assets-check/*')
        for name, body in self.base['Resources'].items():
            if name != 'BusinessDistribution': self.assertEqual(prepared['Resources'][name], body)

    def test_activation_routes_only_known_static_paths_and_s3_does_not_forward_host_or_credentials(self):
        active = migration_template(self.base, self.manifest, 'activate')
        resources = active['Resources']
        routes = resources['BusinessDistribution']['Properties']['DistributionConfig']['CacheBehaviors']
        self.assertEqual({r['PathPattern'] for r in routes}, {'/__gtt-assets-check/*','/assets/*','/shared/*','/style.css'})
        for route in routes:
            self.assertNotIn('OriginRequestPolicyId', route)
            self.assertEqual(route['TargetOriginId'], 'game-assets')
        key = resources['GameS3Cache']['Properties']['CachePolicyConfig']['ParametersInCacheKeyAndForwardedToOrigin']
        self.assertEqual(key['HeadersConfig']['HeaderBehavior'], 'none')
        self.assertEqual(key['CookiesConfig']['CookieBehavior'], 'none')
        self.assertEqual(key['QueryStringsConfig']['QueryStringBehavior'], 'none')
        self.assertIn('GameAssetsBucketPolicy', resources['BusinessDistribution']['DependsOn'])
        # Fixed verified distribution ID avoids waiting for its update before installing S3 access policy.
        self.assertNotIn('"Ref": "BusinessDistribution"', json.dumps(resources['GameAssetsBucketPolicy']))
        self.assertFalse(any(r['Type']=='AWS::S3::Bucket' for r in resources.values()))

    def test_cloudfront_function_guards_other_portals_and_removes_query_credentials(self):
        template = migration_template(self.base, self.manifest, 'prepare')
        code = template['Resources']['GameAssetFunction']['Properties']['FunctionCode']['Fn::Sub'].replace('${DomainName}', 'gttgames.com')
        script = code + """
var input={request:{uri:'/__gtt-assets-check/shared/test/index.js', headers:{host:{value:'play.gttgames.com'}},querystring:{ops:{value:'private'}}}};
var result=handler(input);
if(result.uri!='/shared/test/index.js'||Object.keys(result.querystring).length)throw Error('bad rewrite');
input.request.headers.host.value='admin.gttgames.com';
if(handler(input).statusCode!==404)throw Error('host isolation');
"""
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        result = subprocess.run(['node', '-'], input=script, text=True, capture_output=True, creationflags=flags)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_s3_upload_verifies_checksums_and_commits_manifest_last(self):
        s3 = FakeS3()
        report = publish(s3, self.folder)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['verified_objects'], 3)
        self.assertTrue(s3.writes[-1].endswith('/_gtt-manifest.json'))
        for key, obj in s3.objects.items():
            self.assertTrue(key.startswith(self.manifest['prefix'] + '/'))
            self.assertEqual(obj['ServerSideEncryption'], 'AES256')
            self.assertNotIn('ACL', obj)
            self.assertEqual(obj['ChecksumSHA256'], base64.b64encode(bytes.fromhex(digest(obj['Body']))).decode())

    def test_s3_protection_or_local_corruption_failure_causes_no_object_writes(self):
        s3 = FakeS3(); s3.blocks['BlockPublicPolicy'] = False
        with self.assertRaises(ValueError): publish(s3, self.folder)
        self.assertEqual(s3.writes, [])
        s3 = FakeS3(); (self.folder / 'objects/style.css').write_bytes(b'changed')
        with self.assertRaises(ValueError): publish(s3, self.folder)
        self.assertEqual(s3.writes, [])

    def test_existing_wrong_object_is_not_overwritten_or_committed(self):
        s3 = FakeS3()
        row = self.manifest['files'][0]
        s3.objects[self.manifest['prefix']+'/'+row['path']] = {'Body': b'bad', 'ChecksumSHA256':'bad',
            'ContentType': row['content_type'], 'CacheControl': CACHE_CONTROL, 'Metadata': {}}
        with self.assertRaisesRegex(ValueError, 'mismatch'): publish(s3, self.folder)
        self.assertEqual(s3.writes, [])

    def test_activate_cannot_submit_change_set_without_full_probe_verification(self):
        prepared = migration_template(self.base, self.manifest, 'prepare')
        for name, value in [('edge-assets-prepare.json', prepared), ('edge-rollback.json', self.base)]:
            (self.folder / name).write_bytes(json_bytes(value))
        (self.folder / 'verify-probe.json').write_bytes(json_bytes({'status':'failed'}))
        calls = []
        def aws(service, action, *args):
            calls.append(action)
            return {'get-caller-identity': {'Account': ACCOUNT},
                'describe-stacks': {'Stacks':[{'StackStatus':'UPDATE_COMPLETE'}]},
                'describe-stack-resource': {'StackResourceDetail': {'PhysicalResourceId':DISTRIBUTION}},
                'get-template': {'TemplateBody': prepared},
                'get-public-access-block': {'PublicAccessBlockConfiguration':FakeS3().blocks},
                'head-object': {'ChecksumSHA256':base64.b64encode(bytes.fromhex(digest(json_bytes(self.manifest)))).decode()}}[action]
        with self.assertRaisesRegex(ValueError, 'probe verification'): plan(aws, self.folder, 'activate')
        self.assertNotIn('create-change-set', calls)


if __name__ == '__main__':
    unittest.main()
