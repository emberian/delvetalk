"""Source owns creation descriptors; the receiving host owns atomic admission."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import world

spec = importlib.util.spec_from_file_location('source_factory', ROOT / 'protocols/editor/generate.py')
factory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(factory)


class SourceAllocation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = factory.factory('compiler', ['maker'])

    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.db = Path(home.name) / 'world.json'
        self.serial = 0
        self.factory = self.create('factory', self.program, ['maker'])
        # This boundary fixture emits data. The receiving Factory must distinguish
        # its authentic result from byte-identical directly submitted assertions.
        self.plan = {'factory': 'factory', 'name': 'first', 'editor': 'editor',
                     'generation': 1, 'target': 'target', 'baselineVersion': 0}
        planner = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
            'plan': {'require': [], 'set': {}, 'result': ['record', {
                key: ['input', key] for key in self.plan}], 'outbox': []}}}
        self.editor = self.create('editor', planner, ['maker'])

    def call(self, request):
        self.serial += 1
        return world.exchange(self.db, {'principal': 'maker', 'intent': str(self.serial), **request},
                              profile='compiled')

    def create(self, name, protocol, law):
        result = self.call({'op': 'create', 'object': name, 'protocol': protocol, 'law': law})
        self.assertEqual(result['kind'], 'committed', result)
        return result['data']['root']

    def inspect(self, name):
        return self.call({'op': 'inspect', 'object': name})

    def request(self, name='first', intent='make'):
        return {'op': 'transaction', 'principal': 'maker', 'intent': intent,
                'reads': {'factory': self.factory, 'editor': self.editor, 'factory/' + name: None},
                'calls': [{'object': 'editor', 'command': 'plan', 'input': {**self.plan, 'name': name}},
                          {'object': 'factory', 'command': 'make', 'inputFrom': 0}]}

    def test_source_allocation_admits_exact_child_and_recovers_receipt(self):
        request = self.request()
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        child = self.inspect('factory/first')
        self.assertEqual(receipt['data']['allocated'], {'factory/first': child})
        self.assertTrue(all(set(command) == {'transition'}
                            for command in child['protocol']['commands'].values()))
        self.assertEqual(child['law']['invoke']['submit'], ['maker'])
        self.assertEqual(child['law']['invoke']['compiled'], ['compiler'])
        self.assertEqual(child['law']['invoke']['report'], ['maker'])
        self.assertEqual(child['law']['law'], [])
        self.assertEqual(child['law']['reprogram'], [])
        report = self.call({'op': 'invoke', 'object': 'factory/first', 'expected': child,
                           'command': 'report', 'input': {}})
        self.assertEqual(report['kind'], 'committed', report)
        self.assertEqual(report['data']['result']['status'], 'empty')
        self.assertEqual(self.call(request), receipt)
        self.assertEqual(self.inspect('factory')['version'], 1)

    def test_same_plan_text_has_no_provenance_and_missing_absence_rolls_back(self):
        direct = self.call({'op': 'invoke', 'object': 'factory', 'expected': self.factory,
                           'command': 'make', 'input': self.plan, 'absent': ['factory/first']})
        self.assertEqual(direct['kind'], 'refused', direct)
        self.assertIn('preceding editor plan', direct['data'])
        missing = self.request(intent='missing-absence')
        missing['reads'].pop('factory/first')
        refused = self.call(missing)
        self.assertIn('absence root', refused['data'])
        self.assertEqual(self.inspect('factory'), self.factory)
        self.assertEqual(self.inspect('editor'), self.editor)

    def test_duplicate_child_and_bad_child_law_roll_back_every_staged_write(self):
        duplicate = self.request(intent='duplicate')
        duplicate['calls'] += [copy.deepcopy(duplicate['calls'][0]),
                               {'object': 'factory', 'command': 'make', 'inputFrom': 2}]
        refused = self.call(duplicate)
        self.assertIn('object exists', refused['data'])
        self.assertEqual(self.inspect('factory'), self.factory)
        self.assertEqual(self.inspect('editor'), self.editor)
        objects = world.wire_loads(self.db.read_text())['objects']
        self.assertNotIn('factory/first', objects)

        malformed = copy.deepcopy(self.program)
        # The source still owns law construction. Invalid configured reporter data
        # must fail actual child-law admission rather than leave a broken child.
        fields = malformed['initial']['model']['fields']
        reporters = next(field for field in fields if field['name'] == 'reporters')
        reporters['value'] = {'tag': 'variant', 'label': 'natural', 'payload': {
            'tag': 'record', 'fields': [{'name': 'value', 'value': {'tag': 'natural', 'value': '1'}}]}}
        revised = self.call({'op': 'reprogram', 'object': 'factory', 'expected': self.factory,
                             'protocol': malformed, 'state': malformed['initial']})
        self.assertEqual(revised['kind'], 'committed', revised)
        self.factory = revised['data']['root']
        refused = self.call(self.request(intent='bad-law'))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(self.inspect('factory'), self.factory)
        self.assertEqual(self.inspect('editor'), self.editor)
        self.assertNotIn('factory/first', world.wire_loads(self.db.read_text())['objects'])

    def test_quota_refuses_source_effect_and_current_authority_still_controls_factory(self):
        program = copy.deepcopy(self.program)
        program['allocation']['limit'] = 0
        revised = self.call({'op': 'reprogram', 'object': 'factory', 'expected': self.factory,
                             'protocol': program, 'state': program['initial']})
        self.assertEqual(revised['kind'], 'committed', revised)
        self.factory = revised['data']['root']
        refused = self.call(self.request(intent='quota'))
        self.assertEqual(refused['data'], 'factory child quota exhausted')
        self.assertEqual(self.inspect('factory'), self.factory)
        self.assertEqual(self.inspect('editor'), self.editor)

        denied = self.request(intent='foreign-caller')
        denied['principal'] = 'stranger'
        self.assertEqual(self.call(denied)['data'], 'unauthorized')


if __name__ == '__main__':
    unittest.main()
