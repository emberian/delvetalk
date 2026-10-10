"""Arrival: `world-arrive {principal, did, handle}` from the clock principal records the handle and
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
        # The deployed library is world/lib; a newcomer's packages (and Place, which Avatar imports) join it here.
        self.lib = tempfile.mkdtemp(prefix="dt-arrive-lib-")
        self.addCleanup(shutil.rmtree, self.lib, True)
        shutil.copytree(os.path.join(ROOT, "world", "lib"), self.lib, dirs_exist_ok=True)
        for name in ("Avatar", "Env", "Wake", "Place"):
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
