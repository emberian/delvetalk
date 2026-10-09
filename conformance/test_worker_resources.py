#!/usr/bin/env python3
"""Inherited worker limits must permit the pinned Lean main-thread runtime."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('resource_worker', ROOT / 'scripts/worker.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerResourceTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux address-space custody')
    def test_parent_address_space_and_cpu_limits_remain_hard(self):
        # Parent workers use the shared allowance; they do not invent allocator
        # or stack settings. Native grandchildren apply their own fixed policy.
        probe = """import json, resource, threading
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
print(json.dumps({'memory': memory, 'cpu': resource.getrlimit(resource.RLIMIT_CPU), 'denied': denied}))
"""
        for memory_mib in (64, worker.process_custody.NATIVE_MEMORY_MIB):
            with self.subTest(memory_mib=memory_mib):
                result = worker.command(['-c', probe], 10, memory_mib)
                self.assertEqual(result['memory'], [memory_mib * 1024 * 1024] * 2)
                self.assertEqual(result['cpu'], [10, 10])
                self.assertTrue(result['denied'])

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
