/- A compiled entry held decoded and checked: what a host keeps per pin instead of the
packet JSON. Running it applies checked arguments to the checked entry
(`Checked.apply`) and never decodes or re-checks the packet. -/
import Theory.ObjectiveBendTyping
import Theory.ObjectiveBendCheckpointV2
import Delvetalk.Canonical
import Delvetalk.Limits

namespace Delvetalk
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendTypes

/-! ## Call sites of a message activity

A message activity (`Activity<R>`, Plan `World.Message`) resumes each perform at that
perform's own result type, the codomain of its annotation. The machine keeps no positions,
so a site is named by its plan term (`Turn.yieldedSite`). An entry in which two performs
build the same plan term at different result types is refused (`messageSites`), so the plan
term names exactly one type. The table is built once per held entry (`CheckedEntry.sites`). -/

/-- Whether an activity's Plan type is a message (a record), not a sum. -/
def isMessagePlan : Ty → Bool
  | .field _ _ _ | .emptyRow => true
  | _ => false

/-- Every perform of `term` with its annotation's codomain, in preorder, at the positions
`infer` gives children (`app` [0] [1], record field `i`, `extend`/`case` [1, i], ...). -/
partial def performsOf (annotations : Annotations) (position : List Nat) (term : Term)
    (acc : Array (Term × Option Ty)) : Array (Term × Option Ty) :=
  let at_ := fun (i : Nat) (t : Term) (acc : Array (Term × Option Ty)) => performsOf annotations (position ++ [i]) t acc
  let fields := fun (base : List Nat) (fs : List (String × Term)) (acc : Array (Term × Option Ty)) =>
    fs.zipIdx.foldl (fun acc ((_, t), i) => performsOf annotations (base ++ [i]) t acc) acc
  match term with
  | .perform plan => at_ 0 plan (acc.push (plan, (annotations position).map (·.codomain)))
  | .lam b | .reflect b | .metadata b | .project b | .unary _ b | .get b _ | .inject _ b
  | .done b | .toData b => at_ 0 b acc
  | .app a b | .mix a b | .fix a b | .specification a b | .prototype a b | .binary _ a b
  | .textJoin a b => at_ 1 b (at_ 0 a acc)
  | .ifZero a b c | .ifBool a b c => at_ 2 c (at_ 1 b (at_ 0 a acc))
  | .record fs => fields position fs acc
  | .extend a fs => fields (position ++ [1]) fs (at_ 0 a acc)
  | .case a arms => fields (position ++ [1]) arms (at_ 0 a acc)
  | .bound _ | .nat _ | .boolean _ | .label _ | .refuse _ => acc

/-- The call sites of a message activity's entry: each distinct plan term with its result
type. Refused when two performs build the same plan term at different result types (the
machine could not tell which one yielded). -/
def messageSites (source : AnnotatedTerm) : Except String (Array (Term × Ty)) := do
  let mut sites : Array (Term × Ty) := #[]
  for (plan, type?) in performsOf source.annotations [] source.term #[] do
    let some type := type? | throw "a world call has no annotated result type"
    match sites.find? (fun (t, _) => Minidregg.Theory.ObjectiveBendCheckpoint.termEq t plan) with
    | some (_, other) =>
      if other != type then
        throw ("refused (world-call-site): two world calls of this entry build the same message at different " ++
          "result types, so a response could not be told apart; give one of them a different argument")
    | none => sites := sites.push (plan, type)
  return sites

/-- The sites of an activity entry: `some` for a message activity, `none` for a sum Plan. -/
def sitesFor (source : AnnotatedTerm) (plan : Ty) : Except String (Option (Array (Term × Ty))) :=
  if isMessagePlan plan then some <$> messageSites source else pure none

/-- The activity type an entry finally has once every parameter is applied. -/
def finalType : Nat → Ty → Ty
  | 0, type => type
  | fuel + 1, .arrow _ _ _ codomain => finalType fuel codomain
  | _, type => type

/-- A checked closed source: the packet's own `source`, its `Checked` derivation (the
entry's type is `checked.type`), the checker fuel it carries, and its pin (the packet's
CID, `packetSha256`). -/
structure CheckedEntry where
  pin : String
  source : AnnotatedTerm
  checked : Checked source []
  fuel : Nat
  /-- The call sites of a message activity entry (`messageSites`), built once with the
  entry; `none` for any other entry. An applied entry keeps its entry's. -/
  sites : Option (Array (Term × Ty))

def CheckedEntry.type (e : CheckedEntry) : Ty := e.checked.type

/-- A held entry with its call-site table. -/
def CheckedEntry.make (pin : String) (source : AnnotatedTerm) (checked : Checked source []) (fuel : Nat) :
    Except String CheckedEntry := do
  let sites ← match finalType Bounds.entryArrowDepth checked.type with
    | .computation plan _ _ => sitesFor source plan
    | _ => pure none
  return ⟨pin, source, checked, fuel, sites⟩

/-- Decode and check a packet once. -/
def CheckedEntry.ofPacket (packet : Json) : Except String CheckedEntry := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let some checked := check decoded.source [] decoded.fuel | throw "package refused by Mini type checker"
  CheckedEntry.make (Delvetalk.Canonical.cidJson packet) decoded.source checked decoded.fuel

/-- Checker fuel for an argument: the entry's own fuel plus twice the argument's
constructors. `infer` spends one step per constructor and, in a field list, one per earlier
field, so a literal (however deep) never exhausts it; the entry's fuel stays the margin at
the deepest node. Fuel bounds only the checker (`check` is sound at any fuel). -/
def argumentFuel (fuel : Nat) (argument : Term) : Nat := fuel + 2 * argument.nodes

/-- Apply one closed argument term (with its own injection annotations, paths relative to
it): the argument alone is checked, then the application rule composes it. -/
def CheckedEntry.apply (e : CheckedEntry) (argument : Term) (annotations : AnnotationTree) :
    Except String CheckedEntry := do
  let source : AnnotatedTerm := ⟨argument, annotations.lookup, e.source.assumptions⟩
  -- `checkAt` is `check source` (`checkAt_eq`), walking the tree instead of paths.
  let some arg := checkAt argument annotations e.source.assumptions [] (argumentFuel e.fuel argument)
    | throw "applied package refused by Mini type checker"
  let some applied := e.checked.apply arg rfl | throw "applied package refused by Mini type checker"
  return ⟨e.pin, e.source.applyTo source, applied, e.fuel, e.sites⟩

end Delvetalk
