/- Checkpoint tokens as the journal stores them: every heap address written relative to the
   cell that holds it, so a heap that grew or shrank by a few cells in one place (a list walked
   one further, a longer argument) leaves the rest of its tokens byte-identical and their blocks
   dedup. A pure, invertible renaming of addresses; the checkpoint's digest stays over the
   kernel's own tokens, which `absoluteTokens` restores exactly (the writer checks it, and
   journals the plain tokens when it would not). -/
import Delvetalk.Turn

namespace Delvetalk.Host.Relative
open Lean (Json)
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendCheckpoint

/-- Address `a` seen from position `i`, zigzagged into a natural: 0, 2, 4 … back, 1, 3 … ahead. -/
def toRelative (i a : Nat) : Nat := if a ≤ i then 2 * (i - a) else 2 * (a - i) - 1
def ofRelative (i r : Nat) : Nat := if r % 2 == 0 then i - r / 2 else i + (r + 1) / 2

theorem ofRelative_toRelative (i a : Nat) : ofRelative i (toRelative i a) = a := by
  unfold toRelative ofRelative
  split <;> rename_i h
  · have : 2 * (i - a) % 2 = 0 := by omega
    simp only [this, beq_self_eq_true, ite_true]; omega
  · have : (2 * (a - i) - 1) % 2 = 1 := by omega
    have hne : ((2 * (a - i) - 1) % 2 == 0) = false := by rw [this]; rfl
    simp only [hne, Bool.false_eq_true, ite_false]; omega

section
variable (f : Address → Address)

def mapValue : RuntimeValue → RuntimeValue
  | .closure body environment => .closure body (environment.map f)
  | .record fields => .record (fields.map fun (n, a) => (n, f a))
  | .specification m e => .specification (f m) (f e)
  | .prototype s t => .prototype (f s) (f t)
  | .variant l p => .variant l (f p)
  | other => other

def mapClosure (c : Closure) : Closure := { c with environment := c.environment.map f }

def mapCell : Cell → Cell
  | .suspended c => .suspended (mapClosure f c)
  | .evaluating c => .evaluating (mapClosure f c)
  | .cached c v => .cached (mapClosure f c) (mapValue f v)
  | .native d => .native d
  | .nativeCached d v => .nativeCached d (mapValue f v)

def mapFrame : Frame → Frame
  | .argument t e => .argument t (e.map f)
  | .update a => .update (f a)
  | .extend fs e => .extend fs (e.map f)
  | .condition z s e => .condition z s (e.map f)
  | .binaryLeft p r e => .binaryLeft p r (e.map f)
  | .binaryRight p v => .binaryRight p (mapValue f v)
  | .case arms e => .case arms (e.map f)
  | .ifBool t u e => .ifBool t u (e.map f)
  | .joinSeparator l e => .joinSeparator l (e.map f)
  | .joinHead s acc first tail => .joinHead s acc first (f tail)
  | other => other

def mapControl : Control → Control
  | .evaluate t e => .evaluate t (e.map f)
  | .enter a => .enter (f a)
  | .blackhole a => .blackhole (f a)
  | .returned v => .returned (mapValue f v)
  | .complete v => .complete (mapValue f v)
  | .yielded a => .yielded (f a)
  | other => other
end

/-- Rename every address: a heap cell's by its own index, the control's and the stack's by the
    heap's size. -/
def mapState (g : Nat → Address → Address) (s : State) : State :=
  { heap := s.heap.mapIdx fun i c => mapCell (g i) c
    control := mapControl (g s.heap.size) s.control
    stack := s.stack.map (mapFrame (g s.heap.size)) }

/-- The relative form of a checkpoint's tokens, when they decode and the renaming inverts on
    them; none otherwise (the caller journals them as they are). -/
def relativeTokens (tokens : Array Json) : Option (Array Json) := do
  let plain ← (Delvetalk.Turn.tokensOfJson (Json.arr tokens)).toOption
  let state ← decodeState plain
  let relative := encodeState (mapState toRelative state)
  let back ← decodeState relative
  guard (encodeState (mapState ofRelative back) == plain)
  return (relative.map tokenJson).toArray

/-- The kernel's tokens of a relative form. -/
def absoluteTokens (tokens : Array Json) : Except String (Array Json) := do
  let relative ← Delvetalk.Turn.tokensOfJson (Json.arr tokens)
  let some state := decodeState relative | throw "a relative checkpoint does not decode"
  return ((encodeState (mapState ofRelative state)).map tokenJson).toArray

end Delvetalk.Host.Relative
