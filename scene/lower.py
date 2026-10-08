#!/usr/bin/env python3
"""Compile a pinned Spween parse document into a local Lean-host protocol.

This module compiles syntax. It never decides admission or applies a turn.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

UPSTREAM = "95980f7d1e109138496849a444f28c4b9076a4e2"
PROFILE = "spween-scene-i64-v1"
BIAS = 1 << 63
MAX = (1 << 64) - 1
ROOT = Path(__file__).resolve().parents[1]


class LoweringError(ValueError):
    pass


def n(x): return ["nat", str(x)]
def b(x): return ["boolean", x]
def label(x): return ["label", x]
def var(x): return ["$var", x]
def get(x, key): return ["get", x, key]
def binary(op, x, y): return ["binary", op, x, y]
def iff(c, yes, no): return ["ifBool", c, yes, no]
def negate(c): return iff(c, b(False), b(True))
def both(x, y): return iff(x, y, b(False))
def either(x, y): return iff(x, b(True), y)
def record(fields): return ["record", list(fields.items())]
def extend(x, fields): return ["extend", x, list(fields.items())]
def let(name, value, body): return ["app", ["$lam", name, body], value]
def iskind(value, kind): return binary("labelEqual", get(value, "kind"), label(kind))
def fail(): return get(record({}), "spween-i64-overflow")


def nameless(t, names=()):
    if not isinstance(t, (list, tuple)):
        return t
    if len(t) == 2 and t[0] == "$var" and isinstance(t[1], str):
        return ["bound", names.index(t[1])]
    if len(t) == 3 and t[0] == "$lam" and isinstance(t[1], str):
        return ["lam", nameless(t[2], (t[1],) + names)]
    return [nameless(x, names) for x in t]


def tagged_values(x):
    """Only AST value positions call this; arbitrary prose is never interpreted."""
    if not isinstance(x, list) or not x:
        raise LoweringError("expected tagged Spween value")
    kind = x[0]
    if kind == "null" and len(x) == 1:
        return x
    if len(x) != 2:
        raise LoweringError("invalid tagged Spween value")
    value = x[1]
    if kind == "bool" and type(value) is bool:
        return x
    if kind == "string" and isinstance(value, str):
        return x
    if kind == "int" and isinstance(value, str):
        try:
            integer = int(value)
        except ValueError:
            raise LoweringError("invalid signed decimal integer") from None
        if str(integer) != value or not -BIAS <= integer < BIAS:
            raise LoweringError("integer must be canonical signed i64")
        return x
    if kind == "float":
        raise LoweringError("spween-scene-i64-v1 does not execute Float values; full AST is retained by parsing")
    raise LoweringError("invalid or unsupported tagged Spween value")


class Compiler:
    def __init__(self, document, initial_vars, has):
        if document.get("ok") is not True or document.get("upstream") != UPSTREAM:
            raise LoweringError("requires a successful parse from the pinned Spween revision")
        self.doc = document
        self.ast = document["ast"]
        self.passages = self.ast["passages"]
        self.initial_vars = initial_vars
        self.has = has
        self.variables = set(initial_vars)
        self.strings = set()
        self.counter = 0
        self.names = {p["name"]: i for i, p in enumerate(self.passages)}
        if len(self.names) != len(self.passages):
            raise LoweringError("duplicate passage names are outside this executable profile")
        if any(not isinstance(k, str) for k in initial_vars):
            raise LoweringError("initial variable names must be strings")
        if any(not isinstance(k, str) or not isinstance(v, list) or
               any(not isinstance(item, str) for item in v) for k, v in has.items()):
            raise LoweringError("has must map categories to arrays of string keys")
        for value in initial_vars.values(): self.collect_value(value)
        self.collect_condition(self.ast["meta"].get("requires"))
        for passage in self.passages:
            for item in passage["content"]:
                if item["kind"] == "choice":
                    self.collect_condition(item.get("condition"))
                    for effect in item["effects"]: self.collect_effect(effect)
                    target = item.get("target")
                    if target and not target["is_end"] and target["target"] not in self.names:
                        raise LoweringError("unknown passage target: " + target["target"])
                elif item["kind"] == "effect":
                    self.collect_effect(item["effect"])
        self.ranks = {s: i for i, s in enumerate(sorted(self.strings))}

    def fresh(self):
        self.counter += 1
        return "v" + str(self.counter)

    def collect_value(self, value):
        tagged_values(value)
        if value[0] == "string": self.strings.add(value[1])

    def collect_effect(self, e):
        if e["kind"] == "set":
            self.variables.add(e["var"])
            self.collect_value(e["value"])
        elif e["kind"] == "modify":
            self.variables.add(e["var"])
            tagged_values(["int", e["delta"]])
        elif e["kind"] == "call":
            for value in e["args"]: self.collect_value(value)
        else:
            raise LoweringError("unknown effect kind")

    def collect_condition(self, condition):
        if condition is None: return
        def expr(e):
            if e[0] == "atom": clause(e[1])
            elif e[0] in ("and", "or"):
                expr(e[1]); expr(e[2])
            else: raise LoweringError("unknown condition expression")
        def clause(c):
            if c["kind"] == "compare":
                self.variables.add(c["var"]); self.collect_value(c["value"])
            elif c["kind"] == "not": clause(c["clause"])
            elif c["kind"] != "has": raise LoweringError("unknown condition clause")
        expr(condition["expr"])

    def encode(self, value):
        tagged_values(value)
        kind = value[0]
        if kind == "null": return {"kind": "null"}
        if kind == "int": return {"kind": "int", "value": int(value[1]) + BIAS}
        if kind == "string":
            return {"kind": "string", "value": self.ranks[value[1]], "text": value[1]}
        return {"kind": "bool", "value": value[1]}

    def constant(self, value):
        def core(x):
            if isinstance(x, dict): return record({k: core(v) for k, v in x.items()})
            if type(x) is bool: return b(x)
            if type(x) is int: return n(x)
            return label(x)
        return core(self.encode(value))

    def condition(self, condition, variables):
        if condition is None: return b(True)
        def expr(e):
            if e[0] == "atom": return clause(e[1])
            if e[0] == "and": return both(expr(e[1]), expr(e[2]))
            return either(expr(e[1]), expr(e[2]))
        def clause(c):
            if c["kind"] == "has":
                return b(c["key"] in self.has.get(c["category"], []))
            if c["kind"] == "not": return negate(clause(c["clause"]))
            left = get(variables, c["var"])
            right = c["value"]
            kind = right[0]
            op = c["op"]
            if op in ("eq", "ne"):
                if kind == "null": equal = iskind(left, "null")
                elif kind == "string":
                    equal = both(iskind(left, "string"),
                                 binary("labelEqual", get(left, "text"), label(right[1])))
                elif kind == "bool":
                    equal = iff(iskind(left, "bool"),
                                iff(get(left, "value"), b(right[1]), b(not right[1])),
                                both(iskind(left, "int"), binary("equal", get(left, "value"), n(BIAS + int(right[1])))))
                else:
                    number = int(right[1])
                    equal = iff(iskind(left, "int"), binary("equal", get(left, "value"), n(BIAS + number)),
                                both(iskind(left, "bool"),
                                     iff(get(left, "value"), b(number == 1), b(number == 0))))
                return equal if op == "eq" else negate(equal)
            if kind not in ("int", "string"): return b(False)
            number = BIAS + int(right[1]) if kind == "int" else self.ranks[right[1]]
            a, z = get(left, "value"), n(number)
            if op == "lt": result = binary("less", a, z)
            elif op == "le": result = binary("lessEqual", a, z)
            elif op == "gt": result = binary("less", z, a)
            elif op == "ge": result = binary("lessEqual", z, a)
            else: raise LoweringError("unknown comparison operator")
            return both(iskind(left, kind), result)
        return expr(condition["expr"])

    def effects(self, effects, variables, continuation):
        if not effects: return continuation(variables)
        effect, rest = effects[0], effects[1:]
        if effect["kind"] == "call": return self.effects(rest, variables, continuation)
        key = effect["var"]
        guard = b(True)
        if effect["kind"] == "set": value = self.constant(effect["value"])
        else:
            delta = int(effect["delta"])
            old = get(variables, key)
            integer = get(old, "value")
            if delta >= 0:
                shifted = binary("add", integer, n(delta))
                valid = binary("lessEqual", shifted, n(MAX))
            else:
                shifted = binary("subtract", integer, n(-delta))
                valid = binary("lessEqual", n(-delta), integer)
            guard = iff(iskind(old, "int"), valid, b(True))
            value = iff(iskind(old, "int"), record({"kind": label("int"), "value": shifted}),
                        iff(iskind(old, "null"), self.constant(["int", str(delta)]), old))
        name = self.fresh()
        # The outer conditional forces every checked modification, even when a
        # later assignment overwrites that field in a lazy record.
        return iff(guard, let(name, extend(variables, {key: value}),
                             self.effects(rest, var(name), continuation)), fail())

    def entry(self, index):
        return [c["effect"] for c in self.passages[index]["content"] if c["kind"] == "effect"]

    def choices(self, index):
        return [c for c in self.passages[index]["content"] if c["kind"] == "choice"]

    def sequence(self, values):
        return record({"length": n(len(values)), "items": record({str(i): x for i, x in enumerate(values)})})

    def calls(self, effects):
        return [record({"name": label(e["name"]),
                        "args": self.sequence([self.constant(a) for a in e["args"]])})
                for e in effects if e["kind"] == "call"]

    def session(self, variables, visited, index, ended):
        choices = [] if ended else [record({"index": n(i), "text": label(c["text"]),
                                            "available": self.condition(c.get("condition"), variables)})
                                   for i, c in enumerate(self.choices(index))]
        return record({"vars": variables, "visited": visited, "passage": n(index),
                       "started": b(True), "ended": b(ended), "choices": self.sequence(choices),
                       "requirements": self.condition(self.ast["meta"].get("requires"), variables)})

    def bend(self, body):
        return ["bend", nameless(["$lam", "session", body]), [["state", "session"]]]

    def command(self, origin=None, choice_index=None):
        session = var("session")
        variables = get(session, "vars")
        visited = get(session, "visited")
        start = origin is None
        if start:
            guard = negate(get(session, "started"))
            target = 0
            ended = not self.passages
            effects = []
        else:
            choice = self.choices(origin)[choice_index]
            guard = both(get(session, "started"), both(negate(get(session, "ended")),
                     both(binary("equal", get(session, "passage"), n(origin)),
                          self.condition(choice.get("condition"), variables))))
            nav = choice.get("target")
            ended = nav is None or nav["is_end"]
            target = origin if ended else self.names[nav["target"]]
            effects = choice["effects"]
        entry_effects = [] if ended else self.entry(target)
        entering = b(False) if ended else negate(get(visited, str(target)))
        new_visited = visited if ended else extend(visited, {str(target): b(True)})
        def finish(v):
            return self.session(v, new_visited, target, ended)
        def after_choice(v):
            return iff(entering, self.effects(entry_effects, v, finish), finish(v))
        transition = self.effects(effects, variables, after_choice)
        own_calls = self.calls(effects)
        call_batch = iff(entering, self.sequence(own_calls + self.calls(entry_effects)), self.sequence(own_calls))
        return {"require": [[self.bend(guard), ["literal", True]]],
                "set": {"session": self.bend(transition)},
                "result": ["literal", {"scene": self.ast["meta"]["id"], "command": "start" if start else f"choose:{origin}:{choice_index}"}],
                "outbox": [["record", {"kind": ["literal", "spween-call-batch"], "calls": self.bend(call_batch)}]]}

    def build(self):
        initial = {name: self.encode(self.initial_vars.get(name, ["null"])) for name in sorted(self.variables)}
        commands = {"start": self.command()}
        for i in range(len(self.passages)):
            for j in range(len(self.choices(i))): commands[f"choose:{i}:{j}"] = self.command(i, j)
        source = self.doc["source"]
        provenance = {"upstream": UPSTREAM, "sourceSha256": hashlib.sha256(source.encode()).hexdigest(),
                      "compilerSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        protocol = {"profile": "delvetalk-local-v1", "name": "spween:" + self.ast["meta"]["id"],
                    "sceneProfile": PROFILE, "provenance": provenance,
                    "initial": {"session": {"vars": initial, "visited": {str(i): False for i in range(len(self.passages))},
                                "passage": 0, "started": False, "ended": not self.passages,
                                "choices": {"length": 0, "items": {}}, "requirements": False}},
                    "commands": commands}
        return {"profile": PROFILE, "source": source, "ast": self.ast, "upstream": UPSTREAM,
                "provenance": provenance, "initialVars": self.initial_vars, "has": self.has, "protocol": protocol}


def lower_document(document, initial_vars=None, has=None):
    return Compiler(document, initial_vars or {}, has or {}).build()


def bridge(request):
    executable = ROOT / "scene/spween-bridge/target/debug/delvetalk-spween"
    if not executable.exists():
        raise LoweringError("build scene/spween-bridge with Cargo before parsing")
    result = subprocess.run([str(executable)], input=json.dumps(request) + "\n", text=True,
                            capture_output=True, check=True, timeout=30)
    return json.loads(result.stdout)


def decode_value(value):
    """Presentation only: decode the profile's records back to Spween wire values."""
    kind = value["kind"]
    if kind == "null": return ["null"]
    if kind == "int": return ["int", str(value["value"] - BIAS)]
    if kind == "bool": return ["bool", value["value"]]
    if kind == "string": return ["string", value["text"]]
    raise LoweringError("unknown encoded value")


def decode_sequence(value):
    return [value["items"][str(i)] for i in range(value["length"])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--state", type=Path, help='JSON {"vars": tagged values, "has": category lists}')
    parser.add_argument("--protocol-only", action="store_true")
    args = parser.parse_args()
    state = json.loads(args.state.read_text()) if args.state else {}
    document = bridge({"op": "parse", "source": args.source.read_bytes().decode("utf-8"), "filename": str(args.source)})
    bundle = lower_document(document, state.get("vars", {}), state.get("has", {}))
    print(json.dumps(bundle["protocol"] if args.protocol_only else bundle, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    try: main()
    except (LoweringError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("scene lowering: " + str(error), file=sys.stderr)
        raise SystemExit(1)
