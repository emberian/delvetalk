# A shared two-player Automatafl table

This userspace protocol uses the ordinary compiled host profile, current scoped
law, exact read roots and retained receipts. The game transition runs the actual
Objective Bend package through Mini's compiler/checker/demand engine in Lean.
There is no table/game case in host admission, and no Python game evaluator.
Only two seats exist. No n-player variants are imported.

`protocol.py` fills a declarative JSON protocol template. `client.py` prepares
opaque commitments and renders public board data. `conformance/test_game_table.py`
plays complete admitted rounds and attempts to violate the protocol. Build the
compiled profile using the repository's build instructions, then run:

```sh
python3 conformance/test_game_table.py
```

## Make a table

```sh
python3 game/table/protocol.py \
  --table table:repair-cafe --seat0 did:plc:alice --seat1 did:plc:bob \
  --principal did:plc:host --intent create-cafe-table > /tmp/table-create.json
python3 scripts/world.py --profile compiled /tmp/table-world.json /tmp/table-create.json
```

The initial 5×5 board is the existing qualified `independent` fixture: attractor
at index 0, repulsor at 4, automaton at 12. Indexing is row-major; player 0 wins
at the upper corners, player 1 at the lower corners. The helper only packs this
explicit board data. This version does not select random boards or negotiate
seat occupancy. Each creator chooses two explicit seat DID grants. These local
principal strings are not, by themselves, authenticated DID control.

The initial law grants seat 0 `commit0/reveal0`, seat 1 `commit1/reveal1`, and
both seats `resolve`. It grants nobody `law` or `reprogram`. There is no owner
bypass. Inspection is public in this host profile.

## Commit, then reveal

Prepare a move locally without putting it in a public request:

```sh
python3 game/table/client.py prepare --table table:repair-cafe \
  --round 0 --seat 0 --source 0 --target 5 --private /tmp/alice-round0.private.json
```

The helper creates a new mode-0600 file containing the reveal payload, generates
a 256-bit nonce with the OS random source, fsyncs the file and directory, and prints only
`{"round":0,"digest":"..."}`. Keep the private file until the round's outcome
is known. The helper refuses to overwrite an existing private file. The nonce
must remain private until reveal; preserving it across a lost reply is the
player's custody obligation.

An ordinary invocation has `op: "invoke"`, the table object ID, the seat DID as
`principal`, a fresh `intent`, a complete current object root in `expected`, a
command name, and command `input`. The client-side fields do not grant authority.
Lean checks the current scoped law. Commands are:

| Command | Input | Admission condition |
| --- | --- | --- |
| `commit0`, `commit1` | `{round,digest}` | Correct seat, current round, empty own commitment, live game, 64 lowercase hex digest |
| `reveal0`, `reveal1` | `{round,source,target,nonce}` | Correct seat, both commitments present, own reveal unused, current round, matching digest |
| `resolve` | `{round}` | Either seat, both reveals present, live game, current round |

Read the root with `{"op":"inspect","object":"table:repair-cafe","principal":"did:plc:alice"}`.
Copy the returned whole root into `expected`. A version number or table name alone
is insufficient. A competing commit may invalidate a root; read again and use a
new intent. Repeating an identical old intent returns its retained outcome.

Do not send a reveal until both commitments are present. A received nonce is
public data, including when its request is refused and retained; rejection cannot
make previously transmitted plaintext secret. The protocol stores only hashes
before reveals, and the helper never includes a move or nonce in commit input.
Application state retains revealed coordinates, not nonce strings; the admitted
request history retains submitted reveals.

## Commitment bytes

The digest is SHA-256 over the canonical UTF-8 JSON encoding of this fixed array:

```text
["delvetalk.automatafl.commit.v1", tableId, round, seat, source, target, nonce]
```

Array order is fixed; numbers are JSON natural numbers; strings use the host's
canonical JSON encoder. There is no whitespace between tokens. The Python
custody helper uses the corresponding encoder. `nonce` is exactly 64 lowercase
hex characters representing 32 random bytes. Shape checking cannot prove entropy;
a player who substitutes a guessable nonce weakens their own move secrecy.
The table identity is the receiving object ID supplied by Lean through `["object"]`,
not a caller-asserted input field. Every command also checks that the display
`state.table` matches that actual receiver. Installing a copied program with the
old table label under another object ID therefore refuses table operations.
Binding the actual receiver identity, round and numeric seat prevents replaying a valid
opening across another table, round or seat. Both commits are required before
the first reveal, so seeing one opening does not permit changing the other move.

## Resolve and retry

Resolution invokes `Validated.play(w,h,board,automaton,marks,s0,t0,s1,t1)` using
sources embedded in the immutable protocol. It atomically stores the returned
`{board,automaton,marks,status,winner}`, advances the commitment round, and clears
both move slots. The receipt's new root contains the game result. A transaction
that later fails rolls the entire resolution back; an exact retry of a committed
resolution retrieves the historical receipt without advancing the game again.

Game status 0 means completed, 1 conflict, 2 invalid/unchanged, 3 already terminal.
Conflict and invalid pairs deliberately open a fresh commitment round; returned
board/marks are preserved exactly. This is table admission policy, not a new
movement variant. A nonzero winner prevents further commitments. Invalid moves
are discovered by the game engine at pair resolution; the client does not decide
legality. Wrong openings refuse without changing any table state.

There is no deadline, forced reveal, resignation, automatic victory for a missing
player, wager, seat reassignment or external publication in this version. A
player can withhold an opening and stop progress. Adding a timeout/adjudication
microprotocol needs an explicit clock/deadline authority contract, not a browser
timer or a silent rules change. The two honest-player round and adversarial
admission journeys are the qualified scope.

## Game qualification

The exact revealed-move source is `game/automatafl/Automatafl.obend`; the separate
`Validated.obend` adds representation checks for 2..9 dimensions, one automaton,
bounded marks and no extra packed-board digits. The source-only package expression
is compiled and checked in Lean, then evaluated through the real Mini demand
engine. Complete source texts participate in every exact object root.

`game/automatafl/reference-report.json` records 353 comparisons: 343 agree with
the pinned two-player Rust reference and 10 differ. Those differences concern
stationary destinations being overwritten and failed move sources remaining
passable in Rust. This table uses the already-qualified Objective Bend transition;
it does not silently claim all Rust behaviors match. No experimental multiplayer
logic is imported. The game lane separately qualifies current package execution
against all 353 stored Objective Bend results.
