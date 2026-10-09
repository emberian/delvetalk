/- Proof interface connecting the indexed finite schema to Mini's literal typing.
References are atomic; recursive input is consumed by the bounded normalizer,
so a recursive alias never demands an infinite inductive certificate. -/
import Delvetalk.PackageData
import Theory.ObjectiveBendFiniteDataTyping
namespace Delvetalk.PackageData
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendTyping
open Minidregg.Theory.ObjectiveBendDemandData
set_option autoImplicit false

mutual
inductive SchemaMatches (a : Assumptions) (graph : SchemaGraph) : Schema → Ty → Prop where
  | natural : SchemaMatches a graph .natural .natural
  | boolean : SchemaMatches a graph .boolean .boolean
  | label : SchemaMatches a graph .label .label
  | data : SchemaMatches a graph .data .data
  | record {fields : List (String × Ty × Schema)} {row : Ty} :
      SchemaFieldsMatch a graph fields row → SchemaMatches a graph (.record fields) row
  | variant {index : Nat} {types : VariantSchema} :
      graph.variants[index]? = some types →
      SchemaMatches a graph (.variant index) (.variant types.row)
  | reference {index target : Nat} {row : Ty} {types : VariantSchema} :
      a.alias index = some (.variant row) →
      graph.aliases[index]? = some (.variant target) →
      graph.variants[target]? = some types → types.row = row →
      SchemaMatches a graph (.reference index) (.variable index)
inductive SchemaFieldsMatch (a : Assumptions) (graph : SchemaGraph) :
    List (String × Ty × Schema) → Ty → Prop where
  | nil : SchemaFieldsMatch a graph [] .emptyRow
  | cons {name : String} {member row : Ty} {schema : Schema}
      {rest : List (String × Ty × Schema)} :
      SchemaMatches a graph schema member → SchemaFieldsMatch a graph rest row →
      member.isComputation = false →
      SchemaFieldsMatch a graph ((name,member,schema)::rest) (.field name member row)
end

/-- All static member-index lookups agree with the original finite row and
selected payload schema. This is established once for the actual final graph. -/
structure GraphSound (a : Assumptions) (graph : SchemaGraph) : Prop where
  members : ∀ (index : Nat) (types : VariantSchema) (label : String)
      (member : Ty) (schema : Schema),
      graph.variants[index]? = some types → types.members[label]? = some (member,schema) →
      ∃ fuel, types.row.lookup a.bounds fuel label = some member ∧
        member.isComputation = false ∧ SchemaMatches a graph schema member

/-- Atomic transparent references expose the same sum, while retaining the
exact declared variable type for the final erased conversion derivation. -/
theorem SchemaMatches.reference_conversion {a : Assumptions} {graph : SchemaGraph}
    {index target : Nat} {row : Ty} {types : VariantSchema}
    (alias : a.alias index = some (.variant row))
    (_target : graph.aliases[index]? = some (.variant target))
    (_row : graph.variants[target]? = some types) (sameRow : types.row = row) :
    sameType a (.variant types.row) (.variable index) = true := by
  rw [sameRow]
  exact transparent_sum_conversion alias
/-- Successful bounded monadic composition exposes each actual intermediate
allowance; proofs never substitute a fresh normalization budget. -/
theorem work_bind_ok {α β : Type} (first : Work α) (next : α → Work β)
    {fuel remaining : Nat} {output : β}
    (success : ((first >>= next).run fuel) = .ok (output,remaining)) :
    ∃ value middle, first.run fuel = .ok (value,middle) ∧
      (next value).run middle = .ok (output,remaining) := by
  simp only [Bind.bind, StateT.bind, StateT.run, Except.bind] at success
  cases equation : first fuel with
  | error error => simp [equation] at success
  | ok pair =>
      rcases pair with ⟨value,middle⟩
      refine ⟨value,middle,equation,?_⟩
      simpa only [StateT.run, equation] using success


theorem work_pure_output {α : Type} (value : α) {fuel remaining : Nat} {output : α}
    (success : ((pure value : Work α).run fuel) = .ok (output,remaining)) : output = value := by
  change Except.ok (value,fuel) = Except.ok (output,remaining) at success
  cases success
  rfl

end Delvetalk.PackageData
