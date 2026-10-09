/- Opt-in source package and hash expressions. All admission is shared with the
   default hosts; only this executable selects the extensions and larger budget. -/
import SourceState
import TransactionsCore
import MessagesCore
import FileCustody
import ProgramDigest
import ResidentStore
import SourcePackages
import SourceContract
import SourceAmendment
import SourcePolicy
import SourceProjection
import Preparation
import Delvetalk.Package
open Lean World

namespace Compiled

def charge (amount : Nat) : Evaluation Unit := do
  let remaining ← get
  if amount > remaining then throw "invocation budget exhausted"
  set (remaining - amount)

def sourceSpec (spec : Json) : Except String Json := do
  for (key, _) in (← pairs spec) do
    if !(["modules", "entry", "limits"].contains key) then
      throw "package expression requires source-only modules and entry"
  for m in (← (← field spec "modules").getArr?) do
    for (key, _) in (← pairs m) do
      if !(["name", "source"].contains key) then throw "unsupported source module field"
    discard (str m "name")
    discard (str m "source")
  discard (str spec "entry")
  -- This optional spelling supports the existing source-package descriptor;
  -- it never selects fresh execution or compilation resources.
  match (field spec "limits").toOption with
  | some limits =>
    if limits != Delvetalk.Package.defaultLimits then throw "package compilation limits are fixed"
  | none => pure ()
  put spec "limits" Delvetalk.Package.defaultLimits

/-- Reuse only an artifact computed from this exact normalized source descriptor
inside this evaluation run. No current law, state or source result is retained. -/
def compileSource (spec : Json) : Evaluation Json := do
  Evaluation.checkedArtifact "delvetalk-objective-bend-source-v1" Delvetalk.Package.compile (← sourceSpec spec)

-- A command owns one pure source execution. The envelope is deliberately small:
-- whole-state replacement plus a result, or explicit refusal. Opt-in profiles
-- add bounded retained emissions; law-held contracts separately govern state.
def transitionPackage (protocol transition : Json) : Except String Json := do
  for (key, _) in (← pairs transition) do
    if !(["package", "profile", "inputCodec", "resultCodec", "messages"].contains key) then
      throw "unsupported source transition field"
  let profile ← str transition "profile"
  if profile != "delvetalk-source-transition" then throw "unknown source transition profile"
  Messages.validateCapabilities transition
  for key in ["inputCodec", "resultCodec"] do
    if let some codec := (field transition key).toOption then
      let name ← codec.getStr?
      if name != "value" && !(key == "inputCodec" && (["data", "compact"].contains name)) then
        throw "unknown source data codec"
  sourceSpec (← SourcePackages.resolve protocol (← field transition "package"))

def validateTransition (protocol transition : Json) : Evaluation Unit := do
  discard (compileSource (← transitionPackage protocol transition))

-- Internal typed envelopes use the source adapter's 8 MiB frame ceiling.
-- Preparation.Value adds recursive record/sum wrappers to ordinary JSON; this
-- bounds the consumed representation separately from the 1 MiB extracted
-- result and unchanged 1 MiB mutating-world request boundary.
def typedInputEnvelopeBytes : Nat := 8 * 1024 * 1024

/-- A compact physical command input pins its exact checked schema. This is an
integrity/type identity, not a grant; current law still owns admission. -/
def compactInputValue (artifact input : Json) : Except String Json := do
  let keys := (← pairs input).map Prod.fst
  unless keys == ["schemaPacketSha256", "value"] do
    throw "compact input requires exactly schemaPacketSha256 and value"
  unless (← str input "schemaPacketSha256") == (← str artifact "packetSha256") do
    throw "compact input schema differs from selected current packet"
  field input "value"

def canonicalState (o : Json) : Evaluation Json := do
  let state ← field o "state"
  let keys := (← pairs state).map Prod.fst
  unless keys == ["model"] do throw "typed source state requires exactly model"
  let data ← SourceState.readWith compileSource (← field o "protocol") (← field state "model")
  return obj [("model", Minidregg.Compiler.ObjectiveBendDataWire.dataJson data)]

def prepareInvocation (o request : Json) (derived : Option World.NativeResult) : Evaluation Json := do
  let protocol ← field o "protocol"
  let command ← field (← field protocol "commands") (← str request "command")
  let some transition := sourceTransition? command | throw "source command requires current transition"
  let selected ← SourceState.resolveWith compileSource protocol (← field transition "package") (.arr #[.str "codomain", .str "domain"])
  let data ← match derived with
    | some produced =>
      Delvetalk.PackageData.shape produced.assumptions 256 [] produced.type
      unless (← Delvetalk.PackageData.equivalent produced.assumptions selected.assumptions 256 [] produced.type selected.type) do
        throw "derived source result type differs from recipient input"
      pure produced.value
    | none =>
      let input ← field request "input"
      match (str transition "inputCodec").toOption with
      | some "compact" =>
        let wire ← compactInputValue selected.artifact input
        Delvetalk.PackageData.decodeCompact selected.assumptions 256 selected.type wire
      | some "data" => Delvetalk.PackageData.decode 256 input
      | some "value" => Preparation.encodeValue 64 input
      | none =>
        let (data, nodes) ← Delvetalk.Package.jsonData 64 input
        charge nodes
        pure data
      | _ => throw "unknown source data codec"
  Delvetalk.PackageData.validate selected.assumptions 256 data selected.type
  put request "input" (Minidregg.Compiler.ObjectiveBendDataWire.dataJson data)

def frameDerivedInput (o : Json) (command : String) (produced : World.NativeResult) : Evaluation Json := do
  let protocol ← field o "protocol"
  let descriptor ← field (← field (← field protocol "commands") command) "transition"
  let selected ← SourceState.resolveWith compileSource protocol (← field descriptor "package") (.arr #[.str "codomain", .str "domain"])
  Delvetalk.PackageData.shape produced.assumptions 256 [] produced.type
  unless (← Delvetalk.PackageData.equivalent produced.assumptions selected.assumptions 256 [] produced.type selected.type) do
    throw "derived source result type differs from recipient input"
  Delvetalk.PackageData.validate selected.assumptions 256 produced.value selected.type
  match (str descriptor "inputCodec").toOption with
  | some "compact" =>
    let value ← Delvetalk.PackageData.encodeCompact selected.assumptions 256 selected.type produced.value
    return obj [("schemaPacketSha256", ← field selected.artifact "packetSha256"), ("value", value)]
  | some "data" => return Minidregg.Compiler.ObjectiveBendDataWire.dataJson produced.value
  | some "value" => Preparation.decodeValue Preparation.retainedValueDepth produced.value
  | none =>
    let (value, nodes) ← Delvetalk.Package.dataPlain 64 produced.value
    charge nodes
    return value
  | _ => throw "unknown source data codec"

def initializeAllocation (protocol : Json) (produced : World.NativeResult) : Evaluation Json := do
  let (descriptor, path) ← SourceState.initialSchema protocol
  let selected ← SourceState.resolveWith compileSource protocol descriptor path
  Delvetalk.PackageData.shape produced.assumptions 256 [] produced.type
  unless (← Delvetalk.PackageData.equivalent produced.assumptions selected.assumptions 256 [] produced.type selected.type) do
    throw "allocation initial type differs from child state"
  Delvetalk.PackageData.validate selected.assumptions 256 produced.value selected.type
  return obj [("model", ← SourceState.writeWith compileSource protocol descriptor path produced.value)]

def executeDataPackage (spec : Json) (arguments : Array Json) :
    Evaluation Minidregg.Theory.ObjectiveBendDemandData.Data := do
  let artifact ← compileSource spec
  let remaining ← get
  let execution ← Delvetalk.Package.executeDataValue (← field artifact "packet") (.arr arguments)
    (obj [("ticks", toJson remaining), ("heap", toJson (100000 : Nat)),
          ("stack", toJson (10000 : Nat)), ("nodes", toJson (100000 : Nat)),
          ("inputBytes", toJson typedInputEnvelopeBytes),
          ("bytes", toJson (1048576 : Nat))])
  charge (execution.usage.ticksUsed + execution.usage.conversionNodes)
  match execution with
  | .finished value _ _ _ => pure value
  | .refused failure _ => throw ("typed package execution refused: " ++ failure)

def executeDataTransition (context : World.CallContext) (protocol transition spec state input identity : Json) :
    Evaluation World.TransitionResult := do
  let receiving := Messages.receives transition
  let emitting := Messages.emits transition
  if (← pairs state).map Prod.fst != ["model"] then
    throw "typed source state requires exactly model"
  let inputData ← Delvetalk.PackageData.decode 256 input
  let (identityData, identityNodes) ← Delvetalk.Package.jsonData 64 identity
  charge identityNodes
  let stateData ← SourceState.readWith compileSource protocol (← field state "model")
  let mut arguments := #[stateData, inputData, identityData]
  let mut physicalArguments := #[← field state "model", context.physicalInput.getD input,
    Minidregg.Compiler.ObjectiveBendDataWire.dataJson identityData]
  if receiving then
    let some facts := context.eventFacts | throw "receive-only command requires authenticated event delivery"
    let (data, nodes) ← Delvetalk.Package.jsonData 64 facts
    charge nodes
    arguments := arguments.push data
    physicalArguments := physicalArguments.push (Minidregg.Compiler.ObjectiveBendDataWire.dataJson data)
  else if context.eventFacts.isSome then throw "delivery requires a receive-only command"
  -- Stay inside the native boundary: the package has already materialized and
  -- checked the complete result. Encoding it as typed wire merely to decode it
  -- again duplicates traversal, allocation and budget charge for every field.
  let artifact ← compileSource spec
  let physicalBytes := (Json.arr physicalArguments).compress.utf8ByteSize
  let remaining ← get
  let execution ← Delvetalk.Package.executeDataValuesSized (← field artifact "packet") arguments physicalBytes
    (obj [("ticks", toJson remaining), ("heap", toJson (100000 : Nat)),
      ("stack", toJson (10000 : Nat)), ("nodes", toJson (100000 : Nat)),
      ("bytes", toJson (1048576 : Nat)), ("inputBytes", toJson typedInputEnvelopeBytes)])
  charge (execution.usage.ticksUsed + execution.usage.conversionNodes)
  let (decision, decisionType) ← match execution with
    | .finished value type _ _ => pure (value, type)
    | .refused failure _ => throw ("typed package execution refused: " ++ failure)
  let .record fields := decision | throw "typed source decision must be a record"
  let keys := fields.map Prod.fst
  let expected := ["accepted", "reason", "state", "result"] ++
    (if emitting then ["emissions"] else []) ++
    (if (fields.lookup "allocations").isSome then ["allocations"] else [])
  if keys.length != expected.length || !(expected.all keys.contains) then
    throw "typed source decision has unsupported fields"
  let getField (key : String) : Evaluation Minidregg.Theory.ObjectiveBendDemandData.Data := do
    match fields.lookup key with
    | some value => pure value
    | none => throw "typed source decision field missing"
  let .boolean accepted ← getField "accepted" | throw "typed source accepted must be Bool"
  let .label reason ← getField "reason" | throw "typed source reason must be String"
  let nextState ← getField "state"
  let .record _ := nextState | throw "typed source state must have a record root"
  let result ← if (field transition "resultCodec").isOk then
    Preparation.decodeValue 64 (← getField "result")
  else do
    let (value, nodes) ← Delvetalk.Package.dataPlain 64 (← getField "result")
    charge nodes
    pure value
  if !accepted then
    if reason.isEmpty then throw "source refusal requires a reason"
    throw ("source refused: " ++ reason)
  if !reason.isEmpty then throw "accepted source transition must have empty reason"
  let emissions ← if emitting then do
    let descriptors ← Preparation.list (Messages.maxFanout + 1) (← getField "emissions")
    descriptors.toArray.mapM fun value => do
      tick
      Preparation.exact value ["to", "command", "recipientProgram", "payload"]
      let destination ← Preparation.text (← Preparation.member value "to")
      let command ← Preparation.text (← Preparation.member value "command")
      let program ← Preparation.text (← Preparation.member value "recipientProgram")
      let payload ← Preparation.decodeValue 64 (← Preparation.member value "payload")
      pure (obj [("to", .str destination), ("command", .str command),
        ("recipientProgram", .str program), ("payload", payload)])
  else pure #[]
  let packet ← Minidregg.Theory.ObjectiveBendTyping.decodePacket (← field artifact "packet")
  let allocations ← match fields.lookup "allocations" with
    | none => pure #[]
    | some values => do
      let allocationType ← Delvetalk.PackageData.select packet.source.assumptions decisionType
        (.arr #[obj [("field", .str "allocations")]])
      let descriptors ← Delvetalk.PackageData.allocationElements packet.source.assumptions allocationType values 32
      descriptors.toArray.mapM fun (value, leafType) => do
        tick
        let .record row := value | throw "allocation descriptor must be a record"
        let configured := (row.lookup "initial").isSome
        Preparation.exact value (if configured then ["name", "protocol", "law", "initial"] else ["name", "protocol", "law"])
        let name ← Preparation.text (← Preparation.member value "name")
        let childProtocol ← Preparation.decodeValue 64 (← Preparation.member value "protocol")
        let authority ← Preparation.decodeValue 64 (← Preparation.member value "law")
        let initial ← match row.lookup "initial" with
          | none => pure none
          | some data => do
            let initialType ← Delvetalk.PackageData.select packet.source.assumptions leafType
              (.arr #[obj [("field", .str "initial")]])
            pure (some (World.NativeResult.mk data packet.source.assumptions initialType))
        return World.Allocation.mk
          (obj [("name", .str name), ("protocol", childProtocol), ("law", authority)]) initial
  let statePath := Json.arr ((Array.replicate (if receiving then 4 else 3) (.str "codomain")).push (obj [("field", .str "state")]))
  let model ← SourceState.writeWith compileSource protocol (← field transition "package") statePath nextState
  let resultType ← Delvetalk.PackageData.select packet.source.assumptions decisionType (.arr #[obj [("field", .str "result")]])
  let resultValue ← getField "result"
  return World.TransitionResult.mk (obj [("model", model)]) result
    (some ⟨resultValue, packet.source.assumptions, resultType⟩) emissions allocations

def executeTransition (context : World.CallContext) (state input : Json)
    (principal : String) (transition : Json) : Evaluation World.TransitionResult := do
  let spec ← transitionPackage context.protocol transition
  let identity := obj [("object", .str context.object), ("principal", .str principal),
    ("inputOrigin", context.inputOrigin)]
  executeDataTransition context context.protocol transition spec state input identity

def reprogramResult (id : String) (root : Json) : Evaluation Json := do
  let program ← field root "protocol"
  let digest ← ProgramDigest.digest program
  return obj [("object", .str id), ("version", ← field root "version"),
    ("program", .str digest)]

def checkSourceContract (contract candidate : Json) (checkMethods : Bool) : Evaluation Unit :=
  SourceContract.check compileSource
    contract candidate checkMethods

def checkSourceAmendment (amendment before after request : Json) (principal : String) : Evaluation Unit :=
  SourceAmendment.check (fun package arguments => do
    executeDataPackage (← sourceSpec package) arguments)
    amendment before after request principal

def checkSourcePolicy (policy facts : Json) : Evaluation Unit :=
  SourcePolicy.check (fun package arguments => do executeDataPackage (← sourceSpec package) arguments) policy facts

def runtime : World.Runtime := {
  prepareInvocation := prepareInvocation
  canonicalState := canonicalState
  frameDerivedInput := frameDerivedInput
  initializeAllocation := initializeAllocation
  recodeState := fun o protocol state => do SourceState.recodeWith compileSource (← field o "protocol") protocol state
  budget := 100000,
  validateTransition := validateTransition, executeTransition := executeTransition,
  checkSourceContract := checkSourceContract,
  checkSourceAmendment := checkSourceAmendment,
  checkSourcePolicy := checkSourcePolicy,
  stageMessages := Messages.stage, reprogramResult := reprogramResult,
  programIdentity := ProgramDigest.digest }

def transition (world request : Json) (principal : String) : Except String (Json × Json) := do
  match (← str request "op") with
  | "messages-init" => Messages.initializeRegistry world request
  | "deliver" => Messages.deliverWith runtime world request principal
  | "settle-message" => Messages.settleWith runtime world request principal
  | _ => Transactions.transitionWith runtime world request principal

def handle (world request : Json) : Except String (Json × Json) := do
  if (← str request "op") == "catalogue-page" then
    return (world, ← World.cataloguePage world request (← (← field world "receipts").getArr?).size .null)
  if (← str request "op") == "capture-roots" then
    return (world, ← RetainedRoots.capture (RetainedRoots.fromWorld world) world request)
  if (← str request "op") == "retained-root" then
    return (world, ← RetainedRoots.mint (RetainedRoots.fromWorld world) request)
  if (← str request "op") == "prepare-retained" then
    let captured ← put request "op" (.str "prepare")
    return (world, ← RetainedRoots.prepareCaptured (RetainedRoots.fromWorld world) world
      (fun index currentObjects world request =>
        Preparation.run world request (RetainedRoots.reference index) (some currentObjects)) captured)
  if (← str request "op") == "source-state" then
    return (world, ← SourceState.inspect request)
  if (← str request "op") == "value-codec" then
    return (world, ← Preparation.codec request)
  if (← str request "op") == "prepare" then
    return (world, ← Preparation.run world request)
  if ["messages-pending", "message-event"].contains (← str request "op") then
    return (world, ← Messages.query world request)
  RetainedRoots.handleWith transition world request

def job (j : Json) : Json := World.jobWith handle j

def projectSource (protocol selector : Json) (arguments : Array Json) : Except String Json := do
  let execution : Evaluation Json := do
    let spec ← sourceSpec (← SourcePackages.resolve protocol selector)
    return Minidregg.Compiler.ObjectiveBendDataWire.dataJson (← executeDataPackage spec arguments)
  let (result, _) ← execution.run runtime.budget
  return result
end Compiled

def main (args : List String) : IO Unit :=
  if args == ["--project-source"] then SourceProjection.main Compiled.projectSource
  else if args == ["--resident"] then ResidentStore.serve Compiled.transition Messages.query
    (fun index currentObjects world request =>
        Preparation.run world request (RetainedRoots.reference index) (some currentObjects))
  else FileCustody.mainWith Compiled.handle Compiled.job args
