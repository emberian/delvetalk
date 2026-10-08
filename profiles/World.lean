/- Local durable host fixture profile. Distinct from the Objective Bend kernel.
   Lean owns protocol evaluation, exact roots, current authority and receipts.
   Python owns only locking, process transport and atomic file replacement. -/
import Delvetalk.Core
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
  let xs ← pairs j
  return obj ((xs.filter (fun p => p.1 != k)) ++ [(k,v)])

def empty : Json := obj [("objects", obj []), ("receipts", .arr #[])]

abbrev BendTerm := Minidregg.Theory.ObjectiveBendOpenRecursion.Term
abbrev Evaluation := StateT Nat (Except String)

def tick : Evaluation Unit := do
  let remaining ← get
  if remaining == 0 then throw "invocation budget exhausted"
  set (remaining - 1)

def toTerm (depth : Nat) (value : Json) : Evaluation BendTerm := do
  tick
  match depth with
  | 0 => throw "Bend argument depth exceeded"
  | depth + 1 => match value with
    | .str s => return .label s
    | .bool b => return .boolean b
    | .num _ => return .nat (← value.getNat?)
    | .obj _ => return .record (← (← pairs value).mapM fun (k,v) => do
        return (k, ← toTerm depth v))
    | _ => throw "Bend boundary accepts only Nat, Bool, String and records"

partial def normalize (term : BendTerm) : Evaluation BendTerm := do
  tick
  match Delvetalk.inspect term with
  | .value _ => return term
  | .step next _ => normalize next
  | .yield _ _ _ => throw "Bend effects are forbidden in pure protocol expressions"
  | .stuck => throw "Bend expression stuck"

def materialize (depth : Nat) (term : BendTerm) : Evaluation Json := do
  match depth with
  | 0 => throw "Bend result depth exceeded"
  | depth + 1 => match (← normalize term) with
    | .nat n => return toJson n
    | .boolean b => return .bool b
    | .label s => return .str s
    | .record fs =>
      if (fs.map Prod.fst).eraseDups.length != fs.length then
        throw "Bend result has duplicate record labels"
      return obj (← fs.mapM fun (k,v) => do return (k, ← materialize depth v))
    | _ => throw "Bend result must be Nat, Bool, String or record"

def evaluate (depth : Nat) (state input : Json) (principal : String) (expr : Json) : Evaluation Json := do
  tick
  match depth with
  | 0 => throw "expression depth exceeded"
  | depth + 1 =>
    let a ← expr.getArr?
    let tag ← (a[0]?.toExcept "empty expression").bind Json.getStr?
    if tag == "principal" && a.size == 1 then return .str principal
    if tag == "bend" then
      if a.size != 3 then throw "Bend expression arity"
      let mut term ← Delvetalk.decode a[1]!
      for arg in (← a[2]!.getArr?) do
        let value ← evaluate depth state input principal arg
        term := .app term (← toTerm 64 value)
      return ← materialize 64 term
    if a.size != 2 then throw "expression arity"
    let arg := a[1]!
    match tag with
    | "literal" => return arg
    | "state" => field state (← arg.getStr?)
    | "input" => field input (← arg.getStr?)
    | "record" => return obj (← (← pairs arg).mapM fun (k,v) => do
        return (k, ← evaluate depth state input principal v))
    | "array" => return .arr (← (← arg.getArr?).mapM (evaluate depth state input principal))
    | _ => throw "unknown expression"

-- Reject malformed definitions at installation, including branches not yet used.
def validateExpr (fuel : Nat) (expr : Json) : Except String Unit := do
  match fuel with
  | 0 => throw "expression depth exceeded"
  | fuel + 1 =>
    let a ← expr.getArr?
    let tag ← (a[0]?.toExcept "empty expression").bind Json.getStr?
    if tag == "principal" && a.size == 1 then return
    if tag == "bend" then
      if a.size != 3 then throw "Bend expression arity"
      discard (Delvetalk.decode a[1]!)
      for e in (← a[2]!.getArr?) do validateExpr fuel e
      return
    if a.size != 2 then throw "expression arity"
    match tag with
    | "literal" => pure ()
    | "state" | "input" => discard a[1]!.getStr?
    | "record" => for (_,v) in (← pairs a[1]!) do validateExpr fuel v
    | "array" => for v in (← a[1]!.getArr?) do validateExpr fuel v
    | _ => throw "unknown expression"

def validateProtocol (p : Json) : Except String Unit := do
  if (← str p "profile") != "delvetalk-local-v1" then throw "unknown profile"
  discard (pairs (← field p "initial"))
  for (_,c) in (← pairs (← field p "commands")) do
    for requirement in (← (← field c "require").getArr?) do
      let r ← requirement.getArr?
      if r.size != 2 then throw "require expects two expressions"
      validateExpr 64 r[0]!
      validateExpr 64 r[1]!
    for (_,e) in (← pairs (← field c "set")) do validateExpr 64 e
    validateExpr 64 (← field c "result")
    for e in (← (← field c "outbox").getArr?) do validateExpr 64 e

def law (j : Json) : Except String (Array String) := do
  let xs ← j.getArr?
  xs.mapM Json.getStr?

def authorized (o : Json) (principal : String) : Except String Unit := do
  if !(← law (← field o "law")).contains principal then throw "unauthorized"

def rootCheck (o request : Json) : Except String Unit := do
  if o != (← field request "expected") then throw "stale read root"

def receipt (request : Json) (kind : String) (data : Json) : Json :=
  obj [("intent", (field request "intent").toOption.getD .null),
       ("object", (field request "object").toOption.getD .null),
       ("kind", .str kind), ("data", data)]

def transition (world request : Json) (principal : String) : Except String (Json × Json) := do
  let objects ← field world "objects"
  let id ← str request "object"
  if id.isEmpty then throw "empty object id"
  let op ← str request "op"
  if op == "create" then
    if (field objects id).isOk then throw "object exists"
    let protocol ← field request "protocol"
    validateProtocol protocol
    let authority ← field request "law"
    discard (law authority)
    let o := obj [("protocol", protocol), ("law", authority), ("version", toJson (0 : Nat)),
      ("state", ← field protocol "initial")]
    let next ← put world "objects" (← put objects id o)
    return (next, receipt request "committed" (obj [("root",o), ("result",.null), ("outbox", .arr #[])]))
  let o ← field objects id
  authorized o principal
  rootCheck o request
  let n ← (← field o "version").getNat?
  if op == "law" then
    let authority ← field request "law"
    discard (law authority)
    let nextObj ← put (← put o "law" authority) "version" (toJson (n+1))
    let next ← put world "objects" (← put objects id nextObj)
    return (next, receipt request "committed" (obj [("root",nextObj), ("result",.null), ("outbox", .arr #[])]))
  if op != "invoke" then throw "unknown operation"
  let protocol ← field o "protocol"
  let command ← field (← field protocol "commands") (← str request "command")
  let state ← field o "state"
  let input ← field request "input"
  discard (pairs input)
  let execution : Evaluation (Json × Json × Array Json) := do
    let eval := evaluate 64 state input principal
    for requirement in (← (← field command "require").getArr?) do
      let r ← requirement.getArr?
      if (← eval r[0]!) != (← eval r[1]!) then throw "precondition failed"
    let mut nextState := state
    for (k,e) in (← pairs (← field command "set")) do
      nextState ← put nextState k (← eval e)
    let result ← eval (← field command "result")
    let outbox ← (← (← field command "outbox").getArr?).mapM eval
    return (nextState, result, outbox)
  let ((nextState, result, outbox), _) ← execution.run 10000
  let nextObj ← put (← put o "state" nextState) "version" (toJson (n+1))
  let next ← put world "objects" (← put objects id nextObj)
  return (next, receipt request "committed" (obj [("root",nextObj), ("result",result), ("outbox", .arr outbox)]))

def handle (world request : Json) : Except String (Json × Json) := do
  if request.compress.utf8ByteSize > 65536 then throw "request exceeds 64 KiB"
  let principal ← str request "principal"
  if principal.isEmpty then throw "empty principal"
  if (← str request "op") == "inspect" then
    return (world, ← field (← field world "objects") (← str request "object"))
  let intent ← str request "intent"
  if intent.isEmpty then throw "empty intent"
  let receipts ← (← field world "receipts").getArr?
  for r in receipts do
    let prior ← field r "request"
    if (← str prior "principal") == principal && (← str prior "intent") == intent then
      if prior == request then return (world, ← field r "receipt")
      return (world, receipt request "refused" (.str "intent reused for different request"))
  let (next, outcome) := match transition world request principal with
    | .ok value => value
    | .error e => (world, receipt request "refused" (.str e))
  let next ← put next "receipts" (.arr (receipts.push (obj [("request",request), ("receipt",outcome)])))
  return (next,outcome)

def job (j : Json) : Json :=
  match do
    let world ← field j "world"
    let request ← field j "request"
    let (next, reply) ← handle world request
    pure (obj [("world",next), ("reply",reply)]) with
  | .ok result => result
  | .error e => obj [("error", .str e)]
end World

def main : IO Unit := do
  let stdin ← IO.getStdin
  let stdout ← IO.getStdout
  repeat
    let line ← stdin.getLine
    if line.isEmpty then break
    let out := if line.utf8ByteSize > 16777216 then
        World.obj [("error", .str "frame exceeds 16 MiB")]
      else match Lean.Json.parse line with
        | .ok j => World.job j
        | .error e => World.obj [("error", .str e)]
    stdout.putStrLn out.compress
