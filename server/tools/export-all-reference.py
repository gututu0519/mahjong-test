"""Offline reference export; no Python dependency in Node tests or services."""
import copy
import dataclasses
import gzip
import json
from pathlib import Path
from py.games.catalog import create_registry, GAMES

ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'server/fixtures/all-games'
DEST.mkdir(parents=True,exist_ok=True)

def variants(game):
    c=game.config;gid=game.game_id
    if 'costs' in c:return [dict(bet_minor=c['default_bet_minor'],mode=mode) for mode in c['costs']]
    if gid=='tower-run-treasure-steps':return [dict(denom=10,ultra=False),dict(denom=10,ultra=True)]
    if gid=='buffalo-win':return [{},dict(buy_free=True)]
    if gid=='gates-of-olympus':return [{},dict(ante=True),dict(action='buy')]
    if gid=='super-ace':return [{},dict(buy_bonus=True)]
    if gid=='roma-x-10000':return [{}]+[dict(buy=i) for i in range(2)]
    if gid=='3-billion-vaults':return [{},dict(extra=True)]+[dict(buy=i) for i in range(3)]
    if gid=='money-pot-deluxe':return [dict(extra=i) for i in range(4)]
    if gid in ('jokers-fortune-winx','fortune-gems2'):return [{},dict(extra=True)]
    return [{}]

def main():
    manifest=[]
    for gid in GAMES:
        path=ROOT/'services'/gid/'config'/f'{gid}.json'
        game=create_registry([gid],{gid:path}).get(gid)
        cases=[];normal=[]
        for vindex,payload in enumerate(variants(game)):
            initial_seed=f'{gid}:initial:{vindex}'
            state=game.initial_state(initial_seed)
            start=game.normalize_bet(payload)
            for round_index in range(16 if vindex==0 else 3):
                for step in range(4096):
                    p=copy.deepcopy(payload)
                    if state['phase']!='ready':
                        if gid=='tower-run-treasure-steps':p={'action':'collect' if state['phase']=='collect' else 'continue'}
                        elif 'costs' in game.config:p={'action':'confirm','round_id':state['pending']['round_id']}
                        elif gid in ('gates-of-olympus','sweet-bonanza-pop','big-bass-bonanza'):
                            p.update(action='collect' if state['phase']=='collect' else 'spin',request_index=len(cases)+1)
                        else:p.pop('buy_free',None)
                    elif gid in ('gates-of-olympus','sweet-bonanza-pop','big-bass-bonanza'):p['request_index']=len(cases)+1
                    bet=game.normalize_bet(p)
                    seed=f'{gid}:round:{vindex}:{round_index}:step:{step}'
                    sid=str(len(cases)+1)
                    before=copy.deepcopy(state)
                    outcome=game.step(state,bet,seed,sid)
                    cases.append(dict(payload=p,bet=bet,state=before,seed=seed,sid=sid,expected=dataclasses.asdict(outcome)))
                    state=outcome.state
                    if state['phase']=='ready':break
                else:raise RuntimeError(f'{gid} unfinished reference round')
            normal.append(dict(payload=payload,bet=start,initial_seed=initial_seed,initial=game.initial_state(initial_seed)))
        errors=[]
        for payload in [None,[],{'unsupported':True},{'bet_minor':True},{'coin_minor':True}]:
            try:game.normalize_bet(payload)
            except Exception as exc:errors.append(dict(payload=payload,code=getattr(exc,'code',type(exc).__name__)))
        data=dict(game_id=gid,factory=GAMES[gid]['factory'],config_path=str(path.relative_to(ROOT)).replace('\\','/'),ruleset_id=game.ruleset_id,initial=normal,errors=errors,cases=cases)
        raw=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
        filename=f'{gid}.json.gz'
        (DEST/filename).write_bytes(gzip.compress(raw,mtime=0))
        manifest.append(dict(id=gid,file=filename,steps=len(cases),variants=len(normal)))
        print(gid,len(cases),len(raw))
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
