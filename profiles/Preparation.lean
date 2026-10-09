/- Pure source preparation. The source constructs complete calls. This boundary
   serializes data, bounds work and binds reads to already captured observations.
   It neither substitutes input fields nor chooses a workflow. -/
import Delvetalk.Package
import Delvetalk.PackageData
import FileCustody
import MessagesCore
import SourcePackages

namespace Preparation
open Lean
open World
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Compiler.ObjectiveBendDataWire (dataJson)

abbrev Work := StateT Nat (Except String)
def spend : Work Unit := do
  let n ← get
  if n == 0 then throw "preparation data capacity"
  set (n - 1)
def member (value : Data) (name : String) : Except String Data :=
  match value with
  | .record fields => match fields.lookup name with
    | some value => pure value
    | none => throw ("preparation missing field: " ++ name)
  | _ => throw "preparation requires a record"
def exact (value : Data) (names : List String) : Except String Unit :=
  match value with
  | .record fields => unless fields.length == names.length && fields.all (fun p => names.contains p.1) do
      throw "preparation record has missing or unknown fields"
  | _ => throw "preparation requires a record"
def text (value : Data) : Except String String :=
  match value with
  | .label s => if s.utf8ByteSize > 65536 then throw "preparation text capacity" else pure s
  | _ => throw "preparation requires String"
def nat (value : Data) : Except String Nat :=
  match value with | .natural n => pure n | _ => throw "preparation requires Nat"
def rec (fields : List (String × Data)) : Data := .record fields
def var (name : String) (fields : List (String × Data)) : Data := .variant name (rec fields)

mutual
def encodeValue : Nat → Json → Work Data
  | 0, _ => throw "preparation value nesting capacity"
  | n + 1, value => do
    spend
    match value with
    | .null => pure (var "none" [])
    | .bool b => pure (var "boolean" [("value", .boolean b)])
    | .str s => pure (var "text" [("value", .label s)])
    | .num number =>
      if number.exponent == 0 && number.mantissa >= 0 then
        pure (var "natural" [("value", .natural number.mantissa.toNat)])
      else pure (var "number" [("encoded", .label (FileCustody.encode value))])
    | .arr values => pure (var "array" [("values", ← encodeValues n values.toList)])
    | .obj values => pure (var "record" [("fields", ← encodeFields n values.toList)])
def encodeValues (depth : Nat) : List Json → Work Data
  | [] => pure (var "nil" [])
  | value :: tail => do
    spend
    pure (var "cons" [("head", ← encodeValue depth value), ("tail", ← encodeValues depth tail)])
def encodeFields (depth : Nat) : List (String × Json) → Work Data
  | [] => pure (var "nil" [])
  | (name, value) :: tail => do
    spend
    pure (var "cons" [("head", rec [("name", .label name), ("value", ← encodeValue depth value)]),
      ("tail", ← encodeFields depth tail)])
end

def list : Nat → Data → Except String (List Data)
  | 0, _ => throw "preparation list capacity"
  | n + 1, .variant "nil" payload => do exact payload []; pure []
  | n + 1, .variant "cons" payload => do
    exact payload ["head", "tail"]
    pure ((← member payload "head") :: (← list n (← member payload "tail")))
  | _, _ => throw "preparation requires a list"

def decodeValue : Nat → Data → Work Json
  | 0, _ => throw "preparation value nesting capacity"
  | n + 1, value => do
    spend
    match value with
    | .variant "none" payload => exact payload []; pure .null
    | .variant "boolean" payload =>
      exact payload ["value"]
      match ← member payload "value" with
      | .boolean b => pure (.bool b)
      | _ => throw "preparation requires Bool"
    | .variant "natural" payload =>
      exact payload ["value"]
      pure (toJson (← nat (← member payload "value")))
    | .variant "text" payload =>
      exact payload ["value"]
      pure (.str (← text (← member payload "value")))
    | .variant "number" payload =>
      exact payload ["encoded"]
      let value ← Json.parse (← text (← member payload "encoded"))
      match value with | .num _ => pure value | _ => throw "preparation number is not numeric"
    | .variant "array" payload =>
      exact payload ["values"]
      pure (.arr (← (← list 1025 (← member payload "values")).toArray.mapM (decodeValue n)))
    | .variant "record" payload =>
      exact payload ["fields"]
      let mut names : List String := []
      let mut fields := []
      for entry in (← list 1025 (← member payload "fields")) do
        spend
        exact entry ["name", "value"]
        let name ← text (← member entry "name")
        if names.contains name then throw "preparation duplicate JSON field"
        names := name :: names
        fields := fields ++ [(name, ← decodeValue n (← member entry "value"))]
      pure (obj fields)
    | _ => throw "unknown preparation Value variant"

def identity (value : Data) : Except String String := do
  let id ← text value
  if id.isEmpty || id.utf8ByteSize > 256 then throw "preparation requires a bounded object identity"
  return id

def effect (index : Nat) (value : Data) : Work Json := do
  spend
  let .variant kind payload := value | throw "preparation effect requires a variant"
  let target ← identity (← member payload "object")
  let base := [("object", .str target)]
  match kind with
  | "invoke" =>
    exact payload ["object", "command", "input"]
    let command ← identity (← member payload "command")
    let input ← decodeValue 64 (← member payload "input")
    discard input.getObj?
    return obj (base ++ [("command", .str command), ("input", input)])
  | "invokeResult" =>
    exact payload ["object", "command", "result"]
    let prior ← nat (← member payload "result")
    if prior >= index then throw "preparation result must precede its consumer"
    return obj (base ++ [("command", .str (← identity (← member payload "command"))), ("inputFrom", toJson prior)])
  | "observe" => exact payload ["object"]; return obj (("op", .str "observe") :: base)
  | "reprogramResult" =>
    exact payload ["object", "result"]
    let prior ← nat (← member payload "result")
    if prior >= index then throw "preparation result must precede its consumer"
    return obj (("op", .str "reprogram") :: base ++ [("inputFrom", toJson prior)])
  | "reprogram" =>
    exact payload ["object", "protocol", "state"]
    return obj (("op", .str "reprogram") :: base ++ [
      ("protocol", ← decodeValue 64 (← member payload "protocol")),
      ("state", ← decodeValue 64 (← member payload "state"))])
  | "law" =>
    exact payload ["object", "law"]
    return obj (("op", .str "law") :: base ++ [("law", ← decodeValue 64 (← member payload "law"))])
  | _ => throw "unknown preparation effect"

def bind (owner : String) (ownerRoot : Json) (observations : List (String × Json))
    (principal intent : String) (value : Data)
    (guard : String → Json → Except String Json := fun _ root => pure root) : Work Json := do
  let .variant kind payload := value | throw "preparation requires a result variant"
  match kind with
  | "question" =>
    exact payload ["message", "needs"]
    let names ← (← list 33 (← member payload "needs")).mapM (fun v => (identity v : Work String))
    return obj [("kind", .str "question"), ("message", .str (← text (← member payload "message"))),
      ("needs", toJson names)]
  | "refused" =>
    exact payload ["message"]
    return obj [("kind", .str "refused"), ("message", .str (← text (← member payload "message")))]
  | "ready" =>
    exact payload ["summary", "reads", "calls"]
    let mut reads := [(owner, ownerRoot)]
    let mut declared : List String := []
    for read in (← list 17 (← member payload "reads")) do
      spend
      let .variant readKind readPayload := read | throw "preparation read requires a variant"
      exact readPayload ["object"]
      let id ← identity (← member readPayload "object")
      if declared.contains id then throw "duplicate preparation read"
      declared := id :: declared
      let root ← match readKind with
        | "existing" => match observations.lookup id with
          | some root => pure root
          | none => throw ("preparation read was not observed: " ++ id)
        | "absent" =>
          if id == owner || (observations.lookup id).isSome then throw "preparation absence conflicts with observation"
          pure .null
        | _ => throw "unknown preparation read"
      if id == owner then
        if root != ownerRoot then throw "preparation owner read differs"
      else reads := reads ++ [(id, root)]
    if reads.length > 16 then throw "preparation complete read set capacity"
    let callsData ← list 33 (← member payload "calls")
    if callsData.isEmpty then throw "preparation requires at least one effect"
    let mut calls := #[]
    for call in callsData do
      let framed ← effect calls.size call
      let id ← str framed "object"
      match reads.lookup id with
      | none => throw "preparation effect has no declared read"
      | some _ => pure ()
      calls := calls.push framed
    let encodedReads ← reads.mapM fun (id, root) => do
      return (id, ← if root == .null then pure .null else guard id root)
    let request := obj [("op", .str "transaction"), ("principal", .str principal), ("intent", .str intent),
      ("reads", obj encodedReads), ("calls", .arr calls)]
    if (FileCustody.encode request).utf8ByteSize > World.maxRequestBytes then throw "prepared request exceeds native frame capacity"
    return obj [("kind", .str "ready"), ("summary", .str (← text (← member payload "summary"))),
      ("request", request)]
  | _ => throw "unknown preparation result"

def run (world request : Json)
    (guard : String → Json → Except String Json := fun _ root => pure root) : Except String Json := do
  let keys := (← pairs request).map Prod.fst
  if keys.length != 8 || !keys.all (["op", "object", "root", "entry", "contribution", "observations", "principal", "intent"].contains) then
    throw "prepare requires exact request fields"
  let owner ← str request "object"
  let principal ← str request "principal"
  let intent ← str request "intent"
  if principal.isEmpty || intent.isEmpty then throw "preparation requires principal and intent"
  let root ← field request "root"
  let objects ← field world "objects"
  if (← readObject objects owner principal) != root then throw "preparation owner root differs from captured inspection"
  let protocol ← field root "protocol"
  let hook ← field protocol "preparation"
  if (← str hook "profile") != "delvetalk-source-preparation-v1" then throw "unsupported preparation profile"
  let entry ← str request "entry"
  if entry.isEmpty || entry.utf8ByteSize > 128 then throw "preparation export name capacity"
  let descriptor := obj [("format", .str "delvetalk-source-package-ref-v1"),
    ("name", .str (← str hook "sourcePackage")), ("entry", .str entry)]
  let spec ← SourcePackages.resolve protocol descriptor
  let observationsJson ← (← field request "observations").getArr?
  if observationsJson.size > 16 then throw "preparation observation capacity"
  let mut observations := [(owner, root)]
  for observation in observationsJson do
    let keys := (← pairs observation).map Prod.fst
    if keys.length != 2 || !keys.all (["object", "root"].contains) then throw "preparation observation requires exact fields"
    let id ← str observation "object"
    let observed ← field observation "root"
    if (← readObject objects id principal) != observed then throw "preparation observation differs from captured inspection"
    if id == owner then
      if observed != root then throw "preparation owner observation differs"
    else
      if (observations.lookup id).isSome then throw "duplicate preparation observation"
      observations := observations ++ [(id, observed)]
  let ((args, captured), remaining) ← (do
    let contribution ← encodeValue 64 (← field request "contribution")
    let mut data := var "nil" []
    for (id, observed) in observations.reverse do
      spend
      let observation := rec [("object", .label id), ("version", .natural (← (← field observed "version").getNat?)),
        ("program", .label (Messages.digest (← field observed "protocol"))),
        ("state", ← encodeValue 64 (← field observed "state"))]
      data := var "cons" [("head", observation), ("tail", data)]
    let state ← field (← field root "state") "model"
    let args := #[state, dataJson contribution, dataJson data,
      dataJson (rec [("object", .label owner), ("principal", .label principal)])]
    pure (args, observations) : Work (Array Json × List (String × Json))).run 100000
  let artifact ← Delvetalk.Package.compile spec
  let result ← Delvetalk.Package.executeDataPacket (← field artifact "packet") (.arr args)
    (obj [("ticks", toJson remaining), ("heap", toJson (100000 : Nat)), ("stack", toJson (10000 : Nat)),
      ("nodes", toJson (100000 : Nat)), ("bytes", toJson (1048576 : Nat))])
  if (← str result "status") != "finished" then throw ("source preparation refused: " ++ (← str result "failure"))
  let used := (← (← field result "ticksUsed").getNat?) + (← (← field result "conversionNodes").getNat?)
  if used >= remaining then throw "source preparation work capacity"
  let (value, budget) ← (Delvetalk.PackageData.decode 256 (← field result "value")).run (remaining - used)
  let (reply, _) ← (bind owner root captured principal intent value guard).run budget
  return reply

-- Pure physical codec for custody clients. This operation neither reads objects
-- nor grants authority. It shares the exact Value bridge used by preparation
-- and typed source transitions; batches share one bounded conversion budget.
def codec (request : Json) : Except String Json := do
  let keys := (← pairs request).map Prod.fst
  if keys != ["direction", "op", "values"] then throw "Value codec requires exactly direction, op and values"
  let direction ← str request "direction"
  if !(["encode", "decode", "digest"].contains direction) then throw "unknown Value codec direction"
  if (FileCustody.encode request).utf8ByteSize > World.maxRequestBytes then throw "Value codec input capacity"
  let values ← (← field request "values").getArr?
  if values.size > 64 then throw "Value codec batch capacity"
  let action : Work (Array Json) := values.mapM fun value => do
    spend
    if direction == "encode" then
      return dataJson (← encodeValue 64 value)
    else if direction == "decode" then
      decodeValue 64 (← Delvetalk.PackageData.decode 256 value)
    else
      let size := (FileCustody.encode value).utf8ByteSize
      let remaining ← get
      if size > remaining then throw "Value digest capacity"
      set (remaining - size)
      return .str (Messages.digest value)
  let (converted, _) ← action.run 100000
  let status := if direction == "encode" then "encoded" else if direction == "decode" then "decoded" else "digested"
  return obj [("status", .str status), ("values", .arr converted)]

end Preparation
