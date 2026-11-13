"""Build pinned game assets and reviewable CloudFormation migration templates; verify CDN bytes."""
import argparse
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import ssl
import stat
import sys
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
import zipfile

HERE = Path(__file__).resolve().parent
ACCOUNT = '817557336527'
BUCKET = 'gtt-game-assets-817557336527-us-east-1'
DISTRIBUTION = 'E3RCHQALSXUQDV'
PROBE = '/__gtt-assets-check'
CACHE_CONTROL = 'public, max-age=300, s-maxage=86400'
MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.js': 'application/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
        '.json': 'application/json; charset=utf-8', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg',
        '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf',
        '.webp': 'image/webp', '.wasm': 'application/wasm', '.bin': 'application/octet-stream'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def eligible(path):
    value = PurePosixPath(path)
    if not path or '\\' in path or value.is_absolute() or '..' in value.parts:
        return False
    return (value.suffix.lower() in MIME and
            (len(value.parts) == 1 or value.parts[0] in ('assets', 'shared')))


def validate_manifest(manifest):
    if manifest.get('format') != 1 or manifest.get('game') != 'buffalo-win':
        raise ValueError('Expected the pinned Buffalo Win asset manifest.')
    files = manifest['files']
    paths = [row['path'] for row in files]
    if not files or len(paths) != len(set(path.lower() for path in paths)) or not all(map(eligible, paths)):
        raise ValueError('Unsafe, duplicate or non-static asset paths.')
    for row in files:
        if row['content_type'] != MIME[PurePosixPath(row['path']).suffix.lower()]:
            raise ValueError('Unexpected asset MIME type.')
        if row['cache_control'] != CACHE_CONTROL or len(row['sha256']) != 64:
            raise ValueError('Invalid asset cache/checksum metadata.')
    seed = {'files': files, 'source_release_sha256': manifest['source_release_sha256']}
    release = digest(json_bytes(seed))[:20]
    if manifest['release'] != release or manifest['prefix'] != 'releases/buffalo-win/' + release:
        raise ValueError('Manifest identity does not match its contents.')
    return manifest


def build(archive_path, output_parent, processor=None):
    archive_path, output_parent = Path(archive_path), Path(output_parent)
    source_hash = digest(archive_path.read_bytes())
    if processor is None:
        root = HERE.parents[2]
        sys.path.insert(0, str(root))
        from py.adapters.pg.client_modules import prepare_module
        processor = prepare_module
    objects, entries = {}, []
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Release ZIP has duplicate entries.')
        source_manifest = json.loads(archive.read('release-manifest.json'))['files']
        # The exporter must use exactly the processor deployed in this release.
        # Previously published complete ZIPs still use the old server/ root.
        # Compare their processor bytes to the same implementation now in py/.
        processor_path = next((name for name in (
            'py/adapters/pg/client_modules.py',
            'server/adapters/pg/client_modules.py',
        ) if name in names), None)
        if processor_path is None:
            raise ValueError('The release is missing its module processor.')
        if archive.read(processor_path) != (HERE.parents[2] / 'py/adapters/pg/client_modules.py').read_bytes():
            raise ValueError('The local module processor differs from the deployed release.')
        for name in sorted(names):
            prefix = 'clients/buffalo-win/'
            if not name.startswith(prefix) or name.endswith('/'):
                continue
            relative = name.removeprefix(prefix)
            if not eligible(relative):
                continue
            if stat.S_ISLNK(archive.getinfo(name).external_attr >> 16):
                raise ValueError('Symlinks are not publishable game assets.')
            content = archive.read(name)
            if source_manifest.get(name) != digest(content):
                raise ValueError('Release manifest mismatch: ' + relative)
            original = digest(content)
            transformed = PurePosixPath(relative).name == 'index.js' and relative.startswith('shared/')
            if transformed:
                content, _ = processor(content)
            objects[relative] = content
            entries.append({'path': relative, 'size': len(content), 'sha256': digest(content),
                            'source_sha256': original, 'processed': transformed,
                            'content_type': MIME[PurePosixPath(relative).suffix.lower()],
                            'cache_control': CACHE_CONTROL})
    seed = {'files': entries, 'source_release_sha256': source_hash}
    release = digest(json_bytes(seed))[:20]
    manifest = validate_manifest({'format': 1, 'game': 'buffalo-win', 'release': release,
                                 'prefix': 'releases/buffalo-win/' + release, **seed})
    folder = output_parent / ('gtt-game-assets-' + release)
    folder.mkdir(parents=True, exist_ok=True)
    for relative, content in objects.items():
        target = folder / 'objects' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != content:
            raise ValueError('Existing build differs; refusing overwrite: ' + relative)
        target.write_bytes(content)
    (folder / 'manifest.json').write_bytes(json_bytes(manifest))
    return folder, manifest


def migration_template(base, manifest, phase):
    validate_manifest(manifest)
    if phase not in ('prepare', 'activate'):
        raise ValueError('Expected prepare or activate phase.')
    template = copy.deepcopy(base)
    parameters, resources = template['Parameters'], template['Resources']
    parameters.update({
        'GameAssetsBucketName': {'Type': 'String', 'AllowedPattern': '[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]'},
        'GameAssetsReleasePrefix': {'Type': 'String', 'AllowedPattern': 'releases/buffalo-win/[a-f0-9]{20}'},
        'GameAssetsDistributionId': {'Type': 'String', 'AllowedValues': [DISTRIBUTION]},
    })
    resources['GameAssetsOac'] = {'Type': 'AWS::CloudFront::OriginAccessControl', 'Properties': {
        'OriginAccessControlConfig': {'Name': {'Fn::Sub': '${AWS::StackName}-game-assets'},
            'OriginAccessControlOriginType': 's3', 'SigningBehavior': 'always', 'SigningProtocol': 'sigv4'}}}
    resources['GameS3Cache'] = {'Type': 'AWS::CloudFront::CachePolicy', 'Properties': {'CachePolicyConfig': {
        'Name': {'Fn::Sub': '${AWS::StackName}-GameS3Cache'}, 'MinTTL': 0, 'DefaultTTL': 86400, 'MaxTTL': 86400,
        'ParametersInCacheKeyAndForwardedToOrigin': {'EnableAcceptEncodingGzip': True, 'EnableAcceptEncodingBrotli': True,
            'CookiesConfig': {'CookieBehavior': 'none'}, 'HeadersConfig': {'HeaderBehavior': 'none'},
            'QueryStringsConfig': {'QueryStringBehavior': 'none'}}}}}
    function = """function handler(event) {
    var request = event.request;
    if (!request.headers.host || request.headers.host.value !== 'play.${DomainName}') {
        return {statusCode: 404, headers: {'cache-control': {value: 'no-store'}}};
    }
    var prefix = '/__gtt-assets-check/';
    if (request.uri.indexOf(prefix) === 0) {
        request.uri = request.uri.substring(prefix.length - 1);
    }
    request.querystring = {};
    return request;
}
"""
    resources['GameAssetFunction'] = {'Type': 'AWS::CloudFront::Function', 'Properties': {
        'Name': {'Fn::Sub': '${AWS::StackName}-GameAssetFunction'}, 'AutoPublish': True,
        'FunctionConfig': {'Comment': 'Play-only static S3 assets; no viewer credentials forwarded.', 'Runtime': 'cloudfront-js-2.0'},
        'FunctionCode': {'Fn::Sub': function}}}
    bucket_arn = {'Fn::Sub': 'arn:${AWS::Partition}:s3:::${GameAssetsBucketName}'}
    resources['GameAssetsBucketPolicy'] = {'Type': 'AWS::S3::BucketPolicy', 'Properties': {
        'Bucket': {'Ref': 'GameAssetsBucketName'}, 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
            {'Sid': 'RequireTLS', 'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
             'Resource': [bucket_arn, {'Fn::Sub': 'arn:${AWS::Partition}:s3:::${GameAssetsBucketName}/*'}],
             'Condition': {'Bool': {'aws:SecureTransport': 'false'}}},
            {'Sid': 'AllowGameDistribution', 'Effect': 'Allow', 'Principal': {'Service': 'cloudfront.amazonaws.com'},
             'Action': 's3:GetObject', 'Resource': {'Fn::Sub': 'arn:${AWS::Partition}:s3:::${GameAssetsBucketName}/releases/buffalo-win/*'},
             'Condition': {'StringEquals': {'AWS:SourceArn': {'Fn::Sub':
                 'arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${GameAssetsDistributionId}'}}}}
        ]}}}
    business = resources['BusinessDistribution']
    business['DependsOn'] = ['GameAssetsBucketPolicy']
    config = business['Properties']['DistributionConfig']
    config['Origins'].append({'Id': 'game-assets',
        'DomainName': {'Fn::Sub': '${GameAssetsBucketName}.s3.${AWS::Region}.${AWS::URLSuffix}'},
        'OriginPath': {'Fn::Sub': '/${GameAssetsReleasePrefix}'},
        'OriginAccessControlId': {'Ref': 'GameAssetsOac'}, 'S3OriginConfig': {'OriginAccessIdentity': ''}})

    def behavior(pattern):
        return {'PathPattern': pattern, 'TargetOriginId': 'game-assets', 'ViewerProtocolPolicy': 'redirect-to-https',
            'AllowedMethods': ['GET', 'HEAD'], 'CachedMethods': ['GET', 'HEAD'], 'Compress': True,
            'CachePolicyId': {'Ref': 'GameS3Cache'}, 'FunctionAssociations': [
                {'EventType': 'viewer-request', 'FunctionARN': {'Fn::GetAtt': ['GameAssetFunction', 'FunctionMetadata.FunctionARN']}}]}
    patterns = ['/assets/*', '/shared/*'] + ['/' + row['path'] for row in manifest['files'] if '/' not in row['path']]
    if phase == 'activate':
        config['CacheBehaviors'] = [behavior(path) for path in patterns]
    config['CacheBehaviors'].insert(0, behavior(PROBE + '/*'))
    if len(config['CacheBehaviors']) > 75:
        raise ValueError('Asset behavior count exceeds the documented default quota.')
    return template


def render_bundle(folder, manifest, base_path=None):
    folder = Path(folder)
    base = json.loads(Path(base_path or HERE / '03-edge.json').read_bytes())
    (folder / 'edge-rollback.json').write_bytes(json_bytes(base))
    for phase in ('prepare', 'activate'):
        # Compact JSON stays within CloudFormation TemplateBody's 51,200 byte limit.
        content = json.dumps(migration_template(base, manifest, phase), separators=(',', ':')).encode()
        if len(content) > 51200:
            raise ValueError('Migration template exceeds TemplateBody size limit.')
        (folder / ('edge-assets-' + phase + '.json')).write_bytes(content)
    parameters = [{'ParameterKey': key, 'ParameterValue': value} for key, value in {
        'FoundationStackName': 'gtt-foundation-v2', 'DomainName': 'gttgames.com',
        'PriceClass': 'PriceClass_All', 'WafManagedRulesMode': 'COUNT',
        'GameAssetsBucketName': BUCKET, 'GameAssetsReleasePrefix': manifest['prefix'],
        'GameAssetsDistributionId': DISTRIBUTION}.items()]
    (folder / 'asset-parameters.json').write_bytes(json_bytes(parameters))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def verify_cdn(manifest, phase, origin='https://play.gttgames.com', progress=None):
    validate_manifest(manifest)
    if phase not in ('baseline', 'probe', 'active') or origin != 'https://play.gttgames.com':
        raise ValueError('Expected a known verification phase and the production play origin.')
    prefix = PROBE if phase == 'probe' else ''

    def one(row):
        path = prefix + '/' + quote(row['path'], safe='/')
        client = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
        with client.open(Request(origin + path, headers={'Accept-Encoding': 'identity'}), timeout=25) as response:
            if response.status != 200:
                raise ValueError('Unexpected HTTP status: ' + row['path'])
            checksum, size = hashlib.sha256(), 0
            while chunk := response.read(65536):
                size += len(chunk)
                checksum.update(chunk)
            if checksum.hexdigest() != row['sha256'] or size != row['size']:
                raise ValueError('CDN content differs: ' + row['path'])
            actual_type = response.headers.get_content_type()
            expected_types = {row['content_type'].split(';')[0]}
            if phase == 'baseline' and row['path'].endswith('.js'):
                expected_types.update(('application/javascript', 'text/javascript'))
            if actual_type not in expected_types:
                raise ValueError('CDN MIME differs: ' + row['path'])
            if phase != 'baseline':
                if response.headers.get('x-amz-meta-gtt-release') != manifest['release']:
                    raise ValueError('S3 origin metadata missing: ' + row['path'])
                if 's-maxage=86400' not in response.headers.get('Cache-Control', ''):
                    raise ValueError('Static caching metadata missing: ' + row['path'])
        return row['path']
    errors, completed = [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(one, row): row['path'] for row in manifest['files']}
        for future in concurrent.futures.as_completed(futures):
            completed += 1
            try:
                future.result()
            except Exception as error:
                errors.append({'path': futures[future], 'error': str(error)[:300]})
            if progress and (completed % 40 == 0 or completed == len(futures)):
                progress(completed, len(futures))
    routing_checks = []
    if phase != 'baseline' and not errors:
        client = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
        checks = [('admin', '/deployment.json', 200, None), ('merchant', '/deployment.json', 200, None),
                  ('api', '/gtt/v1/games/list', 401, b'{}'), ('play', '/api/v1/wallet', 401, None)]
        checks += [(role, prefix + '/' + manifest['files'][0]['path'], 404, None)
                   for role in ('admin', 'merchant', 'api')]
        from urllib.error import HTTPError
        for role, path, expected, payload in checks:
            try:
                request = Request('https://' + role + '.gttgames.com' + path, data=payload,
                                  headers={'Content-Type': 'application/json'})
                try:
                    response = client.open(request, timeout=25)
                except HTTPError as error:
                    response = error
                with response:
                    if response.status != expected:
                        raise ValueError(f'Expected HTTP {expected}, got {response.status}')
                    if path == '/deployment.json' and json.load(response)['data']['portal'] != role:
                        raise ValueError('Wrong portal configuration.')
                routing_checks.append({'role': role, 'path': path, 'status': expected})
            except Exception as error:
                errors.append({'path': role + path, 'error': str(error)[:300]})
    return {'status': 'passed' if not errors else 'failed', 'phase': phase, 'release': manifest['release'],
            'manifest_sha256': digest(json_bytes(manifest)), 'checked': completed, 'errors': errors,
            'tls_validation': True, 'routing_checks': routing_checks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    builder = commands.add_parser('build')
    builder.add_argument('--archive', type=Path, required=True)
    builder.add_argument('--output-parent', type=Path, required=True)
    checker = commands.add_parser('verify')
    checker.add_argument('--manifest', type=Path, default=HERE / 'manifest.json')
    checker.add_argument('--phase', choices=('baseline', 'probe', 'active'), required=True)
    args = parser.parse_args()
    if args.command == 'build':
        folder, manifest = build(args.archive, args.output_parent)
        render_bundle(folder, manifest)
        print(json.dumps({'folder': str(folder.resolve()), 'release': manifest['release'],
                          'files': len(manifest['files']), 'bytes': sum(row['size'] for row in manifest['files'])}))
    else:
        manifest = validate_manifest(json.loads(args.manifest.read_bytes()))
        report = verify_cdn(manifest, args.phase, progress=lambda n, total: print(f'Checked {n}/{total}', flush=True))
        (args.manifest.parent / ('verify-' + args.phase + '.json')).write_bytes(json_bytes(report))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report['status'] == 'passed' else 1)
