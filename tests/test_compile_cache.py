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


class ProcessCache(Reflection):
    def compiled(self):
        return self.host.send(op="world-status")["compiled"]

    def test_a_second_world_starts_with_what_the_first_compiled(self):
        self.open_library()
        self.make("probe", PROBE, record(count=nat(0), seen=label("")))
        self.assertEqual(self.turn("probe", "bump")["status"], "admitted")
        first = self.compiled()
        self.assertGreaterEqual((first["packages"], first["methods"]), (1, 1), first)
        other = self.path + ".other"
        self.addCleanup(lambda: os.path.exists(other) and os.remove(other))
        self.assertEqual(self.host.send(op="world-open", path=other, library=LIBRARY, principal="ember")["status"], "opened")
        self.assertEqual(self.compiled(), first)
        self.make("probe", PROBE, record(count=nat(0), seen=label("")))
        self.assertEqual(self.turn("probe", "bump")["status"], "admitted")
        self.assertEqual(self.compiled(), first)


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

    def test_off_unless_named(self):
        self.assertIsNone(self.host.send(op="world-status")["compileCache"])

    def test_a_second_process_reads_what_the_first_wrote(self):
        cache = tempfile.mkdtemp(dir=self.dir.name)
        self.process(cache)
        first = self.world("a.journal")
        self.assertEqual(first["hits"], 0, first)
        written = self.files(cache)
        self.assertTrue(any("/build-" in f for f in written) and any("/def-" in f for f in written), written)
        self.host.close()
        self.process(cache)
        second = self.world("b.journal")
        self.assertGreaterEqual(second["hits"], 2, second)
        self.assertEqual(self.files(cache), written)
        # Replaying the first journal in a third process compiles from the disk too.
        self.host.close()
        self.process(cache)
        self.assertEqual(self.host.send(op="world-open", path=os.path.join(self.dir.name, "a.journal"))["status"], "opened")
        self.assertGreaterEqual(self.host.send(op="world-status")["compileCache"]["hits"], 1)

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
