#!/usr/bin/env python3
"""Standalone transition-algebra interpreter using only the supplied capsule/WIRE."""
import sys
import json

VALUES = {'lam', 'nat', 'boolean', 'label', 'record', 'specification', 'prototype', 'inject'}
OPS = {'add', 'multiply', 'equal', 'subtract', 'divide', 'modulo', 'less', 'lessEqual', 'conjunction', 'labelEqual'}
ARITY = {'bound': 2, 'lam': 2, 'app': 3, 'mix': 3, 'fix': 3,
         'specification': 3, 'prototype': 3, 'reflect': 2, 'metadata': 2,
         'project': 2, 'nat': 2, 'boolean': 2, 'label': 2, 'binary': 4,
         'extend': 3, 'record': 2, 'get': 3, 'ifZero': 4, 'inject': 3,
         'case': 3, 'ifBool': 4, 'perform': 2, 'done': 2}


def field_map(fs, f, depth):
    return [[key, f(body, depth)] for key, body in fs]


def walk(t, depth, on_bound):
    """Apply a bound-variable operation below all (including suspended) binders."""
    tag = t[0]
    if tag == 'bound':
        return on_bound(t[1], depth)
    if tag in {'nat', 'boolean', 'label'}:
        return t
    f = lambda term, d: walk(term, d, on_bound)
    if tag == 'lam':
        return [tag, f(t[1], depth + 1)]
    if tag == 'record':
        return [tag, field_map(t[1], f, depth)]
    if tag in {'extend', 'case'}:
        return [tag, f(t[1], depth), field_map(t[2], f, depth + (tag == 'case'))]
    if tag == 'ifZero':
        return [tag, f(t[1], depth), f(t[2], depth), f(t[3], depth + 1)]
    if tag == 'get':
        return [tag, f(t[1], depth), t[2]]
    if tag == 'inject':
        return [tag, t[1], f(t[2], depth)]
    if tag == 'binary':
        return [tag, t[1], f(t[2], depth), f(t[3], depth)]
    return [tag] + [f(child, depth) for child in t[1:]]


def shift(t, amount):
    return walk(t, 0, lambda i, depth: ['bound', i + amount if i >= depth else i])


def instantiate(body, arg):
    def replace(i, depth):
        if i == depth:
            return shift(arg, depth)
        return ['bound', i - 1 if i > depth else i]
    return walk(body, 0, replace)


def value(t):
    return t[0] in VALUES


def lookup(fs, key):
    for k, term in fs:
        if k == key:
            return term
    return None


def scalar(op, a, b):
    if a[0] == b[0] == 'nat' and op not in {'conjunction', 'labelEqual'}:
        x, y = int(a[1]), int(b[1])
        if op == 'add':
            result = x + y
        elif op == 'multiply':
            result = x * y
        elif op == 'subtract':
            result = max(0, x - y)
        elif op == 'divide':
            result = x // y if y else 0
        elif op == 'modulo':
            result = x % y if y else x
        elif op == 'equal':
            return ['boolean', x == y]
        elif op == 'less':
            return ['boolean', x < y]
        elif op == 'lessEqual':
            return ['boolean', x <= y]
        else:
            return None
        return ['nat', str(result)]
    if op == 'conjunction' and a[0] == b[0] == 'boolean':
        return ['boolean', a[1] and b[1]]
    if op == 'labelEqual' and a[0] == b[0] == 'label':
        return ['boolean', a[1] == b[1]]
    return None


def plug(term, frames):
    for parent, index in reversed(frames):
        parent = list(parent)
        parent[index] = term
        term = parent
    return term


def inspect(root):
    """Return one source step, a suspended perform and zipper, or a terminal state."""
    t, frames = root, []
    while True:
        tag = t[0]
        replacement, child = None, None
        if tag == 'app':
            fn = t[1]
            if fn[0] == 'lam':
                replacement = instantiate(fn[1], t[2])
            elif fn[0] == 'specification':
                replacement = ['app', fn[2], t[2]]
            else:
                child = 1
        elif tag == 'mix':
            a, b = shift(t[1], 2), shift(t[2], 2)
            s, p = ['bound', 1], ['bound', 0]
            replacement = ['lam', ['lam', ['app', ['app', b, s], ['app', ['app', a, s], p]]]]
        elif tag == 'fix':
            replacement = ['app', ['app', t[1], ['fix', t[1], t[2]]], t[2]]
        elif tag in {'reflect', 'metadata', 'project'}:
            required = 'specification' if tag == 'metadata' else 'prototype'
            if t[1][0] == required:
                replacement = t[1][2 if tag == 'project' else 1]
            else:
                child = 1
        elif tag == 'get':
            if t[1][0] == 'record':
                replacement = lookup(t[1][1], t[2])
            else:
                child = 1
        elif tag == 'extend':
            if t[1][0] == 'record':
                keys = {key for key, _ in t[2]}
                replacement = ['record', t[2] + [entry for entry in t[1][1] if entry[0] not in keys]]
            else:
                child = 1
        elif tag == 'ifBool':
            if t[1][0] == 'boolean':
                replacement = t[2] if t[1][1] else t[3]
            else:
                child = 1
        elif tag == 'ifZero':
            if t[1][0] == 'nat':
                n = int(t[1][1])
                replacement = t[2] if n == 0 else instantiate(t[3], ['nat', str(n - 1)])
            else:
                child = 1
        elif tag == 'case':
            if t[1][0] == 'inject':
                arm = lookup(t[2], t[1][1])
                if arm is not None:
                    replacement = instantiate(arm, t[1][2])
            else:
                child = 1
        elif tag == 'done':
            replacement = t[1]
        elif tag == 'binary':
            if not value(t[2]):
                child = 2
            elif not value(t[3]):
                child = 3
            else:
                replacement = scalar(t[1], t[2], t[3])
        elif tag == 'perform':
            return 'yield', root, t[1], frames
        if replacement is not None:
            return 'step', plug(replacement, frames), None, None
        if child is not None:
            frames.append((t, child))
            t = t[child]
            continue
        return ('value' if not frames and value(t) else 'stuck'), root, None, None


def validate(t):
    if not isinstance(t, list) or not t or not isinstance(t[0], str) or t[0] not in ARITY or len(t) != ARITY[t[0]]:
        raise ValueError('invalid term tag or arity')
    tag = t[0]
    if tag == 'bound':
        if type(t[1]) is not int or t[1] < 0:
            raise ValueError('bound index must be a natural number')
    elif tag == 'nat':
        if not isinstance(t[1], str) or not t[1] or any(c not in '0123456789' for c in t[1]):
            raise ValueError('nat must be an unsigned decimal string')
    elif tag == 'boolean':
        if type(t[1]) is not bool:
            raise ValueError('boolean requires bool')
    elif tag == 'label':
        if not isinstance(t[1], str):
            raise ValueError('label requires string')
    elif tag in {'record', 'extend', 'case'}:
        fs = t[1] if tag == 'record' else t[2]
        if not isinstance(fs, list):
            raise ValueError('fields must be a list')
        for entry in fs:
            if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str):
                raise ValueError('invalid field')
            validate(entry[1])
        if tag != 'record':
            validate(t[1])
    elif tag in {'get', 'inject'}:
        key, term = (t[2], t[1]) if tag == 'get' else (t[1], t[2])
        if not isinstance(key, str):
            raise ValueError('key must be string')
        validate(term)
    elif tag == 'binary':
        if not isinstance(t[1], str) or t[1] not in OPS:
            raise ValueError('unknown scalar operator')
        validate(t[2])
        validate(t[3])
    else:
        for term in t[1:]:
            validate(term)


def evaluate(job):
    if not isinstance(job, dict) or not isinstance(job.get('name'), str) or 'term' not in job:
        raise ValueError('job requires name and term')
    term = job['term']
    responses, fuel = job.get('responses', []), job.get('fuel', 10000)
    if not isinstance(responses, list) or type(fuel) is not int or fuel < 0:
        raise ValueError('invalid responses or fuel')
    validate(term)
    for response in responses:
        validate(response)
    plans, reply = [], 0
    while True:
        status, result, plan, frames = inspect(term)
        if status == 'step':
            if fuel == 0:
                status = 'exhausted'
                break
            fuel -= 1
            term = result
        elif status == 'yield':
            plans.append(plan)
            if reply == len(responses):
                break
            term = plug(responses[reply], frames)
            reply += 1
        else:
            break
    return {'name': job['name'], 'status': status, 'term': term, 'plans': plans}


def main():
    # The capsule specifies unbounded naturals; Python's decimal safety cap is finite.
    if hasattr(sys, 'set_int_max_str_digits'):
        sys.set_int_max_str_digits(0)
    sys.setrecursionlimit(100000)
    for line_number, line in enumerate(sys.stdin, 1):
        try:
            job = json.loads(line)
            result = evaluate(job)
            print(json.dumps(result, ensure_ascii=False, separators=(',', ':')), flush=True)
        except Exception as error:
            print(f'line {line_number}: {type(error).__name__}: {error}', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
