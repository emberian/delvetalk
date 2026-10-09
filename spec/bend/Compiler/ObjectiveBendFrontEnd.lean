/- The Objective Bend front end, source text to checked typed core, in Lean.

`lower` is the whole front end on an already-read package: parse every module
(`Compiler.ObjectiveBendParse`), check each module's locked import transcript
against its parsed imports, elaborate the selected declaration
(`Compiler.ObjectiveBendElaborate`), apply result projections, and render the
core (`dregg.objective-bend.core.v2`) and the typing proposal packet
(`dregg.objective-bend.typed-core.v3`) that the checker reads.

`accept` closes the loop on the SAME value: it decodes the packet the front end
just rendered with the checker's own decoder and runs the proof-producing checker
on it. That the decoded term IS the erasure of the elaborator's annotated term is a
theorem (`ObjectiveBendTermWire.decode_json`), not a run-time comparison: `accept`
refuses only a term nested deeper than the decoder's capacity. An `Accepted` value
therefore carries a typing derivation for exactly the Core4 term the elaborator
produced (`ObjectiveBendFrontEndAdequacy` states what that buys). -/
import Compiler.ObjectiveBendParse
import Compiler.ObjectiveBendSurface
import Compiler.ObjectiveBendElaborate
import Compiler.ObjectiveBendLaw
import Compiler.ObjectiveBendTermWire
import Compiler.Sha256
import Theory.ObjectiveBendTyping
namespace Minidregg.Compiler.ObjectiveBendFrontEnd
open Lean
open Minidregg.Compiler.ObjectiveBendElaborate (ATerm CoreTerm Output)
open Minidregg.Theory.ObjectiveBendTyping (DecodedPacket decodePacket Checked check)
set_option autoImplicit false

/-! ## Diagnostics -/

/-- A front-end refusal: the stage that refused, its message, and (for a parse refusal) the
line span and module. Rendered as `dregg.bend.compiler-diagnostic.v1`. -/
structure Diagnostic where
  stage : String
  message : String
  span : Option ObjectiveBendParse.Span := none
  sourceModule : Option String := none
  /-- A one-line statement of the real form when the refused source shows a known
  dialect habit (hosted front end, `Delvetalk.Hints`); never affects acceptance. -/
  hint : Option String := none
  deriving Inhabited, Repr

def Diagnostic.json (d : Diagnostic) : Json :=
  Json.mkObj ([("schema", toJson "dregg.bend.compiler-diagnostic.v1"), ("stage", toJson d.stage),
    ("message", toJson d.message)] ++
    (match d.span with | some s => [("span", s.json)] | none => []) ++
    (match d.sourceModule with | some m => [("module", toJson m)] | none => []) ++
    (match d.hint with | some h => [("hint", toJson h)] | none => []))

def elaborationRefusal (message : String) : Diagnostic := { stage := "objective-core-elaboration", message }

/-! ## Captured modules -/

/-- An import edge as captured: the parsed edge (path, alias, span) and its lock
(the earlier module it names and that module's source fingerprint). -/
structure LockedImport where
  path : String
  importAlias : String
  span : ObjectiveBendSurface.Span
  target : Nat
  moduleName : String
  sha256 : String
  deriving Inhabited

def LockedImport.json (i : LockedImport) : Json :=
  Json.mkObj [("path", toJson i.path), ("alias", toJson i.importAlias), ("span", i.span.json),
    ("module", toJson (toString i.target)), ("moduleName", toJson i.moduleName), ("sha256", toJson i.sha256)]

/-- One module of a captured package: its exact source text and fingerprint. -/
structure SourceModule where
  name : String
  source : String
  sha256 : String
  imports : List LockedImport
  deriving Inhabited

def SourceModule.binding (m : SourceModule) : Json :=
  Json.mkObj [("name", toJson m.name), ("sourceSha256", toJson m.sha256),
    ("imports", Json.arr (m.imports.map LockedImport.json).toArray)]

/-- The locked edge as the parser wrote it (path, alias, span). -/
def LockedImport.parsed (i : LockedImport) : ObjectiveBendSurface.Import := ⟨i.path, i.importAlias, i.span⟩

/-- A parsed module, checked: its locked import transcript is exactly the parsed one, and its
AST reads as the elaborator's module. -/
def checkImports (m : SourceModule) (ast : ObjectiveBendSurface.Module) : Except Diagnostic Unit := do
  if ast.imports != m.imports.map LockedImport.parsed then
    throw (elaborationRefusal "import transcript differs from parsed imports")

/-- The (alias, module name) pairs of a module's locked imports. -/
def SourceModule.aliases (m : SourceModule) : List (String × String) :=
  m.imports.map fun i => (i.importAlias, i.moduleName)

def checkParsed (m : SourceModule) (ast : ObjectiveBendSurface.Module) :
    Except Diagnostic ObjectiveBendElaborate.Module := do
  checkImports m ast
  match ObjectiveBendElaborate.ofSurface m.name m.aliases ast with
  | .ok d => pure d
  | .error e => throw (elaborationRefusal e)

def parseSource (name source : String) : Except Diagnostic ObjectiveBendSurface.Module :=
  match ObjectiveBendParse.parseObjective source with
  | .ok ast => pure ast
  | .error d => throw { stage := "objective-source-parse", message := d.message, span := d.span, sourceModule := some name }

/-- Parse one module and check it (`checkParsed`). -/
def parseModule (m : SourceModule) : Except Diagnostic ObjectiveBendElaborate.Module := do
  checkParsed m (← parseSource m.name m.source)

/-! ## Lowering -/

/-- `^[1-9][0-9]*$` with a value cap. -/
def positive (value : Json) (cap : Nat) : Option Nat := do
  let text ← value.getStr?.toOption
  let n ← text.toNat?
  if n == 0 || toString n != text || n > cap then none else some n

/-- The typed-core packet fields around a typing proposal for `term`, `context` empty. -/
def packetJson (proposal : Json) (term : ATerm) (sourceEntry : String) (modules : List SourceModule)
    (typeFuel : Nat) : Json :=
  let field (k : String) := (proposal.getObjVal? k).toOption.getD .null
  Json.mkObj [("schema", toJson "dregg.objective-bend.typed-core.v3"), ("term", term.json),
    ("types", field "types"), ("annotations", field "annotations"), ("bounds", field "bounds"),
    ("shareableVariables", field "shareableVariables"), ("fuel", toJson (toString typeFuel)),
    ("context", Json.arr #[]), ("sourceEntry", toJson sourceEntry),
    ("sourceModules", Json.arr (modules.map SourceModule.binding).toArray),
    ("status", toJson "exact core annotation proposal; actual checker must return Checked; no law proof or effect authority")]

/-! ## The closure check, on the proposal as Lean data

Checking a whole closure needs the checker's verdict, not a packet: no artifact carries
the whole closure. Its annotated source is built from the typing proposal directly, with
the types hash-consed as the packet's type table would share them (an entry's packet, which
does leave the process, is still rendered, decoded and checked by `accept`). What the
packet decoder would add here is only its capacities on type nesting and row width. -/

section direct
open Minidregg.Theory.ObjectiveBendTypes (Ty LambdaAnnotation Quantity Reuse)
open ObjectiveBendElaborate (PTy InternKey Slot Proposed propose)

structure TyTable where
  table : Array Ty := #[]
  seen : Std.HashMap InternKey Nat := {}
  /-- As `Interner.shared`: read and written only by the compiled `tyOf` (`tyOfShared`). -/
  shared : Std.HashMap USize (Slot × Ty) := {}

def quantityOf : String → Quantity
  | "erased" => .erased | "affine" => .affine | "linear" => .linear | _ => .unrestricted
def reuseOf : String → Reuse
  | "once" => .once | _ => .reusable

def tyNode (key : InternKey) (make : Unit → Ty) : StateM TyTable (Slot × Ty) := do
  let s ← get
  match s.seen[key]? with
  | some i => return (.ref i, s.table[i]?.getD (make ()))
  | none =>
    let t := make ()
    set ({ s with table := s.table.push t, seen := s.seen.insert key s.table.size } : TyTable)
    return (.ref s.table.size, t)

/-- `tyOf`, walking each shared subtree once (as `PTy.internSlotShared`). -/
unsafe def tyOfShared (t : PTy) : StateM TyTable (Slot × Ty) := do
  match t with
  | .natural => return (.leaf .natural, .natural)
  | .boolean => return (.leaf .boolean, .boolean)
  | .label => return (.leaf .label, .label)
  | .emptyRow => return (.leaf .emptyRow, .emptyRow)
  | .variable i => return (.leaf (.variable i), .variable i)
  | .data => return (.leaf .data, .data)
  | _ =>
    let address := ptrAddrUnsafe t
    if let some found := (← get).shared[address]? then return found
    let found ← match t with
      | .arrow r q d c => do
        let (ds, dt) ← tyOfShared d
        let (cs, ct) ← tyOfShared c
        tyNode (.arrow r q ds cs) fun _ => .arrow (reuseOf r) (quantityOf q) dt ct
      | .field n m t => do
        let (ms, mt) ← tyOfShared m
        let (ts, tt) ← tyOfShared t
        tyNode (.field n ms ts) fun _ => .field n mt tt
      | .specification m e => do
        let (ms, mt) ← tyOfShared m
        let (es, et) ← tyOfShared e
        tyNode (.specification ms es) fun _ => .specification mt et
      | .prototype sp t => do
        let (ss, st) ← tyOfShared sp
        let (ts, tt) ← tyOfShared t
        tyNode (.prototype ss ts) fun _ => .prototype st tt
      | .variant r => do
        let (rs, rt) ← tyOfShared r
        tyNode (.variant rs) fun _ => .variant rt
      | .computation p r a => do
        let (ps, pt) ← tyOfShared p
        let (rs, rt) ← tyOfShared r
        let (as, at_) ← tyOfShared a
        tyNode (.computation ps rs as) fun _ => .computation pt rt at_
      | _ => return (.leaf .natural, .natural)
    modify fun s => { s with shared := s.shared.insert address found }
    return found

/-- A proposal type as the checker's `Ty`, every composite node shared by its table key. -/
@[implemented_by tyOfShared]
def tyOf : PTy → StateM TyTable (Slot × Ty)
  | .natural => return (.leaf .natural, .natural)
  | .boolean => return (.leaf .boolean, .boolean)
  | .label => return (.leaf .label, .label)
  | .emptyRow => return (.leaf .emptyRow, .emptyRow)
  | .variable i => return (.leaf (.variable i), .variable i)
  | .data => return (.leaf .data, .data)
  | .arrow r q d c => do
    let (ds, dt) ← tyOf d
    let (cs, ct) ← tyOf c
    tyNode (.arrow r q ds cs) fun _ => .arrow (reuseOf r) (quantityOf q) dt ct
  | .field n m t => do
    let (ms, mt) ← tyOf m
    let (ts, tt) ← tyOf t
    tyNode (.field n ms ts) fun _ => .field n mt tt
  | .specification m e => do
    let (ms, mt) ← tyOf m
    let (es, et) ← tyOf e
    tyNode (.specification ms es) fun _ => .specification mt et
  | .prototype sp t => do
    let (ss, st) ← tyOf sp
    let (ts, tt) ← tyOf t
    tyNode (.prototype ss ts) fun _ => .prototype st tt
  | .variant r => do
    let (rs, rt) ← tyOf r
    tyNode (.variant rs) fun _ => .variant rt
  | .computation p r a => do
    let (ps, pt) ← tyOf p
    let (rs, rt) ← tyOf r
    let (as, at_) ← tyOf a
    tyNode (.computation ps rs as) fun _ => .computation pt rt at_

/-- The annotated source a proposal and an erased term make: what `decodePacket` reads back
from the packet `packetJson` would render. -/
def directSource (proposed : Proposed) (erased : CoreTerm) :
    Minidregg.Theory.ObjectiveBendTyping.AnnotatedTerm := Id.run do
  let mut table : TyTable := {}
  let mut annotations : Std.HashMap (List Nat) LambdaAnnotation := {}
  for a in proposed.annotations do
    let ((_, domain), t) := (tyOf a.domain).run table
    let ((_, codomain), t) := (tyOf a.codomain).run t
    table := t
    annotations := annotations.insertIfNew a.path ⟨domain, codomain, quantityOf a.parameter, reuseOf a.reuse⟩
  let ((_, row), t) := (tyOf proposed.row).run table
  table := t
  let mut bounds : List (Nat × Ty) := [(0, row)]
  for (k, b) in proposed.bounds do
    let ((_, ty), t) := (tyOf b).run table
    table := t
    bounds := bounds ++ [(k, ty)]
  return ⟨erased, fun path => annotations[path]?, ⟨bounds, 0 :: proposed.bounds.map (·.1), []⟩⟩

end direct

/-! ## Templates: each open declaration checked once against its bounds alone (D2) -/

/-- The context every knot field is checked in: `$seed : {}` then `$globals : the knot`. -/
def knotContext : Minidregg.Theory.ObjectiveBendTypes.Context :=
  [⟨.emptyRow, .unrestricted⟩, ⟨.variable 0, .unrestricted⟩]

/-- OB-LTUO LT2 D2. An open declaration's knot field is its template at its own bounds. It is
checked here by the checker with its `Self` variable RIGID: `Self`'s bound is a lower bound
(members are read through it) and never an alias, so a body that uses `self` where a value
of exactly its bound row is expected, which the alias checker of the whole program would
accept and only a wider instance would refuse, is refused HERE, naming the declaration.
`Theory.ObjectiveBendTemplates.Discharges.check_instantiate` is what a template accepted
here buys: acceptance at every instance whose bounds are discharged. -/
def checkTemplate (output : Output) (key : String) (rigidVariables : List Nat) (typeFuel : Nat)
    (field : ATerm) : Except Diagnostic Unit := do
  let refuse := fun (why : String) =>
    (throw (elaborationRefusal why) : Except Diagnostic Unit)
  let noTemplate := fun (e : String) => elaborationRefusal ("refused (template-typing): open declaration " ++ key ++
    " has no typed template: " ++ e)
  let proposed ← (ObjectiveBendElaborate.propose { output with term := field }).mapError noTemplate
  let erased ← field.erase.mapError noTemplate
  let source := directSource proposed erased
  let rigidAt := fun (vars : List Nat) => { source with assumptions := { source.assumptions with rigid := vars } }
  match check (rigidAt rigidVariables) knotContext typeFuel with
  | some _ => pure ()
  | none =>
    -- Which variable only an alias would accept: Self (the first) or Super (the second).
    if (check (rigidAt (rigidVariables.take 1)) knotContext typeFuel).isSome then
      refuse ("refused (super-rigid): open declaration " ++ key ++ " uses super as a value of its " ++
        "Super bound row; Super ranges over every row beneath that HAS those members (a lower bound), so " ++
        "a value of type Super is not a value of the bound row. Read the members it needs (super.m), or " ++
        "extend super (Super with {...})")
    else
    match check source knotContext typeFuel with
    | some _ => refuse ("refused (self-rigid): open declaration " ++ key ++ " uses self as a value of its " ++
        "Self bound row; Self ranges over every type that HAS that row (a lower bound), so a value of type " ++
        "Self is not a value of the row. Read the members it needs (self.m) instead")
    | none => refuse ("refused (template-typing): open declaration " ++ key ++
        " does not type-check against its declared bounds")

def checkTemplates (output : Output) (typeFuel : Nat) : Except Diagnostic Unit :=
  output.templates.forM fun (key, rigidVariables, field) => checkTemplate output key rigidVariables typeFuel field

/-- The packet of a lowering: its typing proposal's packet, or why there is none. -/
def packetOf (proposal : Except String Json) (term : ATerm) (sourceEntry : String) (modules : List SourceModule)
    (typeFuel : Nat) : Json :=
  match proposal with
  | .error message => Json.mkObj [("status", toJson "unsupported"), ("message", toJson message)]
  | .ok proposal => packetJson proposal term sourceEntry modules typeFuel

structure Lowering where
  output : Output
  /-- The selected term after projections: what the core and the packet carry. -/
  term : ATerm
  sourceEntry : String
  argumentCodec : String
  mode : String
  modules : List SourceModule
  limits : Json
  typeFuel : Nat
  /-- The package's enforced laws: the entry module's top-level `law` declarations (a law in any
  other module refuses). The artifact commits them; the kernel installs them on every object
  pinned to the artifact. -/
  laws : List (String × ObjectiveBendLaw.LawExpr)
  /-- The typing proposal for the selected term, or why there is none: built once. -/
  proposal : Except String Json
  /-- `dregg.objective-bend.typed-core.v3`: exactly the packet the checker reads (an
  unsupported proposal is `{status: "unsupported", message}`), built once. -/
  packet : Json
  proposalIs : proposal = ObjectiveBendElaborate.proposalJson { output with term := term }
  packetIs : packet = packetOf proposal term sourceEntry modules typeFuel

/-- Assemble a lowering, building its proposal and packet once. -/
def Lowering.make (output : Output) (term : ATerm) (sourceEntry argumentCodec mode : String)
    (modules : List SourceModule) (limits : Json) (typeFuel : Nat)
    (laws : List (String × ObjectiveBendLaw.LawExpr)) : Lowering :=
  let proposal := ObjectiveBendElaborate.proposalJson { output with term := term }
  ⟨output, term, sourceEntry, argumentCodec, mode, modules, limits, typeFuel, laws, proposal,
    packetOf proposal term sourceEntry modules typeFuel, rfl, rfl⟩

def project (term : ATerm) (projections : List Json) : Except Diagnostic ATerm :=
  projections.foldlM (init := term) fun t p => do
    let t := match (p.getObjValAs? String "field").toOption with
      | some field => if field.isEmpty then t else ATerm.get t field
      | none => t
    match p.getObjVal? "argument" with
    | .ok (.str n) =>
      if ObjectiveBendElaborate.isCanonicalNat n then pure (ATerm.app t (.nat n))
      else throw (elaborationRefusal "projection argument must be canonical Nat")
    | .ok _ => throw (elaborationRefusal "projection argument must be canonical Nat")
    | .error _ => pure t

/-- Selection mode, projections and limits: `limits` carries `heap`/`stack`/`ticks` (canonical
positive, at most 1000000) and an optional `typeFuel` (at most 16384, default 4096) that
travels in the packet. Returns the projections and the type fuel. -/
def options (projections limits : Json) (mode : String) : Except Diagnostic (List Json × Nat) := do
  if mode != "application" && mode != "definition" then
    throw (elaborationRefusal "selection mode must be application or definition")
  let projectionList ← match projections.getArr? with
    | .ok a => pure a.toList
    | .error _ => throw (elaborationRefusal "projections must be an array")
  if mode == "definition" && !projectionList.isEmpty then
    throw (elaborationRefusal "definition mode forbids result projections")
  for key in ["heap", "stack", "ticks"] do
    if (positive ((limits.getObjVal? key).toOption.getD .null) 1000000).isNone then
      throw (elaborationRefusal "preview limits must be canonical positive decimal strings ≤1000000")
  let typeFuel ← match limits.getObjVal? "typeFuel" with
    | .error _ => pure 4096
    | .ok v => match positive v 16384 with
      | some n => pure n
      | none => throw (elaborationRefusal "typeFuel must be a canonical positive decimal string ≤16384")
  return (projectionList, typeFuel)

/-- The front end on an elaborated closure: select the entry and project. Templates are
checked here unless the caller already checked every template of the closure. -/
def lowerElaborated (modules : List SourceModule) (decoded : List ObjectiveBendElaborate.Module)
    (elaborated : ObjectiveBendElaborate.Elaborated) (templatesChecked : Bool)
    (entryModule : Nat) (entryDefinition : String) (args projections limits : Json) (mode : String) :
    Except Diagnostic Lowering := do
  let (projectionList, typeFuel) ← options projections limits mode
  if modules.length > 64 then throw (elaborationRefusal "preview module capacity refused")
  let output ← match elaborated.select entryModule entryDefinition args mode with
    | .ok o => pure o
    | .error e => throw (elaborationRefusal e)
  let term ← project output.term projectionList
  let some entry := modules[entryModule]? | throw (elaborationRefusal "missing selected entry")
  let argumentCodec := if mode == "definition" then "unapplied-definition"
    else match args with
      | .arr _ => "legacy-canonical-nat-bool-record"
      | _ => "dregg.objective-bend.argument-values.v1"
  unless templatesChecked do checkTemplates output typeFuel
  for (m, index) in decoded.zipIdx do
    if index != entryModule && !m.laws.isEmpty then
      throw (elaborationRefusal ("a law belongs to the package's entry module; " ++ m.name ++
        " is imported and declares " ++ toString m.laws.length ++ " law(s)"))
  let laws := (decoded[entryModule]?.map (·.laws)).getD []
  return Lowering.make output term (entry.name ++ "." ++ entryDefinition) argumentCodec mode modules limits typeFuel laws

/-- The front end on parsed, checked modules: elaborate the selected declaration and project. -/
def lowerDecoded (modules : List SourceModule) (decoded : List ObjectiveBendElaborate.Module)
    (entryModule : Nat) (entryDefinition : String) (args projections limits : Json) (mode : String) :
    Except Diagnostic Lowering := do
  discard <| options projections limits mode
  if modules.length > 64 then throw (elaborationRefusal "preview module capacity refused")
  let elaborated ← (ObjectiveBendElaborate.elaboratePackage decoded).mapError elaborationRefusal
  lowerElaborated modules decoded elaborated false entryModule entryDefinition args projections limits mode

/-- The whole front end on read modules: options, parse and check every module, elaborate,
project. -/
def lower (modules : List SourceModule) (entryModule : Nat) (entryDefinition : String)
    (args projections limits : Json) (mode : String) : Except Diagnostic Lowering := do
  discard <| options projections limits mode
  let decoded ← modules.mapM parseModule
  lowerDecoded modules decoded entryModule entryDefinition args projections limits mode

def Lowering.core (l : Lowering) : Json :=
  Json.mkObj [("schema", toJson "dregg.objective-bend.core.v2"), ("edition", toJson "objective-bend-1"),
    ("term", l.term.json), ("sourceEntry", toJson l.sourceEntry), ("argumentCodec", toJson l.argumentCodec),
    ("selectionMode", toJson l.mode), ("sourceModules", Json.arr (l.modules.map SourceModule.binding).toArray),
    ("status", toJson "elaborated executable term; typing is checked by the actual checker, adequacy in ObjectiveBendFrontEndAdequacy"),
    ("limits", l.limits)]


/-! ## Acceptance: the checker on the front end's own packet -/

/-- With a typing proposal, the packet's `term` field is the rendering of the selected term. -/
theorem Lowering.packet_term (l : Lowering) {proposal : Json} (proposed : l.proposal = .ok proposal) :
    l.packet.getObjVal? "term" = .ok l.term.json := by
  rw [l.packetIs, proposed]
  unfold packetOf packetJson
  exact ObjectiveBendTermWire.getObjVal_mkObj (by simp) (by simp)

/-- The front end's packet, decoded by the checker's decoder: its annotations and assumptions
type the erasure of the elaborator's term, and the proof-producing checker accepted that
term closed. The packet's own term IS that erasure (`packetTerm`, by
`ObjectiveBendTermWire.decode_json`), so the checker typed exactly what the packet carries. -/
structure Accepted (l : Lowering) where
  private mk ::
  erased : CoreTerm
  erasure : l.term.erase = .ok erased
  proposal : Json
  proposed : l.proposal = .ok proposal
  packet : DecodedPacket
  decoded : decodePacket l.packet = .ok packet
  /-- The decoded packet's term is the elaborator's erased term: a theorem, not a check. -/
  packetTerm : packet.source.term = erased
  closed : packet.context = []
  /-- The checked source: the packet's annotations on the elaborator's erased term. -/
  source : Minidregg.Theory.ObjectiveBendTyping.AnnotatedTerm
  sourceExact : source = { packet.source with term := erased }
  typed : Checked source []
  checkedExact : check source [] packet.fuel = some typed

/-- The checked source IS the decoded packet's source. -/
theorem Accepted.source_eq_packet {l : Lowering} (a : Accepted l) : a.source = a.packet.source := by
  rw [a.sourceExact, ← a.packetTerm]

def accept (l : Lowering) : Except Diagnostic (Accepted l) := do
  match erasure : l.term.erase with
  | .error e => throw (elaborationRefusal ("core erasure: " ++ e))
  | .ok erased =>
    match proposed : l.proposal with
    | .error message => throw { stage := "objective-source-type-proposal", message }
    | .ok proposal =>
      if shallow : ObjectiveBendTermWire.depth l.term ≤ Minidregg.Theory.ObjectiveBendTyping.termNestingCapacity then
        match decoded : decodePacket l.packet with
        | .error e =>
          throw { stage := "objective-source-type-proposal", message := "typed packet does not decode: " ++ e }
        | .ok packet =>
          have packetTerm : packet.source.term = erased := by
            have rendered := ObjectiveBendTermWire.decode_json l.term _ erased shallow erasure
            have read := ObjectiveBendTermWire.decodePacket_term decoded (l.packet_term proposed)
            rw [rendered] at read
            exact (Except.ok.inj read).symm
          if closed : packet.context = [] then
            let source := { packet.source with term := erased }
            match typed : check source [] packet.fuel with
            | some checked =>
              pure ⟨erased, erasure, proposal, proposed, packet, decoded, packetTerm, closed, source, rfl, checked, typed⟩
            | none => throw { stage := "objective-typed-check", message := "the checker refused the front end's typed packet" }
          else throw (elaborationRefusal "typed packet context must be closed")
      else throw (elaborationRefusal "core term nesting exceeds the checker's decoding capacity")

/-- `accept`'s refusals, in its order, for a whole closure checked on its direct source. -/
def checkDirect (out : Output) (typeFuel : Nat) (rigid : List Nat) :
    Except Diagnostic (Minidregg.Theory.ObjectiveBendTyping.AnnotatedTerm) := do
  let erased ← match out.term.erase with
    | .error e => throw (elaborationRefusal ("core erasure: " ++ e))
    | .ok erased => pure erased
  let proposed ← match ObjectiveBendElaborate.propose out with
    | .error message => throw { stage := "objective-source-type-proposal", message }
    | .ok p => pure p
  unless ObjectiveBendTermWire.depth out.term ≤ Minidregg.Theory.ObjectiveBendTyping.termNestingCapacity do
    throw (elaborationRefusal "core term nesting exceeds the checker's decoding capacity")
  let source := directSource proposed erased
  let source := { source with assumptions := { source.assumptions with rigid } }
  match check source [] typeFuel with
  | some _ => pure source
  | none => throw { stage := "objective-typed-check", message := "the checker refused the front end's typed packet" }

/-- Check a whole elaborated closure once: every template, and the knot of every
declaration as one closed term. An entry's packet then carries only what it reaches
(`Elaborated.select`) without any declaration going unchecked. -/
def checkClosure (_modules : List SourceModule) (elaborated : ObjectiveBendElaborate.Elaborated)
    (limits : Json) : Except Diagnostic Unit := do
  let (_, typeFuel) ← options (.arr #[]) limits "definition"
  let whole := elaborated.whole
  checkTemplates whole typeFuel
  discard <| checkDirect whole typeFuel []

#assert_axioms Lowering.packet_term
#assert_axioms Accepted.source_eq_packet

end Minidregg.Compiler.ObjectiveBendFrontEnd
