"""Every entry of every world closure keeps its source pin and still compiles.

An object's pin is the CID of its source closure (the artifact's `sourcesSha256`); the
compiled packet is an observation beside it (`compiled {binary, packet}`), which replay
counts but never compares. tests/fixtures/pins/artifacts.json holds, per module of
world/lib and world/objects (compiled in the pure profile, as tests.test_objects does),
the closure's source pin and, per top-level def, the reply status and the packet's
digest. The test fails when a module's source pin changes or an entry that compiled
stops compiling; a packet that recompiles differently is counted and printed, not failed
(a compiler change may move packets; it must not move pins or break entries).

The source pin is a function of the world sources alone, so the fixture changes only when
world/ changes. To re-record after a world change, from any binary (the packet digests
are informational):

    DELVETALK_OBEND=... python3 -m tests.test_artifact_pins --record
"""
import json
import os
import sys
import unittest

from tests import host
from tests.test_objects import MODULES, closure, definitions, pure

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "pins", "artifacts.json")
SHARDS = 4


def outcome(process, name, entry):
    reply = process.send(op="compile", modules=pure(closure(name)), entry=entry)
    if reply.get("status") == "compiled":
        artifact = reply["artifact"]
        return {"status": "compiled", "pin": artifact["sourcesSha256"], "packet": artifact["packetSha256"]}
    return {"status": reply.get("status")}


def module_record(process, name):
    """The module's source pin (from any entry that compiles) and each entry's outcome."""
    results = {entry: outcome(process, name, entry) for entry in entries(name)}
    pins = {r["pin"] for r in results.values() if "pin" in r}
    assert len(pins) <= 1, (name, pins)
    return {"pin": next(iter(pins), None),
            "entries": {entry: {k: v for k, v in r.items() if k != "pin"} for entry, r in results.items()}}


def shard(index):
    return [name for position, name in enumerate(sorted(MODULES)) if position % SHARDS == index]


def entries(name):
    return [entry for entry, generic, _ in definitions(name) if not generic]


def record():
    process = host.Host()
    table = {name: module_record(process, name) for name in sorted(MODULES)}
    process.close()
    with open(FIXTURE, "w") as handle:
        json.dump(table, handle, indent=1, sort_keys=True)
        handle.write("\n")


class Pins:
    index = 0

    def test_every_entry_keeps_its_source_pin_and_compiles(self):
        with open(FIXTURE) as handle:
            expected = json.load(handle)
        process = host.Host()
        self.addCleanup(process.close)
        recompiled = 0
        for name in shard(self.index):
            want = expected.get(name, {"pin": None, "entries": {}})
            self.assertEqual(sorted(want["entries"]), sorted(entries(name)), name)
            for entry in entries(name):
                got = outcome(process, name, entry)
                was = want["entries"][entry]
                with self.subTest(module=name, entry=entry):
                    if was["status"] == "compiled":
                        self.assertEqual(got["status"], "compiled", f"{name}.{entry} stopped compiling")
                    if got["status"] == "compiled":
                        self.assertEqual(got["pin"], want["pin"], f"{name}: source pin changed")
                        if was["status"] == "compiled" and got["packet"] != was["packet"]:
                            recompiled += 1
        print(f"\n{type(self).__name__}: {recompiled} entries recompiled to a different packet", file=sys.stderr)


class PinsA(Pins, unittest.TestCase):
    index = 0


class PinsB(Pins, unittest.TestCase):
    index = 1


class PinsC(Pins, unittest.TestCase):
    index = 2


class PinsD(Pins, unittest.TestCase):
    index = 3


if __name__ == "__main__":
    if sys.argv[1:] == ["--record"]:
        record()
    else:
        unittest.main()
