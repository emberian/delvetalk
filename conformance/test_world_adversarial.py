#!/usr/bin/env python3
"""Independent local-host counterexamples and deterministic custody fault injection.

These tests inject OS-operation failures, not real power loss. They exercise the
Python custody wrapper and the built Lean receiver without compiling Lean.
"""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('adversarial_world_transport', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


class AdversarialWorldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'world.json'
        self.protocol = json.loads((ROOT / 'protocols/section-edit/protocol.json').read_text())
        self.root = self.call({'op': 'create', 'object': 'page', 'principal': 'owner',
                              'intent': 'create', 'protocol': self.protocol,
                              'law': ['owner']})['data']['root']

    def call(self, request):
        return world.exchange(self.db, request)

    def edit(self, intent='edit', principal='owner', root=None, text='changed'):
        return {'op': 'invoke', 'object': 'page', 'principal': principal,
                'intent': intent, 'expected': self.root if root is None else root,
                'command': 'edit', 'input': {'text': text}}

    def inspect(self):
        return self.call({'op': 'inspect', 'object': 'page', 'principal': 'observer'})

    def test_refused_identity_stays_refused_after_grant(self):
        denied = self.edit(principal='guest')
        refusal = self.call(denied)
        self.assertEqual(refusal['data'], 'unauthorized')
        grant = self.call({'op': 'law', 'object': 'page', 'principal': 'owner',
                           'intent': 'grant', 'expected': self.root,
                           'law': ['owner', 'guest']})
        self.assertEqual(grant['kind'], 'committed')
        self.assertEqual(self.call(denied), refusal)
        # Refreshing the root does not recycle the retained identity.
        refresh = self.edit(principal='guest', root=self.inspect())
        self.assertEqual(self.call(refresh)['data'], 'intent reused for different request')
        refresh['intent'] = 'new-attempt'
        self.assertEqual(self.call(refresh)['kind'], 'committed')

    def test_intent_binds_object_and_unknown_metadata(self):
        request = self.edit()
        receipt = self.call(request)
        for alteration in ({'object': 'another'}, {'annotation': 'different'}):
            with self.subTest(alteration=alteration):
                self.assertEqual(self.call({**request, **alteration})['data'],
                                 'intent reused for different request')
        # Intent names are scoped to principal, never accidentally global.
        second = self.call({**request, 'principal': 'guest'})
        self.assertEqual(second['data'], 'unauthorized')
        self.assertEqual(self.call(request), receipt)

    def test_aba_requires_revision_even_when_application_state_returns(self):
        baseline = self.call(self.edit(intent='baseline', text='A'))['data']['root']
        first = self.call(self.edit(root=baseline, text='B'))['data']['root']
        restored = self.call(self.edit(intent='restore', root=first, text='A'))['data']['root']
        self.assertEqual(restored['state'], baseline['state'])
        self.assertEqual(restored['version'], baseline['version'] + 2)
        self.assertEqual(self.call(self.edit(intent='stale', root=baseline))['data'], 'stale read root')

    def test_claimed_authority_in_expected_root_cannot_grant(self):
        forged = copy.deepcopy(self.root)
        forged['law'].append('guest')
        result = self.call(self.edit(principal='guest', root=forged))
        self.assertEqual(result['data'], 'unauthorized')
        self.assertEqual(self.inspect(), self.root)

    def test_failure_in_last_outbox_entry_rolls_back_all_writes_and_intents(self):
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {'kept': 'old'},
                    'commands': {'run': {'require': [], 'set': {'kept': ['literal', 'new']},
                        'result': ['literal', 'would succeed'],
                        'outbox': [['literal', {'post': 'first'}],
                                   ['bend', ['perform', ['label', 'late-effect']], []]]}}}
        created = self.call({'op': 'create', 'object': 'atomic', 'principal': 'owner',
                             'intent': 'create-atomic', 'protocol': protocol, 'law': ['owner']})
        root = created['data']['root']
        request = {'op': 'invoke', 'object': 'atomic', 'principal': 'owner', 'intent': 'run',
                   'expected': root, 'command': 'run', 'input': {}}
        refusal = self.call(request)
        self.assertEqual(refusal['kind'], 'refused')
        self.assertIn('effects are forbidden', refusal['data'])
        stored = world.wire_loads(self.db.read_text())
        self.assertEqual(stored['objects']['atomic'], root)
        self.assertEqual(stored['receipts'][-1]['receipt'], refusal)
        self.assertNotIn('outbox', refusal)
        self.assertEqual(self.call(request), refusal)

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

    def test_large_finite_nat_crosses_receiver_boundary_without_decimal_cap(self):
        # Each literal is below Python's default cap; their product is above it.
        # Source and expected-root request remain comfortably below 64 KiB.
        natural = ['nat', '1' + '0' * 2200]
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
            'grow': {'require': [], 'set': {},
                     'result': ['bend', ['binary', 'multiply', natural, natural], []],
                     'outbox': []}}}
        root = self.call({'op': 'create', 'object': 'large', 'principal': 'owner',
                          'intent': 'create-large', 'protocol': protocol,
                          'law': ['owner']})['data']['root']
        request = {'op': 'invoke', 'object': 'large', 'principal': 'owner',
                   'intent': 'grow', 'expected': root, 'command': 'grow', 'input': {}}
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(receipt['data']['result'], 10 ** 4400)
        self.assertEqual(self.call(request), receipt)

    def test_transport_failure_does_not_replace_database(self):
        before = self.db.read_bytes()
        with mock.patch.object(world.subprocess, 'run', side_effect=OSError('injected receiver failure')):
            with self.assertRaisesRegex(OSError, 'injected receiver failure'):
                self.call(self.edit())
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.call(self.edit())['kind'], 'committed')


if __name__ == '__main__':
    unittest.main()
