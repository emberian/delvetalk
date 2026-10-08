#!/usr/bin/env python3
"""Named source-semantic fixtures and malformed-wire checks; standard library only."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "impl/python/evaluator.py"
spec = importlib.util.spec_from_file_location("delvetalk_python", DRIVER)
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


class Conformance(unittest.TestCase):
    def test_named_source_cases(self):
        cases = json.loads((ROOT / "conformance/cases.json").read_text())
        self.assertEqual(len(cases), len({case["name"] for case in cases}))
        for case in cases:
            with self.subTest(name=case["name"]):
                job = {key: value for key, value in case.items() if key != "expected"}
                self.assertEqual(evaluator.run(job), {"name": case["name"], **case["expected"]})

    def test_reject_malformed_ast(self):
        bad = [None, [], ["nat", 1], ["nat", "01"], ["nat", "-1"],
               ["nat", "1.0"], ["nat", "١"], ["nat", "1", 0], ["nat", True],
               ["bound", True], ["bound", -1], ["bound", 1.5], ["bound", 2**53],
               ["boolean", "true"], ["boolean", 1], ["unknown"], ["lam"],
               ["record", {"x": ["nat", "1"]}], ["record", [[1, ["nat", "1"]]]],
               ["record", [["x", ["nat", "1"], "extra"]]], ["get", ["nat", "1"], 0],
               ["binary", "or", ["boolean", True], ["boolean", False]],
               ["label", "\ud800"], ["inject", "\udfff", ["nat", "0"]]]
        for term in bad:
            with self.subTest(term=term), self.assertRaises(ValueError):
                evaluator.validate(term)

    def test_reject_malformed_jobs(self):
        good = {"name": "test", "term": ["nat", "0"]}
        bad = [None, [], {}, {"term": ["nat", "0"]}, {**good, "name": 7},
               {**good, "fuel": True}, {**good, "fuel": -1}, {**good, "fuel": 0.5},
               {**good, "fuel": 2**53}, {**good, "responses": {}},
               {**good, "responses": [["nat", 0]]}, {**good, "unexpected": 1}]
        for job in bad:
            with self.subTest(job=job), self.assertRaises(ValueError):
                evaluator.run(job)

    def test_jsonl_cli(self):
        jobs = [{"name": "a", "term": ["nat", "12"]},
                {"name": "b", "term": ["label", "λ😀"]}]
        result = subprocess.run([sys.executable, str(DRIVER)],
                                input="".join(json.dumps(job) + "\n" for job in jobs),
                                text=True, capture_output=True, check=True)
        self.assertEqual([json.loads(line) for line in result.stdout.splitlines()],
                         [evaluator.run(job) for job in jobs])
        failed = subprocess.run([sys.executable, str(DRIVER)], input='["not a job"]\n',
                                text=True, capture_output=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(failed.stdout, "")
        self.assertIn("line 1", failed.stderr)

    def test_computed_index_capacity_is_explicit(self):
        with self.assertRaises(ValueError):
            evaluator.run({"name": "overflow", "term": ["mix", ["bound", 2**53 - 1],
                                                            ["bound", 0]]})


if __name__ == "__main__":
    unittest.main()
