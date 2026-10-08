#!/usr/bin/env python3
"""Independent interpreter reconstructed from rewrite-2k.txt and AST.md only."""

import json
import re
import sys

if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

MAX_INDEX = (1 << 53) - 1
NAT = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
VALUES = {"lam", "nat", "boolean", "label", "record", "specification",
          "prototype", "inject"}
OPS = {"add", "multiply", "equal", "conjunction", "labelEqual",
       "subtract", "divide", "less", "lessEqual", "modulo"}
UNARY = {"lam", "reflect", "metadata", "project", "perform", "done"}
TWO = {"app", "mix", "fix", "specification", "prototype"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scalar_string(value):
    require(isinstance(value, str), "expected a string")
    require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value),
            "strings must contain Unicode scalar values")


def bounded_integer(value):
    require(type(value) is int and 0 <= value <= MAX_INDEX,
            "expected integer in 0..2^53-1 (not Boolean)")


def validate_fields(fields):
    require(isinstance(fields, list), "fields/arms must be arrays")
    for field in fields:
        require(isinstance(field, list) and len(field) == 2,
                "field/arm must be [key, term]")
        scalar_string(field[0])
        validate_term(field[1])


def validate_term(term):
    require(isinstance(term, list) and term and isinstance(term[0], str),
            "term must be a nonempty tagged array")
    tag = term[0]
    arity = (2 if tag in UNARY | {"bound", "nat", "boolean", "label", "record"}
             else 3 if tag in TWO | {"get", "extend", "inject", "case"}
             else 4 if tag in {"binary", "ifZero", "ifBool"} else 0)
    require(arity and len(term) == arity, "unknown constructor or wrong arity")
    if tag == "bound":
        bounded_integer(term[1])
    elif tag == "nat":
        require(isinstance(term[1], str) and NAT.fullmatch(term[1]) is not None,
                "Nat must be a canonical unsigned decimal string")
    elif tag == "boolean":
        require(type(term[1]) is bool, "boolean literal must be a JSON Boolean")
    elif tag == "label":
        scalar_string(term[1])
    elif tag == "record":
        validate_fields(term[1])
    elif tag in UNARY:
        validate_term(term[1])
    elif tag in TWO:
        validate_term(term[1])
        validate_term(term[2])
    elif tag == "get":
        validate_term(term[1])
        scalar_string(term[2])
    elif tag in {"extend", "case"}:
        validate_term(term[1])
        validate_fields(term[2])
    elif tag == "inject":
        scalar_string(term[1])
        validate_term(term[2])
    elif tag == "binary":
        require(isinstance(term[1], str) and term[1] in OPS, "unknown primitive")
        validate_term(term[2])
        validate_term(term[3])
    else:
        for child in term[1:]:
            validate_term(child)


def map_variables(term, visit, depth=0):
    """Traverse every term component, counting exactly the three binder forms."""
    tag = term[0]
    if tag == "bound":
        return visit(term[1], depth)
    if tag in {"nat", "boolean", "label"}:
        return term
    if tag == "lam":
        return [tag, map_variables(term[1], visit, depth + 1)]
    if tag == "record":
        return [tag, [[k, map_variables(t, visit, depth)] for k, t in term[1]]]
    if tag in {"extend", "case"}:
        return [tag, map_variables(term[1], visit, depth),
                [[k, map_variables(t, visit, depth + (tag == "case"))]
                 for k, t in term[2]]]
    if tag == "ifZero":
        return [tag, map_variables(term[1], visit, depth),
                map_variables(term[2], visit, depth),
                map_variables(term[3], visit, depth + 1)]
    if tag == "get":
        return [tag, map_variables(term[1], visit, depth), term[2]]
    if tag == "inject":
        return [tag, term[1], map_variables(term[2], visit, depth)]
    if tag == "binary":
        return [tag, term[1], map_variables(term[2], visit, depth),
                map_variables(term[3], visit, depth)]
    return [tag] + [map_variables(t, visit, depth) for t in term[1:]]


def shift(term, amount):
    if amount == 0:
        return term
    return map_variables(term, lambda i, d: ["bound", i + amount if i >= d else i])


def substitute(body, argument):
    def variable(index, depth):
        if index == depth:
            return shift(argument, depth)
        return ["bound", index - 1 if index > depth else index]
    return map_variables(body, variable)


def lookup(fields, key):
    for candidate, body in fields:
        if candidate == key:
            return body
    return None


def scalar_op(op, left, right):
    lt, rt = left[0], right[0]
    if op == "conjunction" and lt == rt == "boolean":
        return ["boolean", left[1] and right[1]]
    if op == "labelEqual" and lt == rt == "label":
        return ["boolean", left[1] == right[1]]
    if op not in {"conjunction", "labelEqual"} and lt == rt == "nat":
        a, b = int(left[1]), int(right[1])
        if op == "equal":
            return ["boolean", a == b]
        if op == "less":
            return ["boolean", a < b]
        if op == "lessEqual":
            return ["boolean", a <= b]
        result = {"add": lambda: a + b,
                  "multiply": lambda: a * b,
                  "subtract": lambda: max(0, a - b),
                  "divide": lambda: a // b if b else 0,
                  "modulo": lambda: a % b if b else a}[op]()
        return ["nat", str(result)]
    return None


def scalar_types_match(op, left, right):
    expected = "boolean" if op == "conjunction" else "label" if op == "labelEqual" else "nat"
    return left[0] == right[0] == expected


def contraction(term):
    """Return a deferred source reduction; merely detecting one consumes no fuel."""
    tag = term[0]
    if tag == "app":
        fn, arg = term[1:]
        if fn[0] == "lam":
            return lambda: substitute(fn[1], arg)
        if fn[0] == "specification":
            return lambda: ["app", fn[2], arg]
    elif tag == "mix":
        lower, upper = term[1:]
        return lambda: ["lam", ["lam", ["app", ["app", shift(upper, 2), ["bound", 1]],
                                        ["app", ["app", shift(lower, 2), ["bound", 1]], ["bound", 0]]]]]
    elif tag == "fix":
        return lambda: ["app", ["app", term[1], term], term[2]]
    elif tag in {"reflect", "metadata", "project"}:
        expected = "specification" if tag == "metadata" else "prototype"
        if term[1][0] == expected:
            return lambda: term[1][2 if tag == "project" else 1]
    elif tag == "get" and term[1][0] == "record":
        selected = lookup(term[1][1], term[2])
        if selected is not None:
            return lambda: selected
    elif tag == "extend" and term[1][0] == "record":
        def extend():
            keys = {key for key, _ in term[2]}
            return ["record", term[2] + [[key, val] for key, val in term[1][1] if key not in keys]]
        return extend
    elif tag == "ifBool" and term[1][0] == "boolean":
        return lambda: term[2] if term[1][1] else term[3]
    elif tag == "ifZero" and term[1][0] == "nat":
        def natcase():
            value = int(term[1][1])
            return term[2] if value == 0 else substitute(term[3], ["nat", str(value - 1)])
        return natcase
    elif tag == "case" and term[1][0] == "inject":
        selected = lookup(term[2], term[1][1])
        if selected is not None:
            return lambda: substitute(selected, term[1][2])
    elif tag == "done":
        return lambda: term[1]
    elif tag == "binary" and scalar_types_match(term[1], term[2], term[3]):
        return lambda: scalar_op(term[1], term[2], term[3])
    return None


def observe(term):
    frames = []
    focus = term
    while True:
        tag = focus[0]
        if tag == "perform":
            return "yield", focus[1], frames
        reduce = contraction(focus)
        if reduce is not None:
            return "step", reduce, frames
        if tag in VALUES:
            return ("value" if not frames else "stuck"), None, frames
        position = None
        if tag in {"app", "get", "extend", "ifBool", "ifZero", "case", "reflect", "metadata", "project"}:
            position = 1
        elif tag == "binary":
            position = 3 if focus[2][0] in VALUES else 2
        if position is None or focus[position][0] in VALUES:
            return "stuck", None, frames
        frames.append((focus, position))
        focus = focus[position]


def rebuild(focus, frames):
    for parent, position in reversed(frames):
        parent_copy = parent.copy()
        parent_copy[position] = focus
        focus = parent_copy
    return focus


def run(job):
    require(isinstance(job, dict), "job must be an object")
    require(set(job) <= {"name", "term", "responses", "fuel"}, "unknown job key")
    require("name" in job and "term" in job, "name and term are required")
    scalar_string(job["name"])
    validate_term(job["term"])
    responses = job.get("responses", [])
    require(isinstance(responses, list), "responses must be an array")
    for response in responses:
        validate_term(response)
    fuel = job.get("fuel", 10000)
    bounded_integer(fuel)
    term = job["term"]
    plans = []
    response_index = 0
    while True:
        status, payload, frames = observe(term)
        if status == "step":
            if fuel == 0:
                status = "exhausted"
                break
            term = rebuild(payload(), frames)
            fuel -= 1
        elif status == "yield":
            plans.append(payload)
            if response_index == len(responses):
                break
            term = rebuild(responses[response_index], frames)
            response_index += 1
        else:
            break
    # Runtime renaming may exceed the wire's index bound; never emit that AST.
    validate_term(term)
    for plan in plans:
        validate_term(plan)
    return {"name": job["name"], "status": status, "term": term, "plans": plans}


def reject_constant(value):
    raise ValueError("invalid JSON constant: " + value)


def main():
    for line_number, line in enumerate(sys.stdin, 1):
        try:
            job = json.loads(line, parse_constant=reject_constant)
            result = run(job)
            print(json.dumps(result, ensure_ascii=True, separators=(",", ":")), flush=True)
        except Exception as error:
            print(f"line {line_number}: {type(error).__name__}: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
