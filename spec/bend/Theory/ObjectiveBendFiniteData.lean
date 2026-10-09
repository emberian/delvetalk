/- Finite first-order input values. These constructors contain no source code,
closures, activities, authority or executable metadata. Keeping this type below
both the demand machine and extraction avoids reifying admitted input as AST. -/
import Theory.ObjectiveBendOpenRecursion
namespace Minidregg.Theory.ObjectiveBendDemandData
inductive Data where
  | natural (value : Nat) | boolean (value : Bool) | label (value : String)
  | record (fields : List (String × Data))
  | variant (label : String) (payload : Data)
  deriving Repr

mutual
/-- Closed literal erasure for reference reasoning and kernel responses. Native
argument execution does not construct this representation. -/
def Data.term : Data → Minidregg.Theory.ObjectiveBendOpenRecursion.Term
  | .natural n => .nat n
  | .boolean b => .boolean b
  | .label s => .label s
  | .record fields => .record (fieldsTerm fields)
  | .variant label payload => .inject label payload.term
def fieldsTerm : List (String × Data) → List (String × Minidregg.Theory.ObjectiveBendOpenRecursion.Term)
  | [] => []
  | (name,value) :: rest => (name,value.term) :: fieldsTerm rest
end

mutual
/-- Well-formed finite data: every record's field names are distinct, at every
depth. Exactly the values the universal type `Data` admits. -/
def Data.wellFormed : Data → Bool
  | .natural _ | .boolean _ | .label _ => true
  | .record fields => (fields.map Prod.fst).eraseDups.length == fields.length && Data.fieldsWellFormed fields
  | .variant _ payload => payload.wellFormed
def Data.fieldsWellFormed : List (String × Data) → Bool
  | [] => true
  | (_, value) :: rest => value.wellFormed && Data.fieldsWellFormed rest
end
end Minidregg.Theory.ObjectiveBendDemandData
