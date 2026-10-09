"""Bounded reusable transport for the pure native package JSON-line protocol.

No artifact, evaluation, authority or receipt cache lives here. A failed exchange
destroys the process; the caller decides whether to repeat a pure computation.
One session owns one serial native child, with per-call wall/output bounds and
the shared finite Linux address-space policy (no lifetime CPU deadline).
"""
from copy import deepcopy
import math
import os
import selectors
import signal
import subprocess
import threading
import time

import process_custody


class PackageSession:
    def __init__(self, arguments, *, cwd=None, input_limit=8*1024*1024,
                 stdout_limit=8*1024*1024, stderr_limit=64*1024):
        for value in (input_limit, stdout_limit, stderr_limit):
            if type(value) is not int or value <= 0:
                raise ValueError('package frame bounds must be positive integers')
        self.arguments = [os.fspath(value) for value in arguments]
        self.cwd = cwd
        self.input_limit, self.stdout_limit, self.stderr_limit = input_limit, stdout_limit, stderr_limit
        self.process = None
        self.identity = None
        self._lock = threading.Lock()

    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def _stop(self):
        if self.process is None: return
        process, self.process = self.process, None
        try:
            if self._nested: process.kill()
            else: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            # Darwin can report EPERM for a group whose leader just exited.
            # Poll/reap that leader; a still-live child must remain killable.
            if process.poll() is None: process.kill()
        process.wait()
        for stream in (process.stdin, process.stdout, process.stderr): stream.close()
        self.identity = None

    def close(self):
        with self._lock: self._stop()

    def exchange(self, frame, *, timeout, identity):
        """Return one exact reply line, restarting on runtime identity change.

        Identity must cover the caller's runtime/configuration; it is compared as
        an entire value. Frames are bytes to preserve the native numeric spelling.
        Lock waiting, input writing and output draining share one deadline.
        """
        if not isinstance(frame, bytes): raise TypeError('package frame must be bytes')
        if not frame.endswith(b'\n') or b'\n' in frame[:-1]:
            raise ValueError('package frame must contain exactly one JSON line')
        if len(frame) > self.input_limit:
            raise process_custody.OutputLimitExceeded('package input exceeds frame bound')
        if not math.isfinite(timeout) or timeout <= 0: raise ValueError('invalid package timeout')
        deadline = time.monotonic() + timeout
        if not self._lock.acquire(timeout=timeout):
            raise subprocess.TimeoutExpired(self.arguments, timeout)
        try:
            if self.process is not None and (self.identity != identity or self.process.poll() is not None):
                self._stop()
            if self.process is None:
                command, environment = process_custody.native_launch(self.arguments)
                self._nested = os.environ.get(process_custody.GROUP_ENV) == str(os.getpgrp())
                self.process = subprocess.Popen(command, cwd=self.cwd, env=environment,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    start_new_session=not self._nested)
                self.identity = deepcopy(identity)
                for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                    os.set_blocking(stream.fileno(), False)
            process = self.process
            output, errors, sent = bytearray(), 0, 0
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdin, selectors.EVENT_WRITE, 'input')
                selector.register(process.stdout, selectors.EVENT_READ, 'output')
                selector.register(process.stderr, selectors.EVENT_READ, 'error')
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0: raise subprocess.TimeoutExpired(self.arguments, timeout)
                    for key, _ in selector.select(remaining):
                        if key.data == 'input':
                            try: sent += os.write(key.fd, memoryview(frame)[sent:sent+65536])
                            except BlockingIOError: continue
                            if sent == len(frame): selector.unregister(key.fileobj)
                            continue
                        limit = self.stdout_limit - len(output) if key.data == 'output' else self.stderr_limit - errors
                        try: chunk = os.read(key.fd, min(65536, limit+1))
                        except BlockingIOError: continue
                        if not chunk:
                            if key.data == 'output': raise RuntimeError('native package session ended before reply')
                            selector.unregister(key.fileobj)
                            continue
                        if len(chunk) > limit:
                            raise process_custody.OutputLimitExceeded('package ' + key.data + ' exceeds frame bound')
                        if key.data == 'error': errors += len(chunk)
                        else: output.extend(chunk)
                    if b'\n' in output:
                        if not output.endswith(b'\n') or output.count(b'\n') != 1 or sent != len(frame):
                            raise ValueError('native package session returned invalid framing')
                        # A child may finish stdout before its already-written
                        # diagnostic pipe has drained. Enforce that bound too.
                        while True:
                            try: chunk = os.read(process.stderr.fileno(), min(65536, self.stderr_limit-errors+1))
                            except BlockingIOError: break
                            if not chunk: break
                            errors += len(chunk)
                            if errors > self.stderr_limit:
                                raise process_custody.OutputLimitExceeded('package error exceeds frame bound')
                        return bytes(output)
        except BaseException:
            self._stop()
            raise
        finally:
            self._lock.release()
