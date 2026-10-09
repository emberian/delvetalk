#!/usr/bin/env python3
"""Hosted text extension through checked source and the bounded demand machine."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('DELVETALK_TEXT_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))
SOURCE = (ROOT / 'syntaxes/examples/text-gallery.obend').read_text()


def label(s):
    return {'tag': 'label', 'value': s}


def nat(n):
    return {'tag': 'natural', 'value': str(n)}


def call(request):
    result = subprocess.run([str(BINARY)], input=json.dumps(request) + '\n', text=True,
                            capture_output=True, check=True, timeout=20)
    return json.loads(result.stdout)


class TextPrimitives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = {}
        for name in ('describe', 'caption', 'preview', 'length', 'join', 'decimal', 'unused'):
            reply = call({'op': 'compile', 'source': SOURCE, 'entry': name})
            if reply.get('status') != 'compiled':
                raise AssertionError(reply)
            cls.artifacts[name] = reply['artifact']

    def execute(self, name, *arguments, **limits):
        return call({'op': 'run', 'artifact': self.artifacts[name],
                     'arguments': list(arguments), 'limits': limits})

    def test_authored_dynamic_description_and_refusal(self):
        reply = self.execute('describe', label('Moon room'), nat(13))
        self.assertEqual(reply['value'], label('Moon room: 13 exhibits'), reply)
        for text, accepted in [('短い caption', True), ('🌙' * 25, False)]:
            reply = self.execute('caption', label(text))
            fields = {field['name']: field['value'] for field in reply['value']['fields']}
            self.assertEqual(fields['accepted']['value'], accepted)
            self.assertEqual(fields['reason']['value'], '' if accepted else 'Caption has 25 scalars; limit is 24.')

    def test_unicode_scalars_clamped_slice_and_no_normalization(self):
        text = 'A🌙e\u0301零'
        self.assertEqual(self.execute('length', label(text))['value'], nat(5))
        for start, count, expected in [(1, 3, '🌙e\u0301'), (3, 99, '\u0301零'),
                                        (99, 4, ''), (0, 0, ''), (0, 100, text)]:
            self.assertEqual(self.execute('preview', label(text), nat(start), nat(count))['value'], label(expected))
        self.assertEqual(self.execute('join', label('e'), label('\u0301'))['value'], label('e\u0301'))
        self.assertEqual(self.execute('decimal', nat(0))['value'], label('0'))
        self.assertEqual(self.execute('decimal', nat(10**80))['value'], label(str(10**80)))

    def test_typed_data_route_uses_the_same_text_machine(self):
        reply = call({'op': 'run-data-v1', 'artifact': self.artifacts['describe'],
                      'arguments': [label('Garden'), nat(7)]})
        self.assertEqual(reply['status'], 'finished', reply)
        self.assertEqual(reply['value'], label('Garden: 7 exhibits'))
        self.assertGreater(reply['conversionNodes'], 0)

    def test_wrong_types_and_arities_are_rejected_by_source_checker(self):
        for body in ('textConcat(1n, "x")', 'natText("x")', 'textLength(2n)',
                     'textSlice("x", "a", 1n)', 'textConcat("x")'):
            reply = call({'op': 'compile', 'source': 'edition ObjectiveBend 1\ndef bad() -> String:\n  ' + body + '\n', 'entry': 'bad'})
            self.assertNotEqual(reply.get('status'), 'compiled', reply)

    def test_source_binding_shadows_builtin(self):
        source = 'edition ObjectiveBend 1\ndef natText(n: Nat) -> String:\n  "authored"\ndef entry() -> String:\n  natText(4n)\n'
        compiled = call({'op': 'compile', 'source': source, 'entry': 'entry'})
        reply = call({'op': 'run', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertEqual(reply['value'], label('authored'))

    def test_work_and_allocation_refuse_before_primitive_construction(self):
        reply = self.execute('join', label('a' * 1000), label('b' * 1000), ticks=100)
        self.assertEqual(reply['status'], 'refused', reply)
        self.assertIn('tickExhausted', reply['failure'])
        reply = self.execute('join', label('a' * 1000), label('b' * 1000), bytes=100)
        self.assertEqual(reply['status'], 'refused', reply)
        self.assertIn('suspended', reply['failure'])
        reply = self.execute('decimal', nat(10**100), ticks=100)
        self.assertEqual(reply['status'], 'refused', reply)
        self.assertIn('tickExhausted', reply['failure'])
        self.assertEqual(self.execute('unused', ticks=100)['value'], label('quiet'))

    def test_work_is_shared_across_lazy_record_fields(self):
        source = 'edition ObjectiveBend 1\ndef entry(s: String) -> {first: String, second: String}:\n  {first: textConcat(s,s), second: textConcat(s,s)}\n'
        compiled = call({'op': 'compile', 'source': source, 'entry': 'entry'})
        reply = call({'op': 'run', 'artifact': compiled['artifact'], 'arguments': [label('x'*100)], 'limits': {'ticks': 650}})
        self.assertEqual(reply['status'], 'refused', reply)
        self.assertIn('tickExhausted', reply['failure'])
        self.assertGreater(reply['ticksUsed'], 400)


if __name__ == '__main__':
    unittest.main()
