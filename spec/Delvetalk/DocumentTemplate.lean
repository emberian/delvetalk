/- Hosted document literal sugar. No evaluator or new core forms: expansion uses
the explicitly imported Document module and ordinary checked Bend expressions. -/
import Lean
namespace Delvetalk.DocumentTemplate
open Lean
set_option autoImplicit false

structure Position where
  byte : Nat := 0
  line : Nat := 1
  deriving Inhabited, Repr

structure Piece where
  text : String
  origin : Position
  exact : Bool := false

structure Expansion where
  source : String
  origins : Array Position

def advance (p : Position) (c : Char) : Position :=
  ⟨p.byte + c.utf8Size, p.line + if c == '\n' then 1 else 0⟩

def advanceText (p : Position) (s : List Char) : Position := s.foldl advance p

def quoted (s : List Char) : String := (toJson (String.ofList s)).compress

structure Cursor where
  rest : List Char
  position : Position := {}
  deriving Inhabited

def consume (s : Cursor) (n : Nat) : Cursor :=
  ⟨s.rest.drop n, advanceText s.position (s.rest.take n)⟩

def begins (s : Cursor) (marker : String) : Bool := marker.toList.isPrefixOf s.rest

abbrev Scan := StateT Cursor (Except String)

def refuse {α : Type} (message : String) : Scan α := do
  let s ← get
  throw ("document template line " ++ toString s.position.line ++ ": " ++ message)

def takeChars (n : Nat) : Scan (List Char) := do
  let s ← get
  set (consume s n)
  return s.rest.take n

-- Quoted Bend expressions and comments are never searched for template markers.
def stringToken : Nat → Scan (List Char)
  | 0 => refuse "string capacity"
  | fuel + 1 => do
    let s ← get
    match s.rest with
    | [] => refuse "unterminated string"
    | '"' :: _ => takeChars 1
    | '\\' :: _ =>
      let escaped ← takeChars 2
      return escaped ++ (← stringToken fuel)
    | _ =>
      let char ← takeChars 1
      return char ++ (← stringToken fuel)

-- Holes end only at their own delimiter outside nested records/parentheses and
-- strings. Their content is parsed by the existing Bend parser after lowering.
def hole (closing : String) : Nat → Nat → Scan (List Piece)
  | 0, _ => refuse "interpolation capacity"
  | fuel + 1, depth => do
    let s ← get
    if depth == 0 && begins s closing then
      discard <| takeChars closing.length
      return []
    match s.rest with
    | [] => refuse ("unterminated interpolation; expected " ++ closing)
    | '"' :: _ =>
      discard <| takeChars 1
      let text := '"' :: (← stringToken fuel)
      return ⟨String.ofList text, s.position, true⟩ :: (← hole closing fuel depth)
    | c :: _ =>
      discard <| takeChars 1
      let nextDepth := if c == '{' || c == '(' then depth + 1
        else if c == '}' || c == ')' then depth - 1 else depth
      return ⟨c.toString, s.position, true⟩ :: (← hole closing fuel nextDepth)

def textPiece (literal : List Char) (origin : Position) : List Piece :=
  if literal.isEmpty then [] else [⟨"Document.text(" ++ quoted literal ++ ")", origin, false⟩]

-- Backslash escapes only a delimiter or another backslash; all other backslashes
-- are literal. This preserves ordinary prose, tabs, newlines, Unicode and quotes.
def literal : Nat → List Char → Position → Scan (List (List Piece))
  | 0, _, _ => refuse "literal capacity"
  | fuel + 1, reversed, origin => do
    let s ← get
    if begins s "\"\"\"" then
      discard <| takeChars 3
      let p := textPiece reversed.reverse origin
      return if p.isEmpty then [] else [p]
    if begins s "\\\"\"\"" || begins s "\\{{" || begins s "\\{%" || begins s "\\\\" then
      discard <| takeChars 1
      let escapedState ← get
      let n := if begins escapedState "\"\"\"" then 3 else if begins escapedState "\\" then 1 else 2
      let escaped ← takeChars n
      return ← literal fuel (escaped.reverse ++ reversed) origin
    let textHole := begins s "{{"
    if textHole || begins s "{%" then
      discard <| takeChars 2
      let contents ← hole (if textHole then "}}" else "%}") fuel 0
      if (String.join (contents.map (·.text))).trimAscii.toString.isEmpty then refuse "empty interpolation"
      let wrapper := if textHole then "Document.text(" else "("
      let fragment := [⟨wrapper, s.position, false⟩] ++ contents ++ [⟨")", s.position, false⟩]
      let remaining ← literal fuel [] (← get).position
      let p := textPiece reversed.reverse origin
      return (if p.isEmpty then [] else [p]) ++ [fragment] ++ remaining
    match s.rest with
    | [] => refuse "unterminated doc triple quote"
    | c :: _ =>
      discard <| takeChars 1
      literal fuel (c :: reversed) origin

def joinFragments (origin : Position) : List (List Piece) → List Piece
  | [] => [⟨"Document.empty()", origin, false⟩]
  | [fragment] => fragment
  | fragment :: rest => [⟨"Document.concat(", origin, false⟩] ++ fragment ++
      [⟨",", origin, false⟩] ++ joinFragments origin rest ++ [⟨")", origin, false⟩]

def scan : Nat → Bool → Scan (List Piece)
  | 0, _ => refuse "source capacity"
  | fuel + 1, boundary => do
    let s ← get
    if boundary && begins s "doc\"\"\"" then
      discard <| takeChars 6
      let fragments ← literal fuel [] (← get).position
      return joinFragments s.position fragments ++ (← scan fuel true)
    match s.rest with
    | [] => return []
    | '"' :: _ =>
      discard <| takeChars 1
      let text := '"' :: (← stringToken fuel)
      return ⟨String.ofList text, s.position, true⟩ :: (← scan fuel true)
    | '#' :: _ =>
      let comment := s.rest.takeWhile (· != '\n')
      discard <| takeChars comment.length
      return ⟨String.ofList comment, s.position, true⟩ :: (← scan fuel true)
    | c :: _ =>
      discard <| takeChars 1
      let word := c.isAlphanum || c == '_'
      return ⟨c.toString, s.position, true⟩ :: (← scan fuel (!word))

def lower (source : String) : Except String Expansion := do
  -- Old source is an identity projection, including its diagnostic behavior.
  if (source.splitOn "doc\"\"\"").length <= 1 then
    return ⟨source, #[]⟩
  let (pieces, ending) ← (scan (source.length + 1) true).run ⟨source.toList, {}⟩
  let mut origins := #[]
  for piece in pieces do
    let mut p := piece.origin
    for c in piece.text.toList do
      for _ in [0:c.utf8Size] do origins := origins.push p
      if piece.exact then p := advance p c
  return ⟨String.join (pieces.map (·.text)), origins.push ending.position⟩

def Expansion.position (e : Expansion) (byte : Nat) : Position :=
  (e.origins[byte]?).getD ((e.origins.back?).getD ⟨byte, 1⟩)

def remap (e : Expansion) : Nat → Json → Json
  | 0, value => value
  | fuel + 1, .arr values => .arr (values.map (remap e fuel))
  | fuel + 1, .obj fields =>
    let entries := fields.toList
    match ((Json.obj fields).getObjValAs? Nat "start").toOption,
        ((Json.obj fields).getObjValAs? Nat "end").toOption,
        ((Json.obj fields).getObjValAs? Nat "line").toOption with
    | some start, some stop, some _ =>
      let a := e.position start
      let b := e.position stop
      Json.mkObj [("start", toJson a.byte), ("end", toJson b.byte), ("line", toJson a.line)]
    | _, _, _ => Json.mkObj (entries.map fun (key, value) => (key, remap e fuel value))
  | _, value => value

def Expansion.remap (e : Expansion) (value : Json) : Json :=
  if e.origins.isEmpty then value else Delvetalk.DocumentTemplate.remap e (e.source.length + 1) value

end Delvetalk.DocumentTemplate
