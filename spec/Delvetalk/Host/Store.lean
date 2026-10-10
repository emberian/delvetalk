/- The durable half of the host: objects and the world that holds them. Pure data.
   The journal (Journal.lean) is the only source of a World; Ops.lean is the only
   writer. Nothing here depends on an evaluator. -/
import Delvetalk.Package
import Delvetalk.Entry
import Theory.ObjectiveBendCheckpointV2
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
/-- Rows a relation holds when its declaration names no limit (`Decl.limit` 0). -/
def maxRelationRows : Nat := 4096
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
/-- Subscriptions to one object (`subscribe`, WHOLENESS §3). -/
def subscribersPerObject : Nat := 64
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
/-- A principal's display handle in the registry (a DNS name is at most 253). -/
def maxHandleBytes : Nat := 256
/-- Interpretations waiting on one object, counted apart from its awaits. -/
def pendingInterpretationsPerObject : Nat := 64
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
/-- `publish` Plans one turn may make; bytes of a page title and a section name. -/
def publishesPerTurn : Nat := 4
def maxTitleBytes : Nat := 256
/-- Ids one `objects` listing answers. -/
def listPage : Nat := 64
/-- Bytes of a post's AT URI and CID. -/
def maxUriBytes : Nat := 512
/-- A text field of a form derived from a method's input type: at most the characters a card
    reader shows. A natural field: at most this. -/
def formTextMax : Nat := 1400
def formNaturalMax : Nat := 1000000000
/-- Journal entries between snapshots, and bytes of one snapshot file. -/
def snapshotEvery : Nat := 1000
def maxSnapshotBytes : Nat := 268435456
end Limits

/-- A parsed `law NAME: EXPR` list; empty is "no law". -/
abbrev Law := List (String × LawExpr)

/-- A relation an object's package declares (`def relations() -> Lists.List<Relation.Decl>`): the
    state field holding it, its key columns in order, and the most rows it keeps (0: the default
    `Limits.maxRelationRows`); past it the oldest by key order are dropped (`retain: dropOldest`). -/
structure RelDecl where
  field : String
  key : List String
  limit : Nat := 0
  deriving BEq, Repr

def RelDecl.cap (d : RelDecl) : Nat := if d.limit == 0 then Limits.maxRelationRows else d.limit

/-- A compiled method of an object's package: its checked packet and entry type. -/
structure Compiled where
  packet : Json
  type : Ty
  /-- The packet's declared type bounds and rigid variables: recursive types
      (a `List<T>` field) are data only under them. -/
  bounds : DataBounds
  rigid : List Nat
  /-- The entry decoded and checked once; every run of it starts from this (`Turn.startEntryStep`,
      `Turn.resumeEntryStep`, `Package.executeDataEntry`), never from the packet JSON. -/
  entry : Option Delvetalk.CheckedEntry := none
  /-- The checkpoint dictionary of the entry's program (`Dictionary.ofProgram`), built once with it:
      every yield encodes against it and every resumption decodes against it. -/
  dictionary : Option Minidregg.Theory.ObjectiveBendCheckpoint.Dictionary := none

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
  | exposed
  | principals (allowed : List String)

def ReadPolicy.permits : ReadPolicy → String → Bool
  | .exposed, _ => true
  | .principals allowed, who => allowed.contains who

def ReadPolicy.json : ReadPolicy → Json
  | .exposed => toJson "public"
  | .principals allowed => Json.mkObj [("principals", toJson allowed)]

/-- A compiled replacement package for an object, ready to judge. The state
    migration, when there is one, is a compiled function OldState -> NewState. -/
structure Program where
  inputs : Json
  pin : String
  stateType : Ty
  bounds : DataBounds
  migration : Option Compiled
  /-- The artifact's method table and whether it declares a Bend law (and `lawReads`). -/
  methods : Json := Json.arr #[]
  predicate : Bool := false
  predicateReads : Bool := false
  /-- The compiled packet's digest, observed beside the source pin. -/
  packet : String := ""
  /-- The relations the new code declares. -/
  relations : List RelDecl := []

structure Object where
  /-- The object's pin: the CID of its sealed source closure (the artifact's `sourcesSha256`, the
      Canonical CID of its modules in order, library modules included). What the journal binds. -/
  pin : String
  law : Law
  /-- The law as text, the form it is amended in; `law` is its parse. -/
  lawText : String := ""
  version : Nat
  state : Data
  /-- The entry definition's type: a closed record of first-order data. -/
  stateType : Ty
  bounds : DataBounds := []
  read : ReadPolicy := .exposed
  /-- Ledger of turns started on this object (creation may only lower it). -/
  chain : Ledger := Ledger.start
  /-- The journaled compile inputs (modules, limits); a method is one more `entry`. -/
  inputs : Json := Json.null
  /-- Digest of `inputs`, the key of this object's compiled methods. -/
  inputsKey : String := ""
  /-- The compiler's method table of the pinned artifact (`[{name, input, result, activity, context}]`),
      each row the package does not make public marked `helper: true` (`markHelpers`). -/
  methods : Json := Json.arr #[]
  /-- The artifact's `law: {present, reads}`: the package declares `def law(old, new, request)`,
      and `def lawReads()` beside it. -/
  predicate : Bool := false
  predicateReads : Bool := false
  /-- The object told `ended {receipt, how}` when an activity of this one ends `timedOut`,
      `broken` or `budget` ("" for none); fixed at creation. -/
  supervisor : String := ""
  /-- The highest `n` among this object's children `<id>/<kind>/<n>`: a create with an empty
      `requireAbsent` mints the next one. Derived from the creations the journal records. -/
  minted : Nat := 0
  /-- The `packetSha256` this host compiled the object's sources to: an audit observation
      (journaled as `compiled.packet`), never compared on replay. -/
  packet : String := ""
  /-- The reading of each law clause the package gave one (`law NAME "reading": EXPR`), kept
      while the clause is the package's: a refusal by it says `refused NAME: reading`. -/
  readings : List (String × String) := []
  /-- The relations its package declares (`relations()`); their fields are kept canonical. -/
  relations : List RelDecl := []

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
  /-- Attenuation: the part of the callee's argument the grant fixes (Data wire), merged with the
      caller's at each use; a field the caller gives otherwise is refused `grantConflict`. -/
  fixed : Option Json := none
  /-- Uses left (each admitted call or send under the grant spends one); none is unlimited. -/
  uses : Option Nat := none
  deriving BEq

def Grant.json (g : Grant) : Json :=
  Json.mkObj ([("id", toJson g.id), ("grantor", toJson g.grantor), ("holder", toJson g.holder),
    ("to", toJson g.to), ("object", toJson g.object), ("method", toJson g.method), ("until", toJson g.expires)] ++
    (g.fixed.map fun f => [("fixed", f)]).getD [] ++ (g.uses.map fun n => [("uses", toJson n)]).getD [])

def Grant.ofJson (j : Json) : Except String Grant := do
  return { id := ← j.getObjValAs? String "id", grantor := ← j.getObjValAs? String "grantor",
           holder := ← j.getObjValAs? String "holder", to := ← j.getObjValAs? String "to",
           object := ← j.getObjValAs? String "object", method := ← j.getObjValAs? String "method",
           expires := ← j.getObjValAs? Nat "until", fixed := (j.getObjVal? "fixed").toOption,
           uses := (j.getObjValAs? Nat "uses").toOption }

/-- A post transport confirmed (a `posted` entry at `height`): the object it speaks for; when it
    was made for an awaited slot, that slot as `{principal, intent}`; when it carried one of the
    object's publications, its `page` and section (`part`, "" for the whole page). -/
structure Post where
  object : String
  slot : Option Json := none
  page : String := ""
  part : String := ""
  height : Nat := 0

def Post.json (uri : String) (p : Post) : Json :=
  Json.mkObj ([("uri", toJson uri), ("object", toJson p.object)] ++ (p.slot.map fun s => [("slot", s)]).getD [] ++
    (if p.page.isEmpty then [] else [("page", toJson p.page), ("section", toJson p.part)]) ++
    [("height", toJson p.height)])

def Post.ofJson (j : Json) : Except String (String × Post) := do
  return (← j.getObjValAs? String "uri",
    { object := ← j.getObjValAs? String "object", slot := (j.getObjVal? "slot").toOption,
      page := (j.getObjValAs? String "page").toOption.getD "", part := (j.getObjValAs? String "section").toOption.getD "",
      height := (j.getObjValAs? Nat "height").toOption.getD 0 })

/-- A package compiled as an object's code: artifact, entry type, declared laws. -/
structure Built where
  artifact : Json
  ty : Ty
  laws : Law
  assumptions : Minidregg.Theory.ObjectiveBendTyping.Assumptions
  /-- The relations its entry module's `relations()` declares, unchecked against the state type. -/
  relations : List RelDecl := []
  /-- The methods it declares public (`publicMethods`); its table's other rows are protocol or helpers. -/
  exposed : List String

/-- A standing subscription (WHOLENESS §3): after every admitted write that touches `field` of
    `object`, `subscriber`'s receiver `method` (`changed` unless the subscription named another) is
    sent the change, run under `principal` (who subscribed it and must still be permitted to view
    `object`). One per (subscriber, object, field). -/
structure Subscription where
  subscriber : String
  principal : String
  object : String
  field : String
  method : String := "changed"
  deriving BEq, Repr, Inhabited

/-- The method is written only when it is not `changed`. -/
def Subscription.json (x : Subscription) : Json :=
  Json.mkObj ([("subscriber", toJson x.subscriber), ("principal", toJson x.principal),
    ("object", toJson x.object), ("field", toJson x.field)] ++
    (if x.method == "changed" then [] else [("method", toJson x.method)]))

def Subscription.ofJson (j : Json) : Except String Subscription := do
  return ⟨← j.getObjValAs? String "subscriber", ← j.getObjValAs? String "principal",
    ← j.getObjValAs? String "object", ← j.getObjValAs? String "field",
    (j.getObjValAs? String "method").toOption.getD "changed"⟩

/-- Do two subscriptions stand for the same (subscriber, object, field)? -/
def Subscription.sameAs (x y : Subscription) : Bool :=
  x.subscriber == y.subscriber && x.object == y.object && x.field == y.field

/-- One admitted write of an object, as the moved-root rule reads it (`Ops.movedRootAdmits`): the
    version it produced and, for an ordinary write (kind 0 only) whose steps decode, every edit
    other than `keep` as `(field, edit)` in step order; none otherwise. Derived by `record` from
    `writes[].edits`, so replay and snapshot resume rebuild it and nothing is journaled twice. -/
structure Touch where
  version : Nat
  edits : Option (List (String × Data))
  deriving Inhabited

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
  /-- Per object, its admitted writes in version order (`Touch`): what changed since a version is
      read from the newest back, never by scanning the journal. -/
  touches : Std.HashMap String (Array Touch) := {}
  /-- Standing subscriptions by the object they watch, in the order they were made; derived by
      `record` from entries' `subscribes`/`unsubscribes`. -/
  subscriptions : Std.HashMap String (Array Subscription) := {}
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
  /-- Posts transport confirmed, by AT URI. -/
  posts : Std.HashMap String Post := {}
  /-- The principal that alone moves the clock and confirms posts ("" = anyone), and the
      hourly posting cap; both set by the `settings` entry of the first open that names them. -/
  clockPrincipal : String := ""
  postQuota : Nat := 16
  /-- The principal that opened the world (`world-open {opener}`, in the settings entry; ""
      when none was named): it alone may create an object for a named owner. -/
  opener : String := ""
  settled : Bool := false
  /-- Interpretations one principal may start per clock hour (`world-open {interpretQuota}`, journaled
      in `settings` when named; 48 otherwise). The opener and the clock principal are exempt. -/
  interpretQuota : Nat := 48
  /-- Interpretations started, by the principal of the turn that started them: the clock hour of the
      last one and how many that hour. Derived by `record` from `suspended` entries with an
      `interpretation`. -/
  interpretsStarted : Std.HashMap String (Nat × Nat) := {}
  /-- Reply-is-address: the identity of the first turn that answered each recorded post (an
      entry's `replyTo`), which `awaitPost` settles on. -/
  replies : Std.HashMap String (String × String) := {}
  /-- Checkpoint blocks by CID, from entries' `blocks`: a suspension journals each block of its
      checkpoint's tokens once, and names the rest (`tokenTree`). Derived by `record`. -/
  blocks : Std.HashMap String (Array Json) := {}
  /-- Memory only: the packet digest a resumed snapshot cached for each compile inputs key; a
      rebuild by this binary that differs is counted in `recompiledDifferently`. -/
  cachedPackets : Std.HashMap String String := {}
  /-- A forked world's origin, from its genesis entry (`world-fork`): `{world, height, cid}`. -/
  forkedFrom : Option Json := none
  /-- Memory only: objects this process rebuilt whose packet digest differs from the one a resumed
      snapshot cached for the same inputs (`world-status`; informational). -/
  recompiledDifferently : Nat := 0
  /-- The principal registry: display handle by principal, from `principal` entries. -/
  handles : Std.HashMap String String := {}
  /-- Source modules by CID, from `module` entries: the journal carries each source once and
      compile inputs name it by `cid`. -/
  modules : Std.HashMap String String := {}
  /-- Offers admitted turns retained, by addressee: (entry index, ordinal in the entry). -/
  outbox : Std.HashMap String (Array (Nat × Nat)) := {}
  /-- Publications admitted turns retained, for transport to post: (entry index, ordinal). -/
  published : Array (Nat × Nat) := #[]
  /-- Memory only: each package's closure prepared once (`Package.prepareRequest`), by the digest
      of its resolved compile inputs; every method of it compiles from this. -/
  requests : Std.HashMap String Package.PreparedRequest := {}
  /-- Memory only: compiled packages by the digest of their compile inputs, so replay and
      repeated creation compile each distinct package once. -/
  builds : Std.HashMap String Built := {}

/-- `w` with the memory-only compile caches of `src` (a world a step derived from `w`): what a
    step compiled stays compiled whether or not its world is kept. -/
def World.withCachesOf (w src : World) : World :=
  { w with compiled := src.compiled, requests := src.requests, builds := src.builds, programs := src.programs }

/-- A world's memory-only compile caches. Every key is a content address (the digest of compile
    inputs that name their library by pin and their modules by CID), so a process carries them from
    one world it opens to the next (`Session.stepWorld`). -/
structure Caches where
  compiled : Std.HashMap String Compiled := {}
  requests : Std.HashMap String Package.PreparedRequest := {}
  builds : Std.HashMap String Built := {}
  programs : Std.HashMap String Program := {}

def World.caches (w : World) : Caches := ⟨w.compiled, w.requests, w.builds, w.programs⟩

def World.withCaches (w : World) (c : Caches) : World :=
  { w with compiled := c.compiled, requests := c.requests, builds := c.builds, programs := c.programs }

def identityKey (principal intent : String) : String :=
  (Json.arr #[toJson principal, toJson intent]).compress

end Delvetalk.Host
