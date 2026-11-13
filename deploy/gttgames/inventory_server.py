"""Read-only EC2/server inventory. Does not read keys, credentials or databases."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener


METADATA = 'http://169.254.169.254/latest/'


def collect_metadata(opener=None):
    opener = opener or build_opener(ProxyHandler({}))
    try:
        request = Request(METADATA + 'api/token', method='PUT',
                          headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'})
        with opener.open(request, timeout=3) as response:
            token = response.read(8192).decode()
    except Exception as error:
        return {'status': 'unavailable', 'error': type(error).__name__,
                'note': 'IMDSv2 could not be read; use EC2 console details. No settings were changed.'}

    def read(relative):
        request = Request(METADATA + relative, headers={'X-aws-ec2-metadata-token': token})
        with opener.open(request, timeout=3) as response:
            return response.read(65536).decode().strip()

    result = {'status': 'available', 'errors': {}}
    try:
        identity = json.loads(read('dynamic/instance-identity/document'))
        result['identity'] = {name: identity.get(name) for name in
                              ('accountId', 'instanceId', 'instanceType', 'imageId',
                               'region', 'availabilityZone', 'privateIp')}
    except Exception as error:
        result['errors']['identity'] = type(error).__name__
    try:
        interfaces = []
        for mac in read('meta-data/network/interfaces/macs/').splitlines():
            prefix = 'meta-data/network/interfaces/macs/' + mac.strip('/') + '/'
            interface = {'mac': mac.strip('/')}
            for name in ('interface-id', 'vpc-id', 'subnet-id', 'security-group-ids', 'local-ipv4s'):
                try:
                    interface[name] = read(prefix + name).splitlines()
                except Exception as error:
                    interface[name] = {'error': type(error).__name__}
            interfaces.append(interface)
        result['interfaces'] = interfaces
    except Exception as error:
        result['errors']['interfaces'] = type(error).__name__
    try:
        # /iam/info describes the instance profile; never query security-credentials.
        info = json.loads(read('meta-data/iam/info'))
        result['instance_profile'] = {name: info.get(name) for name in
                                      ('Code', 'InstanceProfileArn', 'InstanceProfileId')}
    except HTTPError as error:
        result['instance_profile'] = {'status': 'not_attached' if error.code == 404 else 'unavailable',
                                      'http_status': error.code}
    except Exception as error:
        result['errors']['instance_profile'] = type(error).__name__
    return result


def command(arguments):
    try:
        value = subprocess.run(arguments, capture_output=True, text=True, timeout=10,
                               check=False, env={**os.environ, 'LC_ALL': 'C'})
        return {'exit_code': value.returncode,
                'stdout': value.stdout.strip()[:16000], 'stderr': value.stderr.strip()[:4000]}
    except Exception as error:
        return {'error': type(error).__name__}


def collect():
    result = {'format': 1, 'read_only': True,
              'system': {'os': platform.system(), 'release': platform.release(),
                         'architecture': platform.machine(), 'python': platform.python_version(),
                         'logical_cpu_count': os.cpu_count()},
              'collected': ['EC2 identity/network IDs', 'instance profile ARN without credentials',
                            'runtime versions', 'disk space', 'listening sockets', 'service state',
                            'Nginx site filenames'],
              'not_collected': ['passwords', 'SSH private keys', 'AWS credentials',
                                'merchant keys', 'database contents', 'application logs', 'Nginx config contents']}
    if platform.system() != 'Linux':
        result['status'] = 'run_on_target_linux_server'
        return result
    result['ec2'] = collect_metadata()
    result['node'] = command(['node', '--version'])
    nginx = '/www/server/nginx/sbin/nginx'
    result['nginx'] = command([nginx, '-v']) if Path(nginx).is_file() else {'status': 'baota_nginx_not_found'}
    result['disk_space'] = {}
    for directory in ('/', '/var/lib/gtt', '/opt/gtt/current'):
        if Path(directory).exists():
            usage = shutil.disk_usage(directory)
            result['disk_space'][directory] = {'total_gib': round(usage.total / 1024 ** 3, 2),
                                               'free_gib': round(usage.free / 1024 ** 3, 2)}
    result['listening_sockets'] = command(['ss', '-lnt'])
    units = ('gtt-gateway.service', 'gtt-admin.service', 'gtt-rtp-worker.service',
             'amazon-ssm-agent.service', 'snap.amazon-ssm-agent.amazon-ssm-agent.service')
    result['services'] = {unit: command(['systemctl', 'show', unit,
                                        '--property=LoadState,ActiveState,SubState']) for unit in units}
    sites = Path('/www/server/panel/vhost/nginx')
    result['nginx_site_filenames'] = sorted(path.name for path in sites.glob('*.conf')) if sites.is_dir() else []
    return result


if __name__ == '__main__':
    print(json.dumps(collect(), ensure_ascii=False, indent=2))
