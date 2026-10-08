"""Explicit compiled runtime selection at the authenticated receiving boundary."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import delve
import manage
import receipts

spec = importlib.util.spec_from_file_location('compiled_clerk_fixture', ROOT / 'conformance/test_live_path.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


def package_protocol():
    package = {'modules': [{'name': 'RemoteMath', 'source':
        'edition ObjectiveBend 1\ndef add(x: Nat, y: Nat) -> Nat:\n  x + y\n'}], 'entry': 'add'}
    calculation = ['package', package, [['input', 'x'], ['input', 'y']]]
    return {'profile': 'delvetalk-local-v1', 'initial': {'answer': 0}, 'commands': {'add': {
        'require': [], 'set': {'answer': calculation}, 'result': calculation, 'outbox': []}}}


class CompiledClerk(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.pds = live.PDS()
        self.clerk = clerk.Clerk(self.base / 'clerk', self.pds)
        self.initial = self.clerk.bootstrap('math', package_protocol(), [delve.DID], [delve.DID],
                                            runtime_profile='compiled')['data']['root']
        credentials = self.base / 'credentials.json'
        credentials.write_text('{"handle":"' + delve.HANDLE + '","app_password":"mock-password"}')
        self.publisher = receipts.Publisher(delve.Delve(self.base / 'publications', credentials,
                                                       self.base / 'posts', self.pds))

    def receive(self, payload, intent):
        source = self.publisher.publish('request', clerk.world.wire_dumps(payload), intent)
        return self.clerk.receive(source['uri'], source['cid'])

    def invoke(self, root=None):
        return {'object': 'math', 'command': 'add', 'input': {'x': 2**80, 'y': 7},
                'expected': self.initial if root is None else root}

    def test_single_remote_source_package_answer_and_complete_pins(self):
        receipt = self.receive(self.invoke(), 'sum')
        self.assertEqual(receipt['reply']['data']['result'], 2**80 + 7)
        self.assertEqual(receipt['reply']['data']['root']['state']['answer'], 2**80 + 7)
        self.assertEqual(receipt['request']['principal'], delve.DID)
        self.assertIn('spec/Delvetalk/Package.lean', receipt['profile']['pins'])
        self.assertIn('spec/upstream/Compiler/ObjectiveBendFrontEnd.lean', receipt['profile']['pins'])
        self.assertIn('.lake/build/bin/delvetalk-compiled', receipt['profile']['pins'])
        entry = clerk.loads(next((self.clerk.state / 'requests').glob('*.json')).read_text())
        self.assertEqual(entry['admissionProfile'], 'compiled')
        self.assertEqual(self.receive(self.invoke(), 'sum'), receipt)

    def test_compiled_multiobject_transaction_uses_operator_runtime(self):
        added = manage.Management(self.clerk.state).add_object('other', delve.DID, 'other', 'protocol-json@1',
            clerk.canonical(package_protocol()), [delve.DID])
        self.assertEqual(added['reply']['kind'], 'committed')
        other = self.clerk.snapshot('other')['root']
        receipt = self.receive({'op': 'transaction', 'reads': {'math': {'expected': self.initial}, 'other': {'expected': other}},
            'calls': [{'object': 'math', 'command': 'add', 'input': {'x': 4, 'y': 5}},
                      {'object': 'other', 'command': 'add', 'input': {'x': 20, 'y': 22}}]}, 'two-sums')
        self.assertEqual(receipt['reply']['data']['results'], [9, 42])
        self.assertEqual(receipt['reply']['data']['roots']['other']['state']['answer'], 42)
        self.assertEqual(self.clerk.snapshot('math')['root']['state']['answer'], 9)

    def test_default_runtime_refuses_compiled_primitive_and_wire_cannot_select_it(self):
        ordinary = clerk.Clerk(self.base / 'ordinary', self.pds)
        refused = ordinary.bootstrap('math', package_protocol(), [delve.DID], [delve.DID])
        self.assertEqual(refused['kind'], 'refused')
        self.assertEqual(clerk.loads(ordinary.database.read_text())['objects'], {})
        self.assertNotIn('runtimeProfile', ordinary.config())
        payload = self.invoke()
        payload['runtimeProfile'] = 'compiled'
        with self.assertRaises(receipts.Failure):
            self.receive(payload, 'runtime-forgery')

    def test_pending_profile_cannot_switch_and_quiescent_upgrade_keeps_history(self):
        source = self.publisher.publish('request', clerk.world.wire_dumps(self.invoke()), 'pending')
        save = clerk.save
        def crash(path, entry):
            if 'receipt' in entry and 'source' in entry:
                raise KeyboardInterrupt('after admission before custody save')
            return save(path, entry)
        with patch.object(clerk, 'save', crash):
            with self.assertRaises(KeyboardInterrupt):
                self.clerk.receive(source['uri'], source['cid'])
        old = self.clerk.profile()
        with self.assertRaisesRegex(ValueError, 'pending'):
            self.clerk.upgrade(old['sha256'], 'world')
        receipt = self.clerk.receive(source['uri'], source['cid'])
        before = self.clerk.database.read_bytes()
        upgraded = self.clerk.upgrade(old['sha256'], 'world')
        self.assertEqual(upgraded['upgrade']['fromRuntime'], 'compiled')
        self.assertEqual(upgraded['upgrade']['toRuntime'], 'world')
        self.assertEqual(self.clerk.database.read_bytes(), before)
        self.assertEqual(self.clerk.receive(source['uri'], source['cid']), receipt)
        refused = self.receive(self.invoke(receipt['reply']['data']['root']), 'under-default')
        self.assertEqual(refused['reply']['kind'], 'refused')
        self.assertEqual(self.clerk.upgrade(old['sha256'], 'world')['status'], 'already-upgraded')


if __name__ == '__main__':
    unittest.main()
