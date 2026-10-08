#!/usr/bin/env python3
"""Syntax conformance and four-engine execution of independently lowered source."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('translator', ROOT / 'scripts/translate.py')
translator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(translator)


class Syntax(unittest.TestCase):
    def test_equivalent_core_and_four_engines(self):
        term = ['binary', 'add', ['nat', '99999999999999999999999999999'], ['nat', '1']]
        a = translator.translate('core-json@1', json.dumps(term).encode())
        b = translator.translate('core-sexpr@1', b'(binary add (nat "99999999999999999999999999999") (nat "1"))')
        self.assertEqual(a['lowered'], b['lowered'])
        self.assertEqual(a['lowered_sha256'], b['lowered_sha256'])
        self.assertNotEqual(a['translation']['pin'], b['translation']['pin'])
        fixture = [{'name': 'translated-big-nat', 'term': b['lowered'],
                    'expected': {'status': 'value', 'term': ['nat', '100000000000000000000000000000'], 'plans': []}}]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'cases.json'
            path.write_text(json.dumps(fixture))
            subprocess.run([sys.executable, str(ROOT / 'scripts/crosscheck.py'),
                            '--no-build', '--cases', str(path)], cwd=ROOT, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_quoted_unicode_and_ordered_duplicate_fields(self):
        raw = '(record (("λ 😀" (label "say \\"hi\\"")) ("λ 😀" (nat "2"))))'.encode()
        result = translator.translate('core-sexpr@1', raw)
        self.assertEqual(result['lowered'], ['record', [['λ 😀', ['label', 'say "hi"']], ['λ 😀', ['nat', '2']]]])
        self.assertEqual(translator.translate('core-sexpr@1', b'(boolean #f)')['lowered'], ['boolean', False])
        self.assertEqual(translator.translate('core-sexpr@1', b'(lam (bound 0))')['lowered'], ['lam', ['bound', 0]])

    def test_markdown_and_exact_source(self):
        protocol = json.loads((ROOT / 'protocols/welcome-once/protocol.json').read_text())
        raw = ('# Welcome λ\r\nOpaque prose: do not execute me.\r\n```delvetalk-protocol\r\n' + json.dumps(protocol) + '\r\n```\r\n').encode()
        artifact = translator.translate('protocol-markdown@1', raw)
        self.assertEqual(artifact['source']['text'].encode(), raw)
        self.assertEqual(artifact['source']['sha256'], translator.digest(raw))
        self.assertEqual(artifact['lowered'], protocol)
        self.assertEqual(artifact['target'], 'local-protocol-v1')
        self.assertIn('impl/python/evaluator.py', artifact['translation']['files'])
        with self.assertRaises(ValueError):
            translator.translate('protocol-markdown@1', raw + raw)
        with self.assertRaises(ValueError):
            translator.translate('protocol-markdown@1', b'```json\n{}\n```\n')

    def test_pinned_spween_source_preserves_ast(self):
        raw = (ROOT / 'syntaxes/examples/greeting.spw').read_bytes()
        artifact = translator.translate('spween-source@1', raw)
        self.assertEqual(artifact['source']['text'].encode(), raw)
        parsed = artifact['lowered']
        self.assertEqual(parsed['source'].encode(), raw)
        self.assertEqual(parsed['ast']['meta']['id'], 'greeting')
        self.assertEqual(parsed['ast']['passages'][0]['name'], 'start')
        self.assertEqual(len(parsed['bridge_binary_sha256']), 64)
        self.assertIn('scene/spween-bridge/Cargo.lock', artifact['translation']['files'])
        self.assertEqual(artifact['target'], 'spween-source-v1')
        with self.assertRaises(ValueError):
            translator.translate('spween-source@1', b'this is not a scene')

    def test_spween_executable_subset_is_explicit(self):
        raw = (ROOT / 'syntaxes/examples/greeting.spw').read_bytes()
        artifact = translator.translate('spween-scene-i64@1', raw)
        bundle = artifact['lowered']
        self.assertEqual(bundle['source'].encode(), raw)
        self.assertEqual(bundle['profile'], 'spween-scene-i64-v1')
        self.assertEqual(artifact['target'], 'spween-protocol-bundle-v1')
        self.assertIn('start', bundle['protocol']['commands'])
        self.assertEqual(bundle['provenance']['compilerSha256'], artifact['translation']['files']['scene/lower.py'])
        full_source = raw.replace(b'Hello,', b'~ price = 1.5\nHello,')
        self.assertEqual(translator.translate('spween-source@1', full_source)['target'], 'spween-source-v1')
        with self.assertRaises(ValueError):
            translator.translate('spween-scene-i64@1', full_source)

    def test_protocol_decimal_precision(self):
        raw = b'{"profile":"delvetalk-local-v1","initial":{"exact":1.00000000000000000000000000001},"commands":{}}'
        artifact = translator.translate('protocol-json@1', raw)
        encoded = translator.canonical(artifact)
        self.assertIn(b'1.00000000000000000000000000001', encoded)
        self.assertEqual(translator.load_json(encoded), artifact)
        with self.assertRaisesRegex(ValueError, 'binary floats'):
            translator.canonical({'rounded': 0.1})

    def test_explicit_registry_extension_and_review_gate(self):
        registry = json.loads((ROOT / 'syntaxes/registry.json').read_text())
        registry['syntaxes']['agent-dialect@7'] = {
            'reviewed': True, 'module': 'syntaxes/adapters.py',
            'entry': 'sexpr', 'target': 'core-term-v1'}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'registry.json'
            path.write_text(json.dumps(registry))
            artifact = translator.translate('agent-dialect@7', b'(nat "17")', path)
            self.assertEqual(artifact['lowered'], ['nat', '17'])
            self.assertEqual(artifact['syntax'], 'agent-dialect@7')
            registry['syntaxes']['agent-dialect@7']['reviewed'] = False
            path.write_text(json.dumps(registry))
            with self.assertRaisesRegex(ValueError, 'reviewed'):
                translator.translate('agent-dialect@7', b'(nat "17")', path)

    def test_malformed_and_no_fallback(self):
        for syntax, raw in [('missing@1', b'(nat "1")'), ('core-json@1', b'["nat",1]'),
                            ('core-sexpr@1', b'(nat "1") (nat "2")'),
                            ('core-sexpr@1', b'(nat "1"'), ('core-sexpr@1', b'(label "\\ud800")'),
                            ('core-json@1', b'{"a":1,"a":2}'),
                            ('protocol-markdown@1', b'```delvetalk-protocol\n{}\n'),
                            ('protocol-markdown@1', b'```delvetalk-protocol\n{}\n```')]:
            with self.subTest(syntax=syntax, source=raw), self.assertRaises(ValueError):
                translator.translate(syntax, raw)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'source'
            path.write_bytes(b'original source\r\n')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/translate.py'),
                                     '--syntax', 'unknown@1', str(path)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b'')
            self.assertEqual(path.read_bytes(), b'original source\r\n')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/translate.py'),
                                     '--syntax', 'core-json@1', str(path), '-o', str(path)], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(path.read_bytes(), b'original source\r\n')


if __name__ == '__main__':
    unittest.main()
