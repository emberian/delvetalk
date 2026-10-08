"""Cross-component public transport mocks with the actual Lean admission binary."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import receipts
import delve


class PDS:
    def __init__(self):
        self.records = {}
        self.puts = 0
        self.lose_collection = None
        self.calls = []

    def __call__(self, method, base, nsid, *, params=None, body=None, token=None):
        self.calls.append((method, nsid))
        if nsid.endswith('createSession'):
            return {'did': delve.DID, 'handle': delve.HANDLE, 'accessJwt': 'mock-token'}
        if nsid.endswith('describeRepo'):
            author = params['repo']
            return {'did': author, 'didDoc': {'id': author, 'service': [{
                'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer',
                'serviceEndpoint': clerk.PDS}]}}
        data = params if method == 'GET' else body
        key = (data['repo'], data['collection'], data['rkey'])
        if nsid.endswith('getRecord'):
            if key not in self.records:
                raise delve.XRPCError(400, {'error': 'RecordNotFound'})
            value = self.records[key]
            if params.get('cid') and params['cid'] != value['cid']:
                raise delve.XRPCError(400, {'error': 'RecordNotFound'})
            return copy.deepcopy(value)
        if nsid.endswith('putRecord'):
            current = self.records.get(key)
            if body['swapRecord'] != (current['cid'] if current else None):
                raise delve.XRPCError(400, {'error': 'InvalidSwap'})
            self.puts += 1
            value = {'uri': 'at://' + '/'.join(key), 'cid': 'cid-' + str(self.puts),
                     'value': copy.deepcopy(body['record'])}
            self.records[key] = value
            if self.lose_collection == data['collection']:
                self.lose_collection = None
                raise delve.Failure('simulated lost successful reply')
            return {k: value[k] for k in ('uri', 'cid')}
        raise AssertionError(nsid)


class LivePath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.http = PDS()
        credentials = self.state / 'credentials.json'
        credentials.write_text(json.dumps({'handle': delve.HANDLE, 'app_password': 'mock-password'}))
        self.client = delve.Delve(self.state / 'publications', credentials, self.state / 'posts', self.http)
        self.pub = receipts.Publisher(self.client)
        self.clerk = clerk.Clerk(self.state / 'clerk', self.http)
        protocol = json.loads((ROOT / 'protocols/counter/protocol.json').read_text())
        self.clerk.bootstrap('counter', protocol, [delve.DID, 'operator'], [delve.DID])

    def publish(self, kind, value, intent, cid=None):
        return self.pub.publish(kind, clerk.world.wire_dumps(value), intent, cid)

    def request(self, amount=1, root=None):
        return {'object': 'counter', 'command': 'add', 'input': {'amount': amount},
                'expected': root or self.clerk.snapshot('counter')['root']}

    def receive(self, publication):
        return self.clerk.receive(publication['uri'], publication['cid'])

    def test_published_request_actual_admission_receipt_and_root_recovery(self):
        root0 = self.clerk.snapshot('counter')
        pointer = self.publish('root', root0, 'root-zero')
        request = self.request(7)
        self.http.lose_collection = receipts.REQUEST
        with self.assertRaises(delve.Failure):
            self.publish('request', request, 'add-seven')
        published = self.publish('request', request, 'add-seven')
        self.assertEqual(published['status'], 'reconciled')
        receipt = self.receive(published)
        self.assertEqual(receipt['request']['principal'], delve.DID)
        self.assertEqual(receipt['reply']['kind'], 'committed')
        self.assertEqual(receipt['reply']['data']['root']['state']['count'], 7)
        self.http.lose_collection = receipts.RECEIPT
        with self.assertRaises(delve.Failure):
            self.publish('receipt', receipt, 'receipt-seven')
        result = self.publish('receipt', receipt, 'receipt-seven')
        self.assertEqual(result['status'], 'reconciled')
        snapshot = self.clerk.snapshot('counter')
        self.http.lose_collection = receipts.ROOT
        with self.assertRaises(delve.Failure):
            self.publish('root', snapshot, 'root-one', pointer['cid'])
        self.assertEqual(self.publish('root', snapshot, 'root-one', pointer['cid'])['status'], 'reconciled')
        self.assertEqual(self.http.puts, 4)
        calls = len(self.http.calls)
        self.assertEqual(self.receive(published), receipt)
        self.assertEqual(len(self.http.calls), calls)
        self.assertEqual(self.clerk.snapshot('counter')['root']['version'], 1)

    def test_current_law_refuses_published_request_and_retains_refusal(self):
        pending = self.publish('request', self.request(), 'before-revocation')
        root = self.clerk.snapshot('counter')['root']
        changed = clerk.world.exchange(self.clerk.database, {'op': 'law', 'object': 'counter',
            'principal': 'operator', 'intent': 'revoke', 'expected': root, 'law': ['operator']})
        self.assertEqual(changed['kind'], 'committed')
        refused = self.receive(pending)
        self.assertEqual(refused['reply']['data'], 'unauthorized')
        self.publish('receipt', refused, 'denial')
        clerk.world.exchange(self.clerk.database, {'op': 'law', 'object': 'counter',
            'principal': 'operator', 'intent': 'restore', 'expected': self.clerk.snapshot('counter')['root'],
            'law': ['operator', delve.DID]})
        self.assertEqual(self.receive(pending), refused)
        self.assertEqual(self.clerk.snapshot('counter')['root']['state']['count'], 0)

    def test_receipt_journal_failure_after_admission_replays_without_remote_source(self):
        published = self.publish('request', self.request(5), 'five')
        save = clerk.save
        def lose_local_receipt(path, value):
            if 'receipt' in value:
                raise OSError('simulated disk reply interruption')
            return save(path, value)
        with patch.object(clerk, 'save', lose_local_receipt):
            with self.assertRaisesRegex(OSError, 'interruption'):
                self.receive(published)
        self.http.records.clear()
        recovered = self.receive(published)
        self.assertEqual(recovered['reply']['data']['root']['state']['count'], 5)
        self.assertEqual(self.clerk.snapshot('counter')['root']['version'], 1)
        self.publish('receipt', recovered, 'five-recovered')

    def test_social_request_root_reference_and_pending_binding_survive_pointer_advance(self):
        snapshot = self.clerk.snapshot('counter')
        pointer = self.publish('root', snapshot, 'initial-pointer')
        payload = {'object': 'counter', 'command': 'add', 'input': {'amount': 4},
                   'expectedRootRef': {key: pointer[key] for key in ('uri', 'cid')}}
        text = 'delvetalk-request v1\n\n```delvetalk-request\n' + json.dumps(payload) + '\n```'
        published = self.client.post(text, 'social-four')
        source = self.http.records[(delve.DID, delve.POST, published['uri'].split('/')[-1])]
        self.assertTrue(source['value']['text'].endswith(delve.SIGNOFF))
        save = clerk.save
        def fail_receipt(path, value):
            if 'receipt' in value:
                raise OSError('interrupted after admission')
            return save(path, value)
        with patch.object(clerk, 'save', fail_receipt):
            with self.assertRaisesRegex(OSError, 'after admission'):
                self.receive(published)
        # The pointer now exposes only the newer CID. Recovery must use the
        # durably resolved preimage, not fetch or reinterpret the changed root.
        self.publish('root', self.clerk.snapshot('counter'), 'advanced-pointer', pointer['cid'])
        self.http.records.pop((delve.DID, delve.POST, published['uri'].split('/')[-1]))
        receipt = self.receive(published)
        self.assertEqual(receipt['request']['expected'], snapshot['root'])
        self.assertEqual(receipt['reply']['data']['root']['state']['count'], 4)
        self.assertEqual(self.clerk.snapshot('counter')['root']['version'], 1)
        self.publish('receipt', receipt, 'social-receipt')

    def test_root_reference_is_an_exact_preimage_not_admission_authority(self):
        pointer = self.publish('root', self.clerk.snapshot('counter'), 'old-pointer')
        other = self.publish('request', self.request(2), 'first-change')
        self.receive(other)
        payload = {'object': 'counter', 'command': 'add', 'input': {'amount': 20},
                   'expectedRootRef': {key: pointer[key] for key in ('uri', 'cid')}}
        text = 'delvetalk-request v1\n```delvetalk-request\n' + json.dumps(payload) + '\n```'
        published = self.client.post(text, 'stale-social')
        refused = self.receive(published)
        self.assertEqual(refused['reply']['data'], 'stale read root')
        self.assertEqual(self.clerk.snapshot('counter')['root']['state']['count'], 2)


if __name__ == '__main__':
    unittest.main()
