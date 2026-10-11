"""`delvetalk-obend root-edit` (docs/ROOT.md §1.5; HOST-HANDOFF §7 item 1, 5.135): the offline edits of a
closed journal, each a new file, the old kept, the first re-sealed entry marked `rootEdit {command, reason,
oldHead, at}`, every re-sealed entry's hash in the printed table, and the result replayed before it is
written.

Evidence for root (layer: host). The world under edit has what re-sealing must carry: a supervised
activity's `ended` delivery (its id hashes the height, and the delivered turn's intent is that id), a
suspension and its resumption (`resumes` names the suspension's hash), and turns whose `turn` is their
height. Refuted by an edited journal that does not open with `verify`, a marker that does not name the old
head, a table that misses a re-sealed entry, an edit that breaks replay written anyway, an open journal
edited, or a deleted world left in place.

    python3 -W error -m unittest tests.test_root_edit -v
"""
import json
import os
import subprocess
import unittest

from transport.journal import entries as journal_entries
from tests.host import binary
from tests.test_chain import field
from tests.test_reflection import Reflection
from tests.test_supervisors import SUPERVISOR, WORKER
from tests.test_turn_world import label, nat, record


def lines(path):
    return journal_entries(path)


class RootEdit(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("boss", SUPERVISOR, record(count=nat(0), how=label(""), **{"class": label("")}, who=label("")))
        self.make("w", WORKER, record(count=nat(0)), supervisor="boss")
        self.make("free", WORKER, record(count=nat(0)))

    def boss(self):
        s = self.state("boss")
        return tuple(field(s, k)["value"] for k in ("count", "how", "class", "who"))

    def edit(self, *argv, out=None, journal=None):
        out = out or os.path.join(self.dir.name, "edited-%d.journal" % len(os.listdir(self.dir.name)))
        p = subprocess.run([binary(), "root-edit", "--journal", journal or self.path, "--out", out, "--reason", "test edit", *argv],
                           capture_output=True, text=True, timeout=600)
        return p, out

    def world(self):
        """A world with an early bump of `free`, an `ended` delivery, a suspension resumed, and a later bump."""
        self.assertEqual(self.turn("free", "bump")["status"], "admitted")
        self.free = self.host.send(op="world-status")["height"]
        self.assertEqual(self.turn("w", "deep")["status"], "refused")
        self.assertEqual(self.turn("w", "wait")["status"], "suspended")
        self.assertEqual(len(self.host.send(op="world-advance", principal="ember", height=5)["resumed"]), 1)
        self.assertEqual(self.turn("w", "bump")["status"], "admitted")
        self.boss_before = self.boss()
        self.release()
        self.entries = lines(self.path)

    def opened(self, path):
        self.host = self.spawn()
        r = self.host.send(op="world-open", path=path, verify=True)
        self.assertEqual(r["status"], "opened", r)
        return r

    def test_drop_rechains_ended_ids_delivered_intents_resumes_and_turns(self):
        self.world()
        p, out = self.edit("drop", "--height", str(self.free))
        self.assertEqual(p.returncode, 0, p.stderr)
        printed = json.loads(p.stdout)
        new = lines(out)
        self.assertEqual(len(new), len(self.entries) - 1)
        self.assertEqual(new[:self.free - 1], self.entries[:self.free - 1])            # the prefix untouched
        self.assertEqual(lines(self.path), self.entries)                                # the old kept
        marker = new[self.free - 1]["rootEdit"]
        self.assertEqual(marker, {"command": {"command": "drop", "height": self.free}, "reason": "test edit",
                                  "oldHead": self.entries[-1]["hash"], "at": self.free})
        self.assertEqual(printed["slugsChanged"], len(self.entries) - self.free)
        self.assertEqual([(t["oldHeight"], t["height"]) for t in printed["table"]],
                         [(h, h - 1) for h in range(self.free + 1, len(self.entries) + 1)])
        self.assertEqual((printed["oldHead"], printed["newHead"]), (self.entries[-1]["hash"], new[-1]["hash"]))
        # What re-sealing carried: an ended id under its new height, the delivered turn's intent with it, resumes, turns.
        endeds = [e for e in new if "ended" in e]
        self.assertEqual(len(endeds), 2)                                               # deep broke; wait timed out
        for ended in endeds:
            [told] = [e for e in new if e.get("delivery", {}).get("id") == ended["ended"]["id"]]
            self.assertEqual(told["identity"]["intent"], ended["ended"]["id"])
            self.assertNotIn(ended["ended"]["id"], {e.get("ended", {}).get("id") for e in self.entries})  # a new height, a new id
        [resumed] = [e for e in new if "resumes" in e]
        self.assertIn(resumed["resumes"], {e["hash"] for e in new})
        self.assertTrue(all(e["turn"] in (0, e["height"]) for e in new if "turn" in e and e["outcome"].get("tag") == "admitted"))
        self.opened(out)
        self.assertEqual(self.boss(), self.boss_before)
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="free")["state"]["fields"][0]["value"]["value"], "0")

    def test_splice_puts_back_what_drop_took_and_truncate_keeps_a_prefix(self):
        self.world()
        _, dropped = self.edit("drop", "--height", str(self.free))
        taken = os.path.join(self.dir.name, "taken.json")
        with open(taken, "w") as f:
            json.dump(self.entries[self.free - 1], f)
        p, back = self.edit("splice", "--at", str(self.free - 1), "--entries", taken, journal=dropped)
        self.assertEqual(p.returncode, 0, p.stderr)
        again = lines(back)
        # The same chain but for the marker in the spliced entry and every hash after it.
        strip = lambda e: {k: v for k, v in e.items() if k not in ("hash", "previous", "rootEdit")}
        self.assertEqual(strip(again[self.free - 1]), strip(self.entries[self.free - 1]))
        self.assertEqual(again[self.free - 1]["rootEdit"]["oldHead"], lines(dropped)[-1]["hash"])
        self.assertEqual(len(again), len(self.entries))
        self.opened(back)
        self.assertEqual(self.boss(), self.boss_before)
        self.release()
        p, cut = self.edit("truncate", "--height", str(self.free))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(lines(cut), self.entries[:self.free])
        self.assertEqual(self.opened(cut)["height"], self.free)

    def test_rewrite_replaces_one_body_and_an_edit_that_breaks_replay_writes_nothing(self):
        self.world()
        body = dict(self.entries[self.free - 1], note="the hand rewrote this")
        entry = os.path.join(self.dir.name, "entry.json")
        with open(entry, "w") as f:
            json.dump(body, f)
        p, out = self.edit("rewrite", "--height", str(self.free), "--entry", entry)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(lines(out)[self.free - 1]["note"], "the hand rewrote this")
        self.opened(out)
        self.release()
        # Dropping the creation of `w` leaves later turns naming nothing: refused, no file.
        [made] = [e["height"] for e in self.entries if e["outcome"].get("tag") == "created" and e["outcome"].get("object") == "w"]
        p, out = self.edit("drop", "--height", str(made))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("does not replay", p.stderr)
        self.assertFalse(os.path.exists(out))

    def test_an_open_journal_is_not_edited(self):
        self.turn("free", "bump")
        p, out = self.edit("truncate", "--height", "1")
        self.assertEqual(p.returncode, 75, p.stderr)
        self.assertFalse(os.path.exists(out))

    def test_delete_world_moves_the_journal_and_its_snapshots_aside_with_the_reason(self):
        self.turn("free", "bump")
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.release()
        state = self.dir.name
        os.rename(self.path, os.path.join(state, "ring.journal"))
        os.rename(self.path + ".blocks", os.path.join(state, "ring.journal.blocks"))
        for name in os.listdir(state):
            if name.startswith("world.journal.snapshot."):
                os.rename(os.path.join(state, name), os.path.join(state, name.replace("world.journal", "ring.journal")))
        p = subprocess.run([binary(), "root-edit", "--state", state, "--reason", "a scratch world", "delete-world", "--name", "ring"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        note = json.loads(p.stdout)
        self.assertEqual((note["status"], note["reason"]), ("deleted", "a scratch world"))
        self.assertFalse(os.path.exists(os.path.join(state, "ring.journal")))
        self.assertEqual(sorted(n.split(".", 1)[1] for n in os.listdir(os.path.join(state, "deleted"))),
                         sorted(["journal", "json"] + [m.split("ring-", 1)[1].split(".", 1)[1] for m in note["moved"][1:]]))
        self.assertFalse([n for n in os.listdir(state) if n.startswith("ring.journal")])


if __name__ == "__main__":
    unittest.main()
