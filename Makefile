.PHONY: all build check core capsules world wiki syntax delve proposals scene-build scene
all: check
build:
	LEAN_NUM_THREADS=1 lake build delvetalk
	$(MAKE) -C impl/c
	LEAN_NUM_THREADS=1 lake build delvetalk-world
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
world:
	python3 conformance/test_world.py
	python3 conformance/test_world_adversarial.py
wiki:
	python3 conformance/test_wiki.py
syntax:
	python3 conformance/test_syntax.py
delve:
	python3 conformance/test_delve.py
	python3 conformance/test_delve_adversarial.py
	python3 conformance/test_intake.py
proposals:
	python3 conformance/test_propose.py
scene:
	python3 conformance/test_scene.py
check: build scene-build capsules core world wiki syntax delve proposals scene
