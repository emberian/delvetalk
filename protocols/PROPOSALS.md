# Proposals are runnable, source-bound evidence

An agent can invent a protocol, write it in a registered notation, and package
its examples as an independently rerunnable proposal. The workflow retains the
exact source and pins the translation and tested host. It never installs a live
object, changes a live world, or grants authority. A passing report establishes
only its listed observations in the local fixture profile.

Build the host (`lake build delvetalk-world`) and run:

```sh
python3 scripts/propose.py --syntax protocol-json@1 \
  protocols/counter/protocol.json protocols/counter/scenarios.json \
  -o /tmp/counter-proposal.json

python3 scripts/propose.py --syntax protocol-markdown@1 \
  syntaxes/examples/convention.md protocols/examples/greeting-scenarios.json

python3 conformance/test_propose.py
```

The Markdown example pairs the greeting card with separate cases for success,
a stale root, a second greeting and an unauthorized principal. For an agent's
new dialect, first add a reviewed,
versioned adapter following [the syntax registry](../syntaxes/README.md). Proposal
source cannot choose Python imports, supply subprocess commands, install an
adapter, or activate a natural-language interpretation fallback. The CLI accepts
adapters targeting `local-protocol-v1` and the explicitly supported
`spween-protocol-bundle-v1`. For a Spween executable bundle it selects the
`protocol` field while retaining the entire source/AST/profile bundle in the
candidate identity. A parse-only `spween-source-v1` artifact refuses execution.
Both paths use the same translator and Lean host as ordinary local objects.
Spween translation also requires the pinned bridge built with
`cargo build --locked --manifest-path scene/spween-bridge/Cargo.toml`; the proposal
conformance suite exercises a real scene through this path.

Each scenario gets a fresh temporary database, a fixed object identity
`candidate`, and its own declared law. Lean validates installation and decides
every transition. Temporary state is removed afterward. The command takes no
live database path, and `-o` refuses any existing file or symlink, including a
source, prior report or live world. No outbox intent is delivered. This is state
isolation, **not an operating-system security sandbox**: the local host's resource
and trust limitations still apply. Registered adapter code is trusted executable
repository code, not sandboxed proposal text.

## Scenario contract

The separate scenarios file is a strict JSON array with 1–64 entries and at most
256 total steps. A scenario has exactly `name`, `law`, and nonempty `steps`.
Names must be unique nonempty strings; they are labels, never filesystem paths.
`law` is an array of principal strings and may be empty. Principal strings are
local fixture assertions, not authenticated identities.

Each step has exactly these required fields:

* `principal`, `command`: nonempty strings;
* `input`: a JSON object;
* `root`: exactly `initial` or `current`;
* `kind`: expected `committed` or `refused`.

Optional `state`, `result` and `outbox` assert exact complete values on a committed
receipt. `state` must be an object and `outbox` an array. Optional `error` asserts
an exact refusal string. Unknown fields, duplicate JSON members, nonfinite
numbers, ambiguous cards and unknown adapters refuse before execution. Decimal
values retain their exact decimal representation through parsing and transport.
A wrong expectation produces a failed report, not an altered interpretation.
Installation refusal likewise produces a failed report and skips that scenario's
steps. An infrastructure or malformed-input error produces no report.

Steps receive distinct deterministic intent IDs; `initial` deliberately permits
stale-root tests after another step commits. This format does not express receipt
replay, competing processes or law revisions; the shared world conformance suite
covers those host behaviors. Add a success case and adversarial cases for stale
roots, unauthorized principals and repeated semantic actions as appropriate.
The runner does not claim test completeness from a count or a green result.

## Identities and reproducibility

The report embeds a `delvetalk-proposal-v1` candidate containing:

* the complete `delvetalk-lowered-v1` artifact, including exact source bytes
  recoverable as UTF-8, source hash, syntax/adapter/validator pin, lowered protocol
  and lowered hash;
* the exact scenarios source, its byte hash, parsed cases and their canonical hash;
* `host`, identifying the selected protocol path (`lowered` or `lowered.protocol`)
  and its exact canonical hash;
* `candidate.id`, SHA-256 of canonical candidate JSON before the `id` field exists.

`execution` records the profile, Python version, and exact hashes of the proposal
runner, world transport, Lean host source, core source, upstream relation/pin,
Lean toolchain and executable used. The executable must already be built; proposal
checking does not launch a compiler. Host/runner hashes are checked again after
execution, and a detected change refuses the run. The report contains complete
installation and invocation receipts and assertion failures. `report.id` hashes
the complete report before its `id` field exists. There are no timestamps or
temporary paths; identical source, translation closure, cases, execution bytes
and observations produce identical reports.

Use `scripts/translate.py`'s exported `load_json` and `canonical` helpers when
reading or hashing these artifacts. Ordinary binary-float JSON loaders can round
a decimal preimage. Canonicalization is this repository's sorted-key exact-decimal
JSON profile, not RFC 8785. SHA-256 identifies bytes; it is not a signature,
authorization decision or proof. The executable/source hashes do not prove that
the binary was built from those sources. Python/OS dependencies are not fully
hermetic, and the host can execute programs with unbounded arithmetic costs
inside its reduction budget. Run in an immutable reviewed checkout for stronger
reproducibility. The before/after hash check is not a defense against malicious
concurrent repository mutation.

Exit status is `0` for all listed assertions passing, `1` for a completed report
with failures, and `2` for invalid input, infrastructure errors, or a refused
output destination. A report may be shared as a proposal, then independently
regenerated by a reviewer. Admission into a real world is a separate receiving
operation under that world's current authority; this command deliberately has
no promotion or installation switch.
