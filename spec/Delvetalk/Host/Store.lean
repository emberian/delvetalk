/- The durable half of the host: objects and the world that holds them. Pure data.
   The journal (Journal.lean) is the only source of a World; Ops.lean is the only
   writer. Nothing here depends on an evaluator. -/
import Delvetalk.Package
import Std.Data.HashMap

namespace Delvetalk.Host
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Theory.ObjectiveBendTypes (Ty DataBounds)
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
/-- Nested `call` depth inside one turn. -/
def maxCallDepth : Nat := 8
/-- Plans answered in one turn, across all nested calls. -/
def maxPlansPerTurn : Nat := 1024
/-- Compiled method packets kept in memory. -/
def maxCompiledPackets : Nat := 256
def maxMethodBytes : Nat := 128
/-- Principals named in one object's read policy. -/
def maxReaders : Nat := 256
/-- The causal ledger a principal's turn starts with; a delivery inherits its
    sender's, decremented. Creation may lower these per object, never raise them. -/
def maxDepth : Nat := 100
/-- Machine ticks across a whole chain of deliveries. -/
def chainWork : Nat := 10000000
/-- Bytes of state a chain may add. -/
def chainStorage : Nat := 1048576
def deliveriesPerCall : Nat := 16
def sendsPerTurn : Nat := 32
/-- Undelivered sends held by the world. -/
def maxPending : Nat := 4096
def genesis : String := "".pushn '0' 64
end Limits

/-- A parsed `law NAME: EXPR` list; empty is "no law". -/
abbrev Law := List (String × LawExpr)

/-- A compiled method of an object's package: its checked packet and entry type. -/
structure Compiled where
  packet : Json
  type : Ty
  /-- The packet's declared type bounds and rigid variables: recursive types
      (a `List<T>` field) are data only under them. -/
  bounds : DataBounds
  rigid : List Nat

/-- Causal budget carried by a turn and inherited, decremented, by its sends. -/
structure Ledger where
  depth : Nat
  work : Nat
  storage : Nat

def Ledger.start : Ledger := ⟨Limits.maxDepth, Limits.chainWork, Limits.chainStorage⟩

def Ledger.json (l : Ledger) : Json :=
  Json.mkObj [("depth", toJson l.depth), ("work", toJson l.work), ("storage", toJson l.storage)]

/-- The first exhausted field, in the order depth, work, storage. -/
def Ledger.exhausted (l : Ledger) : Option String :=
  if l.depth == 0 then some "depth" else if l.work == 0 then some "work"
  else if l.storage == 0 then some "storage" else none

/-- Who may `view` an object; fixed at creation and journaled with it. -/
inductive ReadPolicy where
  | «public»
  | principals (allowed : List String)

def ReadPolicy.permits : ReadPolicy → String → Bool
  | .«public», _ => true
  | .principals allowed, who => allowed.contains who

def ReadPolicy.json : ReadPolicy → Json
  | .«public» => toJson "public"
  | .principals allowed => Json.mkObj [("principals", toJson allowed)]

structure Object where
  /-- `packetSha256` of the compiled artifact the object was created from. -/
  pin : String
  law : Law
  version : Nat
  state : Data
  /-- The entry definition's type: a closed record of first-order data. -/
  stateType : Ty
  bounds : DataBounds := []
  read : ReadPolicy := .«public»
  /-- Ledger of turns started on this object (creation may only lower it). -/
  chain : Ledger := Ledger.start
  /-- The journaled compile inputs (modules, limits); a method is one more `entry`. -/
  inputs : Json := Json.null
  /-- Digest of `inputs`, the key of this object's compiled methods. -/
  inputsKey : String := ""

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
  /-- Memory only, never journaled: compiled methods by `inputsKey/method`. -/
  compiled : Std.HashMap String Compiled := {}
  /-- Undelivered sends in journal order, derived from the journal. -/
  pending : Array Json := #[]

def identityKey (principal intent : String) : String :=
  (Json.arr #[toJson principal, toJson intent]).compress

end Delvetalk.Host
