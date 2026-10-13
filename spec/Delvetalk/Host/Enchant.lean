/- Enchantment (docs/OVERHAUL.md §4): every act leaves strokes on a thing; the card a resident reads may
   be painted from them by the world's model, and the exact card stands beneath it.

   `Strokes` is a thing as exact data at a version, assembled by the host from the store and nothing
   authored for it, or a day of the town (`dayStrokes`, the chronicle's day and what wants a hand). What
   the painter reads is `Strokes.text`: what the thing is, its maker's words and voice, its residents'
   lines, what it wants, and each number with its unit and its meaning ("rains: 2"; "the 7th rain:
   rule seven"); never an entry number or a version. `verify` holds a paint to them. Read-only:
   `world-strokes {principal, object | day, version?, morning?}`. -/
import Delvetalk.Host.TurnLoop

namespace Delvetalk.Host.Enchant
open Lean (Json toJson)
open Delvetalk.Host
open Delvetalk.Theory.ObjectiveBendDemandData (Data)

/-! ## Strokes -/

/-- A line written on the thing: its number, the writer's handle, the verb that wrote it ("" while the
    store keeps no verb column), its text verbatim, the entry that wrote it, on a record with a keeper
    `admitted` or `pending`, and, in a day's strokes, the thing it was written on. -/
structure Line where
  n : Nat
  handle : String
  verb : String
  text : String
  entry : Nat
  state : String
  on : String := ""

/-- A named moment (a bell's `rung`), by whom and at which entry. -/
structure Mark where
  name : String
  handle : String
  entry : Nat

/-- A number and what it counts: `n` of `unit` ("2 rain"), or, `ordinal`, the `n`th `unit` at which what
    `note` says happens ("the 7th rain: rule seven"). The numbers a paint may write, each beside its unit. -/
structure Quantity where
  n : Nat
  unit : String
  ordinal : Bool := false
  note : String := ""

/-- A verb the thing takes: its name, the handle of who grew it ("" for its kind's), what it reads as, and its spell. -/
structure Verb where
  name : String
  grower : String
  reading : String
  spell : String

/-- A rule the thing carries: its name, its owner's handle, its reading, the entry it last fired at (0 for never). -/
structure Rule where
  name : String
  owner : String
  reading : String
  fired : Nat

/-- A want that holds now: its name, its reading, the spell that answers it, in a day's strokes its thing, and
    the handle of who placed it ("" when the host names none). -/
structure Want where
  name : String
  reading : String
  spell : String
  object : String := ""
  owner : String := ""

structure Door where
  label : String
  target : String

/-- The longest paint of a thing; a day may run to `maxDay`; a telling of a place to `maxAway` (one or two
    sentences of what happened while the reader was away) or `maxBefore` (up to four, of its past). -/
def maxPaint : Nat := 400
def maxDay : Nat := 600
def maxAway : Nat := 300
def maxBefore : Nat := 500

/-- A telling (the owner: "not just 'while you were away' but also a 'before you arrived... [painted past]'"): the
    strokes of what happened in a place over a span of its journal, painted above the exact lines it draws on.
    `away`: since the reader's departure, the entry `since` they left at; `before`: the place's whole past. `upto`
    is the entry the reader arrived at, or one past the place's newest change when they are not in it, so a telling
    is of a closed span and its key moves only with the place and the departure, never with a read. `exact` is the
    host's lines it draws on, with their entries: beneath the paint, and in its place when there is none. -/
structure Telling where
  form : String
  since : Nat
  upto : Nat
  exact : List String := []

/-- The words the page sets above a telling: the host's frame, never the paint's. -/
def Telling.frame (t : Telling) : String := if t.form == "away" then "While you were away" else "Before you arrived"

def Telling.json (t : Telling) : Json :=
  Json.mkObj [("form", toJson t.form), ("since", toJson t.since), ("until", toJson t.upto), ("exact", toJson t.exact)]

/-- What a render answer carries of a telling, painted or not: its form, its frame and its exact lines. -/
def Telling.answer (t : Telling) : Json :=
  Json.mkObj [("form", toJson t.form), ("frame", toJson t.frame), ("since", toJson t.since), ("exact", toJson t.exact)]

structure Strokes where
  object : String
  version : Nat
  kind : String := ""
  /-- Its kind's register, else (a thing with no kind) the register of the place it lies in. -/
  voice : String := ""
  /-- Its kind's one plain line of what it is (`about`), read as the voice is. -/
  about : String := ""
  head : String := ""
  /-- The values its kind's form took when it was made (`seed`, `colour`), by name: its maker's words. -/
  fields : List (String × String) := []
  maker : String := ""
  /-- Made after another's post (a coinage of the town's): `coined`, and the coiner: the post author's handle
      when the registry knows it, else the at:// author (a DID). -/
  coined : Bool := false
  coiner : String := ""
  made : Nat := 0
  /-- The clock minute it was last tended at (0: never; the transport keeps a world's clock past 0), and how long ago,
      in words. -/
  tended : Nat := 0
  tendedAgo : String := ""
  keeper : String := ""
  owner : String := ""
  quantities : List Quantity := []
  lines : List Line := []
  marks : List Mark := []
  verbs : List Verb := []
  /-- The law its kind adds to the frame every record or thing keeps (`kind/record`'s clauses left out). -/
  laws : List (String × String) := []
  rules : List Rule := []
  wants : List Want := []
  doors : List Door := []
  around : String := ""
  present : List String := []
  /-- A day's strokes: what the day did, as sentences, and the hands that acted. -/
  today : List String := []
  hands : List String := []
  /-- A day's strokes are of no thing: `day` is the clock day they read. -/
  day : Option Nat := none
  /-- A telling's strokes are of a place's span (`tellingAt`): `today` its acts, `hands` who came. -/
  telling : Option Telling := none
  limit : Nat := maxPaint

/-- Whose words its form values are: the coiner's for a coinage, else its maker's. -/
def Strokes.wordsBy (s : Strokes) : String := if s.coined && !s.coiner.isEmpty then s.coiner else s.maker

/-- How many of the newest lines the strokes carry. -/
def newestLines : Nat := 8

/-- Relation fields that are bookkeeping, not strokes: who was greeted or missed, who left. -/
def unstroked : List String := ["greeted", "missed", "left"]

/-- A JSON object of the fields that say something: an empty string, list, zero or false is left out. -/
def present? (fields : List (String × Json)) : Json :=
  Json.mkObj (fields.filter fun (_, v) => match v with
    | .str s => !s.isEmpty
    | .arr a => !a.isEmpty
    | .num n => n != (0 : Lean.JsonNumber)
    | .bool b => b
    | _ => true)

def Line.json (l : Line) : Json :=
  present? [("n", toJson l.n), ("handle", toJson l.handle), ("verb", toJson l.verb), ("text", toJson l.text),
    ("at", toJson l.entry), ("state", toJson l.state), ("on", toJson l.on)]

def Mark.json (m : Mark) : Json := present? [("name", toJson m.name), ("handle", toJson m.handle), ("at", toJson m.entry)]

def Quantity.json (q : Quantity) : Json :=
  present? [("n", toJson q.n), ("unit", toJson q.unit), ("ordinal", toJson q.ordinal), ("note", toJson q.note)]

def Verb.json (v : Verb) : Json :=
  present? [("name", toJson v.name), ("by", toJson v.grower), ("reading", toJson v.reading), ("spell", toJson v.spell)]

def Rule.json (r : Rule) : Json :=
  present? [("name", toJson r.name), ("owner", toJson r.owner), ("reading", toJson r.reading), ("fired", toJson r.fired)]

def Want.json (x : Want) : Json :=
  present? [("name", toJson x.name), ("reading", toJson x.reading), ("spell", toJson x.spell), ("object", toJson x.object),
    ("owner", toJson x.owner)]

/-! ### What the painter reads -/

/-- `unit` counted `n`: "rain" 2 is "rains", 1 "rain". -/
def plural (unit : String) (n : Nat) : String :=
  if n == 1 || unit.endsWith "s" || unit.endsWith "ed" || unit == "here" then unit else unit ++ "s"

def nth (n : Nat) : String :=
  let suffix := if (n / 10) % 10 == 1 then "th" else match n % 10 with
    | 1 => "st" | 2 => "nd" | 3 => "rd" | _ => "th"
  s!"{n}{suffix}"

def Quantity.text (q : Quantity) : String :=
  if q.ordinal then s!"the {nth q.n} {q.unit}: {q.note}"
  else s!"{plural q.unit 2}: {q.n}" ++ (if q.note.isEmpty then "" else s!" ({q.note})")

def quoted (t : String) : String := "“" ++ t ++ "”"

/-- The strokes as the painter reads them: what the thing is, then its maker's words, its life (lines,
    wants, rules), its counts with their units, its spells; a field it does not hold is not written. -/
def Strokes.text (s : Strokes) : String := Id.run do
  let kindName := ((s.kind.splitOn "/").getLast?.getD s.kind)
  let part := fun (title : String) (rows : List String) =>
    if rows.isEmpty then [] else [title] ++ rows.map ("- " ++ ·)
  let line := fun (cond : Bool) (t : String) => if cond then [t] else []
  let who := (line (!s.maker.isEmpty) s!"made by {s.maker}") ++ (line (!s.owner.isEmpty && s.owner != s.maker) s!"owned by {s.owner}") ++
    (line (!s.keeper.isEmpty) s!"kept by {s.keeper}")
  let out :=
    (match s.day, s.telling with
      | some _, _ => ["What it is: a day of the town"]
      | none, some t => [s!"What it is: a telling of {s.object}" ++ (if s.kind.isEmpty then "" else s!", a {kindName} ({s.kind})") ++
          (if t.form == "away" then ": what happened there while the reader was away, in the third person"
           else ": its past, before the reader's first arrival, in the third person")]
      | none, none => [s!"What it is: {s.object}" ++ (if s.kind.isEmpty then "" else s!", a {kindName} ({s.kind})")]) ++
    line (!s.head.isEmpty) s!"Called: {s.head}" ++
    [if s.voice.isEmpty then "Its voice: plain" else s!"Its voice: {s.voice}"] ++
    line (!s.about.isEmpty) s!"What its kind is: {s.about}" ++
    line (!s.fields.isEmpty) (s!"The words it was made with, {s.wordsBy}'s: " ++ "; ".intercalate (s.fields.map fun (k, v) => s!"{k}: {v}")) ++
    line s.coined s!"A coinage of the town's: {s.coiner} coined it first, in a post on delve.town that its card links; its maker here only placed it, and its words are {s.coiner}'s" ++
    line (!who.isEmpty) ("Who: " ++ ", ".intercalate who) ++
    line (!s.around.isEmpty) s!"It lies in: {s.around}" ++
    line (!s.doors.isEmpty) ("Its doors: " ++ ", ".intercalate (s.doors.map fun d => if d.label == d.target then d.target else s!"{d.label} (to {d.target})")) ++
    line (!s.present.isEmpty) ("Here now: " ++ ", ".intercalate s.present) ++
    line (!s.tendedAgo.isEmpty) s!"Last tended: {s.tendedAgo}" ++
    part (if s.telling.isSome then "What happened there, oldest first:" else "What happened that day, in order:") s.today ++
    line (!s.hands.isEmpty) ((if s.telling.isSome then "Who came here: " else "Hands that acted: ") ++ ", ".intercalate s.hands) ++
    part "Lines written, oldest first:" (s.lines.map fun l =>
      let tag := ", ".intercalate ([l.verb, l.state].filter (!·.isEmpty))
      let on := if l.on.isEmpty then "" else s!" on {l.on}"
      (if l.handle.isEmpty then "someone" else l.handle) ++ on ++ (if tag.isEmpty then "" else s!" ({tag})") ++ ": " ++ quoted l.text) ++
    part "Marks:" (s.marks.map fun m => if m.handle.isEmpty then m.name else s!"{m.name}, by {m.handle}") ++
    part "Counts:" (s.quantities.map Quantity.text) ++
    part (if s.day.isSome then "What still wants a hand, turning daily:" else "What it wants now:") (s.wants.map fun x =>
      (if x.object.isEmpty then "" else s!"{x.object}, ") ++ x.name ++ (if x.reading.isEmpty then "" else ": " ++ quoted x.reading) ++
        (if x.spell.isEmpty then "" else s!"; the spell it asks for: {x.spell}")) ++
    part "Rules on it:" (s.rules.map fun r =>
      s!"{r.name}, {if r.owner.isEmpty then "its kind's" else r.owner ++ "'s"}: {quoted r.reading}" ++ (if r.fired == 0 then " (has not fired)" else " (has fired)")) ++
    part "What its kind holds it to:" (s.laws.map fun (n, r) => if r.isEmpty then n else s!"{n}: {quoted r}") ++
    line (!s.verbs.isEmpty) ("Its verbs: " ++ ", ".intercalate (s.verbs.map fun v =>
      v.name ++ (if v.grower.isEmpty then "" else s!" (grown by {v.grower}" ++ (if v.reading.isEmpty then ")" else ": " ++ quoted v.reading ++ ")")))) ++
    [s!"Length: at most {s.limit} characters, the spell included: about {s.limit / 8} words."]
  return "\n".intercalate out

/-- The strokes as exact data (`world-strokes`), every field present, and the text the painter reads. -/
def Strokes.json (s : Strokes) : Json :=
  Json.mkObj [("object", toJson s.object), ("version", toJson s.version), ("kind", toJson s.kind),
    ("voice", toJson s.voice), ("about", toJson s.about), ("head", toJson s.head),
    ("fields", Json.mkObj (s.fields.map fun (k, v) => (k, toJson v))), ("maker", toJson s.maker),
    ("coined", toJson s.coined), ("coiner", toJson s.coiner), ("made", toJson s.made),
    ("tended", toJson s.tended), ("tendedAgo", toJson s.tendedAgo), ("keeper", toJson s.keeper), ("owner", toJson s.owner),
    ("quantities", Json.arr (s.quantities.toArray.map Quantity.json)),
    ("lines", Json.arr (s.lines.toArray.map Line.json)), ("marks", Json.arr (s.marks.toArray.map Mark.json)),
    ("verbs", Json.arr (s.verbs.toArray.map Verb.json)),
    ("laws", Json.arr (s.laws.toArray.map fun (n, r) => present? [("name", toJson n), ("reading", toJson r)])),
    ("rules", Json.arr (s.rules.toArray.map Rule.json)), ("wants", Json.arr (s.wants.toArray.map Want.json)),
    ("doors", Json.arr (s.doors.toArray.map fun d => Json.mkObj [("label", toJson d.label), ("to", toJson d.target)])),
    ("around", toJson s.around), ("present", toJson s.present), ("today", toJson s.today), ("hands", toJson s.hands),
    ("day", toJson s.day), ("limit", toJson s.limit)] |>.mergeObj
    (Json.mkObj ((s.telling.map fun t => [("telling", t.json)]).getD []))

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

/-- The town as such (`isTown`), else a handle the state gives (`handleKey`), else the registry's for the principal it
    names (`principalKey`). -/
def handleIn (w : World) (fs : List (String × Data)) (handleKey principalKey : String) : String :=
  let principal := (text? fs principalKey).getD ""
  if isTown w principal then townName else
  match text? fs handleKey with
  | some h => if h.isEmpty then handleOf w principal else h
  | none => handleOf w principal

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

/-- A kind object's text field `field` (its `voice`, its `about`), "" for none. -/
def kindText (w : World) (kind field : String) : String :=
  match w.objects[kind]? with
  | some k => (text? (fieldsOf k.state) field).getD ""
  | none => ""

/-- The kind of `id` as it stands ("" for none). -/
def kindOf (w : World) (id : String) : String :=
  match w.objects[id]? with
  | some o => (text? (fieldsOf o.state) "kind").getD ""
  | none => ""

/-- What a thing lying here is called by: `garden/bell/2` a bell, `porch/goblet` a goblet. -/
def calledBy (id : String) : String :=
  let parts := id.splitOn "/"
  let last := parts.getLast?.getD id
  if !last.isEmpty && last.all Char.isDigit then (parts.dropLast.getLast?.getD "thing") else last

/-- `n` minutes since, in words: the day it is in, coarse, so a strokes key moves at most once a day. -/
def ago (minutes : Nat) : String :=
  let days := minutes / Limits.clockDay
  if days == 0 then "today" else if days == 1 then "a day ago" else s!"{days} days ago"

/-- `count(new.F) >= N` or `count(new.F where …) >= N` in a rule's condition: the count it fires at. -/
def threshold (field condition : String) : Option Nat := do
  let counted ← (condition.splitOn s!"count(new.{field}")[1]?
  let rest ← (counted.splitOn ") >= ")[1]?
  let n := (rest.takeWhile Char.isDigit).toString.toNat!
  if n == 0 then none else some n

/-- The names of `kind/record`'s clauses: the frame every record keeps (who owns, who keeps, what only
    a method writes), which a paint need not be told. -/
def frameLaws (w : World) : List String :=
  match w.objects["kind/record"]? with
  | some k => (textClauses ((text? (fieldsOf k.state) "law").getD "")).map (·.2.1)
  | none => []

/-- The unit a line counts as: the verb that wrote it (a bell's rain); a plain `write`, a room's talk or none a line. -/
def lineUnit (verb : String) : String := if verb.isEmpty || ["write", "say", "emote"].contains verb then "line" else verb

/-- How many of each `unit` a list holds, in first-seen order. -/
def tally (units : List String) : List (String × Nat) :=
  units.foldl (fun acc u => if acc.any (·.1 == u) then acc.map fun (k, n) => (k, if k == u then n + 1 else n) else acc ++ [(u, 1)]) []

/-- Lines counted by what wrote them, and all of them as lines when that says more: rains: 2, lines: 2. -/
def lineQuantities (verbs : List String) (note : String := "") : List Quantity :=
  let byVerb := tally (verbs.map lineUnit)
  byVerb.map (fun (u, n) => ({ n, unit := u, note } : Quantity)) ++
    (if byVerb.length > 1 || byVerb.any (·.1 != "line") then [{ n := verbs.length, unit := "line", note }] else [])

/-- The strokes of object `id` with `state` and `lawText` (its own at `version`). -/
def assemble (w : World) (id : String) (o : Object) : Strokes := Id.run do
  let (version, state, lawText) := (o.version, o.state, o.lawText)
  let fs := fieldsOf state
  let kind := (text? fs "kind").getD ""
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
  -- The verbs: the card's spells (its forms, the grown ones among them), the kind's first, then each grown on it
  -- (`Object.verbs`) with its grower and reading.
  let forms := (spellForms w id o).map fun f => (f.action, oneLine (spellTemplate id f))
  let grown := o.verbs.map fun v =>
    ({ name := v.name, grower := shownName w v.grower, reading := v.reading,
       spell := (forms.lookup v.name).getD s!"delvetalk {id} {v.name}" } : Verb)
  let verbs := (forms.filter fun (n, _) => !grown.any (·.name == n)).map (fun (name, spell) =>
    ({ name, grower := "", reading := "", spell } : Verb)) ++ grown
  -- The law its kind adds: each clause `under "K"` stands as K's clauses, the frame's left out.
  let frame := frameLaws w
  let lawsOf := fun (t : String) => (textClauses t).filter (·.1 == "law")
  let laws := ((lawsOf lawText).flatMap fun (_, _, _, body) =>
    match underOf body with
    | some k => ((w.objects[k]?).bind fun ko => text? (fieldsOf ko.state) "law").map (fun t =>
        (lawsOf t).map fun (_, n, r, _) => (n, r.getD "")) |>.getD []
    | none => []).filter fun (n, _) => !frame.contains n
  -- The rules it carries (placed, its text's, its kind's), each with its owner and its last firing; the wants
  -- that hold of it now, each with the spell that answers it as filled at this read (`world-rules`, `world-wants`).
  let carried := carriedRules w id o
  let rules := carried.map fun c =>
    let last := (w.ruleLog[id]?).bind (·.lookup c.clause.name)
    let fired := if (last.bind fun l => (l.getObjVal? "why").toOption).isSome then 0
      else (last.bind fun l => (l.getObjValAs? Nat "height").toOption).getD 0
    ({ name := c.clause.name, owner := (principalThing c.owner).getD (handleShown w c.owner), reading := c.clause.reading, fired } : Rule)
  let wants := (wantRows w "" id o).map fun r =>
    ({ name := (r.getObjValAs? String "name").toOption.getD "", reading := (r.getObjValAs? String "reading").toOption.getD "",
       spell := (r.getObjValAs? String "asks").toOption.getD "",
       owner := handleShown w ((r.getObjValAs? String "owner").toOption.getD "") } : Want)
  let doors := ((fs.lookup "cites").bind listOf |>.getD []).filterMap fun d => do
    let r := fieldsOf d
    pure ({ label := (text? r "label").getD "", target := ← (r.lookup "to").bind referenceId } : Door)
  let around := match (fs.lookup "location").bind referenceId with
    | some place => place
    | none => madeUnder w id
  let present := (rows fs "presence").map fun r => handleIn w r "handle" "who"
  -- Each number with its unit: the lines by the verb that wrote them (a bell's rains), the count a rule
  -- fires at as the nth, what lies here by what it is called, who is here, its doors, any other relation.
  let byVerb := tally (all.map (lineUnit ·.verb))
  let unitOfLines := match byVerb with
    | [(u, _)] => u
    | _ => "line"
  let things := (rows fs "things").filterMap fun r => referenceId (.record r)
  let byKind := tally (things.map calledBy)
  let others := (fs.filter fun (k, v) => isRelation v && !unstroked.contains k &&
      !["lines", "marks", "things", "presence"].contains k).map fun (k, v) => (k, ((rowsOf v).map (·.length)).getD 0)
  let quantities : List Quantity :=
    (if all.isEmpty then (if lines.isEmpty then [{ n := 0, unit := "line" }] else []) else lineQuantities (all.map (·.verb))) ++
    (carried.filterMap fun c => (threshold "lines" c.clause.condition.render).map fun n =>
      ({ n, unit := unitOfLines, ordinal := true, note := s!"rule {c.clause.name}, {quoted c.clause.reading}" } : Quantity)) ++
    byKind.map (fun (u, n) => ({ n, unit := u } : Quantity)) ++
    (if things.isEmpty then [] else [{ n := things.length, unit := "thing", note := "lying here" }]) ++
    (if present.isEmpty then [] else [{ n := present.length, unit := "here" }]) ++
    (if doors.isEmpty then [] else [{ n := doors.length, unit := "door" }]) ++
    (others.filter (·.2 > 0)).map fun (k, n) => ({ n, unit := k } : Quantity)
  let fields := (rows fs "fields").filterMap fun r => do pure (← text? r "name", ← text? r "value")
  let made := (nat? fs "made").getD (((w.touched[id]?).bind (·[0]?)).map (· + 1) |>.getD 0)
  let tended := (nat? fs "tended").getD 0
  let tendedAgo := if tended == 0 then "" else ago (w.clock - tended)
  let maker := handleIn w fs "makerHandle" "maker"
  -- A coinage: made after a post that is not its maker's own (`Record.credit`), crediting its coiner.
  let post := (text? fs "post").getD ""
  let coined := post.startsWith "at://" && !post.startsWith s!"at://{(text? fs "maker").getD ""}/"
  -- The coiner is the post's author: their handle when the host knows it, else the at:// authority itself.
  let author := (((post.drop 5).toString).splitOn "/").head?.getD ""
  let coiner := if !coined then "" else if (handleShown w author).isEmpty then author else handleShown w author
  let kindHere := if kind.isEmpty then kindOf w around else kind
  return { object := id, version, kind, voice := kindText w kindHere "voice", about := kindText w kindHere "about",
           head := (text? fs "head").getD ((text? fs "name").getD ""), fields,
           maker, coined, coiner, made, tended, tendedAgo,
           keeper := handleIn w fs "keeperHandle" "keeper", owner := handleIn w fs "ownerHandle" "owner",
           quantities, lines, marks, verbs, laws, rules, wants, doors, around, present }

/-- The strokes of `id` as it stands, as `reader` may read them: `unknown` when there is no such object or
    version, `denied` when the reader may not view it, `historical` for a version before its current one
    (the store keeps no past wants, verbs or firings, so no strokes of one are assembled). -/
def strokesAt (w : World) (reader id : String) (version : Option Nat) : Except String Strokes := do
  let some o := w.objects[id]? | throw "unknown"
  unless o.read.permits reader do throw "denied"
  if let some v := version then
    if v > o.version then throw "unknown"
    if v < o.version then throw "historical"
  return assemble w id o

/-! ### A day of the town -/

/-- The reading of `name` among the rules (or wants) `id` carries now, "" for none. -/
def readingOf (w : World) (id name : String) (wants : Bool) : String :=
  match w.objects[id]? with
  | some o => (((if wants then carriedWants w id o else carriedRules w id o).find? (·.clause.name == name)).map (·.clause.reading)).getD ""
  | none => ""

/-- A day event as a sentence of the day's strokes: who did what to which thing, a rule or want by its
    reading; no entry number. -/
def eventSentence (w : World) (e : DayEvent) : String :=
  let r := fun (wants : Bool) => let t := readingOf w e.object e.name wants; if t.isEmpty then "" else ", " ++ quoted t
  match e.what with
  | "made" => s!"{e.who} made {e.object}"
  | "grew" => s!"{e.who} grew the verb {e.name} on {e.object}"
  | "fired" => s!"{e.object}'s rule {e.name} fired{r false}"
  | "unfired" => s!"{e.object}'s rule {e.name} held and did not fire: {e.why}"
  | "wanted" => s!"{e.object} came to want {e.name}{r true}"
  | _ => s!"{e.object} stopped wanting {e.name}"

/-- What still wants a hand across the world now (`wanting`), an answerable page of eight, oldest-first rotated by clock day,
    as `hand morning` lists them exact beneath the paint: by their readings, without spells, since a morning's paint
    names no spell (`Paint.contract`) and the `spells` clause holds it to that. -/
def wantsOfDay (w : World) (reader : String) : List Want :=
  (wanting w reader 0 newestLines (oldest := true)).rows.map fun (r : Wanted) => { object := r.object, name := r.name, reading := r.reading, spell := "" }

/-- How many of a day's newest events its strokes carry. -/
def dayEvents : Nat := 16

/-- The strokes of the town's day `day` (`Ops.chronicleDay`): what it did, the lines written in it (the
    newest eight, with the thing each is on), its counts, the hands that acted; with `morning`, what wants a
    hand now. `version` is the day. -/
def dayStrokes (w : World) (reader : String) (day : Nat) (morning : Bool) : Strokes := Id.run do
  let some d := chronicleDay w reader day
    | return { object := "", version := day, day := some day, wants := if morning then wantsOfDay w reader else [], limit := maxDay }
  let mut written : Array Line := #[]
  for (id, o) in w.objects.toList do
    unless o.read.permits reader do continue
    for r in rows (fieldsOf o.state) "lines" do
      let at_ := (nat? r "at").getD 0
      if d.start ≤ at_ && at_ < d.stop then
        let l : Line := { n := (nat? r "n").getD 0, handle := handleIn w r "handle" "author", verb := (text? r "verb").getD "",
                          text := (text? r "text").getD "", entry := at_, state := "", on := id }
        written := written.push l
  let lines := (written.qsort fun a b => a.entry < b.entry || (a.entry == b.entry && a.on < b.on)).toList
  let refused := d.refusals.foldl (· + ·.2) 0
  -- A principal's own avatar (`did:…`) is never a thing of the day.
  let events := d.events.filter fun e => !((e.object.splitOn "/").head?.getD "").contains ':'
  let made := (events.filter (·.what == "made")).map (·.object)
  -- What was made, by what each is called: two bells, a goblet, twelve kinds.
  let byKind := tally (made.map fun id => if id.startsWith "kind/" then "kind" else calledBy id)
  return { object := "", version := day, day := some day, today := (events.drop (events.length - dayEvents)).map (eventSentence w), hands := d.hands,
           lines := lines.drop (lines.length - newestLines),
           quantities := [{ n := d.admitted, unit := "act", note := "admitted" }] ++
             (if refused == 0 then [] else [{ n := refused, unit := "refusal" }]) ++
             (if d.hands.isEmpty then [] else [{ n := d.hands.length, unit := "hand" }]) ++
             (if made.isEmpty then [] else [{ n := made.length, unit := "thing", note := "made" }]) ++
             byKind.map (fun (u, n) => ({ n, unit := u, note := "made" } : Quantity)) ++
             lineQuantities (lines.map (·.verb)) "written",
           wants := if morning then wantsOfDay w reader else [], limit := maxDay }

/-! ### A telling of a place -/

/-- How many of a place's newest changes a telling reads back through, and how many of its acts and lines it
    hands the painter: the span's first lines and its newest, and its newest acts. -/
def tellingSpan : Nat := 512
def tellingActs : Nat := 12
def tellingExact : Nat := 16

/-- A place: a thing one enters (its spells take `enter`). -/
def isPlace (w : World) (id : String) (o : Object) : Bool := (spellForms w id o).any (·.action == "enter")

/-- The row an edit inserts, as fields. -/
def insertedRow : Data → Option (List (String × Data))
  | .variant "insert" (.record f) => (f.lookup "row").map fieldsOf
  | _ => none

/-- The newest change of `id` (within `tellingSpan`) that brought `who` in: the edit inserting their presence row. -/
def arrivalOf (w : World) (id who : String) : Option Touch := Id.run do
  let ts := w.touches.getD id #[]
  for k in [0:min ts.size tellingSpan] do
    let t := ts[ts.size - 1 - k]!
    if ((touchEdits w id t).getD []).any (fun (f, d) => f == "presence" && ((insertedRow d).bind (text? · "who")) == some who) then
      return some t
  return none

/-- One act in a place's span, as the painter reads it (no entry) and as the exact line shows it (with it). -/
structure Act where
  entry : Nat
  who : String
  what : String
  sentence : String

/-- What the journal holds of `id` between entries `since` and `upto`, `reader`'s own comings and goings left out:
    the acts in order (came, left, took, laid down, hung or took down a door, made here, a rule fired), the lines
    written there and the marks made. -/
def spanOf (w : World) (id reader : String) (since upto : Nat) : Array Act × Array Line × Array Mark := Id.run do
  let ts := w.touches.getD id #[]
  let mut acts : Array Act := #[]
  let mut lines : Array Line := #[]
  let mut marks : Array Mark := #[]
  let mut picked : List Touch := []
  for k in [0:min ts.size tellingSpan] do
    let t := ts[ts.size - 1 - k]!
    if t.height ≤ since then break
    if t.height < upto then picked := t :: picked
  for t in picked do
    let some e := w.entries.get? (t.height - 1) | continue
    let p := ((e.getObjVal? "identity").toOption.bind (·.getObjValAs? String "principal" |>.toOption)).getD ""
    let by_ := shownName w p
    let act := fun (who what sentence : String) => ({ entry := t.height, who, what, sentence } : Act)
    let outcome := (e.getObjVal? "outcome").toOption.getD Json.null
    let arr := fun (j : Json) (k : String) => (((j.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]).toList
    -- What was made here lies here by the same write: it is told as made, not as laid down.
    let made := (arr outcome "creates").filterMap fun c => (c.getObjValAs? String "object").toOption.filter (·.startsWith s!"{id}/")
    for (f, d) in (touchEdits w id t).getD [] do
      match f, insertedRow d with
      | "presence", some r =>
        let who := (text? r "who").getD ""
        unless who == reader do acts := acts.push (act (handleIn w r "handle" "who") "came" s!"{handleIn w r "handle" "who"} came in")
      | "left", some r =>
        let who := (text? r "who").getD ""
        unless who == reader do acts := acts.push (act (shownName w who) "left" s!"{shownName w who} left")
      | "lines", some r =>
        lines := lines.push { n := (nat? r "n").getD 0, handle := handleIn w r "handle" "author", verb := (text? r "verb").getD "",
                              text := (text? r "text").getD "", entry := t.height, state := "" }
      | "marks", some r =>
        marks := marks.push { name := (text? r "name").getD "", handle := handleIn w r "handle" "who", entry := t.height }
      | "things", some r =>
        if let some thing := referenceId (.record r) then
          unless made.contains thing do acts := acts.push (act by_ "laid" s!"{by_} laid {thing} down here")
      | "things", none =>
        if let .variant "retract" (.record k) := d then
          if let some thing := (k.lookup "key").bind fun key => text? (fieldsOf key) "object" then
            acts := acts.push (act by_ "took" s!"{by_} took {thing}")
      | "cites", _ =>
        match d with
        | .variant "append" (.record x) =>
          let door := fieldsOf ((x.lookup "item").getD (.record []))
          let label := (text? door "label").getD ""
          let to := ((door.lookup "to").bind referenceId).getD ""
          acts := acts.push (act by_ "hung" (if label == to || label.isEmpty then s!"{by_} hung a door to {to}" else s!"{by_} hung the door {label}, to {to}"))
        | .variant "removeItem" (.record x) =>
          let label := (text? (fieldsOf ((x.lookup "item").getD (.record []))) "label").getD ""
          acts := acts.push (act by_ "unhung" s!"{by_} took down the door {label}")
        | _ => pure ()
      | _, _ => pure ()
    for thing in made do acts := acts.push (act by_ "made" s!"{by_} made {thing} here")
    for f in arr e "fired" do
      if (f.getObjValAs? String "sender").toOption == some id then
        let name := (f.getObjValAs? String "rule").toOption.getD ""
        let owner := shownName w ((f.getObjValAs? String "principal").toOption.getD "")
        let reading := readingOf w id name false
        acts := acts.push (act owner "fired" (s!"its rule {name}, {owner}'s, fired" ++ (if reading.isEmpty then "" else ": " ++ quoted reading)))
  return (acts, lines, marks)

/-- The departure entry of `who` from the place (`left`'s newest row of theirs), 0 when they never left it. -/
def departedAt (fs : List (String × Data)) (who : String) : Nat :=
  ((rows fs "left").filter (text? · "who" == some who)).foldl (fun m r => max m ((nat? r "entry").getD 0)) 0

/-- The strokes of a telling of place `id` for `reader` (`telling {reader?, since?}`; `reader` defaults to the one
    asking, `since` to the entry they last left it at): what happened there after `since` and before they arrived
    (or, not in it, up to its newest change), the acts, lines and marks each by whose hand, counted with their units;
    for one arriving first (`since` 0) its whole past compressed: the making and its credit, the first lines and the
    newest, who came, what was hung, left and taken, what it still wants. The version is the one the reader found.
    Never the reader's own comings and goings, no spell, no rule or law, and nothing that moves after the arrival
    with every act (who is here now, when it was tended): a telling is of what happened. -/
def tellingOf (w : World) (asker id : String) (o : Object) (j : Json) : Except String Strokes := do
  let fs := fieldsOf o.state
  let reader := (j.getObjValAs? String "reader").toOption.getD asker
  let since := (← optNat j "since").getD (departedAt fs reader)
  let here := (rows fs "presence").any (text? · "who" == some reader)
  let arrival := if here then arrivalOf w id reader else none
  let newest := (((w.touches.getD id #[]).back?).map (·.height)).getD 0
  let upto := (arrival.map (·.height)).getD (newest + 1)
  let version := (arrival.map (·.version - 1)).getD o.version
  let (acts, lines, marks) := spanOf w id reader since upto
  let away := since > 0
  let base := assemble w id o
  let visitors := ((acts.toList.filter (·.what == "came")).map (·.who)).eraseDups
  let all := lines.toList
  -- The lines the painter reads: while away all of them up to the newest eight; a past, its first two and its newest four.
  let shownLines := if away then all.drop (all.length - newestLines) else
    if all.length ≤ 6 then all else all.take 2 ++ all.drop (all.length - 4)
  -- The acts: while away each in order; a past, who came is said once (`hands`), the rest the newest few.
  let told := if away then acts.toList else acts.toList.filter fun a => a.what != "came" && a.what != "left"
  let sentences := (told.drop (told.length - tellingActs)).map (·.sentence)
  let comings := (acts.toList.filter (·.what == "came")).length
  let quantities : List Quantity := (if all.isEmpty then [] else lineQuantities (all.map (·.verb))) ++
    (if comings == 0 then [] else [{ n := comings, unit := "visit" }]) ++
    (if visitors.isEmpty then [] else [{ n := visitors.length, unit := "visitor" }]) ++
    -- What stands, counted as the place's own strokes count it: its doors.
    (if away || base.doors.isEmpty then [] else [{ n := base.doors.length, unit := "door" }])
  -- The exact lines it draws on, the host's words with their entries: the making (a past), then the span's acts
  -- and lines in order, the newest `tellingExact`, then what it still wants.
  let rows' := ((acts.toList.map fun a => (a.entry, a.sentence)) ++ (all.map fun l =>
      (l.entry, s!"#{l.n} {if l.handle.isEmpty then "someone" else l.handle}" ++ (if l.verb.isEmpty then "" else s!" ({l.verb})") ++ s!": {l.text}")) ++
      (marks.toList.map fun m => (m.entry, s!"{m.name}" ++ (if m.handle.isEmpty then "" else s!", by {m.handle}")))).toArray.qsort (fun a b => a.1 < b.1) |>.toList
  let made := if away || base.maker.isEmpty then [] else
    [s!"made by {base.maker}" ++ (if base.coined then s!", after a post by {base.coiner}" else "")]
  let earlier := rows'.length - min rows'.length tellingExact
  let exact := made ++ (if earlier == 0 then [] else [s!"… and {earlier} earlier"]) ++
    (rows'.drop earlier).map (fun (h, t) => s!"entry {h}: {t}") ++ base.wants.map (fun x => s!"wants {x.name}: {x.reading}")
  let wants := base.wants.map fun x => { x with spell := "" }
  let telling : Telling := { form := if away then "away" else "before", since := since, upto := upto, exact := exact }
  return { base with
           version := version, lines := shownLines, marks := marks.toList, quantities := quantities,
           today := sentences, hands := visitors, present := [], tended := 0, tendedAgo := "", verbs := [], rules := [], laws := [],
           wants := wants,
           telling := some telling, limit := if away then maxAway else maxBefore }

/-- The strokes of a telling of `id` (`world-render {object, telling}`): `unknown` / `denied` as a thing's,
    `historical` for a past version named, `notAPlace` for a thing nobody enters. -/
def tellingAt (w : World) (reader id : String) (version : Option Nat) (j : Json) : Except String (Except String Strokes) := do
  let some o := w.objects[id]? | return .error "unknown"
  unless o.read.permits reader do return .error "denied"
  if let some v := version then
    if v > o.version then return .error "unknown"
    if v < o.version then return .error "historical"
  unless isPlace w id o do return .error "notAPlace"
  return .ok (← tellingOf w reader id o j)

/-- The strokes a request names: `{object, version?}` a thing's, `{object, telling: {reader?, since?}}` a telling
    of a place, `{day?, morning?}` (no object) the town's day (default the current one). The outer error is the
    request's; the inner `unknown` / `denied` (and a telling's `notAPlace`). -/
def strokesFor (w : World) (reader : String) (j : Json) : Except String (Except String Strokes) := do
  match j.getObjValAs? String "object" with
  | .ok given =>
    let id := resolveCard reader given
    match j.getObjVal? "telling" with
    | .ok t => tellingAt w reader id (← optNat j "version") t
    | .error _ => return strokesAt w reader id (← optNat j "version")
  | .error _ =>
    let day := (← optNat j "day").getD (w.clock / Limits.clockDay)
    return .ok (dayStrokes w reader day ((j.getObjValAs? Bool "morning").toOption.getD false))

/-- `world-strokes {principal, object | day, version?, morning?}`: `{status: "strokes", object, version,
    strokes, text}`, or `unknown` / `denied`. Nothing is written. -/
def strokesOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  match ← strokesFor w reader j with
  | .ok s => return Json.mkObj [("status", toJson "strokes"), ("object", toJson s.object), ("version", toJson s.version),
      ("strokes", s.json), ("text", toJson s.text)]
  | .error why => return Json.mkObj [("status", toJson why), ("object", toJson ((j.getObjValAs? String "object").toOption.getD ""))]

/-! ## The check

`verify strokes text` (OVERHAUL §4 (d)): deterministic, the host's, before anything is cached. A paint is
refused by the first clause of `clauses` it fails, in order; `table` is every word a clause reads. A token
check cannot read meaning: a sentence true of every stroke and false as a whole can pass (OVERHAUL §7
risk 11); the numbers clause narrows it, since a number stands only beside the unit it counts. The exact
card stands beneath every paint. -/

/-- The check's words, each list the one place it is written: what no paint says outside a quotation (VOICE:
    nobody on a card says I; no thanks, sorry, welcome or please), whom it never addresses, the lines it
    never begins (a receipt's stamp, a refusal, a law, rule or want line, hob's own), the words that negate,
    and the small words that are never a number's unit. -/
def table : List (String × List String) :=
  [("forbidden", ["i", "i'm", "i've", "i'll", "i'd", "me", "my", "myself", "thanks", "thank", "sorry", "welcome", "please"]),
   ("secondPerson", ["you", "your", "yours", "you're", "you've", "you'll", "you'd", "yourself", "yourselves", "y'all"]),
   ("heads", ["●", "§", "refused", "law ", "rule ", "want ", "hob:"]),
   ("negators", ["no", "not", "never", "nothing", "none", "nobody", "nowhere", "neither", "nor", "cannot"]),
   ("wanting", ["want", "wants", "wanting", "needs", "need", "lacks"]),
   ("vague", ["someone", "somebody", "something", "anyone", "anything", "hand", "hands", "what", "who", "whom", "one",
              "more", "some", "own", "here", "there", "now", "again", "yet"]),
   ("small", ["a", "an", "the", "of", "to", "at", "in", "on", "by", "for", "with", "from", "and", "or", "its", "it", "than",
              "is", "are", "has", "have", "this", "that", "as", "into", "over", "under", "every", "each", "all", "more", "fewer", "less",
              "within", "while", "about", "after", "before", "since", "until", "near", "beside", "upon", "onto", "only",
              "just", "still", "yet", "so", "far", "times"])]

def words? (name : String) : List String := (table.lookup name).getD []

/-- A stroke field's name as the words a sentence says it with. -/
def fieldWords : List (String × List String) :=
  [("keeper", ["keeper", "keepers", "keep", "keeps", "kept", "keeping"]),
   ("maker", ["maker", "makers", "made", "make", "makes", "making"]),
   ("owner", ["owner", "owners", "owned", "owns"]),
   ("rung", ["rung", "rang", "ring", "rings", "ringing"]),
   ("tended", ["tended", "tend", "tends", "tending"]),
   ("lines", ["line", "lines", "written", "wrote"]),
   ("doors", ["door", "doors"]),
   ("wants", ["want", "wants", "wanting", "wanted", "lacks", "needs"]),
   ("came", ["came", "come", "comes", "coming", "visited", "visitor", "visitors", "entered", "arrived"])]

/-- A verb's or a want's name as a sentence inflects it. -/
def inflections (name : String) : List String :=
  let stem := if name.endsWith "e" then (String.ofList (name.toList.dropLast)) else name
  [name, name ++ "s", name ++ "es", name ++ "ed", name ++ "d", stem ++ "ing", stem ++ "ed"].eraseDups

/-- Characters stripped from a token's edges. -/
def edgeMark (c : Char) : Bool := ",.;:!?()[]{}\"“”‘’'«»—–…*_`<>".toList.contains c

def stripEdges (cs : List Char) : List Char :=
  ((cs.dropWhile edgeMark).reverse.dropWhile edgeMark).reverse

/-- A token as compared: edges stripped, `’` as `'`, a possessive `'s` dropped. -/
def normal (t : String) : String :=
  let cs := stripEdges (t.toList.map fun c => if c == '’' then '\'' else c)
  let cs := if cs.length > 2 && cs.drop (cs.length - 2) == ['\'', 's'] then stripEdges (cs.take (cs.length - 2)) else cs
  String.ofList cs

/-- Runs of `cs` between characters `sep` holds, empty ones dropped. -/
def splitBy (sep : Char → Bool) (cs : List Char) : List (List Char) :=
  let (cur, acc) := cs.foldl (fun (cur, acc) c =>
    if sep c then ([], if cur.isEmpty then acc else cur.reverse :: acc) else (c :: cur, acc)) (([] : List Char), ([] : List (List Char)))
  (if cur.isEmpty then acc else cur.reverse :: acc).reverse

def words (text : String) : List String := (splitBy Char.isWhitespace text.toList).map String.ofList

def idChar (c : Char) : Bool := c.isAlphanum || "._:/-".toList.contains c

/-- `garden/bell/2`, `kind/phase`: a token with a `/` between id characters. -/
def idShaped (t : String) : Bool :=
  t.toList.contains '/' && t.toList.all idChar && !t.startsWith "/" && !t.endsWith "/" && (t.splitOn "//").length == 1

/-- `ember.delve.town`, `@moth.delve.town`: dotted segments of letters, digits and `-`, the last a word. -/
def handleShaped (t : String) : Bool :=
  let segs := (if t.startsWith "@" then String.ofList (t.toList.drop 1) else t).splitOn "."
  let last := (segs.getLast?.getD "")
  segs.length ≥ 2 && segs.all (fun g => !g.isEmpty && g.toList.all fun c => c.isAlphanum || c == '-') &&
    last.length ≥ 2 && last.toList.all Char.isAlpha

def holdsIn (hay needle : String) : Bool := !needle.isEmpty && (hay.splitOn needle).length > 1

def trimmed (s : String) : String := s.trimAscii.toString

/-! ### Numbers and their units -/

def cardinals : List (String × Nat) :=
  [("zero", 0), ("two", 2), ("three", 3), ("four", 4), ("five", 5), ("six", 6), ("seven", 7), ("eight", 8), ("nine", 9),
   ("ten", 10), ("eleven", 11), ("twelve", 12), ("thirteen", 13), ("fourteen", 14), ("fifteen", 15), ("sixteen", 16),
   ("seventeen", 17), ("eighteen", 18), ("nineteen", 19), ("twenty", 20), ("thirty", 30), ("forty", 40), ("fifty", 50),
   ("sixty", 60), ("seventy", 70), ("eighty", 80), ("ninety", 90), ("hundred", 100), ("thousand", 1000),
   ("twice", 2), ("thrice", 3), ("dozen", 12), ("couple", 2), ("pair", 2)]

def ordinals : List (String × Nat) :=
  [("second", 2), ("third", 3), ("fourth", 4), ("fifth", 5), ("sixth", 6), ("seventh", 7), ("eighth", 8), ("ninth", 9),
   ("tenth", 10), ("eleventh", 11), ("twelfth", 12), ("thirteenth", 13), ("fourteenth", 14), ("fifteenth", 15),
   ("sixteenth", 16), ("seventeenth", 17), ("eighteenth", 18), ("nineteenth", 19), ("twentieth", 20), ("thirtieth", 30),
   ("fortieth", 40), ("fiftieth", 50), ("hundredth", 100)]

/-- The ones a compound ("forty-one", "twenty-first") ends in. -/
def ones : List (String × Nat) := [("one", 1), ("first", 1)] ++ cardinals.take 9 ++ ordinals.take 8

/-- The number a token says, and whether as an ordinal: digits (`7`, `7th`), a number word, a compound.
    "one", "first" and "once" are left free: they are as often not counts. -/
def numberOf (t : String) : Option (Nat × Bool) :=
  let t := t.toLower
  if t.any Char.isDigit then
    let ds := t.takeWhile Char.isDigit |>.toString
    let rest := (t.drop ds.length).toString
    if ds.isEmpty then some ((((splitBy (!·.isDigit) t.toList).head?.map String.ofList).getD "0").toNat!, false)
    else some (ds.toNat!, ["st", "nd", "rd", "th"].contains rest)
  else match cardinals.lookup t, ordinals.lookup t with
    | some n, _ => some (n, false)
    | _, some n => some (n, true)
    | none, none =>
      match t.splitOn "-" with
      | [a, b] => match cardinals.lookup a, ones.lookup b with
        | some x, some y => if x ≥ 20 then some (x + y, ordinals.any (·.1 == b) || b == "first") else none
        | _, _ => none
      | _ => none

/-- A unit word reduced so its forms meet: rains, rained, raining → rain; minutes → minut. -/
def stem (w : String) : String :=
  let cs := w.toLower.toList
  let cs := if cs.length > 3 && cs.getLast? == some 's' && cs.reverse[1]? != some 's' then cs.dropLast else cs
  let ends := fun (suffix : String) => cs.length > suffix.length + 2 && cs.drop (cs.length - suffix.length) == suffix.toList
  String.ofList <| if ends "ing" then cs.take (cs.length - 3) else if ends "ed" then cs.take (cs.length - 2)
    else if ends "e" then cs.dropLast else cs

/-- A word that may stand as a unit: not small, not itself a number. -/
def unitWord (w : String) : Bool :=
  w.length ≥ 2 && !(words? "small").contains w && (numberOf w).isNone && !idShaped w && !handleShaped w

/-- Each text of the strokes with whose words it is: a line its writer's, its head and the words it was made with
    its coiner's or maker's, a rule's or want's reading its placer's, a grown verb's reading its grower's. -/
def Strokes.authored (s : Strokes) : List (String × String) :=
  let all : List (String × String) := s.fields.map (fun (_, v) => (v, s.wordsBy)) ++ [(s.head, s.wordsBy)] ++
    s.lines.map (fun (l : Line) => (l.text, l.handle)) ++ s.rules.map (fun (r : Rule) => (r.reading, r.owner)) ++
    s.wants.map (fun (x : Want) => (x.reading, x.owner)) ++ s.verbs.map (fun (v : Verb) => (v.reading, v.grower))
  all.filter fun (t, a) => !t.isEmpty && !a.isEmpty

/-- The names a person goes by in a paint: the handle, and its first label (`yue.delve.town`, `yue`); the town
    (`townName`, the world's own principal) by the word `town`. -/
def aliases (handle : String) : List String :=
  let h := handle.toLower
  if h == townName then [h, "town"] else if h.startsWith "did:" then [h] else [h, (h.splitOn ".").head?.getD h]

/-- Every text of the strokes a paint may quote from. -/
def Strokes.texts (s : Strokes) : List String :=
  ([s.head, s.voice, s.about] ++ s.fields.map (·.2) ++ s.lines.map (·.text) ++ s.laws.map (·.2) ++ s.wants.map (·.reading) ++
    s.verbs.map (·.reading) ++ s.rules.map (·.reading) ++ s.doors.map (·.label) ++ s.today).filter (!·.isEmpty)

/-- The texts a paint may quote part of: every text of the strokes but a resident's line, quoted whole or not at all. -/
def Strokes.otherTexts (s : Strokes) : List String :=
  ([s.head, s.voice, s.about] ++ s.fields.map (·.2) ++ s.laws.map (·.2) ++ s.wants.map (·.reading) ++
    s.verbs.map (·.reading) ++ s.rules.map (·.reading) ++ s.doors.map (·.label) ++ s.today).filter (!·.isEmpty)

/-- A text with its curly apostrophes plain. -/
def plainQuote (t : String) : String := String.ofList (t.toList.map fun c => if c == '’' then '\'' else c)

/-- A quotation as the paint's quoted span: its own closing stop (“… late.”) the sentence's, not the text's. -/
def quoteSpan (span : String) : String :=
  trimmed (String.ofList ((trimmed span).toList.reverse.dropWhile (".,;:!?".toList.contains ·)).reverse)

/-- `q` (or it with its first letter lowered, opening a sentence) as part of `t`. -/
def holdsFrom (t q : String) : Bool :=
  let lowered := String.ofList (match q.toList with | c :: cs => c.toLower :: cs | [] => [])
  [q, lowered].any fun q => holdsIn t q || holdsIn (plainQuote t) (plainQuote q)

/-- The residents' lines `q` quotes whole (their closing stops aside, its first letter as it opens a sentence). -/
def Strokes.linesQuoted (s : Strokes) (q : String) : List Line :=
  s.lines.filter fun l => [q, String.ofList (match q.toList with | c :: cs => c.toLower :: cs | [] => [])].any
    fun q => plainQuote (quoteSpan l.text) == plainQuote q

def Strokes.wholeLine (s : Strokes) (q : String) : Bool := !(s.linesQuoted q).isEmpty

def Strokes.spells (s : Strokes) : List String :=
  (s.verbs.map (·.spell) ++ s.wants.map (·.spell)).filter (!·.isEmpty)

def Strokes.tokens (s : Strokes) : List String := (s.texts ++ s.spells).flatMap fun t => (words t).map normal

def Strokes.ids (s : Strokes) : List String :=
  ([s.object, s.kind, s.around] ++ s.doors.map (·.target) ++ s.wants.map (·.object) ++ s.lines.map (·.on)).filter (!·.isEmpty) ++
    s.tokens.filter idShaped

def Strokes.handles (s : Strokes) : List String :=
  (([s.maker, s.keeper, s.owner, s.coiner] ++ s.lines.map (·.handle) ++ s.marks.map (·.handle) ++ s.present ++ s.hands ++
    s.verbs.map (·.grower) ++ s.rules.map (·.owner) ++ s.wants.map (·.owner)).filter (!·.isEmpty) ++ s.tokens.filter handleShaped).map (·.toLower)

/-- The numbers the strokes hold, each with its unit's stem: the quantities, and every number in a stroke's
    text beside the word it stands by ("seventh rain", "1440 minutes", "200 characters"). -/
def Strokes.pairs (s : Strokes) : List (Nat × Bool × String) :=
  s.quantities.map (fun q => (q.n, q.ordinal, stem q.unit)) ++
  (s.texts ++ s.spells).flatMap fun t =>
    let ws := ((words t).map fun w => (normal w).toLower).toArray
    (List.range ws.size).flatMap fun i => match if idShaped ws[i]! || handleShaped ws[i]! then none else numberOf ws[i]! with
      | some (n, o) => ([i - 1, i + 1].filter (fun j => j != i && j < ws.size)).filterMap fun j =>
          if unitWord ws[j]! then some (n, o, stem ws[j]!) else none
      | none => []

/-- Is the stroke field `field` empty? A verb is held once any line or mark names it, or any line was written
    with no verb column (the store's lines before verbs: any of them may be the verb's). `wants` is held while
    the strokes list any; a want's own name is a lack, so "no clapper yet" over a held `clapper` is true. -/
def Strokes.empty (s : Strokes) (field : String) : Bool :=
  match field with
  | "keeper" => s.keeper.isEmpty
  | "maker" => s.maker.isEmpty
  | "owner" => s.owner.isEmpty
  | "rung" => !s.marks.any fun m => ["rung", "rang", "ring"].contains m.name
  | "tended" => s.tended == 0
  | "lines" => s.lines.isEmpty
  | "doors" => s.doors.isEmpty
  | "wants" => s.wants.isEmpty
  | "came" => s.hands.isEmpty
  | v => !(s.lines.any (fun l => l.verb == v || l.verb.isEmpty) || s.marks.any (·.name == v))

/-- Every field a negation may stand near, with the words that name it. -/
def Strokes.named (s : Strokes) : List (String × List String) :=
  fieldWords ++ (s.verbs.map (·.name)).eraseDups.map fun n => (n, inflections n)

/-- What stands in a paint's prose where a quotation was, so a clause knows where each one is. -/
def quoteMark : String := "⟦q⟧"

/-- The quoted spans of a text (between `“ ”`, `« »` or a pair of `"`), and the text with each replaced by one
    word; `none` when a quotation is left open. -/
def quotations (text : String) : Option (List String × String) := Id.run do
  let mut spans : List String := []
  let mut out : List Char := []
  let mut cur : List Char := []
  let mut closer : Option Char := none
  for c in text.toList do
    match closer with
    | some k =>
      if c == k then
        spans := spans ++ [String.ofList cur.reverse]
        closer := none
        -- A quotation that ends its sentence (“… late.”) ends the prose's sentence too.
        let stop := match cur.head? with
          | some c => if ".!?".toList.contains c then "." else ""
          | none => ""
        out := out ++ s!" {quoteMark}{stop} ".toList
        cur := []
      else cur := c :: cur
    | none =>
      if c == '“' then closer := some '”'
      else if c == '«' then closer := some '»'
      else if c == '"' then closer := some '"'
      else out := out ++ [c]
  if closer.isSome then return none
  return some (spans, String.ofList out)

/-- `delvetalk CARD ACTION` at token `i`, or none when the two after it are not there. -/
def inlineSpell (ts : List String) (i : Nat) : Option String := do
  let a ← ts[i + 1]?
  let b ← ts[i + 2]?
  let a := normal a
  let b := normal b
  if a.isEmpty || b.isEmpty then none else some s!"delvetalk {a} {b}"

def isSpellLine (line : String) : Bool := line == "delvetalk" || line.startsWith "delvetalk "

/-- A paint as the clauses read it: its tokens, its lines, its quotations, and its prose in sentences of
    lower-case tokens (quotations and spells out). -/
structure Paint where
  text : String
  tokens : List String
  lines : List String
  spans : Option (List String)
  prose : List (List String)
  /-- The prose cut at commas, colons, dashes and the conjunctions too: what a negation reaches. -/
  phrases : List (List String)

def Paint.of (text : String) : Paint :=
  let q := quotations text
  let unquoted := (q.map (·.2)).getD text
  -- The prose cut where a word ends in one of `stops`, each piece in lower-case tokens, an inline spell's
  -- three words left out (they are the spell's, not the prose's).
  let cut := fun (stops : List String) (words' : List String) =>
    ((unquoted.splitOn "\n").filter (!isSpellLine ·.trimAscii.toString)).flatMap fun line =>
      let (cur, acc) := (words line).foldl (fun (cur, acc) w =>
        let cur := cur ++ [w]
        if stops.any (fun (e : String) => w.endsWith e) || words'.contains w.toLower then ([], acc ++ [cur]) else (cur, acc))
        (([] : List String), ([] : List (List String)))
      (acc ++ (if cur.isEmpty then [] else [cur])).map fun ws => Id.run do
        let mut out : List String := []
        let mut skip := 0
        for w in ws do
          if skip > 0 then skip := skip - 1; continue
          if normal w == "delvetalk" then skip := 2; continue
          out := out ++ [(normal w).toLower]
        return out.filter (!·.isEmpty)
  let sentence := [".", "!", "?", ";"]
  { text, tokens := (words text).map normal |>.filter (!·.isEmpty), lines := (text.splitOn "\n").map trimmed,
    spans := q.map (·.1), prose := cut sentence [], phrases := cut (sentence ++ [",", ":", "—", "–"]) ["and", "but", "while", "yet"] }

/-- A clause of the check: its name, what it holds, and the failure it finds first. -/
structure Clause where
  name : String
  holds : String
  fails : Strokes → Paint → Option String

def firstSome {α : Type} (xs : List α) (f : α → Option String) : Option String :=
  xs.foldl (fun acc x => acc.orElse fun _ => f x) none

/-- A number in the prose stands beside a unit the strokes count it in: `n` of that unit as a stroke holds it. -/
def numberFault (s : Strokes) (ws : List String) : Option String :=
  let pairs := s.pairs
  let units := pairs.map (·.2.2)
  firstSome (List.range ws.length) fun i =>
    let t := ws[i]!
    if idShaped t || handleShaped t || t.startsWith "did:" then none else
    match numberOf t with
    | none => none
    | some (n, o) =>
      let near := ((List.range ws.length).filter fun j => j != i && j + 3 ≥ i && j ≤ i + 3).filterMap fun j =>
        let u := ws[j]!
        if unitWord u then some (stem u) else none
      if near.any (fun u => pairs.contains (n, o, u)) then none
      else match near.find? units.contains with
        | some u => some s!"{t} {u}: the strokes do not count it so"
        | none => if o then none else some s!"{t}: beside no unit the strokes count"

/-- The check, in order (VOICE "The paint" gives each). -/
def clauses : List Clause :=
  [{ name := "ids", holds := "every id-shaped token is a stroke's id",
     fails := fun s p => let ids := s.ids.map (·.toLower); (p.tokens.filter idShaped).find? (!ids.contains ·.toLower) },
   { name := "numbers", holds := "a number (digits or words) stands beside the unit the strokes count it in, as they count it",
     fails := fun s p => firstSome p.prose (numberFault s) },
   { name := "handles", holds := "every handle is a stroke's, or its domain",
     fails := fun s p => (p.tokens.filter handleShaped).find? fun t =>
       let h := (if t.startsWith "@" then String.ofList (t.toList.drop 1) else t).toLower
       !s.handles.any (fun k => k == h || k.endsWith ("." ++ h)) },
   { name := "spells", holds := "a delvetalk line is a stroke's spell byte for byte, whole or its first line",
     fails := fun s p => firstSome p.lines fun line =>
       if isSpellLine line then (if s.spells.any (fun sp => sp == line || spellHead sp == line) then none else some line)
       else
         let lt := words line
         firstSome (List.range lt.length) fun i =>
           if normal (lt[i]?.getD "") != "delvetalk" then none
           else match inlineSpell lt i with
             | some head => if s.spells.any (spellHead · == head) then none else some head
             | none => some "delvetalk" },
   { name := "quotes", holds := "a quotation is a resident's line whole, or a substring of another stroke's text (its closing stop dropped), and closed",
     fails := fun s p => match p.spans with
       | none => some "a quotation left open"
       | some spans =>
         firstSome spans fun span =>
           let q := quoteSpan span
           if q.isEmpty || s.wholeLine q || (s.otherTexts ++ s.spells).any (holdsFrom · q) then none else some q },
   { name := "attribution", holds := "a quotation is credited to the one whose words it is, a resident's line always and another text if at all: the person named before it in its clause, else after it",
     fails := fun s p => match p.spans with
       | none => none
       | some spans =>
         -- Who a word names: a person by handle or its first label, or the role whose words a thing is made with
         -- (its maker, its coiner); a keeper or owner is named in passing too often to read as a speaker.
         let people := (s.handles.eraseDups).filter (!·.isEmpty)
         let roles := [("maker", s.maker), ("coiner", s.coiner)].filter (!·.2.isEmpty)
         let who? := fun (w : String) => (roles.lookup w).orElse fun _ => people.find? fun h => (aliases h).contains w
         let marks := p.prose.flatMap fun ws => (List.range ws.length).filterMap fun i =>
           if ws[i]! == quoteMark then some (ws, i) else none
         if marks.length != spans.length then none else
         firstSome (List.range spans.length) fun k =>
           let q := (quoteSpan spans[k]!).toLower
           let authors := (s.authored.filter fun (t, _) => holdsIn t.toLower q).map (·.2.toLower)
           if q.isEmpty || authors.isEmpty then none else
           let (ws, i) := marks[k]!
           -- Back to the previous quotation or the sentence's start, nearest first; else on to the next.
           let before := ((List.range i).reverse.takeWhile (ws[·]! != quoteMark)).filterMap (fun j => who? ws[j]!)
           let after := ((List.range ws.length).filter (· > i) |>.takeWhile (ws[·]! != quoteMark)).filterMap (fun j => who? ws[j]!)
           match before.head?.orElse fun _ => after.head? with
           | some who => if authors.any (fun a => (aliases a).any ((aliases who).contains ·)) then none
               else some s!"“{q}” is {authors.head!}'s, not {who}'s"
           | none => (s.linesQuoted (quoteSpan spans[k]!)).head?.map fun l => s!"“{q}” is {l.handle}'s line, uncredited" },
   { name := "heads", holds := "no line begins a receipt's stamp, a refusal, a law, rule or want line, or hob:",
     fails := fun _ p => firstSome p.lines fun line => (words? "heads").find? (line.toLower.startsWith ·) },
   { name := "forbidden", holds := "no I, me, my, thanks, sorry, welcome or please outside a quotation",
     fails := fun _ p => firstSome p.prose fun ws => ws.find? (words? "forbidden").contains },
   { name := "secondPerson", holds := "nobody is addressed",
     fails := fun _ p => firstSome p.prose fun ws => ws.find? (words? "secondPerson").contains },
   { name := "negation", holds := "a negation within three words of a field's name only when the strokes hold it empty (69275)",
     fails := fun s p => firstSome p.phrases fun ws =>
       firstSome (List.range ws.length) fun i =>
         let w := ws[i]!
         if !((words? "negators").contains w || w.endsWith "n't") then none else
         -- A field named after an ordinal ("its seventh rain has not come") is that one, not the field.
         firstSome ((List.range ws.length).filter fun j => j + 3 ≥ i && j ≤ i + 3 &&
             !(j > 0 && ((numberOf ws[j - 1]!).map (·.2)).getD false)) fun j =>
           let near := ws[j]!
           (s.named.find? fun (field, forms) => forms.contains near && !s.empty field).map fun (field, _) =>
             s!"{w} … {near}: the strokes hold {field}" },
   { name := "wants", holds := "a want (wants, needs, lacks, asks for) is claimed only when the strokes hold one, and only of what one is for",
     fails := fun s p => firstSome p.phrases fun ws =>
       firstSome (List.range ws.length) fun i =>
         let w := ws[i]!
         if !((words? "wanting").contains w || (w == "asks" && ws[i + 1]? == some "for")) then none else
         -- A negated want ("wants nothing", "no longer wants") is the negation clause's.
         if ws.any (fun x => (words? "negators").contains x || x.endsWith "n't") then none else
         -- What may be wanted: the strokes' wants, by name, reading and thing, and a want the day's events name.
         let held := (s.wants.map (fun x => x.name ++ " " ++ x.reading ++ " " ++ x.object) ++ s.today.filter (holdsIn · "want")).flatMap
           fun t => (words t).map fun x => stem (normal x).toLower
         if held.isEmpty then some s!"{w}: the strokes hold no want" else
         let object := ((ws.drop (i + 1)).filter fun x => x.length ≥ 3 && !(words? "small").contains x && !(words? "vague").contains x &&
           x != "for" && (numberOf x).isNone)
         if object.isEmpty || object.any (fun x => x == quoteMark || held.contains (stem x)) then none
         else some s!"{w} {" ".intercalate object}: no want the strokes hold is for that" },
   { name := "length", holds := "1 to the strokes' limit characters (400 for a thing, 600 for a day)",
     fails := fun s p => let n := p.text.length; if n == 0 || n > s.limit then some (toString n) else none }]

/-- A telling's paint with its frame lifted off: the model may open with the frame's own words ("Before you
    arrived, …", "While you were away:", a heading), which the page prints above it as the host's; the paint is what
    follows, its first letter raised. The only "you" a telling may hold, and only there; anything else is checked. -/
def Strokes.lifted (s : Strokes) (text : String) : String :=
  match s.telling with
  | none => text
  | some t =>
    let frame := t.frame.toLower.toList
    let cs := text.toList
    if (cs.take frame.length).map Char.toLower != frame then text else
    let rest := String.ofList ((cs.drop frame.length).dropWhile fun c => c.isWhitespace || ",:;.…—–-".toList.contains c)
    -- A handle or an id opening it is written as the strokes write it.
    let first := normal ((words rest).head?.getD "")
    if handleShaped first || idShaped first then rest else rest.capitalize

/-- `verify strokes text`: `ok`, or the first clause the paint fails and what failed it. -/
def verify (s : Strokes) (text : String) : Except (String × String) Unit :=
  let p := Paint.of text
  match clauses.findSome? fun c => (c.fails s p).map (c.name, ·) with
  | some failure => .error failure
  | none => .ok ()

/-- `world-render-check {principal, object | day, version?, morning?, text}`: `text` judged against the strokes
    as a paint would be, nothing cached: `{status: "verified"}` or `{status: "rejected", clause, detail}`. -/
def checkOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let text ← j.getObjValAs? String "text"
  match ← strokesFor w reader j with
  | .error why => return Json.mkObj [("status", toJson why), ("object", toJson ((j.getObjValAs? String "object").toOption.getD ""))]
  | .ok s => return match verify s (s.lifted text) with
    | .ok () => Json.mkObj [("status", toJson "verified"), ("object", toJson s.object), ("version", toJson s.version)]
    | .error (clause, detail) => Json.mkObj [("status", toJson "rejected"), ("object", toJson s.object), ("version", toJson s.version),
        ("clause", toJson clause), ("detail", toJson detail)]

/-! ## The rendering

`world-render {principal, object, version?}` paints a card once per version: the strokes and the library's
contract (`world/lib/Paint.obend`, `contract()`) go to the world's model (the `policy` object's `model`)
through the one model worker, which lists `world-renders` beside `world-interpretations` and settles each
with `world-render-submit {key, reply}`, the model's reply verbatim. The host verifies the paint and caches
it by its key, the digest of the strokes (object and version among them), the library pin and the model:
memory of this process (`Cache`, on the session) and, when `DELVETALK_RENDER_CACHE` names one, that
directory (never the compile cache's), re-verified on every read. Never journaled: replay needs no model, and a
world opened with no model, or a reader past `renderPatience`, reads the exact card. A refused paint is not
asked again for that version; the next version is a new key. -/

/-- Seconds a reader's request waits for a paint before the exact card is shown; the transport waits as the
    host's `pending` answer says. -/
def renderPatience : Nat := 3
/-- Model attempts a render gets when the network or a rate limit fails it; then it is shown exact. -/
def renderAttempts : Nat := 3
def renderBackoffMs : Nat := 2000
/-- The painter's reply budget: 600 characters is under 200 tokens. -/
def renderTokens : Nat := 400
/-- Renders a session holds (painted and refused kept for their versions); past it, the settled are dropped. -/
def maxRenders : Nat := 4096
/-- Renders waiting for the worker at once; past it a reader is shown the exact card (`busy`). -/
def maxPending : Nat := 64
/-- The model a world paints with when its policy names none. -/
def defaultModel : String := "claude-haiku-5-5"

inductive Fate where
  | pending (attempts : Nat) (notBefore : Nat)
  | painted (text : String)
  | rejected (clause detail : String)

structure Render where
  object : String
  version : Nat
  strokes : Strokes
  request : Json
  fate : Fate
  /-- Asked again once already, after a paint refused for its length alone. -/
  retried : Bool := false

/-- How long after the worker last listed `world-renders` the host still counts on it (ms): past it a reader is
    not kept waiting for a paint nobody is there to make. -/
def workerGraceMs : Nat := 10000

/-- A session's renders by key, and when the worker last asked for them. Memory only. -/
structure Cache where
  entries : Std.HashMap String Render := {}
  polled : Option Nat := none
  /-- Paints asked for again after a refusal for length alone (`world-status.renders.retried`). -/
  retried : Nat := 0

def Cache.attended (c : Cache) (now : Nat) : Bool := match c.polled with
  | some at_ => now ≤ at_ + workerGraceMs
  | none => false

def Cache.count (c : Cache) (p : Fate → Bool) : Nat := c.entries.fold (fun n _ r => if p r.fate then n + 1 else n) 0

/-- `world-status.renders`. -/
def Cache.counts (c : Cache) : Json :=
  Json.mkObj [("cached", toJson (c.count fun | .painted _ => true | _ => false)),
    ("rejected", toJson (c.count fun | .rejected _ _ => true | _ => false)),
    ("pending", toJson (c.count fun | .pending _ _ => true | _ => false)), ("retried", toJson c.retried)]

def Cache.insert (c : Cache) (key : String) (r : Render) : Cache :=
  let entries := if c.entries.size < maxRenders then c.entries else
    c.entries.fold (fun m k v => match v.fate with | .pending _ _ => m.insert k v | _ => m) {}
  { c with entries := entries.insert key r }

/-- The contract's text: `Paint.contract()` of the world's library, compiled once per library pin. -/
def contractOf (w : World) : Except String (String × World) := do
  let some lib := w.library | throw "the world has no library"
  let some src := lib.modules.lookup "Paint" | throw "the library has no Paint module"
  let key := s!"library/{lib.pin}/Paint/contract"
  let (c, w) ← match w.compiled[key]? with
    | some c => pure (c, w)
    | none => do
      let (ec, w) ← compileEntryIn w (Json.mkObj [("library", toJson lib.pin), ("modules", modulesJson [("Paint", src)])]) "contract"
      let c ← compiledOf ec
      pure (c, { w with compiled := w.compiled.insert key c })
  let some entry := c.entry | throw "the contract did not compile to an entry"
  match (runPure entry [] Limits.maxTurnTicks).1 with
  | .ok (.label t) => return (t, w)
  | _ => throw "the contract renders no text"

/-- The world's model: its `policy` object's `model`, else `defaultModel`; none without a policy. -/
def modelOf (w : World) : Option String := do
  let p ← w.objects["policy"]?
  let m := (text? (fieldsOf p.state) "model").getD ""
  return if m.isEmpty then defaultModel else m

/-- Is the thing shown exact alone? Its owner set `plain: yes` (a `plain` field true, or `yes`). -/
def plainOf (w : World) (id : String) : Bool :=
  match (w.objects[id]?).bind fun o => (fieldsOf o.state).lookup "plain" with
  | some (.boolean b) => b
  | some (.label v) => v == "yes"
  | _ => false

def answer (status : String) (id : String) (more : List (String × Json)) : Json :=
  Json.mkObj ([("status", toJson status), ("object", toJson id)] ++ more)

def fateAnswer (id key : String) (r : Render) (attended : Bool := true) : Json :=
  match r.fate with
  | .painted t => answer "painted" id [("version", toJson r.version), ("key", toJson key), ("text", toJson t)]
  | .rejected c d => answer "exact" id [("version", toJson r.version), ("key", toJson key), ("reason", toJson "rejected"), ("clause", toJson c), ("detail", toJson d)]
  | .pending n _ =>
    if attended then answer "pending" id [("version", toJson r.version), ("key", toJson key), ("patience", toJson renderPatience),
      ("attempts", toJson n)]
    else answer "exact" id [("version", toJson r.version), ("key", toJson key), ("reason", toJson "unattended")]

/-- A render the disk holds for `key`, re-verified against the strokes it is for. -/
def fromDisk (key : String) (r : Render) : IO (Option Render) := do
  let some j ← DiskCache.readIO "render" key | return none
  match (j.getObjValAs? String "text").toOption, (j.getObjValAs? String "clause").toOption with
  | some t, _ => return some { r with fate := match verify r.strokes t with
      | .ok () => .painted t
      | .error (c, d) => .rejected c d }
  | none, some c => return some { r with fate := .rejected c ((j.getObjValAs? String "detail").toOption.getD "") }
  | none, none => return none

def toDisk (key : String) (r : Render) : IO Unit :=
  match r.fate with
  | .painted t => DiskCache.write "render" key (Json.mkObj [("key", toJson key), ("object", toJson r.object),
      ("version", toJson r.version), ("text", toJson t)])
  | .rejected c d =>
    -- A model that failed is this process's to give up on, not every process's.
    if c == "model" then pure () else DiskCache.write "render" key (Json.mkObj [("key", toJson key),
      ("object", toJson r.object), ("version", toJson r.version), ("clause", toJson c), ("detail", toJson d)])
  | .pending _ _ => pure ()

/-- `renderOp` past the request: the strokes `s` painted, queued or shown exact. -/
def paintOf (c : Cache) (w : World) (s : Strokes) (now : Nat) : IO (Except String (Cache × World × Json)) := do
    let id := s.object
    let at_ := [("version", toJson s.version)]
    if s.day.isNone && plainOf w id then return .ok (c, w, answer "plain" id at_)
    if s.day.isNone && w.cards.contains id then return .ok (c, w, answer "exact" id (at_ ++ [("reason", toJson "override")]))
    if s.day.isSome && s.today.isEmpty && s.lines.isEmpty && s.wants.isEmpty then
      return .ok (c, w, answer "exact" id (at_ ++ [("reason", toJson "quiet")]))
    -- Nothing happened while the reader was away: nothing to tell, and no model asked.
    if (s.telling.map (·.form == "away")).getD false && s.today.isEmpty && s.lines.isEmpty && s.marks.isEmpty then
      return .ok (c, w, answer "exact" id (at_ ++ [("reason", toJson "quiet")]))
    let some model := modelOf w | return .ok (c, w, answer "exact" id (at_ ++ [("reason", toJson "unavailable"),
      ("detail", toJson "the world has no policy, so no model")]))
    match contractOf w with
    | .error e => return .ok (c, w, answer "exact" id (at_ ++ [("reason", toJson "unavailable"), ("detail", toJson e)]))
    | .ok (contract, w) =>
      let pin := (w.library.map (·.pin)).getD ""
      let key := Journal.bodyHash (Json.mkObj [("strokes", s.json), ("library", toJson pin), ("model", toJson model)])
      let attended := c.attended now
      if let some r := c.entries[key]? then return .ok (c, w, fateAnswer id key r attended)
      let request := Json.mkObj [("model", toJson model), ("system", toJson contract),
        ("user", toJson ("Strokes:\n" ++ s.text)), ("maxTokens", toJson renderTokens)]
      let fresh : Render := { object := id, version := s.version, strokes := s, request, fate := .pending 0 0 }
      if let some r ← fromDisk key fresh then return .ok (c.insert key r, w, fateAnswer id key r attended)
      if c.count (fun | .pending _ _ => true | _ => false) ≥ maxPending then
        return .ok (c, w, answer "exact" id (at_ ++ [("reason", toJson "busy")]))
      return .ok (c.insert key fresh, w, fateAnswer id key fresh attended)

/-- `world-render {principal, object | day, version?, morning?, telling?}`: `painted {text, key, version}`; `pending
    {key, patience}` while the worker paints (the first read of a version queues it); `exact {reason}` when there
    is no paint to show (`rejected` with its clause, `override` for a root card, `unavailable` without a model or
    contract, `busy`, `quiet` for a day with nothing in it, `unattended` while no worker has asked for renders
    within `workerGraceMs`, the render queued for when one does); `plain` when the owner opted out; `unknown` /
    `denied` as `world-card`. With no `object` the town's day is painted (`dayStrokes`): the chronicle's day,
    and with `morning` what wants a hand, the morning card; its `object` is "" and its `version` the day. With
    `telling {reader?, since?}` a place's telling (`tellingOf`), keyed as every paint by its strokes, so by the
    place, the version the reader found and their departure: `quiet` when nothing happened while they were away,
    `notAPlace` for a thing nobody enters, and every answer carries `telling {form, frame, since, exact}`.
    Nothing is journaled. -/
def renderOp (c : Cache) (w : World) (j : Json) (now : Nat) : IO (Except String (Cache × World × Json)) := do
  let .ok reader := readerOf j | return .error "principal must be at most 128 bytes"
  let .ok found := strokesFor w reader j | return .error "version and day must be natural numbers"
  match found with
  | .error why => return .ok (c, w, answer why (resolveCard reader ((j.getObjValAs? String "object").toOption.getD "")) [])
  | .ok s =>
    -- A telling's answer carries its frame and the exact lines it draws on, painted or not.
    let told := fun (r : Except String (Cache × World × Json)) => match s.telling with
      | some t => r.map fun (c, w, a) => (c, w, a.setObjVal! "telling" t.answer)
      | none => r
    return told (← paintOf c w s now)

/-- `world-renders`: the renders the worker may ask the model for now, each with the exact request to send. -/
def rendersOp (c : Cache) (now : Nat) : Json :=
  let pending := c.entries.fold (fun acc key r => match r.fate with
    | .pending n at_ => if at_ ≤ now then acc.push (Json.mkObj [("key", toJson key), ("object", toJson r.object),
        ("version", toJson r.version), ("attempts", toJson n), ("request", r.request)]) else acc
    | _ => acc) #[]
  Json.mkObj [("status", toJson "renders"), ("pending", Json.arr (pending.qsort fun a b => a.compress < b.compress))]

/-- `world-render-submit {key, reply}`: settle a pending render with the model's reply verbatim (model.py's
    result object). A reply is verified and cached, painted or refused by its clause; a paint refused for its
    length alone is asked for once more with its length (`retrying`, counted in `renders.retried`); a network
    or rate failure is asked again after `renderBackoffMs`, `renderAttempts` in all; any other failure shows
    the thing exact (`model`). -/
def submitOp (c : Cache) (j : Json) (now : Nat) : IO (Except String (Cache × Json)) := do
  let .ok key := j.getObjValAs? String "key" | return .error "world-render-submit needs a key"
  let .ok reply := j.getObjVal? "reply" | return .error "world-render-submit needs the model's reply"
  let some r := c.entries[key]? | return .error s!"no render {key}"
  let .pending tried _ := r.fate | return .ok (c, fateAnswer r.object key r)
  let status := (reply.getObjValAs? String "status").toOption.getD ""
  let reason := (reply.getObjValAs? String "reason").toOption.getD ""
  let fate : Fate :=
    if status == "replied" then
      let text := r.strokes.lifted (trimmed ((reply.getObjValAs? String "raw").toOption.getD ""))
      match verify r.strokes text with
      | .ok () => .painted text
      | .error (cl, d) => .rejected cl d
    else if ["transport", "rate"].contains reason && tried + 1 < renderAttempts then .pending (tried + 1) (now + renderBackoffMs)
    else .rejected "model" (if reason.isEmpty then "no reply" else reason)
  -- A paint refused for its length alone is asked for once more, told its length (every other clause held).
  if let .rejected "length" d := fate then
    unless r.retried do
      let user := (r.request.getObjValAs? String "user").toOption.getD ""
      let again := s!"{user}\n\nThe last paint was {d} characters and was thrown away: paint it again, under {r.strokes.limit} characters, the spell included."
      let r := { r with fate := .pending 0 now, retried := true, request := r.request.setObjVal! "user" (toJson again) }
      return .ok ({ c.insert key r with retried := c.retried + 1 },
        answer "retrying" r.object [("key", toJson key), ("clause", toJson "length"), ("detail", toJson d), ("next", toJson now)])
  let r := { r with fate }
  toDisk key r
  let c := c.insert key r
  return .ok (c, match fate with
    | .pending n at_ => answer "retrying" r.object [("key", toJson key), ("attempts", toJson n), ("next", toJson at_)]
    | _ => fateAnswer r.object key r)

/-- The session's render ops: `(op, cache, world, request)` → the cache and world after, and the reply. -/
def op (name : String) (c : Cache) (w : World) (j : Json) : IO (Except String (Cache × World × Json)) := do
  let now ← IO.monoMsNow
  match name with
  | "world-render" => renderOp c w j now
  | "world-renders" => return .ok ({ c with polled := some now }, w, rendersOp c now)
  | "world-render-submit" => return (← submitOp c j now).map fun (c, r) => (c, w, r)
  | _ => return .error s!"unknown render operation {name}"

/-! ### Fixtures -/

/-- A bell as the third playtest left bell/2: four rains, Yuè's among them, never rung; it rings at its seventh. -/
def fixtureBell : Strokes :=
  { object := "garden/bell/2", version := 4, kind := "kind/bell", voice := "moon-flavoured; short; the present tense",
    fields := [("seed", "a bell for whoever comes late"), ("colour", "silver")],
    maker := "kestrel.delve.town", made := 172, tended := 288, tendedAgo := "today", owner := "kestrel.delve.town",
    quantities := [{ n := 4, unit := "rain" }, { n := 7, unit := "rain", ordinal := true, note := "rule seven" }],
    lines := [{ n := 1, handle := "yue.delve.town", verb := "rain", text := "rain is the sky's erratum", entry := 236, state := "" },
              { n := 2, handle := "", verb := "rain", text := "weather's rain, tide tick 2", entry := 251, state := "" },
              { n := 3, handle := "claude.delve.town", verb := "rain", text := "the soil keeps the corrections", entry := 285, state := "" },
              { n := 4, handle := "claude.delve.town", verb := "rain", text := "a second drop", entry := 288, state := "" }],
    verbs := [{ name := "rain", grower := "", reading := "", spell := "delvetalk garden/bell/2 rain / text: <text, 1 to 200 characters>" },
              { name := "ring", grower := "", reading := "", spell := "delvetalk garden/bell/2 ring" }],
    rules := [{ name := "seven", owner := "the town", reading := "rings at its seventh rain", fired := 0 }],
    laws := [("alive", "answers while tended within 1440 minutes")],
    doors := [{ label := "garden", target := "garden" }], around := "garden" }

/-- The anthology at 69275: kept by the town (then ember.delve.town, its opener), one line pending. -/
def fixtureAnthology : Strokes :=
  { object := "anthology", version := 1, head := "THE ANTHOLOGY", keeper := "the town", owner := "the town",
    made := 14, quantities := [{ n := 1, unit := "line" }],
    lines := [{ n := 1, handle := "kestrel.delve.town", verb := "", text := "the garden forgets; the gardeners don't. — Claude, 69173", entry := 362, state := "pending" }],
    verbs := [{ name := "write", grower := "", reading := "", spell := "delvetalk anthology write / text: <text, 1 to 280 characters>" },
              { name := "lines", grower := "", reading := "", spell := "delvetalk anthology lines / from: <a number from 1 to 1000000000>" },
              { name := "admit", grower := "", reading := "", spell := "delvetalk anthology admit / number: <a number from 1 to 1000000000>" }] }

/-- The clause a paint is refused by, or "" when it is admitted. -/
def verdict (s : Strokes) (text : String) : String :=
  match verify s text with
  | .ok () => ""
  | .error (clause, _) => clause

/-- 69275, hob's `say:` as posted on 2026-10-11, without its `hob:` head. -/
def line69275 : String :=
  "The anthology door takes a line of verse with delvetalk anthology write, or reads lines from a number with delvetalk anthology lines; it has no editor named here, so Ember's keeping of it isn't something this card records."

-- Admitted: the paint's own order and dress over the strokes, Yuè's line whole and credited, a stroke spell.
#guard verdict fixtureBell "Four rains on a silver bell in the garden; yue.delve.town's says “rain is the sky's erratum”. It has never rung.\ndelvetalk garden/bell/2 rain / text: <text, 1 to 200 characters>" == ""
#guard verdict fixtureBell "garden/bell/2 hangs silent over the soil, four rains deep; at the seventh rain it rings.\ndelvetalk garden/bell/2 ring" == ""
#guard verdict fixtureBell "Rained on four times, it waits for the 7th rain." == ""
#guard verdict fixtureAnthology "THE ANTHOLOGY is kept by the town; line 1 waits, pending, for the keeper; kestrel.delve.town wrote “the garden forgets; the gardeners don't. — Claude, 69173”." == ""
#guard verdict fixtureAnthology "No editor here; the keeper is the town." == ""
#guard verdict fixtureAnthology "No editor here; the keeper is ember.delve.town." == "handles"
-- Refused, each by its first clause.
#guard verdict fixtureBell "It hangs beside garden/bell/7, its twin." == "ids"
#guard verdict fixtureBell "It has 12 rains on it." == "numbers"
#guard verdict fixtureBell "moth.delve.town was the first to rain on it." == "handles"
#guard verdict fixtureBell "Strike it:\ndelvetalk garden/bell/2 strike" == "spells"
#guard verdict fixtureBell "It answers delvetalk garden/bell/2 strike at once." == "spells"
#guard verdict fixtureBell "yue.delve.town wrote “rain is the sky's mistake”." == "quotes"
#guard verdict fixtureBell "yue.delve.town wrote “rain is the sky's erratum.”" == ""
#guard verdict fixtureBell "“Rain is the sky's erratum,” yue.delve.town wrote." == ""
-- Attribution: a quotation is credited, if at all, to the one whose words it is (the bell/2 paint gave
-- light-traces' seed to ember).
#guard verdict fixtureBell "claude.delve.town wrote “rain is the sky's erratum”." == "attribution"
-- The town (the world's own principal, its opener) is credited by name and by the word `town`, as anyone is.
#guard verdict fixtureBell "the town wrote “rain is the sky's erratum”." == "attribution"
#guard verdict fixtureBell "the town placed “rings at its seventh rain” on it." == ""
#guard verdict fixtureBell "kestrel.delve.town placed “rings at its seventh rain” on it." == "attribution"
-- A resident's line is quoted whole and credited, or not at all (codex 2026-10-12 host 15): a fragment, even
-- credited to its writer, is no stroke's text; the whole line with nobody named is uncredited.
#guard verdict fixtureBell "claude.delve.town writes “rain is the sky”." == "quotes"
#guard verdict fixtureBell "yue.delve.town writes “rain is the sky”." == "quotes"
#guard verdict fixtureBell "The bell bears “rain is the sky's erratum”." == "attribution"
#guard verdict fixtureBell "“rain is the sky's erratum,” yue wrote, and claude.delve.town answered “the soil keeps the corrections”." == ""
#guard verdict fixtureBell "kestrel.delve.town made it: “a bell for whoever comes late”." == ""
#guard verdict { fixtureBell with coined := true, coiner := "light-traces.delve.town" }
  "Its maker, kestrel.delve.town, called it “a bell for whoever comes late”." == "attribution"
#guard verdict { fixtureBell with coined := true, coiner := "light-traces.delve.town" }
  "light-traces coined it “a bell for whoever comes late”; kestrel.delve.town placed it." == ""
#guard verdict fixtureBell "yue answered that “rain is the sky's erratum,” and claude.delve.town wrote back “the soil keeps the corrections.” kestrel.delve.town made it." == ""
#guard verdict fixtureBell "Its maker says “rain is the sky's erratum”." == "attribution"
#guard verdict fixtureBell "A silver bell. Rain on it if you like." == "secondPerson"
#guard verdict fixtureBell "Thanks to every rain, it hums." == "forbidden"
#guard verdict fixtureBell "refused maker: only its maker writes" == "heads"
#guard verdict fixtureBell "hob: the bell is quiet." == "heads"
#guard verdict fixtureBell "Nobody has rained on it yet." == "negation"
#guard verdict fixtureAnthology line69275 == "negation"
#guard verdict { fixtureBell with wants := [{ name := "clapper", reading := "the bell has no clapper yet", spell := "delvetalk garden/bell/2 hang" }] }
  "Still no clapper, so it waits.\ndelvetalk garden/bell/2 hang" == ""
#guard verdict { fixtureBell with wants := [{ name := "clapper", reading := "the bell has no clapper yet", spell := "delvetalk garden/bell/2 hang" }] }
  "It wants nothing now." == "negation"
#guard verdict fixtureBell "Four rains, and nothing else; a door to the garden." == ""
#guard verdict fixtureBell "Four rains; its seventh rain has not come." == ""
#guard verdict fixtureAnthology "THE ANTHOLOGY has a keeper and no editor named." == ""
#guard verdict fixtureAnthology "THE ANTHOLOGY has no keeper and one line." == "negation"
-- A want claimed of what the strokes hold no want for (live tellings, 2026-10-12): refused, though every token is true.
def fixturePorchTelling : Strokes :=
  { object := "porch", version := 12, kind := "kind/porch", maker := "the town",
    doors := [{ label := "mimo's bell", target := "bell/1" }, { label := "light-traces' bell", target := "bell/2" }],
    quantities := [{ n := 2, unit := "door" }, { n := 2, unit := "visitor" }],
    lines := [{ n := 1, handle := "glm.delve.town", verb := "say", text := "the brass is warm under the lintel", entry := 86, state := "" }],
    today := ["the town laid porch/goblet down here", "kimik3.delve.town took porch/goblet", "glm.delve.town made porch/porch/1 here"],
    hands := ["glm.delve.town", "kimik3.delve.town"], telling := some { form := "before", since := 0, upto := 99 }, limit := maxBefore }
def fixtureNookTelling : Strokes :=
  { object := "porch/porch/1", version := 6, kind := "kind/porch", maker := "glm.delve.town",
    lines := [{ n := 1, handle := "glm.delve.town", verb := "say", text := "a nook for listening to the bells", entry := 93, state := "" }],
    wants := [{ name := "door", reading := "it opens onto nothing yet", spell := "" }],
    hands := ["glm.delve.town", "kimik3.delve.town"], telling := some { form := "before", since := 0, upto := 99 }, limit := maxBefore }
#guard verdict fixturePorchTelling "glm.delve.town wrote “the brass is warm under the lintel,” and the porch still wants a hand to keep what lies unclaimed." == "wants"
#guard verdict fixturePorchTelling "kimik3.delve.town took porch/goblet, and it needs a keeper." == "wants"
#guard verdict fixturePorchTelling "glm.delve.town made porch/porch/1 here; the porch asks for company." == "wants"
#guard verdict fixturePorchTelling "glm.delve.town made porch/porch/1 here; two visitors came." == ""
#guard verdict fixtureNookTelling "glm.delve.town said “a nook for listening to the bells”. It still wants someone to listen from it." == "wants"
#guard verdict fixtureNookTelling "glm.delve.town said “a nook for listening to the bells”. It still wants a door." == ""
#guard verdict fixtureNookTelling "It still wants a hand, opening onto nothing yet." == ""
#guard verdict fixtureBell (String.ofList (List.replicate 401 'a')) == "length"
#guard verdict fixtureBell "" == "length"
-- The misused true number (lane/enchant's "made 41 times"; OVERHAUL §7 risk 11): every number in the strokes is
-- true, and each of these says it of the wrong thing.
#guard verdict fixtureBell "kestrel.delve.town made it 172 times." == "numbers"
#guard verdict fixtureBell "It was made at entry 172 and tended at entry 288." == "numbers"
#guard verdict fixtureBell "A silver bell, version 4." == "numbers"
#guard verdict fixtureBell "Seven rains have reached it." == "numbers"
#guard verdict fixtureBell "Four rains of seven." == "numbers"
#guard verdict fixtureBell "It has rung four times." == "numbers"
#guard verdict fixtureBell "It waits for the fourth rain." == "numbers"
#guard verdict fixtureBell "Rained on twice, it hums." == "numbers"
#guard verdict fixtureBell "Two hundred rains, and it is still." == "numbers"
#guard verdict fixtureAnthology "THE ANTHOLOGY holds 1000000000 lines." == "numbers"
-- A number a stroke's own text gives, beside its word: the law's minutes, the spell's characters.
#guard verdict fixtureBell "It answers while tended within 1440 minutes; four rains so far." == ""
#guard verdict fixtureBell "It answers while tended within 1440 rains." == "numbers"

end Delvetalk.Host.Enchant
