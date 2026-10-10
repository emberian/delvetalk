"""A directory suspension journals only what changed: nine prose replies stay under a bounded median
entry size.

Evidence for FOUNDATION §11, §12 (layer: rehearsal).

A directory suspension journals only what changed (rehearsal run 6, finding 5; HOST-HANDOFF 5.34):
nine prose replies under the hub each suspend on the model's reading. The program's own checkpoint
tokens and the offered forms are shared blocks, so a suspension after the first adds only what its
turn changed. Refuted by a median of 12 KB or more for one speaker, or of 32 KB or more when every
reply is a new speaker's first. Before host7 both medians were about 64 KB; v2 without the blocks
is about 48 KB.

    python3 -W error -m unittest tests.test_suspension_size -v
"""
import json
import os
import statistics
import unittest

from tests import test_hub

PROSE = [
    "Could we plant a silver fern that remembers yesterday?",
    "I keep thinking about the lighthouse and whether the bells can hear the tide coming in at night.",
    "short one",
    "What happens to refusals once they are written down? Does anyone read them again?",
    "The moths know the way, they said, and nobody argued.",
    "A long one this time: " + "the garden grows slowly when nobody is watching and faster when everyone is. " * 6,
    "Is the anthology still open for lines?",
    "hello again, just passing through the porch",
    "I would like a bell that rings only for the people who admit the ring.",
]
# The directory asks the model only of prose naming a door, a form action or a field
# (objects5, run 8 finding 1): each reply names the garden.
PROSE = [p + " (for the garden)" for p in PROSE]
WHO = ["did:plc:" + ("%024d" % i).replace("0", "a") for i in range(1, 10)]


class SuspensionSize(test_hub.Hub):
    def entries(self):
        with open(self.path) as handle:
            return [json.loads(line) for line in handle]

    def suspensions(self, speakers):
        self.policy()
        self.directory("policy")
        self.greet(*WHO)
        start = len(self.entries())
        for who, text in zip(speakers, PROSE):
            self.assertEqual(self.say(text, who)["status"], "suspended")
        sizes, fresh = [], []
        for e in self.entries()[start:]:
            if e["outcome"]["tag"] != "suspended":
                continue
            sizes.append(len(json.dumps(e, separators=(",", ":")).encode()))
            fresh.append([len(json.dumps(b, separators=(",", ":")).encode()) for b in e.get("blocks", [])])
        print("\n  suspension bytes:", sizes)
        print("  fresh blocks per entry (count, largest):", [(len(f), max(f, default=0)) for f in fresh])
        print("  median:", statistics.median(sizes[1:]))
        if os.environ.get("DT_SUSPENSION_DUMP"):
            with open(os.environ["DT_SUSPENSION_DUMP"] + str(len(set(speakers))), "w") as out:
                json.dump(self.entries()[start:], out)
        self.assertEqual(len(sizes), 9)
        return statistics.median(sizes[1:])

    def test_nine_prose_replies_from_one_speaker_journal_a_small_median_suspension(self):
        self.assertLess(self.suspensions([WHO[0]] * 9), 12 * 1024)

    def test_nine_speakers_suspensions_stay_bounded(self):
        # Each speaker sits at another place in the directory's greeted list, which the reading walks.
        self.assertLess(self.suspensions(WHO), 32 * 1024)


for _name in [n for n in dir(test_hub.Hub) if n.startswith("test_")]:
    setattr(SuspensionSize, _name, None)


if __name__ == "__main__":
    unittest.main()
