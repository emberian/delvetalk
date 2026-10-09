/- Custody-only expansion and source-selected replies. A content locator conveys
   no read or invocation grant. Public receipts and private receiving evidence
   remain separate, including across trusted checkpoint export. -/
import RetainedRoots

namespace OpaqueInteraction
open Lean World

def reference (id : String) (root : Json) : Json :=
  obj [("profile", .str RetainedRoots.profile), ("object", .str id),
    ("key", .str (RetainedRoots.digest root))]

def retain (world request full : Json) : Except String Json := do
  let custody := (field world "opaqueCustody").toOption.getD (obj [])
  let principal ← str request "principal"
  let intents := (field custody principal).toOption.getD (obj [])
  let entry := obj [("request", request), ("receipt", full)]
  put world "opaqueCustody" (← put custody principal (← put intents (← str request "intent") entry))

def transition (runtime : World.Runtime) (world request : Json) (principal : String) :
    Except String (Json × Json) := do
  let fields ← pairs request
  unless fields.length == 7 && fields.all (fun item =>
      ["op", "object", "principal", "intent", "expected", "command", "input"].contains item.1) do
    throw "opaque invocation refused"
  let internal ← put request "op" (.str "invoke")
  let (next, full) ← World.transitionWith runtime world internal principal true
  let data ← field full "data"
  let id ← str request "object"
  let projected := receipt request "committed" (obj [
    ("reference", reference id (← field data "root")),
    ("result", ← field data "result")])
  return (← retain next request full, projected)

-- Do not export source/type/state diagnostics to an invocation-only caller.
-- Exact retries bypass this callback and recover the originally stored reply.
def admit (runtime : World.Runtime) (world request : Json) (principal : String) :
    Except String (Json × Json) :=
  match transition runtime world request principal with
  | .ok result => .ok result
  | .error diagnostic => do
    let projected := receipt request "refused" (.str "opaque invocation refused")
    return (← retain world request (receipt request "refused" (.str diagnostic)), projected)

abbrev View := Json → String → Except String Json

-- A caller can select an exact preimage using invocation authority even when
-- no view is offered. Selection executes no body and grants no future authority.
def select (runtime : World.Runtime) (world request : Json) : Except String Json := do
  let fields ← pairs request
  unless fields.length == 6 && fields.all (fun item =>
      ["op", "object", "principal", "intent", "command", "input"].contains item.1) do
    throw "opaque selection refused"
  let principal ← str request "principal"
  if principal.isEmpty || (← str request "intent").isEmpty then throw "opaque selection refused"
  let id ← str request "object"
  let root ← field (← field world "objects") id
  let internal ← put request "op" (.str "invoke")
  let execution : Evaluation Unit := do
    let prepared ← prepareInvocation runtime root internal
    authorizeRequestWith runtime root prepared.request principal
  let _ ← execution.run runtime.budget
  put (← put request "op" (.str "opaque-invoke")) "expected" (reference id root)

def selectQuery (runtime : World.Runtime) (world request : Json) : Except String Json :=
  match select runtime world request with
  | .ok result => .ok result
  | .error _ => .error "opaque selection refused"

def view (evaluate : View) (world request : Json) : Except String Json := do
  let fields ← pairs request
  unless fields.length >= 4 && fields.length <= 6 && fields.all (fun item =>
      ["op", "object", "principal", "panel", "audience", "expected"].contains item.1) do
    throw "opaque view refused"
  let id ← str request "object"
  let principal ← str request "principal"
  if principal.isEmpty then throw "opaque view refused"
  let root ← field (← field world "objects") id
  let panel ← str request "panel"
  let authority ← field root "law"
  validateLaw authority
  let publication := (field request "audience").toOption == some (.str "public")
  if let some audience := (field request "audience").toOption then
    if audience != .str "public" then throw "opaque view refused"
  let grant := (field authority "view" >>= fun grants => field grants panel).toOption
  if publication && grant != some (.str "public") then throw "opaque view refused"
  match grant with
  | some grant =>
    if grant != .str "public" then
      if !(← law grant).contains principal then throw "opaque view refused"
  | none => discard (readObject (← field world "objects") id principal)
  if let some expected := (field request "expected").toOption then
    if expected != root then throw "opaque view refused"
  let result ← evaluate root panel
  return obj [("reference", reference id root), ("result", result),
    ("panel", .str panel), ("audience", .str (if publication then "public" else "principal"))]

def query (evaluate : View) (world request : Json) : Except String Json :=
  match view evaluate world request with
  | .ok result => .ok result
  | .error _ => .error "opaque view refused"

end OpaqueInteraction
