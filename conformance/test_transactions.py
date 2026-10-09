#!/usr/bin/env python3
"""Receiving-path checks for the opt-in Lean transaction host and local custody."""
import concurrent.futures
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('transaction_transport', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


def binary(op, left, right):
    return ['bend', ['lam', ['lam', ['binary', op, ['bound', 1], ['bound', 0]]]],
            [left, right]]


def account(balance):
    amount = ['input', 'amount']
    current = ['state', 'balance']
    result = ['record', {'amount': amount, 'by': ['principal']}]
    return {'profile': 'delvetalk-local-v1', 'initial': {'balance': balance}, 'commands': {
        'debit': {'require': [[binary('lessEqual', amount, current), ['literal', True]]],
                  'set': {'balance': binary('subtract', current, amount)},
                  'result': result, 'outbox': [result]},
        'credit': {'require': [], 'set': {'balance': binary('add', current, amount)},
                   'result': result, 'outbox': [result]}}}


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / '.lake/build/bin/delvetalk-transactions').exists(),
                        'Build delvetalk-transactions first; tests must not spawn compilers')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'world.json'
        self.a = self.create('a', account(100))
        self.b = self.create('b', account(20))

    def call(self, request):
        return world.exchange(self.db, request, profile='transactions')

    def create(self, name, protocol, law=None):
        return self.call({'op': 'create', 'object': name, 'principal': 'owner',
                          'intent': 'create-' + name, 'protocol': protocol,
                          'law': ['owner', 'alice'] if law is None else law})['data']['root']

    def inspect(self, name):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'observer'})

    def transfer(self, intent='transfer', amount=7):
        return {'op': 'transaction', 'principal': 'alice', 'intent': intent,
                'reads': {'a': self.a, 'b': self.b}, 'calls': [
                    {'object': 'a', 'command': 'debit', 'input': {'amount': amount}},
                    {'object': 'b', 'command': 'credit', 'inputFrom': 0}]}

    def assert_unchanged(self):
        self.assertEqual(self.inspect('a'), self.a)
        self.assertEqual(self.inspect('b'), self.b)

    def test_transfer_commits_one_receipt_and_ordered_outbox(self):
        receipt = self.call(self.transfer())
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(self.inspect('a')['state']['balance'], 93)
        self.assertEqual(self.inspect('b')['state']['balance'], 27)
        self.assertEqual(receipt['data']['roots'], {'a': self.inspect('a'), 'b': self.inspect('b')})
        self.assertEqual(receipt['data']['results'], [{'amount': 7, 'by': 'alice'}] * 2)
        self.assertEqual(receipt['data']['outbox'], [
            {'object': name, 'step': step, 'payload': {'amount': 7, 'by': 'alice'}}
            for step, name in enumerate(['a', 'b'])])
        stored = world.wire_loads(self.db.read_text())
        self.assertEqual(len(stored['receipts']), 3)  # two creates, one transaction

    def test_stale_any_read_refuses_before_execution_and_is_retained(self):
        request = self.transfer()
        request['reads']['b'] = copy.deepcopy(self.b)
        request['reads']['b']['state']['balance'] = 21
        # Would otherwise fail during the first call: read checks precede execution.
        request['calls'][0]['command'] = 'missing'
        refusal = self.call(request)
        self.assertEqual(refusal['data'], 'stale read root')
        self.assert_unchanged()
        self.assertEqual(self.call(request), refusal)

    def test_unauthorized_second_callee_rolls_back_first(self):
        self.b = self.call({'op': 'law', 'object': 'b', 'principal': 'owner',
                           'intent': 'restrict', 'expected': self.b, 'law': ['owner']})['data']['root']
        request = self.transfer()
        refusal = self.call(request)
        self.assertEqual(refusal['data'], 'unauthorized')
        self.assert_unchanged()
        self.b = self.call({'op': 'law', 'object': 'b', 'principal': 'owner',
                           'intent': 'grant', 'expected': self.b,
                           'law': ['owner', 'alice']})['data']['root']
        self.assertEqual(self.call(request), refusal)
        self.assertEqual(self.call(self.transfer('new-attempt'))['kind'], 'committed')

    def test_late_precondition_and_outbox_failure_discard_everything(self):
        for command in [
            {'require': [[['literal', False], ['literal', True]]], 'set': {},
             'result': ['literal', 0], 'outbox': []},
            {'require': [], 'set': {'balance': ['literal', 0]}, 'result': ['literal', 0],
             'outbox': [['literal', 'earlier'], ['bend', ['perform', ['label', 'bad']], []]]},
        ]:
            with self.subTest(command=command):
                name = 'fail-' + str(len(world.wire_loads(self.db.read_text())['objects']))
                bad = self.create(name, {'profile': 'delvetalk-local-v1',
                    'initial': {'balance': 1}, 'commands': {'fail': command}})
                request = self.transfer(name)
                request['reads'][name] = bad
                request['calls'].append({'object': name, 'command': 'fail', 'input': {}})
                refusal = self.call(request)
                self.assertEqual(refusal['kind'], 'refused')
                self.assertIsInstance(refusal['data'], str)
                self.assert_unchanged()
                self.assertEqual(self.inspect(name), bad)

    def test_repeated_object_reads_staged_state_and_advances_each_version(self):
        request = self.transfer()
        request['calls'][1]['object'] = 'a'
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(self.inspect('a')['state']['balance'], 100)
        self.assertEqual(self.inspect('a')['version'], 2)
        self.assertEqual(self.inspect('b'), self.b)
        # Extra reads are actual guards even if no call touches them.
        stale = self.transfer('read-only-guard')
        stale['calls'] = [stale['calls'][1] | {'input': {'amount': 1}}]
        del stale['calls'][0]['inputFrom']
        self.assertEqual(self.call(stale)['data'], 'stale read root')

    def test_lost_reply_restart_and_changed_identity(self):
        request = self.transfer()
        real_fsync = world.os.fsync
        count = 0
        def fsync(fd):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('injected after replace')
            return real_fsync(fd)
        with mock.patch.object(world.os, 'fsync', side_effect=fsync):
            with self.assertRaisesRegex(OSError, 'injected after replace'):
                self.call(request)
        retained = world.wire_loads(self.db.read_text())['receipts'][-1]['receipt']
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/world.py'),
                               '--profile', 'transactions', str(self.db), '-'],
                              input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(proc.stdout), retained)
        changed = copy.deepcopy(request)
        changed['calls'][0]['input']['amount'] = 8
        self.assertEqual(self.call(changed)['data'], 'intent reused for different request')
        # Historical receipts survive subsequent authority changes.
        self.call({'op': 'law', 'object': 'a', 'principal': 'owner', 'intent': 'lock',
                   'expected': self.inspect('a'), 'law': []})
        self.assertEqual(self.call(request), retained)
        self.assertEqual(self.inspect('b')['version'], 1)

    def test_racing_transfers_preserve_sum_and_single_winner(self):
        def transfer(index):
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/world.py'),
                                   '--profile', 'transactions', str(self.db), '-'],
                input=json.dumps(self.transfer('race-' + str(index), index + 1)),
                text=True, capture_output=True, check=True)
            return json.loads(proc.stdout)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(transfer, range(12)))
        self.assertEqual(sum(r['kind'] == 'committed' for r in outcomes), 1)
        self.assertTrue(all(r['kind'] == 'committed' or r['data'] == 'stale read root'
                            for r in outcomes))
        a, b = self.inspect('a'), self.inspect('b')
        self.assertEqual(a['state']['balance'] + b['state']['balance'], 120)
        self.assertEqual((a['version'], b['version']), (1, 1))

    def test_budget_shared_across_calls(self):
        burn = ['fix', ['lam', ['lam', ['lam', ['ifZero', ['bound', 0], ['nat', '0'],
                ['app', ['bound', 3], ['bound', 0]]]]]], ['record', []]]
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
            'run': {'require': [], 'set': {'done': ['bend', burn, [['literal', 1000]]]},
                    'result': ['literal', {}], 'outbox': []}}}
        first = self.create('burn-a', protocol)
        second = self.create('burn-b', protocol)
        request = {'op': 'transaction', 'principal': 'alice', 'intent': 'too-much',
                   'reads': {'burn-a': first, 'burn-b': second}, 'calls': [
                       {'object': name, 'command': 'run', 'input': {}}
                       for name in ['burn-a', 'burn-b']]}
        self.assertEqual(self.call(request)['data'], 'invocation budget exhausted')
        self.assertEqual(self.inspect('burn-a'), first)
        self.assertEqual(self.inspect('burn-b'), second)
        request['calls'].pop()
        request['intent'] = 'one-fits'
        self.assertEqual(self.call(request)['kind'], 'committed')

    def test_law_step_grants_staged_invocation_and_commits_deliberate_lockout(self):
        self.a = self.call({'op': 'law', 'object': 'a', 'principal': 'owner',
            'intent': 'initial-management-only', 'expected': self.a,
            'law': {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'credit': []},
                    'reprogram': [], 'law': ['alice']}})['data']['root']
        authority = {'profile': 'delvetalk-scoped-law-v1',
                     'invoke': {'credit': ['alice']}, 'reprogram': [], 'law': []}
        request = {'op': 'transaction', 'principal': 'alice', 'intent': 'revise-and-credit',
                   'reads': {'a': self.a}, 'calls': [
                       {'op': 'law', 'object': 'a', 'law': authority},
                       {'object': 'a', 'command': 'credit', 'input': {'amount': 1}}]}
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        current = self.inspect('a')
        self.assertEqual(current['law'], authority)
        self.assertEqual(current['state']['balance'], 101)
        self.assertEqual(current['version'], self.a['version'] + 2)
        self.assertEqual(receipt['data']['results'], [None, {'amount': 1, 'by': 'alice'}])
        self.assertEqual(len(receipt['data']['outbox']), 1)
        self.assertEqual(receipt['data']['outbox'][0]['step'], 1)
        locked = self.call({'op': 'law', 'object': 'a', 'principal': 'owner',
            'intent': 'no-owner-bypass', 'expected': current, 'law': ['owner']})
        self.assertEqual(locked['data'], 'unauthorized')
        self.assertEqual(self.call(request), receipt)  # recovery precedes stale roots/current law
        changed = copy.deepcopy(request)
        changed['calls'][0]['law']['law'] = ['alice']
        self.assertEqual(self.call(changed)['data'], 'intent reused for different request')

    def test_law_revocation_and_later_refusal_roll_back_prior_effects(self):
        request = self.transfer('revoke-inside-batch')
        request['calls'].extend([
            {'op': 'law', 'object': 'a', 'law': []},
            {'object': 'a', 'command': 'credit', 'input': {'amount': 1}}])
        refused = self.call(request)
        self.assertEqual(refused['data'], 'unauthorized')
        self.assert_unchanged()
        self.assertEqual(self.call(request), refused)
        # A final self-lockout can commit; law is not unconditionally rejected.
        request['intent'] = 'final-self-lockout'
        request['calls'].pop()
        self.assertEqual(self.call(request)['kind'], 'committed')
        self.assertEqual(self.inspect('a')['law'], [])

    def test_reprogram_then_law_preserves_staged_program_state_and_permissions(self):
        replacement = account(999)
        authority = {'profile': 'delvetalk-scoped-law-v1',
                     'invoke': {'credit': ['alice']}, 'reprogram': ['owner'], 'law': ['owner']}
        request = {'op': 'transaction', 'principal': 'alice', 'intent': 'program-and-law',
                   'reads': {'a': self.a}, 'calls': [
                       {'op': 'reprogram', 'object': 'a', 'protocol': replacement,
                        'state': {'balance': 7}},
                       {'op': 'law', 'object': 'a', 'law': authority}]}
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        current = self.inspect('a')
        self.assertEqual(current['protocol'], replacement)
        self.assertEqual(current['state'], {'balance': 7})
        self.assertEqual(current['law'], authority)
        self.assertEqual(current['version'], 2)
        self.assertEqual(receipt['data']['results'], [None, None])
        self.assertEqual(receipt['data']['outbox'], [])

    def test_law_checks_old_and_new_invariants_on_staged_state(self):
        common = {'profile': 'delvetalk-scoped-law-v2', 'invoke': {'credit': ['alice']},
                  'reprogram': ['alice'], 'law': ['alice']}
        bound = ['lam', ['binary', 'lessEqual',
                 ['get', ['get', ['bound', 0], 'nextState'], 'balance'], ['nat', '100']]]
        request = {'op': 'transaction', 'principal': 'alice', 'intent': 'bad-new-law',
                   'reads': {'a': self.a}, 'calls': [
                       {'object': 'a', 'command': 'credit', 'input': {'amount': 1}},
                       {'op': 'law', 'object': 'a', 'law': {**common, 'invariant': bound}}]}
        self.assertEqual(self.call(request)['data'], 'state invariant refused')
        self.assert_unchanged()
        no_revision = ['lam', ['ifBool', ['binary', 'labelEqual',
            ['get', ['bound', 0], 'op'], ['label', 'law']], ['boolean', False], ['boolean', True]]]
        fixed = self.create('fixed', account(1), {**common, 'invariant': no_revision})
        request = {'op': 'transaction', 'principal': 'alice', 'intent': 'old-law-still-binds',
                   'reads': {'fixed': fixed}, 'calls': [
                       {'op': 'law', 'object': 'fixed', 'law': ['alice']}]}
        self.assertEqual(self.call(request)['data'], 'state invariant refused')
        self.assertEqual(self.inspect('fixed'), fixed)

    def test_no_implicit_reads_forward_references_or_authority_overrides(self):
        cases = [
            ('missing-read', lambda r: r['reads'].pop('b'), 'missing from read set'),
            ('forward-reference', lambda r: r['calls'][1].update(inputFrom=1), 'earlier call'),
            ('ambiguous-input', lambda r: r['calls'][1].update(input={}), 'exactly one'),
            ('principal-override', lambda r: r['calls'][1].update(principal='owner'), 'unsupported'),
            ('law-operation', lambda r: r['calls'][1].update(op='law', law=['alice']), 'unsupported'),
            ('empty', lambda r: r.update(calls=[]), 'at least one'),
        ]
        for intent, alter, error in cases:
            with self.subTest(intent=intent):
                request = self.transfer(intent)
                alter(request)
                refusal = self.call(request)
                self.assertEqual(refusal['kind'], 'refused')
                self.assertIn(error, refusal['data'])
                self.assert_unchanged()


if __name__ == '__main__':
    unittest.main()
