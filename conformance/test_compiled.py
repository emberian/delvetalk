#!/usr/bin/env python3
"""Compiled host receiving path: source binding, shared fuel, hashes and rollback."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('compiled_transport', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


def source(code, entry='run'):
    return {'modules': [{'name': 'Example', 'source': 'edition ObjectiveBend 1\n' + code}], 'entry': entry}


def protocol(expr):
    return {'profile': 'delvetalk-local-v1', 'initial': {'kept': 'old'}, 'commands': {
        'run': {'require': [], 'set': {'kept': expr}, 'result': ['literal', {}], 'outbox': []}}}


class CompiledTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / '.lake/build/bin/delvetalk-compiled').exists(), 'Build compiled host first')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'world.json'

    def call(self, request, profile='compiled'):
        return world.exchange(self.db, request, profile=profile)

    def create(self, expr, name='example'):
        reply = self.call({'op': 'create', 'object': name, 'principal': 'owner',
            'intent': 'create-' + name, 'protocol': protocol(expr), 'law': ['owner']})
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply['data']['root']

    def invoke(self, root, name='example', intent=None, input=None):
        return {'op': 'invoke', 'object': name, 'principal': 'owner', 'intent': intent or 'run-' + name,
                'expected': root, 'command': 'run', 'input': {} if input is None else input}

    def inspect(self, name='example'):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'public'})

    def test_actual_source_package_executes_and_receipt_replays(self):
        package = source('def run(x: Nat, y: Nat) -> Nat:\n  x + y\n')
        root = self.create(['package', package, [['input', 'x'], ['input', 'y']]])
        request = self.invoke(root, input={'x': 2**80, 'y': 7})
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['root']['state'], {'kept': 2**80 + 7})
        self.assertEqual(self.call(request), receipt)

    def test_invalid_source_unused_command_and_claimed_packet_refuse_installation(self):
        valid = source('def run(x: Nat) -> Nat:\n  x\n')
        for index, candidate in enumerate([valid | {'packet': {}}, valid | {'limits': {'ticks': '1000000'}},
                source('def run(x: Nat) -> Nat:\n  nonexistent(x)\n')]):
            expr = ['package', candidate, [['literal', 1]]]
            p = protocol(['literal', 0])
            p['commands']['unused'] = protocol(expr)['commands']['run']
            receipt = self.call({'op': 'create', 'object': str(index), 'principal': 'owner',
                'intent': str(index), 'protocol': p, 'law': ['owner']})
            self.assertEqual(receipt['kind'], 'refused', receipt)
        self.assertEqual(world.wire_loads(self.db.read_text())['objects'], {})

    def test_default_profile_does_not_accept_extensions_or_gain_extra_budget(self):
        expr = ['sha256', ['literal', ['domain', 1]]]
        request = {'op': 'create', 'object': 'default', 'principal': 'owner', 'intent': 'default',
                   'protocol': protocol(expr), 'law': ['owner']}
        self.assertEqual(self.call(request, profile='world')['kind'], 'refused')
        request.update(object='transactions', intent='transactions')
        self.assertEqual(self.call(request, profile='transactions')['kind'], 'refused')
        request.update(object='default-object', intent='default-object', protocol=protocol(['object']))
        self.assertEqual(self.call(request, profile='world')['kind'], 'refused')

    def test_hash_canonical_bytes_match_python_for_nested_unicode_and_escapes(self):
        values = [[], ['delvetalk.automatafl.commit.v1', 'table', 1, 0, 7, 14, 'nonce'],
                  ['é', '雪', '🜉', '\x00\b\t\n\f\r\x1f', '\\"/'],
                  {'z': [True, False, 2**90], 'a': {'🜉': 'raw', 'é': '\u2028\u2029'}},
                  '\u0001\u000e\u001a', 0, 2**100]
        for index, value in enumerate(values):
            with self.subTest(value=value):
                name = 'hash-' + str(index)
                root = self.create(['sha256', ['literal', value]], name)
                receipt = self.call(self.invoke(root, name))
                self.assertEqual(receipt['kind'], 'committed', receipt)
                encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
                self.assertEqual(receipt['data']['root']['state']['kept'], hashlib.sha256(encoded).hexdigest())

    def test_hash_rejects_ambiguous_data_and_digest_shape_is_strict(self):
        for index, value in enumerate([None, -1, 0.5, [None]]):
            name = 'bad-hash-' + str(index)
            root = self.create(['sha256', ['literal', value]], name)
            self.assertEqual(self.call(self.invoke(root, name))['kind'], 'refused')
            self.assertEqual(self.inspect(name), root)
        for index, (digest, valid) in enumerate([('a' * 64, True), ('0123456789abcdef' * 4, True),
                                               ('A' * 64, False), ('g' * 64, False), ('a' * 63, False),
                                               ('', False), (0, False)]):
            name = 'digest-' + str(index)
            root = self.create(['sha256-valid', ['literal', digest]], name)
            self.assertEqual(self.call(self.invoke(root, name))['data']['root']['state']['kept'], valid)

    def test_receiving_object_identity_separates_clones_and_ignores_input_spoof(self):
        expression = ['sha256', ['array', [['literal', 'object-bound-domain'], ['object']]]]
        first = self.create(expression, 'first-clone')
        second = self.create(expression, 'second-clone')
        self.assertEqual(first, second)  # Equal roots are still distinct object identities.
        expected = lambda name: hashlib.sha256(json.dumps(['object-bound-domain', name],
            separators=(',', ':')).encode()).hexdigest()
        a = self.call(self.invoke(first, 'first-clone', input={'object': 'second-clone'}))
        b = self.call(self.invoke(second, 'second-clone', input={'object': 'first-clone'}))
        self.assertEqual(a['data']['root']['state']['kept'], expected('first-clone'))
        self.assertEqual(b['data']['root']['state']['kept'], expected('second-clone'))
        # The same binding applies independently to each transaction callee.
        request = {'op': 'transaction', 'principal': 'owner', 'intent': 'identities',
            'reads': {'first-clone': a['data']['root'], 'second-clone': b['data']['root']}, 'calls': [
                {'object': name, 'command': 'run', 'input': {'object': 'pretend'}}
                for name in ['first-clone', 'second-clone']]}
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed')
        for name in ['first-clone', 'second-clone']:
            self.assertEqual(receipt['data']['roots'][name]['state']['kept'], expected(name))
        # A caller cannot satisfy an object-bound precondition using spoofed input.
        guarded = protocol(['literal', 'would write'])
        guarded['commands']['run']['require'] = [[expression, ['input', 'digest']]]
        root = self.call({'op': 'create', 'object': 'guarded', 'principal': 'owner',
            'intent': 'guarded-create', 'protocol': guarded, 'law': ['owner']})['data']['root']
        refusal = self.call(self.invoke(root, 'guarded', input={'object': 'first-clone', 'digest': expected('first-clone')}))
        self.assertEqual(refusal['data'], 'precondition failed')
        self.assertEqual(self.inspect('guarded'), root)

    def test_package_argument_failure_rolls_back_earlier_transaction_call(self):
        first = self.create(['literal', 'staged'], 'first')
        second = self.create(['package', source('def run(x: Nat) -> Nat:\n  x\n'), [['input', 'x']]], 'second')
        request = {'op': 'transaction', 'principal': 'owner', 'intent': 'rollback',
            'reads': {'first': first, 'second': second}, 'calls': [
                {'object': 'first', 'command': 'run', 'input': {}},
                {'object': 'second', 'command': 'run', 'input': {'x': []}}]}
        self.assertEqual(self.call(request)['kind'], 'refused')
        self.assertEqual(self.inspect('first'), first)
        self.assertEqual(self.inspect('second'), second)

    def test_package_calls_share_one_budget_and_failure_is_retained(self):
        package = source('def loop(n: Nat) -> Nat:\n  if n == 0n then 0n else loop(n - 1n)\n'
                         'def run(n: Nat) -> Nat:\n  loop(n)\n')
        root = self.create(['package', package, [['input', 'n']]])
        # Calibrate against this actual demand machine, not source reduction cost.
        # 3,000 rounds fit alone but two calls exceed the fixed host 100k budget.
        first = self.call(self.invoke(root, intent='single', input={'n': 3000}))
        self.assertEqual(first['kind'], 'committed', first)
        current = first['data']['root']
        request = {'op': 'transaction', 'principal': 'owner', 'intent': 'double',
            'reads': {'example': current}, 'calls': [
                {'object': 'example', 'command': 'run', 'input': {'n': 3000}},
                {'object': 'example', 'command': 'run', 'input': {'n': 3000}}]}
        refusal = self.call(request)
        self.assertEqual(refusal['kind'], 'refused', refusal)
        self.assertIn('tickExhausted', refusal['data'])
        self.assertEqual(self.inspect(), current)
        self.assertEqual(self.call(request), refusal)


if __name__ == '__main__':
    unittest.main()
