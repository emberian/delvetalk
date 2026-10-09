/- Opt-in source package and hash expressions. All admission is shared with the
   default hosts; only this executable selects the extensions and larger budget. -/
import TransactionsCore
import MessagesCore
import FileCustody
import ResidentStore
import SourcePackages
import SourceContract
import Delvetalk.Package
open Lean World

namespace Compiled

def charge (amount : Nat) : Evaluation Unit := do
  let remaining ← get
  if amount > remaining then throw "invocation budget exhausted"
  set (remaining - amount)

-- The digest wire is compact sorted-key JSON with exact natural numbers and
-- UTF-8 strings. Validation excludes JSON values with ambiguous number spelling.
def quoteString (s : String) : String :=
  "\"" ++ s.foldl (fun acc c => acc ++ match c with
    | '"' => "\\\""
    | '\\' => "\\\\"
    | '\x08' => "\\b"
    | '\t' => "\\t"
    | '\n' => "\\n"
    | '\x0c' => "\\f"
    | '\r' => "\\r"
    | _ => if c.toNat < 32 then
        "\\u00" ++ String.singleton (Nat.digitChar (c.toNat / 16)) ++
          String.singleton (Nat.digitChar (c.toNat % 16))
      else String.singleton c) "" ++ "\""

def canonicalData (depth : Nat) (value : Json) : Evaluation String := do
  tick
  match depth with
  | 0 => throw "hash data depth exceeded"
  | depth + 1 => match value with
    | .num _ => return toString (← value.getNat?)
    | .str s => return quoteString s
    | .bool b => return if b then "true" else "false"
    | .arr items => return "[" ++ String.intercalate "," (← items.toList.mapM (canonicalData depth)) ++ "]"
    | .obj _ =>
      let entries ← (← pairs value).mapM fun (key, child) => do
        return quoteString key ++ ":" ++ (← canonicalData depth child)
      return "{" ++ String.intercalate "," entries ++ "}"
    | _ => throw "hash data requires Nat, Bool, String, arrays or records"

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

def validateExtra (protocol expr : Json) (validate : Json → Except String Unit) : Except String Unit := do
  let args ← expr.getArr?
  let tag ← args[0]!.getStr?
  match tag with
  | "object" =>
    if args.size != 1 then throw "object expression arity"
  | "package" | "package-data-v1" =>
    if args.size != 3 then throw "package expression arity"
    discard (Delvetalk.Package.compile (← sourceSpec (← SourcePackages.resolve protocol args[1]!)))
    for argument in (← args[2]!.getArr?) do validate argument
  | "sha256" | "sha256-valid" | "program-digest" =>
    if args.size != 2 then throw "hash expression arity"
    validate args[1]!
  | _ => throw "unknown expression"

def evaluateExtra (context : World.CallContext) (expr : Json) (evaluate : Json → Evaluation Json) : Evaluation Json := do
  let args ← expr.getArr?
  let tag ← args[0]!.getStr?
  match tag with
  | "object" =>
    if args.size != 1 then throw "object expression arity"
    return .str context.object
  | "package" =>
    if args.size != 3 then throw "package expression arity"
    let spec ← sourceSpec (← SourcePackages.resolve context.protocol args[1]!)
    let values ← (← args[2]!.getArr?).mapM evaluate
    -- Recompilation binds execution to the exact stored source. The caller
    -- cannot replace a packet independently from its claimed source.
    let artifact ← Delvetalk.Package.compile spec
    let remaining ← get
    let result ← Delvetalk.Package.executeJsonPacket (← field artifact "packet") (.arr values)
      (obj [("ticks", toJson remaining), ("heap", toJson (100000 : Nat)),
            ("stack", toJson (10000 : Nat)), ("nodes", toJson (100000 : Nat)),
            ("bytes", toJson (1048576 : Nat))])
    charge (← (← field result "ticksUsed").getNat?)
    if (← str result "status") != "finished" then
      throw ("package execution refused: " ++ (← str result "failure"))
    charge (← (← field result "conversionNodes").getNat?)
    field result "value"
  | "package-data-v1" =>
    if args.size != 3 then throw "typed package expression arity"
    let spec ← sourceSpec (← SourcePackages.resolve context.protocol args[1]!)
    let values ← (← args[2]!.getArr?).mapM evaluate
    let artifact ← Delvetalk.Package.compile spec
    let remaining ← get
    let result ← Delvetalk.Package.executeDataPacket (← field artifact "packet") (.arr values)
      (obj [("ticks", toJson remaining), ("heap", toJson (100000 : Nat)),
            ("stack", toJson (10000 : Nat)), ("nodes", toJson (100000 : Nat)),
            ("bytes", toJson (1048576 : Nat))])
    if (← str result "executionProfile") != "delvetalk-package-data-v1" then
      throw "typed package execution profile mismatch"
    charge ((← (← field result "ticksUsed").getNat?) +
      (← (← field result "conversionNodes").getNat?))
    if (← str result "status") != "finished" then
      throw ("typed package execution refused: " ++ (← str result "failure"))
    field result "value"
  | "program-digest" =>
    if args.size != 2 then throw "program digest expression arity"
    let value ← evaluate args[1]!
    charge (FileCustody.encode value).utf8ByteSize
    return .str (Messages.digest value)
  | "sha256" =>
    if args.size != 2 then throw "hash expression arity"
    let bytes ← canonicalData 64 (← evaluate args[1]!)
    charge bytes.utf8ByteSize
    return .str (Minidregg.Compiler.Sha256.hexString bytes)
  | "sha256-valid" =>
    if args.size != 2 then throw "hash expression arity"
    let value ← evaluate args[1]!
    match value.getStr? with
    | .error _ => return .bool false
    | .ok s =>
      charge s.utf8ByteSize
      return .bool (s.length == 64 && s.toList.all (fun c =>
        (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
  | _ => throw "unknown expression"

-- A command owns one pure source execution. The envelope is deliberately small:
-- whole-state replacement plus a result, or explicit refusal. Opt-in profiles
-- add bounded retained emissions; law-held contracts separately govern state.
def transitionPackage (protocol transition : Json) : Except String Json := do
  if (← pairs transition).map Prod.fst != ["package", "profile"] then
    throw "source transition requires exactly profile and package"
  if !(["delvetalk-source-transition-v1", "delvetalk-source-transition-v2",
      "delvetalk-source-data-transition-v1", Messages.effectsProfile,
      Messages.receiveProfile, Messages.dataEffectsProfile, Messages.dataReceiveProfile].contains (← str transition "profile")) then
    throw "unknown source transition profile"
  sourceSpec (← SourcePackages.resolve protocol (← field transition "package"))

def validateTransition (protocol transition : Json) : Except String Unit := do
  discard (Delvetalk.Package.compile (← transitionPackage protocol transition))

def executeDataTransition (context : World.CallContext) (profile : String) (spec state input identity : Json) :
    Evaluation (Json × Json × Array Json) := do
  if (← pairs state).map Prod.fst != ["model"] then
    throw "typed source state requires exactly model"
  let (inputData, inputNodes) ← Delvetalk.Package.jsonData 64 input
  let (identityData, identityNodes) ← Delvetalk.Package.jsonData 64 identity
  charge (inputNodes + identityNodes)
  let mut arguments := #[← field state "model",
    Minidregg.Compiler.ObjectiveBendDataWire.dataJson inputData,
    Minidregg.Compiler.ObjectiveBendDataWire.dataJson identityData]
  if Messages.isReceive profile then
    let some facts := context.eventFacts | throw "receive-only command requires authenticated event delivery"
    let (data, nodes) ← Delvetalk.Package.jsonData 64 facts
    charge nodes
    arguments := arguments.push (Minidregg.Compiler.ObjectiveBendDataWire.dataJson data)
  else if context.eventFacts.isSome then throw "delivery requires a receive-only command"
  let decisionWire ← evaluateExtra context
    (.arr #[.str "package-data-v1", spec, .arr arguments]) pure
  -- Decoding the returned envelope traverses the complete retained state and
  -- result under the SAME remaining budget. No branch gets fresh fuel.
  let decision ← Delvetalk.PackageData.decode 256 decisionWire
  let .record fields := decision | throw "typed source decision must be a record"
  let keys := fields.map Prod.fst
  let expected := ["accepted", "reason", "state", "result"] ++
    if Messages.isEffects profile then ["emissions"] else []
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
  let (result, resultNodes) ← Delvetalk.Package.dataPlain 64 (← getField "result")
  charge resultNodes
  if !accepted then
    if reason.isEmpty then throw "source refusal requires a reason"
    throw ("source refused: " ++ reason)
  if !reason.isEmpty then throw "accepted source transition must have empty reason"
  let emissions ← if Messages.isEffects profile then do
    let (slots, nodes) ← Delvetalk.Package.dataPlain 64 (← getField "emissions")
    charge nodes
    Messages.exact slots ["a", "b", "c", "d"] "source emissions"
    ["a", "b", "c", "d"].toArray.mapM (fun key => do field slots key)
  else pure #[]
  return (obj [("model", Minidregg.Compiler.ObjectiveBendDataWire.dataJson nextState)], result, emissions)

def executeTransition (context : World.CallContext) (state input : Json)
    (principal : String) (transition : Json) : Evaluation (Json × Json × Array Json) := do
  let spec ← transitionPackage context.protocol transition
  let identity := obj ([("object", .str context.object), ("principal", .str principal)] ++
    if (← str transition "profile") == "delvetalk-source-transition-v1" then []
    else [("inputOrigin", context.inputOrigin)])
  let profile ← str transition "profile"
  if ["delvetalk-source-data-transition-v1", Messages.dataEffectsProfile,
      Messages.dataReceiveProfile].contains profile then
    return ← executeDataTransition context profile spec state input identity
  -- This is the same package evaluator and shared budget as ordinary compiled
  -- expressions. It compiles the retained source and invokes the entry once.
  let arguments ← if Messages.isReceive profile then do
    let some facts := context.eventFacts | throw "receive-only command requires authenticated event delivery"
    pure #[state, input, identity, facts]
  else do
    if context.eventFacts.isSome then throw "delivery requires a receive-only command"
    pure #[state, input, identity]
  let decision ← evaluateExtra context (.arr #[.str "package", spec, .arr arguments]) pure
  let fields := ["accepted", "reason", "result", "state"] ++
    if Messages.isEffects profile then ["emissions"] else []
  Messages.exact decision fields "source transition result"
  let accepted ← (← field decision "accepted").getBool?
  let reason ← str decision "reason"
  if !accepted then
    if reason.isEmpty then throw "source refusal requires a reason"
    throw ("source refused: " ++ reason)
  if !reason.isEmpty then throw "accepted source transition must have empty reason"
  let nextState ← field decision "state"
  discard (pairs nextState)
  let emissions ← if Messages.isEffects profile then do
    let slots ← field decision "emissions"
    Messages.exact slots ["a", "b", "c", "d"] "source emissions"
    ["a", "b", "c", "d"].toArray.mapM (fun key => do field slots key)
  else pure #[]
  return (nextState, ← field decision "result", emissions)

def reprogramResult (id : String) (root : Json) : Evaluation Json := do
  let program ← field root "protocol"
  charge (FileCustody.encode program).utf8ByteSize
  return obj [("object", .str id), ("version", ← field root "version"),
    ("program", .str (Messages.digest program))]

def checkSourceContract (contract candidate : Json) (checkMethods : Bool) : Evaluation Unit :=
  SourceContract.check (fun spec => do Delvetalk.Package.compile (← sourceSpec spec))
    contract candidate checkMethods

def runtime : World.Runtime := {
  budget := 100000, validateExtra := validateExtra, evaluateExtra := evaluateExtra,
  validateTransition := validateTransition, executeTransition := executeTransition,
  checkSourceContract := checkSourceContract,
  stageMessages := Messages.stage, reprogramResult := reprogramResult }

def transition (world request : Json) (principal : String) : Except String (Json × Json) := do
  match (← str request "op") with
  | "messages-init" => Messages.initializeRegistry world request
  | "deliver" => Messages.deliverWith runtime world request principal
  | _ => Transactions.transitionWith runtime world request principal

def handle (world request : Json) : Except String (Json × Json) := do
  if ["messages-pending", "message-event"].contains (← str request "op") then
    return (world, ← Messages.query world request)
  World.handleWith transition world request

def job (j : Json) : Json := World.jobWith handle j
end Compiled

def main (args : List String) : IO Unit :=
  if args == ["--resident"] then ResidentStore.serve Compiled.transition Messages.query
  else FileCustody.mainWith Compiled.handle Compiled.job args
