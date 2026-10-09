"""Local package selectors resolve in the actual owning native protocol only."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import world
from conformance.test_source_transition import source as turn_source, protocol as turn_protocol
from conformance.test_source_data_transition import protocol as data_protocol, record, sequence, variant, TARGET
from conformance.test_obend_data_object import SOURCE as SHELF_SOURCE

spec = importlib.util.spec_from_file_location('package_room', ROOT / 'scene/room.py')
room = importlib.util.module_from_spec(spec)
spec.loader.exec_module(room)
REF = 'delvetalk-source-package-ref-v1'
TABLE = 'delvetalk-source-package-table-v1'


def reference(entry, name='resident'):
    return {'format': REF, 'name': name, 'entry': entry}


def localize(protocol):
    protocol = copy.deepcopy(protocol)
    descriptor = next(iter(protocol['commands'].values()))['transition']['package']
    protocol['sourcePackages'] = {'resident': {'format': TABLE, 'modules': descriptor['modules']}}
    for command in protocol['commands'].values():
        command['transition']['package'] = reference(command['transition']['package']['entry'])
    return protocol


class SourcePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'world.json'

    def call(self, request):
        return world.exchange(self.db, request, profile='compiled')

    def create(self, name, protocol):
        receipt = self.call({'op': 'create', 'object': name, 'principal': 'maker',
            'intent': 'create-' + name, 'protocol': protocol, 'law': ['maker', 'visitor']})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['root']['protocol'], protocol)
        return receipt['data']['root']

    def invoke(self, name, root, command='water', fields=None, intent='turn'):
        return {'op': 'invoke', 'object': name, 'principal': 'visitor', 'intent': intent,
                'expected': root, 'command': command, 'input': {'amount': 2} if fields is None else fields}

    def inspect(self, name):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def test_plain_transition_exact_table_reprogram_and_retained_retry(self):
        first = localize(turn_protocol())
        root = self.create('counter', first)
        request = self.invoke('counter', root)
        receipt = self.call(request)
        self.assertEqual(receipt['data']['result'], 2)
        current = self.inspect('counter')
        second = copy.deepcopy(first)
        second['sourcePackages']['resident']['modules'][0]['source'] = turn_source(
            '{accepted: true, reason: "", state: {count: state.count + input.amount}, result: 77n}')
        changed = self.call({'op': 'reprogram', 'object': 'counter', 'principal': 'maker',
            'intent': 'revise', 'expected': current, 'protocol': second, 'state': current['state']})
        self.assertEqual(changed['kind'], 'committed', changed)
        revised = self.inspect('counter')
        self.assertEqual(self.call(request), receipt)
        self.assertEqual(self.inspect('counter'), revised)
        self.assertEqual(self.call(self.invoke('counter', current, intent='stale'))['data'], 'stale read root')
        self.assertEqual(self.call(self.invoke('counter', revised, intent='new'))['data']['result'], 77)

    def test_names_are_local_and_request_data_cannot_select_another_table(self):
        for number in (1, 2):
            program = localize(turn_protocol(turn_source(
                '{accepted: true, reason: "", state: state, result: ' + str(number) + 'n}')))
            root = self.create('object-' + str(number), program)
            request = self.invoke('object-' + str(number), root, intent='turn-' + str(number))
            request['sourcePackages'] = {'resident': {'format': TABLE, 'modules': []}}
            self.assertEqual(self.call(request)['data']['result'], number)
        root = self.inspect('object-1')
        substituted = copy.deepcopy(root)
        substituted['protocol']['sourcePackages'] = self.inspect('object-2')['protocol']['sourcePackages']
        refused = self.call(self.invoke('object-1', substituted, intent='substitute'))
        self.assertEqual(refused['data'], 'stale read root')

    def test_malformed_unknown_and_uncompiled_references_refuse_installation(self):
        for index, mutation in enumerate(('missing', 'foreign', 'extra-ref', 'extra-table', 'format', 'modules', 'bad-source', 'bad-entry')):
            program = localize(turn_protocol())
            package = program['commands']['water']['transition']['package']
            table = program['sourcePackages']['resident']
            if mutation == 'missing': del program['sourcePackages']
            elif mutation == 'foreign': package['name'] = 'another-object/resident'
            elif mutation == 'extra-ref': package['modules'] = table['modules']
            elif mutation == 'extra-table': table['sha256'] = 'a' * 64
            elif mutation == 'format': table['format'] = 'unknown'
            elif mutation == 'modules': table['modules'] = 'not an array'
            elif mutation == 'bad-source': table['modules'][0]['source'] = 'not Bend'
            elif mutation == 'bad-entry': package['entry'] = 'missing'
            with self.subTest(mutation=mutation):
                result = self.call({'op': 'create', 'object': 'bad-' + str(index), 'principal': 'maker',
                    'intent': mutation, 'protocol': program, 'law': ['maker']})
                self.assertEqual(result['kind'], 'refused', result)

    def test_typed_transition_and_expression_share_native_resolution(self):
        target = self.create('target', TARGET)
        program = localize(data_protocol())
        root = self.create('index', program)
        request = {'op': 'transaction', 'principal': 'visitor', 'intent': 'observe-and-add',
            'reads': {'target': target, 'index': root}, 'calls': [
                {'op': 'observe', 'object': 'target'},
                {'object': 'index', 'command': 'add', 'inputFrom': 0}]}
        self.assertEqual(self.call(request)['kind'], 'committed')
        self.assertEqual(self.inspect('index')['state'], {'model': record(visits=sequence(0))})
        legacy = copy.deepcopy(TARGET)
        legacy['sourcePackages'] = program['sourcePackages']
        legacy['commands']['touch']['result'] = ['package-data-v1', reference('identity'), [['literal', sequence(4, 5)]]]
        root = self.create('typed-expression', legacy)
        receipt = self.call(self.invoke('typed-expression', root, 'touch', {}, 'typed-result'))
        self.assertEqual(receipt['data']['result'], sequence(4, 5))

    def test_plain_expression_and_allocation_use_parent_owned_table(self):
        text = 'edition ObjectiveBend 1\ndef label() -> String:\n  "lamp"\n'
        program = copy.deepcopy(TARGET)
        program['sourcePackages'] = {'resident': {'format': TABLE, 'modules': [{'name': 'Factory', 'source': text}]}}
        program['allocation'] = {'limit': 1}
        command = program['commands']['touch']
        command['result'] = ['package', reference('label'), []]
        command['allocate'] = [{'name': ['package', reference('label'), []],
            'protocol': ['literal', TARGET], 'law': ['literal', ['visitor']]}]
        root = self.create('factory', program)
        request = self.invoke('factory', root, 'touch', {}, 'make')
        request['absent'] = ['factory/lamp']
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['result'], 'lamp')
        self.assertIn('factory/lamp', receipt['data']['allocated'])

    def test_source_view_uses_original_table_without_expanding_retained_root(self):
        text = (ROOT / 'syntaxes/examples/lantern.obend').read_text()
        # Multiple methods and the projection share this once-retained module.
        program = {'profile': 'delvetalk-local-v1', 'initial': {'lit': False},
            'sourcePackages': {'resident': {'format': TABLE, 'modules': [{'name': 'Lantern', 'source': text}]}},
            'commands': {method: {'transition': {'profile': 'delvetalk-source-transition-v1',
                'package': reference(method)}} for method in ('light', 'douse')},
            'affordances': {method: {'fields': {}} for method in ('light', 'douse')},
            'viewProgram': {'profile': 'delvetalk-obend-menu-v1', 'package': reference('view')}}
        root = self.create('lantern', program)
        view = room.inspect_object(root, 'lantern')
        self.assertEqual(view['mode'], 'projection', view)
        self.assertEqual(list(view['actions']), ['light'])
        self.assertEqual(view['root'], root)
        receipt = self.call(self.invoke('lantern', root, 'light', {}, 'light'))
        self.assertEqual(receipt['kind'], 'committed', receipt)
        view = room.inspect_object(self.inspect('lantern'), 'lantern')
        self.assertEqual(list(view['actions']), ['douse'])
        self.assertEqual(self.inspect('lantern')['protocol'], program)

    def test_typed_source_view_materializes_children_through_local_reference(self):
        program = {'profile': 'delvetalk-local-v1',
            'initial': {'model': record(entries=variant('nil', record()))},
            'sourcePackages': {'resident': {'format': TABLE, 'modules': [{'name': 'Shelf', 'source': SHELF_SOURCE}]}},
            'commands': {'add': {'transition': {'profile': 'delvetalk-source-data-transition-v1',
                'package': reference('add')}}},
            'affordances': {'add': {'fields': {'object': {'type': 'string', 'minLength': 1, 'maxLength': 64}}}},
            'viewProgram': {'profile': 'delvetalk-obend-data-menu-v1', 'package': reference('view')}}
        root = self.create('shelf', program)
        view = room.inspect_object(root, 'shelf')
        self.assertEqual(view['mode'], 'projection', view)
        self.assertEqual(view['children'], [])
        receipt = self.call(self.invoke('shelf', root, 'add', {'object': 'an-exhibit'}, 'exhibit'))
        self.assertEqual(receipt['kind'], 'committed', receipt)
        view = room.inspect_object(self.inspect('shelf'), 'shelf')
        self.assertEqual([child['object'] for child in view['children']], ['an-exhibit'])
        self.assertEqual(self.inspect('shelf')['protocol'], program)


if __name__ == '__main__':
    unittest.main()
