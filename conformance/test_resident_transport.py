"""Actual consumers use a persistent receiver; reads have an enforced IPC boundary."""
import copy
from contextlib import closing
from decimal import Decimal
import fcntl
import hashlib
from native_support import load_script
from pathlib import Path
import socket
import sqlite3
import stat
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
world = load_script(ROOT / 'scripts/world.py', 'resident_transport_world')


def protocol():
    return {'profile': 'delvetalk-local-v1', 'initial': {'n': Decimal('1.2300'), 'flag': True}, 'commands': {
        'write': {'require': [], 'set': {'n': ['input', 'n']}, 'result': ['input', 'n'], 'outbox': []}}}


class ResidentTransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.database = self.directory / 'world.json'
        self.config = world.configure_resident(self.database, profile='compiled')
        self.create = {'op': 'create', 'object': 'counter', 'principal': 'p', 'intent': 'create',
                       'protocol': protocol(), 'law': ['p']}

    def exchange(self, request):
        return world.exchange(self.database, request, profile='compiled')

    def inspect(self):
        return self.exchange({'op': 'inspect', 'object': 'counter', 'principal': 'reader'})

    def rows(self):
        with closing(sqlite3.connect(self.directory / self.config['database'])) as connection:
            return connection.execute('SELECT count(*) FROM entries').fetchone()[0]

    def test_persistent_receiving_snapshot_retention_and_restart(self):
        with world.resident_session(self.database):
            created = self.exchange(self.create)
            self.assertEqual(created['kind'], 'committed')
            root = created['data']['root']
            write = {'op': 'invoke', 'object': 'counter', 'principal': 'p', 'intent': 'write',
                     'expected': root, 'command': 'write', 'input': {'n': 2}}
            receipt = self.exchange(write)
            self.assertEqual(receipt['kind'], 'committed')
            self.assertEqual(self.exchange(write), receipt)
            self.assertEqual(world.retained_reply(self.database, write), receipt)
            self.assertIsNone(world.retained_reply(self.database, {**write, 'intent': 'unknown'}))
            with patch.object(world.tempfile, 'NamedTemporaryFile', side_effect=AssertionError('read client wrote export')):
                snapshot = world.snapshot(self.database)
            self.assertEqual(snapshot['objects']['counter'], self.inspect())
            self.assertEqual(self.rows(), 2)
            self.assertFalse(self.database.exists())
            self.assertEqual(list(Path(self.config['exports']).iterdir()), [])
        with world.resident_session(self.database):
            self.assertEqual(self.exchange(write), receipt)
            self.assertEqual(world.snapshot(self.database), snapshot)
            self.assertEqual(self.rows(), 2)

    def test_read_endpoint_refuses_writes_even_for_operator_credentials(self):
        with world.resident_session(self.database):
            created = self.exchange(self.create)
            for operation, fields in [('exchange', {'request': {**self.create, 'intent': 'other'}}),
                                      ('checkpoint', {}), ('inspect', {'request': self.create})]:
                with self.subTest(operation=operation), self.assertRaisesRegex(RuntimeError, 'read-only'):
                    world._resident_rpc(self.database, self.config, operation, readonly=True, **fields)
            self.assertEqual(self.inspect(), created['data']['root'])
            self.assertEqual(self.rows(), 1)
            self.assertEqual(stat.S_IMODE(Path(self.config['socket']).stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(Path(self.config['readSocket']).stat().st_mode), 0o600)

    def test_lost_socket_reply_recovers_exact_receipt_without_second_admission(self):
        with world.resident_session(self.database):
            root = self.exchange(self.create)['data']['root']
            request = {'op': 'invoke', 'object': 'counter', 'principal': 'p', 'intent': 'lost',
                       'expected': root, 'command': 'write', 'input': {'n': 5}}
            frame = {'format': world.IPC_FORMAT, 'database': str(self.database), 'profile': 'compiled',
                     'pinsSha256': hashlib.sha256(world.wire_dumps(self.config['pins']).encode()).hexdigest(),
                     'operation': 'exchange', 'request': request}
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.connect(self.config['socket'])
                connection.sendall(world.wire_dumps(frame).encode() + b'\n')
                # Close before reading acknowledgement; native admission remains authoritative.
            recovered = self.exchange(request)
            self.assertEqual(recovered['kind'], 'committed')
            self.assertEqual(world.retained_reply(self.database, request), recovered)
            self.assertEqual(self.rows(), 2)
            self.assertEqual(self.inspect()['state']['n'], 5)

    def test_unavailable_profile_and_runtime_drift_fail_without_file_fallback(self):
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.exchange(self.create)
        with self.assertRaisesRegex(ValueError, 'profile differs'):
            world.exchange(self.database, self.create, profile='world')
        changed = copy.deepcopy(self.config)
        changed['pins']['scripts/world.py'] = '0' * 64
        world._descriptor_path(self.database).write_text(world.wire_dumps(changed))
        with self.assertRaisesRegex(RuntimeError, 'runtime pins changed'):
            with world.resident_session(self.database, timeout=2):
                self.fail('changed runtime started')
        self.assertFalse(self.database.exists())

    def test_file_lookup_preserves_record_order_and_numeric_representation(self):
        database = self.directory / 'file.json'
        created = world.exchange(database, self.create)
        self.assertEqual(world.retained_reply(database, dict(reversed(list(self.create.items())))), created)
        changed = copy.deepcopy(self.create)
        changed['protocol']['initial']['n'] = Decimal('1.23')
        self.assertIsNone(world.retained_reply(database, changed))
        changed = copy.deepcopy(self.create)
        changed['protocol']['initial']['flag'] = 1
        self.assertIsNone(world.retained_reply(database, changed))
        self.assertEqual(len(world.snapshot(database)['receipts']), 1)

    def test_file_query_lock_deadline_is_finite(self):
        database = self.directory / 'blocked.json'
        with open(str(database) + '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            start = time.monotonic()
            with self.assertRaisesRegex(TimeoutError, 'lock deadline'):
                world.query(database, {'op': 'messages-pending', 'principal': 'reader'}, timeout=0.05)
            self.assertLess(time.monotonic() - start, 1)


if __name__ == '__main__':
    unittest.main()
