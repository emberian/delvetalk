/- Pure reference evaluation of a closed core term, for conformance against the
   independent evaluators in impl/. The term is read in the evaluators' array
   wire (`["app", f, a]`, `["nat", "3"]`, ...). The demand machine runs it; the
   reply is the machine's weak-head result, as a shape, or a yielded Plan. -/
import Lean.Data.Json
import Theory.ObjectiveBendDemandData
import Compiler.ObjectiveBendDataWire
import Delvetalk.Turn

namespace Delvetalk.EvaluateTerm
open Lean (Json toJson)
open Delvetalk.Theory.ObjectiveBendOpenRecursion
open Delvetalk.Theory.ObjectiveBendDemandMachine
open Delvetalk.Theory.ObjectiveBendDemandData
open Delvetalk.Compiler.ObjectiveBendDataWire (dataJson)

def primitiveOfName : String → Except String Primitive
  | "add" => pure .add | "multiply" => pure .multiply | "equal" => pure .equal
  | "conjunction" => pure .conjunction | "labelEqual" => pure .labelEqual
  | "subtract" => pure .subtract | "divide" => pure .divide | "less" => pure .less
  | "lessEqual" => pure .lessEqual | "modulo" => pure .modulo
  | "textConcat" => pure .textConcat | "textTake" => pure .textTake | "textDrop" => pure .textDrop
  | "textSpan" => pure .textSpan | "textBreak" => pure .textBreak | "textHasAny" => pure .textHasAny
  | "textCanonicalCompare" => pure .textCanonicalCompare
  | other => throw s!"unknown primitive {other}"

def unaryOfName : String → Except String UnaryPrimitive
  | "natText" => pure .natText | "textLength" => pure .textLength | "sha256Text" => pure .sha256Text
  | other => throw s!"unknown unary primitive {other}"

def natOf (j : Json) : Except String Nat := do
  let text ← j.getStr?
  let some n := text.toNat? | throw "Nat must be a decimal string"
  return n

mutual
def termOf : Nat → Json → Except String Term
  | 0, _ => throw "term nesting capacity"
  | fuel + 1, j => do
    let items ← j.getArr?
    let tag ← (items[0]?.getD Json.null).getStr?
    let child := fun (i : Nat) => do termOf fuel (items[i]?.getD Json.null)
    match tag with
    | "bound" => return .bound (← (items[1]?.getD Json.null).getNat?)
    | "nat" => return .nat (← natOf (items[1]?.getD Json.null))
    | "boolean" => return .boolean (← (items[1]?.getD Json.null).getBool?)
    | "label" => return .label (← (items[1]?.getD Json.null).getStr?)
    | "lam" => return .lam (← child 1)
    | "app" => return .app (← child 1) (← child 2)
    | "mix" => return .mix (← child 1) (← child 2)
    | "fix" => return .fix (← child 1) (← child 2)
    | "specification" => return .specification (← child 1) (← child 2)
    | "prototype" => return .prototype (← child 1) (← child 2)
    | "reflect" => return .reflect (← child 1)
    | "metadata" => return .metadata (← child 1)
    | "project" => return .project (← child 1)
    | "perform" => return .perform (← child 1)
    | "done" => return .done (← child 1)
    | "toData" => return .toData (← child 1)
    | "textJoin" => return .textJoin (← child 1) (← child 2)
    | "relationCount" => return .relationCount (← child 1)
    | "relationLookup" => do
      let key ← (← (items[2]?.getD Json.null).getArr?).toList.mapM (·.getStr?)
      return .relationLookup (← child 1) key (← child 3)
    | "refuse" => return .refuse (← (items[1]?.getD Json.null).getStr?)
    | "unary" => return .unary (← unaryOfName (← (items[1]?.getD Json.null).getStr?)) (← child 2)
    | "binary" => return .binary (← primitiveOfName (← (items[1]?.getD Json.null).getStr?)) (← child 2) (← child 3)
    | "get" => return .get (← child 1) (← (items[2]?.getD Json.null).getStr?)
    | "inject" => return .inject (← (items[1]?.getD Json.null).getStr?) (← child 2)
    | "ifZero" => return .ifZero (← child 1) (← child 2) (← child 3)
    | "ifBool" => return .ifBool (← child 1) (← child 2) (← child 3)
    | "record" => return .record (← fieldsOf fuel (items[1]?.getD Json.null))
    | "extend" => return .extend (← child 1) (← fieldsOf fuel (items[2]?.getD Json.null))
    | "case" => return .case (← child 1) (← fieldsOf fuel (items[2]?.getD Json.null))
    | other => throw s!"unknown constructor {other}"
def fieldsOf : Nat → Json → Except String (List (String × Term))
  | 0, _ => throw "term nesting capacity"
  | fuel + 1, j => do
    (← j.getArr?).toList.mapM fun field => do
      let pair ← field.getArr?
      return ((← (pair[0]?.getD Json.null).getStr?), ← termOf fuel (pair[1]?.getD Json.null))
end

def shape (state : State) : RuntimeValue → Json
  | .natural n => Json.mkObj [("kind", toJson "nat"), ("value", toJson (toString n))]
  | .boolean b => Json.mkObj [("kind", toJson "boolean"), ("value", toJson b)]
  | .label s => Json.mkObj [("kind", toJson "label"), ("value", toJson s)]
  | .closure .. => Json.mkObj [("kind", toJson "lam")]
  | .record fields => Json.mkObj [("kind", toJson "record"), ("names", toJson (fields.map Prod.fst))]
  | .specification .. => Json.mkObj [("kind", toJson "specification")]
  | .prototype .. => Json.mkObj [("kind", toJson "prototype")]
  | .variant label _ => Json.mkObj [("kind", toJson "inject"), ("label", toJson label)]

/-- Run to a result, resuming each yielded Plan with the next response. With `stored`, the term
is applied to a state whose named relations are stored cells over the state's own rows, as a
turn's (`Turn.storeOfState`, the store's `bounded` fetch: rows, and keys for a lookup by the
declared key; KERNEL-HANDOFF §15), run by the hosted runner, and the reply names the rows it
forced and how far into each relation it looked (`reach`); the evaluators run the same term
applied to the state as a literal. -/
def evaluate (term : Term) (responses : List Term) (ticks : Nat)
    (stored : Option (List (String × Data) × Delvetalk.Turn.Store) := none) : Json :=
  let limits : Limits := ⟨1000000, 100000⟩
  let budget : Budget := ⟨1000000, 100000000, 16777216⟩
  let fetch : Fetch := match stored with
    | some (_, store) => store.bounded
    | none => Fetch.none
  let runBounded := fun (limits : Limits) (ticks : Nat) (state : State) => match stored with
    | some _ => (forceHostedWith (fun _ => true) fetch limits budget.bytes ticks state).1
    | none => Delvetalk.Theory.ObjectiveBendDemandMachine.runBounded limits ticks state
  let reads := fun (state : State) (reply : Json) => match stored with
    | some _ => (reply.setObjVal! "forced" (toJson ((forcedRows state).map fun (f, j) => [toJson f, toJson j])))
        |>.setObjVal! "reach" (toJson ((storedReach state).map fun (f, j) => [toJson f, toJson j]))
    | none => reply
  let rec go (fuel : Nat) (state : State) (responses : List Term) (plans : Array Json) : Json :=
    let done := fun (status : String) (value : Json) => Json.mkObj
      [("status", toJson status), ("shape", value), ("plans", Json.arr plans)]
    let doneWith := fun (status : String) (all : Array Json) => Json.mkObj
      [("status", toJson status), ("shape", Json.null), ("plans", Json.arr all)]
    match fuel with
    | 0 => done "exhausted" Json.null
    | fuel + 1 =>
      match runBounded limits ticks state with
      | .finished value final => reads final (done "value" (shape final value))
      | .suspended _ st => reads st (done "exhausted" Json.null)
      | .divergent _ st => reads st (done "exhausted" Json.null)
      | .refused _ st => reads st (done "stuck" Json.null)
      | .yielded _ yielded =>
        match yieldedPlan fetch limits budget yielded with
        | .error _ => done "unmaterializable-plan" Json.null
        | .ok extracted =>
          let plans := plans.push (dataJson extracted.value)
          match responses with
          | [] => reads extracted.state (doneWith "yield" plans)
          | response :: rest =>
            match resume response yielded with
            | none => doneWith "stuck" plans
            | some next => go fuel next rest plans
  let start := match stored with
    | some (state, store) => storedInitial term state (store.relations.map fun r => (r.field, r.size))
    | none => initial term
  go 64 start responses #[]

def op (j : Json) : Except String Json := do
  let term ← termOf 4096 (← j.getObjVal? "term")
  let responses ← match j.getObjVal? "responses" with
    | .ok r => (← r.getArr?).toList.mapM (termOf 4096)
    | .error _ => pure []
  let ticks := (j.getObjValAs? Nat "ticks").toOption.getD 200000
  -- `stored: {state, relations: [{field, key}]}`: the term applied to the state, the named relation
  -- fields held as stored cells over the state's own rows, keyed as named.
  let stored ← match j.getObjVal? "stored" with
    | .error _ => pure none
    | .ok s => do
      let state ← Delvetalk.Compiler.ObjectiveBendDataWire.decodeData 4096 (← s.getObjVal? "state")
      let .record fields := state | throw "stored state must be a record"
      pure (some (fields, ← Delvetalk.Turn.storeOfState state (← s.getObjVal? "relations")))
  return Json.mkObj [("schema", toJson "delvetalk.evaluate-term.v1"), ("result", evaluate term responses ticks stored)]

end Delvetalk.EvaluateTerm
