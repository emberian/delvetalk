# Automatafl: two seats, one shared board

This companion adds a resident view to the [qualified two-player table](../../game/table/README.md).
Every offered table uses the original tuned 11×11 opening with 12 attractors,
24 repulsors and the automaton at F6. The companion preserves the underlying
table commands, commitment bytes and qualified two-player movement rules.
There is no board-size, layout or rules selection.
North aims for the top corners; South aims for the bottom corners. Both players
move the shared attractors and repulsors to guide the automaton.

**This is a facilitated match.** Before playing, agree on two named seats and an
actual private way to hand choices to the operator. The operator can see choices
in its custody. Public town posts and PDS records are not private move channels.
Without private custody, offer an explicitly open rehearsal or an invitation to
arrange a match; do not label an unconfigured card playable.

## Install and encounter

With the compiled host already built, prepare an explicit new table:

```sh
python3 protocols/automatafl/generate.py --table table:automatafl \
  --seat0 north --seat1 south --principal operator --intent open-table \
  > /tmp/automatafl-create.json
python3 scripts/world.py --profile compiled /tmp/automatafl-world.json /tmp/automatafl-create.json
```

Choose the actual authorized principals when installing. Local principal strings
do not authenticate repository control. This generator creates no public post,
enrollment channel, seat reassignment or forced opening.

Use a separate mode-0700 directory per seat with the existing
[private participant helper](../../game/table/PARTICIPANT.md). In the agreed
private interaction, a player can say “F10 to F7”; the operator confirms that as
source index 104, target 71 before preparing the sealed move. A1 is index 0, K1 is 10,
A2 is 11, K11 is 120; rows increase downward. This translation chooses no move for the player.

The helper retains the exact request, nonce and opening before sending. Only
the digest enters the first request. After both commitments, each seat explicitly
opens its original move. Even a refused opening is disclosed in request history.
After a lost reply, retry the original prepared token; never invent a replacement
opening. A stale refusal needs a fresh observation and new intent.

## Public companion

[`Table.obend`](Table.obend) runs through Lean to describe each phase. It offers
only `resolve`, and only after both openings. Current law still decides who may
act. Conflicts, invalid pairs, marks and terminal results remain the actual game’s
outcomes. There are no public source/target/nonce entry forms.

For an already configured cardbook and saved exact public root:

```sh
python3 protocols/automatafl/companion.py --root /tmp/table-root.json \
  --table table:automatafl --book /private/operator/cardbook --alias game-round0
```

This captures a normal town card and prints a coordinate board from that same
root. Each move appears only after its opening is admitted. The board is
presentation, not another movement evaluator. No principal,
unopened move, nonce or full commitment digest appears in the output. Publishing
and binding the real post remain explicit operator actions. Residents may then
use the offered resolve spell or ordinary language interpreted against the exact
captured table; the existing clerk preserves authorship and admission receipts.

[Conformance](../../conformance/test_automatafl_companion.py) exercises a complete
match with private custody, lost replies and actual Lean admission, then public
spell/manual receiving through GET-only PDS fixtures. These local tests establish
no hosted match or private remote channel.
