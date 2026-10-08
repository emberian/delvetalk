#!/usr/bin/env python3
"""Build independent engines and compare whole results against shared fixtures.

Default requires every engine. Explicit --engines is a scoped development run,
never reported as four-way conformance. Requires Lean 4.30, Python 3, Node,
a C compiler, GMP and json-c (see impl/c/Makefile).
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINES = {
    "lean": [str(ROOT / ".lake/build/bin/delvetalk")],
    "python": [sys.executable, str(ROOT / "impl/python/evaluator.py")],
    "js": ["node", str(ROOT / "impl/js/evaluator.mjs")],
    "c": [str(ROOT / "impl/c/evaluator")],
}


def execute(command, *, data=None, timeout=30):
    proc = subprocess.run(command, cwd=ROOT, input=data, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env={**os.environ, "LEAN_NUM_THREADS": "1"}, timeout=timeout)
    if proc.returncode:
        raise RuntimeError(f"{command!r} exited {proc.returncode}\n{proc.stderr}\n{proc.stdout}")
    return proc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engines", nargs="+", choices=ENGINES, default=list(ENGINES))
    parser.add_argument("--cases", type=Path, default=ROOT / "conformance/cases.json")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--report", type=Path, help="also save the JSON report")
    args = parser.parse_args()
    if len(set(args.engines)) != len(args.engines):
        parser.error("duplicate engine")
    if not args.no_build:
        if "lean" in args.engines:
            result = execute(["lake", "build"], timeout=300)
            print(result.stdout + result.stderr, end="", file=sys.stderr)
        if "c" in args.engines:
            result = execute(["make", "-C", "impl/c"], timeout=300)
            print(result.stdout + result.stderr, end="", file=sys.stderr)
    cases = json.loads(args.cases.read_text())
    if not isinstance(cases, list) or not cases:
        raise ValueError("fixture must be a nonempty array")
    names = [case["name"] for case in cases]
    if len(names) != len(set(names)):
        raise ValueError("duplicate fixture name")
    allowed = {"name", "term", "responses", "fuel", "expected"}
    jobs = []
    expected = []
    for case in cases:
        if set(case) - allowed:
            raise ValueError(f"unknown fixture fields: {set(case) - allowed}")
        if set(case["expected"]) != {"status", "term", "plans"}:
            raise ValueError("expected needs exactly status, term, plans")
        jobs.append({key: value for key, value in case.items() if key != "expected"})
        expected.append({"name": case["name"], **case["expected"]})
    data = "".join(json.dumps(job, ensure_ascii=False, separators=(",", ":")) + "\n" for job in jobs)
    report = {"cases": len(cases), "engines": {}, "failures": []}
    for engine in args.engines:
        result = execute(ENGINES[engine], data=data)
        if result.stderr:
            print(f"{engine}: {result.stderr}", end="", file=sys.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        if len(rows) != len(expected):
            raise RuntimeError(f"{engine}: expected {len(expected)} results, got {len(rows)}")
        passed = 0
        for want, got in zip(expected, rows):
            if got == want:
                passed += 1
            else:
                report["failures"].append({"engine": engine, "name": want["name"],
                                           "expected": want, "actual": got})
        report["engines"][engine] = {"passed": passed, "total": len(cases)}
    report["status"] = "pass" if not report["failures"] else "fail"
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.write_text(payload)
    print(payload, end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(f"crosscheck: {error}", file=sys.stderr)
        raise SystemExit(1)
