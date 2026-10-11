"""The library holds one Context and no dynamic universe; objects claim the Plans they perform; cards
render in under 1,400 characters at their fullest.

Evidence for FOUNDATION §5 (layer: objects).

Compile and exercise the Bend standard library and the first objects.

Every module under world/lib and world/objects (and the fixtures in tests/fixtures/objects and examples/automatafl) goes through the real checker
binary (read-only, built elsewhere). Run from the repository root:

    python3 -m unittest tests.test_objects -v
"""
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
    for root in (os.path.join(WORLD, "lib"), os.path.join(WORLD, "objects"), os.path.join(ROOT, "tests", "fixtures", "objects"), os.path.join(ROOT, "examples", "automatafl")):
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
def long(n: Nat) -> String:
  match n:
    case 0: ""
    case 1+previous: textConcat("rain ", long(previous))
def longRains(n: Nat) -> Lists.List<O.Rain>:
  match n:
    case 0: Lists.List::<O.Rain>.nil()
    case 1+previous: Lists.List::<O.Rain>.cons({head: {author: "author", handle: "", text: long(56n), at: 1n, n: previous}, tail: longRains(previous)})
def wide(n: Nat) -> String:
  Document.plain(O.render(sample(longRains(n)), Card.stranger()))
def two(n: Nat) -> String:
  Document.plain(O.render(sample(Lists.append::<O.Rain>(Lists.append::<O.Rain>(Lists.List::<O.Rain>.nil(), {author: "kimik3", handle: "", text: "first", at: 1n, n: 0n}), {author: "gemini", handle: "", text: "second", at: 2n, n: 1n})), Card.stranger()))
"""

POLICY_PROBE = PROBE_HEAD % "Policy" + """import ./Policies.obend as Policies
def long(n: Nat) -> String:
  match n:
    case 0: ""
    case 1+previous: textConcat("words ", long(previous))
def examples(n: Nat) -> Lists.List<Policies.Example>:
  match n:
    case 0: Lists.List::<Policies.Example>.nil()
    case 1+previous: Lists.List::<Policies.Example>.cons({head: {utterance: long(40n), spell: long(40n)}, tail: examples(previous)})
def macros(n: Nat) -> Lists.List<Policies.Macro>:
  match n:
    case 0: Lists.List::<Policies.Macro>.nil()
    case 1+previous: Lists.List::<Policies.Macro>.cons({head: {name: "m", pattern: long(20n), expansion: long(40n)}, tail: macros(previous)})
def full(n: Nat) -> String:
  Document.plain(O.render({owner: "ember", model: "m", system: "s", lexicon: Lists.List::<Policies.Term>.nil(), examples: examples(n), escalate: "", escalateTo: "", macros: macros(n), confirmFor: Lists.List::<String>.nil()}, extend(Card.stranger(), {principal: "ember"})))
"""


class Objects(unittest.TestCase):


    def test_a_full_bell_card_shows_eight_rains_and_counts_the_rest(self):
        """A list holds at most 247 items (the host's data depth), so the fullest bell has 247
        rains; its card shows the first eight, elides the DIDs to their last segment and fits a
        reader's 1,400 characters, under the default budget."""
        full = run_pure("Bell", "many", nat(247), probe=BELL_PROBE)
        self.assertEqual(full["status"], "finished", full)
        text = full["value"]["value"]
        self.assertTrue(text.startswith("A silver bell, planted by glm: “a bell for lost moths” — silent.\n"), text)
        self.assertEqual(text.count("author: a line of rain\n"), 8)
        self.assertTrue(text.endswith("… and 239 more\n"), text)
        self.assertLess(len(text), 1400)

    def test_a_full_policy_card_fits_its_owner(self):
        """Sixteen examples and sixteen macros under the owner's teaching text stay under 1,400
        characters (WORLD-REVIEW 2: the policy's card had no clip)."""
        reply = run_pure("Policy", "full", nat(16), probe=POLICY_PROBE, limits=BIG)
        self.assertEqual(reply["status"], "finished", reply)
        text = reply["value"]["value"]
        self.assertLess(len(text), 1400, text)
        self.assertIn("To teach me a phrase", text)
        self.assertRegex(text, r"… and \d+ more\n$")

NEGATIVE_PRELUDE = """edition ObjectiveBend 1
import ./World.obend as World
record Write:
  before: Nat
  after: Nat
"""


REFUSED = [  # (body, the refusal's name): a perform anywhere but the head of an activity's match
    ("""def bad(count: Nat) -> Activity<{seen: World.Written}>:
  {seen: world.write({before: count, after: count})}
""", "effect-in-field"),
    ("""sum Box:
  some: World.Written
def bad(count: Nat) -> Activity<Box>:
  Box.some(world.write({before: count, after: count}))
""", "effect-in-payload"),
    ("""def bad(count: Nat) -> Activity<Nat>:
  match world.write(world.write({before: count, after: count})):
    case written(_): count
    case refused(_): count
""", "effect-in-plan"),
    ("""def keep(seen: World.Written) -> Nat:
  0n
def bad(count: Nat) -> Activity<Nat>:
  keep(world.write({before: count, after: count}))
""", "effect-as-argument"),
    ("""def bad(count: Nat) -> Activity<Nat>:
  let seen = world.write({before: count, after: count})
  count
""", "effect-in-let"),
    ("""def bad(count: Nat) -> Nat:
  world.write({before: count, after: count})
""", "world-call-outside-activity"),
    ("""def bad() -> Activity<Nat>:
  match world.write({before: 0n, after: 1n}):
    case written(_): 1n
    case refused(_): 0n
""", "nullary-activity"),
]


class Refusals(unittest.TestCase):
    def test_a_perform_outside_an_activitys_match_is_refused_by_name(self):
        for body, name in REFUSED:
            with self.subTest(name):
                reply = compile_job(closure("World") + [{"name": "Bad", "source": NEGATIVE_PRELUDE + body}], "bad")
                self.assertEqual(reply["status"], "error", reply)
                self.assertIn(name, reply["message"])


if __name__ == "__main__":
    unittest.main()


BUDGET_HEAD = "edition ObjectiveBend 1\nimport ./List.obend as Lists\nimport ./Plan.obend as Plans\nimport ./Document.obend as Document\nimport ./Card.obend as Card\nimport ./Relation.obend as Relations\n"
REPEAT = """def rep(n: Nat, s: String) -> String:
  match n:
    case 0: ""
    case 1+p: textConcat(s, rep(p, s))
"""
CLIPPED_PROBE = BUDGET_HEAD + REPEAT + """def one(n: Nat) -> String:
  Document.plain(Document.Document.sequence({items: Card.clipped(Document.Documents.cons({head: Document.text(textConcat(rep(599n, "a"), "\\n")), tail: Document.Documents.cons({head: Document.text(textConcat(rep(599n, "b"), "\\n")), tail: Document.Documents.cons({head: Document.text("c\\n"), tail: Document.Documents.nil()})})}), 8n)}))
"""
BELL_BUDGET_PROBE = BUDGET_HEAD + "import ./Bell.obend as O\n" + REPEAT + """def rains(n: Nat) -> Lists.List<O.Rain>:
  match n:
    case 0: Lists.List::<O.Rain>.nil()
    case 1+p: Lists.List::<O.Rain>.cons({head: {author: "did:plc:glm", handle: "", text: rep(280n, "r"), at: 1n, n: p}, tail: rains(p)})
def doors(n: Nat) -> Card.Doorways:
  match n:
    case 0: Card.Doorways.nil()
    case 1+p: Card.Doorways.cons({head: {label: textConcat(rep(31n, "d"), natText(p)), to: {world: "", object: rep(160n, "t")}}, tail: doors(p)})
def one(n: Nat) -> String:
  Document.plain(O.render({colour: O.Colour.silver({}), seed: rep(80n, "s"), rains: Relations.Relation.rows({items: rains(64n)}), rung: false, planting: "p", planter: "did:plc:glm", planterHandle: rep(64n, "h"), doors: doors(8n)}, Card.stranger()))
"""



class Budgets(unittest.TestCase):
    """A card keeps one character budget across its whole renderer (codex objects 14, 15)."""

    def text(self, name, probe):
        out = run_pure(name, "one", nat(0), probe=probe, limits=BIG)
        self.assertEqual(out["status"], "finished", out)
        return out["value"]["value"]

    def test_clipped_reserves_its_footer_within_the_budget(self):
        text = self.text("Lantern", CLIPPED_PROBE)
        self.assertLessEqual(len(text), 1200, text[-80:])
        self.assertTrue(text.endswith(" more\n"), text[-80:])

    def test_a_bell_with_eight_long_doors_and_long_rains_stays_under_1400(self):
        text = self.text("Bell", BELL_BUDGET_PROBE)
        self.assertLessEqual(len(text), 1400, (len(text), text[-200:]))
        self.assertIn("Doors: ", text)

