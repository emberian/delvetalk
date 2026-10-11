/- `delvetalk-obend serve`: the one process that holds a directory of worlds (docs/FEDERATION.md §1,
   HOST-HANDOFF 5.125). It takes the directory's lock, seals the library, listens on the public socket
   and the root socket (`spec/native/serve.c`), and answers one request at a time in arrival order,
   each through the world its envelope names. It replaces `transport/hostd.py` and the process
   management of `transport/hostproc.py`. -/
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

/-- A world this process holds open, and when it last served an op (monotonic ms). -/
structure Held where
  session : PackageSession.Session
  used : Nat

structure Server where
  config : Config
  worlds : Std.HashMap String Held := {}
  /-- The journal-less session: compile, check and run against the sealed library. -/
  stateless : PackageSession.Session := {}
  sealed : Option String := none
  libraryPin : Option String := none
  sha : String := ""
  /-- The directory's lock, held for the life of the process (dropping the handle would release it). -/
  lock : Option IO.FS.Handle := none

/-- A world idle this long is closed; its next op reopens it by replay. -/
def idleMs : Nat := 600000

/-- The packages `world-arrive` creates from; the sealed library holds them beside the library. -/
def arrival : List String := ["Avatar", "Env", "Wake"]

/-- The ops only the root socket takes (docs/ROOT.md §1.4). The opener's ordinary turns are the public
    socket's too; there its privileges are not (`resident`, `Host.openerActs`). -/
def rootOps : List String := ["world-root", "world-library", "world-settings", "world-fork", "world-snapshot", "library-load",
  "world-dump"]

def errorJson (message : String) : Json :=
  Json.mkObj [("status", toJson "error"), ("message", toJson message)]

def hex (bytes : ByteArray) : String :=
  let digits := "0123456789abcdef".toList.toArray
  String.join (bytes.toList.map fun b => String.mk [digits[(b.toNat / 16)]!, digits[(b.toNat % 16)]!])

/-- The binary's SHA-256, hashed once and cached in `cache` by path, size and mtime (as hostd did). -/
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

/-- A principal's private heap until scratch worlds replace it: `did:plc:` and 24 base32 letters. -/
def isHeapDid (did : String) : Bool :=
  let rest := (did.drop 8).toString
  did.startsWith "did:plc:" && rest.length == 24 && rest.all fun c => c.isLower || ('2' ≤ c && c ≤ '7')

/-- Where a world's journal is and how it is opened. A world: `DIR/<name>.journal`, its clock, opener
    and library as configured, its name journaled. A heap: `DIR/heaps/<did>.journal`, its library
    sealed as the DID's. -/
def openRequest (srv : Server) (key : String) : Json :=
  let c := srv.config
  let lib := fun (librarian : String) => match srv.sealed with
    | some path => if librarian.isEmpty then [] else [("library", toJson path), ("principal", toJson librarian)]
    | none => []
  if key.startsWith "heaps/" then
    let did := (key.drop 6).toString
    Json.mkObj ([("op", toJson "world-open"), ("path", toJson (c.state / "heaps" / s!"{did}.journal").toString),
      ("sync", toJson c.sync)] ++ lib did)
  else
    Json.mkObj ([("op", toJson "world-open"), ("path", toJson (c.state / s!"{key}.journal").toString),
      ("sync", toJson c.sync), ("clock", toJson c.clock), ("name", toJson key)] ++
      (if c.opener.isEmpty then [] else [("opener", toJson c.opener)]) ++ lib c.opener)

/-- The open session of world `key`, opening it by replay when it is not held. -/
def world (srv : Server) (key : String) (now : Nat) : IO (Server × Except String PackageSession.Session) := do
  match srv.worlds[key]? with
  | some h => return ({ srv with worlds := srv.worlds.insert key { h with used := now } }, .ok h.session)
  | none =>
    if key.startsWith "heaps/" then IO.FS.createDirAll (srv.config.state / "heaps")
    let (session, r) ← PackageSession.stepIO {} (openRequest srv key)
    match r with
    | .ok j =>
      if (j.getObjValAs? String "status").toOption == some "opened" then
        return ({ srv with worlds := srv.worlds.insert key ⟨session, now⟩ }, .ok session)
      return (srv, .error s!"world {key} did not open: {j.compress}")
    | .error e => return (srv, .error s!"world {key} did not open: {e}")

/-- Close every world idle past `idleMs` but `keep`; its store goes and its file lock with it. -/
def sweep (srv : Server) (keep : String) (now : Nat) : Server :=
  { srv with worlds := srv.worlds.filter fun k h => k == keep || now < h.used + idleMs }

def serveStatus (srv : Server) : Json :=
  let rows := srv.worlds.toList.map fun (k, h) =>
    let w := h.session.world.map (·.world)
    Json.mkObj [("name", toJson k), ("height", toJson ((w.map (·.height)).getD 0)),
      ("objects", toJson ((w.map (·.objects.size)).getD 0)), ("clock", toJson ((w.map (·.clock)).getD 0)),
      ("open", toJson true)]
  Json.mkObj [("status", toJson "serve"), ("worlds", Json.arr (rows.toArray.qsort fun a b =>
    (a.getObjValAs? String "name").toOption.getD "" < (b.getObjValAs? String "name").toOption.getD ""))]

/-- One request, as the socket it came on may ask it. -/
def answer (srv : Server) (request : Json) (root : Bool) : IO (Server × Json) := do
  let some fields := request.getObj?.toOption | return (srv, errorJson "request is not a JSON object")
  let op := (request.getObjValAs? String "op").toOption.getD ""
  if op == "hostd-info" then
    return (srv, Json.mkObj ([("status", toJson "hostd"), ("hostSha256", toJson srv.sha),
      ("pid", toJson (← IO.Process.getPID).toNat), ("replay", toJson Host.Limits.replayEdition)] ++
      ((srv.libraryPin.map fun p => [("library", toJson p)]).getD [])))
  if op == "serve-status" then return (srv, serveStatus srv)
  if op == "world-open" then return (srv, errorJson "serve opens its worlds; name one with `world`")
  if !root && rootOps.contains op then
    return (srv, errorJson "the opener speaks on the root socket")
  -- Every public request is a resident's, whoever it names: the opener's privileges are the root socket's.
  let bare := Json.mkObj (fields.toList.filter fun (k, _) => k != "world" && k != "heap" && k != "stateless" && k != "resident")
  if (request.getObjVal? "stateless").toOption == some (Json.bool true) then
    let (stateless, r) ← PackageSession.stepIO srv.stateless bare
    return ({ srv with stateless }, r.toOption.getD (errorJson (match r with | .error e => e | .ok _ => "")))
  let key : Except String String := match request.getObjVal? "heap", request.getObjVal? "world" with
    | .ok (.str did), _ => if isHeapDid did then .ok s!"heaps/{did}" else .error "heap must be a DID"
    | .ok _, _ => .error "heap must be a DID"
    | _, .ok (.str name) => if Host.validWorldName name then .ok name else .error s!"no world {name} here"
    | _, .ok _ => .error "world must be a name"
    | _, .error _ => .ok srv.config.home
  match key with
  | .error e => return (srv, errorJson e)
  | .ok key =>
    let now ← IO.monoMsNow
    let (srv, opened) ← world srv key now
    match opened with
    | .error e => return (srv, errorJson e)
    | .ok session =>
      let (session, r) ← PackageSession.stepIO session (if root then bare else bare.setObjVal! "resident" (Json.bool true))
      let srv := { srv with worlds := srv.worlds.insert key ⟨session, now⟩ }
      return (sweep srv key now, match r with
        | .ok j => j
        | .error e => errorJson e)

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
  let pidfile := config.state / "hostd.pid"
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
      if line.utf8ByteSize > 16777216 then throw "package frame exceeds 16 MiB"
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
