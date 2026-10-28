"""Offline full-round Monte Carlo calibration; no wallet calls or outcome clipping."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import time

from server.games.buffalo_win.engine import BuffaloWin

Z = 2.576  # 99% normal-approximation interval, reported explicitly.


def configured(base, filler):
    config = copy.deepcopy(base)
    config['symbol_weights'] = {key: value * 50 for key, value in base['symbol_weights'].items()}
    config['symbol_weights']['2'] = max(1, min(10000, round(filler * 50)))
    return config


def sample_batch(arguments):
    config, buy, count, seed = arguments
    game, rng = BuffaloWin(configuration=config), random.Random(seed)
    credit_sum = credit_square_sum = steps = largest = 0
    cost = 20 * (75 if buy else 1)
    for index in range(count):
        state, paid, credit = game.initial_state('initial'), 0, 0
        for step in range(4096):
            bet = {'coin_minor': 2, 'level': 1, **({'buy_free': True} if buy and step == 0 else {})}
            outcome = game.step(state, bet, str(rng.getrandbits(256)), str(index) + ':' + str(step))
            state = outcome.state
            paid += outcome.debit_minor
            credit += outcome.credit_minor
            steps += 1
            if state['phase'] == 'ready':
                break
        else:
            raise RuntimeError('A complete round exceeded 4096 steps; calibration is invalid, not truncated.')
        if paid != cost:
            raise RuntimeError('Unexpected round debit during calibration.')
        credit_sum += credit
        credit_square_sum += credit * credit
        largest = max(largest, credit)
    return {'rounds': count, 'cost': cost, 'credit': credit_sum, 'credit_squared': credit_square_sum,
            'steps': steps, 'largest_credit': largest}


def simulate(pool, config, buy, count, seed, workers, progress=None):
    chunks = max(workers * 4, 4)
    jobs = [(config, buy, count // chunks + (index < count % chunks), seed + index * 10000019)
            for index in range(chunks)]
    totals = {'rounds': 0, 'cost': 20 * (75 if buy else 1), 'credit': 0, 'credit_squared': 0, 'steps': 0, 'largest_credit': 0}
    for result in pool.map(sample_batch, jobs):
        for key in ('rounds', 'credit', 'credit_squared', 'steps'):
            totals[key] += result[key]
        totals['largest_credit'] = max(totals['largest_credit'], result['largest_credit'])
        if progress:
            progress(totals['rounds'] / count)
    n, cost = totals['rounds'], totals['cost']
    mean = totals['credit'] / (n * cost)
    variance = max(0, (totals['credit_squared'] - totals['credit'] ** 2 / n) / (n - 1)) / cost ** 2
    half = Z * math.sqrt(variance / n)
    return {**totals, 'rtp': mean, 'ci_low': mean - half, 'ci_high': mean + half,
            'ci_half': half, 'confidence': 0.99, 'seed': seed, 'unfinished_rounds': 0}


def calibrate(target_bp, workers=4, progress=None):
    if type(target_bp) is not int or not 8000 <= target_bp <= 9900:
        raise ValueError('Calibration targets must be 80.00%–99.00%.')
    progress = progress or (lambda value: None)
    target, started = target_bp / 10000, time.time()
    base = BuffaloWin().config
    modes = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for buy in (False, True):
            name = 'buy_free' if buy else 'normal'
            train_seed = 783191 + target_bp * 100 + int(buy) * 19
            low, high = 1., 150.
            pilot_count = 2000 if buy else 20000
            for iteration in range(9):
                filler = (low + high) / 2
                report = simulate(pool, configured(base, filler), buy, pilot_count, train_seed, workers)
                progress({'mode': name, 'stage': 'search', 'iteration': iteration + 1, 'filler': filler, 'rtp': report['rtp']})
                if report['rtp'] > target:
                    low = filler
                else:
                    high = filler
            filler = (low + high) / 2
            train_count = 20000 if buy else 200000
            left, right = max(1, filler - 3), min(150, filler + 3)
            a = simulate(pool, configured(base, left), buy, train_count, train_seed + 200000003, workers)
            b = simulate(pool, configured(base, right), buy, train_count, train_seed + 200000003, workers)
            slope = (b['rtp'] - a['rtp']) / (right - left)
            if slope >= 0:
                raise RuntimeError('Calibration search could not establish a decreasing bracket.')
            filler = max(1, min(150, left + (target - a['rtp']) / slope))
            attempts = []
            for attempt in range(4):
                config = configured(base, filler)
                validation_seed = train_seed + 900000011 + attempt * 500000003
                count = 200000 if buy else 2000000
                report = simulate(pool, config, buy, count, validation_seed, workers,
                                  lambda done: progress({'mode': name, 'stage': 'validation', 'attempt': attempt + 1, 'done': done}))
                passed = report['ci_low'] <= target <= report['ci_high'] and report['ci_half'] <= .015
                attempts.append({'filler': filler, 'report': report, 'passed': passed})
                progress({'mode': name, 'stage': 'result', 'attempt': attempt + 1, 'rtp': report['rtp'], 'passed': passed})
                if passed:
                    modes[name] = {'config': config, 'validation': report, 'attempts': attempts}
                    break
                # A failed holdout becomes tuning data; the next holdout uses a fresh seed.
                filler = max(1, min(150, filler + (target - report['rtp']) / slope))
            else:
                raise RuntimeError(name + ' did not pass independent validation; model cannot be published.')
    payload = {'format': 1, 'game_id': 1, 'engine_version': BuffaloWin.version, 'target_bp': target_bp,
               'method': 'complete-round Monte Carlo; 99% normal approximation; up to four independent validations per mode',
               'certified_theoretical': False, 'created_at': int(time.time()), 'seconds': round(time.time() - started, 2), 'modes': modes}
    payload['model_hash'] = hashlib.sha256(json.dumps({name: data['config'] for name, data in modes.items()}, sort_keys=True).encode()).hexdigest()
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--targets', nargs='+', type=int, default=[9000, 9600])
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = []
    for target in args.targets:
        print(json.dumps({'target_bp': target, 'stage': 'starting'}), flush=True)
        report = calibrate(target, args.workers, lambda event: print(json.dumps({'target_bp': target, **event}), flush=True))
        reports.append(report)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix('.tmp')
        temporary.write_text(json.dumps({'models': reports}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
        temporary.replace(args.output)


if __name__ == '__main__':
    main()
