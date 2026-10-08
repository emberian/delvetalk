# Spween parser and runtime oracle

The bridge uses the actual MIT-licensed [Spween source](https://github.com/spwplace/spween/tree/95980f7d1e109138496849a444f28c4b9076a4e2), pinned at commit `95980f7d1e109138496849a444f28c4b9076a4e2`. `scene/spween-bridge/Cargo.toml` pins the Git revision; its committed `Cargo.lock` pins Rust dependencies and registry checksums. No local `/Users/...` dependency or copied parser is used. The AST serializers and replay handler are DelveTalk code. Upstream retains its MIT license; this bridge is AGPL-3.0-or-later.

Build and test from the repository root (Rust supporting edition 2024):

```sh
CARGO_BUILD_JOBS=2 cargo build --locked --manifest-path scene/spween-bridge/Cargo.toml
CARGO_BUILD_JOBS=2 cargo test --locked --manifest-path scene/spween-bridge/Cargo.toml
```

The executable is `scene/spween-bridge/target/debug/delvetalk-spween`. It reads one request per JSON line and writes one response per line. The bridge performs no network calls, subprocess execution, filesystem effects, or dynamic code loading during requests. Dependency retrieval occurs at Cargo build time.

## Parsing

Request: `{"op":"parse","source":"...","filename":"example.scene"}`. `filename` is optional and used only as a parser argument. Success: `{"ok":true,"upstream":"95980...","source":"...","ast":...}`. The source string is retained exactly; AST prose is upstream's token-normalized prose, not an exact lexical reconstruction. Whitespace, comments, and frontmatter constructs omitted by the upstream AST remain in the retained source.

All spans are upstream UTF-8 byte ranges `[start,end]`. The bridge exports every field and variant of the pinned upstream AST:

- Scene: `{meta,passages,span}`.
- Metadata: `{id,title,tags,weight,cooldown,requires,custom,span}`; custom is an ordered array of `[key,taggedValue]` pairs, including upstream normalization of YAML values.
- Passage: `{name,content,span}`.
- Content: `{kind:"prose",text,span}`, `{kind:"effect",effect}`, or `{kind:"choice",text,condition,effects,target,span}`.
- Target: null or `{target,is_end,span}`.
- Condition: null or `{expr,span}`. Expressions: `["atom",clause]`, `["and",left,right]`, `["or",left,right]`.
- Clause: `{kind:"has",category,key,span}`, `{kind:"compare",var,op,value,span}`, or `{kind:"not",clause}`. Operators: `ge`, `le`, `gt`, `lt`, `eq`, `ne`.
- Effect: `{kind:"set",var,value,span}`, `{kind:"modify",var,delta,span}`, or `{kind:"call",name,args,span}`. Delta is a canonical signed decimal string.

Values have unambiguous tags: `["null"]`, `["bool",true]`, `["int","-42"]`, `["float","3ff0000000000000"]`, `["string","text"]`. Integers cover exactly signed i64. Float payloads are exactly 16 lowercase hex digits of IEEE-754 binary64 bits, preserving negative zero and nonfinite values without lossy JSON numbers. Float preservation does not imply that a downstream executable lowering accepts floats.

## Runtime oracle

Request: `{"op":"replay","source":"...","state":{"vars":{"gold":["int","10"]},"has":{"inventory":["key"]}},"actions":[{"choose":0},{"jump":"intro"}]}`. `state` and `actions` default empty; actions require exactly one of `choose` (unsigned index) or `jump` (passage name). Unknown bridge fields are rejected. The host handler supplies variables and membership, records `call` requests in order, always succeeds at calls, and gives them no state mutations. This is an explicit handler profile, not every possible Spween embedding.

Success contains `trace`: an initial `{action:null,ok:true,snapshot}` followed by `{action,ok,error,snapshot}` for each requested action. An upstream runtime error sets that entry's `ok:false`; the oracle captures the resulting state and continues with later actions. Snapshot fields:

- `state`: `{kind:"running",index,passage}` or `{kind:"ended"}`.
- `vars`: tagged values; `has`: membership map; `calls`: cumulative ordered `{name,args}` array.
- `prose`, `requirements`, and `choices:[{index,text,available}]` from the actual runtime.

The initial snapshot is **after** initial passage effects. The runtime reports scene requirements but does not gate startup on them. Passage entry effects run once per passage for the lifetime of that runtime, including after leaving and returning. Choice indices count choices only, not prose or effects. Missing variables read as Null. Bool/Int equality includes true=1 and false=0; numeric comparisons and float epsilon equality follow the actual upstream code. Non-numeric modification preserves the existing value.

The upstream runtime is not transactional: a choice effect can mutate variables before an unknown-target error. The oracle exposes that partial state. A DelveTalk profile that atomically refuses an invalid transition must declare this difference, not claim total runtime equivalence.

## Error and capacity scope

Parse failures return `{ok:false,stage:"parse",error,span,upstream}`. Bridge request failures use `stage:"bridge"`. Ordinary Rust panics from upstream use `stage:"upstream-panic"` and report no semantic result. Both debug and release use overflow checks; signed arithmetic overflow therefore fails instead of silently choosing wraparound semantics. A panic result discards the request's runtime; it does not claim rollback inside Spween.

Requests above 2 MiB are refused after reading the line; this is a local workbench process, not a hardened public parser service. Stack exhaustion and process/resource failure remain possible on adversarial upstream input and cannot be caught as ordinary Rust panics. Callers should impose process deadlines and size limits. Duplicate JSON object members follow serde_json's last-member behavior and are outside the strict interchange profile. No proof of parser completeness, AST round-trip identity, lowering correctness, or arbitrary runtime equivalence is asserted by these tests.
