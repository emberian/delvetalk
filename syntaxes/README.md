# Emergent notation, explicit meaning

Reviewed, versioned adapters lower source into explicit artifacts. Unknown syntax
refuses. Translation never installs objects or dispatches effects.

```sh
python3 scripts/translate.py --syntax core-sexpr@1 syntaxes/examples/add.sexp -o /tmp/add.artifact.json
python3 scripts/translate.py --syntax protocol-markdown@1 syntaxes/examples/convention.md
```

## Built-in versions

| Syntax | Contract |
| --- | --- |
| `core-json@1` | One strict [core AST](../conformance/AST.md); duplicate JSON members and nonfinite numbers refuse. |
| `core-sexpr@1` | Parenthesized arrays; symbols are strings, `#t/#f` booleans, unsigned decimals indices; Nat payloads are quoted: `(nat "123")`. Semicolons start comments. |
| `protocol-json@1` | One local protocol object. |
| `protocol-markdown@1` | Exactly one closed `delvetalk-protocol` fence containing strict JSON; surrounding prose is opaque. |
| `spween-source@1` | Pinned parser's complete AST and source; no execution. |
| `spween-scene-i64@1` | Supported [scene profile](../scene/README.md), lowered to a bundle containing `protocol`; unsupported constructs refuse. |

Spween adapters require `cargo build --locked --manifest-path
scene/spween-bridge/Cargo.toml`. Their source pin identifies build inputs; the
recorded executable hash identifies the invoked binary. Neither proves the
binary was built from those inputs.

Core validation checks shape, not typing or progress. Protocol translation checks
outer shapes; Lean installation validates expressions and invocation checks
current authority. For execution, use `artifact.lowered` as the core job's `term`
or creation's `protocol`; scene bundles use `artifact.lowered.protocol`.

## Artifacts and pins

`delvetalk-lowered-v1` retains exact UTF-8 source, source/lowered hashes, syntax,
target and adapter pin. The host receives only the definition; retain the wrapper
separately. Use `scripts.translate.load_json` for exact decimals. Canonical JSON
is a repository profile, not RFC 8785.

Pins cover registry bytes and declared adapter/validator dependency closure.
They confer no authority, prove no closure completeness, and omit Python/runtime
dependencies. Use immutable sources and separately pinned toolchains when needed.

## Add an agent's dialect

Register reviewed `parse(source: str)` code, target validator and all transitive
local dependencies in [registry.json](registry.json). New meaning requires a new
version. `reviewed: true` is an operator declaration; adapters execute trusted
Python without sandboxing. Source cannot select imports or entrypoints.

[Adapters](adapters.py), [translator](../scripts/translate.py), and
[conformance](../conformance/test_syntax.py) specify extraction, canonicalization
and rejection. Run `make check` to build engines and exercise cross-engine
lowering. Adapters and artifacts are outside semantic capsule budgets.
