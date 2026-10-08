#!/usr/bin/env python3
"""Governed programming through the built Lean world and transaction receivers."""
import copy
from decimal import Decimal
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('programming_transport', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)
PROFILES = ('world', 'transactions')


def protocol(field='text', initial='initial'):
    return {'profile': 'delvetalk-local-v1', 'initial': {field: initial}, 'commands': {
        'write': {'require': [], 'set': {field: ['input', 'value']},
                  'result': ['state', field], 'outbox': []}}}


class ProgrammingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for profile in PROFILES:
            binary = world.PROFILES[profile][0]
            self.assertTrue((ROOT / '.lake/build/bin' / binary).exists(),
                            'Build both Lean receivers before programming tests')

    def seed(self, profile):
        self.profile = profile
        self.db = Path(self.tmp.name) / (profile + '.json')
        self.original = protocol()
        self.root = self.call({'op': 'create', 'object': 'document', 'principal': 'alice',
            'intent': 'create', 'protocol': self.original, 'law': ['alice', 'bob']})['data']['root']

    def call(self, request):
        return world.exchange(self.db, request, profile=self.profile)

    def inspect(self):
        return self.call({'op': 'inspect', 'object': 'document', 'principal': 'reader'})

    def reprogram(self, intent='upgrade', **changes):
        return {'op': 'reprogram', 'object': 'document', 'principal': 'alice',
                'intent': intent, 'expected': self.root, 'protocol': protocol('body', 'not migrated'),
                'state': {'body': 'migrated'}, **changes}

    def write(self, root, intent='write', value='changed'):
        return {'op': 'invoke', 'object': 'document', 'principal': 'bob', 'intent': intent,
                'expected': root, 'command': 'write', 'input': {'value': value}}

    def test_explicit_replacement_and_new_program_runs_under_same_law(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                request = self.reprogram()
                before = world.wire_loads(self.db.read_text())['receipts']
                receipt = self.call(request)
                self.assertEqual(receipt['kind'], 'committed')
                root = receipt['data']['root']
                self.assertEqual(root, {'protocol': request['protocol'], 'state': {'body': 'migrated'},
                                        'law': self.root['law'], 'version': 1})
                self.assertIsNone(receipt['data']['result'])
                self.assertEqual(receipt['data']['outbox'], [])
                stored = world.wire_loads(self.db.read_text())
                self.assertEqual(list(stored['objects']), ['document'])
                self.assertEqual(stored['receipts'][:-1], before)
                self.assertEqual(stored['receipts'][-1]['request']['expected']['protocol'], self.original)
                result = self.call(self.write(root))
                self.assertEqual(result['data']['result'], 'migrated')
                self.assertEqual(result['data']['root']['state'], {'body': 'changed'})

    def test_missing_state_never_resets_and_empty_state_really_replaces(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                request = self.reprogram('missing-state')
                del request['state']
                self.assertEqual(self.call(request)['kind'], 'refused')
                self.assertEqual(self.inspect(), self.root)
                for index, state in enumerate([None, [], 'record', 5]):
                    receipt = self.call(self.reprogram('bad-state-' + str(index), state=state))
                    self.assertEqual(receipt['kind'], 'refused')
                    self.assertEqual(self.inspect(), self.root)
                empty = self.call(self.reprogram('empty', state={}))
                self.assertEqual(empty['kind'], 'committed')
                self.assertEqual(empty['data']['root']['state'], {})

    def test_unauthorized_and_forged_root_cannot_install_or_restore_authority(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                forged = copy.deepcopy(self.root)
                forged['law'].append('mallory')
                request = self.reprogram(principal='mallory', expected=forged)
                refusal = self.call(request)
                self.assertEqual(refusal['data'], 'unauthorized')
                self.assertEqual(self.inspect(), self.root)
                locked = self.call({'op': 'law', 'object': 'document', 'principal': 'alice',
                    'intent': 'lock', 'expected': self.root, 'law': []})['data']['root']
                request = self.reprogram('recover', expected=locked)
                self.assertEqual(self.call(request)['data'], 'unauthorized')
                self.assertEqual(self.inspect(), locked)

    def test_exact_root_rejects_stale_or_forged_program_and_state(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                for key, value in [('state', {'text': 'unread'}), ('protocol', protocol('forged'))]:
                    expected = copy.deepcopy(self.root)
                    expected[key] = value
                    refusal = self.call(self.reprogram('forged-' + key, expected=expected))
                    self.assertEqual(refusal['data'], 'stale read root')
                    self.assertEqual(self.inspect(), self.root)
                current = self.call(self.write(self.root))['data']['root']
                self.assertEqual(self.call(self.reprogram('stale'))['data'], 'stale read root')
                self.assertEqual(self.inspect(), current)

    def test_invalid_protocol_including_unused_command_is_atomic_refusal(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                candidates = [protocol(), protocol(), protocol()]
                candidates[0]['profile'] = 'unrecognized'
                candidates[1]['commands']['unused'] = {'require': [], 'set': {},
                    'result': ['network', 'bad'], 'outbox': []}
                candidates[2]['commands']['write']['require'] = [['wrong arity']]
                for index, candidate in enumerate(candidates):
                    receipt = self.call(self.reprogram('invalid-' + str(index), protocol=candidate))
                    self.assertEqual(receipt['kind'], 'refused')
                    self.assertEqual(self.inspect(), self.root)

    def test_replay_preserves_old_receipts_after_upgrade_and_revocation(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                old_call = self.write(self.root)
                old_receipt = self.call(old_call)
                first = self.reprogram(expected=old_receipt['data']['root'])
                first_receipt = self.call(first)
                second = self.reprogram('second', expected=first_receipt['data']['root'],
                                        protocol=protocol('final'), state={'final': 'kept'})
                second_receipt = self.call(second)
                locked = self.call({'op': 'law', 'object': 'document', 'principal': 'alice',
                    'intent': 'lock', 'expected': second_receipt['data']['root'], 'law': []})['data']['root']
                before = self.db.read_bytes()
                self.assertEqual(self.call(first), first_receipt)
                self.assertEqual(self.call(old_call), old_receipt)
                self.assertEqual(self.call({**first, 'state': {'body': 'different'}})['data'],
                                 'intent reused for different request')
                self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(self.inspect(), locked)

    def test_refusal_is_retained_after_grant_and_new_intent_can_upgrade(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                request = self.reprogram(principal='charlie')
                refusal = self.call(request)
                self.assertEqual(refusal['data'], 'unauthorized')
                granted = self.call({'op': 'law', 'object': 'document', 'principal': 'alice',
                    'intent': 'grant', 'expected': self.root,
                    'law': ['alice', 'bob', 'charlie']})['data']['root']
                self.assertEqual(self.call(request), refusal)
                self.assertEqual(self.call({**request, 'expected': granted})['data'],
                                 'intent reused for different request')
                fresh = {**request, 'expected': granted, 'intent': 'fresh'}
                self.assertEqual(self.call(fresh)['kind'], 'committed')

    def test_unknown_fields_cannot_hide_law_changes_or_implicit_migration(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                for key, value in [('law', ['mallory']), ('initial', {}), ('migration', ['state', 'text']),
                                   ('command', 'write'), ('annotation', 'unexpected')]:
                    refusal = self.call(self.reprogram(key, **{key: value}))
                    self.assertEqual(refusal['data'], 'unsupported reprogram field')
                    self.assertEqual(self.inspect(), self.root)

    def test_replacement_state_keeps_exact_decimal_preimage(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                self.seed(profile)
                precise = Decimal('0.12345678901234567890123456789')
                request = self.reprogram(state={'body': precise})
                receipt = self.call(request)
                self.assertEqual(receipt['data']['root']['state'], {'body': precise})
                self.assertEqual(self.call(request), receipt)
                self.assertEqual(self.inspect()['state'], {'body': precise})

    def test_upgrade_invalidates_transaction_reads_and_new_program_composes(self):
        self.seed('transactions')
        transaction = {'op': 'transaction', 'principal': 'bob', 'intent': 'old-read',
                       'reads': {'document': self.root}, 'calls': [
                           {'object': 'document', 'command': 'write', 'input': {'value': 'transaction'}}]}
        upgraded = self.call(self.reprogram())['data']['root']
        self.assertEqual(self.call(transaction)['data'], 'stale read root')
        fresh = {**transaction, 'intent': 'current-program', 'reads': {'document': upgraded}}
        receipt = self.call(fresh)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(receipt['data']['results'], ['migrated'])
        self.assertEqual(self.inspect()['state'], {'body': 'transaction'})


if __name__ == '__main__':
    unittest.main()
