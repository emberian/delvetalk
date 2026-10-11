/- `delvetalk-obend serve`: the one process that holds a directory of worlds (docs/FEDERATION.md §1,
   HOST-HANDOFF 5.125). It takes the directory's lock, seals the library, listens on the public socket
   and the root socket (`spec/native/serve.c`), and answers one request at a time in arrival order,
   each through the world its envelope names. -/
import Delvetalk.PackageSession

namespace Delvetalk.Serve
open Lean (Json toJson)

@[extern "delvetalk_serve_listen"]
opaque listen (host root group : @& String) : IO Unit

/-- `"<connection> <1 if the root socket> <line>"`, the next request; "" once the loop must stop. -/
@[extern "delvetalk_serve_next"]
opaque next : IO String

@[extern "delvetalk_serve_reply"]
opaque reply (connection : UInt64) (line : @& String) : IO Unit

@[extern "delvetalk_serve_close"]
opaque closeAll : IO Unit

/-- With `DELVETALK_TIMING=1`, one stderr line per op: its name, what it names (object, method,
    principal), the milliseconds from reading the request to writing the reply, and how many
    turns the settling pass after it resumed and delivered. -/
def timingLine (request : Json) (reply : Json) (ms : Nat) : String :=
  let text := fun (k : String) => (request.getObjValAs? String k).toOption.getD ""
  let count := fun (k : String) => ((reply.getObjVal? k).toOption.bind (·.getArr?.toOption)).map (·.size) |>.getD 0
  s!"timing\t{text "op"}\t{ms}\tobject={text "object"}\tmethod={text "method"}\tprincipal={text "principal"}\tresumed={count "resumed"}\tdelivered={count "delivered"}"

/-- How `serve` was started. -/
structure Config where
  state : System.FilePath
  /-- The public socket (`--socket`; default `<state>/host.sock`): it may live outside the state
      directory, so the front mounts no journal. -/
  socket : System.FilePath := ""
  rootSocket : System.FilePath
  /-- The root socket's group (`--root-group`; "" keeps serve's own): the socket is 0660, so the hand
      may run under its own uid in that group (docs/ROOT.md §1.4). -/
  rootGroup : String := ""
  opener : String := ""
  /-- The library directory to seal (with arrival's packages beside it, `../objects`). -/
  library : Option System.FilePath := none
  sync : String := "fsync"
  clock : String := "transport"
  /-- The world an envelope without `world` addresses. -/
  home : String := "town"

structure Server where
  config : Config
  /-- Every world and scratch world this process has opened, held until it stops (a world opened
      over its block store holds its live state and indexes, not its journal: HOST-HANDOFF 5.137), so a
      turn in one may read another (`Host.Foreign`). -/
  worlds : Std.HashMap String PackageSession.Session := {}
  /-- Each scratch world (`scratch/<principal>/<name>`) and the home world's clock at its last op. -/
  scratches : Std.HashMap String Nat := {}
  /-- Scratch worlds discarded, and the home clock they expired at, for the refusal that says so. -/
  expired : Std.HashMap String Nat := {}
  /-- The journal-less session: compile, check and run against the sealed library. -/
  stateless : PackageSession.Session := {}
  sealed : Option String := none
  libraryPin : Option String := none
  sha : String := ""
  /-- The directory's lock, held for the life of the process (dropping the handle would release it). -/
  lock : Option IO.FS.Handle := none

/-- The packages `world-arrive` creates from; the sealed library holds them beside the library. -/
def arrival : List String := ["Avatar"]

/-- The ops only the root socket takes (docs/ROOT.md §1.4). The opener's ordinary turns are the public
    socket's too; there its privileges are not (`resident`, `Host.openerActs`). -/
def rootOps : List String := ["world-root", "world-library", "world-settings", "world-fork", "world-snapshot", "library-load",
  "world-dump"]

def errorJson (message : String) : Json :=
  Json.mkObj [("status", toJson "error"), ("message", toJson message)]

def hex (bytes : ByteArray) : String :=
  let digits := "0123456789abcdef".toList.toArray
  String.join (bytes.toList.map fun b => String.ofList [digits[(b.toNat / 16)]!, digits[(b.toNat % 16)]!])

/-- The binary's SHA-256, hashed once and cached in `cache` by path, size and mtime. -/
def binaryPin (cache binary : System.FilePath) : IO String := do
  let info ← binary.metadata
  let key := [("path", toJson binary.toString), ("size", toJson info.byteSize.toNat),
    ("mtimeNs", toJson (info.modified.sec.toNat * 1000000000 + info.modified.nsec.toNat))]
  if ← cache.pathExists then
    if let .ok held := Json.parse (← IO.FS.readFile cache) then
      if key.all (fun (k, v) => (held.getObjVal? k).toOption == some v) then
        if let .ok sha := held.getObjValAs? String "sha256" then return sha
  let sha := hex (Delvetalk.Canonical.digestBytes (← IO.FS.readBinFile binary))
  let tmp := cache.withExtension "tmp"
  IO.FS.writeFile tmp (Json.mkObj (key ++ [("sha256", toJson sha)])).compress
  IO.FS.rename tmp cache
  return sha

/-- `DIR/library`, rebuilt at each start: the library's files, and arrival's packages beside them. -/
def sealLibrary (library target : System.FilePath) : IO Unit := do
  if ← target.pathExists then IO.FS.removeDirAll target
  IO.FS.createDirAll target
  for f in ← library.walkDir do
    if ← f.isDir then continue
    let rel := (f.toString.drop (library.toString.length + 1)).toString
    let to := target / rel
    if let some parent := to.parent then IO.FS.createDirAll parent
    IO.FS.writeBinFile to (← IO.FS.readBinFile f)
  let objects := (library.parent.getD ".") / "objects"
  for name in arrival do
    IO.FS.writeBinFile (target / s!"{name}.obend") (← IO.FS.readBinFile (objects / s!"{name}.obend"))

/-- A principal as a directory name under `scratch/`: 1..128 bytes, no `/`, not `.` or `..`. -/
def scratchOwner (principal : String) : Bool :=
  !principal.isEmpty && principal.utf8ByteSize ≤ Host.Limits.maxPrincipalBytes && !principal.contains '/' &&
    principal != "." && principal != ".." && principal.all fun (c : Char) => c.toNat ≥ 32

/-- The key of `principal`'s scratch world `name` (`scratch/<principal>/<name>`). -/
def scratchKey (principal name : String) : Except String String :=
  if !Host.validWorldName name then .error s!"a scratch name is {"[a-z][a-z0-9-]{0,31}"}: {name} is not one"
  else if !scratchOwner principal then .error "a scratch world is a principal's: name the principal"
  else .ok s!"scratch/{principal}/{name}"

/-- The journal of world `key`: `DIR/<name>.journal`, or `DIR/scratch/<principal>/<name>.journal`. -/
def journalOf (srv : Server) (key : String) : System.FilePath := srv.config.state / s!"{key}.journal"

/-- How world `key` is opened. A world: its clock, opener and library as configured, its name journaled.
    A scratch: its own settings, journaled when it was made (`scratchOp`), under the scratch bounds. -/
def openRequest (srv : Server) (key : String) : Json :=
  let c := srv.config
  let base := [("op", toJson "world-open"), ("path", toJson (journalOf srv key).toString), ("sync", toJson c.sync)]
  if key.startsWith "scratch/" then
    Json.mkObj (base ++ [("maxJournalBytes", toJson Host.Limits.scratchJournalBytes), ("maxObjects", toJson Host.Limits.scratchObjects)])
  else
    Json.mkObj (base ++ [("clock", toJson c.clock), ("name", toJson key)] ++
      (if c.opener.isEmpty then [] else [("opener", toJson c.opener)]) ++
      (match srv.sealed with
        | some path => if c.opener.isEmpty then [] else [("library", toJson path), ("principal", toJson c.opener)]
        | none => []))

/-- The open session of world `key`, opened by replay when it is not held. A scratch that is not there is
    refused, naming when it expired. -/
def world (srv : Server) (key : String) : IO (Server × Except String PackageSession.Session) := do
  match srv.worlds[key]? with
  | some session => return (srv, .ok session)
  | none =>
    if key.startsWith "scratch/" && !(← (journalOf srv key).pathExists) then
      let name := (key.splitOn "/").getLastD ""
      return (srv, .error (match srv.expired[key]? with
        | some at_ => s!"scratch/{name} expired at clock {at_}; open it again with world-scratch"
        | none => s!"no scratch/{name}; open one with world-scratch"))
    let (session, r) ← PackageSession.stepIO {} (openRequest srv key)
    match r with
    | .ok j =>
      if (j.getObjValAs? String "status").toOption == some "opened" then
        return ({ srv with worlds := srv.worlds.insert key session }, .ok session)
      return (srv, .error s!"world {key} did not open: {j.compress}")
    | .error e => return (srv, .error s!"world {key} did not open: {e}")

/-- The home world's clock, which scratch worlds expire by (none when it does not open). -/
def homeClock (srv : Server) : IO (Server × Nat) := do
  let (srv, home) ← world srv srv.config.home
  return (srv, match home with
    | .ok session => (session.world.map fun (o : Host.Open) => o.world.clock).getD 0
    | .error _ => 0)

/-- Discard scratch world `key` at home clock `clock`: its session, its journal, block store and
    snapshots. The one deletion in the system: a scratch is not custody (docs/FEDERATION.md §3). -/
def discard (srv : Server) (key : String) (clock : Nat) : IO Server := do
  let path := (journalOf srv key).toString
  for f in [path, Host.Snapshot.storeOf path] ++ (← Host.Snapshot.files path).map (·.2) do
    try IO.FS.removeFile f catch _ => pure ()
  return { srv with worlds := srv.worlds.erase key, scratches := srv.scratches.erase key, expired := srv.expired.insert key clock }

/-- Discard every scratch world whose last op was `Limits.scratchMinutes` or more before `clock`. -/
def expire (srv : Server) (clock : Nat) : IO Server := do
  let mut srv := srv
  for (key, last) in srv.scratches.toList do
    if last + Host.Limits.scratchMinutes ≤ clock then srv ← discard srv key clock
  return srv

/-- The scratch worlds on disk at start, each as if its last op were now. -/
def findScratches (srv : Server) (clock : Nat) : IO Server := do
  let dir := srv.config.state / "scratch"
  unless ← dir.pathExists do return srv
  let mut srv := srv
  for owner in ← dir.readDir do
    unless ← owner.path.isDir do continue
    for f in ← owner.path.readDir do
      if f.fileName.endsWith ".journal" then
        srv := { srv with scratches := srv.scratches.insert s!"scratch/{owner.fileName}/{(f.fileName.dropEnd 8).toString}" clock }
  return srv

/-- A scratch world's row: who, its name, the home clock of its last op and when it expires. -/
def scratchRow (key : String) (last : Nat) : Json :=
  let parts := key.splitOn "/"
  Json.mkObj [("principal", toJson (parts.getD 1 "")), ("world", toJson s!"scratch/{parts.getD 2 ""}"),
    ("lastTurn", toJson last), ("expires", toJson (last + Host.Limits.scratchMinutes))]

/-- `world-scratch {principal, name, from?: {world, height?}}`: a world of the principal's own (docs/FEDERATION.md
    §3): empty with the sealed library, its opener, clock and librarian the principal; or `from` a world it may
    read, forked at `height` (default its head) with what the principal may view (`world-fork`). At most
    `Limits.scratchPerPrincipal` at once; it expires `Limits.scratchMinutes` home clock minutes after its last op. -/
def scratchOp (srv : Server) (request : Json) : IO (Server × Json) := do
  let principal := (request.getObjValAs? String "principal").toOption.getD ""
  let name := (request.getObjValAs? String "name").toOption.getD ""
  let key ← match scratchKey principal name with
    | .ok k => pure k
    | .error e => return (srv, errorJson e)
  let path := journalOf srv key
  if ← path.pathExists then return (srv, errorJson s!"scratch/{name} exists; its turns name world scratch/{name}")
  let mine := srv.scratches.toList.filter (·.1.startsWith s!"scratch/{principal}/")
  if mine.length ≥ Host.Limits.scratchPerPrincipal then
    let oldest := (mine.toArray.qsort (·.2 < ·.2))[0]!
    return (srv, Json.mkObj [("status", toJson "refused"), ("class", toJson "capacity"),
      ("reason", toJson s!"a principal holds at most {Host.Limits.scratchPerPrincipal} scratch worlds; the oldest is {(scratchRow oldest.1 oldest.2).getObjValAs? String "world" |>.toOption.getD ""}"),
      ("oldest", scratchRow oldest.1 oldest.2)])
  if let some parent := path.parent then IO.FS.createDirAll parent
  let (srv, clock) ← homeClock srv
  let mut srv := srv
  match request.getObjVal? "from" with
  | .ok from_ =>
    let source := (from_.getObjValAs? String "world").toOption.getD srv.config.home
    let sourceKey ← match (source.dropPrefix? "scratch/").map (·.toString) with
      | some n => match scratchKey principal n with
        | .ok k => pure k
        | .error e => return (srv, errorJson e)
      | none => if Host.validWorldName source then pure source else return (srv, errorJson s!"no world {source} here")
    let (next, opened) ← world srv sourceKey
    srv := next
    let .ok session := opened | return (srv, errorJson (match opened with | .error e => e | .ok _ => ""))
    let fork := Json.mkObj ([("op", toJson "world-fork"), ("principal", toJson principal), ("into", toJson path.toString)] ++
      ((from_.getObjVal? "height").toOption.map fun h => [("height", h)]).getD [])
    let (session, r) ← PackageSession.stepIO session fork
    srv := { srv with worlds := srv.worlds.insert sourceKey session }
    match r with
    | .ok j => unless (j.getObjValAs? String "status").toOption == some "forked" do return (srv, j)
    | .error e => return (srv, errorJson e)
  | .error _ =>
    let opening := Json.mkObj ([("op", toJson "world-open"), ("path", toJson path.toString), ("sync", toJson srv.config.sync),
      ("clock", toJson principal), ("opener", toJson principal), ("principal", toJson principal),
      ("maxJournalBytes", toJson Host.Limits.scratchJournalBytes), ("maxObjects", toJson Host.Limits.scratchObjects)] ++
      ((srv.sealed.map fun p => [("library", toJson p)]).getD []))
    let (session, r) ← PackageSession.stepIO {} opening
    match r with
    | .ok j =>
      unless (j.getObjValAs? String "status").toOption == some "opened" do return (srv, j)
      srv := { srv with worlds := srv.worlds.insert key session }
    | .error e => return (srv, errorJson e)
  let (next, opened) ← world srv key
  let height := match opened with
    | .ok session => (session.world.map fun (o : Host.Open) => o.world.height).getD 0
    | .error _ => 0
  srv := { next with scratches := srv.scratches.insert key clock, expired := srv.expired.erase key }
  return (srv, Json.mkObj [("status", toJson "scratch"), ("world", toJson s!"scratch/{name}"), ("height", toJson height),
    ("expires", toJson (clock + Host.Limits.scratchMinutes))])

/-- `world-cite {principal, scratch, receipt, identity?}`: the scratch entry `receipt` (its hash) kept in the
    home world as a `cited` entry under the principal (`Host.citeOp`), read here from the scratch itself. -/
def citeOp (srv : Server) (request : Json) : IO (Server × Json) := do
  let principal := (request.getObjValAs? String "principal").toOption.getD ""
  let name := (request.getObjValAs? String "scratch").toOption.getD ""
  let key ← match scratchKey principal name with
    | .ok k => pure k
    | .error e => return (srv, errorJson e)
  let (srv, opened) ← world srv key
  let .ok scratch := opened | return (srv, errorJson (match opened with | .error e => e | .ok _ => ""))
  let receipt := (request.getObjValAs? String "receipt").toOption.getD ""
  let some w := scratch.world.map fun (o : Host.Open) => o.world | return (srv, errorJson s!"scratch/{name} is not open")
  let some entry := (w.entries.indexOf? receipt).bind w.entries.get?
    | return (srv, errorJson s!"no entry {receipt} in scratch/{name}")
  let (srv, home) ← world srv srv.config.home
  let .ok session := home | return (srv, errorJson (match home with | .error e => e | .ok _ => ""))
  let cite := Json.mkObj ([("op", toJson "world-cite"), ("principal", toJson principal), ("world", toJson s!"scratch/{name}"),
    ("entry", entry), ("resident", Json.bool true)] ++ ((request.getObjVal? "identity").toOption.map fun i => [("identity", i)]).getD [])
  let (session, r) ← PackageSession.stepIO session cite
  return ({ srv with worlds := srv.worlds.insert srv.config.home session }, match r with
    | .ok j => j
    | .error e => errorJson e)

/-- `serve-status`: this process (its binary's SHA-256, pid, replay edition and the sealed library's pin), every
    world it holds (height, objects, clock, the replay edition its first entry names and the snapshot it reopened
    from) and every scratch world. The one status of the process; a world's own is `world-status`. -/
def serveStatus (srv : Server) : IO Json := do
  let rows := srv.worlds.toList.filter (!·.1.startsWith "scratch/") |>.filterMap fun (k, h) => h.world.map fun (o : Host.Open) =>
    let w := o.world
    Json.mkObj [("name", toJson k), ("height", toJson w.height), ("objects", toJson w.objects.size), ("clock", toJson w.clock),
      ("replay", toJson (((w.entries.get? 0).bind (·.getObjValAs? Nat "replay" |>.toOption)).getD Host.Limits.replayEdition)),
      ("snapshot", o.report.json)]
  let byName := fun (a b : Json) => decide ((a.getObjValAs? String "name").toOption.getD "" < (b.getObjValAs? String "name").toOption.getD "")
  return Json.mkObj ([("status", toJson "serve"), ("hostSha256", toJson srv.sha), ("pid", toJson (← IO.Process.getPID).toNat),
    ("replay", toJson Host.Limits.replayEdition)] ++ ((srv.libraryPin.map fun p => [("library", toJson p)]).getD []) ++
    [("worlds", Json.arr (rows.toArray.qsort byName)),
     ("scratches", Json.arr ((srv.scratches.toList.toArray.qsort (·.1 < ·.1)).map fun (k, t) => scratchRow k t))])

/-- The world a reference names, read by `reader`: a world of the directory, or `scratch/<name>` the
    reader's own scratch world. -/
def referenceKey (world reader : String) : Option String :=
  match (world.dropPrefix? "scratch/").map (·.toString) with
  | some n => (scratchKey reader n).toOption
  | none => if Host.validWorldName world then some world else none

/-- Another held world's answer to `world-view` or `world-card` of `object` as `reader`, and its citation. -/
def readForeign (srv : Server) (world op object reader : String) : Option (Json × Json) := do
  let key ← referenceKey world reader
  let session ← srv.worlds[key]?
  let o ← session.world
  let w := o.world
  let request := Json.mkObj [("principal", toJson reader), ("object", toJson object)]
  let reply ← (match op with
    | "view" => Host.view w request
    | "card" => (Host.cardOp w request).map fun (p : Host.World × Json) => p.2
    | _ => .error "no such read").toOption
  let target := w.objects[object]?
  let cite := Json.mkObj ([("world", toJson world), ("object", toJson object), ("height", toJson w.height), ("head", toJson w.head)] ++
    ((target.map fun t => [("version", toJson t.version), ("stateCid", toJson (Host.stateCid t.state))]).getD []))
  return (reply, cite)

/-- What a request on world `self` may read of the others (`Host.Foreign`). -/
def foreignFor (srv : Server) (self : String) : Host.Foreign :=
  { read := fun world op object reader =>
      if referenceKey world reader == some self then none else readForeign srv world op object reader }

/-- `<world>:<object>`: an object id naming another world's object, when the text before the first `:`
    is a world served here (a world name never is `did`, `zulip` or `at`, so no local id is mistaken). -/
def splitReference (srv : Server) (id reader : String) : Option (String × String) := do
  let world := (id.splitOn ":").headD ""
  let key ← referenceKey world reader
  unless srv.worlds.contains key do none
  return (world, (id.drop (world.length + 1)).toString)

/-- The world an envelope names: `world: <name>` a world of the directory, `world: scratch/<name>` the
    principal's scratch world, none the home world. -/
def keyOf (srv : Server) (request : Json) : Except String String :=
  match request.getObjVal? "world" with
  | .ok (.str name) => match (name.dropPrefix? "scratch/").map (·.toString) with
    | some n => scratchKey ((request.getObjValAs? String "principal").toOption.getD "") n
    | none => if Host.validWorldName name then .ok name else .error s!"no world {name} here"
  | .ok _ => .error "world must be a name"
  | .error _ => .ok srv.config.home

/-- One request, as the socket it came on may ask it. -/
def answer (srv : Server) (request : Json) (root : Bool) : IO (Server × Json) := do
  let some fields := request.getObj?.toOption | return (srv, errorJson "request is not a JSON object")
  let op := (request.getObjValAs? String "op").toOption.getD ""
  if op == "serve-status" then return (srv, ← serveStatus srv)
  if op == "world-open" then return (srv, errorJson "serve opens its worlds; name one with `world`")
  if !root && rootOps.contains op then
    return (srv, errorJson "the opener speaks on the root socket")
  if op == "world-scratch" then return ← scratchOp srv request
  -- `world-root {act: {kind: expire, principal, scratch}}`: a scratch is serve's, not a journal's, so its
  -- expiry is the hand's log only (docs/ROOT.md §2.2).
  if op == "world-root" && ((request.getObjVal? "act").toOption.bind (·.getObjValAs? String "kind" |>.toOption)) == some "expire" then
    let act := (request.getObjVal? "act").toOption.getD Json.null
    match scratchKey ((act.getObjValAs? String "principal").toOption.getD "") ((act.getObjValAs? String "scratch").toOption.getD "") with
    | .error e => return (srv, errorJson e)
    | .ok key =>
      unless srv.scratches.contains key do return (srv, errorJson s!"no {key}")
      let (srv, clock) ← homeClock srv
      let srv ← discard srv key clock
      return (srv, Json.mkObj [("status", toJson "expired"), ("scratch", scratchRow key clock)])
  if op == "world-cite" then return ← citeOp srv request
  -- Every public request is a resident's, whoever it names: the opener's privileges are the root socket's.
  let bare := Json.mkObj (fields.toList.filter fun (k, _) => k != "world" && k != "stateless" && k != "resident")
  if (request.getObjVal? "stateless").toOption == some (Json.bool true) then
    let (stateless, r) ← PackageSession.stepIO srv.stateless bare
    return ({ srv with stateless }, r.toOption.getD (errorJson (match r with | .error e => e | .ok _ => "")))
  match keyOf srv request with
  | .error e => return (srv, errorJson e)
  | .ok key =>
    -- `world-view` and `world-card` of `<world>:<object>` are that world's, answered as of its height.
    if op == "world-view" || op == "world-card" then
      let reader := (request.getObjValAs? String "principal").toOption.getD ""
      if let some (world, object) := splitReference srv ((request.getObjValAs? String "object").toOption.getD "") reader then
        return (srv, match readForeign srv world (if op == "world-view" then "view" else "card") object reader with
          | some (r, cite) => r.setObjVal! "asOf" cite
          | none => errorJson s!"{world} is not a world served here")
    let (srv, opened) ← world srv key
    match opened with
    | .error e => return (srv, errorJson e)
    | .ok session =>
      let (session, r) ← PackageSession.stepIO session (if root then bare else bare.setObjVal! "resident" (Json.bool true))
        (foreignFor srv key)
      let mut srv := { srv with worlds := srv.worlds.insert key session }
      let clock := (session.world.map fun (o : Host.Open) => o.world.clock).getD 0
      let mut out := match r with
        | .ok j => j
        | .error e => errorJson e
      if key.startsWith "scratch/" then
        let (next, home) ← homeClock srv
        srv := { next with scratches := next.scratches.insert key home }
      else if key == srv.config.home then
        -- The home clock moving is what expires scratch worlds.
        if op == "world-advance" then srv ← expire srv clock
        if op == "world-status" && (out.getObjValAs? String "status").toOption == some "world" then
          let open_ := srv.scratches.size
          let expiring := (srv.scratches.toList.filter fun (_, t) => t + Host.Limits.scratchMinutes ≤ clock + 60).length
          out := out.setObjVal! "scratches" (Json.mkObj [("open", toJson open_), ("expiring", toJson expiring)])
      return (srv, out)

def usage : String :=
  "usage: delvetalk-obend serve --state DIR [--socket PATH] [--root-socket PATH] [--root-group GROUP] [--opener DID] [--library DIR] [--sync none|fsync|full] [--clock P] [--home NAME]"

def parseArgs (args : List String) (c : Config) : Except String Config :=
  match args with
  | [] => pure c
  | "--state" :: v :: rest => parseArgs rest { c with state := v, rootSocket := (v : System.FilePath) / "root" / "root.sock" }
  | "--root-socket" :: v :: rest => parseArgs rest { c with rootSocket := v }
  | "--socket" :: v :: rest => parseArgs rest { c with socket := v }
  | "--root-group" :: v :: rest => parseArgs rest { c with rootGroup := v }
  | "--opener" :: v :: rest => parseArgs rest { c with opener := v }
  | "--library" :: v :: rest => parseArgs rest { c with library := if v.isEmpty then none else some v }
  | "--sync" :: v :: rest =>
    if ["none", "fsync", "full"].contains v then parseArgs rest { c with sync := v } else throw usage
  | "--clock" :: v :: rest => parseArgs rest { c with clock := v }
  | "--home" :: v :: rest => if Host.validWorldName v then parseArgs rest { c with home := v } else throw "--home must be a world name"
  | _ => throw usage

/-- `serve`: 0 when told to stop, 75 when another process holds the directory, 64 on bad arguments. -/
def main (args : List String) : IO UInt32 := do
  let errors ← IO.getStderr
  -- `--root-socket` may come before `--state`; the state's default applies only when it is not given.
  let config ← match parseArgs args { state := "", rootSocket := "" } with
    | .ok c => pure c
    | .error e => errors.putStrLn e; return 64
  if config.state.toString.isEmpty then errors.putStrLn usage; return 64
  let given := args.contains "--root-socket"
  let config := if given then config else { config with rootSocket := config.state / "root" / "root.sock" }
  let config := if args.contains "--socket" then config else { config with socket := config.state / "host.sock" }
  IO.FS.createDirAll config.state
  -- The directory's lock before anything else is touched (deploy/one-writer.sh's contract).
  let lockPath := config.state / "journal.lock"
  let lock ← IO.FS.Handle.mk lockPath .append
  unless ← lock.tryLock (exclusive := true) do
    errors.putStrLn s!"serve: {lockPath} is held: another process owns the journal; refusing to start a second writer"
    return 75
  let mut srv : Server := { config, lock := some lock }
  if let some lib := config.library then
    let target := config.state / "library"
    sealLibrary lib target
    srv := { srv with sealed := some target.toString }
    let (stateless, r) ← PackageSession.stepIO {} (Json.mkObj [("op", toJson "library-load"), ("path", toJson target.toString)])
    srv := { srv with stateless, libraryPin := r.toOption.bind (·.getObjValAs? String "pin" |>.toOption) }
  srv := { srv with sha := ← binaryPin (config.state / "binary-pin") (← IO.appPath) }
  -- Every world of the directory is held from the start, so a turn in one may read another.
  for f in ← config.state.readDir do
    if f.fileName.endsWith ".journal" then
      let name := (f.fileName.dropEnd 8).toString
      if Host.validWorldName name then srv := (← world srv name).1
  let (opened, clock) ← homeClock srv
  srv ← findScratches opened clock
  let pidfile := config.state / "serve.pid"
  IO.FS.writeFile pidfile (toString (← IO.Process.getPID))
  for p in [config.socket, config.rootSocket] do
    if let some dir := p.parent then IO.FS.createDirAll dir
  listen config.socket.toString config.rootSocket.toString config.rootGroup
  let timing := (← IO.getEnv "DELVETALK_TIMING") == some "1"
  repeat
    let got ← next
    if got.isEmpty then break
    let started ← IO.monoMsNow
    let parts := got.splitOn " "
    let id := (parts.headD "").toNat?.getD 0
    let root := parts.getD 1 "" == "1"
    let line := (got.drop ((parts.headD "").length + (parts.getD 1 "").length + 2)).toString
    IO.FS.writeFile pidfile (toString (← IO.Process.getPID))
    let request : Except String Json := do
      if line.utf8ByteSize > Delvetalk.Bounds.maxFrameBytes then throw s!"package frame exceeds maxFrameBytes ({Delvetalk.Bounds.maxFrameBytes} bytes)"
      if !Delvetalk.scalarEscapesText line then throw "malformed Unicode escape"
      Json.parse line
    let (next, out) ← match request with
      | .ok j => answer srv j root
      | .error _ => pure (srv, errorJson "request is not a JSON object")
    srv := next
    reply id.toUInt64 out.compress
    if timing then
      errors.putStrLn (timingLine (request.toOption.getD Json.null) out ((← IO.monoMsNow) - started))
      errors.flush
  closeAll
  if let some held := srv.lock then held.unlock
  for p in [config.socket, config.rootSocket, pidfile] do
    try IO.FS.removeFile p catch _ => pure ()
  return 0

end Delvetalk.Serve
