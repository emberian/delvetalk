/- The world kernel and its session ops. `commit` and friends are pure: the turn
   loop calls them with a proposal and gets the next World and a receipt. The IO
   layer at the bottom owns the journal file and nothing else. -/
import Delvetalk.Host.Store
import Delvetalk.Host.Journal
import Delvetalk.Host.Law
import Compiler.ObjectiveBendDataWire

namespace Delvetalk.Host
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)
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

def boundedText (what : String) (cap : Nat) (s : String) : Except String String := do
  if s.isEmpty || s.utf8ByteSize > cap then throw s!"{what} must be 1..{cap} bytes"
  return s

inductive EditKind where
  | keep
  | set (value : Data)
  | add (amount : Nat)

structure Edit where
  field : String
  kind : EditKind

def EditKind.json : EditKind → Json
  | .keep => Json.mkObj [("tag", toJson "keep")]
  | .set v => Json.mkObj [("tag", toJson "set"), ("value", dataJson v)]
  | .add n => Json.mkObj [("tag", toJson "add"), ("value", toJson (toString n))]

def Edit.json (e : Edit) : Json := Json.mkObj [("field", toJson e.field), ("edit", e.kind.json)]

def parseEdit (j : Json) : Except String Edit := do
  let field ← j.getObjValAs? String "field"
  let edit ← j.getObjVal? "edit"
  let kind ← match ← edit.getObjValAs? String "tag" with
    | "keep" => pure EditKind.keep
    | "set" => pure (EditKind.set (← decodeData Limits.dataDepth (← edit.getObjVal? "value")))
    | "add" => pure (EditKind.add (← natField edit "value"))
    | other => throw s!"unknown edit tag {other}"
  return ⟨field, kind⟩

structure Proposal where
  principal : String
  intent : String
  roots : List (String × Nat)
  writes : List (String × List Edit)
  turn : Nat := 0

def rootsJson (roots : List (String × Nat)) : Json :=
  Json.arr (roots.toArray.map fun (o, v) => Json.mkObj [("object", toJson o), ("version", toJson v)])

def writesJson (writes : List (String × List Edit)) : Json :=
  Json.arr (writes.toArray.map fun (o, es) => Json.mkObj
    [("object", toJson o), ("edits", Json.arr (es.toArray.map Edit.json))])

def parseRoots (j : Json) : Except String (List (String × Nat)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxRoots then throw "too many roots"
  let mut out : List (String × Nat) := []
  for r in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← r.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate root"
    out := out ++ [(object, ← natField r "version")]
  return out

def parseWrites (j : Json) : Except String (List (String × List Edit)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxWrites then throw "too many writes"
  let mut out : List (String × List Edit) := []
  for w in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← w.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate write"
    let rawEdits ← (← w.getObjVal? "edits").getArr?
    if rawEdits.size > Limits.maxEditsPerWrite then throw "too many edits"
    let mut edits : List Edit := []
    for e in rawEdits do
      let edit ← parseEdit e
      if edits.any (·.field == edit.field) then throw "duplicate edit field"
      edits := edits ++ [edit]
    out := out ++ [(object, edits)]
  return out

def parseProposal (j : Json) : Except String Proposal := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let turn := match j.getObjVal? "turn" with
    | .ok t => (natOf t).toOption.getD 0
    | .error _ => 0
  return ⟨principal, intent, ← parseRoots (← j.getObjVal? "roots"), ← parseWrites (← j.getObjVal? "writes"), turn⟩

/-- Digest binding an identity to the request that first used it. -/
def Proposal.digest (p : Proposal) : String :=
  Journal.bodyHash (Json.mkObj [("roots", rootsJson p.roots), ("writes", writesJson p.writes),
    ("turn", toJson p.turn)])

/-! ## Judging -/

/-- The closed set of refusal classes. -/
def refusalClasses : List String :=
  ["staleRoot", "unreadWrite", "typeMismatch", "lawRefused", "unknownObject", "duplicateIdentity",
   "evaluation"]

structure Refusal where
  cls : String
  clause : Option String := none
  object : Option String := none
  /-- Named reason for an `evaluation` refusal. -/
  reason : Option String := none

def replaceField (fields : List (String × Data)) (name : String) (v : Data) : List (String × Data) :=
  fields.map fun (k, old) => if k == name then (k, v) else (k, old)

def applyEdit (fields : List (String × Data)) (e : Edit) : Option (List (String × Data)) :=
  match fields.find? (·.1 == e.field) with
  | none => none
  | some (_, old) => match e.kind with
      | .keep => some fields
      | .set v => some (replaceField fields e.field v)
      | .add n => match old with
          | .natural m => some (replaceField fields e.field (.natural (m + n)))
          | _ => none

def applyEdits : Data → List Edit → Option Data
  | .record fields, edits => (edits.foldlM applyEdit fields).map .record
  | _, _ => none

/-- Roots current, writes read, results conform, laws admit. Returns the objects
    as they would be installed. `height` is the height the entry would take. -/
def judge (w : World) (height : Nat) (p : Proposal) : Except Refusal (List (String × Object)) := do
  for id in p.roots.map (·.1) ++ p.writes.map (·.1) do
    unless w.objects.contains id do throw { cls := "unknownObject", object := id }
  for (id, seen) in p.roots do
    if let some o := w.objects[id]? then
      if o.version != seen then throw { cls := "staleRoot", object := id }
  for (id, _) in p.writes do
    unless p.roots.any (·.1 == id) do throw { cls := "unreadWrite", object := id }
  let facts : Law.Facts := ⟨p.principal, p.principal, height, p.turn⟩
  let mut out : List (String × Object) := []
  for (id, edits) in p.writes do
    let some o := w.objects[id]? | throw { cls := "unknownObject", object := id }
    let some new := applyEdits o.state edits | throw { cls := "typeMismatch", object := id }
    unless new.conforms o.stateType && (dataJson new).compress.utf8ByteSize ≤ Limits.maxStateBytes do
      throw { cls := "typeMismatch", object := id }
    if let some clause := Law.refusedBy o.law facts (some o.state) new then
      throw { cls := "lawRefused", clause, object := id }
    out := out ++ [(id, { o with version := o.version + 1, state := new })]
  return out

/-! ## Entries -/

def identityJson (principal intent : String) : Json :=
  Json.mkObj [("principal", toJson principal), ("intent", toJson intent)]

/-- Append a sealed entry to the world. -/
def record (w : World) (entry : Json) (key : String) (touch : List String) : World :=
  let hash := (entry.getObjValAs? String "hash").toOption.getD ""
  let index := w.entries.size
  { w with
    height := w.height + 1, head := hash, entries := w.entries.push entry
    receipts := if w.receipts.contains key then w.receipts else w.receipts.insert key index
    touched := touch.foldl (fun t id => t.insert id ((t.getD id #[]).push index)) w.touched }

def push (w : World) (key : String) (fields : List (String × Json)) (touch : List String) :
    World × Json :=
  let entry := Journal.sealEntry (w.height + 1) w.head fields
  (record w entry key touch, entry)

def statusOf (entry : Json) : String :=
  match entry.getObjVal? "outcome" |>.bind (·.getObjValAs? String "tag") with
  | .ok tag => tag
  | .error _ => "unknown"

def reply (entry : Json) : Json :=
  Json.mkObj [("status", toJson (statusOf entry)), ("receipt", entry)]

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
    if (entry.getObjValAs? String "request").toOption == some digest then some (reply entry)
    else some (duplicate principal intent entry)

/-- The commit rule. Pure: the turn loop calls this with the roots it recorded and
    the writes it produced. Returns the next world and the reply (a receipt). -/
def commit (w : World) (p : Proposal) (extra : List (String × Json) := [])
    (forced : Option Refusal := none) : World × Json :=
  match retained w p.principal p.intent p.digest with
  | some r => (w, r)
  | none =>
    let key := identityKey p.principal p.intent
    let base := [("identity", identityJson p.principal p.intent), ("roots", rootsJson p.roots),
      ("turn", toJson p.turn), ("request", toJson p.digest)] ++ extra
    let verdict : Except Refusal (List (String × Object)) :=
      match forced with | some r => .error r | none => judge w (w.height + 1) p
    match verdict with
    | .error r =>
      let outcome := Json.mkObj ([("tag", toJson "refused"), ("class", toJson r.cls)] ++
        (r.clause.map fun c => [("clause", toJson c)]).getD [] ++
        (r.object.map fun o => [("object", toJson o)]).getD [] ++
        (r.reason.map fun o => [("reason", toJson o)]).getD [])
      let (w', entry) := push w key (base ++ [("outcome", outcome)]) []
      (w', reply entry)
    | .ok updates =>
      let w := updates.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      let writes := Json.arr (updates.toArray.map fun (id, o) => Json.mkObj
        [("object", toJson id), ("version", toJson o.version),
         ("edits", Json.arr ((p.writes.lookup id |>.getD []).toArray.map Edit.json))])
      let outcome := Json.mkObj [("tag", toJson "admitted"), ("writes", writes)]
      let (w', entry) := push w key (base ++ [("outcome", outcome)]) (updates.map (·.1))
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

/-- The state type is the type of the package's entry definition: a zero-argument
    `def initial() -> State` has type `State`, which must be a closed record of
    first-order data. The entry's own value is not used; the seed is explicit. -/
def stateTypeOk (ty : Minidregg.Theory.ObjectiveBendTypes.Ty) : Bool :=
  ty.isData && match ty with
    | .field .. | .emptyRow => true
    | _ => false

def buildObject (inputs seed : Json) : Except String (Object × String) := do
  let (artifact, ty, laws) ← Package.compileKeepingLaws inputs
  unless stateTypeOk ty do
    throw "package entry type must be a closed record of first-order data (a zero-argument definition returning the state record)"
  let state ← decodeData Limits.dataDepth seed
  unless state.conforms ty do throw "seed does not conform to the package state type"
  if (dataJson state).compress.utf8ByteSize > Limits.maxStateBytes then throw "seed exceeds state byte capacity"
  let pin ← artifact.getObjValAs? String "packetSha256"
  let sources ← artifact.getObjValAs? String "sourcesSha256"
  let inputsKey := Journal.bodyHash (Json.mkObj
    (inputs.getObj?.toOption.map (·.toList.filter (·.1 != "entry")) |>.getD []))
  return ({ pin, law := laws, version := 0, state, stateType := ty, inputs, inputsKey }, sources)

def createOutcome (id : String) (o : Object) (sources : String) (artifact seed : Json) : Json :=
  Json.mkObj [("tag", toJson "created"), ("object", toJson id), ("pin", toJson o.pin),
    ("sourcesSha256", toJson sources), ("compile", artifact), ("seed", seed)]

def create (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let id ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let digest := Journal.bodyHash (Json.mkObj
    (j.getObj?.toOption.map (·.toList.filter (·.1 != "op")) |>.getD []))
  if let some r := retained w principal intent digest then return (w, r)
  if id == "self" then throw "object id self is reserved for the running object"
  if w.objects.contains id then throw s!"object {id} already exists"
  if w.objects.size ≥ Limits.maxObjects then throw "object capacity reached"
  let inputs ← compileInputs j
  let seed ← j.getObjVal? "seed"
  let (o, sources) ← buildObject inputs seed
  -- An `artifact` claim is only a claim: the journal keeps the inputs, never the claim.
  let outcome := createOutcome id o sources inputs seed
  let (w', entry) := push { w with objects := w.objects.insert id o } (identityKey principal intent)
    [("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson digest), ("outcome", outcome)] [id]
  return (w', reply entry)

/-! ## Replay -/

def replayEntry (w : World) (entry : Json) : Except String World := do
  let identity ← entry.getObjVal? "identity"
  let principal ← identity.getObjValAs? String "principal"
  let intent ← identity.getObjValAs? String "intent"
  let key := identityKey principal intent
  let outcome ← entry.getObjVal? "outcome"
  match ← outcome.getObjValAs? String "tag" with
  | "created" =>
    let id ← outcome.getObjValAs? String "object"
    if w.objects.contains id then throw s!"object {id} created twice"
    let (o, sources) ← buildObject (← outcome.getObjVal? "compile") (← outcome.getObjVal? "seed")
    unless o.pin == (← outcome.getObjValAs? String "pin") && sources == (← outcome.getObjValAs? String "sourcesSha256") do
      throw s!"object {id} no longer compiles to its recorded pin"
    return record { w with objects := w.objects.insert id o } entry key [id]
  | "refused" =>
    let cls ← outcome.getObjValAs? String "class"
    unless refusalClasses.contains cls do throw s!"unknown refusal class {cls}"
    return record w entry key []
  | "admitted" =>
    let rawWrites ← (← outcome.getObjVal? "writes").getArr?
    let writes ← parseWrites (Json.arr rawWrites)
    let turn ← natField entry "turn"
    let p : Proposal := ⟨principal, intent, ← parseRoots (← entry.getObjVal? "roots"), writes, turn⟩
    unless (entry.getObjValAs? String "request").toOption == some p.digest do throw "request digest does not match"
    match judge w (w.height + 1) p with
    | .error r => throw s!"admitted entry would be refused ({r.cls})"
    | .ok updates =>
      for raw in rawWrites do
        let id ← raw.getObjValAs? String "object"
        let some (_, o) := updates.find? (·.1 == id) | throw "write missing"
        unless (← natField raw "version") == o.version do throw "write version out of sequence"
      let w := updates.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      return record w entry key (updates.map (·.1))
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

/-! ## Reads -/

def view (w : World) (j : Json) : Except String Json := do
  let id ← j.getObjValAs? String "object"
  discard <| boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  match w.objects[id]? with
  | none => return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  | some o => return Json.mkObj [("status", toJson "viewed"), ("object", toJson id),
      ("version", toJson o.version), ("state", dataJson o.state), ("pin", toJson o.pin)]

def receipt (w : World) (j : Json) : Except String Json := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  match w.receipts[identityKey principal intent]? with
  | none => return Json.mkObj [("status", toJson "unknown")]
  | some index => return Json.mkObj [("status", toJson "receipt"), ("receipt", w.entries[index]!)]

def history (w : World) (j : Json) : Except String Json := do
  let id ← j.getObjValAs? String "object"
  let after := match j.getObjVal? "after" with
    | .ok a => (natOf a).toOption.getD 0
    | .error _ => 0
  let limit := min Limits.maxHistoryLimit (match j.getObjVal? "limit" with
    | .ok l => (natOf l).toOption.getD Limits.maxHistoryLimit
    | .error _ => Limits.maxHistoryLimit)
  if !w.objects.contains id then return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  let all := (w.touched.getD id #[]).filter fun index => index + 1 > after
  let page := all.extract 0 limit
  return Json.mkObj [("status", toJson "history"), ("object", toJson id),
    ("entries", Json.arr (page.map fun index => w.entries[index]!)),
    ("more", toJson (decide (all.size > limit)))]

end Delvetalk.Host
