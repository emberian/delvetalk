# Live DelveTalk: bootstrap design

Construction proposal, 2026-10-08; not a declaration that the rooms or game below
are deployed. The executable status remains in [TRACKING](../TRACKING.md).

Ember's [GSB status card](https://delve.town/profile/ember.delve.town/post/3mxen3fdeo224)
names `@livedelvetalk.delve.town` as an imaginary powerbox: a shared textual
address for play, scene proposals and requests. It is not an existing account
and must not depend on mention notifications. The [canon clarification](https://delve.town/profile/ember.delve.town/post/3mxeluynis22j)
sets a further objective: reconstruct the world from public PDS evidence.

## A place with a source desk

The first inhabited place should be a small Spween room. Participants see its
prose, available choices, current revision and exact source. They can play, open
the source desk, submit an extension, inspect its compilation and test results,
and adopt an authorized revision. A later choice executes that new behavior.

The first scene could be a repair café: two visitors repair a mechanical moth,
then add a branch teaching it a constellation. A shared thank-you slot gives
the existing one-shot and retry rules a useful role. The room can later contain
an Automatafl table and doors to participant-authored scenes.

This uses the existing parser, scene compiler, Lean host, proposals, transactions
and reprogramming. The missing connections are substantive:

- A public room view joins committed state with its matching immutable source
  artifact. Old displayed choices retain their original root; they cannot be
  silently reinterpreted against a new version.
- A bounded receiver discovers requests and reconciles receipts/publication
  after restart. The textual powerbox monitor is observation, not admission.
- A source desk retains source, syntax/compiler identities, candidate program,
  diagnostics and intended migration. Compilation returns an artifact; it
  never installs under the compiler service's authority.
- Lean distinguishes playing from programming and law management. The current
  single allowlist gives every admitted principal all three powers.
- Shared objects, participant sessions and remote transactions need a named
  profile. Current Spween sessions have shared variables and statically compiled
  membership tests; arbitrary effect calls only produce outbox intents.

Do not reuse Spween's playground runtime as the authoritative host: its choice
and render paths reconstruct runtime state, losing entry/visited history. A UI
should display committed host state. Scene migration also needs an explicit
passage-name mapping or session restart: copying old numeric passage indices
into reordered source can put participants somewhere else.

## A real two-player Automatafl table

Reuse the pinned Mini [two-player package](https://github.com/emberian/minidregg/tree/dcab86da8f6153ed2b522fc61c5064608694fd83/world/automatafl).
Do not introduce the unstable n-player variants or rewrite game decisions in a
Python transport. Qualify the actual lowered `play` term under the receiving
engine before committing to its runtime profile: the earlier demand-machine
budget and current substitution evaluator's budget are not comparable.

The recorded comparison has 353 cases, 343 agreements and 10 rule differences
against the Rust implementation. Resolve or explicitly name those differences
before advertising the table's rules. The initial receiving test must cover
board validity, a complete round, a conflict and a terminal win.

Public play needs simultaneous-choice secrecy. A proposed commit/reveal profile
binds commitments to match, code, round, conflict attempt, seat, move and a
high-entropy nonce; Lean verifies the commitment. Both commitments precede any
admitted reveal. A private-referee alternative needs actual private ingress and
read protection, which the current public profile does not have. Rules stay
pinned during a match; participants can agree to a new rules epoch for another
match. No automatic timeout winner is implied by this proposal.

## Programming from inside

The growth path is `inspect → propose → compile/check → adopt → use`, with every
result visible as a world artifact. Eventually scene libraries, syntax tools,
views and scheduling policies should be versioned, governed objects too. Each
can evolve without making a textual request an administrative capability.

The small trusted seed still defines evaluation, admission and artifact identity.
Changing that seed requires a named runtime epoch and explicit migration; a
description cannot silently change the machine interpreting it. Current local
reprogramming demonstrates program replacement, not a fully self-hosted compiler
or an endogenous authority system.

Public recovery needs a complete ordered admission history joining genesis,
requests, receipts, program/source artifacts and authoritative heads. Existing
published receipts and root pointers are ingredients; the current local database
is still the commit authority. A public replay index and publication recovery
contract are required before calling that database merely a cache. Multiobject
commits must have one public commit identity, not unrelated per-object updates.

## The eventual `wiki: DelveTalk: Bootstrap (v1)` card

Publish this when another participant can follow its instructions into a working
place. The card should contain:

1. The powerbox address, actual receiving cadence and how to retrieve a receipt.
2. One real room, its genesis/current head, and a complete first-choice example.
3. Exact runtime, syntax, source and authority profiles; distinguish implemented
   guarantees from the larger host contract.
4. The inspect/propose/adopt path and how to recover an uncertain attempt.
5. The pinned kernel description and executable conformance sources.

Use [rewrite-2k.txt](../capsules/rewrite-2k.txt) as the initial kernel description:
1,945 UTF-8 bytes. Its exact identity is in [the capsule manifest](../capsules/manifest.json).
It specifies dynamics and an object boundary; its own scope line excludes the
full typing, admission, messaging and encoding profiles. Pair it with the
explicit typed and host profiles rather than implying the blob alone boots the
whole world. The bootstrap card and the kernel may be separate linked posts,
so operational instructions need not be compressed out of existence.

The launch acceptance is experiential: another participant enters, acts, sees
a shared result, inspects the code, proposes a useful change, and uses the
adopted version. A third participant can reconstruct what happened from public
evidence after the receiving worker restarts.
