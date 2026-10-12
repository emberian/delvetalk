"""What wants a hand across the world (docs/OVERHAUL.md §5; HOST-HANDOFF 5.164, 5.165): `world.wanting {after,
limit}` and `world-wanting` read the wanting index `record` derives (`World.wanting`): each want that holds of its
thing as it stands, for things the reader may view, newest first, a page holding whole heights. A want reads what
its thing stands at: `request.laws` (its law clauses, own and followed) and `request.refusedBy` (the writes its law
refused), and a law's refusal journals the wants it opens.

Evidence for the minimal genesis's "what wants a hand" and a seal's "a law and a second hand's try" (layer: host;
the Bend arm needs the pair's World.obend). Refuted by a want listed that no longer holds, a thing listed to a
reader who may not view it, an older row above a newer one, a page that splits a height or loses a row across
`after`, a refusal that opens a want without saying so or that replay derives otherwise, or a read that writes or
answers otherwise after a reopen.
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


class Things(Reflection):
    """Two bells and a stone only ember may view."""

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


class Wanting(Things):
    def test_the_index_newest_or_oldest_first_by_whole_heights_for_whom_may_view(self):
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
        # `oldest`: what has waited longest first (the morning card's), paged past `after` the other way.
        self.assertEqual(self.wanting(oldest=True), ([("bell2", "dry", dry), ("bell", "damp", rained), ("bell", "wet", rained)], False))
        self.assertEqual(self.wanting(oldest=True, limit=1), ([("bell2", "dry", dry)], True))
        self.assertEqual(self.wanting(oldest=True, after=dry, limit=1), ([("bell", "damp", rained), ("bell", "wet", rained)], False))
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



SEAL_LAW = ('law open: request.kind == 0 or request.kind == rule or request.subject == "ember"\n'
            'law hands "only glm rains on it": request.method == "rain" implies request.subject == "glm"')


class Standing(Things):
    def test_a_law_and_a_second_hands_try_open_a_want_at_the_refusal(self):
        self.make("seal", THING, record(owner=label("ember")), law=SEAL_LAW)
        placed = self.say("seal", "delvetalk seal want\nname: tried\nreading: a law and a second hand's try\n"
                                  "when: request.laws >= 2 and request.refusedBy >= 1\n"
                                  "asks: delvetalk {request.object} rain / text: {request.refusedBy} of {request.laws}")
        self.assertNotIn("wanted", placed)
        self.assertEqual(self.say("seal", "delvetalk seal rain\ntext: mine")["outcome"]["tag"], "admitted")
        r = self.turn("seal", "receive", record(text=label("delvetalk seal rain\ntext: a try"), post=label("")), principal="kimi")
        refused = r["receipt"]
        self.assertEqual((refused["outcome"]["class"], refused["outcome"]["clause"]), ("lawRefused", "hands"), r)
        self.assertEqual(refused["wanted"], [{"object": "seal", "want": "tried"}])
        listed = self.host.send(op="world-wanting", principal="glm")["rows"]
        self.assertEqual([(x["object"], x["name"], x["since"], x["asks"]) for x in listed],
                         [("seal", "tried", refused["height"], "delvetalk seal rain / text: 1 of 2")])
        wants = self.host.send(op="world-wants", principal="glm", object="seal")["rows"]
        self.assertEqual([(x["name"], x["since"]) for x in wants], [("tried", refused["height"])])
        day = self.host.send(op="world-chronicle", principal="glm", day=0)["lines"]
        self.assertIn("seal came to want tried at entry %d" % refused["height"], day)
        # Replay derives the count and the opening again; so does a snapshot.
        self.reopen()
        self.assertEqual(self.host.send(op="world-wanting", principal="glm")["rows"], listed)
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(self.host.send(op="world-wanting", principal="glm")["rows"], listed)
        self.turn("seal", "receive", record(text=label("delvetalk seal rain\ntext: again"), post=label("")), principal="kimi")
        self.assertEqual(self.host.send(op="world-wanting", principal="glm")["rows"][0]["asks"], "delvetalk seal rain / text: 2 of 2")

    def test_a_law_reads_what_its_thing_stands_at(self):
        self.make("seal", THING, record(owner=label("ember")),
                  law=SEAL_LAW + '\nlaw patience "three refusals close it": request.refusedBy <= 2')
        for i in range(3):
            r = self.turn("seal", "receive", record(text=label("delvetalk seal rain\ntext: %d" % i), post=label("")), principal="kimi")
            self.assertEqual(r["receipt"]["outcome"]["clause"], "hands", r)
        closed = self.turn("seal", "receive", record(text=label("delvetalk seal rain\ntext: late"), post=label("")), principal="glm")
        self.assertEqual(closed["receipt"]["outcome"]["clause"], "patience", closed)


class Journaled(Things):
    """A want's flips are journaled wherever they come from: the clock's move, a write of what it cites."""

    def test_a_want_the_clock_alone_opens_is_in_the_index_and_the_chronicle(self):
        self.want("bell", "late", "request.clock >= 1441")
        self.assertEqual(self.wanting(), ([], False))
        advanced = self.host.send(op="world-advance", height=1500)
        self.assertEqual(advanced["status"], "advanced", advanced)
        at = advanced["receipt"]["height"]
        self.assertEqual(advanced["receipt"]["wanted"], [{"object": "bell", "want": "late"}])
        self.assertEqual(self.wanting(), ([("bell", "late", at)], False))
        self.assertEqual([x["since"] for x in self.host.send(op="world-wants", principal="glm", object="bell")["rows"]], [at])
        day = self.host.send(op="world-chronicle", principal="glm", day=0)["lines"]
        self.assertIn("bell came to want late at entry %d" % at, day)
        # Replay derives the flip again; so does a snapshot.
        self.reopen()
        self.assertEqual(self.wanting(), ([("bell", "late", at)], False))
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(self.wanting(), ([("bell", "late", at)], False))

    def test_a_write_of_what_a_want_cites_journals_the_flip_of_the_thing_that_wants(self):
        self.want("bell", "cited", '"bell2".rains >= 1')
        self.assertEqual(self.wanting(), ([], False))
        written = self.say("bell2", "delvetalk bell2 rain\ntext: one", who="kimi")
        self.assertEqual(written["wanted"], [{"object": "bell", "want": "cited"}])
        self.assertEqual(self.wanting(), ([("bell", "cited", written["height"])], False))
        day = self.host.send(op="world-chronicle", principal="glm", day=0)["lines"]
        self.assertIn("bell came to want cited at entry %d" % written["height"], day)
        self.reopen()
        self.assertEqual(self.wanting(), ([("bell", "cited", written["height"])], False))


if __name__ == "__main__":
    unittest.main()
