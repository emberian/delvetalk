#!/usr/bin/env python3
"""Examine completed compact-context reconstructions; never repair candidates."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / "experiments/blind/run.py"
spec = importlib.util.spec_from_file_location("blind_examiner", HELPER_PATH)
examiner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(examiner)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--styles", nargs="+", choices=examiner.STYLES, default=list(examiner.STYLES))
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--report", type=Path, default=ROOT / "experiments/capsule-only/results.json")
    parser.add_argument("--candidates-ready", action="store_true", help="assert the selected authors have finished")
    args = parser.parse_args()
    if not args.candidates_ready:
        parser.error("wait for candidate completion, then pass --candidates-ready")
    if args.timeout <= 0 or len(set(args.styles)) != len(args.styles):
        parser.error("positive timeout and unique styles required")
    paths = [ROOT / "conformance/cases.json", ROOT / "conformance/adversarial-cases.json"]
    cases = [case for path in paths for case in json.loads(path.read_text())]
    if len({case["name"] for case in cases}) != len(cases):
        raise ValueError("duplicate fixture names")
    wire_pin = examiner.digest(ROOT / "experiments/capsule-only/WIRE.txt")
    report = {
        "experiment": "compact-context-reconstruction-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "isolation": "instruction-based; no filesystem sandbox; fresh candidate authors received only one 2K capsule plus WIRE.txt",
        "scope": "pure core semantic observations, not object model reconstruction or a refinement proof",
        "malformed_wire_policy": "informational only; compact input omits several constraints from the first trial; rejection differences do not affect experiment exit status",
        "capacity_policy": "compact inputs specify no 2^53-1 index or fuel ceiling; full-wire capacity rejection requirements do not apply",
        "examiner": examiner.digest(Path(__file__).resolve()),
        "examiner_helpers": examiner.digest(HELPER_PATH),
        "source_provenance": examiner.digest(ROOT / "spec/upstream.json"),
        "wire_document": wire_pin,
        "fixture_sources": [examiner.digest(path) for path in paths],
        "timeout_seconds_per_case": args.timeout,
        "candidates": {},
    }
    for style in args.styles:
        candidate = ROOT / f"experiments/capsule-only/{style}/evaluator.py"
        capsule = ROOT / f"capsules/{style}-2k.txt"
        candidate_pin = examiner.digest(candidate)
        capsule_pin = examiner.digest(capsule)
        observations = [examiner.semantic_observation(candidate, case, args.timeout) for case in cases]
        malformed = []
        for name, payload in examiner.malformed_cases():
            execution = examiner.execute(candidate, payload, args.timeout)
            rejected = (execution["returncode"] != 0 and bool(execution["stderr"].strip())
                        and not execution["stdout"].strip() and not execution["timed_out"]
                        and not execution["output_truncated"])
            malformed.append({"name": name, "rejected_with_diagnostic": rejected,
                              "interpretation": "informational; full-wire rejection rule not necessarily in compact contract",
                              **({} if rejected else {"execution": execution})})
        if examiner.digest(candidate) != candidate_pin:
            raise RuntimeError(f"candidate changed during examination: {style}")
        counts = {kind: sum(row["outcome"] == kind for row in observations)
                  for kind in ("pass", "semantic-mismatch", "result-wire-error", "execution-error", "timeout")}
        report["candidates"][style] = {
            "capsule": capsule_pin, "implementation": candidate_pin,
            "combined_input_bytes": capsule_pin["bytes"] + wire_pin["bytes"],
            "semantic_counts": counts, "semantic_total": len(observations),
            "semantic_observations": observations,
            "informational_malformed_rejected": sum(row["rejected_with_diagnostic"] for row in malformed),
            "informational_malformed_total": len(malformed),
            "informational_malformed_observations": malformed,
        }
        print(f"{style}: {counts['pass']}/{len(observations)} semantic; "
              f"{report['candidates'][style]['combined_input_bytes']} combined input bytes", file=sys.stderr)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
    return int(any(c["semantic_counts"]["pass"] != c["semantic_total"]
                   for c in report["candidates"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
