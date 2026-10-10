# Pure document templates

A template is an ordinary Bend function returning a document. Import the shared
module explicitly; `Document`, `D`, or any other alias works:

```text
import ./Document.obend as Document
def welcome(name: String, offer: Document.Document) -> Document.Document:
  doc"""Hello, {{ name }}.
{% offer %}
"""
```

`{{ expression }}` inserts a **String** as a text node. `{% expression %}`
inserts a **Document** fragment. The native frontend lowers both to ordinary
calls to the selected module's `text`, `concat` and `empty` definitions. Generated
calls use a fresh import alias absent from the original source, so parameters,
locals and closure arguments cannot shadow them. The generated import points to
the same explicitly selected module and source hash. No library is supplied
implicitly; an absent import produces a template-specific diagnostic.

The regular source checker checks those calls. A string containing template markers
or HTML remains text. Use `natText` for decimal interpolation.

Literal spaces, newlines, tabs, quotes and Unicode are retained, including the
newline immediately after an opening delimiter or before a closing one. There
is no automatic indentation stripping or Unicode normalization. Escape only
literal delimiters: `\{{`, `\{%`, `\"""`, and `\\`. Other backslashes remain
literal. Holes accept ordinary single-line Bend expressions, including nested
records, calls, closures, locals and conditionals. Put larger computations in
named functions; include their returned fragment with `{% partial(context) %}`.

Ordinary `if`, `let`, `match`, recursive sums, closures and function arguments supply
control flow. There is no separate template scope or ambient world.

The context must be explicit, already authorized data: rendering creates presentation,
not permission to act.

The hosted compiler extension is
[`DocumentTemplate.lean`](../../../../spec/Delvetalk/DocumentTemplate.lean), with
[`FrontEnd.lean`](../../../../spec/Delvetalk/FrontEnd.lean) binding its dependency
and calling the locally maintained core parser and checker. Original source is retained
in compiled packages; diagnostics and import spans map back to original byte
offsets. Historical origin attribution lives in
[`spec/bend/origin.json`](../../../../spec/bend/origin.json); current behavior lives
in the local compiler source.
`{"op":"template-expand","source":"..."}` on `delvetalk-obend` returns the
ordinary source expansion for inspection. It is not a checked or admitted
artifact; pass the source through the normal compiler. The displayed expansion
includes the fresh import so it also compiles as ordinary Bend source.
