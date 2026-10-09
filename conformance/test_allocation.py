#!/usr/bin/env python3
"""Governed allocation through built Lean admission and durable file custody."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('allocation_transport', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)
PROFILES = ('world', 'transactions', 'compiled')


def child_protocol():
    return {'profile': 'delvetalk-local-v1', 'initial': {'text': 'new'}, 'commands': {
        'write': {'require': [], 'set': {'text': ['input', 'text']},
                  'result': ['state', 'text'], 'outbox': []}}}


def factory_protocol(limit=2, child=None, child_law=None):
    return {'profile': 'delvetalk-local-v1', 'initial': {'last': 'none'},
            'allocation': {'limit': limit}, 'commands': {
        'make': {'require': [], 'set': {'last': ['input', 'name']},
                 'result': ['record', {'name': ['input', 'name'], 'by': ['principal']}],
                 'outbox': [['literal', 'created']], 'allocate': [{
                     'name': ['input', 'name'],
                     'protocol': ['literal', child if child is not None else child_protocol()],
                     'law': ['array', [['principal']]] if child_law is None else ['literal', child_law]}]}}}


def factory_law():
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'make': ['alice']},
            'reprogram': ['manager'], 'law': ['manager']}


class AllocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.serial = 0
        for profile in PROFILES:
            self.assertTrue((ROOT / '.lake/build/bin' / world.PROFILES[profile][0]).exists(),
                            'Build Lean receivers first; allocation tests do not spawn compilers')

    def seed(self, profile='world', protocol=None):
        self.serial += 1
        self.profile = profile
        self.db = Path(self.tmp.name) / f'{profile}-{self.serial}.json'
        self.root = self.create('factory', protocol if protocol is not None else factory_protocol(),
                                factory_law())['data']['root']

    def call(self, request):
        return world.exchange(self.db, request, profile=self.profile)

    def create(self, name, protocol, law):
        return self.call({'op': 'create', 'object': name, 'principal': 'bootstrap',
                          'intent': 'create-' + name, 'protocol': protocol, 'law': law})

    def inspect(self, name='factory'):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def objects(self):
        return world.wire_loads(self.db.read_text())['objects']

    def make(self, name='one', intent='make', **changes):
        return {'op': 'invoke', 'object': 'factory', 'principal': 'alice', 'intent': intent,
                'expected': self.root, 'command': 'make', 'input': {'name': name},
                'absent': ['factory/' + name], **changes}

    def transaction(self, **changes):
        return {'op': 'transaction', 'principal': 'alice', 'intent': 'compose',
                'reads': {'factory': self.root, 'factory/one': None, 'factory/unused': None},
                'calls': [{'object': 'factory', 'command': 'make', 'input': {'name': 'one'}},
                          {'object': 'factory/one', 'command': 'write', 'input': {'text': 'inhabited'}}],
                **changes}

    def test_factory_creates_child_atomically_under_explicit_child_law(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                receipt = self.call(self.make())
                self.assertEqual(receipt['kind'], 'committed')
                child = self.inspect('factory/one')
                self.assertEqual(receipt['data']['allocated'], {'factory/one': child})
                self.assertEqual(child, {'protocol': child_protocol(), 'state': {'text': 'new'},
                                         'law': ['alice'], 'version': 0})
                self.assertEqual(receipt['data']['root'], self.inspect())
                self.assertEqual(self.inspect()['state'], {'last': 'one'})
                self.assertEqual(receipt['data']['result'], {'name': 'one', 'by': 'alice'})
                self.assertEqual(receipt['data']['outbox'], ['created'])
                write = {'op': 'invoke', 'object': 'factory/one', 'principal': 'alice',
                         'intent': 'write', 'expected': child, 'command': 'write', 'input': {'text': 'hello'}}
                self.assertEqual(self.call(write)['kind'], 'committed')
                self.assertNotIn('allocated', self.call(write)['data'])

    def test_current_factory_law_and_predicate_have_no_creator_bypass(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                for principal in ['bootstrap', 'manager', 'mallory']:
                    self.assertEqual(self.call(self.make(intent=principal, principal=principal))['data'],
                                     'unauthorized')
                law = factory_law()
                law['predicate'] = ['lam', ['boolean', False]]
                self.root = self.call({'op': 'law', 'object': 'factory', 'principal': 'manager',
                    'intent': 'deny-predicate', 'expected': self.root, 'law': law})['data']['root']
                self.assertEqual(self.call(self.make(intent='predicate'))['data'], 'authority predicate refused')
                self.assertEqual(set(self.objects()), {'factory'})

    def test_explicit_empty_child_law_has_no_creator_or_factory_manager_bypass(self):
        self.seed(protocol=factory_protocol(child_law=[]))
        receipt = self.call(self.make())
        child = receipt['data']['allocated']['factory/one']
        self.assertEqual(child['law'], [])
        for principal in ['alice', 'manager', 'bootstrap']:
            write = {'op': 'invoke', 'object': 'factory/one', 'principal': principal,
                     'intent': 'write-' + principal, 'expected': child,
                     'command': 'write', 'input': {'text': 'forbidden'}}
            self.assertEqual(self.call(write)['data'], 'unauthorized')
        self.assertEqual(self.inspect('factory/one'), child)

    def test_missing_or_stale_absence_and_stale_parent_refuse_without_allocation(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                missing = self.make(intent='missing')
                del missing['absent']
                self.assertEqual(self.call(missing)['data'], 'allocation target missing absence root')
                receipt = self.call(self.make())
                self.root = receipt['data']['root']
                before = self.objects()
                self.assertEqual(self.call(self.make(intent='collision'))['data'], 'stale absence root')
                old = copy.deepcopy(self.root)
                old['state']['last'] = 'none'
                self.assertEqual(self.call(self.make('two', 'stale-parent', expected=old))['data'], 'stale read root')
                self.assertEqual(self.objects(), before)

    def test_namespace_cannot_escape_or_smuggle_paths(self):
        self.seed()
        for index, name in enumerate(['', '..', '../escape', 'one/two', '/other', '.', 'é', 'a' * 65]):
            with self.subTest(name=name):
                receipt = self.call(self.make(name, 'bad-' + str(index)))
                self.assertEqual(receipt['data'], 'invalid child name')
                self.assertEqual(self.objects(), {'factory': self.root})
        self.assertEqual(self.call(self.make('A-z_09', 'valid'))['kind'], 'committed')

    def test_direct_child_quota_is_shared_across_callers_and_counts_bootstrap_children(self):
        self.seed(protocol=factory_protocol(limit=1))
        self.create('factory/operator-child', child_protocol(), [])
        self.assertEqual(self.call(self.make())['data'], 'factory child quota exhausted')
        self.assertEqual(self.inspect(), self.root)
        self.seed(protocol=factory_protocol(limit=1))
        # A deeper namespace is not a direct child or an aggregate-footprint claim.
        self.create('factory/scope/nested', child_protocol(), [])
        first = self.call(self.make())
        self.assertEqual(first['kind'], 'committed')
        self.root = first['data']['root']
        self.assertEqual(self.call(self.make('two', 'over-quota'))['data'], 'factory child quota exhausted')

    def test_quota_reprogramming_uses_current_policy_and_no_hidden_reset(self):
        self.seed(protocol=factory_protocol(limit=1))
        self.root = self.call(self.make())['data']['root']
        self.root = self.call({'op': 'reprogram', 'object': 'factory', 'principal': 'manager',
            'intent': 'increase', 'expected': self.root, 'protocol': factory_protocol(limit=2),
            'state': self.root['state']})['data']['root']
        self.root = self.call(self.make('two', 'second'))['data']['root']
        self.assertEqual(self.call(self.make('three', 'third'))['data'], 'factory child quota exhausted')

    def test_bad_late_child_or_duplicate_rolls_back_entire_allocation_batch(self):
        for duplicate in [False, True]:
            with self.subTest(duplicate=duplicate):
                protocol = factory_protocol(limit=3)
                second = copy.deepcopy(protocol['commands']['make']['allocate'][0])
                if not duplicate:
                    second['name'] = ['literal', 'two']
                    second['law'] = ['literal', {'profile': 'unknown'}]
                protocol['commands']['make']['allocate'].append(second)
                self.seed(protocol=protocol)
                refusal = self.call(self.make(absent=['factory/one', 'factory/two']))
                self.assertEqual(refusal['kind'], 'refused')
                self.assertEqual(self.objects(), {'factory': self.root})
                self.assertEqual(self.call(self.make(absent=['factory/one', 'factory/two'])), refusal)

    def test_quota_is_checked_against_staged_children_in_one_batch(self):
        protocol = factory_protocol(limit=1)
        second = copy.deepcopy(protocol['commands']['make']['allocate'][0])
        second['name'] = ['literal', 'two']
        protocol['commands']['make']['allocate'].append(second)
        self.seed(protocol=protocol)
        refusal = self.call(self.make(absent=['factory/one', 'factory/two']))
        self.assertEqual(refusal['data'], 'factory child quota exhausted')
        self.assertEqual(self.objects(), {'factory': self.root})

    def test_allocation_expressions_use_parent_prestate_and_share_failure_boundary(self):
        protocol = factory_protocol()
        protocol['commands']['make']['allocate'][0]['name'] = ['state', 'last']
        self.seed(protocol=protocol)
        self.assertEqual(self.call(self.make(absent=['factory/none']))['kind'], 'committed')
        self.assertIn('factory/none', self.objects())
        protocol = factory_protocol()
        protocol['commands']['make']['allocate'][0]['law'] = ['bend', ['perform', ['label', 'forbidden']], []]
        self.seed(protocol=protocol)
        refusal = self.call(self.make())
        self.assertIn('effects are forbidden', refusal['data'])
        self.assertEqual(self.objects(), {'factory': self.root})

    def test_installation_rejects_malformed_unused_allocation_descriptors(self):
        self.seed()
        bad = []
        p = factory_protocol(); del p['allocation']; bad.append(p)
        p = factory_protocol(); p['allocation']['limit'] = -1; bad.append(p)
        p = factory_protocol(); p['allocation']['aggregate'] = True; bad.append(p)
        p = factory_protocol(); p['commands']['make']['allocate'][0]['owner'] = ['principal']; bad.append(p)
        p = factory_protocol(); del p['commands']['make']['allocate'][0]['law']; bad.append(p)
        p = factory_protocol(); p['commands']['make']['allocate'][0]['name'] = ['unknown']; bad.append(p)
        for index, protocol in enumerate(bad):
            with self.subTest(index=index):
                self.assertEqual(self.create('bad-' + str(index), protocol, [])['kind'], 'refused')
        self.assertEqual(self.objects(), {'factory': self.root})

    def test_transaction_creates_then_invokes_child_under_child_current_law(self):
        for profile in ['transactions', 'compiled']:
            with self.subTest(profile=profile):
                self.seed(profile)
                receipt = self.call(self.transaction())
                self.assertEqual(receipt['kind'], 'committed')
                self.assertEqual(receipt['data']['roots']['factory/one'], self.inspect('factory/one'))
                self.assertEqual(receipt['data']['roots']['factory/one']['version'], 1)
                self.assertEqual(receipt['data']['roots']['factory/one']['state'], {'text': 'inhabited'})
                self.assertIsNone(receipt['data']['roots']['factory/unused'])
                self.assertEqual(receipt['data']['outbox'], [{'object': 'factory', 'step': 0, 'payload': 'created'}])
                self.assertEqual(len(world.wire_loads(self.db.read_text())['receipts']), 2)

    def test_transaction_retains_creation_root_before_later_reprogramming(self):
        for profile in ['transactions', 'compiled']:
            with self.subTest(profile=profile):
                original = child_protocol()
                original['roomArtifact'] = {'source': 'original-room-source'}
                self.seed(profile, factory_protocol(child=original))
                replacement = child_protocol()
                replacement['initial'] = {'text': 'replacement-initial'}
                request = self.transaction()
                request['calls'][1] = {'op': 'reprogram', 'object': 'factory/one',
                                       'protocol': replacement, 'state': {'text': 'migrated'}}
                receipt = self.call(request)
                self.assertEqual(receipt['kind'], 'committed')
                self.assertEqual(receipt['data']['allocated'], {'factory/one': {
                    'protocol': original, 'law': ['alice'], 'version': 0,
                    'state': {'text': 'new'}}})
                final = receipt['data']['roots']['factory/one']
                self.assertEqual(final, self.inspect('factory/one'))
                self.assertEqual(final['protocol'], replacement)
                self.assertEqual(final['state'], {'text': 'migrated'})
                self.assertEqual(final['version'], 1)
                self.assertEqual(self.call(request), receipt)
                ordinary = {'op': 'transaction', 'principal': 'alice', 'intent': 'ordinary',
                            'reads': {'factory/one': final}, 'calls': [{
                                'object': 'factory/one', 'command': 'write', 'input': {'text': 'next'}}]}
                self.assertNotIn('allocated', self.call(ordinary)['data'])

    def test_nested_factory_allocates_under_its_own_direct_quota(self):
        self.seed('transactions', factory_protocol(limit=1, child=factory_protocol(limit=1)))
        request = {'op': 'transaction', 'principal': 'alice', 'intent': 'nested',
                   'reads': {'factory': self.root, 'factory/scope': None,
                             'factory/scope/leaf': None},
                   'calls': [{'object': 'factory', 'command': 'make', 'input': {'name': 'scope'}},
                             {'object': 'factory/scope', 'command': 'make', 'input': {'name': 'leaf'}}]}
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(set(receipt['data']['roots']),
                         {'factory', 'factory/scope', 'factory/scope/leaf'})
        self.assertEqual(self.inspect('factory/scope/leaf')['law'], ['alice'])
        self.assertEqual(self.inspect('factory/scope')['version'], 1)
        self.assertEqual(set(receipt['data']['allocated']), {'factory/scope', 'factory/scope/leaf'})
        self.assertEqual(receipt['data']['allocated']['factory/scope']['version'], 0)

    def test_later_transaction_failure_discards_created_children_and_parent_change(self):
        for profile in ['transactions', 'compiled']:
            for blocked in ['authority', 'missing-absence', 'quota']:
                with self.subTest(profile=profile, blocked=blocked):
                    self.seed(profile, factory_protocol(limit=0 if blocked == 'quota' else 2,
                                                       child_law=['bob'] if blocked == 'authority' else None))
                    request = self.transaction()
                    if blocked == 'missing-absence':
                        del request['reads']['factory/one']
                    self.assertEqual(self.call(request)['kind'], 'refused')
                    self.assertEqual(self.objects(), {'factory': self.root})

    def test_transaction_absence_checked_before_calls_and_exact_replay_survives_revocation(self):
        self.seed('transactions')
        request = self.transaction()
        receipt = self.call(request)
        before = self.objects()
        other = copy.deepcopy(request)
        other['intent'] = 'occupied'
        other['reads']['factory'] = self.inspect()
        other['calls'][0]['command'] = 'missing'
        self.assertEqual(self.call(other)['data'], 'stale absence root')
        self.assertEqual(self.objects(), before)
        self.call({'op': 'law', 'object': 'factory', 'principal': 'manager', 'intent': 'lock',
                   'expected': self.inspect(), 'law': []})
        self.assertEqual(self.call(request), receipt)
        changed = copy.deepcopy(request); changed['calls'][0]['input']['name'] = 'different'
        self.assertEqual(self.call(changed)['data'], 'intent reused for different request')

    def test_lost_commit_reply_replays_without_second_child_or_parent_advance(self):
        self.seed()
        request = self.make()
        real_fsync = world.os.fsync
        count = 0
        def fsync(fd):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('lost allocation reply after durable replace')
            return real_fsync(fd)
        with mock.patch.object(world.os, 'fsync', side_effect=fsync):
            with self.assertRaisesRegex(OSError, 'lost allocation reply'):
                self.call(request)
        receipt = world.wire_loads(self.db.read_text())['receipts'][-1]['receipt']
        self.assertEqual(self.call(request), receipt)
        self.assertEqual(self.inspect()['version'], 1)
        self.assertEqual(self.inspect('factory/one')['version'], 0)
        self.assertEqual(set(self.objects()), {'factory', 'factory/one'})


if __name__ == '__main__':
    unittest.main()
