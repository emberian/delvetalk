/- A debug profile of the hosted demand machine: the same transitions and tariff as
`forceHostedFrom` (Theory.ObjectiveBendDemandData), with every tick attributed to the
kind of the state it was spent in: `evaluate.<term>`, `enter.<cell>`,
`returned.<frame>` (the frame the value returns to), `nativeApplication`. It is a
separate loop, never on a turn's path: a request asks for it with `"profile": true`
and the reply carries it beside the ordinary result. It profiles one segment run
(to completion, a yield or exhaustion); extraction of the result or Plan is the
remainder of `ticksUsed`. -/
import Theory.ObjectiveBendDemandData
import Std.Data.HashMap

namespace Delvetalk.Profile
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData

def termKind : Term → String
  | .bound _ => "bound" | .lam _ => "lam" | .app _ _ => "app" | .mix _ _ => "mix" | .fix _ _ => "fix"
  | .specification _ _ => "specification" | .prototype _ _ => "prototype" | .reflect _ => "reflect"
  | .metadata _ => "metadata" | .project _ => "project" | .nat _ => "nat" | .boolean _ => "boolean"
  | .label _ => "label" | .binary _ _ _ => "binary" | .unary _ _ => "unary" | .extend _ _ => "extend"
  | .record _ => "record" | .get _ _ => "get" | .ifZero _ _ _ => "ifZero" | .inject _ _ => "inject"
  | .case _ _ => "case" | .ifBool _ _ _ => "ifBool" | .perform _ => "perform" | .done _ => "done"
  | .toData _ => "toData" | .textJoin _ _ => "textJoin" | .refuse _ => "refuse"

def frameKind : Frame → String
  | .argument .. => "argument" | .nativeArgument _ => "nativeArgument" | .update _ => "update"
  | .field _ => "field" | .reflect => "reflect" | .metadata => "metadata" | .project => "project"
  | .extend .. => "extend" | .condition .. => "condition" | .unary _ => "unary"
  | .binaryLeft .. => "binaryLeft" | .binaryRight .. => "binaryRight" | .case .. => "case"
  | .ifBool .. => "ifBool" | .joinSeparator .. => "joinSeparator" | .joinList .. => "joinList"
  | .joinCons .. => "joinCons" | .joinHead .. => "joinHead"

def stateKind (state : State) : String :=
  match state.control with
  | .evaluate term _ => "evaluate." ++ termKind term
  | .enter address => match state.heap[address]? with
    | some (.suspended _) => "enter.suspended" | some (.evaluating _) => "enter.evaluating"
    | some (.cached _ _) => "enter.cached" | some (.native _) => "enter.native"
    | some (.nativeCached _ _) => "enter.nativeCached" | none => "enter.missing"
  | .returned _ => match state.stack with
    | [] => "returned.empty"
    | .binaryRight primitive _ :: _ => "returned.binaryRight." ++ (reprStr primitive).replace "Minidregg.Theory.ObjectiveBendOpenRecursion.Primitive." ""
    | .unary primitive :: _ => "returned.unary." ++ (reprStr primitive).replace "Minidregg.Theory.ObjectiveBendOpenRecursion.UnaryPrimitive." ""
    | frame :: _ => "returned." ++ frameKind frame
  | .nativeApplication .. => "nativeApplication"
  | _ => "stopped"

abbrev Tally := Std.HashMap String (Nat × Nat)

/-- `forceHostedFrom`'s loop with attribution (the unrestricted policy). -/
def profileFrom (limits : Limits) (bytes : Nat) : Nat → State → Nat → Tally → Tally
  | 0, _, _, tally => tally
  | fuel + 1, state, depth, tally =>
    match state.control with
    | .complete _ | .refused _ | .blackhole _ | .yielded _ => tally
    | _ =>
      let cost := textStepCost state (fuel + 1)
      if cost.2 > bytes || cost.1 > fuel + 1 then tally
      else
        let sizes := Minidregg.Theory.ObjectiveBendDemandMachineFast.sizesAfter state depth
        if sizes.1 ≤ limits.heap && sizes.2 ≤ limits.stack then
          let spent := max 1 cost.1
          let key := stateKind state
          let (count, ticks) := tally.getD key (0, 0)
          let tally := tally.insert key (count + 1, ticks + spent)
          profileFrom limits bytes (fuel + 1 - spent) (Minidregg.Theory.ObjectiveBendDemandMachineFast.stepRawFast state)
            sizes.2 tally
        else tally
termination_by fuel => fuel
decreasing_by all_goals omega

/-- The profile as JSON, heaviest kind first: `[{kind, steps, ticks}]`. -/
def profile (limits : Limits) (bytes ticks : Nat) (state : State) : Json :=
  let tally := profileFrom limits bytes ticks state state.stack.length {}
  let rows := tally.toList.toArray.qsort (fun a b => a.2.2 > b.2.2 || (a.2.2 == b.2.2 && a.1 < b.1))
  Json.arr (rows.map fun (kind, steps, spent) =>
    Json.mkObj [("kind", toJson kind), ("steps", toJson steps), ("ticks", toJson spent)])

end Delvetalk.Profile
