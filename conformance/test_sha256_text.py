"""Source SHA256 semantics and prepaid native work/workspace boundaries."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('DELVETALK_TEXT_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))
SOURCE = '''edition ObjectiveBend 1
def hash(text: String) -> String:
  sha256Text(text)
def both(text: String) -> {first: String, second: String}:
  {first: sha256Text(text), second: sha256Text(text)}
def spin() -> String:
  spin()
def unused() -> String:
  if true then "quiet" else sha256Text(spin())
'''


def label(value):
    return {'tag': 'label', 'value': value}


def call(request):
    result = subprocess.run([str(BINARY)], input=json.dumps(request, ensure_ascii=False) + '\n',
                            text=True, capture_output=True, check=True, timeout=20)
    return json.loads(result.stdout)


class Sha256Text(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = {}
        for name in ('hash', 'both', 'unused'):
            reply = call({'op': 'compile', 'source': SOURCE, 'entry': name})
            if reply.get('status') != 'compiled':
                raise AssertionError(reply)
            cls.artifacts[name] = reply['artifact']

    def run_hash(self, text, op='run', **limits):
        return call({'op': op, 'artifact': self.artifacts['hash'],
                     'arguments': [label(text)], 'limits': limits})

    def test_exact_utf8_known_vectors_padding_and_no_normalization(self):
        for text in ('', 'abc', 'a'*55, 'a'*56, 'a'*63, 'a'*64, 'a'*65,
                     '雪🜉✾\x00\n', 'é', 'e\u0301'):
            reply = self.run_hash(text)
            self.assertEqual(reply.get('status'), 'finished', reply)
            self.assertEqual(reply['value'], label(hashlib.sha256(text.encode()).hexdigest()))
        self.assertNotEqual(self.run_hash('é')['value'], self.run_hash('e\u0301')['value'])

    def test_typed_data_route_uses_same_primitive(self):
        reply = self.run_hash('typed text🌙', op='run-data-v1')
        self.assertEqual(reply.get('status'), 'finished', reply)
        self.assertEqual(reply['value'], label(hashlib.sha256('typed text🌙'.encode()).hexdigest()))

    def test_prepays_work_and_workspace_including_unicode_bytes(self):
        for text in ('x'*200000, '🌙'*50000):
            reply = self.run_hash(text, ticks=100000)
            self.assertEqual(reply.get('status'), 'refused', reply)
            self.assertIn('tickExhausted', reply['failure'])
        # Same scalar count, one quarter the bytes, admits ordinary work.
        self.assertEqual(self.run_hash('x'*50000, ticks=100000)['status'], 'finished')
        reply = self.run_hash('x'*10000, bytes=4200)
        self.assertEqual(reply.get('status'), 'refused', reply)
        self.assertIn('suspended', reply['failure'])

    def test_repeated_hashes_share_work_and_unused_hash_stays_lazy(self):
        reply = call({'op': 'run', 'artifact': self.artifacts['both'],
                      'arguments': [label('x'*10000)], 'limits': {'ticks': 10000}})
        self.assertEqual(reply.get('status'), 'refused', reply)
        self.assertIn('tickExhausted', reply['failure'])
        self.assertGreater(reply['ticksUsed'], 6000)
        reply = call({'op': 'run', 'artifact': self.artifacts['unused'],
                      'arguments': [], 'limits': {'ticks': 100}})
        self.assertEqual(reply['value'], label('quiet'))

    def test_real_unary_type_and_lexical_shadowing(self):
        for body in ('sha256Text(1n)', 'sha256Text()', 'sha256Text("a","b")'):
            reply = call({'op': 'compile', 'source': 'edition ObjectiveBend 1\ndef bad() -> String:\n  '+body+'\n', 'entry': 'bad'})
            self.assertNotEqual(reply.get('status'), 'compiled', reply)
        source = 'edition ObjectiveBend 1\ndef sha256Text(n: Nat) -> String:\n  "authored"\ndef entry() -> String:\n  sha256Text(4n)\n'
        compiled = call({'op': 'compile', 'source': source, 'entry': 'entry'})
        reply = call({'op': 'run', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertEqual(reply['value'], label('authored'))


if __name__ == '__main__':
    unittest.main()
