/- The durable half of the host: objects and the world that holds them. Pure data.
   The journal (Journal.lean) is the only source of a World; Ops.lean is the only
   writer. Nothing here depends on an evaluator. -/
import Delvetalk.Package
import Delvetalk.Entry
import Delvetalk.Host.Blocks
import Theory.ObjectiveBendCheckpointV3
import Std.Data.HashMap

namespace Delvetalk.Host
open Lean (Json toJson)
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
open Delvetalk.Theory.ObjectiveBendTypes (Ty DataBounds)
open Delvetalk.Compiler.ObjectiveBendLaw (LawExpr)

/- Every capacity of the host's world kernel, in one place. A request beyond
    any of them is refused as a request error and journals nothing. -/
namespace Limits
-- Shared kernel bounds (ticks, heap, stack, nodes, bytes, data depth, documents, offers) live in Delvetalk/Limits.lean; this host will read them from there.
def maxObjects : Nat := 10000
def maxObjectIdBytes : Nat := 128
/-- Spells one interpretation answers as `proposals` (MENU §2.2: the prompt asks for at most three). -/
def spellsPerReply : Nat := 3
/-- The characters of a card an interpretation shows the model (docs/FLEX.md §2). -/
def cardShownChars : Nat := 1400
/-- The edition of what replay derives from a journal (HOST-HANDOFF §6, "Replay edition"): a journal's
    first entry records it as `replay`, and a host opens only a journal of its own edition. Bump it
    with every change to what replay derives (judging, a derived field, an index replay checks).
    1: before host12 (no field); 2: host12 (evictions and changes owed as facts, lineage, reservations);
    3: host14 (root entries, ignored and shadowed entries, moderation, the metarule widened to the opener,
    later settings, `unposted`); 4: host16 (roots read by their cells: `scalar`, `fields`, `rows`,
    `spans`; the per-cell bound and the storage ledger by changed cells); 5: host17 (a layered package's
    shape is its stack's: public methods, relations and law shape kept from below, `compileObject`; the
    law's relational atoms judged, what a law cites recorded as roots); 6: host18 (a send refused transiently
    stays pending, `attempts` and `next` on it, up to `deliveryAttempts`); 7: host19 (a Bend law's context
    names the turn's `sender`, read on replay from the pending delivery the entry consumes); 8: kernel16
    (a card's own refusal is the class `cardRefused`, its reason a term: checkpoint term tag 26 and the
    packets of every refusing program changed shape); 9: host22 (rules and wants placed on things as
    kind-4 changes, rules fired and wants posed at commit, journaled `placed`, `fired`, `unfired`,
    `wanted`, `unwanted` and re-derived; `request.verb` from `act`; the last bump the overhaul plans). -/
def replayEdition : Nat := 9
/-- Model calls one world starts per clock day (1440 units), opener included (docs/OPERATIONS.md §b,
    "Spend caps"): interpretations started plus attempts. `world-settings {modelQuota}` moves it. -/
def modelQuota : Nat := 2000
/-- Bytes of a root act's or a moderation power's `reason`/`reading`. -/
def maxReasonBytes : Nat := 256
/-- Model results one interpretation takes before a transient failure is its verdict (HOST-HANDOFF
    5.107): the first `interpretAttempts - 1` transient failures are journaled `attempted`. -/
def interpretAttempts : Nat := 8
/-- The longest backoff between model attempts, in clock units. -/
def interpretBackoffMax : Nat := 60
def maxSourceBytes : Nat := 64
/-- The one name rule (codex agent 14, docs 5): an object id, and the card a spell names, is
    1..`maxObjectIdBytes` of these (ASCII, so characters are bytes). `world/lib/Spell.obend`'s
    `cardAlphabet()` is the same string. -/
def nameAlphabet : String := "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-:/._"
/-- Rows a relation holds when its declaration names no limit (`Decl.limit` 0). -/
def maxRelationRows : Nat := 4096
def maxPrincipalBytes : Nat := 128
def maxIntentBytes : Nat := 256
def maxRoots : Nat := 64
def maxWrites : Nat := 64
def maxEditsPerWrite : Nat := 256
/-- One entry's canonical record in the block store. -/
def maxEntryBytes : Nat := 1048576
def maxJournalEntries : Nat := 1000000
/-- A journal's bytes, its chain and its block store (OPERATIONS §c 1). An open holds the chain and
    reads only the snapshot and the entries after it (`Blocks`, `Snapshot.reopen`), so the bound is
    the disk's, not memory's. It is met at append (`durable`), never first at a restart. -/
def maxJournalBytes : Nat := 4294967296
/-- The last bytes under `maxJournalBytes` that only refusals are written into: an append that would
    reach them is refused `capacity` (`maxJournalBytes`), and that refusal fits. -/
def journalHeadroom : Nat := 1048576
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
/-- Times a send refused transiently (`capacity`, `budget`, `staleRoot`, …) is delivered before that
    refusal is its last: each retry waits for the clock to move past the refusal's. -/
def deliveryAttempts : Nat := 4
def sendsPerTurn : Nat := 32
/-- Rules placed on one object, and wants (docs/OVERHAUL.md §2 conflict 2): what its text carries and
    its kind's `under` carries are bounded by `maxLawClauses` in each text. -/
def rulesPerObject : Nat := 32
def wantsPerObject : Nat := 32
/-- Verbs grown on one object (docs/FOUNDATION.md §10: sixteen a thing; `ungrow` makes room). -/
def verbsPerObject : Nat := 16
/-- A grown verb's reading, in characters: what the verb does, as the grower says it. -/
def verbReadingMax : Nat := 200
def verbNameMax : Nat := 32
/-- Clock units in a day: the chronicle's day (docs/FOUNDATION.md §10), and the model's day (`modelQuota`). -/
def clockDay : Nat := 1440
/-- Lines one day's chronicle says before `and N more`. -/
def chronicleLines : Nat := 48
/-- Rules one commit fires, over every object it wrote; the rest are journaled `unfired`. -/
def rulesPerCommit : Nat := 8
/-- How many rule firings deep a chain goes: a turn a rule's spell delivered fires its own rules one
    level down, and past this depth a rule is `unfired` (a chain of rules ends sooner than `maxDepth`). -/
def ruleDepth : Nat := 4
/-- Undelivered sends held by the world. -/
def maxPending : Nat := 4096
/-- Ticks of one turn: the default and the ceiling a request may ask for (the kernel's own cap). -/
def maxTurnTicks : Nat := 1000000
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
/-- Source text of a package offered as a program (`reprogram`, `extend`, a `create` of source, `check`):
    the kernel's `Bounds.maxPackageBytes` (128 KiB, KERNEL-HANDOFF §25 item 1). -/
def maxPackageBytes : Nat := Bounds.maxPackageBytes
/-- Law text of an `amend`, and the clauses in it. -/
def maxLawBytes : Nat := 4096
def maxLawClauses : Nat := 16
/-- Bytes of the reading a card's own refusal journals (`refuse(line)`, class `cardRefused`): a law
    reading's size; a longer one is kept to its first characters within it, then `…`. -/
def maxRefusalBytes : Nat := 4096
/-- How deep `under "O"` citations are followed: a cited law's `under` is judged one level down, and at
    depth 0 an `under` is false, so a cycle ends (docs/LAW.md §4 F). -/
def lawDepth : Nat := 4
/-- Scratch worlds (docs/FEDERATION.md §3): how many one principal holds open, the journal and object
    bounds of each, and the home world's clock minutes after its last op at which it is discarded. -/
def scratchPerPrincipal : Nat := 2
def scratchJournalBytes : Nat := 16777216
def scratchObjects : Nat := 1000
def scratchMinutes : Nat := 360
/-- A turn's messages to another world one host serves (docs/FEDERATION.md §2): one `call` or `send`
    across per turn (a delivered turn may cross again: the ledger's `depth`, which crosses with the
    message, bounds the chain), and the clock units a call across waits for the target's receipt before
    it is refused `timedOut`. -/
def crossingsPerTurn : Nat := 1
def crossingPatience : Nat := 60
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
/-- The longest value of a declared `source` form field (Bend source; `Form.Kind.source`): the program bound. -/
def formSourceMax : Nat := Bounds.maxPackageBytes
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
  /-- The entry decoded and checked once; every run of it starts from this (`Turn.startEntry`,
      `Turn.resumeEntry`, `Package.executeDataEntryStored`), never from the packet JSON. -/
  entry : Option Delvetalk.CheckedEntry := none
  /-- The checkpoint dictionary of the entry's program (`Dictionary.ofProgram`), built once with it:
      every yield encodes against it and every resumption decodes against it. -/
  dictionary : Option Delvetalk.Theory.ObjectiveBendCheckpoint.Dictionary := none

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

/-- A post reserved against its source's hourly quota (HOST-HANDOFF 5.107), by intent: the source
    (`delve` counts against `postQuota`; any other none), the clock hour it was reserved in, whether
    it was released (the post certainly did not leave) or posted, and how many times the intent was
    reserved before (a released intent may be reserved again). -/
structure Reservation where
  source : String
  hour : Nat
  released : Bool := false
  posted : Bool := false
  round : Nat := 0
  deriving Inhabited

/-- A rule or a want placed on a thing by a hand (docs/OVERHAUL.md §3; KERNEL-HANDOFF §27 item 1): its
    name, unique across the thing's text and its placed lines; who placed it (a rule fires under them;
    they or the thing's owner remove it); the height of the entry that placed it; and the line as the
    one renderer writes it (`Clause.render`), with its parse. -/
structure Placed where
  name : String
  owner : String
  since : Nat
  line : String
  clause : Delvetalk.Compiler.ObjectiveBendLaw.Clause
  deriving BEq, Inhabited

def Placed.json (r : Placed) : Json :=
  Json.mkObj [("name", toJson r.name), ("owner", toJson r.owner), ("since", toJson r.since), ("line", toJson r.line)]

/-- A placed line as a snapshot or a journal holds it; its clause re-parsed by the one parser. -/
def Placed.ofJson (j : Json) : Except String Placed := do
  let line ← j.getObjValAs? String "line"
  let clause ← Delvetalk.Compiler.ObjectiveBendLaw.parseClause line
  return { name := ← j.getObjValAs? String "name", owner := ← j.getObjValAs? String "owner",
           since := ← j.getObjValAs? Nat "since", line, clause }

/-- A verb grown on a thing (docs/FOUNDATION.md §10; OVERHAUL §2): its name, which a spell names as
    it names a declared form (`delvetalk <thing> <name>`) and which the act carries as `request.verb`;
    who grew it and the height of the entry that grew it; what it does, in the grower's words; what it
    takes (`text`, a line, or "" for none); and `does`, the rule placed with it in the same entry that
    gives it consequence (`when: request.verb == "<name>"`), "" for a gesture (a line and a tend). -/
structure Verb where
  name : String
  grower : String
  height : Nat
  reading : String
  takes : String := "text"
  does : String := ""
  deriving BEq, Inhabited

def Verb.json (v : Verb) : Json :=
  Json.mkObj ([("name", toJson v.name), ("by", toJson v.grower), ("at", toJson v.height), ("reading", toJson v.reading),
    ("takes", toJson v.takes)] ++ (if v.does.isEmpty then [] else [("does", toJson v.does)]))

def Verb.ofJson (j : Json) : Except String Verb := do
  return { name := ← j.getObjValAs? String "name", grower := ← j.getObjValAs? String "by",
           height := ← j.getObjValAs? Nat "at", reading := ← j.getObjValAs? String "reading",
           takes := ← j.getObjValAs? String "takes", does := (j.getObjValAs? String "does").toOption.getD "" }

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
  /-- The State fields the new code declares `fixed`. -/
  fixed : List String := []
  /-- The conventional definitions its entry module declares (the artifact's `declares`). -/
  declares : List String := []

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
  /-- Its State's `fixed` fields (the artifact's `fixed`): set by `initial()` or the creating seed,
      never by an edit; no lens or `set` names them. -/
  fixed : List String := []
  /-- The conventional definitions its entry module declares, derived ones included (the artifact's
      `declares`). -/
  declares : List String := []
  /-- The rules and the wants hands placed on it (`world.rule`, `world.want`, the host spells), in the
      order placed; what its text and its kind carry are read from the texts (`Ops.carried`). -/
  rules : List Placed := []
  wants : List Placed := []
  /-- The verbs hands grew on it (`grow`), in the order grown: its spells after the forms its package
      declares, each run by its `act`. -/
  verbs : List Verb := []

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
  /-- What the holder's card says of it ("lent by …: ring, until clock N"); "" for none. -/
  reading : String := ""
  deriving BEq

def Grant.json (g : Grant) : Json :=
  Json.mkObj ([("id", toJson g.id), ("grantor", toJson g.grantor), ("holder", toJson g.holder),
    ("to", toJson g.to), ("object", toJson g.object), ("method", toJson g.method), ("until", toJson g.expires)] ++
    (g.fixed.map fun f => [("fixed", f)]).getD [] ++ (g.uses.map fun n => [("uses", toJson n)]).getD [] ++
    (if g.reading.isEmpty then [] else [("reading", toJson g.reading)]))

def Grant.ofJson (j : Json) : Except String Grant := do
  return { id := ← j.getObjValAs? String "id", grantor := ← j.getObjValAs? String "grantor",
           holder := ← j.getObjValAs? String "holder", to := ← j.getObjValAs? String "to",
           object := ← j.getObjValAs? String "object", method := ← j.getObjValAs? String "method",
           expires := ← j.getObjValAs? Nat "until", fixed := (j.getObjVal? "fixed").toOption,
           uses := (j.getObjValAs? Nat "uses").toOption, reading := (j.getObjValAs? String "reading").toOption.getD "" }

/-- A post transport confirmed (a `posted` entry at `height`): the object it speaks for; when it
    was made for an awaited slot, that slot as `{principal, intent}`; when it carried one of the
    object's publications, its `page` and section (`part`, "" for the whole page). -/
structure Post where
  object : String
  slot : Option Json := none
  page : String := ""
  part : String := ""
  height : Nat := 0
  /-- Why the post left the town (an `unposted` entry: our own post deleted on Delve or Zulip); "" while it stands. -/
  unposted : String := ""

def Post.json (uri : String) (p : Post) : Json :=
  Json.mkObj ([("uri", toJson uri), ("object", toJson p.object)] ++ (p.slot.map fun s => [("slot", s)]).getD [] ++
    (if p.page.isEmpty then [] else [("page", toJson p.page), ("section", toJson p.part)]) ++
    [("height", toJson p.height)] ++ (if p.unposted.isEmpty then [] else [("unposted", toJson p.unposted)]))

def Post.ofJson (j : Json) : Except String (String × Post) := do
  return (← j.getObjValAs? String "uri",
    { object := ← j.getObjValAs? String "object", slot := (j.getObjVal? "slot").toOption,
      page := (j.getObjValAs? String "page").toOption.getD "", part := (j.getObjValAs? String "section").toOption.getD "",
      height := (j.getObjValAs? Nat "height").toOption.getD 0,
      unposted := (j.getObjValAs? String "unposted").toOption.getD "" })

/-- A package compiled as an object's code: artifact, entry type, declared laws. -/
structure Built where
  artifact : Json
  ty : Ty
  laws : Law
  assumptions : Delvetalk.Theory.ObjectiveBendTyping.Assumptions
  /-- The relations its entry module's `relations()` declares, unchecked against the state type. -/
  relations : List RelDecl := []
  /-- The methods it declares public (`publicMethods`), with what each layer below declared: its table's
      other rows are protocol or helpers. -/
  exposed : List String
  /-- Whether it declares a Bend law, and whether that law reads (`lawReads`): the top layer's when it
      declares one, else the code's below. -/
  lawShape : Bool × Bool := (false, false)
  /-- The rules and wants its entry module's text declares: placed on an object made of it with no law
      text given, owned by its creator (`Ops.makeObject`). -/
  lines : List Delvetalk.Compiler.ObjectiveBendLaw.Clause := []

/-- One change of an object's version, as the moved-root rule reads it (`Ops.movedRootAdmits`): the
    version it produced and the height of the entry that made it. Its edits are read from that entry
    when asked (`Ops.touchEdits`): a write of edits (kinds 0 and 3, `Law.editKind`) whose steps decode
    gives every edit other than `keep`, then a `retract` of each key the declared retention evicted;
    any other change (a reprogram, an amendment, a root `set`) gives none. -/
structure Touch where
  version : Nat
  height : Nat
  deriving Inhabited

/-- One object's change at a height (`World.changes`): the version it reached and the principal whose
    entry made it. What `changed {since, prefix, after}` reads, newest back (docs/METAPHYSICS.md §5). -/
structure Change where
  height : Nat
  object : String
  version : Nat
  principal : String
  deriving Inhabited

/-- Where the journal says what an object is: the heights of the entries that set its version, its
    pin and its law text, as they stand (`Ops.anchorsAfter`). A snapshot's objects are checked against
    them at open, so a forger who recomputes a snapshot's CIDs still meets the chain. -/
structure Anchor where
  version : Nat := 0
  pin : Nat := 0
  law : Nat := 0
  /-- The entry naming the CID of its placed rules, wants and verbs (`Ops.placedIn`), 0 for none. -/
  placed : Nat := 0
  /-- The entry setting its read policy (`Ops.readPolicyIn`). -/
  read : Nat := 0
  deriving Inhabited, BEq

/-- The clock hour's counts (`world-status.hour`, docs/ROOT.md §2.3): turns journaled (admitted,
    refused, suspended), refusals by class, interpretations started and model attempts. Derived by
    `record`; a new hour starts them again. -/
structure HourCounts where
  hour : Nat := 0
  turns : Nat := 0
  refused : List (String × Nat) := []
  interpretations : Nat := 0
  attempts : Nat := 0

def HourCounts.json (h : HourCounts) : Json :=
  Json.mkObj [("hour", toJson h.hour), ("turns", toJson h.turns),
    ("refused", Json.mkObj (h.refused.map fun (c, n) => (c, toJson n))),
    ("interpretations", toJson h.interpretations), ("attempts", toJson h.attempts)]

def Reservation.json (r : Reservation) : Json :=
  Json.mkObj [("source", toJson r.source), ("hour", toJson r.hour), ("released", toJson r.released),
    ("posted", toJson r.posted), ("round", toJson r.round)]

def Reservation.ofJson (j : Json) : Except String Reservation := do
  return { source := ← j.getObjValAs? String "source", hour := ← j.getObjValAs? Nat "hour",
           released := ← j.getObjValAs? Bool "released", posted := ← j.getObjValAs? Bool "posted",
           round := ← j.getObjValAs? Nat "round" }

def HourCounts.ofJson (j : Json) : Except String HourCounts := do
  return { hour := ← j.getObjValAs? Nat "hour", turns := ← j.getObjValAs? Nat "turns",
           refused := ← (← (← j.getObjVal? "refused").getObj?).toList.mapM fun (c, n) => do return (c, ← n.getNat?),
           interpretations := ← j.getObjValAs? Nat "interpretations", attempts := ← j.getObjValAs? Nat "attempts" }

/-- What a turn may reach of the other worlds one host serves (docs/FEDERATION.md §2), built by `serve`
    for each request. `read world plan responseType bounds reader ticks` is that world's own answer to
    the read Plan (`view`, `viewField`, `viewAt`, `viewDerived`, `card`, `inspect`, its object
    named in that world), judged there under `reader`, with the citation the reading turn journals
    (`{world, object, version, stateCid, height, head}`) and the ticks left; none for a world not
    served here. `serves world reader` says whether a `call` or `send` to `world` can be carried. -/
structure Foreign where
  read : String → Data → Ty → DataBounds → String → Nat → Option (Data × Json × Nat) := fun _ _ _ _ _ _ => none
  serves : String → String → Bool := fun _ _ => false

instance : Inhabited Foreign := ⟨{}⟩

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
  /-- The journal: the chain in memory, each entry read from the block store when asked (`Blocks`). -/
  entries : Entries := {}
  /-- Identity key (principal, intent) to entry index. The first entry wins. -/
  receipts : Std.HashMap String Nat := {}
  /-- Identity key to the binding a carry kept from the chains before (`Ops.identityRow`: the identity, its
      request digests, the entry's hash, height and outcome tag and class), read from the `carried` genesis
      (`Ops.carriedIdentities`) and never from a snapshot: a retry of an intent the world before admitted
      answers that receipt. -/
  carriedIds : Std.HashMap String Json := {}
  /-- Object id to indices of admitted or creating entries touching it. -/
  touched : Std.HashMap String (Array Nat) := {}
  /-- Per object, its admitted writes in version order (`Touch`): what changed since a version is
      read from the newest back, never by scanning the journal. -/
  touches : Std.HashMap String (Array Touch) := {}
  /-- Per object, the entries that set its version, pin and law (`Anchor`). Derived by `record`. -/
  anchors : Std.HashMap String Anchor := {}
  /-- Every object change in height order, the inverse of `touches` (height to objects): an admitted
      entry's creations and writes, a `created` entry's object, a root write of state. Derived by `record`. -/
  changes : Array Change := #[]
  /-- Memory only, set per request: the request came on `serve`'s public socket naming the opener
      (`resident: true`), so the opener acts as any resident (`openerActs`): an ordinary turn runs,
      the opener's privileges (amending another's thing, revoking any grant, the powers, naming an
      owner) are the root socket's (docs/ROOT.md §1.4). Never journaled: replay admits what either did. -/
  resident : Bool := false
  /-- Memory only: the objects this world may hold (`Limits.maxObjects`, or lower for this process:
      `world-open {maxObjects}`, a scratch world's `Limits.scratchObjects`). -/
  objectBound : Nat := Limits.maxObjects
  /-- Memory only, set per request by `serve`: the other worlds it serves, for reads (`Foreign`). -/
  foreign : Foreign := {}
  /-- Per object, each rule's last firing or refusal to fire, by rule name: `{height, id}` (fired: the
      delivery it staged) or `{height, why}` (unfired), the newest replacing. Derived by `record` from
      admitted entries' `fired` and `unfired`. -/
  ruleLog : Std.HashMap String (List (String × Json)) := {}
  /-- Per object, the wants that held of it after the newest entry that wrote it, each with the height
      of the entry that made it true (a want's `since`). Derived by `record` from `wanted`/`unwanted`. -/
  wanting : Std.HashMap String (List (String × Nat)) := {}
  /-- Per thing, the writes its law has refused (`request.refusedBy`): the entries whose outcome is
      `lawRefused` naming it (`Ops.lawRefusedOf`). Derived by `record`. -/
  refusedBy : Std.HashMap String Nat := {}
  /-- Where each clock day's entries begin: `(day, height)` for every day an entry was journaled in,
      the day of an entry the clock before it over `Limits.clockDay`. Derived by `record`; the
      chronicle reads a day's span of the journal by it (docs/FOUNDATION.md §10). -/
  days : Array (Nat × Nat) := #[]
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
  /-- The world's name among those one host serves (docs/FEDERATION.md §1), journaled once by a
      `named` entry; "" before one is. -/
  name : String := ""
  settled : Bool := false
  /-- Interpretations one principal may start per clock hour (`world-open {interpretQuota}`, journaled
      in `settings` when named; 48 otherwise). The opener and the clock principal are exempt. -/
  interpretQuota : Nat := 48
  /-- Interpretations started, by the principal of the turn that started them: the clock hour of the
      last one and how many that hour. Derived by `record` from `suspended` entries with an
      `interpretation`. -/
  interpretsStarted : Std.HashMap String (Nat × Nat) := {}
  /-- Posting reservations by intent (`world-post-reserve`). Derived by `record`. -/
  reservations : Std.HashMap String Reservation := {}
  /-- Model attempts by interpretation id: the transient failures journaled `attempted` and the clock
      at which the next may be asked. Derived by `record`. -/
  attempts : Std.HashMap String (Nat × Nat) := {}
  /-- Checkpoint blocks by CID, as the index of the entry whose `blocks` carries each: a suspension
      journals each block of its checkpoint's tokens once, and names the rest (`tokenTree`). Derived by `record`. -/
  blocks : Std.HashMap String Nat := {}
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
  /-- Source modules by CID, as the index of the entry whose `sources` carries each: the journal
      carries each source once and compile inputs name it by `cid`. Derived by `record`. -/
  modules : Std.HashMap String Nat := {}
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
  /-- Root acts journaled (`root:<n>` intents). Derived by `record`. -/
  rootActs : Nat := 0
  /-- A root `card` override: the text `world-card` answers in place of `render`. Derived by `record`. -/
  cards : Std.HashMap String String := {}
  /-- Principals quieted (`quiet`): the clock until which their turns are refused, and the reading.
      Derived by `record`. -/
  quiets : Std.HashMap String (Nat × String) := {}
  /-- Objects hidden (`hide`): the read policy `show` restores. Derived by `record`. -/
  hidden : Std.HashMap String Json := {}
  /-- Heights this world replays as refused (docs/ROOT.md §1.3): the ignore set of the whole journal,
      found before replay starts (`Snapshot.ignoresFrom`), kept in a snapshot, and re-derived after every
      `ignore`/`unignore`. -/
  ignoring : List Nat := []
  /-- Every height an `ignore` or `unignore` of the journal names: after the lowest, an entry that no
      longer replays is shadowed, since an unignored entry changes later ones as an ignored one does. -/
  ignoreNamed : List Nat := []
  /-- Heights ignored by the root entries recorded so far (what an `ignore`'s `before` reads). -/
  ignored : List Nat := []
  /-- Entries that no longer replay after an ignored one, skipped: `{height, by, reason}`. -/
  shadowed : Array Json := #[]
  /-- Model calls one clock day may start (`Limits.modelQuota`; `world-settings`), and the day's count. -/
  modelQuota : Nat := Limits.modelQuota
  modelDay : Nat × Nat := (0, 0)
  /-- This clock hour's counts. -/
  hourCounts : HourCounts := {}

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
