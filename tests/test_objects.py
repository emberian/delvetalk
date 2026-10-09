"""Compile and exercise the Bend standard library and the first objects.

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
    for sub in ("lib", "objects"):
        for directory, _, files in os.walk(os.path.join(WORLD, sub)):
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


def compile_job(modules, entry):
    return check({"op": "compile", "modules": modules, "entry": entry})


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

DOC_PROBE = """edition ObjectiveBend 1
import ./Document.obend as Document
def leaves(n: Nat) -> Document.Documents:
  match n:
    case 0: Document.Documents.nil()
    case 1+p: Document.Documents.cons({head: Document.text("abcdefgh"), tail: leaves(p)})
def flat(n: Nat) -> Nat:
  textLength(Document.plain(Document.Document.sequence({items: leaves(n)})))
"""

PROBE_HEAD = "edition ObjectiveBend 1\nimport ./List.obend as Lists\nimport ./Plan.obend as Plans\nimport ./Document.obend as Document\nimport ./%s.obend as O\n"

BELL_PROBE = PROBE_HEAD % "Bell" + """def rains(n: Nat) -> Lists.List<O.Rain>:
  match n:
    case 0: Lists.List::<O.Rain>.nil()
    case 1+previous: Lists.List::<O.Rain>.cons({head: {author: "author", text: "a line of rain"}, tail: rains(previous)})
def sample(rains: Lists.List<O.Rain>) -> O.State:
  {planter: "glm", colour: O.Colour.silver({}), seed: "a bell for lost moths", rains: rains, rung: false, door: {world: "", object: ""}, lastDelivery: "", planting: {principal: "", intent: ""}}
def many(n: Nat) -> String:
  O.card(sample(rains(n)))
def weight(n: Nat) -> Nat:
  Document.size(O.render(sample(rains(n))))
def lineCount(n: Nat) -> Nat:
  Lists.length::<String>(Document.lines(O.render(sample(rains(n)))))
def two(n: Nat) -> String:
  O.card(sample(Lists.append::<O.Rain>(Lists.append::<O.Rain>(Lists.List::<O.Rain>.nil(), {author: "kimik3", text: "first"}), {author: "gemini", text: "second"})))
"""

DOOR_PROBE = PROBE_HEAD % "Door" + """def shut(n: Nat) -> String:
  O.card({open: false, openedBy: "", knocks: Lists.List::<String>.cons({head: "glm", tail: Lists.List::<String>.nil()}), lantern: {world: "", object: ""}, lastDelivery: ""})
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
  O.card({entries: Lists.List::<Plans.Receipt>.cons({head: {slot: {principal: "glm", intent: "plant"}, height: 7n, outcome: Plans.Outcome.refused({class: "required-absence", root: "r1"})}, tail: Lists.List::<Plans.Receipt>.nil()})})
"""

ANTHOLOGY_PROBE = PROBE_HEAD % "Anthology" + """def one(n: Nat) -> String:
  O.card({proposals: Lists.List::<O.Proposal>.cons({head: {author: "glm", line: "moths", status: O.Status.proposed({})}, tail: Lists.List::<O.Proposal>.cons({head: {author: "kimik3", line: "lamps", status: O.Status.admitted({})}, tail: Lists.List::<O.Proposal>.nil()})})})
"""


class Library(unittest.TestCase):
    def test_every_module_compiles(self):
        for name in sorted(MODULES):
            entries = [d for d in definitions(name) if not d[1]]
            if not entries:
                continue
            with self.subTest(module=name):
                reply = compile_job(closure(name), entries[0][0])
                self.assertEqual(reply["status"], "compiled", reply)

    def test_one_context_record(self):
        owners = []
        for name, path in MODULES.items():
            with open(path) as handle:
                if re.search(r"^record Context:", handle.read(), re.M):
                    owners.append(name)
        self.assertEqual(owners, ["Abi"])

    def test_no_dynamic_value_universe(self):
        for name, path in MODULES.items():
            with open(path) as handle:
                self.assertNotIn("Preparation", handle.read(), name)


class Objects(unittest.TestCase):
    def activities(self):
        for name in sorted(MODULES):
            if MODULES[name].startswith(os.path.join(WORLD, "objects")):
                for entry, generic, result in definitions(name):
                    if result.startswith("Activity<"):
                        yield name, entry

    def test_activities_are_computations(self):
        seen = 0
        for name, entry in self.activities():
            with self.subTest(activity=name + "." + entry):
                reply = compile_job(closure(name), entry)
                self.assertEqual(reply["status"], "compiled", reply)
                comp = computation(reply["artifact"]["type"])
                self.assertEqual(comp["tag"], "computation")
                plans = row_names(comp["plan"]["row"])
                responses = row_names(comp["response"]["row"])
                print("%s.%s plan={%s} response={%s}" % (name, entry, ",".join(plans), ",".join(responses)))
                self.assertEqual(plans[:3], ["view", "write", "call"])
                for silence in ("reply", "refused", "unknown", "timedOut", "broken"):
                    self.assertIn(silence, responses)
                seen += 1
        self.assertGreaterEqual(seen, 20)

    def test_methods_perform_the_plans_they_claim(self):
        expected = {("Counter", "bump"): "write", ("Garden", "sow"): "create", ("Garden", "grow"): "create", ("Garden", "counted"): "write", ("Garden", "cistern"): "create",
                    ("Bell", "rain"): "write", ("Bell", "strike"): "await", ("Bell", "rung"): "write",
                    ("Cistern", "retain"): "write", ("Anthology", "submit"): "write", ("Anthology", "admitted"): "write",
                    ("Bell", "ring"): "write", ("Bell", "notify"): "send", ("Door", "open"): "write",
                    ("Door", "announce"): "send", ("Door", "knock"): "write", ("Lantern", "light"): "write",
                    ("Loop", "tick"): "write", ("Loop", "again"): "send"}
        for (name, entry), plan in expected.items():
            with open(MODULES[name]) as handle:
                source = handle.read()
            body = source[source.index("def %s(" % entry):].split("\ndef ")[0]
            self.assertIn("perform(Plan.%s(" % plan, body, (name, entry))

    def test_render_cards(self):
        counter = run_pure("Counter", "card", record(count=nat(3)))
        self.assertEqual(counter["value"]["value"], "Count: 3")
        garden = run_pure("Garden", "card", record(planted=nat(2)))
        self.assertEqual(garden["status"], "finished", garden)
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

    def test_every_object_exports_initial(self):
        for name in ("Counter", "Garden", "Bell", "Cistern", "Anthology"):
            with self.subTest(object=name):
                self.assertIn(("initial", False), [(d[0], d[1]) for d in definitions(name)])
                reply = compile_job(closure(name), "initial")
                self.assertEqual(reply["status"], "compiled", reply)

    def test_plain_is_not_quadratic(self):
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

    def test_chain_objects_render(self):
        door = run_pure("Door", "shut", nat(0), probe=DOOR_PROBE)
        self.assertEqual(door["status"], "finished", door)
        self.assertEqual(door["value"]["value"], "The door is shut.\nknock: glm\n")
        lantern = run_pure("Lantern", "card", record(lit={"tag": "boolean", "value": True}, litBy={"tag": "label", "value": "gemini"}))
        self.assertEqual(lantern["value"]["value"], "The lantern is lit by gemini.\n")
        loop = run_pure("Loop", "card", record(count=nat(3)))
        self.assertEqual(loop["value"]["value"], "Ticks: 3\n")

    def test_lines_split_the_rendered_document(self):
        reply = run_pure("Bell", "lineCount", nat(2), probe=BELL_PROBE)
        self.assertEqual(reply["status"], "finished", reply)
        self.assertEqual(reply["value"]["value"], "3")
        reply = run_pure("Document", "joined", nat(0), probe=LINES_PROBE)
        self.assertEqual(reply["value"]["value"], "alpha|beta gamma|delta|")

    def test_lines_cost_on_the_maximum_bell(self):
        """Document.lines over a 1,025-rain Bell card, generation included."""
        base = run_pure("Bell", "weight", nat(1025), probe=BELL_PROBE, limits=BIG)
        reply = run_pure("Bell", "lineCount", nat(1025), probe=BELL_PROBE, limits=BIG)
        self.assertEqual(reply["status"], "finished", reply)
        self.assertEqual(reply["value"]["value"], "1026")
        print("1025 rains: Document.lines %s ticks (Document.size %s, plain %s)" %
              (reply["ticksUsed"], base["ticksUsed"], 848680))

    def test_maximum_bell(self):
        """A Bell with 1,025 rains does not render under the default budget.

        The card Document (built and measured with the linear Document.size)
        costs about 310 ticks per rain: 256 rains fit, 1,025 cost 316,764 ticks
        and exhaust the default 100,000. The flat text card (Document.plain) is
        linear-ish now: 1,025 rains cost 848,680 ticks, 64 rains 43,000 (this
        was refused before the plain rewrite). Both finish under 1,000,000."""
        line = len("author: a line of rain\n")
        header = len("A silver bell planted by glm: a bell for lost moths (silent)\n")
        fits = run_pure("Bell", "weight", nat(256), probe=BELL_PROBE)
        self.assertEqual(fits["status"], "finished", fits)
        self.assertEqual(fits["value"]["value"], str(header + 256 * line))
        default = run_pure("Bell", "weight", nat(1025), probe=BELL_PROBE)
        self.assertEqual(default["status"], "refused", default)
        self.assertTrue(default["failure"].endswith("tickExhausted"), default)
        raised = run_pure("Bell", "weight", nat(1025), probe=BELL_PROBE, limits=BIG)
        self.assertEqual(raised["status"], "finished", raised)
        self.assertEqual(raised["value"]["value"], str(header + 1025 * line))
        flat64 = run_pure("Bell", "many", nat(64), probe=BELL_PROBE)
        self.assertEqual(flat64["status"], "finished", flat64)
        flat = run_pure("Bell", "many", nat(1025), probe=BELL_PROBE, limits=BIG)
        self.assertEqual(flat["status"], "finished", flat)
        self.assertTrue(flat["value"]["value"].endswith("author: a line of rain\n"))
        print("1025 rains: Document.size %s ticks, %s heap cells; plain card %s ticks; default budget refuses the first" %
              (raised["ticksUsed"], raised["heapCells"], flat["ticksUsed"]))


NEGATIVE_PRELUDE = """edition ObjectiveBend 1
record Write:
  before: Nat
  after: Nat
sum Plan:
  write: Write
sum Response:
  written: {}
  refused: {}
"""


class Refusals(unittest.TestCase):
    def refused(self, body, entry, *names):
        reply = compile_job([{"name": "Bad", "source": NEGATIVE_PRELUDE + body}], entry)
        self.assertEqual(reply["status"], "error", reply)
        self.assertTrue(any(n in reply["message"] for n in names), reply["message"][:400])

    def test_baseline_compiles(self):
        reply = compile_job([{"name": "Ok", "source": NEGATIVE_PRELUDE + """def bump(count: Nat) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({before: count, after: count + 1n})):
    case written(_): count + 1n
    case refused(_): count
"""}], "bump")
        self.assertEqual(reply["status"], "compiled", reply)

    def test_effect_in_field(self):
        self.refused("""def bad(count: Nat) -> Activity<Plan, Response, {seen: Response}>:
  {seen: perform(Plan.write({before: count, after: count}))}
""", "bad", "effect-in-field")

    def test_effect_in_payload(self):
        self.refused("""sum Box:
  some: Response
def bad(count: Nat) -> Activity<Plan, Response, Box>:
  Box.some(perform(Plan.write({before: count, after: count})))
""", "bad", "effect-in-payload")

    def test_effect_in_plan(self):
        self.refused("""def bad(count: Nat) -> Activity<Plan, Response, Nat>:
  match perform(perform(Plan.write({before: count, after: count}))):
    case written(_): count
    case refused(_): count
""", "bad", "effect-in-plan")

    def test_effect_as_argument(self):
        self.refused("""def keep(seen: Response) -> Nat:
  0n
def bad(count: Nat) -> Activity<Plan, Response, Nat>:
  keep(perform(Plan.write({before: count, after: count})))
""", "bad", "effect-as-argument")

    def test_effect_in_let(self):
        self.refused("""def bad(count: Nat) -> Activity<Plan, Response, Nat>:
  let seen = perform(Plan.write({before: count, after: count}))
  count
""", "bad", "effect-in-let")

    def test_perform_outside_activity(self):
        self.refused("""def bad(count: Nat) -> Nat:
  perform(Plan.write({before: count, after: count}))
""", "bad", "perform-outside-activity")

    def test_nullary_activity(self):
        self.refused("""def bad() -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({before: 0n, after: 1n})):
    case written(_): 1n
    case refused(_): 0n
""", "bad", "nullary-activity")

    def test_recursive_types_in_plans_and_responses_are_admitted(self):
        """The first checker refused any recursive type inside a Plan or Response
        with 'the checker refused the front end's typed packet'. The current
        binary admits them; this pins the new behaviour."""
        reply = compile_job([{"name": "Rec", "source": """edition ObjectiveBend 1
sum L:
  nil: {}
  cons: {head: Nat, tail: L}
sum P:
  a: {l: L}
sum R:
  ok: {l: L}
def f(n: Nat) -> Activity<P, R, Nat>:
  match perform(P.a({l: L.nil({})})):
    case ok(_): n
"""}], "f")
        self.assertEqual(reply["status"], "compiled", reply)


if __name__ == "__main__":
    unittest.main()
