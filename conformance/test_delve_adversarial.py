"""Adversarial transport recovery checks; all PDS calls are in-memory mocks."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('delve_fixture', Path(__file__).with_name('test_delve.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
d = fixture.d


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.credentials = self.root / 'credentials.json'
        self.credentials.write_text(json.dumps({'handle': d.HANDLE, 'app_password': 'MOCK-PASSWORD'}))
        self.http = fixture.FakePDS()
        self.clock = [1800000000]
        self.client = d.Delve(self.root / 'state', self.credentials, self.root / 'posts.jsonl',
                              self.http, lambda: self.clock[0])

    def pending_post(self):
        def fail_before_put(method, base, nsid, **kwargs):
            if nsid.endswith('putRecord'):
                raise d.Failure('uncertain before application')
            return self.http(method, base, nsid, **kwargs)
        self.client.http = fail_before_put
        with self.assertRaises(d.Failure):
            self.client.post('hello', 'pending')
        self.client.http = self.http

    def test_same_timestamp_other_writer_still_brakes(self):
        self.pending_post()
        self.client.append({'at': d.stamp(self.clock[0]), 'uri': 'legacy-post'})
        with self.assertRaisesRegex(d.Failure, 'Rate limited'):
            self.client.post('hello', 'pending')
        self.assertEqual(self.http.puts, 0)

    def test_clock_rollback_does_not_hide_other_writer(self):
        self.pending_post()
        self.clock[0] -= 1
        self.client.append({'at': d.stamp(self.clock[0]), 'uri': 'legacy-post'})
        with self.assertRaisesRegex(d.Failure, 'Rate limited'):
            self.client.post('hello', 'pending')
        self.assertEqual(self.http.puts, 0)

    def test_pending_request_reuses_signed_content_and_timestamp(self):
        self.pending_post()
        path = next(self.client.state.glob('*.json'))
        record = json.loads(path.read_text())['record']
        self.clock[0] += 2
        result = self.client.post('hello', 'pending')
        self.assertEqual(self.http.records[result['uri'].split('/')[-1]]['value'], record)
        self.assertTrue(record['text'].endswith(d.SIGNOFF))
        self.assertEqual(self.http.puts, 1)

    def test_conflicting_record_after_uncertainty_is_never_replaced(self):
        self.pending_post()
        key = self.client.key('post', 'pending')
        self.http.records[key] = {'uri': 'other', 'cid': 'other', 'value': {'text': 'different'}}
        with self.assertRaisesRegex(d.Failure, 'different record'):
            self.client.post('hello', 'pending')
        self.assertEqual(self.http.puts, 0)

    def test_reply_target_change_is_rejected_on_pending_retry(self):
        self.pending_post()
        with self.assertRaisesRegex(d.Failure, 'different text or reply target'):
            self.client.post('hello', 'pending', 'at://did:plc:parent/' + d.POST + '/parent')
        self.assertEqual(self.http.puts, 0)

    def test_wrong_explicit_credential_did_fails_before_authentication(self):
        self.credentials.write_text(json.dumps({'handle': d.HANDLE, 'did': 'did:plc:wrong',
                                               'app_password': 'MOCK-PASSWORD'}))
        with self.assertRaisesRegex(d.Failure, 'different account'):
            self.client.post('hello', 'wrong-did')
        self.assertEqual(self.http.calls, [])

    def test_wrong_session_did_cannot_write_even_with_expected_handle(self):
        def wrong_identity(method, base, nsid, **kwargs):
            result = self.http(method, base, nsid, **kwargs)
            if nsid.endswith('createSession'):
                result['did'] = 'did:plc:unexpected'
            return result
        self.client.http = wrong_identity
        with self.assertRaisesRegex(d.Failure, 'identity'):
            self.client.post('hello', 'wrong-session')
        self.assertEqual(self.http.puts, 0)

    def test_malformed_log_cannot_enable_new_send(self):
        self.pending_post()
        with self.client.log.open('a') as stream:
            stream.write('partial log line\n')
        with self.assertRaisesRegex(d.Failure, 'malformed'):
            self.client.post('hello', 'pending')
        self.assertEqual(self.http.puts, 0)

    def test_lost_winner_reply_recovers_without_replacing_winner(self):
        def lose_winner_reply(method, base, nsid, **kwargs):
            body = kwargs.get('body') or {}
            if nsid.endswith('putRecord') and body['record']['phase'] == 'winner-a':
                self.http.lost_reply = True
            return self.http(method, base, nsid, **kwargs)
        self.client.http = lose_winner_reply
        with self.assertRaises(d.Failure):
            self.client.cas_demo('winner-lost')
        self.assertEqual(self.http.puts, 2)
        self.client.http = self.http
        receipt = self.client.cas_demo('winner-lost')
        self.assertEqual(receipt['refetched']['value']['phase'], 'winner-a')
        self.assertEqual(self.http.puts, 3)
        self.assertEqual(receipt['loser']['response']['error'], 'InvalidSwap')

    def test_lost_stale_rejection_can_be_reprobed(self):
        def lose_loser_reply(method, base, nsid, **kwargs):
            body = kwargs.get('body') or {}
            try:
                return self.http(method, base, nsid, **kwargs)
            except d.XRPCError:
                if nsid.endswith('putRecord') and body['record']['phase'] == 'contender-b':
                    raise d.Failure('uncertain rejected request') from None
                raise
        self.client.http = lose_loser_reply
        with self.assertRaises(d.Failure):
            self.client.cas_demo('loser-lost')
        self.client.http = self.http
        receipt = self.client.cas_demo('loser-lost')
        self.assertEqual(self.http.puts, 4)
        self.assertEqual(receipt['refetched']['value']['phase'], 'winner-a')
        self.assertEqual(receipt['events'][-1]['request']['swapRecord'], receipt['baseCID'])

    def test_cas_confirmed_deletion_cannot_resurrect(self):
        self.client.cas_demo('deleted')
        self.http.records.clear()
        with self.assertRaisesRegex(d.Failure, 'resurrection'):
            self.client.cas_demo('deleted')
        self.assertEqual(self.http.puts, 3)

    def test_probe_never_reports_success_if_server_accepts_stale_swap(self):
        def broken_cas(method, base, nsid, **kwargs):
            body = kwargs.get('body') or {}
            if nsid.endswith('putRecord') and body['record']['phase'] == 'contender-b':
                # Deliberately violate the server contract, without modifying the
                # retained client request whose stale CID is the test subject.
                kwargs['body'] = dict(body, swapRecord=self.http.records[body['rkey']]['cid'])
            return self.http(method, base, nsid, **kwargs)
        self.client.http = broken_cas
        with self.assertRaisesRegex(d.Failure, 'accepted a stale CAS'):
            self.client.cas_demo('broken-server')
        receipt = json.loads(next(self.client.state.glob('*.json')).read_text())
        self.assertNotIn('result', receipt)
        self.assertEqual(receipt['events'][-1]['status'], 200)


if __name__ == '__main__':
    unittest.main()
