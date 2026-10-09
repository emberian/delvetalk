/- Opt-in source package and hash expressions. All admission is shared with the
   default hosts; only this executable selects the extensions and larger budget. -/
import TransactionsCore
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

def validateExtra (expr : Json) (validate : Json → Except String Unit) : Except String Unit := do
  let args ← expr.getArr?
  let tag ← args[0]!.getStr?
  match tag with
  | "object" =>
    if args.size != 1 then throw "object expression arity"
  | "package" =>
    if args.size != 3 then throw "package expression arity"
    discard (Delvetalk.Package.compile (← sourceSpec args[1]!))
    for argument in (← args[2]!.getArr?) do validate argument
  | "sha256" | "sha256-valid" =>
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
    let spec ← sourceSpec args[1]!
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
-- whole-state replacement plus a result, or explicit refusal; no effects or
-- allocation. Source types describe this call, not a host-wide state invariant.
def transitionPackage (transition : Json) : Except String Json := do
  if (← pairs transition).map Prod.fst != ["package", "profile"] then
    throw "source transition requires exactly profile and package"
  if (← str transition "profile") != "delvetalk-source-transition-v1" then
    throw "unknown source transition profile"
  sourceSpec (← field transition "package")

def validateTransition (transition : Json) : Except String Unit := do
  discard (Delvetalk.Package.compile (← transitionPackage transition))

def executeTransition (context : World.CallContext) (state input : Json)
    (principal : String) (transition : Json) : Evaluation (Json × Json × Array Json) := do
  let spec ← transitionPackage transition
  let identity := obj [("object", .str context.object), ("principal", .str principal)]
  -- This is the same package evaluator and shared budget as ordinary compiled
  -- expressions. It compiles the retained source and invokes the entry once.
  let decision ← evaluateExtra context
    (.arr #[.str "package", spec, .arr #[state, input, identity]]) pure
  if (← pairs decision).map Prod.fst != ["accepted", "reason", "result", "state"] then
    throw "source transition result requires exactly accepted, reason, state and result"
  let accepted ← (← field decision "accepted").getBool?
  let reason ← str decision "reason"
  if !accepted then
    if reason.isEmpty then throw "source refusal requires a reason"
    throw ("source refused: " ++ reason)
  if !reason.isEmpty then throw "accepted source transition must have empty reason"
  let nextState ← field decision "state"
  discard (pairs nextState)
  return (nextState, ← field decision "result", #[])

def runtime : World.Runtime := {
  budget := 100000, validateExtra := validateExtra, evaluateExtra := evaluateExtra,
  validateTransition := validateTransition, executeTransition := executeTransition }

def handle (world request : Json) : Except String (Json × Json) :=
  World.handleWith (Transactions.transitionWith runtime) world request

def job (j : Json) : Json := World.jobWith handle j
end Compiled

def main : IO Unit := World.serve Compiled.job
