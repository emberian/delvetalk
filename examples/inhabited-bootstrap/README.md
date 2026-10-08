# Two people, a moth, and a world they can change

Iris and Moss share a repair café. Iris straightens a mechanical moth's wing;
Moss winds its spring. Their work is one committed world state, so an old view
cannot overwrite another participant's turn. Iris then proposes opening a window
in the café's own scene source. A compiler checks the proposal; Moss reviews its
explicit migration and adopts it. Moss can now release the moth and leave a
chalk star for the next visitor.

The second change reaches the interface itself. Moss proposes a new **pure Bend
view program** for the shared lamp sign. Iris adopts it, sees the new wording and
uses its offered action. Its details panel shows the lamp becoming lit. The view
program is an admitted part of the object's protocol, and Lean evaluates it
against a retained snapshot. Reading it changes no world state.

Iris and Moss are scripted local principals in this journey, not model calls or
remote accounts. Their commands use the same objects, laws, compiler artifacts,
transactions and receipts available to a person or agent running the CLI.

## Run it and keep the world

Build the world, transactions and scene bridge first (`make check` builds and
checks these parts). Then choose a fresh directory:

```sh
python3 scripts/bootstrap.py run /tmp/inhabited-cafe
python3 scripts/bootstrap.py view /tmp/inhabited-cafe > /tmp/cafe-view.json
python3 scripts/bootstrap.py view /tmp/inhabited-cafe --html > /tmp/current-cafe.html
python3 scripts/bootstrap.py view /tmp/inhabited-cafe --object sign:shared-lamp
python3 scripts/bootstrap.py view /tmp/inhabited-cafe --object sign:shared-lamp --panel details
python3 scripts/bootstrap.py view /tmp/inhabited-cafe --object table:empty
```

The runner refuses to initialize a nonempty directory. It leaves a durable
`world.json`, immutable compiler/scene artifacts, exact retained observations,
a request/receipt history in the world, an event log, a full report, and static
`cafe.html` and `sign.html` views. Nothing is posted or delivered externally.
The object identities and current café artifact ID are in `manifest.json`.

Actions require an explicitly saved view and stable intent. There is no implicit
refresh during dispatch:

```sh
python3 scripts/bootstrap.py view /tmp/inhabited-cafe --object sign:shared-lamp > /tmp/sign-view.json
python3 scripts/bootstrap.py act /tmp/inhabited-cafe --view /tmp/sign-view.json \
  --principal moss --intent light-lamp-from-my-view --action light
```

For scene choices use `--choice 0`; entering an unstarted scene uses `--start`.
A refused action exits `1`; invalid transport input exits `2`. Repeat the exact
view, action and intent to recover its retained receipt. For a new action after
someone else has changed the world, read again and choose a new intent. The
journey deliberately retains three obsolete views so these refusals can be
reproduced. For example:

```sh
python3 scripts/bootstrap.py act /tmp/inhabited-cafe \
  --view /tmp/inhabited-cafe/observations/repaired-before-improvement.json \
  --principal moss --intent old-program-view --choice 1
```

This retrieves the already retained stale-root refusal. It does not reinterpret
that old choice index under the new scene. Request factories frame data; Lean
checks current law, preimages and command guards.

## Source people can work on

- `cafe.scene` starts with the small shared repair bench.
- `cafe-improved.scene` adds the window and chalk-star interaction.
- `improvement-scenarios.json` checks two participants, repair prerequisites,
  stale roots, repeated semantic actions and unauthorized calls.
- `migration.json` is Iris's explicit complete state after both repairs. It
  preserves the repaired wing and wound spring, initializes the new chalk field,
  and updates passage/choice data for the new scene.
- `sign-scenarios.json` checks the shared lamp command; the exact proposed view
  programs live in `scene/projections/sign-v1.json` and `sign-v2.json`. The journey
  additionally evaluates the actual before/after views through Lean and invokes
  the new view's action.
- `table.json` is an ordinary empty object reserved for a later activity.

The migration is reviewed against the exact café root used at adoption. It is
not inferred from source or silently substituted with a new initial state. Its
passage and choice indices are specific to these scene versions; moving passages
requires an explicit corresponding migration. A new source desk can propose
another change using `scripts/desk.py`; see [the source desk contract](../../profiles/DESK.md).
A build artifact and green tests alone never install a proposal.

Moss alone can adopt café programs; Iris alone can adopt sign programs. Each
proposal's compiler can only publish compilation results, and cannot act as
its reviewer. Both participants can use the granted scene commands. The initial
café law explicitly includes the forthcoming window commands, so program change
does not silently confer authority. A new command outside those grants needs a
separate current-law revision. These are local asserted principals, not a network
authentication scheme.

Adoption executes one atomic transaction: release the desk's exact stored
`{protocol,state}`, then reprogram the target from that result. Both complete
read roots and both current authorities are checked by Lean. The ready desk's
`lastRelease` names the reviewer; the transaction receipt and target root establish
that adoption actually happened. Lost replies can recover the same receipt.

The initial table is an empty extension point whose law grants Iris and Moss
reprogram rights. In a compiled-profile world, the `table` command below installs
the stabilized two-player Automatafl program and grants its seat commands through
explicit admissions. The initial reservation itself has no game commands.
The café itself uses a compact source so the whole adoption transaction fits the
host's existing 64 KiB request envelope.

`python3 conformance/test_inhabited_bootstrap.py` runs the persistent journey,
checks actual source/receipt/authority boundaries, verifies the pure view change,
and exercises the same public CLI against retained views. The assertions describe
observed cases; they are not a proof of arbitrary migration or protocol safety.

## Reconstruct somewhere else

The local export bundles the retained admission history together with original
scene sources, complete room artifacts, proposal reports and exact declared
source dependencies. Fresh bootstrap runs preserve these bytes when artifacts
are created, so an export does not quietly substitute today's compiler sources
for an older pin. The original runtime profile is recorded through the shared
runtime closure. Export requires that the installed trusted runtime still
matches it; a legacy world without this evidence refuses rather than acquiring
an invented provenance record.

```sh
python3 scripts/bootstrap.py export /tmp/inhabited-cafe /tmp/inhabited-cafe-bundle
```

The result prints `genesis`, `head` and `worldSha256`. Record the intended genesis
and head through your own trusted channel. Then another local installation with
the matching trusted runtime can verify or reconstruct the world:

```sh
python3 scripts/bootstrap.py verify /tmp/inhabited-cafe-bundle \
  --genesis KNOWN_GENESIS --head KNOWN_HEAD
python3 scripts/bootstrap.py restore /tmp/inhabited-cafe-bundle /tmp/restored-cafe \
  --genesis KNOWN_GENESIS --head KNOWN_HEAD
python3 scripts/bootstrap.py view /tmp/restored-cafe --object sign:shared-lamp > /tmp/restored-sign.json
python3 scripts/bootstrap.py act /tmp/restored-cafe --view /tmp/restored-sign.json \
  --principal moss --intent next-visitor --action light
```

The uppercase values are placeholders for the exact hashes the caller intends
to accept. `--base-head` additionally requires a previously known commit to occur
in the retained history. Neither command silently trusts the bundle's claimed
head as its expected head. A hash establishes identity; it is not a custodian's
signature, authentication of a principal, or proof that a particular person
endorsed the history.

Verification actually replays every retained request through the matching local
Lean runtime and compares receipts and reconstructed world hashes. It checks the
source artifact associated with every program creation and reprogramming,
including a transaction's `inputFrom` candidate. This command never falls back
to inline-only provenance or executes a runtime supplied by the bundle.

Restore creates both the world and its artifact custody. The bootstrap index is
itself attached to a history entry, so its object and artifact identities are
part of the checked chain. Source-bound room views and the pure Bend sign are
rendered from the staged reconstructed world before publication. The destination
must not exist, including as an empty directory or symlink; Linux and macOS use
an atomic operating-system no-replace rename. A failed verification leaves no
published destination. The old source directory is not required after export.

`reconstruction.json` records the accepted anchors and restored artifact IDs;
`cafe.html` and `sign.html` can be opened immediately. The reconstructed world
retains the same local principal-assertion boundary as the original. Continuing
it does not send messages to Delve or acquire another participant's credentials.
The conformance suite deletes its own original fixture after export, reconstructs
into fresh custody, and invokes the restored sign from a separate CLI process.

The reconstructed custody also retains the verified history checkpoint. Exporting
again preserves that anchored prefix byte for byte, including its original
artifact links, and appends new admissions. Adding another spelling or compiler
artifact for an old program cannot rewrite a previously accepted head. Prefix
export independently checks the retained checkpoint against the world; a forked
or shortened local history refuses. Only newly admitted requests select new
source attachments.

To reserve the same world for the compiled host's table extension, select its
profile at creation rather than switching an existing history underneath it:

```sh
python3 scripts/bootstrap.py run /tmp/inhabited-compiled --profile compiled
```

The default remains `transactions`. The chosen profile is recorded in the index
and shared runtime closure, used by source-desk compilation/adoption, and retained
by view, action and reconstruction commands.

## Play at the same café table

The compiled profile can turn that reserved table into a complete two-player
Automatafl table without moving the café into another world:

```sh
python3 scripts/bootstrap.py run /tmp/cafe-with-a-table --profile compiled
python3 scripts/bootstrap.py table /tmp/cafe-with-a-table
python3 scripts/bootstrap.py view /tmp/cafe-with-a-table
python3 scripts/bootstrap.py view /tmp/cafe-with-a-table --object table:empty
python3 scripts/bootstrap.py export /tmp/cafe-with-a-table /tmp/cafe-and-match-bundle
```

The table command delegates to `scripts/table_journey.py`. It explicitly
reprograms the reserved object, grants the two seat principals their command
rights, then plays an authored five-round match through the existing compiled
Lean receiving profile. Each round commits both moves, reveals them and resolves
the round. A wrong late reveal refuses; the match finishes with player 1 winning.
The café's exact source-bound view remains unchanged. The name `table:empty` is
its stable object identity; after installation its actual committed state is a
live game table, not an empty reservation.

The two seat principals are explicit local DIDs, and their private nonce custody
is kept in mode-0600 files under `table-journey/private/`. Public requests and
receipts are retained separately. Running the command again recovers the completed
match if its final root is unchanged. The report is
`table-journey/report.json`; the ordinary world history and source artifacts also
cover the table installation and every game admission. Export never bundles the
private nonce files. Revealed nonces in public retained reveal requests remain
part of the game's normal transcript.

This command works only with a bootstrap created using `--profile compiled`.
It does not switch the runtime behind an existing transactions-profile history.
It performs no live PDS calls, posts or other external delivery, and uses only the
stabilized two-player game.
