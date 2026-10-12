"""A town copied from the run's genesis template is the town a fresh genesis makes (tests/town.py): the same journal
bytes, and, opened by replay, every object's state CID at every version, the height, head and clock, what waits
(pending, interpretations, renders) and the status. Refuted by any test that passes on a copy and would fail on a
fresh genesis (layer: host).

    python3 -W error -m unittest tests.test_town_template -v
"""
import os
import tempfile
import unittest
from pathlib import Path

from tests.town import Town
from tests.test_properties import OPENER

PROCESS = ("compiled", "compileCache", "locked", "sync", "recompiledDifferently", "snapshot")


def world(town):
    send = town.send
    out = {}
    for obj in send(op="world-objects", principal=OPENER)["ids"]:
        v = send(op="world-view", principal=OPENER, object=obj)
        out[obj] = [send(op="world-state-cid", principal=OPENER, object=obj, version=n).get("cid") for n in range(v["version"] + 1)] \
            if v.get("status") == "viewed" else v.get("status")
    return {"objects": out,
            "status": {k: v for k, v in send(op="world-status").items() if k not in PROCESS},
            "pending": send(op="world-pending"),
            "interpretations": send(op="world-interpretations"),
            "renders": send(op="world-renders"),
            "card": send(op="world-card", principal=OPENER, object="commonplace")}


class Template(unittest.TestCase):
    def test_a_copied_town_is_a_fresh_genesis(self):
        for furnished in (True, False):
            with self.subTest(furnished=furnished):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                fresh = Town(os.path.join(tmp.name, "fresh"), cleanup=self.addCleanup, furnished=furnished, fresh=True)
                copy = Town(os.path.join(tmp.name, "copy"), cleanup=self.addCleanup, furnished=furnished)
                for suffix in ("", ".blocks"):
                    self.assertEqual(Path(copy.journal + suffix).read_bytes(), Path(fresh.journal + suffix).read_bytes(), suffix)
                self.assertEqual(copy.made, fresh.made)
                self.assertEqual(world(copy), world(fresh))


if __name__ == "__main__":
    unittest.main()
