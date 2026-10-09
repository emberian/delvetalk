.PHONY: all build check core typed packages capsules world wiki syntax delve proposals scene-build scene portal
all: check
build:
	LEAN_NUM_THREADS=1 lake build delvetalk
	$(MAKE) -C impl/c
	LEAN_NUM_THREADS=1 lake build delvetalk-world
	LEAN_NUM_THREADS=1 lake build delvetalk-transactions
	LEAN_NUM_THREADS=1 lake build delvetalk-typed
	LEAN_NUM_THREADS=1 lake build delvetalk-obend
	LEAN_NUM_THREADS=1 lake build delvetalk-compiled
scene-build:
	CARGO_BUILD_JOBS=2 cargo build --locked --manifest-path scene/spween-bridge/Cargo.toml
	CARGO_BUILD_JOBS=2 cargo test --locked --manifest-path scene/spween-bridge/Cargo.toml
capsules:
	python3 scripts/check_capsules.py
core:
	python3 scripts/crosscheck.py --no-build
	python3 conformance/test_python.py
	node conformance/test_js.mjs
	python3 conformance/test_c.py
	python3 conformance/test_adversarial_core.py
typed:
	python3 conformance/test_typed.py
packages:
	python3 conformance/test_package_adversarial.py
	python3 conformance/test_automatafl.py
	python3 conformance/test_automatafl_audit.py
world:
	python3 conformance/test_world.py
	python3 conformance/test_world_adversarial.py
	python3 conformance/test_transactions.py
	python3 conformance/test_reprogram.py
	python3 conformance/test_workshop.py
	python3 conformance/test_authority.py
	python3 conformance/test_compiled.py
	python3 conformance/test_runtime_profile.py
	python3 conformance/test_convergence.py
	python3 conformance/test_game_table.py
	python3 conformance/test_table_journey.py
	python3 conformance/test_desk.py
	python3 conformance/test_desk_profiles.py
	python3 conformance/test_projection.py
	python3 conformance/test_inhabited_bootstrap.py
	python3 conformance/test_bootstrap_adversarial.py
	python3 conformance/test_history.py
	python3 conformance/test_continuation.py
	python3 conformance/test_compiler_queue.py
wiki:
	python3 conformance/test_wiki.py
syntax:
	python3 conformance/test_syntax.py
delve:
	python3 conformance/test_watch.py
	python3 conformance/test_worker.py
	python3 conformance/test_transaction_intake.py
	python3 conformance/test_delve.py
	python3 conformance/test_delve_adversarial.py
	python3 conformance/test_intake.py
	python3 conformance/test_clerk.py
	python3 conformance/test_clerk_compiled.py
	python3 conformance/test_receipts.py
	python3 conformance/test_live_path.py
	python3 conformance/test_management.py
	python3 conformance/test_management_adversarial.py
proposals:
	python3 conformance/test_propose.py
scene:
	python3 conformance/test_room.py
	python3 conformance/test_scene.py
	python3 conformance/test_scene_adversarial.py
portal:
	python3 conformance/test_affordances.py
	python3 conformance/test_interpret.py
	python3 conformance/test_portal.py
	python3 conformance/test_portal_adversarial.py
	node --check portal/static/app.js
check: build scene-build capsules core typed packages world wiki syntax delve proposals scene portal
