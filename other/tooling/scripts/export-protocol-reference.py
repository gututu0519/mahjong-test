"""Offline, stateful original-adapter calls for native Node regression tests."""
import base64,copy,gzip,importlib,json,tempfile,types,sqlite3
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from urllib.parse import urlencode
from py.run import build_from_directory
from py.adapters.pg.protocol import pack,field,text_field,double_field
ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'server/fixtures/protocols';DEST.mkdir(parents=True,exist_ok=True)

def encoded(value):
    if isinstance(value,bytes):return {'__bytes__':base64.b64encode(value).decode()}
    if isinstance(value,dict):return {str(k):encoded(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [encoded(v) for v in value]
    return value

def main():
    manifest=[]
    for service in sorted((ROOT/'services').iterdir()):
        if not (service/'service.json').exists() or service.name=='game-api':continue
        gid=service.name;spec=json.loads((service/'service.json').read_text())
        entry={'mahjong_client':'local_demo','buffalo_client':'buffalo_demo','olympus_client':'olympus_demo'}.get(spec['entry'],spec['entry'].replace('_client','_demo'))
        module=importlib.import_module('py.services.'+entry)
        token='reference-'+gid
        with tempfile.TemporaryDirectory() as tmp,patch('time.time',return_value=1700000000),patch('secrets.token_hex',side_effect=lambda n=32:'b'*(2*n)),patch('secrets.token_urlsafe',return_value=token),patch('uuid.uuid4',return_value=types.SimpleNamespace(hex='a'*32)):
            app=module.build_server(0,Path(tmp)/'game.db',service/'config'/f'{gid}.json')
            try:
                session=app.service.create_session();calls=[];game=app.service.registry.get(gid)
                adapter_name=next(n for n in ('pg','pp','jili','tada','hacksaw','playngo') if hasattr(app,n));adapter=getattr(app,adapter_name)
                def record(name,*args):
                    result=getattr(adapter,name)(*copy.deepcopy(args));calls.append(dict(method=name,args=encoded(args),expected=encoded(result)));return result
                if adapter_name=='pg':
                    def binary(previous='0'):
                        bet=game.normalize_bet({});salt={'mahjong-ways2':11,'captains-bounty':9,'fortune-rabbit':25,'wild-bandito':5}[gid]
                        raw=text_field(1,token)+field(2,0,1 if gid=='mahjong-ways2' else 2)+field(3,0,1)+text_field(5,previous)+text_field(12,'0_C')+double_field(21,bet['coin_minor']/100)+field(22,0,bet['level'])
                        return pack(raw,37,salt=salt)
                    if gid in ('mahjong-ways2','buffalo-win'):record('game_info',token)
                    else:record('game_info',binary(),token)
                    record('wallet',token)
                    for i in range(5):
                        state=app.service.state(token,gid)['state'];bet=game.normalize_bet({})
                        if gid=='buffalo-win':args=[urlencode(dict(atk=token,btt=2,pf=1,wk='0_C',id=state['sid'],cs=bet['coin_minor']/100,ml=bet['level'])).encode(),token]
                        else:args=[binary(state['sid'])]+([] if gid=='mahjong-ways2' else [token])
                        record('spin',*args);record('spin',*args)
                elif adapter_name=='pp':
                    symbol={'gates-of-olympus':'vs20olympgate','big-bass-bonanza':'vs10bbbonanza','sweet-bonanza-pop':'vs10swtbnz'}[gid]
                    def form(action,index):return {k:[str(v)] for k,v in dict(symbol=symbol,mgckey=token,action=action,index=index,counter=index*2,c=game.normalize_bet({})['coin_minor']/100,l=20 if gid=='gates-of-olympus' else 10,bl=0).items()}
                    record('handle',form('doInit',1))
                    for i in range(2,8):
                        state=app.service.state(token,gid)['state'];q=form('doCollect' if state['phase']=='collect' else 'doSpin',i)
                        record('handle',q);record('handle',q)
                elif adapter_name in ('jili','tada'):
                    record('login',token);record('info',token);record('handle',token,2,[],'notice')
                    adapter_module=importlib.import_module(adapter.__class__.__module__)
                    req=adapter_module.pack('SpinReq',{'bet':game.normalize_bet({})['bet_minor']/10000})
                    for i in range(3):record('handle',token,0,req,f'spin-{i}');record('handle',token,0,req,f'spin-{i}')
                    record('handle',token,4,[],'restore')
                elif adapter_name=='hacksaw':
                    record('authenticate',token)
                    for i in range(1,7):
                        state=app.service.state(token,gid)['state']
                        req=dict(sessionUuid=token,seq=i)
                        if state['pending']:req.update(continueInstructions={'action':'win_presentation_complete'},roundId=state['pending']['round_id'])
                        else:req['bets']=[dict(betAmount=str(game.config['default_bet_minor']))]
                        record('bet',req);record('bet',req)
                    record('authenticate',token)
                else:
                    record('call',token,1,'101');record('call',token,2,'104 1098')
                    for i in range(3,12):
                        state=app.service.state(token,gid)['state'];cmd='1 1 10 10 1' if state['phase']=='ready' else '4 0' if state['phase']=='collect' else '2 6'
                        record('call',token,i,cmd)
                with closing(sqlite3.connect(Path(tmp)/'game.db')) as db:
                    dump='\n'.join(db.iterdump())
                data=dict(id=gid,adapter=adapter_name,session=session,calls=calls,legacy_sql=dump,final_state=app.service.state(token,gid),final_wallet=app.service.wallet(token),final_history=app.service.history(token))
                filename=gid+'.json.gz';(DEST/filename).write_bytes(gzip.compress(json.dumps(data,separators=(',',':')).encode(),mtime=0));manifest.append(dict(id=gid,file=filename,calls=len(calls)));print(gid,len(calls))
            finally:app.server_close()
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
