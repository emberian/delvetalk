#!/usr/bin/env python3
"""Receiving invariants guard real candidate writes, independently of programs."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


world = module('invariant_world', 'scripts/world.py')
source = module('invariant_source', 'conformance/test_source_transition.py')
allocation = module('invariant_allocation', 'conformance/test_allocation.py')
C = ['bound', 0]


def get(*keys):
    value = C
    for key in keys:
        value = ['get', value, key]
    return value


def eq(left, right):
    return ['binary', 'labelEqual', left, ['label', right]]


def conjunction(*values):
    result = ['boolean', True]
    for value in reversed(values):
        result = ['binary', 'conjunction', value, result]
    return result


def bound(maximum=3):
    return ['lam', ['binary', 'lessEqual', get('nextState', 'count'), ['nat', str(maximum)]]]


def on_invoke(body):
    return ['lam', ['ifBool', eq(get('op'), 'invoke'), body, ['boolean', True]]]


def law(invariant=None, **changes):
    return {'profile': 'delvetalk-scoped-law-v2', 'invoke': {'add': ['player']},
            'reprogram': ['programmer'], 'law': ['steward'],
            'invariant': bound() if invariant is None else invariant, **changes}


def protocol(count=0):
    return {'profile': 'delvetalk-local-v1', 'initial': {'count': count}, 'commands': {
        'add': {'require': [], 'set': {'count': ['bend',
            ['lam', ['lam', ['binary', 'add', ['bound', 1], ['bound', 0]]]],
            [['state', 'count'], ['input', 'amount']]]},
            'result': ['record', {'amount': ['input', 'amount']}], 'outbox': [['literal', 'added']]}}}


class StateInvariant(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.serial = 0
        self.profile = 'world'
        self.db = Path(self.tmp.name) / 'world.json'

    def call(self, request):
        self.serial += 1
        return world.exchange(self.db, {'principal': 'player', 'intent': str(self.serial), **request},
                              profile=self.profile)

    def seed(self, profile='world', authority=None, program=None):
        self.profile = profile
        self.db = Path(self.tmp.name) / (profile + '-' + str(self.serial) + '.json')
        made = self.call({'op': 'create', 'object': 'counter', 'principal': 'creator',
                         'protocol': protocol() if program is None else program,
                         'law': law() if authority is None else authority})
        self.assertEqual(made['kind'], 'committed', made)
        return made['data']['root']

    def root(self, identity='counter'):
        return self.call({'op': 'inspect', 'object': identity})

    def objects(self):
        return world.wire_loads(self.db.read_text())['objects']

    def invoke(self, expected, amount=2, **changes):
        return {'op': 'invoke', 'object': 'counter', 'expected': expected,
                'command': 'add', 'input': {'amount': amount}, **changes}

    def revise(self, expected, authority):
        return self.call({'op': 'law', 'object': 'counter', 'principal': 'steward',
                          'expected': expected, 'law': authority})

    def test_legacy_and_source_bodies_cannot_exceed_installed_law(self):
        for profile in ('world', 'transactions', 'compiled'):
            with self.subTest(profile=profile):
                root = self.seed(profile)
                first = self.call(self.invoke(root))
                self.assertEqual(first['kind'], 'committed', first)
                current = first['data']['root']
                refused = self.call(self.invoke(current))
                self.assertEqual(refused['data'], 'state invariant refused')
                self.assertEqual(self.root(), current)
                self.assertIsInstance(refused['data'], str)  # result/outbox never escape
        root = self.seed('compiled', law(invoke={'water': ['player']}), source.protocol())
        refused = self.call(self.invoke(root, 4, command='water'))
        self.assertEqual(refused['data'], 'state invariant refused')
        self.assertEqual(self.root(), root)
        self.assertEqual(self.call(self.invoke(root, 3, command='water'))['kind'], 'committed')

    def test_staged_states_resolved_input_and_receiving_identity(self):
        predicate = on_invoke(conjunction(
            eq(get('object'), 'counter'), eq(get('principal'), 'player'), eq(get('command'), 'add'),
            ['binary', 'equal', get('nextState', 'count'),
             ['binary', 'add', get('state', 'count'), get('input', 'amount')]],
            ['binary', 'lessEqual', get('nextState', 'count'), ['nat', '3']]))
        root = self.seed('transactions', law(predicate))
        request = {'op': 'transaction', 'reads': {'counter': root}, 'calls': [
            {'object': 'counter', 'command': 'add', 'input': {'amount': 2}},
            {'object': 'counter', 'command': 'add', 'inputFrom': 0}]}
        self.assertEqual(self.call(request)['data'], 'state invariant refused')
        self.assertEqual(self.root(), root)
        request['calls'][0]['input']['amount'] = 1
        accepted = self.call(request)
        self.assertEqual(accepted['kind'], 'committed', accepted)
        self.assertEqual(self.root()['state'], {'count': 2})
        self.assertEqual(self.call(self.invoke(self.root(), principal='outsider',
            input={'amount': 0, 'principal': 'player'}))['data'], 'unauthorized')

    def test_reprogram_and_atomic_desk_adoption_use_existing_invariant(self):
        root = self.seed('transactions')
        replacement = protocol()
        replacement['commands']['add']['set'] = {'count': ['literal', 99]}
        direct = {'op': 'reprogram', 'object': 'counter', 'principal': 'programmer',
                  'expected': root, 'protocol': replacement, 'state': {'count': 99}}
        self.assertEqual(self.call(direct)['data'], 'state invariant refused')
        self.assertEqual(self.root(), root)
        candidate = {'protocol': replacement, 'state': {'count': 99}}
        self.assertEqual(self.call({'op': 'transaction', 'principal': 'programmer',
            'reads': {'counter': root}, 'calls': [
                {'op': 'reprogram', 'object': 'counter', **candidate}]})['data'], 'state invariant refused')
        self.assertEqual(self.root(), root)
        desk_program = {'profile': 'delvetalk-local-v1', 'initial': {'adopted': False}, 'commands': {
            'adopt': {'require': [], 'set': {'adopted': ['literal', True]},
                      'result': ['literal', candidate], 'outbox': [['literal', 'adopted']]}}}
        desk = self.call({'op': 'create', 'object': 'desk', 'protocol': desk_program,
                          'law': ['programmer']})['data']['root']
        adoption = {'op': 'transaction', 'principal': 'programmer',
                    'reads': {'counter': root, 'desk': desk}, 'calls': [
                        {'object': 'desk', 'command': 'adopt', 'input': {}},
                        {'op': 'reprogram', 'object': 'counter', 'inputFrom': 0}]}
        self.assertEqual(self.call(adoption)['data'], 'state invariant refused')
        self.assertEqual(self.root('desk'), desk)
        self.assertEqual(self.root(), root)
        # Accepting valid state does not certify future command compatibility.
        programmed = self.call({**direct, 'state': {'count': 1}})
        self.assertEqual(programmed['kind'], 'committed', programmed)
        self.assertEqual(programmed['data']['root']['law'], root['law'])
        self.assertEqual(self.call(self.invoke(self.root(), 0))['data'], 'state invariant refused')

    def test_law_revision_requires_old_and_new_and_can_deliberately_remove(self):
        root = self.seed(program=protocol(2))
        self.assertEqual(self.revise(root, law(bound(1)))['data'], 'state invariant refused')
        self.assertEqual(self.root(), root)
        locked = law(['lam', ['ifBool', eq(get('op'), 'law'), ['boolean', False], ['boolean', True]]])
        refused = self.revise(root, locked)
        self.assertEqual(refused['data'], 'state invariant refused')  # proposed law must also pass
        locked_root = self.seed(authority=locked)
        permissive = law()
        permissive.pop('invariant')
        permissive['profile'] = 'delvetalk-scoped-law-v1'
        self.assertEqual(self.revise(locked_root, permissive)['data'], 'state invariant refused')
        root = self.seed(program=protocol(2))
        revised = self.revise(root, permissive)
        self.assertEqual(revised['kind'], 'committed', revised)
        self.assertEqual(self.call(self.invoke(self.root(), 99))['kind'], 'committed')

    def test_create_and_factory_child_check_initial_state_and_actual_context(self):
        for profile in ('world', 'transactions', 'compiled'):
            root = self.seed(profile)
            before = self.objects()
            rejected = self.call({'op': 'create', 'object': 'invalid', 'protocol': protocol(4), 'law': law()})
            self.assertEqual(rejected['data'], 'state invariant refused')
            self.assertEqual(self.objects(), before)
            initial_guard = ['lam', conjunction(eq(get('object'), 'factory/one'),
                eq(get('principal'), 'alice'), eq(get('op'), 'create'), eq(get('command'), ''),
                ['binary', 'equal', get('state', 'count'), get('nextState', 'count')],
                ['binary', 'lessEqual', get('nextState', 'count'), ['nat', '3']])]
            for count in (4, 2):
                factory = allocation.factory_protocol(child=protocol(count), child_law=law(initial_guard))
                identity = 'factory' if count == 4 else 'good'
                if count == 2:
                    factory['commands']['make']['allocate'][0]['law'][1]['invariant'] = ['lam', conjunction(
                        eq(get('object'), 'good/one'), eq(get('principal'), 'alice'),
                        eq(get('op'), 'create'), eq(get('command'), ''),
                        ['binary', 'equal', get('state', 'count'), get('nextState', 'count')])]
                parent = self.call({'op': 'create', 'object': identity, 'protocol': factory,
                                    'law': allocation.factory_law()})['data']['root']
                before = self.objects()
                reply = self.call({'op': 'invoke', 'object': identity, 'principal': 'alice',
                    'expected': parent, 'command': 'make', 'input': {'name': 'one'}, 'absent': [identity + '/one']})
                self.assertEqual(reply['kind'], 'refused' if count == 4 else 'committed', reply)
                if count == 4:
                    self.assertEqual(reply['data'], 'state invariant refused')
                    self.assertEqual(self.objects(), before)
                else:
                    self.assertEqual(reply['data']['allocated']['good/one']['state'], {'count': 2})

    def test_false_wrong_kind_stuck_effect_and_divergence_refuse_atomically(self):
        omega = ['lam', ['app', ['bound', 0], ['bound', 0]]]
        cases = [(['boolean', False], 'state invariant refused'),
                 (['nat', '1'], 'state invariant must return Bool'),
                 (['bound', 9], 'Bend expression stuck'),
                 (['perform', ['label', 'escape']], 'Bend effects are forbidden'),
                 (['app', omega, omega], 'invocation budget exhausted')]
        for body, message in cases:
            root = self.seed(authority=law(on_invoke(body)))
            request = self.invoke(root, intent='exact-attempt')
            refusal = self.call(request)
            self.assertEqual(refusal['kind'], 'refused', refusal)
            self.assertIn(message, refusal['data'])
            self.assertEqual(self.root(), root)
            self.assertEqual(self.call(request), refusal)
        root = self.seed(authority=law(['lam', ['boolean', True]]))
        self.assertEqual(self.call(self.invoke(root, input={'amount': 1, 'unused': []}))['kind'], 'refused')
        self.assertEqual(self.root(), root)

    def test_invariant_and_authority_and_calls_share_one_budget(self):
        burn = ['fix', ['lam', ['lam', ['lam', ['ifZero', ['bound', 0], ['boolean', True],
                ['app', ['bound', 3], ['bound', 0]]]]]], ['record', []]]
        body = ['app', burn, ['nat', '1000']]
        root = self.seed('transactions', law(on_invoke(body)))
        first = self.call(self.invoke(root, 0))
        self.assertEqual(first['kind'], 'committed', first)
        current = self.root()
        request = {'op': 'transaction', 'reads': {'counter': current}, 'calls': [
            {'object': 'counter', 'command': 'add', 'input': {'amount': 0}},
            {'object': 'counter', 'command': 'add', 'input': {'amount': 0}}]}
        self.assertEqual(self.call(request)['data'], 'invocation budget exhausted')
        self.assertEqual(self.root(), current)
        root = self.seed(authority=law(on_invoke(body), predicate=['lam', body]))
        self.assertEqual(self.call(self.invoke(root, 0))['data'], 'invocation budget exhausted')
        self.assertEqual(self.root(), root)

    def test_profile_validation_and_historical_receipts_survive_law_removal(self):
        root = self.seed()
        for invalid in [law() | {'profile': 'delvetalk-scoped-law-v1'},
                        {k: v for k, v in law().items() if k != 'invariant'},
                        law(invariant=['not-a-term'])]:
            self.assertEqual(self.revise(root, invalid)['kind'], 'refused')
            self.assertEqual(self.root(), root)
        request = self.invoke(root, 4, intent='old-refusal')
        refusal = self.call(request)
        accepted_request = self.invoke(root, 1, intent='old-success')
        accepted = self.call(accepted_request)
        old = law()
        old.pop('invariant')
        old['profile'] = 'delvetalk-scoped-law-v1'
        self.assertEqual(self.revise(self.root(), old)['kind'], 'committed')
        self.assertEqual(self.call(request), refusal)
        self.assertEqual(self.call(accepted_request), accepted)
        self.assertEqual(self.call({**request, 'input': {'amount': 1}})['data'], 'intent reused for different request')
        self.assertEqual(self.call(self.invoke(self.root(), 4))['kind'], 'committed')


if __name__ == '__main__':
    unittest.main()
