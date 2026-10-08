#!/usr/bin/env python3
"""Verify capsule identity/byte budgets and exact vendored source pins."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "capsules/manifest.json").read_text())
files = {p.name for p in (root / "capsules").glob("*.txt")}
assert files == set(manifest["capsules"]), "capsule inventory changed"
for name, entry in manifest["capsules"].items():
    raw = (root / "capsules" / name).read_bytes()
    assert raw.isascii(), name
    assert len(raw) == entry["bytes"] < entry["exclusiveLimit"], name
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"], name
    print(f"{name}: {len(raw)} < {entry['exclusiveLimit']} bytes")
upstream = json.loads((root / "spec/upstream.json").read_text())
for name, entry in upstream["files"].items():
    raw = (root / "spec/upstream" / name).read_bytes()
    compatibility = entry.get("compatibility")
    if compatibility:
        original = (root / compatibility["source"]).read_bytes()
        assert hashlib.sha256(original).hexdigest() == entry["sha256"], name
        projected = original
        for edit in compatibility["replacements"]:
            before, after = edit["from"].encode(), edit["to"].encode()
            assert projected.count(before) == 1, (name, "ambiguous compatibility edit")
            projected = projected.replace(before, after, 1)
        assert raw == projected, (name, "undeclared upstream modification")
        assert hashlib.sha256(raw).hexdigest() == compatibility["builtSha256"], name
    else:
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], name
print("Capsule and upstream identities match. This check is not semantic conformance.")
