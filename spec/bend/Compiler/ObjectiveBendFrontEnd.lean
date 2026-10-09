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
  deriving Inhabited, Repr

def Diagnostic.json (d : Diagnostic) : Json :=
  Json.mkObj ([("schema", toJson "dregg.bend.compiler-diagnostic.v1"), ("stage", toJson d.stage),
    ("message", toJson d.message)] ++
    (match d.span with | some s => [("span", s.json)] | none => []) ++
    (match d.sourceModule with | some m => [("module", toJson m)] | none => []))

def elaborationRefusal (message : String) : Diagnostic := { stage := "objective-core-elaboration", message }

/-! ## Captured modules -/

/-- An import edge as captured: the parsed edge (path, alias, span) and its lock
(the earlier module it names and that module's source fingerprint). -/
structure LockedImport where
  path : String
  importAlias : String
  span : Json
  target : Nat
  moduleName : String
  sha256 : String
  deriving Inhabited

def LockedImport.json (i : LockedImport) : Json :=
  Json.mkObj [("path", toJson i.path), ("alias", toJson i.importAlias), ("span", i.span),
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

def declarationName (d : Json) : String :=
  match (d.getObjValAs? String "kind").toOption with
  | some "function" => ((d.getObjVal? "signature").bind (·.getObjValAs? String "name")).toOption.getD ""
  | _ => (d.getObjValAs? String "name").toOption.getD ""

/-- A parsed module, checked: its locked import transcript is exactly the parsed one, and its
AST decodes to the elaborator's module. -/
def checkParsed (m : SourceModule) (ast : Json) : Except Diagnostic ObjectiveBendElaborate.Module := do
  let parsed := ((ast.getObjVal? "imports").bind Json.getArr?).toOption.getD #[]
  let locked := m.imports.toArray.map fun i =>
    Json.mkObj [("path", toJson i.path), ("alias", toJson i.importAlias), ("span", i.span)]
  if (Json.arr parsed).compress != (Json.arr locked).compress then
    throw (elaborationRefusal "import transcript differs from parsed imports")
  match ObjectiveBendElaborate.decodeModule (Json.mkObj [("name", toJson m.name),
      ("imports", Json.arr (m.imports.map fun i =>
        Json.mkObj [("alias", toJson i.importAlias), ("moduleName", toJson i.moduleName)]).toArray), ("ast", ast)]) with
  | .ok d => pure d
  | .error e => throw (elaborationRefusal e)

def parseSource (name source : String) : Except Diagnostic Json :=
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
def checkTemplate (output : Output) (sourceEntry : String) (modules : List SourceModule) (typeFuel : Nat)
    (key : String) (rigidVariables : List Nat) (field : ATerm) : Except Diagnostic Unit := do
  let refuse := fun (why : String) =>
    (throw (elaborationRefusal why) : Except Diagnostic Unit)
  let proposal ← match ObjectiveBendElaborate.proposalJson { output with term := field } with
    | .ok proposal => pure proposal
    | .error e => throw (elaborationRefusal ("refused (template-typing): open declaration " ++ key ++
        " has no typed template: " ++ e))
  let packet ← match decodePacket (packetJson proposal field sourceEntry modules typeFuel) with
    | .ok packet => pure packet
    | .error e => throw (elaborationRefusal ("refused (template-typing): open declaration " ++ key ++
        " has no typed template: " ++ e))
  let source := packet.source
  let rigidAt := fun (vars : List Nat) => { source with assumptions := { source.assumptions with rigid := vars } }
  match check (rigidAt rigidVariables) knotContext packet.fuel with
  | some _ => pure ()
  | none =>
    -- Which variable only an alias would accept: Self (the first) or Super (the second).
    if (check (rigidAt (rigidVariables.take 1)) knotContext packet.fuel).isSome then
      refuse ("refused (super-rigid): open declaration " ++ key ++ " uses super as a value of its " ++
        "Super bound row; Super ranges over every row beneath that HAS those members (a lower bound), so " ++
        "a value of type Super is not a value of the bound row. Read the members it needs (super.m), or " ++
        "extend super (Super with {...})")
    else
    match check source knotContext packet.fuel with
    | some _ => refuse ("refused (self-rigid): open declaration " ++ key ++ " uses self as a value of its " ++
        "Self bound row; Self ranges over every type that HAS that row (a lower bound), so a value of type " ++
        "Self is not a value of the row. Read the members it needs (self.m) instead")
    | none => refuse ("refused (template-typing): open declaration " ++ key ++
        " does not type-check against its declared bounds")

def checkTemplates (output : Output) (sourceEntry : String) (modules : List SourceModule) (typeFuel : Nat) :
    Except Diagnostic Unit :=
  output.templates.forM fun (key, rigidVariables, field) => checkTemplate output sourceEntry modules typeFuel key rigidVariables field

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

/-- The front end on parsed, checked modules: elaborate the selected declaration and project. -/
def lowerDecoded (modules : List SourceModule) (decoded : List ObjectiveBendElaborate.Module)
    (entryModule : Nat) (entryDefinition : String) (args projections limits : Json) (mode : String) :
    Except Diagnostic Lowering := do
  let (projectionList, typeFuel) ← options projections limits mode
  if modules.length > 64 then throw (elaborationRefusal "preview module capacity refused")
  let output ← match ObjectiveBendElaborate.elaborate decoded entryModule entryDefinition args mode with
    | .ok o => pure o
    | .error e => throw (elaborationRefusal e)
  let term ← project output.term projectionList
  let some entry := modules[entryModule]? | throw (elaborationRefusal "missing selected entry")
  let argumentCodec := if mode == "definition" then "unapplied-definition"
    else match args with
      | .arr _ => "legacy-canonical-nat-bool-record"
      | _ => "dregg.objective-bend.argument-values.v1"
  checkTemplates output (entry.name ++ "." ++ entryDefinition) modules typeFuel
  for (m, index) in decoded.zipIdx do
    if index != entryModule && !m.laws.isEmpty then
      throw (elaborationRefusal ("a law belongs to the package's entry module; " ++ m.name ++
        " is imported and declares " ++ toString m.laws.length ++ " law(s)"))
  let laws := (decoded[entryModule]?.map (·.laws)).getD []
  return ⟨output, term, entry.name ++ "." ++ entryDefinition, argumentCodec, mode, modules, limits, typeFuel, laws⟩

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

/-- The typing proposal for the selected term, or why there is none. -/
def Lowering.proposal (l : Lowering) : Except String Json :=
  ObjectiveBendElaborate.proposalJson { l.output with term := l.term }

/-- `dregg.objective-bend.typed-core.v3`: exactly the packet the checker reads. An unsupported
proposal is `{status: "unsupported", message}`. -/
def Lowering.packet (l : Lowering) : Json :=
  match l.proposal with
  | .error message => Json.mkObj [("status", toJson "unsupported"), ("message", toJson message)]
  | .ok proposal => packetJson proposal l.term l.sourceEntry l.modules l.typeFuel

/-! ## Acceptance: the checker on the front end's own packet -/

/-- With a typing proposal, the packet's `term` field is the rendering of the selected term. -/
theorem Lowering.packet_term (l : Lowering) {proposal : Json} (proposed : l.proposal = .ok proposal) :
    l.packet.getObjVal? "term" = .ok l.term.json := by
  unfold Lowering.packet
  rw [proposed]
  unfold packetJson
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

#assert_axioms Lowering.packet_term
#assert_axioms Accepted.source_eq_packet

end Minidregg.Compiler.ObjectiveBendFrontEnd
