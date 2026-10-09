/- Local durable host fixture profile. Distinct from the Objective Bend kernel.
   Lean owns protocol evaluation, exact roots, current authority and receipts.
   Python owns only locking, process transport and atomic file replacement. -/
import Lean
import EvaluationState
import Theory.ObjectiveBendDemandData
import Theory.ObjectiveBendTyping
open Lean
private def Option.toExcept (o : Option α) (error : String) : Except String α :=
  match o with
  | some v => .ok v
  | none => .error error
namespace World

def obj (xs : List (String × Json)) : Json := Json.mkObj xs
def field (j : Json) (k : String) : Except String Json := j.getObjVal? k
def str (j : Json) (k : String) : Except String String := (field j k).bind Json.getStr?
def pairs (j : Json) : Except String (List (String × Json)) := do
  let o ← j.getObj?
  return o.toList

def put (j : Json) (k : String) (v : Json) : Except String Json := do
  return .obj ((← j.getObj?).insert k v)

def empty : Json := obj [("objects", obj []), ("receipts", .arr #[])]


def noInputOrigin : Json := obj [
  ("kind", .str "none"), ("object", .str ""), ("command", .str ""), ("program", .str ""),
  ("immediatelyPrevious", .bool false)]

-- Acquisition is separate from effect authority. Missing read policy preserves
-- the public commons; an explicit empty grant has no creator/manager bypass.
-- The caller is supplied by authenticated transport, never by source code.
def readObject (objects : Json) (id : String) (principal : String) : Except String Json := do
  if principal.isEmpty then throw "read requires principal"
  let root ← field objects id
  let authority ← field root "law"
  match (field authority "read").toOption with
  | none => return root
  | some (.str "public") => return root
  | some grant =>
    let principals ← (← grant.getArr?).mapM Json.getStr?
    if !principals.contains principal then throw "object read unauthorized"
    return root

-- Recheck acquisition of already captured data without retransmitting roots.
-- This verdict is only for this query; it is not a reusable grant/token.
def authorizeReads (world request : Json) : Except String Json := do
  let keys := (← pairs request).map Prod.fst
  if keys.length != 3 || !["op", "principal", "objects"].all keys.contains then
    throw "authorize-reads requires exact fields"
  let principal ← str request "principal"
  let ids ← (← (← field request "objects").getArr?).mapM Json.getStr?
  if ids.isEmpty || ids.size > 17 then throw "read authorization object capacity"
  let objects ← field world "objects"
  for id in ids do discard (readObject objects id principal)
  return obj [("authorized", .bool true)]

-- Current metadata only: neither retained history nor complete roots cross this
-- boundary. A continuation binds the exact custody revision, including refusals.
def cataloguePage (world request : Json) (sequence : Nat) (head : Json) : Except String Json := do
  let entries ← pairs request
  if entries.length != 4 || !(entries.all (fun item => ["op", "principal", "limit", "cursor"].contains item.1)) then
    throw "catalogue requires exactly op, principal, limit and cursor"
  let principal ← str request "principal"
  if principal.isEmpty then throw "catalogue requires principal"
  let limit ← (← field request "limit").getNat?
  if limit == 0 || limit > 64 then throw "catalogue page capacity"
  let cursor ← field request "cursor"
  let after ← if cursor == .null then pure none else do
    let fields ← pairs cursor
    if fields.length != 3 || !(fields.all (fun item => ["after", "sequence", "head"].contains item.1)) then
      throw "invalid catalogue cursor"
    if (← field cursor "sequence") != toJson sequence || (← field cursor "head") != head then
      throw "stale catalogue cursor"
    pure (some (← str cursor "after"))
  let objects ← field world "objects"
  let mut rows : Array Json := #[]
  let mut last : Option String := none
  let mut more := false
  let mut bytes := 0
  for (id, _) in (← pairs objects) do
    if after.any (fun previous => compare id previous != .gt) then continue
    let root ← match readObject objects id principal with
      | .ok root => pure root
      | .error _ => continue
    let name := ((field root "protocol" >>= fun protocol => str protocol "name").toOption).getD id
    let preview := (name.take 256).toString
    let row := obj [("object", .str id), ("version", ← field root "version"),
      ("name", .str preview), ("nameTruncated", .bool (preview != name))]
    let size := row.compress.utf8ByteSize
    -- Reserve the continuation even if this turns out to be the final row.
    -- Object identities are exact and may be large; the cursor repeats one.
    let continuation := obj [("after", .str id), ("sequence", toJson sequence), ("head", head)]
    if rows.size == limit || bytes + size + continuation.compress.utf8ByteSize + 1024 > 60 * 1024 then
      if rows.isEmpty then throw "catalogue identity response capacity"
      more := true
      break
    rows := rows.push row
    bytes := bytes + size
    last := some id
  let next := if more then obj [("after", .str (last.getD "")),
    ("sequence", toJson sequence), ("head", head)] else .null
  let response := obj [("objects", .arr rows), ("nextCursor", next),
    ("sequence", toJson sequence), ("head", head)]
  if response.compress.utf8ByteSize > 64 * 1024 then throw "catalogue response capacity"
  return response

-- A history row is one indivisible admission, not a replayable redaction. Every
-- native-bound peer whose root/evidence it may disclose must be readable now.
def eventObjects (world reference : Json) : Except String (List String) := do
  let messages ← field world "messages"
  let retained ← field (← field messages "events") (← str reference "id")
  let evidence ← field retained "evidence"
  return [← str evidence "source", ← str evidence "to"]

def admissionObjects (world entry : Json) : Except String (List String) := do
  let request ← field entry "request"
  let mut ids : List String := []
  if let some id := (str request "object").toOption then ids := id :: ids
  if let some reads := (field request "reads").toOption then
    ids := ids ++ (← pairs reads).map Prod.fst
  if let some absent := (field request "absent").toOption then
    ids := ids ++ (← absent.getArr?).toList.filterMap (fun value => value.getStr?.toOption)
  if let some data := (field entry "receipt" >>= fun receipt => field receipt "data").toOption then
    for key in ["roots", "allocated"] do
      if let some roots := (field data key).toOption then ids := ids ++ (← pairs roots).map Prod.fst
    if let some messages := (field data "messages").toOption then
      for reference in (← messages.getArr?) do ids := ids ++ (← eventObjects world reference)
  if ["deliver", "settle-message"].contains ((str request "op").toOption.getD "") then
    ids := ids ++ (← eventObjects world (← field request "event"))
  return ids.eraseDups

def readableAdmission (world entry : Json) (principal : String) : Except String Unit := do
  let objects ← field world "objects"
  for id in (← admissionObjects world entry) do
    -- An absent allocation guard carries no existing object contents.
    if (field objects id).isOk then discard (readObject objects id principal)

def historyPageIndexed (world request : Json) (count : Nat)
    (lookup : Nat → Option Json) : Except String Json := do
  let keys := (← pairs request).map Prod.fst
  let expected := ["op", "principal", "object", "before", "offset", "limit"]
  if keys.length != expected.length || !expected.all keys.contains then
    throw "object-history requires exact fields"
  let principal ← str request "principal"
  let id ← str request "object"
  discard (readObject (← field world "objects") id principal)
  let before ← (← field request "before").getNat?
  let offset ← (← field request "offset").getNat?
  let limit ← (← field request "limit").getNat?
  if before > count || offset > before || limit == 0 || limit > 32 then
    throw "object-history bounds"
  let stop := min before (offset + 256)
  let mut next := offset
  let mut rows : Array Json := #[]
  let mut bytes := 0
  let mut scanned := 0
  for index in [offset:stop] do
    scanned := scanned + 1
    let some entry := lookup index | throw "object-history index missing admission"
    let ids ← match admissionObjects world entry with
      | .ok ids => pure ids
      | .error _ =>
        next := index + 1
        continue
    if !ids.contains id || !(readableAdmission world entry principal).isOk then
      next := index + 1
      continue
    let size := entry.compress.utf8ByteSize
    -- Oversized admissions require explicit custodian export, never a partial row.
    if size > 60 * 1024 then
      next := index + 1
      continue
    if rows.size == limit || bytes + size > 60 * 1024 then break
    rows := rows.push entry
    bytes := bytes + size
    next := index + 1
  return obj [("history", .arr rows), ("before", toJson before), ("scanned", toJson scanned),
    ("nextOffset", if next < before then toJson next else .null)]

-- File custody already holds its exported admission array. Resident custody
-- supplies indexed lookups instead, without materializing the complete history.
def historyPage (world request : Json) (receipts : Array Json) : Except String Json :=
  historyPageIndexed world request receipts.size (fun index => receipts[index]?)

-- Host-bound identity for one actual receiving call, separate from user data.
structure CallContext where
  object : String
  protocol : Json := obj []
  inputOrigin : Json := noInputOrigin
  eventFacts : Option Json := none
  physicalInput : Option Json := none

-- Evidence originates in the actual checked producer, never display decoding.
structure NativeResult where
  value : Minidregg.Theory.ObjectiveBendDemandData.Data
  assumptions : Minidregg.Theory.ObjectiveBendTyping.Assumptions
  type : Minidregg.Theory.ObjectiveBendTypes.Ty

-- Allocation configuration retains checked source type evidence until child admission.
structure Allocation where
  descriptor : Json
  initial : Option NativeResult := none

-- The source result stays native until all dependent calls have consumed it.
-- Presentation JSON is receipt/display data, never typed provenance.
structure TransitionResult where
  state : Json
  result : Json
  nativeResult : Option NativeResult := none
  emissions : Array Json := #[]
  allocations : Array Allocation := #[]

-- Executable-selected extensions; requests and protocols cannot choose a budget.
structure Runtime where
  budget : Nat := 10000
  -- Native framing is decoded before guards/body; receipts retain physical input.
  prepareInvocation : Json → Json → Option NativeResult → Evaluation Json := fun _ request _ => pure request
  frameDerivedInput : Json → String → NativeResult → Evaluation Json :=
    fun _ _ _ => throw "typed derived input requires source runtime"
  initializeAllocation : Json → NativeResult → Evaluation Json :=
    fun _ _ => throw "typed allocation initial requires source runtime"
  recodeState : Json → Json → Json → Evaluation Json := fun _ _ state => pure state
  canonicalState : Json → Evaluation Json := fun root => field root "state"
  validateTransition : Json → Json → Evaluation Unit :=
    fun _ _ => throw "source transitions require compiled profile"
  executeTransition : CallContext → Json → Json → String → Json → Evaluation TransitionResult :=
    fun _ _ _ _ _ => throw "source transitions require compiled profile"
  programIdentity : Json → Evaluation String :=
    fun _ => throw "program identity requires compiled profile"
  reprogramResult : String → Json → Evaluation Json := fun _ _ => pure .null
  checkSourceContract : Json → Json → Bool → Evaluation Unit :=
    fun _ _ _ => throw "source contracts require compiled profile"
  checkSourceAmendment : Json → Json → Json → Json → String → Evaluation Unit :=
    fun _ _ _ _ _ => throw "source amendments require compiled profile"
  checkSourcePolicy : Json → Json → Evaluation Unit :=
    fun _ _ => throw "source policies require compiled profile"
  -- Admission-owned effects are staged under the same budget and rollback as
  -- the source invocation. The default preserves ordinary inert outboxes.
  stageMessages : Json → Json → Json → Json → Nat → Nat → Array Json →
      Evaluation (Json × Array Json × Array Json) :=
    fun world _ _ _ _ _ emitted => pure (world, #[], emitted)

def tick : Evaluation Unit := do
  let remaining ← get
  if remaining == 0 then throw "invocation budget exhausted"
  set (remaining - 1)

-- An opt-in factory has a current direct-child quota, governed by reprogramming.
def allocationLimit (protocol : Json) : Except String (Option Nat) := do
  match (field protocol "allocation").toOption with
  | none => return none
  | some allocation =>
    for (key, _) in (← pairs allocation) do
      if key != "limit" then throw "unsupported allocation policy field"
    return some (← (← field allocation "limit").getNat?)

-- Every command selects the one current source transition boundary.
def sourceTransition? (command : Json) : Option Json := do
  let transition ← (field command "transition").toOption
  if (str transition "profile").toOption == some "delvetalk-source-transition" then
    some transition
  else none

def validateTransitionCommand (command : Json) : Except String Unit := do
  if (← pairs command).map Prod.fst != ["transition"] then
    throw "source command requires exactly transition"

/-- The same structural scanner serves pure protocol inspection and receiving
validation. Only receiving supplies a checked compiler under its existing turn. -/
def validateProtocolUsing {m : Type → Type} [Monad m] [MonadExceptOf String m]
    [MonadLiftT (Except String) m] (validate : Json → Json → m Unit) (p : Json) : m Unit := do
  if (← str p "profile") != "delvetalk-local-v1" then throw "unknown profile"
  discard (pairs (← field p "initial"))
  discard (allocationLimit p)
  for (_, command) in (← pairs (← field p "commands")) do
    validateTransitionCommand command
    let some transition := sourceTransition? command | throw "source command requires current transition"
    validate p transition

def validateProtocolWith (runtime : Runtime) (protocol : Json) : Evaluation Unit :=
  validateProtocolUsing runtime.validateTransition protocol

/-- Pure boundary validation keeps the default host's source refusal. It does
not start an evaluation run or manufacture fresh fuel inside a receiving turn. -/
def validateProtocol (protocol : Json) : Except String Unit :=
  validateProtocolUsing (fun _ _ => throw "source transitions require compiled profile") protocol

def law (j : Json) : Except String (Array String) := do
  let xs ← j.getArr?
  xs.mapM Json.getStr?

def validateLaw (j : Json) : Except String Unit := do
  if (str j "profile").toOption != some "delvetalk-scoped-law" then
    throw "unknown law profile"
  for (key, _) in (← pairs j) do
    unless ["profile", "invoke", "reprogram", "law", "predicate", "invariant",
        "contract", "amendment", "read"].contains key do
      throw "unsupported scoped law field"
  for (_, principals) in (← pairs (← field j "invoke")) do discard (law principals)
  discard (law (← field j "reprogram"))
  discard (law (← field j "law"))
  for key in ["predicate", "invariant"] do
    if let some term := (field j key).toOption then
      let keys := (← pairs term).map Prod.fst
      unless keys.length == 2 && keys.all ["package", "config"].contains do
        throw "source policy requires exactly package and config"
      let keys := (← pairs (← field term "package")).map Prod.fst
      unless keys.length == 2 && keys.all ["modules", "entry"].contains do
        throw "source policy requires standalone modules and entry"
  for key in ["contract", "amendment"] do
    if let some descriptor := (field j key).toOption then discard (pairs descriptor)
  if let some reading := (field j "read").toOption then
    if reading != .str "public" then discard (law reading)

def prepareInvocation (runtime : Runtime) (o request : Json)
    (nativeInput : Option NativeResult := none) : Evaluation Json := do
  if (← str request "op") != "invoke" then return request
  let prepared ← runtime.prepareInvocation o request nativeInput
  if (← put prepared "input" (← field request "input")) != request then
    throw "invocation framing may only normalize input"
  return prepared

def policyContextWith (runtime : Runtime) (o request : Json) (principal : String) : Evaluation Json := do
  let op ← str request "op"
  let command ← if op == "invoke" then str request "command" else pure ""
  let input ← if op == "invoke" then field request "input" else pure (obj [])
  discard (pairs input)
  return obj [("principal", .str principal), ("op", .str op), ("command", .str command),
    ("state", ← runtime.canonicalState o), ("input", input)]

def authorizeRequestWith (runtime : Runtime) (o request : Json) (principal : String) : Evaluation Unit := do
  let authority ← field o "law"
  validateLaw authority
  let principals ← match (← str request "op") with
    | "invoke" =>
      match (field (← field authority "invoke") (← str request "command")).toOption with
      | some grant => law grant
      | none => pure #[]
    | "reprogram" => law (← field authority "reprogram")
    | "law" => law (← field authority "law")
    | _ => throw "unknown operation"
  if !principals.contains principal then throw "unauthorized"
  -- A predicate only restricts an existing grant. Context conversion and every
  -- reduction consume the same budget as the operation it guards.
  match (field authority "predicate").toOption with
  | none => pure ()
  | some predicate =>
    runtime.checkSourcePolicy predicate (← put (← policyContextWith runtime o request principal) "object" (← field request "object"))

def authorizeRequest (o request : Json) (principal : String) : Evaluation Unit :=
  authorizeRequestWith {} o request principal

def rootCheck (o request : Json) : Except String Unit := do
  if o != (← field request "expected") then throw "stale read root"

-- A receiving invariant belongs to law, outside replaceable command code.
-- Every candidate uses actual staged states; invocation input has already been
-- resolved. This consumes the same turn budget as authority and execution.
def checkInvariantWith (runtime : Runtime) (authority before after request : Json) (principal : String)
    (beforeState afterState : Option Json := none) : Evaluation Unit := do
  let some invariant := (field authority "invariant").toOption | return
  let op ← str request "op"
  let command ← if op == "invoke" then str request "command" else pure ""
  let input ← if op == "invoke" then field request "input" else pure (obj [])
  let prior ← match beforeState with
    | some state => pure state
    | none => runtime.canonicalState before
  let next ← match afterState with
    | some state => pure state
    | none => runtime.canonicalState after
  let facts := obj [("object", .str (← str request "object")),
    ("principal", .str principal), ("op", .str op), ("command", .str command),
    ("state", prior), ("nextState", next), ("input", input)]
  runtime.checkSourcePolicy invariant facts

def checkInvariant (authority before after request : Json) (principal : String) : Evaluation Unit :=
  checkInvariantWith {} authority before after request principal

def checkCandidateWith (runtime : Runtime) (before after request : Json) (principal : String) : Evaluation Unit := do
  let beforeLaw ← field before "law"
  let afterLaw ← field after "law"
  let hasInvariant := (field beforeLaw "invariant").isOk ||
    ((str request "op").toOption == some "law" && (field afterLaw "invariant").isOk)
  let beforeState ← if hasInvariant then some <$> runtime.canonicalState before else pure none
  let afterState ← if hasInvariant then some <$> runtime.canonicalState after else pure none
  checkInvariantWith runtime beforeLaw before after request principal beforeState afterState
  let op ← str request "op"
  let checkContract (authority : Json) (methods : Bool) : Evaluation Unit := do
    if let some contract := (field authority "contract").toOption then
      runtime.checkSourceContract contract after methods
  let checkAmendment (authority : Json) : Evaluation Unit := do
    if let some amendment := (field authority "amendment").toOption then
      runtime.checkSourceAmendment amendment before after request principal
  checkAmendment beforeLaw
  checkContract beforeLaw (["create", "reprogram", "law"].contains op)
  -- New law cannot install an invariant already false of the proposed state.
  -- Old law must also admit its own revision; management has no bypass.
  if op == "law" then
    -- Both callbacks close over the identical actual before/after/request/caller.
    -- An unchanged pure amendment has already accepted that context above. Reuse
    -- only this verdict, never across objects, steps, or requests; a changed
    -- descriptor still runs its new guard under the remaining shared budget.
    let sameAmendment := (field beforeLaw "amendment").toOption == (field afterLaw "amendment").toOption
    unless sameAmendment do checkAmendment afterLaw
    checkInvariantWith runtime afterLaw before after request principal beforeState afterState
    checkContract afterLaw true

def checkCandidate (before after request : Json) (principal : String) : Evaluation Unit :=
  checkCandidateWith {} before after request principal

def receipt (request : Json) (kind : String) (data : Json) : Json :=
  obj [("intent", (field request "intent").toOption.getD .null),
       ("object", (field request "object").toOption.getD .null),
       ("kind", .str kind), ("data", data)]

def executeCommandWith (runtime : Runtime) (o request : Json) (principal : String)
    (inputOrigin : Json := noInputOrigin) (eventFacts : Option Json := none)
    (physicalInput : Option Json := none) : Evaluation TransitionResult := do
  let protocol ← field o "protocol"
  let command ← field (← field protocol "commands") (← str request "command")
  let state ← field o "state"
  let input ← field request "input"
  discard (pairs input)
  let context : CallContext := { object := ← str request "object", protocol := protocol, inputOrigin := inputOrigin, eventFacts := eventFacts, physicalInput := physicalInput }
  validateTransitionCommand command
  let some transition := sourceTransition? command | throw "source command requires current transition"
  runtime.executeTransition context state input principal transition

-- Both standalone and transaction admission install exactly this replacement.
-- Authorization belongs to the caller's current-law check, never the candidate.
def reprogramObjectWith (runtime : Runtime) (o protocol state : Json) : Evaluation Json := do
  validateProtocolWith runtime protocol
  let state ← runtime.recodeState o protocol state
  discard (pairs state)
  let n ← (← field o "version").getNat?
  put (← put (← put o "protocol" protocol) "state" state) "version" (toJson (n+1))

-- Bootstrap and governed allocation construct the same object shape. The
-- latter obtains authority only from the current receiving factory invocation.
def newObjectUsing {m : Type → Type} [Monad m] [MonadLiftT (Except String) m]
    (validate : Json → m Unit) (protocol authority : Json) : m Json := do
  validate protocol
  validateLaw authority
  return obj [("protocol", protocol), ("law", authority), ("version", toJson (0 : Nat)),
    ("state", ← field protocol "initial")]

/-- Bootstrap/allocation remain in their caller's current evaluation and cache. -/
def newObjectWith (runtime : Runtime) (protocol authority : Json) : Evaluation Json :=
  newObjectUsing (validateProtocolWith runtime) protocol authority

/-- Pure default-host construction shares the same framing and law validation. -/
def newObject (protocol authority : Json) : Except String Json :=
  newObjectUsing validateProtocol protocol authority

def absenceReads (objects request : Json) : Except String (Array String) := do
  let absent ← match (field request "absent").toOption with
    | none => pure #[]
    | some value => law value
  for id in absent do
    if id.isEmpty then throw "empty absence object id"
    if (field objects id).isOk then throw "stale absence root"
  return absent

def childName (name : String) : Bool :=
  !name.isEmpty && name.length <= 64 && name.toList.all (fun c =>
    (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
    (c >= '0' && c <= '9') || c == '-' || c == '_')

def directChild (parent child : String) : Bool :=
  let namespacePrefix := parent ++ "/"
  namespacePrefix.isPrefixOf child && !(child.drop namespacePrefix.length).toString.contains '/'

-- Every explicit descriptor faces the same local quota, absence and child-law
-- checks for source-authored descriptors. No descriptor
-- transfers parent authority to a later child invocation.
def allocateDescriptorsWith (runtime : Runtime) (objects protocol : Json)
    (parent principal : String) (absent : Array String) (allocations : Array Allocation)
    :
    Evaluation (Json × Json) := do
  if allocations.isEmpty then return (objects, obj [])
  let limit ← (← allocationLimit protocol).toExcept "allocation requires factory policy"
  let mut staged := objects
  let mut roots : Array (String × Json) := #[]
  let mut childCount := (← pairs objects).countP (fun entry => directChild parent entry.1)
  for produced in allocations do
    tick
    let allocation := produced.descriptor
    if (← pairs allocation).map Prod.fst != ["law", "name", "protocol"] then
      throw "allocation requires exactly name, protocol and law"
    let name ← (← field allocation "name").getStr?
    if !childName name then throw "invalid child name"
    let id := parent ++ "/" ++ name
    if !absent.contains id then throw "allocation target missing absence root"
    if (field staged id).isOk then throw "object exists"
    if childCount >= limit then throw "factory child quota exhausted"
    let protocol ← field allocation "protocol"
    let child ← newObjectWith runtime protocol (← field allocation "law")
    let child ← match produced.initial with
      | none => pure child
      | some initial => put child "state" (← runtime.initializeAllocation protocol initial)
    checkCandidateWith runtime child child (obj [("op", .str "create"), ("object", .str id)]) principal
    staged ← put staged id child
    roots := roots.push (id, child)
    childCount := childCount + 1
  return (staged, obj roots.toList)

-- Source has already produced descriptors under the same metered execution.
def allocateChildrenWith (runtime : Runtime) (objects o request : Json)
    (principal : String) (absent : Array String)
    (_inputOrigin : Json := noInputOrigin) (sourceAllocations : Array Allocation := #[]) : Evaluation (Json × Json) := do
  allocateDescriptorsWith runtime objects (← field o "protocol")
    (← str request "object") principal absent sourceAllocations

def transitionEvaluationWith (runtime : Runtime) (world request : Json) (principal : String) : Evaluation (Json × Json) := do
  let workStart ← get
  let objects ← field world "objects"
  let id ← str request "object"
  if id.isEmpty then throw "empty object id"
  let op ← str request "op"
  if op == "create" then
    if (field objects id).isOk then throw "object exists"
    let o ← newObjectWith runtime (← field request "protocol") (← field request "law")
    checkCandidateWith runtime o o request principal
    let next ← put world "objects" (← put objects id o)
    return (next, receipt request "committed" (obj [("root",o), ("result",.null), ("outbox", .arr #[])]))
  -- This profile returns complete roots in receipts; invocation rights alone
  -- cannot authorize acquiring a private preimage through that reply.
  let o ← readObject objects id principal
  let semanticRequest ← prepareInvocation runtime o request
  authorizeRequestWith runtime o semanticRequest principal
  rootCheck o request
  let n ← (← field o "version").getNat?
  if op == "law" then
    let authority ← field request "law"
    validateLaw authority
    let nextObj ← put (← put o "law" authority) "version" (toJson (n+1))
    checkCandidateWith runtime o nextObj request principal
    let next ← put world "objects" (← put objects id nextObj)
    return (next, receipt request "committed" (obj [("root",nextObj), ("result",.null), ("outbox", .arr #[])]))
  if op == "reprogram" then
    for (key, _) in (← pairs request) do
      if !(["op", "object", "principal", "intent", "expected", "protocol", "state"].contains key) then
        throw "unsupported reprogram field"
    let protocol ← field request "protocol"
    -- Migration is an explicit complete record, never an implicit reset or
    -- an expression executed with extra authority. Law and identity stay put.
    let state ← field request "state"
    let nextObj ← reprogramObjectWith runtime o protocol state
    checkCandidateWith runtime o nextObj request principal
    let next ← put world "objects" (← put objects id nextObj)
    let result ← runtime.reprogramResult id nextObj
    return (next, receipt request "committed" (obj [("root",nextObj), ("result",result), ("outbox", .arr #[])]))
  if op != "invoke" then throw "unknown operation"
  let absent ← absenceReads objects request
  let produced ← executeCommandWith runtime o semanticRequest principal
    noInputOrigin none (some (← field request "input"))
  let nextObj ← put (← put o "state" produced.state) "version" (toJson (n+1))
  checkCandidateWith runtime o nextObj semanticRequest principal
  let (staged, allocated) ← allocateChildrenWith runtime (← put objects id nextObj) o semanticRequest principal absent noInputOrigin produced.allocations
  let (next, messages, ordinaryOutbox) ← runtime.stageMessages
    (← put world "objects" staged) request request o 0 workStart produced.emissions
  let mut data := obj [("root",nextObj), ("result",produced.result), ("outbox", .arr ordinaryOutbox)]
  if !messages.isEmpty then data ← put data "messages" (.arr messages)
  if allocated != obj [] then data ← put data "allocated" allocated
  return (next, receipt request "committed" data)

def transitionWith (runtime : Runtime) (world request : Json) (principal : String) : Except String (Json × Json) := do
  let (result, _) ← (transitionEvaluationWith runtime world request principal).run runtime.budget
  return result

def executeCommand (o request : Json) (principal : String) : Evaluation TransitionResult :=
  executeCommandWith {} o request principal

def reprogramObject (o protocol state : Json) : Evaluation Json :=
  reprogramObjectWith {} o protocol state

def transitionEvaluation (world request : Json) (principal : String) : Evaluation (Json × Json) :=
  transitionEvaluationWith {} world request principal

def transition (world request : Json) (principal : String) : Except String (Json × Json) :=
  transitionWith {} world request principal

/-- First retained admission for this exact principal/intent identity. -/
def findReceipt (receipts : Array Json) (principal intent : String) : Except String (Option Json) := do
  for entry in receipts do
    let prior ← field entry "request"
    if (← str prior "principal") == principal && (← str prior "intent") == intent then
      return some entry
  return none

/-- Read-only exact retry lookup. Absence does not assert that the identity is free. -/
def retainedReply (receipts : Array Json) (request : Json) : Except String Json := do
  let some principal := (str request "principal").toOption | return .null
  let some intent := (str request "intent").toOption | return .null
  let some entry ← findReceipt receipts principal intent | return .null
  if (← field entry "request") == request then return ← field entry "receipt"
  return .null

-- Expanded internal envelopes contain retained source and exact state preimages.
-- Authored post/body limits are enforced separately by their transports.
def maxRequestBytes : Nat := 1024 * 1024

/-- Pure commit boundary used by every fresh admission, including compiled source
    and ordered transactions. A failed staged evaluation exposes no staged world. -/
def admissionOutcome (world request : Json) (attempt : Except String (Json × Json)) : Json × Json :=
  match attempt with
  | .ok value => value
  | .error error => (world, receipt request "refused" (.str error))

def handleWith
    (admit : Json → Json → String → Except String (Json × Json))
    (world request : Json) : Except String (Json × Json) := do
  if request.compress.utf8ByteSize > maxRequestBytes then throw "expanded request exceeds 1 MiB"
  let principal ← str request "principal"
  if principal.isEmpty then throw "empty principal"
  if (← str request "op") == "authorize-reads" then
    return (world, ← authorizeReads world request)
  if (← str request "op") == "object-history" then
    return (world, ← historyPage world request (← (← field world "receipts").getArr?))
  if (← str request "op") == "inspect" then
    return (world, ← readObject (← field world "objects") (← str request "object") principal)
  let intent ← str request "intent"
  if intent.isEmpty then throw "empty intent"
  let receipts ← (← field world "receipts").getArr?
  if let some entry ← findReceipt receipts principal intent then
    if (← field entry "request") == request then return (world, ← field entry "receipt")
    return (world, receipt request "refused" (.str "intent reused for different request"))
  let (next, outcome) := admissionOutcome world request (admit world request principal)
  let next ← put next "receipts" (.arr (receipts.push (obj [("request",request), ("receipt",outcome)])))
  return (next,outcome)

def handle (world request : Json) : Except String (Json × Json) :=
  handleWith transition world request

def jobWith (receive : Json → Json → Except String (Json × Json)) (j : Json) : Json :=
  match do
    let world ← field j "world"
    let request ← field j "request"
    let (next, reply) ← receive world request
    pure (obj [("world",next), ("reply",reply)]) with
  | .ok result => result
  | .error e => obj [("error", .str e)]

def job (j : Json) : Json := jobWith handle j

def serve (process : Json → Json) (encode : Json → String := Json.compress) : IO Unit := do
  let stdin ← IO.getStdin
  let stdout ← IO.getStdout
  repeat
    let line ← stdin.getLine
    if line.isEmpty then break
    let out := if line.utf8ByteSize > 16777216 then
        World.obj [("error", .str "frame exceeds 16 MiB")]
      else match Lean.Json.parse line with
        | .ok j => process j
        | .error e => World.obj [("error", .str e)]
    stdout.putStrLn (encode out)

end World
