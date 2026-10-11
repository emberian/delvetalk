/- Enchantment (docs/OVERHAUL.md §4): every act leaves strokes on a thing; the card a resident reads may
   be painted from them by the world's model, and the exact card stands beneath it.

   `Strokes` is the thing as exact data at a version, assembled by the host from the store and nothing
   authored for it: its head, maker, keeper, owner, counts, the eight newest lines and the marks
   verbatim, its verbs with their spells and growers, its laws' readings, its rules and wants, its
   doors, where it lies and who is here. Read-only: `world-strokes {principal, object, version?}`. -/
import Delvetalk.Host.TurnLoop

namespace Delvetalk.Host.Enchant
open Lean (Json toJson)
open Delvetalk.Host
open Delvetalk.Theory.ObjectiveBendDemandData (Data)

/-! ## Strokes -/

/-- A line written on the thing: its number, the writer's handle, the verb that wrote it ("" while the
    store keeps no verb column), its text verbatim, the entry that wrote it, and, on a record with a
    keeper, `admitted` or `pending`. -/
structure Line where
  n : Nat
  handle : String
  verb : String
  text : String
  entry : Nat
  state : String

/-- A named moment (a bell's `rung`), by whom and at which entry. -/
structure Mark where
  name : String
  handle : String
  entry : Nat

/-- A verb the thing takes: its name, who grew it ("" for its kind's), what it reads as, and its spell. -/
structure Verb where
  name : String
  grower : String
  reading : String
  spell : String

/-- A rule on the thing: its name, its owner's handle, the entry it last fired at (0 for never). -/
structure Rule where
  name : String
  owner : String
  fired : Nat

/-- A want the thing holds now: its name, its reading, the spell that answers it. -/
structure Want where
  name : String
  reading : String
  spell : String

structure Door where
  label : String
  target : String

structure Strokes where
  object : String
  version : Nat
  kind : String := ""
  voice : String := ""
  head : String := ""
  /-- The values its kind's form took when it was made (`seed`, `colour`), by name. -/
  fields : List (String × String) := []
  maker : String := ""
  made : Nat := 0
  tended : Nat := 0
  keeper : String := ""
  owner : String := ""
  counts : List (String × Nat) := []
  lines : List Line := []
  marks : List Mark := []
  verbs : List Verb := []
  laws : List (String × String) := []
  rules : List Rule := []
  wants : List Want := []
  doors : List Door := []
  around : String := ""
  present : List String := []
  today : List String := []

/-- How many of the newest lines the strokes carry. -/
def newestLines : Nat := 8

/-- Relation fields that are bookkeeping, not strokes: who was greeted or missed, who left. -/
def unstroked : List String := ["greeted", "missed", "left"]

/-- Counts shown even at zero: a thing with no lines or marks is seen to have none. -/
def alwaysCounted : List String := ["lines", "marks"]

/-- A JSON object of the fields that say something: an empty string, list or zero is left out. -/
def present? (fields : List (String × Json)) : Json :=
  Json.mkObj (fields.filter fun (_, v) => match v with
    | .str s => !s.isEmpty
    | .arr a => !a.isEmpty
    | .num n => n != (0 : Lean.JsonNumber)
    | _ => true)

def Line.json (l : Line) : Json :=
  present? [("n", toJson l.n), ("handle", toJson l.handle), ("verb", toJson l.verb), ("text", toJson l.text),
    ("at", toJson l.entry), ("state", toJson l.state)]

def Mark.json (m : Mark) : Json := present? [("name", toJson m.name), ("handle", toJson m.handle), ("at", toJson m.entry)]

def Verb.json (v : Verb) : Json :=
  present? [("name", toJson v.name), ("by", toJson v.grower), ("reading", toJson v.reading), ("spell", toJson v.spell)]

def Rule.json (r : Rule) : Json := present? [("name", toJson r.name), ("owner", toJson r.owner), ("fired", toJson r.fired)]

def Want.json (x : Want) : Json := present? [("name", toJson x.name), ("reading", toJson x.reading), ("spell", toJson x.spell)]

/-- The strokes as the painter and the reader are shown them; every field present, empty or not, so an
    empty one is seen to be empty. -/
def Strokes.json (s : Strokes) : Json :=
  Json.mkObj [("object", toJson s.object), ("version", toJson s.version), ("kind", toJson s.kind),
    ("voice", toJson s.voice), ("head", toJson s.head),
    ("fields", Json.mkObj (s.fields.map fun (k, v) => (k, toJson v))), ("maker", toJson s.maker), ("made", toJson s.made),
    ("tended", toJson s.tended), ("keeper", toJson s.keeper), ("owner", toJson s.owner),
    ("counts", Json.mkObj (s.counts.map fun (k, n) => (k, toJson n))),
    ("lines", Json.arr (s.lines.toArray.map Line.json)), ("marks", Json.arr (s.marks.toArray.map Mark.json)),
    ("verbs", Json.arr (s.verbs.toArray.map Verb.json)),
    ("laws", Json.arr (s.laws.toArray.map fun (n, r) => present? [("name", toJson n), ("reading", toJson r)])),
    ("rules", Json.arr (s.rules.toArray.map Rule.json)), ("wants", Json.arr (s.wants.toArray.map Want.json)),
    ("doors", Json.arr (s.doors.toArray.map fun d => Json.mkObj [("label", toJson d.label), ("to", toJson d.target)])),
    ("around", toJson s.around), ("present", toJson s.present), ("today", toJson s.today)]

/-! ### Reading the store -/

def fieldsOf : Data → List (String × Data)
  | .record f => f
  | _ => []

def text? (fs : List (String × Data)) (k : String) : Option String :=
  match fs.lookup k with
  | some (.label s) => some s
  | _ => none

def nat? (fs : List (String × Data)) (k : String) : Option Nat :=
  match fs.lookup k with
  | some (.natural n) => some n
  | _ => none

/-- A relation's rows (`rows {items}`), or a list's items, as field lists. -/
def rowsOf : Data → Option (List (List (String × Data)))
  | .variant "rows" (.record f) => ((f.lookup "items").bind listOf).map (·.map fieldsOf)
  | d => (listOf d).map (·.map fieldsOf)

def rows (fs : List (String × Data)) (k : String) : List (List (String × Data)) :=
  ((fs.lookup k).bind rowsOf).getD []

def isRelation : Data → Bool
  | .variant "rows" _ => true
  | _ => false

/-- A handle the state gives (`handleKey`), else the registry's for the principal it names (`principalKey`). -/
def handleIn (w : World) (fs : List (String × Data)) (handleKey principalKey : String) : String :=
  match text? fs handleKey with
  | some h => if h.isEmpty then handleOf w ((text? fs principalKey).getD "") else h
  | none => handleOf w ((text? fs principalKey).getD "")

/-- A spell as one line: the template's lines joined by ` / ` (`delvetalk bell/1 rain / text: <…>`). -/
def oneLine (template : String) : String :=
  " / ".intercalate ((template.splitOn "\n").filter (!·.isEmpty))

/-- The spell's first line, `delvetalk CARD ACTION`. -/
def spellHead (spell : String) : String :=
  ((spell.splitOn " / ").head?.getD spell)

/-- The kind a clause `under "K"` follows. -/
def underOf (expr : String) : Option String := do
  let rest ← expr.dropPrefix? "under \""
  let k := (rest.toString.takeWhile (· != '"')).toString
  if k.isEmpty then none else some k

/-- The longest proper prefix of `id` (by `/`) that is an object of the world: what a thing made under
    a record lies in (`garden/bell/2` in `garden`). -/
def madeUnder (w : World) (id : String) : String := Id.run do
  let parts := id.splitOn "/"
  for k in (List.range parts.length).reverse do
    if k == 0 then continue
    let pfx := "/".intercalate (parts.take k)
    if w.objects.contains pfx then return pfx
  return ""

/-- The strokes of object `id` with `state` and `lawText` (its own at `version`). -/
def assemble (w : World) (id : String) (o : Object) (version : Nat) (state : Data) (lawText : String) : Strokes := Id.run do
  let fs := fieldsOf state
  let kind := (text? fs "kind").getD ""
  let voice := match w.objects[kind]? with
    | some k => (text? (fieldsOf k.state) "voice").getD ""
    | none => ""
  let keeperP := (text? fs "keeper").getD ""
  let admitted := (rows fs "admitted").filterMap (nat? · "n")
  let lineOf := fun (r : List (String × Data)) =>
    let n := (nat? r "n").getD 0
    ({ n, handle := handleIn w r "handle" "author", verb := (text? r "verb").getD "", text := (text? r "text").getD "",
       entry := (nat? r "at").getD 0,
       state := if keeperP.isEmpty then "" else if admitted.contains n then "admitted" else "pending" } : Line)
  let all := ((rows fs "lines").map lineOf).toArray.qsort (fun a b => a.n < b.n) |>.toList
  let mut lines := all.drop (all.length - newestLines)
  -- A thing's surrounding is the line its keeper wrote when it was inspirited.
  if let some d := text? fs "description" then
    unless d.isEmpty do
      lines := { n := 0, handle := handleIn w fs "keeperHandle" "keeper", verb := "inspirit", text := d, entry := 0, state := "" } :: lines
  let marks := (rows fs "marks").map fun r =>
    ({ name := (text? r "name").getD "", handle := handleIn w r "handle" "who", entry := (nat? r "at").getD 0 } : Mark)
  -- The verbs: the card's spells (its kind's), then rows grown on it (`verbs`, when its package keeps them).
  let declared := (spellForms w id o).map fun f =>
    ({ name := f.action, grower := "", reading := "", spell := oneLine (spellTemplate id f) } : Verb)
  let grown := (rows fs "verbs").filterMap fun r => do
    let name ← text? r "name"
    let byHandle := handleIn w r "byHandle" "by"
    pure ({ name, grower := byHandle, reading := (text? r "reading").getD "",
            spell := ((declared.find? (·.name == name)).map (·.spell)).getD s!"delvetalk {id} {name}" } : Verb)
  let verbs := (declared.filter fun v => !grown.any (·.name == v.name)) ++ grown
  -- Each clause with its reading; a clause `under "K"` is K's law, so it stands as K's clauses.
  let laws := (lawClauses lawText).flatMap fun (name, reading, expr) =>
    match underOf expr with
    | some k => ((w.objects[k]?).bind fun ko => text? (fieldsOf ko.state) "law").map (fun t =>
        (lawClauses t).map fun (n, r, _) => (n, r.getD "")) |>.getD [(name, reading.getD "")]
    | none => [(name, ((reading.orElse fun _ => o.readings.lookup name)).getD "")]
  let doors := ((fs.lookup "cites").bind listOf |>.getD []).filterMap fun d => do
    let r := fieldsOf d
    pure ({ label := (text? r "label").getD "", target := ← (r.lookup "to").bind referenceId } : Door)
  let around := match (fs.lookup "location").bind referenceId with
    | some place => place
    | none => madeUnder w id
  let present := (rows fs "presence").map fun r => handleIn w r "handle" "who"
  let counts := ((fs.filter fun (k, v) => isRelation v && !unstroked.contains k).map fun (k, v) =>
    (k, ((rowsOf v).map (·.length)).getD 0)).filter fun (k, n) => n > 0 || alwaysCounted.contains k
  let fields := (rows fs "fields").filterMap fun r => do pure (← text? r "name", ← text? r "value")
  let made := (nat? fs "made").getD (((w.touched[id]?).bind (·[0]?)).map (· + 1) |>.getD 0)
  return { object := id, version, kind, voice,
           head := (text? fs "head").getD ((text? fs "name").getD ""), fields,
           maker := handleIn w fs "makerHandle" "maker",
           made, tended := (nat? fs "tendedAt").getD 0,
           keeper := handleIn w fs "keeperHandle" "keeper", owner := handleIn w fs "ownerHandle" "owner",
           counts, lines, marks, verbs, laws, doors, around, present }

/-- The strokes of `id` at `version` (default its current one), as `reader` may read them: `none` when
    there is no such object or version, or the reader may not view it. -/
def strokesAt (w : World) (reader id : String) (version : Option Nat) : Except String Strokes := do
  let some o := w.objects[id]? | throw "unknown"
  unless o.read.permits reader do throw "denied"
  let v := version.getD o.version
  let some state := stateAt w id v | throw "unknown"
  let (_, lawText) := pinAndLawAt w o id v
  return assemble w id o v state lawText

/-- `world-strokes {principal, object, version?}`: `{status: "strokes", object, version, strokes}`, or
    `unknown` / `denied`. Nothing is written. -/
def strokesOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let id := resolveCard reader (← j.getObjValAs? String "object")
  let version ← optNat j "version"
  match strokesAt w reader id version with
  | .ok s => return Json.mkObj [("status", toJson "strokes"), ("object", toJson id), ("version", toJson s.version),
      ("strokes", s.json)]
  | .error why => return Json.mkObj [("status", toJson why), ("object", toJson id)]

end Delvetalk.Host.Enchant
