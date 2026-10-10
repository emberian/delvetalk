"""An interpretation's proposal names the card whose form it fitted (HOST-HANDOFF 5.64).

Evidence for interpretation (layer: host).

A message-dialect object that offers forms of several cards (the Directory offers its doors')
hears a model's spell as `proposal {object, method, argument}`, checked against the object the
fitted form names, not the asking one; the asker then calls that object. Refuted by: the
proposal checked against the asker (`unclear`, since the asker has no `plant`), the proposal
lacking `object`, the call not reaching the garden, or a form naming a method its card does not
offer being proposed.
"""
import unittest

from tests.test_chain import Chain
from tests.test_policy import PolicyObject
from tests.test_turn_world import ON_DISK, closure, declared, label, record

WORLD_LINE = ("  proposal: {method: String, argument: R}", "  proposal: {object: String, method: String, argument: R}")

HUB = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  asked: Nat
def initial() -> State:
  {asked: 0n}
def offered(card: String, action: String) -> World.Forms:
  Lists.List::<Form.Form>.cons({head: {card: card, action: action, fields: Lists.List::<Form.Field>.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 140n})}, tail: Lists.List::<Form.Field>.nil({})})}, tail: Lists.List::<Form.Form>.nil({})})
def ask(state: State, input: {text: String, card: String, action: String}, context: Abi.Context) -> Activity<String>:
  match world.interpret::<Data>({utterance: input.text, offers: offered(input.card, input.action), policy: {world: "", object: "policy"}, model: ""}):
    case proposal(p): passOn(p.object, p.method, p.argument)
    case unclear(u): "unclear"
    case _: "other"
def passOn(object: String, method: String, argument: Data) -> Activity<String>:
  match world.call::<Data>({object: {world: "", object: object}, method: method, argument: argument}):
    case returned(_): "passed {object} {method}"
    case _: "refused"
""", "ask")

GARDEN = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  planted: Nat
  last: String
record Edits:
  planted: Plans.Edit<Nat, Nat>
  last: Plans.Edit<String, {}>
def initial() -> State:
  {planted: 0n, last: ""}
def keep() -> Edits:
  {planted: Plans.Edit.keep({}), last: Plans.Edit.keep({})}
def plant(state: State, input: {seed: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {planted: add 1n, last: set input.seed}
  state.planted + 1n
def tend(state: State, input: {seed: String}, context: Abi.Context) -> Activity<Nat>:
  0n
""", "plant")


class ProposalForAnotherCard(Chain):
    policy = PolicyObject.policy

    def modules(self, name, source):
        with open(ON_DISK["World"], encoding="utf-8") as f:
            world = f.read()
        self.assertIn(WORLD_LINE[0], world)
        override = {"World": world.replace(WORLD_LINE[0], WORLD_LINE[1])}
        seen, out = set(), []
        for dep in ("Abi", "List", "Form", "Plan", "World"):
            closure(dep, seen, out, override)
        return out + [{"name": name, "source": source}]

    def setUp(self):
        super().setUp()
        self.policy()
        self.make("hub", self.modules("Hub", HUB), record())
        self.make("g", self.modules("Garden", GARDEN), record())

    def ask(self, text, card="g", action="plant"):
        asked = self.turn("hub", "ask", record(text=label("plant a fern"), card=label(card), action=label(action)), principal="glm")
        self.assertEqual(asked["status"], "suspended", asked)
        [pending] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "raw": text, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = settled["resumed"]
        return settled, resumed

    def test_the_proposal_names_the_garden_and_the_hub_calls_it(self):
        settled, resumed = self.ask("delvetalk g plant\nseed: a fern")
        verdict = settled["receipt"]["outcome"]["verdict"]
        self.assertEqual((verdict["tag"], verdict["object"], verdict["method"]), ("proposal", "g", "plant"), verdict)
        self.assertEqual((resumed["status"], resumed["result"]["value"]), ("admitted", "passed g plant"), resumed)
        state = {f["name"]: f["value"] for f in self.state("g")["fields"]}
        self.assertEqual((state["planted"]["value"], state["last"]["value"]), ("1", "a fern"))

    def test_a_form_naming_a_method_its_card_does_not_offer_is_unclear(self):
        settled, resumed = self.ask("delvetalk g tend\nseed: a fern", action="tend")
        verdict = settled["receipt"]["outcome"]["verdict"]
        self.assertEqual(verdict["tag"], "unclear", verdict)
        self.assertIn("tend is not a method g offers", verdict["needs"][0])
        self.assertEqual(resumed["result"]["value"], "unclear", resumed)


if __name__ == "__main__":
    unittest.main()
