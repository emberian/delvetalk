/- Checkpoint codec, edition v3: a checkpoint that references its program, every address
relative to its holder.

A suspended activity's heap is mostly closures over the program's own terms, identical in
every checkpoint of the package (a Garden prose suspension was 20,338 tokens, 17,549 of them
program terms). A checkpoint encodes the machine `State` against a `Dictionary` the decoder
rebuilds from the program alone (the packet's term, which the host holds by pin):

- a term is one token, `nat (i+1)` for the program's `i`th subterm (preorder), or `nat 0`
  followed by the inline term encoding (`ObjectiveBendCheckpoint.encodeTerm`) when it is not
  one (an argument's or a response's literal);
- an environment is one token, `nat (i+1)` for the checkpoint's `i`th distinct
  environment, listed once in a header;
- a string is `str i` for the dictionary's `i`th string (the program's strings, then the
  checkpoint's own, listed once after the edition): `internStrings` is a renaming of
  tokens that `resolveStrings` inverts whatever the tokens;
- before encoding, every address is written relative to its holder (`relativeState`, below),
  so a region of the heap that moved as a whole encodes identically.

Every reference is emitted only after checking that it names exactly the value (the hints
that find candidates are unverified accelerators), so the round trip
(`ObjectiveBendCheckpointV3RoundTrip.plainV3_roundTrip`, then `stateV3_roundTrip`) holds for
every dictionary and every state. Earlier editions do not decode. -/
import Theory.ObjectiveBendCheckpoint
import Std.Data.HashMap
namespace Delvetalk.Theory.ObjectiveBendCheckpoint
open ObjectiveBendOpenRecursion ObjectiveBendDemandMachine
open Delvetalk.Theory.ObjectiveBendDemandData (Data)
set_option autoImplicit false

/-- Term equality that answers at once for one object: a checkpoint's closures hold the
program's own subterms, so a reference check is usually a pointer comparison. Otherwise it
compares the terms' v1 encodings, which decide equality (`termEq_eq` in the round-trip file:
`decodeTerm` inverts `encodeTerm`). -/
def termEq (a b : Term) : Bool := withPtrEq a b (fun _ => decide (encodeTerm a = encodeTerm b)) (by intro h; subst h; simp)

/-! ## The dictionary -/

def mix (h : UInt64) (x : UInt64) : UInt64 := mixHash h x

mutual
/-- A structural hash of a term (only a hint: every use is checked). -/
def termHash : Term → UInt64
  | .bound i => mix 1 (hash i)
  | .lam b => mix 2 (termHash b)
  | .app a b => mix (mix 3 (termHash a)) (termHash b)
  | .mix a b => mix (mix 4 (termHash a)) (termHash b)
  | .fix a b => mix (mix 5 (termHash a)) (termHash b)
  | .specification a b => mix (mix 6 (termHash a)) (termHash b)
  | .prototype a b => mix (mix 7 (termHash a)) (termHash b)
  | .reflect a => mix 8 (termHash a)
  | .metadata a => mix 9 (termHash a)
  | .project a => mix 10 (termHash a)
  | .nat n => mix 11 (hash n)
  | .boolean b => mix 12 (hash b)
  | .label s => mix 13 (hash s)
  | .binary p a b => mix (mix (mix 14 (hash (primitiveCode p))) (termHash a)) (termHash b)
  | .unary p a => mix (mix 15 (hash (unaryCode p))) (termHash a)
  | .extend a fs => mix (mix 16 (termHash a)) (fieldsHash fs)
  | .record fs => mix 17 (fieldsHash fs)
  | .get a n => mix (mix 18 (termHash a)) (hash n)
  | .ifZero a b c => mix (mix (mix 19 (termHash a)) (termHash b)) (termHash c)
  | .inject l a => mix (mix 20 (hash l)) (termHash a)
  | .case a fs => mix (mix 21 (termHash a)) (fieldsHash fs)
  | .ifBool a b c => mix (mix (mix 22 (termHash a)) (termHash b)) (termHash c)
  | .perform a => mix 23 (termHash a)
  | .done a => mix 24 (termHash a)
  | .toData a => mix 25 (termHash a)
  | .textJoin a b => mix (mix 26 (termHash a)) (termHash b)
  | .refuse r => mix 27 (hash r)
  | .relationCount a => mix 28 (termHash a)
  | .relationLookup a k b => mix (mix (mix 29 (termHash a)) (hash k)) (termHash b)
def fieldsHash : List (String × Term) → UInt64
  | [] => 7
  | (n, t) :: rest => mix (mix (hash n) (termHash t)) (fieldsHash rest)
end

/-- What a checkpoint is encoded against: the program's subterms in preorder and its
strings in order of first appearance, with lookup hints for the encoder. The decoder uses
only `terms` and `strings`. -/
structure Dictionary where
  terms : Array Term := #[]
  strings : Array String := #[]
  termHint : Std.HashMap UInt64 (List Nat) := {}
  stringHint : Std.HashMap String Nat := {}
  /-- The field-name lists of the program's records and extensions, in preorder: a record
  value built by one carries exactly its names. -/
  nameLists : Array (List String) := #[]
  nameHint : Std.HashMap (List String) Nat := {}
  deriving Inhabited

namespace Dictionary

def addNames (d : Dictionary) (fields : List (String × Term)) : Dictionary :=
  let names := fields.map (·.1)
  if names.length < 2 || d.nameHint.contains names then d
  else { d with nameLists := d.nameLists.push names, nameHint := d.nameHint.insert names d.nameLists.size }

def addString (d : Dictionary) (s : String) : Dictionary :=
  if d.stringHint.contains s then d
  else { d with strings := d.strings.push s, stringHint := d.stringHint.insert s d.strings.size }

mutual
/-- Add `t` and its subterms in preorder; returns `t`'s hash, computed once per node. Its
result is only ever a hint (every reference is checked), so it needs no proof. -/
partial def addTerm (d : Dictionary) : Term → Dictionary × UInt64
  | t =>
    let index := d.terms.size
    let d := { d with terms := d.terms.push t }
    let (d, h) := match t with
      | .bound i => (d, mix 1 (hash i))
      | .lam b => let (d, x) := addTerm d b; (d, mix 2 x)
      | .app a b => let (d, x) := addTerm d a; let (d, y) := addTerm d b; (d, mix (mix 3 x) y)
      | .mix a b => let (d, x) := addTerm d a; let (d, y) := addTerm d b; (d, mix (mix 4 x) y)
      | .fix a b => let (d, x) := addTerm d a; let (d, y) := addTerm d b; (d, mix (mix 5 x) y)
      | .specification a b => let (d, x) := addTerm d a; let (d, y) := addTerm d b; (d, mix (mix 6 x) y)
      | .prototype a b => let (d, x) := addTerm d a; let (d, y) := addTerm d b; (d, mix (mix 7 x) y)
      | .reflect a => let (d, x) := addTerm d a; (d, mix 8 x)
      | .metadata a => let (d, x) := addTerm d a; (d, mix 9 x)
      | .project a => let (d, x) := addTerm d a; (d, mix 10 x)
      | .nat n => (d, mix 11 (hash n))
      | .boolean b => (d, mix 12 (hash b))
      | .label s => (d.addString s, mix 13 (hash s))
      | .binary p a b => let (d, x) := addTerm d a; let (d, y) := addTerm d b
          (d, mix (mix (mix 14 (hash (primitiveCode p))) x) y)
      | .unary p a => let (d, x) := addTerm d a; (d, mix (mix 15 (hash (unaryCode p))) x)
      | .extend a fs => let (d, x) := addTerm d a; let (d, y) := addFields (d.addNames fs) fs; (d, mix (mix 16 x) y)
      | .record fs => let (d, y) := addFields (d.addNames fs) fs; (d, mix 17 y)
      | .get a n => let (d, x) := addTerm (d.addString n) a; (d, mix (mix 18 x) (hash n))
      | .ifZero a b c => let (d, x) := addTerm d a; let (d, y) := addTerm d b; let (d, z) := addTerm d c
          (d, mix (mix (mix 19 x) y) z)
      | .inject l a => let (d, x) := addTerm (d.addString l) a; (d, mix (mix 20 (hash l)) x)
      | .case a fs => let (d, x) := addTerm d a; let (d, y) := addFields d fs; (d, mix (mix 21 x) y)
      | .ifBool a b c => let (d, x) := addTerm d a; let (d, y) := addTerm d b; let (d, z) := addTerm d c
          (d, mix (mix (mix 22 x) y) z)
      | .perform a => let (d, x) := addTerm d a; (d, mix 23 x)
      | .done a => let (d, x) := addTerm d a; (d, mix 24 x)
      | .toData a => let (d, x) := addTerm d a; (d, mix 25 x)
      | .textJoin a b => let (d, x) := addTerm d a; let (d, y) := addTerm d b; (d, mix (mix 26 x) y)
      | .refuse r => (d.addString r, mix 27 (hash r))
      | .relationCount a => let (d, x) := addTerm d a; (d, mix 28 x)
      | .relationLookup a k b =>
        let (d, x) := addTerm (k.foldl Dictionary.addString d) a; let (d, y) := addTerm d b
        (d, mix (mix (mix 29 x) (hash k)) y)
    ({ d with termHint := d.termHint.insert h (index :: d.termHint.getD h []) }, h)
partial def addFields (d : Dictionary) : List (String × Term) → Dictionary × UInt64
  | [] => (d, 7)
  | (n, t) :: rest =>
    let (d, x) := addTerm (d.addString n) t
    let (d, y) := addFields d rest
    (d, mix (mix (hash n) x) y)
end

/-- The dictionary of a program. -/
def ofProgram (program : Term) : Dictionary := (addTerm {} program).1

/-- The index of a subterm equal to `t`, if the hint finds one (checked again at use). -/
def findTerm (d : Dictionary) (t : Term) : Option Nat :=
  (d.termHint.getD (termHash t) []).find? fun i => match d.terms[i]? with
    | some u => termEq u t
    | none => false

end Dictionary

/-! ## References -/

/-- A term as one reference when the dictionary holds exactly it, else inline. -/
def encodeTermRef (terms : Array Term) (find : Term → Option Nat) (t : Term) : Tokens :=
  match find t with
  | some i => if (match terms[i]? with | some u => termEq u t | none => false) then [.nat (i + 1)]
      else .nat 0 :: encodeTerm t
  | none => .nat 0 :: encodeTerm t

def decodeTermRef (terms : Array Term) (fuel : Nat) : Tokens → Option (Term × Tokens)
  | .nat 0 :: rest => decodeTerm fuel rest
  | .nat (i + 1) :: rest => (terms[i]?).map (·, rest)
  | _ => none

/-- An address list as its length, then each address as a zigzagged step from the one
before (the first from 0): a record's fields and an environment are usually neighbouring
cells, so most steps are one digit. -/
def zigzag (from_ to : Nat) : Nat := if to ≤ from_ then 2 * (from_ - to) else 2 * (to - from_) - 1
def unzigzag (from_ step : Nat) : Nat := if step % 2 == 0 then from_ - step / 2 else from_ + (step + 1) / 2

def encodeSteps : Nat → List Address → Tokens
  | _, [] => []
  | previous, a :: rest => .nat (zigzag previous a) :: encodeSteps a rest

def decodeSteps : Nat → Nat → Tokens → Option (List Address × Tokens)
  | _, 0, rest => some ([], rest)
  | previous, count + 1, .nat step :: rest => do
      let a := unzigzag previous step
      let (others, rest) ← decodeSteps a count rest
      pure (a :: others, rest)
  | _, _ + 1, _ => none

def encodeAddressesV3 (addresses : List Address) : Tokens := .nat addresses.length :: encodeSteps 0 addresses
def decodeAddressesV3 : Tokens → Option (List Address × Tokens)
  | .nat count :: rest => decodeSteps 0 count rest
  | _ => none

/-- A record value's names as one reference to a program name list, else inline. -/
def encodeNamesRef (lists : Array (List String)) (find : List String → Option Nat) (names : List String) : Tokens :=
  match find names with
  | some i => if lists[i]? == some names then [.nat (i + 1)] else .nat 0 :: .nat names.length :: names.map .text
  | none => .nat 0 :: .nat names.length :: names.map .text

def decodeNamesRef (lists : Array (List String)) : Tokens → Option (List String × Tokens)
  | .nat 0 :: .nat count :: rest => decodeTexts count rest
  | .nat (i + 1) :: rest => (lists[i]?).map (·, rest)
  | _ => none

/-- An environment as one reference into the checkpoint's environment table, else inline. -/
def encodeEnvRef (envs : Array Environment) (find : Environment → Option Nat) (e : Environment) : Tokens :=
  match find e with
  | some i => if envs[i]? == some e then [.nat (i + 1)] else .nat 0 :: encodeAddressesV3 e
  | none => .nat 0 :: encodeAddressesV3 e

def decodeEnvRef (envs : Array Environment) : Tokens → Option (Environment × Tokens)
  | .nat 0 :: rest => decodeAddressesV3 rest
  | .nat (i + 1) :: rest => (envs[i]?).map (·, rest)
  | _ => none

/-- How terms and environments are written: the dictionary's terms, the checkpoint's
environments, and the hints that find them. -/
structure Refs where
  terms : Array Term
  findTerm : Term → Option Nat
  envs : Array Environment
  findEnv : Environment → Option Nat
  nameLists : Array (List String)
  findNames : List String → Option Nat

/-! ## The state, with references -/

section
variable (r : Refs)

def encodeFieldsV3 : List (String × Term) → Tokens
  | [] => [.nat 0]
  | (name, body) :: rest => .nat 1 :: .text name :: (encodeTermRef r.terms r.findTerm body ++ encodeFieldsV3 rest)

def encodeClosureV3 (c : Closure) : Tokens :=
  encodeTermRef r.terms r.findTerm c.term ++ encodeEnvRef r.envs r.findEnv c.environment

def encodeValueV3 : RuntimeValue → Tokens
  | .closure body environment => .nat 0 :: encodeClosureV3 r ⟨body, environment⟩
  | .record fields => .nat 4 :: (encodeNamesRef r.nameLists r.findNames (fields.map (·.1)) ++
      encodeAddressesV3 (fields.map (·.2)))
  | other => encodeValue other

def encodeCellV3 : Cell → Tokens
  | .suspended origin => .nat 0 :: encodeClosureV3 r origin
  | .evaluating origin => .nat 1 :: encodeClosureV3 r origin
  | .cached origin value => .nat 2 :: (encodeClosureV3 r origin ++ encodeValueV3 r value)
  | .native origin => .nat 3 :: encodeData origin
  | .nativeCached origin value => .nat 4 :: (encodeData origin ++ encodeValueV3 r value)
  | .stored part none => .nat 5 :: (encodeStored part ++ [.nat 0])
  | .stored part (some value) => .nat 5 :: (encodeStored part ++ .nat 1 :: encodeValueV3 r value)

def encodeFrameV3 : Frame → Tokens
  | .argument term environment => .nat 0 :: encodeClosureV3 r ⟨term, environment⟩
  | .extend fields environment => .nat 6 :: (encodeFieldsV3 r fields ++ encodeEnvRef r.envs r.findEnv environment)
  | .condition zero successorBody environment =>
      .nat 7 :: (encodeTermRef r.terms r.findTerm zero ++ encodeClosureV3 r ⟨successorBody, environment⟩)
  | .binaryLeft primitive right environment =>
      .nat 8 :: .nat (primitiveCode primitive) :: encodeClosureV3 r ⟨right, environment⟩
  | .binaryRight primitive left => .nat 9 :: .nat (primitiveCode primitive) :: encodeValueV3 r left
  | .case arms environment => .nat 10 :: (encodeFieldsV3 r arms ++ encodeEnvRef r.envs r.findEnv environment)
  | .ifBool whenTrue whenFalse environment =>
      .nat 11 :: (encodeTermRef r.terms r.findTerm whenTrue ++ encodeClosureV3 r ⟨whenFalse, environment⟩)
  | .joinSeparator list environment => .nat 14 :: encodeClosureV3 r ⟨list, environment⟩
  | other => encodeFrame other

def encodeControlV3 : Control → Tokens
  | .evaluate term environment => .nat 0 :: encodeClosureV3 r ⟨term, environment⟩
  | .returned value => .nat 3 :: encodeValueV3 r value
  | .complete value => .nat 4 :: encodeValueV3 r value
  | .nativeApplication function argument remaining =>
      .nat 7 :: (encodeTermRef r.terms r.findTerm function ++ encodeData argument ++ [.nat remaining.length] ++
        remaining.flatMap encodeData)
  | other => encodeControl other

/-- The body of a checkpoint: heap, control, stack. -/
def encodeBodyV3 (s : State) : Tokens :=
  [.nat s.heap.size] ++ s.heap.toList.flatMap (encodeCellV3 r) ++ encodeControlV3 r s.control ++
    [.nat s.stack.length] ++ s.stack.flatMap (encodeFrameV3 r)
end

section
variable (terms : Array Term) (envs : Array Environment) (nameLists : Array (List String))

def decodeFieldsV3 (fuel : Nat) : Nat → Tokens → Option (List (String × Term) × Tokens)
  | 0, _ => none
  | _ + 1, .nat 0 :: rest => some ([], rest)
  | n + 1, .nat 1 :: .text name :: rest => do
      let (body, rest) ← decodeTermRef terms fuel rest
      let (others, rest) ← decodeFieldsV3 fuel n rest
      pure ((name, body) :: others, rest)
  | _ + 1, _ => none

def decodeClosureV3 (fuel : Nat) (tokens : Tokens) : Option (Closure × Tokens) := do
  let (term, rest) ← decodeTermRef terms fuel tokens
  let (environment, rest) ← decodeEnvRef envs rest
  pure (⟨term, environment⟩, rest)

def decodeValueV3 (fuel : Nat) : Tokens → Option (RuntimeValue × Tokens)
  | .nat 0 :: rest => do
      let (c, rest) ← decodeClosureV3 terms envs fuel rest; pure (.closure c.term c.environment, rest)
  | .nat 4 :: rest => do
      let (names, rest) ← decodeNamesRef nameLists rest
      let (addresses, rest) ← decodeAddressesV3 rest
      if names.length == addresses.length then pure (.record (names.zip addresses), rest) else none
  | tokens => decodeValue fuel tokens

def decodeCellV3 (fuel : Nat) : Tokens → Option (Cell × Tokens)
  | .nat 0 :: rest => do let (origin, rest) ← decodeClosureV3 terms envs fuel rest; pure (.suspended origin, rest)
  | .nat 1 :: rest => do let (origin, rest) ← decodeClosureV3 terms envs fuel rest; pure (.evaluating origin, rest)
  | .nat 2 :: rest => do
      let (origin, rest) ← decodeClosureV3 terms envs fuel rest
      let (value, rest) ← decodeValueV3 terms envs nameLists fuel rest
      pure (.cached origin value, rest)
  | .nat 3 :: rest => do let (origin, rest) ← decodeData fuel rest; pure (.native origin, rest)
  | .nat 4 :: rest => do
      let (origin, rest) ← decodeData fuel rest
      let (value, rest) ← decodeValueV3 terms envs nameLists fuel rest
      pure (.nativeCached origin value, rest)
  | .nat 5 :: rest => do
      let (part, rest) ← decodeStored fuel rest
      match rest with
      | .nat 0 :: rest => pure (.stored part none, rest)
      | .nat 1 :: rest => do
        let (value, rest) ← decodeValueV3 terms envs nameLists fuel rest
        pure (.stored part (some value), rest)
      | _ => none
  | _ => none

def decodeFrameV3 (fuel : Nat) : Tokens → Option (Frame × Tokens)
  | .nat 0 :: rest => do
      let (c, rest) ← decodeClosureV3 terms envs fuel rest; pure (.argument c.term c.environment, rest)
  | .nat 6 :: rest => do
      let (fields, rest) ← decodeFieldsV3 terms fuel fuel rest
      let (environment, rest) ← decodeEnvRef envs rest
      pure (.extend fields environment, rest)
  | .nat 7 :: rest => do
      let (zero, rest) ← decodeTermRef terms fuel rest
      let (c, rest) ← decodeClosureV3 terms envs fuel rest
      pure (.condition zero c.term c.environment, rest)
  | .nat 8 :: .nat code :: rest => do
      let primitive ← primitiveOf code
      let (c, rest) ← decodeClosureV3 terms envs fuel rest
      pure (.binaryLeft primitive c.term c.environment, rest)
  | .nat 9 :: .nat code :: rest => do
      let primitive ← primitiveOf code
      let (left, rest) ← decodeValueV3 terms envs nameLists fuel rest
      pure (.binaryRight primitive left, rest)
  | .nat 10 :: rest => do
      let (arms, rest) ← decodeFieldsV3 terms fuel fuel rest
      let (environment, rest) ← decodeEnvRef envs rest
      pure (.case arms environment, rest)
  | .nat 11 :: rest => do
      let (whenTrue, rest) ← decodeTermRef terms fuel rest
      let (c, rest) ← decodeClosureV3 terms envs fuel rest
      pure (.ifBool whenTrue c.term c.environment, rest)
  | .nat 14 :: rest => do
      let (c, rest) ← decodeClosureV3 terms envs fuel rest; pure (.joinSeparator c.term c.environment, rest)
  | tokens => decodeFrame fuel tokens

def decodeControlV3 (fuel : Nat) : Tokens → Option (Control × Tokens)
  | .nat 0 :: rest => do
      let (c, rest) ← decodeClosureV3 terms envs fuel rest; pure (.evaluate c.term c.environment, rest)
  | .nat 3 :: rest => do let (value, rest) ← decodeValueV3 terms envs nameLists fuel rest; pure (.returned value, rest)
  | .nat 4 :: rest => do let (value, rest) ← decodeValueV3 terms envs nameLists fuel rest; pure (.complete value, rest)
  | .nat 7 :: rest => do
      let (function, rest) ← decodeTermRef terms fuel rest; let (argument, rest) ← decodeData fuel rest
      match rest with
      | .nat count :: rest =>
        let (remaining, rest) ← decodeMany (decodeData fuel) count rest
        pure (.nativeApplication function argument remaining, rest)
      | _ => none
  | tokens => decodeControl fuel tokens

def decodeBodyV3 (fuel : Nat) : Tokens → Option State
  | .nat cells :: rest => do
    let (heap, rest) ← decodeMany (decodeCellV3 terms envs nameLists fuel) cells rest
    let (control, rest) ← decodeControlV3 terms envs nameLists fuel rest
    match rest with
    | .nat frames :: rest =>
      let (stack, rest) ← decodeMany (decodeFrameV3 terms envs nameLists fuel) frames rest
      if rest.isEmpty then some ⟨heap.toArray, control, stack⟩ else none
    | _ => none
  | _ => none
end

/-! ## Strings -/

/-- A string as `str i` when the table holds exactly it at `i`; an existing `str j` moves
past the table (so `resolveString` inverts this on every token). -/
def internString (table : Array String) (find : String → Option Nat) : Token → Token
  | .text s => match find s with
    | some i => if table[i]? == some s then .str i else .text s
    | none => .text s
  | .str j => .str (j + table.size)
  | t => t

def resolveString (table : Array String) : Token → Token
  | .str j => if h : j < table.size then .text table[j] else .str (j - table.size)
  | t => t

/-! ## Environments -/

section
/-- Every environment a state mentions, in encoding order. -/
def closureEnvs (c : Closure) : List Environment := [c.environment]
def valueEnvs : RuntimeValue → List Environment
  | .closure _ e => [e]
  | _ => []
def cellEnvs : Cell → List Environment
  | .suspended c | .evaluating c => closureEnvs c
  | .cached c v => closureEnvs c ++ valueEnvs v
  | .nativeCached _ v => valueEnvs v
  | .native _ => []
  | .stored _ (some v) => valueEnvs v
  | .stored _ none => []
def frameEnvs : Frame → List Environment
  | .argument _ e | .extend _ e | .condition _ _ e | .binaryLeft _ _ e | .case _ e | .ifBool _ _ e
  | .joinSeparator _ e => [e]
  | .binaryRight _ v => valueEnvs v
  | _ => []
def controlEnvs : Control → List Environment
  | .evaluate _ e => [e]
  | .returned v | .complete v => valueEnvs v
  | _ => []
def stateEnvs (s : State) : List Environment :=
  s.heap.toList.flatMap cellEnvs ++ controlEnvs s.control ++ s.stack.flatMap frameEnvs
end

/-- The distinct environments of a state worth a table entry (those of two or more
addresses: a shorter one is no longer inline than its reference), first appearance first. -/
def envTable (s : State) : Array Environment × Std.HashMap Environment Nat :=
  (stateEnvs s).foldl (fun (table, index) e =>
    if e.length < 2 || index.contains e then (table, index) else (table.push e, index.insert e table.size)) (#[], {})

/-! ## The checkpoint -/

/-- The tokens a checkpoint holds before its strings are interned: the environment table
and the body. -/
def encodePlainV3 (d : Dictionary) (s : State) : Tokens :=
  let (envs, envIndex) := envTable s
  let refs : Refs := ⟨d.terms, d.findTerm, envs, fun e => envIndex[e]?, d.nameLists, fun n => d.nameHint[n]?⟩
  .nat envs.size :: envs.toList.flatMap encodeAddressesV3 ++ encodeBodyV3 refs s

/-- The strings of `plain` the dictionary does not hold, first appearance first. -/
def localStrings (d : Dictionary) (plain : Tokens) : Array String :=
  (plain.foldl (fun (acc : Array String × Std.HashSet String) t => match t with
    | .text x => if d.stringHint.contains x || acc.2.contains x then acc else (acc.1.push x, acc.2.insert x)
    | _ => acc) (#[], {})).1

/-- `plain` with its strings interned: the edition, the strings the dictionary does not
hold, then the tokens with every string a reference into the dictionary's and those. -/
def internAll (d : Dictionary) (plain : Tokens) (edition : String) : Tokens :=
  let locals := localStrings d plain
  let table := d.strings ++ locals
  let localIndex : Std.HashMap String Nat :=
    locals.foldl (fun (m, i) x => (m.insert x i, i + 1)) ({}, d.strings.size) |>.1
  let find := fun (x : String) => (d.stringHint[x]?).orElse fun _ => localIndex[x]?
  .text edition :: .nat locals.size :: (locals.toList.map .text ++ plain.map (internString table find))

/-- The environment table and the body, decoded. -/
def decodePlainV3 (terms : Array Term) (nameLists : Array (List String)) (plain : Tokens) : Option State :=
  match plain with
  | .nat envCount :: rest => do
    let (envs, rest) ← decodeMany decodeAddressesV3 envCount rest
    decodeBodyV3 terms envs.toArray nameLists (plain.length + 1) rest
  | _ => none

/-- A checkpoint's plain tokens: the edition checked, its strings resolved. -/
def decodeStrings (edition : String) (strings : Array String) (tokens : Tokens) : Option Tokens :=
  match tokens with
  | .text e :: .nat count :: rest => do
    if e != edition then none
    let locals ← (rest.take count).mapM fun t => match t with
      | .text x => some x
      | _ => none
    if locals.length != count then none
    some ((rest.drop count).map (resolveString (strings ++ locals.toArray)))
  | _ => none

/-! ## Addresses relative to their holders

A checkpoint's cells are numbered by the collector's canonical traversal, so a cell keeps
its number only until a turn makes the part before it longer; then every later absolute
address moves, and a journal's blocks stop matching between suspensions. v3 writes every
address a cell holds relative to that cell's own number, and those the control and stack
hold relative to the heap's end (`relativeState`, inverted by `absoluteState`), then
encodes as above: a region that moved as a whole encodes identically. -/

def checkpointEditionV3 : String := "dregg.objective-bend.checkpoint.v3"

/-- Address `a` seen from `i`, zigzagged: 0, 2, 4, … at or before `i`; 1, 3, … after. -/
def zigzagFrom (i a : Nat) : Nat := if a ≤ i then 2 * (i - a) else 2 * (a - i) - 1
def unzigzagFrom (i r : Nat) : Nat := if r % 2 == 0 then i - r / 2 else i + (r + 1) / 2

/-- An address as its holder writes it: relative to the holder (odd) when that is the
shorter, else absolute (even). The skeleton the collector numbers first (the knot, the
state) stays absolute from anywhere, so it does not move when data after it grows; data
pointing at its neighbours is relative, so a region that moved as a whole stays the same. -/
def toRelative (i a : Nat) : Nat := if zigzagFrom i a < a then 2 * zigzagFrom i a + 1 else 2 * a
def ofRelative (i r : Nat) : Nat := if r % 2 == 1 then unzigzagFrom i (r / 2) else r / 2

section
variable (f : Address → Address)

def mapValueAddresses : RuntimeValue → RuntimeValue
  | .closure body environment => .closure body (environment.map f)
  | .record fields => .record (fields.map fun (n, a) => (n, f a))
  | .specification m e => .specification (f m) (f e)
  | .prototype sp t => .prototype (f sp) (f t)
  | .variant l p => .variant l (f p)
  | other => other

def mapCellAddresses : Cell → Cell
  | .suspended c => .suspended { c with environment := c.environment.map f }
  | .evaluating c => .evaluating { c with environment := c.environment.map f }
  | .cached c v => .cached { c with environment := c.environment.map f } (mapValueAddresses f v)
  | .native d => .native d
  | .nativeCached d v => .nativeCached d (mapValueAddresses f v)
  | .stored p v => .stored p (v.map (mapValueAddresses f))

def mapWalkAddresses : Walk → Walk
  | .count counted => .count counted
  | .lookup key probe => .lookup key (f probe)

def mapFrameAddresses : Frame → Frame
  | .argument t e => .argument t (e.map f)
  | .update a => .update (f a)
  | .extend fs e => .extend fs (e.map f)
  | .condition z sb e => .condition z sb (e.map f)
  | .binaryLeft p rt e => .binaryLeft p rt (e.map f)
  | .binaryRight p v => .binaryRight p (mapValueAddresses f v)
  | .case arms e => .case arms (e.map f)
  | .ifBool t u e => .ifBool t u (e.map f)
  | .joinSeparator l e => .joinSeparator l (e.map f)
  | .joinHead sep acc first tail => .joinHead sep acc first (f tail)
  | .relationRows walk => .relationRows (mapWalkAddresses f walk)
  | .relationList walk => .relationList (mapWalkAddresses f walk)
  | .relationProbe key probe payload => .relationProbe key (f probe) (f payload)
  | .relationSearch key probe field low high => .relationSearch key (f probe) field low high
  | other => other

def mapControlAddresses : Control → Control
  | .evaluate t e => .evaluate t (e.map f)
  | .enter a => .enter (f a)
  | .blackhole a => .blackhole (f a)
  | .returned v => .returned (mapValueAddresses f v)
  | .complete v => .complete (mapValueAddresses f v)
  | .yielded a => .yielded (f a)
  | other => other
end

/-- Rename every address: a cell's by its own index, the control's and stack's by the
heap's size. -/
def mapStateAddresses (g : Nat → Address → Address) (s : State) : State :=
  ⟨s.heap.mapIdx fun i c => mapCellAddresses (g i) c, mapControlAddresses (g s.heap.size) s.control,
   s.stack.map (mapFrameAddresses (g s.heap.size))⟩

def relativeState (s : State) : State := mapStateAddresses toRelative s
def absoluteState (s : State) : State := mapStateAddresses ofRelative s

/-- A v3 checkpoint. -/
def encodeStateV3 (d : Dictionary) (s : State) : Tokens :=
  internAll d (encodePlainV3 d (relativeState s)) checkpointEditionV3

/-- Decode a v3 checkpoint. -/
def decodeStateV3 (terms : Array Term) (strings : Array String) (nameLists : Array (List String))
    (tokens : Tokens) : Option State :=
  ((decodeStrings checkpointEditionV3 strings tokens).bind (decodePlainV3 terms nameLists)).map absoluteState

/-- Decode a checkpoint against the program's dictionary: edition v3 only. -/
def decodeCheckpoint (d : Dictionary) (tokens : Tokens) : Option State :=
  decodeStateV3 d.terms d.strings d.nameLists tokens

end Delvetalk.Theory.ObjectiveBendCheckpoint
