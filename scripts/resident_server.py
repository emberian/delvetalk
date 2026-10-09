#!/usr/bin/env python3
"""Local IPC custody for one explicitly configured native resident world.

The socket is private; Lean owns admissions, queries and retained receipt lookup.
A daemon never imports a JSON world or creates a fallback receiving engine.
"""
import argparse
import errno
import hashlib
import grp
import os
from pathlib import Path
import signal
import selectors
import socket
import stat
import tempfile
import time
import uuid

import resident_store
import world


def _stop(*_):
    raise SystemExit(0)


def serve(database, *, timeout=30, read_group=None):
    database = Path(database).resolve()
    config = world.resident_config(database)
    if config is None:
        raise ValueError('explicit resident backend required')
    if world._resident_pins(config['profile']) != config['pins']:
        raise ValueError('selected resident runtime pins changed')
    socket_path = Path(config['socket'])
    read_socket = Path(config['readSocket'])
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    for endpoint in (socket_path, read_socket):
        if endpoint.exists():
            # Only the exact configured, non-listening socket can be reclaimed.
            if not stat.S_ISSOCK(endpoint.lstat().st_mode):
                raise ValueError('configured resident socket is occupied by another file')
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(1)
                try:
                    probe.connect(str(endpoint))
                except OSError as error:
                    if error.errno != errno.ECONNREFUSED:
                        raise
                else:
                    raise ValueError('configured resident daemon is already running')
            endpoint.unlink()
    storage = database.parent / config['database']
    identity = {'format': world.IPC_FORMAT, 'database': str(database), 'profile': config['profile'],
                'pinsSha256': hashlib.sha256(world.wire_dumps(config['pins']).encode()).hexdigest()}
    exports = {}
    export_directory = Path(config['exports'])
    export_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    read_gid = grp.getgrnam(read_group).gr_gid if read_group is not None else None
    if read_gid is not None:
        os.chown(export_directory, -1, read_gid)
        os.chmod(export_directory, 0o750)
    def release(token):
        owned = exports.pop(token, None)
        if owned is not None:
            owned[0].unlink(missing_ok=True)
    with resident_store.Resident(storage, profile=config['profile'], timeout=timeout) as resident:
        if world._resident_pins(config['profile']) != config['pins']:
            raise ValueError('selected resident runtime changed during startup')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener, \
                socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as reader, selectors.DefaultSelector() as endpoints:
            listener.bind(str(socket_path))
            os.chmod(socket_path, 0o600)
            owned_socket = socket_path.lstat()
            listener.listen(16)
            reader.bind(str(read_socket))
            os.chmod(read_socket, 0o600 if read_gid is None else 0o660)
            if read_gid is not None:
                os.chown(read_socket, -1, read_gid)
            owned_reader = read_socket.lstat()
            reader.listen(16)
            endpoints.register(listener, selectors.EVENT_READ, False)
            endpoints.register(reader, selectors.EVENT_READ, True)
            try:
                while True:
                    for token, (_, deadline) in list(exports.items()):
                        if time.monotonic() >= deadline:
                            release(token)
                    selected, _ = endpoints.select()[0]
                    connection, _ = selected.fileobj.accept()
                    readonly = selected.data
                    with connection:
                        connection.settimeout(timeout)
                        deadline = time.monotonic() + timeout
                        try:
                            raw = bytearray()
                            while not raw.endswith(b'\n'):
                                connection.settimeout(max(0.001, deadline - time.monotonic()))
                                if time.monotonic() >= deadline:
                                    raise TimeoutError('resident IPC receiving deadline exceeded')
                                part = connection.recv(65536)
                                if not part:
                                    raise ValueError('resident IPC request ended before frame')
                                raw.extend(part)
                                if len(raw) > 1024 * 1024:
                                    raise ValueError('resident IPC request exceeds 1 MiB')
                            frame = world.wire_loads(raw)
                            if not isinstance(frame, dict) or any(frame.get(key) != value for key, value in identity.items()):
                                raise ValueError('resident IPC world/runtime binding differs')
                            operation = frame.get('operation')
                            expected_fields = {
                                'status': set(), 'exchange': {'request'}, 'inspect': {'request'}, 'retained-reply': {'request'},
                                'query': {'request'}, 'snapshot': set(), 'checkpoint': set(),
                                'release-snapshot': {'token'},
                            }.get(operation)
                            if expected_fields is None or set(frame) != set(identity) | {'operation'} | expected_fields:
                                raise ValueError('unsupported resident IPC operation or fields')
                            if readonly and operation in ('exchange', 'checkpoint'):
                                raise PermissionError('read-only resident endpoint refuses mutations')
                            # A lost daemon-side preparation/finalization must be
                            # reconciled under its exact attempt before any new work.
                            if resident.uncertain is not None:
                                if readonly:
                                    raise RuntimeError('operator must recover uncertain resident custody before reads')
                                resident.recover()
                            if operation == 'inspect':
                                if not isinstance(frame['request'], dict) or frame['request'].get('op') != 'inspect':
                                    raise ValueError('read-only inspection requires an inspect request')
                                result = resident.exchange(frame['request'])
                            elif operation == 'exchange':
                                result = resident.exchange(frame['request'])
                            elif operation == 'retained-reply':
                                result = resident.retained_reply(frame['request'])
                            elif operation == 'query':
                                result = resident.query(frame['request'])
                            elif operation == 'snapshot':
                                if len(exports) >= 64:
                                    raise ValueError('resident snapshot export retention bound reached')
                                token = uuid.uuid4().hex
                                with tempfile.NamedTemporaryFile(dir=export_directory, prefix='snapshot-', delete=False) as stream:
                                    destination = Path(stream.name)
                                destination.unlink()  # Only this daemon's fresh empty target.
                                exports[token] = (destination, time.monotonic() + 300)
                                result = {'path': str(destination), 'token': token, 'seal': resident.export(destination)}
                                if read_gid is not None:
                                    os.chown(destination, -1, read_gid)
                                    os.chmod(destination, 0o640)
                            elif operation == 'release-snapshot':
                                token = frame['token']
                                if not isinstance(token, str):
                                    raise ValueError('snapshot release requires an opaque token')
                                release(token)
                                result = None
                            elif operation == 'checkpoint':
                                result = resident.checkpoint()
                            else:
                                result = {'status': 'ready', 'sequence': resident.sequence, 'head': resident.head}
                            response = {'result': result}
                        except resident_store.ReceivingError as error:
                            response = {'kind': 'receiving', 'error': str(error)}
                        except Exception as error:
                            response = {'kind': 'transport', 'error': str(error)}
                        reply = world.wire_dumps(response).encode('utf-8') + b'\n'
                        if len(reply) > world.MAX_IPC_FRAME:
                            reply = world.wire_dumps({'kind': 'transport', 'error': 'resident IPC reply exceeds 64 MiB'}).encode() + b'\n'
                        try:
                            connection.sendall(reply)
                        except OSError:
                            # An acknowledged SQLite commit remains retained;
                            # the caller retries its original request identity.
                            pass
            finally:
                for token in list(exports):
                    release(token)
                for endpoint, owned in ((socket_path, owned_socket), (read_socket, owned_reader)):
                    try:
                        current = endpoint.lstat()
                        if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                            endpoint.unlink()
                    except FileNotFoundError:
                        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path, help='logical world path with an explicit adjacent backend descriptor')
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--read-group', help='grant this OS group the enforced read-only endpoint and ephemeral exports')
    args = parser.parse_args()
    world._timeout(args.timeout)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    serve(args.database, timeout=args.timeout, read_group=args.read_group)


if __name__ == '__main__':
    main()
