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

from tests.host import as_owner

from tests.test_chain import Chain
from tests.test_policy import PolicyObject
from tests.test_turn_world import ON_DISK, closure, declared, label, record

WORLD_LINE = "  proposal: {object: String, method: String, argument: R}"

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
def initial() -> State:
  {planted: 0n, last: ""}
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
            self.assertIn(WORLD_LINE, f.read())
        seen, out = set(), []
        for dep in ("Abi", "List", "Form", "Plan", "World"):
            closure(dep, seen, out)
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
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
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



# MENU §2.2: a reply with several spells is `proposals {items}`, each item a proposal or `unclear`;
# the objects lane's World line, as this copy declares it until it lands.
PROPOSALS_LINES = ("sum Proposed<R>:\n  proposal: {object: String, method: String, argument: R}\n  unclear: {reasons: Document.Names}\n",
                   "  proposals: {items: Lists.List<Proposed<R>>}\n")

MULTI = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  asked: Nat
def initial() -> State:
  {asked: 0n}
def form(action: String) -> Form.Form:
  {card: "g", action: action, fields: Lists.List::<Form.Field>.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 140n})}, tail: Lists.List::<Form.Field>.nil({})})}
def offered() -> World.Forms:
  Lists.List::<Form.Form>.cons({head: form("plant"), tail: Lists.List::<Form.Form>.cons({head: form("tend"), tail: Lists.List::<Form.Form>.nil({})})})
def ask(state: State, input: {text: String}, context: Abi.Context) -> Activity<String>:
  match world.interpret::<Data>({utterance: input.text, offers: offered(), policy: {world: "", object: "policy"}, model: ""}):
    case proposals(p): passAll(p.items, "")
    case proposal(p): "one {p.method}"
    case unclear(u): "unclear"
    case _: "other"
def passAll(items: Lists.List<World.Proposed<Data>>, said: String) -> Activity<String>:
  match items:
    case nil(_): said
    case cons(c): passOne(c.head, c.tail, said)
def passOne(item: World.Proposed<Data>, rest: Lists.List<World.Proposed<Data>>, said: String) -> Activity<String>:
  match item:
    case proposal(p):
      match world.call::<Data>({object: {world: "", object: p.object}, method: p.method, argument: p.argument}):
        case returned(_): passAll(rest, textConcat(said, "+{p.method}"))
        case _: passAll(rest, textConcat(said, "!{p.method}"))
    case unclear(_): passAll(rest, textConcat(said, "?"))
""", "ask")


class SeveralSpells(Chain):
    policy = PolicyObject.policy

    def modules(self, name, source):
        with open(ON_DISK["World"], encoding="utf-8") as f:
            world = f.read()
        if "  proposals:" not in world:
            world = world.replace(WORLD_LINE + "\n", WORLD_LINE + "\n" + PROPOSALS_LINES[1], 1).replace(
                "sum Interpreted<R>:\n", PROPOSALS_LINES[0] + "sum Interpreted<R>:\n", 1)
        seen, out = set(), []
        for dep in ("Abi", "List", "Form", "Plan", "World"):
            closure(dep, seen, out, {"World": world})
        return out + [{"name": name, "source": source}]

    def setUp(self):
        super().setUp()
        self.policy()
        self.make("hub", self.modules("Multi", MULTI), record())
        self.make("g", self.modules("Garden", GARDEN), record())

    def ask(self, text):
        asked = self.turn("hub", "ask", record(text=label("plant two")), principal="glm")
        self.assertEqual(asked["status"], "suspended", asked)
        [pending] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "raw": text, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return settled["receipt"]["outcome"]["verdict"], resumed

    def test_two_spells_and_a_misfit_are_three_items_in_order(self):
        verdict, resumed = self.ask("Here you go:\ndelvetalk g plant\nseed: a fern\ndelvetalk g plant\nseed: a moss\n"
                                    "delvetalk g tend\nseed: x")
        self.assertEqual(verdict["tag"], "proposals", verdict)
        self.assertEqual([i["tag"] for i in verdict["items"]], ["proposal", "proposal", "unclear"], verdict)
        self.assertEqual([i.get("argument") for i in verdict["items"][:2]], [record(seed=label("a fern")), record(seed=label("a moss"))])
        self.assertIn("tend is not a method g offers", verdict["items"][2]["reasons"][0])
        self.assertEqual((resumed["status"], resumed["result"]["value"]), ("admitted", "+plant+plant?"), resumed)
        state = {f["name"]: f["value"] for f in self.state("g")["fields"]}
        self.assertEqual((state["planted"]["value"], state["last"]["value"]), ("2", "a moss"))
        self.release()
        self.host = self.spawn()
        opened = self.host.send(op="world-open", path=self.path)
        self.assertEqual(opened["status"], "opened", opened)
        self.assertEqual({f["name"]: f["value"] for f in self.state("g")["fields"]}, state)

    def test_one_spell_keeps_the_single_proposal(self):
        verdict, resumed = self.ask("delvetalk g plant\nseed: a fern")
        self.assertEqual(verdict["tag"], "proposal", verdict)
        self.assertEqual(resumed["result"]["value"], "one plant", resumed)


if __name__ == "__main__":
    unittest.main()
