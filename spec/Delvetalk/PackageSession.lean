import Delvetalk.Package
import Delvetalk.Host.Session

namespace Delvetalk.PackageSession
open Lean (Json toJson)

/-- A prepared closure, keyed by the request's modules (or single source) and limits. -/
structure Front where
  modules : Json
  limits : Json
  request : Package.PreparedRequest
  bytes : Nat

/-- A compiled entry held decoded and checked, with the artifact it was compiled to. -/
structure Held where
  artifact : Json
  entry : Delvetalk.CheckedEntry
  bytes : Nat

/-- Computation reuse only: this process's own compiler outputs. No world, principal, law,
result or receipt is cached. A claimed artifact runs from the cache only when it equals,
as a whole JSON value, the artifact this process compiled under the same pin; otherwise
its source is recompiled (through the front cache) and compared. -/
structure Cache where
  fronts : List Front := []
  frontBytes : Nat := 0
  held : Std.HashMap String Held := {}
  order : Array String := #[]
  heldBytes : Nat := 0
  hits : Nat := 0
  misses : Nat := 0
  /-- Libraries this process sealed (`library-load`), newest first, at most `maxLibraries`. -/
  libraries : List Host.Library := []

def modulesKey (j : Json) : Json :=
  match j.getObjVal? "modules" with
  | .ok modules => modules
  | .error _ => (j.getObjVal? "source").toOption.getD .null

def sourceBytes (modules : Json) : Nat :=
  match modules with
  | .arr items => items.foldl (fun n m => n + ((m.getObjValAs? String "source").toOption.map String.utf8ByteSize).getD 0) 0
  | .str source => source.utf8ByteSize
  | _ => 0

/-- The prepared closure of a request: from the cache, or prepared and retained (newest
first; the oldest leave when the source bytes would exceed the bound). -/
def front (cache : Cache) (j : Json) : Cache × Except Minidregg.Compiler.ObjectiveBendFrontEnd.Diagnostic Package.PreparedRequest :=
  let modules := modulesKey j
  let limits := Package.getLimits j
  match cache.fronts.find? (fun f => f.limits == limits && f.modules == modules) with
  | some f => (cache, .ok f.request)
  | none =>
    match Package.prepareRequest j with
    | .error e => (cache, .error e)
    | .ok request =>
      let bytes := sourceBytes modules
      if bytes > Bounds.frontCacheSourceBytes then (cache, .ok request) else
      let rec keep : List Front → Nat → List Front
        | [], _ => []
        | f :: rest, room => if f.bytes ≤ room then f :: keep rest (room - f.bytes) else []
      let fronts := keep cache.fronts (Bounds.frontCacheSourceBytes - bytes)
      ({ cache with fronts := ⟨modules, limits, request, bytes⟩ :: fronts,
                    frontBytes := bytes + fronts.foldl (· + ·.bytes) 0 }, .ok request)

/-- The UTF-8 size of `j.compress`, without rendering it. -/
partial def compressedSize : Json → Nat
  | .null => 4
  | .bool b => if b then 4 else 5
  | .num n => n.toString.utf8ByteSize
  | .str s => stringSize s
  | .arr items => 2 + (if items.isEmpty then 0 else items.size - 1) + items.foldl (· + compressedSize ·) 0
  | .obj fields =>
    let (n, total) := fields.foldl (fun (n, total) key value => (n + 1, total + stringSize key + 1 + compressedSize value)) (0, 0)
    2 + (if n == 0 then 0 else n - 1) + total
where
  stringSize (s : String) : Nat :=
    2 + s.foldl (fun n c =>
      n + if c == '"' || c == '\\' || c == '\n' || c == '\r' then 2 else if c.val < 0x20 then 6 else c.utf8Size) 0

/-- Hold a compiled entry under its pin; the oldest leave when the bound would be exceeded. -/
def hold (cache : Cache) (artifact : Json) (entry : Delvetalk.CheckedEntry) : Cache := Id.run do
  let bytes := compressedSize artifact
  if bytes > Bounds.entryCacheBytes then return cache
  let mut cache := cache
  if let some old := cache.held[entry.pin]? then
    cache := { cache with held := cache.held.erase entry.pin, heldBytes := cache.heldBytes - old.bytes,
                          order := cache.order.filter (· != entry.pin) }
  let mut order := cache.order
  let mut held := cache.held
  let mut total := cache.heldBytes
  let mut drop := 0
  while total + bytes > Bounds.entryCacheBytes && drop < order.size do
    if let some old := held[order[drop]!]? then
      total := total - old.bytes
      held := held.erase order[drop]!
    drop := drop + 1
  return { cache with held := held.insert entry.pin ⟨artifact, entry, bytes⟩,
                      order := (order.extract drop order.size).push entry.pin, heldBytes := total + bytes }

def compiledReply (artifact : Json) : Json :=
  Json.mkObj [("status", toJson "compiled"), ("artifact", artifact)]

/-- Compile the request's entry through the front cache and hold it. -/
def compile (cache : Cache) (j : Json) : Cache × Except String (Json × Delvetalk.CheckedEntry) :=
  match j.getObjValAs? String "entry" with
  | .error e => (cache, .error e)
  | .ok entry =>
    let (cache, request) := front cache j
    match request.bind fun request => (Package.compileEntryFrom request entry).mapError (Package.withHint j) with
    | .error d => (cache, .error (Package.Diagnostic.render d))
    | .ok compiled =>
      if !compiled.laws.isEmpty then (cache, .error "package laws require a host law adapter; this pure profile refuses them")
      else (hold cache compiled.artifact compiled.entry, .ok (compiled.artifact, compiled.entry))

/-- The held entry of a claimed artifact: from the cache when it is exactly the artifact
held under its pin, else by recompiling its claimed source and comparing. -/
def entryOf (cache : Cache) (artifact : Json) : Cache × Except String Delvetalk.CheckedEntry :=
  let pin := (artifact.getObjValAs? String "packetSha256").toOption.getD ""
  -- `{"packetSha256": pin}` alone names an entry this process compiled: the pin is the CID
  -- of its own packet. Nothing to verify, nothing to parse beyond the pin.
  let pinOnly := match artifact with
    | .obj fields => fields.size == 1
    | _ => false
  match cache.held[pin]? with
  | some h => if pinOnly || h.artifact == artifact then ({ cache with hits := cache.hits + 1 }, .ok h.entry)
      else recompile pin
  | none => if pinOnly then ({ cache with misses := cache.misses + 1 },
        .error "unknown packetSha256: this process holds no such entry; send the whole artifact")
      else recompile pin
where recompile (_pin : String) : Cache × Except String Delvetalk.CheckedEntry :=
  let cache := { cache with misses := cache.misses + 1 }
  if (artifact.getObjValAs? String "schema").toOption != some "delvetalk.obend-package.v1" then
    (cache, .error "unsupported package artifact")
  else
    let request := Json.mkObj [("modules", (artifact.getObjVal? "modules").toOption.getD .null),
      ("entry", (artifact.getObjVal? "entry").toOption.getD .null), ("limits", (artifact.getObjVal? "limits").toOption.getD .null)]
    match compile cache request with
    | (cache, .error e) => (cache, .error e)
    | (cache, .ok (rebuilt, entry)) =>
      if rebuilt == artifact then (cache, .ok entry)
      else (cache, .error "artifact does not match recompilation of its claimed source")

def status (cache : Cache) : Json :=
  Json.mkObj [("status", toJson "packet-cache"), ("fronts", toJson cache.fronts.length),
    ("frontSourceBytes", toJson cache.frontBytes), ("maxFrontSourceBytes", toJson Bounds.frontCacheSourceBytes),
    ("entries", toJson cache.held.size), ("entryBytes", toJson cache.heldBytes),
    ("maxEntryBytes", toJson Bounds.entryCacheBytes), ("hits", toJson cache.hits), ("misses", toJson cache.misses)]

/-- Runs of a held entry never decode the packet or re-check the package. -/
def runHeld (entry : Delvetalk.CheckedEntry) (operation : String) (j : Json) (world : Option Host.World := none) :
    Except String Json := do
  let limits := Package.getLimits j
  if operation == "run" then
    let profile := (j.getObjValAs? Bool "profile").toOption.getD false
    Package.executeEntry entry (← j.getObjVal? "arguments") limits profile
  else if operation == "run-data-v1" then
    Package.executeDataEntryWire entry (← j.getObjVal? "arguments") limits
  else if operation == "turn-start" then
    let j ← Host.withBindingContext world entry j
    Delvetalk.Turn.startEntryJson entry (← j.getObjVal? "arguments") limits j
  else if operation == "turn-resume" then
    Delvetalk.Turn.resumeEntryJson entry (← j.getObjVal? "checkpoint") (← j.getObjVal? "response") limits j
  else throw "unsupported held operation"

def step (cache : Cache) (request : Json) (world : Option Host.World := none) : Cache × Except String Json :=
  match request.getObjValAs? String "op" with
  | .ok "compile" =>
      match compile cache request with
      | (cache, .ok (artifact, _)) => (cache, .ok (compiledReply artifact))
      | (cache, .error e) => (cache, .error e)
  | .ok "packet-cache-status" => (cache, .ok (status cache))
  | .ok operation =>
      if ["run", "run-data-v1", "turn-start", "turn-resume"].contains operation then
        match request.getObjVal? "artifact" with
        | .error e => (cache, .error e)
        | .ok artifact =>
          let (cache, entry) := entryOf cache artifact
          (cache, entry.bind fun entry => runHeld entry operation request world)
      else (cache, Package.job request)
  | .error _ => (cache, Package.job request)

/-- Sealed libraries a stateless process keeps (`library-load`). -/
def maxLibraries : Nat := 4

/-- `check-package` and `compile` may name a sealed library by `library: <pin>` instead of sending
    its modules: the pin is resolved among the open world's libraries, then those `library-load`
    sealed in this process, and the request's own modules are put over it (`Host.overLibrary`).
    Any other request is as sent. -/
def overLibrary (cache : Cache) (world : Option Host.World) (request : Json) : Except String Json := do
  let some pin := (request.getObjValAs? String "library").toOption | return request
  let some lib := (world.bind (·.libraries[pin]?)).orElse fun _ => cache.libraries.find? (·.pin == pin)
    | throw s!"unknown library pin {pin}: open a world sealed with it, or send library-load first"
  let modules ← Host.overLibrary lib (← Host.requestModules request)
  let rest := (request.getObj?.toOption.map (·.toList) |>.getD []).filter fun (k, _) =>
    k != "library" && k != "modules" && k != "source"
  return Json.mkObj (("modules", Host.modulesJson modules) :: rest)

/-- `library-load {path}`: seal the library directory at `path` in this process (as `world-open
    {library}` does) and keep it for `library: <pin>`; answers `{status: "library", pin, modules}`. -/
def libraryLoad (cache : Cache) (request : Json) : IO (Cache × Except String Json) := do
  let .ok path := request.getObjValAs? String "path" | return (cache, .error "library-load needs a path")
  match ← Host.loadLibrary path with
  | .error e => return (cache, .error e)
  | .ok lib =>
    let kept := (lib :: cache.libraries.filter (·.pin != lib.pin)).take maxLibraries
    return ({ cache with libraries := kept }, .ok (Json.mkObj [("status", toJson "library"),
      ("pin", toJson lib.pin), ("modules", toJson lib.modules.length)]))

/-- Per-process state: the compile cache beside an optional open World. -/
structure Session where
  cache : Cache := {}
  world : Host.Session := none

/-- World ops own their journal file; everything else is `step`. -/
def stepIO (session : Session) (request : Json) : IO (Session × Except String Json) := do
  match request.getObjValAs? String "op" with
  | .ok op =>
    if Host.isWorldOp op then
      let (world, result) ← Host.stepWorld session.world request
      return ({ session with world }, result)
    else if op == "library-load" then
      let (cache, result) ← libraryLoad session.cache request
      return ({ session with cache }, result)
    else
      let world := session.world.map (·.world)
      let request ← if op == "check-package" || op == "compile" then
          match overLibrary session.cache world request with
          | .ok r => pure r
          | .error e => return (session, .error e)
        else pure request
      let (cache, result) := step session.cache request world
      return ({ session with cache }, result)
  | .error _ =>
    let (cache, result) := step session.cache request
    return ({ session with cache }, result)

end Delvetalk.PackageSession
