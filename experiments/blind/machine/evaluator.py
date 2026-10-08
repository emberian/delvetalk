#!/usr/bin/env python3
"""Blind Objective Bend reconstruction from machine-2k.txt and AST.md only."""
import json
import re
import sys

if hasattr(sys, 'set_int_max_str_digits'):
    sys.set_int_max_str_digits(0)

MAX_INDEX = 2**53 - 1
VALUES = {'lam', 'nat', 'boolean', 'label', 'record', 'specification',
          'prototype', 'inject'}
PRIMITIVES = {'add', 'multiply', 'equal', 'conjunction', 'labelEqual',
              'subtract', 'divide', 'less', 'lessEqual', 'modulo'}
UNARY = {'lam', 'reflect', 'metadata', 'project', 'perform', 'done'}
PAIR = {'app', 'mix', 'fix', 'specification', 'prototype'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scalar_string(value):
    return isinstance(value, str) and all(not 0xD800 <= ord(c) <= 0xDFFF for c in value)


def bounded_int(value):
    return type(value) is int and 0 <= value <= MAX_INDEX


def validate_term(t):
    require(isinstance(t, list) and t and scalar_string(t[0]), 'term must be a tagged array')
    tag = t[0]
    arity = (2 if tag in UNARY | {'bound', 'nat', 'boolean', 'label', 'record'}
             else 3 if tag in PAIR | {'extend', 'get', 'inject', 'case'}
             else 4 if tag in {'binary', 'ifZero', 'ifBool'} else -1)
    require(len(t) == arity, 'unknown constructor or invalid arity: ' + tag)
    if tag == 'bound':
        require(bounded_int(t[1]), 'index outside wire range')
    elif tag == 'nat':
        require(isinstance(t[1], str) and re.fullmatch(r'0|[1-9][0-9]*', t[1]) is not None,
                'invalid natural literal')
    elif tag == 'boolean':
        require(type(t[1]) is bool, 'invalid boolean literal')
    elif tag == 'label':
        require(scalar_string(t[1]), 'invalid label')
    elif tag in UNARY:
        validate_term(t[1])
    elif tag in PAIR:
        validate_term(t[1]); validate_term(t[2])
    elif tag == 'binary':
        require(isinstance(t[1], str) and t[1] in PRIMITIVES, 'unknown primitive')
        validate_term(t[2]); validate_term(t[3])
    elif tag in {'ifZero', 'ifBool'}:
        for child in t[1:]:
            validate_term(child)
    elif tag in {'get', 'inject'}:
        key, child = (t[2], t[1]) if tag == 'get' else (t[1], t[2])
        require(scalar_string(key), 'invalid key')
        validate_term(child)
    elif tag in {'record', 'extend', 'case'}:
        if tag != 'record':
            validate_term(t[1])
        entries = t[1] if tag == 'record' else t[2]
        require(isinstance(entries, list), 'fields/arms must be an array')
        for item in entries:
            require(isinstance(item, list) and len(item) == 2 and scalar_string(item[0]),
                    'invalid field/arm')
            validate_term(item[1])


def map_children(t, visit, depth):
    """Visit every child, adding depth only at the three source binders."""
    tag = t[0]
    if tag in {'bound', 'nat', 'boolean', 'label'}:
        return t[:]
    if tag in UNARY:
        return [tag, visit(t[1], depth + (tag == 'lam'))]
    if tag in PAIR:
        return [tag, visit(t[1], depth), visit(t[2], depth)]
    if tag == 'binary':
        return [tag, t[1], visit(t[2], depth), visit(t[3], depth)]
    if tag in {'ifZero', 'ifBool'}:
        return [tag, visit(t[1], depth), visit(t[2], depth),
                visit(t[3], depth + (tag == 'ifZero'))]
    if tag == 'get':
        return [tag, visit(t[1], depth), t[2]]
    if tag == 'inject':
        return [tag, t[1], visit(t[2], depth)]
    if tag == 'record':
        return [tag, [[k, visit(v, depth)] for k, v in t[1]]]
    return [tag, visit(t[1], depth),
            [[k, visit(v, depth + (tag == 'case'))] for k, v in t[2]]]


def shift(t, amount, cutoff=0):
    if t[0] == 'bound':
        return ['bound', t[1] + amount if t[1] >= cutoff else t[1]]
    return map_children(t, lambda child, d: shift(child, amount, d), cutoff)


def substitute(body, argument, depth=0):
    if body[0] == 'bound':
        i = body[1]
        if i == depth:
            return shift(argument, depth)
        return ['bound', i - 1 if i > depth else i]
    return map_children(body, lambda child, d: substitute(child, argument, d), depth)


def primitive(op, left, right):
    if op == 'conjunction':
        return ['boolean', left[1] and right[1]] if left[0] == right[0] == 'boolean' else None
    if op == 'labelEqual':
        return ['boolean', left[1] == right[1]] if left[0] == right[0] == 'label' else None
    if left[0] != 'nat' or right[0] != 'nat':
        return None
    a, b = int(left[1]), int(right[1])
    if op == 'equal': return ['boolean', a == b]
    if op == 'less': return ['boolean', a < b]
    if op == 'lessEqual': return ['boolean', a <= b]
    if op == 'add': n = a + b
    elif op == 'multiply': n = a * b
    elif op == 'subtract': n = max(0, a - b)
    elif op == 'divide': n = a // b if b else 0
    elif op == 'modulo': n = a % b if b else a
    else: return None
    return ['nat', str(n)]


def observe(t):
    """Return (event, next term or raw plan, retained context frames)."""
    frames = []
    while True:
        tag = t[0]
        if tag in VALUES:
            return 'value', t, frames
        if tag == 'perform':
            return 'yield', t[1], frames
        if tag == 'bound':
            return 'stuck', t, frames
        if tag == 'done':
            return 'step', t[1], frames
        if tag == 'mix':
            a, b = shift(t[1], 2), shift(t[2], 2)
            return 'step', ['lam', ['lam', ['app', ['app', b, ['bound', 1]],
                    ['app', ['app', a, ['bound', 1]], ['bound', 0]]]]], frames
        if tag == 'fix':
            return 'step', ['app', ['app', t[1], t], t[2]], frames
        pos = 2 if tag == 'binary' else 1
        if t[pos][0] not in VALUES:
            frames.append((t, pos)); t = t[pos]; continue
        if tag == 'binary' and t[3][0] not in VALUES:
            frames.append((t, 3)); t = t[3]; continue
        value = t[pos]
        result = None
        if tag == 'app':
            if value[0] == 'lam':
                result = substitute(value[1], t[2])
            elif value[0] == 'specification':
                result = ['app', value[2], t[2]]
        elif tag in {'reflect', 'project'} and value[0] == 'prototype':
            result = value[1 if tag == 'reflect' else 2]
        elif tag == 'metadata' and value[0] == 'specification':
            result = value[1]
        elif tag == 'get' and value[0] == 'record':
            result = next((v for k, v in value[1] if k == t[2]), None)
        elif tag == 'extend' and value[0] == 'record':
            keys = {k for k, _ in t[2]}
            result = ['record', t[2] + [[k, v] for k, v in value[1] if k not in keys]]
        elif tag == 'ifBool' and value[0] == 'boolean':
            result = t[2] if value[1] else t[3]
        elif tag == 'ifZero' and value[0] == 'nat':
            n = int(value[1])
            result = t[2] if n == 0 else substitute(t[3], ['nat', str(n - 1)])
        elif tag == 'case' and value[0] == 'inject':
            body = next((v for k, v in t[2] if k == value[1]), None)
            if body is not None: result = substitute(body, value[2])
        elif tag == 'binary':
            result = primitive(t[1], t[2], t[3])
        return ('stuck', t, frames) if result is None else ('step', result, frames)


def plug(term, frames):
    for parent, position in reversed(frames):
        rebuilt = parent[:]
        rebuilt[position] = term
        term = rebuilt
    return term


def run(job):
    require(isinstance(job, dict), 'job must be an object')
    require(set(job) <= {'name', 'term', 'responses', 'fuel'} and {'name', 'term'} <= set(job),
            'missing or unknown job keys')
    require(scalar_string(job['name']), 'name must be a Unicode scalar string')
    fuel = job.get('fuel', 10000)
    require(bounded_int(fuel), 'invalid fuel')
    responses = job.get('responses', [])
    require(isinstance(responses, list), 'responses must be an array')
    validate_term(job['term'])
    for response in responses: validate_term(response)
    term, plans, cursor = job['term'], [], 0
    while True:
        event, payload, frames = observe(term)
        if event == 'step':
            if fuel == 0:
                status = 'exhausted'; break
            term = plug(payload, frames)
            fuel -= 1
        elif event == 'yield':
            validate_term(payload)
            plans.append(payload)
            if cursor == len(responses):
                status = 'yield'; break
            term = plug(responses[cursor], frames)
            cursor += 1
        else:
            status = event; break
    validate_term(term)
    return {'name': job['name'], 'status': status, 'term': term, 'plans': plans}


def reject_constant(value):
    raise ValueError('non-JSON numeric constant: ' + value)


def main():
    for line_number, line in enumerate(sys.stdin, 1):
        try:
            job = json.loads(line, parse_constant=reject_constant)
            result = run(job)
            print(json.dumps(result, ensure_ascii=True, separators=(',', ':')), flush=True)
        except Exception as exc:
            print(f'line {line_number}: {type(exc).__name__}: {exc}', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
