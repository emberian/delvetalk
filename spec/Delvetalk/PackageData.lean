/- Explicit, bounded data serialization for pure source packages. This does not
   change Mini's Plan/Activity types or its evaluator. The original checker still
   accepts every complete application, including generated injection annotations. -/
import Compiler.ObjectiveBendDataWire
import Theory.ObjectiveBendTyping
import Theory.ObjectiveBendFiniteDataTyping
import Std.Data.HashSet
import Std.Data.HashMap

namespace Delvetalk.PackageData
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendOpenRecursion
open Minidregg.Theory.ObjectiveBendDemandData (Data)
open Minidregg.Compiler.ObjectiveBendDataWire

abbrev Work := StateT Nat (Except String)

def spend (n : Nat := 1) : Work Unit := do
  let remaining ← get
  if n > remaining then throw "typed data work capacity"
  set (remaining - n)

def failDepth : Work α := throw "typed data nesting capacity"

/-- Only transparent recursive-sum aliases are in this initial profile. In
    particular a rigid bound is not an alias, nor is a recursive row tail. -/
def sumAlias (a : Assumptions) (index : Nat) : Work Ty := do
  spend
  match a.alias index with
  | some t@(.variant _) => pure t
  | _ => throw "typed data requires a transparent sum alias"

mutual
def shape (a : Assumptions) : Nat → List Nat → Ty → Work Unit
  | 0, _, _ => failDepth
  | depth + 1, seen, type => do
    spend
    match type with
    | .natural | .boolean | .label | .data => pure ()
    | .emptyRow | .field .. => rowShape a depth seen [] type
    | .variant row => rowShape a depth seen [] row
    | .variable index =>
        let bound ← sumAlias a index
        if !seen.contains index then shape a depth (index :: seen) bound
    | _ => throw "type is not serializable package data"
def rowShape (a : Assumptions) : Nat → List Nat → List String → Ty → Work Unit
  | 0, _, _, _ => failDepth
  | depth + 1, seen, names, type => do
    spend
    match type with
    | .emptyRow => pure ()
    | .field name member tail =>
        if names.contains name then throw "duplicate typed data field"
        shape a depth seen member
        rowShape a depth seen (name :: names) tail
    | _ => throw "typed data requires a finite closed row"
end

def exact (json : Json) (keys : List String) : Work Unit := do
  let fields ← json.getObj?
  let names := fields.toArray.toList.map Prod.fst
  spend names.length
  unless names.length == keys.length && names.all keys.contains do
    throw "typed data wire has missing or unknown fields"

/-- Strict framing, then the existing Data values. No ordinary record is guessed
    to be a variant, and every nested node shares the same work allowance. -/
def decode : Nat → Json → Work Data
  | 0, _ => failDepth
  | depth + 1, json => do
    spend
    match ← json.getObjValAs? String "tag" with
    | "natural" => exact json ["tag", "value"]; decodeNatural json
    | "boolean" => exact json ["tag", "value"]; return .boolean (← json.getObjValAs? Bool "value")
    | "label" => exact json ["tag", "value"]; return .label (← json.getObjValAs? String "value")
    | "record" =>
        exact json ["tag", "fields"]
        let fields ← (← json.getObjVal? "fields").getArr?
        let mut names : Std.HashSet String := {}
        let mut values := []
        for field in fields do
          exact field ["name", "value"]
          let name ← field.getObjValAs? String "name"
          if names.contains name then throw "duplicate typed data field"
          names := names.insert name
          values := (name, ← decode depth (← field.getObjVal? "value")) :: values
        return .record values.reverse
    | "variant" =>
        exact json ["tag", "label", "payload"]
        let value := Data.variant (← json.getObjValAs? String "label") (← decode depth (← json.getObjVal? "payload"))
        if (listItems? value).isSome then throw consChainRefusal
        return value
    | "list" =>
        exact json ["tag", "items"]
        let mut items := #[]
        for item in ← (← json.getObjVal? "items").getArr? do
          items := items.push (← decode depth item)
        return listData items
    | _ => throw "unknown typed data tag"

structure Quoted where
  term : Term
  annotations : List (List Nat × LambdaAnnotation) := []

def prefixAnnotations (n : Nat) (annotations : List (List Nat × LambdaAnnotation)) :=
  annotations.map fun (path, annotation) => (n :: path, annotation)

def members : Nat → Ty → Work (List (String × Ty))
  | 0, _ => failDepth
  | depth + 1, type => do
    spend
    match type with
    | .emptyRow => pure []
    | .field name member tail => return (name, member) :: (← members depth tail)
    | _ => throw "typed data requires a finite closed row"

/-- Construction policy only: all shape checks and work charges belong to the
shared traversal below. The validation sink carries no terms or annotations. -/
structure QuoteSink (α : Type) where
  natural : Nat → α
  boolean : Bool → α
  label : String → α
  emptyRecord : α
  field : α → String → α → α
  variant : String → Ty → Ty → α → α
  /-- A whole value at the universal type `Data`, already found well-formed. -/
  data : Data → α

/-- A bounded graph of the selected static schema. Recursive sums retain alias
references; their rows are checked/indexed once, rather than once per value node. -/
inductive Schema where
  | natural | boolean | label
  /-- The universal type: any well-formed finite value, admitted whole. -/
  | data
  | record (fields : List (String × Ty × Schema))
  | variant (index : Nat)
  | reference (index : Nat)

structure VariantSchema where
  row : Ty
  members : Std.HashMap String (Ty × Schema)

structure SchemaState where
  seen : Std.HashSet Nat := {}
  aliases : Std.HashMap Nat Schema := {}
  variants : Std.HashMap Nat VariantSchema := {}

abbrev SchemaBuild := StateT SchemaState Work

mutual
def buildSchema (a : Assumptions) (canonical : Bool) : Nat → Ty → SchemaBuild Schema
  | 0, _ => failDepth
  | depth + 1, ty => do
    spend
    match ty with
    | .natural => pure .natural
    | .boolean => pure .boolean
    | .label => pure .label
    | .data => pure .data
    | .emptyRow | .field .. =>
      let fields ← buildMembers a canonical depth {} ty
      if canonical then
        spend (fields.length * (fields.length.log2 + 1))
        return .record (fields.mergeSort (fun x y => x.1 ≤ y.1))
      return .record fields
    | .variant row =>
      let fields ← buildMembers a canonical depth {} row
      spend fields.length
      let state ← get
      let index := state.variants.size
      let indexed := fields.foldl (fun map (name, member, schema) => map.insert name (member, schema)) ({} : Std.HashMap String (Ty × Schema))
      set { state with variants := state.variants.insert index ⟨row, indexed⟩ }
      return .variant index
    | .variable index =>
      let state ← get
      if !state.seen.contains index then
        set { state with seen := state.seen.insert index }
        let bound ← sumAlias a index
        let schema ← buildSchema a canonical depth bound
        modify fun state => { state with aliases := state.aliases.insert index schema }
      return .reference index
    | _ => throw "type is not serializable package data"
def buildMembers (a : Assumptions) (canonical : Bool) : Nat → Std.HashSet String → Ty → SchemaBuild (List (String × Ty × Schema))
  | 0, _, _ => failDepth
  | depth + 1, names, ty => do
    spend
    match ty with
    | .emptyRow => pure []
    | .field name member tail =>
      if names.contains name then throw "duplicate typed data field"
      let child ← buildSchema a canonical depth member
      let fields ← buildMembers a canonical depth (names.insert name) tail
      return (name, member, child) :: fields
    | _ => throw "typed data requires a finite closed row"
end

structure SchemaGraph where
  root : Schema
  aliases : Std.HashMap Nat Schema
  variants : Std.HashMap Nat VariantSchema

/-- Metadata work includes complete compared type trees, not just graph nodes. -/
def typeMetadataWork : Ty → Nat
  | .natural | .boolean | .label | .emptyRow | .data => 1
  | .variable index | .custody index => 1 + (toString index).utf8ByteSize
  | .arrow _ _ domain result => 1 + typeMetadataWork domain + typeMetadataWork result
  | .field name member tail => 1 + name.utf8ByteSize + typeMetadataWork member + typeMetadataWork tail
  | .specification metadata extension | .prototype metadata extension =>
    1 + typeMetadataWork metadata + typeMetadataWork extension
  | .variant row => 1 + typeMetadataWork row
  | .computation plan response result =>
    1 + typeMetadataWork plan + typeMetadataWork response + typeMetadataWork result


mutual
/-- A final-graph check: references are associated with their actual completed
alias targets, without recursively traversing a cycle. -/
def schemaCertificate (a : Assumptions) (graph : SchemaGraph) : Nat → Schema → Ty → Bool
  | 0, _, _ => false
  | depth + 1, schema, ty => match schema, ty with
    | .natural, .natural | .boolean, .boolean | .label, .label | .data, .data => true
    | .record fields, row => fieldsCertificate a graph depth fields row
    | .variant index, .variant row => match graph.variants[index]? with
      | none => false
      | some types => decide (types.row = row)
    | .reference index, .variable expected =>
      decide (index = expected) && graph.aliases.contains index
    | _, _ => false

def fieldsCertificate (a : Assumptions) (graph : SchemaGraph) :
    Nat → List (String × Ty × Schema) → Ty → Bool
  | 0, _, _ => false
  | _ + 1, [], .emptyRow => true
  | depth + 1, (name,member,child)::rest, .field expected domain tail =>
    decide (name = expected) && decide (member = domain) &&
      !member.isComputation && schemaCertificate a graph depth child member &&
      fieldsCertificate a graph depth rest tail
  | _, _, _ => false
end

mutual
/-- Prepay both the certificate walk and the metadata walk used to count it.
No claim of linear work hides equality on a deeply nested type. -/
def schemaCertificateWork (a : Assumptions) (graph : SchemaGraph) : Nat → Schema → Ty → Nat
  | 0, _, _ => 1
  | depth + 1, schema, ty => 1 + match schema, ty with
    | .record fields, row => fieldsCertificateWork a graph depth fields row
    | .variant index, .variant row => typeMetadataWork row + match graph.variants[index]? with
      | none => 1
      | some types => typeMetadataWork types.row
    | .reference index, .variable expected =>
      (toString index).utf8ByteSize + (toString expected).utf8ByteSize + 1
    | _, _ => 1

def fieldsCertificateWork (a : Assumptions) (graph : SchemaGraph) :
    Nat → List (String × Ty × Schema) → Ty → Nat
  | 0, _, _ => 1
  | _ + 1, [], _ => 1
  | depth + 1, (name,member,child)::rest, .field expected domain tail =>
    1 + name.utf8ByteSize + expected.utf8ByteSize + typeMetadataWork member + typeMetadataWork domain +
      schemaCertificateWork a graph depth child member + fieldsCertificateWork a graph depth rest tail
  | _, _, _ => 1
end

/-- Alias identity and completion are checked once, independently of recursive
occurrences. Local schema certificates only require this certified index. -/
def aliasCertificate (a : Assumptions) (graph : SchemaGraph) (index : Nat) : Bool :=
  match a.alias index, graph.aliases[index]? with
  | some (.variant row), some (.variant target) => match graph.variants[target]? with
    | some types => decide (types.row = row)
    | none => false
  | _, _ => false

def aliasCertificateWork (a : Assumptions) (graph : SchemaGraph) (index : Nat) : Nat :=
  1 + (toString index).utf8ByteSize + a.bounds.length + a.rigid.length +
    match a.alias index, graph.aliases[index]? with
    | some (.variant row), some (.variant target) => typeMetadataWork row +
        match graph.variants[target]? with
        | none => 1
        | some types => typeMetadataWork types.row
    | _, _ => 1

/-- Each finite declared row is indexed once. Duplicate or open row fields
refuse; indexed checks never rescan a row for each alternative. -/
def rowTypeIndex : Nat → Ty → Option (Std.HashMap String Ty)
  | 0, _ => none
  | _ + 1, .emptyRow => some {}
  | depth + 1, .field name member tail => do
    let indexed ← rowTypeIndex depth tail
    if indexed.contains name then none else some (indexed.insert name member)
  | _, _ => none

def rowTypeIndexWork : Nat → Ty → Nat
  | 0, _ => 1
  | _ + 1, .emptyRow => 1
  | depth + 1, .field name _ tail => 1 + 2 * name.utf8ByteSize + rowTypeIndexWork depth tail
  | _, _ => 1

def graphCertificate (a : Assumptions) (graph : SchemaGraph) (depth : Nat) : Bool :=
  graph.variants.toList.all (fun (_, types) => match rowTypeIndex depth types.row with
    | none => false
    | some declared => types.members.toList.all (fun (label, member, schema) =>
      decide (declared[label]? = some member) && !member.isComputation &&
        schemaCertificate a graph depth schema member)) &&
  graph.aliases.toList.all (fun (index, _) => aliasCertificate a graph index)

def graphCertificateWork (a : Assumptions) (graph : SchemaGraph) (depth : Nat) (ty : Ty) : Nat :=
  2 * (1 + schemaCertificateWork a graph depth graph.root ty +
    graph.variants.toList.foldl (fun total (_, types) => total + 1 + rowTypeIndexWork depth types.row +
      match rowTypeIndex depth types.row with
      | none => 1
      | some declared => types.members.toList.foldl (fun subtotal (label, member, schema) => subtotal +
        1 + label.utf8ByteSize + typeMetadataWork member +
          (match declared[label]? with | some actual => typeMetadataWork actual | none => 1) +
          schemaCertificateWork a graph depth schema member) 0) 0 +
    graph.aliases.toList.foldl (fun total (index, _) => total + 1 + aliasCertificateWork a graph index) 0)

/-- Finalization checks the immutable completed graph, including every forward
reference target. No value traversal occurs here. -/
def certifyGraph (a : Assumptions) (depth : Nat) (ty : Ty) (graph : SchemaGraph) : Work SchemaGraph := do
  spend (graphCertificateWork a graph depth ty)
  if schemaCertificate a graph depth graph.root ty && graphCertificate a graph depth then
    pure graph
  else throw "typed data schema certificate refusal"

def schemaGraph (a : Assumptions) (canonical : Bool) (depth : Nat) (ty : Ty) : Work SchemaGraph := do
  let (root, state) ← (buildSchema a canonical depth ty).run {}
  let graph : SchemaGraph := ⟨root, state.aliases, state.variants⟩
  -- Canonical compact codecs sort records; the literal/native admission bridge
  -- uses declaration order and receives this exact final-graph certificate.
  if canonical then return graph
  certifyGraph a (depth + 1) ty graph

def dereference (graph : SchemaGraph) (schema : Schema) : Work Schema := do
  match schema with
  | .reference index =>
    spend
    let some schema := graph.aliases[index]? | throw "typed data requires a transparent sum alias"
    pure schema
  | schema => pure schema

mutual
/-- The work of deciding `Data.wellFormed`: every node once, and the pairwise
name comparison of each record (`eraseDups` is quadratic in its width). -/
def admissionWork : Data → Nat
  | .natural _ | .boolean _ | .label _ => 1
  | .record fields => 1 + fields.length * fields.length + admissionFieldsWork fields
  | .variant _ payload => 1 + admissionWork payload
def admissionFieldsWork : List (String × Data) → Nat
  | [] => 0
  | (_, value) :: rest => admissionWork value + admissionFieldsWork rest
end

def notWellFormed : String := "typed data value at Data repeats a record field"

def indexRecordFields (fields : List (String × Data)) : Work (Std.HashMap String Data) := do
  let mut indexed : Std.HashMap String Data := {}
  for (name, field) in fields do
    spend
    if indexed.contains name then throw "typed data record fields differ from declared type"
    indexed := indexed.insert name field
  return indexed

mutual
def quoteSchema {α : Type} (sink : QuoteSink α) (graph : SchemaGraph) : Nat → Data → Ty → Schema → Work α
  | 0, _, _, _ => failDepth
  | depth + 1, value, declared, schema => do
    spend
    match ← dereference graph schema, value with
    | .data, value =>
      spend (admissionWork value)
      if value.wellFormed then return sink.data value else throw notWellFormed
    | .natural, .natural n => return sink.natural n
    | .boolean, .boolean b => return sink.boolean b
    | .label, .label s => return sink.label s
    | .record types, .record fields =>
      if fields.length != types.length then throw "typed data record fields differ from declared type"
      let indexed ← indexRecordFields fields
      quoteRecordFields sink graph depth indexed types sink.emptyRecord
    | .variant index, .variant label payload =>
      spend 2
      let some types := graph.variants[index]? | throw "unresolved variant schema row"
      let some (ty, childSchema) := types.members[label]? | throw "typed data variant label is undeclared"
      let child ← quoteSchema sink graph depth payload ty childSchema
      return sink.variant label ty declared child
    | _, _ => throw "typed data value does not conform to declared type"

termination_by depth _ _ _ => (depth, 0, 0)
def quoteRecordFields {α : Type} (sink : QuoteSink α) (graph : SchemaGraph) (depth : Nat)
    (indexed : Std.HashMap String Data) (types : List (String × Ty × Schema)) (result : α) : Work α :=
  match types with
  | [] => pure result
  | (name,ty,childSchema)::rest => do
    spend
    let some field := indexed[name]? | throw "typed data record is missing a declared field"
    let child ← quoteSchema sink graph depth field ty childSchema
    quoteRecordFields sink graph depth indexed rest (sink.field result name child)
termination_by (depth, 1, types.length)
end

/-- Static preprocessing and actual value visits share one bounded allowance.
The same sink-independent traversal owns validation and quotation. -/
def quoteWith {α : Type} (sink : QuoteSink α) (a : Assumptions) (depth : Nat)
    (value : Data) (declared : Ty) : Work α := do
  let graph ← schemaGraph a false depth declared
  quoteSchema sink graph depth value declared graph.root

def termSink : QuoteSink Quoted where
  natural n := ⟨.nat n, []⟩
  boolean b := ⟨.boolean b, []⟩
  label s := ⟨.label s, []⟩
  emptyRecord := ⟨.record [], []⟩
  field prior name child :=
    match prior.term with
    | .record terms => ⟨.record (terms ++ [(name, child.term)]),
        prior.annotations ++ prefixAnnotations terms.length child.annotations⟩
    | _ => prior
  variant label ty declared child := ⟨.inject label child.term,
    ([], ⟨ty, declared, .unrestricted, .reusable⟩) :: prefixAnnotations 0 child.annotations⟩
  data value := ⟨.toData value.term, Minidregg.Theory.ObjectiveBendDemandData.shapeAnnotations value [0]⟩

def validationSink : QuoteSink Unit where
  natural _ := ()
  boolean _ := ()
  label _ := ()
  emptyRecord := ()
  field _ _ _ := ()
  variant _ _ _ _ := ()
  data _ := ()

/-- Record builders are reversed until attached to their parent. This preserves
the checked declaration's field order without allocating a literal term. -/
def finishNative : Data → Data
  | .record fields => .record fields.reverse
  | other => other

def nativeSink : QuoteSink Data where
  natural := .natural
  boolean := .boolean
  label := .label
  emptyRecord := .record []
  field prior name child := match prior with
    | .record fields => .record ((name, finishNative child) :: fields)
    | other => other
  variant name _ _ child := .variant name (finishNative child)
  -- Builders hold records reversed until their parent finishes them; a whole
  -- value is handed over in that same unfinished form.
  data value := finishNative value

def normalizeNative (a : Assumptions) (depth : Nat) (value : Data) (type : Ty) : Work Data := do
  return finishNative (← quoteWith nativeSink a depth value type)

/-- Input quotation retains injection annotations and canonical field order. -/
def quote (a : Assumptions) (depth : Nat) (value : Data) (declared : Ty) : Work Quoted :=
  quoteWith termSink a depth value declared

/-- Output validation executes exactly the quotation traversal and work charges,
while the sink discards constructors before any term tree is allocated. -/
def validate (a : Assumptions) (depth : Nat) (value : Data) (declared : Ty) : Work Unit :=
  quoteWith validationSink a depth value declared

def apply (source : AnnotatedTerm) (argument : Quoted) : AnnotatedTerm :=
  { source with term := .app source.term argument.term
                annotations := fun path => match path with
                  | 0 :: rest => source.annotations rest
                  | 1 :: rest => argument.annotations.lookup rest
                  | _ => none }

/-- A physical compact value is meaningful only relative to this exact checked
schema. Records carry canonical positional members; sums retain their label.
Naturals remain arbitrary precision canonical decimal strings. -/
def decodeCompactSchema (graph : SchemaGraph) : Nat → Schema → Json → Work Data
  | 0, _, _ => failDepth
  | depth + 1, schema, wire => do
    spend
    match ← dereference graph schema with
    | .data =>
      -- A universal value carries its own shape: the typed data wire (lists as arrays).
      let value ← decodeData depth wire
      spend (admissionWork value)
      unless value.wellFormed do throw notWellFormed
      return value
    | .natural =>
      let text ← wire.getStr?
      let some n := text.toNat? | throw "compact natural must be canonical decimal"
      unless toString n == text do throw "compact natural must be canonical decimal"
      return .natural n
    | .boolean => return .boolean (← wire.getBool?)
    | .label => return .label (← wire.getStr?)
    | .record types =>
      let values ← wire.getArr?
      unless values.size == types.length do throw "compact record arity differs from declared type"
      let mut fields := []
      for ((name, _, schema), child) in types.toArray.zip values do
        spend
        fields := (name, ← decodeCompactSchema graph depth schema child) :: fields
      return .record fields.reverse
    | .variant index =>
      let values ← wire.getArr?
      unless values.size == 2 do throw "compact variant requires label and payload"
      let label ← values[0]!.getStr?
      spend 2
      let some types := graph.variants[index]? | throw "unresolved variant schema row"
      let some (_, schema) := types.members[label]? | throw "compact variant label is undeclared"
      return .variant label (← decodeCompactSchema graph depth schema values[1]!)
    | .reference _ => throw "unresolved compact schema alias"

def encodeCompactSchema (graph : SchemaGraph) : Nat → Schema → Data → Work Json
  | 0, _, _ => failDepth
  | depth + 1, schema, value => do
    spend
    match value, ← dereference graph schema with
    | value, .data =>
      spend (admissionWork value)
      unless value.wellFormed do throw notWellFormed
      return dataJson value
    | .natural n, .natural => return toJson (toString n)
    | .boolean b, .boolean => return toJson b
    | .label text, .label => return toJson text
    | .record fields, .record types =>
      unless fields.length == types.length do throw "compact record fields differ from declared type"
      let mut indexed : Std.HashMap String Data := {}
      for (name, child) in fields do
        spend
        if indexed.contains name then throw "duplicate typed data field"
        indexed := indexed.insert name child
      let mut values := #[]
      for (name, _, schema) in types do
        spend
        let some child := indexed[name]? | throw "compact record is missing a declared field"
        values := values.push (← encodeCompactSchema graph depth schema child)
      return .arr values
    | .variant label payload, .variant index =>
      spend 2
      let some types := graph.variants[index]? | throw "unresolved variant schema row"
      let some (_, schema) := types.members[label]? | throw "compact variant label is undeclared"
      return .arr #[toJson label, ← encodeCompactSchema graph depth schema payload]
    | _, _ => throw "typed data value does not conform to declared type"

def decodeCompact (a : Assumptions) (depth : Nat) (declared : Ty) (wire : Json) : Work Data := do
  let graph ← schemaGraph a true depth declared
  decodeCompactSchema graph depth graph.root wire

def encodeCompact (a : Assumptions) (depth : Nat) (declared : Ty) (value : Data) : Work Json := do
  let graph ← schemaGraph a true depth declared
  encodeCompactSchema graph depth graph.root value

def prepareWith {α : Type} (read : Assumptions → Ty → α → Work Data) (packet : Json)
    (arguments : Work (Array α)) : Work (AnnotatedTerm × Ty × Nat) := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let mut source := decoded.source
  let some initial := check source [] decoded.fuel | throw "typed package refused by Mini type checker"
  let mut type := initial.type
  for argument in (← arguments) do
    let .arrow _ _ domain codomain := callable type | throw "typed package argument requires a function"
    shape source.assumptions 256 [] domain
    let value ← read source.assumptions domain argument
    let quoted ← quote source.assumptions 256 value domain
    source := apply source quoted
    let some checked := check source [] decoded.fuel | throw "applied typed package refused by Mini type checker"
    type := checked.type
    unless type == codomain do throw "typed package application result mismatch"
  shape source.assumptions 256 [] type
  return (source, type, decoded.fuel)

def prepare (packet arguments : Json) : Work (AnnotatedTerm × Ty × Nat) := do
  prepareWith (fun _ _ => decode 256) packet (do return ← arguments.getArr?)

def prepareValues (packet : Json) (arguments : Array Data) : Work (AnnotatedTerm × Ty × Nat) :=
  -- Quotation is itself the complete bounded native value/type admission.
  -- Repeating an untyped native walk first validates no additional fact.
  prepareWith (fun _ _ value => pure value) packet (pure arguments)

structure NativePreparation where
  source : AnnotatedTerm
  resultType : Ty
  arguments : Array Data
  fuel : Nat

/-- Every argument retains the core callable/quantity gate, then one shared
finite-data normalization allowance. No applied source syntax is constructed. -/
def prepareNativeArguments {α : Type} (read : Assumptions → Ty → α → Work Data)
    (a : Assumptions) (type : Ty) : List α → Work (Ty × List Data)
  | [] => pure (type, [])
  | argument :: rest => do
    let .arrow _ quantity domain codomain := callable type
      | throw "typed package argument requires a function"
    unless argumentAllowed a quantity [] domain [] do
      throw "applied typed package refused by Mini type checker"
    let value ← read a domain argument
    let normalized ← normalizeNative a 256 value domain
    let (resultType, values) ← prepareNativeArguments read a codomain rest
    return (resultType, normalized :: values)

/-- Check the closed source once, then admit finite native arguments against
each selected domain and the same quantity gate used by core application.
The machine receives actual values rather than reconstructed literal syntax. -/
def prepareNativeWith {α : Type} (read : Assumptions → Ty → α → Work Data)
    (packet : Json) (arguments : Work (Array α)) : Work NativePreparation := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let source := decoded.source
  let some initial := check source [] decoded.fuel | throw "typed package refused by Mini type checker"
  let (type, normalized) ← prepareNativeArguments read source.assumptions initial.type (← arguments).toList
  shape source.assumptions 256 [] type
  return ⟨source, type, normalized.toArray, decoded.fuel⟩

def prepareNative (packet : Json) (arguments : Array Data) : Work NativePreparation :=
  prepareNativeWith (fun _ _ value => pure value) packet (pure arguments)

def prepareNativeWire (packet arguments : Json) : Work NativePreparation :=
  prepareNativeWith (fun _ _ => decode 256) packet (do return ← arguments.getArr?)

def prepareNativeCompact (packet arguments : Json) : Work NativePreparation :=
  prepareNativeWith (fun a ty => decodeCompact a 256 ty) packet (do return ← arguments.getArr?)

def prepareCompact (packet arguments : Json) : Work (AnnotatedTerm × Ty × Nat) :=
  prepareWith (fun a ty => decodeCompact a 256 ty) packet (do return ← arguments.getArr?)

/-- Select only explicit structural positions from a checked artifact's type. -/
def select (a : Assumptions) (type : Ty) (path : Json) : Work Ty := do
  let mut selected := type
  let steps ← path.getArr?
  if steps.size > 64 then throw "typed data path capacity"
  for step in steps do
    spend
    match step.getStr? with
    | .ok direction =>
        let .arrow _ _ domain codomain := callable selected | throw "type path requires an arrow"
        selected ← if direction == "domain" then pure domain
          else if direction == "codomain" then pure codomain else throw "unknown type path step"
    | .error _ =>
        exact step ["field"]
        let name ← step.getObjValAs? String "field"
        let row ← match selected with
          | .variable i => sumAlias a i
          | other => pure other
        let some member := (← members 256 row).lookup name | throw "type path field is absent"
        selected := member
  return selected

/-- Paired guarded type graphs using the checker's canonical row order. Shape
    validation precedes this comparison, so canonical shadowing cannot hide a
    duplicate field. Alias indices belong to their own packet. -/
def equivalent (left right : Assumptions) : Nat → List (Ty × Ty) → Ty → Ty → Work Bool
  | 0, _, _, _ => failDepth
  | depth + 1, seen, a, b => do
    spend
    let a := a.canonical
    let b := b.canonical
    if seen.contains (a, b) then return true
    let next := (a, b) :: seen
    match a, b with
    | .variable i, _ => equivalent left right depth next (← sumAlias left i) b
    | _, .variable i => equivalent left right depth next a (← sumAlias right i)
    | .natural, .natural | .boolean, .boolean | .label, .label | .emptyRow, .emptyRow
    | .data, .data => return true
    | .field an am aTail, .field bn bm bTail =>
        if an != bn then return false
        if !(← equivalent left right depth next am bm) then return false
        equivalent left right depth next aTail bTail
    | .variant ar, .variant br => equivalent left right depth next ar br
    | _, _ => return false

/-- Closed source choices retain the type of each configured child model. No
existential box or source-authored schema participates in allocation admission. -/
def allocationLeaves (a : Assumptions) : Nat → Ty → Work (List Ty)
  | 0, _ => failDepth
  | depth + 1, type => do
    spend
    match type with
    | .variable i => allocationLeaves a depth (← sumAlias a i)
    | .variant row =>
        let alternatives ← members depth row
        if alternatives.isEmpty then throw "allocation choice must have alternatives"
        let mut leaves := []
        for (_, payload) in alternatives do
          leaves := leaves ++ (← allocationLeaves a depth payload)
        return leaves
    | .field .. | .emptyRow =>
        let fields ← members depth type
        let names := fields.map Prod.fst
        let expected := ["name", "protocol", "law"] ++ (if names.contains "initial" then ["initial"] else [])
        unless names.length == expected.length && expected.all names.contains do
          throw "allocation requires name, protocol, law and optional typed initial"
        unless fields.lookup "name" == some .label do throw "allocation name requires String"
        for key in ["protocol", "law"] do
          let some member := fields.lookup key | throw "allocation descriptor field missing"
          shape a depth [] member
        if let some initial := fields.lookup "initial" then
          match initial with
          | .field .. | .emptyRow => shape a depth [] initial
          | _ => throw "allocation initial requires a closed record model"
        return [type]
    | _ => throw "allocation requires a closed descriptor or finite source choice"

def allocationListType (a : Assumptions) (type : Ty) : Work Ty := do
  spend
  let expanded ← match type with
    | .variable i => sumAlias a i
    | other => pure other
  let .variant row := expanded | throw "allocations require a nil/cons list"
  let cases ← members 256 row
  unless cases.length == 2 && (cases.map Prod.fst).all ["nil", "cons"].contains do
    throw "allocations require exactly nil/cons alternatives"
  unless cases.lookup "nil" == some .emptyRow do throw "allocation nil requires an empty payload"
  let some cons := cases.lookup "cons" | throw "allocation cons is missing"
  let fields ← members 256 cons
  unless fields.length == 2 && (fields.map Prod.fst).all ["head", "tail"].contains do
    throw "allocation cons requires head/tail"
  let some head := fields.lookup "head" | throw "allocation head is missing"
  let some tail := fields.lookup "tail" | throw "allocation tail is missing"
  unless tail.canonical == type.canonical do throw "allocation tail must retain its list type"
  discard (allocationLeaves a 256 head)
  return head

def allocationLeaf (a : Assumptions) : Nat → Data → Ty → Work (Data × Ty)
  | 0, _, _ => failDepth
  | depth + 1, value, type => do
    spend
    match type with
    | .variable i => allocationLeaf a depth value (← sumAlias a i)
    | .variant row =>
        let .variant label payload := value | throw "allocation choice requires its checked variant"
        let some member := (← members depth row).lookup label | throw "allocation choice alternative missing"
        allocationLeaf a depth payload member
    | .field .. | .emptyRow =>
        let .record _ := value | throw "allocation descriptor requires a checked record"
        return (value, type)
    | _ => throw "invalid allocation descriptor type"

def allocationElements (a : Assumptions) (type : Ty) (value : Data)
    (limit : Nat := 32) : Work (List (Data × Ty)) := do
  let head ← allocationListType a type
  let mut cursor := value
  let mut result := []
  let mut remaining := limit
  repeat
    spend
    match cursor with
    | .variant "nil" (.record []) => return result.reverse
    | .variant "cons" (.record fields) =>
        if remaining == 0 then throw "allocation collection capacity"
        unless fields.length == 2 && (fields.map Prod.fst).all ["head", "tail"].contains do
          throw "allocation cons requires checked head/tail"
        let some item := fields.lookup "head" | throw "allocation head missing"
        let some tail := fields.lookup "tail" | throw "allocation tail missing"
        result := (← allocationLeaf a 256 item head) :: result
        cursor := tail
        remaining := remaining - 1
    | _ => throw "allocation collection requires checked nil/cons"

end Delvetalk.PackageData
