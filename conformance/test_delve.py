"""Mock-only tests. These do not contact or mutate Delve."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('delve', Path(__file__).resolve().parents[1] / 'scripts/delve.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class FakePDS:
    def __init__(self):
        self.records = {}
        self.calls = []
        self.puts = 0
        self.lost_reply = False
        self.race = False
        self.handle = d.HANDLE

    def __call__(self, method, base, nsid, *, params=None, body=None, token=None):
        self.calls.append((method, nsid, body))
        if nsid.endswith('createSession'):
            return {'did': d.DID, 'handle': self.handle, 'accessJwt': 'SECRET-TOKEN'}
        if nsid.endswith('getPostThread'):
            return {'thread': {'post': {'record': {'text': 'full ' * 1000}}}}
        if nsid.endswith('getPosts'):
            return {'posts': [{'uri': params['uris'], 'cid': 'parent-cid', 'record': {
                'reply': {'root': {'uri': 'at://did:plc:root/' + d.POST + '/root', 'cid': 'root-cid'}}}}]}
        if nsid.endswith('getRecord'):
            if params['rkey'] not in self.records:
                raise d.XRPCError(400, {'error': 'RecordNotFound'})
            return self.records[params['rkey']]
        if nsid.endswith('putRecord'):
            assert 'validate' not in body
            self.puts += 1
            key = body['rkey']
            if body['collection'] == d.POST and not d.valid_tid(key):
                raise d.XRPCError(400, {'error': 'InvalidRequest', 'message':
                    f'Invalid record key for {d.POST}: Invalid TID string (got "{key}") at $'})
            old = self.records.get(key)
            if self.race:
                self.race = False
                self.records[key] = {'uri': 'at://' + d.DID + '/' + body['collection'] + '/' + key,
                                     'cid': 'race-cid', 'value': body['record']}
                raise d.XRPCError(400, {'error': 'InvalidSwap'})
            if body['swapRecord'] != (old['cid'] if old else None):
                raise d.XRPCError(400, {'error': 'InvalidSwap', 'message': 'stale record'})
            out = {'uri': 'at://' + d.DID + '/' + body['collection'] + '/' + key,
                   'cid': 'cid-' + str(self.puts)}
            self.records[key] = dict(out, value=body['record'])
            if self.lost_reply:
                self.lost_reply = False
                raise d.Failure('Transport outcome uncertain')
            return out
        raise AssertionError(nsid)


class DelveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        credentials = root / 'credentials.json'
        credentials.write_text(json.dumps({'handle': d.HANDLE, 'app_password': 'SECRET-PASSWORD'}))
        self.http = FakePDS()
        self.clock = [1800000000]
        self.client = d.Delve(root / 'state', credentials, root / 'posts.jsonl', self.http, lambda: self.clock[0])

    def test_read_is_public_full_and_bounded(self):
        result = self.client.read_thread('at://did:plc:any/' + d.POST + '/one')
        self.assertEqual(len(result['thread']['post']['record']['text']), 5000)
        self.assertFalse(any(n.endswith('createSession') for _, n, _ in self.http.calls))
        with self.assertRaises(d.Failure):
            self.client.read_thread('at://a/' + d.POST + '/b', depth=11)

    def test_signoff_cap_and_identity(self):
        with self.assertRaises(d.Failure):
            self.client.post('x' * 2000, 'long')
        self.http.handle = 'wrong.delve.town'
        with self.assertRaisesRegex(d.Failure, 'identity'):
            self.client.post('hello', 'one')
        self.assertEqual(self.http.puts, 0)
        self.http.handle = d.HANDLE
        out = self.client.post('hello\n' + d.SIGNOFF, 'one')
        value = self.http.records[out['uri'].split('/')[-1]]['value']
        self.assertEqual(value['text'].count(d.SIGNOFF), 1)
        self.assertEqual(out['status'], 'created')
        for path in self.client.state.glob('*.json'):
            self.assertNotIn('SECRET', path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_lost_reply_exact_retry(self):
        self.http.lost_reply = True
        with self.assertRaises(d.Failure):
            self.client.post('hello', 'one')
        prepared = next(self.client.state.glob('*.json'))
        before = json.loads(prepared.read_text())['record']
        rkey = json.loads(prepared.read_text())['rkey']
        self.assertTrue(d.valid_tid(rkey))
        self.clock[0] += 100
        out = self.client.post('hello', 'one')
        self.assertEqual(out['status'], 'reconciled')
        self.assertEqual(self.http.puts, 1)
        self.assertEqual(before, json.loads(prepared.read_text())['record'])
        self.assertEqual(rkey, json.loads(prepared.read_text())['rkey'])
        with self.assertRaisesRegex(d.Failure, 'different text'):
            self.client.post('changed', 'one')
        with self.assertRaisesRegex(d.Failure, 'Rate limited'):
            self.client.post('second', 'two')

    def test_invalidswap_reconciliation(self):
        self.http.race = True
        out = self.client.post('hello', 'one')
        self.assertEqual(out['status'], 'reconciled')
        self.assertEqual(self.http.puts, 1)

    def test_different_existing_record_not_overwritten(self):
        self.http.lost_reply = True
        with self.assertRaises(d.Failure):
            self.client.post('hello', 'one')
        key = json.loads(next(self.client.state.glob('*.json')).read_text())['rkey']
        self.http.records[key] = {'value': {'text': 'other'}, 'uri': 'other', 'cid': 'other'}
        with self.assertRaisesRegex(d.Failure, 'different record'):
            self.client.post('hello', 'one')
        self.assertEqual(self.http.puts, 1)

    def legacy_rejection(self):
        key = self.client.key('post', 'legacy')
        record = {'$type': d.POST, 'text': 'hello\n\n' + d.SIGNOFF, 'createdAt': d.stamp(self.clock[0])}
        body = {'repo': d.DID, 'collection': d.POST, 'rkey': key, 'record': record, 'swapRecord': None}
        with self.assertRaises(d.XRPCError) as failure:
            self.http('POST', d.PDS, 'com.atproto.repo.putRecord', body=body)
        state = {'intent': 'legacy', 'principal': d.DID, 'collection': d.POST, 'rkey': key,
                 'reply_to': None, 'record': record, 'reserved': True,
                 'events': [{'at': d.stamp(self.clock[0]), 'request': body},
                            {'status': 400, 'response': failure.exception.data}]}
        path = self.client.state / (key + '.json')
        d.save(path, state)
        self.client.append({'at': d.stamp(self.clock[0]), 'event': 'prepared', 'intentKey': key})
        return path, state

    def test_definitive_invalidtid_migration_preserves_intent_and_record(self):
        path, old = self.legacy_rejection()
        log = self.client.log.read_bytes()
        self.clock[0] += 1
        migrated = self.client.migrate_post_key('legacy')
        new = json.loads(path.read_text())
        self.assertTrue(d.valid_tid(new['rkey']))
        self.assertEqual(new['record'], old['record'])
        self.assertEqual(new['events'][:2], old['events'])
        self.assertFalse(migrated['sent'])
        self.assertEqual(self.client.log.read_bytes(), log)
        self.assertEqual(self.http.puts, 1)  # only the rejected old request
        with self.assertRaisesRegex(d.Failure, 'rotation'):
            self.client.migrate_post_key('legacy')
        out = self.client.post('hello', 'legacy')
        self.assertEqual(out['status'], 'created')
        self.assertEqual(self.http.puts, 2)
        self.assertEqual(json.loads(self.client.log.read_text().splitlines()[-1])['intentKey'], self.client.key('post', 'legacy'))

    def test_invalidtid_migration_refuses_uncertain_or_existing_old_record(self):
        path, state = self.legacy_rejection()
        altered = dict(state, events=state['events'][:1])
        d.save(path, altered)
        with self.assertRaisesRegex(d.Failure, 'definitively rejected'):
            self.client.migrate_post_key('legacy')
        d.save(path, state)
        self.http.records[state['rkey']] = {'value': state['record']}
        with self.assertRaisesRegex(d.Failure, 'Old record exists'):
            self.client.migrate_post_key('legacy')
        self.assertEqual(json.loads(path.read_text()), state)

    def test_tid_encoding_layout(self):
        value = d.tid(self.clock[0])
        number = 0
        for character in value:
            number = number * 32 + d.TID_ALPHABET.index(character)
        self.assertTrue(d.valid_tid(value))
        self.assertEqual(number >> 10, self.clock[0] * 1_000_000)
        self.assertLess(number & 1023, 1024)

    def test_legacy_log_brake_and_reply_root(self):
        self.client.log.write_text(json.dumps({'at': d.stamp(self.clock[0] - 30), 'uri': 'legacy'}) + '\n')
        with self.assertRaisesRegex(d.Failure, 'Rate limited'):
            self.client.post('hello', 'one')
        self.assertEqual(self.http.puts, 0)
        self.clock[0] += 1201
        uri = 'at://did:plc:person/' + d.POST + '/parent'
        out = self.client.post('hello', 'one', uri)
        value = self.http.records[out['uri'].split('/')[-1]]['value']
        self.assertEqual(value['reply']['parent']['uri'], uri)
        self.assertEqual(value['reply']['root']['cid'], 'root-cid')

    def test_cas_real_responses_and_replay(self):
        receipt = self.client.cas_demo('one')
        self.assertEqual(receipt['loser']['response']['error'], 'InvalidSwap')
        self.assertEqual(receipt['refetched']['value']['phase'], 'winner-a')
        self.assertEqual(self.http.puts, 3)
        self.assertEqual(self.client.cas_demo('one')['result'], receipt['result'])
        self.assertEqual(self.http.puts, 3)
        self.assertFalse(self.client.log.exists())

    def test_cas_lost_initial_reply(self):
        self.http.lost_reply = True
        with self.assertRaises(d.Failure):
            self.client.cas_demo('one')
        self.assertEqual(self.client.cas_demo('one')['refetched']['value']['phase'], 'winner-a')
        self.assertEqual(self.http.puts, 3)

    def test_confirmed_deletion_not_resurrected(self):
        out = self.client.post('hello', 'one')
        del self.http.records[out['uri'].split('/')[-1]]
        with self.assertRaisesRegex(d.Failure, 'resurrection'):
            self.client.post('hello', 'one')
        self.assertEqual(self.http.puts, 1)

    def test_other_writer_brakes_uncertain_retry(self):
        # Failure before application: our reservation is durable, another writer posts later.
        original = self.http.__call__
        def failed(method, base, nsid, **kwargs):
            if nsid.endswith('putRecord'):
                raise d.Failure('uncertain')
            return original(method, base, nsid, **kwargs)
        self.client.http = failed
        with self.assertRaises(d.Failure):
            self.client.post('hello', 'one')
        self.clock[0] += 10
        self.client.append({'at': d.stamp(self.clock[0]), 'uri': 'legacy-new'})
        self.client.http = self.http
        with self.assertRaisesRegex(d.Failure, 'Rate limited'):
            self.client.post('hello', 'one')
        self.assertEqual(self.http.puts, 0)


if __name__ == '__main__':
    unittest.main()
