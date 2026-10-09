/- Compiled-evaluation audit adapted from Bread metatheory/Dregg2/Tactics.lean.
Re-runs actual closed Boolean oracle claims; rejects arbitrary named axioms.
This marks compiler trust and does not certify general source refinement. -/
import Theory.AssertAxioms

/-- The two axioms LEAN ITSELF declares for proof-by-compiled-evaluation (`Lean.ofReduceBool`,
`Lean.ofReduceNat`, both `Init.Core`). Recognising THESE by name is sound in the way a name
*pattern* never is: both names are already occupied by the prelude, so no other declaration can
ever bear them and a second one cannot be declared. The equality test is an IDENTITY test, not a
spelling test. Their claim lives in the proof term (via `Lean.reduceBool`), not in the axiom, so
there is nothing here to re-run — accepting them IS accepting compiler trust, which is exactly
what this command's label announces. -/
def Minidregg.Theory.AssertCompiled.isCoreReduceAxiom (a : Lean.Name) : Bool :=
  a == ``Lean.ofReduceBool || a == ``Lean.ofReduceNat

/-- The Boolean claim a `native_decide`/`bv_decide` oracle axiom makes, if its type has the shape
that machinery emits. `Lean.Meta.nativeEqTrue` builds the axiom type as
`mkApp3 (mkConst ``Eq [1]) (mkConst ``Bool) e (mkConst ``Bool.true)` for a CLOSED `e : Bool` it has
just watched evaluate to `true`; this returns that `e`.

Returning the CLAIM rather than a yes/no about the name is the whole point: it is what lets the
caller go and re-run `e` for itself. A type that is not of this shape is not a compiled-evaluation
claim at all and there is nothing to re-run — which is a refusal, not a pass. -/
def Minidregg.Theory.AssertCompiled.nativeOracleClaim? (type : Lean.Expr) : Option Lean.Expr :=
  match type.eq? with
  | some (α, lhs, rhs) =>
      if α.isConstOf ``Bool && rhs.isConstOf ``Bool.true then some lhs else none
  | none => none

open Lean Elab Command in
/-- `#assert_compiled foo` — see the section note above. For every axiom `foo` rests on that is not
kernel-clean, this command requires either (a) one of Lean's own two `reduce*` axioms, whose names
cannot be forged because they are taken, or (b) an axiom asserting `<closed Bool expr> = true` whose
expression this command RE-RUNS through the compiled evaluator and watches return `true`. Anything
else is a hard ERROR. It ALSO errors if `foo` rests on no oracle at all (then `#assert_axioms` is
the correct, stronger pin). A name is never the test — see the `⚑ WHY A NAME CANNOT BE THE TEST`
note above, which records the forgery this command used to accept. -/
elab "#assert_compiled" id:ident : command => do
  let name ← liftCoreM <| realizeGlobalConstNoOverloadWithInfo id
  let axs ← Lean.collectAxioms name
  let env ← getEnv
  let mut coreOracles : Array Name := #[]
  let mut candidates : Array (Name × Expr) := #[]
  let mut refusals : Array MessageData := #[]
  for a in axs do
    if Minidregg.Theory.AssertAxioms.standard.contains a then continue
    if Minidregg.Theory.AssertCompiled.isCoreReduceAxiom a then
      coreOracles := coreOracles.push a
      continue
    match env.find? a with
    | none =>
      refusals := refusals.push m!"{a} — not present in the environment, so its claim cannot be \
        re-run"
    | some info =>
      match Minidregg.Theory.AssertCompiled.nativeOracleClaim? info.type with
      | none =>
        refusals := refusals.push m!"{a} : {info.type} — NOT a compiled-evaluation claim. A \
          `native_decide`/`bv_decide` oracle has type `<closed Bool expr> = true`; this axiom \
          asserts something else, so there is nothing to re-run and nothing here is checkable \
          by compiled evaluation"
      | some claim =>
        if info.levelParams.isEmpty then
          candidates := candidates.push (a, claim)
        else
          refusals := refusals.push m!"{a} — universe-polymorphic ({info.levelParams}), so its \
            claim is not a single closed Boolean this command can re-run"
  -- ⚑ THE TEST. Not "is it named like an oracle" — "does the evaluator I am declaring trust in
  -- still say what this axiom says". Same engine `native_decide` and `#guard` run on.
  unless candidates.isEmpty do
    let evalRefusals ← liftTermElabM do
      let mut fails : Array MessageData := #[]
      for (a, claim) in candidates do
        let verdict : Option MessageData ←
          try
            let b ← unsafe Lean.Meta.evalExpr Bool (Lean.mkConst ``Bool) claim (checkMeta := false)
            pure <| if b then none else
              some m!"{a} — the compiled evaluator returns `false` for the claim this axiom \
                asserts TRUE:{Lean.indentExpr claim}\nThis axiom is either forged or stale; \
                either way nothing may rest on it"
          catch ex =>
            pure <| some m!"{a} — its claim could not be re-run through the compiled evaluator \
              ({ex.toMessageData}), so the compiled-evaluation label is unsupported"
        if let some f := verdict then fails := fails.push f
      pure fails
    refusals := refusals ++ evalRefusals
  unless refusals.isEmpty do
    throwError "compiled-pin FAIL: {name} rests on {refusals.size} axiom(s) this command REFUSES \
      to certify as compiled evaluation:{Lean.indentD (MessageData.joinSep refusals.toList m!"\n")}\
      \nA compiled-evaluation pin certifies a FACT re-run through the evaluator, never a name."
  if coreOracles.isEmpty && candidates.isEmpty then
    throwError "compiled-pin REFUSED: {name} rests on NO compiled-evaluation oracle — it is \
      kernel-clean, so pin it with the STRONGER `#assert_axioms {name}`. Labelling a \
      kernel-clean fact 'compiled' throws away its real pin"



