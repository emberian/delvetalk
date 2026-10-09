"""OS resource custody never fabricates a receiving result or forgets a retry."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import process_custody
import resident_store

LINUX = sys.platform.startswith('linux')
# AS includes Lean's large reserved thread stack; this is not an RSS budget.
LIMIT = 2 * 1024 * 1024 * 1024


class ResidentResources(unittest.TestCase):
    def test_invalid_and_unsupported_limits_refuse_before_filesystem_custody(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in (0, -1, True, 1.5, '512'):
                path = Path(directory) / 'absent' / 'world.sqlite'
                with self.assertRaisesRegex(ValueError, 'positive integer'):
                    resident_store.Resident(path, memory_bytes=value)
                self.assertFalse(path.parent.exists())
            with patch.object(resident_store.sys, 'platform', 'darwin'):
                with self.assertRaisesRegex(ValueError, 'requires Linux'):
                    resident_store.Resident(path, memory_bytes=LIMIT)
                self.assertFalse(path.parent.exists())

    @unittest.skipUnless(LINUX, 'Linux RLIMIT_AS enforcement; no macOS claim')
    def test_launcher_enforces_address_space_without_lifetime_cpu_quota(self):
        source = '''import json, resource, sys
print(json.dumps({'as': resource.getrlimit(resource.RLIMIT_AS), 'cpu': resource.getrlimit(resource.RLIMIT_CPU)}), flush=True)
try:
    allocation = bytearray(128 * 1024 * 1024)
except MemoryError:
    sys.exit(86)
sys.exit(87)
'''
        import resource
        before = resource.getrlimit(resource.RLIMIT_CPU)
        done = subprocess.run([sys.executable, '-c', process_custody.LAUNCH,
            json.dumps([None, 64 * 1024 * 1024, None]), sys.executable, '-c', source],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(done.returncode, 86, done.stderr)
        limits = json.loads(done.stdout)
        self.assertEqual(limits['as'], [64 * 1024 * 1024] * 2)
        self.assertEqual(limits['cpu'], list(before))

    @unittest.skipUnless((ROOT / '.lake/build/bin/delvetalk-world').is_file(), 'prebuilt receiver required')
    def test_killed_receiver_recovers_durable_exact_reply_under_same_configuration(self):
        request = {'op': 'create', 'object': 'room', 'principal': 'keeper', 'intent': 'create',
                   'protocol': {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {}},
                   'law': ['keeper']}
        configured = LIMIT if LINUX else None
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'world.sqlite'
            with resident_store.Resident(database, profile='world', timeout=5, memory_bytes=configured) as receiver:
                self.assertEqual(receiver.memory_bytes, configured)
                pid = receiver.process.pid
                def kill(stage):
                    if stage == 'after_commit':
                        os.kill(receiver.process.pid, signal.SIGKILL)
                        receiver.process.wait(timeout=5)
                receiver._boundary = kill
                with self.assertRaises((BrokenPipeError, RuntimeError)):
                    receiver.exchange(request)
                self.assertEqual(receiver.uncertain, request)
                self.assertIsNone(receiver.process)
                with self.assertRaisesRegex(RuntimeError, 'recover'):
                    receiver.exchange({**request, 'intent': 'different'})
                receiver._boundary = lambda _: None
                receipt = receiver.recover()
                self.assertEqual(receipt['kind'], 'committed')
                self.assertNotEqual(receiver.process.pid, pid)
                self.assertEqual(receiver.exchange(request), receipt)
                self.assertEqual(receiver.sequence, 1)
                receiver.checkpoint()
            with resident_store.Resident(database, profile='world', timeout=5, memory_bytes=configured) as receiver:
                self.assertEqual(receiver.exchange(request), receipt)
                self.assertEqual(len(receiver.export_world()['receipts']), 1)
                if LINUX:
                    line = next(line for line in Path(f'/proc/{receiver.process.pid}/limits').read_text().splitlines()
                                if line.startswith('Max address space'))
                    self.assertEqual(line.split()[3:5], [str(LIMIT)] * 2)


if __name__ == '__main__': unittest.main()
