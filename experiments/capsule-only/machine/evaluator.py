#!/usr/bin/env python3
"""Capsule-only weak-head evaluator; reads/writes one JSON object per line."""
import json
import sys

VALUES = {'lam', 'nat', 'boolean', 'label', 'record', 'specification', 'prototype', 'inject'}
OPS = {'add', 'multiply', 'equal', 'subtract', 'divide', 'modulo', 'less', 'lessEqual', 'conjunction', 'labelEqual'}
UNARY = {'lam', 'reflect', 'metadata', 'project', 'perform', 'done'}
BINARY = {'app', 'mix', 'fix', 'specification', 'prototype'}

class Malformed(ValueError):
    pass


def validate(t):
    if not isinstance(t, list) or not t or not isinstance(t[0], str):
        raise Malformed('term must be a tagged array')
    tag = t[0]
    def arity(n):
        if len(t) != n:
            raise Malformed('wrong arity for ' + tag)
    def fields(fs):
        if not isinstance(fs, list):
            raise Malformed('fields must be a list')
        for f in fs:
            if not isinstance(f, list) or len(f) != 2 or not isinstance(f[0], str):
                raise Malformed('invalid field')
            validate(f[1])
    if tag == 'bound':
        arity(2)
        if type(t[1]) is not int or t[1] < 0:
            raise Malformed('invalid bound index')
    elif tag == 'nat':
        arity(2)
        if not isinstance(t[1], str) or not t[1] or any(c not in '0123456789' for c in t[1]):
            raise Malformed('invalid decimal natural')
    elif tag == 'boolean':
        arity(2)
        if type(t[1]) is not bool:
            raise Malformed('invalid boolean')
    elif tag == 'label':
        arity(2)
        if not isinstance(t[1], str):
            raise Malformed('invalid label')
    elif tag in UNARY:
        arity(2)
        validate(t[1])
    elif tag in BINARY:
        arity(3)
        validate(t[1]); validate(t[2])
    elif tag in {'ifZero', 'ifBool'}:
        arity(4)
        for c in t[1:]: validate(c)
    elif tag == 'binary':
        arity(4)
        if t[1] not in OPS: raise Malformed('invalid operation')
        validate(t[2]); validate(t[3])
    elif tag == 'record':
        arity(2); fields(t[1])
    elif tag in {'extend', 'case'}:
        arity(3); validate(t[1]); fields(t[2])
    elif tag == 'get':
        arity(3); validate(t[1])
        if not isinstance(t[2], str): raise Malformed('invalid field key')
    elif tag == 'inject':
        arity(3)
        if not isinstance(t[1], str): raise Malformed('invalid injection key')
        validate(t[2])
    else:
        raise Malformed('unknown tag ' + tag)


def transform(t, variable, depth=0):
    """Visit every term, accounting for the binders specified by WIRE."""
    tag = t[0]
    if tag == 'bound': return variable(t[1], depth)
    if tag in {'nat', 'boolean', 'label'}: return t
    if tag == 'lam': return [tag, transform(t[1], variable, depth + 1)]
    if tag in UNARY: return [tag, transform(t[1], variable, depth)]
    if tag in BINARY: return [tag, transform(t[1], variable, depth), transform(t[2], variable, depth)]
    if tag == 'binary': return [tag, t[1], transform(t[2], variable, depth), transform(t[3], variable, depth)]
    if tag == 'inject': return [tag, t[1], transform(t[2], variable, depth)]
    if tag == 'get': return [tag, transform(t[1], variable, depth), t[2]]
    if tag == 'record': return [tag, [[k, transform(v, variable, depth)] for k, v in t[1]]]
    if tag in {'extend', 'case'}:
        return [tag, transform(t[1], variable, depth), [[k, transform(v, variable, depth + (tag == 'case'))] for k, v in t[2]]]
    if tag in {'ifZero', 'ifBool'}:
        return [tag, transform(t[1], variable, depth), transform(t[2], variable, depth), transform(t[3], variable, depth + (tag == 'ifZero'))]
    raise AssertionError(tag)


def shift(t, amount):
    return transform(t, lambda i, depth: ['bound', i + amount if i >= depth else i])


def substitute(body, argument):
    def variable(i, depth):
        if i == depth: return shift(argument, depth)
        return ['bound', i - 1 if i > depth else i]
    return transform(body, variable)


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
    elif op == 'subtract': z = max(x - y, 0)
    elif op == 'divide': z = x // y if y else 0
    elif op == 'modulo': z = x % y if y else x
    else: return None
    return ['nat', str(z)]


def focus(term):
    """Return (kind, reduct/plan, evaluation-context).

    Frames are (parent term, selected child index), nearest parent last.
    Discovery and congruence traversal cost no source fuel.
    """
    t, context = term, []
    while True:
        tag = t[0]
        if tag in VALUES: return 'value', t, context
        index = None
        if tag == 'app':
            if t[1][0] not in VALUES: index = 1
            elif t[1][0] == 'lam': return 'step', substitute(t[1][1], t[2]), context
            elif t[1][0] == 'specification': return 'step', ['app', t[1][2], t[2]], context
            else: return 'stuck', t, context
        elif tag == 'mix':
            a, b = shift(t[1], 2), shift(t[2], 2)
            s, p = ['bound', 1], ['bound', 0]
            return 'step', ['lam', ['lam', ['app', ['app', b, s], ['app', ['app', a, s], p]]]], context
        elif tag == 'fix':
            return 'step', ['app', ['app', t[1], t], t[2]], context
        elif tag == 'done': return 'step', t[1], context
        elif tag == 'perform': return 'effect', t[1], context
        elif tag in {'reflect', 'metadata', 'project', 'get', 'extend', 'ifZero', 'ifBool', 'case'}:
            if t[1][0] not in VALUES: index = 1
            else:
                v = t[1]
                if tag in {'reflect', 'project'} and v[0] == 'prototype':
                    return 'step', v[1 if tag == 'reflect' else 2], context
                if tag == 'metadata' and v[0] == 'specification': return 'step', v[1], context
                if tag == 'get' and v[0] == 'record':
                    for k, child in v[1]:
                        if k == t[2]: return 'step', child, context
                if tag == 'extend' and v[0] == 'record':
                    keys = {k for k, _ in t[2]}
                    return 'step', ['record', t[2] + [f for f in v[1] if f[0] not in keys]], context
                if tag == 'ifZero' and v[0] == 'nat':
                    n = int(v[1])
                    return 'step', t[2] if n == 0 else substitute(t[3], ['nat', str(n - 1)]), context
                if tag == 'ifBool' and v[0] == 'boolean': return 'step', t[2] if v[1] else t[3], context
                if tag == 'case' and v[0] == 'inject':
                    for k, arm in t[2]:
                        if k == v[1]: return 'step', substitute(arm, v[2]), context
                return 'stuck', t, context
        elif tag == 'binary':
            if t[2][0] not in VALUES: index = 2
            elif t[3][0] not in VALUES: index = 3
            else:
                result = primitive(t[1], t[2], t[3])
                return ('stuck', t, context) if result is None else ('step', result, context)
        else: return 'stuck', t, context
        context.append((t, index))
        t = t[index]


def rebuild(child, context):
    for parent, index in reversed(context):
        parent = list(parent)
        parent[index] = child
        child = parent
    return child


def evaluate(job):
    if not isinstance(job, dict) or not isinstance(job.get('name'), str) or 'term' not in job:
        raise Malformed('job requires name and term')
    term, responses, fuel = job['term'], job.get('responses', []), job.get('fuel', 10000)
    if type(fuel) is not int or fuel < 0: raise Malformed('fuel must be a natural')
    if not isinstance(responses, list): raise Malformed('responses must be a list')
    validate(term)
    for response in responses: validate(response)
    plans, next_response = [], 0
    while True:
        kind, result, context = focus(term)
        if kind in {'value', 'stuck'}:
            status = kind
            break
        if fuel == 0:
            status = 'exhausted'
            break
        fuel -= 1
        if kind == 'effect':
            plans.append(result)
            if next_response == len(responses):
                status = 'yield'
                break
            result = responses[next_response]
            next_response += 1
        term = rebuild(result, context)
    return {'name': job['name'], 'status': status, 'term': term, 'plans': plans}


def main():
    # Python 3.11's decimal conversion limit is incompatible with unbounded Nat.
    if hasattr(sys, 'set_int_max_str_digits'): sys.set_int_max_str_digits(0)
    for line_number, line in enumerate(sys.stdin, 1):
        try:
            job = json.loads(line)
            answer = evaluate(job)
            print(json.dumps(answer, ensure_ascii=False, separators=(',', ':')), flush=True)
        except (ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
            print('line %d: %s' % (line_number, error), file=sys.stderr)
            return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
