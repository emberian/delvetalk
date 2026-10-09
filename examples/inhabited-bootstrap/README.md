# Two people, a moth, and a world they can change

Iris and Moss repair a mechanical moth, adopt a scene improvement, and replace
a pure Bend lamp view. Lean admits actions and explicit migrations. Views read
retained snapshots without changing state. Participants are scripted local
principals; nothing is posted externally.

## Run it and keep the world

From the repository root, choose an empty directory:

```sh
make build scene-build
python3 scripts/bootstrap.py run /tmp/inhabited-cafe
python3 scripts/bootstrap.py view /tmp/inhabited-cafe --html > /tmp/cafe.html
python3 scripts/bootstrap.py view /tmp/inhabited-cafe --object sign:shared-lamp > /tmp/sign-view.json
python3 scripts/bootstrap.py act /tmp/inhabited-cafe --view /tmp/sign-view.json \
  --principal moss --intent light-from-view --action light
```

The directory retains `world.json`, artifacts, observations, report, event log and
HTML views; `manifest.json` identifies objects. Actions use the saved view without
refresh. Scenes accept `--start` or `--choice N`; views accept `--panel details`.
Exact retries recover receipts. After stale refusal, save a new view and use a
new intent. Refusal exits 1; invalid transport input exits 2.

## Source people can work on

[cafe.scene](cafe.scene), [its improvement](cafe-improved.scene), and
[migration.json](migration.json) define the room change; [sign projections](../../scene/projections/)
define the interface change. Migration explicitly preserves repaired state and
updates version-specific passage/choice indices.

Moss adopts café programs; Iris adopts sign programs. Compilers publish candidates
but cannot review them. Adoption atomically releases the desk candidate and
reprograms the target, checking both roots and authorities. Compilation alone
never installs. New commands require existing grants or a separate law revision.
See the [source desk contract](../../profiles/DESK.md).

## Reconstruct somewhere else

```sh
python3 scripts/bootstrap.py export /tmp/inhabited-cafe /tmp/cafe-bundle
python3 scripts/bootstrap.py verify /tmp/cafe-bundle --genesis KNOWN_GENESIS --head KNOWN_HEAD
python3 scripts/bootstrap.py restore /tmp/cafe-bundle /tmp/restored-cafe \
  --genesis KNOWN_GENESIS --head KNOWN_HEAD
```

Replace placeholders with hashes accepted through your trusted channel. Hashes
identify history; they authenticate no person. Optional `--base-head` requires
a known prefix. Verification replays every request through the matching trusted
local runtime, checks receipts and source attachments, and never executes bundled
runtime code. Missing legacy provenance or runtime mismatch refuses.

Restore requires an absent destination, verifies reconstructed views, then publishes
with atomic no-replace rename. Failure publishes nothing. Original custody is
unnecessary after export. Re-export preserves the verified prefix byte-for-byte
and appends admissions; forked/shortened local history refuses.

## Play at the same café table

Select the runtime at creation; existing histories cannot switch profiles:

```sh
python3 scripts/bootstrap.py run /tmp/cafe-with-table --profile compiled
python3 scripts/bootstrap.py table /tmp/cafe-with-table
python3 scripts/bootstrap.py view /tmp/cafe-with-table --object table:empty
```

`table` reprograms the reserved object, grants seats, then plays five commit/reveal
rounds ending in player 1's win. Retry recovers a completed match only while its
final root remains unchanged. `table-journey/report.json` records results. Private
nonces stay in mode-0600 files and are excluded from export; public reveal requests
remain in history. The default profile is `transactions`.

[Bootstrap tests](../../conformance/test_inhabited_bootstrap.py) and
[adversarial tests](../../conformance/test_bootstrap_adversarial.py) exercise adoption,
stale views and reconstruction. They establish local cases, not arbitrary
migration safety or network authentication. [CLI source](../../scripts/bootstrap.py)
defines artifacts and command options.
