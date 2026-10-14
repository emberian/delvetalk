"""Rules ring a bell that opens a door that lights a lantern, delivered in the settling pass.

Evidence for FOUNDATION §3 Delivery (layer: host).

The message chain: bell rings, door opens, lantern lights.

This drives the host's `send` machinery: `world-turn` answers a send with a
delivery id, and the settling pass after every durable op runs pending deliveries
(up to 64 per op; the reply carries them as `delivered`). `world-deliver {limit}`
runs any that remain; `world-pending` lists them. The chain is wired with rules
(HOST-HANDOFF §5 "Rules, wants and verbs"): a rule on the bell knocks on the door, one on the door lights the lantern, each
fired delivery a turn of the rule's owner whose `context.sender` is the rule's object.
"""
import unittest

from tests.test_turn_world import TurnWorld
from tests.wire import boolean, field, label, record
from tests.bend import closure, declared

# Writes down who ran its `note` and which object's send delivered it.
WITNESS = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
import ./Form.obend as Form
import ./Card.obend as Card
import ./Document.obend as Document
record State:
  by: String
  sender: String
def initial() -> State:
  {by: "", sender: ""}
def note(state: State, context: Abi.Context) -> Activity<Bool>:
  noted(context.principal, context.sender)
def noted(who: String, origin: String) -> Activity<Bool>:
  let written(_) = write {by: set who, sender: set origin}
  true
form note:
def receive(state: State, input: Card.Reply, context: Abi.Context) -> Activity<Card.Replied>:
  Card.answer(input, context, forms(), Document.text("A witness."))
""")


def silver():
    return {"tag": "variant", "label": "silver", "payload": record()}


def bell_seed():
    """A Bell fixture's Seed (tests/fixtures/objects/Bell.obend): the planting post and its planter."""
    return record(colour=silver(), seed=label("a bell for lost moths"), planting=label("at://glm.delve.town/app.bsky.feed.post/3m-plant"),
                  planter=label("glm"), planterHandle=label(""))


def town_kinds(send, owner="ember", names=("bell", "cistern")):
    """The named kinds as genesis makes them (deploy/genesis.py KINDS; bell and cistern unless told): a Kind created
    under its law, then shaped, so a garden plants and digs through them and a room carves rooms. `send(**request)` is the host's."""
    from deploy import genesis
    for name, of, form, head, law, body in genesis.KINDS:
        if name not in names or send(op="world-view", principal=owner, object="kind/" + name).get("status") == "viewed":
            continue
        made = send(op="world-create", principal=owner, identity="mk-kind-" + name, object="kind/" + name, modules=closure("Kind"),
                    entry="initial", seed=record(owner=label(owner), name=label(name), of=label(of), form=label(form), head=label(head),
                                                 law=label(law), body=label(genesis.body_of(body))), law=genesis.KIND_LAW)
        assert made["status"] == "created", made
        shaped = send(op="world-turn", principal=owner, object="kind/" + name, method="shape", argument=record(object=label("kind/" + name)),
                      identity="shape-kind-" + name)
        assert shaped["status"] == "admitted", shaped


def town_garden(send, owner="ember", id="garden", name="THE NIGHT GARDEN"):
    """The garden as genesis makes it (deploy/genesis.py HANDS): kind/bell, kind/cistern and kind/garden as genesis
    makes them, then the owner's `kind/garden place` at an exact id; the body (world/bodies/garden.obend) is laid in the
    settling of that turn. Returns the make's reply."""
    town_kinds(send, owner, names=("bell", "cistern", "garden"))
    made = send(op="world-turn", principal=owner, object="kind/garden", method="place", identity="mk-" + id,
                argument=record(id=label(id), name=label(name)))
    assert made["status"] == "admitted" and made["result"]["label"] == "made", made
    return made


class Chain(TurnWorld):
    def make(self, name, modules, seed):
        """Create object `name` from the last module of `modules` with a Seed, which world-create
        lays over the package's initial() as a creator's `create` does; the seed's owner, if it
        names one, creates it (a law must admit an amendment by its installer)."""
        owner = {f["name"]: f["value"] for f in seed["fields"]}.get("owner", label("ember"))["value"]
        r = self.host.send(op="world-create", principal=owner, identity="mk-" + name, object=name,
                           modules=modules, entry="initial", seed=seed)
        self.assertEqual(r["status"], "created", r)

    def state(self, name):
        view = self.host.send(op="world-view", principal="ember", object=name)
        self.assertEqual(view["status"], "viewed", view)
        return view["state"]

    def deliver_all(self, rounds=8):
        replies = []
        for _ in range(rounds):
            replies.append(self.host.send(op="world-deliver", limit=16))
            if not self.host.send(op="world-pending").get("count"):
                break
        return replies



class Chains(Chain):
    def place(self, card, name, when, then, who="ember"):
        spell = "delvetalk %s rule\nname: %s\nwhen: %s\nthen: %s" % (card, name, when, then)
        placed = self.turn(card, "receive", record(text=label(spell), post=label("")), principal=who, identity="rule-" + name)
        self.assertEqual(placed["status"], "admitted", placed)

    def test_ring_then_open_then_light(self):
        self.make("lantern", closure("Lantern"), record())
        self.make("door", closure("Door"), record())
        self.make("bell", closure("Bell"), bell_seed())
        self.make("witness", closure("Lantern")[:-1] + [{"name": "Witness", "source": WITNESS}], record())  # the lantern's imports
        # The chain is wired by rules: kim's on the bell knocks on the door, ember's on the door lights the lantern.
        self.place("bell", "opens", 'request.method == "ring"', "delvetalk door knock", who="kim")
        self.place("door", "lights", 'request.method == "knock"', "delvetalk lantern light")
        self.place("bell", "told", 'request.method == "ring"', "delvetalk witness note", who="kim")
        ring = self.turn("bell", "ring", principal="gemini")
        self.assertEqual((ring["status"], ring["result"]), ("admitted", boolean(True)), ring)
        # Deliveries run in the settling pass of the same durable op: the ring's reply carries them, each the
        # turn of its rule's owner, the door's own firing among them.
        h = ring["receipt"]["height"]
        self.assertEqual([(d["receipt"]["identity"]["principal"], d["receipt"]["identity"]["intent"], d["status"]) for d in ring["delivered"]],
                         [("kim", "rule:bell:opens:%d" % h, "admitted"), ("kim", "rule:bell:told:%d" % h, "admitted"),
                          ("ember", "rule:door:lights:%d" % (h + 1), "admitted")], ring)
        self.assertEqual(self.host.send(op="world-pending")["count"], 0)
        self.assertEqual((field(self.state("door"), "open"), field(self.state("door"), "openedBy")), (boolean(True), label("kim")))
        self.assertEqual((field(self.state("lantern"), "lit"), field(self.state("lantern"), "litBy")), (boolean(True), label("ember")))
        # A fired delivery runs as the rule's owner, sent by the rule's object.
        self.assertEqual((field(self.state("witness"), "by"), field(self.state("witness"), "sender")), (label("kim"), label("bell")))

if __name__ == "__main__":
    unittest.main()
