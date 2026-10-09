#!/usr/bin/env python3
"""Readable scenario syntax preserves exact participant-authored values."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from syntaxes.spell_examples import parse, load

spec = importlib.util.spec_from_file_location('spell_examples_proposal', ROOT / 'scripts/propose.py')
proposal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proposal)

EXAMPLES = '''examples DelveTalk 1
case opens, refuses old readings and protects authority
law maker visitor
as visitor
at initial
send knock
  word: please
expect result: The paper door swings open onto a tiny lantern-lit room.
as visitor
at initial
send knock
  word: please
expect refusal: stale read root
as visitor
send knock
  word: wrong
expect refusal: precondition failed
as outsider
send knock
  word: please
  principal: maker
expect refusal: unauthorized
'''

OBSERVATION = '''observe main
  title: The paper door
  prose: A paper door with a brass knocker. Whisper please.
  offer knock -> knock: Whisper to the door
expect view
'''

SOURCE = '''edition ObjectiveBend 1
record State:
  lit: Bool
record Input:
  amount: Nat
  quiet: Bool
record Action:
  text: String
  command: String
  input: Input
record Actions:
  knock: Action
record View:
  title: String
  prose: String
  actions: Actions
def view(state: State, panel: String) -> View:
  {title: panel, prose: if state.lit then "A lantern glows." else "The room is dark.", actions: {knock: {text: "Knock", command: "knock", input: {amount: 1n, quiet: true}}}}
'''


class Examples(unittest.TestCase):
    def test_exact_unicode_and_multiline(self):
        text = '''examples DelveTalk 1
case exact
law visitor
as visitor
send knock
  word:  鬼: false\x20\x20
  source: <<END
say "moon"\nexpect refusal: this is source, not a clause

END
expect result: <<RESULT
🜉✾

RESULT
'''
        step = parse(text)[0]['steps'][0]
        self.assertEqual(step['input']['word'], ' 鬼: false  ')
        self.assertEqual(step['input']['source'], 'say "moon"\nexpect refusal: this is source, not a clause\n')
        self.assertEqual(step['result'], '🜉✾\n')
        self.assertEqual(step['root'], 'current')

    def test_scalars_are_explicitly_typed(self):
        source = '''examples DelveTalk 1
case types
law visitor
as visitor
send do
  text: false
  numbertext: 123
  n (Nat): 123
  b (Bool): false
expect result (Bool): true
'''
        step = parse(source)[0]['steps'][0]
        self.assertEqual(step['input'], {'text': 'false', 'numbertext': '123', 'n': 123, 'b': False})
        self.assertIs(step['result'], True)
        proposal.validate_scenarios(parse(source))

    def test_missing_or_duplicate_fields_refuse(self):
        for source in (EXAMPLES.replace('  word: please', '  word: please\n  word: moon', 1),
                       EXAMPLES.replace('expect refusal: unauthorized', ''),
                       EXAMPLES.replace('law maker visitor', 'law maker visitor\nlaw visitor'),
                       EXAMPLES.replace('as visitor\nat initial\nsend knock', 'send knock', 1),
                       EXAMPLES.replace('expect result:', 'expect invented:', 1)):
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse(source)

    def test_unknown_or_bad_literals_refuse(self):
        for line in ('  x (Nat): -1', '  x (Nat): 01', '  x (Bool): yes', '  x (Float): 1.0',
                     '  x (Nat): <<END', '  x: <<END'):
            source = 'examples DelveTalk 1\ncase bad\nlaw a\nas a\nsend go\n' + line + '\nexpect committed\n'
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse(source)

    def test_legacy_json_and_unknown_version(self):
        legacy = proposal.translation.canonical(parse(EXAMPLES)).decode()
        self.assertEqual(load(legacy, proposal.translation.load_json), parse(EXAMPLES))
        with self.assertRaises(ValueError):
            load(EXAMPLES.replace('DelveTalk 1', 'DelveTalk 2'), proposal.translation.load_json)

    def test_bounded_case_and_step_counts(self):
        case = 'case c{}\nlaw a\nas a\nsend go\nexpect committed\n'
        with self.assertRaises(ValueError):
            parse('examples DelveTalk 1\n' + ''.join(case.format(i) for i in range(65)))
        step = 'as a\nsend go\nexpect committed\n'
        with self.assertRaises(ValueError):
            parse('examples DelveTalk 1\ncase c\nlaw a\n' + step * 257)

    def test_view_literals_cover_labels_inputs_and_empty_offers(self):
        text = 'examples DelveTalk 1\ncase view\nlaw\n' + OBSERVATION.replace(
            'expect view', '    amount (Nat): 1\n    quiet (Bool): true\nexpect view')
        step = parse(text)[0]['steps'][0]
        self.assertEqual(step['view']['actions']['knock'], {
            'text': 'Whisper to the door', 'command': 'knock', 'input': {'amount': 1, 'quiet': True}})
        proposal.validate_scenarios(parse(text))
        empty = parse(text[:text.index('  offer')] + 'expect view\n')[0]['steps'][0]
        self.assertEqual(empty['view']['actions'], {})
        for changed in (text.replace('  title:', '  prose:', 1),
                        text.replace('  title:', '  title (Nat):', 1),
                        text.replace('observe main', 'as reader\nobserve main'),
                        text.replace('expect view', 'expect committed'),
                        text.replace('    quiet', '    amount'),
                        text.replace('    amount (Nat): 1', '  offer knock -> knock: Again')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                parse(changed)


if __name__ == '__main__': unittest.main()
