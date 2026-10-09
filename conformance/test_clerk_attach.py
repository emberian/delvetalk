"""Existing workspace enrollment: actual Lean replay/admission and fake public PDS."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('clerk_attach_test', ROOT / 'scripts/clerk.py')
clerk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clerk)
workspace = clerk.module('clerk_attach_workspace', 'scripts/workspace.py')
A = 'did:plc:aaaaaaaaaaaaaaaaaaaaaaaa'
B = 'did:plc:bbbbbbbbbbbbbbbbbbbbbbbb'


class AttachTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.template = cls.directory / 'template'
        cls.anchors = workspace.initialize(cls.template, [
            {'id': 'counter', 'syntax': 'protocol-json@1',
             'source': (ROOT / 'protocols/counter/protocol.json').read_bytes(), 'law': [A]}],
             entry_objects=['counter'], principal=A, profile='transactions')

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(dir=self.directory)
        self.addCleanup(self.case.cleanup)
        self.home = Path(self.case.name)
        self.workspace = self.home / 'workspace'
        # Immutable source/history blobs may be shared; all custody writes use
        # atomic replacement. Never edit a hardlinked file in place in these tests.
        shutil.copytree(self.template, self.workspace, copy_function=os.link)
        self.state = self.home / 'clerk'
        self.records = {}
        self.calls = 0
        self.c = clerk.Clerk(self.state, self.pds)
        self.initial = clerk.loads((self.workspace / 'world.json').read_bytes())
        self.roots = {'counter': self.initial['objects']['counter']}
        self.arguments = {'expected_genesis': self.anchors['genesis'],
                          'expected_seed_head': self.anchors['head'], 'runtime_profile': 'transactions'}

    def pds(self, method, base, nsid, *, params):
        self.calls += 1
        author = params['repo']
        if nsid.endswith('describeRepo'):
            return {'did': author, 'didDoc': {'id': author, 'service': [{
                'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer', 'serviceEndpoint': clerk.PDS}]}}
        uri = f'at://{author}/{params["collection"]}/{params["rkey"]}'
        cid, value = self.records[uri]
        return {'uri': uri, 'cid': cid, 'value': value}

    def record(self, author, key, root):
        uri = f'at://{author}/{clerk.COLLECTION}/{key}'
        self.records[uri] = ('cid-' + key, {'$type': clerk.COLLECTION, 'profile': 'delvetalk-live-v1',
            'requestJson': clerk.world.wire_dumps({'object': 'counter', 'command': 'add',
                                                'input': {'amount': 2}, 'expected': root})})
        return uri, 'cid-' + key

    def attach(self, **overrides):
        return self.c.attach(self.workspace, self.roots, [A, B], **{**self.arguments, **overrides})

    def test_enrollment_preserves_world_law_and_receives_on_same_canonical_database(self):
        before = (self.workspace / 'world.json').read_bytes()
        result = self.attach()
        self.assertEqual(result['status'], 'attached')
        self.assertEqual((self.workspace / 'world.json').read_bytes(), before)
        self.assertFalse((self.state / 'world.json').exists())
        self.assertEqual(self.calls, 0)
        self.assertEqual(self.c.database, (self.workspace / 'world.json').resolve())
        self.assertEqual(self.c.config()['runtimeProfile'], 'transactions')
        self.assertEqual(self.c.execution_profile({'op': 'invoke'}), 'transactions')
        denied = self.c.receive(*self.record(B, 'denied', self.roots['counter']))
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        uri, cid = self.record(A, 'allowed', self.roots['counter'])
        committed = self.c.receive(uri, cid)
        self.assertEqual(committed['reply']['kind'], 'committed')
        restart = clerk.Clerk(self.state, self.pds)
        self.assertEqual(restart.database, self.c.database)
        self.records.clear()
        self.assertEqual(restart.receive(uri, cid), committed)
        self.assertEqual(restart.snapshot('counter')['root']['state']['count'], 2)
        self.assertEqual(restart.snapshot('counter')['root']['law'], [A])
        self.assertEqual(self.attach()['status'], 'already-attached')
        self.assertEqual(self.c.upgrade(self.c.profile()['sha256'])['status'], 'unchanged')

    def test_exact_roots_genesis_seed_runtime_and_local_world_collisions_refuse(self):
        for options in ({'expected_genesis': '0' * 64}, {'expected_seed_head': '0' * 64},
                        {'runtime_profile': 'compiled'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.attach(**options)
        with self.assertRaisesRegex(ValueError, 'root mismatch'):
            self.c.attach(self.workspace, {'counter': {}}, [A], **self.arguments)
        self.assertFalse((self.state / 'clerk.json').exists())
        clerk.save(self.state / 'world.json', {'objects': {}, 'receipts': []})
        before = (self.state / 'world.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'different world'):
            self.attach()
        self.assertEqual((self.state / 'world.json').read_bytes(), before)

    def test_reconstruction_refuses_forged_current_state_even_when_supplied_root_matches(self):
        forged = clerk.loads((self.workspace / 'world.json').read_bytes())
        forged['objects']['counter']['state']['count'] = 99
        clerk.save(self.workspace / 'world.json', forged)
        self.roots = forged['objects']
        with self.assertRaisesRegex(ValueError, 'reconstructed'):
            self.attach()
        self.assertFalse((self.state / 'clerk.json').exists())
        self.assertEqual(clerk.loads((self.workspace / 'world.json').read_bytes()), forged)

    def test_valid_suffix_is_replayed_and_wrong_seed_prefix_is_refused(self):
        root = self.roots['counter']
        request = {'op': 'invoke', 'object': 'counter', 'principal': A, 'intent': 'before-attach',
                   'expected': root, 'command': 'add', 'input': {'amount': 7}}
        reply = clerk.world.exchange(self.workspace / 'world.json', request, profile='transactions')
        self.roots = {'counter': reply['data']['root']}
        self.assertEqual(self.attach()['attachment']['entries'], 2)
        different = self.home / 'different'
        shutil.copytree(self.workspace, different, copy_function=os.link)
        with self.assertRaisesRegex(ValueError, 'different attachment'):
            self.c.attach(different, self.roots, [A, B], **self.arguments)
        other = clerk.Clerk(self.home / 'other-clerk')
        corrupted = clerk.loads((different / 'world.json').read_bytes())
        corrupted['receipts'][0]['request']['intent'] = 'different-seed'
        clerk.save(different / 'world.json', corrupted)
        with self.assertRaisesRegex(ValueError, 'seed prefix'):
            other.attach(different, self.roots, [A, B], **self.arguments)

    def test_config_commit_interruption_is_retryable_without_world_writes(self):
        before = (self.workspace / 'world.json').read_bytes()
        original = clerk.save
        def fail_before(path, value):
            if path == (self.state / 'clerk.json').resolve():
                raise OSError('before attachment commit')
            return original(path, value)
        with patch.object(clerk, 'save', fail_before), self.assertRaises(OSError):
            self.attach()
        self.assertFalse((self.state / 'clerk.json').exists())
        def fail_after(path, value):
            original(path, value)
            if path == (self.state / 'clerk.json').resolve():
                raise OSError('lost attachment reply')
        with patch.object(clerk, 'save', fail_after), self.assertRaises(OSError):
            self.attach()
        self.assertEqual(self.attach()['status'], 'already-attached')
        self.assertEqual((self.workspace / 'world.json').read_bytes(), before)

    def test_cli_attachment_and_bound_path_cannot_follow_retargeted_symlink(self):
        roots = self.home / 'roots.json'
        clerk.save(roots, self.roots)
        command = [sys.executable, str(ROOT / 'scripts/clerk.py'), '--state', str(self.state), 'attach',
                   '--workspace', str(self.workspace), '--expected-roots', str(roots), '--repository', A,
                   '--genesis', self.anchors['genesis'], '--seed-head', self.anchors['head'],
                   '--runtime-profile', 'transactions']
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(clerk.loads(result.stdout)['status'], 'attached')
        database = self.workspace / 'world.json'
        elsewhere = self.home / 'elsewhere.json'
        database.rename(elsewhere)
        database.symlink_to(elsewhere)
        with self.assertRaisesRegex(ValueError, 'canonical path'):
            _ = clerk.Clerk(self.state).database


if __name__ == '__main__':
    unittest.main()
