"""The library holds one Context and no dynamic universe; objects claim the Plans they perform; cards
render in under 1,400 characters at their fullest.

Evidence for FOUNDATION §5 (layer: objects).

Compile and exercise the Bend standard library and the first objects.

Every module under world/lib and world/objects goes through the real checker
binary (read-only, built elsewhere). Run from the repository root:

    python3 -m unittest tests.test_objects -v
"""
import json
import os
import re
import unittest

from tests import host

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORLD = os.path.join(ROOT, "world")
IMPORT = re.compile(r"^import \./(\w+)\.obend", re.M)
DEF = re.compile(r"^def (\w+)(<[^>]*>)?\(.*\) -> (.*):$", re.M)


def modules_on_disk():
    found = {}
    for root in (os.path.join(WORLD, "lib"), os.path.join(WORLD, "objects")):
        for directory, _, files in os.walk(root):
            for name in files:
                if name.endswith(".obend"):
                    assert name not in found, "module names are flat: " + name
                    found[name[:-6]] = os.path.join(directory, name)
    return found


MODULES = modules_on_disk()


def closure(name, seen=None, out=None):
    """The module and its imports in dependency order (imports first)."""
    seen = set() if seen is None else seen
    out = [] if out is None else out
    if name in seen:
        return out
    seen.add(name)
    with open(MODULES[name]) as handle:
        source = handle.read()
    for dep in IMPORT.findall(source):
        closure(dep, seen, out)
    out.append({"name": name, "source": source})
    return out


def check(request):
    return host.check(request)


def pure(modules):
    """The modules without their law lines: the stateless compile is the pure profile, which
    refuses package laws ("package laws require a host law adapter"); the host keeps them."""
    return [dict(m, source="".join(l for l in m["source"].splitlines(True) if not l.startswith("law ")))
            for m in modules]


def compile_job(modules, entry):
    return check({"op": "compile", "modules": pure(modules), "entry": entry})


def definitions(name):
    """(entry, is_generic, result type text) for each top-level def."""
    with open(MODULES[name]) as handle:
        return [(m.group(1), m.group(2) is not None, m.group(3)) for m in DEF.finditer(handle.read())]


def row_names(row):
    names = []
    while isinstance(row, dict) and row.get("tag") == "field":
        names.append(row["name"])
        row = row["tail"]
    return names


def computation(type_json):
    while type_json.get("tag") != "computation":
        type_json = type_json["codomain"]
    return type_json


def record(**fields):
    return {"tag": "record", "fields": [{"name": k, "value": v} for k, v in fields.items()]}


def nat(n):
    return {"tag": "natural", "value": str(n)}


def run_pure(name, entry, *arguments, probe=None, limits=None):
    """Run a pure entry of `name`, or of a probe module compiled after it.

    The checker's run profile takes records, naturals and labels as arguments
    but not variants, so lists and sums are built inside a probe module."""
    modules = closure(name)
    if probe is not None:
        modules = modules + [{"name": "Probe", "source": probe}]
    compiled = compile_job(modules, entry)
    assert compiled["status"] == "compiled", compiled
    request = {"op": "run", "artifact": compiled["artifact"], "arguments": list(arguments)}
    if limits is not None:
        request["limits"] = limits
    return check(request)


BIG = {"ticks": "1000000"}

PROBE_HEAD_G = "edition ObjectiveBend 1\nimport ./List.obend as Lists\nimport ./Plan.obend as Plans\nimport ./Card.obend as Card\nimport ./Garden.obend as O\n"
GARDEN_PROBE = PROBE_HEAD_G + """import ./Document.obend as Document
import ./Relation.obend as Relations
import ./Bell.obend as Bell
def bells(n: Nat) -> Lists.List<O.Child>:
  match n:
    case 0: Lists.List::<O.Child>.nil()
    case 1+p: Lists.append::<O.Child>(bells(p), {world: "", object: textConcat("garden/bell/", natText(n)), colour: Bell.Colour.amber({})})
def shown(n: Nat) -> String:
  Document.plain(O.render({owner: "ember", planted: n, policy: Plans.nobody(), confirmFor: Lists.List::<String>.nil(), pending: Relations.empty(), children: Relations.Relation.rows({items: bells(n)}), pageCheckpoint: ""}, Card.stranger()))
"""

DOC_PROBE = """edition ObjectiveBend 1
import ./Document.obend as Document
def leaves(n: Nat) -> Document.Documents:
  match n:
    case 0: Document.Documents.nil()
    case 1+p: Document.Documents.cons({head: Document.text("abcdefgh"), tail: leaves(p)})
def flat(n: Nat) -> Nat:
  textLength(Document.plain(Document.Document.sequence({items: leaves(n)})))
"""

PROBE_HEAD = "edition ObjectiveBend 1\nimport ./List.obend as Lists\nimport ./Plan.obend as Plans\nimport ./Document.obend as Document\nimport ./Card.obend as Card\nimport ./%s.obend as O\n"

BELL_PROBE = PROBE_HEAD % "Bell" + """import ./Relation.obend as Relations
def rains(n: Nat) -> Lists.List<O.Rain>:
  match n:
    case 0: Lists.List::<O.Rain>.nil()
    case 1+previous: Lists.List::<O.Rain>.cons({head: {author: "author", handle: "", text: "a line of rain", at: 1n, n: previous}, tail: rains(previous)})
def sample(rains: Lists.List<O.Rain>) -> O.State:
  {colour: O.Colour.silver({}), seed: "a bell for lost moths", rains: Relations.Relation.rows({items: rains}), rung: false, planting: "p", planter: "did:plc:glm", planterHandle: "", doors: Lists.List::<Card.Doorway>.nil()}
def many(n: Nat) -> String:
  Document.plain(O.render(sample(rains(n)), Card.stranger()))
def weight(n: Nat) -> Nat:
  Document.size(O.render(sample(rains(n)), Card.stranger()))
def lineCount(n: Nat) -> Nat:
  Lists.length::<String>(Document.lines(O.render(sample(rains(n)), Card.stranger())))
def two(n: Nat) -> String:
  Document.plain(O.render(sample(Lists.append::<O.Rain>(Lists.append::<O.Rain>(Lists.List::<O.Rain>.nil(), {author: "kimik3", handle: "", text: "first", at: 1n, n: 0n}), {author: "gemini", handle: "", text: "second", at: 2n, n: 1n})), Card.stranger()))
"""

DOOR_PROBE = PROBE_HEAD % "Door" + """def shut(n: Nat) -> String:
  Document.plain(O.render({open: false, openedBy: "", openedHandle: "", knocks: Lists.List::<O.Knock>.cons({head: {who: "did:plc:glm", handle: ""}, tail: Lists.List::<O.Knock>.nil()}), watching: Plans.nobody()}, Card.stranger()))
"""

LINES_PROBE = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./Document.obend as Document
def bar(items: Document.Names) -> String:
  Lists.fold::<String, String>(items, "", fn(head: String) -> String -> String: fn(rest: String) -> String: textConcat(head, textConcat("|", rest)))
def joined(n: Nat) -> String:
  bar(Document.lines(Document.Document.sequence({items: Document.Documents.cons({head: Document.text("alpha\\nbe"), tail: Document.Documents.cons({head: Document.text("ta gamma\\n"), tail: Document.Documents.cons({head: Document.text("delta\\n"), tail: Document.Documents.nil()})})})})))
"""

CISTERN_PROBE = PROBE_HEAD % "Cistern" + """def one(n: Nat) -> String:
  Document.plain(O.render({entries: Lists.List::<Plans.Receipt>.cons({head: {slot: {principal: "glm", intent: "plant"}, height: 7n, outcome: Plans.Outcome.refused({class: "required-absence", root: "r1"})}, tail: Lists.List::<Plans.Receipt>.nil()})}, Card.stranger()))
"""

ANTHOLOGY_PROBE = PROBE_HEAD % "Anthology" + """import ./Relation.obend as Relations
import ./Rows.obend as Rows
def one(n: Nat) -> String:
  Document.plain(O.render({owner: "ember", ownerHandle: "", proposals: Relations.Relation.rows({items: Lists.List::<O.Proposal>.cons({head: {author: "glm", handle: "", line: "moths", status: Rows.Status.proposed({}), at: 1n, n: 0n}, tail: Lists.List::<O.Proposal>.cons({head: {author: "kimik3", handle: "", line: "lamps", status: Rows.Status.admitted({}), at: 2n, n: 1n}, tail: Lists.List::<O.Proposal>.nil()})})})}, Card.stranger()))
"""


class Library(unittest.TestCase):

    def test_only_the_abi_module_declares_the_context_record(self):
        owners = []
        for name, path in MODULES.items():
            with open(path) as handle:
                if re.search(r"^record Context:", handle.read(), re.M):
                    owners.append(name)
        self.assertEqual(owners, ["Abi"])

    def test_no_module_mentions_the_preparation_value_universe(self):
        for name, path in MODULES.items():
            with open(path) as handle:
                self.assertNotIn("Preparation", handle.read(), name)


class Objects(unittest.TestCase):
    def test_methods_perform_the_plans_they_claim(self):
        expected = {("Counter", "bump"): "write", ("Garden", "grow"): "create", ("Garden", "counted"): "write", ("Garden", "cistern"): "create",
                    ("Bell", "rain"): "write", ("Bell", "awaitPlanting"): "awaitPost", ("Bell", "rang"): "write",
                    ("Cistern", "retain"): "write", ("Anthology", "submit"): "write", ("Anthology", "admitted"): "write",
                    ("Door", "opened"): "write", ("Door", "knock"): "write",
                    ("Lantern", "lit"): "write", ("Door", "watch"): "subscribe", ("Loop", "tick"): "write", ("Loop", "again"): "send"}
        for (name, entry), plan in expected.items():
            with open(MODULES[name]) as handle:
                source = handle.read()
            found = re.search(r"\ndef %s(<[^>]*>)?\(" % entry, source)
            self.assertIsNotNone(found, (name, entry))
            body = source[found.start() + 1:].split("\ndef ")[0]
            self.assertTrue(any(form % plan in body for form in ("world.%s(", "= %s {")), (name, entry))

    def test_garden_bell_cistern_and_anthology_cards_render_their_text(self):
        counter = run_pure("Counter", "card", record(count=nat(3)))
        self.assertEqual(counter["value"]["value"], "Count: 3")
        garden = run_pure("Garden", "shown", nat(20), probe=GARDEN_PROBE)
        self.assertEqual(garden["status"], "finished", garden)
        text = garden["value"]["value"]
        self.assertEqual(text, (
            "✾ THE NIGHT GARDEN\n"
            "\n"
            "To plant, reply:\n"
            "\n"
            "    delvetalk garden plant\n"
            "    seed: <what might grow here, 1 to 80 characters>\n"
            "    colour: <amber, violet or silver>\n"
            "\n"
            "20 planted, newest first:\n"
            "- garden/bell/20\n"
            "- garden/bell/19\n"
            "- garden/bell/18\n"
            "- garden/bell/17\n"
            "- garden/bell/16\n"
            "- garden/bell/15\n"
            "- garden/bell/14\n"
            "- garden/bell/13\n"
            "… and 12 more\n"))
        self.assertTrue(text.startswith("✾ THE NIGHT GARDEN\n\nTo plant, reply:"))
        self.assertLess(text.index("garden/bell/20\n"), text.index("garden/bell/13\n"))
        self.assertNotIn("garden/bell/12\n", text)
        self.assertTrue(text.endswith("… and 12 more\n"), text)
        self.assertLess(len(text), 1400)
        for name, probe, entry in (("Bell", BELL_PROBE, "two"), ("Cistern", CISTERN_PROBE, "one"), ("Anthology", ANTHOLOGY_PROBE, "one")):
            with self.subTest(object=name):
                reply = run_pure(name, entry, nat(0), probe=probe)
                self.assertEqual(reply["status"], "finished", reply)
                print(name, "->", repr(reply["value"]["value"]))
                if name == "Bell":
                    text = reply["value"]["value"]
                    self.assertLess(text.index("kimik3: first"), text.index("gemini: second"))
                if name == "Cistern":
                    self.assertIn("refused required-absence", reply["value"]["value"])
                if name == "Anthology":
                    self.assertIn("[proposed] glm: moths", reply["value"]["value"])

    def test_every_object_exports_initial_and_a_seeded_constructor(self):
        """The Seed rule: a creator supplies a Seed; the child's seeded makes its State."""
        objects = ("Counter", "Garden", "Bell", "Cistern", "Anthology", "Door", "Lantern", "Loop", "Place", "Thing",
                   "Directory", "Avatar")
        for name in objects:
            with self.subTest(object=name):
                entries = [d[0] for d in definitions(name)]
                for required in ("defaultSeed", "seeded", "initial"):  # test_artifact_pins compiles each
                    self.assertIn(required, entries)
                with open(MODULES[name]) as handle:
                    source = handle.read()
                self.assertIn("seeded(defaultSeed())", source)

    def test_document_plain_is_linear_not_quadratic_over_256_leaves(self):
        """Document.plain flattens the leaves once and joins them in rounds of
        adjacent pairs. Measured on a sequence of 256 eight-byte text leaves
        (generation included, about 30,000 ticks): 555,890 ticks with the old
        accumulating fold, 72,085 now."""
        probe = DOC_PROBE
        flat = run_pure("Document", "flat", nat(256), probe=probe)
        print("plain over 256 leaves:", flat.get("ticksUsed"), "ticks")
        self.assertEqual(flat["status"], "finished", flat)
        self.assertEqual(flat["value"]["value"], "2048")
        self.assertLess(flat["ticksUsed"], 100000)
        self.assertEqual(run_pure("Document", "flat", nat(256), probe=probe, limits=BIG)["ticksUsed"], flat["ticksUsed"])

    def test_the_door_lantern_and_loop_objects_render_their_cards(self):
        door = run_pure("Door", "shut", nat(0), probe=DOOR_PROBE)
        self.assertEqual(door["status"], "finished", door)
        self.assertEqual(door["value"]["value"], "The door is shut.\nknock: glm\n")
        lantern = run_pure("Lantern", "shown", nat(0), probe=PROBE_HEAD % "Lantern" + "def shown(n: Nat) -> String:\n  Document.plain(O.render({lit: true, litBy: \"did:plc:gemini\", litHandle: \"\", watching: Plans.nobody()}, Card.stranger()))\n")
        self.assertEqual(lantern["value"]["value"], "The lantern is lit by gemini.\n")
        loop = run_pure("Loop", "shown", nat(3), probe=PROBE_HEAD % "Loop" + "def shown(n: Nat) -> String:\n  Document.plain(O.render({count: n}, Card.stranger()))\n")
        self.assertEqual(loop["value"]["value"], "Ticks: 3\n")

    def test_lines_split_the_rendered_document(self):
        reply = run_pure("Bell", "lineCount", nat(2), probe=BELL_PROBE)
        self.assertEqual(reply["status"], "finished", reply)
        self.assertEqual(reply["value"]["value"], "3")
        reply = run_pure("Document", "joined", nat(0), probe=LINES_PROBE)
        self.assertEqual(reply["value"]["value"], "alpha|beta gamma|delta|")

    def test_a_full_bell_card_shows_eight_rains_and_counts_the_rest(self):
        """A list holds at most 247 items (the host's data depth), so the fullest bell has 247
        rains; its card shows the first eight, elides the DIDs to their last segment and fits a
        reader's 1,400 characters, under the default budget."""
        full = run_pure("Bell", "many", nat(247), probe=BELL_PROBE)
        self.assertEqual(full["status"], "finished", full)
        text = full["value"]["value"]
        print("247 rains: card %s ticks, %d characters" % (full["ticksUsed"], len(text)))
        self.assertTrue(text.startswith("A silver bell planted by glm: a bell for lost moths (silent)\n"), text)
        self.assertEqual(text.count("author: a line of rain\n"), 8)
        self.assertTrue(text.endswith("… and 239 more\n"), text)
        self.assertLess(len(text), 1400)


NEGATIVE_PRELUDE = """edition ObjectiveBend 1
import ./World.obend as World
record Write:
  before: Nat
  after: Nat
"""


class Refusals(unittest.TestCase):
    def refused(self, body, entry, *names):
        reply = compile_job(closure("World") + [{"name": "Bad", "source": NEGATIVE_PRELUDE + body}], entry)
        self.assertEqual(reply["status"], "error", reply)
        self.assertTrue(any(n in reply["message"] for n in names), reply["message"][:400])

    def test_the_baseline_activity_without_nested_effects_compiles(self):
        reply = compile_job(closure("World") + [{"name": "Ok", "source": NEGATIVE_PRELUDE + """def bump(count: Nat) -> Activity<Nat>:
  match world.write({before: count, after: count + 1n}):
    case written(_): count + 1n
    case refused(_): count
"""}], "bump")
        self.assertEqual(reply["status"], "compiled", reply)

    def test_a_perform_inside_a_record_field_is_refused_as_effect_in_field(self):
        self.refused("""def bad(count: Nat) -> Activity<{seen: World.Written}>:
  {seen: world.write({before: count, after: count})}
""", "bad", "effect-in-field")

    def test_a_perform_inside_a_sum_payload_is_refused_as_effect_in_payload(self):
        self.refused("""sum Box:
  some: World.Written
def bad(count: Nat) -> Activity<Box>:
  Box.some(world.write({before: count, after: count}))
""", "bad", "effect-in-payload")

    def test_a_perform_inside_a_plan_is_refused_as_effect_in_plan(self):
        self.refused("""def bad(count: Nat) -> Activity<Nat>:
  match world.write(world.write({before: count, after: count})):
    case written(_): count
    case refused(_): count
""", "bad", "effect-in-plan")

    def test_a_perform_as_a_call_argument_is_refused_as_effect_as_argument(self):
        self.refused("""def keep(seen: World.Written) -> Nat:
  0n
def bad(count: Nat) -> Activity<Nat>:
  keep(world.write({before: count, after: count}))
""", "bad", "effect-as-argument")

    def test_a_perform_bound_by_let_is_refused_as_effect_in_let(self):
        self.refused("""def bad(count: Nat) -> Activity<Nat>:
  let seen = world.write({before: count, after: count})
  count
""", "bad", "effect-in-let")

    def test_a_world_call_outside_an_activity_is_refused_as_world_call_outside_activity(self):
        self.refused("""def bad(count: Nat) -> Nat:
  world.write({before: count, after: count})
""", "bad", "world-call-outside-activity")

    def test_an_activity_with_no_parameters_is_refused_as_nullary_activity(self):
        self.refused("""def bad() -> Activity<Nat>:
  match world.write({before: 0n, after: 1n}):
    case written(_): 1n
    case refused(_): 0n
""", "bad", "nullary-activity")

    def test_recursive_types_in_plans_and_responses_are_admitted(self):
        """The first checker refused any recursive type inside a Plan or Response
        with 'the checker refused the front end's typed packet'. The current
        binary admits them; this pins the new behaviour."""
        reply = compile_job(closure("World") + [{"name": "Rec", "source": """edition ObjectiveBend 1
import ./World.obend as World
sum L:
  nil: {}
  cons: {head: Nat, tail: L}
def f(n: Nat) -> Activity<Nat>:
  match world.call::<L>({object: {world: "", object: "x"}, method: "m", argument: {l: L.nil({})}}):
    case returned(_): n
    case _: 0n
"""}], "f")
        self.assertEqual(reply["status"], "compiled", reply)


if __name__ == "__main__":
    unittest.main()
