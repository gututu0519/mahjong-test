import json
import logging
import re
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from server.core.contracts import ServiceError
from server.services.buffalo_demo import Handler as BuffaloHandler
from server.services.buffalo_preview import CLIENT
from .common import encode, read_object, signed_headers
from .mock_wallet import MockWallet
from .provider import MerchantService
from .wallet import NoRedirect


def post_gateway(config, path, payload):
    merchant_id = config['sandbox_merchant']
    secret = config['merchants'][merchant_id]['merchant_secret']
    body = encode(payload).encode()
    request = Request(config['gateway_origin'] + path, data=body,
                      headers=signed_headers(merchant_id, secret, path, body), method='POST')
    with build_opener(NoRedirect).open(request, timeout=8) as response:
        return json.load(response)['data']


class JSONRoutes:
    def json_response(self, status, data=None, error=None):
        body = encode({'data': data, 'error': error}).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def guard(self):
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        host = self.headers.get('Host', '')
        if host not in allowed:
            raise ServiceError('HOST_REJECTED', 'Unexpected Host header.', 403)
        if self.headers.get('Origin') not in (None, 'http://' + host):
            raise ServiceError('ORIGIN_REJECTED', 'Cross-origin requests are not enabled.', 403)

    def read_body(self):
        self.guard()
        if urlsplit(self.path).query:
            raise ServiceError('BAD_REQUEST', 'Signed routes do not accept query parameters.')
        if self.headers.get_content_type() != 'application/json':
            raise ServiceError('CONTENT_TYPE', 'Use application/json.', 415)
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= 16384:
            raise ServiceError('BODY_TOO_LARGE', 'Request must contain 1..16384 bytes.', 413)
        return self.rfile.read(length)

    def execute(self, action):
        try:
            action()
        except ServiceError as error:
            self.json_response(error.status, error={'code': error.code, 'message': str(error)})
        except (ValueError, TypeError, KeyError, UnicodeError):
            self.json_response(400, error={'code': 'BAD_REQUEST', 'message': 'Invalid request parameters.'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.exception('GTT request failed')
            self.json_response(503, error={'code': 'SERVICE_UNAVAILABLE', 'message': 'Request failed; inspect local service logs.'})


class GatewayHandler(JSONRoutes, BuffaloHandler):
    server_version = 'GTTGateway/1.0'

    def log_message(self, format, *args):
        message = re.sub(r'([?&](?:ops|atk|tk|token)=)[^&\s"]*', r'\1[redacted]', format % args)
        logging.info('%s %s', self.address_string(), message)

    def _post(self):
        path = urlsplit(self.path).path
        if path.startswith('/gtt/'):
            return self.execute(self.merchant_post)
        return super()._post()

    def merchant_post(self):
        path = urlsplit(self.path).path
        body = self.read_body()
        service = self.server.service
        merchant_id, _ = service.authenticate(self.headers, path, body, service.merchants)
        payload = read_object(body)
        if path == '/gtt/v1/games/list':
            self.json_response(200, service.catalog(merchant_id))
        elif path == '/gtt/v1/games/launch':
            self.json_response(201, service.launch(merchant_id, payload))
        elif path == '/gtt/v1/transactions/list':
            self.json_response(200, service.operations(merchant_id, payload))
        elif path == '/gtt/v1/transactions/retry':
            self.json_response(200, service.retry(merchant_id, payload.get('operation_id')))
        else:
            raise ServiceError('NOT_FOUND', 'Unknown GTT API endpoint.', 404)

    def launch_game(self, game_id, language='zh'):
        raise ServiceError('MERCHANT_AUTH_REQUIRED', 'Use the signed GTT launch endpoint.', 401)


def build_gateway(port, database, config, game=None):
    service = MerchantService(database, config['merchants'], game)
    handler = partial(GatewayHandler, directory=str(CLIENT))
    http = ThreadingHTTPServer(('127.0.0.1', port), handler)
    http.daemon_threads = True
    http.service = service
    http.service_id = 'gtt-gateway'
    from server.adapters.pg.buffalo_win import PGAdapter
    http.pg = PGAdapter(service)
    http.auth = json.loads((CLIENT / 'fixtures/auth-metadata.json').read_bytes())
    http.game_rule = json.loads((CLIENT / 'fixtures/game-rule.json').read_bytes())
    return http


class MockHandler(JSONRoutes, BaseHTTPRequestHandler):
    server_version = 'GTTMockPlatform/1.0'

    def log_message(self, format, *args):
        logging.info('Mock platform %s', format % args)

    def do_GET(self):
        self.execute(self.get)

    def get(self):
        self.guard()
        path = urlsplit(self.path).path
        if path == '/health':
            return self.json_response(200, {'status': 'ok', 'service_id': 'gtt-mock-platform'})
        if path == '/sandbox/status':
            config = self.server.config
            merchant_id = config['sandbox_merchant']
            payload = {'player_id': config['sandbox_player'], 'currency': config['merchants'][merchant_id]['currency'], 'minor_unit': 100}
            result = self.server.wallet.call(merchant_id, 'transactions/list', payload)
            return self.json_response(200, {'merchant_id': merchant_id, **result})
        if path == '/sandbox/prebet-policy':
            return self.json_response(200, {'maxWinMulti': self.server.wallet.prebet_policy(self.server.config['sandbox_merchant'])})
        if path != '/':
            raise ServiceError('NOT_FOUND', 'Unknown endpoint.', 404)
        from pathlib import Path
        body = Path(__file__).with_name('sandbox.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.execute(self.post)

    def post(self):
        body = self.read_body()
        path = urlsplit(self.path).path
        config = self.server.config
        if path == '/api/v1/callbacks/gtt/preBetDecision':
            payload = read_object(body)
            merchant_id, _ = self.server.wallet.authenticate(self.headers, path, body, config['merchants'], allow_disabled=True)
            result = self.server.wallet.prebet_decision(merchant_id, payload)
            raw = encode(result).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            return self.wfile.write(raw)
        if path == '/sandbox/prebet-policy':
            value = self.server.wallet.prebet_policy(config['sandbox_merchant'], read_object(body).get('maxWinMulti'))
            return self.json_response(200, {'maxWinMulti': value})
        if path == '/sandbox/launch':
            payload = read_object(body)
            result = post_gateway(config, '/gtt/v1/games/launch', {
                'player_id': config['sandbox_player'], 'game_id': 'buffalo-win',
                'language': payload.get('language', 'en'),
                **({'external_username': config['sandbox_external_username']} if config.get('sandbox_external_username') else {})})
            result['launch_url'] = config['gateway_origin'] + result['launch_url']
            return self.json_response(201, result)
        if not path.startswith('/wallet/v1/'):
            raise ServiceError('NOT_FOUND', 'Unknown endpoint.', 404)
        # Disabling a merchant stops new GTT play. Previously accepted wallet
        # operations can still be settled by an authorized administrator.
        merchant_id, _ = self.server.wallet.authenticate(self.headers, path, body, config['merchants'], allow_disabled=True)
        self.json_response(200, self.server.wallet.call(merchant_id, path.removeprefix('/wallet/v1/'), read_object(body)))


def build_platform(port, database, config):
    http = ThreadingHTTPServer(('127.0.0.1', port), MockHandler)
    http.daemon_threads = True
    http.wallet = MockWallet(database, config['merchants'])
    http.config = config
    http.wallet.seed(config['sandbox_merchant'], config['sandbox_player'], config['sandbox_balance_minor'])
    if config.get('sandbox_external_username'):
        http.wallet.bind_prebet_player(config['sandbox_merchant'], config['sandbox_player'], config['sandbox_external_username'])
    return http
