/- Checkpoint codec for the Objective demand machine. A machine State is
first-order Lean data (heap of cells holding closures, control, frame stack),
so a whole activity — in particular a QUIESCENT yielded state — is captured as a
canonical token list and restored exactly. The codec adds no constructors to the
core; it is the persistence half of an activity (Faré C20). It carries no
authority, generation or custody: those belong to the kernel's activity record,
which holds this checkpoint as one artifact. The round trip
`decodeState (encodeState s) = some s` is the obligation this module exists for;
it is proved in Theory.ObjectiveBendCheckpointRoundTrip (`state_roundTrip`). A new
constructor here needs its case there, or the build fails. -/
import Theory.ObjectiveBendDemandMachine
import Theory.ObjectiveBendDemandData
namespace Minidregg.Theory.ObjectiveBendCheckpoint
open ObjectiveBendOpenRecursion ObjectiveBendDemandMachine
open Minidregg.Theory.ObjectiveBendDemandData (Data)
set_option autoImplicit false

inductive Token where
  | nat (value : Nat)
  | text (value : String)
  deriving Repr, BEq, DecidableEq

abbrev Tokens := List Token

def primitiveCode : Primitive → Nat
  | .add => 0 | .multiply => 1 | .equal => 2 | .conjunction => 3 | .labelEqual => 4
  | .subtract => 5 | .divide => 6 | .less => 7 | .lessEqual => 8 | .modulo => 10
  | .textConcat => 11 | .textTake => 12 | .textDrop => 13 | .textSpan => 14 | .textBreak => 15
def primitiveOf : Nat → Option Primitive
  | 0 => some .add | 1 => some .multiply | 2 => some .equal | 3 => some .conjunction
  | 4 => some .labelEqual | 5 => some .subtract | 6 => some .divide | 7 => some .less
  | 8 => some .lessEqual | 10 => some .modulo
  | 11 => some .textConcat | 12 => some .textTake | 13 => some .textDrop
  | 14 => some .textSpan | 15 => some .textBreak | _ => none
def unaryCode : UnaryPrimitive → Nat
  | .natText => 0 | .textLength => 1 | .sha256Text => 2
def unaryOf : Nat → Option UnaryPrimitive
  | 0 => some .natText | 1 => some .textLength | 2 => some .sha256Text | _ => none

mutual
def encodeTerm : Term → Tokens
  | .bound index => [.nat 0, .nat index]
  | .lam body => .nat 1 :: encodeTerm body
  | .app function argument => .nat 2 :: (encodeTerm function ++ encodeTerm argument)
  | .mix lower upper => .nat 3 :: (encodeTerm lower ++ encodeTerm upper)
  | .fix spec inherited => .nat 4 :: (encodeTerm spec ++ encodeTerm inherited)
  | .specification metadata extension => .nat 5 :: (encodeTerm metadata ++ encodeTerm extension)
  | .prototype spec target => .nat 6 :: (encodeTerm spec ++ encodeTerm target)
  | .reflect target => .nat 7 :: encodeTerm target
  | .metadata target => .nat 8 :: encodeTerm target
  | .project target => .nat 9 :: encodeTerm target
  | .nat value => [.nat 10, .nat value]
  | .boolean value => [.nat 11, .nat (if value then 1 else 0)]
  | .label value => [.nat 12, .text value]
  | .binary primitive left right =>
      .nat 13 :: .nat (primitiveCode primitive) :: (encodeTerm left ++ encodeTerm right)
  | .extend inherited fields => .nat 14 :: (encodeTerm inherited ++ encodeFields fields)
  | .record fields => .nat 15 :: encodeFields fields
  | .get target name => .nat 16 :: .text name :: encodeTerm target
  | .ifZero value zero successorBody =>
      .nat 17 :: (encodeTerm value ++ encodeTerm zero ++ encodeTerm successorBody)
  | .inject label payload => .nat 18 :: .text label :: encodeTerm payload
  | .case scrutinee arms => .nat 19 :: (encodeTerm scrutinee ++ encodeFields arms)
  | .ifBool condition whenTrue whenFalse =>
      .nat 20 :: (encodeTerm condition ++ encodeTerm whenTrue ++ encodeTerm whenFalse)
  | .perform plan => .nat 21 :: encodeTerm plan
  | .done value => .nat 22 :: encodeTerm value
  | .unary primitive argument => .nat 23 :: .nat (unaryCode primitive) :: encodeTerm argument
  | .toData value => .nat 24 :: encodeTerm value
def encodeFields : List (String × Term) → Tokens
  | [] => [.nat 0]
  | (name,body) :: rest => .nat 1 :: .text name :: (encodeTerm body ++ encodeFields rest)
end

mutual
def decodeTerm : Nat → Tokens → Option (Term × Tokens)
  | 0, _ => none
  | fuel + 1, .nat tag :: rest =>
    let one := fun (make : Term → Term) => do
      let (a, rest) ← decodeTerm fuel rest; pure (make a, rest)
    let two := fun (make : Term → Term → Term) => do
      let (a, rest) ← decodeTerm fuel rest; let (b, rest) ← decodeTerm fuel rest; pure (make a b, rest)
    let three := fun (make : Term → Term → Term → Term) => do
      let (a, rest) ← decodeTerm fuel rest; let (b, rest) ← decodeTerm fuel rest
      let (c, rest) ← decodeTerm fuel rest; pure (make a b c, rest)
    match tag, rest with
    | 0, .nat index :: rest => some (.bound index, rest)
    | 1, _ => one .lam
    | 2, _ => two .app
    | 3, _ => two .mix
    | 4, _ => two .fix
    | 5, _ => two .specification
    | 6, _ => two .prototype
    | 7, _ => one .reflect
    | 8, _ => one .metadata
    | 9, _ => one .project
    | 10, .nat value :: rest => some (.nat value, rest)
    | 11, .nat 0 :: rest => some (.boolean false, rest)
    | 11, .nat 1 :: rest => some (.boolean true, rest)
    | 12, .text value :: rest => some (.label value, rest)
    | 13, .nat code :: rest => do
        let primitive ← primitiveOf code
        let (left, rest) ← decodeTerm fuel rest; let (right, rest) ← decodeTerm fuel rest
        pure (.binary primitive left right, rest)
    | 14, _ => do
        let (inherited, rest) ← decodeTerm fuel rest; let (fields, rest) ← decodeFields fuel rest
        pure (.extend inherited fields, rest)
    | 15, _ => do let (fields, rest) ← decodeFields fuel rest; pure (.record fields, rest)
    | 16, .text name :: rest => do let (target, rest) ← decodeTerm fuel rest; pure (.get target name, rest)
    | 17, _ => three .ifZero
    | 18, .text label :: rest => do let (payload, rest) ← decodeTerm fuel rest; pure (.inject label payload, rest)
    | 19, _ => do
        let (scrutinee, rest) ← decodeTerm fuel rest; let (arms, rest) ← decodeFields fuel rest
        pure (.case scrutinee arms, rest)
    | 20, _ => three .ifBool
    | 21, _ => one .perform
    | 22, _ => one .done
    | 23, .nat code :: rest => do
        let primitive ← unaryOf code
        let (argument, rest) ← decodeTerm fuel rest
        pure (.unary primitive argument, rest)
    | 24, _ => one .toData
    | _, _ => none
  | _ + 1, _ => none
def decodeFields : Nat → Tokens → Option (List (String × Term) × Tokens)
  | 0, _ => none
  | _ + 1, .nat 0 :: rest => some ([], rest)
  | fuel + 1, .nat 1 :: .text name :: rest => do
      let (body, rest) ← decodeTerm fuel rest
      let (others, rest) ← decodeFields fuel rest
      pure ((name,body) :: others, rest)
  | _ + 1, _ => none
end

/-! Lists of addresses and named addresses: length-prefixed. -/
def encodeAddresses (addresses : List Address) : Tokens := .nat addresses.length :: addresses.map .nat
def decodeAddressesN : Nat → Tokens → Option (List Address × Tokens)
  | 0, rest => some ([], rest)
  | count + 1, .nat address :: rest => do
      let (others, rest) ← decodeAddressesN count rest; pure (address :: others, rest)
  | _ + 1, _ => none
def decodeAddresses : Tokens → Option (List Address × Tokens)
  | .nat count :: rest => decodeAddressesN count rest
  | _ => none

def encodeNamed (fields : List (String × Address)) : Tokens :=
  .nat fields.length :: fields.flatMap (fun field => [.text field.1, .nat field.2])
def decodeNamedN : Nat → Tokens → Option (List (String × Address) × Tokens)
  | 0, rest => some ([], rest)
  | count + 1, .text name :: .nat address :: rest => do
      let (others, rest) ← decodeNamedN count rest; pure ((name,address) :: others, rest)
  | _ + 1, _ => none
def decodeNamed : Tokens → Option (List (String × Address) × Tokens)
  | .nat count :: rest => decodeNamedN count rest
  | _ => none

def encodeClosure (closure : Closure) : Tokens := encodeTerm closure.term ++ encodeAddresses closure.environment
def decodeClosure (fuel : Nat) (tokens : Tokens) : Option (Closure × Tokens) := do
  let (term, rest) ← decodeTerm fuel tokens
  let (environment, rest) ← decodeAddresses rest
  pure (⟨term,environment⟩, rest)

def encodeValue : RuntimeValue → Tokens
  | .closure body environment => .nat 0 :: (encodeTerm body ++ encodeAddresses environment)
  | .natural value => [.nat 1, .nat value]
  | .boolean value => [.nat 2, .nat (if value then 1 else 0)]
  | .label value => [.nat 3, .text value]
  | .record fields => .nat 4 :: encodeNamed fields
  | .specification metadata extension => [.nat 5, .nat metadata, .nat extension]
  | .prototype spec target => [.nat 6, .nat spec, .nat target]
  | .variant label payload => [.nat 7, .text label, .nat payload]
def decodeValue (fuel : Nat) : Tokens → Option (RuntimeValue × Tokens)
  | .nat 0 :: rest => do
      let (closure, rest) ← decodeClosure fuel rest; pure (.closure closure.term closure.environment, rest)
  | .nat 1 :: .nat value :: rest => some (.natural value, rest)
  | .nat 2 :: .nat 0 :: rest => some (.boolean false, rest)
  | .nat 2 :: .nat 1 :: rest => some (.boolean true, rest)
  | .nat 3 :: .text value :: rest => some (.label value, rest)
  | .nat 4 :: rest => do let (fields, rest) ← decodeNamed rest; pure (.record fields, rest)
  | .nat 5 :: .nat metadata :: .nat extension :: rest => some (.specification metadata extension, rest)
  | .nat 6 :: .nat spec :: .nat target :: rest => some (.prototype spec target, rest)
  | .nat 7 :: .text label :: .nat payload :: rest => some (.variant label payload, rest)
  | _ => none

/-! Finite Data (native cell origins and native argument frames). -/
mutual
def encodeData : Data → Tokens
  | .natural value => [.nat 0, .nat value]
  | .boolean value => [.nat 1, .nat (if value then 1 else 0)]
  | .label value => [.nat 2, .text value]
  | .record fields => .nat 3 :: .nat fields.length :: encodeDataFields fields
  | .variant label payload => .nat 4 :: .text label :: encodeData payload
def encodeDataFields : List (String × Data) → Tokens
  | [] => []
  | (name, value) :: rest => .text name :: (encodeData value ++ encodeDataFields rest)
end

mutual
def decodeData : Nat → Tokens → Option (Data × Tokens)
  | 0, _ => none
  | _ + 1, .nat 0 :: .nat value :: rest => some (.natural value, rest)
  | _ + 1, .nat 1 :: .nat 0 :: rest => some (.boolean false, rest)
  | _ + 1, .nat 1 :: .nat 1 :: rest => some (.boolean true, rest)
  | _ + 1, .nat 2 :: .text value :: rest => some (.label value, rest)
  | fuel + 1, .nat 3 :: .nat count :: rest => do
      let (fields, rest) ← decodeDataFields fuel count rest
      pure (.record fields, rest)
  | fuel + 1, .nat 4 :: .text label :: rest => do
      let (payload, rest) ← decodeData fuel rest
      pure (.variant label payload, rest)
  | _ + 1, _ => none
def decodeDataFields : Nat → Nat → Tokens → Option (List (String × Data) × Tokens)
  | _, 0, rest => some ([], rest)
  | fuel, count + 1, .text name :: rest => do
      let (value, rest) ← decodeData fuel rest
      let (others, rest) ← decodeDataFields fuel count rest
      pure ((name, value) :: others, rest)
  | _, _ + 1, _ => none
end

def encodeCell : Cell → Tokens
  | .suspended origin => .nat 0 :: encodeClosure origin
  | .evaluating origin => .nat 1 :: encodeClosure origin
  | .cached origin value => .nat 2 :: (encodeClosure origin ++ encodeValue value)
  | .native origin => .nat 3 :: encodeData origin
  | .nativeCached origin value => .nat 4 :: (encodeData origin ++ encodeValue value)
def decodeCell (fuel : Nat) : Tokens → Option (Cell × Tokens)
  | .nat 0 :: rest => do let (origin, rest) ← decodeClosure fuel rest; pure (.suspended origin, rest)
  | .nat 1 :: rest => do let (origin, rest) ← decodeClosure fuel rest; pure (.evaluating origin, rest)
  | .nat 2 :: rest => do
      let (origin, rest) ← decodeClosure fuel rest; let (value, rest) ← decodeValue fuel rest
      pure (.cached origin value, rest)
  | .nat 3 :: rest => do let (origin, rest) ← decodeData fuel rest; pure (.native origin, rest)
  | .nat 4 :: rest => do
      let (origin, rest) ← decodeData fuel rest; let (value, rest) ← decodeValue fuel rest
      pure (.nativeCached origin value, rest)
  | _ => none

def encodeFrame : Frame → Tokens
  | .argument term environment => .nat 0 :: (encodeTerm term ++ encodeAddresses environment)
  | .update address => [.nat 1, .nat address]
  | .field name => [.nat 2, .text name]
  | .reflect => [.nat 3] | .metadata => [.nat 4] | .project => [.nat 5]
  | .extend fields environment => .nat 6 :: (encodeFields fields ++ encodeAddresses environment)
  | .condition zero successorBody environment =>
      .nat 7 :: (encodeTerm zero ++ encodeTerm successorBody ++ encodeAddresses environment)
  | .binaryLeft primitive right environment =>
      .nat 8 :: .nat (primitiveCode primitive) :: (encodeTerm right ++ encodeAddresses environment)
  | .binaryRight primitive left => .nat 9 :: .nat (primitiveCode primitive) :: encodeValue left
  | .case arms environment => .nat 10 :: (encodeFields arms ++ encodeAddresses environment)
  | .ifBool whenTrue whenFalse environment =>
      .nat 11 :: (encodeTerm whenTrue ++ encodeTerm whenFalse ++ encodeAddresses environment)
  | .nativeArgument value => .nat 12 :: encodeData value
  | .unary primitive => [.nat 13, .nat (unaryCode primitive)]
def decodeFrame (fuel : Nat) : Tokens → Option (Frame × Tokens)
  | .nat 0 :: rest => do
      let (term, rest) ← decodeTerm fuel rest; let (environment, rest) ← decodeAddresses rest
      pure (.argument term environment, rest)
  | .nat 1 :: .nat address :: rest => some (.update address, rest)
  | .nat 2 :: .text name :: rest => some (.field name, rest)
  | .nat 3 :: rest => some (.reflect, rest)
  | .nat 4 :: rest => some (.metadata, rest)
  | .nat 5 :: rest => some (.project, rest)
  | .nat 6 :: rest => do
      let (fields, rest) ← decodeFields fuel rest; let (environment, rest) ← decodeAddresses rest
      pure (.extend fields environment, rest)
  | .nat 7 :: rest => do
      let (zero, rest) ← decodeTerm fuel rest; let (successorBody, rest) ← decodeTerm fuel rest
      let (environment, rest) ← decodeAddresses rest
      pure (.condition zero successorBody environment, rest)
  | .nat 8 :: .nat code :: rest => do
      let primitive ← primitiveOf code
      let (right, rest) ← decodeTerm fuel rest; let (environment, rest) ← decodeAddresses rest
      pure (.binaryLeft primitive right environment, rest)
  | .nat 9 :: .nat code :: rest => do
      let primitive ← primitiveOf code
      let (left, rest) ← decodeValue fuel rest
      pure (.binaryRight primitive left, rest)
  | .nat 10 :: rest => do
      let (arms, rest) ← decodeFields fuel rest; let (environment, rest) ← decodeAddresses rest
      pure (.case arms environment, rest)
  | .nat 11 :: rest => do
      let (whenTrue, rest) ← decodeTerm fuel rest; let (whenFalse, rest) ← decodeTerm fuel rest
      let (environment, rest) ← decodeAddresses rest
      pure (.ifBool whenTrue whenFalse environment, rest)
  | .nat 12 :: rest => do let (value, rest) ← decodeData fuel rest; pure (.nativeArgument value, rest)
  | .nat 13 :: .nat code :: rest => do pure (.unary (← unaryOf code), rest)
  | _ => none

def refusalCode : Refusal → Nat
  | .unbound => 0 | .missingCell => 1 | .missingField => 2 | .wrongValue => 3
  | .invalidUpdate => 4 | .capacity => 5 | .missingArm => 6 | .sharedEffect => 7
def refusalOf : Nat → Option Refusal
  | 0 => some .unbound | 1 => some .missingCell | 2 => some .missingField | 3 => some .wrongValue
  | 4 => some .invalidUpdate | 5 => some .capacity | 6 => some .missingArm | 7 => some .sharedEffect
  | _ => none

def decodeMany {α : Type} (item : Tokens → Option (α × Tokens)) : Nat → Tokens → Option (List α × Tokens)
  | 0, rest => some ([], rest)
  | count + 1, tokens => do
      let (first, rest) ← item tokens; let (others, rest) ← decodeMany item count rest
      pure (first :: others, rest)

def encodeControl : Control → Tokens
  | .evaluate term environment => .nat 0 :: (encodeTerm term ++ encodeAddresses environment)
  | .enter address => [.nat 1, .nat address]
  | .blackhole address => [.nat 2, .nat address]
  | .returned value => .nat 3 :: encodeValue value
  | .complete value => .nat 4 :: encodeValue value
  | .refused reason => [.nat 5, .nat (refusalCode reason)]
  | .yielded plan => [.nat 6, .nat plan]
  | .nativeApplication function argument remaining =>
      .nat 7 :: (encodeTerm function ++ encodeData argument ++ [.nat remaining.length] ++
        remaining.flatMap encodeData)
def decodeControl (fuel : Nat) : Tokens → Option (Control × Tokens)
  | .nat 0 :: rest => do
      let (term, rest) ← decodeTerm fuel rest; let (environment, rest) ← decodeAddresses rest
      pure (.evaluate term environment, rest)
  | .nat 1 :: .nat address :: rest => some (.enter address, rest)
  | .nat 2 :: .nat address :: rest => some (.blackhole address, rest)
  | .nat 3 :: rest => do let (value, rest) ← decodeValue fuel rest; pure (.returned value, rest)
  | .nat 4 :: rest => do let (value, rest) ← decodeValue fuel rest; pure (.complete value, rest)
  | .nat 5 :: .nat code :: rest => do pure (.refused (← refusalOf code), rest)
  | .nat 6 :: .nat plan :: rest => some (.yielded plan, rest)
  | .nat 7 :: rest => do
      let (function, rest) ← decodeTerm fuel rest; let (argument, rest) ← decodeData fuel rest
      match rest with
      | .nat count :: rest =>
        let (remaining, rest) ← decodeMany (decodeData fuel) count rest
        pure (.nativeApplication function argument remaining, rest)
      | _ => none
  | _ => none

/-- Edition tag of this checkpoint format; a changed machine shape bumps it and
old checkpoints refuse to load. -/
def checkpointEdition : String := "dregg.objective-bend.checkpoint.v1"

def encodeState (state : State) : Tokens :=
  [.text checkpointEdition, .nat state.heap.size] ++ state.heap.toList.flatMap encodeCell ++
    encodeControl state.control ++ [.nat state.stack.length] ++ state.stack.flatMap encodeFrame

/-- Fuel is the token count: every term constructor consumes at least one token. -/
def decodeState (tokens : Tokens) : Option State :=
  let fuel := tokens.length + 1
  match tokens with
  | .text edition :: .nat cells :: rest => do
    if edition != checkpointEdition then none
    let (heap, rest) ← decodeMany (decodeCell fuel) cells rest
    let (control, rest) ← decodeControl fuel rest
    match rest with
    | .nat frames :: rest =>
      let (stack, rest) ← decodeMany (decodeFrame fuel) frames rest
      if rest.isEmpty then some ⟨heap.toArray, control, stack⟩ else none
    | _ => none
  | _ => none

/-- Canonical bytes are the tokens' JSON; its digest is a checkpoint identity. -/
def tokenJson : Token → Lean.Json
  | .nat value => Lean.Json.mkObj [("n", Lean.toJson (toString value))]
  | .text value => Lean.Json.mkObj [("s", Lean.toJson value)]

/-- Executed round-trip check: re-encoding the decoded checkpoint reproduces the
same tokens. `state_roundTrip` proves the stronger equation for every state. -/
def roundTrips (state : State) : Bool :=
  match decodeState (encodeState state) with
  | some restored => encodeState restored == encodeState state
  | none => false

end Minidregg.Theory.ObjectiveBendCheckpoint
