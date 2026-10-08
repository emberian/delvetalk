#!/usr/bin/env python3
"""Standalone capsule-derived evaluator; one JSON job per input line."""
import json
import sys

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)
sys.setrecursionlimit(20000)

VALUES = {'lam', 'nat', 'boolean', 'label', 'record',
          'specification', 'prototype', 'inject'}
OPS = {'add', 'multiply', 'equal', 'subtract', 'divide', 'modulo',
       'less', 'lessEqual', 'conjunction', 'labelEqual'}


def map_children(t, f, depth):
    """Map term children with their binder depth; preserve ordered fields."""
    k = t[0]
    if k in {'bound', 'nat', 'boolean', 'label'}:
        return t[:]
    if k == 'lam':
        return [k, f(t[1], depth + 1)]
    if k == 'record':
        return [k, [[key, f(v, depth)] for key, v in t[1]]]
    if k in {'extend', 'case'}:
        return [k, f(t[1], depth),
                [[key, f(v, depth + (k == 'case'))] for key, v in t[2]]]
    if k == 'ifZero':
        return [k, f(t[1], depth), f(t[2], depth), f(t[3], depth + 1)]
    if k == 'binary':
        return [k, t[1], f(t[2], depth), f(t[3], depth)]
    if k == 'get':
        return [k, f(t[1], depth), t[2]]
    if k == 'inject':
        return [k, t[1], f(t[2], depth)]
    return [k] + [f(c, depth) for c in t[1:]]


def shift(t, amount, cutoff=0):
    if t[0] == 'bound':
        return ['bound', t[1] + amount if t[1] >= cutoff else t[1]]
    return map_children(t, lambda c, d: shift(c, amount, d), cutoff)


def substitute(body, arg, depth=0):
    """Remove an enclosing binder and replace its occurrences by arg."""
    if body[0] == 'bound':
        i = body[1]
        if i == depth:
            return shift(arg, depth)
        return ['bound', i - 1 if i > depth else i]
    return map_children(body, lambda c, d: substitute(c, arg, d), depth)


def lookup(fields, key):
    for k, value in fields:
        if k == key:
            return value
    return None


def scalar(op, a, b):
    if a[0] == b[0] == 'nat':
        x, y = int(a[1]), int(b[1])
        if op == 'equal':
            return ['boolean', x == y]
        if op == 'less':
            return ['boolean', x < y]
        if op == 'lessEqual':
            return ['boolean', x <= y]
        if op == 'add':
            n = x + y
        elif op == 'multiply':
            n = x * y
        elif op == 'subtract':
            n = max(0, x - y)
        elif op == 'divide':
            n = x // y if y else 0
        elif op == 'modulo':
            n = x % y if y else x
        else:
            return None
        return ['nat', str(n)]
    if a[0] == b[0] == 'boolean' and op == 'conjunction':
        return ['boolean', a[1] and b[1]]
    if a[0] == b[0] == 'label' and op == 'labelEqual':
        return ['boolean', a[1] == b[1]]
    return None


def action(t):
    """Return (kind, payload, context-plugger). Source steps stay atomic."""
    k = t[0]
    identity = lambda x: x
    def step(result):
        return ('step', result, identity)
    def descend(index):
        kind, payload, plug = action(t[index])
        if kind == 'none':
            return ('none', None, identity)
        def outer(x):
            result = t[:]
            result[index] = plug(x)
            return result
        return (kind, payload, outer)
    if k == 'perform':
        return ('yield', t[1], identity)
    if k == 'done':
        return step(t[1])
    if k == 'mix':
        l, u = shift(t[1], 2), shift(t[2], 2)
        s, p = ['bound', 1], ['bound', 0]
        return step(['lam', ['lam', ['app', ['app', u, s],
                    ['app', ['app', l, s], p]]]])
    if k == 'fix':
        return step(['app', ['app', t[1], t], t[2]])
    if k == 'app':
        if t[1][0] == 'lam':
            return step(substitute(t[1][1], t[2]))
        if t[1][0] == 'specification':
            return step(['app', t[1][2], t[2]])
        return descend(1)
    if k in {'reflect', 'metadata', 'project'}:
        expected = 'specification' if k == 'metadata' else 'prototype'
        if t[1][0] == expected:
            return step(t[1][2 if k == 'project' else 1])
        return descend(1)
    if k == 'get':
        if t[1][0] == 'record':
            result = lookup(t[1][1], t[2])
            return step(result) if result is not None else ('none', None, identity)
        return descend(1)
    if k == 'extend':
        if t[1][0] == 'record':
            keys = {key for key, _ in t[2]}
            return step(['record', t[2] + [f for f in t[1][1] if f[0] not in keys]])
        return descend(1)
    if k == 'ifBool':
        if t[1][0] == 'boolean':
            return step(t[2] if t[1][1] else t[3])
        return descend(1)
    if k == 'ifZero':
        if t[1][0] == 'nat':
            n = int(t[1][1])
            return step(t[2] if n == 0 else substitute(t[3], ['nat', str(n - 1)]))
        return descend(1)
    if k == 'case':
        if t[1][0] == 'inject':
            body = lookup(t[2], t[1][1])
            return step(substitute(body, t[1][2])) if body is not None else ('none', None, identity)
        return descend(1)
    if k == 'binary':
        if t[2][0] not in VALUES:
            return descend(2)
        if t[3][0] not in VALUES:
            return descend(3)
        result = scalar(t[1], t[2], t[3])
        return step(result) if result is not None else ('none', None, identity)
    return ('none', None, identity)


def validate_term(t):
    if not isinstance(t, list) or not t or not isinstance(t[0], str):
        raise ValueError('term must be a tagged array')
    k = t[0]
    lengths = {'bound': 2, 'lam': 2, 'app': 3, 'mix': 3, 'fix': 3,
               'specification': 3, 'prototype': 3, 'reflect': 2, 'metadata': 2,
               'project': 2, 'nat': 2, 'boolean': 2, 'label': 2, 'binary': 4,
               'extend': 3, 'record': 2, 'get': 3, 'ifZero': 4, 'inject': 3,
               'case': 3, 'ifBool': 4, 'perform': 2, 'done': 2}
    if k not in lengths or len(t) != lengths[k]:
        raise ValueError('unknown tag or incorrect term arity')
    if k == 'bound':
        if type(t[1]) is not int or t[1] < 0:
            raise ValueError('bound index must be a natural number')
    elif k == 'nat':
        if not isinstance(t[1], str) or not t[1] or any(c not in '0123456789' for c in t[1]):
            raise ValueError('nat requires an unsigned decimal string')
    elif k == 'boolean':
        if type(t[1]) is not bool:
            raise ValueError('boolean requires a JSON boolean')
    elif k == 'label':
        if not isinstance(t[1], str):
            raise ValueError('label requires a string')
    elif k in {'record', 'extend', 'case'}:
        fields = t[1] if k == 'record' else t[2]
        if not isinstance(fields, list):
            raise ValueError('fields require a list')
        for field in fields:
            if not isinstance(field, list) or len(field) != 2 or not isinstance(field[0], str):
                raise ValueError('field requires a string key and term')
            validate_term(field[1])
        if k != 'record':
            validate_term(t[1])
    elif k == 'binary':
        if not isinstance(t[1], str) or t[1] not in OPS:
            raise ValueError('unknown binary operation')
        validate_term(t[2]); validate_term(t[3])
    elif k in {'get', 'inject'}:
        key_index, term_index = (2, 1) if k == 'get' else (1, 2)
        if not isinstance(t[key_index], str):
            raise ValueError('key must be a string')
        validate_term(t[term_index])
    else:
        for c in t[1:]:
            validate_term(c)


def evaluate(job):
    if not isinstance(job, dict) or not isinstance(job.get('name'), str) or 'term' not in job:
        raise ValueError('job requires name and term')
    t = job['term']
    responses = job.get('responses', [])
    fuel = job.get('fuel', 10000)
    if not isinstance(responses, list) or type(fuel) is not int or fuel < 0:
        raise ValueError('responses must be an array; fuel must be a natural number')
    validate_term(t)
    for r in responses:
        validate_term(r)
    plans, reply_index = [], 0
    while True:
        if t[0] in VALUES:
            status = 'value'
            break
        kind, payload, plug = action(t)
        if kind == 'none':
            status = 'stuck'
            break
        if kind == 'yield':
            plans.append(payload)
            if reply_index == len(responses):
                status = 'yield'
                break
            t = plug(responses[reply_index])
            reply_index += 1
        else:
            if fuel == 0:
                status = 'exhausted'
                break
            t = plug(payload)
            fuel -= 1
    return {'name': job['name'], 'status': status, 'term': t, 'plans': plans}


def main():
    for line_number, line in enumerate(sys.stdin, 1):
        try:
            result = evaluate(json.loads(line))
            print(json.dumps(result, ensure_ascii=False, separators=(',', ':')), flush=True)
        except Exception as exc:
            print('line {}: {}: {}'.format(line_number, type(exc).__name__, exc), file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
