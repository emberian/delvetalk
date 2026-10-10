import Lean.Data.Json
import Compiler.ObjectiveBendDataWire

/-!
The spell grammar of a card reply (docs/FOUNDATION.md section 4), ported rule for rule from
`world/lib/Spell.obend`, which stays the reference: every function below carries the name and the
case split of its Bend namesake, over lists of Unicode scalars (Bend `Text`). Pure; `parse`, `bare`
and `fit` are what the host calls, `parsedJson`/`fitJson`/`bareJson` are the wire renderers.
-/
namespace Delvetalk.Host.Spell
open Lean (Json toJson)
open Minidregg.Theory.ObjectiveBendDemandData (Data)

abbrev T := List Char

structure Binding where
  name : String
  value : String
  deriving Repr, BEq

inductive Parsed where
  | spell (card action : String) (fields : List Binding)
  | notASpell (reason : String) (fielded : Bool)
  deriving Repr, BEq

inductive Kind where
  | text (min max : Nat)
  | natural (min max : Nat)
  | choice (options : List String)
  deriving Repr, BEq

structure Field where
  name : String
  kind : Kind
  deriving Repr, BEq

structure Form where
  card : String
  action : String
  fields : List Field
  deriving Repr, BEq

inductive Value where
  | text (value : String)
  | natural (value : Nat)
  | choice (value : String)
  deriving Repr, BEq

structure Entry where
  name : String
  value : Value
  deriving Repr, BEq

/-- Why a spell was refused: WHOLENESS.md section 2. -/
inductive Clause where
  | otherCard | noAction | unknownField | duplicateField | badValue | unclosedBlock | unclear
  deriving Repr, BEq

def Clause.name : Clause → String
  | .otherCard => "otherCard" | .noAction => "noAction" | .unknownField => "unknownField"
  | .duplicateField => "duplicateField" | .badValue => "badValue"
  | .unclosedBlock => "unclosedBlock" | .unclear => "unclear"

inductive Fit where
  | proposal (card action : String) (bindings : List Entry)
  | unclear (needs : List String)
  | refused (clause : Clause) (reason : String)
  deriving Repr, BEq

/-! ## Text primitives (Bend textSpan, textBreak, textTake, textDrop) -/

def span (t : T) (alphabet : T) : Nat := (t.takeWhile (alphabet.contains ·)).length
def brk (t : T) (alphabet : T) : Nat := (t.takeWhile (fun c => !alphabet.contains c)).length

def blanks : T := [' ', '\t', '\r']
def identifier : T := "abcdefghijklmnopqrstuvwxyz0123456789-".toList
def cardAlphabet : T := "abcdefghijklmnopqrstuvwxyz0123456789-:/.".toList
def delimiterAlphabet : T := "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_".toList

def isCardName (v : T) : Bool :=
  let size := v.length
  decide (size > 0) && decide (size ≤ 160) && span v cardAlphabet == size

def isIdentifier (v : T) : Bool :=
  let size := v.length
  decide (size > 0) && span v identifier == size

def isAction (v : T) : Bool := v == ['?'] || isIdentifier v

def trimStart (v : T) : T := v.drop (span v blanks)
def trimEnd (v : T) : T := (v.reverse.dropWhile (blanks.contains ·)).reverse

def str (v : T) : String := String.mk v
def lit (s : String) : T := s.toList

def looksLikeField (v : T) : Bool :=
  let colon := brk v [':']
  decide (colon > 0) && v.take colon != v && isIdentifier (v.take colon)

/-! ## Parse -/

inductive Fields2 where
  | found (bindings : List Binding)
  | bad (reason : String)
  | again (text : T)
  | stray (bindings : List Binding) (rest : T)

inductive Candidate where
  | none
  | stands (card action : String) (tail rest : T)

instance : Inhabited Fields2 := ⟨.found []⟩
instance : Inhabited Parsed := ⟨.notASpell "" false⟩

def fieldHead (text : T) (indent stop : Nat) : Bool :=
  decide (stop > indent) &&
    looksLikeField ((text.drop indent).take (if stop - indent < 17 then stop - indent else 17))

def isSpellAt (text : T) (indent : Nat) : Bool :=
  (text.drop indent).take 10 == lit "delvetalk " || (text.drop indent).take 10 == lit "delvetalk\t"

def isQuote (text : T) : Bool := span (text.take 4) [' '] == 4 || text.take 1 == ['\t']

def tagged (text : T) (indent stop : Nat) : Bool :=
  decide (stop > indent + 3) && (text.drop indent).take 3 == lit "```" &&
    decide (span (text.drop (indent + 3)) blanks < stop - indent - 3)

partial def pastFence (text : T) : T :=
  if text.isEmpty then text else
  let indent := span text [' ', '\t']
  let stop := brk text ['\n']
  if (text.drop indent).take 3 == lit "```" then text.drop (stop + 1) else pastFence (text.drop (stop + 1))

def heading (line rest : T) : Candidate :=
  let afterBlanks := trimStart line
  let cardEnd := brk afterBlanks [' ', '\t']
  let card := afterBlanks.take cardEnd
  let afterCard := trimStart (afterBlanks.drop cardEnd)
  let actionEnd := brk afterCard [' ', '\t']
  let action := afterCard.take actionEnd
  if !isCardName card || !isAction action then .none
  else .stands (str card) (str action) (trimStart (afterCard.drop actionEnd)) rest

def headingAt (text : T) (indent stop : Nat) : Candidate :=
  heading (trimEnd ((text.take stop).drop (indent + 9))) (text.drop (stop + 1))

def consed (b : Binding) : Fields2 → Fields2
  | .found bs => .found (b :: bs)
  | .stray bs rest => .stray (b :: bs) rest
  | other => other

def sequenced (bs : List Binding) : Fields2 → Fields2
  | .found g => .found (bs ++ g)
  | .stray g rest => .stray (bs ++ g) rest
  | other => other

def both (first second : Fields2) : Fields2 :=
  match first with
  | .found f => sequenced f second
  | other => other

mutual
partial def startField (value rest : T) : Fields2 :=
  let colon := brk value [':']
  if looksLikeField value then continued (str (value.take colon)) (trimStart (value.drop (colon + 1))) rest
  else .bad s!"Not a field: {str (value.take 40)}"

partial def continued (name : String) (value rest : T) : Fields2 :=
  if rest.isEmpty then consed ⟨name, str (trimEnd value)⟩ (.found [])
  else more name value (brk rest [',']) rest

partial def more (name : String) (value : T) (stop : Nat) (rest : T) : Fields2 :=
  let next := trimStart (rest.take stop)
  if looksLikeField next then
    consed ⟨name, str (trimEnd value)⟩ (startField next (rest.drop (stop + 1)))
  else continued name (value ++ [','] ++ rest.take stop) (rest.drop (stop + 1))
end

def piece (tail : T) : Fields2 :=
  let stop := brk tail [',']
  startField (trimStart (tail.take stop)) (tail.drop (stop + 1))

def segment (text : T) : Fields2 :=
  if (trimStart text).isEmpty then .found [] else piece (trimStart text)

partial def slashed (before rest : T) : Fields2 :=
  let cut := brk rest ['/']
  if cut == rest.length then segment (before ++ rest)
  else
    let head := rest.take cut
    let after := rest.drop (cut + 1)
    if looksLikeField (trimStart after) && (head.isEmpty || span (head.drop (head.length - 1)) blanks == 1) then
      both (segment (before ++ head)) (slashed [] (trimStart after))
    else slashed (before ++ head ++ ['/']) after

def inline (tail : T) : Fields2 :=
  if tail.isEmpty then .found []
  else slashed [] (if tail.take 1 == ['/'] then trimStart (tail.drop 1) else tail)

def isDelimiter (text : T) : Bool :=
  decide (text.length ≥ 1) && decide (text.length ≤ 32) && span text delimiterAlphabet == text.length

def opens (head : T) : Bool := head.take 2 == lit "<<" || head.take 3 == lit " <<"

mutual
partial def fieldLines (text : T) : Fields2 :=
  if text.isEmpty then .found [] else spellLine text (span text [' ', '\t']) (brk text ['\n'])

partial def spellLine (text : T) (indent stop : Nat) : Fields2 :=
  if tagged text indent stop then fieldLines (pastFence (text.drop (stop + 1)))
  else if decide (indent < stop) && isSpellAt text indent then
    match headingAt text indent stop with
    | .stands .. => if isQuote text then fieldLines (text.drop (stop + 1)) else .again text
    | .none => .found []
  else fieldLine text stop

partial def fieldLine (text : T) (stop : Nat) : Fields2 :=
  if stop == 0 then fieldLines (text.drop 1) else lineParts (text.take stop) (text.drop (stop - 1))

partial def lineParts (line tail : T) : Fields2 :=
  let rest := tail.drop 2
  let first := line.take 1
  if span first blanks == 1 then lineParts (trimStart (trimEnd line)) tail
  else classify (if span (tail.take 1) blanks == 1 then trimEnd line else line) first rest

partial def classify (line first rest : T) : Fields2 :=
  if line.isEmpty || first == ['#'] || first == ['>'] || (first == ['`'] && line.take 3 == lit "```") then
    fieldLines rest
  else if first == ['-'] && line == lit "---" then .found []
  else binding line rest

partial def binding (line rest : T) : Fields2 :=
  let colon := brk line [':']
  let name := line.take colon
  if colon == 0 || name == line then .stray [] rest
  else if opens ((line.drop (colon + 1)).take 3) then valued (str name) (trimStart (line.drop (colon + 1))) rest
  else consed ⟨str name, str (trimStart (line.drop (colon + 1)))⟩ (fieldLines rest)

partial def valued (name : String) (value rest : T) : Fields2 :=
  if value.take 2 == lit "<<" && isDelimiter (trimEnd (value.drop 2)) then
    block name (trimEnd (value.drop 2)) rest []
  else consed ⟨name, str value⟩ (fieldLines rest)

partial def block (name : String) (delimiter rest : T) (lines : List T) : Fields2 :=
  if rest.isEmpty then
    .bad s!"The block <<{str delimiter} for {name} needs a last line that is exactly {str delimiter}."
  else
    let line := rest.take (brk rest ['\n'])
    let after := rest.drop (brk rest ['\n'] + 1)
    if line == delimiter || (line.take (line.length - 1) == delimiter && line.drop (line.length - 1) == ['\r']) then
      consed ⟨name, "\n".intercalate (lines.reverse.map str)⟩ (fieldLines after)
    else block name delimiter after (line :: lines)
end

partial def parseFrom (text : T) (quoted : Candidate) (fielded : Bool) : Parsed :=
  let noLine := "No delvetalk line; the spell is the last unquoted one."
  let spelled' := fun (card action : String) (tail rest : T) => spelled card action (both (inline tail) (fieldLines rest))
  if text.isEmpty then
    match quoted with
    | .stands c a tail rest => spelled' c a tail rest
    | .none => .notASpell noLine fielded
  else
    let indent := span text [' ', '\t']
    let stop := brk text ['\n']
    if tagged text indent stop then parseFrom (pastFence (text.drop (stop + 1))) quoted fielded
    else if decide (indent < stop) && isSpellAt text indent then
      let rest := text.drop (stop + 1)
      match headingAt text indent stop with
      | .none => parseFrom rest quoted fielded
      | candidate@(.stands c a tail rest') =>
          if isQuote text then parseFrom rest candidate fielded else spelled' c a tail rest'
    else parseFrom (text.drop (stop + 1)) quoted (fielded || fieldHead text indent stop)
where
  spelled (card action : String) : Fields2 → Parsed
    | .found bs => .spell card action bs
    | .bad reason => .notASpell reason true
    | .again text => parseFrom text .none false
    | .stray bs rest => seekAfter rest (.spell card action bs)
  seekAfter (text : T) (otherwise : Parsed) : Parsed :=
    if text.isEmpty then otherwise else
    let indent := span text [' ', '\t']
    let stop := brk text ['\n']
    if tagged text indent stop then seekAfter (pastFence (text.drop (stop + 1))) otherwise
    else if decide (indent < stop) && isSpellAt text indent && !isQuote text then
      match headingAt text indent stop with
      | .none => seekAfter (text.drop (stop + 1)) otherwise
      | .stands c a tail rest => spelled c a (both (inline tail) (fieldLines rest))
    else seekAfter (text.drop (stop + 1)) otherwise

/-- The spell a reply means: its last unquoted `delvetalk <card> <action>` line with the fields
    that follow (inline after the action, or one per line), or why there is none. -/
def parse (text : String) : Parsed := parseFrom text.toList .none false

/-- Field lines with no delvetalk line: every `name: value` line outside tagged fences and `>`
    quotation, in order. -/
partial def bareT (text : T) : List Binding :=
  if text.isEmpty then [] else
  let indent := span text [' ', '\t']
  let stop := brk text ['\n']
  if tagged text indent stop then bareT (pastFence (text.drop (stop + 1)))
  else
    let line := trimEnd ((text.take stop).drop indent)
    let rest := text.drop (stop + 1)
    if line.take 1 == ['>'] || line.take 3 == lit "```" || !looksLikeField line then bareT rest
    else ⟨str (line.take (brk line [':'])), str (trimStart (line.drop (brk line [':'] + 1)))⟩ :: bareT rest

def bare (text : String) : List Binding := bareT text.toList

/-! ## Fit -/

def number (value : T) : Option Nat :=
  let size := value.length
  if size == 0 || size > 18 || span value "0123456789".toList != size then none
  else if size > 1 && value.take 1 == ['0'] then none
  else some (value.foldl (fun total c => total * 10 + (c.toNat - '0'.toNat)) 0)

/-- `none` is fine; `some (clause, reason)` is a refusal. -/
def judge (field : Field) (value : String) : Option (Clause × String) :=
  let wrong := fun r => some (Clause.badValue, r)
  match field.kind with
  | .text min max =>
      if value.length < min || value.length > max then wrong s!"{field.name} takes {min} to {max} characters."
      else none
  | .natural min max =>
      match number value.toList with
      | none => wrong s!"{field.name} takes a natural number in plain digits."
      | some v => if v < min || v > max then wrong s!"{field.name} takes {min} to {max}" else none
  | .choice options =>
      if options.contains value then none
      else wrong s!"{field.name} is one of: {", ".intercalate options}"

def named (name : String) (b : Binding) : Bool := b.name == name

def audit (fields : List Field) : List Binding → Option (Clause × String)
  | [] => none
  | b :: rest =>
      match fields.find? (·.name == b.name) with
      | none => some (.unknownField, s!"No field {b.name} in this spell; it takes {if fields.isEmpty then "none" else ", ".intercalate (fields.map (·.name))}.")
      | some f =>
          if rest.any (named b.name) then some (.duplicateField, s!"{b.name} is given twice; keep one.")
          else match judge f b.value with
            | some w => some w
            | none => audit fields rest

def valueOf (bindings : List Binding) (name : String) : String :=
  match bindings.find? (named name) with
  | some b => b.value
  | none => ""

def typed (kind : Kind) (value : String) : Value :=
  match kind with
  | .text .. => .text value
  | .natural .. => .natural ((number value.toList).getD 0)
  | .choice .. => .choice value

def isText : Kind → Bool
  | .text .. => true
  | _ => false

def rebound (bindings : List Binding) (form : Form) : List Binding :=
  if bindings.any (named form.action) then
    match form.fields.find? (fun f => isText f.kind && !bindings.any (named f.name)) with
    | none => bindings
    | some f => bindings.map fun b => if b.name == form.action then { b with name := f.name } else b
  else bindings

def clauseOfReason (reason : String) : Clause :=
  if reason.startsWith "The block <<" then .unclosedBlock else .noAction

def fit (parsed : Parsed) (form : Form) : Fit :=
  match parsed with
  | .notASpell reason _ => .refused (clauseOfReason reason) reason
  | .spell card action fields =>
      if card != form.card || action != form.action then
        .refused .otherCard s!"This card answers {form.card} {form.action}."
      else
        let bindings := rebound fields form
        match audit form.fields bindings with
        | some (clause, reason) => .refused clause reason
        | none =>
            let needs := (form.fields.filter fun f => !bindings.any (named f.name)).map (·.name)
            if needs.isEmpty then
              .proposal form.card form.action
                (form.fields.map fun f => ⟨f.name, typed f.kind (valueOf bindings f.name)⟩)
            else .unclear needs

/-! ## Forms -/

partial def listOf : Data → Option (List Data)
  | .variant "nil" _ => some []
  | .variant "cons" (.record f) => do
    let head ← f.lookup "head"
    return head :: (← listOf (← f.lookup "tail"))
  | _ => none

def label : Data → Option String
  | .label s => some s
  | _ => none

def Form.ofData : Data → Option Form
  | .record f => do
    let card ← (f.lookup "card").bind label
    let action ← (f.lookup "action").bind label
    let items ← (f.lookup "fields").bind listOf
    let fields ← items.mapM fun
      | .record g => do
          let name ← (g.lookup "name").bind label
          let kind ← match ← g.lookup "kind" with
            | .variant "text" (.record k) => do
                let .natural a ← k.lookup "min" | none
                let .natural b ← k.lookup "max" | none
                pure (Kind.text a b)
            | .variant "natural" (.record k) => do
                let .natural a ← k.lookup "min" | none
                let .natural b ← k.lookup "max" | none
                pure (Kind.natural a b)
            | .variant "choice" (.record k) => do
                let opts ← (k.lookup "options").bind listOf
                pure (Kind.choice (← opts.mapM label))
            | _ => none
          pure (Field.mk name kind)
      | _ => none
    return ⟨card, action, fields⟩
  | _ => none

def Form.ofJson (j : Json) : Except String Form := do
  let card ← j.getObjValAs? String "card"
  let action ← j.getObjValAs? String "action"
  let items ← (← j.getObjVal? "fields").getArr?
  let fields ← items.toList.mapM fun item => do
    let name ← item.getObjValAs? String "name"
    let k ← item.getObjVal? "kind"
    let kind ←
      match k.getObjVal? "text" with
      | .ok t => pure (Kind.text (← t.getObjValAs? Nat "min") (← t.getObjValAs? Nat "max"))
      | .error _ =>
        match k.getObjVal? "natural" with
        | .ok t => pure (Kind.natural (← t.getObjValAs? Nat "min") (← t.getObjValAs? Nat "max"))
        | .error _ =>
          let c ← k.getObjVal? "choice"
          let opts ← (← c.getObjVal? "options").getArr?
          pure (Kind.choice (← opts.toList.mapM fun o => o.getStr?))
    pure (Field.mk name kind)
  return ⟨card, action, fields⟩

/-! ## Wire -/

def bindingsJson (bs : List Binding) : Json :=
  Json.arr (bs.toArray.map fun b => Json.mkObj [("name", toJson b.name), ("value", toJson b.value)])

def parsedJson : Parsed → List (String × Json)
  | .spell card action fields =>
      [("spell", Json.mkObj [("card", toJson card), ("action", toJson action), ("fields", bindingsJson fields)])]
  | .notASpell reason fielded =>
      [("notASpell", Json.mkObj [("reason", toJson reason), ("fielded", Json.bool fielded)])]

def valueJson : Value → Json
  | .text s => Json.mkObj [("text", toJson s)]
  | .natural n => Json.mkObj [("natural", toJson n)]
  | .choice s => Json.mkObj [("choice", toJson s)]

def fitJson : Fit → Json
  | .proposal card action bs =>
      Json.mkObj [("proposal", Json.mkObj [("card", toJson card), ("action", toJson action),
        ("bindings", Json.arr (bs.toArray.map fun e => Json.mkObj [("name", toJson e.name), ("value", valueJson e.value)]))])]
  | .unclear needs => Json.mkObj [("unclear", Json.mkObj [("needs", toJson needs)])]
  | .refused clause reason =>
      Json.mkObj [("refused", Json.mkObj [("clause", toJson clause.name), ("reason", toJson reason)])]

/-- The stateless op `spell-parse {text, form?}`. -/
def op (request : Json) : Except String Json := do
  let text ← request.getObjValAs? String "text"
  let parsed := parse text
  let fitPart ← match request.getObjVal? "form" with
    | .ok f =>
        if f.isNull then pure [] else do
          let form ← Form.ofJson f
          pure [("fit", fitJson (fit parsed form))]
    | .error _ => pure []
  return Json.mkObj ([("status", toJson "parsed")] ++ parsedJson parsed ++ fitPart ++
    [("bare", bindingsJson (bare text))])

private def plant : Form :=
  ⟨"garden-1", "plant", [⟨"colour", .choice ["amber", "violet", "silver"]⟩, ⟨"seed", .text 1 80⟩]⟩

#guard parse "delvetalk garden-1 plant\nseed: fern\ncolour: silver\n" ==
  .spell "garden-1" "plant" [⟨"seed", "fern"⟩, ⟨"colour", "silver"⟩]
#guard fit (parse "delvetalk garden-1 plant\nseed: fern\ncolour: silver\n") plant ==
  .proposal "garden-1" "plant" [⟨"colour", .choice "silver"⟩, ⟨"seed", .text "fern"⟩]
#guard parse "delvetalk tide subscribe / every: 1 / note: WC-01, first light" ==
  .spell "tide" "subscribe" [⟨"every", "1"⟩, ⟨"note", "WC-01, first light"⟩]
#guard parse "delvetalk w c\nsource: <<BEND\nline\n" ==
  .notASpell "The block <<BEND for source needs a last line that is exactly BEND." true
#guard fit (parse "delvetalk garden-1 plant\nplant: a fern") plant == .unclear ["colour"]
#guard fit (parse "delvetalk garden-1 plant\nplant: a fern\nseed: moss\ncolour: silver") plant ==
  .refused .unknownField "No field plant in this spell; it takes colour, seed."
#guard fit (parse "delvetalk garden-2 plant") plant == .refused .otherCard "This card answers garden-1 plant."
#guard bare "plant: a fern\n> x: y\n" == [⟨"plant", "a fern"⟩]

end Delvetalk.Host.Spell
