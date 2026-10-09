/- Executed static finalization supplies the native admission graph invariant. -/
import Delvetalk.PackageDataAdmission
import Std.Data.HashMap.Lemmas
namespace Delvetalk.PackageData
open Minidregg.Theory.ObjectiveBendTypes
open Minidregg.Theory.ObjectiveBendTyping
set_option autoImplicit false

/-- Every retained alias has one checked completed target. This certificate is
shared by all recursive occurrences in the same immutable graph. -/
def AliasesSound (a : Assumptions) (graph : SchemaGraph) : Prop :=
  ∀ index, graph.aliases.contains index = true →
    SchemaMatches a graph (.reference index) (.variable index)

theorem aliasCertificate_sound {a : Assumptions} {graph : SchemaGraph} {index : Nat}
    (checked : aliasCertificate a graph index = true) :
    SchemaMatches a graph (.reference index) (.variable index) := by
  cases alias : a.alias index with
  | none => simp [aliasCertificate, alias] at checked
  | some bound =>
    cases bound <;> simp_all [aliasCertificate]
    rename_i row
    cases target : graph.aliases[index]? with
    | none => simp [aliasCertificate, alias, target] at checked
    | some targetSchema =>
      cases targetSchema <;> simp_all [aliasCertificate]
      rename_i targetIndex
      cases lookup : graph.variants[targetIndex]? with
      | none => simp [aliasCertificate, alias, target, lookup] at checked
      | some types =>
        have equality : types.row = row := of_decide_eq_true (by simpa [aliasCertificate, alias, target, lookup] using checked)
        exact .reference alias target lookup equality

theorem graphCertificate_aliasesSound {a : Assumptions} {graph : SchemaGraph} {depth : Nat}
    (checked : graphCertificate a graph depth = true) : AliasesSound a graph := by
  have aliases := (Bool.and_eq_true_iff.mp checked).2
  intro index present
  cases lookup : graph.aliases[index]? with
  | none => simp [Std.HashMap.contains_eq_isSome_getElem?, lookup] at present
  | some schema =>
    have entry : (index, schema) ∈ graph.aliases.toList := Std.HashMap.mem_toList_iff_getElem?_eq_some.mpr lookup
    exact aliasCertificate_sound (List.all_eq_true.mp aliases (index, schema) entry)

private theorem certificates_sound (a : Assumptions) (graph : SchemaGraph) (aliasesSound : AliasesSound a graph) (depth : Nat) :
    (∀ schema ty, schemaCertificate a graph depth schema ty = true → SchemaMatches a graph schema ty) ∧
    (∀ fields row, fieldsCertificate a graph depth fields row = true → SchemaFieldsMatch a graph fields row) := by
  induction depth with
  | zero => simp [schemaCertificate, fieldsCertificate]
  | succ depth ih =>
    constructor
    · intro schema ty checked
      cases schema with
      | natural => cases ty <;> simp_all [schemaCertificate]; exact .natural
      | boolean => cases ty <;> simp_all [schemaCertificate]; exact .boolean
      | label => cases ty <;> simp_all [schemaCertificate]; exact .label
      | data => cases ty <;> simp_all [schemaCertificate]; exact .data
      | record fields => exact .record (ih.2 fields ty checked)
      | variant index =>
        cases ty <;> simp_all [schemaCertificate]
        rename_i row
        cases lookup : graph.variants[index]? with
        | none => simp [schemaCertificate, lookup] at checked
        | some types =>
          have same : types.row = row := of_decide_eq_true (by simpa [schemaCertificate, lookup] using checked)
          subst row
          exact .variant lookup
      | reference index =>
        cases ty <;> simp_all [schemaCertificate]
        rename_i expected
        rcases checked with ⟨same, present⟩
        subst expected
        exact aliasesSound index present
    · intro fields row checked
      cases fields with
      | nil => cases row <;> simp_all [fieldsCertificate]; exact .nil
      | cons head rest =>
        rcases head with ⟨name, member, child⟩
        cases row <;> simp_all [fieldsCertificate]
        rename_i expected domain tail
        rcases checked with ⟨⟨⟨⟨names, members⟩, pure⟩, childChecked⟩, restChecked⟩
        subst expected
        subst domain
        exact .cons (ih.1 child member childChecked) (ih.2 rest tail restChecked) pure

theorem schemaCertificate_sound {a : Assumptions} {graph : SchemaGraph} {depth : Nat}
    {schema : Schema} {ty : Ty} (aliasesSound : AliasesSound a graph) (checked : schemaCertificate a graph depth schema ty = true) :
    SchemaMatches a graph schema ty :=
  (certificates_sound a graph aliasesSound depth).1 schema ty checked

/-- The once-built declared-row index has precisely the core first-match
lookup meaning. Its closed-row/uniqueness checks are executable. -/
theorem rowTypeIndex_lookup (bounds : Bounds) (depth : Nat) (row : Ty)
    (indexed : Std.HashMap String Ty) (label : String) (member : Ty)
    (built : rowTypeIndex depth row = some indexed)
    (found : indexed[label]? = some member) : row.lookup bounds depth label = some member := by
  induction depth generalizing row indexed with
  | zero => simp [rowTypeIndex] at built
  | succ depth ih =>
    cases row <;> simp [rowTypeIndex] at built
    · subst indexed
      simp at found
    · rename_i name domain tail
      cases tailIndex : rowTypeIndex depth tail with
      | none => simp [tailIndex] at built
      | some fields =>
        simp [tailIndex] at built
        have equality := built.2
        subst indexed
        by_cases same : name = label
        · subst label
          simp at found
          subst member
          simp [Ty.lookup]
        · have tailFound : fields[label]? = some member := by
            simpa [Std.HashMap.getElem?_insert, same] using found
          simpa [Ty.lookup, same] using ih tail fields tailIndex tailFound

theorem graphCertificate_sound {a : Assumptions} {graph : SchemaGraph} {depth : Nat}
    (checked : graphCertificate a graph depth = true) : GraphSound a graph := by
  have variants := (Bool.and_eq_true_iff.mp checked).1
  have aliasesSound := graphCertificate_aliasesSound checked
  refine ⟨?_⟩
  intro index types label member schema lookup memberLookup
  have present : (index, types) ∈ graph.variants.toList :=
    Std.HashMap.mem_toList_iff_getElem?_eq_some.mpr lookup
  have variantValid := List.all_eq_true.mp variants (index, types) present
  cases declaredIndex : rowTypeIndex depth types.row with
  | none => simp [declaredIndex] at variantValid
  | some declared =>
    have members : types.members.toList.all (fun (label, member, schema) =>
        decide (declared[label]? = some member) && !member.isComputation && schemaCertificate a graph depth schema member) = true := by
      simpa [declaredIndex] using variantValid
    have field : (label, member, schema) ∈ types.members.toList :=
      Std.HashMap.mem_toList_iff_getElem?_eq_some.mpr memberLookup
    have valid := List.all_eq_true.mp members (label, member, schema) field
    rcases Bool.and_eq_true_iff.mp valid with ⟨prior, child⟩
    rcases Bool.and_eq_true_iff.mp prior with ⟨row, pure⟩
    exact ⟨depth, rowTypeIndex_lookup a.bounds depth types.row declared label member declaredIndex (of_decide_eq_true row), (by simpa using pure), schemaCertificate_sound aliasesSound child⟩
/-- Acceptance of the executed static certificate establishes both obligations
without an assumed graph invariant. The returned allowance is the actual one. -/
theorem certifyGraph_sound {a : Assumptions} {depth : Nat} {ty : Ty}
    {graph output : SchemaGraph} {fuel remaining : Nat}
    (success : (certifyGraph a depth ty graph).run fuel = .ok (output, remaining)) :
    output = graph ∧ SchemaMatches a graph graph.root ty ∧ GraphSound a graph := by
  change ((spend (graphCertificateWork a graph depth ty) >>= fun _ =>
    if schemaCertificate a graph depth graph.root ty && graphCertificate a graph depth then
      pure graph else throw "typed data schema certificate refusal").run fuel) = .ok (output, remaining) at success
  obtain ⟨unit, middle, _, final⟩ := work_bind_ok _ _ success
  by_cases checked : (schemaCertificate a graph depth graph.root ty && graphCertificate a graph depth) = true
  · simp only [checked, Bool.true_eq, if_true] at final
    exact ⟨work_pure_output graph final,
      schemaCertificate_sound (graphCertificate_aliasesSound (Bool.and_eq_true_iff.mp checked).2) (Bool.and_eq_true_iff.mp checked).1,
      graphCertificate_sound (Bool.and_eq_true_iff.mp checked).2⟩
  · have falseCheck : (schemaCertificate a graph depth graph.root ty && graphCertificate a graph depth) = false := Bool.eq_false_iff.mpr checked
    simp only [falseCheck, Bool.false_eq_true, if_false] at final
    change Except.error "typed data schema certificate refusal" = Except.ok (output, remaining) at final
    cases final

/-- The actual declaration-order builder cannot return an uncertified graph.
Forward aliases are complete and associated with their declared source sums. -/
theorem schemaGraph_sound {a : Assumptions} {depth : Nat} {ty : Ty}
    {graph : SchemaGraph} {fuel remaining : Nat}
    (success : (schemaGraph a false depth ty).run fuel = .ok (graph, remaining)) :
    GraphSound a graph ∧ SchemaMatches a graph graph.root ty := by
  change (((buildSchema a false depth ty).run {} >>= fun pair =>
    certifyGraph a (depth + 1) ty ⟨pair.1, pair.2.aliases, pair.2.variants⟩).run fuel) =
      .ok (graph, remaining) at success
  obtain ⟨pair, middle, _, final⟩ := work_bind_ok _ _ success
  obtain ⟨equal, schemaMatched, sound⟩ := certifyGraph_sound final
  subst graph
  exact ⟨sound, schemaMatched⟩

#print axioms schemaGraph_sound

end Delvetalk.PackageData
