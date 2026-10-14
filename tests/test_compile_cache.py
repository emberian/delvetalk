"""With `DELVETALK_COMPILE_CACHE` the compile caches are also the disk's (HOST-HANDOFF §5.3 "Compile caches"):
every key is a content address, and a damaged file is compiled again, never used.

Evidence for HOST-HANDOFF §5.3 (layer: host). Refuted by a damaged file being used.

    python3 -W error -m unittest tests.test_compile_cache -v
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from tests.host import Host

from tests.test_reflection import LIBRARY, PROBE, Reflection
from tests.wire import label, nat, record


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
