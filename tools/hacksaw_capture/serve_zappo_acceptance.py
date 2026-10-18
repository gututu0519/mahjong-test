"""Seeded original-client acceptance on temporary ports and private databases."""
import argparse
import json
import logging
from pathlib import Path
import random
import sqlite3
import threading

from server.services.dr_zappo_demo import build_server

SCENARIOS = {
    'no-brainer': dict(port=18097, seed=0, mode='fs_2'),
    'hidden': dict(port=18098, seed=0, mode='base', hidden=True),
    'free-max': dict(port=18099, seed=0, mode='fs_2', cap=True),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    folder = root / 'clients/dr-zappo/diagnostics/acceptance'
    folder.mkdir(parents=True, exist_ok=True)
    if args.verify:
        report = {}
        for name, spec in SCENARIOS.items():
            with sqlite3.connect(folder / (name + '.sqlite3')) as db:
                responses = [json.loads(r[0]) for r in db.execute('SELECT response_json FROM spins ORDER BY id')]
                pending = [json.loads(r[0])['pending'] for r in db.execute('SELECT state_json FROM game_states')]
            bets = [r for r in responses if not r['outcome'].get('confirm')]
            assert bets and not any(pending), name + ' not completed'
            expected = json.loads((folder / (name + '.expected.json')).read_text(encoding='utf-8'))
            for bet in bets:
                assert bet['outcome']['mode'] == spec['mode'], name
                assert bet['outcome']['total_minor'] == expected['win'], name
                confirms = [r for r in responses if r['round_id'] == bet['round_id'] and r['outcome'].get('confirm')]
                assert len(confirms) == 1 and confirms[0]['wallet']['credit_minor'] == expected['win'], name
            for r in responses:
                w = r['wallet']
                assert w['before_minor'] - w['debit_minor'] + w['credit_minor'] == w['after_minor'], name
            report[name] = dict(rounds=len(bets), win_minor=expected['win'], balance_minor=responses[-1]['wallet']['after_minor'])
        (folder / 'verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
        return
    logging.basicConfig(filename=folder / 'service.log', level=logging.INFO)
    servers = []
    try:
        for name, spec in SCENARIOS.items():
            config = json.loads((root / 'services/dr-zappo/config/dr-zappo.json').read_text(encoding='utf-8'))
            if spec.get('hidden'):
                config.update(free_trigger_probability=1, free_scatter_weights=[0, 0, 1])
            if spec.get('cap'):
                config.update(free_eye_probability=1, additional_eye_probability=1, multiplier_probability=1,
                              multiplier_weights=[0] * 14 + [1])
            path = folder / (name + '.config.json')
            path.write_text(json.dumps(config), encoding='utf-8')
            http = build_server(spec['port'], folder / (name + '.sqlite3'), path)
            game = http.service.registry.get('dr-zappo')
            run, seed = game.step, str(spec['seed'])
            game.step = lambda state, bet, entropy, sid, run=run, seed=seed: run(state, bet, seed, sid)
            _, win, count, feature = game.generate(random.Random(seed), 200, spec['mode'])
            (folder / (name + '.expected.json')).write_text(json.dumps(dict(win=win, spins=count, feature=feature)), encoding='utf-8')
            servers.append(http)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            print(name, spec['port'], 'win_minor', win, 'spins', count, flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for http in servers:
            http.shutdown()
            http.server_close()


if __name__ == '__main__':
    main()
