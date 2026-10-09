"""Typed child models stay native through governed construction admission."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
import world

FILES = [('List', 'world/lib/prelude/List.obend'), ('Abi', 'world/lib/prelude/Abi.obend'),
         ('Preparation', 'world/lib/prelude/Preparation.obend'), ('Encounter', 'world/lib/prelude/Encounter.obend'),
         ('Allocation', 'world/lib/prelude/Allocation.obend'), ('Document', 'world/lib/document/Document.obend'),
         ('Reflection', 'world/lib/prelude/Reflection.obend'), ('Writing', 'protocols/source-desk/Writing.obend')]


def modules(counter=None, factory=None):
    return [{'name': name, 'source': (ROOT / path).read_text()} for name, path in FILES] + [
        {'name': 'Counter', 'source': counter or (ROOT / 'conformance/fixtures/allocation/Counter.obend').read_text()},
        {'name': 'TypedFactory', 'source': factory or (ROOT / 'conformance/fixtures/allocation/Factory.obend').read_text()}]


def protocol(sources, name):
    selected = next(item for item in sources if item['name'] == name)
    return source_object.load([item for item in sources if item['name'] != name] + [selected],
                              syntax='objective-bend-object')


class TypedAllocation(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.database = Path(home.name) / 'world.json'
        self.serial = 0

    def exchange(self, request):
        self.serial += 1
        return world.exchange(self.database, {'principal': 'maker', 'intent': str(self.serial), **request}, profile='compiled')

    def seed(self, *, counter=None, factory=None, writer=None):
        sources = modules(counter, factory)
        child_sources = sources[:-1]
        writer = protocol(child_sources, 'Writing') if writer is None else writer
        child = protocol(child_sources, 'Counter')
        config = source_object.record({'writer': source_object.value(writer),
            'counter': source_object.value(child), 'law': source_object.value({'profile': 'delvetalk-scoped-law',
                'invoke': {'report': ['maker']}, 'reprogram': ['maker'], 'law': ['maker'], 'read': ['maker']})})
        program = source_object.load(sources, syntax='objective-bend-object', constructor='initial', arguments=[config])
        reply = self.exchange({'op': 'create', 'object': 'factory', 'protocol': program, 'law': {'profile': 'delvetalk-scoped-law',
            'invoke': {'make': ['maker']}, 'reprogram': ['maker'], 'law': ['maker'], 'read': ['maker']}})
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply['data']['root']

    def make(self, root, name, kind, *, absent=True):
        request = {'op': 'invoke', 'object': 'factory', 'expected': root, 'command': 'make',
                   'input': {'name': name, 'kind': kind}}
        if absent:
            request['absent'] = ['factory/' + name]
        return self.exchange(request)

    def inspect(self, name):
        return self.exchange({'op': 'inspect', 'object': name})

    def model(self, root):
        return {field['name']: field['value'] for field in source_object.state_data(root)['fields']}

    def test_heterogeneous_configured_children_and_plain_copy(self):
        root = self.seed()
        for name, kind in [('writing', 'writer'), ('counter', 'counter'), ('copy', 'copy')]:
            reply = self.make(root, name, kind)
            self.assertEqual(reply['kind'], 'committed', reply)
            root = reply['data']['root']
            child = reply['data']['allocated']['factory/' + name]
            model = self.model(child)
            if kind == 'writer':
                self.assertEqual(model['candidate']['value'], 'candidate')
                self.assertEqual(model['target']['value'], 'target')
            else:
                self.assertEqual(model['count']['value'], '0' if kind == 'copy' else '3')
        self.assertEqual(self.make(root, 'extra', 'counter')['data'], 'factory child quota exhausted')

    def test_actual_writing_factory_builds_typed_configured_card(self):
        import desk
        package = desk.module('typed_writing_package', 'protocols/source-desk/package.py')
        reply = self.exchange({'op': 'create', 'object': 'factory', 'protocol': package.writing_factory(),
            'law': {'profile': 'delvetalk-scoped-law', 'invoke': {'make': ['maker']},
                    'law': ['maker'], 'reprogram': ['maker'], 'read': ['maker']}})
        self.assertEqual(reply['kind'], 'committed', reply.get('data'))
        root = reply['data']['root']
        reply = self.exchange({'op': 'invoke', 'object': 'factory', 'expected': root,
            'command': 'make', 'input': {'name': 'writing', 'candidate': 'candidate',
            'target': 'target', 'syntax': 'objective-bend-object'}, 'absent': ['factory/writing']})
        self.assertEqual(reply['kind'], 'committed', reply.get('data'))
        child = reply['data']['allocated']['factory/writing']
        model = self.model(child)
        self.assertEqual(model['candidate']['value'], 'candidate')
        self.assertEqual(model['target']['value'], 'target')
        self.assertEqual(model['syntax']['value'], 'objective-bend-object')
        self.assertEqual(child['law']['invoke']['report'], ['maker'])

    def test_native_type_mismatch_and_missing_absence_roll_back(self):
        sources = modules()
        root = self.seed(writer=protocol(sources[:-1], 'Counter'))
        reply = self.make(root, 'bad', 'writer')
        self.assertEqual(reply['kind'], 'refused', reply.get('data') if reply['kind'] == 'refused' else reply['kind'])
        self.assertIn('type differs', reply['data'])
        self.assertEqual(self.inspect('factory'), root)
        self.assertNotIn('factory/bad', world.wire_loads(self.database.read_text())['objects'])
        transaction = self.exchange({'op': 'transaction',
            'reads': {'factory': root, 'factory/good': None, 'factory/bad': None},
            'calls': [{'object': 'factory', 'command': 'make', 'input': {'name': 'good', 'kind': 'counter'}},
                      {'object': 'factory', 'command': 'make', 'input': {'name': 'bad', 'kind': 'writer'}}]})
        self.assertEqual(transaction['kind'], 'refused', transaction['kind'])
        self.assertIn('type differs', transaction['data'])
        self.assertEqual(self.inspect('factory'), root)
        self.assertNotIn('factory/good', world.wire_loads(self.database.read_text())['objects'])
        reply = self.make(root, 'missing', 'counter', absent=False)
        self.assertEqual(reply['kind'], 'refused', reply.get('data') if reply['kind'] == 'refused' else reply['kind'])
        self.assertIn('absence', reply['data'])
        self.assertEqual(self.inspect('factory'), root)

    def test_forged_child_schema_claim_cannot_frame_typed_initial(self):
        sources = modules()
        writer = protocol(sources[:-1], 'Writing')
        writer['initial']['model']['schema']['packetSha256'] = '0' * 64
        root = self.seed(writer=writer)
        reply = self.make(root, 'forged', 'writer')
        self.assertEqual(reply['kind'], 'refused', reply.get('data') if reply['kind'] == 'refused' else reply['kind'])
        self.assertIn('schema', reply['data'])
        self.assertEqual(self.inspect('factory'), root)

    def test_source_revision_requires_matching_typed_construction(self):
        counter = (ROOT / 'conformance/fixtures/allocation/Counter.obend').read_text()
        counter = counter.replace('  count: Nat\n', '  count: Nat\n  flag: Bool\n').replace('initial: {count: 0n}', 'initial: {count: 0n, flag: false}')
        factory = (ROOT / 'conformance/fixtures/allocation/Factory.obend').read_text()
        factory = factory.replace('{count: 3n}', '{count: 3n, flag: true}')
        root = self.seed(counter=counter, factory=factory)
        reply = self.make(root, 'revised', 'counter')
        self.assertEqual(reply['kind'], 'committed', reply)
        model = self.model(reply['data']['allocated']['factory/revised'])
        self.assertEqual(model['count']['value'], '3')
        self.assertTrue(model['flag']['value'])

    def test_inactive_allocation_alternative_requires_canonical_descriptor_abi(self):
        sources = modules()
        sources[-1]['source'] = sources[-1]['source'].replace('  copy: {name: String, protocol: P.Value, law: P.Value}',
            '  copy: {name: String, protocol: P.Value, law: String}').replace('law: config.law}) else Child.counter',
            'law: "forged"}) else Child.counter')
        with self.assertRaisesRegex(ValueError, 'allocations.*incompatible'):
            source_object.load(sources, syntax='objective-bend-object')


if __name__ == '__main__':
    unittest.main()
