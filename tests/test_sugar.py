"""Surface sugar compiles to the packet of its explicit spelling and moves no receipt; a misuse is
refused by name with the spelling it means.

Evidence for FOUNDATION §8 Surface (layer: kernel).

Surface sugar without new semantics: each sugared form compiles to the packet of
its explicit spelling. A packet names its modules' source hashes (`sourceModules`),
so two spellings are compared on the packet without that one field; everything else
(term, annotations, types, bounds, entry) must be byte-identical. EQUIVALENT lists every
pair, REFUSED every misuse with the words its refusal must carry.

    python3 -m unittest tests.test_sugar -v
"""
import hashlib
import re
import json
import unittest

from tests.test_turn import Host, library_modules, nat, variant

HEAD = "edition ObjectiveBend 1\n"


def core(artifact):
    """The packet's digest without its source hashes."""
    packet = dict(artifact["packet"])
    packet.pop("sourceModules")
    return hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()


# A stand-in for world/lib/World.obend: the message and three world methods, so a sugared and
# an explicit spelling yield the same world calls without the world library's closure.
SUGAR_WORLD = HEAD + """record Reference:
  world: String
  object: String
record Message:
  object: Reference
  method: String
  argument: Data
record Edit:
  field: Nat
  after: Nat
sum Sent:
  delivery: {id: String}
  refused: {clause: String}
sum Reply:
  written: {}
  refused: {clause: String}
  later: {}
protocol world:
  send({object: Reference, method: String, argument: Data}) -> Sent
  put(Edit) -> Reply
"""


# A generic declaration in every package, so both spellings run the generics pass (an
# explicit `Data.of::<T>` is a specialization, and the pass adds its generated module
# to the package's metadata).
DATA_PLANS = HEAD + """import ./World.obend as World
sum Box<T>:
  box: {value: T}
record Note:
  text: String
  count: Nat
"""


# (name, explicit, sugared, entry): each pair must compile to the same packet.
DATA_PAIRS = [
    ("sum payload field",
     DATA_PLANS + "def tell(text: String) -> Activity<Nat>:\n"
     "  match world.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: Data.of::<{text: String}>({text: text})}):\n"
     "    case _: 1n\n",
     DATA_PLANS + "def tell(text: String) -> Activity<Nat>:\n"
     "  match world.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: {text: text}}):\n"
     "    case _: 1n\n",
     "tell"),
    ("named record value",
     DATA_PLANS + "def tell(note: Note) -> Activity<Nat>:\n"
     "  match world.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: Data.of::<Note>(note)}):\n"
     "    case _: note.count\n",
     DATA_PLANS + "def tell(note: Note) -> Activity<Nat>:\n"
     "  match world.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: note}):\n"
     "    case _: note.count\n",
     "tell"),
    ("call argument",
     DATA_PLANS + "def wrap(d: Data, n: Nat) -> Nat:\n  n\ndef f(n: Nat) -> Nat:\n  wrap(Data.of::<Nat>(n), n)\n",
     DATA_PLANS + "def wrap(d: Data, n: Nat) -> Nat:\n  n\ndef f(n: Nat) -> Nat:\n  wrap(n, n)\n",
     "f"),
    ("definition result",
     DATA_PLANS + "def nothing(n: Nat) -> Data:\n  Data.of::<{}>({})\n",
     DATA_PLANS + "def nothing(n: Nat) -> Data:\n  {}\n",
     "nothing"),
    ("both branches of an if",
     DATA_PLANS + "def pick(n: Nat) -> Data:\n  if n == 0n then Data.of::<String>(\"zero\") else Data.of::<Nat>(n)\n",
     DATA_PLANS + "def pick(n: Nat) -> Data:\n  if n == 0n then \"zero\" else n\n",
     "pick"),
]


LISTS_HEAD = HEAD + """import ./List.obend as Lists
import ./World.obend as World
record Rain:
  author: String
  text: String
record State:
  rains: Lists.List<Rain>
  count: Nat
def line(rain: Rain) -> String:
  rain.text
"""


# (name, explicit, sugared, entry)
GENERIC_PAIRS = [
    ("arguments fix both parameters",
     LISTS_HEAD + "def lines(state: State) -> Lists.List<String>:\n  Lists.map::<Rain, String>(state.rains, line)\n",
     LISTS_HEAD + "def lines(state: State) -> Lists.List<String>:\n  Lists.map(state.rains, line)\n",
     "lines"),
    ("a lambda's annotation",
     LISTS_HEAD + "def sizes(state: State) -> Lists.List<Nat>:\n  Lists.map::<Rain, Nat>(state.rains, fn(r: Rain) -> Nat: textLength(r.text))\n",
     LISTS_HEAD + "def sizes(state: State) -> Lists.List<Nat>:\n  Lists.map(state.rains, fn(r: Rain) -> Nat: textLength(r.text))\n",
     "sizes"),
    ("nested calls",
     LISTS_HEAD + "def count(state: State) -> Nat:\n  Lists.length::<String>(Lists.map::<Rain, String>(state.rains, line)) + Lists.length::<Rain>(state.rains)\n",
     LISTS_HEAD + "def count(state: State) -> Nat:\n  Lists.length(Lists.map(state.rains, line)) + Lists.length(state.rains)\n",
     "count"),
    ("constructor from its head",
     LISTS_HEAD + "def one(rain: Rain, state: State) -> Lists.List<Rain>:\n  Lists.List::<Rain>.cons({head: rain, tail: state.rains})\n",
     LISTS_HEAD + "def one(rain: Rain, state: State) -> Lists.List<Rain>:\n  Lists.List.cons({head: rain, tail: state.rains})\n",
     "one"),
    ("constructor from the expected type",
     LISTS_HEAD + "def fresh(n: Nat) -> State:\n  {rains: Lists.List::<Rain>.nil({}), count: n}\n",
     LISTS_HEAD + "def fresh(n: Nat) -> State:\n  {rains: Lists.List.nil({}), count: n}\n",
     "fresh"),
    ("a literal head with a declared tail",
     LISTS_HEAD + "def said(text: String, state: State) -> Lists.List<Rain>:\n  Lists.List::<Rain>.cons({head: {author: \"me\", text: text}, tail: state.rains})\n",
     LISTS_HEAD + "def said(text: String, state: State) -> Lists.List<Rain>:\n  Lists.List.cons({head: {author: \"me\", text: text}, tail: state.rains})\n",
     "said"),
    ("an activity's result type",
     LISTS_HEAD + "def wrote<T>(state: State, then: Nat -> T) -> Activity<T>:\n"
     "  match world.put({field: state.count + 1n, after: 0n}):\n    case _: then(state.count)\n"
     "def bump(state: State, n: Nat) -> Activity<Nat>:\n"
     "  wrote::<Nat>(state, fn(c: Nat) -> Nat: c + n)\n",
     LISTS_HEAD + "def wrote<T>(state: State, then: Nat -> T) -> Activity<T>:\n"
     "  match world.put({field: state.count + 1n, after: 0n}):\n    case _: then(state.count)\n"
     "def bump(state: State, n: Nat) -> Activity<Nat>:\n"
     "  wrote(state, fn(c: Nat) -> Nat: c + n)\n",
     "bump"),
    ("inside a generic body",
     LISTS_HEAD + "def twice<T>(items: Lists.List<T>) -> Nat:\n  Lists.length::<T>(items) + Lists.length::<T>(items)\n"
     "def f(state: State) -> Nat:\n  twice::<Rain>(state.rains)\n",
     LISTS_HEAD + "def twice<T>(items: Lists.List<T>) -> Nat:\n  Lists.length(items) + Lists.length(items)\n"
     "def f(state: State) -> Nat:\n  twice(state.rains)\n",
     "f"),
]


TURN_HEAD = HEAD + """import ./World.obend as World
"""


BUMP_SUGARED = TURN_HEAD + """def bump(count: Nat) -> Activity<Nat>:
  let written(_) = world.put({field: 0n, after: count + 1n})
  let next = count + 1n
  next
"""


# The match the statement lowers to: one refusal arm per label it does not name.
BUMP_EXPLICIT = TURN_HEAD + """def bump(count: Nat) -> Activity<Nat>:
  match world.put({field: 0n, after: count + 1n}):
    case written(_):
      let next = count + 1n
      next
    case refused(_): refuse("unexpected response refused")
    case later(_): refuse("unexpected response later")
"""


# Two statements in a row, the second binding its payload.
TWICE_SUGARED = TURN_HEAD + """def twice(count: Nat) -> Activity<String>:
  let written(_) = world.put({field: 0n, after: count})
  let refused(r) = world.put({field: 1n, after: count})
  r.clause
"""


TWICE_EXPLICIT = TURN_HEAD + """def twice(count: Nat) -> Activity<String>:
  match world.put({field: 0n, after: count}):
    case written(_):
      match world.put({field: 1n, after: count}):
        case refused(r): r.clause
        case written(_): refuse("unexpected response written")
        case later(_): refuse("unexpected response later")
    case refused(_): refuse("unexpected response refused")
    case later(_): refuse("unexpected response later")
"""


SCENE = HEAD + """record State:
  title: String
  count: Nat
"""


# (name, explicit, sugared, entry)
TEXT_PAIRS = [
    ("two pieces", SCENE + "def f(s: State) -> String:\n  textConcat(\"SCENE \", s.title)\n",
     SCENE + "def f(s: State) -> String:\n  \"SCENE {s.title}\"\n", "f"),
    ("four pieces, right-nested",
     SCENE + "def f(s: State) -> String:\n  textConcat(\"SCENE \", textConcat(s.title, textConcat(\": \", natText(s.count))))\n",
     SCENE + "def f(s: State) -> String:\n  \"SCENE {s.title}: {natText(s.count)}\"\n", "f"),
    ("five pieces, joined",
     SCENE + "def f(s: State) -> String:\n  textJoin(TextPieces.cons({head: \"SCENE \", tail: TextPieces.cons({head: s.title, tail: "
     "TextPieces.cons({head: \" (\", tail: TextPieces.cons({head: natText(s.count), tail: TextPieces.cons({head: \" here)\", "
     "tail: TextPieces.nil({})})})})})}), \"\")\n",
     SCENE + "def f(s: State) -> String:\n  \"SCENE {s.title} ({natText(s.count)} here)\"\n", "f"),
    ("doubled braces and an escaped literal inside",
     SCENE + "def f(s: State) -> String:\n  textConcat(\"{{\", textConcat(textConcat(s.title, \"!\"), \"}}\"))\n",
     SCENE + "def f(s: State) -> String:\n  \"{{{textConcat(s.title, \\\"!\\\")}}}\"\n", "f"),
]


FORM_HEAD = HEAD + "import ./List.obend as Lists\nimport ./Form.obend as F\n"


FORM_EXPLICIT = FORM_HEAD + """def planting() -> F.Form:
  {card: "", action: "plant", fields: F.Fields.cons({head: {name: "colour", kind: F.Kind.choice({options: F.Names.cons({head: "amber", tail: F.Names.cons({head: "violet", tail: F.Names.cons({head: "silver", tail: F.Names.nil({})})})})})}, tail: F.Fields.cons({head: {name: "seed", kind: F.Kind.text({min: 1n, max: 80n})}, tail: F.Fields.cons({head: {name: "count", kind: F.Kind.natural({min: 1n, max: 1000n})}, tail: F.Fields.nil({})})})})}
def forms() -> Lists.List<F.Form>:
  Lists.List.cons({head: planting(), tail: Lists.List.nil({})})
"""


FORM_SUGARED = FORM_HEAD + """form plant as planting:
  colour: amber | violet | silver
  seed: text 1..80
  count: natural 1..1000n
"""


GARDEN = HEAD + """import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as P
import ./World.obend as World
record State:
  planted: Nat
  children: Lists.List<P.Reference>
  note: String
def plant(state: State, input: {child: P.Reference, note: String}, context: Abi.Context) -> Activity<Nat>:
"""


WRITE_EXPLICIT = GARDEN + """  let written(_) = world.write(extend(keep(), {planted: P.Edit::<Nat, Nat>.add({delta: 1n}), children: P.Entries::<P.Reference, P.Reference>.append({item: input.child}), note: P.Edit::<String, {}>.set({value: input.note})}))
  state.planted + 1n
"""


WRITE_SUGARED = GARDEN + """  let written(_) = write {planted: add 1n, children: append input.child, note: set input.note}
  state.planted + 1n
"""


# KERNEL-HANDOFF §16 item 8c: a form block declares its method's input record and, without a
# hand-written forms(), forms() of the blocks in source order.
FORM_STATE = FORM_HEAD + """sum Colour:
  amber: {}
  violet: {}
  silver: {}
record State:
  planted: Nat
def plant(state: State, input: PlantInput) -> Nat:
  state.planted + input.count
def water(state: State, input: WaterInput) -> Nat:
  textLength(input.note)
"""


FORM_BLOCKS = """form plant as planting:
  colour: amber | violet | silver
  seed: text 1..80
  count: natural 1..1000
form water:
  note: text 0..40
  shade: Colour
"""


FORM_BLOCKS_EXPLICIT = """def planting() -> F.Form:
  {card: "", action: "plant", fields: F.Fields.cons({head: {name: "colour", kind: F.Kind.choice({options: F.Names.cons({head: "amber", tail: F.Names.cons({head: "violet", tail: F.Names.cons({head: "silver", tail: F.Names.nil({})})})})})}, tail: F.Fields.cons({head: {name: "seed", kind: F.Kind.text({min: 1n, max: 80n})}, tail: F.Fields.cons({head: {name: "count", kind: F.Kind.natural({min: 1n, max: 1000n})}, tail: F.Fields.nil({})})})})}
def waterForm() -> F.Form:
  {card: "", action: "water", fields: F.Fields.cons({head: {name: "note", kind: F.Kind.text({min: 0n, max: 40n})}, tail: F.Fields.cons({head: {name: "shade", kind: F.Kind.choice({options: F.Names.cons({head: "amber", tail: F.Names.cons({head: "violet", tail: F.Names.cons({head: "silver", tail: F.Names.nil({})})})})})}, tail: F.Fields.nil({})})})}
"""


FORM_INPUTS_EXPLICIT = """sum PlantColour:
  amber: {}
  violet: {}
  silver: {}
record PlantInput:
  colour: PlantColour
  seed: String
  count: Nat
record WaterInput:
  note: String
  shade: Colour
def forms() -> Lists.List<F.Form>:
  Lists.List.cons({head: planting(), tail: Lists.List.cons({head: waterForm(), tail: Lists.List.nil({})})})
"""


ROWS = HEAD + """import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as P
import ./Relation.obend as Relations
import ./World.obend as World
record Row:
  at: Nat
  text: String
record State:
  rows: Relations.Relation<Row>
def plant(state: State, input: {at: Nat}, context: Abi.Context) -> Activity<Nat>:
"""


RELATIONS = HEAD + """import ./List.obend as Lists
record Decl:
  field: String
  key: Lists.List<String>
record State:
  rains: Lists.List<{author: String, at: Nat, text: String}>
def relations() -> Lists.List<Decl>:
  Lists.List.cons({head: {field: "rains", key: Lists.List.cons({head: "author", tail: Lists.List.cons({head: "at", tail: Lists.List.nil({})})})}, tail: Lists.List.nil({})})
def initial() -> State:
  {rains: Lists.List.nil({})}
"""


# KERNEL-HANDOFF §16 item 8a: a module with a State and the Plan library and neither `Edits` nor
# `keep` gets both, at the end of the module: lists and relations `Entries<X, X>`, a Nat `Edit<Nat, Nat>`,
# anything else `Edit<T, {}>`; `keep()` keeps every field.
DERIVED_HEAD = HEAD + """import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as P
import ./Relation.obend as Relations
import ./World.obend as World
record Row:
  at: Nat
  text: String
type Names = Lists.List<String>
record State:
  planted: Nat
  children: Lists.List<P.Reference>
  names: Names
  rows: Relations.Relation<Row>
  note: String
  open: Bool
  owner: P.Reference
"""


DERIVED_PAIR = """record Edits:
  planted: P.Edit<Nat, Nat>
  children: P.Entries<P.Reference, P.Reference>
  names: P.Entries<String, String>
  rows: P.Entries<Row, Row>
  note: P.Edit<String, {}>
  open: P.Edit<Bool, {}>
  owner: P.Edit<P.Reference, {}>
def keep() -> Edits:
  {planted: P.Edit.keep({}), children: P.Entries.keep({}), names: P.Entries.keep({}), rows: P.Entries.keep({}), note: P.Edit.keep({}), open: P.Edit.keep({}), owner: P.Edit.keep({})}
"""


DERIVED_REST = """def initial() -> State:
  {planted: 0n, children: Lists.List.nil({}), names: Lists.List.nil({}), rows: Relations.empty(), note: "", open: false, owner: P.nobody()}
def plant(state: State, input: {child: P.Reference, at: Nat, name: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {planted: add 1n, children: append input.child, names: amend input.name with "{input.name}!", rows: upsert {at: input.at, text: input.name}, open: set true}
  state.planted + 1n
"""


def without_state(source):
    """The module with its State renamed (and nothing fixed), so a hand-written Edits and keep()
    are its own: the explicit spelling a derived pair is compared against."""
    return re.sub(r"(?<![.\w])State\b", "Shape", source).replace(": fixed ", ": ")


# A `fixed` State field is set by initial() or a seed only: the derived Edits omits it, the
# artifact lists it, and no write names it.
FIXED_HEAD = DERIVED_HEAD.replace("  note: String\n", "  note: fixed String\n").replace("  owner: P.Reference\n", "  owner: fixed P.Reference\n")


FIXED_PAIR = """record Edits:
  planted: P.Edit<Nat, Nat>
  children: P.Entries<P.Reference, P.Reference>
  names: P.Entries<String, String>
  rows: P.Entries<Row, Row>
  open: P.Edit<Bool, {}>
def keep() -> Edits:
  {planted: P.Edit.keep({}), children: P.Entries.keep({}), names: P.Entries.keep({}), rows: P.Entries.keep({}), open: P.Edit.keep({})}
"""


ABI_LIB = ("Abi", "List", "World")
REL_LIB = ("Abi", "List", "World", "Relation")
FORM_LIB = ("List", "Form")


def modules(source, library=(), world=False, extra=()):
    """The library from world/lib, the stand-in World when `world`, any extra modules, then the package."""
    return (library_modules(*library) + ([{"name": "World", "source": SUGAR_WORLD}] if world else [])
            + list(extra) + [{"name": "Package", "source": source}])


def edit(sugared, explicit):
    """A `write {...}` in Garden.plant and the world.write it spells."""
    return (GARDEN + "  let written(_) = world.write(extend(keep(), {%s}))\n  state.planted\n" % explicit,
            GARDEN + "  let written(_) = write {%s}\n  state.planted\n" % sugared)


ALIAS_LIB = {"name": "Lib", "source": ROWS.split("def plant")[0]}
ALIAS_HEAD = (HEAD + "import ./Abi.obend as Abi\nimport ./Plan.obend as P\nimport ./World.obend as World\n"
              "import ./Lib.obend as Lib\ntype State = Lib.State\n"
              "def plant(state: State, input: {at: Nat}, context: Abi.Context) -> Activity<Nat>:\n")
ROWS_ALIASED = ROWS.replace("record State:\n  rows: Relations.Relation<Row>\n",
                            "type Rows = Relations.Relation<Row>\nrecord State:\n  rows: Rows\n")
REMOVE = "  let written(_) = write {rows: remove {at: input.at}}\n  0n\n"
RETRACT = "  let written(_) = world.write(extend(keep(), {rows: P.Entries::<%s, %s>.retract({key: {at: input.at}})}))\n  0n\n"
OTHER_LIB = {"name": "Lib", "source": HEAD + "import ./List.obend as Lists\nimport ./Plan.obend as P\nrecord Exit:\n  label: String\n"
             "record State:\n  exits: Lists.List<Exit>\n  count: Nat\n  name: String\n"}
OTHER = (HEAD + "import ./Abi.obend as Abi\nimport ./List.obend as Lists\nimport ./Plan.obend as P\n"
         "import ./World.obend as World\nimport ./Lib.obend as Lib\ntype State = Lib.State\n"
         "def go(state: State, input: {label: String}, context: Abi.Context) -> Activity<Nat>:\n"
         "  let written(_) = write {exits: append {label: input.label}, count: add 1n, name: set input.label}\n  0n\n")
OTHER_WRITTEN = without_state(OTHER) + ("record Edits:\n  exits: P.Entries<Lib.Exit, Lib.Exit>\n  count: P.Edit<Nat, Nat>\n"
                                        "  name: P.Edit<String, {}>\ndef keep() -> Edits:\n"
                                        "  {exits: P.Entries.keep({}), count: P.Edit.keep({}), name: P.Edit.keep({})}\n")
OWN_FORMS = "def forms() -> Lists.List<F.Form>:\n  Lists.List.cons({head: waterForm(), tail: Lists.List.nil({})})\n"
INPUTS = FORM_INPUTS_EXPLICIT[:FORM_INPUTS_EXPLICIT.index("def forms()")]

# (what, explicit, sugared, entries, library, world, extra): each pair compiles to one packet.
EQUIVALENT = (
    [("Data injection: " + n, e, s, (entry,), (), True, ()) for n, e, s, entry in DATA_PAIRS]
    + [("inferred type arguments: " + n, e, s, (entry,), ("List",), True, ()) for n, e, s, entry in GENERIC_PAIRS]
    + [("let-response", BUMP_EXPLICIT, BUMP_SUGARED, ("bump",), (), True, ()),
       ("two let-responses", TWICE_EXPLICIT, TWICE_SUGARED, ("twice",), (), True, ())]
    + [("interpolation: " + n, e, s, (entry,), (), False, ()) for n, e, s, entry in TEXT_PAIRS]
    + [("a form block", FORM_EXPLICIT, FORM_SUGARED, ("planting",), FORM_LIB, False, ()),
       ("form blocks: values, inputs and the derived forms()", FORM_STATE + FORM_BLOCKS_EXPLICIT + FORM_INPUTS_EXPLICIT,
        FORM_STATE + FORM_BLOCKS, ("plant", "water", "planting", "waterForm", "forms"), FORM_LIB, False, ()),
       ("a hand-written forms() is kept", FORM_STATE + FORM_BLOCKS_EXPLICIT + INPUTS + OWN_FORMS,
        FORM_STATE + FORM_BLOCKS + OWN_FORMS, ("forms",), FORM_LIB, False, ()),
       ("write {...}", WRITE_EXPLICIT, WRITE_SUGARED, ("plant",), ABI_LIB, False, ())]
    # RELATIONAL section 3: insert/upsert/retract; `remove ITEM` is removeItem, `amend ITEM with CHANGE` amendItem.
    + [("write " + s.split(": ")[1].split(" ")[0], *edit(s, x), ("plant",), ABI_LIB, False, ()) for s, x in (
        ("children: insert input.child", "children: P.Entries::<P.Reference, P.Reference>.insert({row: input.child})"),
        ("children: upsert input.child", "children: P.Entries::<P.Reference, P.Reference>.upsert({row: input.child})"),
        ("children: retract {object: input.note}", "children: P.Entries::<P.Reference, P.Reference>.retract({key: {object: input.note}})"),
        ("children: remove input.child", "children: P.Entries::<P.Reference, P.Reference>.removeItem({item: input.child})"),
        ("children: amend input.child with input.child",
         "children: P.Entries::<P.Reference, P.Reference>.amendItem({item: input.child, change: input.child})"))]
    # remove on a relation is a retract by key, through `type State = Lib.State` and a field alias too (review kernel 6).
    + [("remove on a relation", ROWS + RETRACT % ("Row", "Row"), ROWS + REMOVE, ("plant",), REL_LIB, False, ()),
       ("remove through a State alias", ALIAS_HEAD + RETRACT % ("Lib.Row", "Lib.Row"), ALIAS_HEAD + REMOVE, ("plant",), REL_LIB, False, (ALIAS_LIB,)),
       ("remove through a field alias", ROWS_ALIASED + RETRACT % ("Row", "Row"), ROWS_ALIASED + REMOVE, ("plant",), REL_LIB, False, ()),
       ("derived Edits and keep()", without_state(DERIVED_HEAD + DERIVED_REST + DERIVED_PAIR), DERIVED_HEAD + DERIVED_REST,
        ("plant", "keep", "initial"), REL_LIB, False, ()),
       ("derived Edits of another module's State", OTHER_WRITTEN, OTHER, ("go",), REL_LIB, False, (OTHER_LIB,)),
       ("fixed fields: the pair that omits them", without_state(FIXED_HEAD + DERIVED_REST + FIXED_PAIR), FIXED_HEAD + DERIVED_REST,
        ("plant", "keep", "initial"), REL_LIB, False, ())])

WRITES = ("write", "remove", "derived", "fixed")

WORDS = "def wrap(d: Data, n: Nat) -> Nat:\n  n\n"
BUMP = "def bump(state: State, context: Abi.Context) -> Activity<Nat>:\n  let written(_) = write {planted: add 1n}\n  0n\n"
FIXED_LAYER = ("layer over ./Base.obend\n" + HEAD + "import ./Abi.obend as Abi\nimport ./Plan.obend as P\nimport ./World.obend as World\n"
               "def retitle(state: Super.State, input: {}, context: Abi.Context) -> Activity<Nat>:\n"
               "  let written(_) = world.write::<Super.Edits>({note: P.Edit.set({value: \"\"})})\n  state.planted\n")
RELATIONS_BOUNDED = (RELATIONS.replace("  key: Lists.List<String>\n", "  key: Lists.List<String>\n  limit: Nat\n  retain: String\n")
                     .replace("tail: Lists.List.nil({})})})}, tail", "tail: Lists.List.nil({})})}), limit: 64n, retain: \"dropOldest\"}, tail"))
FIXED_REFUSAL = "refused (fixed): note is fixed; no edit names it"

# (source, entry, library, world, extra, words the refusal carries); None: the package checks.
REFUSED = [
    (DATA_PLANS + WORDS + "def f(n: Nat) -> Nat:\n  wrap(fn(x: Nat) -> Nat: x, n)\n", "f", (), True, (),
     ["refused (data-injection): this value is a function"]),
    (DATA_PLANS + "def go(n: Nat) -> Activity<Nat>:\n  match world.send({object: {world: \"\", object: \"b\"}, method: \"m\", argument: {}}):\n"
     "    case _: n\n" + WORDS + "def f(n: Nat) -> Nat:\n  wrap(go(n), n)\n", "f", (), True, (),
     ["refused (data-injection): this value is an Activity"]),
    # Neither the argument (a nil of no known type) nor the position fixes T.
    (LISTS_HEAD + "def zero(n: Nat) -> Nat:\n  Lists.length(Lists.List.nil({}))\n", "zero", ("List",), True, (),
     ["cannot infer the type argument T of Lists.length (line 13)", "write Lists.length::<T>(...) naming T"]),
    # kept<T, U> never mentions T: the refusal shows what was inferred.
    (LISTS_HEAD + "def kept<T, U>(found: Lists.Maybe<U>, rest: Lists.List<U>) -> Lists.List<U>:\n  rest\n"
     "def pick(state: State) -> Lists.List<Rain>:\n  kept(Lists.Maybe.none({}), state.rains)\n", "pick", ("List",), True, (),
     ["cannot infer the type argument T of kept", "write kept::<T, Rain>(...) naming T"]),
    (TURN_HEAD + "def pick(reply: World.Reply) -> Activity<Nat>:\n  let written(_) = reply\n  1n\n", "pick", (), True, (),
     ["refused (let-response)"]),
    (TURN_HEAD + "def f(n: Nat) -> Nat:\n  refuse(\"no\")\n", "f", (), True, (), ["refused (refuse-outside-activity)"]),
    (TURN_HEAD + "def g(n: Nat) -> Activity<Nat>:\n  if refuse(\"no\") then n else 0n\n", "g", (), True, (), ["refused (refuse-outside-tail)"]),
    *[(SCENE + "def f(s: State) -> String:\n  " + text + "\n", "f", (), False, (), [words])
      for text, words in (("\"a {s.title\"", "is not closed"), ("\"a } b\"", "written }}"), ("\"a {s.title s.title}\"", "holds one expression"))],
    (HEAD + "form plant:\n  seed: text 1..80\n", "plantForm", FORM_LIB, False, (), ["a form block needs the Form library"]),
    (FORM_HEAD + "form plant:\n  seed: words 1..80\n", "plantForm", FORM_LIB, False, (),
     ["a form field is `name: text MIN..MAX`", "`name: source`"]),
    (FORM_HEAD + "form plant:\n  seed: text 1..80\n", "plantForm", FORM_LIB, False, (), None),  # the default name
    (FORM_STATE.replace("record State:", "sum Mixed:\n  one: {}\n  two: {n: Nat}\nrecord State:") + FORM_BLOCKS.replace("shade: Colour", "shade: Mixed"),
     "plant", FORM_LIB, False, (), ["refused (form-kind): form water offers shade: Mixed, which is not a closed sum of empty cases"]),
    (FORM_STATE.replace("input: PlantInput", "input: {count: Nat}") + FORM_BLOCKS, "plant", FORM_LIB, False, (),
     ["refused (form-input): plant has a form block, so its input is PlantInput"]),
    (FORM_STATE.replace("def water(state: State, input: WaterInput)", "def water(state: State)").replace("textLength(input.note)", "0n") + FORM_BLOCKS,
     "water", FORM_LIB, False, (), ["so its input is WaterInput"]),
    # A block without fields: the method takes no input, or `{}`.
    (FORM_STATE + FORM_BLOCKS + "form ring:\ndef ring(state: State) -> Nat:\n  0n\n", "ring", FORM_LIB, False, (), None),
    (FORM_STATE + FORM_BLOCKS + "form ring:\ndef ring(state: State, input: {}) -> Nat:\n  0n\n", "ring", FORM_LIB, False, (), None),
    (FORM_STATE + FORM_BLOCKS + "record PlantInput:\n  count: Nat\n", "plant", FORM_LIB, False, (),
     ["refused (form-input): form plant declares PlantInput, its method's input, and so does the module"]),
    (WRITE_SUGARED.replace("add 1n", "bump 1n"), "plant", ABI_LIB, False, (),
     ["takes add, set, append, remove, amend, removeItem, insert, upsert or retract, not bump"]),
    (GARDEN + "  let written(_) = write {children: remove {index: 0n}}\n  state.planted\n", "plant", ABI_LIB, False, (),
     ["names a position, and edits name items", "children: remove ITEM"]),
    (DERIVED_HEAD + "record Edits:\n  planted: P.Edit<Nat, Nat>\n" + BUMP, "bump", REL_LIB, False, (),
     ["refused (derived-edits): Edits is derived from State; delete this declaration"]),
    (DERIVED_HEAD + "def keep() -> Edits:\n  {planted: P.Edit.keep({})}\n" + BUMP, "bump", REL_LIB, False, (),
     ["refused (derived-edits): keep() is derived from State; delete this declaration"]),
    (HEAD + "import ./List.obend as Lists\nimport ./Plan.obend as P\nimport ./Outer.obend as Outer\nrecord State:\n  items: Outer.Items\n",
     "keep", REL_LIB, False, ({"name": "Inner", "source": HEAD + "record Item:\n  n: Nat\n"},
                              {"name": "Outer", "source": HEAD + "import ./List.obend as Lists\nimport ./Inner.obend as Inner\ntype Items = Lists.List<Inner.Item>\n"}),
     ["refused (derived-edits): State.items holds items of a type from a module Package does not import"]),
    (HEAD + "import ./Abi.obend as Abi\nrecord State:\n  count: Nat\n"
     "def bump(state: State, context: Abi.Context) -> Activity<Nat>:\n  let written(_) = write {count: add 1n}\n  0n\n", "bump", ("Abi",), False, (),
     ["refused (derived-edits): write {...} and keep() derive Edits from State through the Plan library"]),
    (FIXED_HEAD + DERIVED_REST.replace("open: set true}", "open: set true, note: set input.name}"), "plant", REL_LIB, False, (), [FIXED_REFUSAL]),
    (FIXED_HEAD + DERIVED_REST.replace("let written(_) = write {", "let written(_) = world.write({note: P.Edit.set({value: \"\"})})\n  let again(_) = write {"),
     "plant", REL_LIB, False, (), [FIXED_REFUSAL]),
    (FIXED_LAYER, "retitle", REL_LIB, False, ({"name": "Base", "source": FIXED_HEAD + DERIVED_REST},), [FIXED_REFUSAL]),
    (DERIVED_HEAD.replace("  text: String\n", "  text: fixed String\n") + DERIVED_REST, "plant", REL_LIB, False, (),
     ["refused (fixed): only a State field is fixed; text is a field of Row"]),
]


class Sugar(unittest.TestCase):
    independent = True  # one shared host per process; tests/run.py deals the tests into chunks
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def compiled(self, source, entry, library=(), world=False, extra=()):
        reply = self.h.send({"op": "compile", "entry": entry, "modules": modules(source, library, world, extra)})
        self.assertEqual(reply["status"], "compiled", reply)
        return reply["artifact"]

    def test_each_expression_and_form_sugar_compiles_to_the_packet_of_its_explicit_spelling(self):
        self.equivalent([e for e in EQUIVALENT if not e[0].startswith(WRITES)])

    def test_each_write_and_derived_edit_compiles_to_the_packet_of_its_explicit_spelling(self):
        self.equivalent([e for e in EQUIVALENT if e[0].startswith(WRITES)])

    def equivalent(self, pairs):
        for what, explicit, sugared, entries, library, world, extra in pairs:
            for entry in entries:
                with self.subTest(sugar=what, entry=entry):
                    a = self.compiled(explicit, entry, library, world, extra)
                    b = self.compiled(sugared, entry, library, world, extra)
                    self.assertEqual(core(a), core(b))
                    self.assertEqual(a["type"], b["type"])
                    if what.startswith("inferred"):  # instance records name source hashes and spans; their names agree
                        self.assertEqual([i["name"] for i in a["genericInstances"]], [i["name"] for i in b["genericInstances"]])
                    if what.startswith("fixed"):
                        self.assertEqual(b["fixed"], ["note", "owner"])
        self.assertNotIn("fixed", self.compiled(DERIVED_HEAD + DERIVED_REST, "plant", REL_LIB))

    def test_each_misuse_is_refused_by_name(self):
        for source, entry, library, world, extra, words in REFUSED:
            with self.subTest(source=source[-120:], entry=entry):
                reply = self.h.send({"op": "check-package", "entry": entry, "modules": modules(source, library, world, extra)})
                if words is None:
                    self.assertEqual(reply["status"], "checked", reply)
                    continue
                self.assertEqual(reply["status"], "refused", reply)
                for w in words:
                    self.assertIn(w, reply["diagnostic"]["message"])
        d = self.h.send({"op": "check-package", "entry": "plant", "modules": modules(
            FORM_STATE.replace("input: PlantInput", "input: {count: Nat}") + FORM_BLOCKS, FORM_LIB)})["diagnostic"]
        self.assertEqual((d["definition"], d["expected"], d["found"]), ("Package.plant", "PlantInput", "{count: Nat}"))
        bad = self.h.send({"op": "compile", "entry": "initial", "modules": modules(
            RELATIONS_BOUNDED.replace("  limit: Nat\n", "  limit: String\n").replace("limit: 64n", "limit: \"many\""), ("List",))})
        self.assertEqual(bad["status"], "error", bad)
        self.assertIn("relations(): a limit is a Nat", bad["message"])

    def test_each_derived_refusal_names_its_source_line(self):
        # `compile` does not localize (check-package's `localize` recompiles each function alone to
        # find a spanless refusal): a span here is the generics pass's own (KERNEL-HANDOFF §16 item 9).
        tags = ("refused (fixed): note", "refused (form-kind)", "refused (form-input): form", "refused (derived-edits): State.")
        seen = set()
        for source, entry, library, world, extra, words in REFUSED:
            if not words or not words[0].startswith(tags):
                continue
            with self.subTest(refusal=words[0]):
                reply = self.h.send({"op": "compile", "entry": entry, "modules": modules(source, library, world, extra)})
                self.assertEqual(reply["status"], "error", reply)
                d = json.loads(reply["message"])
                self.assertIn(words[0], d["message"])
                self.assertIn("line", d.get("span", {}), d)
                self.assertTrue(d.get("module"), d)
                line = (modules(source, library, world, extra)[-1]["source"] if d["module"] == "Package" else
                        next(m["source"] for m in modules(source, library, world, extra) if m["name"] == d["module"])).split("\n")[d["span"]["line"] - 1]
                if "form-kind" in words[0]:
                    self.assertIn("shade: Mixed", line)
                if "declares PlantInput" in words[0]:
                    self.assertIn("record PlantInput", line)
                if "State.items" in words[0]:
                    self.assertIn("items: Outer.Items", line)
                seen.add(words[0][:24])
        self.assertEqual(len(seen), 4, seen)

    def test_let_response_continues_on_its_response_and_refuses_any_other_by_name(self):
        art = self.compiled(BUMP_SUGARED, "bump", world=True)
        started = self.h.start(art, [nat(4)])
        self.assertEqual(started["status"], "yielded", started)
        done = self.h.resume(art, started["checkpoint"], variant("written"))
        self.assertEqual((done["status"], done["value"]), ("finished", nat(5)), done)
        for label, payload in (("refused", {"tag": "record", "fields": [
                {"name": "clause", "value": {"tag": "label", "value": "owner"}}]}), ("later", None)):
            with self.subTest(response=label):
                reply = self.h.resume(art, self.h.start(art, [nat(4)])["checkpoint"], variant(label, payload))
                self.assertEqual(reply, {"status": "error", "message": "turn refused: unexpected response " + label})
        # The second statement refuses after the first continues.
        art = self.compiled(TWICE_SUGARED, "twice", world=True)
        second = self.h.resume(art, self.h.start(art, [nat(1)])["checkpoint"], variant("written"))
        self.assertEqual(second["status"], "yielded", second)
        self.assertEqual(self.h.resume(art, second["checkpoint"], variant("written"))["message"], "turn refused: unexpected response written")
        # In both branches of a tail `if`, refuse is where the activity finishes.
        art = self.compiled(TURN_HEAD + "def h(n: Nat) -> Activity<Nat>:\n  if n == 0n then refuse(\"zero\") else n\n", "h", world=True)
        self.assertEqual(self.h.start(art, [nat(0)])["message"], "turn refused: zero")
        self.assertEqual(self.h.start(art, [nat(3)])["value"], nat(3))

    def test_a_source_field_is_the_source_kind_of_a_form_library_that_has_it(self):
        # Form.obend's `source: {}` case is the objects lane's: one library with it, one without.
        having, lacking = library_modules(*FORM_LIB), library_modules(*FORM_LIB)
        for with_case, ms in ((True, having), (False, lacking)):
            for m in ms:
                if m["name"] == "Form":
                    bare = m["source"].replace("  source: {}\n", "")
                    m["source"] = bare.replace("sum Kind:\n", "sum Kind:\n  source: {}\n") if with_case else bare
        explicit = FORM_HEAD + ("def workshopForm() -> F.Form:\n  {card: \"\", action: \"compile\", fields: "
                                "F.Fields.cons({head: {name: \"program\", kind: F.Kind.source({})}, tail: "
                                "F.Fields.cons({head: {name: \"note\", kind: F.Kind.text({min: 1n, max: 80n})}, "
                                "tail: F.Fields.nil({})})})}\n"
                                "def forms() -> Lists.List<F.Form>:\n  Lists.List.cons({head: workshopForm(), tail: Lists.List.nil({})})\n")
        sugared = FORM_HEAD + "form compile as workshopForm:\n  program: source\n  note: text 1..80\n"
        replies = [self.h.send({"op": "compile", "entry": "workshopForm",
                                "modules": having + [{"name": "Package", "source": text}]}) for text in (explicit, sugared)]
        self.assertEqual(core(replies[0]["artifact"]), core(replies[1]["artifact"]), replies)
        self.assertIn('"source"', json.dumps(replies[1]["artifact"]["packet"]))
        reply = self.h.send({"op": "check-package", "entry": "workshopForm", "modules": lacking + [{"name": "Package", "source": sugared}]})
        self.assertEqual(reply["status"], "refused", reply)

    def test_the_artifact_lists_relations_fixed_fields_and_declarations_through_layers_and_aliases(self):
        # RELATIONAL section 11: a limit (0 is the host's default) and the retention past it.
        art = self.compiled(RELATIONS_BOUNDED, "initial", ("List",))
        self.assertEqual(art["relations"], [{"field": "rains", "key": ["author", "at"], "limit": 64, "retain": "dropOldest"}])
        # Refuted by an artifact without `fixed` whose effective State has fixed fields: a layer with no
        # State of its own, or a State aliasing an alias of one (review kernel 2).
        base = ({"name": "Base", "source": FIXED_HEAD + DERIVED_REST},)
        layer = ("layer over ./Base.obend\n" + HEAD + "import ./Abi.obend as Abi\n"
                 "def louder(state: Super.State, context: Abi.Context) -> Nat:\n  state.planted + 2n\n")
        for entry in ("plant", "louder"):
            with self.subTest(layer=entry):
                self.assertEqual(self.compiled(layer, entry, REL_LIB, extra=base).get("fixed"), ["note", "owner"])
        lib = ({"name": "Lib", "source": FIXED_HEAD + DERIVED_REST + "type Shared = State\n"},)
        aliased = HEAD + "import ./Lib.obend as Lib\ntype Again = Lib.Shared\ntype State = Again\ndef initial() -> State:\n  Lib.initial()\n"
        self.assertEqual(self.compiled(aliased, "initial", REL_LIB, extra=lib).get("fixed"), ["note", "owner"])
        # A layer that writes no forms() or initial() declares what its stack declares (review kernel 5).
        stack = ({"name": "Base", "source": FORM_STATE + FORM_BLOCKS + "def initial() -> State:\n  {planted: 0n}\ndef methods() -> Nat:\n  0n\n"},)
        for entry in ("extra", "plant"):
            with self.subTest(entry=entry):
                art = self.compiled("layer over ./Base.obend\n" + HEAD + "def extra(n: Nat) -> Nat:\n  n\n", entry, FORM_LIB, extra=stack)
                self.assertEqual(art["declares"], ["forms", "methods", "initial"])


if __name__ == "__main__":
    unittest.main()
