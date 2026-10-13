/- `delvetalk-obend carry` (docs/FOUNDATION.md §2; docs/OVERHAUL.md §5 step 1): a world carried to this
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
   carried world's current library when its pin differs (`carriedFrom.library {from, to}`). The image's
   packages are that library's modules and `DIR/../objects` (as `deploy/seed.py` names them), so an object
   moves with the host: its own modules named as the image names one take the image's source, any module
   the new source imports comes with it, layers above stay, and it compiles against the new library. One
   whose closure is unchanged keeps its pin. One that moves keeps its state when the state conforms to the
   new type; else the package's `migrate(old: State8) -> State` (a reprogram's migration, `Ops.runMigration`)
   converts it, the old state read through `migrate`'s argument type. The genesis lists each move (`moved
   [{object, from, to, migration, before, after}]`, pins and state CIDs) and the moved object's version moves
   once. Its suspensions (taken in the code before) cannot resume: when its package offers `carried` they are
   dropped, their supervisors told, and the genesis holds a delivery of `carried {}` to it (`rearmed`), as a kind
   sends what it makes `made`: the first settling of the carried world runs it, and a self-ticking tide schedules
   its next `due` there. A moved or left object's suspension is otherwise never dropped silently: it refuses the
   carry by name until the owner names the object with `--leave` (or the activity ends first). A moved object holding its package's law as it was (unamended) takes the package's new law when it
   changed (`law {before, after}` on its move); one whose law an owner amended keeps it, named (`kept`). An
   object whose
   move refuses (its package does not compile against the image, or its state does not conform and it has
   no `migrate`, or `migrate` refuses) is carried retired at its old pin, the refusal its reading; so is one
   whose own package the image no longer ships (Wake, Env), and one the owner names with `--leave`. Only an
   object that does not rebuild under its own pin refuses the carry, by name.

   A thing's body is a layer, and the image's bodies are genesis's (`--body OBJ=FILE`, which
   transport/carry.py derives from `deploy/genesis.py`'s KINDS): a kind takes FILE as its `body`, and each
   thing whose `kind` names it takes FILE as its first layer, as the commonplace takes its own; each such
   change is a move (`body: true`). Without `--library` the
   world's library and every pin are carried as they were.

   A world of an edition that names states otherwise (before 10, by their wire JSON; from 10, by their cells:
   `Naming.ofEdition`) is read by its own naming, every object checked against its anchors, and the genesis
   lists each state's two names (`renamed [{object, before, after}]`), so a check finds each object at the state
   the snapshot held.

   The old journal is only read: J must verify as a chain, not be open, and OUT must not exist. The new
   journal is replayed from its genesis, and every object's state CID compared with the snapshot's (a moved
   object's with its migrated state's), before it is written. -/
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
  Snapshot.carriedKeys ++ ["pending", "suspended", "handles", "modules", "blocks", "anchors", "receipts", "touched"]

/-- The world a snapshot body at `height` of `src` holds, as this binary reads it: the indexes in
    `readKeys`, laid over an empty world's, then the store, every object checked against its anchors by
    the naming of the journal's replay edition (`Naming.ofEdition`). -/
def readWorld (b : Json) (src : Entries) (height : Nat) (replay : Nat) : Except String World := do
  let base : World := { entries := src.upTo height, height, head := ← b.getObjValAs? String "head" }
  let index ← b.getObjVal? "index"
  let read ← readKeys.foldlM (init := Snapshot.indexJson base) fun j k => do
    match index.getObjVal? k with
    | .ok v => return j.setObjVal! k v
    | .error _ => if Snapshot.addedKeys.contains k then return j else throw s!"its index has no {k}"
  let w ← Snapshot.installIndex base read
  let naming := Naming.ofEdition replay
  let w ← Snapshot.install b w naming
  let w := { w with carriedIds := (src.genesis?.map carriedIdentities).getD {} }
  Snapshot.checkAnchors w naming ((b.getObjValAs? String "edition").toOption == some Snapshot.edition)
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
  unless Delvetalk.Canonical.encode canonical == Delvetalk.Canonical.encode o.state do
    throw "its rows are not canonical under this host's relations"
  let (methods, predicate, predicateReads) := b.shape
  let packet ← b.artifact.getObjValAs? String "packetSha256"
  let o : Object := { o with
    stateType := b.ty, bounds := b.assumptions.bounds, methods, predicate, predicateReads, relations, packet,
    fixed := fixedOf b.artifact, declares := declaresOf b.artifact }
  return (o.withState canonical, b)

/-- Whether a suspended entry's checkpoint decodes under the packet this binary compiles for its method (one
    the host resumes itself holds none). -/
def resumable (w : World) (e : Json) : Except String World := do
  if hostResumed e then return w
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

/-- The packages the image ships: the library sealed from `--library DIR`, the modules of
    `DIR/../objects` by name, and the bodies `--body OBJ=FILE` names (genesis's, from transport/carry.py):
    a kind's, set as its `body` and laid over every thing of that kind, or a thing's own. -/
structure Shipped where
  library : Library
  objects : List (String × String)
  bodies : List (String × String) := []

/-- An object's move: its pin before and after, the migration that converted its state ("" when the state
    conformed), and the state's CID before and after. -/
structure Moved where
  object : String
  before : String
  after : String
  migration : String
  stateBefore : String
  stateAfter : String
  /-- The image's body it took: as its layer (a thing of a kind, the commonplace) or as its `body` (a kind). -/
  body : Bool := false
  /-- Its law text before and after, when it held its package's law and the image's package declares another. -/
  law : Option (String × String) := none
  /-- The package's own rule and want lines placed on it at the move (by name), and those it took off. -/
  placed : List String := []
  unplaced : List String := []

def Moved.json (m : Moved) : Json :=
  Json.mkObj ([("object", toJson m.object), ("from", toJson m.before), ("to", toJson m.after),
    ("migration", toJson m.migration), ("before", toJson m.stateBefore), ("after", toJson m.stateAfter)] ++
    (if m.body then [("body", toJson true)] else []) ++
    ((m.law.map fun (b, a) => [("law", Json.mkObj [("before", toJson b), ("after", toJson a)])]).getD []) ++
    (if m.placed.isEmpty then [] else [("placed", toJson m.placed)]) ++
    (if m.unplaced.isEmpty then [] else [("unplaced", toJson m.unplaced)]))

/-- What a carry made of a world: the world as this binary holds it, the objects left (retired, with the
    whole refusal; its retired clause reads the first line within 200 bytes), the objects moved to the image's packages, the suspensions dropped (the entry and why), and what
    refused the carry (by name). -/
structure Carried where
  world : World
  left : List (String × String) := []
  moved : List Moved := []
  dropped : List (Json × String) := []
  refused : List (String × String) := []
  /-- Moved objects whose package's law changed but whose own law is not the package's as it was (an owner's
      amendment): their law is kept, each named with it. -/
  kept : List (String × String) := []
  /-- Each object's state as the old edition named it and as this one does, when the editions name
      states otherwise (`Naming.ofEdition`): the same state, renamed. -/
  renamed : List (String × String × String) := []

/-- The method a package declares to be told it was carried (`carried(state, input: {}, context)`), as a kind
    tells what it makes `made`: what the carry's move dropped (a self-ticking tide's waiting `due`) it starts
    again from there. -/
def rearmMethod : String := "carried"

/-- The moved objects whose package offers `carried`, each told once, after the move; and every object a re-arm of an
    earlier carry still waits for (pending, never run), told again under this carry's intent: what the old one sends
    would take ids the world before bound (`Ops.deliveryId` of the same intent), and never run (`Ops.answered`). The
    live tide's re-arm `carried:tide`, run at last by the v13 carry, sent a `due` v9 had bound. -/
def Carried.rearmed (c : Carried) : List String :=
  let moved := c.moved.filterMap fun m => (c.world.objects[m.object]?).bind fun o => if o.offers rearmMethod then some m.object else none
  let waiting := c.world.pending.toList.filterMap fun p =>
    if rearmIntent ((p.getObjValAs? String "id").toOption.getD "") then (p.getObjValAs? String "to").toOption else none
  (moved ++ waiting).eraseDups

/-- The delivery telling `id` it was carried: a pending send from no object (the carry, the opener's act), so it
    runs as the first turn that settles the carried world, under the carry's principal and a fresh ledger. Its id,
    the turn's intent, is this carry's own (`carried:<id>:<the carried genesis's height>`, `Ops.rearmIntent`). -/
def rearm (principal : String) (at_ : Nat) (id : String) : Json :=
  Json.mkObj [("id", toJson s!"carried:{id}:{at_}"), ("to", toJson id), ("method", toJson rearmMethod),
    ("argument", Delvetalk.Compiler.ObjectiveBendDataWire.dataJson (.record [])), ("sender", toJson ""), ("from", identityJson principal "carry"),
    ("principal", toJson principal), ("ledger", Ledger.start.json)]

/-- The modules a source depends on: those it imports, and the one a layer is laid over. -/
def dependsOn (source : String) : List String :=
  importsOf source ++ ((source.splitOn "\n").head?.bind fun l =>
    (l.trimAscii.toString.dropPrefix? "layer over ./").bind fun r => (r.toString.splitOn ".obend").head?).toList

/-- `inputs` as the image ships them: the library its new pin, each own module the image names its source, the
    first layer `body` when one is given, and before each the image's modules it newly needs (neither the
    library's nor already its own). Inputs naming no library are as they were. -/
def movedInputs (s : Shipped) (inputs : Json) (body : Option String := none) : Except String Json := do
  unless (inputs.getObjValAs? String "library").toOption.isSome do return inputs
  let .ok m := inputs.getObjVal? "modules" | return inputs.setObjVal! "library" (toJson s.library.pin)
  let image := fun (n : String) => (s.library.modules.lookup n).orElse fun _ => s.objects.lookup n
  let modules ← parseModules m
  -- A body laid again is laid as extend lays one: over the module below it (`Ops.layerLine`).
  let laid := fun (below src : String) =>
    if (src.splitOn "\n").head?.map (·.trimAscii.toString) == some (layerLine below) then src else layerLine below ++ "\n" ++ src
  let own := (modules.zip (("" :: modules.map (·.1)).take modules.length)).map fun ((n, src), below) =>
    (n, if n == "Layer1" then ((body.map (laid below)).getD src) else (image n).getD src)
  let mut out : Array (String × String) := #[]
  for (n, src) in own do
    -- What the image's source newly imports, depth first, each once.
    let mut todo := (dependsOn src).reverse
    let mut needed : Array (String × String) := #[]
    for _ in [0:(s.objects.length + 1) * 64] do
      let some d := todo.head? | break
      todo := todo.tail
      if (s.library.modules.lookup d).isSome || own.any (·.1 == d) || out.any (·.1 == d) || needed.any (·.1 == d) then continue
      let some dsrc := s.objects.lookup d | continue
      needed := #[(d, dsrc)] ++ needed
      todo := (dependsOn dsrc).reverse ++ todo
    out := out ++ needed |>.push (n, src)
  return (inputs.setObjVal! "modules" (modulesJson out.toList)).setObjVal! "library" (toJson s.library.pin)

/-- The package `o` was made from (its entry module, below any layers), when it was its library's and the
    image ships it no longer, in its library or among its packages (Wake, Env): the object has nothing to move to. -/
def gone (w : World) (s : Shipped) (o : Object) : Option String := do
  let pin ← (o.inputs.getObjValAs? String "library").toOption
  let lib ← w.libraries[pin]?
  let own ← (o.inputs.getObjVal? "modules").toOption.bind (parseModules · |>.toOption)
  let (name, _) ← own[own.length - layersOf o.inputs - 1]?
  if (lib.modules.lookup name).isSome && (s.library.modules.lookup name).isNone && (s.objects.lookup name).isNone then
    some name else none

/-- The law a moved object holds under the image: its package's new law when it held its package's law as it
    was (as made, unamended) and the package's law changed, with its readings; else its own, and
    `amended` when the package's law changed and the object's is not the package's as it was. Only a
    package-declared law is the carry's: a law given at creation is the maker's, and genesis's (`deploy.genesis
    refresh`) lays the image's. -/
def lawUnder (w : World) (id : String) (o : Object) (old new : Built) :
    Except String (Law × String × List (String × String) × Bool) := do
  let was := renderLaw old.laws
  if old.laws.isEmpty || new.laws.isEmpty || renderLaw new.laws == was then return (o.law, o.lawText, o.readings, false)
  if renderLaw o.law != was then return (o.law, o.lawText, o.readings, true)
  if let some message := citationRefusal w id new.laws then throw s!"its package's law: {message}"
  let readings := (artifactReadings new.artifact).filter fun (n, _) => (new.laws.lookup n).isSome
  return (new.laws, renderLaw new.laws, readings, false)

/-- The rules and wants of a moved object holding its package's law (as `makeObject` places a package's lines on
    what is made of it with no law text given): each placed row its old package placed (the same line, by name)
    that the new package changes or drops taken off, and each line of the new package whose name its text and
    rows leave free placed, owned by its owner (else the opener), `since` the carried genesis. Its own and hands'
    rows stay. -/
def placedUnder (w : World) (o : Object) (old new : Built) (state : Delvetalk.Theory.ObjectiveBendDemandData.Data) :
    List Placed × List Placed × List String × List String := Id.run do
  if old.laws.isEmpty || renderLaw o.law != renderLaw old.laws then return (o.rules, o.wants, [], [])
  let packaged := fun (r : Placed) => old.lines.any fun c => c.name == r.name && c.render == r.line
  let kept := fun (r : Placed) => !packaged r || new.lines.any fun c => c.name == r.name && c.render == r.line
  let rules := o.rules.filter kept
  let wants := o.wants.filter kept
  let gone := ((o.rules ++ o.wants).filter (!kept ·)).map (·.name)
  let taken := ((parseClauses o.lawText).toOption.getD []).map (·.name) ++ (rules ++ wants).map (·.name)
  let owner := if (ownerOf state).isEmpty then w.opener else ownerOf state
  let fresh := (new.lines.filter fun c => !taken.contains c.name).map fun c =>
    ({ name := c.name, owner, since := 1, line := c.render, clause := c } : Placed)
  return (rules ++ fresh.filter (Law.isRule ·.clause), wants ++ fresh.filter (Law.isWant ·.clause), fresh.map (·.name), gone)

/-- `o` (built as `old` under its own pin) moved to the image's packages, or none when its closure there is
    its pin's; else why it cannot move. -/
def moved (w : World) (s : Shipped) (id : String) (o : Object) (old : Built) :
    Except String (Option (Object × Built × Moved × Bool)) := do
  -- Its body: a kind (holding a `body`) takes its own as that field; a thing of a kind takes its kind's, and
  -- the commonplace its own, laid as its first layer.
  let kind := match Law.rawField "kind" o.state with
    | some (.label k) => some k
    | _ => none
  let held := (s.bodies.lookup id).filter fun _ => (Law.rawField "body" o.state).isSome
  let layer := if layersOf o.inputs == 0 || held.isSome then none
    else (s.bodies.lookup id).orElse fun _ => kind.bind fun k => s.bodies.lookup k
  let inputs ← movedInputs s o.inputs layer
  let b ← compileObject w inputs |>.mapError (s!"its package does not compile against the library this host ships: " ++ ·)
  let pin ← b.artifact.getObjValAs? String "sourcesSha256"
  let relaid := held.any fun src => match Law.rawField "body" o.state with
    | some (.label b) => b != src
    | _ => true
  if pin == o.pin && !relaid then return none
  let (state, migration) ← if o.state.conformsUnder b.assumptions.bounds b.ty then pure (o.state, "") else do
    let m ← compileMigration w inputs "migrate" b.ty (fun dom bounds => o.state.conformsUnder bounds dom)
        "its migrate does not read the state as it was"
      |>.mapError fun (_, e) => s!"its state does not conform to its package's new state type, and {e}"
    let next ← runMigration m o.state |>.mapError (s!"its migrate: " ++ ·)
    unless next.conformsUnder b.assumptions.bounds b.ty do
      throw "its migrate's result does not conform to the new state type"
    pure (next, "migrate")
  let state := match held, state with
    | some src, .record fs => .record (fs.map fun (k, v) => if k == "body" then (k, .label src) else (k, v))
    | _, st => st
  let (relations, state) ← relationsFor b state |>.mapError (s!"its state under the new relations: " ++ ·)
  let cells := Delvetalk.Turn.StateCells.of (cellDecls relations) state
  if let some cell := (Delvetalk.Turn.Changes.all cells).overBound cells then
    throw (((cellRefusal id cell).reason).getD "a cell passes maxCellBytes")
  let fixed := fixedOf b.artifact
  if let some f := movedFixed (o.fixed ++ fixed.filter (!o.fixed.contains ·)) o.cells cells then
    throw s!"its migrate moves {f}, which is fixed"
  if let some f := o.fixed.find? (!fixed.contains ·) then
    throw s!"{f} is fixed, and its package no longer fixes it"
  let (methods, predicate, predicateReads) := b.shape
  let (law, lawText, readings, amended) ← lawUnder w id o old b
  let (rules, wants, placed, unplaced) := placedUnder w o old b state
  let o' := { o with inputs, inputsKey := inputsKeyOf inputs, pin, cells, version := o.version + 1, stateType := b.ty,
                     bounds := b.assumptions.bounds, methods, predicate, predicateReads, relations, fixed,
                     packet := ← b.artifact.getObjValAs? String "packetSha256", declares := declaresOf b.artifact,
                     law, lawText, readings, rules, wants }
  return some (o', b, { object := id, before := o.pin, after := pin, migration,
                        stateBefore := o.stateCid, stateAfter := cells.cid,
                        body := layer.isSome || relaid,
                        law := if lawText == o.lawText then none else some (o.lawText, lawText), placed, unplaced }, amended)

/-- Every object rebuilt and, with the image's packages, moved to them; every suspension checked. An
    object named in `leave` is carried retired whether or not it fails, at its own pin, and its suspensions
    are dropped; a moved object's are dropped when its package offers `carried`. Any other suspension the carry
    cannot keep refuses it by name. -/
def carryWorld (w : World) (leave : List String) (reason : String) (shipped : Option Shipped := none) :
    Except String Carried := do
  for id in leave do
    unless w.objects.contains id do throw s!"--leave {id}: the world holds no {id}"
  let w := match shipped with
    | some s => { w with libraries := w.libraries.insert s.library.pin s.library }
    | none => w
  let mut c : Carried := { world := w }
  let opener := if w.opener.isEmpty then w.clockPrincipal else w.opener
  let retire := fun (o : Object) (why : String) => { o with lawText := (retiredLaw o.lawText why opener).getD o.lawText }
  -- Left: what the owner names, each object whose package the image no longer ships, and each whose move to
  -- the image's packages refuses (its compile or its migration), at its own pin, the refusal its reading.
  let named : List (String × String) := (w.objects.toList.filterMap fun (id, o) =>
      if leave.contains id then some (id, s!"left at the carry: {reason}") else do
        let name ← gone w (← shipped) o
        some (id, s!"left at the carry: its package {name} is no longer shipped"))
  for (id, o) in Snapshot.sortedBy w.objects.toList (·.1) do
    match rebuilt c.world o with
    | .error e =>
      if let some _ := named.lookup id then
        let why := s!"carried retired: {e}"
        c := { c with world := { c.world with objects := c.world.objects.insert id (retire o (reading why)) }, left := c.left ++ [(id, why)] }
      else c := { c with refused := c.refused ++ [(id, e)] }
    | .ok (o', b) =>
      let step : Except String (Option (Object × Built × Moved × Bool)) := match named.lookup id, shipped with
        | some why, _ => .error why
        | none, none => .ok none
        | none, some s => (moved c.world s id o' b).mapError (s!"left at the carry: " ++ ·)
      match step with
      | .ok (some (o'', b', m, amended)) =>
        c := { c with world := cacheBuild { c.world with objects := c.world.objects.insert id o'' } o''.inputs b', moved := c.moved ++ [m],
                      kept := if amended then c.kept ++ [(id, o''.lawText)] else c.kept }
      | .ok none =>
        c := { c with world := cacheBuild { c.world with objects := c.world.objects.insert id o' } o'.inputs b }
      | .error why =>
        -- The whole refusal is the carry's output; the retired clause reads its first line, within a reading's bound.
        c := { c with world := cacheBuild { c.world with objects := c.world.objects.insert id (retire o' (reading why)) } o'.inputs b,
                      left := c.left ++ [(id, why)] }
  -- A suspension the carry cannot keep is dropped only by a decision: the owner's `--leave`, or a moved package's
  -- `carried`, which takes up again what it waited for. Any other refuses the carry by name (codex docs 7).
  let mut kept : Array Json := #[]
  for e in w.suspended do
    let id := Snapshot.suspendedObject e
    let what := s!"{id}'s suspension {(e.getObjValAs? String "hash").toOption.getD ""}"
    if let some (_, why) := c.left.find? (·.1 == id) then
      if leave.contains id then c := { c with dropped := c.dropped ++ [(e, "its object was left")] }
      else c := { c with refused := c.refused ++ [(what, s!"its object is carried retired ({(why.splitOn "\n").headD ""}), which ends the activity: name it with --leave {id}, or let the activity end before the carry")] }
      continue
    if let some m := c.moved.find? (·.object == id) then
      if (c.world.objects[id]?).any (·.offers rearmMethod) then
        c := { c with dropped := c.dropped ++ [(e, s!"its object moved to pin {m.after}, and is told `{rearmMethod}`")] }
      else c := { c with refused := c.refused ++ [(what, s!"its object moves to pin {m.after}, whose code cannot resume it, and its package offers no `{rearmMethod}`: name it with --leave {id}, or let the activity end before the carry")] }
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

def renamedJson (renamed : List (String × String × String)) : Json :=
  Json.arr (renamed.toArray.map fun (id, before, after) =>
    Json.mkObj [("object", toJson id), ("before", toJson before), ("after", toJson after)])

/-! ## Makings

A carried genesis keeps each object's making (`made`): who made it, under which intent, at which height of
the world it was made in. A reader of the world's history (genesis's refresh: is this kind genesis's?) reads it
there when the journals before are not on its disk. -/

/-- A `made` row: the object, and the identity and height of the entry that made it. -/
def madeRow (id : String) (e : Json) : Json :=
  Json.mkObj [("object", toJson id), ("identity", (e.getObjVal? "identity").toOption.getD Json.null),
    ("height", (e.getObjVal? "height").toOption.getD Json.null)]

/-- The makings of what the journal at `journal`, whose genesis is `genesis`, was given by it: a carried genesis's
    `made`; for one of an edition before it kept them, every making in the journal it was carried from (its
    `carriedFrom.world`, as given or beside `journal`), read when it is on this disk, and that one's in turn. -/
partial def givenMakings (journal : String) (genesis : Json) : IO (Std.HashMap String Json) := do
  if tagOf genesis != "carried" then return {}
  if ((genesis.getObjVal? "outcome").toOption.bind (·.getObjVal? "made" |>.toOption)).isSome then return madeOf genesis
  let some (_, origin) := genesisOrigin genesis | return {}
  let some world := (origin.getObjValAs? String "world").toOption | return {}
  let beside := ((journal : System.FilePath).parent.getD ".") / world
  let some path ← [(world : System.FilePath), beside].findM? (·.pathExists) | return {}
  let .ok old ← Snapshot.openEntries path.toString | return {}
  let earlier ← match old.genesis? with
    | some g => givenMakings path.toString g
    | none => pure {}
  return old.foldl (fun m _ e => (makes e).foldl (fun m id => m.insert id (madeRow id e)) m) earlier

/-- Every object's making, by id: the entry of `src` that made it, or what `src`'s genesis gave it (`given`). -/
def makings (w : World) (src : Entries) (given : Std.HashMap String Json) : Array Json :=
  let found := src.foldl (fun m _ e => (makes e).foldl (fun m id => m.insert id (madeRow id e)) m) given
  ((w.objects.toList.map (·.1)).toArray.qsort (· < ·)).filterMap (found[·]?)

/-- The `carried` genesis of `c` (the world of the journal `world` at `height`, whose head is `cid`, of
    replay edition `replay`), with `before` the old journal's own genesis and `made` its objects' makings. -/
def carryGenesis (c : Carried) (src : Entries) (world reason : String) (height : Nat) (cid : String)
    (replay : Nat) (before : Json) (library : Option Library) (made : Array Json) : Except String Json := do
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
  let principal := if !w.opener.isEmpty then w.opener else if !w.clockPrincipal.isEmpty then w.clockPrincipal else "host"
  -- A re-arm an earlier carry left pending is superseded by this carry's of the same object (`Carried.rearmed`).
  let stale := fun (p : Json) => rearmIntent ((p.getObjValAs? String "id").toOption.getD "")
  let pending := w.pending.filter (!stale ·) ++ (c.dropped.filterMap fun (e, _) => droppedEnd w e).toArray ++
    (c.rearmed.map (rearm principal (height + 1))).toArray
  let all := Snapshot.indexJson w
  let index := Json.mkObj (Snapshot.carriedKeys.filterMap fun k => (all.getObjVal? k).toOption.map (k, ·))
  -- Every identity the world binds (a suspension's is carried with it; a transient refusal binds none), and
  -- those its own carry kept: a retry after the carry answers the receipt it had (`Ops.boundEntry`).
  let bound := w.receipts.toArray.filterMap (fun (_, i) => (src.get? i).bind fun e =>
      if tagOf e == "suspended" || isTransient e || rearmIntent (identityIntent e) then none else some (identityRow e))
  let identities := (bound ++ (w.carriedIds.toArray.filter fun (_, row) => !rearmIntent (identityIntent row)).map (·.2)).qsort (fun a b => a.compress < b.compress)
  Snapshot.genesisEntry w w "carried" principal "carry" cid ("carriedFrom", origin) pending suspended
    ([("index", index)] ++ (if identities.isEmpty then [] else [("identities", Json.arr identities)]) ++
     (if c.left.isEmpty then [] else [("left", Json.arr (c.left.toArray.map fun (id, why) =>
        Json.mkObj [("object", toJson id), ("reading", toJson why)]))]) ++
     (if c.moved.isEmpty then [] else [("moved", Json.arr (c.moved.toArray.map (·.json)))]) ++
     (if c.dropped.isEmpty then [] else [("dropped", Json.arr (c.dropped.toArray.map fun (e, why) =>
        Json.mkObj [("hash", (e.getObjVal? "hash").toOption.getD Json.null), ("object", toJson (Snapshot.suspendedObject e)),
          ("reason", toJson why)]))]) ++
     (if c.kept.isEmpty then [] else [("kept", Json.arr (c.kept.toArray.map fun (id, law) =>
        Json.mkObj [("object", toJson id), ("law", toJson law)]))]) ++
     (if c.rearmed.isEmpty then [] else [("rearmed", toJson c.rearmed)]) ++
     (if c.renamed.isEmpty then [] else [("renamed", renamedJson c.renamed)]) ++
     (if made.isEmpty then [] else [("made", Json.arr made)])) (height := height + 1)

def fail (message : String) (code : UInt32 := 1) : IO UInt32 := do
  (← IO.getStderr).putStrLn s!"carry: {message}"
  return code

def usage : String :=
  "usage: delvetalk-obend carry --from J --out J2 --reason R [--library DIR [--body OBJ=FILE]...] [--leave OBJ]...\n" ++
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
  if height == src.base then return ← fail s!"{journal} holds no world"
  let first ← match Snapshot.checkedEntry src src.base with
    | .ok e => pure e
    | .error e => return ← fail s!"{journal} does not verify: {e}"
  let replay := (first.getObjValAs? Nat "replay").toOption.getD 1
  let head := (src.hashAt? (height - 1)).getD ""
  let snapshots ← Snapshot.files journal
  let some (_, file) := snapshots.find? (·.1 == height)
    | return ← fail (s!"{journal} has no snapshot at its head ({height}); " ++
        (match snapshots.head? with | some (h, _) => s!"the newest is at {h}; " | none => "") ++
        s!"write one with the binary of its edition ({replay}): deploy/verify.sh --snapshot")
  let body ← match Snapshot.verifiedBody (← IO.FS.readBinFile file) height src [Snapshot.edition, Snapshot.previousEdition] with
    | .ok b => pure b
    | .error e => return ← fail s!"{file}: {e}"
  let w ← match readWorld body src height replay with
    | .ok w => pure w
    | .error e => return ← fail s!"{file} does not read here: {e}"
  -- The library this host ships, sealed as serve seals it, beside the new journal; and its packages.
  let shipped ← match RootEdit.textArg args "--library" with
    | none => pure none
    | some dir =>
      let target := ((out : System.FilePath).parent.getD ".") / "library"
      try Delvetalk.Serve.sealLibrary dir target catch e => return ← fail s!"--library {dir}: {e}"
      let library ← match ← loadLibrary target.toString with
        | .ok l => pure l
        | .error e => return ← fail s!"--library {dir}: {e}"
      let objects := ((dir : System.FilePath).parent.getD ".") / "objects"
      let mut packages : List (String × String) := []
      if ← objects.isDir then
        for f in ← objects.readDir do
          if f.fileName.endsWith ".obend" then
            packages := packages ++ [((f.fileName.dropEnd 6).toString, ← IO.FS.readFile f.path)]
      let mut bodies : List (String × String) := []
      for spec in allArgs args "--body" do
        let some (obj, file) := (match spec.splitOn "=" with | [o, f] => some (o, f) | _ => none)
          | return ← fail s!"--body {spec}: a body is OBJ=FILE" 64
        bodies := bodies ++ [(obj, ← IO.FS.readFile file)]
      pure (some ({ library, objects := packages, bodies } : Shipped))
  let carried ← match carryWorld w leave reason shipped with
    | .ok c => pure c
    | .error e => return ← fail e 64
  let naming := Naming.ofEdition replay
  let renamed := w.objects.toList.filterMap fun (id, o) =>
    let before := naming.state o
    if before == o.stateCid then none else some (id, before, o.stateCid)
  let carried := { carried with renamed := (renamed.toArray.qsort (fun a b => a.1 < b.1)).toList }
  unless carried.refused.isEmpty do
    return ← fail ("refused, each by name (list an object as --leave OBJ to carry it retired):\n" ++
      "\n".intercalate (carried.refused.map fun (what, why) => s!"  {what}: {why}"))
  let made := makings w src (← givenMakings journal first)
  let entry ← match carryGenesis carried src journal reason height head replay first (shipped.map (·.library)) made with
    | .ok e => pure e
    | .error e => return ← fail e
  -- The new journal replays from its genesis, and holds every object at the state the snapshot held.
  let replayed ← match Snapshot.replayAll (Entries.ofArray #[entry]) with
    | .ok r => pure r
    | .error e => return ← fail s!"the carried genesis does not replay: {e}"
  for (id, o) in w.objects.toList do
    let some o' := replayed.objects[id]? | return ← fail s!"{id} was not carried"
    let expected := ((carried.moved.find? (·.object == id)).map (·.stateAfter)).getD o.stateCid
    unless o'.stateCid == expected do return ← fail s!"the state of {id} moved in the carry"
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
    ("moved", Json.arr (carried.moved.toArray.map (·.json))),
    ("dropped", Json.arr (carried.dropped.toArray.map fun (e, why) => Json.mkObj [("hash", (e.getObjVal? "hash").toOption.getD Json.null),
      ("object", toJson (Snapshot.suspendedObject e)), ("reason", toJson why)])),
    ("kept", Json.arr (carried.kept.toArray.map fun (id, law) => Json.mkObj [("object", toJson id), ("law", toJson law)])),
    ("rearmed", toJson carried.rearmed), ("renamed", renamedJson carried.renamed)])
  return 0

end Delvetalk.Host.Carry
