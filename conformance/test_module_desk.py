"""Direct and CLI module checks run real bounded compiler children and Lean admission."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import desk
import source_store

PACKAGE = ROOT / 'protocols/peer-layers'


class ModuleDeskChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='module-desk-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.client = desk.Desk(self.home / 'world.json', self.home / 'artifacts', profile='compiled')
        self.law = {'profile': 'delvetalk-scoped-law',
                    'invoke': {'requestCheck': ['maker'], 'submit': ['maker'], 'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': ['maker']},
                    'reprogram': [], 'law': ['owner'], 'read': 'public'}
        entries = [{'name': name, 'sourceRef': source_store.store_bytes(self.client.artifact_store,
                    (PACKAGE / (name + '.obend')).read_bytes())} for name in ('Base', 'Doubling', 'Main')]
        self.proposal = source_store.prepare_module_proposal(self.client.artifact_store,
            source_store.seal_modules(entries), (PACKAGE / 'doubling.examples').read_bytes())

        modules = desk.source_object.read_closure([(name, PACKAGE / (name + '.obend'))
            for name in ('Base', 'Doubling', 'Main')])
        protocol = desk.source_object.load(modules, syntax='objective-bend-object')
        self.target = self.client.exchange({'op': 'create', 'object': 'target', 'principal': 'owner',
            'intent': 'make-target', 'protocol': protocol, 'law': {'profile': 'delvetalk-scoped-law',
                'invoke': {'ring': ['maker'], 'stamp': ['maker'], 'base': ['maker']},
                'read': 'public', 'law': ['owner'], 'reprogram': ['maker']}})['data']['root']

    def pending(self, name):
        created = self.client.create(name, 'owner', 'create-' + name, self.law)
        self.assertEqual(created['kind'], 'committed', created)
        submitted = self.client.submit_refs(name, 'maker', 'submit-' + name, created['data']['root'],
            self.proposal, {'model': desk.source_object.compact_state(self.target['protocol'],
                desk.source_object.data({'value': 0}), entry='describe', path=[{'field': 'initial'}])}, 'target')
        self.assertEqual(submitted['kind'], 'committed', submitted)
        view = desk.projection.project(submitted['data']['root'], name)
        checked = self.client.exchange(desk.projection.request(view, 'check', 'maker', 'request-check-' + name))
        self.assertEqual(checked['kind'], 'committed', checked)
        return self.client.inspect(name, principal='maker')

    def assert_ready(self, name, reply):
        self.assertEqual(reply['kind'], 'committed', reply)
        root = self.client.inspect(name)
        self.assertEqual(desk.candidate_state(root)['status'], 'ready', desk.candidate_state(root).get('diagnostics'))
        build = desk.load_artifact(self.client.artifact_store, desk.candidate_state(root)['artifact'])
        self.assertTrue(build['passed'], build)
        self.assertEqual(build['sourceBindings']['manifest'], self.proposal['manifest'])
        self.assertEqual([entry['name'] for entry in build['sourceMaterial']['modules']], ['Base', 'Doubling', 'Main'])
        self.assertTrue(build['report']['passed'])
        return root

    def test_direct_check_and_cli_check_then_receipt_first_recovery(self):
        pending = self.pending('direct')
        direct_work = desk.compiler_work(pending, 'direct', 'compiler', self.client.database)
        reply = self.client.check('direct', 'compiler', direct_work['intent'], pending)
        self.assert_ready('direct', reply)
        cli_pending = self.pending('cli')
        expected = self.home / 'cli-root.json'
        expected.write_bytes(desk.canonical(cli_pending))
        command = [sys.executable, str(ROOT / 'scripts/desk.py'), '--database', str(self.client.database),
                   '--artifacts', str(self.client.artifact_store), '--profile', 'compiled', 'check',
                   '--object', 'cli', '--principal', 'compiler', '--intent', desk.compiler_work(cli_pending, 'cli', 'compiler', self.client.database)['intent'], '--expected-root', str(expected)]
        child = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60)
        self.assertEqual(child.returncode, 0, child.stderr.decode())
        cli_reply = desk.loads(child.stdout)
        self.assert_ready('cli', cli_reply)
        # Sources may disappear after admission; exact retries recover historical
        # receipts before consulting module blobs or current adapter pins.
        ref = self.proposal['manifest']['modules'][0]['sourceRef']
        source_store.blob_path(self.client.artifact_store, ref['sha256']).unlink()
        self.assertEqual(self.client.check('direct', 'compiler', direct_work['intent'], pending), reply)
        child = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60)
        self.assertEqual(child.returncode, 0, child.stderr.decode())
        self.assertEqual(desk.loads(child.stdout), cli_reply)

    def test_pending_admission_revalidates_module_custody_before_commit(self):
        pending = self.pending('pending')
        profile = desk.execution_profile('compiled')
        work = desk.compiler_work(pending, 'pending', 'compiler', self.client.database)
        build = desk.bounded_compile(pending, work=work, profile='compiled', artifact_store=self.client.artifact_store)
        self.assertTrue(build['passed'], build)
        entry = self.client.prepare_check({'object': 'pending', 'principal': 'compiler',
            'intent': work['intent'], 'expected': pending}, build, profile)
        ref = self.proposal['manifest']['modules'][0]['sourceRef']
        path = source_store.blob_path(self.client.artifact_store, ref['sha256'])
        original = path.read_bytes()
        path.write_bytes(original + b'\n')
        with self.assertRaises(ValueError): self.client.admit_check(entry)
        self.assertEqual(self.client.inspect('pending'), pending)
        path.write_bytes(original)
        reply = self.client.admit_check(entry)
        self.assert_ready('pending', reply)


if __name__ == '__main__': unittest.main()
