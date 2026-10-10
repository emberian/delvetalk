/- Driving an activity against the store. A turn reads committed state, collects
   the roots it viewed and the writes it performed, and ends in exactly one
   `commit`. An activity yields `World.Message {object, method, argument}` (`world/lib/World.obend`);
   `messagePlan` re-heads it as the arm of `answer` named by `method` (`worldMethods`).
   `docs/HOST-HANDOFF.md` section 5 says what each does. A method is
   `(state, [input,] context) -> Activity<A>` or the same with a pure data result (the new state). -/
import Delvetalk.Host.Ops
import Delvetalk.Turn
import Delvetalk.Document
import Delvetalk.Host.Spell

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
  /-- The post this turn's text replies to ("" for none): the bridge names the parent of an
      observed reply, so a reply to a recorded post is the reply that post awaits. -/
  replyTo : String := ""
  /-- How the method was asked for (`inputOrigin.kind`): `request`, or `spell` when the host parsed
      the reply's spell (`spellTurn`), and the line that asked (`inputOrigin.command`, "" for the method). -/
  origin : String := "request"
  command : String := ""
  /-- The post the turn came from (`inputOrigin.post`): the `post` of the `{text, post}` it was
      asked with, kept when the host reads that reply as a spell (`heardPost`). -/
  post : String := ""

/-- The post a `receive {text, post}` is asked from: the reply's own post, which a spell's method
    no longer sees in its argument. -/
def heardPost (method : String) (argument : Data) : Option String :=
  if method != "receive" then none else
  match argument with
  | .record fs => match fs.lookup "post" with
    | some (.label p) => if p.isEmpty then none else some p
    | _ => none
  | _ => none

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
  let replyTo := (← optText j "replyTo").getD ""
  if replyTo.utf8ByteSize > Limits.maxUriBytes then throw s!"replyTo must be at most {Limits.maxUriBytes} bytes"
  let digest := Journal.bodyHash (Json.mkObj ([("principal", toJson principal), ("object", toJson object),
    ("method", toJson method), ("argument", dataJson argument), ("limits", limits)] ++
    (if replyTo.isEmpty then [] else [("replyTo", toJson replyTo)])))
  let profile ← match j.getObjVal? "profile" with
    | .ok (.bool b) => pure b
    | .ok _ => throw "profile must be true or false"
    | .error _ => pure false
  return { principal, object, method, argument, intent, limits, digest, profile, replyTo }

inductive Abort where
  /-- The request is not a well-formed turn; nothing is journaled. -/
  | request (message : String)
  /-- The turn is refused by name; a refused entry is journaled. -/
  | evaluation (reason : String)
  /-- A machine budget ran out (`ticks`, `heap`, `stack`, `nodes`, `bytes`): the named
      silence, journaled as class `budget` with the resource as its reason. -/
  | budget (resource : String)
  /-- The turn is refused with a named class other than `evaluation` (`typeMismatch`: the
      argument does not conform to the method's input type, `expected` what it takes). -/
  | refused (cls reason : String) (expected : Option Json := none)
  /-- The turn's principal has started its hour's interpretations (`interpretQuota`): a transient
      refusal of class `quota`, naming the clock at which the next may start. -/
  | quota (reason : String) (next : Nat)
  /-- The turn awaits a slot: its activity is checkpointed and journaled. -/
  | suspend (principal intent : String) (patience : Nat) (checkpoint : Delvetalk.Turn.Checkpoint)
      (interpretation : Option Json := none) (post : Option String := none)
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
  writes : List (String × List Written) := []
  /-- Fields read alone (`viewField`): object, field, version (`recordFieldRoot`). -/
  fieldRoots : List (String × String × Nat) := []
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
  /-- A delivery the host owes the object's own choice of receiver (a change to its subscription's
      method, an activity's end to its supervisor): it may name a helper. -/
  receiver : Bool := false
  /-- The top frame's `inputOrigin` kind and command (`TurnRequest.origin`, `command`). -/
  origin : String := "request"
  command : String := ""
  /-- The running frame's post (`inputOrigin.post`): its own `receive {text, post}`'s, else the
      calling frame's; journaled with a suspension. -/
  post : String := ""
  grants : List Grant := []
  revokes : List String := []
  /-- Subscriptions this turn makes and ends (`subscribe`/`unsubscribe`). -/
  subscribes : List Subscription := []
  unsubscribes : List Subscription := []
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
  /-- The object whose `create` found the violation: the root the refusal names. -/
  violator : String := ""
  /-- Slots this turn already awaited, as identity keys, and how many awaits it has made. -/
  awaited : List String := []
  awaits : Nat := 0
  /-- `check` Plans this turn ran; the journal keeps the count. -/
  checks : Nat := 0
  /-- Handlers installed by `run`, innermost first: the call depth of the callee's frame and the
      handler object. Every frame at that depth or deeper, until the `run` returns, is under it. -/
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
    if s.roots.length + s.fieldRoots.length ≥ Limits.maxRoots then evaluation "turn exceeds the root capacity"
    set { s with roots := s.roots ++ [(id, version)] }

/-- A root on one field of an object (`viewField`, WHOLENESS §3a): none when the whole object is
    already a root, which covers it. -/
def recordFieldRoot (id field : String) (version : Nat) : M Unit := do
  let s ← get
  unless s.roots.any (·.1 == id) || s.fieldRoots.any (fun (o, f, _) => o == id && f == field) do
    if s.roots.length + s.fieldRoots.length ≥ Limits.maxRoots then evaluation "turn exceeds the root capacity"
    set { s with fieldRoots := s.fieldRoots ++ [(id, field, version)] }

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
  match s.world.compiled[key]? <|> diskCompiled key with
  | some c =>
    unless s.world.compiled.contains key do
      let cache := if s.world.compiled.size < Limits.maxCompiledPackets then s.world.compiled else {}
      set { s with world := { s.world with compiled := cache.insert key c } }
    return c
  | none =>
    -- A method (of a layer stack too: the kernel resolves it with late binding) is compiled from
    -- its package's closure prepared once, and held decoded and checked.
    match compileEntryIn s.world obj.inputs method >>= fun (ec, w) => do return (← compiledOf ec, w) with
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

/-- The id a create with an empty `requireAbsent` gets: `<creator>/<package, lowercased>/<n>`, the
    first `n` past the creator's `minted` counter not held by an object, by this turn's creates,
    or by the creates of a suspended turn (its `absent`), so interleaved creators never race on
    a name. A source package is kind `created`. -/
def mintId (self package : String) : M String := do
  let s ← get
  let reserved : Std.HashSet String := s.world.suspended.foldl (fun acc e =>
    let absent := ((e.getObjVal? "outcome").toOption.bind (·.getObjVal? "activity" |>.toOption)
      |>.bind (·.getObjVal? "absent" |>.toOption) |>.bind (·.getArr? |>.toOption)).getD #[]
    absent.foldl (fun a x => match x.getStr? with | .ok i => a.insert i | .error _ => a) acc) {}
  let kind := (if package.startsWith "edition" then "created" else package).toLower
  let base := ((s.world.objects[self]?).map (·.minted)).getD 0
  let mut n := base + 1
  for _ in [0:Limits.maxObjects + Limits.maxSuspended + Limits.createsPerTurn] do
    let id := s!"{self}/{kind}/{n}"
    if !(s.world.objects.contains id || s.creates.any (·.1 == id) || reserved.contains id) then return id
    n := n + 1
  evaluation "no child id is free"

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

def buildCreated (w : World) (creator : Object) (package : String) (seed : Data) (lawArg principal : String)
    (height : Nat) : Except (String × String) (CreateRec × Built) := do
  let inputs ← creationInputs creator package
  let built ← (compileObject w inputs).mapError (("compile", ·))
  let initial ← (initialState built).mapError (("compile", ·))
  let state ← (mergeSeed initial seed built.assumptions.bounds built.ty).mapError (("typeMismatch", ·))
  let state := withOwner state seed principal
  let (relations, state) ← (relationsFor built state).mapError fun e =>
    (if e.startsWith "duplicateKey" then "duplicateKey" else "key", e)
  let lawText := if lawArg.startsWith "law " then some lawArg else none
  let (object, sources) ← (makeObject built inputs state none none principal height lawText).mapError
    (fun e => (if isAmendmentRefusal e then "law"
      else if e.endsWith "byte capacity" then "capacity" else "typeMismatch", e))
  return ({ object := { object with relations }, sources, seed := dataJson state }, built)

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
    run (it takes a context) whose input is a record of form-expressible fields, among those the package
    declares public (and `receive`): helpers and the other conventional names (`render`, `set`) have none. -/
def methodForms (id : String) (methods : Json) (declared : List (String × List (String × Data)) := []) : List Data :=
  ((methods.getArr?.toOption).getD #[]).toList.filterMap fun m => do
    guard ((m.getObjValAs? Bool "context").toOption == some true && isActionRow m)
    let name ← (m.getObjValAs? String "name").toOption
    let fields ← rowFields ((m.getObjVal? "input").toOption.getD Json.null)
    -- A field the package's form for this action declares takes that kind; any other, its type's.
    let given := (declared.lookup name).getD []
    let kinds ← fields.mapM fun (n, member) =>
      (given.lookup n <|> formKind member).map fun k => Data.record [("name", .label n), ("kind", k)]
    return .record [("card", .label id), ("action", .label name), ("fields", listData kinds)]

/-- A declared form field's kind as the host reads it: `text`, `natural` and `choice` as given, and
    `source` (Bend source) as text of 1 to `Limits.formSourceMax` characters. -/
def declaredKind : Data → Option Data
  | .variant "source" _ => some (.variant "text" (.record [("min", .natural 1), ("max", .natural Limits.formSourceMax)]))
  | k@(.variant "text" _) => some k
  | k@(.variant "natural" _) => some k
  | k@(.variant "choice" _) => some k
  | _ => none

/-- The kinds the package's pure `forms()` declares, by action and field, and the `source` fields by
    action; none when its entry module declares no `forms()` or it does not evaluate. -/
def declaredForms (o : Object) : M (List (String × List (String × Data)) × List (String × List String)) := do
  if !((entrySource o).splitOn "\n").any (·.startsWith "def forms(") then return ([], [])
  let some c ← tryCatch (some <$> compiledMethod o "forms") (fun _ => pure none) | return ([], [])
  let some entry := c.entry | return ([], [])
  let .ok value := (runPure entry [] Delvetalk.Bounds.lawTicks).1 | return ([], [])
  let forms := ((listOf value).getD []).filterMap fun
    | .record f => do
      let action ← (f.lookup "action").bind labelOf
      let fields := (((f.lookup "fields").bind listOf).getD []).filterMap fun
        | .record g => do
          let name ← (g.lookup "name").bind labelOf
          let kind ← g.lookup "kind"
          return (name, kind)
        | _ => none
      return (action, fields)
    | _ => none
  return (forms.map fun (a, fs) => (a, fs.filterMap fun (n, k) => (declaredKind k).map (n, ·)),
          forms.map fun (a, fs) => (a, fs.filterMap fun (n, k) => match k with | .variant "source" _ => some n | _ => none))

/-- An object's forms (`methodForms`) with the kinds its `forms()` declares: a spell is judged by the
    card's own bounds, and the type's default holds only for a field no form names. -/
def formsOf (id : String) (o : Object) : M (List Data) := do
  return methodForms id o.methods (← declaredForms o).1

/-- Does the object's method table list `name`? -/
def hasMethod (o : Object) (name : String) : Bool :=
  ((o.methods.getArr?.toOption).getD #[]).any fun m => (m.getObjValAs? String "name").toOption == some name

/-- The Context a card is rendered for: the reader (`principal`), the card's object, the asking
    object (`caller`, "" for `world-card`), and the turn's intent and height. -/
def cardContext (w : World) (id reader caller intent : String) (height : Nat) (method : String) : Data :=
  contextData id reader (handleOf w reader) caller intent height w.clock "card" method

/-- An object's card as `context`'s reader sees it, run on its committed state under this turn's
    ticks: `renderFor(state, context)` when the package has it, else `render`, which may take
    `(state, context)` or the state alone. `noCard` when it has neither, `render` when it fails
    or runs out. -/
def renderCard (o : Object) (context : String → Data) : M (Except String Data) := do
  let name := if hasMethod o "renderFor" then "renderFor" else "render"
  let compiled ← tryCatch (some <$> compiledMethod o name) fun _ => pure none
  let some c := compiled | return .error "noCard"
  let arguments := match c.type with
    | .arrow _ _ _ (.arrow _ _ ct _) => #[o.state, fitRecord c.bounds ct (context name)]
    | _ => #[o.state]
  let entry ← entryOf c
  let st ← get
  match Package.executeDataEntry entry arguments (st.limits.setObjVal! "ticks" (toJson (toString st.ticks))) with
  | .ok (.finished value _ _ usage) => spend (usage.ticksUsed + usage.conversionNodes); return .ok value
  | .ok (.refused _ usage) => spend (usage.ticksUsed + usage.conversionNodes); return .error "render"
  | .error _ => return .error "render"

/-- The views a package declares: the labels its pure `views()` returns (`def views() ->
    List<String>`), read as `lawReads()` is; none when it has no such definition. -/
def declaredViews (o : Object) : M (List String) := do
  if !((entrySource o).splitOn "\n").any (·.startsWith "def views(") then return []
  let some c ← tryCatch (some <$> compiledMethod o "views") (fun _ => pure none) | return []
  let some entry := c.entry | return []
  match (runPure entry [] Delvetalk.Bounds.lawTicks).1 with
  | .ok d => return (labels [] d).getD []
  | .error _ => return []

/-- A derived view of an object (`viewDerived {object, view}`): the package's pure definition
    `view`, which `views()` must name, run on the committed state (with the reader's Context when
    it takes one) under this turn's remaining ticks, as a card is rendered. Its value must be
    first-order data. `noView` when the package does not declare `view`, `view` when it fails, runs
    out, or answers something other than data. -/
def derivedView (o : Object) (view : String) (context : Data) : M (Except String Data) := do
  unless (← declaredViews o).contains view do return .error "noView"
  let some c ← tryCatch (some <$> compiledMethod o view) (fun _ => pure none) | return .error "noView"
  let (arguments, result) := match c.type with
    | .arrow _ _ _ (.arrow _ _ ct r) => (#[o.state, fitRecord c.bounds ct context], r)
    | .arrow _ _ _ r => (#[o.state], r)
    | r => (#[], r)
  unless result.isDataUnder c.bounds [] Ty.dataFuel [] do return .error "view"
  let entry ← entryOf c
  let st ← get
  match Package.executeDataEntry entry arguments (st.limits.setObjVal! "ticks" (toJson (toString st.ticks))) with
  | .ok (.finished value _ _ usage) => spend (usage.ticksUsed + usage.conversionNodes); return .ok value
  | .ok (.refused _ usage) => spend (usage.ticksUsed + usage.conversionNodes); return .error "view"
  | .error _ => return .error "view"

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

/-- The argument of a turn asked from outside with its text words read as cases where the method's
    input has closed sums of empty payloads (`wordsAsCases`). A word naming no case is
    `(path, word, cases)`. -/
def inputWords (compiled : Compiled) (argument : Data) : Except (String × String × List String) Data :=
  match compiled.type with
  | .arrow _ _ _ (.arrow _ _ domain (.arrow _ _ _ _)) => wordsAsCases compiled.bounds domain argument
  | _ => pure argument

/-- A word that names no case, refused as the reason says: "colour is one of: amber, violet". -/
def wordRefusal (path word : String) (cases : List String) : String :=
  s!"{argumentRefusal}: {if path.isEmpty then "the argument" else path} is one of: {", ".intercalate cases} (not {word})"

/-- What method `method` of object `id` takes, for a `typeMismatch` refusal: `type`, its input
    as the artifact's method table records it (resolved, so it reads alone), else the compiled
    domain (`typeJson`, whose variables need the packet's bounds); and `form`, the form a card
    would offer for it (`methodForms`, plain JSON), when it has one. -/
def expectedInput (obj : Object) (id method : String) (compiled : Compiled) : Json :=
  let row := ((obj.methods.getArr?.toOption).getD #[]).find? fun m => (m.getObjValAs? String "name").toOption == some method
  let type := match (row.bind fun r => (r.getObjVal? "input").toOption), compiled.type with
    | some input, _ => input
    | none, .arrow _ _ _ (.arrow _ _ domain (.arrow _ _ _ _)) => Minidregg.Theory.ObjectiveBendTyping.typeJson domain
    | none, _ => Json.null
  let form := row.bind fun r => (methodForms id (Json.arr #[r])).head?
  Json.mkObj ([("method", toJson method), ("type", type)] ++ (form.map fun f => [("form", plainJson f)]).getD [])

/-- A kernel refusal at the start or resumption of an activity: an argument that does not
    conform is the journaled class `typeMismatch` (with what was `expected`), anything else an
    `evaluation`. -/
def kernelRefusal {α : Type} (r : Except String α) (expected : Option Json := none) : M α :=
  match r with
  | .ok a => pure a
  | .error e => if e.startsWith argumentRefusal then throw (.refused "typeMismatch" e expected) else throw (.evaluation e)

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
  let context := contextData handler s.subject (handleOf s.world s.subject) self s.intent s.world.height s.world.clock "handle" "" s.post
  let (domain, arguments) := match c.type with
    | .arrow _ _ _ (.arrow _ _ d (.arrow _ _ ct _)) => (d, [obj.state, plan, fitRecord c.bounds ct context])
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

/-- The clause that would refuse a reprogram (kind 1) or amendment (kind 2) of `id`, another
    object than the running one, proposed by `proposer` in the running frame: the target's law
    (text and metarule; a reprogram's compile and migration too) judges that change alone, at the
    version the turn reads, now. `none` when it would admit, and always for the running object
    itself, whose change the commit judges with the rest of the turn. `change` carries the
    proposal's `programs`/`layered` or `laws`. -/
def dryChange (w : World) (s : TurnState) (self id : String) (version : Nat) (proposer : String) (kind : Nat)
    (change : Proposal) : Option String :=
  if id == self then none else
  let written : Written := { caller := proposer, kind, edits := [], method := s.method, via := s.via, argument := s.argument }
  let p : Proposal := { change with principal := s.principal, intent := s.intent, roots := [(id, version)],
                                    writes := [(id, [written])], turn := w.height + 1 }
  match judge w (w.height + 1) p with
  | .ok _ => none
  | .error r => some (r.clause.getD r.cls)

/-- Why a turn naming a helper is refused (class `noMethod`). -/
def noMethodReason (id method : String) : String :=
  s!"{id} has no method {method}; reply delvetalk {id} ? for its spells."

/-- Is `method` refused to `self` calling object `id`: not a method `id` offers? An object may call
    its own helpers. -/
def helperOf (w : World) (self id method : String) : Bool :=
  id != self && ((w.objects[id]?).map (!·.offers method)).getD false

/-- The world's methods (WHOLENESS §1, `protocol world`), which a message activity calls. `spell` is
    not one: the host's spell path runs a card's methods directly (WHOLENESS, second root decisions, 5). -/
def worldMethods : List String :=
  ["view", "viewField", "viewAt", "viewDerived", "write", "judge", "call", "callVia", "run", "send",
   "sendVia", "create", "createUnder", "await", "awaitUntil", "awaitPost", "awaitPostUntil", "interpret",
   "offer", "publish", "reprogram", "extend", "amend", "inspect", "check", "grant", "grantWith", "revoke",
   "objects", "card", "subscribe", "unsubscribe"]

/-- A message activity's yield (`World.Message {object, method, argument}`, WHOLENESS §1) as the
    host answers it: a call of the world object's `method`, re-headed as the Plan variant the arms
    answer (`write`'s argument is the edits of the running object, `judge`'s the edits to judge).
    `.error clause` for a message to another object (`notWorld`: a message to an object is a
    `call`), a method the world has not, or anything else (`noMethod`). -/
def messagePlan (self : String) : Data → Except String Data
  | .record fs =>
    match fs.lookup "object", (fs.lookup "method").bind labelOf, fs.lookup "argument" with
    | some target, some method, some argument =>
      if fs.length != 3 then .error "noMethod" else
      if referenceId target != some worldId then .error "notWorld"
      else if !worldMethods.contains method then .error "noMethod"
      else .ok (match method with
        | "write" => .variant "write" (.record [("object", .record [("world", .label ""), ("object", .label self)]), ("edits", argument)])
        | "judge" => .variant "judge" (.record [("edits", argument)])
        | _ => .variant method argument)
    | _, _, _ => .error "noMethod"
  | _ => .error "noMethod"

/-- A turn state for compiling outside a turn. -/
def scratchState (w : World) : TurnState :=
  { world := w, principal := "", intent := "", subject := "", ticks := 0, limits := Json.mkObj [] }

/-! ## Spells (WHOLENESS §2, host day 2)

A direct `receive {text, post}` to an object written in the message dialect is read by the host:
the reply's spell (`Spell.parse`) names a card and an action; the card resolves as `Card.names` does
(`resolveCard`) and the turn is retargeted to it; the action is looked up among the card's forms
(`methodForms`) and the fields fitted (`Spell.fit`); a fitting spell runs the method with the typed
argument (`inputOrigin.kind = "spell"`, `command` the spell line). A spell that does not fit is a
refused turn of class `badSpell` with `clause`, `reason` and `hint` (the spell with its blanks). A
spell missing fields, or a reply with no spell, runs `receive` with the bare `name: value` lines in
`Heard.fields` (completion is the object's policy, WHOLENESS's root decision). `?` is answered by
the host with the card's usage and journals nothing. -/

/-- A form's field as the spell a reader copies (`Card.hint`). -/
def spellHint : Spell.Kind → String
  | .text a b => s!"<text, {a} to {b} characters>"
  | .natural a b => s!"<a number from {a} to {b}>"
  | .choice options => s!"<{", ".intercalate options}>"

/-- One form as the spell to send, the fields `given` filled in and the rest shown as blanks. -/
def spellTemplate (card : String) (form : Spell.Form) (given : List Spell.Binding := []) : String :=
  s!"delvetalk {card} {form.action}\n" ++ String.join (form.fields.map fun f =>
    s!"{f.name}: {((given.find? (·.name == f.name)).map (·.value)).getD (spellHint f.kind)}\n")

/-- One lens as the `set` spell a reader copies (`Card.lensTemplate`). -/
def lensTemplate (card : String) (lens : Spell.Field) (value : Option String := none) : String :=
  s!"delvetalk {card} set\n{lens.name}: {value.getD (spellHint lens.kind)}\n"

/-- A card's usage (`Card.help`): every form as a template, then every lens. -/
def spellUsage (card : String) (forms : List Spell.Form) (lenses : List Spell.Field := []) : String :=
  if forms.isEmpty && lenses.isEmpty then s!"{card} takes no spells; reply in words and the directory places them." else
  (if forms.isEmpty then "" else "Reply with a spell:\n" ++ String.join (forms.map fun f => "\n" ++ spellTemplate card f)) ++
  (if lenses.isEmpty then "" else
    "\nTo set a field, reply with one of these (one field a spell):\n" ++ String.join (lenses.map fun l => "\n" ++ lensTemplate card l))

/-- The spell line a reply's spell stands on, for `inputOrigin.command`. -/
def spellLine (card action : String) : String := s!"delvetalk {card} {action}"

/-- A fitted spell's typed argument: the form's fields in order, text as text, a natural as a
    natural, a choice as the variant of that name with an empty payload. -/
def spellArgument (entries : List Spell.Entry) : Data :=
  .record (entries.map fun e => (e.name, match e.value with
    | .text t => .label t
    | .natural n => .natural n
    | .choice c => .label c))

/-- A spell's argument for `method` of `o`: a choice is a word, read as the case of that name where
    the method's input has a closed sum there (`inputWords`), and kept as text where it takes text (a
    form may offer choices for a `String`). `none` when a word names no case of the type. -/
def spellArgumentFor (w : World) (o : Object) (method : String) (entries : List Spell.Entry) : Except String Data :=
  let argument := spellArgument entries
  match ((compiledMethod o method).run.run (scratchState w)).1 with
  | .ok c => match inputWords c argument with
    | .ok a => .ok a
    | .error (path, word, cases) => .error s!"{path} is one of: {", ".intercalate cases} (not {word})"
  | .error _ => .ok argument

def bindingsData (bs : List Spell.Binding) : Data :=
  listData (bs.map fun b => .record [("name", .label b.name), ("value", .label b.value)])

/-- `receive`'s argument with the bare field lines added when the method declares `fields`. -/
def withFields (w : World) (o : Object) (argument : Data) (fields : List Spell.Binding) : Data :=
  match argument with
  | .record fs =>
    let candidate := Data.record (fs.filter (·.1 != "fields") ++ [("fields", bindingsData fields)])
    match ((compiledMethod o "receive").run.run (scratchState w)).1 with
    | .ok c => if argumentFits c candidate then candidate else argument
    | .error _ => argument
  | other => other

/-- Does a `receive` argument fit the card's own `receive` input, with or without the `fields` the
    host fills? A reply carrying another field (a forged `who`) is not read as a spell: `receive`
    runs as asked and its type refuses it (`typeMismatch`), as any other method's would. -/
def heardFits (w : World) (o : Object) (argument : Data) : Bool :=
  match argument, ((compiledMethod o "receive").run.run (scratchState w)).1 with
  | .record fs, .ok c =>
    argumentFits c argument || argumentFits c (.record (fs.filter (·.1 != "fields") ++ [("fields", bindingsData [])]))
  | _, _ => false

/-- `formsOf` outside a turn. -/
def spellFormsData (w : World) (id : String) (o : Object) : List Data :=
  ((formsOf id o).run.run (scratchState w)).1.toOption.getD (methodForms id o.methods)

/-- The forms a card offers, as the spell grammar reads them. -/
def spellForms (w : World) (id : String) (o : Object) : List Spell.Form :=
  (spellFormsData w id o).filterMap Spell.Form.ofData

/-- The lenses of a card (WHOLENESS §2: a lens is a form): the fields its pure `lenses() ->
    Lists.List<Form.Field>` names, each with the kind of value it takes, when it also has a `set`
    method; none otherwise (also when `lenses()` is the sum dialect's list of `Form.Lens`, which is
    not data). -/
def declaredLenses (w : World) (o : Object) : List Spell.Field :=
  if !hasMethod o "set" || !((entrySource o).splitOn "\n").any (·.startsWith "def lenses(") then [] else
  let read : M (List Spell.Field) := do
    let some c ← tryCatch (some <$> compiledMethod o "lenses") (fun _ => pure none) | return []
    let some entry := c.entry | return []
    match (runPure entry [] Delvetalk.Bounds.lawTicks).1 with
    | .ok d =>
      let form := Spell.Form.ofData (.record [("card", .label ""), ("action", .label "set"), ("fields", d)])
      return (form.map (·.fields)).getD []
    | .error _ => return []
  match (read.run.run (scratchState w)).1 with
  | .ok ls => ls
  | .error _ => []

/-- A lens's value as the `set` method takes it: `Form.Value`. -/
def lensValue : Spell.Value → Data
  | .text t => .variant "text" (.record [("value", .label t)])
  | .natural n => .variant "natural" (.record [("value", .natural n)])
  | .choice c => .variant "choice" (.record [("value", .label c)])

/-- What the host makes of a `receive {text, …}` asked of a card of the message dialect (`routeSpell`). -/
inductive SpellRoute where
  /-- Not a spell the host reads: run `receive` as asked. -/
  | asIs
  /-- Run `method` of `object` with `argument`; `command` is the spell line when the spell named the
      method (the turn's `inputOrigin.kind` is then `spell`), "" when it is `receive` with the bare fields. -/
  | run (object method : String) (argument : Data) (command : String)
  | usage (object text : String)
  | refuse (object clause reason hint : String)

/-- `receive` with the bare field lines (`Heard.fields`): completion is the card's policy. -/
def receiveHeard (w : World) (id : String) (o : Object) (argument : Data) (fields : List Spell.Binding) : SpellRoute :=
  .run id "receive" (withFields w o argument fields) ""

/-- `delvetalk <card> set` with one `<field>: <value>` line: the value is judged against the lens's
    kind (`badValue`) and the card's `set {field, value: Form.Value}` method runs with it
    (`inputOrigin.kind = "spell"`). No field line is completion, the card's policy (`receive` with the
    bare fields); a field no lens names, or more than one, is `unknownField`. -/
def lensSpell (w : World) (id : String) (argument : Data) (target : Object) (card : String) (lenses : List Spell.Field)
    (fields : List Spell.Binding) : SpellRoute :=
  match fields with
  | [] => receiveHeard w id target argument fields
  | [b] =>
    match lenses.find? (·.name == b.name) with
    | none => .refuse id "unknownField"
        s!"No field {b.name} in this spell; it takes {", ".intercalate (lenses.map (·.name))}." (spellUsage id [] lenses)
    | some lens =>
      match Spell.judge lens b.value with
      | some (clause, reason) => .refuse id clause.name reason (lensTemplate id lens b.value)
      | none =>
        .run id "set" (.record [("field", .label lens.name), ("value", lensValue (Spell.typed lens.kind b.value))]) (spellLine card "set")
  | _ => .refuse id "unknownField"
      s!"set takes one field a spell, not {", ".intercalate (fields.map (·.name))}" (spellUsage id [] lenses)

/-- The first ```obend fenced block of a reply: the lines after the opening fence up to a line that
    starts with ```; none when there is none or it is never closed. -/
def firstFence (text : String) : Option String := Id.run do
  let lines := text.splitOn "\n"
  let some start := lines.findIdx? (fun l => (l.dropWhile (· == ' ')).startsWith "```obend") | return none
  let body := lines.drop (start + 1)
  let some stop := body.findIdx? (fun l => (l.dropWhile (· == ' ')).startsWith "```") | return none
  return some ("\n".intercalate (body.take stop))

/-- A spell's fields with a reply's ```obend block as the value of the form's first `source` field it
    lacks (`Form.Kind.source`): a block and a fenced reply are one value, judged by one bound. -/
def withFence (w : World) (o : Object) (action : String) (argument : Data) (fields : List Spell.Binding) : List Spell.Binding :=
  let sources := ((((declaredForms o).run.run (scratchState w)).1.toOption.map (·.2)).getD []).lookup action |>.getD []
  let text := match argument with
    | .record fs => ((fs.lookup "text").bind labelOf).getD ""
    | _ => ""
  match sources.find? (fun n => !fields.any (·.name == n)), firstFence text with
  | some name, some code => fields ++ [{ name, value := code }]
  | _, _ => fields

/-- What a spell naming `card` and `action` with `fields` asks of card `self` (`o`), read for
    `principal`. `retarget`: a direct turn goes to the card the spell names; a call or a delivery
    reads only spells naming the card it was sent to (another is `otherCard`), since its sender chose
    that object. -/
def castSpell (w : World) (principal self : String) (argument : Data) (o : Object) (card action : String)
    (fields : List Spell.Binding) (retarget : Bool) : SpellRoute := Id.run do
  let id := resolveCard principal card
  let usageHere := spellUsage self (spellForms w self o)
  let some target := w.objects[id]? | return .refuse self "otherCard" s!"There is no card {card}; the directory lists the doors." usageHere
  unless target.read.permits principal && (retarget || id == self) do
    return .refuse self "otherCard" s!"There is no card {card}; the directory lists the doors." usageHere
  let forms := spellForms w id target
  let lenses := declaredLenses w target
  if action == "?" then return .usage id (spellUsage id forms lenses)
  -- `set` with one `<field>: <value>` line goes through a lens (`lensSpell`).
  if action == "set" && !lenses.isEmpty && !forms.any (·.action == "set") then
    return lensSpell w id argument target card lenses fields
  let some form := forms.find? (·.action == action)
    | return .refuse id "noAction" s!"{id} has no spell {action}; it has these:" (spellUsage id forms lenses)
  let fields := withFence w target action argument fields
  match Spell.fit (.spell id action fields) form with
  | .proposal _ _ entries => match spellArgumentFor w target action entries with
    | .ok a => return .run id action a (spellLine card action)
    | .error reason => return .refuse id "badValue" reason (spellTemplate id form fields)
  | .unclear _ => return receiveHeard w id target argument fields
  | .refused clause reason => return .refuse id clause.name reason (spellTemplate id form fields)

/-- A `receive {text, …}` to `id`, read as a spell by the host when the card speaks the message
    dialect (WHOLENESS §2): a direct turn's, a called one's and a delivered one's alike (`retarget`
    only for a direct turn). `asIs` when the host leaves it as asked. -/
def routeSpell (w : World) (principal id method : String) (argument : Data) (retarget : Bool) : SpellRoute := Id.run do
  if method != "receive" then return .asIs
  let .record args := argument | return .asIs
  let some (.label text) := args.lookup "text" | return .asIs
  let some o := w.objects[id]? | return .asIs
  unless heardFits w o argument do return .asIs
  match Spell.parse text with
  | .spell card action fields => return castSpell w principal id argument o card action fields retarget
  | .notASpell reason fielded =>
    if reason.startsWith "The block <<" then
      return .refuse id "unclosedBlock" reason (spellUsage id (spellForms w id o))
    let bare := Spell.bare text
    -- A reply with no spell line whose first field line names an action or a field of one of this
    -- card's forms is that form's spell (`Card.withBare`).
    let first := if fielded then bare.head? else none
    let form := first.bind fun b => (spellForms w id o).find? fun f => f.action == b.name || f.fields.any (·.name == b.name)
    match form with
    | some f =>
      let given := bare.filter fun b => b.name == f.action || f.fields.any (·.name == b.name)
      return castSpell w principal id argument o id f.action given retarget
    | none => return receiveHeard w id o argument bare

mutual
/-- Run `method` of object `id` against its committed state; its result is returned. -/
partial def runMethod (depth : Nat) (id method : String) (argument : Data) (caller : String)
    (subject : String) (via : String := "") (post : Option String := none) : M Data := do
  let outer ← get
  let post := post.getD ((heardPost method argument).getD outer.post)
  set { outer with subject, method, via, argument, post }
  let result ← runFrame depth id method argument caller
  modify fun s => { s with subject := outer.subject, method := outer.method, via := outer.via, argument := outer.argument,
                           post := outer.post }
  return result

/-- The body of `runMethod`, inside the frame it set. -/
partial def runFrame (depth : Nat) (id method : String) (argument : Data) (caller : String) : M Data := do
  let s ← get
  let some obj := s.world.objects[id]? | evaluation s!"unknown object {id}"
  -- Only a method the package makes public is asked from outside (a call or a run checked it).
  if depth == 0 && !s.receiver && !obj.offers method then throw (.refused "noMethod" (noMethodReason id method))
  recordRoot id obj.version
  let compiled ← compiledMethod obj method
  let expected := expectedInput obj id method compiled
  -- A direct turn's argument came from outside: its text words are read as cases.
  let argument ← if depth == 0 && s.direct then
      match inputWords compiled argument with
      | .ok a => do modify (fun st => { st with argument := a }); pure a
      | .error (path, word, cases) =>
        throw (.refused "typeMismatch" (wordRefusal path word cases)
          (some (expected.setObjVal! "cases" (Json.mkObj [("at", toJson path), ("given", toJson word), ("cases", toJson cases)]))))
    else pure argument
  let context := contextData id s.subject (handleOf s.world s.subject) caller s.intent s.world.height s.world.clock
    (if depth == 0 then s.origin else "call") (if depth == 0 && !s.command.isEmpty then s.command else method) s.post
  let (arguments, r) ← match compiled.type with
    | .arrow _ _ _ (.arrow _ _ _ (.arrow _ _ ct r)) => pure ([obj.state, argument, fitRecord compiled.bounds ct context], r)
    | .arrow _ _ _ (.arrow _ _ ct r) => pure ([obj.state, fitRecord compiled.bounds ct context], r)
    | _ => throw (.request s!"method {method} must take (state, [input,] context)")
  unless argumentFits compiled argument do throw (.refused "typeMismatch" argumentRefusal (some expected))
  match r with
  | .computation .. =>
    let b ← budgetsNow
    let binding := Delvetalk.Turn.Binding.make id s.principal s.intent (← get).roots
    let entry ← entryOf compiled
    let started ← kernelRefusal (Delvetalk.Turn.startEntryStep entry arguments binding b compiled.dictionary) (some expected)
    noteProfile fun _ => (Delvetalk.Turn.prepareStartEntry entry arguments |>.map fun (applied, _) =>
      Delvetalk.Profile.profile ⟨b.heap, b.stack⟩ b.bytes b.ticks (Minidregg.Theory.ObjectiveBendDemandMachine.initial applied.source.term))
    drive depth id caller compiled binding started 0
  | _ =>
    unless r.isDataUnder compiled.bounds compiled.rigid Ty.dataFuel [] do throw (.request s!"method {method} must be pure data or an activity")
    let st ← get
    let lim := st.limits.setObjVal! "ticks" (toJson (toString st.ticks))
    -- The held entry, as cards run: no packet decode or re-check per call.
    let entry ← entryOf compiled
    match Package.executeDataEntry entry arguments.toArray lim with
    | .error e => evaluation e
    | .ok (.refused failure usage) =>
      spend (usage.ticksUsed + usage.conversionNodes)
      evaluation failure
    | .ok (.finished value _ _ usage) =>
      spend (usage.ticksUsed + usage.conversionNodes)
      let .record fields := value | evaluation "a pure method must return the state record"
      addWrite id caller (fields.map fun (k, v) => (⟨k, .set v⟩ : Edit))
      return value

partial def drive (depth : Nat) (self caller : String) (compiled : Compiled) (binding : Delvetalk.Turn.Binding)
    (outcome : Delvetalk.Turn.Step) (_n : Nat) : M Data := do
  match outcome with
  | .finished value _ used => spend used; return value
  | .exhausted resource used =>
    spend used
    throw (.budget resource)
  | .yielded message _ responseType suspension used =>
    spend used
    countPlan
    -- A message activity calls the world by method name.
    let plan ← match messagePlan self message with
      | .ok p => pure p
      | .error clause => pure (.variant "refusedMessage" (.record [("clause", .label clause)]))
    let response ← match plan with
      | .variant "refusedMessage" (.record f) =>
        refusedWith compiled.bounds responseType (((f.lookup "clause").bind labelOf).getD "noMethod")
      | .variant "await" (.record f) | .variant "awaitUntil" (.record f) => awaitPlan depth self compiled.bounds f responseType suspension.checkpoint
      | .variant "awaitPost" (.record f) | .variant "awaitPostUntil" (.record f) => awaitPostPlan depth self compiled.bounds f responseType suspension.checkpoint
      | .variant "interpret" (.record f) => interpretPlan depth self compiled.bounds f responseType suspension.checkpoint
      | _ => do
        -- A frame in the extent of a `run` (its callee, or any frame that callee calls) offers each
        -- Plan to the handlers around it, innermost first; a `pass` goes to the next one out, and
        -- the host answers what every one passed.
        let mut handled : Option Data := none
        for (installed, handler) in (← get).handlers do
          if handled.isNone && installed ≤ depth then
            handled ← handleWith handler self message compiled.bounds responseType
        match handled with
        | some response => pure response
        | none => answer depth self caller compiled.bounds plan responseType
    let b ← budgetsNow
    let entry ← entryOf compiled
    -- A yield held in this process resumes from its machine state; no checkpoint is made.
    let next ← liftEval (Delvetalk.Turn.resumeSuspended entry suspension binding response b)
    noteProfile fun _ => (Delvetalk.Turn.prepareResumeEntry entry suspension.checkpoint binding response |>.map fun (_, _, _, _, st, resumed) =>
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

/-- `awaitPost {post, patience}` / `awaitPostUntil {post, until}`: wait for the reply that answers
    `post`, the first turn on the post's recorded object whose `replyTo` names it (`World.replies`);
    answered `reply {receipt}` of that turn once it settles, or `timedOut` by the clock. -/
partial def awaitPostPlan (depth : Nat) (self : String) (bounds : DataBounds) (f : List (String × Data))
    (responseType : Ty) (checkpoint : Delvetalk.Turn.Checkpoint) : M Data := do
  let some post := (f.lookup "post").bind labelOf | evaluation "malformed awaitPost plan"
  if post.isEmpty || post.utf8ByteSize > Limits.maxUriBytes then evaluation "awaitPost names no post"
  let s ← get
  let patience ← match f.lookup "until", f.lookup "patience" with
    | some (.natural height), _ => pure (height - s.world.clock)
    | none, some (.natural patience) => pure patience
    | _, _ => evaluation "malformed awaitPost plan"
  let key := "post:" ++ post
  if s.awaited.contains key then respond bounds responseType "broken" [emptyRecord]
  else if s.awaits ≥ Limits.awaitsPerTurn then evaluation "turn exceeds the await capacity"
  else
    set { s with awaited := s.awaited ++ [key], awaits := s.awaits + 1 }
    let answered := s.world.replies[post]?
    if answered == some (s.principal, s.intent) then respond bounds responseType "broken" [emptyRecord] else
    match answered.bind fun (sp, si) => settled s.world sp si with
    | some entry => respond bounds responseType "reply" [.record [("receipt", receiptData entry)]]
    | none =>
      if patience == 0 then respond bounds responseType "timedOut" [emptyRecord]
      else if patience > Limits.maxPatience then evaluation "await patience exceeds its capacity"
      else
        mayWait depth self checkpoint
        throw (.suspend "" "" patience checkpoint none (some post))

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
  -- The model to ask instead of the policy's own (a card's second attempt names the escalate model).
  let model := ((f.lookup "model").bind labelOf).getD ""
  if model.utf8ByteSize > Limits.maxPrincipalBytes then evaluation "interpret model exceeds its byte capacity"
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
      -- Interpretations the turn's principal may start this clock hour (`interpretQuota`); the
      -- opener and the clock principal are exempt.
      let w := s.world
      let hour := w.clock / 60
      let used := match w.interpretsStarted[s.principal]? with
        | some (h, n) => if h == hour then n else 0
        | none => 0
      unless s.principal == w.opener || s.principal == w.clockPrincipal || used < w.interpretQuota do
        throw (.quota s!"the interpreter has read {w.interpretQuota} this hour; reply with the spell itself, or wait." ((hour + 1) * 60))
      mayWait depth self checkpoint (interpreting := true)
      let id := Journal.bodyHash (Json.arr #[toJson s.principal, toJson s.intent, toJson s.awaits])
      set { s with awaits := s.awaits + 1 }
      throw (.suspend interpretationPrincipal id Limits.interpretationPatience checkpoint
        (some (Json.mkObj ([("id", toJson id), ("object", toJson self), ("policy", toJson policy),
          ("utterance", toJson utterance), ("offers", dataJson offers)] ++
          (if model.isEmpty then [] else [("model", toJson model)])))))

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
    -- Only `callVia` names a grant; a `call` carrying `via` is a plain call.
    let via := match plan with
      | .variant "callVia" _ => ((f.lookup "via").bind labelOf).getD ""
      | _ => ""
    match referenceId target with
    | none => refusedWith bounds responseType "unknownObject"
    | some id =>
      if !(← get).world.objects.contains id then refusedWith bounds responseType "unknownObject"
      else if helperOf (← get).world self id method then refusedWith bounds responseType "noMethod"
      else if depth + 1 > Limits.maxCallDepth then evaluation "call depth exceeded"
      else match ← grantFor via self id method argument with
        | .error clause => refusedWith bounds responseType clause
        | .ok (subject, argument) => do
          -- A called `receive` to a card of the message dialect is read as a spell, as a direct
          -- turn's is (never under a grant: it names the one method it may run).
          let world := (← get).world
          let heard := heardPost method argument
          let route := if via.isEmpty then routeSpell world subject id method argument false else .asIs
          let (method, argument, refusal) := match route with
            | .run _ m a _ => (m, a, none)
            | .refuse _ clause _ _ => (method, argument, some clause)
            | _ => (method, argument, none)
          if let some clause := refusal then refusedWith bounds responseType clause else
          if helperOf (← get).world self id method then refusedWith bounds responseType "noMethod" else
          let some calleeObj := (← get).world.objects[id]? | refusedWith bounds responseType "unknownObject"
          let callee ← compiledMethod calleeObj method
          if !argumentFits callee argument then refusedWith bounds responseType "typeMismatch" else
          spendGrant via
          let result ← runMethod (depth + 1) id method argument self subject via heard
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
        else if helperOf s.world self id method then refusedWith bounds responseType "noMethod"
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
    modify fun s => { s with world := s.world.withCachesOf w }
    let p : Proposal := { principal := s.principal, intent := s.intent, roots := s.roots, writes,
                          programs := s.programs, layered := s.layered, laws := s.laws, absent := s.absent,
                          creates := s.creates, grants := s.grants, revokes := s.revokes, spent := s.spent,
                          subscribes := s.subscribes, unsubscribes := s.unsubscribes, fieldRoots := s.fieldRoots,
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
        -- Another object's law is asked now, so the proposer never hears `reprogrammed` in a turn
        -- whose commit that law refuses.
        -- The verdict depends on the target as read: it is a root whatever the answer.
        recordRoot id o.version
        let world := cacheProgram s.world o source migration prog extend
        let change : Proposal := { principal := s.principal, intent := s.intent, roots := [], writes := [],
                                   programs := [(id, (source, migration))], layered := if extend then [id] else [] }
        match dryChange world s self id o.version proposer 1 change with
        | some clause => refusedWith bounds responseType clause
        | none =>
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
        let change : Proposal := { principal := s.principal, intent := s.intent, roots := [], writes := [], laws := [(id, text)] }
        match dryChange s.world s self id o.version proposer 2 change with
        | some clause => refusedWith bounds responseType clause
        | none =>
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
          [.record (shown ++ [("methods", listData (← formsOf id o))]), .record shown]
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
  | .variant "viewField" (.record f) =>
    -- One field of another object's state (RELATIONAL §6), answered `viewed {version, state}` when the
    -- field's value conforms to the reader's type at the call site (any value does at `Data`).
    let s ← get
    let some name := (f.lookup "field").bind labelOf | evaluation "malformed viewField plan"
    match (f.lookup "object").bind referenceId >>= fun id => (s.world.objects[id]?).map (id, ·) with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some (id, o) =>
      if !o.read.permits s.subject then respond bounds responseType "denied" [emptyRecord] else
      -- The turn read this field alone: only a later write of it makes the turn stale.
      recordFieldRoot id name o.version
      match o.state with
      | .record fields => match fields.lookup name with
        | some value =>
          let d := Data.variant "viewed" (.record [("version", .natural o.version), ("state", value)])
          if d.conformsUnder bounds responseType then return d else refusedWith bounds responseType "typeMismatch"
        | none => refusedWith bounds responseType "field"
      | _ => refusedWith bounds responseType "field"
  | .variant "subscribe" (.record f) | .variant "unsubscribe" (.record f) =>
    -- A standing request for `changed` deliveries (WHOLENESS §3): the subscriber is the running
    -- object, the principal the frame's subject, who must be permitted to view the object.
    let s ← get
    let some name := (f.lookup "field").bind labelOf | evaluation "malformed subscribe plan"
    -- The receiver: a method of the subscriber that the change is delivered to (`changed` by default).
    let receiver := ((f.lookup "method").bind labelOf).getD ""
    let receiver := if receiver.isEmpty then "changed" else receiver
    let ending := match plan with
      | .variant "unsubscribe" _ => true
      | _ => false
    match (f.lookup "object").bind referenceId >>= fun id => (s.world.objects[id]?).map (id, ·) with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some (id, o) =>
      if !o.read.permits s.subject then respond bounds responseType "denied" [emptyRecord] else
      let has := match o.state with
        | .record fields => fields.any (·.1 == name)
        | _ => false
      if !has then refusedWith bounds responseType "field" else
      let x : Subscription := { subscriber := self, principal := s.subject, object := id, field := name, method := receiver }
      let standing := ((s.world.subscriptions.getD id #[]).toList.filter (!s.unsubscribes.contains ·))
      let mine := (standing ++ s.subscribes).filter x.sameAs
      if ending then
        set { s with subscribes := s.subscribes.filter (!mine.contains ·),
                     unsubscribes := s.unsubscribes ++ (mine.filter (standing.contains ·)) }
        respond bounds responseType "subscribed" [emptyRecord]
      else if mine.contains x then respond bounds responseType "subscribed" [emptyRecord]
      else if !(Minidregg.Compiler.ObjectiveBendParse.isIdent receiver.toList) ||
          !(((s.world.objects[self]?).map (hasMethod · receiver)).getD false) then
        refusedWith bounds responseType "method"
      else if mine.isEmpty && ((standing ++ s.subscribes).filter (·.object == id) |>.length |> (· ≥ Limits.subscribersPerObject)) then
        refusedWith bounds responseType "subscribers"
      else
        -- Another receiver for the same field replaces the standing one.
        set { s with subscribes := s.subscribes.filter (!mine.contains ·) ++ [x],
                     unsubscribes := s.unsubscribes ++ (mine.filter (standing.contains ·)) }
        respond bounds responseType "subscribed" [emptyRecord]
  | .variant "viewAt" (.record f) =>
    -- A past version of an object's state, rebuilt from the journal (`stateAt`), answered as `view`
    -- answers the present one; the root is the object as it is NOW, so a turn that read history
    -- still conflicts with what changed since.
    let s ← get
    let some version := (f.lookup "version").bind fun | .natural n => some n | _ => none
      | evaluation "malformed viewAt plan"
    match (f.lookup "object").bind referenceId >>= fun id => (s.world.objects[id]?).map (id, ·) with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some (id, o) =>
      if !o.read.permits s.subject then respond bounds responseType "denied" [emptyRecord] else
      recordRoot id o.version
      match stateAt s.world id version with
      | some state => respond bounds responseType "viewed" [.record [("version", .natural version), ("state", state)]]
      | none => refusedWith bounds responseType "version"
  | .variant "viewDerived" (.record f) =>
    -- A view the target's package derives from its state, as first-order Data, under read
    -- authority; the root is recorded as for `view`.
    let s ← get
    let some view := (f.lookup "view").bind labelOf | evaluation "malformed viewDerived plan"
    match (f.lookup "object").bind referenceId >>= fun id => (s.world.objects[id]?).map (id, ·) with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some (id, o) =>
      if !o.read.permits s.subject then respond bounds responseType "denied" [emptyRecord] else
      recordRoot id o.version
      let context := contextData id s.subject (handleOf s.world s.subject) self s.intent s.world.height s.world.clock "view" view s.post
      match ← derivedView o view context with
      | .ok value => respond bounds responseType "derived" [.record [("version", .natural o.version), ("value", value)]]
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
    let some named := referenceId target | refusedWith bounds responseType "foreignWorld"
    -- An empty `requireAbsent` asks the host to mint the child's id.
    let id ← if named.isEmpty then mintId self package else pure named
    let s ← get
    let note := fun (s : TurnState) => { s with absent := if s.absent.contains id then s.absent else s.absent ++ [id] }
    if !validObjectId id || id == "self" || ownCards.contains id then
      refusedWith bounds responseType "objectId"
    else if s.world.objects.contains id || s.creates.any (·.1 == id) then
      -- The reply says so now; the turn will be refused at its commit, naming the root.
      set { note s with violation := s.violation.orElse (fun _ => some id),
                        violator := if s.violation.isSome then s.violator else self }
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
    -- Only `sendVia` names a grant.
    let via := match plan with
      | .variant "sendVia" _ => ((f.lookup "via").bind labelOf).getD ""
      | _ => ""
    match referenceId target with
    | none => refusedWith bounds responseType "foreignWorld"
    | some id =>
      if helperOf (← get).world self id method then refusedWith bounds responseType "noMethod" else
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
def turnReply (_w : World) (r : Json) : Json :=
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
      (if tagOf entry == "refused" then [("public", publicRefusal entry)] else []))

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
  /-- This turn re-runs one whose resumption was refused `staleRoot` (`resumeOne`). -/
  rerun : Bool := false
  /-- A delivery to a receiver the object chose itself (`TurnState.receiver`). -/
  receiver : Bool := false

def ledgerJson (l : Ledger) : Json := l.json

/-- The sends of an admitted turn, each with the ledger it inherits: depth - 1,
    work - the ticks this turn used, storage - the bytes its writes added. -/
def sendsJson (w : World) (principal intent : String) (ledger : Ledger) (used : Nat)
    (sends : List Send) (updates : List (String × Object)) : List (String × Json) :=
  if sends.isEmpty then [] else
  let child := childLedger w ledger used updates
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
  /-- The recorded post this direct turn answers (journaled as `replyTo`), "" for none. -/
  answers : String := ""
  /-- The turn re-runs a stale resumption (journaled as `rerun: true`, and so never re-run again). -/
  rerun : Bool := false


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
    (ctx.resumes.map fun h => [("resumes", toJson h)]).getD [] ++
    (if ctx.answers.isEmpty then [] else [("replyTo", toJson ctx.answers)]) ++
    (if ctx.rerun then [("rerun", toJson true)] else [])

/-- End a segment of a turn: commit it, refuse it, or journal its suspension. -/
def finishTurn (w : World) (ctx : Ctx) (result : Except Abort Data) (st : TurnState) :
    Except String (World × Json) := do
  let w := w.withCachesOf st.world
  let used := ctx.usedBefore + (ctx.ticksStart - st.ticks)
  let proposal : Proposal :=
    { principal := ctx.principal
      intent := ctx.intent
      roots := st.roots
      rebaseOwn := if ctx.resumes.isSome then some ctx.object else none
      writes := st.writes
      turn := w.height + 1
      programs := st.programs
      layered := st.layered
      laws := st.laws
      absent := st.absent
      creates := st.creates
      grants := st.grants
      revokes := st.revokes
      spent := st.spent
      subscribes := st.subscribes
      unsubscribes := st.unsubscribes
      fieldRoots := st.fieldRoots }
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
  | .error (.refused cls reason expected) =>
    let (w', r) := commit w { proposal with writes := [], creates := [] } base
      (some { cls, reason := some reason, object := some ctx.object, expected }) (onEnd := endedIfLate)
    return (w', turnReply w' r)
  | .error (.quota reason next) =>
    let (w', r) := commit w { proposal with writes := [], creates := [] } base
      (some { cls := "quota", reason := some reason, next := some next })
    return (w', turnReply w' r)
  | .error (.suspend sp si patience checkpoint interpretation post) =>
    let interpretation := interpretation.map (compactInterpretation · ctx.argument)
    -- An argument's long texts are blocks, the same the checkpoint holds them in (`activityArgument`
    -- restores them): a reply's text is journaled once.
    let (hoisted, argumentBlocks) := hoistLabels (dataJson ctx.argument)
    let argument := Json.mkObj [("argument", hoisted)]
    let journaledCheckpoint := compactCheckpoint w checkpoint.toJson
      [("object", ctx.object), ("principal", ctx.principal), ("intent", ctx.intent)]
      (((interpretation.map (·.2)).getD #[]) ++ argumentBlocks)
    let interpretation := interpretation.map (·.1)
    -- Only what the activity holds: an empty or zero field is left out (`activityArray`,
    -- `activityNat` read it back), and the roots are the entry's own.
    let activity := Json.mkObj <| (([("object", toJson ctx.object), ("method", toJson ctx.method)] ++
      ((argument.getObj?.toOption.map (·.toList)).getD []) ++ [
      ("checkpoint", journaledCheckpoint.1),
      ("absent", toJson st.absent),
      ("writes", writesJson st.writes), ("sends", Json.arr (st.sends.toArray.map sendJson)),
      ("creates", Json.arr (st.creates.toArray.map fun (id, c) => createRecJson id c)),
      ("extends", toJson st.layered),
      ("programs", Json.arr (st.programs.toArray.map fun (id, (src, mig)) => Json.mkObj
        [("object", toJson id), ("source", toJson src), ("migration", toJson mig)])),
      ("laws", Json.arr (st.laws.toArray.map fun (id, text) => Json.mkObj [("object", toJson id), ("law", toJson text)])),
      ("ticks", toJson st.ticks), ("awaited", toJson st.awaited), ("awaits", toJson st.awaits),
      ("offers", offersJson st.offers), ("publishes", Json.arr st.publishes.toArray), ("caller", toJson ctx.caller), ("checks", toJson st.checks),
      ("grants", Json.arr (st.grants.toArray.map Grant.json)), ("revokes", toJson st.revokes),
      ("subscribes", Json.arr (st.subscribes.toArray.map (·.json))), ("unsubscribes", Json.arr (st.unsubscribes.toArray.map (·.json))),
      ("spent", spentJson st.spent)] ++
      (if st.post.isEmpty then [] else [("post", toJson st.post)]) ++
      (if st.origin == "request" then [] else [("origin", toJson st.origin), ("command", toJson st.command)]) ++
      (if st.violation.isSome then [("violation", toJson st.violation), ("violator", toJson st.violator)] else [])).filter
        fun (k, v) => k == "ticks" || !(v == Json.arr #[] || v == toJson "" || v == toJson (0 : Nat)))
    -- A post await names the post; the slot it settles on is whichever reply answers it.
    let waitsOn := match post with
      | some p => ("post", toJson p)
      | none => ("slot", Json.mkObj [("principal", toJson sp), ("intent", toJson si)])
    let outcome := Json.mkObj <| [("tag", toJson "suspended"), waitsOn,
      ("deadline", toJson (w.clock + patience)), ("activity", activity)] ++
      (interpretation.map fun i => [("interpretation", i)]).getD []
    let (w', entry) := push w (identityKey ctx.principal ctx.intent)
      ([("identity", identityJson ctx.principal ctx.intent), ("roots", allRootsJson st.roots st.fieldRoots),
        ("turn", toJson proposal.turn), ("request", toJson ctx.digest)] ++ base ++ [("outcome", outcome)] ++
        newSources w (st.creates.flatMap fun (_, c) => inputSources c.object.inputs) ++ journaledCheckpoint.2) []
    return (w', turnReply w' (reply entry))
  | .ok value =>
    match st.violation with
    | some id =>
      let (w', r) := commit w { proposal with writes := [], creates := [] } base
        (some { cls := "requiredAbsence", object := some id,
                root := some (if st.violator.isEmpty then ctx.object else st.violator) }) (onEnd := endedIfLate)
      return (w', turnReply w' r)
    | none =>
    -- A send under a grant leaves only if the grant still stands (a suspension may have outlived it).
    match st.sends.find? fun x => !x.via.isEmpty && (grantStands w x.via x.to x.method).isNone with
    | some x =>
      let (w', r) := commit w { proposal with writes := [], creates := [], grants := [], revokes := [], spent := [], subscribes := [], unsubscribes := [] } base
        (some { cls := "lawRefused", clause := some "noGrant", object := some x.to }) (onEnd := endedIfLate)
      return (w', turnReply w' r)
    | none =>
    let offered := (if st.offers.isEmpty then [] else [("offers", offersJson st.offers)]) ++
      (if st.publishes.isEmpty then [] else [("publishes", Json.arr st.publishes.toArray)]) ++
      (if st.checks == 0 then [] else [("checks", toJson st.checks)])
    let (w', r) := commit w proposal (base ++ [("result", dataJson value)] ++ offered) none
      (fun updates => sendsJson w ctx.principal ctx.intent ctx.ledger used st.sends updates ++
        changesJson w ctx.principal ctx.intent ctx.ledger used st.sends.length updates proposal.allWrites) endedIfLate
    return (w', turnReply w' r)

/-- The door word a card's pure `blurb()` gives (`Card.Door {word, blurb}`), if it has one. -/
def blurbWord (o : Object) : M (Option String) := do
  if !((entrySource o).splitOn "\n").any (·.startsWith "def blurb(") then return none
  let some c ← tryCatch (some <$> compiledMethod o "blurb") (fun _ => pure none) | return none
  let some entry := c.entry | return none
  match (runPure entry [] Delvetalk.Bounds.lawTicks).1 with
  | .ok (.record fs) => return (fs.lookup "word").bind labelOf
  | _ => return none

/-- `publishPage {page}` asked of a card whose package declares no `publishPage` (WORLD-REVIEW
    finding 16): the host publishes the card's default page as `Card.defaultPage` wrote it, the card as
    a stranger sees it and how to reply (the host's usage of its forms and lenses), under `page`, else
    the door word `blurb()` gives, else the object's id. The result is the post id, as
    `Card.publishPage`'s. -/
def defaultPublishPage (id : String) (argument : Data) : M Data := do
  let s ← get
  let some o := s.world.objects[id]? | evaluation s!"unknown object {id}"
  recordRoot id o.version
  let given := match argument with
    | .record fs => ((fs.lookup "page").bind labelOf).getD ""
    | _ => ""
  let word := (← blurbWord o).getD id
  let title := if given.isEmpty then word else given
  let card ← match ← renderCard o (fun m => cardContext s.world id "" "" s.intent s.world.height m) with
    | .ok doc => liftEval (Delvetalk.Document.render doc)
    | .error clause => evaluation s!"publishPage: the card does not render ({clause})"
  let usage := spellUsage id (spellForms s.world id o) (declaredLenses s.world o)
  let body := s!"## Card\n\n{card}\n## How to reply\n\n{usage}"
  if title.utf8ByteSize > Limits.maxTitleBytes || title.any (· == '\n') then evaluation "publishPage: the title is not one line of at most 256 bytes"
  if body.utf8ByteSize > Delvetalk.Document.maxOutputBytes then evaluation "publishPage: the page exceeds its capacity"
  let s ← get
  let post := Journal.bodyHash (Json.arr #[toJson "publish", toJson s.principal, toJson s.intent, toJson s.publishes.length])
  set { s with publishes := s.publishes ++ [Json.mkObj [("id", toJson post), ("object", toJson id),
    ("page", toJson title), ("section", toJson ""), ("text", toJson s!"wiki: {title}\n\n{body}")]] }
  return .label post

/-- One turn: drive the method, then one `commit`. Request errors (unknown method,
    wrong arity) journal nothing, except for a delivery, which must be consumed. -/
def runTurnWith (w : World) (req : TurnRequest) (how : TurnMeta) : Except String (World × Json) := do
  if let some r := retainedTurn w req then return (w, r)
  let ledger := how.ledger.getD ((w.objects[req.object]?).map (·.chain) |>.getD Ledger.start)
  let ticks ← match Delvetalk.Turn.budgets req.limits with
    | .ok b => pure b.ticks
    | .error e => throw e
  let init : TurnState := { world := w, principal := req.principal, intent := req.intent, subject := req.principal,
                            direct := how.delivery.isNone, receiver := how.receiver, ticks, limits := req.limits, profiling := req.profile,
                            origin := req.origin, command := req.command,
                            post := if req.post.isEmpty then (heardPost req.method req.argument).getD "" else req.post }
  -- A reply to a post recorded for this very object answers it (reply-is-address).
  let post := if req.replyTo.isEmpty then none else w.posts[req.replyTo]?
  let answers := match post with
    | some p => if p.object == req.object then req.replyTo else ""
    | none => ""
  -- A card that declares no `publishPage` has the host's default page (`defaultPublishPage`).
  let byHost := req.method == "publishPage" && how.delivery.isNone &&
    ((w.objects[req.object]?).map (!hasMethod · "publishPage")).getD false
  let action := if byHost then defaultPublishPage req.object req.argument
    else runMethod 0 req.object req.method req.argument how.caller req.principal how.via
  let (result, st) := (action.run).run init
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
      via := how.via
      answers
      rerun := how.rerun }
  let (w', r) ← finishTurn w ctx result st
  return (w', if req.profile then r.setObjVal! "profile" (profileJson st.profile) else r)

/-- Journal a `badSpell` refusal of the turn as asked (its identity binds, so a resend is a new
    turn). -/
def refuseSpell (w : World) (req : TurnRequest) (object clause reason hint : String) : Except String (World × Json) := do
  let ctx : Ctx := { principal := req.principal, intent := req.intent, object := req.object, method := req.method,
                     argument := req.argument, digest := req.digest, ledger := Ledger.start, delivery := none,
                     ticksStart := 0 }
  let p : Proposal := { principal := req.principal, intent := req.intent, roots := [], writes := [], turn := w.height + 1 }
  let (w', r) := commit w p (entryBase ctx 0)
    (some { cls := "badSpell", clause := some clause, object := some object, reason := some reason, hint := some hint })
  return (w', turnReply w' r)

/-- A direct turn's `receive` read as a spell (`routeSpell`); `none` when the host leaves the turn as asked. -/
def spellTurn (w : World) (req : TurnRequest) : Option (Except String (World × Json)) :=
  match routeSpell w req.principal req.object req.method req.argument true with
  | .asIs => none
  | .run object method argument command =>
    let asked := { req with object := object, method := method, argument := argument,
                            post := (heardPost req.method req.argument).getD "",
                            origin := (if command.isEmpty then req.origin else "spell"),
                            command := (if command.isEmpty then req.command else command) }
    some (runTurnWith w asked {})
  | .usage object text =>
    some (.ok (w, Json.mkObj [("status", toJson "usage"), ("object", toJson object), ("text", toJson text)]))
  | .refuse object clause reason hint => some (refuseSpell w req object clause reason hint)

/-- A direct turn; `env` and `wake` name the principal's own (`resolveCard`), refused
    `unknownObject` naming `env/<principal>` when it has none. A `receive` to a card of the message
    dialect is read as a spell first (`spellTurn`). -/
def runTurn (w : World) (req : TurnRequest) : Except String (World × Json) :=
  let req := { req with object := resolveCard req.principal req.object }
  match spellTurn w req with
  | some r => r
  | none => runTurnWith w req {}

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
    let target ← liftEval (verdict.getObjValAs? String "object")
    respond bounds responseType "proposal" [.record [("object", .label target), ("method", .label method), ("argument", argument)]]
  | "replied" =>
    respond bounds responseType "replied" [.record [("text", .label (← liftEval (verdict.getObjValAs? String "text")))]]
  | _ =>
    let needs := strings (verdict.getObjVal? "needs").toOption
    respond bounds responseType "unclear" [.record [("needs", listData (needs.map Data.label))]]

/-- A list field of a journaled activity: `[]` when left out (an empty one is not journaled). -/
def activityArray (act : Json) (key : String) : Except String Json :=
  match act.getObjVal? key with
  | .ok v => pure v
  | .error _ => pure (Json.arr #[])

/-- A count of a journaled activity: 0 when left out. -/
def activityNat (act : Json) (key : String) : Except String Nat :=
  match act.getObjVal? key with
  | .ok v => natOf v
  | .error _ => pure 0

/-- Continue the activity a suspension entry journaled. The turn's roots are
    re-validated first: if anything it read or required absent has moved, the whole
    turn is refused `staleRoot` and journaled under its original identity. -/
def resumeSegment (w : World) (sus : Json) (kind : Resume) : Except String (World × Json) := do
  let hash ← sus.getObjValAs? String "hash"
  let identity ← sus.getObjVal? "identity"
  let principal ← identity.getObjValAs? String "principal"
  let intent ← identity.getObjValAs? String "intent"
  let outcome ← sus.getObjVal? "outcome"
  let act ← outcome.getObjVal? "activity"
  let object ← act.getObjValAs? String "object"
  let method ← act.getObjValAs? String "method"
  let argument ← decodeData Limits.dataDepth (← activityArgument w act)
  -- An older journal repeats the roots in the activity; they are the entry's.
  let rootsJson := (act.getObjVal? "roots").toOption.getD ((sus.getObjVal? "roots").toOption.getD (Json.arr #[]))
  let roots ← parseRoots rootsJson
  let fieldRoots ← parseFieldRoots rootsJson
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
      timedOut := match kind with | .timedOut => true | _ => false
      rerun := (sus.getObjValAs? Bool "rerun").toOption.getD false }
  -- A moved root whose staged changes so far all commute may still commit (`judge` decides at the
  -- end); one already changed otherwise cannot, and the turn is refused now.
  let staged ← parseRecordedWrites (← activityArray act "writes")
  let stale? := (roots.find? fun (id, v) => match (w.objects[id]?).map (·.version) with
      | some now => now != v && !(v < now && ((staged.lookup id).isNone || movedRootAdmits w staged id v (id == object)))
      | none => true).map (·.1)
    <|> (absent.find? fun id => w.objects.contains id)
    <|> (fieldRoots.find? fun (id, field, v) => match (w.objects[id]?).map (·.version) with
      | some now => now != v && !(v < now && ((fieldsChangedSince w id v).map (!·.contains field)).getD false)
      | none => true).map (·.1)
  if let some id := stale? then
    let stalled : Proposal :=
      { principal := principal
        intent := intent
        roots := roots
        writes := []
        turn := w.height + 1
        absent := absent }
    let (w', r) := commit w stalled (entryBase ctx ctx.usedBefore) (some { cls := "staleRoot", object := some id })
    return (w', turnReply w' r)
  let writes ← parseRecordedWrites (← activityArray act "writes")
  let sends ← (← (← activityArray act "sends").getArr?).toList.mapM sendOfJson
  let grants ← (((act.getObjVal? "grants").toOption.bind (·.getArr?.toOption)).getD #[]).toList.mapM Grant.ofJson
  let creates ← ((← (← activityArray act "creates").getArr?).toList.mapM fun r => do
    let id ← r.getObjValAs? String "object"
    let seed ← r.getObjVal? "seed"
    let (o, sources) ← buildObject w (← expandInputs w (← r.getObjVal? "compile")) seed (r.getObjVal? "read").toOption
      (r.getObjVal? "chain").toOption principal (w.height + 1) (some (← r.getObjValAs? String "law"))
    let o := { o with supervisor := (r.getObjValAs? String "supervisor").toOption.getD "" }
    return (id, ({ object := o, sources, seed } : CreateRec)))
  let programs ← ((← (← activityArray act "programs").getArr?).toList.mapM fun r => do
    return (← r.getObjValAs? String "object", (← r.getObjValAs? String "source", ← r.getObjValAs? String "migration")))
  let laws ← ((← (← activityArray act "laws").getArr?).toList.mapM fun r => do
    return (← r.getObjValAs? String "object", ← r.getObjValAs? String "law"))
  let checkpoint ← Delvetalk.Turn.Checkpoint.fromJson (← expandSuspended w sus)
  let init : TurnState :=
    { world := w
      roots := roots
      fieldRoots := fieldRoots
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
      subscribes := ((act.getObjVal? "subscribes").toOption.bind (·.getArr?.toOption) |>.getD #[]).toList.filterMap
        fun j => (Subscription.ofJson j).toOption
      unsubscribes := ((act.getObjVal? "unsubscribes").toOption.bind (·.getArr?.toOption) |>.getD #[]).toList.filterMap
        fun j => (Subscription.ofJson j).toOption
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
      violator := (act.getObjValAs? String "violator").toOption.getD ""
      awaited := strings (act.getObjVal? "awaited").toOption
      awaits := ← activityNat act "awaits"
      publishes := (((act.getObjVal? "publishes").toOption.bind (·.getArr?.toOption)).getD #[]).toList
      checks := ← activityNat act "checks"
      post := (act.getObjValAs? String "post").toOption.getD ""
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
    let next ← liftEval (Delvetalk.Turn.resumeEntryStep (← entryOf compiled) checkpoint binding response b compiled.dictionary)
    drive 0 object ctx.caller compiled binding next 0
  let (result, st) := action.run.run init
  finishTurn w ctx result st

/-- Continue a suspended activity. A direct turn whose resumption is refused `staleRoot` (its
    roots moved past what `movedRootAdmits` allows while it waited) is re-run once, at once, from its
    journaled request on the current state: the refusal is transient, so the identity is free, and
    the re-run carries `rerun: true` so a second stale resumption of it is final. -/
def resumeOne (w : World) (sus : Json) (kind : Resume) : Except String (World × Json) := do
  let (w', r) ← resumeSegment w sus kind
  let stale := (r.getObjVal? "receipt").toOption.any fun e =>
    tagOf e == "refused" && ((e.getObjVal? "outcome").toOption.bind (·.getObjValAs? String "class" |>.toOption)) == some "staleRoot"
  if !stale || (sus.getObjVal? "delivery").toOption.isSome || (sus.getObjValAs? Bool "rerun").toOption == some true then
    return (w', r)
  let identity ← sus.getObjVal? "identity"
  let act ← (← sus.getObjVal? "outcome").getObjVal? "activity"
  let req : TurnRequest :=
    { principal := ← identity.getObjValAs? String "principal"
      object := ← act.getObjValAs? String "object"
      method := ← act.getObjValAs? String "method"
      argument := ← decodeData Limits.dataDepth (← activityArgument w act)
      intent := ← identity.getObjValAs? String "intent"
      limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))]
      digest := ← sus.getObjValAs? String "turnRequest"
      replyTo := (sus.getObjValAs? String "replyTo").toOption.getD ""
      -- A spell's re-run is the spell's method again, from the post it was asked from.
      post := (act.getObjValAs? String "post").toOption.getD ""
      origin := (act.getObjValAs? String "origin").toOption.getD "request"
      command := (act.getObjValAs? String "command").toOption.getD "" }
  let (w'', again) ← runTurnWith w' req { rerun := true }
  let staleHash := ((r.getObjVal? "receipt").toOption.bind (·.getObjValAs? String "hash" |>.toOption)).getD ""
  return (w'', again.setObjVal! "rerunOf" (toJson staleHash))

/-- The first suspended activity that can go on: its slot settled, or its deadline passed. -/
def pickResumable (w : World) : Option (Json × Resume) :=
  w.suspended.findSome? fun s =>
    let outcome := (s.getObjVal? "outcome").toOption.getD Json.null
    let slot := match (outcome.getObjValAs? String "post").toOption with
      | some post => match w.replies[post]? with
        | some (sp, si) => Json.mkObj [("principal", toJson sp), ("intent", toJson si)]
        | none => Json.mkObj [("principal", toJson ""), ("intent", toJson "")]
      | none => (outcome.getObjVal? "slot").toOption.getD Json.null
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
  let to ← d.getObjValAs? String "to"
  let method ← d.getObjValAs? String "method"
  let senderId := (d.getObjValAs? String "sender").toOption.getD ""
  -- A change goes to the receiver its subscriber named; an activity's end to the supervisor its
  -- object was created under. Either may be a helper: the receiving object chose it.
  let receiver := (d.getObjVal? "field").toOption.isSome ||
    (method == "ended" && ((w.objects[senderId]?).map (·.supervisor)) == some to)
  let how : TurnMeta :=
    { caller := senderId
      via
      ledger := some ledger
      delivery := some (id, sender)
      receiver }
  let deliveryFields := [("ledger", ledger.json), ("delivery", Json.mkObj ([("id", toJson id), ("from", sender)] ++
    (if via.isEmpty then [] else [("via", toJson via)])))]
  -- A send under a grant that no longer stands (revoked, or the clock past it) is consumed, refused.
  if !via.isEmpty && (grantStands w via to method).isNone then
    let p : Proposal := { principal := principal, intent := id, roots := [], writes := [], turn := w.height + 1 }
    return commit w p deliveryFields (some { cls := "lawRefused", clause := some "noGrant", object := some to })
  -- A change is delivered only while its subscription's principal may still view the object; else it
  -- is consumed, refused, and the subscription drops (`subscriptionsAfter`).
  if (d.getObjVal? "field").toOption.isSome then
    if let .ok object := d.getObjValAs? String "object" then
      unless ((w.objects[object]?).map (·.read.permits principal)).getD false do
        let p : Proposal := { principal := principal, intent := id, roots := [], writes := [], turn := w.height + 1 }
        return commit w p deliveryFields (some { cls := "lawRefused", clause := some "denied", object := some object })
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
    -- A delivered `receive` to a card of the message dialect is read as a spell, as a direct turn's
    -- is, against the card it was sent to (not under a grant: that names the one method it may run).
    match if via.isEmpty then routeSpell w principal object method argument false else .asIs with
    | .run _ m a command =>
      runTurnWith w { req with method := m, argument := a, command := command,
                               post := (heardPost method argument).getD "",
                               origin := (if command.isEmpty then req.origin else "spell") } how
    | .refuse card clause reason hint =>
      let p : Proposal := { principal := principal, intent := id, roots := [], writes := [], turn := w.height + 1 }
      return commit w p deliveryFields
        (some { cls := "badSpell", clause := some clause, object := some card, reason := some reason, hint := some hint })
    | _ => runTurnWith w req how

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

/-- The text law's verdict on a kind-0 change by `principal` through `method`, judged on the unchanged
    state (`Facts {subject: principal, caller: "", kind: 0, method, height, turn, pin}`): `true`, or
    `{clause, reading?}` naming the first clause that refuses and reads no state field, whose verdict
    the change cannot alter. A clause that reads the state leaves the verdict to the commit (`true`). -/
def methodAdmits (w : World) (o : Object) (principal method : String) : Json :=
  let facts : Law.Facts := ⟨principal, "", w.height + 1, w.height + 1, o.pin, 0, method, []⟩
  match o.law.find? fun (_, clause) => clause.fields.isEmpty && !Law.admits facts (some o.state) o.state clause with
  | none => Json.bool true
  | some (name, _) => Json.mkObj ([("clause", toJson name)] ++ ((o.readings.lookup name).map fun r => [("reading", toJson r)]).getD [])

/-- The method table as `principal` reads it: each method a turn can run (it takes a context) with
    `admits` (`methodAdmits`). -/
def methodsFor (w : World) (o : Object) (principal : String) : Json :=
  Json.arr ((((publicRows o.methods).getArr?.toOption).getD #[]).map fun m =>
    match (m.getObjValAs? Bool "context").toOption, (m.getObjValAs? String "name").toOption with
    | some true, some name => m.setObjVal! "admits" (methodAdmits w o principal name)
    | _, _ => m)

/-- `world-inspect {principal, object}`: the pin, law text and entry source an object
    shows a reader its read policy permits (`source: false` leaves the source out), and its method
    table with each turnable method's `admits` for the reader. -/
def inspectOp (w : World) (j : Json) : Except String Json := do
  let id ← j.getObjValAs? String "object"
  let principal ← readerOf j
  match w.objects[id]? with
  | none => return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  | some o =>
    if !o.read.permits principal then
      return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
    let withSource ← match j.getObjVal? "source" with
      | .ok (.bool b) => pure b
      | .ok _ => throw "source must be true or false"
      | .error _ => pure true
    return Json.mkObj ([("status", toJson "inspected"), ("object", toJson id), ("pin", toJson o.pin),
      ("pinSlug", toJson ((Slug.ofCid o.pin).getD "")), ("law", toJson o.lawText)] ++
      (if withSource then [("source", toJson (entrySource o))] else []) ++ [("methods", methodsFor w o principal),
      ("supervisor", toJson o.supervisor),
      ("forms", dataJson (listData (spellFormsData w id o)))]) |> fun r =>
      -- The views its package declares (`views()`), which `viewDerived` answers.
      let init : TurnState := { world := w, principal, intent := "", subject := principal,
                                ticks := Delvetalk.Bounds.lawTicks, limits := Json.mkObj [] }
      let views := (((declaredViews o).run.run init).1.toOption).getD []
      if views.isEmpty then r else r.setObjVal! "views" (toJson views)

/-- `world-card {principal, object}`: the object's rendered card, as text and as Document data. -/
def cardOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← readerOf j
  let id := resolveCard principal (← j.getObjValAs? String "object")
  match w.objects[id]? with
  | none => return (w, Json.mkObj [("status", toJson "unknown"), ("object", toJson id)])
  | some o =>
    if !o.read.permits principal then return (w, Json.mkObj [("status", toJson "denied"), ("object", toJson id)])
    let init : TurnState := { world := w, principal, intent := "", subject := principal, ticks := Limits.maxTurnTicks,
                              limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))] }
    let (r, st) := (renderCard o (cardContext w id principal "" "" w.height)).run.run init
    -- The render definition compiled here stays compiled for the next read.
    let w := w.withCachesOf st.world
    match r with
    | .ok (.ok document) =>
      return (w, Json.mkObj [("status", toJson "card"), ("object", toJson id),
        ("text", toJson (← Delvetalk.Document.render document)), ("document", dataJson document)])
    | .ok (.error clause) => return (w, Json.mkObj [("status", toJson "refused"), ("object", toJson id), ("clause", toJson clause)])
    | .error _ => return (w, Json.mkObj [("status", toJson "refused"), ("object", toJson id), ("clause", toJson "render")])

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

/-- A suspension's interpretation, with what it journals by block restored (`expandInterpretation`). -/
def interpretationOf (w : World) (s : Json) : Option Json :=
  (s.getObjVal? "outcome").toOption.bind (expandInterpretation w)

/-- `world-interpretations`: every `interpret` still waiting for a reply. The world returned
    carries only the compiled prompts it cached; nothing is journaled. -/
def interpretationsReply (w : World) : World × Json := Id.run do
  let mut w := w
  let mut pending : Array Json := #[]
  for s in w.suspended do
    let item : Option (String × String × String × Data × String × String) := do
      let i ← interpretationOf w s
      let id ← (i.getObjValAs? String "id").toOption
      guard (settled w interpretationPrincipal id).isNone
      let deadline ← ((s.getObjVal? "outcome").toOption.bind (·.getObjValAs? Nat "deadline" |>.toOption))
      guard (w.clock ≤ deadline)
      let object ← (i.getObjValAs? String "object").toOption
      let policy ← (i.getObjValAs? String "policy").toOption
      let offers ← (i.getObjVal? "offers").toOption.bind fun o => (decodeData Limits.dataDepth o).toOption
      let utterance ← (i.getObjValAs? String "utterance").toOption
      pure (id, object, policy, offers, utterance, (i.getObjValAs? String "model").toOption.getD "")
    let some (id, object, policy, offers, utterance, model) := item | continue
    let (shown, w') := policyJson w policy offers utterance
    -- A model the Plan named takes precedence over the policy's own.
    let shown := if model.isEmpty then shown else shown.setObjVal! "model" (toJson model)
    w := w'
    pending := pending.push (Json.mkObj [("id", toJson id), ("object", toJson object), ("policy", shown),
      ("utterance", toJson utterance), ("offers", plainJson offers)])
  return (w, Json.mkObj [("status", toJson "interpretations"), ("pending", Json.arr pending)])

def abortText : Abort → String
  | .request m | .evaluation m => m
  | .budget r => s!"{r} budget exhausted"
  | .refused cls r _ => s!"{cls}: {r}"
  | .quota r _ => s!"quota: {r}"
  | .suspend .. => "unexpected suspension"

/-- The input type of a method: `none` when it takes none, an error when it is not a method. -/
def inputTypeOf : Ty → Except String (Option Ty)
  | .arrow _ _ _ (.arrow _ _ dom (.arrow _ _ _ _)) => pure (some dom)
  | .arrow _ _ _ (.arrow _ _ _ _) => pure none
  | _ => throw "not a method"

def unclearVerdict (needs : List String) : Json :=
  Json.mkObj [("tag", toJson "unclear"), ("needs", toJson needs)]

/-- A proposal of `method` with `argument` to the suspended object, or `unclear` with the reason: the
    method must be a method of the object, the argument (its text words read as cases) must conform
    to its input, and the suspended activity's response type must carry the proposal. -/
def proposalVerdict (w : World) (target self : String) (obj : Object) (bounds : DataBounds) (responseType : Ty)
    (method : String) (argument : Data) : World × Json := Id.run do
  -- Another object will be called with it: only a method it offers.
  if target != self && !obj.offers method then return (w, unclearVerdict [s!"{method} is not a method {target} offers"])
  let (r, st) := ((compiledMethod obj method).run.run (scratchState w))
  let w := w.withCachesOf st.world
  let compiledM ← match r with
    | .ok c => pure c
    | .error e => return (w, unclearVerdict [s!"{method} is not a method of the object: {abortText e}"])
  let some input := (inputTypeOf compiledM.type).toOption | return (w, unclearVerdict [s!"{method} is not a method"])
  -- The argument came from outside: its text words are read as cases.
  let argument ← match inputWords compiledM argument with
    | .ok a => pure a
    | .error (path, word, cases) =>
      return (w, unclearVerdict [s!"{if path.isEmpty then "the argument" else path} is one of: {", ".intercalate cases} (not {word})"])
  let fits := match input with
    | some dom => argument.conformsUnder compiledM.bounds dom
    | none => match argument with | .record [] => true | _ => false
  if !fits then return (w, unclearVerdict [s!"the argument does not fit the input of {method}"])
  -- A proposal names the object whose form it fitted (`Interpreted.proposal {object, method, argument}`).
  let carried := Data.variant "proposal" (.record [("object", .label target), ("method", .label method), ("argument", argument)])
  unless carried.conformsUnder bounds responseType do
    return (w, unclearVerdict [s!"the object cannot carry a proposal of {target} {method}"])
  return (w, Json.mkObj [("tag", toJson "proposal"), ("object", toJson target), ("method", toJson method),
    ("argument", dataJson argument)])

/-- What a model's text says to a suspended activity of the message dialect, fitted against the
    offered forms as a reply's spell is (WHOLENESS §2, "Interpretation"): a spell naming an offered
    form that fits is that form's proposal; one that misfits, or misses fields, is `unclear` naming
    why or what it needs; a spell naming no offered form is `unclear`. A text with no spell line whose
    first field line names an offered action or field is that form's spell (`Card.withBare`). `none`
    when the text is no spell: the object hears it as `replied`. -/
def spellVerdict (offered : List Spell.Form) (text : String) : Option (Except (List String) (String × String × Data)) :=
  let fitted := fun (form : Spell.Form) (fields : List Spell.Binding) =>
    match Spell.fit (.spell form.card form.action fields) form with
    | .proposal _ action entries => Except.ok (form.card, action, spellArgument entries)
    | .unclear needs => .error needs
    | .refused _ reason => .error [reason]
  match Spell.parse text with
  | .spell card action fields =>
    match offered.find? fun f => f.card == card && f.action == action with
    | some form => some (fitted form fields)
    | none => some (.error [s!"{card} {action} is not one of the offered actions"])
  | .notASpell _ fielded => do
    guard fielded
    let first ← (Spell.bare text).head?
    let form ← offered.find? fun f => f.action == first.name || f.fields.any (·.name == first.name)
    some (fitted form ((Spell.bare text).filter fun b => b.name == form.action || form.fields.any (·.name == b.name)))

/-- What a reply says to the suspended object. A JSON reply `{method, argument}` is a proposal
    (`proposalVerdict`: a method of the object, one of the offered actions, with an argument that
    conforms to the method's input type and fits the object's response type) or `unclear` with the
    reason. Any other reply is the model's text: it is fitted as a spell against the offered forms
    (`spellVerdict`), and prose is `replied {text}`. An object whose Response
    cannot carry it hears `unclear`. A failed call is `unclear {needs: ["model: <reason>"]}`. -/
def interpretVerdict (w : World) (s : Json) (reply : Json) : Except String (World × Json) := do
  let some i := interpretationOf w s | throw "not an interpretation"
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
  let w := w.withCachesOf st2.world
  let offers ← decodeData Limits.dataDepth (← i.getObjVal? "offers")
  let forms := (listHeads [] offers).getD []
  let some method := (json.getObjValAs? String "method").toOption
    | match raw with
      | some text =>
        match spellVerdict (forms.filterMap Spell.Form.ofData) text with
        | some (.ok (card, action, argument)) =>
          -- The form names its card: the proposal is checked against that object, which may be
          -- another than the asking one (a directory offers its doors' forms).
          let principal := ((s.getObjVal? "identity").toOption.bind (·.getObjValAs? String "principal" |>.toOption)).getD ""
          let target := if w.objects.contains card then card else resolveCard principal card
          let some targetObj := w.objects[target]? | return (w, unclearVerdict [s!"there is no card {card}"])
          return proposalVerdict w target object targetObj suspended.bounds responseType action argument
        | some (.error needs) => return (w, unclearVerdict needs)
        | none => pure ()
        if (Data.variant "replied" (.record [("text", .label text)])).conformsUnder suspended.bounds responseType then
          return (w, Json.mkObj [("tag", toJson "replied"), ("text", toJson text)])
        return (w, unclearVerdict ["the reply names no method"])
      | none => return (w, unclearVerdict ["the reply names no method"])
  let actions := forms.filterMap fun form =>
    match form with
    | .record f => (f.lookup "action").bind labelOf
    | _ => none
  if !actions.isEmpty && !actions.contains method then
    return (w, unclearVerdict [s!"{method} is not one of the offered actions"])
  let wanted := match (json.getObjVal? "argument").toOption.getD (Json.mkObj []) with
    | .null => Json.mkObj []
    | other => other
  match Package.jsonData Limits.plainDepth wanted with
  | .error e => return (w, unclearVerdict [s!"the argument is not plain data: {e}"])
  | .ok (argument, _) => return proposalVerdict w object object obj suspended.bounds responseType method argument

/-- `world-interpretation {id, reply}`: settle a pending interpretation with the model's
    reply, verbatim. The verdict is journaled; the suspended turn resumes with it. -/
def interpretationOp (w : World) (j : Json) : Except String (World × Json) := do
  let id ← boundedText "interpretation id" Limits.maxIntentBytes (← j.getObjValAs? String "id")
  let replied ← j.getObjVal? "reply"
  if replied.compress.utf8ByteSize > Limits.maxReplyBytes then throw "reply exceeds its byte capacity"
  let digest := Journal.bodyHash replied
  if let some r := retained w interpretationPrincipal id digest then return (w, r)
  let some s := w.suspended.find? fun s => (interpretationOf w s).bind (·.getObjValAs? String "id" |>.toOption) == some id
    | throw s!"no pending interpretation {id}"
  let (w, verdict) ← interpretVerdict w s replied
  let (w', entry) := push w (identityKey interpretationPrincipal id)
    [("identity", identityJson interpretationPrincipal id), ("roots", rootsJson []),
     ("turn", toJson (w.height + 1)), ("request", toJson digest),
     ("outcome", Json.mkObj [("tag", toJson "interpreted"), ("id", toJson id), ("reply", replied),
       ("verdict", verdict)])] []
  return (w', reply entry)

end Delvetalk.Host
