"""The compile caches are the process's (HOST-HANDOFF 5.59): every key is a content address (compile
inputs naming their library by pin and modules by CID), so a world opened after another in the same
process starts with what that one compiled, and creating the same package there compiles nothing.
With `DELVETALK_COMPILE_CACHE` they are also the disk's (5.66): another process reads the packages and
definitions one wrote, and a damaged file is compiled again.

Evidence for HOST-HANDOFF 5.59 and 5.66 (layer: host). Refuted by a second world that starts with empty
caches, by a creation in it that adds a package to them, by a second process that reads nothing the
first wrote, or by a damaged file being used.

    python3 -W error -m unittest tests.test_compile_cache -v
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from tests.host import Host

from tests.test_reflection import LIBRARY, PROBE, Reflection
from tests.test_turn_world import label, nat, record


class DiskCache(Reflection):
    def process(self, cache):
        with mock.patch.dict(os.environ, {"DELVETALK_COMPILE_CACHE": cache}):
            h = Host()
        self.hosts.append(h)
        self.host = h
        return h

    def files(self, cache):
        [stamp] = os.listdir(cache)
        return sorted(os.path.join(cache, stamp, f) for f in os.listdir(os.path.join(cache, stamp)))

    def world(self, name):
        path = os.path.join(self.dir.name, name)
        self.assertEqual(self.host.send(op="world-open", path=path, library=LIBRARY, principal="ember")["status"], "opened")
        self.make("probe", PROBE, record(count=nat(0), seen=label("")))
        self.assertEqual(self.turn("probe", "bump")["status"], "admitted")
        return self.host.send(op="world-status")["compileCache"]


    def test_a_damaged_file_is_compiled_again(self):
        cache = tempfile.mkdtemp(dir=self.dir.name)
        self.process(cache)
        self.world("a.journal")
        self.host.close()
        for f in self.files(cache):
            with open(f, encoding="utf-8") as h:
                entry = json.load(h)
            (entry["artifact"] if "artifact" in entry else entry)["packet"] = {"damaged": True}
            with open(f, "w", encoding="utf-8") as h:
                json.dump(entry, h)
        self.process(cache)
        again = self.world("b.journal")
        self.assertEqual(again["hits"], 0, again)


if __name__ == "__main__":
    unittest.main()
