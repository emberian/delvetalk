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
-- Shared kernel bounds (ticks, heap, stack, nodes, bytes, data depth, documents, offers) live in Delvetalk/Limits.lean; this host will read them from there.
def maxObjects : Nat := 10000
def maxObjectIdBytes : Nat := 128
def maxPrincipalBytes : Nat := 128
def maxIntentBytes : Nat := 256
def maxRoots : Nat := 64
def maxWrites : Nat := 64
def maxEditsPerWrite : Nat := 256
/-- Compressed `dataJson` of one object's state. -/
def maxStateBytes : Nat := 262144
/-- One compressed journal line. -/
def maxEntryBytes : Nat := 1048576
def maxJournalEntries : Nat := 1000000
def maxJournalBytes : Nat := 268435456
def maxHistoryLimit : Nat := 100
def dataDepth : Nat := 8192
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
/-- Deliveries the settling pass after one durable op runs; the rest wait for the next op. -/
def deliveriesPerSettle : Nat := 64
def sendsPerTurn : Nat := 32
/-- Undelivered sends held by the world. -/
def maxPending : Nat := 4096
/-- Ticks of one turn: the default and the ceiling a request may ask for (the kernel's own cap). -/
def maxTurnTicks : Nat := 1000000
/-- Seed state of a created object, compressed wire bytes. -/
def maxSeedBytes : Nat := 262144
/-- Objects one turn may create. -/
def createsPerTurn : Nat := 8
/-- Suspended activities waiting on one object, and in the whole world. -/
def pendingActivitiesPerObject : Nat := 8
def maxSuspended : Nat := 4096
/-- Awaits one turn may perform, across its suspensions. -/
def awaitsPerTurn : Nat := 8
/-- Largest patience of an await, in clock units. -/
def maxPatience : Nat := 1000000
/-- Compressed checkpoint tokens a suspension may journal. -/
def maxCheckpointBytes : Nat := 524288
/-- Suspended activities one settling pass resumes. -/
def maxResumesPerCall : Nat := 1024
/-- Source text of a package offered to `reprogram`. -/
def maxPackageBytes : Nat := 32768
/-- Law text of an `amend`, and the clauses in it. -/
def maxLawBytes : Nat := 4096
def maxLawClauses : Nat := 16
/-- Compiled packages kept in memory (`World.builds`). -/
def maxBuilds : Nat := 1024
/-- Prepared reprograms kept in memory. -/
def maxPreparedPrograms : Nat := 16
/-- Modules and bytes of the sealed standard library. -/
def maxLibraryModules : Nat := 256
def maxLibraryBytes : Nat := 786432
/-- `check` Plans one turn may run (each is a full compile). -/
def checksPerTurn : Nat := 8
/-- Clock units an `interpret` waits for its reply before it resumes `timedOut`. -/
def interpretationPatience : Nat := 64
/-- Utterance and offered forms of one `interpret`. -/
def maxUtteranceBytes : Nat := 8192
def maxOffersBytes : Nat := 65536
/-- A model reply, as settled. -/
def maxReplyBytes : Nat := 262144
/-- Nesting of the plain JSON argument of a proposal. -/
def plainDepth : Nat := 64
/-- Grants one turn may make, and grants (live or revoked) a world holds. -/
def grantsPerTurn : Nat := 8
def maxGrants : Nat := 4096
def genesis : String := "".pushn '0' 64
/-- Ids one `objects` listing answers. -/
def listPage : Nat := 64
/-- Bytes of a post's AT URI and CID. -/
def maxUriBytes : Nat := 512
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

/-- A compiled replacement package for an object, ready to judge. The state
    migration, when there is one, is a compiled function OldState -> NewState. -/
structure Program where
  inputs : Json
  pin : String
  stateType : Ty
  bounds : DataBounds
  migration : Option Compiled

structure Object where
  /-- `packetSha256` of the compiled artifact the object was created from. -/
  pin : String
  law : Law
  /-- The law as text, the form it is amended in; `law` is its parse. -/
  lawText : String := ""
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

/-- The standard library every package may import by name: modules in dependency
    order, sealed by `pin` (a hash of the names and sources in that order). -/
structure Library where
  pin : String
  modules : List (String × String)

/-- A delegation: `grantor` (the principal of the direct turn that made it) lets `to` (a
    principal or an object id) run `method` of `object` as the grantor, while the clock is at
    most `expires` (the Plan's `until`). `holder` is the object whose method granted it; it and the grantor may revoke. -/
structure Grant where
  id : String
  grantor : String
  holder : String
  to : String
  object : String
  method : String
  expires : Nat
  revoked : Bool := false
  deriving BEq

def Grant.json (g : Grant) : Json :=
  Json.mkObj [("id", toJson g.id), ("grantor", toJson g.grantor), ("holder", toJson g.holder),
    ("to", toJson g.to), ("object", toJson g.object), ("method", toJson g.method), ("until", toJson g.expires)]

def Grant.ofJson (j : Json) : Except String Grant := do
  return { id := ← j.getObjValAs? String "id", grantor := ← j.getObjValAs? String "grantor",
           holder := ← j.getObjValAs? String "holder", to := ← j.getObjValAs? String "to",
           object := ← j.getObjValAs? String "object", method := ← j.getObjValAs? String "method",
           expires := ← j.getObjValAs? Nat "until" }

/-- A package compiled as an object's code: artifact, entry type, declared laws. -/
structure Built where
  artifact : Json
  ty : Ty
  laws : Law
  assumptions : Minidregg.Theory.ObjectiveBendTyping.Assumptions

structure World where
  /-- The current library, every library a journaled object was compiled under (by pin),
      and the text of the world law that judges a library change. -/
  library : Option Library := none
  libraries : Std.HashMap String Library := {}
  libraryLaw : String := ""
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
  /-- Memory only: prepared reprograms by `programKey`. -/
  programs : Std.HashMap String Program := {}
  /-- The logical clock, moved only by `world-advance` entries. -/
  clock : Nat := 0
  /-- Suspension entries still waiting, in journal order. -/
  suspended : Array Json := #[]
  /-- Every grant an admitted turn made, by id; a revocation marks it. -/
  grants : Std.HashMap String Grant := {}
  /-- Posts transport confirmed, by AT URI: the object the post speaks for and, when it was
      made for an awaited slot, that slot as `{principal, intent}`. -/
  posts : Std.HashMap String (String × Option Json) := {}
  /-- The principal that alone moves the clock and confirms posts ("" = anyone), and the
      hourly posting cap; both set by the `settings` entry of the first open that names them. -/
  clockPrincipal : String := ""
  postQuota : Nat := 16
  settled : Bool := false
  /-- Source modules by CID, from `module` entries: the journal carries each source once and
      compile inputs name it by `cid`. -/
  modules : Std.HashMap String String := {}
  /-- Memory only: compiled packages by the digest of their compile inputs, so replay and
      repeated creation compile each distinct package once. -/
  builds : Std.HashMap String Built := {}

def identityKey (principal intent : String) : String :=
  (Json.arr #[toJson principal, toJson intent]).compress

end Delvetalk.Host
