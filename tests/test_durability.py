"""Each sync mode opens, writes and reopens a journal to the same head.

Evidence for FOUNDATION §2 Durability (layer: host).

`world-open {sync}`: "none" flushes, "fsync" (the default) asks the OS to write the bytes out,
"full" adds the drive-cache barrier (F_FULLFSYNC on macOS). Each mode opens, writes and reopens
to the same head; the boolean of the previous release still means none/fsync.
"""
import json
import os
import unittest

from tests.host import Host, HostCase
from tests.test_turn_world import counter_modules, nat, record


class Durability(HostCase):
    def run_mode(self, mode, bumps=3):
        path = os.path.join(self.dir.name, f"{mode}.journal")
        h = self.spawn()
        if mode is None:  # Host.send names "none" when a request names no mode; the default needs the raw line
            h.proc.stdin.write(json.dumps({"op": "world-open", "path": path}) + "\n")
            h.proc.stdin.flush()
            opened = json.loads(h.proc.stdout.readline())
        else:
            opened = h.send(op="world-open", path=path, sync=mode)
        self.assertEqual(opened["status"], "opened", opened)
        r = h.send(op="world-create", principal="ember", identity="mk", object="c1", modules=counter_modules(),
                   entry="initial", seed=record(count=nat(0)))
        self.assertEqual(r["status"], "created", r)
        for i in range(bumps):
            r = h.send(op="world-turn", principal="ember", object="c1", method="bump", argument=record(), identity=f"b{i}")
            self.assertEqual(r["status"], "admitted", r)
        status = h.send(op="world-status")
        h.close()
        again = self.spawn()
        self.assertEqual(again.send(op="world-open", path=path, sync="none")["status"], "opened")
        self.assertEqual(again.send(op="world-status")["head"], status["head"])
        return status["sync"]

    def test_each_mode_opens_writes_and_reopens_to_the_same_head(self):
        for mode, expect in [("none", "none"), ("fsync", "fsync"), ("full", "full"), (None, "fsync")]:
            self.assertEqual(self.run_mode(mode), expect)

    def test_the_boolean_still_means_none_or_fsync_and_anything_else_is_refused(self):
        h = self.spawn()
        for value, expect in [(False, "none"), (True, "fsync")]:
            path = os.path.join(self.dir.name, f"{expect}-bool.journal")
            self.assertEqual(h.send(op="world-open", path=path, sync=value)["status"], "opened")
            self.assertEqual(h.send(op="world-status")["sync"], expect)
        bad = h.send(op="world-open", path=os.path.join(self.dir.name, "bad.journal"), sync="barrier")
        self.assertEqual(bad["status"], "error", bad)
        self.assertIn("none", bad["message"])


if __name__ == "__main__":
    unittest.main()
