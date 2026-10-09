"""Bounded POSIX child custody, without Python callbacks after fork.

Spools bound parent reads independently of child memory limits. File-size limits
are optional: receiving children may legitimately write large world snapshots.
"""
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time


class OutputLimitExceeded(RuntimeError):
    pass


GROUP_ENV = 'DELVETALK_CUSTODY_GROUP'

LAUNCH = """import json, os, resource, sys
cpu, memory, file_size = json.loads(sys.argv[1])
def limit(kind, wanted):
    hard = resource.getrlimit(kind)[1]
    value = wanted if hard == resource.RLIM_INFINITY else min(wanted, hard)
    resource.setrlimit(kind, (value, value))
    return value
limit(resource.RLIMIT_CPU, cpu)
if memory is not None and sys.platform.startswith('linux'):
    memory = limit(resource.RLIMIT_AS, memory)
    os.environ['MIMALLOC_ARENA_RESERVE'] = '131072'
    os.environ['LEAN_STACK_SIZE_KB'] = str(min(64 * 1024, memory // 4 // 1024))
if file_size is not None:
    limit(resource.RLIMIT_FSIZE, file_size)
os.environ['DELVETALK_CUSTODY_GROUP'] = str(os.getpgrp())
os.execvp(sys.argv[2], sys.argv[2:])
"""


def run(arguments, *, timeout, cpu_seconds, stdout_limit, stderr_limit,
        input=None, cwd=None, env=None, memory_bytes=None, file_limit=None):
    """Return exact byte outputs and reap our child on every exit.

    A size violation raises OutputLimitExceeded; wall expiry raises TimeoutExpired.
    A normal nonzero exit remains a CompletedProcess for caller-specific reporting.
    Spool writes may briefly exceed their capture limit between polling intervals;
    at most limit+1 bytes are ever read into the parent. Optional RLIMIT_FSIZE also
    bounds every regular file written by the child, so it must be chosen explicitly.
    The outermost custodian owns and terminates the whole process group. Nested
    custodians stay in that group, kill/reap their direct child on exit, and leave
    descendant cleanup to the outer boundary (including after normal completion).
    """
    if os.name != 'posix':
        raise RuntimeError('process custody requires POSIX process groups')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be positive and finite')
    for name, value in (('cpu_seconds', cpu_seconds), ('stdout_limit', stdout_limit),
                        ('stderr_limit', stderr_limit), ('memory_bytes', memory_bytes),
                        ('file_limit', file_limit)):
        if value is None and name in ('memory_bytes', 'file_limit'): continue
        if type(value) is not int or value <= 0:
            raise ValueError(name + ' must be a positive integer')
    if input is not None and not isinstance(input, bytes):
        raise TypeError('process input must be bytes')
    arguments = [os.fspath(value) for value in arguments]
    if not arguments: raise ValueError('process command is empty')
    nested = os.environ.get(GROUP_ENV) == str(os.getpgrp())
    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        if input is not None: source.write(input)
        source.seek(0)
        process = subprocess.Popen([sys.executable, '-c', LAUNCH,
            json.dumps([cpu_seconds, memory_bytes, file_limit]), *arguments],
            cwd=cwd, env=env, stdin=source, stdout=output, stderr=errors,
            start_new_session=not nested)
        deadline = time.monotonic() + timeout
        def check_sizes():
            for name, stream, limit in (('stdout', output, stdout_limit), ('stderr', errors, stderr_limit)):
                if os.fstat(stream.fileno()).st_size > limit:
                    raise OutputLimitExceeded(name + ' exceeds ' + str(limit) + ' bytes')
        try:
            while True:
                check_sizes()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(arguments, timeout)
                try:
                    process.wait(timeout=min(0.02, remaining))
                    break
                except subprocess.TimeoutExpired:
                    pass
        finally:
            try:
                if nested: process.kill()
                else: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        check_sizes()
        output.seek(0); errors.seek(0)
        stdout, stderr = output.read(stdout_limit + 1), errors.read(stderr_limit + 1)
        if len(stdout) > stdout_limit or len(stderr) > stderr_limit:
            raise OutputLimitExceeded('output changed beyond capture bound')
        return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)
