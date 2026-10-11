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
from tests.wire import label, record
from tests.bend import MODULES, closure, declared

WORLD_LINE = "  proposal: {object: String, method: String, argument: R, spell: String}"

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
  match world.interpret::<Data>({utterance: input.text, offers: offered(input.card, input.action), policy: {world: "", object: "policy"}, model: "", held: "", misfit: ""}):
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


# hob's reply that stopped the second playtest (message 69158; journal height 349), verbatim: prose, no `say:`.
PLAYTEST_69158 = "That's a good result to see end to end: a clause you wrote, with your own name and reading, parsed, enforced on the first attempt, and the receipt quoted your words back. The refusal reads as the card's own voice, not a generic error, which is the point of putting the reading next to the law.\n\nI'm the card's hob here, so I should be plain about what I did and didn't do: I'm not going to add a spell from this message, since it's a comment on the mechanism rather than a request to act on the card. If you want something run, tell me the spell in words, for example \"delvetalk garden plant, seed: ..., colour: ...\", and I'll answer with the spell or ask for what's missing."


class ProposalForAnotherCard(Chain):
    policy = PolicyObject.policy

    def modules(self, name, source):
        with open(MODULES["World"], encoding="utf-8") as f:
            self.assertIn(WORLD_LINE, f.read())
        out = closure(*("Abi", "List", "Form", "Plan", "World"))
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

    def test_hobs_answers_that_are_no_spell(self):
        # docs/FLEX.md §4 host 6: `none`, `card`, `ask: <question>`, `say: <answer>` beside the spells. Only `say:`
        # is hob's answer, two sentences and 300 characters at most, cut at a sentence end outside an example;
        # prose with no prefix and no spell is silence (the second playtest's stop, 69158, verbatim below).
        answer = "A kind is a template for a made thing. The make form takes a name and an of."
        long = ("A kind is a template. " * 40).strip()
        quoted = "Try `delvetalk kinds make / name: lamp.` and it is yours. Then use it."
        for said, verdict in (("none", {"tag": "unclear", "needs": ["not addressed"]}),
                              ("  None\n", {"tag": "unclear", "needs": ["not addressed"]}),
                              ("card", {"tag": "replied", "text": "card"}),
                              ("ask: which seed, 1 to 140 characters?", {"tag": "unclear", "needs": ["which seed, 1 to 140 characters?"]}),
                              ("say: " + answer, {"tag": "said", "text": answer}),
                              ("say: " + answer + " If you tell me the name, I can draft it.", {"tag": "said", "text": answer}),
                              ("say: " + long, {"tag": "said", "text": "A kind is a template. A kind is a template."}),
                              ("say: " + quoted, {"tag": "said", "text": quoted}),
                              ("say: " + "x" * 700, {"tag": "unclear", "needs": ["not addressed"]}),
                              (answer, {"tag": "unclear", "needs": ["not addressed"]}),
                              (PLAYTEST_69158, {"tag": "unclear", "needs": ["not addressed"]})):
            settled, _ = self.ask(said)
            self.assertEqual(settled["receipt"]["outcome"]["verdict"], verdict, said)


# MENU §2.2: a reply with several spells is `proposals {items}`, each item a proposal or `unclear`.
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
  match world.interpret::<Data>({utterance: input.text, offers: offered(), policy: {world: "", object: "policy"}, model: "", held: "", misfit: ""}):
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
    modules = ProposalForAnotherCard.modules

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


if __name__ == "__main__":
    unittest.main()
