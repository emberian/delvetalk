#!/usr/bin/env python3
"""Local durable transport; the selected Lean profile owns semantic decisions.

Input: one request JSON file, or '-' for stdin. Output: Lean's reply JSON.
Principal strings are assertions by the local caller, NOT authenticated identities.
The database and lock must be on a local filesystem supporting flock/atomic rename.
"""
import argparse
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import importlib.util
import json
import os
import math
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import time

# Lean Nat is unbounded. Do not impose Python's decimal conversion cap on
# otherwise admitted finite results; Lean owns the request/frame envelopes.
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'world': ('delvetalk-world', 'World.lean'),
    'transactions': ('delvetalk-transactions', 'Transactions.lean'),
    'compiled': ('delvetalk-compiled', 'Compiled.lean'),
}
BACKEND_FORMAT = 'delvetalk-resident-backend-v1'
IPC_FORMAT = 'delvetalk-resident-ipc-v1'
MAX_IPC_FRAME = 64 * 1024 * 1024
MAX_EXPANDED_REQUEST_BYTES = 1024 * 1024


def _descriptor_path(database):
    return Path(str(Path(database).resolve()) + '.backend.json')


def resident_config(database):
    """Only an explicit adjacent descriptor selects resident custody."""
    path = _descriptor_path(database)
    if not path.exists():
        return None
    value = wire_loads(path.read_bytes())
    if (not isinstance(value, dict) or set(value) != {'format', 'database', 'socket', 'readSocket', 'exports', 'profile', 'pins'}
            or value['format'] != BACKEND_FORMAT or not isinstance(value['profile'], str) or value['profile'] not in PROFILES
            or not isinstance(value['database'], str) or Path(value['database']).name != value['database']
            or value['database'] in ('', '.', '..')
            or not isinstance(value['socket'], str) or not Path(value['socket']).is_absolute()
            or str(Path(value['socket']).resolve()) != value['socket']
            or not isinstance(value['readSocket'], str) or not Path(value['readSocket']).is_absolute()
            or str(Path(value['readSocket']).resolve()) != value['readSocket']
            or value['readSocket'] == value['socket']
            or not isinstance(value['exports'], str) or not Path(value['exports']).is_absolute()
            or str(Path(value['exports']).resolve()) != value['exports']
            or not isinstance(value['pins'], dict) or not value['pins']
            or any(not isinstance(k, str) or not isinstance(v, str) or len(v) != 64
                   or any(c not in '0123456789abcdef' for c in v) for k, v in value['pins'].items())):
        raise ValueError('malformed explicit resident backend descriptor')
    storage = Path(database).resolve().parent / value['database']
    if storage.resolve().parent != Path(database).resolve().parent:
        raise ValueError('resident storage escapes its world directory')
    return value


def is_resident(database):
    return resident_config(database) is not None


def exists(database):
    config = resident_config(database)
    return (Path(database).resolve().parent / config['database']).is_file() if config else Path(database).is_file()


def _resident_pins(profile):
    spec = importlib.util.spec_from_file_location('transport_runtime', ROOT / 'scripts/runtime_profile.py')
    runtime_profile = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime_profile)
    return runtime_profile.hash_paths((*runtime_profile.paths(profile),
        'profiles/ResidentStore.lean', 'scripts/resident_store.py', 'scripts/resident_server.py'), root=ROOT)


def configure_resident(database, *, profile='compiled', socket_path=None, timeout=30):
    """Select a fresh resident world; this never imports or replaces JSON custody."""
    _timeout(timeout)
    if profile not in PROFILES:
        raise ValueError('unknown resident profile')
    database = Path(database).resolve()
    storage = database.with_name(database.name + '.sqlite3')
    if database.exists() or storage.exists() or _descriptor_path(database).exists():
        raise ValueError('resident selection requires fresh world custody')
    database.parent.mkdir(parents=True, exist_ok=True)
    if socket_path is None:
        socket_path = Path(tempfile.mkdtemp(prefix='delvetalk-resident-', dir='/tmp')) / 'receiver.sock'
    socket_path = Path(socket_path).resolve()
    if len(os.fsencode(socket_path)) > 95:
        raise ValueError('resident Unix socket path exceeds 95 bytes')
    if socket_path.exists():
        raise ValueError('resident socket already exists')
    value = {'format': BACKEND_FORMAT, 'database': storage.name, 'socket': str(socket_path),
             'readSocket': str(socket_path) + '.read',
             'exports': str(socket_path.parent / (socket_path.name + '.exports')),
             'profile': profile, 'pins': _resident_pins(profile)}
    path = _descriptor_path(database)
    with path.open('x') as stream:
        stream.write(wire_dumps(value) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(database.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return value


def _timeout(value):
    if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 300:
        raise ValueError('transport timeout must be finite and in (0,300]')
    return value


def _resident_rpc(database, config, operation, *, timeout=30, readonly=False, **fields):
    timeout = _timeout(timeout)
    import hashlib
    frame = {'format': IPC_FORMAT, 'database': str(Path(database).resolve()),
             'profile': config['profile'],
             'pinsSha256': hashlib.sha256(wire_dumps(config['pins']).encode()).hexdigest(),
             'operation': operation, **fields}
    data = wire_dumps(frame).encode('utf-8') + b'\n'
    if len(data) > 1024 * 1024:
        raise ValueError('resident IPC request exceeds 1 MiB')
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            deadline = time.monotonic() + timeout
            connection.settimeout(timeout)
            connection.connect(config['readSocket'] if readonly else config['socket'])
            connection.settimeout(max(0.001, deadline - time.monotonic()))
            connection.sendall(data)
            response = bytearray()
            while not response.endswith(b'\n'):
                if time.monotonic() >= deadline:
                    raise TimeoutError('resident IPC receiving deadline exceeded')
                connection.settimeout(max(0.001, deadline - time.monotonic()))
                part = connection.recv(65536)
                if not part:
                    raise RuntimeError('resident daemon ended before its reply; retry the exact request')
                response.extend(part)
                if len(response) > MAX_IPC_FRAME:
                    raise ValueError('resident IPC reply exceeds 64 MiB')
    except (OSError, TimeoutError) as error:
        raise RuntimeError('explicit resident backend unavailable or reply uncertain: ' + str(error)) from error
    result = wire_loads(response)
    if not isinstance(result, dict) or set(result) not in ({'result'}, {'error', 'kind'}):
        raise ValueError('malformed resident IPC response')
    if 'error' in result:
        failure = ValueError if result['kind'] == 'receiving' else RuntimeError
        raise failure(result['error'])
    return result['result']


@contextmanager
def resident_session(database, *, profile=None, timeout=30):
    """Own a local daemon lifetime for an explicitly configured world."""
    timeout = _timeout(timeout)
    config = resident_config(database)
    if config is None or (profile is not None and profile != config['profile']):
        raise ValueError('explicit resident configuration/profile required')
    if Path(config['socket']).exists():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(min(1, timeout))
            try:
                probe.connect(config['socket'])
            except OSError as error:
                import errno
                if error.errno != errno.ECONNREFUSED:
                    raise RuntimeError('configured resident socket is occupied') from error
            else:
                raise ValueError('configured resident daemon is already running')
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/resident_server.py'), str(Path(database).resolve())],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=errors, stderr=errors, start_new_session=True)
        try:
            deadline = time.monotonic() + timeout
            while True:
                if process.poll() is not None:
                    errors.seek(0)
                    raise RuntimeError('resident daemon failed to start: ' + errors.read(1048576).decode('utf-8', errors='replace'))
                try:
                    status = _resident_rpc(database, config, 'status', timeout=min(1, max(0.001, deadline-time.monotonic())))
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.02)
            yield status
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def snapshot_bytes(database, *, timeout=30):
    """Expand custody on demand; ordinary resident admissions never rewrite it."""
    database = Path(database).resolve()
    config = resident_config(database)
    if config is None:
        return database.read_bytes()
    exported = _resident_rpc(database, config, 'snapshot', timeout=timeout, readonly=True)
    if (not isinstance(exported, dict) or set(exported) != {'path', 'token', 'seal'}
            or not isinstance(exported['token'], str)
            or not isinstance(exported['path'], str) or not isinstance(exported['seal'], dict)
            or Path(exported['path']).parent.resolve() != Path(config['exports'])):
        raise ValueError('malformed resident snapshot export')
    try:
        import hashlib
        raw = Path(exported['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != exported['seal'].get('sha256'):
            raise ValueError('resident snapshot export seal differs')
        return raw
    finally:
        try:
            _resident_rpc(database, config, 'release-snapshot', timeout=timeout, readonly=True, token=exported['token'])
        except (ValueError, RuntimeError):
            pass  # The daemon expires only its own exports after client loss.


def snapshot(database, *, timeout=30):
    return wire_loads(snapshot_bytes(database, timeout=timeout))


def retained_reply(database, request, *, timeout=30):
    config = resident_config(database)
    if config is not None:
        return _resident_rpc(database, config, 'retained-reply', timeout=timeout, readonly=True, request=request)
    if not Path(database).exists():
        return None
    executable = ROOT / '.lake/build/bin' / PROFILES['world'][0]
    if not executable.is_file():
        raise RuntimeError('prebuilt native receipt lookup required')
    response = subprocess.run([str(executable), '--lookup-files', str(Path(database).resolve())],
        cwd=ROOT, input=wire_dumps(request) + '\n', text=True, capture_output=True,
        timeout=_timeout(timeout), env={**os.environ, 'LEAN_NUM_THREADS': '1'})
    if response.returncode:
        raise RuntimeError(response.stderr + response.stdout)
    result = wire_loads(response.stdout)
    if result is None:
        return None
    if not isinstance(result, dict):
        raise ValueError('malformed native receipt lookup response')
    if set(result) == {'error'}:
        raise ValueError(result['error'])
    return result


def query(database, request, *, profile='compiled', timeout=30):
    config = resident_config(database)
    if config is None:
        if profile not in PROFILES:
            raise ValueError('unknown native query profile')
        executable = ROOT / '.lake/build/bin' / PROFILES[profile][0]
        response = subprocess.run([str(executable), '--query-files', str(Path(database).resolve())],
            cwd=ROOT, input=wire_dumps(request) + '\n', text=True, capture_output=True,
            timeout=_timeout(timeout), env={**os.environ, 'LEAN_NUM_THREADS': '1'})
        if response.returncode:
            raise RuntimeError(response.stderr + response.stdout)
        result = wire_loads(response.stdout)
        if not isinstance(result, dict):
            raise ValueError('malformed native query response')
        if set(result) == {'error'}:
            raise ValueError(result['error'])
        if set(result) != {'reply'}:
            raise ValueError('malformed native query fields')
        return result['reply']
    if profile != config['profile']:
        raise ValueError('selected resident profile differs from caller')
    return _resident_rpc(database, config, 'query', timeout=timeout, readonly=True, request=request)


def wire_loads(text):
    def invalid(value):
        raise ValueError('non-JSON number: ' + value)
    return json.loads(text, parse_float=Decimal, parse_constant=invalid)


def _needs_decimal_encoding(value):
    """Check object keys before native JSON can silently coerce them."""
    if isinstance(value, dict):
        decimal = False
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('JSON object keys must be strings')
            # Visit every child: short-circuiting would miss invalid later keys.
            decimal = _needs_decimal_encoding(item) or decimal
        return decimal
    if isinstance(value, (list, tuple)):
        decimal = False
        for item in value:
            decimal = _needs_decimal_encoding(item) or decimal
        return decimal
    return isinstance(value, Decimal)


def _decimal_dumps(value):
    # Preserve exact decimal preimages: binary float roundtrips can merge roots.
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('non-JSON decimal')
        return str(value)
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(key, ensure_ascii=False) + ':' + _decimal_dumps(item)
                              for key, item in value.items()) + '}'
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(_decimal_dumps(item) for item in value) + ']'
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def wire_dumps(value):
    if _needs_decimal_encoding(value):
        return _decimal_dumps(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def exchange(database, request, *, profile='world', timeout=30):
    deadline = time.monotonic() + _timeout(timeout)
    config = resident_config(database)
    if config is not None:
        if profile != config['profile']:
            raise ValueError('selected resident profile differs from caller')
        inspect = isinstance(request, dict) and request.get('op') == 'inspect'
        return _resident_rpc(database, config, 'inspect' if inspect else 'exchange', timeout=timeout,
                             readonly=inspect, request=request)
    try:
        binary, source = PROFILES[profile]
    except KeyError:
        raise ValueError('unknown local host profile: ' + str(profile)) from None
    database = Path(database).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    # The lock has stable identity across replacing the database file.
    with open(str(database) + '.lock', 'a') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('file custody lock deadline exceeded')
                time.sleep(min(0.02, remaining))
        executable = ROOT / '.lake/build/bin' / binary
        command = ([str(executable)] if executable.exists() else
                   ['lake', 'env', 'lean', '--run', 'profiles/' + source])
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=database.parent,
                                             prefix=database.name + '.', delete=False) as f:
                temporary = f.name
            # Paths are trusted custody arguments, never fields of a request.
            # Lean reads the snapshot and retains all admission/replay decisions.
            proc = subprocess.run([*command, '--files', str(database), temporary], cwd=ROOT,
                                  input=wire_dumps(request) + '\n', text=True, capture_output=True,
                                  timeout=max(0.001, deadline - time.monotonic()),
                                  env={**os.environ, 'LEAN_NUM_THREADS': '1'})
            if proc.returncode:
                raise RuntimeError(proc.stderr + proc.stdout)
            response = wire_loads(proc.stdout)
            if not isinstance(response, dict):
                raise ValueError('malformed file custody response')
            if set(response) == {'error'}:
                raise ValueError(response['error'])
            if set(response) != {'reply', 'changed'} or type(response['changed']) is not bool:
                raise ValueError('malformed file custody response')
            # A retained reply can follow a prior rename whose directory fsync
            # failed. Re-establish both barriers even when admission is unchanged.
            descriptor = os.open(temporary if response['changed'] else database, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
                    raise ValueError('missing file custody snapshot or candidate')
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if response['changed']:
                os.replace(temporary, database)
                temporary = None
            directory = os.open(database.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return response['reply']
        finally:
            if temporary is not None:
                os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=PROFILES, default='world',
                        help='opt-in Lean host admission profile (default: world)')
    parser.add_argument('database', type=Path)
    parser.add_argument('request', help="request JSON path, or '-' for stdin")
    args = parser.parse_args()
    request = wire_loads(sys.stdin.read() if args.request == '-' else Path(args.request).read_text())
    try:
        print(wire_dumps(exchange(args.database, request, profile=args.profile)))
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({'transport_error': str(exc)}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
