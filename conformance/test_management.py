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
spec = importlib.util.spec_from_file_location('management_test', ROOT / 'scripts/manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)
clerk = manage.clerk
A = 'did:plc:aaaaaaaaaaaaaaaaaaaaaaaa'
B = 'did:plc:bbbbbbbbbbbbbbbbbbbbbbbb'


class ManagementTests(unittest.TestCase):
    def setUp(self):
        if not (ROOT / '.lake/build/bin/delvetalk-world').is_file():
            self.fail('build delvetalk-world before running management tests')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.records = {}
        self.fetches = 0
        self.c = clerk.Clerk(self.state, self.pds)
        self.m = manage.Management(self.state)
        protocol = clerk.loads((ROOT / 'protocols/counter/protocol.json').read_text())
        self.root = self.c.bootstrap('counter', protocol, [A], [A])['data']['root']

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
                          self.c.snapshot('counter') if root is None else root, law)

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
        self.assertEqual(self.c.snapshot('counter')['root']['law'], [])
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
        def blocked(database, request):
            if request['op'] == 'invoke':
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('test synchronization timeout')
            return original(database, request)
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
        denied = subprocess.run(command + [*args[:args.index('--intent')], '--intent', 'denied', '--expected-root', str(snapshot), '--allow', A], capture_output=True, text=True)
        self.assertEqual(denied.returncode, 2, denied.stderr)
        self.assertEqual(json.loads(denied.stdout)['reply']['data'], 'unauthorized')

    def program(self, intent='program', principal=A, root=None, state=b'{"welcome":null}'):
        return self.m.reprogram('counter', principal, intent, root or self.root, 'protocol-json@1',
                               (ROOT / 'protocols/welcome-once/protocol.json').read_bytes(), state)

    def test_reprogram_installs_source_and_complete_state_under_current_law(self):
        receipt = self.program()
        self.assertEqual(receipt['reply']['kind'], 'committed')
        root = receipt['reply']['data']['root']
        self.assertEqual(root['law'], [A])
        self.assertEqual(root['state'], {'welcome': None})
        self.assertEqual(root['version'], 1)
        self.assertEqual(set(receipt['request']), {'op', 'object', 'principal', 'intent', 'expected', 'protocol', 'state'})
        artifact = receipt['program']['artifact']
        self.assertEqual(artifact['source']['text'], (ROOT / 'protocols/welcome-once/protocol.json').read_text())
        self.assertIn('syntaxes/adapters.py', artifact['translation']['files'])
        uri, cid = self.record(A, 'new-program', root)
        payload = {'object': 'counter', 'command': 'knock', 'input': {'message': 'hello'}, 'expected': root}
        self.records[uri][1]['requestJson'] = clerk.world.wire_dumps(payload)
        invoked = self.c.receive(uri, cid)
        self.assertEqual(invoked['reply']['kind'], 'committed')
        self.assertEqual(invoked['reply']['data']['result'], 'welcomed')
        self.assertEqual(self.m.resume(A, 'program'), receipt)

    def test_reprogram_current_authority_stale_root_and_explicit_state(self):
        self.assertEqual(self.program('unauthorized', B)['reply']['data'], 'unauthorized')
        committed = self.program()
        self.assertEqual(self.program('stale')['reply']['data'], 'stale read root')
        current = committed['reply']['data']['root']
        invalid = self.program('bad-state', root=current, state=b'[]')
        self.assertEqual(invalid['reply']['kind'], 'refused')
        self.assertEqual(self.c.snapshot('counter')['root'], current)
        empty = self.program('explicit-empty', root=current, state=b'{}')
        self.assertEqual(empty['reply']['data']['root']['state'], {})
        self.revise('lockout-program', [])
        self.assertEqual(self.program('locked')['reply']['data'], 'unauthorized')

    def test_reprogram_exact_source_binding_and_replay_without_translation(self):
        receipt = self.program()
        with patch.object(manage.translation, 'translate', side_effect=AssertionError('must not retranslate')):
            self.assertEqual(self.program(), receipt)
            self.assertEqual(self.m.resume(A, 'program'), receipt)
        with self.assertRaisesRegex(ValueError, 'different request or source'):
            self.m.reprogram('counter', A, 'program', self.root, 'protocol-json@1',
                             (ROOT / 'protocols/welcome-once/protocol.json').read_bytes() + b'\n', b'{"welcome":null}')
        with self.assertRaisesRegex(ValueError, 'different request or source'):
            self.program(state=b'{"welcome": null}')
        with self.assertRaisesRegex(ValueError, 'different request'):
            self.revise('program', [A], root=self.root)

    def test_pending_reprogram_keeps_artifact_and_blocks_upgrade(self):
        original_save = clerk.save
        def lose_receipt(path, value):
            if 'artifact' in value and 'receipt' in value:
                raise OSError('lost reprogram reply')
            original_save(path, value)
        with patch.object(clerk, 'save', lose_receipt):
            with self.assertRaisesRegex(OSError, 'lost reprogram'):
                self.program()
        with self.assertRaisesRegex(ValueError, 'pending request'):
            self.c.upgrade(self.c.profile()['sha256'])
        with patch.object(manage, 'translation_current', side_effect=ValueError('translation pins changed')):
            with self.assertRaisesRegex(ValueError, 'translation pins changed'):
                self.m.resume(A, 'program')
        with patch.object(manage.translation, 'translate', side_effect=AssertionError('must not retranslate')):
            receipt = self.m.resume(A, 'program')
        self.assertEqual(receipt['reply']['data']['root']['version'], 1)
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)

    def test_reprogram_cli_distinguishes_custody_directory_and_state_file(self):
        snapshot = self.state / 'snapshot.json'
        snapshot.write_text(clerk.world.wire_dumps(self.c.snapshot('counter')))
        state_file = self.state / 'new-state.json'
        state_file.write_text('{"welcome":null}')
        command = [sys.executable, str(ROOT / 'scripts/manage.py'), '--state', str(self.state),
                   'reprogram', '--object', 'counter', '--principal', A, '--intent', 'cli-program',
                   '--expected-root', str(snapshot), '--source', str(ROOT / 'protocols/welcome-once/protocol.json'),
                   '--syntax', 'protocol-json@1', '--state', str(state_file)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt['request']['state'], {'welcome': None})
        self.assertEqual(receipt['reply']['kind'], 'committed')

    def test_oversize_request_does_not_reserve_unrecoverable_intent(self):
        with self.assertRaisesRegex(ValueError, 'request exceeds 64 KiB'):
            self.program('oversized', state=b'{"padding":"' + b'x' * 65000 + b'"}')
        self.assertFalse(self.m.path(A, 'oversized').exists())
        self.assertEqual(self.c.snapshot('counter')['root'], self.root)


if __name__ == '__main__':
    unittest.main()
