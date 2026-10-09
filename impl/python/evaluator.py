#!/usr/bin/env python3
"""Independent, dependency-free tree interpreter for the Objective Bend core.

This consumes the conformance JSON AST, not surface syntax. It implements no
typechecker or host admission. A stuck untyped term is a legitimate result.
"""
import hashlib
import json
import re
import sys

# Python integers implement the source's unbounded Nat (subject to host memory).
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

PRIMITIVES = {"add", "multiply", "equal", "conjunction", "labelEqual",
              "subtract", "divide", "less", "lessEqual", "modulo",
              "textConcat", "textTake", "textDrop", "textSpan", "textBreak"}
UNARY = {"natText", "textLength", "sha256Text"}
VALUES = {"lam", "nat", "boolean", "label", "record", "specification",
          "prototype", "inject"}
MAX_WIRE_INTEGER = 2**53 - 1
ARITIES = {"bound": 2, "lam": 2, "app": 3, "mix": 3, "fix": 3,
           "specification": 3, "prototype": 3, "reflect": 2, "metadata": 2,
           "project": 2, "nat": 2, "boolean": 2, "label": 2, "refuse": 2, "binary": 4,
           "extend": 3, "record": 2, "get": 3, "ifZero": 4, "inject": 3,
           "case": 3, "ifBool": 4, "perform": 2, "done": 2, "toData": 2, "textJoin": 3, "unary": 3}


def valid_string(value):
    return isinstance(value, str) and not any(0xD800 <= ord(c) <= 0xDFFF for c in value)


def validate(term):
    """Reject malformed ASTs; preserve ordered duplicate fields and open terms."""
    if not isinstance(term, list) or not term or not isinstance(term[0], str):
        raise ValueError("term must be a nonempty tagged array")
    tag = term[0]
    if tag not in ARITIES or len(term) != ARITIES[tag]:
        raise ValueError(f"unknown constructor or wrong arity: {tag!r}")
    if tag == "bound":
        if type(term[1]) is not int or not 0 <= term[1] <= MAX_WIRE_INTEGER:
            raise ValueError("bound index must be an integer in 0..2^53-1")
    elif tag == "nat":
        if not isinstance(term[1], str) or not re.fullmatch(r"0|[1-9][0-9]*", term[1]):
            raise ValueError("Nat must be a canonical unsigned decimal string")
    elif tag == "boolean":
        if type(term[1]) is not bool:
            raise ValueError("boolean literal must be a JSON Boolean")
    elif tag in {"label", "refuse"}:
        if not valid_string(term[1]):
            raise ValueError(f"{tag} must be a Unicode scalar string")
    elif tag in {"get", "inject"}:
        key, value = (term[2], term[1]) if tag == "get" else (term[1], term[2])
        if not valid_string(key):
            raise ValueError("key must be a Unicode scalar string")
        validate(value)
    elif tag in {"record", "extend", "case"}:
        fields = term[-1]
        if not isinstance(fields, list):
            raise ValueError("fields/arms must be an ordered array")
        for field in fields:
            if not isinstance(field, list) or len(field) != 2 or not valid_string(field[0]):
                raise ValueError("field/arm must be [string,term]")
            validate(field[1])
        if tag != "record":
            validate(term[1])
    elif tag == "binary":
        if not isinstance(term[1], str) or term[1] not in PRIMITIVES:
            raise ValueError("unknown primitive")
        validate(term[2])
        validate(term[3])
    elif tag == "unary":
        if not isinstance(term[1], str) or term[1] not in UNARY:
            raise ValueError("unknown unary primitive")
        validate(term[2])
    else:
        for child in term[1:]:
            validate(child)
    return term


def walk(term, variable, depth=0):
    """Map variables, tracking all and only the three binding constructs."""
    tag = term[0]
    if tag == "bound":
        return variable(term[1], depth)
    if tag in {"nat", "boolean", "label", "refuse"}:
        return term
    if tag == "lam":
        return [tag, walk(term[1], variable, depth + 1)]
    if tag == "ifZero":
        return [tag, walk(term[1], variable, depth), walk(term[2], variable, depth),
                walk(term[3], variable, depth + 1)]
    if tag in {"record", "extend", "case"}:
        fields = [[key, walk(body, variable, depth + (tag == "case"))]
                  for key, body in term[-1]]
        return [tag, fields] if tag == "record" else [tag, walk(term[1], variable, depth), fields]
    if tag in {"binary", "inject", "unary"}:
        return [tag, term[1], *[walk(child, variable, depth) for child in term[2:]]]
    if tag == "get":
        return [tag, walk(term[1], variable, depth), term[2]]
    return [tag, *[walk(child, variable, depth) for child in term[1:]]]


def shift(term, amount):
    return walk(term, lambda n, depth: ["bound", n + amount if n >= depth else n])


def instantiate(body, argument):
    def variable(index, depth):
        if index < depth:
            return ["bound", index]
        if index == depth:
            return shift(argument, depth)
        return ["bound", index - 1]
    return walk(body, variable)


def prefix_length(text, alphabet, member):
    count = 0
    for c in text:
        if (c in alphabet) != member:
            break
        count += 1
    return count


def primitive(name, left, right):
    if name == "conjunction":
        return ["boolean", left[1] and right[1]] if left[0] == right[0] == "boolean" else None
    if name == "labelEqual":
        return ["boolean", left[1] == right[1]] if left[0] == right[0] == "label" else None
    if name in {"textConcat", "textSpan", "textBreak"}:
        if left[0] != "label" or right[0] != "label":
            return None
        if name == "textConcat":
            return ["label", left[1] + right[1]]
        return ["nat", str(prefix_length(left[1], right[1], name == "textSpan"))]
    if name in {"textTake", "textDrop"}:
        if left[0] != "label" or right[0] != "nat":
            return None
        text, n = left[1], int(right[1])
        size = len(text.encode("utf-8"))
        if name == "textTake":
            return ["label", "" if n == 0 else text if n >= size else text[:n]]
        return ["label", text if n == 0 else "" if n >= size else text[n:]]
    if left[0] != "nat" or right[0] != "nat":
        return None
    a, b = int(left[1]), int(right[1])
    if name == "equal":
        return ["boolean", a == b]
    if name == "less":
        return ["boolean", a < b]
    if name == "lessEqual":
        return ["boolean", a <= b]
    if name == "add":
        n = a + b
    elif name == "multiply":
        n = a * b
    elif name == "subtract":
        n = max(0, a - b)
    elif name == "divide":
        n = a // b if b else 0
    elif name == "modulo":
        n = a % b if b else a
    else:
        return None
    return ["nat", str(n)]


def unary(name, argument):
    if name == "natText" and argument[0] == "nat":
        return ["label", argument[1]]
    if name == "textLength" and argument[0] == "label":
        return ["nat", str(len(argument[1]))]
    if name == "sha256Text" and argument[0] == "label":
        return ["label", hashlib.sha256(argument[1].encode("utf-8")).hexdigest()]
    return None


def join_expansion(items, separator):
    """textJoin's meaning: case on the list, then the fold `go accumulated rest`
    (a fix of four lambdas) appending separator ++ head; the separator sits
    under six binders inside go's cons arm."""
    shifted = shift(separator, 6)
    body = ["case", ["bound", 0], [
        ["nil", ["bound", 2]],
        ["cons", ["app", ["app", ["bound", 4],
                          ["binary", "textConcat", ["bound", 2],
                           ["binary", "textConcat", shifted, ["get", ["bound", 0], "head"]]]],
                  ["get", ["bound", 0], "tail"]]]]]
    go = ["fix", ["lam", ["lam", ["lam", ["lam", body]]]], ["record", []]]
    return ["case", items, [["nil", ["label", ""]],
                            ["cons", ["app", ["app", go, ["get", ["bound", 0], "head"]],
                                      ["get", ["bound", 0], "tail"]]]]]


def focus(term):
    """Return the unique evaluation-position redex and its outer context.

    Context frames store original arrays and child indexes, outermost first.
    No descent through perform, fix, mix, done, or weak-head values.
    """
    frames = []
    while True:
        tag = term[0]
        index = None
        if tag in {"app", "get", "extend", "reflect", "metadata", "project",
                   "ifZero", "ifBool", "case"} and term[1][0] not in VALUES:
            index = 1
        elif tag == "unary" and term[2][0] not in VALUES:
            index = 2
        elif tag == "binary":
            if term[2][0] not in VALUES:
                index = 2
            elif term[3][0] not in VALUES:
                index = 3
        if index is None:
            return term, frames
        frames.append((term, index))
        term = term[index]


def plug(frames, term):
    for parent, index in reversed(frames):
        result = parent.copy()
        result[index] = term
        term = result
    return term


def contract(term):
    """One root reduction, or None. Call only at the evaluation focus."""
    tag = term[0]
    if tag == "app":
        if term[1][0] == "lam":
            return instantiate(term[1][1], term[2])
        if term[1][0] == "specification":
            return ["app", term[1][2], term[2]]
    elif tag == "mix":
        lower, upper = shift(term[1], 2), shift(term[2], 2)
        return ["lam", ["lam", ["app", ["app", upper, ["bound", 1]],
                                ["app", ["app", lower, ["bound", 1]], ["bound", 0]]]]]
    elif tag == "fix":
        return ["app", ["app", term[1], term], term[2]]
    elif tag in {"reflect", "project"} and term[1][0] == "prototype":
        return term[1][1 if tag == "reflect" else 2]
    elif tag == "metadata" and term[1][0] == "specification":
        return term[1][1]
    elif tag == "get" and term[1][0] == "record":
        return next((body for key, body in term[1][1] if key == term[2]), None)
    elif tag == "extend" and term[1][0] == "record":
        keys = {key for key, _ in term[2]}
        return ["record", term[2] + [field for field in term[1][1] if field[0] not in keys]]
    elif tag == "binary":
        return primitive(*term[1:])
    elif tag == "unary":
        return unary(*term[1:])
    elif tag == "ifZero" and term[1][0] == "nat":
        n = int(term[1][1])
        return term[2] if n == 0 else instantiate(term[3], ["nat", str(n - 1)])
    elif tag == "case" and term[1][0] == "inject":
        body = next((body for key, body in term[2] if key == term[1][1]), None)
        return None if body is None else instantiate(body, term[1][2])
    elif tag == "ifBool" and term[1][0] == "boolean":
        return term[2] if term[1][1] else term[3]
    elif tag in {"done", "toData"}:
        return term[1]
    elif tag == "textJoin":
        return join_expansion(term[1], term[2])
    return None


def reducible(term):
    """Recognize a root step without executing it (especially at zero fuel)."""
    tag = term[0]
    if tag in {"mix", "fix", "done", "toData", "textJoin"}:
        return True
    if tag == "app":
        return term[1][0] in {"lam", "specification"}
    if tag in {"reflect", "project"}:
        return term[1][0] == "prototype"
    if tag == "metadata":
        return term[1][0] == "specification"
    if tag == "extend":
        return term[1][0] == "record"
    if tag == "get":
        return term[1][0] == "record" and any(key == term[2] for key, _ in term[1][1])
    if tag == "binary":
        return primitive(*term[1:]) is not None
    if tag == "unary":
        return unary(*term[1:]) is not None
    if tag == "ifZero":
        return term[1][0] == "nat"
    if tag == "ifBool":
        return term[1][0] == "boolean"
    if tag == "case":
        return term[1][0] == "inject" and any(key == term[1][1] for key, _ in term[2])
    return False


def run(job):
    if not isinstance(job, dict) or set(job) - {"name", "term", "responses", "fuel"}:
        raise ValueError("job must contain only name,term,responses,fuel")
    if "term" not in job or not valid_string(job.get("name")):
        raise ValueError("job requires a string name and term")
    term = validate(job["term"])
    responses = job.get("responses", [])
    fuel = job.get("fuel", 10000)
    if not isinstance(responses, list) or type(fuel) is not int or not 0 <= fuel <= MAX_WIRE_INTEGER:
        raise ValueError("responses must be an array; fuel an integer in 0..2^53-1")
    for response in responses:
        validate(response)
    plans, reply = [], 0
    while True:
        if term[0] in VALUES:
            status = "value"
            break
        redex, frames = focus(term)
        if redex[0] == "perform":
            plans.append(redex[1])
            if reply == len(responses):
                status = "yield"
                break
            term = plug(frames, responses[reply])
            reply += 1
            continue
        if fuel == 0:
            status = "exhausted" if reducible(redex) else "stuck"
            break
        reduct = contract(redex)
        if reduct is None:
            status = "stuck"
            break
        term = plug(frames, reduct)
        fuel -= 1
    # Source shifting may grow free indices beyond the interchange capacity.
    # Report an execution error rather than publishing an inexact/out-of-wire AST.
    validate(term)
    for plan in plans:
        validate(plan)
    return {"name": job["name"], "status": status, "term": term, "plans": plans}


def main():
    for line_number, line in enumerate(sys.stdin, 1):
        try:
            result = run(json.loads(line))
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        except (ValueError, RecursionError) as error:
            print(f"line {line_number}: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
