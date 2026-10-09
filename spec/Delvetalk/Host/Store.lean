/- The durable half of the host: objects and the world that holds them. Pure data.
   The journal (Journal.lean) is the only source of a World; Ops.lean is the only
   writer. Nothing here depends on an evaluator. -/
import Delvetalk.Package
import Std.Data.HashMap

namespace Delvetalk.Host
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Theory.ObjectiveBendTypes (Ty)
open Minidregg.Compiler.ObjectiveBendLaw (LawExpr)

/- Every capacity of the host's world kernel, in one place. A request beyond
    any of them is refused as a request error and journals nothing. -/
namespace Limits
def maxObjects : Nat := 10000
def maxObjectIdBytes : Nat := 128
def maxPrincipalBytes : Nat := 128
def maxIntentBytes : Nat := 256
def maxRoots : Nat := 64
def maxWrites : Nat := 64
def maxEditsPerWrite : Nat := 256
/-- Compressed `dataJson` of one object's state. -/
def maxStateBytes : Nat := 65536
/-- One compressed journal line. -/
def maxEntryBytes : Nat := 1048576
def maxJournalEntries : Nat := 1000000
def maxJournalBytes : Nat := 268435456
def maxHistoryLimit : Nat := 100
def dataDepth : Nat := 64
def genesis : String := "".pushn '0' 64
end Limits

/-- A parsed `law NAME: EXPR` list; empty is "no law". -/
abbrev Law := List (String × LawExpr)

structure Object where
  /-- `packetSha256` of the compiled artifact the object was created from. -/
  pin : String
  law : Law
  version : Nat
  state : Data
  /-- The entry definition's type: a closed record of first-order data. -/
  stateType : Ty

structure World where
  objects : Std.HashMap String Object := {}
  /-- Number of journal entries; the last entry's height. -/
  height : Nat := 0
  head : String := Limits.genesis
  /-- Entry `h` is at index `h - 1`. -/
  entries : Array Json := #[]
  /-- Identity key (principal, intent) to entry index. The first entry wins. -/
  receipts : Std.HashMap String Nat := {}
  /-- Object id to indices of admitted or creating entries touching it. -/
  touched : Std.HashMap String (Array Nat) := {}

def identityKey (principal intent : String) : String :=
  (Json.arr #[toJson principal, toJson intent]).compress

end Delvetalk.Host
