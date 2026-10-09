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

/-- Apply one closed argument term (with its own injection annotations, paths relative to
it): the argument alone is checked, then the application rule composes it. -/
def CheckedEntry.apply (e : CheckedEntry) (argument : Term) (annotations : List (List Nat × LambdaAnnotation)) :
    Except String CheckedEntry := do
  let source : AnnotatedTerm := ⟨argument, fun path => (annotations.find? (·.1 == path)).map (·.2), e.source.assumptions⟩
  let some arg := check source [] e.fuel | throw "applied package refused by Mini type checker"
  let some applied := e.checked.apply arg rfl | throw "applied package refused by Mini type checker"
  return ⟨e.pin, e.source.applyTo source, applied, e.fuel⟩

end Delvetalk
