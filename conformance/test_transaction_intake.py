"""Authenticated remote transactions through the existing clerk and actual Lean."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import delve
import manage
import receipts
import transaction_intake

spec = importlib.util.spec_from_file_location('transaction_live_fixture', ROOT / 'conformance/test_live_path.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class TransactionIntake(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.pds = live.PDS()
        self.clerk = clerk.Clerk(self.base / 'clerk', self.pds)
        protocol = clerk.loads((ROOT / 'protocols/counter/protocol.json').read_text())
        self.a = self.clerk.bootstrap('a', protocol, [delve.DID], [delve.DID])['data']['root']
        manage.Management(self.clerk.state).add_object('b', delve.DID, 'create-b', 'protocol-json@1',
            clerk.canonical(protocol), [delve.DID])
        self.b = self.clerk.snapshot('b')['root']
        credentials = self.base / 'credentials.json'
        credentials.write_text('{"handle":"' + delve.HANDLE + '","app_password":"mock-password"}')
        self.publisher = receipts.Publisher(delve.Delve(self.base / 'publication', credentials,
                                                       self.base / 'posts', self.pds))

    def payload(self):
        return {'op': 'transaction', 'reads': {'a': {'expected': self.a}, 'b': {'expected': self.b}},
                'calls': [{'object': 'a', 'command': 'add', 'input': {'amount': 3}},
                          {'object': 'b', 'command': 'add', 'input': {'amount': 5}}]}

    def receive(self, payload, intent='tx'):
        published = self.publisher.publish('request', clerk.world.wire_dumps(payload), intent)
        return self.clerk.receive(published['uri'], published['cid'])

    def test_committed_multiobject_receipt_and_restart(self):
        payload = self.payload()
        receipt = self.receive(payload)
        self.assertEqual(receipt['request']['principal'], delve.DID)
        self.assertEqual(receipt['reply']['kind'], 'committed')
        self.assertEqual(receipt['reply']['data']['roots']['a']['state']['count'], 3)
        self.assertEqual(receipt['reply']['data']['roots']['b']['state']['count'], 5)
        self.assertIsNone(receipt['reply']['object'])
        record = receipts.encode('receipt', clerk.world.wire_dumps(receipt))
        self.assertEqual(record['objects'], ['a', 'b'])
        self.assertNotIn('object', record)
        self.pds.records.clear()
        self.assertEqual(clerk.Clerk(self.clerk.state, self.pds).receive(receipt['source']['uri'], receipt['source']['cid']), receipt)

    def test_compact_roots_resolve_before_binding_and_stale_is_lean_refusal(self):
        payload = self.payload()
        for object_id in ('a', 'b'):
            snapshot = self.clerk.snapshot(object_id)
            published = self.publisher.publish('root', clerk.world.wire_dumps(snapshot), 'root-' + object_id)
            payload['reads'][object_id] = {'expectedRootRef': {key: published[key] for key in ('uri', 'cid')}}
        receipt = self.receive(payload)
        self.assertEqual(receipt['reply']['kind'], 'committed')
        journal = clerk.loads((self.clerk.state / 'requests' / (clerk.hashlib.sha256(receipt['source']['uri'].encode()).hexdigest() + '.json')).read_text())
        self.assertEqual(set(journal['resolvedRoots']), {'a', 'b'})
        stale = self.receive(payload, 'stale')
        self.assertEqual(stale['reply']['data'], 'stale read root')
        self.assertEqual(self.clerk.snapshot('a')['root']['version'], 1)

    def test_policy_failure_rolls_back_prior_call_and_missing_read_stays_host_check(self):
        updated = clerk.world.exchange(self.clerk.database, {'op': 'law', 'object': 'b', 'principal': delve.DID,
            'intent': 'lock-b', 'expected': self.b, 'law': []})
        payload = self.payload()
        payload['reads']['b']['expected'] = updated['data']['root']
        denied = self.receive(payload, 'denied')
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        self.assertEqual(self.clerk.snapshot('a')['root'], self.a)
        del payload['reads']['b']
        missing = self.receive(payload, 'missing-read')
        self.assertEqual(missing['reply']['data'], 'transaction target missing from read set')
        self.assertEqual(self.clerk.snapshot('a')['root'], self.a)

    def test_law_step_current_authority_stale_rollback_and_exact_retry(self):
        payload = {'op': 'transaction', 'reads': {'a': {'expected': self.a}, 'b': {'expected': self.b}},
            'calls': [{'object': 'a', 'command': 'add', 'input': {'amount': 3}},
                      {'op': 'law', 'object': 'b', 'law': []}]}
        receipt = self.receive(payload, 'law-batch')
        self.assertEqual(receipt['request']['principal'], delve.DID)
        self.assertEqual(receipt['reply']['kind'], 'committed', receipt)
        current_a, current_b = self.clerk.snapshot('a')['root'], self.clerk.snapshot('b')['root']
        self.assertEqual(current_a['state']['count'], 3)
        self.assertEqual(current_b['law'], [])
        self.assertEqual(current_b['state'], self.b['state'])
        self.assertEqual(current_b['version'], self.b['version'] + 1)
        self.assertIsNone(receipt['reply']['data']['results'][1])
        self.assertEqual(self.clerk.receive(receipt['source']['uri'], receipt['source']['cid']), receipt)
        denied = copy.deepcopy(payload)
        denied['reads'] = {'a': {'expected': current_a}, 'b': {'expected': current_b}}
        denied['calls'][1]['law'] = [delve.DID]
        refusal = self.receive(denied, 'current-law-denies')
        self.assertEqual(refusal['reply']['kind'], 'refused')
        self.assertEqual(self.clerk.snapshot('a')['root'], current_a)
        self.assertEqual(self.clerk.snapshot('b')['root'], current_b)
        stale = self.receive(payload, 'law-stale')
        self.assertEqual(stale['reply']['data'], 'stale read root')

    def test_bounded_shape_enrollment_and_forged_principals(self):
        for mutate in (lambda x: x.update(principal=delve.DID), lambda x: x.update(intent='forged'),
                       lambda x: x['calls'][0].update(principal=delve.DID),
                       lambda x: x['calls'][0].update(op='law'),
                       lambda x: x.update(calls=x['calls'] * 17)):
            payload = self.payload()
            mutate(payload)
            with self.subTest(payload=payload), self.assertRaises(receipts.Failure):
                receipts.encode('request', clerk.world.wire_dumps(payload))
        payload = self.payload()
        payload['calls'][1]['object'] = 'not-enrolled'
        with self.assertRaisesRegex(ValueError, 'not configured'):
            self.receive(payload, 'unknown-target')
        self.assertEqual(len(list((self.clerk.state / 'requests').glob('*.json'))), 1)  # operator create only

    def test_reprogram_candidate_from_prior_result_is_atomic_and_same_principal(self):
        replacement = copy.deepcopy(self.b['protocol'])
        replacement['name'] = 'adopted-program'
        producer = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'offer': {
            'require': [], 'set': {}, 'result': ['literal', {'protocol': replacement, 'state': {'count': 9}}], 'outbox': []}}}
        changed = clerk.world.exchange(self.clerk.database, {'op': 'reprogram', 'object': 'a', 'principal': delve.DID,
            'intent': 'install-producer', 'expected': self.a, 'protocol': producer, 'state': {}})
        payload = self.payload()
        payload['reads']['a']['expected'] = changed['data']['root']
        payload['calls'] = [{'object': 'a', 'command': 'offer', 'input': {}},
                            {'op': 'reprogram', 'object': 'b', 'inputFrom': 0}]
        receipt = self.receive(payload, 'adopt')
        self.assertEqual(receipt['reply']['kind'], 'committed')
        root = receipt['reply']['data']['roots']['b']
        self.assertEqual(root['protocol']['name'], 'adopted-program')
        self.assertEqual(root['state'], {'count': 9})
        self.assertEqual(root['law'], self.b['law'])

    def test_crash_before_envelope_save_replays_with_same_profile_and_source(self):
        payload = self.payload()
        publication = self.publisher.publish('request', clerk.world.wire_dumps(payload), 'crash')
        save = clerk.save
        def crash(path, value):
            if 'receipt' in value and 'source' in value:
                raise KeyboardInterrupt('process interrupted')
            return save(path, value)
        with patch.object(clerk, 'save', crash):
            with self.assertRaises(KeyboardInterrupt):
                self.clerk.receive(publication['uri'], publication['cid'])
        self.pds.records.clear()
        recovered = self.clerk.receive(publication['uri'], publication['cid'])
        self.assertEqual(recovered['reply']['data']['roots']['a']['version'], 1)
        self.assertEqual(self.clerk.snapshot('b')['root']['version'], 1)


if __name__ == '__main__':
    unittest.main()
