"""Isolated manual browser acceptance server using reproducible engine seeds.

Run from the repository root with python -m tools.jili_capture.serve_roma_acceptance.
This never changes the production service, probabilities, or wallet database.
"""
import json
import logging
import time
import threading
import argparse
import html
import re
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urlencode

from server.services.roma_x_10000_demo import Handler, ROOT
from server.adapters.jili.roma_x_10000 import Adapter, CLIENT
from server.core.service import GameService
from server.games.catalog import create_registry

OUT = ROOT / 'clients/roma-x-10000/diagnostics/acceptance'
CASES = {'free': '262', 'retrigger': '40720', 'battle': '4',
         'wheel': '23', 'cash': '68', 'max': '189', 'normal': '0'}
TELEMETRY_LOCK = threading.Lock()

OBSERVER = r"""(() => {
  const nativeFetch = window.fetch.bind(window), errors = [], commands = [];
  window.addEventListener('error', e => errors.push(String(e.message || e.target?.src || 'resource error')), true);
  window.addEventListener('unhandledrejection', e => errors.push(String(e.reason?.stack || e.reason)));
  window.fetch = async (input, init) => {
    const response = await nativeFetch(input, init);
    if (!response.ok) errors.push(response.status + ' ' + String(input).split('?')[0]);
    if (String(input) === '/jili/command') commands.push(JSON.parse(init.body).ack);
    return response;
  };
  setInterval(() => {
    try {
      const modules = [...(window.System?.entries?.() || [])];
      const primitives = {};
      for (const [name, exports] of modules) {
        if (!/CommonGameManager|GameController|GameView|Bottom|GameManager/.test(name)) continue;
        for (const [key, value] of Object.entries(exports)) {
          if (!value || typeof value !== 'object') continue;
          const fields = {};
          for (const prop of ['m_currState','IsGameIdle','IsGetInfo','IsAutoSpin','IsSpined','m_iState']) {
            try { if (['number','string','boolean'].includes(typeof value[prop])) fields[prop] = value[prop]; } catch {}
          }
          if (Object.keys(fields).length) primitives[name + ':' + key] = fields;
        }
      }
      const labels = [], nodes = [];
      function walk(node) {
        if (!node?.activeInHierarchy) return;
        nodes.push(node.name);
        for (const c of node.components || []) if (typeof c.string === 'string') labels.push(c.string);
        for (const child of node.children || []) walk(child);
      }
      walk(window.cc?.director?.getScene());
      nativeFetch('/_acceptance/telemetry', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({session:new URLSearchParams(location.search).get('ops'), primitives,
          labels, nodes, errors, commands, progress:typeof progressNow === 'undefined' ? null : progressNow})}).catch(()=>{});
    } catch (e) { errors.push(String(e)); }
  }, 1000);
})();"""


class AcceptanceHandler(Handler):
    def get(self):
        url = urlsplit(self.path)
        if url.path == '/_acceptance/observer.js':
            return super().respond(200, OBSERVER.encode(), 'application/javascript')
        if url.path.startswith('/_acceptance/start/'):
            case = url.path.rsplit('/', 1)[-1]
            if case not in CASES:
                return super().respond(404, {})
            service = self.server.service
            session = service.create_session()
            token = session['token']
            service.state(token, 'roma-x-10000')
            with service.connection(True) as db:
                player = service.sessions._player(db, token)
                state = json.loads(db.execute('SELECT state_json FROM game_states WHERE player_id=?', (player['id'],)).fetchone()[0])
                state['acceptance_seed'] = CASES[case]
                db.execute('UPDATE game_states SET state_json=? WHERE player_id=?', (json.dumps(state), player['id']))
            (OUT / (case + '-session.json')).write_text(json.dumps({'token': token, 'case': case}), encoding='utf-8')
            self.send_response(302)
            self.send_header('Location', self.launch(token))
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if url.path == '/_acceptance/portrait':
            src = html.escape('/?' + urlencode({'ops': parse_qs(url.query).get('ops', [''])[0]}), quote=True)
            return super().respond(200, ('<!doctype html><title>Roma portrait acceptance</title><style>body{margin:0;background:#222}iframe{width:390px;height:660px;border:0}</style><iframe src="' + src + '"></iframe>').encode(), 'text/html')
        return super().get()

    def respond(self, status, data, mime='application/json; charset=utf-8'):
        if isinstance(data, bytes) and 'text/html' in mime and urlsplit(self.path).path == '/rx10000/':
            data = data.replace(b'<head>', b'<head><script src="/_acceptance/observer.js"></script>', 1)
        return super().respond(status, data, mime)

    def post(self):
        if urlsplit(self.path).path == '/_acceptance/telemetry':
            size = int(self.headers.get('Content-Length', 0))
            if not 0 < size < 262144:
                raise ValueError('Invalid telemetry size')
            data = json.loads(self.rfile.read(size))
            token = data.pop('session')
            session_files = OUT.glob('*-session.json')
            case = next((json.loads(f.read_text())['case'] for f in session_files if json.loads(f.read_text())['token'] == token), 'unknown')
            with TELEMETRY_LOCK:
                previous = OUT / (case + '-telemetry.json')
                try:
                    old = json.loads(previous.read_text(encoding='utf-8')) if previous.exists() else {}
                except json.JSONDecodeError:
                    old = {}
                if any(old.get(k) != data.get(k) for k in ('labels', 'primitives', 'errors', 'commands')):
                    with (OUT / (case + '-timeline.jsonl')).open('a', encoding='utf-8') as history:
                        history.write(json.dumps({'time': time.time(), **{k:v for k,v in data.items() if k != 'nodes'}}, ensure_ascii=False) + '\n')
                previous.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            return super().respond(200, {})
        return super().post()


def verify_acceptance():
    """Compare observed original-client money and idle state with SQLite."""
    service = GameService(OUT/'wallet.sqlite3', create_registry(['roma-x-10000']))
    results = []
    for case in ('free', 'retrigger', 'battle', 'wheel', 'cash', 'max'):
        token = json.loads((OUT/(case + '-session.json')).read_text())['token']
        observed = json.loads((OUT/(case + '-telemetry.json')).read_text(encoding='utf-8'))
        wallet = service.wallet(token)
        history = service.history(token, 100)
        displayed = [re.sub('<[^>]+>', '', value).strip() for value in observed['labels']]
        money = f"{wallet['balance_minor']/10000:,.2f}"
        idle = any(value.get('IsGameIdle') is True for value in observed['primitives'].values())
        assert money in displayed, (case, 'UI/wallet mismatch', money)
        assert idle and not observed['errors'], (case, 'Client not idle or script errors', observed['errors'])
        assert history, (case, 'No settled spins')
        for row in history:
            values = row['wallet']
            assert values['before_minor'] - values['debit_minor'] + values['credit_minor'] == values['after_minor']
        results.append(dict(case=case, seed=CASES[case], balance_minor=wallet['balance_minor'],
                            spins=len(history), debit_minor=sum(row['wallet']['debit_minor'] for row in history),
                            credit_minor=sum(row['wallet']['credit_minor'] for row in history),
                            client_idle=idle, script_errors=observed['errors']))
    (OUT/'verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', help='Verify completed manual browser scenarios against their wallets')
    args = parser.parse_args()
    if args.verify:
        return verify_acceptance()
    OUT.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=OUT/'http.log', level=logging.INFO)
    registry = create_registry(['roma-x-10000'])
    game = registry.get('roma-x-10000')
    original_step = game.step
    def seeded_step(state, bet, seed, sid, _attempt=0):
        if not _attempt:
            seed = state.get('acceptance_seed', '0') if state['sid'] == '0' else '0'
        return original_step(state, bet, seed, sid, _attempt)
    game.step = seeded_step
    service = GameService(OUT/'wallet.sqlite3', registry)
    with ThreadingHTTPServer(('127.0.0.1', 18094), partial(AcceptanceHandler, directory=str(CLIENT))) as http:
        http.daemon_threads = True
        http.service, http.jili = service, Adapter(service)
        http.generated, http.service_id = True, 'roma-x-10000-acceptance'
        print('Roma acceptance: http://127.0.0.1:18094/_acceptance/start/free', flush=True)
        http.serve_forever()


if __name__ == '__main__':
    main()
