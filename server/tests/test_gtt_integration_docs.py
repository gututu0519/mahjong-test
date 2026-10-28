"""Execute published signing examples and protect the integration contract."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from server.merchant import integration_docs as docs


class IntegrationDocumentationTests(unittest.TestCase):
    def test_published_python_signing_vector(self):
        namespace = {}
        exec(docs.PYTHON_EXAMPLE, namespace)
        v = docs.VECTOR
        headers = namespace['sign_headers'](v['merchant_id'], v['merchant_secret'], v['path'], v['body'].encode(), v['timestamp'], v['nonce'])
        self.assertEqual(headers['X-GTT-Signature'], 'e8a481cb0904f9a5b872c71a98ecf531aacac3992ae81bbbf1c42a0a1a91ccec')
        self.assertEqual(hashlib.sha256(v['body'].encode()).hexdigest(), v['body_sha256'])
        self.assertEqual(headers['X-GTT-Merchant'], v['merchant_id'])

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for the published JavaScript example')
    def test_published_node_signing_vector(self):
        v = docs.VECTOR
        source = docs.NODE_EXAMPLE + '\nconst v = ' + json.dumps(v) + ";\nconst h = signHeaders(v.merchant_id, v.merchant_secret, v.path, Buffer.from(v.body), v.timestamp, v.nonce);\nif (!signatureMatches(v.signature, h['X-GTT-Signature'])) process.exit(1);\nif (signatureMatches(v.signature, 'INVALID')) process.exit(2);\nconsole.log(h['X-GTT-Signature']);\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'vector.mjs'
            path.write_text(source, encoding='utf-8')
            result = subprocess.run(['node', str(path)], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), v['signature'])

    def test_exports_cover_all_endpoints_and_resolve_schema_references(self):
        spec = docs.openapi('http://127.0.0.1:8110')
        guide = docs.markdown('http://127.0.0.1:8110')
        self.assertEqual(len(spec['paths']), 11)
        referenced = []
        def walk(value):
            if isinstance(value, dict):
                if '$ref' in value:
                    referenced.append(value['$ref'])
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(spec)
        self.assertTrue(referenced)
        for reference in referenced:
            node = spec
            for part in reference.removeprefix('#/').split('/'):
                node = node[part]
        for endpoint in docs.ENDPOINTS:
            self.assertIn(endpoint['path'], guide)
            operation = spec['paths'][endpoint['path']]['post']
            self.assertIn(str(endpoint['status']), operation['responses'])
            self.assertTrue(docs.schema_rows(endpoint['response_schema']))
        self.assertIn('data.operations[].result.wallet.after_minor', guide)
        self.assertEqual(set(spec['security'][0]), {'Merchant', 'Timestamp', 'Nonce', 'Signature'})
        self.assertEqual(spec['servers'][0]['url'], 'http://127.0.0.1:8110')
        self.assertEqual(docs.gateway_origin('https://user:password@example.com'), docs.EXAMPLE_ORIGIN)
        self.assertEqual(docs.gateway_origin('https://example.com/path'), docs.EXAMPLE_ORIGIN)
        self.assertEqual(docs.document('http://127.0.0.1:8110')['environment'], '本机联调')
        altered = docs.document()
        altered['sections'][0]['title'] = 'changed'
        self.assertNotEqual(docs.document()['sections'][0]['title'], 'changed')


if __name__ == '__main__':
    unittest.main()
