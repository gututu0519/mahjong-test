import unittest
from pathlib import Path
from server.adapters.pg.client_modules import prepare_module, repair_source


class ModuleRepairTests(unittest.TestCase):
    def test_real_formatted_module(self):
        original = (Path(__file__).parent / 'fixtures/pg-client/formatted-index.js').read_bytes()
        fixed, revision = prepare_module(original)
        self.assertNotEqual(original, fixed)
        self.assertEqual(repair_source(fixed.decode()), fixed.decode())
        self.assertEqual(prepare_module(original)[1], revision)
        self.assertNotEqual(prepare_module(original + b'\n// update')[1], revision)

    def test_unknown_loop_rejected(self):
        with self.assertRaisesRegex(ValueError, 'timed out'):
            prepare_module(b'while (true) {}')

    def test_comma_declaration_with_different_closing_indent(self):
        original = (Path(__file__).parent / 'fixtures/pg-client/formatted-index.js').read_bytes()
        # Beautifiers indent a continued declaration two columns past its closing brace.
        variant = original.replace(b'    var g = F(this, function() {',
            b'    var unused = 0\n      , g = F(this, function() {')
        self.assertNotEqual(variant, original)
        fixed, _ = prepare_module(variant)
        self.assertIn(b"= '.+$';", fixed)

    def test_plain_module_preserved(self):
        source = b'System.register([], function () { return {execute() {}}; });'
        self.assertEqual(prepare_module(source)[0], source)

    def test_module_with_browser_observer(self):
        source = (b'System.register([], function(){});'
            b'const node = document.querySelector("#game-overlay") || document.body;'
            b'new MutationObserver(() => {}).observe(node, {childList: true});')
        self.assertEqual(prepare_module(source)[0], source)

    def test_unrelated_regex_preserved(self):
        source = "const value = 'prefix' + '+$'; System.register([], function(){});"
        self.assertEqual(repair_source(source), source)


if __name__ == '__main__':
    unittest.main()
