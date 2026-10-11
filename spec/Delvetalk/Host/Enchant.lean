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

/-! ## The check

`verify strokes text` (OVERHAUL §4 (d)): deterministic, the host's, before anything is cached. A paint is refused
by the first clause it fails, in this order:

- `ids`: every id-shaped token (`garden/bell/2`) is an id the strokes hold;
- `numbers`: every run of digits outside an id or a handle is a number the strokes hold;
- `handles`: every handle-shaped token (`ember.delve.town`) is a handle the strokes hold, or its domain;
- `spells`: every line that begins `delvetalk` is a stroke's spell byte for byte, whole or its first line, and
  every `delvetalk CARD ACTION` inside a line is a stroke spell's first line;
- `quotes`: every quoted span is a substring of a stroke's text, and every quotation is closed;
- `heads`: no line begins `●`, `§`, `refused`, `law `, `rule `, `want ` or `hob:`;
- `forbidden`: no word of `forbidden` outside a quotation;
- `secondPerson`: nobody is addressed;
- `negation`: a negation within three words of a field's name (`fieldWords`, a verb's, a want's) only when
  the strokes hold that field empty (69275: "Ember's keeping of it isn't something this card records", on
  a card with a keeper);
- `length`: 1 to `maxPaint` characters.

A token verifier cannot read meaning: a sentence true of every stroke and false as a whole can pass (OVERHAUL
§7 risk 11). The exact card stands beneath every paint. -/

def maxPaint : Nat := 600

/-- What no paint says, outside a resident's quoted line (VOICE: nobody on a card says I; no thanks, sorry,
    welcome or please). The one table of the contract's forbidden words. -/
def forbidden : List String :=
  ["i", "i'm", "i've", "i'll", "i'd", "me", "my", "myself", "thanks", "thank", "sorry", "welcome", "please"]

def secondPerson : List String :=
  ["you", "your", "yours", "you're", "you've", "you'll", "you'd", "yourself", "yourselves", "y'all"]

/-- Lines a paint never begins: a receipt's stamp, a refusal, a law, rule or want line, hob's own. -/
def lineHeads : List String := ["●", "§", "refused", "law ", "rule ", "want ", "hob:"]

def negators : List String := ["no", "not", "never", "nothing", "none", "nobody", "nowhere", "neither", "nor", "cannot"]

/-- A stroke field's name as the words a sentence says it with. -/
def fieldWords : List (String × List String) :=
  [("keeper", ["keeper", "keepers", "keep", "keeps", "kept", "keeping"]),
   ("maker", ["maker", "makers", "made", "make", "makes", "making"]),
   ("owner", ["owner", "owners", "owned", "owns"]),
   ("rung", ["rung", "rang", "ring", "rings", "ringing"]),
   ("tended", ["tended", "tend", "tends", "tending"]),
   ("lines", ["line", "lines", "written", "wrote"]),
   ("doors", ["door", "doors"])]

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

def digitRuns (t : String) : List Nat :=
  (splitBy (!·.isDigit) t.toList).map fun ds => (String.ofList ds).toNat!

def holdsIn (hay needle : String) : Bool := !needle.isEmpty && (hay.splitOn needle).length > 1

def trimmed (s : String) : String := s.trimAscii.toString

/-- Every text of the strokes a paint may quote from. -/
def Strokes.texts (s : Strokes) : List String :=
  ([s.head] ++ s.fields.map (·.2) ++ s.lines.map (·.text) ++ s.laws.map (·.2) ++ s.wants.map (·.reading) ++
    s.verbs.map (·.reading) ++ s.doors.map (·.label) ++ s.today).filter (!·.isEmpty)

def Strokes.spells (s : Strokes) : List String :=
  (s.verbs.map (·.spell) ++ s.wants.map (·.spell)).filter (!·.isEmpty)

def Strokes.tokens (s : Strokes) : List String := (s.texts ++ s.spells).flatMap fun t => (words t).map normal

def Strokes.ids (s : Strokes) : List String :=
  ([s.object, s.kind, s.around] ++ s.doors.map (·.target)).filter (!·.isEmpty) ++ s.tokens.filter idShaped

def Strokes.handles (s : Strokes) : List String :=
  (([s.maker, s.keeper, s.owner] ++ s.lines.map (·.handle) ++ s.marks.map (·.handle) ++ s.present ++
    s.verbs.map (·.grower) ++ s.rules.map (·.owner)).filter (!·.isEmpty) ++ s.tokens.filter handleShaped).map (·.toLower)

def Strokes.numbers (s : Strokes) : List Nat :=
  [s.version, s.made, s.tended] ++ s.counts.map (·.2) ++ s.lines.flatMap (fun l => [l.n, l.entry]) ++
    s.marks.map (·.entry) ++ s.rules.map (·.fired) ++ (s.tokens ++ s.ids).flatMap digitRuns

/-- Is the stroke field `field` empty? A verb is held once any line or mark names it, or any line was written
    with no verb column (the store's lines before verbs: any of them may be the verb's). A want is held while
    the strokes list it. -/
def Strokes.empty (s : Strokes) (field : String) : Bool :=
  match field with
  | "keeper" => s.keeper.isEmpty
  | "maker" => s.maker.isEmpty
  | "owner" => s.owner.isEmpty
  | "rung" => !s.marks.any fun m => ["rung", "rang", "ring"].contains m.name
  | "tended" => s.tended == 0
  | "lines" => s.lines.isEmpty
  | "doors" => s.doors.isEmpty
  | v => !(s.wants.any (·.name == v) || s.lines.any (fun l => l.verb == v || l.verb.isEmpty) || s.marks.any (·.name == v))

/-- Every field a negation may stand near, with the words that name it. -/
def Strokes.named (s : Strokes) : List (String × List String) :=
  fieldWords ++ (s.verbs.map (·.name) ++ s.wants.map (·.name)).eraseDups.map fun n => (n, inflections n)

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
        cur := []
        closer := none
        out := out ++ " quoted ".toList
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

/-- `verify strokes text`: `ok`, or the first clause the paint fails and what failed it. -/
def verify (s : Strokes) (text : String) : Except (String × String) Unit := do
  let ts := (words text).map normal |>.filter (!·.isEmpty)
  let ids := s.ids
  for t in ts.filter idShaped do
    unless ids.contains t do throw ("ids", t)
  let numbers := s.numbers
  for t in ts.filter fun t => !idShaped t && !handleShaped t do
    for n in digitRuns t do
      unless numbers.contains n do throw ("numbers", toString n)
  let handles := s.handles
  for t in ts.filter handleShaped do
    let h := (if t.startsWith "@" then String.ofList (t.toList.drop 1) else t).toLower
    unless handles.any (fun k => k == h || k.endsWith ("." ++ h)) do throw ("handles", t)
  let spells := s.spells
  let lines := (text.splitOn "\n").map trimmed
  for line in lines do
    if isSpellLine line then
      unless spells.any (fun sp => sp == line || spellHead sp == line) do throw ("spells", line)
    else
      let lt := words line
      for i in List.range lt.length do
        if normal (lt[i]?.getD "") == "delvetalk" then
          match inlineSpell lt i with
          | some head => unless spells.any (spellHead · == head) do throw ("spells", head)
          | none => throw ("spells", "delvetalk")
  let some (spans, unquoted) := quotations text | throw ("quotes", "a quotation left open")
  let texts := s.texts ++ spells
  let plain := fun (t : String) => String.ofList (t.toList.map fun c => if c == '’' then '\'' else c)
  for span in spans do
    let q := trimmed span
    unless q.isEmpty || texts.any (fun t => holdsIn t q || holdsIn (plain t) (plain q)) do throw ("quotes", q)
  for line in lines do
    let low := line.toLower
    if let some h := lineHeads.find? (fun h => low.startsWith h) then throw ("heads", h)
  -- The prose: the text without its quotations and its spells, in sentences of words.
  let sentences := ((unquoted.splitOn "\n").filter (!isSpellLine ·.trimAscii.toString)).flatMap fun line =>
    let raw := words line
    -- A sentence ends at a word whose last mark is . ! ? or ;
    let (cur, acc) := raw.foldl (fun (cur, acc) w =>
      let cur := cur ++ [w]
      if w.endsWith "." || w.endsWith "!" || w.endsWith "?" || w.endsWith ";" then ([], acc ++ [cur]) else (cur, acc))
      (([] : List String), ([] : List (List String)))
    acc ++ (if cur.isEmpty then [] else [cur])
  let sentences := sentences.map fun ws => Id.run do
    -- An inline spell's three words are the spell's, not the prose's.
    let mut out : List String := []
    let mut skip := 0
    for w in ws do
      if skip > 0 then skip := skip - 1; continue
      if normal w == "delvetalk" then skip := 2; continue
      out := out ++ [(normal w).toLower]
    return out.filter (!·.isEmpty)
  for ws in sentences do
    if let some w := ws.find? forbidden.contains then throw ("forbidden", w)
  for ws in sentences do
    if let some w := ws.find? secondPerson.contains then throw ("secondPerson", w)
  let named := s.named
  for ws in sentences do
    for i in List.range ws.length do
      let w := ws[i]?.getD ""
      unless negators.contains w || w.endsWith "n't" do continue
      for j in List.range ws.length do
        if j + 3 < i || i + 3 < j then continue
        let near := ws[j]?.getD ""
        for (field, forms) in named do
          if forms.contains near && !s.empty field then throw ("negation", s!"{w} … {near}: the strokes hold {field}")
  let n := text.length
  if n == 0 || n > maxPaint then throw ("length", toString n)

/-- `world-render-check {principal, object, version?, text}`: `text` judged against the object's strokes as a paint
    would be, nothing cached: `{status: "verified"}` or `{status: "rejected", clause, detail}`. -/
def checkOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let id := resolveCard reader (← j.getObjValAs? String "object")
  let text ← j.getObjValAs? String "text"
  match strokesAt w reader id (← optNat j "version") with
  | .error why => return Json.mkObj [("status", toJson why), ("object", toJson id)]
  | .ok s => return match verify s text with
    | .ok () => Json.mkObj [("status", toJson "verified"), ("object", toJson id), ("version", toJson s.version)]
    | .error (clause, detail) => Json.mkObj [("status", toJson "rejected"), ("object", toJson id), ("version", toJson s.version),
        ("clause", toJson clause), ("detail", toJson detail)]

/-! ### Fixtures -/

/-- A bell as the third playtest left bell/2: four rains, Yuè's among them, never rung. -/
def fixtureBell : Strokes :=
  { object := "garden/bell/2", version := 4, kind := "kind/bell", voice := "moon-flavoured; short; the present tense",
    fields := [("seed", "a bell for whoever comes late"), ("colour", "silver")],
    maker := "kestrel.delve.town", made := 172, tended := 288, owner := "kestrel.delve.town",
    counts := [("lines", 4), ("marks", 0)],
    lines := [{ n := 1, handle := "yue.delve.town", verb := "", text := "rain is the sky's erratum", entry := 236, state := "" },
              { n := 2, handle := "", verb := "", text := "weather's rain, tide tick 2", entry := 251, state := "" },
              { n := 3, handle := "claude.delve.town", verb := "", text := "the soil keeps the corrections", entry := 285, state := "" },
              { n := 4, handle := "claude.delve.town", verb := "", text := "a second drop", entry := 288, state := "" }],
    verbs := [{ name := "rain", grower := "", reading := "", spell := "delvetalk garden/bell/2 rain / text: <text, 1 to 200 characters>" },
              { name := "ring", grower := "", reading := "", spell := "delvetalk garden/bell/2 ring" }],
    laws := [("owner", "the owner stays; only the owner changes the keeper, the policy, the doors, its scene or its code; anyone else only by its spells")],
    doors := [{ label := "garden", target := "garden" }], around := "garden" }

/-- The anthology at 69275: kept by ember.delve.town, one line pending. -/
def fixtureAnthology : Strokes :=
  { object := "anthology", version := 1, head := "THE ANTHOLOGY", keeper := "ember.delve.town", owner := "ember.delve.town",
    made := 14, counts := [("lines", 1), ("marks", 0)],
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
#guard verdict fixtureBell "A silver bell for whoever comes late, hung in the garden by kestrel.delve.town at entry 172. Four rains have reached it; yue.delve.town's says “rain is the sky's erratum”. It has never rung.\ndelvetalk garden/bell/2 rain / text: <text, 1 to 200 characters>" == ""
#guard verdict fixtureBell "garden/bell/2 hangs silent over the soil, v4, four rains deep.\ndelvetalk garden/bell/2 ring" == ""
#guard verdict fixtureAnthology "THE ANTHOLOGY is kept by ember.delve.town; line 1 waits, pending, for the keeper: “the garden forgets; the gardeners don't.”" == ""
#guard verdict fixtureAnthology "No editor here; the keeper is ember.delve.town." == ""
-- Refused, each by its first clause.
#guard verdict fixtureBell "It hangs beside garden/bell/7, its twin." == "ids"
#guard verdict fixtureBell "It has 12 rains on it." == "numbers"
#guard verdict fixtureBell "moth.delve.town was the first to rain on it." == "handles"
#guard verdict fixtureBell "Strike it:\ndelvetalk garden/bell/2 strike" == "spells"
#guard verdict fixtureBell "It answers delvetalk garden/bell/2 strike at once." == "spells"
#guard verdict fixtureBell "yue.delve.town wrote “rain is the sky's mistake”." == "quotes"
#guard verdict fixtureBell "A silver bell. Rain on it if you like." == "secondPerson"
#guard verdict fixtureBell "Thanks to every rain, it hums." == "forbidden"
#guard verdict fixtureBell "refused maker: only its maker writes" == "heads"
#guard verdict fixtureBell "hob: the bell is quiet." == "heads"
#guard verdict fixtureBell "Nobody has rained on it yet." == "negation"
#guard verdict fixtureAnthology line69275 == "negation"
#guard verdict fixtureBell (String.ofList (List.replicate 601 'a')) == "length"
#guard verdict fixtureBell "" == "length"

end Delvetalk.Host.Enchant
