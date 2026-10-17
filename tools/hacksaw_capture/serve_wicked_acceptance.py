"""Isolated original-client acceptance services; never changes port 8095.

Buy Stash N Stack or Coin Craze at the default bet: five generated free spins,
with coin expansion and a multiplier. --extended covers retriggers, Epic,
stacked multipliers and early max-win settlement. Evidence stays in diagnostics.
"""
import logging
from pathlib import Path
import argparse
import json
import sqlite3
import random
import threading
from server.services.wicked_grin_demo import build_server

SCENARIOS = {
    'stash-retrigger': dict(port=18095,seed=38,mode='fs',win=520),
    'coin-retrigger': dict(port=18096,seed=38,mode='fs_2',win=1520),
    'epic': dict(port=18097,seed=2,mode='mod_spread',win=4000),
    'stacked': dict(port=18098,seed=13,mode='mod_spread',win=16260),
    'max': dict(port=18099,seed=3,mode='mod_spread',win=2_000_000,cap_config=True),
    'collector-max': dict(port=18100,seed=18,mode='fs_2',win=2_000_000,cap_config=True),
}


def extended(directory,verify=False):
    directory = directory/'v1.1'
    directory.mkdir(parents=True,exist_ok=True)
    if verify:
        report = {}
        for name,spec in SCENARIOS.items():
            with sqlite3.connect(directory/(name+'.sqlite3')) as db:
                rows = [json.loads(row[0]) for row in db.execute('SELECT response_json FROM spins ORDER BY id')]
                assert not any(json.loads(r[0])['pending'] for r in db.execute('SELECT state_json FROM game_states')),name+' is pending'
                bets = [r for r in rows if not r['outcome'].get('confirm')]
                assert bets,name+' has not been played in the browser'
                for bet in bets:
                    assert bet['outcome']['mode']==spec['mode'],name
                    assert bet['outcome']['total_minor']==spec['win'],name
                    confirms = [r for r in rows if r['round_id']==bet['round_id'] and r['outcome'].get('confirm')]
                    assert len(confirms)==1 and confirms[0]['wallet']['credit_minor']==spec['win'],name
                for row in rows:
                    w = row['wallet']
                    assert w['before_minor']-w['debit_minor']+w['credit_minor']==w['after_minor']
                report[name] = dict(rounds=len(bets),win_minor=spec['win'],balance_minor=rows[-1]['wallet']['after_minor'])
        (directory/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
        return
    servers = []
    logging.basicConfig(filename=directory/'service.log',level=logging.INFO)
    try:
        for name,spec in SCENARIOS.items():
            config = json.loads((Path(__file__).resolve().parents[2]/'services/wicked-grin/config/wicked-grin.json').read_text(encoding='utf-8'))
            if spec.get('cap_config'):
                # Test-only weights create the documented cap naturally through
                # normal coin/multiplier rules. Production configuration is untouched.
                config['coin_weights'] = [0]*17+[1]
                config['multiplier_probability'] = .6
            path = directory/(name+'.config.json')
            path.write_text(json.dumps(config),encoding='utf-8')
            http = build_server(spec['port'],directory/(name+'.sqlite3'),path)
            game = http.service.registry.get('wicked-grin')
            original,seed = game.step,str(spec['seed'])
            game.step = lambda state,bet,rng,sid,run=original,fixed=seed: run(state,bet,fixed,sid)
            assert game.generate(random.Random(seed),200,spec['mode'])[1]==spec['win']
            servers.append(http)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            print(name+' http://127.0.0.1:'+str(spec['port'])+'/',flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for http in servers:
            http.shutdown()
            http.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--extended',action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    directory = root/'clients/wicked-grin/diagnostics/acceptance'
    directory.mkdir(parents=True,exist_ok=True)
    if args.extended:
        return extended(directory,args.verify)
    if args.verify:
        with sqlite3.connect(directory/'games.sqlite3') as db:
            rows = [json.loads(row[0]) for row in db.execute('SELECT response_json FROM spins ORDER BY id')]
            for row in rows:
                wallet = row['wallet']
                assert wallet['before_minor']-wallet['debit_minor']+wallet['credit_minor']==wallet['after_minor']
            pending = [json.loads(row[0])['pending'] for row in db.execute('SELECT state_json FROM game_states')]
            assert not any(pending), 'A browser acceptance round has not been confirmed yet'
            for mode, cost, win in [('fs',16000,4100),('fs_2',40000,5700)]:
                rounds = [r for r in rows if r['outcome'].get('mode')==mode]
                assert rounds, 'Missing browser scenario '+mode
                for row in rounds:
                    assert row['wallet']['debit_minor']==cost
                    assert row['outcome']['total_minor']==win
                    confirms = [r for r in rows if r['round_id']==row['round_id'] and r['outcome'].get('confirm')]
                    assert len(confirms)==1 and confirms[0]['wallet']['credit_minor']==win
            result = {'status':'ok','operations':len(rows),'settled_modes':['fs','fs_2'],
                      'last_balance_minor':rows[-1]['wallet']['after_minor']}
            (directory/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result))
        return
    logging.basicConfig(filename=directory/'service.log',level=logging.INFO)
    with build_server(18095,directory/'games.sqlite3') as http:
        game = http.service.registry.get('wicked-grin')
        original = game.step
        game.step = lambda state,bet,seed,sid: original(state,bet,'93',sid)
        print('Wicked Grin seed-93 acceptance: http://127.0.0.1:18095/',flush=True)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
