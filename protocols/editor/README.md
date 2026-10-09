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
