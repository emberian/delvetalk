# Propose a protocol

Fork the repository and add `protocols/<name>/protocol.json` plus
`scenarios.json`, following the existing examples and the
[local profile](protocols/README.md). Pull requests are the proposal mechanism;
merging a definition does not silently install it into existing worlds.

State the action, the identity that may perform it, what it reads, the effects
it proposes and the result it returns. Include a successful trace and a trace
that must refuse: stale root, competing use, changed request under an old id,
or current-law refusal. Keep external delivery claims separate from local
outbox claims. Give the human convention a title such as `DelveTalk: ...`;
the town's `Card:` family is used for capability cards.

Run `make check`. New scenarios in the protocol directory are discovered by
the host suite. Add core fixtures to `conformance/cases.json` when your protocol
needs a language behavior that is not covered; specify an expected observation
independently rather than accepting whichever implementation runs first.

The authoritative object stores its exact protocol definition and law. Any
future migration or live admission route needs an explicit policy; changing a
file in this repository cannot override a live object's law. Protocol prose,
core evaluator code and the local host profile must state their own scope.

For interpreter changes, preserve the tagged AST interface and the pinned
source relation. A disagreement is a counterexample to investigate, not a
reason to update all expected outputs. Include the smallest failing input.
Do not call resource exhaustion divergence or a missing reply failure.

The current profile is for trusted local experiments. Do not expose it as a
network authority service without adding real authentication, read controls,
resource accounting and a receiving-path review. Nobody needs to send live
welcomes to demonstrate the one-shot-slot rule.
