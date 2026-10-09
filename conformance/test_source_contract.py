#!/usr/bin/env python3
"""Law-held source specification bounds constrain actual receiving programs."""
import copy
from native_support import load_script
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
world = load_script(ROOT / 'scripts/world.py', 'source_contract_world')
SOURCE = (ROOT / 'protocols/source-contract/Counter.obend').read_text()


def package(source=SOURCE, entry='add'):
    return {'modules': [{'name': 'Contract', 'source': source}], 'entry': entry}


def native(request):
    result = subprocess.run([str(ROOT / '.lake/build/bin/delvetalk-obend')],
                            input=json.dumps(request) + '\n', text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def protocol(source=SOURCE):
    return {'profile': 'delvetalk-local-v1', 'initial': {'count': 0}, 'commands': {
        'add': {'transition': {'profile': 'delvetalk-source-transition-v1', 'package': package(source)}}}}


def invariant(maximum):
    return ['lam', ['binary', 'lessEqual', ['get', ['get', ['bound', 0], 'nextState'], 'count'],
                    ['nat', str(maximum)]]]


class SourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiled = native({'op': 'compile', **package(entry='contractMetadata')})
        if compiled.get('status') != 'compiled':
            raise AssertionError(compiled)
        observed = native({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
        if observed.get('status') != 'finished':
            raise AssertionError(observed)
        cls.metadata = observed['value']

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'world.json'
        self.serial = 0

    def law(self, **changes):
        return {'profile': 'delvetalk-scoped-law-v3',
                'invoke': {'add': ['visitor']}, 'reprogram': ['maker'], 'law': ['steward'],
                'contract': {'profile': 'delvetalk-source-contract-v1',
                             'package': package(entry='contract'), 'stateProfile': 'plain',
                             'metadata': copy.deepcopy(self.metadata)}, **changes}

    def call(self, request):
        self.serial += 1
        return world.exchange(self.db, {'principal': 'visitor', 'intent': f'contract-{self.serial}', **request},
                              profile='compiled')

    def create(self, program=None, authority=None, name='counter'):
        return self.call({'op': 'create', 'object': name, 'principal': 'creator',
                          'protocol': protocol() if program is None else program,
                          'law': self.law() if authority is None else authority})

    def inspect(self, name='counter'):
        return self.call({'op': 'inspect', 'object': name})

    def invoke(self, root, amount=1, **changes):
        return {'op': 'invoke', 'object': 'counter', 'expected': root,
                'command': 'add', 'input': {'amount': amount}, **changes}

    def replace(self, root, program, **changes):
        return {'op': 'reprogram', 'object': 'counter', 'principal': 'maker', 'expected': root,
                'protocol': program, 'state': root['state'], **changes}

    def test_actual_spec_metadata_survives_application_and_compatible_replacement(self):
        root = self.create()['data']['root']
        first = self.call(self.invoke(root, 2))
        self.assertEqual(first['kind'], 'committed', first)
        root = first['data']['root']
        revised = protocol(SOURCE.replace('state.count + input.amount', 'state.count + input.amount + 1n'))
        result = self.call(self.replace(root, revised))
        self.assertEqual(result['kind'], 'committed', result)
        root = result['data']['root']
        self.assertEqual(root['law']['contract']['metadata'], self.metadata)
        second = self.call(self.invoke(root))
        self.assertEqual(second['kind'], 'committed', second)
        self.assertEqual(second['data']['root']['state'], {'count': 4})
        # The source claim is retained as a claim; matching interfaces do not
        # entail behavioral equivalence or prove the claim of this replacement.
        self.assertIn('unchecked', json.dumps(root['law']['contract']['metadata']))

    def test_state_preserving_replacement_cannot_drop_or_change_required_method(self):
        root = self.create()['data']['root']
        absent = protocol()
        absent['commands'] = {}
        changed = protocol(SOURCE.replace('  amount: Nat', '  amount: String')
                           .replace('state.count + input.amount', 'state.count'))
        legacy = protocol()
        legacy['commands']['add'] = {'require': [], 'set': {}, 'outbox': [], 'result': ['literal', 0]}
        for program, reason in ((absent, 'missing method'), (changed, 'signature mismatch'),
                                (legacy, 'requires source method')):
            with self.subTest(reason=reason):
                result = self.call(self.replace(root, program))
                self.assertEqual(result['kind'], 'refused', result)
                self.assertIn(reason, result['data'])
                self.assertEqual(self.inspect(), root)
        extra = protocol()
        extra['commands']['another'] = copy.deepcopy(extra['commands']['add'])
        accepted = self.call(self.replace(root, extra))
        self.assertEqual(accepted['kind'], 'committed', accepted)

    def test_metadata_source_and_state_profile_are_not_caller_assertions(self):
        for change, reason in (({'metadata': {'tag': 'boolean', 'value': True}}, 'metadata differs'),
                               ({'stateProfile': 'model'}, 'state profile mismatch'),
                               ({'package': package(entry='add')}, 'must be a Specification')):
            authority = self.law()
            authority['contract'].update(change)
            program = protocol()
            if change.get('stateProfile') == 'model':
                program['initial'] = {'model': {'tag': 'record', 'fields': [
                    {'name': 'count', 'value': {'tag': 'natural', 'value': '0'}}]}}
            result = self.create(program=program, authority=authority, name=f'bad-{self.serial}')
            self.assertEqual(result['kind'], 'refused', result)
            self.assertIn(reason, result['data'])
        authority = self.law()
        authority['contract']['package']['packet'] = {}
        result = self.create(authority=authority)
        self.assertEqual(result['kind'], 'refused', result)

    def test_state_invariant_and_interface_bounds_have_distinct_obligations(self):
        root = self.create(authority=self.law(invariant=invariant(3)))['data']['root']
        refused = self.call(self.invoke(root, 4))
        self.assertEqual(refused['data'], 'state invariant refused')
        self.assertEqual(self.inspect(), root)
        # The same state passes an invariant but the changed input signature does not.
        wrong = protocol(SOURCE.replace('  amount: Nat', '  amount: String')
                         .replace('state.count + input.amount', 'state.count'))
        rejected = self.call(self.replace(root, wrong))
        self.assertEqual(rejected['kind'], 'refused', rejected)
        self.assertIn('signature mismatch', rejected['data'])

    def test_current_law_revision_and_replay(self):
        root = self.create()['data']['root']
        request = self.invoke(root, intent='one-knock')
        original = self.call(request)
        root = original['data']['root']
        bad = self.law()
        bad['contract']['metadata'] = {'tag': 'boolean', 'value': True}
        refusal = self.call({'op': 'law', 'object': 'counter', 'principal': 'steward',
                             'expected': root, 'law': bad})
        self.assertEqual(refusal['kind'], 'refused', refusal)
        self.assertEqual(self.inspect(), root)
        unauthorized = self.call({'op': 'law', 'object': 'counter', 'principal': 'maker',
                                  'expected': root, 'law': ['maker']})
        self.assertEqual(unauthorized['data'], 'unauthorized')
        # Authorized law evolution is explicit; no invariant or contract grants
        # an owner a hidden override. Historical successful attempts remain exact.
        revised = self.call({'op': 'law', 'object': 'counter', 'principal': 'steward',
                             'expected': root, 'law': []})
        self.assertEqual(revised['kind'], 'committed', revised)
        self.assertEqual(self.call(request), original)
        self.assertEqual(self.inspect(), revised['data']['root'])

    def test_late_contract_failure_rolls_back_previous_transaction_call(self):
        root = self.create()['data']['root']
        absent = protocol()
        absent['commands'] = {}
        # Give one explicit actor both permissions; no authority flows from the first call.
        authority = self.law(invoke={'add': ['maker']})
        root = self.call({'op': 'law', 'object': 'counter', 'principal': 'steward',
                          'expected': root, 'law': authority})['data']['root']
        result = self.call({'op': 'transaction', 'object': 'counter', 'principal': 'maker',
                           'reads': {'counter': root}, 'calls': [
                               {'object': 'counter', 'command': 'add', 'input': {'amount': 1}},
                               {'op': 'reprogram', 'object': 'counter', 'protocol': absent,
                                'state': {'count': 1}}]})
        self.assertEqual(result['kind'], 'refused', result)
        self.assertIn('missing method', result['data'])
        self.assertEqual(self.inspect(), root)

    def test_every_write_preserves_declared_state_even_from_extra_legacy_methods(self):
        program = protocol()
        program['commands']['damage'] = {'require': [], 'set': {'count': ['literal', 'broken']},
                                         'outbox': [], 'result': ['literal', 0]}
        authority = self.law(invoke={'add': ['visitor'], 'damage': ['visitor']})
        made = self.create(program=program, authority=authority)
        self.assertEqual(made['kind'], 'committed', made)
        root = made['data']['root']
        rejected = self.call(self.invoke(root, command='damage', input={}))
        self.assertEqual(rejected['kind'], 'refused', rejected)
        self.assertIn('declared type', rejected['data'])
        self.assertEqual(self.inspect(), root)
        bad_initial = protocol()
        bad_initial['initial'] = {'count': 'broken'}
        refused = self.create(program=bad_initial, name='wrong-state')
        self.assertEqual(refused['kind'], 'refused', refused)

    def test_recursive_model_schema_uses_own_packet_aliases_and_unselected_payloads(self):
        typed = SOURCE.replace('record State:\n  count: Nat',
            'sum Items:\n  nil: {}\n  cons: {head: Nat, tail: Items}\nrecord State:\n  items: Items')
        typed = typed.replace('record Context:\n  object: String\n  principal: String',
            'record Origin:\n  kind: String\n  object: String\n  command: String\n'
            '  immediatelyPrevious: Bool\nrecord Context:\n  object: String\n  principal: String\n'
            '  inputOrigin: Origin')
        typed = typed.replace('{count: state.count + input.amount}', 'state')
        typed = typed.replace('state.count + input.amount', '0n').replace('state.count', '0n')
        observed = native({'op': 'compile', **package(typed, 'contractMetadata')})
        self.assertEqual(observed['status'], 'compiled', observed)
        metadata = native({'op': 'run-data-v1', 'artifact': observed['artifact'], 'arguments': []})['value']
        authority = self.law()
        authority['contract'].update(package=package(typed, 'contract'), stateProfile='model', metadata=metadata)
        model = {'tag': 'record', 'fields': [{'name': 'items', 'value': {
            'tag': 'variant', 'label': 'nil', 'payload': {'tag': 'record', 'fields': []}}}]}
        program = protocol(typed)
        program['initial'] = {'model': model}
        program['commands']['add']['transition']['profile'] = 'delvetalk-source-data-transition-v1'
        made = self.create(program, authority)
        self.assertEqual(made['kind'], 'committed', made)
        root = made['data']['root']
        # Independent source aliases are interpreted in their own checked packet.
        independent = typed.replace('sum Items:', 'sum Unrelated:\n  unit: {}\nsum Items:')
        independent += '\ndef unrelated() -> Unrelated:\n  Unrelated.unit()\n'
        replacement = copy.deepcopy(program)
        replacement['commands']['add']['transition']['package'] = package(independent)
        revised = self.call(self.replace(root, replacement))
        self.assertEqual(revised['kind'], 'committed', revised)
        root = revised['data']['root']
        changed = copy.deepcopy(replacement)
        changed['commands']['add']['transition']['package'] = package(independent.replace('head: Nat', 'head: String'))
        refused = self.call(self.replace(root, changed))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('signature mismatch', refused['data'])
        self.assertEqual(self.inspect(), root)

    def test_allocated_child_contract_failure_rolls_back_parent(self):
        child = protocol()
        child['initial'] = {'count': 'broken'}
        factory = {'profile': 'delvetalk-local-v1', 'initial': {'made': False},
                   'allocation': {'limit': 2}, 'commands': {'make': {
                       'require': [], 'set': {'made': ['literal', True]},
                       'result': ['literal', 1], 'outbox': [['literal', 'created']],
                       'allocate': [{'name': ['literal', 'child'], 'protocol': ['literal', child],
                                     'law': ['literal', self.law()]}]}}}
        made = self.create(factory, ['visitor'], 'factory')
        self.assertEqual(made['kind'], 'committed', made)
        root = made['data']['root']
        refused = self.call({'op': 'invoke', 'object': 'factory', 'expected': root,
                             'command': 'make', 'input': {}, 'absent': ['factory/child']})
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('declared type', refused['data'])
        self.assertEqual(self.inspect('factory'), root)
        self.assertNotIn('factory/child', world.wire_loads(self.db.read_text())['objects'])

    def test_other_native_profiles_cannot_silently_ignore_a_source_contract(self):
        plain = {'profile': 'delvetalk-local-v1', 'initial': {'count': 0}, 'commands': {}}
        for host in ('world', 'transactions'):
            result = world.exchange(Path(self.tmp.name) / (host + '.json'),
                {'op': 'create', 'object': 'counter', 'principal': 'creator', 'intent': 'create',
                 'protocol': plain, 'law': self.law()}, profile=host)
            self.assertEqual(result['kind'], 'refused', result)
            self.assertIn('source contracts require compiled profile', result['data'])

    def test_delivery_cannot_commit_a_receive_method_that_breaks_contract_state(self):
        # The raw source profile allows a Decision with a different state row.
        # The law's input-state schema must still protect the delivered write.
        text = SOURCE.replace('record Decision:',
            'record Next:\n  count: String\nrecord Event:\n  id: String\n  source: String\n'
            '  sourceProgram: String\n  originatingPrincipal: String\nrecord Decision:')
        text = text.replace('  state: State', '  state: Next').replace('  amount: Nat', '  chord: String')
        text = text.replace('context: Context)', 'context: Context, event: Event)')
        text = text.replace('add(', 'hear(')
        text = text.replace('state: state', 'state: {count: "broken"}')
        text = text.replace('state: {count: state.count + input.amount}', 'state: {count: "broken"}')
        text = text.replace('state.count + input.amount', 'state.count')
        text = text.replace('record Context:\n  object: String\n  principal: String',
            'record Origin:\n  kind: String\n  object: String\n  command: String\n'
            '  immediatelyPrevious: Bool\nrecord Context:\n  object: String\n  principal: String\n'
            '  inputOrigin: Origin')
        compiled = native({'op': 'compile', **package(text, 'contractMetadata')})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        metadata = native({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})['value']
        authority = self.law(invoke={'hear': ['relay']})
        authority['contract'].update(package=package(text, 'contract'), metadata=metadata)
        door = protocol()
        door['commands'] = {'hear': {'transition': {'profile': 'delvetalk-source-receive-v1',
                                                  'package': package(text, 'hear')}}}
        self.assertEqual(self.call({'op': 'messages-init', 'principal': 'bootstrap',
                                    'lineage': 'contract-test', 'pendingLimit': 16})['kind'], 'committed')
        made = self.create(door, authority, 'door')
        self.assertEqual(made['kind'], 'committed', made)
        door_root = made['data']['root']
        from conformance.test_resident_messages import source_protocol
        bell = source_protocol('Bell')
        bell_root = self.create(bell, ['visitor'], 'bell')['data']['root']
        hasher = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'hash': {
            'require': [], 'set': {}, 'outbox': [], 'result': ['program-digest', ['input', 'program']]}}}
        hash_root = self.create(hasher, ['visitor'], 'hash')['data']['root']
        digest = self.call({'op': 'invoke', 'object': 'hash', 'expected': hash_root, 'command': 'hash',
                            'input': {'program': door}})['data']['result']
        emitted = self.call({'op': 'invoke', 'object': 'bell', 'expected': bell_root, 'command': 'play',
                            'input': {'to': 'door', 'recipientProgram': digest, 'chord': 'C E G', 'voices': 1}})
        self.assertEqual(emitted['kind'], 'committed', emitted)
        event = emitted['data']['messages'][0]
        request = {'op': 'deliver', 'object': 'door', 'principal': 'relay', 'intent': 'delivery',
                   'expected': door_root, 'event': event}
        refused = self.call(request)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('declared type', refused['data'])
        self.assertEqual(self.inspect('door'), door_root)
        snapshot = world.wire_loads(self.db.read_text())
        self.assertEqual(snapshot['messages']['events'][event['id']]['status'], 'pending')
        self.assertEqual(self.call(request), refused)

    def test_shared_package_selector_does_not_escape_the_candidate(self):
        program = protocol()
        program['sourcePackages'] = {'local': {'format': 'delvetalk-source-package-table-v1',
                                              'modules': package()['modules']}}
        program['commands']['add']['transition']['package'] = {
            'format': 'delvetalk-source-package-ref-v1', 'name': 'local', 'entry': 'add'}
        made = self.create(program=program)
        self.assertEqual(made['kind'], 'committed', made)
        root = made['data']['root']
        altered = copy.deepcopy(program)
        altered['sourcePackages']['local']['modules'][0]['source'] = SOURCE.replace(
            '  amount: Nat', '  amount: String').replace('state.count + input.amount', 'state.count')
        refused = self.call(self.replace(root, altered))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('signature mismatch', refused['data'])


if __name__ == '__main__':
    unittest.main()
