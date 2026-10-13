"""The transport's files (docs/OPERATIONS.md section b): every path under `<state>/` is named here once, and no other
module joins one. `<state>/` is serve's directory too (its journals, lock, library, scratch/ worlds and sockets); what the
transport keeps is either shared by every world (the claims, the access log, the hand's log, the model's spend, the
bridge rows) or a world's own, under `worlds/<world>/`, the town's like any other's."""
import contextlib
import fcntl
import hashlib
import json
import os
import re
import signal
import sqlite3
import tempfile
import threading
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from transport.config import Config
from transport.delve import canonical
from transport.host import HostClient

NAME = re.compile(r'[a-z][a-z0-9-]{0,31}\Z')
_DRAFT_HELD = threading.local()

RESERVED = ('did', 'zulip', 'guest', 'at', 'world', 'me', 'scratch')  # prefixes a local id can start with (docs/FEDERATION.md section 1)


class State:
    def __init__(self, root, world='town', config=None):
        if not NAME.match(world) or world in RESERVED:
            raise SystemExit(f'{world!r} is not a world name: [a-z][a-z0-9-]{{0,31}}, never {", ".join(RESERVED)}')
        self.root, self.world = Path(root), world
        self.config = config or Config.load(self.root)
        c, r = self.config, self.root
        # serve's, read here
        self.journal, self.library = r / f'{world}.journal', r / 'library'  # the library serve sealed from config.library
        self.host_socket = Path(c.host_socket) if c.host_socket else r / 'host.sock'
        self.root_socket = Path(c.root_socket) if c.root_socket else r / 'root' / 'root.sock'
        # every world's
        self.identity, self.access_log, self.hand_log = r / 'identity.sqlite', r / 'access.log', r / 'hand-log.jsonl'
        self.lexicon_ledger = r / 'lexicons' / (urllib.parse.quote(c.lexicon_authority, safe='') + '.json')  # account-wide schema digests
        self.spend, self.row = r / 'model-spend.jsonl', r / 'bridges' / f'{world}.json'
        self.repo_key = Path(c.repo_keys) / f'{world}.key'
        # this world's
        self.home = h = r / 'worlds' / world
        self.observed, self.since = h / 'observe.sqlite', h / 'since'  # the observer's posts; where its observing began
        self.draft_locks = h / 'draft-locks'
        self.outbox, self.awaiting = h / 'outbox', h / 'awaiting'  # drafts; turns waiting on an interpretation
        self.principals, self.mentioned, self.skipped = h / 'principals.txt', h / 'mentioned.txt', h / 'skipped.txt'
        self.publications = h / 'publications.after'  # the cursor of what objects published
        self.posting, self.interpretations = h / 'posting', h / 'interpretations'  # the posting ledger; model replies by request
        self.watch_log, self.alerted = h / 'watch.jsonl', h / 'alerted.json'
        self.mirror = h / 'mirror.json'  # what the mirror last wrote to the PDS: {collection rkey: digest}
        self.serviceauth_ledger = h / 'serviceauth.json'  # consumed audience/issuer/nonces until JWT expiry
        self.repo_ledger = h / 'repo.json'  # signing key, journal base, chain epochs and last served head
        self.firehose = h / 'events'  # length-prefixed DAG-CBOR records: seq, kind, epoch, height, exact event frame bytes;
        # fsynced before delivery, newest 10,000 retained, atomic rewrite at 20,000; copied by carry and state backups
        self.taught = h / 'taught.txt'  # the residents whose first admitted reply carried the next move
        self.requests = h / 'requests.json'  # {revs: {did: {pds, rev}}, refused: {uri: {cid, why}}}; consumed URIs stay in observe.sqlite
        self.hosted = r / 'hosted' / urllib.parse.quote(c.origin.rstrip('/'), safe='')  # origin-wide public snapshots
        self.legacy_hosted = h / 'hosted'  # per-world migration input; only town snapshots can be adopted
        self.answers = h / 'answers'  # online.fg-goose.gsb.answer records, <did>.<rkey>.json: the façade and the mirror serve them

    def hosted_paths(self, name):
        """An Accounts-validated file stem -> public snapshot; legacy siblings are migration inputs only."""
        return self.hosted / (name + '.json')

    def host(self, **more):
        return HostClient(self.host_socket, **{'world': self.world, **more})

    def root_host(self):
        return HostClient(self.root_socket, self.world)

    def serve_argv(self):
        """`delvetalk-obend serve` as the config has it; an empty opener, library or group is left to serve's default."""
        c = self.config
        given = {'--opener': c.opener, '--library': c.library, '--root-group': c.root_group}
        return [c.obend, 'serve', '--state', str(self.root), '--socket', str(self.host_socket), '--root-socket', str(self.root_socket),
                '--sync', c.sync, *(x for k, v in given.items() if v for x in (k, v))]

    # ---- files

    @staticmethod
    def write(path, value):
        """`value` as canonical JSON at `path`, whole or not at all."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
        tmp = Path(name)
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(canonical(value) + '\n')
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def new_draft(self, path, value):
        """Create a draft with its creation time; later mutations use write."""
        self.write(path, dict(value, createdAt=datetime.now(timezone.utc).isoformat()))

    @contextlib.contextmanager
    def draft_lock(self, path):
        """Hold a draft across threads and processes; reject same-thread reentry."""
        key = Path(path).resolve()
        held = getattr(_DRAFT_HELD, 'paths', set())
        if key in held:
            raise RuntimeError(f'draft lock already held: {key}')
        _DRAFT_HELD.paths = held
        self.draft_locks.mkdir(parents=True, exist_ok=True, mode=0o700)
        held.add(key)
        try:
            with open(self.draft_locks / (hashlib.sha256(str(key).encode()).hexdigest() + '.lock'), 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                yield
        finally:
            held.remove(key)

    @staticmethod
    def words(path):
        return set(path.read_text().split()) if path.exists() else set()

    @staticmethod
    def lines(path):
        """A JSON-lines file of the transport's (the hand's log, the spend ledger, the watch log), a torn line left out."""
        rows = []
        for line in path.read_text().splitlines() if path.exists() else []:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
        return rows

    @staticmethod
    def append(path, line):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(path, 'a') as f:
            f.write(line + '\n')

    def access(self):
        """The front's access log, its rotated generation first, each line split: time method path status bytes did world."""
        return [l.split() for p in (self.access_log.with_name(self.access_log.name + '.1'), self.access_log) if p.exists()
                for l in p.read_text().splitlines()]

    def observations(self):
        """The observer's posts, oldest observed first (observe.py writes them)."""
        if not self.observed.exists():
            return []
        db = sqlite3.connect(self.observed)
        try:
            return [json.loads(js) for (js,) in db.execute('SELECT json FROM observations ORDER BY seq')]
        except sqlite3.OperationalError:
            return []
        finally:
            db.close()

    def drafts(self):
        """[(path, draft)] of the outbox, oldest first."""
        return [(p, json.loads(p.read_text())) for p in sorted(self.outbox.glob('*.json'), key=lambda p: int(p.name.split('-')[0]))]

    def unposted(self):
        return [(p, d) for p, d in self.drafts() if not d['posted'] and not d.get('skipped') and not d.get('unposted')]

    def mark_posted(self, path):
        with self.draft_lock(path):
            self.write(path, dict(json.loads(Path(path).read_text()), posted=True))

    def bridge(self):
        """The world's bridge row (`open`); a world without one is observed on delve.town."""
        return json.loads(self.row.read_text()) if self.row.exists() else {'world': self.world, 'transport': 'delve'}

    def pidfile(self, name):
        return self.home / f'{name}.pid'

    def daemon(self, name, step, stop=None, every=None):
        """step() every `every` seconds (default `poll`) under a pid file; SIGTERM/SIGINT finish the current step and exit."""
        stop, pidfile = stop or threading.Event(), self.pidfile(name)
        pidfile.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), 0)
                raise SystemExit(f'{name} already running (pid {pidfile.read_text().strip()})')
            except (ProcessLookupError, ValueError):
                pass
        pidfile.write_text(str(os.getpid()))
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *_: stop.set())
        try:
            while not stop.is_set():
                step()
                pidfile.touch()  # the heartbeat: the file's age is the time since the last finished step
                stop.wait(self.config.poll if every is None else every)
        finally:
            pidfile.unlink(missing_ok=True)
