"""Publication boundary tests use a fake PDS; no network or account writes."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import receipts as r
from delve import Delve, Failure, XRPCError, DID, HANDLE


class PDS:
    def __init__(self):
        self.records = {}
        self.puts = 0
        self.lose = False
        self.race = None

    def __call__(self, method, base, nsid, *, params=None, body=None, token=None):
        if nsid.endswith('createSession'):
            return {'did': DID, 'handle': HANDLE, 'accessJwt': 'SECRET-TOKEN'}
        if nsid.endswith('getRecord'):
            item = self.records.get((params['collection'], params['rkey']))
            if item is None:
                raise XRPCError(400, {'error': 'RecordNotFound'})
            return copy.deepcopy(item)
        if nsid.endswith('putRecord'):
            self.puts += 1
            key = (body['collection'], body['rkey'])
            old = self.records.get(key)
            if self.race:
                self.records[key] = {'uri': 'at://' + DID + '/' + '/'.join(key),
                                     'cid': 'race', 'value': self.race}
                self.race = None
                raise XRPCError(400, {'error': 'InvalidSwap'})
            if body['swapRecord'] != (old['cid'] if old else None):
                raise XRPCError(400, {'error': 'InvalidSwap'})
            self.records[key] = {'uri': 'at://' + DID + '/' + '/'.join(key),
                                 'cid': 'cid-' + str(self.puts), 'value': body['record']}
            if self.lose:
                self.lose = False
                raise Failure('Transport outcome uncertain')
            return {k: self.records[key][k] for k in ('uri', 'cid')}
        raise AssertionError(nsid)


class Publications(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.credentials = self.dir / 'credentials.json'
        self.credentials.write_text(json.dumps({'handle': HANDLE, 'app_password': 'SECRET-PASSWORD'}))
        self.http = PDS()
        self.pub = self.restart()

    def restart(self):
        return r.Publisher(Delve(self.dir / 'state', self.credentials,
                                self.dir / 'post-log.jsonl', self.http))

    def request(self):
        return '{"object":"counter","command":"add","input":{},"expected":{"version":0}}'

    def root(self, version, state=0):
        return json.dumps({'format': 'delvetalk-clerk-root-v1', 'object': 'counter',
                           'root': {'version': version, 'state': state},
                           'profile': {'name': 'delvetalk-pds-clerk-v1', 'pins': {'host': 'abc'}}})

    def test_lost_reply_restart_exact_identity_and_readback(self):
        self.http.lose = True
        with self.assertRaises(Failure):
            self.pub.publish('request', self.request(), 'first')
        result = self.restart().publish('request', self.request(), 'first')
        self.assertEqual(result['status'], 'reconciled')
        self.assertEqual(self.http.puts, 1)
        with self.assertRaisesRegex(Failure, 'different content'):
            self.pub.publish('request', self.request() + '\n', 'first')
        self.assertFalse((self.dir / 'post-log.jsonl').exists())
        for path in (self.dir / 'state').glob('*.json'):
            self.assertNotIn('SECRET', path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_root_compare_and_swap_and_stale_snapshot(self):
        first = self.pub.publish('root', self.root(0), 'root-zero')
        with self.assertRaisesRegex(Failure, 'preimage changed'):
            self.pub.publish('root', self.root(1), 'bad-preimage')
        second = self.pub.publish('root', self.root(1), 'root-one', first['cid'])
        self.assertEqual(second['status'], 'updated')
        self.assertEqual(self.pub.publish('root', self.root(0), 'root-zero')['status'], 'superseded')
        with self.assertRaisesRegex(Failure, 'version must increase'):
            self.pub.publish('root', self.root(0), 'late-zero', second['cid'])
        with self.assertRaisesRegex(Failure, 'version must increase'):
            self.pub.publish('root', self.root(1, 999), 'fork-one', second['cid'])
        self.assertEqual(self.http.puts, 2)

    def test_cas_loser_never_rebases(self):
        first = self.pub.publish('root', self.root(0), 'zero')
        self.http.race = r.encode('root', self.root(2))
        with self.assertRaisesRegex(Failure, 'CAS lost'):
            self.pub.publish('root', self.root(1), 'one', first['cid'])
        with self.assertRaisesRegex(Failure, 'version must increase'):
            self.restart().publish('root', self.root(1), 'one', first['cid'])
        self.assertEqual(self.http.puts, 2)

    def test_identical_cas_race_reconciles(self):
        self.http.race = r.encode('request', self.request())
        out = self.pub.publish('request', self.request(), 'same')
        self.assertEqual(out['status'], 'reconciled')

    def test_absent_confirmed_record_not_resurrected(self):
        self.pub.publish('request', self.request(), 'once')
        self.http.records.clear()
        with self.assertRaisesRegex(Failure, 'refusing resurrection'):
            self.pub.publish('request', self.request(), 'once')
        self.assertEqual(self.http.puts, 1)

    def test_big_numbers_and_decimal_preimages_are_strings(self):
        text = self.request().replace('"version":0', '"version":99999999999999999999999999,"x":0.100000000000000000000001')
        encoded = r.encode('request', text)
        self.assertEqual(encoded['requestJson'], text)
        self.assertEqual(set(encoded), {'$type', 'profile', 'requestJson'})

    def test_compact_root_reference_validated_without_fetching(self):
        value = {'object': 'counter', 'command': 'add', 'input': {},
                 'expectedRootRef': {'uri': 'at://' + DID + '/' + r.ROOT + '/root-key', 'cid': 'root-cid'}}
        text = json.dumps(value)
        self.assertEqual(r.encode('request', text)['requestJson'], text)
        self.pub.publish('request', text, 'compact')
        self.assertEqual(len(self.http.records), 1)
        for mutation in (
                lambda x: x.update(expected={}),
                lambda x: x['expectedRootRef'].update(uri='at://did:plc:other/' + r.ROOT + '/key'),
                lambda x: x['expectedRootRef'].update(uri='at://' + DID + '/town.delve.feed.post/key'),
                lambda x: x['expectedRootRef'].update(uri='at://' + DID + '/' + r.ROOT + '/../key'),
                lambda x: x['expectedRootRef'].update(cid=''),
                lambda x: x['expectedRootRef'].update(extra=True)):
            bad = copy.deepcopy(value)
            mutation(bad)
            with self.subTest(value=bad), self.assertRaises(Failure):
                r.encode('request', json.dumps(bad))

    def test_explicit_remote_reprogram_and_discriminator(self):
        value = {'op': 'reprogram', 'object': 'counter', 'protocol': {'commands': {}},
                 'state': {'count': 9}, 'expected': {'version': 0}}
        text = json.dumps(value)
        self.assertEqual(r.encode('request', text)['requestJson'], text)
        self.pub.publish('request', text, 'program')
        compact = copy.deepcopy(value)
        del compact['expected']
        compact['expectedRootRef'] = {'uri': 'at://' + DID + '/' + r.ROOT + '/root', 'cid': 'root-cid'}
        self.assertEqual(r.encode('request', json.dumps(compact))['requestJson'], json.dumps(compact))
        invoked = json.loads(self.request())
        invoked['op'] = 'invoke'
        self.assertEqual(r.encode('request', json.dumps(invoked))['requestJson'], json.dumps(invoked))
        for mutation in (lambda x: x.update(op='law'), lambda x: x.update(op='create'),
                         lambda x: x.update(principal=DID), lambda x: x.update(law=[DID]),
                         lambda x: x.update(command='add'), lambda x: x.update(state=[]),
                         lambda x: x.pop('state'), lambda x: x.update(protocol='code')):
            bad = copy.deepcopy(value)
            mutation(bad)
            with self.subTest(request=bad), self.assertRaises(Failure):
                r.encode('request', json.dumps(bad))

    def test_ambiguous_or_malformed_snapshots_rejected_before_write(self):
        with self.assertRaisesRegex(Failure, 'Duplicate JSON'):
            self.pub.publish('request', self.request().replace('"input":{}', '"input":{},"input":{}'), 'duplicate')
        with self.assertRaisesRegex(Failure, 'natural version'):
            self.pub.publish('root', self.root(True), 'bool-version')
        with self.assertRaisesRegex(Failure, 'Non-JSON'):
            self.pub.publish('root', self.root(0, float('nan')), 'nan')
        self.assertEqual(self.http.puts, 0)
        first = self.pub.publish('root', self.root(0), 'zero')
        key = next(iter(self.http.records))
        self.http.records[key]['value']['version'] = '1'
        with self.assertRaisesRegex(Failure, 'metadata disagrees'):
            self.pub.publish('root', self.root(2), 'two', first['cid'])
        self.assertEqual(self.http.puts, 1)

    def test_receipt_binds_refused_and_accepted_without_interpreting(self):
        for kind in ('accepted', 'refused'):
            value = {'format': 'delvetalk-clerk-receipt-v1',
                     'source': {'uri': 'at://did:plc:author/org.delvetalk.request/key', 'cid': 'cid',
                                'author': 'did:plc:author', 'pds': 'https://pds.delve.town'},
                     'request': {'principal': 'did:plc:author', 'object': 'counter', 'expected': {}},
                     'reply': {'kind': kind, 'data': 'opaque local result'},
                     'profile': {'name': 'delvetalk-pds-clerk-v1', 'pins': {'host': 'abc'}}}
            text = json.dumps(value)
            record = r.encode('receipt', text)
            self.assertEqual(record['receiptJson'], text)
            self.assertEqual(record['sha256'], r.digest(text))
            self.assertEqual(record['requestRef']['cid'], 'cid')
            self.pub.publish('receipt', text, kind)
        self.assertEqual(self.http.puts, 2)


if __name__ == '__main__':
    unittest.main()
