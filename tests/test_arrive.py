"""An arrival records a principal's handle and creates their Avatar, Env and Wake from the world's
library, owned by their DID, once.

Evidence for FOUNDATION §3 Context (layer: host).

Arrival: `world-arrive {principal, did, handle}` from the clock principal records the handle and
creates the newcomer's Avatar (`<did>`), Env (`env/<did>`) and Wake (`wake/<did>`) from the world's
library, owned by the DID, as ordinary creates by the world's opener. Each case names what would
refute it.

    python3 -W error -m unittest tests.test_arrive -v
"""
import os
import shutil
import tempfile
import unittest

from tests.host import HostCase, ROOT

DID = "did:plc:abcdefghijklmnopqrstuvwx"
OBJECTS = os.path.join(ROOT, "world", "objects")


def field(state, name):
    return {f["name"]: f["value"] for f in state["fields"]}[name]


class Arrive(HostCase):
    def setUp(self):
        super().setUp()
        # The deployed library is world/lib (Places, which the Avatar imports, is there); a newcomer's packages join it here.
        self.lib = tempfile.mkdtemp(prefix="dt-arrive-lib-")
        self.addCleanup(shutil.rmtree, self.lib, True)
        shutil.copytree(os.path.join(ROOT, "world", "lib"), self.lib, dirs_exist_ok=True)
        for name in ("Avatar", "Env", "Wake"):
            shutil.copy(os.path.join(OBJECTS, name + ".obend"), self.lib)
        r = self.host.send(op="world-open", path=self.path, library=self.lib, principal="ember", clock="transport", opener="ember")
        self.assertEqual(r["status"], "opened", r)

    def arrive(self, handle="newt.delve.town", principal="transport", did=DID):
        return self.host.send(op="world-arrive", principal=principal, did=did, handle=handle)

    def view(self, obj, who=DID):
        v = self.host.send(op="world-view", principal=who, object=obj)
        self.assertEqual(v["status"], "viewed", v)
        return v["state"]

    def test_an_arrival_creates_the_newcomers_three_objects_owned_by_the_did(self):
        before = self.host.send(op="world-status")["height"]
        r = self.arrive()
        self.assertEqual(r["status"], "arrived", r)
        self.assertEqual([c["object"] for c in r["created"]], [DID, "env/" + DID, "wake/" + DID])
        self.assertEqual(r["principal"]["outcome"]["handle"], "newt.delve.town")
        self.assertEqual(self.host.send(op="world-status")["height"], before + 4)
        self.assertEqual(field(self.view(DID), "handle")["value"], "newt.delve.town")
        self.assertEqual(field(self.view("env/" + DID), "owner")["value"], DID)
        wake = self.view("wake/" + DID)
        self.assertEqual(field(wake, "owner")["value"], DID)
        self.assertEqual(field(field(wake, "env"), "object")["value"], "env/" + DID)
        # Ordinary creates by the opener, for the owner; the default law names the DID.
        receipt = self.host.send(op="world-receipt", principal="ember", identity="arrive:env/" + DID)
        self.assertEqual((receipt["receipt"]["outcome"]["tag"], receipt["receipt"]["outcome"]["owner"]), ("created", DID), receipt)
        avatar = self.host.send(op="world-inspect", principal=DID, object=DID)
        self.assertIn(DID, avatar["law"])

    def test_env_and_wake_resolve_to_the_newcomers_own_after_arrival(self):
        missing = self.host.send(op="world-card", principal=DID, object="env")
        self.assertEqual(missing["status"], "unknown", missing)
        self.arrive()
        card = self.host.send(op="world-card", principal=DID, object="env")
        self.assertEqual((card["status"], card["object"]), ("card", "env/" + DID), card)

    def test_the_env_is_named_by_its_owners_handle_and_takes_a_mention_in(self):
        self.arrive(handle="talkie.delve.town")
        self.assertEqual(field(self.view("env/" + DID), "handle")["value"], "talkie.delve.town")
        stranger = self.host.send(op="world-card", principal="did:plc:someone", object="env/" + DID)
        self.assertEqual(stranger["text"], "ENV of talkie.delve.town: 0 new since #0.\n")
        self.assertTrue(stranger["text"].startswith("ENV of talkie.delve.town: 0 new"), stranger)
        self.assertNotIn("…", stranger["text"])
        other = "did:plc:zyxwvutsrqponmlkjihgfedc"
        self.arrive(handle="glm.delve.town", did=other)
        r = self.host.send(op="world-turn", principal=other, object="env/" + DID, method="mention", identity="mention-1",
                           argument={"tag": "record", "fields": [{"name": "text", "value": {"tag": "label", "value": "@talkie.delve.town the cistern is dug"}},
                                                                  {"name": "post", "value": {"tag": "label", "value": "at://glm/post/9"}}]})
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "done"), r)
        self.assertEqual(r.get("offers", []), [])
        # A post quoting a spell for another card is a mention all the same, and offers nothing: a
        # mention is the env's `mention`, which the host never reads as a spell (a `receive` it does).
        quoted = self.host.send(op="world-turn", principal=other, object="env/" + DID, method="mention", identity="mention-2",
                                argument={"tag": "record", "fields": [{"name": "text", "value": {"tag": "label", "value": "status: reply with\ndelvetalk garden plant / colour: silver / seed: a fern"}},
                                                                       {"name": "post", "value": {"tag": "label", "value": "at://glm/post/10"}}]})
        self.assertEqual((quoted["status"], quoted["result"]["label"], quoted.get("offers", [])), ("admitted", "done", []), quoted)
        mine = self.host.send(op="world-card", principal=DID, object="env/" + DID)["text"]
        self.assertEqual(mine, (
            "ENV of talkie.delve.town (yours): 2 new since #0. Reply delvetalk env observe to read them, delvetalk env seen / at: <number> to mark them read.\n"
            "#11 mention from glm.delve.town: status: reply with\n"
            "#10 mention from glm.delve.town: @talkie.delve.town the cistern is dug\n"))
        self.assertIn("mention from glm.delve.town: @talkie.delve.town the cistern is dug\n", mine)
        self.assertIn("mention from glm.delve.town: status: reply with", mine)

    def test_the_env_card_shows_the_newest_eight_in_one_line_each_within_1400(self):
        self.arrive(handle="mimo.delve.town")
        other = "did:plc:zyxwvutsrqponmlkjihgfedc"
        self.arrive(handle="glm.delve.town", did=other)
        for i in range(20):
            text = ("mention %02d: " % i) + "a long thought about the town " * 12 + "\nand a second line"
            r = self.host.send(op="world-turn", principal=other, object="env/" + DID, method="receive", identity="m%d" % i,
                               argument={"tag": "record", "fields": [{"name": "text", "value": {"tag": "label", "value": text}},
                                                                      {"name": "post", "value": {"tag": "label", "value": "at://glm/p/%d" % i}}]})
            self.assertEqual(r["status"], "admitted", r)
        card = self.host.send(op="world-card", principal=DID, object="env/" + DID)["text"]
        self.assertEqual(card, (
            "ENV of mimo.delve.town (yours): 20 new since #0. Reply delvetalk env observe to read them, delvetalk env seen / at: <number> to mark them read.\n"
            "#29 mention from glm.delve.town: mention 19: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#28 mention from glm.delve.town: mention 18: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#27 mention from glm.delve.town: mention 17: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#26 mention from glm.delve.town: mention 16: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#25 mention from glm.delve.town: mention 15: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#24 mention from glm.delve.town: mention 14: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#23 mention from glm.delve.town: mention 13: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#22 mention from glm.delve.town: mention 12: a long thought about the town a long thought about the town a long thought about the to…\n"
            "… and 12 more\n"))
        self.assertLessEqual(len(card), 1400)
        self.assertIn("mention 19:", card.split("\n")[1])
        self.assertNotIn("mention 11:", card)
        self.assertIn("… and 12 more\n", card)
        self.assertNotIn("a second line", card)

    def test_a_second_arrival_creates_nothing_and_a_new_handle_is_one_entry(self):
        self.arrive()
        height = self.host.send(op="world-status")["height"]
        again = self.arrive()
        self.assertEqual((again["status"], again["created"]), ("arrived", []), again)
        self.assertNotIn("principal", again)
        self.assertEqual(self.host.send(op="world-status")["height"], height)
        renamed = self.arrive(handle="newt2.delve.town")
        self.assertEqual(renamed["created"], [])
        self.assertEqual(self.host.send(op="world-status")["height"], height + 1)

    def test_only_the_clock_principal_reports_an_arrival(self):
        r = self.arrive(principal="ember")
        self.assertEqual(r["status"], "error", r)
        self.assertIn("clock principal", r["message"])
        self.assertEqual(self.host.send(op="world-view", principal=DID, object=DID)["status"], "unknown")

    def test_an_arrival_replays(self):
        self.arrive()
        self.reopen()
        self.host.send(op="world-open", path=self.path, library=self.lib)
        self.assertEqual(field(self.view(DID), "handle")["value"], "newt.delve.town")
        self.assertEqual(self.arrive()["created"], [])


if __name__ == "__main__":
    unittest.main()
