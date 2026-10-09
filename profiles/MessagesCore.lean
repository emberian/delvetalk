/- Durable local messages. This module owns retained evidence and consumption;
   source execution and physical custody are supplied by the receiving host. -/
import WorldCore
import FileCustody
import Compiler.Sha256
open Lean World

namespace Messages

def effectsProfile := "delvetalk-source-effects-v1"
def receiveProfile := "delvetalk-source-receive-v1"
def dataEffectsProfile := "delvetalk-source-data-effects-v1"
def dataReceiveProfile := "delvetalk-source-data-receive-v1"
def isEffects (profile : String) : Bool := profile == effectsProfile || profile == dataEffectsProfile
def isReceive (profile : String) : Bool := profile == receiveProfile || profile == dataReceiveProfile
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

def registry (world : Json) : Except String Json := do
  let value ← field world "messages"
  exact value ["profile", "lineage", "pendingLimit", "pending", "events"] "message registry"
  if (← str value "profile") != registryProfile then throw "unknown message registry profile"
  discard (component (← field value "lineage"))
  let pending ← (← field value "pendingLimit").getNat?
  if pending == 0 || pending > 128 then
    throw "message capacity must satisfy 1 <= pending <= 128"
  discard ((← field value "events").getObj?)
  if (← pairs (← field value "pending")).length > pending then
    throw "message pending index exceeds capacity"
  return value

def initializeRegistry (world request : Json) : Except String (Json × Json) := do
  exact request ["op", "principal", "intent", "lineage", "pendingLimit"] "messages-init"
  if (field world "messages").isOk then throw "message lineage is already initialized"
  if !(← pairs (← field world "objects")).isEmpty then
    throw "messages-init requires empty-world bootstrap"
  let value := obj [("profile", .str registryProfile),
    ("lineage", ← field request "lineage"), ("pendingLimit", ← field request "pendingLimit"),
    ("pending", obj []), ("events", obj [])]
  let next ← put world "messages" value
  discard (registry next)
  return (next, receipt request "committed" value)

-- Every emission slot is validated before enabled flags are considered. Payload
-- is ordinary bounded record data; there is no executable expression in it.
def descriptor (value : Json) : Evaluation Unit := do
  exact value ["enabled", "to", "command", "recipientProgram", "payload"] "message emission"
  discard ((← field value "enabled").getBool?)
  discard (component (← field value "to"))
  discard (component (← field value "command"))
  discard (hashShape (← field value "recipientProgram"))
  let payload ← field value "payload"
  discard (pairs payload)
  if (FileCustody.encode payload).utf8ByteSize > 4096 then throw "message payload exceeds 4096 bytes"
  discard (toTerm 64 payload)
  charge (FileCustody.encode value).utf8ByteSize

-- This hook is called at the actual invocation position, while the admission is
-- still staged. Ordinary outboxes and matching-looking data never enter it.
def stage (world admission invocation preimage : Json) (call : Nat)
    (emitted : Array Json) : Evaluation (Json × Array Json × Array Json) := do
  let command ← field (← field (← field preimage "protocol") "commands") (← str invocation "command")
  let profile := ((field command "transition").bind (fun value => str value "profile")).toOption
  if !(isEffects (profile.getD "")) then return (world, #[], emitted)
  if emitted.size != 4 then throw "source effects require exactly four emission slots"
  for value in emitted do descriptor value
  -- A pure branch of an effects-capable command needs no delivery custody.
  -- Validation remains eager: disabling a malformed slot cannot hide it.
  if emitted.all (fun value => ((field value "enabled").bind Json.getBool?).toOption == some false) then
    return (world, #[], #[])
  let config ← registry world
  let mut events ← field config "events"
  let mut pendingIndex ← field config "pending"
  let mut pending := (← pairs pendingIndex).length
  let source ← component (← field invocation "object")
  let principal ← component (← field admission "principal")
  let intent ← component (← field admission "intent")
  let program ← field preimage "protocol"
  let sourceBytes := (FileCustody.encode preimage).utf8ByteSize
  if sourceBytes > 65536 then throw "message source preimage exceeds 64 KiB"
  let programBytes := FileCustody.encode program
  charge (sourceBytes + programBytes.utf8ByteSize)
  let sourceProgram := Minidregg.Compiler.Sha256.hexString programBytes
  -- Source capture is one immutable Json value shared by every slot. Recipient
  -- roots cannot change inside this staging call: resolve and hash each once.
  let mut targets : Array (String × Json × String) := #[]
  let mut references := #[]
  for slot in [:emitted.size] do
    let value := emitted[slot]!
    if !(← (← field value "enabled").getBool?) then continue
    if pending >= (← (← field config "pendingLimit").getNat?) then
      throw "message pending capacity exhausted"
    let recipient ← str value "to"
    let currentRows ← (← pairs pendingIndex).mapM fun row => do
      return (row.1, ← field events row.1)
    charge currentRows.length
    let fromSource := currentRows.countP (fun row =>
      (str row.2 "status").toOption == some "pending" &&
      ((field row.2 "evidence").bind (fun e => str e "source")).toOption == some source)
    let toRecipient := currentRows.countP (fun row =>
      (str row.2 "status").toOption == some "pending" &&
      ((field row.2 "evidence").bind (fun e => str e "to")).toOption == some recipient)
    if fromSource >= 32 || toRecipient >= 32 then
      throw "message emitter or recipient pending capacity exhausted"
    let (targetProgram, targetDigest) ← match targets.find? (fun row => row.1 == recipient) with
      | some (_, program, hash) => pure (program, hash)
      | none => do
        let target ← field (← field world "objects") recipient
        let program ← field target "protocol"
        let bytes := FileCustody.encode program
        charge bytes.utf8ByteSize
        let hash := Minidregg.Compiler.Sha256.hexString bytes
        targets := targets.push (recipient, program, hash)
        pure (program, hash)
    if targetDigest != (← str value "recipientProgram") then
      throw "message recipient program changed before emission"
    let targetCommand ← field (← field targetProgram "commands") (← str value "command")
    if !isReceive (((field targetCommand "transition").bind (fun t => str t "profile")).toOption.getD "") then
      throw "message target must be a receive-only source command"
    let identity := obj [("lineage", ← field config "lineage"), ("principal", .str principal),
      ("intent", .str intent), ("call", toJson call), ("slot", toJson slot)]
    let id := digest identity
    if (field events id).isOk then throw "message identity collision"
    let reference := obj [("lineage", ← field config "lineage"), ("id", .str id)]
    let evidence := obj [("ref", reference), ("source", .str source), ("sourcePreimage", preimage),
      ("sourceProgram", .str sourceProgram), ("originatingPrincipal", .str principal),
      ("admission", obj [("principal", .str principal), ("intent", .str intent)]),
      ("call", toJson call), ("slot", toJson slot), ("to", .str recipient),
      ("command", ← field value "command"), ("recipientProgram", ← field value "recipientProgram"),
      ("payload", ← field value "payload")]
    events ← put events id (obj [("evidence", evidence), ("status", .str "pending")])
    pendingIndex ← put pendingIndex id (.bool true)
    references := references.push reference
    pending := pending + 1
  let updated ← put (← put config "events" events) "pending" pendingIndex
  return (← put world "messages" updated, references, #[])

-- Only native staged admission mints this table. Retained immutable evidence is
-- sufficient; delivery must not scan receipt history (resident custody indexes it).
def deliverWith (runtime : Runtime) (world request : Json) (principal : String) : Except String (Json × Json) := do
  exact request ["op", "principal", "intent", "object", "event", "expected"] "deliver"
  let config ← registry world
  let reference ← field request "event"
  exact reference ["lineage", "id"] "event reference"
  if (← field reference "lineage") != (← field config "lineage") then throw "foreign message lineage"
  let id ← hashShape (← field reference "id")
  let events ← field config "events"
  let retained ← field events id
  if (← str retained "status") != "pending" then throw "message already consumed"
  let evidence ← field retained "evidence"
  if (← field evidence "ref") != reference then throw "message reference differs from evidence"
  let target ← str evidence "to"
  if (← str request "object") != target then throw "message recipient cannot be redirected"
  let preimage ← field (← field world "objects") target
  if preimage != (← field request "expected") then throw "stale read root"
  if digest (← field preimage "protocol") != (← str evidence "recipientProgram") then
    throw "message recipient program changed"
  let invocation := obj [("op", .str "invoke"), ("object", .str target),
    ("command", ← field evidence "command"), ("input", ← field evidence "payload")]
  let facts := obj [("id", .str id), ("source", ← field evidence "source"),
    ("sourceProgram", ← field evidence "sourceProgram"),
    ("originatingPrincipal", ← field evidence "originatingPrincipal")]
  let execution : Evaluation (Json × Json) := do
    authorizeRequest preimage invocation principal
    let (state, result, emitted) ← executeCommandWith runtime preimage invocation principal
      noInputOrigin (some facts)
    if !emitted.isEmpty then throw "message delivery cannot emit descendants"
    let version ← (← field preimage "version").getNat?
    let nextObject ← put (← put preimage "state" state) "version" (toJson (version + 1))
    checkCandidateWith runtime preimage nextObject invocation principal
    return (nextObject, result)
  let ((nextObject, result), _) ← execution.run runtime.budget
  let objects ← put (← field world "objects") target nextObject
  let terminal := obj [("evidence", evidence), ("status", .str "consumed"),
    ("consumption", obj [("principal", .str principal), ("intent", ← field request "intent")])]
  let pendingIndex ← (← field config "pending").getObj?
  let nextRegistry ← put (← put config "events" (← put events id terminal)) "pending"
    (.obj (pendingIndex.erase id))
  let next ← put (← put world "objects" objects) "messages" nextRegistry
  let data := obj [("root", nextObject), ("result", result), ("outbox", .arr #[]),
    ("event", reference), ("recipient", .str target), ("status", .str "consumed")]
  return (next, receipt request "committed" data)

-- Public bounded observations; never admissions, acknowledgements, or claims.
def query (world request : Json) : Except String Json := do
  discard (component (← field request "principal"))
  let config ← registry world
  match (← str request "op") with
  | "messages-pending" =>
    exact request ["op", "principal"] "messages-pending"
    return obj [("profile", ← field config "profile"), ("lineage", ← field config "lineage"),
      ("pending", ← field config "pending")]
  | "message-event" =>
    exact request ["op", "principal", "event"] "message-event"
    let reference ← field request "event"
    exact reference ["lineage", "id"] "event reference"
    if (← field reference "lineage") != (← field config "lineage") then throw "foreign message lineage"
    let id ← hashShape (← field reference "id")
    let retained ← field (← field config "events") id
    let evidence ← field retained "evidence"
    if (← field evidence "ref") != reference then throw "message reference differs from evidence"
    let root := (field (← field world "objects") (← str evidence "to")).toOption.getD .null
    return obj [("event", retained), ("root", root)]
  | _ => throw "unknown message query"

end Messages
