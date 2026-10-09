"""Independent management identity and recovery checks; no external operations."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manage_adversarial', ROOT / 'scripts/manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)
clerk = manage.clerk
A = 'did:plc:aaaaaaaaaaaaaaaaaaaaaaaa'
B = 'did:plc:bbbbbbbbbbbbbbbbbbbbbbbb'
desk = clerk.module('desk_adversarial', 'scripts/desk.py')


class ManagementAdversarial(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.c = clerk.Clerk(self.state)
        self.m = manage.Management(self.state)
        protocol = clerk.loads((ROOT / 'protocols/counter/protocol.json').read_text())
        self.root = self.c.bootstrap('counter', protocol, [A], [A, B])['data']['root']

    def test_same_intent_string_has_distinct_principal_identity(self):
        refused = self.m.law('counter', B, 'shared-intent', self.root, [B])
        accepted = self.m.law('counter', A, 'shared-intent', self.root, [A, B])
        self.assertEqual(refused['reply']['data'], 'unauthorized')
        self.assertEqual(accepted['reply']['kind'], 'committed')
        self.assertNotEqual(self.m.path(A, 'shared-intent'), self.m.path(B, 'shared-intent'))
        self.assertEqual(self.m.resume(B, 'shared-intent'), refused)
        self.assertEqual(self.m.resume(A, 'shared-intent'), accepted)

    def pending(self):
        with patch.object(clerk.world, 'exchange', side_effect=OSError('before admission')):
            with self.assertRaises(OSError):
                self.m.law('counter', A, 'pending', self.root, [A, B])

    def test_management_source_change_blocks_pending_and_upgrade(self):
        self.pending()
        before = self.c.database.read_bytes()
        with patch.object(manage, 'management_profile', return_value={'changed': True}):
            with self.assertRaisesRegex(ValueError, 'management implementation pins changed'):
                self.m.resume(A, 'pending')
            with self.assertRaisesRegex(ValueError, 'pending request'):
                self.c.upgrade(self.c.profile()['sha256'])
        self.assertEqual(before, self.c.database.read_bytes())
        self.assertEqual(self.m.resume(A, 'pending')['reply']['kind'], 'committed')

    def test_pending_local_assertion_faces_revocation_before_resume(self):
        self.pending()
        reply = clerk.world.exchange(self.c.database, {'op': 'law', 'object': 'counter',
            'principal': A, 'intent': 'independent-revocation', 'expected': self.root, 'law': []})
        self.assertEqual(reply['kind'], 'committed')
        before = self.c.snapshot('counter')['root']
        refused = self.m.resume(A, 'pending')
        self.assertEqual(refused['reply']['data'], 'unauthorized')
        self.assertEqual(self.c.snapshot('counter')['root'], before)
        self.assertEqual(self.m.resume(A, 'pending'), refused)

    def program(self, intent='program', source=None):
        source = source if source is not None else (ROOT / 'protocols/counter/protocol.json').read_bytes()
        return self.m.reprogram('counter', A, intent, self.root, 'protocol-json@1', source, b'{"count":10}')

    def test_equal_lowering_does_not_erase_source_identity(self):
        accepted = self.program()
        self.assertEqual(accepted['reply']['kind'], 'committed')
        same_protocol_different_source = (ROOT / 'protocols/counter/protocol.json').read_bytes() + b'\n'
        with self.assertRaisesRegex(ValueError, 'different request or source'):
            self.program(source=same_protocol_different_source)
        self.assertEqual(self.m.resume(A, 'program'), accepted)
        self.assertEqual(accepted['program']['artifact']['source']['text'],
                         (ROOT / 'protocols/counter/protocol.json').read_text())
        self.assertEqual(accepted['program']['stateSource']['text'], '{"count":10}')

    def test_law_and_program_cannot_reuse_one_management_identity(self):
        accepted = self.m.law('counter', A, 'shared-operation', self.root, [A])
        with self.assertRaisesRegex(ValueError, 'different request or source'):
            self.program('shared-operation')
        self.assertEqual(self.m.resume(A, 'shared-operation'), accepted)

    def test_pending_program_keeps_artifact_and_checks_translation_before_resume(self):
        with patch.object(clerk.world, 'exchange', side_effect=OSError('before program admission')):
            with self.assertRaises(OSError):
                self.program()
        path = self.m.path(A, 'program')
        pending = path.read_bytes()
        with patch.object(manage, 'translation_current', side_effect=ValueError('translation pins changed')):
            with self.assertRaisesRegex(ValueError, 'translation pins changed'):
                self.m.resume(A, 'program')
        self.assertEqual(path.read_bytes(), pending)
        self.assertEqual(self.c.snapshot('counter')['root'], self.root)
        with patch.object(manage.translation, 'translate', side_effect=AssertionError('must not retranslate')):
            accepted = self.m.resume(A, 'program')
        self.assertEqual(accepted['reply']['kind'], 'committed')
        with patch.object(manage, 'translation_current', side_effect=ValueError('now upgraded')):
            self.assertEqual(self.m.resume(A, 'program'), accepted)

    def desk_candidate(self):
        worker = desk.Desk(self.c.database, self.state / 'builds')
        empty = worker.create('candidate', A, 'create-candidate', [A])['data']['root']
        source = (ROOT / 'protocols/counter/protocol.json').read_bytes()
        pending = worker.submit('candidate', A, 'submit-candidate', empty, 'protocol-json@1',
                                source, b'[]', {'count': 3}, 'counter')['data']['root']
        build = {'format': 'delvetalk-desk-build-v1', 'passed': True,
                 'candidateRootSha256': desk.digest(pending), 'protocol': clerk.loads(source)}
        return worker, pending, build

    def test_pending_desk_admission_cannot_cross_runtime_change(self):
        worker, pending, build = self.desk_candidate()
        with patch.object(desk, 'bounded_compile', return_value=build), patch.object(
                worker, 'exchange', side_effect=OSError('uncertain before admission')):
            with self.assertRaises(OSError):
                worker.check('candidate', A, 'compile', pending)
        before = self.c.database.read_bytes()
        with patch.object(desk, 'execution_profile', return_value={'different': True}):
            with self.assertRaisesRegex(ValueError, 'runtime pins changed'):
                worker.check('candidate', A, 'compile', pending)
        self.assertEqual(self.c.database.read_bytes(), before)
        with patch.object(desk, 'bounded_compile', side_effect=AssertionError('recompiled')):
            self.assertEqual(worker.check('candidate', A, 'compile', pending)['kind'], 'committed')

    def test_uncertain_committed_desk_reply_survives_runtime_change_without_execution(self):
        worker, pending, build = self.desk_candidate()
        exchange = worker.exchange
        committed = []
        def lose_reply(request):
            committed.append(exchange(request))
            raise OSError('lost committed reply')
        with patch.object(desk, 'bounded_compile', return_value=build), patch.object(worker, 'exchange', lose_reply):
            with self.assertRaises(OSError):
                worker.check('candidate', A, 'compile', pending)
        with patch.object(desk, 'execution_profile', return_value={'different': True}), patch.object(
                worker, 'exchange', side_effect=AssertionError('must not execute new engine')), patch.object(
                desk, 'load_artifact', side_effect=AssertionError('historical receipt needs no artifact')):
            self.assertEqual(worker.check('candidate', A, 'compile', pending), committed[0])

    @unittest.skipUnless(os.name == 'posix', 'process group custody')
    def test_desk_cancellation_kills_compiler_descendants(self):
        marker = self.state / 'child-pid'
        code = ('import subprocess,sys,time,pathlib; '
                'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
                f'pathlib.Path({str(marker)!r}).write_text(str(child.pid)); time.sleep(30)')
        popen = subprocess.Popen
        processes = []
        def start(_arguments, **kwargs):
            process = popen([sys.executable, '-c', code], **kwargs)
            processes.append(process)
            wait = process.wait
            def interrupt(*args, **kwargs):
                process.wait = wait  # Cleanup must use the real reaping operation.
                deadline = time.monotonic() + 3
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                if not marker.exists():
                    raise RuntimeError('test child did not start')
                raise KeyboardInterrupt()
            process.wait = interrupt
            return process
        try:
            with patch.object(desk.subprocess, 'Popen', start):
                with self.assertRaises(KeyboardInterrupt):
                    desk.bounded_compile(self.root)
            self.assertIsNotNone(processes[0].poll())
            child = int(marker.read_text())
            status = subprocess.run(['ps', '-o', 'stat=', '-p', str(child)], capture_output=True, text=True).stdout.strip()
            self.assertTrue(not status or status.startswith('Z'), 'compiler descendant survived cancellation')
        finally:
            for process in processes:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, 9)
                    except ProcessLookupError:
                        pass
                    process.wait()


if __name__ == '__main__':
    unittest.main()
