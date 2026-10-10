"""Making an object in the shared world from a resident's own source (docs/GROUND.md §6 changes 1 and 6).

Evidence (layer: host): the `make` Plan creates, under the maker's authority, an object from Bend
source the resident supplied (the Workshop's held, checked package); the create entry journals the
source (by CID), its pin and `madeFrom {object, pin, receipt}`; a compile failure is refused by name
with the checker's diagnostic. Refuted by a made object whose pin is not its source's, a lineage that
names an object or receipt the journal does not hold, a lost diagnostic, or a make that does not replay.

    python3 -W error -m unittest tests.test_make -v
"""
import unittest

from tests.test_reflection import Reflection
from tests.test_turn_world import declared, label, nat, record

MAKER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  made: Nat
def initial() -> State:
  {made: 0n}
def make(state: State, input: {source: String, id: String, origin: String, receipt: String}, context: Abi.Context) -> Activity<String>:
  match world.make({package: input.source, seed: Data.of::<{}>({}), law: "", requireAbsent: {world: "", object: input.id}, madeFrom: {object: {world: "", object: input.origin}, receipt: input.receipt}}):
    case created(c): c.object.object
    case refused(r): "{r.clause} | {r.reading}"
    case _: "other"
""")

LAMP = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  lit: Bool
def initial() -> State:
  {lit: false}
def light(state: State, context: Abi.Context) -> Activity<Bool>:
  let written(_) = write {lit: set true}
  true
def methods() -> Lists.List<String>:
  Lists.List::<String>.cons({head: "light", tail: Lists.List::<String>.nil({})})
""".replace("import ./Abi.obend as Abi\n", "import ./Abi.obend as Abi\nimport ./List.obend as Lists\n", 1)


KIND = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  made: Nat
def initial() -> State:
  {made: 0n}
def make(state: State, input: {source: String, body: String, id: String}, context: Abi.Context) -> Activity<String>:
  match world.create({package: input.source, seed: Data.of::<{}>({}), law: "", requireAbsent: {world: "", object: input.id}}):
    case created(c): grafted(input.id, input.body)
    case refused(r): "create {r.clause}"
    case _: "other"
def grafted(id: String, body: String) -> Activity<String>:
  match world.extend({object: {world: "", object: id}, package: body, migration: ""}):
    case reprogrammed(p): "made {id}"
    case refused(r): refuse("what was made could not be given its body, so nothing was made")
    case _: "other"
""", "make")

DIM = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
type State = Super.State
def dim(state: State, context: Abi.Context) -> Activity<Bool>:
  let written(_) = write {lit: set false}
  false
def methods() -> Lists.List<String>:
  Lists.List::<String>.cons({head: "light", tail: Lists.List::<String>.cons({head: "dim", tail: Lists.List::<String>.nil({})})})
"""


class Make(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("workshop", MAKER, record(made=nat(0)))

    def held(self):
        """A receipt the journal holds: the workshop's creation stands in for the hold of the checked package."""
        return self.host.send(op="world-receipt", principal="ember", identity="mk-workshop")["receipt"]["hash"]

    def test_a_residents_source_is_made_with_its_lineage(self):
        receipt = self.held()
        r = self.turn("workshop", "make", record(source=label(LAMP), id=label("lamp"),
                                                origin=label("workshop"), receipt=label(receipt)), principal="kim")
        self.assertEqual((r["status"], r["result"]), ("admitted", label("lamp")), r)
        [made] = r["receipt"]["outcome"]["creates"]
        pin = self.host.send(op="world-inspect", principal="kim", object="workshop")["pin"]
        self.assertEqual(made["madeFrom"], {"object": "workshop", "pin": pin, "receipt": receipt})
        lamp = self.host.send(op="world-inspect", principal="kim", object="lamp")
        self.assertEqual(lamp["pin"], made["pin"])
        self.assertEqual(self.turn("lamp", "light", principal="kim")["status"], "admitted")
        self.reopen()
        self.assertEqual(self.host.send(op="world-inspect", principal="kim", object="lamp")["pin"], made["pin"])

    def test_a_compile_failure_is_refused_by_name_with_the_diagnostic(self):
        r = self.turn("workshop", "make", record(source=label("edition ObjectiveBend 1\nrecord State:\n  n: Nat\ndef initial() -> State:\n  {n: true}\n"),
                                                id=label("bad"), origin=label("workshop"), receipt=label(self.held())), principal="kim")
        said = r["result"]["value"]
        self.assertTrue(said.startswith("compile | "), said)
        self.assertIn("initial", said)

    def test_a_lineage_the_journal_does_not_hold_is_refused(self):
        for frm, receipt in (("ghost", self.held()), ("workshop", "bafy-not-a-receipt")):
            r = self.turn("workshop", "make", record(source=label(LAMP), id=label("lamp"), origin=label(frm),
                                                    receipt=label(receipt)), principal="kim")
            self.assertTrue(r["result"]["value"].startswith("madeFrom | "), r)


class CreateThenExtend(Reflection):
    """A turn reaches what it created (the rewrite lane's Kind): an `extend` of an object the same turn
    created lays the layer into the creation, judged by the made thing's law, so a kind makes a thing
    and grafts its body in one entry; a body that does not compile refuses with nothing made."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("kind", KIND, record(made=nat(0)))


    def test_a_body_that_does_not_compile_leaves_nothing_made(self):
        r = self.turn("kind", "make", record(source=label(LAMP), body=label(DIM.replace("false\n", "7n\n", 1)), id=label("lamp")), principal="kim")
        self.assertEqual(r["status"], "refused", r)
        self.assertNotEqual(self.host.send(op="world-inspect", principal="kim", object="lamp")["status"], "inspected")


if __name__ == "__main__":
    unittest.main()
