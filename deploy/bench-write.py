#!/usr/bin/env python3
"""A one-row write against the size of the relation it lands in: per-turn round trip (median, best) and ticks of
`upsert` replacing one row of a relation of ROWS rows, through the raw pipe to one host process. A write pays for
the cells it changes (KERNEL-HANDOFF §15): the times at 16 and 2,048 rows should be close.

  DELVETALK_OBEND=/path/to/delvetalk-obend python3 deploy/bench-write.py [TURNS] [ROWS ...]
"""
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.host import Host  # noqa: E402
from tests.test_reflection import LIBRARY  # noqa: E402
from tests.test_relation import PACKAGE, rain, relation  # noqa: E402
from tests.wire import record  # noqa: E402


def bench(rows, turns):
    host = Host()
    try:
        with tempfile.TemporaryDirectory() as scratch:
            path = os.path.join(scratch, "world.journal")
            assert host.send(op="world-open", path=path, library=LIBRARY, principal="ember")["status"] == "opened"
            seed = record(rains=relation(*[rain("r", i, "t%d" % i) for i in range(rows)]))
            made = host.send(op="world-create", principal="ember", identity="mk", object="b",
                             source=PACKAGE.replace("LIMIT", "4096n"), entry="initial", seed=seed)
            assert made["status"] == "created", made
            times, ticks = [], set()
            for n in range(turns):
                start = time.perf_counter()
                r = host.send(op="world-turn", principal="ann", object="b", method="upsert",
                              argument=rain("r", rows // 2, "w%d" % n), identity="w%d" % n)
                times.append(time.perf_counter() - start)
                assert r["status"] == "admitted", r
                ticks.add(r["ticksUsed"])
            return statistics.median(times) * 1e3, min(times) * 1e3, sorted(ticks)
    finally:
        host.close()


def main():
    turns = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    for rows in [int(a) for a in sys.argv[2:]] or [16, 2048]:
        median, best, ticks = bench(rows, turns)
        print(f"{rows:>6} rows  {turns} turns  median {median:8.2f} ms  best {best:8.2f} ms  ticks {ticks}")


if __name__ == "__main__":
    main()
