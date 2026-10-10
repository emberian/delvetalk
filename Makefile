PROOF_ONLY = Delvetalk.PackageDataAdmission Delvetalk.PackageDataNormalization Delvetalk.PackageDataSchemaProofs Delvetalk.Typed Theory.ObjectiveBendNativeDataSimulation

build:
	LEAN_NUM_THREADS=2 lake build
	LEAN_NUM_THREADS=2 lake build $(PROOF_ONLY)

PY ?= python3

.PHONY: check smoke profile

# The whole suite in parallel; ends with the tests per layer and the five slowest classes.
check:
	$(PY) -W ignore -m tests.run

# The same, with host processes and hostd daemons counted per class (tests/PROFILE.md).
profile:
	$(PY) -W ignore -m tests.run --profile

smoke:
	$(PY) -W ignore -m tests.run test_turn_world test_chain
