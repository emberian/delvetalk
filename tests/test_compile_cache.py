"""The compile caches are the process's (HOST-HANDOFF 5.59): every key is a content address (compile
inputs naming their library by pin and modules by CID), so a world opened after another in the same
process starts with what that one compiled, and creating the same package there compiles nothing.

Evidence for HOST-HANDOFF 5.59 (layer: host). Refuted by a second world that starts with empty caches,
or by a creation in it that adds a package to them.

    python3 -W error -m unittest tests.test_compile_cache -v
"""
import os
import unittest

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


if __name__ == "__main__":
    unittest.main()
