"""Source-held candidate law survives invocation, management and atomic composition."""
from pathlib import Path
import tempfile
import unittest
from test_authority import ROOT, counter, law, source_object, world


def invariant(blocked):
    return {'package': {'modules': [
        {'name': name, 'source': path.read_text()} for name, path in [
            ('List', ROOT / 'world/lib/prelude/List.obend'),
            ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
            ('Candidate', ROOT / 'conformance/fixtures/current-law/Candidate.obend')]],
        'entry': 'invariant'}, 'config': blocked}


class StateInvariant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = counter()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / 'world.json'
        self.serial = 0
        self.authority = law(invoke={'add': ['player']}, reprogram=['player'], law=['player'], invariant=invariant(3))
        made = self.call({'op': 'create', 'object': 'counter', 'protocol': self.program, 'law': self.authority})
        self.assertEqual(made['kind'], 'committed', made)
        self.initial = made['data']['root']

    def call(self, request):
        self.serial += 1
        return world.exchange(self.db, {'principal': 'player', 'intent': str(self.serial), **request}, profile='compiled')

    def root(self):
        return world.query(self.db, {'op': 'inspect', 'object': 'counter', 'principal': 'reader'})

    def test_invocation_and_reprogramming_cannot_erase_candidate_law(self):
        first = self.call({'op': 'invoke', 'object': 'counter', 'expected': self.initial,
                          'command': 'add', 'input': {'amount': 2}})
        self.assertEqual(first['kind'], 'committed', first)
        current = first['data']['root']
        requests = [
            {'op': 'invoke', 'command': 'add', 'input': {'amount': 1}},
            {'op': 'reprogram', 'protocol': self.program, 'state': {'model': source_object.data({'count': 3})}},
            {'op': 'law', 'law': {**self.authority, 'invariant': invariant(2)}}]
        for request in requests:
            with self.subTest(op=request['op']):
                refusal = self.call({'object': 'counter', 'expected': current, **request})
                self.assertEqual(refusal['kind'], 'refused', refusal)
                self.assertEqual(refusal['data'], 'source policy refused')
                self.assertEqual(self.root(), current)
        # Old law still permits an authorized removal on an allowed current state.
        authority = dict(self.authority)
        del authority['invariant']
        revised = self.call({'op': 'law', 'object': 'counter', 'expected': current, 'law': authority})
        self.assertEqual(revised['kind'], 'committed', revised)

    def test_creation_and_late_transaction_candidate_refusal_are_atomic(self):
        refused = self.call({'op': 'create', 'object': 'blocked', 'protocol': self.program,
                             'law': {**self.authority, 'invariant': invariant(0)}})
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(refused['data'], 'source policy refused')
        request = {'op': 'transaction', 'intent': 'late', 'reads': {'counter': self.initial}, 'calls': [
            {'object': 'counter', 'command': 'add', 'input': {'amount': 2}},
            {'object': 'counter', 'command': 'add', 'input': {'amount': 1}}]}
        refusal = self.call(request)
        self.assertEqual(refusal['kind'], 'refused', refusal)
        self.assertEqual(refusal['data'], 'source policy refused')
        self.assertEqual(self.call(request), refusal)
        self.assertEqual(self.root(), self.initial)
        self.assertNotIn('blocked', world.wire_loads(self.db.read_text())['objects'])


if __name__ == '__main__':
    unittest.main()
