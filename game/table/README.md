# A shared two-player Automatafl table

An ordinary `compiled` protocol implements two seats and commit/reveal. Lean
checks admission and executes the qualified [game package](../automatafl/README.md).

## Make a table

From the repository root:

```sh
make build
python3 game/table/protocol.py --table table:cafe --seat0 alice --seat1 bob \
  --principal host --intent create > /tmp/table-create.json
python3 scripts/world.py --profile compiled /tmp/table-world.json /tmp/table-create.json
python3 conformance/test_game_table.py
```

Use a fresh database. The initial 5×5 board places an attractor at 0, repulsor
at 4 and automaton at 12, with row-major indices. Each seat receives its own commit/reveal commands; either
can resolve. Nobody receives management rights. Inspection is public. Local
principal strings do not authenticate DID control.

## Commit, then reveal

```sh
python3 game/table/client.py prepare --table table:cafe --round 0 --seat 0 \
  --source 0 --target 5 --private /tmp/alice-round0.private.json
```

The helper prints `{round,digest}` and durably creates a new mode-0600 reveal
file with a random 256-bit nonce. Keep it private until both commitments exist.
Even a refused reveal exposes plaintext in retained request history.

Invoke `commit0/commit1` with `{round,digest}`, `reveal0/reveal1` with
`{round,source,target,nonce}`, and `resolve` with `{round}`. Each request needs
current whole `expected` root, authorized principal and intent. Exact retry
recovers the receipt; stale refusal requires a new root and intent.

## Commitment bytes

SHA-256 hashes canonical UTF-8 JSON:

```text
["delvetalk.automatafl.commit.v1",tableId,round,seat,source,target,nonce]
```

The receiver supplies `tableId`; nonce is 64 lowercase hex characters. Shape
checks cannot prove entropy. Both commitments precede either opening.
[Protocol](protocol.py) and [client](client.py) specify encoding and guards.

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
