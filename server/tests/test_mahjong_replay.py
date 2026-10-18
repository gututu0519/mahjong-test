import base64
import concurrent.futures
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools.pg_capture.mahjong_ways2.local_spin import LocalSpin, SpinError
from server.adapters.pg.protocol import (decode_request, double_field, field, fields, pack,
                           text_field, unpack)


def request(sid='0', cs=.01, ml=5, seed=29, token='local-demo-session'):
    raw = (text_field(1, token) + field(2, 0, 1) + field(3, 0, 1) +
           text_field(5, sid) + text_field(12, '0_C') +
           double_field(21, cs) + field(22, 0, ml))
    return pack(raw, seed)


def response(body, seed=29):
    raw, _ = unpack(body, seed)
    return {n: struct.unpack('<d', v)[0] if w == 1 else v.decode() if n in (1, 2) else v
            for n, w, v in fields(raw)}


class LocalSpinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'wallet.json'
        self.engine = LocalSpin(self.path)

    def test_transport_all_seeds_and_request_validation(self):
        for seed in range(256):
            raw, extracted = unpack(request(seed=seed))
            self.assertEqual(extracted, seed)
            self.assertEqual(decode_request(raw)['atk'], 'local-demo-session')
            self.assertEqual(pack(raw, seed), request(seed=seed))
        for raw in (b'', b'\x00', b'\x0a\xff', b'\x09\x00'):
            with self.assertRaises(ValueError):
                list(fields(raw)) if raw else unpack(raw)

    def test_loss_win_cascade_settlement_and_restart(self):
        loss = response(self.engine.spin(request()))
        self.assertEqual((loss[15], loss[17], loss[14]), (1, 0, 1999))
        first = response(self.engine.spin(request('1')))
        self.assertEqual((first[3], first[4], first[15], first[17], first[14]), (1, 4, 1, .6, 1998.6))
        # Reloading during a cascade preserves its bet, parent ID, and balance.
        self.engine = LocalSpin(self.path)
        info = self.engine.game_info({'dt': {'bl': 2000}})
        self.assertEqual(info['dt']['bl'], 1998.6)
        self.assertEqual(base64.b64decode(info['localSpin']), unpack(self.engine.spin(request('1')), 29)[0])
        second = response(self.engine.spin(request('2')))
        self.assertEqual((second[3], second[4], second[15], second[17], second[14]), (4, 4, 0, .3, 1998.9))
        final = response(self.engine.spin(request('3')))
        self.assertEqual((final[3], final[4], final[15], final[17], final[14]), (4, 1, 0, 0, 1998.9))
        self.assertEqual((first[2], second[2], final[2]), ('2', '2', '2'))
        self.assertEqual(final[6], .9)
        self.assertEqual(self.engine.wallet()['dt']['cb'], 1998.9)

    def test_retry_and_concurrent_duplicate_debit_once(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            bodies = list(pool.map(lambda seed: self.engine.spin(request(seed=seed)), range(4)))
        decoded = [response(body, seed) for seed, body in enumerate(bodies)]
        self.assertTrue(all(r == decoded[0] for r in decoded))
        self.assertEqual(self.engine.state['balance'], 1999)
        self.assertEqual(self.engine.state['serial'], 1)

    def test_invalid_inputs_do_not_change_wallet(self):
        for body in (request(cs=.02), request(ml=11), request(token='wrong'), request(sid='old')):
            with self.assertRaises(SpinError):
                self.engine.spin(body)
            self.assertEqual(self.engine.state['balance'], 2000)
        self.engine.spin(request())
        self.engine.spin(request('1'))
        with self.assertRaisesRegex(SpinError, 'Finish the current cascade'):
            self.engine.spin(request('2', ml=1))
        self.assertEqual(self.engine.state['balance'], 1998.6)

    def test_selected_bet_scales_entire_round_and_wraps(self):
        sid, total_bet, total_win = '0', 0, 0
        for round_data in self.engine.rounds:
            for step in round_data:
                r = response(self.engine.spin(request(sid, cs=.3, ml=2)))
                sid = r[1]
                self.assertAlmostEqual(r[17], step['transaction']['tw'])
                total_bet += r[15]
                total_win += r[17]
                self.assertAlmostEqual(r[14], 2000 - total_bet + total_win)
        self.assertEqual(self.engine.state['round'], 0)
        self.assertEqual(self.engine.state['step'], 0)
        self.assertEqual(response(self.engine.spin(request(sid, cs=.06, ml=10)))[15], 12)

    def test_insufficient_balance_and_failed_save_are_atomic(self):
        self.engine.state['balance'] = 0
        with self.assertRaisesRegex(SpinError, 'Insufficient'):
            self.engine.spin(request())
        self.assertEqual(self.engine.state['serial'], 0)
        self.engine.state['balance'] = 2000
        self.engine.path = self.path / 'missing' / 'wallet.json'
        self.path.write_text('not a directory')
        with self.assertRaises(OSError):
            self.engine.spin(request())
        self.assertEqual(self.engine.state['balance'], 2000)
        self.assertEqual(self.engine.state['serial'], 0)


if __name__ == '__main__':
    unittest.main()
