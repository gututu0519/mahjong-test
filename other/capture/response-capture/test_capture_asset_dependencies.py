"""资源清单解析的纯合成边界测试；不读取捕获目录或访问网络。"""
import json
import unittest

from capture_asset_dependencies import analyze_asset_manifest, decode_cocos_uuid


class AssetDependencyTests(unittest.TestCase):
    def config(self, **changes):
        value = dict(name='main', paths={}, types=[], uuids=['e3bJNvI3xDDpXyr2wsdWZQ'], scenes={'main': 0},
                     deps=[], packs={}, redirect=[], importBase='import', nativeBase='native', debug=False,
                     isZip=False, encrypted=False, versions={'import': [0, '4bb03'], 'native': []})
        value.update(changes)
        return json.dumps(value).encode()

    def test_compact_uuid_matches_captured_engine_and_main_filename(self):
        self.assertEqual(decode_cocos_uuid('e3bJNvI3xDDpXyr2wsdWZQ'), 'e36c936f-237c-430e-95f2-af6c2c756650')
        self.assertEqual(decode_cocos_uuid('31tDZxlrBAMpJvSC5RmZkn'), '31b43671-96b0-4032-926f-482e51999927')
        self.assertIsNone(decode_cocos_uuid('not-a-cocos-uuid'))

    def test_scene_import_has_verified_path(self):
        data = analyze_asset_manifest('/1682240/assets/main/config.baf4f.json', self.config())
        self.assertTrue(data['recognized'])
        self.assertEqual(data['dependencies'][0]['path'], '/1682240/assets/main/import/e3/e36c936f-237c-430e-95f2-af6c2c756650.4bb03.json')
        self.assertEqual(data['dependencies'][0]['scope'], 'entry-scene')

    def test_pack_path_and_language_hint_do_not_claim_mandatory(self):
        data = analyze_asset_manifest('/1682240/assets/resources/config.a.json', self.config(
            scenes={}, packs={'012345678': [0]}, paths={'0': ['atlas/zh/lang_packed', 0]},
            versions={'import': ['012345678', 'abcde'], 'native': []}))
        self.assertEqual(data['dependencies'][0]['path'], '/1682240/assets/resources/import/01/012345678.abcde.json')
        self.assertEqual(data['dependencies'][0]['scope'], 'bundle-declared:language-hint=zh')
        self.assertTrue(any('不等于当前语言' in item for item in data['notes']))

    def test_native_is_only_prefix_until_extension_is_observed(self):
        data = analyze_asset_manifest('/x/assets/main/config.a.json', self.config(versions={'import': [0, 'abc'], 'native': [0, 'def']}))
        self.assertTrue(data['native_candidates'][0]['path_prefix'].endswith('e36c936f-237c-430e-95f2-af6c2c756650.def.'))
        self.assertFalse(any(d['path'].endswith('.png') for d in data['dependencies']))
        self.assertTrue(any(s.startswith('native-extension:') for s in data['unknown']))

    def test_dependency_bundle_route_is_not_guessed(self):
        data = analyze_asset_manifest('/x/assets/main/config.a.json', self.config(deps=['internal']))
        self.assertTrue(any(s.startswith('bundle-dependency:internal:') for s in data['unknown']))

    def test_shared_package_entry_is_known_but_encoded_assets_are_not(self):
        data = analyze_asset_manifest('/shared/abc/index.json', b'{"name":"abc","main":"engine.123.js","assets":"opaque-base64"}')
        self.assertEqual(data['dependencies'][0]['path'], '/shared/abc/engine.123.js')
        self.assertTrue(data['unknown'])

    def test_uncovered_uuid_is_explicit_unknown(self):
        data = analyze_asset_manifest('/x/assets/main/config.a.json', self.config(versions={'import': [], 'native': []}))
        self.assertTrue(any(s.startswith('uuid-unversioned:') for s in data['unknown']))

    def test_malformed_version_pairs_are_not_silently_ignored(self):
        data = analyze_asset_manifest('/x/assets/main/config.a.json', self.config(versions={'import': [0], 'native': []}))
        self.assertTrue(data['unknown'])
        self.assertFalse(data['dependencies'])

    def test_traversal_and_query_paths_are_rejected(self):
        for path in ['/../config.json', '/x/%2e%2e/config.json', '/x/config.json?token=x', '//host/config.json']:
            self.assertFalse(analyze_asset_manifest(path, self.config())['recognized'])
        data = analyze_asset_manifest('/x/config.json', self.config(importBase='../elsewhere'))
        self.assertFalse(data['dependencies'])

    def test_encrypted_zip_or_unknown_uuid_is_not_fabricated(self):
        for content in [self.config(encrypted=True), self.config(isZip=True), self.config(uuids=['unknown'])]:
            data = analyze_asset_manifest('/x/config.json', content)
            self.assertTrue(data['unknown'])
            self.assertFalse(data['dependencies'])

    def test_plain_json_is_not_mistaken_for_resource_manifest(self):
        self.assertFalse(analyze_asset_manifest('/api/data.json', b'{"ok":true}')['recognized'])
        self.assertTrue(analyze_asset_manifest('/x.json', b'"opaque"')['unknown'])

    def test_malformed_scene_and_encoded_control_paths_are_safe(self):
        data = analyze_asset_manifest('/x/config.json', self.config(scenes={'bad': [0]}))
        self.assertTrue(any('scene' in item for item in data['unknown']))
        self.assertFalse(analyze_asset_manifest('/x/%00/config.json', self.config())['recognized'])
        data = analyze_asset_manifest('/x/config.json', self.config(nativeBase='native%5csecret'))
        self.assertFalse(data['dependencies'])


if __name__ == '__main__':
    unittest.main()
