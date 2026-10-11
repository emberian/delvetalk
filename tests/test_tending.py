"""Tending (docs/METAPHYSICS.md §4, §7.4; docs/LAW.md §4 A, E, F): a made thing is tended at the clock minute and the
entry of its making; a bell's rain tends it, and so does `tend`. kind/bell's law says `alive`: untended for
genesis.QUIET_AFTER clock minutes, a bell takes `tend` alone. Its card says it is quiet and since which entry, and
answers a rain with the clause and the spell that wakes it; the law refuses the same write when a body forgets to.

Evidence for FOUNDATION §8 law (layer: objects). Refuted by: a quiet bell admitting a rain; a tend refused; a card
that hides quiet; the body's window differing from the law's; an instance law that does not cite its kind.
"""
import unittest

from deploy import genesis
from tests.bend import closure, declared
from tests.test_chain import Chain, town_kinds
from tests.wire import cast_refusal, field, label, nat, record, rows

GLM, KIM = "did:plc:glm", "did:plc:kim"


class Tending(Chain):
    def setUp(self):
        super().setUp()
        town_kinds(self.host.send, names=("bell",))
        made = self.turn("kind/bell", "make", record(colour=label("silver"), seed=label("a bell nobody tends")), principal=GLM)
        self.assertEqual((made["status"], made["result"]["label"]), ("admitted", "made"), made)
        self.made_at = made["receipt"]["height"] - 1  # the entry the making turn read, as `context.height` is

    def advance(self, minutes):
        clock = self.host.send(op="world-status").get("clock", 0)
        self.host.send(op="world-advance", principal="transport", height=clock + minutes)

    def card(self, reply):
        if reply["status"] == "refused" and reply["receipt"]["outcome"]["class"] == "cardRefused":
            return reply["receipt"]["outcome"]["reason"] + "\n"  # the card's refusal refuses the turn: its line is the reason
        return "".join(o["text"] for o in reply.get("offers") or reply["receipt"].get("offers") or [])

    def rain(self, text, who=KIM):
        return self.turn("bell/1", "rain", record(text=label(text)), principal=who)

    def test_the_window_is_one_number_in_the_body_and_the_law(self):
        body = genesis.body_of("bell")
        self.assertIn("def quietAfter() -> Nat:\n  %dn\n" % genesis.QUIET_AFTER, body)
        bell = next(k for k in genesis.KINDS if k[0] == "bell")
        self.assertIn(genesis.ALIVE_LAW, bell[4])

    def test_a_made_thing_cites_its_kinds_law_and_is_tended_at_its_making(self):
        laws = self.host.send(op="world-inspect", principal=GLM, object="bell/1")["laws"]
        self.assertIn('under "kind/bell"', str(laws))
        bell = self.state("bell/1")
        self.assertEqual(int(field(bell, "tendedAt")["value"]), self.made_at)

    def test_an_untended_bell_goes_quiet_takes_tend_alone_and_a_rain_tends_it(self):
        self.assertEqual(self.rain("first")["status"], "admitted")
        self.advance(genesis.QUIET_AFTER)  # at the window's edge it still answers
        rained = self.rain("at the edge")
        self.assertEqual((rained["status"], len(rows(field(self.state("bell/1"), "lines")))), ("admitted", 2), rained)
        tended_at = rained["receipt"]["height"] - 1
        self.advance(genesis.QUIET_AFTER + 1)
        card = self.host.send(op="world-card", principal=KIM, object="bell/1")["text"]
        self.assertIn("— quiet, untended since entry %d. Tend it:\n  delvetalk bell/1 tend\n" % tended_at, card)
        hushed = self.rain("too late")
        self.assertEqual(cast_refusal(hushed)[0], "alive", hushed)
        self.assertEqual(self.card(hushed), "refused alive: answers while tended within %d minutes; tend it: delvetalk bell/1 tend\n" % genesis.QUIET_AFTER)
        self.assertEqual(hushed["receipt"]["outcome"].get("writes", []), [], hushed)
        rung = self.turn("bell/1", "ring", principal=KIM)
        self.assertEqual(rung["receipt"]["outcome"]["class"], "lawRefused", rung)
        tended = self.turn("bell/1", "tend", principal=KIM)
        self.assertEqual(tended["status"], "admitted", tended)
        self.assertTrue(self.card(tended).startswith("Tended at clock "), self.card(tended))
        self.assertEqual(self.rain("awake again")["status"], "admitted")
        self.assertIn("— silent. Rain on it:", self.host.send(op="world-card", principal=KIM, object="bell/1")["text"])

    def test_the_law_refuses_a_rain_on_a_quiet_bell_when_its_body_forgets_to(self):
        """The owner lays a body whose rain skips the check: kind/bell's `alive` still refuses it (under the kind)."""
        forgetful = ("layer over ./Layer1.obend\nedition ObjectiveBend 1\nimport ./Abi.obend as Abi\nimport ./List.obend as Lists\nimport ./Document.obend as Document\nimport ./Form.obend as Form\nimport ./Plan.obend as Plans\nimport ./World.obend as World\nimport ./Card.obend as Card\nimport ./Relation.obend as Relations\nimport ./Rows.obend as Rows\nimport ./Text.obend as Text\nimport ./Scenes.obend as Scenes\n"
                     "type State = Super.State\nform pour:\n  text: text 1..200\n"
                     "def pour(state: State, input: PourInput, context: Abi.Context) -> Activity<Nat>:\n"
                     "  let written(_) = write {lines: insert {author: context.principal, handle: context.handle, text: input.text, at: context.height, n: state.next}, next: add 1n}\n"
                     "  state.next\n")
        laid = self.host.send(op="world-reprogram", principal=GLM, identity="forget", object="bell/1",
                              version=self.host.send(op="world-view", principal=GLM, object="bell/1")["version"], package=forgetful, mode="extend")
        self.assertEqual(laid["status"], "admitted", laid)
        self.assertEqual(self.turn("bell/1", "pour", record(text=label("while awake")), principal=KIM)["status"], "admitted")
        self.advance(genesis.QUIET_AFTER + 1)
        poured = self.turn("bell/1", "pour", record(text=label("past the window")), principal=KIM)
        out = poured["receipt"]["outcome"]
        self.assertEqual((poured["status"], out["class"], out["clause"]), ("refused", "lawRefused", "alive"), poured)

    def test_the_quiet_view_names_the_entry_for_another_object(self):
        self.advance(genesis.QUIET_AFTER + 1)
        asker = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def ask(state: State, context: Abi.Context) -> Activity<Data>:
  match world.viewDerived::<Data>({object: {world: context.world, object: "bell/1"}, view: "quietSince"}):
    case derived(d): d.value
    case _: Plans.nothing()
""")
        r = self.host.send(op="world-create", principal="ember", identity="mk-asker", object="asker",
                           modules=closure("World") + [{"name": "Asker", "source": asker}], entry="initial", seed=record(n=nat(0)))
        self.assertEqual(r["status"], "created", r)
        asked = self.turn("asker", "ask", principal=KIM)
        self.assertEqual((asked["status"], asked["result"]), ("admitted", nat(self.made_at)), asked)


class KindLaw(Chain):
    """LAW §4 F: an instance is created under `under "<kind>"`, so the kind's owner amends every instance's law at once."""

    def test_amending_the_kinds_law_re_laws_its_instances(self):
        town_kinds(self.host.send, names=("bell",))
        self.assertEqual(self.turn("kind/bell", "make", record(colour=label("amber"), seed=label("a")), principal=GLM)["status"], "admitted")
        sealed = genesis.RECORD_LAW + '\nlaw sealed "only its maker rains": request.subject == new.maker'
        v = self.host.send(op="world-view", principal="ember", object="kind/bell")["version"]
        proposed = self.host.send(op="world-propose", principal="ember", identity="relaw", roots=[{"object": "kind/bell", "version": v}],
                                  writes=[{"object": "kind/bell", "edits": [record(law={"tag": "variant", "label": "set", "payload": record(value=label(sealed))})]}])
        self.assertEqual(proposed["status"], "admitted", proposed)
        other = self.turn("bell/1", "rain", record(text=label("not the maker")), principal=KIM)
        self.assertEqual((other["status"], other["receipt"]["outcome"]["clause"]), ("refused", "sealed"), other)
        self.assertEqual(self.turn("bell/1", "rain", record(text=label("the maker")), principal=GLM)["status"], "admitted")


if __name__ == "__main__":
    unittest.main()
