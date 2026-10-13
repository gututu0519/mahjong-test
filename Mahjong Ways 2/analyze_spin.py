"""Offline Spin rule audit. Reads decoded captures; never submits a Spin.

Usage from repository root:
  python "Mahjong Ways 2/analyze_spin.py" diagnostics/spin-decoded-all.json --output "Mahjong Ways 2/fixtures/spin-rule-evidence.json"
Input is private diagnostic data. Output contains counts and capture row numbers only.
"""
import argparse
import json
import math
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from spin_protocol import decode_request, fields

# GameConstant.PayOutData in assets/main/index.03e77.js, not fitted to outcomes.
PAYTABLE = {
    2: {3: 10, 4: 25, 5: 50}, 3: {3: 8, 4: 20, 5: 40},
    4: {3: 6, 4: 15, 5: 30}, 5: {3: 5, 4: 10, 5: 15},
    6: {3: 3, 4: 5, 5: 12}, 7: {3: 3, 4: 5, 5: 12},
    8: {3: 2, 4: 4, 5: 10}, 9: {3: 1, 4: 3, 5: 6},
    10: {3: 1, 4: 3, 5: 6},
}
VISIBLE = [list(range(1, 5)), list(range(8, 13)), list(range(15, 20)),
           list(range(22, 27)), list(range(29, 33))]


def evaluate_board(original_reels, coin_size, bet_level, multiplier):
    """Compute awards from a supplied board, without response wp/lw/rwsp/snww.

    This is a deterministic rule evaluator, not a random reel generator.
    Rounding beyond the captured bet sizes has not been verified.
    """
    if len(original_reels) != 35 or any(x not in range(11) for x in original_reels):
        raise ValueError('Expected 35 symbol IDs in 0..10')
    result = dict(wp={}, snww={}, rwsp={}, lw={})
    unit = Decimal(str(coin_size)) * Decimal(str(bet_level))
    for symbol, payouts in PAYTABLE.items():
        positions, counts = [], []
        for column in VISIBLE:
            hits = [p for p in column if original_reels[p] in (0, symbol)]
            if not hits:
                break
            positions.extend(hits)
            counts.append(len(hits))
        if len(counts) < 3:
            continue
        key, rate, ways = str(symbol), payouts[len(counts)], math.prod(counts)
        result['wp'][key] = positions
        result['snww'][key] = ways
        result['rwsp'][key] = rate
        result['lw'][key] = float(unit * rate * ways)
    result['tw'] = float(sum((Decimal(str(v)) for v in result['lw'].values()), Decimal(0))
                         * Decimal(str(multiplier)))
    return result


def audit(rows):
    valid = [r for r in rows if 'transaction' in r and 'wallet' in r]
    checks, observations, seen_payouts = defaultdict(list), [], Counter()
    states, groups, bet_settings = Counter(), defaultdict(list), Counter()
    previous, counts, combo = None, Counter(), 0
    eq = lambda a, b: math.isclose(a, b, abs_tol=1e-7, rel_tol=1e-9)
    for row in valid:
        t, w, rid = row['transaction'], row['wallet'], row['id']
        request = decode_request(bytes(row['request']))

        def check(name, passed):
            checks[name].append((rid, bool(passed)))

        states[f"{t['st']}->{t['nst']}"] += 1
        groups[t['psid']].append(t)
        bet_settings[(request.get('btt'), t['cs'], t['ml'])] += 1
        predicted = evaluate_board(t['orl'], t['cs'], t['ml'], t['wm'])
        check('board_winning_positions', predicted['wp'] == (t['wp'] or {}))
        check('board_ways', predicted['snww'] == (t['snww'] or {}))
        check('client_paytable', predicted['rwsp'] == (json.loads(t['rwsp']) if t['rwsp'] else {}))
        check('board_base_awards', predicted['lw'] == (t['lw'] or {}))
        check('board_total_award', eq(predicted['tw'], t['tw']))
        for key, positions in predicted['wp'].items():
            seen_payouts[(int(key), len({p // 7 for p in positions}))] += 1
        check('base_stake', eq(t['tbb'], t['cs'] * t['ml'] * 20))
        check('charged_only_on_paid_start', eq(t['tb'], t['tbb'] if t['st'] == 1 else 0))
        check('wallet_debit', eq(w['blab'], w['blb'] - t['tb']))
        check('wallet_award', eq(w['bl'], w['blab'] + t['tw']))
        check('step_net_profit', eq(t['np'], t['tw'] - t['tb']))
        check('current_total_win', eq(t['ctw'], t['tw']))
        check('multiplier_schedule', t['wm'] == [1, 2, 3, 5][t['mi']] * (2 if t['st'] in (21, 22) else 1))
        wins = {p for positions in predicted['wp'].values() for p in positions}
        golden = set((t['ssb'] or {}).values())
        converted = wins & golden
        check('remove_except_golden', set(t['ptbr'] or []) == wins - golden)
        check('golden_to_wild', t['rl'] == [0 if i in converted else v for i, v in enumerate(t['orl'])])
        check('golden_after', (t['ss'] or {}) == {k: p for k, p in (t['ssb'] or {}).items() if p not in converted})
        check('scatter_visible_only', t['sc'] == sum(t['orl'][p] == 1 for c in VISIBLE for p in c))
        if t['st'] == 1:
            counts, combo = Counter(), 0
            check('parent_id_paid_start', t['sid'] == t['psid'])
            check('initial_award', eq(t['aw'], t['tw']))
        else:
            counts[str(t['st'])] += 1
        if t['st'] in (1, 21):
            combo = 0
        combo = combo + 1 if t['tw'] else 0
        check('feature_state_counts', (t['fstc'] or {}) == dict(counts))
        check('combo_count', t['cwc'] == combo)
        check('parent_combo_count', t['pcwc'] == (1 if t['st'] == 1 and t['tw'] else 0))
        ratio = t['tw'] / t['tbb']
        # Captured GameInfo/Get wt = mw:3, bw:5, mgw:15, smgw:35.
        # gwt classifies the current payout; the animation uses ssaw at chain end.
        gwt = 4 if ratio >= 35 else 3 if ratio >= 15 else 2 if ratio >= 5 else 1 if ratio >= 3 else -1
        check('captured_threshold_gwt', t['gwt'] == gwt)
        free = t['st'] in (21, 22)
        next_state = ((22 if free else 4) if t['tw'] else
                      ((21 if t['fs']['s'] > 0 else 1) if free else
                       (21 if t['sc'] >= 3 else 1)))
        check('next_state_from_outcome', t['nst'] == next_state)
        if previous:
            p = previous['transaction']
            check('request_previous_or_reset', request.get('id') in (p['sid'], '0'))
            if request.get('id') == '0':
                observations.append({'capture': rid, 'event': 'request_id_reset'})
            check('state_continuity', t['st'] == p['nst'])
            check('multiplier_index', t['mi'] == (0 if t['st'] in (1, 21) else min(p['mi'] + 1, 3)))
            if t['psid'] == p['psid']:
                check('round_award_accumulation', eq(t['aw'], p['aw'] + t['tw']))
                check('single_spin_award_accumulation', eq(t['ssaw'], t['tw'] if t['st'] == 21 else p['ssaw'] + t['tw']))
                if t['fs'] and p['fs']:
                    fs, old = t['fs'], p['fs']
                    check('free_remaining', fs['s'] == old['s'] - int(t['st'] == 21) + fs['nosa'])
                    check('free_total', fs['ts'] == old['ts'] + fs['nosa'])
                    check('free_award', eq(fs['aw'], old['aw'] + t['tw']))
            if t['rs']:
                check('cascade_parent_continuity', t['psid'] == p['psid'])
                gone = p['ptbr'] or []
                board = []
                for col in range(5):
                    board.extend(t['rs']['rns'][col])
                    board.extend(v for i, v in enumerate(p['rl'][col * 7:(col + 1) * 7]) if col * 7 + i not in gone)
                check('cascade_reconstructed_board', board == t['orl'])
                moves = {k: {1: pos, 2: pos + sum(x > pos and x // 7 == pos // 7 for x in gone)}
                         for k, pos in (p['ss'] or {}).items()}
                new = {col * 7 + i for col, indices in enumerate(t['rs']['rnss']) for i in indices}
                check('new_golden_positions', set((t['ssb'] or {}).values()) == {v[2] for v in moves.values()} | new)
                decoded = {k: {n: v for n, wire, v in fields(bytes(value[str(i)] for i in range(len(value))))}
                           for k, value in (t['rs']['sspt'] or {}).items()}
                check('golden_position_transform', decoded == {k: v for k, v in moves.items() if v[1] != v[2]})
        if t['fs'] and t['fs']['nosa']:
            observations.append({'capture': rid, 'event': 'free_steps_awarded',
                                 'st': t['st'], 'nst': t['nst'], 'sc': t['sc'], 'fs': t['fs']})
        previous = row
    return {
        'input_rows': len(rows), 'decoded_rows': len(valid),
        'unreadable_rows': [{'capture': r['id']} for r in rows if 'transaction' not in r],
        'complete_paid_rounds': sum(any(t['st'] == 1 for t in g) and any(t['nst'] == 1 for t in g) for g in groups.values()),
        'states': dict(states),
        'bet_settings': [{'btt': b, 'cs': c, 'ml': m, 'responses': n} for (b, c, m), n in bet_settings.items()],
        'checks': {k: {'passed': sum(v for _, v in values), 'total': len(values),
                       'failed_capture_rows': [rid for rid, v in values if not v]} for k, values in checks.items()},
        'paytable_coverage': [{'symbol': sym, 'columns': length, 'rate': rate,
                              'observations': seen_payouts[(sym, length)]}
                             for sym, payouts in PAYTABLE.items() for length, rate in payouts.items()],
        'observations': observations,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decoded', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(json.loads(args.decoded.read_text(encoding='utf-8-sig')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    failed = {name: check for name, check in result['checks'].items() if check['failed_capture_rows']}
    print(json.dumps({'decoded': result['decoded_rows'], 'checks': len(result['checks']), 'failures': failed}))
    raise SystemExit(bool(failed))
