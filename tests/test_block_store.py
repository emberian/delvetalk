"""The journal as a block store: an open from a snapshot equals replay from height 0.

Evidence for HOST-HANDOFF §3 (layer: host). Every entry is a canonical record under its CID in
`<journal>.blocks`; the journal file is the chain of links; a snapshot carries every index `record`
derives, so an open reads it and replays only the entries after it, each read and checked against the
chain. Refuted by any read that answers otherwise after an open from a snapshot than after replay from
0 (`world-open {verify: true}` and an open with the snapshots removed), or by a snapshot `verify` refuses.
"""
import glob
import json
import os
import unittest

from transport.journal import entries as journal_entries
from tests.test_reflection import PACKAGE, PROBE, Reflection, probe_seed, source_seed
from tests.wire import label, record

# What a process says of itself rather than of the world.
PROCESS = ("compiled", "compileCache", "locked", "sync", "recompiledDifferently")


class BlockStore(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()

    def ask(self, identity):
        return self.host.send(op="world-turn", principal="ember", object="probe", method="ask", identity=identity,
                              argument=record(utterance=label("bump it"), policy=label("target")))

    def world(self):
        """Everything a reader can ask of the world's history and indexes."""
        send = lambda **r: self.host.send(**r)
        status = {k: v for k, v in send(op="world-status").items() if k not in PROCESS}
        heights = range(1, status["height"] + 1, 100)
        entries = [send(op="world-entries", principal="ember", after=h - 1, limit=100)["entries"] for h in heights]
        identities = [e["identity"]["intent"] for page in entries for e in page if e["identity"]["principal"] == "ember"]
        return {"status": status, "entries": entries,
                "receipts": [send(op="world-receipt", principal="ember", identity=i) for i in identities],
                "history": [send(op="world-history", principal="ember", object=o) for o in ("c", "probe", "target")],
                "pending": send(op="world-pending"),
                "interpretations": [p["id"] for p in send(op="world-interpretations")["pending"]],
                "offers": send(op="world-offers", principal="ember"),
                "sources": send(op="world-sources", principal="ember"),
                "states": [send(op="world-view", principal="ember", object=o) for o in ("c", "probe", "target")]}

    def test_an_open_from_a_snapshot_answers_as_replay_from_height_0(self):
        self.make("c", PACKAGE, source_seed())
        self.make("probe", PROBE, probe_seed())
        self.make("target", PROBE, probe_seed())
        for _ in range(3):
            self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(self.turn("probe", "fire", record(target=label("target")))["status"], "admitted")
        self.assertEqual(self.ask("wait-1")["status"], "suspended")
        snap = self.host.send(op="world-snapshot")["height"]
        # After it: more turns, a delivery, and the interpretation settled into its resumed turn.
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(self.turn("probe", "fire", record(target=label("target")))["status"], "admitted")
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"],
                                 reply={"status": "replied", "raw": "delvetalk probe bump2\nn: 3"})
        self.assertEqual(settled["resumed"][-1]["status"], "admitted", settled)  # after a re-run: probe moved
        self.assertEqual(self.ask("wait-2")["status"], "suspended")
        live = self.world()

        self.reopen()
        opened = self.host.send(op="world-open", path=self.path)
        self.assertEqual(opened["snapshot"], {"resumed": snap, "refused": []}, opened)
        self.assertEqual(self.world(), live)
        verified = self.host.send(op="world-open", path=self.path, verify=True)
        self.assertEqual(verified["snapshot"]["refused"], [], verified)
        self.assertEqual(self.world(), live)
        self.release()
        for f in glob.glob(self.path + ".snapshot.*.cbor"):
            os.remove(f)
        self.host = self.spawn()
        self.assertEqual(self.host.send(op="world-open", path=self.path)["snapshot"], {"resumed": 0, "refused": []})
        self.assertEqual(self.world(), live)

    def test_a_line_format_journal_is_refused_by_name(self):
        self.make("c", PACKAGE, source_seed())
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        entries = journal_entries(self.path)
        old = os.path.join(self.dir.name, "old.journal")
        with open(old, "w") as f:
            f.write("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries))
        refused = self.spawn().send(op="world-open", path=old)
        self.assertEqual(refused["status"], "error", refused)
        self.assertIn("old line format", refused["message"])


if __name__ == "__main__":
    unittest.main()
