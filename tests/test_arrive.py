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
from tests.test_turn_world import declared, label, nat, record

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

    def say(self, text, who=DID, identity="s1"):
        return self.host.send(op="world-turn", principal=who, object="me", method="receive", identity=identity,
                              argument=record(text=label(text), post=label("")))

    def test_me_is_the_speakers_own_avatar(self):
        # docs/GROUND.md §6 change 2: a card may print `delvetalk me note` without a DID.
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

    def test_an_arrival_creates_the_newcomers_three_objects_owned_by_the_did(self):
        before = self.host.send(op="world-status")["height"]
        r = self.arrive()
        self.assertEqual(r["status"], "arrived", r)
        self.assertEqual([c["object"] for c in r["created"]], [DID, "env/" + DID, "wake/" + DID])
        self.assertEqual(r["principal"]["outcome"]["handle"], "newt.delve.town")
        self.assertEqual(self.host.send(op="world-status")["height"], before + 5)   # the principal, three creates, the Wake's arrived turn
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
            "#13 mention from glm.delve.town: status: reply with\n"
            "#12 mention from glm.delve.town: @talkie.delve.town the cistern is dug\n"))
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
            "#31 mention from glm.delve.town: mention 19: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#30 mention from glm.delve.town: mention 18: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#29 mention from glm.delve.town: mention 17: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#28 mention from glm.delve.town: mention 16: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#27 mention from glm.delve.town: mention 15: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#26 mention from glm.delve.town: mention 14: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#25 mention from glm.delve.town: mention 13: a long thought about the town a long thought about the town a long thought about the to…\n"
            "#24 mention from glm.delve.town: mention 12: a long thought about the town a long thought about the town a long thought about the to…\n"
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


# A Wake whose `arrived` subscribes its owner's wake to the garden's `n` (the objects lane's
# `Wake.arrived` does the same for the real garden).
ARRIVING_WAKE = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  owner: String
  env: Plans.Reference
def initial() -> State:
  {owner: "", env: {world: "", object: ""}}
def arrived(state: State, input: {}, context: Abi.Context) -> Activity<Nat>:
  match world.subscribe({object: {world: "", object: "garden"}, field: "n", method: "changed"}):
    case subscribed(_): 1n
    case _: 0n
def changed(state: State, input: World.Changed, context: Abi.Context) -> Activity<Nat>:
  0n
""", "arrived", "changed")

GARDEN = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {n: add 1n}
  state.n + 1n
""", "bump")


class Arrived(HostCase):
    arrive = Arrive.arrive

    def setUp(self):
        super().setUp()
        self.lib = tempfile.mkdtemp(prefix="dt-arrive-lib-")
        self.addCleanup(shutil.rmtree, self.lib, True)
        shutil.copytree(os.path.join(ROOT, "world", "lib"), self.lib, dirs_exist_ok=True)
        for name in ("Avatar", "Env"):
            shutil.copy(os.path.join(OBJECTS, name + ".obend"), self.lib)
        with open(os.path.join(self.lib, "Wake.obend"), "w", encoding="utf-8") as f:
            f.write(ARRIVING_WAKE)
        r = self.host.send(op="world-open", path=self.path, library=self.lib, principal="ember", clock="transport", opener="ember")
        self.assertEqual(r["status"], "opened", r)
        r = self.host.send(op="world-create", principal="ember", identity="mk-garden", object="garden",
                           modules=[{"name": "Probe", "source": GARDEN}], entry="initial", seed=record())
        self.assertEqual(r["status"], "created", r)

    def test_the_wakes_arrived_runs_once_as_the_newcomers_turn(self):
        r = self.arrive()
        turned = r["arrivedTurn"]
        self.assertEqual((turned["status"], turned["result"]), ("admitted", nat(1)), turned)
        self.assertEqual(turned["receipt"]["identity"], {"principal": DID, "intent": "arrive-" + DID})
        bumped = self.host.send(op="world-turn", principal="ember", object="garden", method="bump", argument=record(), identity="b1")
        self.assertEqual([c["to"] for c in bumped["receipt"].get("changes", [])], ["wake/" + DID], bumped)
        again = self.arrive()
        self.assertNotIn("arrivedTurn", again)
        self.reopen()
        bumped = self.host.send(op="world-turn", principal="ember", object="garden", method="bump", argument=record(), identity="b2")
        self.assertEqual([c["to"] for c in bumped["receipt"].get("changes", [])], ["wake/" + DID], bumped)



class ToldWithoutPosting(HostCase):
    """OFFERING §4: the world moves when nobody posts. A newcomer's Wake, in the turn arrival
    runs as theirs (`Wake.arrived`), subscribes to every planting in the garden; a planting
    calls the planter's `Wake.watchBell`, so the planter hears when that bell rings. Each
    reaches the avatar's inbox as a note in the settle pass of the turn that wrote it."""

    arrive, view = Arrive.arrive, Arrive.view

    def setUp(self):
        super().setUp()
        self.lib = tempfile.mkdtemp(prefix="dt-arrive-lib-")
        self.addCleanup(shutil.rmtree, self.lib, True)
        shutil.copytree(os.path.join(ROOT, "world", "lib"), self.lib, dirs_exist_ok=True)
        for name in ("Avatar", "Env", "Wake"):
            shutil.copy(os.path.join(OBJECTS, name + ".obend"), self.lib)
        r = self.host.send(op="world-open", path=self.path, library=self.lib, principal="ember", clock="transport", opener="ember")
        self.assertEqual(r["status"], "opened", r)
        from tests.test_objects import closure
        r = self.host.send(op="world-create", principal="ember", identity="mk-garden", object="garden", modules=closure("Garden"),
                           entry="initial", seed=record(owner={"tag": "label", "value": "ember"}))
        self.assertEqual(r["status"], "created", r)

    def inbox(self, did=DID):
        from tests.test_replay import get, rows
        return [get(n, "text")["value"] for n in rows(get(self.view(did), "inbox"))]

    def plant(self, who, seed, ident):
        r = self.host.send(op="world-turn", principal=who, object="garden", method="receive", identity=ident,
                           argument=record(text={"tag": "label", "value": "delvetalk garden plant\nseed: %s\ncolour: silver" % seed}, post={"tag": "label", "value": "at://x/" + ident}))
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "planted"), r)
        return r

    def test_a_world_with_an_arrival_a_subscription_and_a_change_reopens_as_written(self):
        # The playtest (run 17:05, height 39): a planting both creates a bell and owes the Wake a
        # change; first execution counted the bell in the change's ledger, replay did not.
        self.arrive()
        self.plant("ember", "a lamp", "p1")
        self.plant(DID, "a fern", "p2")
        def cids():
            ids = self.host.send(op="world-objects", principal="ember")["ids"]
            return {i: self.host.send(op="world-state-cid", principal="ember", object=i).get("cid") for i in ids}
        before = (self.host.send(op="world-status")["height"], cids())
        self.assertIn("garden/bell/2", before[1])
        self.reopen()
        self.assertEqual((self.host.send(op="world-status")["height"], cids()), before)

    def test_a_newcomer_hears_each_planting_and_its_own_bell_ring(self):
        arrived = self.arrive()
        self.assertEqual((arrived["arrivedTurn"]["status"], arrived["arrivedTurn"]["result"]["label"]), ("admitted", "watching"), arrived)
        self.assertEqual(self.arrive().get("arrivedTurn"), None)
        self.plant("ember", "a lamp", "p1")
        self.assertEqual(self.inbox(), ["garden.planted is 1"])
        self.plant(DID, "a fern", "p2")
        self.assertEqual(self.inbox(), ["garden.planted is 1", "garden.planted is 2"])
        rung = self.host.send(op="world-turn", principal="ember", object="garden/bell/2", method="ring", argument=record(), identity="r1")
        self.assertEqual(rung["status"], "admitted", rung)
        self.assertEqual(self.inbox(), ["garden.planted is 1", "garden.planted is 2", "garden/bell/2.rung turned true"])
        # Ember has no wake: the planting stands, and nobody hears bell 1 ring.
        self.assertEqual(self.host.send(op="world-turn", principal="ember", object="garden/bell/1", method="ring", argument=record(), identity="r2")["status"], "admitted")
        self.assertEqual(len(self.inbox()), 3)


if __name__ == "__main__":
    unittest.main()
