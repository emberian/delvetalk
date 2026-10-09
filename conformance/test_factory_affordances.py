#!/usr/bin/env python3
"""Declared factory forms compose with actual Lean allocation and durable retry."""
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


a = module('factory_affordances', 'scripts/affordances.py')
world = module('factory_world', 'scripts/world.py')
room = module('factory_room', 'scene/room.py')


def factory(name='object'):
    return json.loads((ROOT / 'protocols/factories' / (name + '.json')).read_text())


class FactoryAffordanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'world.json'
        self.profile = 'world'

    def call(self, request):
        return world.exchange(self.db, request, profile=self.profile)

    def seed(self, protocol=None):
        receipt = self.call({'op': 'create', 'object': 'workshop', 'principal': 'operator',
            'intent': 'seed', 'protocol': factory() if protocol is None else protocol,
            'law': {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'make': ['maker']},
                    'law': ['manager'], 'reprogram': ['manager']}})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        return {'mode': 'raw', 'object': 'workshop', 'root': receipt['data']['root']}

    def inspect(self, object_id='workshop'):
        return self.call({'op': 'inspect', 'object': object_id, 'principal': 'reader'})

    def prepare(self, view, name='lamp', intent='make', principal='maker', **fields):
        return a.request(view, 'a1', principal, intent, {'name': name, **fields})

    def test_declared_absence_allocates_and_child_is_immediately_usable(self):
        for profile in ('world', 'transactions', 'compiled'):
            with self.subTest(profile=profile):
                self.profile = profile
                self.db = Path(self.tmp.name) / (profile + '.json')
                view = self.seed()
                action = a.card(view)['actions'][0]
                self.assertEqual(action['children'], [{'field': 'name'}])
                request = self.prepare(view, 'lamp_A-9')
                self.assertEqual(request['absent'], ['workshop/lamp_A-9'])
                self.assertEqual(request['expected'], view['root'])
                receipt = self.call(request)
                self.assertEqual(receipt['kind'], 'committed', receipt)
                refs = a.allocated_refs(receipt)
                self.assertEqual(refs, [{'object': 'workshop/lamp_A-9', 'root': self.inspect('workshop/lamp_A-9')}])
                child_view = room.inspect_object(refs[0]['root'], refs[0]['object'])
                self.assertEqual(child_view['mode'], 'projection')
                self.assertEqual(a.card(child_view)['prose'], '')
                write = a.request(child_view, 'a1', 'maker', 'write', {'text': 'A light for visitors.'})
                self.assertEqual(self.call(write)['kind'], 'committed')
                reading = room.inspect_object(self.inspect(refs[0]['object']), refs[0]['object'])
                displayed = a.card(reading)
                self.assertEqual(displayed['prose'], 'A light for visitors.')
                self.assertEqual(displayed['actions'][0]['command'], 'write')
                self.assertEqual(displayed['actions'][0]['fields'][0]['name'], 'text')
                self.assertEqual(refs[0]['root']['version'], 0)
                refs[0]['root']['state']['text'] = 'not an alias'
                self.assertEqual(receipt['data']['allocated']['workshop/lamp_A-9']['state']['text'], '')

    def test_bounded_names_and_metadata_are_checked_without_reading_or_inference(self):
        view = self.seed()
        action = a.card(view)['actions'][0]
        for name in ('', 'a/b', '..', '../escape', 'é', 'x' * 65, 'a b', '\ud800'):
            with self.subTest(name=repr(name)):
                with self.assertRaises(a.AffordanceError): a.validate_fields(action, {'name': name})
                with self.assertRaises(a.AffordanceError): self.prepare(view, name)
        for children in ([], ['missing'], ['name', 'name'], 'name', [True]):
            changed = copy.deepcopy(view)
            changed['root']['protocol']['affordances']['make']['children'] = children
            with self.assertRaises(a.AffordanceError): a.card(changed)
        for bounds in ({'type': 'bool'}, {'type': 'string', 'maxLength': 64},
                       {'type': 'string', 'minLength': 1, 'maxLength': 65}):
            changed = copy.deepcopy(view)
            changed['root']['protocol']['affordances']['make']['fields']['name'] = bounds
            with self.assertRaises(a.AffordanceError): a.card(changed)
        del view['root']['protocol']['affordances']['make']['children']
        # Even a transparent allocation expression does not authorize guessing.
        self.assertNotIn('absent', self.prepare(view))

    def test_projection_bound_child_name_is_explicit_and_cannot_be_overridden(self):
        view = self.seed()
        view.update(format='delvetalk-projection-view-v1', mode='projection', data={'title': 'Workshop', 'prose': '', 'actions': {
            'fixed': {'text': 'Make the fixed lamp', 'command': 'make', 'input': {'name': 'fixed'}}}})
        self.assertEqual(a.card(view)['actions'][0]['children'], [{'field': 'name', 'value': 'fixed'}])
        self.assertEqual(a.card(view)['actions'][0]['fields'], [])
        request = a.request(view, 'a1', 'maker', 'fixed')
        self.assertEqual(request['absent'], ['workshop/fixed'])
        self.assertEqual(self.call(request)['kind'], 'committed')
        with self.assertRaises(a.AffordanceError): self.prepare(view, 'override')

    def test_stale_absence_quota_current_law_and_exact_restart_retry(self):
        protocol = factory(); protocol['allocation']['limit'] = 1
        view = self.seed(protocol)
        request = self.prepare(view)
        self.assertEqual(self.call(self.prepare(view, principal='operator', intent='unauthorized'))['data'], 'unauthorized')
        receipt = self.call(request)
        current = {**view, 'root': receipt['data']['root']}
        collision = self.call(self.prepare(current, intent='collision'))
        self.assertEqual(collision['data'], 'stale absence root')
        self.assertEqual(a.allocated_refs(collision), [])
        self.assertEqual(self.call(self.prepare(current, 'second', 'quota'))['data'], 'factory child quota exhausted')
        self.assertEqual(self.call(self.prepare(view, 'second', 'stale'))['data'], 'stale read root')
        self.call({'op': 'law', 'object': 'workshop', 'principal': 'manager', 'intent': 'lock',
                   'expected': current['root'], 'law': []})
        # exchange starts a new host each time; no helper-local replay cache.
        self.assertEqual(self.call(request), receipt)
        changed = copy.deepcopy(request); changed['absent'].append('workshop/other')
        self.assertEqual(self.call(changed)['data'], 'intent reused for different request')

    def test_false_declaration_and_late_collision_roll_back_all_children(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                self.db = Path(self.tmp.name) / str(duplicate)
                protocol = factory()
                descriptor = protocol['commands']['make']['allocate'][0]
                if duplicate:
                    protocol['commands']['make']['allocate'].append(copy.deepcopy(descriptor))
                else:
                    descriptor['name'] = ['literal', 'undeclared']
                view = self.seed(protocol)
                request = self.prepare(view)
                receipt = self.call(request)
                self.assertEqual(receipt['data'], 'object exists' if duplicate else 'allocation target missing absence root')
                self.assertEqual(self.inspect(), view['root'])
                self.assertEqual(set(world.wire_loads(self.db.read_text())['objects']), {'workshop'})
                self.assertEqual(a.allocated_refs(receipt), [])
                self.assertEqual(self.call(request), receipt)

    def test_multiple_declared_inputs_preserve_order_and_leave_collisions_to_lean(self):
        for second in ('door', 'lamp'):
            with self.subTest(second=second):
                self.db = Path(self.tmp.name) / second
                protocol = factory()
                metadata = protocol['affordances']['make']
                metadata['fields']['second'] = copy.deepcopy(metadata['fields']['name'])
                metadata['children'] = ['second', 'name']
                descriptor = copy.deepcopy(protocol['commands']['make']['allocate'][0])
                descriptor['name'] = ['input', 'second']
                protocol['commands']['make']['allocate'].append(descriptor)
                view = self.seed(protocol)
                request = self.prepare(view, second=second)
                self.assertEqual(request['absent'], ['workshop/door', 'workshop/lamp'] if second == 'door' else ['workshop/lamp'])
                receipt = self.call(request)
                if second == 'door':
                    self.assertEqual([r['object'] for r in a.allocated_refs(receipt)], ['workshop/door', 'workshop/lamp'])
                else:
                    self.assertEqual(receipt['data'], 'object exists')
                    self.assertEqual(self.inspect(), view['root'])

    def test_public_child_schema_rejects_ambiguous_or_unbounded_declarations(self):
        action = a.card(self.seed())['actions'][0]
        for children in ([{'field': 'name'}, {'field': 'name'}],
                         [{'field': 'name', 'value': 'override'}],
                         [{'field': 'missing'}], [{'field': 'bound', 'value': '../escape'}],
                         [{'field': 'name', 'other': True}], 'name'):
            with self.subTest(children=children):
                with self.assertRaises(a.AffordanceError):
                    a.validate_children_schema(children, action['fields'])
        self.assertEqual(a.allocated_refs({'kind': 'committed', 'data': {'result': 'workshop/fake'}}), [])
        with self.assertRaises(a.AffordanceError):
            a.allocated_refs({'kind': 'committed', 'data': {'allocated': {'workshop/fake': {'version': 1}}}})

    def test_source_desk_factory_pins_compiler_and_preserves_separate_authority(self):
        view = self.seed(factory('source-desk'))
        receipt = self.call(self.prepare(view, 'proposal'))
        self.assertEqual(receipt['kind'], 'committed', receipt)
        child = a.allocated_refs(receipt)[0]
        self.assertEqual(child['root']['protocol'], json.loads((ROOT / 'protocols/source-desk/protocol.json').read_text()))
        self.assertEqual(child['root']['law']['invoke']['compiled'], ['compiler'])
        self.assertEqual(child['root']['law']['invoke']['submit'], ['maker'])
        self.assertEqual(child['root']['law']['reprogram'], [])
        request = {'op': 'invoke', 'object': child['object'], 'principal': 'maker', 'intent': 'submit',
                   'expected': child['root'], 'command': 'submit',
                   'input': {'proposal': {'syntax': 'example', 'source': 'source', 'scenarios': '[]'},
                             'migration': {}, 'target': 'workshop/lamp'}}
        pending = self.call(request)
        self.assertEqual(pending['kind'], 'committed')
        request.update(command='compiled', intent='forged-compiler', expected=pending['data']['root'], input={})
        self.assertEqual(self.call(request)['data'], 'unauthorized')


if __name__ == '__main__': unittest.main()
