#!/usr/bin/env python3
"""Current source factories exercise the allocator's distinct custody boundaries."""
import copy
from functools import lru_cache
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
import world


def law(command='make', actors=('alice',), managers=('manager',)):
    return {'profile': 'delvetalk-scoped-law', 'invoke': {command: list(actors)},
            'reprogram': list(managers), 'law': list(managers),
            'read': ['alice', 'reader', 'manager', 'bootstrap', 'stranger']}


@lru_cache(maxsize=1)
def child_protocol():
    files = [('List', 'world/lib/prelude/List.obend'), ('Abi', 'world/lib/prelude/Abi.obend'),
             ('Encounter', 'world/lib/prelude/Encounter.obend'),
             ('Counter', 'conformance/fixtures/allocation/Counter.obend')]
    return source_object.load([{'name': name, 'source': (ROOT / path).read_text()} for name, path in files],
                              syntax='objective-bend-object')


def factory_protocol(limit=2, child=None, child_law=None, *, previous=False):
    files = [('List', 'world/lib/prelude/List.obend'), ('Abi', 'world/lib/prelude/Abi.obend'),
             ('Preparation', 'world/lib/prelude/Preparation.obend'),
             ('Encounter', 'world/lib/prelude/Encounter.obend'), ('Allocation', 'world/lib/prelude/Allocation.obend'),
             ('GateFactory', 'conformance/fixtures/allocation/GateFactory.obend')]
    config = source_object.record({'child': source_object.value(child_protocol() if child is None else child),
        'law': source_object.value(law('report') if child_law is None else child_law),
        'previous': source_object.data(previous)})
    result = source_object.load([{'name': name, 'source': (ROOT / path).read_text()} for name, path in files],
        syntax='objective-bend-object', constructor='initial', arguments=[config])
    result['allocation']['limit'] = limit
    return result


class AllocationTests(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.home = Path(home.name)
        self.serial = 0

    def call(self, request):
        return world.exchange(self.db, request, profile='compiled')

    def seed(self, program=None):
        self.serial += 1
        self.db = self.home / ('world-' + str(self.serial) + '.json')
        self.root = self.create('factory', factory_protocol() if program is None else program, law())['data']['root']

    def create(self, name, protocol, authority):
        return self.call({'op': 'create', 'object': name, 'principal': 'bootstrap',
                          'intent': 'create-' + name, 'protocol': protocol, 'law': authority})

    def inspect(self, name='factory'):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def objects(self):
        return world.wire_loads(self.db.read_text())['objects']

    def make(self, name='one', intent='make', *, second='', **changes):
        return {'op': 'invoke', 'object': 'factory', 'principal': 'alice', 'intent': intent,
                'expected': self.root, 'command': 'make', 'input': {'name': name, 'second': second},
                'absent': ['factory/' + name] + (['factory/' + second] if second else []), **changes}

    def test_stale_parent_and_missing_or_false_absence_refuse_before_allocation(self):
        self.seed()
        missing = self.make(intent='missing')
        missing.pop('absent')
        self.assertEqual(self.call(missing)['data'], 'allocation target missing absence root')
        self.root = self.call(self.make('one', 'first'))['data']['root']
        stale = copy.deepcopy(self.root)
        stale['version'] = 0
        self.assertEqual(self.call(self.make('two', 'stale-parent', expected=stale))['data'], 'stale read root')
        self.assertEqual(self.call(self.make('one', 'false-absence'))['data'], 'stale absence root')
        self.assertEqual(set(self.objects()), {'factory', 'factory/one'})

    def test_unused_malformed_allocation_policy_is_refused_at_installation(self):
        program = factory_protocol()
        for index, metadata in enumerate(({'limit': -1}, {'limit': 1, 'unknown': True},
                         {'limit': 1, 'owner': 'alice'}, {'limit': '1'})):
            with self.subTest(metadata=metadata):
                broken = copy.deepcopy(program)
                broken['allocation'] = metadata
                self.db = self.home / ('malformed-policy-' + str(index) + '.json')
                refusal = self.create('unused', broken, law())
                self.assertEqual(refusal['kind'], 'refused')
                expected = 'Natural number expected' if index in (0, 3) else 'unsupported allocation policy field'
                self.assertEqual(refusal['data'], expected)
                self.assertNotIn('unused', self.objects())
        self.db = self.home / 'valid-unused-policy.json'
        self.assertEqual(self.create('unused', program, law())['kind'], 'committed')

    def test_unused_descriptor_requires_law_and_cannot_contain_effectful_function(self):
        from conformance.test_typed_allocation import modules
        for field, value in (('', ''), (', law: (Nat) -> Nat', ', law: fn(x: Nat) -> Nat: x')):
            with self.subTest(field=field):
                sources = modules()
                sources[-1]['source'] = sources[-1]['source'].replace(
                    '  copy: {name: String, protocol: P.Value, law: P.Value}',
                    '  copy: {name: String, protocol: P.Value' + field + '}').replace(
                    'Child.copy({name: input.name, protocol: config.counter, law: config.law})',
                    'Child.copy({name: input.name, protocol: config.counter' + value + '})')
                message = 'allocation requires name, protocol, law' if not field else 'type is not serializable package data'
                with self.assertRaisesRegex(ValueError, message):
                    source_object.load(sources, syntax='objective-bend-object')

    def test_direct_quota_ignores_grandchildren_and_128_unrelated_roots(self):
        self.seed(factory_protocol(limit=1))
        self.assertEqual(self.create('factory/scope/nested', child_protocol(), law('report'))['kind'], 'committed')
        for index in range(128):
            self.assertEqual(self.create('unrelated-' + str(index), child_protocol(), law('report'))['kind'], 'committed')
        receipt = self.call(self.make())
        self.assertEqual(receipt['kind'], 'committed', receipt.get('data'))
        self.root = receipt['data']['root']
        self.assertEqual(self.call(self.make('two', 'quota'))['data'], 'factory child quota exhausted')
        self.assertEqual(self.inspect(), self.root)
        self.seed(factory_protocol(limit=1))
        self.create('factory/operator-child', child_protocol(), law('report'))
        self.assertEqual(self.call(self.make())['data'], 'factory child quota exhausted')

    def test_collision_precedes_quota_and_late_bad_batch_retains_atomic_refusal(self):
        self.seed(factory_protocol(limit=1))
        receipt = self.call(self.make())
        self.root = receipt['data']['root']
        # In one checked absence batch both descriptors refer to the staged child;
        # its collision must win before the already-exhausted quota check.
        self.seed(factory_protocol(limit=1))
        request = self.make(second='one')
        refusal = self.call(request)
        self.assertEqual(refusal['data'], 'object exists')
        self.assertEqual(self.objects(), {'factory': self.root})
        self.assertEqual(self.call(request), refusal)
        self.seed(factory_protocol(limit=3))
        request = self.make(second='bad/name')
        refusal = self.call(request)
        self.assertEqual(refusal['data'], 'invalid child name')
        self.assertEqual(self.objects(), {'factory': self.root})
        self.assertEqual(self.call(request), refusal)

    def test_second_call_counts_staged_children_and_rolls_back_both_steps(self):
        self.seed(factory_protocol(limit=1))
        request = {'op': 'transaction', 'principal': 'alice', 'intent': 'staged-quota',
            'reads': {'factory': self.root, 'factory/one': None, 'factory/two': None},
            'calls': [{'object': 'factory', 'command': 'make', 'input': {'name': 'one', 'second': ''}},
                      {'object': 'factory', 'command': 'make', 'input': {'name': 'two', 'second': ''}}]}
        refusal = self.call(request)
        self.assertEqual(refusal['data'], 'factory child quota exhausted')
        self.assertEqual(self.objects(), {'factory': self.root})
        self.assertEqual(self.call(request), refusal)

    def test_namespace_prestate_and_current_quota_revision(self):
        self.seed(factory_protocol(previous=True))
        receipt = self.call(self.make(absent=['factory/none']))
        self.assertEqual(receipt['kind'], 'committed', receipt.get('data'))
        self.assertIn('factory/none', self.objects())
        self.seed(factory_protocol(limit=1))
        for index, name in enumerate(('', '..', '../escape', 'one/two', '/other', '.', 'é', 'a' * 65)):
            refusal = self.call(self.make(name, 'bad-' + str(index)))
            self.assertEqual(refusal['data'], 'invalid child name')
            self.assertEqual(self.objects(), {'factory': self.root})
        self.root = self.call(self.make('A-z_09', 'valid'))['data']['root']
        revised = copy.deepcopy(self.root['protocol'])
        revised['allocation']['limit'] = 2
        self.root = self.call({'op': 'reprogram', 'object': 'factory', 'principal': 'manager',
            'intent': 'revise-quota', 'expected': self.root, 'protocol': revised, 'state': self.root['state']})['data']['root']
        self.root = self.call(self.make('two', 'after-revision'))['data']['root']
        self.assertEqual(self.call(self.make('three', 'full-again'))['data'], 'factory child quota exhausted')

    def test_child_lockout_and_management_do_not_bypass_current_invocation_grant(self):
        self.seed(factory_protocol(child_law=law('report', actors=(), managers=())))
        receipt = self.call(self.make())
        child = receipt['data']['allocated']['factory/one']
        for principal in ('alice', 'manager', 'bootstrap'):
            reply = self.call({'op': 'invoke', 'object': 'factory/one', 'principal': principal,
                'intent': 'locked-' + principal, 'expected': child, 'command': 'report', 'input': {}})
            self.assertEqual(reply['data'], 'unauthorized')
        for principal in ('bootstrap', 'manager', 'stranger'):
            self.assertEqual(self.call(self.make('two', principal, principal=principal))['data'], 'unauthorized')

    def test_created_child_is_invoked_under_its_law_and_late_failure_rolls_back(self):
        self.seed()
        request = {'op': 'transaction', 'principal': 'alice', 'intent': 'create-use',
            'reads': {'factory': self.root, 'factory/one': None},
            'calls': [{'object': 'factory', 'command': 'make', 'input': {'name': 'one', 'second': ''}},
                      {'object': 'factory/one', 'command': 'report', 'input': {}}]}
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt.get('data'))
        self.assertEqual(receipt['data']['allocated']['factory/one']['version'], 0)
        self.assertEqual(receipt['data']['roots']['factory/one']['version'], 1)
        self.seed(factory_protocol(child_law=law('report', actors=('other',))))
        request['reads']['factory'] = self.root
        refusal = self.call(request)
        self.assertEqual(refusal['data'], 'unauthorized')
        self.assertEqual(self.objects(), {'factory': self.root})

    def test_nested_factories_have_independent_direct_quotas(self):
        self.seed(factory_protocol(limit=1))
        inner = self.create('factory/scope', factory_protocol(limit=1),
                            law('make', managers=('alice',)))['data']['root']
        request = {'op': 'transaction', 'principal': 'alice', 'intent': 'nested',
            'reads': {'factory/scope': inner, 'factory/scope/leaf': None},
            'calls': [{'object': 'factory/scope', 'command': 'make',
                       'input': {'name': 'leaf', 'second': ''}}]}
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt.get('data'))
        self.assertEqual(set(receipt['data']['allocated']), {'factory/scope/leaf'})
        self.assertEqual(receipt['data']['allocated']['factory/scope/leaf']['version'], 0)
        self.assertEqual(receipt['data']['roots']['factory/scope']['version'], 1)
        self.assertEqual(self.call(self.make('second', 'outer-full'))['data'],
                         'factory child quota exhausted')

    def test_creation_receipt_retains_initial_root_before_later_child_revision(self):
        self.seed()
        replacement = copy.deepcopy(child_protocol())
        replacement['name'] = 'Revised counter'
        request = {'op': 'transaction', 'principal': 'alice', 'intent': 'create-revise',
            'reads': {'factory': self.root, 'factory/one': None},
            'calls': [{'object': 'factory', 'command': 'make', 'input': {'name': 'one', 'second': ''}},
                      {'op': 'reprogram', 'object': 'factory/one', 'protocol': replacement,
                       'state': copy.deepcopy(child_protocol()['initial'])}]}
        # Source-selected child management is separate from the parent's grant.
        self.seed(factory_protocol(child_law=law('report', managers=('alice',))))
        request['reads']['factory'] = self.root
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt.get('data'))
        self.assertEqual(receipt['data']['allocated']['factory/one']['protocol']['name'], 'Counter prototype')
        self.assertEqual(receipt['data']['allocated']['factory/one']['version'], 0)
        self.assertEqual(receipt['data']['roots']['factory/one']['protocol']['name'], 'Revised counter')
        self.assertEqual(receipt['data']['roots']['factory/one']['version'], 1)
        self.assertEqual(self.call(request), receipt)

    def test_current_source_predicate_restricts_an_existing_factory_grant(self):
        from conformance.test_current_boundary import policy
        self.seed()
        authority = law()
        authority['predicate'] = policy('refuse', 'unused')
        revised = self.call({'op': 'law', 'object': 'factory', 'principal': 'manager',
            'intent': 'source-predicate', 'expected': self.root, 'law': authority})
        self.assertEqual(revised['kind'], 'committed', revised.get('data'))
        self.root = revised['data']['root']
        refusal = self.call(self.make())
        self.assertEqual(refusal['kind'], 'refused', refusal.get('data'))
        self.assertEqual(self.objects(), {'factory': self.root})

    def test_lost_commit_reply_replays_without_another_child_or_parent_advance(self):
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
