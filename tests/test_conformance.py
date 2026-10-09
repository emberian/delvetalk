"""The independent evaluators (impl/python, impl/js, impl/c) against the Lean machine.

Generated closed core terms (tests/conformance/generate.py) are run through
the machine (`evaluate-term` op of delvetalk-obend) and through each evaluator;
results are compared as statuses, weak-head shapes and yielded Plans. Evaluators
are small-step call-by-name; the machine is call-by-need with tariffs, so only
values and stuckness are compared, never step counts.

    python3 -m unittest tests.test_conformance -v
    python3 -m tests.test_conformance [N] [IMPL_DIR]   # print the report only
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.conformance.generate import BINARY, TAGS, UNARY, generate, size, tags

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from tests.host import binary
LEAN = binary()
COUNT = int(os.environ.get("CONFORMANCE_CASES", "400"))

# Disagreements we chose not to fix. Key: the generator's case kind; value: why.
# A disagreeing case of a listed kind is expected; any other disagreement fails.
KNOWN_DIVERGENCE = {
    "shared-effect": "A perform reached while forcing a shared argument cell is refused by the machine "
                     "(Refusal.sharedEffect: an effect would be cached and shared). The evaluators are "
                     "call-by-name: they substitute the argument and perform at each use. The checker "
                     "refuses such programs (an Activity is never in a shared position), so no typed "
                     "term reaches it; matching the machine would need the evaluators to model sharing.",
}


# ---------- the reference ----------

class Reference:
    def __init__(self):
        self.proc = subprocess.Popen([LEAN], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1)

    def evaluate(self, case):
        request = {"op": "evaluate-term", "term": case["term"], "responses": case["responses"]}
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        reply = json.loads(self.proc.stdout.readline())
        if reply.get("status") == "error":
            return {"status": "reference-error", "message": reply["message"], "plans": []}
        return reply["result"]

    def close(self):
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.proc.wait(timeout=60)


# ---------- the evaluators ----------

def shape_of(term):
    kind = term[0]
    if kind in ("nat", "boolean", "label"):
        return {"kind": kind, "value": term[1] if kind != "boolean" else bool(term[1])}
    if kind == "record":
        return {"kind": "record", "names": [name for name, _ in term[1]]}
    if kind == "inject":
        return {"kind": "inject", "label": term[1]}
    return {"kind": kind}


def data_of(term):
    """A literal data term as the wire's Data, or None when it is not literal data."""
    kind = term[0]
    if kind == "nat":
        return {"tag": "natural", "value": term[1]}
    if kind == "boolean":
        return {"tag": "boolean", "value": term[1]}
    if kind == "label":
        return {"tag": "label", "value": term[1]}
    if kind == "record":
        fields = [(n, data_of(t)) for n, t in term[1]]
        if any(v is None for _, v in fields):
            return None
        return {"tag": "record", "fields": [{"name": n, "value": v} for n, v in fields]}
    if kind == "inject":
        payload = data_of(term[2])
        return None if payload is None else {"tag": "variant", "label": term[1], "payload": payload}
    return None


def normalize_evaluator(result):
    plans = [data_of(p) for p in result["plans"]]
    return {"status": result["status"],
            "shape": shape_of(result["term"]) if result["status"] == "value" else None,
            "plans": plans}


def normalize_reference(result):
    return {"status": result["status"], "shape": result.get("shape") if result["status"] == "value" else None,
            "plans": result.get("plans", [])}


class Evaluator:
    def __init__(self, name, argv):
        self.name, self.argv = name, argv

    def run_all(self, cases):
        """Per-case result or {'status': 'rejected', 'message'}: an evaluator that
        refuses its input stops its stream, so the stream is restarted after it."""
        results = {}
        index = 0
        while index < len(cases):
            batch = cases[index:]
            payload = "".join(json.dumps(job(c)) + "\n" for c in batch)
            done = subprocess.run(self.argv, input=payload, capture_output=True, text=True, timeout=600)
            lines = [json.loads(l) for l in done.stdout.splitlines() if l.strip()]
            for case, result in zip(batch, lines):
                results[case["name"]] = result
            index += len(lines)
            if index < len(cases) and len(lines) < len(batch):
                results[cases[index]["name"]] = {"status": "rejected", "message": done.stderr.strip()[-200:]}
                index += 1
        return results


def job(case):
    return {k: v for k, v in case.items() if k != "kind"}


def build_evaluators(impl, scratch):
    found, skipped = [], []
    python = os.path.join(impl, "python", "evaluator.py")
    if os.path.exists(python):
        found.append(Evaluator("python", [sys.executable, python]))
    node = shutil.which("node")
    js = os.path.join(impl, "js", "evaluator.mjs")
    if os.path.exists(js):
        if node:
            found.append(Evaluator("js", [node, js]))
        else:
            skipped.append(("js", "node is not installed"))
    source = os.path.join(impl, "c", "evaluator.c")
    if os.path.exists(source):
        cc, pkg = shutil.which("cc"), shutil.which("pkg-config")
        if not cc or not pkg:
            skipped.append(("c", "cc or pkg-config is not installed"))
        else:
            flags = subprocess.run([pkg, "--cflags", "--libs", "gmp", "json-c"], capture_output=True, text=True)
            if flags.returncode != 0:
                skipped.append(("c", "gmp or json-c is not installed (pkg-config)"))
            else:
                binary = os.path.join(scratch, "evaluator-c")
                built = subprocess.run([cc, "-O2", "-std=c11", source, "-o", binary] + flags.stdout.split(),
                                       capture_output=True, text=True)
                if built.returncode != 0:
                    skipped.append(("c", "does not build: " + built.stderr.strip()[-300:]))
                else:
                    found.append(Evaluator("c", [binary]))
    return found, skipped


# ---------- comparison ----------

def disagreement(reference, other):
    if other["status"] == "rejected":
        return "rejected input: " + other.get("message", "")
    if reference["status"] != other["status"]:
        return f"status {reference['status']} (machine) vs {other['status']}"
    if reference["shape"] != other["shape"]:
        return f"value {json.dumps(reference['shape'])} (machine) vs {json.dumps(other['shape'])}"
    if len(reference["plans"]) != len(other["plans"]):
        return f"{len(reference['plans'])} plans (machine) vs {len(other['plans'])}"
    for a, b in zip(reference["plans"], other["plans"]):
        if b is not None and a != b:
            return f"plan {json.dumps(a)[:80]} (machine) vs {json.dumps(b)[:80]}"
    return None


def c_size(case):
    return size(case["term"])


def key_tags(case):
    found = tags(case["term"])
    return sorted(found)


def report(count=COUNT, impl=os.path.join(ROOT, "impl")):
    cases = generate(count)
    with tempfile.TemporaryDirectory() as scratch:
        evaluators, skipped = build_evaluators(impl, scratch)
        ref = Reference()
        try:
            reference = {c["name"]: normalize_reference(ref.evaluate(c)) for c in cases}
        finally:
            ref.close()
        out = {"cases": len(cases), "skipped": skipped, "evaluators": {}}
        for ev in evaluators:
            raw = ev.run_all(cases)
            agree, first, bad = 0, {}, []
            excused = 0
            for c in cases:
                got = raw.get(c["name"], {"status": "rejected", "message": "no output"})
                other = got if got["status"] == "rejected" else normalize_evaluator(got)
                why = disagreement(reference[c["name"]], other)
                if why is None:
                    agree += 1
                else:
                    bad.append((c, why))
                    excused += c["kind"] in KNOWN_DIVERGENCE
                    for t in key_tags(c):
                        if t not in first or c_size(c) < first[t][2]:
                            first[t] = (c["name"], why, c_size(c))
            out["evaluators"][ev.name] = {"agree": agree, "first": first, "bad": bad, "excused": excused}
        return out


def render(out):
    lines = [f"{out['cases']} generated terms"]
    for name, why in out["skipped"]:
        lines.append(f"SKIPPED {name}: {why}")
    for name, r in out["evaluators"].items():
        lines.append(f"\n{name}: {r['agree']}/{out['cases']} agree with the machine; "
                     f"{r['excused']} known divergence, {len(r['bad']) - r['excused']} unexpected")
        for t, (case, why, n) in sorted(r["first"].items()):
            lines.append(f"  {t:<24} {case} ({n} nodes)  {why[:100]}")
    return "\n".join(lines)


class Conformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = report()
        print("\n" + render(cls.out))

    def test_generator_covers_every_constructor_and_primitive(self):
        seen = set()
        for c in generate(COUNT):
            tags(c["term"], seen)
        self.assertEqual(sorted(set(TAGS) - seen), [])
        self.assertEqual(sorted(set("binary:" + b for b in BINARY) - seen), [])
        self.assertEqual(sorted(set("unary:" + u for u in UNARY) - seen), [])

    def test_the_machine_evaluates_every_generated_term(self):
        ref = Reference()
        try:
            for c in generate(COUNT):
                self.assertNotEqual(ref.evaluate(c)["status"], "reference-error", c["name"])
        finally:
            ref.close()

    def test_evaluators_agree_with_the_machine_except_known_divergence(self):
        self.assertTrue(self.out["evaluators"], "no evaluator could run")
        for name, r in self.out["evaluators"].items():
            with self.subTest(evaluator=name):
                unexpected = [(c["name"], why) for c, why in r["bad"] if c["kind"] not in KNOWN_DIVERGENCE]
                self.assertEqual(unexpected[:3], [])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        print(render(report(int(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "impl"))))
    else:
        unittest.main()
