"""A journal names the replay edition it was written under, and a host of another edition refuses it by
name before replaying (HOST-HANDOFF §6, "Replay edition").

Evidence (layer: host). Refuted by a journal without the field reopening, an edition-1 journal failing
somewhere inside replay instead of at its head, or `world-status` not naming the edition.

    python3 -W error -m unittest tests.test_replay_edition -v
"""
import json
import unittest

from tests.host import HostCase
from tests.test_turn_world import counter_modules, nat, record
from tests.wire import cid_of


class ReplayEdition(HostCase):
    def test_the_first_entry_names_the_edition_and_another_is_refused_by_name(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk", object="c",
                           modules=counter_modules(), entry="initial", seed=record(count=nat(0)))
        self.assertEqual(r["status"], "created", r)
        edition = self.host.send(op="world-status")["replay"]
        self.assertEqual(edition, 2)
        with open(self.path) as f:
            [first] = [json.loads(line) for line in f]
        self.assertEqual(first["replay"], edition)
        # An edition-1 journal: the field absent, the hash made again so the chain itself is sound.
        del first["replay"], first["hash"]
        first["hash"] = cid_of(first)
        with open(self.path, "w") as f:
            f.write(json.dumps(first, separators=(",", ":")) + "\n")
        self.release()
        self.host = self.spawn()
        opened = self.host.send(op="world-open", path=self.path)
        self.assertEqual(opened["status"], "error", opened)
        self.assertIn("journal replay edition 1; this host is 2", opened["message"])
        self.assertIn("new genesis", opened["message"])


if __name__ == "__main__":
    unittest.main()
