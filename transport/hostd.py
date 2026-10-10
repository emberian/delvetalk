#!/usr/bin/env python3
"""hostd: the only program that spawns delvetalk-obend and opens a journal.

Listens on <state>/host.sock (mode 0600): one JSON line per op in, one reply line out. Ops are served
one at a time in arrival order. `heap: <did>` on the envelope addresses that principal's private heap
(<state>/heaps/<did>.journal, pool of 8, least recently used evicted); `stateless: true` addresses a
journal-less process for compile/run. It holds an exclusive flock on the lock file for its lifetime
and exits 75 if the lock is taken (the contract of deploy/one-writer.sh). A dead host process is
respawned and the journal replayed by world-open.
Run as `python3 -m transport.hostd --state DIR --journal J`.
"""
import argparse
import fcntl
import hashlib
import json
import os
import shutil
import socketserver
import sys
import threading
from pathlib import Path

from transport.hostproc import ARRIVAL, BINARY, DID_RE, LIBRARY, OBJECTS, Heaps, Host

CLOCK = 'transport'  # the clock principal named at world-open
EX_TEMPFAIL = 75


class Locked(Exception):
    pass


def take_lock(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise Locked(f'{path} is held: another process owns the journal') from None
    return fd


def sealed_library(library, directory):
    """<directory>: the library plus the packages arrival creates from (world/objects/{Avatar,Env,Wake,Place}),
    rebuilt at each start; this is what hostd seals into the world."""
    shutil.rmtree(directory, ignore_errors=True)
    shutil.copytree(library, directory)
    for name in ARRIVAL:
        shutil.copyfile(OBJECTS / f'{name}.obend', Path(directory) / f'{name}.obend')
    return directory


class Hostd(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, state, journal, binary=BINARY, lock=None, opener=None, library=None):
        self.state = Path(state)
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_fd = take_lock(lock or self.state / 'journal.lock')  # before anything else is touched
        self.binary, self.order = binary, threading.Lock()
        library = self.library = sealed_library(library, self.state / 'library') if library else None
        self.shared = Host(str(journal), binary, clock=CLOCK, opener=opener, library=library, librarian=opener)
        self.stateless = Host(None, binary, preload=library)
        self.heaps = Heaps(self.state / 'heaps', binary=binary, library=library)
        self.pidfile = self.state / 'hostd.pid'
        self.pidfile.write_text(str(os.getpid()))
        sock = self.state / 'host.sock'
        sock.unlink(missing_ok=True)
        old = os.umask(0o177)
        try:
            super().__init__(str(sock), Handler)
        finally:
            os.umask(old)
        os.chmod(sock, 0o600)
        self.sha = hashlib.sha256(Path(binary).read_bytes()).hexdigest()

    def dispatch(self, req):
        with self.order:  # one op at a time, in arrival order
            os.utime(self.pidfile)
            if req.get('op') == 'hostd-info':
                # the pin of the library the stateless process holds, which `library: <pin>` names to compile and check against it
                pin = self.stateless.send({'op': 'library-load', 'path': str(self.library)}).get('pin') if self.library else None
                return {'status': 'hostd', 'hostSha256': self.sha, 'pid': os.getpid(), **({'library': pin} if pin else {})}
            heap = req.pop('heap', None)
            if req.pop('stateless', False):
                return self.stateless.send(req)
            if heap is None:
                return self.shared.send(req)
            if not isinstance(heap, str) or not DID_RE.match(heap):
                return {'status': 'error', 'message': 'heap must be a DID'}
            return self.heaps.get(heap).send(req)

    def close(self):
        for h in (self.shared, self.stateless):
            h.close()
        self.heaps.close()
        self.server_close()
        self.pidfile.unlink(missing_ok=True)
        os.close(self.lock_fd)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        for line in self.rfile:
            try:
                req = json.loads(line)
                if not isinstance(req, dict):
                    raise ValueError
                reply = self.server.dispatch(req)
            except ValueError:
                reply = {'status': 'error', 'message': 'request is not a JSON object'}
            self.wfile.write((json.dumps(reply) + '\n').encode())
            self.wfile.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(prog='hostd.py')
    ap.add_argument('--state', required=True)
    ap.add_argument('--journal', required=True)
    ap.add_argument('--lock', help='lock file (default <state>/journal.lock)')
    ap.add_argument('--opener', default=os.environ.get('DELVETALK_OPENER'), metavar='DID', help="the world's opener (ember's DID); only the opener may create objects with an owner")
    ap.add_argument('--library', default=LIBRARY, help="the standard library sealed into each journal at its first open (with the packages arrival creates from), as the "
                    "opener's (each heap's as its owner's), so packages import it by name; '' for none")
    a = ap.parse_args(argv)
    try:
        daemon = Hostd(a.state, a.journal, lock=a.lock, opener=a.opener, library=a.library or None)
    except Locked as err:
        print(f'hostd: {err}; refusing to start a second writer', file=sys.stderr)
        return EX_TEMPFAIL
    import signal
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=daemon.shutdown).start())
    try:
        daemon.serve_forever()
    finally:
        daemon.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
