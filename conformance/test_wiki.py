import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("wiki", Path(__file__).resolve().parents[1] / "scripts/wiki.py")
wiki = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wiki)


def snapshot(text):
    return {"format": "delvetalk-wiki-observation-v1", "source": "https://agentwiki.elsyian.moe/p/example.md",
            "markdown": text, "observedSha256": wiki.digest(text)}


class WikiTest(unittest.TestCase):
    def setUp(self):
        self.text = "# Example\n\n## Doors\nA welcome\n\n## Sweeps\nNone waiting\n"
        self.before = snapshot(self.text)
        self.proposal = wiki.prepare(self.before, "Sweeps", "One waiting\n")

    def test_target_is_not_version(self):
        self.assertEqual(self.proposal["section"], "Sweeps")
        self.assertEqual(self.proposal["postDraft"], "edit: Example › Sweeps\nOne waiting\n")
        self.assertNotEqual(self.proposal["section"], self.proposal["observedSha256"])

    def test_same_read_is_not_commit_authority(self):
        self.assertEqual(wiki.check(self.proposal, self.before)["status"], "observed-unchanged")
        self.assertFalse(wiki.check(self.proposal, self.before)["canCommit"])

    def test_unrelated_change_stales_whole_read(self):
        changed = snapshot(self.text.replace("A welcome", "Two welcomes"))
        self.assertEqual(wiki.check(self.proposal, changed)["status"], "stale-observation")

    def test_same_target_new_revision_stale(self):
        changed = snapshot(self.text.replace("None waiting", "Already changed"))
        self.assertEqual(wiki.check(self.proposal, changed)["status"], "stale-observation")

    def test_corrupt_read_rejected(self):
        self.before["markdown"] += "changed"
        with self.assertRaises(ValueError): wiki.check(self.proposal, self.before)

    def test_duplicate_target_rejected(self):
        with self.assertRaises(ValueError): wiki.prepare(snapshot(self.text + "\n## Sweeps\nagain"), "Sweeps", "x")

    def test_missing_target_rejected(self):
        with self.assertRaises(ValueError): wiki.prepare(self.before, "Sweep", "x")

    def test_page_replacement_rejected(self):
        with self.assertRaises(ValueError): wiki.prepare(self.before, "Sweeps", "## Doors\ndestroyed")


if __name__ == "__main__": unittest.main()
