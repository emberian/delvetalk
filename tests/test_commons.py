"""The commons: a place graph whose gates admit anyone, a list of principals, or only a turn their
gate object calls.

Evidence for FOUNDATION §8 (layer: objects).

The commons (after main's protocols/commons): a place graph with directed paths, ways in, and
gates that say who may cross: anyone, the principals a gate lists, or only a turn the named gate
object calls. Every move is the turn's own principal's.

Refuted by: a principal crossing a members gate that does not list it, a direct move through an
object gate, a copy of the gate object letting anyone through, a stranger changing a gate, a
seventeenth presence, or a misconfigured graph admitting anyone.
"""
import unittest

from tests.test_replay import get, items
from tests.test_turn_world import TurnWorld, closure, label, record
from tests.test_turn_world import declared

OWNER, GLM, KIM = "did:plc:ember", "did:plc:glm", "did:plc:kimik3"


def lst(xs):
    return {"tag": "list", "items": list(xs)}


def variant(tag, **fields):
    return {"tag": "variant", "label": tag, "payload": record(**fields)}


def place(name, title):
    return record(name=label(name), title=label(title), description=label("about the " + name))


def path(a, b):
    return record(**{"from": label(a), "to": label(b)})


def gate(a, b, rule):
    return record(**{"from": label(a), "to": label(b), "rule": rule})


def seed(paths=None, presence=()):
    return record(owner=label(OWNER),
                  places=lst([place("porch", "Porch"), place("yard", "Yard"), place("vault", "Vault"), place("attic", "Attic")]),
                  paths=lst(paths if paths is not None else [path("porch", "yard"), path("yard", "porch"), path("yard", "vault"), path("yard", "attic")]),
                  entries=lst([label("porch")]),
                  gates=lst([gate("yard", "vault", variant("members", names=lst([label(GLM)]))),
                             gate("yard", "attic", variant("object", object=label("door-1")))]),
                  presence=lst(presence))


DOOR = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  crossings: Nat
record Edits:
  crossings: Plans.Edit<Nat, Nat>
def keep() -> Edits:
  {crossings: Plans.Edit.keep({})}
sum Done:
  moved: {from: String, to: String}
  refused: {clause: String, reading: String}
def initial() -> State:
  {crossings: 0n}
def cross(state: State, input: {to: String}, context: Abi.Context) -> Activity<String>:
  match world.call::<Done>({object: {world: "", object: "commons"}, method: "move", argument: Data.of::<{to: String}>({to: input.to})}):
    case returned(r): told(r.result)
    case refused(r): r.clause
    case _: "no answer"
def told(done: Done) -> String:
  match done:
    case moved(m): textConcat("moved to ", m.to)
    case refused(r): r.reading
""")


class Commons(TurnWorld):
    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal=OWNER, identity="mk-commons", object="commons", modules=closure("Commons"),
                           entry="initial", seed=seed())
        self.assertEqual(r["status"], "created", r)

    def act(self, method, who, **fields):
        r = self.turn("commons", method, record(**{k: label(v) for k, v in fields.items()}), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        res = r["result"]
        return res["label"] if res["label"] == "moved" else get(res["payload"], "reading")["value"]

    def where(self):
        state = self.host.send(op="world-view", principal=OWNER, object="commons")["state"]
        return {get(p, "who")["value"]: get(p, "at")["value"] for p in items(get(state, "presence"))}

    def door(self, name):
        r = self.host.send(op="world-create", principal=OWNER, identity="mk-" + name, object=name,
                           modules=closure("World") + [{"name": "Door", "source": DOOR}], entry="initial",
                           seed=record(crossings={"tag": "natural", "value": "0"}))
        self.assertEqual(r["status"], "created", r)

    def test_ways_in_paths_and_a_members_gate_decide_who_moves_where(self):
        self.assertEqual(self.act("enter", GLM, place="yard"), "yard is not a way in")
        for who in (GLM, KIM):
            self.assertEqual(self.act("enter", who, place="porch"), "moved")
            self.assertEqual(self.act("move", who, to="yard"), "moved")
        self.assertEqual(self.act("enter", GLM, place="porch"), "Already here, at yard")
        self.assertEqual(self.act("move", KIM, to="vault"), "Gated: the gate does not know you")
        self.assertEqual(self.act("move", GLM, to="vault"), "moved")
        self.assertEqual(self.act("move", GLM, to="porch"), "No path from vault to porch")
        self.assertEqual(self.where(), {GLM: "vault", KIM: "yard"})
        card = self.turn("commons", "receive", record(text=label(""), post=label("")), principal=KIM)["offers"][0]["text"]
        self.assertEqual(card, (
            "COMMONS: you are at Yard.\n"
            "about the yard\n"
            "Paths:\n"
            "  to porch\n"
            "  to vault (gated; you may not cross)\n"
            "  to attic (gated by door-1)\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk commons enter\n"
            "    place: <text, 1 to 64 characters>\n"
            "\n"
            "    delvetalk commons move\n"
            "    to: <text, 1 to 64 characters>\n"
            "\n"
            "    delvetalk commons leave\n"))
        self.assertTrue(card.startswith("COMMONS: you are at Yard.\nabout the yard\nPaths:\n  to porch\n  to vault (gated; you may not cross)\n"
                                        "  to attic (gated by door-1)\n"), card)
        outside = self.turn("commons", "receive", record(text=label(""), post=label("")), principal="did:plc:zero")["offers"][0]["text"]
        self.assertEqual(outside, (
            "COMMONS of ember: 4 places, 2 here. Ways in: porch\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk commons enter\n"
            "    place: <text, 1 to 64 characters>\n"
            "\n"
            "    delvetalk commons move\n"
            "    to: <text, 1 to 64 characters>\n"
            "\n"
            "    delvetalk commons leave\n"))
        self.assertTrue(outside.startswith("COMMONS of ember: 4 places, 2 here. Ways in: porch\n"), outside)

    def test_the_owner_lets_one_more_through_and_a_stranger_cannot(self):
        for who in (KIM,):
            self.act("enter", who, place="porch")
            self.act("move", who, to="yard")
        self.assertEqual(self.act("allow", KIM, **{"from": "yard", "to": "vault", "principal": KIM}),
                         "Only the owner changes a gate; that is ember")
        self.assertEqual(self.act("allow", OWNER, **{"from": "yard", "to": "vault", "principal": KIM}), "moved")
        self.assertEqual(self.act("move", KIM, to="vault"), "moved")
        self.assertEqual(self.act("allow", OWNER, **{"from": "yard", "to": "attic", "principal": KIM}), "Only a members gate lists who may cross.")
        forged = self.host.send(op="world-propose", principal=KIM, identity="forged", roots=[{"object": "commons", "version": 4}],
                                writes=[{"object": "commons", "edits": [record(gates=variant("keep"), presence=variant("keep"))]}])
        self.assertEqual((forged["status"], forged["receipt"]["outcome"]["class"], forged["receipt"]["outcome"].get("clause")),
                         ("refused", "lawRefused", "owner"), forged)

    def test_an_object_gate_admits_only_a_turn_its_object_calls(self):
        self.door("door-1")
        self.door("door-2")
        self.act("enter", KIM, place="porch")
        self.act("move", KIM, to="yard")
        self.assertEqual(self.act("move", KIM, to="attic"), "Gated: only door-1 lets you through")
        copy = self.turn("door-2", "cross", record(to=label("attic")), principal=KIM)
        self.assertEqual(copy["result"], label("Gated: only door-1 lets you through"), copy)
        through = self.turn("door-1", "cross", record(to=label("attic")), principal=KIM)
        self.assertEqual((through["status"], through["result"]), ("admitted", label("moved to attic")), through)
        self.assertEqual(self.where(), {KIM: "attic"})

    def test_sixteen_are_here_and_the_seventeenth_waits(self):
        for i in range(16):
            self.assertEqual(self.act("enter", "did:plc:p%d" % i, place="porch"), "moved")
        self.assertEqual(self.act("enter", "did:plc:p16", place="porch"), "Sixteen are here already.")
        self.assertEqual(self.act("leave", "did:plc:p3"), "moved")
        self.assertEqual(self.act("enter", "did:plc:p16", place="porch"), "moved")
        self.assertNotIn("did:plc:p3", self.where())
        self.assertEqual(len(self.where()), 16)

    def test_a_misconfigured_commons_admits_nobody(self):
        r = self.host.send(op="world-create", principal=OWNER, identity="mk-bad", object="bad", modules=closure("Commons"), entry="initial",
                           seed=seed(paths=[path("porch", "cellar")]))
        self.assertEqual(r["status"], "created", r)
        r = self.turn("bad", "enter", record(place=label("porch")), principal=GLM)
        self.assertEqual(get(r["result"]["payload"], "reading")["value"], "The commons is misconfigured: a path names a place that is not here")


if __name__ == "__main__":
    unittest.main()
