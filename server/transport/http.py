"""Versioned JSON routes shared by independent HTTP service entry points."""
import json
import logging
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit
from server.core.contracts import ServiceError


class PlatformRoutes:
    server_version = 'LocalGameServer/1.0'

    def log_message(self, format, *args):
        logging.info('%s %s', self.address_string(), format % args)

    def _json(self, status, data):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self._response(status, body, 'application/json; charset=utf-8')

    def _response(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Game-Engine', getattr(self.server, 'engine_mode', 'generated'))
        self.end_headers()
        self.wfile.write(body)

    def _token(self):
        auth = self.headers.get('Authorization', '')
        return auth[7:] if auth.startswith('Bearer ') else None

    def _guard_origin(self):
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            raise ServiceError('ORIGIN_REJECTED', 'Cross-origin writes are not enabled.', 403)

    def _handle(self, action):
        try:
            action()
        except ServiceError as error:
            self._json(error.status, {'dt': None, 'err': {'cd': error.code, 'msg': str(error)}})
        except (ValueError, UnicodeError, TypeError, KeyError) as error:
            self._json(400, {'dt': None, 'err': {'cd': 'BAD_REQUEST', 'msg': str(error)[:160]}})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.exception('Request failed')
            self._json(500, {'dt': None, 'err': {'cd': 'INTERNAL_ERROR', 'msg': 'Request was not committed.'}})

    def do_GET(self):
        self._handle(self._get)

    def _get(self):
        path = urlsplit(self.path).path
        service = self.server.service
        if path == '/health':
            self._json(200, {'status': 'ok', 'mode': 'generated', 'api_version': 1,
                             'service_id': getattr(self.server, 'service_id', 'development'),
                             'games': service.registry.catalog(), 'currency': 'DEMO'})
        elif path == '/api/v1/games':
            self._json(200, {'games': service.registry.catalog()})
        elif path == '/api/v1/wallet':
            self._json(200, service.wallet(self._token()))
        elif path == '/api/v1/history':
            limit = int(parse_qs(urlsplit(self.path).query).get('limit', ['20'])[0])
            self._json(200, {'spins': service.history(self._token(), limit)})
        elif path.startswith('/api/v1/games/') and path.endswith('/state'):
            game_id = path.removeprefix('/api/v1/games/').removesuffix('/state')
            self._json(200, service.state(self._token(), game_id))
        elif path.startswith(('/api/', '/game-api/', '/web-api/')):
            raise ServiceError('NOT_FOUND', 'Unknown API endpoint.', 404)
        else:
            self.serve_assets()

    def do_POST(self):
        self._handle(self._post)

    def _post(self):
        self._guard_origin()
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 <= length <= 16384:
            raise ServiceError('BODY_TOO_LARGE', 'Request body exceeds 16 KiB.', 413)
        body = self.rfile.read(length)
        path = urlsplit(self.path).path
        service = self.server.service
        if path.startswith('/api/'):
            if self.headers.get_content_type() != 'application/json':
                raise ServiceError('CONTENT_TYPE', 'Use application/json.', 415)
            payload = json.loads(body or b'{}')
            if not isinstance(payload, dict):
                raise ServiceError('BAD_REQUEST', 'Expected a JSON object.')
            if path == '/api/v1/sessions':
                self._json(201, service.create_session())
            elif path.startswith('/api/v1/games/') and path.endswith('/launch'):
                game_id = path.removeprefix('/api/v1/games/').removesuffix('/launch')
                self._json(201, self.launch_game(game_id, payload.get('language', 'zh')))
            elif path.startswith('/api/v1/games/') and path.endswith('/spin'):
                game_id = path.removeprefix('/api/v1/games/').removesuffix('/spin')
                result = service.spin(self._token(), game_id, self.headers.get('Idempotency-Key'),
                                      payload.get('previous_sid'), payload.get('bet', {}))
                self._json(200, result)
            else:
                raise ServiceError('NOT_FOUND', 'Unknown API endpoint.', 404)
            return
        self.compatibility_post(path, body)

    def launch_game(self, game_id, language='zh'):
        raise ServiceError('NOT_FOUND', 'This service does not host game clients.', 404)

    def compatibility_post(self, path, body):
        raise ServiceError("NOT_FOUND", "Unknown API endpoint.", 404)

    def serve_assets(self):
        raise ServiceError("NOT_FOUND", "This service exposes JSON API only.", 404)


class APIHandler(PlatformRoutes, BaseHTTPRequestHandler):
    pass
