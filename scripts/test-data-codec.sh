#!/bin/sh
# Run in an independent warmed native snapshot under a coordinated compiler seat.
set -eu
cd "$(dirname "$0")/.."
lake env lean --run conformance/PackageDataCodec.lean
