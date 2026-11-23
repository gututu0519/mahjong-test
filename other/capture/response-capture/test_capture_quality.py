"""采集质量门禁测试，仅用临时合成数据，不作为真实游戏采集证据。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import capture_quality as quality


class CaptureQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-capture-quality-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'bodies').mkdir()
        self.rows = []
        self.config = '/999/assets/main/config.abc.json'
        self.rules = {'test-game': {
            'name': '合成质量测试', 'static_prefixes': ['/999/'], 'scope': '合成测试限定版本与语言，不是原厂证据',
            'requirements': {'verified': True, 'exhaustive': True, 'label': '临时明确清单', 'source': 'synthetic-only',
                             'assets': [{'path': '/999/index.html'}, {'path': self.config}],
                             'manifests': [self.config], 'features': ['free_spins'], 'unknown': []},
        }}
        self.feature = {'game_code': 'test-game', 'feature_id': 'free_spins', 'feature_name': '合成免费链', 'status': 'evidence_complete',
                        'checks': [{'name': '仅测试门禁输入', 'passed': True}], 'evidence': [], 'pending_reasons': []}
        self.real_requirements = quality._requirements
        patcher = patch.object(quality, '_requirements', side_effect=lambda: self.rules)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(quality.feature_detector, 'analyze_session', side_effect=lambda *args: {'features': [self.feature]})
        patcher.start()
        self.addCleanup(patcher.stop)

    def row(self, path, content=b'asset', *, status=200, state='complete', size=None, write=True):
        if isinstance(content, dict):
            content = json.dumps(content).encode()
        name = f'bodies/{len(self.rows)+1:06d}.bin'
        if write:
            (self.root / name).write_bytes(content)
        row = {'id': len(self.rows)+1, 'url': 'https://synthetic.invalid' + path, 'body': name,
               'state': state, 'status': status, 'size': len(content) if size is None else size}
        self.rows.append(row)
        return row

    def config_content(self):
        return {'name': 'main', 'uuids': [], 'versions': {'import': [], 'native': []}, 'packs': {},
                'paths': {}, 'scenes': {}, 'redirect': [], 'deps': [], 'importBase': 'import', 'nativeBase': 'native'}

    def good(self):
        self.row('/999/index.html', b'<html></html>')
        self.row(self.config, self.config_content())

    def result(self):
        return quality.analyze_capture({'id': 'synthetic-quality-test', 'state': 'recording', 'rows': self.rows}, self.root, 0)

    def test_complete_requires_explicit_verified_scope_and_all_targets(self):
        self.good()
        result = self.result()
        self.assertTrue(result['summary']['can_stop'])
        self.assertEqual(result['summary']['status'], 'complete')
        self.assertEqual(result['generated_at'], '1970-01-01T00:00:00Z')
        self.assertIn('限定版本', result['summary']['scope'])
        self.rules['test-game']['requirements']['exhaustive'] = False
        result = self.result()
        self.assertFalse(result['summary']['can_stop'])
        self.assertTrue(result['games'][0]['assets']['observed_complete'])
        self.assertFalse(result['games'][0]['assets']['all_resources_verified'])

    def test_actual_requirement_file_has_scoped_cash_targets_not_full_claim(self):
        registered = self.real_requirements()
        self.assertTrue(registered['cash-mania']['requirements']['verified'])
        self.assertFalse(registered['cash-mania']['requirements']['exhaustive'])

    def test_failed_asset_is_blocking_but_successful_retry_clears_history(self):
        self.good()
        self.row('/999/needed.js', status=404, state='complete')
        self.assertEqual(self.result()['summary']['status'], 'blocked')
        self.row('/999/needed.js', b'ok')
        result = self.result()
        self.assertEqual(result['games'][0]['assets']['observed']['failed'], 0)
        self.assertTrue(result['summary']['can_stop'])

    def test_pending_asset_is_collecting_not_complete(self):
        self.good()
        self.row('/999/loading.js', status=None, state='pending', write=False)
        result = self.result()
        self.assertEqual(result['games'][0]['status'], 'collecting')
        self.assertFalse(result['summary']['can_stop'])
        self.assertEqual(result['games'][0]['missing'][0]['severity'], 'pending')

    def test_missing_or_truncated_body_is_not_saved(self):
        self.good()
        self.row('/999/absent.js', write=False)
        self.row('/999/truncated.js', b'abc', size=100)
        result = self.result()
        self.assertEqual(result['games'][0]['assets']['observed']['missing_body'], 2)
        self.assertFalse(result['summary']['can_stop'])

    def test_declared_zero_bytes_can_be_saved_but_empty_manifest_is_unknown(self):
        self.good()
        self.row('/999/empty.js', b'', size=0)
        self.assertTrue(self.result()['summary']['can_stop'])
        row = self.rows[1]
        (self.root / row['body']).write_bytes(b'')
        row['size'] = 0
        result = self.result()
        self.assertTrue(result['games'][0]['assets']['observed_complete'])
        self.assertFalse(result['summary']['can_stop'])

    def test_missing_manifest_and_unknown_game_never_complete(self):
        self.row('/999/index.html')
        self.assertFalse(self.result()['summary']['can_stop'])
        self.rows = []
        self.row('/game-api/new-unknown-game/v4/Spin')
        result = self.result()
        self.assertEqual(result['games'][0]['status'], 'unknown')
        self.assertFalse(result['summary']['can_stop'])

    def test_feature_candidate_or_no_features_never_completes(self):
        self.good()
        self.feature['status'] = 'candidate'
        self.assertFalse(self.result()['summary']['can_stop'])
        self.feature['status'] = 'unknown'
        self.assertFalse(self.result()['summary']['can_stop'])

    def test_language_and_lazy_dependencies_are_unknown_not_red(self):
        self.row('/999/index.html')
        config = self.config_content()
        config.update(uuids=['e3bJNvI3xDDpXyr2wsdWZQ'], paths={'0': ['atlas/fr/lang_packed', 0]}, versions={'import': [0, 'abcd'], 'native': []})
        self.row(self.config, config)
        result = self.result()
        game = result['games'][0]
        self.assertEqual(game['status'], 'unknown')
        self.assertEqual(game['assets']['dynamic_dependencies']['missing'][0]['severity'], 'unknown')
        self.assertIn('语言', game['assets']['dynamic_dependencies']['missing'][0]['action'])
        self.assertFalse(result['summary']['can_stop'])

    def test_real_failure_is_listed_before_lazy_dependency_gaps(self):
        self.row('/999/index.html')
        config = self.config_content()
        config.update(uuids=['e3bJNvI3xDDpXyr2wsdWZQ'], paths={'0': ['atlas/fr/lang_packed', 0]}, versions={'import': [0, 'abcd'], 'native': []})
        self.row(self.config, config)
        self.row('/999/paytable-rules/locale/game.json', status=404)
        missing = self.result()['games'][0]['missing']
        self.assertEqual(missing[0]['severity'], 'error')
        self.assertEqual(missing[0]['path'], '/999/paytable-rules/locale/game.json')

    def test_native_prefix_with_trailing_dot_uses_observed_extension(self):
        self.row('/999/index.html')
        config = self.config_content()
        config.update(uuids=['e3bJNvI3xDDpXyr2wsdWZQ'], redirect=[0, 0], versions={'import': [], 'native': [0, 'abcd']})
        self.row(self.config, config)
        self.row('/999/assets/main/native/e3/e36c936f-237c-430e-95f2-af6c2c756650.abcd.mp3')
        result = self.result()
        dynamic = result['games'][0]['assets']['dynamic_dependencies']
        self.assertEqual(dynamic['total'], 1)
        self.assertEqual(dynamic['saved'], 1)
        self.assertTrue(any('变体' in reason for reason in dynamic['unknown']))
        self.assertFalse(result['summary']['can_stop'])

    def test_shared_package_index_is_parsed_and_ad_probe_is_not_required(self):
        self.good()
        self.row('/shared/abcd/index.json', {'name': 'sdk', 'main': 'boot.js', 'assets': []})
        self.row('/shared/abcd/boot.js')
        self.row('/shared/abcd/shell-res/ad/ad_adv_dfp_test.js', status=404)
        result = self.result()
        self.assertTrue(result['summary']['can_stop'])
        dynamic = result['games'][0]['assets']['dynamic_dependencies']
        self.assertEqual(dynamic['inspected_manifests'], 2)
        self.assertEqual(dynamic['saved'], 1)
        self.assertEqual(result['games'][0]['assets']['observed']['failed'], 0)

    def test_later_invalid_manifest_variant_keeps_known_dependencies_and_unknown(self):
        self.good()
        self.row('/shared/abcd/index.json', {'name': 'sdk', 'main': 'boot.js', 'assets': []})
        self.row('/shared/abcd/boot.js')
        self.row('/shared/abcd/index.json', b'<html>not a manifest</html>')
        result = self.result()
        dynamic = result['games'][0]['assets']['dynamic_dependencies']
        self.assertEqual(dynamic['saved'], 1)
        self.assertEqual(dynamic['inspected_manifests'], 2)
        self.assertTrue(any('不同正文' in note for note in dynamic['unknown']))
        self.assertFalse(result['summary']['can_stop'])

    def test_no_idle_or_local_readiness_shortcut_and_no_sensitive_output(self):
        self.good()
        self.rules['test-game']['requirements']['exhaustive'] = False
        self.rows[0]['url'] += '?token=secret-query'
        self.rows[0]['request_headers'] = [{'name': 'Cookie', 'value': 'secret-cookie'}]
        self.row('/account/secret-path-token', b'ignored')
        result = quality.analyze_capture({'id': 'synthetic-quality-test', 'state': 'completed', 'readiness': 'included', 'rows': self.rows}, self.root, 999999999)
        self.assertFalse(result['summary']['can_stop'])
        rendered = json.dumps(result, ensure_ascii=False)
        for token in ('secret-query', 'secret-cookie', 'secret-path-token', 'https://synthetic.invalid'):
            self.assertNotIn(token, rendered)
        self.assertIn('网络空闲', rendered)

    def test_invalid_requirement_file_and_path_traversal_are_not_complete(self):
        self.good()
        self.rows[0]['body'] = '../outside.bin'
        self.assertFalse(self.result()['summary']['can_stop'])
        with patch.object(quality, '_requirements', side_effect=ValueError('bad file')):
            result = self.result()
        self.assertFalse(result['summary']['can_stop'])


if __name__ == '__main__':
    unittest.main()
