"""Publish immutable, verified asset objects. Never changes CloudFront, ACLs or public-access blocks."""
import argparse
import base64
import concurrent.futures
import json
from pathlib import Path

try:
    from .game_assets import ACCOUNT, BUCKET, DISTRIBUTION, digest, json_bytes, validate_manifest
except ImportError:
    from game_assets import ACCOUNT, BUCKET, DISTRIBUTION, digest, json_bytes, validate_manifest


def error_code(error):
    return str(getattr(error, 'response', {}).get('Error', {}).get('Code', ''))


def ensure_bucket(s3, bucket):
    created = False
    try:
        s3.head_bucket(Bucket=bucket, ExpectedBucketOwner=ACCOUNT)
    except Exception as error:
        if error_code(error) not in ('404', 'NoSuchBucket', 'NotFound'):
            raise
        # S3 defaults to all four protections enabled. No PutPublicAccessBlock call.
        s3.create_bucket(Bucket=bucket, ObjectOwnership='BucketOwnerEnforced')
        created = True
    scope = {'Bucket': bucket, 'ExpectedBucketOwner': ACCOUNT}
    region = s3.get_bucket_location(**scope).get('LocationConstraint') or 'us-east-1'
    blocks = s3.get_public_access_block(**scope)['PublicAccessBlockConfiguration']
    if region != 'us-east-1' or not all(blocks.get(key) is True for key in (
            'BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets')):
        raise ValueError('Bucket region or private access protection verification failed; stopped.')
    ownership = s3.get_bucket_ownership_controls(**scope)['OwnershipControls']['Rules']
    encryption = s3.get_bucket_encryption(**scope)['ServerSideEncryptionConfiguration']['Rules']
    if ownership != [{'ObjectOwnership': 'BucketOwnerEnforced'}] or not encryption or any(
            row['ApplyServerSideEncryptionByDefault']['SSEAlgorithm'] != 'AES256' for row in encryption):
        raise ValueError('Expected disabled ACLs and SSE-S3; review existing settings before proceeding.')
    try:
        policy = json.loads(s3.get_bucket_policy(**scope)['Policy'])
    except Exception as error:
        if error_code(error) != 'NoSuchBucketPolicy':
            raise
        policy = {'Statement': []}
    for statement in policy.get('Statement', []):
        if statement.get('Effect') != 'Allow':
            continue
        if (statement.get('Principal') != {'Service': 'cloudfront.amazonaws.com'}
                or statement.get('Action') != 's3:GetObject'
                or statement.get('Resource') != f'arn:aws:s3:::{bucket}/releases/buffalo-win/*'
                or statement.get('Condition') != {'StringEquals': {
                    'AWS:SourceArn': f'arn:aws:cloudfront::{ACCOUNT}:distribution/{DISTRIBUTION}'}}):
            raise ValueError('Existing bucket policy has an unreviewed Allow; stopped without modifying it.')
    if s3.get_bucket_versioning(**scope).get('Status') != 'Enabled':
        s3.put_bucket_versioning(**scope, VersioningConfiguration={'Status': 'Enabled'})
    try:
        lifecycle = s3.get_bucket_lifecycle_configuration(**scope)['Rules']
    except Exception as error:
        if error_code(error) != 'NoSuchLifecycleConfiguration':
            raise
        lifecycle = []
    expected = [{'ID': 'AbortIncompleteUploads', 'Filter': {'Prefix': ''}, 'Status': 'Enabled',
                 'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 7}}]
    if not lifecycle:
        s3.put_bucket_lifecycle_configuration(**scope, LifecycleConfiguration={'Rules': expected})
    elif lifecycle != expected:
        raise ValueError('Existing lifecycle needs review; no rules overwritten.')
    if s3.get_bucket_versioning(**scope).get('Status') != 'Enabled':
        raise ValueError('Versioning verification failed.')
    return {'created': created, 'region': region, 'public_access_block': blocks,
            'ownership': 'BucketOwnerEnforced', 'encryption': 'AES256', 'versioning': 'Enabled'}


def verify_head(head, row, release):
    checksum = base64.b64encode(bytes.fromhex(row['sha256'])).decode()
    if (head.get('ContentLength') != row['size'] or head.get('ChecksumSHA256') != checksum
            or head.get('ContentType') != row['content_type'] or head.get('CacheControl') != row['cache_control']
            or head.get('Metadata', {}).get('gtt-sha256') != row['sha256']
            or head.get('Metadata', {}).get('gtt-release') != release):
        raise ValueError('S3 object checksum or metadata mismatch: ' + row['path'])


def publish(s3, folder, bucket=BUCKET, progress=None):
    if bucket != BUCKET:
        raise ValueError('Expected the dedicated, confirmed project asset bucket.')
    folder = Path(folder)
    manifest = validate_manifest(json.loads((folder / 'manifest.json').read_bytes()))
    # Validate every local object before creating or modifying any remote resources.
    for row in manifest['files']:
        content = (folder / 'objects' / row['path']).read_bytes()
        if len(content) != row['size'] or digest(content) != row['sha256']:
            raise ValueError('Local asset differs from build manifest: ' + row['path'])
    safety = ensure_bucket(s3, bucket)

    def one(row):
        arguments = {'Bucket': bucket, 'Key': manifest['prefix'] + '/' + row['path'], 'ExpectedBucketOwner': ACCOUNT}
        try:
            head = s3.head_object(**arguments, ChecksumMode='ENABLED')
        except Exception as error:
            if error_code(error) not in ('404', 'NoSuchKey', 'NotFound'):
                raise
            content = (folder / 'objects' / row['path']).read_bytes()
            s3.put_object(**arguments, Body=content, ContentType=row['content_type'],
                CacheControl=row['cache_control'], ServerSideEncryption='AES256',
                ChecksumSHA256=base64.b64encode(bytes.fromhex(row['sha256'])).decode(), ChecksumAlgorithm='SHA256',
                Metadata={'gtt-sha256': row['sha256'], 'gtt-release': manifest['release']}, IfNoneMatch='*')
            head = s3.head_object(**arguments, ChecksumMode='ENABLED')
        verify_head(head, row, manifest['release'])

    # Fail fast on a denied write before submitting a whole upload batch.
    one(manifest['files'][0])
    completed, errors = 1, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(one, row): row['path'] for row in manifest['files'][1:]}
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            try:
                future.result()
            except Exception as error:
                errors.append({'path': futures[future], 'error': str(error)[:400]})
            if progress and (completed % 40 == 0 or completed == len(manifest['files'])):
                progress(completed, len(manifest['files']))
    if errors:
        report = {'status': 'failed', 'bucket': bucket, 'prefix': manifest['prefix'], 'errors': errors}
    else:
        # Commit only after all objects have verified checksums and metadata.
        content = json_bytes(manifest)
        s3.put_object(Bucket=bucket, ExpectedBucketOwner=ACCOUNT, Key=manifest['prefix'] + '/_gtt-manifest.json',
            Body=content, ContentType='application/json', CacheControl='no-store', ServerSideEncryption='AES256',
            ChecksumAlgorithm='SHA256', ChecksumSHA256=base64.b64encode(bytes.fromhex(digest(content))).decode(),
            Metadata={'gtt-release': manifest['release']})
        report = {'status': 'passed', 'bucket': bucket, 'prefix': manifest['prefix'],
                  'release': manifest['release'], 'verified_objects': completed, 'safety': safety,
                  'manifest_sha256': digest(content), 'cloudfront_modified': False}
    (folder / 'upload-receipt.json').write_bytes(json_bytes(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--profile')
    args = parser.parse_args()
    import boto3
    from botocore.config import Config
    session = boto3.Session(profile_name=args.profile, region_name='us-east-1')
    if session.client('sts').get_caller_identity()['Account'] != ACCOUNT:
        raise SystemExit('Wrong AWS account; stopped before any S3 writes.')
    s3 = session.client('s3', config=Config(max_pool_connections=10, retries={'mode': 'standard', 'max_attempts': 3}))
    report = publish(s3, args.folder, progress=lambda n, total: print(f'Uploaded/verified {n}/{total}', flush=True))
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['status'] == 'passed' else 1)
