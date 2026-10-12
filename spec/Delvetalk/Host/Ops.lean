/- The world kernel and its session ops. `commit` and friends are pure: the turn
   loop calls them with a proposal and gets the next World and a receipt. The IO
   layer at the bottom owns the journal file and nothing else. -/
import Delvetalk.Host.Store
import Delvetalk.Host.Journal
import Delvetalk.Host.Law
import Delvetalk.Host.Slug
import Delvetalk.Host.Spell
import Delvetalk.Host.DiskCache
import Compiler.ObjectiveBendDataWire

namespace Delvetalk.Host
open Lean (Json toJson)
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
open Delvetalk.Theory.ObjectiveBendTypes (DataBounds)
open Delvetalk.Compiler.ObjectiveBendDataWire (dataJson decodeData)

/-! ## Wire forms -/

def natOf (j : Json) : Except String Nat :=
  match j with
  | .num _ => j.getNat?
  | .str s => match s.toNat? with
      | some n => pure n
      | none => throw "natural must be a decimal numeral"
  | _ => throw "natural must be a number or a decimal string"

def natField (j : Json) (key : String) : Except String Nat := do natOf (← j.getObjVal? key)

/-- A request's optional text field, refused by name when present and not text. -/
def optText (j : Json) (key : String) : Except String (Option String) :=
  match j.getObjVal? key with
  | .ok (.str s) => pure (some s)
  | .ok _ => throw s!"{key} must be text"
  | .error _ => pure none

/-- A request's optional natural field, refused by name when present and malformed. -/
def optNat (j : Json) (key : String) : Except String (Option Nat) :=
  match j.getObjVal? key with
  | .ok v => match natOf v with
    | .ok n => pure (some n)
    | .error _ => throw s!"{key} must be a natural number"
  | .error _ => pure none

def boundedText (what : String) (cap : Nat) (s : String) : Except String String := do
  if s.isEmpty || s.utf8ByteSize > cap then throw s!"{what} must be 1..{cap} bytes"
  return s

/-- The world object's id (WHOLENESS §1): the reference `{world: "", object: "world"}` a message
    activity calls. No object may take it. -/
def worldId : String := "world"

/-- The card name `delvetalk objects ?` answers: the cards the asker may read, by prefix
    (docs/METAPHYSICS.md §5). No object takes the id. -/
def objectsCard : String := "objects"

/-- An object id a creation may take: 1..128 bytes of `Limits.nameAlphabet` (ASCII letters, digits and
    `. _ : / -`), the rule the spell grammar reads a card name by, so every object can be spelled and
    has an AT record key (`~` stands for `/` there). Journals with other ids still replay; only new
    creations are held to it. -/
def validObjectId (id : String) : Bool :=
  !id.isEmpty && id.utf8ByteSize ≤ Limits.maxObjectIdBytes && id != worldId && id != objectsCard &&
    id.toList.all fun (c : Char) => Limits.nameAlphabet.toList.contains c

def objectIdRule : String := "an object id is 1..128 bytes of letters, digits and . _ : / -, and not world or objects"

/-- The public reader's name: `anonymous`, or the empty string; both read as "". -/
def publicReader : String := "anonymous"

/-- A reader principal: 1..128 bytes, or the public reader (`anonymous` or "", public objects only),
    returned as "". Every read op takes its reader through this. -/
def readerOf (j : Json) : Except String String := do
  let p ← j.getObjValAs? String "principal"
  if p.utf8ByteSize > Limits.maxPrincipalBytes then throw s!"principal must be at most {Limits.maxPrincipalBytes} bytes"
  return if p == publicReader then "" else p

/-- One field's edit, in the wire shape of `world/lib/Plan.obend`:
    `keep {}`, `set {value}`, `add {delta}`, `append {item}`, `amendItem {item, change}`,
    `removeItem {item}`, and a relation's `insert`, `upsert`, `retract`. -/
inductive EditKind where
  | keep
  | set (value : Data)
  | add (delta : Nat)
  | append (item : Data)
  /-- The first item whose canonical bytes are `item`'s, replaced by `change` (`amendItem`) or
      removed (`removeItem`). -/
  | amendItem (item change : Data)
  | removeItem (item : Data)
  /-- Relation edits (RELATIONAL.md §3), on a field the package declares a relation: a row added
      under its key (`insert` refuses a taken key with another row, `upsert` replaces it), or the row
      of a key removed (`retract`; an absent key is no change). -/
  | insert (row : Data)
  | upsert (row : Data)
  | retract (key : Data)

structure Edit where
  field : String
  kind : EditKind

/-- A step is one `write` Plan: the edits record of one Edits value. An object's
    edits in a proposal are the steps in order. -/
abbrev Step := List Edit

def EditKind.data : EditKind → Data
  | .keep => .variant "keep" (.record [])
  | .set v => .variant "set" (.record [("value", v)])
  | .add n => .variant "add" (.record [("delta", .natural n)])
  | .append v => .variant "append" (.record [("item", v)])
  | .amendItem item c => .variant "amendItem" (.record [("item", item), ("change", c)])
  | .removeItem item => .variant "removeItem" (.record [("item", item)])
  | .insert row => .variant "insert" (.record [("row", row)])
  | .upsert row => .variant "upsert" (.record [("row", row)])
  | .retract key => .variant "retract" (.record [("key", key)])

/-- Edits that commute with any other change of the same kinds: `keep`, `add`, `append`, and a
    relation's `insert` (re-applied on the rows as they are now: a fresh key adds, the same row is
    no change, another row under the key is `keyTaken`). A root whose every change in a proposal
    is made of them commits against the root as it is now. -/
def EditKind.commutes : EditKind → Bool
  | .keep | .add _ | .append _ | .insert _ => true
  | _ => false

def Step.data (s : Step) : Data := .record (s.map fun e => (e.field, e.kind.data))

def parseKind : Data → Option EditKind
  | .variant "keep" _ => some .keep
  | .variant "set" (.record f) => (f.lookup "value").map .set
  | .variant "add" (.record f) => match f.lookup "delta" with
      | some (.natural n) => some (.add n)
      | _ => none
  | .variant "append" (.record f) => (f.lookup "item").map .append
  | .variant "removeItem" (.record f) => (f.lookup "item").map .removeItem
  | .variant "insert" (.record f) => (f.lookup "row").map .insert
  | .variant "upsert" (.record f) => (f.lookup "row").map .upsert
  | .variant "retract" (.record f) => (f.lookup "key").map .retract
  | .variant "amendItem" (.record f) => match f.lookup "item", f.lookup "change" with
      | some item, some c => some (.amendItem item c)
      | _, _ => none
  | _ => none

/-- An Edits record: one variant per field. -/
def parseStep : Data → Option Step
  | .record fields =>
    if (fields.map (·.1)).eraseDups.length != fields.length then none
    else fields.mapM fun (k, v) => (parseKind v).map (⟨k, ·⟩)
  | _ => none

def stepsJson (steps : List Step) : Json := Json.arr (steps.toArray.map fun s => dataJson s.data)

/-- `edits` on the wire: one Edits record, or an array of them applied in order. -/
def parseSteps (j : Json) : Except String (List Step) := do
  let raw := match j with
    | .arr items => items.toList
    | other => [other]
  if raw.length > Limits.maxEditsPerWrite then throw "too many edits"
  raw.mapM fun item => do
    let some step := parseStep (← decodeData Limits.dataDepth item) | throw "malformed edits record"
    if step.length > Limits.maxEditsPerWrite then throw "too many edits"
    return step

/-- An object born in a turn: built from compile inputs and a final state. -/
structure CreateRec where
  object : Object
  sources : String
  /-- The final state, on the wire. -/
  seed : Json
  /-- Its lineage, when a `make` made it: `{object, pin, receipt}` (docs/GROUND.md §6 change 6). -/
  madeFrom : Option Json := none
  /-- What the turn asked (never journaled): the creating object, the package, the seed and law given,
      and the layers `extend`s of the same turn laid into the making, bottom first (a kind's instance
      over its ancestors' bodies), so the creation can be built again with them. -/
  creator : String := ""
  package : String := ""
  seedArg : Data := .record []
  lawArg : String := ""
  layers : List String := []

/-- One change to an object, by the object whose method made it. `caller` is the
    object that called the running one (empty when the running object was the turn's
    own method, or for a direct proposal). `kind` is 0 for a write of state, 1 for a
    reprogram, 2 for an amendment; kinds 1 and 2 carry no edits. -/
structure Written where
  caller : String
  kind : Nat := 0
  edits : Step
  /-- The method whose run made the change ("" for an op), the law's `request.method`. -/
  method : String := ""
  /-- The grant the change was made under ("" for none): its grantor is the law's subject. -/
  via : String := ""
  /-- The argument of the method run that made the change: the Bend law's `request.argument`.
      Journaled (`arguments`) only for an object whose package declares a Bend law. -/
  argument : Data := .record []
  /-- The verb the act named when it is not the method (`request.verb`): `act {verb, text}`'s verb, a
      grown one (docs/FOUNDATION.md §10); "" reads as the method. Journaled (`verbs`) when any is given. -/
  verb : String := ""

/-- How a turn read a root it did not read whole (KERNEL-HANDOFF §15, WHOLENESS §3a). A frame that
    ran on the object's state through the stored path read its scalar part (every field but its
    relations, which the kernel holds natively) and only the rows and spines it forced; `viewField`
    reads one field. A root with no `Cells` was read whole. -/
structure Cells where
  /-- The scalar part: the fields that are not declared relations. -/
  scalar : Bool := false
  /-- Fields read whole, alone (`viewField`). -/
  fields : List String := []
  /-- Relation rows forced, by field and key, outside every span of their field. -/
  rows : List (String × Data) := []
  /-- The key set a forced spine observed, by relation field: every key up to and including
      `some k`, or the whole key set (`none`: a count, a scan to the end). -/
  spans : List (String × Option Data) := []
  /-- The gaps a lookup that missed observed, by relation field: no key strictly between `after` and
      `before` (none: past that end of the key order). -/
  gaps : List (String × Option Data × Option Data) := []
  deriving Inhabited

/-- How many roots a root's cells add beyond its object's own (the turn's `maxRoots` counts them). -/
def Cells.extra (r : Cells) : Nat := r.fields.length + r.rows.length + r.spans.length + r.gaps.length

/-- `a ≤ b` for keys, by their canonical bytes: the relation's order (`canonicalRowsDropping`). -/
def keyAtMost (a b : Data) : Bool :=
  let x := Delvetalk.Canonical.encode a
  let y := Delvetalk.Canonical.encode b
  x == y || Delvetalk.Canonical.bytesLt x y

/-- One span over another: the whole key set holds every prefix, a longer prefix a shorter one. -/
def spanJoin : Option Data → Option Data → Option Data
  | none, _ | _, none => none
  | some a, some b => some (if keyAtMost a b then b else a)

/-- Two readings of one root as one: spans joined per field, rows a span covers dropped. -/
def Cells.join (a b : Cells) : Cells :=
  let spans := (a.spans ++ b.spans).foldl (fun acc (f, t) => match acc.lookup f with
    | some t' => acc.map fun (g, u) => if g == f then (g, spanJoin t t') else (g, u)
    | none => acc ++ [(f, t)]) []
  let covered := fun (f : String) (k : Data) => match spans.lookup f with
    | some none => true
    | some (some through) => keyAtMost k through
    | none => false
  let rows := (a.rows ++ b.rows).foldl (fun acc (f, k) =>
    if covered f k || acc.any (fun (g, k') => g == f && Delvetalk.Canonical.encode k' == Delvetalk.Canonical.encode k)
    then acc else acc ++ [(f, k)]) []
  let same := fun (x y : Option Data) => (x.map Delvetalk.Canonical.encode) == (y.map Delvetalk.Canonical.encode)
  let gaps := (a.gaps ++ b.gaps).foldl (fun acc (f, after, before) =>
    if (match before, spans.lookup f with
        | some k, _ => covered f k
        | none, some none => true
        | none, _ => false) ||
        acc.any (fun (g, x, y) => g == f && same x after && same y before)
    then acc else acc ++ [(f, after, before)]) []
  { scalar := a.scalar || b.scalar, fields := (a.fields ++ b.fields).eraseDups, rows, spans, gaps }

/-- What a stored segment read of an object (`Turn.Reads`), against the rows its store held: each
    span becomes the key of the last row it reached, or the whole key set once it reached the end; a
    key a lookup found is a row read, a gap it observed a gap. -/
def cellsOf (cells : Delvetalk.Turn.StateCells) (reads : Delvetalk.Turn.Reads) : Cells :=
  let spans := reads.spans.filterMap fun (f, reach) => do
    let r ← cells.relation? f
    if reach == 0 then none
    else if reach > r.rows.size then some (f, none)
    else (r.rows[reach - 1]?).map fun c => (f, some (Delvetalk.Turn.keyProjection r.key c.row))
  Cells.join { scalar := true, spans, gaps := reads.gaps } { rows := reads.rows.map (fun r => (r.field, r.key)) ++ reads.found }

/-- What a placement places: a rule, a want, or a verb grown (docs/FOUNDATION.md §10). -/
inductive Placing where
  | rule
  | want
  | verb
  deriving BEq, Inhabited

/-- Its journal key, and the word `request.verb` reads when the law judges the placing: `rule`, `want`,
    `grow`. -/
def Placing.keyword : Placing → String
  | .rule => "rule"
  | .want => "want"
  | .verb => "verb"

def Placing.act : Placing → String
  | .rule => "rule"
  | .want => "want"
  | .verb => "grow"

/-- A rule, a want or a verb a turn places on an object, or takes off it (`line` "" for a removal): a
    change of kind `rule` (4), judged by the object's law when it places (docs/OVERHAUL.md §2 conflict
    8) with `request.verb` naming which (`Placing.act`). A rule's or a want's `line` is its clause; a
    verb's is its reading, with what it `takes` and the rule it `does` (placed in the same turn). -/
structure Placement where
  object : String
  what : Placing
  name : String
  line : String := ""
  takes : String := ""
  does : String := ""
  deriving BEq, Inhabited

def Placement.keyword (x : Placement) : String := x.what.keyword

def Placement.json (x : Placement) : Json :=
  Json.mkObj ([("object", toJson x.object), (x.keyword, toJson x.name)] ++
    (if x.line.isEmpty then [] else if x.what == .verb then
      [("reading", toJson x.line), ("takes", toJson x.takes)] ++ (if x.does.isEmpty then [] else [("does", toJson x.does)])
     else [("line", toJson x.line)]))

def Placement.ofJson (j : Json) : Except String Placement := do
  let object ← j.getObjValAs? String "object"
  let text := fun (k : String) => (j.getObjValAs? String k).toOption.getD ""
  match j.getObjValAs? String "rule", j.getObjValAs? String "want", j.getObjValAs? String "verb" with
  | .ok n, .error _, .error _ => return { object, what := .rule, name := n, line := text "line" }
  | .error _, .ok n, .error _ => return { object, what := .want, name := n, line := text "line" }
  | .error _, .error _, .ok n => return { object, what := .verb, name := n, line := text "reading", takes := text "takes", does := text "does" }
  | _, _, _ => throw "a placement names one rule, one want or one verb"

structure Proposal where
  principal : String
  intent : String
  roots : List (String × Nat)
  writes : List (String × List Written)
  /-- Assigned by the host (`commit` sets it to the entry's height); never read from a client. -/
  turn : Nat := 0
  /-- Reprograms: object, package source, migration entry ("" for none). -/
  programs : List (String × (String × String)) := []
  /-- Objects whose reprogram is an extension over their current code (`mode: extend`). -/
  layered : List String := []
  /-- Amendments: object, new law text. -/
  laws : List (String × String) := []
  /-- Objects the turn required absent, and objects it creates (a subset). -/
  absent : List String := []
  creates : List (String × CreateRec) := []
  /-- Grants the turn makes and grant ids it revokes; they take effect with the commit. -/
  grants : List Grant := []
  revokes : List String := []
  /-- Uses the turn spends of limited grants: grant id and count. -/
  spent : List (String × Nat) := []
  /-- How the turn read each root it did not read whole, by object (`Cells`). -/
  cells : List (String × Cells) := []
  /-- A reprogram's lineage, by object (`become`: the kind whose body it laid), journaled on the
      reprogram as `madeFrom {object, pin, receipt}`. -/
  madeFrom : List (String × Json) := []
  /-- A resumed turn's own object: it may be re-based on the object's current state when it
      moved while the turn waited (`movedRootAdmits`). An entry with `resumes` sets it on replay. -/
  rebaseOwn : Option String := none
  /-- The object whose send the turn delivers ("" for a direct turn): the law's `context.sender`.
      Replay reads it from the pending delivery the entry consumes. -/
  sender : String := ""
  /-- Rules, wants and verbs the turn places and takes off; they take effect with the commit. -/
  placements : List Placement := []

/-- The method a grown verb runs (`act {verb, text}`, docs/FOUNDATION.md §10): its `request.verb` is the verb. -/
def actMethod : String := "act"

/-- The host's own spells on every card (docs/CATALOGUE.md §2, higher-order cards), and its reads,
    answered as `?` is: no verb grows under these names. -/
def hostSpells : List String := ["become", "adopt", "lend", "rule", "unrule", "want", "unwant", "grow", "ungrow",
  "retire", "unretire", "hide", "show"]
def hostReads : List String := ["rules", "wants", "verbs"]

/-- Words a spell reads as no verb: the usage, the lens, the words' way in and the act itself. -/
def verbsReserved : List String := ["?", "set", "receive", actMethod]

/-- What a grown verb takes: a line (`text`), or nothing. -/
def verbTakes : List String := ["text", ""]

/-- A verb's name: a spell's action word (`Spell.identifier`), at most `Limits.verbNameMax` long. -/
def verbWord (name : String) : Bool :=
  !name.isEmpty && name.length ≤ Limits.verbNameMax && name.all fun c => c.isLower || c.isDigit || c == '-'

/-- The names in an object's method table. -/
def methodNames (o : Object) : List String :=
  ((o.methods.getArr?.toOption).getD #[]).toList.filterMap fun m => (m.getObjValAs? String "name").toOption

/-- Writes, plus a direct (caller-less) change of the proper kind for each reprogram or
    amendment that no write of the proposal already names, and one of kind `rule` for each thing a
    placement names: its `request.verb` the placing's (`rule`, `want`, `grow`), judged by the law, or ""
    for a thing only taken off, which the law does not judge. -/
def Proposal.allWrites (p : Proposal) : List (String × List Written) :=
  let placed := (p.placements.map (·.object)).eraseDups.flatMap fun id =>
    let acts := ((p.placements.filter fun x => x.object == id && !x.line.isEmpty).map (·.what.act)).eraseDups
    (if acts.isEmpty then [""] else acts).map ((id, 4, ·))
  let wanted := p.programs.map (fun x => (x.1, 1, "")) ++ p.laws.map (fun x => (x.1, 2, "")) ++ placed
  wanted.foldl (fun acc (id, kind, verb) =>
    let have_ := ((acc.lookup id).getD []).any fun x => x.kind == kind && x.verb == verb
    let w : Written := { caller := "", kind, edits := [], verb }
    if have_ then acc
    else if acc.any (·.1 == id) then
      acc.map fun (i, ws) => if i == id then (i, ws ++ [w]) else (i, ws)
    else acc ++ [(id, [w])]) p.writes

/-- A child id `<parent>/<kind>/<n>` raises its parent's `minted` counter to `n` (any creation of
    that shape, named or minted, so a later mint never collides with a named child). -/
def noteMinted (w : World) (id : String) : World :=
  let parts := id.splitOn "/"
  if parts.length < 3 then w else
  match parts.getLast!.toNat? with
  | none => w
  | some n =>
    let parent := "/".intercalate (parts.take (parts.length - 2))
    match w.objects[parent]? with
    | some p => if p.minted ≥ n then w else { w with objects := w.objects.insert parent { p with minted := n } }
    | none => w

/-- `j.compress.utf8ByteSize`, counted without printing: the state byte bound reads it on every
    write, and printing a large state to measure it was most of a write's cost. -/
partial def compressedSize : Json → Nat
  | .null => 4
  | .bool b => if b then 4 else 5
  | .num n => n.toString.utf8ByteSize
  | .str s => (Json.renderString s "").utf8ByteSize
  | .arr a => 2 + a.foldl (fun n x => n + compressedSize x) 0 + (a.size - 1)
  | .obj kvs =>
    let (n, count) := kvs.foldl (fun (n, c) k v => (n + (Json.renderString k "").utf8ByteSize + 1 + compressedSize v, c + 1)) (0, 0)
    2 + n + (count - 1)

/-- The bytes of a state as the bound counts them: the canonical DAG-CBOR of the Data
    (`Delvetalk.Canonical.encode`), not its verbose wire JSON, where a relation row cost about 150
    bytes of tags and names (the Anthology refused its 631st short line). -/
def stateBytes (state : Data) : Nat := (Delvetalk.Canonical.encode state).size


/-- Roots as an entry records them: `{object, version}` for a root read whole, and for one read by
    its cells (`Cells`) what was read: `scalar: true`, `fields [f]`, `rows [{field, key}]`, `spans
    [{field, through?}]` (no `through`: the whole key set), `gaps [{field, after?, before?}]`. The state
    at that version is named by the entry that wrote it (`writes[].cid`, `world-state-cid`). -/
def rootsJson (roots : List (String × Nat)) (cells : List (String × Cells) := []) : Json :=
  Json.arr (roots.toArray.map fun (o, v) => Json.mkObj ([("object", toJson o), ("version", toJson v)] ++
    match cells.lookup o with
    | none => []
    | some r =>
      (if r.scalar then [("scalar", toJson true)] else []) ++
      (if r.fields.isEmpty then [] else [("fields", toJson r.fields)]) ++
      (if r.rows.isEmpty then [] else [("rows", Json.arr (r.rows.toArray.map fun (f, k) =>
        Json.mkObj [("field", toJson f), ("key", dataJson k)]))]) ++
      (if r.spans.isEmpty then [] else [("spans", Json.arr (r.spans.toArray.map fun (f, t) =>
        Json.mkObj ([("field", toJson f)] ++ (t.map fun k => [("through", dataJson k)]).getD [])))]) ++
      (if r.gaps.isEmpty then [] else [("gaps", Json.arr (r.gaps.toArray.map fun (f, after, before) =>
        Json.mkObj ([("field", toJson f)] ++ (after.map fun k => [("after", dataJson k)]).getD [] ++
          (before.map fun k => [("before", dataJson k)]).getD [])))])))

/-- The fields recording who made each change: parallel arrays of steps, callers, kinds. -/
def writtenFields (ws : List Written) : List (String × Json) :=
  [("edits", stepsJson (ws.map (·.edits))), ("callers", toJson (ws.map (·.caller))),
   ("kinds", toJson (ws.map (·.kind)))] ++
  (if ws.all (·.method.isEmpty) then [] else [("methods", toJson (ws.map (·.method)))]) ++
  (if ws.all (·.via.isEmpty) then [] else [("vias", toJson (ws.map (·.via)))]) ++
  (if ws.all (·.verb.isEmpty) then [] else [("verbs", toJson (ws.map (·.verb)))]) ++
  (if ws.all (fun w => match w.argument with | .record [] => true | _ => false) then []
   else [("arguments", Json.arr (ws.toArray.map (dataJson ·.argument)))])

def writesJson (writes : List (String × List Written)) : Json :=
  Json.arr (writes.toArray.map fun (o, ws) => Json.mkObj (("object", toJson o) :: writtenFields ws))

/-- An entry's `roots` (`rootsJson`): the roots at their versions, and how each root read by its
    cells was read. Together within `maxRoots`. -/
def parseRoots (j : Json) : Except String (List (String × Nat) × List (String × Cells)) := do
  let raw ← j.getArr?
  let mut out : List (String × Nat) := []
  let mut cells : List (String × Cells) := []
  for r in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← r.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate root"
    out := out ++ [(object, ← natField r "version")]
    let list := fun (k : String) => ((r.getObjVal? k).toOption.map fun a => a.getArr?.map (·.toList)).getD (pure [])
    let scalar := (r.getObjValAs? Bool "scalar").toOption.getD false
    let fields ← (← list "fields").mapM (·.getStr?)
    let rows ← (← list "rows").mapM fun x => do
      return (← x.getObjValAs? String "field", ← decodeData Limits.dataDepth (← x.getObjVal? "key"))
    let spans ← (← list "spans").mapM fun x => do
      return (← x.getObjValAs? String "field", ← match x.getObjVal? "through" with
        | .ok k => some <$> decodeData Limits.dataDepth k
        | .error _ => pure none)
    let key : Json → String → Except String (Option Data) := fun x k => match x.getObjVal? k with
      | .ok d => some <$> decodeData Limits.dataDepth d
      | .error _ => pure none
    let gaps ← (← list "gaps").mapM fun x => do
      return (← x.getObjValAs? String "field", ← key x "after", ← key x "before")
    if scalar || !fields.isEmpty || !rows.isEmpty || !spans.isEmpty || !gaps.isEmpty then
      cells := cells ++ [(object, ({ scalar := scalar, fields, rows, spans, gaps } : Cells))]
  if out.length + (cells.map (·.2.extra)).sum > Limits.maxRoots then throw "too many roots"
  return (out, cells)

/-- Writes as a client sends them: direct, so every step has the empty caller, and proposed (kind
    `Law.proposedKind`): no method of the object made them. A client cannot name a caller. -/
def parseWrites (j : Json) : Except String (List (String × List Written)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxWrites then throw "too many writes"
  let mut out : List (String × List Written) := []
  for w in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← w.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate write"
    out := out ++ [(object, (← parseSteps (← w.getObjVal? "edits")).map fun step =>
      { caller := "", kind := Law.proposedKind, edits := step })]
  return out

/-- Writes as the journal records them: steps with their callers and kinds. -/
def parseRecordedWrites (j : Json) : Except String (List (String × List Written)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxWrites then throw "too many writes"
  let mut out : List (String × List Written) := []
  for w in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← w.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate write"
    let steps ← parseSteps (← w.getObjVal? "edits")
    let callers ← (← (← w.getObjVal? "callers").getArr?).toList.mapM (·.getStr?)
    let kinds ← (← (← w.getObjVal? "kinds").getArr?).toList.mapM natOf
    let optional := fun (key : String) => do
      match w.getObjVal? key with
      | .ok a => (← a.getArr?).toList.mapM (·.getStr?)
      | .error _ => pure (steps.map fun _ => "")
    let methods ← optional "methods"
    let vias ← optional "vias"
    let verbs ← optional "verbs"
    let arguments ← match w.getObjVal? "arguments" with
      | .ok a => (← a.getArr?).toList.mapM (decodeData Limits.dataDepth)
      | .error _ => pure (steps.map fun _ => Data.record [])
    unless callers.length == steps.length && kinds.length == steps.length && methods.length == steps.length &&
        vias.length == steps.length && arguments.length == steps.length && verbs.length == steps.length do
      throw "a write's callers, kinds, methods, vias, arguments and verbs must match its edits"
    out := out ++ [(object, (steps.zip (callers.zip (kinds.zip (methods.zip (vias.zip (arguments.zip verbs)))))).map
      fun (step, caller, kind, method, via, argument, verb) => { caller, kind, edits := step, method, via, argument, verb })]
  return out

/-- A direct proposal. A write must name an object among its roots; `turn` is the
    host's to assign, so a request that carries one is refused. -/
def parseProposal (j : Json) : Except String Proposal := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  if (j.getObjVal? "turn").toOption.isSome then throw "turn is assigned by the host and cannot be supplied"
  let (roots, cells) ← parseRoots (← j.getObjVal? "roots")
  let writes ← parseWrites (← j.getObjVal? "writes")
  for (id, _) in writes do
    unless roots.any (·.1 == id) do throw s!"write names {id}, which is not among the roots"
  return { principal, intent, roots, writes, cells }

def spentJson (spent : List (String × Nat)) : Json :=
  Json.arr (spent.toArray.map fun (id, n) => Json.mkObj [("id", toJson id), ("uses", toJson n)])

def parseSpent (j : Option Json) : Except String (List (String × Nat)) := do
  let some raw := j | return []
  (← raw.getArr?).toList.mapM fun x => do return (← x.getObjValAs? String "id", ← natField x "uses")

/-- Digest binding an identity to the request that first used it. -/
def Proposal.digest (p : Proposal) : String :=
  let programs := p.programs.map fun (id, (src, mig)) => Json.mkObj
    [("object", toJson id), ("source", toJson (Journal.bodyHash src)), ("migration", toJson mig)]
  let laws := p.laws.map fun (id, text) => Json.mkObj [("object", toJson id), ("law", toJson text)]
  Journal.bodyHash (Json.mkObj ([("roots", rootsJson p.roots p.cells), ("writes", writesJson p.allWrites)] ++
    (if programs.isEmpty then [] else [("programs", Json.arr programs.toArray)]) ++
    (if p.layered.isEmpty then [] else [("extends", toJson p.layered)]) ++
    (if laws.isEmpty then [] else [("laws", Json.arr laws.toArray)]) ++
    (if p.absent.isEmpty then [] else [("absent", toJson p.absent)]) ++
    (if p.creates.isEmpty then [] else [("creates", Json.arr (p.creates.toArray.map fun (id, c) => Json.mkObj
      [("object", toJson id), ("pin", toJson c.object.pin), ("seed", toJson (Journal.bodyHash c.seed.compress)),
       ("law", toJson c.object.lawText)]))]) ++
    (if p.grants.isEmpty then [] else [("grants", Json.arr (p.grants.toArray.map Grant.json))]) ++
    (if p.revokes.isEmpty then [] else [("revokes", toJson p.revokes)]) ++
    (if p.spent.isEmpty then [] else [("spent", spentJson p.spent)]) ++
    (if p.placements.isEmpty then [] else [("placements", Json.arr (p.placements.toArray.map (·.json)))])))

/-! ## Judging -/

/-- The closed set of refusal classes. -/
def refusalClasses : List String :=
  ["staleRoot", "typeMismatch", "capacity", "absentItem", "lawRefused", "unknownObject",
   "duplicateIdentity", "evaluation", "budget", "budgetExhausted", "programRefused", "requiredAbsence",
   "keyTaken", "duplicateKey", "badSpell", "quota", "noMethod", "quiet", "cardRefused"]

open Lean Elab Term in
/-- `natsIn% N`: every `Nat` definition of namespace `N`, as `[(its name, its value)]` in name order, so a
    bound is written once, by its definition, and answered from there. -/
elab "natsIn% " ns:ident : term => do
  let pre := ns.getId
  let names := (← getEnv).constants.fold (init := #[]) fun acc n ci =>
    if n.getPrefix == pre && !n.isInternal && ci.type == Lean.mkConst ``Nat && ci.isDefinition then acc.push n else acc
  let items ← (names.qsort (·.toString < ·.toString)).mapM fun n =>
    `((($(quote (n.getString!)) : String), Lean.toJson $(mkIdent n)))
  elabTerm (← `([$items,*])) none

structure Refusal where
  cls : String
  clause : Option String := none
  object : Option String := none
  /-- Named reason for an `evaluation` refusal. -/
  reason : Option String := none
  /-- For `typeMismatch` of a turn's argument: what the method takes (`{type, form?}`). -/
  expected : Option Json := none
  /-- The root the refusal was judged against when it is not `object`: for `requiredAbsence`, the
      object whose create found `object` already there. -/
  root : Option String := none
  /-- For `badSpell`: the spell the reply meant, its blanks shown, to resend. -/
  hint : Option String := none
  /-- For `quota`: the clock at which the principal may try again. -/
  next : Option Nat := none
  /-- For `lawRefused`: the refusing clause's reading, wherever the law came from (the package, a law
      given at creation or by amendment, a Bend verdict, a kind's clause it cites, the host's own clauses).
      For `cardRefused`: the reading of the card's own line. Journaled beside `reason`, which `voiced`
      writes from it: `refused <clause>: <reading>`. -/
  reading : Option String := none

/-- `text` within `bytes` UTF-8 bytes: whole, or its longest prefix of whole characters that fits
    followed by `…`. -/
def withinBytes (text : String) (bytes : Nat) : String :=
  if text.utf8ByteSize ≤ bytes then text else
  (text.foldl (fun (kept : String × Nat) c =>
    if kept.2 + c.utf8Size ≤ bytes then (kept.1.push c, kept.2 + c.utf8Size) else (kept.1, bytes + 1)) ("", 0)).1 ++ "…"

/-- A card's own refusal (`refuse(line)` in its Bend, class `cardRefused`), refused by `object`: the
    clause and reading of a line `refused <clause>: <reading>` (the clause one word, split at the first
    `: `), else clause `card` and the whole line as the reading. The reading is journaled within
    `Limits.maxRefusalBytes` (`withinBytes`): the card's refusal stands, its text is bounded. -/
def cardRefusal (object line : String) : Refusal :=
  let parsed : Option (String × String) :=
    if line.startsWith "refused " then
      match (line.drop "refused ".length).toString.splitOn ": " with
      | clause :: reading :: more =>
        if clause.isEmpty || clause.any Char.isWhitespace || clause.utf8ByteSize > Limits.maxMethodBytes then none
        else some (clause, ": ".intercalate (reading :: more))
      | _ => none
    else none
  let (clause, reading) := parsed.getD ("card", line)
  { cls := "cardRefused", clause := some clause, object := some object,
    reading := some (withinBytes reading Limits.maxRefusalBytes) }

def replaceField (fields : List (String × Data)) (name : String) (v : Data) : List (String × Data) :=
  fields.map fun (k, old) => if k == name then (k, v) else (k, old)

/-- Plain JSON for a model to read: lists are arrays, a sum is an object with its `tag`. -/
partial def listHeads (acc : List Data) : Data → Option (List Data)
  | .variant "nil" _ => some acc.reverse
  | .variant "cons" (.record f) => do
    let head ← f.lookup "head"
    let tail ← f.lookup "tail"
    listHeads (head :: acc) tail
  | _ => none

partial def plainJson : Data → Json
  | .natural n => toJson n
  | .boolean b => toJson b
  | .label s => toJson s
  | .record fs => Json.mkObj (fs.map fun (k, v) => (k, plainJson v))
  | d@(.variant l p) =>
    match listHeads [] d with
    | some items => Json.arr (items.toArray.map plainJson)
    | none => match p with
      | .record fs => Json.mkObj (("tag", toJson l) :: fs.map fun (k, v) => (k, plainJson v))
      | other => Json.mkObj [("tag", toJson l), ("value", plainJson other)]

/-- The refusal of a state with a cell past `Bounds.maxCellBytes` (KERNEL-HANDOFF §15 step 4):
    `capacity`, clause `maxCellBytes`, the reason naming the cell. -/
def cellRefusal (id : String) (cell : String × Data) (cls : String := "capacity") : Refusal :=
  let what := if cell.1 == "scalar" then "its scalar fields"
    else s!"the {cell.1} row keyed {(plainJson cell.2).compress}"
  { cls, clause := some "maxCellBytes", object := some id,
    reason := some s!"{what} of {id} pass maxCellBytes ({Delvetalk.Bounds.maxCellBytes} canonical bytes); write less to that cell." }

/-- The prefix the kernel puts in front of a refusal it reports as text. -/
def kernelPrefix : String := "turn refused: "

/-- A ledger field a chain of sends spent (`budgetExhausted`), as its reason says it. -/
def exhaustedReason (field : String) : String := s!"the chain of sends spent its {field}."

/-- A refusal's `reason` as the town reads it (docs/VOICE.md, "The host's refusals"), from what the
    refusal names: the class, the object, the limit or resource, the clause. Classes whose reason the
    site writes (lawRefused, quota, noMethod, badSpell) keep it. Applied once, where `commit`
    journals the refusal. -/
def Refusal.voiced (r : Refusal) : Refusal :=
  let obj := r.object.getD ""
  let given := (r.reason.map fun t => if t.startsWith kernelPrefix then (t.drop kernelPrefix.length).toString else t)
  let reason := match r.cls with
    | "staleRoot" => some s!"{obj} moved while you wrote; send the same spell again."
    | "budget" => some s!"the turn ran out of {given.getD "ticks"}; make it smaller, or send it again later."
    | "evaluation" => given
    | "capacity" => match given with
      | some m => if m.any (· == ' ') then some m else some s!"the host's {m} is full; try later."
      | none => some s!"the host's {if obj.isEmpty then "capacity" else obj} is full; try later."
    | "typeMismatch" =>
      let method := ((r.expected.bind fun e => (e.getObjValAs? String "method").toOption)).getD "it"
      let pointer := s!"reply delvetalk {obj} ? for its spell."
      -- A word that names no case says which: "colour is one of: amber, violet (not gold)".
      match given with
      | some m => if m.startsWith "argument does not conform to its type: " then some s!"{(m.drop 39).toString}; {pointer}"
        else if m.startsWith "argument does not conform" || m.isEmpty then some s!"not what {method} takes; {pointer}"
        else some s!"{m}; {pointer}"
      | none => some s!"not what {method} takes; {pointer}"
    | "unknownObject" => some s!"no card {obj} that you may see; the commonplace lists the doors."
    | "programRefused" =>
      let head := s!"the package was refused at {r.clause.getD "compile"}; the workshop's check shows where"
      -- The compiler's or the migration's diagnostic follows: the proposer sees the cause.
      some (match given with
        | some m => if m.isEmpty then head ++ "." else s!"{head}: {m}"
        | none => head ++ ".")
    | "absentItem" => some "that item is not in the list now."
    | "requiredAbsence" => some s!"{obj} is already there; {r.root.getD ""} found it."
    | "keyTaken" => some "another row holds that key; upsert, or add an ordinal."
    | "duplicateKey" => some "the write names one key twice."
    | "budgetExhausted" => given.map exhaustedReason
    | "lawRefused" | "cardRefused" => (r.reading.map fun t => s!"refused {r.clause.getD "law"}: {t}") <|> given
    | _ => given
  { r with reason }

/-- Why an edit does not apply: `typeMismatch` (the field or value is not of the kind the
    edit needs), `absentItem`, `keyTaken`, `duplicateKey`. -/
abbrev EditResult := Except String

/-- A `List<T>` on the wire is `nil {} | cons {head, tail}`. -/
partial def appendItem (item : Data) : Data → EditResult Data
  | .variant "nil" _ => pure (.variant "cons" (.record [("head", item), ("tail", .variant "nil" (.record []))]))
  | .variant "cons" (.record f) => do
    let some head := f.lookup "head" | throw "typeMismatch"
    let some tail := f.lookup "tail" | throw "typeMismatch"
    pure (.variant "cons" (.record [("head", head), ("tail", ← appendItem item tail)]))
  | _ => throw "typeMismatch"

/-- Replace (`some change`) or remove (`none`) the first item whose canonical bytes are `item`'s;
    `absentItem` when no item is. -/
partial def editByItem (item : Data) (change : Option Data) : Data → EditResult Data
  | .variant "nil" _ => throw "absentItem"
  | .variant "cons" (.record f) => do
    let some head := f.lookup "head" | throw "typeMismatch"
    let some tail := f.lookup "tail" | throw "typeMismatch"
    if Delvetalk.Canonical.encode head == Delvetalk.Canonical.encode item then
      match change with
      | some c => pure (.variant "cons" (.record [("head", c), ("tail", tail)]))
      | none => pure tail
    else pure (.variant "cons" (.record [("head", head), ("tail", ← editByItem item change tail)]))
  | _ => throw "typeMismatch"

/-! ## Relations (RELATIONAL.md §2, §3)

A relation is a state field the package declares in `relations()`: `rows {items: List<T>}` of records
`T`, kept sorted by the canonical bytes of each row's key projection, no two rows sharing a key, and
at most its declared number of rows (the oldest by key order dropped). The host keeps that form:
`canonicalRelation` on seeds, migration results and every write; the three edits in `applyStep`. -/

partial def listOf : Data → Option (List Data)
  | .variant "nil" _ => some []
  | .variant "cons" (.record f) => do
    let head ← f.lookup "head"
    return head :: (← listOf (← f.lookup "tail"))
  | _ => none

def ofList (items : List Data) : Data :=
  items.foldr (fun x t => .variant "cons" (.record [("head", x), ("tail", t)])) (.variant "nil" (.record []))

/-- A relation value's rows. -/
def relationRows : Data → EditResult (List Data)
  | .variant "rows" (.record f) => match (f.lookup "items").bind listOf with
    | some rows => pure rows
    | none => throw "typeMismatch"
  | _ => throw "typeMismatch"

def relationOf (rows : List Data) : Data := .variant "rows" (.record [("items", ofList rows)])

/-- A row's key: its key columns, in the declaration's order, as a record. -/
def keyOf (d : RelDecl) : Data → EditResult Data
  | .record cols => do
    return .record (← d.key.mapM fun k => match cols.lookup k with
      | some v => pure (k, v)
      | none => throw "typeMismatch")
  | _ => throw "typeMismatch"

/-- A key as the edit gives it, put in the declaration's column order. -/
def keyAsDeclared (d : RelDecl) (key : Data) : EditResult Data := keyOf d key

/-- Rows sorted by their keys' canonical bytes, no key twice (`duplicateKey`), the oldest by key
    order dropped past the declared limit; with the rows dropped. -/
def canonicalRowsDropping (d : RelDecl) (rows : List Data) : EditResult (List Data × List Data) := do
  let keyed ← rows.mapM fun r => do return (Delvetalk.Canonical.encode (← keyOf d r), r)
  let sorted := (keyed.toArray.qsort fun a b => Delvetalk.Canonical.bytesLt a.1 b.1).toList
  let mut prev : Option ByteArray := none
  for (k, _) in sorted do
    if prev == some k then throw "duplicateKey"
    prev := some k
  let over := sorted.length - d.cap
  return ((sorted.drop over).map (·.2), (sorted.take over).map (·.2))

def canonicalRows (d : RelDecl) (rows : List Data) : EditResult (List Data) :=
  (·.1) <$> canonicalRowsDropping d rows

def canonicalRelation (d : RelDecl) (v : Data) : EditResult Data := do
  return relationOf (← canonicalRows d (← relationRows v))

/-- Every declared relation of a state record in canonical form. -/
def canonicalState (decls : List RelDecl) : Data → EditResult Data
  | .record fields => do
    return .record (← fields.mapM fun (k, v) => match decls.find? (·.field == k) with
      | some d => do return (k, ← canonicalRelation d v)
      | none => pure (k, v))
  | other => if decls.isEmpty then pure other else throw "typeMismatch"

/-- A row's cell under `d`; `typeMismatch` when it lacks a key column. -/
def rowCell (d : RelDecl) (row : Data) : EditResult Delvetalk.Turn.RowCell := do
  discard <| keyOf d row
  return Delvetalk.Turn.RowCell.of d.key row

/-- A relation after `put` was inserted, within its declared limit: the oldest rows by key order
    (the first) dropped, with them. -/
def withinLimit (d : RelDecl) (r : Delvetalk.Turn.RelationCells) (put : Delvetalk.Turn.RowCell) :
    Delvetalk.Turn.RelationCells × List Data × Option Delvetalk.Turn.RowCell :=
  let over := r.rows.size - d.cap
  ((List.range over).foldl (fun r _ => r.eraseAt 0) r, (r.rows.extract 0 over).toList.map (·.row), some put)

/-- One relation edit on a relation's cells (the table of RELATIONAL.md §3), by binary search on the
    key's canonical bytes; with the rows the declared retention dropped to keep it within its limit
    (the oldest by key order) and the row it put, if any:

    | edit    | key absent | key present, same row | key present, other row |
    | insert  | add        | no change             | refused `keyTaken`     |
    | upsert  | add        | no change             | replace                |
    | retract | no change  | remove                | remove                 | -/
def relationEdit (d : RelDecl) (old : Delvetalk.Turn.RelationCells) (kind : EditKind) :
    EditResult (Delvetalk.Turn.RelationCells × List Data × Option Delvetalk.Turn.RowCell) := do
  match kind with
  | .insert row | .upsert row =>
    let c ← rowCell d row
    let i := old.position c.key
    match old.rows[i]? with
    | some x =>
      if x.key != c.key then return withinLimit d (old.insertAt i c) c
      else if x.cid == c.cid then return (old, [], none)
      else match kind with
        | .insert _ => throw "keyTaken"
        | _ => return (old.setAt i c, [], some c)
    | none => return withinLimit d (old.insertAt i c) c
  | .retract key =>
    match old.find? (Delvetalk.Canonical.encode (← keyAsDeclared d key)) with
    | some (i, _) => return (old.eraseAt i, [], none)
    | none => return (old, [], none)
  | _ => throw "typeMismatch"

/-- A state under a write: its scalar fields (a relation's holding the empty relation) and its
    relations' cells, with the rows retention evicted and the rows put, by field. -/
structure Editing where
  scalar : List (String × Data)
  relations : List Delvetalk.Turn.RelationCells
  evicted : List (String × Data) := []
  put : List (String × Delvetalk.Turn.RowCell) := []

/-- All edits of a step read the state before the step. A relation field takes `insert`, `upsert`,
    `retract` (`relationEdit`) and `set` (its rows put in canonical form); a scalar field every other
    edit. -/
def applyStep (decls : List RelDecl) (state : Editing) (step : Step) : EditResult Editing :=
  step.foldlM (init := state) fun acc e => do
    let some old := state.scalar.lookup e.field | throw "typeMismatch"
    match decls.find? (·.field == e.field) with
    | some d =>
      let some rel := state.relations.find? (·.field == e.field) | throw "typeMismatch"
      let (rel, dropped, put) ← match e.kind with
        | .keep => pure (rel, [], [])
        | .set v => do
          let rows ← (← canonicalRows d (← relationRows v)).mapM (rowCell d)
          pure (Delvetalk.Turn.RelationCells.of rel.field rel.key rows.toArray, [], rows)
        | .insert _ | .upsert _ | .retract _ => do
          let (rel, dropped, put) ← relationEdit d rel e.kind
          pure (rel, dropped, put.toList)
        | _ => throw "typeMismatch"
      return { acc with relations := acc.relations.map fun r => if r.field == e.field then rel else r,
                        evicted := acc.evicted ++ dropped.map (e.field, ·), put := acc.put ++ put.map (e.field, ·) }
    | none =>
      let put := fun (v : Data) => pure { acc with scalar := replaceField acc.scalar e.field v }
      match e.kind with
      | .keep => pure acc
      | .set v => put v
      | .add n => match old with
          | .natural m => put (.natural (m + n))
          | _ => throw "typeMismatch"
      | .append item => put (← appendItem item old)
      | .amendItem item c => put (← editByItem item (some c) old)
      | .removeItem item => put (← editByItem item none old)
      | .insert _ | .upsert _ | .retract _ => throw "typeMismatch"

/-- What a write made: the state's cells after it, the rows the declared retention evicted to make
    room for an insert or an upsert, by field (codex host 8, 10: `insertOnly` and the conflict index
    read them), and the cells it changed (`Turn.Changes`: what is checked, bounded and charged). -/
structure Applied where
  cells : Delvetalk.Turn.StateCells
  evicted : List (String × Data)
  changes : Delvetalk.Turn.Changes

/-- The steps applied in order to `before`'s cells. Only the cells they reach are touched. -/
def applyEdits (decls : List RelDecl) (before : Delvetalk.Turn.StateCells) (steps : List Step) : EditResult Applied := do
  let .record fields := before.scalar | throw "typeMismatch"
  let e ← steps.foldlM (applyStep decls) { scalar := fields, relations := before.relations }
  let cells := Delvetalk.Turn.StateCells.make (.record e.scalar) e.relations
  return { cells, evicted := e.evicted, changes := Delvetalk.Turn.Changes.of before cells e.put }

/-- The rows a write's edits put, by field, as cells: what `Turn.Changes.of` weighs. -/
def putRows (decls : List RelDecl) (changes : List Written) : List (String × Delvetalk.Turn.RowCell) :=
  changes.flatMap fun c => c.edits.flatMap fun e => match decls.find? (·.field == e.field), e.kind with
    | some d, .insert row | some d, .upsert row => [(e.field, Delvetalk.Turn.RowCell.of d.key row)]
    | some d, .set v => ((relationRows v).toOption.getD []).map fun row => (e.field, Delvetalk.Turn.RowCell.of d.key row)
    | _, _ => []

/-- The canonical bytes the cells a turn's writes changed hold (`Turn.Changes`): what the storage
    ledger charges. A created object's every cell is new. -/
def chargedBytes (before : Option Object) (after : Object) (changes : List Written) : Nat :=
  match before with
  | some b => (Delvetalk.Turn.Changes.of b.cells after.cells (putRows after.relations changes)).bytes after.cells
  | none => (Delvetalk.Turn.Changes.all after.cells).bytes after.cells

/-! ## Law as state, and programs -/

/-- The state type is the type of the package's entry definition: a zero-argument
    `def initial() -> State` has type `State`, which must be a closed record of
    first-order data. The entry's own value is not used; the seed is explicit. -/
def stateTypeOk (assumptions : Delvetalk.Theory.ObjectiveBendTyping.Assumptions)
    (ty : Delvetalk.Theory.ObjectiveBendTypes.Ty) : Bool :=
  ty.isDataUnder assumptions.bounds assumptions.rigid Delvetalk.Theory.ObjectiveBendTypes.Ty.dataFuel [] &&
    match ty with
    | .field .. | .emptyRow => true
    | _ => false

/-- A type with its variables renamed in order of first use, each bound one's body written once
    where first met: two state types are the same exactly when these agree, whatever numbering the
    compiles gave their bounds (a layer stack's packet numbers them anew). -/
partial def canonicalTy (bounds : DataBounds) (ty : Delvetalk.Theory.ObjectiveBendTypes.Ty) : Except String Json :=
  (go ty).run' ([], 0)
where
  go : Delvetalk.Theory.ObjectiveBendTypes.Ty → StateT (List (Nat × Nat) × Nat) (Except String) Json
    | .variable i => do
      let (seen, steps) ← get
      if steps > 4096 then throw "type too deep to compare"
      set (seen, steps + 1)
      match seen.lookup i with
      | some k => return Json.mkObj [("ref", toJson k)]
      | none =>
        let k := seen.length
        set (seen ++ [(i, k)], steps + 1)
        match bounds.lookup i with
        | some body => return Json.mkObj [("var", toJson k), ("is", ← go body)]
        | none => return Json.mkObj [("free", toJson k)]
    | .field n m t => do return Json.mkObj [("field", toJson n), ("member", ← go m), ("tail", ← go t)]
    | .variant r => do return Json.mkObj [("variant", ← go r)]
    | other => pure (Delvetalk.Theory.ObjectiveBendTyping.typeJson other)

def inputsKeyOf (inputs : Json) : String :=
  Journal.bodyHash (Json.mkObj (inputs.getObj?.toOption.map (·.toList.filter (·.1 != "entry")) |>.getD []))

/-! ## The standard library

A world opened with a library seals `world/lib/**/*.obend` as a closure: module name
(file name without `.obend`), source, dependency order. An object's compile inputs
name it by `"library": pin`; the modules the package imports (transitively) are
prepended to the package's own modules when it is compiled, so a package can
`import ./Plan.obend as Plans` without carrying the source. -/

/-- The module names a source imports (`import ./Name.obend as X` lines). -/
def importsOf (source : String) : List String :=
  (source.splitOn "\n").filterMap fun line =>
    (line.dropPrefix? "import ./").bind fun rest => ((rest.toString.splitOn ".obend").head?)

def libraryDigest (modules : List (String × String)) : String :=
  Journal.bodyHash (Json.arr (modules.toArray.map fun (n, src) =>
    Json.mkObj [("name", toJson n), ("source", toJson src)]))

def modulesJson (modules : List (String × String)) : Json :=
  Json.arr (modules.toArray.map fun (n, src) => Json.mkObj [("name", toJson n), ("source", toJson src)])

def parseModules (j : Json) : Except String (List (String × String)) := do
  (← j.getArr?).toList.mapM fun m => do return (← m.getObjValAs? String "name", ← m.getObjValAs? String "source")

/-- Seal files `(name, source)` into a library: names unique identifiers, every import
    present, no cycle; order is by rounds of ready modules, each in name order. -/
def sealLibrary (files : List (String × String)) : Except String Library := do
  if files.length > Limits.maxLibraryModules then
    throw s!"library has {files.length} modules, more than {Limits.maxLibraryModules}"
  let bytes := files.foldl (fun n (name, src) => n + name.utf8ByteSize + src.utf8ByteSize) 0
  if bytes > Limits.maxLibraryBytes then throw s!"library exceeds {Limits.maxLibraryBytes} bytes"
  let names := files.map (·.1)
  for n in names do
    unless Delvetalk.Compiler.ObjectiveBendParse.isIdent n.toList do throw s!"library module name `{n}` is not an identifier"
  if names.eraseDups.length != names.length then throw "library has two modules of one name"
  for (n, src) in files do
    for i in importsOf src do
      unless names.contains i do throw s!"library module {n} imports {i}, which is not in the library"
  let sorted := (files.toArray.qsort fun a b => a.1 < b.1).toList
  let mut placed : List (String × String) := []
  let mut rest := sorted
  for _ in [0:files.length + 1] do
    if rest.isEmpty then break
    let ready := rest.filter fun (_, src) => (importsOf src).all fun i => placed.any (·.1 == i)
    if ready.isEmpty then throw "library modules import each other in a cycle"
    placed := placed ++ ready
    rest := rest.filter fun (n, _) => !ready.any (·.1 == n)
  unless rest.isEmpty do throw "library modules import each other in a cycle"
  return { pin := libraryDigest placed, modules := placed }

/-- The library modules a set of module sources needs, transitively, in library order. -/
def libraryClosure (lib : Library) (sources : List String) : List (String × String) := Id.run do
  -- A worklist: each library module's imports are read once, when it is first wanted.
  let mut wanted : Std.HashSet String := {}
  let mut todo := (sources.flatMap importsOf).eraseDups
  for _ in [0:lib.modules.length + 1] do
    let fresh := todo.filter (!wanted.contains ·)
    if fresh.isEmpty then break
    wanted := fresh.foldl (·.insert ·) wanted
    todo := (fresh.flatMap fun n => ((lib.modules.lookup n).map importsOf).getD []).eraseDups
  return lib.modules.filter fun (n, _) => wanted.contains n

/-- A package's own modules over a library, as the compiler is given them: the library modules
    they import (transitively, in library order), then the own modules that are not the library's
    own bytes. A module of a library module's name with other bytes is refused. When every own
    module is the library's (a package named from the library: `world-arrive`, a check of a
    library module), the last of them is the entry and stays, after the library modules it imports. -/
def overLibrary (lib : Library) (own : List (String × String)) : Except String (List (String × String)) := do
  for (n, src) in own do
    if let some libSrc := lib.modules.lookup n then
      unless libSrc == src do throw s!"module {n} shadows the library module of that name"
  let mine := own.filter fun (n, _) => (lib.modules.lookup n).isNone
  match mine, own.getLast? with
  | [], some entry => return libraryClosure lib [entry.2] ++ [entry]
  | _, _ => return libraryClosure lib (mine.map (·.2)) ++ mine

/-- Compile inputs with the library modules prepended; inputs without `"library"` are as given.
    The result is for the compiler only; the object keeps the inputs it was given. -/
def resolveInputs (w : World) (inputs : Json) : Except String Json := do
  let some pin := (inputs.getObjValAs? String "library").toOption | return inputs
  let some lib := w.libraries[pin]? | throw s!"unknown library pin {pin}"
  let own ← match inputs.getObjVal? "modules" with
    | .ok m => parseModules m
    | .error _ => pure [("Main", ← inputs.getObjValAs? String "source")]
  let modules ← overLibrary lib own
  let fields := (inputs.getObj?.toOption.map (·.toList) |>.getD []).filter fun (k, _) =>
    k != "library" && k != "source" && k != "modules"
  return Json.mkObj (("modules", modulesJson modules) :: fields)

/-- Name the world's current library in compile inputs (a package of one `source` becomes
    the module `Main`). Without a library the inputs are as given. -/
def attachLibrary (w : World) (inputs : Json) : Except String Json := do
  let some lib := w.library | return inputs
  let own ← match inputs.getObjVal? "modules" with
    | .ok m => parseModules m
    | .error _ => pure [("Main", ← inputs.getObjValAs? String "source")]
  -- A package named from the library keeps its entry module (`overLibrary`).
  let own := match own.filter (fun (n, src) => lib.modules.lookup n != some src), own.getLast? with
    | [], some entry => [entry]
    | mine, _ => mine
  let fields := (inputs.getObj?.toOption.map (·.toList) |>.getD []).filter fun (k, _) =>
    k != "source" && k != "modules" && k != "library"
  let attached := Json.mkObj (("modules", modulesJson own) :: ("library", toJson lib.pin) :: fields)
  discard <| resolveInputs w attached
  return attached

/-- The source of an object's entry module: the last of its own modules. -/
def entrySource (o : Object) : String :=
  match o.inputs.getObjVal? "modules" with
  | .ok (.arr modules) => ((modules.back?.bind fun m => (m.getObjValAs? String "source").toOption)).getD ""
  | _ => (o.inputs.getObjValAs? String "source").toOption.getD ""

/-- Does a compiled artifact answer spells: is `receive` among its methods (docs/AUTHORING.md D-receive)? -/
def answersSpells (artifact : Json) : Bool :=
  (((artifact.getObjVal? "methods").toOption.bind (·.getArr?.toOption)).getD #[]).any fun m =>
    (m.getObjValAs? String "name").toOption == some "receive"

/-- A dry-run compile's diagnostics, `"<module>:<line>: <stage>: <message>"` (the kernel's hint, when
    it has one, the next line at the same place), none when it is clean; `fallback` names the
    module when the kernel names none. A package that declares laws compiles, as it would at
    `world-create`. With them, whether what compiled answers spells (`answersSpells`). -/
def checkDiagnosticsCold (modules : List (String × String)) (entry fallback : String) : List String × Bool :=
  let request := Json.mkObj [("entry", toJson entry), ("limits", Package.defaultLimits), ("modules", modulesJson modules)]
  match Package.compileStructured request with
  | .ok (artifact, _, _) => ([], answersSpells artifact)
  | .error e =>
    let d := Package.localize modules Package.defaultLimits e
    let at_ := s!"{d.sourceModule.getD fallback}:{(d.span.map (·.line)).getD 0}"
    ([s!"{at_}: {d.stage}: {d.message}"] ++ (d.hint.map fun h => [s!"{at_}: hint: {h}"]).getD [], false)

/-- This process's dry-run diagnostics by the digest of what was checked (modules, entry, fallback): a check is
    a pure function of them, and the workshop's `check` and `propose` re-check one draft (and the library under it)
    many times. -/
initialize checkMemo : IO.Ref (Std.HashMap String (List String × Bool)) ← IO.mkRef {}

unsafe def checkDiagnosticsImpl (modules : List (String × String)) (entry fallback : String) : List String × Bool :=
  unsafeBaseIO do
    let key := Journal.bodyHash (Json.arr #[modulesJson modules, toJson entry, toJson fallback])
    if let some d := (← checkMemo.get)[key]? then return d
    let d := checkDiagnosticsCold modules entry fallback
    checkMemo.modify fun m => boundedInsert m Limits.maxCompiledPackets key d
    return d

/-- `checkDiagnosticsCold`, once per process for the same modules, entry and fallback. -/
@[implemented_by checkDiagnosticsImpl]
def checkDiagnostics (modules : List (String × String)) (entry fallback : String) : List String × Bool :=
  checkDiagnosticsCold modules entry fallback

/-- Dry-run compile of `source` as an entry module over the library: the diagnostics as
    `"<module>:<line>: <stage>: <message>"`, none when it is clean. Nothing is installed. -/
def checkSource (w : World) (source : String) : List String × Bool :=
  if source.utf8ByteSize > Limits.maxPackageBytes then
    ([s!"Checked:0: package-request: package source exceeds maxPackageBytes ({Limits.maxPackageBytes} bytes)"], false)
  else
    -- The front end elaborates every declaration of every module whatever entry is selected,
    -- so the entry only has to exist: `initial` when declared, else the first `def`, else a
    -- definition appended after the source (which moves no line of it).
    let defs := (source.splitOn "\n").filterMap fun line =>
      (line.dropPrefix? "def ").map fun rest => (rest.toString.takeWhile fun c => c.isAlphanum || c == '_').toString
    let (checked, entry) :=
      if defs.contains "initial" then (source, "initial")
      else match defs.find? (!·.isEmpty) with
        | some name => (source, name)
        | none => (source ++ "\ndef checkedEntry() -> Nat:\n  0n\n", "checkedEntry")
    let modules := (match w.library with
      | some lib => libraryClosure lib [checked]
      | none => []) ++ [("Checked", checked)]
    checkDiagnostics modules entry "Checked"

/-- A dry-run compile of `modules` (dependency order, library modules included) for `entry`:
    `{status: "checked", artifact}`, or `{status: "refused", diagnostic}` with the kernel's stage,
    message, module, span and hint (`Package.localize`). `lawful` accepts a package that declares
    laws (a world's objects do); the stateless profile refuses them, as `check-package` always has. -/
def checkModules (modules : List (String × String)) (entry : String) (limits : Json) (lawful : Bool) : Json :=
  let request := Json.mkObj [("entry", toJson entry), ("limits", limits), ("modules", modulesJson modules)]
  let refused := fun (d : Package.Diagnostic) => Json.mkObj [("status", toJson "refused"), ("diagnostic", d.json)]
  match Package.compileStructured request with
  | .ok (artifact, _, laws) =>
    if !lawful && !laws.isEmpty then
      refused (Package.requestRefusal "package laws require a host law adapter; this pure profile refuses them")
    else Json.mkObj [("status", toJson "checked"), ("artifact", artifact)]
  | .error d => refused (Package.localize modules limits d)

/-- A request's own modules: `modules`, or one `source` as the module `Package`. -/
def requestModules (j : Json) : Except String (List (String × String)) := do
  match j.getObjVal? "modules" with
  | .ok m => parseModules m
  | .error _ => return [("Package", ← j.getObjValAs? String "source")]

/-- `world-check {principal, modules | source, entry, limits?}`: compile the modules over the
    world's sealed library (the modules they import, as `overLibrary` resolves them; a world
    without a library compiles them alone), journalling nothing. A read: any principal may ask,
    "" anonymously, since the library is the world's public code. A package that declares laws
    compiles, as it would at `world-create`. The answer is `check-package`'s plus `library`. -/
def worldCheck (w : World) (j : Json) : Except String Json := do
  discard <| readerOf j
  let entry ← j.getObjValAs? String "entry"
  let own ← requestModules j
  let modules ← match w.library with
    | some lib => overLibrary lib own
    | none => pure own
  let answer := checkModules modules entry (Package.getLimits j) true
  return match w.library with
    | some lib => answer.setObjVal! "library" (toJson lib.pin)
    | none => answer

/-- The metarule's refusal, naming the proposer it was checked against and the clause that
    refused (a law must admit an amendment by its own proposer). -/
def amendmentRefusal (proposer clause : String) : String :=
  s!"law does not admit an amendment by its proposer {proposer}: {clause}"

def isAmendmentRefusal (message : String) : Bool :=
  message.startsWith "law does not admit an amendment by its proposer "

/-- The rule against a self-sealing law: a law is only accepted if it admits an
    amendment (the state unchanged) by the principal who proposes it. None when it does,
    else the refusal naming that principal and the clause (`name: expression`) that refused. -/
def amendable (law : Law) (principal caller : String) (height turn : Nat) (pin : String) (state : Data)
    (clock : Nat := 0) (id : String := "") (cite : Law.Facts → Law.Facts := fun f => f) : Option String :=
  (Law.refusedBy law (cite { subject := principal, caller, height, turn, pin, kind := 2, clock, object := id }) (some state) state).map fun name =>
    amendmentRefusal principal (((law.lookup name).map fun e => s!"{name}: {e.render}").getD name)

def replaceSource (inputs : Json) (source : String) : Except String Json := do
  match inputs.getObjVal? "modules" with
  | .ok (.arr modules) =>
    let some last := modules.back? | throw "package has no modules"
    let name ← last.getObjValAs? String "name"
    return inputs.setObjVal! "modules" (.arr (modules.pop.push (Json.mkObj [("name", toJson name), ("source", toJson source)])))
  | _ => return inputs.setObjVal! "source" (toJson source)

/-! ## Extension

`reprogram {mode: extend}` (Plan `extend`) appends the offered source as a new module, a layer,
over the object's current modules. The host writes `layer over ./<entry>.obend` as the layer's
first line (in place of the author's own `layer over` line, if any), which imports the module below as `Super` and tells the
kernel the modules are a layer stack: every method of the stack is resolved with late binding (a
method below that calls an overridden one reaches the override) and the artifact's method table
lists the whole stack, top first. `inputs.layers` counts the layers. -/

def layersOf (inputs : Json) : Nat := (inputs.getObjValAs? Nat "layers").toOption.getD 0

/-- The line that makes a module a layer over the module below. -/
def layerLine (below : String) : String := s!"layer over ./{below}.obend"

/-- The inputs with `source` as one more layer over the current entry module. -/
def extendInputs (inputs : Json) (source : String) : Except String Json := do
  let modules ← match inputs.getObjVal? "modules" with
    | .ok (.arr ms) => pure ms
    | _ => pure #[Json.mkObj [("name", toJson "Main"), ("source", toJson (← inputs.getObjValAs? String "source"))]]
  let some top := modules.back? | throw "package has no modules"
  let below ← top.getObjValAs? String "name"
  let n := layersOf inputs + 1
  let name := s!"Layer{n}"
  if modules.any fun m => (m.getObjValAs? String "name").toOption == some name then
    throw s!"the package already has a module named {name}"
  let line := layerLine below
  -- A layer goes over what the object runs now, whatever module its own first line names: a body
  -- written over RECORD is laid over a bell's body when it is the bell's kind's kind's.
  let withSuper := match source.splitOn "\n" with
    | first :: rest => if first.trimAscii.toString.startsWith "layer over " then "\n".intercalate (line :: rest) else line ++ "\n" ++ source
    | [] => line
  let fields := (inputs.getObj?.toOption.map (·.toList) |>.getD []).filter fun (k, _) => k != "source" && k != "modules" && k != "layers"
  return Json.mkObj ([("modules", .arr (modules.push (Json.mkObj [("name", toJson name), ("source", toJson withSuper)]))),
    ("layers", toJson n)] ++ fields)

/-- Compile inputs checked: their whole source closure (the library modules the pin names, the base
    package and every layer over it, `resolveInputs`) compiled for `initial`, as `checkSource` answers. -/
def checkInputs (w : World) (inputs : Json) : List String × Bool :=
  match resolveInputs w inputs >>= fun j => j.getObjVal? "modules" >>= parseModules with
  | .ok modules => checkDiagnostics modules "initial" ((modules.getLast?.map (·.1)).getD "Main")
  | .error e => ([s!"Main:0: package-request: {e}"], false)

/-- `inputs` with each of `layers` laid over them in order, as `extend` lays one (`extendInputs`),
    each within `maxPackageBytes`. -/
def layeredInputs (inputs : Json) (layers : List String) : Except String Json :=
  layers.foldlM (init := inputs) fun inputs layer =>
    if layer.utf8ByteSize > Limits.maxPackageBytes then
      throw s!"package source exceeds maxPackageBytes ({Limits.maxPackageBytes} bytes)"
    else extendInputs inputs layer

/-- What an object would run with `layers` laid over it, checked (`checkInputs`); `[]` is what it runs.
    A layer alone does not compile: its `layer over` names a module below it. -/
def checkObject (w : World) (o : Object) (layers : List String := []) : List String × Bool :=
  match layeredInputs o.inputs layers with
  | .ok inputs => checkInputs w inputs
  | .error e => ([s!"Main:0: package-request: {e}"], false)

/-- The readings an artifact's `laws` table gives (`[{name, reading}]`), the empty ones left out. -/
def artifactReadings (artifact : Json) : List (String × String) :=
  (((artifact.getObjVal? "laws").toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap fun l =>
    match l.getObjValAs? String "name", l.getObjValAs? String "reading" with
    | .ok n, .ok r => if r.isEmpty then none else some (n, r)
    | _, _ => none

/-- The method table and the Bend-law shape an artifact records. -/
def artifactShape (artifact : Json) : Json × Bool × Bool :=
  let law := (artifact.getObjVal? "law").toOption.getD Json.null
  ((artifact.getObjVal? "methods").toOption.getD (Json.arr #[]),
   (law.getObjValAs? Bool "present").toOption.getD false, (law.getObjValAs? Bool "reads").toOption.getD false)

/-- The sources an object's compile inputs carry. -/
def inputSources (inputs : Json) : List String :=
  let modules := match inputs.getObjVal? "modules" with
    | .ok (.arr ms) => ms.toList.filterMap fun m => (m.getObjValAs? String "source").toOption
    | _ => []
  modules ++ ((inputs.getObjValAs? String "source").toOption.map ([·])).getD []

/-- The fields of a record type, through the packet's bounds; none for any other type. -/
partial def recordFieldTypes (bounds : DataBounds) (fuel : Nat) : Delvetalk.Theory.ObjectiveBendTypes.Ty → Option (List (String × Delvetalk.Theory.ObjectiveBendTypes.Ty))
  | .variable i => if fuel == 0 then none else (bounds.lookup i).bind (recordFieldTypes bounds (fuel - 1))
  | .field n m tail => ((n, m) :: ·) <$> recordFieldTypes bounds fuel tail
  | .emptyRow => some []
  | _ => none

/-- The first of `fixed` whose value in `after` is not its value in `before` (by canonical bytes; a
    relation's by its rows' CIDs). -/
def movedFixed (fixed : List String) (before after : Delvetalk.Turn.StateCells) : Option String :=
  fixed.find? fun f => match before.relation? f, after.relation? f with
    | some a, some b => a.rows.map (·.cid) != b.rows.map (·.cid)
    | none, none => ((Law.rawField f before.scalar).map Law.canon) != ((Law.rawField f after.scalar).map Law.canon)
    | _, _ => ((Law.rawField f before.state).map Law.canon) != ((Law.rawField f after.state).map Law.canon)

/-- The State fields an artifact lists as `fixed` (none when absent). -/
def fixedOf (artifact : Json) : List String :=
  ((artifact.getObjValAs? (List String) "fixed").toOption).getD []

/-- The relations an artifact lists (`relations [{field, key, limit, retain?}]`, the value of the
    entry module's `relations()`, which the kernel evaluates once per prepared closure); `none` when
    the entry module declares none. An empty key or a retention other than `dropOldest` refuses. -/
def declsOfArtifact (artifact : Json) : Except String (Option (List RelDecl)) := do
  let some raw := (artifact.getObjVal? "relations").toOption | return none
  let items ← raw.getArr?
  some <$> items.toList.mapM fun d => do
    let field ← d.getObjValAs? String "field"
    let key ← d.getObjValAs? (List String) "key"
    if key.isEmpty then throw s!"relation {field} declares an empty key"
    let limit := (d.getObjValAs? Nat "limit").toOption.getD 0
    match (d.getObjValAs? String "retain").toOption with
    | some r => unless r.isEmpty || r == "dropOldest" do throw s!"relation {field} retains by {r}; only dropOldest is known"
    | none => pure ()
    return ({ field, key, limit } : RelDecl)

/-- A pure definition of a held entry run on data arguments under `ticks`: its value, or the
    machine's refusal (`budget` when the ticks ran out), and the ticks it used. -/
def runPure (entry : Delvetalk.CheckedEntry) (arguments : List Data) (ticks : Nat) :
    Except String Data × Nat :=
  match Package.executeDataEntry entry arguments.toArray (Json.mkObj [("ticks", toJson (toString ticks))]) with
  | .ok (.finished value _ _ usage) => (.ok value, usage.ticksUsed + usage.conversionNodes)
  | .ok (.refused failure usage) =>
    (.error (if (failure.splitOn "tick").length > 1 then "budget" else failure), usage.ticksUsed + usage.conversionNodes)
  | .error e => (.error e, 0)

/-- The names a package exposes without declaring them: the protocol every card and law speaks
    (HOST-HANDOFF 5.62). Every other definition whose first parameter is the State is a helper unless
    `forms()`, `methods()` or `views()` names it. -/
def conventionalMethods : List String :=
  ["receive", "render", "forms", "lenses", "set", "publishPage", "page", "relations", "methods",
   "law", "lawReads", "views", "initial"]

/-- The conventional definitions an artifact says its entry module declares, derived ones included
    (`declares: [names]`, the kernel's `declaredNames`): a derived `forms()` counts. -/
def declaresOf (artifact : Json) : List String :=
  ((artifact.getObjValAs? (List String) "declares").toOption).getD []

/-- Does an object's entry module declare `name` (its artifact's `declares`)? -/
def Object.declaresDef (o : Object) (name : String) : Bool := o.declares.contains name

/-- The labels of a `List<String>` value. -/
partial def labels (acc : List String) : Data → Option (List String)
  | .variant "nil" _ => some acc.reverse
  | .variant "cons" (.record f) => match f.lookup "head", f.lookup "tail" with
    | some (.label s), some tail => labels (s :: acc) tail
    | _, _ => none
  | _ => none

/-- The actions of the forms a `forms()` value lists (`Lists.List<Form.Form>`). -/
def formActions (value : Data) : List String :=
  ((listOf value).getD []).filterMap fun
    | .record fs => match fs.lookup "action" with
      | some (.label a) => some a
      | _ => none
    | _ => none

/-- The methods a package declares public (HOST-HANDOFF 5.62), beside the conventional names: the
    actions of its `forms()`, the names its `methods()` returns and those its `views()` returns, each
    read only when its entry module declares it. A `forms()` or `views()` that does not evaluate names nothing; a
    `methods()` that is not a `List<String>` refuses the package (clause `methods`). `compile` gives
    a zero-argument definition's held entry. -/
def publicMethods (compile : String → Except String Delvetalk.CheckedEntry) (declares : List String) :
    Except String (List String) := do
  let read := fun (name : String) =>
    if !declares.contains name then none else
    match compile name with
    | .ok entry => some (runPure entry [] Delvetalk.Bounds.lawTicks).1
    | .error e => some (.error e)
  let forms := match read "forms" with
    | some (.ok v) => formActions v
    | _ => []
  let views := match read "views" with
    | some (.ok v) => (labels [] v).getD []
    | _ => []
  let declared ← match read "methods" with
    | none => pure []
    | some (.ok v) => match labels [] v with
      | some names => pure names
      | none => throw "methods: methods() must return a List<String> of method names"
    | some (.error e) => throw s!"methods: methods() did not evaluate: {e}"
  return (forms ++ declared ++ views).eraseDups

/-- A method table with its rows marked: a row `exposed` (the declared names) does not name is
    `protocol: true` when its name is conventional (public, but no action a card offers), else
    `helper: true` (not public). -/
def markHelpers (methods : Json) (exposed : List String) : Json :=
  Json.arr (((methods.getArr?.toOption).getD #[]).map fun m =>
    match (m.getObjValAs? String "name").toOption with
    | some name =>
      if exposed.contains name then m
      -- `~name` in `methods()`: public, but offered to nobody (no usage, form, action or spell),
      -- as a method a bridge or another object calls.
      else if exposed.contains ("~" ++ name) then m.setObjVal! "unoffered" (toJson true)
      else if conventionalMethods.contains name then m.setObjVal! "protocol" (toJson true)
      else m.setObjVal! "helper" (toJson true)
    | none => m)

/-- The names a marked method table declares public (rows neither helper nor protocol). -/
def declaredRows (methods : Json) : List String :=
  ((methods.getArr?.toOption).getD #[]).toList.filterMap fun m =>
    if (m.getObjValAs? Bool "helper").toOption == some true || (m.getObjValAs? Bool "protocol").toOption == some true then none
    else if (m.getObjValAs? Bool "unoffered").toOption == some true then ("~" ++ ·) <$> (m.getObjValAs? String "name").toOption
    else (m.getObjValAs? String "name").toOption

/-- Is a method table row a helper (not callable from outside the object)? -/
def isHelperRow (m : Json) : Bool := (m.getObjValAs? Bool "helper").toOption == some true

/-- Is a method table row an action a card offers as a form: declared public, or `receive`? -/
def isActionRow (m : Json) : Bool :=
  !isHelperRow m && (m.getObjValAs? Bool "unoffered").toOption != some true && ((m.getObjValAs? Bool "protocol").toOption != some true ||
    (m.getObjValAs? String "name").toOption == some "receive")

/-- The rows of a method table a turn, a call, a send or a delivery may name. -/
def publicRows (methods : Json) : Json :=
  Json.arr (((methods.getArr?.toOption).getD #[]).filter (!isHelperRow ·))

/-- The public rows a reader is shown (`world-inspect`, `world-objects {methods}`): not the
    unoffered ones (`~name`), which stay callable. -/
def offeredRows (methods : Json) : Json :=
  Json.arr (((methods.getArr?.toOption).getD #[]).filter fun m =>
    !isHelperRow m && (m.getObjValAs? Bool "unoffered").toOption != some true)

/-- Does `o` offer `method` to a turn, a call, a send or a delivery: a row of its method table not
    marked a helper? A definition that is no method (the State not first, or more than one input)
    is offered to nobody either. -/
def Object.offers (o : Object) (method : String) : Bool :=
  ((o.methods.getArr?.toOption).getD #[]).any fun m =>
    (m.getObjValAs? String "name").toOption == some method && !isHelperRow m

/-- The cases of a sum type (through the bounds): its labels and payload types. -/
partial def variantCases (bounds : DataBounds) (fuel : Nat) : Delvetalk.Theory.ObjectiveBendTypes.Ty → Option (List (String × Delvetalk.Theory.ObjectiveBendTypes.Ty))
  | .variable i => if fuel == 0 then none else (bounds.lookup i).bind (variantCases bounds (fuel - 1))
  | .variant r => recordFieldTypes bounds (bounds.length + 1) r
  | _ => none

/-- A value from outside with its text words read as cases (HOST-HANDOFF 5.52): where `ty` has a closed
    sum whose every case has an empty payload and the value is a text, the text is the case of that
    name; through records, list items and the payloads of the sums the value names. A text naming no
    case is `(path, word, cases)`, `path` the field path (`bed.colours[1]`, "" for the whole value). Any other value
    is left as it is, for the conformance check to judge. -/
partial def wordsAsCases (bounds : DataBounds) (ty : Delvetalk.Theory.ObjectiveBendTypes.Ty) (d : Data)
    (path : String := "") : Except (String × String × List String) Data :=
  let fuel := bounds.length + 1
  match d with
  | .label word =>
    match variantCases bounds fuel ty with
    | some cases@(_ :: _) =>
      if !cases.all fun (_, p) => match recordFieldTypes bounds fuel p with | some [] => true | _ => false then pure d
      else if cases.any (·.1 == word) then pure (.variant word (.record []))
      else throw (path, word, cases.map (·.1))
    | _ => pure d
  | .record fs =>
    match recordFieldTypes bounds fuel ty with
    | some tys => .record <$> fs.mapM fun (n, v) => match tys.lookup n with
      | some t => (n, ·) <$> wordsAsCases bounds t v (if path.isEmpty then n else s!"{path}.{n}")
      | none => pure (n, v)
    | none => pure d
  | .variant l p =>
    let item := do
      let cons ← (variantCases bounds fuel ty).bind (·.lookup "cons")
      (← recordFieldTypes bounds fuel cons).lookup "head"
    match Delvetalk.Compiler.ObjectiveBendDataWire.listItems? d, item with
    | some items, some t =>
      Delvetalk.Compiler.ObjectiveBendDataWire.listData <$> (items.zipIdx.mapM fun (v, i) => wordsAsCases bounds t v s!"{path}[{i}]")
    | _, _ =>
      match (variantCases bounds fuel ty).bind (·.lookup l) with
      | some t => .variant l <$> wordsAsCases bounds t p path
      | none => pure d
  | _ => pure d

/-- The row type of a relation field's type through the packet's bounds: a genuine `Relation<T>`, the
    closed one-case sum `rows {items: List<T>}` (`Ty.relationItem`), which types a relation exactly when
    it types each row (`Theory.ObjectiveBendCellConformance.relation_typed_iff`): what lets a write be
    checked by the rows it changes. -/
def relationItemOf (bounds : DataBounds) : Nat → Delvetalk.Theory.ObjectiveBendTypes.Ty → Option Delvetalk.Theory.ObjectiveBendTypes.Ty
  | fuel + 1, .variable i => (bounds.lookup i).bind (relationItemOf bounds fuel)
  | _, ty => ty.relationItem bounds

/-- The columns of a relation field's rows, read from the state type: `rows {items: List<T>}` with `T` a
    record, the field a genuine `Relation<T>` (`relationItemOf`). -/
def rowColumns (bounds : DataBounds) (stateType : Delvetalk.Theory.ObjectiveBendTypes.Ty) (field : String) : Option (List String) := do
  let fuel := bounds.length + 1
  let fieldTy ← (← recordFieldTypes bounds fuel stateType).lookup field
  discard <| relationItemOf bounds fuel fieldTy
  let payload ← (← variantCases bounds fuel fieldTy).lookup "rows"
  let items ← (← recordFieldTypes bounds fuel payload).lookup "items"
  let cons ← (← variantCases bounds fuel items).lookup "cons"
  let head ← (← recordFieldTypes bounds fuel cons).lookup "head"
  return (← recordFieldTypes bounds fuel head).map (·.1)

/-- A package's relations against its state type: each a relation field whose rows have every key
    column; refused by name (`key: …`) otherwise. -/
def checkRelations (decls : List RelDecl) (bounds : DataBounds) (stateType : Delvetalk.Theory.ObjectiveBendTypes.Ty) : Except String Unit := do
  for d in decls do
    let some cols := rowColumns bounds stateType d.field
      | throw s!"key: {d.field} is not a Relation<T> field of a record T"
    for k in d.key do
      unless cols.contains k do throw s!"key: relation {d.field} names column {k}, which its rows lack"

def buildKey (inputs : Json) : String := Journal.bodyHash inputs

/-- The on-disk form of a compiled package: its artifact (with the packet), its laws as text, its
    relations and the methods it declares public. -/
def builtJson (key : String) (b : Built) : Json :=
  Json.mkObj [("key", toJson key), ("artifact", b.artifact), ("laws", toJson (renderLaw b.laws)),
    ("lines", toJson ("\n".intercalate (b.lines.map (·.render)))),
    ("relations", Json.arr (b.relations.toArray.map fun d =>
      Json.mkObj [("field", toJson d.field), ("key", toJson d.key), ("limit", toJson d.limit)])),
    ("exposed", toJson b.exposed), ("lawShape", toJson [b.lawShape.1, b.lawShape.2])]

/-- A compiled package from its on-disk form; the packet is decoded and re-checked by Mini. -/
def builtOf (j : Json) : Option Built := do
  let artifact ← (j.getObjVal? "artifact").toOption
  let packet ← (artifact.getObjVal? "packet").toOption
  let entry ← (Delvetalk.CheckedEntry.ofPacket packet).toOption
  let decoded ← (Delvetalk.Theory.ObjectiveBendTyping.decodePacket packet).toOption
  let laws ← match (j.getObjValAs? String "laws").toOption with
    | some "" => some []
    | some text => (parseLawText text).toOption
    | none => none
  let relations ← ((j.getObjVal? "relations").toOption.bind (·.getArr?.toOption)).map fun ds => ds.toList.filterMap fun d =>
    match d.getObjValAs? String "field", d.getObjValAs? (List String) "key", d.getObjValAs? Nat "limit" with
    | .ok field, .ok key, .ok limit => some ({ field, key, limit } : RelDecl)
    | _, _, _ => none
  let lines ← match (j.getObjValAs? String "lines").toOption with
    | some text => (parseClauses text).toOption
    | none => none
  let exposed ← (j.getObjValAs? (List String) "exposed").toOption
  let [predicate, reads] ← (j.getObjValAs? (List Bool) "lawShape").toOption | none
  return { artifact, ty := entry.type, laws, assumptions := decoded.source.assumptions, relations, exposed,
           lawShape := (predicate, reads), lines }

/-- The inputs of the code below a layered package's top layer: that module gone, `layers` one less. -/
def lowerInputs (inputs : Json) : Option Json := do
  let n := layersOf inputs
  if n == 0 then none
  let ms ← (inputs.getObjVal? "modules").toOption.bind (·.getArr?.toOption)
  let fields := (inputs.getObj?.toOption.map (·.toList) |>.getD []).filter fun (k, _) => k != "modules" && k != "layers"
  return Json.mkObj ([("modules", Json.arr ms.pop)] ++ (if n > 1 then [("layers", toJson (n - 1))] else []) ++ fields)

/-- This process's prepared closures by `inputsKeyOf` (a content address: the inputs name their library
    by pin), whichever world prepared them: preparing parses and expands the whole closure, library
    included, and a caller that cannot keep the world it was handed (a pure read) would prepare it again. -/
initialize requestMemo : IO.Ref (Std.HashMap String Package.PreparedRequest) ← IO.mkRef {}

unsafe def requestReadImpl (key : String) : Option Package.PreparedRequest :=
  unsafeBaseIO do return (← requestMemo.get)[key]?

/-- The process's prepared closure of `key`; `none` in the model (prepare as if cold). -/
@[implemented_by requestReadImpl]
def requestRead (_key : String) : Option Package.PreparedRequest := none

unsafe def requestKeepImpl (key : String) (r : Package.PreparedRequest) : Package.PreparedRequest :=
  unsafeBaseIO do
    requestMemo.modify fun m => boundedInsert m Limits.maxBuilds key r
    return r

/-- `r`, kept as the process's prepared closure of `key`. -/
@[implemented_by requestKeepImpl]
def requestKeep (_key : String) (r : Package.PreparedRequest) : Package.PreparedRequest := r

/-- This process's compiled packages by `buildKey` (a content address), whichever world built them. -/
initialize buildMemo : IO.Ref (Std.HashMap String Built) ← IO.mkRef {}

unsafe def buildReadImpl (key : String) : Option Built :=
  unsafeBaseIO do return (← buildMemo.get)[key]?

/-- The process's compiled package of `key`; `none` in the model (compile as if cold). -/
@[implemented_by buildReadImpl]
def buildRead (_key : String) : Option Built := none

unsafe def buildKeepImpl (key : String) (b : Built) : Built :=
  unsafeBaseIO do
    buildMemo.modify fun m => boundedInsert m Limits.maxBuilds key b
    return b

/-- `b`, kept as the process's compiled package of `key`. -/
@[implemented_by buildKeepImpl]
def buildKeep (_key : String) (b : Built) : Built := b

mutual
/-- A package's compiled form. A layered package is a stack (HOST-HANDOFF 5.3): a layer keeps what the
    code below it declared public and may declare more, keeps the relations below when it declares
    none, and keeps the law shape below when it declares no Bend law; so whether an object was made
    layered, extended later or rebuilt by replay, its stack has one shape. -/
partial def compileObject (w : World) (inputs : Json) : Except String Built := do
  let key := buildKey inputs
  if let some b := w.builds[key]? <|> buildRead key then return b
  if let some b := ((DiskCache.read "build" key).bind builtOf).map DiskCache.hit then return buildKeep key b
  return buildKeep key (← compileObjectCold w inputs)

/-- `compileObject` with no cache to answer it. -/
partial def compileObjectCold (w : World) (inputs : Json) : Except String Built := do
  -- One prepared closure for the entry and, when the entry module declares them, `relations()`; the
  -- process's, so the object's first definition (`compileEntryIn`: its `render`, `receive`, `forms`) is
  -- lowered from it, not prepared again.
  -- Only when this world holds the library the inputs name: an unknown pin is refused as before.
  let resolved ← resolveInputs w inputs
  let own := inputsKeyOf inputs
  let request ← match requestRead own with
    | some r => pure r
    | none => pure (requestKeep own (← (Package.prepareRequest resolved).mapError Package.Diagnostic.render))
  let c ← (Package.compileEntryFrom request (← inputs.getObjValAs? String "entry")).mapError fun d =>
    (Package.withHint resolved d).render
  let (artifact, ty, laws) := (c.artifact, c.entry.type, c.laws)
  let packet ← artifact.getObjVal? "packet"
  let decoded ← Delvetalk.Theory.ObjectiveBendTyping.decodePacket packet
  unless stateTypeOk decoded.source.assumptions ty do
    throw "package entry type must be a closed record of first-order data (a zero-argument definition returning the state record)"
  let declared ← (declsOfArtifact artifact).mapError (s!"key: " ++ ·)
  let exposed ← publicMethods (fun name =>
    ((Package.compileEntryCore request name).mapError Package.Diagnostic.render).map (·.entry)) (declaresOf artifact)
  let (_, predicate, reads) := artifactShape artifact
  let below ← match lowerInputs inputs with
    | some lower => some <$> compileObject w lower
    | none => pure none
  return { artifact, ty, laws, assumptions := decoded.source.assumptions,
           lines := c.clauses.filter fun x => Law.isRule x || Law.isWant x,
           relations := declared.getD ((below.map (·.relations)).getD []),
           exposed := exposed ++ ((below.map (·.exposed)).getD []).filter (!exposed.contains ·),
           lawShape := if predicate then (predicate, reads) else ((below.map (·.lawShape)).getD (false, false)) }
end

/-- The method table and law shape an object of `b` runs with (`Object.methods`, `predicate`, `predicateReads`). -/
def Built.shape (b : Built) : Json × Bool × Bool :=
  (markHelpers (artifactShape b.artifact).1 b.exposed, b.lawShape)

/-- A package's migration `name` over `inputs`, compiled: a function from a state its argument type
    `reads` (a reprogram: the object's state type; a carry: the state as it was) to `ty`, the state type
    the same inputs compile. Failures are `(clause, message)`; `wrong` says a type that does not fit. -/
def compileMigration (w : World) (inputs : Json) (name : String) (ty : Delvetalk.Theory.ObjectiveBendTypes.Ty)
    (reads : Delvetalk.Theory.ObjectiveBendTypes.Ty → DataBounds → Bool)
    (wrong : String) : Except (String × String) Compiled := do
  unless Delvetalk.Compiler.ObjectiveBendParse.isIdent name.toList do throw ("migration", "invalid migration name")
  let resolved ← (resolveInputs w (inputs.setObjVal! "entry" (toJson name))).mapError (("compile", ·))
  -- A migration the package does not define is said by name, not by the compiler's entry search.
  let (art, mty, _) ← (Package.compileKeepingLaws resolved).mapError fun e =>
    if (e.splitOn "missing selected entry").length > 1 then
      ("migration", s!"the package defines no {name}; a migration is def {name}(old: OldState) -> State")
    else ("migration", e)
  let packet ← (art.getObjVal? "packet").mapError (("migration", ·))
  let md ← (Delvetalk.Theory.ObjectiveBendTyping.decodePacket packet).mapError (("migration", ·))
  match mty with
  | .arrow _ _ dom cod =>
    unless reads dom md.source.assumptions.bounds && cod == ty do throw ("migration", wrong)
  | _ => throw ("migration", "the migration must be a function OldState -> NewState")
  return ⟨packet, mty, md.source.assumptions.bounds, md.source.assumptions.rigid,
    (Delvetalk.CheckedEntry.ofPacket packet).toOption, none⟩

/-- A compiled migration run over `state`: the state it converts it to, or why not. -/
def runMigration (m : Compiled) (state : Data) : Except String Data :=
  let run := match m.entry with
    | some e => Package.executeDataEntry e #[state] (Json.mkObj [])
    | none => Package.executeDataValues m.packet #[state] (Json.mkObj [])
  match run with
  | .ok (.finished value _ _ _) => .ok value
  | .ok (.refused failure _) => .error s!"the migration was refused: {failure}"
  | .error e => .error e

/-- Compile a replacement for an object's entry module (its imports stay as
    sealed at creation). Failures are `(clause, message)`. -/
def prepareProgram (w : World) (o : Object) (source migration : String) (extend : Bool := false) :
    Except (String × String) Program := do
  if source.utf8ByteSize > Limits.maxPackageBytes then
    throw ("packageBytes", s!"package source exceeds maxPackageBytes ({Limits.maxPackageBytes} bytes)")
  let replaced ← (if extend then extendInputs o.inputs source else replaceSource o.inputs source).mapError (("compile", ·))
  -- A reprogram is compiled against the library the world has now.
  let inputs ← (match w.library with
    | some lib => if (replaced.getObjVal? "library").toOption.isSome then
        pure (replaced.setObjVal! "library" (toJson lib.pin)) else pure replaced
    | none => pure replaced)
  -- The new code compiled as any package is (`compileObject`: a stack keeps the shape below it).
  let built ← (compileObject w (inputs.setObjVal! "entry" (toJson "initial"))).mapError fun e =>
    if e.startsWith "methods: " then ("methods", (e.drop 9).toString)
    else if e.startsWith "key: " then ("key", (e.drop 5).toString) else ("compile", e)
  let (artifact, ty, assumptions) := (built.artifact, built.ty, built.assumptions)
  let packet ← (artifact.getObjValAs? String "packetSha256").mapError (("compile", ·))
  -- The pin is the sealed source closure's CID, an extension's too: its modules are the code it
  -- extends, the layer and the library it compiled against now (docs 2: the same layer under two
  -- libraries is two closures).
  let pin ← (artifact.getObjValAs? String "sourcesSha256").mapError (("compile", ·))
  let same := (← (canonicalTy assumptions.bounds ty).mapError (("stateType", ·))) ==
    (← (canonicalTy o.bounds o.stateType).mapError (("stateType", ·)))
  let migrated : Option Compiled ← if migration.isEmpty then
      if same then pure none else throw ("stateType", "the state type differs and no migration names a conversion")
    else some <$> (compileMigration w inputs migration ty (fun dom _ => dom == o.stateType)
      "the migration must have type OldState -> NewState")
  -- A stack's artifact lists every layer's methods (the kernel's `stackMethodTable`); its shape is
  -- the stack's (`Built.shape`).
  let (methods, predicate, predicateReads) := built.shape
  let relations := built.relations
  (checkRelations relations assumptions.bounds ty).mapError (("key", ·))
  return { inputs, pin, stateType := ty, bounds := assumptions.bounds, migration := migrated,
           methods, predicate, predicateReads, packet, relations, fixed := fixedOf artifact,
           declares := declaresOf artifact }

/-- A prepared reprogram's key: the object's inputs, the source, the migration, the mode, and the
    library it compiles against now (a reprogram takes the world's current library). -/
def programKey (w : World) (o : Object) (source migration : String) (extend : Bool := false) : String :=
  o.inputsKey ++ "/" ++ Journal.bodyHash source ++ "/" ++ migration ++ (if extend then "/extend" else "") ++
    "/" ++ ((w.library.map (·.pin)).getD "")

def programFor (w : World) (o : Object) (source migration : String) (extend : Bool := false) : Except (String × String) Program :=
  match w.programs[programKey w o source migration extend]? with
  | some p => pure p
  | none => prepareProgram w o source migration extend

def cacheProgram (w : World) (o : Object) (source migration : String) (p : Program) (extend : Bool := false) : World :=
  if w.programs.size < Limits.maxPreparedPrograms then
    { w with programs := w.programs.insert (programKey w o source migration extend) p }
  else w

/-! ## Sources by CID

The journal carries each source module once: the first entry whose compile inputs need a
source carries it in its `sources [{cid, source}]` field, and compile inputs in every entry
name it as `{name, cid}` (or `sourceCid`). Objects keep the full inputs in memory. -/

def sourceCid (source : String) : String := Journal.bodyHash (toJson source)

/-- Compile inputs as journaled: every source replaced by its CID. -/
def compactInputs (inputs : Json) : Json :=
  let inputs := match inputs.getObjVal? "modules" with
    | .ok (.arr ms) => inputs.setObjVal! "modules" (.arr (ms.map fun (m : Json) =>
        match m.getObjValAs? String "source" with
        | .ok src => Json.mkObj [("name", (m.getObjVal? "name").toOption.getD Json.null), ("cid", toJson (sourceCid src))]
        | .error _ => m))
    | _ => inputs
  match inputs.getObjValAs? String "source", inputs.getObj? with
  | .ok src, .ok fields =>
    Json.mkObj ((fields.toList.filter fun (kv : String × Json) => kv.1 != "source") ++ [("sourceCid", toJson (sourceCid src))])
  | _, _ => inputs

/-- The `sources` field an entry needs: each source the world has not recorded, once. -/
def newSources (w : World) (sources : List String) : List (String × Json) :=
  let fresh := (sources.map fun src => (sourceCid src, src)).foldl (fun acc (cid, src) =>
    if w.modules.contains cid || acc.any (·.1 == cid) then acc else acc ++ [(cid, src)]) []
  if fresh.isEmpty then [] else
    [("sources", Json.arr (fresh.toArray.map fun (cid, src) => Json.mkObj [("cid", toJson cid), ("source", toJson src)]))]

/-- The sources an entry carries, checked against their CIDs. -/
def entrySources (entry : Json) : Except String (List (String × String)) := do
  let some raw := (entry.getObjVal? "sources").toOption | return []
  (← raw.getArr?).toList.mapM fun m => do
    let cid ← m.getObjValAs? String "cid"
    let src ← m.getObjValAs? String "source"
    unless sourceCid src == cid do throw "a journaled source is not its CID's"
    return (cid, src)

/-- The blocks an entry carries, checked against their CIDs. -/
def entryBlocks (entry : Json) : Except String (List (String × Array Json)) := do
  let some raw := (entry.getObjVal? "blocks").toOption | return []
  (← raw.getArr?).toList.mapM fun b => do
    let cid ← b.getObjValAs? String "cid"
    let items ← (← b.getObjVal? "items").getArr?
    unless Journal.bodyHash (Json.arr items) == cid do throw "a journaled block is not its CID's"
    return (cid, items)

/-- The checkpoint block `cid`, read from the entry that carries it (`World.blocks`). -/
def blockItems (w : World) (cid : String) : Option (Array Json) := do
  let entry ← w.entries.get? (← w.blocks[cid]?)
  ((entryBlocks entry).toOption.getD []).lookup cid

/-- The source module `cid`, read from the entry that carries it (`World.modules`). -/
def sourceText (w : World) (cid : String) : Option String := do
  let entry ← w.entries.get? (← w.modules[cid]?)
  ((entrySources entry).toOption.getD []).lookup cid

/-! ## Checkpoint blocks

A checkpoint's tokens are mostly the program's own terms, the same in every suspension of a
package. The journal stores them as a tree of content-defined blocks: the token array is cut
where a token's hash says so (so equal runs cut alike in every checkpoint), each block is
named by its CID and journaled once (`blocks [{cid, items}]` on the first entry that needs it),
and the list of block CIDs is cut the same way until at most `treeFanout` names remain
(`tokenTree {depth, roots}`). The checkpoint's digest still covers the whole token array, which
replay and resumption reassemble from the blocks. -/

/-- A cheap, fixed hash of an item (FNV-1a over its compressed JSON) that decides block cuts. -/
def cutHash (item : Json) : Nat :=
  item.compress.toUTF8.foldl (fun h b => ((h ^^^ b.toNat) * 16777619) % 4294967296) 2166136261

/-- Cut items into blocks: after at least `low` items, where the hash of the last four items
    together is 0 mod `every` (a window, so runs of common tokens still vary), never past `high`.
    An item whose compressed form is `big` bytes or more (a long string) is a block of its own,
    cut before and after, so the run around it dedups whatever it holds. `big` 0 turns the rule off. -/
def cutBlocks (items : Array Json) (low high every : Nat) (big : Nat := 0) : Array (Array Json) := Id.run do
  let mut out : Array (Array Json) := #[]
  let mut cur : Array Json := #[]
  let mut window : List Nat := []
  for item in items do
    let text := item.compress
    if big != 0 && text.utf8ByteSize ≥ big then
      if !cur.isEmpty then out := out.push cur
      out := out.push #[item]
      cur := #[]
      window := []
      continue
    cur := cur.push item
    window := (cutHash item :: window).take 4
    let mixed := window.foldl (fun h x => ((h ^^^ x) * 16777619) % 4294967296) 2166136261
    if (cur.size ≥ low && mixed % every == 0) || cur.size ≥ high then
      out := out.push cur
      cur := #[]
  if !cur.isEmpty then out := out.push cur
  return out

def treeFanout : Nat := 16

/-- Leaves of at most 256 tokens; a token of 256 bytes or more is a leaf of its own. -/
def leafLow : Nat := 32
def leafHigh : Nat := 256
def leafEvery : Nat := 64
def leafBig : Nat := 256

/-- The tree of a token array: its depth, its root names, and every block it uses. -/
partial def blockTree (items : Array Json) (depth : Nat := 0)
    (acc : Array (String × Array Json) := #[]) : Nat × Array Json × Array (String × Array Json) :=
  let blocks := if depth == 0 then cutBlocks items leafLow leafHigh leafEvery leafBig
    else cutBlocks items 2 16 4
  let named := blocks.map fun b => (Journal.bodyHash (Json.arr b), b)
  let names := named.map fun (c, _) => toJson c
  if names.size ≤ treeFanout then (depth + 1, names, acc ++ named)
  else blockTree names (depth + 1) (acc ++ named)

/-- The checkpoint fields a suspended entry already says: the binding's object (the activity's),
    principal and intent (the entry's identity). The digest is derived from them and the tokens. -/
def boundFields : List String := ["object", "principal", "intent"]

/-- An entry's `blocks` field: the blocks `used` names that the world does not hold yet, each once. -/
def blocksField (w : World) (used : Array (String × Array Json)) : List (String × Json) :=
  let fresh := used.foldl (fun (acc : Array (String × Array Json)) (c, b) =>
    if w.blocks.contains c || acc.any (·.1 == c) then acc else acc.push (c, b)) #[]
  if fresh.isEmpty then [] else
    [("blocks", Json.arr (fresh.map fun (c, b) => Json.mkObj [("cid", toJson c), ("items", Json.arr b)]))]

/-- A checkpoint as journaled: `tokens` replaced by `tokenTree`, and the blocks the world does
    not hold yet (each once), `extra` ones (an interpretation's) among them. The fields the entry
    already says (`bound`: object, principal, intent) are dropped when they agree, and so is the
    `digest`, which `expandSuspended` derives again. -/
def compactCheckpoint (w : World) (checkpoint : Json) (bound : List (String × String))
    (extra : Array (Array Json) := #[]) : Json × List (String × Json) :=
  match (checkpoint.getObjVal? "tokens").toOption.bind (·.getArr?.toOption) with
  | none => (checkpoint, [])
  | some tokens =>
    let (depth, roots, used) := blockTree tokens
    let said := fun (k : String) (v : Json) => k == "digest" || (bound.lookup k).any (toJson · == v)
    let fields := ((checkpoint.getObj?.toOption.map (·.toList)).getD []).filter fun (k, v) => k != "tokens" && !said k v
    (Json.mkObj (fields ++ [("tokenTree", Json.mkObj [("depth", toJson depth), ("roots", Json.arr roots)])]),
     blocksField w (used ++ extra.map fun b => (Journal.bodyHash (Json.arr b), b)))

/-- The CID a one-item block of `item` is journaled under. -/
def blockCid (item : Json) : String := Journal.bodyHash (Json.arr #[item])

/-- A field this long (compact JSON bytes) or longer is journaled as a block (`blockField`); a
    shorter one costs less inline than its CID. -/
def blockThreshold : Nat := 256

/-- `field` of `j` as a one-item block named by CID (`<field>Block`) when it is at least `least`
    bytes, so a value that recurs (the forms of every reading of one card, the utterance of one post
    read again, a retried argument) is journaled once; the blocks to journal are the second part. -/
def blockField (j : Json) (field : String) (least : Nat := blockThreshold) : Json × Array (Array Json) :=
  match j.getObjVal? field with
  | .ok v =>
    if v.compress.utf8ByteSize < least then (j, #[]) else
    let rest := ((j.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != field)
    (Json.mkObj (rest ++ [(field ++ "Block", toJson (blockCid v))]), #[#[v]])
  | .error _ => (j, #[])

/-- `j` with `field` restored from the world's blocks (`blockField`); none when the block is not
    journaled. -/
def unblockField (w : World) (j : Json) (field : String) : Option Json := do
  let some cid := (j.getObjValAs? String (field ++ "Block")).toOption | return j
  let v ← (blockItems w cid).bind (·[0]?)
  let rest := ((j.getObj?.toOption.map (·.toList)).getD []).filter fun (k, _) => k != field ++ "Block"
  return Json.mkObj (rest ++ [(field, v)])

/-- Data wire JSON with every text of at least `blockThreshold` bytes journaled as a one-item block of
    the string (`{tag: "labelBlock", cid}`): the same block the checkpoint's leaf for that text is, so
    a reply's text is journaled once whether the argument or the machine holds it. -/
partial def hoistLabels (j : Json) : Json × Array (Array Json) :=
  match j with
  | .obj _ =>
    if (j.getObjValAs? String "tag").toOption == some "label" then
      match j.getObjValAs? String "value" with
      | .ok v => if v.utf8ByteSize < blockThreshold then (j, #[]) else
          (Json.mkObj [("tag", toJson "labelBlock"), ("cid", toJson (blockCid (toJson v)))], #[#[toJson v]])
      | .error _ => (j, #[])
    else
      let fields := (j.getObj?.toOption.map (·.toList)).getD []
      let (out, blocks) := fields.foldl (fun (acc : List (String × Json) × Array (Array Json)) (k, v) =>
        let (v', bs) := hoistLabels v; (acc.1 ++ [(k, v')], acc.2 ++ bs)) ([], #[])
      (Json.mkObj out, blocks)
  | .arr items =>
    let (out, blocks) := items.foldl (fun (acc : Array Json × Array (Array Json)) v =>
      let (v', bs) := hoistLabels v; (acc.1.push v', acc.2 ++ bs)) (#[], #[])
    (.arr out, blocks)
  | other => (other, #[])

/-- `hoistLabels` undone from the world's blocks. -/
partial def lowerLabels (w : World) (j : Json) : Except String Json :=
  match j with
  | .obj _ =>
    if (j.getObjValAs? String "tag").toOption == some "labelBlock" then do
      let cid ← j.getObjValAs? String "cid"
      let some item := (blockItems w cid).bind (·[0]?) | throw s!"text block {cid} is not journaled"
      return Json.mkObj [("tag", toJson "label"), ("value", ← item.getStr?)]
    else do
      let fields := (j.getObj?.toOption.map (·.toList)).getD []
      return Json.mkObj (← fields.mapM fun (k, v) => do return (k, ← lowerLabels w v))
  | .arr items => return .arr (← items.mapM (lowerLabels w))
  | other => return other

/-- A suspended activity's `argument`, its long texts restored from the world's blocks (`hoistLabels`;
    an older entry's whole `argumentBlock` too). -/
def activityArgument (w : World) (act : Json) : Except String Json := do
  match unblockField w act "argument" with
  | some a => lowerLabels w (← a.getObjVal? "argument")
  | none => throw "a suspended activity's argument block is not journaled"

/-- An interpretation as journaled: its `offers` (the same forms in every reading of one card) are a
    one-item block (`offersBlock`), and so is a long `utterance` (`utteranceBlock`; the commonplace reads
    one post's text more than once), so a reading costs only what is new in it. The blocks to
    journal with it are the second component. -/
def compactInterpretation (i : Json) (argument : Data) : Json × Array (Array Json) :=
  let (i, offers) := blockField i "offers" 0
  -- A card reading its reply hands the model the reply's own text: then it is not journaled twice.
  let text := match argument with
    | .record fs => match fs.lookup "text" with
      | some (.label t) => some t
      | _ => none
    | _ => none
  if (i.getObjValAs? String "utterance").toOption == text && text.isSome then
    let rest := ((i.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "utterance")
    (Json.mkObj (rest ++ [("utteranceIsText", toJson true)]), offers)
  else
    let (i, utterance) := blockField i "utterance"
    (i, offers ++ utterance)

/-- The interpretation of a suspended entry's `outcome`, with its `offers` and `utterance` restored
    from the world's blocks, or the utterance from the activity's argument's `text`. -/
def expandInterpretation (w : World) (outcome : Json) : Option Json := do
  let i ← (outcome.getObjVal? "interpretation").toOption
  let i ← unblockField w (← unblockField w i "offers") "utterance"
  if (i.getObjValAs? Bool "utteranceIsText").toOption != some true then return i
  let act ← (outcome.getObjVal? "activity").toOption
  let argument ← (activityArgument w act).toOption
  let text ← ((argument.getObjVal? "fields").toOption.bind (·.getArr?.toOption)).bind fun fs =>
    fs.findSome? fun f => if (f.getObjValAs? String "name").toOption == some "text" then
      ((f.getObjVal? "value").toOption.bind (·.getObjValAs? String "value" |>.toOption)) else none
  let rest := ((i.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "utteranceIsText")
  return Json.mkObj (rest ++ [("utterance", toJson text)])

/-- A journaled checkpoint with its token array reassembled from the world's blocks. -/
partial def expandCheckpoint (w : World) (checkpoint : Json) : Except String Json := do
  let some tree := (checkpoint.getObjVal? "tokenTree").toOption | return checkpoint
  let rec expand (depth : Nat) (names : Array Json) : Except String (Array Json) := do
    if depth == 0 then return names
    let mut out : Array Json := #[]
    for n in names do
      let cid ← n.getStr?
      let some items := blockItems w cid | throw s!"checkpoint block {cid} is not journaled"
      out := out ++ items
    expand (depth - 1) out
  let tokens ← expand (← tree.getObjValAs? Nat "depth") (← (← tree.getObjVal? "roots").getArr?)
  let fields := ((checkpoint.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "tokenTree")
  return Json.mkObj (fields ++ [("tokens", Json.arr tokens)])

/-- A suspension the host resumes itself: hob's reading of words that reached a card (`heardTurn`), whose
    settled answer the host runs as the turn. No Bend waits in it, so its activity holds no checkpoint. -/
def hostResumed (entry : Json) : Bool :=
  ((entry.getObjVal? "outcome").toOption.bind (·.getObjVal? "activity" |>.toOption)).any
    fun a => (a.getObjVal? "checkpoint").toOption.isNone

/-- A suspended entry's checkpoint whole: its tokens from the world's blocks (`expandCheckpoint`),
    the binding fields the entry says (`boundFields`) and the digest derived again when the journal
    left them out (`compactCheckpoint`). -/
def expandSuspended (w : World) (entry : Json) : Except String Json := do
  let identity ← entry.getObjVal? "identity"
  let act ← (← entry.getObjVal? "outcome").getObjVal? "activity"
  let c ← expandCheckpoint w (← act.getObjVal? "checkpoint")
  let fill := fun (c : Json) (k : String) (v : Except String String) =>
    match c.getObjVal? k, v with
    | .error _, .ok v => c.setObjVal! k (toJson v)
    | _, _ => c
  let c := fill c "object" (act.getObjValAs? String "object")
  let c := fill c "principal" (identity.getObjValAs? String "principal")
  let c := fill c "intent" (identity.getObjValAs? String "intent")
  if (c.getObjVal? "digest").toOption.isSome then return c
  let tokens ← Delvetalk.Turn.tokensOfJson (← c.getObjVal? "tokens")
  return c.setObjVal! "digest" (toJson (Delvetalk.Turn.checkpointDigest
    (← c.getObjValAs? String "packetSha256") (← c.getObjValAs? String "object")
    (← c.getObjValAs? String "principal") (← c.getObjValAs? String "intent")
    (← c.getObjValAs? String "rootsDigest") tokens))

/-- Compile inputs from an entry: every CID resolved to the source a `module` entry recorded. -/
def expandInputs (w : World) (inputs : Json) : Except String Json := do
  let resolve := fun (cid : String) => match sourceText w cid with
    | some src => pure src
    | none => throw s!"compile inputs name module {cid}, which no module entry recorded"
  let inputs ← match inputs.getObjVal? "modules" with
    | .ok (.arr ms) => do
      let expanded ← ms.mapM fun m => do
        match m.getObjValAs? String "cid" with
        | .ok cid => pure (Json.mkObj [("name", (m.getObjVal? "name").toOption.getD Json.null), ("source", toJson (← resolve cid))])
        | .error _ => pure m
      pure (inputs.setObjVal! "modules" (.arr expanded))
    | _ => pure inputs
  match inputs.getObjValAs? String "sourceCid", inputs.getObj? with
  | .ok cid, .ok fields =>
    return Json.mkObj ((fields.toList.filter fun (kv : String × Json) => kv.1 != "sourceCid") ++ [("source", toJson (← resolve cid))])
  | _, _ => return inputs

/-- Count `o` in `world-status.recompiledDifferently` when a snapshot this process resumed from
    cached another packet digest for the same compile inputs; nothing is journaled to compare with. -/
def noteRecompiled (w : World) (o : Object) : World :=
  match w.cachedPackets[o.inputsKey]? with
  | some p => if p != o.packet then { w with recompiledDifferently := w.recompiledDifferently + 1 } else w
  | none => w

/-- A creation as a turn journals it, in its entry or its suspended activity; `lines` when its package's
    rules and wants were placed on it (no law given: `makeObject`), so it is built again so (`createdLaw`). -/
def createRecJson (id : String) (c : CreateRec) : Json :=
  Json.mkObj [("object", toJson id), ("pin", toJson c.object.pin),
    ("read", c.object.read.json), ("chain", c.object.chain.json), ("compile", compactInputs c.object.inputs),
    ("seed", c.seed), ("cid", toJson c.object.stateCid), ("law", toJson c.object.lawText)] |> fun j =>
    (if c.object.rules.isEmpty && c.object.wants.isEmpty then j else j.setObjVal! "lines" (toJson true)) |> fun j =>
    (if c.object.supervisor.isEmpty then j else j.setObjVal! "supervisor" (toJson c.object.supervisor)) |> fun j =>
    match c.madeFrom with
    | some m => j.setObjVal! "madeFrom" m
    | none => j

structure Judged where
  updates : List (String × Object)
  reprograms : List Json
  amendments : List Json
  creations : List (String × Object) := []
  creates : List Json := []
  /-- Per written object, the keys its declared retention evicted (`{field, key}`), journaled as the
      write's `evicted` when there are any. -/
  evicted : List (String × Array Json) := []
  /-- Per written object, the facts its law judged each distinct change by: what its rules are judged
      by too (`reactions`), so `request.verb`, `request.kind` and `request.clock` read alike. -/
  facts : List (String × List Law.Facts) := []

/-- The id of the `ordinal`th grant of the turn with this identity. -/
def grantId (principal intent : String) (ordinal : Nat) : String :=
  Journal.bodyHash (Json.arr #[toJson "grant", toJson principal, toJson intent, toJson ordinal])

/-- The grant `id`, if it can stand behind running `method` of `object` now: made, not
    revoked, the clock not past its `until`, and naming that object and method. -/
def grantStands (w : World) (id object method : String) : Option Grant :=
  match w.grants[id]? with
  | some g => if !g.revoked && w.clock ≤ g.expires && g.object == object && g.method == method then some g else none
  | none => none

/-- Install a commit's grants, spend its uses, and mark its revocations. -/
def applyGrants (w : World) (grants : List Grant) (revokes : List String) (spent : List (String × Nat) := []) : World :=
  let w := grants.foldl (fun w g => { w with grants := w.grants.insert g.id g }) w
  let w := spent.foldl (fun w (id, n) => match w.grants[id]? with
    | some g => { w with grants := w.grants.insert id { g with uses := g.uses.map (· - n) } }
    | none => w) w
  revokes.foldl (fun w id => match w.grants[id]? with
    | some g => { w with grants := w.grants.insert id { g with revoked := true } }
    | none => w) w

/-- The argument a use of grant `g` runs with: the caller's, with the grant's fixed part merged
    in. A fixed record field the caller gives with other bytes is a conflict; a fixed value that is
    not a record must be the whole argument (or the caller gives `{}`). -/
def attenuate (g : Grant) (argument : Data) : Except String Data := do
  let some raw := g.fixed | return argument
  let fixed ← decodeData Limits.dataDepth raw
  let same := fun (a b : Data) => Delvetalk.Canonical.encode a == Delvetalk.Canonical.encode b
  match fixed, argument with
  | .record ff, .record af =>
    for (k, v) in ff do
      if let some given := af.lookup k then
        unless same given v do throw "grantConflict"
    return .record (af ++ ff.filter fun (k, _) => (af.lookup k).isNone)
  | f, .record [] => return f
  | f, a => if same f a then return a else throw "grantConflict"

/-! ## The two-tier law

A package may declare `def law(old: State, new: State, request: Abi.Request) -> Abi.Verdict` (the
artifact's `law.present`) and `def lawReads() -> List<String>` (`law.reads`). After the law text
admits an ordinary write (kind 0), the host runs the current code's `law` on the object's state
before and after, with `request = {context, method, argument, kind, pin, reads}`, under
`Bounds.lawTicks`; `reads` are the objects `lawReads()` names, as `{object, version, state}`, each
a root of the turn. Reprograms and amendments are judged by the law text alone: the amendment
metarule is decided on the fragment, and no predicate, budget or bug can seal out the hand that
may amend or reprogram. -/

/-- Compile definition `name` of a package (compile inputs without `entry`) from its prepared
    closure, preparing the closure once per package and process; the world returned caches it. -/
def compileEntryIn (w : World) (inputs : Json) (name : String) : Except String (Package.EntryCompiled × World) := do
  let own := inputsKeyOf inputs
  let (request, w) ← match requestRead own with
    | some r => pure (r, w)
    | none =>
      let resolved ← resolveInputs w (Json.mkObj ((inputs.getObj?.toOption.map (·.toList)).getD [] |>.filter (·.1 != "entry")))
      let key := Journal.bodyHash resolved
      match w.requests[key]? with
      | some r => pure (requestKeep own r, w)
      | none =>
        let r ← (Package.prepareRequest resolved).mapError Package.Diagnostic.render
        pure (requestKeep own r, { w with requests := boundedInsert w.requests Limits.maxBuilds key r })
  let compiled ← (Package.compileEntryFrom request name).mapError Package.Diagnostic.render
  return (compiled, w)

def compiledOf (c : Package.EntryCompiled) : Except String Compiled := do
  return ⟨← c.artifact.getObjVal? "packet", c.entry.type, c.entry.source.assumptions.bounds,
    c.entry.source.assumptions.rigid, some c.entry,
    some (Delvetalk.Theory.ObjectiveBendCheckpoint.Dictionary.ofProgram c.entry.source.term)⟩

/-- A compiled definition from its packet: decoded and re-checked (`CheckedEntry.ofPacket`). -/
def compiledOfPacket (packet : Json) : Option Compiled := do
  let e ← (Delvetalk.CheckedEntry.ofPacket packet).toOption
  return ⟨packet, e.type, e.source.assumptions.bounds, e.source.assumptions.rigid, some e,
    some (Delvetalk.Theory.ObjectiveBendCheckpoint.Dictionary.ofProgram e.source.term)⟩

/-- This process's compiled definitions by key (`defKey`, a content address), whichever world compiled
    them. A world keeps only what its own threaded state cached, and a pure read that cannot hand a
    world back (a card's `actions` as it renders, a Bend law at judgement) would otherwise compile its
    definition again at every call: from source, or, under `DELVETALK_COMPILE_CACHE`, by reading and
    re-checking the file. -/
initialize defMemo : IO.Ref (Std.HashMap String Compiled) ← IO.mkRef {}

unsafe def memoReadImpl (key : String) : Option Compiled :=
  unsafeBaseIO do return (← defMemo.get)[key]?

/-- The process's compiled definition of `key`; `none` in the model (compile as if cold). -/
@[implemented_by memoReadImpl]
def memoRead (_key : String) : Option Compiled := none

/-- The on-disk form of a compiled definition. -/
def compiledJson (key : String) (c : Compiled) : Json := Json.mkObj [("key", toJson key), ("packet", c.packet)]

unsafe def memoKeepImpl (key : String) (c : Compiled) : Compiled :=
  unsafeBaseIO do
    if (← defMemo.get).contains key then return c
    defMemo.modify fun m => boundedInsert m Limits.maxCompiledPackets key c
    -- and the disk's, when there is one: a definition no world holds is never written by `persistCaches`
    (DiskCache.write "def" key (compiledJson key c)).catchExceptions fun _ => pure ()
    return c

/-- `c`, kept as the process's compiled definition of `key` (and the disk cache's). -/
@[implemented_by memoKeepImpl]
def memoKeep (_key : String) (c : Compiled) : Compiled := c

/-- Definitions that did not compile, by `defKey`, with why: asking again for a definition a package lacks (a
    card's `actions`, `lenses`, `prompt`) is answered here, not by preparing and failing again. -/
initialize failMemo : IO.Ref (Std.HashMap String String) ← IO.mkRef {}

unsafe def failReadImpl (key : String) : Option String :=
  unsafeBaseIO do return (← failMemo.get)[key]?

/-- Why `key` did not compile in this process; `none` in the model. -/
@[implemented_by failReadImpl]
def failRead (_key : String) : Option String := none

unsafe def failKeepImpl {α : Type} (key : String) (r : Except String α) : Except String α :=
  unsafeBaseIO do
    if let .error e := r then failMemo.modify fun m => boundedInsert m Limits.maxCompiledPackets key e
    return r

/-- `r`, its failure (if it is one) kept as the process's answer for `key`. -/
@[implemented_by failKeepImpl]
def failKeep {α : Type} (_key : String) (r : Except String α) : Except String α := r

/-- Whether `w` resolves `inputs`' library (or they name none): only then is a compile failure the package's own,
    the same in every world, and so the process's to remember. -/
def resolvable (w : World) (inputs : Json) : Bool :=
  match (inputs.getObjValAs? String "library").toOption with
  | some pin => w.libraries.contains pin
  | none => true

/-- Zero-argument pure definitions run, by `defKey`: their value is a function of the compiled entry alone
    (`forms()`, `views()`, `lenses()`, `lawReads()`), so it is computed once per process. -/
initialize zeroMemo : IO.Ref (Std.HashMap String (Except String Data)) ← IO.mkRef {}

unsafe def runZeroImpl (key : String) (entry : Delvetalk.CheckedEntry) : Except String Data :=
  unsafeBaseIO do
    if let some r := (← zeroMemo.get)[key]? then return r
    let r := (runPure entry [] Delvetalk.Bounds.lawTicks).1
    zeroMemo.modify fun m => boundedInsert m Limits.maxCompiledPackets key r
    return r

/-- `entry` (the definition `key`, of no arguments) run under the law's ticks. -/
@[implemented_by runZeroImpl]
def runZero (_key : String) (entry : Delvetalk.CheckedEntry) : Except String Data :=
  (runPure entry [] Delvetalk.Bounds.lawTicks).1

/-- A definition of the on-disk compile cache (`DiskCache`, kind `def`), when it holds `key`; once read,
    the process's. -/
def diskCompiled (key : String) : Option Compiled :=
  (DiskCache.read "def" key).bind fun j => ((j.getObjVal? "packet").toOption.bind compiledOfPacket).map fun c =>
    memoKeep key (DiskCache.hit c)


/-- The cache key of an object's compiled definition (`compiledMethod` uses the same). -/
def defKey (o : Object) (name : String) : String := o.inputsKey ++ "/" ++ name

/-- An object's definition `name`, compiled and prepared (from the world's cache when warm, else
    the process's, else the disk's). -/
def compileDef (w : World) (o : Object) (name : String) : Except String (Compiled × World) := do
  let key := defKey o name
  if let some c := w.compiled[key]? then return (c, w)
  if let some c := memoRead key <|> diskCompiled key then return (c, w)
  let mine := resolvable w o.inputs
  if mine then if let some e := failRead key then throw e
  let compiled := compileEntryIn w o.inputs name >>= fun (c, w) => do return (← compiledOf c, w)
  let (c, w) ← if mine then failKeep key compiled else compiled
  return (memoKeep key c, w)

/-- Compile the Bend law (and its reads) of the objects a proposal writes, into the world's
    cache, so the pure `judge` finds them. -/
def warmLaws (w : World) (ids : List String) : World :=
  ids.foldl (fun w id => match w.objects[id]? with
    | some o =>
      if !o.predicate then w else
      (["law"] ++ (if o.predicateReads then ["lawReads"] else [])).foldl (fun w name =>
        if w.compiled.contains (defKey o name) then w else
        match compileDef w o name with
        | .ok (c, w) => { w with compiled := boundedInsert w.compiled Limits.maxCompiledPackets (defKey o name) c }
        | .error _ => w) w
    | none => w) w

/-- The objects an object's `lawReads()` names. -/
def lawReadsOf (w : World) (o : Object) : Except String (List String) := do
  if !o.predicateReads then return []
  let (c, _) ← compileDef w o "lawReads"
  let some entry := c.entry | throw "lawReads is not held"
  match runZero (defKey o "lawReads") entry with
  | .ok value => match labels [] value with
    | some ids => return ids.eraseDups.take Limits.maxRoots
    | none => throw "lawReads must return a List<String>"
  -- Out of ticks is the turn's budget, transient, not the package's fault (codex host 14).
  | .error "budget" => throw "budget"
  | .error _ => throw "lawReads did not finish"

/-- A built package's relations, checked, and a state put in canonical form under them
    (`duplicateKey` refused by name). -/
def relationsFor (b : Built) (state : Data) : Except String (List RelDecl × Data) := do
  let decls := b.relations
  checkRelations decls b.assumptions.bounds b.ty
  match canonicalState decls state with
  | .ok s => return (decls, s)
  | .error "duplicateKey" => throw "duplicateKey: two rows of a relation share a key"
  | .error e => throw s!"{e}: a relation field does not hold rows"

/-- The `law` text an object's state holds (what `under "O"` judges by), parsed; none when it holds
    none or it does not parse. -/
def citedLaw (w : World) (id : String) : Option Law := do
  let .label text ← (w.objects[id]?).bind fun o => Law.rawField "law" o.state | none
  (parseLawText text).toOption

/-- What some names read beyond the written object, closed `Limits.lawDepth` deep, each once in the
    order met: every object they cite (`"O".F`, `under "O"`, `"O" wants N`); through `under "O"`, what
    O's law text names; through `"O" wants N` (when `wanting`), what O's want N names, with every want
    clause O carries, so a want resting on another's want is judged by both. Without `wanting` it is
    what a thing's kind carries through `under` (`carried`). -/
structure Cites where
  objects : List String := []
  wants : List (String × List Delvetalk.Compiler.ObjectiveBendLaw.Clause) := []

instance : Inhabited Cites := ⟨{}⟩

/-- The names a law reads. -/
def lawNames (law : Law) : List Delvetalk.Compiler.ObjectiveBendLaw.LawName :=
  law.flatMap fun (_, c) => c.names

/-- The objects a write's facts read and whether one may read them (`Law.Facts.reads`): the first of
    `ids` that `who` may not view, if any. -/
def unviewable (w : World) (who : String) (ids : List String) : Option String :=
  ids.find? fun r => !(((w.objects[r]?).map (·.read.permits who)).getD true)

/-- The states of some objects as the world holds them (`Law.Facts.reads`). -/
def statesOf (w : World) (ids : List String) : List (String × Data) :=
  ids.filterMap fun id => (w.objects[id]?).map (id, ·.state)

/-! ## Rules and wants on things (docs/OVERHAUL.md §2, §3; KERNEL-HANDOFF §27)

A thing carries the rules and wants hands placed on it (`Object.rules`, `Object.wants`), those of its own
text, and those its kind's text carries through `under` (`Law.followed`). Each is judged by the law's own
`denote`: a rule when a write makes its condition hold, a want on the thing as it stands. -/

/-- One rule or want a thing carries: the clause; the hand it is the act of (a placed line's placer; a
    line of the thing's own text, or of the kind whose text carries it, that object's owner); the object
    whose text or rows hold it; and the height it was placed at (none for a text's line). -/
structure CarriedClause where
  clause : Delvetalk.Compiler.ObjectiveBendLaw.Clause
  owner : String
  holder : String
  placed : Option Nat := none

/-- The text `owner` of a state record ("" for none). -/
def ownerOf (state : Data) : String :=
  match state with
  | .record fs => match fs.lookup "owner" with
    | some (.label t) => t
    | _ => ""
  | _ => ""

mutual
/-- `Cites` of some names (see the structure). -/
partial def citesOf (w : World) (first : List Delvetalk.Compiler.ObjectiveBendLaw.LawName) (wanting : Bool := true) : Cites := Id.run do
  let mut out : Cites := {}
  let mut seen : List Delvetalk.Compiler.ObjectiveBendLaw.LawName := []
  let mut frontier := first
  for _ in [0:Limits.lawDepth] do
    let mut next : List Delvetalk.Compiler.ObjectiveBendLaw.LawName := []
    for n in frontier do
      if seen.contains n then continue
      seen := seen ++ [n]
      match n with
      | .cited o _ =>
        unless out.objects.contains o do out := { out with objects := out.objects ++ [o] }
      | .law o =>
        unless out.objects.contains o do out := { out with objects := out.objects ++ [o] }
        next := next ++ ((citedLaw w o).getD []).flatMap fun (_, c) => c.names
      | .want o name =>
        unless out.objects.contains o do out := { out with objects := out.objects ++ [o] }
        if wanting then
          let clauses := match out.wants.lookup o with
            | some cs => cs
            | none => ((w.objects[o]?).map fun x => (carriedWants w o x).map (·.clause)).getD []
          unless out.wants.any (·.1 == o) do out := { out with wants := out.wants ++ [(o, clauses)] }
          next := next ++ ((clauses.find? (·.name == name)).map (·.condition.names)).getD []
      | _ => pure ()
    if next.isEmpty then break
    frontier := next
  return out

/-- The rules and wants `o` (`id`) carries, in order: its placed rules and wants, its own text's, then
    those its law's `under` citations carry (`Law.followed`), each owned by its holder's owner. -/
partial def carried (w : World) (id : String) (o : Object) : List CarriedClause :=
  let placed := (o.rules ++ o.wants).map fun r => ({ clause := r.clause, owner := r.owner, holder := id, placed := some r.since } : CarriedClause)
  let own := (((parseClauses o.lawText).toOption.getD []).filter fun c => Law.isRule c || Law.isWant c).map fun c =>
    ({ clause := c, owner := ownerOf o.state, holder := id } : CarriedClause)
  let followed := (Law.followed (statesOf w (citesOf w (lawNames o.law) false).objects) o.law).map fun (h, c) =>
    ({ clause := c, owner := ((w.objects[h]?).map (ownerOf ·.state)).getD "", holder := h } : CarriedClause)
  placed ++ own ++ followed

partial def carriedWants (w : World) (id : String) (o : Object) : List CarriedClause := (carried w id o).filter (Law.isWant ·.clause)
end

def carriedRules (w : World) (id : String) (o : Object) : List CarriedClause := (carried w id o).filter (Law.isRule ·.clause)

/-- The objects a law cites, closed (`citesOf`). -/
def lawCitations (w : World) (law : Law) : List String :=
  (citesOf w (lawNames law)).objects

/-- What a thing whose law is `law` stands at (`request.laws`, `request.refusedBy`): its law clauses, own
    and followed through `under` (`Law.lawClauses`), and the writes its law has refused (`World.refusedBy`). -/
def standingOf (w : World) (id : String) (law : Law) : Law.Standing :=
  { laws := Law.lawClauses (statesOf w (citesOf w (lawNames law) false).objects) law, refusedBy := w.refusedBy.getD id 0 }

/-- Facts about `facts.object`, whose law is `law`, with what some names cite as `w` holds it: the cited
    states (`Law.Facts.reads`), their want clauses (`Law.Facts.wants`), and what the object and each cited
    thing stand at (`Law.Facts.standing`: a cited want reads its own thing's). -/
def citing (w : World) (law : Law) (names : List Delvetalk.Compiler.ObjectiveBendLaw.LawName) (facts : Law.Facts) : Law.Facts :=
  let c := citesOf w names
  { facts with reads := statesOf w c.objects, wants := c.wants,
               standing := (facts.object, standingOf w facts.object law) :: c.objects.filterMap fun r =>
                 if r == facts.object then none else (w.objects[r]?).map fun o => (r, standingOf w r o.law) }

/-- What an object's law and the rules and wants it carries cite (their conditions and their spells'
    holes), closed: the roots a write of it records. -/
def objectCitations (w : World) (id : String) (o : Object) : List String :=
  (citesOf w (lawNames o.law ++ (carried w id o).flatMap (·.clause.names))).objects

/-- The proposal with the objects the laws of its written objects read added as roots: the Bend
    law's `lawReads`, and every object the text law and the carried rules and wants cite
    (`objectCitations`). -/
def withLawReads (w : World) (p : Proposal) : Proposal :=
  p.allWrites.foldl (fun p (id, _) => match w.objects[id]? with
    | some o => ((lawReadsOf w o).toOption.getD [] ++ objectCitations w id o).foldl (fun p r =>
          if p.roots.any (·.1 == r) then p else match w.objects[r]? with
          | some ro => { p with roots := p.roots ++ [(r, ro.version)] }
          | none => p) p
    | none => p) p

/-- Why a law's `under` citations cannot stand (create, amend, reprogram): a cited object that does
    not exist or whose `law` does not parse, or a cycle of citations within `Limits.lawDepth`,
    named. -/
def citationRefusal (w : World) (self : String) (law : Law) : Option String := Id.run do
  let unders := fun (l : Law) => (l.flatMap fun (_, c) => c.names.filterMap fun | .law o => some o | _ => none).eraseDups
  let mut paths : List (List String) := (unders law).map ([·])
  for _ in [0:Limits.lawDepth] do
    let mut next : List (List String) := []
    for path in paths do
      let some last := path.getLast? | continue
      if last == self || (path.dropLast.contains last) then
        return some s!"under: a cycle of citations: {" -> ".intercalate ((if self.isEmpty then [] else [self]) ++ path)}"
      unless w.objects.contains last do return some s!"under: no object {last} to cite"
      let some cited := citedLaw w last | return some s!"under: {last} holds no law text that parses"
      next := next ++ (unders cited).map (path ++ [·])
    paths := next
  return none

/-- The display handle the principal registry holds for a principal, "" when unknown. -/
def handleOf (w : World) (principal : String) : String :=
  (w.handles[principal]?).getD ""

/-- How a principal is named on a card: the handle the registry holds, else the principal. -/
def shownName (w : World) (principal : String) : String :=
  let h := handleOf w principal
  if h.isEmpty then principal else h

/-- The principal the registry names by `handle` (case folded, as a DNS name is), if one. -/
def principalNamed (w : World) (handle : String) : Option String :=
  let h := handle.toLower
  w.handles.fold (fun acc did name => if acc.isNone && name.toLower == h then some did else acc) none

/-- What the host tells a running method about itself, built here and nowhere else.
    `handle` is the principal's display handle from the registry (`world-principal`), ""
    when unknown; `caller` is the calling object's id (empty for the turn's own method),
    `intent` the turn's identity, `height` the journal height the turn read, `clock` the world
    clock (`world-advance`) the frame runs at, which deadlines compare against,
    `inputOrigin.post` the post the turn came from (`TurnState.post`), "" for none, and `sender`
    the object whose send this turn delivers (a rule's object, a sending object, a supervised
    activity's), the same in every frame of the turn and in its law's context, "" for a turn a
    principal began. None is chosen by the client. -/
def contextData (id principal handle caller intent : String) (height clock : Nat) (kind command : String)
    (post : String := "") (sender : String := "") : Data :=
  .record [("world", .label ""), ("object", .label id), ("principal", .label principal),
    ("handle", .label handle), ("caller", .label caller), ("sender", .label sender), ("intent", .label intent), ("height", .natural height),
    ("clock", .natural clock),
    ("inputOrigin", .record [("kind", .label kind), ("object", .label caller), ("command", .label command),
      ("program", .label ""), ("immediatelyPrevious", .boolean false), ("post", .label post)])]

/-- A record the host builds (a Context, a law's Request) as the receiving code's own library
    declares it: the fields its type names, in its order, each fitted alike. An object compiled
    under an older library whose Context lacks a field the host now fills keeps running; a
    field the host cannot fill leaves the record as built (and the kernel refuses it by name). -/
partial def fitRecord (bounds : DataBounds) (ty : Delvetalk.Theory.ObjectiveBendTypes.Ty) (d : Data) : Data :=
  match d, recordFieldTypes bounds (bounds.length + 1) ty with
  | .record fs, some names =>
    if names.all (fun (n, _) => fs.any (·.1 == n)) then
      .record (names.map fun (n, m) => (n, fitRecord bounds m ((fs.lookup n).getD (.record []))))
    else d
  | _, _ => d

/-- The fields `contextData` fills. -/
def contextFields : List String :=
  ["world", "object", "principal", "handle", "caller", "sender", "intent", "height", "clock", "inputOrigin"]

/-- A Context type: a record (through the bounds) naming the principal and the intent, every
    field of which the host fills. An older library's Context with fewer fields is one too. -/
def isContextType (bounds : DataBounds) (ty : Delvetalk.Theory.ObjectiveBendTypes.Ty) : Bool :=
  match recordFieldTypes bounds (bounds.length + 1) ty with
  | some fs => fs.any (·.1 == "principal") && fs.any (·.1 == "intent") && fs.all (contextFields.contains ·.1)
  | none => false

/-- The parameter types of a definition's type, outermost first. -/
def arrowDomains : Nat → Delvetalk.Theory.ObjectiveBendTypes.Ty → List Delvetalk.Theory.ObjectiveBendTypes.Ty
  | fuel + 1, .arrow _ _ domain codomain => domain :: arrowDomains fuel codomain
  | _, _ => []

/-- `turn-start` on a held entry whose last parameter is a Context, sent the arguments before it:
    the host appends the Context the binding (`object`, `principal`, `intent`, the entry's name as
    the command) implies, fitted to the entry's own Context type, as a world turn builds it
    (`inputOrigin.kind` "repl"; `handle`, `height` and `clock` from the world this process has open,
    else "" and 0). A request that already carries the Context (one argument more) is as sent:
    a REPL turn may name its own Context. -/
def withBindingContext (world : Option World) (entry : Delvetalk.CheckedEntry) (request : Json) : Except String Json := do
  let arguments ← (← request.getObjVal? "arguments").getArr?
  let domains := arrowDomains Delvetalk.Bounds.entryArrowDepth entry.type
  let bounds := entry.source.assumptions.bounds
  let some ct := domains.getLast? | return request
  unless domains.length == arguments.size + 1 && isContextType bounds ct do return request
  let principal ← request.getObjValAs? String "principal"
  let command := ((request.getObjVal? "artifact").toOption.bind fun a => (a.getObjValAs? String "entry").toOption).getD ""
  let context := contextData (← request.getObjValAs? String "object") principal
    ((world.map (handleOf · principal)).getD "") "" (← request.getObjValAs? String "intent")
    ((world.map (·.height)).getD 0) ((world.map (·.clock)).getD 0) "repl" command
  return request.setObjVal! "arguments" (Json.arr (arguments.push (dataJson (fitRecord bounds ct context))))

/-- An object's Bend law on one ordinary write: none when it admits. -/
def bendLaw (w : World) (p : Proposal) (id : String) (o : Object) (new : Data) (subject caller method : String)
    (argument : Data) (kind : Nat) (pin : String) : Option Refusal := Id.run do
  let refuse := fun (clause reading : String) => some ({ cls := "lawRefused", clause := some clause, object := some id, reading := some reading } : Refusal)
  let .ok (c, _) := compileDef w o "law" | return refuse "law" s!"the Bend law of {id} does not compile."
  let some entry := c.entry | return refuse "law" s!"the Bend law of {id} does not compile."
  let ids ← match lawReadsOf w o with
    | .ok ids => pure ids
    | .error "budget" => return some { cls := "budget", reason := some "law ticks", object := some id }
    | .error e => return refuse "lawReads" s!"the law of {id} does not say what it reads: {e}"
  let mut reads : List Data := []
  for r in ids do
    match w.objects[r]? with
    | some ro =>
      unless p.roots.any (·.1 == r) do return refuse "lawReads" s!"the law of {id} reads {r}, which this turn did not read."
      -- A law reads only what its subject may view: its verdict could disclose the rest (codex host 3).
      unless ro.read.permits subject do
        return some { cls := "lawRefused", clause := some "lawReads", object := some id,
                      reading := some s!"the law of {id} reads {r}, which you may not see." }
      reads := reads ++ [.record [("object", .label r), ("version", .natural ro.version), ("state", ro.state)]]
    | none => pure ()
  let context := contextData id subject (handleOf w subject) caller p.intent w.height w.clock "law" method (sender := p.sender)
  let request := Data.record [("context", context), ("method", .label method), ("argument", argument),
    ("kind", .natural kind), ("pin", .label pin),
    ("reads", reads.foldr (fun x t => .variant "cons" (.record [("head", x), ("tail", t)])) (.variant "nil" (.record [])))]
  let request := match c.type with
    | .arrow _ _ _ (.arrow _ _ _ (.arrow _ _ requestType _)) => fitRecord c.bounds requestType request
    | _ => request
  match (runPure entry [o.state, new, request] Delvetalk.Bounds.lawTicks).1 with
  | .ok (.variant "admitted" _) => return none
  | .ok (.variant "refused" (.record f)) =>
    match f.lookup "clause", f.lookup "reading" with
    -- A verdict without a reading takes the one the package gave the clause, else says so.
    | some (.label clause), reading =>
      let given := match reading with | some (.label t) => if t.isEmpty then none else some t | _ => none
      return refuse clause ((given <|> o.readings.lookup clause).getD s!"the Bend law of {id} refuses this.")
    | _, _ => return refuse "law" s!"the Bend law of {id} gave no verdict."
  | .error "budget" => return some { cls := "budget", reason := some "law ticks", object := some id }
  | _ => return refuse "law" s!"the Bend law of {id} gave no verdict."

/-- An admitted entry's writes with their edits (`Touch`): for each written object, the version and
    the edits other than `keep` then a retraction of each evicted key; none for a write that was not
    one of edits. -/
def writeEdits (entry : Json) : List (String × Nat × Option (List (String × Data))) :=
  let ws := ((entry.getObjVal? "outcome").toOption.bind (·.getObjVal? "writes" |>.toOption)
    |>.bind (·.getArr? |>.toOption)).getD #[]
  ws.toList.filterMap fun x => do
    let id ← (x.getObjValAs? String "object").toOption
    let version ← (x.getObjValAs? Nat "version").toOption
    let kinds := (((x.getObjVal? "kinds").toOption.bind (·.getArr? |>.toOption)).getD #[]).toList
    let steps := (((x.getObjVal? "edits").toOption.bind (·.getArr? |>.toOption)).getD #[]).toList
    -- A key the declared retention evicted is touched as a retraction of it (codex host 10).
    let evicted := (((x.getObjVal? "evicted").toOption.bind (·.getArr? |>.toOption)).getD #[]).toList.filterMap fun e => do
      let f ← (e.getObjValAs? String "field").toOption
      let k ← (e.getObjVal? "key").toOption.bind (decodeData Limits.dataDepth · |>.toOption)
      return (f, Data.variant "retract" (Data.record [("key", k)]))
    let edits : Option (List (String × Data)) :=
      -- A placing (kind `rule`) moves no field: it neither changes what a turn read nor ends the run of writes.
      if kinds.any (fun k => !((k.getNat?.toOption.map fun n => n == 4 || Law.editKind n).getD false)) then none else
      (steps.foldlM (init := ([] : List (String × Data))) fun acc step => match decodeData Limits.dataDepth step with
        | .ok (.record fs) => some (acc ++ fs.filter fun (x : String × Data) => match x.2 with
            | Data.variant "keep" _ => false
            | _ => true)
        | _ => none).map (· ++ evicted)
    return (id, version, edits)

/-- The index rows an admitted entry at `height` adds (`World.touches`), from its `writes`. -/
def touchesOf (height : Nat) (entry : Json) : List (String × Touch) :=
  (writeEdits entry).map fun (id, version, _) => (id, { version, height })

/-- The edits of the change `t` of `id`, read from its entry (`writeEdits`): none for a change not of
    edits (a reprogram, an amendment, a root `set`, whose entry writes none of them). -/
def touchEdits (w : World) (id : String) (t : Touch) : Option (List (String × Data)) := do
  let entry ← w.entries.get? (t.height - 1)
  let (_, _, edits) ← (writeEdits entry).find? fun (x, v, _) => x == id && v == t.version
  edits

/-- The edits of `id`'s admitted writes after version `seen`, oldest first, from the per-object
    index (`World.touches`, newest back to `seen`); none when one of them was not an ordinary write
    (a reprogram or an amendment) or does not decode. -/
def editsSince (w : World) (id : String) (seen : Nat) : Option (List (String × Data)) := Id.run do
  let ts := w.touches.getD id #[]
  let mut out : List (String × Data) := []
  let mut i := ts.size
  while i > 0 do
    i := i - 1
    let t : Touch := ts[i]!
    if t.version ≤ seen then break
    match touchEdits w id t with
    | some es => out := es ++ out
    | none => return none
  return some out

/-- The fields of `id` its ordinary admitted writes changed after version `seen` (edits other
    than `keep`); none when one of its later changes was not an ordinary write. -/
def fieldsChangedSince (w : World) (id : String) (seen : Nat) : Option (List String) :=
  (editsSince w id seen).map fun es => (es.map (·.1)).eraseDups

/-- The keys of relation `d` that ordinary admitted writes of `id` touched after version `seen`
    (the rows' keys of inserts and upserts, the keys of retracts); none when a later change of `id`
    was not an ordinary write or changed the field by any other edit (a `set` of the whole relation
    touches every key). Reads only the writes since `seen` (`editsSince`). -/
def keysChangedSince (w : World) (id : String) (seen : Nat) (d : RelDecl) : Option (List Data) := do
  let es ← editsSince w id seen
  (es.filter (·.1 == d.field)).mapM fun (_, k) => match parseKind k with
    | some (.insert row) | some (.upsert row) => (keyOf d row).toOption
    | some (.retract key) => (keyAsDeclared d key).toOption
    | _ => none

/-- The changes an entry at `height` makes (`World.changes`): an admitted entry's creations (version 0)
    then its writes, a `created` entry's object. -/
def changesOf (height : Nat) (entry : Json) : Array Change :=
  let principal := ((entry.getObjVal? "identity").toOption.bind (·.getObjValAs? String "principal" |>.toOption)).getD ""
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let rows := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
  let change := fun (id : String) (version : Nat) => ({ height, object := id, version, principal } : Change)
  match (outcome.getObjValAs? String "tag").toOption.getD "" with
  | "admitted" =>
    let writes := (rows "writes").filterMap fun x => do
      return change (← (x.getObjValAs? String "object").toOption) (← (x.getObjValAs? Nat "version").toOption)
    let creates := (rows "creates").filterMap fun x => do
      let id ← (x.getObjValAs? String "object").toOption
      if writes.any (·.object == id) then none else some (change id 0)
    creates ++ writes
  | "created" => ((outcome.getObjValAs? String "object").toOption.map fun id => #[change id 0]).getD #[]
  | _ => #[]

/-- The newest change of each object `reader` may read under `prefix` since `since` (heights above it),
    newest first, after the row of `after` when one is named; at most `Limits.listPage`, and whether
    more follow. Walks `World.changes` from the newest back to `since`. -/
def changedSince (w : World) (reader : String) (since : Nat) (pfx after : String) : List Change × Bool := Id.run do
  let mut seen : Std.HashSet String := {}
  let mut started := after.isEmpty
  let mut out : Array Change := #[]
  let mut i := w.changes.size
  while i > 0 do
    i := i - 1
    let c := w.changes[i]!
    if c.height ≤ since then break
    if seen.contains c.object then continue
    seen := seen.insert c.object
    if !started then
      if c.object == after then started := true
      continue
    unless c.object.startsWith pfx do continue
    let some o := w.objects[c.object]? | continue
    unless o.read.permits reader do continue
    if out.size == Limits.listPage then return (out.toList, true)
    out := out.push c
  return (out.toList, false)


/-- The edit half of `movedRootAdmits`: with `changedFields`, an edit of a field no write since
    changed is admitted too. With no change of `id`, `none` changes of its own (`noChange`). -/
def editsAdmit (w : World) (writes : List (String × List Written)) (id : String) (seen : Nat)
    (changedFields : Option (List String)) (noChange : Bool) : Bool :=
  let decls := ((w.objects[id]?).map (·.relations)).getD []
  let untouched := fun (e : Edit) =>
    match decls.find? (·.field == e.field) with
    | none => false
    | some d =>
      let key? := match e.kind with
        | .upsert row => (keyOf d row).toOption
        | .retract key => (keyAsDeclared d key).toOption
        | _ => none
      match key?, keysChangedSince w id seen d with
      | some key, some keys =>
        let k := Delvetalk.Canonical.encode key
        !keys.any (Delvetalk.Canonical.encode · == k)
      | _, _ => false
  match writes.lookup id with
  | none => noChange && changedFields.isSome
  | some changes => !changes.isEmpty && changes.all fun c => Law.editKind c.kind && c.edits.all fun e =>
      e.kind.commutes || untouched e ||
        (match changedFields with
         | some fields => !fields.contains e.field
         | none => false)

/-- A root `id` the turn read at `seen` that has moved since may still commit when every change the
    turn makes of it is an ordinary write and each edit either commutes (`EditKind.commutes`), or
    is an `upsert`/`retract` of a relation row whose key no admitted write since `seen` touched
    (`keysChangedSince`: the row rule, for any root), or, on a resumed turn's own object (`own`), is
    to a field those writes left alone (a turn that only read its own object qualifies). Anything
    else is `staleRoot`. -/
def movedRootAdmits (w : World) (writes : List (String × List Written)) (id : String) (seen : Nat) (own : Bool) : Bool :=
  editsAdmit w writes id seen (if own then fieldsChangedSince w id seen else none) own

/-- What a turn read of `id` at `seen` by its cells still holds: every later change of `id` was an ordinary write
    (`editsSince`) that left alone what the turn read. Its scalar part: no field that is not a
    declared relation changed. A field read whole: unchanged. A row: no write touched its key
    (`keysChangedSince`). A span: no write touched a key at or before its last (any key, for the
    whole key set): an insert or a retract there moves what the spine showed, and an upsert there
    may change a row the turn passed. A gap: no write touched a key strictly inside it (an insert
    there could be the key the lookup missed); a write below or above a looked-up key leaves the
    lookup as it was. -/
def cellsCurrent (w : World) (id : String) (seen : Nat) (r : Cells) : Bool := Id.run do
  let some changed := fieldsChangedSince w id seen | return false
  let decls := ((w.objects[id]?).map (·.relations)).getD []
  if r.scalar && changed.any (fun f => !decls.any (·.field == f)) then return false
  if r.fields.any changed.contains then return false
  let touched := fun (f : String) => match decls.find? (·.field == f) with
    | some d => keysChangedSince w id seen d
    | none => if changed.contains f then none else some []
  for (f, key) in r.rows do
    match touched f with
    | some keys => if keys.any (Delvetalk.Canonical.encode · == Delvetalk.Canonical.encode key) then return false
    | none => return false
  for (f, through) in r.spans do
    match touched f, through with
    | some keys, none => if !keys.isEmpty then return false
    | some keys, some last => if keys.any (keyAtMost · last) then return false
    | none, _ => return false
  let below := fun (a b : Data) => keyAtMost a b && Delvetalk.Canonical.encode a != Delvetalk.Canonical.encode b
  for (f, after, before) in r.gaps do
    match touched f with
    | some keys =>
      if keys.any (fun k => (after.all (below · k)) && (before.all (below k ·))) then return false
    | none => return false
  return true

/-- A root `id` read at `seen` that has moved since may still commit: by the turn's changes of it
    (`movedRootAdmits`: they commute, edit untouched keys, or, on a resumed turn's own object, fields
    the writes since left alone), or, for a root read by its cells, because no write since touched
    what it read (`cellsCurrent`) and each of its edits leaves alone what those writes changed: a
    keyed edit an untouched key, any other a field they left alone (RELATIONAL §3: a waiting edit
    never silently replaces or removes a row it did not see). The cells only admit more: a root read
    by them is never stale where the whole-object rule admits it. One rule for `judge` and a
    resumption. -/
def rootAdmits (w : World) (writes : List (String × List Written)) (id : String) (seen : Nat)
    (cells : Option Cells) (own : Bool) : Bool :=
  movedRootAdmits w writes id seen own ||
    ((cells.map (cellsCurrent w id seen)).getD false && editsAdmit w writes id seen (fieldsChangedSince w id seen) true)

/-- `principal` acts as the world's opener: it is the opener, and the request did not come on the
    public socket (`World.resident`). -/
def openerActs (w : World) (principal : String) : Bool :=
  !w.opener.isEmpty && principal == w.opener && !w.resident

/-- The widened metarule (docs/ROOT.md §2.1): an amendment (kind 2) by the world's opener is
    admitted by the host whatever the law says. A law cannot name the opener (its grammar has no
    `world`, and a package's law is written before any world exists), so the host holds the rule
    rather than checking every law for a clause no package could write; `world-inspect` shows it as
    the law's first row. -/
def openerAmends (w : World) (subject : String) : Bool := openerActs w subject

/-- Why `principal`'s change waits (docs/ROOT.md §2.2): the hand quieted it until a clock past this one.
    Every entry changing the world under that principal is refused so, transiently, whatever carries it (a
    turn, a proposal, a reprogram, an amendment, a placing, a resumption, a delivery); the opener is never. -/
def quietOf (w : World) (principal object : String) : Option Refusal := do
  let (till, reading) ← w.quiets[principal]?
  guard (till > w.clock && !openerActs w principal)
  return { cls := "quiet", clause := some s!"until clock {till}", object := if object.isEmpty then none else some object,
           reason := some s!"the hand quieted you until clock {till}: {reading}", next := some till }

/-- A state as clauses reading `names` see it: every scalar field, and only the relations they name
    (a clause citing another object's law by `under` may read any field: then the whole state). A
    clause reads a state by its top-level fields alone, so to it this is the whole state, made without
    the rows of relations it does not name. -/
def viewFor (names : List Delvetalk.Compiler.ObjectiveBendLaw.LawName) (cells : Delvetalk.Turn.StateCells) : Data :=
  if names.any (fun | .law _ => true | _ => false) then cells.state
  else Delvetalk.Turn.wholeOf cells.scalar
    ((cells.relations.filter fun r => names.contains (.field r.field)).map fun r => (r.field, r.rows))

/-- Roots current, writes read, results conform, laws admit. Returns the objects
    as they would be installed. `height` is the height the entry would take. -/
def judge (w : World) (height : Nat) (p : Proposal) : Except Refusal Judged := do
  if let some r := quietOf w p.principal ((p.roots.head?.map (·.1)).getD "") then throw r
  let writes := p.allWrites
  for id in p.roots.map (·.1) ++ writes.map (·.1) do
    unless w.objects.contains id do throw { cls := "unknownObject", object := id }
  -- A root the turn only changes by `add`/`append` (FOUNDATION section 13, row 1) need only be a
  -- version the object had: its changes re-apply on the state as it is now and are judged there.
  for (id, seen) in p.roots do
    if let some o := w.objects[id]? then
      if o.version != seen && !(seen < o.version &&
          rootAdmits w writes id seen (p.cells.lookup id) (p.rebaseOwn == some id)) then
        throw { cls := "staleRoot", object := id }
  -- A write to the running object needs no view; its version is the first root. A
  -- proposal that writes what it never named as a root is malformed.
  for (id, _) in writes do
    unless p.roots.any (·.1 == id) do
      throw { cls := "evaluation", object := id, reason := some "a write names an object that is not a root" }
  -- An absence is a root too: something appearing since the turn looked makes it stale.
  for id in p.absent do
    if w.objects.contains id then throw { cls := "staleRoot", object := id }
  if w.objects.size + p.creates.length > w.objectBound then
    throw { cls := "evaluation", reason := some "object capacity reached" }
  if w.grants.size + p.grants.length > Limits.maxGrants then throw { cls := "capacity", object := some "grants", reason := some "maxGrants" }
  for g in p.grants do
    if w.grants.contains g.id then throw { cls := "evaluation", reason := some "a grant id is already taken" }
  -- A limited grant must have the uses the turn spends left when it commits.
  for (id, n) in p.spent do
    match w.grants[id]? with
    | some g =>
      if let some left := g.uses then
        if left < n then throw { cls := "lawRefused", clause := some "grantSpent", object := some g.object,
                                  reading := some s!"the grant has {left} of its uses left, and the turn spends {n}." }
    | none => throw { cls := "evaluation", reason := some "a turn spends an unknown grant" }
  -- A revocation needs the grantor's turn, or a turn that read the object holding the grant.
  for id in p.revokes do
    match w.grants[id]? with
    | some g =>
      unless g.grantor == p.principal || p.roots.any (·.1 == g.holder) || openerActs w p.principal do
        throw { cls := "lawRefused", clause := some "notGrantor", object := some g.holder,
                reading := some s!"only its grantor, or a turn that read {g.holder}, revokes the grant." }
    | none => throw { cls := "evaluation", reason := some "a revocation names an unknown grant" }
  let mut out : List (String × Object) := []
  let mut reprograms : List Json := []
  let mut amendments : List Json := []
  let mut evictions : List (String × Array Json) := []
  let mut factsOf : List (String × List Law.Facts) := []
  -- Every write is applied before any law judges: a law citing another object the commit writes reads
  -- it as the commit leaves it, so an atomic commit is judged as the world it makes.
  let mut staged : List (String × List Written × Object × Object × Delvetalk.Turn.StateCells × List (String × Data)) := []
  for (id, changes) in writes do
    let some o := w.objects[id]? | throw { cls := "unknownObject", object := id }
    let applied ← match applyEdits o.relations o.cells (changes.map (·.edits)) with
      | .ok a => pure a
      | .error clause => throw { cls := clause, object := id }
    let evictedKeys := applied.evicted.toArray.filterMap fun (f, row) => do
      let d ← o.relations.find? (·.field == f)
      let k ← (keyOf d row).toOption
      return Json.mkObj [("field", toJson f), ("key", dataJson k)]
    unless evictedKeys.isEmpty do evictions := evictions ++ [(id, evictedKeys)]
    -- Checked by its changed cells: every row it left as it was conformed when it was written
    -- (`Turn.Changes.checked`).
    unless (applied.changes.checked applied.cells).conformsUnder o.bounds o.stateType do
      throw { cls := "typeMismatch", object := id }
    -- A fixed field is set when the object is made and never after: no write changes it (a
    -- proposal's edits are not the kernel's, which refuses such a write at compile).
    if let some f := movedFixed o.fixed o.cells applied.cells then
      throw { cls := "lawRefused", clause := some "fixed", object := some id,
              reading := some s!"{f} is fixed; it is set when {id} is made and never after." }
    if let some cell := applied.changes.overBound applied.cells then
      throw (cellRefusal id cell)
    -- A reprogram replaces code and, through its migration, the state's type.
    let mut next := o
    let mut cells := applied.cells
    if let some (source, migration) := p.programs.lookup id then
      let refuse := fun (clause message : String) => ({ cls := "programRefused", clause := some clause, object := some id, reason := some message } : Refusal)
      let extend := p.layered.contains id
      let prog ← match programFor w o source migration extend with
        | .ok prog => pure prog
        | .error (clause, message) => throw (refuse clause message)
      let written := applied.cells.state
      let mut state := written
      if let some m := prog.migration then
        match runMigration m written with
        | .ok value => state := value
        | .error e => throw (refuse "migration" e)
      unless state.conformsUnder prog.bounds prog.stateType do
        throw (refuse "migration" "the converted state does not conform to the new state type")
      -- A fixed field stays fixed: new code must fix it too (codex host 5, docs 1).
      if let some f := o.fixed.find? (!prog.fixed.contains ·) then
        throw (refuse "fixed" s!"{f} is fixed; it is set when {id} is made and never after, so the new code must keep it fixed")
      -- A migration's result is put in canonical form under the new code's relations.
      state ← match canonicalState prog.relations state with
        | .ok s => pure s
        | .error e => throw (refuse "migration" s!"{e}: the converted state's relations are not canonical")
      cells := Delvetalk.Turn.StateCells.of (cellDecls prog.relations) state
      if let some cell := (Delvetalk.Turn.Changes.all cells).overBound cells then
        throw (cellRefusal id cell "programRefused")
      -- No migration sets a fixed field: one fixed before, or one the new code fixes that the old
      -- state had, keeps the value it had, judged on the state as it will be held.
      if let some f := movedFixed (prog.fixed.filter fun f => (Law.rawField f written).isSome) applied.cells cells then
        throw (refuse "fixed" s!"the migration sets {f}, which is fixed")
      next := { o with pin := prog.pin, packet := prog.packet, inputs := prog.inputs, inputsKey := inputsKeyOf prog.inputs,
                       stateType := prog.stateType, bounds := prog.bounds, methods := prog.methods,
                       predicate := prog.predicate, predicateReads := prog.predicateReads, relations := prog.relations,
                       fixed := prog.fixed, declares := prog.declares, madeFrom := (p.madeFrom.lookup id).orElse fun _ => o.madeFrom }
      reprograms := reprograms ++ [Json.mkObj [("object", toJson id), ("oldPin", toJson o.pin),
        ("newPin", toJson prog.pin),
        ("source", toJson source), ("migration", toJson migration),
        ("result", dataJson state)] |> (fun j => if extend then j.setObjVal! "mode" (toJson "extend") else j) |>
          fun j => match p.madeFrom.lookup id with
            | some m => j.setObjVal! "madeFrom" m
            | none => j]
    staged := staged ++ [(id, changes, o, next, cells, applied.evicted)]
  let cand := staged.foldl (fun (c : World) (id, changes, o, next, cells, _) =>
      { c with objects := c.objects.insert id { next with cells, version := if changes.any (·.kind != 4) then o.version + 1 else o.version } })
    (p.creates.foldl (fun (c : World) (id, x) => { c with objects := c.objects.insert id x.object }) w)
  for (id, changes, o, next, cells, evicted) in staged do
    let mut next := next
    -- The current law judges the whole write, under the pin the object will run. Every
    -- kind of change the object undergoes in this turn is judged, once for each object
    -- that called the running one to make it: the subject is the principal, the caller
    -- is the object whose call it was (empty when the turn's own method wrote).
    -- A change made under a grant is judged with the grantor as its subject, if the grant
    -- still stands for this object and method; otherwise the turn is refused `noGrant`.
    -- The state a reprogram's migration makes is a proposed write too: judged once more as kind
    -- `proposed`, as whoever asked for the reprogram.
    let migrated := if ((p.programs.lookup id).map (·.2.isEmpty)) == some false then
        (changes.filter (·.kind == 1)).map fun c => { c with kind := Law.proposedKind }
      else []
    let judgments := ((changes ++ migrated).map fun c => (c.caller, c.kind, c.method, c.via, c.verb)).eraseDups
    -- A placement is judged by the law (`request.kind == rule`); taking a line off is the placer's or
    -- the owner's, judged below by who asks.
    let judgments := if judgments.isEmpty then [("", 0, "", "", "")] else
      judgments.filter fun (_, kind, _, _, verb) => kind != 4 || !verb.isEmpty
    let mut judgedBy : List Law.Facts := []
    for (caller, kind, method, via, verb) in judgments do
      let subject ← if via.isEmpty then pure p.principal else
        match grantStands w via id method with
        | some g => pure g.grantor
        | none => throw { cls := "lawRefused", clause := some "noGrant", object := some id,
                          reading := some s!"no standing grant lets this turn run {method} on {id}." }
      -- What the law cites is read as the commit leaves it (the roots `withLawReads` records), and only
      -- by a subject who may view it.
      if let some r := unviewable cand subject (lawCitations cand o.law) then
        throw { cls := "lawRefused", clause := some "lawReads", object := some id,
                reading := some s!"the law of {id} cites {r}, which {subject} may not view." }
      let facts : Law.Facts := citing cand o.law (lawNames o.law)
        { subject, caller, height, turn := p.turn, pin := next.pin, kind, method,
          verb := if verb.isEmpty then method else verb, evicted, clock := w.clock, object := id }
      judgedBy := judgedBy ++ [facts]
      -- The metarule, widened (docs/ROOT.md §2.1): no law locks out the hand that opened the world.
      -- An amendment by the opener is the host's to admit; every other change is the law's.
      unless kind == 2 && openerAmends w subject do
        let names := lawNames o.law
        if let some (clause, cited) := Law.refusal o.law facts (some (viewFor names o.cells)) (viewFor names cells) then
          throw { cls := "lawRefused", clause, object := id, reading := cited <|> o.readings.lookup clause }
    -- The Bend law, after the text admits: once for each write of edits (the object's own or a
    -- proposed one, its `kind` saying which), with its argument. A migration's state is the text
    -- law's alone: the old code's law does not read the new type.
    if o.predicate then
      -- A placing (a rule, want or verb placed, kind 4 with its verb) is judged too: its state is unchanged,
      -- and a predicate refusing `request.kind == 4` keeps its card from strangers' rules (codex objects 4).
      let judged := changes.filter fun c => Law.editKind c.kind || (c.kind == 4 && !c.verb.isEmpty)
      let seen := judged.foldl (fun (acc : List (String × Written)) c =>
        let key := (Json.arr #[toJson c.caller, toJson c.kind, toJson c.method, toJson c.via, dataJson c.argument]).compress
        if acc.any (·.1 == key) then acc else acc ++ [(key, c)]) []
      for (_, c) in seen do
        let subject := if c.via.isEmpty then p.principal else ((grantStands w c.via id c.method).map (·.grantor)).getD p.principal
        if let some r := bendLaw cand p id o cells.state subject c.caller c.method c.argument c.kind next.pin then throw r
    if let some text := p.laws.lookup id then
      let refuse := fun (clause reading : String) => ({ cls := "lawRefused", clause := some clause, object := some id, reading := some reading } : Refusal)
      let law ← match parseLawText text with
        | .ok law => pure law
        | .error e => throw (refuse "law syntax" e)
      let amender := ((changes.find? (·.kind == 2)).map (·.caller)).getD ""
      -- The opener's amendment needs no clause for itself: the host admits it whatever the law (`openerAmends`).
      if let some message := citationRefusal cand id law then throw (refuse "under" ((message.drop "under: ".length).toString))
      unless openerAmends w p.principal do
        if let some message := amendable law p.principal amender height p.turn next.pin cells.state w.clock id (citing cand law (lawNames law)) then throw (refuse "amendable" message)
      -- A reading stays with its clause only while the amendment leaves that clause as it was.
      -- The amendment's own readings; a clause it leaves as it was without one keeps its reading.
      let given := ((parseLawTextReadings text).toOption.map (·.2)).getD []
      let kept := o.readings.filter fun (n, _) => law.lookup n == o.law.lookup n && (given.lookup n).isNone
      next := { next with law, lawText := text, readings := given ++ kept }
      amendments := amendments ++ [Json.mkObj [("object", toJson id), ("old", toJson o.lawText), ("new", toJson text)]]
    -- Rules, wants and verbs placed and taken off (KERNEL-HANDOFF §27 item 1; FOUNDATION §10): a rule's
    -- or a want's line parsed by the one parser, of the modality it is placed as, its name new across
    -- the thing's text and placed lines; a verb's name a spell's action word new to the thing's forms,
    -- the host's spells and its verbs, on a thing with an `act`; each within its bound; a removal by
    -- its placer, the thing's owner or the opener.
    for x in p.placements.filter (·.object == id) do
      let refuse := fun (clause reading : String) => ({ cls := "lawRefused", clause := some clause, object := some id, reading := some reading } : Refusal)
      let mayRemove := fun (placer : String) => placer == p.principal || ownerOf o.state == p.principal || openerActs w p.principal
      match x.what with
      | .verb =>
        if x.line.isEmpty then
          let some row := next.verbs.find? (·.name == x.name)
            | throw (refuse "unplaced" s!"{id} has no verb {x.name} that a hand grew.")
          unless mayRemove row.grower do
            throw (refuse "notPlacer" s!"only who grew verb {x.name}, or the owner of {id}, takes it off.")
          next := { next with verbs := next.verbs.filter (·.name != x.name) }
        else
          let bad := fun (reason : String) => ({ cls := "programRefused", clause := some "verb", object := some id, reason := some reason } : Refusal)
          unless verbWord x.name do
            throw (bad s!"a verb's name is one word of a to z, digits and -, at most {Limits.verbNameMax} long, not {x.name}")
          unless x.line.length ≤ Limits.verbReadingMax && !x.line.any (· == '\n') do
            throw (bad s!"a verb's reading is one line of at most {Limits.verbReadingMax} characters")
          unless verbTakes.contains x.takes do
            throw (bad s!"a verb takes text (a line) or nothing, not {x.takes}")
          unless next.offers actMethod do
            throw { cls := "noMethod", clause := some actMethod, object := some id,
                    reading := some s!"{id} has no act, so no verb grows on it." }
          if hostSpells.contains x.name || hostReads.contains x.name || verbsReserved.contains x.name ||
              (methodNames next).contains x.name then
            throw (refuse "nameTaken" s!"{id} already takes {x.name}; grow a verb whose name is new.")
          if next.verbs.any (·.name == x.name) then
            throw (refuse "nameTaken" s!"{x.name} is grown on {id} already; use it: delvetalk {id} {x.name}")
          unless x.does.isEmpty || p.placements.any (fun r => r.object == id && r.what == .rule && r.name == x.does && !r.line.isEmpty) do
            throw (bad s!"a verb does a rule placed with it; {x.does} is placed by no rule of this turn")
          if next.verbs.length ≥ Limits.verbsPerObject then
            throw { cls := "capacity", object := some id, reason := some "verbsPerObject" }
          next := { next with verbs := next.verbs ++ [{ name := x.name, grower := p.principal, height, reading := x.line,
                                                         takes := x.takes, does := x.does }] }
      | .rule | .want =>
        let want := x.what == .want
        let rows := if want then next.wants else next.rules
        if x.line.isEmpty then
          let some row := rows.find? (·.name == x.name)
            | throw (refuse "unplaced" s!"{id} has no {x.keyword} {x.name} that a hand placed.")
          unless mayRemove row.owner do
            throw (refuse "notPlacer" s!"only who placed {x.keyword} {x.name}, or the owner of {id}, takes it off.")
          next := if want then { next with wants := next.wants.filter (·.name != x.name) }
            else { next with rules := next.rules.filter (·.name != x.name) }
        else
          let clause ← match Delvetalk.Compiler.ObjectiveBendLaw.parseClause x.line with
            | .ok c => pure c
            | .error e => throw { cls := "programRefused", clause := some "law syntax", object := some id, reason := some e }
          unless clause.name == x.name && (if want then Law.isWant clause else Law.isRule clause) do
            throw { cls := "programRefused", clause := some "law syntax", object := some id,
                    reason := some s!"the line places {clause.name} as another modality than {x.keyword} {x.name}" }
          let names := (((parseClauses next.lawText).toOption.getD []).map (·.name)) ++ (next.rules ++ next.wants).map (·.name)
          if names.contains x.name then
            throw (refuse "nameTaken" s!"{id} already carries a clause {x.name}; place one whose name is new.")
          if let some message := citationRefusal cand id [(x.name, clause.condition)] then
            throw (refuse "under" ((message.drop "under: ".length).toString))
          -- A line reads, and its spell carries, only what its placer may view.
          if let some r := unviewable cand p.principal (citesOf cand clause.names).objects then
            throw (refuse "lawReads" s!"{x.keyword} {x.name} cites {r}, which you may not view.")
          if rows.length ≥ (if want then Limits.wantsPerObject else Limits.rulesPerObject) then
            throw { cls := "capacity", object := some id, reason := some (if want then "wantsPerObject" else "rulesPerObject") }
          let row : Placed := { name := x.name, owner := p.principal, since := height, line := clause.render, clause }
          next := if want then { next with wants := next.wants ++ [row] } else { next with rules := next.rules ++ [row] }
    -- A placing (rule, want, verb, or one taken off) is not a state move: the version roots judge, and a
    -- suspended turn rooted on the thing, stay where they were.
    let moves := changes.any (·.kind != 4)
    out := out ++ [(id, { next with version := if moves then o.version + 1 else o.version, cells })]
    factsOf := factsOf ++ [(id, judgedBy)]
  return { updates := out, reprograms, amendments, evicted := evictions, facts := factsOf,
           creations := p.creates.map fun (id, c) => (id, { c.object with madeFrom := c.madeFrom }),
           creates := p.creates.map fun (id, c) => createRecJson id c }

/-! ## Entries -/

/-- The card name for the speaker's own avatar (docs/GROUND.md §6 change 2): the object an arrival
    makes under the principal's own id (`arriveOp`), so a card may print `delvetalk me note` and
    never a DID. No object may take the id, so no one can stand in for another's own. -/
def meCard : String := "me"

/-- The object a principal means by `object`: `me` is its avatar, the object named by the principal itself. -/
def resolveCard (principal object : String) : String :=
  if object == meCard then principal else object

/-- The one object whose id folds to `id`'s fold; none when no object or several do. -/
def foldedId (w : World) (id : String) : Option String :=
  let key := Spell.fold id
  match w.objects.fold (fun acc k _ => if Spell.fold k == key then k :: acc else acc) [] with
  | [k] => some k
  | _ => none

/-- The principal under which a settled interpretation is journaled. -/
def interpretationPrincipal : String := "interpretation"

def identityJson (principal intent : String) : Json :=
  Json.mkObj [("principal", toJson principal), ("intent", toJson intent)]

/-- Append a sealed entry to the world. -/
def tagOf (entry : Json) : String :=
  match entry.getObjVal? "outcome" |>.bind (·.getObjValAs? String "tag") with
  | .ok tag => tag
  | .error _ => "unknown"

/-- Refusals a retry may outrun: a root moved, a machine budget ran out, an evaluation
    failed, a capacity was full (pending activities and interpretations drain; a capacity
    that never drains refuses the retry again). They are journaled but do not bind the
    identity's outcome. -/
def transientClasses : List String := ["staleRoot", "budget", "evaluation", "capacity", "quota", "quiet"]

/-- `bounds`: the kernel's bounds (`Delvetalk.Bounds`, and the generic instances a package may need), the
    host's (`Limits`) and the refusal classes, so no client or test restates one. -/
def bounds : Json :=
  Json.mkObj [("status", toJson "bounds"),
    ("kernel", Json.mkObj (natsIn% Delvetalk.Bounds ++ [("maxInstances", toJson Generics.maxInstances)])),
    ("host", Json.mkObj (natsIn% Delvetalk.Host.Limits)),
    ("refusalClasses", toJson refusalClasses), ("transientClasses", toJson transientClasses)]

def isTransient (entry : Json) : Bool :=
  tagOf entry == "refused" &&
    ((entry.getObjVal? "outcome").toOption.bind (·.getObjValAs? String "class" |>.toOption)).any transientClasses.contains

/-- The reservations after an entry: `reserved` adds one (a released intent reserved again counts a
    round), `released` and a `posted` naming an `intent` settle it. -/
def reservationsAfter (w : World) (entry : Json) : Std.HashMap String Reservation :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let intent := (outcome.getObjValAs? String "intent").toOption
  match tagOf entry, intent with
  | "reserved", some i =>
    let round := ((w.reservations[i]?).map (·.round + 1)).getD 0
    w.reservations.insert i { source := (outcome.getObjValAs? String "source").toOption.getD "",
                              hour := (outcome.getObjValAs? Nat "hour").toOption.getD 0, round }
  | "released", some i => match w.reservations[i]? with
    | some r => w.reservations.insert i { r with released := true }
    | none => w.reservations
  | "posted", some i => match w.reservations[i]? with
    | some r => w.reservations.insert i { r with posted := true }
    | none => w.reservations
  | _, _ => w.reservations

/-- The clock hour's counts after an entry (`world-status.hour`). -/
def hourAfter (w : World) (entry : Json) : HourCounts :=
  let hour := w.clock / 60
  let h := if w.hourCounts.hour == hour then w.hourCounts else { hour }
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  match tagOf entry with
  | "admitted" => { h with turns := h.turns + 1 }
  | "refused" =>
    let cls := (outcome.getObjValAs? String "class").toOption.getD "unknown"
    { h with turns := h.turns + 1,
             refused := if h.refused.any (·.1 == cls) then h.refused.map fun (c, n) => (c, if c == cls then n + 1 else n)
               else h.refused ++ [(cls, 1)] }
  | "suspended" =>
    let n := if (outcome.getObjVal? "interpretation").toOption.isSome then 1 else 0
    { h with turns := h.turns + 1, interpretations := h.interpretations + n }
  | "attempted" => { h with attempts := h.attempts + 1 }
  | _ => h

/-- Does an entry start a model call (an interpretation's suspension, or an attempt): what
    `modelQuota` counts per clock day. -/
def modelCall (entry : Json) : Bool :=
  tagOf entry == "attempted" || (tagOf entry == "suspended" &&
    ((entry.getObjVal? "outcome").toOption.bind (·.getObjVal? "interpretation" |>.toOption)).isSome)

/-- The act of a root entry (`kind`) or a moderation entry (`power`): one name for what `record`
    and `applyRoot` do with it. -/
def actOf (outcome : Json) : String :=
  ((outcome.getObjValAs? String "kind").toOption <|> (outcome.getObjValAs? String "power").toOption).getD ""

/-! ## Anchors: what each entry says an object is -/

/-- The rows of `k` in an entry's outcome that name `id`, in order. -/
def rowsNaming (outcome : Json) (k id : String) : Array Json :=
  (((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]).filter fun x =>
    (x.getObjValAs? String "object").toOption == some id

/-- Whether an entry is a genesis that installs a store (`Snapshot.installGenesis`): a fork's of a
    principal's view, a carry's of a whole world. -/
def installsStore (entry : Json) : Bool := tagOf entry == "forked" || tagOf entry == "carried"

/-- A store-installing genesis's origin, under the name its tag gives it: `forkedFrom {world, height, cid}`
    or `carriedFrom {world, height, cid, replay, reason, entries, carriedFrom?}`. The entry's `previous`
    is the origin's `cid`. -/
def genesisOrigin (entry : Json) : Option (String × Json) :=
  let key := if tagOf entry == "carried" then "carriedFrom" else "forkedFrom"
  if !installsStore entry then none else
  ((entry.getObjVal? "outcome").toOption.bind (·.getObjVal? key |>.toOption)).map (key, ·)

/-- An origin as `world-status` shows it: a carry's index of the old chain's entries left out, at every
    generation (a carried world's origin names the origin of the world it carried, when that was a carry). -/
partial def originShown (origin : Json) : Json :=
  Json.mkObj (((origin.getObj?.toOption.map (·.toList)).getD []).filterMap fun (k, v) =>
    if k == "entries" then none else if k == "carriedFrom" then some (k, originShown v) else some (k, v))

/-- A carried genesis's old chains, newest generation first: each entry hash with its height in that
    world and that world's origin (`carriedFrom`, which names the generation before when it was a carry). -/
partial def carriedEntries (entry : Json) : Array (String × Nat × Json) :=
  let rec walk (origin : Json) : Array (String × Nat × Json) :=
    let mine := (((origin.getObjVal? "entries").toOption.bind (·.getObj?.toOption)).map fun m =>
      m.toList.foldl (fun (acc : Array (String × Nat × Json)) (h, v) => match v.getNat? with
        | .ok n => acc.push (h, n, origin)
        | .error _ => acc) #[]).getD #[]
    mine ++ (((origin.getObjVal? "carriedFrom").toOption.map walk).getD #[])
  match genesisOrigin entry with
  | some ("carriedFrom", origin) => walk origin
  | _ => #[]

/-- The object rows of a store-installing genesis that name `id`. -/
def genesisRow (outcome : Json) (id : String) : Option Json :=
  ((outcome.getObjVal? "state").toOption.bind (·.getObjVal? "objects" |>.toOption) |>.bind (·.getArr?.toOption)).bind
    fun os => os.find? fun o => (o.getObjValAs? String "id").toOption == some id

/-- The rules and wants hands placed on an object and the verbs they grew, as one value: what a placing,
    a creation and a store-installing genesis commit to (`placedIn`), so a snapshot's rows rest on the
    journal as its state does on a write's `cid`. -/
def placedRows (rules wants verbs : Json) : Json :=
  Json.mkObj [("rules", rules), ("wants", wants), ("verbs", verbs)]

def placedCid (o : Object) : String :=
  Journal.bodyHash (placedRows (Json.arr (o.rules.toArray.map (·.json))) (Json.arr (o.wants.toArray.map (·.json)))
    (Json.arr (o.verbs.toArray.map (·.json))))

/-- An object with nothing placed or grown on it. -/
def Object.unplaced (o : Object) : Bool := o.rules.isEmpty && o.wants.isEmpty && o.verbs.isEmpty

/-- `placed [{object, cid}]` of an admitted entry: each written or created object whose placed rows the
    entry changed or made, with their CID (`placedCid`). Replay compares it when the entry has it. -/
def placedField (before : World) (objects : List (String × Object)) : List (String × Json) :=
  let rows := objects.filterMap fun (id, o) =>
    let was := (before.objects[id]?).map placedCid
    if was == some (placedCid o) || (was.isNone && o.unplaced) then none
    else some (Json.mkObj [("object", toJson id), ("cid", toJson (placedCid o))])
  if rows.isEmpty then [] else [("placed", Json.arr rows.toArray)]

/-- The version the entry gives `id`, when it sets one: a creation's 0, a write's, a root `set`'s, a
    fork genesis's. -/
def versionIn (entry : Json) (id : String) : Option Nat :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let named := (outcome.getObjValAs? String "object").toOption == some id
  match tagOf entry with
  | "created" => if named then some 0 else none
  | "admitted" =>
    match (rowsNaming outcome "writes" id).back? with
    | some x => (x.getObjValAs? Nat "version").toOption
    | none => if (rowsNaming outcome "creates" id).isEmpty then none else some 0
  | "root" =>
    if !named || actOf outcome != "set" then none
    else if (outcome.getObjValAs? String "field").toOption == some "version" then
      (outcome.getObjVal? "after").toOption.bind (·.getNat?.toOption)
    else (outcome.getObjValAs? Nat "version").toOption
  | "forked" | "carried" => (genesisRow outcome id).bind (·.getObjValAs? Nat "version" |>.toOption)
  | _ => none

/-- The pin the entry gives `id`, when it sets one: a creation's, a reprogram's, a root `set` of the
    pin or the program, a store-installing genesis's. -/
def pinIn (entry : Json) (id : String) : Option String :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let named := (outcome.getObjValAs? String "object").toOption == some id
  match tagOf entry with
  | "created" => if named then (outcome.getObjValAs? String "pin").toOption else none
  | "admitted" =>
    match (rowsNaming outcome "reprograms" id).back? with
    | some r => (r.getObjValAs? String "newPin").toOption
    | none => (rowsNaming outcome "creates" id).back?.bind (·.getObjValAs? String "pin" |>.toOption)
  | "root" =>
    if !named || actOf outcome != "set" then none else
    match (outcome.getObjValAs? String "field").toOption with
    | some "pin" => (outcome.getObjVal? "after").toOption.bind (·.getStr?.toOption)
    | some "program" => (outcome.getObjValAs? String "pin").toOption
    | _ => none
  | "forked" | "carried" => (genesisRow outcome id).bind (·.getObjValAs? String "pin" |>.toOption)
  | _ => none

/-- The law text the entry gives `id`, when it sets one: a creation's, an amendment's, a root `set` of
    the law, a `retire` or `unretire`, a store-installing genesis's. -/
def lawIn (entry : Json) (id : String) : Option String :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let named := (outcome.getObjValAs? String "object").toOption == some id
  let after := (outcome.getObjVal? "after").toOption.bind (·.getStr?.toOption)
  match tagOf entry with
  | "created" => if named then (outcome.getObjValAs? String "lawText").toOption else none
  | "admitted" =>
    match (rowsNaming outcome "amendments" id).back? with
    | some a => (a.getObjValAs? String "new").toOption
    | none => (rowsNaming outcome "creates" id).back?.bind (·.getObjValAs? String "law" |>.toOption)
  | "root" | "moderated" =>
    if !named then none else
    match actOf outcome with
    | "set" => if (outcome.getObjValAs? String "field").toOption == some "law" then after else none
    | "retire" | "unretire" => after
    | _ => none
  | "forked" | "carried" => (genesisRow outcome id).bind (·.getObjValAs? String "law" |>.toOption)
  | _ => none

/-- The CID of `id`'s placed rows the entry commits to: a placing's or creation's `placed`, a store-installing
    genesis's rows. -/
def placedIn (entry : Json) (id : String) : Option String :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  match tagOf entry with
  | "created" => if (outcome.getObjValAs? String "object").toOption == some id then (outcome.getObjValAs? String "placed").toOption else none
  | "admitted" => (rowsNaming outcome "placed" id).back?.bind (·.getObjValAs? String "cid" |>.toOption)
  | "forked" | "carried" => (genesisRow outcome id).map fun o =>
    let rows := fun (k : String) => (o.getObjVal? k).toOption.getD (Json.arr #[])
    Journal.bodyHash (placedRows (rows "rules") (rows "wants") (rows "verbs"))
  | _ => none

/-- The read policy the entry gives `id`: a creation's, a root `set` of it, `hide` or `show`, a
    store-installing genesis's. -/
def readPolicyIn (entry : Json) (id : String) : Option Json :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let named := (outcome.getObjValAs? String "object").toOption == some id
  match tagOf entry with
  | "created" => if named then (outcome.getObjVal? "read").toOption else none
  | "admitted" => (rowsNaming outcome "creates" id).back?.bind (·.getObjVal? "read" |>.toOption)
  | "root" | "moderated" =>
    if !named then none else
    match actOf outcome with
    | "set" => if (outcome.getObjValAs? String "field").toOption == some "read" then (outcome.getObjVal? "after").toOption else none
    | "hide" | "show" => (outcome.getObjVal? "after").toOption
    | _ => none
  | "forked" | "carried" => (genesisRow outcome id).bind (·.getObjVal? "read" |>.toOption)
  | _ => none

/-- How a journal names an object's state. From replay edition 10, the CID of its cells' block
    (`Object.stateCid`), journaled as `cid` on every creation, write and root `set`, and as a genesis
    row's `stateCid`; before it, the CID of the state's wire JSON, a creation named by its seed's. A
    carry reads a world of an earlier edition by that edition's naming (`Naming.ofEdition`). -/
structure Naming where
  state : Object → String
  seed : Json → Option String

def Naming.cells : Naming := ⟨Object.stateCid, fun _ => none⟩

def Naming.ofEdition (edition : Nat) : Naming :=
  if edition < 10 then ⟨fun o => Journal.bodyHash (dataJson o.state), fun seed => some (Journal.bodyHash seed)⟩
  else Naming.cells

/-- The state CID the entry names for `id` at `version`: a creation's `cid` (an earlier edition's
    seed's, by `naming`), a write's `cid`, a root `set`'s, a store-installing genesis's `stateCid`; none
    when it names none. -/
def stateCidIn (entry : Json) (id : String) (version : Nat) (naming : Naming := .cells) : Option String :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let named := (outcome.getObjValAs? String "object").toOption == some id
  let created := fun (j : Json) => (j.getObjValAs? String "cid").toOption <|> ((j.getObjVal? "seed").toOption.bind naming.seed)
  match tagOf entry with
  | "created" => if version == 0 && named then created outcome else none
  | "admitted" =>
    match ((rowsNaming outcome "writes" id).filter fun x => (x.getObjValAs? Nat "version").toOption == some version).back? with
    | some x => (x.getObjValAs? String "cid").toOption
    | none => if version != 0 then none else (rowsNaming outcome "creates" id).back?.bind created
  | "root" =>
    if named && (outcome.getObjValAs? Nat "version").toOption == some version then (outcome.getObjValAs? String "cid").toOption else none
  | "forked" | "carried" => (genesisRow outcome id).bind (·.getObjValAs? String "stateCid" |>.toOption)
  | _ => none

/-- The objects an entry may say something of. -/
def objectsNamed (entry : Json) : List String :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let ids := fun (k : String) => (((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap
    fun x => (x.getObjValAs? String "object").toOption
  let installed := (((outcome.getObjVal? "state").toOption.bind (·.getObjVal? "objects" |>.toOption) |>.bind (·.getArr?.toOption)).getD #[]).toList.filterMap
    fun o => (o.getObjValAs? String "id").toOption
  (((outcome.getObjValAs? String "object").toOption.toList ++ ids "writes" ++ ids "creates" ++ ids "reprograms" ++
    ids "amendments" ++ ids "placed" ++ installed)).eraseDups

/-- `World.anchors` after the entry at `height`: each object it gives a version, a pin or a law is
    anchored there for that; a root `delete` forgets the object. -/
def anchorsAfter (w : World) (height : Nat) (entry : Json) : Std.HashMap String Anchor :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  if tagOf entry == "root" && actOf outcome == "delete" then
    w.anchors.erase ((outcome.getObjValAs? String "object").toOption.getD "")
  else (objectsNamed entry).foldl (fun m id =>
    let a := m.getD id {}
    let a := if (versionIn entry id).isSome then { a with version := height } else a
    let a := if (pinIn entry id).isSome then { a with pin := height } else a
    let a := if (lawIn entry id).isSome then { a with law := height } else a
    let a := if (placedIn entry id).isSome then { a with placed := height } else a
    let a := if (readPolicyIn entry id).isSome then { a with read := height } else a
    if a == m.getD id {} then m else m.insert id a) w.anchors

/-- The indexes a root or moderation entry moves (docs/ROOT.md §1.3: rebuilt as `record` rebuilds
    them), the clock hour's counts, and the day's model calls. The store's half is `applyRoot`. -/
def recordActs (w : World) (entry : Json) : World := Id.run do
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let day := w.clock / Limits.clockDay
  let mut w := { w with hourCounts := hourAfter w entry,
                        modelDay := if !modelCall entry then w.modelDay
                          else if w.modelDay.1 == day then (day, w.modelDay.2 + 1) else (day, 1) }
  let tag := tagOf entry
  unless tag == "root" || tag == "moderated" do return w
  if tag == "root" then w := { w with rootActs := w.rootActs + 1 }
  let text := fun (k : String) => (outcome.getObjValAs? String k).toOption.getD ""
  let after := (outcome.getObjVal? "after").toOption.getD Json.null
  match actOf outcome with
  | "card" =>
    w := { w with cards := match after.getStr? with
      | .ok t => w.cards.insert (text "object") t
      | .error _ => w.cards.erase (text "object") }
  | "ignore" | "unignore" =>
    let h := (outcome.getObjValAs? Nat "height").toOption.getD 0
    w := { w with ignored := if actOf outcome == "ignore" then (w.ignored.erase h) ++ [h] else w.ignored.erase h }
  | "settings" =>
    if let .ok c := after.getObjValAs? Nat "clock" then w := { w with clock := c }
  | "quiet" =>
    let who := text "principal"
    match after.getObjValAs? Nat "until", after.getObjValAs? String "reading" with
    | .ok u, .ok r => w := { w with quiets := w.quiets.insert who (u, r) }
    | _, _ => w := { w with quiets := w.quiets.erase who }
  | "hide" =>
    let id := text "object"
    unless w.hidden.contains id do
      w := { w with hidden := w.hidden.insert id ((outcome.getObjVal? "before").toOption.getD Json.null) }
  | "show" => w := { w with hidden := w.hidden.erase (text "object") }
  | "set" =>
    let id := text "object"
    match text "field" with
    | "activities" =>
      let kept := ((after.getArr?.toOption).getD #[]).toList.filterMap (·.getStr?.toOption)
      let keep := fun (s : Json) =>
        let obj := (s.getObjVal? "outcome").toOption.bind (·.getObjVal? "activity" |>.toOption)
          |>.bind (·.getObjValAs? String "object" |>.toOption)
        obj != some id || kept.contains ((s.getObjValAs? String "hash").toOption.getD "")
      w := { w with suspended := w.suspended.filter keep }
    | "state" | "owner" =>
      -- A root write of state is a write whose edits nobody knows: a root read before it is stale.
      if let .ok v := outcome.getObjValAs? Nat "version" then
        w := { w with touches := w.touches.insert id ((w.touches.getD id #[]).push { version := v, height := w.height }),
                      changes := w.changes.push { height := w.height, object := id, version := v,
                                                  principal := (entry.getObjVal? "identity" >>= (·.getObjValAs? String "principal")).toOption.getD "" } }
    | _ => pure ()
  | _ => pure ()
  return w

/-- An entry replay treats as refused (`ignore`) or skips because it no longer holds (shadowed): in
    the chain, its sources and blocks known (they are content, not effects), nothing else. -/
def recordInert (w : World) (entry : Json) : World :=
  let sources := (entrySources entry).toOption.getD []
  { w with height := w.height + 1, head := (entry.getObjValAs? String "hash").toOption.getD "",
           modules := sources.foldl (fun m (x : String × String) => m.insert x.1 w.height) w.modules,
           blocks := ((entryBlocks entry).toOption.getD []).foldl (fun m (x : String × Array Json) => m.insert x.1 w.height) w.blocks }

def ledgerOf (j : Json) : Except String Ledger := do
  return ⟨← natField j "depth", ← natField j "work", ← natField j "storage"⟩

/-- A send to another world (`world` on it), which `serve` carries (`outbound`) unless its ledger is spent:
    a spent one is refused where it was sent. -/
def crossesOver (p : Json) : Bool :=
  (p.getObjValAs? String "world").toOption.any (!·.isEmpty) &&
    ((p.getObjVal? "ledger").toOption.bind fun l => (ledgerOf l).toOption.bind (·.exhausted)).isNone

/-- A pending send ready to deliver here: not one crossing over, and not one a transient refusal put back
    until the clock passes it. -/
def deliverable (w : World) (p : Json) : Bool :=
  !crossesOver p && ((p.getObjValAs? Nat "next").toOption.map fun n => decide (n ≤ w.clock)).getD true

/-- A send whose delivery was refused transiently, put back to be delivered again once the clock moves,
    unless that was its last attempt (`Limits.deliveryAttempts`). -/
def redelivered (w : World) (entry : Json) (id : String) : Option Json := do
  guard (isTransient entry)
  let p ← w.pending.find? fun p => (p.getObjValAs? String "id").toOption == some id
  let attempts := ((p.getObjValAs? Nat "attempts").toOption.getD 0) + 1
  guard (attempts < Limits.deliveryAttempts)
  return (p.setObjVal! "attempts" (toJson attempts)).setObjVal! "next" (toJson (w.clock + 1))

/-- The thing whose law refused an entry (its outcome `lawRefused`, naming it): `World.refusedBy` counts it. -/
def lawRefusedOf (outcome : Json) : Option String :=
  if (outcome.getObjValAs? String "tag").toOption == some "refused" &&
      (outcome.getObjValAs? String "class").toOption == some "lawRefused"
  then (outcome.getObjValAs? String "object").toOption else none

/-- An admitted entry's rows of `k` (`fired`, `unfired`, `wanted`, `unwanted`). -/
def reactionRows (entry : Json) (k : String) : Array Json :=
  if tagOf entry != "admitted" && tagOf entry != "refused" then #[] else ((entry.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]

/-- Each rule's last firing or refusal to fire after an entry (`World.ruleLog`). -/
def ruleLogAfter (w : World) (entry : Json) : Std.HashMap String (List (String × Json)) :=
  let height := w.height + 1
  let note := fun (log : Std.HashMap String (List (String × Json))) (object rule : String) (j : Json) =>
    log.insert object (((log.getD object []).filter (·.1 != rule)) ++ [(rule, j)])
  let log := (reactionRows entry "fired").foldl (fun log f =>
    match f.getObjValAs? String "sender", f.getObjValAs? String "rule", f.getObjValAs? String "id" with
    | .ok o, .ok r, .ok id => note log o r (Json.mkObj [("height", toJson height), ("id", toJson id)])
    | _, _, _ => log) w.ruleLog
  (reactionRows entry "unfired").foldl (fun log f =>
    match f.getObjValAs? String "object", f.getObjValAs? String "rule", f.getObjValAs? String "why" with
    | .ok o, .ok r, .ok why => note log o r (Json.mkObj [("height", toJson height), ("why", toJson why)])
    | _, _, _ => log) log

/-- The wants holding after an entry, with the height that made each true (`World.wanting`). -/
def wantingAfter (w : World) (entry : Json) : Std.HashMap String (List (String × Nat)) :=
  let pairs := fun (k : String) => (reactionRows entry k).toList.filterMap fun x =>
    match x.getObjValAs? String "object", x.getObjValAs? String "want" with
    | .ok o, .ok n => some (o, n)
    | _, _ => none
  let gone := (pairs "unwanted").foldl (fun m (o, n) => m.insert o ((m.getD o []).filter (·.1 != n))) w.wanting
  (pairs "wanted").foldl (fun m (o, n) => m.insert o ((m.getD o []).filter (·.1 != n) ++ [(n, w.height + 1)])) gone

def recordCore (w : World) (entry : Json) (key : String) (touch : List String) : World :=
  let hash := (entry.getObjValAs? String "hash").toOption.getD ""
  let index := w.height
  let delivered := (entry.getObjVal? "delivery").toOption.bind fun d => (d.getObjValAs? String "id").toOption
  let identity := (entry.getObjVal? "identity").toOption.getD Json.null
  let sent := match (entry.getObjVal? "outcome").toOption.bind (fun o => (o.getObjValAs? String "tag").toOption),
      (entry.getObjVal? "sends").toOption.bind (·.getArr?.toOption) with
    | some tag, some sends => if tag != "admitted" && tag != "relayed" then #[] else sends.map fun s =>
        -- A send under a grant is delivered as its grantor (the send's own `principal`).
        let fields := s.getObj?.toOption.map (·.toList) |>.getD []
        Json.mkObj ([("from", identity)] ++
          (if fields.any (·.1 == "principal") then [] else
            [("principal", (identity.getObjVal? "principal").toOption.getD Json.null)]) ++ fields)
    | _, _ => #[]
  -- The rules an admitted write fired, run under their owners, the written object their sender.
  let fired := (reactionRows entry "fired").map fun f =>
    Json.mkObj ([("from", identity)] ++ ((f.getObj?.toOption.map (·.toList)).getD []))
  let sources := (entrySources entry).toOption.getD []
  -- Offers of an admitted entry are retained for their addressees.
  let offered := if tagOf entry != "admitted" then #[] else
    (((entry.getObjVal? "offers").toOption.bind (·.getArr?.toOption)).getD #[]).zipIdx.filterMap fun (o, i) =>
      (o.getObjValAs? String "to").toOption.map (·, i)
  let publications := if tagOf entry != "admitted" then #[] else
    (((entry.getObjVal? "publishes").toOption.bind (·.getArr?.toOption)).getD #[]).zipIdx.map fun (_, i) => (index, i)
  { w with
    published := w.published ++ publications
    outbox := offered.foldl (fun box (to, i) => box.insert to ((box.getD to #[]).push (index, i))) w.outbox
    modules := sources.foldl (fun m (x : String × String) => m.insert x.1 index) w.modules
    blocks := ((entryBlocks entry).toOption.getD []).foldl (fun m (x : String × Array Json) => m.insert x.1 index) w.blocks
    pending := (match delivered with
      | some id => (w.pending.filter fun p => (p.getObjValAs? String "id").toOption != some id) ++
          ((redelivered w entry id).map (#[·])).getD #[]
      | none => w.pending) ++ sent ++ fired ++
      -- An activity's end told to its object's supervisor, whatever the entry's outcome.
      (((entry.getObjVal? "ended").toOption.map fun e =>
        #[Json.mkObj ([("from", identity), ("principal", (identity.getObjVal? "principal").toOption.getD Json.null)] ++
          ((e.getObj?.toOption.map (·.toList)).getD []))]).getD #[])
    height := w.height + 1, head := hash
    handles := if tagOf entry == "principal" then
        match (entry.getObjVal? "outcome").toOption with
        | some o => match o.getObjValAs? String "did", o.getObjValAs? String "handle" with
          | .ok did, .ok "" => w.handles.erase did
          | .ok did, .ok handle => w.handles.insert did handle
          | _, _ => w.handles
        | none => w.handles
      else w.handles
    reservations := reservationsAfter w entry
    attempts := if tagOf entry != "attempted" then w.attempts else
      match (entry.getObjVal? "outcome").toOption with
      | some o => match o.getObjValAs? String "id", o.getObjValAs? Nat "attempt", o.getObjValAs? Nat "next" with
        | .ok id, .ok n, .ok next => w.attempts.insert id (n, next)
        | _, _, _ => w.attempts
      | none => w.attempts
    interpretsStarted := if tagOf entry != "suspended" then w.interpretsStarted else
      match (entry.getObjVal? "outcome").toOption.bind (·.getObjVal? "interpretation" |>.toOption),
          (entry.getObjVal? "identity").toOption.bind (·.getObjValAs? String "principal" |>.toOption) with
      | some _, some p =>
        let hour := w.clock / 60
        let (h, n) := w.interpretsStarted.getD p (hour, 0)
        w.interpretsStarted.insert p (hour, if h == hour then n + 1 else 1)
      | _, _ => w.interpretsStarted
    clock := if tagOf entry == "advanced" then (entry.getObjVal? "outcome" |>.bind (·.getObjValAs? Nat "to")).toOption.getD w.clock else w.clock
    suspended := (match (entry.getObjValAs? String "resumes").toOption with
        | some h => w.suspended.filter fun s => (s.getObjValAs? String "hash").toOption != some h
        | none => w.suspended) ++ (if tagOf entry == "suspended" then #[entry] else #[])
    -- A suspended identity is not settled, nor one refused transiently: its next entry takes
    -- over the receipt.
    receipts := match w.receipts[key]? with
      | none => w.receipts.insert key index
      | some i => if (w.entries.get? i).all fun e => tagOf e == "suspended" || isTransient e then w.receipts.insert key index
          else w.receipts
    touched := touch.foldl (fun t id => t.insert id ((t.getD id #[]).push index)) w.touched
    ruleLog := ruleLogAfter w entry
    wanting := wantingAfter w entry
    refusedBy := match (entry.getObjVal? "outcome").toOption.bind lawRefusedOf with
      | some id => w.refusedBy.insert id (w.refusedBy.getD id 0 + 1)
      | none => w.refusedBy
    days := if (w.days.back?.map (·.1)) == some (w.clock / Limits.clockDay) then w.days
      else w.days.push (w.clock / Limits.clockDay, index + 1)
    touches := if tagOf entry != "admitted" then w.touches else
      (touchesOf (index + 1) entry).foldl (fun t (id, x) => t.insert id ((t.getD id #[]).push x)) w.touches
    changes := w.changes ++ changesOf (w.height + 1) entry
    anchors := anchorsAfter w (w.height + 1) entry }

def record (w : World) (entry : Json) (key : String) (touch : List String) : World :=
  recordActs (recordCore w entry key touch) entry

/-- The facts a want of `o` (`id`) is judged and filled by, as `w` holds it at `height`: the clock, the
    thing, the states its lines cite and the wants they name (`Law.asItStands` keeps only these). -/
def wantFacts (w : World) (height : Nat) (id : String) (o : Object) : Law.Facts :=
  citing w o.law ((carriedWants w id o).flatMap (·.clause.names))
    { subject := "", caller := "", height, turn := height, clock := w.clock, object := id }

/-- The wants of `o` (`id`) that hold of its state as it stands in `w`, at its clock, each with its
    clause: the want's condition judged with what the thing's lines cite as `w` holds them. -/
def posing (w : World) (height : Nat) (id : String) (o : Object) : List CarriedClause :=
  let facts := wantFacts w height id o
  (carriedWants w id o).filter fun c => !(Law.poses facts id o.state [c.clause]).isEmpty

/-- `{object, want}` rows for the wants of `id` that hold `now` and did not before (`was`), and the reverse. -/
def wantFlips (id : String) (was now : List String) : Array Json × Array Json :=
  let row := fun (n : String) => Json.mkObj [("object", toJson id), ("want", toJson n)]
  ((now.filter (!was.contains ·)).toArray.map row, (was.filter (!now.contains ·)).toArray.map row)

/-- An entry's `wanted` and `unwanted` fields, each only when it holds a row. -/
def flipFields (wanted unwanted : Array Json) : List (String × Json) :=
  (if wanted.isEmpty then [] else [("wanted", Json.arr wanted)]) ++
    (if unwanted.isEmpty then [] else [("unwanted", Json.arr unwanted)])

/-- The wants a law's refusal opens and closes on the thing it refused (`lawRefusedOf`), whose
    `request.refusedBy` it moves by one, at the clock: journaled by `push` on every such entry, as
    `reactions` journals an admitted write's, and re-derived by replay. -/
def refusalWants (w : World) (outcome : Json) : List (String × Json) :=
  match (lawRefusedOf outcome).bind fun id => (w.objects[id]?).map (id, ·) with
  | none => []
  | some (id, o) =>
    let after := { w with refusedBy := w.refusedBy.insert id (w.refusedBy.getD id 0 + 1) }
    let (wanted, unwanted) := wantFlips id ((posing w (w.height + 1) id o).map (·.clause.name))
      ((posing after (w.height + 1) id o).map (·.clause.name))
    flipFields wanted unwanted

/-- Seal and record the world's next entry. A law's refusal carries the wants it flips (`refusalWants`). -/
def push (w : World) (key : String) (fields : List (String × Json)) (touch : List String) :
    World × Json :=
  let fields := fields ++ refusalWants w ((fields.lookup "outcome").getD Json.null)
  let entry := Journal.sealEntry (w.height + 1) w.head fields
  (record { w with entries := w.entries.push entry } entry key touch, entry)

def statusOf (entry : Json) : String :=
  match entry.getObjVal? "outcome" |>.bind (·.getObjValAs? String "tag") with
  | .ok tag => tag
  | .error _ => "unknown"

/-- A receipt as a reply shows it: the entry with `slug` beside `hash`, the name a person cites
    (`Slug`); the journal holds only the hash. -/
def slugged (entry : Json) : Json :=
  match (entry.getObjValAs? String "hash").toOption.bind Slug.ofCid with
  | some s => entry.setObjVal! "slug" (toJson s)
  | none => entry

def reply (entry : Json) : Json :=
  Json.mkObj [("status", toJson (statusOf entry)), ("receipt", slugged entry)]

def duplicate (principal intent : String) (entry : Json) : Json :=
  Json.mkObj [("status", toJson "refused"), ("class", toJson "duplicateIdentity"),
    ("identity", identityJson principal intent),
    ("reason", toJson s!"{intent} already names a different turn; choose a new intent."),
    ("original", entry.getObjVal? "hash" |>.toOption |>.getD Json.null)]

/-- What binds an identity, as a carry keeps it (`World.carriedIds`): the identity, its request digests,
    the entry's hash and height in its chain, and its outcome's tag and class. `reply`, `duplicate` and
    `isTransient` read it as they read the entry. -/
def identityRow (entry : Json) : Json :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  Json.mkObj ((["identity", "request", "turnRequest", "hash", "height"].filterMap fun k => (entry.getObjVal? k).toOption.map (k, ·)) ++
    [("outcome", Json.mkObj ((["tag", "class"].filterMap fun k => (outcome.getObjVal? k).toOption.map (k, ·))))])

/-- The bindings a `carried` genesis keeps (`identities`), by identity key. -/
def carriedIdentities (genesis : Json) : Std.HashMap String Json :=
  if tagOf genesis != "carried" then {} else
  ((((genesis.getObjVal? "outcome").toOption.bind (·.getObjVal? "identities" |>.toOption)).bind (·.getArr?.toOption)).getD #[]).foldl
    (fun (m : Std.HashMap String Json) row =>
      let who := fun (k : String) => (row.getObjVal? "identity").toOption.bind (·.getObjValAs? String k |>.toOption)
      match who "principal", who "intent" with
      | some p, some i => m.insert (identityKey p i) row
      | _, _ => m) {}

/-- The entry an identity is bound to: this chain's (`receipts`), else the one a carry kept (`carriedIds`). -/
def boundEntry (w : World) (principal intent : String) : Option Json :=
  match w.receipts[identityKey principal intent]? with
  | some index => some (w.entries.getD index)
  | none => w.carriedIds[identityKey principal intent]?

/-- Retry rule shared by every journaled op: the same identity and request returns
    the retained receipt without an entry; the same identity with another request
    is `duplicateIdentity` and is not journaled (the identity is already bound). An identity
    the world before a carry bound is bound here as there. -/
def retained (w : World) (principal intent digest : String) : Option Json :=
  match boundEntry w principal intent with
  | none => none
  | some entry =>
    let same := (entry.getObjValAs? String "request").toOption == some digest
    if tagOf entry == "suspended" then none
    -- A transient refusal does not bind the identity: the retry runs (and is judged) again.
    else if isTransient entry then none
    else if same then some (reply entry)
    else some (duplicate principal intent entry)

/-- The id of the `ordinal`th send of the turn with this identity. -/
def deliveryId (principal intent : String) (ordinal : Nat) : String :=
  Journal.bodyHash (Json.arr #[toJson principal, toJson intent, toJson ordinal])

/-- The ledger a turn's sends and changes inherit: depth - 1, work - the ticks it used, storage -
    the canonical bytes of the cells its writes changed (`cellBytes`; every cell of an object it
    created). -/
def childLedger (w : World) (ledger : Ledger) (used : Nat) (updates : List (String × Object))
    (writes : List (String × List Written)) : Ledger :=
  let added := updates.foldl (fun n (id, o) => n + chargedBytes w.objects[id]? o ((writes.lookup id).getD [])) 0
  ⟨ledger.depth - 1, ledger.work - used, ledger.storage - added⟩

/-! ## Supervision -/

/-- The id of the `ended` delivery an entry at `height` sends. -/
def endedId (principal intent : String) (height : Nat) : String :=
  Journal.bodyHash (Json.arr #[toJson "ended", toJson principal, toJson intent, toJson height])

/-- The receipt an entry is, as `Plan.obend`'s `Receipt` on the wire. -/
def receiptOf (principal intent : String) (height : Nat) (outcome : Json) : Data :=
  let text := fun (k : String) => (outcome.getObjValAs? String k).toOption.getD ""
  .record [("slot", .record [("principal", .label principal), ("intent", .label intent)]),
    ("height", .natural height),
    ("outcome", if text "tag" == "refused" then .variant "refused" (.record [("class", .label (text "class")), ("root", .label (text "object"))])
      else .variant "admitted" (.record [])),
    -- The entry that carries this receipt is the one being sealed: its hash is not known inside it.
    ("hash", .label "")]

/-- The `ended` field of an entry: a delivery of `ended {receipt, how}` to the supervisor of
    `object`, under the ledger the activity ran with, one level deeper and less the work it
    spent. Nothing when the object has no supervisor (or it is gone). -/
def endedField (w : World) (object principal intent how : String) (ledger : Ledger) (used : Nat)
    (height : Nat) (outcome : Json) : List (String × Json) :=
  match (w.objects[object]?).map (·.supervisor) with
  | some sup =>
    if sup.isEmpty || !w.objects.contains sup then [] else
    let child : Ledger := ⟨ledger.depth - 1, ledger.work - used, ledger.storage⟩
    let argument := Data.record [("receipt", receiptOf principal intent height outcome), ("how", .label how)]
    [("ended", Json.mkObj [("id", toJson (endedId principal intent height)), ("to", toJson sup),
      ("method", toJson "ended"), ("argument", dataJson argument), ("sender", toJson object),
      ("ledger", child.json)])]
  | none => []

/-! ## What a write sets off and opens (docs/OVERHAUL.md §3 "Commit"; FOUNDATION §10; FOUNDATION §5) -/

/-- The delivery id, and the delivered turn's intent, of rule `name` of `object` fired at `height`. -/
def ruleDeliveryId (object name : String) (height : Nat) : String := s!"rule:{object}:{name}:{height}"

/-- How many rule firings deep the turn an entry delivers is: the `depth` its pending send carries (a
    rule's firing), 0 for a direct turn or another send. -/
def ruleDepthOf (w : World) (delivery : Option String) : Nat :=
  ((delivery.bind fun id => w.pending.find? fun d => (d.getObjValAs? String "id").toOption == some id).bind
    fun d => (d.getObjValAs? Nat "depth").toOption).getD 0

/-- The card a filled spell line names, as its owner would resolve it (`me` their avatar, a name folded
    to the one object it names), or none when the line is not a spell. -/
def spellCard (w : World) (owner text : String) : Option String :=
  match Spell.parse text with
  | .spell card _ _ =>
    let card := if Spell.fold card == meCard then meCard else card
    let id := resolveCard owner card
    some (if w.objects.contains id then id else (foldedId w id).getD id)
  | _ => none

/-- What an admitted write sets off and opens, as the entry journals it and replay re-derives it:

    - `fired`: for each written object in order, each rule it carries (`carried`, after the write)
      whose condition the write makes hold under any of the facts its law judged the write by
      (`Judged.facts`), its spell filled at the write (`Law.fill`), staged as a delivery of `receive
      {text}` to the card the line names, run under the rule's owner (`me` their avatar) with the
      ledger the turn's sends inherit, one firing deeper (`text` the line, `post` "": no post carries
      it): `{id: rule:<object>:<name>:<height>, to,
      method, argument, sender: object, principal: owner, ledger, rule, depth}`;
    - `unfired`: `{object, rule, owner, why}` for a rule that held and was not cast: `hole` (a hole read
      nothing), `spell` (the filled line is not a spell), `noOwner`, `quiet` (its owner is quieted),
      `ruleDepth` (the chain is `Limits.ruleDepth` firings deep), `rulesPerCommit` (that many fired),
      `pending` (the world holds `Limits.maxPending` undelivered sends), `reads` (its owner may not
      view the thing or an object its condition or holes cite);
    - `wanted`, `unwanted`: `{object, want}` for each want that holds of the object as it stands after
      the write and did not before (a created object had none), and the reverse, at the clock. -/
def reactions (before after : World) (height : Nat) (judged : Judged) (child : Ledger) (depth : Nat) :
    List (String × Json) := Id.run do
  let mut fired : Array Json := #[]
  let mut unfired : Array Json := #[]
  for (id, o) in judged.updates do
    let some old := before.objects[id]? | continue
    let rules := carriedRules after id o
    if rules.isEmpty then continue
    let names := rules.flatMap (·.clause.names)
    let cite := citing after o.law names
    let (oldState, newState) := (viewFor names old.cells, viewFor names o.cells)
    for r in rules do
      let held := ((judged.facts.lookup id).getD []).find? fun f =>
        !(Law.fires (cite f) (some oldState) newState [r.clause]).isEmpty
      let some f := held | continue
      let facts := cite f
      let refuse := fun (why : String) => Json.mkObj [("object", toJson id), ("rule", toJson r.clause.name),
        ("owner", toJson r.owner), ("why", toJson why)]
      -- A rule reads, and its spell carries, only what its owner may view: the thing it is on and all
      -- its condition and holes cite.
      if (unviewable after r.owner (id :: (citesOf after r.clause.names).objects)).isSome then
        unfired := unfired.push (refuse "reads")
        continue
      let text := (r.clause.modality.spell?).bind (Law.fill facts (some oldState) newState)
      let quiet := (quietOf before r.owner "").isSome
      match text, text.bind (spellCard before r.owner) with
      | none, _ => unfired := unfired.push (refuse "hole")
      | some _, none => unfired := unfired.push (refuse "spell")
      | some text, some to =>
        if r.owner.isEmpty then unfired := unfired.push (refuse "noOwner")
        else if quiet then unfired := unfired.push (refuse "quiet")
        else if depth + 1 > Limits.ruleDepth then unfired := unfired.push (refuse "ruleDepth")
        else if fired.size ≥ Limits.rulesPerCommit then unfired := unfired.push (refuse "rulesPerCommit")
        else if before.pending.size + fired.size ≥ Limits.maxPending then unfired := unfired.push (refuse "pending")
        else fired := fired.push (Json.mkObj [("id", toJson (ruleDeliveryId id r.clause.name height)), ("to", toJson to),
          ("method", toJson "receive"), ("argument", dataJson (.record [("text", .label text), ("post", .label "")])), ("sender", toJson id),
          ("principal", toJson r.owner), ("ledger", child.json), ("rule", toJson r.clause.name), ("depth", toJson (depth + 1))])
  let mut wanted : Array Json := #[]
  let mut unwanted : Array Json := #[]
  for (id, o) in judged.updates ++ judged.creations do
    let was := ((before.objects[id]?).map fun x => (posing before height id x).map (·.clause.name)).getD []
    let (opened, closed) := wantFlips id was ((posing after height id o).map (·.clause.name))
    wanted := wanted ++ opened
    unwanted := unwanted ++ closed
  return (if fired.isEmpty then [] else [("fired", Json.arr fired)]) ++
    (if unfired.isEmpty then [] else [("unfired", Json.arr unfired)]) ++ flipFields wanted unwanted

/-- The ledger and the ticks an entry's fields name (a turn's `entryBase`), and the delivery it consumes. -/
def entryBudget (fields : List (String × Json)) : Ledger × Nat × Option String :=
  (((fields.lookup "ledger").bind fun l => (ledgerOf l).toOption).getD Ledger.start,
   ((fields.lookup "ticksUsed").bind fun t => t.getNat?.toOption).getD 0,
   (fields.lookup "delivery").bind fun d => (d.getObjValAs? String "id").toOption)

/-- The commit rule. Pure: the turn loop calls this with the roots it recorded and
    the writes it produced. Returns the next world and the reply (a receipt). -/
def commit (w : World) (p : Proposal) (extra : List (String × Json) := [])
    (forced : Option Refusal := none)
    (onAdmit : List (String × Object) → List (String × Json) := fun _ => [])
    (onEnd : Nat → Json → List (String × Json) := fun _ _ => []) : World × Json :=
  -- Arguments are kept only where a Bend law reads them; its reads are roots; its code is warm.
  let p := { p with writes := p.writes.map fun (id, ws) =>
    if ((w.objects[id]?).map (·.predicate)).getD false then (id, ws) else (id, ws.map fun x => { x with argument := .record [] }) }
  let w := warmLaws w (p.writes.map (·.1))
  -- The law reads join the roots only within the root bound replay holds every entry to (codex
  -- host 4): past it the turn is refused `capacity` on the roots it read itself.
  let expanded := withLawReads w p
  let (p, forced) := if forced.isNone && expanded.roots.length + (expanded.cells.map (·.2.extra)).sum > Limits.maxRoots
    then (p, some ({ cls := "capacity", reason := some "maxRoots" } : Refusal)) else (expanded, forced)
  match retained w p.principal p.intent p.digest with
  | some r => (w, r)
  | none =>
    -- The turn number is the host's: the height of the entry about to be written.
    let p := { p with turn := w.height + 1 }
    let key := identityKey p.principal p.intent
    let base := [("identity", identityJson p.principal p.intent), ("roots", rootsJson p.roots p.cells),
      ("turn", toJson p.turn), ("request", toJson p.digest)] ++
      (if p.absent.isEmpty then [] else [("absent", toJson p.absent)]) ++ extra
    let verdict : Except Refusal Judged :=
      match forced with | some r => .error r | none => judge w (w.height + 1) p
    match verdict with
    | .error r =>
      let r := r.voiced
      let outcome := Json.mkObj ([("tag", toJson "refused"), ("class", toJson r.cls)] ++
        (r.clause.map fun c => [("clause", toJson c)]).getD [] ++
        (r.object.map fun o => [("object", toJson o)]).getD [] ++
        (r.reason.map fun o => [("reason", toJson o)]).getD [] ++
        (r.reading.map fun o => [("reading", toJson o)]).getD [] ++
        (r.expected.map fun e => [("expected", e)]).getD [] ++
        (r.root.map fun x => [("root", toJson x)]).getD [] ++
        (r.hint.map fun x => [("hint", toJson x)]).getD [] ++
        (r.next.map fun x => [("next", toJson x)]).getD [])
      -- What the turn offered and published happened only if it is admitted: a refusal carries neither.
      let base := base.filter fun (k, _) => k != "offers" && k != "publishes"
      let (w', entry) := push w key (base ++ [("outcome", outcome)] ++ onEnd (w.height + 1) outcome) []
      (w', reply entry)
    | .ok judged =>
      let before := w
      let updates := judged.updates
      let w := updates.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      let w := judged.creations.foldl (fun w (id, o) => noteMinted { w with objects := w.objects.insert id o } id) w
      let w := applyGrants w p.grants p.revokes p.spent
      let writes := Json.arr (updates.toArray.map fun (id, o) => Json.mkObj
        (("object", toJson id) :: ("version", toJson o.version) :: ("cid", toJson o.stateCid) ::
          writtenFields ((p.allWrites.lookup id).getD []) ++
          ((judged.evicted.lookup id).map (fun ks => [("evicted", Json.arr ks)])).getD []))
      let outcome := Json.mkObj ([("tag", toJson "admitted"), ("writes", writes)] ++
        (if judged.reprograms.isEmpty then [] else [("reprograms", Json.arr judged.reprograms.toArray)]) ++
        (if judged.amendments.isEmpty then [] else [("amendments", Json.arr judged.amendments.toArray)]) ++
        (if judged.creates.isEmpty then [] else [("creates", Json.arr judged.creates.toArray)]) ++
        (if p.grants.isEmpty then [] else [("grants", Json.arr (p.grants.toArray.map Grant.json))]) ++
        (if p.revokes.isEmpty then [] else [("revokes", toJson p.revokes)]) ++
        (if p.spent.isEmpty then [] else [("spent", spentJson p.spent)]) ++
        (if p.placements.isEmpty then [] else [("placements", Json.arr (p.placements.toArray.map (·.json)))]) ++
        placedField before (updates ++ judged.creations))
      -- The rules the write fires and the wants it opens and closes, under the ledger its sends inherit.
      let (ledger, used, delivery) := entryBudget base
      let child := childLedger before ledger used (updates ++ judged.creations) p.allWrites
      let reacted := reactions before w (before.height + 1) judged child (ruleDepthOf before delivery)
      let holders := (p.grants.map (·.holder)).filter fun h => !updates.any (·.1 == h)
      -- A creation's state is storage the turn spent, as a write's growth is (codex host 9): the
      -- ledger its sends inherit counts both (`childLedger`; a created id is new, so all of it).
      let (w', entry) := push w key (base ++ [("outcome", outcome)] ++ onAdmit (updates ++ judged.creations) ++ reacted ++
          newSources w (judged.creations.flatMap fun (_, o) => inputSources o.inputs) ++ onEnd (w.height + 1) outcome)
        (updates.map (·.1) ++ judged.creations.map (·.1) ++ holders.eraseDups)
      (w', reply entry)

/-! ## Creation -/

/-- Compile inputs from a request: either a previously compiled `artifact`
    (re-derived and compared) or `modules`/`source` + `entry` + `limits`. -/
def compileInputs (j : Json) : Except String Json := do
  match j.getObjVal? "artifact" with
  | .ok a => return Json.mkObj [("modules", ← a.getObjVal? "modules"), ("entry", ← a.getObjVal? "entry"),
      ("limits", ← a.getObjVal? "limits")]
  | .error _ =>
    let fields := ["modules", "source", "entry", "limits"].filterMap fun k =>
      (j.getObjVal? k).toOption.map (k, ·)
    return Json.mkObj fields

def parseRead (j : Option Json) : Except String ReadPolicy :=
  match j with
  | none => pure .exposed
  | some (.str "public") => pure .exposed
  | some obj => do
    let raw ← (← obj.getObjVal? "principals").getArr?
    if raw.size > Limits.maxReaders then throw "too many readers"
    let names ← raw.toList.mapM fun r => do boundedText "reader" Limits.maxPrincipalBytes (← r.getStr?)
    pure (.principals names)

def parseChain (j : Option Json) : Except String Ledger :=
  match j with
  | none => pure Ledger.start
  | some c => do
    let l : Ledger := ⟨← natField c "depth", ← natField c "work", ← natField c "storage"⟩
    if l.depth > Limits.maxDepth || l.work > Limits.chainWork || l.storage > Limits.chainStorage then
      throw "a chain ledger may be lowered at creation, never raised above the host limits"
    pure l

/-- The law of an object created without one:
    `owner: request.kind == 0 or request.kind == rule or request.subject == "<creator>"`.

    Writes only ever change the running object (a method's `write` is its own; other
    objects change by being called, and their own law judges what they do to themselves),
    so a kind-0 judgment is always about an object's own method acting for a principal.
    The law therefore means: anyone may invoke my methods and place a rule or a want on me
    (docs/OVERHAUL.md §2 conflict 8); only my creator may reprogram or amend me. An object
    that wants its writes guarded as well declares a law (`request.subject`, `request.caller`,
    `appendOnly`, `unchanged`, ...); a maker-only thing says `request.kind == rule implies
    request.subject == new.maker`. -/
def defaultLaw (creator : String) : Except String Law := do
  if creator.any (fun c => c == '"' || c == '\\' || c.toNat < 32) then
    throw "the creator handle cannot be named in the default law"
  let clause ← Delvetalk.Compiler.ObjectiveBendLaw.parse
    s!"request.kind == 0 or request.kind == rule or request.subject == \"{creator}\""
  return [("owner", clause)]


/-- Give a compiled package its first state and law. `lawText`, when given, is the law
    exactly as journaled; otherwise the package's laws, or the default owner law. -/
def makeObject (w : World) (b : Built) (inputs : Json) (state : Data) (read : Option Json := none)
    (chain : Option Json := none) (creator : String := "") (height : Nat := 1)
    (lawText : Option String := none) : Except String (Object × String) := do
  unless state.conformsUnder b.assumptions.bounds b.ty do throw "seed does not conform to the package state type"
  let cells := Delvetalk.Turn.StateCells.of (cellDecls b.relations) state
  if let some cell := (Delvetalk.Turn.Changes.all cells).overBound cells then
    throw ((cellRefusal "the seed" cell).reason.getD "")
  -- The pin is the source closure's CID; the compiled packet is only observed beside it.
  let packet ← b.artifact.getObjValAs? String "packetSha256"
  let sources ← b.artifact.getObjValAs? String "sourcesSha256"
  let pin := sources
  -- No law declared: the creator owns reprogramming and amendment, anyone may write.
  let laws ← match lawText with
    | some text => parseLawText text
    | none => if b.laws.isEmpty then defaultLaw creator else pure b.laws
  if let some message := citationRefusal w "" laws then throw message
  if let some message := amendable laws creator "" height 0 pin state (cite := citing w laws (lawNames laws)) then throw message
  let (methods, predicate, predicateReads) := b.shape
  -- Readings belong to the package's clauses; a law given at creation keeps those it left alone.
  let given := (lawText.bind fun t => (parseLawTextReadings t).toOption.map (·.2)).getD []
  let readings := given ++ (artifactReadings b.artifact).filter fun (n, _) =>
    (laws.lookup n).isSome && laws.lookup n == b.laws.lookup n && (given.lookup n).isNone
  -- A package's rules and wants are placed on what is made of it, by its creator, when no text is given.
  let placed := if lawText.isSome then [] else b.lines.map fun c =>
    ({ name := c.name, owner := creator, since := height, line := c.render, clause := c } : Placed)
  return ({ pin, law := laws, lawText := lawText.getD (renderLaw laws), version := 0, cells, stateType := b.ty, readings,
            rules := placed.filter (Law.isRule ·.clause), wants := placed.filter (Law.isWant ·.clause),
            bounds := b.assumptions.bounds, read := ← parseRead read, chain := ← parseChain chain,
            inputs, inputsKey := inputsKeyOf inputs, methods, predicate, predicateReads, packet,
            relations := b.relations, fixed := fixedOf b.artifact, declares := declaresOf b.artifact }, sources)

def cacheBuild (w : World) (inputs : Json) (b : Built) : World :=
  { w with builds := boundedInsert w.builds Limits.maxBuilds (buildKey inputs) b }

/-- Build an object and remember its compiled package in the world. -/
def buildObjectIn (w : World) (inputs seed : Json) (read : Option Json := none) (chain : Option Json := none)
    (creator : String := "") (height : Nat := 1) (lawText : Option String := none) :
    Except String (Object × String × World) := do
  let built ← compileObject w inputs
  let (_, state) ← relationsFor built (← decodeData Limits.dataDepth seed)
  let (o, sources) ← makeObject w built inputs state read chain creator height lawText
  return (o, sources, cacheBuild w inputs built)

def buildObject (w : World) (inputs seed : Json) (read : Option Json := none) (chain : Option Json := none)
    (creator : String := "") (height : Nat := 1) (lawText : Option String := none) : Except String (Object × String) := do
  let (o, sources, _) ← buildObjectIn w inputs seed read chain creator height lawText
  return (o, sources)

def createOutcome (id : String) (o : Object) (artifact seed : Json) : Json :=
  Json.mkObj ([("tag", toJson "created"), ("read", o.read.json), ("chain", o.chain.json), ("object", toJson id), ("pin", toJson o.pin),
    ("compile", artifact), ("seed", seed), ("cid", toJson o.stateCid)] ++ (if o.unplaced then [] else [("placed", toJson (placedCid o))]))

/-- A seed (a `Data` payload) is a whole state, or a record naming some fields of it (the rest
    come from `initial()`), for `world-create` and the `create` Plan alike. -/
def mergeSeed (initial seed : Data) (bounds : Delvetalk.Theory.ObjectiveBendTypes.DataBounds)
    (ty : Delvetalk.Theory.ObjectiveBendTypes.Ty) : Except String Data := do
  if seed.conformsUnder bounds ty then return seed
  match seed, initial with
  | .record given, .record base =>
    if given.any fun (k, _) => !base.any (·.1 == k) then throw "the seed names a field the state does not have"
    return .record (base.map fun (k, v) => (k, (given.lookup k).getD v))
  | _, _ => throw "the seed is not a record"

/-- The `owner` convention every object's law uses: when the state has a text field `owner`
    and the seed does not set it, the merged state takes `owner` (the named owner, else the
    creating principal) before the law's dry run, so a creator owns what it makes. -/
def withOwner (state seed : Data) (owner : String) : Data :=
  let given := match seed with
    | .record f => f.any (·.1 == "owner")
    | _ => true
  match state with
  | .record fs =>
    if given then state else
    match fs.lookup "owner" with
    | some (.label _) => .record (fs.map fun (k, v) => if k == "owner" then (k, .label owner) else (k, v))
    | _ => state
  | _ => state

/-- The state a package's entry (its `initial()`) evaluates to. -/
def initialState (b : Built) : Except String Data := do
  match Package.executeDataValues (← b.artifact.getObjVal? "packet") #[] (Json.mkObj []) with
  | .ok (.finished v _ _ _) => pure v
  | _ => throw "initial() did not evaluate"

def create (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let id ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let digest := Journal.bodyHash (Json.mkObj
    (j.getObj?.toOption.map (·.toList.filter (·.1 != "op")) |>.getD []))
  if let some r := retained w principal intent digest then return (w, r)
  unless validObjectId id do throw s!"object id {id} is not one: {objectIdRule}"
  if id == "self" then throw "object id self is reserved for the running object"
  if id == meCard then throw "object id me is reserved: it names each principal's own avatar"
  -- The opener of the world may create an object for its owner: the law (the default law
  -- names the owner) and the metarule are the owner's, the creator is the opener.
  let owner ← optText j "owner"
  if let some o := owner then
    discard <| boundedText "owner" Limits.maxPrincipalBytes o
    if !openerActs w principal then
      throw s!"only the opener of the world{if w.resident && principal == w.opener then ", on the root socket," else ""} may name an owner{if w.opener.isEmpty then "; this world names no opener" else s!"; that is {w.opener}"}"
  if w.objects.contains id then throw s!"object {id} already exists"
  if w.objects.size ≥ w.objectBound then throw "object capacity reached"
  let inputs ← attachLibrary w (← compileInputs j)
  -- The seed is laid over initial(), as the create Plan does: a record of some of the state's
  -- fields ({} is initial() itself). The journal keeps the whole state, so replay needs no merge.
  let built ← compileObject w inputs
  let given ← decodeData Limits.dataDepth (← j.getObjVal? "seed")
  let state ← (mergeSeed (← initialState built) given built.assumptions.bounds built.ty).mapError (s!"typeMismatch: {·}")
  let state := withOwner state given (owner.getD principal)
  -- Relations are journaled in canonical form, so the seed is the state the object holds.
  let (_, state) ← relationsFor built state
  let seed := dataJson state
  -- A law given at creation is the object's law text from the start, in `world-amend`'s grammar
  -- (readings included); it replaces the package's and the default law.
  let law ← match ← optText j "law" with
    | some text => if text.isEmpty then pure none else match parseLawText text with
      | .ok _ => pure (some text)
      | .error message => throw s!"law syntax: {message}"
    | none => pure none
  let (o, sources, w) ← buildObjectIn (cacheBuild w inputs built) inputs seed (j.getObjVal? "read").toOption (j.getObjVal? "chain").toOption (owner.getD principal) (w.height + 1) law
  let supervisor := (← optText j "supervisor").getD ""
  unless supervisor.isEmpty || w.objects.contains supervisor do throw s!"supervisor {supervisor} is not an object"
  unless supervisor.isEmpty || ((w.objects[supervisor]?).map (·.offers "ended")).getD false do
    throw s!"supervisor {supervisor} does not take ended: a supervisor's package declares it"
  let o := { o with supervisor }
  -- An `artifact` claim is only a claim: the journal keeps the inputs, never the claim.
  discard <| pure sources
  let outcome := createOutcome id o (compactInputs inputs) seed
  let outcome := if supervisor.isEmpty then outcome else outcome.setObjVal! "supervisor" (toJson supervisor)
  let outcome := match owner with
    | some o => outcome.setObjVal! "owner" (toJson o)
    | none => outcome
  let outcome := match law with
    | some text => outcome.setObjVal! "law" (toJson text)
    | none => outcome
  -- The law the object starts with, as it holds it: a snapshot's law is checked against the
  -- journal's (`Snapshot.expectedLaws`), and replay against this.
  let outcome := outcome.setObjVal! "lawText" (toJson o.lawText)
  let (w', entry) := push (noteMinted { w with objects := w.objects.insert id o } id) (identityKey principal intent)
    ([("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson digest), ("outcome", outcome)] ++ newSources w (inputSources inputs)) [id]
  return (w', reply entry)

/-! ## The library as a journaled fact

The first `library` entry records the library's pin, its modules and the world law that
judges every later change; a change is another `library` entry naming the pin it
replaces. Replay re-seals the recorded modules and re-judges the change. -/

/-- The default law of library change: only the principal who opened the world. -/
def libraryLawText (opener : String) : Except String String := do
  if opener.any (fun c => c == '"' || c == '\\' || c.toNat < 32) then
    throw "the opener handle cannot be named in the library law"
  return s!"law opener: request.subject == \"{opener}\""

/-- The first clause of the world law that refuses `principal` installing library `pin`. -/
def libraryRefusal (lawText principal : String) (height : Nat) (pin : String) : Option String :=
  match parseLawText lawText with
  | .error _ => some "law syntax"
  | .ok law => Law.refusedBy law { subject := principal, caller := "", height, turn := height, pin, kind := 1 } (some (.record [])) (.record [])

def installLibrary (w : World) (lib : Library) (lawText : String) : World :=
  { w with library := some lib, libraries := w.libraries.insert lib.pin lib, libraryLaw := lawText }

/-- Journal the library as the world's own (`lawArg` only on the first), or a change of it.
    The world law judges the principal; a refusal is a `lawRefused` entry naming `library`. -/
def libraryOp (w : World) (principal intent : String) (lib : Library) (lawArg : Option String) :
    Except String (World × Json) := do
  let digest := Journal.bodyHash (Json.arr #[toJson principal, toJson intent, toJson lib.pin])
  if let some r := retained w principal intent digest then return (w, r)
  let first := w.library.isNone
  let lawText ← if first then (match lawArg with | some t => pure t | none => libraryLawText principal)
    else pure w.libraryLaw
  if !first && w.library.map (·.pin) == some lib.pin then
    return (w, Json.mkObj [("status", toJson "library"), ("pin", toJson lib.pin), ("changed", toJson false)])
  let key := identityKey principal intent
  let base := [("identity", identityJson principal intent), ("roots", rootsJson []),
    ("turn", toJson (w.height + 1)), ("request", toJson digest)]
  match libraryRefusal lawText principal (w.height + 1) lib.pin with
  | some clause =>
    let outcome := Json.mkObj [("tag", toJson "refused"), ("class", toJson "lawRefused"),
      ("clause", toJson clause), ("object", toJson "library")]
    let (w', entry) := push w key (base ++ [("outcome", outcome)]) []
    return (w', reply entry)
  | none =>
    let outcome := Json.mkObj ([("tag", toJson "library"), ("pin", toJson lib.pin),
      ("previous", toJson ((w.library.map (·.pin)).getD "")), ("modules", modulesJson lib.modules)] ++
      (if first then [("law", toJson lawText)] else []))
    let (w', entry) := push (installLibrary w lib lawText) key (base ++ [("outcome", outcome)]) []
    return (w', reply entry)

/-! ## Settings and posts

The first open that names a clock principal or a posting quota journals a `settings` entry;
after that both are fixed. `posted` entries record what transport published for an object,
so a reply to that post reaches its card (`world-reach`). An open that journals nothing
answers `{}`, never null: `durable`'s settling pass sets `resumed`/`delivered` on the answer. -/

def settingsOp (w : World) (clock : Option String) (quota : Option Nat) (opener : Option String := none)
    (interpretQuota : Option Nat := none) : Except String (World × Json) := do
  if clock.isNone && quota.isNone && opener.isNone && interpretQuota.isNone then return (w, Json.mkObj [])
  let clockP := clock.getD ""
  let openerP := opener.getD ""
  if w.settled then
    if (clock.isSome && clockP != w.clockPrincipal) || (quota.isSome && quota != some w.postQuota) ||
        (opener.isSome && openerP != w.opener) || (interpretQuota.isSome && interpretQuota != some w.interpretQuota) then
      throw s!"the journal records clock {w.clockPrincipal}, postQuota {w.postQuota}, interpretQuota {w.interpretQuota} and opener {w.opener}; the settings differ"
    return (w, Json.mkObj [])
  if let some c := clock then discard <| boundedText "clock principal" Limits.maxPrincipalBytes c
  if let some o := opener then discard <| boundedText "opener" Limits.maxPrincipalBytes o
  let q := quota.getD 16
  let intent := "settings"
  -- The opener is recorded only when named, so earlier settings entries keep their bytes.
  let fields := [("clock", toJson clockP), ("postQuota", toJson q)] ++
    (if openerP.isEmpty then [] else [("opener", toJson openerP)]) ++
    ((interpretQuota.map fun n => [("interpretQuota", toJson n)]).getD [])
  let (w', entry) := push { w with clockPrincipal := clockP, postQuota := q, opener := openerP, settled := true,
                                   interpretQuota := interpretQuota.getD 48 }
    (identityKey "world" intent)
    [("identity", identityJson "world" intent), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson (Journal.bodyHash (Json.mkObj fields))),
     ("outcome", Json.mkObj ([("tag", toJson "settings")] ++ fields))] []
  return (w', reply entry)

/-- A later `settings` entry (`world-settings`, the `settings` power; docs/ROOT.md §2.2): the opener
    replaces quotas (`postQuota`, `interpretQuota`, `modelQuota`), each value the last one named,
    with a reading. -/
def settingsChange (w : World) (principal intent digest : String) (values : List (String × Nat)) (reading : String)
    (extra : List (String × Json) := []) : Except String (World × Json) := do
  if w.opener.isEmpty || principal != w.opener then throw "settings are the opener's"
  if values.isEmpty then throw "settings names none of postQuota, interpretQuota, modelQuota"
  for (k, _) in values do
    unless ["postQuota", "interpretQuota", "modelQuota"].contains k do throw s!"no setting {k}"
  if let some r := retained w principal intent digest then return (w, r)
  let get := fun (k : String) (d : Nat) => (values.lookup k).getD d
  let w1 := { w with postQuota := get "postQuota" w.postQuota, interpretQuota := get "interpretQuota" w.interpretQuota,
                     modelQuota := get "modelQuota" w.modelQuota }
  let outcome := Json.mkObj ([("tag", toJson "settings")] ++ values.map (fun (k, n) => (k, toJson n)) ++ [("reading", toJson reading)])
  let (w', entry) := push w1 (identityKey principal intent)
    ([("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0), ("request", toJson digest)] ++
      extra ++ [("outcome", outcome)]) []
  return (w', reply entry)

/-- The words a world's name may not be: the first segments of the ids and references a name would
    be read against (docs/FEDERATION.md §1). -/
def reservedWorldNames : List String := ["did", "zulip", "guest", "at", "world", "me", "scratch"]

/-- `[a-z][a-z0-9-]{0,31}`, not a reserved word. -/
def validWorldName (n : String) : Bool :=
  let cs := n.toList
  !cs.isEmpty && cs.length ≤ 32 && (cs.head!.isLower) &&
    cs.all (fun c => c.isLower || c.isDigit || c == '-') && !reservedWorldNames.contains n

/-- `world-open {name}`: the world's name, journaled once (`named {name}`, identity `world/name`); a
    world that holds another name refuses this one. -/
def nameOp (w : World) (name : String) : Except String (World × Json) := do
  if name.isEmpty || name == w.name then return (w, Json.mkObj [])
  if !w.name.isEmpty then throw s!"this journal is the world {w.name}, not {name}"
  unless validWorldName name do
    throw s!"a world's name is a-z, digits and -, starting with a letter, at most 32, and not one of {", ".intercalate reservedWorldNames}"
  let fields := [("name", toJson name)]
  let (w', entry) := push { w with name } (identityKey "world" "name")
    [("identity", identityJson "world" "name"), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson (Journal.bodyHash (Json.mkObj fields))),
     ("outcome", Json.mkObj ([("tag", toJson "named")] ++ fields))] []
  return (w', reply entry)

def parseSlot (j : Json) : Except String Json := do
  let principal ← boundedText "slot principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "slot intent" Limits.maxIntentBytes (← j.getObjValAs? String "intent")
  return identityJson principal intent

def postIndex (w : World) (uri : String) (post : Post) : World :=
  { w with posts := w.posts.insert uri post }

/-- The `page` and `section` of a `posted` request or outcome: absent, or a page title (a line of
    at most `maxTitleBytes`) and a section, "" for the whole page. A section without a page is refused. -/
def postedPage (j : Json) : Except String (String × String) := do
  let page ← optText j "page"
  let part ← optText j "section"
  match page with
  | none => if part.isSome then throw "section needs a page" else return ("", "")
  | some page =>
    let part := part.getD ""
    if page.isEmpty || page.utf8ByteSize > Limits.maxTitleBytes || part.utf8ByteSize > Limits.maxTitleBytes
        || page.any (· == '\n') || part.any (· == '\n') then
      throw s!"page and section are titles: one line of 1..{Limits.maxTitleBytes} bytes"
    return (page, part)

/-- The URI schemes a transport may record a post under. -/
def postSchemes : List String := ["at://", "zulip://"]

/-- `world-posted {principal, uri, unposted: true, reason, …}`: our own post was deleted on Delve or
    Zulip (the hand's `unpost`). Journals `unposted {uri, object, reason}` (identity
    `unposted:<uri>`): the post left the town, its reservation stays settled, and the post's record
    says so. A uri never posted, or unposted already, is refused. -/
def unpostedOp (w : World) (j : Json) (principal uri : String) : Except String (World × Json) := do
  let reason ← boundedText "reason" Limits.maxReasonBytes (← j.getObjValAs? String "reason")
  if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then
    throw s!"posts are confirmed only by {w.clockPrincipal}"
  let fields := [("tag", toJson "unposted"), ("uri", toJson uri), ("reason", toJson reason)]
  let digest := Journal.bodyHash (Json.mkObj fields)
  let intent := "unposted:" ++ uri
  let answer := fun (entry : Json) => Json.mkObj [("status", toJson "unposted"),
    ("height", (entry.getObjVal? "height").toOption.getD Json.null), ("receipt", entry)]
  match retained w principal intent digest with
  | some r => return (w, match r.getObjVal? "receipt" with | .ok e => answer e | .error _ => r)
  | none =>
    let some post := w.posts[uri]? | throw s!"post {uri} was never recorded here"
    unless post.unposted.isEmpty do throw s!"post {uri} is already unposted"
    let (w', entry) := push { w with posts := w.posts.insert uri { post with unposted := reason } } (identityKey principal intent)
      [("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0),
       ("request", toJson digest), ("outcome", Json.mkObj (fields ++ [("object", toJson post.object)]))] [post.object]
    return (w', answer entry)

/-- `world-posted {principal, uri, cid, object, slot?, page?, section?}`: transport confirms a post it
    made for `object` (and for an awaited `slot`, or carrying the object's publication of `page`,
    section "" for the whole page). Only the world's clock principal, when one is named. -/
def postedOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let uri ← boundedText "uri" Limits.maxUriBytes (← j.getObjValAs? String "uri")
  if (j.getObjVal? "unposted").toOption == some (Json.bool true) then return ← unpostedOp w j principal uri
  let cid ← boundedText "cid" Limits.maxUriBytes (← j.getObjValAs? String "cid")
  let object ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let slot ← match j.getObjVal? "slot" with
    | .ok (.null) | .error _ => pure none
    | .ok s => pure (some (← parseSlot s))
  let (page, part) ← postedPage j
  -- The reservation the post settles (HOST-HANDOFF 5.107): every post names its intent.
  let some reserved := (j.getObjValAs? String "intent").toOption
    | throw "a post settles a reservation; name its intent"
  -- An AT post, or a message of the Zulip playtest transport (`zulip://<stream>/<topic>/<id>`).
  unless postSchemes.any (fun (p : String) => uri.startsWith p) do
    throw s!"uri must be an at:// or zulip:// URI, not {(uri.splitOn "://").head!}://"
  if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then
    throw s!"posts are confirmed only by {w.clockPrincipal}"
  unless w.objects.contains object do throw s!"unknown object {object}"
  let fields := [("tag", toJson "posted"), ("uri", toJson uri), ("cid", toJson cid), ("object", toJson object)] ++
    (slot.map fun s => [("slot", s)]).getD [] ++
    (if page.isEmpty then [] else [("page", toJson page), ("section", toJson part)]) ++
    [("intent", toJson reserved)]
  let digest := Journal.bodyHash (Json.mkObj fields)
  let answer := fun (entry : Json) => Json.mkObj [("status", toJson "posted"),
    ("height", (entry.getObjVal? "height").toOption.getD Json.null), ("receipt", entry)]
  let intent := "posted:" ++ uri
  match retained w principal intent digest with
  | some r => return (w, match r.getObjVal? "receipt" with | .ok e => answer e | .error _ => r)
  | none =>
    if w.posts.contains uri then throw s!"post {uri} is already recorded"
    match w.reservations[reserved]? with
    | some r =>
      if r.released then throw s!"the reservation of {reserved} was released"
      if r.posted then throw s!"the reservation of {reserved} is already posted"
    | none => throw s!"no reservation of {reserved}; reserve it with world-post-reserve first"
    let (w', entry) := push (postIndex w uri { object, slot, page, part, height := w.height + 1 }) (identityKey principal intent)
      [("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0),
       ("request", toJson digest), ("outcome", Json.mkObj fields)] [object]
    return (w', answer entry)

/-- The clock hour posts are counted in (60 clock units, as `interpretQuota` counts). -/
def postHour (w : World) : Nat := w.clock / 60

/-- The source whose posts count against `postQuota` (delve.town's etiquette; Zulip has none). -/
def quotaSource : String := "delve"

/-- Reservations of `source` standing in the current hour (not released). -/
def postsUsed (w : World) (source : String) : Nat :=
  w.reservations.fold (fun n _ r => if r.source == source && r.hour == postHour w && !r.released then n + 1 else n) 0

/-- Would a reservation of `source` now be refused? The clock at which the next may be made. -/
def postRefusal (w : World) (source : String) : Option Nat :=
  if source == quotaSource && postsUsed w source ≥ w.postQuota then some ((postHour w + 1) * 60) else none

/-- `world-post-reserve {principal: clock, intent, source}` (HOST-HANDOFF 5.107): admit one post of
    `intent` before the network is touched. `delve` posts count against the journaled `postQuota` per
    clock hour and are refused `quota {next}` past it; another source reserves without a count. The
    reservation is journaled `reserved {intent, source, hour}` under `(clock, "post:" intent)`, so a
    retry of the intent answers it again and takes no second slot; an intent released is reserved
    anew. -/
def postReserveOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "intent" Limits.maxIntentBytes (← j.getObjValAs? String "intent")
  let source ← boundedText "source" Limits.maxSourceBytes (← j.getObjValAs? String "source")
  if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then
    throw s!"posts are reserved only by {w.clockPrincipal}"
  let round := match w.reservations[intent]? with
    | some r => if r.released then r.round + 1 else r.round
    | none => 0
  let key := s!"post:{intent}" ++ (if round == 0 then "" else s!"/{round}")
  let digest := Journal.bodyHash (Json.mkObj [("intent", toJson intent), ("source", toJson source)])
  if let some r := retained w principal key digest then return (w, r)
  if let some next := postRefusal w source then
    return (w, Json.mkObj [("status", toJson "refused"), ("class", toJson "quota"), ("source", toJson source),
      ("reason", toJson s!"{w.postQuota} {source} posts an hour; the next at clock {next}"), ("next", toJson next)])
  let (w', entry) := push w (identityKey principal key)
    [("identity", identityJson principal key), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson digest), ("outcome", Json.mkObj [("tag", toJson "reserved"), ("intent", toJson intent),
       ("source", toJson source), ("hour", toJson (postHour w))])] []
  return (w', reply entry)

/-- `world-post-release {principal: clock, intent, reason}`: give back a reservation whose post
    certainly did not leave (credentials unreadable, the request refused before the network); never
    one that may have landed. Journaled `released {intent, reason}`; releasing it again answers
    without an entry. -/
def postReleaseOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "intent" Limits.maxIntentBytes (← j.getObjValAs? String "intent")
  let reason ← j.getObjValAs? String "reason"
  if reason.utf8ByteSize > Limits.maxHandleBytes then throw s!"reason must be at most {Limits.maxHandleBytes} bytes"
  if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then
    throw s!"posts are released only by {w.clockPrincipal}"
  let some r := w.reservations[intent]? | throw s!"no reservation of {intent}"
  if r.posted then throw s!"{intent} was posted; a posted reservation stands"
  if r.released then return (w, Json.mkObj [("status", toJson "released"), ("intent", toJson intent)])
  let key := s!"release:{intent}/{r.round}"
  let (w', entry) := push w (identityKey principal key)
    [("identity", identityJson principal key), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson (Journal.bodyHash (Json.mkObj [("intent", toJson intent), ("reason", toJson reason)]))),
     ("outcome", Json.mkObj [("tag", toJson "released"), ("intent", toJson intent), ("reason", toJson reason)])] []
  return (w', reply entry)

/-- `world-status.posts`: per source standing this clock hour, how many are reserved and, for the
    counted source, the quota and the clock at which the next may be made. -/
def postsStatus (w : World) : Json :=
  let sources := (w.reservations.fold (fun acc _ r => if r.hour == postHour w && !acc.contains r.source then acc ++ [r.source] else acc)
    [quotaSource])
  Json.mkObj [("hour", toJson (postHour w)), ("sources", Json.arr (sources.toArray.map fun src =>
    Json.mkObj ([("source", toJson src), ("used", toJson (postsUsed w src))] ++
      (if src == quotaSource then [("quota", toJson w.postQuota),
        ("next", match postRefusal w src with | some n => toJson n | none => Json.null)] else []))))]

/-- `world-principal {principal, did, handle}`: the clock principal records the display handle
    of `did` (the bridge, at the first observed post of each author). Journaled as a
    `principal` entry and indexed by `record`, so replay and snapshots rebuild the registry; a
    handle already recorded answers without an entry. Handles are what cards show where the
    town reads names; they confer nothing. -/
def principalOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let did ← boundedText "did" Limits.maxPrincipalBytes (← j.getObjValAs? String "did")
  let handle ← j.getObjValAs? String "handle"
  if handle.utf8ByteSize > Limits.maxHandleBytes then throw s!"handle must be at most {Limits.maxHandleBytes} bytes"
  if handle.toList.any (fun (c : Char) => c.toNat < 32 || c.toNat == 127) then throw "handle must be one line of printable text"
  if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then
    throw s!"principals are recorded only by {w.clockPrincipal}"
  let answer := fun (entry : Option Json) => Json.mkObj ([("status", toJson "principal"), ("did", toJson did),
    ("handle", toJson handle)] ++ (entry.map fun e => [("receipt", e)]).getD [])
  if handleOf w did == handle && (w.handles.contains did || handle.isEmpty) then return (w, answer none)
  let intent := s!"principal:{did}:{w.height + 1}"
  let fields := [("tag", toJson "principal"), ("did", toJson did), ("handle", toJson handle)]
  let (w', entry) := push w (identityKey principal intent)
    [("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson (Journal.bodyHash (Json.mkObj fields))), ("outcome", Json.mkObj fields)] []
  return (w', answer (some entry))

/-- `world-cite {principal, identity?, world, entry}`: an entry of a scratch world kept as evidence here
    (docs/FEDERATION.md §3, the second exit), whole inside a `cited` entry under the citer's identity
    (`cite:<hash>` unless one is named). `serve` reads the entry from the scratch itself; the entry
    must be its hash's. Evidence survives the scratch; its state does not. -/
def citeOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let world ← j.getObjValAs? String "world"
  let cited ← j.getObjVal? "entry"
  let hash ← cited.getObjValAs? String "hash"
  let body := Json.mkObj (((cited.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "hash"))
  unless Journal.bodyHash body == hash do throw "the cited entry is not its hash's"
  let intent ← boundedText "identity" Limits.maxIntentBytes ((← optText j "identity").getD s!"cite:{hash}")
  let digest := Journal.bodyHash (Json.mkObj [("world", toJson world), ("receipt", toJson hash)])
  if let some r := retained w principal intent digest then return (w, r)
  let (w', entry) := push w (identityKey principal intent)
    [("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0), ("request", toJson digest),
     ("outcome", Json.mkObj [("tag", toJson "cited"), ("world", toJson world), ("receipt", toJson hash), ("entry", cited)])] []
  return (w', Json.mkObj [("status", toJson "cited"), ("receipt", slugged entry)])

/-! ## Crossings (docs/FEDERATION.md §2): a `call` or `send` to another world one host serves

A send across is a pending delivery with `world` on it (`crossesOver`); a call across is a suspension with
`crossing` on it, waiting on the slot `(principal, id)`. `serve` carries each (`outbound`): the target world
journals it `relayed`, under `(principal, "<home>:<id>")`, as a pending send of that world (`relayOp`), which
it delivers as any send, under the sender's principal with `request.caller` `<home>:<object>`; the target's
receipt of that delivery comes back as the home world's `crossed` entry (`crossOp`), which consumes the send
or settles the call's slot. Each journal holds the other's receipt as data, so either replays alone. -/

/-- The entry an identity's receipt names: `(hash, height)`. -/
def sentFrom (w : World) (principal intent : String) : Option (String × Nat) := do
  let e ← w.entries.get? (← w.receipts[identityKey principal intent]?)
  return (← (e.getObjValAs? String "hash").toOption, ← (e.getObjValAs? Nat "height").toOption)

/-- What waits here to cross to another world: each send across still pending and each call across still
    suspended, as `{id, principal, world, to, method, argument, sender, ledger, receipt, height, send}`
    (`receipt` and `height` name the entry that sent it, `send` whether a pending send is consumed). -/
def outbound (w : World) : Array Json :=
  let item := fun (id principal : String) (c : Json) (from_ : Json) (send : Bool) =>
    let text := fun (k : String) => (from_.getObjValAs? String k).toOption.getD ""
    let (hash, height) := (sentFrom w (text "principal") (text "intent")).getD ("", 0)
    Json.mkObj ((["world", "to", "method", "argument", "sender", "ledger"].filterMap fun k => (c.getObjVal? k).toOption.map (k, ·)) ++
      [("id", toJson id), ("principal", toJson principal), ("from", from_), ("receipt", toJson hash), ("height", toJson height),
       ("send", toJson send)])
  let sends := w.pending.filter crossesOver |>.filterMap fun p => do
    item (← (p.getObjValAs? String "id").toOption) (← (p.getObjValAs? String "principal").toOption) p (← (p.getObjVal? "from").toOption) true
  let calls := w.suspended.filterMap fun e => do
    let outcome ← (e.getObjVal? "outcome").toOption
    let c ← (outcome.getObjVal? "crossing").toOption
    let slot ← (outcome.getObjVal? "slot").toOption
    let principal ← (slot.getObjValAs? String "principal").toOption
    let id ← (slot.getObjValAs? String "intent").toOption
    if w.receipts.contains (identityKey principal id) then none
    else item id principal c ((e.getObjVal? "identity").toOption.getD Json.null) false
  sends ++ calls

/-- `world-relay {principal, world, id, to, method, argument, sender, ledger, receipt, height}` (serve's own,
    never a socket's): a call or send of world `world`'s entry `receipt` arrives here as a `relayed` entry
    under `(principal, "<world>:<id>")` whose one send (`<world>:<sender>` its sender) the settling pass
    delivers. A second relay of the same answers the first's receipt. -/
def relayOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let world ← j.getObjValAs? String "world"
  let intent ← boundedText "identity" Limits.maxIntentBytes s!"{world}:{← j.getObjValAs? String "id"}"
  let to ← j.getObjValAs? String "to"
  let method ← boundedText "method" Limits.maxMethodBytes (← j.getObjValAs? String "method")
  let argument ← j.getObjVal? "argument"
  discard <| decodeData Limits.dataDepth argument
  let ledger ← j.getObjVal? "ledger"
  discard <| ledgerOf ledger
  let send := Json.mkObj [("id", toJson (deliveryId principal intent 0)), ("to", toJson to), ("method", toJson method),
    ("argument", argument), ("sender", toJson s!"{world}:{← j.getObjValAs? String "sender"}"), ("ledger", ledger)]
  let outcome := Json.mkObj [("tag", toJson "relayed"), ("world", toJson world),
    ("receipt", toJson (← j.getObjValAs? String "receipt")), ("height", toJson (← natField j "height"))]
  let digest := Journal.bodyHash (Json.mkObj [("outcome", outcome), ("send", send)])
  if let some r := retained w principal intent digest then return (w, r)
  if w.pending.size ≥ Limits.maxPending then throw "world exceeds the pending delivery capacity"
  let (w', entry) := push w (identityKey principal intent)
    [("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0), ("request", toJson digest),
     ("outcome", outcome), ("sends", Json.arr #[send])] []
  return (w', reply entry)

/-- `world-cross {principal, id, world, answer {tag, class?, clause?, reason?}, receipt? {hash, height}, result?}`
    (serve's own): the other world's answer to the crossing `id` waiting here (`outbound`), journaled as
    `crossed` under `(principal, id)`: it consumes a send's pending delivery, or settles a call's slot,
    which the settling pass then resumes (`TurnLoop.crossedResponse`). -/
def crossOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← j.getObjValAs? String "principal"
  let id ← j.getObjValAs? String "id"
  let answer ← j.getObjVal? "answer"
  unless ["admitted", "refused"].contains (← answer.getObjValAs? String "tag") do throw "a crossing answers admitted or refused"
  let receipt := (j.getObjVal? "receipt").toOption
  let result := (j.getObjVal? "result").toOption
  let outcome := Json.mkObj ([("tag", toJson "crossed"), ("world", toJson (← j.getObjValAs? String "world")),
    ("answer", answer)] ++ ((receipt.map fun r => [("receipt", r)]).getD []))
  let digest := Journal.bodyHash (Json.mkObj ([("outcome", outcome)] ++ ((result.map fun r => [("result", r)]).getD [])))
  if let some r := retained w principal id digest then return (w, r)
  let some item := (outbound w).find? fun x =>
      (x.getObjValAs? String "id").toOption == some id && (x.getObjValAs? String "principal").toOption == some principal
    | throw s!"no crossing {id} waits here"
  let delivery := if (item.getObjValAs? Bool "send").toOption == some true then
      [("delivery", Json.mkObj [("id", toJson id), ("from", (item.getObjVal? "from").toOption.getD Json.null)])] else []
  let (w', entry) := push w (identityKey principal id)
    ([("identity", identityJson principal id), ("roots", rootsJson []), ("turn", toJson 0), ("request", toJson digest),
      ("outcome", outcome)] ++ delivery ++ ((result.map fun r => [("result", r)]).getD [])) []
  return (w', reply entry)

/-- A newcomer's own object, made from the library module of that name: the Avatar, whose id is the
    principal's DID (`me` resolves to it); it holds the newcomer's notes (mentions, rule notes). -/
def arrivals (did : String) : List (String × String) :=
  [(did, "Avatar")]

/-- `world-arrive {principal, did, handle}`: the clock principal (transport) reports a principal
    it has verified or observed. The handle is recorded as `world-principal` does, and the newcomer's
    avatar (`arrivals`), when absent, is created from the world's library, by the world's opener for
    the owner `did` (`world-create {…, owner}`), as an ordinary `created` entry with identity
    `(opener, "arrive:<id>")`. The partial seed names, of `owner` (the DID) and `handle`, the fields
    the package's state has; the rest is `initial()`. Idempotent: a second arrival creates nothing,
    and a changed handle is one `principal` entry. -/
def arriveOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let did ← boundedText "did" (Limits.maxObjectIdBytes - 5) (← j.getObjValAs? String "did")
  let handle ← j.getObjValAs? String "handle"
  if w.clockPrincipal.isEmpty || principal != w.clockPrincipal then
    throw s!"arrivals are reported only by the clock principal{if w.clockPrincipal.isEmpty then "; this world names none" else s!" {w.clockPrincipal}"}"
  if w.opener.isEmpty then throw "this world names no opener to create a newcomer's objects"
  if did == "self" || did == meCard || did.any (· == '/') then throw s!"{did} cannot name a principal's objects"
  let some lib := w.library | throw "this world has no library to make a newcomer's objects from"
  let (w, recorded) ← principalOp w (Json.mkObj [("principal", toJson principal), ("did", toJson did), ("handle", toJson handle)])
  let mut w := w
  let mut made : Array Json := #[]
  for (id, module) in arrivals did do
    if w.objects.contains id then continue
    let some source := lib.modules.lookup module | throw s!"the world's library has no module {module}"
    let request := Json.mkObj [("principal", toJson w.opener), ("identity", toJson s!"arrive:{id}"),
      ("object", toJson id), ("owner", toJson did), ("entry", toJson "initial"),
      ("modules", modulesJson [(module, source)])]
    let inputs ← attachLibrary w (← compileInputs request)
    let built ← compileObject w inputs
    let given : List (String × Data) := [("owner", .label did), ("handle", .label handle)]
    let seed := match ← initialState built with
      | .record fields => given.filter fun (k, _) => fields.any (·.1 == k)
      | _ => []
    -- The host makes a newcomer's things as the opener on whichever socket the arrival came.
    let (w', r) ← create { cacheBuild w inputs built with resident := false } (request.setObjVal! "seed" (dataJson (.record seed)))
    let w' := { w' with resident := w.resident }
    if (r.getObjValAs? String "status").toOption != some "created" then
      throw s!"arrival of {did}: {module} {id} was not created: {r.compress}"
    w := w'
    made := made.push (Json.mkObj [("object", toJson id), ("height", toJson w.height)])
  return (w, Json.mkObj ([("status", toJson "arrived"), ("did", toJson did), ("handle", toJson handle),
    ("created", Json.arr made)] ++ ((recorded.getObjVal? "receipt").toOption.map fun e => [("principal", e)]).getD []))

/-! ## Replay -/

/-- A delivery entry must consume exactly the pending delivery it names, under
    the sender's principal; a budget refusal must name a field that is zero. -/
def checkDelivery (w : World) (entry : Json) (principal intent : String) (outcome : Json) : Except String Unit := do
  -- The final entry of a resumed delivery names its delivery again; the suspension consumed it.
  if (entry.getObjVal? "resumes").toOption.isSome then return ()
  let some d := (entry.getObjVal? "delivery").toOption | return ()
  let id ← d.getObjValAs? String "id"
  let some p := w.pending.find? fun p => (p.getObjValAs? String "id").toOption == some id
    | throw "delivery of an unknown or already delivered id"
  unless (p.getObjValAs? String "principal").toOption == some principal && intent == id do
    throw "delivery runs under another principal than its sender's"
  unless (d.getObjVal? "from").toOption == (p.getObjVal? "from").toOption do throw "delivery names another sender"
  unless (d.getObjValAs? String "via").toOption == (p.getObjValAs? String "via").toOption do
    throw "delivery names another grant than its send"
  if (outcome.getObjValAs? String "class").toOption == some "budgetExhausted" then
    let ledger ← ledgerOf (← p.getObjVal? "ledger")
    unless ledger.exhausted.map exhaustedReason == (outcome.getObjValAs? String "reason").toOption do
      throw "budget refusal names a field that is not exhausted"
  else if (← ledgerOf (← p.getObjVal? "ledger")).exhausted.isSome then
    throw "a delivery with an exhausted ledger ran"

def checkSends (w : World) (entry : Json) (principal intent : String) : Except String Unit := do
  let some sends := (entry.getObjVal? "sends").toOption | return ()
  let mut ordinal := 0
  for s in ← sends.getArr? do
    if let .ok via := s.getObjValAs? String "via" then
      let some g := grantStands w via (← s.getObjValAs? String "to") (← s.getObjValAs? String "method")
        | throw "a send names a grant that does not stand"
      unless (s.getObjValAs? String "principal").toOption == some g.grantor do
        throw "a send under a grant is not delivered as its grantor"
    unless (s.getObjValAs? String "id").toOption == some (deliveryId principal intent ordinal) do
      throw "send id does not match its ordinal"
    discard <| s.getObjValAs? String "to"
    discard <| s.getObjValAs? String "method"
    discard <| decodeData Limits.dataDepth (← s.getObjVal? "argument")
    discard <| ledgerOf (← s.getObjVal? "ledger")
    ordinal := ordinal + 1

/-- An `ended` field names its entry's id and the supervisor of the object it speaks for. -/
def checkEnded (w : World) (entry : Json) (principal intent : String) : Except String Unit := do
  let some e := (entry.getObjVal? "ended").toOption | return ()
  unless (← e.getObjValAs? String "id") == endedId principal intent (w.height + 1) do throw "an ended delivery is not its entry's"
  let object ← e.getObjValAs? String "sender"
  unless (w.objects[object]?).map (·.supervisor) == some (← e.getObjValAs? String "to") do
    throw "an ended delivery is not to the object's supervisor"
  discard <| decodeData Limits.dataDepth (← e.getObjVal? "argument")
  discard <| ledgerOf (← e.getObjVal? "ledger")

/-- An entry that resumes a suspension must name a waiting one of the same identity. -/
def checkResumes (w : World) (entry : Json) (principal intent : String) : Except String Unit := do
  let some h := (entry.getObjValAs? String "resumes").toOption | return ()
  let some s := w.suspended.find? fun s => (s.getObjValAs? String "hash").toOption == some h
    | throw "resumes a suspension that is not waiting"
  let id ← s.getObjVal? "identity"
  unless (id.getObjValAs? String "principal").toOption == some principal &&
      (id.getObjValAs? String "intent").toOption == some intent do
    throw "resumes a suspension of another identity"

/-! ## Root (docs/ROOT.md §1)

A root entry is `{root: true, reason, outcome {tag: root, kind, object?, field?, before, after}}`; a
moderation entry is `{outcome {tag: moderated, power, …, before?, after?, reading}}`. `rootBefore`
reads the value an act replaces from the store as it stands, `applyRoot` lays `after` on the store
verbatim (no judge, no conformance, no pin check), and `recordActs` moves the indexes: live and
replay call the same three. -/

/-- The fields `set` may name. -/
def rootFields : List String :=
  ["state", "law", "program", "pin", "owner", "read", "version", "fixed", "supervisor", "ledger", "readings", "activities"]

/-- The one top-level state field a root `set` of `state.F` names: F; none for any other field (a nested path refuses). -/
def stateFieldOf (field : String) : Option String :=
  if !field.startsWith "state." then none else
  let f := (field.drop "state.".length).toString
  if f.isEmpty || f.any (· == '.') then none else some f

/-- A state field's new value as a root `set` gives it: typed wire data, or a plain JSON number, text or boolean
    standing for a field of that kind (`--value 12` for a natural). -/
def fieldValue (current : Data) (j : Json) : Except String Data :=
  match decodeData Limits.dataDepth j, current, j with
  | .ok d, _, _ => .ok d
  | .error _, .natural _, .num _ => return .natural (← j.getNat?)
  | .error _, .label _, .str t => .ok (.label t)
  | .error _, .boolean _, .bool b => .ok (.boolean b)
  | .error e, _, _ => .error s!"the value is not typed data, nor a plain value of the field's kind: {e}"

/-- `state` with its top-level field `f` replaced by `v`, when it has it. -/
def withField (state : Data) (f : String) (v : Data) : Except String Data :=
  match state with
  | .record fs => if fs.any (·.1 == f) then .ok (.record (replaceField fs f v)) else .error s!"the state has no field {f}"
  | _ => .error "the state is not a record"

def readingsJson (rs : List (String × String)) : Json :=
  Json.arr (rs.toArray.map fun (n, r) => Json.mkObj [("name", toJson n), ("reading", toJson r)])

/-- An object's whole record, as `delete`'s `before` names it. -/
def objectRecord (o : Object) : Json :=
  Json.mkObj ([("pin", toJson o.pin), ("law", toJson o.lawText), ("version", toJson o.version),
    ("state", dataJson o.state), ("read", o.read.json), ("chain", o.chain.json), ("compile", o.inputs),
    ("supervisor", toJson o.supervisor), ("fixed", toJson o.fixed), ("readings", readingsJson o.readings)] ++
    (if o.minted == 0 then [] else [("minted", toJson o.minted)]))

/-- The suspensions waiting on an activity of `id`, by entry hash. -/
def activitiesOf (w : World) (id : String) : List String :=
  w.suspended.toList.filterMap fun s =>
    let obj := (s.getObjVal? "outcome").toOption.bind (·.getObjVal? "activity" |>.toOption)
      |>.bind (·.getObjValAs? String "object" |>.toOption)
    if obj == some id then (s.getObjValAs? String "hash").toOption else none

/-- The settings a root `settings` act or `world-settings` names, with their current values. -/
def settingValue (w : World) (k : String) : Option Json :=
  match k with
  | "clock" => some (toJson w.clock)
  | "clockPrincipal" => some (toJson w.clockPrincipal)
  | "postQuota" => some (toJson w.postQuota)
  | "interpretQuota" => some (toJson w.interpretQuota)
  | "modelQuota" => some (toJson w.modelQuota)
  | "opener" => some (toJson w.opener)
  | "libraryLaw" => some (toJson w.libraryLaw)
  | _ => none

/-- The value an act replaces, read from the store and indexes as they stand. -/
def rootBefore (w : World) (outcome : Json) : Except String Json := do
  let text := fun (k : String) => (outcome.getObjValAs? String k).toOption.getD ""
  let object := fun (_ : Unit) => match w.objects[text "object"]? with
    | some o => Except.ok o
    | none => .error s!"no object {text "object"}"
  match actOf outcome with
  | "set" =>
    let o ← object ()
    match text "field" with
    | "state" => return dataJson o.state
    | f@_ =>
    if let some name := stateFieldOf f then
      match Law.rawField name o.state with
      | some v => return dataJson v
      | none => throw s!"the state of {text "object"} has no field {name}"
    else match f with
    | "law" => return toJson o.lawText
    | "program" => return o.inputs
    | "pin" => return toJson o.pin
    | "owner" => return toJson (ownerOf o.state)
    | "read" => return o.read.json
    | "version" => return toJson o.version
    | "fixed" => return toJson o.fixed
    | "supervisor" => return toJson o.supervisor
    | "ledger" => return o.chain.json
    | "readings" => return readingsJson o.readings
    | "activities" => return toJson (activitiesOf w (text "object"))
    | f => throw s!"set names no field {f}; one of {", ".intercalate rootFields}"
  | "delete" => return objectRecord (← object ())
  | "settings" =>
    let some fields := ((outcome.getObjVal? "after").toOption.bind (·.getObj?.toOption)) | throw "settings names no values"
    return Json.mkObj (← fields.toList.mapM fun (k, _) => match settingValue w k with
      | some v => pure (k, v)
      | none => throw s!"no setting {k}")
  | "library" => return toJson ((w.library.map (·.pin)).getD "")
  | "ignore" | "unignore" =>
    return Json.mkObj [("ignored", toJson (w.ignored.contains ((outcome.getObjValAs? Nat "height").toOption.getD 0)))]
  | "card" => return ((w.cards[text "object"]?).map toJson).getD Json.null
  | "quiet" => return match w.quiets[text "principal"]? with
    | some (u, r) => Json.mkObj [("until", toJson u), ("reading", toJson r)]
    | none => Json.null
  | "hide" | "show" => return (← object ()).read.json
  | "retire" | "unretire" => return toJson (← object ()).lawText
  | "revoke" => match w.grants[text "grant"]? with
    | some g => return Json.mkObj [("revoked", toJson g.revoked)]
    | none => throw s!"no grant {text "grant"}"
  | k => throw s!"no root act {k}"

/-- Lay an act's `after` on the store, verbatim. -/
def applyRoot (w : World) (outcome : Json) : Except String World := do
  let id := (outcome.getObjValAs? String "object").toOption.getD ""
  let after := (outcome.getObjVal? "after").toOption.getD Json.null
  let put := fun (o : Object) => { w with objects := w.objects.insert id o }
  let withLaw := fun (o : Object) (text : String) => do
    let law ← parseLawText text
    let given := ((parseLawTextReadings text).toOption.map (·.2)).getD []
    let kept := o.readings.filter fun (n, _) => law.lookup n == o.law.lookup n && (given.lookup n).isNone
    return put { o with law, lawText := text, readings := given ++ kept }
  match actOf outcome with
  | "set" =>
    let some o := w.objects[id]? | throw s!"no object {id}"
    let version := (outcome.getObjValAs? Nat "version").toOption.getD (o.version + 1)
    let field := (outcome.getObjValAs? String "field").toOption.getD ""
    if let some name := stateFieldOf field then
      return put { o.withState (← canonicalState o.relations (← withField o.state name (← decodeData Limits.dataDepth after))) with version }
    match field with
    | "state" => return put { o.withState (← canonicalState o.relations (← decodeData Limits.dataDepth after)) with version }
    | "owner" =>
      let owner ← after.getStr?
      let state := match o.state with
        | .record fs => Data.record (if fs.any (·.1 == "owner") then replaceField fs "owner" (.label owner) else fs ++ [("owner", .label owner)])
        | d => d
      return put { o.withState state with version }
    | "law" => withLaw o (← after.getStr?)
    | "program" =>
      let built ← compileObject w after
      let (methods, predicate, predicateReads) := built.shape
      let w := cacheBuild w after built
      return { w with objects := w.objects.insert id { o with
        pin := ← built.artifact.getObjValAs? String "sourcesSha256", stateType := built.ty,
        bounds := built.assumptions.bounds, inputs := after, inputsKey := inputsKeyOf after,
        methods, predicate, predicateReads,
        packet := (built.artifact.getObjValAs? String "packetSha256").toOption.getD "",
        relations := built.relations, fixed := fixedOf built.artifact, declares := declaresOf built.artifact } }
    | "pin" => return put { o with pin := ← after.getStr? }
    | "read" => return put { o with read := ← parseRead (some after) }
    | "version" => return put { o with version := ← natOf after }
    | "fixed" => return put { o with fixed := ← Lean.fromJson? after }
    | "supervisor" => return put { o with supervisor := ← after.getStr? }
    | "ledger" => return put { o with chain := ← parseChain (some after) }
    | "readings" =>
      let rows ← after.getArr?
      return put { o with readings := ← rows.toList.mapM fun r => return (← r.getObjValAs? String "name", ← r.getObjValAs? String "reading") }
    | "activities" => return w
    | f => throw s!"set names no field {f}"
  | "delete" => return { w with objects := w.objects.erase id }
  | "settings" =>
    let some fields := after.getObj?.toOption | throw "settings names no values"
    let mut w := w
    for (k, v) in fields.toList do
      w ← match k with
        | "clock" => pure w
        | "clockPrincipal" => pure { w with clockPrincipal := ← v.getStr? }
        | "postQuota" => pure { w with postQuota := ← natOf v }
        | "interpretQuota" => pure { w with interpretQuota := ← natOf v }
        | "modelQuota" => pure { w with modelQuota := ← natOf v }
        | "opener" => pure { w with opener := ← v.getStr? }
        | "libraryLaw" => pure { w with libraryLaw := ← v.getStr? }
        | _ => throw s!"no setting {k}"
    return w
  | "library" =>
    let lib ← sealLibrary (← parseModules (← after.getObjVal? "modules"))
    unless lib.pin == (← after.getObjValAs? String "pin") do throw "the library is not the seal of its modules"
    return installLibrary w lib w.libraryLaw
  | "hide" | "show" =>
    let some o := w.objects[id]? | throw s!"no object {id}"
    return put { o with read := ← parseRead (some after) }
  | "retire" | "unretire" =>
    let some o := w.objects[id]? | throw s!"no object {id}"
    withLaw o (← after.getStr?)
  | "revoke" =>
    let g := (outcome.getObjValAs? String "grant").toOption.getD ""
    let some grant := w.grants[g]? | throw s!"no grant {g}"
    return { w with grants := w.grants.insert g { grant with revoked := true } }
  | "ignore" | "unignore" | "card" | "quiet" => return w
  | k => throw s!"no root act {k}"

/-- Is an entry a root `ignore` or `unignore`? -/
def isIgnoreAct (e : Json) : Bool :=
  tagOf e == "root" && ["ignore", "unignore"].contains (actOf ((e.getObjVal? "outcome").toOption.getD Json.null))

/-- The law a journaled creation is built again with: none when its package's lines were placed (the law
    was its package's, given by nobody), else the law text it was made with. -/
def createdLaw (r : Json) : Except String (Option String) := do
  if (r.getObjValAs? Bool "lines").toOption == some true then return none
  return some (← r.getObjValAs? String "law")

/-- The objects an admitted entry created, rebuilt from their journaled inputs. -/
def rebuildCreates (w : World) (principal : String) (recorded : Array Json) :
    Except String (World × List (String × CreateRec)) := do
  let mut w := w
  let mut creates : List (String × CreateRec) := []
  for r in recorded do
    let id ← r.getObjValAs? String "object"
    let seed ← r.getObjVal? "seed"
    let (o, sources, w') ← buildObjectIn w (← expandInputs w (← r.getObjVal? "compile")) seed (r.getObjVal? "read").toOption
      (r.getObjVal? "chain").toOption principal (w.height + 1) (← createdLaw r)
    w := w'
    let o := { o with supervisor := (r.getObjValAs? String "supervisor").toOption.getD "" }
    creates := creates ++ [(id, ({ object := o, sources, seed, madeFrom := (r.getObjVal? "madeFrom").toOption } : CreateRec))]
  return (w, creates)

def replayEntry (w : World) (entry : Json) : Except String World := do
  let identity ← entry.getObjVal? "identity"
  let principal ← identity.getObjValAs? String "principal"
  let intent ← identity.getObjValAs? String "intent"
  let key := identityKey principal intent
  let outcome ← entry.getObjVal? "outcome"
  -- The sources an entry introduces are known before its compile inputs are read.
  let introduced ← entrySources entry
  for (cid, _) in introduced do
    if w.modules.contains cid then throw "a source is journaled twice"
  let w := { w with modules := introduced.foldl (fun m (x : String × String) => m.insert x.1 w.height) w.modules }
  let blocks ← entryBlocks entry
  let w := { w with blocks := blocks.foldl (fun m (x : String × Array Json) => m.insert x.1 w.height) w.blocks }
  checkDelivery w entry principal intent outcome
  checkSends w entry principal intent
  -- A turn answers only a post recorded for the object it ran on (its first root).
  if let some post := (entry.getObjValAs? String "replyTo").toOption then
    let first := ((entry.getObjVal? "roots").toOption.bind (·.getArr?.toOption)).bind (·[0]?)
      |>.bind (·.getObjValAs? String "object" |>.toOption)
    unless (w.posts[post]?).map (some ·.object) == some first do
      throw s!"a turn answers {post}, which is not a post recorded for its object"
  checkResumes w entry principal intent
  checkEnded w entry principal intent
  match ← outcome.getObjValAs? String "tag" with
  | "advanced" =>
    let before ← natField outcome "from"
    let to ← natField outcome "to"
    unless before == w.clock && to > before do throw "clock advance out of sequence"
    return record w entry key []
  | "settings" =>
    -- A later settings entry is the opener's `world-settings`: quotas only, each replacing the last.
    if w.settled then
      unless !w.opener.isEmpty && principal == w.opener do throw "settings recorded twice"
      let q := fun (k : String) (d : Nat) => (outcome.getObjValAs? Nat k).toOption.getD d
      for k in ["clock", "opener"] do
        if (outcome.getObjVal? k).toOption.isSome then throw s!"a later settings entry names {k}"
      return record { w with postQuota := q "postQuota" w.postQuota, interpretQuota := q "interpretQuota" w.interpretQuota,
                             modelQuota := q "modelQuota" w.modelQuota } entry key []
    return record { w with clockPrincipal := ← outcome.getObjValAs? String "clock",
                           postQuota := ← natField outcome "postQuota", settled := true,
                           interpretQuota := (outcome.getObjValAs? Nat "interpretQuota").toOption.getD 48,
                           modelQuota := (outcome.getObjValAs? Nat "modelQuota").toOption.getD Limits.modelQuota,
                           opener := (outcome.getObjValAs? String "opener").toOption.getD "" } entry key []
  | "root" =>
    unless (entry.getObjValAs? Bool "root").toOption == some true do throw "a root outcome without the root marker"
    if w.opener.isEmpty || principal != w.opener then throw "a root entry by another than the opener"
    unless intent == s!"root:{w.rootActs + 1}" do throw "root acts out of order"
    unless (outcome.getObjVal? "before").toOption == some (← rootBefore w outcome) do
      throw s!"root entry {w.height + 1}: before does not match"
    let id := (outcome.getObjValAs? String "object").toOption.getD ""
    return record (← applyRoot w outcome) entry key (if id.isEmpty then [] else [id])
  | "moderated" =>
    if w.opener.isEmpty || principal != w.opener then throw "moderation by another than the opener"
    if let .ok before := outcome.getObjVal? "before" then
      unless before == (← rootBefore w outcome) do throw "a moderation's before does not match"
    let id := (outcome.getObjValAs? String "object").toOption.getD ""
    return record (← applyRoot w outcome) entry key (if id.isEmpty then [] else [id])
  | "unposted" =>
    let uri ← outcome.getObjValAs? String "uri"
    let some post := w.posts[uri]? | throw "unposted names a post never recorded"
    unless post.unposted.isEmpty do throw "a post unposted twice"
    if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then throw "unposted by another principal"
    let reason ← outcome.getObjValAs? String "reason"
    return record { w with posts := w.posts.insert uri { post with unposted := reason } } entry key [post.object]
  | "cited" =>
    discard <| outcome.getObjValAs? String "world"
    discard <| outcome.getObjVal? "entry"
    return record w entry key []
  | "relayed" =>
    discard <| outcome.getObjValAs? String "world"
    discard <| outcome.getObjValAs? String "receipt"
    unless ((entry.getObjVal? "sends").toOption.bind (·.getArr?.toOption)).map (·.size) == some 1 do
      throw "a relayed entry sends one delivery"
    return record w entry key []
  | "crossed" =>
    discard <| outcome.getObjValAs? String "world"
    discard <| (← outcome.getObjVal? "answer").getObjValAs? String "tag"
    -- A send's crossing consumes its pending delivery (`checkDelivery`); a call's settles its waiting slot.
    unless (outbound w).any fun x => (x.getObjValAs? String "id").toOption == some intent &&
        (x.getObjValAs? String "principal").toOption == some principal do
      throw "a crossing that nothing here waits for"
    return record w entry key []
  | "named" =>
    if !w.name.isEmpty then throw "a world named twice"
    let name ← outcome.getObjValAs? String "name"
    unless validWorldName name do throw "a world name outside the rule"
    return record { w with name } entry key []
  | "principal" =>
    discard <| outcome.getObjValAs? String "did"
    discard <| outcome.getObjValAs? String "handle"
    if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then throw "principal recorded by another principal"
    return record w entry key []
  | "reserved" =>
    if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then throw "post reserved by another principal"
    let source ← outcome.getObjValAs? String "source"
    unless (← natField outcome "hour") == postHour w do throw "a reservation not in its clock hour"
    if (postRefusal w source).isSome then throw "a reservation past its source's quota"
    return record w entry key []
  | "released" =>
    if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then throw "post released by another principal"
    let some r := w.reservations[← outcome.getObjValAs? String "intent"]? | throw "release of an unknown reservation"
    if r.posted || r.released then throw "release of a settled reservation"
    return record w entry key []
  | "attempted" =>
    unless principal == interpretationPrincipal do throw "an attempt under another identity than the interpreter's"
    let id ← outcome.getObjValAs? String "id"
    unless w.suspended.any (fun s => ((s.getObjVal? "outcome").toOption.bind fun o => (o.getObjVal? "interpretation").toOption
        |>.bind fun i => (i.getObjValAs? String "id").toOption) == some id) do
      throw "an attempt at an unknown or settled interpretation"
    unless (← natField outcome "attempt") == ((w.attempts[id]?).map (·.1)).getD 0 + 1 do throw "attempts out of order"
    return record w entry key []
  | "posted" =>
    let uri ← outcome.getObjValAs? String "uri"
    let object ← outcome.getObjValAs? String "object"
    if w.posts.contains uri then throw "post recorded twice"
    unless w.objects.contains object do throw "post for an unknown object"
    if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then throw "post confirmed by another principal"
    let slot ← match outcome.getObjVal? "slot" with
      | .ok s => pure (some (← parseSlot s))
      | .error _ => pure none
    let (page, part) ← postedPage outcome
    if let .ok i := outcome.getObjValAs? String "intent" then
      match w.reservations[i]? with
      | some r => if r.released || r.posted then throw "a post settles a settled reservation"
      | none => throw "a post settles an unknown reservation"
    return record (postIndex w uri { object, slot, page, part, height := ← natField entry "height" }) entry key [object]
  | "suspended" =>
    unless hostResumed entry do
      let checkpoint ← expandSuspended w entry
      let tokens ← Delvetalk.Turn.tokensOfJson (← checkpoint.getObjVal? "tokens")
      unless (← checkpoint.getObjValAs? String "digest") == Delvetalk.Turn.checkpointDigest
          (← checkpoint.getObjValAs? String "packetSha256") (← checkpoint.getObjValAs? String "object")
          (← checkpoint.getObjValAs? String "principal") (← checkpoint.getObjValAs? String "intent")
          (← checkpoint.getObjValAs? String "rootsDigest") tokens do
        throw "checkpoint digest does not match its tokens"
    -- A suspension waits on a slot, or on the reply that answers a post.
    if (outcome.getObjValAs? String "post").toOption.isNone then discard <| outcome.getObjVal? "slot"
    discard <| natField outcome "deadline"
    return record w entry key []
  | "library" =>
    let recorded ← parseModules (← outcome.getObjVal? "modules")
    let lib ← sealLibrary recorded
    unless lib.modules == recorded && lib.pin == (← outcome.getObjValAs? String "pin") do
      throw "library entry is not the seal of its modules"
    unless (← outcome.getObjValAs? String "previous") == ((w.library.map (·.pin)).getD "") do
      throw "library entry does not replace the current library"
    let lawText ← if w.library.isNone then outcome.getObjValAs? String "law" else pure w.libraryLaw
    if let some clause := libraryRefusal lawText principal (w.height + 1) lib.pin then
      throw s!"library change would be refused by the world law ({clause})"
    return record (installLibrary w lib lawText) entry key []
  | "interpreted" =>
    let id ← outcome.getObjValAs? String "id"
    unless principal == interpretationPrincipal && intent == id do
      throw "interpretation runs under another identity than its request's"
    unless w.suspended.any (fun s => ((s.getObjVal? "outcome").toOption.bind fun o => (o.getObjVal? "interpretation").toOption
        |>.bind fun i => (i.getObjValAs? String "id").toOption) == some id) do
      throw "interpretation of an unknown or already settled request"
    discard <| outcome.getObjVal? "reply"
    let verdict ← outcome.getObjVal? "verdict"
    unless ["proposal", "proposals", "unclear"].contains (← verdict.getObjValAs? String "tag") do throw "unknown verdict"
    return record w entry key []
  | "created" =>
    let id ← outcome.getObjValAs? String "object"
    if w.objects.contains id then throw s!"object {id} created twice"
    let inputs ← expandInputs w (← outcome.getObjVal? "compile")
    let owner := (outcome.getObjValAs? String "owner").toOption
    if owner.isSome && (w.opener.isEmpty || principal != w.opener) then throw "an owner named by another than the opener"
    let (o, sources, w) ← buildObjectIn w inputs (← outcome.getObjVal? "seed") (outcome.getObjVal? "read").toOption (outcome.getObjVal? "chain").toOption (owner.getD principal) (w.height + 1)
      (outcome.getObjValAs? String "law").toOption
    -- The pin binds the sources; the packet this compiler made of them is only counted if it differs.
    unless o.pin == (← outcome.getObjValAs? String "pin") && sources == o.pin do
      throw s!"object {id} is not the source closure its pin names"
    if let .ok text := outcome.getObjValAs? String "lawText" then
      unless text == o.lawText do throw s!"object {id} is not made with the law its creation journaled"
    unless (outcome.getObjValAs? String "cid").toOption == some o.stateCid do
      throw s!"object {id} is not made at the state CID its creation journaled"
    if let .ok cid := outcome.getObjValAs? String "placed" then
      unless cid == placedCid o do throw s!"object {id} is not made with the rows its creation journaled"
    let w := noteRecompiled w o
    let o := { o with supervisor := (outcome.getObjValAs? String "supervisor").toOption.getD "" }
    return record (noteMinted { w with objects := w.objects.insert id o } id) entry key [id]
  | "refused" =>
    let cls ← outcome.getObjValAs? String "class"
    unless refusalClasses.contains cls do throw s!"unknown refusal class {cls}"
    let flipped := refusalWants w outcome
    for k in ["wanted", "unwanted"] do
      unless flipped.lookup k == (entry.getObjVal? k).toOption do throw s!"what the refusal {k} does not replay"
    return record w entry key []
  | "admitted" =>
    let rawWrites ← (← outcome.getObjVal? "writes").getArr?
    let writes ← parseRecordedWrites (Json.arr rawWrites)
    let turn ← natField entry "turn"
    let recordedPrograms := (outcome.getObjVal? "reprograms").toOption.bind (·.getArr?.toOption) |>.getD #[]
    let recordedLaws := (outcome.getObjVal? "amendments").toOption.bind (·.getArr?.toOption) |>.getD #[]
    let programs ← recordedPrograms.toList.mapM fun r => do
      return (← r.getObjValAs? String "object", (← r.getObjValAs? String "source", ← r.getObjValAs? String "migration"))
    let layered := recordedPrograms.toList.filterMap fun r =>
      if (r.getObjValAs? String "mode").toOption == some "extend" then (r.getObjValAs? String "object").toOption else none
    let madeFrom : List (String × Json) := recordedPrograms.toList.filterMap fun r =>
      match r.getObjValAs? String "object", r.getObjVal? "madeFrom" with
      | .ok o, .ok m => some (o, m)
      | _, _ => none
    let laws ← recordedLaws.toList.mapM fun r => do
      return (← r.getObjValAs? String "object", ← r.getObjValAs? String "new")
    let recordedCreates := (outcome.getObjVal? "creates").toOption.bind (·.getArr?.toOption) |>.getD #[]
    let (w, creates) ← rebuildCreates w principal recordedCreates
    let absent := ((entry.getObjVal? "absent").toOption.bind (·.getArr?.toOption) |>.getD #[]).toList.filterMap
      fun a => a.getStr?.toOption
    let grants ← ((outcome.getObjVal? "grants").toOption.bind (·.getArr?.toOption) |>.getD #[]).toList.mapM Grant.ofJson
    let revokes ← ((outcome.getObjVal? "revokes").toOption.bind (·.getArr?.toOption) |>.getD #[]).toList.mapM (·.getStr?)
    for (g, i) in grants.zipIdx do
      unless g.id == grantId principal intent i && g.grantor == principal do throw "a grant is not its turn's"
    let spent ← parseSpent (outcome.getObjVal? "spent").toOption
    let (roots, cells) ← parseRoots (← entry.getObjVal? "roots")
    let rebaseOwn := if (entry.getObjVal? "resumes").toOption.isSome then roots.head?.map (·.1) else none
    let placements ← ((outcome.getObjVal? "placements").toOption.bind (·.getArr?.toOption) |>.getD #[]).toList.mapM Placement.ofJson
    -- A delivered entry's sender is the pending send it consumes (checked by `checkDelivery`).
    let delivered := ((entry.getObjVal? "delivery").toOption.bind fun d => (d.getObjValAs? String "id").toOption)
    let sender := (delivered.bind fun id => w.pending.find? fun s => (s.getObjValAs? String "id").toOption == some id).bind
      (fun s => (s.getObjValAs? String "sender").toOption) |>.getD ""
    let p : Proposal := { principal, intent, roots, rebaseOwn, writes, turn, programs, laws,
                          absent, creates, grants, revokes, spent, layered, cells, madeFrom, sender,
                          placements }
    unless turn == w.height + 1 do throw "turn is not the height of its entry"
    unless (entry.getObjValAs? String "request").toOption == some p.digest do throw "request digest does not match"
    let w := warmLaws w (p.writes.map (·.1))
    match judge w (w.height + 1) p with
    | .error r => throw s!"admitted entry would be refused ({r.cls})"
    | .ok judged =>
      unless judged.reprograms == recordedPrograms.toList && judged.amendments == recordedLaws.toList &&
          judged.creates == recordedCreates.toList do
        throw "recorded reprograms, amendments or creations do not replay"
      for x in rawWrites do
        let id := (x.getObjValAs? String "object").toOption.getD ""
        let recorded := ((x.getObjVal? "evicted").toOption.bind (·.getArr?.toOption)).getD #[]
        unless recorded == ((judged.evicted.lookup id).getD #[]) do
          throw s!"the rows retention evicted from {id} do not replay"
      let w := (judged.updates.filter (fun (id, _) => judged.reprograms.any fun r =>
          (r.getObjValAs? String "object").toOption == some id) ++ judged.creations).foldl (fun w (_, o) => noteRecompiled w o) w
      let updates := judged.updates
      for raw in rawWrites do
        let id ← raw.getObjValAs? String "object"
        let some (_, o) := updates.find? (·.1 == id) | throw "write missing"
        unless (← natField raw "version") == o.version do throw "write version out of sequence"
        -- The state an admitted write commits to (host7; earlier entries name none).
        if let some cid := (raw.getObjValAs? String "cid").toOption then
          unless cid == o.stateCid do throw s!"the state of {id} does not replay to the CID its write recorded"
      let entryLedger ← match entry.getObjVal? "ledger" with
        | .ok l => ledgerOf l
        | .error _ => pure Ledger.start
      let usedTicks := (entry.getObjValAs? Nat "ticksUsed").toOption.getD 0
      let before := w
      let w := updates.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      let w := judged.creations.foldl (fun w (id, o) => noteMinted { w with objects := w.objects.insert id o } id) w
      let w := applyGrants w grants revokes spent
      -- The rules it fired and the wants it opened and closed are re-derived and must be the ones journaled.
      let child := childLedger before entryLedger usedTicks (updates ++ judged.creations) p.allWrites
      let reacted := reactions before w (before.height + 1) judged child (ruleDepthOf before delivered)
      for k in ["fired", "unfired", "wanted", "unwanted"] do
        unless reacted.lookup k == (entry.getObjVal? k).toOption do
          throw s!"what the write {k} does not replay"
      if let .ok recorded := outcome.getObjVal? "placed" then
        unless (placedField before (updates ++ judged.creations)).lookup "placed" == some recorded do
          throw "the rows the write placed do not replay"
      let holders := (grants.map (·.holder)).filter fun h => !updates.any (·.1 == h)
      return record w entry key (updates.map (·.1) ++ judged.creations.map (·.1) ++ holders.eraseDups)
  | other => throw s!"unknown outcome {other}"

/-- One entry of a replay under the world's ignore set (docs/ROOT.md §1.3): an ignored height is
    recorded as refused, with no effect; after an ignored height, an entry that no longer replays is
    shadowed (skipped, listed with the ignored height before it and the reason); before any, a
    disagreement breaks the journal as it always has. -/
def replayStep (w : World) (entry : Json) : Except String World :=
  let height := w.height + 1
  if w.ignoring.contains height then .ok (recordInert w entry) else
  match replayEntry w entry with
  | .ok w' => .ok w'
  | .error e => match (w.ignoreNamed.filter (· < height)).max? with
    | some by_ => .ok (recordInert { w with shadowed := w.shadowed.push (Json.mkObj
        [("height", toJson height), ("by", toJson by_), ("reason", toJson e)]) } entry)
    | none => .error e

/-! ## The clock -/

/-- `world-advance {height}`: the only clock the world has. Moving it is journaled so
    replay is deterministic; moving it to or before now is a no-op. -/
def advance (w : World) (j : Json) : Except String (World × Json) := do
  let to ← natField j "height"
  if !w.clockPrincipal.isEmpty then
    let who := (← optText j "principal").getD ""
    if who != w.clockPrincipal then throw s!"the clock is moved only by {w.clockPrincipal}"
  if to ≤ w.clock then
    return (w, Json.mkObj [("status", toJson "advanced"), ("clock", toJson w.clock)])
  let intent := s!"advance:{to}"
  let (w', entry) := push w (identityKey "clock" intent)
    [("identity", identityJson "clock" intent), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson (Journal.bodyHash (toJson intent))),
     ("outcome", Json.mkObj [("tag", toJson "advanced"), ("from", toJson w.clock), ("to", toJson to)])] []
  return (w', Json.mkObj [("status", toJson "advanced"), ("clock", toJson to), ("receipt", entry)])

/-! ## Reads -/

/-- Ids the reader may view, starting with `prefix`, after `after` in byte order: one page,
    and whether more follow. -/
def listIds (w : World) (reader pfx after : String) : List String × Bool :=
  let ids := (w.objects.toList.filterMap fun (id, o) =>
    if id.startsWith pfx && decide (after < id) && o.read.permits reader then some id else none).toArray.qsort (· < ·)
  ((ids.extract 0 Limits.listPage).toList, ids.size > Limits.listPage)

/-- `world-objects {principal, prefix?, after?}`. -/
def objectsOp (w : World) (j : Json) : Except String Json := do
  let principal ← readerOf j
  let text := fun (k : String) => match j.getObjVal? k with
    | .ok (.str s) => pure s
    | .ok _ => throw s!"{k} must be text"
    | .error _ => pure ""
  let (ids, more) := listIds w principal (← text "prefix") (← text "after")
  let withMethods ← match j.getObjVal? "methods" with
    | .ok (.bool b) => pure b
    | .ok _ => throw "methods must be true or false"
    | .error _ => pure false
  let listed := [("status", toJson "listed"), ("ids", toJson ids), ("more", toJson more)]
  if !withMethods then return Json.mkObj listed
  -- The turnable method names (those that take a context) of each listed object.
  let names := fun (o : Object) => (((offeredRows o.methods).getArr?.toOption).getD #[]).toList.filterMap fun m =>
    if (m.getObjValAs? Bool "context").toOption == some true then (m.getObjValAs? String "name").toOption else none
  return Json.mkObj (listed ++ [("methods", Json.mkObj (ids.filterMap fun id =>
    (w.objects[id]?).map fun o => (id, toJson (names o))))])

def view (w : World) (j : Json) : Except String Json := do
  let id ← j.getObjValAs? String "object"
  let principal ← readerOf j
  match w.objects[id]? with
  | none => return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  | some o =>
    if !o.read.permits principal then
      return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
    return Json.mkObj [("status", toJson "viewed"), ("object", toJson id),
      ("version", toJson o.version), ("state", dataJson o.state), ("pin", toJson o.pin)]

/-- The CID of `id`'s state at `version`, as the journal names it: the current state's, a created
    or child seed's (version 0), or the `cid` of the admitted write that made the version (host7; a
    write journaled before names none). -/
def stateCidAt (w : World) (id : String) (version : Nat) : Option String := Id.run do
  let some o := w.objects[id]? | return none
  if o.version == version then return some o.stateCid
  for i in (w.touched[id]?).getD #[] do
    let some entry := w.entries.get? i | continue
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let arr := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
    let named := fun (j : Json) => (j.getObjValAs? String "object").toOption == some id
    match tagOf entry with
    | "created" =>
      if version == 0 && named outcome then
        if let .ok cid := outcome.getObjValAs? String "cid" then return some cid
    | "admitted" =>
      for x in arr "writes" do
        if named x && (x.getObjValAs? Nat "version").toOption == some version then
          return (x.getObjValAs? String "cid").toOption
      if version == 0 then
        for c in arr "creates" do
          if named c then
            if let .ok cid := c.getObjValAs? String "cid" then return some cid
    | _ => pure ()
  return none

/-- The object's state at `version`, rebuilt from the journal: its created seed (or a creating turn's
    seed), then each admitted write of it in order, re-applying its edits under the object's relations
    (or taking a reprogram's recorded result), each checked against the CID its write recorded. None
    when the version is past the current one, the object came from a fork genesis before it, or a
    rebuilt state is not the one the journal names (a relation declaration a reprogram changed). -/
def stateAt (w : World) (id : String) (version : Nat) : Option Data := Id.run do
  let some o := w.objects[id]? | return none
  if version == o.version then return some o.state
  if version > o.version then return none
  let decls := cellDecls o.relations
  -- A seed is the state at version 0 when its cells are those the creation journaled (a seed may name
  -- only some fields, the rest from `initial()`).
  let seedOf := fun (j : Json) => do
    let seed ← (decodeData Limits.dataDepth (← (j.getObjVal? "seed").toOption)).toOption
    let cells := Delvetalk.Turn.StateCells.of decls (← (canonicalState o.relations seed).toOption)
    if (j.getObjValAs? String "cid").toOption == some cells.cid then some cells else none
  let mut state : Option Delvetalk.Turn.StateCells := none
  for i in (w.touched[id]?).getD #[] do
    let some entry := w.entries.get? i | continue
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let arr := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
    let named := fun (j : Json) => (j.getObjValAs? String "object").toOption == some id
    match tagOf entry with
    | "created" => if named outcome then state := seedOf outcome
    | "admitted" =>
      for c in arr "creates" do
        if named c then state := seedOf c
      for x in arr "writes" do
        unless named x do continue
        let some v := (x.getObjValAs? Nat "version").toOption | return none
        if v > version then return state.map (·.state)
        let some before := state | return none
        let next? : Option Delvetalk.Turn.StateCells := match (arr "reprograms").find? named with
          | some r => (r.getObjVal? "result").toOption.bind fun j =>
            (decodeData Limits.dataDepth j).toOption.map (Delvetalk.Turn.StateCells.of decls)
          | none => ((x.getObjVal? "edits").toOption.bind (parseSteps · |>.toOption)).bind fun steps =>
            (applyEdits o.relations before steps).toOption.map (·.cells)
        let some next := next? | return none
        if let .ok cid := x.getObjValAs? String "cid" then
          if cid != next.cid then return none
        state := some next
    | _ => pure ()
    if version == 0 && state.isSome then return state.map (·.state)
  return none

/-- `world-state-cid {principal, object, version}`: the CID of the object's state at that version, for
    a reader who may view it (a CID of a state the reader may not see would let it test guesses):
    `{status: "stateCid", object, version, cid}`, `denied`, or `unknown` (no such object, version, or
    a version only a write from before host7 made). -/
def stateCidOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let id ← j.getObjValAs? String "object"
  let version ← natField j "version"
  let answer := fun (status : String) (more : List (String × Json)) =>
    Json.mkObj ([("status", toJson status), ("object", toJson id), ("version", toJson version)] ++ more)
  match w.objects[id]? with
  | none => return answer "unknown" []
  | some o =>
    if !o.read.permits reader then return answer "denied" []
    match stateCidAt w id version with
    | some cid => return answer "stateCid" [("cid", toJson cid)]
    | none => return answer "unknown" []

/-- A reader may see an object's changes if it may view the object (an object no longer in
    the world is not viewable). -/
def viewable (w : World) (reader id : String) : Bool :=
  match w.objects[id]? with
  | some o => o.read.permits reader
  | none => false

/-- The public projection of a refusal: observed, not committed, the class and the root it
    names, and nothing else. `root` is `{object, version}`, the version the turn read it at (a reader
    who may view the object reads that state's CID with `world-state-cid`); an `unknownObject` refusal also names the
    id the author wrote (as resolved, so `me` reads the author's DID) and where the list of cards is. -/
def publicRefusal (entry : Json) : Json :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let named := (outcome.getObjValAs? String "object").toOption.getD ""
  -- A refusal judged against another root than the id it names (`requiredAbsence`: the creating
  -- object, read at a version, beside the id it found taken) commits to that root.
  let id := (outcome.getObjValAs? String "root").toOption.getD named
  let cls := (outcome.getObjValAs? String "class").toOption.getD "unknown"
  let roots := (entry.getObjVal? "roots").toOption.getD (Json.arr #[])
  let version := (((parseRoots roots).toOption.map (·.1)).getD []).lookup id
  let root := Json.mkObj ([("object", toJson id)] ++ (version.map fun v => [("version", toJson v)]).getD [])
  -- A law's reading is the law's public text about the clause, never state.
  let law := if cls == "lawRefused" then ["reason", "reading"].filterMap fun k => (outcome.getObjVal? k).toOption.map (k, ·) else []
  let slug := (entry.getObjValAs? String "hash").toOption.bind Slug.ofCid
  Json.mkObj ([("status", toJson "refused"), ("class", toJson cls), ("root", root)] ++
    (slug.map fun x => [("slug", toJson x)]).getD [] ++ law ++
    (if cls == "unknownObject" then
      [("object", toJson id), ("hint", toJson s!"no card named {id}; the commonplace lists the doors")]
    -- A spell that did not fit: which part, where, and the spell to resend; all from the reply itself.
    else if cls == "badSpell" then
      [("object", toJson named)] ++ ["clause", "reason", "hint"].filterMap fun k => (outcome.getObjVal? k).toOption.map (k, ·)
    -- A quota: how many, and when the next may start; nothing about the turn.
    else if cls == "quota" || cls == "quiet" then ["clause", "reason", "next"].filterMap fun k => (outcome.getObjVal? k).toOption.map (k, ·)
    else if id != named then [("object", toJson named)] else []))

/-- An entry as `reader` may see it. The identity's own principal sees it whole. Anyone else
    sees a refusal only as its public projection, and any other entry as its chain fields,
    identity, turn and outcome tag, with the roots and writes of objects it may view; the rest
    is elided and counted. Results, offers, sends, sources and checkpoints never show. -/
def projectEntry (w : World) (reader : String) (entry : Json) : Json :=
  let owner := ((entry.getObjVal? "identity").toOption.bind fun i => (i.getObjValAs? String "principal").toOption).getD ""
  if owner == reader && !reader.isEmpty then slugged entry
  -- A root entry is whole to every reader, `before` included (docs/ROOT.md §1.2), and so is the
  -- opener's moderation and a turn root ran `as` another.
  else if tagOf entry == "root" || tagOf entry == "moderated" then slugged entry
  else if tagOf entry == "refused" then
    (publicRefusal entry).setObjVal! "height" ((entry.getObjVal? "height").toOption.getD Json.null)
      |>.setObjVal! "hash" ((entry.getObjVal? "hash").toOption.getD Json.null)
  else slugged <|
    let objectOf := fun (x : Json) => (x.getObjValAs? String "object").toOption.getD ""
    let arr := fun (x : Option Json) => ((x.bind (·.getArr?.toOption)).getD #[])
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let roots := arr (entry.getObjVal? "roots").toOption
    let writes := arr (outcome.getObjVal? "writes").toOption
    let shownRoots := roots.filter fun r => viewable w reader (objectOf r)
    let shownWrites := writes.filter fun x => viewable w reader (objectOf x)
    let elided := (roots.size - shownRoots.size) + (writes.size - shownWrites.size)
    Json.mkObj ((["height", "previous", "hash", "identity", "turn"].filterMap fun k =>
        (entry.getObjVal? k).toOption.map (k, ·)) ++
      [("roots", Json.arr shownRoots),
       ("outcome", Json.mkObj ([("tag", toJson (tagOf entry))] ++
         (if writes.isEmpty then [] else [("writes", Json.arr shownWrites)]))),
       ("elided", toJson elided)])

/-- A text's clauses, every modality, as the one parser reads it (`parseClauses`): the keyword, the
    name, the reading (if any) and the body after the `:` as the one renderer writes it (`COND`, `COND
    then SPELL`, `COND asks SPELL`). A text that does not parse has none. -/
def textClauses (text : String) : List (String × String × Option String × String) :=
  ((parseClauses text).toOption.getD []).map fun c =>
    let body := c.condition.render ++ match c.modality with
      | .law => ""
      | .rule spell => " then " ++ spell.render
      | .want spell => " asks " ++ spell.render
    (c.modality.keyword, c.name, (if c.reading.isEmpty then none else some c.reading), body)

/-- A law text with the `retired` clause (ROOT 2.2) appended, which admits only the opener's amendment:
    the root `retire`, the card power `retire / reading:` and a carry's `--leave` write this one clause.
    `none` when the text is retired already. -/
def retiredLaw (text reading opener : String) : Option String :=
  if (textClauses text).any (·.2.1 == "retired") then none else
  let clause := s!"law retired \"{reading}\": request.kind == 2 and request.subject == \"{opener}\""
  some (if text.isEmpty then clause else s!"{text}\n{clause}")

/-- A law text with its `retired` clause removed (`unretire`). -/
def unretiredLaw (text : String) : String :=
  "\n".intercalate ((text.splitOn "\n").filter fun l => !(l.trimAscii.toString.startsWith "law retired "))

/-- The text's clauses as `(name, body, reading)`, the reading the text gives, else the package's while
    its clause stands ("" for none): the `inspect` Plan's `laws`, rules and wants among them. -/
def lawRowsOf (o : Object) : List (String × String × String) :=
  (textClauses o.lawText).map fun (_, name, reading, body) =>
    (name, body, ((reading.orElse fun _ => o.readings.lookup name)).getD "")

/-- An object's text as clauses with their keywords and readings: a reading the text gives, else the
    one the package gave the clause while it stands (`Object.readings`). What `world-inspect` answers
    as `laws` and the library's `law {card}` page reads. -/
def lawRows (o : Object) : Json :=
  Json.arr ((textClauses o.lawText).toArray.map fun (keyword, name, reading, body) =>
    Json.mkObj ([("name", toJson name), ("keyword", toJson keyword), ("clause", toJson body)] ++
      ((reading.orElse fun _ => o.readings.lookup name).map fun r => [("reading", toJson r)]).getD []))

/-- A rule a thing carries, as `rules` reads it (docs/FOUNDATION.md §10, the readback a wake never had): its
    name, owner (and handle), reading, condition, spell, line and the object holding it; when a hand
    placed it, the height; its last firing (`fired {height, id, receipt}`, the receipt the slug of the
    turn it delivered once that ran) or refusal to fire (`unfired {height, why}`). -/
def ruleRow (w : World) (id : String) (c : CarriedClause) : Json :=
  let last := (w.ruleLog[id]?).bind (·.lookup c.clause.name)
  let receipt := last.bind fun l => (l.getObjValAs? String "id").toOption.bind fun d =>
    (w.receipts[identityKey c.owner d]?).bind w.entries.hashAt? |>.bind Slug.ofCid
  Json.mkObj ([("name", toJson c.clause.name), ("owner", toJson c.owner), ("handle", toJson (handleOf w c.owner)),
      ("when", toJson c.clause.condition.render), ("then", toJson ((c.clause.modality.spell?.map (·.render)).getD "")),
      ("line", toJson c.clause.render), ("from", toJson c.holder)] ++
    (if c.clause.reading.isEmpty then [] else [("reading", toJson c.clause.reading)]) ++
    ((c.placed.map fun h => [("placed", toJson h)]).getD []) ++
    ((last.map fun l => if (l.getObjVal? "why").toOption.isSome then [("unfired", l)]
      else [("fired", (receipt.map fun r => l.setObjVal! "receipt" (toJson r)).getD l)]).getD []))

/-- What answers a want, filled at the read for `reader` (`Law.fill` over `Law.asItStands`): the line's
    template when a hole reads nothing, or the want cites what the reader may not view. -/
def wantAsks (w : World) (reader : String) (facts : Law.Facts) (id : String) (o : Object) (c : CarriedClause) : String :=
  let template := (c.clause.modality.spell?.map (·.render)).getD ""
  if (unviewable w reader (citesOf w c.clause.names).objects).isSome then template else
  ((c.clause.modality.spell?).bind (Law.fill (Law.asItStands facts id) none o.state)).getD template

/-- The wants that hold of `id` as it stands now, as `wants` reads them: name, owner, reading,
    condition, the spell that answers it (`wantAsks`, for its reader), the line, the object holding it,
    and `since`: the height of the entry that made it true, or `clock` when it came true by the clock alone. -/
def wantRows (w : World) (reader id : String) (o : Object) : List Json :=
  let facts := wantFacts w w.height id o
  (posing w w.height id o).map fun c =>
    let since := ((w.wanting[id]?).bind (·.lookup c.clause.name)).map toJson |>.getD (toJson "clock")
    Json.mkObj ([("name", toJson c.clause.name), ("owner", toJson c.owner), ("when", toJson c.clause.condition.render),
        ("asks", toJson (wantAsks w reader facts id o c)), ("line", toJson c.clause.render), ("from", toJson c.holder), ("since", since)] ++
      (if c.clause.reading.isEmpty then [] else [("reading", toJson c.clause.reading)]))

/-- One row of the world's wanting index as `wanting` reads it: the thing, the want's name and reading,
    what answers it (`wantAsks`), and the height of the entry that made it true. -/
structure Wanted where
  object : String
  name : String
  reading : String
  asks : String
  since : Nat

/-- What wants a hand across the world (`world.wanting {after, limit}`, `world-wanting`): each row of the
    wanting index (`World.wanting`) whose want still holds of its thing as it stands, for things `reader`
    may view, newest first (by `since`, then thing and name). A page holds whole heights, each below
    `after` (0: from the newest), while it stays within `limit` rows (0, or past `Limits.listPage`, is
    `listPage`); its first height is whole whatever its size, so `after` set to a page's last `since`
    reads on without a gap. `more` when older rows remain. A want that came true by the clock alone,
    with no entry to make it, is not in the index: the thing's `wants` reads it. Derived, no root. -/
def wanting (w : World) (reader : String) (after limit : Nat) : List Wanted × Bool := Id.run do
  let rows : List Wanted := w.wanting.toList.flatMap fun (id, xs) => match w.objects[id]? with
    | none => []
    | some o =>
      if !o.read.permits reader then [] else
      let holding := posing w w.height id o
      let facts := wantFacts w w.height id o
      xs.filterMap fun (name, since) =>
        if after != 0 && since ≥ after then none else
        (holding.find? (·.clause.name == name)).map fun c =>
          { object := id, name, reading := c.clause.reading, asks := wantAsks w reader facts id o c, since }
  let sorted := (rows.toArray.qsort fun (a b : Wanted) =>
    a.since > b.since || (a.since == b.since && (a.object < b.object || (a.object == b.object && a.name < b.name)))).toList
  let cap := if limit == 0 then Limits.listPage else min limit Limits.listPage
  let mut page : Array Wanted := #[]
  let mut rest := sorted
  while true do
    let some first := rest.head? | break
    let group := rest.takeWhile (·.since == first.since)
    unless page.isEmpty || page.size + group.length ≤ cap do break
    page := page ++ group.toArray
    rest := rest.drop group.length
  return (page.toList, !rest.isEmpty)

/-- `world-wanting {principal?, after?, limit?}` → `{status: wanting, rows: [{object, name, reading?, asks,
    since}], more}` (`wanting`). -/
def wantingOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let nat := fun (k : String) => (j.getObjValAs? Nat k).toOption.getD 0
  let (rows, more) := wanting w reader (nat "after") (nat "limit")
  return Json.mkObj [("status", toJson "wanting"), ("more", toJson more), ("rows", Json.arr (rows.toArray.map fun r =>
    Json.mkObj ([("object", toJson r.object), ("name", toJson r.name), ("asks", toJson r.asks), ("since", toJson r.since)] ++
      (if r.reading.isEmpty then [] else [("reading", toJson r.reading)]))))]

/-- `world-rules {object, principal?}`: every rule `object` carries (`ruleRow`), for a reader who may
    view it. `world-wants {object, principal?}`: the wants that hold of it now (`wantRows`). Derived
    reads: no root, no entry. -/
def rulesOp (w : World) (j : Json) (wants : Bool) : Except String Json := do
  let reader ← readerOf j
  let id ← j.getObjValAs? String "object"
  let some o := w.objects[id]? | return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  if !o.read.permits reader then return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
  let rows := if wants then wantRows w reader id o else (carriedRules w id o).map (ruleRow w id)
  return Json.mkObj [("status", toJson (if wants then "wants" else "rules")), ("object", toJson id), ("rows", Json.arr rows.toArray)]

/-- Why a rule that held was not cast, in words (`Ops.reactions`'s `why`). -/
def unfiredWords : String → String
  | "hole" => "a hole in its spell read nothing"
  | "spell" => "its filled line is not a spell"
  | "noOwner" => "nobody owns it to act as"
  | "quiet" => "its owner is quieted"
  | "ruleDepth" => s!"the chain of rules is {Limits.ruleDepth} deep"
  | "rulesPerCommit" => s!"{Limits.rulesPerCommit} rules fired on this write already"
  | "pending" => s!"the world holds {Limits.maxPending} undelivered sends"
  | "reads" => "its owner may not view what it reads"
  | other => other

/-- One thing a day of the journal did to a thing (`chronicleDay`): `made`, `grew` (a verb), `fired` or
    `unfired` (a rule), `wanted` or `unwanted`; `who` is the hand or the rule's owner as shown, `name` the
    verb, rule or want, `why` an unfired rule's reason, `entry` the height. -/
structure DayEvent where
  what : String
  object : String
  who : String := ""
  name : String := ""
  why : String := ""
  entry : Nat

/-- A clock day of the journal (`World.days`), folded: its entries, what they did to things the reader may
    view, the refusals by class and the hands that acted, by handle. `none` when nothing was journaled. -/
structure Day where
  day : Nat
  start : Nat
  stop : Nat
  admitted : Nat
  events : List DayEvent
  refusals : List (String × Nat)
  hands : List String

def chronicleDay (w : World) (reader : String) (day : Nat) : Option Day := Id.run do
  let some i := w.days.findIdx? (·.1 == day) | return none
  let start := w.days[i]!.2
  let stop := ((w.days[i + 1]?).map (·.2)).getD (w.height + 1)
  let mut events : Array DayEvent := #[]
  let mut refusals : List (String × Nat) := []
  let mut hands : Array String := #[]
  let mut admitted := 0
  for h in [start:stop] do
    let some e := w.entries.get? (h - 1) | continue
    let who := ((e.getObjVal? "identity").toOption.bind (·.getObjValAs? String "principal" |>.toOption)).getD ""
    let outcome := (e.getObjVal? "outcome").toOption.getD Json.null
    let rows := fun (j : Json) (k : String) => (((j.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]).toList
    let text := fun (j : Json) (k : String) => (j.getObjValAs? String k).toOption.getD ""
    let seen := fun (id : String) => viewable w reader id
    match tagOf e with
    | "refused" =>
      let cls := text outcome "class"
      refusals := if refusals.any (·.1 == cls) then refusals.map fun (c, n) => (c, if c == cls then n + 1 else n)
        else refusals ++ [(cls, 1)]
    | "created" =>
      if !hands.contains (shownName w who) then hands := hands.push (shownName w who)
      if seen (text outcome "object") then events := events.push { what := "made", object := text outcome "object", who := shownName w who, entry := h }
    | "admitted" =>
      admitted := admitted + 1
      if !who.isEmpty && !hands.contains (shownName w who) then hands := hands.push (shownName w who)
      for c in rows outcome "creates" do
        if seen (text c "object") then events := events.push { what := "made", object := text c "object", who := shownName w who, entry := h }
      for x in rows outcome "placements" do
        if seen (text x "object") && !(text x "verb").isEmpty && !(text x "reading").isEmpty then
          events := events.push { what := "grew", object := text x "object", who := shownName w who, name := text x "verb", entry := h }
      for f in rows e "fired" do
        if seen (text f "sender") then
          events := events.push { what := "fired", object := text f "sender", who := shownName w (text f "principal"), name := text f "rule", entry := h }
      for f in rows e "unfired" do
        if seen (text f "object") then
          events := events.push { what := "unfired", object := text f "object", who := shownName w (text f "owner"), name := text f "rule",
                                  why := unfiredWords (text f "why"), entry := h }
    | _ => pure ()
    -- An admitted write's wants, and a law refusal's (`refusalWants`).
    for x in rows e "wanted" do
      if seen (text x "object") then events := events.push { what := "wanted", object := text x "object", name := text x "want", entry := h }
    for x in rows e "unwanted" do
      if seen (text x "object") then events := events.push { what := "unwanted", object := text x "object", name := text x "want", entry := h }
  return some { day, start, stop, admitted, events := events.toList, refusals, hands := hands.toList }

/-- A day event as the chronicle's line. -/
def DayEvent.line (e : DayEvent) : String :=
  match e.what with
  | "made" => s!"made {e.object} ({e.who}, entry {e.entry})"
  | "grew" => s!"grew {e.name} on {e.object} ({e.who}, entry {e.entry})"
  | "fired" => s!"rule {e.name} of {e.who} fired on {e.object} at entry {e.entry}"
  | "unfired" => s!"rule {e.name} of {e.who} did not fire on {e.object} at entry {e.entry}: {e.why}"
  | "wanted" => s!"{e.object} came to want {e.name} at entry {e.entry}"
  | _ => s!"{e.object} stopped wanting {e.name} at entry {e.entry}"

/-- `world-chronicle {principal, day}` (docs/FOUNDATION.md §10; OVERHAUL §2 conflict 6): one clock day of the
    journal folded into lines (`chronicleDay`), derived at the read and never written. The day's span is
    `World.days`; each line names what an entry of it did to a thing the reader may view: made, grown (a
    verb), fired or not, came to want or stopped; then the refusals by class and the hands that acted, by
    handle. At most `Limits.chronicleLines` lines of things, the rest counted. -/
def chronicle (w : World) (reader : String) (day : Nat) : List String :=
  match chronicleDay w reader day with
  | none => [s!"day {day}: nothing was journaled."]
  | some d =>
    let shown := (d.events.take Limits.chronicleLines).map DayEvent.line
    let more := d.events.length - shown.length
    [s!"day {day}: entries {d.start} to {d.stop - 1}, {d.admitted} admitted."] ++ shown ++
      (if more == 0 then [] else [s!"and {more} more."]) ++
      (if d.refusals.isEmpty then [] else ["refused: " ++ ", ".intercalate (d.refusals.map fun (c, n) => s!"{n} {c}")]) ++
      (if d.hands.isEmpty then [] else ["hands: " ++ ", ".intercalate d.hands])

def chronicleOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let day ← match j.getObjValAs? Nat "day" with
    | .ok d => pure d
    | .error _ => pure (w.clock / Limits.clockDay)
  return Json.mkObj [("status", toJson "chronicled"), ("day", toJson day), ("lines", toJson (chronicle w reader day))]

/-- The pin and law text `id` had at `version`: its current ones, with each later reprogram and
    amendment undone (newest first), as the admitted entries that made later versions record them. -/
def pinAndLawAt (w : World) (o : Object) (id : String) (version : Nat) : String × String := Id.run do
  let mut pin := o.pin
  let mut law := o.lawText
  for i in ((w.touched[id]?).getD #[]).reverse do
    let some entry := w.entries.get? i | continue
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let arr := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
    let named := fun (x : Json) => (x.getObjValAs? String "object").toOption == some id
    let later := (arr "writes").any fun x => named x && ((x.getObjValAs? Nat "version").toOption.getD 0) > version
    if !later then continue
    for r in arr "reprograms" do
      if named r then pin := (r.getObjValAs? String "oldPin").toOption.getD pin
    for a in arr "amendments" do
      if named a then law := (a.getObjValAs? String "old").toOption.getD law
  return (pin, law)

/-- `world-object {principal, object, version?}`: the object as of `version` (default current): its pin and
    law in force then, the law's clauses with their readings, the state CID the journal names, and the
    library pin its code was compiled under. `denied` and `unknown` as `world-state-cid` answers them. -/
def objectOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let id ← j.getObjValAs? String "object"
  let unknown := Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  let some o := w.objects[id]? | return unknown
  if !o.read.permits reader then return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
  let version := (← optNat j "version").getD o.version
  if version > o.version then return unknown
  let some cid := stateCidAt w id version | return unknown
  let (pin, law) := pinAndLawAt w o id version
  let clauses := (textClauses law).map fun (_, n, r, b) => (n, r, b)
  let current := (textClauses o.lawText).map fun (_, n, r, b) => (n, r, b)
  -- A clause's reading: the one its law text gives, else the package's while the clause is the package's.
  let readingOf := fun (name : String) (reading : Option String) (expr : String) =>
    reading.orElse fun _ => if (current.find? (·.1 == name)).map (·.2.2) == some expr then o.readings.lookup name else none
  let rows := clauses.map fun (name, reading, expr) => (name, readingOf name reading expr, expr)
  let library := (o.inputs.getObjValAs? String "library").toOption
  return Json.mkObj [("status", toJson "object"), ("record", Json.mkObj ([("object", toJson id), ("version", toJson version),
    ("pin", toJson pin), ("pinSlug", toJson ((Slug.ofCid pin).getD "")), ("law", toJson law),
    ("readings", Json.arr (rows.toArray.filterMap fun (n, r, _) => r.map fun r => Json.mkObj [("name", toJson n), ("reading", toJson r)])),
    ("laws", Json.arr (rows.toArray.map fun (n, r, e) => Json.mkObj ([("object", toJson id), ("version", toJson version),
      ("pin", toJson pin), ("name", toJson n), ("clause", toJson e)] ++ (r.map fun r => [("reading", toJson r)]).getD []))),
    ("stateCid", toJson cid)] ++ (library.map fun l => [("library", toJson l)]).getD []))]

/-- `world-dump {principal, object}` (docs/ROOT.md §1.6): what the root console's editor shows beside
    `world-view`, `world-object` and `world-sources`: the owner, the read policy, the fixed fields, the
    supervisor, the ledger, and the activities waiting (each suspension's hash, principal, method,
    what it waits on and its deadline). The opener's, on the root socket. -/
def dumpOp (w : World) (j : Json) : Except String Json := do
  let principal ← j.getObjValAs? String "principal"
  if !openerActs w principal then throw "world-dump is the opener's, on the root socket"
  let id ← j.getObjValAs? String "object"
  let some o := w.objects[id]? | return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  let activities := w.suspended.filterMap fun s => do
    let outcome ← (s.getObjVal? "outcome").toOption
    let act ← (outcome.getObjVal? "activity").toOption
    guard ((act.getObjValAs? String "object").toOption == some id)
    let identity := (s.getObjVal? "identity").toOption.getD Json.null
    return Json.mkObj ([("hash", (s.getObjVal? "hash").toOption.getD Json.null),
      ("principal", (identity.getObjVal? "principal").toOption.getD Json.null),
      ("intent", (identity.getObjVal? "intent").toOption.getD Json.null),
      ("method", (act.getObjVal? "method").toOption.getD Json.null)] ++
      (["post", "slot", "deadline", "interpretation"].filterMap fun k => (outcome.getObjVal? k).toOption.map (k, ·)))
  return Json.mkObj [("status", toJson "dump"), ("object", toJson id), ("version", toJson o.version),
    ("owner", toJson (ownerOf o.state)), ("read", o.read.json), ("fixed", toJson o.fixed),
    ("supervisor", toJson o.supervisor), ("ledger", o.chain.json), ("activities", Json.arr activities)]

/-- A page of `(height, item)` pairs, ascending by height: after `after` (exclusive), or with
    `reverse: true` descending below `before` (exclusive; from the newest when absent); at most `limit`
    (1..100, default 100). A `cursor` (`"<height>.<n>"`, the `n`th item of that height, as a page's
    reply names its last item) continues exactly where a page stopped, in either order, so items
    sharing a height are never skipped (codex transport 12); `after`/`before` page by whole heights.
    The items, whether more follow, and the cursor of the last item shown when they do. -/
def pageByHeight {α : Type} (j : Json) (items : Array (Nat × α)) : Except String (Array α × Bool × Option String) := do
  let limit := (← optNat j "limit").getD Limits.maxHistoryLimit
  if limit == 0 || limit > Limits.maxHistoryLimit then throw s!"limit must be 1..{Limits.maxHistoryLimit}"
  let reverse ← match j.getObjVal? "reverse" with
    | .ok (.bool b) => pure b
    | .ok _ => throw "reverse must be true or false"
    | .error _ => pure false
  -- Each item's place: its height and its ordinal among the items of that height.
  let placed : Array ((Nat × Nat) × α) := (items.foldl (fun (acc : Array ((Nat × Nat) × α) × Nat × Nat) (h, x) =>
    let (out, lastH, n) := acc
    let k := if h == lastH && !out.isEmpty then n + 1 else 0
    (out.push ((h, k), x), h, k)) (#[], 0, 0)).1
  let lt := fun (a b : Nat × Nat) => a.1 < b.1 || (a.1 == b.1 && a.2 < b.2)
  let cursor ← match (j.getObjValAs? String "cursor").toOption with
    | none => pure none
    | some c => match c.splitOn "." with
      | [h, k] => match h.toNat?, k.toNat? with
        | some h, some k => pure (some (h, k))
        | _, _ => throw "cursor must be <height>.<n>"
      | _ => throw "cursor must be <height>.<n>"
  let chosen ← if reverse then do
      let before ← optNat j "before"
      pure (placed.reverse.filter fun (p, _) => before.all (p.1 < ·) && cursor.all (lt p ·))
    else do
      let after := (← optNat j "after").getD 0
      pure (placed.filter fun (p, _) => p.1 > after && cursor.all (lt · p))
  let shown := chosen.extract 0 limit
  let more := decide (chosen.size > limit)
  let last := if more then shown.back?.map fun ((h, k), _) => s!"{h}.{k}" else none
  return (shown.map (·.2), more, last)

/-- A page reply's paging fields: `more`, and `cursor` when more follow. -/
def pageFields (more : Bool) (cursor : Option String) : List (String × Json) :=
  [("more", toJson more)] ++ (cursor.map fun c => [("cursor", toJson c)]).getD []

/-- Every source the journal carries, as `(height, record {cid, name, text, height})`: an entry's `sources`
    (named as the compile inputs that introduced it name it) and a library entry's modules, each once,
    at the first entry that carried it. -/
def sourceRecords (w : World) : Array (Nat × String × Json) := Id.run do
  let mut names : Std.HashMap String String := {}
  for i in [0:w.entries.count] do
    let some entry := w.entries.get? i | continue
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let compiles := ((outcome.getObjVal? "compile").toOption.toList ++
      (((outcome.getObjVal? "creates").toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap fun c => (c.getObjVal? "compile").toOption)
    for c in compiles do
      for m in ((c.getObjVal? "modules").toOption.bind (·.getArr?.toOption)).getD #[] do
        if let (.ok n, .ok cid) := (m.getObjValAs? String "name", m.getObjValAs? String "cid") then
          unless names.contains cid do names := names.insert cid n
  let mut out : Array (Nat × String × Json) := #[]
  let mut seen : Std.HashSet String := {}
  for i in [0:w.entries.count] do
    let some entry := w.entries.get? i | continue
    let height := i + 1
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let carried := (((entry.getObjVal? "sources").toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap fun x =>
      match x.getObjValAs? String "cid", x.getObjValAs? String "source" with
      | .ok c, .ok t => some (c, (names.get? c).getD "", t)
      | _, _ => none
    let library := if tagOf entry != "library" then [] else
      (((outcome.getObjVal? "modules").toOption.bind (parseModules · |>.toOption)).getD []).map fun (n, t) => (sourceCid t, n, t)
    for (cid, name, text) in carried ++ library do
      if seen.contains cid then continue
      seen := seen.insert cid
      out := out.push (height, cid, Json.mkObj [("cid", toJson cid), ("name", toJson name), ("text", toJson text),
        ("height", toJson height)])
  return out

/-- The source CIDs `reader` may read: the modules of every object it may view, and the libraries'. -/
def readableSources (w : World) (reader : String) : Std.HashSet String := Id.run do
  let mut out : Std.HashSet String := {}
  for (_, l) in w.libraries.toList do
    for (_, src) in l.modules do out := out.insert (sourceCid src)
  for (_, o) in w.objects.toList do
    if o.read.permits reader then
      for src in inputSources o.inputs do out := out.insert (sourceCid src)
  return out

/-- `world-source {principal, cid}`: `{status: "source", record: {cid, name, text, height}}`, `denied` unless
    an object the reader may view has it in its closure (or a library has it), `unknown` when the journal
    carries no such source. -/
def sourceOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let cid ← j.getObjValAs? String "cid"
  match (sourceRecords w).find? (·.2.1 == cid) with
  | none => return Json.mkObj [("status", toJson "unknown"), ("message", toJson s!"unknown: no source here is {cid}")]
  | some (_, _, record) =>
    if !(readableSources w reader).contains cid then return Json.mkObj [("status", toJson "denied"), ("cid", toJson cid)]
    return Json.mkObj [("status", toJson "source"), ("record", record)]

/-- `world-sources {principal, after?, before?, reverse?, limit?}`: the sources the reader may read, paged by
    the height of the entry that carried each. -/
def sourcesOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let readable := readableSources w reader
  let (shown, more, cursor) ← pageByHeight j ((sourceRecords w).filterMap fun (h, cid, r) => if readable.contains cid then some (h, r) else none)
  return Json.mkObj ([("status", toJson "sources"), ("sources", Json.arr shown)] ++ pageFields more cursor)

/-- `world-grants {principal, after?, before?, reverse?, limit?}`: every grant an admitted entry made whose
    object the reader may view, as it stands now (`revoked`, `uses` left), with the `height` and `hash` of
    the entry that made it, paged by that height. -/
def grantsOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let mut items : Array (Nat × Json) := #[]
  for i in [0:w.entries.count] do
    let some entry := w.entries.get? i | continue
    if tagOf entry != "admitted" then continue
    let made := ((entry.getObjVal? "outcome").toOption.bind (·.getObjVal? "grants" |>.toOption) |>.bind (·.getArr?.toOption)).getD #[]
    for g in made do
      let some id := (g.getObjValAs? String "id").toOption | continue
      let some now := w.grants[id]? | continue
      unless viewable w reader now.object do continue
      items := items.push (i + 1, (now.json.setObjVal! "revoked" (toJson now.revoked)).setObjVal! "height" (toJson (i + 1))
        |>.setObjVal! "hash" ((entry.getObjVal? "hash").toOption.getD Json.null))
  let (shown, more, cursor) ← pageByHeight j items
  return Json.mkObj ([("status", toJson "grants"), ("grants", Json.arr shown)] ++ pageFields more cursor)

/-- `world-entry {principal, hash, bytes?}`: the entry whose hash it is, as the reader may see it
    (`projectEntry`), and with `bytes: true` the lowercase hex of its canonical DAG-CBOR without `hash`
    when the reader sees it whole (the identity's own principal); `unknown` otherwise. -/
def entryOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let hash ← j.getObjValAs? String "hash"
  let some entry := (w.entries.indexOf? hash).bind w.entries.get?
    | return Json.mkObj [("status", toJson "unknown"), ("message", toJson s!"unknown: no entry here is {hash}")]
  let owner := ((entry.getObjVal? "identity").toOption.bind fun i => (i.getObjValAs? String "principal").toOption).getD ""
  let whole := owner == reader && !reader.isEmpty
  let bytes ← if whole && (j.getObjValAs? Bool "bytes").toOption == some true then do
      let fields := ((entry.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "hash")
      pure [("bytes", toJson (Delvetalk.Canonical.hex (← Delvetalk.Canonical.encodeJson (Json.mkObj fields))))]
    else pure []
  return Json.mkObj ([("status", toJson "receipt"), ("receipt", projectEntry w reader entry)] ++ bytes)

/-- `world-entries {principal, after?, before?, reverse?, limit?}`: every entry, each as the reader may
    see it, paged by height (`pageByHeight`). -/
def entriesOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let (shown, more, cursor) ← pageByHeight j ((Array.range w.entries.count).map fun i => (i + 1, i))
  return Json.mkObj ([("status", toJson "entries"), ("entries", Json.arr (shown.map (projectEntry w reader ∘ w.entries.getD)))] ++
    pageFields more cursor)

/-- Everything a slug may name, as `(cid, kind)`: every entry's hash (`receipt`); every pin an
    entry gave an object `reader` may view (`pin`); the state CIDs the journal names for such an
    object: a created seed, a write's `cid` (`state`). -/
def slugTargets (w : World) (reader : String) : Array (String × String) := Id.run do
  let mut out : Array (String × String) := #[]
  let seen := fun (id : String) => viewable w reader id
  for i in [0:w.entries.count] do
    let some entry := w.entries.get? i | continue
    if let .ok h := entry.getObjValAs? String "hash" then out := out.push (h, "receipt")
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let arr := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
    let object := fun (j : Json) => (j.getObjValAs? String "object").toOption.getD ""
    match tagOf entry with
    | "created" =>
      if seen (object outcome) then
        if let .ok p := outcome.getObjValAs? String "pin" then out := out.push (p, "pin")
        if let .ok cid := outcome.getObjValAs? String "cid" then out := out.push (cid, "state")
    | "admitted" =>
      for c in arr "creates" do
        if seen (object c) then
          if let .ok p := c.getObjValAs? String "pin" then out := out.push (p, "pin")
          if let .ok cid := c.getObjValAs? String "cid" then out := out.push (cid, "state")
      for r in arr "reprograms" do
        if seen (object r) then
          if let .ok p := r.getObjValAs? String "newPin" then out := out.push (p, "pin")
      for x in arr "writes" do
        if seen (object x) then
          if let .ok c := x.getObjValAs? String "cid" then out := out.push (c, "state")
    | "forked" | "carried" =>
      -- The installed store: each object's pin and state as the genesis holds them.
      let rows := ((outcome.getObjVal? "state").toOption.bind (·.getObjVal? "objects" |>.toOption) |>.bind (·.getArr?.toOption)).getD #[]
      for o in rows do
        if seen ((o.getObjValAs? String "id").toOption.getD "") then
          if let .ok p := o.getObjValAs? String "pin" then out := out.push (p, "pin")
          if let .ok c := o.getObjValAs? String "stateCid" then out := out.push (c, "state")
      -- A carry's old chains, every generation: their receipts resolve as entries of the world before.
      for (h, _) in carriedEntries entry do out := out.push (h, "carried")
    | _ => pure ()
  return out

/-- `world-resolve {principal, slug}`: the one CID the slug names among what `principal` may see
    (`slugTargets`): `{status: "resolved", slug, kind: receipt | pin | state, cid, receipt?}`, with the
    receipt as `world-receipt` renders it to that reader when it names one; `{status: "ambiguous",
    matches}` when it names two or more CIDs; `{status: "unknown"}` when none. -/
def resolveOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let slug ← j.getObjValAs? String "slug"
  if (Slug.decode slug).isNone then throw s!"{slug} is not a slug: two proquint words, like lusab-babad"
  let hits := (slugTargets w reader).foldl (fun (acc : Array (String × String)) (cid, kind) =>
    if Slug.ofCid cid == some slug && !acc.any (·.1 == cid) then acc.push (cid, kind) else acc) #[]
  match hits.toList with
  | [] => return Json.mkObj [("status", toJson "unknown"), ("slug", toJson slug),
      ("message", toJson s!"unknown: no receipt, pin or state here is named {slug}")]
  | [(cid, "carried")] =>
    -- A receipt of a world this one was carried from: its height there, and that world.
    let (height, origin) := (((w.entries.get? 0).map carriedEntries).getD #[] |>.find? (·.1 == cid) |>.map (·.2)).getD (0, Json.null)
    let world := (origin.getObjValAs? String "world").toOption.getD ""
    return Json.mkObj [("status", toJson "resolved"), ("slug", toJson slug), ("kind", toJson "receipt"), ("cid", toJson cid),
      ("carried", Json.mkObj [("world", toJson world), ("height", toJson height), ("at", (origin.getObjVal? "height").toOption.getD Json.null)]),
      ("message", toJson s!"entry {height} of the world before the carry ({world})")]
  | [(cid, kind)] =>
    let receipt := if kind != "receipt" then none else
      ((w.entries.indexOf? cid).bind w.entries.get?).map (projectEntry w reader)
    return Json.mkObj ([("status", toJson "resolved"), ("slug", toJson slug), ("kind", toJson kind),
      ("cid", toJson cid)] ++ (receipt.map fun r => [("receipt", r)]).getD [])
  | many => return Json.mkObj [("status", toJson "ambiguous"), ("slug", toJson slug), ("matches", toJson many.length),
      ("message", toJson s!"ambiguous: {many.length} matches; cite the object and version")]


/-- `world-receipt {principal, identity, of?}`: the receipt of identity (`of`, default the
    reader, `identity`), projected under the reader's authority; a refusal with its `public` projection. -/
def receipt (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let owner := (← optText j "of").getD reader
  match boundEntry w owner intent with
  | none => return Json.mkObj [("status", toJson "unknown")]
  | some entry =>
    let shown := projectEntry w reader entry
    if owner != reader && tagOf entry == "refused" then return publicRefusal entry
    -- A refusal's owner also gets what may be said of it in public, which a draft of it carries.
    return Json.mkObj ([("status", toJson "receipt"), ("receipt", shown)] ++
      (if tagOf entry == "refused" then [("public", publicRefusal entry)] else []))

def history (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let id ← j.getObjValAs? String "object"
  let after := (← optNat j "after").getD 0
  let asked := (← optNat j "limit").getD Limits.maxHistoryLimit
  if asked == 0 || asked > Limits.maxHistoryLimit then throw s!"limit must be 1..{Limits.maxHistoryLimit}"
  if !w.objects.contains id then return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  if !viewable w reader id then return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
  let all := (w.touched.getD id #[]).filter fun index => index + 1 > after
  let page := all.extract 0 asked
  return Json.mkObj [("status", toJson "history"), ("object", toJson id),
    ("entries", Json.arr (page.map fun index => projectEntry w reader (w.entries.getD index))),
    ("more", toJson (decide (all.size > asked)))]

/-- The principal transport reads publications as: the world's clock principal, or "transport". -/
def publisher (w : World) : String := if w.clockPrincipal.isEmpty then "transport" else w.clockPrincipal

/-- The direct turn a turn descends from, through the causal ledger: a delivered turn's
    `delivery.from` names the sending turn's identity, whose entry may itself be a delivery, up to
    the ledger's depth. Answered as `{post, principal, intent}`, `post` the turn's `replyTo` when it
    answered a recorded post, else its intent (the bridge's identity for an observed post). -/
def originOf (w : World) (entry : Json) : Json := Id.run do
  let mut e := entry
  for _ in [0:Limits.maxDepth] do
    let some sender := ((e.getObjVal? "delivery").toOption.bind (·.getObjVal? "from" |>.toOption)) | break
    let (.ok p, .ok i) := (sender.getObjValAs? String "principal", sender.getObjValAs? String "intent") | break
    let some index := w.receipts[identityKey p i]? | break
    let some next := w.entries.get? index | break
    e := next
  let identity := (e.getObjVal? "identity").toOption.getD Json.null
  let intent := (identity.getObjValAs? String "intent").toOption.getD ""
  Json.mkObj [("post", toJson ((e.getObjValAs? String "replyTo").toOption.getD intent)),
    ("principal", (identity.getObjVal? "principal").toOption.getD Json.null), ("intent", toJson intent)]

/-- `world-offers {principal, after?}`: the offers addressed to the principal, oldest first,
    after journal height `after`; one page. Each offer carries `from`, the turn it answers (`originOf`). The publisher also gets the `publications`
    (`{height, ordinal, id, object, page, section, text}`) to post. -/
def offersOp (w : World) (j : Json) : Except String Json := do
  let principal ← readerOf j
  let after := (← optNat j "after").getD 0
  let all := (w.outbox.getD principal #[]).filter fun (index, _) => index + 1 > after
  let page := all.extract 0 Limits.maxHistoryLimit
  let items := page.filterMap fun (index, i) => do
    let entry ← w.entries.get? index
    let offer ← ((entry.getObjVal? "offers").toOption.bind (·.getArr?.toOption)).bind (·[i]?)
    pure (Json.mkObj [("height", toJson (index + 1)), ("ordinal", toJson i),
      ("identity", (entry.getObjVal? "identity").toOption.getD Json.null),
      -- The turn the offer answers: the entry's own, or for a handed-on (delivered) turn the
      -- direct turn it descends from, so the bridge drafts it against the originating post.
      ("from", originOf w entry),
      ("text", (offer.getObjVal? "text").toOption.getD Json.null)])
  let pubs := if principal != publisher w then #[] else
    let mine := w.published.filter fun (index, _) => index + 1 > after
    (mine.extract 0 Limits.maxHistoryLimit).filterMap fun (index, i) => do
      let entry ← w.entries.get? index
      let p ← ((entry.getObjVal? "publishes").toOption.bind (·.getArr?.toOption)).bind (·[i]?)
      let fields ← p.getObj?.toOption
      pure (Json.mkObj ([("height", toJson (index + 1)), ("ordinal", toJson i)] ++ fields.toList))
  return Json.mkObj ([("status", toJson "offers"), ("offers", Json.arr items), ("more", toJson (decide (all.size > page.size)))] ++
    (if principal == publisher w then [("publications", Json.arr pubs)] else []))


/-- The newest whole-page post recorded for each object's page, by `identityKey object page`:
    the post a section edit of that page replies to. -/
def pagePosts (w : World) : Std.HashMap String (Nat × String) :=
  w.posts.fold (init := {}) fun m uri p =>
    if p.page.isEmpty || !p.part.isEmpty then m else
    let key := identityKey p.object p.page
    match m[key]? with
    | some (h, _) => if h ≥ p.height then m else m.insert key (p.height, uri)
    | none => m.insert key (p.height, uri)

/-- `world-publications {principal, after?, before?, reverse?, limit?}`: the publications admitted turns
    retained, for every reader (a publication is posted publicly), paged by height (`pageByHeight`):
    `{height, ordinal, id, object, page, section, body, hash}` (`hash` the retaining entry's), and
    `replyTo` for a section edit when a post of its whole page is recorded (the newest). -/
def publicationsOp (w : World) (j : Json) : Except String Json := do
  discard <| readerOf j
  let posts := pagePosts w
  -- The page is chosen by height first: only its entries are read.
  let (chosen, more, cursor) ← pageByHeight j (w.published.map fun (index, i) => (index + 1, (index, i)))
  let shown := chosen.filterMap fun (index, i) => do
    let entry ← w.entries.get? index
    let p ← ((entry.getObjVal? "publishes").toOption.bind (·.getArr?.toOption)).bind (·[i]?)
    let field := fun (k : String) => (p.getObjValAs? String k).toOption
    let object ← field "object"
    let title ← field "page"
    let part ← field "section"
    let text ← field "text"
    -- The retained text is the agentwiki header, a blank line, then the body.
    let body := "\n\n".intercalate (text.splitOn "\n\n").tail
    let replyTo := if part.isEmpty then [] else
      match posts[identityKey object title]? with
      | some (_, uri) => [("replyTo", toJson uri)]
      | none => []
    pure (Json.mkObj ([("height", toJson (index + 1)), ("ordinal", toJson i),
      ("id", (p.getObjVal? "id").toOption.getD Json.null), ("object", toJson object), ("page", toJson title),
      ("section", toJson part), ("body", toJson body),
      ("hash", (entry.getObjVal? "hash").toOption.getD Json.null)] ++ replyTo))
  return Json.mkObj ([("status", toJson "publications"), ("publications", Json.arr shown)] ++ pageFields more cursor)

end Delvetalk.Host

namespace Delvetalk.Host
open Lean in
#guard [Json.null, .bool true, .bool false, toJson (5 : Nat), toJson (-3 : Int), .str "a\"b\\c\n\u0001é", .arr #[],
  .arr #[toJson (1 : Nat), .str "x"], Json.mkObj [],
  Json.mkObj [("k", toJson (1 : Nat)), ("q\"", .arr #[Json.mkObj [("z", .null)]])]].all fun j => compressedSize j == j.compress.utf8ByteSize
end Delvetalk.Host
