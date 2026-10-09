# The Room Between

Two artists offer pieces; a curator arranges them; both artists approve that
particular arrangement before the room opens.

[Agreement.obend](Agreement.obend) is reusable ordinary Bend behavior. It owns
piece validation, participant rules, arrangement, approvals and the encounter.
[Exhibition.obend](Exhibition.obend) supplies the concrete object's methods, forms
and panels. Shared Abi and Encounter definitions arrive as explicit sealed
modules. The previous Python guard/write/menu generator and generated executable
JSON are removed.

An approval is a typed pending/approved variant. The approved payload carries the
actual arrangement revision. Opening checks both proofs against that revision;
old approval of different text/order cannot open a changed arrangement. The normal
object remains one-shot: contributions and arrangement cannot be overwritten, and
opening cannot repeat. Current law management and authorized reprogramming keep
their ordinary meaning; approval is neither a programming veto nor a grant.

The source declares offerNorth/offerSouth, arrange, consentNorth/consentSouth and
open. It validates nonempty title/note/caption, Nat display time 1–30, lighting
choice, role, once-only ordering and exact arrangement approval. Typed input
checking enforces Nat/Bool/String distinctions. Form upper string bounds live in
source presentation; raw invocation retains the host input bound. Piece notes
remain claims about the work, not certified physical properties.

The pure source view offers applicable actions and north/south note panels. It
has no actions after opening. Visible actions remain subject to the caller's
current grant and captured exact root.

[package.py](package.py) loads exact modules. An explicit participants configuration
can be supplied to the source `initial(participants)` constructor; the native
compiler checks/evaluates it and retains those arguments in the object's root.
Python authors no behavior or workflow here.

[exhibition.examples](exhibition.examples) records source-level success and
refusal cases: both artists' approvals, opening too early, impersonation, invalid
display time, attempted rearrangement and repeated opening. The separate physical
[runner](run.py) exercises ordinary source submission, queued native compilation,
current-granted adoption, portal forms, stale views, exact retries and continuation
export/replay on the `compiled` host. It submits the exact ordered module manifest,
not generated protocol-json behavior.

```sh
python3 protocols/shared-exhibition/run.py /PRIVATE/new-exhibition
python3 scripts/portal.py /PRIVATE/new-exhibition --allow-local-actions --principal north
python3 conformance/test_exhibition_journey.py
```

Use a fresh directory. `--content /PRIVATE/content.json` supplies north/south pieces
and caption/order as private fixture data. No network, publication or native build
runs. Tests additionally show that approval from a different arrangement cannot
open the room, that renewed approval does not bypass current law revocation, and
that two separately configured exhibitions reuse the same exact source table.
