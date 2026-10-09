"""Actual staged laws, existing grants and both law-held source guards admit revision."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import world

SOURCE = '''edition ObjectiveBend 1
import ./Preparation.obend as P
record Context:
  object: String
  principal: String
  currentLaw: P.Value
  nextLaw: P.Value
def configuration(law: P.Value) -> String:
  P.textOrEmpty(P.get(P.get(law, "amendment"), "config"))
def amend(context: Context) -> Bool:
  context.object == "counter" && (context.principal == "maker" || context.principal == "service") && configuration(context.currentLaw) == "stable" && configuration(context.nextLaw) == "stable"
def refuse(context: Context) -> Bool:
  false
def notBool(context: Context) -> Nat:
  1n
'''


def package(entry='amend'):
    return {'modules': [
        {'name': 'List', 'source': (ROOT / 'world/lib/prelude/List.obend').read_text()}, {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
        {'name': 'Amendment', 'source': SOURCE}], 'entry': entry}


def law(entry='amend'):
    return {'profile': 'delvetalk-scoped-law-v4', 'invoke': {'add': ['maker']},
            'reprogram': ['maker'], 'law': ['maker', 'service'],
            'amendment': {'profile': 'delvetalk-source-amendment-v1',
                          'package': package(entry), 'config': 'stable'}}


def program():
    return {'profile': 'delvetalk-local-v1', 'initial': {'count': 0}, 'commands': {
        'add': {'require': [], 'set': {'count': ['literal', 1]},
                'result': ['state', 'count'], 'outbox': []}}}


class SourceAmendment(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.db = Path(home.name) / 'world.json'
        self.serial = 0

    def call(self, request, profile='compiled'):
        self.serial += 1
        return world.exchange(self.db, {'principal': 'maker', 'intent': str(self.serial), **request},
                              profile=profile)

    def create(self, authority=None, profile='compiled'):
        return self.call({'op': 'create', 'object': 'counter', 'protocol': program(),
                          'law': law() if authority is None else authority}, profile)

    def root(self):
        return self.call({'op': 'inspect', 'object': 'counter'})

    def change(self, root, authority, **fields):
        return {'op': 'law', 'object': 'counter', 'expected': root,
                'law': authority, 'principal': 'service', **fields}

    def test_actual_current_and_proposed_laws_admit_change_and_receipt_retry(self):
        created = self.create()
        self.assertEqual(created['kind'], 'committed', created)
        root = created['data']['root']
        revised = copy.deepcopy(root['law'])
        revised['invoke']['add'].append('visitor')
        request = self.change(root, revised, intent='enroll')
        accepted = self.call(request)
        self.assertEqual(accepted['kind'], 'committed', accepted)
        self.assertEqual(accepted['data']['root']['law'], revised)
        denied = copy.deepcopy(revised)
        denied['amendment']['config'] = 'claimed elsewhere'
        current = accepted['data']['root']
        refusal = self.call(self.change(current, denied))
        self.assertEqual(refusal['data'], 'source amendment refused')
        self.assertEqual(self.root(), current)
        self.assertEqual(self.call(request), accepted)

    def test_existing_grants_and_staleness_precede_source_guard(self):
        root = self.create()['data']['root']
        self.assertEqual(self.call(self.change(root, root['law'], principal='stranger'))['data'], 'unauthorized')
        committed = self.call(self.change(root, root['law']))
        self.assertEqual(committed['kind'], 'committed', committed)
        self.assertEqual(self.call(self.change(root, root['law']))['data'], 'stale read root')

    def test_old_guard_cannot_be_removed_and_new_guard_checks_same_actual_change(self):
        root = self.create()['data']['root']
        without = {key: value for key, value in root['law'].items() if key != 'amendment'}
        without['profile'] = 'delvetalk-scoped-law-v1'
        refusal = self.call(self.change(root, without))
        self.assertEqual(refusal['data'], 'source amendment refused')
        refusing = law('refuse')
        refusal = self.call(self.change(root, refusing))
        self.assertEqual(refusal['data'], 'source amendment refused')
        self.assertEqual(self.root(), root)

    def test_non_boolean_or_malformed_guard_and_default_hosts_refuse_creation(self):
        refusal = self.create(law('notBool'))
        self.assertEqual(refusal['data'], 'source amendment must return Bool')
        malformed = law()
        malformed['amendment']['package']['packet'] = {}
        self.assertIn('missing or unknown fields', self.create(malformed)['data'])
        for profile in ('world', 'transactions'):
            with self.subTest(profile=profile):
                self.assertEqual(self.create(profile=profile)['data'], 'source amendments require compiled profile')

    def test_later_transaction_failure_rolls_back_law_and_command(self):
        root = self.create()['data']['root']
        revised = law()
        revised['invoke']['add'].append('service')
        forbidden = copy.deepcopy(revised)
        forbidden['amendment']['config'] = 'changed'
        request = {'op': 'transaction', 'principal': 'service', 'intent': 'batch',
                   'reads': {'counter': root}, 'calls': [
                       {'op': 'law', 'object': 'counter', 'law': revised},
                       {'object': 'counter', 'command': 'add', 'input': {}},
                       {'op': 'law', 'object': 'counter', 'law': forbidden}]}
        refused = self.call(request)
        self.assertEqual(refused['data'], 'source amendment refused')
        self.assertEqual(self.root(), root)
        self.assertEqual(self.call(request), refused)

    def test_optional_state_invariant_still_constrains_invocations(self):
        authority = law()
        authority['invariant'] = ['lam', ['binary', 'lessEqual',
            ['get', ['get', ['bound', 0], 'nextState'], 'count'], ['nat', '0']]]
        root = self.create(authority)['data']['root']
        refused = self.call({'op': 'invoke', 'object': 'counter', 'expected': root,
                             'command': 'add', 'input': {}})
        self.assertEqual(refused['data'], 'state invariant refused')
        self.assertEqual(self.root(), root)

    def test_source_contract_remains_an_independent_restriction(self):
        authority = law()
        authority['contract'] = {}
        refused = self.create(authority)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('source contract has missing or unknown fields', refused['data'])

    def test_source_permitted_management_lockout_has_no_recovery_bypass(self):
        root = self.create()['data']['root']
        locked = copy.deepcopy(root['law'])
        locked['law'] = []
        request = self.change(root, locked, intent='lock')
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        current = receipt['data']['root']
        denied = self.call(self.change(current, root['law'], principal='maker'))
        self.assertEqual(denied['data'], 'unauthorized')
        self.assertEqual(self.call(request), receipt)


if __name__ == '__main__':
    unittest.main()
