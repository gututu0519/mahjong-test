"""Read the live capture, retain public assets and credential-free commands."""
import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT/'clients/tower-run-treasure-steps'
HOSTS = {'cdn.playngonetwork.com': 'cdn', 'pc-prod-eu.playngonetwork.com': 'platform'}


def packets(folder):
    """SignalR MessagePack strings contain complete CRLF-terminated commands.

    Extract only the bounded ASCII packet strings; no session header or login
    commands enter the exported evidence. Raw frames remain local.
    """
    result = []
    for frame, line in enumerate((folder/'websockets.jsonl').read_text(encoding='utf-8').splitlines()):
        row = json.loads(line)
        if row['encoding'] != 'base64':
            continue
        raw = base64.b64decode(row['data'])
        start = raw.find(b'd=')
        end = raw.find(b'\r\n\r\n', start)
        if start < 0:
            continue
        if end < 0:
            end = len(raw)
        lines = raw[start+2:end].decode('utf-8', errors='ignore').splitlines()
        if row['direction'] == 'sent':
            lines = lines[2:]
        lines = [s for s in lines if re.fullmatch(r'[0-9][0-9 .+-]*', s)]
        lines = [s for s in lines if s.split()[0] not in ('91', '101', '103', '127')]
        if lines:
            result.append(dict(frame=frame, direction=row['direction'], lines=lines))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('session', nargs='?')
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    index_file = CLIENT/'resource-index.json'
    if args.audit:
        index = json.loads(index_file.read_text(encoding='utf-8'))
        errors = [name for name, meta in index.items() if not (CLIENT/name).is_file()
                  or hashlib.sha256((CLIENT/name).read_bytes()).hexdigest() != meta['sha256']]
        print(json.dumps(dict(resources=len(index), errors=errors)))
        return bool(errors)
    sessions = json.load(urlopen('http://127.0.0.1:8090/api/sessions', timeout=15))
    sid = args.session or next(s['id'] for s in sessions if 'tower-run-treasure-steps' in s['url'])
    snapshot = json.load(urlopen('http://127.0.0.1:8090/api/sessions/'+sid, timeout=15))
    capture = ROOT/'response-capture/captures'/sid
    CLIENT.mkdir(parents=True, exist_ok=True)
    fixtures = CLIENT/'fixtures'
    fixtures.mkdir(exist_ok=True)
    index = json.loads(index_file.read_text(encoding='utf-8')) if index_file.exists() else {}
    for row in snapshot['rows']:
        if row.get('status') != 200 or not row.get('body'):
            continue
        url = urlsplit(row['url'])
        source = capture/row['body']
        target = None
        if url.hostname in HOSTS:
            target = CLIENT/HOSTS[url.hostname]/url.path.lstrip('/')
        elif url.hostname in ('released.playngonetwork.com', 'asccw.playngonetwork.com'):
            name = {'/casino/ContainerLauncher': 'launcher.html', '/configuration/prelaunchconfiguration': 'prelaunch.json',
                    '/configuration/v2': 'configuration.json', '/games/getgamebygid/towerruntreasuresteps': 'game.json',
                    '/casino/gamehelp': 'help.html'}.get(url.path)
            if name:
                target = fixtures/name
            elif url.path.startswith(('/casino/gamehelp/', '/Content/')):
                target = CLIENT/'released'/url.path.lstrip('/')
        elif row['id'] == 17 and '/games/1098/hero-desktop/' in url.path:
            target = ROOT/'demo/tower-run-cover.webp'
            shutil.copyfile(source, target)
            continue
        if target is None:
            continue
        target = target.resolve()
        if not target.is_relative_to(CLIENT.resolve()):
            raise ValueError('Invalid public asset path')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        name = target.relative_to(CLIENT.resolve()).as_posix()
        index[name] = dict(url=url._replace(query='', fragment='').geturl(), request=row['id'],
                           bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    decoded = packets(capture)
    (fixtures/'commands.json').write_text(json.dumps(decoded, indent=2), encoding='utf-8')
    summary = dict(session=sid, state=snapshot['state'], last_request=max(r['id'] for r in snapshot['rows']),
                   frames=snapshot.get('ws_count'), packets=len(decoded),
                   requests=dict(Counter(r['lines'][0].split()[0] for r in decoded if r['direction']=='sent')))
    (fixtures/'evidence-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    index_file.write_text(json.dumps(index, indent=2), encoding='utf-8')
    print(json.dumps(dict(resources=len(index), **summary)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
