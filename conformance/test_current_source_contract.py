"""Current typed receiving ABI enforces law-owned checked source contracts."""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN_ROOT = Path(os.environ.get('DELVETALK_NATIVE_ROOT', ROOT)) / '.lake/build/bin'
SOURCE = (ROOT / 'conformance/fixtures/source-contract/Counter.obend').read_text()


def native(name, request):
    return json.loads(subprocess.run([str(BIN_ROOT / name)], input=json.dumps(request) + '\n',
        capture_output=True, text=True, check=True, timeout=30).stdout)


def package(entry):
    return {'modules': [{'name': 'Counter', 'source': SOURCE}], 'entry': entry}


def record(**fields):
    return {'tag': 'record', 'fields': [{'name': k, 'value': v} for k, v in fields.items()]}


def nat(n):
    return {'tag': 'natural', 'value': str(n)}


class CurrentSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiled = native('delvetalk-obend', {'op': 'compile', **package('contractMetadata')})
        if compiled.get('status') != 'compiled':
            raise AssertionError(compiled)
        observed = native('delvetalk-obend', {'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
        cls.metadata = observed['value']

    def setUp(self):
        self.world = {'objects': {}, 'receipts': []}
        self.serial = 0

    def call(self, **request):
        self.serial += 1
        request = {'principal': 'maker', 'intent': 'contract-' + str(self.serial), **request}
        response = native('delvetalk-compiled', {'world': self.world, 'request': request})
        self.assertNotIn('error', response, response)
        self.world = response['world']
        return response['reply']

    def create(self, mode='model'):
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {'model': record(count=nat(0))},
                    'commands': {name: {'transition': {'profile': 'delvetalk-source-transition',
                       'package': package(name), 'inputCodec': 'data'}} for name in ('add', 'damage')}}
        law = {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker'], 'damage': ['maker']},
               'reprogram': ['maker'], 'law': ['maker'],
               'contract': {'profile': 'delvetalk-source-contract-v1', 'package': package('contract'),
                            'stateProfile': mode, 'metadata': copy.deepcopy(self.metadata)}}
        return self.call(op='create', object='counter', protocol=protocol, law=law)

    def test_current_contract_admits_and_checks_actual_typed_state(self):
        made = self.create()
        self.assertEqual(made['kind'], 'committed', made)
        root = made['data']['root']
        added = self.call(op='invoke', object='counter', command='add', expected=root, input=record(amount=nat(3)))
        self.assertEqual(added['kind'], 'committed', added)
        root = added['data']['root']
        self.assertEqual(root['state']['model'], record(count=nat(3)))
        refused = self.call(op='invoke', object='counter', command='damage', expected=root, input=record(amount=nat(1)))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(self.world['objects']['counter'], root)

    def test_atomic_rollback_preserves_prior_staged_source_result_and_history(self):
        made = self.create()
        self.assertEqual(made['kind'], 'committed', made)
        root = made['data']['root']
        refused = self.call(op='transaction', object='counter', reads={'counter': root}, calls=[
            {'object': 'counter', 'command': 'add', 'input': record(amount=nat(3))},
            {'object': 'counter', 'command': 'damage', 'input': record(amount=nat(1))}])
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(self.world['objects']['counter'], root)
        self.assertEqual(len(self.world['receipts']), 2)

    def test_current_contract_rejects_missing_methods_and_forged_metadata(self):
        made = self.create()
        self.assertEqual(made['kind'], 'committed', made)
        root = made['data']['root']
        protocol = copy.deepcopy(root['protocol'])
        del protocol['commands']['add']
        refused = self.call(op='reprogram', object='counter', expected=root,
                            protocol=protocol, state=root['state'])
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('missing method', refused['data'])
        self.assertEqual(self.world['objects']['counter'], root)
        law = copy.deepcopy(root['law'])
        law['contract']['metadata'] = {'tag': 'boolean', 'value': True}
        refused = self.call(op='law', object='counter', expected=root, law=law)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('metadata differs', refused['data'])
        self.assertEqual(self.world['objects']['counter'], root)

    def test_plain_contract_state_profile_is_retired(self):
        reply = self.create('plain')
        self.assertEqual(reply['kind'], 'refused', reply)
        self.assertIn('model state profile', reply['data'])
        self.assertNotIn('counter', self.world['objects'])


if __name__ == '__main__': unittest.main()
