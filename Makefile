PY ?= python3

.PHONY: check smoke

check:
	$(PY) -W ignore -m tests.run

smoke:
	$(PY) -W ignore -m tests.run test_turn_world test_chain
