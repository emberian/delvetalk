/- Objective Bend edition 1 source parser.

Source text → the module's `Compiler.ObjectiveBendSurface` AST (whose `Module.json` is the
`dregg.objective-bend.module.v1` AST JSON), which `Compiler.ObjectiveBendElaborate.ofSurface`
reads. Ported from the retired
TypeScript parser and translation-validated against it before that parser was
deleted (docs/OBJECTIVE-BEND-FRONTEND.md, "Provenance"): same AST, same spans
(UTF-8 byte offsets, 1-based lines), same refusals.

The surface grammar is line-oriented and was written as JavaScript regular
expressions. Each one is kept here as a `Re` value with JavaScript matching
semantics (leftmost alternative first, greedy/lazy quantifiers, backtracking,
an empty iteration of a star is rejected), so a pattern can be read against its
original. JavaScript `\s` and `trim` are the ECMAScript WhiteSpace and
LineTerminator sets, not ASCII.

Every recursion is fuel-bounded with fuel proportional to the input; running
out is a refusal ("capacity"), never a different parse. -/
import Lean
import Compiler.ObjectiveBendLaw
import Compiler.ObjectiveBendSurface
namespace Minidregg.Compiler.ObjectiveBendParse
open Lean (Json toJson)
open ObjectiveBendSurface (Param Expr Pattern Body Signature Method Claim Field Spec Decl Import Module)
set_option autoImplicit false

/-! ## ECMAScript character classes -/

def jsSpace (c : Char) : Bool :=
  let n := c.toNat
  n == 9 || n == 10 || n == 11 || n == 12 || n == 13 || n == 32 || n == 0xA0 || n == 0x1680 ||
  (0x2000 ≤ n && n ≤ 0x200A) || n == 0x2028 || n == 0x2029 || n == 0x202F || n == 0x205F ||
  n == 0x3000 || n == 0xFEFF
def lineTerminator (c : Char) : Bool :=
  let n := c.toNat
  n == 10 || n == 13 || n == 0x2028 || n == 0x2029
def asciiDigit (c : Char) : Bool := '0' ≤ c && c ≤ '9'
def asciiAlpha (c : Char) : Bool := ('a' ≤ c && c ≤ 'z') || ('A' ≤ c && c ≤ 'Z')
def wordChar (c : Char) : Bool := asciiAlpha c || asciiDigit c || c == '_'
def identStart (c : Char) : Bool := asciiAlpha c || c == '_'

def jsTrimStart (s : List Char) : List Char := s.dropWhile jsSpace
def jsTrim (s : List Char) : List Char := ((jsTrimStart s).reverse.dropWhile jsSpace).reverse
def utf8Length (s : List Char) : Nat := s.foldl (fun n c => n + c.utf8Size) 0
/-- JavaScript string length (UTF-16 code units). -/
def utf16Length (s : List Char) : Nat := s.foldl (fun n c => n + if c.toNat > 0xFFFF then 2 else 1) 0

/-! ## Regular expressions with JavaScript backtracking semantics -/

inductive Re where
  | char (p : Char → Bool)
  | lit (s : List Char)
  | seq (a b : Re)
  | alt (a b : Re)
  | star (r : Re) (greedy : Bool)
  | group (index : Nat) (r : Re)
  | eps
  /-- `$` without the multiline flag: end of input. -/
  | done
  deriving Inhabited

abbrev Caps := Array (Option (Nat × Nat))

inductive Outcome where
  | found (stop : Nat) (caps : Caps)
  | none
  | exhausted
  deriving Inhabited

/-- Continuation-passing backtracking matcher: the first success in JavaScript's
search order wins. -/
def run : Nat → Re → List Char → Nat → Caps → (List Char → Nat → Caps → Outcome) → Outcome
  | 0, _, _, _, _, _ => .exhausted
  | fuel + 1, r, s, pos, caps, k =>
    match r with
    | .eps => k s pos caps
    | .done => if s.isEmpty then k s pos caps else .none
    | .char p =>
      match s with
      | c :: rest => if p c then k rest (pos + 1) caps else .none
      | [] => .none
    | .lit l => if l.isPrefixOf s then k (s.drop l.length) (pos + l.length) caps else .none
    | .seq a b => run fuel a s pos caps (fun s' pos' caps' => run fuel b s' pos' caps' k)
    | .alt a b =>
      match run fuel a s pos caps k with
      | .none => run fuel b s pos caps k
      | other => other
    | .group i a => run fuel a s pos caps (fun s' pos' caps' => k s' pos' (caps'.set! i (some (pos, pos'))))
    | .star a greedy =>
      let more : Unit → Outcome := fun _ => run fuel a s pos caps (fun s' pos' caps' =>
        if pos' == pos then .none else run fuel (.star a greedy) s' pos' caps' k)
      if greedy then
        match more () with
        | .none => k s pos caps
        | other => other
      else
        match k s pos caps with
        | .none => more ()
        | other => other

/-- Fuel for one match: proportional to the subject (each consumed character costs
a bounded number of matcher frames for the patterns below). -/
def matchFuel (length : Nat) : Nat := 64 * (length + 64)

/-- The longest subject a pattern is matched against (one source line). Longer lines refuse
rather than recurse that deep. -/
def maxLine : Nat := 16384

/-- A match anchored at the start (`^...`) of `s`, whose length is `length`: `some captures`,
`none`, or a capacity refusal. -/
def anchoredAt (r : Re) (s : List Char) (length : Nat) : Except String (Option (Nat × Caps)) :=
  if length > maxLine then .error "Error: source line capacity" else
  match run (matchFuel length) r s 0 (Array.replicate 10 none) (fun _ stop caps => .found stop caps) with
  | .found stop caps => .ok (some (stop, caps))
  | .none => .ok none
  | .exhausted => .error "Error: source line capacity"

def anchored (r : Re) (s : List Char) : Except String (Option (Nat × Caps)) := anchoredAt r s s.length

/-- An unanchored test (`/.../.test`): a match starting anywhere. -/
def searches (r : Re) (s : List Char) : Except String Bool := do
  let mut rest := s
  let mut length := s.length
  for _ in [0:s.length + 1] do
    if (← anchoredAt r rest length).isSome then return true
    rest := rest.drop 1
    length := length - 1
  return false

def capture (s : List Char) (caps : Caps) (i : Nat) : Option (List Char) :=
  match caps[i]? with
  | some (some (a, b)) => some ((s.drop a).take (b - a))
  | _ => none

namespace Re
def chr (ch : Char) : Re := .char (· == ch)
def str (t : String) : Re := .lit t.toList
def space : Re := .char jsSpace
def nonSpace : Re := .char (fun c => !jsSpace c)
def word : Re := .char wordChar
def dot : Re := .char (fun c => !lineTerminator c)
def many (r : Re) : Re := .star r true
def many1 (r : Re) : Re := .seq r (.star r true)
def lazy1 (r : Re) : Re := .seq r (.star r false)
def opt (r : Re) : Re := .alt r .eps
def seqs : List Re → Re
  | [] => .eps
  | [r] => r
  | r :: rs => .seq r (seqs rs)
def alts : List Re → Re
  | [] => .eps
  | [r] => r
  | r :: rs => .alt r (alts rs)
/-- `[A-Za-z_]\w*` -/
def ident : Re := .seq (.char identStart) (many word)
/-- `"(?:[^"\\]|\\.)*"` -/
def quoted : Re := seqs [chr '"', many (alts [.char (fun c => c != '"' && c != '\\'), .seq (chr '\\') dot]), chr '"']
end Re
open Re

/-- `^[A-Za-z_]\w*$` -/
def isIdent (s : List Char) : Bool :=
  match s with
  | c :: rest => identStart c && rest.all wordChar
  | [] => false

/-! ## Spans and diagnostics -/

abbrev Span := ObjectiveBendSurface.Span

/-- A parse refusal: the TypeScript `compiler-diagnostic` (message and line span) or a bare
`Error` (message only). -/
structure Diagnostic where
  message : String
  span : Option Span
  deriving Inhabited, Repr

def Diagnostic.json (d : Diagnostic) : Json :=
  Json.mkObj ([("schema", toJson "dregg.bend.compiler-diagnostic.v1"), ("stage", toJson "objective-source-parse"),
    ("message", toJson d.message)] ++ (match d.span with | some s => [("span", s.json)] | none => []))

/-! ## JSON string literals (`JSON.parse` of a quoted token) -/

def hexValue (c : Char) : Option Nat :=
  if '0' ≤ c && c ≤ '9' then some (c.toNat - '0'.toNat)
  else if 'a' ≤ c && c ≤ 'f' then some (c.toNat - 'a'.toNat + 10)
  else if 'A' ≤ c && c ≤ 'F' then some (c.toNat - 'A'.toNat + 10)
  else none

def hex4 : List Char → Option (Nat × List Char)
  | a :: b :: c :: d :: rest => do
    pure ((((← hexValue a) * 16 + (← hexValue b)) * 16 + (← hexValue c)) * 16 + (← hexValue d), rest)
  | _ => none

/-- The body of a quoted token (between the quotes). A lone UTF-16 surrogate escape has no
`String` value in Lean and is refused (JavaScript would keep it). -/
def unescape : Nat → List Char → Except String (List Char)
  | 0, _ => .error "Error: string literal capacity"
  | _ + 1, [] => .ok []
  | fuel + 1, c :: rest =>
    if c.toNat < 0x20 then .error "SyntaxError: JSON Parse error: Unterminated string"
    else if c != '\\' then do return c :: (← unescape fuel rest)
    else match rest with
      | e :: tail =>
        let simple : Option Char := match e with
          | '"' => some '"' | '\\' => some '\\' | '/' => some '/' | 'b' => some (Char.ofNat 8)
          | 'f' => some (Char.ofNat 12) | 'n' => some '\n' | 'r' => some '\r' | 't' => some '\t'
          | _ => none
        match simple with
        | some ch => do return ch :: (← unescape fuel tail)
        | none =>
          if e != 'u' then .error ("SyntaxError: JSON Parse error: Invalid escape character " ++ e.toString)
          else match hex4 tail with
            | none => .error "SyntaxError: JSON Parse error: \\u must be followed by 4 hex digits"
            | some (high, after) =>
              if 0xD800 ≤ high && high ≤ 0xDBFF then
                match after with
                | '\\' :: 'u' :: more =>
                  match hex4 more with
                  | some (low, after2) =>
                    if 0xDC00 ≤ low && low ≤ 0xDFFF then do
                      return Char.ofNat (0x10000 + (high - 0xD800) * 0x400 + (low - 0xDC00)) :: (← unescape fuel after2)
                    else .error "Error: lone UTF-16 surrogate in a string literal"
                  | none => .error "Error: lone UTF-16 surrogate in a string literal"
                | _ => .error "Error: lone UTF-16 surrogate in a string literal"
              else if 0xDC00 ≤ high && high ≤ 0xDFFF then .error "Error: lone UTF-16 surrogate in a string literal"
              else do return Char.ofNat high :: (← unescape fuel after)
      | [] => .error "SyntaxError: JSON Parse error: Unterminated string"

/-- `JSON.parse` of a whole quoted token `"..."`. -/
def jsonStringLiteral (token : List Char) : Except String String := do
  match token with
  | '"' :: rest =>
    match rest.reverse with
    | '"' :: inner => return String.ofList (← unescape (token.length + 1) inner.reverse)
    | _ => throw "SyntaxError: JSON Parse error: Unterminated string"
  | _ => throw "SyntaxError: JSON Parse error: Unexpected token"

/-- An identifier or a quoted (JSON) string field name. -/
def fieldName (text : List Char) : Except String String :=
  if isIdent text then .ok (String.ofList text)
  else if text.head? == some '"' then jsonStringLiteral text
  else .error "Error: expected identifier or quoted string field name"

/-! ## Parameters and signatures -/

/-- `^\s*(?:(affine|linear)\s+)?([+-]?)([A-Za-z_]\w*)\s*(?::\s*(.+?))?\s*$` -/
def parameterRe : Re := seqs [many space, opt (seqs [group 1 (alts [str "affine", str "linear"]), many1 space]),
  group 2 (opt (.char (fun c => c == '+' || c == '-'))), group 3 ident, many space,
  opt (seqs [chr ':', many space, group 4 (lazy1 dot)]), many space, .done]

/-- Top-level comma split of a parameter list. `( < [ {` open and `) > ] }` close, except the
`>` of an arrow `->`, which is not a bracket: so a record type `{x: Nat, y: Nat}` and an
arrow `(Nat, Nat) -> Nat` are each one parameter type (the elaborator's `splitTop` counts
the same way). The TypeScript original counted neither `{` nor the arrow, so a record-typed
parameter was cut at its first comma and every parameter after an arrow-typed one was
swallowed into its type. -/
def splitPieces (raw : List Char) : List (List Char) :=
  let step := fun (acc : List (List Char) × List Char × Int × Option Char) (c : Char) =>
    let (pieces, current, depth, prev) := acc
    let depth := if c == '(' || c == '<' || c == '[' || c == '{' then depth + 1 else depth
    let depth := if c == ')' || c == ']' || c == '}' || (c == '>' && prev != some '-') then depth - 1 else depth
    if c == ',' && depth == 0 then (current.reverse :: pieces, [], depth, some c)
    else (pieces, c :: current, depth, some c)
  let (pieces, current, _, _) := raw.foldl step ([], [], 0, none)
  (current.reverse :: pieces).reverse

def splitParameters (raw : List Char) : Except String (List Param) := do
  if (jsTrim raw).isEmpty then return []
  (splitPieces raw).mapM fun piece => do
    let some (_, caps) ← anchored parameterRe piece | throw "Error: invalid parameter"
    let keyword := capture piece caps 1
    let marker := (capture piece caps 2).getD []
    let name := (capture piece caps 3).getD []
    if keyword.isSome && !marker.isEmpty then
      throw ("Error: parameter " ++ String.ofList name ++ " has two quantity markers")
    if keyword.isSome && (name == "affine".toList || name == "linear".toList) then
      throw "Error: quantity keyword is not a parameter name"
    let quantity := match keyword with
      | some k => String.ofList k
      | none => if marker == ['+'] then "copy" else if marker == ['-'] then "dead" else "default"
    return ⟨String.ofList name, String.ofList ((capture piece caps 4).getD ['_']), quantity⟩

/-! ## Expressions -/

structure Token where
  text : List Char
  /-- Character indices into the expression text. -/
  start : Nat
  stop : Nat
  deriving Inhabited

/-- `^(?:[A-Za-z_]\w*|[0-9]+n?|"(?:[^"\\]|\\.)*"|->|==|!=|<=|>=|&&|\|\||[{}:=().,+*/%<>-])` -/
def tokenRe : Re := alts [ident, seqs [many1 (.char asciiDigit), opt (chr 'n')], quoted,
  str "::", str "->", str "==", str "!=", str "<=", str ">=", str "&&", str "||",
  .char (fun c => "{}:=().,+*/%<>-".toList.contains c)]

/-- The length of the `tokenRe` match at the start of `s`, scanned directly: the alternatives
in their order (JavaScript takes the first that matches, not the longest), each of which
matches at most one way. A quoted token runs to its first unescaped `"`; a backslash before a
line terminator or the end, or no closing quote, is no match (no shorter split of the
string's units ends at a quote). -/
def tokenLength (s : List Char) : Option Nat :=
  match s with
  | [] => none
  | c :: rest =>
    if identStart c then some (1 + (rest.takeWhile wordChar).length)
    else if asciiDigit c then
      let digits := 1 + (rest.takeWhile asciiDigit).length
      some (if (s.drop digits).head? == some 'n' then digits + 1 else digits)
    else if c == '"' then
      let rec quoted : List Char → Nat → Option Nat
        | [], _ => none
        | '"' :: _, n => some (n + 1)
        | '\\' :: d :: more, n => if lineTerminator d then none else quoted more (n + 2)
        | '\\' :: [], _ => none
        | _ :: more, n => quoted more (n + 1)
      quoted rest 1
    else
      let pair := match rest with
        | d :: _ => (c == ':' && d == ':') || (c == '-' && d == '>') || (c == '=' && d == '=') ||
            (c == '!' && d == '=') || (c == '<' && d == '=') || (c == '>' && d == '=') ||
            (c == '&' && d == '&') || (c == '|' && d == '|')
        | [] => false
      if pair then some 2
      else if c == '{' || c == '}' || c == ':' || c == '=' || c == '(' || c == ')' || c == '.' || c == ',' ||
          c == '+' || c == '*' || c == '/' || c == '%' || c == '<' || c == '>' || c == '-' then some 1
      else none

def tokenize (text : List Char) : Except String (Array Token) := do
  let mut tokens : Array Token := #[]
  let mut rest := text
  let total := text.length
  let mut at_ := 0
  for _ in [0:text.length + 1] do
    match rest with
    | [] => break
    | c :: tail =>
      if jsSpace c then
        rest := tail; at_ := at_ + 1
      else
        if total - at_ > maxLine then throw "Error: source line capacity"
        let some stop := tokenLength rest
          | throw ("Error: unsupported expression at column " ++ toString (utf16Length (text.take at_)))
        tokens := tokens.push ⟨rest.take stop, at_, at_ + stop⟩
        rest := rest.drop stop; at_ := at_ + stop
  return tokens

def precedence (op : String) : Option Nat :=
  match op with
  | "||" => some 1 | "&&" => some 2 | "==" => some 3 | "!=" => some 3
  | "<" => some 4 | ">" => some 4 | "<=" => some 4 | ">=" => some 4
  | "+" => some 5 | "-" => some 5 | "*" => some 6 | "/" => some 6 | "%" => some 6
  | _ => none

structure ExprEnv where
  text : List Char
  tokens : Array Token
  /-- `byteAt[i]` = absolute byte offset of character `i` of the expression text. -/
  byteAt : Array Nat
  line : Nat

abbrev EP := StateT Nat (Except String)

def ExprEnv.location (env : ExprEnv) (start stop : Nat) : Span :=
  ⟨env.byteAt[start]!, env.byteAt[stop]!, env.line⟩

def tokenText (t : Token) : String := String.ofList t.text

def peek (env : ExprEnv) : EP (Option String) := do return (env.tokens[← get]?).map tokenText

def take (env : ExprEnv) (wanted : Option String := none) : EP Token := do
  let i ← get
  set (i + 1)
  let message := "Error: expected " ++ wanted.getD "expression"
  match env.tokens[i]? with
  | some t => if wanted.all (· == tokenText t) then pure t else throw message
  | none => throw message

def isNumberToken (t : List Char) : Bool :=
  let digits := t.takeWhile asciiDigit
  !digits.isEmpty && (t.drop digits.length == [] || t.drop digits.length == ['n'])

/-- `value.replace(/n$/," ").trim().replace(/^0+(?=[0-9])/,"")` -/
def natValue (t : List Char) : String :=
  let digits := t.takeWhile asciiDigit
  let stripped := digits.dropWhile (· == '0')
  String.ofList (if stripped.isEmpty then ['0'] else stripped)

/-! ## String interpolation

`"SCENE {state.title} ({natText(n)} here)"` is the text pieces and the expressions between
braces, joined: up to four pieces by right-nested `textConcat`, more by `textJoin` over the
built-in `TextPieces` list with separator "". `{{` and `}}` are literal braces; an
expression's own string literals are escaped (`{f(\"a\")}`), as everything inside the
token is. A token without an unescaped `{` is an ordinary string. -/

inductive Piece where
  | text (raw : List Char)
  /-- An expression's source text (still escaped) and its character offset in the token. -/
  | code (raw : List Char) (offset : Nat)

def interpolationPieces (token : List Char) : Except String (List Piece) := do
  let inner := (token.drop 1).dropLast.toArray
  let mut pieces : Array Piece := #[]
  let mut literal : Array Char := #[]
  let mut i := 0
  for _ in [0:inner.size + 1] do
    if i ≥ inner.size then break
    let c := inner[i]!
    if c == '\\' then
      literal := (literal.push c).push (inner[i + 1]?.getD c)
      i := i + 2
    else if c == '{' && inner[i + 1]? == some '{' then
      literal := literal.push '{'; i := i + 2
    else if c == '}' && inner[i + 1]? == some '}' then
      literal := literal.push '}'; i := i + 2
    else if c == '}' then
      throw "Error: a lone } in a string literal is written }}"
    else if c == '{' then
      let mut depth := 1
      let mut j := i + 1
      for _ in [0:inner.size + 1] do
        if j ≥ inner.size || depth == 0 then break
        let d := inner[j]!
        if d == '\\' then j := j + 2
        else
          if d == '{' then depth := depth + 1
          if d == '}' then depth := depth - 1
          j := j + 1
      if depth != 0 then throw "Error: an interpolation { in a string literal is not closed"
      if !literal.isEmpty then pieces := pieces.push (.text literal.toList)
      literal := #[]
      pieces := pieces.push (.code (inner.extract (i + 1) (j - 1)).toList (i + 2))
      i := j
    else
      literal := literal.push c; i := i + 1
  if !literal.isEmpty then pieces := pieces.push (.text literal.toList)
  return pieces.toList

def builtinTextPieces : String := "TextPieces"

/-- The pieces joined: one piece is itself, up to four a right-nested `textConcat`, more a
`textJoin` over `TextPieces` with separator "". -/
def joinPieces (pieces : List Expr) (span : Span) : Expr :=
  if pieces.length ≤ 4 then
    match pieces.reverse with
    | [] => .str "" span
    | last :: earlier => earlier.foldl (fun acc p => .call (.var "textConcat" span) [p, acc] span) last
  else
    let ctor := fun (label : String) => Expr.member (.var builtinTextPieces span) label span
    let list := pieces.foldr (fun p acc => Expr.call (ctor "cons") [.record [("head", p), ("tail", acc)] span] span)
      (.call (ctor "nil") [.record [] span] span)
    .call (.var "textJoin" span) [list, .str "" span] span

/-- The placeholder a `write {...}` names the Plan library by, until the module's alias of
`Plan.obend` replaces it (`parseObjective`). Not an identifier a source can spell. -/
def writePlansAlias : String := "$plans"

/-- The callee a `write {...}` names until the generics pass decides its dialect: in an
`Activity<Plan, Response, R>` the Plan `Plan.write({object, edits})`, in an `Activity<R>`
the world call `world.write(edits)`. Not an identifier a source can spell. -/
def writeMarker : String := "$write"

/-- `parse(minimum)`: an atom, its postfix member/call chain, then binary operators of at
least `minimum` precedence (left-associative). -/
def parseExpr (env : ExprEnv) : Nat → Nat → EP (Expr × Span)
  | 0, _ => throw "Error: expression nesting capacity"
  | fuel + 1, minimum => do
    let first ← take env
    let firstText := tokenText first
    if firstText == "let" then
      let name ← take env
      if !isIdent name.text || tokenText name == "in" then throw "Error: expected a name after let"
      let mut type := "_"
      if (← peek env) == some ":" then
        let colon ← take env (some ":")
        for _ in [0:env.tokens.size + 1] do
          if (← peek env) == some "=" then break
          if (← get) ≥ env.tokens.size then throw "Error: expected = in let"
          discard <| take env
        let some equals := env.tokens[← get]? | throw "Error: expected = in let"
        let raw := jsTrim ((env.text.drop colon.stop).take (equals.start - colon.stop))
        if raw.isEmpty then throw "Error: missing let type"
        type := String.ofList raw
      discard <| take env (some "=")
      let (value, _) ← parseExpr env fuel 0
      discard <| take env (some "in")
      let (letBody, bodySpan) ← parseExpr env fuel 0
      let span := { env.location first.start first.stop with stop := bodySpan.stop }
      return (.letE (tokenText name) type value letBody span, span)
    if firstText == "if" then
      let (condition, _) ← parseExpr env fuel 0
      discard <| take env (some "then")
      let (whenTrue, _) ← parseExpr env fuel 0
      discard <| take env (some "else")
      let (whenFalse, falseSpan) ← parseExpr env fuel 0
      let span := { env.location first.start first.stop with stop := falseSpan.stop }
      return (.ite condition whenTrue whenFalse span, span)
    let mut result : Expr × Span := (default, default)
    if (firstText == "fn" || firstText == "extension") && (← peek env) == some "(" then
      let opening ← take env (some "(")
      let mut depth := 1
      let mut closing := opening
      for _ in [0:env.tokens.size + 1] do
        if depth == 0 then break
        closing ← take env
        if tokenText closing == "(" then depth := depth + 1
        if tokenText closing == ")" then depth := depth - 1
      let parameters ← splitParameters ((env.text.drop opening.stop).take (closing.start - opening.stop))
      discard <| take env (some "->")
      let some typeToken := env.tokens[← get]? | throw "Error: missing closure result type"
      for _ in [0:env.tokens.size + 1] do
        if (← peek env) == some ":" then break
        if (← get) ≥ env.tokens.size then throw "Error: missing closure body"
        modify (· + 1)
      let colon ← take env (some ":")
      let resultType := jsTrim ((env.text.drop typeToken.start).take (colon.start - typeToken.start))
      if resultType.isEmpty then throw "Error: missing closure result type"
      let (closureBody, bodySpan) ← parseExpr env fuel 0
      let span := { env.location first.start first.stop with stop := bodySpan.stop }
      result := if firstText == "fn" then
          (.lambda parameters (String.ofList resultType) closureBody span, span)
        else
          (.extensionValue parameters (String.ofList resultType) closureBody span, span)
    -- `write {field: op value, ...}`: the Plan that writes the running object's edits,
    -- every other field kept (in an `Activity<R>`, the world call `world.write(edits)`;
    -- the generics pass chooses, `writeMarker`). Lowers to
    -- `Plan.write({object: Plans.self(context), edits: extend(keep(), {field: E, ...})})`
    -- with `E` = `Plans.Edit.add({delta: v})` (add), `Plans.Edit.set({value: v})` (set),
    -- `Plans.Entries.append({item: v})` (append), `Plans.Entries.remove({index: v})`
    -- (remove), `Plans.Entries.removeItem({item: v})` (removeItem), and for a relation
    -- `Plans.Entries.insert({row: v})` (insert), `Plans.Entries.upsert({row: v})` (upsert),
    -- `Plans.Entries.retract({key: v})` (retract); `Plans` is the module's
    -- alias of Plan.obend (`writePlansAlias`, resolved after parsing) and the type
    -- arguments are inferred from the object's Edits.
    else if firstText == "write" && (← peek env) == some "{" then
      let open_ ← take env (some "{")
      let span := env.location first.start open_.stop
      let plans := Expr.var writePlansAlias span
      let lib := fun (type name : String) => Expr.member (.member plans type span) name span
      let mut edits : Array (String × Expr) := #[]
      for _ in [0:env.tokens.size + 1] do
        let name ← take env
        if !isIdent name.text then throw "Error: write {field: op value, ...} expects a field name"
        discard <| take env (some ":")
        let op ← take env
        let (value, _) ← parseExpr env fuel 0
        let (type, ctor, payload) ← match tokenText op with
          | "add" => pure ("Edit", "add", "delta")
          | "set" => pure ("Edit", "set", "value")
          | "append" => pure ("Entries", "append", "item")
          | "remove" => pure ("Entries", "remove", "index")
          | "removeItem" => pure ("Entries", "removeItem", "item")
          | "insert" => pure ("Entries", "insert", "row")
          | "upsert" => pure ("Entries", "upsert", "row")
          | "retract" => pure ("Entries", "retract", "key")
          | other => throw ("Error: write {field: op value} takes add, set, append, remove, removeItem, insert, upsert or retract, not " ++ other)
        edits := edits.push (tokenText name, .call (lib type ctor) [.record [(payload, value)] span] span)
        let next ← take env
        if tokenText next == "}" then break
        if tokenText next != "," then throw "Error: expected , or } in write {...}"
      let object := Expr.call (.member plans "self" span) [.var "context" span] span
      let changes := Expr.extend (.call (.var "keep" span) [] span) edits.toList span
      result := (.call (.var writeMarker span)
        [.record [("object", object), ("edits", changes)] span] span, span)
    else if firstText == "{" then
      let mut fields : Array (String × Expr) := #[]
      if (← peek env) != some "}" then
        for _ in [0:env.tokens.size + 1] do
          let key ← take env
          let name ← StateT.lift (fieldName key.text)
          discard <| take env (some ":")
          let (value, _) ← parseExpr env fuel 0
          fields := fields.push (name, value)
          if (← peek env) != some "," then break
          discard <| take env (some ",")
      let closing ← take env (some "}")
      let span := env.location first.start closing.stop
      result := (.record fields.toList span, span)
    else if firstText == "(" then
      if (← peek env) == some ")" then
        let closing ← take env (some ")")
        let span := env.location first.start closing.stop
        result := (.unit span, span)
      else
        result ← parseExpr env fuel 0
        discard <| take env (some ")")
    else if firstText == "true" || firstText == "false" then
      let span := env.location first.start first.stop
      result := (.bool (firstText == "true") span, span)
    else if isNumberToken first.text then
      let span := env.location first.start first.stop
      result := (.nat (natValue first.text) span, span)
    else if first.text.head? == some '"' then
      let span := env.location first.start first.stop
      let pieces ← StateT.lift (interpolationPieces first.text)
      if pieces.all (fun p => match p with | .text _ => true | _ => false) then
        let raw := pieces.flatMap fun p => match p with | .text r => r | _ => []
        let value ← StateT.lift (jsonStringLiteral ('"' :: raw ++ ['"']))
        result := (.str value span, span)
      else
        let mut parts : List Expr := []
        for piece in pieces do
          match piece with
          | .text raw => parts := parts ++ [.str (← StateT.lift (jsonStringLiteral ('"' :: raw ++ ['"']))) span]
          | .code raw offset =>
            let code ← StateT.lift (unescape (raw.length + 1) raw)
            let tokens ← StateT.lift (tokenize code)
            let base := env.byteAt[first.start + offset]!
            let byteAt := (code.foldl (fun (acc : Array Nat × Nat) c => (acc.1.push acc.2, acc.2 + c.utf8Size))
              (#[], base)) |> fun (acc, last) => acc.push last
            let inner : ExprEnv := ⟨code, tokens, byteAt, env.line⟩
            let ((e, _), cursor) ← StateT.lift ((parseExpr inner fuel 0).run 0)
            if cursor != tokens.size then throw "Error: an interpolation in a string literal holds one expression"
            parts := parts ++ [e]
        result := (joinPieces parts span, span)
    else if isIdent first.text then
      let span := env.location first.start first.stop
      result := (.var firstText span, span)
    else throw "Error: expected expression atom"
    for _ in [0:env.tokens.size + 1] do
      let some next := (← peek env) | break
      if next == "::" then
        discard <| take env (some "::")
        let opening ← take env (some "<")
        let mut depth := 1
        let mut closing := opening
        for _ in [0:env.tokens.size + 1] do
          if depth == 0 then break
          closing ← take env
          if tokenText closing == "<" then depth := depth + 1
          if tokenText closing == ">" then depth := depth - 1
        if depth != 0 then throw "Error: unterminated generic specialization"
        let types := (splitPieces ((env.text.drop opening.stop).take (closing.start - opening.stop))).map jsTrim
        if types.isEmpty || types.any List.isEmpty then throw "Error: specialization requires type arguments"
        let span := { result.2 with stop := (env.location closing.start closing.stop).stop }
        result := (.specialize result.1 (types.map String.ofList) span, span)
        continue
      if next == "." then
        discard <| take env (some ".")
        let field ← take env
        let name ← StateT.lift (fieldName field.text)
        let span := { result.2 with stop := (env.location field.start field.stop).stop }
        result := (.member result.1 name span, span)
        continue
      if next == "(" then
        discard <| take env (some "(")
        let mut args : Array Expr := #[]
        if (← peek env) != some ")" then
          for _ in [0:env.tokens.size + 1] do
            let (arg, _) ← parseExpr env fuel 0
            args := args.push arg
            if (← peek env) != some "," then break
            discard <| take env (some ",")
        let closing ← take env (some ")")
        let span := { result.2 with stop := (env.location closing.start closing.stop).stop }
        let calleeName := match result.1 with
          | .var name _ => some name
          | _ => none
        if calleeName == some "compose" then
          result := (.compose args.toList span, span)
        else if calleeName == some "fix" then
          let #[specification, inherited] := args | throw "Error: fix expects specification and inherited target"
          result := (.fix specification inherited span, span)
        else if calleeName == some "extend" then
          match args with
          | #[inherited, .record fields _] => result := (.extend inherited fields span, span)
          | _ => throw "Error: extend expects inherited target and record fields"
        else
          result := (.call result.1 args.toList span, span)
        continue
      let some priority := precedence next | break
      if priority < minimum then break
      discard <| take env
      let (right, rightSpan) ← parseExpr env fuel (priority + 1)
      let span := { result.2 with stop := rightSpan.stop }
      result := (.binary next result.1 right span, span)
    return result

/-- `expression(text, sourceSpan)`: the whole text is one expression. `start` is the absolute
byte offset of the text's first character. -/
def expression (text : List Char) (start line : Nat) : Except String Expr := do
  let tokens ← tokenize text
  let byteAt := (text.foldl (fun (acc : Array Nat × Nat) c => (acc.1.push acc.2, acc.2 + c.utf8Size))
    (#[], start)) |> fun (acc, last) => acc.push last
  let env : ExprEnv := ⟨text, tokens, byteAt, line⟩
  let ((expr, _), cursor) ← (parseExpr env (text.length + tokens.size + 1) 0).run 0
  if cursor != tokens.size then throw "Error: unexpected trailing expression token"
  return expr

/-! ## Lines and declarations -/

structure Line where
  text : List Char
  indent : Nat
  number : Nat
  start : Nat
  stop : Nat
  deriving Inhabited

def Line.span (l : Line) : Span := ⟨l.start, l.stop, l.number⟩

abbrev PS := StateT Nat (Except Diagnostic)

def fail {α : Type} (line : Line) (message : String) : PS α := throw ⟨message, some line.span⟩
def bare {α : Type} (message : String) : PS α := throw ⟨message, none⟩
def liftBare {α : Type} (x : Except String α) : PS α :=
  match x with
  | .ok a => pure a
  | .error e => bare e
def liftAt {α : Type} (line : Line) (x : Except String α) : PS α :=
  match x with
  | .ok a => pure a
  | .error e => fail line e
def matchAt (line : Line) (r : Re) (s : List Char) : PS (Option (Nat × Caps)) := liftAt line (anchored r s)

/-- `String.prototype.lastIndexOf` (character index; equal prefixes, so equal bytes); `0` when
absent. -/
def lastIndexOf (hay needle : List Char) : Nat := Id.run do
  let mut found := 0
  let mut rest := hay
  for i in [0:hay.length + 1] do
    if needle.isPrefixOf rest then found := i
    rest := rest.drop 1
  return found

/-- `expr(text, line)`: an expression found at its last occurrence in the line; its errors
become line diagnostics. -/
def lineExpr (line : Line) (text : List Char) : PS Expr :=
  liftAt line (expression text (line.start + utf8Length (line.text.take (lastIndexOf line.text text))) line.number)

/-- `^([A-Za-z_]\w*)\s*\((.*)\)(?:\s*->\s*(.+?))?\s*$` -/
def signatureRe : Re := seqs [group 1 ident, many space, chr '(', group 2 (many dot), chr ')',
  opt (seqs [many space, str "->", many space, group 3 (lazy1 dot)]), many space, .done]

def signature (raw : List Char) (line : Line) : PS Signature := do
  let some (_, caps) ← matchAt line signatureRe raw | fail line "expected method signature"
  let parameters ← liftAt line (splitParameters ((capture raw caps 2).getD []))
  return ⟨String.ofList ((capture raw caps 1).getD []), parameters,
    String.ofList ((capture raw caps 3).getD ['_']), line.span⟩

/-- `^case\s+(0n?|1n?\+([A-Za-z_]\w*)|_|true|false|([A-Za-z_]\w*)\(\s*([A-Za-z_]\w*)?\s*\))\s*:\s*(.*)$` -/
def caseRe : Re := seqs [str "case", many1 space,
  group 1 (alts [.seq (chr '0') (opt (chr 'n')), seqs [chr '1', opt (chr 'n'), chr '+', group 2 ident], chr '_',
    str "true", str "false", seqs [group 3 ident, chr '(', many space, opt (group 4 ident), many space, chr ')']]),
  many space, chr ':', many space, group 5 (many dot), .done]

/-- `^let\s+([A-Za-z_]\w*)\s*(?::\s*(.+?))?\s*=\s*(.+)$` -/
def letRe : Re := seqs [str "let", many1 space, group 1 ident, many space,
  opt (seqs [chr ':', many space, group 2 (lazy1 dot)]), many space, chr '=', many space, group 3 (many1 dot), .done]

/-- `^let\s+([A-Za-z_]\w*)\(\s*([A-Za-z_]\w*)?\s*\)\s*=\s*(.+)$`: a statement that
performs and continues with one response. -/
def letCaseRe : Re := seqs [str "let", many1 space, group 1 ident, many space, chr '(', many space,
  opt (group 2 ident), many space, chr ')', many space, chr '=', many space, group 3 (many1 dot), .done]

def startsWith (s : List Char) (p : String) : Bool := p.toList.isPrefixOf s
def endsWith (s : List Char) (p : String) : Bool := p.toList.reverse.isPrefixOf s.reverse

/-- `body(indent)`: the indented method body after a header line. -/
def body (lines : Array Line) : Nat → Nat → PS Body
  | 0, _ => bare "Error: body nesting capacity"
  | fuel + 1, indent => do
    let i ← get
    let some line := lines[i]? | bare "Error: missing indented method body"
    if line.indent ≤ indent then bare "Error: missing indented method body"
    set (i + 1)
    if startsWith line.text "match " && endsWith line.text ":" then
      let scrutinee ← lineExpr line ((line.text.drop 6).take (line.text.length - 7))
      let mut branches : Array (Pattern × Body × Span) := #[]
      for _ in [0:lines.size] do
        let j ← get
        let some branch := lines[j]? | break
        if branch.indent ≤ line.indent then break
        set (j + 1)
        let some (_, caps) ← matchAt branch caseRe branch.text
          | fail branch "expected zero/successor/true/false/label(binder)/wildcard case"
        let whole := (capture branch.text caps 1).getD []
        let pattern : Pattern :=
          if whole == ['_'] then .wildcard
          else if whole == "true".toList || whole == "false".toList then .bool (whole == "true".toList)
          else match capture branch.text caps 3 with
            | some label => .ctor (String.ofList label) (String.ofList ((capture branch.text caps 4).getD ['_']))
            | none => match capture branch.text caps 2 with
              | some binder => .succ (String.ofList binder)
              | none => .zero
        let inline := (capture branch.text caps 5).getD []
        let branchBody ← if inline.isEmpty then body lines fuel branch.indent
          else do
            let e ← lineExpr branch inline
            pure (Body.expr e branch.span)
        branches := branches.push (pattern, branchBody, branch.span)
      if branches.isEmpty then fail line "empty match"
      return .cases scrutinee branches.toList line.span
    -- `let label(x) = E` then the rest of the block: `match E:` with `case label(x):` the
    -- rest and every other label refusing the turn by name (`Pattern.unexpected`).
    if let some (_, caps) ← matchAt line letCaseRe line.text then
      let label := String.ofList ((capture line.text caps 1).getD [])
      let binder := String.ofList ((capture line.text caps 2).getD ['_'])
      let valueText := (capture line.text caps 3).getD []
      let value ← lineExpr line valueText
      match lines[i + 1]? with
      | some next => if next.indent != line.indent then fail line "a let must be followed by its body at the same indent"
      | none => fail line "a let must be followed by its body at the same indent"
      let rest ← body lines fuel (line.indent - 1)
      return .cases value [(.ctor label binder, rest, line.span),
        (.unexpected, .expr (.str ("unexpected response") line.span) line.span, line.span)] line.span
    if let some (_, caps) ← matchAt line letRe line.text then
      let name := (capture line.text caps 1).getD []
      if name != "in".toList then
        let valueText := (capture line.text caps 3).getD []
        let value := expression valueText
          (line.start + utf8Length (line.text.take (lastIndexOf line.text valueText))) line.number
        if let .ok value := value then
          match lines[i + 1]? with
          | some next => if next.indent != line.indent then fail line "a let must be followed by its body at the same indent"
          | none => fail line "a let must be followed by its body at the same indent"
          let rest ← body lines fuel (line.indent - 1)
          return .letB (String.ofList name) (String.ofList ((capture line.text caps 2).getD ['_'])) value rest
            line.span
    let text := if startsWith line.text "return " then line.text.drop 7 else line.text
    return .expr (← lineExpr line text) line.span

def namedImportRe : Re := seqs [str "import", many1 space, group 1 ident, many1 space, str "from", many1 space, chr '"',
  group 2 (seqs [str "./", many1 (.char (fun c => c != '"' && c != '\\')), str ".obend"]), chr '"', .done]
def importRe : Re := seqs [str "import", many1 space, group 1 (many1 nonSpace),
  opt (seqs [many1 space, str "as", many1 space, group 2 ident]), .done]
def exportRe : Re := seqs [str "export", many1 space, group 1 ident, chr '.', group 2 ident,
  opt (seqs [many1 space, str "as", many1 space, group 3 ident]), .done]
def importLeadRe : Re := .seq (str "import") space
def genOneRe : Re := seqs [str ".bend", opt (chr '"'), alts [space, .done]]
/-- `spec S [extends P, ...] for T:` (closed) or `spec S[Self has {...}, Super has {...}]:`
(open over its future self and inherited row, OB-LTUO LT2). -/
def specRe : Re := seqs [opt (group 1 (.seq (str "suffix") (many1 space))), str "spec", many1 space, group 2 ident,
  alts [seqs [opt (seqs [many1 space, str "extends", many1 space, group 3 (lazy1 dot)]), many1 space, str "for", many1 space,
      group 4 (many1 dot)],
    seqs [chr '[', group 5 (many1 (.char (· != ']'))), chr ']']],
  chr ':', .done]
def parentRe : Re := seqs [ident, opt (.seq (chr '.') ident), .done]
def qualifiedRe : Re := seqs [group 1 (alts [str "def", str "around", str "before", str "after",
  seqs [str "combine", many1 space, group 2 (alts [chr '+', chr '*', str "and"])]]), many1 space, group 3 (many dot),
  chr ':', .done]
def claimRe : Re := seqs [str "claim", many1 space, group 1 ident, opt (seqs [chr '(', group 2 (many dot), chr ')']),
  many space, chr ':', many space, group 3 (many1 dot), .done]
def extensionRe : Re := seqs [str "extension", many1 space, group 1 ident,
  opt (seqs [chr '[', group 4 (many1 (.char (· != ']'))), chr ']']), chr '(', group 2 (many dot), chr ')',
  many space, str "->", many space, group 3 (many1 dot), chr ':', .done]
def typeBindersRe : Re := seqs [chr '<', group 2 (many1 (.char (· != '>'))), chr '>']
def sumRe : Re := seqs [str "sum", many1 space, group 1 ident, opt typeBindersRe, chr ':', .done]
def genericDefRe : Re := seqs [str "def", many1 space, group 1 ident, typeBindersRe,
  group 3 (many1 dot), chr ':', .done]
def typeAliasRe : Re := seqs [str "type", many1 space, group 1 ident, many space,
  chr '=', many space, group 2 (many1 dot), .done]
def sumCaseRe : Re := seqs [group 1 ident, many space, chr ':', many space, group 2 (many1 dot), .done]
def recordRe : Re := seqs [str "record", many1 space, group 1 ident, chr ':', .done]
def fieldRe : Re := seqs [group 1 (.alt ident quoted), chr ':', many space, group 2 (many1 dot), .done]
/-- `law NAME "reading": EXPR`, a top-level ENFORCED law of the package (`Compiler.ObjectiveBendLaw`);
the optional reading (a string literal) is what a refusal by it quotes. -/
def lawRe : Re := seqs [str "law", many1 space, group 1 ident, opt (seqs [many1 space, group 3 quoted]), many space,
  chr ':', many space, group 2 (many1 dot), .done]

/-- `String.prototype.split` on one character. -/
def splitChar (s : List Char) (sep : Char) : List (List Char) :=
  let (finished, current) := s.foldl (fun (acc : List (List Char) × List Char) c =>
    if c == sep then (acc.2.reverse :: acc.1, []) else (acc.1, c :: acc.2)) ([], [])
  (current.reverse :: finished).reverse

def cap (s : List Char) (caps : Caps) (i : Nat) : String := String.ofList ((capture s caps i).getD [])

/-! ## Form blocks

    form plant as planting:
      colour: amber | violet | silver
      seed: text 1..80
      count: natural 1..1000
      program: source

declares `def planting() -> F.Form` (default name `plantForm`) whose body is the Form
record the library uses, `F` being the module's alias of `Form.obend`:
`{card: "", action: "plant", fields: F.Fields.cons({head: {name: "colour", kind:
F.Kind.choice({options: F.Names.cons(...)})}, tail: ...})}`, each list ending in `nil({})`.
`source` is `F.Kind.source({})`: Bend source, which the host reads as text of 1 to
`Host.Limits.formSourceMax` characters and fills from a reply's fenced `obend` block. -/
def formRe : Re := seqs [str "form", many1 space, group 1 ident,
  opt (seqs [many1 space, str "as", many1 space, group 2 ident]), many space, chr ':', .done]
def rangeKindRe : Re := seqs [group 1 (alts [str "text", str "natural"]), many1 space,
  group 2 (many1 (.char asciiDigit)), opt (chr 'n'), many space, str "..", many space,
  group 3 (many1 (.char asciiDigit)), opt (chr 'n'), many space, .done]

/-- One form field's kind, as the Form library's constructor application. -/
def formKind (alias : String) (line : Line) (spec : List Char) : PS Expr := do
  let span := line.span
  let lib := fun (type name : String) => Expr.member (.member (.var alias span) type span) name span
  let trimmed := String.ofList spec |>.trimAscii |>.toString
  if trimmed == "source" then return .call (lib "Kind" "source") [.record [] span] span
  if let some (_, caps) ← matchAt line rangeKindRe trimmed.toList then
    let kind := cap trimmed.toList caps 1
    let low := natValue ((capture trimmed.toList caps 2).getD [])
    let high := natValue ((capture trimmed.toList caps 3).getD [])
    return .call (lib "Kind" kind) [.record [("min", .nat low span), ("max", .nat high span)] span] span
  let options := (trimmed.splitOn "|").map fun o => o.trimAscii.toString
  if options.length < 2 || options.any (fun o => !isIdent o.toList) then
    fail line "a form field is `name: text MIN..MAX`, `name: natural MIN..MAX`, `name: source` or `name: a | b | c`"
  let names := options.foldr (fun o acc =>
      Expr.call (lib "Names" "cons") [.record [("head", .str o span), ("tail", acc)] span] span)
    (.call (lib "Names" "nil") [.record [] span] span)
  return .call (lib "Kind" "choice") [.record [("options", names)] span] span

def genericParameters (raw : List Char) : Except String (List String) := do
  let names := (splitPieces raw).map jsTrim
  if names.isEmpty || names.any (fun n => !isIdent n) then throw "Error: generic parameters must be type names"
  if names.eraseDups.length != names.length then throw "Error: duplicate generic type parameter"
  return names.map String.ofList

/-- Lines of the source: `split("\n")`, tabs refused anywhere, indentation and spans from the
raw line, blank and `#` comment lines dropped. -/
def sourceLines (source : String) : Except Diagnostic (Array Line) := do
  let raws := splitChar source.toList '\n'
  let mut lines : Array Line := #[]
  let mut offset := 0
  let mut number := 1
  for raw in raws do
    if raw.contains '\t' then throw ⟨"Error: tabs are not indentation in Objective Bend edition1", none⟩
    let indent := raw.length - (jsTrimStart raw).length
    let text := jsTrim raw
    if !text.isEmpty && text.head? != some '#' then
      lines := lines.push ⟨text, indent, number, offset + utf8Length (raw.take indent), offset + utf8Length raw⟩
    offset := offset + utf8Length raw + 1
    number := number + 1
  return lines

def trimText (s : String) : String := String.ofList (jsTrim s.toList)

/-- Split at top-level occurrences of `sep` (outside brackets). -/
def splitTopAt (s : String) (sep : String) : List String := Id.run do
  let chars := s.toList
  let sepChars := sep.toList
  let mut depth : Int := 0
  let mut current : List Char := []
  let mut parts : List String := []
  let mut rest := chars
  for _ in [0:chars.length + 1] do
    match rest with
    | [] => break
    | c :: tail =>
      if depth == 0 && rest.take sepChars.length == sepChars then
        parts := parts ++ [String.ofList current]
        current := []
        rest := rest.drop sepChars.length
        continue
      if c == '(' || c == '<' || c == '{' || c == '[' then depth := depth + 1
      if c == ')' || (c == '>' && !(current.getLast? == some '-')) || c == '}' || c == ']' then depth := depth - 1
      current := current ++ [c]
      rest := tail
  return parts ++ [String.ofList current]

def splitTopComma (s : String) : List String := splitTopAt s ","

/-- `PARAMS -> RESULT` at the first top-level arrow. -/
def splitArrow (s : String) : Option (String × String) :=
  match splitTopAt s "->" with
  | first :: second :: more => some (trimText first, trimText ("->".intercalate (second :: more)))
  | _ => none

/-- A protocol method's type as the elaborator reads it: `(A, B) -> R` curried to
`A -> B -> R`, `() -> R` to `R`. -/
def protocolType (text : String) : String :=
  let t := trimText text
  match splitArrow t with
  | some (params, result) =>
    if params.startsWith "(" && params.endsWith ")" then
      let inner := trimText ((params.drop 1).dropRight 1).toString
      if inner.isEmpty then result
      else " -> ".intercalate ((splitTopComma inner).map trimText) ++ " -> " ++ result
    else t
  | none => t

/-- The rest of a signature-form protocol line after its name (`protocolSignature`). -/
def protocolSignatureOf (name rest : List Char) : Except String (String × List String × String) := do
  let shape := "a protocol method is `name: TYPE` or `name<T, ...>(INPUT) -> RESULT`"
  let (params, rest) ← match rest with
    | '<' :: after =>
      let inside := after.takeWhile (· != '>')
      if inside.length == after.length then throw shape
      let params := (splitTopComma (String.ofList inside)).map trimText
      if !params.all (fun p => isIdent p.toList) then throw shape
      pure (params, after.drop (inside.length + 1))
    | _ => pure ([], rest)
  let some (input, result) := splitArrow (String.ofList rest) | throw shape
  if !(input.startsWith "(" && input.endsWith ")" && !result.isEmpty) then throw shape
  let input := trimText ((input.drop 1).dropRight 1).toString
  let one := "a world method takes exactly one input: name(INPUT) -> RESULT"
  match splitTopComma input with
  | [only] => if (trimText only).isEmpty then throw one else pure (String.ofList name, params, input ++ " -> " ++ result)
  | _ => throw one

/-- A protocol method in signature form, `name<P, ...>(INPUT) -> RESULT` (the world's
protocol): its name, type parameters and type `INPUT -> RESULT`. `none` when the line is
not in that form; `some (.error why)` when it starts as one but is misshapen. -/
def protocolSignature (text : String) : Option (Except String (String × List String × String)) :=
  let chars := text.toList
  let name := chars.takeWhile wordChar
  let rest := chars.drop name.length
  if isIdent name && (rest.head? == some '<' || rest.head? == some '(') then some (protocolSignatureOf name rest)
  else none

def declarations (lines : Array Line) :
    PS (Array Import × Array Decl × Option (String × Span) × Array (String × Span)) := do
  let fuel := lines.size + 1
  let mut layer : Option (String × Span) := none
  let mut implements : Array (String × Span) := #[]
  let mut imports : Array Import := #[]
  let mut decls : Array Decl := #[]
  for _ in [0:lines.size] do
    let i ← get
    let some line := lines[i]? | break
    set (i + 1)
    if line.indent != 0 then fail line "unexpected indentation"
    if line.text == "edition ObjectiveBend 1".toList then continue
    if startsWith line.text "layer " then
      if i != 0 then fail line "`layer over ./NAME.obend` is the module's first line"
      let rest := jsTrim (line.text.drop 6)
      unless startsWith rest "over " do fail line "a layer is declared `layer over ./NAME.obend`"
      let path := String.ofList (jsTrim (rest.drop 5))
      unless path.startsWith "./" && path.endsWith ".obend" && !path.any (· == ' ') do
        fail line "a layer is declared `layer over ./NAME.obend`"
      layer := some (path, line.span)
      continue
    if startsWith line.text "implements " then
      let name := String.ofList (jsTrim (line.text.drop 11))
      unless !name.isEmpty && name.all (fun c => c.isAlphanum || c == '_' || c == '.') do
        fail line "a module claims a protocol as `implements NAME` (or `implements Alias.NAME`)"
      implements := implements.push (name, line.span)
      continue
    if startsWith line.text "protocol " && line.text.getLast? == some ':' then
      let name := String.ofList (jsTrim ((line.text.drop 9).dropLast))
      unless isIdent name.toList do fail line "a protocol is declared `protocol NAME:`"
      let mut methods : Array Field := #[]
      for _ in [0:lines.size] do
        let j ← get
        let some member := lines[j]? | break
        if member.indent == 0 then break
        set (j + 1)
        let text := String.ofList member.text
        if let some signature := protocolSignature text then
          match signature with
          | .ok (m, params, type) =>
            methods := methods.push { name := m, type, span := member.span, typeParameters := params }
          | .error why => fail member why
          continue
        match text.splitOn ":" with
        | m :: rest =>
          let m := trimText m
          let type := trimText (":".intercalate rest)
          unless isIdent m.toList && !type.isEmpty do fail member "a protocol method is `name: TYPE`"
          methods := methods.push ⟨m, protocolType type, member.span, []⟩
        | [] => fail member "a protocol method is `name: TYPE`"
      if methods.isEmpty then fail line "a protocol declares at least one method"
      decls := decls.push (.protocol name methods.toList (methods.toList.map (·.type)) line.span)
      continue
    if let some (_, caps) ← matchAt line namedImportRe line.text then
      imports := imports.push ⟨cap line.text caps 2, cap line.text caps 1, line.span⟩
      continue
    let imported ← matchAt line importRe line.text
    if (← matchAt line importLeadRe line.text).isSome && (← liftAt line (searches genOneRe line.text)) then
      fail line "Gen-1 ./NAME.bend imports are retired; Objective Bend imports ./NAME.obend"
    if let some (_, caps) := imported then
      imports := imports.push ⟨cap line.text caps 1, cap line.text caps 2, line.span⟩
      continue
    if let some (_, caps) ← matchAt line exportRe line.text then
      let target := cap line.text caps 1 ++ "." ++ cap line.text caps 2
      let name := (capture line.text caps 3).map String.ofList |>.getD (cap line.text caps 2)
      decls := decls.push (.reexport name target line.span)
      continue
    if let some (_, caps) ← matchAt line specRe line.text then
      let parents := match capture line.text caps 3 with
        | none => []
        | some raw => (splitChar raw ',').map jsTrim
      for parent in parents do
        if (← matchAt line parentRe parent).isNone then fail line "spec parent must be a declaration name or Alias.Name"
      if parents.eraseDups.length != parents.length then fail line "duplicate spec parent"
      let mut requirements : Array Signature := #[]
      let mut methods : Array Method := #[]
      let mut claims : Array Claim := #[]
      for _ in [0:lines.size] do
        let j ← get
        let some clause := lines[j]? | break
        if clause.indent == 0 then break
        set (j + 1)
        if startsWith clause.text "requires " then
          requirements := requirements.push (← signature (clause.text.drop 9) clause)
          continue
        if let some (_, q) ← matchAt clause qualifiedRe clause.text then
          let qualifier := match capture clause.text q 2 with
            | some c => String.ofList c
            | none => let head := cap clause.text q 1; if head == "def" then "primary" else head
          let method ← signature ((capture clause.text q 3).getD []) clause
          let methodBody ← body lines fuel clause.indent
          methods := methods.push ⟨method, qualifier, methodBody⟩
          continue
        if let some (_, l) ← matchAt clause claimRe clause.text then
          let parameters ← liftBare (splitParameters ((capture clause.text l 2).getD []))
          let claimBody ← lineExpr clause ((capture clause.text l 3).getD [])
          claims := claims.push ⟨cap clause.text l 1, parameters, claimBody, clause.span⟩
          continue
        -- `law` names an ENFORCED predicate or an accepted proof obligation (GPT-6 row G); a spec
        -- property nothing checks is a `claim`. The old spelling refuses by name, never reinterprets.
        if startsWith clause.text "law " then
          fail clause "law means an enforced predicate; an unchecked property of a spec is a claim (write `claim name: expr`)"
        fail clause "expected requires, actual method body, or claim"
      let spec : ObjectiveBendSurface.Spec := ⟨cap line.text caps 2, (capture line.text caps 1).isSome,
        parents.map String.ofList, cap line.text caps 4, requirements.toList, methods.toList, claims.toList,
        (capture line.text caps 5).map String.ofList, line.span⟩
      decls := decls.push (.spec spec)
      continue
    if let some (_, caps) ← matchAt line extensionRe line.text then
      let parameters ← liftBare (splitParameters ((capture line.text caps 2).getD []))
      let extensionBody ← body lines fuel line.indent
      decls := decls.push (.extension (cap line.text caps 1) parameters (cap line.text caps 3) extensionBody
        ((capture line.text caps 4).map String.ofList) line.span)
      continue
    if let some (_, caps) ← matchAt line typeAliasRe line.text then
      decls := decls.push (.typeAlias (cap line.text caps 1) (cap line.text caps 2) line.span)
      continue
    if let some (_, caps) ← matchAt line sumRe line.text then
      let typeParameters ← match capture line.text caps 2 with
        | some raw => liftAt line (genericParameters raw)
        | none => pure []
      let mut cases : Array Field := #[]
      let mut labels : List String := []
      for _ in [0:lines.size] do
        let j ← get
        let some c := lines[j]? | break
        if c.indent == 0 then break
        set (j + 1)
        let some (_, m) ← matchAt c sumCaseRe c.text | fail c "expected sum case label: Type"
        cases := cases.push ⟨cap c.text m 1, cap c.text m 2, c.span, []⟩
        labels := labels ++ [cap c.text m 1]
      if cases.isEmpty then fail line "empty sum"
      if labels.eraseDups.length != labels.length then fail line "duplicate sum label"
      decls := decls.push (.sum (cap line.text caps 1) cases.toList typeParameters line.span)
      continue
    if let some (_, caps) ← matchAt line formRe line.text then
      let action := cap line.text caps 1
      let name := match capture line.text caps 2 with
        | some n => String.ofList n
        | none => action ++ "Form"
      let some formImport := imports.find? (·.path.endsWith "Form.obend")
        | fail line "a form block needs the Form library: import ./Form.obend as Form"
      let alias := formImport.importAlias
      let span := line.span
      let mut fields : Array (String × Expr) := #[]
      for _ in [0:lines.size] do
        let j ← get
        let some c := lines[j]? | break
        if c.indent == 0 then break
        set (j + 1)
        let some (_, m) ← matchAt c sumCaseRe c.text | fail c "expected a form field: name: kind"
        let fieldName := cap c.text m 1
        if fields.any (·.1 == fieldName) then fail c "duplicate form field"
        fields := fields.push (fieldName, ← formKind alias c ((capture c.text m 2).getD []))
      let lib := fun (type name : String) => Expr.member (.member (.var alias span) type span) name span
      let list := fields.toList.foldr (fun (n, kind) acc =>
          Expr.call (lib "Fields" "cons") [.record [("head", .record [("name", .str n span), ("kind", kind)] span),
            ("tail", acc)] span] span)
        (.call (lib "Fields" "nil") [.record [] span] span)
      let value := Expr.record [("card", .str "" span), ("action", .str action span), ("fields", list)] span
      decls := decls.push (.function ⟨name, [], alias ++ ".Form", span⟩ none (.expr value span) span)
      continue
    if let some (_, caps) ← matchAt line recordRe line.text then
      let mut methods : Array Signature := #[]
      let mut fields : Array Field := #[]
      for _ in [0:lines.size] do
        let j ← get
        let some m := lines[j]? | break
        if m.indent == 0 then break
        set (j + 1)
        if let some (_, f) ← matchAt m fieldRe m.text then
          let name ← liftBare (fieldName ((capture m.text f 1).getD []))
          fields := fields.push ⟨name, cap m.text f 2, m.span, []⟩
        else
          methods := methods.push (← signature m.text m)
      decls := decls.push (.record (cap line.text caps 1) methods.toList fields.toList line.span)
      continue
    -- `law NAME: EXPR` is a law the kernel enforces on every object of the package; its text is
    -- parsed here (a refusal names the construct outside the fragment) and again by the
    -- elaborator's module decoder, which keeps the law itself.
    if let some (_, caps) ← matchAt line lawRe line.text then
      let text := cap line.text caps 2
      if let .error message := ObjectiveBendLaw.parse text then fail line message
      let reading ← match capture line.text caps 3 with
        | none => pure ""
        | some quotedText => match Lean.Json.parse (String.ofList quotedText) with
          | .ok (.str r) => pure r
          | _ => fail line "a law's reading is a string literal: law name \"what it means\": EXPR"
      decls := decls.push (.law (cap line.text caps 1) text reading line.span)
      continue
    if startsWith line.text "law " || line.text == "law".toList || startsWith line.text "law:" then
      fail line (ObjectiveBendLaw.refusalPrefix ++ "expected `law NAME: EXPR` (a top-level law has a name and no parameters)")
    if let some (_, caps) ← matchAt line genericDefRe line.text then
      let typeParameters ← liftAt line (genericParameters ((capture line.text caps 2).getD []))
      let sig ← signature ((capture line.text caps 1).getD [] ++ (capture line.text caps 3).getD []) line
      let functionBody ← body lines fuel line.indent
      decls := decls.push (.function sig (some typeParameters) functionBody line.span)
      continue
    if startsWith line.text "def " && endsWith line.text ":" then
      let sig ← signature ((line.text.drop 4).take (line.text.length - 5)) line
      let functionBody ← body lines fuel line.indent
      decls := decls.push (.function sig none functionBody line.span)
      continue
    fail line "unsupported Objective Bend declaration"
  return (imports, decls, layer, implements)

/-- Parse one module's source text. -/
def parseObjective (source : String) : Except Diagnostic Module := do
  let lines ← sourceLines source
  let ((imports, decls, layer, implements), _) ← (declarations lines).run 0
  -- `write {...}` names the Plan library by placeholder; it becomes the module's alias.
  let plans := ((imports.find? (·.path.endsWith "Plan.obend")).map (·.importAlias)).getD "Plans"
  let decls := decls.map (·.mapVars fun n => if n == writePlansAlias then plans else n)
  -- A layer imports the module it layers over as `Super` (unless it already does).
  let imports := match layer with
    | some (path, span) =>
      if imports.any (fun i => i.importAlias == "Super" && i.path == path) then imports
      else #[(⟨path, "Super", span⟩ : Import)] ++ imports
    | none => imports
  return ⟨imports.toList, decls.toList, layer.map (·.1), implements.toList⟩

/-- Strict UTF-8 decoding as `new TextDecoder("utf-8",{fatal:true})`: invalid bytes refuse and a
leading byte-order mark is consumed. -/
def decodeSource (bytes : ByteArray) : Option String :=
  (String.fromUTF8? bytes).map fun s =>
    match s.toList with
    | '﻿' :: rest => String.ofList rest
    | _ => s

end Minidregg.Compiler.ObjectiveBendParse
