"""Shipped interpretation domains run inside the unchanged native work budget."""
import json
import importlib.util
import tempfile
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('DELVETALK_TEXT_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))


def label(s): return {'tag': 'label', 'value': s}
def nat(n): return {'tag': 'natural', 'value': str(n)}
def call(request):
    return json.loads(subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
        text=True, capture_output=True, timeout=30, check=True).stdout)
def plain(value):
    if value['tag'] == 'record': return {f['name']: plain(f['value']) for f in value['fields']}
    return value['value']


class TextBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules = [{'name': name, 'source': (ROOT / path).read_text()} for name, path in [
            ('List', 'world/lib/prelude/List.obend'), ('Preparation', 'world/lib/prelude/Preparation.obend'), ('Encounter', 'world/lib/prelude/Encounter.obend'),
            ('Document', 'world/lib/document/Document.obend'), ('Interpretation', 'protocols/interpretation/Interpretation.obend')]]
        cls.artifacts = {}
        cls.modules = modules
        for entry in ('route', 'childToken'):
            result = call({'op': 'compile', 'modules': modules, 'entry': entry})
            if result.get('status') != 'compiled': raise AssertionError(result)
            cls.artifacts[entry] = result['artifact']
        for entry in ('textSpan', 'textBreak'):
            source = 'edition ObjectiveBend 1\ndef scan(s: String, alphabet: String) -> Nat:\n  ' + entry + '(s, alphabet)\n'
            result = call({'op': 'compile', 'source': source, 'entry': 'scan'})
            if result.get('status') != 'compiled': raise AssertionError(result)
            cls.artifacts[entry] = result['artifact']

    def run_entry(self, entry, arguments, **limits):
        return call({'op': 'run-data-v1', 'artifact': self.artifacts[entry], 'arguments': arguments, 'limits': limits})

    def test_entire_utterance_domain_including_long_literal_fields(self):
        texts = ['x' * 512, 'x' * 4096, ' ' * 4096, '🌙' * 1024,
                 'do ' + 'c' * 2040 + ' ' + 'a' * 2040,
                 'do cap act ' + 'x' * (4096 - len('do cap act ')),
                 ' \t\ndo cap act ' + 'x' * (4096 - len(' \t\ndo cap act ')),
                 'do cap act ' + '🌙' * 1021,
                 ' do ' + 'c' * 409 + ' ' + 'a' * 3681 + ' ',
                 ' ' * 128 + 'do ' + 'c' * 1981 + ' ' + 'a' * 1982 + ' ']
        for text in texts:
            with self.subTest(length=len(text.encode('utf-8'))):
                result = self.run_entry('route', [label(text)])
                self.assertEqual(result.get('status'), 'finished', result)
                self.assertLess(result['ticksUsed'] + result['conversionNodes'], 100000)
                route = plain(result['value'])
                if text.lstrip().startswith('do '):
                    self.assertTrue(route['literal'])
                    self.assertTrue(route['valid'])
                    if 'cap act ' in text:
                        self.assertEqual(route['fields'], text.split('cap act ', 1)[1])
                else: self.assertFalse(route['literal'])
        for text in ('do', 'do   ', 'do card'):
            result = self.run_entry('route', [label(text)])
            self.assertEqual(result['status'], 'finished', result)
            self.assertFalse(plain(result['value'])['valid'])

    def test_child_domain_boundaries_and_unicode_rejection(self):
        for text, expected in [('z' * 24, True), ('z' * 64, True), ('_-09Az' * 10, True),
                                ('', False), ('a' * 65, False), ('a' * 63 + '!', False),
                                ('a' * 63 + '🌙', False), ('e\u0301', False), ('a/b', False)]:
            result = self.run_entry('childToken', [label(text), nat(0)])
            self.assertEqual(result['status'], 'finished', result)
            self.assertEqual(result['value'], {'tag': 'boolean', 'value': expected}, result)

    def test_scans_count_scalars_without_normalization(self):
        for entry, text, alphabet, expected in [
            ('textSpan', '🌙e\u0301!', '🌙e\u0301', 3), ('textBreak', '🌙e\u0301!', '!', 3),
            ('textSpan', 'e\u0301', 'é', 0), ('textSpan', 'abc', '', 0),
            ('textBreak', 'abc', '', 3), ('textBreak', '', 'abc', 0)]:
            result = self.run_entry(entry, [label(text), label(alphabet)])
            self.assertEqual(result.get('value'), nat(expected), result)

    def test_long_route_runs_in_actual_receiving_host(self):
        spec = importlib.util.spec_from_file_location('text_boundary_world', ROOT / 'scripts/world.py')
        world = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(world)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'world.json'
            protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'route': {
                'require': [], 'set': {}, 'outbox': [], 'result': ['package', {
                    'modules': self.modules, 'entry': 'route'}, [['input', 'text']]]}}}
            made = world.exchange(database, {'op': 'create', 'object': 'router', 'principal': 'maker',
                'intent': 'make', 'protocol': protocol, 'law': ['maker']}, profile='compiled')
            self.assertEqual(made['kind'], 'committed', made)
            text = ' do ' + 'c' * 409 + ' ' + 'a' * 3681 + ' '
            receipt = world.exchange(database, {'op': 'invoke', 'object': 'router', 'principal': 'maker',
                'intent': 'route', 'expected': made['data']['root'], 'command': 'route',
                'input': {'text': text}}, profile='compiled')
            self.assertEqual(receipt['kind'], 'committed', receipt)
            self.assertTrue(receipt['data']['result']['literal'])
            self.assertEqual(receipt['data']['result']['action'], 'a' * 3681)

    def test_new_primitives_keep_type_and_shadowing_boundaries(self):
        for body in ('textSpan(7n, "a")', 'textBreak("a", 7n)', 'textSpan("a")'):
            result = call({'op': 'compile', 'source': 'edition ObjectiveBend 1\ndef f() -> Nat:\n  ' + body + '\n', 'entry': 'f'})
            self.assertEqual(result['status'], 'error', result)
        source = 'edition ObjectiveBend 1\ndef textSpan(s: String, a: String) -> Nat:\n  7n\ndef f() -> Nat:\n  textSpan("a", "a")\n'
        result = call({'op': 'compile', 'source': source, 'entry': 'f'})
        run = call({'op': 'run-data-v1', 'artifact': result['artifact'], 'arguments': []})
        self.assertEqual(run.get('value'), nat(7), run)

    def test_preflight_is_work_bounded_and_short_prefix_ignores_long_suffix(self):
        short = self.run_entry('textBreak', [label(' x'), label(' ')])
        long = self.run_entry('textBreak', [label(' ' + 'x' * 100000), label(' ')])
        self.assertEqual(short['status'], 'finished', short)
        self.assertEqual(long['ticksUsed'], short['ticksUsed'])
        for text, alphabet in [('a' * 4096, 'a'), ('a', 'a' * 100000)]:
            result = self.run_entry('textSpan', [label(text), label(alphabet)], ticks=100)
            self.assertEqual(result['status'], 'refused', result)
            self.assertIn('tickExhausted', result['failure'])
            self.assertEqual(result['ticksUsed'] + result['conversionNodes'], 100)


if __name__ == '__main__': unittest.main()
