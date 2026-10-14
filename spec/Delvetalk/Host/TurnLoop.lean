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
import Delvetalk.Host.Surfaces
import Delvetalk.Host.Tongue

namespace Delvetalk.Host
open Lean (Json toJson)
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
open Delvetalk.Theory.ObjectiveBendTypes (Ty DataBounds)
open Delvetalk.Compiler.ObjectiveBendDataWire (dataJson decodeData)

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
  /-- How the words reached the object (docs/FLEX.md §2, HOST-HANDOFF 5.118): as parsed, what the
      transport saw of the post (`statedReaches`); after `runTurn`, `reply` or `spell` when the host
      checked one itself. "" for none: an `interpret` of such a turn is `not addressed`. -/
  reach : String := ""

/-- What a transport may state of a post's reach: a mention or summons of the world, a door's word
    in a thread the world opened, field lines there (checked: the text has one), a turn asked on the
    card itself (its page, the API), or a post that mentions a principal, handed to their avatar
    (`mentioned`: heard as a note, never cast, for its spell lines are the author's own to the cards
    they name). `reply` and `spell` are the host's to find. -/
def statedReaches : List String := ["mention", "door", "fields", "direct", "mentioned"]

/-- The text of a `receive {text, …}`; "" for another method. -/
def heardText (method : String) (argument : Data) : String :=
  if method != "receive" then "" else
  match argument with
  | .record fs => match fs.lookup "text" with
    | some (.label t) => t
    | _ => ""
  | _ => ""

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
  unless Delvetalk.Compiler.ObjectiveBendParse.isIdent method.toList do throw "invalid method name"
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
  let reach := (← optText j "reach").getD ""
  unless reach.isEmpty || statedReaches.contains reach do
    throw s!"reach is one of {", ".intercalate statedReaches}, not {reach}; a reply and a spell line are the host's to find"
  if reach == "fields" && (Spell.bare (heardText method argument)).isEmpty then
    throw "reach fields, but the text has no field line"
  let digest := Journal.bodyHash (Json.mkObj ([("principal", toJson principal), ("object", toJson object),
    ("method", toJson method), ("argument", dataJson argument), ("limits", limits)] ++
    (if replyTo.isEmpty then [] else [("replyTo", toJson replyTo)]) ++
    (if reach.isEmpty then [] else [("reach", toJson reach)])))
  let profile ← match j.getObjVal? "profile" with
    | .ok (.bool b) => pure b
    | .ok _ => throw "profile must be true or false"
    | .error _ => pure false
  return { principal, object, method, argument, intent, limits, digest, profile, replyTo, reach }

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
  /-- The turn is refused whole: a card's own Bend (`refuse(line)`, `cardRefused`: `Ops.cardRefusal`), or a
      grant a direct turn enters under refusing it (`granted`). -/
  | named (refusal : Refusal)
  /-- The turn's principal has started its hour's interpretations (`interpretQuota`): a transient
      refusal of class `quota`, naming the clock at which the next may start. -/
  | quota (reason : String) (next : Nat)
  /-- The turn awaits a slot: its activity is checkpointed and journaled. A `crossing` is a call of
      another world's object, which `serve` carries (`crossCall`). -/
  | suspend (principal intent : String) (patience : Nat) (checkpoint : Delvetalk.Turn.Checkpoint)
      (interpretation : Option Json := none) (crossing : Option Json := none)
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
  /-- A `receive` handed on carries how the original words reached the turn that sent it (a card
      forwarding a reply to the commonplace), so the receiver's interpretation is judged by it: "" is
      words that reached nobody, none a send that carries no reach (a delivery). -/
  reach : Option String := none
  /-- Another world this send goes to (`world:` of its `Reference`; "" this world's): `serve` carries it
      there (`Ops.outbound`), never this world's delivery. -/
  world : String := ""

structure TurnState where
  world : World
  /-- What this segment read of other worlds (`Foreign`): `{world, object, version, stateCid, height,
      head}` each, journaled as `cites` on the entry it ends in. Not roots: two journals do not commit
      together, so a foreign read can go stale without refusing the turn. -/
  cites : Array Json := #[]
  /-- Calls and sends this turn sent to other worlds, across its suspensions (`Limits.crossingsPerTurn`). -/
  crossings : Nat := 0
  roots : List (String × Nat) := []
  behaviours : List (String × Nat) := []
  writes : List (String × List Written) := []
  /-- How each root not read whole was read (`Cells`, by object): a stored frame's scalar part,
      rows and spans (`recordReading`), a field read alone (`viewField`). -/
  cells : List (String × Cells) := []
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
  /-- A delivery the host owes the object's own choice of receiver (an activity's end to its
      supervisor): it may name a helper. -/
  receiver : Bool := false
  /-- The top frame's `inputOrigin` kind and command (`TurnRequest.origin`, `command`). -/
  origin : String := "request"
  command : String := ""
  /-- The running frame's post (`inputOrigin.post`): its own `receive {text, post}`'s, else the
      calling frame's; journaled with a suspension. -/
  post : String := ""
  /-- The object whose send this turn delivers ("" for a turn a principal began): every frame's
      `context.sender` and its law's. -/
  sender : String := ""
  /-- How the turn's words reached it (`TurnRequest.reach`, `delivery` for a delivered turn, `direct`
      for a method other than `receive`); journaled with a suspension. -/
  reach : String := ""
  grants : List Grant := []
  revokes : List String := []
  /-- Rules, wants and verbs this turn places and takes off; admitted at the final commit. -/
  placements : List Placement := []
  /-- Uses of limited grants this turn spent, by grant id. -/
  spent : List (String × Nat) := []
  sends : List Send := []
  programs : List (String × (String × String)) := []
  layered : List String := []
  /-- A program's lineage, by object (a plan's `become`): journaled on its reprogram (`Proposal.madeFrom`). -/
  madeFrom : List (String × Json) := []
  laws : List (String × String) := []
  ticks : Nat
  plans : Nat := 0
  /-- A plan's acts as they ran (`runPlan`), journaled as the entry's `plan`. -/
  acts : Array Json := #[]
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

/-- The roots a turn holds against `maxRoots`: each object, and each field, row and span it read. -/
def rootCount (s : TurnState) : Nat := s.roots.length + (s.cells.map (·.2.extra)).sum

/-- `id` is a root read whole: whatever was read of it by its cells is covered. -/
def recordRoot (id : String) (version : Nat) : M Unit := do
  let s ← get
  if s.roots.any (·.1 == id) then
    set { s with cells := s.cells.filter (·.1 != id) }
  else
    if rootCount s ≥ Limits.maxRoots then evaluation "turn exceeds the root capacity"
    set { s with roots := s.roots ++ [(id, version)] }

/-- Reading offers also reads their behaviour revision; state-only reads keep their ordinary roots. -/
def recordBehaviour (id : String) (o : Object) : M Unit := do
  recordRoot id o.version
  modify fun (s : TurnState) => if s.behaviours.any (·.1 == id) then s
    else { s with behaviours := s.behaviours ++ [(id, o.behaviour)] }

/-- `id` is a root read by its cells (`Cells`): joined with what the turn read of it before, and
    nothing when it is already a root read whole. -/
def recordCells (id : String) (version : Nat) (r : Cells) : M Unit := do
  let s ← get
  let joined := match s.cells.lookup id with
    | some before => some (before.join r)
    | none => if s.roots.any (·.1 == id) then none else some r
  let some joined := joined | return
  let cells := (s.cells.filter (·.1 != id)) ++ [(id, joined)]
  let roots := if s.roots.any (·.1 == id) then s.roots else s.roots ++ [(id, version)]
  if roots.length + (cells.map (·.2.extra)).sum > Limits.maxRoots then evaluation "turn exceeds the root capacity"
  set { s with roots, cells }

/-- A root on one field of an object (`viewField`, WHOLENESS §3a). -/
def recordFieldRoot (id field : String) (version : Nat) : M Unit :=
  recordCells id version { fields := [field] }

/-- A stored frame's store, kept for its resumed segments in this process: the object, the version
    it was read at, and its cells there (KERNEL-HANDOFF §15: each declared relation's rows in key
    order, fetched by position). -/
structure Held where
  object : String
  version : Nat
  cells : Delvetalk.Turn.StateCells

def Held.of (id : String) (version : Nat) (o : Object) : Held := { object := id, version, cells := o.cells }

def Held.store (h : Held) : Delvetalk.Turn.Store := h.cells.store

/-- The frame of a journaled resumption: its checkpoint holds no stored cell (`Held.kept`), so it
    fetches nothing and reads its object through what the checkpoint carries. -/
def Held.journaled (id : String) (version : Nat) : Held :=
  { object := id, version, cells := Delvetalk.Turn.StateCells.make (.record []) [] }

/-- What a stored segment of a held frame read is a root (`cellsOf`). -/
def Held.note (h : Held) (reads : Delvetalk.Turn.Reads) : M Unit :=
  recordCells h.object h.version (cellsOf h.cells reads)

/-- A yield as a checkpoint kept past this process holds it: every stored cell not yet forced made
    the native rows it stands for at the version read (`Turn.materializeStored`), so a journaled
    resumption needs no store at that version; what the rest of the turn may read of those
    relations is their whole key set then. -/
def Held.kept (h : Held) (s : Delvetalk.Turn.Suspension) : M Delvetalk.Turn.Suspension := do
  let (state, fields) ← match Delvetalk.Turn.materializeStored h.store s.state Limits.maxCheckpointBytes with
    | .ok kept => pure kept
    | .error e => evaluation e
  unless fields.isEmpty do recordCells h.object h.version { spans := fields.map (·, none) }
  return { s with state }

/-- The world a turn sees: created objects and all preceding edits, programs, amendments and placements.
    Structural checks share the commit's staging; laws admit only at commit. Versions remain root versions. -/
def turnWorld (s : TurnState) : Except Refusal World := do
  let p : Proposal := { principal := s.principal, intent := s.intent, roots := s.roots, writes := s.writes,
                        programs := s.programs, layered := s.layered, madeFrom := s.madeFrom,
                        laws := s.laws, placements := s.placements, turn := s.world.height + 1 }
  let staged ← stageProposal s.world (s.world.height + 1) p false
  let w := staged.updates.foldl (fun (w : World) (id, o) =>
    { w with objects := w.objects.insert id { o with version := ((s.world.objects[id]?).map (·.version)).getD o.version } }) s.world
  return applyGrants w s.grants s.revokes s.spent

/-- The running turn's world, or the structural refusal of its staged changes. -/
def currentWorld : M World := do
  match turnWorld (← get) with
  | .ok w => return w
  | .error r => throw (.named r)

/-- The state a stored frame starts from: its scalar part (its relations emptied), their rows held
    by the store, so neither the machine nor a checkpoint carries a row it did not force. -/
def storedState (o : Object) : Data := o.cells.scalar

def field? (fields : List (String × Data)) (name : String) : Option Data := fields.lookup name

def labelOf : Data → Option String
  | .label s => some s
  | _ => none

def emptyRecord : Data := .record []

/-- A `Reference` to another world's object: `(world, object)` when `world` is not "". -/
def foreignRef : Data → Option (String × String)
  | .record f => match (f.lookup "world").bind labelOf, (f.lookup "object").bind labelOf with
      | some world, some id => if world.isEmpty then none else some (world, id)
      | _, _ => none
  | _ => none

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
  -- A result whose refusal carries a reading (`Created`, `Programmed`, `Amended`) hears an empty one.
  respond bounds responseType "refused" [.record [("clause", .label clause)],
    .record [("clause", .label clause), ("reading", .label "")], emptyRecord]

/-- `refused {clause, reading}` where the call site's result carries a reading (World's `call`
    since run 11), the refusal's voiced reason (`Refusal.voiced`); `{clause}` otherwise. -/
def refusedReading (bounds : DataBounds) (responseType : Ty) (clause reading : String) : M Data :=
  respond bounds responseType "refused"
    [.record [("clause", .label clause), ("reading", .label reading)], .record [("clause", .label clause)], emptyRecord]

/-- The read Plans another world answers of an object of its own (`Foreign.read`): what a turn may read
    there it reads as a resident of that world would. -/
def foreignReads : List String := ["view", "viewField", "viewAt", "viewDerived", "card", "inspect"]

/-- A read Plan naming another world's object (`World.foreign`): that world's own answer to the same Plan
    with the object named locally, judged there under the turn's subject, and its citation kept for the
    entry (`TurnState.cites`); `foreignWorld` when no world of that name is served here. -/
def foreignRead (bounds : DataBounds) (responseType : Ty) (tag : String) (f : List (String × Data))
    (world id : String) : M Data := do
  let s ← get
  let here := Data.variant tag (.record (f.map fun (k, v) =>
    if k == "object" then (k, .record [("world", .label ""), ("object", .label id)]) else (k, v)))
  match s.world.foreign.read world here responseType bounds s.subject s.ticks with
  | none => refusedReading bounds responseType "foreignWorld" s!"{world} is not a world served here"
  | some (answer, cite, ticks) =>
    modify fun s => { s with ticks, cites := if cite.isNull then s.cites else s.cites.push cite }
    return answer

/-- Why a `call` or `send` to `world` does not cross, as a clause and its reading: a grant serves turns
    in the world it was made in; a world not served here; a turn's second crossing; and, for a call
    (which waits for the target's receipt), any frame but the turn's own. -/
def crossingRefusal (s : TurnState) (world via : String) (depth : Option Nat) : Option (String × String) :=
  if !via.isEmpty then some ("noGrant", s!"a grant serves turns in the world it was made in; nothing here is granted in {world}.")
  else if !s.world.foreign.serves world s.subject then some ("foreignWorld", s!"{world} is not a world served here")
  else if s.crossings ≥ Limits.crossingsPerTurn then
    some ("crossing", s!"a turn sends to another world once; this one has; send the rest from the turn that answers there.")
  else match depth with
    | some d => if d != 0 then
        some ("crossing", s!"a call to {world} waits for its receipt, and only a turn's own method may wait; send it instead.")
      else none
    | none => none

/-- The reading of a refused call: the voiced reason of the refusal it names. -/
def callReading (cls object : String) (expected : Option Json := none) : String :=
  (({ cls, object := some object, expected } : Refusal).voiced.reason).getD ""

def compiledMethod (obj : Object) (method : String) : M Compiled := do
  let key := obj.inputsKey ++ "/" ++ method
  let s ← get
  match s.world.compiled[key]? <|> memoRead key <|> diskCompiled key with
  | some c =>
    unless s.world.compiled.contains key do
      set { s with world := { s.world with compiled := boundedInsert s.world.compiled Limits.maxCompiledPackets key c } }
    return c
  | none =>
    let mine := resolvable s.world obj.inputs
    if mine then if let some e := failRead key then throw (.request s!"method {method} does not compile: {e}")
    -- A method (of a layer stack too: the kernel resolves it with late binding) is compiled from
    -- its package's closure prepared once, and held decoded and checked.
    let compiled := compileEntryIn s.world obj.inputs method >>= fun (ec, w) => do return (← compiledOf ec, w)
    match (if mine then failKeep key compiled else compiled) with
    | .error e => throw (.request s!"method {method} does not compile: {e}")
    | .ok (c, w) =>
      let c := memoKeep key c
      set { s with world := { w with compiled := boundedInsert w.compiled Limits.maxCompiledPackets key c } }
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

/-- The verb an act names when it is not its method (`request.verb`): `act {verb, text}`'s verb, a grown
    one (docs/FOUNDATION.md §10); "" otherwise, read as the method. -/
def actVerb (method : String) (argument : Data) : String :=
  if method != actMethod then "" else match argument with
    | .record fs => match fs.lookup "verb" with
      | some (.label v) => v
      | _ => ""
    | _ => ""

#guard actVerb "act" (.record [("verb", .label "water"), ("text", .label "on the bell")]) == "water"
#guard actVerb "rain" (.record [("verb", .label "water"), ("text", .label "x")]) == ""
#guard actVerb "act" (.record [("text", .label "x")]) == ""

/-- Stage a write by the running object `id`, called by `caller`. The running object is
    always the first root of its own activity, so no earlier view is needed. -/
def addWrite (id caller : String) (step : Step) : M Unit := do
  let s ← get
  unless s.roots.any (·.1 == id) do evaluation "a write names an object that is not a root"
  if step.length > Limits.maxEditsPerWrite then evaluation "turn exceeds the edit capacity"
  let prior := (s.writes.lookup id).getD []
  if prior.length ≥ Limits.maxEditsPerWrite then evaluation "turn exceeds the edit capacity"
  let steps := prior ++ [({ caller, edits := step, method := s.method, via := s.via, argument := s.argument,
                            verb := actVerb s.method s.argument } : Written)]
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
  let change : Written := { caller, kind, edits := [], method := s.method, via := s.via, argument := s.argument,
                            verb := actVerb s.method s.argument }
  if s.writes.any (·.1 == id) then
    set { s with writes := s.writes.map fun (k, ws) => if k == id then (k, ws ++ [change]) else (k, ws) }
    return true
  if s.writes.length ≥ Limits.maxWrites then return false
  set { s with writes := s.writes ++ [(id, [change])] }
  return true

/-- The receipt a settled slot answers an await with (`Plan.Receipt`), its `hash` the entry's CID, so
    Bend may cite it (`madeFrom`). -/
def receiptData (entry : Json) : Data :=
  let identity := (entry.getObjVal? "identity").toOption.getD Json.null
  let text := fun (j : Json) (k : String) => ((j.getObjValAs? String k).toOption).getD ""
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  -- A `crossed` entry's outcome is the other world's, as it answered.
  let outcome := if tagOf entry == "crossed" then (outcome.getObjVal? "answer").toOption.getD outcome else outcome
  let result : Data := match outcome.getObjValAs? String "tag" with
    | .ok "refused" => .variant "refused" (.record [("class", .label (text outcome "class")),
        ("root", .label (text outcome "object"))])
    | _ => .variant "admitted" (.record [])
  let fields : List (String × Data) := [("slot", .record [("principal", .label (text identity "principal")),
      ("intent", .label (text identity "intent"))]),
    ("height", .natural ((entry.getObjValAs? Nat "height").toOption.getD 0)), ("outcome", result)]
  .record (fields ++ [("hash", Data.label (text entry "hash"))])

/-- An await's `reply`. -/
def receiptReply (entry : Json) : Data := .record [("receipt", receiptData entry)]

/-- The settled entry of an identity, if it has one (a suspension is not settled). -/
def settled (w : World) (principal intent : String) : Option Json :=
  match w.receipts[identityKey principal intent]? with
  | some i => (w.entries.get? i).bind fun e => if tagOf e == "suspended" then none else some e
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

/-- The first free `<prefix><n>`, n from 1: not an object, not created this turn, not held by a
    suspension's absence. -/
def mintUnder (pfx : String) : M String := do
  let s ← get
  let held := fun (id : String) => s.world.objects.contains id || s.creates.any (·.1 == id) ||
    s.world.suspended.any fun e => (((e.getObjVal? "outcome").toOption.bind (·.getObjVal? "activity" |>.toOption)
      |>.bind (·.getObjVal? "absent" |>.toOption) |>.bind (·.getArr? |>.toOption)).getD #[]).contains (toJson id)
  for n in [1:Limits.maxObjects + Limits.createsPerTurn + 2] do
    if !held s!"{pfx}{n}" then return s!"{pfx}{n}"
  evaluation "no child id is free"

/-- Compile an object's new sibling: `package` is a module of the creator's own sealed
    chain (a name), or the source of one more module over that chain. -/
def creationInputs (creator : Object) (package : String) : Except (String × String) Json := do
  if package.utf8ByteSize > Limits.maxPackageBytes then
    throw ("packageBytes", s!"package source exceeds maxPackageBytes ({Limits.maxPackageBytes} bytes)")
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

/-- What `creator`'s `create` of `package`, then an `extend` of each of `layers`, would compile, checked
    (`checkInputs`): a kind checks the stack its instances will run, its ancestors' bodies and its own
    (`world.check {package, layers}`). A package of source with no layers is checked as one entry module
    over the library (`checkSource`). -/
def checkStack (w : World) (creator : Object) (package : String) (layers : List String) : List String × Bool :=
  if layers.isEmpty && package.startsWith "edition" then checkSource w package else
  -- A layer alone lays on nothing (playtest 5: "no module layer over ./Kind.obend … in the creator's package", the
  -- whole source quoted back): it is checked over what it would be laid on.
  if layers.isEmpty && package.startsWith "layer over" then
    ([s!"Checked:1: package-request: a layer is checked over what it lays on: delvetalk workshop check / over: <a kind, or a thing>, with this block (kind/record for a body over a record)"], false) else
  match (creationInputs creator package).mapError (·.2) >>= (layeredInputs · layers) with
  | .ok inputs => checkInputs w inputs
  | .error e => ([s!"Checked:0: package-request: {e}"], false)

/-- `checked {diagnostics, reaches}`, or `{diagnostics}` where the call site's result has no `reaches`
    (a package compiled before it). -/
def checkedData (verdict : List String × Bool) : List Data :=
  let diagnostics := ("diagnostics", listData (verdict.1.map Data.label))
  [.record [diagnostics, ("reaches", .boolean verdict.2)], .record [diagnostics]]

def buildCreated (w : World) (creator : Object) (package : String) (seed : Data) (lawArg principal : String)
    (height : Nat) (layers : List String := []) : Except (String × String) (CreateRec × Built) := do
  let inputs ← creationInputs creator package
  -- The layers `extend`s of the same turn lay into the making: one closure, one pin.
  let inputs ← (layeredInputs inputs layers).mapError fun e =>
    (if e.startsWith "package source exceeds" then "packageBytes" else "compile", e)
  let built ← (compileObject w inputs).mapError (("compile", ·))
  let initial ← (initialState built).mapError (("compile", ·))
  let state ← (mergeSeed initial seed built.assumptions.bounds built.ty).mapError (("typeMismatch", ·))
  let state := withOwner state seed principal
  let (relations, state) ← (relationsFor built state).mapError fun e =>
    (if e.startsWith "duplicateKey" then "duplicateKey" else "key", e)
  let lawText := if lawArg.startsWith "law " then some lawArg else none
  let (object, sources) ← (makeObject w built inputs state none none principal height lawText).mapError
    (fun e => (if isAmendmentRefusal e || e.startsWith "under: " then "law"
      else if e.endsWith "byte capacity" then "capacity" else "typeMismatch", e))
  return ({ object := { object with relations }, sources, seed := dataJson state }, built)

/-- The turn's world with what it made (docs/HOST-HANDOFF.md 5.203): a later frame calls it, writes it and places on it
    (judged at the commit by its own law, `judge`), as a plan's later act names it (`{made N}`). -/
def madeIn (w : World) (id : String) (made : CreateRec) : World :=
  { w with objects := w.objects.insert id { made.object with madeFrom := made.madeFrom } }

/-- What a host spell changes (`hostChange`, `placingChange`): the roots it reads and the state edits,
    placements, program, law or grant it stages, with the world its program is cached in; `refusal` when its code or its law does not read,
    which refuses the turn whole at its commit. A spell alone commits it (`hostSpell`); a plan's act stages it into
    its one turn (`stageHost`). -/
structure HostChange where
  world : World
  roots : List (String × Nat) := []
  writes : List (String × List Written) := []
  placements : List Placement := []
  programs : List (String × (String × String)) := []
  layered : List String := []
  madeFrom : List (String × Json) := []
  laws : List (String × String) := []
  grants : List Grant := []
  refusal : Option Refusal := none

/-- Append clauses through the amendment path, preserving names and the parser's diagnostics. -/
def appendedLaw (o : Object) (id clauses : String) : Except (String × String) String := do
  let existing := ((textClauses o.lawText).map (·.2.1)) ++ (o.rules ++ o.wants).map (·.name)
  if let some (_, n, _, _) := (textClauses clauses).find? (existing.contains ·.2.1) then
    throw ("lawClash", s!"{id}'s text already has a clause {n}; choose clause names new to this text.")
  return if o.lawText.isEmpty then clauses else s!"{o.lawText}\n{clauses}"

/-- A kind's clause collection for its things, held beside its form and body in state. -/
def thingsText (o : Object) : Option String := do
  let _ ← textField o.state "of"
  let _ ← textField o.state "body"
  textField o.state "law"

/-- The clauses each thing follows from a kind's text, through the same `carried` relation. -/
def clausesForThings (w : World) (id : String) (o : Object) (text : String) : List CarriedClause :=
  let collection := { o with lawText := text, law := (parseLawText text).toOption.getD [], rules := [], wants := [] }
  (carried w id collection).map fun (c : CarriedClause) => { c with owner := thingPrincipal id }

/-- Install a kind's component rows and cited text together. Ancestors already installed retain
    their position; a changed body replaces its layer there. The journaled lineage supplies replay
    with the bodies and their source pins and receipts, without reading a later kind's state. -/
def kindChange (w : World) (principal : String) (o : Object) (id kindId : String) (prepare : Bool := true) :
    Except (String × String) HostChange := do
  let some k := (w.objects[kindId]?).filter (·.read.permits principal)
    | throw ("unknownKind", s!"There is no kind {kindId}.")
  let some body := textField k.state "body" | throw ("unknownKind", s!"{kindId} is no kind.")
  let stack ← kindStack w principal ((textField k.state "of").getD "record") body 4
  let old := lineageComponents o.madeFrom
  let requested := (stack.kinds ++ [(kindId, k)]).map fun (name, src) =>
    Json.mkObj [("object", toJson name), ("pin", toJson src.pin), ("receipt", toJson (versionReceipt w name)),
                ("body", toJson ((textField src.state "body").getD ""))]
  let fresh := old.map (fun c =>
      match requested.find? (fun r => componentText r "object" == componentText c "object") with
      | some r => if componentText r "body" == componentText c "body" && componentText r "pin" == componentText c "pin" then c else r
      | none => c) ++
    requested.filter (fun r => !(old.any fun c => componentText c "object" == componentText r "object"))
  let (_, components) ← (componentInputs o.inputs old fresh).mapError (("compile", ·))
  let installed := (components.find? fun c => componentText c "object" == kindId).getD Json.null
  let lineage := Json.mkObj [("object", toJson kindId), ("pin", toJson k.pin), ("receipt", toJson (componentText installed "receipt")),
                          ("components", toJson components)]
  let cited := (textClauses o.lawText).any fun c => c.2.2.2 == s!"under \"{kindId}\""
  let names := (textClauses o.lawText).map (·.2.1) ++ (o.rules ++ o.wants).map (·.name)
  let name := ((List.range (names.length + 1)).map fun n => if n == 0 then "kind" else s!"kind{n}").find? (!names.contains ·)
  let citation := kindCitation w kindId (name.getD "kind")
  let text ← if cited || citation.isEmpty then pure o.lawText else appendedLaw o id citation
  let change : HostChange := { world := w, roots := (id, o.version) :: (stack.kinds ++ [(kindId, k)]).map (fun (name, src) => (name, src.version)),
                               laws := if text == o.lawText then [] else [(id, text)] }
  let change := { change with refusal := match parseLawText text with
    | .error message => some { cls := "programRefused", clause := some "law syntax", object := some id, reason := some message }
    | .ok _ => none }
  if o.madeFrom == some lineage then return change
  let source := body
  let change := { change with programs := [(id, (source, ""))], layered := [id], madeFrom := [(id, lineage)] }
  if !prepare then return change
  return match programFor w o source "" true (some lineage) with
    | .error (clause, message) => { change with refusal := some { cls := "programRefused", clause := some clause, object := some id, reason := some message } }
    | .ok prog => { change with world := cacheProgram w o source "" prog true (some lineage) }

/-- An `extend` (or `reprogram {mode: extend}`) of `id`, which this turn created (`made`): the creation
    built again with the layer over its package and the layers laid before it (a kind's instance takes
    its ancestors' bodies, then its own), judged by the made thing's own law as a reprogram (kind 1)
    proposed by `self`. A replacing reprogram or a migration of a thing not made yet is refused; the
    creation journals one closure and its pin. -/
def extendCreation (bounds : DataBounds) (responseType : Ty) (self id : String) (made : CreateRec)
    (source migration : String) (extend : Bool) : M Data := do
  let s ← get
  if !extend then return ← refusedReading bounds responseType "unknownObject" s!"{id} is not made until this turn ends; a layer may be laid into the making with extend"
  if !migration.isEmpty then return ← refusedReading bounds responseType "migration" s!"{id} is being made: its state has no older type to migrate"
  let some creator := s.world.objects[made.creator]? | evaluation "the creating object vanished"
  match buildCreated s.world creator made.package made.seedArg made.lawArg s.principal (s.world.height + 1) (made.layers ++ [source]) with
  | .error (clause, message) =>
    refusedReading bounds responseType clause
      ((({ cls := "programRefused", clause := some clause, object := some id, reason := some message } : Refusal).voiced.reason).getD message)
  | .ok (again, built) =>
    let o := again.object
    let facts : Law.Facts := citing s.world o.law (lawNames o.law)
      { subject := s.principal, caller := self, height := s.world.height + 1,
        turn := s.world.height + 1, pin := o.pin, kind := 1, clock := s.world.clock, object := id }
    if let some clause := Law.refusedBy o.law facts (some o.state) o.state then
      return ← refusedReading bounds responseType clause ((o.readings.lookup clause).getD s!"the law of {id} does not admit this layer.")
    let again := { again with object := { o with supervisor := made.object.supervisor }, madeFrom := made.madeFrom,
                              creator := made.creator, package := made.package, seedArg := made.seedArg,
                              lawArg := made.lawArg, layers := made.layers ++ [source] }
    set { s with creates := s.creates.map (fun (k, c) => if k == id then (k, again) else (k, c)),
                 world := madeIn (cacheBuild s.world o.inputs built) id again }
    respond bounds responseType "reprogrammed" [.record [("pin", .label o.pin)]]

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

/-- The argument a principal's own turn runs `method` of `id` with under grant `via` (`lentVia`), as a call
    under it does (`grantFor`, `spendGrant`): the grant stands for this principal, has a use left, which the
    turn spends, and fixes what it fixes of the argument. "" runs the argument as given. -/
def granted (via id method : String) (argument : Data) : M Data := do
  if via.isEmpty then return argument
  match ← grantFor via "" id method argument with
  | .ok (_, merged) => spendGrant via; return merged
  | .error clause => throw (.named { cls := "lawRefused", clause := some clause, object := some id,
                                     reading := some s!"no grant lets this turn run {method} on {id} ({clause})." })

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

/-- A form field's kind for a member type: text (required: only a form or kind that declares `0..N` makes
    a field optional), a natural, or a choice among the labels of a sum whose every payload is empty. Any
    other type has no form. -/
def formKind (member : Json) : Option Data :=
  match (member.getObjValAs? String "tag").toOption with
  | some "label" => some (.variant "text" (.record [("min", .natural 1), ("max", .natural Limits.formTextMax)]))
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
    let name ← (m.getObjValAs? String "name").toOption
    -- `act` offered to nobody (`~act`) still has its form: the grown verbs' (`withVerbs`), never a spell itself.
    guard ((m.getObjValAs? Bool "context").toOption == some true && (isActionRow m || (name == actMethod && !isHelperRow m)))
    let fields ← rowFields ((m.getObjVal? "input").toOption.getD Json.null)
    -- A field the package's form for this action declares takes that kind; any other, its type's.
    let given := (declared.lookup name).getD []
    let kinds ← fields.mapM fun (n, member) =>
      (given.lookup n <|> formKind member).map fun k => Data.record [("name", .label n), ("kind", k)]
    return .record [("card", .label id), ("action", .label name), ("fields", listData kinds)]

/-- A declared form field's kind as the host reads it: `text`, `object`, `natural` and `choice` as given, and
    `source` (Bend source) as text of 1 to `Limits.formSourceMax` characters. -/
def declaredKind : Data → Option Data
  | .variant "source" _ => some (.variant "text" (.record [("min", .natural 1), ("max", .natural Limits.formSourceMax)]))
  | k@(.variant "text" _) => some k
  | k@(.variant "object" _) => some k
  | k@(.variant "natural" _) => some k
  | k@(.variant "choice" _) => some k
  | _ => none

/-- The kinds the package's pure `forms()` declares, by action and field, and the `source` fields by
    action; none when its entry module declares no `forms()` or it does not evaluate. -/
def declaredForms (o : Object) : M (List (String × List (String × Data)) × List (String × List String)) := do
  if !o.declaresDef "forms" then return ([], [])
  let some c ← tryCatch (some <$> compiledMethod o "forms") (fun _ => pure none) | return ([], [])
  let some entry := c.entry | return ([], [])
  let .ok value := runZero (defKey o "forms") entry | return ([], [])
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

/-- Why `argument` misfits the form the card declares for `method` (`declaredForms`), judged as a
    spell's field is (`Spell.judge`): a text's length, a natural's range, a choice's options (a
    word, or the case a sum-typed field took). Fields no form declares keep their type's freedom. -/
def declaredMisfit (method : String) (argument : Data) (declared : List (String × List (String × Data))) : Option String := do
  let given ← declared.lookup method
  let form ← Spell.Form.ofData (.record [("card", .label ""), ("action", .label method),
    ("fields", listData (given.map fun (n, k) => Data.record [("name", .label n), ("kind", k)]))])
  let .record values := argument | none
  form.fields.findSome? fun f => do
    let shown ← match values.lookup f.name with
      | some (.label t) => some t
      | some (.natural n) => some (toString n)
      | some (.variant l _) => some l
      | _ => none
    let (_, reason) ← Spell.judge f shown
    return (if reason.endsWith "." then (reason.dropEnd 1).toString else reason)

/-- A form's action, on the Data wire. -/
def formAction : Data → String
  | .record fs => ((fs.lookup "action").bind fun | .label a => some a | _ => none).getD ""
  | _ => ""

/-- A grown verb's form: its name as the action, and the `text` field of the card's `act` form when it
    takes a line (so a grown verb's line is held to the bound `act` declares). -/
def grownForm (id : String) (act : Option Data) (v : Verb) : Data :=
  let text := if v.takes.isEmpty then [] else match act with
    | some (.record fs) => (((fs.lookup "fields").bind listOf).getD []).filter fun
        | .record g => (g.lookup "name").bind labelOf == some "text"
        | _ => false
    | _ => []
  .record [("card", .label id), ("action", .label v.name), ("fields", listData text)]

/-- A card's declared forms with its grown verbs after them; `act` itself is no spell, offered or not (`~act`): its
    spells are the verbs. -/
def withVerbs (id : String) (o : Object) (declared : List Data) : List Data :=
  let act := declared.find? (formAction · == actMethod)
  declared.filter (formAction · != actMethod) ++ (if act.isSome then o.verbs.map (grownForm id act) else [])

/-- An object's forms (`methodForms`) with the kinds its `forms()` declares: a spell is judged by the
    card's own bounds, and the type's default holds only for a field no form names. Then its grown verbs
    (docs/FOUNDATION.md §10), each a form as a declared one is; `act` itself is no spell: its spells
    are the verbs. -/
def formsOf (id : String) (o : Object) : M (List Data) := do
  return withVerbs id o (methodForms id o.methods (← declaredForms o).1)

/-- Does the object's method table list `name`? -/
def hasMethod (o : Object) (name : String) : Bool :=
  ((o.methods.getArr?.toOption).getD #[]).any fun m => (m.getObjValAs? String "name").toOption == some name

/-- The Context a card is rendered for: the reader (`principal`), the card's object, the asking
    object (`caller`, "" for `world-card`), and the turn's intent and height. -/
def cardContext (w : World) (id reader caller intent : String) (height : Nat) (method : String) (whole : Bool := false) : Data :=
  contextData id reader (handleShown w reader) w.opener caller intent height w.clock (if whole then Card.wholeKind else "card") method
    (room := w.cardRoom)

/-- A pure definition of `id`'s package run on its committed state (the first argument) through the
    stored path under this turn's ticks (KERNEL-HANDOFF §15): only the rows it forces are fetched,
    and what it read of `id` is a root (`recordReading`). -/
def storedPure (id : String) (o : Object) (c : Compiled) (rest : List Data) : M (Except String Data) := do
  let entry ← entryOf c
  let st ← get
  match Package.executeDataEntryStored entry (#[storedState o] ++ rest.toArray) o.cells.store
      (st.limits.setObjVal! "ticks" (toJson (toString st.ticks))) with
  | .ok (.finished value _ _ usage, reads) =>
    recordCells id o.version (cellsOf o.cells reads)
    spend (usage.ticksUsed + usage.conversionNodes)
    return .ok value
  | .ok (.refused failure usage, reads) =>
    recordCells id o.version (cellsOf o.cells reads)
    spend (usage.ticksUsed + usage.conversionNodes)
    return .error failure
  | .error e => return .error e

/-- The views a package declares: the labels its pure `views()` returns (`def views() ->
    List<String>`), read as `lawReads()` is; none when it has no such definition. -/
def declaredViews (o : Object) : M (List String) := do
  if !o.declaresDef "views" then return []
  let some c ← tryCatch (some <$> compiledMethod o "views") (fun _ => pure none) | return []
  let some entry := c.entry | return []
  match runZero (defKey o "views") entry with
  | .ok d => return (labels [] d).getD []
  | .error _ => return []

/-- A derived view of an object (`viewDerived {object, view}`): the package's pure definition
    `view`, which `views()` must name, run on the committed state (with the reader's Context when
    it takes one) under this turn's remaining ticks, as a card is rendered. Its value must be
    first-order data. `noView` when the package does not declare `view`, `view` when it fails, runs
    out, or answers something other than data. -/
def derivedView (id : String) (o : Object) (view : String) (context : Data) (detailed : Bool := false) : M (Except String Data) := do
  unless (← declaredViews o).contains view do return .error "noView"
  let some c ← tryCatch (some <$> compiledMethod o view) (fun _ => pure none) | return .error "noView"
  let (rest, result) := match c.type with
    | .arrow _ _ _ (.arrow _ _ ct r) => (some [fitRecord c.bounds ct context], r)
    | .arrow _ _ _ r => (some [], r)
    | r => (none, r)
  unless result.isDataUnder c.bounds [] Ty.dataFuel [] do return .error "view"
  -- A view of no parameter reads nothing of the object.
  let ran ← match rest with
    | some rest => storedPure id o c rest
    | none => do
      let (value, used) := runPure (← entryOf c) [] (← get).ticks
      spend used
      pure value
  -- A view out of ticks says so (`budget`, as a card's render does); any other failure is `view`.
  -- `detailed` (`world-derived`, for the view's author) keeps the machine's words after the clause.
  return ran.mapError fun e => (if e == "budget" || (e.splitOn "tick").length > 1 then "budget" else "view") ++ (if detailed then s!": {e}" else "")

/-- The kernel's refusal of an argument that does not conform to the entry's input type. -/
def argumentRefusal : String := "turn refused: argument does not conform to its type"

/-- Does `argument` fit the input of a compiled method? The check is exact: a method without an
    input takes only `{}` (a field it does not declare is refused by name, `extraField`). At `Data`
    any well-formed value fits; at a data type the value must conform under the packet's bounds (the
    check the kernel's `prepareStart` makes). -/
def argumentFits (compiled : Compiled) (argument : Data) : Bool :=
  match compiled.type with
  | .arrow _ _ _ (.arrow _ _ domain (.arrow _ _ _ _)) =>
    if domain == .data then argument.wellFormed
    else !(domain.isDataUnder compiled.bounds [] Ty.dataFuel []) || argument.conformsUnder compiled.bounds domain
  | _ => match argument with
    | .record [] => true
    | _ => false

/-- The field names of a record row; none for anything else. -/
def rowNames : Ty → Option (List String)
  | .field n _ t => (rowNames t).map (n :: ·)
  | .emptyRow => some []
  | _ => none

/-- The first field of a record `argument` that the method's input does not declare (every field,
    for a method without an input); none when the input is not a record row or all are declared. -/
def extraField (compiled : Compiled) (argument : Data) : Option String :=
  match argument with
  | .record fs =>
    let declared := match compiled.type with
      | .arrow _ _ _ (.arrow _ _ domain (.arrow _ _ _ _)) => rowNames domain
      | .arrow _ _ _ (.arrow _ _ _ _) => some []
      | _ => none
    declared.bind fun names => (fs.find? fun (k, _) => !names.contains k).map (·.1)
  | _ => none

/-- The fields of a record row with their types; none for anything else. -/
def rowTypes : Ty → Option (List (String × Ty))
  | .field n m r => (rowTypes r).map ((n, m) :: ·)
  | .emptyRow => some []
  | _ => none

#guard rowNames (.field "who" .label (.field "n" .natural .emptyRow)) == some ["who", "n"]
#guard rowNames .data == none

/-- A refusal's reason for an argument that does not fit: the field the input lacks when there is
    one, else `argumentRefusal`; a method without an input says it takes `{}`. -/
def misfitReason (compiled : Compiled) (method : String) (argument : Data) : String :=
  match extraField compiled argument, compiled.type with
  | some f, _ => s!"{argumentRefusal}: {method} takes no field {f}"
  | none, .arrow _ _ _ (.arrow _ _ domain (.arrow _ _ _ _)) =>
    -- The first field the input declares that the argument lacks, or holds a value of another type.
    let given := match argument with
      | .record fs => fs
      | _ => []
    match (rowTypes domain).bind fun fields => fields.find? fun (n, t) => match given.lookup n with
        | some v => !v.conformsUnder compiled.bounds t
        | none => true with
    | some (f, _) => if (given.lookup f).isSome then s!"{argumentRefusal}: {method}'s field {f} is not of its type"
        else s!"{argumentRefusal}: {method} needs field {f}"
    | none => s!"{argumentRefusal}: {method} takes a record of its fields"
  | none, _ => s!"{argumentRefusal}: {method} takes no input; send an empty record"

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
def expectedInput (obj : Object) (id method : String) (compiled : Compiled)
    (declared : List (String × List (String × Data)) := []) : Json :=
  let row := ((obj.methods.getArr?.toOption).getD #[]).find? fun m => (m.getObjValAs? String "name").toOption == some method
  let type := match (row.bind fun r => (r.getObjVal? "input").toOption), compiled.type with
    | some input, _ => input
    | none, .arrow _ _ _ (.arrow _ _ domain (.arrow _ _ _ _)) => Delvetalk.Theory.ObjectiveBendTyping.typeJson domain
    | none, _ => Json.null
  -- The card's declared bounds (`declaredForms`), as the spell path judges by: the hint and the
  -- front's actions agree.
  let form := row.bind fun r => (methodForms id (Json.arr #[r]) declared).head?
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
  let context := contextData handler s.subject (handleShown s.world s.subject) s.world.opener self s.intent s.world.height s.world.clock "handle" "" s.post s.sender
    s.world.cardRoom
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
    proposal's `programs`/`layered` or `laws`. With the clause, the refusal's voiced reason (a
    migration's or the compiler's diagnostic included: codex agent 12). -/
def dryChange (w : World) (s : TurnState) (self id : String) (version : Nat) (proposer : String) (kind : Nat)
    (change : Proposal) : Option (String × String) :=
  if id == self then none else
  let written : Written := { caller := proposer, kind, edits := [], method := s.method, via := s.via, argument := s.argument }
  let p : Proposal := { change with principal := s.principal, intent := s.intent, roots := [(id, version)],
                                    writes := [(id, [written])], turn := w.height + 1 }
  match judge w (w.height + 1) p with
  | .ok _ => none
  -- The call site hears the clause and its reading (a law's own, else the voiced reason), never "refused …" twice.
  | .error r => some (r.clause.getD r.cls, (r.reading <|> r.voiced.reason).getD "")

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
   "sendVia", "create", "createUnder", "make", "await", "awaitUntil", "interpret",
   "offer", "publish", "reprogram", "extend", "compose", "kindStack", "amend", "inspect", "check", "checkObject", "grant", "grantWith", "revoke",
   "objects", "changed", "card", "principal",
   "rule", "unrule", "want", "unwant", "grow", "ungrow", "act", "chronicle", "wanting", "holds", "receipt"]

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
  | .text 0 b => s!"<optional text, up to {b} characters>"
  | .text a b => s!"<text, {a} to {b} characters>"
  | .object 0 b => s!"<optional object id, up to {b} characters>"
  | .object a b => s!"<object id, {a} to {b} characters>"
  | .natural a b => s!"<a number from {a} to {b}>"
  | .choice options => s!"<{", ".intercalate options}>"

/-- One form as the spell to send, the fields `given` filled in and the rest shown as blanks. -/
def spellTemplate (card : String) (form : Spell.Form) (given : List Spell.Binding := []) : String :=
  s!"delvetalk {card} {form.action}\n" ++ String.join (form.fields.map fun f =>
    s!"{f.name}: {((given.find? (·.name == f.name)).map (·.value)).getD (spellHint f.kind)}\n")

/-- One lens as the `set` spell a reader copies (`Card.lensTemplate`). -/
def lensTemplate (card : String) (lens : Spell.Field) (value : Option String := none) : String :=
  s!"delvetalk {card} set\n{lens.name}: {value.getD (spellHint lens.kind)}\n"

/-- A card's usage (`Card.help`): every form as a template, then the `set` spell once with every lens a line under
    it, so a card's usage grows a line a lens, not a spell. -/
def spellUsage (card : String) (forms : List Spell.Form) (lenses : List Spell.Field := []) : String :=
  if forms.isEmpty && lenses.isEmpty then s!"{card} takes no spells; reply in words and hob places them." else
  (if forms.isEmpty then "" else "Reply with a spell:\n" ++ String.join (forms.map fun f => "\n" ++ spellTemplate card f)) ++
  (if lenses.isEmpty then "" else
    s!"\nTo set a field: delvetalk {card} set, then one of these lines (one field a spell):\n" ++
      String.join (lenses.map fun l => s!"{l.name}: {spellHint l.kind}\n"))

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

/-- The `misfit` a card's `receive` still declares (`Card.Heard`): always empty, since a misfit spell is
    hob's to read (`heardTurn`), never a card's. -/
def noMisfit : Data := .record [("clause", .label ""), ("reason", .label "")]

/-- The spell the host read in a reply, as `receive` hears it (`spell {card, action}`; "" for none): what a card
    completes when the spell lacked fields, so no card reads the spell line again. -/
def castData (card action : String) : Data := .record [("card", .label card), ("action", .label action)]

/-- The spell line of a reply's text, as the host reads it: its card and action, or none. -/
def castOf (method : String) (argument : Data) : Data :=
  match Spell.parse (heardText method argument) with
  | .spell card action _ => castData card action
  | _ => castData "" ""

/-- `receive`'s argument with what the host fills, as the method declares it: the bare field lines as
    `fields`, the spell it read as `spell` (`cast`, else read from the text), and an empty `misfit`
    (`noMisfit`). -/
def heardArgument (w : World) (o : Object) (argument : Data) (fields : List Spell.Binding)
    (cast : Option Data := none) : Option Data :=
  match argument, ((compiledMethod o "receive").run.run (scratchState w)).1 with
  | .record fs, .ok c =>
    let base := fs.filter (fun (k, _) => k != "fields" && k != "misfit" && k != "spell") ++ [("fields", bindingsData fields)]
    let spell := ("spell", cast.getD (castOf "receive" argument))
    let shapes := [base, base ++ [spell], base ++ [("misfit", noMisfit)], base ++ [spell, ("misfit", noMisfit)]]
    (shapes.map Data.record).find? (argumentFits c)
  | _, _ => none

/-- Does a `receive` argument fit the card's own `receive` input, with or without the `fields` the
    host fills? A reply carrying another field (a forged `who`) is not read as a spell: `receive`
    runs as asked and its type refuses it (`typeMismatch`), as any other method's would. -/
def heardFits (w : World) (o : Object) (argument : Data) : Bool :=
  match ((compiledMethod o "receive").run.run (scratchState w)).1 with
  | .ok c => argumentFits c argument || (heardArgument w o argument []).isSome
  | .error _ => false

/-- `formsOf` outside a turn, without the package's `views()` entries: a derived view is read
    (`viewDerived`), not cast. -/
def spellFormsData (w : World) (id : String) (o : Object) : List Data :=
  let views := ((declaredViews o).run.run (scratchState w)).1.toOption.getD []
  let forms := ((formsOf id o).run.run (scratchState w)).1.toOption.getD (withVerbs id o (methodForms id o.methods))
  forms.filter fun f => match f with
    | .record fs => match fs.lookup "action" with
      | some (.label a) => !views.contains a
      | _ => true
    | _ => true

/-- The forms a card offers, as the spell grammar reads them. -/
def spellForms (w : World) (id : String) (o : Object) : List Spell.Form :=
  (spellFormsData w id o).filterMap Spell.Form.ofData

/-- The facts `methodAdmits` and `kindAdmits` judge `principal`'s change of `o` (`id`) by, before the
    method, verb and kind are named: what the law cites (`citing`) is the same for every method, so a
    reply that judges each of a card's actions gathers it once. -/
def admitFacts (w : World) (o : Object) (principal : String) (id : String := "") : Law.Facts :=
  citing w o.law (lawNames o.law)
    { subject := principal, caller := "", height := w.height + 1,
      turn := w.height + 1, pin := o.pin, clock := w.clock, object := id }

/-- `methodAdmits` on facts already gathered (`admitFacts`). -/
def methodAdmitsBy (o : Object) (facts : Law.Facts) (method : String) (verb : String := method) : Json :=
  let facts := { facts with method, verb }
  match o.law.find? fun (_, clause) => !Law.admits facts (some o.state) o.state clause with
  | none => Json.bool true
  | some (name, _) => Json.mkObj ([("clause", toJson name)] ++ ((o.readings.lookup name).map fun r => [("reading", toJson r)]).getD [])

/-- The text law's verdict on a kind-0 change by `principal` through `method`, judged on the state as
    it stands (`Facts {subject: principal, caller: "", kind: 0, method, height, turn, pin}`, old and new
    the current state): `true`, or `{clause, reading?}` naming the first clause that refuses. A clause
    that reads the state is judged on it too (codex agent 11: `request.subject == new.owner or …`
    refuses a stranger whatever the method writes, unless the method moves the owner). -/
def methodAdmits (w : World) (o : Object) (principal method : String) (id : String := "") (verb : String := method) : Json :=
  methodAdmitsBy o (admitFacts w o principal id) method verb

/-- The actions a card offers `reader` by its own word: the pure `def actions(state: State, context:
    Abi.Context) -> List<String>` it may define (a conventional name, run as a card renders, under the
    law's ticks), for guards its methods keep in Bend (the Bell's planter-only `door`). `none` when it
    defines none, or it does not finish. -/
def readerActions (w : World) (id : String) (o : Object) (reader : String) : Option (List String) := do
  guard (hasMethod o "actions")
  let (c, _) ← (compileDef w o "actions").toOption
  let entry ← c.entry
  let context := cardContext w id reader "" "" w.height "actions"
  let arguments := match c.type with
    | .arrow _ _ _ (.arrow _ _ ct _) => [o.state, fitRecord c.bounds ct context]
    | _ => [o.state]
  match (runPure entry arguments Delvetalk.Bounds.lawTicks).1 with
  | .ok value => labels [] value
  | .error _ => none

/-- The card shown to hob and every card whose forms are in the reading, once each. -/
def offeredCards (self : String) (offers : Data) : List String :=
  (self :: ((listOf offers).getD []).filterMap (fun f => match f with
    | .record fs => (fs.lookup "card").bind labelOf
    | _ => none)).eraseDups

def offeredRoots (w : World) (self : String) (offers : Data) : List (String × Nat) × List (String × Nat) :=
  let cards := (offeredCards self offers).filterMap fun id => (w.objects[id]?).map (id, ·)
  (cards.map fun (id, o) => (id, o.version), cards.map fun (id, o) => (id, o.behaviour))

/-- A numbered model slot changes only with the behaviour it reads, never with ordinary state. -/
def interpretationSlot (slotParts : Array Json) (behaviours : List (String × Nat)) : String :=
  let revisions := (behaviours.filter (·.2 != 0)).toArray.map fun (id, revision) =>
    Json.mkObj [("object", toJson id), ("behaviour", toJson revision)]
  Journal.bodyHash (Json.arr (if revisions.isEmpty then slotParts else slotParts.push (Json.arr revisions)))

/-- The per-reader action filter usage and inspection share (codex agent 11): an action is offered to
    `reader` when the law admits them to run it on the state as it stands (`methodAdmits`) and the
    card's `actions` (if any) lists it. `receive`, the spell's way in, always stands. A spell for
    another action is still fitted, and the commit's law refuses it. -/
def offeredTo (w : World) (id : String) (o : Object) (reader : String) : String → Bool :=
  let listed := readerActions w id o reader
  let facts := admitFacts w o reader id
  fun action =>
    -- A grown verb is offered as its `act` is, judged with the verb as `request.verb`, by the law alone: a card's
    -- own `actions` names its declared methods, never the verbs hands grew on it.
    let grown := o.verbs.any (·.name == action)
    let method := if grown then actMethod else action
    action == "receive" ||
      (methodAdmitsBy o facts method action == Json.bool true && (grown || (listed.map (·.contains method)).getD true))

/-- The forms a card's usage shows `principal` (`offeredTo`). -/
def usageForms (w : World) (id : String) (o : Object) (principal : String) (forms : List Spell.Form) : List Spell.Form :=
  let offered := offeredTo w id o principal
  forms.filter fun f => offered f.action

/-- A spell's template with blanks for the fields whose value does not fit the form's kind. -/
def blankedTemplate (card : String) (form : Spell.Form) (given : List Spell.Binding) : String :=
  spellTemplate card form (given.filter fun b => match form.fields.find? (·.name == b.name) with
    | some f => (Spell.judge f b.value).isNone
    | none => false)

/-- The lenses of a card (WHOLENESS §2: a lens is a form): the fields its pure `lenses() ->
    Lists.List<Form.Field>` names, each with the kind of value it takes, when it also has a `set`
    method; none otherwise (also when `lenses()` is the sum dialect's list of `Form.Lens`, which is
    not data). A `fixed` State field is no lens, whatever `lenses()` says. -/
def declaredLenses (w : World) (o : Object) : List Spell.Field :=
  if !hasMethod o "set" || !o.declaresDef "lenses" then [] else
  let read : M (List Spell.Field) := do
    let some c ← tryCatch (some <$> compiledMethod o "lenses") (fun _ => pure none) | return []
    let some entry := c.entry | return []
    match runZero (defKey o "lenses") entry with
    | .ok d =>
      let form := Spell.Form.ofData (.record [("card", .label ""), ("action", .label "set"), ("fields", d)])
      return (form.map (·.fields)).getD []
    | .error _ => return []
  match (read.run.run (scratchState w)).1 with
  | .ok ls => ls.filter fun l => !o.fixed.contains l.name
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
  /-- A read the card renders (`Surfaces.answer`: the book, the chronicle, the map), answered as `?` is, with
      what a transport needs beside its text (`paint`, `ways`). -/
  | read (object text : String) (extra : List (String × Json))
  | refuse (object clause reason hint : String)
  /-- One of the host's own spells on any card (`become`, `adopt`, `lend`; `hostSpell`), a direct
      turn's only. -/
  | host (object action : String) (fields : List Spell.Binding)

/-- `receive` with the bare field lines (`Heard.fields`): completion is the card's policy. -/
def receiveHeard (w : World) (id : String) (o : Object) (argument : Data) (fields : List Spell.Binding)
    (cast : Option Data := none) : SpellRoute :=
  .run id "receive" ((heardArgument w o argument fields (cast := cast)).getD argument) ""

/-- `delvetalk <card> set` with one `<field>: <value>` line: the value is judged against the lens's
    kind (`badValue`) and the card's `set {field, value: Form.Value}` method runs with it
    (`inputOrigin.kind = "spell"`). No field line is completion, the card's policy (`receive` with the
    bare fields); a field no lens names, or more than one, is `unknownField`. -/
def lensSpell (w : World) (id : String) (argument : Data) (target : Object) (card : String) (lenses : List Spell.Field)
    (fields : List Spell.Binding) : SpellRoute :=
  match fields with
  | [] => receiveHeard w id target argument fields
  | [b] =>
    if target.fixed.contains b.name then .refuse id "fixed"
      s!"{b.name} is fixed; it is set when {card} is made and never after." (spellUsage card [] lenses) else
    match lenses.find? (·.name == b.name) with
    | none => .refuse id "unknownField"
        s!"No field {b.name} in this spell; it takes {", ".intercalate (lenses.map (·.name))}." (spellUsage card [] lenses)
    | some lens =>
      match Spell.judge lens b.value with
      | some (clause, reason) => .refuse id clause.name reason (lensTemplate card lens)
      | none =>
        .run id "set" (.record [("field", .label lens.name), ("value", lensValue (Spell.typed lens.kind b.value))]) (spellLine card "set")
  | _ => .refuse id "unknownField"
      s!"set takes one field a spell, not {", ".intercalate (fields.map (·.name))}" (spellUsage card [] lenses)

/-- The first ```obend fenced block of a reply: the lines after the opening fence up to a line that
    starts with ```; none when there is none or it is never closed. -/
def firstFence (text : String) : Option String := Id.run do
  let lines := text.splitOn "\n"
  let some start := lines.findIdx? (fun l => (l.dropWhile (· == ' ')).startsWith "```obend") | return none
  let body := lines.drop (start + 1)
  let some stop := body.findIdx? (fun l => (l.dropWhile (· == ' ')).startsWith "```") | return none
  return some ("\n".intercalate (body.take stop))

/-- The first code fence of a reply tagged exactly `tag` (```spween): the lines after it up to a line that starts with
    ```; none when there is none or it is never closed. -/
def taggedFence (tag : String) (text : String) : Option String := Id.run do
  let lines := text.splitOn "\n"
  let some start := lines.findIdx? (fun l => l.trimAscii.toString == "```" ++ tag) | return none
  let body := lines.drop (start + 1)
  let some stop := body.findIdx? (fun l => (l.dropWhile (· == ' ')).startsWith "```") | return none
  return some ("\n".intercalate (body.take stop))

/-- The fence tags the spell grammar reads as its own (a spell fenced whole, a plan, Bend): never a field's block. -/
def fenceWords : List String := ["text", "delvetalk", "plan", "obend"]

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

/-- What a rule's condition is, where a hand writes one: a level, held at every write; a crossing or a period by `changed`. -/
def levelLine : String :=
  "A rule fires at every write while its condition holds: count(new.lines) >= 3 fires at the third line and every one after. Once, as it crosses: count(new.lines) == 3 and changed(count(new.lines)); at each third: count(new.lines) % 3 == 0 and changed(count(new.lines))."

/-- A spell's fields, as parsed, with a block fenced with the name of a form field it does not name as that field's
    value (```spween under `delvetalk kind/room make / name: jar`), before the values without a name are bound, so
    words around the fence never take the field the fence names. -/
def withTagged (form : Spell.Form) (argument : Data) (fields : List Spell.Binding) : List Spell.Binding :=
  let text := match argument with
    | .record fs => ((fs.lookup "text").bind labelOf).getD ""
    | _ => ""
  if !text.contains '`' then fields else
  fields ++ form.fields.filterMap fun f =>
    if fenceWords.contains f.name || fields.any (Spell.fold ·.name == Spell.fold f.name) then none
    else (taggedFence f.name text).map ({ name := f.name, value := · })

/-- `delvetalk <card> rules` (docs/FOUNDATION.md §10): every rule the card carries, by name, owner,
    reading, condition and spell, and when it last fired (the entry and the receipt of the turn it
    delivered) or why it did not. -/
def rulesText (w : World) (id : String) (o : Object) (shown : String) : String :=
  let rules := carriedRules w id o
  let line := fun (things : Bool) (c : CarriedClause) =>
    let history := if things then "" else
      let row := ruleRow w id c
      let fired := (row.getObjVal? "fired").toOption.map fun f =>
        s!"fired at entry {(f.getObjValAs? Nat "height").toOption.getD 0}" ++
          ((f.getObjValAs? String "receipt").toOption.map (s!", receipt " ++ ·)).getD ""
      let unfired := (row.getObjVal? "unfired").toOption.map fun f =>
        s!"not fired at entry {(f.getObjValAs? Nat "height").toOption.getD 0}: {(f.getObjValAs? String "why").toOption.getD ""}"
      "  " ++ ((fired.orElse fun _ => unfired).getD "not fired yet") ++ "\n"
    let held := if c.holder == id then "" else s!", carried from {c.holder}"
    let reading := if c.clause.reading.isEmpty then "" else s!" {Delvetalk.Compiler.ObjectiveBendLaw.quoteReading c.clause.reading}"
    let owner := if things then "the thing" else shownName w c.owner
    let level := (c.clause.levelHint.map fun h => s!"  {h}\n").getD ""
    s!"» {c.clause.name} ({owner}{held}){reading}: when {c.clause.condition.render} then {(c.clause.modality.spell?.map (·.render)).getD ""}\n" ++ history ++ level
  match thingsText o with
  | some text =>
    let things := (clausesForThings w id o text).filter (Law.isRule ·.clause)
    s!"The rules of {shown}:\n\nfor its things (each acts as the thing):\n" ++
      (if things.isEmpty then "No rules.\n" else String.join (things.map (line true))) ++
      "\non the kind:\n" ++ (if rules.isEmpty then "No rules.\n" else String.join (rules.map (line false)))
  | none =>
    if rules.isEmpty then s!"{shown} carries no rules.\nTo place one: delvetalk {shown} rule / name: <name> / when: <condition> / then: <spell>\n{levelLine}\n" else
    s!"The rules {shown} carries:\n\n" ++ String.join (rules.map (line false))

/-- `delvetalk <card> verbs` (docs/FOUNDATION.md §10): the verbs the card takes, the ones its kind
    declares first, then each grown one with its grower, the entry that grew it, its reading, what it
    takes and the rule it does. -/
def verbsText (w : World) (o : Object) (shown : String) (declared : List Spell.Form) : String :=
  let given := if declared.isEmpty then "" else
    s!"Declared by its kind: {", ".intercalate (declared.map (·.action))}.\n"
  let grown := o.verbs.map fun v =>
    let takes := if v.takes.isEmpty then "" else " / text: <a line>"
    let reaction := if v.does.isEmpty then "" else s!"; reaction: rule {v.does}"
    s!"» {v.name} (grown by {shownName w v.grower}, entry {v.height}) {Delvetalk.Compiler.ObjectiveBendLaw.quoteReading v.reading}; does a line and a tend{reaction}\n  delvetalk {shown} {v.name}{takes}\n"
  let room := if o.offers actMethod then
      s!"\nTo grow one: delvetalk {shown} grow / name: <one word> / reading: <what it does>\n" else
      s!"\n{shown} has no act, so no verb grows on it.\n"
  s!"The verbs {shown} takes:\n\n{given}" ++ (if grown.isEmpty then "Grown here: none yet.\n" else "Grown here:\n" ++ String.join grown) ++ room

/-- The opener's powers on `world` and on a card (docs/ROOT.md §2.2). -/
def worldPowers : List String := ["quiet", "unquiet", "settings", "revoke"]
def cardPowers : List String := ["retire", "unretire", "hide", "show"]

/-- Would `o`'s law admit `principal`'s change of kind `kind` (1 reprogram, 2 amend) on the state as
    it stands? As `methodAdmits` judges a method. -/
def kindAdmitsBy (o : Object) (facts : Law.Facts) (kind : Nat) (verb : String := "") : Bool :=
  let facts := { facts with kind, verb }
  (o.law.find? fun (_, clause) => !Law.admits facts (some o.state) o.state clause).isNone

/-- `kindAdmitsBy` on the facts `admitFacts` gathers. -/
def kindAdmits (w : World) (o : Object) (principal : String) (kind : Nat) (id : String := "") (verb : String := "") : Bool :=
  kindAdmitsBy o (admitFacts w o principal id) kind verb

/-- `rule`'s and `want`'s fields as the usage prints them: the spell last, since its own fields follow it. -/
def ruleLine (target : String := "") : String := "name: <a name>\n" ++ target ++ "when: <a condition>\nthen: <a spell, holes {new.F} and {request.subject}>"

def wantLine (target : String := "") : String := s!"name: <a name>\n{target}when: <a condition on the thing as it stands>\nasks: <the spell that answers it>"
def forThingsLine : String := "for: <things, or leave it out for the kind itself>\n"
def growLine : String := "name: <one word>\nreading: <what it does>\ntakes: <text, or nothing>\ndoes: <a spell its use casts, or leave it out>\nbody: <a few lines of Bend in a <<BEND block, or leave it out>"

/-- `adopt`'s field as the usage prints it: a law written inline, or the id of what holds one. -/
def adoptLine : String := "law: law <name> \"<reading>\": <expression>, or a kind's or a page's id"

/-- The host actions the card's usage offers this hand, judged with the same facts as its methods. -/
def hostOfferedTo (w : World) (id : String) (o : Object) (principal : String) : String → Bool :=
  let facts := admitFacts w o principal id
  let things := (thingsText o).isSome && principal == ownerOf o.state && kindAdmitsBy o facts 2
  fun (action : String) => match action with
    | "become" => kindAdmitsBy o facts 1
    | "adopt" => kindAdmitsBy o facts 2
    | "lend" => ((offeredRows o.methods).getArr?.toOption.getD #[]).any fun (m : Json) =>
      match (m.getObjValAs? String "name").toOption with
      | some n => isActionRow m && methodAdmitsBy o facts n == Json.bool true
      | none => false
    | "rule" | "want" => kindAdmitsBy o facts 4 (verb := action) || things
    | "unrule" | "unwant" => things
    | "grow" => o.offers actMethod && kindAdmitsBy o facts 4 (verb := "grow")
    | "rules" | "wants" => true
    | "verbs" => o.offers actMethod
    | _ => false

/-- The host spells' templates a card's usage shows `principal`: those its law would admit them. -/
def hostUsage (w : World) (o : Object) (principal card : String) : String :=
  let id := namedCard w principal card
  let facts := admitFacts w o principal id
  let offered := hostOfferedTo w id o principal
  let target := if (thingsText o).isSome && principal == ownerOf o.state && kindAdmitsBy o facts 2 then forThingsLine else ""
  let lines := (if offered "become" then [s!"delvetalk {card} become\nkind: <a kind's id>\n"] else []) ++
    (if offered "adopt" then [s!"delvetalk {card} adopt\n{adoptLine}\n"] else []) ++
    (if offered "lend" then [s!"delvetalk {card} lend\nto: <a handle, or me>\nmethod: <one of its methods>\nuntil: +<clock units>\n"] else []) ++
    (if offered "rule" then [s!"delvetalk {card} rule\n{ruleLine target}\n"] else []) ++
    (if offered "want" then [s!"delvetalk {card} want\n{wantLine target}\n"] else []) ++
    (if target.isEmpty then [] else [s!"delvetalk {card} unrule\nname: <the rule's name>\n{target}",
      s!"delvetalk {card} unwant\nname: <the want's name>\n{target}"]) ++
    (if offered "grow" then [s!"delvetalk {card} grow\n{growLine}\n"] else []) ++
    [s!"delvetalk {card} rules\n", s!"delvetalk {card} wants\n"] ++
    (if o.offers actMethod then [s!"delvetalk {card} verbs\n"] else [])
  if lines.isEmpty then "" else "\nThe host's spells for any card:\n" ++ String.join (lines.map ("\n" ++ ·))

/-- Whether a filled want asks an action this reader is offered now. Reads pose descriptions,
    not work; unresolved holes, missing cards and hidden targets wait on other hands. -/
def wantAnswerable (w : World) (reader asks : String) : Bool :=
  match Spell.parse asks with
  | .spell card action _ =>
    let card := if Spell.fold card == meCard then meCard else card
    let id := namedCard w reader card
    match w.objects[id]? with
    | none => false
    | some o =>
      if !o.read.permits reader || action == "?" || hostReads.contains action || Surfaces.reads.contains action then false
      else if (spellForms w id o).any (fun (form : Spell.Form) => form.action == action) then offeredTo w id o reader action
      else hostOfferedTo w id o reader action
  | _ => false

/-- Holding wants stay descriptive on their card; answerability is derived for this reader. -/
def wantRows (w : World) (reader id : String) (o : Object) : List Json :=
  let facts := wantFacts w w.height id o (some reader)
  (posing w w.height id o (some reader)).map fun (c : CarriedClause) =>
    let since := ((w.wanting[id]?).bind (·.lookup c.clause.name)).map toJson |>.getD (toJson 0)
    let (asks, filled) := wantAsks facts id o c
    Json.mkObj ([("name", toJson c.clause.name), ("owner", toJson c.owner), ("when", toJson c.clause.condition.render),
        ("asks", toJson asks), ("answerable", toJson (filled && wantAnswerable w reader asks)),
        ("line", toJson c.clause.render), ("from", toJson c.holder), ("since", since)] ++
      (if c.clause.reading.isEmpty then [] else [("reading", toJson c.clause.reading)]))

structure Wanted where
  object : String
  name : String
  reading : String
  asks : String
  since : Nat
  answerable : Bool

/-- A derived page: waiting counts only visible held wants; next is the cursor in this day's ordering. -/
structure WantingPage where
  rows : List Wanted
  more : Bool
  waiting : Nat
  next : Nat

/-- Answerable wants, newest first by whole heights, or oldest-first discovery rotated by clock day.
    In discovery, after/next is an offset in the rotated list; pages stay within the row bound even
    at a shared height. No entry or root is written by this read. -/
def wanting (w : World) (reader : String) (after limit : Nat) (oldest : Bool := false) : WantingPage := Id.run do
  let held : List Wanted := w.wanting.toList.flatMap fun (entry : String × List (String × Nat)) =>
    let (id, xs) := entry
    match w.objects[id]? with
    | none => []
    | some o =>
      if !o.read.permits reader then [] else
      let holding := posing w w.height id o (some reader)
      let facts := wantFacts w w.height id o (some reader)
      xs.filterMap fun (indexed : String × Nat) =>
        let (name, since) := indexed
        (holding.find? (fun (c : CarriedClause) => c.clause.name == name)).map fun (c : CarriedClause) =>
          let (asks, filled) := wantAsks facts id o c
          { object := id, name, reading := c.clause.reading, asks, since,
              answerable := filled && wantAnswerable w reader asks }
  let (answerable, blocked) := held.partition (fun (r : Wanted) => r.answerable)
  let sorted := (answerable.toArray.qsort fun (a b : Wanted) =>
    (if oldest then a.since < b.since else a.since > b.since) ||
      (a.since == b.since && (a.object < b.object || (a.object == b.object && a.name < b.name)))).toList
  let cap := if limit == 0 then Limits.listPage else min limit Limits.listPage
  if oldest then
    let start := if sorted.isEmpty then 0 else (w.clock / Limits.clockDay) % sorted.length
    let rotated := sorted.drop start ++ sorted.take start
    let rest := rotated.drop after
    let page := rest.take cap
    return { rows := page, more := rest.length > page.length, waiting := blocked.length,
               next := min after sorted.length + page.length }
  let mut page : Array Wanted := #[]
  let mut rest := sorted.filter fun (r : Wanted) => after == 0 || r.since < after
  while true do
    let some first := rest.head? | break
    let group := rest.takeWhile (fun (r : Wanted) => r.since == first.since)
    unless page.isEmpty || page.size + group.length ≤ cap do break
    page := page ++ group.toArray
    rest := rest.drop group.length
  return { rows := page.toList, more := !rest.isEmpty, waiting := blocked.length,
             next := ((page.toList.getLast?).map (fun (r : Wanted) => r.since)).getD after }

/-- A row as Bend reads it (`World.Want`). -/
def wantedData (r : Wanted) : Data := .record [("object", .label r.object), ("name", .label r.name),
  ("reading", .label r.reading), ("asks", .label r.asks), ("since", .natural r.since)]

def wantingData (page : WantingPage) : Data := .record [("rows", listData (page.rows.map wantedData)),
  ("more", .boolean page.more), ("waiting", .natural page.waiting), ("next", .natural page.next)]

/-- The wire read shares the page the Bend query and the commonplace receive. -/
def wantingOp (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let nat := fun (k : String) => (j.getObjValAs? Nat k).toOption.getD 0
  let page := wanting w reader (nat "after") (nat "limit") ((j.getObjValAs? Bool "oldest").toOption.getD false)
  return Json.mkObj [("status", toJson "wanting"), ("more", toJson page.more),
    ("waiting", toJson page.waiting), ("next", toJson page.next), ("rows", Json.arr (page.rows.toArray.map fun (r : Wanted) =>
      Json.mkObj ([("object", toJson r.object), ("name", toJson r.name), ("asks", toJson r.asks), ("since", toJson r.since)] ++
        (if r.reading.isEmpty then [] else [("reading", toJson r.reading)]))))]

/-- `world-rules {object, principal?}`: every rule `object` carries (`ruleRow`), for a reader who may
    view it. `world-wants {object, principal?}`: the wants that hold of it now (`wantRows`). Derived
    reads: no root, no entry. -/
def rulesOp (w : World) (j : Json) (wants : Bool) : Except String Json := do
  let reader ← readerOf j
  let id ← j.getObjValAs? String "object"
  let some o := w.objects[id]? | return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  if !o.read.permits reader then return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
  let rows := if wants then wantRows w reader id o else (carriedRules w id o).map (ruleRow w id)
  return Json.mkObj [("status", toJson (if wants then "wants" else "rules")), ("object", toJson id), ("rows", Json.arr rows.toArray)]

/-- `delvetalk <card> wants`: the wants that hold of the card now, each with the spell that answers it
    and since when it has held. -/
def wantsText (w : World) (reader id : String) (o : Object) (shown : String) : String :=
  let rows := wantRows w reader id o
  let line := fun (row : Json) =>
    let text := fun (k : String) => (row.getObjValAs? String k).toOption.getD ""
    let since := match (row.getObjValAs? Nat "since").toOption with
      | some h => s!"since entry {h}"
      | none => "by the clock"
    let reading := if text "reading" == "" then "" else s!" {Delvetalk.Compiler.ObjectiveBendLaw.quoteReading (text "reading")}"
    let answerable := (row.getObjValAs? Bool "answerable").toOption.getD false
    let status := if answerable then "answerable" else "waiting on other hands"
    s!"» {text "name"}{reading} ({since}; {status}): {text "asks"}\n"
  match thingsText o with
  | some text =>
    let things := (clausesForThings w id o text).filter (Law.isWant ·.clause)
    let clauseLine := fun (c : CarriedClause) =>
      let held := if c.holder == id then "" else s!", carried from {c.holder}"
      let reading := if c.clause.reading.isEmpty then "" else s!" {Delvetalk.Compiler.ObjectiveBendLaw.quoteReading c.clause.reading}"
      s!"» {c.clause.name} (the thing{held}){reading}: when {c.clause.condition.render} asks {(c.clause.modality.spell?.map (·.render)).getD ""}\n"
    s!"The wants of {shown}:\n\nfor its things (each acts as the thing):\n" ++
      (if things.isEmpty then "No wants.\n" else String.join (things.map clauseLine)) ++
      "\non the kind (holding now):\n" ++ (if rows.isEmpty then "No wants.\n" else String.join (rows.map line))
  | none =>
    if rows.isEmpty then s!"{shown} wants nothing now.\n" else
    s!"What {shown} wants now:\n\n" ++ String.join (rows.map line)

/-- An object's card as `reader` sees it (asked by `caller` under `intent`, `cardContext`), run on its
    committed state under this turn's ticks: `renderWanting(state, context, wanting)` when the package
    declares it, handed what wants a hand across the world as the reader may view it (`wanting`, the
    daily rotated `Limits.cardWanting`, `wantingData`; derived, no root) as it is handed the reader; else
    `render`, which may take the state alone or `(state, context)`. `noCard` when it has neither, `render`
    when it fails or runs out. It runs on the stored state (`storedPure`): what it read of `id` is a root. -/
def renderCard (id : String) (o : Object) (reader caller intent : String) (whole : Bool := false) : M (Except String Data) := do
  let name := if o.declaresDef "renderWanting" then "renderWanting" else "render"
  let compiled ← tryCatch (some <$> compiledMethod o name) fun _ => pure none
  let some c := compiled | return .error "noCard"
  let w := (← get).world
  let context := fun (ct : Ty) => fitRecord c.bounds ct (cardContext w id reader caller intent w.height name whole)
  let arguments := match arrowDomains 3 c.type with
    | [_, ct] => [context ct]
    | [_, ct, _] => [context ct, wantingData (wanting w reader 0 Limits.cardWanting (oldest := true))]
    | _ => []
  match ← storedPure id o c arguments with
  | .ok value => return .ok value
  | .error _ => return .error "render"

/-- `delvetalk objects ?` (docs/METAPHYSICS.md §5): the cards `principal` may read under `prefix:`, in
    id order, twenty a reply, `after:` the last of the reply before. A principal's own cards (ids
    holding a DID) are listed only to a prefix that names one. -/
def objectsListing (w : World) (principal pfx after : String) : String :=
  let own := fun (id : String) => (id.splitOn "did:").length > 1 && (pfx.splitOn "did:").length == 1
  let ids := (w.objects.toList.filterMap fun (id, o) =>
    if id.startsWith pfx && decide (after < id) && !own id && o.read.permits principal then some id else none).toArray.qsort (· < ·)
  let page := (ids.extract 0 20).toList
  let under := if pfx.isEmpty then "" else s!" under {pfx}"
  if page.isEmpty then s!"No card{under} that you may read{if after.isEmpty then "" else s!" after {after}"}." else
  s!"The cards{under} you may read:\n" ++ String.join (page.map (s!"\n{·}")) ++
    (if ids.size > page.length then s!"\n\nMore: delvetalk objects ?\nprefix: {pfx}\nafter: {page.getLast!}\n" else "")

/-- The line every card's usage ends with: where the other cards are listed. -/
def objectsLine : String := "\nTo list the cards you may read: delvetalk objects ?\n"

/-- Why `me` names nothing yet. -/
def noAvatarReason : String := "You have no avatar here yet; your first arrival in the town makes one, and then me is it."

/-- `act`'s argument for a use of `verb` given as its own spell's fields. -/
def actArgument (verb : String) (argument : Data) : Data :=
  let text := match argument with
    | .record fs => ((fs.lookup "text").bind labelOf).getD ""
    | _ => ""
  .record [("verb", .label verb), ("text", .label text)]

/-- The receipt of the turn that made `id`: the first entry that touched it ("" when none is held). -/
def madeReceipt (w : World) (id : String) : String :=
  (((w.touched[id]?).bind (·[0]?)).bind w.entries.hashAt?).getD ""

/-- The workshop a verb grown with a body is written by (`growBody`). -/
def workshopId : String := "workshop"

/-- A grown verb's use as its card's `act` takes it: `{verb, text}`, the text "" when the verb takes
    none; none when `action` is no verb grown on `o` (a declared form shadows a verb of its name). -/
def grownAct (o : Object) (action : String) (argument : Data) : Option Data := do
  guard (!o.offers action)
  let _ ← o.verbs.find? (·.name == action)
  return actArgument action argument

/-- What a spell naming `card` and `action` with `fields` asks of card `self` (`o`), read for
    `principal`. `retarget`: a direct turn goes to the card the spell names; a call or a delivery
    reads only spells naming the card it was sent to (another is `otherCard`), since its sender chose
    that object. -/
def castSpell (w : World) (principal self : String) (argument : Data) (o : Object) (card action : String)
    (fields : List Spell.Binding) (retarget : Bool) (speaker : Bool := retarget) : SpellRoute := Id.run do
  -- A card's name is read in any case (docs/FLEX.md §4 host 2): `me` folded, and a name
  -- no object has as written is the one object whose id it folds to.
  let card := if Spell.fold card == meCard then meCard else card
  let id := namedCard w principal card
  -- The card as the speaker named it (`me`, a handle, never the DID): usage and reasons speak it.
  let shown := card
  -- The answering card's own spells when it has some; else where the doors are listed. What a reply only
  -- shows on a refusal (this usage, the target's offered forms and lenses) is built on the branch that shows it.
  let unknown := fun (_ : Unit) =>
    let here := usageForms w self o principal (spellForms w self o)
    if here.isEmpty then s!"no card named {card}; the commonplace lists the doors" else spellUsage self here
  -- The opener's powers on `world`, the id the host answers for.
  if id == worldId && !w.objects.contains worldId && worldPowers.contains action && retarget then
    return .host worldId action (fields.filter (·.name != ""))
  -- `delvetalk objects ?`, the listing no object answers.
  if Spell.fold card == objectsCard && !w.objects.contains objectsCard && action == "?" && retarget then
    let given := fun (n : String) => ((fields.find? (·.name == n)).map (·.value)).getD ""
    return .usage objectsCard (objectsListing w principal (given "prefix") (given "after"))
  let some target := w.objects[id]?
    | if card == meCard then
        return .refuse self "noAvatar" noAvatarReason (unknown ())
      else return .refuse self "otherCard" s!"There is no card {card}; the commonplace lists the doors." (unknown ())
  unless viewable w principal id && (retarget || id == self) do
    return .refuse self "otherCard" s!"There is no card {card}; the commonplace lists the doors." (unknown ())
  let forms := spellForms w id target
  -- The card's spells as the speaker is offered them, with its lenses (`set`'s: shown only when `set` is
  -- offered to the speaker), one admission judgement for them all.
  let usage := fun (_ : Unit) =>
    let offered := offeredTo w id target principal
    (forms.filter (offered ·.action), if offered "set" then declaredLenses w target else [])
  -- A read the card renders (the book, the chronicle, the map): its own definition, else, unless the card has
  -- a spell of that name, the square's from this card.
  if Surfaces.reads.contains action then
    let owns := forms.any (·.action == action) || target.verbs.any (·.name == action)
    match Surfaces.answer w principal id target action fields (fallback := !owns) with
    | some (.ok a) => return .read a.object a.text a.extra
    | some (.error (clause, reason)) =>
      let (shownForms, shownLenses) := usage ()
      return .refuse id clause reason (spellUsage shown (shownForms.filter (·.action == action)) shownLenses)
    | none => pure ()
  if action == "?" then
    let lineage := lineageLine w target
    let (shownForms, shownLenses) := usage ()
    return .usage id (spellUsage shown shownForms shownLenses ++ (if lineage.isEmpty then "" else "\n" ++ lineage) ++
      Surfaces.usage w principal id target shown (forms.map (·.action) ++ target.verbs.map (·.name)) ++
      hostUsage w target principal shown ++ objectsLine)
  if hostReads.contains action && !forms.any (·.action == action) then
    return .usage id (match action with
      | "rules" => rulesText w id target shown
      | "wants" => wantsText w principal id target shown
      | _ => verbsText w target shown ((usage ()).1.filter fun f => !target.verbs.any (·.name == f.action)))
  -- A verb grown with a body (docs/AUTHORING.md §3 (b)) is a one-method layer the workshop writes, checks
  -- and lays (or holds for the card's owner): its `growBody`, the speaker's turn.
  if action == "grow" && speaker && !forms.any (·.action == action) && w.objects.contains workshopId &&
      fields.any (fun b => b.name == "body" && !b.value.isEmpty) then
    let given := fun (n : String) => Data.label (((fields.find? (·.name == n)).map (·.value)).getD "")
    return .run workshopId "growBody" (.record [("object", .label id), ("name", given "name"), ("reading", given "reading"),
      ("takes", given "takes"), ("body", given "body")]) (spellLine card action)
  -- The host's own spells, on any card that does not define the action itself (`hostSpell`).
  if hostSpells.contains action && !forms.any (·.action == action) then
    if !speaker then
      let (shownForms, shownLenses) := usage ()
      return .refuse id "noAction" s!"{action} is a speaker's own spell, from a direct reply or a rule." (spellUsage shown shownForms shownLenses)
    return .host id action (fields.filter (·.name != ""))
  -- `set` with one `<field>: <value>` line goes through a lens (`lensSpell`).
  if action == "set" && !forms.any (·.action == "set") then
    let lenses := declaredLenses w target
    if !lenses.isEmpty || (hasMethod target "set" && !target.fixed.isEmpty) then
      return lensSpell w id argument target card lenses (fields.filter (·.name != ""))
  let some form := forms.find? (·.action == action)
    | return .refuse id "noAction" (s!"{shown} has no spell {action}; it has these" ++
        (if target.offers actMethod && verbWord action && kindAdmits w target principal 4 id "grow"
          then s!", and {action} grows on it: delvetalk {shown} grow / name: {action} / reading: <what it does>" else "") ++ ":")
        (let (fs, ls) := usage (); spellUsage shown fs ls)
  let fields := withFence w target action argument (Spell.bind form (withTagged form argument fields))
  match Spell.fit (.spell id action fields) form with
  | .proposal _ _ entries => match grownAct target action (spellArgument entries) with
    -- A grown verb runs the card's `act` with the verb (docs/FOUNDATION.md §10).
    | some a => return .run id actMethod a (spellLine card action)
    | none => match spellArgumentFor w target action entries with
    | .ok a => return .run id action a (spellLine card action)
    | .error reason => return .refuse id "badValue" reason (blankedTemplate shown form fields)
  | .unclear _ => return receiveHeard w id target argument fields (castData card action)
  | .refused clause reason => return .refuse id clause.name reason (blankedTemplate shown form fields)

/-- A `receive {text, …}` to `id`, read as a spell by the host when the card speaks the message
    dialect (WHOLENESS §2): a direct turn's, a called one's and a delivered one's alike (`retarget`
    only for a direct turn). `asIs` when the host leaves it as asked. -/
def routeSpell (w : World) (principal id method : String) (argument : Data) (retarget : Bool)
    (addressed : Bool := false) (speaker : Bool := retarget) : SpellRoute := Id.run do
  if method != "receive" then return .asIs
  let .record args := argument | return .asIs
  let some (.label text) := args.lookup "text" | return .asIs
  let some o := w.objects[id]? | return .asIs
  unless heardFits w o argument do return .asIs
  -- A direct reply to the card needs no `delvetalk` before one of its actions (docs/FLEX.md §4 host 2).
  let addressee := if addressed then some (id, (spellForms w id o).map (·.action)) else none
  match Spell.parseFor text addressee with
  | .spell card action fields => return castSpell w principal id argument o card action fields retarget speaker
  | .quotation reason => return .refuse id "quotation" reason (spellUsage id (spellForms w id o))
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

/-- The placements a placing spell names on `o` (`rule`, `want`, `grow` and their removals; KERNEL-HANDOFF
    §27, docs/FOUNDATION.md §10), from its fields (`value`) and the field that holds a spell (`spell`:
    `then`, `asks`, `does`, which a typed spell writes last), or the refusal `(clause, reason)`. A spell
    cast on a card, a world call (`world.rule` …) and a `call` of one on a card that does not declare it
    place alike.

    `grow` places a verb, judged by the card's law as a placing whose `request.verb` is `grow`; with
    `does`, the rule that gives it consequence is placed with it under the grower, `when: request.verb
    == "<name>"`; `ungrow` takes off the verb and the rule it does. -/
def placementsOf (o : Object) (id action : String) (value spell : String → Option String) :
    Except (String × String) (List Placement) := do
  let need := fun (key why : String) => match value key with
    | some v => Except.ok v
    | none => Except.error ("missingField", s!"{action} takes {key}: {why}.")
  let clauseOk := fun (line : String) => match Delvetalk.Compiler.ObjectiveBendLaw.parseClause line with
    | .ok _ => Except.ok ()
    | .error message => Except.error ("badValue", message)
  match action with
  | "rule" | "want" =>
    let want := action == "want"
    let key := if want then "asks" else "then"
    let name ← need "name" s!"a name new to {id}"
    let cond ← need "when" (if want then "a condition" else
      "a condition; a rule fires at every write while it holds, so once at a crossing is T == 3 and changed(T)")
    let some given := (spell key).filter (!·.isEmpty) | throw ("missingField", s!"{action} takes {key}: the spell, last.")
    let reading := ((value "reading").map fun r => " " ++ Delvetalk.Compiler.ObjectiveBendLaw.quoteReading r).getD ""
    let line := s!"{action} {name}{reading}: {cond} {key} {given}"
    clauseOk line
    return [{ object := id, what := if want then .want else .rule, name, line }]
  | "unrule" | "unwant" =>
    let name ← need "name" "the name it was placed under"
    return [{ object := id, what := if action == "unwant" then .want else .rule, name }]
  | "grow" =>
    let name ← need "name" "one word, the verb"
    let reading ← need "reading" "what the verb does"
    let some takes := match ((value "takes").getD "text").toLower with
        | "text" | "a line" | "line" => some "text"
        | "nothing" | "none" | "" => some ""
        | _ => none
      | throw ("badValue", "takes is text (a line) or nothing.")
    let verb : Placement := { object := id, what := .verb, name, line := reading, takes }
    match (spell "does").filter (!·.isEmpty) with
    | none => return [verb]
    | some given =>
      let line := s!"rule {name}: request.verb == {Lean.Json.compress (toJson name)} then {given}"
      clauseOk line
      return [{ verb with does := name }, { object := id, what := .rule, name, line }]
  | "ungrow" =>
    let name ← need "name" "the verb's name"
    -- The rule a verb does goes with it, while it stands.
    let does := ((o.verbs.find? (·.name == name)).map (·.does)).getD ""
    return [{ object := id, what := .verb, name }] ++
      (if !does.isEmpty && o.rules.any (·.name == does) then [{ object := id, what := .rule, name := does }] else [])
  | _ => throw ("noAction", s!"{action} places nothing.")

/-- The host's spells that place on a card (`placementsOf`). -/
def placingSpells : List String := ["rule", "want", "unrule", "unwant", "grow", "ungrow"]

/-- A placing's target is the object itself, or a kind's text for its things. The latter is a
    state amendment, judged by the kind's own law as kind 2 and journaled as its state edit. -/
def placingChange (w : World) (o : Object) (id action : String) (value spell : String → Option String) :
    Except (String × String) HostChange := do
  let target := (value "for").getD ""
  unless target.isEmpty || target == "things" do
    throw ("badValue", "for: things edits a kind's text for its things; leave for out for the object itself.")
  let xs ← placementsOf o id action value spell
  if target != "things" then return { world := w, roots := [(id, o.version)], placements := xs }
  unless ["rule", "want", "unrule", "unwant"].contains action do
    throw ("badValue", "for: things takes rule, want, unrule or unwant.")
  let some text := thingsText o | throw ("badValue", s!"{id} is no kind; for: things names a kind's text.")
  let clauses ← (parseClauses text).mapError (("badValue", ·))
  let some x := xs.head? | throw ("badValue", "Name one rule or want.")
  let after ← if x.line.isEmpty then
      let keyword := if action == "unwant" then "want" else "rule"
      unless clauses.any (fun c => c.name == x.name && c.modality.keyword == keyword) do
        throw ("badValue", s!"{id} has no {keyword} {x.name} for its things.")
      pure ("\n".intercalate ((clauses.filter fun c => !(c.name == x.name && c.modality.keyword == keyword)).map (·.render)))
    else appendedLaw { o with lawText := text, rules := [], wants := [] } id x.line
  let _ ← (parseClauses after).mapError (("badValue", ·))
  let written : Written :=
    { caller := "", kind := 2, method := action,
      edits := [(⟨"law", .set (.label after)⟩ : Edit)] }
  return { world := w, roots := [(id, o.version)], writes := [(id, [written])] }

/-- Stage the same placing a direct spell commits, including a kind's state-text amendment, against the
    turn's world (`turnWorld`: its earlier edits and placements). `admit` has the target's law judge it as
    the commit will, so a Bend body hears the verdict at once; a plan's host-spell act defers that verdict to
    its final commit. `check` returns the verdict without staging the change. -/
def stagePlacements (id action : String) (value spell : String → Option String) (check : Bool := false)
    (admit : Bool := true) : M (Option (String × String)) := do
  let s ← get
  let world ← currentWorld
  let some o := world.objects[id]? | return some ("unknownObject", s!"There is no card {id}.")
  match placingChange world o id action value spell with
  | .error e => return some e
  | .ok c =>
    recordRoot id ((s.world.objects[id]?).map (·.version) |>.getD o.version)
    let p : Proposal :=
      { principal := s.principal, intent := s.intent, roots := [(id, o.version)], writes := c.writes,
        placements := c.placements, turn := world.height + 1 }
    match (if admit then judge world (world.height + 1) p else stageProposal world (world.height + 1) p false) with
    | .error r => return some (r.clause.getD r.cls, (r.reading <|> r.voiced.reason).getD "")
    | .ok _ =>
      unless check do
        let steps := ((s.writes.lookup id).getD []) ++ ((c.writes.lookup id).getD [])
        let writes := if steps.isEmpty then s.writes else
          if s.writes.any (·.1 == id) then
            s.writes.map fun (k, ws) => if k == id then (k, steps) else (k, ws)
          else s.writes ++ [(id, steps)]
        modify fun s => { s with writes, placements := s.placements ++ c.placements }
      return none

/-- A record's text fields by name, as a placing call's argument gives them. -/
def labelsOf (argument : Data) : String → Option String := fun k => match argument with
  | .record fs => ((fs.lookup k).bind labelOf).filter (!·.isEmpty)
  | _ => none

/-- The limit a new wait on `self` would pass, by name, or none: awaits and interpretations waiting on
    one object are counted apart (`pendingActivitiesPerObject`, `pendingInterpretationsPerObject`), and
    the world's suspensions together (`maxSuspended`). -/
def waitFull (w : World) (self : String) (interpreting : Bool) : Option String :=
  let waiting := w.suspended.filter fun e =>
    let outcome := (e.getObjVal? "outcome").toOption
    (outcome.bind (·.getObjVal? "activity" |>.toOption) |>.bind (·.getObjValAs? String "object" |>.toOption)) == some self &&
      (outcome.bind (·.getObjVal? "interpretation" |>.toOption)).isSome == interpreting
  if waiting.size ≥ (if interpreting then Limits.pendingInterpretationsPerObject else Limits.pendingActivitiesPerObject) then
    some (if interpreting then "pendingInterpretationsPerObject" else "pendingActivitiesPerObject")
  else if w.suspended.size ≥ Limits.maxSuspended then some "maxSuspended"
  else none

/-- Why `principal` may not start a reading now, as the quota refusal's reading and the clock it lifts
    at: its interpretations this clock hour spent (`interpretQuota`; the opener and the clock principal
    are exempt), or the world's model calls this clock day (`modelQuota`, docs/OPERATIONS.md §b;
    nobody is exempt). None when it may. -/
def interpretGate (w : World) (principal : String) : Option (String × Nat) :=
  let hour := w.clock / 60
  let used := match w.interpretsStarted[principal]? with
    | some (h, n) => if h == hour then n else 0
    | none => 0
  let day := w.clock / Limits.clockDay
  if !(principal == w.opener || principal == w.clockPrincipal || used < w.interpretQuota) then
    some (s!"the interpreter has read {w.interpretQuota} this hour; reply with the spell itself, or wait.", (hour + 1) * 60)
  else if (if w.modelDay.1 == day then w.modelDay.2 else 0) ≥ w.modelQuota then
    some (s!"the world's {w.modelQuota} model readings for the day are spent; reply with the spell itself, or wait.", (day + 1) * Limits.clockDay)
  else none

/-- A suspension that is `object`'s wait on the clock for itself: an await on a slot whose principal is the
    object (which no hand acts as), by an activity of the object (`resumeSegment`, `awaitPlan`). -/
def selfWait (object : String) (sus : Json) : Bool :=
  let outcome := (sus.getObjVal? "outcome").toOption.getD Json.null
  let slot := (outcome.getObjVal? "slot").toOption.getD Json.null
  let act := (outcome.getObjVal? "activity").toOption.getD Json.null
  (slot.getObjValAs? String "principal").toOption == some object && (act.getObjValAs? String "object").toOption == some object

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
  let world ← currentWorld
  let some obj := world.objects[id]? | evaluation s!"unknown object {id}"
  -- Only a method the package makes public is asked from outside (a call or a run checked it).
  if depth == 0 && !s.receiver && !obj.offers method then throw (.refused "noMethod" (noMethodReason id method))
  -- `act` runs a verb grown on the card, never another (docs/FOUNDATION.md §10): its `request.verb`.
  if method == actMethod then
    let verb := actVerb method argument
    unless obj.verbs.any (·.name == verb) do
      throw (.refused "noMethod" s!"{id} has no verb {verb}; `delvetalk {id} verbs` lists the ones it takes, and grow adds one.")
  -- The frame reads its object by its cells: the scalar part, and the rows its segments force.
  recordCells id obj.version { scalar := true }
  let held := Held.of id obj.version obj
  let compiled ← compiledMethod obj method
  -- `receive` is heard with what the host fills where the sender left it out (`heardArgument`: `fields` empty, the
  -- `spell` read from the text, none for a mention, which is heard and never cast; `misfit` none), whoever sends it:
  -- a mention, a rule's firing or a send of `{text, post}`.
  let argument ← if method != "receive" || argumentFits compiled argument then pure argument else
    match heardArgument world obj argument [] (if s.reach == "mentioned" then some (castData "" "") else none) with
    | some filled => do modify (fun st => { st with argument := filled }); pure filled
    | none => pure argument
  -- What the method takes, with the card's declared bounds: built only for a refusal.
  let expectedNow : M Json := do return expectedInput obj id method compiled (← declaredForms obj).1
  -- A direct turn's argument came from outside: its text words are read as cases.
  let argument ← if depth == 0 && s.direct then
      match inputWords compiled argument with
      | .ok a => do modify (fun st => { st with argument := a }); pure a
      | .error (path, word, cases) =>
        throw (.refused "typeMismatch" (wordRefusal path word cases)
          (some ((← expectedNow).setObjVal! "cases" (Json.mkObj [("at", toJson path), ("given", toJson word), ("cases", toJson cases)]))))
    else pure argument
  let context := contextData id s.subject (handleShown s.world s.subject) s.world.opener caller s.intent s.world.height s.world.clock
    (if depth == 0 then s.origin else "call") (if depth == 0 && !s.command.isEmpty then s.command else method) s.post s.sender s.world.cardRoom
  let (arguments, r) ← match compiled.type with
    | .arrow _ _ _ (.arrow _ _ _ (.arrow _ _ ct r)) => pure ([storedState obj, argument, fitRecord compiled.bounds ct context], r)
    | .arrow _ _ _ (.arrow _ _ ct r) => pure ([storedState obj, fitRecord compiled.bounds ct context], r)
    | _ => throw (.request s!"method {method} must take (state, [input,] context)")
  unless argumentFits compiled argument do throw (.refused "typeMismatch" (misfitReason compiled method argument) (some (← expectedNow)))
  -- A direct turn's argument is held to the card's declared form bounds as a spell is (codex host
  -- 12, agent 3): one advertised action, one bound, whichever way it is asked.
  if depth == 0 && s.direct then
    if let some why := declaredMisfit method argument (← declaredForms obj).1 then
      throw (.refused "typeMismatch" why (some (← expectedNow)))
  match r with
  | .computation .. =>
    let b ← budgetsNow
    let binding := Delvetalk.Turn.Binding.make id s.principal s.intent (← get).roots
    let entry ← entryOf compiled
    let (started, reads) ← match Delvetalk.Turn.startEntry entry arguments held.store binding b compiled.dictionary with
      | .ok step => pure step
      | .error e => kernelRefusal (.error e) (some (← expectedNow))
    held.note reads
    noteProfile fun _ => (Delvetalk.Turn.storedStart entry arguments held.store |>.map fun (start, _) =>
      Delvetalk.Profile.profile ⟨b.heap, b.stack⟩ b.bytes b.ticks start held.store.bounded)
    drive depth id caller compiled binding held started 0
  | _ =>
    unless r.isDataUnder compiled.bounds compiled.rigid Ty.dataFuel [] do throw (.request s!"method {method} must be pure data or an activity")
    let st ← get
    let lim := st.limits.setObjVal! "ticks" (toJson (toString st.ticks))
    -- The held entry on the stored state, as cards run: no packet decode or re-check per call.
    let entry ← entryOf compiled
    match Package.executeDataEntryStored entry arguments.toArray held.store lim with
    | .error e => evaluation e
    | .ok (.refused failure usage, reads) =>
      held.note reads
      spend (usage.ticksUsed + usage.conversionNodes)
      evaluation failure
    | .ok (.finished value _ _ usage, reads) =>
      held.note reads
      spend (usage.ticksUsed + usage.conversionNodes)
      let .record fields := value | evaluation "a pure method must return the state record"
      addWrite id caller (fields.map fun (k, v) => (⟨k, .set v⟩ : Edit))
      return value

partial def drive (depth : Nat) (self caller : String) (compiled : Compiled) (binding : Delvetalk.Turn.Binding)
    (held : Held) (outcome : Delvetalk.Turn.Step) (_n : Nat) : M Data := do
  match outcome with
  | .finished value _ used => spend used; return value
  | .exhausted resource used =>
    spend used
    throw (.budget resource)
  | .refused line used =>
    spend used
    throw (.named (cardRefusal self line))
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
      | .variant "await" (.record f) | .variant "awaitUntil" (.record f) =>
        awaitPlan depth self compiled.bounds f responseType (← held.kept suspension).checkpoint
      | .variant "interpret" (.record f) => interpretPlan depth self compiled.bounds f responseType (← held.kept suspension).checkpoint
      | _ => do
        -- A frame in the extent of a `run` (its callee, or any frame that callee calls) offers each
        -- Plan to the handlers around it, innermost first; a `pass` goes to the next one out, and
        -- the host answers what every one passed.
        let mut handled : Option Data := none
        for (installed, handler) in (← get).handlers do
          if handled.isNone && installed ≤ depth then
            handled ← handleWith handler self message compiled.bounds responseType
        match handled, plan with
        | some response, _ => pure response
        | none, .variant tag (.record f) =>
          -- A call of another world's object suspends the turn (only `callVia` names a grant).
          match if tag == "call" || tag == "callVia" then (f.lookup "object").bind foreignRef else none with
          | some (world, id) =>
            let via := if tag == "callVia" then ((f.lookup "via").bind labelOf).getD "" else ""
            crossCall depth self compiled.bounds f world id via responseType (← held.kept suspension).checkpoint
          | none => answer depth self caller compiled.bounds plan responseType
        | none, _ => answer depth self caller compiled.bounds plan responseType
    let b ← budgetsNow
    let entry ← entryOf compiled
    -- A yield held in this process resumes from its machine state over the frame's store; no
    -- checkpoint is made.
    let (next, reads) ← liftEval (Delvetalk.Turn.resumeSuspended entry suspension held.store binding response b)
    held.note reads
    noteProfile fun _ => (Delvetalk.Turn.resumeState entry suspension.state suspension.site response |>.map fun (_, _, _, _, resumed) =>
      Delvetalk.Profile.profile (Delvetalk.Theory.ObjectiveBendDemandCollect.limitsPast ⟨b.heap, b.stack⟩ suspension.state)
        b.bytes b.ticks resumed held.store.bounded)
    drive depth self caller compiled binding held next 0

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
  -- A thing waits on the clock for itself once at a time (`selfWait`): the one wait whose end is a new cause.
  else if sp == self && s.world.suspended.any (selfWait self) then
    respond bounds responseType "refused" [.record [("clause", .label "waiting")]]
  else if s.awaits ≥ Limits.awaitsPerTurn then evaluation "turn exceeds the await capacity"
  else
    set { s with awaited := s.awaited ++ [key], awaits := s.awaits + 1 }
    match settled s.world sp si with
    | some entry => respond bounds responseType "reply" [receiptReply entry]
    | none =>
      if patience == 0 then respond bounds responseType "timedOut" [emptyRecord]
      else if patience > Limits.maxPatience then evaluation "await patience exceeds its capacity"
      else
        mayWait depth self checkpoint
        throw (.suspend sp si patience checkpoint)

/-- `call` of another world's object (docs/FEDERATION.md §2): the turn suspends on the slot `(principal,
    id)` and `serve` carries the call there (`Ops.outbound`), where it is a delivered turn under this turn's
    principal judged by that world's law alone; the `crossed` entry citing that world's receipt settles the
    slot, and the turn goes on with its result or its refusal (`crossedResponse`), or `timedOut` past
    `Limits.crossingPatience`. -/
partial def crossCall (depth : Nat) (self : String) (bounds : DataBounds) (f : List (String × Data))
    (world id via : String) (responseType : Ty) (checkpoint : Delvetalk.Turn.Checkpoint) : M Data := do
  let some method := (f.lookup "method").bind labelOf | evaluation "malformed call plan"
  let some argument := f.lookup "argument" | evaluation "malformed call plan"
  let s ← get
  if let some (clause, reading) := crossingRefusal s world via (some depth) then
    return ← refusedReading bounds responseType clause reading
  if s.awaits ≥ Limits.awaitsPerTurn then evaluation "turn exceeds the await capacity"
  mayWait depth self checkpoint
  let slot := Journal.bodyHash (Json.arr #[toJson s.principal, toJson s.intent, toJson world, toJson s.awaits])
  set { s with awaits := s.awaits + 1, crossings := s.crossings + 1 }
  throw (.suspend s.principal slot Limits.crossingPatience checkpoint (crossing := some (Json.mkObj
    [("world", toJson world), ("to", toJson id), ("method", toJson method), ("argument", dataJson argument),
     ("sender", toJson self)])))

/-- The capacities every suspension is held to; only the top of a turn may wait. Awaits and
    interpretations waiting on one object are counted apart (`pendingActivitiesPerObject`,
    `pendingInterpretationsPerObject`): every prose reply to a card waits for the model, and
    a batch of replies must not exhaust the slots awaits need. A full count refuses the turn
    `capacity`, naming the limit. -/
partial def mayWait (depth : Nat) (self : String) (checkpoint : Delvetalk.Turn.Checkpoint)
    (interpreting : Bool := false) : M Unit := do
  let s ← get
  if depth != 0 then evaluation "a wait inside a call is not supported"
  else if let some name := waitFull s.world self interpreting then throw (.refused "capacity" name)
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
  -- Words that reached no card go to no model (docs/FLEX.md §2): answered at once, no quota spent.
  if s.reach.isEmpty then
    return ← respond bounds responseType "unclear" [.record [("needs", listData [.label "not addressed"])]]
  match s.world.objects[policy]? with
  | none => respond bounds responseType "denied" [emptyRecord]
  | some o =>
    if !o.read.permits s.subject then respond bounds responseType "denied" [emptyRecord]
    else if utterance.utf8ByteSize > Limits.maxUtteranceBytes then evaluation "utterance exceeds its byte capacity"
    else if (dataJson offers).compress.utf8ByteSize > Limits.maxOffersBytes then
      evaluation "offers exceed their byte capacity"
    else if s.awaits ≥ Limits.awaitsPerTurn then evaluation "turn exceeds the await capacity"
    else
      if let some (reading, next) := interpretGate s.world s.principal then throw (.quota reading next)
      for card in offeredCards self offers do
        if let some target := s.world.objects[card]? then recordBehaviour card target
      let s ← get
      mayWait depth self checkpoint (interpreting := true)
      let id := interpretationSlot #[toJson s.principal, toJson s.intent, toJson s.awaits] s.behaviours
      set { s with awaits := s.awaits + 1 }
      throw (.suspend interpretationPrincipal id Limits.interpretationPatience checkpoint
        (some (Json.mkObj ([("id", toJson id), ("object", toJson self), ("policy", toJson policy),
          ("utterance", toJson utterance), ("offers", dataJson offers)] ++
          (if model.isEmpty then [] else [("model", toJson model)])))))

partial def answer (depth : Nat) (self caller : String) (bounds : DataBounds) (plan : Data) (responseType : Ty) : M Data := do
  -- Another world's object: a read is that world's answer; a call waits, which only `drive` may suspend.
  if let .variant tag (.record f) := plan then
    if let some (world, id) := (f.lookup "object").bind foreignRef then
      if foreignReads.contains tag then return ← foreignRead bounds responseType tag f world id
      if tag == "call" || tag == "callVia" then
        return ← refusedReading bounds responseType "crossing"
          s!"a call to {world} waits for its receipt, and only a turn's own method may wait; send it instead."
  match plan with
  | .variant "view" (.record f) =>
    match (f.lookup "object").bind referenceId with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some id =>
      let world ← currentWorld
      match world.objects[id]? with
      | none => respond bounds responseType "denied" [emptyRecord]
      | some o =>
        if !viewable world (← get).subject id then respond bounds responseType "denied" [emptyRecord] else
        recordRoot id o.version
        -- A state of another type than the call site's `S` is refused by name (a kind asking whether
        -- `of` names a kind), never an evaluation error.
        let viewed := Data.variant "viewed" (.record [("version", .natural o.version), ("state", o.state)])
        if viewed.conformsUnder bounds responseType then return viewed
        refusedWith bounds responseType "typeMismatch"
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
    | none => refusedReading bounds responseType "unknownObject" (callReading "unknownObject" "")
    | some id =>
      let world ← currentWorld
      let some calleeObj := world.objects[id]? | refusedReading bounds responseType "unknownObject" (callReading "unknownObject" id)
      -- A placing spell called on a card that does not declare it is the host's, as cast (hob's `grow:`).
      if via.isEmpty && placingSpells.contains method && !calleeObj.offers method then
        match ← stagePlacements id method (labelsOf argument) (labelsOf argument) with
        | some (clause, reading) => refusedReading bounds responseType clause reading
        | none => respond bounds responseType "returned" [.record [("result", emptyRecord)]]
      else
      -- A grown verb called by name is its card's `act` with the verb, as a spell of it is.
      let (method, argument) := match grownAct calleeObj method argument with
        | some a => (actMethod, a)
        | none => (method, argument)
      if helperOf world self id method then refusedReading bounds responseType "noMethod" (noMethodReason id method)
      else if depth + 1 > Limits.maxCallDepth then evaluation "call depth exceeded"
      else match ← grantFor via self id method argument with
        | .error clause => refusedReading bounds responseType clause s!"no grant lets this call run {method} on {id} ({clause})."
        | .ok (subject, argument) => do
          -- A called `receive` to a card of the message dialect is read as a spell, as a direct
          -- turn's is (never under a grant: it names the one method it may run).
          let world ← currentWorld
          let heard := heardPost method argument
          let route := if via.isEmpty then routeSpell world subject id method argument false else .asIs
          let (method, argument, refusal) := match route with
            | .run _ m a _ => (m, a, none)
            | .refuse _ clause reason _ => (method, argument, some (clause, reason))
            | _ => (method, argument, none)
          if let some (clause, reason) := refusal then refusedReading bounds responseType clause reason else
          if helperOf world self id method then refusedReading bounds responseType "noMethod" (noMethodReason id method) else
          let some calleeObj := world.objects[id]? | refusedReading bounds responseType "unknownObject" (callReading "unknownObject" id)
          let callee ← compiledMethod calleeObj method
          if !argumentFits callee argument then
            refusedReading bounds responseType "typeMismatch" (match extraField callee argument with
              | some f => s!"{id} {method} takes no field {f}."
              | none => callReading "typeMismatch" id (some (Json.mkObj [("method", toJson method)]))) else
          spendGrant via
          let result ← runMethod (depth + 1) id method argument self subject via heard
          respond bounds responseType "returned" [.record [("result", result)]]
  | .variant "run" (.record f) =>
    let some target := f.lookup "object" | evaluation "malformed run plan"
    let some method := (f.lookup "method").bind labelOf | evaluation "malformed run plan"
    let some argument := f.lookup "argument" | evaluation "malformed run plan"
    let some handler := (f.lookup "handler").bind referenceId
      | refusedReading bounds responseType "handler" "a run names its handler by reference."
    let s ← get
    match referenceId target >>= fun id => (s.world.objects[id]?).map (id, ·) with
    | none => refusedReading bounds responseType "unknownObject" (callReading "unknownObject" ((referenceId target).getD ""))
    | some (id, calleeObj) =>
      match s.world.objects[handler]? with
      | none => refusedReading bounds responseType "handler" s!"no handler {handler} that you may see; a run names an object whose handle() answers plans."
      | some h =>
        if !h.read.permits s.subject then refusedReading bounds responseType "handler" s!"no handler {handler} that you may see; a run names an object whose handle() answers plans."
        else if helperOf s.world self id method then refusedReading bounds responseType "noMethod" (noMethodReason id method)
        else if depth + 1 > Limits.maxCallDepth then evaluation "call depth exceeded"
        else
          let callee ← compiledMethod calleeObj method
          if !argumentFits callee argument then
            refusedReading bounds responseType "typeMismatch" (match extraField callee argument with
              | some f => s!"{id} {method} takes no field {f}."
              | none => callReading "typeMismatch" id (some (Json.mkObj [("method", toJson method)]))) else
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
                          programs := s.programs, layered := s.layered, madeFrom := s.madeFrom, laws := s.laws, absent := s.absent,
                          creates := s.creates, grants := s.grants, revokes := s.revokes, spent := s.spent,
                          cells := s.cells,
                          placements := s.placements, turn := w.height + 1 }
    let p := withLawReads w p
    -- What the verdict read is the turn's root too: a later move of it makes the answer stale (codex host 12).
    for (id, version) in p.roots do
      unless s.roots.any (·.1 == id) do recordRoot id version
    let (admitted, clause) := match judge w (w.height + 1) p with
      | .ok _ => (true, "")
      | .error r => (false, r.clause.getD r.cls)
    respond bounds responseType "judged" [.record [("admitted", .boolean admitted), ("clause", .label clause)]]
  | .variant "kindStack" (.record f) =>
    let some of := (f.lookup "of").bind labelOf | evaluation "malformed kindStack plan"
    let some body := (f.lookup "body").bind labelOf | evaluation "malformed kindStack plan"
    let some kindId := (f.lookup "kind").bind labelOf | evaluation "malformed kindStack plan"
    let some (.natural depth) := f.lookup "depth" | evaluation "malformed kindStack plan"
    let s ← get
    match kindStack s.world s.subject of body (min depth 4) with
    | .error (clause, reading) => refusedReading bounds responseType clause reading
    | .ok stack =>
      for (name, k) in stack.kinds do recordRoot name k.version
      respond bounds responseType "stacked" [.record [("package", .label stack.package),
        ("layers", listData (stack.layers.map Data.label)), ("form", .label stack.form),
        ("head", .label stack.head), ("voice", .label stack.voice), ("law", .label (kindCitation s.world kindId))]]
  | .variant "compose" (.record f) =>
    let some id := (f.lookup "object").bind referenceId | refusedWith bounds responseType "foreignWorld"
    let some kindId := (f.lookup "kind").bind labelOf | evaluation "malformed compose plan"
    let s ← get
    let some o := s.world.objects[id]? | refusedWith bounds responseType "unknownObject"
    match kindChange s.world s.principal o id kindId (!(s.creates.any (·.1 == id))) with
    | .error (clause, reading) => refusedReading bounds responseType clause reading
    | .ok c =>
      for (name, version) in c.roots do
        unless s.creates.any (·.1 == name) do recordRoot name version
      if let some r := c.refusal then
        return ← refusedReading bounds responseType (r.clause.getD r.cls) ((r.reason <|> r.reading).getD "")
      if let some (_, made) := s.creates.find? (·.1 == id) then
        let some creator := s.world.objects[made.creator]? | evaluation "the creating object vanished"
        let lineage := (c.madeFrom.lookup id).orElse fun _ => o.madeFrom
        let (inputs, _) ← match componentInputs o.inputs (lineageComponents o.madeFrom) (lineageComponents lineage) with
          | .ok x => pure x
          | .error e => evaluation e
        let modules ← match inputModules inputs with
          | .ok ms => pure ms
          | .error e => evaluation e
        let layers ← match (modules.toList.drop (modules.size - layersOf inputs)).mapM (fun m => m.getObjValAs? String "source") with
          | .ok ls => pure ls
          | .error e => evaluation e
        let text := (c.laws.lookup id).getD made.lawArg
        match buildCreated c.world creator made.package made.seedArg text s.principal (s.world.height + 1) layers with
        | .error (clause, reading) => refusedReading bounds responseType clause reading
        | .ok (again, built) =>
          for kind in (if c.programs.isEmpty then [] else [1]) ++ (if c.laws.isEmpty then [] else [2]) do
            let facts : Law.Facts := citing s.world o.law (lawNames o.law)
              { subject := s.principal, caller := self, height := s.world.height + 1,
                turn := s.world.height + 1, pin := again.object.pin, kind, clock := s.world.clock, object := id }
            if let some clause := Law.refusedBy o.law facts (some o.state) again.object.state then
              return ← refusedReading bounds responseType clause ((o.readings.lookup clause).getD s!"the law of {id} does not admit this component.")
          let lineage := match made.madeFrom, lineage with
            | some original, some installed => some (original.setObjVal! "components" ((installed.getObjVal? "components").toOption.getD (.arr #[])))
            | _, installed => installed
          let again := { again with object := { again.object with supervisor := o.supervisor }, madeFrom := lineage,
                                       creator := made.creator, package := made.package, seedArg := made.seedArg, lawArg := text, layers }
          modify fun t => { t with creates := t.creates.map (fun (name, r) => if name == id then (name, again) else (name, r)),
                                     world := madeIn (cacheBuild c.world again.object.inputs built) id again }
          respond bounds responseType "reprogrammed" [.record [("pin", .label again.object.pin)]]
      else
        if (!c.programs.isEmpty && s.programs.any (·.1 == id)) || (!c.laws.isEmpty && s.laws.any (·.1 == id)) then
          return ← refusedWith bounds responseType "duplicate"
        let proposer := if id == self then caller else self
        let change : Proposal := { principal := s.principal, intent := s.intent, roots := [], writes := [],
                                      programs := c.programs, layered := c.layered, madeFrom := c.madeFrom, laws := c.laws }
        for kind in (if c.programs.isEmpty then [] else [1]) ++ (if c.laws.isEmpty then [] else [2]) do
          if let some (clause, reading) := dryChange c.world s self id o.version proposer kind change then
            return ← refusedReading bounds responseType clause reading
          if !(← ensureWrite id proposer kind) then return ← refusedWith bounds responseType "capacity"
        modify fun t => { t with world := c.world, programs := t.programs ++ c.programs, layered := t.layered ++ c.layered,
                                   madeFrom := t.madeFrom ++ c.madeFrom, laws := t.laws ++ c.laws }
        let pin : Option String := match c.programs.lookup id with
          | some (source, migration) => (programFor c.world o source migration true (c.madeFrom.lookup id)).toOption.map (fun (prog : Program) => prog.pin)
          | none => some o.pin
        respond bounds responseType "reprogrammed" [.record [("pin", .label (pin.getD o.pin))]]
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
    -- An object this turn created is not made yet: an `extend` of it lays the layer into the making
    -- (the creation built again with it, judged by the made thing's law), so a kind makes a thing and
    -- grafts its body in one entry.
    if let some (_, made) := s.creates.find? (·.1 == id) then
      return ← extendCreation bounds responseType self id made source migration extend
    let some o := s.world.objects[id]? | refusedWith bounds responseType "unknownObject"
    -- Reprogramming another object is a change of it proposed by the running object: it reads
    -- the target, and the target's own law judges it with request.caller = the proposer.
    let proposer := if id == self then caller else self
    if s.programs.any (·.1 == id) then refusedWith bounds responseType "duplicate"
    else match programFor s.world o source migration extend with
      | .error (clause, message) =>
        -- What to correct goes back with the clause, where the call site's result has `reading`.
        refusedReading bounds responseType clause
          ((({ cls := "programRefused", clause := some clause, object := some id, reason := some message } : Refusal).voiced.reason).getD message)
      | .ok prog =>
        -- Another object's law is asked now, so the proposer never hears `reprogrammed` in a turn
        -- whose commit that law refuses.
        -- The verdict depends on the target as read: it is a root whatever the answer.
        recordRoot id o.version
        let world := cacheProgram s.world o source migration prog extend
        let change : Proposal := { principal := s.principal, intent := s.intent, roots := [], writes := [],
                                   programs := [(id, (source, migration))], layered := if extend then [id] else [] }
        match dryChange world s self id o.version proposer 1 change with
        | some (clause, reading) => refusedReading bounds responseType clause reading
        | none =>
        recordRoot id o.version
        if !(← ensureWrite id proposer 1) then refusedWith bounds responseType "capacity"
        else
          modify fun s => { s with world := cacheProgram s.world o source migration prog extend,
                                   programs := s.programs ++ [(id, (source, migration))],
                                   layered := if extend then s.layered ++ [id] else s.layered }
          respond bounds responseType "reprogrammed" [.record [("pin", .label prog.pin)]]
  -- The placing arms (docs/OVERHAUL.md §3; World.obend): `rule`, `want`, `grow` and their removals, each the
  -- host spell of that name as a Bend body casts it (a kind's `made` placing its rule), staged under the
  -- turn's principal, with its law verdict returned to the body (`stagePlacements`).
  | .variant "rule" (.record f) | .variant "unrule" (.record f) | .variant "want" (.record f)
  | .variant "unwant" (.record f) | .variant "grow" (.record f) | .variant "ungrow" (.record f) =>
    let action := match plan with | .variant a _ => a | _ => ""
    let some id := (f.lookup "object").bind referenceId | refusedReading bounds responseType "foreignWorld" "a placing names an object of this world."
    let some _ := (← currentWorld).objects[id]? | refusedReading bounds responseType "unknownObject" (callReading "unknownObject" id)
    let check := match f.lookup "check" with
      | some (.boolean b) => b
      | _ => false
    match ← stagePlacements id action (labelsOf (.record f)) (labelsOf (.record f)) (action == "ungrow" && check) with
    | some (clause, reading) => refusedReading bounds responseType clause reading
    | none => respond bounds responseType "placed" [emptyRecord]
  -- `act {object, verb, text}`: a use of a grown verb, as its spell is (the target's `act`, `request.verb` the verb).
  | .variant "act" (.record f) =>
    let some object := f.lookup "object" | evaluation "malformed act plan"
    let argument := Data.record [("verb", (f.lookup "verb").getD (.label "")), ("text", (f.lookup "text").getD (.label ""))]
    answer depth self caller bounds (.variant "call" (.record [("object", object), ("method", .label actMethod), ("argument", argument)])) responseType
  -- `chronicle {day}`: the day's lines (`Ops.chronicle`), as the turn's subject may read them; derived, no root.
  | .variant "chronicle" (.record f) =>
    let s ← get
    let day := match f.lookup "day" with | some (.natural d) => d | _ => s.world.clock / Limits.clockDay
    respond bounds responseType "chronicled"
      [.record [("day", .natural day), ("lines", listData ((chronicle s.world s.subject day).map Data.label))]]
  -- `wanting {after, limit}`: what wants a hand across the world (`wanting`), as the turn's subject may
  -- view it; derived, no root.
  | .variant "wanting" (.record f) =>
    let nat := fun (k : String) => match f.lookup k with | some (.natural n) => n | _ => 0
    let s ← get
    let oldest := match f.lookup "oldest" with | some (.boolean b) => b | _ => false
    let page := wanting s.world s.subject (nat "after") (nat "limit") oldest
    respond bounds responseType "wanting" [wantingData page]
  -- `holds {object, when}`: a condition in the law's grammar (FOUNDATION §4) judged of `object` as it stands, by the
  -- one `denote`, at the clock, `request.subject` the turn's subject (a scene's guard, world/lib/Scenes.obend): no
  -- `old`, nothing written. The object and every object the condition cites are roots, each the subject's to view.
  | .variant "holds" (.record f) =>
    let some id := (f.lookup "object").bind referenceId | refusedReading bounds responseType "foreignWorld" "a condition reads an object of this world."
    let some text := (f.lookup "when").bind labelOf | evaluation "malformed holds plan"
    let s ← get
    let some o := s.world.objects[id]? | refusedReading bounds responseType "unknownObject" (callReading "unknownObject" id)
    match Delvetalk.Compiler.ObjectiveBendLaw.parse text with
    | .error message => refusedReading bounds responseType "badValue" message
    | .ok expr =>
      match Law.standingRefusal expr with
      | some what => refusedReading bounds responseType "badValue" s!"a condition read as it stands reads no old, no change and no under: {what}"
      | none =>
      let names := expr.names
      let cited := (citesOf s.world names).objects
      match unviewable s.world s.subject (id :: cited) with
      | some r => refusedReading bounds responseType "reads" s!"{r} is not the reader's to view."
      | none =>
        recordRoot id o.version
        for r in cited do
          if let some c := s.world.objects[r]? then recordRoot r c.version
        let facts := citing s.world o.law names
          { subject := s.subject, caller := self, height := s.world.height + 1, turn := s.world.height + 1,
            clock := s.world.clock, object := id }
        respond bounds responseType "held" [.record [("value", .boolean (Law.denote facts none (viewFor names o.cells) expr))]]
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
        | some (clause, reading) => refusedReading bounds responseType clause reading
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
        -- `source: false` answers "" for the source (a long one costs a reader ticks it never needs).
        let withSource := match f.lookup "source" with
          | some (.boolean b) => b
          | _ => true
        let shown := [("pin", Data.label o.pin), ("law", .label o.lawText), ("source", .label (if withSource then entrySource o else ""))]
        let id := ((f.lookup "object").bind referenceId).getD ""
        -- What the turn learnt (pin, law, source) is the object's now: a root (codex host 11).
        recordRoot id o.version
        let offered := (← formsOf id o).filter (offeredTo s.world id o s.subject <| formAction ·)
        let methods := ("methods", listData offered)
        -- The clauses with their readings, and the actions offered to the asking principal.
        let laws := ("laws", listData (lawRowsOf o |>.map fun (n, c, r) => .record [("name", .label n), ("clause", .label c), ("reading", .label r)]))
        let names := ("offered", listData (offered.map (Data.label ∘ formAction)))
        respond bounds responseType "inspected"
          [.record (shown ++ [methods, laws, names]), .record (shown ++ [methods]), .record shown]
  -- `principal {handle}`: the principal the registry names by a handle (`me`, the turn's subject), so `offer`
  -- and `lend` to a handle work from Bend.
  | .variant "principal" (.record f) =>
    let some handle := (f.lookup "handle").bind labelOf | evaluation "malformed principal plan"
    let s ← get
    match if handle == meCard then some s.subject else principalNamed s.world handle with
    | some did => respond bounds responseType "named" [.record [("principal", .label did)]]
    | none => respond bounds responseType "unknown" [emptyRecord]
  -- `receipt {name}`: an entry of this town's journal, or of a chain it was carried from, named by its CID or its
  -- slug (`Ops.receiptNamed`): `found {cid, height, principal}`, `ambiguous {count}`, `unknown`. Read from the chain
  -- as the turn reads it, every entry before its own, which is append-only: no root (a register's anchors,
  -- world/bodies/register.obend).
  | .variant "receipt" (.record f) =>
    let some name := (f.lookup "name").bind labelOf | evaluation "malformed receipt plan"
    let s ← get
    match receiptNamed s.world name with
    | .found cid height principal =>
      respond bounds responseType "found" [.record [("cid", .label cid), ("height", .natural height), ("principal", .label principal)]]
    | .ambiguous count => respond bounds responseType "ambiguous" [.record [("count", .natural count)]]
    | .unknown => respond bounds responseType "unknown" [emptyRecord]
  | .variant "objects" (.record f) =>
    let some pfx := (f.lookup "prefix").bind labelOf | evaluation "malformed objects plan"
    let some after := (f.lookup "after").bind labelOf | evaluation "malformed objects plan"
    let s ← get
    let (ids, more) := listIds s.world s.subject pfx after
    respond bounds responseType "listed" [.record [("ids", listData (ids.map Data.label)), ("more", .boolean more)]]
  | .variant "changed" (.record f) =>
    let some (.natural since) := f.lookup "since" | evaluation "malformed changed plan"
    let some pfx := (f.lookup "prefix").bind labelOf | evaluation "malformed changed plan"
    let some after := (f.lookup "after").bind labelOf | evaluation "malformed changed plan"
    let s ← get
    let (items, more) := changedSince s.world s.subject since pfx after
    let item := fun (c : Change) =>
      let handle := handleShown s.world c.principal
      Data.record [("object", .record [("world", .label ""), ("object", .label c.object)]), ("version", .natural c.version), ("height", .natural c.height),
        ("by", .label (if handle.isEmpty then c.principal else handle))]
    respond bounds responseType "changed" [.record [("items", listData (items.map item)), ("more", .boolean more)]]
  | .variant "card" (.record f) =>
    let s ← get
    match (f.lookup "object").bind referenceId >>= fun id => (s.world.objects[id]?).map (id, ·) with
    | none => respond bounds responseType "denied" [emptyRecord]
    | some (id, o) =>
      if !o.read.permits s.subject then respond bounds responseType "denied" [emptyRecord] else
      -- What the card shows is its code's on the scalar part and the rows it forced (`storedPure`).
      recordCells id o.version { scalar := true }
      match ← renderCard id o s.subject self s.intent with
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
      recordCells id o.version { scalar := true }
      let context := contextData id s.subject (handleShown s.world s.subject) s.world.opener self s.intent s.world.height s.world.clock "view" view s.post s.sender
        s.world.cardRoom
      match ← derivedView id o view context with
      | .ok value => respond bounds responseType "derived" [.record [("version", .natural o.version), ("value", value)]]
      | .error clause => refusedWith bounds responseType clause
  -- `check {package, layers}`: `package` as `create` takes it, with `layers` laid over it (`checkStack`).
  | .variant "check" (.record f) =>
    let some (.label source) := f.lookup "package" | evaluation "malformed check plan"
    let some layers := (f.lookup "layers").bind (labels []) | evaluation "malformed check plan"
    let s ← get
    let some creator := s.world.objects[self]? | evaluation "the checking object vanished"
    if s.checks ≥ Limits.checksPerTurn then evaluation "turn exceeds the check capacity"
    set { s with checks := s.checks + 1 }
    respond bounds responseType "checked" (checkedData (checkStack s.world creator source layers))
  -- `checkObject {object, layers}`: what a readable object runs, its whole closure, with `layers` laid
  -- over it (`Ops.checkObject`).
  | .variant "checkObject" (.record f) =>
    let some layers := (f.lookup "layers").bind (labels []) | evaluation "malformed check plan"
    let s ← get
    match (f.lookup "object").bind referenceId >>= fun id => (s.world.objects[id]?) with
    | some o =>
      if !o.read.permits s.subject then refusedWith bounds responseType "unknownObject" else
      if s.checks ≥ Limits.checksPerTurn then evaluation "turn exceeds the check capacity"
      set { s with checks := s.checks + 1 }
      respond bounds responseType "checked" (checkedData (checkObject s.world o layers))
    | none => refusedWith bounds responseType "unknownObject"
  | .variant "create" (.record f) | .variant "createUnder" (.record f) | .variant "make" (.record f) =>
    let some package := (f.lookup "package").bind labelOf | evaluation "malformed create plan"
    -- `make` (docs/GROUND.md §6 changes 1 and 6): the create, from source a resident supplied, with
    -- its lineage `madeFrom {object, receipt}`, to which the host adds the pin `object` runs now; the
    -- object and the receipt must be the journal's.
    let (madeFrom, unmade) ← (match plan with
      | .variant "make" _ => do
        let some (.record m) := f.lookup "madeFrom" | evaluation "malformed make plan"
        let some fromId := (m.lookup "object").bind referenceId | evaluation "malformed make plan"
        let some receipt := (m.lookup "receipt").bind labelOf | evaluation "malformed make plan"
        let s ← get
        -- An empty receipt cites the turn that made `object` (a kind forked whole: its maker's).
        let receipt := if receipt.isEmpty then madeReceipt s.world fromId else receipt
        match s.world.objects[fromId]? with
        | none => pure (none, some s!"there is no object {fromId} to have been made from")
        | some fromObj =>
          if (s.world.entries.indexOf? receipt).isNone then
            pure (none, some s!"there is no receipt {receipt} in the journal")
          else do
            recordRoot fromId fromObj.version
            pure (some (Json.mkObj [("object", toJson fromId), ("pin", toJson fromObj.pin), ("receipt", toJson receipt)]), none)
      | _ => pure (none, none) : M (Option Json × Option String))
    if let some reason := unmade then refusedReading bounds responseType "madeFrom" reason else
    -- `createUnder` names the child's supervisor; it must be an object now.
    let supervisor := ((f.lookup "supervisor").bind referenceId).getD ""
    let some seed := f.lookup "seed" | evaluation "malformed create plan"
    let lawArg := ((f.lookup "law").bind labelOf).getD ""
    let some target := f.lookup "requireAbsent" | evaluation "malformed create plan"
    let some named := referenceId target | refusedWith bounds responseType "foreignWorld"
    -- An empty `requireAbsent` asks the host to mint the child's id; one ending in `/` names the
    -- prefix to mint under, the first free `<prefix><n>` (a kind numbering a garden's bells past ids
    -- someone already holds).
    let id ← if named.isEmpty then mintId self package
      else if named.endsWith "/" then mintUnder named else pure named
    let s ← get
    let note := fun (s : TurnState) => { s with absent := if s.absent.contains id then s.absent else s.absent ++ [id] }
    if !validObjectId id || id == "self" || id == meCard then
      refusedWith bounds responseType "objectId"
    else if s.world.objects.contains id || s.creates.any (·.1 == id) then
      -- The reply says so now; the turn will be refused at its commit, naming the root.
      set { note s with violation := s.violation.orElse (fun _ => some id),
                        violator := if s.violation.isSome then s.violator else self }
      refusedWith bounds responseType "requiredAbsence"
    else if s.creates.length ≥ Limits.createsPerTurn || s.absent.length ≥ Limits.maxRoots then
      refusedWith bounds responseType "capacity"
    -- A supervisor other than the creator itself must offer `ended`: the creator chooses it, not
    -- the object told (codex host 6).
    else if !supervisor.isEmpty && supervisor != self &&
        !((s.world.objects[supervisor]?).map (·.offers "ended")).getD false then
      refusedWith bounds responseType "supervisor"
    else
      let some creator := s.world.objects[self]? | evaluation "the creating object vanished"
      match buildCreated s.world creator package seed lawArg s.principal (s.world.height + 1) with
      -- The checker's diagnostic goes back with the clause, where the call site's result has `reading`.
      | .error (clause, message) => refusedReading bounds responseType clause message
      | .ok (made, built) =>
        let made := { made with object := { made.object with supervisor }, madeFrom, creator := self, package,
                                seedArg := seed, lawArg }
        set { note s with creates := s.creates ++ [(id, made)], world := madeIn (cacheBuild s.world made.object.inputs built) id made }
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
    | none =>
      -- A send to another world's object leaves with the commit for `serve` to carry (`Ops.outbound`).
      let some (world, id) := foreignRef target | refusedWith bounds responseType "foreignWorld"
      let s ← get
      if let some (clause, _) := crossingRefusal s world via none then return ← refusedWith bounds responseType clause
      if s.sends.length ≥ Limits.sendsPerTurn then evaluation "turn exceeds the send capacity"
      if s.world.pending.size + s.sends.length ≥ Limits.maxPending then
        evaluation "world exceeds the pending delivery capacity"
      let delivery := deliveryId s.principal s.intent s.sends.length
      set { s with sends := s.sends ++ [({ to := id, world, method, argument, sender := self } : Send)], crossings := s.crossings + 1 }
      respond bounds responseType "delivery" [.record [("id", .label delivery)]]
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
      let staged : Send := { to := id, method, argument, sender := self, via, grantor := if via.isEmpty then "" else subject,
                             reach := if method == "receive" && s.reach != "delivery" then some s.reach else none }
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
      else if (f.lookup "fixed").any (fun d => (Delvetalk.Canonical.encode d).size > Delvetalk.Bounds.maxCellBytes) then
        refusedWith bounds responseType "capacity"
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

/-- A read Plan of world `w`'s object, answered as `answer` answers it there for `reader` (`Foreign.read`):
    what `serve` runs for a turn of another world that reads it. Nothing it records is kept but the ticks
    it spent and the citation of the object read (`{world, object, version, stateCid, height, head}`, `world`
    as the reader named it), which is null when the reader was denied or refused. -/
def readIn (w : World) (world : String) (plan : Data) (responseType : Ty) (bounds : DataBounds) (reader : String)
    (ticks : Nat) : Data × Json × Nat :=
  let init : TurnState := { world := w, principal := reader, intent := "", subject := reader, ticks,
                            limits := Json.mkObj [] }
  match (answer 0 "" "" bounds plan responseType).run.run init with
  | (.ok answer, st) =>
    let id := match plan with
      | .variant _ (.record f) => ((f.lookup "object").bind referenceId).getD ""
      | _ => ""
    let read := match answer with
      | .variant tag _ => tag != "denied" && tag != "refused"
      | _ => false
    let cite := match w.objects[id]? with
      | some o => if !read then Json.null else Json.mkObj [("world", toJson world), ("object", toJson id),
          ("version", toJson o.version), ("stateCid", toJson o.stateCid), ("height", toJson w.height), ("head", toJson w.head)]
      | none => Json.null
    (answer, cite, st.ticks)
  | (.error _, st) => (.variant "denied" (.record []), Json.null, st.ticks)

def offersJson (offers : List (String × String)) : Json :=
  Json.arr (offers.toArray.map fun (to, text) => Json.mkObj [("to", toJson to), ("text", toJson text)])

/-- An admitted entry's three host-rendered lines (docs/FOUNDATION.md §5; docs/OVERHAUL.md §2 "The revealing
    reply"), each left out when empty: **what it moved** (each rule it fired, with the spell it cast under
    its owner's name, or why one that held did not fire), **what it opened or closed** (each want of a
    written thing that came to hold, with the spell that answers it, or stopped holding), and **where it
    stands** (each relation it added rows to: how many it holds now, crediting its first row's author
    when it is another principal's or the speaker just added it), said only while the thing is at the
    version the entry wrote, so a later read of an old receipt never gives today's count as the entry's.
    From the entry and the world after it; no model. -/
def revealed (w : World) (entry : Json) : List String := Id.run do
  if tagOf entry != "admitted" then return []
  -- A plan's acts first, one line each, in order (docs/HOST-HANDOFF.md 5.203).
  let acts := (((entry.getObjVal? "plan").toOption.bind (·.getObjVal? "acts" |>.toOption)).bind (·.getArr?.toOption)).getD #[]
  let planned := acts.toList.map fun a =>
    let t := fun (k : String) => (a.getObjValAs? String k).toOption.getD ""
    let made := ((a.getObjVal? "made").toOption.bind (·.getArr?.toOption)).getD #[]
    let did := if !made.isEmpty then "made " ++ ", ".intercalate (made.toList.filterMap (·.getStr?.toOption))
      else match t "done" with | "staged" => "placed" | "read" => "read" | _ => "done"
    s!"{(a.getObjValAs? Nat "act").toOption.getD 0}. {t "spell"}: {did}" ++ (if t "done" == "read" then "\n" ++ t "text" else "")
  let principal := ((entry.getObjVal? "identity").toOption.bind fun i => (i.getObjValAs? String "principal").toOption).getD ""
  let rows := fun (k : String) => (((entry.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]).toList
  let text := fun (j : Json) (k : String) => (j.getObjValAs? String k).toOption.getD ""
  let moved := (rows "fired").map (fun f =>
      let said := (((f.getObjVal? "argument").toOption.bind fun a => (decodeData Limits.dataDepth a).toOption).bind
        fun d => textField d "text").getD ""
      let queued := ((f.getObjValAs? Nat "next").toOption.map fun n => s!" (queued until clock {n})").getD ""
      s!"rule {text f "rule"} of {shownName w (text f "principal")} fired{queued}: {shownSpell w said}") ++
    (rows "unfired").map fun f =>
      s!"rule {text f "rule"} of {shownName w (text f "owner")} did not fire: {unfiredWords (text f "why")}"
  let asked := fun (id name : String) => ((w.objects[id]?).map fun o => wantRows w principal id o).getD [] |>.find? fun r =>
    (r.getObjValAs? String "name").toOption == some name
  let opened := (rows "wanted").map (fun x =>
      let id := text x "object"
      let asks := ((asked id (text x "want")).bind fun r => (r.getObjValAs? String "asks").toOption).getD ""
      s!"{id} now wants {text x "want"}" ++ (if asks.isEmpty then "" else s!": {asks}")) ++
    (rows "unwanted").map fun x => s!"{text x "object"} no longer wants {text x "want"}"
  -- Where it stands: each relation a write inserted into, its count now, and its actual first row's author.
  let writes := ((((entry.getObjVal? "outcome").toOption.bind (·.getObjVal? "writes" |>.toOption)).map
    fun j => (parseRecordedWrites j).toOption.getD []).getD [])
  let wrote := fun (id : String) => ((((entry.getObjVal? "outcome").toOption.bind (·.getObjVal? "writes" |>.toOption)).bind
    (·.getArr?.toOption)).getD #[]).findSome? fun x =>
      if (x.getObjValAs? String "object").toOption == some id then (x.getObjValAs? Nat "version").toOption else none
  let mut stands : List String := []
  for (id, ws) in writes do
    let some o := w.objects[id]? | continue
    unless wrote id == some o.version do continue
    let inserted := ws.flatMap fun x => x.edits.filterMap fun e => match e.kind with
      | .insert row | .upsert row => some (e.field, row)
      | _ => none
    for field in (inserted.map (·.1)).eraseDups do
      let some now := o.cells.relation? field | continue
      let added := (inserted.filter (·.1 == field)).map (·.2)
      let addedKeys := added.map fun r => (Delvetalk.Turn.RowCell.of now.key r).key
      let credit := match now.rows[0]? with
        | some c => match Law.rawField "author" c.row with
          | some (.label author) =>
            if !author.isEmpty && (author != principal || addedKeys.contains c.key) then s!", the first by {shownName w author}" else ""
          | _ => ""
        | none => ""
      stands := stands ++ [s!"{id}'s {field}: {now.rows.size}" ++ credit]
  return planned ++ [moved, opened, stands].filterMap fun ls => if ls.isEmpty then none else some ("; ".intercalate ls)

/-- The `revealed` field of a reply to an admitted entry, left out when it has no line. -/
def revealedField (w : World) (entry : Json) : List (String × Json) :=
  let lines := revealed w entry
  if lines.isEmpty then [] else [("revealed", toJson lines)]

/-- Whether everyone may read what an admitted entry read and wrote (every object of its roots and writes, as the
    public reader may view them now): a post, which everyone reads, carries what the turn offered only then, else its
    receipt line alone. Answered as `inPublic` on its reply and receipt, so a draft asks the host nothing more. -/
def inPublic (w : World) (entry : Json) : List (String × Json) :=
  if tagOf entry != "admitted" then [] else
  let arr := fun (j : Json) (k : String) => ((j.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]
  let objects := (arr entry "roots" ++ arr ((entry.getObjVal? "outcome").toOption.getD Json.null) "writes").toList.filterMap
    (·.getObjValAs? String "object" |>.toOption)
  [("inPublic", toJson (objects.all (viewable w "" ·)))]

/-- A law's refusal that teaches (a world with more than one post's room, `cardRoom`): whose law it is, and the one line
    that has it your way, your own thing of its kind or your own kind over it; none for any other refusal, or a world
    whose cards are post-sized (its refusal reads as before). Said in the reply, never journaled. -/
def teaching (w : World) (entry : Json) : Option String := do
  guard (w.cardRoom > Limits.cardShownChars && tagOf entry == "refused")
  let outcome ← (entry.getObjVal? "outcome").toOption
  guard ((outcome.getObjValAs? String "class").toOption == some "lawRefused")
  let id ← (outcome.getObjValAs? String "object").toOption
  let o ← w.objects[id]?
  let owner := ownerOf o.state
  let whose := if owner.isEmpty then s!"{id}'s law" else s!"{shownName w owner}'s law on {id}"
  let kind := (text? (fieldsOf o.state) "kind").getD ""
  let over := if kind.isEmpty then (if id.startsWith "kind/" then id else "record") else kind
  let yours := if kind.isEmpty then "" else s!"delvetalk {kind} make (a {kind.drop 5} of your own, under the same law), or "
  return s!"It is {whose}. To have it your way: {yours}delvetalk kinds make / name: <yours> / of: {over} / law: <your law>; its law read whole: delvetalk library laws / card: {id}"

/-- Where a resident's words stand while hob reads them (playtest 5: a ghost's words sat suspended at entry 809, unsaid):
    for a suspended entry still waiting on an interpretation, the line that says hob is reading, by when it answers
    (the suspension's deadline: past it the turn resumes `timedOut`, never hangs), and how many readings wait before
    it in the town and on the card. Said in the reply and the receipt, never journaled. -/
def waitingLine (w : World) (entry : Json) : Option String := do
  guard (tagOf entry == "suspended")
  let hash ← (entry.getObjValAs? String "hash").toOption
  let outcome ← (entry.getObjVal? "outcome").toOption
  let slot ← (outcome.getObjVal? "slot").toOption
  guard ((slot.getObjValAs? String "principal").toOption == some interpretationPrincipal)
  guard (w.suspended.any fun s => (s.getObjValAs? String "hash").toOption == some hash)
  let deadline := (outcome.getObjValAs? Nat "deadline").toOption.getD w.clock
  let height := (entry.getObjValAs? Nat "height").toOption.getD 0
  let objectOf := fun (s : Json) => (((s.getObjVal? "outcome").toOption.bind (·.getObjVal? "activity" |>.toOption)).bind
    (·.getObjValAs? String "object" |>.toOption)).getD ""
  let reading := w.suspended.toList.filter fun s => ((s.getObjVal? "outcome").toOption.bind (·.getObjVal? "slot" |>.toOption)).bind
    (·.getObjValAs? String "principal" |>.toOption) == some interpretationPrincipal
  let ahead := (reading.filter fun s => (s.getObjValAs? Nat "height").toOption.getD 0 < height).length
  let object := objectOf entry
  let here := (reading.filter fun s => objectOf s == object).length
  return s!"hob is reading these words for {object}: it answers by clock {deadline}, within {deadline - w.clock} minutes, " ++
    s!"else the turn ends timed out; {ahead} reading{if ahead == 1 then "" else "s"} wait before it in the town, " ++
    s!"{here} on {object} with it. Its receipt says how it ended."

/-- A rule an admitted entry placed that holds as a level over what grows (`Clause.levelHint`): the one line that says
    so and what to write instead, for each rule the entry placed on a thing (`placed`) or wrote into a text (an amendment:
    `for: things`, `adopt`), the first. Said in the reply, never journaled. -/
def ruleTeaching (w : World) (entry : Json) : Option String := do
  guard (tagOf entry == "admitted")
  let outcome ← (entry.getObjVal? "outcome").toOption
  let height := (entry.getObjValAs? Nat "height").toOption.getD 0
  let rows := fun (k : String) => (((outcome.getObjVal? k).toOption.bind (·.getArr?.toOption)).getD #[]).toList
  let placed := (rows "placed").filterMap (·.getObjValAs? String "object" |>.toOption) |>.flatMap fun id =>
    (((w.objects[id]?).map (·.rules)).getD []).filter (·.since == height) |>.map (·.clause)
  let written := (rows "amendments").flatMap fun a =>
    let text := fun (k : String) => (a.getObjValAs? String k).toOption.getD ""
    let before := ((parseClauses (text "old")).toOption.getD []).map (·.render)
    ((parseClauses (text "new")).toOption.getD []).filter (!before.contains ·.render)
  (placed ++ written).findSome? (·.levelHint)

/-- Lift `result`, `ticksUsed` and, for a suspension, `slot` and `deadline` to the reply, and the
    offers the entry retains for the turn's own principal (others are read with `world-offers`), and an
    admitted entry's three lines (`revealed`) and whether they may be posted (`inPublic`). -/
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
      (if mine.isEmpty then [] else [("offers", Json.arr mine)]) ++ revealedField w entry ++ inPublic w entry ++
      -- A plan's acts as they ran, and the one its refusal names.
      ((entry.getObjVal? "plan").toOption.map fun p => [("plan", match planRefusedAct entry with
        | some (n, _) => p.setObjVal! "refused" (toJson n)
        | none => p)]).getD [] ++
      -- What a refusal may say in public, for transport to draft from; a law's, on a roomy world, how to have it otherwise.
      (if tagOf entry == "refused" then [("public", publicRefusal entry)] else []) ++
      (((teaching w entry).orElse fun _ => ruleTeaching w entry).map fun t => [("hint", toJson t)]).getD [] ++
      ((waitingLine w entry).map fun t => [("waiting", toJson t)]).getD [])

/-- `world-receipt {principal, identity, of?}`: the receipt of identity (`of`, default the
    reader, `identity`), projected under the reader's authority; a refusal with its `public` projection.
    The identity's own principal is told what the entry revealed, as the admitted reply told it. -/
def receipt (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let owner := (← optText j "of").getD reader
  match boundEntry w owner intent with
  | none => return Json.mkObj [("status", toJson "unknown")]
  | some entry =>
    let shown := projectEntry w reader entry
    if owner != reader && tagOf entry == "refused" then return publicRefusal entry
    -- A refusal's owner also gets what may be said of it in public, which a draft of it carries.
    return Json.mkObj ([("status", toJson "receipt"), ("receipt", shown)] ++ inPublic w entry ++
      (if owner == reader then ((waitingLine w entry).map fun t => [("waiting", toJson t)]).getD [] else []) ++
      (if tagOf entry == "refused" then [("public", publicRefusal entry)] else []) ++
      (if owner == reader && !reader.isEmpty then revealedField w entry else []))

/-- Retry rule for turns: the identity is bound to the whole turn request. -/
def retainedTurn (w : World) (r : TurnRequest) : Option Json :=
  match boundEntry w r.principal r.intent with
  | none => none
  | some entry =>
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
  /-- A turn root ran `as` its principal (docs/ROOT.md §1.1): `{by, reason}`, journaled beside it. -/
  root : Option Json := none
  /-- The reach a delivered `receive` carries from the turn that handed it on (`Send.reach`). -/
  reach : Option String := none

def ledgerJson (l : Ledger) : Json := l.json

/-- The sends of an admitted turn, each with the ledger it inherits: depth - 1,
    work - the ticks this turn used, storage - the bytes its writes added. -/
def sendsJson (w : World) (principal intent : String) (ledger : Ledger) (used : Nat)
    (sends : List Send) (updates : List (String × Object)) (writes : List (String × List Written)) : List (String × Json) :=
  if sends.isEmpty then [] else
  let child := childLedger w ledger used updates writes
  [("sends", Json.arr (sends.zipIdx.toArray.map fun (x, i) => Json.mkObj
    ([("id", toJson (deliveryId principal intent i)), ("to", toJson x.to), ("method", toJson x.method),
     ("argument", dataJson x.argument), ("sender", toJson x.sender), ("ledger", child.json)] ++
     (if x.via.isEmpty then [] else [("via", toJson x.via), ("principal", toJson x.grantor)]) ++
     ((x.reach.map fun r => [("reach", toJson r)]).getD []) ++
     (if x.world.isEmpty then [] else [("world", toJson x.world)]))))]

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
  /-- `{by, reason}` of a turn root ran `as` its principal. -/
  root : Option Json := none
  /-- A plan's acts (`runPlan`): `{acts, of}`, journaled on its entry. -/
  plan : Option Json := none
  /-- Offered cards at the action's starting state; behaviours remain the revisions the reading saw. -/
  readingRoots : List (String × Nat) := []
  behaviours : List (String × Nat) := []


def sendJson (s : Send) : Json :=
  Json.mkObj ([("to", toJson s.to), ("method", toJson s.method), ("argument", dataJson s.argument),
    ("sender", toJson s.sender)] ++
    (if s.via.isEmpty then [] else [("via", toJson s.via), ("grantor", toJson s.grantor)]) ++
    ((s.reach.map fun r => [("reach", toJson r)]).getD []) ++
    (if s.world.isEmpty then [] else [("world", toJson s.world)]))

def sendOfJson (j : Json) : Except String Send := do
  return { to := ← j.getObjValAs? String "to", method := ← j.getObjValAs? String "method",
           argument := ← decodeData Limits.dataDepth (← j.getObjVal? "argument"),
           sender := ← j.getObjValAs? String "sender",
           via := (j.getObjValAs? String "via").toOption.getD "",
           grantor := (j.getObjValAs? String "grantor").toOption.getD "",
           reach := (j.getObjValAs? String "reach").toOption,
           world := (j.getObjValAs? String "world").toOption.getD "" }

def entryBase (ctx : Ctx) (used : Nat) : List (String × Json) :=
  [("turnRequest", toJson ctx.digest), ("ticksUsed", toJson used), ("ledger", ctx.ledger.json)] ++
    (ctx.delivery.map fun (id, sender) => [("delivery", Json.mkObj ([("id", toJson id), ("from", sender)] ++
      (if ctx.via.isEmpty then [] else [("via", toJson ctx.via)])))]).getD [] ++
    (ctx.resumes.map fun h => [("resumes", toJson h)]).getD [] ++
    (if ctx.answers.isEmpty then [] else [("replyTo", toJson ctx.answers)]) ++
    (if ctx.rerun then [("rerun", toJson true)] else []) ++
    (ctx.root.map fun r => [("root", r)]).getD [] ++
    (ctx.plan.map fun j => [("plan", j)]).getD []

/-- End a segment of a turn: commit it, refuse it, or journal its suspension. -/
def finishTurn (w : World) (ctx : Ctx) (result : Except Abort Data) (st : TurnState) :
    Except String (World × Json) := do
  let w := w.withCachesOf st.world
  let used := ctx.usedBefore + (ctx.ticksStart - st.ticks)
  let proposal : Proposal :=
    { principal := ctx.principal
      intent := ctx.intent
      roots := st.roots
      behaviours := st.behaviours
      rebaseOwn := if ctx.resumes.isSome then some ctx.object else none
      writes := st.writes
      turn := w.height + 1
      programs := st.programs
      layered := st.layered
      madeFrom := st.madeFrom
      laws := st.laws
      absent := st.absent
      creates := st.creates
      grants := st.grants
      revokes := st.revokes
      spent := st.spent
      placements := st.placements
      cells := st.cells
      sender := st.sender }
  let proposal := proposal.previewReadings w
  let base := entryBase ctx used ++ (if st.cites.isEmpty then [] else [("cites", Json.arr st.cites)])
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
  | .error (.named refusal) =>
    let (w', r) := commit w { proposal with writes := [], creates := [] } base (some refusal) (onEnd := endedIfLate)
    return (w', turnReply w' r)
  | .error (.quota reason next) =>
    let (w', r) := commit w { proposal with writes := [], creates := [] } base
      (some { cls := "quota", reason := some reason, next := some next })
    return (w', turnReply w' r)
  | .error (.suspend sp si patience checkpoint interpretation crossing) =>
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
      ("ticks", toJson st.ticks), ("awaited", toJson st.awaited), ("awaits", toJson st.awaits), ("crossings", toJson st.crossings),
      ("offers", offersJson st.offers), ("publishes", Json.arr st.publishes.toArray), ("caller", toJson ctx.caller), ("checks", toJson st.checks),
      ("grants", Json.arr (st.grants.toArray.map Grant.json)), ("revokes", toJson st.revokes),
      ("placements", Json.arr (st.placements.toArray.map (·.json))),
      ("spent", spentJson st.spent)] ++
      (if st.post.isEmpty then [] else [("post", toJson st.post)]) ++
      (if st.origin == "request" then [] else [("origin", toJson st.origin), ("command", toJson st.command)]) ++
      (if st.reach.isEmpty then [] else [("reach", toJson st.reach)]) ++
      (if st.violation.isSome then [("violation", toJson st.violation), ("violator", toJson st.violator)] else [])).filter
        fun (k, v) => k == "ticks" || !(v == Json.arr #[] || v == toJson "" || v == toJson (0 : Nat)))
    let waitsOn := ("slot", Json.mkObj [("principal", toJson sp), ("intent", toJson si)])
    let outcome := Json.mkObj <| [("tag", toJson "suspended"), waitsOn,
      ("deadline", toJson (w.clock + patience)), ("activity", activity)] ++
      (interpretation.map fun i => [("interpretation", i)]).getD [] ++
      -- A call across carries the ledger a send would: one level less deep, the work this turn used spent.
      (crossing.map fun c => [("crossing", c.setObjVal! "ledger"
        (Ledger.json ⟨ctx.ledger.depth - 1, ctx.ledger.work - used, ctx.ledger.storage⟩))]).getD []
    let (w', entry) := push w (identityKey ctx.principal ctx.intent)
      ([("identity", identityJson ctx.principal ctx.intent), ("roots", rootsJson st.roots st.cells proposal.behaviours),
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
      let (w', r) := commit w { proposal with writes := [], creates := [], grants := [], revokes := [], spent := [] } base
        (some { cls := "lawRefused", clause := some "noGrant", object := some x.to, reading := some s!"the grant a send to {x.to} was made under no longer stands." }) (onEnd := endedIfLate)
      return (w', turnReply w' r)
    | none =>
    let offered := (if st.offers.isEmpty then [] else [("offers", offersJson st.offers)]) ++
      (if st.publishes.isEmpty then [] else [("publishes", Json.arr st.publishes.toArray)]) ++
      (if st.checks == 0 then [] else [("checks", toJson st.checks)])
    let (w', r) := commit w proposal (base ++ [("result", dataJson value)] ++ offered) none
      (fun updates => sendsJson w ctx.principal ctx.intent ctx.ledger used st.sends updates proposal.allWrites) endedIfLate
    return (w', turnReply w' r)

/-- `publishPage {page}` asked of a card whose package declares no `publishPage` (WORLD-REVIEW
    finding 16): the host publishes the card's default page as `Card.defaultPage` wrote it, the card as
    a stranger sees it and how to reply (the host's usage of the forms offered a stranger, and its lenses), under `page`, else
    the object's id. The result is the post id, as
    `Card.publishPage`'s. The page is public, so a card whose read policy names principals has none:
    refused `noMethod` (codex host 2). -/
def defaultPublishPage (id : String) (argument : Data) : M Data := do
  let s ← get
  let some o := s.world.objects[id]? | evaluation s!"unknown object {id}"
  unless o.read matches .exposed do
    throw (.refused "noMethod" s!"{id} is not public, so the host makes no page of it; only a card anyone may read has one.")
  recordRoot id o.version
  let given := match argument with
    | .record fs => ((fs.lookup "page").bind labelOf).getD ""
    | _ => ""
  let title := if given.isEmpty then id else given
  let card ← match ← renderCard id o "" "" s.intent with
    | .ok doc => liftEval (Delvetalk.Document.render doc)
    | .error clause => evaluation s!"publishPage: the card does not render ({clause})"
  let usage := spellUsage id (usageForms s.world id o "" (spellForms s.world id o)) (declaredLenses s.world o)
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
  -- The reply names the card the turn ran on (a spell's card as resolved), so a turn line names it.
  let named := fun (r : Json) => if (r.getObjVal? "receipt").isOk then r.setObjVal! "object" (toJson req.object) else r
  if let some r := retainedTurn w req then return (w, named r)
  let ledger := how.ledger.getD ((w.objects[req.object]?).map (·.chain) |>.getD Ledger.start)
  let ticks ← match Delvetalk.Turn.budgets req.limits with
    | .ok b => pure b.ticks
    | .error e => throw e
  let init : TurnState := { world := w, principal := req.principal, intent := req.intent, subject := req.principal,
                            direct := how.delivery.isNone, receiver := how.receiver, ticks, limits := req.limits, profiling := req.profile,
                            sender := if how.delivery.isSome then how.caller else "",
                            origin := req.origin, command := req.command,
                            post := if req.post.isEmpty then (heardPost req.method req.argument).getD "" else req.post,
                            reach := if how.delivery.isSome then how.reach.getD "delivery"
                              else if !req.reach.isEmpty then req.reach
                              else if req.method != "receive" then "direct" else "" }
  -- A reply to a post recorded for this very object answers it (reply-is-address).
  let post := if req.replyTo.isEmpty then none else w.posts[req.replyTo]?
  let answers := match post with
    | some p => if p.object == req.object then req.replyTo else ""
    | none => ""
  -- A card that declares no `publishPage` has the host's default page (`defaultPublishPage`).
  let byHost := req.method == "publishPage" && how.delivery.isNone &&
    ((w.objects[req.object]?).map (!hasMethod · "publishPage")).getD false
  let action := if byHost then defaultPublishPage req.object req.argument
    else do
      -- A send under a grant spent it when it was sent; a principal's own turn under one spends it here.
      let argument ← if how.delivery.isSome then pure req.argument else granted how.via req.object req.method req.argument
      runMethod 0 req.object req.method argument how.caller req.principal how.via
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
      rerun := how.rerun
      root := how.root }
  let (w', r) ← finishTurn w ctx result st
  let r := named r
  return (w', if req.profile then r.setObjVal! "profile" (profileJson st.profile) else r)

/-- Journal a `badSpell` refusal of the turn as asked (its identity binds, so a resend is a new
    turn). -/
def refuseSpell (w : World) (req : TurnRequest) (object clause reason hint : String) (how : TurnMeta := {}) :
    Except String (World × Json) := do
  let ctx : Ctx := { principal := req.principal, intent := req.intent, object := req.object, method := req.method,
                     argument := req.argument, digest := req.digest, ledger := how.ledger.getD Ledger.start,
                     delivery := how.delivery, via := how.via, ticksStart := 0 }
  let p : Proposal := { principal := req.principal, intent := req.intent, roots := [], writes := [], turn := w.height + 1 }
  let (w', r) := commit w p (entryBase ctx 0)
    (some { cls := "badSpell", clause := some clause, object := some object, reason := some reason, hint := some hint })
  return (w', turnReply w' r)

/-- hob's one tail line (docs/VOICE.md "hob") under `?` usage or a badSpell hint of a direct turn,
    when a `library` card the speaker may see exists: the page that says how a spell is read, in the
    speaker's stated tongue (`Tongue.say`). Never in a refusal's reason, never twice. -/
def hobTail (w : World) (principal text line : String) : String :=
  match w.objects["library"]? with
  | some lib => if lib.read.permits principal && !text.isEmpty then s!"{text.trimAsciiEnd}\n\n{Tongue.say (Tongue.choose w principal "") line}" else text
  | none => text

/-- The opener's powers (docs/ROOT.md §2.2), each a receipted turn under the opener's identity with a
    required reading: on `world`, `quiet`/`unquiet {who, hours}` (their turns refused `quiet` until
    the clock), `settings {postQuota, interpretQuota, modelQuota, turnQuota, objectQuota, paintQuota}`, `revoke {grant}`; on a card,
    `retire`/`unretire` (an amendment adding or removing the `retired` clause, which admits only the
    opener's amendments), `hide`/`show` (the read policy narrowed to its owner and the opener, and
    restored). Anyone else is refused `badSpell`, clause `opener`. -/
def moderate (w : World) (req : TurnRequest) (id action : String) (value : String → Option String) :
    Except String (World × Json) := do
  let template := s!"delvetalk {id} {action}\n" ++ (match action with
    | "quiet" => "who: <a handle>\nhours: <n>\n" | "unquiet" => "who: <a handle>\n"
    | "settings" => String.join (quotaKeys.map (s!"{·}: <n>\n"))
    | "revoke" => "grant: <a grant id>\n" | _ => "") ++ "reading: <why, for the receipt>\n"
  if !openerActs w req.principal then
    return ← refuseSpell w req id "opener" s!"only the hand that opened the world casts {action}, on the root socket." template
  let some reading := value "reading"
    | refuseSpell w req id "missingField" s!"{action} takes reading: why, for the receipt." template
  if reading.utf8ByteSize > Limits.maxReasonBytes || reading.any (fun c => c == '"' || c == '\\' || c == '\n') then
    return ← refuseSpell w req id "badValue" s!"a reading is one line of at most {Limits.maxReasonBytes} bytes, without quotes." template
  let ctx : Ctx := { principal := req.principal, intent := req.intent, object := id, method := action,
                     argument := req.argument, digest := req.digest, ledger := Ledger.start, delivery := none, ticksStart := 0 }
  let base := entryBase ctx 0
  let moderated := fun (fields : List (String × Json)) => do
    let outcome := Json.mkObj ([("tag", toJson "moderated"), ("power", toJson action)] ++ fields ++ [("reading", toJson reading)])
    let before ← rootBefore w outcome
    let outcome := outcome.setObjVal! "before" before
    let w1 ← applyRoot w outcome
    let touch := if worldPowers.contains action then [] else [id]
    let (w', entry) := push w1 (identityKey req.principal req.intent)
      ([("identity", identityJson req.principal req.intent), ("roots", rootsJson []), ("turn", toJson 0),
        ("request", toJson req.digest)] ++ base ++ [("outcome", outcome)]) touch
    pure (w', turnReply w' (reply entry))
  let amend := fun (o : Object) (text : String) =>
    let p : Proposal := { principal := req.principal, intent := req.intent, roots := [(id, o.version)],
                          writes := [], laws := [(id, text)], turn := w.height + 1 }
    let (w', r) := commit w p (base ++ [("reading", toJson reading)])
    (w', turnReply w' r)
  let card := fun (_ : Unit) => match w.objects[id]? with
    | some o => Except.ok o
    | none => .error s!"no card {id}"
  match action with
  | "quiet" | "unquiet" =>
    let some name := value "who" | refuseSpell w req id "missingField" s!"{action} takes who: a handle." template
    let who := if name == meCard then req.principal else
      (principalNamed w name).getD name
    if action == "unquiet" then
      unless (w.quiets[who]?).any (·.1 > w.clock) do
        return ← refuseSpell w req id "badValue" s!"{name} is not quieted." template
      return ← moderated [("principal", toJson who), ("after", Json.null)]
    let some hours := (value "hours").bind (·.toNat?)
      | refuseSpell w req id "missingField" "quiet takes hours: a number of hours on the clock." template
    moderated [("principal", toJson who),
      ("after", Json.mkObj [("until", toJson (w.clock + hours * 60)), ("reading", toJson reading)])]
  | "settings" =>
    let named := quotaKeys.filterMap fun k => (value k).map (k, ·)
    let some values := named.mapM (fun (k, v) => v.toNat?.map (k, ·))
      | refuseSpell w req id "badValue" "a quota is a number." template
    if values.isEmpty then return ← refuseSpell w req id "missingField" "settings names a quota." template
    let (w', r) ← settingsChange w req.principal req.intent req.digest values reading base
    return (w', turnReply w' r)
  | "revoke" =>
    let some g := value "grant" | refuseSpell w req id "missingField" "revoke takes grant: its id." template
    unless w.grants.contains g do return ← refuseSpell w req id "badValue" s!"no grant {g}." template
    let p : Proposal := { principal := req.principal, intent := req.intent, roots := [], writes := [], revokes := [g],
                          turn := w.height + 1 }
    let (w', r) := commit w p (base ++ [("reading", toJson reading)])
    return (w', turnReply w' r)
  | "hide" =>
    let o ← card ()
    if w.hidden.contains id then return ← refuseSpell w req id "badValue" s!"{id} is hidden already." template
    let owner := ownerOf o.state
    let readers := (if owner.isEmpty || owner == w.opener then [] else [owner]) ++ [w.opener]
    moderated [("object", toJson id), ("after", ReadPolicy.json (.principals readers))]
  | "show" =>
    let some prior := w.hidden[id]? | refuseSpell w req id "badValue" s!"{id} is not hidden." template
    moderated [("object", toJson id), ("after", prior)]
  | "retire" =>
    let o ← card ()
    let some after := retiredLaw o.lawText reading w.opener
      | return ← refuseSpell w req id "badValue" s!"{id} is retired already." template
    return amend o after
  | "unretire" =>
    let o ← card ()
    unless (textClauses o.lawText).any (·.2.1 == "retired") do
      return ← refuseSpell w req id "badValue" s!"{id} is not retired." template
    return amend o (unretiredLaw o.lawText)
  | _ => refuseSpell w req id "noAction" s!"no power {action}." template

/-- A host spell's field `n`, given and not empty. -/
def hostValue (fields : List Spell.Binding) (n : String) : Option String :=
  ((fields.find? (·.name == n)).map (·.value)).filter (!·.isEmpty)

/-- The spell a placing's field `key` holds: a spell's own fields follow it on the line (`then: delvetalk me note /
    text: …`), so the field that holds the spell takes every field after it back into the line. -/
def hostSpellFrom (fields : List Spell.Binding) (key : String) : Option String :=
  (fields.findIdx? (·.name == key)).map fun i =>
    " / ".intercalate (((fields.drop i).take 1).map (·.value) ++ (fields.drop (i + 1)).map fun b => s!"{b.name}: {b.value}")

/-- Fields before a placing's nested spell belong to the placing; later ones belong to that spell. -/
def hostPlacingValue (fields : List Spell.Binding) : String → Option String :=
  let stop := (fields.findIdx? fun b => ["then", "asks", "does"].contains b.name).getD fields.length
  fun name => hostValue (if name == "for" then fields.take stop else fields) name

/-- `become`, `adopt` and `lend` on card `id` (`o`) for `principal` (`hostSpell` says what each does), from the
    spell's fields (`value`); `ordinal` numbers the grant `lend` makes among the turn's. A misfit is `(clause, reason)`. -/
def hostChange (w : World) (principal intent : String) (o : Object) (id action : String) (value : String → Option String)
    (ordinal : Nat) : Except (String × String) HostChange := do
  match action with
  | "become" =>
    let some kindId := value "kind" | throw ("missingField", "become takes kind: the id of a kind.")
    kindChange w principal o id kindId
  | "adopt" =>
    let some given := value "law" | throw ("missingField", "adopt takes law: a law written inline, or the id of a kind or a page.")
    -- A law written inline is adopted as it stands; an id names the kind or page holding one, read as a root.
    let inline := ["law ", "rule ", "want "].any fun k => given.trimAscii.toString.startsWith k
    let (clauses, source) ← if inline then pure (given.trimAscii.toString, []) else
      let some src := (w.objects[given]?).filter (·.read.permits principal)
        | throw ("unknownLaw", s!"There is no kind or page {given}; or write the law: law <name> \"<reading>\": <expression>.")
      let some clauses := (textField src.state "law").filter (!·.isEmpty)
        | throw ("noLaw", s!"{given} names no law to adopt.")
      pure (clauses, [(given, src.version)])
    let text ← appendedLaw o id clauses
    return { world := w, roots := (id, o.version) :: source, laws := [(id, text)],
             refusal := match parseLawText text with
               | .error message => some { cls := "programRefused", clause := some "law syntax", object := some id, reason := some message }
               | .ok _ => none }
  | "lend" =>
    let some toName := value "to" | throw ("missingField", "lend takes to: a handle, or me.")
    let some m := value "method" | throw ("missingField", "lend takes method: one of the card's methods.")
    let some untilText := value "until" | throw ("missingField", "lend takes until: +<clock units>.")
    let some n := (if untilText.startsWith "+" then untilText.drop 1 else untilText).toNat?
      | throw ("badValue", "until takes +<clock units>, plain digits.")
    -- `me`, a handle the registry knows, or a principal as written.
    let to := if toName == meCard then principal else (principalNamed w toName).getD toName
    unless o.offers m do throw ("noAction", s!"{id} has no method {m} to lend.")
    unless methodAdmits w o principal m id == Json.bool true do
      throw ("notYours", s!"The law of {id} does not let you run {m}, so you cannot lend it.")
    let expires := w.clock + n
    let speaker := ((w.handles[principal]?).filter (!·.isEmpty)).getD principal
    return { world := w, roots := [(id, o.version)],
             grants := [{ id := grantId principal intent ordinal, grantor := principal, holder := id, to,
                          object := id, method := m, expires, reading := s!"lent by {speaker}: {m}, until clock {expires}" }] }
  | _ => throw ("noAction", s!"{id} has no spell {action}.")

/-- The host's spells on any card (docs/CATALOGUE.md §2), each a direct turn of the speaker judged by
    the card's own law, journaled under the turn's identity:

    - `become / kind: <id>` installs the kind's ancestor bodies and its own, bottom first, and cites
      its text in the same turn. `madeFrom` names the kind's pin and receipt and records each body's
      layer position; a repeated installation replaces changed bodies there and retains unchanged ones.
    - `adopt / law: <law text or id>` appends a clause set to the card's text: the text itself when it
      starts `law `, `rule ` or `want ` (`law NAME "reading": EXPR`, a block for several; a rule or a want
      adopted is the card's own, fired under its owner), else the text `law` of the kind
      or library page the id names (a root of the turn); an amendment by the speaker under the
      metarule, the clauses' readings with them; a clause name the card's law already has is refused
      `lawClash`.
    - `lend / to: <handle or me> / method: <m> / until: +<n>` grants `to` the running of `m` on the
      card as the speaker until clock now + n (a grant held by the card, with a reading); only a
      method the card offers and its law admits the speaker to run (else `notYours`). -/
def hostSpell (w : World) (req : TurnRequest) (id action : String) (fields : List Spell.Binding) (how : TurnMeta := {}) :
    Except String (World × Json) := do
  let refuseSpell := fun (w : World) (req : TurnRequest) (object clause reason hint : String) =>
    refuseSpell w req object clause reason hint how
  let value := hostValue fields
  if worldPowers.contains action || cardPowers.contains action then
    if how.delivery.isSome then return ← refuseSpell w req id "opener" s!"{action} is the hand's, cast directly on the root socket." ""
    return ← moderate w req id action value
  let some o := w.objects[id]? | refuseSpell w req id "otherCard" s!"There is no card {id}." ""
  let ctx : Ctx := { principal := req.principal, intent := req.intent, object := id, method := action,
                     argument := req.argument, digest := req.digest, ledger := how.ledger.getD Ledger.start,
                     delivery := how.delivery, via := how.via, ticksStart := 0 }
  let base := entryBase ctx 0
  let target := if (thingsText o).isSome then forThingsLine else ""
  let template := (s!"delvetalk {id} {action}\n" ++ match action with
    | "become" => "kind: <a kind's id>\n"
    | "adopt" => adoptLine ++ "\n"
    | "rule" => ruleLine target ++ "\n"
    | "want" => wantLine target ++ "\n"
    | "unrule" | "unwant" => "name: <the name it was placed under>\n" ++ target
    | "grow" => growLine ++ "\n"
    | "ungrow" => "name: <the verb's name>\n"
    | _ => "to: <a handle, or me>\nmethod: <one of its methods>\nuntil: +<clock units>\n")
  let change := if placingSpells.contains action then
      placingChange w o id action (hostPlacingValue fields) (hostSpellFrom fields)
    else hostChange w req.principal req.intent o id action value 0
  match change with
  | .error (clause, reason) => refuseSpell w req id clause reason template
  | .ok c =>
    let p : Proposal := { principal := req.principal, intent := req.intent, roots := c.roots, writes := c.writes,
                          placements := c.placements,
                          programs := c.programs, layered := c.layered, madeFrom := c.madeFrom, laws := c.laws,
                          grants := c.grants, turn := w.height + 1 }
    let (w', r) := commit c.world p base c.refusal
    return (w', turnReply w' r)

/-- A grant lent to `principal` for `method` of `object` that stands now (`lend`): the borrower's direct
    turn runs under it, judged with the grantor as subject. "" for none. -/
def lentVia (w : World) (principal object method : String) : String :=
  (w.grants.fold (fun acc gid g => if acc.isNone && g.to == principal && g.holder == object &&
      (grantStands w gid object method).isSome then some gid else acc) none).getD ""

/-- One field value as a spell line writes it: text (a block when it has a line break), a number, a
    case with no payload as its word; none for anything else. -/
def spellValue (name : String) : Data → Option String
  | .label t =>
    if t.any (· == '\n') then
      let delimiter := (List.range 8).map (fun i => if i == 0 then "END" else s!"END{i}") |>.find? fun d =>
        !(t.splitOn "\n").any (· == d)
      delimiter.map fun d => s!"{name}: <<{d}\n{t}\n{d}"
    else some s!"{name}: {t}"
  | .natural n => some s!"{name}: {n}"
  | .variant c (.record []) => some s!"{name}: {c}"
  | _ => none

/-- The spell a proposal stands for, `delvetalk <card> <method>` and a line per field of its argument:
    what a card that asks first prints back for a yes. "" when a field has no spell form (a nested
    record, a list). -/
def proposalSpell (card method : String) (argument : Data) : String :=
  let head := s!"delvetalk {card} {method}"
  match argument with
  | .record fs => match fs.mapM fun (n, v) => spellValue n v with
    | some lines => "\n".intercalate (head :: lines)
    | none => ""
  | _ => ""

/-- A proposal as the Plan hears it (`World.Interpreted.proposal`): the object, method, argument and the
    spell it stands for. -/
def proposalData (target method : String) (argument : Data) (spell : String) : Data :=
  .record [("object", Data.label target), ("method", .label method), ("argument", argument), ("spell", .label spell)]

/-- A form offered to the interpreter: its spell form and its `source` fields (`Form.Kind.source`),
    which a spell's ```obend block fills (`withFence`). -/
structure OfferedForm where
  form : Spell.Form
  sources : List String

def OfferedForm.ofData : Data → Option OfferedForm
  | .record f =>
    let fields := ((f.lookup "fields").bind listOf).getD []
    let isSource := fun (d : Data) => match d with
      | .record g => match g.lookup "kind" with | some (.variant "source" _) => true | _ => false
      | _ => false
    let sources := fields.filter isSource |>.filterMap fun
      | .record g => (g.lookup "name").bind labelOf
      | _ => none
    let rest := Data.record (f.map fun (k, v) => if k == "fields" then (k, listData (fields.filter (!isSource ·))) else (k, v))
    (Spell.Form.ofData rest).map ({ form := ·, sources })
  | _ => none

/-- What a model's text says to a suspended activity of the message dialect, fitted against the
    offered forms as a reply's spell is (WHOLENESS §2, "Interpretation"): a spell naming an offered
    form that fits is that form's proposal; one that misfits, or misses fields, is `unclear` naming
    why or what it needs; a spell naming no offered form is `unclear`. A text with no spell line whose
    first field line names an offered action or field is that form's spell (`Card.withBare`). `none`
    when the text is no spell: the object hears it as `replied`. -/
def spellVerdict (offered : List OfferedForm) (text : String) : Option (Except (List String) (String × String × Data)) :=
  -- A reply's ```obend block is the value of the form's first `source` field the spell lacks, as
  -- `withFence` binds it for a typed spell: a block and a fenced reply are one value.
  let fence := firstFence text
  let fitted := fun (offer : OfferedForm) (fields : List Spell.Binding) =>
    let form := offer.form
    match offer.sources.find? (fun n => !fields.any (·.name == n)), fence with
    | some name, none => Except.error [name]
    | source, code =>
    match Spell.fit (.spell form.card form.action fields) form with
    | .proposal _ action entries =>
      let bound := match source, code with
        | some name, some c => [(name, Data.label c)]
        | _, _ => []
      Except.ok (form.card, action, match spellArgument entries with
        | .record fs => .record (fs ++ bound)
        | other => other)
    | .unclear needs => .error needs
    | .refused _ reason => .error [reason]
  match Spell.parse text with
  | .spell card action fields =>
    match offered.find? fun f => Spell.fold f.form.card == Spell.fold card && f.form.action == action with
    | some form => some (fitted form fields)
    | none => some (.error [s!"{card} {action} is not one of the offered actions"])
  | .quotation reason => some (.error [reason])
  | .notASpell _ fielded =>
    if fielded then do
      let first ← (Spell.bare text).head?
      let offer ← offered.find? fun f => f.form.action == first.name || f.form.fields.any (·.name == first.name)
      some (fitted offer ((Spell.bare text).filter fun b => b.name == offer.form.action || offer.form.fields.any (·.name == b.name)))
    -- A reply that is one ```obend block and no spell settles the one offered form that takes source
    -- (the workshop's drafting: the model answers with the Bend, playtest 2's D3).
    else do
      let _ ← fence
      match offered.filter (!·.sources.isEmpty) with
      | [offer] => some (fitted offer [])
      | _ => none

/-! ## Words a card heard (docs/OVERHAUL.md §2.7; docs/FOUNDATION.md §10): hob reads them for that card

Words that reach a card (`reachOf`: a reply, a door's word, field lines, a summons, a turn asked on the
card) and name none of its spells are read by the host for that card. The card's `receive` hears them
first and answers what it reads as its own (an avatar's words to it, a room's spween block, a door's word
at the commonplace); what it leaves `silent` the host gives hob with the card's table, its doors' tables,
its wants and the library's pages, and hob's answer runs as the speaker's turn on that card
(`resumeHeard`). A card opts out of hob for words only by answering them. -/

/-- The world's one interpretation policy (genesis's `policy`): the model hob reads with, its examples
    and the actions that ask the speaker first (`confirmFor`). -/
def policyId : String := "policy"

/-- A card's doors (its `cites`), each `(label, card it opens)`; a link door opens no card and is left out. -/
def doorsOf (o : Object) : List (String × String) :=
  match o.state with
  | .record fs => ((fs.lookup "cites").bind listOf |>.getD []).filterMap fun d => do
      let .record r := d | none
      let to ← (r.lookup "to").bind referenceId
      guard (!to.isEmpty)
      pure (← (r.lookup "label").bind labelOf, to)
  | _ => []

/-- The host's placing spells hob may answer with on a card (`placingChange`; `grow` is its own answer,
    `growVerdict`), each a form whose fields are the usage's (`ruleLine`, `wantLine`: the spell last), for a
    speaker the thing's law admits placing it (kind 4), or the kind's owner amending its text (kind 2). -/
def placingForms (w : World) (id principal : String) (o : Object) : List Data :=
  let text := fun (name : String) (max : Nat) => Data.record [("name", .label name),
    ("kind", .variant "text" (.record [("min", .natural 1), ("max", .natural max)]))]
  let named := text "name" Limits.maxMethodBytes
  let target := if (thingsText o).isSome && principal == ownerOf o.state && kindAdmits w o principal 2 id then
    [Data.record [("name", .label "for"), ("kind", .variant "text" (.record [("min", .natural 0), ("max", .natural 6)]))]] else []
  let fields := fun (action : String) => match action with
    | "rule" => [named] ++ target ++ [text "when" Limits.maxLawBytes, text "then" Limits.maxLawBytes]
    | "want" => [named] ++ target ++ [text "when" Limits.maxLawBytes, text "asks" Limits.maxLawBytes]
    | _ => [named] ++ target
  (["rule", "want", "unrule", "unwant"].filter fun a =>
      !o.offers a && (kindAdmits w o principal 4 (verb := if a.startsWith "un" then (a.drop 2).toString else a) || !target.isEmpty)).map fun a =>
    .record [("card", .label id), ("action", .label a), ("fields", listData (fields a))]

/-- What hob is offered for words that reached `id`, read for `principal`: the card's table (its declared
    forms and grown verbs that it offers the speaker, `offeredTo`, and the host's placing spells its law
    admits, `placingForms`), then each door's card (`doorsOf`) and the first three cards under it (a
    garden's bells), each form under its own card. A door's cards are how words at the commonplace reach
    the town. A card that would pass `maxOffersBytes` is left out. -/
def heardOffers (w : World) (id principal : String) : List Data := Id.run do
  let some o := w.objects[id]? | return []
  let table := fun (c : String) (x : Object) =>
    (spellFormsData w c x).filter fun f => formAction f != "receive" && offeredTo w c x principal (formAction f)
  let mut forms := table id o ++ placingForms w id principal o
  let mut seen : List String := [id]
  for (_, door) in doorsOf o do
    for c in door :: ((listIds w principal (door ++ "/") "").1.take 3) do
      if seen.contains c then continue
      seen := c :: seen
      let some x := w.objects[c]? | continue
      unless x.read.permits principal do continue
      let more := forms ++ table c x
      if (dataJson (listData more)).compress.utf8ByteSize > Limits.maxOffersBytes then return forms
      forms := more
  return forms

/-- Did a card's `receive` take nothing of the words: admitted, its result `silent` (`Card.Replied`),
    nothing written, made, placed, sent, offered or published. -/
def heardSilent (r : Json) : Bool := Id.run do
  let some e := (r.getObjVal? "receipt").toOption | return false
  let outcome := (e.getObjVal? "outcome").toOption.getD Json.null
  let quiet := ((outcome.getObj?.toOption.map (·.toList)).getD []).all fun (k, v) =>
    k == "tag" || (k == "writes" && v == Json.arr #[])
  let silent := match (e.getObjVal? "result").toOption.map (decodeData Limits.dataDepth) with
    | some (.ok (.variant "silent" _)) => true
    | _ => false
  return tagOf e == "admitted" && quiet && silent && ["offers", "sends", "publishes"].all fun k => (e.getObjVal? k).toOption.isNone

/-- The card words reached, as the root of a turn that reads them (what its `replyTo` answers is a post of it). -/
def cardRoot (w : World) (id : String) : List (String × Nat) :=
  ((w.objects[id]?).map fun o => [(id, o.version)]).getD []

/-- A misfit spell hob reads past (`misfitClauses`), and the host's own refusal of it, which stands
    when hob reads nothing better. -/
structure Misfit where
  clause : String
  reason : String
  hint : String

/-- One act of a settled reading: a card's method with its argument (a grown verb as written, run as its
    card's `act`), or a placing spell (`grow`) staged as the spell stages it; `spell` is how it is cast. -/
structure HeardStep where
  object : String
  method : String
  argument : Data
  spell : String

/-- The action a policy's `confirmFor` names a step by: a grown verb's name, else its method. -/
def HeardStep.action (s : HeardStep) : String :=
  if s.method == actMethod then ((labelsOf s.argument) "verb").getD s.method else s.method

/-- One act of a plan (docs/HOST-HANDOFF.md 5.203): a spell read in the turn after the acts before it (`spell`, its
    holes `{made N}` filled from what act N made, `fillHoles`), or a step hob read already (`step`). -/
inductive Act where
  | spell (text : String)
  | step (s : HeardStep)

def Act.text : Act → String
  | .spell t => t
  | .step s => s.spell

/-- An act's spell line, as a reply names the act: its first line, trimmed. -/
def actLine (text : String) : String := ((text.trimAscii.toString.splitOn "\n").headD "").trimAscii.toString

/-- `text` with each hole `{made N}` the first object act `N` made (`made`, what each act before act `n` made, in
    order), or why one names nothing: no number, an act not before `n`, or an act that made nothing. -/
def fillHoles (text : String) (made : Array (List String)) (n : Nat) : Except String String := do
  let parts := text.splitOn "{made "
  let mut out := parts.headD ""
  for part in parts.drop 1 do
    match part.splitOn "}" with
    | k :: rest@(_ :: _) =>
      let shown := "{made " ++ k ++ "}"
      let some i := k.trimAscii.toString.toNat? | throw s!"{shown} names no act; a hole is \{made N}, N an earlier act's number."
      unless 0 < i && i < n do throw s!"{shown} names no act before act {n}; a hole names what an earlier act made."
      let some id := (made[i - 1]?).bind (·.head?) | throw s!"{shown}: act {i} made nothing."
      out := out ++ id ++ "}".intercalate rest
    | _ => out := out ++ "{made " ++ part
  return out

/-- A refusal of a plan's act `n` (`line`), whole: its clause, the act named in its reason. -/
def actRefusal (_n : Nat) (_line object clause reason : String) (hint : String := "") : Abort :=
  .named { cls := "badSpell", clause := some clause, object := some object,
           reason := some reason, hint := if hint.isEmpty then none else some hint }

/-- An abort inside act `n`, named by it: whatever refuses an act refuses the plan. An act that would wait (an await,
    hob's reading) is refused `planWaits`: a plan's acts run inside its one turn. -/
def inAct (n : Nat) (line object : String) : Abort → Abort
  | .evaluation r => .evaluation s!"act {n} ({line}): {r}"
  | .refused cls r e => .refused cls s!"act {n} ({line}): {r}" e
  | .named r => .named { r with reason := some s!"act {n} ({line}): {(r.reason <|> r.reading).getD r.cls}" }
  | .suspend .. => actRefusal n line object "planWaits" "it waits on another turn, and a plan's acts run inside its one turn; send it alone."
  | other => other

/-- Stage a host spell's change into the turn (`hostChange`; a placing as `stagePlacements` stages it): a plan's act,
    judged with the plan at its commit. An opener's power is an entry of its own, never an act. -/
def stageHost (n : Nat) (line id action : String) (fields : List Spell.Binding) : M Unit := do
  let s ← get
  let world ← currentWorld
  if worldPowers.contains action || cardPowers.contains action then
    throw (actRefusal n line id "notInPlan" s!"{action} is the hand's power, an entry of its own; cast it alone.")
  let some o := world.objects[id]? | throw (actRefusal n line id "otherCard" s!"There is no card {id}.")
  if placingSpells.contains action then
    if let some (clause, reading) ← stagePlacements id action (hostPlacingValue fields) (hostSpellFrom fields) (admit := false) then
      throw (actRefusal n line id clause reading)
    return
  if s.creates.any (·.1 == id) then
    throw (actRefusal n line id "notMade" s!"{id} is made by this plan; it takes its law and body as its kind makes it.")
  match hostChange world s.principal s.intent o id action (hostValue fields) s.grants.length with
  | .error (clause, reason) => throw (actRefusal n line id clause reason)
  | .ok c =>
    if let some r := c.refusal then throw (.named r)
    if !c.programs.isEmpty && s.programs.any (·.1 == id) then
      throw (actRefusal n line id "codeTwice" s!"{id} is given code by an earlier act of this plan.")
    for (x, v) in c.roots do recordRoot x v
    modify fun s => { s with world := s.world.withCachesOf c.world, programs := s.programs ++ c.programs, layered := s.layered ++ c.layered,
                             madeFrom := s.madeFrom ++ c.madeFrom, grants := s.grants ++ c.grants,
                             laws := (s.laws.filter fun old => !c.laws.any (·.1 == old.1)) ++ c.laws }

/-- Run a plan as one turn of the speaker (`ctx`, its identity and what it resumes; docs/HOST-HANDOFF.md 5.203): each
    act in order at the top of the turn, as a spell posted alone runs, reading the cards as the acts before it left
    them (`turnWorld`; what they made is an object of the turn, `madeIn`); a spell is read when its act comes, against
    `receiver` with the post's argument (`argOf`), so a later act names what an earlier made (`{made N}`). Nothing is
    judged until the one commit (`finishTurn`), which judges every law against the world the acts leave, fires rules
    once and writes one receipt; any refusal refuses the whole plan, naming the act (`inAct`, `planRefusedAct`).
    hob's settled steps run the same way (`runHeard`). -/
def runPlan (w : World) (ctx : Ctx) (post reach origin receiver : String) (acts : List Act) (argOf : String → Data) :
    Except String (World × Json) := do
  let init : TurnState := { world := w, principal := ctx.principal, intent := ctx.intent, subject := ctx.principal,
                            roots := ctx.readingRoots, behaviours := ctx.behaviours, direct := true, ticks := Limits.maxTurnTicks,
                            limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))],
                            origin, command := ((acts.head?.map Act.text).getD ""), post, reach }
  let action : M Data := do
    let mut result := emptyRecord
    let mut made : Array (List String) := #[]
    for (act, i) in acts.zipIdx do
      let n := i + 1
      let line := actLine act.text
      let before ← get
      let (object, done, r) ← tryCatch (runAct n line act made) fun e => do
        modify fun s => { s with acts := s.acts.push (Json.mkObj [("act", toJson n), ("spell", toJson line), ("refused", toJson true)]) }
        throw (inAct n line receiver e)
      result := r
      let after ← get
      let madeNow := (after.creates.drop before.creates.length).map (·.1)
      made := made.push madeNow
      -- What the act touched, so a refusal at the commit names the act that staged it (`planRefusedAct`).
      let staged := fun (t : TurnState) => (t.writes.map (·.1)) ++ (t.placements.map (·.object)) ++ (t.laws.map (·.1)) ++
        (t.programs.map (·.1)) ++ (t.grants.map (·.holder)) ++ (t.creates.map (·.1))
      let touched := ((staged after).filter fun x => !(staged before).contains x ||
        (after.writes.lookup x).map (·.length) != (before.writes.lookup x).map (·.length) ||
        after.placements.filter (·.object == x) != before.placements.filter (·.object == x) ||
        after.laws.lookup x != before.laws.lookup x || after.programs.lookup x != before.programs.lookup x).eraseDups
      modify fun s => { s with acts := s.acts.push (Json.mkObj ([("act", toJson n), ("spell", toJson line), ("object", toJson object),
        ("done", toJson done)] ++ (match done, r with | "read", .label t => [("text", toJson t)] | _, _ => []) ++
        (if madeNow.isEmpty then [] else [("made", toJson madeNow)]) ++
        (if touched.isEmpty then [] else [("touched", toJson touched)]))) }
    return result
  let (result, st) := (action.run).run init
  let plan := Json.mkObj [("acts", Json.arr st.acts), ("of", toJson acts.length)]
  let (w', r) ← finishTurn w { ctx with ticksStart := Limits.maxTurnTicks, plan := if acts.all (· matches .step _) then none else some plan } result st
  return (w', if (r.getObjVal? "receipt").isOk then r.setObjVal! "object" (toJson ctx.object) else r)
where
  /-- One act: the card it ran on, what it did (`ran`, `staged`, `read`: a `?` read on the cards as they stand in the
      turn, its text the act's answer) and the frame's result. -/
  runAct (n : Nat) (line : String) (act : Act) (made : Array (List String)) : M (String × String × Data) := do
    match act with
    | .step step =>
      let world ← currentWorld
      let some obj := world.objects[step.object]? | throw (.refused "unknownObject" s!"There is no card {step.object}.")
      if placingSpells.contains step.method && !obj.offers step.method then
        if let some (clause, reading) ← stagePlacements step.object step.method (labelsOf step.argument) (labelsOf step.argument) (admit := false) then
          throw (.refused clause reading)
        return (step.object, "staged", emptyRecord)
      let (method, argument) := match grownAct obj step.method step.argument with
        | some a => (actMethod, a)
        | none => (step.method, step.argument)
      let via := lentVia world ctx.principal step.object method
      let r ← runMethod 0 step.object method (← granted via step.object method argument) "" ctx.principal via
      return (step.object, "ran", r)
    | .spell text =>
      let filled ← match fillHoles text made n with
        | .ok t => pure t
        | .error why => throw (actRefusal n line receiver "hole" why)
      let world ← currentWorld
      match routeSpell world ctx.principal receiver "receive" (argOf filled) true with
      | .run object method argument command =>
        modify fun s => { s with command }
        let via := lentVia world ctx.principal object method
        let r ← runMethod 0 object method (← granted via object method argument) "" ctx.principal via
        return (object, "ran", r)
      | .host object action fields => stageHost n line object action fields; return (object, "staged", emptyRecord)
      | .usage object usage => return (object, "read", .label usage)
      | .read object text _ => return (object, "read", .label text)
      | .refuse object clause reason hint => throw (actRefusal n line object clause reason hint)
      | .asIs => throw (actRefusal n line receiver "noAction" "this act is no spell.")

/-- Run hob's settled steps as the speaker's turn (`runPlan`): it answers the post its words replied to only when it
    ran first on that post's card. -/
def runHeard (w : World) (ctx : Ctx) (post reach : String) (steps : List HeardStep) : Except String (World × Json) :=
  let answers := if (w.posts[ctx.answers]?).map (·.object) == steps.head?.map (·.object) then ctx.answers else ""
  runPlan w { ctx with answers } post reach "interpreted" ctx.object (steps.map .step) fun _ => ctx.argument

/-- hob's reading of `text`, words that reached the cards `ids` (one, or each misfit spell's of a post, `runSpells`),
    as the speaker's turn (`req`'s identity), rooted on the first that exists. Field lines that fit a form offered
    (`heardOffers` of each card: its own, its doors') are that form's spell, run at once with no model. Else the turn waits on hob: a suspension the host resumes itself (`hostResumed`,
    `resumeHeard`), counted by the interpretation quotas and slots as any reading. None when hob cannot
    read for the speaker (no policy they may read, words or offers past their bounds) or, for a misfit, its
    readings are spent or the card's reading slots full: the caller answers as it would without hob. Prose
    past those is refused transiently, `quota` saying when to try again or `capacity` naming the limit. -/
def heardTurn (w : World) (req : TurnRequest) (ids : List String) (text : String) (misfit : Option Misfit) :
    Option (Except String (World × Json)) := do
  let policy ← w.objects[policyId]?
  guard (policy.read.permits req.principal && text.utf8ByteSize ≤ Limits.maxUtteranceBytes)
  let id := ((ids.find? w.objects.contains).orElse fun _ => ids.head?).getD req.object
  let offers := listData ((ids.eraseDups.flatMap (heardOffers w · req.principal)).foldl
    (fun acc f => if acc.any (fun g => (dataJson g).compress == (dataJson f).compress) then acc else acc ++ [f]) [])
  guard ((dataJson offers).compress.utf8ByteSize ≤ Limits.maxOffersBytes)
  let (roots, behaviours) := offeredRoots w id offers
  guard (roots.length ≤ Limits.maxRoots)
  let answers := match w.posts[req.replyTo]? with
    | some p => if p.object == id then req.replyTo else ""
    | none => ""
  let ctx : Ctx := { principal := req.principal, intent := req.intent, object := id, method := req.method,
                     argument := req.argument, digest := req.digest, delivery := none, ticksStart := 0, answers,
                     ledger := ((w.objects[id]?).map (·.chain)).getD Ledger.start }
  let post := (heardPost req.method req.argument).getD req.post
  if misfit.isNone then
    if let .notASpell _ true := Spell.parse text then
      if let some (.ok (card, action, argument)) := spellVerdict (((listOf offers).getD []).filterMap OfferedForm.ofData) text then
        return runHeard w ctx post req.reach [{ object := card, method := action, argument, spell := proposalSpell card action argument }]
  -- Past the quotas or the reading slots, prose is refused transiently, saying why; a misfit keeps its refusal.
  let refused := fun (r : Refusal) =>
    let p : Proposal := { principal := req.principal, intent := req.intent, roots := cardRoot w id, writes := [], turn := w.height + 1 }
    let (w', e) := commit w p (entryBase ctx 0) (some r)
    Except.ok (w', turnReply w' e)
  -- Readings spent (the hand's for the hour, the world's for the day): the words wait, and the card's own spells, which
  -- need no reading, are the refusal's hint (docs/DEPLOY.md "A second instance": hob answers with the card's spells).
  if let some (reading, next) := interpretGate w req.principal then
    guard misfit.isNone
    let spells := ((w.objects[id]?).map fun o => spellUsage id (spellForms w id o)).getD ""
    return refused { cls := "quota", reason := some reading, next := some next, hint := if spells.isEmpty then none else some spells }
  if let some limit := waitFull w id true then
    guard misfit.isNone
    return refused { cls := "capacity", reason := some limit, object := some id }
  let hid := interpretationSlot #[toJson req.principal, toJson req.intent, toJson "heard"] behaviours
  let interpretation := Json.mkObj ([("id", toJson hid), ("object", toJson id), ("policy", toJson policyId),
      ("utterance", toJson text), ("offers", dataJson offers)] ++
    ((misfit.map fun m => [("misfit", toJson s!"{m.clause}, {m.reason}"), ("refusal", Json.mkObj
      [("clause", toJson m.clause), ("reason", toJson m.reason), ("hint", toJson m.hint)])]).getD []))
  let (interpretation, interpretationBlocks) := compactInterpretation interpretation req.argument
  let (argument, argumentBlocks) := hoistLabels (dataJson req.argument)
  let activity := Json.mkObj ([("object", toJson id), ("method", toJson "receive"), ("argument", argument)] ++
    (if post.isEmpty then [] else [("post", toJson post)]) ++ (if req.reach.isEmpty then [] else [("reach", toJson req.reach)]))
  let outcome := Json.mkObj [("tag", toJson "suspended"),
    ("slot", Json.mkObj [("principal", toJson interpretationPrincipal), ("intent", toJson hid)]),
    ("deadline", toJson (w.clock + Limits.interpretationPatience)), ("activity", activity), ("interpretation", interpretation)]
  let blocks := (interpretationBlocks ++ argumentBlocks).map fun b => (Journal.bodyHash (Json.arr b), b)
  let (w', entry) := push w (identityKey req.principal req.intent)
    ([("identity", identityJson req.principal req.intent), ("roots", rootsJson roots [] behaviours), ("turn", toJson (w.height + 1)),
      ("request", toJson req.digest)] ++ entryBase ctx 0 ++ [("outcome", outcome)] ++ blocksField w blocks) []
  return .ok (w', turnReply w' (reply entry))

/-- How a direct turn's words reached the card (docs/FLEX.md §2): a reply to a post the world recorded,
    a spell line in the text, else what the transport stated (`statedReaches`), else nothing. -/
def reachOf (w : World) (req : TurnRequest) : String :=
  if req.reach == "mentioned" then req.reach
  else if !req.replyTo.isEmpty && w.posts.contains req.replyTo then "reply"
  else match Spell.parse (heardText req.method req.argument) with
    | .spell .. => "spell"
    | _ => req.reach

/-! ## Reach (docs/FLEX.md §2; OVERHAUL §2.7): where an observed post's words go -/

/-- An ancestor the transport observed above a post: its uri, its author, the post it answers. -/
structure Seen where
  uri : String
  author : String
  replyTo : String

/-- The world's square (genesis's commonplace): where a summons lands, and whose doors prose may name. -/
def commonplaceId : String := Spell.townCard

/-- The longest walk up a thread (Zulip's topic, the doors' threads on Delve). -/
def reachHops : Nat := 32

/-- The nearest post the world recorded among `hops` ancestors from `uri`, walking `replyTo` through what was
    observed (`seen`), each asked once (`asked`: a cycle or a second walk asks nothing twice); with `author`
    (a Zulip topic) the walk passes only that author's own messages: another resident's message above is
    whom the words answer. -/
def walkTo (w : World) (seen : List Seen) (author : Option String) :
    Nat → String → List String → Option (String × Post) × List String
  | 0, _, asked => (none, asked)
  | n + 1, uri, asked =>
    if uri.isEmpty || asked.contains uri then (none, asked) else
    let asked := uri :: asked
    match w.posts[uri]? with
    | some p => (some (uri, p), asked)
    | none =>
      let above := seen.find? (·.uri == uri)
      if author.isSome && (above.map (·.author)) != author then (none, asked)
      else walkTo w seen author n ((above.map (·.replyTo)).getD "") asked

/-- The card of the first of the commonplace's doors (`cites`, as its card shows them) whose label the text
    names as a word. -/
def namedDoor (w : World) (text : String) : Option String := do
  let o ← w.objects[commonplaceId]?
  let doors := (doorsOf o).map fun (label, to) => (label.toLower, to)
  let words := (text.toLower.split fun c => !(c.isAlphanum || c == '\'' || c == '-' || c == '_')).map (·.toString)
  words.findSome? fun word => doors.lookup word

/-- `world-reach {uri, text, kind, author, replyTo?, root?, mentions?, chain?: [{uri, author, replyTo?}]}`: where
    an observed post reaches, and how, or nowhere (docs/FLEX.md §2; the bridge passes only what it saw). (a) A
    reply reaches the card whose recorded post is its direct parent (`how: reply`, with the post it answers); on
    Zulip, where a topic is one thread, the nearest recorded message up the topic past only its author's own,
    unless it mentions only other residents. (b) A spell line reaches its card (`spell`); a summons reaches the
    commonplace (`mention`). (c) Field lines anywhere in a thread the world opened reach that thread's card
    (`fields`), and (d) prose there naming one of the commonplace's doors reaches that door's card (`door`).
    Other prose deeper in a thread, and anything on Zulip that reached no recorded message, reaches nothing. -/
def reachOp (w : World) (j : Json) : Except String Json := do
  let uri ← j.getObjValAs? String "uri"
  let text ← j.getObjValAs? String "text"
  let kind ← j.getObjValAs? String "kind"
  let author ← j.getObjValAs? String "author"
  let replyTo := (← optText j "replyTo").getD ""
  let root := (← optText j "root").getD ""
  let mentions := (← optNat j "mentions").getD 0
  let chain ← match j.getObjVal? "chain" with
    | .ok c => (← c.getArr?).toList.mapM fun a => do
        pure ({ uri := ← a.getObjValAs? String "uri", author := ← a.getObjValAs? String "author",
                replyTo := (← optText a "replyTo").getD "" } : Seen)
    | .error _ => pure []
  if chain.length > reachHops then throw s!"chain is at most {reachHops} ancestors"
  let reached := fun (object : String) (slot : Option Json) (how : String) (answers : String) =>
    Json.mkObj ([("status", toJson "reached"), ("object", toJson object)] ++ ((slot.map fun s => [("slot", s)]).getD []) ++
      [("how", toJson how)] ++ (if answers.isEmpty then [] else [("replyTo", toJson answers)]))
  let unreached := Json.mkObj [("status", toJson "unreached")]
  let zulip := uri.startsWith "zulip://"
  let hops := if !zulip then 1 else if mentions > 0 && kind != "summon" then 0 else reachHops
  let (found, asked) := walkTo w chain (if zulip then some author else none) hops replyTo []
  -- A reply names what its parent was made for: the slot, a page's section, and why it left the town.
  if let some (at_, p) := found then
    return (reached p.object p.slot "reply" at_).mergeObj (Json.mkObj ((if p.page.isEmpty then [] else
      [("page", toJson p.page), ("section", toJson p.part)]) ++ (if p.unposted.isEmpty then [] else [("unposted", toJson p.unposted)])))
  let parsed := if kind.startsWith "wiki" then none else some (Spell.parse text)
  if let some (.spell card _ _) := parsed then return reached card none "spell" ""
  if kind == "summon" then return reached commonplaceId none "mention" ""
  if zulip || replyTo.isEmpty then return unreached
  let above := ((chain.find? (·.uri == replyTo)).map (·.replyTo)).getD ""
  let thread := match (walkTo w chain none reachHops above asked).1 with
    | some (_, p) => some p
    | none => if root.isEmpty || root == replyTo then none else w.posts[root]?
  let some t := thread | return unreached
  if parsed.isSome && !(Spell.bare text).isEmpty then return reached t.object t.slot "fields" ""
  match namedDoor w text with
  | some door => return reached door none "door" ""
  | none => return unreached

/-- The misfits hob reads past (`heardTurn`), its reading run instead of the refusal when it reads the
    spell meant. A duplicate field, an unclosed block, `fixed` and the host spells' own stay refusals:
    their hint is the fix. -/
def misfitClauses : List String := ["unknownField", "noAction", "badValue", "otherCard"]

/-- Words a card's `receive` heard and left silent (`heardSilent`) go to hob for that card (`heardTurn`),
    the silent answer discarded; whatever the card answered itself stands, and so does its silence when
    hob cannot read. -/
def heard (w : World) (req : TurnRequest) (ran : Except String (World × Json)) : Except String (World × Json) := do
  let (w', r) ← ran
  if !heardSilent r then return (w', r)
  match heardTurn (w.withCachesOf w') req [req.object] (heardText req.method req.argument) none with
  | some turn => turn
  | none => return (w', r)

/-- A direct turn's `receive` read as a spell (`routeSpell`); `none` when the host leaves the turn as asked.
    Words that reached the card and run no spell of it are heard (`heard`); a misfit spell is hob's to read
    past, its refusal standing when hob reads nothing better (`heardTurn`). -/
def spellTurn (w : World) (req : TurnRequest) (routed : Option SpellRoute := none) : Option (Except String (World × Json)) :=
  if req.reach == "mentioned" then none else
  let route := match routed with
    | some r => r
    | none => routeSpell w req.principal req.object req.method req.argument true (req.reach == "direct" || req.reach == "reply")
  match route with
  | .asIs => none
  | .run object method argument command =>
    let asked := { req with object := object, method := method, argument := argument,
                            post := (heardPost req.method req.argument).getD "",
                            origin := (if command.isEmpty then req.origin else "spell"),
                            command := (if command.isEmpty then req.command else command) }
    let ran := runTurnWith w asked { via := lentVia w req.principal object method }
    let words := method == "receive" && command.isEmpty && !req.reach.isEmpty &&
      !(heardText req.method req.argument).trimAscii.isEmpty
    some (if words then heard w asked ran else ran)
  | .usage object text =>
    some (.ok (w, Json.mkObj [("status", toJson "usage"), ("object", toJson object),
      ("text", toJson (hobTail w req.principal text "usage"))]))
  | .read object text extra =>
    some (.ok (w, Json.mkObj ([("status", toJson "usage"), ("object", toJson object), ("text", toJson text)] ++ extra)))
  | .refuse object clause reason hint =>
    let hint := hobTail w req.principal hint "hint"
    let refused := refuseSpell w req object clause reason hint
    some (if misfitClauses.contains clause then
      (heardTurn w req [object] (heardText req.method req.argument) (some { clause, reason, hint })).getD refused else refused)
  | .host object action fields => some (hostSpell w req object action fields)

/-- A quieted principal's turn, journaled as refused `quiet` (transient: the same identity runs again
    once the clock passes `until`), or a hand's past its hour's `turnQuota`, refused `quota` (`turnGate`) the same way. -/
def quietRefusal (w : World) (req : TurnRequest) (quiet : Refusal) : Except String (World × Json) := do
  let ctx : Ctx := { principal := req.principal, intent := req.intent, object := req.object, method := req.method,
                     argument := req.argument, digest := req.digest, ledger := Ledger.start, delivery := none,
                     ticksStart := 0 }
  let p : Proposal := { principal := req.principal, intent := req.intent, roots := [], writes := [], turn := w.height + 1 }
  let (w', r) := commit w p (entryBase ctx 0) (some quiet)
  return (w', turnReply w' r)

/-- A direct turn past the quiet check: the spell read (`routed`, when the caller has read it on this world
    already: `routedOf`), else the method as asked. -/
def runTurnHeard (w : World) (req : TurnRequest) (routed : Option SpellRoute := none) : Except String (World × Json) :=
  let req := { req with reach := reachOf w req }
  -- `world-turn` on `world` naming a power: its argument's fields are the spell's.
  let powerOnCard := cardPowers.contains req.method && ((w.objects[req.object]?).map (!hasMethod · req.method)).getD false
  if (req.object == worldId && !w.objects.contains worldId && worldPowers.contains req.method) || powerOnCard then
    let fields : List Spell.Binding := match req.argument with
      | .record fs => fs.filterMap fun (k, v) => match v with
        | .label t => some { name := k, value := t }
        | .natural n => some { name := k, value := toString n }
        | _ => none
      | _ => []
    hostSpell w req req.object req.method fields else
  match spellTurn w req routed with
  | some r => r
  | none => runTurnWith w req { via := lentVia w req.principal req.object req.method }

/-- A direct turn; `me` names the principal's avatar and a handle a resident's (`namedCard`), `me` refused `noAvatar` while it has
    none. A `receive` to a card of the message
    dialect is read as a spell first (`spellTurn`). -/
def runOne (w : World) (req : TurnRequest) (routed : Option SpellRoute := none) : Except String (World × Json) :=
  let asked := req.object
  let req := { req with object := namedCard w req.principal req.object }
  -- `me` before the speaker has an avatar: refused by name, saying what makes one.
  if asked == meCard && !w.objects.contains req.object && (retainedTurn w req).isNone then
    refuseSpell w req meCard "noAvatar" noAvatarReason "" else
  -- A retry is answered from the identity before its spell is read again: new code may route the
  -- same words elsewhere (codex host 13).
  if let some r := retainedTurn w req then .ok (w, r) else
  -- A quieted principal's turn is refused before it runs (`quietOf`; judge refuses every other entry of theirs), and
  -- so is a hand's past this hour's `turnQuota` (`turnGate`).
  match quietOf w req.principal req.object <|> turnGate w req.principal req.object with
  | some held => quietRefusal w req held
  | none => runTurnHeard w req routed

/-- How `runOne` would route a direct turn's spell on `w` (`spellTurn`'s `routeSpell`): none for a quieted
    speaker, one past its hour's turns, or a mention. Handed to `runOne`, the spell is not read twice. -/
def routedOf (w : World) (req : TurnRequest) : Option SpellRoute := do
  let req := { req with object := namedCard w req.principal req.object }
  guard ((quietOf w req.principal "").isNone && (turnGate w req.principal "").isNone)
  let req := { req with reach := reachOf w req }
  guard (req.reach != "mentioned")
  return routeSpell w req.principal req.object req.method req.argument true (req.reach == "direct" || req.reach == "reply")

/-- The misfit a route is, with its card (`misfitOf`). -/
def misfitIn (w : World) (req : TurnRequest) : SpellRoute → Option (String × Misfit)
  | .refuse object clause reason hint =>
    if misfitClauses.contains clause then some (object, { clause, reason, hint := hobTail w req.principal hint "hint" }) else none
  | _ => none

/-- The misfit a direct turn's spell is (`spellTurn`'s `.refuse` of a `misfitClauses` clause), with its
    card, as `runOne` would read it: none for a quieted speaker, a mention, or any other routing. -/
def misfitOf (w : World) (req : TurnRequest) : Option (String × Misfit) :=
  (routedOf w req).bind (misfitIn w req)

/-- A post with several spells at a line's start: each its own turn, as if posted alone (identity the post's
    plus `#1` .. `#3`, the post's text that spell, judged alone with its own receipt); a fourth and later are
    one refusal, `badSpell` clause `tooManySpells` (`#4`). A post is read by hob at most once: its misfit spells
    (`misfitOf`) are one reading after the spells that run, under the first one's identity, offered each one's
    card's table, its utterance those spells, a retry answered from that identity; where hob cannot read, each
    is refused alone as it would be. The reply lists the turns in order, the reading last. Each child
    without a receipt carries `spell`, the exact text used for that turn; a grouped reading carries
    its joined text. Children with receipts carry no `spell`. -/
def runSpells (w : World) (req : TurnRequest) (spells : List String) : Except String (World × Json) := do
  let mut w := w
  let mut turns : Array Json := #[]
  let mut misfits : Array (TurnRequest × String × String × Misfit) := #[]
  let withSpell := fun (r : Json) (spell : String) =>
    if (r.getObjVal? "receipt").isOk then r else r.setObjVal! "spell" (toJson spell)
  for (spell, i) in (spells.take Limits.spellsPerReply).zipIdx do
    let argument := match req.argument with
      | .record fs => Data.record (fs.map fun (k, v) => if k == "text" then (k, .label spell) else (k, v))
      | other => other
    let one := { req with intent := s!"{req.intent}#{i + 1}", argument,
                          digest := Journal.bodyHash (Json.arr #[toJson req.digest, toJson (i + 1)]) }
    let routed := routedOf w one
    if let some (card, m) := routed.bind (misfitIn w one) then
      misfits := misfits.push (one, spell, card, m)
      continue
    let (w', r) ← runOne w one routed
    w := w'
    turns := turns.push (withSpell r spell)
  if let some (first, _, _, m) := misfits[0]? then
    let text := "\n\n".intercalate (misfits.toList.map (·.2.1.trimAscii.toString))
    let joined : Misfit := if misfits.size == 1 then m else
      { clause := m.clause, reason := "; ".intercalate (misfits.toList.map fun (_, s, _, x) => s!"{((s.splitOn "\n").head?).getD s}: {x.reason}"),
        hint := "\n\n".intercalate (misfits.toList.map (·.2.2.2.hint)) }
    let argument := match first.argument with
      | .record fs => Data.record (fs.map fun (k, v) => if k == "text" then (k, .label text) else (k, v))
      | other => other
    let reading := { first with object := resolveCard first.principal first.object, argument }
    let reading := { reading with reach := reachOf w reading }
    match (retainedTurn w reading).map (fun r => Except.ok (w, r)) <|>
        heardTurn w reading (misfits.toList.map (·.2.2.1)) text (some joined) with
    | some turn =>
      let (w', r) ← turn
      w := w'
      turns := turns.push (withSpell r text)
    | none =>
      for (one, spell, card, x) in misfits do
        let (w', r) ← refuseSpell w { one with object := resolveCard one.principal one.object } card x.clause x.reason x.hint
        w := w'
        turns := turns.push (withSpell r spell)
  if spells.length > Limits.spellsPerReply then
    let n := Limits.spellsPerReply + 1
    let card := req.object
    let req := { req with intent := s!"{req.intent}#{n}", digest := Journal.bodyHash (Json.arr #[toJson req.digest, toJson n]) }
    let (w', r) ← if let some r := retainedTurn w req then pure (w, r) else
      refuseSpell w req card "tooManySpells"
        s!"A post casts at most {Limits.spellsPerReply} spells; the {spells.length - Limits.spellsPerReply} after them are not cast. Post them again."
        ""
    w := w'
    turns := turns.push (withSpell r (heardText req.method req.argument))
  return (w, Json.mkObj [("status", toJson "spells"), ("turns", Json.arr turns)])

/-- A post that is a plan (`Spell.plan`): its acts as one turn of the speaker under the post's identity (`runPlan`),
    read against the card the post reached; past `Limits.planActs` acts, or with none, refused `badSpell` whole. -/
def runPlanTurn (w : World) (req : TurnRequest) (acts : List String) : Except String (World × Json) :=
  let asked := req.object
  let req := { req with object := resolveCard req.principal req.object }
  if let some r := retainedTurn w req then .ok (w, r) else
  if asked == meCard && !w.objects.contains req.object then refuseSpell w req meCard "noAvatar" noAvatarReason "" else
  if acts.length > Limits.planActs then
    refuseSpell w req req.object "tooManyActs"
      s!"A plan carries at most {Limits.planActs} acts; this one has {acts.length}, and none was done. Make two plans." "" else
  if acts.isEmpty then
    refuseSpell w req req.object "noAction" "A plan with no act: under delvetalk plan, one spell a line at the margin." "" else
  match quietOf w req.principal req.object <|> turnGate w req.principal req.object with
  | some held => quietRefusal w req held
  | none =>
    let answers := match w.posts[req.replyTo]? with
      | some p => if p.object == req.object then req.replyTo else ""
      | none => ""
    let ctx : Ctx := { principal := req.principal, intent := req.intent, object := req.object, method := req.method,
                       argument := req.argument, digest := req.digest, delivery := none, ticksStart := 0, answers,
                       ledger := ((w.objects[req.object]?).map (·.chain)).getD Ledger.start }
    let argOf := fun (text : String) => match req.argument with
      | .record fs => Data.record (fs.map fun (k, v) => if k == "text" then (k, .label text) else (k, v))
      | other => other
    runPlan w ctx ((heardPost req.method req.argument).getD req.post) "spell" "spell" req.object (acts.map .spell) argOf

/-- One table for a card's actions (playtest 5: `delvetalk register sign` ran, `POST …/register/sign` answered
    `noMethod`): a direct turn naming an action the card offers as a spell but not as a method of its table (a grown
    verb, a placing or a host read) is that spell, cast through `receive` from its fields as a typed spell is, so a spell
    and its action route reach the same act. A field with no spell form leaves the turn as it was asked. -/
def spellOfAction (w : World) (req : TurnRequest) : TurnRequest :=
  if req.method == "receive" then req else
  match w.objects[namedCard w req.principal req.object]? with
  | none => req
  | some o =>
    let spelled := o.verbs.any (·.name == req.method) || placingSpells.contains req.method || hostReads.contains req.method
    if o.offers req.method || !o.offers "receive" || !spelled then req else
    match proposalSpell req.object req.method req.argument with
    | "" => req
    | spell => { req with method := "receive", argument := .record [("text", .label spell), ("post", .label "")] }

/-- A direct turn; a plan is one turn (`runPlanTurn`); a post with several spells at a line's start is one turn a
    spell (`runSpells`). -/
def runTurn (w : World) (req : TurnRequest) : Except String (World × Json) :=
  let req := spellOfAction w req
  let text := heardText req.method req.argument
  match (if req.method == "receive" && req.reach != "mentioned" && (Spell.quotes text).isNone then Spell.plan text else none) with
  | some acts => runPlanTurn w req acts
  | none =>
  let spells := Spell.segments (heardText req.method req.argument)
  let several := req.method == "receive" && spells.length > 1 && (Spell.quotes (heardText req.method req.argument)).isNone
  -- One identity, one request: a post's identity is bound by its one turn, or by its spells' turns (`#1`), so the
  -- other kind of request under it is `duplicateIdentity`.
  let other := boundEntry w req.principal (if several then req.intent else s!"{req.intent}#1")
  match other with
  | some entry => if isTransient entry then (if several then runSpells w req spells else runOne w req)
    else .ok (w, duplicate req.principal req.intent entry)
  | none => if several then runSpells w req spells else runOne w req

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

/-- One item of a `proposals` verdict as the Plan hears it (`World.Proposed<R>`): `proposal {object,
    method, argument}` or `unclear {reasons}`. -/
def proposedData (item : Json) : Except String Data := do
  match ← item.getObjValAs? String "tag" with
  | "proposal" =>
    return .variant "proposal" (proposalData (← item.getObjValAs? String "object") (← item.getObjValAs? String "method")
      (← decodeData Limits.dataDepth (← item.getObjVal? "argument")) ((item.getObjValAs? String "spell").toOption.getD ""))
  | _ => return .variant "unclear" (.record [("reasons", listData ((strings (item.getObjVal? "reasons").toOption).map Data.label))])

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
    let spell := (verdict.getObjValAs? String "spell").toOption.getD ""
    respond bounds responseType "proposal" [proposalData target method argument spell]
  | "proposals" =>
    let items ← liftEval ((← liftEval (verdict.getObjVal? "items")).getArr?)
    let proposed ← liftEval (items.toList.mapM proposedData)
    respond bounds responseType "proposals" [.record [("items", listData proposed)]]
  | _ =>
    let needs := strings (verdict.getObjVal? "needs").toOption
    respond bounds responseType "unclear" [.record [("needs", listData (needs.map Data.label))]]

/-- The response a `crossed` entry resumes a call across with: the target's result, or its refusal as the
    target voiced it. -/
def crossedResponse (bounds : DataBounds) (responseType : Ty) (e : Json) : M Data := do
  let answer := ((e.getObjVal? "outcome").toOption.bind (·.getObjVal? "answer" |>.toOption)).getD Json.null
  let text := fun (k : String) => (answer.getObjValAs? String k).toOption.getD ""
  if text "tag" == "admitted" then
    let result ← liftEval (decodeData Limits.dataDepth ((e.getObjVal? "result").toOption.getD (dataJson emptyRecord)))
    respond bounds responseType "returned" [.record [("result", result)]]
  else
    refusedReading bounds responseType (if (text "clause").isEmpty then text "class" else text "clause") (text "reason")

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
    turn is refused `staleRoot` and journaled under its original identity. A thing's wait on the clock
    for itself (`selfWait`) that the clock ends is a new cause: it goes on under the thing's own `chain`, not
    what was left of the chain that waited, so a thing that ticks itself (the tide) ticks for ever, each period
    with a whole budget, and missed periods are one wake at the clock it wakes to (docs/review/astra-2026-10-12
    world 5). It waited real clock time (a wait's `patience` is never 0), and a thing holds one such wait at a
    time (`awaitPlan`), so it cannot multiply. -/
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
  let (roots, cells) ← parseRoots (← sus.getObjVal? "roots")
  let behaviours ← parseBehaviours (← sus.getObjVal? "roots")
  let absent := strings (act.getObjVal? "absent").toOption
  let ticks ← natField act "ticks"
  let ledger ← ledgerOf (← sus.getObjVal? "ledger")
  let ledger := match kind with
    | .timedOut => if selfWait object sus then ((w.objects[object]?).map (·.chain)).getD ledger else ledger
    | _ => ledger
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
      | some now => now != v && !(v < now && ((staged.lookup id).isNone || rootAdmits w staged id v (cells.lookup id) (id == object)))
      | none => true).map (·.1)
    <|> (absent.find? fun id => w.objects.contains id)
  let refusal := (staleBehaviour w behaviours).orElse fun _ =>
    stale?.map fun id => ({ cls := "staleRoot", object := some id } : Refusal)
  if let some refusal := refusal then
    let stalled : Proposal :=
      { principal := principal
        intent := intent
        roots := roots
        behaviours := behaviours
        writes := []
        turn := w.height + 1
        absent := absent }
    let (w', r) := commit w stalled (entryBase ctx ctx.usedBefore) (some refusal)
    return (w', turnReply w' r)
  let writes ← parseRecordedWrites (← activityArray act "writes")
  let sends ← (← (← activityArray act "sends").getArr?).toList.mapM sendOfJson
  let grants ← (((act.getObjVal? "grants").toOption.bind (·.getArr?.toOption)).getD #[]).toList.mapM Grant.ofJson
  let creates ← ((← (← activityArray act "creates").getArr?).toList.mapM fun r => do
    let id ← r.getObjValAs? String "object"
    let seed ← r.getObjVal? "seed"
    let (o, sources) ← buildObject w (← expandInputs w (← r.getObjVal? "compile")) seed (r.getObjVal? "read").toOption
      (r.getObjVal? "chain").toOption principal (w.height + 1) (← createdLaw r)
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
      behaviours := behaviours
      cells := cells
      writes := writes
      principal := principal
      intent := intent
      subject := principal
      method := method
      via := via
      argument := argument
      direct := delivery.isNone
      sender := if delivery.isSome then (act.getObjValAs? String "caller").toOption.getD "" else ""
      grants := grants
      revokes := strings (act.getObjVal? "revokes").toOption
      placements := ← (((act.getObjVal? "placements").toOption.bind (·.getArr?.toOption)).getD #[]).toList.mapM Placement.ofJson
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
      crossings := ← activityNat act "crossings"
      publishes := (((act.getObjVal? "publishes").toOption.bind (·.getArr?.toOption)).getD #[]).toList
      checks := ← activityNat act "checks"
      post := (act.getObjValAs? String "post").toOption.getD ""
      -- A spell's origin and command go on with it, so a second suspension journals them and a
      -- stale re-run of that one runs as the spell it was (codex host 15).
      origin := (act.getObjValAs? String "origin").toOption.getD "request"
      command := (act.getObjValAs? String "command").toOption.getD ""
      reach := (act.getObjValAs? String "reach").toOption.getD ""
      limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))] }
  let action : M Data := do
    let s ← get
    let some obj := s.world.objects[object]? | evaluation s!"unknown object {object}"
    let compiled ← compiledMethod obj method
    let some (_, responseType, _) := computationParts compiled.type | evaluation "the method is not an activity"
    let crossing := (outcome.getObjVal? "crossing").toOption
    let response ← match kind with
      | .reply e =>
        if tagOf e == "interpreted" then interpretedResponse compiled.bounds responseType e
        else if tagOf e == "crossed" then crossedResponse compiled.bounds responseType e
        else respond compiled.bounds responseType "reply" [receiptReply e]
      | .timedOut => match crossing with
        | some c =>
          let world := (c.getObjValAs? String "world").toOption.getD ""
          refusedReading compiled.bounds responseType "timedOut" s!"{world} did not answer within {Limits.crossingPatience} clock minutes."
        | none => respond compiled.bounds responseType "timedOut" [emptyRecord]
    -- The activity began with only its own object as a root.
    let binding := Delvetalk.Turn.Binding.make object principal intent
      (roots.filter (·.1 == object))
    let b ← budgetsNow
    -- The journaled checkpoint holds the rows it may still read (`Held.kept`): no store.
    let held := Held.journaled object ((roots.lookup object).getD obj.version)
    -- `checkpoint` is the journaled one (`expandSuspended`), so its digest is the journal's.
    let (next, reads) ← liftEval (Delvetalk.Turn.resumeEntry (← entryOf compiled) checkpoint
      checkpoint.digest binding response b held.store compiled.dictionary)
    held.note reads
    drive 0 object ctx.caller compiled binding held next 0
  let (result, st) := action.run.run init
  finishTurn w ctx result st

/-- The actions the world's policy asks the speaker before hob's reading runs them (`confirmFor`). -/
def confirmFor (w : World) : List String :=
  (((w.objects[policyId]?).bind fun o => (Law.rawField "confirmFor" o.state).bind listOf).getD []).filterMap labelOf

/-- A spell as an offer prints it: each line indented, so a reply quoting the offer casts nothing. -/
def indentSpell (spell : String) : String :=
  String.join (((spell.trimAsciiEnd.toString).splitOn "\n").map fun l => s!"    {l}\n")

/-- The fields of the forms offered that hob's needs name as a word (`colour`, or `which colour?`), each
    once, in the forms' order: only a field's own name is ever said, never the model's words. -/
def neededFields (needs : List String) (forms : List Spell.Form) : List String :=
  let said := needs.flatMap fun n => ((n.split fun c => !(c.isAlphanum || c == '_' || c == '-')).toList.map (·.toString))
  (forms.flatMap fun f => f.fields.map (·.name)).eraseDups.filter said.contains

/-- The card `id` as `reader` reads it now, as text (`world-card`'s); none when it renders none. -/
def cardRendered (w : World) (id reader : String) : Option String :=
  match w.objects[id]? with
  | none => none
  | some o =>
    let init : TurnState := { world := w, principal := reader, intent := "", subject := reader, ticks := Limits.maxTurnTicks,
                              limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))] }
    match (renderCard id o reader "" "").run.run init with
    | (.ok (.ok document), _) => (Delvetalk.Document.render document).toOption
    | _ => none

/-- `text` followed by `block` within `bound` characters (`Limits.cardShownChars`, or a world's `cardRoom`), the one
    place the bound is applied to a card: over it, `text` is cut to leave room for a closing line that says so and
    where the rest is read, and `block` (whole lines) stands after it. -/
def clipCard (id text block : String) (bound : Nat := Limits.cardShownChars) : String :=
  let whole := if block.isEmpty then text else (if text.isEmpty || text.endsWith "\n" then text else text ++ "\n") ++ block
  if whole.length ≤ bound then whole else
  let note := s!"\n[clipped at {bound} characters; world-inspect {id} reads its source]\n"
  (text.take (bound - note.length - block.length)).toString ++ note ++ block

/-- The card `id` shows its readers as `text`, clipped by `clipCard` at the world's `cardRoom`, with one line for each
    want it holds (`wants <name>: <reading>: <spell>`, `wantRows` for `reader`) while the lines stay within a quarter of
    the one-post bound (`Limits.cardShownChars`). -/
def shownCard (w : World) (id reader text : String) : String :=
  let lines : List String := match w.objects[id]? with
    | some o => (wantRows w reader id o).map fun (row : Json) =>
      let field := fun (k : String) => (row.getObjValAs? String k).toOption.getD ""
      let reading := if field "reading" == "" then "" else s!" {field "reading"}:"
      s!"wants {field "name"}:{reading} {(field "asks").trimAscii.toString.replace "\n" " / "}\n"
    | none => []
  let (block, _) := lines.foldl (init := ("", true)) fun (held : String × Bool) (l : String) =>
    if held.2 && held.1.length + l.length ≤ Limits.cardShownChars / 4 then (held.1 ++ l, true) else (held.1, false)
  clipCard id text block w.cardRoom

/-- `cardRendered` within `Limits.cardShownChars` characters, "" for none: what an interpretation shows the model
    of the card answered (its wants go with it as `wants`, whole). -/
def cardText (w : World) (id reader : String) : String :=
  clipCard id ((cardRendered w id reader).getD "") ""

/-- A question hob read no spell into, answered by the card itself (the decision after the v8 deploy: data, not
    narration): its exact text as the speaker reads it (`shownCard`, what `world-card` answers). The paint is
    the front's to place above it (renders are per process, outside the world). -/
def cardAnswer (w : World) (id reader : String) : String :=
  shownCard w id reader ((cardRendered w id reader).getD "")

/-- Settle hob's reading of words a card heard (`heardTurn`), as the speaker's turn under the suspension's
    identity. A spell, or `grow:` and the spell that uses the verb, runs (`runHeard`), unless the policy asks
    first for one of its actions (`confirmFor`): then the speaker is offered the spells to send. A question
    (`ask:`, or hob's spell that did not fit) naming fields of the forms offered is offered as what is still
    needed, with the spells that take them; naming none, as one fixed line pointing at the card's spells.
    Anything else is silence: `none`, a model that could not be asked, the reading's deadline passed. A misfit spell hob read nothing better for is the host's refusal of it. A changed offered
    card refuses the reading as `staleRoot`, naming its behaviour revision, before any spell runs.
    hob's lines are in the speaker's tongue: the one they state, else the one their words are in (`Tongue.choose`). -/
def resumeHeard (w : World) (sus : Json) (kind : Resume) : Except String (World × Json) := do
  let identity ← sus.getObjVal? "identity"
  let principal ← identity.getObjValAs? String "principal"
  let intent ← identity.getObjValAs? String "intent"
  let outcome ← sus.getObjVal? "outcome"
  let act ← outcome.getObjVal? "activity"
  let card ← act.getObjValAs? String "object"
  let i := (expandInterpretation w outcome).getD Json.null
  let (roots, _) ← parseRoots (← sus.getObjVal? "roots")
  let behaviours ← parseBehaviours (← sus.getObjVal? "roots")
  let stale := staleBehaviour w behaviours
  let roots := if stale.isSome then roots else roots.map fun (id, seen) =>
    (id, ((w.objects[id]?).map (·.version)).getD seen)
  let tongue := Tongue.choose w principal ((i.getObjValAs? String "utterance").toOption.getD "")
  let ctx : Ctx := { principal, intent, object := card, method := "receive",
                     argument := ← decodeData Limits.dataDepth (← activityArgument w act),
                     digest := ← sus.getObjValAs? String "turnRequest", ledger := ← ledgerOf (← sus.getObjVal? "ledger"),
                     delivery := none, resumes := some (← sus.getObjValAs? String "hash"), ticksStart := 0,
                     answers := (sus.getObjValAs? String "replyTo").toOption.getD "",
                     readingRoots := roots, behaviours }
  let close := fun (offer : String) (refusal : Option Refusal) =>
    let p : Proposal := { principal, intent, roots, behaviours, rebaseOwn := some card, writes := [], turn := w.height + 1 }
    let (w', r) := commit w p (entryBase ctx 0 ++
      (if offer.isEmpty then [] else [("offers", offersJson [(principal, offer)])])) refusal
    (w', turnReply w' r)
  if let some r := stale then return close "" (some r)
  let verdict := match kind with
    | .reply e => ((e.getObjVal? "outcome").toOption.bind (·.getObjVal? "verdict" |>.toOption)).getD Json.null
    | .timedOut => Json.null
  let items := match (verdict.getObjValAs? String "tag").toOption with
    | some "proposal" => [verdict]
    | some "proposals" => (((verdict.getObjVal? "items").toOption.bind (·.getArr?.toOption)).getD #[]).toList
    | _ => []
  let steps := items.filterMap fun v => do
    guard ((v.getObjValAs? String "tag").toOption == some "proposal")
    pure ({ object := ← (v.getObjValAs? String "object").toOption, method := ← (v.getObjValAs? String "method").toOption,
            argument := ← (v.getObjVal? "argument").toOption.bind (decodeData Limits.dataDepth · |>.toOption),
            spell := (v.getObjValAs? String "spell").toOption.getD "" } : HeardStep)
  -- hob's plan: its acts run as a post's plan runs, read in the turn against the card (`runPlan`), unless the policy asks first.
  if (verdict.getObjValAs? String "tag").toOption == some "plan" then
    let acts := strings (verdict.getObjVal? "acts").toOption
    let asks := confirmFor w
    if acts.any (fun a => match Spell.parse a with | .spell _ action _ => asks.contains action | _ => false) then
      return close (Tongue.say tongue "asksFirst" ++ "\n\n" ++ indentSpell ("delvetalk plan\n" ++ "\n".intercalate acts)) none
    let text := fun (k : String) => (act.getObjValAs? String k).toOption.getD ""
    let argOf := fun (t : String) => match ctx.argument with
      | .record fs => Data.record (fs.map fun (k, v) => if k == "text" then (k, .label t) else (k, v))
      | other => other
    return ← runPlan w ctx (text "post") (text "reach") "interpreted" card (acts.map .spell) argOf
  if !items.isEmpty && steps.length == items.length then
    let asks := confirmFor w
    if steps.any (asks.contains ·.action) then
      return close (Tongue.say tongue "asksFirst" ++ "\n" ++ String.join (steps.map fun x => "\n" ++ indentSpell x.spell)) none
    let text := fun (k : String) => (act.getObjValAs? String k).toOption.getD ""
    return ← runHeard w ctx (text "post") (text "reach") steps
  if let some r := (i.getObjVal? "refusal").toOption then
    let text := fun (k : String) => (r.getObjValAs? String k).toOption
    return close "" (some { cls := "badSpell", clause := text "clause", object := some card, reason := text "reason", hint := text "hint" })
  let needs := strings (verdict.getObjVal? "needs").toOption ++ items.flatMap fun v => strings (v.getObjVal? "reasons").toOption
  let forms := (((i.getObjVal? "offers").toOption.bind (decodeData Limits.dataDepth · |>.toOption)).bind listOf |>.getD []).filterMap Spell.Form.ofData
  let asked := needs.any fun n => !n.isEmpty && n != "not addressed" && !n.startsWith "model:"
  -- A question hob reads no spell or ask into is answered by the card itself (`cardAnswer`); other words, by silence.
  let question := ["?", "？", "؟"].any (((i.getObjValAs? String "utterance").toOption.getD "").trimAscii.toString.endsWith ·)
  let answered := match kind with | .reply _ => !needs.any (·.startsWith "model:") | .timedOut => false
  if !asked && question && answered then return close (cardAnswer w card principal) none
  if !asked then return close "" none
  let fields := neededFields needs forms
  -- An ask naming no field the card's spells take: none of them fits the words; the card's `?` lists them.
  if fields.isEmpty then return close (Tongue.say tongue "noneTakes" [("card", card)] ++ "\n") none
  let taking := forms.filter fun f => f.fields.any (fields.contains ·.name)
  return close (Tongue.say tongue "needs" [("fields", ", ".intercalate fields)] ++ "\n" ++
    String.join (taking.map fun f => "\n" ++ indentSpell (spellTemplate f.card f))) none

/-- Continue a suspended activity (hob's reading of words a card heard is the host's: `resumeHeard`). A
    direct turn whose resumption is refused `staleRoot` (its roots moved past what `movedRootAdmits`
    allows while it waited) is re-run once, at once, from its journaled request on the current state: the refusal is transient, so the identity is free, and
    the re-run carries `rerun: true` so a second stale resumption of it is final. -/
def resumeOne (w : World) (sus : Json) (kind : Resume) : Except String (World × Json) := do
  if hostResumed sus then return ← resumeHeard w sus kind
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
      command := (act.getObjValAs? String "command").toOption.getD ""
      reach := (act.getObjValAs? String "reach").toOption.getD "" }
  let (w'', again) ← runTurnWith w' req { rerun := true }
  let staleHash := ((r.getObjVal? "receipt").toOption.bind (·.getObjValAs? String "hash" |>.toOption)).getD ""
  return (w'', again.setObjVal! "rerunOf" (toJson staleHash))

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
  let to ← d.getObjValAs? String "to"
  let method ← d.getObjValAs? String "method"
  let senderId := (d.getObjValAs? String "sender").toOption.getD ""
  -- An activity's end goes to the supervisor its object was created under, which offered `ended` or
  -- was the creator: it may be a helper then, the receiving object chose it.
  let receiver := method == "ended" && ((w.objects[senderId]?).map (·.supervisor)) == some to
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
    return commit w p deliveryFields (some { cls := "lawRefused", clause := some "noGrant", object := some to, reading := some s!"the grant this send to {to} was made under no longer stands." })
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
    let how := { how with reach := (d.getObjValAs? String "reach").toOption }
    -- A delivered `receive` to a card of the message dialect is read as a spell, as a direct turn's
    -- is, against the card it was sent to (not under a grant: that names the one method it may run).
    -- A rule's spell is its owner's act, so the host's spells read in it as in a direct reply.
    let ruled := (d.getObjVal? "rule").toOption.isSome
    match if via.isEmpty then routeSpell w principal object method argument false (speaker := ruled) else .asIs with
    | .host card action fields =>
      hostSpell w { req with object := card, method := action } card action fields how
    | .run _ m a command =>
      runTurnWith w { req with method := m, argument := a, command := command,
                               post := (heardPost method argument).getD "",
                               origin := (if command.isEmpty then req.origin else "spell") } how
    | .refuse card clause reason hint =>
      let p : Proposal := { principal := principal, intent := id, roots := [], writes := [], turn := w.height + 1 }
      return commit w p deliveryFields
        (some { cls := "badSpell", clause := some clause, object := some card, reason := some reason, hint := some hint })
    | _ => runTurnWith w req how

/-- A turn's reply as `reader` sees it when it ran in another op's settling pass (a resumption, a
    delivery): whole but for its offers when `reader` is the turn's own principal, else the projection
    of its receipt (`projectEntry`) and what a refusal may say in public (codex host 1). The offers are
    their addressees', read with `world-offers`. -/
def settledFor (w : World) (reader : String) (r : Json) : Json :=
  match r.getObj?, r.getObjVal? "receipt" with
  | .ok fields, .ok entry =>
    let owner := ((entry.getObjVal? "identity").toOption.bind fun i => (i.getObjValAs? String "principal").toOption).getD ""
    if owner == reader && !reader.isEmpty then Json.mkObj (fields.toList.filter (·.1 != "offers"))
    else Json.mkObj ([("status", (r.getObjVal? "status").toOption.getD Json.null), ("receipt", projectEntry w reader entry)] ++
      ["public", "rerunOf"].filterMap fun k => (r.getObjVal? k).toOption.map (k, ·))
  | .ok fields, .error _ => Json.mkObj (fields.toList.filter (·.1 != "offers"))
  | .error _, _ => r

/-- Up to `limit` deliveries, oldest first; sends of a delivery join the queue. Each is shown as
    `reader` may see it (`settledFor`). -/
def deliver (w : World) (limit : Nat) (reader : String) : Except String (World × Json) := do
  let mut w := w
  let mut receipts : Array Json := #[]
  for _ in [0:min limit Limits.deliveriesPerCall] do
    let some d := w.pending.find? (deliverable w) | break
    let (w', r) ← deliverOne w d
    w := w'
    receipts := receipts.push (settledFor w reader r)
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
    let some d := w.pending.find? (deliverable w) | break
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

/-- The method table as `principal` reads it: each method a turn can run (it takes a context) with
    `admits` (`methodAdmits`). -/
def methodsFor (w : World) (o : Object) (principal : String) : Json :=
  let facts := admitFacts w o principal
  Json.arr ((((offeredRows o.methods).getArr?.toOption).getD #[]).map fun m =>
    match (m.getObjValAs? Bool "context").toOption, (m.getObjValAs? String "name").toOption with
    | some true, some name => m.setObjVal! "admits" (methodAdmitsBy o facts name)
    | _, _ => m)

/-- The law rows with the host's metarule first when the world has an opener (docs/ROOT.md §2.1):
    every law admits the opener's amendment, and the laws page says so. -/
def openerRow (w : World) (rows : Json) : Json :=
  if w.opener.isEmpty then rows else
  Json.arr (#[Json.mkObj [("name", toJson "opener"), ("clause", toJson s!"request.kind == 2 and request.subject == \"{w.opener}\""),
    ("reading", toJson "the hand that opened the world may amend any law"), ("host", toJson true)]] ++ ((rows.getArr?.toOption).getD #[]))

/-- `world-inspect {principal, object}`: the pin, law text and entry source an object
    shows a reader its read policy permits (`source: false` leaves the source out), and its method
    table with each turnable method's `admits` for the reader. -/
def inspectOp (w : World) (j : Json) : Except String Json := do
  if let some asked := ← optText j "grant" then
    let grant ← boundedText "grant" Limits.maxIntentBytes asked
    let principal ← readerOf j
    match grantRead w grant with
    | some row =>
      if viewable w principal ((row.getObjValAs? String "object").toOption.getD "") then
        return Json.mkObj [("status", toJson "inspected"), ("grant", row)]
      return Json.mkObj [("status", toJson "denied")]
    | none => return Json.mkObj [("status", toJson "unknown"), ("grant", toJson grant)]
  let id ← j.getObjValAs? String "object"
  let principal ← readerOf j
  match w.objects[id]? with
  | none => return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  | some o =>
    if !o.read.permits principal then
      return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
    -- The source only when asked for: the library and every reader that wants the laws, forms and
    -- methods never pay for it.
    let withSource ← match j.getObjVal? "source" with
      | .ok (.bool b) => pure b
      | .ok _ => throw "source must be true or false"
      | .error _ => pure false
    let offered := (spellFormsData w id o).filter (offeredTo w id o principal <| formAction ·)
    return Json.mkObj ([("status", toJson "inspected"), ("object", toJson id), ("pin", toJson o.pin),
      ("pinSlug", toJson ((Slug.ofCid o.pin).getD "")), ("law", toJson o.lawText),
      -- The law's clauses with their readings, and whether a Bend `law(old, new, request)` judges after it.
      ("laws", openerRow w (lawRows o)), ("cites", toJson (lawCitations w o.law)), ("bendLaw", toJson o.predicate)] ++
      (if withSource then [("source", toJson (entrySource o))] else []) ++ [("methods", methodsFor w o principal),
      ("supervisor", toJson o.supervisor), ("maker", toJson o.maker), ("retired", toJson (objectRetired o)),
      -- Its canonical bytes, and its scalar part's, which `Bounds.maxCellBytes` bounds as it bounds each row.
      ("stateBytes", toJson (stateBytes o.state)),
      ("scalarBytes", toJson (Delvetalk.Canonical.encode o.cells.scalar).size),
      ("forms", dataJson (listData offered)),
      -- The actions the reader is offered, by name (what a card's usage lists for them), and each one's
      -- spell as `?` prints it (`spellTemplate`), which a front copies rather than composes.
      ("offered", toJson (offered.map formAction)),
      ("templates", Json.mkObj ((offered.filterMap Spell.Form.ofData).map fun f => (f.action, toJson (spellTemplate id f)))),
      -- The numbers `request.kind` reads, by name (`proposed`: a write no method of the object made).
      ("requestKinds", Json.mkObj (Law.kindNames.map fun (n, k) => (n, toJson k)))] ++
      (if o.fixed.isEmpty then [] else [("fixed", toJson o.fixed)]) ++
      -- Where its code came from, and the line `?` prints for it (`lineageLine`).
      (match o.madeFrom with | some m => [("madeFrom", m), ("lineage", toJson (lineageLine w o))] | none => [])) |> fun r =>
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
    -- A root `card` override answers in place of `render` until cleared (docs/ROOT.md §1.1).
    if let some text := w.cards[id]? then
      return (w, Json.mkObj [("status", toJson "card"), ("object", toJson id),
        ("text", toJson (shownCard w id principal text)), ("override", toJson true)])
    let init : TurnState := { world := w, principal, intent := "", subject := principal, ticks := Limits.maxTurnTicks,
                              limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks))] }
    -- `whole`: the card unclipped (`Card.limit` none), for a transport that threads it into parts itself.
    let whole := (j.getObjValAs? Bool "whole").toOption.getD false
    let (r, st) := (renderCard id o principal "" "" whole).run.run init
    -- The render definition compiled here stays compiled for the next read.
    let w := w.withCachesOf st.world
    match r with
    | .ok (.ok document) =>
      return (w, Json.mkObj [("status", toJson "card"), ("object", toJson id),
        ("text", toJson (shownCard w id principal (← Delvetalk.Document.render document))),
        ("document", dataJson document)])
    | .ok (.error clause) => return (w, Json.mkObj [("status", toJson "refused"), ("object", toJson id), ("clause", toJson clause)])
    | .error _ => return (w, Json.mkObj [("status", toJson "refused"), ("object", toJson id), ("clause", toJson "render")])

/-- `world-derived {principal, object, view}`: a derived view (`views()` names it) read from outside a turn, as
    `viewDerived` answers an object inside one: the pure definition run on the committed state with the reader's
    Context as a card is rendered (`cardContext`), under the read authority `world-card` keeps, journaling nothing. A
    card's `view` (docs/VIEWS.md) is the one a front draws. `noView` when the package names no such view, `view` when it
    fails or answers something other than data (its `detail` the machine's words), `budget` out of ticks, `viewTooLarge`
    past `Limits.maxViewBytes` of wire JSON. -/
def derivedOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← readerOf j
  let id := resolveCard principal (← j.getObjValAs? String "object")
  let view ← j.getObjValAs? String "view"
  let refused := fun (clause : String) => Json.mkObj [("status", toJson "refused"), ("object", toJson id), ("view", toJson view),
    ("clause", toJson clause)]
  match w.objects[id]? with
  | none => return (w, Json.mkObj [("status", toJson "unknown"), ("object", toJson id)])
  | some o =>
    if !o.read.permits principal then return (w, Json.mkObj [("status", toJson "denied"), ("object", toJson id)])
    -- A view may nest as deep as a Document on the wire (a board's tiles are a long list), within the turn's ticks.
    let init : TurnState := { world := w, principal, intent := "", subject := principal, ticks := Limits.maxTurnTicks,
                              limits := Json.mkObj [("ticks", toJson (toString Limits.maxTurnTicks)),
                                                    ("depth", toJson (toString Delvetalk.Bounds.documentWireDepth))] }
    let (r, st) := (derivedView id o view (cardContext w id principal "" "" w.height view) (detailed := true)).run.run init
    let w := w.withCachesOf st.world
    match r with
    | .ok (.ok value) =>
      let bytes := Delvetalk.Compiler.ObjectiveBendDataWire.dataJsonBytes value
      if bytes > Limits.maxViewBytes then return (w, refused "viewTooLarge") else
      return (w, Json.mkObj [("status", toJson "derived"), ("object", toJson id), ("view", toJson view),
        ("version", toJson o.version), ("bytes", toJson bytes), ("value", dataJson value)])
    | .ok (.error e) =>
      let clause := (e.splitOn ": ").headD e
      return (w, if clause == e then refused e else (refused clause).setObjVal! "detail" (toJson ((e.drop (clause.length + 2)).take 400)))
    | .error _ => return (w, refused "view")

/-- The system text an interpretation sends: the Policy's own pure `prompt(state, offers,
    utterance)` when its package defines one and it renders text under the turn tick budget,
    else none (the caller then sends the `system` field). The method table does not list
    `prompt` (its offers are not a form), so the definition is compiled by name and cached. `name` is `prompt`
    (the system text: the policy's own and the host's contract) or `userTurn` (what residents wrote, quoted:
    the card, its forms, wants, pages and the misfit spell, then the speaker's words). -/
def policyPrompt (w : World) (o : Object) (offers : Data) (utterance : String) (asked : Data := .record [])
    (name : String := "prompt") : Option String × World :=
  match compileDef w o name with
  | .error _ => (none, w)
  | .ok (c, w') =>
    let w' := { w' with compiled := boundedInsert w'.compiled Limits.maxCompiledPackets (defKey o name) c }
    match c.entry with
    | none => (none, w')
    | some entry =>
      -- `prompt(state, offers, utterance)`, or `prompt(state, asked)` taking the whole request
      -- `{utterance, offers, card, misfit, wants, pages}` (docs/FLEX.md §4 host 5), fitted to its type.
      let arguments := match c.type with
        | .arrow _ _ _ (.arrow _ _ dom .label) => [o.state, fitRecord c.bounds dom asked]
        | _ => [o.state, offers, .label utterance]
      match (runPure entry arguments Limits.maxTurnTicks).1 with
      | .ok (.label text) => (some text, w')
      | _ => (none, w')

/-- The state of a Policy object as `{model, system, examples}` (absent fields are null), with
    `system` the Policy's rendered prompt for these offers and utterance when it has one. -/
def policyJson (w : World) (id : String) (offers : Data) (utterance : String) (asked : Data := .record []) : Json × World :=
  match w.objects[id]? with
  | some o =>
    match o.state with
    | Data.record f =>
      let (prompt, w) := policyPrompt w o offers utterance asked
      let field := fun k => ((f.lookup k).map plainJson).getD Json.null
      (Json.mkObj [("model", field "model"), ("system", (prompt.map toJson).getD (field "system")),
        ("examples", field "examples"), ("lexicon", field "lexicon")], w)
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
    -- The card answered, as the speaker reads it now; the misfit spell hob reads past (`heardTurn`).
    let speaker := ((s.getObjVal? "identity").toOption.bind (·.getObjValAs? String "principal" |>.toOption)).getD ""
    let i := (interpretationOf w s).getD Json.null
    let misfit := (i.getObjValAs? String "misfit").toOption.getD ""
    let card := cardText w object speaker
    let reach := ((s.getObjVal? "outcome").toOption.bind (·.getObjVal? "activity" |>.toOption)
      |>.bind (·.getObjValAs? String "reach" |>.toOption)).getD ""
    -- The card's wants as they stand, each with the spell that answers it filled, and the library's
    -- pages: what hob may read the words into besides the forms offered.
    let wants := ((w.objects[object]?).map (wantRows w speaker object ·)).getD [] |>.map fun r =>
      let field := fun (k : String) => Data.label ((r.getObjValAs? String k).toOption.getD "")
      Data.record [("name", field "name"), ("reading", field "reading"), ("asks", field "asks")]
    let pages := (((w.objects["library"]?).filter (·.read.permits speaker)).bind fun o =>
      (Law.rawField "pages" o.state).bind Law.rowsOf).getD []
    let asked := Data.record [("utterance", .label utterance), ("offers", offers), ("card", .label card),
      ("misfit", .label misfit), ("wants", listData wants), ("pages", listData pages)]
    let (shown, w') := policyJson w policy offers utterance asked
    -- The user turn the policy quotes residents' writing in (`Policy.userTurn`); a policy with none sends the words alone.
    let (userTurn, w') := match w.objects[policy]? with
      | some p => policyPrompt w' p offers utterance asked "userTurn"
      | none => (none, w')
    -- A model the Plan named takes precedence over the policy's own.
    let shown := if model.isEmpty then shown else shown.setObjVal! "model" (toJson model)
    w := w'
    -- How many transient failures the host journaled, and the clock before which the next is not asked.
    let (tried, next) := (w.attempts[id]?).getD (0, 0)
    pending := pending.push (Json.mkObj [("id", toJson id), ("object", toJson object), ("policy", shown),
      ("utterance", toJson utterance), ("user", toJson (userTurn.getD utterance)), ("offers", plainJson offers),
      ("roots", (s.getObjVal? "roots").toOption.getD (Json.arr #[])), ("card", toJson card),
      ("misfit", toJson misfit), ("wants", plainJson (listData wants)), ("reach", toJson reach), ("attempts", toJson tried),
      ("next", if next > w.clock then toJson next else Json.null)])
  return (w, Json.mkObj [("status", toJson "interpretations"), ("pending", Json.arr pending)])

def abortText : Abort → String
  | .request m | .evaluation m => m
  | .budget r => s!"{r} budget exhausted"
  | .refused cls r _ => s!"{cls}: {r}"
  | .named r => s!"{r.cls}: {(r.voiced.reason).getD ""}"
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
def proposalVerdict (w : World) (target self : String) (obj : Object) (carries : Data → Bool)
    (method : String) (argument : Data) (card : String := target) (grown : List String := []) : World × Json := Id.run do
  -- A grown verb (or one the same answer grows, `grown`) is proposed as its card's `act`, its spell the verb's.
  let spell := proposalSpell card method argument
  let (method, argument) := match grownAct obj method argument with
    | some a => (actMethod, a)
    | none => if grown.contains method then (actMethod, actArgument method argument) else (method, argument)
  -- A host placing spell the card does not declare is staged as the spell stages it (`runHeard`, `placementsOf`):
  -- its fields are read there, and the law judges it at the commit.
  if placingSpells.contains method && !obj.offers method then
    unless carries (.variant "proposal" (proposalData target method argument spell)) do
      return (w, unclearVerdict [s!"the object cannot carry a proposal of {target} {method}"])
    if let .error (_, reason) := placingChange w obj target method (labelsOf argument) (labelsOf argument) then
      return (w, unclearVerdict [reason])
    return (w, Json.mkObj [("tag", toJson "proposal"), ("object", toJson target), ("method", toJson method),
      ("argument", dataJson argument), ("spell", toJson spell)])
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
  -- A proposal names the object whose form it fitted and the spell that asks it
  -- (`Interpreted.proposal {object, method, argument, spell}`), so a card can hold it and print it back.
  unless carries (.variant "proposal" (proposalData target method argument spell)) do
    return (w, unclearVerdict [s!"the object cannot carry a proposal of {target} {method}"])
  return (w, Json.mkObj [("tag", toJson "proposal"), ("object", toJson target), ("method", toJson method),
    ("argument", dataJson argument), ("spell", toJson spell)])

/-- hob's `grow: NAME "reading"` (docs/FOUNDATION.md §10): a verb the words mean that the card does
    not take yet, with the spell that uses it on the lines after, answered as two proposals in order, the
    grow (the host's placing spell, which a `call` stages: `placementsOf`) and the use (the card's `act`
    with the verb). The spell must name the verb grown; the card is the one it names. -/
def growVerdict (w : World) (principal self : String) (carries : Data → Bool) (said : String) :
    World × Json := Id.run do
  let lines := said.splitOn "\n"
  let head := ((lines.headD "").drop 5).trimAscii.toString
  let name := (head.takeWhile (· != ' ')).toString
  let rest := (head.drop name.length).trimAscii.toString
  let reading := if rest.length ≥ 2 && rest.startsWith "\"" && rest.endsWith "\"" then ((rest.drop 1).dropRight 1).toString else rest
  if name.isEmpty || reading.isEmpty then return (w, unclearVerdict ["grow: names the verb and says what it does"])
  let .spell card action fields := Spell.parse ("\n".intercalate (lines.drop 1))
    | return (w, unclearVerdict [s!"grow: {name} is followed by the spell that uses it"])
  unless Spell.fold action == Spell.fold name do
    return (w, unclearVerdict [s!"the spell after grow: {name} uses {action}"])
  let target := if w.objects.contains card then card else resolveCard principal card
  let some obj := w.objects[target]? | return (w, unclearVerdict [s!"there is no card {card}"])
  let growArgument := Data.record [("name", .label name), ("reading", .label reading)]
  let growSpell := proposalSpell card "grow" growArgument
  unless carries (.variant "proposal" (proposalData target "grow" growArgument growSpell)) do
    return (w, unclearVerdict [s!"the object cannot carry a proposal of {target} grow"])
  let grown := Json.mkObj [("tag", toJson "proposal"), ("object", toJson target), ("method", toJson "grow"),
    ("argument", dataJson growArgument), ("spell", toJson growSpell)]
  let used := Data.record (fields.filter (·.name == "text") |>.map fun b => (b.name, Data.label b.value))
  let (w, use) := proposalVerdict w target self obj carries name used card (grown := [name])
  let item := fun (v : Json) => if (v.getObjValAs? String "tag").toOption == some "proposal" then v
    else Json.mkObj [("tag", toJson "unclear"), ("reasons", (v.getObjVal? "needs").toOption.getD (Json.arr #[]))]
  return (w, Json.mkObj [("tag", toJson "proposals"), ("items", Json.arr #[grown, item use])])

/-- What a reply says to the suspended object: the model's text (`raw`), hob's four answers. `none`;
    `ask: <question>`; `grow:` (`growVerdict`); else it is fitted as a spell against the offered forms
    (`spellVerdict`) and checked as a proposal (`proposalVerdict`: a method of the card, its argument
    conforming to the method's input, the suspended object's response type carrying it); prose that is
    none of these is `none` (silence). An object whose Response cannot carry an answer hears `unclear`.
    A failed call is `unclear {needs: ["model: <reason>"]}`. -/
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
  let some text := (reply.getObjValAs? String "raw").toOption | throw "a replied interpretation carries the model's text, raw"
  if let some r := staleBehaviour w (← parseBehaviours (← s.getObjVal? "roots")) then
    return (w, unclearVerdict [r.voiced.reason.getD ""])
  let some obj := w.objects[object]? | throw s!"unknown object {object}"
  -- What the answer must fit: the suspended activity's response type; the host's own reading of words a
  -- card heard runs the answer itself (`resumeHeard`), so any answer fits it.
  let (w, carries) ← if hostResumed s then pure (w, fun (_ : Data) => true) else do
    let (r2, st2) := ((compiledMethod obj suspendedMethod).run.run (scratchState w))
    let suspended ← match r2 with | .ok c => pure c | .error e => throw (abortText e)
    let some (_, responseType, _) := computationParts suspended.type | throw "the suspended method is not an activity"
    pure (w.withCachesOf st2.world, fun (d : Data) => d.conformsUnder suspended.bounds responseType)
  let offers ← decodeData Limits.dataDepth (← i.getObjVal? "offers")
  let forms := (listHeads [] offers).getD []
  let principal := ((s.getObjVal? "identity").toOption.bind (·.getObjValAs? String "principal" |>.toOption)).getD ""
  -- hob's four answers (docs/OVERHAUL.md §2; FOUNDATION §10): the spell meant, `grow: NAME
  -- "reading"` with the spell that uses it, `ask: <question>`, or `none`. hob states no fact and
  -- shows no card: there is no fifth.
  let said := text.trimAscii.toString
  if said.toLower == "none" then return (w, unclearVerdict ["not addressed"])
  if (said.take 4).toString.toLower == "ask:" then
    let q := ((said.drop 4).toString.trimAscii.toString)
    if !q.isEmpty && !(q.any (· == '\n')) then return (w, unclearVerdict [q])
  if (said.take 5).toString.toLower == "grow:" then
    return growVerdict w principal object carries said
  -- A plan (docs/HOST-HANDOFF.md 5.203): its acts, read in its one turn as they come (`resumeHeard`, `runPlan`); only
  -- the host's own reading runs one, for an object's Response carries a proposal, not a turn.
  if let some acts := Spell.plan text then
    if !hostResumed s then return (w, unclearVerdict ["a plan answers only the host's reading"])
    if acts.isEmpty || acts.length > Limits.planActs then
      return (w, unclearVerdict [s!"a plan carries 1 to {Limits.planActs} acts"])
    return (w, Json.mkObj [("tag", toJson "plan"), ("acts", toJson acts)])
  -- Several spells (MENU §2.2): each fitted and checked as one would be, answered in order as
  -- `proposals {items}`, at most `spellsPerReply`. One spell keeps the single verdict.
  let segments := Spell.segments text
  if segments.length > 1 then
    let offered := forms.filterMap OfferedForm.ofData
    let mut w := w
    let mut items : Array Json := #[]
    for segment in segments.take Limits.spellsPerReply do
      let item ← match spellVerdict offered segment with
        | some (.ok (card, action, argument)) =>
          let target := if w.objects.contains card then card else resolveCard principal card
          match w.objects[target]? with
          | none => pure (unclearVerdict [s!"there is no card {card}"])
          | some targetObj =>
            let (w', v) := proposalVerdict w target object targetObj carries action argument card
            w := w'
            pure v
        | some (.error needs) => pure (unclearVerdict needs)
        | none => pure (unclearVerdict ["not a spell"])
      items := items.push (if (item.getObjValAs? String "tag").toOption == some "proposal" then item
        else Json.mkObj [("tag", toJson "unclear"), ("reasons", (item.getObjVal? "needs").toOption.getD (Json.arr #[]))])
    return (w, Json.mkObj [("tag", toJson "proposals"), ("items", Json.arr items)])
  match spellVerdict (forms.filterMap OfferedForm.ofData) text with
  | some (.ok (card, action, argument)) =>
    -- The form names its card: the proposal is checked against that object, which may be
    -- another than the asking one (a directory offers its doors' forms).
    let target := if w.objects.contains card then card else resolveCard principal card
    let some targetObj := w.objects[target]? | return (w, unclearVerdict [s!"there is no card {card}"])
    return proposalVerdict w target object targetObj carries action argument card
  | some (.error needs) => return (w, unclearVerdict needs)
  -- Prose with no answer's prefix and no spell says nothing to the card: silence.
  | none => return (w, unclearVerdict ["not addressed"])

/-- The model failures the host retries rather than settles: the network or a rate limit. -/
def transientReasons : List String := ["transport", "rate"]

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
  -- A transient failure is the host's to retry (HOST-HANDOFF 5.107): journaled `attempted` with the
  -- clock the next may be asked at, the activity still waiting, until the last attempt, whose
  -- failure is the verdict.
  let tried := ((w.attempts[id]?).map (·.1)).getD 0
  let transient := (replied.getObjValAs? String "status").toOption == some "failed" &&
    transientReasons.contains ((replied.getObjValAs? String "reason").toOption.getD "")
  if transient && tried + 1 < Limits.interpretAttempts then
    let attempt := tried + 1
    let next := w.clock + min Limits.interpretBackoffMax (2 ^ (attempt - 1))
    let key := s!"{id}/attempt/{attempt}"
    let reason := (replied.getObjValAs? String "reason").toOption.getD ""
    let (w', entry) := push w (identityKey interpretationPrincipal key)
      [("identity", identityJson interpretationPrincipal key), ("roots", rootsJson []),
       ("turn", toJson (w.height + 1)), ("request", toJson digest),
       ("outcome", Json.mkObj [("tag", toJson "attempted"), ("id", toJson id), ("attempt", toJson attempt),
         ("reason", toJson reason), ("next", toJson next)])] []
    return (w', Json.mkObj [("status", toJson "retrying"), ("id", toJson id), ("attempt", toJson attempt),
      ("next", toJson next), ("receipt", slugged entry)])
  let (w, verdict) ← interpretVerdict w s replied
  let (w', entry) := push w (identityKey interpretationPrincipal id)
    [("identity", identityJson interpretationPrincipal id), ("roots", rootsJson []),
     ("turn", toJson (w.height + 1)), ("request", toJson digest),
     ("outcome", Json.mkObj [("tag", toJson "interpreted"), ("id", toJson id), ("reply", replied),
       ("verdict", verdict)])] []
  return (w', reply entry)

end Delvetalk.Host
