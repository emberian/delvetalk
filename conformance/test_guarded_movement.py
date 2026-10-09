#!/usr/bin/env python3
"""Authenticated prior-call data gates existing commons movement, not authority."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


commons = module('guarded_commons', 'protocols/commons/generate.py')
world = module('guarded_world', 'scripts/world.py')
SOURCE = (ROOT / 'protocols/commons/garden-gate.obend').read_text()
GATE = {'from': 'porch', 'to': 'garden', 'object': 'door', 'command': 'cross'}


def door_protocol(source=SOURCE):
    transition = {'transition': {'profile': 'delvetalk-source-transition-v1',
        'package': {'modules': [{'name': 'Main', 'source': source}], 'entry': 'cross'}}}
    return {'profile': 'delvetalk-local-v1', 'initial': {'approvals': 0},
            'commands': {'cross': transition, 'echo': copy.deepcopy(transition)}}


def door_law(visitors=('moss', 'iris')):
    return {'profile': 'delvetalk-scoped-law-v1',
            'invoke': {'cross': list(visitors), 'echo': list(visitors)},
            'reprogram': ['maker'], 'law': ['maker']}


class GuardedMovement(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / '.lake/build/bin/delvetalk-compiled').is_file(), 'prebuilt compiled host required')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'world.json'
        self.serial = 0
        self.create('commons', commons.build(gates=[GATE]), commons.law())
        self.create('door', door_protocol(), door_law())
        self.create('other', door_protocol(), door_law())
        self.invoke('commons', 'enter', {'place': 'porch'})

    def identity(self):
        self.serial += 1
        return 'request-' + str(self.serial)

    def call(self, request):
        return world.exchange(self.db, request, profile='compiled')

    def root(self, object_id):
        return self.call({'op': 'inspect', 'object': object_id, 'principal': 'reader'})

    def create(self, object_id, protocol, law):
        reply = self.call({'op': 'create', 'object': object_id, 'principal': 'operator',
            'intent': self.identity(), 'protocol': protocol, 'law': law})
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply['data']['root']

    def invoke(self, object_id, command, data, principal='moss', kind='committed'):
        reply = self.call({'op': 'invoke', 'object': object_id, 'principal': principal,
            'intent': self.identity(), 'expected': self.root(object_id), 'command': command, 'input': data})
        self.assertEqual(reply['kind'], kind, reply)
        return reply

    def transaction(self, calls=None, word='please', principal='moss'):
        calls = calls or [{'object': 'door', 'command': 'cross', 'input': {'word': word}},
                          {'object': 'commons', 'command': 'move', 'inputFrom': 0}]
        return {'op': 'transaction', 'principal': principal, 'intent': self.identity(),
                'reads': {call['object']: self.root(call['object']) for call in calls}, 'calls': calls}

    def assert_refused_unchanged(self, request):
        before = {obj: self.root(obj) for obj in request['reads']}
        reply = self.call(request)
        self.assertEqual(reply['kind'], 'refused', reply)
        self.assertEqual({obj: self.root(obj) for obj in before}, before)
        return reply

    def test_real_source_door_controls_existing_location_and_return_is_ungated(self):
        self.assert_refused_unchanged(self.transaction(word='wrong'))
        reply = self.call(self.transaction())
        self.assertEqual(reply['kind'], 'committed', reply)
        self.assertEqual(reply['data']['results'][0]['description'], 'The paper door opens onto the shared garden.')
        self.assertEqual(self.root('commons')['state']['locations']['moss'], 'garden')
        self.assertEqual(self.root('door')['state']['approvals'], 1)
        self.invoke('commons', 'move', {'place': 'porch'})
        self.assertEqual(self.root('commons')['state']['locations']['moss'], 'porch')
        self.invoke('commons', 'move', {'place': 'garden'}, kind='refused')

    def test_explicit_input_cannot_forge_an_origin_even_after_successful_door(self):
        forged = {'place': 'garden', 'inputOrigin': {'present': True, 'object': 'door',
            'command': 'cross', 'immediatelyPrevious': True}, 'principal': 'maker'}
        self.invoke('commons', 'move', forged, kind='refused')
        self.assert_refused_unchanged(self.transaction(calls=[
            {'object': 'door', 'command': 'cross', 'input': {'word': 'please'}},
            {'object': 'commons', 'command': 'move', 'input': forged}]))

    def test_same_data_from_other_object_or_command_is_not_the_gate(self):
        for object_id, command in [('other', 'cross'), ('door', 'echo')]:
            with self.subTest(object=object_id, command=command):
                self.assert_refused_unchanged(self.transaction(calls=[
                    {'object': object_id, 'command': command, 'input': {'word': 'please'}},
                    {'object': 'commons', 'command': 'move', 'inputFrom': 0}]))

    def test_old_result_and_reuse_are_not_immediate_predecessors(self):
        self.assert_refused_unchanged(self.transaction(calls=[
            {'object': 'door', 'command': 'cross', 'input': {'word': 'please'}},
            {'object': 'other', 'command': 'cross', 'input': {'word': 'please'}},
            {'object': 'commons', 'command': 'move', 'inputFrom': 0}]))
        self.assert_refused_unchanged(self.transaction(calls=[
            {'object': 'door', 'command': 'cross', 'input': {'word': 'please'}},
            {'object': 'commons', 'command': 'move', 'inputFrom': 0},
            {'object': 'commons', 'command': 'move', 'input': {'place': 'porch'}},
            {'object': 'commons', 'command': 'move', 'inputFrom': 0}]))
        # A fresh admission at the same door really can authorize the next crossing.
        reply = self.call(self.transaction(calls=[
            {'object': 'door', 'command': 'cross', 'input': {'word': 'please'}},
            {'object': 'commons', 'command': 'move', 'inputFrom': 0},
            {'object': 'commons', 'command': 'move', 'input': {'place': 'porch'}},
            {'object': 'door', 'command': 'cross', 'input': {'word': 'please'}},
            {'object': 'commons', 'command': 'move', 'inputFrom': 3}]))
        self.assertEqual(reply['kind'], 'committed', reply)
        self.assertEqual(self.root('door')['state']['approvals'], 2)

    def test_late_failure_rolls_back_door_and_movement(self):
        self.assert_refused_unchanged(self.transaction(calls=[
            {'object': 'door', 'command': 'cross', 'input': {'word': 'please'}},
            {'object': 'commons', 'command': 'move', 'inputFrom': 0},
            {'object': 'commons', 'command': 'move', 'input': {'place': 'tower'}}]))

    def test_each_current_law_still_checks_the_global_visitor(self):
        self.invoke('commons', 'enter', {'place': 'porch'}, principal='iris')
        gate = self.root('door')
        reply = self.call({'op': 'law', 'object': 'door', 'principal': 'maker', 'intent': self.identity(),
            'expected': gate, 'law': door_law(['moss'])})
        self.assertEqual(reply['kind'], 'committed')
        self.assert_refused_unchanged(self.transaction(principal='iris'))
        current = self.root('commons')
        law = copy.deepcopy(current['law'])
        law['invoke']['move'] = ['iris']
        self.assertEqual(self.call({'op': 'law', 'object': 'commons', 'principal': 'steward',
            'intent': self.identity(), 'expected': current, 'law': law})['kind'], 'committed')
        self.assert_refused_unchanged(self.transaction())

    def test_source_revision_changes_crossing_without_reprogramming_commons(self):
        original = self.root('commons')
        current = self.root('door')
        source = SOURCE.replace('password: "please"', 'password: "moon"')
        reply = self.call({'op': 'reprogram', 'object': 'door', 'principal': 'maker',
            'intent': self.identity(), 'expected': current, 'protocol': door_protocol(source),
            'state': current['state']})
        self.assertEqual(reply['kind'], 'committed', reply)
        self.assertEqual(self.root('commons'), original)
        self.assert_refused_unchanged(self.transaction(word='please'))
        self.assertEqual(self.call(self.transaction(word='moon'))['kind'], 'committed')

    def test_exact_retry_survives_revocation_but_stale_new_attempt_refuses(self):
        request = self.transaction()
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        changed = copy.deepcopy(request)
        changed['intent'] = self.identity()
        self.assertEqual(self.call(changed)['kind'], 'refused')
        gate = self.root('door')
        revoked = door_law([])
        self.assertEqual(self.call({'op': 'law', 'object': 'door', 'principal': 'maker',
            'intent': self.identity(), 'expected': gate, 'law': revoked})['kind'], 'committed')
        self.assertEqual(self.call(request), receipt)
        self.assertEqual(self.root('door')['state']['approvals'], 1)

    def test_gate_configuration_rejects_unknown_duplicate_and_foreign_metadata(self):
        for gates in [[{**GATE, 'to': 'missing'}], [GATE, GATE],
                      [{**GATE, 'authority': ['moss']}], [{**GATE, 'object': ''}]]:
            with self.assertRaises(ValueError):
                commons.build(gates=gates)
        # Existing default source remains byte-equivalent when no gates are authored.
        self.assertEqual(commons.build(), json.loads((ROOT / 'protocols/commons/protocol.json').read_text()))

    def test_origin_is_host_context_not_stored_input_and_older_data_remains_usable(self):
        self.create('probe', {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
            'observe': {'require': [], 'set': {}, 'result': ['input-origin'], 'outbox': []}}}, ['moss'])
        default = {'present': False, 'object': '', 'command': '', 'immediatelyPrevious': False}
        forged = {'present': True, 'object': 'door', 'command': 'cross', 'immediatelyPrevious': True}
        reply = self.invoke('probe', 'observe', forged)
        self.assertEqual(reply['data']['result'], default)
        reply = self.call(self.transaction(calls=[
            {'object': 'door', 'command': 'cross', 'input': {'word': 'please'}},
            {'object': 'probe', 'command': 'observe', 'inputFrom': 0},
            {'object': 'probe', 'command': 'observe', 'inputFrom': 0},
            {'object': 'probe', 'command': 'observe', 'input': forged}]))
        self.assertEqual(reply['kind'], 'committed', reply)
        self.assertEqual(reply['data']['results'][1], forged)
        self.assertEqual(reply['data']['results'][2], {**forged, 'immediatelyPrevious': False})
        self.assertEqual(reply['data']['results'][3], default)


if __name__ == '__main__':
    unittest.main()
