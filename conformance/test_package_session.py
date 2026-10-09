#!/usr/bin/env python3
"""Physical package sessions cannot turn process failure into a reply."""
from pathlib import Path
import os
import subprocess
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from package_session import PackageSession
from process_custody import OutputLimitExceeded


class SessionTests(unittest.TestCase):
    def session(self, code, **kwargs):
        return PackageSession([sys.executable, '-u', '-c', code], **kwargs)

    def test_reuse_identity_restart_and_exact_bytes(self):
        with self.session('import sys; [sys.stdout.buffer.write(x) and sys.stdout.flush() for x in sys.stdin.buffer]') as session:
            frame = b'{"number":1.2300}\n'
            self.assertEqual(session.exchange(frame, timeout=2, identity={'runtime': 1}), frame)
            first = session.process.pid
            self.assertEqual(session.exchange(frame, timeout=2, identity={'runtime': 1}), frame)
            self.assertEqual(session.process.pid, first)
            session.exchange(frame, timeout=2, identity={'runtime': 2})
            self.assertNotEqual(session.process.pid, first)

    def test_timeout_reaps_and_next_call_starts_clean(self):
        with self.session('import sys,time; [time.sleep(10) for x in sys.stdin]') as session:
            with self.assertRaises(subprocess.TimeoutExpired):
                session.exchange(b'{}\n', timeout=.1, identity=1)
            self.assertIsNone(session.process)
            session.arguments = [sys.executable, '-u', '-c', 'import sys; [print(x.strip()) for x in sys.stdin]']
            self.assertEqual(session.exchange(b'{}\n', timeout=2, identity=1), b'{}\n')

    def test_stdout_stderr_and_frame_bounds(self):
        for code in ("import sys;sys.stdin.readline();print('x'*2048)",
                     "import sys;sys.stdin.readline();sys.stderr.write('x'*2048);print('{}')"):
            with self.subTest(code=code), self.session(code, stdout_limit=64, stderr_limit=64) as session:
                with self.assertRaises(OutputLimitExceeded): session.exchange(b'{}\n', timeout=2, identity=1)
                self.assertIsNone(session.process)
        with self.session('') as session:
            with self.assertRaises(ValueError): session.exchange(b'{}\n{}\n', timeout=1, identity=1)
            self.assertIsNone(session.process)

    def test_death_and_extra_reply_refuse(self):
        for code in ('import sys;sys.stdin.readline()', "import sys;sys.stdin.readline();print('{}\\n{}')"):
            with self.subTest(code=code), self.session(code) as session:
                with self.assertRaises((RuntimeError, ValueError)):
                    session.exchange(b'{}\n', timeout=2, identity=1)
                self.assertIsNone(session.process)

    def test_threads_share_single_serial_process(self):
        with self.session('import sys; [print(x.strip()) for x in sys.stdin]') as session:
            results, errors = [], []
            def invoke(i):
                try:
                    frame = ('{"i":%d}\n' % i).encode()
                    results.append(session.exchange(frame, timeout=5, identity=1) == frame)
                except Exception as error: errors.append(error)
            threads = [threading.Thread(target=invoke, args=(i,)) for i in range(8)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(errors, [])
            self.assertEqual(results, [True]*8)

    def test_blocked_input_uses_same_deadline(self):
        with self.session('import time;time.sleep(10)', input_limit=2*1024*1024) as session:
            with self.assertRaises(subprocess.TimeoutExpired):
                session.exchange(b'"'+b'x'*(1024*1024)+b'"\n', timeout=.1, identity=1)
            self.assertIsNone(session.process)


if __name__ == '__main__': unittest.main()
