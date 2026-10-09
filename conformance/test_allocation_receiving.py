"""Governed allocation over mock PDS transport and the actual Lean receivers."""
from native_support import load_script
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import delve
import receipts
import transaction_intake
import worker


def fixture(name, path):
    return load_script(ROOT / path, name)


live = fixture('allocation_receiving_live', 'conformance/test_live_path.py')
allocation = fixture('allocation_receiving_factory', 'conformance/test_allocation.py')


class AllocationReceiving(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.serial = 0
        for binary, _ in clerk.world.PROFILES.values():
            self.assertTrue((ROOT / '.lake/build/bin' / binary).is_file(),
                            'Build Lean receivers first; receiving tests do not spawn compilers')

    def seed(self, runtime='compiled', child_law=None):
        self.serial += 1
        self.directory = self.base / str(self.serial)
        self.directory.mkdir()
        self.pds = live.PDS()
        self.clerk = clerk.Clerk(self.directory / 'clerk', self.pds)
        law = allocation.law(actors=(delve.DID,))
        law['read'].extend([delve.DID, 'local-clerk-operator'])
        child_law = child_law if child_law is not None else allocation.law('report', actors=(delve.DID,))
        child_law['read'].extend([delve.DID, 'local-clerk-operator'])
        self.root = self.clerk.bootstrap('factory', allocation.factory_protocol(child_law=child_law),
            law, [delve.DID], runtime_profile=runtime)['data']['root']
        credentials = self.directory / 'mock-credentials.json'
        credentials.write_text('{"handle":"' + delve.HANDLE + '","app_password":"mock-password"}')
        self.publisher = receipts.Publisher(delve.Delve(self.directory / 'publisher', credentials,
                                                       self.directory / 'posts', self.pds))

    def publish(self, payload, intent='make'):
        return self.publisher.publish('request', clerk.world.wire_dumps(payload), intent)

    def receive(self, payload, intent='make'):
        publication = self.publish(payload, intent)
        return self.clerk.receive(publication['uri'], publication['cid'])

    def make(self, name='one'):
        return {'object': 'factory', 'expected': self.root, 'command': 'make',
                'input': {'name': name, 'second': ''}, 'absent': ['factory/' + name]}

    def transaction(self):
        return {'op': 'transaction', 'reads': {'factory': {'expected': self.root},
                    'factory/one': {'expected': None}, 'factory/unused': {'expected': None}},
                'calls': [{'object': 'factory', 'command': 'make', 'input': {'name': 'one', 'second': ''}},
                          {'object': 'factory/one', 'command': 'report', 'input': {}}]}

    def test_remote_allocation_registers_only_admitted_children_and_replays_exact_receipt(self):
        for runtime in ('compiled',):
            with self.subTest(runtime=runtime):
                self.seed(runtime)
                payload = self.make()
                payload['absent'].append('factory/unused')
                publication = self.publish(payload)
                receipt = self.clerk.receive(publication['uri'], publication['cid'])
                self.assertEqual(receipt['reply']['kind'], 'committed')
                child = self.clerk.snapshot('factory/one')['root']
                self.assertEqual(child['law']['invoke']['report'], [delve.DID])
                self.assertEqual(receipt['reply']['data']['allocated'], {'factory/one': child})
                self.assertEqual(self.clerk.config()['objects'], ['factory', 'factory/one'])
                self.assertEqual(receipt['request']['principal'], delve.DID)
                self.assertEqual(receipt['request']['intent'], 'delve:' + publication['uri'])
                artifacts = worker.publication_artifacts(receipt)
                self.assertEqual([a['record']['object'] for a in artifacts[:-1]], ['factory', 'factory/one'])
                self.pds.records.clear()
                restarted = clerk.Clerk(self.clerk.state, self.pds)
                self.assertEqual(restarted.receive(publication['uri'], publication['cid']), receipt)
                with self.assertRaisesRegex(ValueError, 'different CID'):
                    restarted.receive(publication['uri'], 'other-cid')
                self.assertEqual(restarted.snapshot('factory')['root']['version'], 1)

    def test_new_child_is_remotely_addressable_but_creator_has_no_implicit_authority(self):
        self.seed(child_law=allocation.law('report', actors=()))
        self.assertEqual(self.receive(self.make())['reply']['kind'], 'committed')
        child = self.clerk.snapshot('factory/one')['root']
        payload = {'object': 'factory/one', 'expected': child, 'command': 'report', 'input': {}}
        denied = self.receive(payload, 'write')
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        self.assertEqual(self.clerk.snapshot('factory/one')['root'], child)

    def test_transaction_allocates_calls_and_preserves_unused_absence_in_worker_head(self):
        for runtime in ('compiled',):
            with self.subTest(runtime=runtime):
                self.seed(runtime)
                receipt = self.receive(self.transaction(), 'compose')
                self.assertEqual(receipt['reply']['kind'], 'committed')
                roots = receipt['reply']['data']['roots']
                self.assertEqual(receipt['reply']['data']['results'][-1], 0)
                self.assertEqual(roots['factory/one']['version'], 1)
                self.assertIsNone(roots['factory/unused'])
                self.assertEqual(self.clerk.config()['objects'], ['factory', 'factory/one'])
                artifacts = worker.publication_artifacts(receipt)
                self.assertEqual([item['kind'] for item in artifacts],
                                 ['root-snapshot', 'root-snapshot', 'admission-head'])
                head = clerk.loads(artifacts[-1]['record']['headJson'])
                self.assertEqual(set(head['roots']), set(roots))
                self.assertIsNone(head['roots']['factory/unused'])
                self.assertEqual(receipts.encode('receipt', clerk.world.wire_dumps(receipt))['objects'],
                                 ['factory', 'factory/one', 'factory/unused'])

    def test_failed_child_call_rolls_back_allocation_and_does_not_register_custody(self):
        self.seed(child_law=allocation.law('report', actors=()))
        denied = self.receive(self.transaction(), 'rollback')
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        self.assertEqual(self.clerk.config()['objects'], ['factory'])
        self.assertEqual(self.clerk.snapshot('factory')['root'], self.root)
        self.assertEqual(set(clerk.loads(self.clerk.database.read_bytes())['objects']), {'factory'})
        self.assertEqual(worker.publication_artifacts(denied), [])

    def test_registration_crash_replays_bound_request_without_pds_or_duplicate_allocation(self):
        for transaction in (False, True):
            with self.subTest(transaction=transaction):
                self.seed()
                publication = self.publish(self.transaction() if transaction else self.make(), 'crash')
                save = clerk.save
                def crash(path, value):
                    if path == self.clerk.state / 'clerk.json':
                        raise OSError('registration interrupted after admission')
                    return save(path, value)
                with patch.object(clerk, 'save', crash):
                    with self.assertRaisesRegex(OSError, 'registration interrupted'):
                        self.clerk.receive(publication['uri'], publication['cid'])
                self.assertEqual(self.clerk.config()['objects'], ['factory'])
                snapshot = clerk.loads(self.clerk.database.read_bytes())
                self.assertEqual(set(snapshot['objects']), {'factory', 'factory/one'})
                self.pds.records.clear()
                restarted = clerk.Clerk(self.clerk.state, self.pds)
                receipt = restarted.receive(publication['uri'], publication['cid'])
                self.assertEqual(receipt['reply']['kind'], 'committed')
                self.assertEqual(restarted.config()['objects'], ['factory', 'factory/one'])
                self.assertEqual(clerk.loads(restarted.database.read_bytes()), snapshot)
                self.assertEqual(restarted.receive(publication['uri'], publication['cid']), receipt)

    def test_existing_unregistered_child_cannot_be_enrolled_by_false_absence(self):
        self.seed()
        clerk.world.exchange(self.clerk.database, {'op': 'create', 'object': 'factory/one',
            'principal': 'operator', 'intent': 'operator-child',
            'protocol': allocation.child_protocol(), 'law': allocation.law('report', actors=(delve.DID,))}, profile='compiled')
        refused = self.receive(self.make(), 'occupied')
        self.assertEqual(refused['reply']['data'], 'stale absence root')
        self.assertEqual(self.clerk.config()['objects'], ['factory'])
        root = clerk.world.exchange(self.clerk.database, {'op': 'inspect', 'object': 'factory/one',
                                                        'principal': 'reader'}, profile='compiled')
        with self.assertRaisesRegex(ValueError, 'not configured'):
            self.receive({'object': 'factory/one', 'expected': root, 'command': 'report',
                          'input': {}}, 'unregistered')

    def test_transport_rejects_nonlocal_namespaces_and_nonabsence_unregistered_reads(self):
        self.seed()
        for object_id in ('elsewhere/one', 'factory/one/nested', 'factory/../escape'):
            payload = self.transaction()
            payload['reads'][object_id] = payload['reads'].pop('factory/one')
            payload['calls'][1]['object'] = object_id
            with self.subTest(object_id=object_id), self.assertRaisesRegex(ValueError, 'not configured'):
                transaction_intake.resolve(payload, self.clerk, self.clerk.config())
        payload = self.transaction()
        payload['reads']['factory/one'] = {'expected': self.root}
        with self.assertRaisesRegex(ValueError, 'not configured'):
            transaction_intake.resolve(payload, self.clerk, self.clerk.config())
        for descriptor in ({'expectedRootRef': None}, {'expected': False}, {'expected': []}):
            payload = self.transaction()
            payload['reads']['factory/one'] = descriptor
            with self.subTest(descriptor=descriptor), self.assertRaises(ValueError):
                transaction_intake.validate(payload)
        for absent in (None, 'factory/one', [None], ['factory/one'] * 17):
            payload = self.make()
            payload['absent'] = absent
            with self.subTest(absent=absent), self.assertRaises(receipts.Failure):
                receipts.encode('request', clerk.world.wire_dumps(payload))


if __name__ == '__main__':
    unittest.main()
