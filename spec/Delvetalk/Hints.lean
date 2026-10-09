/- Dialect hints: when the compiler refuses a package, name the most likely
pseudo-Bend habit behind the refusal and state the real form in one line. Agents
writing for DelveTalk bring forms from other languages (`fn(t) t.id != id`,
`Maybe<T>`, `halt(reason)`, `Some(v)`, `match x: Pat -> body`, `record A: X | Y`,
`law name: match ...`). The checker's messages are about the core, not the habit.

A hint never changes what is accepted: it is computed only for a refusal and it
rides beside the diagnostic's stage, message, module and span. It fires only when
its trigger is present where the refusal points:

- a parse refusal: the text of the one line it names (there is no parsed module);
- an elaboration or type-proposal refusal: the parsed declaration that holds the
  line it names; without a line, the declarations its message names by key
  (`Module.name`), else any declaration, but then the trigger itself (`halt`,
  `Some`, `Maybe<`) must appear in the message;
- a refusal of the checker on the typed packet, or of the request: never. -/
import Compiler.ObjectiveBendSurface
namespace Delvetalk.Hints
open Minidregg.Compiler.ObjectiveBendSurface (Expr Body Decl Param Span)

def has (text pattern : String) : Bool := (text.splitOn pattern).length > 1

def trimStart (s : String) : String := String.ofList (s.toList.dropWhile Char.isWhitespace)
def trimBoth (s : String) : String := String.ofList ((s.toList.dropWhile Char.isWhitespace).reverse.dropWhile Char.isWhitespace).reverse

def isIdentChar (c : Char) : Bool := c.isAlphanum || c == '_'

/-- The text between the first `open` after `after` and its matching `)`. -/
def parenthesized (line after : String) : Option String :=
  match line.splitOn after with
  | _ :: rest :: _ =>
    let inner := (rest.toList.takeWhile (· != ')'))
    if inner.length == rest.length then none else some (String.ofList inner)
  | _ => none

/-- Parameters listed without a `: Type`. -/
def untypedParameters (inner : String) : Bool :=
  let parts := ((inner.splitOn ",").map trimBoth).filter (· != "")
  !parts.isEmpty && parts.any (fun p => !has p ":")

/-- A match arm written `label(x) -> body` or `Pattern -> body`. -/
def arrowArm (trimmed : String) : Bool :=
  let head := trimmed.toList.takeWhile isIdentChar
  !head.isEmpty && !["def", "fn", "case", "law", "record", "sum", "type"].contains (String.ofList head) &&
  (let rest := trimStart (String.ofList (trimmed.toList.drop head.length))
   rest.startsWith "->" || rest.startsWith "=>" ||
   (rest.startsWith "(" && (let after := rest.toList.dropWhile (· != ')')
     let tail := trimStart (String.ofList (after.drop 1))
     tail.startsWith "->" || tail.startsWith "=>")))

/-- A `[` outside every string literal on the line. -/
def bracketOutsideString (line : String) : Bool :=
  (line.toList.foldl (fun (state : Bool × Bool × Bool) c =>
    let (inString, escaped, found) := state
    if found then state
    else if inString then
      if escaped then (true, false, false) else if c == '\\' then (true, true, false)
      else if c == '"' then (false, false, false) else (true, false, false)
    else if c == '"' then (true, false, false)
    else (false, false, c == '[')) (false, false, false)).2.2

/-- The hint for one source line, if it shows a dialect habit. `source` is the
whole module (to tell a declared `Maybe` from an assumed builtin). -/
def lineHint (source line : String) : Option String :=
  let trimmed := trimBoth line
  if trimmed.startsWith "//" then some "comments start with `#`; `//` is not a comment in Bend"
  else if (trimmed.startsWith "record " || trimmed.startsWith "sum ") && has trimmed "|" then
    some "a sum is declared with `sum Name:` and its arms as `label: {fields}`, one per indented line; there is no `A | B` form"
  else if trimmed.startsWith "law " && (has trimmed "match" || trimmed.endsWith ":") then
    some "laws are one line over request facts, not a match: `law name: EXPR` (for example `law owner: request.kind == 0 or request.subject == \"me\"`)"
  else if trimmed.startsWith "def " && (((parenthesized trimmed "(").map untypedParameters).getD false || !has trimmed "->") then
    some "definitions are `def name(x: T) -> U:`; parameter and result types are required"
  else if ((parenthesized trimmed "fn(").map untypedParameters).getD false then
    some "closures are `fn(x: T) -> U: body`; parameter and result types are required"
  else if has line "halt(" then
    some "there is no halt; to go on only with the response you expect, write `let written(_) = perform(Plan.write({...}))` and continue the block (any other response refuses the turn by name); a refusal the caller should read is a sum arm you return (`Result.refused({...})`)"
  else if has line "Some(" || has line "None" then
    some "there is no Some/None; a sum value is `Sum.label({fields})`, for example `Maybe.some({value: v})` with `sum Maybe<T>:` declared"
  else if (has line "Maybe<" || has line "Option<") && !has source "sum Maybe" && !has source "sum Option" then
    some "there is no Maybe builtin; declare `sum Maybe<T>:` with arms `none: {}` and `some: {value: T}`"
  else if !trimmed.startsWith "#" && bracketOutsideString line then
    some "there are no list literals; build a list as `Lists.List.cons({head: x, tail: rest})` ending in `Lists.List.nil({})`"
  else if arrowArm trimmed then
    some "match arms are `case label(x): body` (`case _: body` for the rest); there is no `Pattern -> body`"
  else none

/-! ## Triggers in a parsed declaration -/

/-- What a declaration mentions that a hint can be about. -/
structure Facts where
  vars : List String := []
  types : List String := []
  untypedClosure : Bool := false

def Facts.params (f : Facts) (ps : List Param) : Facts :=
  { f with types := ps.map (·.type) ++ f.types }

mutual
def exprFacts : Facts → Expr → Facts
  | f, .var n _ => { f with vars := n :: f.vars }
  | f, .nat .. | f, .bool .. | f, .str .. | f, .unit .. => f
  | f, .record fs _ => fieldFacts f fs
  | f, .extend i fs _ => fieldFacts (exprFacts f i) fs
  | f, .member t _ _ => exprFacts f t
  | f, .call c args _ => listFacts (exprFacts f c) args
  | f, .compose specs _ => listFacts f specs
  | f, .fix a b _ | f, .binary _ a b _ => exprFacts (exprFacts f a) b
  | f, .lambda ps r b _ | f, .extensionValue ps r b _ =>
    let g := f.params ps
    exprFacts { g with types := r :: g.types, untypedClosure := f.untypedClosure || ps.any (·.type == "_") } b
  | f, .ite a b c _ => exprFacts (exprFacts (exprFacts f a) b) c
  | f, .letE _ t v b _ => exprFacts (exprFacts { f with types := t :: f.types } v) b
  | f, .specialize t types _ => exprFacts { f with types := types ++ f.types } t
  | f, .dataOf t v _ => exprFacts { f with types := t :: f.types } v
def fieldFacts : Facts → List (String × Expr) → Facts
  | f, [] => f
  | f, (_, v) :: rest => fieldFacts (exprFacts f v) rest
def listFacts : Facts → List Expr → Facts
  | f, [] => f
  | f, e :: rest => listFacts (exprFacts f e) rest
end

mutual
def bodyFacts : Facts → Body → Facts
  | f, .expr e _ => exprFacts f e
  | f, .cases sc branches _ => branchFacts (exprFacts f sc) branches
  | f, .letB _ t v b _ => bodyFacts (exprFacts { f with types := t :: f.types } v) b
def branchFacts : Facts → List (Minidregg.Compiler.ObjectiveBendSurface.Pattern × Body × Span) → Facts
  | f, [] => f
  | f, (_, b, _) :: rest => branchFacts (bodyFacts f b) rest
end

/-- The facts of a signature (its parameter and result types) and then of a body. -/
def signedFacts (f : Facts) (ps : List Param) (result : String) (b : Body) : Facts :=
  bodyFacts { (f.params ps) with types := result :: (f.params ps).types } b

def declFacts : Decl → Facts
  | .function sig _ b _ => signedFacts {} sig.params sig.resultType b
  | .extension _ ps t b _ _ => signedFacts {} ps t b
  | .spec sp => sp.methods.foldl (fun f m => signedFacts f m.signature.params m.signature.resultType m.body)
      (sp.claims.foldl (fun f c => exprFacts (f.params c.params) c.body) {})
  | .record _ methods fields _ =>
    { types := fields.map (·.type) ++ methods.flatMap (fun m => m.resultType :: m.params.map (·.type)) }
  | .sum _ cases _ _ => { types := cases.map (·.type) }
  | .typeAlias _ t _ => { types := [t] }
  | _ => {}

/-- `name<` with nothing qualifying it (`Lists.Maybe<T>` is a declared sum, not a builtin). -/
def bareGeneric (text name : String) : Bool :=
  match text.splitOn (name ++ "<") with
  | first :: rest => !rest.isEmpty && (first :: rest.dropLast).any fun before =>
      match before.toList.getLast? with
      | some c => !(isIdentChar c || c == '.')
      | none => true
  | [] => false

def declares (m : Minidregg.Compiler.ObjectiveBendSurface.Module) (name : String) : Bool :=
  m.decls.any fun d => d.name == name && (d matches .sum ..)

/-- The hint a parsed declaration's own triggers give, each with the word that names it. -/
def declHint (m : Minidregg.Compiler.ObjectiveBendSurface.Module) (d : Decl) : Option (String × String) :=
  let f := declFacts d
  let untypedDef := match d with
    | .function sig _ _ _ => sig.resultType == "_" || sig.params.any (·.type == "_")
    | _ => false
  if untypedDef then
    some (d.name, "definitions are `def name(x: T) -> U:`; parameter and result types are required")
  else if f.untypedClosure then
    some (d.name, "closures are `fn(x: T) -> U: body`; parameter and result types are required")
  else if f.vars.contains "halt" then
    some ("halt", "there is no halt; to go on only with the response you expect, write `let written(_) = perform(Plan.write({...}))` and continue the block (any other response refuses the turn by name); a refusal the caller should read is a sum arm you return (`Result.refused({...})`)")
  else if f.vars.contains "Some" || f.vars.contains "None" then
    some ((if f.vars.contains "Some" then "Some" else "None"),
      "there is no Some/None; a sum value is `Sum.label({fields})`, for example `Maybe.some({value: v})` with `sum Maybe<T>:` declared")
  else
    let builtin := fun (name : String) => !declares m name && f.types.any (bareGeneric · name)
    if builtin "Maybe" || builtin "Option" then
      some ((if builtin "Maybe" then "Maybe<" else "Option<"),
        "there is no Maybe builtin; declare `sum Maybe<T>:` with arms `none: {}` and `some: {value: T}`")
    else none

/-- The declaration of `m` that holds `line`: the last one whose header is at or above it. -/
def declAt (m : Minidregg.Compiler.ObjectiveBendSurface.Module) (line : Nat) : Option Decl :=
  (m.decls.filter fun d => d.span.line ≤ line).getLast?

/-- A refused module as the hint sees it: its name, source text and, when it parsed, its surface. -/
abbrev Refused := String × String × Option Minidregg.Compiler.ObjectiveBendSurface.Module

/-- The hint for a refusal at `stage` naming `module` and `line` (1-based) with `message`. -/
def hintFor (modules : List Refused) (stage message : String) (module : Option String) (line : Option Nat) :
    Option String :=
  let named := module.bind fun m => modules.find? (·.1 == m)
  if stage == "objective-source-parse" then
    named.bind fun (_, source, _) => line.bind fun n => ((source.splitOn "\n")[n - 1]?).bind (lineHint source)
  else if stage == "objective-typed-check" || stage == "package-request" then none
  else
    match named, line with
    | some (_, _, some ast), some n => ((declAt ast n).bind (declHint ast)).map (·.2)
    | _, _ =>
      let keyed := modules.findSome? fun (name, _, ast) => ast.bind fun ast =>
        (ast.decls.filter fun d => has message (name ++ "." ++ d.name)).findSome? (declHint ast)
      let anywhere := modules.reverse.findSome? fun (_, _, ast) => ast.bind fun ast =>
        ast.decls.findSome? fun d => (declHint ast d).bind fun (trigger, hint) =>
          if has message trigger then some hint else none
      (keyed.map (·.2)) <|> anywhere

end Delvetalk.Hints
