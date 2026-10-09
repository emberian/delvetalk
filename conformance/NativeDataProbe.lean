import Theory.ObjectiveBendDemandData
import Theory.ObjectiveBendNativeDataSimulation
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData
private def oldApplication (term : Term) (args : List Data) :=
  args.foldl (fun term data => .app term data.term) term
private def compare (name : String) (term : Term) (args : List Data)
    (heap : Nat := 10000) : IO Unit := do
  let limits : Limits := ⟨heap,1000⟩
  let budget : Budget := ⟨10000,100000,10000000⟩
  let old := execute limits budget (oldApplication term args)
  let native := executeDataArguments limits budget term args
  match old,native with
  | .ok a,.ok b =>
    unless reprStr a.extraction.result.value == reprStr b.extraction.result.value do
      throw (IO.userError (name ++ " data mismatch"))
    unless a.extraction.result.remaining.nodes == b.extraction.result.remaining.nodes &&
        a.extraction.result.remaining.bytes == b.extraction.result.remaining.bytes && a.state.heap.size == b.state.heap.size do
      throw (IO.userError (name ++ " structural accounting mismatch"))
    unless b.extraction.result.remaining.ticks ≥ a.extraction.result.remaining.ticks do
      throw (IO.userError (name ++ " native ticks increased"))
    IO.println s!"{name}: source={100000-a.extraction.result.remaining.ticks} native={100000-b.extraction.result.remaining.ticks} heap={b.state.heap.size}"
  | .error (a,_,_),.error (b,_,_) =>
    unless reprStr a == reprStr b do throw (IO.userError (name ++ " refusal mismatch"))
    IO.println s!"{name}: same refusal {reprStr a}"
  | _,_ => throw (IO.userError (name ++ " outcome mismatch"))
private def probe : IO Unit := do
  compare "scalar" (.lam (.bound 0)) [.natural 17]
  compare "declared record" (.lam (.bound 0)) [.record [("z",.natural 1),("a",.boolean true)]]
  compare "nested variant" (.lam (.bound 0)) [.variant "Some" (.record [("x",.variant "Some" (.natural 9))])]
  compare "argument order" (.lam (.lam (.record [("first",.bound 1),("second",.bound 0)]))) [.natural 3,.natural 5]
  compare "spec wrapper" (.specification (.record []) (.lam (.bound 0))) [.label "x"]
  compare "repeated force" (.lam (.record [("a",.bound 0),("b",.bound 0)])) [.record [("x",.natural 3)]]
  compare "unused huge lazy input" (.lam (.nat 1)) [.record ((List.range 5000).map fun n => (toString n,.natural n))] 1
  compare "wrong function" (.nat 1) [.natural 2]
  compare "yield" (.lam (.perform (.bound 0))) [.variant "Ping" (.record [])]
  let ticksToFinish (native : Bool) := (List.range 30).find? fun ticks =>
    let limits : Limits := ⟨100,100⟩
    let budget : Budget := ⟨100,ticks,100000⟩
    if native then (executeDataArguments limits budget (.lam (.bound 0)) [.natural 1]).isOk
    else (execute limits budget (.app (.lam (.bound 0)) (.nat 1))).isOk
  unless ticksToFinish false == some 8 && ticksToFinish true == some 6 do
    throw (IO.userError s!"lowfuel threshold source={ticksToFinish false} native={ticksToFinish true}")
  IO.println "native finite data differential passes; scalar lowfuel threshold 8→6"
#eval probe
