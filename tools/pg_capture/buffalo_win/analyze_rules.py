"""Check inferred Buffalo Win rules against a saved capture snapshot, without playing.

python -m tools.pg_capture.buffalo_win.analyze_rules --snapshot diagnostics/buffalo-capture-snapshot.json
No network requests, wallet changes, or capture-session mutations are performed.
"""
import argparse
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# Hypothesis inferred from the observed sw fields; validation is in-sample, not independent proof.
PAYS = {3: 5, 4: 4, 5: 3, 6: 3, 7: 2, 8: 2, 9: 2, 10: 1, 11: 1, 12: 1}


def money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'))


def predict(si):
    """Deterministic evaluation of supplied reels; does not generate random outcomes."""
    reels = si['rl']
    positions = {}
    for symbol in PAYS:
        matches = []
        for offset in range(0, len(reels), 4):
            column = [offset + i for i, value in enumerate(reels[offset:offset + 4])
                      if value in (0, symbol)]
            if not column:
                break
            matches.extend(column)
        if len({position // 4 for position in matches}) >= 3:
            positions[str(symbol)] = matches
    counts = {}
    for symbol, cells in positions.items():
        count = len(cells)
        for key, block in (si['es'] or {}).items():
            if set(block).issubset(cells):
                count += si['bsc'][key] - len(block)
        counts[symbol] = count
    base = money(sum(Decimal(n) * PAYS[int(symbol)] * Decimal(str(si['cs'])) * Decimal(str(si['ml']))
                     for symbol, n in counts.items()))
    last_start = len(reels) - 4
    extend = 1 in reels[-4:] or any(p >= last_start for cells in positions.values() for p in cells)
    return positions, counts, base, extend, money(0 if extend else base * si['gm'])


def analyze(snapshot, capture_root):
    folder = (capture_root / snapshot['id']).resolve()
    spins, seen, duplicate_rows, rejected_rows = [], set(), [], []
    for row in snapshot['rows']:
        if '/game-api/buffalo-win/' not in row['url'] or row['url'].split('?')[0].split('/')[-1] != 'Spin':
            continue
        body = row.get('body')
        path = (folder / body).resolve() if body else None
        if row.get('status') != 200 or not path or not path.is_relative_to(folder) or not path.is_file():
            rejected_rows.append(row['id'])
            continue
        response = json.loads(path.read_bytes())
        si = (response.get('dt') or {}).get('si')
        if response.get('err') or not si:
            rejected_rows.append(row['id'])
            continue
        if si['sid'] in seen:
            duplicate_rows.append(row['id'])
            continue
        seen.add(si['sid'])
        spins.append({'row': row['id'], 'si': si})

    checks = defaultdict(lambda: {'checked': 0, 'mismatch_rows': []})

    def check(name, row, condition):
        checks[name]['checked'] += 1
        if not condition:
            checks[name]['mismatch_rows'].append(row)

    groups, pay_evidence = defaultdict(list), defaultdict(list)
    for index, record in enumerate(spins):
        row, si = record['row'], record['si']
        groups[si['psid']].append(record)
        wp, counts, base, extend, payout = predict(si)
        check('winning_positions', row, wp == (si['wp'] or {}))
        check('weighted_symbol_counts', row, counts == (si['scs'] or {}))
        check('continue_extension', row, extend == si['ix'])
        check('final_payout', row, payout == money(si['tw']))
        check('scatter_count', row, si['rl'].count(1) == si['sc'])
        expected_bet = money(Decimal(str(si['cs'])) * Decimal(str(si['ml'])) * 10)
        check('bet_units', row, money(si['tbb']) == expected_bet)
        check('debit_only_paid_start', row, money(si['tb']) == (expected_bet if si['st'] == 1 else 0))
        check('wallet_equations', row,
              money(si['blb']) - money(si['tb']) == money(si['blab'])
              and money(si['blab']) + money(si['tw']) == money(si['bl'])
              and money(si['tw']) - money(si['tb']) == money(si['np']))
        check('state_transition', row,
              (si['nst'] in (4, 22)) == extend and (si['st'] in (21, 22)) == (si['fs'] is not None and si['st'] != 4))
        if index:
            previous = spins[index - 1]['si']
            check('wallet_continuity', row, money(si['blb']) == money(previous['bl']))
            if si['st'] in (4, 22):
                check('retained_reels', row, si['rl'][:-4] == previous['rl'] and si['rl'][-4:] == si['rs']['ecrl'])
                check('multiplier_increment', row, si['gm'] == previous['gm'] + 1)
            if si['st'] == 21 and previous['fs']:
                check('free_remaining', row, si['fs']['s'] == previous['fs']['s'] - 1)
                check('free_multiplier_carry', row, si['gm'] == (1 if previous['st'] not in (21, 22) else previous['gm']))
            if si['st'] == 22:
                check('extension_keeps_free_remaining', row, si['fs']['s'] == previous['fs']['s'])
        if si['st'] == 1:
            check('paid_multiplier_reset', row, si['gm'] == 1)
        if si['st'] == 21:
            original = si['orl'][:]
            for block in (si['es'] or {}).values():
                for position in block:
                    original[position] = 0
            check('free_expanded_symbols_become_wild', row, original == si['rl'])
        for symbol, (rate, award) in (si['sw'] or {}).items():
            check('symbol_paytable', row, rate == PAYS[int(symbol)] and
                  money(award) == money(Decimal(str(si['cs'])) * Decimal(str(si['ml'])) * int(rate) * counts[symbol]))
            pay_evidence[symbol].append(row)

    total_bet = sum((money(x['si']['tb']) for x in spins), Decimal(0))
    total_win = sum((money(x['si']['tw']) for x in spins), Decimal(0))
    free_groups = [v for v in groups.values() if any(x['si']['fs'] for x in v)]
    return {
        'capture_id': snapshot['id'], 'snapshot_state': snapshot.get('state'),
        'snapshot_rows': len(snapshot['rows']), 'unique_spin_responses': len(spins),
        'duplicate_rows': duplicate_rows, 'rejected_rows': rejected_rows,
        'response_row_range': [spins[0]['row'], spins[-1]['row']] if spins else [],
        'paid_starts': sum(x['si']['st'] == 1 for x in spins),
        'free_starts': sum(x['si']['st'] == 21 for x in spins),
        'extension_steps': sum(x['si']['st'] in (4, 22) for x in spins),
        'rounds': len(groups), 'completed_rounds': sum(v[-1]['si']['nst'] == 1 for v in groups.values()),
        'positive_rounds': sum(any(x['si']['tw'] > 0 for x in v) for v in groups.values()),
        'positive_settlements': sum(x['si']['tw'] > 0 for x in spins),
        'state_transitions': dict(Counter(f"{x['si']['st']}->{x['si']['nst']}" for x in spins)),
        'total_bet': str(total_bet), 'total_payout': str(total_win), 'net': str(total_win - total_bet),
        'observed_return_ratio': str(total_win / total_bet) if total_bet else None,
        'paytable': PAYS, 'paytable_evidence_rows': dict(pay_evidence),
        'free_features': [{'trigger_row': next(x['row'] for x in v if x['si']['fs']),
                           'trigger_scatter_count': next(x['si']['sc'] for x in v if x['si']['fs']),
                           'initial_free_spins': next(x['si']['fs']['ts'] for x in v if x['si']['fs']),
                           'final_row': v[-1]['row'], 'final_multiplier': v[-1]['si']['gm'],
                           'payout': str(sum((money(x['si']['tw']) for x in v if x['si']['st'] in (21, 22)), Decimal(0)))}
                          for v in free_groups],
        'checks': dict(checks),
        'limitations': ['In-sample reconstruction only; not a recovery of the original RNG or reel weights.',
                        'Current stake coverage is limited; free-spin trigger and retrigger tables need more evidence.',
                        'Observed return ratio is not theoretical RTP.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--capture-root', type=Path, default=ROOT / 'response-capture/captures')
    parser.add_argument('--output', type=Path, default=ROOT / 'diagnostics/buffalo-rules/summary.json')
    args = parser.parse_args()
    summary = analyze(json.loads(args.snapshot.read_bytes()), args.capture_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    failures = {k: v['mismatch_rows'] for k, v in summary['checks'].items() if v['mismatch_rows']}
    print(json.dumps({'responses': summary['unique_spin_responses'], 'paid_starts': summary['paid_starts'],
                      'free_starts': summary['free_starts'], 'extension_steps': summary['extension_steps'],
                      'checks': len(summary['checks']), 'mismatches': failures, 'output': str(args.output)}))
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
