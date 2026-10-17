"""Seeded original-client acceptance, isolated from production port 8096."""
import argparse
import json
import logging
from pathlib import Path
import random
import sqlite3
import threading

from server.services.le_vampire_demo import build_server

SCENARIOS={
    'coffin':dict(port=18096,seed=2,mode='fs',win=79880),
    'love':dict(port=18097,seed=0,mode='fs_2',win=70200),
    'blood-gold':dict(port=18098,seed=353,mode='mod_epic',win=549720),
    'hidden':dict(port=18099,seed=0,mode='base',hidden=True),
    'max':dict(port=18100,seed=0,mode='mod_epic',cap=True,win=3_000_000),
    'free-max':dict(port=18101,seed=0,mode='fs_2',cap=True,win=3_000_000),
}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');parser.add_argument('--only',choices=list(SCENARIOS));args=parser.parse_args()
    selected={k:v for k,v in SCENARIOS.items() if not args.only or k==args.only}
    root=Path(__file__).resolve().parents[2];directory=root/'clients/le-vampire/diagnostics/acceptance'
    directory.mkdir(parents=True,exist_ok=True)
    if args.verify:
        report={}
        for name,spec in selected.items():
            with sqlite3.connect(directory/(name+'.sqlite3')) as db:
                rows=[json.loads(r[0]) for r in db.execute('SELECT response_json FROM spins ORDER BY id')]
                assert not any(json.loads(r[0])['pending'] for r in db.execute('SELECT state_json FROM game_states')),name+' pending'
            bets=[r for r in rows if not r['outcome'].get('confirm')];assert bets,name+' not played'
            for bet in bets:
                expected=json.loads((directory/(name+'.expected.json')).read_text())
                assert bet['outcome']['mode']==spec['mode'],name
                assert bet['outcome']['total_minor']==expected['win'],name
                con=[r for r in rows if r['round_id']==bet['round_id'] and r['outcome'].get('confirm')]
                assert len(con)==1 and con[0]['wallet']['credit_minor']==expected['win'],name
            for r in rows:
                w=r['wallet'];assert w['before_minor']-w['debit_minor']+w['credit_minor']==w['after_minor']
            report[name]=dict(rounds=len(bets),win_minor=expected['win'],balance_minor=rows[-1]['wallet']['after_minor'])
        (directory/'verification.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report));return
    logging.basicConfig(filename=directory/'service.log',level=logging.INFO)
    servers=[]
    try:
        for name,spec in selected.items():
            config=json.loads((root/'services/le-vampire/config/le-vampire.json').read_text())
            if spec.get('hidden'):config.update(bonus_probability=1,bonus_weights=[0,0,1])
            if spec.get('cap'):config.update(coin_weights=[0]*19+[1],special_probabilities=[0]*4)
            path=directory/(name+'.config.json');path.write_text(json.dumps(config))
            http=build_server(spec['port'],directory/(name+'.sqlite3'),path)
            game=http.service.registry.get('le-vampire');run=game.step;seed=str(spec['seed'])
            game.step=lambda state,bet,rng,sid,run=run,seed=seed:run(state,bet,seed,sid)
            events,win,spins,feature=game.generate(random.Random(seed),200,spec['mode'])
            if 'win' in spec:assert win==spec['win'],(name,win)
            expected=dict(seed=spec['seed'],win=win,spins=spins,feature=feature)
            (directory/(name+'.expected.json')).write_text(json.dumps(expected))
            servers.append(http);threading.Thread(target=http.serve_forever,daemon=True).start()
            print(name+' http://127.0.0.1:'+str(spec['port'])+' '+json.dumps(expected),flush=True)
        threading.Event().wait()
    except KeyboardInterrupt:pass
    finally:
        for http in servers:http.shutdown();http.server_close()


if __name__=='__main__':main()
