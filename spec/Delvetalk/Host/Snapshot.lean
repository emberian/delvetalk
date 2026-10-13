/- Snapshots: the store and every index `record` derives, at a journal height, in canonical bytes, so
   `world-open` reads them and replays only the entries after it. A snapshot is derived: the journal
   stays the only source of truth, and a snapshot that fails any check is refused by name and the
   previous one (or full replay) used.

   File: `<journal>.snapshot.<height>.cbor`, the DAG-CBOR of `{body, cid}` where `cid` is the CID
   of `body`'s canonical bytes. `body` holds the store (`storeJson`: objects with their state, law,
   read policy, ledger, compile inputs by CID, method table; the state types by pin; libraries;
   grants; posts; settings; the clock) and the indexes (`indexJson`: receipts, the history and
   change indexes, the rules' last firings, the wants that hold, the clock days, pending deliveries, suspensions, the outbox, publications, where
   each source and block lies, reservations, attempts, the root and moderation indexes, the hour's
   and the day's counts).

   Loading checks, in order: the CID, the edition, its height against the chain, its head against
   the chain's hash at that height, that no later `ignore` names a height at or before it, each
   object's state against the entry its newest change names, and that every later entry, read and
   checked against the chain, replays on it. `world-open {verify: true}` replays from height 0 and
   compares every snapshot with the replayed world, which is the proof of the fast path. -/
import Delvetalk.Host.Ops
import Delvetalk.Canonical

namespace Delvetalk.Host.Snapshot
open Lean (Json toJson)
open Delvetalk.Theory.ObjectiveBendTypes (Ty DataBounds)
open Delvetalk.Compiler.ObjectiveBendDataWire (dataJson decodeData)

def edition : String := "delvetalk.snapshot.v5"

/-- The edition before (`v4`: anchors of a version, a pin and a law only; no `refusedBy` from the binary that
    wrote the first), which a carry still reads (HOST-HANDOFF §6, "The snapshot body is the carry's contract");
    deleted with the next. -/
def previousEdition : String := "delvetalk.snapshot.v4"

/-- The index keys `previousEdition` may not write: a carry from it starts them empty. -/
def addedKeys : List String := ["refusedBy"]

/-! ## Writing -/

def tyJson (t : Ty) : Json := Delvetalk.Theory.ObjectiveBendTyping.typeJson t

def tyOf (j : Json) : Except String Ty :=
  return (← Delvetalk.Theory.ObjectiveBendTyping.decodeTypeWith #[] Limits.dataDepth Limits.dataDepth j).1

def boundsJson (bounds : DataBounds) : Json :=
  Json.arr (bounds.toArray.map fun (i, t) => Json.mkObj [("index", toJson i), ("type", tyJson t)])

def boundsOf (j : Json) : Except String DataBounds := do
  (← j.getArr?).toList.mapM fun e => do return (← natField e "index", ← tyOf (← e.getObjVal? "type"))

def sortedBy {α : Type} (xs : List α) (key : α → String) : List α :=
  (xs.toArray.qsort fun a b => key a < key b).toList

/-- Compile inputs with each source the journal carries named by its CID; a source no entry
    carries (a reprogram's or an extension's module) stays whole. -/
def knownByCid (w : World) (inputs : Json) : Json :=
  let compact := compactInputs inputs
  let restore := fun (m : Json) (src : String) =>
    if w.modules.contains (sourceCid src) then m
    else Json.mkObj [("name", (m.getObjVal? "name").toOption.getD Json.null), ("source", toJson src)]
  match inputs.getObjVal? "modules", compact.getObjVal? "modules" with
  | .ok (.arr full), .ok (.arr ms) =>
    compact.setObjVal! "modules" (.arr ((ms.zip full).map fun (m, f) =>
      match f.getObjValAs? String "source" with
      | .ok src => restore m src
      | .error _ => m))
  | _, _ => match inputs.getObjValAs? String "source" with
    | .ok src => if w.modules.contains (sourceCid src) then compact else inputs
    | .error _ => compact

/-! ### The indexes -/

def mapJson {α : Type} (m : Std.HashMap String α) (f : α → Json) : Json :=
  Json.mkObj (m.toList.map fun (k, v) => (k, f v))

def mapOf {α : Type} (j : Json) (f : Json → Except String α) : Except String (Std.HashMap String α) := do
  (← j.getObj?).toList.foldlM (init := {}) fun m (k, v) => do return m.insert k (← f v)

def pairJson (a b : Nat) : Json := Json.arr #[toJson a, toJson b]

def pairOf (j : Json) : Except String (Nat × Nat) := do
  let #[a, b] := ← j.getArr? | throw "an index pair is not two naturals"
  return (← a.getNat?, ← b.getNat?)

def arrOf {α : Type} (j : Json) (f : Json → Except String α) : Except String (Array α) := do
  (← j.getArr?).mapM f

/-- Every index `record` derives from the entries up to the world's height (`Ops.recordCore`,
    `recordActs`, `recordInert`), so an open reads them instead of reading those entries. -/
def indexJson (w : World) : Json :=
  Json.mkObj [
    ("receipts", mapJson w.receipts toJson),
    ("touched", mapJson w.touched toJson),
    ("touches", mapJson w.touches fun ts => Json.arr (ts.map fun t => pairJson t.version t.height)),
    ("anchors", mapJson w.anchors fun a => Json.arr #[toJson a.version, toJson a.pin, toJson a.law, toJson a.placed, toJson a.read, toJson a.maker]),
    ("changes", Json.arr (w.changes.map fun c => Json.arr #[toJson c.height, toJson c.object, toJson c.version, toJson c.principal])),
    ("ruleLog", mapJson w.ruleLog fun xs => Json.mkObj xs),
    ("wanting", mapJson w.wanting fun xs => Json.mkObj (xs.map fun (n, h) => (n, toJson h))),
    ("wantFlips", Json.arr (w.wantFlips.map (·.json))),
    ("wantCites", mapJson w.wantCites fun xs => toJson xs),
    ("wantReaders", mapJson w.wantReaders fun xs => toJson xs),
    ("wantClock", mapJson w.wantClock toJson),
    ("refusedBy", mapJson w.refusedBy toJson),
    ("days", Json.arr (w.days.map fun (d, h) => pairJson d h)),
    ("pending", Json.arr w.pending),
    ("suspended", Json.arr w.suspended),
    ("handles", mapJson w.handles toJson),
    ("modules", mapJson w.modules toJson),
    ("blocks", mapJson w.blocks toJson),
    ("outbox", mapJson w.outbox fun xs => Json.arr (xs.map fun (a, b) => pairJson a b)),
    ("published", Json.arr (w.published.map fun (a, b) => pairJson a b)),
    ("reservations", mapJson w.reservations (·.json)),
    ("attempts", mapJson w.attempts fun (a, b) => pairJson a b),
    ("interpretsStarted", mapJson w.interpretsStarted fun (a, b) => pairJson a b),
    ("rootActs", toJson w.rootActs),
    ("cards", mapJson w.cards toJson),
    ("quiets", mapJson w.quiets fun (u, r) => Json.arr #[toJson u, toJson r]),
    ("hidden", mapJson w.hidden id),
    ("ignored", toJson w.ignored), ("ignoring", toJson w.ignoring), ("ignoreNamed", toJson w.ignoreNamed),
    ("shadowed", Json.arr w.shadowed),
    ("modelDay", pairJson w.modelDay.1 w.modelDay.2), ("hour", w.hourCounts.json),
    ("forkedFrom", w.forkedFrom.getD Json.null)]

/-- `w` with the indexes `indexJson` wrote. -/
def installIndex (w : World) (j : Json) : Except String World := do
  let field := fun (k : String) => j.getObjVal? k
  let nats := fun (x : Json) => (Lean.fromJson? x : Except String (List Nat))
  let quiet := fun (x : Json) => do
    let #[u, r] := ← x.getArr? | throw "a quiet is not a clock and a reading"
    return (← u.getNat?, ← r.getStr?)
  let change := fun (x : Json) => do
    let #[h, o, v, p] := ← x.getArr? | throw "a change is not four fields"
    return ({ height := ← h.getNat?, object := ← o.getStr?, version := ← v.getNat?, principal := ← p.getStr? } : Change)
  return { w with
    receipts := ← mapOf (← field "receipts") (·.getNat?)
    touched := ← mapOf (← field "touched") fun x => arrOf x (·.getNat?)
    touches := ← mapOf (← field "touches") fun x => arrOf x fun t => do
      let (version, height) ← pairOf t
      return ({ version, height } : Touch)
    anchors := ← mapOf (← field "anchors") fun x => do
      match ← x.getArr? with
      | #[v, p, l, d, r, m] => return ({ version := ← v.getNat?, pin := ← p.getNat?, law := ← l.getNat?, placed := ← d.getNat?, read := ← r.getNat?, maker := ← m.getNat? } : Anchor)
      | #[v, p, l, d, r] => return ({ version := ← v.getNat?, pin := ← p.getNat?, law := ← l.getNat?, placed := ← d.getNat?, read := ← r.getNat? } : Anchor)
      -- `previousEdition`'s, read by a carry alone (`checkAnchors` without `whole`).
      | #[v, p, l] => return ({ version := ← v.getNat?, pin := ← p.getNat?, law := ← l.getNat? } : Anchor)
      | _ => throw "an anchor is not six heights"
    changes := ← arrOf (← field "changes") change
    ruleLog := ← mapOf (← field "ruleLog") fun x => do return (← x.getObj?).toList
    wanting := ← mapOf (← field "wanting") fun x => do (← x.getObj?).toList.mapM fun (n, h) => do return (n, ← h.getNat?)
    wantFlips := ← arrOf ((field "wantFlips").toOption.getD (Json.arr #[])) WantFlip.ofJson
    wantCites := ← mapOf (← field "wantCites") fun x => (Lean.fromJson? x : Except String (List String))
    wantReaders := ← mapOf (← field "wantReaders") fun x => (Lean.fromJson? x : Except String (List String))
    wantClock := ← mapOf (← field "wantClock") (·.getBool?)
    refusedBy := ← mapOf (← field "refusedBy") (·.getNat?)
    days := ← arrOf (← field "days") pairOf
    pending := ← (← field "pending").getArr?
    suspended := ← (← field "suspended").getArr?
    handles := ← mapOf (← field "handles") (·.getStr?)
    modules := ← mapOf (← field "modules") (·.getNat?)
    blocks := ← mapOf (← field "blocks") (·.getNat?)
    outbox := ← mapOf (← field "outbox") fun x => arrOf x pairOf
    published := ← arrOf (← field "published") pairOf
    reservations := ← mapOf (← field "reservations") Reservation.ofJson
    attempts := ← mapOf (← field "attempts") pairOf
    interpretsStarted := ← mapOf (← field "interpretsStarted") pairOf
    rootActs := ← (← field "rootActs").getNat?
    cards := ← mapOf (← field "cards") (·.getStr?)
    quiets := ← mapOf (← field "quiets") quiet
    hidden := ← mapOf (← field "hidden") pure
    ignored := ← nats (← field "ignored")
    ignoring := ← nats (← field "ignoring")
    ignoreNamed := ← nats (← field "ignoreNamed")
    shadowed := ← (← field "shadowed").getArr?
    modelDay := ← pairOf (← field "modelDay")
    hourCounts := ← HourCounts.ofJson (← field "hour")
    forkedFrom := match field "forkedFrom" with
      | .ok .null | .error _ => none
      | .ok f => some f }

/-! ### The store -/

/-- The store of `w`: what replay computes at a price. A law that does not read back from its text is
    refused: the snapshot would judge by another law than replay. A fork's genesis carries it too. -/
def storeJson (w : World) : Except String Json := do
  let objects := sortedBy w.objects.toList (·.1)
  let mut types : List (String × Json) := []
  let mut out : Array Json := #[]
  for (id, o) in objects do
    unless (match parseLawText o.lawText with | .ok l => l == o.law | .error _ => false) do throw s!"the law of {id} does not read back from its text"
    unless types.any (·.1 == o.pin) do
      types := types ++ [(o.pin, Json.mkObj [("pin", toJson o.pin), ("stateType", tyJson o.stateType),
        ("bounds", boundsJson o.bounds), ("methods", o.methods), ("predicate", toJson o.predicate),
        ("predicateReads", toJson o.predicateReads)])]
    out := out.push (Json.mkObj ([("id", toJson id), ("pin", toJson o.pin), ("law", toJson o.lawText),
      ("version", toJson o.version), ("state", dataJson o.state), ("stateCid", toJson o.stateCid), ("read", o.read.json),
      ("maker", toJson o.maker), ("chain", o.chain.json), ("compile", knownByCid w o.inputs), ("supervisor", toJson o.supervisor)] ++
      (if o.behaviour == 0 then [] else [("behaviour", toJson o.behaviour)]) ++
      (if o.minted == 0 then [] else [("minted", toJson o.minted)]) ++
      (if o.packet.isEmpty then [] else [("packet", toJson o.packet)]) ++
      (if o.readings.isEmpty then [] else [("readings", Json.arr (o.readings.toArray.map fun (n, r) =>
        Json.mkObj [("name", toJson n), ("reading", toJson r)]))]) ++
      (if o.relations.isEmpty then [] else [("relations", Json.arr (o.relations.toArray.map fun d =>
        Json.mkObj [("field", toJson d.field), ("key", toJson d.key), ("limit", toJson d.limit)]))]) ++
      (if o.fixed.isEmpty then [] else [("fixed", toJson o.fixed)]) ++
      (if o.declares.isEmpty then [] else [("declares", toJson o.declares)]) ++
      (if o.rules.isEmpty then [] else [("rules", Json.arr (o.rules.toArray.map (·.json)))]) ++
      (if o.wants.isEmpty then [] else [("wants", Json.arr (o.wants.toArray.map (·.json)))]) ++
      (if o.verbs.isEmpty then [] else [("verbs", Json.arr (o.verbs.toArray.map (·.json)))]) ++
      (match o.madeFrom with | some m => [("madeFrom", m)] | none => [])))
  let libraries := sortedBy w.libraries.toList (·.1)
  let grants := sortedBy w.grants.toList (·.1)
  let posts := sortedBy w.posts.toList (·.1)
  return Json.mkObj [("clock", toJson w.clock),
    ("library", toJson ((w.library.map (·.pin)).getD "")), ("libraryLaw", toJson w.libraryLaw),
    ("libraries", Json.arr (libraries.toArray.map fun (pin, l) =>
      Json.mkObj [("pin", toJson pin), ("modules", modulesJson l.modules)])),
    ("settings", Json.mkObj ([("settled", toJson w.settled), ("clock", toJson w.clockPrincipal),
      ("postQuota", toJson w.postQuota), ("interpretQuota", toJson w.interpretQuota)] ++
      (if w.modelQuota == Limits.modelQuota then [] else [("modelQuota", toJson w.modelQuota)]) ++
      (if w.opener.isEmpty then [] else [("opener", toJson w.opener)]) ++
      (if w.name.isEmpty then [] else [("name", toJson w.name)]))),
    ("types", Json.arr (types.toArray.map (·.2))), ("objects", Json.arr out),
    ("grants", Json.arr (grants.toArray.map fun (_, g) => (g.json).setObjVal! "revoked" (toJson g.revoked))),
    ("grantTombstones", Json.arr (w.grantTombstones.map (fun (g : GrantTombstone) => g.json))),
    ("posts", Json.arr (posts.toArray.map fun (uri, p) => p.json uri))]

/-- The body of a snapshot of `w`: its edition, height and head, the store and the indexes. -/
def body (w : World) : Except String Json := do
  let store ← storeJson w
  return Json.mkObj (((store.getObj?.toOption.map (·.toList)).getD []) ++ [("edition", toJson edition),
    ("height", toJson w.height), ("head", toJson w.head), ("index", indexJson w)])

def fileOf (journal : String) (height : Nat) : String := s!"{journal}.snapshot.{height}.cbor"

/-- The canonical bytes of a snapshot of `w`: the DAG-CBOR map `{cid: text, body: bytes}` whose
    `body` is the canonical bytes of the body and `cid` their CID, so a reader checks the CID over
    the bytes as stored before it decodes anything. -/
def encode (w : World) : Except String ByteArray := do
  let bytes ← Delvetalk.Canonical.encodeJson (← body w)
  let open_ := Delvetalk.Canonical.text (Delvetalk.Canonical.head ByteArray.empty 5 2) "cid"
  let withCid := Delvetalk.Canonical.text (Delvetalk.Canonical.text open_ (Delvetalk.Canonical.cid bytes)) "body"
  return (Delvetalk.Canonical.head withCid 2 bytes.size).append bytes

/-- The CID and the body bytes of a snapshot file. -/
def split (b : ByteArray) : Except String (String × ByteArray) := do
  let text := fun (pos : Nat) => do
    if pos ≥ b.size || (b.get! pos).toNat / 32 != 3 then throw "the snapshot is not {cid, body}"
    let (n, p) ← Delvetalk.Canonical.readArg b (pos + 1) ((b.get! pos).toNat % 32)
    if p + n > b.size then throw "truncated snapshot"
    let some s := String.fromUTF8? (b.extract p (p + n)) | throw "snapshot text is not UTF-8"
    return (s, p + n)
  unless b.size > 0 && b.get! 0 == 0xa2 do throw "the snapshot is not {cid, body}"
  let (k1, p) ← text 1
  let (cid, p) ← text p
  let (k2, p) ← text p
  unless k1 == "cid" && k2 == "body" do throw "the snapshot is not {cid, body}"
  unless p < b.size && (b.get! p).toNat / 32 == 2 do throw "the snapshot body is not bytes"
  let (n, p) ← Delvetalk.Canonical.readArg b (p + 1) ((b.get! p).toNat % 32)
  unless p + n == b.size do throw "the snapshot body is not its length"
  return (cid, b.extract p (p + n))

/-- Snapshot files beside `journal`, newest first. -/
def files (journal : String) : IO (List (Nat × String)) := do
  let path : System.FilePath := journal
  let dir := (path.parent.map (·.toString)).getD "."
  let dir := if dir.isEmpty then "." else dir
  let some base := path.fileName | return []
  let pfx := base ++ ".snapshot."
  let mut found : List (Nat × String) := []
  for e in ← System.FilePath.readDir dir do
    if e.fileName.startsWith pfx && e.fileName.endsWith ".cbor" then
      let middle := ((e.fileName.drop pfx.length).dropRight ".cbor".length).toString
      if let some h := middle.toNat? then found := (h, e.path.toString) :: found
  return (found.toArray.qsort fun a b => a.1 > b.1).toList

/-- How many snapshot files a journal keeps; older ones are removed when a new one is written. -/
def kept : Nat := 3

/-- Write a snapshot of `w` beside `journal` (through a temporary file and a rename), and remove
    all but the newest `kept`. -/
def write (journal : String) (w : World) : IO (Except String Nat) := do
  try
    match encode w with
    | .error e => return .error e
    | .ok bytes =>
      if bytes.size > Limits.maxSnapshotBytes then return .error "snapshot exceeds its byte capacity"
      let target := fileOf journal w.height
      IO.FS.writeBinFile (target ++ ".tmp") bytes
      IO.FS.rename (target ++ ".tmp") target
      for (_, f) in (← files journal).drop kept do
        try IO.FS.removeFile f catch _ => pure ()
      return .ok w.height
  catch e => return .error s!"snapshot write failed: {e}"

/-- `base` with the store a snapshot body (or a fork's genesis) holds: objects, types, libraries,
    grants, posts, settings, the clock. Compile inputs name sources through `base`'s journal. -/
def install (b : Json) (base : World) (naming : Naming := .cells) : Except String World := do
  let mut w := base
  let mut libraries : Std.HashMap String Library := {}
  for l in ← (← b.getObjVal? "libraries").getArr? do
    let pin ← l.getObjValAs? String "pin"
    libraries := libraries.insert pin { pin, modules := ← parseModules (← l.getObjVal? "modules") }
  let current ← b.getObjValAs? String "library"
  let library ← if current.isEmpty then pure none else match libraries[current]? with
    | some l => pure (some l)
    | none => throw "the current library is not among its libraries"
  let settings ← b.getObjVal? "settings"
  w := { w with libraries, library, libraryLaw := ← b.getObjValAs? String "libraryLaw",
                settled := ← settings.getObjValAs? Bool "settled",
                clockPrincipal := ← settings.getObjValAs? String "clock",
                postQuota := ← natField settings "postQuota",
                interpretQuota := (settings.getObjValAs? Nat "interpretQuota").toOption.getD 48,
                modelQuota := (settings.getObjValAs? Nat "modelQuota").toOption.getD Limits.modelQuota,
                opener := (settings.getObjValAs? String "opener").toOption.getD "",
                name := (settings.getObjValAs? String "name").toOption.getD "" }
  let mut types : Std.HashMap String (Ty × DataBounds × Json × Bool × Bool) := {}
  for t in ← (← b.getObjVal? "types").getArr? do
    types := types.insert (← t.getObjValAs? String "pin") (← tyOf (← t.getObjVal? "stateType"),
      ← boundsOf (← t.getObjVal? "bounds"), ← t.getObjVal? "methods", ← t.getObjValAs? Bool "predicate",
      ← t.getObjValAs? Bool "predicateReads")
  let mut objects : Std.HashMap String Object := {}
  for o in ← (← b.getObjVal? "objects").getArr? do
    let id ← o.getObjValAs? String "id"
    let pin ← o.getObjValAs? String "pin"
    let some (stateType, bounds, methods, predicate, predicateReads) := types[pin]?
      | throw s!"object {id} names a type no entry holds"
    let lawText ← o.getObjValAs? String "law"
    let inputs ← expandInputs w (← o.getObjVal? "compile")
    let state ← decodeData Limits.dataDepth (← o.getObjVal? "state")
    unless state.conformsUnder bounds stateType do throw s!"the state of {id} does not conform to its type"
    let some cid := (o.getObjValAs? String "stateCid").toOption | throw s!"object {id} carries no state CID"
    let relations : List RelDecl := (((o.getObjVal? "relations").toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap fun d =>
      match d.getObjValAs? String "field", d.getObjValAs? (List String) "key", d.getObjValAs? Nat "limit" with
      | .ok field, .ok key, .ok limit => some { field, key, limit }
      | _, _, _ => none
    let law ← parseLawText lawText
    let version ← natField o "version"
    let read ← parseRead (some (← o.getObjVal? "read"))
    let chain ← parseChain (some (← o.getObjVal? "chain"))
    let placedOf := fun (k : String) => (((o.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]).toList.mapM Placed.ofJson
    let allocationEntry : Option Nat := ((w.anchors[id]?).map (fun (a : Anchor) => a.maker)).filter (fun (h : Nat) => h != 0)
    let mut allocationOrigin : Option (Nat × String) := allocationEntry.bind fun (h : Nat) =>
      (w.entries.get? (h - 1)).bind fun (entry : Json) => (makerIn entry id).map (h, ·)
    if allocationOrigin.isNone then
      for index in (w.touched.getD id #[]).reverse do
        if let some maker := (w.entries.get? index).bind (makerIn · id) then
          allocationOrigin := some (index + 1, maker)
          break
    if allocationOrigin.isNone then
      if let some maker := w.entries.genesis?.bind (makerIn · id) then
        allocationOrigin := some (w.entries.base + 1, maker)
    if allocationEntry.isNone then
      if let some (height, _) := allocationOrigin then
        let anchor := w.anchors.getD id {}
        w := { w with anchors := w.anchors.insert id { anchor with maker := height } }
    let allocation := ((allocationOrigin.map (·.2)).getD (let owner := ownerOf state; if owner.isEmpty then w.opener else owner))
    let obj : Object :=
      { pin := pin
        law := law
        lawText := lawText
        version := version
        behaviour := (o.getObjValAs? Nat "behaviour").toOption.getD 0
        cells := Delvetalk.Turn.StateCells.of (cellDecls relations) state
        stateType := stateType
        bounds := bounds
        read := read
        chain := chain
        inputs := inputs
        inputsKey := inputsKeyOf inputs
        methods := methods
        predicate := predicate
        predicateReads := predicateReads
        supervisor := (o.getObjValAs? String "supervisor").toOption.getD ""
        maker := (o.getObjValAs? String "maker").toOption.getD allocation
        minted := (o.getObjValAs? Nat "minted").toOption.getD 0
        packet := (o.getObjValAs? String "packet").toOption.getD ""
        readings := artifactReadings (Json.mkObj [("laws", (o.getObjVal? "readings").toOption.getD (Json.arr #[]))])
        relations := relations
        fixed := (o.getObjValAs? (List String) "fixed").toOption.getD []
        declares := (o.getObjValAs? (List String) "declares").toOption.getD []
        rules := ← placedOf "rules"
        wants := ← placedOf "wants"
        verbs := ← (((o.getObjVal? "verbs").toOption.bind (·.getArr?.toOption)).getD #[]).toList.mapM Verb.ofJson
        madeFrom := (o.getObjVal? "madeFrom").toOption }
    unless cid == naming.state obj do throw s!"the state of {id} is not its CID's"
    objects := objects.insert id obj
  let mut grants : Std.HashMap String Grant := {}
  for g in ← (← b.getObjVal? "grants").getArr? do
    let grant ← Grant.ofJson g
    grants := grants.insert grant.id { grant with revoked := ← g.getObjValAs? Bool "revoked" }
  let mut posts : Std.HashMap String Post := {}
  for p in ← (← b.getObjVal? "posts").getArr? do
    let (uri, post) ← Post.ofJson p
    posts := posts.insert uri post
  let grantTombstones ← (((b.getObjVal? "grantTombstones").toOption.bind (·.getArr?.toOption)).getD #[]).mapM GrantTombstone.ofJson
  if grantTombstones.size > Limits.maxGrantTombstones then throw "grant tombstones exceed maxGrantTombstones"
  w := { w with objects, grants, grantTombstones, posts, clock := ← natField b "clock" }
  let endings : List (String × GrantTombstone) := w.grants.toList.filterMap fun (entry : String × Grant) =>
    let (id, g) := entry
    if !g.revoked && w.clock ≤ g.expires then none else
      (grantHistory w id).bind fun (row : Json) => (GrantTombstone.ofJson row).toOption.map (id, ·)
  return compactGrants w endings

/-! ## Store-installing geneses: forks and carries

A fork (`world-fork`) and a carry (`delvetalk-obend carry`, `Host/Carry.lean`) each start a new journal
whose genesis entry holds another world's store as a snapshot body holds it (`storeJson`, every source
whole), that world's pending deliveries and suspended activities written out whole, its handle
registry, and `previous` naming the entry it was taken at. A fork (`forked`) is one principal's view at
a height, under that principal as opener and clock. A carry (`carried`) is the whole world at its head
read by a newer binary: its settings, every object, the indexes it stands on (`carriedKeys`) and the old
chain's entries by hash, so every receipt of the world before still resolves by its slug. Replay starts
from the installed genesis (`installGenesis`) and never reads the world before it. -/

/-- A suspended entry as a genesis holds it: its checkpoint, its argument and its interpretation written
    out whole, since a genesis carries no blocks. -/
def wholeSuspension (w : World) (e : Json) : Except String Json := do
  let outcome ← e.getObjVal? "outcome"
  let activity ← outcome.getObjVal? "activity"
  let activity ← if hostResumed e then pure activity else pure (activity.setObjVal! "checkpoint" (← expandSuspended w e))
  let activity := Json.mkObj ((((activity.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "argumentBlock")) ++
    [("argument", ← activityArgument w activity)])
  let outcome := outcome.setObjVal! "activity" activity
  let outcome := match expandInterpretation w outcome with
    | some i => outcome.setObjVal! "interpretation" i
    | none => outcome
  return e.setObjVal! "outcome" outcome

/-- The object a suspended entry's activity runs on. -/
def suspendedObject (e : Json) : String :=
  ((e.getObjVal? "outcome").toOption.bind (·.getObjVal? "activity" |>.toOption)
    |>.bind (·.getObjValAs? String "object" |>.toOption)).getD ""

/-- The indexes a carry keeps beyond the store, the pending deliveries, the suspensions and the handles,
    each as `indexJson` writes it: what the world stands on that no object's state holds (the rules'
    last firings, the wants that hold, the refusals each law made, posting reservations, model attempts, the quotas' counts, the root acts'
    count, the moderation: cards, quiets, hidden). Every other index names entries of the old chain. -/
def carriedKeys : List String :=
  ["ruleLog", "wanting", "wantFlips", "refusedBy", "reservations", "attempts", "interpretsStarted", "rootActs", "cards", "quiets",
   "hidden", "modelDay", "hour"]

/-- A genesis entry chained to `cid`: `tag` and its origin, the store of `shown` with every source its
    objects compile from carried once in the entry's `sources` (as any entry carries the sources it is
    first to name) and named by CID, the pending deliveries and whole suspensions given, the handles of
    `w`, and `more`. -/
def genesisEntry (w shown : World) (tag principal intent cid : String) (origin : String × Json)
    (pending suspended : Array Json) (more : List (String × Json)) (height : Nat := 1) : Except String Json := do
  let sources := newSources {} (shown.objects.toList.flatMap fun (_, o) => inputSources o.inputs)
  let cids := (sources.flatMap fun (_, j) => ((j.getArr?.toOption).getD #[]).toList.filterMap
    (·.getObjValAs? String "cid" |>.toOption))
  let state ← storeJson { shown with modules := cids.foldl (fun m c => m.insert c 0) {} }
  let handles := w.handles.toList.toArray.qsort (fun a b => a.1 < b.1) |>.map fun (did, h) =>
    Json.mkObj [("did", toJson did), ("handle", toJson h)]
  let outcome := Json.mkObj ([("tag", toJson tag), origin, ("state", state), ("pending", Json.arr pending),
    ("suspended", Json.arr suspended), ("handles", Json.arr handles)] ++ more)
  return Journal.sealEntry height cid ([("identity", identityJson principal intent), ("roots", rootsJson []),
    ("turn", toJson 0), ("request", toJson (Journal.bodyHash origin.2)), ("outcome", outcome)] ++ sources) (first := true)

/-- The genesis entry of a fork of `w` (the world at `height`, whose entry there is `cid`) for
    `principal`, and the ids it omitted: only objects the principal may view are carried, with their
    grants, pending deliveries and suspended activities. -/
def forkGenesis (w : World) (principal world : String) (height : Nat) (cid : String) :
    Except String (Json × List String) := do
  let carried := w.objects.filter fun _ o => o.read.permits principal
  let omitted := (w.objects.toList.filter fun (id, _) => !carried.contains id).map (·.1) |>.toArray.qsort (· < ·) |>.toList
  let keeps := fun (id : String) => carried.contains id
  let lawText ← libraryLawText principal
  let grants := w.grants.filter fun _ g => keeps g.object
  let grantTombstones : Array GrantTombstone := w.grantTombstones.filter fun (g : GrantTombstone) => keeps g.object
  let shown : World := { w with objects := carried, posts := {}, grants, grantTombstones, opener := principal,
                                clockPrincipal := principal, settled := true, libraryLaw := lawText }
  let pending := w.pending.filter fun p => keeps ((p.getObjValAs? String "to").toOption.getD "")
  let suspended ← (w.suspended.filter fun e => keeps (suspendedObject e)).mapM (wholeSuspension w)
  let origin := Json.mkObj [("world", toJson world), ("height", toJson height), ("cid", toJson cid)]
  let entry ← genesisEntry w shown "forked" principal "fork" cid ("forkedFrom", origin) pending suspended
    [("omitted", toJson omitted)]
  return (entry, omitted)

/-- The world a store-installing genesis (the first of `entries`) starts: its store installed, a carry's
    standing indexes laid over it, the pending deliveries and suspended activities it holds, the handles,
    a fork's origin, and the entry recorded. -/
def installGenesis (entries : Entries) (entry : Json) : Except String World := do
  let outcome ← entry.getObjVal? "outcome"
  -- Compile inputs name the sources the genesis carries by CID (an older fork's are whole).
  let sources ← entrySources entry
  let first := entries.base
  let w ← install (← outcome.getObjVal? "state")
    { entries := entries.upTo (first + 1), height := first, modules := sources.foldl (fun m (c, _) => m.insert c first) {} }
  -- A carry's indexes, each as `indexJson` writes it, over the empty ones of the installed store.
  let w ← match outcome.getObjVal? "index" with
    | .ok carried => installIndex w (carriedKeys.foldl (fun j k => match carried.getObjVal? k with
        | .ok v => j.setObjVal! k v
        | .error _ => j) (indexJson w))
    | .error _ => pure w
  let arr := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
  let handles := (arr "handles").foldl (fun m h => match h.getObjValAs? String "did", h.getObjValAs? String "handle" with
    | .ok d, .ok x => m.insert d x
    | _, _ => m) ({} : Std.HashMap String String)
  let forkedFrom := if tagOf entry == "forked" then (outcome.getObjVal? "forkedFrom").toOption else none
  let cachedPackets := w.objects.fold (fun m _ o => if o.packet.isEmpty then m else m.insert o.inputsKey o.packet) {}
  -- Each object's version is a barrier at the genesis (a touch whose entry writes no edits of it, as a root `set`
  -- is): the writes that made it are the old chain's, which no index here reads, and a carry's move changed cells
  -- no write names. A carried suspension's root read below it is stale, never current by an empty history (codex host 9).
  let touches := w.objects.fold (fun t id o => t.insert id #[({ version := o.version, height := first + 1 } : Touch)]) {}
  let w := { w with pending := arr "pending", suspended := arr "suspended", handles, forkedFrom, cachedPackets,
                    entries := entries.upTo (first + 1), height := first, carriedIds := carriedIdentities entry, touches }
  -- The want index is read off the installed objects (`Ops.reindexWants`), a carry's or a fork's alike.
  let w := reindexWants w (w.objects.toList.map (·.1))
  let identity ← entry.getObjVal? "identity"
  return record w entry (identityKey (← identity.getObjValAs? String "principal") (← identity.getObjValAs? String "intent")) []

/-! ## Reading -/

/-- The checked body of a snapshot file's bytes, refused by name. -/
def verifiedBody (bytes : ByteArray) (height : Nat) (entries : Entries) (editions : List String := [edition]) :
    Except String Json := do
  if bytes.size > Limits.maxSnapshotBytes then throw "exceeds its byte capacity"
  let (cid, raw) ← split bytes
  unless cid == Delvetalk.Canonical.cid raw do throw "its bytes are not its CID's"
  let b ← Delvetalk.Canonical.decodeJson raw Limits.dataDepth
  unless editions.contains (← b.getObjValAs? String "edition") do throw "another snapshot edition"
  unless (← natField b "height") == height do throw "its height is not its file name's"
  if height ≤ entries.base || height > entries.count then throw "the journal is shorter than its height"
  unless entries.hashAt? (height - 1) == some (← b.getObjValAs? String "head") do
    throw "its head is not the journal's hash at its height"
  return b

/-- The world a snapshot body holds over `entries` (its height's prefix): the indexes, then the store. -/
def installBody (b : Json) (entries : Entries) (caches : Caches) : Except String World := do
  let height ← natField b "height"
  let base ← installIndex { entries := entries.upTo height, height, head := ← b.getObjValAs? String "head" } (← b.getObjVal? "index")
  let w ← install b base
  return { w.withCaches caches with
    cachedPackets := w.objects.fold (fun m _ o => if o.packet.isEmpty then m else m.insert o.inputsKey o.packet) {} }

/-- Each object against the entries its anchors name (`World.anchors`): the version, the state's CID
    where that entry names one (by `naming`, the journal's edition's), the pin, the law text, the read policy,
    and its behaviour revision with the rules, wants and verbs placed on it (their CID, `placedIn`; an object with rows no entry commits to
    is not the journal's, and a world whose rows predate their CIDs is replayed whole). A forger who recomputes
    a snapshot's CIDs moves no entry. A carry reading `previousEdition`, whose anchors hold the first three
    alone, checks those (`whole` false). -/
def checkAnchors (w : World) (naming : Naming := .cells) (whole : Bool := true) : Except String Unit := do
  let mut read : Std.HashMap Nat Json := {}
  for (id, o) in w.objects.toList do
    let some a := w.anchors[id]? | throw s!"object {id} is not the journal's"
    unless a.maker != 0 do throw s!"the maker of {id} has no journal anchor"
    let mut entries : List (Nat × Json) := []
    for h in ([a.version, a.pin, a.law, a.maker] ++ (if whole then [a.placed, a.read].filter (· != 0) else [])).eraseDups do
      match read[h]? with
      | some e => entries := (h, e) :: entries
      | none =>
        let some e := w.entries.get? (h - 1) | throw s!"the entry at height {h}, which {id} rests on, is not readable"
        read := read.insert h e
        entries := (h, e) :: entries
    let at_ := fun (h : Nat) => (entries.lookup h).getD Json.null
    unless versionIn (at_ a.version) id == some o.version do throw s!"object {id} is not at the journal's version and pin"
    if let some cid := stateCidIn (at_ a.version) id o.version naming then
      unless cid == naming.state o do throw s!"the state of {id} is not the one the journal commits to at version {o.version}"
    unless pinIn (at_ a.pin) id == some o.pin do throw s!"object {id} is not at the journal's version and pin"
    if let some law := lawIn (at_ a.law) id then
      unless law == o.lawText do throw s!"the law of {id} is not the journal's"
    unless makerIn (at_ a.maker) id == some o.maker do
      throw s!"the maker of {id} is not the journal's"
    if whole then
      unless (if a.read == 0 then none else readPolicyIn (at_ a.read) id) == some o.read.json do
        throw s!"the read policy of {id} is not the journal's"
      unless (if a.placed == 0 then o.unplaced else placedIn (at_ a.placed) id == some (placedCid o)) do
        throw s!"the rules, wants and verbs on {id} are not the journal's"

/-- The height a journal's first entry takes: 1, or for a `carried` genesis (of edition 12 on) the height
    after the head it was carried from, whose heights it continues. -/
def firstHeight (entry : Json) : Nat :=
  match tagOf entry, genesisOrigin entry with
  | "carried", some (_, origin) =>
    if (entry.getObjValAs? Nat "replay").toOption.getD 1 < 12 then 1
    else (origin.getObjValAs? Nat "height").toOption.getD 0 + 1
  | _, _ => 1

/-- The entry at index `i` of `src`, checked against the chain: its record is its CID's (`Entries.get?`
    reads only such), its height is `i + 1` (the first one's `firstHeight`), and it names the entry
    before it (the genesis, or for a fork's or a carry's genesis the entry it was taken at). -/
def checkedEntry (src : Entries) (i : Nat) : Except String Json := do
  let fail {α : Type} (what : String) : Except String α := throw s!"journal broken at height {i + 1}: {what}"
  let some entry := src.get? i | fail "its record is missing or not its CID's"
  unless (entry.getObjValAs? Nat "height").toOption == some (i + 1) do fail "height out of sequence"
  let first := i == src.base
  if first && firstHeight entry != i + 1 then fail s!"a journal's first entry here is at height {firstHeight entry}"
  let previous := (entry.getObjValAs? String "previous").toOption.getD ""
  let expected := if !first then (src.hashAt? (i - 1)).getD "" else match genesisOrigin entry with
    | some (_, origin) => (origin.getObjValAs? String "cid").toOption.getD ""
    | none => Limits.genesis
  unless previous == expected do
    fail (if first && installsStore entry then s!"a {tagOf entry} genesis must chain to the cid it was taken at"
      else "previous hash does not chain")
  return entry

/-- `w` with the entry at its next height replayed from `src` (`Ops.replayStep`), the entries it may
    read being `src`'s up to and including that one. -/
def replayNext (w : World) (src : Entries) : Except String World := do
  let entry ← checkedEntry src w.height
  replayStep { w with entries := src.upTo (w.height + 1) } entry

/-- The ignore set and the named heights the root `ignore`/`unignore` entries of `src` from index
    `start` leave, over `ignoring` and `named` (read in order: the last act on a height wins). An act
    naming a height at or below `floor` (a snapshot's) changes what that snapshot holds. -/
def ignoresFrom (src : Entries) (start : Nat) (ignoring named : List Nat) (floor : Nat := 0) :
    Except String (List Nat × List Nat) := do
  let mut ignoring := ignoring
  let mut named := named
  for i in [start:src.count] do
    let entry ← checkedEntry src i
    unless isIgnoreAct entry do continue
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let h := (outcome.getObjValAs? Nat "height").toOption.getD 0
    if h ≤ floor then throw "an ignore after it changes what it holds"
    ignoring := if actOf outcome == "ignore" then (ignoring.erase h) ++ [h] else ignoring.erase h
    named := if named.contains h then named else named ++ [h]
  return (ignoring, named)

/-- Where replay of a journal starts: a fork's or a carry's installed genesis and one entry consumed, else an
    empty world. -/
def startOf (src : Entries) (caches : Caches := {}) : Except String World := do
  if src.count == src.base then return ({ entries := src.upTo 0 } : World).withCaches caches
  let first ← checkedEntry src src.base
  if installsStore first then return (← installGenesis src first).withCaches caches
  return ({ entries := src.upTo 0 } : World).withCaches caches

/-- Full replay from height 0: the slow path, which `verify` compares every snapshot with. -/
def replayAll (src : Entries) (caches : Caches := {}) : Except String World := do
  let start ← startOf src caches
  let (ignoring, ignoreNamed) ← ignoresFrom src start.height [] []
  let mut w := { start with ignoring, ignoreNamed }
  while w.height < src.count do
    w ← (replayNext w src).mapError fun e => if e.startsWith "journal broken" then e else s!"journal broken at height {w.height + 1}: {e}"
  return w

/-- A world from a snapshot body: the indexes and the store installed, every object's state against
    its anchor, then every later entry checked against the chain and replayed. An `ignore` or
    `unignore` after it that names a height at or before it would change what it holds. -/
def resume (b : Json) (src : Entries) (caches : Caches := {}) : Except String World := do
  let height ← natField b "height"
  let w ← installBody b src caches
  -- The identities a carry kept are the genesis's, never the snapshot's.
  let w := { w with carriedIds := (src.genesis?.map carriedIdentities).getD {} }
  let (ignoring, ignoreNamed) ← ignoresFrom src height w.ignoring w.ignoreNamed height
  checkAnchors w
  let mut w := { w with ignoring, ignoreNamed }
  while w.height < src.count do
    w ← (replayNext w src).mapError fun e => s!"the entry at height {w.height + 1} does not replay on it: {e}"
  return w

/-! ## Opening -/

/-- The block store beside a journal. -/
def storeOf (journal : String) : String := journal ++ ".blocks"

/-- The chain file's links, each naming the one before it (`Blocks.Link`); a line that is not a link
    (the line format, whole entries per line, before the block store) is refused by name. -/
def chainOf (journal content : String) : Except String (Array Link) := do
  let lines := content.splitOn "\n"
  let (complete, tail) := (lines.dropLast, lines.getLast?.getD "")
  if complete.length ≥ Limits.maxJournalEntries then throw "journal exceeds entry capacity"
  let mut out : Array Link := #[]
  for line in complete do
    -- The first link's height is the journal's first (`firstHeight`, checked against its entry).
    let height := match out.back? with | some prev => prev.height + 1 | none => 1
    if out.isEmpty && (line.splitOn "\"outcome\"").length > 1 then
      throw s!"{journal} holds whole entries, one per line (the format before the block store): `delvetalk-obend migrate --journal {journal} --out NEW` writes it as a chain and a block store"
    let some link := Link.ofLine line | throw s!"journal broken at height {height}: unparsable line"
    unless link.height == height || (out.isEmpty && link.height > 0) do throw s!"journal broken at height {height}: height out of sequence"
    if let some prev := out.back? then
      unless link.previous == prev.hash do throw s!"journal broken at height {height}: previous hash does not chain"
    out := out.push link
  unless tail.isEmpty do throw s!"journal broken at height {(out.back?.map (·.height)).getD 0 + 1}: unterminated final line"
  return out

/-- The journal at `journal` as `Entries`: its chain, read whole, over its block store, read only when
    asked. Every link must lie inside the store. -/
def openEntries (journal : String) : IO (Except String Entries) := do
  let chain ← if ← System.FilePath.pathExists journal then IO.FS.readFile journal else pure ""
  let links ← match chainOf journal chain with
    | .ok l => pure l
    | .error e => return .error e
  let store := storeOf journal
  unless ← System.FilePath.pathExists store do
    if links.isEmpty then return .ok { depth := Limits.dataDepth }
    return .error s!"journal broken: its block store {store} is missing"
  let size := (← System.FilePath.metadata store).byteSize.toNat
  let handle ← IO.FS.Handle.mk store .read
  let base := (links[0]?.map (·.height - 1)).getD 0
  let mut e : Entries := { store := some handle, depth := Limits.dataDepth, base, count := base }
  for l in links do
    if l.offset + l.bytes > size then return .error s!"journal broken at height {l.height}: its record lies past the block store's end"
    e := e.pushStored l.hash (l.offset, l.bytes)
  return .ok e

/-- Every entry of the journal at `journal`, read and checked (`root-edit`, `migrate`'s check). -/
def journalEntries (journal : String) : IO (Except String (Array Json)) := do
  match ← openEntries journal with
  | .error e => return .error e
  | .ok src => return ((List.range (src.count - src.base)).map (· + src.base)).toArray.mapM (checkedEntry src)

/-- Entries as a fresh journal: each record appended to `<path>.blocks`, then each link to `path`.
    Neither file may exist. -/
def writeJournal (path : String) (entries : Array Json) : IO (Except String Unit) := do
  try
    if (← System.FilePath.pathExists path) || (← System.FilePath.pathExists (storeOf path)) then
      return .error s!"{path} already exists"
    let mut records := ByteArray.empty
    let mut lines := ""
    for e in entries do
      let r ← match recordBytes e with
        | .ok r => pure r
        | .error err => return .error s!"an entry has no canonical form: {err}"
      let link := Link.of e records.size r.size
      records := records ++ r
      lines := lines ++ link.json.compress ++ "\n"
    IO.FS.writeBinFile (storeOf path) records
    IO.FS.writeFile path lines
    return .ok ()
  catch e => return .error s!"journal write failed: {e}"

/-- What an open did with the snapshots: the height it resumed from (0: full replay) and each
    snapshot it refused, by name. -/
structure Report where
  resumed : Nat := 0
  refused : List (Nat × String) := []

def Report.json (r : Report) : Json :=
  Json.mkObj [("resumed", toJson r.resumed), ("refused", Json.arr (r.refused.toArray.map fun (h, why) =>
    Json.mkObj [("height", toJson h), ("reason", toJson why)]))]

/-- The world `src` holds: from the newest snapshot that passes every check, else by full replay.
    `world-open` and the re-derivation after an `ignore` both come here. -/
def reopen (journal : String) (src : Entries) (caches : Caches := {}) : IO (Except String (World × Report)) := do
  let mut report : Report := {}
  for (height, f) in ← files journal do
    if height > src.count then
      report := { report with refused := report.refused ++ [(height, "the journal is shorter than its height")] }
      continue
    let attempt ← try
        let bytes ← IO.FS.readBinFile f
        pure (verifiedBody bytes height src >>= fun b => resume b src caches)
      catch e => pure (.error s!"unreadable: {e}")
    match attempt with
    | .ok w => return .ok (w, { report with resumed := height })
    | .error e => report := { report with refused := report.refused ++ [(height, e)] }
  return (replayAll src caches).map (·, report)

/-- Open a journal: the newest snapshot that passes every check, else full replay. With `verify`,
    replay everything and compare every snapshot with the replayed world at its height; a snapshot
    that disagrees is refused by name. A journal of another replay edition is refused first. -/
def openJournal (journal : String) (verify : Bool := false) (caches : Caches := {}) :
    IO (Except String (World × Report)) := do
  let src ← match ← openEntries journal with
    | .ok s => pure s
    | .error e => return .error e
  if src.count > src.base then
    let first ← match checkedEntry src src.base with
      | .ok e => pure e
      | .error e => return .error e
    let edition := (first.getObjValAs? Nat "replay").toOption.getD 1
    if edition != Limits.replayEdition then
      return .error s!"journal replay edition {edition}; this host is {Limits.replayEdition}; a world from another host's edition does not reopen here: carry it (`delvetalk-obend carry --from {journal} --out NEW`, over a snapshot at its head written by the binary of its edition)"
  unless verify do return ← reopen journal src caches
  let snaps ← files journal
  let heights := snaps.map (·.1)
  let mut report : Report := {}
  let start ← match startOf src caches with
    | .ok w => pure w
    | .error e => return .error e
  let (ignoring, ignoreNamed) ← match ignoresFrom src start.height [] [] with
    | .ok r => pure r
    | .error e => return .error e
  let mut w := { start with ignoring, ignoreNamed }
  while w.height < src.count do
    match replayNext w src with
    | .ok w' => w := w'
    | .error e => return .error (if e.startsWith "journal broken" then e else s!"journal broken at height {w.height + 1}: {e}")
    if heights.contains w.height then
      let some (_, f) := snaps.find? (·.1 == w.height) | continue
      let bytes ← IO.FS.readBinFile f
      let normalized : Except String Json := do
        let mine ← verifiedBody bytes w.height src
        let installedBody : Except String Json := do
          let installed ← installBody mine src {}
          checkAnchors installed
          body installed
        installedBody.mapError (fun (_ : String) => "it disagrees with replay at its height")
      match normalized, body w with
      | .ok mine, .ok replayed =>
        if mine != replayed then
          report := { report with refused := report.refused ++ [(w.height, "it disagrees with replay at its height")] }
      | .error e, _ | _, .error e =>
        report := { report with refused := report.refused ++ [(w.height, e)] }
  return .ok (w, report)

end Delvetalk.Host.Snapshot
