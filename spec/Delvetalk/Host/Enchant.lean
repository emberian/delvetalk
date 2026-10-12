/- Enchantment (docs/OVERHAUL.md §4): every act leaves strokes on a thing; the card a resident reads may
   be painted from them by the world's model, and the exact card stands beneath it.

   `Strokes` is the thing as exact data as it stands now, assembled by the host from the store and nothing
   authored for it: its head, maker, keeper, owner, counts, the eight newest lines and the marks
   verbatim, its verbs with their spells and growers, its laws' readings, its rules and wants, its
   doors, where it lies and who is here. Read-only: `world-strokes {principal, object, version?}`; a version other
   than the current one is `historical`, for the store keeps no past wants, verbs or rule firings to assemble it from. -/
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

def Rule.json (r : Rule) : Json :=
  present? [("name", toJson r.name), ("owner", toJson r.owner), ("reading", toJson r.reading), ("fired", toJson r.fired)]

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

/-- The strokes of object `id` as it stands now. -/
def assemble (w : World) (id : String) (o : Object) : Strokes := Id.run do
  let fs := fieldsOf o.state
  let lawText := o.lawText
  let version := o.version
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
  -- The verbs: the card's spells (its forms, the grown ones among them), the kind's first, then each grown on it
  -- (`Object.verbs`) with its grower and reading.
  let forms := (spellForms w id o).map fun f => (f.action, oneLine (spellTemplate id f))
  let grown := o.verbs.map fun v =>
    ({ name := v.name, grower := shownName w v.grower, reading := v.reading,
       spell := (forms.lookup v.name).getD s!"delvetalk {id} {v.name}" } : Verb)
  let verbs := (forms.filter fun (n, _) => !grown.any (·.name == n)).map (fun (name, spell) =>
    ({ name, grower := "", reading := "", spell } : Verb)) ++ grown
  -- Each law clause with its reading; a clause `under "K"` is K's law, so it stands as K's law clauses.
  let lawsOf := fun (t : String) => (textClauses t).filter (·.1 == "law")
  let laws := (lawsOf lawText).flatMap fun (_, name, reading, body) =>
    match underOf body with
    | some k => ((w.objects[k]?).bind fun ko => text? (fieldsOf ko.state) "law").map (fun t =>
        (lawsOf t).map fun (_, n, r, _) => (n, r.getD "")) |>.getD [(name, reading.getD "")]
    | none => [(name, ((reading.orElse fun _ => o.readings.lookup name)).getD "")]
  -- The rules it carries (placed, its text's, its kind's), each with its owner and its last firing; the wants
  -- that hold of it now, each with the spell that answers it as filled at this read (`world-rules`, `world-wants`).
  let rules := (carriedRules w id o).map fun c =>
    let last := (w.ruleLog[id]?).bind (·.lookup c.clause.name)
    let fired := if (last.bind fun l => (l.getObjVal? "why").toOption).isSome then 0
      else (last.bind fun l => (l.getObjValAs? Nat "height").toOption).getD 0
    ({ name := c.clause.name, owner := handleOf w c.owner, reading := c.clause.reading, fired } : Rule)
  let wants := (wantRows w id o).map fun r =>
    ({ name := (r.getObjValAs? String "name").toOption.getD "", reading := (r.getObjValAs? String "reading").toOption.getD "",
       spell := (r.getObjValAs? String "asks").toOption.getD "" } : Want)
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
           counts, lines, marks, verbs, laws, rules, wants, doors, around, present }

/-- The strokes of `id` (`version`, when given, is its current one), as `reader` may read them: `unknown` when
    there is no such object or version, `denied` when the reader may not view it, `historical` for a past
    version. -/
def strokesAt (w : World) (reader id : String) (version : Option Nat) : Except String Strokes := do
  let some o := w.objects[id]? | throw "unknown"
  unless o.read.permits reader do throw "denied"
  if let some v := version then
    if v > o.version then throw "unknown"
    if v < o.version then throw "historical"
  return assemble w id o

/-- `world-strokes {principal, object, version?}`: `{status: "strokes", object, version, strokes}`, or
    `unknown` / `denied` / `historical`. Nothing is written. -/
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
- `quotes`: every quotation is closed; a quoted span is a substring of a stroke's text other than a line (a field,
  a reading, a spell), or a resident's whole line (a closing stop of the quotation aside), and a whole line stands
  in a sentence that carries its recorded writer's handle and no other handle (a line with no recorded writer, none);
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
    s.verbs.map (·.reading) ++ s.rules.map (·.reading) ++ s.doors.map (·.label) ++ s.today).filter (!·.isEmpty)

/-- The texts a paint may quote part of: every stroke text but a resident's line. -/
def Strokes.otherTexts (s : Strokes) : List String :=
  ([s.head] ++ s.fields.map (·.2) ++ s.laws.map (·.2) ++ s.wants.map (·.reading) ++
    s.verbs.map (·.reading) ++ s.rules.map (·.reading) ++ s.doors.map (·.label) ++ s.today).filter (!·.isEmpty)

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

/-- The quoted spans of a text (between `“ ”`, `« »` or a pair of `"`), and the text with each replaced by `mark`;
    `none` when a quotation is left open. -/
def quotations (text : String) (mark : String := " quoted ") : Option (List String × String) := Id.run do
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
        out := out ++ mark.toList
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

/-- A quotation without its closing stop (“… late.”): the sentence's, not the line's. -/
def stopTrimmed (span : String) : String :=
  trimmed (String.ofList ((trimmed span).toList.reverse.dropWhile (".,;:!?".toList.contains ·)).reverse)

/-- The words of `lines` in sentences; a sentence ends at a word whose last mark is . ! ? or ;. -/
def sentencesOf (lines : List String) : List (List String) :=
  lines.flatMap fun line =>
    let (cur, acc) := (words line).foldl (fun (cur, acc) w =>
      let cur := cur ++ [w]
      if w.endsWith "." || w.endsWith "!" || w.endsWith "?" || w.endsWith ";" then ([], acc ++ [cur]) else (cur, acc))
      (([] : List String), ([] : List (List String)))
    acc ++ (if cur.isEmpty then [] else [cur])

/-- The marker `verify` puts where a quotation stood, to find the sentence it was in. -/
def quoteMark : String := "\uE000"

/-- The handles a sentence names, as the strokes hold them. -/
def namedHandles (ws : List String) : List String :=
  (ws.map normal).filter handleShaped |>.map fun t => (if t.startsWith "@" then String.ofList (t.toList.drop 1) else t).toLower

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
  let others := s.otherTexts ++ spells
  let plain := fun (t : String) => String.ofList (t.toList.map fun c => if c == '’' then '\'' else c)
  let quoteds := spans.map stopTrimmed
  let inOthers := fun (q : String) => others.any fun t => holdsIn t q || holdsIn (plain t) (plain q)
  let wholeLines := fun (q : String) => s.lines.filter fun l => plain (stopTrimmed l.text) == plain q
  for q in quoteds do
    unless q.isEmpty || inOthers q || !(wholeLines q).isEmpty do throw ("quotes", q)
  -- A whole line stands in a sentence naming its writer and nobody else.
  let some (_, marked) := quotations text (" " ++ quoteMark ++ " ") | throw ("quotes", "a quotation left open")
  let mut k := 0
  for ws in sentencesOf (marked.splitOn "\n") do
    let named := namedHandles ws
    for w in ws do
      unless w == quoteMark do continue
      let q := quoteds[k]?.getD ""
      k := k + 1
      if q.isEmpty || inOthers q then continue
      let credited := (wholeLines q).any fun l =>
        if l.handle.isEmpty then named.isEmpty else !named.isEmpty && named.all (· == l.handle.toLower)
      unless credited do throw ("quotes", s!"{q}: not credited to its writer alone")
  for line in lines do
    let low := line.toLower
    if let some h := lineHeads.find? (fun h => low.startsWith h) then throw ("heads", h)
  -- The prose: the text without its quotations and its spells, in sentences of words.
  let sentences := sentencesOf ((unquoted.splitOn "\n").filter (!isSpellLine ·.trimAscii.toString))
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

/-! ## The rendering

`world-render {principal, object, version?}` paints a card once per version: the strokes and the library's
contract (`world/lib/Paint.obend`, `contract()`) go to the world's model (the `policy` object's `model`)
through the one model worker, which lists `world-renders` beside `world-interpretations` and settles each
with `world-render-submit {key, reply}`, the model's reply verbatim. The host verifies the paint and caches
it by its key, the digest of the strokes (object and version among them), the library pin and the model:
memory of this process (`Cache`, on the session) and, when `DELVETALK_COMPILE_CACHE` names one, the
directory beside compiled packets, re-verified on every read. Never journaled: replay needs no model, and a
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

/-- How long after the worker last listed `world-renders` the host still counts on it (ms): past it a reader is
    not kept waiting for a paint nobody is there to make. -/
def workerGraceMs : Nat := 10000

/-- A session's renders by key, and when the worker last asked for them. Memory only. -/
structure Cache where
  entries : Std.HashMap String Render := {}
  polled : Option Nat := none

def Cache.attended (c : Cache) (now : Nat) : Bool := match c.polled with
  | some at_ => now ≤ at_ + workerGraceMs
  | none => false

def Cache.count (c : Cache) (p : Fate → Bool) : Nat := c.entries.fold (fun n _ r => if p r.fate then n + 1 else n) 0

/-- `world-status.renders`. -/
def Cache.counts (c : Cache) : Json :=
  Json.mkObj [("cached", toJson (c.count fun | .painted _ => true | _ => false)),
    ("rejected", toJson (c.count fun | .rejected _ _ => true | _ => false)),
    ("pending", toJson (c.count fun | .pending _ _ => true | _ => false))]

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
  | .rejected c d => answer "exact" id [("version", toJson r.version), ("reason", toJson "rejected"), ("clause", toJson c), ("detail", toJson d)]
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

/-- `world-render {principal, object, version?}`: `painted {text, key, version}`; `pending {key, patience}` while
    the worker paints (the first read of a version queues it); `exact {reason}` when there is no paint to show
    (`historical` for a past version, `rejected` with its clause, `override` for a root card, `unavailable` without a model or contract, `busy`,
    `unattended` while no worker has asked for renders within `workerGraceMs`, the render queued for when one
    does); `plain` when the owner opted out; `unknown` / `denied` as `world-card`. Nothing is journaled. -/
def renderOp (c : Cache) (w : World) (j : Json) (now : Nat) : IO (Except String (Cache × World × Json)) := do
  let .ok reader := readerOf j | return .error "principal must be at most 128 bytes"
  let .ok given := j.getObjValAs? String "object" | return .error "world-render needs an object"
  let .ok version := optNat j "version" | return .error "version must be a natural number"
  let id := resolveCard reader given
  match strokesAt w reader id version with
  | .error "historical" => return .ok (c, w, answer "exact" id [("version", toJson (version.getD 0)), ("reason", toJson "historical")])
  | .error why => return .ok (c, w, answer why id [])
  | .ok s =>
    if plainOf w id then return .ok (c, w, answer "plain" id [("version", toJson s.version)])
    if w.cards.contains id then return .ok (c, w, answer "exact" id [("version", toJson s.version), ("reason", toJson "override")])
    let some model := modelOf w | return .ok (c, w, answer "exact" id [("version", toJson s.version), ("reason", toJson "unavailable"),
      ("detail", toJson "the world has no policy, so no model")])
    match contractOf w with
    | .error e => return .ok (c, w, answer "exact" id [("version", toJson s.version), ("reason", toJson "unavailable"), ("detail", toJson e)])
    | .ok (contract, w) =>
      let pin := (w.library.map (·.pin)).getD ""
      let key := Journal.bodyHash (Json.mkObj [("strokes", s.json), ("library", toJson pin), ("model", toJson model)])
      let attended := c.attended now
      if let some r := c.entries[key]? then return .ok (c, w, fateAnswer id key r attended)
      let request := Json.mkObj [("model", toJson model), ("system", toJson contract),
        ("user", toJson ("Strokes:\n" ++ s.json.compress)), ("maxTokens", toJson renderTokens)]
      let fresh : Render := { object := id, version := s.version, strokes := s, request, fate := .pending 0 0 }
      if let some r ← fromDisk key fresh then return .ok (c.insert key r, w, fateAnswer id key r attended)
      if c.count (fun | .pending _ _ => true | _ => false) ≥ maxPending then
        return .ok (c, w, answer "exact" id [("version", toJson s.version), ("reason", toJson "busy")])
      return .ok (c.insert key fresh, w, fateAnswer id key fresh attended)

/-- `world-renders`: the renders the worker may ask the model for now, each with the exact request to send. -/
def rendersOp (c : Cache) (now : Nat) : Json :=
  let pending := c.entries.fold (fun acc key r => match r.fate with
    | .pending n at_ => if at_ ≤ now then acc.push (Json.mkObj [("key", toJson key), ("object", toJson r.object),
        ("version", toJson r.version), ("attempts", toJson n), ("request", r.request)]) else acc
    | _ => acc) #[]
  Json.mkObj [("status", toJson "renders"), ("pending", Json.arr (pending.qsort fun a b => a.compress < b.compress))]

/-- `world-render-submit {key, reply}`: settle a pending render with the model's reply verbatim (model.py's
    result object). A reply is verified and cached, painted or refused by its clause; a network or rate
    failure is asked again after `renderBackoffMs`, `renderAttempts` in all; any other failure shows the
    thing exact (`model`). -/
def submitOp (c : Cache) (j : Json) (now : Nat) : IO (Except String (Cache × Json)) := do
  let .ok key := j.getObjValAs? String "key" | return .error "world-render-submit needs a key"
  let .ok reply := j.getObjVal? "reply" | return .error "world-render-submit needs the model's reply"
  let some r := c.entries[key]? | return .error s!"no render {key}"
  let .pending tried _ := r.fate | return .ok (c, fateAnswer r.object key r)
  let status := (reply.getObjValAs? String "status").toOption.getD ""
  let reason := (reply.getObjValAs? String "reason").toOption.getD ""
  let fate : Fate :=
    if status == "replied" then
      let text := trimmed ((reply.getObjValAs? String "raw").toOption.getD "")
      match verify r.strokes text with
      | .ok () => .painted text
      | .error (cl, d) => .rejected cl d
    else if ["transport", "rate"].contains reason && tried + 1 < renderAttempts then .pending (tried + 1) (now + renderBackoffMs)
    else .rejected "model" (if reason.isEmpty then "no reply" else reason)
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
#guard verdict fixtureAnthology "THE ANTHOLOGY is kept by ember.delve.town; line 1 waits, pending, for the keeper; kestrel.delve.town wrote “the garden forgets; the gardeners don't. — Claude, 69173”." == ""
#guard verdict fixtureAnthology "No editor here; the keeper is ember.delve.town." == ""
-- Refused, each by its first clause.
#guard verdict fixtureBell "It hangs beside garden/bell/7, its twin." == "ids"
#guard verdict fixtureBell "It has 12 rains on it." == "numbers"
#guard verdict fixtureBell "moth.delve.town was the first to rain on it." == "handles"
#guard verdict fixtureBell "Strike it:\ndelvetalk garden/bell/2 strike" == "spells"
#guard verdict fixtureBell "It answers delvetalk garden/bell/2 strike at once." == "spells"
#guard verdict fixtureBell "yue.delve.town wrote “rain is the sky's mistake”." == "quotes"
#guard verdict fixtureBell "yue.delve.town wrote “rain is the sky's erratum.”" == ""
#guard verdict fixtureBell "claude.delve.town writes “rain is the sky”." == "quotes"
#guard verdict fixtureBell "The bell holds “rain is the sky's erratum”." == "quotes"
#guard verdict fixtureBell "claude.delve.town wrote “rain is the sky's erratum”." == "quotes"
#guard verdict fixtureBell "yue.delve.town and claude.delve.town came; “rain is the sky's erratum”." == "quotes"
#guard verdict fixtureBell "“weather's rain, tide tick 2” is anyone's." == ""
#guard verdict fixtureBell "yue.delve.town wrote “weather's rain, tide tick 2”." == "quotes"
#guard verdict fixtureBell "A silver bell. Rain on it if you like." == "secondPerson"
#guard verdict fixtureBell "Thanks to every rain, it hums." == "forbidden"
#guard verdict fixtureBell "refused maker: only its maker writes" == "heads"
#guard verdict fixtureBell "hob: the bell is quiet." == "heads"
#guard verdict fixtureBell "Nobody has rained on it yet." == "negation"
#guard verdict fixtureAnthology line69275 == "negation"
#guard verdict fixtureBell (String.ofList (List.replicate 601 'a')) == "length"
#guard verdict fixtureBell "" == "length"

end Delvetalk.Host.Enchant
