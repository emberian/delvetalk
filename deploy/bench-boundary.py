#!/usr/bin/env python3
"""Per-op round trip across the transport boundary, in medians: world-status x1000 and Counter bumps x200 through
(a) serve's socket with a connection per op, (b) one persistent connection (transport.host.HostClient), (c) the raw pipe to a host process.

  DELVETALK_OBEND=/path/to/delvetalk-obend python3 deploy/bench-boundary.py
"""
import json
import socket
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deploy.seed import closure, modules_on_disk  # noqa: E402
from deploy.serve import Served  # noqa: E402
from transport.config import Config  # noqa: E402
from transport.host import HostClient, HostProcess  # noqa: E402

OWNER = 'bench'  # a resident, not the opener: the public socket takes its turns
EMPTY = {'tag': 'record', 'fields': []}


def modules_with_counter():  # Counter is a fixture, not a world object
    return {**modules_on_disk(), 'Counter': ROOT / 'tests' / 'fixtures' / 'objects' / 'Counter.obend'}


class PerOp:
    """The old HostClient: a socket per op."""
    def __init__(self, path): self.path = str(path)

    def send(self, req):
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(self.path)
            s.sendall((json.dumps(req) + '\n').encode())
            return json.loads(s.makefile('rb').readline())


def median_ms(send, make, n):
    times = []
    for i in range(n):
        req = make(i)
        t = time.perf_counter()
        reply = send(req)
        times.append(time.perf_counter() - t)
        assert reply.get('status') not in (None, 'error'), reply
    return statistics.median(times) * 1000


def main():
    with tempfile.TemporaryDirectory(prefix='dt-bench-') as tmp:
        d = Served(Path(tmp) / 'state')
        sock = d.sock
        made = PerOp(sock).send({'op': 'world-create', 'principal': OWNER, 'identity': 'mk', 'object': 'c', 'entry': 'initial',
                                 'modules': closure('Counter', modules_with_counter()), 'seed': EMPTY})
        assert made['status'] == 'created', made
        raw = HostProcess(Config.load().obend, Path(tmp) / 'raw.journal', clock='transport')
        assert raw.send({'op': 'world-create', 'principal': OWNER, 'identity': 'mk', 'object': 'c', 'entry': 'initial',
                         'modules': closure('Counter', modules_with_counter()), 'seed': EMPTY})['status'] == 'created'
        status = lambda i: {'op': 'world-status'}

        def bump(tag):
            return lambda i: {'op': 'world-turn', 'principal': OWNER, 'object': 'c', 'method': 'bump', 'argument': EMPTY, 'identity': f'{tag}-{i}'}
        rows = []
        for name, send, tag in (('(a) socket per op', PerOp(sock).send, 'a'), ('(b) persistent socket', HostClient(sock).send, 'b'),
                                ('(c) raw pipe', raw.send, 'c')):
            rows.append((name, median_ms(send, status, 1000), median_ms(send, bump(tag), 200)))
        d.stop()
        raw.close()
    print(f"{'':24}{'world-status x1000':>22}{'Counter bump x200':>22}")
    for name, s, b in rows:
        print(f'{name:24}{s:>19.3f} ms{b:>19.3f} ms')


if __name__ == '__main__':
    main()
