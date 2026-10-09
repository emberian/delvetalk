#!/usr/bin/env python3
"""Exact bounded child output, threaded launch, and whole-group termination."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('test_process_custody_module', ROOT / 'scripts/process_custody.py')
custody = importlib.util.module_from_spec(spec)
spec.loader.exec_module(custody)


class ProcessCustodyTests(unittest.TestCase):
    def run_child(self, source, **kwargs):
        options = {'timeout': 3, 'cpu_seconds': 3, 'stdout_limit': 65536, 'stderr_limit': 65536}
        options.update(kwargs)
        return custody.run([sys.executable, '-c', source], **options)

    def test_threaded_launch_preserves_bytes_environment_and_nonzero_status(self):
        original = subprocess.Popen
        def checked(*args, **kwargs):
            self.assertNotIn('preexec_fn', kwargs)
            self.assertTrue(kwargs['start_new_session'])
            self.assertNotEqual(kwargs['stdout'], subprocess.PIPE)
            self.assertNotEqual(kwargs['stderr'], subprocess.PIPE)
            return original(*args, **kwargs)
        def call(index):
            raw = ('雨' + str(index)).encode() + b'\x00\r\n'
            result = self.run_child('import os,sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); '
                'sys.stderr.buffer.write(os.environ["CUSTODY_TEST"].encode()); sys.exit(7)',
                input=raw, env={**os.environ, 'CUSTODY_TEST': 'kept'})
            self.assertEqual((result.returncode, result.stdout, result.stderr), (7, raw, b'kept'))
        with patch.object(custody.subprocess, 'Popen', side_effect=checked):
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(call, range(8)))

    def test_stdout_and_stderr_limits_apply_even_when_child_exits_quickly(self):
        for stream in ('stdout', 'stderr'):
            with self.subTest(stream=stream):
                with self.assertRaisesRegex(custody.OutputLimitExceeded, stream):
                    self.run_child(f'import sys; sys.{stream}.buffer.write(b"x" * 262144)',
                                   stdout_limit=1024, stderr_limit=1024)
        result = self.run_child('import sys; sys.stdout.buffer.write(b"x" * 1024)', stdout_limit=1024)
        self.assertEqual(result.stdout, b'x' * 1024)

    def test_continuous_output_refuses_without_parent_pipe_capture(self):
        for descriptor in (1, 2):
            with self.subTest(descriptor=descriptor):
                with self.assertRaises(custody.OutputLimitExceeded):
                    self.run_child(f'import os\nwhile True: os.write({descriptor}, b"x" * 65536)',
                                   stdout_limit=131072, stderr_limit=131072)

    def test_timeout_reaps_direct_child_and_normal_exit_kills_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / 'pid'
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_child('import os,time,pathlib; '
                    f'pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(5)', timeout=0.2)
            with self.assertRaises(ProcessLookupError): os.kill(int(pidfile.read_text()), 0)
            marker = Path(directory) / 'escaped'
            descendant = f'import time,pathlib; time.sleep(.3); pathlib.Path({str(marker)!r}).write_text("escaped")'
            result = self.run_child('import subprocess,sys; '
                                   f'subprocess.Popen([sys.executable,"-c",{descendant!r}]); print("done")')
            self.assertEqual(result.stdout, b'done\n')
            time.sleep(0.4)
            self.assertFalse(marker.exists())

    def test_resource_limits_apply_in_fresh_launcher(self):
        result = self.run_child('import resource,json; print(json.dumps([resource.getrlimit(resource.RLIMIT_CPU),'
            'resource.getrlimit(resource.RLIMIT_FSIZE)]))', cpu_seconds=2, file_limit=65536)
        self.assertEqual(json.loads(result.stdout), [[2, 2], [65536, 65536]])

    def test_receiving_output_bound_does_not_limit_snapshot_files(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / 'snapshot'
            result = self.run_child('from pathlib import Path; '
                f'Path({str(snapshot)!r}).write_bytes(b"s" * (9*1024*1024)); print("ok")',
                stdout_limit=16, stderr_limit=16)
            self.assertEqual(result.stdout, b'ok\n')
            self.assertEqual(snapshot.stat().st_size, 9 * 1024 * 1024)

    def test_nested_custodian_cannot_escape_outer_timeout_or_raise_hard_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'escaped'
            ready = Path(directory) / 'ready'
            nested_child = ('import os,time,pathlib; '
                f'pathlib.Path({str(ready)!r}).write_text(str(os.getpgrp())); '
                f'time.sleep(.6); pathlib.Path({str(marker)!r}).write_text("escaped")')
            inner = ('import sys; '
                f'sys.path.insert(0,{str(ROOT / "scripts")!r}); import process_custody; '
                f'process_custody.run([sys.executable,"-c",{nested_child!r}], '
                'timeout=3,cpu_seconds=20,stdout_limit=1024,stderr_limit=1024)')
            with self.assertRaises(subprocess.TimeoutExpired): self.run_child(inner, timeout=0.4, cpu_seconds=2)
            self.assertTrue(ready.exists(), 'nested native child must have run')
            time.sleep(0.4)
            self.assertFalse(marker.exists())

    def test_native_policy_is_shared_scoped_and_uses_exact_byte_output(self):
        original = dict(os.environ)
        environment = {**original, 'LEAN_NUM_THREADS': '99', 'LEAN_STACK_SIZE_KB': '1',
                       'LEAN_MAIN_USE_THREAD': '0', 'MIMALLOC_ARENA_RESERVE': '1',
                       'CUSTODY_TEST_MARKER': 'preserved'}
        code = ('import json,os; print(json.dumps({k:v for k,v in os.environ.items() '
                'if k.startswith(("LEAN_","MIMALLOC_","CUSTODY_TEST_MARKER"))}))')
        result = custody.run_native([sys.executable, '-c', code], env=environment,
            timeout=3, cpu_seconds=2, stdout_limit=4096, stderr_limit=1024)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual(observed['LEAN_NUM_THREADS'], '1')
        self.assertEqual(observed['CUSTODY_TEST_MARKER'], 'preserved')
        for key in ('LEAN_STACK_SIZE_KB', 'LEAN_MAIN_USE_THREAD', 'MIMALLOC_ARENA_RESERVE'):
            self.assertNotIn(key, observed)
        self.assertEqual(dict(os.environ), original)
        command, persistent = custody.native_launch(['receiver', '--resident'], env=environment)
        self.assertEqual(persistent, custody.native_environment(environment))
        self.assertEqual(json.loads(command[3]), [None, custody.NATIVE_MEMORY_BYTES, None])
        self.assertEqual(command[-2:], ['receiver', '--resident'])
        self.assertEqual(custody.NATIVE_MEMORY_BYTES,
                         4 * 1024 * 1024 * 1024 if sys.platform.startswith('linux') else None)

    def test_worker_selects_reply_bounds_without_a_world_file_limit(self):
        spec = importlib.util.spec_from_file_location('custody_test_worker', ROOT / 'scripts/worker.py')
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        output = subprocess.CompletedProcess([], 0, b'{"ok":true}\n', b'')
        with patch.object(worker.process_custody, 'run', return_value=output) as run:
            self.assertEqual(worker.command(['-c', 'print("unused")'], 2.1), {'ok': True})
            options = run.call_args.kwargs
            self.assertEqual(options['stdout_limit'], 64 * 1024 * 1024)
            self.assertEqual(options['stderr_limit'], 1024 * 1024)
            self.assertEqual(options['cpu_seconds'], 3)
            self.assertIsNone(options.get('file_limit'))
        with patch.object(worker.process_custody, 'run', side_effect=worker.process_custody.OutputLimitExceeded('stdout')):
            with self.assertRaises(worker.process_custody.OutputLimitExceeded):
                worker.command(['-c', 'print("unused")'], 2)


if __name__ == '__main__': unittest.main()
