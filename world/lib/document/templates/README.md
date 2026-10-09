# Pure document templates

A template is an ordinary Bend function returning `Document.Document`. Import
the shared document module explicitly as `Document`, then write:

```text
def welcome(name: String, offer: Document.Document) -> Document.Document:
  doc"""Hello, {{ name }}.
{% offer %}
"""
```

`{{ expression }}` inserts a **String** as a text node. `{% expression %}`
inserts a **Document** fragment. The native frontend lowers both to ordinary
calls to the selected `Document.text`, `Document.concat` and `Document.empty`
definitions. The regular source checker checks those calls. A string containing
template markers, HTML, or an offer-shaped JSON value remains text; it cannot
create a typed offer. Use `natText` for decimal interpolation.

Literal spaces, newlines, tabs, quotes and Unicode are retained, including the
newline immediately after an opening delimiter or before a closing one. There
is no automatic indentation stripping or Unicode normalization. Escape only
literal delimiters: `\{{`, `\{%`, `\"""`, and `\\`. Other backslashes remain
literal. Holes accept ordinary single-line Bend expressions, including nested
records, calls, closures, locals and conditionals. Put larger computations in
named functions; include their returned fragment with `{% partial(context) %}`.

[Phrasebook.obend](Phrasebook.obend) demonstrates the composition tools:

- `each` takes a rendering function and iterates over a dynamic bounded count.
- `Sections` gives names to function-valued slots. `Base` renders through its
  `self` slots, and `Workshop` specializes them with actual `self`/`super`
  extensions. Inherited bodies see specialized slots; `super` retains inherited
  behavior.
- `withHeading` accepts a fragment and returns another template. Ordinary
  imports select reusable partials and retain their exact source revisions.
- `sourcePrompt` combines instructions, an explicit data quotation, and a typed
  captured offer. It makes no network call and invokes no model.
- Ordinary `if`, `let`, `match`, recursive sums, closures and function arguments
  supply control flow. There is no separate template scope or ambient world.

The context must be explicit, already authorized data. Rendering a copied
capture creates presentation, not permission to act. Receiving admission and
retained capture roots remain the authority boundary. `Document.plain` is only
a text projection; keep the structured value for interactive renderers.

The hosted compiler extension is
[`DocumentTemplate.lean`](../../../../spec/Delvetalk/DocumentTemplate.lean), with
a narrow reversible parser hook recorded in `spec/upstream.json`. Original
source is retained in compiled packages; diagnostics and import spans map back
to original byte offsets. Conformance lives in
[`test_document_templates.py`](../../../../conformance/test_document_templates.py).
`{"op":"template-expand","source":"..."}` on `delvetalk-obend` returns the
ordinary source expansion for inspection. It is not a checked or admitted
artifact; pass the source through the normal compiler.

Native source checking and execution establish template behavior; these tests
do not claim receiving deployment or renderer HTML escaping.
