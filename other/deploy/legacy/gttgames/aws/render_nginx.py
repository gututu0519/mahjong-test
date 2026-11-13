"""Render the ALB-only Nginx ingress. Writes only the requested output file."""
import argparse
from pathlib import Path
import re


def render(domain='gttgames.com'):
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]+\.[a-z]{2,}', domain):
        raise ValueError('Expected a lowercase public domain.')
    common = '''# Included by the existing Nginx http context. Existing port 80/TLS sites are untouched.
# Restrict ports 8080/8081 to the managed ALB security group before deploying.
log_format gtt_alb_safe '$http_x_gtt_client_ip $host $request_method $uri $status $body_bytes_sent $request_time';
limit_req_zone $http_x_gtt_client_ip zone=gtt_alb_login:10m rate=10r/m;
upstream gtt_alb_gateway { server 127.0.0.1:8110; keepalive 16; }
upstream gtt_alb_console { server 127.0.0.1:8112; keepalive 16; }
'''
    def proxy(upstream):
        return '''
        # The ALB accepts only the protected CloudFront origin. The viewer-request
        # function overwrites X-GTT-Client-IP, including attacker-supplied values.
        if ($http_x_gtt_client_ip = "") { return 403; }
        if ($http_x_forwarded_proto != "https") { return 403; }
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Real-IP $http_x_gtt_client_ip;
        proxy_set_header X-Forwarded-For $http_x_gtt_client_ip;
        proxy_set_header X-Forwarded-Host "";
        proxy_set_header Forwarded "";
        proxy_set_header X-GTT-Origin-Verify "";
        proxy_set_header Connection "";
        proxy_connect_timeout 3s;
        proxy_read_timeout 90s;
        proxy_send_timeout 30s;
        proxy_next_upstream off;
        proxy_cache off;
        proxy_redirect off;
        proxy_pass http://''' + upstream + ''';
'''
    def health(port, backend):
        return '''
server {
    listen PORT default_server;
    server_name _;
    access_log off;
    error_log /dev/null crit;
    location = /health {
        limit_except GET { deny all; }
        proxy_set_header Host 127.0.0.1:BACKEND;
        proxy_set_header Origin "";
        proxy_set_header Connection "";
        proxy_connect_timeout 2s;
        proxy_read_timeout 3s;
        proxy_next_upstream off;
        proxy_cache off;
        proxy_pass http://127.0.0.1:BACKEND;
    }
    location / { return 404; }
}
'''.replace('PORT', str(port)).replace('BACKEND', str(backend))
    def server(port, host, locations):
        return '''
server {
    listen PORT;
    server_name HOST;
    access_log /www/wwwlogs/gtt-alb-access.log gtt_alb_safe;
    # Full URLs can include player credentials, even in ordinary error messages.
    error_log /dev/null crit;
    client_max_body_size 16k;
    add_header Strict-Transport-Security "max-age=86400" always;
    add_header Referrer-Policy no-referrer always;
    add_header X-Content-Type-Options nosniff always;
LOCATIONS
}
'''.replace('PORT', str(port)).replace('HOST', host).replace('LOCATIONS', locations)
    gateway = 'gtt_alb_gateway'
    api = '''    location ^~ /gtt/v1/ {
        limit_except POST { deny all; }
''' + proxy(gateway) + '''    }
    location / { return 404; }'''
    play = '''    location ~ ^/(gtt|sandbox)(/|$) { return 404; }
    location = /health { return 404; }
    location / {
        limit_except GET POST { deny all; }
''' + proxy(gateway) + '    }'
    value = common + health(8080, 8110) + health(8081, 8112)
    value += server(8080, 'api.' + domain, api) + server(8080, 'play.' + domain, play)
    for role in ('merchant', 'admin'):
        routes = '''    location = /api/ROLE/login {
        limit_req zone=gtt_alb_login burst=5 nodelay;
        limit_req_status 429;
        limit_except POST { deny all; }
''' + proxy('gtt_alb_console') + '''    }
    location ^~ /api/ROLE/ {
        limit_except GET POST { deny all; }
''' + proxy('gtt_alb_console') + '''    }
    location ~ ^/(?:admin\\.(?:js|css)|deployment\\.json|merchant/)?$ {
        limit_except GET { deny all; }
''' + proxy('gtt_alb_console') + '''    }
    location / { return 404; }'''
        value += server(8081, role + '.' + domain, routes.replace('ROLE', role))
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', default='gttgames.com')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(render(args.domain))
    print('Rendered:', args.output)
