/- Resident receiving state and a prepare/finalize journal boundary.
   Physical custody may retain bytes, but receipt selection and admission remain
   here. Export alone expands the ordered receipt history into its legacy array. -/
import FileCustody
import RetainedRoots
import Compiler.Sha256
import Std.Data.TreeMap
open Lean World

namespace ResidentStore

abbrev Admit := Json → Json → String → Except String (Json × Json)
abbrev Key := String × String
def compareKey (a b : Key) : Ordering :=
  match compare a.1 b.1 with
  | .eq => compare a.2 b.2
  | other => other
abbrev Index := Std.TreeMap Key Json compareKey
abbrev HistoryIndex := Std.TreeMap Nat Json compare

def genesis : String := Minidregg.Compiler.Sha256.hexString "delvetalk-resident-v1"
def digest (value : Json) : String := Minidregg.Compiler.Sha256.hexString (FileCustody.encode value)

structure State where
  base : Json := World.empty
  index : Index := {}
  roots : RetainedRoots.Index := {}
  history : List Json := []
  ordered : HistoryIndex := {}
  sequence : Nat := 0
  head : String := genesis

structure Prepared where
  next : State
  entry : Json

structure Session where
  committed : State := {}
  pending : Option Prepared := none

def exactFields (value : Json) (keys : List String) : Except String Unit := do
  let actual := (← pairs value).map Prod.fst
  if actual.length != keys.length || !(actual.all keys.contains) then
    throw "resident frame has missing or unknown fields"

def requestKey (request : Json) : Except String Key := do
  return (← str request "principal", ← str request "intent")

def remember (state : State) (key : Key) (admission base : Json) (head : String)
    (trackChanges : Bool := true) : State :=
  { base, index := state.index.insert key admission,
    roots := RetainedRoots.admission
      (if trackChanges then RetainedRoots.changed state.roots state.base base else state.roots) admission,
    history := admission :: state.history,
    ordered := state.ordered.insert state.sequence admission,
    sequence := state.sequence + 1, head }

def selected (state : State) (request : Json) : Array Json :=
  match (requestKey request).toOption.bind (fun key => state.index[key]?) with
  | some entry => #[entry]
  | none => #[]

def expand (state : State) : Except String Json :=
  put state.base "receipts" (.arr state.history.reverse.toArray)

-- Structural patches describe physical changes, not executable behavior.
-- Nested registries (including retained message events) emit only changed paths;
-- arrays/scalars remain atomic. Traversal may scale with current data, never with
-- the receipt history kept separately below.
partial def changes (before after : Json) (path : List String := []) : Array Json := Id.run do
  if before == after then return #[]
  let location := .arr (path.map Json.str).toArray
  match before, after with
  | .obj old, .obj next =>
    let mut result := #[]
    for (key, value) in next.toList do
      match old[key]? with
      | some prior => result := result ++ changes prior value (path ++ [key])
      | none => result := result.push (obj [
          ("path", .arr ((path ++ [key]).map Json.str).toArray), ("value", value)])
    for (key, _) in old.toList do
      if next[key]?.isNone then
        result := result.push (obj [
          ("path", .arr ((path ++ [key]).map Json.str).toArray), ("remove", .bool true)])
    return result
  | _, _ => return #[obj [("path", location), ("value", after)]]

-- The selected receipt is only an optimization of handleWith's search. Its
-- own envelope checks and full Json equality still decide retry/collision.
-- A fresh attempt still passes through the exact selected admission function.
def prepare (admit : Admit) (state : State) (request : Json) :
    Except String (Json × Option Prepared) := do
  let prior := selected state request
  let input ← put state.base "receipts" (.arr prior)
  let (next, reply) ← World.handleWith (RetainedRoots.wrap admit state.roots) input request
  let retained ← (← field next "receipts").getArr?
  if retained.size == prior.size then
    return (obj [("status", .str "settled"), ("reply", reply),
      ("sequence", toJson state.sequence), ("head", .str state.head)], none)
  if !prior.isEmpty || retained.size != 1 then throw "resident receipt append invariant"
  let admission := retained[0]!
  let key ← requestKey request
  let base ← put next "receipts" (.arr #[])
  let frame := obj [("format", .str "delvetalk-resident-entry-v1"),
    ("sequence", toJson (state.sequence + 1)), ("previous", .str state.head),
    ("request", request), ("reply", reply), ("delta", .arr (changes state.base base))]
  let head := digest frame
  let entry ← put frame "head" (.str head)
  let prepared : Prepared := { entry, next := remember state key admission base head }
  return (obj [("status", .str "prepared"), ("entry", entry)], some prepared)

def status (state : State) (kind : String) : Json :=
  obj [("status", .str kind), ("sequence", toJson state.sequence), ("head", .str state.head)]

def applyFrame (admit : Admit) (session : Session) (frame : Json) : Except String (Session × Json) := do
  let op ← str frame "op"
  if op == "status" then
    exactFields frame ["op"]
    if session.pending.isSome then throw "resident has an unfinalized preparation"
    return (session, status session.committed "ready")
  if op == "lookup" then
    exactFields frame ["op", "request"]
    if session.pending.isSome then throw "cannot query a pending preparation"
    let request ← field frame "request"
    let reply ← World.retainedReply (selected session.committed request) request
    return (session, obj [("status", .str "lookup"), ("reply", reply)])
  if op == "prepare" then
    exactFields frame ["op", "request"]
    if session.pending.isSome then throw "finalize or restart the pending preparation before another request"
    let (reply, pending) ← prepare admit session.committed (← field frame "request")
    return ({ session with pending }, reply)
  if op == "finalize" then
    exactFields frame ["op", "head"]
    let head ← str frame "head"
    match session.pending with
    | none =>
      if head != session.committed.head then throw "no matching prepared entry"
      return (session, status session.committed "finalized")
    | some prepared =>
      if head != prepared.next.head then throw "finalization does not name the prepared entry"
      return ({ committed := prepared.next }, status prepared.next "finalized")
  if op == "restore" then
    exactFields frame ["op", "entry"]
    if session.pending.isSome then throw "cannot restore over a pending preparation"
    let expected ← field frame "entry"
    let (_, some actual) ← prepare admit session.committed (← field expected "request")
      | throw "journal contains a non-admission"
    if actual.entry != expected then throw "journal entry does not reproduce exact receiving result"
    return ({ committed := actual.next }, status actual.next "restored")
  throw "unknown resident operation"

-- A checkpoint is trusted local custody sealed by this receiver. Its content
-- digest and journal anchor must be retained by the physical custodian. Rebuild
-- the index here; physical storage never supplies selected authority/receipts.
def admissionKey (entry : Json) : Option Key :=
  ((field entry "request").bind requestKey).toOption

def validateCheckpointAdmission (entry : Json) (key : Key) : Except String Unit := do
  exactFields entry ["request", "receipt"]
  let request ← field entry "request"
  if key.1.isEmpty || key.2.isEmpty || (← str request "op") == "inspect" then
    throw "invalid checkpoint receipt identity"
  if (← field (← field entry "receipt") "intent") != .str key.2 then
    throw "checkpoint receipt intent differs"

def checkedAppend (state : State) (entry : Json) : Except String State := do
  let some key := admissionKey entry | throw "invalid checkpoint receipt identity"
  validateCheckpointAdmission entry key
  if state.index[key]?.isSome then throw "duplicate checkpoint receipt identity"
  return remember state key entry state.base state.head false

def loadCheckpoint (world : Json) (sequence : Nat) (head : String) : Except String State := do
  discard (pairs (← field world "objects"))
  let history ← (← field world "receipts").getArr?
  if history.size != sequence then throw "checkpoint sequence differs from retained history"
  let base ← put world "receipts" (.arr #[])
  let roots := RetainedRoots.collect {} (← field world "objects")
  history.foldlM checkedAppend { base, head, roots }

abbrev Query := Json → Json → Except String Json

def serve (admit : Admit) (query : Query := fun _ _ => .error "query unavailable in this profile")
    (capturedPreparation : RetainedRoots.Index → Json → Query := fun _ _ _ _ => .error "preparation unavailable in this profile") : IO Unit := do
  let stdin ← IO.getStdin
  let stdout ← IO.getStdout
  let mut session : Session := {}
  repeat
    let line ← stdin.getLine
    if line.isEmpty then break
    let result ← try
      if line.utf8ByteSize > 67108864 then throw (IO.userError "resident frame exceeds 64 MiB")
      let frame ← IO.ofExcept (Json.parse line)
      let op ← IO.ofExcept (str frame "op")
      if op == "query" then
        IO.ofExcept (exactFields frame ["op", "request"])
        if session.pending.isSome then throw (IO.userError "cannot query a pending preparation")
        let request ← IO.ofExcept (field frame "request")
        let operation ← IO.ofExcept (str request "op")
        let reply ← IO.ofExcept (
          if operation == "inspect" then do
            World.readObject (← field session.committed.base "objects")
              (← str request "object") (← str request "principal")
          else if operation == "authorize-reads" then
            World.authorizeReads session.committed.base request
          else if operation == "object-history" then
            World.historyPageIndexed session.committed.base request session.committed.sequence
              (fun index => session.committed.ordered[index]?)
          else if operation == "catalogue-page" then
            World.cataloguePage session.committed.base request session.committed.sequence (.str session.committed.head)
          else if operation == "retained-root" then RetainedRoots.mint session.committed.roots request
          else if operation == "capture-roots" then do
            let captured ← RetainedRoots.capture session.committed.roots session.committed.base request
            put (← put captured "sequence" (toJson session.committed.sequence)) "head" (.str session.committed.head)
          else if operation == "prepare-retained" then do
            let captured ← put request "op" (.str "prepare")
            RetainedRoots.prepareCaptured session.committed.roots session.committed.base capturedPreparation captured
          else query session.committed.base request)
        pure (obj [("status", .str "query"), ("reply", reply)])
      else if op == "export" then
        IO.ofExcept (exactFields frame ["op", "path"])
        if session.pending.isSome then throw (IO.userError "cannot export a pending preparation")
        let path ← IO.ofExcept (str frame "path")
        let world ← IO.ofExcept (expand session.committed)
        let raw := FileCustody.encode world ++ "\n"
        IO.FS.writeFile path raw
        let checkpointSeal := obj [("sequence", toJson session.committed.sequence),
          ("head", .str session.committed.head),
          ("sha256", .str (Minidregg.Compiler.Sha256.hexString raw))]
        pure (obj [("status", .str "exported"), ("seal", checkpointSeal)])
      else if op == "load" then
        IO.ofExcept (exactFields frame ["op", "path", "seal"])
        if session.pending.isSome || session.committed.sequence != 0 then
          throw (IO.userError "checkpoint load requires a fresh resident")
        let checkpointSeal ← IO.ofExcept (field frame "seal")
        IO.ofExcept (exactFields checkpointSeal ["sequence", "head", "sha256"])
        let raw ← IO.FS.readFile (← IO.ofExcept (str frame "path"))
        if Minidregg.Compiler.Sha256.hexString raw != (← IO.ofExcept (str checkpointSeal "sha256")) then
          throw (IO.userError "checkpoint content digest differs")
        let state ← IO.ofExcept (loadCheckpoint (← IO.ofExcept (Json.parse raw))
          (← IO.ofExcept ((← IO.ofExcept (field checkpointSeal "sequence")).getNat?))
          (← IO.ofExcept (str checkpointSeal "head")))
        session := { committed := state }
        pure (status state "loaded")
      else
        let (next, reply) ← IO.ofExcept (applyFrame admit session frame)
        session := next
        pure reply
    catch error => pure (obj [("error", .str error.toString)])
    stdout.putStrLn (FileCustody.encode result)
    stdout.flush

end ResidentStore
