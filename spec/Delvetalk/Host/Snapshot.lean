/- Snapshots: the store at a journal height, in canonical bytes, so `world-open` replays only
   the entries after it. A snapshot is derived: the journal stays the only source of truth, and
   a snapshot that fails any check is refused by name and the previous one (or full replay) used.

   File: `<journal>.snapshot.<height>.cbor`, the DAG-CBOR of `{body, cid}` where `cid` is the CID
   of `body`'s canonical bytes. `body` holds what replay computes at a price (objects with their
   state, law, read policy, ledger, compile inputs by CID, method table; the state types by pin;
   libraries; grants; posts; settings) and, as cross-checks, what the journal derives cheaply
   (clock, pending deliveries, suspended activities). Everything `record` derives from entries
   (receipts, history index, outbox, modules, pending, suspended, clock) is rebuilt by a
   bookkeeping pass over the entries up to the snapshot height, and must agree with the copies.

   Loading checks, in order: the CID, the edition, its height against the journal, its head against the journal's hash at that height, the
   derived copies, and finally that every later entry replays on it. -/
import Delvetalk.Host.Ops
import Delvetalk.Canonical

namespace Delvetalk.Host.Snapshot
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendTypes (Ty DataBounds)
open Minidregg.Compiler.ObjectiveBendDataWire (dataJson decodeData)

def edition : String := "delvetalk.snapshot.v2"

/-! ## Canonical bytes back to JSON

`Canonical.encodeJson` writes the snapshot; this reads exactly that subset back (unsigned and
negative integers, big naturals, text, arrays, maps with text keys, true, false, null). -/

partial def readArg (b : ByteArray) (pos info : Nat) : Except String (Nat × Nat) := do
  let be := fun (width : Nat) => do
    if pos + width > b.size then throw "truncated snapshot"
    return ((List.range width).foldl (fun acc i => acc * 256 + (b.get! (pos + i)).toNat) 0, pos + width)
  if info < 24 then return (info, pos)
  else if info == 24 then be 1
  else if info == 25 then be 2
  else if info == 26 then be 4
  else if info == 27 then be 8
  else throw "snapshot has an indefinite or reserved length"

partial def readJson (b : ByteArray) (pos depth : Nat) : Except String (Json × Nat) := do
  if depth == 0 then throw "snapshot nesting capacity"
  if pos ≥ b.size then throw "truncated snapshot"
  let ib := (b.get! pos).toNat
  let major := ib / 32
  let info := ib % 32
  if major == 7 then
    if info == 20 then return (Json.bool false, pos + 1)
    else if info == 21 then return (Json.bool true, pos + 1)
    else if info == 22 then return (Json.null, pos + 1)
    else throw "snapshot holds a simple value outside JSON"
  let (n, p) ← readArg b (pos + 1) info
  match major with
  | 0 => return (toJson n, p)
  | 1 => return (toJson (-(Int.ofNat n) - 1), p)
  | 2 =>
    if p + n > b.size then throw "truncated snapshot"
    return (toJson ((b.extract p (p + n)).foldl (fun acc x => acc * 256 + x.toNat) 0), p + n)
  | 3 =>
    if p + n > b.size then throw "truncated snapshot"
    let some s := String.fromUTF8? (b.extract p (p + n)) | throw "snapshot text is not UTF-8"
    return (Json.str s, p + n)
  | 4 =>
    let mut items : Array Json := #[]
    let mut at_ := p
    for _ in [0:n] do
      let (j, q) ← readJson b at_ (depth - 1)
      items := items.push j
      at_ := q
    return (Json.arr items, at_)
  | 5 =>
    let mut fields : Array (String × Json) := #[]
    let mut at_ := p
    for _ in [0:n] do
      let (k, q) ← readJson b at_ (depth - 1)
      let .str key := k | throw "snapshot map key is not text"
      let (v, r) ← readJson b q (depth - 1)
      fields := fields.push (key, v)
      at_ := r
    return (Json.mkObj fields.toList, at_)
  | _ => throw "snapshot holds a CBOR item outside JSON"

def decodeBytes (b : ByteArray) : Except String Json := do
  let (j, p) ← readJson b 0 Limits.dataDepth
  unless p == b.size do throw "trailing bytes after the snapshot"
  return j

/-! ## Writing -/

def tyJson (t : Ty) : Json := Minidregg.Theory.ObjectiveBendTyping.typeJson t

def tyOf (j : Json) : Except String Ty :=
  return (← Minidregg.Theory.ObjectiveBendTyping.decodeTypeWith #[] Limits.dataDepth Limits.dataDepth j).1

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

/-- The suspended activities and pending deliveries `record` derives, as their identities. -/
def derived (w : World) : List (String × Json) :=
  [("clock", toJson w.clock),
   ("pending", toJson (w.pending.toList.map fun p => (p.getObjValAs? String "id").toOption.getD "")),
   ("suspended", toJson (w.suspended.toList.map fun s => (s.getObjValAs? String "hash").toOption.getD ""))]

/-- The body of a snapshot of `w`. A law that does not read back from its text is refused: the
    snapshot would judge by another law than replay. -/
def body (w : World) : Except String Json := do
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
      ("version", toJson o.version), ("state", dataJson o.state), ("stateCid", toJson (stateCid o.state)), ("read", o.read.json),
      ("chain", o.chain.json), ("compile", knownByCid w o.inputs), ("supervisor", toJson o.supervisor)] ++
      (if o.minted == 0 then [] else [("minted", toJson o.minted)]) ++
      (if o.packet.isEmpty then [] else [("packet", toJson o.packet)]) ++
      (if o.readings.isEmpty then [] else [("readings", Json.arr (o.readings.toArray.map fun (n, r) =>
        Json.mkObj [("name", toJson n), ("reading", toJson r)]))]) ++
      (if o.relations.isEmpty then [] else [("relations", Json.arr (o.relations.toArray.map fun d =>
        Json.mkObj [("field", toJson d.field), ("key", toJson d.key), ("limit", toJson d.limit)]))]) ++
      (if o.fixed.isEmpty then [] else [("fixed", toJson o.fixed)])))
  let libraries := sortedBy w.libraries.toList (·.1)
  let grants := sortedBy w.grants.toList (·.1)
  let posts := sortedBy w.posts.toList (·.1)
  return Json.mkObj ([("edition", toJson edition), ("height", toJson w.height),
    ("head", toJson w.head),
    ("library", toJson ((w.library.map (·.pin)).getD "")), ("libraryLaw", toJson w.libraryLaw),
    ("libraries", Json.arr (libraries.toArray.map fun (pin, l) =>
      Json.mkObj [("pin", toJson pin), ("modules", modulesJson l.modules)])),
    ("settings", Json.mkObj ([("settled", toJson w.settled), ("clock", toJson w.clockPrincipal),
      ("postQuota", toJson w.postQuota), ("interpretQuota", toJson w.interpretQuota)] ++
      (if w.opener.isEmpty then [] else [("opener", toJson w.opener)]))),
    ("types", Json.arr (types.toArray.map (·.2))), ("objects", Json.arr out),
    ("grants", Json.arr (grants.toArray.map fun (_, g) => (g.json).setObjVal! "revoked" (toJson g.revoked))),
    ("posts", Json.arr (posts.toArray.map fun (uri, p) => p.json uri))] ++
    derived w)

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
    let (n, p) ← readArg b (pos + 1) ((b.get! pos).toNat % 32)
    if p + n > b.size then throw "truncated snapshot"
    let some s := String.fromUTF8? (b.extract p (p + n)) | throw "snapshot text is not UTF-8"
    return (s, p + n)
  unless b.size > 0 && b.get! 0 == 0xa2 do throw "the snapshot is not {cid, body}"
  let (k1, p) ← text 1
  let (cid, p) ← text p
  let (k2, p) ← text p
  unless k1 == "cid" && k2 == "body" do throw "the snapshot is not {cid, body}"
  unless p < b.size && (b.get! p).toNat / 32 == 2 do throw "the snapshot body is not bytes"
  let (n, p) ← readArg b (p + 1) ((b.get! p).toNat % 32)
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

/-! ## Reading -/

/-- The checked body of a snapshot file's bytes, refused by name. -/
def verifiedBody (bytes : ByteArray) (height : Nat) (entries : Array Json) : Except String Json := do
  if bytes.size > Limits.maxSnapshotBytes then throw "exceeds its byte capacity"
  let (cid, raw) ← split bytes
  unless cid == Delvetalk.Canonical.cid raw do throw "its bytes are not its CID's"
  let b ← decodeBytes raw
  unless (← b.getObjValAs? String "edition") == edition do throw "another snapshot edition"
  unless (← natField b "height") == height do throw "its height is not its file name's"
  if height == 0 || height > entries.size then throw "the journal is shorter than its height"
  unless (entries[height - 1]!.getObjValAs? String "hash").toOption == some (← b.getObjValAs? String "head") do
    throw "its head is not the journal's hash at its height"
  return b

/-- The store a snapshot body holds (objects, types, libraries, grants, posts, settings). -/
def install (b : Json) (modules : Std.HashMap String String) : Except String World := do
  let mut w : World := { modules }
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
                opener := (settings.getObjValAs? String "opener").toOption.getD "" }
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
    unless cid == stateCid state do throw s!"the state of {id} is not its CID's"
    let law ← parseLawText lawText
    let version ← natField o "version"
    let read ← parseRead (some (← o.getObjVal? "read"))
    let chain ← parseChain (some (← o.getObjVal? "chain"))
    let obj : Object :=
      { pin := pin
        law := law
        lawText := lawText
        version := version
        state := state
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
        minted := (o.getObjValAs? Nat "minted").toOption.getD 0
        packet := (o.getObjValAs? String "packet").toOption.getD ""
        readings := artifactReadings (Json.mkObj [("laws", (o.getObjVal? "readings").toOption.getD (Json.arr #[]))])
        relations := (((o.getObjVal? "relations").toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap fun d =>
          match d.getObjValAs? String "field", d.getObjValAs? (List String) "key", d.getObjValAs? Nat "limit" with
          | .ok field, .ok key, .ok limit => some { field, key, limit }
          | _, _, _ => none
        fixed := (o.getObjValAs? (List String) "fixed").toOption.getD [] }
    objects := objects.insert id obj
  let mut grants : Std.HashMap String Grant := {}
  for g in ← (← b.getObjVal? "grants").getArr? do
    let grant ← Grant.ofJson g
    grants := grants.insert grant.id { grant with revoked := ← g.getObjValAs? Bool "revoked" }
  let mut posts : Std.HashMap String Post := {}
  for p in ← (← b.getObjVal? "posts").getArr? do
    let (uri, post) ← Post.ofJson p
    posts := posts.insert uri post
  return { w with objects, grants, posts }

/-- The bookkeeping `record` derives from entries, with no judging: receipts, the history index,
    outbox, publications, sources, pending deliveries, suspensions, the clock. -/
def recordAll (w : World) (entries : Array Json) : Except String World := do
  let mut w := w
  for entry in entries do
    let identity ← entry.getObjVal? "identity"
    let key := identityKey (← identity.getObjValAs? String "principal") (← identity.getObjValAs? String "intent")
    -- `touched` is the objects an entry wrote, created or held a grant of, as `commit` indexed it.
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let ids := fun (k : String) => (((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap
      fun x => (x.getObjValAs? String "object").toOption
    let touch := match tagOf entry with
      | "admitted" =>
        let written := ids "writes"
        let holders := (((outcome.getObjVal? "grants").toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap
          fun g => (g.getObjValAs? String "holder").toOption
        written ++ ids "creates" ++ (holders.filter (!written.contains ·)).eraseDups
      | "created" | "posted" => ((outcome.getObjValAs? String "object").toOption.map ([·])).getD []
      | _ => []
    w := record w entry key touch
  return w

/-! ## Forks

`world-fork` writes a new journal whose genesis entry (`forked`) holds the shared world's store at a
height as a snapshot body, with the pending deliveries and suspended activities of the objects it
carries, and chains to the forked world's entry at that height. The fork's opener and clock
principal are the forking principal. -/

/-- The genesis entry of a fork of `w` (the world at `height`, whose entry there is `cid`) for
    `principal`, and the ids it omitted: only objects the principal may view are carried, with their
    grants, pending deliveries and suspended activities (checkpoints and offers written out whole). -/
def forkGenesis (w : World) (principal world : String) (height : Nat) (cid : String) :
    Except String (Json × List String) := do
  let carried := w.objects.filter fun _ o => o.read.permits principal
  let omitted := (w.objects.toList.filter fun (id, _) => !carried.contains id).map (·.1) |>.toArray.qsort (· < ·) |>.toList
  let keeps := fun (id : String) => carried.contains id
  let lawText ← libraryLawText principal
  let grants := w.grants.filter fun _ g => keeps g.object
  let shown : World := { w with objects := carried, modules := {}, posts := {}, grants, opener := principal,
                                clockPrincipal := principal, settled := true, libraryLaw := lawText }
  let state ← body shown
  let pending := w.pending.filter fun p => keeps ((p.getObjValAs? String "to").toOption.getD "")
  let suspended ← (w.suspended.filter fun e => keeps (((e.getObjVal? "outcome").toOption.bind (·.getObjVal? "activity" |>.toOption)
      |>.bind (·.getObjValAs? String "object" |>.toOption)).getD "")).mapM fun e => do
    let outcome ← e.getObjVal? "outcome"
    let activity ← outcome.getObjVal? "activity"
    let activity := activity.setObjVal! "checkpoint" (← expandSuspended w e)
    -- A fork carries no blocks for these: the argument is restored whole.
    let activity := ((Json.mkObj ((((activity.getObj?.toOption.map (·.toList)).getD []).filter (·.1 != "argumentBlock")) ++
      [("argument", ← activityArgument w activity)])))
    let outcome := outcome.setObjVal! "activity" activity
    let outcome := match expandInterpretation w outcome with
      | some i => outcome.setObjVal! "interpretation" i
      | none => outcome
    return e.setObjVal! "outcome" outcome
  let origin := Json.mkObj [("world", toJson world), ("height", toJson height), ("cid", toJson cid)]
  let handles := w.handles.toList.toArray.qsort (fun a b => a.1 < b.1) |>.map fun (did, h) =>
    Json.mkObj [("did", toJson did), ("handle", toJson h)]
  let outcome := Json.mkObj [("tag", toJson "forked"), ("forkedFrom", origin), ("state", state),
    ("pending", Json.arr pending), ("suspended", Json.arr suspended), ("handles", Json.arr handles),
    ("omitted", toJson omitted)]
  let entry := Journal.sealEntry 1 cid [("identity", identityJson principal "fork"), ("roots", rootsJson []),
    ("turn", toJson 0), ("request", toJson (Journal.bodyHash origin)), ("outcome", outcome)]
  return (entry, omitted)

/-- The world a fork's genesis entry starts: its store installed, its carried pending deliveries
    and suspended activities, handles and origin, and the entry recorded. -/
def installFork (entry : Json) : Except String World := do
  let outcome ← entry.getObjVal? "outcome"
  let state ← outcome.getObjVal? "state"
  let w ← install state {}
  let arr := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
  let handles := (arr "handles").foldl (fun m h => match h.getObjValAs? String "did", h.getObjValAs? String "handle" with
    | .ok d, .ok x => m.insert d x
    | _, _ => m) ({} : Std.HashMap String String)
  let clock ← natField state "clock"
  let forkedFrom := (outcome.getObjVal? "forkedFrom").toOption
  let cachedPackets := w.objects.fold (fun m _ o => if o.packet.isEmpty then m else m.insert o.inputsKey o.packet) {}
  let w := { w with clock, pending := arr "pending", suspended := arr "suspended", handles, forkedFrom, cachedPackets }
  let identity ← entry.getObjVal? "identity"
  return record w entry (identityKey (← identity.getObjValAs? String "principal") (← identity.getObjValAs? String "intent")) []

/-- Where replay of a journal starts: a fork's installed genesis and one entry consumed, else an empty world. -/
def startOf (entries : Array Json) (caches : Caches := {}) : Except String (World × Nat) := do
  match entries[0]? with
  | some e => if tagOf e == "forked" then return ((← installFork e).withCaches caches, 1) else return (({} : World).withCaches caches, 0)
  | none => return (({} : World).withCaches caches, 0)

/-- What the entries say each object is, without judging: created (with its pin), then each
    admitted write's recorded version and each reprogram's new pin. -/
def expectedObjects (entries : Array Json) : Std.HashMap String (Nat × String) := Id.run do
  let mut out : Std.HashMap String (Nat × String) := {}
  for entry in entries do
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let arr := fun (k : String) => ((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
    let text := fun (j : Json) (k : String) => (j.getObjValAs? String k).toOption.getD ""
    match tagOf entry with
    | "forked" =>
      for o in ((outcome.getObjVal? "state").toOption.bind (·.getObjVal? "objects" |>.toOption) |>.bind (·.getArr?.toOption)).getD #[] do
        out := out.insert (text o "id") ((o.getObjValAs? Nat "version").toOption.getD 0, text o "pin")
    | "created" => out := out.insert (text outcome "object") (0, text outcome "pin")
    | "admitted" =>
      for c in arr "creates" do out := out.insert (text c "object") (0, text c "pin")
      for x in arr "writes" do
        let id := text x "object"
        let pin := ((out[id]?).map (·.2)).getD ""
        out := out.insert id ((x.getObjValAs? Nat "version").toOption.getD 0, pin)
      for r in arr "reprograms" do
        let id := text r "object"
        out := out.insert id (((out[id]?).map (·.1)).getD 0, text r "newPin")
    | _ => pure ()
  return out

/-- The state CIDs the journal itself commits to, by object and version: a created state (its
    seed is the whole state) and a write's `cid` (host7). -/
def anchoredStates (entries : Array Json) : Std.HashMap (String × Nat) String := Id.run do
  let mut out : Std.HashMap (String × Nat) String := {}
  for entry in entries do
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let arr := fun (j : Json) (k : String) => ((j.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
    let text := fun (j : Json) (k : String) => (j.getObjValAs? String k).toOption.getD ""
    match tagOf entry with
    | "forked" =>
      for o in ((outcome.getObjVal? "state").toOption.bind (·.getObjVal? "objects" |>.toOption) |>.bind (·.getArr?.toOption)).getD #[] do
        if let (.ok v, .ok c) := (o.getObjValAs? Nat "version", o.getObjValAs? String "stateCid") then
          out := out.insert (text o "id", v) c
    | "created" =>
      if let .ok seed := outcome.getObjVal? "seed" then out := out.insert (text outcome "object", 0) (Journal.bodyHash seed)
    | "admitted" =>
      for c in arr outcome "creates" do
        if let .ok seed := c.getObjVal? "seed" then out := out.insert (text c "object", 0) (Journal.bodyHash seed)
      for x in arr outcome "writes" do
        if let (.ok v, .ok c) := (x.getObjValAs? Nat "version", x.getObjValAs? String "cid") then
          out := out.insert (text x "object", v) c
    | _ => pure ()
  return out

/-- A world from a snapshot body and the journal's entries: the store installed, the entries up
    to its height recorded, the derived copies compared, the later entries replayed. -/
def resume (b : Json) (entries : Array Json) (caches : Caches := {}) : Except String World := do
  let height ← natField b "height"
  let early := entries.extract 0 height
  let (start, skip) ← startOf entries caches
  let booked ← recordAll start (early.extract skip early.size)
  let w ← install b booked.modules
  let w := { booked with library := w.library, libraries := w.libraries, libraryLaw := w.libraryLaw,
                         objects := w.objects, grants := w.grants, posts := w.posts,
                         cachedPackets := w.objects.fold (fun m _ o =>
                           if o.packet.isEmpty then m else m.insert o.inputsKey o.packet) {},
                         clockPrincipal := w.clockPrincipal, postQuota := w.postQuota, opener := w.opener,
                         interpretQuota := w.interpretQuota,
                         settled := w.settled }
  for (k, v) in derived w do
    unless (b.getObjVal? k).toOption == some v do throw s!"its {k} is not the journal's"
  let expected := expectedObjects early
  unless expected.size == w.objects.size do throw "its objects are not the journal's"
  for (id, o) in w.objects.toList do
    unless expected[id]? == some (o.version, o.pin) do throw s!"object {id} is not at the journal's version and pin"
  -- Each state against the CID the journal commits to at its version, where it names one.
  let anchored := anchoredStates entries
  for (id, o) in w.objects.toList do
    if let some cid := anchored[(id, o.version)]? then
      unless cid == stateCid o.state do throw s!"the state of {id} is not the one the journal commits to at version {o.version}"
  let mut w := w
  for entry in entries.extract height entries.size do
    match replayEntry w entry with
    | .ok w' => w := w'
    | .error e => throw s!"the entry at height {w.height + 1} does not replay on it: {e}"
  return w

/-! ## Opening -/

/-- The journal's lines, parsed and hash-walked from genesis (cheap: no judging, no compiling). -/
def entriesOf (content : String) : Except String (Array Json) := do
  let lines := content.splitOn "\n"
  let (complete, tail) := (lines.dropLast, lines.getLast?.getD "")
  if complete.length ≥ Limits.maxJournalEntries then throw "journal exceeds entry capacity"
  let mut out : Array Json := #[]
  let mut head := Limits.genesis
  for line in complete do
    let height := out.size + 1
    let entry ← match Json.parse line with
      | .ok e => pure e
      | .error _ => throw s!"journal broken at height {height}: unparsable line"
    -- A fork's genesis chains to the forked world's entry at its height, which it names.
    if height == 1 && tagOf entry == "forked" then
      let previous := (entry.getObjValAs? String "previous").toOption.getD ""
      unless ((entry.getObjVal? "outcome").toOption.bind (·.getObjVal? "forkedFrom" |>.toOption)
          |>.bind (·.getObjValAs? String "cid" |>.toOption)) == some previous do
        throw "journal broken at height 1: a fork's genesis must chain to the cid it was forked from"
      head := previous
    Journal.verify height head entry
    head := (entry.getObjValAs? String "hash").toOption.getD ""
    out := out.push entry
  unless tail.isEmpty do throw s!"journal broken at height {out.size + 1}: unterminated final line"
  return out

/-- Full replay of verified entries. -/
def replayAll (entries : Array Json) (caches : Caches := {}) : Except String World := do
  let (start, skip) ← startOf entries caches
  let mut w := start
  for entry in entries.extract skip entries.size do
    match replayEntry w entry with
    | .ok w' => w := w'
    | .error e => throw s!"journal broken at height {w.height + 1}: {e}"
  return w

/-- What an open did with the snapshots: the height it resumed from (0: full replay) and each
    snapshot it refused, by name. -/
structure Report where
  resumed : Nat := 0
  refused : List (Nat × String) := []

def Report.json (r : Report) : Json :=
  Json.mkObj [("resumed", toJson r.resumed), ("refused", Json.arr (r.refused.toArray.map fun (h, why) =>
    Json.mkObj [("height", toJson h), ("reason", toJson why)]))]

/-- Open a journal's content: the newest snapshot that passes every check, else full replay.
    With `verify`, replay everything and compare every snapshot with the replayed store at its
    height; a snapshot that disagrees is refused by name. -/
def openContent (journal content : String) (verify : Bool := false) (caches : Caches := {}) :
    IO (Except String (World × Report)) := do
  let entries ← match entriesOf content with
    | .ok e => pure e
    | .error e => return .error e
  let snaps ← files journal
  let mut report : Report := {}
  if verify then
    let heights := snaps.map (·.1)
    let (start, skip) ← match startOf entries caches with
      | .ok r => pure r
      | .error e => return .error s!"journal broken at height 1: {e}"
    let mut w := start
    for entry in entries.extract skip entries.size do
      match replayEntry w entry with
      | .ok w' => w := w'
      | .error e => return .error s!"journal broken at height {w.height + 1}: {e}"
      if heights.contains w.height then
        let some (_, f) := snaps.find? (·.1 == w.height) | continue
        let bytes ← IO.FS.readBinFile f
        match verifiedBody bytes w.height entries, body w with
        | .ok mine, .ok replayed =>
          if mine != replayed then
            report := { report with refused := report.refused ++ [(w.height, "it disagrees with replay at its height")] }
        | .error e, _ | _, .error e =>
          report := { report with refused := report.refused ++ [(w.height, e)] }
    return .ok (w, report)
  for (height, f) in snaps do
    let attempt ← try
        let bytes ← IO.FS.readBinFile f
        pure (verifiedBody bytes height entries >>= fun b => resume b entries caches)
      catch e => pure (.error s!"unreadable: {e}")
    match attempt with
    | .ok w => return .ok (w, { report with resumed := height })
    | .error e => report := { report with refused := report.refused ++ [(height, e)] }
  match replayAll entries caches with
  | .ok w => return .ok (w, report)
  | .error e => return .error e

end Delvetalk.Host.Snapshot
