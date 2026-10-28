"""Read-only checks after DNS and trusted HTTPS certificates are installed."""
import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from server.merchant.deployment import Deployment


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def check(config):
    deployment = Deployment(config)
    if not deployment.production:
        raise ValueError('Expected production origins.')
    client = build_opener(NoRedirect)
    results = []
    def request(role, path, expected, method='GET', origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        req = Request(deployment.origins[role] + path, data=b'{}' if method == 'POST' else None,
                      headers=headers, method=method)
        try:
            response = client.open(req, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            if response.status != expected:
                raise RuntimeError(f'{role} {path}: expected {expected}, got {response.status}')
            results.append({'role': role, 'path': path, 'status': response.status})
            return response.read(16384)
    for role in ('merchant', 'admin'):
        request(role, '/', 200)
        runtime = json.loads(request(role, '/deployment.json', 200))['data']
        if runtime['portal'] != role:
            raise RuntimeError('Console portal mismatch.')
        request(role, '/api/' + role + '/me', 401)
        request(role, '/api/' + ('admin' if role == 'merchant' else 'merchant') + '/me', 404)
    request('api', '/gtt/v1/games/list', 401, 'POST')
    request('api', '/', 404)
    request('play', '/gtt/v1/games/list', 404, 'POST')
    request('play', '/api/v1/wallet', 401)
    request('merchant', '/api/merchant/login', 403, 'POST', deployment.origins['admin'])
    return {'status': 'passed', 'checks': results, 'tls_validation': 'enabled'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('/etc/gtt/production.json'))
    args = parser.parse_args()
    print(json.dumps(check(json.loads(args.config.read_bytes())), ensure_ascii=False))
