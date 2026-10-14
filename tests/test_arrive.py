"""An arrival records a principal's handle and creates their Avatar from the world's library,
owned by their DID, once.

Evidence for FOUNDATION §3 Context (layer: host).

Arrival: `world-arrive {principal, did, handle}` from the clock principal records the handle and
creates the newcomer's Avatar (`<did>`) from the world's library, owned by the DID, as an ordinary
create by the world's opener. Each case names what would
refute it.

    python3 -W error -m unittest tests.test_arrive -v
"""
import os
import shutil
import tempfile
import unittest

from tests.host import HostCase, ROOT
from tests.wire import field, label, record

DID = "did:plc:abcdefghijklmnopqrstuvwx"
OBJECTS = os.path.join(ROOT, "world", "objects")


def opened(case):
    """Open the case's world on the deployed library (world/lib, which the Avatar
    imports) joined by the newcomer's package."""
    case.lib = tempfile.mkdtemp(prefix="dt-arrive-lib-")
    case.addCleanup(shutil.rmtree, case.lib, True)
    shutil.copytree(os.path.join(ROOT, "world", "lib"), case.lib, dirs_exist_ok=True)
    shutil.copy(os.path.join(OBJECTS, "Avatar.obend"), case.lib)
    r = case.host.send(op="world-open", path=case.path, library=case.lib, principal="ember", clock="transport", opener="ember")
    case.assertEqual(r["status"], "opened", r)


class Arrive(HostCase):
    def setUp(self):
        super().setUp()
        opened(self)

    def arrive(self, handle="newt.delve.town", principal="transport", did=DID):
        return self.host.send(op="world-arrive", principal=principal, did=did, handle=handle)

    def view(self, obj, who=DID):
        v = self.host.send(op="world-view", principal=who, object=obj)
        self.assertEqual(v["status"], "viewed", v)
        return v["state"]

    def say(self, text, who=DID, identity="s1"):
        return self.host.send(op="world-turn", principal=who, object="me", method="receive", identity=identity,
                              argument=record(text=label(text), post=label("")))

    def test_me_is_the_speakers_own_avatar(self):
        # docs/VOICE.md "The offering": a card may print `delvetalk me note` without a DID.
        self.assertEqual(self.arrive()["status"], "arrived")
        usage = self.say("delvetalk me ?", identity="u1")
        self.assertEqual(usage["status"], "usage", usage)
        self.assertIn("delvetalk me note", usage["text"])
        self.assertNotIn(DID, usage["text"])
        noted = self.say("delvetalk me note\ntext: a moth", identity="n1")
        self.assertEqual(noted["status"], "admitted", noted)
        self.assertEqual([w["object"] for w in noted["receipt"]["outcome"]["writes"]], [DID])
        stranger = "did:plc:zzzzzzzzzzzzzzzzzzzzzzzz"
        out = self.say("delvetalk me note\ntext: a moth", who=stranger, identity="n2")["receipt"]["outcome"]
        self.assertEqual((out["class"], out["clause"]), ("badSpell", "noAvatar"), out)
        self.assertIn("arriv", out["reason"])
        made = self.host.send(op="world-create", principal="ember", identity="mk-me", object="me",
                              source="edition ObjectiveBend 1\nrecord State:\n  n: Nat\ndef initial() -> State:\n  {n: 0n}\n",
                              entry="initial", seed=record())
        self.assertEqual(made["status"], "error", made)

    def test_an_arrival_creates_the_newcomers_avatar_owned_by_the_did(self):
        before = self.host.send(op="world-status")["height"]
        r = self.arrive()
        self.assertEqual(r["status"], "arrived", r)
        self.assertEqual([c["object"] for c in r["created"]], [DID])
        self.assertEqual(r["principal"]["outcome"]["handle"], "newt.delve.town")
        self.assertEqual(self.host.send(op="world-status")["height"], before + 2)   # the principal, the create
        self.assertEqual(field(self.view(DID), "handle")["value"], "newt.delve.town")
        # Ordinary creates by the opener, for the owner; the default law names the DID.
        receipt = self.host.send(op="world-receipt", principal="ember", identity="arrive:" + DID)
        self.assertEqual((receipt["receipt"]["outcome"]["tag"], receipt["receipt"]["outcome"]["owner"]), ("created", DID), receipt)
        avatar = self.host.send(op="world-inspect", principal=DID, object=DID)
        self.assertIn(DID, avatar["law"])
        card = self.host.send(op="world-card", principal=DID, object="me")  # me resolves to the speaker's own
        self.assertEqual((card["status"], card["object"]), ("card", DID), card)

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
        self.reopen()
        self.host.send(op="world-open", path=self.path, library=self.lib)
        self.assertEqual(field(self.view(DID), "handle")["value"], "newt.delve.town")  # the avatar keeps its seed; the registry holds the new handle
        self.assertEqual(self.arrive()["created"], [])

    def test_only_the_clock_principal_reports_an_arrival(self):
        r = self.arrive(principal="ember")
        self.assertEqual(r["status"], "error", r)
        self.assertIn("clock principal", r["message"])
        self.assertEqual(self.host.send(op="world-view", principal=DID, object=DID)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
