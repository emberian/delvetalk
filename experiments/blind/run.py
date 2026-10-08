#!/usr/bin/env python3
"""Examine completed capsule reconstructions without repairing their code."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
STYLES = ("machine", "algebra", "rewrite")
OUTPUT_LIMIT = 65536


def digest(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def strict_equal(a, b):
    """JSON numbers and booleans are distinct; array order is significant."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(strict_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(strict_equal(x, y) for x, y in zip(a, b))
    return a == b


def mismatch_paths(want, got, path="$", limit=12):
    if strict_equal(want, got):
        return []
    if type(want) is not type(got):
        return [path + " (type)"]
    if isinstance(want, dict):
        paths = [path + "." + key + " (missing)" for key in want.keys() - got.keys()]
        paths += [path + "." + key + " (unexpected)" for key in got.keys() - want.keys()]
        for key in want.keys() & got.keys():
            paths.extend(mismatch_paths(want[key], got[key], path + "." + key, limit))
        return sorted(paths)[:limit]
    if isinstance(want, list):
        paths = [path + " (length)"] if len(want) != len(got) else []
        for index, (a, b) in enumerate(zip(want, got)):
            paths.extend(mismatch_paths(a, b, f"{path}[{index}]", limit))
        return paths[:limit]
    return [path]


def execute(candidate, payload, timeout):
    # One process per case: a crash or divergent implementation cannot erase
    # observations for later cases. Tempfiles avoid unbounded captured output.
    with tempfile.TemporaryFile() as inp, tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        inp.write(payload.encode("utf-8")); inp.seek(0)
        proc = subprocess.Popen([sys.executable, str(candidate)], cwd=ROOT,
                                stdin=inp, stdout=out, stderr=err,
                                start_new_session=True)
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        def read(stream):
            stream.seek(0)
            raw = stream.read(OUTPUT_LIMIT + 1)
            return raw[:OUTPUT_LIMIT].decode("utf-8", errors="replace"), len(raw) > OUTPUT_LIMIT
        stdout, out_over = read(out)
        stderr, err_over = read(err)
        return {"returncode": proc.returncode, "timed_out": timed_out,
                "output_truncated": out_over or err_over,
                "stdout": stdout, "stderr": stderr}


def malformed_cases():
    base = {"name": "invalid", "term": ["nat", "0"]}
    def job(**changes):
        return json.dumps({**base, **changes}, ensure_ascii=True) + "\n"
    return [
        ("invalid-json", "{\n"),
        ("job-array", "[]\n"),
        ("missing-name", '{"term":["nat","0"]}\n'),
        ("non-string-name", job(name=1)),
        ("unknown-job-member", job(extra=True)),
        ("unknown-term-tag", job(term=["wat"])),
        ("extra-term-member", job(term=["nat", "0", "extra"])),
        ("numeric-nat", job(term=["nat", 0])),
        ("leading-zero-nat", job(term=["nat", "01"])),
        ("negative-nat", job(term=["nat", "-1"])),
        ("boolean-index", job(term=["bound", True])),
        ("out-of-range-index", job(term=["bound", 2**53])),
        ("negative-fuel", job(fuel=-1)),
        ("boolean-fuel", job(fuel=True)),
        ("fractional-fuel", job(fuel=1.5)),
        ("out-of-range-fuel", job(fuel=2**53)),
        ("unused-invalid-response", job(responses=[["nat", "01"]])),
        ("lone-surrogate-label", job(term=["label", "\ud800"])),
        ("lone-surrogate-name", job(name="\ud800")),
        ("record-object-not-pairs", job(term=["record", {"x": ["nat", "0"]}])),
        ("unknown-primitive", job(term=["binary", "plus", ["nat", "1"], ["nat", "2"]])),
    ]


def semantic_observation(candidate, case, timeout):
    expected = {"name": case["name"], **case["expected"]}
    job = {k: v for k, v in case.items() if k != "expected"}
    execution = execute(candidate, json.dumps(job, ensure_ascii=True) + "\n", timeout)
    result = {"name": case["name"]}
    if execution["timed_out"]:
        return {**result, "outcome": "timeout", "execution": execution}
    if execution["returncode"] != 0 or execution["output_truncated"]:
        return {**result, "outcome": "execution-error", "execution": execution}
    try:
        lines = execution["stdout"].splitlines()
        if len(lines) != 1:
            raise ValueError("expected exactly one JSONL result")
        actual = json.loads(lines[0])
    except (ValueError, TypeError) as error:
        return {**result, "outcome": "result-wire-error", "detail": str(error), "execution": execution}
    if strict_equal(expected, actual):
        return {**result, "outcome": "pass"}
    result_wire = not isinstance(actual, dict) or set(actual) != set(expected)
    if not result_wire:
        result_wire = (not isinstance(actual["name"], str)
                       or actual["status"] not in ("value", "stuck", "yield", "exhausted")
                       or not isinstance(actual["term"], list)
                       or not isinstance(actual["plans"], list))
    return {**result, "outcome": "result-wire-error" if result_wire else "semantic-mismatch",
            "mismatch_paths": mismatch_paths(expected, actual), "expected": expected, "actual": actual}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--styles", nargs="+", choices=STYLES, default=list(STYLES))
    parser.add_argument("--cases", type=Path, action="append", help="repeat to append a source-backed fixture file")
    parser.add_argument("--timeout", type=float, default=2.0, help="seconds per case and candidate")
    parser.add_argument("--report", type=Path, default=ROOT / "experiments/blind/results.json")
    parser.add_argument("--candidates-ready", action="store_true", help="assert candidate authors have finished")
    args = parser.parse_args()
    if not args.candidates_ready:
        parser.error("wait for candidate completion, then pass --candidates-ready")
    if args.timeout <= 0 or len(set(args.styles)) != len(args.styles):
        parser.error("positive timeout and unique styles required")
    paths = args.cases or [ROOT / "conformance/cases.json"]
    cases = []
    sources = []
    for path in paths:
        path = path.resolve()
        incoming = json.loads(path.read_text())
        if not isinstance(incoming, list) or not incoming:
            raise ValueError(f"empty or invalid fixture file: {path}")
        for case in incoming:
            if set(case) - {"name", "term", "responses", "fuel", "expected"}:
                raise ValueError("unknown fixture members")
            if set(case["expected"]) != {"status", "term", "plans"}:
                raise ValueError("expected must contain status, term, plans")
        cases.extend(incoming)
        sources.append(digest(path))
    if len({case["name"] for case in cases}) != len(cases):
        raise ValueError("duplicate fixture names")
    report = {"experiment": "capsule-reconstruction-v1", "created_at": datetime.now(timezone.utc).isoformat(),
              "isolation": "instruction-based; no filesystem sandbox; candidate authors received one capsule plus AST.md",
              "scope": "pure core reconstruction; no object host, typechecker, durable activity, or network conformance claim",
              "examiner": digest(Path(__file__).resolve()),
              "source_provenance": digest(ROOT / "spec/upstream.json"),
              "wire_document": digest(ROOT / "experiments/blind/inputs/AST.md"), "fixture_sources": sources,
              "timeout_seconds_per_case": args.timeout, "candidates": {}}
    for style in args.styles:
        candidate = ROOT / f"experiments/blind/{style}/evaluator.py"
        capsule = ROOT / f"capsules/{style}-2k.txt"
        candidate_pin = digest(candidate)
        observations = [semantic_observation(candidate, case, args.timeout) for case in cases]
        malformed = []
        for name, payload in malformed_cases():
            execution = execute(candidate, payload, args.timeout)
            passed = (execution["returncode"] != 0 and bool(execution["stderr"].strip())
                      and not execution["stdout"].strip() and not execution["timed_out"]
                      and not execution["output_truncated"])
            malformed.append({"name": name, "outcome": "pass" if passed else "malformed-wire-accepted-or-bad-diagnostic",
                              **({} if passed else {"execution": execution})})
        counts = {kind: sum(row["outcome"] == kind for row in observations)
                  for kind in ("pass", "semantic-mismatch", "result-wire-error", "execution-error", "timeout")}
        if digest(candidate) != candidate_pin:
            raise RuntimeError(f"candidate changed during examination: {style}")
        report["candidates"][style] = {"capsule": digest(capsule), "implementation": candidate_pin,
            "semantic_counts": counts, "semantic_total": len(observations),
            "malformed_wire_passed": sum(row["outcome"] == "pass" for row in malformed),
            "malformed_wire_total": len(malformed), "semantic_observations": observations,
            "malformed_wire_observations": malformed}
        print(f"{style}: {counts['pass']}/{len(observations)} semantic; "
              f"{report['candidates'][style]['malformed_wire_passed']}/{len(malformed)} malformed wire", file=sys.stderr)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
    # A faithful experiment may have failed candidates. Exit 1 preserves that
    # signal; this exploratory experiment is deliberately outside make check.
    return int(any(c["semantic_counts"]["pass"] != c["semantic_total"]
                   or c["malformed_wire_passed"] != c["malformed_wire_total"]
                   for c in report["candidates"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
