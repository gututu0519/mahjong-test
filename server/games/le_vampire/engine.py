"""Le Vampire mechanics from original help, captured events and client readers.

Probability weights are local configuration. Monetary values are integer cents;
special-symbol values use the original tenths-of-a-base-bet representation.
"""
import hashlib
import json
import random
from pathlib import Path

from server.games.wicked_grin.engine import WickedGrin, action

COINS = [2, 4, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 200, 300, 400, 500, 1000, 1500, 2500, 5000]
PAYING = tuple(range(1,9)) + tuple(range(15,19))


def encode_grid(grid):
    return '.-' + ''.join(chr(int(v)+40) for v in grid)


def decode_grid(value):
    if not isinstance(value,str) or len(value)!=32 or value[:2]!='.-':
        raise ValueError('Expected a six by five grid')
    return [ord(c)-40 for c in value[2:]]


def mask(positions):
    positions=set(positions)
    return ''.join('1' if p in positions else '0' for p in range(30))


def order(p):
    return p%6,p//6


def adjacent(p,q):
    return max(abs(p%6-q%6),abs(p//6-q//6))<=1 and p!=q


class LeVampire(WickedGrin):
    game_id='le-vampire'
    title='Le Vampire'
    version='1.0.0'

    def __init__(self,config=None):
        self.config=json.loads(Path(config or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        self.ruleset_id=hashlib.sha256(json.dumps({'engine':self.version,'config':self.config},sort_keys=True).encode()).hexdigest()[:20]

    def clusters(self,grid):
        """Wilds may participate in clusters of more than one paying symbol."""
        found=[]
        for symbol in PAYING:
            unseen={i for i,v in enumerate(grid) if v in (0,symbol)}
            while unseen:
                todo=[min(unseen,key=order)];cells=set(todo);unseen.difference_update(cells)
                while todo:
                    p=todo.pop()
                    near={q for q in (p-6,p+6,p-1,p+1) if 0<=q<30 and abs(q%6-p%6)+abs(q//6-p//6)==1}
                    more=near & unseen
                    unseen.difference_update(more);cells.update(more);todo.extend(more)
                if len(cells)>=5 and any(grid[p]==symbol for p in cells):found.append((symbol,cells))
        return sorted(found,key=lambda item:(min(map(order,item[1])),item[0]))

    def payout(self,symbol,count,bet):
        tier=0 if count==5 else 1 if count<8 else 2 if count<10 else 3 if count<12 else 4 if count<14 else 5
        return bet*self.config['payouts'][str(symbol)][tier]//5

    def evaluate(self,grid,bet):
        return [action('gridwin',symbol=str(s),count=str(len(cells)),mask=mask(cells),
                       winAmount=str(self.payout(s,len(cells),bet))) for s,cells in self.clusters(grid)]

    def resolve_special(self,grid,gold,blood,rng,bet,minimum,limit):
        """Resolve clovers, local bags and global pots, including repeat reveals.

        Returns actions and payout; caller owns the persistent highlight sets.
        Values of activated collectors survive reveals and can be multiplied.
        """
        grid=list(grid);area=set(gold)|set(blood);values={};used=set();actions=[]
        cfg=self.config

        def reveal(cells,local=False):
            for p in sorted(cells,key=order):
                values.pop(p,None);used.discard(p)
                pick=rng.random()
                weights=cfg['special_probabilities']
                if pick<weights[0]:grid[p]=41
                elif pick<sum(weights[:2]):grid[p]=42
                elif pick<sum(weights[:3]):grid[p]=44
                elif pick<sum(weights):grid[p]=43
                else:
                    floor=max(minimum,50 if p in blood else 0)
                    indices=[i for i,v in enumerate(COINS) if v>=floor]
                    i=rng.choices(indices,weights=[cfg['coin_weights'][i] for i in indices])[0]
                    grid[p]=19+i;values[p]=COINS[i]
            actions.append(action('localReplace' if local else 'replace',g=encode_grid(grid),
                                  goldMask=mask(set(cells)-set(blood)),bloodMask=mask(set(cells)&set(blood))))

        if not area:return [],0
        reveal(area)
        for cycle in range(1000):
            # Left-to-right columns, top-to-bottom within each column, as captured.
            clovers=sorted((p for p in area if grid[p] in (41,42) and p not in used),key=order)
            for p in clovers:
                hits=sorted((q for q in values if q!=p and (grid[p]==42 or adjacent(p,q))),key=order)
                if not hits:continue
                mult=rng.choices([2,3,4,5,10,20],weights=cfg['multiplier_weights'])[0]
                for q in hits:values[q]*=mult
                used.add(p)
                actions.append(action('globalMult' if grid[p]==42 else 'mult',p=str(p),m=str(mult),
                                      hits=list(map(str,hits)),results=[str(values[q]) for q in hits]))
            # A cap ends the whole feature immediately, including deferred values.
            if bet*sum(values.values())//10>=limit:break
            bags=sorted((p for p in area if grid[p]==44),key=order)
            pots=sorted((p for p in area if grid[p]==43),key=order)
            candidates=bags or pots
            candidate=None
            for p in candidates:
                hits={q for q in values if q!=p and (grid[p]==43 or adjacent(p,q))}
                if hits:candidate=(p,hits);break
            if candidate is None:
                # A bag with no adjacent prize remains inert; global pots can act.
                for p in pots:
                    hits=set(values)-{p}
                    if hits:candidate=(p,hits);break
            if candidate is None:break
            p,hits=candidate;local=grid[p]==44
            collected=sum(values[q] for q in hits)
            # Spent clovers in the covered region are replaced as well. Activated
            # collectors remain and may be collected again by another collector.
            refill={q for q in hits if grid[q] not in (45,46)}
            refill.update(q for q in used if q!=p and (not local or adjacent(p,q)))
            actions.append(action('localCollect' if local else 'collect',p=str(p),w=str(collected),
                                  h=mask(hits),replaceMask=mask(refill)))
            grid[p]=46 if local else 45;values[p]=collected
            if refill:reveal(refill,local)
        else:raise RuntimeError('Special-symbol chain exceeded sanity limit')
        win=min(bet*sum(values.values())//10,limit)
        actions.append(action('cashWin',w=str(win),h=mask(values)))
        return actions,win

    def generate(self,rng,amount,mode):
        events=[];total=0;cap=amount*self.config['maximum_win_multiplier']
        gold=set();blood=set();upgraded=set();pending_reset=None;guarantee=None
        awarded=0

        def emit(kind,data,win=0):
            nonlocal total
            win=min(win,cap-total);total+=win
            events.append(dict(et=2,etn=kind,en='0',ba='0',bc='0',wa=str(win),wc='0',awa=str(total),awc='0',c=data))

        def play(game_mode,forced=None):
            nonlocal pending_reset,guarantee,awarded
            prefix='' if game_mode=='base' else game_mode+'_'
            reelset=(forced if forced in ('mod_rainbow','mod_epic') else 'default') if game_mode=='base' else ('fs2_high' if game_mode=='fs_2' else 'epic' if game_mode=='epic' else 'fs_high')
            reels=self.config['reels'][reelset]
            stops=[rng.randrange(len(reel)) for reel in reels]
            grid=[int(reels[c][(stops[c]+r)%len(reels[c])]) for r in range(5) for c in range(6)]
            grid=[v+10 if v in upgraded else v for v in grid]
            special=None;scatters=0
            if forced in ('fs','fs_2'):scatters=3 if forced=='fs' else 4
            elif forced=='mod_epic':special=14
            elif forced=='mod_rainbow':special=14 if rng.random()<self.config['epic_probability'] else 13
            elif guarantee is not None:special=guarantee;guarantee=None
            elif game_mode=='epic':special=14 if rng.random()<self.config['epic_probability'] else 13
            elif game_mode=='base' and rng.random()<self.config['bonus_probability']*(5 if mode=='mod_bonus' else 1):
                scatters=rng.choices([3,4,5],weights=self.config['bonus_weights'])[0]
            elif rng.random()<self.config['rainbow_probability']:
                special=14 if rng.random()<self.config['epic_probability'] else 13
            if scatters:
                for p in rng.sample(range(30),scatters):grid[p]=12
            elif special:grid[rng.randrange(30)]=special
            extras=0
            for cascade in range(1000):
                data={'reelSet':reelset,'grid':encode_grid(grid)}
                if cascade==0:data['stops']=list(map(str,stops))
                actions=[];win=0
                if cascade==0 and pending_reset:
                    actions.append(action(pending_reset));pending_reset=None
                clusters=self.clusters(grid);removed=set()
                for symbol,cells in clusters:
                    effective=symbol+10 if symbol in upgraded else symbol
                    paid=min(self.payout(effective,len(cells),amount),cap-total-win);win+=paid
                    actions.append(action('gridwin',symbol=str(effective),count=str(len(cells)),mask=mask(cells),winAmount=str(paid)))
                    if effective>=15:blood.update(cells);gold.difference_update(cells)
                    else:gold.update(cells-set(blood))
                    removed.update(i for i,v in enumerate(grid) if v==symbol)
                    removed.update(p for p in cells if grid[p]==0)
                    if game_mode!='base' and 5<=symbol<=8 and symbol not in upgraded:
                        upgraded.add(symbol);extras+=2;awarded+=2
                        actions.append(action('highUpgrade',i=str(symbol),s='2'))
                        if len(upgraded)==4:
                            guarantee=14 if game_mode=='epic' else (14 if rng.random()<self.config['epic_probability'] else 13)
                            actions.append(action('allHighsUpgraded'))
                if removed:actions.append(action('remove',mask=mask(removed)))
                if actions:data['actions']=actions
                emit(prefix+('reveal' if cascade==0 else 'collapse'),data,win)
                if total>=cap:return 0,None,extras
                if not clusters:break
                for c in range(6):
                    kept=[grid[r*6+c] for r in range(5) if r*6+c not in removed]
                    new=[int(rng.choice(reels[c])) for _ in range(5-len(kept))]+kept
                    for r,v in enumerate(new):grid[r*6+c]=v+10 if v in upgraded else v
            else:raise RuntimeError('Cascade exceeded sanity limit')
            if game_mode=='base' and scatters:
                fs='fs' if scatters==3 else 'fs_2' if scatters==4 else 'epic'
                positions=[p for p,v in enumerate(grid) if v==12]
                data.setdefault('actions',[]).extend([action('gridwin',symbol='12',count=str(len(positions)),mask=mask(positions),winAmount='0'),
                                                     action('bonusfeaturewon',bfw=fs,bfc='10')])
                return 10,fs,extras
            p=next((p for p,v in enumerate(grid) if v in (13,14)),None)
            if p is not None:
                is_epic=grid[p]==14
                raining=is_epic and rng.random()<self.config['blood_rain_probability']
                original_gold,original_blood=set(gold),set(blood)
                active_blood=set(range(30)) if raining else set(blood)
                active_gold=(set(range(30))-active_blood) if is_epic else set(gold)
                data.setdefault('actions',[]).append(action('activator',p=str(p),**({'blood':True} if raining else {})))
                minimum=10 if game_mode=='epic' or mode in ('mod_rainbow','mod_epic') else 0
                special_actions,cash=self.resolve_special(grid,active_gold,active_blood,rng,amount,minimum,cap-total)
                data['actions'].extend(special_actions)
                total_before=total;events[-1]['wa']=str(int(events[-1]['wa'])+cash)
                # emit already added the cluster win; the special resolution is
                # attached to its final no-win event, like the original server.
                add_cash(cash)
                events[-1]['awa']=str(total_before+cash)
                if game_mode=='fs':gold.clear();blood.clear();pending_reset='clearHighlights'
                elif game_mode in ('fs_2','epic'):
                    gold.clear();gold.update(original_gold);blood.clear();blood.update(original_blood)
                    if is_epic:pending_reset='highlightReset'
                else:gold.clear();blood.clear()
            return 0,None,extras

        def add_cash(win):
            nonlocal total
            total+=win

        count,feature,_=play('base',mode if mode in ('fs','fs_2','mod_rainbow','mod_epic') else None)
        awarded+=count
        if count and total<cap:
            gold.clear();blood.clear();upgraded.clear();pending_reset=None
            emit('feature_enter',{'bonusFeatureWon':feature,'bonusFeatureCount':str(count)})
            remaining=count
            while remaining and total<cap:
                remaining-=1
                _,_,extra=play(feature)
                remaining+=extra
            if total<cap:emit('feature_exit',{})
        if total>=cap:emit('max_win_reached',{})
        return events,total,awarded,feature
