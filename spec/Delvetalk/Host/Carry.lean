/- `delvetalk-obend carry` (docs/TENURE.md §1(b); docs/OVERHAUL.md §5 step 1): a world carried to this
   binary. The journal of another replay edition does not reopen here, so its world is read from the
   snapshot the binary that wrote it took at its head, never from its entries, and becomes the genesis of a
   new journal: `carried`, chained to the old head, holding the whole store, every grant, pending delivery,
   suspension, post, handle and setting, the indexes the world stands on (`Snapshot.carriedKeys`), and the
   old chain's entries by hash, so a receipt of the world before resolves by its slug as "entry N of the
   world before the carry". Height 2 continues from there.

   Every object is rebuilt by this binary from its sources (pins are source CIDs, so none moves): its
   sources must seal to its pin, its state conform to the type this host compiles and its rows be canonical
   under this host's relations; then its state type, bounds, method table, law shape and packet are this
   host's. Every suspended checkpoint must decode under the packet this host compiles for its method. A
   failure refuses the carry by name; the owner lists the object with `--leave OBJ`, and it is carried
   retired (ROOT 2.2's `retired` clause, its reason the clause's reading), its state kept as it was, its
   suspensions dropped with their supervisors told `ended {how: broken}`.

   A carry is where the host changes, and the library ships with the host: `--library DIR` (serve's
   `--library`, the image's `world/lib`) is sealed as serve seals it, into OUT's directory, and becomes the
   carried world's current library when its pin differs (`carriedFrom.library {from, to}`); every object keeps
   the pin it was compiled under, its library among the world's, and what is made afterwards compiles against
   the new one. Without it the world's library is carried as it was.

   The old journal is only read: J must verify as a chain, not be open, and OUT must not exist. The new
   journal is replayed from its genesis, and every object's state CID compared with the snapshot's, before
   it is written. -/
import Delvetalk.Host.Snapshot
import Delvetalk.Host.RootEdit
import Delvetalk.Serve

namespace Delvetalk.Host.Carry
open Lean (Json toJson)

/-- Every value of a repeated flag. -/
def allArgs (args : List String) (flag : String) : List String :=
  match args with
  | f :: v :: rest => if f == flag then v :: allArgs rest flag else allArgs (v :: rest) flag
  | _ => []

/-- The index keys a carry reads from a snapshot body: what it keeps (`carriedKeys`), the pending
    deliveries, suspensions and handles, and what reads the old chain for it (sources and checkpoint
    blocks by the entry carrying each; the anchors its objects are checked against). Any other key of an
    older binary's body is not read, so a snapshot edition is a contract on these alone. -/
def readKeys : List String :=
  Snapshot.carriedKeys ++ ["pending", "suspended", "handles", "modules", "blocks", "anchors"]

/-- The world a snapshot body at `height` of `src` holds, as this binary reads it: the indexes in
    `readKeys`, laid over an empty world's, then the store, every object checked against its anchors. -/
def readWorld (b : Json) (src : Entries) (height : Nat) : Except String World := do
  let base : World := { entries := src.upTo height, height, head := ← b.getObjValAs? String "head" }
  let index ← b.getObjVal? "index"
  let read ← readKeys.foldlM (init := Snapshot.indexJson base) fun j k => do
    return j.setObjVal! k (← (index.getObjVal? k).mapError fun _ => s!"its index has no {k}")
  let w ← Snapshot.installIndex base read
  let w ← Snapshot.install b w
  Snapshot.checkAnchors w
  return w

/-- A reason as a law clause's reading: one line, no quotes or backslashes, at most 200 bytes. -/
def reading (s : String) : String :=
  let line := ((s.splitOn "\n").headD "").map fun c => if c == '"' || c == '\\' then '\'' else c
  if line.utf8ByteSize ≤ 200 then line else (line.take 197).toString ++ "..."

/-- `o` as this binary builds it, or why it cannot be. -/
def rebuilt (w : World) (o : Object) : Except String (Object × Built) := do
  let b ← compileObject w o.inputs
  let pin ← b.artifact.getObjValAs? String "sourcesSha256"
  unless pin == o.pin do throw s!"its sources seal to {pin}, not to its pin {o.pin}"
  unless o.state.conformsUnder b.assumptions.bounds b.ty do
    throw "its state does not conform to its type as this host compiles it"
  let (relations, canonical) ← relationsFor b o.state
  unless stateCid canonical == stateCid o.state do throw "its rows are not canonical under this host's relations"
  let (methods, predicate, predicateReads) := b.shape
  return ({ o with stateType := b.ty, bounds := b.assumptions.bounds, methods, predicate, predicateReads, relations,
                   packet := ← b.artifact.getObjValAs? String "packetSha256", fixed := fixedOf b.artifact,
                   declares := declaresOf b.artifact }, b)

/-- Whether a suspended entry's checkpoint decodes under the packet this binary compiles for its method. -/
def resumable (w : World) (e : Json) : Except String World := do
  let id := Snapshot.suspendedObject e
  let some o := w.objects[id]? | throw s!"it suspends {id}, which the store does not hold"
  let method ← ((← e.getObjVal? "outcome").getObjVal? "activity") >>= (·.getObjValAs? String "method")
  let (c, w) ← compileDef w o method
  let entry ← match c.entry with
    | some e => pure e
    | none => Delvetalk.CheckedEntry.ofPacket c.packet
  let checkpoint ← Delvetalk.Turn.Checkpoint.fromJson (← expandSuspended w e)
  unless checkpoint.packetSha256 == entry.pin do
    throw s!"its checkpoint was taken under packet {checkpoint.packetSha256}; this host compiles {id}'s {method} as {entry.pin}"
  let dictionary := c.dictionary.getD (Delvetalk.Theory.ObjectiveBendCheckpoint.Dictionary.ofProgram entry.source.term)
  let (_, tokens) := Delvetalk.Turn.splitSite checkpoint.tokens
  if (Delvetalk.Theory.ObjectiveBendCheckpoint.decodeCheckpoint dictionary tokens).isNone then
    throw "its checkpoint does not decode under this host's kernel"
  return w

/-- What a carry made of a world: the world as this binary holds it, the objects left (retired, with the
    reading), the suspensions dropped (the entry and why), and what refused the carry (by name). -/
structure Carried where
  world : World
  left : List (String × String) := []
  dropped : List (Json × String) := []
  refused : List (String × String) := []

/-- Every object rebuilt and every suspension checked; an object named in `leave` is carried retired
    whether or not it fails, and its suspensions are dropped. -/
def carryWorld (w : World) (leave : List String) (reason : String) : Except String Carried := do
  for id in leave do
    unless w.objects.contains id do throw s!"--leave {id}: the world holds no {id}"
  let mut c : Carried := { world := w }
  let opener := if w.opener.isEmpty then w.clockPrincipal else w.opener
  for (id, o) in Snapshot.sortedBy w.objects.toList (·.1) do
    match rebuilt c.world o with
    | .ok (o', b) =>
      let o' := if leave.contains id then { o' with lawText := (retiredLaw o.lawText (reading s!"left at the carry: {reason}") opener).getD o.lawText } else o'
      c := { c with world := cacheBuild { c.world with objects := c.world.objects.insert id o' } o.inputs b }
      if leave.contains id then c := { c with left := c.left ++ [(id, s!"left at the carry: {reason}")] }
    | .error e =>
      if leave.contains id then
        let why := reading s!"carried retired: {e}"
        let o' := { o with lawText := (retiredLaw o.lawText why opener).getD o.lawText }
        c := { c with world := { c.world with objects := c.world.objects.insert id o' }, left := c.left ++ [(id, why)] }
      else c := { c with refused := c.refused ++ [(id, e)] }
  let mut kept : Array Json := #[]
  for e in w.suspended do
    let id := Snapshot.suspendedObject e
    if leave.contains id then
      c := { c with dropped := c.dropped ++ [(e, "its object was left")] }
      continue
    match resumable c.world e with
    | .ok w' => c := { c with world := w' }; kept := kept.push e
    | .error why => c := { c with refused := c.refused ++ [(s!"{id}'s suspension {(e.getObjValAs? String "hash").toOption.getD ""}", why)] }
  -- A retired object's law changed: re-parse it, as `install` would read it.
  let objects ← c.world.objects.toList.foldlM (init := c.world.objects) fun m (id, o) => do
    if c.left.any (·.1 == id) then return m.insert id { o with law := ← parseLawText o.lawText } else return m
  return { c with world := { c.world with objects, suspended := kept } }

/-- A dropped suspension's end, told to its object's supervisor as the turn ending it would tell it
    (`endedField`, as `Ops.recordCore` makes it a pending delivery): `how: broken`, refused `carried`. -/
def droppedEnd (w : World) (e : Json) : Option Json := do
  let identity ← (e.getObjVal? "identity").toOption
  let principal ← (identity.getObjValAs? String "principal").toOption
  let intent ← (identity.getObjValAs? String "intent").toOption
  let id := Snapshot.suspendedObject e
  let ledger := ((e.getObjVal? "ledger").toOption.bind fun l => (ledgerOf l).toOption).getD Ledger.start
  let outcome := Json.mkObj [("tag", toJson "refused"), ("class", toJson "carried"), ("object", toJson id)]
  let [("ended", d)] := endedField w id principal intent "broken" ledger 0 1 outcome | none
  return Json.mkObj ([("from", identity), ("principal", toJson principal)] ++ ((d.getObj?.toOption.map (·.toList)).getD []))

/-- The `carried` genesis of `c` (the world of the journal `world` at `height`, whose head is `cid`, of
    replay edition `replay`), with `before` the old journal's own genesis. -/
def carryGenesis (c : Carried) (src : Entries) (world reason : String) (height : Nat) (cid : String)
    (replay : Nat) (before : Json) (library : Option Library) : Except String Json := do
  let previous := (c.world.library.map (·.pin)).getD ""
  let changed := library.filter (·.pin != previous)
  let w := match changed with
    | some l => { c.world with library := some l, libraries := c.world.libraries.insert l.pin l }
    | none => c.world
  let entries := Json.mkObj ((List.range height).filterMap fun i => (src.hashAt? i).map (·, toJson (i + 1)))
  let earlier := match genesisOrigin before with
    | some ("carriedFrom", o) => [("carriedFrom", o)]
    | _ => []
  let origin := Json.mkObj ([("world", toJson world), ("height", toJson height), ("cid", toJson cid),
    ("replay", toJson replay), ("reason", toJson reason), ("entries", entries)] ++
    (changed.map fun l => [("library", Json.mkObj [("from", toJson previous), ("to", toJson l.pin)])]).getD [] ++ earlier)
  let suspended ← w.suspended.mapM (Snapshot.wholeSuspension w)
  let pending := w.pending ++ (c.dropped.filterMap fun (e, _) => droppedEnd w e).toArray
  let all := Snapshot.indexJson w
  let index := Json.mkObj (Snapshot.carriedKeys.filterMap fun k => (all.getObjVal? k).toOption.map (k, ·))
  let principal := if !w.opener.isEmpty then w.opener else if !w.clockPrincipal.isEmpty then w.clockPrincipal else "host"
  Snapshot.genesisEntry w w "carried" principal "carry" cid ("carriedFrom", origin) pending suspended
    ([("index", index)] ++
     (if c.left.isEmpty then [] else [("left", Json.arr (c.left.toArray.map fun (id, why) =>
        Json.mkObj [("object", toJson id), ("reading", toJson why)]))]) ++
     (if c.dropped.isEmpty then [] else [("dropped", Json.arr (c.dropped.toArray.map fun (e, why) =>
        Json.mkObj [("hash", (e.getObjVal? "hash").toOption.getD Json.null), ("object", toJson (Snapshot.suspendedObject e)),
          ("reason", toJson why)]))]))

def fail (message : String) (code : UInt32 := 1) : IO UInt32 := do
  (← IO.getStderr).putStrLn s!"carry: {message}"
  return code

def usage : String :=
  "usage: delvetalk-obend carry --from J --out J2 --reason R [--library DIR] [--leave OBJ]...\n" ++
  "       J's snapshot at its head, written by the binary of J's edition, is read; J2 must not exist"

def main (args : List String) : IO UInt32 := do
  let some journal := RootEdit.textArg args "--from" | return ← fail usage 64
  let some out := RootEdit.textArg args "--out" | return ← fail usage 64
  let some reason := RootEdit.textArg args "--reason" | return ← fail usage 64
  if reason.isEmpty || reason.any (· == '\n') then return ← fail "a reason is one line" 64
  let leave := allArgs args "--leave"
  if (← (out : System.FilePath).pathExists) || (← (Snapshot.storeOf out : System.FilePath).pathExists) then
    return ← fail s!"{out} exists: a carry writes a new journal"
  unless ← (journal : System.FilePath).pathExists do return ← fail s!"no journal {journal}"
  let handle ← IO.FS.Handle.mk journal .read
  unless ← handle.tryLock (exclusive := true) do return ← fail s!"{journal} is open in another process: stop it first" 75
  let src ← match ← Snapshot.openEntries journal with
    | .ok s => pure s
    | .error e => return ← fail s!"{journal} does not verify: {e}"
  let height := src.count
  if height == 0 then return ← fail s!"{journal} holds no world"
  let first ← match Snapshot.checkedEntry src 0 with
    | .ok e => pure e
    | .error e => return ← fail s!"{journal} does not verify: {e}"
  let replay := (first.getObjValAs? Nat "replay").toOption.getD 1
  let head := (src.hashAt? (height - 1)).getD ""
  let snapshots ← Snapshot.files journal
  let some (_, file) := snapshots.find? (·.1 == height)
    | return ← fail (s!"{journal} has no snapshot at its head ({height}); " ++
        (match snapshots.head? with | some (h, _) => s!"the newest is at {h}; " | none => "") ++
        s!"write one with the binary of its edition ({replay}): deploy/verify.sh --snapshot")
  let body ← match Snapshot.verifiedBody (← IO.FS.readBinFile file) height src with
    | .ok b => pure b
    | .error e => return ← fail s!"{file}: {e}"
  let w ← match readWorld body src height with
    | .ok w => pure w
    | .error e => return ← fail s!"{file} does not read here: {e}"
  let carried ← match carryWorld w leave reason with
    | .ok c => pure c
    | .error e => return ← fail e 64
  -- The library this host ships, sealed as serve seals it, beside the new journal.
  let library ← match RootEdit.textArg args "--library" with
    | none => pure none
    | some dir =>
      let target := ((out : System.FilePath).parent.getD ".") / "library"
      try Delvetalk.Serve.sealLibrary dir target catch e => return ← fail s!"--library {dir}: {e}"
      match ← loadLibrary target.toString with
      | .ok l => pure (some l)
      | .error e => return ← fail s!"--library {dir}: {e}"
  unless carried.refused.isEmpty do
    return ← fail ("refused, each by name (list an object as --leave OBJ to carry it retired):\n" ++
      "\n".intercalate (carried.refused.map fun (what, why) => s!"  {what}: {why}"))
  let entry ← match carryGenesis carried src journal reason height head replay first library with
    | .ok e => pure e
    | .error e => return ← fail e
  -- The new journal replays from its genesis, and holds every object at the state the snapshot held.
  let replayed ← match Snapshot.replayAll (Entries.ofArray #[entry]) with
    | .ok r => pure r
    | .error e => return ← fail s!"the carried genesis does not replay: {e}"
  for (id, o) in w.objects.toList do
    let some o' := replayed.objects[id]? | return ← fail s!"{id} was not carried"
    unless stateCid o'.state == stateCid o.state do return ← fail s!"the state of {id} moved in the carry"
  unless replayed.objects.size == w.objects.size do return ← fail "the carried world holds another set of objects"
  if let .error e ← Snapshot.writeJournal out #[entry] then return ← fail e
  handle.unlock
  let hash := (entry.getObjValAs? String "hash").toOption.getD ""
  RootEdit.printJson (Json.mkObj [("status", toJson "carried"), ("out", toJson out), ("hash", toJson hash),
    ("slug", toJson ((Slug.ofCid hash).getD "")), ("replay", toJson Limits.replayEdition),
    ("carriedFrom", Json.mkObj [("world", toJson journal), ("height", toJson height), ("cid", toJson head),
      ("replay", toJson replay)]),
    ("library", toJson ((replayed.library.map (·.pin)).getD "")),
    ("objects", toJson replayed.objects.size), ("pending", toJson replayed.pending.size),
    ("suspended", toJson replayed.suspended.size), ("grants", toJson replayed.grants.size),
    ("posts", toJson replayed.posts.size), ("receipts", toJson height),
    ("left", Json.arr (carried.left.toArray.map fun (id, why) => Json.mkObj [("object", toJson id), ("reading", toJson why)])),
    ("dropped", Json.arr (carried.dropped.toArray.map fun (e, why) => Json.mkObj [("hash", (e.getObjVal? "hash").toOption.getD Json.null),
      ("object", toJson (Snapshot.suspendedObject e)), ("reason", toJson why)]))])
  return 0

end Delvetalk.Host.Carry
