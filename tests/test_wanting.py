"""What wants a hand across the world (docs/OVERHAUL.md §5; HOST-HANDOFF 5.164): `world.wanting {after, limit}` and
`world-wanting` read the wanting index `record` derives (`World.wanting`): each want that holds of its thing as
it stands, for things the reader may view, newest first, a page holding whole heights.

Evidence for the minimal genesis's "what wants a hand" (layer: host; the Bend arm needs the pair's World.obend).
Refuted by a want listed that no longer holds, a thing listed to a reader who may not view it, an older row above
a newer one, a page that splits a height or loses a row across `after`, or a read that writes or answers
otherwise after a reopen.
"""
import unittest

from tests.test_reflection import Reflection
from tests.test_verbs import STONE, THING
from tests.wire import label, nat, record
from tests.bend import declared

ASK = "delvetalk {request.object} rain / text: again"

LIST = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def wants(state: State, input: {after: Nat, limit: Nat}, context: Abi.Context) -> Activity<String>:
  match world.wanting({after: input.after, limit: input.limit}):
    case wanting(w): if w.more then "{rows(w.rows)} +" else rows(w.rows)
    case refused(r): "refused {r.clause}"
def rows(items: Lists.List<World.Want>) -> String:
  textJoin(Lists.map(items, fn(i: World.Want) -> String: "{i.object} {i.name} @{natText(i.since)}: {i.asks}"), "; ")
""", "wants")


class Wanting(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        for name in ("bell", "bell2"):
            self.make(name, THING, record(owner=label("ember")))
        self.make("stone", STONE, record(owner=label("ember")), read={"principals": ["ember"]})

    def say(self, card, text, who="glm"):
        r = self.turn(card, "receive", record(text=label(text), post=label("")), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r["receipt"]

    def want(self, card, name, when, who="glm"):
        return self.say(card, "delvetalk %s want\nname: %s\nwhen: %s\nasks: %s" % (card, name, when, ASK), who=who)

    def wanting(self, who="glm", **page):
        r = self.host.send(op="world-wanting", principal=who, **page)
        self.assertEqual(r["status"], "wanting", r)
        return [(x["object"], x["name"], x["since"]) for x in r["rows"]], r["more"]

    def test_the_index_newest_first_by_whole_heights_for_whom_may_view(self):
        # Two wants that one rain makes true at once, a want true where it is placed, one on a private stone.
        self.want("bell", "wet", "new.rains >= 1")
        self.want("bell", "damp", "new.rains >= 1")
        dry = self.want("bell2", "dry", "new.rains <= 0")["height"]
        hidden = self.want("stone", "dry", "new.rains <= 0", who="ember")["height"]
        rained = self.say("bell", "delvetalk bell rain\ntext: one", who="kimi")["height"]
        self.assertEqual(self.wanting(), ([("bell", "damp", rained), ("bell", "wet", rained), ("bell2", "dry", dry)], False))
        self.assertEqual(self.wanting(who="ember")[0], [("bell", "damp", rained), ("bell", "wet", rained),
                                                        ("stone", "dry", hidden), ("bell2", "dry", dry)])
        # A page of one row still holds its height whole; `after` its last `since` reads on without a gap.
        self.assertEqual(self.wanting(limit=1), ([("bell", "damp", rained), ("bell", "wet", rained)], True))
        self.assertEqual(self.wanting(after=rained, limit=1), ([("bell2", "dry", dry)], False))
        row = self.host.send(op="world-wanting", principal="glm", after=rained)["rows"][0]
        self.assertEqual(row["asks"], "delvetalk bell2 rain / text: again")
        # A want that stops holding leaves; reading writes nothing; a reopen and a snapshot answer the same.
        self.say("bell2", "delvetalk bell2 rain\ntext: one", who="kimi")
        height = self.host.send(op="world-status")["height"]
        listed = self.wanting()
        self.assertEqual(listed, ([("bell", "damp", rained), ("bell", "wet", rained)], False))
        self.assertEqual(self.host.send(op="world-status")["height"], height)
        self.reopen()
        self.assertEqual(self.wanting(), listed)
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(self.wanting(), listed)

    def test_a_body_reads_the_index_through_world_wanting(self):
        self.make("list", LIST, record(n=nat(0)))
        dry = self.want("bell2", "dry", "new.rains <= 0")["height"]
        self.want("stone", "dry", "new.rains <= 0", who="ember")
        r = self.turn("list", "wants", record(after=nat(0), limit=nat(0)), principal="glm")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(r["result"]["value"], "bell2 dry @%d: delvetalk bell2 rain / text: again" % dry)


if __name__ == "__main__":
    unittest.main()
