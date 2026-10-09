"""Current source authority, exact preimages, management and retained receipts."""
import copy
from pathlib import Path
import tempfile
import unittest
from native_support import load_script

ROOT = Path(__file__).resolve().parents[1]
world = load_script(ROOT / 'scripts/world.py', 'authority_transport')
source_object = load_script(ROOT / 'scripts/source_object.py', 'authority_source')


def law(**changes):
    return {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['player']},
            'reprogram': ['programmer'], 'law': ['steward'], **changes}


def counter():
    return source_object.load([{'name': 'Counter', 'source':
        (ROOT / 'examples/current-objects/Counter.obend').read_text()}], syntax='objective-bend-object')


class AuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = counter()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / 'world.json'
        self.serial = 0
        made = self.call({'op': 'create', 'object': 'counter', 'principal': 'creator',
                          'protocol': self.program, 'law': law()})
        self.assertEqual(made['kind'], 'committed', made)
        self.initial = made['data']['root']

    def call(self, request):
        self.serial += 1
        return world.exchange(self.db, {'intent': str(self.serial), 'principal': 'player', **request}, profile='compiled')

    def root(self):
        return world.query(self.db, {'op': 'inspect', 'object': 'counter', 'principal': 'reader'})

    def invoke(self, root=None, **changes):
        return {'op': 'invoke', 'object': 'counter', 'command': 'add',
                'expected': self.initial if root is None else root, 'input': {'amount': 1}, **changes}

    def revise(self, root, authority, **changes):
        return self.call({'op': 'law', 'object': 'counter', 'principal': 'steward',
                          'expected': root, 'law': authority, **changes})

    def program_request(self, root=None, **changes):
        return {'op': 'reprogram', 'object': 'counter', 'principal': 'programmer',
                'expected': self.initial if root is None else root, 'protocol': self.program,
                'state': {'model': source_object.data({'count': 9})}, **changes}

    def test_command_and_management_grants_are_independent(self):
        for request in [self.invoke(principal='creator'), self.invoke(principal='programmer'),
                        self.program_request(principal='player'),
                        {'op': 'law', 'object': 'counter', 'expected': self.initial,
                         'principal': 'programmer', 'law': law(invoke={'add': ['programmer']})}]:
            with self.subTest(request=request):
                self.assertEqual(self.call(request)['kind'], 'refused')
                self.assertEqual(self.root(), self.initial)
        changed = self.revise(self.initial, law(invoke={'*': ['player']}))['data']['root']
        self.assertEqual(self.call(self.invoke(changed))['data'], 'unauthorized')
        # Literal star does not grant the actual command; proposed self-grants cannot authorize law revision.
        self.assertEqual(self.revise(changed, law(), principal='player')['kind'], 'refused')

    def test_current_law_exact_retry_and_deliberate_lockout(self):
        request = self.invoke(intent='retained')
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        changed = self.revise(receipt['data']['root'], law(invoke={}))['data']['root']
        self.assertEqual(self.call(request), receipt)
        self.assertEqual(self.call(self.invoke(changed))['data'], 'unauthorized')
        locked = self.revise(changed, law(invoke={}, reprogram=[], law=[]))['data']['root']
        for principal in ['creator', 'player', 'programmer', 'steward']:
            with self.subTest(principal=principal):
                self.assertEqual(self.revise(locked, law(), principal=principal)['kind'], 'refused')
                self.assertEqual(self.call(self.program_request(locked, principal=principal))['kind'], 'refused')
        self.assertEqual(self.root(), locked)

    def test_refused_identity_remains_refused_after_grant(self):
        request = self.invoke(intent='denied', principal='guest')
        refusal = self.call(request)
        changed = self.revise(self.initial, law(invoke={'add': ['player', 'guest']}))['data']['root']
        self.assertEqual(self.call(request), refusal)
        self.assertEqual(self.call({**request, 'expected': changed})['data'], 'intent reused for different request')
        self.assertEqual(self.call({**request, 'expected': changed, 'intent': 'fresh'})['kind'], 'committed')

    def test_every_request_byte_binds_receipt_identity(self):
        request = self.invoke(intent='exact')
        receipt = self.call(request)
        for alteration in [{'object': 'another'}, {'annotation': 'untrusted'}, {'input': {'amount': 2}}]:
            with self.subTest(alteration=alteration):
                self.assertEqual(self.call({**request, **alteration})['data'], 'intent reused for different request')
        self.assertEqual(self.call({**request, 'principal': 'guest'})['data'], 'unauthorized')
        self.assertEqual(self.call(request), receipt)

    def test_stale_and_forged_roots_never_authorize(self):
        for component in ['state', 'protocol', 'law', 'version']:
            forged = copy.deepcopy(self.initial)
            if component == 'state': forged['state'] = {'model': source_object.data({'count': 8})}
            elif component == 'protocol': forged['protocol']['initial'] = {'model': source_object.data({'count': 8})}
            elif component == 'law': forged['law']['invoke']['add'].append('guest')
            else: forged['version'] += 1
            with self.subTest(component=component):
                self.assertEqual(self.call(self.invoke(forged))['kind'], 'refused')
                self.assertEqual(self.call(self.program_request(forged))['kind'], 'refused')
                self.assertEqual(self.root(), self.initial)
        committed = self.call(self.invoke())
        self.assertEqual(self.call(self.invoke(intent='stale'))['data'], 'stale read root')
        self.assertEqual(self.root(), committed['data']['root'])

    def test_programming_replaces_explicit_state_preserves_law_and_old_receipts(self):
        request = self.invoke(intent='before-program')
        receipt = self.call(request)
        current = receipt['data']['root']
        missing = self.program_request(current)
        del missing['state']
        self.assertEqual(self.call(missing)['kind'], 'refused')
        programmed = self.call(self.program_request(current))
        self.assertEqual(programmed['kind'], 'committed', programmed)
        root = programmed['data']['root']
        self.assertEqual(root['law'], current['law'])
        self.assertEqual(root['state'], {'model': source_object.data({'count': 9})})
        self.assertEqual(self.call(request), receipt)
        next_receipt = self.call(self.invoke(root))
        self.assertEqual(next_receipt['kind'], 'committed', next_receipt)
        self.assertEqual(next_receipt['data']['root']['state'], {'model': source_object.data({'count': 10})})

    def test_malformed_law_and_program_refuse_atomically(self):
        for malformed in [law(extra=True), law(invoke={'add': 'player'}), ['player'],
                          law(profile='delvetalk-scoped-law-v1')]:
            with self.subTest(law=malformed):
                self.assertEqual(self.revise(self.initial, malformed)['kind'], 'refused')
                self.assertEqual(self.root(), self.initial)
        malformed = copy.deepcopy(self.program)
        malformed['commands']['unused'] = {'require': [], 'set': {}, 'result': ['literal', 0], 'outbox': []}
        refused = self.call(self.program_request(protocol=malformed))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(self.root(), self.initial)


if __name__ == '__main__':
    unittest.main()
