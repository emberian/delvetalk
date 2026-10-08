#!/usr/bin/env python3
"""Bounded adversarial four-engine checks, seed 0xDE1E7A1C.

Requires built Lean and C executables. This independently generates open and
ill-typed terms, exercises binder substitution and nested yield contexts, and
checks source-derived observations. Differential agreement is not refinement.
"""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINES = {
    'lean': [str(ROOT / '.lake/build/bin/delvetalk')],
    'python': [sys.executable, str(ROOT / 'impl/python/evaluator.py')],
    'js': ['node', str(ROOT / 'impl/js/evaluator.mjs')],
    'c': [str(ROOT / 'impl/c/evaluator')],
}
SEED = 0xDE1E7A1C
PRIMITIVES = ['add', 'multiply', 'equal', 'conjunction', 'labelEqual',
              'subtract', 'divide', 'less', 'lessEqual', 'modulo']
KEYS = ['', 'x', 'x\x00y', '🜉✾', 'e\u0301', 'é']
N = lambda x: ['nat', str(x)]
B = lambda x: ['bound', x]
L = lambda x: ['label', x]


def execute(engine, text):
    return subprocess.run(ENGINES[engine], input=text, text=True,
                          capture_output=True, timeout=30, cwd=ROOT)


def observations(jobs):
    data = ''.join(json.dumps(j, ensure_ascii=True) + '\n' for j in jobs)
    result = {}
    for engine in ENGINES:
        p = execute(engine, data)
        if p.returncode:
            raise AssertionError(f'{engine}: exit {p.returncode}: {p.stderr[:2000]}')
        rows = [json.loads(line) for line in p.stdout.splitlines()]
        if len(rows) != len(jobs):
            raise AssertionError(f'{engine}: {len(rows)} results for {len(jobs)} jobs')
        result[engine] = rows
    return result


def generate(rng, depth):
    if depth <= 0:
        return copy.deepcopy(rng.choice([B(rng.randrange(5)), N(rng.randrange(5)),
                                         ['boolean', bool(rng.randrange(2))],
                                         L(rng.choice(KEYS))]))
    child = lambda: generate(rng, depth - 1)
    fields = lambda: [[rng.choice(KEYS), child()] for _ in range(rng.randrange(4))]
    tag = rng.choice(['leaf', 'lam', 'app', 'mix', 'fix', 'specification',
                      'prototype', 'reflect', 'metadata', 'project', 'binary',
                      'extend', 'record', 'get', 'ifZero', 'inject', 'case',
                      'ifBool', 'perform', 'done'])
    if tag == 'leaf': return generate(rng, 0)
    if tag in ['lam', 'reflect', 'metadata', 'project', 'perform', 'done']:
        return [tag, child()]
    if tag in ['app', 'mix', 'fix', 'specification', 'prototype']:
        return [tag, child(), child()]
    if tag == 'binary': return [tag, rng.choice(PRIMITIVES), child(), child()]
    if tag in ['extend', 'case']: return [tag, child(), fields()]
    if tag == 'record': return [tag, fields()]
    if tag == 'get': return [tag, child(), rng.choice(KEYS)]
    if tag == 'inject': return [tag, rng.choice(KEYS), child()]
    return [tag, child(), child(), child()]


def contexts():
    """Every source congruence position; payloads deliberately contain effects."""
    latent = ['perform', L('latent')]
    return [
        lambda t: ['app', t, latent],
        lambda t: ['get', t, 'x'],
        lambda t: ['extend', t, [['x', latent], ['x', N(8)]]],
        lambda t: ['binary', 'add', t, latent],
        lambda t: ['binary', 'conjunction', ['boolean', False], t],
        lambda t: ['ifZero', t, latent, ['lam', B(1)]],
        lambda t: ['case', t, [['x', ['lam', B(1)]], ['x', latent]]],
        lambda t: ['ifBool', t, latent, N(9)],
        lambda t: ['reflect', t],
        lambda t: ['metadata', t],
        lambda t: ['project', t],
    ]


class AdversarialCore(unittest.TestCase):
    def check_jobs(self, jobs, expected=None):
        rows = observations(jobs)
        for i, job in enumerate(jobs):
            reference = rows['lean'][i]
            for engine in ENGINES:
                self.assertEqual(rows[engine][i], reference,
                    f'{engine}; minimal reproducible JSONL job:\n{json.dumps(job)}')
            if expected is not None:
                self.assertEqual(reference, {'name': job['name'], **expected[i]},
                                 f'source-derived expectation: {job["name"]}')

    def test_nested_yield_contexts(self):
        jobs, expected = [], []
        plan = ['app', ['perform', L('do-not-force')], B(3)]
        for i, outer in enumerate(contexts()):
            for j, inner in enumerate(contexts()):
                term = outer(inner(['perform', plan]))
                # Resuming with another perform is free, even at zero fuel.
                reply = ['perform', ['record', [['x', B(7)]]]]
                jobs.append({'name': f'frames-{i}-{j}', 'term': term,
                             'responses': [reply], 'fuel': 0})
                expected.append({'status': 'yield', 'term': outer(inner(reply)),
                                 'plans': [plan, reply[1]]})
        self.check_jobs(jobs, expected)

    def test_generated_binder_and_context_composition(self):
        rng = random.Random(SEED)
        jobs = []
        for i in range(240):
            term = generate(rng, 4)
            argument = generate(rng, 2)
            # Force substitution through every constructor, including branches
            # which stay lazy. The outer lambda reveals exact residual bodies.
            binder = [
                ['app', ['lam', ['lam', term]], argument],
                ['case', ['inject', 'x', argument], [['x', ['lam', term]]]],
                ['ifZero', N(3), argument, ['lam', term]],
            ][i % 3]
            jobs.append({'name': f'binder-{i}', 'term': binder, 'fuel': 1})
            jobs.append({'name': f'random-{i}', 'term': term,
                         'responses': [argument, generate(rng, 2)],
                         'fuel': rng.choice([0, 1, 2, 7, 16])})
        self.check_jobs(jobs)

    def test_unicode_duplicates_and_capture(self):
        jobs, expected = [], []
        # Extension keeps *all* new duplicates and only unshadowed inherited
        # duplicates; comparison uses full scalar strings, including NUL.
        old = [[k, N(i)] for i, k in enumerate(KEYS + ['x', 'x\x00z'])]
        new = [['x\x00y', N(41)], ['x\x00y', N(42)], ['é', N(43)]]
        term = ['extend', ['record', old], new]
        keys = {k for k, _ in new}
        jobs.append({'name': 'extension-nul-unicode', 'term': term, 'fuel': 1})
        expected.append({'status': 'value', 'term': ['record', new +
                          [f for f in old if f[0] not in keys]], 'plans': []})
        # Lambda, successor and case each add exactly one binding layer.
        body = ['lam', ['ifZero', B(1), B(1),
                        ['case', B(2), [['x', ['record',
                          [['a', B(3)], ['b', B(2)], ['c', B(1)], ['d', B(0)]]]]]]]]
        result = ['lam', ['ifZero', B(5), B(5),
                          ['case', B(6), [['x', ['record',
                            [['a', B(7)], ['b', B(2)], ['c', B(1)], ['d', B(0)]]]]]]]]
        jobs.append({'name': 'three-binders-open-substitution',
                     'term': ['app', ['lam', body], B(4)], 'fuel': 1})
        expected.append({'status': 'value', 'term': result, 'plans': []})
        self.check_jobs(jobs, expected)

    def test_zero_fuel_does_not_contract_overflowing_binders(self):
        maximum = B(2**53 - 1)
        terms = [
            ['mix', maximum, N(0)],
            ['app', ['lam', ['lam', B(1)]], maximum],
            ['case', ['inject', 'x', maximum], [['x', ['lam', B(1)]]]],
        ]
        jobs, expected = [], []
        for i, term in enumerate(terms):
            for j, wrap in enumerate([lambda t: t, *contexts()]):
                residual = wrap(term)
                jobs.append({'name': f'no-contraction-{i}-{j}',
                             'term': residual, 'fuel': 0})
                expected.append({'status': 'exhausted', 'term': residual, 'plans': []})
                jobs.append({'name': f'no-contraction-after-resume-{i}-{j}',
                             'term': wrap(['perform', L('resume')]),
                             'responses': [term], 'fuel': 0})
                expected.append({'status': 'exhausted', 'term': residual,
                                 'plans': [L('resume')]})
        self.check_jobs(jobs, expected)
        # Once a step is authorized, the output would exceed wire capacity.
        # That must be an execution error, not a rounded bound or stuck term.
        for i, term in enumerate(terms):
            job = {'name': f'overflow-after-step-{i}', 'term': term, 'fuel': 1}
            for engine in ENGINES:
                p = execute(engine, json.dumps(job) + '\n')
                self.assertNotEqual(p.returncode, 0, f'{engine}: {job}')
                self.assertFalse(p.stdout.strip(), f'{engine}: {job}')

    def test_malformed_wire_rejected(self):
        valid = {'name': 'malformed', 'term': N(0)}
        cases = [dict(valid, term=['nat', n]) for n in ['', '00', '+1', '-1', '١', '1\n']]
        cases += [dict(valid, term=['bound', n]) for n in [-1, True, 2**53]]
        cases += [dict(valid, term=['boolean', 1]),
                  dict(valid, term=['record', [['x', N(0), N(1)]]]),
                  dict(valid, term=['binary', 'ADD', N(0), N(1)]),
                  dict(valid, responses=[['label', '\ud800']]),
                  dict(valid, responses=[['nat', '01']]),
                  dict(valid, unexpected=0)]
        for job in cases:
            raw = json.dumps(job) + '\n'
            for engine in ENGINES:
                p = execute(engine, raw)
                self.assertNotEqual(p.returncode, 0, f'{engine} accepted {raw}')
                self.assertFalse(p.stdout.strip(), f'{engine} emitted result for malformed job')


if __name__ == '__main__':
    unittest.main()
