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

    def test_an_object_as_of_a_version_with_its_pin_law_and_readings_then(self):
        self.turn("c", "bump")
        law = 'law owner "only ember": request.subject == "ember"'
        a = self.host.send(op="world-amend", principal="ember", identity="a1", object="c", version=1, law=law)
        self.assertEqual(a["status"], "admitted", a)
        now = self.host.send(op="world-object", principal="anonymous", object="c")["record"]
        self.assertEqual((now["version"], now["law"], now["readings"]), (2, law, [{"name": "owner", "reading": "only ember"}]), now)
        self.assertEqual(now["laws"], [{"object": "c", "version": 2, "pin": now["pin"], "name": "owner",
                                        "clause": 'request.subject == "ember"', "reading": "only ember"}])
        self.assertEqual(now["stateCid"], self.host.send(op="world-state-cid", principal="", object="c", version=2)["cid"])
        then = self.host.send(op="world-object", principal="anonymous", object="c", version=0)["record"]
        self.assertEqual((then["law"], then["readings"]), (self.made["receipt"]["outcome"].get("law", then["law"]), []))
        self.assertNotIn("only ember", then["law"])
        self.assertEqual(then["stateCid"], self.host.send(op="world-state-cid", principal="", object="c", version=0)["cid"])
        self.assertEqual(then["pinSlug"], now["pinSlug"])
        self.assertIn("library", then)
        self.assertEqual(self.host.send(op="world-object", principal="anonymous", object="vault")["status"], "denied")
        self.assertEqual(self.host.send(op="world-object", principal="anonymous", object="c", version=9)["status"], "unknown")

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

    def test_object_ids_are_record_keys(self):
        odd = self.host.send(op="world-create", principal="ember", identity="mk-odd", object="odd~one", source=PACKAGE,
                             entry="initial", seed=source_seed())
        self.assertEqual(odd["status"], "error", odd)
        self.assertIn("is not one: an object id is 1..128 bytes of letters, digits and . _ : / -", odd["message"])
        at = self.host.send(op="world-create", principal="ember", identity="mk-at", object="env/a@b", source=PACKAGE,
                            entry="initial", seed=source_seed())
        self.assertEqual(at["status"], "error", at)
        fine = self.host.send(op="world-create", principal="ember", identity="mk-env", object="env/did:plc:abc", source=PACKAGE,
                              entry="initial", seed=source_seed())
        self.assertEqual(fine["status"], "created", fine)


if __name__ == "__main__":
    unittest.main()
