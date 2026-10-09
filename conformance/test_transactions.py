"""Atomic composition of current source methods and current management law."""
import concurrent.futures
import copy
from pathlib import Path
import tempfile
import unittest
from test_authority import counter, law, source_object, world


class Transactions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = counter()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / 'world.json'
        self.serial = 0
        self.roots = {}
        for name in ['a', 'b']:
            made = self.call({'op': 'create', 'object': name, 'protocol': self.program,
                             'law': law(invoke={'add': ['player']}, reprogram=['player'], law=['player'])})
            self.assertEqual(made['kind'], 'committed', made)
            self.roots[name] = made['data']['root']

    def call(self, request):
        self.serial += 1
        return world.exchange(self.db, {'principal': 'player', 'intent': str(self.serial), **request}, profile='compiled')

    def root(self, name):
        return world.query(self.db, {'op': 'inspect', 'object': name, 'principal': 'reader'})

    def turn(self, **changes):
        return {'op': 'transaction', 'reads': self.roots, 'calls': [
            {'object': 'a', 'command': 'add', 'input': {'amount': 3}},
            {'object': 'b', 'command': 'add', 'input': {'amount': 4}}], **changes}

    def assert_unchanged(self):
        self.assertEqual({name: self.root(name) for name in self.roots}, self.roots)

    def test_multiobject_commit_exact_retry_and_retained_stale_refusal(self):
        request = self.turn(intent='both')
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        for name, amount in [('a', 3), ('b', 4)]:
            self.assertEqual(self.root(name)['state'], {'model': source_object.data({'count': amount})})
        self.assertEqual(self.call(request), receipt)
        refusal = self.call({**request, 'intent': 'stale'})
        self.assertEqual(refusal['kind'], 'refused', refusal)
        self.assertEqual(self.call({**request, 'intent': 'stale'}), refusal)
        self.assertEqual(self.call({**request, 'calls': []})['data'], 'intent reused for different request')

    def test_repeated_object_observes_staged_state_and_versions(self):
        receipt = self.call(self.turn(calls=[{'object': 'a', 'command': 'add', 'input': {'amount': 2}},
                                           {'object': 'a', 'command': 'add', 'input': {'amount': 3}}]))
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(self.root('a')['state'], {'model': source_object.data({'count': 5})})
        self.assertEqual(self.root('a')['version'], self.roots['a']['version'] + 2)
        self.assertEqual(self.root('b'), self.roots['b'])

    def test_late_input_or_authority_refusal_rolls_back_prior_source_effects(self):
        for input in [{}, {'amount': 'wrong'}]:
            with self.subTest(input=input):
                refusal = self.call(self.turn(calls=[{'object': 'a', 'command': 'add', 'input': {'amount': 3}},
                    {'object': 'b', 'command': 'add', 'input': input}]))
                self.assertEqual(refusal['kind'], 'refused', refusal)
                self.assert_unchanged()
        calls = self.turn()['calls']
        refusal = self.call(self.turn(calls=[calls[0], {'op': 'law', 'object': 'b', 'law': law(invoke={})}, calls[1]]))
        self.assertEqual(refusal['kind'], 'refused', refusal)
        self.assert_unchanged()

    def test_staged_law_grants_and_programming_preserves_it(self):
        authority = law(invoke={'add': ['guest']}, reprogram=['guest'], law=['player'])
        receipt = self.call(self.turn(calls=[{'op': 'law', 'object': 'a', 'law': authority}]))
        self.assertEqual(receipt['kind'], 'committed', receipt)
        roots = {**self.roots, 'a': self.root('a')}
        receipt = self.call(self.turn(principal='guest', reads=roots, calls=[
            {'op': 'reprogram', 'object': 'a', 'protocol': self.program,
             'state': {'model': source_object.data({'count': 9})}},
            {'object': 'a', 'command': 'add', 'input': {'amount': 1}}]))
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(self.root('a')['law'], authority)
        self.assertEqual(self.root('a')['state'], {'model': source_object.data({'count': 10})})

    def test_missing_reads_forward_results_and_authority_overrides_refuse(self):
        variants = [self.turn(reads={'a': self.roots['a']}),
                    self.turn(calls=[{'object': 'a', 'command': 'add', 'inputFrom': 1}]),
                    self.turn(calls=[{'object': 'a', 'command': 'add', 'input': {'amount': 1}, 'principal': 'guest'}])]
        for request in variants:
            with self.subTest(request=request):
                self.assertEqual(self.call(request)['kind'], 'refused')
                self.assert_unchanged()

    def test_racing_source_transactions_have_one_winner(self):
        # Exchange always uses a separate native receiver process and file custody.
        requests = [{**self.turn(), 'intent': 'race-' + str(n), 'principal': 'player'} for n in range(8)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda request: world.exchange(self.db, request, profile='compiled'), requests))
        self.assertEqual(sum(reply['kind'] == 'committed' for reply in replies), 1)
        for name, amount in [('a', 3), ('b', 4)]:
            self.assertEqual(self.root(name)['state'], {'model': source_object.data({'count': amount})})


if __name__ == '__main__':
    unittest.main()
