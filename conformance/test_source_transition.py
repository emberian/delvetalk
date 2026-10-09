#!/usr/bin/env python3
"""Source-owned state transitions on the actual compiled receiving host."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


world = module('source_transition_world', 'scripts/world.py')
adapters = module('source_transition_adapters', 'syntaxes/adapters.py')


def source(body=None, *, state='count: Nat', result='Nat', extra='', helpers=''):
    body = body or ('{accepted: input.amount <= 10n, reason: if input.amount <= 10n then "" else "too much rain", '
                    'state: {count: state.count + input.amount}, result: state.count + input.amount}')
    return ('edition ObjectiveBend 1\nrecord State:\n  ' + state + '\n'
        'record Input:\n  amount: Nat\nrecord Context:\n  object: String\n  principal: String\n'
        'record Decision:\n  accepted: Bool\n  reason: String\n  state: State\n  result: ' + result + '\n' +
        extra + helpers + 'def turn(state: State, input: Input, context: Context) -> Decision:\n  ' + body + '\n')


def protocol(text=None, initial=None):
    return {'profile': 'delvetalk-local-v1', 'initial': initial or {'count': 0}, 'commands': {
        'water': {'transition': {'profile': 'delvetalk-source-transition-v1',
            'package': {'modules': [{'name': 'Garden', 'source': text or source()}], 'entry': 'turn'}}}}}


class SourceTransition(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'world.json'

    def call(self, request, profile='compiled'):
        return world.exchange(self.db, request, profile=profile)

    def create(self, candidate=None, *, name='garden', profile='compiled'):
        candidate = candidate or protocol()
        adapters.protocol_shape(candidate)
        return self.call({'op': 'create', 'object': name, 'principal': 'owner',
            'intent': 'create-' + name, 'protocol': candidate, 'law': ['owner', 'visitor']}, profile)

    def inspect(self, name='garden'):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def request(self, root, amount=2, *, intent='water', principal='visitor', name='garden'):
        return {'op': 'invoke', 'object': name, 'principal': principal, 'intent': intent,
                'expected': root, 'command': 'water', 'input': {'amount': amount}}

    def test_success_refusal_replay_and_stale_roots(self):
        made = self.create()
        self.assertEqual(made['kind'], 'committed', made)
        root = made['data']['root']
        request = self.request(root)
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['root']['state'], {'count': 2})
        self.assertEqual(receipt['data']['result'], 2)
        self.assertEqual(receipt['data']['outbox'], [])
        self.assertEqual(receipt['data']['root']['version'], 1)
        self.assertEqual(self.call(request), receipt)
        stale = self.call(self.request(root, intent='different-turn'))
        self.assertEqual(stale['data'], 'stale read root')
        current = self.inspect()
        declined_request = self.request(current, 99, intent='decline')
        declined = self.call(declined_request)
        self.assertEqual((declined['kind'], declined['data']), ('refused', 'source refused: too much rain'))
        self.assertEqual(self.inspect(), current)
        self.assertEqual(self.call(declined_request), declined)

    def test_receiving_identity_and_current_law_are_not_input_claims(self):
        text = source('{accepted: true, reason: "", state: state, result: context}', result='Context')
        text = text.replace('  amount: Nat\n', '  amount: Nat\n  object: String\n  principal: String\n')
        root = self.create(protocol(text))['data']['root']
        request = self.request(root)
        request['input'].update(object='other', principal='owner')
        receipt = self.call(request)
        self.assertEqual(receipt['data']['result'], {'object': 'garden', 'principal': 'visitor'})
        current = self.inspect()
        revised = self.call({'op': 'law', 'object': 'garden', 'principal': 'owner',
            'intent': 'restrict', 'expected': current, 'law': ['owner']})['data']['root']
        request = self.request(revised, intent='now-denied')
        request['input'].update(object='other', principal='owner')
        self.assertEqual(self.call(request)['data'], 'unauthorized')
        self.assertEqual(self.inspect(), revised)

    def test_typed_input_and_success_record_envelope_fail_closed(self):
        root = self.create()['data']['root']
        for bad in (True, 'two', -1, None, []):
            receipt = self.call(self.request(root, bad, intent='bad-' + repr(bad)))
            self.assertEqual(receipt['kind'], 'refused', receipt)
            self.assertEqual(self.inspect(), root)
        cases = [
            ('{accepted: true, reason: "ambiguous", state: state, result: 0n}', '', 'empty reason'),
            ('{accepted: false, reason: "", state: state, result: 0n}', '', 'requires a reason'),
            ('{accepted: true, reason: "", state: state, result: 0n, extra: 1n}', '  extra: Nat\n', 'requires exactly'),
        ]
        for index, (body, extra, message) in enumerate(cases):
            name = 'bad-envelope-' + str(index)
            installed = self.create(protocol(source(body, extra=extra)), name=name)
            self.assertEqual(installed['kind'], 'committed', installed)
            snapshot = installed['data']['root']
            refused = self.call(self.request(snapshot, name=name, intent=name))
            self.assertEqual(refused['kind'], 'refused', refused)
            self.assertIn(message, refused['data'])
            self.assertEqual(self.inspect(name), snapshot)
        nonrecord = source('{accepted: true, reason: "", state: 0n, result: 0n}').replace('  state: State\n', '  state: Nat\n')
        snapshot = self.create(protocol(nonrecord), name='nonrecord')['data']['root']
        self.assertEqual(self.call(self.request(snapshot, name='nonrecord'))['kind'], 'refused')
        self.assertEqual(self.inspect('nonrecord'), snapshot)

    def test_whole_state_replacement_is_not_a_patch_or_a_permanent_type_invariant(self):
        text = source('{accepted: true, reason: "", state: {count: state.count + input.amount}, result: 0n}',
                      state='count: Nat\n  obsolete: String')
        text = text.replace('record Decision:', 'record Next:\n  count: Nat\nrecord Decision:')
        text = text.replace('  state: State\n', '  state: Next\n')
        root = self.create(protocol(text, {'count': 0, 'obsolete': 'removed'}))['data']['root']
        receipt = self.call(self.request(root))
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['root']['state'], {'count': 2})
        # Source chose a different output row. A later call needs a compatible
        # input type; the host does not invent a permanent object-state theorem.
        current = self.inspect()
        self.assertEqual(self.call(self.request(current, intent='incompatible-next'))['kind'], 'refused')
        self.assertEqual(self.inspect(), current)

    def test_opt_in_and_source_only_installation(self):
        for profile in ('world', 'transactions'):
            refused = self.create(name=profile, profile=profile)
            self.assertEqual((refused['kind'], refused['data']),
                             ('refused', 'source transitions require compiled profile'))
        for index, mutation in enumerate(('outbox', 'allocate', 'packet', 'limits', 'invalid')):
            candidate = protocol()
            command = candidate['commands']['water']
            package = command['transition']['package']
            if mutation in ('outbox', 'allocate'):
                command[mutation] = []
            elif mutation == 'packet':
                package['packet'] = {}
            elif mutation == 'limits':
                package['limits'] = {'ticks': '999999999'}
            else:
                package['modules'][0]['source'] = 'invalid Objective Bend'
            # Call Lean directly: structural Python preflight grants nothing.
            refused = self.call({'op': 'create', 'object': mutation, 'principal': 'owner',
                'intent': 'bad-install-' + str(index), 'protocol': candidate, 'law': ['owner']})
            self.assertEqual(refused['kind'], 'refused', refused)

    def test_legacy_commands_keep_prestate_evaluation_and_inert_metadata(self):
        candidate = {'profile': 'delvetalk-local-v1', 'initial': {'count': 3}, 'commands': {
            'water': {'require': [], 'set': {'count': ['literal', 8]}, 'result': ['state', 'count'],
                      'outbox': [['literal', 'legacy']], 'transition': {'note': 'inert metadata'}}}}
        root = self.create(candidate)['data']['root']
        receipt = self.call(self.request(root))
        self.assertEqual(receipt['data']['root']['state'], {'count': 8})
        self.assertEqual(receipt['data']['result'], 3)
        self.assertEqual(receipt['data']['outbox'], ['legacy'])

    def test_late_transaction_refusal_rolls_back_prior_effects(self):
        first = self.create(name='first')['data']['root']
        second = self.create(name='second')['data']['root']
        request = {'op': 'transaction', 'principal': 'visitor', 'intent': 'atomic-refusal',
            'reads': {'first': first, 'second': second}, 'calls': [
                {'object': 'first', 'command': 'water', 'input': {'amount': 3}},
                {'object': 'second', 'command': 'water', 'input': {'amount': 99}}]}
        receipt = self.call(request)
        self.assertEqual(receipt['data'], 'source refused: too much rain')
        self.assertEqual(self.inspect('first'), first)
        self.assertEqual(self.inspect('second'), second)
        self.assertEqual(self.call(request), receipt)

    def test_one_source_invocation_shared_budget_and_eager_refusal_payload(self):
        helper = 'def loop(n: Nat) -> Nat:\n  if n == 0n then 0n else loop(n - 1n)\n'
        body = 'let value = loop(input.amount) in {accepted: true, reason: "", state: {count: value}, result: value}'
        candidate = protocol(source(body, helpers=helper))
        root = self.create(candidate)['data']['root']
        once = self.call(self.request(root, 3000))
        self.assertEqual(once['kind'], 'committed', once)
        current = self.inspect()
        twice = {'op': 'transaction', 'principal': 'visitor', 'intent': 'shared-budget',
            'reads': {'garden': current}, 'calls': [
                {'object': 'garden', 'command': 'water', 'input': {'amount': 3000}},
                {'object': 'garden', 'command': 'water', 'input': {'amount': 3000}}]}
        refused = self.call(twice)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('tickExhausted', refused['data'])
        self.assertEqual(self.inspect(), current)
        eager = source('{accepted: false, reason: "no", state: state, result: loop(input.amount)}', helpers=helper)
        snapshot = self.create(protocol(eager), name='eager')['data']['root']
        refused = self.call(self.request(snapshot, 10000, name='eager', intent='eager-refusal'))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('tickExhausted', refused['data'])
        self.assertEqual(self.inspect('eager'), snapshot)


if __name__ == '__main__':
    unittest.main()
