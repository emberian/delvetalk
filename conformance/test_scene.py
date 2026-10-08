#!/usr/bin/env python3
"""Actual pinned Spween runtime versus compiled programs inside Lean admission."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lower = load("scene_lower", "scene/lower.py")
world = load("scene_world", "scripts/world.py")


def scene(body):
    return "---\nid: test\ntitle: Test\nweight: 1\ncooldown: 0\n---\n\n" + body


class SceneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "world.json"
        self.serial = 0

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, source, state=None):
        state = state or {}
        parsed = lower.bridge({"op": "parse", "source": source})
        self.assertTrue(parsed["ok"], parsed)
        bundle = lower.lower_document(parsed, state.get("vars"), state.get("has"))
        self.assertEqual(bundle["source"], source)
        self.assertEqual(bundle["ast"], parsed["ast"])
        response = world.exchange(self.db, {"op": "create", "object": "scene", "principal": "owner",
                                "intent": "create", "protocol": bundle["protocol"], "law": ["player"]})
        self.assertEqual(response["kind"], "committed", response)
        self.root = response["data"]["root"]
        self.calls = []
        return bundle

    def invoke(self, command, **changes):
        self.serial += 1
        request = {"op": "invoke", "object": "scene", "principal": "player", "intent": str(self.serial),
                   "expected": self.root, "command": command, "input": {}}
        request.update(changes)
        response = world.exchange(self.db, request)
        if response["kind"] == "committed":
            self.root = response["data"]["root"]
            for batch in response["data"]["outbox"]:
                self.assertEqual(batch["kind"], "spween-call-batch")
                self.calls.extend({"name": c["name"], "args": [lower.decode_value(a) for a in lower.decode_sequence(c["args"])]}
                                  for c in lower.decode_sequence(batch["calls"]))
        return response, request

    def compare(self, snapshot):
        session = self.root["state"]["session"]
        actual_vars = {k: lower.decode_value(v) for k, v in session["vars"].items()}
        expected_vars = {k: snapshot["vars"].get(k, ["null"]) for k in actual_vars}
        self.assertEqual(actual_vars, expected_vars)
        self.assertEqual(self.calls, snapshot["calls"])
        self.assertEqual(session["ended"], snapshot["state"]["kind"] == "ended")
        if not session["ended"]: self.assertEqual(session["passage"], snapshot["state"]["index"])
        self.assertEqual(lower.decode_sequence(session["choices"]), snapshot["choices"])
        self.assertEqual(session["requirements"], snapshot["requirements"])

    def replay(self, source, actions, state=None):
        oracle = lower.bridge({"op": "replay", "source": source, "state": state or {},
                               "actions": [{"choose": i} for i in actions]})
        self.assertTrue(oracle["ok"], oracle)
        self.install(source, state)
        response, _ = self.invoke("start")
        self.assertEqual(response["kind"], "committed", response)
        self.compare(oracle["trace"][0]["snapshot"])
        for i, step in zip(actions, oracle["trace"][1:]):
            passage = self.root["state"]["session"]["passage"]
            response, _ = self.invoke(f"choose:{passage}:{i}")
            self.assertEqual(response["kind"] == "committed", step["ok"], (response, step))
            self.compare(step["snapshot"])

    def test_branching_reentry_signed_values_and_ordered_outbox(self):
        source = (ROOT / "scene/examples/door.scene").read_text()
        self.replay(source, [0, 0, 0, 0, 0, 1, 1])
        self.assertEqual(lower.decode_value(self.root["state"]["session"]["vars"]["tokens"]), ["int", "0"])
        self.assertEqual([c["args"][0][1] for c in self.calls].count("the door opens"), 1)

    def test_ordered_modify_set_and_missing_non_numeric_values(self):
        source = scene('''=== intro
~ score = -2
~ score += 1
~ score += 4
~ word = "old"
~ word -= 9
* [Go] { score == 3 }
  ~ score -= 8
  ~ score = -11
  ~ score += 2
  ~ missing -= 3
  ~ flag += 2
  ~ notify "first" -9 true null
  ~ notify "second"
  -> END
''')
        self.replay(source, [0], {"vars": {"flag": ["bool", True]}})

    def test_conditions_against_runtime_across_value_kinds(self):
        # Distinct requests go through the parser and actual runtime. This
        # checks coercion and ordering, rather than restating expected booleans.
        values = [["null"], ["bool", False], ["bool", True], ["int", "-2"],
                  ["int", "0"], ["int", "1"], ["string", "ä"], ["string", "a"]]
        literals = ["null", "false", "true", "-2", "0", "1", '"ä"', '"z"']
        for vi, value in enumerate(values):
            for op in ("==", "!=", "<", "<=", ">", ">="):
                with self.subTest(value=value, op=op):
                    self.db = Path(self.tmp.name) / f"condition-{vi}-{op.replace('=', 'e').replace('<', 'l').replace('>', 'g').replace('!', 'n')}.json"
                    source = scene("=== intro\n" + "\n".join(
                        f"* [Check {i}] {{ value {op} {literal} }}\n  -> END" for i, literal in enumerate(literals)))
                    self.replay(source, [], {"vars": {"value": value}})

    def test_membership_negation_boolean_combinations_and_requirements(self):
        source = '''---
id: conditions
title: Conditions
weight: 1
cooldown: 0
requires: "ready == true"
---
=== intro
~ ready = false
* [Use key] { inventory.key && !inventory.missing || ready == true }
  -> END
* [Unavailable] { ready && inventory.key }
  -> END
'''
        self.replay(source, [1, 0], {"has": {"inventory": ["key"]}})

    def test_atomic_overflow_even_if_later_overwritten(self):
        source = scene('''=== intro
* [Overflow]
  ~ number += 1
  ~ number = 0
  ~ notify "must not escape"
  -> END
''')
        self.install(source, {"vars": {"number": ["int", str((1 << 63) - 1)]}})
        self.assertEqual(self.invoke("start")[0]["kind"], "committed")
        before = copy.deepcopy(self.root)
        response, request = self.invoke("choose:0:0")
        self.assertEqual(response["kind"], "refused")
        self.assertEqual(world.exchange(self.db, {"op": "inspect", "object": "scene", "principal": "any"}), before)
        self.assertEqual(world.exchange(self.db, request), response)
        self.assertEqual(self.calls, [])
        oracle = lower.bridge({"op": "replay", "source": source,
                               "state": {"vars": {"number": ["int", str((1 << 63) - 1)]}},
                               "actions": [{"choose": 0}]})
        self.assertFalse(oracle["ok"])
        self.assertEqual(oracle["stage"], "upstream-panic")

    def test_underflow_and_full_signed_boundaries(self):
        source = scene('''=== intro
* [Underflow]
  ~ number -= 1
  -> END
* [In range]
  ~ number += 1
  -> END
''')
        self.install(source, {"vars": {"number": ["int", str(-(1 << 63))], "$lam": ["null"], "$var": ["null"]}})
        self.assertEqual(self.invoke("start")[0]["kind"], "committed")
        self.assertEqual(self.invoke("choose:0:0")[0]["kind"], "refused")
        self.assertEqual(self.invoke("choose:0:1")[0]["kind"], "committed")
        self.assertEqual(lower.decode_value(self.root["state"]["session"]["vars"]["number"]), ["int", str(-(1 << 63) + 1)])

    def test_receipt_retry_stale_root_authority_and_start_once(self):
        self.install((ROOT / "scene/examples/door.scene").read_text())
        initial = copy.deepcopy(self.root)
        response, request = self.invoke("start")
        self.assertEqual(response["kind"], "committed")
        recovered = subprocess.run(["python3", str(ROOT / "scripts/world.py"), str(self.db), "-"],
                                   input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(recovered.stdout), response)
        self.assertEqual(self.invoke("start")[0]["kind"], "refused")
        self.assertEqual(self.invoke("choose:0:0", expected=initial)[0]["data"], "stale read root")
        self.assertEqual(self.invoke("choose:0:0", principal="stranger")[0]["data"], "unauthorized")
        self.assertEqual(self.invoke("choose:1:0")[0]["kind"], "refused")
        self.assertEqual(len(self.calls), 1)

    def test_explicit_unsupported_and_target_diagnostics(self):
        for body, expected in [('=== intro\n~ x = 1.5\n', "Float"),
                               ('=== intro\n* [Go]\n  -> missing\n', "unknown passage")]:
            parsed = lower.bridge({"op": "parse", "source": scene(body)})
            self.assertTrue(parsed["ok"], parsed)
            with self.assertRaisesRegex(lower.LoweringError, expected): lower.lower_document(parsed)
        parsed = lower.bridge({"op": "parse", "source": scene("=== intro\nHello.\n")})
        with self.assertRaisesRegex(lower.LoweringError, "Float"):
            lower.lower_document(parsed, {"x": ["float", "3ff0000000000000"]})
        parsed["upstream"] = "unknown"
        with self.assertRaisesRegex(lower.LoweringError, "pinned"):
            lower.lower_document(parsed)

    def test_cli_retains_exact_utf8_source_and_newlines(self):
        source = scene("=== intro\nA door: 🜉✾\n* [Go]\n  -> END\n").replace("\n", "\r\n")
        path = Path(self.tmp.name) / "unicode.scene"
        path.write_bytes(source.encode("utf-8"))
        process = subprocess.run(["python3", str(ROOT / "scene/lower.py"), str(path)],
                                 capture_output=True, text=True, check=True)
        bundle = json.loads(process.stdout)
        self.assertEqual(bundle["source"], source)
        self.assertEqual(bundle["provenance"]["sourceSha256"], hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__": unittest.main()
