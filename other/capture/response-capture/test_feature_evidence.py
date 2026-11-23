"""仅用临时合成 protobuf 验证检测器；这些结果不是原厂抓取证据。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys

import feature_evidence as detector


def encode(data, types, name='__root__'):
    p = detector.protocol

    def scalar(n, kind, value):
        if kind in ('int32', 'uint32', 'int64', 'uint64', 'bool'):
            return p.field(n, 0, int(value))
        if kind == 'double':
            return p.double_field(n, value)
        if kind == 'string':
            return p.text_field(n, value)
        if kind == 'bytes':
            return p.field(n, 2, value)
        if kind == 'Int32List' and isinstance(value, list):
            value = {'__value': value}
        return p.field(n, 2, encode(value, types, kind))

    result = []
    for key, spec in types[name]['fields'].items():
        if key not in data or data[key] is None:
            continue
        n, kind, value = spec['id'], spec['type'], data[key]
        if 'keyType' in spec:
            for k, v in value.items():
                result.append(p.field(n, 2, scalar(1, spec['keyType'], int(k)) + scalar(2, kind, v)))
        elif spec.get('rule') == 'repeated':
            result.extend(scalar(n, kind, item) for item in value)
        else:
            result.append(scalar(n, kind, value))
    return b''.join(result)


def synthetic_chain(code='wild-bandito', retrigger=False, gold=False, cascade=False, buy=False):
    """合成最低生命周期，不代表概率、原厂盘面或真实账户。"""
    count = 12 if code == 'wild-bandito' else 10
    size = 25 if code == 'wild-bandito' else 35
    balance, award, remaining, total, previous = 100.0, 0.0, count, count, 'synthetic-before'
    frames = []

    def add(st, nst, *, debit=0, win=0, free=True, added=0, scatters=False, refill=False, fb=0):
        nonlocal balance, previous, award
        sid = 'synthetic-spin-' + str(len(frames) + 1)
        board = [2] * size
        if scatters:
            for pos in ([1, 6, 11] if size == 25 else [1, 8, 15]):
                board[pos] = 1
        before = balance
        balance = round(balance - debit + win, 8)
        award = round(award + win, 8)
        tx = dict(sid=sid, psid='synthetic-round' if free else sid, st=st, nst=nst,
                  cs=0.03 if size == 25 else 0.02, ml=2, tbb=1.2 if size == 25 else 0.8,
                  tb=debit, tw=win, np=win-debit, blb=before, blab=before-debit, bl=balance,
                  rl=board[:], orl=board[:], sc=3 if scatters else 0, gm=1)
        if free:
            tx['fs'] = dict(s=remaining, ts=total, nosa=added, aw=award, gm=1)
        if gold and st in (21, 22):
            tx['ssb'] = {str(p): p for p in range(15, 20) if board[p] >= 2}
            tx['ss'] = dict(tx['ssb'])
        if refill:
            tx['rs'] = {'rns': [[2], [], [], [], []]}
        frames.append({'tx': tx, 'previous': previous, 'token': 'synthetic-secret-session-A', 'fb': fb})
        previous = sid

    add(1, 21, debit=1.2 if size == 25 else 0.8, added=count, scatters=True, fb=2 if buy else 0)
    used_retrigger = False
    first = True
    while remaining:
        remaining -= 1
        extra = count if retrigger and not used_retrigger and remaining == count - 2 else 0
        if extra:
            remaining += extra
            total += extra
            used_retrigger = True
        if cascade and first:
            add(21, 22, win=0.2)
            add(22, 21 if remaining else 1, refill=True)
        else:
            add(21, 21 if remaining else 1, added=extra, scatters=bool(extra))
        first = False
    add(1, 1, debit=1.2 if size == 25 else 0.8, free=False)
    return frames


class FeatureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-feature-evidence-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'bodies').mkdir()

    def save(self, frames, code='wild-bandito'):
        rows = []
        p = detector.protocol
        for index, frame in enumerate(frames, 1):
            tx = frame['tx']
            fields = [p.text_field(1, frame['token']), p.field(2, 0, 1), p.field(3, 0, 1),
                      p.text_field(5, frame['previous']), p.text_field(12, '0_C'),
                      p.double_field(21, tx['cs']), p.field(22, 0, tx['ml'])]
            if frame.get('fb'):
                fields.append(p.field(24, 0, frame['fb']))
            request = p.pack(b''.join(fields), 37, salt=detector.SUPPORTED[code][0])
            schema = detector.SCHEMAS[code]
            response = p.pack(encode(tx, schema['transaction']['nested']) + encode(tx, schema['wallet']['nested']), 37, salt=detector.SUPPORTED[code][0])
            request_path, body_path = f'bodies/{index:06d}.request.bin', f'bodies/{index:06d}.bin'
            (self.root / request_path).write_bytes(request)
            (self.root / body_path).write_bytes(response)
            rows.append({'id': index, 'state': 'complete', 'status': 200,
                         'url': f'https://synthetic.invalid/game-api/{code}/v4/Spin?token=do-not-export',
                         'request_body': request_path, 'body': body_path})
        return {'id': 'synthetic-unit-test', 'rows': rows}

    def analyze(self, frames, code='wild-bandito'):
        return detector.analyze_session(self.save(frames, code), self.root)

    def feature(self, result, name):
        return next(f for f in result['features'] if f['feature_id'] == name)

    def assert_incomplete(self, result):
        self.assertTrue(all(f['status'] != 'evidence_complete' for f in result['features']))

    def test_complete_free_cycle_and_retrigger_are_separate(self):
        result = self.analyze(synthetic_chain())
        self.assertEqual(self.feature(result, 'free_spins')['status'], 'evidence_complete')
        self.assertEqual(self.feature(result, 'free_retrigger')['status'], 'pending')
        retriggered = self.analyze(synthetic_chain(retrigger=True))
        self.assertEqual(self.feature(retriggered, 'free_retrigger')['status'], 'evidence_complete')

    def test_missing_response_or_missing_final_paid_spin_is_incomplete(self):
        frames = synthetic_chain()
        for omitted in (0, 2, len(frames)-2, len(frames)-1):
            with self.subTest(omitted=omitted):
                self.assert_incomplete(self.analyze(frames[:omitted] + frames[omitted+1:]))

    def test_state_gap_and_wrong_counters_are_incomplete(self):
        frames = synthetic_chain()
        frames[2]['tx']['st'] = 22
        self.assert_incomplete(self.analyze(frames))
        frames = synthetic_chain(retrigger=True)
        frames[2]['tx']['fs']['ts'] += 1
        self.assert_incomplete(self.analyze(frames))

    def test_cross_session_does_not_join(self):
        frames = synthetic_chain()
        for frame in frames[4:]:
            frame['token'] = 'synthetic-secret-session-B'
        self.assert_incomplete(self.analyze(frames))

    def test_identical_retry_is_deduplicated_without_becoming_new_evidence(self):
        frames = synthetic_chain()
        frames.insert(3, copy.deepcopy(frames[2]))
        result = self.analyze(frames)
        self.assertEqual(result['stats']['duplicate_spins'], 1)
        self.assertEqual(self.feature(result, 'free_spins')['status'], 'evidence_complete')
        self.assert_incomplete(self.analyze([frames[0], *[copy.deepcopy(frames[1]) for _ in range(15)]]))

    def test_conflicting_retry_and_wallet_discontinuity_are_incomplete(self):
        frames = synthetic_chain()
        duplicate = copy.deepcopy(frames[2])
        duplicate['tx']['fs']['s'] += 1
        frames.insert(3, duplicate)
        self.assert_incomplete(self.analyze(frames))
        frames = synthetic_chain()
        for key in ('blb', 'blab', 'bl'):
            frames[2]['tx'][key] += 1
        self.assert_incomplete(self.analyze(frames))

    def test_nonzero_fb_cannot_automatically_verify_purchase(self):
        result = self.analyze(synthetic_chain('mahjong-ways2', buy=True), 'mahjong-ways2')
        purchase = self.feature(result, 'feature_buy')
        self.assertEqual(purchase['status'], 'candidate')
        self.assertTrue(purchase['pending_reasons'])
        self.assert_incomplete(result)

    def test_third_reel_requires_full_free_cycle_new_spin_and_refill(self):
        frames = synthetic_chain('mahjong-ways2', gold=True, cascade=True)
        result = self.analyze(frames, 'mahjong-ways2')
        self.assertEqual(self.feature(result, 'free_third_reel_gold')['status'], 'evidence_complete')
        self.assert_incomplete(self.analyze([frames[1]], 'mahjong-ways2'))
        self.assert_incomplete(self.analyze(synthetic_chain('mahjong-ways2', gold=True), 'mahjong-ways2'))
        frames[2]['tx']['ssb'].pop('16')
        self.assert_incomplete(self.analyze(frames, 'mahjong-ways2'))

    def test_invalid_body_path_and_failed_status_do_not_complete(self):
        detail = self.save(synthetic_chain())
        detail['rows'][2]['body'] = '../outside.bin'
        result = detector.analyze_session(detail, self.root)
        self.assertEqual(result['stats']['invalid_saved_spins'], 1)
        self.assert_incomplete(result)
        detail = self.save(synthetic_chain())
        detail['rows'][2]['status'] = 500
        self.assert_incomplete(detector.analyze_session(detail, self.root))

    def test_plain_body_and_unsupported_game_are_pending(self):
        detail = self.save(synthetic_chain())
        (self.root / detail['rows'][2]['body']).write_text('{"err":"not a spin"}', encoding='utf8')
        self.assert_incomplete(detector.analyze_session(detail, self.root))
        detail = {'id': 'synthetic-unit-test', 'rows': [{'state': 'complete', 'status': 200, 'body': 'bodies/000001.bin', 'url': 'https://synthetic.invalid/game-api/cash-mania/v4/Spin'}]}
        result = detector.analyze_session(detail, self.root)
        self.assertEqual(result['features'], [])
        self.assertEqual(result['pending_games'][0]['status'], 'pending')

    def test_output_is_sanitized_and_does_not_assert_implementation(self):
        output = json.dumps(self.analyze(synthetic_chain()), ensure_ascii=False)
        for forbidden in ('synthetic-secret', 'synthetic-spin', 'synthetic-round', 'do-not-export', 'https://', 'blb', 'blab', 'implementation_complete'):
            self.assertNotIn(forbidden, output)
        self.assertIn('sha256', output)
        self.assertIn('仅判断已保存协议样本', output)

    def test_cli_reads_manifest_path_as_utf8_and_returns_json(self):
        detail = self.save(synthetic_chain())
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps(detail), encoding='utf-8-sig')
        run = subprocess.run([sys.executable, detector.__file__, str(manifest), '--bodies-root', str(self.root)], capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr.decode('utf-8', errors='replace'))
        result = json.loads(run.stdout.decode('utf-8'))
        self.assertEqual(result['session_id'], 'synthetic-unit-test')
        self.assertEqual(self.feature(result, 'free_spins')['status'], 'evidence_complete')


if __name__ == '__main__':
    unittest.main()
