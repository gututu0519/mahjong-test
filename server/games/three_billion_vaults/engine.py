"""3 Billion Vaults local outcome generator. Frequencies are configurable, not original RTP."""
import copy
import hashlib
import json
import random
from pathlib import Path
from server.core.contracts import Outcome, ServiceError


def evaluate(columns, wilds, bet, table):
    awards, total = [], 0
    wilds = set(wilds)
    for symbol in range(8):
        ways, count = 1, 0
        for col in range(5):
            hits = sum(value == symbol or col*3+row in wilds for row, value in enumerate(columns[col]))
            if not hits:
                break
            ways *= hits
            count += 1
        win = bet * table[symbol][count] * ways // 10
        if win:
            awards.append(dict(Symbol=symbol, Count=count, LineNum=ways, Win=win/10000))
            total += win
    return awards, total


class ThreeBillionVaults:
    game_id, title, version, minor_unit = '3-billion-vaults', '3 Billion Vaults', '1.0.0', 10000

    def __init__(self, config_path=None):
        self.config = json.loads(Path(config_path or Path(__file__).with_name('config.json')).read_text())
        c = self.config
        if len(c['symbol_weights']) != 8 or any(type(v) is not int or v <= 0 for v in c['symbol_weights']):
            raise ValueError('Invalid symbol weights')
        if len(c['paytable_tenths']) != 8 or any(len(r)!=6 or any(type(v) is not int or v<0 for v in r) for r in c['paytable_tenths']):
            raise ValueError('Invalid paytable')
        if not c['bets_minor'] or any(type(v) is not int or v<=0 or v%10 for v in c['bets_minor']):
            raise ValueError('Invalid bet levels')
        if any(not 0<=c[k]<=1 for k in ('wild_chance','feature_chance','heist_chance')):
            raise ValueError('Invalid frequency')
        if len(c['buy_multipliers'])!=3 or any(v<=0 for v in c['buy_multipliers']) or c['extra_multiplier']!=1.5:
            raise ValueError('Invalid prices')
        if type(c['max_win_multiple']) is not int or c['max_win_multiple'] <= 0:
            raise ValueError('Invalid win limit')
        self.ruleset_id = self.version+':'+hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:16]

    def initial_state(self, seed):
        return dict(sid='0',round_id='0',phase='ready',ruleset_id=self.ruleset_id,last_event=None,last_bet_minor=1000,wilds={})

    def public_state(self, state):
        return copy.deepcopy(state)

    def normalize_bet(self, payload):
        if not isinstance(payload,dict) or set(payload)-{'bet_minor','extra','buy'}:
            raise ServiceError('BET_INVALID','Invalid play fields.')
        amount, extra, buy = payload.get('bet_minor',1000),payload.get('extra',False),payload.get('buy')
        if type(amount) is not int or amount not in self.config['bets_minor'] or type(extra) is not bool or (buy is not None and (type(buy) is not int or buy not in range(3) or extra)):
            raise ServiceError('BET_INVALID','Invalid play selection.')
        return dict(bet_minor=amount,extra=extra,buy=buy)

    def step(self, state, bet, seed, sid, _attempt=0):
        c, rng = self.config, random.Random(seed)
        amount, extra, buy = bet['bet_minor'],bet['extra'],bet.get('buy')
        saved = copy.deepcopy(state['wilds'])
        moved = [p-1 for p in saved.get(str(amount),[]) if p%3]
        def plate():
            cols = [rng.choices(range(8),c['symbol_weights'],k=3) for _ in range(5)]
            for col in cols:
                if rng.random()<.25: col[:] = [col[0]]*3
            return cols
        def record(cols, wilds, new, **fields):
            awards,total=evaluate(cols,wilds,amount,c['paytable_tenths'])
            return dict(PlateSymbol=[dict(Column=col) for col in cols],NowWildPos=wilds,NewWildPos=new,
                        RedEnvelopePos=[],AwardDataVec=awards,FGRedCoins=[],RoundWin=total/10000,
                        AwardTypeFlag=int(bool(total)),WildSymbol=10,**fields)
        cols=plate()
        new=sorted(rng.sample([p for p in range(6,15) if p not in moved], min(rng.randint(1,3),9-len(moved)))) if rng.random()<c['wild_chance'] else []
        wilds=sorted(set(moved+new));saved[str(amount)]=wilds
        first=record(cols,wilds,new)
        # Cosmetic diamond arrivals and the feature draw are separate, as in the rules.
        if rng.random()<.35:
            pos=rng.randrange(15)
            if pos not in wilds:
                cols[pos//3][pos%3]=rng.choice([14,15,16]);first=record(cols,wilds,new)
        if rng.random()<c['heist_chance']:
            left,right=rng.randrange(3),12+rng.randrange(3)
            symbol=rng.randrange(8);cols[0][left]=cols[4][right%3]=symbol
            first=record(cols,wilds,new);cash=int(amount*rng.choice([3.8,8.8,18.8,38.8,88.8,188.8,388.8,888.8]))
            first.update(RedEnvelopePos=[left,right],RedEnvelopeWin=cash/10000,RoundWin=(round(first['RoundWin']*10000)+cash)/10000,AwardTypeFlag=first['AwardTypeFlag']|128)
        queue=[first]
        game_type = [1,2,4][buy] if buy is not None else rng.choice([1,2,3,4,5,6,7]) if rng.random()<c['feature_chance']*(1.5 if extra else 1) else 0
        def jackpot():
            tier=rng.choices(range(4),[80,16,3,1])[0];upgrade=rng.random()<.1
            serial=([24,24,24] if upgrade else [])+[20+tier]*3
            prize=amount*[15,30,100,1000,5000][tier+int(upgrade)]
            return dict(SymbolSerial=serial,Win=prize/10000,HitSymbol=20+tier,JPType=tier+int(upgrade),IsUpgraded=upgrade)
        free_total=0
        if game_type:
            colors={1:16,2:32,3:64,4:48,5:80,6:96,7:112}[game_type]
            available=[p for p in range(15) if p not in wilds and p not in first['RedEnvelopePos']]
            for symbol,bit in [(14,16),(15,32),(16,64)]:
                if colors&bit and available:
                    pos=rng.choice(available);available.remove(pos);cols[pos//3][pos%3]=symbol
            awards,line=evaluate(cols,wilds,amount,c['paytable_tenths'])
            first.update(AwardDataVec=awards,RoundWin=(line+round(first.get('RedEnvelopeWin',0)*10000))/10000,AwardTypeFlag=(first['AwardTypeFlag']&~1)|int(bool(line)))
        if game_type==3:
            jp=jackpot();first.update(JPPlate=jp,AwardTypeFlag=first['AwardTypeFlag']|64|256,RoundWin=(round(first['RoundWin']*10000)+round(jp['Win']*10000))/10000)
        elif game_type:
            colors={1:16,2:32,3:64,4:48,5:80,6:96,7:112}[game_type]
            first.update(GameType=game_type,FreeRemainRound=6,FreeTotalRound=6,AwardTypeFlag=first['AwardTypeFlag']|2|colors)
            rank=2 if game_type in (4,7) else 1 if game_type in (2,6) else 0
            total_rounds,now=6,0
            while now<total_rounds:
                now+=1;cols=plate();wilds=sorted(rng.sample(range(3,15),rng.randint(3+rank*2,[6,8,12][rank])))
                r=record(cols,wilds,wilds,GameType=game_type,FreeNowRound=now,FreeTotalRound=total_rounds,FreeRemainRound=total_rounds-now)
                r['WildSymbol']=11+rank;r['AwardTypeFlag']|=4
                for _ in range(rng.randrange(3)):
                    pos=rng.randrange(15)
                    if any(v['Pos']==pos for v in r['FGRedCoins']):continue
                    if rng.random()<.12 and total_rounds<30:
                        cols[pos//3][pos%3]=19;total_rounds+=1
                        r['FGRedCoins'].append(dict(Pos=pos,AddRound=1));r['AwardTypeFlag']|=1024
                    else:
                        cols[pos//3][pos%3]=18;cash=amount*rng.choice([5,10,15])//10
                        r['FGRedCoins'].append(dict(Pos=pos,Win=cash/10000))
                awards,line=evaluate(cols,wilds,amount,c['paytable_tenths']);cash=sum(round(v.get('Win',0)*10000) for v in r['FGRedCoins'])
                r['AwardDataVec']=[dict(Symbol=-98,Count=5,Win=v['Win']) for v in r['FGRedCoins'] if 'Win' in v]+awards
                r['RoundWin']=(line+cash)/10000;r['AwardTypeFlag']=(r['AwardTypeFlag']&~1)|int(bool(line))|(64 if r['FGRedCoins'] else 0)
                if game_type in (3,5,6,7) and rng.random()<.08:
                    jp=jackpot();r['JPPlate']=jp
                    r['AwardTypeFlag']|=64|256;r['RoundWin']=(round(r['RoundWin']*10000)+round(jp['Win']*10000))/10000
                    if not r['FGRedCoins']:
                        pos=next(p for p in range(15) if p not in wilds)
                        cols[pos//3][pos%3]=16
                        awards,line=evaluate(cols,wilds,amount,c['paytable_tenths'])
                        r['AwardDataVec']=awards;r['RoundWin']=(line+round(jp['Win']*10000))/10000
                        r['AwardTypeFlag']=(r['AwardTypeFlag']&~1)|int(bool(line))
                r.update(FreeTotalRound=total_rounds,FreeRemainRound=total_rounds-now)
                if now==total_rounds:r['AwardTypeFlag']|=8
                free_total+=round(r['RoundWin']*10000);queue.append(r)
        total=sum(round(r['RoundWin']*10000) for r in queue)
        if total>amount*c['max_win_multiple']:
            # Retry the entire draw; never silently truncate a displayed award.
            if _attempt >= 99:
                raise ServiceError('GENERATION_LIMIT','Configured maximum exceeded.',503)
            return self.step(state,bet,str(seed)+':limit',sid,_attempt+1)
        last=dict(WildRecordVec=[dict(Bet=b/10000,Pos=saved.get(str(b),[])) for b in c['bets_minor']])
        spin=dict(RoundQueue=queue,TotalWin=total/10000,FreeTotalWin=free_total/10000,LastInfo=last,IsBuy=buy is not None)
        event=dict(round_id=sid,bet_minor=amount,extra=extra,buy=buy,spin=spin,total_minor=total)
        new_state=dict(sid=sid,round_id=sid,phase='ready',ruleset_id=self.ruleset_id,last_event=event,last_bet_minor=amount,wilds=saved)
        debit=round(amount*(c['buy_multipliers'][buy] if buy is not None else c['extra_multiplier'] if extra else 1))
        return Outcome(new_state,event,debit,total)
