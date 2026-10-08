# Emergent notation, explicit meaning

Agents may invent arbitrary surface syntaxes and microprotocol notation. This
registry is an open boundary: a syntax becomes executable by adding a reviewed,
versioned adapter to a typed target. Agreement is about the lowered artifact,
not whether everyone writes the same characters. Unrecognized notation remains
readable source; translation refuses instead of guessing its meaning.

```sh
python3 scripts/translate.py --syntax core-sexpr@1 syntaxes/examples/add.sexp -o /tmp/add.artifact.json
python3 scripts/translate.py --syntax protocol-markdown@1 syntaxes/examples/convention.md
python3 conformance/test_syntax.py
```

The last command requires the four engines and Spween bridge to be built
(`make check` does this).
It lowers matching JSON/S-expression terms and executes the result in Lean,
Python, JS and C; it also checks Unicode, large naturals, malformed syntax and
ambiguous cards. An artifact's `lowered` field is the core term or local protocol
object. A core runner job is `{"name":"example","term": artifact.lowered}`;
a world creation request uses `protocol: artifact.lowered`. Translation itself
never installs an object, invokes a protocol or dispatches an effect.

## Built-in versions

* `core-json@1`: exactly one core AST JSON value, as described in
  [AST.md](../conformance/AST.md). Duplicate JSON object members, NaN and Infinity
  are rejected. Ordered field/arm pair arrays preserve duplicate labels.
* `core-sexpr@1`: the same nested arrays using parentheses. Bare symbols are
  strings; double-quoted strings use JSON escapes. `#t`/`#f` are Booleans;
  canonical unsigned decimal tokens are integers (for indices). Nat payloads
  must be quoted decimal strings: `(nat "123")`. Semicolon starts a line comment.
  Exactly one expression is required. Example: `(lam (bound 0))`.
* `protocol-json@1`: exactly one JSON protocol object in the local protocol schema.
* `protocol-markdown@1`: UTF-8 Markdown with exactly one fenced block whose info
  string is precisely `delvetalk-protocol`. Its body is strict JSON in the local
  [protocol schema](../protocols/README.md). Backtick or tilde fences of at least
  three characters and up to three leading spaces are recognized; closing
  fences use the same character and at least the opening length. Other fenced
  blocks and prose are opaque. Unclosed fences and multiple tagged blocks
  refuse. This is a deliberately explicit extraction grammar, not all of
  CommonMark and not an interpretation of prose.

* `spween-source@1`: a scene parsed by the real pinned Spween parser, retained as
  a full AST with exact source and upstream revision. This target is source-only;
  parsing does not execute effects, evaluate scene state or install a protocol.
  Build its fixed adapter with `cargo build --locked --manifest-path
  scene/spween-bridge/Cargo.toml`. Example:
  `python3 scripts/translate.py --syntax spween-source@1 syntaxes/examples/greeting.spw`.

* `spween-scene-i64@1`: parse with that same pinned parser and explicitly compile
  the supported scene subset using `scene/lower.py`. The target is
  `spween-protocol-bundle-v1`, retaining `source`, complete `ast`, `upstream`,
  `provenance`, named `spween-scene-i64-v1` profile and generated `protocol`.
  Hand `artifact.lowered.protocol` to the local host only after reviewing its
  proposed authority. Translation itself performs no scene effects. This adapter
  uses empty initial variables and `has` tables; the standalone compiler accepts
  explicit initial state. Unsupported constructs refuse instead of silently
  changing meaning; the source-only adapter can still retain their AST.

The Spween source pin includes the reviewed bridge module, Cargo manifest/lock,
upstream repository revision and syntax wrapper. Executable lowering additionally
pins `scene/lower.py`; its profile and compiler/source hashes remain in the
generated protocol provenance. The parse result separately
records SHA-256 of the actual executable invoked. A source manifest identifies
build inputs; it does not prove that an existing executable was built from them.
Build from the pinned sources and retain build evidence where that matters.
The Python/Rust toolchains and Cargo dependency bytes are not bundled; the lock
records dependency identities and registry checksums, with the git revision
pinning Spween. Arbitrary scene text never selects the executable or its flags.

The core target checks AST shape using the independent Python evaluator's
validator; it is untyped and can still be stuck. The protocol target checks only
profile and outer definition/command shapes. Lean installation validates actual
expressions and Lean invocation decides current authority and state transitions.
An accepted translation is not an accepted protocol or a proof of its safety.

## Artifacts and pins

`delvetalk-lowered-v1` retains the entire original UTF-8 source as `source.text`
and SHA-256 of its exact bytes, including CRLF and all surrounding prose.
Re-encoding this string as UTF-8 reproduces the source bytes. It records syntax
ID/version, target, lowered value and lowered SHA-256. Canonical JSON here means
Python JSON with sorted object keys, no extra whitespace, unescaped Unicode,
finite exact decimal numbers and UTF-8; it is a repository profile, not RFC 8785.
Decimals retain their exact values; artifact consumers must use a lossless JSON
reader (`scripts.translate.load_json` in Python), not binary floating point.
The translator refuses Python floats instead of silently rounding them. All core
natural values are strings, avoiding floating-point loss. Retain this artifact
alongside an admitted object/receipt when source provenance is needed; the host
currently receives only the lowered definition and does not persist this wrapper.

`translation.pin` hashes a canonical manifest containing the syntax selection,
exact adapter and validator entries, SHA-256 of the registry bytes and SHA-256
of each declared repository dependency, including the translator. The registry
does not contain its own hash, so there is no self-hash cycle. Changing a
validator or the registry changes the pin, even when source notation is unchanged.
Pins identify bytes; neither a source hash nor an adapter pin confers authority.

The included closure lists every repository module used by these adapters and
validators. It does not pin Python or the standard library. A custom adapter
must declare every local transitive dependency in `closure`; a single entry-file
hash is insufficient. For stronger reproducibility, pin its runtime/dependency
lock or image separately and use an immutable checkout during translation.
The translator does not prove dependency-closure completeness or sandbox Python.

## Add an agent's dialect

Add reviewed parser code as a repository module, export `parse(source: str)`
returning a JSON value, and register a new immutable ID/version with `reviewed:
true`, its module path, entrypoint and target. Include all transitive repository
modules in the registry-wide or selected adapter/target `closure`. The local operator's code review is the trust boundary:
`reviewed: true` is a declaration, not a signature or evidence of review. Registry
code runs as trusted local Python; do not register arbitrary downloaded parsers
without reviewing them. Source cannot supply an import path or entrypoint, and
embedded source is never evaluated as Python or shell code.

Targets are also extensible: register a target validator with an explicit
module/entrypoint and closure. Define the corresponding receiver semantics and
conformance suite before claiming interoperability. To change a dialect's meaning,
allocate a new version; retain older adapters for historical source. Keep examples
that distinguish interpretations, rejection cases and two notations lowering to
the same target. An LLM may propose an adapter or interpretation, but there is no
natural-language fallback in the execution path.

Adapter code, registry, source artifacts and this document are **outside** the
1/2/3/6/16 KB semantic capsule budgets. The capsules describe the machine; this
package supplies a growing vocabulary for writing programs and proposals for it.
