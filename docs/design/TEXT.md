# Hosted text

DelveTalk extends the pinned Objective Bend edition with four checked source
builtins. Local or imported definitions may shadow these names.

| Source | Type | Meaning |
| --- | --- | --- |
| `textConcat(a,b)` | `(String,String) → String` | Exact concatenation |
| `natText(n)` | `Nat → String` | Canonical unsigned decimal; zero is `"0"` |
| `textLength(s)` | `String → Nat` | Unicode scalar count |
| `textSlice(s,start,count)` | `(String,Nat,Nat) → String` | Drop `start` scalars, take at most `count` |

Indices start at zero. Bounds clamp; an exhausted slice is empty. No operation
normalizes text. Combining marks count separately; a slice may split a grapheme.
The source compiler lowers slicing to checked `textDrop` followed by `textTake`.
These internal binary primitives have distinct String/Nat input types. Numeric
rendering and length are genuine unary terms. Wrong types are checker refusals.
Arguments are demanded only when their result is demanded.

**Resources.** Hosted package execution admits work and a conservative allocation
bound before entering each primitive. Let `B` be input UTF-8 bytes (both inputs for
concatenation), and `K = log₂(n)+1`, with `K=1` at zero.

| Primitive | Charged ticks | Required allocation allowance |
| --- | --- | --- |
| Concatenate | `1 + 2B` | `B` bytes |
| Take / drop | `1 + 2B` | input byte count |
| Length | `1 + B` | zero new text bytes |
| Decimal | `1 + K²` | `K` bytes |

These conservative bounds can refuse an operation whose final output would fit.
Slice pays for both traversals; decimal accounts for conversion work, not just
its result. Scratch scalar lists are bounded linearly by admitted input bytes.
The allocation allowance is the remaining extraction-byte budget, not a fresh
per-field limit. Work shares the existing whole-execution tick allowance across
all demanded fields. Insufficient work suspends before the primitive; insufficient
allocation suspends for capacity. Neither produces a partial successful result.
Final data encoding still consumes the normal extraction node/byte budgets.

**Boundary.** This is an explicit hosted extension, not an upstream semantic
update. `spec/upstream.json` retains the original commit and hashes and records
reversible edits. The reference syntax, typing derivations, demand machine and
source-wire theorem include the extension. The original unit-cost forcing
function and its fast-equivalence proof remain; hosted extraction selects the
separately named text-aware force. Historical operations keep unit cost.
Independent Python/C/JS evaluators still cover the pinned fragment only.

[Text gallery](../../syntaxes/examples/text-gallery.obend) authors changing room
prose and a Unicode caption limit. [Tests](../../conformance/test_text_primitives.py)
exercise actual source compilation, Unicode boundaries, type errors, name
shadowing, laziness and shared work/capacity refusal.
