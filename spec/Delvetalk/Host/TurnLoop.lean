/- Driving an activity against the store. A turn reads committed state, collects
   the roots it viewed and the writes it performed, and ends in exactly one
   `commit`. The wire shapes are those of `world/lib/Plan.obend`:

   A method is `(state, [input,] context) -> Activity<Plan, Response, A>` or the
   same with a pure data result (the new state). `context` is
   `Abi.Context {world, object, principal, caller, intent, height, inputOrigin}`.
   Plans answered:
     view  {object: Reference}                     -> viewed {version, state} | denied {}
     write {object: Reference, edits: Edits}       -> written {} | refused {clause: notSelf}
       (a write changes only the running object; the Reference must name it)
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
  /-- A machine budget ran out (`ticks`, `heap`, `stack`, `nodes`, `bytes`): the named
      silence, journaled as class `budget` with the resource as its reason. -/
  | budget (resource : String)
  /-- The turn awaits a slot: its activity is checkpointed and journaled. -/
  | suspend (principal intent : String) (patience : Nat) (checkpoint : Delvetalk.Turn.Checkpoint)
      (interpretation : Option Json := none)
  deriving Inhabited

structure TurnState where
  world : World
  roots : List (String × Nat) := []
  writes : List (String × List Written) := []
  principal : String
  intent : String
  /-- Sends in order: target, method, argument and the sending object. They leave with the commit. -/
  sends : List (String × String × Data × String) := []
  programs : List (String × (String × String)) := []
  laws : List (String × String) := []
  ticks : Nat
  plans : Nat := 0
  /-- Rendered `offer` documents in order; the receipt carries them, the journal their count. -/
  offers : List String := []
  /-- Objects created, and objects the turn required absent (created ones included). -/
  creates : List (String × CreateRec) := []
  absent : List String := []
  /-- An object a `create` found already there: the turn will be refused naming it. -/
  violation : Option String := none
  /-- Slots this turn already awaited, as identity keys, and how many awaits it has made. -/
  awaited : List String := []
  awaits : Nat := 0
  /-- `check` Plans this turn ran; the journal keeps the count. -/
  checks : Nat := 0
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

/-- A `List<T>` value on the wire: `nil {} | cons {head, tail}`. -/
def listData (items : List Data) : Data :=
  items.foldr (fun x tail => .variant "cons" (.record [("head", x), ("tail", tail)]))
    (.variant "nil" (.record []))


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
    match resolveInputs s.world inputs >>= Package.compileKeepingLaws with
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

/-- Stage a write by the running object `id`, called by `caller`. The running object is
    always the first root of its own activity, so no earlier view is needed. -/
def addWrite (id caller : String) (step : Step) : M Unit := do
  let s ← get
  unless s.roots.any (·.1 == id) do evaluation "a write names an object that is not a root"
  if step.length > Limits.maxEditsPerWrite then evaluation "turn exceeds the edit capacity"
  let prior := (s.writes.lookup id).getD []
  if prior.length ≥ Limits.maxEditsPerWrite then evaluation "turn exceeds the edit capacity"
  let steps := prior ++ [(⟨caller, 0, step⟩ : Written)]
  if !s.writes.any (·.1 == id) && s.writes.length ≥ Limits.maxWrites then
    evaluation "turn exceeds the write capacity"
  let writes := if s.writes.any (·.1 == id) then
      s.writes.map fun (k, es) => if k == id then (k, steps) else (k, es)
    else s.writes ++ [(id, steps)]
  set { s with writes }

/-- Record that the running object `id`, called by `caller`, reprograms (kind 1) or
    amends (kind 2) itself. False when the write set is full. -/
def ensureWrite (id caller : String) (kind : Nat) : M Bool := do
  let s ← get
  if s.writes.any (·.1 == id) then
    set { s with writes := s.writes.map fun (k, ws) => if k == id then (k, ws ++ [(⟨caller, kind, []⟩ : Written)]) else (k, ws) }
    return true
  if s.writes.length ≥ Limits.maxWrites then return false
  set { s with writes := s.writes ++ [(id, [(⟨caller, kind, []⟩ : Written)])] }
  return true

/-- What the host tells a running method about itself, built here and nowhere else.
    `caller` is the calling object's id (empty for the turn's own method), `intent` the
    turn's identity, `height` the journal height the turn read. None is chosen by the client. -/
def contextData (id principal caller intent : String) (height : Nat) (kind command : String) : Data :=
  .record [("world", .label ""), ("object", .label id), ("principal", .label principal),
    ("caller", .label caller), ("intent", .label intent), ("height", .natural height),
    ("inputOrigin", .record [("kind", .label kind), ("object", .label caller), ("command", .label command),
      ("program", .label ""), ("immediatelyPrevious", .boolean false)])]

/-- The receipt a settled slot answers an await with. -/
def receiptData (entry : Json) : Data :=
  let identity := (entry.getObjVal? "identity").toOption.getD Json.null
  let text := fun (j : Json) (k : String) => ((j.getObjValAs? String k).toOption).getD ""
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let result : Data := match outcome.getObjValAs? String "tag" with
    | .ok "refused" => .variant "refused" (.record [("class", .label (text outcome "class")),
        ("root", .label (text outcome "object"))])
    | _ => .variant "admitted" (.record [])
  .record [("slot", .record [("principal", .label (text identity "principal")),
      ("intent", .label (text identity "intent"))]),
    ("height", .natural ((entry.getObjValAs? Nat "height").toOption.getD 0)), ("outcome", result)]

/-- The settled entry of an identity, if it has one (a suspension is not settled). -/
def settled (w : World) (principal intent : String) : Option Json :=
  match w.receipts[identityKey principal intent]? with
  | some i => let e := w.entries[i]!; if tagOf e == "suspended" then none else some e
  | none => none

/-- Compile an object's new sibling: `package` is a module of the creator's own sealed
    chain (a name), or the source of one more module over that chain. -/
def creationInputs (creator : Object) (package : String) : Except (String × String) Json := do
  if package.utf8ByteSize > Limits.maxPackageBytes then
    throw ("packageBytes", s!"package source exceeds {Limits.maxPackageBytes} bytes")
  let limits := (creator.inputs.getObjVal? "limits").toOption
  let finish := fun (fields : List (String × Json)) =>
    Json.mkObj (fields ++ [("entry", toJson "initial")] ++ (limits.map fun l => [("limits", l)]).getD [] ++
      ((creator.inputs.getObjVal? "library").toOption.map fun l => [("library", l)]).getD [])
  match creator.inputs.getObjVal? "modules" with
  | .ok (.arr modules) =>
    if package.startsWith "edition" then
      let named := modules.pop.push (Json.mkObj [("name", toJson "Created"), ("source", toJson package)])
      return finish [("modules", .arr named)]
    else
      match modules.findIdx? fun m => (m.getObjValAs? String "name").toOption == some package with
      | some i => return finish [("modules", .arr (modules.extract 0 (i + 1)))]
      | none => throw ("unknownPackage", s!"no module {package} in the creator's package")
  | _ =>
    if package.startsWith "edition" then return finish [("source", toJson package)]
    else throw ("unknownPackage", "the creator has no sealed modules to name")

/-- A seed is a whole state, or a record naming some fields of it (the rest come from
    `initial()`); a variant around the record is only a wrapper for the creator's types. -/
def mergeSeed (initial seed : Data) (bounds : DataBounds) (ty : Ty) : Except String Data := do
  let payload := match seed with
    | .variant _ p => p
    | d => d
  if payload.conformsUnder bounds ty then return payload
  match payload, initial with
  | .record given, .record base =>
    if given.any fun (k, _) => !base.any (·.1 == k) then throw "the seed names a field the state does not have"
    return .record (base.map fun (k, v) => (k, (given.lookup k).getD v))
  | _, _ => throw "the seed is not a record"

def buildCreated (w : World) (creator : Object) (package : String) (seed : Data) (lawArg principal : String)
    (height : Nat) : Except (String × String) CreateRec := do
  let inputs ← creationInputs creator package
  let built ← (compileObject w inputs).mapError (("compile", ·))
  let packet ← (built.artifact.getObjVal? "packet").mapError (("compile", ·))
  let initial ← match Package.executeDataValues packet #[] (Json.mkObj []) with
    | .ok (.finished v _ _ _) => pure v
    | _ => throw ("compile", "initial() did not evaluate")
  let state ← (mergeSeed initial seed built.assumptions.bounds built.ty).mapError (("typeMismatch", ·))
  let lawText := if lawArg.startsWith "law " then some lawArg else none
  let (object, sources) ← (makeObject built inputs state none none principal height lawText).mapError
    (fun e => (if e == noAmendmentClause then "law"
      else if e.endsWith "byte capacity" then "capacity" else "typeMismatch", e))
  return { object, sources, seed := dataJson state }

mutual
/-- Run `method` of object `id` against its committed state; its result is returned. -/
partial def runMethod (depth : Nat) (id method : String) (argument : Data) (caller : String) : M Data := do
  let s ← get
  let some obj := s.world.objects[id]? | evaluation s!"unknown object {id}"
  recordRoot id obj.version
  let compiled ← compiledMethod obj method
  let context := contextData id s.principal caller s.intent s.world.height
    (if depth == 0 then "request" else "call") method
  let (arguments, r) ← match compiled.type with
    | .arrow _ _ _ (.arrow _ _ _ (.arrow _ _ _ r)) => pure ([obj.state, argument, context], r)
    | .arrow _ _ _ (.arrow _ _ _ r) => pure ([obj.state, context], r)
    | _ => throw (.request s!"method {method} must take (state, [input,] context)")
  match r with
  | .computation .. =>
    let b ← budgetsNow
    let binding := Delvetalk.Turn.Binding.make id s.principal s.intent (← get).roots
    let started ← liftEval (Delvetalk.Turn.startActivity compiled.packet arguments binding b)
    drive depth id caller compiled binding started 0
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
      addWrite id caller (fields.map fun (k, v) => (⟨k, .set v⟩ : Edit))
      return value

partial def drive (depth : Nat) (self caller : String) (compiled : Compiled) (binding : Delvetalk.Turn.Binding)
    (outcome : Delvetalk.Turn.Outcome) (_n : Nat) : M Data := do
  match outcome with
  | .finished value _ used => spend used; return value
  | .exhausted resource used =>
    spend used
    throw (.budget resource)
  | .yielded plan _ responseType checkpoint used =>
    spend used
    countPlan
    let response ← match plan with
      | .variant "await" (.record f) => awaitPlan depth self compiled.bounds f responseType checkpoint
      | .variant "interpret" (.record f) => interpretPlan depth self compiled.bounds f responseType checkpoint
      | _ => answer depth self caller compiled.bounds plan responseType
    let b ← budgetsNow
    let next ← liftEval (Delvetalk.Turn.resumeActivity compiled.packet checkpoint binding response b)
    drive depth self caller compiled binding next 0

/-- `await {slot, patience}`: answered at once if the slot is settled or hopeless;
    otherwise the turn suspends (only at the top of a turn, never inside a call). -/
partial def awaitPlan (depth : Nat) (self : String) (bounds : DataBounds) (f : List (String × Data))
    (responseType : Ty) (checkpoint : Delvetalk.Turn.Checkpoint) : M Data := do
  let some (.record slot) := f.lookup "slot" | evaluation "malformed await plan"
  let some sp := (slot.lookup "principal").bind labelOf | evaluation "malformed await plan"
  let some si := (slot.lookup "intent").bind labelOf | evaluation "malformed await plan"
  let some (.natural patience) := f.lookup "patience" | evaluation "malformed await plan"
  let s ← get
  let key := identityKey sp si
  if (sp == s.principal && si == s.intent) || s.awaited.contains key then
    respond bounds responseType "broken" [emptyRecord]
  else if s.awaits ≥ Limits.awaitsPerTurn then evaluation "turn exceeds the await capacity"
  else
    set { s with awaited := s.awaited ++ [key], awaits := s.awaits + 1 }
    match settled s.world sp si with
    | some entry => respond bounds responseType "reply" [.record [("receipt", receiptData entry)]]
    | none =>
      if patience == 0 then respond bounds responseType "timedOut" [emptyRecord]
      else if patience > Limits.maxPatience then evaluation "await patience exceeds its capacity"
      else
        mayWait depth self checkpoint
        throw (.suspend sp si patience checkpoint)

/-- The capacities every suspension is held to; only the top of a turn may wait. -/
partial def mayWait (depth : Nat) (self : String) (checkpoint : Delvetalk.Turn.Checkpoint) : M Unit := do
  let s ← get
  if depth != 0 then evaluation "a wait inside a call is not supported"
  else if (s.world.suspended.filter fun e =>
      ((e.getObjVal? "outcome").toOption.bind (·.getObjVal? "activity" |>.toOption)
        |>.bind (·.getObjValAs? String "object" |>.toOption)) == some self).size
      ≥ Limits.pendingActivitiesPerObject then
    evaluation "pending activity capacity (pendingActivitiesPerObject) reached for the object"
  else if s.world.suspended.size ≥ Limits.maxSuspended then
    evaluation "pending activity capacity (maxSuspended) reached"
  else if (Delvetalk.Turn.tokensJson checkpoint.tokens).compress.utf8ByteSize > Limits.maxCheckpointBytes then
    evaluation "checkpoint exceeds its byte capacity"

/-- `interpret {utterance, offers, policy}`: the turn waits for a model's reply, which the
    transport fetches (`world-interpretations`) and settles (`world-interpretation`). The
    policy object must be readable by the turn's principal, else the Plan is answered `denied`. -/
partial def interpretPlan (depth : Nat) (self : String) (bounds : DataBounds) (f : List (String × Data))
    (responseType : Ty) (checkpoint : Delvetalk.Turn.Checkpoint) : M Data := do
  let some (.label utterance) := f.lookup "utterance" | evaluation "malformed interpret plan"
  let some offers := f.lookup "offers" | evaluation "malformed interpret plan"
  let some policy := (f.lookup "policy").bind referenceId | evaluation "malformed interpret plan"
  let s ← get
  match s.world.objects[policy]? with
  | none => respond bounds responseType "denied" [emptyRecord]
  | some o =>
    if !o.read.permits s.principal then respond bounds responseType "denied" [emptyRecord]
    else if utterance.utf8ByteSize > Limits.maxUtteranceBytes then evaluation "utterance exceeds its byte capacity"
    else if (dataJson offers).compress.utf8ByteSize > Limits.maxOffersBytes then
      evaluation "offers exceed their byte capacity"
    else if s.awaits ≥ Limits.awaitsPerTurn then evaluation "turn exceeds the await capacity"
    else
      mayWait depth self checkpoint
      let id := Journal.bodyHash (Json.arr #[toJson s.principal, toJson s.intent, toJson s.awaits])
      set { s with awaits := s.awaits + 1 }
      throw (.suspend interpretationPrincipal id Limits.interpretationPatience checkpoint
        (some (Json.mkObj [("id", toJson id), ("object", toJson self), ("policy", toJson policy),
          ("utterance", toJson utterance), ("offers", dataJson offers)])))

partial def answer (depth : Nat) (self caller : String) (bounds : DataBounds) (plan : Data) (responseType : Ty) : M Data := do
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
    -- A write changes the running object and nothing else; other objects change when called.
    match referenceId target with
    | some id =>
      if id != self then refusedWith bounds responseType "notSelf"
      else
        addWrite self caller step
        respond bounds responseType "written" [emptyRecord]
    | none => refusedWith bounds responseType "notSelf"
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
    let some id := referenceId target | refusedWith bounds responseType "notSelf"
    let s ← get
    let some o := s.world.objects[id]? | refusedWith bounds responseType "unknownObject"
    if id != self then refusedWith bounds responseType "notSelf"
    else if s.programs.any (·.1 == id) then refusedWith bounds responseType "duplicate"
    else match programFor s.world o source migration with
      | .error (clause, _) => refusedWith bounds responseType clause
      | .ok prog =>
        if !(← ensureWrite id caller 1) then refusedWith bounds responseType "capacity"
        else
          modify fun s => { s with world := cacheProgram s.world o source migration prog,
                                   programs := s.programs ++ [(id, (source, migration))] }
          respond bounds responseType "reprogrammed" [.record [("pin", .label prog.pin)]]
  | .variant "amend" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed amend plan"
    let some text := (f.lookup "law").bind labelOf | evaluation "malformed amend plan"
    let some id := referenceId target | refusedWith bounds responseType "notSelf"
    let s ← get
    if id != self then refusedWith bounds responseType "notSelf"
    else if s.laws.any (·.1 == id) then refusedWith bounds responseType "duplicate"
    else match parseLawText text with
      | .error _ => refusedWith bounds responseType "law syntax"
      | .ok _ =>
        if !(← ensureWrite id caller 2) then refusedWith bounds responseType "capacity"
        else
          modify fun s => { s with laws := s.laws ++ [(id, text)] }
          respond bounds responseType "amended" [emptyRecord]
  | .variant "inspect" (.record f) =>
    let s ← get
    match (f.lookup "object").bind referenceId >>= fun id => (s.world.objects[id]?) with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some o =>
      if !o.read.permits s.principal then respond bounds responseType "denied" [emptyRecord]
      else respond bounds responseType "inspected" [.record [("pin", .label o.pin),
        ("law", .label o.lawText), ("source", .label (entrySource o))]]
  | .variant "check" (.record f) =>
    let some (.label source) := f.lookup "package" | evaluation "malformed check plan"
    let s ← get
    if s.checks ≥ Limits.checksPerTurn then evaluation "turn exceeds the check capacity"
    set { s with checks := s.checks + 1 }
    respond bounds responseType "checked"
      [.record [("diagnostics", listData ((checkSource s.world source).map Data.label))]]
  | .variant "create" (.record f) =>
    let some package := (f.lookup "package").bind labelOf | evaluation "malformed create plan"
    let some seed := f.lookup "seed" | evaluation "malformed create plan"
    let lawArg := ((f.lookup "law").bind labelOf).getD ""
    let some target := f.lookup "requireAbsent" | evaluation "malformed create plan"
    let some id := referenceId target | refusedWith bounds responseType "foreignWorld"
    let s ← get
    let note := fun (s : TurnState) => { s with absent := if s.absent.contains id then s.absent else s.absent ++ [id] }
    if id.isEmpty || id == "self" || id.utf8ByteSize > Limits.maxObjectIdBytes then
      refusedWith bounds responseType "objectId"
    else if s.world.objects.contains id || s.creates.any (·.1 == id) then
      -- The reply says so now; the turn will be refused at its commit, naming the root.
      set { note s with violation := s.violation.orElse fun _ => some id }
      refusedWith bounds responseType "requiredAbsence"
    else if s.creates.length ≥ Limits.createsPerTurn || s.absent.length ≥ Limits.maxRoots then
      refusedWith bounds responseType "capacity"
    else
      let some creator := s.world.objects[self]? | evaluation "the creating object vanished"
      match buildCreated s.world creator package seed lawArg s.principal (s.world.height + 1) with
      | .error (clause, _) => refusedWith bounds responseType clause
      | .ok rec =>
        set { note s with creates := s.creates ++ [(id, rec)] }
        respond bounds responseType "created" [.record [("object", .record [("world", .label ""), ("object", .label id)])]]
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
      set { s with sends := s.sends ++ [(id, method, argument, self)] }
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

/-- Lift `result`, `ticksUsed` and, for a suspension, `slot` and `deadline` to the reply. -/
def turnReply (r : Json) : Json :=
  match r.getObjVal? "receipt" with
  | .error _ => r
  | .ok entry =>
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let extra := ["result", "ticksUsed"].filterMap (fun k => (entry.getObjVal? k).toOption.map (k, ·)) ++
      ["slot", "deadline"].filterMap (fun k => (outcome.getObjVal? k).toOption.map (k, ·))
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
  /-- The object whose send this turn delivers; the delivered method's `caller`. -/
  caller : String := ""
  ledger : Option Ledger := none
  delivery : Option (String × Json) := none

def ledgerJson (l : Ledger) : Json := l.json

/-- The sends of an admitted turn, each with the ledger it inherits: depth - 1,
    work - the ticks this turn used, storage - the bytes its writes added. -/
def sendsJson (w : World) (principal intent : String) (ledger : Ledger) (used : Nat)
    (sends : List (String × String × Data × String)) (updates : List (String × Object)) : List (String × Json) :=
  if sends.isEmpty then [] else
  let added := updates.foldl (fun n (id, o) =>
    let before := ((w.objects[id]?).map fun p => (dataJson p.state).compress.utf8ByteSize).getD 0
    n + ((dataJson o.state).compress.utf8ByteSize - before)) 0
  let child : Ledger := ⟨ledger.depth - 1, ledger.work - used, ledger.storage - added⟩
  [("sends", Json.arr (sends.zipIdx.toArray.map fun ((to, method, argument, sender), i) => Json.mkObj
    [("id", toJson (deliveryId principal intent i)), ("to", toJson to), ("method", toJson method),
     ("argument", dataJson argument), ("sender", toJson sender), ("ledger", child.json)]))]

/-- What a turn segment carries into its end: who it is, how it began, what it has spent. -/
structure Ctx where
  principal : String
  intent : String
  object : String
  method : String
  argument : Data
  /-- Digest of the original request; binds the identity for retries. -/
  digest : String
  ledger : Ledger
  delivery : Option (String × Json)
  /-- Hash of the suspension this segment continues. -/
  resumes : Option String := none
  usedBefore : Nat := 0
  ticksStart : Nat
  /-- The calling object of the activity's top method (empty for a direct turn). -/
  caller : String := ""


def sendJson (s : String × String × Data × String) : Json :=
  Json.mkObj [("to", toJson s.1), ("method", toJson s.2.1), ("argument", dataJson s.2.2.1), ("sender", toJson s.2.2.2)]

def entryBase (ctx : Ctx) (used : Nat) : List (String × Json) :=
  [("turnRequest", toJson ctx.digest), ("ticksUsed", toJson used), ("ledger", ctx.ledger.json)] ++
    (ctx.delivery.map fun (id, sender) => [("delivery", Json.mkObj [("id", toJson id), ("from", sender)])]).getD [] ++
    (ctx.resumes.map fun h => [("resumes", toJson h)]).getD []

/-- End a segment of a turn: commit it, refuse it, or journal its suspension. -/
def finishTurn (w : World) (ctx : Ctx) (result : Except Abort Data) (st : TurnState) :
    Except String (World × Json) := do
  let w := { w with compiled := st.world.compiled, programs := st.world.programs }
  let used := ctx.usedBefore + (ctx.ticksStart - st.ticks)
  let proposal : Proposal :=
    { principal := ctx.principal
      intent := ctx.intent
      roots := st.roots
      writes := st.writes
      turn := w.height + 1
      programs := st.programs
      laws := st.laws
      absent := st.absent
      creates := st.creates }
  let base := entryBase ctx used
  let refuse := fun (reason : String) =>
    let cls := if st.roots.isEmpty && !w.objects.contains ctx.object then "unknownObject" else "evaluation"
    let (w', r) := commit w { proposal with writes := [], creates := [] } base
      (some { cls, reason := some reason, object := if cls == "unknownObject" then some ctx.object else none })
    (w', turnReply r)
  match result with
  | .error (.request message) => if ctx.delivery.isSome || ctx.resumes.isSome then return refuse message else throw message
  | .error (.evaluation reason) => return refuse reason
  | .error (.budget resource) =>
    let (w', r) := commit w { proposal with writes := [], creates := [] } base
      (some { cls := "budget", reason := some resource })
    return (w', turnReply r)
  | .error (.suspend sp si patience checkpoint interpretation) =>
    let activity := Json.mkObj ([("object", toJson ctx.object), ("method", toJson ctx.method),
      ("argument", dataJson ctx.argument),
      ("checkpoint", checkpoint.toJson),
      ("roots", rootsJson st.roots), ("absent", toJson st.absent),
      ("writes", writesJson st.writes), ("sends", Json.arr (st.sends.toArray.map sendJson)),
      ("creates", Json.arr (st.creates.toArray.map fun (id, c) => createRecJson id c)),
      ("programs", Json.arr (st.programs.toArray.map fun (id, (src, mig)) => Json.mkObj
        [("object", toJson id), ("source", toJson src), ("migration", toJson mig)])),
      ("laws", Json.arr (st.laws.toArray.map fun (id, text) => Json.mkObj [("object", toJson id), ("law", toJson text)])),
      ("ticks", toJson st.ticks), ("awaited", toJson st.awaited), ("awaits", toJson st.awaits),
      ("offers", toJson st.offers), ("caller", toJson ctx.caller), ("checks", toJson st.checks)] ++
      (if st.violation.isSome then [("violation", toJson st.violation)] else []))
    let outcome := Json.mkObj <| [("tag", toJson "suspended"),
      ("slot", Json.mkObj [("principal", toJson sp), ("intent", toJson si)]),
      ("deadline", toJson (w.clock + patience)), ("activity", activity)] ++
      (interpretation.map fun i => [("interpretation", i)]).getD []
    let (w', entry) := push w (identityKey ctx.principal ctx.intent)
      ([("identity", identityJson ctx.principal ctx.intent), ("roots", rootsJson st.roots),
        ("turn", toJson proposal.turn), ("request", toJson ctx.digest)] ++ base ++ [("outcome", outcome)]) []
    return (w', turnReply (reply entry))
  | .ok value =>
    match st.violation with
    | some id =>
      let (w', r) := commit w { proposal with writes := [], creates := [] } base
        (some { cls := "requiredAbsence", object := some id })
      return (w', turnReply r)
    | none =>
    let offered := (if st.offers.isEmpty then [] else [("offers", toJson st.offers.length)]) ++
      (if st.checks == 0 then [] else [("checks", toJson st.checks)])
    let (w', r) := commit w proposal (base ++ [("result", dataJson value)] ++ offered) none
      (sendsJson w ctx.principal ctx.intent ctx.ledger used st.sends)
    let reply := turnReply r
    -- The texts leave on the reply only; the journal keeps their count.
    return (w', if st.offers.isEmpty then reply else reply.setObjVal! "offers"
      (Json.arr (st.offers.toArray.map fun t => Json.mkObj [("principal", toJson ctx.principal), ("text", toJson t)])))

/-- One turn: drive the method, then one `commit`. Request errors (unknown method,
    wrong arity) journal nothing, except for a delivery, which must be consumed. -/
def runTurnWith (w : World) (req : TurnRequest) (how : TurnMeta) : Except String (World × Json) := do
  if let some r := retainedTurn w req then return (w, r)
  let ledger := how.ledger.getD ((w.objects[req.object]?).map (·.chain) |>.getD Ledger.start)
  let ticks ← match Delvetalk.Turn.budgets req.limits with
    | .ok b => pure b.ticks
    | .error e => throw e
  let init : TurnState := { world := w, principal := req.principal, intent := req.intent, ticks, limits := req.limits }
  let (result, st) := (runMethod 0 req.object req.method req.argument how.caller |>.run).run init
  let ctx : Ctx :=
    { principal := req.principal
      intent := req.intent
      object := req.object
      method := req.method
      argument := req.argument
      digest := req.digest
      ledger := ledger
      delivery := how.delivery
      ticksStart := ticks
      caller := how.caller }
  finishTurn w ctx result st

def runTurn (w : World) (req : TurnRequest) : Except String (World × Json) :=
  runTurnWith w req {}

/-! ## Resuming suspended turns -/

inductive Resume where
  | reply (entry : Json)
  | timedOut

def computationParts : Ty → Option (Ty × Ty × Ty)
  | .arrow _ _ _ c => computationParts c
  | .computation p r a => some (p, r, a)
  | _ => none

def strings (j : Option Json) : List String :=
  ((j.bind (·.getArr?.toOption)).getD #[]).toList.filterMap fun a => a.getStr?.toOption

/-- The response an `interpreted` entry resumes its `interpret` Plan with. -/
def interpretedResponse (bounds : DataBounds) (responseType : Ty) (e : Json) : M Data := do
  let outcome := (e.getObjVal? "outcome").toOption.getD Json.null
  let verdict ← liftEval (outcome.getObjVal? "verdict")
  match ← liftEval (verdict.getObjValAs? String "tag") with
  | "proposal" =>
    let raw ← liftEval (verdict.getObjVal? "argument")
    let argument ← liftEval (decodeData Limits.dataDepth raw)
    let method ← liftEval (verdict.getObjValAs? String "method")
    respond bounds responseType "proposal" [.record [("method", .label method), ("argument", argument)]]
  | _ =>
    let needs := strings (verdict.getObjVal? "needs").toOption
    respond bounds responseType "unclear" [.record [("needs", listData (needs.map Data.label))]]

/-- Continue the activity a suspension entry journaled. The turn's roots are
    re-validated first: if anything it read or required absent has moved, the whole
    turn is refused `staleRoot` and journaled under its original identity. -/
def resumeOne (w : World) (sus : Json) (kind : Resume) : Except String (World × Json) := do
  let hash ← sus.getObjValAs? String "hash"
  let identity ← sus.getObjVal? "identity"
  let principal ← identity.getObjValAs? String "principal"
  let intent ← identity.getObjValAs? String "intent"
  let outcome ← sus.getObjVal? "outcome"
  let act ← outcome.getObjVal? "activity"
  let object ← act.getObjValAs? String "object"
  let method ← act.getObjValAs? String "method"
  let argument ← decodeData Limits.dataDepth (← act.getObjVal? "argument")
  let roots ← parseRoots (← act.getObjVal? "roots")
  let absent := strings (act.getObjVal? "absent").toOption
  let ticks ← natField act "ticks"
  let ledger ← ledgerOf (← sus.getObjVal? "ledger")
  let delivery ← match sus.getObjVal? "delivery" with
    | .ok d => pure (some (← d.getObjValAs? String "id", ← d.getObjVal? "from"))
    | .error _ => pure none
  let ctx : Ctx :=
    { principal := principal
      intent := intent
      object := object
      method := method
      argument := argument
      digest := ← sus.getObjValAs? String "turnRequest"
      ledger := ledger
      delivery := delivery
      resumes := some hash
      usedBefore := ← natField sus "ticksUsed"
      ticksStart := ticks
      caller := (act.getObjValAs? String "caller").toOption.getD "" }
  let stale? := (roots.find? fun (id, v) => (w.objects[id]?).map (·.version) != some v).map (·.1)
    <|> absent.find? fun id => w.objects.contains id
  if let some id := stale? then
    let stalled : Proposal :=
      { principal := principal
        intent := intent
        roots := roots
        writes := []
        turn := w.height + 1
        absent := absent }
    let (w', r) := commit w stalled (entryBase ctx ctx.usedBefore) (some { cls := "staleRoot", object := some id })
    return (w', turnReply r)
  let writes ← parseRecordedWrites (← act.getObjVal? "writes")
  let sends ← ((← (← act.getObjVal? "sends").getArr?).toList.mapM fun s => do
    return (← s.getObjValAs? String "to", ← s.getObjValAs? String "method",
      ← decodeData Limits.dataDepth (← s.getObjVal? "argument"), ← s.getObjValAs? String "sender"))
  let creates ← ((← (← act.getObjVal? "creates").getArr?).toList.mapM fun r => do
    let id ← r.getObjValAs? String "object"
    let seed ← r.getObjVal? "seed"
    let (o, sources) ← buildObject w (← r.getObjVal? "compile") seed (r.getObjVal? "read").toOption
      (r.getObjVal? "chain").toOption principal (w.height + 1) (some (← r.getObjValAs? String "law"))
    return (id, ({ object := o, sources, seed } : CreateRec)))
  let programs ← ((← (← act.getObjVal? "programs").getArr?).toList.mapM fun r => do
    return (← r.getObjValAs? String "object", (← r.getObjValAs? String "source", ← r.getObjValAs? String "migration")))
  let laws ← ((← (← act.getObjVal? "laws").getArr?).toList.mapM fun r => do
    return (← r.getObjValAs? String "object", ← r.getObjValAs? String "law"))
  let checkpoint ← Delvetalk.Turn.Checkpoint.fromJson (← act.getObjVal? "checkpoint")
  let init : TurnState :=
    { world := w
      roots := roots
      writes := writes
      principal := principal
      intent := intent
      sends := sends
      programs := programs
      laws := laws
      ticks := ticks
      offers := strings (act.getObjVal? "offers").toOption
      creates := creates
      absent := absent
      violation := (act.getObjValAs? String "violation").toOption
      awaited := strings (act.getObjVal? "awaited").toOption
      awaits := ← natField act "awaits"
      checks := (natField act "checks").toOption.getD 0
      limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))] }
  let action : M Data := do
    let s ← get
    let some obj := s.world.objects[object]? | evaluation s!"unknown object {object}"
    let compiled ← compiledMethod obj method
    let some (_, responseType, _) := computationParts compiled.type | evaluation "the method is not an activity"
    let response ← match kind with
      | .reply e =>
        if tagOf e == "interpreted" then interpretedResponse compiled.bounds responseType e
        else respond compiled.bounds responseType "reply" [.record [("receipt", receiptData e)]]
      | .timedOut => respond compiled.bounds responseType "timedOut" [emptyRecord]
    -- The activity began with only its own object as a root, at the version still current.
    let binding := Delvetalk.Turn.Binding.make object principal intent
      (roots.filter (·.1 == object))
    let b ← budgetsNow
    let next ← liftEval (Delvetalk.Turn.resumeActivity compiled.packet checkpoint binding response b)
    drive 0 object ctx.caller compiled binding next 0
  let (result, st) := action.run.run init
  finishTurn w ctx result st

/-- The first suspended activity that can go on: its slot settled, or its deadline passed. -/
def pickResumable (w : World) : Option (Json × Resume) :=
  w.suspended.findSome? fun s =>
    let outcome := (s.getObjVal? "outcome").toOption.getD Json.null
    let slot := (outcome.getObjVal? "slot").toOption.getD Json.null
    match (slot.getObjValAs? String "principal").toOption, (slot.getObjValAs? String "intent").toOption,
        (outcome.getObjValAs? Nat "deadline").toOption with
    | some sp, some si, some deadline =>
      match settled w sp si with
      | some e => some (s, .reply e)
      | none => if w.clock > deadline then some (s, .timedOut) else none
    | _, _, _ => none

/-- Resume everything that can be resumed, oldest first; resumed turns may settle
    other slots, which the next pass picks up. -/
def settle (w : World) : Except String (World × Array Json) := do
  let mut w := w
  let mut out : Array Json := #[]
  for _ in [0:Limits.maxResumesPerCall] do
    let some (s, kind) := pickResumable w | break
    let (w', r) ← resumeOne w s kind
    w := w'
    out := out.push r
  return (w, out)

/-- Run the oldest pending delivery as a turn of its sender's principal. -/
def deliverOne (w : World) (d : Json) : Except String (World × Json) := do
  let id ← d.getObjValAs? String "id"
  let principal ← d.getObjValAs? String "principal"
  let sender ← d.getObjVal? "from"
  let ledger ← ledgerOf (← d.getObjVal? "ledger")
  let how : TurnMeta :=
    { caller := (d.getObjValAs? String "sender").toOption.getD ""
      ledger := some ledger
      delivery := some (id, sender) }
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
  if (j.getObjVal? "turn").toOption.isSome then throw "turn is assigned by the host and cannot be supplied"
  let p : Proposal :=
    { principal := principal
      intent := intent
      roots := [(object, version)]
      writes := []
      programs := [(object, (source, migration))] }
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
  if (j.getObjVal? "turn").toOption.isSome then throw "turn is assigned by the host and cannot be supplied"
  let p : Proposal :=
    { principal := principal
      intent := intent
      roots := [(object, version)]
      writes := []
      laws := [(object, text)] }
  if let some r := retained w principal intent p.digest then return (w, r)
  match parseLawText text with
  | .error message => return withProgramRefusal w p "law syntax" message
  | .ok _ => return commit w p


/-! ## Reflection and interpretation as ops -/

/-- `world-inspect {principal, object}`: the pin, law text and entry source an object
    shows a reader its read policy permits. -/
def inspectOp (w : World) (j : Json) : Except String Json := do
  let id ← j.getObjValAs? String "object"
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  match w.objects[id]? with
  | none => return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  | some o =>
    if !o.read.permits principal then
      return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
    return Json.mkObj [("status", toJson "inspected"), ("object", toJson id), ("pin", toJson o.pin),
      ("law", toJson o.lawText), ("source", toJson (entrySource o))]

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

/-- The state of a Policy object as `{model, system, examples}` (absent fields are null). -/
def policyJson (w : World) (id : String) : Json :=
  match (w.objects[id]?).map (fun o => o.state) with
  | some (Data.record f) => Json.mkObj (["model", "system", "examples"].map fun k =>
      (k, ((f.lookup k).map plainJson).getD Json.null))
  | _ => Json.null

def interpretationOf (s : Json) : Option Json :=
  (s.getObjVal? "outcome").toOption.bind fun o => (o.getObjVal? "interpretation").toOption

/-- `world-interpretations`: every `interpret` still waiting for a reply. -/
def interpretationsReply (w : World) : Json :=
  let pending := w.suspended.filterMap fun s => do
    let i ← interpretationOf s
    let id ← (i.getObjValAs? String "id").toOption
    guard (settled w interpretationPrincipal id).isNone
    let deadline ← ((s.getObjVal? "outcome").toOption.bind (·.getObjValAs? Nat "deadline" |>.toOption))
    guard (w.clock ≤ deadline)
    let object ← (i.getObjValAs? String "object").toOption
    let policy ← (i.getObjValAs? String "policy").toOption
    let offers ← (i.getObjVal? "offers").toOption.bind fun o => (decodeData Limits.dataDepth o).toOption
    let utterance ← (i.getObjValAs? String "utterance").toOption
    pure (Json.mkObj [("id", toJson id), ("object", toJson object), ("policy", policyJson w policy),
      ("utterance", toJson utterance), ("offers", plainJson offers)])
  Json.mkObj [("status", toJson "interpretations"), ("pending", Json.arr pending)]

def scratchState (w : World) : TurnState :=
  { world := w, principal := "", intent := "", ticks := 0, limits := Json.mkObj [] }

def abortText : Abort → String
  | .request m | .evaluation m => m
  | .budget r => s!"{r} budget exhausted"
  | .suspend .. => "unexpected suspension"

/-- The input type of a method: `none` when it takes none, an error when it is not a method. -/
def inputTypeOf : Ty → Except String (Option Ty)
  | .arrow _ _ _ (.arrow _ _ dom (.arrow _ _ _ _)) => pure (some dom)
  | .arrow _ _ _ (.arrow _ _ _ _) => pure none
  | _ => throw "not a method"

def unclearVerdict (needs : List String) : Json :=
  Json.mkObj [("tag", toJson "unclear"), ("needs", toJson needs)]

/-- What a reply says to the suspended object: a proposal (a method of the object, one of
    the offered actions, with an argument that conforms to the method's input type and
    fits the object's response type), or `unclear` with the reason. -/
def interpretVerdict (w : World) (s : Json) (reply : Json) : Except String (World × Json) := do
  let some i := interpretationOf s | throw "not an interpretation"
  let act ← (← s.getObjVal? "outcome").getObjVal? "activity"
  let object ← act.getObjValAs? String "object"
  let suspendedMethod ← act.getObjValAs? String "method"
  match (reply.getObjValAs? String "status").toOption with
  | some "replied" => pure ()
  | some "failed" =>
    let reason := ((reply.getObjValAs? String "reason").toOption).getD "failed"
    return (w, unclearVerdict [s!"the model did not reply: {reason}"])
  | _ => throw "reply must have status replied or failed"
  let some json := (reply.getObjVal? "json").toOption | throw "a replied interpretation carries json"
  let some method := (json.getObjValAs? String "method").toOption
    | return (w, unclearVerdict ["the reply names no method"])
  let offers ← decodeData Limits.dataDepth (← i.getObjVal? "offers")
  let actions := ((listHeads [] offers).getD []).filterMap fun form =>
    match form with
    | .record f => (f.lookup "action").bind labelOf
    | _ => none
  if !actions.isEmpty && !actions.contains method then
    return (w, unclearVerdict [s!"{method} is not one of the offered actions"])
  let some obj := w.objects[object]? | throw s!"unknown object {object}"
  let (r, st) := ((compiledMethod obj method).run.run (scratchState w))
  let (r2, st2) := ((compiledMethod obj suspendedMethod).run.run st)
  let suspended ← match r2 with | .ok c => pure c | .error e => throw (abortText e)
  let some (_, responseType, _) := computationParts suspended.type | throw "the suspended method is not an activity"
  let w := { w with compiled := st2.world.compiled }
  let compiledM ← match r with
    | .ok c => pure c
    | .error e => return (w, unclearVerdict [s!"{method} is not a method of the object: {abortText e}"])
  let raw := (json.getObjVal? "argument").toOption.getD (Json.mkObj [])
  let input ← (inputTypeOf compiledM.type).mapError fun _ => s!"{method} is not a method"
  let wanted := match raw with
    | .null => Json.mkObj []
    | other => other
  match Package.jsonData Limits.plainDepth wanted with
  | .error e => return (w, unclearVerdict [s!"the argument is not plain data: {e}"])
  | .ok (argument, _) =>
    let fits := match input with
      | some dom => argument.conformsUnder compiledM.bounds dom
      | none => match argument with | .record [] => true | _ => false
    if !fits then return (w, unclearVerdict [s!"the argument does not fit the input of {method}"])
    let candidate := Data.variant "proposal" (.record [("method", .label method), ("argument", argument)])
    if !candidate.conformsUnder suspended.bounds responseType then
      return (w, unclearVerdict [s!"the object cannot carry a proposal of {method}"])
    return (w, Json.mkObj [("tag", toJson "proposal"), ("method", toJson method),
      ("argument", dataJson argument)])

/-- `world-interpretation {id, reply}`: settle a pending interpretation with the model's
    reply, verbatim. The verdict is journaled; the suspended turn resumes with it. -/
def interpretationOp (w : World) (j : Json) : Except String (World × Json) := do
  let id ← boundedText "interpretation id" Limits.maxIntentBytes (← j.getObjValAs? String "id")
  let replied ← j.getObjVal? "reply"
  if replied.compress.utf8ByteSize > Limits.maxReplyBytes then throw "reply exceeds its byte capacity"
  let digest := Journal.bodyHash replied
  if let some r := retained w interpretationPrincipal id digest then return (w, r)
  let some s := w.suspended.find? fun s => (interpretationOf s).bind (·.getObjValAs? String "id" |>.toOption) == some id
    | throw s!"no pending interpretation {id}"
  let (w, verdict) ← interpretVerdict w s replied
  let (w', entry) := push w (identityKey interpretationPrincipal id)
    [("identity", identityJson interpretationPrincipal id), ("roots", rootsJson []),
     ("turn", toJson (w.height + 1)), ("request", toJson digest),
     ("outcome", Json.mkObj [("tag", toJson "interpreted"), ("id", toJson id), ("reply", replied),
       ("verdict", verdict)])] []
  return (w', reply entry)

end Delvetalk.Host
