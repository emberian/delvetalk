/- Driving an activity against the store. A turn reads committed state, collects
   the roots it viewed and the writes it performed, and ends in exactly one
   `commit`. The wire shapes are those of `world/lib/Plan.obend`:

   A method is `(state, [input,] context) -> Activity<Plan, Response, A>` or the
   same with a pure data result (the new state). `context` is
   `Abi.Context {object, principal, inputOrigin}`.
   Plans answered:
     view  {object: Reference}                     -> viewed {version, state} | denied {}
     write {object: Reference, edits: Edits}       -> written {} | refused {clause}
     call  {object: Reference, method, argument}   -> returned {result} | refused {clause}
   A Reference `{world, object}` names an object of this world when `world` is "".
   `viewed` carries the object's whole state. Every other Plan label refuses the
   turn: `plan not supported: <label>`. -/
import Delvetalk.Host.Ops
import Delvetalk.Turn

namespace Delvetalk.Host
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Theory.ObjectiveBendTypes (Ty DataBounds)
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
  writes : List (String × List Step) := []
  principal : String
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

def field? (fields : List (String × Data)) (name : String) : Option Data := fields.lookup name

def labelOf : Data → Option String
  | .label s => some s
  | _ => none

/-- A Reference naming this world's object. -/
def referenceId : Data → Option String
  | .record f => match (f.lookup "world").bind labelOf, (f.lookup "object").bind labelOf with
      | some "", some id => some id
      | _, _ => none
  | _ => none

def emptyRecord : Data := .record []

/-- The first payload that makes a response conform to the Response type. -/
def respond (bounds : DataBounds) (responseType : Ty) (label : String) (payloads : List Data) : M Data := do
  for p in payloads do
    let d := Data.variant label p
    if d.conformsUnder bounds responseType then return d
  evaluation s!"response type cannot carry {label}"

def refusedWith (bounds : DataBounds) (responseType : Ty) (clause : String) : M Data :=
  respond bounds responseType "refused" [.record [("clause", .label clause)], emptyRecord]

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
      let decoded ← match Minidregg.Theory.ObjectiveBendTyping.decodePacket packet with
        | .ok d => pure d
        | .error e => throw (.request e)
      let c : Compiled := ⟨packet, ty, decoded.source.assumptions.bounds, decoded.source.assumptions.rigid⟩
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

def addWrite (id : String) (step : Step) : M Bool := do
  let s ← get
  unless s.roots.any (·.1 == id) do return false
  if step.length > Limits.maxEditsPerWrite then evaluation "turn exceeds the edit capacity"
  let prior := (s.writes.lookup id).getD []
  if prior.length ≥ Limits.maxEditsPerWrite then evaluation "turn exceeds the edit capacity"
  let steps := prior ++ [step]
  if !s.writes.any (·.1 == id) && s.writes.length ≥ Limits.maxWrites then
    evaluation "turn exceeds the write capacity"
  let writes := if s.writes.any (·.1 == id) then
      s.writes.map fun (k, es) => if k == id then (k, steps) else (k, es)
    else s.writes ++ [(id, steps)]
  set { s with writes }
  return true

def contextData (id principal kind origin command : String) : Data :=
  .record [("world", .label ""), ("object", .label id), ("principal", .label principal),
    ("inputOrigin", .record [("kind", .label kind), ("object", .label origin), ("command", .label command),
      ("program", .label ""), ("immediatelyPrevious", .boolean false)])]

mutual
/-- Run `method` of object `id` against its committed state; its result is returned. -/
partial def runMethod (depth : Nat) (id method : String) (argument : Data) (origin : String) : M Data := do
  let s ← get
  let some obj := s.world.objects[id]? | evaluation s!"unknown object {id}"
  recordRoot id obj.version
  let compiled ← compiledMethod obj method
  let context := contextData id s.principal (if depth == 0 then "request" else "call") origin method
  let (arguments, r) ← match compiled.type with
    | .arrow _ _ _ (.arrow _ _ _ (.arrow _ _ _ r)) => pure ([obj.state, argument, context], r)
    | .arrow _ _ _ (.arrow _ _ _ r) => pure ([obj.state, context], r)
    | _ => throw (.request s!"method {method} must take (state, [input,] context)")
  match r with
  | .computation .. =>
    let b ← budgetsNow
    let started ← liftEval (Delvetalk.Turn.startActivity compiled.packet arguments b)
    drive depth id compiled started 0
  | _ =>
    unless r.isDataUnder compiled.bounds compiled.rigid Ty.dataFuel [] do throw (.request s!"method {method} must be pure data or an activity")
    let st ← get
    let lim := st.limits.setObjVal! "ticks" (toJson (toString st.ticks))
    match Package.executeDataValues compiled.packet arguments.toArray lim with
    | .error e => evaluation e
    | .ok (.refused failure usage) =>
      spend (usage.ticksUsed + usage.conversionNodes)
      evaluation s!"turn refused: {failure}"
    | .ok (.finished value _ _ usage) =>
      spend (usage.ticksUsed + usage.conversionNodes)
      let .record fields := value | evaluation "a pure method must return the state record"
      let _ ← addWrite id (fields.map fun (k, v) => (⟨k, .set v⟩ : Edit))
      return value

partial def drive (depth : Nat) (self : String) (compiled : Compiled)
    (outcome : Delvetalk.Turn.Outcome) (_n : Nat) : M Data := do
  match outcome with
  | .finished value _ used => spend used; return value
  | .yielded plan _ responseType checkpoint used =>
    spend used
    countPlan
    let response ← answer depth self compiled.bounds plan responseType
    let b ← budgetsNow
    let next ← liftEval (Delvetalk.Turn.resumeActivity compiled.packet checkpoint response b)
    drive depth self compiled next 0

partial def answer (depth : Nat) (self : String) (bounds : DataBounds) (plan : Data) (responseType : Ty) : M Data := do
  match plan with
  | .variant "view" (.record f) =>
    match (f.lookup "object").bind referenceId with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some id =>
      match (← get).world.objects[id]? with
      | none => respond bounds responseType "denied" [emptyRecord]
      | some o =>
        if !o.read.permits (← get).principal then respond bounds responseType "denied" [emptyRecord] else
        recordRoot id o.version
        respond bounds responseType "viewed" [.record [("version", .natural o.version), ("state", o.state)]]
  | .variant "write" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed write plan"
    let some step := (f.lookup "edits").bind parseStep | evaluation "malformed write plan"
    match referenceId target with
    | none => refusedWith bounds responseType "unreadWrite"
    | some id =>
      if (← addWrite id step) then respond bounds responseType "written" [emptyRecord]
      else refusedWith bounds responseType "unreadWrite"
  | .variant "call" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed call plan"
    let some method := (f.lookup "method").bind labelOf | evaluation "malformed call plan"
    let some argument := f.lookup "argument" | evaluation "malformed call plan"
    match referenceId target with
    | none => refusedWith bounds responseType "unknownObject"
    | some id =>
      if !(← get).world.objects.contains id then refusedWith bounds responseType "unknownObject"
      else if depth + 1 > Limits.maxCallDepth then evaluation "call depth exceeded"
      else
        let result ← runMethod (depth + 1) id method argument self
        respond bounds responseType "returned" [.record [("result", result)]]
  | .variant label _ => evaluation s!"plan not supported: {label}"
  | _ => evaluation "plan is not a variant"
end

/-- Lift `result` and `ticksUsed` of the receipt to the reply. -/
def turnReply (r : Json) : Json :=
  match r.getObjVal? "receipt" with
  | .error _ => r
  | .ok entry =>
    let extra := ["result", "ticksUsed"].filterMap fun k => (entry.getObjVal? k).toOption.map (k, ·)
    Json.mkObj ([("status", (r.getObjVal? "status").toOption.getD Json.null), ("receipt", entry)] ++ extra)

/-- Retry rule for turns: the identity is bound to the whole turn request. -/
def retainedTurn (w : World) (r : TurnRequest) : Option Json :=
  match w.receipts[identityKey r.principal r.intent]? with
  | none => none
  | some index =>
    let entry := w.entries[index]!
    if (entry.getObjValAs? String "turnRequest").toOption == some r.digest then some (turnReply (reply entry))
    else some (duplicate r.principal r.intent entry)

/-- One turn: drive the method, then one `commit`. Request errors (unknown method,
    wrong arity) journal nothing; every other end is a receipt. -/
def runTurn (w : World) (req : TurnRequest) : Except String (World × Json) := do
  if let some r := retainedTurn w req then return (w, r)
  let init : TurnState := { world := w, principal := req.principal, ticks := 1000000, limits := req.limits }
  let ticks ← match Delvetalk.Turn.budgets req.limits with
    | .ok b => pure b.ticks
    | .error e => throw e
  let (result, st) := (runMethod 0 req.object req.method req.argument "" |>.run).run { init with ticks }
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
