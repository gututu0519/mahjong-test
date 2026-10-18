"""Deterministic browser acceptance with separate databases and explicit weights."""
import argparse
import json
import logging
from pathlib import Path
import random
import sqlite3
import threading

from server.services.tower_run_treasure_steps_demo import build_server

SCENARIOS = {'treasure': (18102, False), 'ultra': (18103, True), 'cap': (18104, False), 'empty': (18105, False)}
RULE_SCENARIOS = {'openings': (18106, False), 'ultra-openings': (18107, True),
                  'full': (18108, False), 'treasure-cap': (18109, True)}
ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT/'clients/tower-run-treasure-steps/diagnostics/acceptance'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--rules',action='store_true')
    args=parser.parse_args()
    folder=FOLDER/'rules-v3' if args.rules else FOLDER
    scenarios=RULE_SCENARIOS if args.rules else SCENARIOS
    folder.mkdir(parents=True,exist_ok=True)
    if args.verify:
        report={}
        for name in scenarios:
            with sqlite3.connect(folder/(name+'.sqlite3')) as db:
                rows=[json.loads(r[0]) for r in db.execute('SELECT response_json FROM spins ORDER BY id')]
                pending=[json.loads(r[0])['pending'] for r in db.execute('SELECT state_json FROM game_states')]
            bets=[r for r in rows if 'ultra' in r['outcome']]
            assert bets and not any(pending),name+' unfinished'
            expected=json.loads((folder/(name+'.expected.json')).read_text())
            for bet in bets:
                assert bet['outcome']['total_minor']==expected['win_minor'],name
                paid=[r for r in rows if r['round_id']==bet['round_id'] and r['outcome'].get('confirm')]
                assert len(paid)==1 and paid[0]['wallet']['credit_minor']==expected['win_minor'],name
            assert all(r['wallet']['before_minor']-r['wallet']['debit_minor']+r['wallet']['credit_minor']==r['wallet']['after_minor'] for r in rows)
            report[name]=dict(rounds=len(bets),win_minor=expected['win_minor'],completed=True)
        (folder/'verification.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
        return
    logging.basicConfig(filename=folder/'service.log',level=logging.INFO)
    servers=[]
    try:
        for name,(port,ultra) in scenarios.items():
            config=json.loads((ROOT/'server/games/tower_run_treasure_steps/config.json').read_text())
            if name=='cap':config['symbol_weights']=[0]*9+[1,0]
            else:config.update(symbol_weights=[45,30,20,15,10,5,5,5,5,5,1],treasure_land_probability=.12,treasure_symbol_weights=[30,30,40])
            if name=='empty':config['treasure_land_probability']=0
            if 'openings' in name:
                config.update(treasure_land_probability=.05,chest_timers=[4])
            elif name=='full':
                config.update(treasure_land_probability=1,treasure_symbol_weights=[1,0,0],coin_coins=[10],coin_weights=[1])
            elif name=='treasure-cap':
                config.update(treasure_land_probability=1,treasure_symbol_weights=[0,1,1],
                              chest_coins=[50000],chest_weights=[1],chest_timers=[12])
            seed={'openings':'247','ultra-openings':'2155'}.get(name,'4')
            path=folder/(name+'.config.json');path.write_text(json.dumps(config))
            http=build_server(port,folder/(name+'.sqlite3'),path)
            game=http.service.registry.get('tower-run-treasure-steps')
            step=game.step
            game.step=lambda state,bet,entropy,sid,step=step,seed=seed:step(state,bet,seed,sid)
            result=game.generate(random.Random(seed),10,ultra,0)
            expected=dict(win_minor=result['total_minor'],bonus=result['bonus'],packets=len(result['queue']))
            (folder/(name+'.expected.json')).write_text(json.dumps(expected))
            servers.append(http)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            print(name,port,expected,flush=True)
        threading.Event().wait()
    finally:
        for http in servers:http.shutdown();http.server_close()


if __name__=='__main__':main()
