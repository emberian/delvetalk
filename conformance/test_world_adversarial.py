#!/usr/bin/env python3
"""Independent local-host counterexamples and deterministic custody fault injection.

These tests inject OS-operation failures, not real power loss. They exercise the
Python custody wrapper and the built Lean receiver without compiling Lean.
"""
from native_support import load_script
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
world = load_script(ROOT / 'scripts/world.py', 'adversarial_world_transport')
from test_authority import counter, law, source_object


class AdversarialWorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = counter()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'world.json'
        self.root = self.call({'op': 'create', 'object': 'page', 'principal': 'owner',
                              'intent': 'create', 'protocol': self.protocol,
                              'law': law(invoke={'add': ['owner']}, reprogram=['owner'], law=['owner'])})['data']['root']

    def call(self, request):
        return world.exchange(self.db, request, profile='compiled')

    def edit(self, intent='edit', principal='owner', root=None, amount=1):
        return {'op': 'invoke', 'object': 'page', 'principal': principal,
                'intent': intent, 'expected': self.root if root is None else root,
                'command': 'add', 'input': {'amount': amount}}

    def inspect(self):
        return self.call({'op': 'inspect', 'object': 'page', 'principal': 'observer'})



    def test_aba_requires_revision_even_when_application_state_returns(self):
        changed = self.call(self.edit())['data']['root']
        restored = self.call({'op': 'reprogram', 'object': 'page', 'principal': 'owner',
            'intent': 'restore', 'expected': changed, 'protocol': self.protocol,
            'state': self.root['state']})['data']['root']
        self.assertEqual(restored['state'], self.root['state'])
        self.assertEqual(restored['version'], self.root['version'] + 2)
        self.assertEqual(self.call(self.edit(intent='stale'))['data'], 'stale read root')

    def test_replace_failure_preserves_previous_file_and_retry_can_commit(self):
        before = self.db.read_bytes()
        request = self.edit()
        with mock.patch.object(world.os, 'replace', side_effect=OSError('injected before replace')):
            with self.assertRaisesRegex(OSError, 'injected before replace'):
                self.call(request)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.db.parent.iterdir()), ['world.json', 'world.json.lock'])
        committed = self.call(request)
        self.assertEqual(committed['kind'], 'committed')
        self.assertEqual(self.call(request), committed)
        self.assertEqual(self.inspect()['version'], 1)

    def test_post_replace_fsync_failure_is_uncertain_but_retry_recovers(self):
        real_fsync = world.os.fsync
        calls = 0
        def fsync(fd):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('injected directory fsync failure')
            return real_fsync(fd)
        request = self.edit()
        with mock.patch.object(world.os, 'fsync', side_effect=fsync):
            with self.assertRaisesRegex(OSError, 'injected directory fsync failure'):
                self.call(request)
        # This is process-visible persistence, not a claim about surviving power loss.
        retained = world.wire_loads(self.db.read_text())['receipts'][-1]['receipt']
        self.assertEqual(retained['kind'], 'committed')
        self.assertEqual(self.call(request), retained)
        self.assertEqual(self.inspect()['version'], 1)

    def test_large_finite_nat_crosses_receiver_and_persisted_root(self):
        request = self.edit(amount=10 ** 4400)
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['root']['state'], {'model': source_object.data({'count': 10 ** 4400})})
        self.assertEqual(self.call(request), receipt)
        self.assertEqual(self.inspect(), receipt['data']['root'])

    def test_transport_failure_does_not_replace_database(self):
        before = self.db.read_bytes()
        with mock.patch.object(world.process_custody, 'run_native', side_effect=OSError('injected receiver failure')):
            with self.assertRaisesRegex(OSError, 'injected receiver failure'):
                self.call(self.edit())
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.call(self.edit())['kind'], 'committed')


if __name__ == '__main__':
    unittest.main()
