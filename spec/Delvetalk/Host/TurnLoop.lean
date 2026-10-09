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
import Delvetalk.Document

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
  let given := (j.getObjVal? "limits").toOption.getD (Json.mkObj [])
  let limits := if (given.getObjVal? "ticks").toOption.isSome then given
    else given.setObjVal! "ticks" (toJson (toString Limits.maxTurnTicks))
  if let .ok asked := (given.getObjVal? "ticks").bind natOf then
    if asked > Limits.maxTurnTicks then throw "ticks exceeds the turn ceiling"
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
  intent : String
  /-- Sends in order: target object, method, argument. They leave with the commit. -/
  sends : List (String × String × Data) := []
  programs : List (String × (String × String)) := []
  laws : List (String × String) := []
  ticks : Nat
  plans : Nat := 0
  /-- Rendered `offer` documents in order; the receipt carries them, the journal their count. -/
  offers : List String := []
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

/-- Make sure the turn's write set names `id` (a reprogram or amendment is a write). -/
def ensureWrite (id : String) : M Bool := do
  let s ← get
  if s.writes.any (·.1 == id) then return true
  if s.writes.length ≥ Limits.maxWrites then return false
  set { s with writes := s.writes ++ [(id, [])] }
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
    let binding := Delvetalk.Turn.Binding.make id s.principal s.intent (← get).roots
    let started ← liftEval (Delvetalk.Turn.startActivity compiled.packet arguments binding b)
    drive depth id compiled binding started 0
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

partial def drive (depth : Nat) (self : String) (compiled : Compiled) (binding : Delvetalk.Turn.Binding)
    (outcome : Delvetalk.Turn.Outcome) (_n : Nat) : M Data := do
  match outcome with
  | .finished value _ used => spend used; return value
  | .exhausted resource used =>
    spend used
    evaluation (if resource == "ticks" then "turn refused: tick budget exhausted"
      else s!"turn refused: {resource} budget exhausted")
  | .yielded plan _ responseType checkpoint used =>
    spend used
    countPlan
    let response ← answer depth self compiled.bounds plan responseType
    let b ← budgetsNow
    let next ← liftEval (Delvetalk.Turn.resumeActivity compiled.packet checkpoint binding response b)
    drive depth self compiled binding next 0

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
  | .variant "reprogram" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed reprogram plan"
    let some source := (f.lookup "package").bind labelOf | evaluation "malformed reprogram plan"
    let some migration := (f.lookup "migration").bind labelOf | evaluation "malformed reprogram plan"
    let some id := referenceId target | refusedWith bounds responseType "unreadWrite"
    let s ← get
    let some o := s.world.objects[id]? | refusedWith bounds responseType "unreadWrite"
    if !s.roots.any (·.1 == id) then refusedWith bounds responseType "unreadWrite"
    else if s.programs.any (·.1 == id) then refusedWith bounds responseType "duplicate"
    else match programFor s.world o source migration with
      | .error (clause, _) => refusedWith bounds responseType clause
      | .ok prog =>
        if !(← ensureWrite id) then refusedWith bounds responseType "writeCapacity"
        else
          modify fun s => { s with world := cacheProgram s.world o source migration prog,
                                   programs := s.programs ++ [(id, (source, migration))] }
          respond bounds responseType "reprogrammed" [.record [("pin", .label prog.pin)]]
  | .variant "amend" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed amend plan"
    let some text := (f.lookup "law").bind labelOf | evaluation "malformed amend plan"
    let some id := referenceId target | refusedWith bounds responseType "unreadWrite"
    let s ← get
    if !s.roots.any (·.1 == id) then refusedWith bounds responseType "unreadWrite"
    else if s.laws.any (·.1 == id) then refusedWith bounds responseType "duplicate"
    else match parseLawText text with
      | .error _ => refusedWith bounds responseType "law syntax"
      | .ok _ =>
        if !(← ensureWrite id) then refusedWith bounds responseType "writeCapacity"
        else
          modify fun s => { s with laws := s.laws ++ [(id, text)] }
          respond bounds responseType "amended" [emptyRecord]
  | .variant "send" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed send plan"
    let some method := (f.lookup "method").bind labelOf | evaluation "malformed send plan"
    let some argument := f.lookup "argument" | evaluation "malformed send plan"
    match referenceId target with
    | none => refusedWith bounds responseType "foreignWorld"
    | some id =>
      let s ← get
      if s.sends.length ≥ Limits.sendsPerTurn then evaluation "turn exceeds the send capacity"
      if s.world.pending.size + s.sends.length ≥ Limits.maxPending then
        evaluation "world exceeds the pending delivery capacity"
      let delivery := deliveryId s.principal s.intent s.sends.length
      set { s with sends := s.sends ++ [(id, method, argument)] }
      respond bounds responseType "delivery" [.record [("id", .label delivery)]]
  | .variant "offer" (.record f) =>
    let some document := f.lookup "document" | evaluation "malformed offer plan"
    let text ← liftEval (Delvetalk.Document.render document)
    let s ← get
    if s.offers.length ≥ Delvetalk.Document.maxOffersPerTurn
        || (s.offers.foldl (· + ·.utf8ByteSize) text.utf8ByteSize) > Delvetalk.Document.maxOutputBytes then
      evaluation "turn exceeds the offer capacity"
    set { s with offers := s.offers ++ [text] }
    respond bounds responseType "offered" [emptyRecord]
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

/-- What a turn knows about how it began: the ledger it runs under and, for a
    delivery, the id and the sender's identity. -/
structure TurnMeta where
  ledger : Option Ledger := none
  delivery : Option (String × Json) := none

def ledgerJson (l : Ledger) : Json := l.json

/-- The sends of an admitted turn, each with the ledger it inherits: depth - 1,
    work - the ticks this turn used, storage - the bytes its writes added. -/
def sendsJson (w : World) (principal intent : String) (ledger : Ledger) (used : Nat)
    (sends : List (String × String × Data)) (updates : List (String × Object)) : List (String × Json) :=
  if sends.isEmpty then [] else
  let added := updates.foldl (fun n (id, o) =>
    let before := ((w.objects[id]?).map fun p => (dataJson p.state).compress.utf8ByteSize).getD 0
    n + ((dataJson o.state).compress.utf8ByteSize - before)) 0
  let child : Ledger := ⟨ledger.depth - 1, ledger.work - used, ledger.storage - added⟩
  [("sends", Json.arr (sends.zipIdx.toArray.map fun ((to, method, argument), i) => Json.mkObj
    [("id", toJson (deliveryId principal intent i)), ("to", toJson to), ("method", toJson method),
     ("argument", dataJson argument), ("ledger", child.json)]))]

/-- One turn: drive the method, then one `commit`. Request errors (unknown method,
    wrong arity) journal nothing, except for a delivery, which must be consumed. -/
def runTurnWith (w : World) (req : TurnRequest) (how : TurnMeta) : Except String (World × Json) := do
  if let some r := retainedTurn w req then return (w, r)
  let ledger := how.ledger.getD ((w.objects[req.object]?).map (·.chain) |>.getD Ledger.start)
  let requested ← match Delvetalk.Turn.budgets req.limits with
    | .ok b => pure b.ticks
    | .error e => throw e
  let ticks := requested
  let init : TurnState := { world := w, principal := req.principal, intent := req.intent, ticks := 1000000, limits := req.limits }
  let (result, st) := (runMethod 0 req.object req.method req.argument "" |>.run).run { init with ticks }
  let w := { w with compiled := st.world.compiled, programs := st.world.programs }
  let used := ticks - st.ticks
  let proposal : Proposal := { principal := req.principal, intent := req.intent, roots := st.roots, writes := st.writes, turn := w.height + 1, programs := st.programs, laws := st.laws }
  let base := [("turnRequest", toJson req.digest), ("ticksUsed", toJson used), ("ledger", ledger.json)] ++
    (how.delivery.map fun (id, sender) => [("delivery", Json.mkObj [("id", toJson id), ("from", sender)])]).getD []
  let refuse := fun (reason : String) =>
    let cls := if st.roots.isEmpty && !w.objects.contains req.object then "unknownObject" else "evaluation"
    let (w', r) := commit w { proposal with writes := [] } base
      (some { cls, reason := some reason, object := if cls == "unknownObject" then some req.object else none })
    (w', turnReply r)
  match result with
  | .error (.request message) => if how.delivery.isSome then return refuse message else throw message
  | .error (.evaluation reason) => return refuse reason
  | .ok value =>
    let offered := if st.offers.isEmpty then [] else [("offers", toJson st.offers.length)]
    let (w', r) := commit w proposal (base ++ [("result", dataJson value)] ++ offered) none
      (sendsJson w req.principal req.intent ledger used st.sends)
    let reply := turnReply r
    -- The texts leave on the reply only; the journal keeps their count.
    return (w', if st.offers.isEmpty then reply else reply.setObjVal! "offers"
      (Json.arr (st.offers.toArray.map fun t => Json.mkObj [("principal", toJson req.principal), ("text", toJson t)])))

def runTurn (w : World) (req : TurnRequest) : Except String (World × Json) :=
  runTurnWith w req {}

/-- Run the oldest pending delivery as a turn of its sender's principal. -/
def deliverOne (w : World) (d : Json) : Except String (World × Json) := do
  let id ← d.getObjValAs? String "id"
  let principal ← d.getObjValAs? String "principal"
  let sender ← d.getObjVal? "from"
  let ledger ← ledgerOf (← d.getObjVal? "ledger")
  let how : TurnMeta := { ledger := some ledger, delivery := some (id, sender) }
  match ledger.exhausted with
  | some field =>
    let p : Proposal := { principal := principal, intent := id, roots := [], writes := [], turn := w.height + 1 }
    let (w', r) := commit w p
      [("ledger", ledger.json), ("delivery", Json.mkObj [("id", toJson id), ("from", sender)])]
      (some { cls := "budgetExhausted", reason := some field })
    return (w', r)
  | none =>
    let argument ← decodeData Limits.dataDepth (← d.getObjVal? "argument")
    let object ← d.getObjValAs? String "to"
    let method ← d.getObjValAs? String "method"
    let req : TurnRequest :=
      { principal := principal
        object := object
        method := method
        argument := argument
        intent := id
        limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))]
        digest := Journal.bodyHash d }
    runTurnWith w req how

/-- Up to `limit` deliveries, oldest first; sends of a delivery join the queue. -/
def deliver (w : World) (limit : Nat) : Except String (World × Json) := do
  let mut w := w
  let mut receipts : Array Json := #[]
  for _ in [0:min limit Limits.deliveriesPerCall] do
    let some d := w.pending[0]? | break
    let (w', r) ← deliverOne w d
    w := w'
    receipts := receipts.push r
  return (w, Json.mkObj [("status", toJson "delivered"), ("receipts", Json.arr receipts),
    ("pending", toJson w.pending.size)])

def pendingReply (w : World) : Json :=
  Json.mkObj [("status", toJson "pending"), ("count", toJson w.pending.size),
    ("ids", Json.arr ((w.pending.extract 0 Limits.maxHistoryLimit).map fun p =>
      (p.getObjVal? "id").toOption.getD Json.null))]

/-! ## Reprogramming and amending as ops -/

def withProgramRefusal (w : World) (p : Proposal) (clause message : String) : World × Json :=
  commit w p [] (some { cls := "programRefused", clause := some clause, reason := some message })

/-- `world-reprogram {principal, identity, object, version, package, migration?}`. -/
def reprogramOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let object ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let source ← j.getObjValAs? String "package"
  let migration := (j.getObjValAs? String "migration").toOption.getD ""
  let version ← natField j "version"
  let turn := ((j.getObjVal? "turn").toOption.bind (natOf · |>.toOption)).getD 0
  let p : Proposal :=
    { principal := principal
      intent := intent
      roots := [(object, version)]
      writes := []
      programs := [(object, (source, migration))]
      turn := turn }
  if let some r := retained w principal intent p.digest then return (w, r)
  match w.objects[object]? with
  | none => return commit w p
  | some o => match programFor w o source migration with
    | .error (clause, message) => return withProgramRefusal w p clause message
    | .ok prog => return commit (cacheProgram w o source migration prog) p

/-- `world-amend {principal, identity, object, version, law}`. -/
def amendOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let object ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let text ← j.getObjValAs? String "law"
  let version ← natField j "version"
  let turn := ((j.getObjVal? "turn").toOption.bind (natOf · |>.toOption)).getD 0
  let p : Proposal :=
    { principal := principal
      intent := intent
      roots := [(object, version)]
      writes := []
      laws := [(object, text)]
      turn := turn }
  if let some r := retained w principal intent p.digest then return (w, r)
  match parseLawText text with
  | .error message => return withProgramRefusal w p "law syntax" message
  | .ok _ => return commit w p

end Delvetalk.Host
