# Play from small action cards

[`table_participant.py`](../../scripts/table_participant.py) gives each of the
two seats a private custody directory and a portable typed card. It uses the
existing compiled table and commitment library; Lean admits every request and
executes the game. Create the table using the [table guide](README.md).

```sh
python3 scripts/table_participant.py --database /tmp/table-world.json \
  --custody /tmp/alice-table --table table:cafe --principal alice --seat 0 observe
```

The card shows indexed board cells, the round, seals/openings and offered actions.
`.` is empty, `+` attracts, `-` repels and `@` is the automaton. Indices run left
to right, top to bottom on the original 11×11 opening: A1=0, K1=10, A2=11,
F6=60, K11=120. There is no board selection. Source and target are bounded integers; movement legality
is checked when both moves resolve. The cards also work unchanged with the
[token interpreter](../../scripts/interpret.py), for example
`do CARD commit {"source":104,"target":71}`. That example is F10 to F7. No model call is needed.

Repeat the same connection arguments, replacing `observe` with:

```sh
prepare CARD commit --fields '{"source":104,"target":71}' --intent alice-round0-seal
send PREPARED
```

`prepare` saves the exact observed root, intent and request before transmission.
It stores a random nonce and opening separately in mode-0600 files beneath a
mode-0700 directory. Default output contains neither opening, digest nor raw root.
Keep the whole directory private and use a separate one for each participant.
These local principal strings do not authenticate a DID.

Observe again after each participant acts. Once both seals are observed, your
card offers `reveal`; prepare it with no fields and a new intent. Once both
openings are observed, either seat can prepare `resolve`. Offered actions are
construction hints, not grants: Lean checks the current law and exact root.

After a lost reply, restart with identical connection arguments and `send` the
same prepared token. It reuses the exact request and recovers the host receipt.
A successful `receiptView` describes that receipt's historical root; use
`observe` to see the current table.
A stale refusal stays refused; observe again and prepare with a new intent.
For a repeated commit, supply the original source/target: the same opening is
retained. Historical receipts remain recoverable after a runtime change,
including when only the world's exact receipt survived a lost reply. Observing,
preparing new requests and executing still-pending requests require the pinned
runtime; custody never silently migrates. Exported world history contains revealed
openings, while private unrevealed moves remain in participant custody.

[Tests](../../conformance/test_table_participant.py) cover actual Lean admission,
lost replies, stale and unauthorized requests, hidden openings, a complete match
in the inhabited bootstrap, and anchored export/reconstruction. No external
delivery, timeout, forced opening or new game rule is introduced.
