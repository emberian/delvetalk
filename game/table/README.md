# A shared two-player Automatafl table

An ordinary [CommitRevealTable](CommitRevealTable.obend) source object owns two
seats, commitment framing, commit/reveal/reset, seat checks, grants and encounters.
Lean admits its source transitions under current law and executes the qualified
[game package](../automatafl/README.md). Python only loads exact modules and typed
configuration, retains private openings, and transports requests.

## Make a table

From the repository root:

```sh
make build
python3 game/table/protocol.py --table table:cafe --seat0 alice --seat1 bob \
  --principal host --intent create > /tmp/table-create.json
python3 scripts/world.py --profile compiled /tmp/table-world.json /tmp/table-create.json
python3 conformance/test_game_table.py
```

Use a fresh database. Every new table uses the [original 11×11 opening](../automatafl/original-opening.json):
12 attractors, 24 repulsors and the automaton at F6 (index 60). Indices are
row-major: A1=0, K1=10, A2=11, K11=120; rows increase downward. No alternate
board or rules parameter is offered. Each seat receives its own commit/reveal commands; either
can resolve. Nobody receives management rights. Inspection is public. Local
principal strings do not authenticate DID control.

## Commit, then reveal

```sh
python3 game/table/client.py prepare --table table:cafe --round 0 --seat 0 \
  --source 104 --target 71 --private /tmp/alice-round0.private.json
```

The helper prints `{round,digest}` and durably creates a new mode-0600 reveal
file with a random 256-bit nonce. Keep it private until both commitments exist.
Even a refused reveal exposes plaintext in retained request history.

Invoke `commit0/commit1` with `{round,digest}`, `reveal0/reveal1` with
`{round,source,target,nonce}`, and `resolve` with `{round}`. Each request needs
current whole `expected` root, authorized principal and intent. Exact retry
recovers the receipt; stale refusal requires a new root and intent.

## Commitment bytes

The source `commitment` export computes SHA-256 over exact UTF-8 text. Its seven
fields are `delvetalk.automatafl.commit.v2`, table identity, round, seat, source,
target and nonce. Each field is framed as its decimal Unicode-scalar length,
then `:`, then its text; numbers use canonical decimal. Concatenate the seven
frames without separators. This is unambiguous even when identities contain
colons, controls or non-ASCII text. The private helper calls that same source
export; it does not implement a second framing or digest rule.

The v2 commitment format replaces the prelaunch v1 JSON-array framing. Existing
retained requests and historical receipts are never rewritten or reinterpreted;
new tables and new custody use the source-owned format.

The receiver supplies `tableId`; nonce is 64 lowercase hex characters. Shape
checks cannot prove entropy. Both commitments precede either opening.
[CommitRevealTable](CommitRevealTable.obend) specifies encoding and guards.
[Protocol loading](protocol.py) and [private custody](client.py) contain no
executable command generator.

## Resolve and retry

Resolution atomically stores the game result, advances the round and clears slots.
Conflict/invalid pairs also advance; winners block further commitments. Wrong
openings refuse. A player can withhold forever: no deadline, forced reveal,
resignation, wager, seat reassignment or external delivery exists.

## Game qualification

[Tests](../../conformance/test_game_table.py) exercise complete rounds and hostile
requests. The transition matches 353 stored Bend outputs; ten disagree with the
historical Rust oracle. Qualification is scoped to this two-player profile.

[Participant cards](PARTICIPANT.md) supply typed move selection and private opening/retry custody.

The [ten-round original-board match](../automatafl/original-opening-qualification.json)
agrees cell-for-cell with the original Rust rule core using its documented adapter.
Smaller boards in conformance tests are isolated algorithm fixtures, not game variants.
