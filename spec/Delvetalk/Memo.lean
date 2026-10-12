/- The bound every process memo keeps (the host's compiled packages and definitions, the package
   front end's parsed modules, the law's parsed texts): a memo answers a pure function of its key, so
   which entries it holds changes only how fast an answer comes. -/
import Std.Data.HashMap

namespace Delvetalk

/-- `m` with `k ↦ v`, holding at most `bound` keys: when full, one other key goes (never the whole map, which
    would recompile everything a full cache held). -/
def boundedInsert {α : Type} (m : Std.HashMap String α) (bound : Nat) (k : String) (v : α) : Std.HashMap String α :=
  if m.size < bound || m.contains k then m.insert k v else
  match m.fold (init := none) fun (acc : Option String) key _ => acc <|> (if key == k then none else some key) with
  | some old => (m.erase old).insert k v
  | none => m.insert k v

end Delvetalk
