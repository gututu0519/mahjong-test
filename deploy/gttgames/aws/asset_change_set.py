"""Create, but never execute, guarded prepare/activate/rollback asset migration change sets."""
import argparse
import base64
import json
from pathlib import Path
import subprocess

try:
    from .game_assets import ACCOUNT, BUCKET, DISTRIBUTION, digest, json_bytes, validate_manifest
except ImportError:
    from game_assets import ACCOUNT, BUCKET, DISTRIBUTION, digest, json_bytes, validate_manifest

HERE = Path(__file__).resolve().parent


def plan(aws, folder, phase):
    folder = Path(folder)
    manifest = validate_manifest(json.loads((folder / 'manifest.json').read_bytes()))
    if aws('sts', 'get-caller-identity')['Account'] != ACCOUNT:
        raise ValueError('Wrong AWS account; stopped before changes.')
    stack = aws('cloudformation', 'describe-stacks', '--stack-name', 'gtt-edge')['Stacks'][0]
    if stack['StackStatus'] not in ('CREATE_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE'):
        raise ValueError('The edge stack is not ready for a new update.')
    physical = aws('cloudformation', 'describe-stack-resource', '--stack-name', 'gtt-edge',
                   '--logical-resource-id', 'BusinessDistribution')['StackResourceDetail']['PhysicalResourceId']
    if physical != DISTRIBUTION:
        raise ValueError('Existing business distribution does not match this migration.')
    current = aws('cloudformation', 'get-template', '--stack-name', 'gtt-edge', '--template-stage', 'Original')['TemplateBody']
    if isinstance(current, str):
        current = json.loads(current)
    expected = ['edge-rollback.json'] if phase == 'prepare' else ['edge-assets-prepare.json']
    if phase == 'rollback':
        expected = ['edge-assets-prepare.json', 'edge-assets-activate.json']
    if current not in [json.loads((folder / name).read_bytes()) for name in expected]:
        raise ValueError('Current stack template differs from the expected phase. Review before overwriting changes.')
    if phase != 'rollback':
        scope = ('--bucket', BUCKET, '--expected-bucket-owner', ACCOUNT)
        blocks = aws('s3api', 'get-public-access-block', *scope)['PublicAccessBlockConfiguration']
        if not all(blocks.get(key) is True for key in (
                'BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets')):
            raise ValueError('All four S3 public-access blocks must remain enabled.')
        head = aws('s3api', 'head-object', *scope, '--key', manifest['prefix'] + '/_gtt-manifest.json',
                   '--checksum-mode', 'ENABLED')
        expected_checksum = base64.b64encode(bytes.fromhex(digest(json_bytes(manifest)))).decode()
        if head.get('ChecksumSHA256') != expected_checksum:
            raise ValueError('S3 committed release manifest does not match this migration package.')
    if phase in ('prepare', 'activate'):
        required_check = 'baseline' if phase == 'prepare' else 'probe'
        receipt = json.loads((folder / ('verify-' + required_check + '.json')).read_bytes())
        if (receipt.get('status') != 'passed' or receipt.get('phase') != required_check or receipt.get('errors')
                or receipt.get('manifest_sha256') != digest(json_bytes(manifest))
                or receipt.get('checked') != len(manifest['files'])):
            raise ValueError('Full CDN ' + required_check + ' verification is required before this phase.')
    new_values = {'GameAssetsBucketName': BUCKET, 'GameAssetsReleasePrefix': manifest['prefix'],
                  'GameAssetsDistributionId': DISTRIBUTION}
    parameters = [{'ParameterKey': row['ParameterKey'], 'UsePreviousValue': True}
                  for row in stack['Parameters'] if row['ParameterKey'] not in new_values]
    if phase != 'rollback':
        parameters += [{'ParameterKey': key, 'ParameterValue': value} for key, value in new_values.items()]
    template = 'edge-rollback.json' if phase == 'rollback' else 'edge-assets-' + phase + '.json'
    parameter_path = folder / (phase + '-parameters.json')
    parameter_path.write_bytes(json_bytes(parameters))
    change_set = 'gtt-assets-' + phase + '-' + manifest['release'][:12]
    response = aws('cloudformation', 'create-change-set', '--stack-name', 'gtt-edge', '--change-set-type', 'UPDATE',
        '--change-set-name', change_set, '--template-body', 'file://' + str((folder / template).resolve()),
        '--parameters', 'file://' + str(parameter_path.resolve()))
    return {'submitted': True, 'executed': False, 'phase': phase, 'change_set_name': change_set, **response}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'activate', 'rollback'))
    parser.add_argument('--folder', type=Path, default=HERE)
    parser.add_argument('--profile')
    args = parser.parse_args()
    def aws(service, action, *arguments):
        command = ['aws', '--region', 'us-east-1', '--output', 'json', '--no-cli-pager']
        if args.profile:
            command += ['--profile', args.profile]
        result = subprocess.run(command + [service, action, *arguments], capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError(service + ':' + action + ': ' + result.stderr.strip()[:1500])
        return json.loads(result.stdout)
    print(json.dumps(plan(aws, args.folder, args.phase), indent=2))
