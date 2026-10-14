"""Making an object in the shared world from a resident's own source (docs/VOICE.md "The offering").

Evidence (layer: host): the `make` Plan creates, under the maker's authority, an object from Bend
source the resident supplied (the Workshop's held, checked package); the create entry journals the
source (by CID), its pin and `madeFrom {object, pin, receipt}`; a compile failure is refused by name
with the checker's diagnostic. Refuted by a made object whose pin is not its source's, a lineage that
names an object or receipt the journal does not hold, a lost diagnostic, or a make that does not replay.

    python3 -W error -m unittest tests.test_make -v
"""
import json
import unittest

from tests.test_reflection import Reflection
from tests.wire import label, nat, record
from tests.bend import declared

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


class MakerFixture(Reflection):
    opener = None

    def setUp(self):
        super().setUp()
        self.open_library(**({"opener": self.opener} if self.opener else {}))
        self.make("workshop", MAKER, record(made=nat(0)))

    def held(self):
        """A receipt the journal holds: the workshop's creation stands in for the hold of the checked package."""
        return self.host.send(op="world-receipt", principal="ember", identity="mk-workshop")["receipt"]["hash"]



class Make(MakerFixture):
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

    def test_a_package_made_in_a_turn_keeps_its_rules_and_wants_through_replay(self):
        # codex 2026-10-12 host 4: replay built the creation with its law as given, which places no package
        # lines, so the want it opened did not replay and its rules were lost.
        lines = 'want dark "it is dark": new.lit == 0 asks delvetalk lamp light\nrule lit: new.lit == 1 then delvetalk me note / text: lit\n'
        source = LAMP.replace("def initial()", lines + "def initial()")
        r = self.turn("workshop", "make", record(source=label(source), id=label("lamp"),
                                                origin=label("workshop"), receipt=label(self.held())), principal="kim")
        self.assertEqual((r["status"], r["result"]), ("admitted", label("lamp")), r)
        self.assertEqual(r["receipt"]["wanted"], [{"object": "lamp", "want": "dark"}], r)
        rows = lambda op: [x["name"] for x in self.host.send(op=op, principal="kim", object="lamp")["rows"] if x["from"] == "lamp"]
        self.assertEqual((rows("world-rules"), rows("world-wants")), (["lit"], ["dark"]))
        self.reopen()
        verified = self.host.send(op="world-open", path=self.path, verify=True)
        self.assertEqual(verified["status"], "opened", verified)
        self.assertEqual((rows("world-rules"), rows("world-wants")), (["lit"], ["dark"]))

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


class ObjectShares(MakerFixture):
    opener = "ember"

    def make_as(self, who, name):
        return self.turn("workshop", "make", record(source=label(LAMP), id=label(name),
                         origin=label("workshop"), receipt=label(self.held())), principal=who)

    def test_kind_makings_charge_the_resident_and_retirement_releases_only_their_share(self):
        for i in range(128):
            r = self.make_as("kim", f"kim/{i}")
            self.assertEqual((r["status"], r["result"]), ("admitted", label(f"kim/{i}")), r)
        r = self.make_as("kim", "kim/over")
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "capacity"), r)
        self.assertIn("objectsPerPrincipal", r["receipt"]["outcome"]["reason"])
        # The live review's finding 6: the bound and what frees it, never "try later" (waiting frees nothing).
        self.assertIn("you keep 128 of the 128 things a hand keeps in this town; retire one of yours (delvetalk <thing> retire)", r["receipt"]["outcome"]["reason"])
        self.assertNotIn("later", r["receipt"]["outcome"]["reason"])
        self.assertEqual(self.make_as("yue", "yue/0")["status"], "admitted")
        retired = self.turn("kim/0", "retire", record(reading=label("finished")), principal=self.opener)
        self.assertEqual(retired["status"], "admitted", retired)
        self.assertEqual(self.host.send(op="world-inspect", principal="kim", object="kim/0")["status"], "inspected")
        self.assertEqual(self.make_as("kim", "kim/replacement")["status"], "admitted")
        self.reopen()
        self.assertEqual(self.make_as("kim", "kim/still-full")["status"], "refused")
        restored = self.turn("kim/0", "unretire", record(reading=label("restored")))
        self.assertEqual(restored["status"], "refused", restored)
        self.assertIn("objectsPerPrincipal", restored["receipt"]["outcome"]["reason"])

    def test_a_resident_releases_their_share_by_an_amendable_retirement_and_cannot_restore_over_it(self):
        for i in range(128):
            self.assertEqual(self.make_as("kim", f"kim/{i}")["status"], "admitted")
        inspected = self.host.send(op="world-inspect", principal="kim", object="kim/0")
        prior = inspected["law"]
        retired = self.host.send(op="world-amend", principal="kim", identity="own-retirement", object="kim/0", version=0,
                                 law=prior + '\nlaw retired "finished": request.kind == 2 and request.subject == "kim"')
        self.assertEqual(retired["status"], "admitted", retired)
        self.assertTrue(self.host.send(op="world-inspect", principal="kim", object="kim/0")["retired"])
        self.assertEqual(self.turn("kim/0", "light", principal="kim")["receipt"]["outcome"]["clause"], "retired")
        self.assertEqual(self.make_as("kim", "kim/replacement")["status"], "admitted")
        version = self.host.send(op="world-view", principal="kim", object="kim/0")["version"]
        restored = self.host.send(op="world-amend", principal="kim", identity="own-restoration", object="kim/0", version=version, law=prior)
        self.assertEqual(restored["status"], "refused", restored)
        self.assertIn("objectsPerPrincipal", restored["receipt"]["outcome"]["reason"])
        live_law = self.host.send(op="world-inspect", principal="kim", object="kim/1")["law"]
        marked = self.host.send(op="world-amend", principal="kim", identity="false-retirement", object="kim/1", version=0,
                                law=live_law + '\nlaw retired: request.kind == 0 or request.subject == "kim"')
        self.assertEqual(marked["status"], "admitted", marked)
        self.assertFalse(self.host.send(op="world-inspect", principal="kim", object="kim/1")["retired"])
        self.assertEqual(self.make_as("kim", "kim/not-freed-by-name")["status"], "refused")
        self.reopen()
        self.assertTrue(self.host.send(op="world-inspect", principal="kim", object="kim/0")["retired"])
        self.assertEqual(self.make_as("kim", "kim/still-full-after-retirement")["status"], "refused")

    def test_a_resealed_snapshot_cannot_change_the_maker_to_bypass_the_share(self):
        from tests.test_snapshot import read_snapshot, write_snapshot
        self.assertEqual(self.make_as("kim", "kim/one")["status"], "admitted")
        snapshot = self.host.send(op="world-snapshot")
        self.assertEqual(snapshot["status"], "snapshot", snapshot)
        path = self.path + f".snapshot.{snapshot['height']}.cbor"
        body = read_snapshot(path)
        next(obj for obj in body["objects"] if obj["id"] == "kim/one")["maker"] = "ember"
        write_snapshot(path, body)
        self.reopen()
        opened = self.host.send(op="world-open", path=self.path)
        self.assertTrue(any("maker" in r["reason"] for r in opened["snapshot"]["refused"]), opened)
        self.assertEqual(self.host.send(op="world-inspect", principal="kim", object="kim/one")["maker"], "kim")

    def test_retiring_does_not_reclaim_the_global_object_limit(self):
        opened = self.host.send(op="world-open", path=self.path, maxObjects=2)
        self.assertEqual(opened["status"], "opened", opened)
        self.assertEqual(self.make_as("kim", "last")["status"], "admitted")
        retired = self.turn("last", "retire", record(reading=label("finished")), principal=self.opener)
        self.assertEqual(retired["status"], "admitted", retired)
        r = self.make_as("kim", "still-no-global-slot")
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "capacity"), r)
        self.assertIn("maxObjects", r["receipt"]["outcome"]["reason"])

    def test_direct_creations_and_in_turn_creations_use_the_same_share_and_opener_is_exempt(self):
        spoofed = LAMP.replace("  lit: Bool", "  lit: Bool\n  owner: String").replace("{lit: false}", '{lit: false, owner: "ember"}')
        for who, count in (("kim", 128), ("ember", 129)):
            for i in range(count):
                r = self.host.send(op="world-create", principal=who, identity=f"{who}-direct-{i}",
                                   object=f"{who}/direct/{i}", source=spoofed if i == 0 else LAMP, entry="initial", seed=record(owner=label("ember")) if i == 0 else record())
                self.assertEqual(r["status"], "created", r)
        self.assertEqual(self.host.send(op="world-inspect", principal="kim", object="kim/direct/0")["maker"], "kim")
        r = self.host.send(op="world-create", principal="kim", identity="over-direct", object="over-direct",
                           source=LAMP, entry="initial", seed=record())
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "capacity"), r)
        self.assertIn("objectsPerPrincipal", r["receipt"]["outcome"]["reason"])
        self.assertEqual(self.make_as("kim", "over-through-kind")["status"], "refused")


class CreateThenExtend(Reflection):
    """A turn reaches what it created (the rewrite lane's Kind): an `extend` of an object the same turn
    created lays the layer into the creation, judged by the made thing's law, so a kind makes a thing
    and grafts its body in one entry; a body that does not compile refuses with nothing made."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("kind", KIND, record(made=nat(0)))


    def test_a_method_the_body_adds_runs_on_the_made_thing_and_a_later_layer_lays_over_it(self):
        """The objects lane's atomic make: the layer's own methods are the made thing's, taking their input."""
        body = DIM.replace("import ./Plan.obend as Plans\n", "import ./Plan.obend as Plans\nimport ./Form.obend as Form\n", 1).replace("def methods()", """form rain:
  drops: natural 1..9
def rain(state: State, input: RainInput, context: Abi.Context) -> Activity<Nat>:
  input.drops
def methods()""").replace('cons({head: "dim", tail:', 'cons({head: "dim", tail: Lists.List::<String>.cons({head: "rain", tail:').replace("nil({})})})", "nil({})})})})")
        r = self.turn("kind", "make", record(source=label(LAMP), body=label(body), id=label("lamp")), principal="kim")
        self.assertEqual(r["status"], "admitted", r)
        rained = self.turn("lamp", "rain", record(drops=nat(3)), principal="kim")
        self.assertEqual((rained["status"], rained.get("result")), ("admitted", nat(3)), rained)
        shine = body.replace("type State = Super.State", "type State = Super.State\ndef shine(state: State, context: Abi.Context) -> Activity<Bool>:\n  true").replace(
            'cons({head: "rain", tail:', 'cons({head: "rain", tail: Lists.List::<String>.cons({head: "shine", tail:').replace("nil({})})})})", "nil({})})})})})")
        later = self.host.send(op="world-reprogram", principal="kim", identity="re1", object="lamp", version=0, mode="extend",
                               package=shine, migration="")
        self.assertEqual(later["status"], "admitted", later)
        self.assertEqual(self.turn("lamp", "rain", record(drops=nat(4)), principal="kim").get("result"), nat(4))
        self.reopen()
        self.assertEqual(self.turn("lamp", "rain", record(drops=nat(5)), principal="kim").get("result"), nat(5))

    def test_a_body_laid_in_the_making_has_the_shape_a_later_extend_gives(self):
        """The objects lane's cistern: a body that names only its own method in `methods()` and declares no
        relations, laid in the turn that makes the thing, keeps what the code below declared public and its
        relations (HOST-HANDOFF §5.3 "Extend"), as the same body laid by a later extend does, and after replay."""
        from tests.test_relation import PACKAGE as RAINS
        base = RAINS.replace("LIMIT", "0n")
        pour = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
type State = Super.State
form pour:
  text: text 1..280
def pour(state: State, input: PourInput, context: Abi.Context) -> Activity<Nat>:
  Super.insert(state, {author: context.principal, at: 1n, text: input.text}, context)
def methods() -> Lists.List<String>:
  Lists.List::<String>.cons({head: "pour", tail: Lists.List::<String>.nil({})})
"""
        made = self.turn("kind", "make", record(source=label(base), body=label(pour), id=label("cistern")), principal="kim")
        self.assertEqual(made["status"], "admitted", made)
        poured = self.turn("cistern", "pour", record(text=label("refused tooSoon")), principal="kim")
        self.assertEqual((poured["status"], poured.get("result")), ("admitted", nat(1)), poured)
        below = self.turn("cistern", "insert", record(author=label("ann"), at=nat(2), text=label("x")), principal="ann")
        self.assertEqual(below["status"], "admitted", below)
        # The same body, laid by an extend after the making.
        self.host.send(op="world-create", principal="kim", identity="mk-later", object="later", source=base,
                       entry="initial", seed=record())
        later = self.host.send(op="world-reprogram", principal="kim", identity="re-later", object="later", version=0,
                               mode="extend", package=pour, migration="")
        self.assertEqual(later["status"], "admitted", later)
        inspect = lambda o: self.host.send(op="world-inspect", principal="kim", object=o)
        self.assertEqual(inspect("cistern")["methods"], inspect("later")["methods"])
        # The forms are the same but for the card each names.
        self.assertEqual(json.dumps(inspect("cistern")["forms"]).replace('"cistern"', '"later"'), json.dumps(inspect("later")["forms"]))
        self.reopen()
        again = self.turn("cistern", "pour", record(text=label("refused again")), principal="bob")
        self.assertEqual(again["status"], "admitted", again)

    def test_a_prefix_mints_past_the_ids_already_held(self):
        """`requireAbsent` ending in `/`: the first free `<prefix><n>`, so a squatter of lamp/1 refuses nothing."""
        self.host.send(op="world-create", principal="mallory", identity="squat", object="lamp/1",
                               modules=[{"name": "Counter", "source": LAMP}], entry="initial", seed=record())
        numbering = KIND.replace("grafted(input.id, input.body)", "grafted(c.object.object, input.body)")
        self.make("numbering", numbering, record(made=nat(0)))
        made = []
        for i in range(2):
            r = self.turn("numbering", "make", record(source=label(LAMP), body=label(DIM), id=label("lamp/")), principal="kim")
            self.assertEqual(r["status"], "admitted", r)
            made += [c["object"] for c in r["receipt"]["outcome"]["creates"]]
        self.assertEqual(made, ["lamp/2", "lamp/3"])
        self.reopen()
        self.assertEqual(self.host.send(op="world-inspect", principal="kim", object="lamp/3")["status"], "inspected")

    def test_a_body_that_does_not_compile_leaves_nothing_made(self):
        r = self.turn("kind", "make", record(source=label(LAMP), body=label(DIM.replace("false\n", "7n\n", 1)), id=label("lamp")), principal="kim")
        self.assertEqual(r["status"], "refused", r)
        self.assertNotEqual(self.host.send(op="world-inspect", principal="kim", object="lamp")["status"], "inspected")


CITER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def cite(state: State, input: {intent: String}, context: Abi.Context) -> Activity<String>:
  match world.await({slot: {principal: context.principal, intent: input.intent}, patience: 8n}):
    case reply(r): r.receipt.hash
    case _: "none"
""", "cite")


class ReceiptHash(Reflection):
    """An await's receipt carries its entry's hash, so Bend can cite it (`madeFrom`; the objects lane's draft adopt)."""

    def test_the_awaited_receipt_names_its_hash(self):
        self.open_library()
        self.make("citer", CITER, record(n=nat(0)))
        first = self.turn("citer", "cite", record(intent=label("x")), principal="kim", identity="x")
        r = self.turn("citer", "cite", record(intent=label("x")), principal="kim")
        self.assertEqual(r.get("result"), label(first["receipt"]["hash"]), r)


class Misfit(Reflection):
    """A turn's argument that does not fit is refused naming the field: one the input does not declare, one it
    needs and lacks, one of another type (HOST-HANDOFF §5.1 "Typed arguments")."""

    def test_the_refusal_names_the_field_that_does_not_fit(self):
        from tests.test_reflection import PROBE, probe_seed
        self.open_library()
        self.make("probe", PROBE, probe_seed())
        reason = lambda argument: self.turn("probe", "bump2", argument)["receipt"]["outcome"]["reason"]
        self.assertIn("bump2 takes no field m", reason(record(n=nat(1), m=nat(2))))
        self.assertIn("bump2 needs field n", reason(record()))
        self.assertIn("bump2's field n is not of its type", reason(record(n=label("one"))))
        self.assertEqual(self.turn("probe", "bump2", record(n=nat(1)))["status"], "admitted")


if __name__ == "__main__":
    unittest.main()
