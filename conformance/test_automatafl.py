"""Actual pinned Obend gameplay through the generic compiler/demand executable."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'game/automatafl'
spec = importlib.util.spec_from_file_location('automatafl_bridge', HERE / 'bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def load(name):
    return json.loads((HERE / name).read_text())


class AutomataflTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jobs = {j['id']: j for j in load('jobs.json')}
        cls.cases = {j['id']: j for j in load('cases.json')}
        cls.play = load('play.package.json')
        cls.valid = load('board-valid.package.json')
        artifacts = {'play': load('raw-play.package.json'), 'automaton': load('automaton.package.json')}
        jobs = [{'op': 'run', 'artifact': artifacts[j['entry']],
                 'arguments': [{'tag': 'natural', 'value': str(n)} for n in j['arguments']],
                 'limits': {'ticks': 100000}} for j in cls.jobs.values()]
        process = subprocess.run([str(bridge.BINARY)], input=''.join(json.dumps(j) + '\n' for j in jobs),
                                 text=True, capture_output=True, timeout=90, check=True)
        replies = [json.loads(line) for line in process.stdout.splitlines()]
        assert len(replies) == len(jobs)
        cls.results = dict(zip(cls.jobs, replies))

    def execute(self, artifact, arguments, limits=None):
        reply = bridge.run(artifact, arguments, limits)
        self.assertEqual(reply['status'], 'finished', reply)
        return bridge.data(reply['value'])

    def test_full_original_corpus_and_recorded_reference_differences(self):
        historical = {r['id']: r for r in map(json.loads, (HERE / 'reference-bend.jsonl').read_text().splitlines())}
        rust = {r['id']: r['result'] for r in map(json.loads, (HERE / 'reference-rust.jsonl').read_text().splitlines())}
        differences = []
        for name, reply in self.results.items():
            with self.subTest(case=name):
                self.assertEqual(reply['status'], 'finished', reply)
                self.assertEqual(reply['value'], historical[name]['result'])
                self.assertLessEqual(reply['ticksUsed'], 100000)
                value = bridge.data(reply['value'])
                case = self.cases[name]
                if case['kind'] == 'automaton':
                    actual, reference = value, rust[name]['a']
                else:
                    cells = bridge.unpack(value['board'], case['w'] * case['h'])
                    marks = [i for i, bit in enumerate(bridge.unpack(value['marks'], len(cells), 2)) if bit]
                    self.assertEqual(cells.count(3), 1)
                    self.assertEqual(cells[value['automaton']], 3)
                    self.assertEqual(cells.count(1), case['cells'].count(1))
                    self.assertEqual(cells.count(2), case['cells'].count(2))
                    actual = {'cells': cells, 'a': value['automaton'], 'marks': marks,
                              'status': value['status'], 'winner': value['winner']}
                    if value['status'] == 2:
                        actual, reference = {'rejected': True}, {'rejected': rust[name].get('rejected', False)}
                    else:
                        reference = {key: rust[name][key] for key in actual}
                    if value['status'] == 1:
                        self.assertEqual(cells, case['cells'])
                if actual != reference:
                    differences.append(name)
        self.assertEqual(len(self.results), 353)
        self.assertEqual(differences, [d['id'] for d in load('reference-report.json')['differences']])
        self.assertEqual(len(differences), 10)
        for index in range(80):
            self.assertEqual(self.results[f'random-{index}']['value'],
                             self.results[f'random-{index}-swapped']['value'])

    def test_validated_wrapper_preserves_representative_game_behaviors(self):
        for name in ['independent', 'fork', 'vacuum-fork', 'collision', 'stationary-destination',
                     'failed-source-still-blocks', 'conflict-mark-refused', 'win-top', 'win-bottom']:
            with self.subTest(case=name):
                self.assertEqual(self.execute(self.play, self.jobs[name]['arguments']),
                                 bridge.data(self.results[name]['value']))

    def test_terminal_wins_are_preserved_on_next_round(self):
        for name, winner in [('win-top', 1), ('win-bottom', 2)]:
            original = [int(n) for n in self.jobs[name]['arguments']]
            first = self.execute(self.play, original)
            self.assertEqual((first['status'], first['winner']), (0, winner))
            second = self.execute(self.play, original[:2] + [first['board'], first['automaton'], first['marks']] + original[5:])
            self.assertEqual(second, {**first, 'status': 3})

    def test_board_representation_validation_runs_in_obend(self):
        args = [int(n) for n in self.jobs['independent']['arguments']]
        self.assertTrue(self.execute(self.valid, args[:5]))
        invalid = []
        for position, value in [(0, 0), (0, 1), (1, 10), (2, 0), (2, args[2] + 3*4**1),
                                (2, args[2] + 4**25), (3, 25), (3, 11), (4, 2**25)]:
            changed = list(args)
            changed[position] = value
            invalid.append(changed)
        for changed in invalid:
            with self.subTest(arguments=changed):
                self.assertFalse(self.execute(self.valid, changed[:5]))
                result = self.execute(self.play, changed)
                self.assertEqual(result, {'board': changed[2], 'automaton': changed[3],
                                         'marks': changed[4], 'status': 2, 'winner': 0})

    def test_nine_by_nine_and_exact_tick_boundary(self):
        args = [9, 9, 3*4**40 + 1 + 2*4**8, 40, 0, 0, 9, 8, 17]
        reply = bridge.run(self.play, args, {'ticks': 100000})
        self.assertEqual(reply['status'], 'finished', reply)
        self.assertEqual(bridge.data(reply['value'])['status'], 0)
        cost = reply['ticksUsed']
        self.assertGreater(cost, 10000)
        self.assertEqual(bridge.run(self.play, args, {'ticks': cost})['value'], reply['value'])
        refused = bridge.run(self.play, args, {'ticks': cost - 1})
        self.assertEqual(refused['status'], 'refused')
        self.assertEqual(refused['ticksUsed'], cost - 1)
        self.assertNotIn('value', refused)

    def test_checked_in_artifacts_reproduce_from_source(self):
        for name, entry, validated in [('play', 'play', True), ('raw-play', 'play', False),
                                      ('board-valid', 'boardValid', True), ('automaton', 'automaton', False)]:
            with self.subTest(artifact=name):
                self.assertEqual(bridge.export(entry, validated), load(name + '.package.json'))


if __name__ == '__main__':
    unittest.main()
