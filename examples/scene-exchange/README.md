# The Rain Relay

Jun frees a roof vane. Tavi opens a shutter. Together they release yesterday's
rain into a listening room and give its sound a name: Threadsong.

The [scene](rain-relay.scene) uses the pinned Spween i64 subset. The
[rain card](RainCard.obend) owns a typed name/ink form in ordinary Bend source.
The scene uses the source-owned SceneRuntime and Handler; its announcement is
retained in the handler state.
Both sources pass proposal scenarios before local installation. The journey
copies portal action tokens, prepares exact drafts, submits to Lean, and retains
source-bound history. It needs no language model or credentials.

After the repository's normal `make build scene-build`, choose a new directory:

```sh
python3 examples/scene-exchange/journey.py /tmp/rain-relay
python3 scripts/portal.py /tmp/rain-relay --principal tavi --allow-local-actions
```

Open the printed loopback URL. The listening room remains open; its **Listen
once more** action is usable. **Details** exposes source, state, law and retained
receipts. Copy `do CARD ACTION` from a card; forms append a JSON object such as
`{"name":"Threadsong","ink":"silver"}`. Use the card's actual identifiers.
Prepare, review, then execute. A retry uses the same draft. A stale refusal needs
a fresh card and a new draft.

`report.json` records the result; `events.json` keeps the copyable tokens, cards,
drafts and replies. `sources/` and `artifacts/` retain original text and compiler
provenance. `history/` replays all admissions through the named local host
(default `compiled`). Its genesis/head hashes identify this run; trust in
those hashes must come through a separate channel. Portal actions after the run
extend the world beyond that initial history checkpoint.

The journey includes premature release, an unauthorized visitor, Tavi's stale
card, exact retry, invalid ink clarification, and an attempted second name.
The naming card's reader convention does not enforce order across objects.
Form field bounds guide portal input; the source receiving method enforces them
and first-write semantics. Lean owns authority and exact-root admission. The
source handler retains the scene announcement; no external delivery is attempted.

```sh
python3 conformance/test_scene_exchange.py
```

This tests scripted local coordination, source custody and replay. Principals are
local assertions; the journey establishes no network identity or deployment.
