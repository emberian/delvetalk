#!/usr/bin/env python3
"""Independent reconstruction from algebra-2k.txt and conformance/AST.md."""
import json
import re
import sys

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)

MAX_INDEX = 2**53 - 1
PRIMITIVES = {'add', 'multiply', 'equal', 'conjunction', 'labelEqual',
              'subtract', 'divide', 'less', 'lessEqual', 'modulo'}
VALUES = {'lam', 'nat', 'boolean', 'label', 'record', 'specification',
          'prototype', 'inject'}
UNARY = {'lam', 'reflect', 'metadata', 'project', 'perform', 'done'}
BINARY = {'app', 'mix', 'fix', 'specification', 'prototype'}


def scalar_string(s):
    return isinstance(s, str) and not any(0xD800 <= ord(c) <= 0xDFFF for c in s)


def integer(n):
    return type(n) is int and 0 <= n <= MAX_INDEX


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_pairs(pairs):
    require(isinstance(pairs, list), 'fields/arms must be arrays')
    for pair in pairs:
        require(isinstance(pair, list) and len(pair) == 2, 'invalid field/arm pair')
        require(scalar_string(pair[0]), 'invalid field/arm key')
        validate_term(pair[1])


def validate_term(t):
    require(isinstance(t, list) and t and isinstance(t[0], str), 'invalid term')
    tag = t[0]
    if tag in UNARY:
        require(len(t) == 2, 'wrong unary arity')
        validate_term(t[1])
    elif tag in BINARY:
        require(len(t) == 3, 'wrong binary constructor arity')
        validate_term(t[1]); validate_term(t[2])
    elif tag == 'bound':
        require(len(t) == 2 and integer(t[1]), 'invalid bound index')
    elif tag == 'nat':
        require(len(t) == 2 and isinstance(t[1], str)
                and re.fullmatch(r'0|[1-9][0-9]*', t[1]) is not None, 'invalid Nat')
    elif tag == 'boolean':
        require(len(t) == 2 and type(t[1]) is bool, 'invalid Boolean')
    elif tag == 'label':
        require(len(t) == 2 and scalar_string(t[1]), 'invalid label')
    elif tag == 'record':
        require(len(t) == 2, 'wrong record arity'); validate_pairs(t[1])
    elif tag in {'extend', 'case'}:
        require(len(t) == 3, 'wrong fields/arms constructor arity')
        validate_term(t[1]); validate_pairs(t[2])
    elif tag == 'get':
        require(len(t) == 3 and scalar_string(t[2]), 'invalid get')
        validate_term(t[1])
    elif tag == 'inject':
        require(len(t) == 3 and scalar_string(t[1]), 'invalid inject')
        validate_term(t[2])
    elif tag in {'ifZero', 'ifBool'}:
        require(len(t) == 4, 'wrong conditional arity')
        for child in t[1:]: validate_term(child)
    elif tag == 'binary':
        require(len(t) == 4 and isinstance(t[1], str) and t[1] in PRIMITIVES,
                'invalid primitive')
        validate_term(t[2]); validate_term(t[3])
    else:
        raise ValueError('unknown constructor: ' + tag)


def map_bound(t, replace, depth=0):
    """Traverse all lazy components too, counting precisely the source binders."""
    tag = t[0]
    if tag == 'bound': return replace(t[1], depth)
    if tag in {'nat', 'boolean', 'label'}: return t
    if tag == 'lam': return [tag, map_bound(t[1], replace, depth + 1)]
    if tag == 'ifZero':
        return [tag, map_bound(t[1], replace, depth),
                map_bound(t[2], replace, depth), map_bound(t[3], replace, depth + 1)]
    if tag == 'case':
        return [tag, map_bound(t[1], replace, depth),
                [[k, map_bound(v, replace, depth + 1)] for k, v in t[2]]]
    if tag == 'record':
        return [tag, [[k, map_bound(v, replace, depth)] for k, v in t[1]]]
    if tag == 'extend':
        return [tag, map_bound(t[1], replace, depth),
                [[k, map_bound(v, replace, depth)] for k, v in t[2]]]
    if tag == 'get': return [tag, map_bound(t[1], replace, depth), t[2]]
    if tag == 'inject': return [tag, t[1], map_bound(t[2], replace, depth)]
    if tag == 'binary':
        return [tag, t[1], map_bound(t[2], replace, depth), map_bound(t[3], replace, depth)]
    return [tag] + [map_bound(v, replace, depth) for v in t[1:]]


def shift(t, amount):
    return map_bound(t, lambda n, depth: ['bound', n + amount if n >= depth else n])


def instantiate(body, argument):
    def replace(n, depth):
        if n == depth: return shift(argument, depth)
        return ['bound', n - 1 if n > depth else n]
    return map_bound(body, replace)


def is_value(t): return t[0] in VALUES


def lookup(pairs, key):
    for k, body in pairs:
        if k == key: return body
    return None


def primitive(op, a, b):
    if op == 'conjunction':
        return ['boolean', a[1] and b[1]] if a[0] == b[0] == 'boolean' else None
    if op == 'labelEqual':
        return ['boolean', a[1] == b[1]] if a[0] == b[0] == 'label' else None
    if a[0] != 'nat' or b[0] != 'nat': return None
    x, y = int(a[1]), int(b[1])
    if op == 'equal': return ['boolean', x == y]
    if op == 'less': return ['boolean', x < y]
    if op == 'lessEqual': return ['boolean', x <= y]
    if op == 'add': z = x + y
    elif op == 'multiply': z = x * y
    elif op == 'subtract': z = max(0, x - y)
    elif op == 'divide': z = x // y if y else 0
    elif op == 'modulo': z = x % y if y else x
    else: return None
    return ['nat', str(z)]


def rebuild(root, path, replacement):
    if not path: return replacement
    parents = []
    node = root
    for index in path:
        parents.append((node, index)); node = node[index]
    for parent, index in reversed(parents):
        new_parent = list(parent); new_parent[index] = replacement; replacement = new_parent
    return replacement


def observe(root):
    """Return a source reduction, yield site, or terminal classification."""
    t, path = root, []
    while True:
        tag, reduced, descend = t[0], None, None
        if is_value(t): return 'value', None, None
        if tag == 'perform': return 'yield', t[1], path
        if tag == 'done': reduced = t[1]
        elif tag == 'mix':
            a, b = shift(t[1], 2), shift(t[2], 2)
            s, p = ['bound', 1], ['bound', 0]
            reduced = ['lam', ['lam', ['app', ['app', b, s], ['app', ['app', a, s], p]]]]
        elif tag == 'fix': reduced = ['app', ['app', t[1], ['fix', t[1], t[2]]], t[2]]
        elif tag == 'app':
            if t[1][0] == 'lam': reduced = instantiate(t[1][1], t[2])
            elif t[1][0] == 'specification': reduced = ['app', t[1][2], t[2]]
            elif not is_value(t[1]): descend = 1
        elif tag in {'reflect', 'metadata', 'project'}:
            expected = 'specification' if tag == 'metadata' else 'prototype'
            if t[1][0] == expected: reduced = t[1][2 if tag == 'project' else 1]
            elif not is_value(t[1]): descend = 1
        elif tag == 'get':
            if t[1][0] == 'record': reduced = lookup(t[1][1], t[2])
            elif not is_value(t[1]): descend = 1
        elif tag == 'extend':
            if t[1][0] == 'record':
                keys = {k for k, _ in t[2]}
                reduced = ['record', t[2] + [[k, v] for k, v in t[1][1] if k not in keys]]
            elif not is_value(t[1]): descend = 1
        elif tag == 'ifBool':
            if t[1][0] == 'boolean': reduced = t[2] if t[1][1] else t[3]
            elif not is_value(t[1]): descend = 1
        elif tag == 'ifZero':
            if t[1][0] == 'nat':
                n = int(t[1][1]); reduced = t[2] if n == 0 else instantiate(t[3], ['nat', str(n - 1)])
            elif not is_value(t[1]): descend = 1
        elif tag == 'case':
            if t[1][0] == 'inject':
                body = lookup(t[2], t[1][1])
                if body is not None: reduced = instantiate(body, t[1][2])
            elif not is_value(t[1]): descend = 1
        elif tag == 'binary':
            if not is_value(t[2]): descend = 2
            elif not is_value(t[3]): descend = 3
            else: reduced = primitive(t[1], t[2], t[3])
        if reduced is not None: return 'step', rebuild(root, path, reduced), None
        if descend is None: return 'stuck', None, None
        path.append(descend); t = t[descend]


def run(job):
    require(isinstance(job, dict), 'job must be an object')
    require(set(job) <= {'name', 'term', 'responses', 'fuel'} and {'name', 'term'} <= set(job),
            'missing or unknown job keys')
    require(scalar_string(job['name']), 'name must be a Unicode scalar string')
    term = job['term']; validate_term(term)
    responses = job.get('responses', [])
    require(isinstance(responses, list), 'responses must be an array')
    for response in responses: validate_term(response)
    fuel = job.get('fuel', 10000)
    require(integer(fuel), 'invalid fuel')
    plans, used = [], 0
    while True:
        action, data, path = observe(term)
        if action == 'step':
            if fuel == 0:
                status = 'exhausted'; break
            term = data; fuel -= 1
        elif action == 'yield':
            plans.append(data)
            if used == len(responses):
                status = 'yield'; break
            term = rebuild(term, path, responses[used]); used += 1
        else:
            status = action; break
    validate_term(term)
    for plan in plans: validate_term(plan)
    return {'name': job['name'], 'status': status, 'term': term, 'plans': plans}


def reject_constant(s):
    raise ValueError('non-JSON numeric constant: ' + s)


def main():
    for number, line in enumerate(sys.stdin, 1):
        try:
            job = json.loads(line, parse_constant=reject_constant)
            result = run(job)
            print(json.dumps(result, ensure_ascii=True, separators=(',', ':')), flush=True)
        except Exception as exc:
            print('line {}: {}: {}'.format(number, type(exc).__name__, exc), file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
