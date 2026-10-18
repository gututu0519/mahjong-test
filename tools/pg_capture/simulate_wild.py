"""Run complete rule-based features through real HTTP/binary PG requests."""
import argparse
import json
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server.adapters.pg.protocol import pack, unpack, text_field, field, double_field
from server.adapters.pg.wild_bandito import SCHEMA
from server.adapters.pg.wire import decode
from .serve_wild_acceptance import build_acceptance


def simulate(scenario='basic', scatters=3):
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / 'wallet.sqlite3'
        http = build_acceptance(0, database, scenario, scatters)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        origin = lambda: f'http://127.0.0.1:{http.server_port}'

        def call(path, data, headers):
            req = Request(origin() + path, data=data, headers=headers)
            try:
                response = urlopen(req, timeout=10)
            except HTTPError as error:
                response = error
            with response:
                return response.status, response.read()

        try:
            status, data = call('/api/v1/sessions', b'{}', {'Content-Type': 'application/json'})
            assert status == 201
            session = json.loads(data)
            token = session['token']
            headers = {'Content-Type': 'application/octet-stream', 'X-Local-Game-Session': token}
            common = text_field(1, token) + field(2, 0, 2) + field(3, 0, 1)
            previous = '0'
            frames = []
            resumed = False
            total_debit = total_credit = 0
            final = None
            for step in range(100):
                raw = (common + text_field(5, previous) + text_field(12, '0_C')
                       + double_field(21, .1) + field(22, 0, 2) + field(24, 0, 0))
                seed = (step * 17 + 3) % 256
                status, response = call('/game-api/wild-bandito/v4/Spin', pack(raw, seed, salt=5), headers)
                assert status == 200, (status, step)
                plain = unpack(response, seed, salt=5)[0]
                tx = decode(plain, SCHEMA['transaction']['nested'])
                tx.update(decode(plain, SCHEMA['wallet']['nested']))
                previous = tx['sid']
                debit, credit = round(tx.get('tb', 0) * 100), round(tx.get('tw', 0) * 100)
                total_debit += debit
                total_credit += credit
                assert debit == (400 if step == 0 else 0)
                assert round(tx['bl'] * 100) == 200000 - total_debit + total_credit
                if step % 3 == 0:
                    retry_seed = (seed + 1) % 256
                    status, retry = call('/game-api/wild-bandito/v4/Spin', pack(raw, retry_seed, salt=5), headers)
                    assert status == 200
                    assert unpack(retry, retry_seed, salt=5)[0] == plain
                frames.append({'step': step, 'st': tx.get('st'), 'nst': tx.get('nst'), 'gm': tx.get('gm'),
                               'free': tx.get('fs'), 'debit_minor': debit, 'credit_minor': credit,
                               'balance_minor': round(tx['bl'] * 100)})
                if step == 0:
                    assert tx['nst'] == 21
                    assert tx['fs']['s'] == 12 + (scatters - 3) * 2
                if tx['st'] in (21, 22):
                    # Every ordinary symbol on the middle reel must carry gold,
                    # even the hidden cell. A winning gold symbol becomes Wild.
                    assert all(tx['orl'][p] <= 1 or p in tx.get('ssb', {}).values() for p in range(10, 15))
                if step == 3:
                    before = http.service.wallet(token)['balance_minor']
                    http.shutdown()
                    thread.join()
                    http.server_close()
                    http = build_acceptance(0, database, scenario, scatters)
                    thread = threading.Thread(target=http.serve_forever, daemon=True)
                    thread.start()
                    status, info = call('/game-api/wild-bandito/v4/GameInfo/Get', pack(common, 13, salt=5), headers)
                    assert status == 200
                    info = decode(unpack(info, 13, salt=5)[0], SCHEMA['transaction']['nested'])
                    assert info['sid'] == previous and info['fs'] == tx['fs']
                    assert http.service.wallet(token)['balance_minor'] == before
                    resumed = True
                if tx['nst'] == 1:
                    final = tx
                    break
            assert final is not None, 'Feature did not finish'
            expected_total = 12 + (scatters - 3) * 2 + (12 if scenario in ('retrigger', 'last-retrigger') else 0)
            expected_credit = 0 if scenario == 'no-win' else 2400
            assert final['fs']['s'] == 0 and final['fs']['ts'] == expected_total
            assert sum(f['st'] == 21 for f in frames) == expected_total
            assert total_credit == expected_credit and total_debit == 400
            assert final['fs']['aw'] == expected_credit / 100 and final['gm'] == (1 if scenario == 'no-win' else 3)
            summary = http.pg.history(token, {}, summary=True)['dt']['bs']
            assert summary['bc'] == 1 and summary['btba'] == 4 and summary['btwa'] == expected_credit / 100
            # A new ordinary round resets the multiplier and charges exactly once.
            raw = common + text_field(5, previous) + text_field(12, '0_C') + double_field(21, .1) + field(22, 0, 2) + field(24, 0, 0)
            status, data = call('/game-api/wild-bandito/v4/Spin', pack(raw, 19, salt=5), headers)
            assert status == 200
            normal = decode(unpack(data, 19, salt=5)[0], SCHEMA['transaction']['nested'])
            assert normal['st'] == normal['nst'] == 1 and normal['gm'] == 1 and 'fs' not in normal
            assert http.service.wallet(token)['balance_minor'] == 200000 - 800 + expected_credit
            return dict(scenario=scenario, scatters=scatters, free_spins=expected_total, requests=len(frames),
                        debit_minor=total_debit, award_minor=total_credit, feature_balance_minor=200000 - 400 + expected_credit,
                        following_normal_balance_minor=200000 - 800 + expected_credit, resumed=resumed, frames=frames)
        finally:
            http.shutdown()
            thread.join()
            http.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('diagnostics/wild-free-simulation.json'))
    args = parser.parse_args()
    results = [simulate(scenario, scatters) for scenario in ('basic', 'no-win', 'retrigger', 'last-retrigger') for scatters in (3, 4, 5)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    summary = [{k: v for k, v in r.items() if k != 'frames'} for r in results]
    args.output.with_name(args.output.stem + '-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
