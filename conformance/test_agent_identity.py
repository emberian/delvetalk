#!/usr/bin/env python3
"""Enrollment adversaries with private SQLite custody and a fixed fake proof provider."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('test_agent_identity_module', ROOT / 'scripts/agent_identity.py')
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)
A = 'did:plc:' + 'a' * 24
B = 'did:plc:' + 'b' * 24
ORIGIN = 'https://garden.example'


class FakeProvider:
    def __init__(self):
        self.posts = {}
        self.handles = {'alice.delve.town': A, 'bob.delve.town': B}
        self.reads = []
        self.before_fetch = None

    def resolve_handle(self, handle):
        return self.handles[handle]

    def fetch_post(self, uri):
        self.reads.append(uri)
        if self.before_fetch:
            self.before_fetch()
        return dict(self.posts[uri])

    def post(self, enrollment, key='proof', *, author=None, text=None, cid=None):
        author = author or enrollment['challenge']['did']
        uri = f'at://{author}/{identity.FEED}/{key}'
        self.posts[uri] = {'uri': uri, 'cid': cid or 'cid-' + key, 'authorDid': author,
                           'text': enrollment['challenge']['text'] if text is None else text,
                           'basis': 'fake-fixed-provider-v1'}
        return {'uri': uri}


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.clock = [1900000000]
        self.provider = FakeProvider()
        self.store = identity.IdentityStore(self.path / 'identity', origin=ORIGIN,
                                            provider=self.provider, now=lambda: self.clock[0])

    def enroll(self, who=A):
        return self.store.enroll({'did': who})

    def verified(self, who=A, key='proof'):
        pending = self.enroll(who)
        proof = self.provider.post(pending, key)
        result = self.store.verify(pending['token'], proof)
        return pending, result

    def error(self, code, function, *args):
        with self.assertRaises(identity.IdentityError) as raised:
            function(*args)
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def test_pending_once_secret_hash_only_and_exact_proof_survives_restart(self):
        pending = self.store.enroll({'handle': 'alice.delve.town'})
        token = pending['token']
        self.assertEqual(pending['challenge']['did'], A)
        self.assertIn(ORIGIN, pending['challenge']['text'])
        self.assertNotIn(token, pending['challenge']['text'])
        self.error('invalid_credential', self.store.authenticate, token)
        proof = self.provider.post(pending)
        result = self.store.verify(token, proof)
        self.assertEqual(self.store.authenticate(token), {k: result[k] for k in ('accountId', 'did')})
        self.assertRegex(result['accountId'], '^[0-9a-f]{32}$')
        self.assertEqual(result['proof'], {'uri': proof['uri'], 'cid': 'cid-proof', 'basis': 'fake-fixed-provider-v1'})
        self.assertNotIn(token, repr(result))
        self.provider.posts.clear()
        reopened = identity.IdentityStore(self.store.path, origin=ORIGIN, provider=self.provider)
        self.assertEqual(reopened.verify(token, proof), result)  # Idempotent recovery does not refetch.
        self.assertEqual(len(self.provider.reads), 1)
        with sqlite3.connect(self.store.database) as db:
            row = db.execute('SELECT hash,state FROM credentials').fetchone()
            self.assertEqual(row, (identity.token_hash(token), 'active'))
        for path in self.store.path.iterdir():
            if path.is_file():
                self.assertNotIn(token.encode(), path.read_bytes())
        self.assertEqual(self.store.database.stat().st_mode & 0o777, 0o600)

    def test_wrong_author_copied_proof_substring_and_claimed_principal_fail(self):
        pending = self.enroll()
        self.error('proof_author_mismatch', self.store.verify, pending['token'], self.provider.post(pending, author=B))
        self.assertEqual(self.provider.reads, [])
        for index, text in enumerate(['Quote:\n' + pending['challenge']['text'], pending['challenge']['text'] + '\n',
                                      'prefix ' + pending['challenge']['text'] + ' suffix']):
            proof = self.provider.post(pending, str(index), text=text)
            self.error('proof_does_not_match_challenge', self.store.verify, pending['token'], proof)
        proof = self.provider.post(pending, 'spoof')
        self.provider.posts[proof['uri']]['authorDid'] = B
        self.error('proof_does_not_match_challenge', self.store.verify, pending['token'], proof)
        self.error('invalid_request', self.store.verify, pending['token'], {'uri': proof['uri'], 'principal': A})
        self.error('invalid_request', self.store.enroll, {'did': A, 'role': 'operator'})
        self.error('invalid_credential', self.store.authenticate, pending['token'])

    def test_challenge_is_credential_bound_single_use_and_multiple_credentials_share_account(self):
        first, second = self.enroll(), self.enroll()
        first_proof = self.provider.post(first, 'first')
        one = self.store.verify(first['token'], first_proof)
        self.error('proof_does_not_match_challenge', self.store.verify, second['token'], first_proof)
        second_proof = self.provider.post(second, 'second')
        two = self.store.verify(second['token'], second_proof)
        self.assertEqual(one['accountId'], two['accountId'])
        self.assertNotEqual(first['challenge']['text'], second['challenge']['text'])
        self.error('credential_already_verified', self.store.verify, first['token'], second_proof)
        third = self.enroll()
        # Even a faulty provider cannot reuse an already consumed exact URI/CID.
        self.provider.posts[first_proof['uri']]['text'] = third['challenge']['text']
        self.error('proof_already_used', self.store.verify, third['token'], first_proof)

    def test_expiry_before_and_during_provider_read_and_revocation_during_read(self):
        pending = self.enroll()
        proof = self.provider.post(pending)
        self.clock[0] += 900
        self.error('challenge_expired', self.store.verify, pending['token'], proof)
        self.assertEqual(self.provider.reads, [])
        pending = self.enroll()
        proof = self.provider.post(pending, 'expires-during-read')
        self.provider.before_fetch = lambda: self.clock.__setitem__(0, self.clock[0] + 900)
        self.error('challenge_expired', self.store.verify, pending['token'], proof)
        self.provider.before_fetch = None
        pending = self.enroll()
        proof = self.provider.post(pending, 'revoke-during-read')
        self.provider.before_fetch = lambda: self.store.revoke(pending['token'])
        self.error('invalid_credential', self.store.verify, pending['token'], proof)

    def test_concurrent_verification_consumes_once_and_returns_one_account(self):
        pending = self.enroll()
        proof = self.provider.post(pending)
        barrier = threading.Barrier(2)
        self.provider.before_fetch = lambda: barrier.wait(timeout=3)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.store.verify(pending['token'], proof), range(2)))
        self.assertEqual(results[0], results[1])
        with sqlite3.connect(self.store.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM proofs').fetchone()[0], 1)

    def test_rotation_and_revocation_are_individual_atomic_and_preserve_account_identity(self):
        first, account = self.verified(key='first')
        second, same = self.verified(key='second')
        rotated = self.store.rotate(first['token'])
        self.error('invalid_credential', self.store.authenticate, first['token'])
        self.error('invalid_credential', self.store.rotate, first['token'])
        self.assertEqual(rotated['accountId'], account['accountId'])
        self.assertEqual(self.store.authenticate(rotated['token']), self.store.authenticate(second['token']))
        self.store.revoke(rotated['token'])
        self.assertEqual(self.store.revoke(rotated['token']), {'status': 'revoked'})
        self.error('invalid_credential', self.store.authenticate, rotated['token'])
        self.assertEqual(self.store.authenticate(second['token'])['accountId'], account['accountId'])
        self.store.revoke(second['token'])
        restored, again = self.verified(key='restored')
        self.assertEqual(again['accountId'], same['accountId'])
        self.error('invalid_credential', self.store.authenticate, second['token'])
        for path in self.store.path.iterdir():
            if path.is_file():
                self.assertNotIn(rotated['token'].encode(), path.read_bytes())

    def test_domain_binding_and_input_urls_do_not_redirect_proof_reads(self):
        pending = self.enroll()
        other = identity.IdentityStore(self.path / 'other', origin='https://other.example', provider=self.provider)
        other_pending = other.enroll({'did': A})
        proof = self.provider.post(pending)
        self.error('proof_does_not_match_challenge', other.verify, other_pending['token'], proof)
        with self.assertRaisesRegex(identity.IdentityError, 'origin_mismatch'):
            identity.IdentityStore(self.store.path, origin='https://other.example')
        for uri in ['http://localhost/secret', 'https://pds.delve.town/anything',
                    f'at://{A}/app.bsky.feed.post/key', f'at://{A}/{identity.FEED}/../x']:
            self.error('invalid_proof_uri', self.store.verify, pending['token'], {'uri': uri})
        for payload in [{'handle': 'http://localhost'}, {'handle': 'alice.example'}, {'did': 'owner'},
                        {'did': A, 'handle': 'alice.delve.town'}]:
            with self.assertRaises(identity.IdentityError):
                self.store.enroll(payload)
        self.assertEqual(self.provider.reads, [proof['uri']])

    def test_verification_attempts_and_storage_rates_are_bounded(self):
        pending = self.enroll()
        proof = self.provider.post(pending, text='wrong')
        for _ in range(8):
            self.error('proof_does_not_match_challenge', self.store.verify, pending['token'], proof)
        self.error('verification_rate_limited', self.store.verify, pending['token'], proof)
        self.assertEqual(len(self.provider.reads), 8)
        for _ in range(9):
            self.enroll()
        self.error('identity_rate_limited', self.enroll)
        small = identity.IdentityStore(self.path / 'small', origin=ORIGIN, max_credentials=1)
        small.enroll({'did': A})
        self.error('credential_storage_full', small.enroll, {'did': B})

    def test_failed_provider_does_not_leak_error_contents_or_activate(self):
        pending = self.enroll()
        proof = self.provider.post(pending)
        with patch.object(self.provider, 'fetch_post', side_effect=RuntimeError(pending['token'])):
            error = self.error('proof_provider_unavailable', self.store.verify, pending['token'], proof)
        self.assertEqual(error.status, 503)
        self.assertNotIn(pending['token'], str(error))
        self.error('invalid_credential', self.store.authenticate, pending['token'])

    def test_transaction_loss_rolls_back_account_activation_and_proof_consumption(self):
        pending = self.enroll()
        proof = self.provider.post(pending)
        original, calls = self.store._db, [0]
        @contextmanager
        def interrupted():
            calls[0] += 1
            number = calls[0]
            with original() as db:
                yield db
                if number == 2:
                    raise OSError('simulated loss before commit')
        with patch.object(self.store, '_db', interrupted), self.assertRaises(OSError):
            self.store.verify(pending['token'], proof)
        self.error('invalid_credential', self.store.authenticate, pending['token'])
        result = self.store.verify(pending['token'], proof)
        self.assertEqual(self.store.authenticate(pending['token'])['accountId'], result['accountId'])


class FixedProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = identity.DelveProvider()
        self.calls = []
        self.doc = {'id': A, 'alsoKnownAs': ['at://alice.delve.town'], 'service': [{
            'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer', 'serviceEndpoint': identity.PDS}]}
        self.uri = f'at://{A}/{identity.FEED}/proof'
        self.record = {'uri': self.uri, 'cid': 'immutable-cid', 'value': {'$type': identity.FEED, 'text': 'literal challenge'}}
        def get(nsid, params):
            self.calls.append((nsid, params))
            if nsid.endswith('resolveHandle'):
                return {'did': A}
            if nsid.endswith('describeRepo'):
                return {'did': A, 'didDoc': self.doc}
            return self.record
        self.provider._get = get

    def test_authoritative_record_text_and_bidirectional_handle_binding(self):
        self.assertEqual(self.provider.resolve_handle('alice.delve.town'), A)
        result = self.provider.fetch_post(self.uri)
        self.assertEqual(result['authorDid'], A)
        self.assertEqual(result['cid'], 'immutable-cid')
        self.assertEqual(result['basis'], identity.BASIS)
        self.record['value']['text'] = 'not challenge'
        self.record['value']['embed'] = {'text': 'literal challenge', 'author': A}
        self.assertEqual(self.provider.fetch_post(self.uri)['text'], 'not challenge')
        self.doc['alsoKnownAs'] = []
        with self.assertRaisesRegex(identity.IdentityError, 'handle_did_link'):
            self.provider.resolve_handle('alice.delve.town')
        self.doc['service'][0]['serviceEndpoint'] = 'http://localhost'
        with self.assertRaisesRegex(identity.IdentityError, 'unsupported_proof_repository'):
            self.provider.fetch_post(self.uri)
        self.assertTrue(all(call[0] in ('com.atproto.identity.resolveHandle', 'com.atproto.repo.describeRepo',
                                      'com.atproto.repo.getRecord') for call in self.calls))

    def test_transport_is_fixed_get_bounded_and_redirects_fail_closed(self):
        provider = identity.DelveProvider()
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size):
                self.size = size
                return b'{"did":"' + A.encode() + b'"}'
        response, requests = Response(), []
        class Opener:
            def open(self, request, timeout):
                requests.append((request, timeout))
                return response
        with patch.object(identity.urllib.request, 'build_opener', return_value=Opener()):
            provider._get('com.atproto.identity.resolveHandle', {'handle': 'alice.delve.town'})
        request, timeout = requests[0]
        self.assertTrue(request.full_url.startswith(identity.PDS + '/xrpc/'))
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertNotIn('Authorization', request.headers)
        self.assertEqual(timeout, 10)
        self.assertEqual(response.size, 256 * 1024 + 1)
        with self.assertRaisesRegex(identity.IdentityError, 'redirect'):
            identity.NoRedirect().redirect_request(None, None, 302, '', {}, 'http://localhost')


if __name__ == '__main__':
    unittest.main()
