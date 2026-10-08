#!/usr/bin/env python3
"""C-specific boundary tests plus every common conformance fixture.

Run from any directory: python3 conformance/test_c.py
Requires make, pkg-config, a C11 compiler, GMP, and json-c >= 0.15.
"""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "impl/c/evaluator"


def invoke(jobs):
    return subprocess.run([str(BINARY)], input="".join(json.dumps(j) + "\n" for j in jobs),
                          text=True, capture_output=True, check=True)


class CReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["make", "-C", str(ROOT / "impl/c")], check=True)

    def test_common_cases(self):
        cases = json.loads((ROOT / "conformance/cases.json").read_text())
        jobs = [{k: v for k, v in c.items() if k != "expected"} for c in cases]
        results = [json.loads(line) for line in invoke(jobs).stdout.splitlines()]
        self.assertEqual(len(results), len(cases))
        for case, result in zip(cases, results):
            with self.subTest(case=case["name"]):
                self.assertEqual(result, {"name": case["name"], **case["expected"]})

    def test_large_naturals(self):
        # Thousands of bits: not a disguised uint64 implementation.
        a, b = 10**1000 + 9123, 10**333 + 73
        for op, expected in [("multiply", a*b), ("divide", a//b), ("modulo", a%b)]:
            with self.subTest(op=op):
                result = json.loads(invoke([{"name": op, "term":
                    ["binary", op, ["nat", str(a)], ["nat", str(b)]]}]).stdout)
                self.assertEqual(result["term"], ["nat", str(expected)])

    def test_unicode_and_embedded_nul(self):
        for label in ["🦄", "a\0b", "\\ud800"]:
            result = json.loads(invoke([{"name": label, "term": ["label", label]}]).stdout)
            self.assertEqual(result["term"], ["label", label])
            self.assertEqual(result["name"], label)
        result = json.loads(invoke([{"name": "nul-lookup", "term": ["get",
            ["record", [["a", ["nat", "1"]], ["a\0b", ["nat", "2"]]]], "a\0b"]}]).stdout)
        self.assertEqual(result["term"], ["nat", "2"])

    def test_invalid_wire(self):
        malformed = [
            '{"name":"x","term":["label","\\ud800"]}',
            '{"name":"x","term":["label","\\udc00"]}',
            '{"name":"x","term":["label","\\ud800\\u1234"]}',
            '{"name":"x","term":["nat","01"]}',
            '{"name":"x","term":["nat",1]}',
            '{"name":"x","term":["boolean",1]}',
            '{"name":"x","term":["bound",true]}',
            '{"name":"x","term":["bound",9007199254740992]}',
            '{"name":"x","term":["nat\\u0000evil","1"]}',
            '{"name\\u0000bad":"x","term":["nat","1"]}',
            '{"name":"x","term":["lam",["bound",0],0]}',
            '{"name":"x","term":["record",{"x":["nat","1"]}]}',
            '{"name":"x","term":["nat","0"],"fuel":-1}',
            '{"name":"x","term":["nat","0"],"fuel":1.5}',
            '{"name":"x","term":["nat","0"],"responses":[["nat","-1"]]}',
            '{"name":"x","term":["nat","0"],"extra":1}',
            '{"name":"x","term":["nat","0"]}{}',
        ]
        for data in malformed:
            with self.subTest(data=data):
                p = subprocess.run([str(BINARY)], input=data + "\n", text=True, capture_output=True)
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(p.stdout, "")
                self.assertIn("delvetalk-c:", p.stderr)

    def test_invalid_utf8(self):
        for data in [b"\xed\xa0\x80", b"\xc0\xaf", b"\xf4\x90\x80\x80", b"\xff"]:
            with self.subTest(data=data):
                p = subprocess.run([str(BINARY)], input=b'{"name":"x","term":["label","' + data + b'"]}\n', capture_output=True)
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(p.stdout, b"")


if __name__ == "__main__":
    unittest.main()
