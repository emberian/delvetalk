#!/usr/bin/env python3
"""Native file custody preserves admission; history is not a request frame.

The large-history case is a synthetic transport fixture, not a replay proof.
"""
import copy
from decimal import Decimal
from native_support import load_script
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
world = load_script(ROOT / 'scripts/world.py', 'file_custody_world')


def protocol():
    return {'profile': 'delvetalk-local-v1', 'initial': {'value': Decimal('1.2301'), 'text': '雨🜉'},
            'commands': {'write': {'require': [], 'set': {'text': ['input', 'text']},
                                   'result': ['state', 'text'], 'outbox': []}}}


class FileCustodyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / 'world.json'

    def call(self, request, profile='world'):
        return world.exchange(self.db, request, profile=profile)

    def create(self):
        request = {'op': 'create', 'object': 'room', 'principal': 'keeper', 'intent': 'create',
                   'protocol': protocol(), 'law': ['keeper']}
        return request, self.call(request)

    def native(self, profile, value, *args):
        result = subprocess.run([str(ROOT / '.lake/build/bin' / world.PROFILES[profile][0]), *args],
                                input=world.wire_dumps(value) + '\n', capture_output=True, text=True,
                                timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return world.wire_loads(result.stdout)

    def test_same_receiving_function_as_framed_mode_in_all_profiles(self):
        for profile in world.PROFILES:
            with self.subTest(profile=profile):
                self.db = Path(self.directory.name) / (profile + '.json')
                expected = {'objects': {}, 'receipts': []}
                def compare(request):
                    nonlocal expected
                    framed = self.native(profile, {'world': expected, 'request': request})
                    reply = self.call(request, profile)
                    self.assertEqual(reply, framed['reply'])
                    expected = framed['world']
                    self.assertEqual(world.wire_loads(self.db.read_text()), expected)
                    return reply
                create = {'op': 'create', 'object': 'room', 'principal': 'keeper', 'intent': 'create',
                          'protocol': protocol(), 'law': ['keeper']}
                root = compare(create)['data']['root']
                compare({'op': 'inspect', 'object': 'room', 'principal': 'reader'})
                write = {'op': 'invoke', 'object': 'room', 'principal': 'keeper', 'intent': 'write',
                         'expected': root, 'command': 'write', 'input': {'text': '星\n☂'}}
                next_root = compare(write)['data']['root']
                compare({**write, 'principal': 'stranger'})
                compare({**write, 'input': {'text': 'different'}})
                compare({'op': 'law', 'object': 'room', 'principal': 'keeper', 'intent': 'lock',
                         'expected': next_root, 'law': []})
                compare(write)
                compare({**write, 'intent': 'new'})
                compare(create)

    def test_history_larger_than_legacy_frame_keeps_inspect_retry_and_new_admission(self):
        create, created = self.create()
        # Repeated legal-size receipt-shaped records test physical framing only.
        missing = {'op': 'invoke', 'object': 'absent', 'principal': 'keeper', 'intent': 'large',
                   'padding': 'x' * 60000}
        self.call(missing)
        snapshot = world.wire_loads(self.db.read_text())
        template = snapshot['receipts'][-1]
        for index in range(280):
            entry = copy.deepcopy(template)
            entry['request']['intent'] = 'padding-' + str(index)
            entry['receipt']['intent'] = entry['request']['intent']
            snapshot['receipts'].append(entry)
        self.db.write_text(world.wire_dumps(snapshot) + '\n')
        self.assertGreater(self.db.stat().st_size, 16 * 1024 * 1024)
        inspect = {'op': 'inspect', 'object': 'room', 'principal': 'reader'}
        self.assertEqual(self.native('world', {'world': snapshot, 'request': inspect}),
                         {'error': 'frame exceeds 16 MiB'})
        before = self.db.read_bytes()
        self.assertEqual(self.call(inspect), created['data']['root'])
        self.assertEqual(self.call(create), created)
        self.assertEqual(self.db.read_bytes(), before)
        request = {'op': 'invoke', 'object': 'room', 'principal': 'keeper', 'intent': 'after-growth',
                   'expected': created['data']['root'], 'command': 'write', 'input': {'text': 'Still here.'}}
        self.assertEqual(self.call(request)['kind'], 'committed')
        self.assertEqual(len(world.wire_loads(self.db.read_text())['receipts']), len(snapshot['receipts']) + 1)

    def test_request_only_stdin_and_unchanged_operations_preserve_snapshot(self):
        create, receipt = self.create()
        before = self.db.read_bytes()
        original = world.process_custody.run_native
        calls = []
        def observe(command, **kwargs):
            calls.append((command, kwargs['input']))
            return original(command, **kwargs)
        with patch.object(world.process_custody, 'run_native', side_effect=observe), patch.object(world.os, 'replace') as replace:
            self.assertEqual(self.call(create), receipt)
            self.call({'op': 'inspect', 'object': 'room', 'principal': 'reader'})
            replace.assert_not_called()
        self.assertEqual(world.wire_loads(calls[0][1]), create)
        self.assertEqual(calls[0][0][-3:-1], ['--files', str(self.db.resolve())])
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.db.parent.iterdir()), ['world.json', 'world.json.lock'])

    def test_failures_leave_old_snapshot_or_exact_durable_receipt(self):
        _, created = self.create()
        request = {'op': 'invoke', 'object': 'room', 'principal': 'keeper', 'intent': 'write',
                   'expected': created['data']['root'], 'command': 'write', 'input': {'text': 'After crash.'}}
        before = self.db.read_bytes()
        for operation in ('fsync', 'replace'):
            with self.subTest(operation=operation):
                with patch.object(world.os, operation, side_effect=OSError('injected')):
                    with self.assertRaises(OSError): self.call(request)
                self.assertEqual(self.db.read_bytes(), before)
        real_fsync = world.os.fsync
        count = 0
        def fail_directory(descriptor):
            nonlocal count
            count += 1
            if count == 2: raise OSError('reply lost after rename')
            return real_fsync(descriptor)
        with patch.object(world.os, 'fsync', side_effect=fail_directory):
            with self.assertRaises(OSError): self.call(request)
        changed = self.db.read_bytes()
        self.assertNotEqual(changed, before)
        retained = world.wire_loads(changed)['receipts'][-1]['receipt']
        with patch.object(world.os, 'fsync', wraps=real_fsync) as barriers:
            self.assertEqual(self.call(request), retained)
            self.assertEqual(barriers.call_count, 2)
        self.assertEqual(self.db.read_bytes(), changed)
        self.assertEqual(sorted(p.name for p in self.db.parent.iterdir()), ['world.json', 'world.json.lock'])

    def test_malformed_process_output_and_input_do_not_replace_custody(self):
        _, created = self.create()
        before = self.db.read_bytes()
        inspect = {'op': 'inspect', 'object': 'room', 'principal': 'reader'}
        for output in ('[]', '{"changed":1,"reply":null}', '{"changed":true,"reply":null}',
                       '{"changed":false,"reply":null,"extra":true}', '{'):
            with self.subTest(output=output):
                with patch.object(world.process_custody, 'run_native', return_value=subprocess.CompletedProcess([], 0, output.encode('utf-8'), b'')):
                    with self.assertRaises(ValueError): self.call(inspect)
                self.assertEqual(self.db.read_bytes(), before)
        with patch.object(world.process_custody, 'run_native', return_value=subprocess.CompletedProcess([], 1, b'', b'failed')):
            with self.assertRaises(RuntimeError): self.call(inspect)
        with self.assertRaises(ValueError): self.call({**inspect, 'padding': 'x' * world.MAX_EXPANDED_REQUEST_BYTES})
        self.assertEqual(self.db.read_bytes(), before)
        self.db.write_text('{broken')
        with self.assertRaises(ValueError): self.call(inspect)
        self.assertEqual(self.db.read_text(), '{broken')

    def test_native_request_envelope_is_bounded_and_candidate_is_not_the_database(self):
        self.create()
        before = self.db.read_bytes()
        candidate = self.db.parent / 'candidate'
        candidate.write_text('untouched')
        binary = str(ROOT / '.lake/build/bin/delvetalk-world')
        for data in (b'{' , b'{}\n{}\n', b'\xff', b' ' * 65538):
            with self.subTest(data=data[:20]):
                result = subprocess.run([binary, '--files', str(self.db), str(candidate)],
                                        input=data, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(set(world.wire_loads(result.stdout)), {'error'})
                self.assertEqual(candidate.read_text(), 'untouched')
                self.assertEqual(self.db.read_bytes(), before)
        result = self.native('world', {}, '--files', str(self.db), str(self.db))
        self.assertIn('candidate must differ', result['error'])
        self.assertEqual(self.db.read_bytes(), before)

    def test_decimal_scale_survives_candidate_reply_reopen_and_exact_retry(self):
        candidate = protocol()
        numbers = {'value': Decimal('1.2300'), 'integral': Decimal('1.00'),
                   'zero': Decimal('0.0000'), 'negative': Decimal('-12.3000'),
                   'small': Decimal('1E-10000'), 'large': 10 ** 100}
        candidate['initial'].update(numbers)
        create = {'op': 'create', 'object': 'room', 'principal': 'keeper', 'intent': 'scaled',
                  'protocol': candidate, 'law': ['keeper']}
        receipt = self.call(create)
        root = receipt['data']['root']
        stored = world.wire_loads(self.db.read_bytes())
        for key, number in numbers.items():
            with self.subTest(key=key):
                observed = [root['state'][key], stored['objects']['room']['state'][key],
                            stored['receipts'][0]['request']['protocol']['initial'][key]]
                for value in observed:
                    if isinstance(number, Decimal): self.assertEqual(value.as_tuple(), number.as_tuple())
                    else: self.assertEqual(value, number)
        # Each exchange starts a fresh receiving process and rereads the file.
        self.assertEqual(self.call(create), receipt)
        altered = copy.deepcopy(root)
        altered['state']['value'] = Decimal('1.23')
        request = {'op': 'invoke', 'object': 'room', 'principal': 'keeper', 'intent': 'rounded',
                   'expected': altered, 'command': 'write', 'input': {'text': 'No rounding.'}}
        self.assertEqual(self.call(request)['data'], 'stale read root')
        request.update(intent='exact', expected=root)
        result = self.call(request)
        self.assertEqual(result['kind'], 'committed', result)
        self.assertEqual(result['data']['root']['state']['value'].as_tuple(), numbers['value'].as_tuple())
        self.assertEqual(self.call(request), result)


if __name__ == '__main__': unittest.main()
