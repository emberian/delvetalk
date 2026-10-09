/- Explicit, bounded data serialization for pure source packages. This does not
   change Mini's Plan/Activity types or its evaluator. The original checker still
   accepts every complete application, including generated injection annotations. -/
import Compiler.ObjectiveBendDataWire
import Theory.ObjectiveBendTyping
import Std.Data.HashSet

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
    | .natural | .boolean | .label => pure ()
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
        return .variant (← json.getObjValAs? String "label") (← decode depth (← json.getObjVal? "payload"))
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

/-- Traverse finite values against their DECLARED type. A sink cannot alter
acceptance, rejection or accounting: its operations are pure constructors. -/
def quoteWith {α : Type} (sink : QuoteSink α) (a : Assumptions) : Nat → Data → Ty → Work α
  | 0, _, _ => failDepth
  | depth + 1, value, declared => do
    spend
    let expanded ← match declared with
      | .variable index => sumAlias a index
      | other => pure other
    match value, expanded with
    | .natural n, .natural => return sink.natural n
    | .boolean b, .boolean => return sink.boolean b
    | .label s, .label => return sink.label s
    | .record fields, row =>
        let types ← members depth row
        if fields.length != types.length || (fields.map Prod.fst).eraseDups.length != fields.length then
          throw "typed data record fields differ from declared type"
        let mut result := sink.emptyRecord
        for (name, ty) in types do
          let some field := fields.lookup name | throw "typed data record is missing a declared field"
          let child ← quoteWith sink a depth field ty
          result := sink.field result name child
        return result
    | .variant label payload, .variant row =>
        let types ← members depth row
        let some ty := types.lookup label | throw "typed data variant label is undeclared"
        let child ← quoteWith sink a depth payload ty
        return sink.variant label ty declared child
    | _, _ => throw "typed data value does not conform to declared type"

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

def validationSink : QuoteSink Unit where
  natural _ := ()
  boolean _ := ()
  label _ := ()
  emptyRecord := ()
  field _ _ _ := ()
  variant _ _ _ _ := ()

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

/-- Native values share the strict decoder's depth, duplicate checks and work
charges without encoding a JSON tree merely to decode it again. -/
def admitValue : Nat → Data → Work Data
  | 0, _ => failDepth
  | depth + 1, value => do
    spend
    match value with
    | .natural _ | .boolean _ | .label _ => spend 2; return value
    | .variant _ payload =>
      spend 3
      let _ ← admitValue depth payload
      return value
    | .record fields =>
      spend 2
      let mut names : Std.HashSet String := {}
      for (name, child) in fields do
        spend 2
        if names.contains name then throw "duplicate typed data field"
        names := names.insert name
        let _ ← admitValue depth child
      return value

def prepareWith {α : Type} (read : α → Work Data) (packet : Json)
    (arguments : Array α) : Work (AnnotatedTerm × Ty × Nat) := do
  let decoded ← decodePacket packet
  unless decoded.context.isEmpty do throw "package must have a closed context"
  let mut source := decoded.source
  let some initial := check source [] decoded.fuel | throw "typed package refused by Mini type checker"
  let mut type := initial.type
  for argument in arguments do
    let .arrow _ _ domain codomain := callable type | throw "typed package argument requires a function"
    shape source.assumptions 256 [] domain
    let value ← read argument
    let quoted ← quote source.assumptions 256 value domain
    source := apply source quoted
    let some checked := check source [] decoded.fuel | throw "applied typed package refused by Mini type checker"
    type := checked.type
    unless type == codomain do throw "typed package application result mismatch"
  shape source.assumptions 256 [] type
  return (source, type, decoded.fuel)

def prepare (packet arguments : Json) : Work (AnnotatedTerm × Ty × Nat) := do
  prepareWith (decode 256) packet (← arguments.getArr?)

def prepareValues (packet : Json) (arguments : Array Data) : Work (AnnotatedTerm × Ty × Nat) :=
  prepareWith (admitValue 256) packet arguments

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
    | .natural, .natural | .boolean, .boolean | .label, .label | .emptyRow, .emptyRow => return true
    | .field an am aTail, .field bn bm bTail =>
        if an != bn then return false
        if !(← equivalent left right depth next am bm) then return false
        equivalent left right depth next aTail bTail
    | .variant ar, .variant br => equivalent left right depth next ar br
    | _, _ => return false

end Delvetalk.PackageData
