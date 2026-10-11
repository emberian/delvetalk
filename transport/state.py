"""The transport's files (docs/OPERATIONS.md section b): every path under `<state>/` is named here once, and no other
module joins one. `<state>/` is serve's directory too (its journals, lock, library, scratch/ worlds and sockets); what the
transport keeps is either shared by every world (the claims, the access log, the hand's log, the model's spend, the
bridge rows) or a world's own, under `worlds/<world>/`, the town's like any other's."""
import json
import os
import re
import signal
import threading
from pathlib import Path

from transport.config import Config
from transport.delve import canonical
from transport.host import HostClient

NAME = re.compile(r'[a-z][a-z0-9-]{0,31}\Z')
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
        self.spend, self.row = r / 'model-spend.jsonl', r / 'bridges' / f'{world}.json'
        self.repo_key = Path(c.repo_keys) / f'{world}.key'
        # this world's
        self.home = h = r / 'worlds' / world
        self.observed, self.since = h / 'observe.sqlite', h / 'since'  # the observer's posts; where its observing began
        self.outbox, self.awaiting = h / 'outbox', h / 'awaiting'  # drafts; turns waiting on an interpretation
        self.principals, self.mentioned, self.skipped = h / 'principals.txt', h / 'mentioned.txt', h / 'skipped.txt'
        self.publications = h / 'publications.after'  # the cursor of what objects published
        self.posting, self.interpretations = h / 'posting', h / 'interpretations'  # the posting ledger; model replies by request
        self.watch_log, self.alerted = h / 'watch.jsonl', h / 'alerted.json'

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
        tmp = path.with_suffix('.tmp')
        with open(tmp, 'w') as f:
            f.write(canonical(value) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    @staticmethod
    def words(path):
        return set(path.read_text().split()) if path.exists() else set()

    @staticmethod
    def append(path, line):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(path, 'a') as f:
            f.write(line + '\n')

    def drafts(self):
        """[(path, draft)] of the outbox, oldest first."""
        return [(p, json.loads(p.read_text())) for p in sorted(self.outbox.glob('*.json'), key=lambda p: int(p.name.split('-')[0]))]

    def unposted(self):
        return [(p, d) for p, d in self.drafts() if not d['posted'] and not d.get('skipped')]

    def mark_posted(self, path):
        self.write(path, dict(json.loads(Path(path).read_text()), posted=True))

    def bridge(self):
        """The world's bridge row (`open`); a world without one is observed on delve.town."""
        return json.loads(self.row.read_text()) if self.row.exists() else {'world': self.world, 'transport': 'delve'}

    def pidfile(self, name):
        return self.home / f'{name}.pid'

    def daemon(self, name, step, stop=None):
        """step() every `poll` seconds under a pid file; SIGTERM/SIGINT finish the current step and exit."""
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
                stop.wait(self.config.poll)
        finally:
            pidfile.unlink(missing_ok=True)
