"""New rounds from public rules. Local weights are not original RTP estimates."""
import copy
import hashlib
import json
from pathlib import Path
import random

from server.core.contracts import Outcome, ServiceError


def wire(*parts):
    return ' '.join(str(p) for p in parts)


class TowerRunTreasureSteps:
    game_id = 'tower-run-treasure-steps'
    title = 'Tower Run Treasure Steps'
    version = '1.1.0'
    minor_unit = 100

    def __init__(self, config=None):
        self.config = json.loads(Path(config or Path(__file__).with_name('config.json')).read_text(encoding='utf-8'))
        self.ruleset_id = hashlib.sha256(json.dumps(dict(version=self.version, config=self.config), sort_keys=True).encode()).hexdigest()[:20]

    def initial_state(self, seed):
        return dict(sid='0', phase='ready', pending=None, progress={}, last_denom=10, ultra=False, last_grid=[i % 10 for i in range(25)])

    def public_state(self, state):
        return copy.deepcopy(state)

    def normalize_bet(self, payload):
        if not isinstance(payload, dict):
            raise ServiceError('BET_INVALID', 'Expected an object.')
        action = payload.get('action')
        if action in ('continue', 'collect', 'replay') and set(payload) == {'action'}:
            return dict(action=action)
        if set(payload) != {'denom', 'ultra'} or type(payload['denom']) is not int or payload['denom'] not in self.config['denominations'] or type(payload['ultra']) is not bool:
            raise ServiceError('BET_INVALID', 'Invalid denomination or booster.')
        return payload.copy()

    def evaluate(self, grid, multiplier=1):
        result = []
        for symbol, table in enumerate(self.config['payouts']):
            cells = [p for p, value in enumerate(grid) if value in (symbol, 10)]
            # Wilds may support multiple symbol awards, but do not invent a
            # paying symbol absent from the board.
            if symbol not in grid or len(cells) < (7 if symbol < 5 else 6):
                continue
            index = 11 - min(11, len(cells))
            result.append(dict(symbol=symbol, cells=cells, coins=table[index] * multiplier, multiplier=multiplier))
        return result

    def generate(self, rng, denom, ultra, progress):
        coins, total, cap = 15 if ultra else 10, 0, 10*self.config['maximum_win_multiplier']
        grid = rng.choices(range(11), self.config['symbol_weights'], k=25)
        initial = grid.copy()
        lines = [wire(1, 1, coins, denom, *grid, 1, 0), '2 0 0 0 0 0']
        steps = rng.randint(1, 6)
        end = progress + steps
        encounter = end >= 18
        end %= 18
        lines.append(wire(2, 2, 21, progress, steps, end, 18, int(encounter), denom))
        if encounter:
            prize = rng.choices(self.config['instant_coins'], self.config['instant_weights'])[0]
            total += prize
            lines.append(wire(2, 2, 0, prize))
        charge, stage, cascade, multiplier, bonus = 0, 0, 1, 2 if ultra else 1, False
        while total < cap:
            wins = self.evaluate(grid, multiplier)
            if not wins:
                break
            args, removed = [], set()
            awarded = 0
            for win in wins:
                if total == cap:
                    break
                paid = min(win['coins'], cap - total)
                total += paid
                awarded += 1
                args.extend([win['symbol'], len(win['cells']), *win['cells'], paid, win['multiplier']])
                removed.update(win['cells'])
            lines.append(wire(2, 2, 8, cascade, awarded, *args))
            charge += awarded
            if stage < 3:
                lines.append(wire(2, 2, 22, cascade, min(charge, 9), 9))
            lines.append(wire(2, 2, 9, cascade, len(removed), *sorted(removed)))
            next_multiplier, wilds = (2 if ultra else 1), []
            if total < cap and stage < 2 and charge >= 6:
                wilds = rng.sample(sorted(removed), min(len(removed), rng.randint(2, 8) if stage == 0 else rng.randint(1, 4)))
                next_multiplier = 5 if ultra else rng.choices(self.config['global_multipliers'], self.config['global_weights'])[0]
                stage = 2
            elif total < cap and stage < 1 and charge >= 3:
                wilds = rng.sample(sorted(removed), min(len(removed), rng.randint(1, 4)))
                stage = 1
            if wilds:
                lines.append(wire(2, 2, 23, cascade, len(wilds), *wilds))
            if next_multiplier != (2 if ultra else 1):
                lines.append(wire(2, 2, 24, cascade, next_multiplier))
            if total < cap and charge >= 9:
                stage, bonus = 3, True
            # Column-major grid, gravity toward the bottom of each column.
            for col in range(5):
                cells = list(range(col * 5, col * 5 + 5))
                remain = [grid[p] for p in cells if p not in removed]
                refill = rng.choices(range(11), self.config['symbol_weights'], k=5-len(remain))
                available = [p for p in cells if p not in wilds]
                rebuilt = refill[:len(available)-len(remain)] + remain
                for p, value in zip(available, rebuilt):
                    grid[p] = value
            # Awarded Wilds occupy the cleared coordinates in the new reveal.
            for p in wilds:
                grid[p] = 10
            cascade += 1
            lines.append(wire(2, 2, 10, cascade, 25, *grid))
            multiplier = next_multiplier
            if cascade > 500:
                raise RuntimeError('Cascade sanity limit exceeded')
        lines.append('2 5 1')
        bonus = bonus and total < cap
        queue, bonus_coins = self.generate_treasure(rng, denom, ultra, total, cap) if bonus else ([], 0)
        base_coins = total
        total += bonus_coins
        return dict(lines=lines, queue=queue, total_coins=total, total_minor=total*denom,
                    base_coins=base_coins, treasure_coins=bonus_coins,
                    progress=end, initial_grid=initial, bonus=bonus, cascades=cascade-1)

    def generate_treasure(self, rng, denom, ultra, base_coins, cap):
        """Generate sticky hold spins and the original separate opening groups.

        13 is a closed Mimic; 14 is an opened Mimic. The landing packet still
        shows the closed symbol and countdown, then event 26/27 opens it. The
        next spin shows symbol 14 and its cash value, without awarding it again.
        """
        maximum_lives = 4 if ultra else 3
        coins, lives, paid = 15 if ultra else 10, maximum_lives, 0
        queue = [['2 0 3 11 0 0', wire(2, 2, 1, lives), '2 5 1']]
        locked, batch, batch_spins, spins = {}, [], 0, 0

        def credit(value):
            nonlocal paid
            value = min(value, cap-base_coins-paid)
            paid += value
            return value

        def final_award():
            return ['2 0 3 14 0 0', wire(2, 2, 0, paid), '2 5 1']

        while lives > 0 and len(locked) < 25 and base_coins+paid < cap:
            previous_lives = lives
            lives -= 1
            spins += 1
            was_open = {p for p, item in locked.items() if item['open']}
            opened, activated, keys, reset = [], [], set(), False
            for p, item in sorted(locked.items()):
                if item['symbol'] == 13 and not item['open']:
                    item['timer'] -= 1
                    if item['timer'] == 0:
                        item['open'] = True
                        item['value'] = credit(item['value'])
                        opened.append((p, item['value']))
                        reset = True
                        if base_coins+paid == cap:
                            break
            # Land all symbols before resolving keys, including keys whose
            # target chest is later in column-major order on this same spin.
            for p in range(25):
                if base_coins+paid == cap:
                    break
                if p in locked or rng.random() >= self.config['treasure_land_probability']:
                    continue
                symbol = rng.choices([11, 12, 13], self.config['treasure_symbol_weights'])[0]
                reset = True
                if symbol == 11:
                    value = credit(rng.choices(self.config['coin_coins'], self.config['coin_weights'])[0])
                    locked[p] = dict(symbol=11, value=value, open=True, timer=0)
                elif symbol == 13:
                    locked[p] = dict(symbol=13, open=False, timer=rng.choice(self.config['chest_timers']),
                                     value=rng.choices(self.config['chest_coins'], self.config['chest_weights'])[0])
                else:
                    keys.add(p)
            for p in sorted(keys):
                if base_coins+paid == cap:
                    break
                closed = [q for q in locked if locked[q]['symbol']==13 and not locked[q]['open']]
                if closed:
                    target = rng.choice(closed)
                    item = locked[target]
                    item['open'] = True
                    item['value'] = credit(item['value'])
                    activated.append((p, target, item['value']))
            if reset:
                lives = maximum_lives
            display = [14 if p in was_open and locked[p]['symbol']==13 else locked[p]['symbol']
                       if p in locked else 12 if p in keys else -1 for p in range(25)]
            values = []
            for p, item in sorted(locked.items()):
                symbol = display[p]
                value = item['value'] if symbol in (11,14) else item['timer']
                values.extend([p, symbol, value])
            ended = lives == 0 or len(locked) == 25 or base_coins+paid == cap
            has_opening = bool(opened or activated)
            flag = 3 if has_opening else 2 if reset or ended else 1
            batch.extend([wire(3, 0, base_coins, base_coins*denom, previous_lives, 1),
                          wire(1, 1, coins, denom, *display, flag, 0),
                          '2 0 3 13 0 0', wire(2, 2, 25, len(locked), *values), '2 5 0'])
            batch_spins += 1
            if has_opening:
                groups = []
                if opened:
                    groups.append(['2 0 0 13 1 0', *[wire(2, 2, 27, p, value) for p, value in opened]])
                if activated:
                    groups.append(['2 0 0 12 1 0', *[wire(2, 2, 26, p, target, value) for p, target, value in activated]])
                for i, group in enumerate(groups):
                    batch.extend(group + [wire(2, 5, int(i==len(groups)-1))])
                queue.append(batch)
                # The client acknowledges the opening animation before the
                # next life-reset group (or a terminal cap/full-board award).
                queue.append(final_award() if ended else ['2 0 3 11 0 0', wire(2, 2, 1, batch_spins), '2 5 1'])
            elif ended:
                queue.append(batch + final_award())
            elif reset:
                queue.append(batch + ['2 0 3 11 0 0', wire(2, 2, 1, batch_spins), '2 5 1'])
            if reset or ended:
                batch, batch_spins = [], 0
            if spins > 1000:
                raise RuntimeError('Treasure sanity limit exceeded')
        return queue, paid

    def step(self, state, bet, seed, sid):
        state = copy.deepcopy(state)
        action = bet.get('action')
        pending = state['pending']
        if action:
            if not pending:
                raise ServiceError('ROUND_INVALID', 'No pending round.', 409)
            if action == 'replay':
                if pending.get('presentation_version',1) == 1 and pending['all_queue']:
                    # Preserve unfinished development rounds saved before the
                    # final hold spin and end award were packed together.
                    old=pending['all_queue']
                    if old[-1][0]=='2 0 3 14 0 0' and len(old)>1:
                        end=old.pop()
                        last=old[-1]
                        if '2 0 3 11 0 0' in last:
                            del last[last.index('2 0 3 11 0 0'):]
                        last.extend(end)
                    for packet in old:
                        for i,line in enumerate(packet):
                            if line.startswith('3 0 '):
                                data=line.split()
                                packet[i]=wire(3,0,pending['total_coins'],pending['total_minor'],*data[4:])
                    pending['presentation_version']=2
                pending['queue'] = copy.deepcopy(pending['all_queue'])
                state.update(sid=sid,phase='pending')
                return Outcome(state,dict(round_id=pending['round_id'],lines=pending['initial_lines'],next_phase='pending',replay=True),0,0)
            if action == 'collect':
                if pending['queue'] or state['phase'] != 'collect':
                    raise ServiceError('ROUND_PENDING', 'Finish the presentation first.', 409)
                amount = pending['total_minor']
                state.update(sid=sid, phase='ready', pending=None)
                return Outcome(state, dict(round_id=pending['round_id'], lines=[wire(5, pending['total_coins']), wire(6, amount)], next_phase='ready', confirm=True), 0, amount)
            if state['phase'] == 'collect':
                # A treasure room with no cash award asks for the base-game
                # summary once more before sending its collect command.
                state['sid']=sid
                return Outcome(state,dict(round_id=pending['round_id'],lines=[wire(3,0,pending['total_coins'],pending['total_minor'],0,1)],next_phase='collect'),0,0)
            if pending['queue']:
                lines = pending['queue'].pop(0)
                if not pending['queue'] and pending.get('presentation_version', 2) < 3:
                    state['phase']='collect'
            else:
                lines = [wire(3, 0, pending['total_coins'], pending['total_minor'], 0, 1)]
                state['phase'] = 'collect' if pending['total_minor'] else 'ready'
                if not pending['total_minor']:
                    lines.append('6 0')
                    state['pending'] = None
            state['sid'] = sid
            return Outcome(state, dict(round_id=pending['round_id'], lines=lines, next_phase=state['phase']), 0, 0)
        if pending:
            raise ServiceError('ROUND_PENDING', 'Finish the previous round.', 409)
        denom, ultra = bet['denom'], bet['ultra']
        result = self.generate(random.Random(str(seed)), denom, ultra, state['progress'].get(str(denom), 0))
        state['progress'][str(denom)] = result['progress']
        state.update(sid=sid, phase='pending', last_denom=denom, ultra=ultra, last_grid=result['initial_grid'],
                     pending=dict(round_id=sid, queue=result['queue'], all_queue=copy.deepcopy(result['queue']), total_coins=result['total_coins'], total_minor=result['total_minor'], initial_lines=result['lines'],presentation_version=3))
        return Outcome(state, dict(round_id=sid, lines=result['lines'], next_phase='pending',
                                   total_minor=result['total_minor'], bonus=result['bonus'], ultra=ultra, denom=denom), (15 if ultra else 10)*denom, 0)
