#!/usr/bin/env python3
"""Incremental native receiving, durable commit and exact retained retries."""
import copy
import hashlib
from decimal import Decimal
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import resident_store
import world


def create():
    return {'op': 'create', 'object': 'room', 'principal': 'keeper', 'intent': 'create',
            'protocol': {'profile': 'delvetalk-local-v1', 'initial': {'value': Decimal('1.2300')},
                'commands': {'write': {'require': [], 'set': {'value': ['input', 'value']},
                                      'result': ['state', 'value'], 'outbox': []}}}, 'law': ['keeper']}


class ResidentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def open(self, name='resident.sqlite', **kwargs):
        return resident_store.Resident(self.directory / name, **kwargs)

    def test_receiving_differential_all_profiles_exact_retry_collision_and_current_law(self):
        for profile in world.PROFILES:
            with self.subTest(profile=profile), self.open(profile + '.sqlite', profile=profile) as resident:
                snapshot = {'objects': {}, 'receipts': []}
                def compare(request):
                    nonlocal snapshot
                    reference = self.directory / (profile + '-reference.json')
                    expected_reply = world.exchange(reference, request, profile=profile)
                    expected = {'reply': expected_reply, 'world': world.wire_loads(reference.read_bytes())}
                    actual = resident.exchange(request)
                    self.assertEqual(actual, expected['reply'])
                    snapshot = expected['world']
                    self.assertEqual(resident.export_world(), snapshot)
                    return actual
                request = create()
                root = compare(request)['data']['root']
                compare({'op': 'inspect', 'object': 'room', 'principal': 'keeper'})
                write = {'op': 'invoke', 'object': 'room', 'principal': 'keeper', 'intent': 'write',
                         'expected': root, 'command': 'write', 'input': {'value': Decimal('2.3000')}}
                next_root = compare(write)['data']['root']
                compare({**write, 'input': {'value': Decimal('2.3')}})
                compare({'op': 'law', 'object': 'room', 'principal': 'keeper', 'intent': 'lock',
                         'expected': next_root, 'law': []})
                compare(write)
                compare({**write, 'intent': 'fresh'})
                compare(request)
                self.assertEqual(resident.retained_reply(write), snapshot['receipts'][1]['receipt'])
                self.assertIsNone(resident.retained_reply({**write, 'input': {'value': 3}}))
                self.assertIsNone(resident.retained_reply({**write, 'intent': 'unseen'}))

    def test_registry_initialization_uses_world_lifecycle_not_receipt_history(self):
        for initialize_first in (False, True):
            with self.subTest(initialize_first=initialize_first), self.open(str(initialize_first) + '.sqlite') as resident:
                reference = self.directory / (str(initialize_first) + '-reference.json')
                def compare(request):
                    expected = world.exchange(reference, request, profile='compiled')
                    self.assertEqual(resident.exchange(request), expected)
                    self.assertEqual(resident.export_world(), world.wire_loads(reference.read_bytes()))
                    return expected
                compare({'op': 'invoke', 'object': 'absent', 'principal': 'keeper', 'intent': 'absent'})
                init = {'op': 'messages-init', 'principal': 'keeper', 'intent': 'init',
                        'lineage': 'courtyard', 'pendingLimit': 128}
                if initialize_first:
                    self.assertEqual(compare(init)['kind'], 'committed')
                compare(create())
                outcome = compare(init)
                self.assertEqual(outcome['kind'], 'committed' if initialize_first else 'refused')
                self.assertEqual(compare({**init, 'intent': 'new-init'})['kind'], 'refused')

    def test_all_uncertain_boundaries_reconcile_exactly_once(self):
        for stage in ('after_prepare', 'before_commit', 'after_commit', 'after_finalize', 'before_reply'):
            with self.subTest(stage=stage), self.open(stage + '.sqlite', profile='world') as resident:
                request = create()
                def fail(at):
                    if at == stage: raise OSError('injected custody interruption')
                resident._boundary = fail
                with self.assertRaises(OSError): resident.exchange(request)
                with self.assertRaisesRegex(RuntimeError, 'recover'): resident.exchange({**request, 'intent': 'other'})
                resident._boundary = lambda _: None
                reply = resident.recover()
                self.assertEqual(reply['kind'], 'committed')
                self.assertEqual(resident.sequence, 1)
                self.assertEqual(len(resident.export_world()['receipts']), 1)
                self.assertEqual(resident.exchange(request), reply)
                self.assertEqual(resident.sequence, 1)

    def test_restart_checkpoint_tail_and_native_index_exact_decimal(self):
        request = create()
        with self.open(profile='world') as resident:
            reply = resident.exchange(request)
            resident.checkpoint()
            refusal = {'op': 'invoke', 'object': 'absent', 'principal': 'keeper', 'intent': 'absent'}
            refused = resident.exchange(refusal)
            expected = resident.export_world()
        with self.open(profile='world') as resident:
            self.assertEqual(resident.exchange(request), reply)
            self.assertEqual(resident.exchange(refusal), refused)
            changed = copy.deepcopy(request)
            changed['protocol']['initial']['value'] = Decimal('1.23')
            self.assertEqual(resident.exchange(changed)['kind'], 'refused')
            self.assertEqual(resident.sequence, 2)
            self.assertEqual(resident.export_world(), expected)
            self.assertEqual(resident.audit()['sequence'], 2)
            self.assertEqual(resident.export_world(), expected)

    def test_checkpoint_native_fold_rejects_duplicate_or_miskeyed_history_atomically(self):
        with self.open('origin.sqlite', profile='world') as origin:
            origin.exchange(create())
            snapshot = origin.export_world()
        duplicate = copy.deepcopy(snapshot)
        duplicate['receipts'].append(copy.deepcopy(duplicate['receipts'][0]))
        wrong_intent = copy.deepcopy(snapshot)
        wrong_intent['receipts'][0]['receipt']['intent'] = 'another'
        missing_key = copy.deepcopy(snapshot)
        del missing_key['receipts'][0]['request']['principal']
        extra_field = copy.deepcopy(snapshot)
        extra_field['receipts'][0]['extra'] = True
        for i, value in enumerate((duplicate, wrong_intent, missing_key, extra_field)):
            raw = world.wire_dumps(value).encode()
            path = self.directory / f'checkpoint-{i}.json'
            path.write_bytes(raw)
            with self.open(f'check-{i}.sqlite', profile='world') as resident:
                with self.assertRaises(resident_store.ReceivingError):
                    resident._rpc({'op': 'load', 'path': str(path), 'seal': {
                        'sequence': len(value['receipts']), 'head': 'trusted-test-head',
                        'sha256': hashlib.sha256(raw).hexdigest()}})
                self.assertEqual(resident._rpc({'op': 'status'})['sequence'], 0)
                self.assertEqual(resident.exchange(create())['kind'], 'committed')

    def test_modified_frame_refused_by_exact_native_reexecution(self):
        with self.open(profile='world') as resident:
            resident.exchange(create())
        db = sqlite3.connect(self.directory / 'resident.sqlite')
        raw = db.execute('select frame from entries').fetchone()[0]
        frame = world.wire_loads(raw)
        frame['reply']['kind'] = 'imaginary'
        db.execute('update entries set frame=?', (world.wire_dumps(frame).encode(),))
        db.commit(); db.close()
        with self.assertRaisesRegex(resident_store.ReceivingError, 'does not reproduce'):
            self.open(profile='world')

    def test_corrupt_checkpoint_and_second_writer_refused(self):
        with self.open(profile='world') as resident:
            resident.exchange(create())
            resident.checkpoint()
            with self.assertRaises(BlockingIOError): self.open(profile='world')
        db = sqlite3.connect(self.directory / 'resident.sqlite')
        db.execute("update checkpoints set body=x'7b7d'")
        db.commit(); db.close()
        with self.assertRaisesRegex(ValueError, 'digest'): self.open(profile='world')
        with self.open(profile='world', use_checkpoint=False) as resident:
            self.assertEqual(resident.sequence, 1)

    def test_file_and_resident_lookup_share_native_exact_numeric_and_key_order_rules(self):
        request = create()
        snapshot = self.directory / 'reference.json'
        reply = world.exchange(snapshot, request, profile='world')
        def lookup(candidate):
            run = subprocess.run([str(ROOT / '.lake/build/bin/delvetalk-world'), '--lookup-files', str(snapshot)],
                input=world.wire_dumps(candidate), text=True, capture_output=True, check=True, timeout=10)
            return world.wire_loads(run.stdout)
        with self.open(profile='world') as resident:
            self.assertEqual(resident.exchange(request), reply)
            reordered = dict(reversed(list(request.items())))
            different = copy.deepcopy(request)
            different['protocol']['initial']['value'] = Decimal('1.23')
            for candidate, expected in ((reordered, reply), (different, None),
                    ({**request, 'intent': 'absent'}, None), ({}, None)):
                self.assertEqual(lookup(candidate), expected)
                self.assertEqual(resident.retained_reply(candidate), expected)
            self.assertEqual(resident.sequence, 1)
        self.assertEqual(len(world.wire_loads(snapshot.read_bytes())['receipts']), 1)

    def test_delta_preserves_numeric_scale_array_atomicity_and_ordered_map_edits(self):
        with self.open(profile='world') as resident:
            root = resident.exchange(create())['data']['root']
            def write(value, serial):
                nonlocal root
                request = {'op': 'invoke', 'principal': 'keeper', 'intent': str(serial), 'object': 'room',
                           'expected': root, 'command': 'write', 'input': {'value': value}}
                root = resident.exchange(request)['data']['root']
                raw = resident.connection.execute('select frame from entries order by sequence desc limit 1').fetchone()[0]
                return [change for change in world.wire_loads(raw)['delta']
                        if change['path'][:3] == ['objects', 'room', 'state']]
            prefix = ['objects', 'room', 'state', 'value']
            changes = write(Decimal('1.23'), 0)
            self.assertEqual(changes, [{'path': prefix, 'value': Decimal('1.23')}])
            self.assertEqual(changes[0]['value'].as_tuple().exponent, -2)
            write({'old': None, 'same': {'x': 1}}, 1)
            changes = write({'same': {'x': 1}, 'a': {}, 'z': False}, 2)
            self.assertEqual(changes, [{'path': prefix + ['a'], 'value': {}},
                                      {'path': prefix + ['z'], 'value': False},
                                      {'path': prefix + ['old'], 'remove': True}])
            self.assertEqual(write({'z': False, 'a': {}, 'same': {'x': 1}}, 3), [])
            write([Decimal('2.300')], 4)
            changes = write([Decimal('2.30')], 5)
            self.assertEqual(changes, [{'path': prefix, 'value': [Decimal('2.30')]}])
            self.assertEqual(changes[0]['value'][0].as_tuple().exponent, -2)
            self.assertEqual(write([Decimal('2.30')], 6), [])

    def test_restart_rechecks_captured_runtime_before_accepting_work(self):
        with self.open(profile='world') as resident:
            resident.exchange(create())
            with patch.object(resident_store, '_pins', return_value='changed runtime'):
                with self.assertRaisesRegex(ValueError, 'runtime/profile identity'):
                    resident.audit()
            self.assertIsNone(resident.process)
            resident._start()
            self.assertEqual(resident.sequence, 1)

    def test_pending_preparation_requires_exact_finalize(self):
        with self.open(profile='world') as resident:
            prepared = resident._rpc({'op': 'prepare', 'request': create()})
            with self.assertRaisesRegex(resident_store.ReceivingError, 'prepared entry'):
                resident._rpc({'op': 'finalize', 'head': 'wrong'})
            with self.assertRaisesRegex(resident_store.ReceivingError, 'pending preparation'):
                resident._rpc({'op': 'prepare', 'request': create()})
            # No durable commit: restarting forgets the candidate.
            resident._start()
            self.assertEqual(resident.sequence, 0)
            self.assertEqual(resident.exchange(create())['kind'], 'committed')

    def test_messages_nested_delta_stays_small_with_consumed_history(self):
        from conformance.test_resident_messages import ResidentMessages, source_protocol
        with self.open(profile='compiled') as resident:
            helper = ResidentMessages()
            helper.serial = 0
            def call(request, kind=None):
                reply = resident.exchange(request)
                if kind is not None: self.assertEqual(reply['kind'], kind, reply)
                return reply
            helper.call = call
            helper.snapshot = resident.export_world
            helper.setup_world(pending=2)
            sizes = []
            original = None
            for i in range(100):
                request, receipt, refs = helper.ring()
                if original is None: original = request, receipt
                pending = resident.query({'op': 'messages-pending', 'principal': 'reader'})
                self.assertIn(refs[0]['id'], pending['pending'])
                event = resident.query({'op': 'message-event', 'principal': 'reader', 'event': refs[0]})
                self.assertEqual(event['event']['status'], 'pending')
                helper.call(helper.delivery(refs[0]), 'committed')
                raw = resident.connection.execute('select frame from entries order by sequence desc limit 1').fetchone()[0]
                entry = world.wire_loads(raw)
                self.assertTrue(any(change['path'][:2] == ['messages', 'events'] for change in entry['delta']))
                self.assertFalse(any(change['path'] == ['messages'] for change in entry['delta']))
                sizes.append(len(raw))
            self.assertLess(max(sizes) - min(sizes), 300)
            self.assertEqual(resident.exchange(original[0]), original[1])
            self.assertEqual(resident.query({'op': 'messages-pending', 'principal': 'reader'})['pending'], {})
            self.assertEqual(len(resident.export_world()['messages']['events']), 100)
            helper.reprogram('bell', source_protocol('Bell') | {'revision': 'after the sounds'})
            self.assertEqual(resident.exchange(original[0]), original[1])
            resident.checkpoint()
        with self.open(profile='compiled') as resident:
            self.assertEqual(resident.exchange(original[0]), original[1])
            self.assertEqual(len(resident.export_world()['messages']['events']), 100)
            self.assertEqual(resident.audit()['sequence'], resident.sequence)

    def test_history_over_legacy_frame_size_uses_checkpoint_file_and_indexed_retry(self):
        request = {'op': 'invoke', 'object': 'absent', 'principal': 'keeper',
                   'intent': 'large-000', 'padding': 'x' * 60000}
        with self.open(profile='world') as resident:
            reply = resident.exchange(request)
            for i in range(1, 285):
                resident.exchange({**request, 'intent': f'large-{i:03d}'})
            exported = self.directory / 'expanded.json'
            resident.export(exported)
            self.assertGreater(exported.stat().st_size, 16 * 1024 * 1024)
            resident.checkpoint()
        with self.open(profile='world') as resident:
            self.assertEqual(resident.exchange(request), reply)
            self.assertEqual(resident.sequence, 285)
            self.assertEqual(resident.retained_reply(request), reply)

    def test_journal_turn_bytes_do_not_rewrite_retained_history(self):
        with self.open(profile='world') as resident:
            for i in range(250):
                reply = resident.exchange({'op': 'invoke', 'object': 'absent', 'principal': 'keeper',
                                           'intent': f'absent-{i:04d}'})
                self.assertEqual(reply['kind'], 'refused')
            sizes = [row[0] for row in resident.connection.execute('select length(frame) from entries')]
            self.assertLess(max(sizes) - min(sizes), 5)
            self.assertLess(max(sizes), 1500)
            self.assertEqual(len(resident.export_world()['receipts']), 250)
            self.assertEqual(resident.audit()['sequence'], 250)


if __name__ == '__main__': unittest.main()
