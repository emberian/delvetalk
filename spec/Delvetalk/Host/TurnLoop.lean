/- Driving an activity against the store. A turn reads committed state, collects
   the roots it viewed and the writes it performed, and ends in exactly one
   `commit`. The wire shapes are those of `world/lib/Plan.obend`; `answer` handles
   every constructor of its Plan (view, write, call/callVia, send/sendVia, create,
   await/awaitUntil, interpret, offer, publish, reprogram, amend, inspect, check,
   grant, revoke, objects, card). A label of some other sum refuses the turn:
   `plan not supported: <label>`. `docs/HOST-HANDOFF.md` section 5 says what each does.
   A method is `(state, [input,] context) -> Activity<Plan, Response, A>` or the
   same with a pure data result (the new state). -/
import Delvetalk.Host.Ops
import Delvetalk.Turn
import Delvetalk.Document

namespace Delvetalk.Host
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Theory.ObjectiveBendTypes (Ty DataBounds)
open Minidregg.Compiler.ObjectiveBendDataWire (dataJson decodeData)

structure TurnRequest where
  principal : String
  object : String
  method : String
  argument : Data
  intent : String
  limits : Json
  /-- Digest of the whole request; binds the identity for retries. -/
  digest : String
  /-- Answer the tick breakdown of the turn's activity segments (not part of the digest). -/
  profile : Bool := false

def parseTurn (j : Json) : Except String TurnRequest := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let object ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let method ← boundedText "method" Limits.maxMethodBytes (← j.getObjValAs? String "method")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  unless Minidregg.Compiler.ObjectiveBendParse.isIdent method.toList do throw "invalid method name"
  let argument ← decodeData Limits.dataDepth (← j.getObjVal? "argument")
  let given ← match j.getObjVal? "limits" with
    | .ok l@(.obj _) => pure l
    | .ok _ => throw "limits must be an object"
    | .error _ => pure (Json.mkObj [])
  let limits := if (given.getObjVal? "ticks").toOption.isSome then given
    else given.setObjVal! "ticks" (toJson (toString Limits.maxTurnTicks))
  if let some asked := ← optNat given "ticks" then
    if asked > Limits.maxTurnTicks then throw "ticks exceeds the turn ceiling"
  let digest := Journal.bodyHash (Json.mkObj [("principal", toJson principal), ("object", toJson object),
    ("method", toJson method), ("argument", dataJson argument), ("limits", limits)])
  let profile ← match j.getObjVal? "profile" with
    | .ok (.bool b) => pure b
    | .ok _ => throw "profile must be true or false"
    | .error _ => pure false
  return ⟨principal, object, method, argument, intent, limits, digest, profile⟩

inductive Abort where
  /-- The request is not a well-formed turn; nothing is journaled. -/
  | request (message : String)
  /-- The turn is refused by name; a refused entry is journaled. -/
  | evaluation (reason : String)
  /-- A machine budget ran out (`ticks`, `heap`, `stack`, `nodes`, `bytes`): the named
      silence, journaled as class `budget` with the resource as its reason. -/
  | budget (resource : String)
  /-- The turn is refused with a named class other than `evaluation` (`typeMismatch`: the
      argument does not conform to the method's input type). -/
  | refused (cls reason : String)
  /-- The turn awaits a slot: its activity is checkpointed and journaled. -/
  | suspend (principal intent : String) (patience : Nat) (checkpoint : Delvetalk.Turn.Checkpoint)
      (interpretation : Option Json := none)
  deriving Inhabited

/-- A `send` staged by a turn: it leaves with the commit. `sender` is the sending object (the
    delivered turn's caller); `via` the grant it is sent under, whose grantor the delivery runs as. -/
structure Send where
  to : String
  method : String
  argument : Data
  sender : String
  via : String := ""
  grantor : String := ""

structure TurnState where
  world : World
  roots : List (String × Nat) := []
  /-- The CID of the committed state each root was read at. -/
  rootCids : List (String × String) := []
  writes : List (String × List Written) := []
  /-- The turn's identity principal: it names the entry and derives send and grant ids. -/
  principal : String
  intent : String
  /-- The running frame: whose authority it acts with (the principal, or a grant's grantor),
      the method it runs, and the grant it runs under. -/
  subject : String
  method : String := ""
  via : String := ""
  /-- The running frame's argument: a change it makes carries it to the Bend law. -/
  argument : Data := .record []
  /-- A turn a principal asked for directly (not a delivery): only such a turn may grant. -/
  direct : Bool := true
  grants : List Grant := []
  revokes : List String := []
  /-- Uses of limited grants this turn spent, by grant id. -/
  spent : List (String × Nat) := []
  sends : List Send := []
  programs : List (String × (String × String)) := []
  layered : List String := []
  laws : List (String × String) := []
  ticks : Nat
  plans : Nat := 0
  /-- Rendered `offer` documents in order, each with its addressee: the journal retains them. -/
  offers : List (String × String) := []
  /-- Publications in order, as journaled: `{id, object, page, section, text}`. -/
  publishes : List Json := []
  /-- Objects created, and objects the turn required absent (created ones included). -/
  creates : List (String × CreateRec) := []
  absent : List String := []
  /-- An object a `create` found already there: the turn will be refused naming it. -/
  violation : Option String := none
  /-- Slots this turn already awaited, as identity keys, and how many awaits it has made. -/
  awaited : List String := []
  awaits : Nat := 0
  /-- `check` Plans this turn ran; the journal keeps the count. -/
  checks : Nat := 0
  /-- Frames run under a handler (`run`): the call depth of the frame and the handler object. -/
  handlers : List (Nat × String) := []
  limits : Json
  /-- `profile: true` on the request: every activity segment's tick breakdown, by kind
      (`Delvetalk.Profile`), summed over the turn. Memory only; never journaled. -/
  profiling : Bool := false
  profile : Std.HashMap String (Nat × Nat) := {}

abbrev M := ExceptT Abort (StateM TurnState)

def evaluation {α : Type} (reason : String) : M α := throw (.evaluation reason)

def liftEval {α : Type} (r : Except String α) : M α :=
  match r with
  | .ok a => pure a
  | .error e => throw (.evaluation e)

def recordRoot (id : String) (version : Nat) : M Unit := do
  let s ← get
  unless s.roots.any (·.1 == id) do
    if s.roots.length ≥ Limits.maxRoots then evaluation "turn exceeds the root capacity"
    -- Writes are staged, so what a turn reads of an object is its committed state.
    let cid := (s.world.objects[id]?).bind fun o => if o.version == version then some (stateCid o.state) else none
    set { s with roots := s.roots ++ [(id, version)],
                 rootCids := s.rootCids ++ ((cid.map fun c => [(id, c)]).getD []) }

def field? (fields : List (String × Data)) (name : String) : Option Data := fields.lookup name

def labelOf : Data → Option String
  | .label s => some s
  | _ => none

/-- A Reference naming this world's object. -/
def referenceId : Data → Option String
  | .record f => match (f.lookup "world").bind labelOf, (f.lookup "object").bind labelOf with
      | some "", some id => some id
      | _, _ => none
  | _ => none

def emptyRecord : Data := .record []

/-- A `List<T>` value on the wire: `nil {} | cons {head, tail}`. -/
def listData (items : List Data) : Data :=
  items.foldr (fun x tail => .variant "cons" (.record [("head", x), ("tail", tail)]))
    (.variant "nil" (.record []))


/-- The first payload that makes a response conform to the Response type. -/
def respond (bounds : DataBounds) (responseType : Ty) (label : String) (payloads : List Data) : M Data := do
  for p in payloads do
    let d := Data.variant label p
    if d.conformsUnder bounds responseType then return d
  evaluation s!"response type cannot carry {label}"

def refusedWith (bounds : DataBounds) (responseType : Ty) (clause : String) : M Data :=
  respond bounds responseType "refused" [.record [("clause", .label clause)], emptyRecord]

def compiledMethod (obj : Object) (method : String) : M Compiled := do
  let key := obj.inputsKey ++ "/" ++ method
  let s ← get
  match s.world.compiled[key]? with
  | some c => return c
  | none =>
    -- An extended object's method is compiled from the highest layer that defines it, from
    -- its package's closure prepared once, and held decoded and checked.
    match compileEntryIn s.world (delegate obj.inputs method) method >>= fun (ec, w) => do return (← compiledOf ec, w) with
    | .error e => throw (.request s!"method {method} does not compile: {e}")
    | .ok (c, w) =>
      -- A full cache is emptied and refilled, never left full (which would compile every turn).
      let cache := if w.compiled.size < Limits.maxCompiledPackets then w.compiled else {}
      set { s with world := { w with compiled := cache.insert key c } }
      return c

/-- The held entry of a compiled method (one is held whenever a method compiles). -/
def entryOf (c : Compiled) : M Delvetalk.CheckedEntry :=
  match c.entry with
  | some e => pure e
  | none => match Delvetalk.CheckedEntry.ofPacket c.packet with
    | .ok e => pure e
    | .error e => throw (.request e)

def budgetsNow : M Delvetalk.Turn.Budgets := do
  let s ← get
  liftEval (Delvetalk.Turn.budgets (s.limits.setObjVal! "ticks" (toJson (toString s.ticks))))

def spend (used : Nat) : M Unit :=
  modify fun s => { s with ticks := s.ticks - used }

/-- Add one segment's profile rows (`[{kind, steps, ticks}]`) to the turn's tally. -/
def noteProfile (rows : Unit → Except String Json) : M Unit := do
  unless (← get).profiling do return
  let .ok (.arr rows) := rows () | return
  let add := fun (t : Std.HashMap String (Nat × Nat)) (row : Json) =>
    match row.getObjValAs? String "kind", row.getObjValAs? Nat "steps", row.getObjValAs? Nat "ticks" with
    | .ok k, .ok n, .ok x => let (a, b) := t.getD k (0, 0); t.insert k (a + n, b + x)
    | _, _, _ => t
  modify fun s => { s with profile := rows.foldl add s.profile }

/-- The tally as the kernel prints a profile: heaviest kind first. -/
def profileJson (tally : Std.HashMap String (Nat × Nat)) : Json :=
  let rows := tally.toList.toArray.qsort (fun a b => a.2.2 > b.2.2 || (a.2.2 == b.2.2 && a.1 < b.1))
  Json.arr (rows.map fun (kind, steps, spent) =>
    Json.mkObj [("kind", toJson kind), ("steps", toJson steps), ("ticks", toJson spent)])

def countPlan : M Unit := do
  let s ← get
  if s.plans ≥ Limits.maxPlansPerTurn then evaluation "turn exceeds the plan capacity"
  set { s with plans := s.plans + 1 }

/-- Stage a write by the running object `id`, called by `caller`. The running object is
    always the first root of its own activity, so no earlier view is needed. -/
def addWrite (id caller : String) (step : Step) : M Unit := do
  let s ← get
  unless s.roots.any (·.1 == id) do evaluation "a write names an object that is not a root"
  if step.length > Limits.maxEditsPerWrite then evaluation "turn exceeds the edit capacity"
  let prior := (s.writes.lookup id).getD []
  if prior.length ≥ Limits.maxEditsPerWrite then evaluation "turn exceeds the edit capacity"
  let steps := prior ++ [({ caller, edits := step, method := s.method, via := s.via, argument := s.argument } : Written)]
  if !s.writes.any (·.1 == id) && s.writes.length ≥ Limits.maxWrites then
    evaluation "turn exceeds the write capacity"
  let writes := if s.writes.any (·.1 == id) then
      s.writes.map fun (k, es) => if k == id then (k, steps) else (k, es)
    else s.writes ++ [(id, steps)]
  set { s with writes }

/-- Record that the running object `id`, called by `caller`, reprograms (kind 1) or
    amends (kind 2) itself. False when the write set is full. -/
def ensureWrite (id caller : String) (kind : Nat) : M Bool := do
  let s ← get
  let change : Written := { caller, kind, edits := [], method := s.method, via := s.via, argument := s.argument }
  if s.writes.any (·.1 == id) then
    set { s with writes := s.writes.map fun (k, ws) => if k == id then (k, ws ++ [change]) else (k, ws) }
    return true
  if s.writes.length ≥ Limits.maxWrites then return false
  set { s with writes := s.writes ++ [(id, [change])] }
  return true

/-- The receipt a settled slot answers an await with. -/
def receiptData (entry : Json) : Data :=
  let identity := (entry.getObjVal? "identity").toOption.getD Json.null
  let text := fun (j : Json) (k : String) => ((j.getObjValAs? String k).toOption).getD ""
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let result : Data := match outcome.getObjValAs? String "tag" with
    | .ok "refused" => .variant "refused" (.record [("class", .label (text outcome "class")),
        ("root", .label (text outcome "object"))])
    | _ => .variant "admitted" (.record [])
  .record [("slot", .record [("principal", .label (text identity "principal")),
      ("intent", .label (text identity "intent"))]),
    ("height", .natural ((entry.getObjValAs? Nat "height").toOption.getD 0)), ("outcome", result)]

/-- The settled entry of an identity, if it has one (a suspension is not settled). -/
def settled (w : World) (principal intent : String) : Option Json :=
  match w.receipts[identityKey principal intent]? with
  | some i => let e := w.entries[i]!; if tagOf e == "suspended" then none else some e
  | none => none

/-- Compile an object's new sibling: `package` is a module of the creator's own sealed
    chain (a name), or the source of one more module over that chain. -/
def creationInputs (creator : Object) (package : String) : Except (String × String) Json := do
  if package.utf8ByteSize > Limits.maxPackageBytes then
    throw ("packageBytes", s!"package source exceeds {Limits.maxPackageBytes} bytes")
  let limits := (creator.inputs.getObjVal? "limits").toOption
  let finish := fun (fields : List (String × Json)) =>
    Json.mkObj (fields ++ [("entry", toJson "initial")] ++ (limits.map fun l => [("limits", l)]).getD [] ++
      ((creator.inputs.getObjVal? "library").toOption.map fun l => [("library", l)]).getD [])
  match creator.inputs.getObjVal? "modules" with
  | .ok (.arr modules) =>
    if package.startsWith "edition" then
      let named := modules.pop.push (Json.mkObj [("name", toJson "Created"), ("source", toJson package)])
      return finish [("modules", .arr named)]
    else
      match modules.findIdx? fun m => (m.getObjValAs? String "name").toOption == some package with
      | some i => return finish [("modules", .arr (modules.extract 0 (i + 1)))]
      | none => throw ("unknownPackage", s!"no module {package} in the creator's package")
  | _ =>
    if package.startsWith "edition" then return finish [("source", toJson package)]
    else throw ("unknownPackage", "the creator has no sealed modules to name")

/-- A seed (a `Data` payload) is a whole state, or a record naming some fields of it (the rest
    come from `initial()`). -/
def mergeSeed (initial seed : Data) (bounds : DataBounds) (ty : Ty) : Except String Data := do
  if seed.conformsUnder bounds ty then return seed
  match seed, initial with
  | .record given, .record base =>
    if given.any fun (k, _) => !base.any (·.1 == k) then throw "the seed names a field the state does not have"
    return .record (base.map fun (k, v) => (k, (given.lookup k).getD v))
  | _, _ => throw "the seed is not a record"

def buildCreated (w : World) (creator : Object) (package : String) (seed : Data) (lawArg principal : String)
    (height : Nat) : Except (String × String) (CreateRec × Built) := do
  let inputs ← creationInputs creator package
  let built ← (compileObject w inputs).mapError (("compile", ·))
  let packet ← (built.artifact.getObjVal? "packet").mapError (("compile", ·))
  let initial ← match Package.executeDataValues packet #[] (Json.mkObj []) with
    | .ok (.finished v _ _ _) => pure v
    | _ => throw ("compile", "initial() did not evaluate")
  let state ← (mergeSeed initial seed built.assumptions.bounds built.ty).mapError (("typeMismatch", ·))
  let lawText := if lawArg.startsWith "law " then some lawArg else none
  let (object, sources) ← (makeObject built inputs state none none principal height lawText).mapError
    (fun e => (if isAmendmentRefusal e then "law"
      else if e.endsWith "byte capacity" then "capacity" else "typeMismatch", e))
  return ({ object, sources, seed := dataJson state }, built)

/-- The subject a call or send of `method` on `callee` by the running object `self` acts
    with, and the argument it runs with: the running frame's own subject and the argument when
    `via` is empty; else the grantor of grant `via` if it stands for that callee and method, names
    the frame's subject or `self` as grantee, and has a use left, with the argument attenuated by
    the grant. A refusal is the clause: `noGrant`, `grantSpent`, `grantConflict`. -/
def grantFor (via self callee method : String) (argument : Data) : M (Except String (String × Data)) := do
  let s ← get
  if via.isEmpty then return .ok (s.subject, argument)
  match grantStands s.world via callee method with
  | none => return .error "noGrant"
  | some g =>
    if !(g.to == s.subject || g.to == self) || s.revokes.contains via then return .error "noGrant"
    if let some left := g.uses then
      if left ≤ ((s.spent.lookup via).getD 0) then return .error "grantSpent"
    match attenuate g argument with
    | .ok merged => return .ok (g.grantor, merged)
    | .error clause => return .error clause

/-- Spend one use of a limited grant (the commit checks the uses are still there). -/
def spendGrant (via : String) : M Unit := do
  if via.isEmpty then return
  let s ← get
  let some g := s.world.grants[via]? | return
  if g.uses.isNone then return
  let n := (s.spent.lookup via).getD 0
  set { s with spent := (s.spent.filter fun (x : String × Nat) => x.1 != via) ++ [(via, n + 1)] }

/-- The fields of a row type (`field` chain ending `emptyRow`) as `(name, member)`. -/
partial def rowFields (row : Json) : Option (List (String × Json)) :=
  match (row.getObjValAs? String "tag").toOption with
  | some "emptyRow" => some []
  | some "field" => do
    let name ← (row.getObjValAs? String "name").toOption
    let member ← (row.getObjVal? "member").toOption
    let rest ← rowFields ((row.getObjVal? "tail").toOption.getD Json.null)
    return (name, member) :: rest
  | _ => none

/-- A form field's kind for a member type: text, a natural, or a choice among the labels of a
    sum whose every payload is empty. Any other type has no form. -/
def formKind (member : Json) : Option Data :=
  match (member.getObjValAs? String "tag").toOption with
  | some "label" => some (.variant "text" (.record [("min", .natural 0), ("max", .natural Limits.formTextMax)]))
  | some "natural" => some (.variant "natural" (.record [("min", .natural 0), ("max", .natural Limits.formNaturalMax)]))
  | some "variant" => do
    let cases ← rowFields ((member.getObjVal? "row").toOption.getD Json.null)
    guard (!cases.isEmpty && cases.all fun (_, p) => (p.getObjValAs? String "tag").toOption == some "emptyRow")
    return .variant "choice" (.record [("options", listData (cases.map fun (n, _) => Data.label n))])
  | _ => none

/-- The actions of an object as forms, from its artifact's method table: every method a turn can
    run (it takes a context) whose input is a record of form-expressible fields. -/
def methodForms (id : String) (methods : Json) : List Data :=
  ((methods.getArr?.toOption).getD #[]).toList.filterMap fun m => do
    guard ((m.getObjValAs? Bool "context").toOption == some true)
    let name ← (m.getObjValAs? String "name").toOption
    let fields ← rowFields ((m.getObjVal? "input").toOption.getD Json.null)
    let kinds ← fields.mapM fun (n, member) => (formKind member).map fun k => Data.record [("name", .label n), ("kind", k)]
    return .record [("card", .label id), ("action", .label name), ("fields", listData kinds)]

/-- Does the object's method table list `name`? -/
def hasMethod (o : Object) (name : String) : Bool :=
  ((o.methods.getArr?.toOption).getD #[]).any fun m => (m.getObjValAs? String "name").toOption == some name

/-- The Context a card is rendered for: the reader (`principal`), the card's object, the asking
    object (`caller`, "" for `world-card`), and the turn's intent and height. -/
def cardContext (w : World) (id reader caller intent : String) (height : Nat) (method : String) : Data :=
  contextData id reader (handleOf w reader) caller intent height "card" method

/-- An object's card as `context`'s reader sees it, run on its committed state under this turn's
    ticks: `renderFor(state, context)` when the package has it, else `render`, which may take
    `(state, context)` or the state alone. `noCard` when it has neither, `render` when it fails
    or runs out. -/
def renderCard (o : Object) (context : String → Data) : M (Except String Data) := do
  let name := if hasMethod o "renderFor" then "renderFor" else "render"
  let compiled ← tryCatch (some <$> compiledMethod o name) fun _ => pure none
  let some c := compiled | return .error "noCard"
  let arguments := match c.type with
    | .arrow _ _ _ (.arrow _ _ _ _) => #[o.state, context name]
    | _ => #[o.state]
  let entry ← entryOf c
  let st ← get
  match Package.executeDataEntry entry arguments (st.limits.setObjVal! "ticks" (toJson (toString st.ticks))) with
  | .ok (.finished value _ _ usage) => spend (usage.ticksUsed + usage.conversionNodes); return .ok value
  | .ok (.refused _ usage) => spend (usage.ticksUsed + usage.conversionNodes); return .error "render"
  | .error _ => return .error "render"

/-- The kernel's refusal of an argument that does not conform to the entry's input type. -/
def argumentRefusal : String := "turn refused: argument does not conform to its type"

/-- Does `argument` fit the input of a compiled method? A method without an input takes any. At
    `Data` any well-formed value fits; at a data type the value must conform under the packet's
    bounds (the check the kernel's `prepareStart` makes). -/
def argumentFits (compiled : Compiled) (argument : Data) : Bool :=
  match compiled.type with
  | .arrow _ _ _ (.arrow _ _ domain (.arrow _ _ _ _)) =>
    if domain == .data then argument.wellFormed
    else !(domain.isDataUnder compiled.bounds [] Ty.dataFuel []) || argument.conformsUnder compiled.bounds domain
  | _ => true

/-- A kernel refusal at the start or resumption of an activity: an argument that does not
    conform is the journaled class `typeMismatch`, anything else an `evaluation`. -/
def kernelRefusal {α : Type} (r : Except String α) : M α :=
  match r with
  | .ok a => pure a
  | .error e => if e.startsWith argumentRefusal then throw (.refused "typeMismatch" e) else throw (.evaluation e)

/-- Offer a Plan the frame `self` yielded to handler object `handler`: its pure
    `handle(state, plan[, context]) -> pass {} | answer {response}`. `none` is pass (also when the
    plan does not conform to the handler's input: a handler takes the plans its type names); an
    answer must conform to the yielding frame's response type. The handler is a root. -/
def handleWith (handler self : String) (plan : Data) (bounds : DataBounds) (responseType : Ty) : M (Option Data) := do
  let s ← get
  let some obj := s.world.objects[handler]? | evaluation s!"handler {handler} vanished"
  recordRoot handler obj.version
  let c ← compiledMethod obj "handle"
  let entry ← entryOf c
  let context := contextData handler s.subject (handleOf s.world s.subject) self s.intent s.world.height "handle" ""
  let (domain, arguments) := match c.type with
    | .arrow _ _ _ (.arrow _ _ d (.arrow _ _ _ _)) => (d, [obj.state, plan, context])
    | .arrow _ _ _ (.arrow _ _ d _) => (d, [obj.state, plan])
    | _ => (.emptyRow, [obj.state, plan])
  -- A plan the handler's input does not name passes.
  unless plan.conformsUnder c.bounds domain do return none
  let (result, used) := runPure entry arguments (← get).ticks
  spend used
  match result with
  | .ok (.variant "answer" (.record f)) =>
    let some response := f.lookup "response" | evaluation "a handler answer carries no response"
    unless response.conformsUnder bounds responseType do
      evaluation "the handler's answer does not conform to the response type"
    return some response
  | .ok _ => return none
  | .error "budget" => throw (.budget "ticks")
  | .error e => evaluation s!"handle refused: {e}"

mutual
/-- Run `method` of object `id` against its committed state; its result is returned. -/
partial def runMethod (depth : Nat) (id method : String) (argument : Data) (caller : String)
    (subject : String) (via : String := "") : M Data := do
  let outer ← get
  set { outer with subject, method, via, argument }
  let result ← runFrame depth id method argument caller
  modify fun s => { s with subject := outer.subject, method := outer.method, via := outer.via, argument := outer.argument }
  return result

/-- The body of `runMethod`, inside the frame it set. -/
partial def runFrame (depth : Nat) (id method : String) (argument : Data) (caller : String) : M Data := do
  let s ← get
  let some obj := s.world.objects[id]? | evaluation s!"unknown object {id}"
  recordRoot id obj.version
  let compiled ← compiledMethod obj method
  let context := contextData id s.subject (handleOf s.world s.subject) caller s.intent s.world.height
    (if depth == 0 then "request" else "call") method
  let (arguments, r) ← match compiled.type with
    | .arrow _ _ _ (.arrow _ _ _ (.arrow _ _ _ r)) => pure ([obj.state, argument, context], r)
    | .arrow _ _ _ (.arrow _ _ _ r) => pure ([obj.state, context], r)
    | _ => throw (.request s!"method {method} must take (state, [input,] context)")
  unless argumentFits compiled argument do throw (.refused "typeMismatch" argumentRefusal)
  match r with
  | .computation .. =>
    let b ← budgetsNow
    let binding := Delvetalk.Turn.Binding.make id s.principal s.intent (← get).roots
    let entry ← entryOf compiled
    let started ← kernelRefusal (Delvetalk.Turn.startEntry entry arguments binding b)
    noteProfile fun _ => (Delvetalk.Turn.prepareStartEntry entry arguments |>.map fun (applied, _) =>
      Delvetalk.Profile.profile ⟨b.heap, b.stack⟩ b.bytes b.ticks (Minidregg.Theory.ObjectiveBendDemandMachine.initial applied.source.term))
    drive depth id caller compiled binding started 0
  | _ =>
    unless r.isDataUnder compiled.bounds compiled.rigid Ty.dataFuel [] do throw (.request s!"method {method} must be pure data or an activity")
    let st ← get
    let lim := st.limits.setObjVal! "ticks" (toJson (toString st.ticks))
    match Package.executeDataValues compiled.packet arguments.toArray lim with
    | .error e => evaluation e
    | .ok (.refused failure usage) =>
      spend (usage.ticksUsed + usage.conversionNodes)
      evaluation s!"turn refused: {failure}"
    | .ok (.finished value _ _ usage) =>
      spend (usage.ticksUsed + usage.conversionNodes)
      let .record fields := value | evaluation "a pure method must return the state record"
      addWrite id caller (fields.map fun (k, v) => (⟨k, .set v⟩ : Edit))
      return value

partial def drive (depth : Nat) (self caller : String) (compiled : Compiled) (binding : Delvetalk.Turn.Binding)
    (outcome : Delvetalk.Turn.Outcome) (_n : Nat) : M Data := do
  match outcome with
  | .finished value _ used => spend used; return value
  | .exhausted resource used =>
    spend used
    throw (.budget resource)
  | .yielded plan _ responseType checkpoint used =>
    spend used
    countPlan
    let response ← match plan with
      | .variant "await" (.record f) | .variant "awaitUntil" (.record f) => awaitPlan depth self compiled.bounds f responseType checkpoint
      | .variant "interpret" (.record f) => interpretPlan depth self compiled.bounds f responseType checkpoint
      | _ => do
        -- A frame run under a handler offers each Plan to it first.
        match (← get).handlers.lookup depth with
        | some handler => match ← handleWith handler self plan compiled.bounds responseType with
          | some response => pure response
          | none => answer depth self caller compiled.bounds plan responseType
        | none => answer depth self caller compiled.bounds plan responseType
    let b ← budgetsNow
    let entry ← entryOf compiled
    let next ← liftEval (Delvetalk.Turn.resumeEntry entry checkpoint binding response b)
    noteProfile fun _ => (Delvetalk.Turn.prepareResumeEntry entry checkpoint binding response |>.map fun (_, _, _, _, st, resumed) =>
      Delvetalk.Profile.profile (Minidregg.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ st) b.bytes b.ticks resumed)
    drive depth self caller compiled binding next 0

/-- `await {slot, patience}`: answered at once if the slot is settled or hopeless;
    otherwise the turn suspends (only at the top of a turn, never inside a call). -/
partial def awaitPlan (depth : Nat) (self : String) (bounds : DataBounds) (f : List (String × Data))
    (responseType : Ty) (checkpoint : Delvetalk.Turn.Checkpoint) : M Data := do
  let some (.record slot) := f.lookup "slot" | evaluation "malformed await plan"
  let some sp := (slot.lookup "principal").bind labelOf | evaluation "malformed await plan"
  let some si := (slot.lookup "intent").bind labelOf | evaluation "malformed await plan"
  let s ← get
  -- `until` is an absolute clock height; `patience` is relative to the clock now.
  let patience ← match f.lookup "until", f.lookup "patience" with
    | some (.natural height), _ => pure (height - s.world.clock)
    | none, some (.natural patience) => pure patience
    | _, _ => evaluation "malformed await plan"
  let key := identityKey sp si
  if (sp == s.principal && si == s.intent) || s.awaited.contains key then
    respond bounds responseType "broken" [emptyRecord]
  else if s.awaits ≥ Limits.awaitsPerTurn then evaluation "turn exceeds the await capacity"
  else
    set { s with awaited := s.awaited ++ [key], awaits := s.awaits + 1 }
    match settled s.world sp si with
    | some entry => respond bounds responseType "reply" [.record [("receipt", receiptData entry)]]
    | none =>
      if patience == 0 then respond bounds responseType "timedOut" [emptyRecord]
      else if patience > Limits.maxPatience then evaluation "await patience exceeds its capacity"
      else
        mayWait depth self checkpoint
        throw (.suspend sp si patience checkpoint)

/-- The capacities every suspension is held to; only the top of a turn may wait. Awaits and
    interpretations waiting on one object are counted apart (`pendingActivitiesPerObject`,
    `pendingInterpretationsPerObject`): every prose reply to a card waits for the model, and
    a batch of replies must not exhaust the slots awaits need. A full count refuses the turn
    `capacity`, naming the limit. -/
partial def mayWait (depth : Nat) (self : String) (checkpoint : Delvetalk.Turn.Checkpoint)
    (interpreting : Bool := false) : M Unit := do
  let s ← get
  let waiting := s.world.suspended.filter fun e =>
    let outcome := (e.getObjVal? "outcome").toOption
    (outcome.bind (·.getObjVal? "activity" |>.toOption) |>.bind (·.getObjValAs? String "object" |>.toOption)) == some self &&
      (outcome.bind (·.getObjVal? "interpretation" |>.toOption)).isSome == interpreting
  let (cap, name) := if interpreting then (Limits.pendingInterpretationsPerObject, "pendingInterpretationsPerObject")
    else (Limits.pendingActivitiesPerObject, "pendingActivitiesPerObject")
  if depth != 0 then evaluation "a wait inside a call is not supported"
  else if waiting.size ≥ cap then throw (.refused "capacity" name)
  else if s.world.suspended.size ≥ Limits.maxSuspended then throw (.refused "capacity" "maxSuspended")
  else if (Delvetalk.Turn.tokensJson checkpoint.tokens).compress.utf8ByteSize > Limits.maxCheckpointBytes then
    evaluation "checkpoint exceeds its byte capacity"

/-- `interpret {utterance, offers, policy}`: the turn waits for a model's reply, which the
    transport fetches (`world-interpretations`) and settles (`world-interpretation`). The
    policy object must be readable by the turn's principal, else the Plan is answered `denied`. -/
partial def interpretPlan (depth : Nat) (self : String) (bounds : DataBounds) (f : List (String × Data))
    (responseType : Ty) (checkpoint : Delvetalk.Turn.Checkpoint) : M Data := do
  let some (.label utterance) := f.lookup "utterance" | evaluation "malformed interpret plan"
  let some offers := f.lookup "offers" | evaluation "malformed interpret plan"
  let some policy := (f.lookup "policy").bind referenceId | evaluation "malformed interpret plan"
  let s ← get
  match s.world.objects[policy]? with
  | none => respond bounds responseType "denied" [emptyRecord]
  | some o =>
    if !o.read.permits s.subject then respond bounds responseType "denied" [emptyRecord]
    else if utterance.utf8ByteSize > Limits.maxUtteranceBytes then evaluation "utterance exceeds its byte capacity"
    else if (dataJson offers).compress.utf8ByteSize > Limits.maxOffersBytes then
      evaluation "offers exceed their byte capacity"
    else if s.awaits ≥ Limits.awaitsPerTurn then evaluation "turn exceeds the await capacity"
    else
      mayWait depth self checkpoint (interpreting := true)
      let id := Journal.bodyHash (Json.arr #[toJson s.principal, toJson s.intent, toJson s.awaits])
      set { s with awaits := s.awaits + 1 }
      throw (.suspend interpretationPrincipal id Limits.interpretationPatience checkpoint
        (some (Json.mkObj [("id", toJson id), ("object", toJson self), ("policy", toJson policy),
          ("utterance", toJson utterance), ("offers", dataJson offers)])))

partial def answer (depth : Nat) (self caller : String) (bounds : DataBounds) (plan : Data) (responseType : Ty) : M Data := do
  match plan with
  | .variant "view" (.record f) =>
    match (f.lookup "object").bind referenceId with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some id =>
      match (← get).world.objects[id]? with
      | none => respond bounds responseType "denied" [emptyRecord]
      | some o =>
        if !o.read.permits (← get).subject then respond bounds responseType "denied" [emptyRecord] else
        recordRoot id o.version
        respond bounds responseType "viewed" [.record [("version", .natural o.version), ("state", o.state)]]
  | .variant "write" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed write plan"
    let some step := (f.lookup "edits").bind parseStep | evaluation "malformed write plan"
    -- A write changes the running object and nothing else; other objects change when called.
    match referenceId target with
    | some id =>
      if id != self then refusedWith bounds responseType "notSelf"
      else
        addWrite self caller step
        respond bounds responseType "written" [emptyRecord]
    | none => refusedWith bounds responseType "notSelf"
  | .variant "call" (.record f) | .variant "callVia" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed call plan"
    let some method := (f.lookup "method").bind labelOf | evaluation "malformed call plan"
    let some argument := f.lookup "argument" | evaluation "malformed call plan"
    let via := ((f.lookup "via").bind labelOf).getD ""
    match referenceId target with
    | none => refusedWith bounds responseType "unknownObject"
    | some id =>
      if !(← get).world.objects.contains id then refusedWith bounds responseType "unknownObject"
      else if depth + 1 > Limits.maxCallDepth then evaluation "call depth exceeded"
      else match ← grantFor via self id method argument with
        | .error clause => refusedWith bounds responseType clause
        | .ok (subject, argument) =>
          let some calleeObj := (← get).world.objects[id]? | refusedWith bounds responseType "unknownObject"
          let callee ← compiledMethod calleeObj method
          if !argumentFits callee argument then refusedWith bounds responseType "typeMismatch" else
          spendGrant via
          let result ← runMethod (depth + 1) id method argument self subject via
          respond bounds responseType "returned" [.record [("result", result)]]
  | .variant "run" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed run plan"
    let some method := (f.lookup "method").bind labelOf | evaluation "malformed run plan"
    let some argument := f.lookup "argument" | evaluation "malformed run plan"
    let some handler := (f.lookup "handler").bind referenceId | refusedWith bounds responseType "handler"
    let s ← get
    match referenceId target >>= fun id => (s.world.objects[id]?).map (id, ·) with
    | none => refusedWith bounds responseType "unknownObject"
    | some (id, calleeObj) =>
      match s.world.objects[handler]? with
      | none => refusedWith bounds responseType "handler"
      | some h =>
        if !h.read.permits s.subject then refusedWith bounds responseType "handler"
        else if depth + 1 > Limits.maxCallDepth then evaluation "call depth exceeded"
        else
          let callee ← compiledMethod calleeObj method
          if !argumentFits callee argument then refusedWith bounds responseType "typeMismatch" else
          modify fun s => { s with handlers := (depth + 1, handler) :: s.handlers }
          let result ← runMethod (depth + 1) id method argument self s.subject
          modify fun s => { s with handlers := s.handlers.drop 1 }
          respond bounds responseType "returned" [.record [("result", result)]]
  | .variant "judge" (.record f) =>
    -- The verdict the turn would get if it ended now with this write added, committing nothing.
    let some step := (f.lookup "edits").bind parseStep | evaluation "malformed judge plan"
    let s ← get
    let staged := ({ caller, edits := step, method := s.method, via := s.via, argument := s.argument } : Written)
    let writes := if s.writes.any (·.1 == self) then s.writes.map fun (k, ws) => if k == self then (k, ws ++ [staged]) else (k, ws)
      else s.writes ++ [(self, [staged])]
    let w := warmLaws s.world (writes.map (·.1))
    modify fun s => { s with world := { s.world with compiled := w.compiled } }
    let p : Proposal := { principal := s.principal, intent := s.intent, roots := s.roots, writes,
                          programs := s.programs, layered := s.layered, laws := s.laws, absent := s.absent,
                          creates := s.creates, grants := s.grants, revokes := s.revokes, spent := s.spent,
                          turn := w.height + 1 }
    let p := withLawReads w p
    let (admitted, clause) := match judge w (w.height + 1) p with
      | .ok _ => (true, "")
      | .error r => (false, r.clause.getD r.cls)
    respond bounds responseType "judged" [.record [("admitted", .boolean admitted), ("clause", .label clause)]]
  | .variant "reprogram" (.record f) | .variant "extend" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed reprogram plan"
    let some source := (f.lookup "package").bind labelOf | evaluation "malformed reprogram plan"
    let some migration := (f.lookup "migration").bind labelOf | evaluation "malformed reprogram plan"
    -- `extend {…}`, or `reprogram {…, mode: "extend"}`: a layer over the current code.
    let extend := match plan with
      | .variant "extend" _ => true
      | _ => ((f.lookup "mode").bind labelOf) == some "extend"
    let some id := referenceId target | refusedWith bounds responseType "foreignWorld"
    let s ← get
    let some o := s.world.objects[id]? | refusedWith bounds responseType "unknownObject"
    -- Reprogramming another object is a change of it proposed by the running object: it reads
    -- the target, and the target's own law judges it with request.caller = the proposer.
    let proposer := if id == self then caller else self
    if s.programs.any (·.1 == id) then refusedWith bounds responseType "duplicate"
    else match programFor s.world o source migration extend with
      | .error (clause, _) => refusedWith bounds responseType clause
      | .ok prog =>
        recordRoot id o.version
        if !(← ensureWrite id proposer 1) then refusedWith bounds responseType "capacity"
        else
          modify fun s => { s with world := cacheProgram s.world o source migration prog extend,
                                   programs := s.programs ++ [(id, (source, migration))],
                                   layered := if extend then s.layered ++ [id] else s.layered }
          respond bounds responseType "reprogrammed" [.record [("pin", .label prog.pin)]]
  | .variant "amend" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed amend plan"
    let some text := (f.lookup "law").bind labelOf | evaluation "malformed amend plan"
    let some id := referenceId target | refusedWith bounds responseType "foreignWorld"
    let s ← get
    let some o := s.world.objects[id]? | refusedWith bounds responseType "unknownObject"
    let proposer := if id == self then caller else self
    if s.laws.any (·.1 == id) then refusedWith bounds responseType "duplicate"
    else match parseLawText text with
      | .error _ => refusedWith bounds responseType "law syntax"
      | .ok _ =>
        recordRoot id o.version
        if !(← ensureWrite id proposer 2) then refusedWith bounds responseType "capacity"
        else
          modify fun s => { s with laws := s.laws ++ [(id, text)] }
          respond bounds responseType "amended" [emptyRecord]
  | .variant "inspect" (.record f) =>
    let s ← get
    match (f.lookup "object").bind referenceId >>= fun id => (s.world.objects[id]?) with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some o =>
      if !o.read.permits s.subject then respond bounds responseType "denied" [emptyRecord]
      else
        let shown := [("pin", Data.label o.pin), ("law", .label o.lawText), ("source", .label (entrySource o))]
        let id := ((f.lookup "object").bind referenceId).getD ""
        respond bounds responseType "inspected"
          [.record (shown ++ [("methods", listData (methodForms id o.methods))]), .record shown]
  | .variant "objects" (.record f) =>
    let some pfx := (f.lookup "prefix").bind labelOf | evaluation "malformed objects plan"
    let some after := (f.lookup "after").bind labelOf | evaluation "malformed objects plan"
    let s ← get
    let (ids, more) := listIds s.world s.subject pfx after
    respond bounds responseType "listed" [.record [("ids", listData (ids.map Data.label)), ("more", .boolean more)]]
  | .variant "card" (.record f) =>
    let s ← get
    match (f.lookup "object").bind referenceId >>= fun id => (s.world.objects[id]?).map (id, ·) with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some (id, o) =>
      if !o.read.permits s.subject then respond bounds responseType "denied" [emptyRecord] else
      recordRoot id o.version
      let reader := cardContext s.world id s.subject self s.intent s.world.height
      match ← renderCard o reader with
      | .ok document => respond bounds responseType "carded" [.record [("document", document)]]
      | .error clause => refusedWith bounds responseType clause
  | .variant "check" (.record f) =>
    let some (.label source) := f.lookup "package" | evaluation "malformed check plan"
    let s ← get
    if s.checks ≥ Limits.checksPerTurn then evaluation "turn exceeds the check capacity"
    set { s with checks := s.checks + 1 }
    respond bounds responseType "checked"
      [.record [("diagnostics", listData ((checkSource s.world source).map Data.label))]]
  | .variant "create" (.record f) | .variant "createUnder" (.record f) =>
    let some package := (f.lookup "package").bind labelOf | evaluation "malformed create plan"
    -- `createUnder` names the child's supervisor; it must be an object now.
    let supervisor := ((f.lookup "supervisor").bind referenceId).getD ""
    let some seed := f.lookup "seed" | evaluation "malformed create plan"
    let lawArg := ((f.lookup "law").bind labelOf).getD ""
    let some target := f.lookup "requireAbsent" | evaluation "malformed create plan"
    let some id := referenceId target | refusedWith bounds responseType "foreignWorld"
    let s ← get
    let note := fun (s : TurnState) => { s with absent := if s.absent.contains id then s.absent else s.absent ++ [id] }
    if id.isEmpty || id == "self" || ownCards.contains id || id.utf8ByteSize > Limits.maxObjectIdBytes then
      refusedWith bounds responseType "objectId"
    else if s.world.objects.contains id || s.creates.any (·.1 == id) then
      -- The reply says so now; the turn will be refused at its commit, naming the root.
      set { note s with violation := s.violation.orElse fun _ => some id }
      refusedWith bounds responseType "requiredAbsence"
    else if s.creates.length ≥ Limits.createsPerTurn || s.absent.length ≥ Limits.maxRoots then
      refusedWith bounds responseType "capacity"
    else if !supervisor.isEmpty && !s.world.objects.contains supervisor && supervisor != self then
      refusedWith bounds responseType "supervisor"
    else
      let some creator := s.world.objects[self]? | evaluation "the creating object vanished"
      match buildCreated s.world creator package seed lawArg s.principal (s.world.height + 1) with
      | .error (clause, _) => refusedWith bounds responseType clause
      | .ok (made, built) =>
        let made := { made with object := { made.object with supervisor } }
        set { note s with creates := s.creates ++ [(id, made)], world := cacheBuild s.world made.object.inputs built }
        respond bounds responseType "created" [.record [("object", .record [("world", .label ""), ("object", .label id)])]]
  | .variant "send" (.record f) | .variant "sendVia" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed send plan"
    let some method := (f.lookup "method").bind labelOf | evaluation "malformed send plan"
    let some argument := f.lookup "argument" | evaluation "malformed send plan"
    let via := ((f.lookup "via").bind labelOf).getD ""
    match referenceId target with
    | none => refusedWith bounds responseType "foreignWorld"
    | some id =>
      match ← grantFor via self id method argument with
      | .error clause => refusedWith bounds responseType clause
      | .ok (subject, argument) =>
      spendGrant via
      let s ← get
      if s.sends.length ≥ Limits.sendsPerTurn then evaluation "turn exceeds the send capacity"
      if s.world.pending.size + s.sends.length ≥ Limits.maxPending then
        evaluation "world exceeds the pending delivery capacity"
      let delivery := deliveryId s.principal s.intent s.sends.length
      let staged : Send := { to := id, method, argument, sender := self, via, grantor := if via.isEmpty then "" else subject }
      set { s with sends := s.sends ++ [staged] }
      respond bounds responseType "delivery" [.record [("id", .label delivery)]]
  | .variant "grant" (.record f) | .variant "grantWith" (.record f) =>
    let some to := (f.lookup "to").bind labelOf | evaluation "malformed grant plan"
    let some method := (f.lookup "method").bind labelOf | evaluation "malformed grant plan"
    let some (.natural expires) := f.lookup "until" | evaluation "malformed grant plan"
    -- `grantWith` fixes part of the argument and limits the uses (at least one).
    let fixed := (f.lookup "fixed").map dataJson
    let uses ← match f.lookup "uses" with
      | some (.natural n) => pure (some n)
      | some _ => evaluation "malformed grant plan"
      | none => pure none
    let s ← get
    -- Only the object a principal asked directly may speak for that principal: not a callee,
    -- not a delivered turn, not a frame already running under a grant.
    if depth != 0 || !s.direct || !s.via.isEmpty then refusedWith bounds responseType "notDirect"
    else match (f.lookup "object").bind referenceId with
    | none => refusedWith bounds responseType "unknownObject"
    | some object =>
      if !s.world.objects.contains object then refusedWith bounds responseType "unknownObject"
      else if to.isEmpty || to.utf8ByteSize > Limits.maxPrincipalBytes then refusedWith bounds responseType "grantee"
      else if s.grants.length ≥ Limits.grantsPerTurn then refusedWith bounds responseType "capacity"
      else if uses == some 0 then refusedWith bounds responseType "uses"
      else if fixed.any (·.compress.utf8ByteSize > Limits.maxSeedBytes) then refusedWith bounds responseType "capacity"
      else
        let id := grantId s.principal s.intent s.grants.length
        set { s with grants := s.grants ++ [({ id, grantor := s.principal, holder := self, to, object, method, expires,
                                                fixed, uses } : Grant)] }
        respond bounds responseType "granted" [.record [("id", .label id)]]
  | .variant "revoke" (.record f) =>
    let some id := (f.lookup "id").bind labelOf | evaluation "malformed revoke plan"
    let s ← get
    match s.world.grants[id]? with
    | none => refusedWith bounds responseType "unknownGrant"
    | some g =>
      if !(g.holder == self || (g.grantor == s.subject && s.via.isEmpty)) then refusedWith bounds responseType "notGrantor"
      else if g.revoked || s.revokes.contains id then respond bounds responseType "revoked" [emptyRecord]
      else
        modify fun s => { s with revokes := s.revokes ++ [id] }
        respond bounds responseType "revoked" [emptyRecord]
  | .variant "offer" (.record f) =>
    let some document := f.lookup "document" | evaluation "malformed offer plan"
    let text ← liftEval (Delvetalk.Document.render document)
    let s ← get
    -- `to` is a principal; "" is the acting principal (the frame's subject).
    let to := match (f.lookup "to").bind labelOf with
      | some t => if t.isEmpty then s.subject else t
      | none => s.subject
    if to.utf8ByteSize > Limits.maxPrincipalBytes then evaluation "offer addressee exceeds its byte capacity"
    if s.offers.length ≥ Delvetalk.Document.maxOffersPerTurn
        || (s.offers.foldl (· + ·.2.utf8ByteSize) text.utf8ByteSize) > Delvetalk.Document.maxOutputBytes then
      evaluation "turn exceeds the offer capacity"
    set { s with offers := s.offers ++ [(to, text)] }
    respond bounds responseType "offered" [emptyRecord]
  | .variant "publish" (.record f) =>
    let some page := (f.lookup "page").bind labelOf | evaluation "malformed publish plan"
    let some part := (f.lookup "section").bind labelOf | evaluation "malformed publish plan"
    let some body := (f.lookup "body").bind labelOf | evaluation "malformed publish plan"
    let s ← get
    -- The page belongs to the object: its title is the one given, or the object's id.
    let title := if page.isEmpty then self else page
    if title.utf8ByteSize > Limits.maxTitleBytes || part.utf8ByteSize > Limits.maxTitleBytes
        || (title.any (· == '\n')) || (part.any (· == '\n')) then
      refusedWith bounds responseType "title"
    else if body.utf8ByteSize > Delvetalk.Document.maxOutputBytes then refusedWith bounds responseType "capacity"
    else if s.publishes.length ≥ Limits.publishesPerTurn then refusedWith bounds responseType "capacity"
    else
      let id := Journal.bodyHash (Json.arr #[toJson "publish", toJson s.principal, toJson s.intent, toJson s.publishes.length])
      -- agentwiki: a page is `wiki: Title` then its sections; a section edit is `edit: Title › Section`.
      let text := if part.isEmpty then s!"wiki: {title}\n\n{body}" else s!"edit: {title} › {part}\n\n{body}"
      set { s with publishes := s.publishes ++ [Json.mkObj [("id", toJson id), ("object", toJson self),
        ("page", toJson title), ("section", toJson part), ("text", toJson text)]] }
      respond bounds responseType "published" [.record [("post", .label id)]]
  | .variant label _ => evaluation s!"plan not supported: {label}"
  | _ => evaluation "plan is not a variant"
end

def offersJson (offers : List (String × String)) : Json :=
  Json.arr (offers.toArray.map fun (to, text) => Json.mkObj [("to", toJson to), ("text", toJson text)])

/-- Lift `result`, `ticksUsed` and, for a suspension, `slot` and `deadline` to the reply, and the
    offers the entry retains for the turn's own principal (others are read with `world-offers`). -/
def turnReply (w : World) (r : Json) : Json :=
  match r.getObjVal? "receipt" with
  | .error _ => r
  | .ok entry =>
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let extra := ["result", "ticksUsed"].filterMap (fun k => (entry.getObjVal? k).toOption.map (k, ·)) ++
      ["slot", "deadline"].filterMap (fun k => (outcome.getObjVal? k).toOption.map (k, ·))
    let principal := ((entry.getObjVal? "identity").toOption.bind fun i => (i.getObjValAs? String "principal").toOption).getD ""
    let mine := (((entry.getObjVal? "offers").toOption.bind (·.getArr?.toOption)).getD #[]).filterMap fun o =>
      match o.getObjValAs? String "to", o.getObjValAs? String "text" with
      | .ok to, .ok text => if to == principal then some (Json.mkObj [("principal", toJson to), ("text", toJson text)]) else none
      | _, _ => none
    Json.mkObj ([("status", (r.getObjVal? "status").toOption.getD Json.null), ("receipt", entry)] ++ extra ++
      (if mine.isEmpty then [] else [("offers", Json.arr mine)]) ++
      -- What a refusal may say in public, for transport to draft from.
      (if tagOf entry == "refused" then [("public", publicRefusal w "" entry)] else []))

/-- Retry rule for turns: the identity is bound to the whole turn request. -/
def retainedTurn (w : World) (r : TurnRequest) : Option Json :=
  match w.receipts[identityKey r.principal r.intent]? with
  | none => none
  | some index =>
    let entry := w.entries[index]!
    let same := (entry.getObjValAs? String "turnRequest").toOption == some r.digest
    if isTransient entry then none
    else if same then some (turnReply w (reply entry))
    else some (duplicate r.principal r.intent entry)

/-- What a turn knows about how it began: the ledger it runs under and, for a
    delivery, the id and the sender's identity. -/
structure TurnMeta where
  /-- The object whose send this turn delivers; the delivered method's `caller`. -/
  caller : String := ""
  /-- The grant a delivered send was made under. -/
  via : String := ""
  ledger : Option Ledger := none
  delivery : Option (String × Json) := none

def ledgerJson (l : Ledger) : Json := l.json

/-- The sends of an admitted turn, each with the ledger it inherits: depth - 1,
    work - the ticks this turn used, storage - the bytes its writes added. -/
def sendsJson (w : World) (principal intent : String) (ledger : Ledger) (used : Nat)
    (sends : List Send) (updates : List (String × Object)) : List (String × Json) :=
  if sends.isEmpty then [] else
  let added := updates.foldl (fun n (id, o) =>
    let before := ((w.objects[id]?).map fun p => (dataJson p.state).compress.utf8ByteSize).getD 0
    n + ((dataJson o.state).compress.utf8ByteSize - before)) 0
  let child : Ledger := ⟨ledger.depth - 1, ledger.work - used, ledger.storage - added⟩
  [("sends", Json.arr (sends.zipIdx.toArray.map fun (x, i) => Json.mkObj
    ([("id", toJson (deliveryId principal intent i)), ("to", toJson x.to), ("method", toJson x.method),
     ("argument", dataJson x.argument), ("sender", toJson x.sender), ("ledger", child.json)] ++
     (if x.via.isEmpty then [] else [("via", toJson x.via), ("principal", toJson x.grantor)]))))]

/-- What a turn segment carries into its end: who it is, how it began, what it has spent. -/
structure Ctx where
  principal : String
  intent : String
  object : String
  method : String
  argument : Data
  /-- Digest of the original request; binds the identity for retries. -/
  digest : String
  ledger : Ledger
  delivery : Option (String × Json)
  /-- Hash of the suspension this segment continues. -/
  resumes : Option String := none
  usedBefore : Nat := 0
  ticksStart : Nat
  /-- The calling object of the activity's top method (empty for a direct turn). -/
  caller : String := ""
  /-- The grant a delivered send was made under ("" for none). -/
  via : String := ""
  /-- This segment continues an activity whose await ran past its deadline. -/
  timedOut : Bool := false


def sendJson (s : Send) : Json :=
  Json.mkObj ([("to", toJson s.to), ("method", toJson s.method), ("argument", dataJson s.argument),
    ("sender", toJson s.sender)] ++
    (if s.via.isEmpty then [] else [("via", toJson s.via), ("grantor", toJson s.grantor)]))

def sendOfJson (j : Json) : Except String Send := do
  return { to := ← j.getObjValAs? String "to", method := ← j.getObjValAs? String "method",
           argument := ← decodeData Limits.dataDepth (← j.getObjVal? "argument"),
           sender := ← j.getObjValAs? String "sender",
           via := (j.getObjValAs? String "via").toOption.getD "",
           grantor := (j.getObjValAs? String "grantor").toOption.getD "" }

def entryBase (ctx : Ctx) (used : Nat) : List (String × Json) :=
  [("turnRequest", toJson ctx.digest), ("ticksUsed", toJson used), ("ledger", ctx.ledger.json)] ++
    (ctx.delivery.map fun (id, sender) => [("delivery", Json.mkObj ([("id", toJson id), ("from", sender)] ++
      (if ctx.via.isEmpty then [] else [("via", toJson ctx.via)])))]).getD [] ++
    (ctx.resumes.map fun h => [("resumes", toJson h)]).getD []

/-- End a segment of a turn: commit it, refuse it, or journal its suspension. -/
def finishTurn (w : World) (ctx : Ctx) (result : Except Abort Data) (st : TurnState) :
    Except String (World × Json) := do
  let w := { w with compiled := st.world.compiled, programs := st.world.programs, builds := st.world.builds }
  let used := ctx.usedBefore + (ctx.ticksStart - st.ticks)
  let proposal : Proposal :=
    { principal := ctx.principal
      intent := ctx.intent
      roots := st.roots
      rootCids := st.rootCids
      writes := st.writes
      turn := w.height + 1
      programs := st.programs
      layered := st.layered
      laws := st.laws
      absent := st.absent
      creates := st.creates
      grants := st.grants
      revokes := st.revokes
      spent := st.spent }
  let base := entryBase ctx used
  -- An activity of a supervised object that ends broken, out of budget, or after its await
  -- timed out tells the supervisor (`endedField`), under the ledger it ran with.
  let ended := fun (how : String) (h : Nat) (out : Json) =>
    endedField w ctx.object ctx.principal ctx.intent how ctx.ledger used h out
  let endedIfLate := fun (h : Nat) (out : Json) => if ctx.timedOut then ended "timedOut" h out else []
  let refuse := fun (reason : String) =>
    let cls := if st.roots.isEmpty && !w.objects.contains ctx.object then "unknownObject" else "evaluation"
    let (w', r) := commit w { proposal with writes := [], creates := [] } base
      (some { cls, reason := some reason, object := if cls == "unknownObject" then some ctx.object else none })
      (onEnd := ended "broken")
    (w', turnReply w' r)
  match result with
  | .error (.request message) => if ctx.delivery.isSome || ctx.resumes.isSome then return refuse message else throw message
  | .error (.evaluation reason) => return refuse reason
  | .error (.budget resource) =>
    let (w', r) := commit w { proposal with writes := [], creates := [] } base
      (some { cls := "budget", reason := some resource }) (onEnd := ended "budget")
    return (w', turnReply w' r)
  | .error (.refused cls reason) =>
    let (w', r) := commit w { proposal with writes := [], creates := [] } base
      (some { cls, reason := some reason, object := some ctx.object }) (onEnd := endedIfLate)
    return (w', turnReply w' r)
  | .error (.suspend sp si patience checkpoint interpretation) =>
    let activity := Json.mkObj ([("object", toJson ctx.object), ("method", toJson ctx.method),
      ("argument", dataJson ctx.argument),
      ("checkpoint", checkpoint.toJson),
      ("roots", rootsJson st.roots st.rootCids), ("absent", toJson st.absent),
      ("writes", writesJson st.writes), ("sends", Json.arr (st.sends.toArray.map sendJson)),
      ("creates", Json.arr (st.creates.toArray.map fun (id, c) => createRecJson id c)),
      ("extends", toJson st.layered),
      ("programs", Json.arr (st.programs.toArray.map fun (id, (src, mig)) => Json.mkObj
        [("object", toJson id), ("source", toJson src), ("migration", toJson mig)])),
      ("laws", Json.arr (st.laws.toArray.map fun (id, text) => Json.mkObj [("object", toJson id), ("law", toJson text)])),
      ("ticks", toJson st.ticks), ("awaited", toJson st.awaited), ("awaits", toJson st.awaits),
      ("offers", offersJson st.offers), ("publishes", Json.arr st.publishes.toArray), ("caller", toJson ctx.caller), ("checks", toJson st.checks),
      ("grants", Json.arr (st.grants.toArray.map Grant.json)), ("revokes", toJson st.revokes),
      ("spent", spentJson st.spent)] ++
      (if st.violation.isSome then [("violation", toJson st.violation)] else []))
    let outcome := Json.mkObj <| [("tag", toJson "suspended"),
      ("slot", Json.mkObj [("principal", toJson sp), ("intent", toJson si)]),
      ("deadline", toJson (w.clock + patience)), ("activity", activity)] ++
      (interpretation.map fun i => [("interpretation", i)]).getD []
    let (w', entry) := push w (identityKey ctx.principal ctx.intent)
      ([("identity", identityJson ctx.principal ctx.intent), ("roots", rootsJson st.roots st.rootCids),
        ("turn", toJson proposal.turn), ("request", toJson ctx.digest)] ++ base ++ [("outcome", outcome)] ++
        newSources w (st.creates.flatMap fun (_, c) => inputSources c.object.inputs)) []
    return (w', turnReply w' (reply entry))
  | .ok value =>
    match st.violation with
    | some id =>
      let (w', r) := commit w { proposal with writes := [], creates := [] } base
        (some { cls := "requiredAbsence", object := some id }) (onEnd := endedIfLate)
      return (w', turnReply w' r)
    | none =>
    -- A send under a grant leaves only if the grant still stands (a suspension may have outlived it).
    match st.sends.find? fun x => !x.via.isEmpty && (grantStands w x.via x.to x.method).isNone with
    | some x =>
      let (w', r) := commit w { proposal with writes := [], creates := [], grants := [], revokes := [], spent := [] } base
        (some { cls := "lawRefused", clause := some "noGrant", object := some x.to }) (onEnd := endedIfLate)
      return (w', turnReply w' r)
    | none =>
    let offered := (if st.offers.isEmpty then [] else [("offers", offersJson st.offers)]) ++
      (if st.publishes.isEmpty then [] else [("publishes", Json.arr st.publishes.toArray)]) ++
      (if st.checks == 0 then [] else [("checks", toJson st.checks)])
    let (w', r) := commit w proposal (base ++ [("result", dataJson value)] ++ offered) none
      (sendsJson w ctx.principal ctx.intent ctx.ledger used st.sends) endedIfLate
    return (w', turnReply w' r)

/-- One turn: drive the method, then one `commit`. Request errors (unknown method,
    wrong arity) journal nothing, except for a delivery, which must be consumed. -/
def runTurnWith (w : World) (req : TurnRequest) (how : TurnMeta) : Except String (World × Json) := do
  if let some r := retainedTurn w req then return (w, r)
  let ledger := how.ledger.getD ((w.objects[req.object]?).map (·.chain) |>.getD Ledger.start)
  let ticks ← match Delvetalk.Turn.budgets req.limits with
    | .ok b => pure b.ticks
    | .error e => throw e
  let init : TurnState := { world := w, principal := req.principal, intent := req.intent, subject := req.principal,
                            direct := how.delivery.isNone, ticks, limits := req.limits, profiling := req.profile }
  let (result, st) := (runMethod 0 req.object req.method req.argument how.caller req.principal how.via |>.run).run init
  let ctx : Ctx :=
    { principal := req.principal
      intent := req.intent
      object := req.object
      method := req.method
      argument := req.argument
      digest := req.digest
      ledger := ledger
      delivery := how.delivery
      ticksStart := ticks
      caller := how.caller
      via := how.via }
  let (w', r) ← finishTurn w ctx result st
  return (w', if req.profile then r.setObjVal! "profile" (profileJson st.profile) else r)

/-- A direct turn; `env` and `wake` name the principal's own (`resolveCard`), refused
    `unknownObject` naming `env/<principal>` when it has none. -/
def runTurn (w : World) (req : TurnRequest) : Except String (World × Json) :=
  runTurnWith w { req with object := resolveCard req.principal req.object } {}

/-! ## Resuming suspended turns -/

inductive Resume where
  | reply (entry : Json)
  | timedOut

def computationParts : Ty → Option (Ty × Ty × Ty)
  | .arrow _ _ _ c => computationParts c
  | .computation p r a => some (p, r, a)
  | _ => none

def strings (j : Option Json) : List String :=
  ((j.bind (·.getArr?.toOption)).getD #[]).toList.filterMap fun a => a.getStr?.toOption

/-- The response an `interpreted` entry resumes its `interpret` Plan with. -/
def interpretedResponse (bounds : DataBounds) (responseType : Ty) (e : Json) : M Data := do
  let outcome := (e.getObjVal? "outcome").toOption.getD Json.null
  let verdict ← liftEval (outcome.getObjVal? "verdict")
  match ← liftEval (verdict.getObjValAs? String "tag") with
  | "proposal" =>
    let raw ← liftEval (verdict.getObjVal? "argument")
    let argument ← liftEval (decodeData Limits.dataDepth raw)
    let method ← liftEval (verdict.getObjValAs? String "method")
    respond bounds responseType "proposal" [.record [("method", .label method), ("argument", argument)]]
  | "replied" =>
    respond bounds responseType "replied" [.record [("text", .label (← liftEval (verdict.getObjValAs? String "text")))]]
  | _ =>
    let needs := strings (verdict.getObjVal? "needs").toOption
    respond bounds responseType "unclear" [.record [("needs", listData (needs.map Data.label))]]

/-- Continue the activity a suspension entry journaled. The turn's roots are
    re-validated first: if anything it read or required absent has moved, the whole
    turn is refused `staleRoot` and journaled under its original identity. -/
def resumeOne (w : World) (sus : Json) (kind : Resume) : Except String (World × Json) := do
  let hash ← sus.getObjValAs? String "hash"
  let identity ← sus.getObjVal? "identity"
  let principal ← identity.getObjValAs? String "principal"
  let intent ← identity.getObjValAs? String "intent"
  let outcome ← sus.getObjVal? "outcome"
  let act ← outcome.getObjVal? "activity"
  let object ← act.getObjValAs? String "object"
  let method ← act.getObjValAs? String "method"
  let argument ← decodeData Limits.dataDepth (← act.getObjVal? "argument")
  let roots ← parseRoots (← act.getObjVal? "roots")
  let rootCids := parseRootCids (← act.getObjVal? "roots")
  let absent := strings (act.getObjVal? "absent").toOption
  let ticks ← natField act "ticks"
  let ledger ← ledgerOf (← sus.getObjVal? "ledger")
  let delivery ← match sus.getObjVal? "delivery" with
    | .ok d => pure (some (← d.getObjValAs? String "id", ← d.getObjVal? "from"))
    | .error _ => pure none
  let via := ((sus.getObjVal? "delivery").toOption.bind fun d => (d.getObjValAs? String "via").toOption).getD ""
  let ctx : Ctx :=
    { principal := principal
      intent := intent
      object := object
      method := method
      argument := argument
      digest := ← sus.getObjValAs? String "turnRequest"
      ledger := ledger
      delivery := delivery
      resumes := some hash
      usedBefore := ← natField sus "ticksUsed"
      ticksStart := ticks
      caller := (act.getObjValAs? String "caller").toOption.getD ""
      via
      timedOut := match kind with | .timedOut => true | _ => false }
  -- A moved root whose staged changes so far all commute may still commit (`judge` decides at the
  -- end); one already changed otherwise cannot, and the turn is refused now.
  let staged ← parseRecordedWrites (← act.getObjVal? "writes")
  let movable := fun (id : String) => match staged.lookup id with
    | some changes => changes.all fun c => c.kind == 0 && c.edits.all (·.kind.commutes)
    | none => true
  let stale? := (roots.find? fun (id, v) => match (w.objects[id]?).map (·.version) with
      | some now => now != v && !(v < now && movable id)
      | none => true).map (·.1)
    <|> absent.find? fun id => w.objects.contains id
  if let some id := stale? then
    let stalled : Proposal :=
      { principal := principal
        intent := intent
        roots := roots
        rootCids := rootCids
        writes := []
        turn := w.height + 1
        absent := absent }
    let (w', r) := commit w stalled (entryBase ctx ctx.usedBefore) (some { cls := "staleRoot", object := some id })
    return (w', turnReply w' r)
  let writes ← parseRecordedWrites (← act.getObjVal? "writes")
  let sends ← (← (← act.getObjVal? "sends").getArr?).toList.mapM sendOfJson
  let grants ← (((act.getObjVal? "grants").toOption.bind (·.getArr?.toOption)).getD #[]).toList.mapM Grant.ofJson
  let creates ← ((← (← act.getObjVal? "creates").getArr?).toList.mapM fun r => do
    let id ← r.getObjValAs? String "object"
    let seed ← r.getObjVal? "seed"
    let (o, sources) ← buildObject w (← expandInputs w (← r.getObjVal? "compile")) seed (r.getObjVal? "read").toOption
      (r.getObjVal? "chain").toOption principal (w.height + 1) (some (← r.getObjValAs? String "law"))
    let o := { o with supervisor := (r.getObjValAs? String "supervisor").toOption.getD "" }
    return (id, ({ object := o, sources, seed } : CreateRec)))
  let programs ← ((← (← act.getObjVal? "programs").getArr?).toList.mapM fun r => do
    return (← r.getObjValAs? String "object", (← r.getObjValAs? String "source", ← r.getObjValAs? String "migration")))
  let laws ← ((← (← act.getObjVal? "laws").getArr?).toList.mapM fun r => do
    return (← r.getObjValAs? String "object", ← r.getObjValAs? String "law"))
  let checkpoint ← Delvetalk.Turn.Checkpoint.fromJson (← act.getObjVal? "checkpoint")
  let init : TurnState :=
    { world := w
      roots := roots
      rootCids := rootCids
      writes := writes
      principal := principal
      intent := intent
      subject := principal
      method := method
      via := via
      argument := argument
      direct := delivery.isNone
      grants := grants
      revokes := strings (act.getObjVal? "revokes").toOption
      spent := ← parseSpent (act.getObjVal? "spent").toOption
      sends := sends
      programs := programs
      layered := strings (act.getObjVal? "extends").toOption
      laws := laws
      ticks := ticks
      offers := (((act.getObjVal? "offers").toOption.bind (·.getArr?.toOption)).getD #[]).toList.filterMap fun o =>
        match o.getObjValAs? String "to", o.getObjValAs? String "text" with
        | .ok to, .ok text => some (to, text)
        | _, _ => none
      creates := creates
      absent := absent
      violation := (act.getObjValAs? String "violation").toOption
      awaited := strings (act.getObjVal? "awaited").toOption
      awaits := ← natField act "awaits"
      publishes := (((act.getObjVal? "publishes").toOption.bind (·.getArr?.toOption)).getD #[]).toList
      checks := (natField act "checks").toOption.getD 0
      limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))] }
  let action : M Data := do
    let s ← get
    let some obj := s.world.objects[object]? | evaluation s!"unknown object {object}"
    let compiled ← compiledMethod obj method
    let some (_, responseType, _) := computationParts compiled.type | evaluation "the method is not an activity"
    let response ← match kind with
      | .reply e =>
        if tagOf e == "interpreted" then interpretedResponse compiled.bounds responseType e
        else respond compiled.bounds responseType "reply" [.record [("receipt", receiptData e)]]
      | .timedOut => respond compiled.bounds responseType "timedOut" [emptyRecord]
    -- The activity began with only its own object as a root, at the version still current.
    let binding := Delvetalk.Turn.Binding.make object principal intent
      (roots.filter (·.1 == object))
    let b ← budgetsNow
    let next ← liftEval (Delvetalk.Turn.resumeEntry (← entryOf compiled) checkpoint binding response b)
    drive 0 object ctx.caller compiled binding next 0
  let (result, st) := action.run.run init
  finishTurn w ctx result st

/-- The first suspended activity that can go on: its slot settled, or its deadline passed. -/
def pickResumable (w : World) : Option (Json × Resume) :=
  w.suspended.findSome? fun s =>
    let outcome := (s.getObjVal? "outcome").toOption.getD Json.null
    let slot := (outcome.getObjVal? "slot").toOption.getD Json.null
    match (slot.getObjValAs? String "principal").toOption, (slot.getObjValAs? String "intent").toOption,
        (outcome.getObjValAs? Nat "deadline").toOption with
    | some sp, some si, some deadline =>
      match settled w sp si with
      | some e => some (s, .reply e)
      | none => if w.clock > deadline then some (s, .timedOut) else none
    | _, _, _ => none

/-- Resume everything that can be resumed, oldest first; resumed turns may settle
    other slots, which the next pass picks up. -/
def settle (w : World) : Except String (World × Array Json) := do
  let mut w := w
  let mut out : Array Json := #[]
  for _ in [0:Limits.maxResumesPerCall] do
    let some (s, kind) := pickResumable w | break
    let (w', r) ← resumeOne w s kind
    w := w'
    out := out.push r
  return (w, out)

/-- Run the oldest pending delivery as a turn of its sender's principal. -/
def deliverOne (w : World) (d : Json) : Except String (World × Json) := do
  let id ← d.getObjValAs? String "id"
  let principal ← d.getObjValAs? String "principal"
  let sender ← d.getObjVal? "from"
  let ledger ← ledgerOf (← d.getObjVal? "ledger")
  let via := (d.getObjValAs? String "via").toOption.getD ""
  let how : TurnMeta :=
    { caller := (d.getObjValAs? String "sender").toOption.getD ""
      via
      ledger := some ledger
      delivery := some (id, sender) }
  let to ← d.getObjValAs? String "to"
  let method ← d.getObjValAs? String "method"
  let deliveryFields := [("ledger", ledger.json), ("delivery", Json.mkObj ([("id", toJson id), ("from", sender)] ++
    (if via.isEmpty then [] else [("via", toJson via)])))]
  -- A send under a grant that no longer stands (revoked, or the clock past it) is consumed, refused.
  if !via.isEmpty && (grantStands w via to method).isNone then
    let p : Proposal := { principal := principal, intent := id, roots := [], writes := [], turn := w.height + 1 }
    return commit w p deliveryFields (some { cls := "lawRefused", clause := some "noGrant", object := some to })
  match ledger.exhausted with
  | some field =>
    let p : Proposal := { principal := principal, intent := id, roots := [], writes := [], turn := w.height + 1 }
    let (w', r) := commit w p deliveryFields
      (some { cls := "budgetExhausted", reason := some field })
    return (w', r)
  | none =>
    let argument ← decodeData Limits.dataDepth (← d.getObjVal? "argument")
    let object ← d.getObjValAs? String "to"
    let method ← d.getObjValAs? String "method"
    let req : TurnRequest :=
      { principal := principal
        object := object
        method := method
        argument := argument
        intent := id
        limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))]
        digest := Journal.bodyHash d }
    runTurnWith w req how

/-- Up to `limit` deliveries, oldest first; sends of a delivery join the queue. -/
def deliver (w : World) (limit : Nat) : Except String (World × Json) := do
  let mut w := w
  let mut receipts : Array Json := #[]
  for _ in [0:min limit Limits.deliveriesPerCall] do
    let some d := w.pending[0]? | break
    let (w', r) ← deliverOne w d
    w := w'
    -- A delivery's offers are its addressees' (`world-offers`), not the caller's of this op.
    receipts := receipts.push (match r.getObj? with
      | .ok fields => Json.mkObj (fields.toList.filter (·.1 != "offers"))
      | .error _ => r)
  return (w, Json.mkObj [("status", toJson "delivered"), ("receipts", Json.arr receipts),
    ("pending", toJson w.pending.size)])

/-- The settling pass after a durable op: resume what can go on, then run pending deliveries
    oldest first (each may release more), up to `deliveriesPerSettle`. Nobody calls deliver. -/
def settleAll (w : World) : Except String (World × Array Json × Array Json) := do
  let (w, resumed) ← settle w
  let mut w := w
  let mut resumed := resumed
  let mut delivered : Array Json := #[]
  for _ in [0:Limits.deliveriesPerSettle] do
    let some d := w.pending[0]? | break
    let (w', r) ← deliverOne w d
    let (w'', more) ← settle w'
    w := w''
    delivered := delivered.push r
    resumed := resumed ++ more
  return (w, resumed, delivered)

def pendingReply (w : World) : Json :=
  Json.mkObj [("status", toJson "pending"), ("count", toJson w.pending.size),
    ("ids", Json.arr ((w.pending.extract 0 Limits.maxHistoryLimit).map fun p =>
      (p.getObjVal? "id").toOption.getD Json.null))]

/-! ## Reprogramming and amending as ops -/

def withProgramRefusal (w : World) (p : Proposal) (clause message : String) : World × Json :=
  commit w p [] (some { cls := "programRefused", clause := some clause, reason := some message })

/-- `world-reprogram {principal, identity, object, version, package, migration?}`. -/
def reprogramOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let object ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let source ← j.getObjValAs? String "package"
  let migration := (← optText j "migration").getD ""
  let extend ← match (← optText j "mode") with
    | none | some "replace" => pure false
    | some "extend" => pure true
    | some other => throw s!"mode must be replace or extend, not {other}"
  let version ← natField j "version"
  if (j.getObjVal? "turn").toOption.isSome then throw "turn is assigned by the host and cannot be supplied"
  let p : Proposal :=
    { principal := principal
      intent := intent
      roots := [(object, version)]
      writes := []
      programs := [(object, (source, migration))]
      layered := if extend then [object] else [] }
  if let some r := retained w principal intent p.digest then return (w, r)
  match w.objects[object]? with
  | none => return commit w p
  | some o => match programFor w o source migration extend with
    | .error (clause, message) => return withProgramRefusal w p clause message
    | .ok prog => return commit (cacheProgram w o source migration prog extend) p

/-- `world-revoke {principal, identity, grant}`: the grantor's own write to the grant, outside any
    object: the grant stops standing with this entry. Anyone else is refused `notGrantor`. -/
def revokeOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let id ← boundedText "grant" Limits.maxIntentBytes (← j.getObjValAs? String "grant")
  let p : Proposal := { principal, intent, roots := [], writes := [], revokes := [id] }
  if let some r := retained w principal intent p.digest then return (w, r)
  unless w.grants.contains id do throw s!"unknown grant {id}"
  return commit w p

/-- `world-amend {principal, identity, object, version, law}`. -/
def amendOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let object ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let text ← j.getObjValAs? String "law"
  let version ← natField j "version"
  if (j.getObjVal? "turn").toOption.isSome then throw "turn is assigned by the host and cannot be supplied"
  let p : Proposal :=
    { principal := principal
      intent := intent
      roots := [(object, version)]
      writes := []
      laws := [(object, text)] }
  if let some r := retained w principal intent p.digest then return (w, r)
  match parseLawText text with
  | .error message => return withProgramRefusal w p "law syntax" message
  | .ok _ => return commit w p


/-! ## Reflection and interpretation as ops -/

/-- `world-inspect {principal, object}`: the pin, law text and entry source an object
    shows a reader its read policy permits. -/
def inspectOp (w : World) (j : Json) : Except String Json := do
  let id ← j.getObjValAs? String "object"
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  match w.objects[id]? with
  | none => return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  | some o =>
    if !o.read.permits principal then
      return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
    return Json.mkObj [("status", toJson "inspected"), ("object", toJson id), ("pin", toJson o.pin),
      ("law", toJson o.lawText), ("source", toJson (entrySource o)), ("methods", o.methods),
      ("supervisor", toJson o.supervisor),
      ("forms", dataJson (listData (methodForms id o.methods)))]

/-- `world-card {principal, object}`: the object's rendered card, as text and as Document data. -/
def cardOp (w : World) (j : Json) : Except String Json := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let id := resolveCard principal (← j.getObjValAs? String "object")
  match w.objects[id]? with
  | none => return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  | some o =>
    if !o.read.permits principal then return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
    let init : TurnState := { world := w, principal, intent := "", subject := principal, ticks := Limits.maxTurnTicks,
                              limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))] }
    match ((renderCard o (cardContext w id principal "" "" w.height)).run.run init).1 with
    | .ok (.ok document) =>
      return Json.mkObj [("status", toJson "card"), ("object", toJson id),
        ("text", toJson (← Delvetalk.Document.render document)), ("document", dataJson document)]
    | .ok (.error clause) => return Json.mkObj [("status", toJson "refused"), ("object", toJson id), ("clause", toJson clause)]
    | .error _ => return Json.mkObj [("status", toJson "refused"), ("object", toJson id), ("clause", toJson "render")]

/-- Plain JSON for a model to read: lists are arrays, a sum is an object with its `tag`. -/
partial def listHeads (acc : List Data) : Data → Option (List Data)
  | .variant "nil" _ => some acc.reverse
  | .variant "cons" (.record f) => do
    let head ← f.lookup "head"
    let tail ← f.lookup "tail"
    listHeads (head :: acc) tail
  | _ => none

partial def plainJson : Data → Json
  | .natural n => toJson n
  | .boolean b => toJson b
  | .label s => toJson s
  | .record fs => Json.mkObj (fs.map fun (k, v) => (k, plainJson v))
  | d@(.variant l p) =>
    match listHeads [] d with
    | some items => Json.arr (items.toArray.map plainJson)
    | none => match p with
      | .record fs => Json.mkObj (("tag", toJson l) :: fs.map fun (k, v) => (k, plainJson v))
      | other => Json.mkObj [("tag", toJson l), ("value", plainJson other)]

/-- The system text an interpretation sends: the Policy's own pure `prompt(state, offers,
    utterance)` when its package defines one and it renders text under the turn tick budget,
    else none (the caller then sends the `system` field). The method table does not list
    `prompt` (its offers are not a form), so the definition is compiled by name and cached. -/
def policyPrompt (w : World) (o : Object) (offers : Data) (utterance : String) : Option String × World :=
  match compileDef w o "prompt" with
  | .error _ => (none, w)
  | .ok (c, w') =>
    let cache := if w'.compiled.size < Limits.maxCompiledPackets then w'.compiled else {}
    let w' := { w' with compiled := cache.insert (defKey o "prompt") c }
    match c.entry with
    | none => (none, w')
    | some entry =>
      match (runPure entry [o.state, offers, .label utterance] Limits.maxTurnTicks).1 with
      | .ok (.label text) => (some text, w')
      | _ => (none, w')

/-- The state of a Policy object as `{model, system, examples}` (absent fields are null), with
    `system` the Policy's rendered prompt for these offers and utterance when it has one. -/
def policyJson (w : World) (id : String) (offers : Data) (utterance : String) : Json × World :=
  match w.objects[id]? with
  | some o =>
    match o.state with
    | Data.record f =>
      let (prompt, w) := policyPrompt w o offers utterance
      let field := fun k => ((f.lookup k).map plainJson).getD Json.null
      (Json.mkObj [("model", field "model"), ("system", (prompt.map toJson).getD (field "system")),
        ("examples", field "examples")], w)
    | _ => (Json.null, w)
  | none => (Json.null, w)

def interpretationOf (s : Json) : Option Json :=
  (s.getObjVal? "outcome").toOption.bind fun o => (o.getObjVal? "interpretation").toOption

/-- `world-interpretations`: every `interpret` still waiting for a reply. The world returned
    carries only the compiled prompts it cached; nothing is journaled. -/
def interpretationsReply (w : World) : World × Json := Id.run do
  let mut w := w
  let mut pending : Array Json := #[]
  for s in w.suspended do
    let item : Option (String × String × String × Data × String) := do
      let i ← interpretationOf s
      let id ← (i.getObjValAs? String "id").toOption
      guard (settled w interpretationPrincipal id).isNone
      let deadline ← ((s.getObjVal? "outcome").toOption.bind (·.getObjValAs? Nat "deadline" |>.toOption))
      guard (w.clock ≤ deadline)
      let object ← (i.getObjValAs? String "object").toOption
      let policy ← (i.getObjValAs? String "policy").toOption
      let offers ← (i.getObjVal? "offers").toOption.bind fun o => (decodeData Limits.dataDepth o).toOption
      let utterance ← (i.getObjValAs? String "utterance").toOption
      pure (id, object, policy, offers, utterance)
    let some (id, object, policy, offers, utterance) := item | continue
    let (shown, w') := policyJson w policy offers utterance
    w := w'
    pending := pending.push (Json.mkObj [("id", toJson id), ("object", toJson object), ("policy", shown),
      ("utterance", toJson utterance), ("offers", plainJson offers)])
  return (w, Json.mkObj [("status", toJson "interpretations"), ("pending", Json.arr pending)])

def scratchState (w : World) : TurnState :=
  { world := w, principal := "", intent := "", subject := "", ticks := 0, limits := Json.mkObj [] }

def abortText : Abort → String
  | .request m | .evaluation m => m
  | .budget r => s!"{r} budget exhausted"
  | .refused cls r => s!"{cls}: {r}"
  | .suspend .. => "unexpected suspension"

/-- The input type of a method: `none` when it takes none, an error when it is not a method. -/
def inputTypeOf : Ty → Except String (Option Ty)
  | .arrow _ _ _ (.arrow _ _ dom (.arrow _ _ _ _)) => pure (some dom)
  | .arrow _ _ _ (.arrow _ _ _ _) => pure none
  | _ => throw "not a method"

def unclearVerdict (needs : List String) : Json :=
  Json.mkObj [("tag", toJson "unclear"), ("needs", toJson needs)]

/-- What a reply says to the suspended object. A JSON reply `{method, argument}` is a proposal
    (a method of the object, one of the offered actions, with an argument that conforms to the
    method's input type and fits the object's response type) or `unclear` with the reason. Any
    other reply is the model's text, `replied {text}`, for the object to read with its own
    grammar; an object whose Response cannot carry it hears `unclear`. A failed call is
    `unclear {needs: ["model: <reason>"]}`. -/
def interpretVerdict (w : World) (s : Json) (reply : Json) : Except String (World × Json) := do
  let some i := interpretationOf s | throw "not an interpretation"
  let act ← (← s.getObjVal? "outcome").getObjVal? "activity"
  let object ← act.getObjValAs? String "object"
  let suspendedMethod ← act.getObjValAs? String "method"
  match (reply.getObjValAs? String "status").toOption with
  | some "replied" => pure ()
  | some "failed" =>
    let reason := ((reply.getObjValAs? String "reason").toOption).getD "failed"
    return (w, unclearVerdict [s!"model: {reason}"])
  | _ => throw "reply must have status replied or failed"
  let json := (reply.getObjVal? "json").toOption.getD Json.null
  let raw := (reply.getObjValAs? String "raw").toOption
  if json.isNull && raw.isNone then throw "a replied interpretation carries json or raw"
  let some obj := w.objects[object]? | throw s!"unknown object {object}"
  let (r2, st2) := ((compiledMethod obj suspendedMethod).run.run (scratchState w))
  let suspended ← match r2 with | .ok c => pure c | .error e => throw (abortText e)
  let some (_, responseType, _) := computationParts suspended.type | throw "the suspended method is not an activity"
  let w := { w with compiled := st2.world.compiled }
  let some method := (json.getObjValAs? String "method").toOption
    | match raw with
      | some text =>
        if (Data.variant "replied" (.record [("text", .label text)])).conformsUnder suspended.bounds responseType then
          return (w, Json.mkObj [("tag", toJson "replied"), ("text", toJson text)])
        return (w, unclearVerdict ["the reply names no method"])
      | none => return (w, unclearVerdict ["the reply names no method"])
  let offers ← decodeData Limits.dataDepth (← i.getObjVal? "offers")
  let actions := ((listHeads [] offers).getD []).filterMap fun form =>
    match form with
    | .record f => (f.lookup "action").bind labelOf
    | _ => none
  if !actions.isEmpty && !actions.contains method then
    return (w, unclearVerdict [s!"{method} is not one of the offered actions"])
  let (r, st) := ((compiledMethod obj method).run.run (scratchState w))
  let w := { w with compiled := st.world.compiled }
  let compiledM ← match r with
    | .ok c => pure c
    | .error e => return (w, unclearVerdict [s!"{method} is not a method of the object: {abortText e}"])
  let raw := (json.getObjVal? "argument").toOption.getD (Json.mkObj [])
  let input ← (inputTypeOf compiledM.type).mapError fun _ => s!"{method} is not a method"
  let wanted := match raw with
    | .null => Json.mkObj []
    | other => other
  match Package.jsonData Limits.plainDepth wanted with
  | .error e => return (w, unclearVerdict [s!"the argument is not plain data: {e}"])
  | .ok (argument, _) =>
    let fits := match input with
      | some dom => argument.conformsUnder compiledM.bounds dom
      | none => match argument with | .record [] => true | _ => false
    if !fits then return (w, unclearVerdict [s!"the argument does not fit the input of {method}"])
    let candidate := Data.variant "proposal" (.record [("method", .label method), ("argument", argument)])
    if !candidate.conformsUnder suspended.bounds responseType then
      return (w, unclearVerdict [s!"the object cannot carry a proposal of {method}"])
    return (w, Json.mkObj [("tag", toJson "proposal"), ("method", toJson method),
      ("argument", dataJson argument)])

/-- `world-interpretation {id, reply}`: settle a pending interpretation with the model's
    reply, verbatim. The verdict is journaled; the suspended turn resumes with it. -/
def interpretationOp (w : World) (j : Json) : Except String (World × Json) := do
  let id ← boundedText "interpretation id" Limits.maxIntentBytes (← j.getObjValAs? String "id")
  let replied ← j.getObjVal? "reply"
  if replied.compress.utf8ByteSize > Limits.maxReplyBytes then throw "reply exceeds its byte capacity"
  let digest := Journal.bodyHash replied
  if let some r := retained w interpretationPrincipal id digest then return (w, r)
  let some s := w.suspended.find? fun s => (interpretationOf s).bind (·.getObjValAs? String "id" |>.toOption) == some id
    | throw s!"no pending interpretation {id}"
  let (w, verdict) ← interpretVerdict w s replied
  let (w', entry) := push w (identityKey interpretationPrincipal id)
    [("identity", identityJson interpretationPrincipal id), ("roots", rootsJson []),
     ("turn", toJson (w.height + 1)), ("request", toJson digest),
     ("outcome", Json.mkObj [("tag", toJson "interpreted"), ("id", toJson id), ("reply", replied),
       ("verdict", verdict)])] []
  return (w', reply entry)

end Delvetalk.Host
