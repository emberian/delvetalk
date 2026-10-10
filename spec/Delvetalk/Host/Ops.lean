/- The world kernel and its session ops. `commit` and friends are pure: the turn
   loop calls them with a proposal and gets the next World and a receipt. The IO
   layer at the bottom owns the journal file and nothing else. -/
import Delvetalk.Host.Store
import Delvetalk.Host.Journal
import Delvetalk.Host.Law
import Delvetalk.Host.Slug
import Compiler.ObjectiveBendDataWire

namespace Delvetalk.Host
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Theory.ObjectiveBendTypes (DataBounds)
open Minidregg.Compiler.ObjectiveBendDataWire (dataJson decodeData)

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

/-- An object id a creation may take: 1..128 bytes of letters, digits and `. _ : / -`, so every object has an
    AT record key (`~` stands for `/` there). Journals with other ids still replay; only new creations
    are held to it. -/
def validObjectId (id : String) : Bool :=
  !id.isEmpty && id.utf8ByteSize ≤ Limits.maxObjectIdBytes && id != worldId &&
    id.toList.all fun (c : Char) => c.isAlphanum || ".:_/-".toList.contains c

def objectIdRule : String := "an object id is 1..128 bytes of letters, digits and . _ : / -, and not world"

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
  /-- The first item whose canonical bytes are `item`'s, replaced by `change` or removed. The
      label is the constructor the object used (`amendItem`/`removeItem` in Plan.obend, or
      `amend`/`remove` with an `item` payload), kept so the journal records what was written. -/
  | amendBy (label : String) (item change : Data)
  | removeBy (label : String) (item : Data)
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
  | .amendBy l item c => .variant l (.record [("item", item), ("change", c)])
  | .removeBy l item => .variant l (.record [("item", item)])
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
  | .variant "remove" (.record f) => (f.lookup "item").map (.removeBy "remove")
  | .variant "amend" (.record f) => match f.lookup "item", f.lookup "change" with
      | some item, some c => some (.amendBy "amend" item c)
      | _, _ => none
  | .variant "removeItem" (.record f) => (f.lookup "item").map (.removeBy "removeItem")
  | .variant "insert" (.record f) => (f.lookup "row").map .insert
  | .variant "upsert" (.record f) => (f.lookup "row").map .upsert
  | .variant "retract" (.record f) => (f.lookup "key").map .retract
  | .variant "amendItem" (.record f) => match f.lookup "item", f.lookup "change" with
      | some item, some c => some (.amendBy "amendItem" item c)
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
  /-- Subscriptions the turn makes and ends (WHOLENESS §3); they take effect with the commit. -/
  subscribes : List Subscription := []
  unsubscribes : List Subscription := []
  /-- Fields of objects the turn read alone (`viewField`), at the version it read. -/
  fieldRoots : List (String × String × Nat) := []
  /-- A resumed turn's own object: it may be re-based on the object's current state when it
      moved while the turn waited (`movedRootAdmits`). An entry with `resumes` sets it on replay. -/
  rebaseOwn : Option String := none

/-- Writes, plus a direct (caller-less) change of the proper kind for each reprogram or
    amendment that no write of the proposal already names. -/
def Proposal.allWrites (p : Proposal) : List (String × List Written) :=
  let wanted := p.programs.map (fun x => (x.1, 1)) ++ p.laws.map (fun x => (x.1, 2))
  wanted.foldl (fun acc (id, kind) =>
    let have_ := ((acc.lookup id).getD []).any (·.kind == kind)
    if have_ then acc
    else if acc.any (·.1 == id) then
      acc.map fun (i, ws) => if i == id then (i, ws ++ [{ caller := "", kind, edits := [] }]) else (i, ws)
    else acc ++ [(id, [{ caller := "", kind, edits := [] }])]) p.writes

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

/-- The bytes of a state as the bound counts them: its wire JSON, compressed. -/
def stateBytes (state : Data) : Nat := compressedSize (dataJson state)

/-- The CID of an object's state: its canonical bytes as the journal hashes them, so a root
    names exactly the card version a turn was judged against. -/
def stateCid (state : Data) : String := Journal.bodyHash (dataJson state)

/-- Roots as an entry records them: object and version. The state at that version is named by the
    entry that wrote it (`writes[].cid`, `world-state-cid`). -/
def rootsJson (roots : List (String × Nat)) : Json :=
  Json.arr (roots.toArray.map fun (o, v) => Json.mkObj [("object", toJson o), ("version", toJson v)])

/-- Field roots (WHOLENESS §3a): a turn that read one field of an object (`viewField`) conflicts only
    with later writes of that field. Journaled in `roots` beside the object roots as `{object, field,
    key: "*", version}`; the `key` is `*` because the host does not see which rows a turn's code read
    (that waits on lazy state cells, KERNEL-HANDOFF §15). -/
def fieldRootsJson (roots : List (String × String × Nat)) : Array Json :=
  roots.toArray.map fun (o, f, v) => Json.mkObj [("object", toJson o), ("field", toJson f), ("key", toJson "*"), ("version", toJson v)]

/-- An entry's `roots`: the object roots, then the field roots. -/
def allRootsJson (roots : List (String × Nat)) (fieldRoots : List (String × String × Nat)) : Json :=
  match rootsJson roots with
  | .arr a => .arr (a ++ fieldRootsJson fieldRoots)
  | other => other

/-- The fields recording who made each change: parallel arrays of steps, callers, kinds. -/
def writtenFields (ws : List Written) : List (String × Json) :=
  [("edits", stepsJson (ws.map (·.edits))), ("callers", toJson (ws.map (·.caller))),
   ("kinds", toJson (ws.map (·.kind)))] ++
  (if ws.all (·.method.isEmpty) then [] else [("methods", toJson (ws.map (·.method)))]) ++
  (if ws.all (·.via.isEmpty) then [] else [("vias", toJson (ws.map (·.via)))]) ++
  (if ws.all (fun w => match w.argument with | .record [] => true | _ => false) then []
   else [("arguments", Json.arr (ws.toArray.map (dataJson ·.argument)))])

def writesJson (writes : List (String × List Written)) : Json :=
  Json.arr (writes.toArray.map fun (o, ws) => Json.mkObj (("object", toJson o) :: writtenFields ws))

def parseRoots (j : Json) : Except String (List (String × Nat)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxRoots then throw "too many roots"
  let mut out : List (String × Nat) := []
  for r in raw do
    if (r.getObjVal? "field").toOption.isSome then continue
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← r.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate root"
    out := out ++ [(object, ← natField r "version")]
  return out

/-- The field roots among an entry's `roots` (`fieldRootsJson`). -/
def parseFieldRoots (j : Json) : Except String (List (String × String × Nat)) := do
  let raw ← j.getArr?
  let mut out : List (String × String × Nat) := []
  for r in raw do
    let some field := (r.getObjValAs? String "field").toOption | continue
    unless (r.getObjValAs? String "key").toOption == some "*" do throw "a field root's key is *"
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← r.getObjValAs? String "object")
    if out.any (fun (o, f, _) => o == object && f == field) then throw "duplicate root"
    out := out ++ [(object, field, ← natField r "version")]
  return out

/-- Writes as a client sends them: direct, so every step has the empty caller. A client
    cannot name a caller. -/
def parseWrites (j : Json) : Except String (List (String × List Written)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxWrites then throw "too many writes"
  let mut out : List (String × List Written) := []
  for w in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← w.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate write"
    out := out ++ [(object, (← parseSteps (← w.getObjVal? "edits")).map fun step => { caller := "", edits := step })]
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
    let arguments ← match w.getObjVal? "arguments" with
      | .ok a => (← a.getArr?).toList.mapM (decodeData Limits.dataDepth)
      | .error _ => pure (steps.map fun _ => Data.record [])
    unless callers.length == steps.length && kinds.length == steps.length && methods.length == steps.length &&
        vias.length == steps.length && arguments.length == steps.length do
      throw "a write's callers, kinds, methods, vias and arguments must match its edits"
    out := out ++ [(object, (steps.zip (callers.zip (kinds.zip (methods.zip (vias.zip arguments))))).map
      fun (step, caller, kind, method, via, argument) => { caller, kind, edits := step, method, via, argument })]
  return out

/-- A direct proposal. A write must name an object among its roots; `turn` is the
    host's to assign, so a request that carries one is refused. -/
def parseProposal (j : Json) : Except String Proposal := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  if (j.getObjVal? "turn").toOption.isSome then throw "turn is assigned by the host and cannot be supplied"
  let roots ← parseRoots (← j.getObjVal? "roots")
  let writes ← parseWrites (← j.getObjVal? "writes")
  for (id, _) in writes do
    unless roots.any (·.1 == id) do throw s!"write names {id}, which is not among the roots"
  return { principal, intent, roots, writes }

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
  Journal.bodyHash (Json.mkObj ([("roots", rootsJson p.roots), ("writes", writesJson p.allWrites)] ++
    (if p.fieldRoots.isEmpty then [] else [("fieldRoots", Json.arr (fieldRootsJson p.fieldRoots))]) ++
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
    (if p.subscribes.isEmpty then [] else [("subscribes", Json.arr (p.subscribes.toArray.map (·.json)))]) ++
    (if p.unsubscribes.isEmpty then [] else [("unsubscribes", Json.arr (p.unsubscribes.toArray.map (·.json)))])))

/-! ## Judging -/

/-- The closed set of refusal classes. -/
def refusalClasses : List String :=
  ["staleRoot", "typeMismatch", "capacity", "absentItem", "lawRefused", "unknownObject",
   "duplicateIdentity", "evaluation", "budget", "budgetExhausted", "programRefused", "requiredAbsence",
   "keyTaken", "duplicateKey", "badSpell", "quota"]

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

def replaceField (fields : List (String × Data)) (name : String) (v : Data) : List (String × Data) :=
  fields.map fun (k, old) => if k == name then (k, v) else (k, old)

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

def bytesLt (a b : ByteArray) : Bool := Id.run do
  for i in [0:min a.size b.size] do
    if a[i]! != b[i]! then return a[i]! < b[i]!
  return a.size < b.size

/-- Rows sorted by their keys' canonical bytes, no key twice (`duplicateKey`), the oldest by key
    order dropped past the declared limit. -/
def canonicalRows (d : RelDecl) (rows : List Data) : EditResult (List Data) := do
  let keyed ← rows.mapM fun r => do return (Delvetalk.Canonical.encode (← keyOf d r), r)
  let sorted := (keyed.toArray.qsort fun a b => bytesLt a.1 b.1).toList
  let mut prev : Option ByteArray := none
  for (k, _) in sorted do
    if prev == some k then throw "duplicateKey"
    prev := some k
  return (sorted.drop (sorted.length - d.cap)).map (·.2)

def canonicalRelation (d : RelDecl) (v : Data) : EditResult Data := do
  return relationOf (← canonicalRows d (← relationRows v))

/-- Every declared relation of a state record in canonical form. -/
def canonicalState (decls : List RelDecl) : Data → EditResult Data
  | .record fields => do
    return .record (← fields.mapM fun (k, v) => match decls.find? (·.field == k) with
      | some d => do return (k, ← canonicalRelation d v)
      | none => pure (k, v))
  | other => if decls.isEmpty then pure other else throw "typeMismatch"

/-- One relation edit on a canonical relation (the table of RELATIONAL.md §3):

    | edit    | key absent | key present, same row | key present, other row |
    | insert  | add        | no change             | refused `keyTaken`     |
    | upsert  | add        | no change             | replace                |
    | retract | no change  | remove                | remove                 | -/
def relationEdit (d : RelDecl) (old : Data) (kind : EditKind) : EditResult Data := do
  let rows ← relationRows old
  let keyed ← rows.mapM fun r => do return (Delvetalk.Canonical.encode (← keyOf d r), r)
  let others := fun (k : ByteArray) => (keyed.filter (·.1 != k)).map (·.2)
  match kind with
  | .insert row | .upsert row =>
    let k := Delvetalk.Canonical.encode (← keyOf d row)
    match keyed.find? (·.1 == k) with
    | none => canonicalRelation d (relationOf (rows ++ [row]))
    | some (_, r) =>
      if Delvetalk.Canonical.encode r == Delvetalk.Canonical.encode row then pure old
      else match kind with
        | .insert _ => throw "keyTaken"
        | _ => canonicalRelation d (relationOf (others k ++ [row]))
  | .retract key =>
    let k := Delvetalk.Canonical.encode (← keyAsDeclared d key)
    if keyed.any (·.1 == k) then pure (relationOf (others k)) else pure old
  | _ => throw "typeMismatch"

/-- All edits of a step read the state before the step. A relation field takes `insert`, `upsert`,
    `retract` (`relationEdit`); any other edit of it is followed by putting it back in canonical form. -/
def applyStep (decls : List RelDecl) (fields : List (String × Data)) (step : Step) : EditResult (List (String × Data)) :=
  step.foldlM (init := fields) fun acc e => do
    let some old := fields.lookup e.field | throw "typeMismatch"
    let decl := decls.find? (·.field == e.field)
    let put := fun (v : Data) => match decl with
      | some d => do return replaceField acc e.field (← canonicalRelation d v)
      | none => pure (replaceField acc e.field v)
    match e.kind with
    | .keep => pure acc
    | .set v => put v
    | .add n => match old with
        | .natural m => put (.natural (m + n))
        | _ => throw "typeMismatch"
    | .append item => put (← appendItem item old)
    | .amendBy _ item c => put (← editByItem item (some c) old)
    | .removeBy _ item => put (← editByItem item none old)
    | .insert _ | .upsert _ | .retract _ => match decl with
      | some d => pure (replaceField acc e.field (← relationEdit d old e.kind))
      | none => throw "typeMismatch"

def applyEdits (decls : List RelDecl) : Data → List Step → EditResult Data
  | .record fields, steps => (steps.foldlM (applyStep decls) fields).map .record
  | _, _ => throw "typeMismatch"

/-! ## Law as state, and programs -/

/-- The state type is the type of the package's entry definition: a zero-argument
    `def initial() -> State` has type `State`, which must be a closed record of
    first-order data. The entry's own value is not used; the seed is explicit. -/
def stateTypeOk (assumptions : Minidregg.Theory.ObjectiveBendTyping.Assumptions)
    (ty : Minidregg.Theory.ObjectiveBendTypes.Ty) : Bool :=
  ty.isDataUnder assumptions.bounds assumptions.rigid Minidregg.Theory.ObjectiveBendTypes.Ty.dataFuel [] &&
    match ty with
    | .field .. | .emptyRow => true
    | _ => false

/-- A type with its variables renamed in order of first use, each bound one's body written once
    where first met: two state types are the same exactly when these agree, whatever numbering the
    compiles gave their bounds (a layer stack's packet numbers them anew). -/
partial def canonicalTy (bounds : DataBounds) (ty : Minidregg.Theory.ObjectiveBendTypes.Ty) : Except String Json :=
  (go ty).run' ([], 0)
where
  go : Minidregg.Theory.ObjectiveBendTypes.Ty → StateT (List (Nat × Nat) × Nat) (Except String) Json
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
    | other => pure (Minidregg.Theory.ObjectiveBendTyping.typeJson other)

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
    unless Minidregg.Compiler.ObjectiveBendParse.isIdent n.toList do throw s!"library module name `{n}` is not an identifier"
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

/-- Dry-run compile of `source` as an entry module over the library: the diagnostics as
    `"<module>:<line>: <stage>: <message>"`, none when it is clean. Nothing is installed. -/
def checkSource (w : World) (source : String) : List String :=
  if source.utf8ByteSize > Limits.maxPackageBytes then
    [s!"Checked:0: package-request: package source exceeds {Limits.maxPackageBytes} bytes"]
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
    match Package.checkPackage modules entry with
    | .ok _ => []
    | .error d =>
      -- A package that declares laws compiles; only the pure profile has no adapter for them.
      if (d.message.splitOn "package laws require").length > 1 then []
      else
        let at_ := s!"{d.sourceModule.getD "Checked"}:{(d.span.map (·.line)).getD 0}"
        -- The kernel's dialect hint, when it has one, is the next line at the same place.
        [s!"{at_}: {d.stage}: {d.message}"] ++ (d.hint.map fun h => [s!"{at_}: hint: {h}"]).getD []

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

def renderLaw (law : Law) : String :=
  "\n".intercalate (law.map fun (name, clause) => s!"law {name}: {clause.render}")

/-- The `"reading"` after a law's name, as the compiler's grammar has it (`law NAME "reading": EXPR`,
    a JSON string literal): the reading and the rest after it, or none when the line has none. -/
def lawReading (rest : String) : Except String (Option (String × String)) := do
  let chars := rest.toList
  unless chars.head? == some '"' do return none
  let rec close : List Char → Nat → Option Nat
    | [], _ => none
    | '\\' :: _ :: more, n => close more (n + 2)
    | '"' :: _, n => some n
    | _ :: more, n => close more (n + 1)
  let some n := close (chars.drop 1) 1 | throw "a law reading is an unterminated string"
  let literal := String.ofList (chars.take (n + 1))
  let reading ← (Lean.Json.parse literal >>= (·.getStr?)).mapError fun _ => s!"a law reading must be a JSON string, found {literal}"
  return some (reading, String.ofList (chars.drop (n + 1)))

/-- Law text: one `law NAME: EXPR` or `law NAME "reading": EXPR` per line, the grammar the compiler
    accepts at the top of a package; the readings beside the law, by clause name. -/
def parseLawTextReadings (text : String) : Except String (Law × List (String × String)) := do
  if text.utf8ByteSize > Limits.maxLawBytes then throw "law text exceeds its byte capacity"
  let lines := (text.splitOn "\n").map String.trimAscii |>.filter (!·.isEmpty) |>.map (·.toString)
  if lines.length > Limits.maxLawClauses then throw "law has too many clauses"
  let parsed ← lines.mapM fun line => do
    let some rest := line.dropPrefix? "law " | throw s!"expected `law NAME: EXPR`, found `{line}`"
    let rest := rest.toString
    let name := (rest.takeWhile fun c => c.isAlphanum || c == '_').toString
    unless Minidregg.Compiler.ObjectiveBendParse.isIdent name.toList do throw s!"invalid law name in `{line}`"
    let after := (rest.drop name.length).toString.trimAsciiStart.toString
    let (reading, after) ← match ← lawReading after with
      | some (r, more) => pure (some r, more.trimAsciiStart.toString)
      | none => pure (none, after)
    let some expr := after.dropPrefix? ":" | throw s!"expected `law NAME: EXPR`, found `{line}`"
    pure ((name, ← Minidregg.Compiler.ObjectiveBendLaw.parse expr.toString), reading.map (name, ·))
  let law := parsed.map (·.1)
  Minidregg.Compiler.ObjectiveBendLaw.checkNames law
  return (law, parsed.filterMap (·.2) |>.filter (!·.2.isEmpty))

/-- Law text: one `law NAME: EXPR` per line (a reading after the name allowed), as at the top of a package. -/
def parseLawText (text : String) : Except String Law := do
  return (← parseLawTextReadings text).1

/-- The rule against a self-sealing law: a law is only accepted if it admits an
    amendment (the state unchanged) by the principal who proposes it. None when it does,
    else the refusal naming that principal and the clause (`name: expression`) that refused. -/
def amendable (law : Law) (principal caller : String) (height turn : Nat) (pin : String) (state : Data) : Option String :=
  (Law.refusedBy law ⟨principal, caller, height, turn, pin, 2, ""⟩ (some state) state).map fun name =>
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
first line (unless the author did), which imports the module below as `Super` and tells the
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
  let withSuper := if (source.splitOn "\n").head?.map (·.trimAscii.toString) == some line then source
    else line ++ "\n" ++ source
  let fields := (inputs.getObj?.toOption.map (·.toList) |>.getD []).filter fun (k, _) => k != "source" && k != "modules" && k != "layers"
  return Json.mkObj ([("modules", .arr (modules.push (Json.mkObj [("name", toJson name), ("source", toJson withSuper)]))),
    ("layers", toJson n)] ++ fields)

/-- The readings an artifact's `laws` table gives (`[{name, reading}]`), the empty ones left out. -/
def artifactReadings (artifact : Json) : List (String × String) :=
  (((artifact.getObjVal? "laws").toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap fun l =>
    match l.getObjValAs? String "name", l.getObjValAs? String "reading" with
    | .ok n, .ok r => if r.isEmpty then none else some (n, r)
    | _, _ => none

/-- What a refusal by law clause `name` of `o` says, when the package gave the clause a reading. -/
def readingOf (o : Object) (name : String) : Option String :=
  (o.readings.lookup name).map fun r => s!"refused {name}: {r}"

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
partial def recordFieldTypes (bounds : DataBounds) (fuel : Nat) : Minidregg.Theory.ObjectiveBendTypes.Ty → Option (List (String × Minidregg.Theory.ObjectiveBendTypes.Ty))
  | .variable i => if fuel == 0 then none else (bounds.lookup i).bind (recordFieldTypes bounds (fuel - 1))
  | .field n m tail => ((n, m) :: ·) <$> recordFieldTypes bounds fuel tail
  | .emptyRow => some []
  | _ => none

/-- Does a package's entry module (the last of its modules, or its one `source`) declare
    `relations()`? Only the entry module's declaration counts: a package whose other modules
    declare one, and its entry module none, has no relations. -/
def entryDeclaresRelations (inputs : Json) : Bool :=
  let src := match inputs.getObjVal? "modules" with
    | .ok (.arr ms) => (ms.back?.bind fun m => (m.getObjValAs? String "source").toOption).getD ""
    | _ => (inputs.getObjValAs? String "source").toOption.getD ""
  (src.splitOn "\n").any (·.startsWith "def relations(")

/-- The relation declarations `relations()` returned (a list of `{field, key, limit?, retain?}`). -/
def parseDecls (value : Data) : Except String (List RelDecl) := do
  let some items := listOf value | throw "relations() must return a list of Decl"
  items.mapM fun d => do
    let .record f := d | throw "a relation Decl is a record"
    let some (.label field) := f.lookup "field" | throw "a relation Decl names its field"
    let some keys := (f.lookup "key").bind listOf | throw s!"relation {field} declares no key list"
    let key ← keys.mapM fun k => match k with
      | .label c => pure c
      | _ => throw s!"relation {field}'s key names columns by text"
    if key.isEmpty then throw s!"key: relation {field} declares an empty key"
    let limit := match f.lookup "limit" with
      | some (.natural n) => n
      | _ => 0
    match f.lookup "retain" with
    | some (.label r) => unless r.isEmpty || r == "dropOldest" do throw s!"relation {field} retains by {r}; only dropOldest is known"
    | some (.variant r _) => unless r == "dropOldest" do throw s!"relation {field} retains by {r}; only dropOldest is known"
    | _ => pure ()
    return { field, key, limit }

/-- The relations a compiled `relations()` entry declares, run as a pure entry. -/
def declsOfEntry (entry : Delvetalk.CheckedEntry) : Except String (List RelDecl) := do
  match Package.executeDataEntry entry #[] (Json.mkObj [("ticks", toJson (toString Delvetalk.Bounds.lawTicks))]) with
  | .ok (.finished value _ _ _) => parseDecls value
  | _ => throw "relations() did not evaluate"

/-- The cases of a sum type (through the bounds): its labels and payload types. -/
partial def variantCases (bounds : DataBounds) (fuel : Nat) : Minidregg.Theory.ObjectiveBendTypes.Ty → Option (List (String × Minidregg.Theory.ObjectiveBendTypes.Ty))
  | .variable i => if fuel == 0 then none else (bounds.lookup i).bind (variantCases bounds (fuel - 1))
  | .variant r => recordFieldTypes bounds (bounds.length + 1) r
  | _ => none

/-- A value from outside with its text words read as cases (HOST-HANDOFF 5.52): where `ty` has a closed
    sum whose every case has an empty payload and the value is a text, the text is the case of that
    name; through records, list items and the payloads of the sums the value names. A text naming no
    case is `(path, word, cases)`, `path` the field path (`bed.colours[1]`, "" for the whole value). Any other value
    is left as it is, for the conformance check to judge. -/
partial def wordsAsCases (bounds : DataBounds) (ty : Minidregg.Theory.ObjectiveBendTypes.Ty) (d : Data)
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
    match Minidregg.Compiler.ObjectiveBendDataWire.listItems? d, item with
    | some items, some t =>
      Minidregg.Compiler.ObjectiveBendDataWire.listData <$> (items.zipIdx.mapM fun (v, i) => wordsAsCases bounds t v s!"{path}[{i}]")
    | _, _ =>
      match (variantCases bounds fuel ty).bind (·.lookup l) with
      | some t => .variant l <$> wordsAsCases bounds t p path
      | none => pure d
  | _ => pure d

/-- The columns of a relation field's rows, read from the state type: `rows {items: List<T>}` with `T` a record. -/
def rowColumns (bounds : DataBounds) (stateType : Minidregg.Theory.ObjectiveBendTypes.Ty) (field : String) : Option (List String) := do
  let fuel := bounds.length + 1
  let fieldTy ← (← recordFieldTypes bounds fuel stateType).lookup field
  let payload ← (← variantCases bounds fuel fieldTy).lookup "rows"
  let items ← (← recordFieldTypes bounds fuel payload).lookup "items"
  let cons ← (← variantCases bounds fuel items).lookup "cons"
  let head ← (← recordFieldTypes bounds fuel cons).lookup "head"
  return (← recordFieldTypes bounds fuel head).map (·.1)

/-- A package's relations against its state type: each a relation field whose rows have every key
    column; refused by name (`key: …`) otherwise. -/
def checkRelations (decls : List RelDecl) (bounds : DataBounds) (stateType : Minidregg.Theory.ObjectiveBendTypes.Ty) : Except String Unit := do
  for d in decls do
    let some cols := rowColumns bounds stateType d.field
      | throw s!"key: {d.field} is not a Relation<T> field of a record T"
    for k in d.key do
      unless cols.contains k do throw s!"key: relation {d.field} names column {k}, which its rows lack"

/-- Compile a replacement for an object's entry module (its imports stay as
    sealed at creation). Failures are `(clause, message)`. -/
def prepareProgram (w : World) (o : Object) (source migration : String) (extend : Bool := false) :
    Except (String × String) Program := do
  if source.utf8ByteSize > Limits.maxPackageBytes then
    throw ("packageBytes", s!"package source exceeds {Limits.maxPackageBytes} bytes")
  let replaced ← (if extend then extendInputs o.inputs source else replaceSource o.inputs source).mapError (("compile", ·))
  -- A reprogram is compiled against the library the world has now.
  let inputs ← (match w.library with
    | some lib => if (replaced.getObjVal? "library").toOption.isSome then
        pure (replaced.setObjVal! "library" (toJson lib.pin)) else pure replaced
    | none => pure replaced)
  let resolved := fun (entry : String) => (resolveInputs w (inputs.setObjVal! "entry" (toJson entry))).mapError (("compile", ·))
  let (artifact, ty, _) ← (Package.compileKeepingLaws (← resolved "initial")).mapError (("compile", ·))
  let decoded ← (do
    Minidregg.Theory.ObjectiveBendTyping.decodePacket (← artifact.getObjVal? "packet")).mapError (("compile", ·))
  let assumptions := decoded.source.assumptions
  unless stateTypeOk assumptions ty do
    throw ("compile", "initial() must return a closed record of first-order data")
  let packet ← (artifact.getObjValAs? String "packetSha256").mapError (("compile", ·))
  let sourcePin ← (artifact.getObjValAs? String "sourcesSha256").mapError (("compile", ·))
  -- The pin is the sources' CID. An extension's is its layer over the sources it extends,
  -- whatever `initial` it reaches.
  let pin := if extend then Journal.bodyHash (Json.arr #[toJson "extend", toJson o.pin, toJson (Journal.bodyHash (toJson source))])
    else sourcePin
  let same := (← (canonicalTy assumptions.bounds ty).mapError (("stateType", ·))) ==
    (← (canonicalTy o.bounds o.stateType).mapError (("stateType", ·)))
  let migrated : Option Compiled ← if migration.isEmpty then
      if same then pure none else throw ("stateType", "the state type differs and no migration names a conversion")
    else do
      unless Minidregg.Compiler.ObjectiveBendParse.isIdent migration.toList do throw ("migration", "invalid migration name")
      let (art, mty, _) ← (Package.compileKeepingLaws (← resolved migration)).mapError (("migration", ·))
      let packet ← (art.getObjVal? "packet").mapError (("migration", ·))
      let md ← (Minidregg.Theory.ObjectiveBendTyping.decodePacket packet).mapError (("migration", ·))
      match mty with
      | .arrow _ _ dom cod =>
        unless dom == o.stateType && cod == ty do
          throw ("migration", "the migration must have type OldState -> NewState")
      | _ => throw ("migration", "the migration must be a function OldState -> NewState")
      pure (some ⟨packet, mty, md.source.assumptions.bounds, md.source.assumptions.rigid,
        (Delvetalk.CheckedEntry.ofPacket packet).toOption, none⟩)
  -- A stack's artifact lists every layer's methods (the kernel's `stackMethodTable`); its law shape
  -- is the stack's when a layer declares a law, else the code's below.
  let (methods, predicate, predicateReads) := artifactShape artifact
  let (predicate, predicateReads) := if !extend || predicate then (predicate, predicateReads)
    else (o.predicate, o.predicateReads)
  -- A layer that declares no relations keeps the relations of the code below it, as it keeps its law.
  let relations ← if !entryDeclaresRelations (← resolved "initial") then pure (if extend then o.relations else []) else do
    let compiled ← (Package.compileEntry (← resolved "relations")).mapError (("key", ·.render))
    (declsOfEntry compiled.entry).mapError (("key", ·))
  (checkRelations relations assumptions.bounds ty).mapError (("key", ·))
  return { inputs, pin, stateType := ty, bounds := assumptions.bounds, migration := migrated,
           methods, predicate, predicateReads, packet, relations }

def programKey (o : Object) (source migration : String) (extend : Bool := false) : String :=
  o.inputsKey ++ "/" ++ Journal.bodyHash source ++ "/" ++ migration ++ (if extend then "/extend" else "")

def programFor (w : World) (o : Object) (source migration : String) (extend : Bool := false) : Except (String × String) Program :=
  match w.programs[programKey o source migration extend]? with
  | some p => pure p
  | none => prepareProgram w o source migration extend

def cacheProgram (w : World) (o : Object) (source migration : String) (p : Program) (extend : Bool := false) : World :=
  if w.programs.size < Limits.maxPreparedPrograms then
    { w with programs := w.programs.insert (programKey o source migration extend) p }
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

/-- A checkpoint as journaled: `tokens` replaced by `tokenTree`, and the blocks the world does
    not hold yet (each once), `extra` ones (an interpretation's) among them. -/
def compactCheckpoint (w : World) (checkpoint : Json)
    (extra : Array (Array Json) := #[]) : Json × List (String × Json) :=
  match (checkpoint.getObjVal? "tokens").toOption.bind (·.getArr?.toOption) with
  | none => (checkpoint, [])
  | some tokens =>
    let (depth, roots, used) := blockTree tokens
    let used := used ++ extra.map fun b => (Journal.bodyHash (Json.arr b), b)
    let fresh := used.foldl (fun (acc : Array (String × Array Json)) (c, b) =>
      if w.blocks.contains c || acc.any (·.1 == c) then acc else acc.push (c, b)) #[]
    let fields := ((checkpoint.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "tokens")
    (Json.mkObj (fields ++ [("tokenTree", Json.mkObj [("depth", toJson depth), ("roots", Json.arr roots)])]),
     if fresh.isEmpty then [] else
       [("blocks", Json.arr (fresh.map fun (c, b) => Json.mkObj [("cid", toJson c), ("items", Json.arr b)]))])

/-- The CID a one-item block of `item` is journaled under. -/
def blockCid (item : Json) : String := Journal.bodyHash (Json.arr #[item])

/-- An interpretation as journaled: its `offers` (the same forms in every reading of one card) are a
    one-item block named by CID (`offersBlock`), so a reading costs only what is new in it. The
    blocks to journal with it are the second component. -/
def compactInterpretation (i : Json) : Json × Array (Array Json) :=
  match i.getObjVal? "offers" with
  | .ok offers =>
    let rest := ((i.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "offers")
    (Json.mkObj (rest ++ [("offersBlock", toJson (blockCid offers))]), #[#[offers]])
  | .error _ => (i, #[])

/-- An interpretation with its `offers` restored from the world's blocks. -/
def expandInterpretation (w : World) (i : Json) : Option Json := do
  let some cid := (i.getObjValAs? String "offersBlock").toOption | return i
  let offers ← (w.blocks[cid]?).bind (·[0]?)
  let rest := ((i.getObj?.toOption.map (·.toList)).getD []).filter fun (k, _) => k != "offersBlock"
  return Json.mkObj (rest ++ [("offers", offers)])

/-- The blocks an entry carries, checked against their CIDs. -/
def entryBlocks (entry : Json) : Except String (List (String × Array Json)) := do
  let some raw := (entry.getObjVal? "blocks").toOption | return []
  (← raw.getArr?).toList.mapM fun b => do
    let cid ← b.getObjValAs? String "cid"
    let items ← (← b.getObjVal? "items").getArr?
    unless Journal.bodyHash (Json.arr items) == cid do throw "a journaled block is not its CID's"
    return (cid, items)

/-- A journaled checkpoint with its token array reassembled from the world's blocks. -/
partial def expandCheckpoint (w : World) (checkpoint : Json) : Except String Json := do
  let some tree := (checkpoint.getObjVal? "tokenTree").toOption | return checkpoint
  let rec expand (depth : Nat) (names : Array Json) : Except String (Array Json) := do
    if depth == 0 then return names
    let mut out : Array Json := #[]
    for n in names do
      let cid ← n.getStr?
      let some items := w.blocks[cid]? | throw s!"checkpoint block {cid} is not journaled"
      out := out ++ items
    expand (depth - 1) out
  let tokens ← expand (← tree.getObjValAs? Nat "depth") (← (← tree.getObjVal? "roots").getArr?)
  let fields := ((checkpoint.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "tokenTree")
  return Json.mkObj (fields ++ [("tokens", Json.arr tokens)])

/-- The sources an entry carries, checked against their CIDs. -/
def entrySources (entry : Json) : Except String (List (String × String)) := do
  let some raw := (entry.getObjVal? "sources").toOption | return []
  (← raw.getArr?).toList.mapM fun m => do
    let cid ← m.getObjValAs? String "cid"
    let src ← m.getObjValAs? String "source"
    unless sourceCid src == cid do throw "a journaled source is not its CID's"
    return (cid, src)

/-- Compile inputs from an entry: every CID resolved to the source a `module` entry recorded. -/
def expandInputs (w : World) (inputs : Json) : Except String Json := do
  let resolve := fun (cid : String) => match w.modules[cid]? with
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

def createRecJson (id : String) (c : CreateRec) : Json :=
  Json.mkObj [("object", toJson id), ("pin", toJson c.object.pin),
    ("read", c.object.read.json), ("chain", c.object.chain.json), ("compile", compactInputs c.object.inputs),
    ("seed", c.seed), ("law", toJson c.object.lawText)] |> fun j =>
    if c.object.supervisor.isEmpty then j else j.setObjVal! "supervisor" (toJson c.object.supervisor)

structure Judged where
  updates : List (String × Object)
  reprograms : List Json
  amendments : List Json
  creations : List (String × Object) := []
  creates : List Json := []

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
    closure, preparing the closure once per package; the world returned caches it. -/
def compileEntryIn (w : World) (inputs : Json) (name : String) : Except String (Package.EntryCompiled × World) := do
  let resolved ← resolveInputs w (Json.mkObj ((inputs.getObj?.toOption.map (·.toList)).getD [] |>.filter (·.1 != "entry")))
  let key := Journal.bodyHash resolved
  let (request, w) ← match w.requests[key]? with
    | some r => pure (r, w)
    | none =>
      let r ← (Package.prepareRequest resolved).mapError Package.Diagnostic.render
      let cache := if w.requests.size < Limits.maxBuilds then w.requests else {}
      pure (r, { w with requests := cache.insert key r })
  let compiled ← (Package.compileEntryFrom request name).mapError Package.Diagnostic.render
  return (compiled, w)

def compiledOf (c : Package.EntryCompiled) : Except String Compiled := do
  return ⟨← c.artifact.getObjVal? "packet", c.entry.type, c.entry.source.assumptions.bounds,
    c.entry.source.assumptions.rigid, some c.entry,
    some (Minidregg.Theory.ObjectiveBendCheckpoint.Dictionary.ofProgram c.entry.source.term)⟩

/-- A pure definition of a held entry run on data arguments under `ticks`: its value, or the
    machine's refusal (`budget` when the ticks ran out), and the ticks it used. -/
def runPure (entry : Delvetalk.CheckedEntry) (arguments : List Data) (ticks : Nat) :
    Except String Data × Nat :=
  match Package.executeDataEntry entry arguments.toArray (Json.mkObj [("ticks", toJson (toString ticks))]) with
  | .ok (.finished value _ _ usage) => (.ok value, usage.ticksUsed + usage.conversionNodes)
  | .ok (.refused failure usage) =>
    (.error (if (failure.splitOn "tick").length > 1 then "budget" else failure), usage.ticksUsed + usage.conversionNodes)
  | .error e => (.error e, 0)

/-- The cache key of an object's compiled definition (`compiledMethod` uses the same). -/
def defKey (o : Object) (name : String) : String := o.inputsKey ++ "/" ++ name

/-- An object's definition `name`, compiled and prepared (from the world's cache when warm). -/
def compileDef (w : World) (o : Object) (name : String) : Except String (Compiled × World) := do
  if let some c := w.compiled[defKey o name]? then return (c, w)
  let (c, w) ← compileEntryIn w o.inputs name
  return (← compiledOf c, w)

/-- Compile the Bend law (and its reads) of the objects a proposal writes, into the world's
    cache, so the pure `judge` finds them. -/
def warmLaws (w : World) (ids : List String) : World :=
  ids.foldl (fun w id => match w.objects[id]? with
    | some o =>
      if !o.predicate then w else
      (["law"] ++ (if o.predicateReads then ["lawReads"] else [])).foldl (fun w name =>
        if w.compiled.contains (defKey o name) then w else
        match compileDef w o name with
        | .ok (c, w) =>
          let cache := if w.compiled.size < Limits.maxCompiledPackets then w.compiled else {}
          { w with compiled := cache.insert (defKey o name) c }
        | .error _ => w) w
    | none => w) w

/-- The labels of a `List<String>` value. -/
partial def labels (acc : List String) : Data → Option (List String)
  | .variant "nil" _ => some acc.reverse
  | .variant "cons" (.record f) => match f.lookup "head", f.lookup "tail" with
    | some (.label s), some tail => labels (s :: acc) tail
    | _, _ => none
  | _ => none

/-- The objects an object's `lawReads()` names. -/
def lawReadsOf (w : World) (o : Object) : Except String (List String) := do
  if !o.predicateReads then return []
  let (c, _) ← compileDef w o "lawReads"
  let some entry := c.entry | throw "lawReads is not held"
  match (runPure entry [] Delvetalk.Bounds.lawTicks).1 with
  | .ok value => match labels [] value with
    | some ids => return ids.eraseDups.take Limits.maxRoots
    | none => throw "lawReads must return a List<String>"
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

/-- The proposal with the objects the Bend laws of its written objects read added as roots. -/
def withLawReads (w : World) (p : Proposal) : Proposal :=
  p.writes.foldl (fun p (id, _) => match w.objects[id]? with
    | some o => match lawReadsOf w o with
      | .ok ids => ids.foldl (fun p r =>
          if p.roots.any (·.1 == r) then p else match w.objects[r]? with
          | some ro => { p with roots := p.roots ++ [(r, ro.version)] }
          | none => p) p
      | .error _ => p
    | none => p) p

/-- The display handle the principal registry holds for a principal, "" when unknown. -/
def handleOf (w : World) (principal : String) : String :=
  (w.handles[principal]?).getD ""

/-- What the host tells a running method about itself, built here and nowhere else.
    `handle` is the principal's display handle from the registry (`world-principal`), ""
    when unknown; `caller` is the calling object's id (empty for the turn's own method),
    `intent` the turn's identity, `height` the journal height the turn read, `clock` the world
    clock (`world-advance`) the frame runs at, which deadlines compare against. None is chosen
    by the client. -/
def contextData (id principal handle caller intent : String) (height clock : Nat) (kind command : String) : Data :=
  .record [("world", .label ""), ("object", .label id), ("principal", .label principal),
    ("handle", .label handle), ("caller", .label caller), ("intent", .label intent), ("height", .natural height),
    ("clock", .natural clock),
    ("inputOrigin", .record [("kind", .label kind), ("object", .label caller), ("command", .label command),
      ("program", .label ""), ("immediatelyPrevious", .boolean false)])]

/-- A record the host builds (a Context, a law's Request) as the receiving code's own library
    declares it: the fields its type names, in its order, each fitted alike. An object compiled
    under an older library whose Context lacks a field the host now fills keeps running; a
    field the host cannot fill leaves the record as built (and the kernel refuses it by name). -/
partial def fitRecord (bounds : DataBounds) (ty : Minidregg.Theory.ObjectiveBendTypes.Ty) (d : Data) : Data :=
  match d, recordFieldTypes bounds (bounds.length + 1) ty with
  | .record fs, some names =>
    if names.all (fun (n, _) => fs.any (·.1 == n)) then
      .record (names.map fun (n, m) => (n, fitRecord bounds m ((fs.lookup n).getD (.record []))))
    else d
  | _, _ => d

/-- The fields `contextData` fills. -/
def contextFields : List String :=
  ["world", "object", "principal", "handle", "caller", "intent", "height", "clock", "inputOrigin"]

/-- A Context type: a record (through the bounds) naming the principal and the intent, every
    field of which the host fills. An older library's Context with fewer fields is one too. -/
def isContextType (bounds : DataBounds) (ty : Minidregg.Theory.ObjectiveBendTypes.Ty) : Bool :=
  match recordFieldTypes bounds (bounds.length + 1) ty with
  | some fs => fs.any (·.1 == "principal") && fs.any (·.1 == "intent") && fs.all (contextFields.contains ·.1)
  | none => false

/-- The parameter types of a definition's type, outermost first. -/
def arrowDomains : Nat → Minidregg.Theory.ObjectiveBendTypes.Ty → List Minidregg.Theory.ObjectiveBendTypes.Ty
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
  let refuse := fun (clause : String) => some ({ cls := "lawRefused", clause := some clause, object := some id } : Refusal)
  let .ok (c, _) := compileDef w o "law" | return refuse "law"
  let some entry := c.entry | return refuse "law"
  let .ok ids := lawReadsOf w o | return refuse "lawReads"
  let mut reads : List Data := []
  for r in ids do
    match w.objects[r]? with
    | some ro =>
      unless p.roots.any (·.1 == r) do return refuse "lawReads"
      reads := reads ++ [.record [("object", .label r), ("version", .natural ro.version), ("state", ro.state)]]
    | none => pure ()
  let context := contextData id subject (handleOf w subject) caller p.intent w.height w.clock "law" method
  let request := Data.record [("context", context), ("method", .label method), ("argument", argument),
    ("kind", .natural kind), ("pin", .label pin),
    ("reads", reads.foldr (fun x t => .variant "cons" (.record [("head", x), ("tail", t)])) (.variant "nil" (.record [])))]
  let request := match c.type with
    | .arrow _ _ _ (.arrow _ _ _ (.arrow _ _ requestType _)) => fitRecord c.bounds requestType request
    | _ => request
  match (runPure entry [o.state, new, request] Delvetalk.Bounds.lawTicks).1 with
  | .ok (.variant "admitted" _) => return none
  | .ok (.variant "refused" (.record f)) =>
    match f.lookup "clause" with
    | some (.label clause) => return refuse clause
    | _ => return refuse "law"
  | .error "budget" => return some { cls := "budget", reason := some "law ticks", object := some id }
  | _ => return refuse "law"

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
    match t.edits with
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

/-- The index entries an admitted entry adds (`World.touches`), from its `writes`. -/
def touchesOf (entry : Json) : List (String × Touch) :=
  let ws := ((entry.getObjVal? "outcome").toOption.bind (·.getObjVal? "writes" |>.toOption)
    |>.bind (·.getArr? |>.toOption)).getD #[]
  ws.toList.filterMap fun x => do
    let id ← (x.getObjValAs? String "object").toOption
    let version ← (x.getObjValAs? Nat "version").toOption
    let kinds := (((x.getObjVal? "kinds").toOption.bind (·.getArr? |>.toOption)).getD #[]).toList
    let steps := (((x.getObjVal? "edits").toOption.bind (·.getArr? |>.toOption)).getD #[]).toList
    let edits : Option (List (String × Data)) :=
      if kinds.any (fun k => k.getNat?.toOption != some 0) then none else
      steps.foldlM (init := []) fun acc step => match decodeData Limits.dataDepth step with
        | .ok (.record fs) => some (acc ++ fs.filter fun (_, k) => match k with
            | .variant "keep" _ => false
            | _ => true)
        | _ => none
    return (id, { version, edits })

/-- A root `id` the turn read at `seen` that has moved since may still commit when every change the
    turn makes of it is an ordinary write and each edit either commutes (`EditKind.commutes`), or
    is an `upsert`/`retract` of a relation row whose key no admitted write since `seen` touched
    (`keysChangedSince`: the row rule, for any root), or, on a resumed turn's own object (`own`), is
    to a field those writes left alone (a turn that only read its own object qualifies). Anything
    else is `staleRoot`. -/
def movedRootAdmits (w : World) (writes : List (String × List Written)) (id : String) (seen : Nat) (own : Bool) : Bool :=
  let decls := ((w.objects[id]?).map (·.relations)).getD []
  let changedFields := if own then fieldsChangedSince w id seen else none
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
  | none => own && changedFields.isSome
  | some changes => !changes.isEmpty && changes.all fun c => c.kind == 0 && c.edits.all fun e =>
      e.kind.commutes || untouched e ||
        (match changedFields with
         | some fields => !fields.contains e.field
         | none => false)

/-- Roots current, writes read, results conform, laws admit. Returns the objects
    as they would be installed. `height` is the height the entry would take. -/
def judge (w : World) (height : Nat) (p : Proposal) : Except Refusal Judged := do
  let writes := p.allWrites
  for id in p.roots.map (·.1) ++ writes.map (·.1) do
    unless w.objects.contains id do throw { cls := "unknownObject", object := id }
  -- A root the turn only changes by `add`/`append` (FOUNDATION section 13, row 1) need only be a
  -- version the object had: its changes re-apply on the state as it is now and are judged there.
  for (id, seen) in p.roots do
    if let some o := w.objects[id]? then
      if o.version != seen && !(seen < o.version &&
          movedRootAdmits w writes id seen (p.rebaseOwn == some id)) then
        throw { cls := "staleRoot", object := id }
  -- A field root is current while no write since the turn read touched that field.
  for (id, field, seen) in p.fieldRoots do
    let some o := w.objects[id]? | throw { cls := "unknownObject", object := id }
    if o.version != seen && !(seen < o.version && ((fieldsChangedSince w id seen).map (!·.contains field)).getD false) then
      throw { cls := "staleRoot", object := id }
  -- A write to the running object needs no view; its version is the first root. A
  -- proposal that writes what it never named as a root is malformed.
  for (id, _) in writes do
    unless p.roots.any (·.1 == id) do
      throw { cls := "evaluation", object := id, reason := some "a write names an object that is not a root" }
  -- An absence is a root too: something appearing since the turn looked makes it stale.
  for id in p.absent do
    if w.objects.contains id then throw { cls := "staleRoot", object := id }
  if w.objects.size + p.creates.length > Limits.maxObjects then
    throw { cls := "evaluation", reason := some "object capacity reached" }
  if w.grants.size + p.grants.length > Limits.maxGrants then throw { cls := "capacity", object := some "grants" }
  -- Subscriptions stand at most `subscribersPerObject` to an object, counted as they will be.
  for x in p.subscribes do
    let standing := ((w.subscriptions.getD x.object #[]).toList ++ p.subscribes).filter fun y =>
      y.object == x.object && !p.unsubscribes.contains y
    if standing.eraseDups.length > Limits.subscribersPerObject then
      throw { cls := "capacity", object := some x.object, reason := some "subscribersPerObject" }
  for g in p.grants do
    if w.grants.contains g.id then throw { cls := "evaluation", reason := some "a grant id is already taken" }
  -- A limited grant must have the uses the turn spends left when it commits.
  for (id, n) in p.spent do
    match w.grants[id]? with
    | some g =>
      if let some left := g.uses then
        if left < n then throw { cls := "lawRefused", clause := some "grantSpent", object := some g.object }
    | none => throw { cls := "evaluation", reason := some "a turn spends an unknown grant" }
  -- A revocation needs the grantor's turn, or a turn that read the object holding the grant.
  for id in p.revokes do
    match w.grants[id]? with
    | some g =>
      unless g.grantor == p.principal || p.roots.any (·.1 == g.holder) do
        throw { cls := "lawRefused", clause := some "notGrantor", object := some g.holder }
    | none => throw { cls := "evaluation", reason := some "a revocation names an unknown grant" }
  let mut out : List (String × Object) := []
  let mut reprograms : List Json := []
  let mut amendments : List Json := []
  for (id, changes) in writes do
    let some o := w.objects[id]? | throw { cls := "unknownObject", object := id }
    let written ← match applyEdits o.relations o.state (changes.map (·.edits)) with
      | .ok d => pure d
      | .error clause => throw { cls := clause, object := id }
    unless written.conformsUnder o.bounds o.stateType do throw { cls := "typeMismatch", object := id }
    unless stateBytes written ≤ Limits.maxStateBytes do
      throw { cls := "capacity", object := id }
    -- A reprogram replaces code and, through its migration, the state's type.
    let mut next := o
    let mut state := written
    if let some (source, migration) := p.programs.lookup id then
      let refuse := fun (clause message : String) => ({ cls := "programRefused", clause := some clause, object := some id, reason := some message } : Refusal)
      let extend := p.layered.contains id
      let prog ← match programFor w o source migration extend with
        | .ok prog => pure prog
        | .error (clause, message) => throw (refuse clause message)
      if let some m := prog.migration then
        let run := match m.entry with
          | some e => Package.executeDataEntry e #[written] (Json.mkObj [])
          | none => Package.executeDataValues m.packet #[written] (Json.mkObj [])
        match run with
        | .ok (.finished value _ _ _) => state := value
        | .ok (.refused failure _) => throw (refuse "migration" s!"the migration was refused: {failure}")
        | .error e => throw (refuse "migration" e)
      unless state.conformsUnder prog.bounds prog.stateType && stateBytes state ≤ Limits.maxStateBytes do
        throw (refuse "migration" "the converted state does not conform to the new state type")
      -- A migration's result is put in canonical form under the new code's relations.
      state ← match canonicalState prog.relations state with
        | .ok s => pure s
        | .error e => throw (refuse "migration" s!"{e}: the converted state's relations are not canonical")
      next := { o with pin := prog.pin, packet := prog.packet, inputs := prog.inputs, inputsKey := inputsKeyOf prog.inputs,
                       stateType := prog.stateType, bounds := prog.bounds, methods := prog.methods,
                       predicate := prog.predicate, predicateReads := prog.predicateReads, relations := prog.relations }
      reprograms := reprograms ++ [Json.mkObj [("object", toJson id), ("oldPin", toJson o.pin),
        ("newPin", toJson prog.pin),
        ("source", toJson source), ("migration", toJson migration),
        ("result", dataJson state)] |> fun j => if extend then j.setObjVal! "mode" (toJson "extend") else j]
    -- The current law judges the whole write, under the pin the object will run. Every
    -- kind of change the object undergoes in this turn is judged, once for each object
    -- that called the running one to make it: the subject is the principal, the caller
    -- is the object whose call it was (empty when the turn's own method wrote).
    -- A change made under a grant is judged with the grantor as its subject, if the grant
    -- still stands for this object and method; otherwise the turn is refused `noGrant`.
    let judgments := (changes.map fun c => (c.caller, c.kind, c.method, c.via)).eraseDups
    for (caller, kind, method, via) in (if judgments.isEmpty then [("", 0, "", "")] else judgments) do
      let subject ← if via.isEmpty then pure p.principal else
        match grantStands w via id method with
        | some g => pure g.grantor
        | none => throw { cls := "lawRefused", clause := some "noGrant", object := some id }
      let facts : Law.Facts := ⟨subject, caller, height, p.turn, next.pin, kind, method⟩
      if let some clause := Law.refusedBy o.law facts (some o.state) state then
        throw { cls := "lawRefused", clause, object := id, reason := readingOf o clause }
    -- The Bend law, after the text admits: once for each ordinary change, with its argument.
    if o.predicate then
      let seen := (changes.filter (·.kind == 0)).foldl (fun (acc : List (String × Written)) c =>
        let key := (Json.arr #[toJson c.caller, toJson c.method, toJson c.via, dataJson c.argument]).compress
        if acc.any (·.1 == key) then acc else acc ++ [(key, c)]) []
      for (_, c) in seen do
        let subject := if c.via.isEmpty then p.principal else ((grantStands w c.via id c.method).map (·.grantor)).getD p.principal
        if let some r := bendLaw w p id o state subject c.caller c.method c.argument 0 next.pin then throw r
    if let some text := p.laws.lookup id then
      let refuse := fun (clause : String) => ({ cls := "lawRefused", clause := some clause, object := some id } : Refusal)
      let law ← match parseLawText text with
        | .ok law => pure law
        | .error _ => throw (refuse "law syntax")
      let amender := ((changes.find? (·.kind == 2)).map (·.caller)).getD ""
      if let some message := amendable law p.principal amender height p.turn next.pin state then throw (refuse message)
      -- A reading stays with its clause only while the amendment leaves that clause as it was.
      -- The amendment's own readings; a clause it leaves as it was without one keeps its reading.
      let given := ((parseLawTextReadings text).toOption.map (·.2)).getD []
      let kept := o.readings.filter fun (n, _) => law.lookup n == o.law.lookup n && (given.lookup n).isNone
      next := { next with law, lawText := text, readings := given ++ kept }
      amendments := amendments ++ [Json.mkObj [("object", toJson id), ("old", toJson o.lawText), ("new", toJson text)]]
    out := out ++ [(id, { next with version := o.version + 1, state })]
  return { updates := out, reprograms, amendments,
           creations := p.creates.map fun (id, c) => (id, c.object),
           creates := p.creates.map fun (id, c) => createRecJson id c }

/-! ## Entries -/

/-- Card names that mean the acting principal's own object: a turn or card naming `env` or
    `wake` runs `env/<principal>` or `wake/<principal>`. No object may take these ids, so no one
    can stand in for another's own. -/
def ownCards : List String := ["env", "wake"]

/-- The object a principal means by `object`: its own for a name in `ownCards`. -/
def resolveCard (principal object : String) : String :=
  if ownCards.contains object then s!"{object}/{principal}" else object

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
def transientClasses : List String := ["staleRoot", "budget", "evaluation", "capacity", "quota"]

def isTransient (entry : Json) : Bool :=
  tagOf entry == "refused" &&
    ((entry.getObjVal? "outcome").toOption.bind (·.getObjValAs? String "class" |>.toOption)).any transientClasses.contains

/-- The subscriptions after an entry: an admitted one's `subscribes` added (once each) and
    `unsubscribes` removed; a refused delivery of `changed` whose principal may no longer view the
    object (`lawRefused denied`) drops its subscription, as a fallen grant is dropped. -/
def subscriptionsAfter (w : World) (entry : Json) : Std.HashMap String (Array Subscription) := Id.run do
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let list := fun (k : String) => ((((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap
    fun j => (Subscription.ofJson j).toOption)
  let mut subs := w.subscriptions
  if tagOf entry == "admitted" then
    for x in list "subscribes" do
      let now := subs.getD x.object #[]
      unless now.contains x do subs := subs.insert x.object (now.push x)
    for x in list "unsubscribes" do
      subs := subs.insert x.object ((subs.getD x.object #[]).filter (· != x))
  else if (outcome.getObjValAs? String "clause").toOption == some "denied" then
    let id := (entry.getObjVal? "delivery").toOption.bind fun d => (d.getObjValAs? String "id").toOption
    if let some d := w.pending.find? fun p => (p.getObjValAs? String "id").toOption == id then
      if (d.getObjVal? "field").toOption.isSome then
        if let (.ok to, .ok principal, .ok object, .ok field) :=
            (d.getObjValAs? String "to", d.getObjValAs? String "principal", d.getObjValAs? String "object", d.getObjValAs? String "field") then
          let x : Subscription := { subscriber := to, principal, object, field }
          subs := subs.insert object ((subs.getD object #[]).filter fun y => !(y.sameAs x && y.principal == principal))
  return subs

def record (w : World) (entry : Json) (key : String) (touch : List String) : World :=
  let hash := (entry.getObjValAs? String "hash").toOption.getD ""
  let index := w.entries.size
  let delivered := (entry.getObjVal? "delivery").toOption.bind fun d => (d.getObjValAs? String "id").toOption
  let identity := (entry.getObjVal? "identity").toOption.getD Json.null
  let sent := match (entry.getObjVal? "outcome").toOption.bind (fun o => (o.getObjValAs? String "tag").toOption),
      (entry.getObjVal? "sends").toOption.bind (·.getArr?.toOption) with
    | some "admitted", some sends => sends.map fun s =>
        -- A send under a grant is delivered as its grantor (the send's own `principal`).
        let fields := s.getObj?.toOption.map (·.toList) |>.getD []
        Json.mkObj ([("from", identity)] ++
          (if fields.any (·.1 == "principal") then [] else
            [("principal", (identity.getObjVal? "principal").toOption.getD Json.null)]) ++ fields)
    | _, _ => #[]
  -- A subscriber's `changed` deliveries, run under the subscription's principal, the changed
  -- object as their sender.
  let changed := if tagOf entry != "admitted" then #[] else
    (((entry.getObjVal? "changes").toOption.bind (·.getArr?.toOption)).getD #[]).map fun c =>
      let fields := c.getObj?.toOption.map (·.toList) |>.getD []
      Json.mkObj ([("from", identity), ("method", toJson ((c.getObjValAs? String "method").toOption.getD "changed")),
        ("sender", (c.getObjVal? "object").toOption.getD Json.null)] ++ fields.filter (·.1 != "method"))
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
    modules := sources.foldl (fun m (cid, src) => m.insert cid src) w.modules
    blocks := ((entryBlocks entry).toOption.getD []).foldl (fun m (cid, b) => m.insert cid b) w.blocks
    pending := (match delivered with
      | some id => w.pending.filter fun p => (p.getObjValAs? String "id").toOption != some id
      | none => w.pending) ++ sent ++ changed ++
      -- An activity's end told to its object's supervisor, whatever the entry's outcome.
      (((entry.getObjVal? "ended").toOption.map fun e =>
        #[Json.mkObj ([("from", identity), ("principal", (identity.getObjVal? "principal").toOption.getD Json.null)] ++
          ((e.getObj?.toOption.map (·.toList)).getD []))]).getD #[])
    height := w.height + 1, head := hash, entries := w.entries.push entry
    replies := match (entry.getObjValAs? String "replyTo").toOption,
        identity.getObjValAs? String "principal", identity.getObjValAs? String "intent" with
      | some post, .ok p, .ok i => if w.replies.contains post then w.replies else w.replies.insert post (p, i)
      | _, _, _ => w.replies
    handles := if tagOf entry == "principal" then
        match (entry.getObjVal? "outcome").toOption with
        | some o => match o.getObjValAs? String "did", o.getObjValAs? String "handle" with
          | .ok did, .ok "" => w.handles.erase did
          | .ok did, .ok handle => w.handles.insert did handle
          | _, _ => w.handles
        | none => w.handles
      else w.handles
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
      | some i => if tagOf w.entries[i]! == "suspended" || isTransient w.entries[i]! then w.receipts.insert key index
          else w.receipts
    touched := touch.foldl (fun t id => t.insert id ((t.getD id #[]).push index)) w.touched
    subscriptions := subscriptionsAfter w entry
    touches := if tagOf entry != "admitted" then w.touches else
      (touchesOf entry).foldl (fun t (id, x) => t.insert id ((t.getD id #[]).push x)) w.touches }

def push (w : World) (key : String) (fields : List (String × Json)) (touch : List String) :
    World × Json :=
  let entry := Journal.sealEntry (w.height + 1) w.head fields
  (record w entry key touch, entry)

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
    ("original", entry.getObjVal? "hash" |>.toOption |>.getD Json.null)]

/-- Retry rule shared by every journaled op: the same identity and request returns
    the retained receipt without an entry; the same identity with another request
    is `duplicateIdentity` and is not journaled (the identity is already bound). -/
def retained (w : World) (principal intent digest : String) : Option Json :=
  match w.receipts[identityKey principal intent]? with
  | none => none
  | some index =>
    let entry := w.entries[index]!
    let same := (entry.getObjValAs? String "request").toOption == some digest
    if tagOf entry == "suspended" then none
    -- A transient refusal does not bind the identity: the retry runs (and is judged) again.
    else if isTransient entry then none
    else if same then some (reply entry)
    else some (duplicate principal intent entry)

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
      else .variant "admitted" (.record []))]

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
  let p := withLawReads w p
  match retained w p.principal p.intent p.digest with
  | some r => (w, r)
  | none =>
    -- The turn number is the host's: the height of the entry about to be written.
    let p := { p with turn := w.height + 1 }
    let key := identityKey p.principal p.intent
    let base := [("identity", identityJson p.principal p.intent), ("roots", allRootsJson p.roots p.fieldRoots),
      ("turn", toJson p.turn), ("request", toJson p.digest)] ++
      (if p.absent.isEmpty then [] else [("absent", toJson p.absent)]) ++ extra
    let verdict : Except Refusal Judged :=
      match forced with | some r => .error r | none => judge w (w.height + 1) p
    match verdict with
    | .error r =>
      let outcome := Json.mkObj ([("tag", toJson "refused"), ("class", toJson r.cls)] ++
        (r.clause.map fun c => [("clause", toJson c)]).getD [] ++
        (r.object.map fun o => [("object", toJson o)]).getD [] ++
        (r.reason.map fun o => [("reason", toJson o)]).getD [] ++
        (r.expected.map fun e => [("expected", e)]).getD [] ++
        (r.root.map fun x => [("root", toJson x)]).getD [] ++
        (r.hint.map fun x => [("hint", toJson x)]).getD [] ++
        (r.next.map fun x => [("next", toJson x)]).getD [])
      let (w', entry) := push w key (base ++ [("outcome", outcome)] ++ onEnd (w.height + 1) outcome) []
      (w', reply entry)
    | .ok judged =>
      let updates := judged.updates
      let w := updates.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      let w := judged.creations.foldl (fun w (id, o) => noteMinted { w with objects := w.objects.insert id o } id) w
      let w := applyGrants w p.grants p.revokes p.spent
      let writes := Json.arr (updates.toArray.map fun (id, o) => Json.mkObj
        (("object", toJson id) :: ("version", toJson o.version) :: ("cid", toJson (stateCid o.state)) ::
          writtenFields ((p.allWrites.lookup id).getD [])))
      let outcome := Json.mkObj ([("tag", toJson "admitted"), ("writes", writes)] ++
        (if judged.reprograms.isEmpty then [] else [("reprograms", Json.arr judged.reprograms.toArray)]) ++
        (if judged.amendments.isEmpty then [] else [("amendments", Json.arr judged.amendments.toArray)]) ++
        (if judged.creates.isEmpty then [] else [("creates", Json.arr judged.creates.toArray)]) ++
        (if p.grants.isEmpty then [] else [("grants", Json.arr (p.grants.toArray.map Grant.json))]) ++
        (if p.revokes.isEmpty then [] else [("revokes", toJson p.revokes)]) ++
        (if p.spent.isEmpty then [] else [("spent", spentJson p.spent)]) ++
        (if p.subscribes.isEmpty then [] else [("subscribes", Json.arr (p.subscribes.toArray.map (·.json)))]) ++
        (if p.unsubscribes.isEmpty then [] else [("unsubscribes", Json.arr (p.unsubscribes.toArray.map (·.json)))]))
      let holders := (p.grants.map (·.holder)).filter fun h => !updates.any (·.1 == h)
      let (w', entry) := push w key (base ++ [("outcome", outcome)] ++ onAdmit updates ++
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
  | none => pure .«public»
  | some (.str "public") => pure .«public»
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
    `owner: request.kind == 0 or request.subject == "<creator>"`.

    Writes only ever change the running object (a method's `write` is its own; other
    objects change by being called, and their own law judges what they do to themselves),
    so a kind-0 judgment is always about an object's own method acting for a principal.
    The law therefore means: anyone may invoke my methods; only my creator may
    reprogram or amend me. An object that wants its writes guarded as well declares a law
    (`request.subject`, `request.caller`, `appendOnly`, `unchanged`, ...). -/
def defaultLaw (creator : String) : Except String Law := do
  if creator.any (fun c => c == '"' || c == '\\' || c.toNat < 32) then
    throw "the creator handle cannot be named in the default law"
  let clause ← Minidregg.Compiler.ObjectiveBendLaw.parse
    s!"request.kind == 0 or request.subject == \"{creator}\""
  return [("owner", clause)]

def buildKey (inputs : Json) : String := Journal.bodyHash inputs

def compileObject (w : World) (inputs : Json) : Except String Built := do
  if let some b := w.builds[buildKey inputs]? then return b
  let resolved ← resolveInputs w inputs
  -- One prepared closure for the entry and, when the entry module declares them, `relations()`.
  let request ← (Package.prepareRequest resolved).mapError Package.Diagnostic.render
  let c ← (Package.compileEntryCore request (← resolved.getObjValAs? String "entry")).mapError
    fun d => (Package.withHint resolved d).render
  let (artifact, ty, laws) := (c.artifact, c.entry.type, c.laws)
  let packet ← artifact.getObjVal? "packet"
  let decoded ← Minidregg.Theory.ObjectiveBendTyping.decodePacket packet
  unless stateTypeOk decoded.source.assumptions ty do
    throw "package entry type must be a closed record of first-order data (a zero-argument definition returning the state record)"
  let relations ← if !entryDeclaresRelations resolved then pure [] else do
    let r ← (Package.compileEntryCore request "relations").mapError fun d => s!"key: relations(): {d.render}"
    declsOfEntry r.entry
  return { artifact, ty, laws, assumptions := decoded.source.assumptions, relations }

/-- Give a compiled package its first state and law. `lawText`, when given, is the law
    exactly as journaled; otherwise the package's laws, or the default owner law. -/
def makeObject (b : Built) (inputs : Json) (state : Data) (read : Option Json := none)
    (chain : Option Json := none) (creator : String := "") (height : Nat := 1)
    (lawText : Option String := none) : Except String (Object × String) := do
  unless state.conformsUnder b.assumptions.bounds b.ty do throw "seed does not conform to the package state type"
  if stateBytes state > Limits.maxSeedBytes then throw "seed exceeds state byte capacity"
  -- The pin is the source closure's CID; the compiled packet is only observed beside it.
  let packet ← b.artifact.getObjValAs? String "packetSha256"
  let sources ← b.artifact.getObjValAs? String "sourcesSha256"
  let pin := sources
  -- No law declared: the creator owns reprogramming and amendment, anyone may write.
  let laws ← match lawText with
    | some text => parseLawText text
    | none => if b.laws.isEmpty then defaultLaw creator else pure b.laws
  if let some message := amendable laws creator "" height 0 pin state then throw message
  let (methods, predicate, predicateReads) := artifactShape b.artifact
  -- Readings belong to the package's clauses; a law given at creation keeps those it left alone.
  let given := (lawText.bind fun t => (parseLawTextReadings t).toOption.map (·.2)).getD []
  let readings := given ++ (artifactReadings b.artifact).filter fun (n, _) =>
    (laws.lookup n).isSome && laws.lookup n == b.laws.lookup n && (given.lookup n).isNone
  return ({ pin, law := laws, lawText := renderLaw laws, version := 0, state, stateType := b.ty, readings,
            bounds := b.assumptions.bounds, read := ← parseRead read, chain := ← parseChain chain,
            inputs, inputsKey := inputsKeyOf inputs, methods, predicate, predicateReads, packet }, sources)

def cacheBuild (w : World) (inputs : Json) (b : Built) : World :=
  if w.builds.size < Limits.maxBuilds then { w with builds := w.builds.insert (buildKey inputs) b } else w

/-- Build an object and remember its compiled package in the world. -/
def buildObjectIn (w : World) (inputs seed : Json) (read : Option Json := none) (chain : Option Json := none)
    (creator : String := "") (height : Nat := 1) (lawText : Option String := none) :
    Except String (Object × String × World) := do
  let built ← compileObject w inputs
  let (relations, state) ← relationsFor built (← decodeData Limits.dataDepth seed)
  let (o, sources) ← makeObject built inputs state read chain creator height lawText
  return ({ o with relations }, sources, cacheBuild w inputs built)

def buildObject (w : World) (inputs seed : Json) (read : Option Json := none) (chain : Option Json := none)
    (creator : String := "") (height : Nat := 1) (lawText : Option String := none) : Except String (Object × String) := do
  let (o, sources, _) ← buildObjectIn w inputs seed read chain creator height lawText
  return (o, sources)

def createOutcome (id : String) (o : Object) (artifact seed : Json) : Json :=
  Json.mkObj [("tag", toJson "created"), ("read", o.read.json), ("chain", o.chain.json), ("object", toJson id), ("pin", toJson o.pin),
    ("compile", artifact), ("seed", seed)]

/-- A seed (a `Data` payload) is a whole state, or a record naming some fields of it (the rest
    come from `initial()`), for `world-create` and the `create` Plan alike. -/
def mergeSeed (initial seed : Data) (bounds : Minidregg.Theory.ObjectiveBendTypes.DataBounds)
    (ty : Minidregg.Theory.ObjectiveBendTypes.Ty) : Except String Data := do
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
  if ownCards.contains id then throw s!"object id {id} is reserved: it names each principal's own {id}/<principal>"
  -- The opener of the world may create an object for its owner: the law (the default law
  -- names the owner) and the metarule are the owner's, the creator is the opener.
  let owner ← optText j "owner"
  if let some o := owner then
    discard <| boundedText "owner" Limits.maxPrincipalBytes o
    if w.opener.isEmpty || principal != w.opener then
      throw s!"only the opener of the world may name an owner{if w.opener.isEmpty then "; this world names no opener" else s!"; that is {w.opener}"}"
  if w.objects.contains id then throw s!"object {id} already exists"
  if w.objects.size ≥ Limits.maxObjects then throw "object capacity reached"
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
  let (o, sources, w) ← buildObjectIn (cacheBuild w inputs built) inputs seed (j.getObjVal? "read").toOption (j.getObjVal? "chain").toOption (owner.getD principal) (w.height + 1)
  let supervisor := (← optText j "supervisor").getD ""
  unless supervisor.isEmpty || w.objects.contains supervisor do throw s!"supervisor {supervisor} is not an object"
  let o := { o with supervisor }
  -- An `artifact` claim is only a claim: the journal keeps the inputs, never the claim.
  discard <| pure sources
  let outcome := createOutcome id o (compactInputs inputs) seed
  let outcome := if supervisor.isEmpty then outcome else outcome.setObjVal! "supervisor" (toJson supervisor)
  let outcome := match owner with
    | some o => outcome.setObjVal! "owner" (toJson o)
    | none => outcome
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
  | .ok law => Law.refusedBy law ⟨principal, "", height, height, pin, 1, ""⟩ (some (.record [])) (.record [])

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
so a reply to that post can be routed back (`world-addressee`). -/

def settingsOp (w : World) (clock : Option String) (quota : Option Nat) (opener : Option String := none)
    (interpretQuota : Option Nat := none) : Except String (World × Json) := do
  if clock.isNone && quota.isNone && opener.isNone && interpretQuota.isNone then return (w, Json.null)
  let clockP := clock.getD ""
  let openerP := opener.getD ""
  if w.settled then
    if (clock.isSome && clockP != w.clockPrincipal) || (quota.isSome && quota != some w.postQuota) ||
        (opener.isSome && openerP != w.opener) || (interpretQuota.isSome && interpretQuota != some w.interpretQuota) then
      throw s!"the journal records clock {w.clockPrincipal}, postQuota {w.postQuota}, interpretQuota {w.interpretQuota} and opener {w.opener}; the settings differ"
    return (w, Json.null)
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

/-- `world-posted {principal, uri, cid, object, slot?, page?, section?}`: transport confirms a post it
    made for `object` (and for an awaited `slot`, or carrying the object's publication of `page`,
    section "" for the whole page). Only the world's clock principal, when one is named. -/
def postedOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let uri ← boundedText "uri" Limits.maxUriBytes (← j.getObjValAs? String "uri")
  let cid ← boundedText "cid" Limits.maxUriBytes (← j.getObjValAs? String "cid")
  let object ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let slot ← match j.getObjVal? "slot" with
    | .ok (.null) | .error _ => pure none
    | .ok s => pure (some (← parseSlot s))
  let (page, part) ← postedPage j
  -- An AT post, or a message of the Zulip playtest transport (`zulip://<stream>/<topic>/<id>`).
  unless postSchemes.any (fun (p : String) => uri.startsWith p) do
    throw s!"uri must be an at:// or zulip:// URI, not {(uri.splitOn "://").head!}://"
  if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then
    throw s!"posts are confirmed only by {w.clockPrincipal}"
  unless w.objects.contains object do throw s!"unknown object {object}"
  let fields := [("tag", toJson "posted"), ("uri", toJson uri), ("cid", toJson cid), ("object", toJson object)] ++
    (slot.map fun s => [("slot", s)]).getD [] ++
    (if page.isEmpty then [] else [("page", toJson page), ("section", toJson part)])
  let digest := Journal.bodyHash (Json.mkObj fields)
  let answer := fun (entry : Json) => Json.mkObj [("status", toJson "posted"),
    ("height", (entry.getObjVal? "height").toOption.getD Json.null), ("receipt", entry)]
  let intent := "posted:" ++ uri
  match retained w principal intent digest with
  | some r => return (w, match r.getObjVal? "receipt" with | .ok e => answer e | .error _ => r)
  | none =>
    if w.posts.contains uri then throw s!"post {uri} is already recorded"
    let (w', entry) := push (postIndex w uri { object, slot, page, part, height := w.height + 1 }) (identityKey principal intent)
      [("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0),
       ("request", toJson digest), ("outcome", Json.mkObj fields)] [object]
    return (w', answer entry)

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

/-- A newcomer's own objects, each made from the library module of that name: the Avatar (its id
    is the principal's DID), its Env and its Wake (`env/<did>`, `wake/<did>`, the ids `env` and
    `wake` resolve to for that principal). -/
def arrivals (did : String) : List (String × String) :=
  [(did, "Avatar"), (s!"env/{did}", "Env"), (s!"wake/{did}", "Wake")]

/-- `world-arrive {principal, did, handle}`: the clock principal (transport) reports a principal
    it has verified or observed. The handle is recorded as `world-principal` does, and each of the
    newcomer's objects (`arrivals`) that is absent is created from the world's library, by the
    world's opener for the owner `did` (`world-create {…, owner}`), as an ordinary `created` entry
    with identity `(opener, "arrive:<id>")`. The partial seed names, of `owner` (the DID), `handle`
    and `env` (a Reference to `env/<did>`, which the Wake watches), the fields the package's state
    has; the rest is `initial()`. Idempotent: a second arrival creates nothing, and a changed
    handle is one `principal` entry. -/
def arriveOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let did ← boundedText "did" (Limits.maxObjectIdBytes - 5) (← j.getObjValAs? String "did")
  let handle ← j.getObjValAs? String "handle"
  if w.clockPrincipal.isEmpty || principal != w.clockPrincipal then
    throw s!"arrivals are reported only by the clock principal{if w.clockPrincipal.isEmpty then "; this world names none" else s!" {w.clockPrincipal}"}"
  if w.opener.isEmpty then throw "this world names no opener to create a newcomer's objects"
  if did == "self" || ownCards.contains did || did.any (· == '/') then throw s!"{did} cannot name a principal's objects"
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
    let given : List (String × Data) := [("owner", .label did), ("handle", .label handle),
      ("env", .record [("world", .label ""), ("object", .label s!"env/{did}")])]
    let seed := match ← initialState built with
      | .record fields => given.filter fun (k, _) => fields.any (·.1 == k)
      | _ => []
    let (w', r) ← create (cacheBuild w inputs built) (request.setObjVal! "seed" (dataJson (.record seed)))
    if (r.getObjValAs? String "status").toOption != some "created" then
      throw s!"arrival of {did}: {module} {id} was not created: {r.compress}"
    w := w'
    made := made.push (Json.mkObj [("object", toJson id), ("height", toJson w.height)])
  return (w, Json.mkObj ([("status", toJson "arrived"), ("did", toJson did), ("handle", toJson handle),
    ("created", Json.arr made)] ++ ((recorded.getObjVal? "receipt").toOption.map fun e => [("principal", e)]).getD []))

/-- `world-addressee {parent}`: the object (and slot, or page and section) a post at `parent` was made for. -/
def addressee (w : World) (j : Json) : Except String Json := do
  let uri ← j.getObjValAs? String "parent"
  match w.posts[uri]? with
  | none => return Json.mkObj [("status", toJson "unknown")]
  | some p => return Json.mkObj ([("status", toJson "addressee"), ("object", toJson p.object)] ++
      (p.slot.map fun s => [("slot", s)]).getD [] ++
      (if p.page.isEmpty then [] else [("page", toJson p.page), ("section", toJson p.part)]))

/-! ## Replay -/

/-- The id of the `ordinal`th send of the turn with this identity. -/
def deliveryId (principal intent : String) (ordinal : Nat) : String :=
  Journal.bodyHash (Json.arr #[toJson principal, toJson intent, toJson ordinal])

/-- The ledger a turn's sends and changes inherit: depth - 1, work - the ticks it used, storage -
    the bytes its writes added. -/
def childLedger (w : World) (ledger : Ledger) (used : Nat) (updates : List (String × Object)) : Ledger :=
  let added := updates.foldl (fun n (id, o) =>
    let before := ((w.objects[id]?).map fun p => stateBytes p.state).getD 0
    n + (stateBytes o.state - before)) 0
  ⟨ledger.depth - 1, ledger.work - used, ledger.storage - added⟩

/-- What a write did to one field, as `changed` reports it: for a relation the rows inserted and the
    rows retracted (an upsert that replaced a row is both), for a list the items added and the items
    removed (by canonical bytes), for anything else the new value and the old one. Both are lists. -/
def fieldChange (decls : List RelDecl) (field : String) (old new : Data) : Data × Data :=
  let listed := fun (items : List Data) => ofList items
  let diff := fun (a b : List Data) =>
    let bs := b.map Delvetalk.Canonical.encode
    a.filter fun x => !bs.contains (Delvetalk.Canonical.encode x)
  let rows := fun (d : Data) => if decls.any (·.field == field) then (relationRows d).toOption else listOf d
  match rows old, rows new with
  | some before, some after => (listed (diff after before), listed (diff before after))
  | _, _ => (listed [new], listed [old])

/-- The `changed` deliveries an admitted write owes its subscribers (WHOLENESS §3): for each written
    object, each subscription to a field its edits touched (an edit other than `keep`), in
    subscription order, `{id, to, object, field, version, principal, ledger, argument}` with argument
    `{object: Reference, field, version, inserted, retracted}`; ids continue the sends' ordinals. Sends
    and changes together are at most `sendsPerTurn`: the subscribers past it are named in `unserved`. -/
def changesJson (w : World) (principal intent : String) (ledger : Ledger) (used sent : Nat)
    (updates : List (String × Object)) (writes : List (String × List Written)) : List (String × Json) := Id.run do
  let child := (childLedger w ledger used updates).json
  let mut changes : Array Json := #[]
  let mut unserved : Array Json := #[]
  for (id, o) in updates do
    let some before := w.objects[id]? | continue
    let touched := (((writes.lookup id).getD []).filter (·.kind == 0)).flatMap fun c =>
      (c.edits.filter fun e => match e.kind with | .keep => false | _ => true).map (·.field)
    for x in w.subscriptions.getD id #[] do
      unless touched.contains x.field do continue
      if sent + changes.size ≥ Limits.sendsPerTurn then
        unserved := unserved.push (toJson x.subscriber)
        continue
      let field := fun (d : Data) => match d with
        | .record fs => (fs.lookup x.field).getD (.record [])
        | _ => .record []
      let (inserted, retracted) := fieldChange o.relations x.field (field before.state) (field o.state)
      let argument := Data.record [("object", .record [("world", .label ""), ("object", .label id)]),
        ("field", .label x.field), ("version", .natural o.version), ("inserted", inserted), ("retracted", retracted)]
      changes := changes.push (Json.mkObj ([("id", toJson (deliveryId principal intent (sent + changes.size))),
        ("to", toJson x.subscriber), ("object", toJson id), ("field", toJson x.field), ("version", toJson o.version),
        ("principal", toJson x.principal), ("ledger", child), ("argument", dataJson argument)] ++
        (if x.method == "changed" then [] else [("method", toJson x.method)])))
  return (if changes.isEmpty then [] else [("changes", Json.arr changes)]) ++
    (if unserved.isEmpty then [] else [("unserved", Json.arr unserved)])

def ledgerOf (j : Json) : Except String Ledger := do
  return ⟨← natField j "depth", ← natField j "work", ← natField j "storage"⟩

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
    unless ledger.exhausted == (outcome.getObjValAs? String "reason").toOption do
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

/-- The objects an admitted entry created, rebuilt from their journaled inputs. -/
def rebuildCreates (w : World) (principal : String) (recorded : Array Json) :
    Except String (World × List (String × CreateRec)) := do
  let mut w := w
  let mut creates : List (String × CreateRec) := []
  for r in recorded do
    let id ← r.getObjValAs? String "object"
    let seed ← r.getObjVal? "seed"
    let (o, sources, w') ← buildObjectIn w (← expandInputs w (← r.getObjVal? "compile")) seed (r.getObjVal? "read").toOption
      (r.getObjVal? "chain").toOption principal (w.height + 1) (some (← r.getObjValAs? String "law"))
    w := w'
    let o := { o with supervisor := (r.getObjValAs? String "supervisor").toOption.getD "" }
    creates := creates ++ [(id, ({ object := o, sources, seed } : CreateRec))]
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
  let w := { w with modules := introduced.foldl (fun m (cid, src) => m.insert cid src) w.modules }
  let blocks ← entryBlocks entry
  let w := { w with blocks := blocks.foldl (fun m (cid, b) => m.insert cid b) w.blocks }
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
    if w.settled then throw "settings recorded twice"
    return record { w with clockPrincipal := ← outcome.getObjValAs? String "clock",
                           postQuota := ← natField outcome "postQuota", settled := true,
                           interpretQuota := (outcome.getObjValAs? Nat "interpretQuota").toOption.getD 48,
                           opener := (outcome.getObjValAs? String "opener").toOption.getD "" } entry key []
  | "principal" =>
    discard <| outcome.getObjValAs? String "did"
    discard <| outcome.getObjValAs? String "handle"
    if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then throw "principal recorded by another principal"
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
    return record (postIndex w uri { object, slot, page, part, height := ← natField entry "height" }) entry key [object]
  | "suspended" =>
    let activity ← outcome.getObjVal? "activity"
    let checkpoint ← expandCheckpoint w (← activity.getObjVal? "checkpoint")
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
    unless ["proposal", "unclear", "replied"].contains (← verdict.getObjValAs? String "tag") do throw "unknown verdict"
    return record w entry key []
  | "created" =>
    let id ← outcome.getObjValAs? String "object"
    if w.objects.contains id then throw s!"object {id} created twice"
    let inputs ← expandInputs w (← outcome.getObjVal? "compile")
    let owner := (outcome.getObjValAs? String "owner").toOption
    if owner.isSome && (w.opener.isEmpty || principal != w.opener) then throw "an owner named by another than the opener"
    let (o, sources, w) ← buildObjectIn w inputs (← outcome.getObjVal? "seed") (outcome.getObjVal? "read").toOption (outcome.getObjVal? "chain").toOption (owner.getD principal) (w.height + 1)
    -- The pin binds the sources; the packet this compiler made of them is only counted if it differs.
    unless o.pin == (← outcome.getObjValAs? String "pin") && sources == o.pin do
      throw s!"object {id} is not the source closure its pin names"
    let w := noteRecompiled w o
    let o := { o with supervisor := (outcome.getObjValAs? String "supervisor").toOption.getD "" }
    return record (noteMinted { w with objects := w.objects.insert id o } id) entry key [id]
  | "refused" =>
    let cls ← outcome.getObjValAs? String "class"
    unless refusalClasses.contains cls do throw s!"unknown refusal class {cls}"
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
    let roots ← parseRoots (← entry.getObjVal? "roots")
    let fieldRoots ← parseFieldRoots (← entry.getObjVal? "roots")
    let rebaseOwn := if (entry.getObjVal? "resumes").toOption.isSome then roots.head?.map (·.1) else none
    let subs := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption) |>.getD #[]).toList.mapM Subscription.ofJson
    let subscribes ← subs "subscribes"
    let unsubscribes ← subs "unsubscribes"
    let p : Proposal := { principal, intent, roots, rebaseOwn, writes, turn, programs, laws,
                          absent, creates, grants, revokes, spent, layered, subscribes, unsubscribes, fieldRoots }
    unless turn == w.height + 1 do throw "turn is not the height of its entry"
    unless (entry.getObjValAs? String "request").toOption == some p.digest do throw "request digest does not match"
    let w := warmLaws w (p.writes.map (·.1))
    match judge w (w.height + 1) p with
    | .error r => throw s!"admitted entry would be refused ({r.cls})"
    | .ok judged =>
      unless judged.reprograms == recordedPrograms.toList && judged.amendments == recordedLaws.toList &&
          judged.creates == recordedCreates.toList do
        throw "recorded reprograms, amendments or creations do not replay"
      let w := (judged.updates.filter (fun (id, _) => judged.reprograms.any fun r =>
          (r.getObjValAs? String "object").toOption == some id) ++ judged.creations).foldl (fun w (_, o) => noteRecompiled w o) w
      let updates := judged.updates
      for raw in rawWrites do
        let id ← raw.getObjValAs? String "object"
        let some (_, o) := updates.find? (·.1 == id) | throw "write missing"
        unless (← natField raw "version") == o.version do throw "write version out of sequence"
        -- The state an admitted write commits to (host7; earlier entries name none).
        if let some cid := (raw.getObjValAs? String "cid").toOption then
          unless cid == stateCid o.state do throw s!"the state of {id} does not replay to the CID its write recorded"
      -- The changes owed to subscribers are re-derived and must be the ones journaled.
      let sentCount := ((entry.getObjVal? "sends").toOption.bind (·.getArr?.toOption) |>.map (·.size)).getD 0
      let entryLedger ← match entry.getObjVal? "ledger" with
        | .ok l => ledgerOf l
        | .error _ => pure Ledger.start
      let usedTicks := (entry.getObjValAs? Nat "ticksUsed").toOption.getD 0
      let owed := changesJson w principal intent entryLedger usedTicks sentCount updates p.allWrites
      unless owed.lookup "changes" == (entry.getObjVal? "changes").toOption &&
          owed.lookup "unserved" == (entry.getObjVal? "unserved").toOption do
        throw "the changes owed to subscribers do not replay"
      let w := updates.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      let w := judged.creations.foldl (fun w (id, o) => noteMinted { w with objects := w.objects.insert id o } id) w
      let w := applyGrants w grants revokes spent
      let holders := (grants.map (·.holder)).filter fun h => !updates.any (·.1 == h)
      return record w entry key (updates.map (·.1) ++ judged.creations.map (·.1) ++ holders.eraseDups)
  | other => throw s!"unknown outcome {other}"

def replay (content : String) : Except String World := do
  let lines := content.splitOn "\n"
  let (complete, tail) := (lines.dropLast, lines.getLast?.getD "")
  if complete.length ≥ Limits.maxJournalEntries then throw "journal exceeds entry capacity"
  let mut w : World := {}
  for line in complete do
    let height := w.height + 1
    let entry ← match Json.parse line with
      | .ok e => pure e
      | .error _ => throw s!"journal broken at height {height}: unparsable line"
    Journal.verify height w.head entry
    match replayEntry w entry with
    | .ok w' => w := w'
    | .error e => throw s!"journal broken at height {height}: {e}"
  unless tail.isEmpty do throw s!"journal broken at height {w.height + 1}: unterminated final line"
  return w

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
  let names := fun (o : Object) => ((o.methods.getArr?.toOption).getD #[]).toList.filterMap fun m =>
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
  if o.version == version then return some (stateCid o.state)
  for i in (w.touched[id]?).getD #[] do
    let some entry := w.entries[i]? | continue
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let arr := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
    let named := fun (j : Json) => (j.getObjValAs? String "object").toOption == some id
    match tagOf entry with
    | "created" =>
      if version == 0 && named outcome then
        if let .ok seed := outcome.getObjVal? "seed" then return some (Journal.bodyHash seed)
    | "admitted" =>
      for x in arr "writes" do
        if named x && (x.getObjValAs? Nat "version").toOption == some version then
          return (x.getObjValAs? String "cid").toOption
      if version == 0 then
        for c in arr "creates" do
          if named c then
            if let .ok seed := c.getObjVal? "seed" then return some (Journal.bodyHash seed)
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
  let mut state : Option Data := none
  for i in (w.touched[id]?).getD #[] do
    let some entry := w.entries[i]? | continue
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let arr := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
    let named := fun (j : Json) => (j.getObjValAs? String "object").toOption == some id
    let seedOf := fun (j : Json) => (j.getObjVal? "seed").toOption.bind fun s => (decodeData Limits.dataDepth s).toOption
    match tagOf entry with
    | "created" => if named outcome then state := seedOf outcome
    | "admitted" =>
      for c in arr "creates" do
        if named c then state := seedOf c
      for x in arr "writes" do
        unless named x do continue
        let some v := (x.getObjValAs? Nat "version").toOption | return none
        if v > version then return state
        let some before := state | return none
        let next? : Option Data := match (arr "reprograms").find? named with
          | some r => (r.getObjVal? "result").toOption.bind (decodeData Limits.dataDepth · |>.toOption)
          | none => ((x.getObjVal? "edits").toOption.bind (parseSteps · |>.toOption)).bind fun steps =>
            (applyEdits o.relations before steps).toOption
        let some next := next? | return none
        if let .ok cid := x.getObjValAs? String "cid" then
          if cid != stateCid next then return none
        state := some next
    | _ => pure ()
    if version == 0 && state.isSome then return state
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
    id the author wrote (as resolved, so `env` reads `env/<did>`) and where the list of cards is. -/
def publicRefusal (entry : Json) : Json :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let named := (outcome.getObjValAs? String "object").toOption.getD ""
  -- A refusal judged against another root than the id it names (`requiredAbsence`: the creating
  -- object, read at a version, beside the id it found taken) commits to that root.
  let id := (outcome.getObjValAs? String "root").toOption.getD named
  let cls := (outcome.getObjValAs? String "class").toOption.getD "unknown"
  let roots := (entry.getObjVal? "roots").toOption.getD (Json.arr #[])
  let version := ((parseRoots roots).toOption.getD []).lookup id
  let root := Json.mkObj ([("object", toJson id)] ++ (version.map fun v => [("version", toJson v)]).getD [])
  -- A law's reading is the package's public text about the clause, never state.
  let reading := if cls == "lawRefused" then (outcome.getObjValAs? String "reason").toOption else none
  let slug := (entry.getObjValAs? String "hash").toOption.bind Slug.ofCid
  Json.mkObj ([("status", toJson "refused"), ("class", toJson cls), ("root", root)] ++
    (slug.map fun x => [("slug", toJson x)]).getD [] ++
    (reading.map fun r => [("reason", toJson r)]).getD [] ++
    (if cls == "unknownObject" then
      [("object", toJson id), ("hint", toJson s!"no card named {id}; reply to the directory for the list")]
    -- A spell that did not fit: which part, where, and the spell to resend; all from the reply itself.
    else if cls == "badSpell" then
      [("object", toJson named)] ++ ["clause", "reason", "hint"].filterMap fun k => (outcome.getObjVal? k).toOption.map (k, ·)
    -- A quota: how many, and when the next may start; nothing about the turn.
    else if cls == "quota" then ["reason", "next"].filterMap fun k => (outcome.getObjVal? k).toOption.map (k, ·)
    else if id != named then [("object", toJson named)] else []))

/-- An entry as `reader` may see it. The identity's own principal sees it whole. Anyone else
    sees a refusal only as its public projection, and any other entry as its chain fields,
    identity, turn and outcome tag, with the roots and writes of objects it may view; the rest
    is elided and counted. Results, offers, sends, sources and checkpoints never show. -/
def projectEntry (w : World) (reader : String) (entry : Json) : Json :=
  let owner := ((entry.getObjVal? "identity").toOption.bind fun i => (i.getObjValAs? String "principal").toOption).getD ""
  if owner == reader && !reader.isEmpty then slugged entry
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

/-- A law text's clauses as written: name, reading (if any), and the expression's text. -/
def lawClauses (text : String) : List (String × Option String × String) :=
  ((text.splitOn "\n").map (·.trimAscii.toString)).filterMap fun line => do
    let rest ← (line.dropPrefix? "law ").map (·.toString)
    let name := (rest.takeWhile fun c => c.isAlphanum || c == '_').toString
    let after := (rest.drop name.length).toString.trimAsciiStart.toString
    let (reading, after) := match lawReading after with
      | .ok (some (r, more)) => (some r, more.trimAsciiStart.toString)
      | _ => (none, after)
    let expr ← after.dropPrefix? ":"
    return (name, reading, expr.toString.trimAscii.toString)

/-- The pin and law text `id` had at `version`: its current ones, with each later reprogram and
    amendment undone (newest first), as the admitted entries that made later versions record them. -/
def pinAndLawAt (w : World) (o : Object) (id : String) (version : Nat) : String × String := Id.run do
  let mut pin := o.pin
  let mut law := o.lawText
  for i in ((w.touched[id]?).getD #[]).reverse do
    let some entry := w.entries[i]? | continue
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
  let clauses := lawClauses law
  let current := lawClauses o.lawText
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

/-- A page of `(height, item)` pairs, ascending by height: after `after` (exclusive), or with
    `reverse: true` descending below `before` (exclusive; from the newest when absent); at most `limit`
    (1..100, default 100). The items and whether more follow. -/
def pageByHeight (j : Json) (items : Array (Nat × Json)) : Except String (Array Json × Bool) := do
  let limit := (← optNat j "limit").getD Limits.maxHistoryLimit
  if limit == 0 || limit > Limits.maxHistoryLimit then throw s!"limit must be 1..{Limits.maxHistoryLimit}"
  let reverse ← match j.getObjVal? "reverse" with
    | .ok (.bool b) => pure b
    | .ok _ => throw "reverse must be true or false"
    | .error _ => pure false
  let chosen ← if reverse then do
      let before ← optNat j "before"
      pure (items.reverse.filter fun (h, _) => before.all (h < ·))
    else do
      let after := (← optNat j "after").getD 0
      pure (items.filter fun (h, _) => h > after)
  return ((chosen.extract 0 limit).map (·.2), decide (chosen.size > limit))

/-- Every source the journal carries, as `(height, record {cid, name, text, height})`: an entry's `sources`
    (named as the compile inputs that introduced it name it) and a library entry's modules, each once,
    at the first entry that carried it. -/
def sourceRecords (w : World) : Array (Nat × String × Json) := Id.run do
  let mut names : Std.HashMap String String := {}
  for entry in w.entries do
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let compiles := ((outcome.getObjVal? "compile").toOption.toList ++
      (((outcome.getObjVal? "creates").toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap fun c => (c.getObjVal? "compile").toOption)
    for c in compiles do
      for m in ((c.getObjVal? "modules").toOption.bind (·.getArr?.toOption)).getD #[] do
        if let (.ok n, .ok cid) := (m.getObjValAs? String "name", m.getObjValAs? String "cid") then
          unless names.contains cid do names := names.insert cid n
  let mut out : Array (Nat × String × Json) := #[]
  let mut seen : Std.HashSet String := {}
  for (entry, i) in w.entries.zipIdx do
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
  let (shown, more) ← pageByHeight j ((sourceRecords w).filterMap fun (h, cid, r) => if readable.contains cid then some (h, r) else none)
  return Json.mkObj [("status", toJson "sources"), ("sources", Json.arr shown), ("more", toJson more)]

/-- `world-grants {principal, after?, before?, reverse?, limit?}`: every grant an admitted entry made whose
    object the reader may view, as it stands now (`revoked`, `uses` left), with the `height` and `hash` of
    the entry that made it, paged by that height. -/
def grantsOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let mut items : Array (Nat × Json) := #[]
  for (entry, i) in w.entries.zipIdx do
    if tagOf entry != "admitted" then continue
    let made := ((entry.getObjVal? "outcome").toOption.bind (·.getObjVal? "grants" |>.toOption) |>.bind (·.getArr?.toOption)).getD #[]
    for g in made do
      let some id := (g.getObjValAs? String "id").toOption | continue
      let some now := w.grants[id]? | continue
      unless viewable w reader now.object do continue
      items := items.push (i + 1, (now.json.setObjVal! "revoked" (toJson now.revoked)).setObjVal! "height" (toJson (i + 1))
        |>.setObjVal! "hash" ((entry.getObjVal? "hash").toOption.getD Json.null))
  let (shown, more) ← pageByHeight j items
  return Json.mkObj [("status", toJson "grants"), ("grants", Json.arr shown), ("more", toJson more)]

/-- `world-entry {principal, hash, bytes?}`: the entry whose hash it is, as the reader may see it
    (`projectEntry`), and with `bytes: true` the lowercase hex of its canonical DAG-CBOR without `hash`
    when the reader sees it whole (the identity's own principal); `unknown` otherwise. -/
def entryOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let hash ← j.getObjValAs? String "hash"
  let some entry := w.entries.find? fun e => (e.getObjValAs? String "hash").toOption == some hash
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
  let (shown, more) ← pageByHeight j (w.entries.zipIdx.map fun (e, i) => (i + 1, e))
  return Json.mkObj [("status", toJson "entries"), ("entries", Json.arr (shown.map (projectEntry w reader))),
    ("more", toJson more)]

/-- Everything a slug may name, as `(cid, kind)`: every entry's hash (`receipt`); every pin an
    entry gave an object `reader` may view (`pin`); the state CIDs the journal names for such an
    object: a created seed, a write's `cid` (`state`). -/
def slugTargets (w : World) (reader : String) : Array (String × String) := Id.run do
  let mut out : Array (String × String) := #[]
  let seen := fun (id : String) => viewable w reader id
  for entry in w.entries do
    if let .ok h := entry.getObjValAs? String "hash" then out := out.push (h, "receipt")
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let arr := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
    let object := fun (j : Json) => (j.getObjValAs? String "object").toOption.getD ""
    match tagOf entry with
    | "created" =>
      if seen (object outcome) then
        if let .ok p := outcome.getObjValAs? String "pin" then out := out.push (p, "pin")
        if let .ok seed := outcome.getObjVal? "seed" then out := out.push (Journal.bodyHash seed, "state")
    | "admitted" =>
      for c in arr "creates" do
        if seen (object c) then
          if let .ok p := c.getObjValAs? String "pin" then out := out.push (p, "pin")
          if let .ok seed := c.getObjVal? "seed" then out := out.push (Journal.bodyHash seed, "state")
      for r in arr "reprograms" do
        if seen (object r) then
          if let .ok p := r.getObjValAs? String "newPin" then out := out.push (p, "pin")
      for x in arr "writes" do
        if seen (object x) then
          if let .ok c := x.getObjValAs? String "cid" then out := out.push (c, "state")
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
  | [(cid, kind)] =>
    let receipt := if kind != "receipt" then none else
      (w.entries.find? fun e => (e.getObjValAs? String "hash").toOption == some cid).map (projectEntry w reader)
    return Json.mkObj ([("status", toJson "resolved"), ("slug", toJson slug), ("kind", toJson kind),
      ("cid", toJson cid)] ++ (receipt.map fun r => [("receipt", r)]).getD [])
  | many => return Json.mkObj [("status", toJson "ambiguous"), ("slug", toJson slug), ("matches", toJson many.length),
      ("message", toJson s!"ambiguous: {many.length} matches; cite the object and version")]


/-- `world-receipt {principal, identity, of?}`: the receipt of identity (`of`, default the
    reader, `identity`), projected under the reader's authority. -/
def receipt (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let owner := (← optText j "of").getD reader
  match w.receipts[identityKey owner intent]? with
  | none => return Json.mkObj [("status", toJson "unknown")]
  | some index =>
    let entry := w.entries[index]!
    let shown := projectEntry w reader entry
    if owner != reader && tagOf entry == "refused" then return publicRefusal entry
    return Json.mkObj [("status", toJson "receipt"), ("receipt", shown)]

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
    ("entries", Json.arr (page.map fun index => projectEntry w reader w.entries[index]!)),
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
    let some next := w.entries[index]? | break
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
    let entry ← w.entries[index]?
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
      let entry ← w.entries[index]?
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
  let items := w.published.filterMap fun (index, i) => do
    let entry ← w.entries[index]?
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
    pure (index + 1, Json.mkObj ([("height", toJson (index + 1)), ("ordinal", toJson i),
      ("id", (p.getObjVal? "id").toOption.getD Json.null), ("object", toJson object), ("page", toJson title),
      ("section", toJson part), ("body", toJson body),
      ("hash", (entry.getObjVal? "hash").toOption.getD Json.null)] ++ replyTo))
  let (shown, more) ← pageByHeight j items
  return Json.mkObj [("status", toJson "publications"), ("publications", Json.arr shown), ("more", toJson more)]

end Delvetalk.Host

namespace Delvetalk.Host
open Lean in
#guard [Json.null, .bool true, .bool false, toJson (5 : Nat), toJson (-3 : Int), .str "a\"b\\c\n\u0001é", .arr #[],
  .arr #[toJson (1 : Nat), .str "x"], Json.mkObj [],
  Json.mkObj [("k", toJson (1 : Nat)), ("q\"", .arr #[Json.mkObj [("z", .null)]])]].all fun j => compressedSize j == j.compress.utf8ByteSize
end Delvetalk.Host
