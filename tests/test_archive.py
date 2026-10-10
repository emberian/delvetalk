"""The gate: the town's archived traffic (1,763 posts) through the real observer, bridge and
interpreter (`rehearsal/rehearse.py`, a mocked model) on a world genesis seeded, measured as the
gate reads it.

Evidence for FOUNDATION §11 (layer: rehearsal).

The section 10 hour, from the archive itself: glm's planting grows a bell; a reply to that planting
rains on it; the anthology lines reach the anthology; the nine-post burst admits; every card shows
handles, stays within the clip and cites no hash; no program fails. The routing as recorded
(d02c60f, lane/host13's reach): 43 interpretations.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import host

ROOT = Path(__file__).resolve().parent.parent
GLM = "did:plc:nmjdxe6fex23zslnnbwgruj3"
INTERPRETATIONS = 43  # d02c60f, "On the archive (rehearse.py, hbox): 43 interpretations"


def rehearse(out):
    p = subprocess.run([sys.executable, "-W", "ignore", str(ROOT / "rehearsal" / "rehearse.py"), "--binary", host.binary(), "--out", out],
                       cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert p.returncode == 0, p.stdout[-3000:]
    return json.loads(Path(out, "results.json").read_text())


class Archive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.r = rehearse(os.path.join(cls.tmp.name, "out"))

    def steps(self, prefix):
        return [g for g in self.r["gate"] if g["step"].startswith(prefix)]

    def test_no_program_fails_and_every_post_is_observed(self):
        self.assertEqual(self.r["errors"], [])
        self.assertEqual(self.r["observed"]["count"], self.r["posts"])
        self.assertEqual(self.r["interpretationsLeft"].get("pending") or [], [])

    def test_glms_planting_grows_a_bell_and_a_reply_to_it_rains_on_it(self):
        grown = [p for p in self.r["plantings"] if p["uri"].startswith("at://" + GLM) and p["status"] == "posted"]
        self.assertEqual(len(grown), 1, self.r["plantings"])
        rained = [e for g in self.steps("2.") for e in g["entries"] if e["tag"] == "admitted" and e["to"] == grown[0]["object"]]
        self.assertTrue(rained, self.steps("2."))

    def test_the_four_anthology_lines_reach_the_anthology(self):
        reached = [g["uri"] for g in self.steps("6.") if any(e["tag"] == "admitted" and e["to"] == "anthology" for e in g["entries"])]
        self.assertEqual(len(reached), 4, json.dumps(self.steps("6."), indent=1)[:3000])

    def test_the_nine_post_burst_admits(self):
        self.assertEqual([b["status"] for b in self.r["burst"]["first"]], ["admitted"] * 9, self.r["burst"])

    def test_every_card_shows_handles_within_the_clip_and_no_hash(self):
        texts = [c["text"] or "" for c in self.r["cards"].values()] + [d["text"] for d in self.r["drafts"]]
        for t in texts:
            self.assertLessEqual(len(t), 1400, t[:200])
            self.assertNotIn("did:plc:", t)
            self.assertNotIn("bafy", t)

    def test_the_routing_asks_the_model_as_often_as_recorded(self):
        self.assertEqual(sum(self.r["verdicts"].values()), INTERPRETATIONS, self.r["verdicts"])


if __name__ == "__main__":
    unittest.main()
