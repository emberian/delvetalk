/- Durable local messages. This module owns retained evidence and consumption;
   source execution and physical custody are supplied by the receiving host. -/
import WorldCore
import FileCustody
import Compiler.Sha256
import ProgramDigest
open Lean World

namespace Messages

def registryProfile := "delvetalk-messages-v1"

-- Custody encoding preserves exact JSON-number mantissas/scales. A message binds
-- the complete protocol value, including metadata; hashes confer no authority.
def digest (value : Json) : String :=
  Minidregg.Compiler.Sha256.hexString (FileCustody.encode value)

def charge (amount : Nat) : Evaluation Unit := do
  let remaining ← get
  if amount > remaining then throw "invocation budget exhausted"
  set (remaining - amount)

def exact (value : Json) (keys : List String) (label : String) : Except String Unit := do
  let actual := (← pairs value).map Prod.fst
  if actual.length != keys.length || !(keys.all actual.contains) then
    throw (label ++ " has unsupported fields")

def component (value : Json) : Except String String := do
  let text ← value.getStr?
  if text.isEmpty || text.utf8ByteSize > 256 then throw "message identity must have 1..256 UTF-8 bytes"
  return text

def hashShape (value : Json) : Except String String := do
  let hash ← value.getStr?
  if hash.length != 64 || !(hash.toList.all (fun c =>
      (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) then
    throw "message program must be an exact SHA256 digest"
  return hash

-- Operator-selected limits are immutable lineage configuration. These named
-- host ceilings bound one causal admission, not the number of independent turns.
def maxDepth : Nat := 8
def maxFanout : Nat := 16
def maxEvents : Nat := 64
def maxWork : Nat := 1000000
def maxBytes : Nat := 1048576
def terminalReserve : Nat := 8192

def defaultLimits : Json := obj [("depth", toJson maxDepth), ("fanout", toJson maxFanout),
  ("events", toJson maxEvents), ("work", toJson maxWork), ("bytes", toJson maxBytes)]

def validateCapabilities (transition : Json) : Except String Unit := do
  if let some value := (field transition "messages").toOption then
    exact value ["emit", "receive"] "message capabilities"
    discard ((← field value "emit").getBool?)
    discard ((← field value "receive").getBool?)

def capability (transition : Json) (name : String) : Bool :=
  (((field transition "messages").bind (fun flags => field flags name)).bind Json.getBool?).toOption.getD false

def emits (transition : Json) : Bool := capability transition "emit"
def receives (transition : Json) : Bool := capability transition "receive"

def validateLimits (limits : Json) : Except String Unit := do
  exact limits ["depth", "fanout", "events", "work", "bytes"] "causal limits"
  for (key, ceiling) in [("depth", maxDepth), ("fanout", maxFanout), ("events", maxEvents),
      ("work", maxWork), ("bytes", maxBytes)] do
    let value ← (← field limits key).getNat?
    if value == 0 || value > ceiling then throw ("causal limit outside host ceiling: " ++ key)

def registry (world : Json) : Except String Json := do
  let value ← field world "messages"
  exact value ["profile", "lineage", "pendingLimit", "pending", "events", "captures", "causes", "limits"] "message registry"
  if (← str value "profile") != registryProfile then throw "unknown message registry profile"
  discard (component (← field value "lineage"))
  let pending ← (← field value "pendingLimit").getNat?
  if pending == 0 || pending > 128 then throw "message capacity must satisfy 1 <= pending <= 128"
  for key in ["events", "captures", "causes"] do discard ((← field value key).getObj?)
  if (← pairs (← field value "pending")).length > pending then throw "message pending index exceeds capacity"
  validateLimits (← field value "limits")
  return value

def initializeRegistry (world request : Json) : Except String (Json × Json) := do
  exact request (["op", "principal", "intent", "lineage", "pendingLimit"] ++
    if (field request "limits").isOk then ["limits"] else []) "messages-init"
  if (field world "messages").isOk then throw "message lineage is already initialized"
  if !(← pairs (← field world "objects")).isEmpty then throw "messages-init requires empty-world bootstrap"
  let value := obj [("profile", .str registryProfile),
    ("lineage", ← field request "lineage"), ("pendingLimit", ← field request "pendingLimit"),
    ("limits", (field request "limits").toOption.getD defaultLimits),
    ("pending", obj []), ("events", obj []), ("captures", obj []), ("causes", obj [])]
  let next ← put world "messages" value
  discard (registry next)
  return (next, receipt request "committed" value)

-- The typed source boundary decodes Prelude.Value once. Routing and payload
-- remain plain bounded data here, never expressions. An empty collection is pure.
def descriptor (value : Json) : Evaluation Unit := do
  exact value ["to", "command", "recipientProgram", "payload"] "message emission"
  discard (component (← field value "to"))
  discard (component (← field value "command"))
  discard (hashShape (← field value "recipientProgram"))
  let payload ← field value "payload"
  discard (pairs payload)
  if (FileCustody.encode payload).utf8ByteSize > 4096 then throw "message payload exceeds 4096 bytes"
  discard (ProgramDigest.render value)

def counter (value : Json) (key : String) : Except String Nat := (field value key).bind Json.getNat?

def withinLedger (config ledger : Json) : Except String Unit := do
  let limits ← field config "limits"
  for key in ["events", "work", "bytes"] do
    if (← counter ledger key) > (← counter limits key) then throw ("causal " ++ key ++ " capacity exhausted")

-- A capture is retained once per emitting call. Events carry only its reference;
-- authenticated facts and query projections are resolved by the receiver.
def resolvedEvidence (config evidence : Json) : Except String Json := do
  let capture ← field (← field config "captures") (← str evidence "capture")
  for key in ["source", "sourceProgram", "originatingPrincipal", "admission", "call"] do
    if (← field capture key) != (← field evidence key) then throw "message capture differs from evidence"
  put evidence "sourcePreimage" (← field capture "sourcePreimage")

def resolvedEvent (config event : Json) : Except String Json := do
  put event "evidence" (← resolvedEvidence config (← field event "evidence"))

def stageCausal (world admission invocation preimage : Json) (call : Nat)
    (emitted : Array Json) (parent : Option Json) (workStart : Option Nat := none) : Evaluation (Json × Array Json × Array Json) := do
  let command ← field (← field (← field preimage "protocol") "commands") (← str invocation "command")
  let some transition := (field command "transition").toOption | return (world, #[], emitted)
  validateCapabilities transition
  if !emits transition then
    if !emitted.isEmpty then throw "message emission capability missing"
    return (world, #[], #[])
  if emitted.size > maxFanout then throw "message fanout exceeds host ceiling"
  for value in emitted do descriptor value
  if emitted.isEmpty then return (world, #[], #[])
  let config ← registry world
  let limits ← field config "limits"
  if emitted.size > (← counter limits "fanout") then throw "causal fanout capacity exhausted"
  let mut events ← field config "events"
  let mut captures ← field config "captures"
  let mut causes ← field config "causes"
  let mut pendingIndex ← field config "pending"
  let mut pending := (← pairs pendingIndex).length
  let source ← component (← field invocation "object")
  let principal ← component (← field admission "principal")
  let intent ← component (← field admission "intent")
  let lineage ← field config "lineage"
  let origin := obj [("principal", .str principal), ("intent", .str intent)]
  let (causeId, parentId, depth) ← match parent with
    | none => pure (digest (obj [("lineage", lineage), ("admission", origin)]), "", 0)
    | some evidence => do
      let causal ← field evidence "causal"
      pure (← str causal "root", ← str (← field evidence "ref") "id", (← counter causal "depth") + 1)
  if depth > (← counter limits "depth") then throw "causal depth capacity exhausted"
  let mut ledger ← match (field causes causeId).toOption with
    | some value => pure value
    | none => do
      if parent.isSome then throw "message causal ledger missing"
      pure (obj [("origin", origin), ("events", toJson (0 : Nat)),
        ("work", toJson (0 : Nat)), ("bytes", toJson (0 : Nat))])
  let program ← field preimage "protocol"
  -- Prepay traversal and canonical rendering before capture allocation using
  -- the same physical prices as program hashing. Retained bytes remain exact;
  -- work units do not charge large shared source text once per UTF-8 byte.
  let (sourceBytes, _) ← (ProgramDigest.measure ProgramDigest.maxDepth preimage).run 0
  if sourceBytes > 65536 then throw "message source preimage exceeds 64 KiB"
  charge (8 * ((sourceBytes + 63) / 64))
  if (FileCustody.encode preimage).utf8ByteSize != sourceBytes then
    throw "message source capture size mismatch"
  let sourceProgram ← ProgramDigest.digest program
  let captureId := digest (obj [("lineage", lineage), ("admission", origin), ("call", toJson call)])
  if (field captures captureId).isOk then throw "message capture identity collision"
  let captureHead := obj [("source", .str source), ("sourceProgram", .str sourceProgram),
    ("originatingPrincipal", .str principal), ("admission", origin), ("call", toJson call)]
  let headBytes := (← ProgramDigest.render captureHead).utf8ByteSize
  -- Exact encoded size after adding one member to this nonempty JSON object;
  -- reuse the already encoded preimage instead of traversing it a second time.
  let captureBytes := headBytes + sourceBytes + (FileCustody.encode (.str "sourcePreimage")).utf8ByteSize + 2
  captures ← put captures captureId (← put captureHead "sourcePreimage" preimage)
  ledger ← put ledger "bytes" (toJson ((← counter ledger "bytes") + captureBytes))
  let mut targets : Array (String × Json × String) := #[]
  let mut references := #[]
  for slot in [:emitted.size] do
    let value := emitted[slot]!
    if pending >= (← counter config "pendingLimit") then throw "message pending capacity exhausted"
    let recipient ← str value "to"
    let currentRows ← (← pairs pendingIndex).mapM fun row => do return (row.1, ← field events row.1)
    charge currentRows.length
    let fromSource := currentRows.countP (fun row =>
      ((field row.2 "evidence").bind (fun e => str e "source")).toOption == some source)
    let toRecipient := currentRows.countP (fun row =>
      ((field row.2 "evidence").bind (fun e => str e "to")).toOption == some recipient)
    if fromSource >= 32 || toRecipient >= 32 then throw "message emitter or recipient pending capacity exhausted"
    let (targetProgram, targetDigest) ← match targets.find? (fun row => row.1 == recipient) with
      | some (_, program, hash) => pure (program, hash)
      | none => do
        let target ← field (← field world "objects") recipient
        let program ← field target "protocol"
        let hash ← ProgramDigest.digest program
        targets := targets.push (recipient, program, hash)
        pure (program, hash)
    if targetDigest != (← str value "recipientProgram") then throw "message recipient program changed before emission"
    let targetCommand ← field (← field targetProgram "commands") (← str value "command")
    let targetTransition ← field targetCommand "transition"
    validateCapabilities targetTransition
    if !receives targetTransition then throw "message target must be a receive-only source command"
    let identity := obj [("lineage", lineage), ("principal", .str principal),
      ("intent", .str intent), ("call", toJson call), ("slot", toJson slot)]
    let id := digest identity
    if (field events id).isOk then throw "message identity collision"
    let reference := obj [("lineage", lineage), ("id", .str id)]
    let evidence := obj [("ref", reference), ("capture", .str captureId), ("source", .str source),
      ("sourceProgram", .str sourceProgram), ("originatingPrincipal", .str principal),
      ("admission", origin), ("call", toJson call), ("slot", toJson slot), ("to", .str recipient),
      ("command", ← field value "command"), ("recipientProgram", ← field value "recipientProgram"),
      ("payload", ← field value "payload"), ("causal", obj [("root", .str causeId),
        ("parent", .str parentId), ("depth", toJson depth)])]
    let row := obj [("evidence", evidence), ("status", .str "pending")]
    let rowBytes := (← ProgramDigest.render row).utf8ByteSize
    ledger ← put (← put ledger "events" (toJson ((← counter ledger "events") + 1))) "bytes"
      (toJson ((← counter ledger "bytes") + rowBytes + terminalReserve))
    withinLedger config ledger
    events ← put events id row
    pendingIndex ← put pendingIndex id (.bool true)
    references := references.push reference
    pending := pending + 1
  if let some start := workStart then
    let remaining ← get
    ledger ← put ledger "work" (toJson ((← counter ledger "work") + start - remaining))
    withinLedger config ledger
  causes ← put causes causeId ledger
  let updated ← put (← put (← put (← put config "events" events) "pending" pendingIndex)
    "captures" captures) "causes" causes
  return (← put world "messages" updated, references, #[])

def stage (world admission invocation preimage : Json) (call workStart : Nat)
    (emitted : Array Json) : Evaluation (Json × Array Json × Array Json) :=
  stageCausal world admission invocation preimage call emitted none (some workStart)

-- Query and delivery resolve only receiver-retained evidence. The request never
-- carries payload, causal authority, source facts or an alternative capture.
def pendingEvent (world request : Json) : Except String (Json × String × Json) := do
  let config ← registry world
  let reference ← field request "event"
  exact reference ["lineage", "id"] "event reference"
  if (← field reference "lineage") != (← field config "lineage") then throw "foreign message lineage"
  let id ← hashShape (← field reference "id")
  let row ← field (← field config "events") id
  if (← str row "status") != "pending" then throw "message already terminal"
  let evidence ← resolvedEvidence config (← field row "evidence")
  if (← field evidence "ref") != reference then throw "message reference differs from evidence"
  if (← str request "object") != (← str evidence "to") then throw "message recipient cannot be redirected"
  return (config, id, evidence)

def terminal (config : Json) (id : String) (status : String) (consumption : Json) : Except String Json := do
  let events ← field config "events"
  let row ← field events id
  let updated ← put (← put row "status" (.str status)) "consumption" consumption
  let growth := (FileCustody.encode updated).utf8ByteSize - (FileCustody.encode row).utf8ByteSize
  if growth > terminalReserve then throw "terminal metadata exceeds reserved storage"
  let pending ← (← field config "pending").getObj?
  put (← put config "events" (← put events id updated)) "pending" (.obj (pending.erase id))

def deliverWith (runtime : Runtime) (world request : Json) (principal : String) : Except String (Json × Json) := do
  exact request ["op", "principal", "intent", "object", "event", "expected"] "deliver"
  discard (component (.str principal))
  discard (component (← field request "intent"))
  let (config, id, evidence) ← pendingEvent world request
  let target ← str evidence "to"
  let preimage ← readObject (← field world "objects") target principal
  if preimage != (← field request "expected") then throw "stale read root"
  let causal ← field evidence "causal"
  let causeId ← str causal "root"
  let ledger ← field (← field config "causes") causeId
  let used ← counter ledger "work"
  let ceiling ← counter (← field config "limits") "work"
  if used >= ceiling then throw "causal work capacity exhausted"
  let fuel := min runtime.budget (ceiling - used)
  let invocation := obj [("op", .str "invoke"), ("object", .str target),
    ("command", ← field evidence "command"), ("input", ← field evidence "payload")]
  let facts := obj [("id", .str id), ("source", ← field evidence "source"),
    ("sourceProgram", ← field evidence "sourceProgram"),
    ("originatingPrincipal", ← field evidence "originatingPrincipal"),
    ("root", .str causeId), ("parent", ← field causal "parent"), ("depth", ← field causal "depth"),
    ("rootPrincipal", ← field (← field ledger "origin") "principal")]
  let execution : Evaluation (Json × Json) := do
    let prepared ← prepareInvocation runtime preimage invocation
    let semanticInvocation := prepared.request
    authorizeRequestWith runtime preimage semanticInvocation principal
    if (← ProgramDigest.digest (← field preimage "protocol")) != (← str evidence "recipientProgram") then
      throw "message recipient program changed"
    let produced ← executeCommandWith runtime preimage semanticInvocation principal noInputOrigin (some facts) (some (← field evidence "payload")) prepared.nativeInput
    if !produced.allocations.isEmpty then throw "message delivery cannot allocate children"
    let version ← counter preimage "version"
    let nextObject ← put (← put preimage "state" produced.state) "version" (toJson (version + 1))
    checkCandidateWith runtime preimage nextObject semanticInvocation principal
    let objects ← put (← field world "objects") target nextObject
    let consumed ← terminal config id "consumed" (obj [("principal", .str principal), ("intent", ← field request "intent")])
    let prepared ← put (← put world "objects" objects) "messages" consumed
    let (next, children, _) ← stageCausal prepared request invocation preimage 0 produced.emissions (some evidence)
    let mut data := obj [("root", nextObject), ("result", produced.result), ("outbox", .arr #[]),
      ("event", ← field request "event"), ("recipient", .str target), ("status", .str "consumed")]
    if !children.isEmpty then data ← put data "messages" (.arr children)
    let outputBytes := (← ProgramDigest.render data).utf8ByteSize
    let current ← registry next
    let causes ← field current "causes"
    let updated ← field causes causeId
    let remaining ← get
    let updated ← put (← put updated "work" (toJson (used + fuel - remaining))) "bytes"
      (toJson ((← counter updated "bytes") + outputBytes))
    withinLedger current updated
    let final ← put next "messages" (← put current "causes" (← put causes causeId updated))
    return (final, data)
  let ((next, data), _) ← execution.run fuel
  return (next, receipt request "committed" data)

-- Settlement is recipient governance, not source recall or execution of an old
-- payload against replacement code. Reserved terminal bytes permit cleanup even
-- when the causal computation/evidence budget has reached its ceiling.
def settleWith (runtime : Runtime) (world request : Json) (principal : String) : Except String (Json × Json) := do
  exact request ["op", "principal", "intent", "object", "event", "expected", "reason"] "settle-message"
  discard (component (.str principal))
  discard (component (← field request "intent"))
  let reason ← str request "reason"
  if reason.isEmpty || (FileCustody.encode (.str reason)).utf8ByteSize > 1024 then throw "settlement requires a bounded nonempty reason"
  let (config, id, evidence) ← pendingEvent world request
  let target ← str evidence "to"
  let preimage ← readObject (← field world "objects") target principal
  if preimage != (← field request "expected") then throw "stale read root"
  let input := obj [("event", ← field request "event"), ("reason", .str reason),
    ("source", ← field evidence "source"), ("sourceProgram", ← field evidence "sourceProgram"),
    ("originatingPrincipal", ← field evidence "originatingPrincipal"), ("causal", ← field evidence "causal")]
  let governed := obj [("op", .str "invoke"), ("object", .str target),
    ("command", .str "$messages-settle"), ("input", input)]
  let decision : Evaluation Unit := do
    let reference ← field request "event"
    let causal ← field evidence "causal"
    let metadata : Minidregg.Theory.ObjectiveBendDemandData.Data := .record [
      ("event", .record [("lineage", .label (← str reference "lineage")), ("id", .label (← str reference "id"))]),
      ("reason", .label reason), ("source", .label (← str evidence "source")),
      ("sourceProgram", .label (← str evidence "sourceProgram")),
      ("originatingPrincipal", .label (← str evidence "originatingPrincipal")),
      ("causal", .record [("root", .label (← str causal "root")),
        ("parent", .label (← str causal "parent")), ("depth", .natural (← counter causal "depth"))])]
    charge 12
    authorizeRequestWith runtime preimage governed principal (some metadata)
    checkCandidateWith runtime preimage preimage governed principal (some metadata)
  discard (decision.run runtime.budget)
  let consumption := obj [("principal", .str principal), ("intent", ← field request "intent"),
    ("reason", .str reason)]
  let next ← put world "messages" (← terminal config id "settled" consumption)
  let data := obj [("root", preimage), ("event", ← field request "event"), ("recipient", .str target),
    ("status", .str "settled"), ("reason", .str reason), ("outbox", .arr #[])]
  return (next, receipt request "committed" data)

-- New acquisition of retained facts faces both endpoint laws. An event locator
-- grants nothing, and evidence is expanded only after these current read checks.
def query (world request : Json) : Except String Json := do
  let principal ← component (← field request "principal")
  let objects ← field world "objects"
  let config ← registry world
  match (← str request "op") with
  | "messages-pending" =>
    exact request ["op", "principal"] "messages-pending"
    let mut visible := obj []
    for (id, value) in (← pairs (← field config "pending")) do
      let retained ← field (← field config "events") id
      let evidence ← field retained "evidence"
      if !(readObject objects (← str evidence "source") principal).isOk ||
          !(readObject objects (← str evidence "to") principal).isOk then continue
      visible ← put visible id value
    return obj [("profile", ← field config "profile"), ("lineage", ← field config "lineage"),
      ("pending", visible)]
  | "message-event" =>
    exact request ["op", "principal", "event"] "message-event"
    let reference ← field request "event"
    exact reference ["lineage", "id"] "event reference"
    if (← field reference "lineage") != (← field config "lineage") then throw "foreign message lineage"
    let id ← hashShape (← field reference "id")
    let retained ← field (← field config "events") id
    let evidence ← field retained "evidence"
    if (← field evidence "ref") != reference then throw "message reference differs from evidence"
    discard (readObject objects (← str evidence "source") principal)
    let root ← readObject objects (← str evidence "to") principal
    return obj [("event", ← resolvedEvent config retained), ("root", root)]
  | _ => throw "unknown message query"

end Messages
