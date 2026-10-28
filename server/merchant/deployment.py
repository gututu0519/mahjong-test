"""Explicit public origins and the loopback reverse-proxy trust boundary."""
import ipaddress
import re
from urllib.parse import urlsplit

from server.core.contracts import ServiceError

ROLES = ('site', 'api', 'play', 'merchant', 'admin')


def public_origin(value):
    if not isinstance(value, str):
        raise ValueError('Public origins must be HTTPS origin strings.')
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError:
        raise ValueError('Invalid public origin port.') from None
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or value != value.strip() or parsed.netloc.lower() != parsed.netloc):
        raise ValueError('Public origins require HTTPS, lowercase hosts and no URL path or credentials.')
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in parsed.hostname.split('.')):
        raise ValueError('Public origins require valid DNS hostnames.')
    return value.rstrip('/')


class Deployment:
    def __init__(self, config=None):
        config = config or {}
        environment = config.get('environment', 'development')
        if environment not in ('development', 'production'):
            raise ValueError('environment must be development or production.')
        self.production = environment == 'production'
        self.origins = {}
        self.trusted_proxies = set()
        if self.production:
            supplied = config.get('public_origins', {})
            if not isinstance(supplied, dict) or set(supplied) != set(ROLES):
                raise ValueError('Production requires site, api, play, merchant and admin public origins.')
            self.origins = {role: public_origin(supplied[role]) for role in ROLES}
            if len({urlsplit(value).netloc for value in self.origins.values()}) != len(ROLES):
                raise ValueError('Public origin hosts must be distinct.')
            proxies = config.get('trusted_proxy_ips', ['127.0.0.1', '::1'])
            if not isinstance(proxies, list) or not proxies:
                raise ValueError('At least one loopback trusted proxy is required.')
            for value in proxies:
                address = ipaddress.ip_address(value)
                if not address.is_loopback:
                    raise ValueError('Backend services only trust loopback proxies.')
                self.trusted_proxies.add(str(address))

    def role(self, handler):
        host = handler.headers.get('Host', '')
        return next((role for role, origin in self.origins.items() if urlsplit(origin).netloc == host), None)

    def guard(self, handler, service):
        host = handler.headers.get('Host', '')
        local_hosts = {f'127.0.0.1:{handler.server.server_port}', f'localhost:{handler.server.server_port}'}
        origin = handler.headers.get('Origin')
        if not self.production:
            if host not in local_hosts:
                raise ServiceError('HOST_REJECTED', 'Unexpected Host header.', 403)
            if origin not in (None, 'http://' + host):
                raise ServiceError('ORIGIN_REJECTED', 'Cross-origin requests are not enabled.', 403)
            return
        # Direct loopback health probes are used by systemd/deployment checks.
        if handler.command == 'GET' and handler.path == '/health' and host in local_hosts and origin is None:
            return
        if handler.client_address[0] not in self.trusted_proxies:
            raise ServiceError('PROXY_REJECTED', 'A trusted reverse proxy is required.', 403)
        role = self.role(handler)
        if role not in (('api', 'play') if service == 'gateway' else ('merchant', 'admin')):
            raise ServiceError('HOST_REJECTED', 'Unexpected public host.', 403)
        if handler.headers.get('X-Forwarded-Proto') != 'https':
            raise ServiceError('HTTPS_REQUIRED', 'HTTPS is required.', 403)
        if origin not in (None, self.origins[role]):
            raise ServiceError('ORIGIN_REJECTED', 'Cross-origin requests are not enabled.', 403)
        path = urlsplit(handler.path).path
        if service == 'gateway':
            if (role == 'api') != path.startswith('/gtt/'):
                raise ServiceError('NOT_FOUND', 'Endpoint is not available on this host.', 404)
        elif path.startswith('/api/') and not path.startswith('/api/' + role + '/'):
            raise ServiceError('NOT_FOUND', 'Endpoint is not available on this host.', 404)

    def remote(self, handler):
        if self.production and handler.client_address[0] in self.trusted_proxies:
            try:
                return str(ipaddress.ip_address(handler.headers.get('X-Real-IP', '')))
            except ValueError:
                pass
        return handler.client_address[0]

    def browser_config(self, handler):
        return {'portal': self.role(handler),
                'merchant_url': self.origins.get('merchant', '') + '/' if self.production else '/merchant/',
                'admin_url': self.origins.get('admin', '') + '/' if self.production else '/',
                'home_url': self.origins.get('site', '') + '/' if self.production else '/'}
