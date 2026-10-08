#!/usr/bin/env python3
"""Exercise the compiled byte-exact Mini checker through DelveTalk's core AST.

Python constructs packets and compares observations; it does not decide typing.
"""
import copy
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / '.lake/build/bin/delvetalk-typed'
NAT = {'tag': 'natural'}
BOOL = {'tag': 'boolean'}
EMPTY = {'tag': 'emptyRow'}
CUSTODY = {'tag': 'custody', 'identity': '17'}
VAR = {'tag': 'variable', 'index': '0'}
N = lambda n: ['nat', str(n)]
B = lambda n: ['bound', n]
FIELD = lambda key, ty, tail=EMPTY: {'tag': 'field', 'name': key, 'member': ty, 'tail': tail}
VARIANT = lambda row: {'tag': 'variant', 'row': row}
ARROW = lambda dom, cod, quantity='unrestricted', reuse='reusable': {
    'tag': 'arrow', 'domain': dom, 'codomain': cod, 'parameter': quantity, 'reuse': reuse}
PLAN = VARIANT(FIELD('write', NAT))
RESPONSE = VARIANT(FIELD('ok', EMPTY, FIELD('no', EMPTY)))
ACTIVITY = {'tag': 'computation', 'plan': PLAN, 'response': RESPONSE, 'result': RESPONSE}
WRITE = ['inject', 'write', N(1)]
PERFORM = ['perform', WRITE]


def ann(path, domain, codomain, quantity='unrestricted', reuse='reusable'):
    return dict(path=path, domain=domain, codomain=codomain, parameter=quantity, reuse=reuse)


def effects(path):
    return [ann(path, PLAN, RESPONSE), ann(path + [0], NAT, PLAN)]


def packet(term, annotations=(), **kw):
    return dict(schema='delvetalk.typed-core.v1', name='test', term=term, types=[],
                annotations=list(annotations), bounds=[], shareableVariables=[],
                rigidVariables=[], **kw)


def binding(ty, quantity):
    return dict(type=ty, quantity=quantity)


def run_jobs(jobs):
    process = subprocess.run([str(CHECKER)], cwd=ROOT, text=True, capture_output=True,
                             input=''.join(json.dumps(j) + '\n' for j in jobs), timeout=30)
    if process.returncode:
        raise AssertionError(process.stderr)
    rows = [json.loads(line) for line in process.stdout.splitlines()]
    if len(rows) != len(jobs):
        raise AssertionError((len(rows), len(jobs), process.stderr))
    return rows


class TypedCore(unittest.TestCase):
    def accepted(self, job, ty=None, uses=None):
        row, = run_jobs([job])
        self.assertEqual(row['status'], 'accepted', row)
        if ty is not None:
            self.assertEqual(row['type'], ty)
        if uses is not None:
            self.assertEqual(row['uses'], uses)
        return row

    def refused(self, job, kind=None):
        row, = run_jobs([job])
        self.assertEqual(row['status'], 'refused', row)
        self.assertEqual(row['diagnostic']['stage'], 'checker')
        if kind:
            self.assertEqual(row['diagnostic']['kind'], kind, row)
        return row

    def test_base_types_and_typed_identity(self):
        self.accepted(packet(['binary', 'less', N(1), N(2)]), BOOL, [])
        self.accepted(packet(['app', ['lam', B(0)], N(7)], [ann([0], NAT, NAT)]), NAT, [])
        self.refused(packet(['binary', 'add', ['label', 'x'], N(1)]), 'typing')
        self.refused(packet(['lam', B(0)]), 'typing')

    def test_quantities_count_real_uses(self):
        duplicate = ['binary', 'add', B(0), B(0)]
        for quantity in ['affine', 'linear']:
            self.refused(packet(duplicate, context=[binding(NAT, quantity)]), 'ownership')
            self.accepted(packet(N(0), context=[binding(NAT, quantity)]), NAT, [0])
            self.accepted(packet(B(0), context=[binding(NAT, quantity)]), NAT, [1])
        self.accepted(packet(duplicate, context=[binding(NAT, 'unrestricted')]), NAT, [2])
        self.refused(packet(B(0), context=[binding(NAT, 'erased')]), 'ownership')
        self.accepted(packet(N(0), context=[binding(NAT, 'erased')]), NAT, [0])

    def test_capture_reuse_and_transitive_custody(self):
        for ty in [CUSTODY, FIELD('secret', CUSTODY),
                   {'tag': 'prototype', 'spec': EMPTY, 'target': CUSTODY},
                   {'tag': 'specification', 'metadata': EMPTY, 'extension': CUSTODY}]:
            with self.subTest(type=ty):
                self.refused(packet(['lam', B(1)], [ann([], NAT, ty)],
                                    context=[binding(ty, 'linear')]), 'typing')
                result = self.accepted(packet(['lam', B(1)], [ann([], NAT, ty, reuse='once')],
                                             context=[binding(ty, 'linear')]),
                                       ARROW(NAT, ty, reuse='once'), [1])
                self.assertFalse(result['shareable'])
        # Even shareable data cannot be captured from an affine outer binder.
        self.refused(packet(['lam', B(1)], [ann([], NAT, NAT)],
                            context=[binding(NAT, 'affine')]), 'ownership')
        self.accepted(packet(['lam', B(1)], [ann([], NAT, NAT)],
                             context=[binding(NAT, 'unrestricted')]), ARROW(NAT, NAT), [1])

    def test_effect_case_and_explicit_done(self):
        activity = ['case', PERFORM, [['ok', ['done', N(1)]], ['no', ['done', N(0)]]]]
        annotations = effects([0]) + [ann([1, 0], PLAN, RESPONSE), ann([1, 1], PLAN, RESPONSE)]
        expected = dict(ACTIVITY, result=NAT)
        row = self.accepted(packet(activity, annotations), expected, [])
        self.assertFalse(row['shareable'])
        self.refused(packet(['case', PERFORM, [['ok', N(1)], ['no', N(0)]]], effects([0])))
        self.accepted(packet(PERFORM, effects([])), ACTIVITY)

    def test_activities_cannot_hide_in_suspended_positions(self):
        cases = [
            (['record', [['next', PERFORM]]], [0], []),
            (['extend', ['record', []], [['next', PERFORM]]], [1, 0], []),
            (['specification', PERFORM, N(0)], [0], []),
            (['specification', N(0), PERFORM], [1], []),
            (['prototype', PERFORM, N(0)], [0], []),
            (['prototype', N(0), PERFORM], [1], []),
            (['app', ['lam', N(0)], PERFORM], [1], [ann([0], ACTIVITY, NAT, 'affine')]),
            (['inject', 'later', PERFORM], [0],
             [ann([], ACTIVITY, VARIANT(FIELD('later', ACTIVITY)))]),
        ]
        for term, path, extra in cases:
            with self.subTest(term=term[0], path=path):
                self.refused(packet(term, effects(path) + extra), 'typing')
        # Same positions with plain values really do check.
        self.accepted(packet(['record', [['next', N(1)]]]), FIELD('next', NAT))
        self.accepted(packet(['app', ['lam', N(0)], N(1)], [ann([0], NAT, NAT, 'affine')]), NAT)

    def test_plan_response_constraints(self):
        self.refused(packet(['perform', N(1)], [ann([], NAT, RESPONSE)]), 'typing')
        self.refused(packet(PERFORM, [ann([], PLAN, ARROW(NAT, NAT)), ann([0], NAT, PLAN)]), 'typing')

    def test_rigid_bounds_are_not_aliases(self):
        bound = FIELD('n', NAT)
        common = dict(bounds=[dict(index=0, type=bound)], shareableVariables=[0])
        # A rigid future row supports lookup of its lower-bound members.
        lookup = packet(['get', B(0), 'n'], context=[binding(VAR, 'unrestricted')])
        lookup.update(common, rigidVariables=[0])
        self.accepted(lookup, NAT, [1])
        missing = copy.deepcopy(lookup)
        missing['term'][2] = 'future'
        self.refused(missing, 'typing')
        # The visible row can construct an alias but cannot manufacture future Self.
        body = ['lam', ['record', [['n', N(1)]]]]
        alias = packet(body, [ann([], NAT, VAR)])
        alias.update(common)
        self.accepted(alias, ARROW(NAT, VAR))
        rigid = copy.deepcopy(alias)
        rigid['rigidVariables'] = [0]
        self.refused(rigid, 'typing')

    def test_false_shareability_premises_and_activity_aliases_refused(self):
        job = packet(B(0), context=[binding(VAR, 'unrestricted')])
        job.update(bounds=[dict(index=0, type=FIELD('secret', CUSTODY))], shareableVariables=[0])
        self.refused(job, 'typing')
        job = packet(N(0))
        job.update(bounds=[dict(index=0, type=ACTIVITY)])
        self.refused(job, 'typing')

    def test_shadowed_custody_cannot_be_laundered_by_row_equality(self):
        # Canonical row equality ignores shadowed second x, but shareability must not.
        clean = FIELD('x', NAT)
        bad = ['record', [['x', N(1)], ['x', B(0)]]]
        job = packet(['app', ['lam', N(0)], bad], [ann([0], clean, NAT)],
                     context=[binding(CUSTODY, 'linear')])
        self.refused(job, 'typing')
        good = copy.deepcopy(job)
        good['term'][2][1][1][1] = N(2)
        good['context'] = []
        self.accepted(good, NAT)

    def test_binder_and_field_annotation_positions(self):
        # record field 0; extend fields under 1; successor body under 2.
        term = ['extend', ['record', [['first', ['lam', B(0)]]]],
                [['second', ['ifZero', N(1), ['lam', B(0)], ['lam', B(1)]]]]]
        anns = [ann([0, 0], NAT, NAT), ann([1, 0, 1], NAT, NAT), ann([1, 0, 2], NAT, NAT)]
        self.accepted(packet(term, anns), FIELD('second', ARROW(NAT, NAT), FIELD('first', ARROW(NAT, NAT))))
        job = packet(term, anns)
        job['annotations'][2] = ann([1, 0, 2, 0], NAT, NAT)
        row, = run_jobs([job])
        self.assertEqual(row['status'], 'error')

    def test_type_tables_share_storage_only(self):
        job = packet(['lam', B(0)], [ann([], {'tag': 'ref', 'index': 0}, NAT)])
        job['types'] = [NAT]
        self.accepted(job, ARROW(NAT, NAT))
        job['types'] = [{'tag': 'ref', 'index': 0}]
        row, = run_jobs([job])
        self.assertEqual(row['status'], 'error')
        self.assertIn('earlier', row['diagnostic']['message'])

    def test_budget_is_a_diagnostic_not_stuck(self):
        job = packet(['lam', B(0)], [ann([], NAT, NAT)], fuel=1)
        self.refused(job, 'budget')
        job['fuel'] = 8
        self.accepted(job, ARROW(NAT, NAT))

    def test_malformed_and_refused_jobs_do_not_abort_batch(self):
        jobs = [packet(N(0)), packet(['bound', -1]), packet(['lam', B(0)]), packet(N(2))]
        rows = run_jobs(jobs)
        self.assertEqual([r['status'] for r in rows], ['accepted', 'error', 'refused', 'accepted'])
        for change in [dict(rigidVariables=[0]), dict(rigidVariables=[0, 0]),
                       dict(annotations=[ann([], NAT, NAT)]), dict(unknown=True),
                       dict(schema='other'), dict(fuel=16385)]:
            job = packet(N(0)); job.update(change)
            row, = run_jobs([job])
            self.assertEqual(row['status'], 'error', row)
        proc = subprocess.run([str(CHECKER)], input='{"name":"\\ud800"}\n{}\n', text=True,
                              capture_output=True, timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual([json.loads(line)['status'] for line in proc.stdout.splitlines()], ['error', 'error'])


if __name__ == '__main__':
    unittest.main()
