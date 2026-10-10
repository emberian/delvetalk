"""The host's read ops behind the AT repository: one public reader, entries by hash and by page, an
object as of a version, sources under read authority.

Evidence for FOUNDATION §2 (layer: host).

The host's read ops for the AT repository façade (docs/REPO.md "Host ops"): one public reader name,
entries by hash and by page, an object as of a version, sources, grants and publications. Each case
names what would refute it.

    python3 -W error -m unittest tests.test_reads -v
"""
import unittest

from tests.test_reflection import PACKAGE, Reflection, source_seed

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


    def test_sources_by_cid_and_by_page_under_read_authority(self):
        from tests.wire import cid_of
        page = self.host.send(op="world-sources", principal="anonymous")
        self.assertEqual(page["status"], "sources", page)
        mine = [s for s in page["sources"] if s["text"] == PACKAGE]
        # The vault carries the same source; the counter makes it readable to the public.
        self.assertEqual(len(mine), 1, [s["name"] for s in page["sources"]])
        one = self.host.send(op="world-source", principal="anonymous", cid=mine[0]["cid"])
        self.assertEqual((one["status"], one["record"]["name"], one["record"]["height"]), ("source", "Main", mine[0]["height"]), one)
        self.assertEqual(one["record"]["cid"], cid_of(PACKAGE))
        heights = [s["height"] for s in page["sources"]]
        self.assertEqual(heights, sorted(heights))
        self.assertEqual(self.host.send(op="world-source", principal="anonymous", cid="bafy-none")["status"], "unknown")

    def test_pages_by_height_and_item_skip_nothing(self):
        # codex transport 12: one entry (the library's) carries many sources; paging by height alone
        # with limit 1 skipped the rest of that entry. The reply's `cursor` is (height, item).
        whole = self.host.send(op="world-sources", principal="anonymous")["sources"]
        self.assertGreater(len(whole), 2)
        for reverse in (False, True):
            seen, cursor = [], None
            while True:
                page = self.host.send(op="world-sources", principal="anonymous", limit=1,
                                      **({"cursor": cursor} if cursor else {}), **({"reverse": True} if reverse else {}))
                seen += [s["cid"] for s in page["sources"]]
                if not page["more"]:
                    break
                cursor = page["cursor"]
            self.assertEqual(seen, [s["cid"] for s in (reversed(whole) if reverse else whole)], reverse)


if __name__ == "__main__":
    unittest.main()
