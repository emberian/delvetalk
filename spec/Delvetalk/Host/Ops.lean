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

/-- A request's optional text field, refused by name when present and not text. -/
def optText (j : Json) (key : String) : Except String (Option String) :=
  match j.getObjVal? key with
  | .ok (.str s) => pure (some s)
  | .ok _ => throw s!"{key} must be text"
  | .error _ => pure none

/-- A request's optional natural field, refused by name when present and malformed. -/
def optNat (j : Json) (key : String) : Except String (Option Nat) :=
  match j.getObjVal? key with
  | .ok v => match natOf v with
    | .ok n => pure (some n)
    | .error _ => throw s!"{key} must be a natural number"
  | .error _ => pure none

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
  | remove (index : Nat)
  /-- The first item whose canonical bytes are `item`'s, replaced by `change` or removed. The
      label is the constructor the object used (`amendItem`/`removeItem` in Plan.obend, or
      `amend`/`remove` with an `item` payload), kept so the journal records what was written. -/
  | amendBy (label : String) (item change : Data)
  | removeBy (label : String) (item : Data)

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
  | .remove i => .variant "remove" (.record [("index", .natural i)])
  | .amendBy l item c => .variant l (.record [("item", item), ("change", c)])
  | .removeBy l item => .variant l (.record [("item", item)])

/-- Edits that commute with any other change of the same kinds: `keep`, `add`, `append`. A root
    whose every change in a proposal is made of them commits against the root as it is now. -/
def EditKind.commutes : EditKind → Bool
  | .keep | .add _ | .append _ => true
  | _ => false

def Step.data (s : Step) : Data := .record (s.map fun e => (e.field, e.kind.data))

def parseKind : Data → Option EditKind
  | .variant "keep" _ => some .keep
  | .variant "set" (.record f) => (f.lookup "value").map .set
  | .variant "add" (.record f) => match f.lookup "delta" with
      | some (.natural n) => some (.add n)
      | _ => none
  | .variant "append" (.record f) => (f.lookup "item").map .append
  | .variant "remove" (.record f) => match f.lookup "index", f.lookup "item" with
      | some (.natural i), none => some (.remove i)
      | none, some item => some (.removeBy "remove" item)
      | _, _ => none
  | .variant "amend" (.record f) => match f.lookup "index", f.lookup "item", f.lookup "change" with
      | some (.natural i), none, some c => some (.amend i c)
      | none, some item, some c => some (.amendBy "amend" item c)
      | _, _, _ => none
  | .variant "removeItem" (.record f) => (f.lookup "item").map (.removeBy "removeItem")
  | .variant "amendItem" (.record f) => match f.lookup "item", f.lookup "change" with
      | some item, some c => some (.amendBy "amendItem" item c)
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

/-- An object born in a turn: built from compile inputs and a final state. -/
structure CreateRec where
  object : Object
  sources : String
  /-- The final state, on the wire. -/
  seed : Json

/-- One change to an object, by the object whose method made it. `caller` is the
    object that called the running one (empty when the running object was the turn's
    own method, or for a direct proposal). `kind` is 0 for a write of state, 1 for a
    reprogram, 2 for an amendment; kinds 1 and 2 carry no edits. -/
structure Written where
  caller : String
  kind : Nat := 0
  edits : Step
  /-- The method whose run made the change ("" for an op), the law's `request.method`. -/
  method : String := ""
  /-- The grant the change was made under ("" for none): its grantor is the law's subject. -/
  via : String := ""
  /-- The argument of the method run that made the change: the Bend law's `request.argument`.
      Journaled (`arguments`) only for an object whose package declares a Bend law. -/
  argument : Data := .record []

structure Proposal where
  principal : String
  intent : String
  roots : List (String × Nat)
  writes : List (String × List Written)
  /-- Assigned by the host (`commit` sets it to the entry's height); never read from a client. -/
  turn : Nat := 0
  /-- Reprograms: object, package source, migration entry ("" for none). -/
  programs : List (String × (String × String)) := []
  /-- Objects whose reprogram is an extension over their current code (`mode: extend`). -/
  layered : List String := []
  /-- Amendments: object, new law text. -/
  laws : List (String × String) := []
  /-- Objects the turn required absent, and objects it creates (a subset). -/
  absent : List String := []
  creates : List (String × CreateRec) := []
  /-- Grants the turn makes and grant ids it revokes; they take effect with the commit. -/
  grants : List Grant := []
  revokes : List String := []
  /-- Uses the turn spends of limited grants: grant id and count. -/
  spent : List (String × Nat) := []

/-- Writes, plus a direct (caller-less) change of the proper kind for each reprogram or
    amendment that no write of the proposal already names. -/
def Proposal.allWrites (p : Proposal) : List (String × List Written) :=
  let wanted := p.programs.map (fun x => (x.1, 1)) ++ p.laws.map (fun x => (x.1, 2))
  wanted.foldl (fun acc (id, kind) =>
    let have_ := ((acc.lookup id).getD []).any (·.kind == kind)
    if have_ then acc
    else if acc.any (·.1 == id) then
      acc.map fun (i, ws) => if i == id then (i, ws ++ [{ caller := "", kind, edits := [] }]) else (i, ws)
    else acc ++ [(id, [{ caller := "", kind, edits := [] }])]) p.writes

def rootsJson (roots : List (String × Nat)) : Json :=
  Json.arr (roots.toArray.map fun (o, v) => Json.mkObj [("object", toJson o), ("version", toJson v)])

/-- The fields recording who made each change: parallel arrays of steps, callers, kinds. -/
def writtenFields (ws : List Written) : List (String × Json) :=
  [("edits", stepsJson (ws.map (·.edits))), ("callers", toJson (ws.map (·.caller))),
   ("kinds", toJson (ws.map (·.kind)))] ++
  (if ws.all (·.method.isEmpty) then [] else [("methods", toJson (ws.map (·.method)))]) ++
  (if ws.all (·.via.isEmpty) then [] else [("vias", toJson (ws.map (·.via)))]) ++
  (if ws.all (fun w => match w.argument with | .record [] => true | _ => false) then []
   else [("arguments", Json.arr (ws.toArray.map (dataJson ·.argument)))])

def writesJson (writes : List (String × List Written)) : Json :=
  Json.arr (writes.toArray.map fun (o, ws) => Json.mkObj (("object", toJson o) :: writtenFields ws))

def parseRoots (j : Json) : Except String (List (String × Nat)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxRoots then throw "too many roots"
  let mut out : List (String × Nat) := []
  for r in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← r.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate root"
    out := out ++ [(object, ← natField r "version")]
  return out

/-- Writes as a client sends them: direct, so every step has the empty caller. A client
    cannot name a caller. -/
def parseWrites (j : Json) : Except String (List (String × List Written)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxWrites then throw "too many writes"
  let mut out : List (String × List Written) := []
  for w in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← w.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate write"
    out := out ++ [(object, (← parseSteps (← w.getObjVal? "edits")).map fun step => { caller := "", edits := step })]
  return out

/-- Writes as the journal records them: steps with their callers and kinds. -/
def parseRecordedWrites (j : Json) : Except String (List (String × List Written)) := do
  let raw ← j.getArr?
  if raw.size > Limits.maxWrites then throw "too many writes"
  let mut out : List (String × List Written) := []
  for w in raw do
    let object ← boundedText "object id" Limits.maxObjectIdBytes (← w.getObjValAs? String "object")
    if out.any (·.1 == object) then throw "duplicate write"
    let steps ← parseSteps (← w.getObjVal? "edits")
    let callers ← (← (← w.getObjVal? "callers").getArr?).toList.mapM (·.getStr?)
    let kinds ← (← (← w.getObjVal? "kinds").getArr?).toList.mapM natOf
    let optional := fun (key : String) => do
      match w.getObjVal? key with
      | .ok a => (← a.getArr?).toList.mapM (·.getStr?)
      | .error _ => pure (steps.map fun _ => "")
    let methods ← optional "methods"
    let vias ← optional "vias"
    let arguments ← match w.getObjVal? "arguments" with
      | .ok a => (← a.getArr?).toList.mapM (decodeData Limits.dataDepth)
      | .error _ => pure (steps.map fun _ => Data.record [])
    unless callers.length == steps.length && kinds.length == steps.length && methods.length == steps.length &&
        vias.length == steps.length && arguments.length == steps.length do
      throw "a write's callers, kinds, methods, vias and arguments must match its edits"
    out := out ++ [(object, (steps.zip (callers.zip (kinds.zip (methods.zip (vias.zip arguments))))).map
      fun (step, caller, kind, method, via, argument) => { caller, kind, edits := step, method, via, argument })]
  return out

/-- A direct proposal. A write must name an object among its roots; `turn` is the
    host's to assign, so a request that carries one is refused. -/
def parseProposal (j : Json) : Except String Proposal := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  if (j.getObjVal? "turn").toOption.isSome then throw "turn is assigned by the host and cannot be supplied"
  let roots ← parseRoots (← j.getObjVal? "roots")
  let writes ← parseWrites (← j.getObjVal? "writes")
  for (id, _) in writes do
    unless roots.any (·.1 == id) do throw s!"write names {id}, which is not among the roots"
  return { principal, intent, roots, writes }

def spentJson (spent : List (String × Nat)) : Json :=
  Json.arr (spent.toArray.map fun (id, n) => Json.mkObj [("id", toJson id), ("uses", toJson n)])

def parseSpent (j : Option Json) : Except String (List (String × Nat)) := do
  let some raw := j | return []
  (← raw.getArr?).toList.mapM fun x => do return (← x.getObjValAs? String "id", ← natField x "uses")

/-- Digest binding an identity to the request that first used it. -/
def Proposal.digest (p : Proposal) : String :=
  let programs := p.programs.map fun (id, (src, mig)) => Json.mkObj
    [("object", toJson id), ("source", toJson (Journal.bodyHash src)), ("migration", toJson mig)]
  let laws := p.laws.map fun (id, text) => Json.mkObj [("object", toJson id), ("law", toJson text)]
  Journal.bodyHash (Json.mkObj ([("roots", rootsJson p.roots), ("writes", writesJson p.allWrites)] ++
    (if programs.isEmpty then [] else [("programs", Json.arr programs.toArray)]) ++
    (if p.layered.isEmpty then [] else [("extends", toJson p.layered)]) ++
    (if laws.isEmpty then [] else [("laws", Json.arr laws.toArray)]) ++
    (if p.absent.isEmpty then [] else [("absent", toJson p.absent)]) ++
    (if p.creates.isEmpty then [] else [("creates", Json.arr (p.creates.toArray.map fun (id, c) => Json.mkObj
      [("object", toJson id), ("pin", toJson c.object.pin), ("seed", toJson (Journal.bodyHash c.seed.compress)),
       ("law", toJson c.object.lawText)]))]) ++
    (if p.grants.isEmpty then [] else [("grants", Json.arr (p.grants.toArray.map Grant.json))]) ++
    (if p.revokes.isEmpty then [] else [("revokes", toJson p.revokes)]) ++
    (if p.spent.isEmpty then [] else [("spent", spentJson p.spent)])))

/-! ## Judging -/

/-- The closed set of refusal classes. -/
def refusalClasses : List String :=
  ["staleRoot", "typeMismatch", "capacity", "outOfRange", "absentItem", "lawRefused", "unknownObject",
   "duplicateIdentity", "evaluation", "budget", "budgetExhausted", "programRefused", "requiredAbsence"]

structure Refusal where
  cls : String
  clause : Option String := none
  object : Option String := none
  /-- Named reason for an `evaluation` refusal. -/
  reason : Option String := none

def replaceField (fields : List (String × Data)) (name : String) (v : Data) : List (String × Data) :=
  fields.map fun (k, old) => if k == name then (k, v) else (k, old)

/-- Why an edit does not apply: `typeMismatch` (the field or value is not of the kind the
    edit needs) or `outOfRange` (an index at or past the end of the list). -/
abbrev EditResult := Except String

/-- A `List<T>` on the wire is `nil {} | cons {head, tail}`. -/
partial def appendItem (item : Data) : Data → EditResult Data
  | .variant "nil" _ => pure (.variant "cons" (.record [("head", item), ("tail", .variant "nil" (.record []))]))
  | .variant "cons" (.record f) => do
    let some head := f.lookup "head" | throw "typeMismatch"
    let some tail := f.lookup "tail" | throw "typeMismatch"
    pure (.variant "cons" (.record [("head", head), ("tail", ← appendItem item tail)]))
  | _ => throw "typeMismatch"

partial def amendItem (index : Nat) (change : Data) : Data → EditResult Data
  | .variant "nil" _ => throw "outOfRange"
  | .variant "cons" (.record f) => do
    let some head := f.lookup "head" | throw "typeMismatch"
    let some tail := f.lookup "tail" | throw "typeMismatch"
    if index == 0 then pure (.variant "cons" (.record [("head", change), ("tail", tail)]))
    else pure (.variant "cons" (.record [("head", head), ("tail", ← amendItem (index - 1) change tail)]))
  | _ => throw "typeMismatch"

/-- Delete the element at `index`. -/
partial def removeItem (index : Nat) : Data → EditResult Data
  | .variant "nil" _ => throw "outOfRange"
  | .variant "cons" (.record f) => do
    let some head := f.lookup "head" | throw "typeMismatch"
    let some tail := f.lookup "tail" | throw "typeMismatch"
    if index == 0 then pure tail
    else pure (.variant "cons" (.record [("head", head), ("tail", ← removeItem (index - 1) tail)]))
  | _ => throw "typeMismatch"

/-- Replace (`some change`) or remove (`none`) the first item whose canonical bytes are `item`'s;
    `absentItem` when no item is. -/
partial def editByItem (item : Data) (change : Option Data) : Data → EditResult Data
  | .variant "nil" _ => throw "absentItem"
  | .variant "cons" (.record f) => do
    let some head := f.lookup "head" | throw "typeMismatch"
    let some tail := f.lookup "tail" | throw "typeMismatch"
    if Delvetalk.Canonical.encode head == Delvetalk.Canonical.encode item then
      match change with
      | some c => pure (.variant "cons" (.record [("head", c), ("tail", tail)]))
      | none => pure tail
    else pure (.variant "cons" (.record [("head", head), ("tail", ← editByItem item change tail)]))
  | _ => throw "typeMismatch"

/-- All edits of a step read the state before the step. -/
def applyStep (fields : List (String × Data)) (step : Step) : EditResult (List (String × Data)) :=
  step.foldlM (init := fields) fun acc e => do
    let some old := fields.lookup e.field | throw "typeMismatch"
    let put := fun (v : Data) => pure (replaceField acc e.field v)
    match e.kind with
    | .keep => pure acc
    | .set v => put v
    | .add n => match old with
        | .natural m => put (.natural (m + n))
        | _ => throw "typeMismatch"
    | .append item => put (← appendItem item old)
    | .amend i c => put (← amendItem i c old)
    | .remove i => put (← removeItem i old)
    | .amendBy _ item c => put (← editByItem item (some c) old)
    | .removeBy _ item => put (← editByItem item none old)

def applyEdits : Data → List Step → EditResult Data
  | .record fields, steps => (steps.foldlM applyStep fields).map .record
  | _, _ => throw "typeMismatch"

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
def relevantBounds (bounds : DataBounds) (ty : Minidregg.Theory.ObjectiveBendTypes.Ty) : Except String DataBounds := do
  -- The closure of the variables `ty` reaches through the table; each round adds one or stops,
  -- so `bounds.length + 1` rounds reach the fixpoint. Not reaching it refuses by name.
  let mut used := (tyVariables ty).eraseDups
  let mut closed := false
  for _ in [0:bounds.length + 2] do
    let next := (used ++ used.flatMap fun i => ((bounds.lookup i).map tyVariables).getD []).eraseDups
    if next.length == used.length then
      closed := true
      break
    used := next
  unless closed do throw "type too deep to compare"
  return bounds.filter fun (i, _) => used.contains i

def inputsKeyOf (inputs : Json) : String :=
  Journal.bodyHash (Json.mkObj (inputs.getObj?.toOption.map (·.toList.filter (·.1 != "entry")) |>.getD []))

/-! ## The standard library

A world opened with a library seals `world/lib/**/*.obend` as a closure: module name
(file name without `.obend`), source, dependency order. An object's compile inputs
name it by `"library": pin`; the modules the package imports (transitively) are
prepended to the package's own modules when it is compiled, so a package can
`import ./Plan.obend as Plans` without carrying the source. -/

/-- The module names a source imports (`import ./Name.obend as X` lines). -/
def importsOf (source : String) : List String :=
  (source.splitOn "\n").filterMap fun line =>
    (line.dropPrefix? "import ./").bind fun rest => ((rest.toString.splitOn ".obend").head?)

def libraryDigest (modules : List (String × String)) : String :=
  Journal.bodyHash (Json.arr (modules.toArray.map fun (n, src) =>
    Json.mkObj [("name", toJson n), ("source", toJson src)]))

def modulesJson (modules : List (String × String)) : Json :=
  Json.arr (modules.toArray.map fun (n, src) => Json.mkObj [("name", toJson n), ("source", toJson src)])

def parseModules (j : Json) : Except String (List (String × String)) := do
  (← j.getArr?).toList.mapM fun m => do return (← m.getObjValAs? String "name", ← m.getObjValAs? String "source")

/-- Seal files `(name, source)` into a library: names unique identifiers, every import
    present, no cycle; order is by rounds of ready modules, each in name order. -/
def sealLibrary (files : List (String × String)) : Except String Library := do
  if files.length > Limits.maxLibraryModules then
    throw s!"library has {files.length} modules, more than {Limits.maxLibraryModules}"
  let bytes := files.foldl (fun n (name, src) => n + name.utf8ByteSize + src.utf8ByteSize) 0
  if bytes > Limits.maxLibraryBytes then throw s!"library exceeds {Limits.maxLibraryBytes} bytes"
  let names := files.map (·.1)
  for n in names do
    unless Minidregg.Compiler.ObjectiveBendParse.isIdent n.toList do throw s!"library module name `{n}` is not an identifier"
  if names.eraseDups.length != names.length then throw "library has two modules of one name"
  for (n, src) in files do
    for i in importsOf src do
      unless names.contains i do throw s!"library module {n} imports {i}, which is not in the library"
  let sorted := (files.toArray.qsort fun a b => a.1 < b.1).toList
  let mut placed : List (String × String) := []
  let mut rest := sorted
  for _ in [0:files.length + 1] do
    if rest.isEmpty then break
    let ready := rest.filter fun (_, src) => (importsOf src).all fun i => placed.any (·.1 == i)
    if ready.isEmpty then throw "library modules import each other in a cycle"
    placed := placed ++ ready
    rest := rest.filter fun (n, _) => !ready.any (·.1 == n)
  unless rest.isEmpty do throw "library modules import each other in a cycle"
  return { pin := libraryDigest placed, modules := placed }

/-- The library modules a set of module sources needs, transitively, in library order. -/
def libraryClosure (lib : Library) (sources : List String) : List (String × String) :=
  let wanted := (List.range (lib.modules.length + 1)).foldl (fun need _ =>
    (need ++ need.flatMap fun n => ((lib.modules.lookup n).map importsOf).getD []).eraseDups)
    (sources.flatMap importsOf).eraseDups
  lib.modules.filter fun (n, _) => wanted.contains n

/-- Compile inputs with the library modules prepended; inputs without `"library"` are as given.
    The result is for the compiler only; the object keeps the inputs it was given. -/
def resolveInputs (w : World) (inputs : Json) : Except String Json := do
  let some pin := (inputs.getObjValAs? String "library").toOption | return inputs
  let some lib := w.libraries[pin]? | throw s!"unknown library pin {pin}"
  let own ← match inputs.getObjVal? "modules" with
    | .ok m => parseModules m
    | .error _ => pure [("Main", ← inputs.getObjValAs? String "source")]
  for (n, src) in own do
    if let some libSrc := lib.modules.lookup n then
      unless libSrc == src do throw s!"module {n} shadows the library module of that name"
  let own := own.filter fun (n, _) => (lib.modules.lookup n).isNone
  let modules := libraryClosure lib (own.map (·.2)) ++ own
  let fields := (inputs.getObj?.toOption.map (·.toList) |>.getD []).filter fun (k, _) =>
    k != "library" && k != "source" && k != "modules"
  return Json.mkObj (("modules", modulesJson modules) :: fields)

/-- Name the world's current library in compile inputs (a package of one `source` becomes
    the module `Main`). Without a library the inputs are as given. -/
def attachLibrary (w : World) (inputs : Json) : Except String Json := do
  let some lib := w.library | return inputs
  let own ← match inputs.getObjVal? "modules" with
    | .ok m => parseModules m
    | .error _ => pure [("Main", ← inputs.getObjValAs? String "source")]
  let own := own.filter fun (n, src) => lib.modules.lookup n != some src
  let fields := (inputs.getObj?.toOption.map (·.toList) |>.getD []).filter fun (k, _) =>
    k != "source" && k != "modules" && k != "library"
  let attached := Json.mkObj (("modules", modulesJson own) :: ("library", toJson lib.pin) :: fields)
  discard <| resolveInputs w attached
  return attached

/-- The source of an object's entry module: the last of its own modules. -/
def entrySource (o : Object) : String :=
  match o.inputs.getObjVal? "modules" with
  | .ok (.arr modules) => ((modules.back?.bind fun m => (m.getObjValAs? String "source").toOption)).getD ""
  | _ => (o.inputs.getObjValAs? String "source").toOption.getD ""

/-- Dry-run compile of `source` as an entry module over the library: the diagnostics as
    `"<module>:<line>: <stage>: <message>"`, none when it is clean. Nothing is installed. -/
def checkSource (w : World) (source : String) : List String :=
  if source.utf8ByteSize > Limits.maxPackageBytes then
    [s!"Checked:0: package-request: package source exceeds {Limits.maxPackageBytes} bytes"]
  else
    -- The front end elaborates every declaration of every module whatever entry is selected,
    -- so the entry only has to exist: `initial` when declared, else the first `def`, else a
    -- definition appended after the source (which moves no line of it).
    let defs := (source.splitOn "\n").filterMap fun line =>
      (line.dropPrefix? "def ").map fun rest => (rest.toString.takeWhile fun c => c.isAlphanum || c == '_').toString
    let (checked, entry) :=
      if defs.contains "initial" then (source, "initial")
      else match defs.find? (!·.isEmpty) with
        | some name => (source, name)
        | none => (source ++ "\ndef checkedEntry() -> Nat:\n  0n\n", "checkedEntry")
    let modules := (match w.library with
      | some lib => libraryClosure lib [checked]
      | none => []) ++ [("Checked", checked)]
    match Package.checkPackage modules entry with
    | .ok _ => []
    | .error d =>
      -- A package that declares laws compiles; only the pure profile has no adapter for them.
      if (d.message.splitOn "package laws require").length > 1 then []
      else
        let at_ := s!"{d.sourceModule.getD "Checked"}:{(d.span.map (·.line)).getD 0}"
        -- The kernel's dialect hint, when it has one, is the next line at the same place.
        [s!"{at_}: {d.stage}: {d.message}"] ++ (d.hint.map fun h => [s!"{at_}: hint: {h}"]).getD []

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
def amendable (law : Law) (principal caller : String) (height turn : Nat) (pin : String) (state : Data) : Bool :=
  (Law.refusedBy law ⟨principal, caller, height, turn, pin, 2, ""⟩ (some state) state).isNone

def replaceSource (inputs : Json) (source : String) : Except String Json := do
  match inputs.getObjVal? "modules" with
  | .ok (.arr modules) =>
    let some last := modules.back? | throw "package has no modules"
    let name ← last.getObjValAs? String "name"
    return inputs.setObjVal! "modules" (.arr (modules.pop.push (Json.mkObj [("name", toJson name), ("source", toJson source)])))
  | _ => return inputs.setObjVal! "source" (toJson source)

/-! ## Extension

`reprogram {mode: extend}` (Plan `extend`) appends the offered source as a new module, a layer,
over the object's current modules. The layer sees the current entry module as `Super` (the host
adds `import ./<entry>.obend as Super` after its `edition` line when it lacks it, so its line
numbers in diagnostics are one more than the author's), defines what it overrides, and every
method it does not define is the code below it: `delegate` drops layers until the top one
defines the entry. `inputs.layers` counts them. -/

/-- The definitions a source declares at the top level (`def NAME`). -/
def definedNames (source : String) : List String :=
  (source.splitOn "\n").filterMap fun line =>
    (line.dropPrefix? "def ").map fun rest => (rest.toString.takeWhile fun c => c.isAlphanum || c == '_').toString

def layersOf (inputs : Json) : Nat := (inputs.getObjValAs? Nat "layers").toOption.getD 0

/-- The compile inputs whose entry module defines `name`: the layers that do not are dropped. -/
def delegate (inputs : Json) (name : String) : Json := Id.run do
  let mut inputs := inputs
  for _ in [0:layersOf inputs] do
    let some (.arr ms) := (inputs.getObjVal? "modules").toOption | break
    let some top := ms.back? | break
    if (definedNames ((top.getObjValAs? String "source").toOption.getD "")).contains name then break
    inputs := (inputs.setObjVal! "modules" (.arr ms.pop)).setObjVal! "layers" (toJson (layersOf inputs - 1))
  return inputs

/-- The inputs with `source` as one more layer over the current entry module. -/
def extendInputs (inputs : Json) (source : String) : Except String Json := do
  let modules ← match inputs.getObjVal? "modules" with
    | .ok (.arr ms) => pure ms
    | _ => pure #[Json.mkObj [("name", toJson "Main"), ("source", toJson (← inputs.getObjValAs? String "source"))]]
  let some top := modules.back? | throw "package has no modules"
  let below ← top.getObjValAs? String "name"
  let n := layersOf inputs + 1
  let name := s!"Layer{n}"
  if modules.any fun m => (m.getObjValAs? String "name").toOption == some name then
    throw s!"the package already has a module named {name}"
  let importLine := s!"import ./{below}.obend as Super"
  let lines := source.splitOn "\n"
  let withSuper := if lines.any (·.trimAscii.toString == importLine) then source else
    match lines with
    | first :: rest => "\n".intercalate (first :: importLine :: rest)
    | [] => importLine
  let fields := (inputs.getObj?.toOption.map (·.toList) |>.getD []).filter fun (k, _) => k != "source" && k != "modules" && k != "layers"
  return Json.mkObj ([("modules", .arr (modules.push (Json.mkObj [("name", toJson name), ("source", toJson withSuper)]))),
    ("layers", toJson n)] ++ fields)

/-- The method table and the Bend-law shape an artifact records. -/
def artifactShape (artifact : Json) : Json × Bool × Bool :=
  let law := (artifact.getObjVal? "law").toOption.getD Json.null
  ((artifact.getObjVal? "methods").toOption.getD (Json.arr #[]),
   (law.getObjValAs? Bool "present").toOption.getD false, (law.getObjValAs? Bool "reads").toOption.getD false)

/-- Compile a replacement for an object's entry module (its imports stay as
    sealed at creation). Failures are `(clause, message)`. -/
def prepareProgram (w : World) (o : Object) (source migration : String) (extend : Bool := false) :
    Except (String × String) Program := do
  if source.utf8ByteSize > Limits.maxPackageBytes then
    throw ("packageBytes", s!"package source exceeds {Limits.maxPackageBytes} bytes")
  let replaced ← (if extend then extendInputs o.inputs source else replaceSource o.inputs source).mapError (("compile", ·))
  -- A reprogram is compiled against the library the world has now.
  let inputs ← (match w.library with
    | some lib => if (replaced.getObjVal? "library").toOption.isSome then
        pure (replaced.setObjVal! "library" (toJson lib.pin)) else pure replaced
    | none => pure replaced)
  let resolved := fun (entry : String) => (resolveInputs w ((delegate inputs entry).setObjVal! "entry" (toJson entry))).mapError (("compile", ·))
  let (artifact, ty, _) ← (Package.compileKeepingLaws (← resolved "initial")).mapError (("compile", ·))
  let decoded ← (do
    Minidregg.Theory.ObjectiveBendTyping.decodePacket (← artifact.getObjVal? "packet")).mapError (("compile", ·))
  let assumptions := decoded.source.assumptions
  unless stateTypeOk assumptions ty do
    throw ("compile", "initial() must return a closed record of first-order data")
  let compiledPin ← (artifact.getObjValAs? String "packetSha256").mapError (("compile", ·))
  -- An extension's code is its layer over the code it extends, whatever `initial` it reaches.
  let pin := if extend then Journal.bodyHash (Json.arr #[toJson "extend", toJson o.pin, toJson (Journal.bodyHash (toJson source))])
    else compiledPin
  let same := ty == o.stateType &&
    (← (relevantBounds assumptions.bounds ty).mapError (("stateType", ·))) ==
      (← (relevantBounds o.bounds o.stateType).mapError (("stateType", ·)))
  let migrated : Option Compiled ← if migration.isEmpty then
      if same then pure none else throw ("stateType", "the state type differs and no migration names a conversion")
    else do
      unless Minidregg.Compiler.ObjectiveBendParse.isIdent migration.toList do throw ("migration", "invalid migration name")
      let (art, mty, _) ← (Package.compileKeepingLaws (← resolved migration)).mapError (("migration", ·))
      let packet ← (art.getObjVal? "packet").mapError (("migration", ·))
      let md ← (Minidregg.Theory.ObjectiveBendTyping.decodePacket packet).mapError (("migration", ·))
      match mty with
      | .arrow _ _ dom cod =>
        unless dom == o.stateType && cod == ty do
          throw ("migration", "the migration must have type OldState -> NewState")
      | _ => throw ("migration", "the migration must be a function OldState -> NewState")
      pure (some ⟨packet, mty, md.source.assumptions.bounds, md.source.assumptions.rigid, none⟩)
  let (methods, predicate, predicateReads) ← if !extend then pure (artifactShape artifact) else do
    -- The layer's own table (compiled with one of its definitions as the entry), then every
    -- method below it that the layer does not override; the law shape is the layer's if it
    -- declares a law, else the code's below.
    let own := definedNames source
    let some first := own.head? | throw ("compile", "an extension defines nothing")
    let (layerArtifact, _, _) ← (Package.compileKeepingLaws (← (resolveInputs w (inputs.setObjVal! "entry" (toJson first))).mapError (("compile", ·)))).mapError (("compile", ·))
    let (mine, lawHere, readsHere) := artifactShape layerArtifact
    let rows := (mine.getArr?.toOption.getD #[]) ++ ((o.methods.getArr?.toOption.getD #[]).filter fun m =>
      !own.contains ((m.getObjValAs? String "name").toOption.getD ""))
    pure (Json.arr rows, lawHere || o.predicate, if lawHere then readsHere else o.predicateReads)
  return { inputs, pin, stateType := ty, bounds := assumptions.bounds, migration := migrated,
           methods, predicate, predicateReads }

def programKey (o : Object) (source migration : String) (extend : Bool := false) : String :=
  o.inputsKey ++ "/" ++ Journal.bodyHash source ++ "/" ++ migration ++ (if extend then "/extend" else "")

def programFor (w : World) (o : Object) (source migration : String) (extend : Bool := false) : Except (String × String) Program :=
  match w.programs[programKey o source migration extend]? with
  | some p => pure p
  | none => prepareProgram w o source migration extend

def cacheProgram (w : World) (o : Object) (source migration : String) (p : Program) (extend : Bool := false) : World :=
  if w.programs.size < Limits.maxPreparedPrograms then
    { w with programs := w.programs.insert (programKey o source migration extend) p }
  else w

/-! ## Sources by CID

The journal carries each source module once: the first entry whose compile inputs need a
source carries it in its `sources [{cid, source}]` field, and compile inputs in every entry
name it as `{name, cid}` (or `sourceCid`). Objects keep the full inputs in memory. -/

def sourceCid (source : String) : String := Journal.bodyHash (toJson source)

/-- The sources an object's compile inputs carry. -/
def inputSources (inputs : Json) : List String :=
  let modules := match inputs.getObjVal? "modules" with
    | .ok (.arr ms) => ms.toList.filterMap fun m => (m.getObjValAs? String "source").toOption
    | _ => []
  modules ++ ((inputs.getObjValAs? String "source").toOption.map ([·])).getD []

/-- Compile inputs as journaled: every source replaced by its CID. -/
def compactInputs (inputs : Json) : Json :=
  let inputs := match inputs.getObjVal? "modules" with
    | .ok (.arr ms) => inputs.setObjVal! "modules" (.arr (ms.map fun (m : Json) =>
        match m.getObjValAs? String "source" with
        | .ok src => Json.mkObj [("name", (m.getObjVal? "name").toOption.getD Json.null), ("cid", toJson (sourceCid src))]
        | .error _ => m))
    | _ => inputs
  match inputs.getObjValAs? String "source", inputs.getObj? with
  | .ok src, .ok fields =>
    Json.mkObj ((fields.toList.filter fun (kv : String × Json) => kv.1 != "source") ++ [("sourceCid", toJson (sourceCid src))])
  | _, _ => inputs

/-- The `sources` field an entry needs: each source the world has not recorded, once. -/
def newSources (w : World) (sources : List String) : List (String × Json) :=
  let fresh := (sources.map fun src => (sourceCid src, src)).foldl (fun acc (cid, src) =>
    if w.modules.contains cid || acc.any (·.1 == cid) then acc else acc ++ [(cid, src)]) []
  if fresh.isEmpty then [] else
    [("sources", Json.arr (fresh.toArray.map fun (cid, src) => Json.mkObj [("cid", toJson cid), ("source", toJson src)]))]

/-- The sources an entry carries, checked against their CIDs. -/
def entrySources (entry : Json) : Except String (List (String × String)) := do
  let some raw := (entry.getObjVal? "sources").toOption | return []
  (← raw.getArr?).toList.mapM fun m => do
    let cid ← m.getObjValAs? String "cid"
    let src ← m.getObjValAs? String "source"
    unless sourceCid src == cid do throw "a journaled source is not its CID's"
    return (cid, src)

/-- Compile inputs from an entry: every CID resolved to the source a `module` entry recorded. -/
def expandInputs (w : World) (inputs : Json) : Except String Json := do
  let resolve := fun (cid : String) => match w.modules[cid]? with
    | some src => pure src
    | none => throw s!"compile inputs name module {cid}, which no module entry recorded"
  let inputs ← match inputs.getObjVal? "modules" with
    | .ok (.arr ms) => do
      let expanded ← ms.mapM fun m => do
        match m.getObjValAs? String "cid" with
        | .ok cid => pure (Json.mkObj [("name", (m.getObjVal? "name").toOption.getD Json.null), ("source", toJson (← resolve cid))])
        | .error _ => pure m
      pure (inputs.setObjVal! "modules" (.arr expanded))
    | _ => pure inputs
  match inputs.getObjValAs? String "sourceCid", inputs.getObj? with
  | .ok cid, .ok fields =>
    return Json.mkObj ((fields.toList.filter fun (kv : String × Json) => kv.1 != "sourceCid") ++ [("source", toJson (← resolve cid))])
  | _, _ => return inputs

def createRecJson (id : String) (c : CreateRec) : Json :=
  Json.mkObj [("object", toJson id), ("pin", toJson c.object.pin), ("sourcesSha256", toJson c.sources),
    ("read", c.object.read.json), ("chain", c.object.chain.json), ("compile", compactInputs c.object.inputs),
    ("seed", c.seed), ("law", toJson c.object.lawText)] |> fun j =>
    if c.object.supervisor.isEmpty then j else j.setObjVal! "supervisor" (toJson c.object.supervisor)

structure Judged where
  updates : List (String × Object)
  reprograms : List Json
  amendments : List Json
  creations : List (String × Object) := []
  creates : List Json := []

/-- The id of the `ordinal`th grant of the turn with this identity. -/
def grantId (principal intent : String) (ordinal : Nat) : String :=
  Journal.bodyHash (Json.arr #[toJson "grant", toJson principal, toJson intent, toJson ordinal])

/-- The grant `id`, if it can stand behind running `method` of `object` now: made, not
    revoked, the clock not past its `until`, and naming that object and method. -/
def grantStands (w : World) (id object method : String) : Option Grant :=
  match w.grants[id]? with
  | some g => if !g.revoked && w.clock ≤ g.expires && g.object == object && g.method == method then some g else none
  | none => none

/-- Install a commit's grants, spend its uses, and mark its revocations. -/
def applyGrants (w : World) (grants : List Grant) (revokes : List String) (spent : List (String × Nat) := []) : World :=
  let w := grants.foldl (fun w g => { w with grants := w.grants.insert g.id g }) w
  let w := spent.foldl (fun w (id, n) => match w.grants[id]? with
    | some g => { w with grants := w.grants.insert id { g with uses := g.uses.map (· - n) } }
    | none => w) w
  revokes.foldl (fun w id => match w.grants[id]? with
    | some g => { w with grants := w.grants.insert id { g with revoked := true } }
    | none => w) w

/-- The argument a use of grant `g` runs with: the caller's, with the grant's fixed part merged
    in. A fixed record field the caller gives with other bytes is a conflict; a fixed value that is
    not a record must be the whole argument (or the caller gives `{}`). -/
def attenuate (g : Grant) (argument : Data) : Except String Data := do
  let some raw := g.fixed | return argument
  let fixed ← decodeData Limits.dataDepth raw
  let same := fun (a b : Data) => Delvetalk.Canonical.encode a == Delvetalk.Canonical.encode b
  match fixed, argument with
  | .record ff, .record af =>
    for (k, v) in ff do
      if let some given := af.lookup k then
        unless same given v do throw "grantConflict"
    return .record (af ++ ff.filter fun (k, _) => (af.lookup k).isNone)
  | f, .record [] => return f
  | f, a => if same f a then return a else throw "grantConflict"

/-! ## The two-tier law

A package may declare `def law(old: State, new: State, request: Abi.Request) -> Abi.Verdict` (the
artifact's `law.present`) and `def lawReads() -> List<String>` (`law.reads`). After the law text
admits an ordinary write (kind 0), the host runs the current code's `law` on the object's state
before and after, with `request = {context, method, argument, kind, pin, reads}`, under
`Bounds.lawTicks`; `reads` are the objects `lawReads()` names, as `{object, version, state}`, each
a root of the turn. Reprograms and amendments are judged by the law text alone: the amendment
metarule is decided on the fragment, and no predicate, budget or bug can seal out the hand that
may amend or reprogram. -/

/-- Compile definition `name` of a package (compile inputs without `entry`) from its prepared
    closure, preparing the closure once per package; the world returned caches it. -/
def compileEntryIn (w : World) (inputs : Json) (name : String) : Except String (Package.EntryCompiled × World) := do
  let resolved ← resolveInputs w (Json.mkObj ((inputs.getObj?.toOption.map (·.toList)).getD [] |>.filter (·.1 != "entry")))
  let key := Journal.bodyHash resolved
  let (request, w) ← match w.requests[key]? with
    | some r => pure (r, w)
    | none =>
      let r ← (Package.prepareRequest resolved).mapError Package.Diagnostic.render
      let cache := if w.requests.size < Limits.maxBuilds then w.requests else {}
      pure (r, { w with requests := cache.insert key r })
  let compiled ← (Package.compileEntryFrom request name).mapError Package.Diagnostic.render
  return (compiled, w)

def compiledOf (c : Package.EntryCompiled) : Except String Compiled := do
  return ⟨← c.artifact.getObjVal? "packet", c.entry.type, c.entry.source.assumptions.bounds,
    c.entry.source.assumptions.rigid, some c.entry⟩

/-- A pure definition of a held entry run on data arguments under `ticks`: its value, or the
    machine's refusal (`budget` when the ticks ran out), and the ticks it used. -/
def runPure (entry : Delvetalk.CheckedEntry) (arguments : List Data) (ticks : Nat) :
    Except String Data × Nat :=
  match Package.executeDataEntry entry arguments.toArray (Json.mkObj [("ticks", toJson (toString ticks))]) with
  | .ok (.finished value _ _ usage) => (.ok value, usage.ticksUsed + usage.conversionNodes)
  | .ok (.refused failure usage) =>
    (.error (if (failure.splitOn "tick").length > 1 then "budget" else failure), usage.ticksUsed + usage.conversionNodes)
  | .error e => (.error e, 0)

/-- The cache key of an object's compiled definition (`compiledMethod` uses the same). -/
def defKey (o : Object) (name : String) : String := o.inputsKey ++ "/" ++ name

/-- An object's definition `name`, compiled and prepared (from the world's cache when warm). -/
def compileDef (w : World) (o : Object) (name : String) : Except String (Compiled × World) := do
  if let some c := w.compiled[defKey o name]? then return (c, w)
  let (c, w) ← compileEntryIn w (delegate o.inputs name) name
  return (← compiledOf c, w)

/-- Compile the Bend law (and its reads) of the objects a proposal writes, into the world's
    cache, so the pure `judge` finds them. -/
def warmLaws (w : World) (ids : List String) : World :=
  ids.foldl (fun w id => match w.objects[id]? with
    | some o =>
      if !o.predicate then w else
      (["law"] ++ (if o.predicateReads then ["lawReads"] else [])).foldl (fun w name =>
        if w.compiled.contains (defKey o name) then w else
        match compileDef w o name with
        | .ok (c, w) =>
          let cache := if w.compiled.size < Limits.maxCompiledPackets then w.compiled else {}
          { w with compiled := cache.insert (defKey o name) c }
        | .error _ => w) w
    | none => w) w

/-- The labels of a `List<String>` value. -/
partial def labels (acc : List String) : Data → Option (List String)
  | .variant "nil" _ => some acc.reverse
  | .variant "cons" (.record f) => match f.lookup "head", f.lookup "tail" with
    | some (.label s), some tail => labels (s :: acc) tail
    | _, _ => none
  | _ => none

/-- The objects an object's `lawReads()` names. -/
def lawReadsOf (w : World) (o : Object) : Except String (List String) := do
  if !o.predicateReads then return []
  let (c, _) ← compileDef w o "lawReads"
  let some entry := c.entry | throw "lawReads is not held"
  match (runPure entry [] Delvetalk.Bounds.lawTicks).1 with
  | .ok value => match labels [] value with
    | some ids => return ids.eraseDups.take Limits.maxRoots
    | none => throw "lawReads must return a List<String>"
  | .error _ => throw "lawReads did not finish"

/-- The proposal with the objects the Bend laws of its written objects read added as roots. -/
def withLawReads (w : World) (p : Proposal) : Proposal :=
  p.writes.foldl (fun p (id, _) => match w.objects[id]? with
    | some o => match lawReadsOf w o with
      | .ok ids => ids.foldl (fun p r =>
          if p.roots.any (·.1 == r) then p else match w.objects[r]? with
          | some ro => { p with roots := p.roots ++ [(r, ro.version)] }
          | none => p) p
      | .error _ => p
    | none => p) p

/-- An object's Bend law on one ordinary write: none when it admits. -/
def bendLaw (w : World) (p : Proposal) (id : String) (o : Object) (new : Data) (subject caller method : String)
    (argument : Data) (kind : Nat) (pin : String) : Option Refusal := Id.run do
  let refuse := fun (clause : String) => some ({ cls := "lawRefused", clause := some clause, object := some id } : Refusal)
  let .ok (c, _) := compileDef w o "law" | return refuse "law"
  let some entry := c.entry | return refuse "law"
  let .ok ids := lawReadsOf w o | return refuse "lawReads"
  let mut reads : List Data := []
  for r in ids do
    match w.objects[r]? with
    | some ro =>
      unless p.roots.any (·.1 == r) do return refuse "lawReads"
      reads := reads ++ [.record [("object", .label r), ("version", .natural ro.version), ("state", ro.state)]]
    | none => pure ()
  let context := Data.record [("world", .label ""), ("object", .label id), ("principal", .label subject),
    ("caller", .label caller), ("intent", .label p.intent), ("height", .natural w.height),
    ("inputOrigin", .record [("kind", .label "law"), ("object", .label caller), ("command", .label method),
      ("program", .label ""), ("immediatelyPrevious", .boolean false)])]
  let request := Data.record [("context", context), ("method", .label method), ("argument", argument),
    ("kind", .natural kind), ("pin", .label pin),
    ("reads", reads.foldr (fun x t => .variant "cons" (.record [("head", x), ("tail", t)])) (.variant "nil" (.record [])))]
  match (runPure entry [o.state, new, request] Delvetalk.Bounds.lawTicks).1 with
  | .ok (.variant "admitted" _) => return none
  | .ok (.variant "refused" (.record f)) =>
    match f.lookup "clause" with
    | some (.label clause) => return refuse clause
    | _ => return refuse "law"
  | .error "budget" => return some { cls := "budget", reason := some "law ticks", object := some id }
  | _ => return refuse "law"

/-- Every change of `id` in the writes is an ordinary write made only of commuting edits. -/
def commutesAt (writes : List (String × List Written)) (id : String) : Bool :=
  match writes.lookup id with
  | some changes => !changes.isEmpty && changes.all fun c => c.kind == 0 && c.edits.all (·.kind.commutes)
  | none => false

/-- Roots current, writes read, results conform, laws admit. Returns the objects
    as they would be installed. `height` is the height the entry would take. -/
def judge (w : World) (height : Nat) (p : Proposal) : Except Refusal Judged := do
  let writes := p.allWrites
  for id in p.roots.map (·.1) ++ writes.map (·.1) do
    unless w.objects.contains id do throw { cls := "unknownObject", object := id }
  -- A root the turn only changes by `add`/`append` (FOUNDATION section 13, row 1) need only be a
  -- version the object had: its changes re-apply on the state as it is now and are judged there.
  for (id, seen) in p.roots do
    if let some o := w.objects[id]? then
      if o.version != seen && !(seen < o.version && commutesAt writes id) then
        throw { cls := "staleRoot", object := id }
  -- A write to the running object needs no view; its version is the first root. A
  -- proposal that writes what it never named as a root is malformed.
  for (id, _) in writes do
    unless p.roots.any (·.1 == id) do
      throw { cls := "evaluation", object := id, reason := some "a write names an object that is not a root" }
  -- An absence is a root too: something appearing since the turn looked makes it stale.
  for id in p.absent do
    if w.objects.contains id then throw { cls := "staleRoot", object := id }
  if w.objects.size + p.creates.length > Limits.maxObjects then
    throw { cls := "evaluation", reason := some "object capacity reached" }
  if w.grants.size + p.grants.length > Limits.maxGrants then throw { cls := "capacity", object := some "grants" }
  for g in p.grants do
    if w.grants.contains g.id then throw { cls := "evaluation", reason := some "a grant id is already taken" }
  -- A limited grant must have the uses the turn spends left when it commits.
  for (id, n) in p.spent do
    match w.grants[id]? with
    | some g =>
      if let some left := g.uses then
        if left < n then throw { cls := "lawRefused", clause := some "grantSpent", object := some g.object }
    | none => throw { cls := "evaluation", reason := some "a turn spends an unknown grant" }
  -- A revocation needs the grantor's turn, or a turn that read the object holding the grant.
  for id in p.revokes do
    match w.grants[id]? with
    | some g =>
      unless g.grantor == p.principal || p.roots.any (·.1 == g.holder) do
        throw { cls := "lawRefused", clause := some "notGrantor", object := some g.holder }
    | none => throw { cls := "evaluation", reason := some "a revocation names an unknown grant" }
  let mut out : List (String × Object) := []
  let mut reprograms : List Json := []
  let mut amendments : List Json := []
  for (id, changes) in writes do
    let some o := w.objects[id]? | throw { cls := "unknownObject", object := id }
    let written ← match applyEdits o.state (changes.map (·.edits)) with
      | .ok d => pure d
      | .error clause => throw { cls := clause, object := id }
    unless written.conformsUnder o.bounds o.stateType do throw { cls := "typeMismatch", object := id }
    unless (dataJson written).compress.utf8ByteSize ≤ Limits.maxStateBytes do
      throw { cls := "capacity", object := id }
    -- A reprogram replaces code and, through its migration, the state's type.
    let mut next := o
    let mut state := written
    if let some (source, migration) := p.programs.lookup id then
      let refuse := fun (clause message : String) => Refusal.mk "programRefused" (some clause) (some id) (some message)
      let extend := p.layered.contains id
      let prog ← match programFor w o source migration extend with
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
                       stateType := prog.stateType, bounds := prog.bounds, methods := prog.methods,
                       predicate := prog.predicate, predicateReads := prog.predicateReads }
      reprograms := reprograms ++ [Json.mkObj [("object", toJson id), ("oldPin", toJson o.pin),
        ("newPin", toJson prog.pin), ("source", toJson source), ("migration", toJson migration),
        ("result", dataJson state)] |> fun j => if extend then j.setObjVal! "mode" (toJson "extend") else j]
    -- The current law judges the whole write, under the pin the object will run. Every
    -- kind of change the object undergoes in this turn is judged, once for each object
    -- that called the running one to make it: the subject is the principal, the caller
    -- is the object whose call it was (empty when the turn's own method wrote).
    -- A change made under a grant is judged with the grantor as its subject, if the grant
    -- still stands for this object and method; otherwise the turn is refused `noGrant`.
    let judgments := (changes.map fun c => (c.caller, c.kind, c.method, c.via)).eraseDups
    for (caller, kind, method, via) in (if judgments.isEmpty then [("", 0, "", "")] else judgments) do
      let subject ← if via.isEmpty then pure p.principal else
        match grantStands w via id method with
        | some g => pure g.grantor
        | none => throw { cls := "lawRefused", clause := some "noGrant", object := some id }
      let facts : Law.Facts := ⟨subject, caller, height, p.turn, next.pin, kind, method⟩
      if let some clause := Law.refusedBy o.law facts (some o.state) state then
        throw { cls := "lawRefused", clause, object := id }
    -- The Bend law, after the text admits: once for each ordinary change, with its argument.
    if o.predicate then
      let seen := (changes.filter (·.kind == 0)).foldl (fun (acc : List (String × Written)) c =>
        let key := (Json.arr #[toJson c.caller, toJson c.method, toJson c.via, dataJson c.argument]).compress
        if acc.any (·.1 == key) then acc else acc ++ [(key, c)]) []
      for (_, c) in seen do
        let subject := if c.via.isEmpty then p.principal else ((grantStands w c.via id c.method).map (·.grantor)).getD p.principal
        if let some r := bendLaw w p id o state subject c.caller c.method c.argument 0 next.pin then throw r
    if let some text := p.laws.lookup id then
      let refuse := fun (clause : String) => Refusal.mk "lawRefused" (some clause) (some id) none
      let law ← match parseLawText text with
        | .ok law => pure law
        | .error _ => throw (refuse "law syntax")
      let amender := ((changes.find? (·.kind == 2)).map (·.caller)).getD ""
      unless amendable law p.principal amender height p.turn next.pin state do throw (refuse noAmendmentClause)
      next := { next with law, lawText := text }
      amendments := amendments ++ [Json.mkObj [("object", toJson id), ("old", toJson o.lawText), ("new", toJson text)]]
    out := out ++ [(id, { next with version := o.version + 1, state })]
  return { updates := out, reprograms, amendments,
           creations := p.creates.map fun (id, c) => (id, c.object),
           creates := p.creates.map fun (id, c) => createRecJson id c }

/-! ## Entries -/

/-- Card names that mean the acting principal's own object: a turn or card naming `env` or
    `wake` runs `env/<principal>` or `wake/<principal>`. No object may take these ids, so no one
    can stand in for another's own. -/
def ownCards : List String := ["env", "wake"]

/-- The object a principal means by `object`: its own for a name in `ownCards`. -/
def resolveCard (principal object : String) : String :=
  if ownCards.contains object then s!"{object}/{principal}" else object

/-- The principal under which a settled interpretation is journaled. -/
def interpretationPrincipal : String := "interpretation"

def identityJson (principal intent : String) : Json :=
  Json.mkObj [("principal", toJson principal), ("intent", toJson intent)]

/-- Append a sealed entry to the world. -/
def tagOf (entry : Json) : String :=
  match entry.getObjVal? "outcome" |>.bind (·.getObjValAs? String "tag") with
  | .ok tag => tag
  | .error _ => "unknown"

/-- Refusals a retry may outrun: a root moved, a machine budget ran out, an evaluation
    failed. They are journaled but do not bind the identity's outcome. -/
def transientClasses : List String := ["staleRoot", "budget", "evaluation"]

def isTransient (entry : Json) : Bool :=
  tagOf entry == "refused" &&
    ((entry.getObjVal? "outcome").toOption.bind (·.getObjValAs? String "class" |>.toOption)).any transientClasses.contains

def record (w : World) (entry : Json) (key : String) (touch : List String) : World :=
  let hash := (entry.getObjValAs? String "hash").toOption.getD ""
  let index := w.entries.size
  let delivered := (entry.getObjVal? "delivery").toOption.bind fun d => (d.getObjValAs? String "id").toOption
  let identity := (entry.getObjVal? "identity").toOption.getD Json.null
  let sent := match (entry.getObjVal? "outcome").toOption.bind (fun o => (o.getObjValAs? String "tag").toOption),
      (entry.getObjVal? "sends").toOption.bind (·.getArr?.toOption) with
    | some "admitted", some sends => sends.map fun s =>
        -- A send under a grant is delivered as its grantor (the send's own `principal`).
        let fields := s.getObj?.toOption.map (·.toList) |>.getD []
        Json.mkObj ([("from", identity)] ++
          (if fields.any (·.1 == "principal") then [] else
            [("principal", (identity.getObjVal? "principal").toOption.getD Json.null)]) ++ fields)
    | _, _ => #[]
  let sources := (entrySources entry).toOption.getD []
  -- Offers of an admitted entry are retained for their addressees.
  let offered := if tagOf entry != "admitted" then #[] else
    (((entry.getObjVal? "offers").toOption.bind (·.getArr?.toOption)).getD #[]).zipIdx.filterMap fun (o, i) =>
      (o.getObjValAs? String "to").toOption.map (·, i)
  let publications := if tagOf entry != "admitted" then #[] else
    (((entry.getObjVal? "publishes").toOption.bind (·.getArr?.toOption)).getD #[]).zipIdx.map fun (_, i) => (index, i)
  { w with
    published := w.published ++ publications
    outbox := offered.foldl (fun box (to, i) => box.insert to ((box.getD to #[]).push (index, i))) w.outbox
    modules := sources.foldl (fun m (cid, src) => m.insert cid src) w.modules
    pending := (match delivered with
      | some id => w.pending.filter fun p => (p.getObjValAs? String "id").toOption != some id
      | none => w.pending) ++ sent ++
      -- An activity's end told to its object's supervisor, whatever the entry's outcome.
      (((entry.getObjVal? "ended").toOption.map fun e =>
        #[Json.mkObj ([("from", identity), ("principal", (identity.getObjVal? "principal").toOption.getD Json.null)] ++
          ((e.getObj?.toOption.map (·.toList)).getD []))]).getD #[])
    height := w.height + 1, head := hash, entries := w.entries.push entry
    clock := if tagOf entry == "advanced" then (entry.getObjVal? "outcome" |>.bind (·.getObjValAs? Nat "to")).toOption.getD w.clock else w.clock
    suspended := (match (entry.getObjValAs? String "resumes").toOption with
        | some h => w.suspended.filter fun s => (s.getObjValAs? String "hash").toOption != some h
        | none => w.suspended) ++ (if tagOf entry == "suspended" then #[entry] else #[])
    -- A suspended identity is not settled, nor one refused transiently: its next entry takes
    -- over the receipt.
    receipts := match w.receipts[key]? with
      | none => w.receipts.insert key index
      | some i => if tagOf w.entries[i]! == "suspended" || isTransient w.entries[i]! then w.receipts.insert key index
          else w.receipts
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
    let same := (entry.getObjValAs? String "request").toOption == some digest
    if tagOf entry == "suspended" then none
    -- A transient refusal does not bind the identity: the retry runs (and is judged) again.
    else if isTransient entry then none
    else if same then some (reply entry)
    else some (duplicate principal intent entry)

/-! ## Supervision -/

/-- The id of the `ended` delivery an entry at `height` sends. -/
def endedId (principal intent : String) (height : Nat) : String :=
  Journal.bodyHash (Json.arr #[toJson "ended", toJson principal, toJson intent, toJson height])

/-- The receipt an entry is, as `Plan.obend`'s `Receipt` on the wire. -/
def receiptOf (principal intent : String) (height : Nat) (outcome : Json) : Data :=
  let text := fun (k : String) => (outcome.getObjValAs? String k).toOption.getD ""
  .record [("slot", .record [("principal", .label principal), ("intent", .label intent)]),
    ("height", .natural height),
    ("outcome", if text "tag" == "refused" then .variant "refused" (.record [("class", .label (text "class")), ("root", .label (text "object"))])
      else .variant "admitted" (.record []))]

/-- The `ended` field of an entry: a delivery of `ended {receipt, how}` to the supervisor of
    `object`, under the ledger the activity ran with, one level deeper and less the work it
    spent. Nothing when the object has no supervisor (or it is gone). -/
def endedField (w : World) (object principal intent how : String) (ledger : Ledger) (used : Nat)
    (height : Nat) (outcome : Json) : List (String × Json) :=
  match (w.objects[object]?).map (·.supervisor) with
  | some sup =>
    if sup.isEmpty || !w.objects.contains sup then [] else
    let child : Ledger := ⟨ledger.depth - 1, ledger.work - used, ledger.storage⟩
    let argument := Data.record [("receipt", receiptOf principal intent height outcome), ("how", .label how)]
    [("ended", Json.mkObj [("id", toJson (endedId principal intent height)), ("to", toJson sup),
      ("method", toJson "ended"), ("argument", dataJson argument), ("sender", toJson object),
      ("ledger", child.json)])]
  | none => []

/-- The commit rule. Pure: the turn loop calls this with the roots it recorded and
    the writes it produced. Returns the next world and the reply (a receipt). -/
def commit (w : World) (p : Proposal) (extra : List (String × Json) := [])
    (forced : Option Refusal := none)
    (onAdmit : List (String × Object) → List (String × Json) := fun _ => [])
    (onEnd : Nat → Json → List (String × Json) := fun _ _ => []) : World × Json :=
  -- Arguments are kept only where a Bend law reads them; its reads are roots; its code is warm.
  let p := { p with writes := p.writes.map fun (id, ws) =>
    if ((w.objects[id]?).map (·.predicate)).getD false then (id, ws) else (id, ws.map fun x => { x with argument := .record [] }) }
  let w := warmLaws w (p.writes.map (·.1))
  let p := withLawReads w p
  match retained w p.principal p.intent p.digest with
  | some r => (w, r)
  | none =>
    -- The turn number is the host's: the height of the entry about to be written.
    let p := { p with turn := w.height + 1 }
    let key := identityKey p.principal p.intent
    let base := [("identity", identityJson p.principal p.intent), ("roots", rootsJson p.roots),
      ("turn", toJson p.turn), ("request", toJson p.digest)] ++
      (if p.absent.isEmpty then [] else [("absent", toJson p.absent)]) ++ extra
    let verdict : Except Refusal Judged :=
      match forced with | some r => .error r | none => judge w (w.height + 1) p
    match verdict with
    | .error r =>
      let outcome := Json.mkObj ([("tag", toJson "refused"), ("class", toJson r.cls)] ++
        (r.clause.map fun c => [("clause", toJson c)]).getD [] ++
        (r.object.map fun o => [("object", toJson o)]).getD [] ++
        (r.reason.map fun o => [("reason", toJson o)]).getD [])
      let (w', entry) := push w key (base ++ [("outcome", outcome)] ++ onEnd (w.height + 1) outcome) []
      (w', reply entry)
    | .ok judged =>
      let updates := judged.updates
      let w := updates.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      let w := judged.creations.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      let w := applyGrants w p.grants p.revokes p.spent
      let writes := Json.arr (updates.toArray.map fun (id, o) => Json.mkObj
        (("object", toJson id) :: ("version", toJson o.version) ::
          writtenFields ((p.allWrites.lookup id).getD [])))
      let outcome := Json.mkObj ([("tag", toJson "admitted"), ("writes", writes)] ++
        (if judged.reprograms.isEmpty then [] else [("reprograms", Json.arr judged.reprograms.toArray)]) ++
        (if judged.amendments.isEmpty then [] else [("amendments", Json.arr judged.amendments.toArray)]) ++
        (if judged.creates.isEmpty then [] else [("creates", Json.arr judged.creates.toArray)]) ++
        (if p.grants.isEmpty then [] else [("grants", Json.arr (p.grants.toArray.map Grant.json))]) ++
        (if p.revokes.isEmpty then [] else [("revokes", toJson p.revokes)]) ++
        (if p.spent.isEmpty then [] else [("spent", spentJson p.spent)]))
      let holders := (p.grants.map (·.holder)).filter fun h => !updates.any (·.1 == h)
      let (w', entry) := push w key (base ++ [("outcome", outcome)] ++ onAdmit updates ++
          newSources w (judged.creations.flatMap fun (_, o) => inputSources o.inputs) ++ onEnd (w.height + 1) outcome)
        (updates.map (·.1) ++ judged.creations.map (·.1) ++ holders.eraseDups)
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

/-- The law of an object created without one:
    `owner: request.kind == 0 or request.subject == "<creator>"`.

    Writes only ever change the running object (a method's `write` is its own; other
    objects change by being called, and their own law judges what they do to themselves),
    so a kind-0 judgment is always about an object's own method acting for a principal.
    The law therefore means: anyone may invoke my methods; only my creator may
    reprogram or amend me. An object that wants its writes guarded as well declares a law
    (`request.subject`, `request.caller`, `appendOnly`, `unchanged`, ...). -/
def defaultLaw (creator : String) : Except String Law := do
  if creator.any (fun c => c == '"' || c == '\\' || c.toNat < 32) then
    throw "the creator handle cannot be named in the default law"
  let clause ← Minidregg.Compiler.ObjectiveBendLaw.parse
    s!"request.kind == 0 or request.subject == \"{creator}\""
  return [("owner", clause)]

def buildKey (inputs : Json) : String := Journal.bodyHash inputs

def compileObject (w : World) (inputs : Json) : Except String Built := do
  if let some b := w.builds[buildKey inputs]? then return b
  let (artifact, ty, laws) ← Package.compileKeepingLaws (← resolveInputs w inputs)
  let packet ← artifact.getObjVal? "packet"
  let decoded ← Minidregg.Theory.ObjectiveBendTyping.decodePacket packet
  unless stateTypeOk decoded.source.assumptions ty do
    throw "package entry type must be a closed record of first-order data (a zero-argument definition returning the state record)"
  return { artifact, ty, laws, assumptions := decoded.source.assumptions }

/-- Give a compiled package its first state and law. `lawText`, when given, is the law
    exactly as journaled; otherwise the package's laws, or the default owner law. -/
def makeObject (b : Built) (inputs : Json) (state : Data) (read : Option Json := none)
    (chain : Option Json := none) (creator : String := "") (height : Nat := 1)
    (lawText : Option String := none) : Except String (Object × String) := do
  unless state.conformsUnder b.assumptions.bounds b.ty do throw "seed does not conform to the package state type"
  if (dataJson state).compress.utf8ByteSize > Limits.maxSeedBytes then throw "seed exceeds state byte capacity"
  let pin ← b.artifact.getObjValAs? String "packetSha256"
  let sources ← b.artifact.getObjValAs? String "sourcesSha256"
  -- No law declared: the creator owns reprogramming and amendment, anyone may write.
  let laws ← match lawText with
    | some text => parseLawText text
    | none => if b.laws.isEmpty then defaultLaw creator else pure b.laws
  unless amendable laws creator "" height 0 pin state do throw noAmendmentClause
  let (methods, predicate, predicateReads) := artifactShape b.artifact
  return ({ pin, law := laws, lawText := renderLaw laws, version := 0, state, stateType := b.ty,
            bounds := b.assumptions.bounds, read := ← parseRead read, chain := ← parseChain chain,
            inputs, inputsKey := inputsKeyOf inputs, methods, predicate, predicateReads }, sources)

def cacheBuild (w : World) (inputs : Json) (b : Built) : World :=
  if w.builds.size < Limits.maxBuilds then { w with builds := w.builds.insert (buildKey inputs) b } else w

/-- Build an object and remember its compiled package in the world. -/
def buildObjectIn (w : World) (inputs seed : Json) (read : Option Json := none) (chain : Option Json := none)
    (creator : String := "") (height : Nat := 1) (lawText : Option String := none) :
    Except String (Object × String × World) := do
  let built ← compileObject w inputs
  let (o, sources) ← makeObject built inputs (← decodeData Limits.dataDepth seed) read chain creator height lawText
  return (o, sources, cacheBuild w inputs built)

def buildObject (w : World) (inputs seed : Json) (read : Option Json := none) (chain : Option Json := none)
    (creator : String := "") (height : Nat := 1) (lawText : Option String := none) : Except String (Object × String) := do
  let (o, sources, _) ← buildObjectIn w inputs seed read chain creator height lawText
  return (o, sources)

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
  if ownCards.contains id then throw s!"object id {id} is reserved: it names each principal's own {id}/<principal>"
  if w.objects.contains id then throw s!"object {id} already exists"
  if w.objects.size ≥ Limits.maxObjects then throw "object capacity reached"
  let inputs ← attachLibrary w (← compileInputs j)
  let seed ← j.getObjVal? "seed"
  let (o, sources, w) ← buildObjectIn w inputs seed (j.getObjVal? "read").toOption (j.getObjVal? "chain").toOption principal (w.height + 1)
  let supervisor := (← optText j "supervisor").getD ""
  unless supervisor.isEmpty || w.objects.contains supervisor do throw s!"supervisor {supervisor} is not an object"
  let o := { o with supervisor }
  -- An `artifact` claim is only a claim: the journal keeps the inputs, never the claim.
  let outcome := createOutcome id o sources (compactInputs inputs) seed
  let outcome := if supervisor.isEmpty then outcome else outcome.setObjVal! "supervisor" (toJson supervisor)
  let (w', entry) := push { w with objects := w.objects.insert id o } (identityKey principal intent)
    ([("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson digest), ("outcome", outcome)] ++ newSources w (inputSources inputs)) [id]
  return (w', reply entry)

/-! ## The library as a journaled fact

The first `library` entry records the library's pin, its modules and the world law that
judges every later change; a change is another `library` entry naming the pin it
replaces. Replay re-seals the recorded modules and re-judges the change. -/

/-- The default law of library change: only the principal who opened the world. -/
def libraryLawText (opener : String) : Except String String := do
  if opener.any (fun c => c == '"' || c == '\\' || c.toNat < 32) then
    throw "the opener handle cannot be named in the library law"
  return s!"law opener: request.subject == \"{opener}\""

/-- The first clause of the world law that refuses `principal` installing library `pin`. -/
def libraryRefusal (lawText principal : String) (height : Nat) (pin : String) : Option String :=
  match parseLawText lawText with
  | .error _ => some "law syntax"
  | .ok law => Law.refusedBy law ⟨principal, "", height, height, pin, 1, ""⟩ (some (.record [])) (.record [])

def installLibrary (w : World) (lib : Library) (lawText : String) : World :=
  { w with library := some lib, libraries := w.libraries.insert lib.pin lib, libraryLaw := lawText }

/-- Journal the library as the world's own (`lawArg` only on the first), or a change of it.
    The world law judges the principal; a refusal is a `lawRefused` entry naming `library`. -/
def libraryOp (w : World) (principal intent : String) (lib : Library) (lawArg : Option String) :
    Except String (World × Json) := do
  let digest := Journal.bodyHash (Json.arr #[toJson principal, toJson intent, toJson lib.pin])
  if let some r := retained w principal intent digest then return (w, r)
  let first := w.library.isNone
  let lawText ← if first then (match lawArg with | some t => pure t | none => libraryLawText principal)
    else pure w.libraryLaw
  if !first && w.library.map (·.pin) == some lib.pin then
    return (w, Json.mkObj [("status", toJson "library"), ("pin", toJson lib.pin), ("changed", toJson false)])
  let key := identityKey principal intent
  let base := [("identity", identityJson principal intent), ("roots", rootsJson []),
    ("turn", toJson (w.height + 1)), ("request", toJson digest)]
  match libraryRefusal lawText principal (w.height + 1) lib.pin with
  | some clause =>
    let outcome := Json.mkObj [("tag", toJson "refused"), ("class", toJson "lawRefused"),
      ("clause", toJson clause), ("object", toJson "library")]
    let (w', entry) := push w key (base ++ [("outcome", outcome)]) []
    return (w', reply entry)
  | none =>
    let outcome := Json.mkObj ([("tag", toJson "library"), ("pin", toJson lib.pin),
      ("previous", toJson ((w.library.map (·.pin)).getD "")), ("modules", modulesJson lib.modules)] ++
      (if first then [("law", toJson lawText)] else []))
    let (w', entry) := push (installLibrary w lib lawText) key (base ++ [("outcome", outcome)]) []
    return (w', reply entry)

/-! ## Settings and posts

The first open that names a clock principal or a posting quota journals a `settings` entry;
after that both are fixed. `posted` entries record what transport published for an object,
so a reply to that post can be routed back (`world-addressee`). -/

def settingsOp (w : World) (clock : Option String) (quota : Option Nat) : Except String (World × Json) := do
  if clock.isNone && quota.isNone then return (w, Json.null)
  let clockP := clock.getD ""
  if w.settled then
    if (clock.isSome && clockP != w.clockPrincipal) || (quota.isSome && quota != some w.postQuota) then
      throw s!"the journal records clock {w.clockPrincipal} and postQuota {w.postQuota}; the settings differ"
    return (w, Json.null)
  if let some c := clock then discard <| boundedText "clock principal" Limits.maxPrincipalBytes c
  let q := quota.getD 16
  let intent := "settings"
  let (w', entry) := push { w with clockPrincipal := clockP, postQuota := q, settled := true }
    (identityKey "world" intent)
    [("identity", identityJson "world" intent), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson (Journal.bodyHash (Json.mkObj [("clock", toJson clockP), ("postQuota", toJson q)]))),
     ("outcome", Json.mkObj [("tag", toJson "settings"), ("clock", toJson clockP), ("postQuota", toJson q)])] []
  return (w', reply entry)

def parseSlot (j : Json) : Except String Json := do
  let principal ← boundedText "slot principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let intent ← boundedText "slot intent" Limits.maxIntentBytes (← j.getObjValAs? String "intent")
  return identityJson principal intent

def postIndex (w : World) (uri : String) (post : Post) : World :=
  { w with posts := w.posts.insert uri post }

/-- The `page` and `section` of a `posted` request or outcome: absent, or a page title (a line of
    at most `maxTitleBytes`) and a section, "" for the whole page. A section without a page is refused. -/
def postedPage (j : Json) : Except String (String × String) := do
  let page ← optText j "page"
  let part ← optText j "section"
  match page with
  | none => if part.isSome then throw "section needs a page" else return ("", "")
  | some page =>
    let part := part.getD ""
    if page.isEmpty || page.utf8ByteSize > Limits.maxTitleBytes || part.utf8ByteSize > Limits.maxTitleBytes
        || page.any (· == '\n') || part.any (· == '\n') then
      throw s!"page and section are titles: one line of 1..{Limits.maxTitleBytes} bytes"
    return (page, part)

/-- `world-posted {principal, uri, cid, object, slot?, page?, section?}`: transport confirms a post it
    made for `object` (and for an awaited `slot`, or carrying the object's publication of `page`,
    section "" for the whole page). Only the world's clock principal, when one is named. -/
def postedOp (w : World) (j : Json) : Except String (World × Json) := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let uri ← boundedText "uri" Limits.maxUriBytes (← j.getObjValAs? String "uri")
  let cid ← boundedText "cid" Limits.maxUriBytes (← j.getObjValAs? String "cid")
  let object ← boundedText "object id" Limits.maxObjectIdBytes (← j.getObjValAs? String "object")
  let slot ← match j.getObjVal? "slot" with
    | .ok (.null) | .error _ => pure none
    | .ok s => pure (some (← parseSlot s))
  let (page, part) ← postedPage j
  unless uri.startsWith "at://" do throw "uri must be an at:// URI"
  if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then
    throw s!"posts are confirmed only by {w.clockPrincipal}"
  unless w.objects.contains object do throw s!"unknown object {object}"
  let fields := [("tag", toJson "posted"), ("uri", toJson uri), ("cid", toJson cid), ("object", toJson object)] ++
    (slot.map fun s => [("slot", s)]).getD [] ++
    (if page.isEmpty then [] else [("page", toJson page), ("section", toJson part)])
  let digest := Journal.bodyHash (Json.mkObj fields)
  let answer := fun (entry : Json) => Json.mkObj [("status", toJson "posted"),
    ("height", (entry.getObjVal? "height").toOption.getD Json.null), ("receipt", entry)]
  let intent := "posted:" ++ uri
  match retained w principal intent digest with
  | some r => return (w, match r.getObjVal? "receipt" with | .ok e => answer e | .error _ => r)
  | none =>
    if w.posts.contains uri then throw s!"post {uri} is already recorded"
    let (w', entry) := push (postIndex w uri { object, slot, page, part, height := w.height + 1 }) (identityKey principal intent)
      [("identity", identityJson principal intent), ("roots", rootsJson []), ("turn", toJson 0),
       ("request", toJson digest), ("outcome", Json.mkObj fields)] [object]
    return (w', answer entry)

/-- `world-addressee {parent}`: the object (and slot, or page and section) a post at `parent` was made for. -/
def addressee (w : World) (j : Json) : Except String Json := do
  let uri ← j.getObjValAs? String "parent"
  match w.posts[uri]? with
  | none => return Json.mkObj [("status", toJson "unknown")]
  | some p => return Json.mkObj ([("status", toJson "addressee"), ("object", toJson p.object)] ++
      (p.slot.map fun s => [("slot", s)]).getD [] ++
      (if p.page.isEmpty then [] else [("page", toJson p.page), ("section", toJson p.part)]))

/-! ## Replay -/

/-- The id of the `ordinal`th send of the turn with this identity. -/
def deliveryId (principal intent : String) (ordinal : Nat) : String :=
  Journal.bodyHash (Json.arr #[toJson principal, toJson intent, toJson ordinal])

def ledgerOf (j : Json) : Except String Ledger := do
  return ⟨← natField j "depth", ← natField j "work", ← natField j "storage"⟩

/-- A delivery entry must consume exactly the pending delivery it names, under
    the sender's principal; a budget refusal must name a field that is zero. -/
def checkDelivery (w : World) (entry : Json) (principal intent : String) (outcome : Json) : Except String Unit := do
  -- The final entry of a resumed delivery names its delivery again; the suspension consumed it.
  if (entry.getObjVal? "resumes").toOption.isSome then return ()
  let some d := (entry.getObjVal? "delivery").toOption | return ()
  let id ← d.getObjValAs? String "id"
  let some p := w.pending.find? fun p => (p.getObjValAs? String "id").toOption == some id
    | throw "delivery of an unknown or already delivered id"
  unless (p.getObjValAs? String "principal").toOption == some principal && intent == id do
    throw "delivery runs under another principal than its sender's"
  unless (d.getObjVal? "from").toOption == (p.getObjVal? "from").toOption do throw "delivery names another sender"
  unless (d.getObjValAs? String "via").toOption == (p.getObjValAs? String "via").toOption do
    throw "delivery names another grant than its send"
  if (outcome.getObjValAs? String "class").toOption == some "budgetExhausted" then
    let ledger ← ledgerOf (← p.getObjVal? "ledger")
    unless ledger.exhausted == (outcome.getObjValAs? String "reason").toOption do
      throw "budget refusal names a field that is not exhausted"
  else if (← ledgerOf (← p.getObjVal? "ledger")).exhausted.isSome then
    throw "a delivery with an exhausted ledger ran"

def checkSends (w : World) (entry : Json) (principal intent : String) : Except String Unit := do
  let some sends := (entry.getObjVal? "sends").toOption | return ()
  let mut ordinal := 0
  for s in ← sends.getArr? do
    if let .ok via := s.getObjValAs? String "via" then
      let some g := grantStands w via (← s.getObjValAs? String "to") (← s.getObjValAs? String "method")
        | throw "a send names a grant that does not stand"
      unless (s.getObjValAs? String "principal").toOption == some g.grantor do
        throw "a send under a grant is not delivered as its grantor"
    unless (s.getObjValAs? String "id").toOption == some (deliveryId principal intent ordinal) do
      throw "send id does not match its ordinal"
    discard <| s.getObjValAs? String "to"
    discard <| s.getObjValAs? String "method"
    discard <| decodeData Limits.dataDepth (← s.getObjVal? "argument")
    discard <| ledgerOf (← s.getObjVal? "ledger")
    ordinal := ordinal + 1

/-- An `ended` field names its entry's id and the supervisor of the object it speaks for. -/
def checkEnded (w : World) (entry : Json) (principal intent : String) : Except String Unit := do
  let some e := (entry.getObjVal? "ended").toOption | return ()
  unless (← e.getObjValAs? String "id") == endedId principal intent (w.height + 1) do throw "an ended delivery is not its entry's"
  let object ← e.getObjValAs? String "sender"
  unless (w.objects[object]?).map (·.supervisor) == some (← e.getObjValAs? String "to") do
    throw "an ended delivery is not to the object's supervisor"
  discard <| decodeData Limits.dataDepth (← e.getObjVal? "argument")
  discard <| ledgerOf (← e.getObjVal? "ledger")

/-- An entry that resumes a suspension must name a waiting one of the same identity. -/
def checkResumes (w : World) (entry : Json) (principal intent : String) : Except String Unit := do
  let some h := (entry.getObjValAs? String "resumes").toOption | return ()
  let some s := w.suspended.find? fun s => (s.getObjValAs? String "hash").toOption == some h
    | throw "resumes a suspension that is not waiting"
  let id ← s.getObjVal? "identity"
  unless (id.getObjValAs? String "principal").toOption == some principal &&
      (id.getObjValAs? String "intent").toOption == some intent do
    throw "resumes a suspension of another identity"

/-- The objects an admitted entry created, rebuilt from their journaled inputs. -/
def rebuildCreates (w : World) (principal : String) (recorded : Array Json) :
    Except String (World × List (String × CreateRec)) := do
  let mut w := w
  let mut creates : List (String × CreateRec) := []
  for r in recorded do
    let id ← r.getObjValAs? String "object"
    let seed ← r.getObjVal? "seed"
    let (o, sources, w') ← buildObjectIn w (← expandInputs w (← r.getObjVal? "compile")) seed (r.getObjVal? "read").toOption
      (r.getObjVal? "chain").toOption principal (w.height + 1) (some (← r.getObjValAs? String "law"))
    w := w'
    let o := { o with supervisor := (r.getObjValAs? String "supervisor").toOption.getD "" }
    creates := creates ++ [(id, ({ object := o, sources, seed } : CreateRec))]
  return (w, creates)

def replayEntry (w : World) (entry : Json) : Except String World := do
  let identity ← entry.getObjVal? "identity"
  let principal ← identity.getObjValAs? String "principal"
  let intent ← identity.getObjValAs? String "intent"
  let key := identityKey principal intent
  let outcome ← entry.getObjVal? "outcome"
  -- The sources an entry introduces are known before its compile inputs are read.
  let introduced ← entrySources entry
  for (cid, _) in introduced do
    if w.modules.contains cid then throw "a source is journaled twice"
  let w := { w with modules := introduced.foldl (fun m (cid, src) => m.insert cid src) w.modules }
  checkDelivery w entry principal intent outcome
  checkSends w entry principal intent
  checkResumes w entry principal intent
  checkEnded w entry principal intent
  match ← outcome.getObjValAs? String "tag" with
  | "advanced" =>
    let before ← natField outcome "from"
    let to ← natField outcome "to"
    unless before == w.clock && to > before do throw "clock advance out of sequence"
    return record w entry key []
  | "settings" =>
    if w.settled then throw "settings recorded twice"
    return record { w with clockPrincipal := ← outcome.getObjValAs? String "clock",
                           postQuota := ← natField outcome "postQuota", settled := true } entry key []
  | "posted" =>
    let uri ← outcome.getObjValAs? String "uri"
    let object ← outcome.getObjValAs? String "object"
    if w.posts.contains uri then throw "post recorded twice"
    unless w.objects.contains object do throw "post for an unknown object"
    if !w.clockPrincipal.isEmpty && principal != w.clockPrincipal then throw "post confirmed by another principal"
    let slot ← match outcome.getObjVal? "slot" with
      | .ok s => pure (some (← parseSlot s))
      | .error _ => pure none
    let (page, part) ← postedPage outcome
    return record (postIndex w uri { object, slot, page, part, height := ← natField entry "height" }) entry key [object]
  | "suspended" =>
    let activity ← outcome.getObjVal? "activity"
    let checkpoint ← activity.getObjVal? "checkpoint"
    let tokens ← Delvetalk.Turn.tokensOfJson (← checkpoint.getObjVal? "tokens")
    unless (← checkpoint.getObjValAs? String "digest") == Delvetalk.Turn.checkpointDigest
        (← checkpoint.getObjValAs? String "packetSha256") (← checkpoint.getObjValAs? String "object")
        (← checkpoint.getObjValAs? String "principal") (← checkpoint.getObjValAs? String "intent")
        (← checkpoint.getObjValAs? String "rootsDigest") tokens do
      throw "checkpoint digest does not match its tokens"
    discard <| outcome.getObjVal? "slot"
    discard <| natField outcome "deadline"
    return record w entry key []
  | "library" =>
    let recorded ← parseModules (← outcome.getObjVal? "modules")
    let lib ← sealLibrary recorded
    unless lib.modules == recorded && lib.pin == (← outcome.getObjValAs? String "pin") do
      throw "library entry is not the seal of its modules"
    unless (← outcome.getObjValAs? String "previous") == ((w.library.map (·.pin)).getD "") do
      throw "library entry does not replace the current library"
    let lawText ← if w.library.isNone then outcome.getObjValAs? String "law" else pure w.libraryLaw
    if let some clause := libraryRefusal lawText principal (w.height + 1) lib.pin then
      throw s!"library change would be refused by the world law ({clause})"
    return record (installLibrary w lib lawText) entry key []
  | "interpreted" =>
    let id ← outcome.getObjValAs? String "id"
    unless principal == interpretationPrincipal && intent == id do
      throw "interpretation runs under another identity than its request's"
    unless w.suspended.any (fun s => ((s.getObjVal? "outcome").toOption.bind fun o => (o.getObjVal? "interpretation").toOption
        |>.bind fun i => (i.getObjValAs? String "id").toOption) == some id) do
      throw "interpretation of an unknown or already settled request"
    discard <| outcome.getObjVal? "reply"
    let verdict ← outcome.getObjVal? "verdict"
    unless ["proposal", "unclear", "replied"].contains (← verdict.getObjValAs? String "tag") do throw "unknown verdict"
    return record w entry key []
  | "created" =>
    let id ← outcome.getObjValAs? String "object"
    if w.objects.contains id then throw s!"object {id} created twice"
    let inputs ← expandInputs w (← outcome.getObjVal? "compile")
    let (o, sources, w) ← buildObjectIn w inputs (← outcome.getObjVal? "seed") (outcome.getObjVal? "read").toOption (outcome.getObjVal? "chain").toOption principal (w.height + 1)
    unless o.pin == (← outcome.getObjValAs? String "pin") && sources == (← outcome.getObjValAs? String "sourcesSha256") do
      throw s!"object {id} no longer compiles to its recorded pin"
    let o := { o with supervisor := (outcome.getObjValAs? String "supervisor").toOption.getD "" }
    return record { w with objects := w.objects.insert id o } entry key [id]
  | "refused" =>
    let cls ← outcome.getObjValAs? String "class"
    unless refusalClasses.contains cls do throw s!"unknown refusal class {cls}"
    return record w entry key []
  | "admitted" =>
    let rawWrites ← (← outcome.getObjVal? "writes").getArr?
    let writes ← parseRecordedWrites (Json.arr rawWrites)
    let turn ← natField entry "turn"
    let recordedPrograms := (outcome.getObjVal? "reprograms").toOption.bind (·.getArr?.toOption) |>.getD #[]
    let recordedLaws := (outcome.getObjVal? "amendments").toOption.bind (·.getArr?.toOption) |>.getD #[]
    let programs ← recordedPrograms.toList.mapM fun r => do
      return (← r.getObjValAs? String "object", (← r.getObjValAs? String "source", ← r.getObjValAs? String "migration"))
    let layered := recordedPrograms.toList.filterMap fun r =>
      if (r.getObjValAs? String "mode").toOption == some "extend" then (r.getObjValAs? String "object").toOption else none
    let laws ← recordedLaws.toList.mapM fun r => do
      return (← r.getObjValAs? String "object", ← r.getObjValAs? String "new")
    let recordedCreates := (outcome.getObjVal? "creates").toOption.bind (·.getArr?.toOption) |>.getD #[]
    let (w, creates) ← rebuildCreates w principal recordedCreates
    let absent := ((entry.getObjVal? "absent").toOption.bind (·.getArr?.toOption) |>.getD #[]).toList.filterMap
      fun a => a.getStr?.toOption
    let grants ← ((outcome.getObjVal? "grants").toOption.bind (·.getArr?.toOption) |>.getD #[]).toList.mapM Grant.ofJson
    let revokes ← ((outcome.getObjVal? "revokes").toOption.bind (·.getArr?.toOption) |>.getD #[]).toList.mapM (·.getStr?)
    for (g, i) in grants.zipIdx do
      unless g.id == grantId principal intent i && g.grantor == principal do throw "a grant is not its turn's"
    let spent ← parseSpent (outcome.getObjVal? "spent").toOption
    let p : Proposal := { principal, intent, roots := ← parseRoots (← entry.getObjVal? "roots"), writes, turn, programs, laws,
                          absent, creates, grants, revokes, spent, layered }
    unless turn == w.height + 1 do throw "turn is not the height of its entry"
    unless (entry.getObjValAs? String "request").toOption == some p.digest do throw "request digest does not match"
    let w := warmLaws w (p.writes.map (·.1))
    match judge w (w.height + 1) p with
    | .error r => throw s!"admitted entry would be refused ({r.cls})"
    | .ok judged =>
      unless judged.reprograms == recordedPrograms.toList && judged.amendments == recordedLaws.toList &&
          judged.creates == recordedCreates.toList do
        throw "recorded reprograms, amendments or creations do not replay"
      let updates := judged.updates
      for raw in rawWrites do
        let id ← raw.getObjValAs? String "object"
        let some (_, o) := updates.find? (·.1 == id) | throw "write missing"
        unless (← natField raw "version") == o.version do throw "write version out of sequence"
      let w := updates.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      let w := judged.creations.foldl (fun w (id, o) => { w with objects := w.objects.insert id o }) w
      let w := applyGrants w grants revokes spent
      let holders := (grants.map (·.holder)).filter fun h => !updates.any (·.1 == h)
      return record w entry key (updates.map (·.1) ++ judged.creations.map (·.1) ++ holders.eraseDups)
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

/-! ## The clock -/

/-- `world-advance {height}`: the only clock the world has. Moving it is journaled so
    replay is deterministic; moving it to or before now is a no-op. -/
def advance (w : World) (j : Json) : Except String (World × Json) := do
  let to ← natField j "height"
  if !w.clockPrincipal.isEmpty then
    let who := (← optText j "principal").getD ""
    if who != w.clockPrincipal then throw s!"the clock is moved only by {w.clockPrincipal}"
  if to ≤ w.clock then
    return (w, Json.mkObj [("status", toJson "advanced"), ("clock", toJson w.clock)])
  let intent := s!"advance:{to}"
  let (w', entry) := push w (identityKey "clock" intent)
    [("identity", identityJson "clock" intent), ("roots", rootsJson []), ("turn", toJson 0),
     ("request", toJson (Journal.bodyHash (toJson intent))),
     ("outcome", Json.mkObj [("tag", toJson "advanced"), ("from", toJson w.clock), ("to", toJson to)])] []
  return (w', Json.mkObj [("status", toJson "advanced"), ("clock", toJson to), ("receipt", entry)])

/-! ## Reads -/

/-- Ids the reader may view, starting with `prefix`, after `after` in byte order: one page,
    and whether more follow. -/
def listIds (w : World) (reader pfx after : String) : List String × Bool :=
  let ids := (w.objects.toList.filterMap fun (id, o) =>
    if id.startsWith pfx && decide (after < id) && o.read.permits reader then some id else none).toArray.qsort (· < ·)
  ((ids.extract 0 Limits.listPage).toList, ids.size > Limits.listPage)

/-- `world-objects {principal, prefix?, after?}`. -/
def objectsOp (w : World) (j : Json) : Except String Json := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let text := fun (k : String) => match j.getObjVal? k with
    | .ok (.str s) => pure s
    | .ok _ => throw s!"{k} must be text"
    | .error _ => pure ""
  let (ids, more) := listIds w principal (← text "prefix") (← text "after")
  return Json.mkObj [("status", toJson "listed"), ("ids", toJson ids), ("more", toJson more)]

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

/-- The public projection of a refusal: observed, not committed, the class and the root it
    names, and nothing else; an `unknownObject` refusal also names the id the author wrote (as
    resolved, so `env` reads `env/<did>`) and where the list of cards is. -/
def publicRefusal (entry : Json) : Json :=
  let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
  let root := (outcome.getObjValAs? String "object").toOption.getD ""
  let cls := (outcome.getObjValAs? String "class").toOption.getD "unknown"
  Json.mkObj ([("status", toJson "refused"), ("class", toJson cls), ("root", toJson root)] ++
    (if cls == "unknownObject" then
      [("object", toJson root), ("hint", toJson s!"no card named {root}; reply to the directory for the list")]
    else []))

/-- A reader may see an object's changes if it may view the object (an object no longer in
    the world is not viewable). -/
def viewable (w : World) (reader id : String) : Bool :=
  match w.objects[id]? with
  | some o => o.read.permits reader
  | none => false

/-- An entry as `reader` may see it. The identity's own principal sees it whole. Anyone else
    sees a refusal only as its public projection, and any other entry as its chain fields,
    identity, turn and outcome tag, with the roots and writes of objects it may view; the rest
    is elided and counted. Results, offers, sends, sources and checkpoints never show. -/
def projectEntry (w : World) (reader : String) (entry : Json) : Json :=
  let owner := ((entry.getObjVal? "identity").toOption.bind fun i => (i.getObjValAs? String "principal").toOption).getD ""
  if owner == reader && !reader.isEmpty then entry
  else if tagOf entry == "refused" then
    (publicRefusal entry).setObjVal! "height" ((entry.getObjVal? "height").toOption.getD Json.null)
      |>.setObjVal! "hash" ((entry.getObjVal? "hash").toOption.getD Json.null)
  else
    let objectOf := fun (x : Json) => (x.getObjValAs? String "object").toOption.getD ""
    let arr := fun (x : Option Json) => ((x.bind (·.getArr?.toOption)).getD #[])
    let outcome := (entry.getObjVal? "outcome").toOption.getD Json.null
    let roots := arr (entry.getObjVal? "roots").toOption
    let writes := arr (outcome.getObjVal? "writes").toOption
    let shownRoots := roots.filter fun r => viewable w reader (objectOf r)
    let shownWrites := writes.filter fun x => viewable w reader (objectOf x)
    let elided := (roots.size - shownRoots.size) + (writes.size - shownWrites.size)
    Json.mkObj ((["height", "previous", "hash", "identity", "turn"].filterMap fun k =>
        (entry.getObjVal? k).toOption.map (k, ·)) ++
      [("roots", Json.arr shownRoots),
       ("outcome", Json.mkObj ([("tag", toJson (tagOf entry))] ++
         (if writes.isEmpty then [] else [("writes", Json.arr shownWrites)]))),
       ("elided", toJson elided)])

/-- A reader principal: 1..128 bytes, or "" for an anonymous reader (public objects only). -/
def readerOf (j : Json) : Except String String := do
  let p ← j.getObjValAs? String "principal"
  if p.utf8ByteSize > Limits.maxPrincipalBytes then throw s!"principal must be at most {Limits.maxPrincipalBytes} bytes"
  return p

/-- `world-receipt {principal, identity, of?}`: the receipt of identity (`of`, default the
    reader, `identity`), projected under the reader's authority. -/
def receipt (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let intent ← boundedText "identity" Limits.maxIntentBytes (← j.getObjValAs? String "identity")
  let owner := (← optText j "of").getD reader
  match w.receipts[identityKey owner intent]? with
  | none => return Json.mkObj [("status", toJson "unknown")]
  | some index =>
    let entry := w.entries[index]!
    let shown := projectEntry w reader entry
    if owner != reader && tagOf entry == "refused" then return publicRefusal entry
    return Json.mkObj [("status", toJson "receipt"), ("receipt", shown)]

def history (w : World) (j : Json) : Except String Json := do
  let reader ← readerOf j
  let id ← j.getObjValAs? String "object"
  let after := (← optNat j "after").getD 0
  let asked := (← optNat j "limit").getD Limits.maxHistoryLimit
  if asked == 0 || asked > Limits.maxHistoryLimit then throw s!"limit must be 1..{Limits.maxHistoryLimit}"
  if !w.objects.contains id then return Json.mkObj [("status", toJson "unknown"), ("object", toJson id)]
  if !viewable w reader id then return Json.mkObj [("status", toJson "denied"), ("object", toJson id)]
  let all := (w.touched.getD id #[]).filter fun index => index + 1 > after
  let page := all.extract 0 asked
  return Json.mkObj [("status", toJson "history"), ("object", toJson id),
    ("entries", Json.arr (page.map fun index => projectEntry w reader w.entries[index]!)),
    ("more", toJson (decide (all.size > asked)))]

/-- The principal transport reads publications as: the world's clock principal, or "transport". -/
def publisher (w : World) : String := if w.clockPrincipal.isEmpty then "transport" else w.clockPrincipal

/-- `world-offers {principal, after?}`: the offers addressed to the principal, oldest first,
    after journal height `after`; one page. The publisher also gets the `publications`
    (`{height, ordinal, id, object, page, section, text}`) to post. -/
def offersOp (w : World) (j : Json) : Except String Json := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let after := (← optNat j "after").getD 0
  let all := (w.outbox.getD principal #[]).filter fun (index, _) => index + 1 > after
  let page := all.extract 0 Limits.maxHistoryLimit
  let items := page.filterMap fun (index, i) => do
    let entry ← w.entries[index]?
    let offer ← ((entry.getObjVal? "offers").toOption.bind (·.getArr?.toOption)).bind (·[i]?)
    pure (Json.mkObj [("height", toJson (index + 1)), ("ordinal", toJson i),
      ("identity", (entry.getObjVal? "identity").toOption.getD Json.null),
      ("text", (offer.getObjVal? "text").toOption.getD Json.null)])
  let pubs := if principal != publisher w then #[] else
    let mine := w.published.filter fun (index, _) => index + 1 > after
    (mine.extract 0 Limits.maxHistoryLimit).filterMap fun (index, i) => do
      let entry ← w.entries[index]?
      let p ← ((entry.getObjVal? "publishes").toOption.bind (·.getArr?.toOption)).bind (·[i]?)
      let fields ← p.getObj?.toOption
      pure (Json.mkObj ([("height", toJson (index + 1)), ("ordinal", toJson i)] ++ fields.toList))
  return Json.mkObj ([("status", toJson "offers"), ("offers", Json.arr items), ("more", toJson (decide (all.size > page.size)))] ++
    (if principal == publisher w then [("publications", Json.arr pubs)] else []))


/-- The newest whole-page post recorded for each object's page, by `identityKey object page`:
    the post a section edit of that page replies to. -/
def pagePosts (w : World) : Std.HashMap String (Nat × String) :=
  w.posts.fold (init := {}) fun m uri p =>
    if p.page.isEmpty || !p.part.isEmpty then m else
    let key := identityKey p.object p.page
    match m[key]? with
    | some (h, _) => if h ≥ p.height then m else m.insert key (p.height, uri)
    | none => m.insert key (p.height, uri)

/-- `world-publications {principal, after?}`: the publications admitted turns retained, for the
    publisher (the clock principal, else "transport"; anyone else is `denied`), oldest first after
    journal height `after`, one page: `{height, ordinal, id, object, page, section, body}`, and
    `replyTo` for a section edit when a post of its whole page is recorded (the newest). -/
def publicationsOp (w : World) (j : Json) : Except String Json := do
  let principal ← boundedText "principal" Limits.maxPrincipalBytes (← j.getObjValAs? String "principal")
  let after := (← optNat j "after").getD 0
  if principal != publisher w then return Json.mkObj [("status", toJson "denied")]
  let all := w.published.filter fun (index, _) => index + 1 > after
  let shown := all.extract 0 Limits.maxHistoryLimit
  let posts := pagePosts w
  let items := shown.filterMap fun (index, i) => do
    let entry ← w.entries[index]?
    let p ← ((entry.getObjVal? "publishes").toOption.bind (·.getArr?.toOption)).bind (·[i]?)
    let field := fun (k : String) => (p.getObjValAs? String k).toOption
    let object ← field "object"
    let title ← field "page"
    let part ← field "section"
    let text ← field "text"
    -- The retained text is the agentwiki header, a blank line, then the body.
    let body := "\n\n".intercalate (text.splitOn "\n\n").tail
    let replyTo := if part.isEmpty then [] else
      match posts[identityKey object title]? with
      | some (_, uri) => [("replyTo", toJson uri)]
      | none => []
    pure (Json.mkObj ([("height", toJson (index + 1)), ("ordinal", toJson i),
      ("id", (p.getObjVal? "id").toOption.getD Json.null), ("object", toJson object), ("page", toJson title),
      ("section", toJson part), ("body", toJson body)] ++ replyTo))
  return Json.mkObj [("status", toJson "publications"), ("publications", Json.arr items),
    ("more", toJson (decide (all.size > shown.size)))]

end Delvetalk.Host
