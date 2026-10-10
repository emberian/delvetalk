/- Executable source evaluator. Every emitted step, yield, and value carries
   evidence from the independently defined, vendored Mini relation.
   Completeness of `inspect` (the stuck classification) is not yet proved. -/
import Theory.ObjectiveBendOpenRecursion
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendOpenRecursion
private def Option.toExcept (o : Option α) (error : String) : Except String α :=
  match o with
  | some v => .ok v
  | none => .error error
namespace Delvetalk

inductive View (t : Term) where
  | value : Value t → View t
  | step (next : Term) : Step t next → View t
  | yield (plan : Term) (frames : List SourceFrame) : Yields t plan frames → View t
  | stuck : View t

def inspect (t : Term) : View t :=
  match t with
  | .lam b => .value (.function b)
  | .nat n => .value (.natural n)
  | .boolean b => .value (.boolean b)
  | .label s => .value (.label s)
  | .record fs => .value (.record fs)
  | .specification m e => .value (.specification m e)
  | .prototype s v => .value (.prototype s v)
  | .inject k v => .value (.inject k v)
  | .bound _ | .refuse _ => .stuck
  | .perform p => .yield p [] (.perform p)
  | .done v => .step v (.done v)
  | .toData v => .step v (.toData v)
  | .textJoin l s => .step (textJoinExpansion l s) (.textJoin l s)
  | .mix a b => .step (mixBody a b) (.mix a b)
  | .fix s i => .step (.app (.app s (.fix s i)) i) (.fix s i)
  | .app f a => match f with
    | .lam b => .step (instantiate b a) (.beta b a)
    | .specification m e => .step (.app e a) (.applySpecification m e a)
    | f => match inspect f with
      | .step n h => .step (.app n a) (.application a h)
      | .yield p c h => .yield p (c ++ [.application a]) (.application a h)
      | _ => .stuck
  | .reflect x => match x with
    | .prototype s v => .step s (.reflectPrototype s v)
    | x => match inspect x with
      | .step n h => .step (.reflect n) (.reflectStep h)
      | .yield p c h => .yield p (c ++ [.reflect]) (.reflect h)
      | _ => .stuck
  | .metadata x => match x with
    | .specification m e => .step m (.metadataSpecification m e)
    | x => match inspect x with
      | .step n h => .step (.metadata n) (.metadataStep h)
      | .yield p c h => .yield p (c ++ [.metadata]) (.metadata h)
      | _ => .stuck
  | .project x => match x with
    | .prototype s v => .step v (.projectPrototype s v)
    | x => match inspect x with
      | .step n h => .step (.project n) (.projectStep h)
      | .yield p c h => .yield p (c ++ [.project]) (.project h)
      | _ => .stuck
  | .extend x fs => match x with
    | .record old => .step (.record (extendFields old fs)) (.extendRecord old fs)
    | x => match inspect x with
      | .step n h => .step (.extend n fs) (.extendTarget fs h)
      | .yield p c h => .yield p (c ++ [.extend fs]) (.extend fs h)
      | _ => .stuck
  | .get x key => match x with
    | .record fs => match h : fs.find? (fun f => f.1 == key) with
      | some (k,b) => if hk : k = key then
          .step b (.field fs key b (by simpa [hk] using h)) else .stuck
      | none => .stuck
    | x => match inspect x with
      | .step n h => .step (.get n key) (.target key h)
      | .yield p c h => .yield p (c ++ [.field key]) (.field key h)
      | _ => .stuck
  | .unary op a => match inspect a with
    | .step n h => .step (.unary op n) (.unaryArgument op h)
    | .yield p c h => .yield p (c ++ [.unary op]) (.unary op h)
    | .stuck => .stuck
    | .value ha => match h : unaryResult op a with
      | some n => .step n (.unaryPrimitive op a n ha h)
      | none => .stuck
  | .binary op l r => match inspect l with
    | .step n h => .step (.binary op n r) (.binaryLeft op r h)
    | .yield p c h => .yield p (c ++ [.binaryLeft op r]) (.binaryLeft op r h)
    | .stuck => .stuck
    | .value hl => match inspect r with
      | .step n h => .step (.binary op l n) (.binaryRight op l hl h)
      | .yield p c h => .yield p (c ++ [.binaryRight op l]) (.binaryRight op hl h)
      | .stuck => .stuck
      | .value hr => match h : primitiveResult op l r with
        | some n => .step n (.primitive op l r n hl hr h)
        | none => .stuck
  | .ifZero x z s => match x with
    | .nat 0 => .step z (.zero z s)
    | .nat (n+1) => .step (instantiate s (.nat n)) (.successor n z s)
    | x => match inspect x with
      | .step n h => .step (.ifZero n z s) (.condition z s h)
      | .yield p c h => .yield p (c ++ [.condition z s]) (.condition z s h)
      | _ => .stuck
  | .case x arms => match x with
    | .inject tag v => match h : arms.find? (fun a => a.1 == tag) with
      | some (k,b) => if hk : k = tag then
          .step (instantiate b v) (.caseInject tag v arms b (by simpa [hk] using h)) else .stuck
      | none => .stuck
    | x => match inspect x with
      | .step n h => .step (.case n arms) (.caseTarget arms h)
      | .yield p c h => .yield p (c ++ [.case arms]) (.case arms h)
      | _ => .stuck
  | .ifBool x a b => match x with
    | .boolean true => .step a (.ifTrue a b)
    | .boolean false => .step b (.ifFalse a b)
    | x => match inspect x with
      | .step n h => .step (.ifBool n a b) (.ifCondition a b h)
      | .yield p c h => .yield p (c ++ [.ifBool a b]) (.ifBool a b h)
      | _ => .stuck
termination_by sizeOf t

#assert_axioms inspect

private def primNames : List (String × Primitive) :=
  [("add",.add),("multiply",.multiply),("equal",.equal),("conjunction",.conjunction),
   ("labelEqual",.labelEqual),("subtract",.subtract),("divide",.divide),
   ("less",.less),("lessEqual",.lessEqual),("modulo",.modulo),("textConcat",.textConcat),
   ("textTake",.textTake),("textDrop",.textDrop),("textSpan",.textSpan),("textBreak",.textBreak),
   ("textHasAny",.textHasAny),("textCanonicalCompare",.textCanonicalCompare)]
private def primName (p : Primitive) : String :=
  ((primNames.find? (fun x => x.2 == p)).map Prod.fst).getD "unknown"

private def wireNat (j : Json) : Except String Nat := do
  let n ← j.getNat?
  if n <= 9007199254740991 then pure n else throw "integer exceeds wire range"

partial def decode (j : Json) : Except String Term := do
  let a ← j.getArr?
  let tag ← (← a[0]?.toExcept "empty term").getStr?
  let arity (n : Nat) : Except String Unit :=
    if a.size = n+1 then pure () else throw s!"{tag}: wrong arity"
  let arg (i : Nat) := (a[i]?.toExcept "missing argument")
  let t (i : Nat) := arg i >>= decode
  let str (i : Nat) := arg i >>= Json.getStr?
  let fields (i : Nat) : Except String (List (String × Term)) := do
    let fs ← (← arg i).getArr?
    fs.toList.mapM fun f => do
      let pair ← f.getArr?
      unless pair.size = 2 do throw "field/arm must be [name,term]"
      return (← pair[0]!.getStr?, ← decode pair[1]!)
  match tag with
  | "bound" => arity 1; return .bound (← wireNat (← arg 1))
  | "nat" =>
    arity 1
    let s ← str 1
    unless !s.isEmpty && s.toList.all (fun c => c >= '0' && c <= '9') &&
      (s == "0" || !s.startsWith "0") do throw "nat requires canonical decimal string"
    return .nat (← s.toNat?.toExcept "invalid natural")
  | "boolean" => arity 1; return .boolean (← (← arg 1).getBool?)
  | "label" => arity 1; return .label (← str 1)
  | "lam" => arity 1; return .lam (← t 1)
  | "app" => arity 2; return .app (← t 1) (← t 2)
  | "mix" => arity 2; return .mix (← t 1) (← t 2)
  | "fix" => arity 2; return .fix (← t 1) (← t 2)
  | "specification" => arity 2; return .specification (← t 1) (← t 2)
  | "prototype" => arity 2; return .prototype (← t 1) (← t 2)
  | "reflect" => arity 1; return .reflect (← t 1)
  | "metadata" => arity 1; return .metadata (← t 1)
  | "project" => arity 1; return .project (← t 1)
  | "binary" =>
    arity 3
    let p ← str 1
    let op ← ((primNames.find? (fun x => x.1 == p)).map Prod.snd).toExcept "unknown primitive"
    return .binary op (← t 2) (← t 3)
  | "extend" => arity 2; return .extend (← t 1) (← fields 2)
  | "record" => arity 1; return .record (← fields 1)
  | "get" => arity 2; return .get (← t 1) (← str 2)
  | "ifZero" => arity 3; return .ifZero (← t 1) (← t 2) (← t 3)
  | "inject" => arity 2; return .inject (← str 1) (← t 2)
  | "case" => arity 2; return .case (← t 1) (← fields 2)
  | "ifBool" => arity 3; return .ifBool (← t 1) (← t 2) (← t 3)
  | "perform" => arity 1; return .perform (← t 1)
  | "unary" =>
    arity 2
    let op ← match ← str 1 with
      | "natText" => pure UnaryPrimitive.natText
      | "textLength" => pure UnaryPrimitive.textLength
      | "sha256Text" => pure UnaryPrimitive.sha256Text
      | _ => throw "unknown unary primitive"
    return .unary op (← t 2)
  | "done" => arity 1; return .done (← t 1)
  | "toData" => arity 1; return .toData (← t 1)
  | "textJoin" => arity 2; return .textJoin (← t 1) (← t 2)
  | "refuse" => arity 1; return .refuse (← str 1)
  | _ => throw s!"unknown term constructor {tag}"

private def arr (tag : String) (args : List Json) : Json := .arr ((.str tag :: args).toArray)
partial def encode (t : Term) : Json :=
  let fields (fs : List (String × Term)) := Json.arr (fs.map (fun (k,v) => Json.arr #[.str k,encode v])).toArray
  match t with
  | .bound n => arr "bound" [toJson n]
  | .nat n => arr "nat" [.str (toString n)]
  | .boolean b => arr "boolean" [toJson b]
  | .label s => arr "label" [.str s]
  | .lam b => arr "lam" [encode b]
  | .app f a => arr "app" [encode f,encode a]
  | .mix l u => arr "mix" [encode l,encode u]
  | .fix s i => arr "fix" [encode s,encode i]
  | .specification m e => arr "specification" [encode m,encode e]
  | .prototype s v => arr "prototype" [encode s,encode v]
  | .reflect x => arr "reflect" [encode x]
  | .metadata x => arr "metadata" [encode x]
  | .project x => arr "project" [encode x]
  | .unary p a => arr "unary" [.str (match p with | .natText => "natText" | .textLength => "textLength" | .sha256Text => "sha256Text"),encode a]
  | .binary p l r => arr "binary" [.str (primName p),encode l,encode r]
  | .extend x fs => arr "extend" [encode x,fields fs]
  | .record fs => arr "record" [fields fs]
  | .get x k => arr "get" [encode x,.str k]
  | .ifZero n z s => arr "ifZero" [encode n,encode z,encode s]
  | .inject k v => arr "inject" [.str k,encode v]
  | .case x fs => arr "case" [encode x,fields fs]
  | .ifBool c a b => arr "ifBool" [encode c,encode a,encode b]
  | .perform p => arr "perform" [encode p]
  | .done v => arr "done" [encode v]
  | .toData v => arr "toData" [encode v]
  | .textJoin l s => arr "textJoin" [encode l, encode s]
  | .refuse r => arr "refuse" [.str r]

partial def run (t : Term) (fuel : Nat) (responses : List Term) (plans : Array Json := #[]) : String × Term × Array Json :=
  match inspect t with
  | .value _ => ("value", t, plans)
  | .stuck => ("stuck", t, plans)
  | .step n _ => if fuel == 0 then ("exhausted",t,plans) else run n (fuel-1) responses plans
  | .yield p frames _ =>
    let plans := plans.push (encode p)
    match responses with
    | [] => ("yield",t,plans)
    | response :: rest => run (plug frames response) fuel rest plans

def job (j : Json) : Except String Json := do
  let obj ← j.getObj?
  unless obj.toList.all (fun (k,_) => ["name","term","responses","fuel"].contains k) do
    throw "unknown job key"
  let name ← (← j.getObjVal? "name").getStr?
  let term ← decode (← j.getObjVal? "term")
  let fuel ← match j.getObjVal? "fuel" with
    | .ok f => wireNat f
    | .error _ => pure 10000
  let responses ← match j.getObjVal? "responses" with
    | .ok r => (← r.getArr?).toList.mapM decode
    | .error _ => pure []
  let (status, result, plans) := run term fuel responses
  let encoded := encode result
  let _ ← decode encoded
  for plan in plans do
    let _ ← decode plan
    pure ()
  return Json.mkObj [("name",.str name),("status",.str status),("term",encoded),("plans",.arr plans)]
-- Lean's JSON decoder substitutes U+FFFD for lone surrogate escapes. Reject
-- those before decoding so the common wire preserves exact scalar strings.
private def hex4 (a b c d : Char) : Option Nat := do
  let digit (c : Char) : Option Nat :=
    if c >= '0' && c <= '9' then some (c.toNat - 48)
    else if c >= 'a' && c <= 'f' then some (c.toNat - 87)
    else if c >= 'A' && c <= 'F' then some (c.toNat - 55)
    else none
  return (← digit a)*4096 + (← digit b)*256 + (← digit c)*16 + (← digit d)

def scalarEscapes : List Char → Bool
  | '\\' :: 'u' :: a :: b :: c :: d :: rest =>
    match hex4 a b c d with
    | none => false
    | some n =>
      if 55296 <= n && n <= 56319 then
        match rest with
        | '\\' :: 'u' :: e :: f :: g :: h :: tail =>
          match hex4 e f g h with
          | some m => 56320 <= m && m <= 57343 && scalarEscapes tail
          | none => false
        | _ => false
      else if 56320 <= n && n <= 57343 then false
      else scalarEscapes rest
  | '\\' :: _ :: rest => scalarEscapes rest
  | _ :: rest => scalarEscapes rest
  | [] => true

private def hexByte (b : UInt8) : Option Nat :=
  if b >= 48 && b <= 57 then some (b.toNat - 48)
  else if b >= 97 && b <= 102 then some (b.toNat - 87)
  else if b >= 65 && b <= 70 then some (b.toNat - 55)
  else none

private def hex4At (bytes : ByteArray) (i : Nat) : Option Nat := do
  return (← hexByte bytes[i]!)*4096 + (← hexByte bytes[i+1]!)*256 + (← hexByte bytes[i+2]!)*16 + (← hexByte bytes[i+3]!)

/-- `scalarEscapes` over the UTF-8 bytes of a line from byte `i` (every byte it inspects is
ASCII, and a multi-byte character inside a `\uXXXX` window makes both refuse). -/
def scalarEscapesFrom (bytes : ByteArray) (i : Nat) : Bool :=
  if h : i < bytes.size then
    if bytes[i] != 92 then scalarEscapesFrom bytes (i + 1)
    else if i + 1 < bytes.size && bytes[i+1]! == 117 && i + 5 < bytes.size then
      match hex4At bytes (i + 2) with
      | none => false
      | some n =>
        if 55296 <= n && n <= 56319 then
          if i + 11 < bytes.size && bytes[i+6]! == 92 && bytes[i+7]! == 117 then
            match hex4At bytes (i + 8) with
            | some m => 56320 <= m && m <= 57343 && scalarEscapesFrom bytes (i + 12)
            | none => false
          else false
        else if 56320 <= n && n <= 57343 then false
        else scalarEscapesFrom bytes (i + 6)
    else scalarEscapesFrom bytes (i + 2)
  else true
termination_by bytes.size - i

/-- `scalarEscapes line.toList`, without building the list. -/
def scalarEscapesText (line : String) : Bool := scalarEscapesFrom line.toUTF8 0
end Delvetalk
