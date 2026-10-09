# Compiled source host

**`delvetalk-compiled` adds source packages, whole transitions and digests to shared admission.**
Select `world.exchange(...,profile='compiled')` or `scripts/world.py --profile
compiled`. One fixed 100,000-tick budget covers the request. Default hosts retain
10,000 ticks and reject these tags.

```json
["package",{"modules":[{"name":"Example","source":"edition ObjectiveBend 1\ndef run(x: Nat) -> Nat:\n  x\n"}],"entry":"run"},[["input","x"]]]
```

Descriptors require `modules` and `entry`; modules contain exactly `name,source`.
Imports name earlier supplied modules. Optional `limits` must equal
`{"ticks":"100000","heap":"100000","stack":"10000","typeFuel":"16384"}`;
packets, hashes and extra fields refuse. Installation checks every package,
including unused commands. Execution recompiles exact stored source, runs the edition's
shared-demand machine and materializes data. Package laws refuse; object law
remains authoritative.

Arguments/results support Nat, Bool, String and records to depth 64; arrays,
nulls, negative/fractional numbers, variants and effects refuse. Demand,
materialization and conversion consume the shared budget. Capacities: 100,000
heap cells/materialized nodes, 10,000 stack frames, 1,048,576 materialized bytes.
Parsing/checking/compilation use structural bounds outside demand ticks; this
is no complete CPU/memory tariff.

## Whole source transitions

An opt-in command contains only
`{"transition":{"profile":"delvetalk-source-transition-v1","package":SOURCE_DESCRIPTOR}}`.
Its entry receives `(state,input,{object,principal})` and returns exactly
`{accepted:Bool,reason:String,state:S,result:R}`. Identity comes from admission,
never input fields. One package execution eagerly materializes the entire decision
under the shared budget, including payloads of a refused decision.

Acceptance requires an empty reason and record-valued state, replacing the
**whole state** and advancing version once. False requires a nonempty reason;
`source refused: REASON`, malformed results or exhaustion retain one atomic
refusal. Transaction failure rolls back every call. This first profile emits no
outbox and cannot allocate or mix legacy command fields.

Installation checks source compilation; typed application and output shape are
checked at invocation. Neither establishes a persistent state invariant or an
installation-time transition ABI guarantee. Legacy commands and incidental
transition metadata remain unchanged. [Implementation](Compiled.lean),
[receiving tests](../conformance/test_source_transition.py).

## Digest expressions

| Expression | Result |
| --- | --- |
| `["object"]` | Actual receiving identity, including each transaction callee |
| `["sha256",expr]` | Canonical JSON SHA256; 64 lowercase hex characters |
| `["sha256-valid",expr]` | Digest shape only |

Hash data additionally permits arrays. Canonical JSON preserves array order,
sorts keys by Unicode scalar value, performs no Unicode normalization, retains
UTF-8, uses compact separators/canonical decimal naturals, and escapes controls
with JSON short escapes or lowercase `\u00xx`. Slash remains literal.
For supported values, Python agrees:

```python
hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')).hexdigest()
```

Hashing charges each node and UTF-8 byte; shape checks charge string bytes.
Protocols own domain separation, nonces and reveal rules. Digests confer no
authority. Source caching must preserve exact source/packet binding.

Build: `LEAN_NUM_THREADS=1 lake build delvetalk-compiled`.
Check: `python3 conformance/test_compiled.py`.
[Implementation](Compiled.lean); [tests](../conformance/test_compiled.py).
These local checks establish no deployment or compiler refinement.
