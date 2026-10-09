import Delvetalk.Package
import Delvetalk.Host.Ops

namespace Delvetalk.PackageSession
open Lean (Json toJson)

/-- Only this process's successful compiler outputs enter the cache. Digests are
    never lookup keys: both compile requests and claimed artifacts compare whole
    Json values, including source, configuration and executable packet. -/
structure Entry where
  request : Json
  artifact : Json
  bytes : Nat

abbrev Cache := List Entry

def maxBytes : Nat := 8388608

def fit : Nat → List Entry → List Entry
  | _, [] => []
  | remaining, entry :: rest =>
      if entry.bytes ≤ remaining then entry :: fit (remaining - entry.bytes) rest else []

def retain (cache : Cache) (request artifact : Json) : Cache :=
  let bytes := request.compress.utf8ByteSize + artifact.compress.utf8ByteSize
  if bytes > maxBytes then cache
  else ⟨request, artifact, bytes⟩ :: fit (maxBytes - bytes) (cache.take 7)

def compiled (artifact : Json) : Json :=
  Json.mkObj [("status", toJson "compiled"), ("artifact", artifact)]

/-- Computation reuse only. No world, principal, law, result or receipt is cached.
    Unknown artifacts follow ordinary source recompilation; execution always
    checks/materializes the current arguments with the current request budgets. -/
def step (cache : Cache) (request : Json) : Cache × Except String Json :=
  match request.getObjValAs? String "op" with
  | .ok "compile" =>
      match cache.find? (fun entry => entry.request == request) with
      | some entry => (cache, .ok (compiled entry.artifact))
      | none => match Package.compile request with
        | .error error => (cache, .error error)
        | .ok artifact => (retain cache request artifact, .ok (compiled artifact))
  | .ok operation =>
      let known := match request.getObjVal? "artifact" with
        | .ok artifact => cache.any (fun entry => entry.artifact == artifact)
        | .error _ => false
      if known && operation == "run" then (cache, Package.runVerified request)
      else if known && operation == "run-data-v1" then (cache, Package.runDataVerified request)
      else (cache, Package.job request)
  | .error _ => (cache, Package.job request)

/-- Per-process state: the compile cache beside an optional open World. -/
structure Session where
  cache : Cache := []
  world : Host.Session := none

/-- World ops own their journal file; everything else is `step`. -/
def stepIO (session : Session) (request : Json) : IO (Session × Except String Json) := do
  match request.getObjValAs? String "op" with
  | .ok op =>
    if Host.isWorldOp op then
      let (world, result) ← Host.stepWorld session.world request
      return ({ session with world }, result)
    else
      let (cache, result) := step session.cache request
      return ({ session with cache }, result)
  | .error _ =>
    let (cache, result) := step session.cache request
    return ({ session with cache }, result)

end Delvetalk.PackageSession
