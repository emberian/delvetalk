/- Dialect hints: when the compiler refuses a package, name the most likely
pseudo-Bend habit behind the refusal and state the real form in one line. Agents
writing for DelveTalk bring forms from other languages (`fn(t) t.id != id`,
`Maybe<T>`, `halt(reason)`, `Some(v)`, `match x: Pat -> body`, `record A: X | Y`,
`law name: match ...`). The checker's messages are about the core, not the habit.

A hint never changes what is accepted: it is computed only for a refusal, from
the refused module's source text, and it rides beside the diagnostic's stage,
message, module and span. The line the diagnostic names is examined first, then
the rest of that module, then every module. -/
namespace Delvetalk.Hints

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
    some "there is no halt; a refusal is a sum arm you return (declare it in your result sum and return `Result.refused({...})`)"
  else if has line "Some(" || has line "None" then
    some "there is no Some/None; a sum value is `Sum.label({fields})`, for example `Maybe.some({value: v})` with `sum Maybe<T>:` declared"
  else if (has line "Maybe<" || has line "Option<") && !has source "sum Maybe" && !has source "sum Option" then
    some "there is no Maybe builtin; declare `sum Maybe<T>:` with arms `none: {}` and `some: {value: T}`"
  else if !trimmed.startsWith "#" && bracketOutsideString line then
    some "there are no list literals; build a list as `Lists.List::<T>.cons({head: x, tail: rest})` ending in `Lists.List::<T>.nil()`"
  else if arrowArm trimmed then
    some "match arms are `case label(x): body` (`case _: body` for the rest); there is no `Pattern -> body`"
  else none

def firstHint (source : String) (lines : List String) : Option String :=
  lines.findSome? (lineHint source)

/-- The hint for a refusal naming `module` and `line` (1-based) among `modules`. -/
def hintFor (modules : List (String × String)) (module : Option String) (line : Option Nat) : Option String :=
  let named := module.bind fun m => modules.find? (·.1 == m)
  let atLine := named.bind fun (_, source) => line.bind fun n =>
    ((source.splitOn "\n")[n - 1]?).bind (lineHint source)
  atLine <|> (named.bind fun (_, source) => firstHint source (source.splitOn "\n")) <|>
    modules.reverse.findSome? fun (_, source) => firstHint source (source.splitOn "\n")

end Delvetalk.Hints
