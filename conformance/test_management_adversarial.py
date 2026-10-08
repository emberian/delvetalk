"""Independent management identity and recovery checks; no external operations."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manage_adversarial', ROOT / 'scripts/manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)
clerk = manage.clerk
A = 'did:plc:aaaaaaaaaaaaaaaaaaaaaaaa'
B = 'did:plc:bbbbbbbbbbbbbbbbbbbbbbbb'


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


if __name__ == '__main__':
    unittest.main()
