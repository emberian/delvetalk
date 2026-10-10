"""The host's read ops for the AT repository façade (docs/REPO.md "Host ops"): one public reader name,
entries by hash and by page, an object as of a version, sources, grants and publications. Each case
names what would refute it.

    python3 -W error -m unittest tests.test_reads -v
"""
import json
import unittest

from tests.test_reflection import PACKAGE, Reflection, source_seed
from tests.test_turn_world import record

PUBLIC = ("anonymous", "")


class Reads(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.made = self.make("c", PACKAGE, source_seed())
        r = self.host.send(op="world-create", principal="ember", identity="mk-vault", object="vault", source=PACKAGE,
                           entry="initial", seed=source_seed(), read={"principals": ["ember"]})
        self.assertEqual(r["status"], "created", r)

    def test_anonymous_and_the_empty_string_are_the_public_reader_everywhere(self):
        for who in PUBLIC:
            self.assertEqual(self.host.send(op="world-objects", principal=who)["ids"], ["c"], who)
            self.assertEqual(self.host.send(op="world-inspect", principal=who, object="c")["status"], "inspected", who)
            self.assertEqual(self.host.send(op="world-view", principal=who, object="c")["status"], "viewed", who)
            self.assertEqual(self.host.send(op="world-view", principal=who, object="vault")["status"], "denied", who)
            self.assertEqual(self.host.send(op="world-history", principal=who, object="c")["status"], "history", who)

    def test_an_entry_by_hash_with_its_bytes_only_for_its_own_principal(self):
        from tests.wire import cid_of
        bumped = self.turn("c", "bump", principal="ann", identity="b1")["receipt"]
        mine = self.host.send(op="world-entry", principal="ann", hash=bumped["hash"], bytes=True)
        self.assertEqual((mine["status"], mine["receipt"]["hash"], mine["receipt"]["slug"]), ("receipt", bumped["hash"], bumped["slug"]))
        body = {k: v for k, v in bumped.items() if k not in ("hash", "slug")}
        canonical = self.host.send(op="canonical-encode", json=body)
        self.assertEqual(mine["bytes"], canonical["hex"])
        self.assertEqual(canonical["cid"], bumped["hash"])
        theirs = self.host.send(op="world-entry", principal="anonymous", hash=bumped["hash"], bytes=True)
        self.assertNotIn("bytes", theirs)
        self.assertIn("elided", theirs["receipt"])
        self.assertEqual(self.host.send(op="world-entry", principal="ann", hash="bafy-nothing")["status"], "unknown")

    def test_entries_page_forward_and_back_without_skipping_or_repeating(self):
        for i in range(5):
            self.turn("c", "bump", identity=f"p{i}")
        height = self.host.send(op="world-status")["height"]
        seen, after = [], 0
        while True:
            page = self.host.send(op="world-entries", principal="anonymous", after=after, limit=3)
            seen += [e["height"] for e in page["entries"]]
            if not page["more"]:
                break
            after = seen[-1]
        self.assertEqual(seen, list(range(1, height + 1)))
        back = self.host.send(op="world-entries", principal="anonymous", reverse=True, before=height, limit=2)
        self.assertEqual(([e["height"] for e in back["entries"]], back["more"]), ([height - 1, height - 2], True))


if __name__ == "__main__":
    unittest.main()
