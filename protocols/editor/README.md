# Repeated authored editing

`Editor.obend` is an ordinary source-owned object. Bind `EDITOR_TARGET` and
`EDITOR_FACTORY` using `generate.editor_source`; grant its five methods explicitly
using `generate.editor_law`. The factory must independently grant `make` to the
same intended makers and configure its compiler. Compilation never grants rights
on the edited target: the target's current law governs reprogramming.

A generation follows these actual receiving turns:

1. `draft(name)` chooses a new generation. An immediate authenticated target
   observation supplies `plan`; its result supplies the factory's `make`.
2. The factory allocates a new one-shot candidate. Submit exact retained source,
   scenarios and a complete target state to that candidate. `report` immediately
   supplies `review`, which selects only the current generation.
3. The ordinary compiler queue compiles that candidate. A later `report` and
   `review` expose ready or failed status. A late older job cannot make the
   current generation ready.
4. A fresh target observation supplies `approve`. Its version must equal the
   planned baseline. The candidate's `adopt` supplies reprogramming, whose actual
   native result immediately supplies `finish`. The whole turn commits together.
   `finish` checks authenticated reprogram origin, target, new version and the
   exact native program digest before recording adopted status.

`scripts/editor.py` frames these turns and retains exact generation inputs and
receipts for interrupted retries. It does not evaluate editing behavior. The
baseline custody record retains the complete target preimage; the source uses
its receiving version. Target drift requires an explicit fresh generation with
current state. Candidate desks never reset from ready to empty. Failed, pending,
ready and previously adopted generations remain inspectable, with their exact
source and compiler receipts retained. The Editor keeps an ordered list of its
candidate identities. The supplied quota is 32 candidates per factory.

`Counter.obend` and its scenarios provide a small target. A second source revision
changes addition to double addition; `failure.examples` deliberately fails a
scenario. `conformance/test_editor_generations.py` joins a lost allocation reply recovered by exact retry, overlapping generations,
late completion, target drift, failed compilation, rebasing, authenticated
adoption, exact history restoration, old receipt retry and another successful
revision. These are local receiving-path examples; they make no publication or
remote identity claim.

The current source emits `delvetalk-obend-data-offers-v1`: ordinary typed menu
content plus visible source-authored transaction recipes. `make` also rebases by
allocating a fresh candidate and capturing a fresh baseline. `submit` asks for
source language (@2 or @3), exact Bend text and examples; it submits an existing
inline source proposal and copies the captured target state. No source-store write
or compilation occurs while preparing a card. `review` and `adopt` use authentic
prior results. The source chooses visibility, references, calls and substitutions;
`scripts/source_offers.py` interprets those recipes against one snapshot. This
competing workflow language is being replaced by Bend preparation under
[the source-ownership design](../../docs/design/BEND.md). Every
offer also retains the exact source owner's root, so changed availability stales
an earlier card.

Portal captures these same recipes. For town, use `Town.capture_offer(object,key)`
or `scripts/town.py --clerk-state STATE capture editor --offer make`. The cardbook
retains the complete composite offer; later replies cannot supply another plan or
silently refresh its roots. Publication remains a separate authorized action.
Source fields are bounded to 32 KiB and examples to 16 KiB; the complete receiving
request must still fit 64 KiB. Missing dependencies appear unavailable. Current
laws decide whether the actual replying author may perform every step.
