#!/usr/bin/env python3
"""Single-writer SQLite custody for a long-lived native DelveTalk receiver.

Lean selects retained receipts and prepares exact admissions. SQLite retains the
native journal atomically; it never chooses authorization, roots or retry results.
Keep the database and its WAL together. This requires a local POSIX filesystem.
"""
import argparse
import math
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runtime_profile
import process_custody
import world

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'delvetalk-resident-custody-v1'
MAX_FRAME = 64 * 1024 * 1024


class ReceivingError(ValueError):
    """The native receiver rejected a frame without changing committed state."""


def _pins(profile):
    files = runtime_profile.file_hashes(profile)
    for name in ('profiles/ResidentStore.lean', 'scripts/resident_store.py', 'scripts/process_custody.py'):
        with (ROOT / name).open('rb') as stream:
            files[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return json.dumps(files, sort_keys=True, separators=(',', ':'))


class Resident:
    """Own one resident process and SQLite writer lock until close().

    After an uncertain preparation/commit, only recover() may resume this object;
    it reconstructs durable state and retries the exact retained attempt. A new
    Resident also reconstructs committed state before accepting any request.

    Optional memory_bytes sets Linux RLIMIT_AS before exec (virtual address space,
    not an RSS guarantee). Explicit limits on unsupported systems refuse startup.
    A killed receiver is an uncertain attempt, never a semantic refusal/success.
    This persistent process has no cumulative CPU quota; RPC wall time is bounded.
    """
    def __init__(self, database, *, profile='compiled', timeout=30, use_checkpoint=True, memory_bytes=None):
        if profile not in world.PROFILES: raise ValueError('unknown resident profile')
        if not math.isfinite(timeout) or timeout <= 0: raise ValueError('resident timeout must be positive')
        if memory_bytes is not None:
            if type(memory_bytes) is not int or memory_bytes <= 0:
                raise ValueError('resident memory_bytes must be a positive integer')
            if not sys.platform.startswith('linux'):
                raise ValueError('resident memory limit requires Linux RLIMIT_AS')
        self.memory_bytes = memory_bytes
        self.database = Path(database).resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.profile, self.timeout = profile, timeout
        self.process = self.errors = self.connection = None
        self.uncertain = None
        self._buffer = bytearray()
        self.lock = open(str(self.database) + '.lock', 'a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.connection = sqlite3.connect(self.database, isolation_level=None)
            self.connection.execute('PRAGMA journal_mode=WAL')
            self.connection.execute('PRAGMA synchronous=FULL')
            self.connection.execute('PRAGMA trusted_schema=OFF')
            self.connection.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entries (
                    sequence INTEGER PRIMARY KEY, head TEXT NOT NULL UNIQUE, frame BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS checkpoints (
                    sequence INTEGER PRIMARY KEY, head TEXT NOT NULL, sha256 TEXT NOT NULL, body BLOB NOT NULL);
            ''')
            self._identity = {'format': FORMAT, 'profile': profile, 'pins': _pins(profile)}
            metadata = dict(self.connection.execute('SELECT key,value FROM metadata'))
            if not metadata:
                if self.connection.execute('SELECT count(*) FROM entries').fetchone()[0]:
                    raise ValueError('journal has no custody identity')
                self.connection.execute('BEGIN IMMEDIATE')
                try:
                    self.connection.executemany('INSERT INTO metadata VALUES (?,?)', self._identity.items())
                    self.connection.commit()
                except BaseException:
                    self.connection.rollback()
                    raise
            elif any(metadata.get(key) != value for key, value in self._identity.items()):
                raise ValueError('resident custody runtime/profile identity differs')
            self._start(use_checkpoint=use_checkpoint)
        except BaseException:
            self.close()
            raise

    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def _stop(self):
        if self.process is not None:
            try: os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
            self.process = None
        if self.errors is not None:
            self.errors.close()
            self.errors = None
        self._buffer.clear()

    def close(self):
        self._stop()
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.lock is not None:
            self.lock.close()
            self.lock = None

    def _rpc(self, frame):
        try:
            return self._rpc_raw(frame)
        except ReceivingError:
            raise
        except BaseException:
            self._stop()
            raise

    def _rpc_raw(self, frame):
        if self.process is None: raise RuntimeError('resident receiver is unavailable')
        data = world.wire_dumps(frame).encode('utf-8') + b'\n'
        if len(data) > MAX_FRAME: raise ValueError('resident frame exceeds 64 MiB')
        deadline = time.monotonic() + self.timeout
        def wait(selector):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError('resident receiving deadline exceeded')
            if os.fstat(self.errors.fileno()).st_size > 1024 * 1024:
                raise RuntimeError('resident diagnostic output exceeds 1 MiB')
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE)
            offset = 0
            while offset < len(data):
                wait(selector)
                try: offset += os.write(self.process.stdin.fileno(), data[offset:offset + 65536])
                except BlockingIOError: continue
            selector.unregister(self.process.stdin)
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while b'\n' not in self._buffer:
                wait(selector)
                try: chunk = os.read(self.process.stdout.fileno(), 65536)
                except BlockingIOError: continue
                if not chunk: raise RuntimeError('resident receiver ended before reply')
                self._buffer.extend(chunk)
                if len(self._buffer) > MAX_FRAME: raise ValueError('resident reply exceeds 64 MiB')
        line, _, tail = self._buffer.partition(b'\n')
        self._buffer = bytearray(tail)
        reply = world.wire_loads(line)
        if not isinstance(reply, dict): raise ValueError('malformed resident reply')
        if set(reply) == {'error'}: raise ReceivingError(reply['error'])
        return reply

    def _start(self, *, use_checkpoint=True):
        self._stop()
        if _pins(self.profile) != self._identity['pins']:
            raise ValueError('resident custody runtime/profile identity differs')
        executable = ROOT / '.lake/build/bin' / world.PROFILES[self.profile][0]
        if not executable.is_file(): raise ValueError('prebuilt resident receiver required')
        self.errors = tempfile.TemporaryFile()
        arguments = [str(executable), '--resident']
        if self.memory_bytes is not None:
            # The fresh interpreter sets limits before exec; no post-fork Python
            # callback runs in the threaded account-heap parent's address space.
            arguments = [sys.executable, '-c', process_custody.LAUNCH,
                         json.dumps([None, self.memory_bytes, None]), *arguments]
        self.process = subprocess.Popen(arguments, cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors, bufsize=0,
            start_new_session=True, env={**os.environ, 'LEAN_NUM_THREADS': '1'})
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        status = self._rpc({'op': 'status'})
        if status.get('status') != 'ready' or status.get('sequence') != 0:
            raise ValueError('resident did not start empty')
        count, highest = self.connection.execute('SELECT count(*),coalesce(max(sequence),0) FROM entries').fetchone()
        if count != highest: raise ValueError('resident journal has a sequence gap')
        checkpoint = self.connection.execute('SELECT sequence,head,sha256,body FROM checkpoints ORDER BY sequence DESC LIMIT 1').fetchone() if use_checkpoint else None
        if checkpoint is not None:
            sequence, head, sha, body = checkpoint
            anchor = self.connection.execute('SELECT head FROM entries WHERE sequence=?', (sequence,)).fetchone()
            if sequence == 0:
                if head != status['head']: raise ValueError('checkpoint genesis differs')
            elif anchor != (head,): raise ValueError('checkpoint journal anchor differs')
            if hashlib.sha256(body).hexdigest() != sha: raise ValueError('checkpoint content digest differs')
            with tempfile.NamedTemporaryFile(dir=self.database.parent, prefix='.resident-load-') as stream:
                stream.write(body); stream.flush()
                status = self._rpc({'op': 'load', 'path': stream.name,
                    'seal': {'sequence': sequence, 'head': head, 'sha256': sha}})
            if status.get('status') != 'loaded': raise ValueError('checkpoint was not loaded')
        for sequence, head, raw in self.connection.execute(
                'SELECT sequence,head,frame FROM entries WHERE sequence>? ORDER BY sequence', (status['sequence'],)):
            frame = world.wire_loads(raw)
            if frame.get('sequence') != sequence or frame.get('head') != head:
                raise ValueError('journal row differs from native frame')
            status = self._rpc({'op': 'restore', 'entry': frame})
            if status.get('status') != 'restored' or status.get('sequence') != sequence or status.get('head') != head:
                raise ValueError('journal restore differs')
        if status['sequence'] != highest: raise ValueError('checkpoint exceeds journal')
        self.sequence, self.head = status['sequence'], status['head']

    def _boundary(self, stage):
        """Fault-injection seam; ordinary custody has no callbacks or side effects."""

    def _persist(self, entry):
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            latest = self.connection.execute('SELECT sequence,head FROM entries ORDER BY sequence DESC LIMIT 1').fetchone()
            if latest != ((self.sequence, self.head) if self.sequence else None):
                raise ValueError('resident durable head changed outside its session')
            self.connection.execute('INSERT INTO entries VALUES (?,?,?)',
                (entry['sequence'], entry['head'], world.wire_dumps(entry).encode('utf-8')))
            self._boundary('before_commit')
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def exchange(self, request):
        if self.uncertain is not None:
            raise RuntimeError('recover the exact uncertain resident attempt before another request')
        retained = world.wire_loads(world.wire_dumps(request))
        try:
            response = self._rpc({'op': 'prepare', 'request': retained})
        except ReceivingError:
            raise
        except BaseException:
            self.uncertain = retained
            self._stop()
            raise
        if response.get('status') == 'settled':
            if response.get('sequence') != self.sequence or response.get('head') != self.head:
                self.uncertain = retained
                self._stop()
                raise ValueError('settled resident head differs')
            return response['reply']
        self.uncertain = retained
        try:
            if set(response) != {'status', 'entry'} or response['status'] != 'prepared':
                raise ValueError('malformed native preparation')
            entry = response['entry']
            if entry['previous'] != self.head or entry['sequence'] != self.sequence + 1:
                raise ValueError('prepared resident head differs')
            self._boundary('after_prepare')
            self._persist(entry)
            self._boundary('after_commit')
            finalized = self._rpc({'op': 'finalize', 'head': entry['head']})
            if finalized != {'status': 'finalized', 'sequence': entry['sequence'], 'head': entry['head']}:
                raise ValueError('resident finalization differs')
            self.sequence, self.head = entry['sequence'], entry['head']
            self._boundary('after_finalize')
            self._boundary('before_reply')
            self.uncertain = None
            return entry['reply']
        except BaseException:
            self._stop()
            raise

    def recover(self):
        if self.uncertain is None: raise ValueError('resident has no uncertain attempt')
        request = self.uncertain
        self._start()
        self.uncertain = None
        return self.exchange(request)

    def retained_reply(self, request):
        if self.uncertain is not None: raise RuntimeError('recover before querying resident custody')
        response = self._rpc({'op': 'lookup', 'request': request})
        if response.get('status') != 'lookup': raise ValueError('invalid native lookup reply')
        return response['reply']

    def query(self, request):
        if self.uncertain is not None: raise RuntimeError('recover before querying resident custody')
        response = self._rpc({'op': 'query', 'request': request})
        if response.get('status') != 'query': raise ValueError('invalid native query reply')
        return response['reply']

    def _snapshot(self):
        if self.uncertain is not None: raise RuntimeError('recover before exporting resident custody')
        with tempfile.NamedTemporaryFile(dir=self.database.parent, prefix='.resident-export-') as stream:
            response = self._rpc({'op': 'export', 'path': stream.name})
            if response.get('status') != 'exported': raise ValueError('native export failed')
            stream.seek(0)
            raw = stream.read()
        seal = response['seal']
        if seal != {'sequence': self.sequence, 'head': self.head, 'sha256': hashlib.sha256(raw).hexdigest()}:
            raise ValueError('native export seal differs')
        return raw, seal

    def export_world(self):
        """Explicit O(history) expanded snapshot for reference/replay consumers."""
        raw, _ = self._snapshot()
        return world.wire_loads(raw)

    def export(self, destination):
        destination = Path(destination).resolve()
        if destination.exists(): raise ValueError('resident export destination already exists')
        raw, seal = self._snapshot()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                os.link(temporary, destination)
                directory = os.open(destination.parent, os.O_RDONLY)
                try: os.fsync(directory)
                finally: os.close(directory)
            finally:
                temporary.unlink()
        return seal

    def checkpoint(self):
        raw, seal = self._snapshot()
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            existing = self.connection.execute('SELECT head,sha256,body FROM checkpoints WHERE sequence=?', (self.sequence,)).fetchone()
            value = (self.head, seal['sha256'], raw)
            if existing is not None and existing != value: raise ValueError('checkpoint identity reused')
            if existing is None:
                self.connection.execute('INSERT INTO checkpoints VALUES (?,?,?,?)', (self.sequence, *value))
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        return seal

    def audit(self):
        """Reproduce every stored admission through native receiving from genesis."""
        if self.uncertain is not None: raise RuntimeError('recover before resident audit')
        expected = self.sequence, self.head
        try:
            self._start(use_checkpoint=False)
            if (self.sequence, self.head) != expected: raise ValueError('resident audit changed the head')
        except BaseException:
            self._stop()
            raise
        return {'sequence': self.sequence, 'head': self.head}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=world.PROFILES, default='compiled')
    parser.add_argument('database', type=Path)
    sub = parser.add_subparsers(dest='operation', required=True)
    sub.add_parser('exchange').add_argument('request', type=Path)
    sub.add_parser('export').add_argument('destination', type=Path)
    sub.add_parser('checkpoint')
    sub.add_parser('audit')
    args = parser.parse_args()
    with Resident(args.database, profile=args.profile) as resident:
        if args.operation == 'exchange': result = resident.exchange(world.wire_loads(args.request.read_bytes()))
        elif args.operation == 'export': result = resident.export(args.destination)
        elif args.operation == 'checkpoint': result = resident.checkpoint()
        else: result = resident.audit()
        print(world.wire_dumps(result))


if __name__ == '__main__': main()
