"""Selected-host proposal/desk composition with real Lean binaries, no network."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('desk_profiles', ROOT / 'scripts/desk.py')
desk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desk)
proposal = desk.module('selected_proposal', 'scripts/propose.py')
manage = desk.module('selected_management', 'scripts/manage.py')


class DeskProfiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.database = self.directory / 'world.json'
        self.artifacts = self.directory / 'artifacts'
        package = {'modules': [{'name': 'Example', 'source':
            'edition ObjectiveBend 1\ndef run(x: Nat) -> Nat:\n  x + 1n\n'}], 'entry': 'run'}
        expression = ['package', package, [['input', 'x']]]
        self.protocol = {'profile': 'delvetalk-local-v1', 'initial': {'count': 0},
            'runtimeProfile': 'compiled', 'commands': {'run': {'require': [],
            'set': {'count': expression}, 'result': expression, 'outbox': []}}}
        self.source = desk.canonical(self.protocol)
        self.scenarios = desk.canonical([{'name': 'increment', 'law': ['a'], 'steps': [
            {'principal': 'a', 'command': 'run', 'input': {'x': 4}, 'root': 'initial',
             'kind': 'committed', 'result': 5, 'state': {'count': 5}}]}])

    def test_explicit_profile_controls_candidate_installation_and_every_scenario(self):
        default = proposal.propose('protocol-json@1', self.source, self.scenarios)
        self.assertFalse(default['passed'])
        self.assertEqual(default['outcomes'][0]['installation']['kind'], 'refused')
        self.assertEqual(default['execution']['admissionProfile'], 'world')
        compiled = proposal.propose('protocol-json@1', self.source, self.scenarios, profile='compiled')
        self.assertTrue(compiled['passed'], compiled['outcomes'])
        self.assertEqual(compiled['execution']['admissionProfile'], 'compiled')
        self.assertIn('spec/Delvetalk/Package.lean', compiled['execution']['files'])
        self.assertEqual(compiled['outcomes'][0]['steps'][0]['receipt']['data']['result'], 5)

    def test_compiled_desk_worker_check_adoption_and_invocation(self):
        worker = desk.Desk(self.database, self.artifacts, profile='compiled')
        candidate = worker.create('candidate', 'a', 'create-candidate', ['a'])['data']['root']
        target = worker.exchange({'op': 'create', 'object': 'target', 'principal': 'a', 'intent': 'target',
            'protocol': desk.loads((ROOT / 'protocols/counter/protocol.json').read_bytes()), 'law': ['a']})['data']['root']
        pending = worker.submit('candidate', 'a', 'submit', candidate, 'protocol-json@1', self.source,
                                self.scenarios, {'count': 0}, 'target')['data']['root']
        checked = worker.check('candidate', 'a', 'check', pending)
        self.assertEqual(checked['kind'], 'committed')
        ready = checked['data']['root']
        self.assertEqual(desk.candidate_state(ready)['status'], 'ready', ready['state'])
        artifact = desk.load_artifact(self.artifacts, desk.candidate_state(ready)['artifact'])
        self.assertEqual(artifact['report']['execution']['admissionProfile'], 'compiled')
        adopted = worker.adopt('candidate', 'target', 'a', 'adopt', ready, target)
        self.assertEqual(adopted['kind'], 'committed', adopted)
        root = worker.inspect('target')
        invoked = worker.exchange({'op': 'invoke', 'object': 'target', 'principal': 'a', 'intent': 'run',
                                  'expected': root, 'command': 'run', 'input': {'x': 4}})
        self.assertEqual(invoked['data']['root']['state'], {'count': 5})

    def test_pending_profile_change_refuses_without_creating_receipt(self):
        worker = desk.Desk(self.database, self.artifacts)
        candidate = worker.create('candidate', 'a', 'create', ['a'])['data']['root']
        plain = (ROOT / 'protocols/counter/protocol.json').read_bytes()
        pending = worker.submit('candidate', 'a', 'submit', candidate, 'protocol-json@1', plain,
            (ROOT / 'protocols/counter/scenarios.json').read_bytes(), {'count': 0}, 'target')['data']['root']
        with patch.object(worker, 'exchange', side_effect=OSError('before admission')):
            with self.assertRaises(OSError):
                worker.check('candidate', 'a', 'check', pending)
        before = self.database.read_bytes()
        changed = desk.Desk(self.database, self.artifacts, profile='compiled')
        with self.assertRaisesRegex(ValueError, 'runtime pins changed'):
            changed.check('candidate', 'a', 'check', pending)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(worker.check('candidate', 'a', 'check', pending)['kind'], 'committed')

    def test_compiled_clerk_management_uses_selected_profile_for_all_operations(self):
        principal = 'did:plc:aaaaaaaaaaaaaaaaaaaaaaaa'
        custody = self.directory / 'clerk'
        clerk = manage.clerk.Clerk(custody)
        initial = clerk.bootstrap('first', desk.loads((ROOT / 'protocols/counter/protocol.json').read_bytes()),
                                  [principal], [principal], runtime_profile='compiled')['data']['root']
        manager = manage.Management(custody)
        created = manager.add_object('second', principal, 'create', 'protocol-json@1', self.source, [principal])
        self.assertEqual(created['reply']['kind'], 'committed', created)
        changed = manager.reprogram('first', principal, 'replace', initial, 'protocol-json@1', self.source, b'{"count":0}')
        self.assertEqual(changed['reply']['kind'], 'committed', changed)
        root = changed['reply']['data']['root']
        with patch.object(manage.clerk.world, 'exchange', side_effect=OSError('before admission')):
            with self.assertRaises(OSError):
                manager.law('first', principal, 'law', root, [principal])
        before = clerk.database.read_bytes()
        config = clerk.config()
        manage.clerk.save(custody / 'clerk.json', {**config, 'runtimeProfile': 'world'})
        with self.assertRaisesRegex(ValueError, 'admission profile changed'):
            manager.resume(principal, 'law')
        self.assertEqual(clerk.database.read_bytes(), before)
        manage.clerk.save(custody / 'clerk.json', config)
        revised = manager.resume(principal, 'law')
        for receipt in (created, changed, revised):
            self.assertEqual(receipt['admissionProfile'], 'compiled')
            self.assertEqual(receipt['reply']['kind'], 'committed')


if __name__ == '__main__':
    unittest.main()
