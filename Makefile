PROOF_ONLY = Delvetalk.PackageDataAdmission Delvetalk.PackageDataNormalization Delvetalk.PackageDataSchemaProofs Delvetalk.Typed Theory.ObjectiveBendNativeDataSimulation

build:
	LEAN_NUM_THREADS=2 lake build
	LEAN_NUM_THREADS=2 lake build $(PROOF_ONLY)

PY ?= python3

.PHONY: check smoke

check:
	$(PY) -W ignore -m tests.run

smoke:
	$(PY) -W ignore -m tests.run test_turn_world test_chain
