import Theory.ObjectiveBendDemandMachineFast
namespace Minidregg.Theory.ObjectiveBendDemandMachine
open ObjectiveBendDemandData ObjectiveBendOpenRecursion
set_option autoImplicit false

/-- Proof-only erasure. The native runtime never constructs input literals. -/
def eraseNativeCell : Cell → Cell
  | .native data => .suspended ⟨data.term, []⟩
  | .nativeCached data value => .cached ⟨data.term, []⟩ value
  | cell => cell

def eraseNativeHeap (heap : Array Cell) : Array Cell := heap.map eraseNativeCell

@[simp] theorem eraseNativeHeap_size (heap : Array Cell) :
    (eraseNativeHeap heap).size = heap.size := by simp [eraseNativeHeap]

private theorem allocationFold (fields : List (String × Data)) (heap : Array Cell)
    (addresses : List (String × Address)) :
    let native := fields.foldl (fun (p : Array Cell × List (String × Address)) f =>
      (p.1.push (.native f.2), (f.1,p.1.size)::p.2)) (heap,addresses)
    let source := (fieldsTerm fields).foldl (fun (p : Array Cell × List (String × Address)) f =>
      (p.1.push (.suspended ⟨f.2,[]⟩), (f.1,p.1.size)::p.2)) (eraseNativeHeap heap,addresses)
    (eraseNativeHeap native.1, native.2) = source := by
  induction fields generalizing heap addresses with
  | nil => rfl
  | cons field rest ih =>
      simp only [List.foldl_cons, fieldsTerm]
      simpa [eraseNativeHeap, Array.map_push, eraseNativeCell] using
        ih (heap.push (.native field.2)) ((field.1,heap.size)::addresses)

/-- Lazy children have exactly the original addresses and declared field order. -/
theorem allocateNativeFields_erasure (heap : Array Cell) (fields : List (String × Data)) :
    let native := allocateNativeFields heap fields
    (eraseNativeHeap native.1,native.2) = allocateFields (eraseNativeHeap heap) [] (fieldsTerm fields) := by
  have h := allocationFold fields heap []
  simp only [allocateNativeFields, allocateFields]
  rw [← h]

/-- No input value can introduce executable closures or reflected metadata. -/
def finiteRuntimeValue : RuntimeValue → Prop
  | .natural _ | .boolean _ | .label _ | .record _ | .variant _ _ => True
  | .closure _ _ | .specification _ _ | .prototype _ _ => False

theorem forceNative_finite (heap : Array Cell) (data : Data) :
    finiteRuntimeValue (forceNative heap data).2 := by
  cases data <;> simp [forceNative, finiteRuntimeValue]

/-- Forcing one finite value is the same literal weak-head value and child heap
as source literal evaluation. It eliminates the source enter/update instructions;
only the immediate layer is allocated. -/
theorem forceNative_literal (heap : Array Cell) (data : Data) (stack : List Frame) :
    let result := forceNative heap data
    { heap := eraseNativeHeap result.1, control := Control.returned result.2, stack := stack : State } =
      stepRaw {heap := eraseNativeHeap heap, control := .evaluate data.term [], stack := stack} := by
  cases data with
  | natural n => rfl
  | boolean b => rfl
  | label s => rfl
  | variant tag payload => simp [forceNative, Data.term, stepRaw, eraseNativeHeap, Array.map_push, eraseNativeCell]
  | record fields =>
      have h := allocateNativeFields_erasure heap fields
      simp only [forceNative, Data.term, stepRaw]
      cases hn : allocateNativeFields heap fields with
      | mk nativeHeap addresses =>
          simp only [hn] at h ⊢
          rw [← h]

end Minidregg.Theory.ObjectiveBendDemandMachine
