"""The host-owned outbound channel: what the world says to whom, retained and readable under
the reader's authority, and the posts transport made for objects, so replies find their way back.

Each case is named by the defect that would make it fail.
"""
import json
import unittest

from tests.test_chain import field
from tests.test_reflection import PACKAGE, Reflection, source_seed
from tests.test_turn_world import label, nat, record

URI = "at://did:plc:world/town.delve.feed.post/3abc"
SLOT = {"principal": "did:plc:kim", "intent": "strike-1"}


class Posts(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("bell", PACKAGE, source_seed())

    def posted(self, uri=URI, principal="transport", **extra):
        return self.host.send(op="world-posted", principal=principal, uri=uri, cid="bafyreiabc", object="bell", **extra)

    def test_a_reply_to_a_recorded_post_finds_its_object_and_slot_and_a_stranger_post_is_unknown(self):
        r = self.posted(slot=SLOT)
        self.assertEqual(r["status"], "posted", r)
        self.assertEqual(r["height"], self.host.send(op="world-status")["height"])
        found = self.host.send(op="world-addressee", parent=URI)
        self.assertEqual(found, {"status": "addressee", "object": "bell", "slot": SLOT})
        plain = self.posted(uri=URI + "x")
        self.assertEqual(self.host.send(op="world-addressee", parent=URI + "x"), {"status": "addressee", "object": "bell"})
        self.assertEqual(plain["status"], "posted")
        self.assertEqual(self.host.send(op="world-addressee", parent="at://nobody/p/1"), {"status": "unknown"})

    def test_the_index_is_rebuilt_by_replay(self):
        self.posted(slot=SLOT)
        self.reopen()
        self.assertEqual(self.host.send(op="world-addressee", parent=URI)["slot"], SLOT)

    def test_a_retried_confirmation_is_the_same_entry_and_another_cid_is_refused(self):
        first = self.posted()
        again = self.posted()
        self.assertEqual(again["height"], first["height"])
        other = self.host.send(op="world-posted", principal="transport", uri=URI, cid="bafyreiother", object="bell")
        self.assertEqual(other.get("class"), "duplicateIdentity", other)

    def test_a_post_for_an_unknown_object_or_a_non_at_uri_is_a_request_error(self):
        self.assertEqual(self.host.send(op="world-posted", principal="transport", uri=URI, cid="c", object="ghost")["status"], "error")
        self.assertEqual(self.posted(uri="https://example.com")["status"], "error")


class Settings(Reflection):
    def test_a_named_clock_alone_moves_the_clock_and_confirms_posts(self):
        r = self.host.send(op="world-open", path=self.path, library=self.library(), principal="ember", clock="transport")
        self.assertEqual(r["status"], "opened", r)
        self.make("bell", PACKAGE, source_seed())
        self.assertEqual(self.host.send(op="world-advance", height=3)["status"], "error")
        self.assertEqual(self.host.send(op="world-advance", height=3, principal="mallory")["status"], "error")
        self.assertEqual(self.host.send(op="world-advance", height=3, principal="transport")["status"], "advanced")
        mallory = self.host.send(op="world-posted", principal="mallory", uri=URI, cid="c", object="bell")
        self.assertEqual(mallory["status"], "error")
        self.reopen()
        self.assertEqual(self.host.send(op="world-advance", height=4)["status"], "error")
        self.assertEqual(self.host.send(op="world-status")["clock"], 3)

    def test_post_quota_defaults_to_16_is_set_at_open_and_fixed_after(self):
        self.assertEqual(self.host.send(op="world-status")["postQuota"], 16)
        self.host.send(op="world-open", path=self.path, postQuota=4)
        self.assertEqual(self.host.send(op="world-status")["postQuota"], 4)
        self.reopen()
        self.assertEqual(self.host.send(op="world-status")["postQuota"], 4)
        differ = self.host.send(op="world-open", path=self.path, postQuota=5)
        self.assertEqual(differ["status"], "error")
        self.assertIn("settings differ", differ["message"])

    def library(self):
        from tests.test_reflection import LIBRARY
        return LIBRARY


if __name__ == "__main__":
    unittest.main()
