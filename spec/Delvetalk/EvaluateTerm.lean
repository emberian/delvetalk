/- Pure reference evaluation of a closed core term, for conformance against the
   independent evaluators in impl/. The term is read in the evaluators' array
   wire (`["app", f, a]`, `["nat", "3"]`, ...). The demand machine runs it; the
   reply is the machine's weak-head result, as a shape, or a yielded Plan. -/
import Lean.Data.Json
import Theory.ObjectiveBendDemandData
import Compiler.ObjectiveBendDataWire

namespace Delvetalk.EvaluateTerm
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData
open Minidregg.Compiler.ObjectiveBendDataWire (dataJson)

def primitiveOfName : String → Except String Primitive
  | "add" => pure .add | "multiply" => pure .multiply | "equal" => pure .equal
  | "conjunction" => pure .conjunction | "labelEqual" => pure .labelEqual
  | "subtract" => pure .subtract | "divide" => pure .divide | "less" => pure .less
  | "lessEqual" => pure .lessEqual | "modulo" => pure .modulo
  | "textConcat" => pure .textConcat | "textTake" => pure .textTake | "textDrop" => pure .textDrop
  | "textSpan" => pure .textSpan | "textBreak" => pure .textBreak
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

/-- Run to a result, resuming each yielded Plan with the next response. -/
def evaluate (term : Term) (responses : List Term) (ticks : Nat) : Json :=
  let limits : Limits := ⟨1000000, 100000⟩
  let budget : Budget := ⟨1000000, 100000000, 16777216⟩
  let rec go (fuel : Nat) (state : State) (responses : List Term) (plans : Array Json) : Json :=
    let done := fun (status : String) (value : Json) => Json.mkObj
      [("status", toJson status), ("shape", value), ("plans", Json.arr plans)]
    let doneWith := fun (status : String) (all : Array Json) => Json.mkObj
      [("status", toJson status), ("shape", Json.null), ("plans", Json.arr all)]
    match fuel with
    | 0 => done "exhausted" Json.null
    | fuel + 1 =>
      match runBounded limits ticks state with
      | .finished value final => done "value" (shape final value)
      | .suspended _ _ => done "exhausted" Json.null
      | .divergent _ _ => done "exhausted" Json.null
      | .refused _ _ => done "stuck" Json.null
      | .yielded _ yielded =>
        match yieldedPlan limits budget yielded with
        | .error _ => done "unmaterializable-plan" Json.null
        | .ok extracted =>
          let plans := plans.push (dataJson extracted.value)
          match responses with
          | [] => doneWith "yield" plans
          | response :: rest =>
            match resume response yielded with
            | none => doneWith "stuck" plans
            | some next => go fuel next rest plans
  go 64 (initial term) responses #[]

def op (j : Json) : Except String Json := do
  let term ← termOf 4096 (← j.getObjVal? "term")
  let responses ← match j.getObjVal? "responses" with
    | .ok r => (← r.getArr?).toList.mapM (termOf 4096)
    | .error _ => pure []
  let ticks := (j.getObjValAs? Nat "ticks").toOption.getD 200000
  return Json.mkObj [("schema", toJson "delvetalk.evaluate-term.v1"), ("result", evaluate term responses ticks)]

end Delvetalk.EvaluateTerm
