#!/usr/bin/env python3
"""Inherited worker limits must permit the pinned Lean main-thread runtime."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('resource_worker', ROOT / 'scripts/worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerResourceTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux address-space custody')
    def test_stack_reservation_fits_unchanged_address_space_budget(self):
        # Use real pthread allocation: this failed at Lean 4.34's default 1 GiB
        # stack under the worker's 1 GiB address-space limit, despite low RSS.
        probe = '''import json, os, resource, threading
stack = int(os.environ['LEAN_STACK_SIZE_KB']) * 1024
threading.stack_size(stack)
thread = threading.Thread(target=lambda: None)
thread.start()
thread.join()
memory = resource.getrlimit(resource.RLIMIT_AS)
try:
    allocation = bytearray(memory[0])
except MemoryError:
    denied = True
else:
    denied = False
print(json.dumps({'stack': stack, 'memory': memory, 'cpu': resource.getrlimit(resource.RLIMIT_CPU), 'denied': denied, 'arena': os.environ['MIMALLOC_ARENA_RESERVE']}))
'''
        for memory_mib in (64, 2048):
            with self.subTest(memory_mib=memory_mib):
                with mock.patch.dict(os.environ, {'LEAN_STACK_SIZE_KB': '1048576', 'MIMALLOC_ARENA_RESERVE': '1048576'}):
                    result = worker.command(['-c', probe], 10, memory_mib)
                self.assertEqual(result['memory'], [memory_mib * 1024 * 1024] * 2)
                self.assertEqual(result['cpu'], [10, 10])
                self.assertEqual(result['stack'], min(64, memory_mib // 4) * 1024 * 1024)
                self.assertTrue(result['denied'])
                self.assertEqual(result['arena'], '131072')

    @unittest.skipUnless((ROOT / '.lake/build/bin/delvetalk-transactions').is_file(), 'built transactions host required')
    def test_real_lean_admission_under_default_worker_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            request = {'op': 'create', 'object': 'bounded-counter', 'principal': 'owner',
                       'intent': 'create', 'protocol': json.loads((ROOT / 'protocols/counter/protocol.json').read_text()),
                       'law': ['owner']}
            request_path = directory / 'request.json'
            request_path.write_text(json.dumps(request))
            reply = worker.command([str(ROOT / 'scripts/world.py'), '--profile', 'transactions',
                                    str(directory / 'world.json'), str(request_path)], 15)
            self.assertEqual(reply['kind'], 'committed')
            self.assertEqual(reply['data']['root']['state'], request['protocol']['initial'])
            self.assertTrue((directory / 'world.json').is_file())
            inspected = worker.command([str(ROOT / 'scripts/desk.py'), '--database', str(directory / 'world.json'),
                                        '--artifacts', str(directory / 'artifacts'), '--profile', 'transactions',
                                        'inspect', '--object', 'bounded-counter'], 15)
            self.assertEqual(inspected, reply['data']['root'])
            if sys.platform.startswith('linux'):
                before = (directory / 'world.json').read_bytes()
                with self.assertRaises(RuntimeError):
                    worker.command([str(ROOT / 'scripts/world.py'), '--profile', 'transactions',
                                    str(directory / 'world.json'), str(request_path)], 15, memory_mib=1024)
                self.assertEqual((directory / 'world.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
