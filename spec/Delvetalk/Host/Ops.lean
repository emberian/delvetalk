/- The world kernel and its session ops. `commit` and friends are pure: the turn
   loop calls them with a proposal and gets the next World and a receipt. The IO
   layer at the bottom owns the journal file and nothing else. -/
import Delvetalk.Host.Store
import Delvetalk.Host.Journal
import Delvetalk.Host.Law
import Compiler.ObjectiveBendDataWire

namespace Delvetalk.Host
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Theory.ObjectiveBendTypes (DataBounds)
open Minidregg.Compiler.ObjectiveBendDataWire (dataJson decodeData)

/-! ## Wire forms -/

def natOf (j : Json) : Except String Nat :=
  match j with
  | .num _ => j.getNat?
  | .str s => match s.toNat? with
      | some n => pure n
      | none => throw "natural must be a decimal numeral"
  | _ => throw "natural must be a number or a decimal string"

def natField (j : Json) (key : String) : Except String Nat := do natOf (← j.getObjVal? key)

def boundedText (what : String) (cap : Nat) (s : String) : Except String String := do
  if s.isEmpty || s.utf8ByteSize > cap then throw s!"{what} must be 1..{cap} bytes"
  return s

/-- One field's edit, in the wire shape of `world/lib/Plan.obend`:
    `keep {}`, `set {value}`, `add {delta}`, `append {item}`, `amend {index, change}`. -/
inductive EditKind where
  | keep
  | set (value : Data)
  | add (delta : Nat)
  | append (item : Data)
  | amend (index : Nat) (change : Data)

structure Edit where
  field : String
  kind : EditKind

/-- A step is one `write` Plan: the edits record of one Edits value. An object's
    edits in a proposal are the steps in order. -/
abbrev Step := List Edit

def EditKind.data : EditKind → Data
  | .keep => .variant "keep" (.record [])
  | .set v => .variant "set" (.record [("value", v)])
  | .add n => .variant "add" (.record [("delta", .natural n)])
  | .append v => .variant "append" (.record [("item", v)])
  | .amend i v => .variant "amend" (.record [("index", .natural i), ("change", v)])

def Step.data (s : Step) : Data := .record (s.map fun e => (e.field, e.kind.data))

def parseKind : Data → Option EditKind
  | .variant "keep" _ => some .keep
  | .variant "set" (.record f) => (f.lookup "value").map .set
  | .variant "add" (.record f) => match f.lookup "delta" with
      | some (.natural n) => some (.add n)
      | _ => none
  | .variant "append" (.record f) => (f.lookup "item").map .append
  | .variant "amend" (.record f) => match f.lookup "index", f.lookup "change" with
      | some (.natural i), some c => some (.amend i c)
      | _, _ => none
  | _ => none

/-- An Edits record: one variant per field. -/
def parseStep : Data → Option Step
  | .record fields =>
    if (fields.map (·.1)).eraseDups.length != fields.length then none
    else fields.mapM fun (k, v) => (parseKind v).map (⟨k, ·⟩)
  | _ => none

def stepsJson (steps : List Step) : Json := Json.arr (steps.toArray.map fun s => dataJson s.data)

/-- `edits` on the wire: one Edits record, or an array of them applied in order. -/
def parseSteps (j : Json) : Except String (List Step) := do
  let raw := match j with
    | .arr items => items.toList
    | other => [other]
  if raw.length > Limits.maxEditsPerWrite then throw "too many edits"
  raw.mapM fun item => do
    let some step := parseStep (← decodeData Limits.dataDepth item) | throw "malformed edits record"
    if step.length > Limits.maxEditsPerWrite then throw "too many edits"
    return step

structure Proposal where
  principal : String
  intent : String
  roots : List (String × Nat)
  writes : List (String × List Step)
  turn : Nat := 0
  /-- Reprograms: object, package source, migration entry ("" for none). -/
  programs : List (String × (String × String)) := []
  /-- Amendments: object, new law text. -/
  laws : List (String × String) := []

/-- Writes plus an empty write for each object only reprogrammed or amended. -/
def Proposal.allWrites (p : Proposal) : List (String × List Step) :=
  let extra := (p.programs.map (·.1) ++ p.laws.map (·.1)).foldl
    (fun acc id => if p.writes.any (·.1 == id) || acc.any (·.1 == id) then acc else acc ++ [(id, [])]) []
  p.writes ++ extra

def rootsJson (roots : List (String × Nat)) : Json :=
  Json.arr (roots.toArray.map fun (o, v) => Json.mkObj [("object", toJson o), ("version", toJson v)])

def writesJson (writes : List (String × List Step)) : Json :=
  Json.arr (writes.toArray.map fun (o, es) => Json.mkObj
    [("object", toJson o), ("edits", stepsJson es)])

def parseRoots (j : Json) : Except String (List (String × Nat)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxRoots then throw "too many roots"
  let mut out : List (String × Nat) := []
  for r in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← r.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate root"
    out := out ++ [(object, ← natField r "version")]
  return out

def parseWrites (j : Json) : Except String (List (String × List Step)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxWrites then throw "too many writes"
  let mut out : List (String × List Step) := []
  for w in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← w.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate write"
    out := out ++ [(object, ← parseSteps (← w.getObjVal? "edits"))]
  return out

def parseProposal (j : Json) : Except String Proposal := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let turn := match j.getObjVal? "turn" with
    | .ok t => (natOf t).toOption.getD 0
    | .error _ => 0
  return { principal, intent, roots := ← parseRoots (← j.getObjVal? "roots"), writes := ← parseWrites (← j.getObjVal? "writes"), turn }

/-- Digest binding an identity to the request that first used it. -/
def Proposal.digest (p : Proposal) : String :=
  let programs := p.programs.map fun (id, (src, mig)) => Json.mkObj
    [("object", toJson id), ("source", toJson (Journal.bodyHash src)), ("migration", toJson mig)]
  let laws := p.laws.map fun (id, text) => Json.mkObj [("object", toJson id), ("law", toJson text)]
  Journal.bodyHash (Json.mkObj ([("roots", rootsJson p.roots), ("writes", writesJson p.allWrites),
    ("turn", toJson p.turn)] ++
    (if programs.isEmpty then [] else [("programs", Json.arr programs.toArray)]) ++
    (if laws.isEmpty then [] else [("laws", Json.arr laws.toArray)])))

/-! ## Judging -/

/-- The closed set of refusal classes. -/
def refusalClasses : List String :=
  ["staleRoot", "unreadWrite", "typeMismatch", "lawRefused", "unknownObject", "duplicateIdentity",
   "evaluation", "budgetExhausted", "programRefused"]

structure Refusal where
  cls : String
  clause : Option String := none
  object : Option String := none
  /-- Named reason for an `evaluation` refusal. -/
  reason : Option String := none

def replaceField (fields : List (String × Data)) (name : String) (v : Data) : List (String × Data) :=
  fields.map fun (k, old) => if k == name then (k, v) else (k, old)

/-- A `List<T>` on the wire is `nil {} | cons {head, tail}`. -/
partial def appendItem (item : Data) : Data → Option Data
  | .variant "nil" _ => some (.variant "cons" (.record [("head", item), ("tail", .variant "nil" (.record []))]))
  | .variant "cons" (.record f) => do
    let head ← f.lookup "head"
    let tail ← f.lookup "tail"
    some (.variant "cons" (.record [("head", head), ("tail", ← appendItem item tail)]))
  | _ => none

partial def amendItem (index : Nat) (change : Data) : Data → Option Data
  | .variant "cons" (.record f) => do
    let head ← f.lookup "head"
    let tail ← f.lookup "tail"
    if index == 0 then some (.variant "cons" (.record [("head", change), ("tail", tail)]))
    else some (.variant "cons" (.record [("head", head), ("tail", ← amendItem (index - 1) change tail)]))
  | _ => none

/-- All edits of a step read the state before the step. -/
def applyStep (fields : List (String × Data)) (step : Step) : Option (List (String × Data)) :=
  step.foldlM (init := fields) fun acc e =>
    match fields.lookup e.field with
    | none => none
    | some old =>
      let put := fun (v : Data) => some (replaceField acc e.field v)
      match e.kind with
      | .keep => some acc
      | .set v => put v
      | .add n => match old with
          | .natural m => put (.natural (m + n))
          | _ => none
      | .append item => (appendItem item old).bind put
      | .amend i c => (amendItem i c old).bind put

def applyEdits : Data → List Step → Option Data
  | .record fields, steps => (steps.foldlM applyStep fields).map .record
  | _, _ => none

/-! ## Law as state, and programs -/

/-- The state type is the type of the package's entry definition: a zero-argument
    `def initial() -> State` has type `State`, which must be a closed record of
    first-order data. The entry's own value is not used; the seed is explicit. -/
def stateTypeOk (assumptions : Minidregg.Theory.ObjectiveBendTyping.Assumptions)
    (ty : Minidregg.Theory.ObjectiveBendTypes.Ty) : Bool :=
  ty.isDataUnder assumptions.bounds assumptions.rigid Minidregg.Theory.ObjectiveBendTypes.Ty.dataFuel [] &&
    match ty with
    | .field .. | .emptyRow => true
    | _ => false

def tyVariables : Minidregg.Theory.ObjectiveBendTypes.Ty → List Nat
  | .variable i => [i]
  | .field _ m t => tyVariables m ++ tyVariables t
  | .variant r => tyVariables r
  | _ => []

/-- The bounds a type actually uses (transitively): what makes two state types
    the same, ignoring the rest of a package's bounds table. -/
def relevantBounds (bounds : DataBounds) (ty : Minidregg.Theory.ObjectiveBendTypes.Ty) : DataBounds :=
  let used := (List.range 8).foldl (fun used _ =>
    (used ++ used.flatMap fun i => ((bounds.lookup i).map tyVariables).getD []).eraseDups) (tyVariables ty).eraseDups
  bounds.filter fun (i, _) => used.contains i

def inputsKeyOf (inputs : Json) : String :=
  Journal.bodyHash (Json.mkObj (inputs.getObj?.toOption.map (·.toList.filter (·.1 != "entry")) |>.getD []))

def noAmendmentClause : String := "law has no amendment clause"

def renderLaw (law : Law) : String :=
  "\n".intercalate (law.map fun (name, clause) => s!"law {name}: {clause.render}")

/-- Law text: one `law NAME: EXPR` per line, as at the top of a package. -/
def parseLawText (text : String) : Except String Law := do
  if text.utf8ByteSize > Limits.maxLawBytes then throw "law text exceeds its byte capacity"
  let lines := (text.splitOn "\n").map String.trimAscii |>.filter (!·.isEmpty) |>.map (·.toString)
  if lines.length > Limits.maxLawClauses then throw "law has too many clauses"
  let law ← lines.mapM fun line => do
    let some rest := line.dropPrefix? "law " | throw s!"expected `law NAME: EXPR`, found `{line}`"
    match (rest.toString).splitOn ":" with
    | name :: more@(_ :: _) =>
      let name := name.trimAscii.toString
      unless Minidregg.Compiler.ObjectiveBendParse.isIdent name.toList do throw s!"invalid law name `{name}`"
      pure (name, ← Minidregg.Compiler.ObjectiveBendLaw.parse (":".intercalate more))
    | _ => throw s!"expected `law NAME: EXPR`, found `{line}`"
  Minidregg.Compiler.ObjectiveBendLaw.checkNames law
  return law

/-- The rule against a self-sealing law: a law is only accepted if it admits an
    amendment (the state unchanged) by the principal who proposes it. -/
def amendable (law : Law) (principal : String) (height turn : Nat) (pin : String) (state : Data) : Bool :=
  (Law.refusedBy law ⟨principal, principal, height, turn, pin⟩ (some state) state).isNone

def replaceSource (inputs : Json) (source : String) : Except String Json := do
  match inputs.getObjVal? "modules" with
  | .ok (.arr modules) =>
    let some last := modules.back? | throw "package has no modules"
    let name ← last.getObjValAs? String "name"
    return inputs.setObjVal! "modules" (.arr (modules.pop.push (Json.mkObj [("name", toJson name), ("source", toJson source)])))
  | _ => return inputs.setObjVal! "source" (toJson source)

/-- Compile a replacement for an object's entry module (its imports stay as
    sealed at creation). Failures are `(clause, message)`. -/
def prepareProgram (o : Object) (source migration : String) : Except (String × String) Program := do
  if source.utf8ByteSize > Limits.maxPackageBytes then
    throw ("packageBytes", s!"package source exceeds {Limits.maxPackageBytes} bytes")
  let inputs ← (replaceSource o.inputs source).mapError (("compile", ·))
  let (artifact, ty, _) ← (Package.compileKeepingLaws (inputs.setObjVal! "entry" (toJson "initial"))).mapError (("compile", ·))
  let decoded ← (do
    Minidregg.Theory.ObjectiveBendTyping.decodePacket (← artifact.getObjVal? "packet")).mapError (("compile", ·))
  let assumptions := decoded.source.assumptions
  unless stateTypeOk assumptions ty do
    throw ("compile", "initial() must return a closed record of first-order data")
  let pin ← (artifact.getObjValAs? String "packetSha256").mapError (("compile", ·))
  let same := ty == o.stateType && relevantBounds assumptions.bounds ty == relevantBounds o.bounds o.stateType
  let migrated : Option Compiled ← if migration.isEmpty then
      if same then pure none else throw ("stateType", "the state type differs and no migration names a conversion")
    else do
      unless Minidregg.Compiler.ObjectiveBendParse.isIdent migration.toList do throw ("migration", "invalid migration name")
      let (art, mty, _) ← (Package.compileKeepingLaws (inputs.setObjVal! "entry" (toJson migration))).mapError (("migration", ·))
      let packet ← (art.getObjVal? "packet").mapError (("migration", ·))
      let md ← (Minidregg.Theory.ObjectiveBendTyping.decodePacket packet).mapError (("migration", ·))
      match mty with
      | .arrow _ _ dom cod =>
        unless dom == o.stateType && cod == ty do
          throw ("migration", "the migration must have type OldState -> NewState")
      | _ => throw ("migration", "the migration must be a function OldState -> NewState")
      pure (some ⟨packet, mty, md.source.assumptions.bounds, md.source.assumptions.rigid⟩)
  return { inputs, pin, stateType := ty, bounds := assumptions.bounds, migration := migrated }

def programKey (o : Object) (source migration : String) : String :=
  o.inputsKey ++ "/" ++ Journal.bodyHash source ++ "/" ++ migration

def programFor (w : World) (o : Object) (source migration : String) : Except (String × String) Program :=
  match w.programs[programKey o source migration]? with
  | some p => pure p
  | none => prepareProgram o source migration

def cacheProgram (w : World) (o : Object) (source migration : String) (p : Program) : World :=
  if w.programs.size < Limits.maxPreparedPrograms then
    { w with programs := w.programs.insert (programKey o source migration) p }
  else w

structure Judged where
  updates : List (String × Object)
  reprograms : List Json
  amendments : List Json

/-- Roots current, writes read, results conform, laws admit. Returns the objects
    as they would be installed. `height` is the height the entry would take. -/
def judge (w : World) (height : Nat) (p : Proposal) : Except Refusal Judged := do
  let writes := p.allWrites
  for id in p.roots.map (·.1) ++ writes.map (·.1) do
    unless w.objects.contains id do throw { cls := "unknownObject", object := id }
  for (id, seen) in p.roots do
    if let some o := w.objects[id]? then
      if o.version != seen then throw { cls := "staleRoot", object := id }
  for (id, _) in writes do
    unless p.roots.any (·.1 == id) do throw { cls := "unreadWrite", object := id }
  let mut out : List (String × Object) := []
  let mut reprograms : List Json := []
  let mut amendments : List Json := []
  for (id, edits) in writes do
    let some o := w.objects[id]? | throw { cls := "unknownObject", object := id }
    let some written := applyEdits o.state edits | throw { cls := "typeMismatch", object := id }
    unless written.conformsUnder o.bounds o.stateType && (dataJson written).compress.utf8ByteSize ≤ Limits.maxStateBytes do
      throw { cls := "typeMismatch", object := id }
    -- A reprogram replaces code and, through its migration, the state's type.
    let mut next := o
    let mut state := written
    if let some (source, migration) := p.programs.lookup id then
      let refuse := fun (clause message : String) => Refusal.mk "programRefused" (some clause) (some id) (some message)
      let prog ← match programFor w o source migration with
        | .ok prog => pure prog
        | .error (clause, message) => throw (refuse clause message)
      if let some m := prog.migration then
        match Package.executeDataValues m.packet #[written] (Json.mkObj []) with
        | .ok (.finished value _ _ _) => state := value
        | .ok (.refused failure _) => throw (refuse "migration" s!"the migration was refused: {failure}")
        | .error e => throw (refuse "migration" e)
      unless state.conformsUnder prog.bounds prog.stateType && (dataJson state).compress.utf8ByteSize ≤ Limits.maxStateBytes do
        throw (refuse "migration" "the converted state does not conform to the new state type")
      next := { o with pin := prog.pin, inputs := prog.inputs, inputsKey := inputsKeyOf prog.inputs,
                       stateType := prog.stateType, bounds := prog.bounds }
      reprograms := reprograms ++ [Json.mkObj [("object", toJson id), ("oldPin", toJson o.pin),
        ("newPin", toJson prog.pin), ("source", toJson source), ("migration", toJson migration),
        ("result", dataJson state)]]
    -- The current law judges the whole write, under the pin the object will run.
    let facts : Law.Facts := ⟨p.principal, p.principal, height, p.turn, next.pin⟩
    if let some clause := Law.refusedBy o.law facts (some o.state) state then
      throw { cls := "lawRefused", clause, object := id }
    if let some text := p.laws.lookup id then
      let refuse := fun (clause : String) => Refusal.mk "lawRefused" (some clause) (some id) none
      let law ← match parseLawText text with
        | .ok law => pure law
        | .error _ => throw (refuse "law syntax")
      unless amendable law p.principal height p.turn next.pin state do throw (refuse noAmendmentClause)
      next := { next with law, lawText := text }
      amendments := amendments ++ [Json.mkObj [("object", toJson id), ("old", toJson o.lawText), ("new", toJson text)]]
    out := out ++ [(id, { next with version := o.version + 1, state })]
  return { updates := out, reprograms, amendments }

/-! ## Entries -/

def identityJson (principal intent : String) : Json :=
  Json.mkObj [("principal", toJson principal), ("intent", toJson intent)]

/-- Append a sealed entry to the world. -/
def record (w : World) (entry : Json) (key : String) (touch : List String) : World :=
  let hash := (entry.getObjValAs? String "hash").toOption.getD ""
  let index := w.entries.size
  let delivered := (entry.getObjVal? "delivery").toOption.bind fun d => (d.getObjValAs? String "id").toOption
  let identity := (entry.getObjVal? "identity").toOption.getD Json.null
  let sent := match (entry.getObjVal? "outcome").toOption.bind (fun o => (o.getObjValAs? String "tag").toOption),
      (entry.getObjVal? "sends").toOption.bind (·.getArr?.toOption) with
    | some "admitted", some sends => sends.map fun s => Json.mkObj
        ([("from", identity), ("principal", (identity.getObjVal? "principal").toOption.getD Json.null)] ++
          (s.getObj?.toOption.map (·.toList) |>.getD []))
    | _, _ => #[]
  { w with
    pending := (match delivered with
      | some id => w.pending.filter fun p => (p.getObjValAs? String "id").toOption != some id
      | none => w.pending) ++ sent
    height := w.height + 1, head := hash, entries := w.entries.push entry
    receipts := if w.receipts.contains key then w.receipts else w.receipts.insert key index
    touched := touch.foldl (fun t id => t.insert id ((t.getD id #[]).push index)) w.touched }

def push (w : World) (key : String) (fields : List (String × Json)) (touch : List String) :
    World × Json :=
  let entry := Journal.sealEntry (w.height + 1) w.head fields
  (record w entry key touch, entry)

def statusOf (entry : Json) : String :=
  match entry.getObjVal? "outcome" |>.bind (·.getObjValAs? String "tag") with
  | .ok tag => tag
  | .error _ => "unknown"

def reply (entry : Json) : Json :=
  Json.mkObj [("status", toJson (statusOf entry)), ("receipt", entry)]

def duplicate (principal intent : String) (entry : Json) : Json :=
  Json.mkObj [("status", toJson "refused"), ("class", toJson "duplicateIdentity"),
    ("identity", identityJson principal intent),
    ("original", entry.getObjVal? "hash" |>.toOption |>.getD Json.null)]

/-- Retry rule shared by every journaled op: the same identity and request returns
    the retained receipt without an entry; the same identity with another request
    is `duplicateIdentity` and is not journaled (the identity is already bound). -/
def retained (w : World) (principal intent digest : String) : Option Json :=
  match w.receipts[identityKey principal intent]? with
  | none => none
  | some index =>
    let entry := w.entries[index]!
    if (entry.getObjValAs? String "request").toOption == some digest then some (reply entry)
    else some (duplicate principal intent entry)

/-- The commit rule. Pure: the turn loop calls this with the roots it recorded and
    the writes it produced. Returns the next world and the reply (a receipt). -/
def commit (w : World) (p : Proposal) (extra : List (String × Json) := [])
    (forced : Option Refusal := none)
    (onAdmit : List (String × Object) → List (String × Json) := fun _ => []) : World × Json :=
  match retained w p.principal p.intent p.digest with
  | some r => (w, r)
  | none =>
    let key := identityKey p.principal p.intent
    let base := [("identity", identityJson p.principal p.intent), ("roots", rootsJson p.roots),
      ("turn", toJson p.turn), ("request", toJson p.digest)] ++ extra
    let verdict : Except Refusal Judged :=
      match forced with | some r => .error r | none => judge w (w.height + 1) p
    match verdict with
    | .error r =>
      let outcome := Json.mkObj ([("tag", toJson "refused"), ("class", toJson r.cls)] ++
        (r.clause.map fun c => [("clause", toJson c)]).getD [] ++
        (r.object.map fun o => [("object", toJson o)]).getD [] ++
        (r.reason.map fun o => [("reason", toJson o)]).getD [])
      let (w', entry) := push w key (base ++ [("outcome", outcome)]) []
      (w', reply entry)
    | .ok judged =>
      let updates := judged.updates
      let w := updates.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      let writes := Json.arr (updates.toArray.map fun (id, o) => Json.mkObj
        [("object", toJson id), ("version", toJson o.version),
         ("edits", stepsJson ((p.writes.lookup id).getD []))])
      let outcome := Json.mkObj ([("tag", toJson "admitted"), ("writes", writes)] ++
        (if judged.reprograms.isEmpty then [] else [("reprograms", Json.arr judged.reprograms.toArray)]) ++
        (if judged.amendments.isEmpty then [] else [("amendments", Json.arr judged.amendments.toArray)]))
      let (w', entry) := push w key (base ++ [("outcome", outcome)] ++ onAdmit updates) (updates.map (·.1))
      (w', reply entry)

/-! ## Creation -/

/-- Compile inputs from a request: either a previously compiled `artifact`
    (re-derived and compared) or `modules`/`source` + `entry` + `limits`. -/
def compileInputs (j : Json) : Except String Json := do
  match j.getObjVal? "artifact" with
  | .ok a => return Json.mkObj [("modules", ← a.getObjVal? "modules"), ("entry", ← a.getObjVal? "entry"),
      ("limits", ← a.getObjVal? "limits")]
  | .error _ =>
    let fields := ["modules", "source", "entry", "limits"].filterMap fun k =>
      (j.getObjVal? k).toOption.map (k, ·)
    return Json.mkObj fields

def parseRead (j : Option Json) : Except String ReadPolicy :=
  match j with
  | none => pure .«public»
  | some (.str "public") => pure .«public»
  | some obj => do
    let raw ← (← obj.getObjVal? "principals").getArr?
    if raw.size > Limits.maxReaders then throw "too many readers"
    let names ← raw.toList.mapM fun r => do boundedText "reader" Limits.maxPrincipalBytes (← r.getStr?)
    pure (.principals names)

def parseChain (j : Option Json) : Except String Ledger :=
  match j with
  | none => pure Ledger.start
  | some c => do
    let l : Ledger := ⟨← natField c "depth", ← natField c "work", ← natField c "storage"⟩
    if l.depth > Limits.maxDepth || l.work > Limits.chainWork || l.storage > Limits.chainStorage then
      throw "a chain ledger may be lowered at creation, never raised above the host limits"
    pure l

def buildObject (inputs seed : Json) (read : Option Json := none) (chain : Option Json := none)
    (creator : String := "") (height : Nat := 1) : Except String (Object × String) := do
  let (artifact, ty, laws) ← Package.compileKeepingLaws inputs
  let packet ← artifact.getObjVal? "packet"
  let decoded ← Minidregg.Theory.ObjectiveBendTyping.decodePacket packet
  let assumptions := decoded.source.assumptions
  unless stateTypeOk assumptions ty do
    throw "package entry type must be a closed record of first-order data (a zero-argument definition returning the state record)"
  let state ← decodeData Limits.dataDepth seed
  unless state.conformsUnder assumptions.bounds ty do throw "seed does not conform to the package state type"
  if (dataJson state).compress.utf8ByteSize > Limits.maxStateBytes then throw "seed exceeds state byte capacity"
  let pin ← artifact.getObjValAs? String "packetSha256"
  let sources ← artifact.getObjValAs? String "sourcesSha256"
  unless amendable laws creator height 0 pin state do throw noAmendmentClause
  let inputsKey := inputsKeyOf inputs
  return ({ pin, law := laws, lawText := renderLaw laws, version := 0, state, stateType := ty, bounds := assumptions.bounds,
            read := ← parseRead read, chain := ← parseChain chain, inputs, inputsKey }, sources)

def createOutcome (id : String) (o : Object) (sources : String) (artifact seed : Json) : Json :=
  Json.mkObj [("tag", toJson "created"), ("read", o.read.json), ("chain", o.chain.json), ("object", toJson id), ("pin", toJson o.pin),
    ("sourcesSha256", toJson sources), ("compile", artifact), ("seed", seed)]

def create (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let id ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let digest := Journal.bodyHash (Json.mkObj
    (j.getObj?.toOption.map (·.toList.filter (·.1 != "op")) |>.getD []))
  if let some r := retained w principal intent digest then return (w, r)
  if id == "self" then throw "object id self is reserved for the running object"
  if w.objects.contains id then throw s!"object {id} already exists"
  if w.objects.size ≥ Limits.maxObjects then throw "object capacity reached"
  let inputs ← compileInputs j
  let seed ← j.getObjVal? "seed"
  let (o, sources) ← buildObject inputs seed (j.getObjVal? "read").toOption (j.getObjVal? "chain").toOption principal (w.height + 1)
  -- An `artifact` claim is only a claim: the journal keeps the inputs, never the claim.
  let outcome := createOutcome id o sources inputs seed
  let (w', entry) := push { w with objects := w.objects.insert id o } (identityKey principal intent)
    [("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson digest), ("outcome", outcome)] [id]
  return (w', reply entry)

/-! ## Replay -/

/-- The id of the `ordinal`th send of the turn with this identity. -/
def deliveryId (principal intent : String) (ordinal : Nat) : String :=
  Journal.bodyHash (Json.arr #[toJson principal, toJson intent, toJson ordinal])

def ledgerOf (j : Json) : Except String Ledger := do
  return ⟨← natField j "depth", ← natField j "work", ← natField j "storage"⟩

/-- A delivery entry must consume exactly the pending delivery it names, under
    the sender's principal; a budget refusal must name a field that is zero. -/
def checkDelivery (w : World) (entry : Json) (principal intent : String) (outcome : Json) : Except String Unit := do
  let some d := (entry.getObjVal? "delivery").toOption | return ()
  let id ← d.getObjValAs? String "id"
  let some p := w.pending.find? fun p => (p.getObjValAs? String "id").toOption == some id
    | throw "delivery of an unknown or already delivered id"
  unless (p.getObjValAs? String "principal").toOption == some principal && intent == id do
    throw "delivery runs under another principal than its sender's"
  unless (d.getObjVal? "from").toOption == (p.getObjVal? "from").toOption do throw "delivery names another sender"
  if (outcome.getObjValAs? String "class").toOption == some "budgetExhausted" then
    let ledger ← ledgerOf (← p.getObjVal? "ledger")
    unless ledger.exhausted == (outcome.getObjValAs? String "reason").toOption do
      throw "budget refusal names a field that is not exhausted"
  else if (← ledgerOf (← p.getObjVal? "ledger")).exhausted.isSome then
    throw "a delivery with an exhausted ledger ran"

def checkSends (entry : Json) (principal intent : String) : Except String Unit := do
  let some sends := (entry.getObjVal? "sends").toOption | return ()
  let mut ordinal := 0
  for s in ← sends.getArr? do
    unless (s.getObjValAs? String "id").toOption == some (deliveryId principal intent ordinal) do
      throw "send id does not match its ordinal"
    discard <| s.getObjValAs? String "to"
    discard <| s.getObjValAs? String "method"
    discard <| decodeData Limits.dataDepth (← s.getObjVal? "argument")
    discard <| ledgerOf (← s.getObjVal? "ledger")
    ordinal := ordinal + 1

def replayEntry (w : World) (entry : Json) : Except String World := do
  let identity ← entry.getObjVal? "identity"
  let principal ← identity.getObjValAs? String "principal"
  let intent ← identity.getObjValAs? String "intent"
  let key := identityKey principal intent
  let outcome ← entry.getObjVal? "outcome"
  checkDelivery w entry principal intent outcome
  checkSends entry principal intent
  match ← outcome.getObjValAs? String "tag" with
  | "created" =>
    let id ← outcome.getObjValAs? String "object"
    if w.objects.contains id then throw s!"object {id} created twice"
    let (o, sources) ← buildObject (← outcome.getObjVal? "compile") (← outcome.getObjVal? "seed") (outcome.getObjVal? "read").toOption (outcome.getObjVal? "chain").toOption principal (w.height + 1)
    unless o.pin == (← outcome.getObjValAs? String "pin") && sources == (← outcome.getObjValAs? String "sourcesSha256") do
      throw s!"object {id} no longer compiles to its recorded pin"
    return record { w with objects := w.objects.insert id o } entry key [id]
  | "refused" =>
    let cls ← outcome.getObjValAs? String "class"
    unless refusalClasses.contains cls do throw s!"unknown refusal class {cls}"
    return record w entry key []
  | "admitted" =>
    let rawWrites ← (← outcome.getObjVal? "writes").getArr?
    let writes ← parseWrites (Json.arr rawWrites)
    let turn ← natField entry "turn"
    let recordedPrograms := (outcome.getObjVal? "reprograms").toOption.bind (·.getArr?.toOption) |>.getD #[]
    let recordedLaws := (outcome.getObjVal? "amendments").toOption.bind (·.getArr?.toOption) |>.getD #[]
    let programs ← recordedPrograms.toList.mapM fun r => do
      return (← r.getObjValAs? String "object", (← r.getObjValAs? String "source", ← r.getObjValAs? String "migration"))
    let laws ← recordedLaws.toList.mapM fun r => do
      return (← r.getObjValAs? String "object", ← r.getObjValAs? String "new")
    let p : Proposal := { principal, intent, roots := ← parseRoots (← entry.getObjVal? "roots"), writes, turn, programs, laws }
    unless (entry.getObjValAs? String "request").toOption == some p.digest do throw "request digest does not match"
    match judge w (w.height + 1) p with
    | .error r => throw s!"admitted entry would be refused ({r.cls})"
    | .ok judged =>
      unless judged.reprograms == recordedPrograms.toList && judged.amendments == recordedLaws.toList do
        throw "recorded reprograms or amendments do not replay"
      let updates := judged.updates
      for raw in rawWrites do
        let id ← raw.getObjValAs? String "object"
        let some (_, o) := updates.find? (·.1 == id) | throw "write missing"
        unless (← natField raw "version") == o.version do throw "write version out of sequence"
      let w := updates.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      return record w entry key (updates.map (·.1))
  | other => throw s!"unknown outcome {other}"

def replay (content : String) : Except String World := do
  let lines := content.splitOn "\n"
  let (complete, tail) := (lines.dropLast, lines.getLast?.getD "")
  if complete.length ≥ Limits.maxJournalEntries then throw "journal exceeds entry capacity"
  let mut w : World := {}
  for line in complete do
    let height := w.height + 1
    let entry ← match Json.parse line with
      | .ok e => pure e
      | .error _ => throw s!"journal broken at height {height}: unparsable line"
    Journal.verify height w.head entry
    match replayEntry w entry with
    | .ok w' => w := w'
    | .error e => throw s!"journal broken at height {height}: {e}"
  unless tail.isEmpty do throw s!"journal broken at height {w.height + 1}: unterminated final line"
  return w

/-! ## Reads -/

def view (w : World) (j : Json) : Except String Json := do
  let id ← j.getObjValAs? String "object"
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  match w.objects[id]? with
  | none => return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  | some o =>
    if !o.read.permits principal then
      return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
    return Json.mkObj [("status", toJson "viewed"), ("object", toJson id),
      ("version", toJson o.version), ("state", dataJson o.state), ("pin", toJson o.pin)]

def receipt (w : World) (j : Json) : Except String Json := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  match w.receipts[identityKey principal intent]? with
  | none => return Json.mkObj [("status", toJson "unknown")]
  | some index => return Json.mkObj [("status", toJson "receipt"), ("receipt", w.entries[index]!)]

def history (w : World) (j : Json) : Except String Json := do
  let id ← j.getObjValAs? String "object"
  let after := match j.getObjVal? "after" with
    | .ok a => (natOf a).toOption.getD 0
    | .error _ => 0
  let limit := min Limits.maxHistoryLimit (match j.getObjVal? "limit" with
    | .ok l => (natOf l).toOption.getD Limits.maxHistoryLimit
    | .error _ => Limits.maxHistoryLimit)
  if !w.objects.contains id then return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  let all := (w.touched.getD id #[]).filter fun index => index + 1 > after
  let page := all.extract 0 limit
  return Json.mkObj [("status", toJson "history"), ("object", toJson id),
    ("entries", Json.arr (page.map fun index => w.entries[index]!)),
    ("more", toJson (decide (all.size > limit)))]

end Delvetalk.Host
