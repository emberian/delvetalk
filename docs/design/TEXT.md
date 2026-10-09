# Hosted text

The DelveTalk Objective Bend edition provides checked source builtins. Local or imported definitions may shadow these names.

| Source | Type | Meaning |
| --- | --- | --- |
| `textConcat(a,b)` | `(String,String) → String` | Exact concatenation |
| `natText(n)` | `Nat → String` | Canonical unsigned decimal; zero is `"0"` |
| `sha256Text(s)` | `String → String` | Lowercase SHA-256 of exact UTF-8 bytes |
| `textLength(s)` | `String → Nat` | Unicode scalar count |
| `textSlice(s,start,count)` | `(String,Nat,Nat) → String` | Drop `start` scalars, take at most `count` |
| `textTake(s,count)` / `textDrop(s,count)` | `(String,Nat) → String` | Take or drop a scalar prefix |
| `textSpan(s,alphabet)` | `(String,String) → Nat` | Length of the longest prefix containing only scalars in `alphabet` |
| `textBreak(s,alphabet)` | `(String,String) → Nat` | Length of the prefix before the first scalar in `alphabet` |

Indices start at zero. Bounds clamp; an exhausted slice is empty. No operation
normalizes text. Combining marks count separately; a slice may split a grapheme.
The source compiler lowers slicing to checked `textDrop` followed by `textTake`.
Take and drop are also directly available source operations with distinct String/Nat input types. Numeric
rendering and length are genuine unary terms. Wrong types are checker refusals.
Arguments are demanded only when their result is demanded.

**Resources.** Hosted package execution admits work and a conservative allocation
bound before entering each primitive. Let `B` be input UTF-8 bytes (both inputs for
concatenation), `Q = min(B, 4n)` for a prefix of `n` scalars, and
`K = log₂(n)+1`, with `K=1` at zero. For scans, `A` is alphabet UTF-8
bytes and `V` is the number of scalar positions examined, including a stopping
nonmatch.

| Primitive | Charged ticks | Required allocation allowance |
| --- | --- | --- |
| Concatenate | `1 + 2B` | `B` bytes |
| Take | `1 + 2Q` | `Q` bytes |
| Drop | `1 + B + Q` | `B` bytes |
| Span / break | `1 + 2(A + 2)V` | zero new text bytes |
| Length | `1 + B` | zero new text bytes |
| Decimal | `1 + K²` | `K` bytes |
| SHA-256 text | `65 + 8⌈B/64⌉ + 32⌈(B+9)/64⌉` | `64⌈(B+9)/64⌉ + 4096` bytes |

Take/drop use UTF-8 slices rather than allocating a list for the whole input.
When `n = 0` or `n ≥ B`, their implementation returns an existing string or the
empty string immediately, charging one tick and zero new text allocation.
Other drops still account for both prefix traversal and suffix copying; their
cost is not merely proportional to the dropped prefix.

Span/break walk an iterator without making a character list. A bounded preflight
counts the examined prefix; the tariff pays for both preflight and evaluation,
including a conservative full-alphabet membership walk at each scalar. The
preflight itself stops at a cap derived from the available ticks. Exhausting that
cap consumes the remaining work allowance and refuses, rather than returning
spent work as unused credit. A short prefix does not charge for an untouched
long suffix. These bounds can still refuse operations whose final output fits.
Slice pays for both component operations; decimal accounts for conversion work,
not just its result.
The allocation allowance is the remaining extraction-byte budget, not a fresh
per-field limit. Work shares the existing whole-execution tick allowance across
all demanded fields. Insufficient work suspends before the primitive; insufficient
allocation suspends for capacity. Neither produces a partial successful result.
Final data encoding still consumes the normal extraction node/byte budgets.

SHA-256 prepays input copying/padding, every compression block and hex output.
Its workspace reserve covers padded input and bounded schedule/state/hex
temporaries; its final64-byte text still pays ordinary extraction. UTF-8 bytes
set these costs, including multi-byte scalars. Domain separation, field framing
and commitment policy belong to authored source; the primitive adds none.
The block tariff follows [program-digest calibration](PROGRAM-DIGEST.md).

**Boundary.** Text operations belong to the local DelveTalk semantics fork.
[Mini origin](../../spec/bend/origin.json) records its upstream baseline without
constraining local semantic edits. The reference syntax, typing derivations, demand machine and
source-wire theorem include the extension. The original unit-cost forcing
function and its fast-equivalence proof remain; hosted extraction selects the
separately named text-aware force. Other core operations keep unit cost.
Independent Python/C/JS evaluators still cover their shared fragment, not these extensions.

[Text gallery](../../syntaxes/examples/text-gallery.obend) authors changing room
prose and a Unicode caption limit. [Tests](../../conformance/test_text_primitives.py)
exercise actual source compilation, Unicode boundaries, type errors, name
shadowing, laziness and shared work/capacity refusal.

The source [interpretation library](../../protocols/interpretation/Interpretation.obend)
uses these scans for literal routing and ASCII child-key validation. Its
[boundary tests](../../conformance/test_text_boundaries.py) execute 4096-byte
utterances, long literal tokens, Unicode, and valid/invalid 64-scalar keys under
the ordinary 100,000-unit package allowance, including actual native receiving.
