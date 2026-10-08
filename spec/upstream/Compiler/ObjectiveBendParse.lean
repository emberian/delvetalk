/- Objective Bend edition 1 source parser.

Source text → the `dregg.objective-bend.module.v1` AST (JSON) that
`Compiler.ObjectiveBendElaborate.decodeModule` reads. Ported from the retired
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
namespace Minidregg.Compiler.ObjectiveBendParse
open Lean
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
def matchFuel (s : List Char) : Nat := 64 * (s.length + 64)

/-- The longest subject a pattern is matched against (one source line). Longer lines refuse
rather than recurse that deep. -/
def maxLine : Nat := 16384

/-- A match anchored at the start (`^...`): `some captures`, `none`, or a capacity refusal. -/
def anchored (r : Re) (s : List Char) : Except String (Option (Nat × Caps)) :=
  if s.length > maxLine then .error "Error: source line capacity" else
  match run (matchFuel s) r s 0 (Array.replicate 10 none) (fun _ stop caps => .found stop caps) with
  | .found stop caps => .ok (some (stop, caps))
  | .none => .ok none
  | .exhausted => .error "Error: source line capacity"

/-- An unanchored test (`/.../.test`): a match starting anywhere. -/
def searches (r : Re) (s : List Char) : Except String Bool := do
  let mut rest := s
  for _ in [0:s.length + 1] do
    if (← anchored r rest).isSome then return true
    rest := rest.drop 1
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

structure Span where
  start : Nat
  stop : Nat
  line : Nat
  deriving Inhabited, Repr, BEq

def Span.json (s : Span) : Json :=
  Json.mkObj [("start", toJson s.start), ("end", toJson s.stop), ("line", toJson s.line)]

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

def parameterJson (name type quantity : String) : Json :=
  Json.mkObj [("name", toJson name), ("type", toJson type), ("quantity", toJson quantity)]

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

def splitParameters (raw : List Char) : Except String (List Json) := do
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
    return parameterJson (String.ofList name) (String.ofList ((capture piece caps 4).getD ['_'])) quantity

/-! ## Expressions -/

structure Token where
  text : List Char
  /-- Character indices into the expression text. -/
  start : Nat
  stop : Nat
  deriving Inhabited

/-- `^(?:[A-Za-z_]\w*|[0-9]+n?|"(?:[^"\\]|\\.)*"|->|==|!=|<=|>=|&&|\|\||[{}:=().,+*/%<>-])` -/
def tokenRe : Re := alts [ident, seqs [many1 (.char asciiDigit), opt (chr 'n')], quoted,
  str "->", str "==", str "!=", str "<=", str ">=", str "&&", str "||",
  .char (fun c => "{}:=().,+*/%<>-".toList.contains c)]

def tokenize (text : List Char) : Except String (Array Token) := do
  let mut tokens : Array Token := #[]
  let mut rest := text
  let mut at_ := 0
  for _ in [0:text.length + 1] do
    match rest with
    | [] => break
    | c :: tail =>
      if jsSpace c then
        rest := tail; at_ := at_ + 1
      else
        let some (stop, _) ← anchored tokenRe rest
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

def node (kind : String) (fields : List (String × Json)) (span : Span) : Json :=
  Json.mkObj ([("kind", toJson kind)] ++ fields ++ [("span", span.json)])

def isNumberToken (t : List Char) : Bool :=
  let digits := t.takeWhile asciiDigit
  !digits.isEmpty && (t.drop digits.length == [] || t.drop digits.length == ['n'])

/-- `value.replace(/n$/," ").trim().replace(/^0+(?=[0-9])/,"")` -/
def natValue (t : List Char) : String :=
  let digits := t.takeWhile asciiDigit
  let stripped := digits.dropWhile (· == '0')
  String.ofList (if stripped.isEmpty then ['0'] else stripped)

def kindOf (j : Json) : String := (j.getObjValAs? String "kind").toOption.getD ""

/-- `parse(minimum)`: an atom, its postfix member/call chain, then binary operators of at
least `minimum` precedence (left-associative). -/
def parseExpr (env : ExprEnv) : Nat → Nat → EP (Json × Span)
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
      return (node "let" [("name", toJson (tokenText name)), ("type", toJson type), ("value", value), ("body", letBody)] span, span)
    if firstText == "if" then
      let (condition, _) ← parseExpr env fuel 0
      discard <| take env (some "then")
      let (whenTrue, _) ← parseExpr env fuel 0
      discard <| take env (some "else")
      let (whenFalse, falseSpan) ← parseExpr env fuel 0
      let span := { env.location first.start first.stop with stop := falseSpan.stop }
      return (node "if" [("condition", condition), ("whenTrue", whenTrue), ("whenFalse", whenFalse)] span, span)
    let mut result : Json × Span := (Json.null, default)
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
          (node "lambda" [("parameters", Json.arr parameters.toArray), ("resultType", toJson (String.ofList resultType)),
            ("body", closureBody)] span, span)
        else
          (node "extension-value" [("parameters", Json.arr parameters.toArray),
            ("targetType", toJson (String.ofList resultType)), ("body", closureBody)] span, span)
    else if firstText == "{" then
      let mut fields : Array Json := #[]
      if (← peek env) != some "}" then
        for _ in [0:env.tokens.size + 1] do
          let key ← take env
          let name ← StateT.lift (fieldName key.text)
          discard <| take env (some ":")
          let (value, _) ← parseExpr env fuel 0
          fields := fields.push (Json.mkObj [("name", toJson name), ("value", value)])
          if (← peek env) != some "," then break
          discard <| take env (some ",")
      let closing ← take env (some "}")
      let span := env.location first.start closing.stop
      result := (node "record" [("fields", Json.arr fields)] span, span)
    else if firstText == "(" then
      if (← peek env) == some ")" then
        let closing ← take env (some ")")
        let span := env.location first.start closing.stop
        result := (node "unit" [] span, span)
      else
        result ← parseExpr env fuel 0
        discard <| take env (some ")")
    else if firstText == "true" || firstText == "false" then
      let span := env.location first.start first.stop
      result := (node "bool" [("value", toJson (firstText == "true"))] span, span)
    else if isNumberToken first.text then
      let span := env.location first.start first.stop
      result := (node "nat" [("value", toJson (natValue first.text))] span, span)
    else if first.text.head? == some '"' then
      let span := env.location first.start first.stop
      let value ← StateT.lift (jsonStringLiteral first.text)
      result := (node "string" [("value", toJson value)] span, span)
    else if isIdent first.text then
      let span := env.location first.start first.stop
      result := (node "var" [("name", toJson firstText)] span, span)
    else throw "Error: expected expression atom"
    for _ in [0:env.tokens.size + 1] do
      let some next := (← peek env) | break
      if next == "." then
        discard <| take env (some ".")
        let field ← take env
        let name ← StateT.lift (fieldName field.text)
        let span := { result.2 with stop := (env.location field.start field.stop).stop }
        result := (node "member" [("target", result.1), ("name", toJson name)] span, span)
        continue
      if next == "(" then
        discard <| take env (some "(")
        let mut args : Array Json := #[]
        if (← peek env) != some ")" then
          for _ in [0:env.tokens.size + 1] do
            let (arg, _) ← parseExpr env fuel 0
            args := args.push arg
            if (← peek env) != some "," then break
            discard <| take env (some ",")
        let closing ← take env (some ")")
        let span := { result.2 with stop := (env.location closing.start closing.stop).stop }
        let calleeName := if kindOf result.1 == "var" then (result.1.getObjValAs? String "name").toOption else none
        if calleeName == some "compose" then
          result := (node "compose" [("specifications", Json.arr args)] span, span)
        else if calleeName == some "fix" then
          let #[specification, inherited] := args | throw "Error: fix expects specification and inherited target"
          result := (node "fix" [("specification", specification), ("inherited", inherited)] span, span)
        else if calleeName == some "extend" then
          match args with
          | #[inherited, fields] =>
            if kindOf fields != "record" then throw "Error: extend expects inherited target and record fields"
            result := (node "extend" [("inherited", inherited),
              ("fields", (fields.getObjVal? "fields").toOption.getD (Json.arr #[]))] span, span)
          | _ => throw "Error: extend expects inherited target and record fields"
        else
          result := (node "call" [("callee", result.1), ("args", Json.arr args)] span, span)
        continue
      let some priority := precedence next | break
      if priority < minimum then break
      discard <| take env
      let (right, rightSpan) ← parseExpr env fuel (priority + 1)
      let span := { result.2 with stop := rightSpan.stop }
      result := (node "binary" [("op", toJson next), ("left", result.1), ("right", right)] span, span)
    return result

/-- `expression(text, sourceSpan)`: the whole text is one expression. `start` is the absolute
byte offset of the text's first character. -/
def expression (text : List Char) (start line : Nat) : Except String Json := do
  let tokens ← tokenize text
  let byteAt := (text.foldl (fun (acc : Array Nat × Nat) c => (acc.1.push acc.2, acc.2 + c.utf8Size))
    (#[], start)) |> fun (acc, last) => acc.push last
  let env : ExprEnv := ⟨text, tokens, byteAt, line⟩
  let ((json, _), cursor) ← (parseExpr env (tokens.size + 1) 0).run 0
  if cursor != tokens.size then throw "Error: unexpected trailing expression token"
  return json

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

/-- `String.prototype.lastIndexOf` (character index; equal prefixes, so equal bytes). -/
def lastIndexOf (hay needle : List Char) : Nat :=
  ((List.range (hay.length + 1)).reverse.find? (fun i => needle.isPrefixOf (hay.drop i))).getD 0

/-- `expr(text, line)`: an expression found at its last occurrence in the line; its errors
become line diagnostics. -/
def lineExpr (line : Line) (text : List Char) : PS Json :=
  liftAt line (expression text (line.start + utf8Length (line.text.take (lastIndexOf line.text text))) line.number)

/-- `^([A-Za-z_]\w*)\s*\((.*)\)(?:\s*->\s*(.+?))?\s*$` -/
def signatureRe : Re := seqs [group 1 ident, many space, chr '(', group 2 (many dot), chr ')',
  opt (seqs [many space, str "->", many space, group 3 (lazy1 dot)]), many space, .done]

def signature (raw : List Char) (line : Line) : PS (String × List Json × String × Span) := do
  let some (_, caps) ← matchAt line signatureRe raw | fail line "expected method signature"
  let parameters ← liftAt line (splitParameters ((capture raw caps 2).getD []))
  return (String.ofList ((capture raw caps 1).getD []), parameters,
    String.ofList ((capture raw caps 3).getD ['_']), line.span)

def signatureJson (s : String × List Json × String × Span) : List (String × Json) :=
  [("name", toJson s.1), ("parameters", Json.arr s.2.1.toArray), ("resultType", toJson s.2.2.1), ("span", s.2.2.2.json)]

/-- `^case\s+(0n?|1n?\+([A-Za-z_]\w*)|_|true|false|([A-Za-z_]\w*)\(\s*([A-Za-z_]\w*)?\s*\))\s*:\s*(.*)$` -/
def caseRe : Re := seqs [str "case", many1 space,
  group 1 (alts [.seq (chr '0') (opt (chr 'n')), seqs [chr '1', opt (chr 'n'), chr '+', group 2 ident], chr '_',
    str "true", str "false", seqs [group 3 ident, chr '(', many space, opt (group 4 ident), many space, chr ')']]),
  many space, chr ':', many space, group 5 (many dot), .done]

/-- `^let\s+([A-Za-z_]\w*)\s*(?::\s*(.+?))?\s*=\s*(.+)$` -/
def letRe : Re := seqs [str "let", many1 space, group 1 ident, many space,
  opt (seqs [chr ':', many space, group 2 (lazy1 dot)]), many space, chr '=', many space, group 3 (many1 dot), .done]

def startsWith (s : List Char) (p : String) : Bool := p.toList.isPrefixOf s
def endsWith (s : List Char) (p : String) : Bool := p.toList.reverse.isPrefixOf s.reverse

/-- `body(indent)`: the indented method body after a header line. -/
def body (lines : Array Line) : Nat → Nat → PS Json
  | 0, _ => bare "Error: body nesting capacity"
  | fuel + 1, indent => do
    let i ← get
    let some line := lines[i]? | bare "Error: missing indented method body"
    if line.indent ≤ indent then bare "Error: missing indented method body"
    set (i + 1)
    if startsWith line.text "match " && endsWith line.text ":" then
      let scrutinee ← lineExpr line ((line.text.drop 6).take (line.text.length - 7))
      let mut branches : Array Json := #[]
      for _ in [0:lines.size] do
        let j ← get
        let some branch := lines[j]? | break
        if branch.indent ≤ line.indent then break
        set (j + 1)
        let some (_, caps) ← matchAt branch caseRe branch.text
          | fail branch "expected zero/successor/true/false/label(binder)/wildcard case"
        let whole := (capture branch.text caps 1).getD []
        let pattern : Json :=
          if whole == ['_'] then Json.mkObj [("kind", toJson "wildcard")]
          else if whole == "true".toList || whole == "false".toList then
            Json.mkObj [("kind", toJson "bool"), ("value", toJson (whole == "true".toList))]
          else match capture branch.text caps 3 with
            | some label => Json.mkObj [("kind", toJson "constructor"), ("label", toJson (String.ofList label)),
                ("binder", toJson (String.ofList ((capture branch.text caps 4).getD ['_'])))]
            | none => match capture branch.text caps 2 with
              | some binder => Json.mkObj [("kind", toJson "succ"), ("binder", toJson (String.ofList binder))]
              | none => Json.mkObj [("kind", toJson "zero")]
        let inline := (capture branch.text caps 5).getD []
        let branchBody ← if inline.isEmpty then body lines fuel branch.indent
          else do
            let e ← lineExpr branch inline
            pure (Json.mkObj [("kind", toJson "expression"), ("expression", e), ("span", branch.span.json)])
        branches := branches.push (Json.mkObj [("pattern", pattern), ("body", branchBody), ("span", branch.span.json)])
      if branches.isEmpty then fail line "empty match"
      return Json.mkObj [("kind", toJson "match"), ("scrutinee", scrutinee), ("branches", Json.arr branches),
        ("span", line.span.json)]
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
          return Json.mkObj [("kind", toJson "let"), ("name", toJson (String.ofList name)),
            ("type", toJson (String.ofList ((capture line.text caps 2).getD ['_']))), ("value", value),
            ("body", rest), ("span", line.span.json)]
    let text := if startsWith line.text "return " then line.text.drop 7 else line.text
    return Json.mkObj [("kind", toJson "expression"), ("expression", ← lineExpr line text), ("span", line.span.json)]

def namedImportRe : Re := seqs [str "import", many1 space, group 1 ident, many1 space, str "from", many1 space, chr '"',
  group 2 (seqs [str "./", many1 (.char (fun c => c != '"' && c != '\\')), str ".obend"]), chr '"', .done]
def importRe : Re := seqs [str "import", many1 space, group 1 (many1 nonSpace),
  opt (seqs [many1 space, str "as", many1 space, group 2 ident]), .done]
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
def sumRe : Re := seqs [str "sum", many1 space, group 1 ident, chr ':', .done]
def sumCaseRe : Re := seqs [group 1 ident, many space, chr ':', many space, group 2 (many1 dot), .done]
def recordRe : Re := seqs [str "record", many1 space, group 1 ident, chr ':', .done]
def fieldRe : Re := seqs [group 1 (.alt ident quoted), chr ':', many space, group 2 (many1 dot), .done]
/-- `law NAME: EXPR`, a top-level ENFORCED law of the package (`Compiler.ObjectiveBendLaw`). -/
def lawRe : Re := seqs [str "law", many1 space, group 1 ident, many space, chr ':', many space, group 2 (many1 dot), .done]

/-- `String.prototype.split` on one character. -/
def splitChar (s : List Char) (sep : Char) : List (List Char) :=
  let (finished, current) := s.foldl (fun (acc : List (List Char) × List Char) c =>
    if c == sep then (acc.2.reverse :: acc.1, []) else (acc.1, c :: acc.2)) ([], [])
  (current.reverse :: finished).reverse

def cap (s : List Char) (caps : Caps) (i : Nat) : String := String.ofList ((capture s caps i).getD [])

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

def declarations (lines : Array Line) : PS (Array Json × Array Json) := do
  let fuel := lines.size + 1
  let mut imports : Array Json := #[]
  let mut decls : Array Json := #[]
  for _ in [0:lines.size] do
    let i ← get
    let some line := lines[i]? | break
    set (i + 1)
    if line.indent != 0 then fail line "unexpected indentation"
    if line.text == "edition ObjectiveBend 1".toList then continue
    if let some (_, caps) ← matchAt line namedImportRe line.text then
      imports := imports.push (Json.mkObj [("path", toJson (cap line.text caps 2)), ("alias", toJson (cap line.text caps 1)),
        ("span", line.span.json)])
      continue
    let imported ← matchAt line importRe line.text
    if (← matchAt line importLeadRe line.text).isSome && (← liftAt line (searches genOneRe line.text)) then
      fail line "Gen-1 ./NAME.bend imports are retired; Objective Bend imports ./NAME.obend"
    if let some (_, caps) := imported then
      imports := imports.push (Json.mkObj [("path", toJson (cap line.text caps 1)), ("alias", toJson (cap line.text caps 2)),
        ("span", line.span.json)])
      continue
    if let some (_, caps) ← matchAt line specRe line.text then
      let parents := match capture line.text caps 3 with
        | none => []
        | some raw => (splitChar raw ',').map jsTrim
      for parent in parents do
        if (← matchAt line parentRe parent).isNone then fail line "spec parent must be a declaration name or Alias.Name"
      if parents.eraseDups.length != parents.length then fail line "duplicate spec parent"
      let mut requirements : Array Json := #[]
      let mut methods : Array Json := #[]
      let mut claims : Array Json := #[]
      for _ in [0:lines.size] do
        let j ← get
        let some clause := lines[j]? | break
        if clause.indent == 0 then break
        set (j + 1)
        if startsWith clause.text "requires " then
          requirements := requirements.push (Json.mkObj (signatureJson (← signature (clause.text.drop 9) clause)))
          continue
        if let some (_, q) ← matchAt clause qualifiedRe clause.text then
          let qualifier := match capture clause.text q 2 with
            | some c => String.ofList c
            | none => let head := cap clause.text q 1; if head == "def" then "primary" else head
          let method ← signature ((capture clause.text q 3).getD []) clause
          let methodBody ← body lines fuel clause.indent
          methods := methods.push (Json.mkObj (signatureJson method ++ [("qualifier", toJson qualifier), ("body", methodBody)]))
          continue
        if let some (_, l) ← matchAt clause claimRe clause.text then
          let parameters ← liftBare (splitParameters ((capture clause.text l 2).getD []))
          let claimBody ← lineExpr clause ((capture clause.text l 3).getD [])
          claims := claims.push (Json.mkObj [("name", toJson (cap clause.text l 1)), ("parameters", Json.arr parameters.toArray),
            ("body", claimBody), ("span", clause.span.json)])
          continue
        -- `law` names an ENFORCED predicate or an accepted proof obligation (GPT-6 row G); a spec
        -- property nothing checks is a `claim`. The old spelling refuses by name, never reinterprets.
        if startsWith clause.text "law " then
          fail clause "law means an enforced predicate; an unchecked property of a spec is a claim (write `claim name: expr`)"
        fail clause "expected requires, actual method body, or claim"
      decls := decls.push (Json.mkObj ([("kind", toJson "spec"), ("name", toJson (cap line.text caps 2)),
        ("suffix", toJson (capture line.text caps 1).isSome), ("parents", toJson (parents.map String.ofList)),
        ("targetType", toJson (cap line.text caps 4)), ("requirements", Json.arr requirements), ("methods", Json.arr methods),
        ("claims", Json.arr claims), ("span", line.span.json)] ++
        (match capture line.text caps 5 with
          | some b => [("binders", toJson (String.ofList b))]
          | none => [])))
      continue
    if let some (_, caps) ← matchAt line extensionRe line.text then
      let parameters ← liftBare (splitParameters ((capture line.text caps 2).getD []))
      let extensionBody ← body lines fuel line.indent
      decls := decls.push (Json.mkObj ([("kind", toJson "extension"), ("name", toJson (cap line.text caps 1)),
        ("parameters", Json.arr parameters.toArray), ("targetType", toJson (cap line.text caps 3)),
        ("body", extensionBody), ("span", line.span.json)] ++
        (match capture line.text caps 4 with
          | some b => [("binders", toJson (String.ofList b))]
          | none => [])))
      continue
    if let some (_, caps) ← matchAt line sumRe line.text then
      let mut cases : Array Json := #[]
      let mut labels : List String := []
      for _ in [0:lines.size] do
        let j ← get
        let some c := lines[j]? | break
        if c.indent == 0 then break
        set (j + 1)
        let some (_, m) ← matchAt c sumCaseRe c.text | fail c "expected sum case label: Type"
        cases := cases.push (Json.mkObj [("label", toJson (cap c.text m 1)), ("type", toJson (cap c.text m 2)),
          ("span", c.span.json)])
        labels := labels ++ [cap c.text m 1]
      if cases.isEmpty then fail line "empty sum"
      if labels.eraseDups.length != labels.length then fail line "duplicate sum label"
      decls := decls.push (Json.mkObj [("kind", toJson "sum"), ("name", toJson (cap line.text caps 1)),
        ("cases", Json.arr cases), ("span", line.span.json)])
      continue
    if let some (_, caps) ← matchAt line recordRe line.text then
      let mut methods : Array Json := #[]
      let mut fields : Array Json := #[]
      for _ in [0:lines.size] do
        let j ← get
        let some m := lines[j]? | break
        if m.indent == 0 then break
        set (j + 1)
        if let some (_, f) ← matchAt m fieldRe m.text then
          let name ← liftBare (fieldName ((capture m.text f 1).getD []))
          fields := fields.push (Json.mkObj [("name", toJson name), ("type", toJson (cap m.text f 2)), ("span", m.span.json)])
        else
          methods := methods.push (Json.mkObj (signatureJson (← signature m.text m)))
      decls := decls.push (Json.mkObj [("kind", toJson "record"), ("name", toJson (cap line.text caps 1)),
        ("methods", Json.arr methods), ("fields", Json.arr fields), ("span", line.span.json)])
      continue
    -- `law NAME: EXPR` is a law the kernel enforces on every object of the package; its text is
    -- parsed here (a refusal names the construct outside the fragment) and again by the
    -- elaborator's module decoder, which keeps the law itself.
    if let some (_, caps) ← matchAt line lawRe line.text then
      let text := cap line.text caps 2
      if let .error message := ObjectiveBendLaw.parse text then fail line message
      decls := decls.push (Json.mkObj [("kind", toJson "law"), ("name", toJson (cap line.text caps 1)),
        ("source", toJson text), ("span", line.span.json)])
      continue
    if startsWith line.text "law " || line.text == "law".toList || startsWith line.text "law:" then
      fail line (ObjectiveBendLaw.refusalPrefix ++ "expected `law NAME: EXPR` (a top-level law has a name and no parameters)")
    if startsWith line.text "def " && endsWith line.text ":" then
      let sig ← signature ((line.text.drop 4).take (line.text.length - 5)) line
      let functionBody ← body lines fuel line.indent
      decls := decls.push (Json.mkObj [("kind", toJson "function"), ("signature", Json.mkObj (signatureJson sig)),
        ("body", functionBody), ("span", line.span.json)])
      continue
    fail line "unsupported Objective Bend declaration"
  return (imports, decls)

def moduleSchema : String := "dregg.objective-bend.module.v1"

/-- Parse one module's source text. -/
def parseObjective (source : String) : Except Diagnostic Json := do
  let lines ← sourceLines source
  let ((imports, decls), _) ← (declarations lines).run 0
  return Json.mkObj [("schema", toJson moduleSchema), ("edition", toJson "objective-bend-1"),
    ("imports", Json.arr imports), ("declarations", Json.arr decls),
    ("theoremScope", toJson "new source AST; elaboration and reference semantics are Objective Core4")]

/-- Strict UTF-8 decoding as `new TextDecoder("utf-8",{fatal:true})`: invalid bytes refuse and a
leading byte-order mark is consumed. -/
def decodeSource (bytes : ByteArray) : Option String :=
  (String.fromUTF8? bytes).map fun s =>
    match s.toList with
    | '﻿' :: rest => String.ofList rest
    | _ => s

end Minidregg.Compiler.ObjectiveBendParse
