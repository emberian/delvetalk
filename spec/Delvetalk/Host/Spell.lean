import Lean.Data.Json
import Compiler.ObjectiveBendDataWire
import Delvetalk.Host.Store

/-!
The spell grammar of a card reply (docs/FOUNDATION.md section 4), ported rule for rule from
`world/lib/Spell.obend`, which stays the reference: every function below carries the name and the
case split of its Bend namesake, over lists of Unicode scalars (Bend `Text`). Pure; `parse`, `bare`
and `fit` are what the host calls, `parsedJson`/`fitJson`/`bareJson` are the wire renderers.
-/
namespace Delvetalk.Host.Spell
open Lean (Json toJson)
open Delvetalk.Theory.ObjectiveBendDemandData (Data)

abbrev T := List Char

structure Binding where
  name : String
  value : String
  deriving Repr, BEq

inductive Parsed where
  | spell (card action : String) (fields : List Binding)
  | notASpell (reason : String) (fielded : Bool)
  /-- A text that quotes a card (one of its header lines beside `delvetalk` lines): its spells are the
      card's examples, so nothing is cast (`quotation`). -/
  | quotation (reason : String)
  deriving Repr, BEq

inductive Kind where
  | text (min max : Nat)
  | object (min max : Nat)
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
  | otherCard | noAction | unknownField | duplicateField | badValue | unclosedBlock | quotation | unclear
  deriving Repr, BEq

def Clause.name : Clause → String
  | .otherCard => "otherCard" | .noAction => "noAction" | .unknownField => "unknownField"
  | .duplicateField => "duplicateField" | .badValue => "badValue"
  | .unclosedBlock => "unclosedBlock" | .quotation => "quotation" | .unclear => "unclear"

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
def cardAlphabet : T := Limits.nameAlphabet.toList
def delimiterAlphabet : T := "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_".toList

def isCardName (v : T) : Bool :=
  let size := v.length
  decide (size > 0) && decide (size ≤ Limits.maxObjectIdBytes) && span v cardAlphabet == size

def isIdentifier (v : T) : Bool :=
  let size := v.length
  decide (size > 0) && span v identifier == size

def isAction (v : T) : Bool := v == ['?'] || isIdentifier v

def trimStart (v : T) : T := v.drop (span v blanks)
def trimEnd (v : T) : T := (v.reverse.dropWhile (blanks.contains ·)).reverse

def str (v : T) : String := String.mk v
def lit (s : String) : T := s.toList

/-- ASCII letters folded to lower case: actions and field names are read in any case
    (docs/FLEX.md §4 host 2); a card's name is kept as written and folded where it is compared. -/
def foldT (v : T) : T := v.map Char.toLower
def fold (s : String) : String := str (foldT s.toList)

/-- A word with one trailing `.` or `:` trimmed (`delvetalk garden plant.`). -/
def unmarked (v : T) : T :=
  if v.length > 1 && (v.getLast? == some '.' || v.getLast? == some ':') then v.dropLast else v

def looksLikeField (v : T) : Bool :=
  let colon := brk v [':']
  decide (colon > 0) && v.take colon != v && isIdentifier (foldT (v.take colon))

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
  let head := foldT ((text.drop indent).take 10)
  head == lit "delvetalk " || head == lit "delvetalk\t"


def tagged (text : T) (indent stop : Nat) : Bool :=
  decide (stop > indent + 3) && (text.drop indent).take 3 == lit "```" &&
    decide (span (text.drop (indent + 3)) blanks < stop - indent - 3)

partial def pastFence (text : T) : T :=
  if text.isEmpty then text else
  let indent := span text [' ', '\t']
  let stop := brk text ['\n']
  if (text.drop indent).take 3 == lit "```" then text.drop (stop + 1) else pastFence (text.drop (stop + 1))

/-- The world's square (genesis's commonplace): where a summons lands, and whose doors prose may name. -/
def townCard : String := "commonplace"

/-- The town's reads (`Surfaces.townReads`), written with no card or with inline fields after them (`delvetalk
    chronicle`, `delvetalk chronicle / day: 3`, `delvetalk map`, `delvetalk makings`): the square's spells of those names. -/
def townWords : List String := ["chronicle", "map", "makings"]

/-- The town's mending basket (world/objects/Mending.obend; docs/MENDING.md): `delvetalk report <words>` is its
    `report` with the words as `text`, from any card or thread; fields after `report` are its own. -/
def basketCard : String := "mending"

def heading (line rest : T) : Candidate :=
  let afterBlanks := trimStart line
  let cardEnd := brk afterBlanks [' ', '\t']
  let card := afterBlanks.take cardEnd
  let afterCard := trimStart (afterBlanks.drop cardEnd)
  if townWords.contains (str (foldT card)) && (afterCard.isEmpty || afterCard.take 1 == ['/']) then
    .stands townCard (str (foldT card)) afterCard rest else
  let actionEnd := brk afterCard [' ', '\t']
  let written := afterCard.take actionEnd
  let action := unmarked (foldT written)
  let tail := trimStart (afterCard.drop actionEnd)
  -- An action written with capitals is one only when what follows is a spell's (nothing, or inline
  -- fields): `Delvetalk Garden Plant` is a spell, "delvetalk Is The word" a sentence.
  let spellTail := tail.isEmpty || tail.take 1 == ['/'] || looksLikeField tail
  -- `delvetalk try`, alone on its line: the spells indented under it are tried, not cast (docs/POSTING.md §2;
  -- `Serve.postShaped` answers it before any world reads it).
  if foldT card == lit "try" && written.isEmpty then .stands "try" "try" [] rest else
  -- `delvetalk guide`, alone: the guide's contents, the library's page (docs/POSTING.md; deploy/genesis.py `guide_pages`).
  if foldT card == lit "guide" && written.isEmpty then .stands "library" "read" (lit "/ page: guide") rest else
  -- `delvetalk report <words>`: a report put in the mending basket, the words its `text` (fields, inline or below, are
  -- the report spell's own: `delvetalk report / about: bell/1 / text: …`).
  if foldT card == lit "report" then
    .stands basketCard "report" (if afterCard.isEmpty || afterCard.take 1 == ['/'] || looksLikeField afterCard then afterCard
      else lit "/ text: " ++ afterCard) rest else
  -- `delvetalk receipt / of: <slug or post>`: a receipt looked up, nothing written (`Serve.receiptAsked`).
  if foldT card == lit "receipt" && (written.isEmpty || written.take 1 == ['/']) then .stands "receipt" "receipt" afterCard rest else
  if !isCardName card || !isAction action || (foldT written != written && !spellTail) then .none
  else .stands (str card) (str action) tail rest

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
  if looksLikeField value then continued (str (foldT (value.take colon))) (trimStart (value.drop (colon + 1))) rest
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

/-- The cut is a `/` after a blank (or at the start) with a field after it: the second `/` of `at://did:plc:…`
    follows a `/`, so a URI in a value is never cut there. -/
partial def slashed (before rest : T) : Fields2 :=
  let cut := brk rest ['/']
  if cut == rest.length then segment (before ++ rest)
  else
    let head := rest.take cut
    let after := rest.drop (cut + 1)
    let prior := before ++ head
    if looksLikeField (trimStart after) && (prior.isEmpty || span (prior.drop (prior.length - 1)) blanks == 1) then
      both (segment prior) (slashed [] (trimStart after))
    else slashed (prior ++ ['/']) after

/-- The slashed form's leading values without a name (`plant / silver / a fern`): the segments before
    the first that has a colon; after a named field a ` / ` is part of its value. -/
def leading (tail : T) : List Binding × T :=
  let parts := (str tail).splitOn " / "
  let values := parts.takeWhile fun p => !p.any (· == ':')
  let rest := " / ".intercalate (parts.drop values.length)
  (values.filterMap fun v => let t := str (trimEnd (trimStart v.toList)); if t.isEmpty then none else some ⟨"", t⟩, rest.toList)

def inline (tail : T) : Fields2 :=
  if tail.isEmpty then .found []
  else if tail.take 1 == ['/'] then
    let (values, rest) := leading (trimStart (tail.drop 1))
    sequenced values (if (trimStart rest).isEmpty then .found [] else slashed [] (trimStart rest))
  else slashed [] tail

def isDelimiter (text : T) : Bool :=
  decide (text.length ≥ 1) && decide (text.length ≤ 32) && span text delimiterAlphabet == text.length

/-- The delimiter a field's value opens a block with (`<<END`), if it is one. -/
def blockValue (value : T) : Option T :=
  if value.take 2 == lit "<<" && isDelimiter (trimEnd (value.drop 2)) then some (trimEnd (value.drop 2)) else none

/-- The delimiter of the block a field line opens (`law: <<END`), if it opens one. -/
def blockOpener (line : T) : Option T :=
  let colon := brk line [':']
  if colon < line.length && looksLikeField line then blockValue (trimStart (line.drop (colon + 1))) else none

/-- A field's value that opens a code fence (`spween: ```spween`): its tag, if it does. -/
def fenceValue (value : T) : Option T :=
  let v := trimEnd (trimStart value)
  if v.take 3 == lit "```" && !(v.drop 3).any (· == '`') then some (v.drop 3) else none

/-- A field's value that begins `<<` and opens no block (`spween: <<=== start`, obend #1295): the opener as written. -/
def falseOpener (value : T) : Option T :=
  let v := trimEnd (trimStart value)
  -- A word after `<<` that is no delimiter (`<<end`, one past 32) stays the value as written; a scene's first line
  -- (`<<=== start`) or any other non-word opens nothing and says so.
  if v.take 2 == lit "<<" && (blockValue v).isNone && (v.drop 2).any (fun c => !(c.isAlphanum || c == '_')) then some v else none

def falseOpenerReason (name : String) (opener : T) : String :=
  s!"The block {str opener} for {name} opens nothing: a block opens with << and one word of capitals, digits or _ ({name}: <<END), its lines under it, and that word alone on its last line."

/-- The spell line's last inline field when its value opens a block (`delvetalk kind/room make / name: jar / spween:
    <<END`): the fields before it, its name and the delimiter. The block's lines follow the spell line, as they follow a
    field line that opens one. -/
def lastOpens (bs : List Binding) : Option (List Binding × String × T) := do
  let b ← bs.getLast?
  guard (!b.name.isEmpty)
  let d ← blockValue b.value.toList
  return (bs.dropLast, b.name, d)

/-- A block's last line: exactly its delimiter (a trailing carriage return allowed). -/
def closesBlock (delimiter line : T) : Bool :=
  line == delimiter || (line.take (line.length - 1) == delimiter && line.drop (line.length - 1) == ['\r'])

/-- The content of exactly one whole block or code fence; other text stays verbatim. -/
def unwrap (value : String) : String := Id.run do
  let lines := value.splitOn "\n"
  let lines := if lines.getLastD "" == "" then lines.dropLast else lines
  let opening := (lines.headD "").trimAscii.toString
  let closer := match blockValue opening.toList with
    | some delimiter => some (fun (line : String) => closesBlock delimiter line.toList)
    | none => if opening.startsWith "```" && !(opening.drop 3).toString.contains '`' then
        some (fun (line : String) => line.trimAscii.toString == "```") else none
  let some closes := closer | return value
  let body := lines.drop 1
  let some stop := body.findIdx? closes | return value
  if stop + 2 != lines.length then return value
  return "\n".intercalate (body.take stop)

mutual
partial def fieldLines (text : T) : Fields2 :=
  if text.isEmpty then .found [] else spellLine text (span text [' ', '\t']) (brk text ['\n'])

partial def spellLine (text : T) (indent stop : Nat) : Fields2 :=
  if tagged text indent stop then fieldLines (pastFence (text.drop (stop + 1)))
  else if decide (indent < stop) && isSpellAt text indent then
    match headingAt text indent stop with
    | .stands .. => if indent == 0 then .again text else fieldLines (text.drop (stop + 1))
    | .none => .found []
  else fieldLine text stop

partial def fieldLine (text : T) (stop : Nat) : Fields2 :=
  if stop == 0 then afterBlank (text.drop 1) else lineParts (text.take stop) (text.drop (stop - 1))

/-- After a blank line a value without a name is prose: the fields end at it (docs/FLEX.md §4 host 3). -/
partial def afterBlank (rest : T) : Fields2 :=
  let next := trimEnd (trimStart (rest.take (brk rest ['\n'])))
  if next.isEmpty || next.any (· == ':') || ["#", ">", "`"].any (lit · == next.take 1) || isSpellAt next 0
  then fieldLines rest else .stray [] rest

/-- Values without a name run on while their lines have no colon; any other line ends the fields, so
    prose after them never reads a later `name: value` line as a field. -/
partial def loose (rest : T) : Fields2 :=
  let stop := brk rest ['\n']
  let line := trimEnd (trimStart (rest.take stop))
  if line.isEmpty || line.any (· == ':') || ["#", ">", "`"].any (lit · == line.take 1) || isSpellAt line 0
  then .stray [] rest
  else consed ⟨"", str line⟩ (loose (rest.drop (stop + 1)))

partial def lineParts (line tail : T) : Fields2 :=
  let rest := tail.drop 2
  let first := line.take 1
  if span first blanks == 1 then lineParts (trimStart (trimEnd line)) tail
  else classify (if span (tail.take 1) blanks == 1 then trimEnd line else line) first rest

partial def classify (line first rest : T) : Fields2 :=
  if line.isEmpty then afterBlank rest
  else if first == ['#'] || first == ['>'] || (first == ['`'] && line.take 3 == lit "```") then
    fieldLines rest
  else if first == ['-'] && line == lit "---" then .found []
  else binding line rest

partial def binding (line rest : T) : Fields2 :=
  let colon := brk line [':']
  let name := line.take colon
  -- A line is a field only when it looks like one (`name: value`, the name an identifier), as
  -- `bareT` reads them: prose with a colon after the fields ends them (docs/FLEX.md §4 host 1).
  -- A line with no colon in the field lines is a value without a name, bound by type at fit.
  if !line.any (· == ':') then consed ⟨"", str line⟩ (loose rest)
  else if colon == 0 || name == line || !looksLikeField line then .stray [] rest
  else match blockOpener line with
    | some delimiter => block (str (foldT name)) delimiter rest []
    | none =>
      let value := trimStart (line.drop (colon + 1))
      match fenceValue value, falseOpener value with
      | some tag, _ => fenced (str (foldT name)) tag rest []
      | none, some opener => .bad (falseOpenerReason (str (foldT name)) opener)
      | none, none => consed ⟨str (foldT name), str value⟩ (fieldLines rest)

/-- A field whose value opens a code fence (`spween: ```spween`, kestrel's jar at obend #1299): the lines under it up
    to a line that is ``` are its value, as a `<<END` block's are. -/
partial def fenced (name : String) (tag rest : T) (lines : List T) : Fields2 :=
  if rest.isEmpty then
    .bad s!"The block ```{str tag} for {name} needs a last line that is exactly ```."
  else
    let line := rest.take (brk rest ['\n'])
    let after := rest.drop (brk rest ['\n'] + 1)
    if trimEnd (trimStart line) == lit "```" then consed ⟨name, "\n".intercalate (lines.reverse.map str)⟩ (fieldLines after)
    else fenced name tag after (line :: lines)

partial def block (name : String) (delimiter rest : T) (lines : List T) : Fields2 :=
  if rest.isEmpty then
    .bad s!"The block <<{str delimiter} for {name} needs a last line that is exactly {str delimiter}."
  else
    let line := rest.take (brk rest ['\n'])
    let after := rest.drop (brk rest ['\n'] + 1)
    if closesBlock delimiter line then
      let value := "\n".intercalate (s!"<<{str delimiter}" :: (lines.reverse.map str ++ [str line]))
      consed ⟨name, unwrap value⟩ (fieldLines after)
    else block name delimiter after (line :: lines)
end

/-- A spell line's inline fields, then the lines under it: a block when its last inline field opens one (`lastOpens`),
    else field lines. -/
def headed (tail rest : T) : Fields2 :=
  match inline tail with
  | .found bs => match lastOpens bs with
    | some (before, name, delimiter) => sequenced before (block name delimiter rest [])
    | none => match bs.getLast? with
      | some b => match fenceValue b.value.toList, falseOpener b.value.toList with
        | some tag, _ => if b.name.isEmpty then sequenced bs (fieldLines rest) else sequenced bs.dropLast (fenced b.name tag rest [])
        | none, some opener => if b.name.isEmpty then sequenced bs (fieldLines rest) else .bad (falseOpenerReason b.name opener)
        | none, none => sequenced bs (fieldLines rest)
      | none => sequenced bs (fieldLines rest)
  | other => other

/-- The delimiter of the block a spell line opens with its last inline field, if it does. -/
def lineOpens (line : T) : Option T :=
  match headingAt line 0 line.length with
  | .stands _ _ tail _ => match inline tail with
    | .found bs => (lastOpens bs).map (·.2.2)
    | _ => none
  | .none => none

/-- A spell line is cast only at the margin: an indented `delvetalk …` line is a quotation or an example
    (every card prints its spells indented), never a spell. -/
partial def parseFrom (text : T) (fielded : Bool) : Parsed :=
  if text.isEmpty then .notASpell "No delvetalk line; the spell is the last unquoted one." fielded
  else
    let indent := span text [' ', '\t']
    let stop := brk text ['\n']
    if tagged text indent stop then parseFrom (pastFence (text.drop (stop + 1))) fielded
    else if indent == 0 && decide (0 < stop) && isSpellAt text 0 then
      match headingAt text 0 stop with
      | .none => parseFrom (text.drop (stop + 1)) fielded
      | .stands c a tail rest => spelled c a (headed tail rest)
    else parseFrom (text.drop (stop + 1)) (fielded || fieldHead text indent stop)
where
  spelled (card action : String) : Fields2 → Parsed
    | .found bs => .spell card action bs
    | .bad reason => .notASpell reason true
    | .again text => parseFrom text false
    | .stray bs rest => seekAfter rest (.spell card action bs)
  seekAfter (text : T) (otherwise : Parsed) : Parsed :=
    if text.isEmpty then otherwise else
    let indent := span text [' ', '\t']
    let stop := brk text ['\n']
    if tagged text indent stop then seekAfter (pastFence (text.drop (stop + 1))) otherwise
    else if indent == 0 && decide (0 < stop) && isSpellAt text 0 then
      match headingAt text 0 stop with
      | .none => seekAfter (text.drop (stop + 1)) otherwise
      | .stands c a tail rest => spelled c a (headed tail rest)
    else seekAfter (text.drop (stop + 1)) otherwise

/-! ## Render: values as data

`render` writes a spell whose fields hold arbitrary text so that `parse` reads back exactly those
fields. A value goes inline (`/ name: value`) only when `inlineSafe` says no rule of `slashed`,
`piece` or `more` could cut it: it is one printable line with no edge blank, no ` /` (the cut of
`slashed`), no leading `/`, no comma-led piece that looks like a field (`more`), and is not itself a
block's opener (`<<END`, which `headed` and `binding` read as one). From the first
field that is not inline-safe on, each field takes a line of its own: `name: value` when the value is
inline-safe (`binding` takes the whole line after the colon), else a `name: <<DELIM` block (`block`
takes every line verbatim up to `closesBlock`), the delimiter chosen so that no line of the value
closes it. `renderChecked` is the gate the host uses: it parses the text back. -/

def slashAfterBlank : T → Bool
  | ' ' :: '/' :: _ => true
  | _ :: rest => slashAfterBlank rest
  | [] => false

def inlineSafe (value : String) : Bool :=
  let t := value.toList
  !t.isEmpty && (blockValue t).isNone && t.all (fun c => c.toNat ≥ 32 && c.toNat != 127) &&
    t.head? != some ' ' && t.getLast? != some ' ' && t.head? != some '/' && !slashAfterBlank t &&
    ((value.splitOn ",").drop 1).all fun p => !p.any (· == ':')

/-- A delimiter (`delimiterAlphabet`, at most 32) that no line of `value` closes. One of
    `END`, `END_0` .. `END_n` for `n` the value's line count: a line closes at most one of them. -/
def blockDelimiter (value : String) : String :=
  let lines := (value.splitOn "\n").map String.toList
  let candidates := "END" :: (List.range (lines.length + 1)).map fun n => s!"END_{n}"
  (candidates.find? fun d => !lines.any (closesBlock d.toList ·)).getD "END"

def renderLine (b : Binding) : String :=
  if inlineSafe b.value then s!"{b.name}: {b.value}" else
  let d := blockDelimiter b.value
  s!"{b.name}: <<{d}\n{b.value}\n{d}"

/-- How many leading fields go inline: named ones with an identifier name and an inline-safe value,
    after at most nameless safe values without a colon (`leading`). -/
def inlineCount (named : Bool) : List Binding → Nat
  | [] => 0
  | b :: rest =>
    if b.name.isEmpty then
      (if !named && inlineSafe b.value && !b.value.any (· == ':') then inlineCount named rest + 1 else 0)
    else if isIdentifier b.name.toList && inlineSafe b.value then inlineCount true rest + 1 else 0

def render (card action : String) (fields : List Binding) : String :=
  let n := inlineCount false fields
  let segment := fun (b : Binding) => if b.name.isEmpty then b.value else s!"{b.name}: {b.value}"
  s!"delvetalk {card} {action}" ++ String.join ((fields.take n).map fun b => " / " ++ segment b) ++
    String.join ((fields.drop n).map fun b => "\n" ++ renderLine b)

/-- The commonplace's head line as `Menu.trieHead` writes it: its first sentence the door count,
    `One door.` or `<count> doors.` (`Eight doors. Indented lines are typed back whole; …`). -/
def doorsHead (t : String) : Bool :=
  match t.splitOn ". " with
  | first :: _ :: _ => first == "One door" || (match first.splitOn " " with | [_, "doors"] => true | _ => false)
  | _ => false

/-- A card's header line, as cards print them: `✾ <TITLE>`, the commonplace's door count
    (`doorsHead`), a kind's `KIND <name>: …`, or a line ending `Make one:`. -/
def cardHeader (line : String) : Bool :=
  let t := line.trimAscii.toString
  t.startsWith "✾ " || doorsHead t || t.startsWith "KIND " || t.endsWith "Make one:"

/-- A text holding a card's header line beside a `delvetalk` line (at any indent) quotes that card. -/
def quotes (text : String) : Option String := do
  let lines := text.splitOn "\n"
  let header ← lines.find? cardHeader
  guard (lines.any fun l => isSpellAt (l.trimAsciiStart.toString.toList) 0)
  return s!"This quotes a card ({(header.trimAscii.toString.take 40).toString}): its spells are examples, so none is cast. Write the spell alone, at the start of a line."

/-- Where `segments` is in the text: in the open, inside a tagged code fence, or inside a field's
    `<<TAG` block. A `delvetalk` line inside a fence or block is text, as the parser reads it. -/
inductive Scan where
  | open_
  | fence
  | block (delimiter : T)

/-- The spells of a text, one per line that starts `delvetalk` at the margin (an indented line is
    none, as is any inside a tagged code fence or a `<<TAG` block), each with the lines after it up to
    the next; prose before the first is dropped. A post's several spells (`runSpells`) and a model's
    (`interpretVerdict`) are split here. `probe` is how a line is read for its head: a plan's lines with their
    holes filled (`planProbe`). -/
def segments (text : String) (probe : String → String := id) : List String :=
  let lines := text.splitOn "\n"
  let (segments, current, _) := lines.foldl
    (fun (acc : List String × Option (List String) × Scan) line =>
      let (done, open_, scan) := acc
      let chars := line.toList
      let indent := span chars [' ', '\t']
      let append := fun (o : Option (List String)) => o.map (· ++ [line])
      match scan with
      | .fence =>
          (done, append open_, if (chars.drop indent).take 3 == lit "```" then .open_ else .fence)
      | .block delimiter =>
          (done, append open_, if closesBlock delimiter chars then .open_ else .block delimiter)
      | .open_ =>
          let head := (probe line).toList
          if isSpellAt head 0 && (match headingAt head 0 head.length with | .stands .. => true | .none => false) then
            (match open_ with | some ls => done ++ ["\n".intercalate ls] | none => done, some [line],
              match lineOpens (trimEnd head) with | some delimiter => .block delimiter | none => .open_)
          else if tagged chars indent chars.length then (done, append open_, .fence)
          else match open_ with
            | some _ =>
                (done, append open_,
                  match blockOpener (trimEnd (trimStart chars)) with
                  | some delimiter => .block delimiter
                  | none => .open_)
            | none => (done, none, .open_)) ([], none, .open_)
  match current with
  | some ls => segments ++ ["\n".intercalate ls]
  | none => segments

/-- A post that is one spell block and nothing else: its non-blank lines (inside one code fence, or
    bare) are a `delvetalk` line and field lines, every one starting with the first's indent. Dedented,
    it is cast as written (a Zulip code block, a spell pasted with its indent); an indented spell among
    other lines stays an example. -/
def wholeSpell (text : String) : Option String := do
  let all := text.splitOn "\n"
  let blank := fun (l : String) => l.trimAscii.isEmpty
  let opens := fun (l : String) => ["```", "```text", "```delvetalk"].contains l.trimAscii.toString
  let shut := fun (l : String) => l.trimAscii.toString == "```"
  let body := all.filter (!blank ·)
  let fenced := body.length ≥ 3 && opens (body.headD "") && shut (body.getLastD "")
  let inner := if fenced then
      let from_ := all.findIdx opens
      let to := all.length - 1 - (all.reverse.findIdx shut)
      (all.drop (from_ + 1)).take (to - from_ - 1)
    else all
  let lines := inner.filter (!blank ·)
  let first ← lines.head?
  let indent := String.ofList (first.toList.takeWhile (fun c => c == ' ' || c == '\t'))
  guard (fenced || !indent.isEmpty)
  guard (lines.all (·.startsWith indent))
  let dedent := fun (l : String) => if l.startsWith indent then (l.drop indent.length).toString else l
  guard (isSpellAt (dedent first).toList 0)
  guard ((text.splitOn "<<").length > 1 || (lines.drop 1).all fun l => looksLikeField (dedent l).toList)
  return "\n".intercalate (inner.map dedent)

/-- The spell a reply means: its `delvetalk <card> <action>` line at the margin with the fields that
    follow (inline after the action, or one per line; a later spell line at the margin replaces it), a
    quotation of a card (`quotes`), a post that is one spell block (`wholeSpell`), or why there
    is none. -/
def parse (text : String) : Parsed :=
  match quotes text, wholeSpell text with
  | some reason, _ => .quotation reason
  | none, some spell => parseFrom spell.toList false
  | none, none => parseFrom text.toList false

/-- A plan's line as read for its head: each hole `{made N}` (`TurnLoop.fillHoles`) read as a card name. -/
def planProbe (line : String) : String :=
  (line.splitOn "{made ").foldl (fun (acc : String × Bool) part =>
    if !acc.2 then (part, true) else
    match part.splitOn "}" with
    | n :: rest => (acc.1 ++ "made-" ++ n ++ "}".intercalate rest, true)
    | [] => (acc.1 ++ part, true)) ("", false) |>.1

/-- A plan's head (docs/HOST-HANDOFF.md 5.203): `delvetalk plan` at the margin, in any case, a trailing `:` or `.`
    allowed, nothing after it. -/
def isPlanHead (line : String) : Bool :=
  let f := fold line.trimAsciiEnd.toString
  !(line.startsWith " " || line.startsWith "\t") && (f == "delvetalk plan" || f == "delvetalk plan:" || f == "delvetalk plan.")

/-- A code fence tagged `plan` opens a plan as its head does. -/
def isPlanFence (line : String) : Bool := fold line.trimAscii.toString == "```plan"

/-- The acts of a plan, when the post is one (docs/HOST-HANDOFF.md 5.203): a post with a plan's head (`isPlanHead`)
    or a fence tagged `plan` (`isPlanFence`) outside any other fence. Its acts are every spell of the post, as
    `segments` splits them, the plan fence's lines read as written at the margin (dedented by its first line's
    indent) and the head dropped: one plan is the post's spells, run as one turn (`runPlan`). Lines before the first
    spell (prose, an `if:` line) are no act. -/
def plan (text : String) : Option (List String) := Id.run do
  let lines := text.splitOn "\n"
  let mut out : Array String := #[]
  let mut found := false
  -- `none` in the open; `some none` inside another fence; `some (some body)` inside the plan's fence.
  let mut fence : Option (Option (Array String)) := none
  for line in lines do
    match fence with
    | some none =>
      out := out.push line
      if (line.trimAsciiStart.toString.take 3).toString == "```" then fence := none
    | some (some body) =>
      if line.trimAscii.toString == "```" then
        let first := (body.find? (!·.trimAscii.isEmpty)).getD ""
        let indent := String.ofList (first.toList.takeWhile (fun c => c == ' ' || c == '\t'))
        out := out ++ body.map fun l => if l.startsWith indent then (l.drop indent.length).toString else l
        fence := none
      else fence := some (some (body.push line))
    | none =>
      if isPlanFence line then found := true; fence := some (some #[])
      else if isPlanHead line then found := true
      else
        out := out.push line
        if (line.trimAsciiStart.toString.take 3).toString == "```" then fence := some none
  if !found then return none
  if let some (some body) := fence then out := out ++ body
  return some (segments ("\n".intercalate out.toList) planProbe)

/-- `render`, kept only when `parse` reads it back as exactly this spell and `segments` finds it one
    spell: the host's gate for a spell built from text it does not control. -/
def renderChecked (card action : String) (fields : List Binding) : Option String :=
  let text := render card action fields
  if parse text == .spell card action fields && (segments text).length == 1 then some text else none

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
    else ⟨str (foldT (line.take (brk line [':']))), str (trimStart (line.drop (brk line [':'] + 1)))⟩ :: bareT rest

def bare (text : String) : List Binding := bareT text.toList

/-- On a reply addressed to `card` (docs/FLEX.md §4 host 2), the text with its first line written as a
    spell line when that line names one of `actions` (or `?`), alone or after the card's name, with
    nothing after it but inline fields (`/ name: value`); a field line, a `>` quotation or a sentence is
    not one. -/
def addressedText (text card : String) (actions : List String) : Option String := do
  let lines := text.splitOn "\n"
  let i ← lines.findIdx? fun l => !(trimStart l.toList).isEmpty
  let line := trimEnd (trimStart (lines[i]!).toList)
  guard (line.take 1 != ['>'] && !looksLikeField line)
  let words := (str line).splitOn " " |>.filter (· != "")
  let named := fun (w : String) => let a := str (unmarked (foldT w.toList)); if a == "?" || actions.contains a then some a else none
  let (action, used) ← match words with
    | w :: rest => match named w with
      | some a => some (a, 1)
      | none => match rest with
        | w2 :: _ => if fold w == fold card then (named w2).map (·, 2) else none
        | [] => none
    | [] => none
  let tail := " ".intercalate (words.drop used)
  guard (tail.isEmpty || tail.startsWith "/")
  return "\n".intercalate (lines.take i ++ [s!"delvetalk {card} {action} {tail}"] ++ lines.drop (i + 1))

/-- `parse`, and on a reply addressed to a card, the spell its first line names without `delvetalk`. -/
def parseFor (text : String) (addressee : Option (String × List String)) : Parsed :=
  match parse text, addressee with
  | p@(.spell ..), _ => p
  | p@(.quotation _), _ => p
  | p@(.notASpell reason _), some (card, actions) =>
    if reason.startsWith "The block <<" then p else
    match addressedText text card actions with
    | some t => parse t
    | none => p
  | p, none => p

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
      if value.length < min || value.length > max then wrong s!"{field.name} takes {min} to {max} characters; this one is {value.length}."
      else none
  | .object min max =>
      if value.length < min || value.length > max || !(value.isEmpty && min == 0 || isCardName value.toList) then
        wrong s!"{field.name} takes an object id of {min} to {max} characters."
      else none
  | .natural min max =>
      match number value.toList with
      | none => wrong s!"{field.name} takes a natural number in plain digits."
      | some v => if v < min || v > max then wrong s!"{field.name} takes {min} to {max}; this one is {v}." else none
  | .choice options =>
      if options.contains value then none
      else wrong s!"{field.name} is one of: {", ".intercalate options}"

def named (name : String) (b : Binding) : Bool := b.name == name

def audit (fields : List Field) : List Binding → Option (Clause × String)
  | [] => none
  | b :: rest =>
      match fields.find? (·.name == b.name) with
      | none => audit fields rest
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
  | .text .. | .object .. => .text value
  | .natural .. => .natural ((number value.toList).getD 0)
  | .choice .. => .choice value

def isText : Kind → Bool
  | .text .. | .object .. => true
  | _ => false

/-- A text or object field whose bound starts at 0 may be left out of a spell: it reads as the empty text; a natural one
    from 0, as 0 (`lines` with no `from` is the newest page). -/
def Field.optional (f : Field) : Bool :=
  match f.kind with
  | .text 0 _ | .object 0 _ | .natural 0 _ => true
  | _ => false

def rebound (bindings : List Binding) (form : Form) : List Binding :=
  if bindings.any (named form.action) then
    match form.fields.find? (fun f => isText f.kind && !bindings.any (named f.name)) with
    | none => bindings
    | some f => bindings.map fun b => if b.name == form.action then { b with name := f.name } else b
  else bindings

def isNatural : Kind → Bool
  | .natural .. => true
  | _ => false

/-- Values without a name (docs/FLEX.md §4 host 3), bound in order to the open field they fit: a
    choice whose option the value is (folded; the option as the form writes it), else digits to the one
    open natural, else the one open text field. A value that fits none, or more than one natural or text,
    is dropped: fit then names what is still missing. -/
def boundByType (fields : List Field) (bs : List Binding) : List Binding :=
  (bs.filter (·.name == "")).foldl (fun acc b =>
    let open_ := fields.filter fun f => !acc.any (named f.name)
    -- `seed fern` is a field with its colon missing, not a value.
    let first := fold ((b.value.splitOn " ").headD "")
    if fields.any (·.name == first) then acc else
    let option := open_.findSome? fun f => match f.kind with
      | .choice os => (os.find? (fold · == fold b.value)).map (f.name, ·)
      | _ => none
    match option with
    | some (n, o) => acc ++ [⟨n, o⟩]
    | none =>
      let kinds := if (number b.value.toList).isSome && (open_.filter (isNatural ·.kind)).length == 1
        then open_.filter (isNatural ·.kind) else open_.filter (isText ·.kind)
      match kinds with
      | [f] => acc ++ [⟨f.name, b.value⟩]
      | _ => acc) (bs.filter (·.name != ""))

/-- A field name is read in any case (folded as the spell is parsed); the form's own spelling binds it
    (`ringAt: 3` to a form field `ringAt`, docs/AUTHORING.md §6.1). -/
def spelled (form : Form) (b : Binding) : Binding :=
  match form.fields.find? (fold ·.name == fold b.name) with
  | some f => { b with name := f.name }
  | none => b

/-- A spell's bindings as `form` reads them: names in the form's spelling (`spelled`), the action-named
    line to its text field (`rebound`), the values without a name by type. -/
def bind (form : Form) (bs : List Binding) : List Binding :=
  boundByType form.fields (rebound (bs.map (spelled form)) form)

/-- A name a field could have: one word of letters, digits, `_` and `-`. -/
def fieldWord (name : String) : Bool :=
  !name.isEmpty && name.all fun c => c.isAlphanum || c == '_' || c == '-'

def clauseOfReason (reason : String) : Clause :=
  if reason.startsWith "The block <<" then .unclosedBlock else .noAction

def proposed (form : Form) (bindings : List Binding) : Fit :=
  match audit form.fields bindings with
  | some (clause, reason) => .refused clause reason
  | none =>
      let needs := (form.fields.filter fun f => !f.optional && !bindings.any (named f.name)).map (·.name)
      if needs.isEmpty then
        .proposal form.card form.action
          (form.fields.map fun f => ⟨f.name, typed f.kind (valueOf bindings f.name)⟩)
      else .unclear needs

def fit (parsed : Parsed) (form : Form) : Fit :=
  match parsed with
  | .notASpell reason _ => .refused (clauseOfReason reason) reason
  | .quotation reason => .refused .quotation reason
  | .spell card action fields =>
      if fold card != fold form.card || action != form.action then
        .refused .otherCard s!"This card answers {form.card} {form.action}."
      else
        -- A binding whose name the form lacks ends the fields when no field the form names follows it
        -- (`hob: still owed …` in the reply's prose, the second playtest's D7); with one after it, it is
        -- a misspelled field and the fields behind it would be lost, so it is refused.
        let bound := bind form fields
        let known := fun (b : Binding) => form.fields.any (·.name == b.name)
        let bindings := bound.takeWhile known
        let stray := bound.drop bindings.length
        -- A stray one-word name before a spell that still needs a field is that field misnamed (`say / line:` to a
        -- verb that takes `text`, obend #1116): refused by name, never read as the spell missing it.
        match stray.head? with
        | some b =>
            let unknown := fun (_ : Unit) => Fit.refused .unknownField
                s!"{b.name} is not a field of {form.card} {form.action}; its fields are {", ".intercalate (form.fields.map (·.name))}."
            if stray.any known then unknown ()
            else match proposed form bindings with
              | .unclear _ => if fieldWord b.name then unknown () else proposed form bindings
              | fit => fit
        | none => proposed form bindings

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
            | .variant "object" (.record k) => do
                let .natural a ← k.lookup "min" | none
                let .natural b ← k.lookup "max" | none
                pure (Kind.object a b)
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
        match k.getObjVal? "object" with
        | .ok t => pure (Kind.object (← t.getObjValAs? Nat "min") (← t.getObjValAs? Nat "max"))
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
  | .quotation reason => [("quotation", Json.mkObj [("reason", toJson reason)])]

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
  let addressee ← match request.getObjVal? "addressee" with
    | .ok a => do
      let actions ← (← a.getObjVal? "actions").getArr?
      pure (some (← a.getObjValAs? String "card", ← actions.toList.mapM (·.getStr?)))
    | .error _ => pure none
  let parsed := parseFor text addressee
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
#guard parse "delvetalk garden/bell/2 water / text: WC-01, first light" ==
  .spell "garden/bell/2" "water" [⟨"text", "WC-01, first light"⟩]
#guard parse "delvetalk w c\nsource: <<BEND\nline\n" ==
  .notASpell "The block <<BEND for source needs a last line that is exactly BEND." true
#guard fit (parse "delvetalk garden-1 plant\nplant: a fern") plant == .unclear ["colour"]
-- A `text 0..N` field may be left out: it reads as the empty text.
#guard fit (parse "delvetalk kinds make / name: lamp") ⟨"kinds", "make", [⟨"name", .text 1 80⟩, ⟨"law", .text 0 4096⟩]⟩ ==
  .proposal "kinds" "make" [⟨"name", .text "lamp"⟩, ⟨"law", .text ""⟩]
#guard fit (parse "delvetalk garden-1 plant\nplant: a fern\nseed: moss\ncolour: silver") plant ==
  .refused .unknownField "plant is not a field of garden-1 plant; its fields are colour, seed."
#guard fit (parse "delvetalk garden-1 plant\nvoce: lunar\nseed: moss\ncolour: silver") plant ==
  .refused .unknownField "voce is not a field of garden-1 plant; its fields are colour, seed."
-- A line whose name the form lacks ends the fields: the second playtest's 69082, a `hob:` line after the spell.
#guard fit (parse "delvetalk library laws / card: prereg\nhob: still owed — a law that parses") ⟨"library", "laws", [⟨"card", .text 1 128⟩]⟩ ==
  .proposal "library" "laws" [⟨"card", .text "prereg"⟩]
#guard fit (parse "delvetalk garden-2 plant") plant == .refused .otherCard "This card answers garden-1 plant."
#guard bare "plant: a fern\n> x: y\n" == [⟨"plant", "a fern"⟩]
#guard plan "delvetalk plan\ndelvetalk kinds make / name: lamp\ndelvetalk {made 1} make\n" ==
  some ["delvetalk kinds make / name: lamp", "delvetalk {made 1} make\n"]
#guard plan "make two:\n```plan\n  delvetalk a b\n  delvetalk c d / x: y\n```\nthanks" ==
  some ["delvetalk a b", "delvetalk c d / x: y\nthanks"]
#guard plan "```text\ndelvetalk plan\ndelvetalk a b\n```\n" == none
#guard plan "delvetalk a b\ndelvetalk c d" == none

#guard render "me" "note" [⟨"text", "bell/2 has 2 rains, the last by kim"⟩] == "delvetalk me note / text: bell/2 has 2 rains, the last by kim"
#guard render "me" "note" [⟨"text", "a / to: eve"⟩] == "delvetalk me note\ntext: <<END\na / to: eve\nEND"
-- A block opened by the spell line's last inline field (the jar of 2026-10-14): its lines are the value, as under a
-- field line; the fields after the block follow it.
#guard parse "delvetalk kind/room make / name: jar / spween: <<END\n---\nid: jar\n---\n=== start\nHoney.\n* [Taste] -> start\nEND" ==
  .spell "kind/room" "make" [⟨"name", "jar"⟩, ⟨"spween", "---\nid: jar\n---\n=== start\nHoney.\n* [Taste] -> start"⟩]
#guard parse "delvetalk w c / a: 1 / b: <<B\nx\nB\nc: 2" == .spell "w" "c" [⟨"a", "1"⟩, ⟨"b", "x"⟩, ⟨"c", "2"⟩]
#guard parse "delvetalk w c / b: <<B\nx\n" == .notASpell "The block <<B for b needs a last line that is exactly B." true
#guard unwrap "<<END\n=== start\nHoney.\nEND\n" == "=== start\nHoney."
#guard parse "delvetalk room/1 rescene\nspween: ```spween\n=== start\nHoney.\n```" == .spell "room/1" "rescene" [⟨"spween", "=== start\nHoney."⟩]
#guard parse "delvetalk room/1 rescene / spween: ```spween\n=== start\nHoney.\n```" == .spell "room/1" "rescene" [⟨"spween", "=== start\nHoney."⟩]
#guard parse "delvetalk room/1 rescene\nspween: <<=== start\nHoney.\nEND" == .notASpell "The block <<=== start for spween opens nothing: a block opens with << and one word of capitals, digits or _ (spween: <<END), its lines under it, and that word alone on its last line." true
#guard unwrap "```spween\n=== start\nHoney.\n```" == "=== start\nHoney."
#guard unwrap "```\n lead\n\n```\n" == " lead\n"
#guard unwrap "<<END\n```spween\nHoney.\n```\nEND" == "```spween\nHoney.\n```"
#guard ["<<END", "<<END\nHoney.", "```spween\nHoney.", "Before <<END\nHoney.\nEND",
  "<<END\nHoney.\nEND\nAfter", "<<END\nHoney.\nEND\n<<END\nMore.\nEND",
  "Before\n```spween\nHoney.\n```", "```spween\nHoney.\n```\nAfter",
  "```spween\nHoney.\n```\n```spween\nMore.\n```"].all fun v => unwrap v == v
#guard segments "delvetalk w c / b: <<B\ndelvetalk p q\nB\ndelvetalk r s" == ["delvetalk w c / b: <<B\ndelvetalk p q\nB", "delvetalk r s"]
#guard (renderChecked "me" "note" [⟨"text", "<<END"⟩]).isSome
#guard ["", " lead", "trail ", "a\nb", "END", "END\nEND_0\nEND_1", "<<END", "x\ndelvetalk p s / o: e", "---", "# h", "> q", "```", "a, b: c", "/ x", "tab\tx", "r\r\nEND\r"].all fun v =>
  renderChecked "me" "note" [⟨"a", "q"⟩, ⟨"text", v⟩, ⟨"z", "w"⟩] == some (render "me" "note" [⟨"a", "q"⟩, ⟨"text", v⟩, ⟨"z", "w"⟩])

end Delvetalk.Host.Spell
