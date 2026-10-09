#!/usr/bin/env python3
"""Readable authored cases still run through the existing Lean fixture runner."""
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
    def test_actual_lean_admission(self):
        self.assertTrue((ROOT / '.lake/build/bin/delvetalk-world').exists(), 'build the world host first')
        protocol = {'profile': 'delvetalk-local-v1', 'name': 'examples-test', 'initial': {},
                    'commands': {'knock': {'require': [[["input", "word"], ["literal", "please"]]],
                                           'set': {}, 'result': ['literal', 'The paper door swings open onto a tiny lantern-lit room.'],
                                           'outbox': []}}}
        report = proposal.propose('protocol-json@1', proposal.translation.canonical(protocol),
                                  EXAMPLES.encode(), profile='world')
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['candidate']['scenarios']['source'], EXAMPLES)
        self.assertEqual([step['receipt']['kind'] for step in report['outcomes'][0]['steps']],
                         ['committed', 'refused', 'refused', 'refused'])

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

    def source_protocol(self, source=SOURCE):
        return {'profile': 'delvetalk-local-v1', 'initial': {'lit': False},
                'commands': {'knock': {'require': [], 'set': {'lit': ['literal', True]},
                                      'result': ['literal', 'Welcome'], 'outbox': []}},
                'viewProgram': {'profile': 'delvetalk-obend-view-v1', 'package': {
                    'modules': [{'name': 'Main', 'source': source}], 'entry': 'view'}}}

    def observe(self, prose='The room is dark.', panel='main'):
        return {'observe': panel, 'view': {'title': panel, 'prose': prose, 'actions': {
            'knock': {'text': 'Knock', 'command': 'knock', 'input': {'amount': 1, 'quiet': True}}}}}

    def run_views(self, steps, protocol=None, law=None):
        return proposal.propose('protocol-json@1', proposal.translation.canonical(protocol or self.source_protocol()),
            proposal.translation.canonical([{'name': 'interface', 'law': law or [], 'steps': steps}]), profile='compiled')

    def test_actual_source_view_observes_current_state_without_grant_or_write(self):
        steps = [self.observe(), {'principal': 'visitor', 'command': 'knock', 'input': {},
                                 'root': 'initial', 'kind': 'committed', 'result': 'Welcome'},
                 self.observe('A lantern glows.', 'details'),
                 {'principal': 'outsider', 'command': 'knock', 'input': {},
                  'root': 'current', 'kind': 'refused', 'error': 'unauthorized'},
                 self.observe('A lantern glows.')]
        report = self.run_views(steps, law=['visitor'])
        self.assertTrue(report['passed'], report['outcomes'])
        observed = report['outcomes'][0]['steps']
        self.assertEqual([observed[i]['view']['root']['version'] for i in (0, 2, 4)], [0, 1, 1])
        self.assertIn('scene/projection.py', report['execution']['files'])
        self.assertEqual(observed[2]['view']['runtimeProfile']['profile'], 'compiled')
        pure = self.run_views([self.observe()])
        self.assertTrue(pure['passed'], pure['outcomes'])
        self.assertEqual(pure['outcomes'][0]['steps'][0]['view']['root']['law'], [])

    def test_exact_view_mismatch_including_bool_nat_and_extra_offer_fails(self):
        originals = [self.observe() for _ in range(5)]
        originals[0]['view']['title'] = 'Untrue title'
        originals[1]['view']['actions']['knock']['text'] = 'Wrong label'
        originals[2]['view']['actions']['knock']['input']['amount'] = True
        originals[3]['view']['actions']['knock']['command'] = 'other'
        originals[4]['view']['actions'] = {}
        report = self.run_views(originals)
        self.assertFalse(report['passed'])
        self.assertEqual(len(report['outcomes'][0]['failures']), 5)
        self.assertTrue(all(item['field'] == 'view' for item in report['outcomes'][0]['failures']))

    def test_failed_projection_is_a_failed_scenario_not_an_absent_assertion(self):
        absent = self.source_protocol()
        absent.pop('viewProgram')
        wrong_command = self.source_protocol(SOURCE.replace('command: "knock"', 'command: "missing"'))
        exhausted = self.source_protocol(SOURCE.replace('def view(',
            'def loop(n: Nat) -> String:\n  if n == 0n then "done" else loop(n - 1n)\ndef view(').replace(
            'title: panel', 'title: loop(10000n)'))
        for protocol in (absent, wrong_command, exhausted):
            with self.subTest(protocol=protocol):
                report = self.run_views([self.observe()], protocol=protocol)
                outcome = report['outcomes'][0]
                self.assertFalse(report['passed'])
                self.assertEqual(outcome['installation']['kind'], 'committed')
                self.assertIn('viewError', outcome['steps'][0])
                self.assertEqual(outcome['failures'][0]['field'], 'view')
        with self.assertRaisesRegex(ValueError, 'compiled profile'):
            proposal.run_scenarios(self.source_protocol(), [{'name': 'wrong host', 'law': [],
                                  'steps': [self.observe()]}], profile='world')

    def test_desk_requires_behavior_and_interface_before_readiness(self):
        desk = proposal.module('view_examples_desk', 'scripts/desk.py')
        source = (ROOT / 'syntaxes/examples/paper-door.obend').read_bytes()
        examples = EXAMPLES.replace('as visitor\nat initial\nsend knock',
                                    OBSERVATION + '\nas visitor\nat initial\nsend knock', 1)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            worker = desk.Desk(folder / 'world.json', folder / 'artifacts', profile='compiled')
            for name, fixture, status in (('good', examples, 'ready'),
                                         ('bad', examples.replace('title: The paper door', 'title: Untrue'), 'failed')):
                candidate = worker.create(name, 'maker', 'create-' + name, ['maker'])['data']['root']
                pending = worker.submit(name, 'maker', 'submit-' + name, candidate,
                    'objective-bend-spell@1', source, fixture.encode(), {}, 'door')['data']['root']
                checked = worker.check(name, 'maker', 'check-' + name, pending)
                self.assertEqual(checked['kind'], 'committed', checked)
                state = checked['data']['root']['state']
                self.assertEqual(state['status'], status, state)
                artifact = desk.load_artifact(folder / 'artifacts', state['artifact'])
                self.assertEqual(artifact['passed'], status == 'ready', artifact)
                failures = artifact['report']['outcomes'][0]['failures']
                self.assertEqual([item['field'] for item in failures], [] if status == 'ready' else ['view'])


if __name__ == '__main__':
    unittest.main()
