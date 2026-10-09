#!/usr/bin/env python3
"""Local operator management, mock PDS observations, actual existing Lean executable."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from conformance.source_custody_fixture import counter_protocol, counter_source, scoped as current_law
spec = importlib.util.spec_from_file_location('management_test', ROOT / 'scripts/manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)
clerk = manage.clerk
A = 'did:plc:aaaaaaaaaaaaaaaaaaaaaaaa'
B = 'did:plc:bbbbbbbbbbbbbbbbbbbbbbbb'


class ManagementTests(unittest.TestCase):
    def setUp(self):
        if not (ROOT / '.lake/build/bin/delvetalk-compiled').is_file():
            self.fail('build delvetalk-compiled before running management tests')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.records = {}
        self.fetches = 0
        self.c = clerk.Clerk(self.state, self.pds)
        self.m = manage.Management(self.state)
        protocol = counter_protocol()
        self.root = self.c.bootstrap('counter', protocol, current_law([A]), [A])['data']['root']

    def pds(self, method, base, nsid, *, params):
        self.fetches += 1
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
                'input': {'amount': 1}, 'expected': root})})
        return uri, 'cid-' + key

    def revise(self, intent, law, principal=A, root=None):
        return self.m.law('counter', principal, intent,
                          self.c.snapshot('counter') if root is None else root, current_law(law) if isinstance(law, list) else law)

    def test_transport_enrollment_then_lean_authority(self):
        before = self.c.database.read_bytes()
        self.assertEqual(self.m.enrollment(B, True)['status'], 'changed')
        self.assertEqual(self.m.enrollment(B, True)['status'], 'unchanged')
        self.assertEqual(self.c.database.read_bytes(), before)
        refused = self.c.receive(*self.record(B, 'no-authority', self.root))
        self.assertEqual(refused['reply']['data'], 'unauthorized')
        self.assertEqual(self.revise('unauthorized-manager', [A, B], principal=B)['reply']['data'], 'unauthorized')
        revised = self.revise('enroll-law', [A, B])
        self.assertEqual(revised['reply']['kind'], 'committed')
        allowed = self.c.receive(*self.record(B, 'allowed', revised['reply']['data']['root']))
        self.assertEqual(allowed['reply']['kind'], 'committed')
        self.assertEqual(allowed['request']['principal'], B)
        self.assertEqual(revised['principalSource'], 'local-operator-assertion')

    def test_revocation_retains_receipts_and_enrollment(self):
        self.m.enrollment(B, True)
        root = self.revise('grant', [A, B])['reply']['data']['root']
        uri, cid = self.record(B, 'admitted', root)
        old = self.c.receive(uri, cid)
        revoked = self.revise('revoke', [A])
        self.assertIn(B, self.m.status()['repositories'])
        denial = self.c.receive(*self.record(B, 'revoked', revoked['reply']['data']['root']))
        self.assertEqual(denial['reply']['data'], 'unauthorized')
        self.m.enrollment(B, False)
        self.records.clear()
        count = self.fetches
        self.assertEqual(self.c.receive(uri, cid), old)
        self.assertEqual(self.fetches, count)
        with self.assertRaisesRegex(ValueError, 'not configured'):
            self.c.receive(*self.record(B, 'unenrolled', revoked['reply']['data']['root']))

    def test_empty_law_has_no_local_recovery_bypass(self):
        empty = self.revise('lockout', [])
        self.assertEqual(empty['reply']['kind'], 'committed')
        self.m.enrollment(B, True)
        for principal in (A, B):
            self.assertEqual(self.revise('no-rescue', [A], principal=principal)['reply']['data'], 'unauthorized')
        self.assertEqual(self.c.snapshot('counter')['root']['law'], current_law([]))
        self.assertEqual(self.m.resume(A, 'lockout'), empty)

    def test_exact_roots_stable_binding_and_historical_pin_replay(self):
        accepted = self.revise('one', [A, B], root=self.root)
        self.assertEqual(self.revise('one', [A, B], root=self.root), accepted)
        with self.assertRaisesRegex(ValueError, 'different request'):
            self.revise('one', [A], root=self.root)
        stale = self.revise('stale', [A], root=self.root)
        self.assertEqual(stale['reply']['data'], 'stale read root')
        with patch.object(clerk, 'pins', return_value={'different': 'pins'}):
            self.assertEqual(self.m.resume(A, 'one'), accepted)
            self.assertEqual(self.m.resume(A, 'stale'), stale)
            with self.assertRaisesRegex(ValueError, 'pins changed'):
                self.revise('new', [A], root=self.root)

    def test_uncertain_management_reply_and_upgrade_quiescence(self):
        original_save = clerk.save
        def lose_receipt(path, value):
            if path.name.startswith('management-') and 'receipt' in value:
                raise OSError('lost exported receipt')
            original_save(path, value)
        with patch.object(clerk, 'save', lose_receipt):
            with self.assertRaisesRegex(OSError, 'lost exported'):
                self.revise('uncertain', [A, B])
        self.assertEqual(self.m.status()['attempts'][0]['status'], 'pending')
        with self.assertRaisesRegex(ValueError, 'pending request'):
            self.c.upgrade(self.c.profile()['sha256'])
        receipt = self.m.resume(A, 'uncertain')
        self.assertEqual(receipt['reply']['data']['root']['version'], 1)
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)
        self.assertEqual(self.m.status()['attempts'][0]['status'], 'committed')

    def test_unenrollment_preserves_pre_admission_pending_attempt(self):
        uri, cid = self.record(A, 'pending', self.root)
        with patch.object(clerk.world, 'exchange', side_effect=OSError('before admission')):
            with self.assertRaises(OSError):
                self.c.receive(uri, cid)
        journal = next((self.state / 'requests').glob('*.json'))
        before = journal.read_bytes()
        self.m.enrollment(A, False)
        self.assertEqual(journal.read_bytes(), before)
        self.records.clear()
        self.assertEqual(self.c.receive(uri, cid)['reply']['kind'], 'committed')
        self.assertEqual(self.m.status()['repositories'], [])

    def test_pending_attempt_faces_current_law_after_revocation(self):
        uri, cid = self.record(A, 'pending', self.root)
        with patch.object(clerk.world, 'exchange', side_effect=OSError('before admission')):
            with self.assertRaises(OSError):
                self.c.receive(uri, cid)
        self.revise('remove-authority', [])
        self.m.enrollment(A, False)
        self.assertEqual(self.c.receive(uri, cid)['reply']['data'], 'unauthorized')

    def test_receive_and_management_share_serialization(self):
        entered, release, started = threading.Event(), threading.Event(), threading.Event()
        original = clerk.world.exchange
        output, failures = {}, []
        def blocked(database, request, **kwargs):
            if request['op'] == 'invoke':
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('test synchronization timeout')
            return original(database, request, **kwargs)
        def run(key, operation):
            try:
                output[key] = operation()
            except Exception as exc:
                failures.append(exc)
        uri, cid = self.record(A, 'concurrent', self.root)
        def law():
            started.set()
            return self.revise('concurrent-law', [], root=self.root)
        with patch.object(clerk.world, 'exchange', blocked):
            receiver = threading.Thread(target=run, args=('receive', lambda: self.c.receive(uri, cid)), daemon=True)
            manager = threading.Thread(target=run, args=('law', law), daemon=True)
            receiver.start()
            try:
                self.assertTrue(entered.wait(5))
                manager.start()
                self.assertTrue(started.wait(5))
                self.assertNotIn('law', output)
            finally:
                release.set()
                receiver.join(5)
                if manager.ident is not None:
                    manager.join(5)
            self.assertFalse(receiver.is_alive() or manager.is_alive(), 'custody deadlock')
        self.assertFalse(failures, failures)
        self.assertEqual(output['receive']['reply']['kind'], 'committed')
        self.assertEqual(output['law']['reply']['data'], 'stale read root')

    def test_cli_explicit_empty_law_and_resume(self):
        snapshot = self.state / 'snapshot.json'
        snapshot.write_text(clerk.world.wire_dumps(self.c.snapshot('counter')))
        command = [sys.executable, str(ROOT / 'scripts/manage.py'), '--state', str(self.state)]
        args = ['law', '--object', 'counter', '--principal', A, '--intent', 'cli', '--expected-root', str(snapshot)]
        missing = subprocess.run(command + args, capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)
        accepted = subprocess.run(command + args + ['--empty-law'], capture_output=True, text=True)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        recovered = subprocess.run(command + ['resume', '--principal', A, '--intent', 'cli'], capture_output=True, text=True)
        self.assertEqual(json.loads(accepted.stdout), json.loads(recovered.stdout))
        grant_path = self.state / 'grant.json'
        grant_path.write_text(clerk.world.wire_dumps(current_law([A])))
        denied = subprocess.run(command + [*args[:args.index('--intent')], '--intent', 'denied', '--expected-root', str(snapshot), '--law-file', str(grant_path)], capture_output=True, text=True)
        self.assertEqual(denied.returncode, 2, denied.stderr)
        self.assertEqual(json.loads(denied.stdout)['reply']['data'], 'unauthorized')

    def scoped(self):
        return {'profile': 'delvetalk-scoped-law', 'invoke': {'add': [B]},
                'reprogram': [A], 'law': [A]}

    def test_scoped_law_transport_and_command_authority(self):
        self.m.enrollment(B, True)
        receipt = self.revise('scoped', self.scoped())
        self.assertEqual(receipt['reply']['kind'], 'committed')
        root = receipt['reply']['data']['root']
        self.assertEqual(root['law'], self.scoped())
        self.assertEqual(self.c.receive(*self.record(B, 'scoped-add', root))['reply']['kind'], 'committed')
        self.assertEqual(self.revise('no-management', [B], principal=B)['reply']['data'], 'unauthorized')
        malformed = self.revise('malformed-law', {'profile': 'delvetalk-scoped-law'})
        self.assertEqual(malformed['reply']['kind'], 'refused')
        self.assertEqual(self.m.resume(A, 'malformed-law'), malformed)

    def add(self, object_id='desk', intent='create-desk', law=None):
        return self.m.add_object(object_id, A, intent, 'objective-bend-object', counter_source(),
                                 self.scoped() if law is None else law)

    def test_add_object_registers_only_after_success_and_keeps_existing_state(self):
        before = self.c.config()
        created = self.add()
        self.assertEqual(created['reply']['kind'], 'committed')
        self.assertEqual(created['registration'], {'object': 'desk', 'registered': True})
        after = self.c.config()
        self.assertEqual(after, {**before, 'objects': ['counter', 'desk']})
        self.assertEqual(self.c.snapshot('counter')['root'], self.root)
        self.assertEqual(self.c.snapshot('desk')['root']['law'], self.scoped())
        with patch.object(manage.translation, 'translate', side_effect=AssertionError('no retranslation')):
            self.assertEqual(self.add(), created)
        refused = self.add('invalid', 'invalid', law={'bogus': True})
        self.assertEqual(refused['reply']['kind'], 'refused')
        self.assertNotIn('invalid', self.c.config()['objects'])
        duplicate = self.add('desk', 'duplicate')
        self.assertEqual(duplicate['reply']['data'], 'object exists')
        self.assertFalse(duplicate['registration']['registered'])

    def test_add_object_recovers_world_config_and_receipt_boundaries(self):
        save = clerk.save
        for boundary in ('config', 'receipt'):
            with self.subTest(boundary=boundary):
                def fail(path, value):
                    if ((boundary == 'config' and path.name == 'clerk.json') or
                            (boundary == 'receipt' and 'receipt' in value)):
                        raise OSError('registration interruption')
                    save(path, value)
                with patch.object(clerk, 'save', fail):
                    with self.assertRaisesRegex(OSError, 'registration interruption'):
                        self.add(boundary, boundary)
                with self.assertRaisesRegex(ValueError, 'pending request'):
                    self.c.upgrade(self.c.profile()['sha256'])
                receipt = self.m.resume(A, boundary)
                self.assertTrue(receipt['registration']['registered'])
                self.assertEqual(self.c.snapshot(boundary)['root']['version'], 0)
                self.assertEqual(self.m.resume(A, boundary), receipt)

    def test_scoped_bootstrap_and_add_object_law_file_cli(self):
        law_path = self.state / 'law.json'
        law_path.write_text(clerk.world.wire_dumps(self.scoped()))
        protocol_path = self.state / 'source-counter.json'
        protocol_path.write_text(clerk.world.wire_dumps(counter_protocol()))
        source_path = self.state / 'source-counter.obend'
        source_path.write_bytes(counter_source())
        custody = self.state / 'scoped-clerk'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/clerk.py'), '--state', str(custody),
            'bootstrap', '--object', 'first', '--protocol', str(protocol_path),
            '--repository', B, '--law-file', str(law_path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['root']['law'], self.scoped())
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/manage.py'), '--state', str(custody),
            'add-object', '--object', 'second', '--principal', A, '--intent', 'cli-second',
            '--source', str(source_path), '--syntax', 'objective-bend-object',
            '--law-file', str(law_path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)['registration']['registered'])


if __name__ == '__main__':
    unittest.main()
