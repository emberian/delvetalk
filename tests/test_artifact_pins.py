"""Every entry of every world closure compiles to the artifact it compiled to before.

Pins and journals depend on the packet bytes, so a change to the compiler's internals must
leave every artifact identical. tests/fixtures/pins/artifacts.json holds, per module and
top-level def of world/lib and world/objects (compiled in the pure profile, as
tests.test_objects does), the reply status, the packetSha256 and a SHA-256 of the artifact
(or of the refusal message). Record it again only for an intended language change:

    DELVETALK_OBEND=... python3 -m tests.test_artifact_pins --record
"""
import hashlib
import json
import os
import sys
import unittest

from tests import host
from tests.test_objects import MODULES, closure, definitions, pure

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "pins", "artifacts.json")
SHARDS = 4


def digest(value):
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def outcome(process, name, entry):
    reply = process.send(op="compile", modules=pure(closure(name)), entry=entry)
    if reply.get("status") == "compiled":
        artifact = reply["artifact"]
        return {"status": "compiled", "packetSha256": artifact["packetSha256"], "artifact": digest(artifact)}
    return {"status": reply.get("status"), "message": digest(reply.get("message"))}


def shard(index):
    return [name for position, name in enumerate(sorted(MODULES)) if position % SHARDS == index]


def entries(name):
    return [entry for entry, generic, _ in definitions(name) if not generic]


def record():
    process = host.Host()
    table = {}
    for name in sorted(MODULES):
        table[name] = {entry: outcome(process, name, entry) for entry in entries(name)}
    process.close()
    with open(FIXTURE, "w") as handle:
        json.dump(table, handle, indent=1, sort_keys=True)
        handle.write("\n")


class Pins:
    index = 0

    def test_every_entry_compiles_to_its_recorded_artifact(self):
        with open(FIXTURE) as handle:
            expected = json.load(handle)
        process = host.Host()
        self.addCleanup(process.close)
        for name in shard(self.index):
            self.assertEqual(sorted(expected.get(name, {})), sorted(entries(name)), name)
            for entry in entries(name):
                with self.subTest(module=name, entry=entry):
                    self.assertEqual(outcome(process, name, entry), expected[name][entry])


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
