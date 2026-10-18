"""Isolated Play'n GO client host and native HTTP command endpoint (8099)."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import json
import logging
import mimetypes
import re
from urllib.parse import parse_qs, urlencode, unquote, urlsplit

from server.adapters.playngo.tower_run import Adapter, CLIENT
from server.core.contracts import ServiceError
from server.core.service import GameService
from server.games.catalog import create_registry
from server.transport.http import PlatformRoutes


class Handler(PlatformRoutes, BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logging.info('%s %s', self.address_string(), re.sub(r'\?[^ ]*', '', fmt % args))

    def _response(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self' data: blob:; frame-src 'self'; worker-src 'self' blob:")
        if getattr(self, 'new_token', None):
            self.send_header('Set-Cookie', 'tower-session='+self.new_token+'; Path=/; HttpOnly; SameSite=Lax')
        self.end_headers()
        self.wfile.write(body)

    def token(self):
        cookies = SimpleCookie(self.headers.get('Cookie',''))
        item = cookies.get('tower-session')
        if not item:
            raise ServiceError('SESSION_INVALID', 'Open the game first.', 401)
        self.server.service.wallet(item.value)
        return item.value

    def launch_game(self, game_id, language='en'):
        if game_id != 'tower-run-treasure-steps':
            raise ServiceError('NOT_FOUND', 'Unknown game.', 404)
        if language not in ('zh','en'):
            raise ServiceError('LANGUAGE_INVALID','Supported languages: zh, en.')
        session = self.server.service.create_session()
        return dict(game_id=game_id, language=language, client_language='zh_CN' if language=='zh' else 'en_GB',
                    launch_url='/?'+urlencode(dict(mock=1,ops=session['token'],lang=language)))

    def localize(self, value):
        if isinstance(value, dict):
            return {k:self.localize(v) for k,v in value.items()}
        if isinstance(value, list):
            return [self.localize(v) for v in value]
        if isinstance(value, str):
            for host, prefix in (('https://cdn.playngonetwork.com','/cdn'),('https://pc-prod-eu.playngonetwork.com','/platform'),
                                 ('https://asccw.playngonetwork.com',''),('https://ascflyp.playngonetwork.com',''),('https://released.playngonetwork.com','')):
                value = value.replace(host,prefix)
            # These fields also occur as JSON strings (module configuration).
            return value
        return value

    def _get(self):
        u = urlsplit(self.path)
        q = parse_qs(u.query)
        if u.path == '/platform/player-events':
            from server.adapters.playngo.player_events import serve
            return serve(self)
        if u.path in ('/','/casino/ContainerLauncher'):
            token = q.get('ops',[''])[0]
            if not token:
                token = self.server.service.create_session()['token']
            self.server.service.wallet(token)
            self.new_token = token
            with self.server.service.connection() as db:
                player = self.server.service.sessions._player(db, token)
                keys = db.execute("SELECT request_key FROM spins WHERE player_id=? AND game_id='tower-run-treasure-steps'", (player['id'],)).fetchall()
                seq = max((int(r['request_key'].split(':')[1]) for r in keys if r['request_key'].startswith('playngo:')),default=0)
            html = (CLIENT/'fixtures/launcher.html').read_text(encoding='utf-8')
            html = re.sub(r'window.serverUrl\s*=\s*"[^"]+"', 'window.serverUrl = location.origin', html)
            html = html.replace('https://cdn.playngonetwork.com','/cdn')
            if q.get('lang') == ['zh']:
                html = html.replace('lang: "en_GB"','lang: "zh_CN"')
            html = html.replace('<head>', '<head><title>Tower Run Treasure Steps</title><script>window.localTowerOps='+json.dumps(token)+';window.localTowerSequence='+str(seq)+';</script><script src="/local-adapter.js"></script>')
            return self._response(200, html.encode(), 'text/html; charset=utf-8')
        if u.path in ('/games/1098','/games/getgamebygid/towerruntreasuresteps'):
            return self._json(200,json.loads((CLIENT/'fixtures/game.json').read_text(encoding='utf-8')))
        if u.path in ('/configuration/prelaunchconfiguration','/configuration/v2'):
            name = 'prelaunch.json' if 'prelaunch' in u.path else 'configuration.json'
            data = self.localize(json.loads((CLIENT/'fixtures'/name).read_text(encoding='utf-8')))
            if name=='prelaunch.json':
                data['Server'] = 'http://'+self.headers['Host']+'/'
                if q.get('lang') == ['zh_CN']:
                    data['Language']='zh_CN'
            else:
                history='/history'
                if q.get('ops'):
                    self.server.service.wallet(q['ops'][0])
                    history+='?'+urlencode(dict(ops=q['ops'][0]))
                data.update(defaultProtocol='http', lobbyUrl='http://127.0.0.1:8080/demo/',
                            desktopGameHistoryUrl=history,mobileGameHistoryUrl=history)
            return self._json(200,data)
        if u.path == '/casino/gamehelp':
            name='help-zh.html' if q.get('lang',[''])[0] in ('zh','zh_CN') else 'help.html'
            text = self.localize((CLIENT/'fixtures'/name).read_text(encoding='utf-8'))
            text = text.replace('/Content/', '/released/Content/').replace('/casino/gamehelp/', '/released/casino/gamehelp/')
            return self._response(200,text.encode(),'text/html; charset=utf-8')
        if u.path == '/history':
            token=q.get('ops',[None])[0] or self.token()
            rows = self.server.service.history(token,100)
            pending=self.server.service.state(token,'tower-run-treasure-steps')['state']['pending']
            grouped={}
            for row in rows:
                if pending and row['round_id']==pending['round_id']:
                    continue
                item=grouped.setdefault(row['round_id'],dict(debit=0,credit=0,balance=row['wallet']['after_minor']))
                item['debit']+=row['wallet']['debit_minor']
                item['credit']+=row['wallet']['credit_minor']
            import html
            body=''.join('<tr><td>{}</td><td>{:.2f}</td><td>{:.2f}</td><td>{:.2f}</td></tr>'.format(html.escape(rid),item['debit']/100,item['credit']/100,item['balance']/100) for rid,item in grouped.items())
            text='<!doctype html><meta name="viewport" content="width=device-width"><title>Tower Run History</title><style>body{background:#14202b;color:#fff;font:16px system-ui;padding:24px}table{width:100%}td,th{text-align:right;padding:12px}</style><h1>Tower Run Treasure Steps</h1><table><tr><th>Round</th><th>Bet</th><th>Win</th><th>Balance</th></tr>'+body+'</table>'
            return self._response(200,text.encode(),'text/html; charset=utf-8')
        if u.path.endswith('/promotions/player/available'):
            return self._json(200,[])
        return super()._get()

    def serve_assets(self):
        name = unquote(urlsplit(self.path).path).lstrip('/')
        target = (CLIENT/name).resolve()
        if not name.startswith(('cdn/','platform/','released/')) and name != 'local-adapter.js':
            raise ServiceError('NOT_FOUND','Unknown resource.',404)
        asset_root=(CLIENT/name.split('/')[0]).resolve() if '/' in name else CLIENT.resolve()
        if not target.is_relative_to(asset_root) or not target.is_file():
            raise ServiceError('NOT_FOUND','Unknown resource.',404)
        mime = {'.js':'application/javascript','.json':'application/json','.atlas':'text/plain'}.get(target.suffix,mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        return self._response(200,target.read_bytes(),mime)

    def _post(self):
        if urlsplit(self.path).path != '/':
            return super()._post()
        self._guard_origin()
        length = int(self.headers.get('Content-Length','0'))
        if not 0 < length <= 65536:
            raise ServiceError('REQUEST_INVALID','Invalid request size.')
        form = parse_qs(self.rfile.read(length).decode('utf-8'),keep_blank_values=True)
        packet = form.get('d',[''])[0].splitlines()
        if len(packet) < 3 or not packet[0].isdigit():
            raise ServiceError('REQUEST_INVALID','Invalid packet.')
        token = packet[1].split('!',1)[0]
        self.server.service.wallet(token)
        sequence = int(packet[0])
        commands = [s for s in packet[2:] if s.strip()]
        output = []
        for command in commands:
            output.extend(self.server.playngo.call(token,sequence,command))
        return self._response(200, ('d='+'\r\n'.join(output)+'\r\n\r\n').encode(),'text/plain; charset=utf-8')


def build_server(port=8099,database=None,config=None):
    service_dir = CLIENT.parents[1]/'services/tower-run-treasure-steps'
    service = GameService(database or service_dir/'data/games.sqlite3',create_registry(['tower-run-treasure-steps'],{'tower-run-treasure-steps':config} if config else {}))
    http = ThreadingHTTPServer(('127.0.0.1',port),Handler)
    http.service, http.playngo = service,Adapter(service)
    http.service_id,http.engine_mode='tower-run-treasure-steps','generated'
    return http
