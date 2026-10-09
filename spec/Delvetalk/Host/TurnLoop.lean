/- Driving an activity against the store. A turn reads committed state, collects
   the roots it viewed and the writes it performed, and ends in exactly one
   `commit`. The wire shapes of Plans and responses are fixed in `answer`.

   Plans (variant label, payload record):
     view  {object}                    -> viewed {version, state} | denied {}
     write {object, edits}             -> written {} | refused {clause} (or {})
     call  {object, method, argument}  -> reply <result> | refused {clause} (or {})
   `object` is a label; `self` names the object whose method is running.
   `edits` is a `List`: nil {} | cons {head, tail}; `head` is
   {field: label, edit: keep {} | add <natural> | set <any data>}.
   Every other Plan label refuses the turn: `plan not supported: <label>`. -/
import Delvetalk.Host.Ops
import Delvetalk.Turn

namespace Delvetalk.Host
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Theory.ObjectiveBendTypes (Ty)
open Minidregg.Compiler.ObjectiveBendDataWire (dataJson decodeData)

structure TurnRequest where
  principal : String
  object : String
  method : String
  argument : Data
  intent : String
  limits : Json
  /-- Digest of the whole request; binds the identity for retries. -/
  digest : String

def parseTurn (j : Json) : Except String TurnRequest := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let object ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let method ← boundedText "method" Limits.maxMethodBytes (← j.getObjValAs? String "method")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  unless Minidregg.Compiler.ObjectiveBendParse.isIdent method.toList do throw "invalid method name"
  let argument ← decodeData Limits.dataDepth (← j.getObjVal? "argument")
  let limits := (j.getObjVal? "limits").toOption.getD (Json.mkObj [])
  let digest := Journal.bodyHash (Json.mkObj [("principal", toJson principal), ("object", toJson object),
    ("method", toJson method), ("argument", dataJson argument), ("limits", limits)])
  return ⟨principal, object, method, argument, intent, limits, digest⟩

inductive Abort where
  /-- The request is not a well-formed turn; nothing is journaled. -/
  | request (message : String)
  /-- The turn is refused by name; a refused entry is journaled. -/
  | evaluation (reason : String)
  deriving Inhabited

structure TurnState where
  world : World
  roots : List (String × Nat) := []
  writes : List (String × List Edit) := []
  ticks : Nat
  plans : Nat := 0
  limits : Json

abbrev M := ExceptT Abort (StateM TurnState)

def evaluation {α : Type} (reason : String) : M α := throw (.evaluation reason)

def liftEval {α : Type} (r : Except String α) : M α :=
  match r with
  | .ok a => pure a
  | .error e => throw (.evaluation e)

def recordRoot (id : String) (version : Nat) : M Unit := do
  let s ← get
  unless s.roots.any (·.1 == id) do
    if s.roots.length ≥ Limits.maxRoots then evaluation "turn exceeds the root capacity"
    set { s with roots := s.roots ++ [(id, version)] }

/-- Fold a later edit of one field into an earlier one; `none` if they cannot meet. -/
def mergeEdit (old new : EditKind) : Option EditKind :=
  match old, new with
  | _, .keep => some old
  | .keep, n => some n
  | _, .set v => some (.set v)
  | .add a, .add b => some (.add (a + b))
  | .set (.natural m), .add b => some (.set (.natural (m + b)))
  | _, _ => none

def mergeEdits (old : List Edit) (new : List Edit) : Option (List Edit) :=
  new.foldlM (init := old) fun acc e =>
    match acc.find? (·.field == e.field) with
    | none => some (acc ++ [e])
    | some prior => (mergeEdit prior.kind e.kind).map fun k =>
        acc.map fun x => if x.field == e.field then { x with kind := k } else x

def field? (fields : List (String × Data)) (name : String) : Option Data := fields.lookup name

def labelOf : Data → Option String
  | .label s => some s
  | _ => none

partial def parseEditList : Data → Option (List Edit)
  | .variant "nil" _ => some []
  | .variant "cons" (.record f) => do
    let .record head ← field? f "head" | none
    let field ← (field? head "field").bind labelOf
    let .variant tag payload ← field? head "edit" | none
    let kind ← match tag, payload with
      | "keep", _ => some EditKind.keep
      | "add", .natural n => some (EditKind.add n)
      | "set", v => some (EditKind.set v)
      | _, _ => none
    let rest ← parseEditList (← field? f "tail")
    some (⟨field, kind⟩ :: rest)
  | _ => none

def emptyRecord : Data := .record []

/-- The first payload that makes a response conform to the Response type. -/
def respond (responseType : Ty) (label : String) (payloads : List Data) : M Data := do
  for p in payloads do
    let d := Data.variant label p
    if d.conforms responseType then return d
  evaluation s!"response type cannot carry {label}"

def refusedWith (responseType : Ty) (clause : String) : M Data :=
  respond responseType "refused" [.record [("clause", .label clause)], emptyRecord]

def compiledMethod (obj : Object) (method : String) : M Compiled := do
  let key := obj.inputsKey ++ "/" ++ method
  let s ← get
  match s.world.compiled[key]? with
  | some c => return c
  | none =>
    let inputs := obj.inputs.setObjVal! "entry" (toJson method)
    match Package.compileKeepingLaws inputs with
    | .error e => throw (.request s!"method {method} does not compile: {e}")
    | .ok (artifact, ty, _) =>
      let packet ← match artifact.getObjVal? "packet" with
        | .ok p => pure p
        | .error e => throw (.request e)
      let c : Compiled := ⟨packet, ty⟩
      if s.world.compiled.size < Limits.maxCompiledPackets then
        set { s with world := { s.world with compiled := s.world.compiled.insert key c } }
      return c

def budgetsNow : M Delvetalk.Turn.Budgets := do
  let s ← get
  liftEval (Delvetalk.Turn.budgets (s.limits.setObjVal! "ticks" (toJson (toString s.ticks))))

def spend (used : Nat) : M Unit :=
  modify fun s => { s with ticks := s.ticks - used }

def countPlan : M Unit := do
  let s ← get
  if s.plans ≥ Limits.maxPlansPerTurn then evaluation "turn exceeds the plan capacity"
  set { s with plans := s.plans + 1 }

def addWrite (id : String) (edits : List Edit) : M Bool := do
  let s ← get
  unless s.roots.any (·.1 == id) do return false
  let prior := (s.writes.lookup id).getD []
  let some merged := mergeEdits prior edits | return false
  if merged.length > Limits.maxEditsPerWrite then evaluation "turn exceeds the edit capacity"
  let writes := if s.writes.any (·.1 == id) then
      s.writes.map fun (k, es) => if k == id then (k, merged) else (k, es)
    else
      if s.writes.length ≥ Limits.maxWrites then s.writes else s.writes ++ [(id, merged)]
  if !writes.any (·.1 == id) then evaluation "turn exceeds the write capacity"
  set { s with writes }
  return true

mutual
/-- Run `method` of object `id` against its committed state; its result is returned. -/
partial def runMethod (depth : Nat) (id method : String) (argument : Data) : M Data := do
  let s ← get
  let some obj := s.world.objects[id]? | evaluation s!"unknown object {id}"
  recordRoot id obj.version
  let compiled ← compiledMethod obj method
  let result := match compiled.type with
    | .arrow _ _ _ (.arrow _ _ _ r) => some r
    | _ => none
  let some r := result | throw (.request s!"method {method} must take (state, argument)")
  match r with
  | .computation .. =>
    let b ← budgetsNow
    let started ← liftEval (Delvetalk.Turn.startActivity compiled.packet [obj.state, argument] b)
    drive depth id compiled started 0
  | _ =>
    unless r.isData do throw (.request s!"method {method} must be pure data or an activity")
    let st ← get
    let lim := st.limits.setObjVal! "ticks" (toJson (toString st.ticks))
    match Package.executeDataValues compiled.packet #[obj.state, argument] lim with
    | .error e => evaluation e
    | .ok (.refused failure usage) =>
      spend (usage.ticksUsed + usage.conversionNodes)
      evaluation s!"turn refused: {failure}"
    | .ok (.finished value _ _ usage) =>
      spend (usage.ticksUsed + usage.conversionNodes)
      let .record fields := value | evaluation "a pure method must return the state record"
      let _ ← addWrite id (fields.map fun (k, v) => ⟨k, .set v⟩)
      return value

partial def drive (depth : Nat) (self : String) (compiled : Compiled)
    (outcome : Delvetalk.Turn.Outcome) (_n : Nat) : M Data := do
  match outcome with
  | .finished value _ used => spend used; return value
  | .yielded plan _ responseType checkpoint used =>
    spend used
    countPlan
    let response ← answer depth self plan responseType
    let b ← budgetsNow
    let next ← liftEval (Delvetalk.Turn.resumeActivity compiled.packet checkpoint response b)
    drive depth self compiled next 0

partial def answer (depth : Nat) (self : String) (plan : Data) (responseType : Ty) : M Data := do
  let resolve := fun (name : String) => if name == "self" then self else name
  match plan with
  | .variant "view" (.record f) =>
    let some name := (field? f "object").bind labelOf | evaluation "malformed view plan"
    let id := resolve name
    match (← get).world.objects[id]? with
    | none => respond responseType "denied" [emptyRecord]
    | some o =>
      recordRoot id o.version
      respond responseType "viewed" [.record [("version", .natural o.version), ("state", o.state)]]
  | .variant "write" (.record f) =>
    let some name := (field? f "object").bind labelOf | evaluation "malformed write plan"
    let some edits := (field? f "edits").bind parseEditList | evaluation "malformed write plan"
    if edits.length > Limits.maxEditsPerWrite then evaluation "turn exceeds the edit capacity"
    let id := resolve name
    if (← addWrite id edits) then respond responseType "written" [emptyRecord]
    else if (← get).roots.any (·.1 == id) then refusedWith responseType "typeMismatch"
    else refusedWith responseType "unreadWrite"
  | .variant "call" (.record f) =>
    let some name := (field? f "object").bind labelOf | evaluation "malformed call plan"
    let some method := (field? f "method").bind labelOf | evaluation "malformed call plan"
    let some argument := field? f "argument" | evaluation "malformed call plan"
    let id := resolve name
    if !(← get).world.objects.contains id then refusedWith responseType "unknownObject"
    else if depth + 1 > Limits.maxCallDepth then evaluation "call depth exceeded"
    else
      let result ← runMethod (depth + 1) id method argument
      respond responseType "reply" [result]
  | .variant label _ => evaluation s!"plan not supported: {label}"
  | _ => evaluation "plan is not a variant"
end

def editsFromRoots (roots : List (String × Nat)) : List (String × Nat) := roots

/-- Retry rule for turns: the identity is bound to the whole turn request. -/
def retainedTurn (w : World) (r : TurnRequest) : Option Json :=
  match w.receipts[identityKey r.principal r.intent]? with
  | none => none
  | some index =>
    let entry := w.entries[index]!
    if (entry.getObjValAs? String "turnRequest").toOption == some r.digest then some (reply entry)
    else some (duplicate r.principal r.intent entry)

/-- Lift `result` and `ticksUsed` of the receipt to the reply. -/
def turnReply (r : Json) : Json :=
  match r.getObjVal? "receipt" with
  | .error _ => r
  | .ok entry =>
    let extra := ["result", "ticksUsed"].filterMap fun k => (entry.getObjVal? k).toOption.map (k, ·)
    Json.mkObj ([("status", (r.getObjVal? "status").toOption.getD Json.null), ("receipt", entry)] ++ extra)

/-- One turn: drive the method, then one `commit`. Request errors (unknown method,
    wrong arity) journal nothing; every other end is a receipt. -/
def runTurn (w : World) (req : TurnRequest) : Except String (World × Json) := do
  if let some r := retainedTurn w req then return (w, r)
  let init : TurnState := { world := w, ticks := 1000000, limits := req.limits }
  let ticks ← match Delvetalk.Turn.budgets req.limits with
    | .ok b => pure b.ticks
    | .error e => throw e
  let (result, st) := (runMethod 0 req.object req.method req.argument |>.run).run { init with ticks }
  let w := { w with compiled := st.world.compiled }
  let used := ticks - st.ticks
  let proposal : Proposal := ⟨req.principal, req.intent, st.roots, st.writes, w.height + 1⟩
  let base := [("turnRequest", toJson req.digest), ("ticksUsed", toJson used)]
  match result with
  | .error (.request message) => throw message
  | .error (.evaluation reason) =>
    let cls := if st.roots.isEmpty && !w.objects.contains req.object then "unknownObject" else "evaluation"
    let (w', r) := commit w { proposal with writes := [] } base
      (some { cls, reason := some reason, object := if cls == "unknownObject" then some req.object else none })
    return (w', turnReply r)
  | .ok value =>
    let (w', r) := commit w proposal (base ++ [("result", dataJson value)])
    return (w', turnReply r)

end Delvetalk.Host
