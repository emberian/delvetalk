"""Actual receiving fingerprints: canonical bytes, shared work, and factory edits."""
import copy
import hashlib
from native_support import load_script
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    # Independent byte oracle for the finite JSON values used below.
    if isinstance(value, str):
        escapes = {'"': '\\"', '\\': '\\\\', '\n': '\\n', '\r': '\\r'}
        return '"' + ''.join(escapes.get(c, ('\\u%04x' % ord(c)) if ord(c) < 32 else c)
                             for c in value) + '"'
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return '[' + ','.join(map(canonical, value)) + ']'
    return '{' + ','.join(canonical(k) + ':' + canonical(value[k]) for k in sorted(value)) + '}'


class ProgramDigest(unittest.TestCase):
    binary = ROOT / '.lake/build/bin/delvetalk-compiled'

    def setUp(self):
        self.world = {'objects': {}, 'receipts': []}
        self.serial = 0

    def call(self, request, replacements=()):
        encoded = json.dumps({'world': self.world, 'request': request}, ensure_ascii=False)
        for marker, number in replacements:
            encoded = encoded.replace(json.dumps(marker), number)
        result = subprocess.run([str(self.binary)], input=encoded + '\n', text=True,
                                capture_output=True, timeout=30, check=True)
        frame = json.loads(result.stdout)
        self.world = frame['world']
        return frame['reply']

    def install(self, result=None):
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'hash': {
            'require': [], 'set': {}, 'result': result or ['program-digest', ['input', 'value']], 'outbox': []}}}
        reply = self.call({'op': 'create', 'object': 'hash', 'principal': 'owner',
                           'intent': 'create', 'protocol': protocol, 'law': ['owner']})
        self.assertEqual(reply['kind'], 'committed', reply)

    def request(self, value):
        self.serial += 1
        return {'op': 'invoke', 'object': 'hash', 'principal': 'owner',
                'intent': str(self.serial), 'expected': self.world['objects']['hash'],
                'command': 'hash', 'input': {'value': value}}

    def test_canonical_unicode_escapes_large_integer_and_nested_rows(self):
        self.install()
        value = {'z': ['雪🜉', '"\\\b\t\n\f\r\x00\x1f', -12345678901234567890123456789],
                 'a': {'empty': [], 'null': None, 'yes': True}}
        reply = self.call(self.request(value))
        self.assertEqual(reply['kind'], 'committed', reply)
        self.assertEqual(reply['data']['result'], hashlib.sha256(canonical(value).encode()).hexdigest())
        # JsonNumber scale is intentionally significant: 120e-2 must not become1.2.
        reply = self.call(self.request('__scaled__'), [('__scaled__', '120e-2')])
        self.assertEqual(reply['data']['result'], hashlib.sha256(b'120e-2').hexdigest())

    def test_near_budget_success_over_budget_refusal_and_retry(self):
        self.install()
        reply = self.call(self.request('x' * 150000))
        self.assertEqual(reply['kind'], 'committed', reply)
        self.assertEqual(reply['data']['result'], hashlib.sha256(('"' + 'x'*150000 + '"').encode()).hexdigest())
        request = self.request('x' * 155000)
        before = copy.deepcopy(self.world['objects'])
        refused = self.call(request)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('budget exhausted', refused['data'])
        self.assertEqual(self.world['objects'], before)
        self.assertEqual(self.call(request), refused)
        self.assertEqual(self.world['objects'], before)

    def test_hashes_share_turn_budget_and_do_not_partially_commit(self):
        digest = ['program-digest', ['input', 'value']]
        self.install(['array', [digest, digest]])
        before = copy.deepcopy(self.world['objects'])
        refused = self.call(self.request('x'*90000))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('budget exhausted', refused['data'])
        self.assertEqual(self.world['objects'], before)

    def test_output_cap_precedes_canonical_allocation(self):
        # Four shared input references: request fits, canonical result exceeds1MiB.
        self.install(['program-digest', ['array', [['input', 'value']]*4]])
        refused = self.call(self.request('x'*300000))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('exceeds 1 MiB', refused['data'])
        self.assertEqual(self.world['objects']['hash']['version'], 0)

    def test_depth_and_decimal_conversion_are_bounded(self):
        self.install()
        nested = None
        for _ in range(256):
            nested = [nested]
        refused = self.call(self.request(nested))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('nesting exceeds', refused['data'])
        # Decimal input is already parsed by transport; re-rendering it must pay
        # its own quadratic limb bound before toString, not merely byte length.
        refused = self.call(self.request('__huge__'), [('__huge__', '9'*4299)])
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('budget exhausted', refused['data'])

    def test_real_session_factory_configuration_can_be_reprogrammed(self):
        package = load_script(ROOT / 'protocols/root-directory/package.py', 'digest_session_package')
        child = package.entry()
        original = package.factory(child)
        proposed = package.factory(child, welcome='welcome')
        self.assertGreater(len(canonical(proposed).encode()), 100000)
        law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'make': ['town-session-service']},
               'reprogram': ['steward'], 'law': ['steward']}
        created = self.call({'op': 'create', 'object': 'sessions', 'principal': 'steward',
            'intent': 'create', 'protocol': original, 'law': law})
        self.assertEqual(created['kind'], 'committed', created)
        request = {'op': 'reprogram', 'object': 'sessions', 'principal': 'steward',
            'intent': 'configure-welcome', 'expected': created['data']['root'],
            'protocol': proposed, 'state': proposed['initial']}
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['result']['program'],
                         hashlib.sha256(canonical(proposed).encode()).hexdigest())
        installed = copy.deepcopy(self.world)
        self.assertEqual(installed['objects']['sessions']['protocol'], proposed)
        self.assertEqual(installed['objects']['sessions']['state'], proposed['initial'])
        self.assertEqual(self.call(request), receipt)
        self.assertEqual(self.world, installed)


if __name__ == '__main__':
    unittest.main()
