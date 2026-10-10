/- A compiled entry held decoded and checked: what a host keeps per pin instead of the
packet JSON. Running it applies checked arguments to the checked entry
(`Checked.apply`) and never decodes or re-checks the packet. -/
import Theory.ObjectiveBendTyping
import Delvetalk.Canonical

namespace Delvetalk
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendTypes

/-- A checked closed source: the packet's own `source`, its `Checked` derivation (the
entry's type is `checked.type`), the checker fuel it carries, and its pin (the packet's
CID, `packetSha256`). -/
structure CheckedEntry where
  pin : String
  source : AnnotatedTerm
  checked : Checked source []
  fuel : Nat

def CheckedEntry.type (e : CheckedEntry) : Ty := e.checked.type

/-- Decode and check a packet once. -/
def CheckedEntry.ofPacket (packet : Json) : Except String CheckedEntry := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let some checked := check decoded.source [] decoded.fuel | throw "package refused by Mini type checker"
  return ⟨Delvetalk.Canonical.cidJson packet, decoded.source, checked, decoded.fuel⟩

/-- An argument's injection annotations as a tree shaped like its term: child `i` of a node
is the annotation subtree of the term's child `i` (the checker's positions). A literal's
annotations are built with it in one pass, and a lookup walks its path, so no annotation
holds a path of its own: a list of `n` cells has `n` annotations at depths up to `2n`, and
storing each path (or scanning a list of them per lookup, as before) was quadratic in
memory and cubic in time. -/
inductive AnnotationTree where
  | node (here : Option LambdaAnnotation) (children : Array AnnotationTree)

instance : Inhabited AnnotationTree := ⟨.node none #[]⟩

def AnnotationTree.empty : AnnotationTree := .node none #[]

def AnnotationTree.lookup : AnnotationTree → List Nat → Option LambdaAnnotation
  | .node here _, [] => here
  | .node _ children, i :: rest => match children[i]? with
    | some child => child.lookup rest
    | none => none

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
  let some arg := check source [] (argumentFuel e.fuel argument) | throw "applied package refused by Mini type checker"
  let some applied := e.checked.apply arg rfl | throw "applied package refused by Mini type checker"
  return ⟨e.pin, e.source.applyTo source, applied, e.fuel⟩

end Delvetalk
