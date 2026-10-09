/- Compact read guards select retained exact preimages. The digest is a locator;
   the ordinary receiver still compares Json roots and checks current authority.
   Retention scales with admitted history; queries never scan that history. -/
import FileCustody
import Compiler.Sha256
import Std.Data.TreeMap
open Lean World

namespace RetainedRoots

def profile := "delvetalk-retained-root-v1"
abbrev Key := String × String
def compareKey (a b : Key) : Ordering :=
  match compare a.1 b.1 with
  | .eq => compare a.2 b.2
  | other => other
abbrev Index := Std.TreeMap Key (Array Json) compareKey
def digest (root : Json) : String :=
  Minidregg.Compiler.Sha256.hexString (FileCustody.encode root)

-- A bucket retains collisions rather than treating digest equality as Json
-- equality. An ambiguous locator cannot be used as a guard.
def insert (index : Index) (object : String) (root : Json) : Index := Id.run do
  if root == .null then return index
  let key := (object, digest root)
  let prior := index[key]?.getD #[]
  if prior.contains root then return index
  return index.insert key (prior.push root)

def collect (index : Index) (roots : Json) : Index :=
  ((pairs roots).toOption.getD []).foldl (fun acc (id, root) => insert acc id root) index

def isReference (value : Json) : Bool :=
  (str value "profile").toOption == some profile

def resolve (index : Index) (object : String) (value : Json) : Except String Json := do
  if !isReference value then return value
  let fields ← pairs value
  if fields.length != 3 || !(fields.all (fun item => ["profile", "object", "key"].contains item.1)) then
    throw "malformed retained root reference"
  if (← str value "object") != object then throw "retained root reference object differs"
  let some bucket := index[(object, ← str value "key")]? | throw "unknown retained root reference"
  if bucket.size != 1 then throw "ambiguous retained root reference"
  return bucket[0]!

def reference (index : Index) (object : String) (root : Json) : Except String Json := do
  if root == .null then throw "absence is not a retained root"
  let value := obj [("profile", .str profile), ("object", .str object), ("key", .str (digest root))]
  if (← resolve index object value) != root then throw "retained root differs"
  return value

def expandRequest (index : Index) (request : Json) : Except String Json := do
  let mut expanded := request
  if let some expected := (field request "expected").toOption then
    expanded ← put expanded "expected" (← resolve index (← str request "object") expected)
  if let some reads := (field request "reads").toOption then
    let entries ← (← pairs reads).mapM fun (id, root) => do
      return (id, ← resolve index id root)
    expanded ← put expanded "reads" (obj entries)
  return expanded

-- View refresh/publication guards expand only inside receiving custody. The
-- query callback sees an exact root; its transport never returns that root.
def expandView (index : Index) (request : Json) : Except String Json := do
  match (field request "expected").toOption with
  | none => return request
  | some expected =>
    if !isReference expected then throw "opaque view refused"
    match resolve index (← str request "object") expected with
    | .error _ => throw "opaque view refused"
    | .ok root => put request "expected" root

abbrev Admit := Json → Json → String → Except String (Json × Json)
-- This callback belongs INSIDE handleWith: retries compare the original compact
-- request before expansion, and receipts retain that original request.
def wrap (admit : Admit) (index : Index) : Admit := fun world request principal => do
  if (str request "op").toOption == some "opaque-transaction" then
    -- Keep the public selection compact for source preparation. Resolve its
    -- exact owner locator here without exporting or replacing the envelope.
    let expected ← field request "expected"
    if !isReference expected then throw "opaque transaction refused"
    match resolve index (← str request "object") expected with
    | .error _ => throw "opaque transaction refused"
    | .ok _ => admit world request principal
  else if (str request "op").toOption == some "opaque-invoke" then
    let expected := (field request "expected").toOption.getD .null
    if !isReference expected then throw "opaque invocation refused"
    match expandRequest index request with
    | .ok expanded => admit world expanded principal
    | .error _ => throw "opaque invocation refused"
  else admit world (← expandRequest index request) principal

def admission (index : Index) (entry : Json) : Index := Id.run do
  if (field entry "receipt" >>= fun receipt => str receipt "kind").toOption != some "committed" then
    return index
  let mut result := index
  if let some request := (field entry "request").toOption then
    if let some reads := (field request "reads").toOption then
      for (id, root) in (pairs reads).toOption.getD [] do
        if !isReference root then result := insert result id root
    if let some expected := (field request "expected").toOption then
      if !isReference expected then
        if let some id := (str request "object").toOption then result := insert result id expected
  if let some data := (field entry "receipt" >>= fun receipt => field receipt "data").toOption then
    if let some roots := (field data "roots").toOption then result := collect result roots
    if let some roots := (field data "allocated").toOption then result := collect result roots
    if let some root := (field data "root").toOption then
      if let some id := (field entry "request" >>= fun request => str request "object").toOption then
        result := insert result id root
  return result

def fromWorld (world : Json) : Index := Id.run do
  let mut result := collect {} ((field world "objects").toOption.getD (obj []))
  for entry in ((field world "receipts" >>= Json.getArr?).toOption.getD #[]) do
    result := admission result entry
  -- Private opaque evidence is trusted custody, never participant history.
  for (_, intents) in ((field world "opaqueCustody" >>= pairs).toOption.getD []) do
    for (_, entry) in (pairs intents).toOption.getD [] do
      result := admission result entry
  return result

-- Only changed roots are hashed at an incremental boundary. This includes
-- before-images independently of the shape of the emitted receipt.
def changed (index : Index) (before after : Json) : Index := Id.run do
  let old := (field before "objects").toOption.getD (obj [])
  let next := (field after "objects").toOption.getD (obj [])
  let mut result := index
  for (id, root) in (pairs next).toOption.getD [] do
    if (field old id).toOption != some root then
      if let some prior := (field old id).toOption then result := insert result id prior
      result := insert result id root
  return result

def mint (index : Index) (request : Json) : Except String Json := do
  if (FileCustody.encode request).utf8ByteSize > World.maxRequestBytes then throw "retained root mint capacity"
  let entries ← pairs request
  if entries.length != 3 || !(entries.all (fun item => ["op", "object", "root"].contains item.1)) then
    throw "retained root mint requires exactly op, object and root"
  reference index (← str request "object") (← field request "root")

-- Read a bounded set and mint its locators in the same native observation. The
-- optional guards bind a discovery pass to an earlier capture without refreshing
-- it. File custody has no journal head; resident custody adds its committed head.
def capture (index : Index) (world request : Json) : Except String Json := do
  let fields ← pairs request
  if fields.length != 4 || !(fields.all (fun item => ["op", "objects", "principal", "expected"].contains item.1)) then
    throw "root capture requires exactly op, objects, principal and expected"
  let principal ← str request "principal"
  if principal.isEmpty then throw "root capture requires principal"
  let values ← (← field request "objects").getArr?
  if values.isEmpty || values.size > 17 then throw "root capture object capacity"
  let ids ← values.toList.mapM Json.getStr?
  if ids.any String.isEmpty || ids.eraseDups.length != ids.length then throw "root capture object identities"
  let objects ← field world "objects"
  for (id, expected) in (← pairs (← field request "expected")) do
    if !ids.contains id then throw "root capture guard outside selected objects"
    if expected == .null then
      if (field objects id).toOption.isSome then throw "stale capture absence"
    else
      let current ← readObject objects id principal
      let root ← resolve index id expected
      if current != root then throw "stale capture root"
  let mut roots := []
  let mut rootBytes := 0
  for id in ids do
    let value ← if (field objects id).toOption.isNone then pure .null else do
      let root ← readObject objects id principal
      rootBytes := rootBytes + (FileCustody.encode root).utf8ByteSize
      if rootBytes > 60 * 1024 * 1024 then throw "root capture response capacity"
      pure (obj [("root", root), ("reference", ← reference index id root)])
    roots := roots ++ [(id, value)]
  return obj [("roots", obj roots),
    ("sequence", toJson (← (← field world "receipts").getArr?).size), ("head", .null)]

def handleWith (admit : Admit) (world request : Json) : Except String (Json × Json) := do
  if (← str request "op") == "catalogue-page" then
    return (world, ← World.cataloguePage world request (← (← field world "receipts").getArr?).size .null)
  if (← str request "op") == "retained-root" then
    return (world, ← mint (fromWorld world) request)
  if (← str request "op") == "capture-roots" then
    return (world, ← capture (fromWorld world) world request)
  let hasExpected := ((field request "expected").toOption.map isReference).getD false
  let hasReads := ((field request "reads" >>= pairs).toOption.getD []).any (fun entry => isReference entry.2)
  if !hasExpected && !hasReads then return ← World.handleWith admit world request
  World.handleWith (wrap admit (fromWorld world)) world request

-- Preparation executes against retained captured observations, even when the
-- current object has advanced. Admission of the resulting request checks current
-- exact roots later. No preparation observation is refreshed here.
def prepareCaptured (index : Index) (current : Json) (run : Index → Json → Json → Json → Except String Json)
    (request : Json) : Except String Json := do
  if (FileCustody.encode request).utf8ByteSize > World.maxRequestBytes then throw "retained preparation capacity"
  let id ← str request "object"
  let principal ← str request "principal"
  let currentObjects ← field current "objects"
  -- Read permission belongs to the current host, independently of which old
  -- preimage preparation observes. Never authorize a read using captured law.
  discard (readObject currentObjects id principal)
  let root ← resolve index id (← field request "root")
  let observations ← (← field request "observations").getArr?
  if observations.size > 16 then throw "retained observation capacity"
  let mut objects := obj [(id, root)]
  let mut expandedObservations := #[]
  for observation in observations do
    let target ← str observation "object"
    discard (readObject currentObjects target principal)
    let captured ← resolve index target (← field observation "root")
    objects ← put objects target captured
    expandedObservations := expandedObservations.push (← put observation "root" captured)
  let expanded ← put (← put request "root" root) "observations" (.arr expandedObservations)
  run index currentObjects (obj [("objects", objects), ("receipts", .arr #[])]) expanded

end RetainedRoots
