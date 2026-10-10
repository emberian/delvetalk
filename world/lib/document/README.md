# Structured documents

`Document.obend` is what every card's `render` returns (docs/FOUNDATION.md section 5): a
text, or a sequence of documents. `plain` is its text, `lines` its lines and `size` its
length in characters; the host renders a Document byte for byte as `plain` does.
Templates (`templates/`) are the `doc"""…"""` syntax over its `text`, `concat` and `empty`.
