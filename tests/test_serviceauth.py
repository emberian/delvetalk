"""ATPROTO §2(b): service JWTs name a resident, never their HTTP forwarder.

Refuted by any invalid token reaching the host, a bare audience treated differently
from #delvetalk, a rotation needing two refreshes, or capacity forgetting a live jti.
Real k256/p256 signatures; offline DID documents and a fake host, no Lean process.
"""
import base64
import concurrent.futures
import http.client
from functools import partial
import json
import os
import stat
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.parse

from cryptography.hazmat.primitives.asymmetric import ec

from tests.host import bounds, serve
from tests.test_http import DID, HANDLE, Provider, URI
from tests.test_repo import World
from tests.test_requests import FakePDS, PLC
from transport import delve, identity
from transport.atproto.cbor import CID, block, read_car
from transport.atproto.sign import CURVES, Key
from transport.config import Config
from transport.http import Front, RATE
from transport.repo import NS
from transport.serviceauth import Rejected, Verifier, MAX_TOKEN
from transport.state import State

METHOD = NS + 'getEntry'
OTHER = 'did:plc:' + 'b' * 24


def segment(value):
    raw = json.dumps(value, separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


class Documents(FakePDS):
    """Use the poller's DID-document fixture for both methods, with editable documents."""
    def __init__(self):
        super().__init__()
        self.overrides = {}
        self.posts = Provider()

    def __call__(self, method, url, headers, body):
        if url.startswith(PLC) or url.endswith('/.well-known/did.json'):
            did = url[len(PLC):] if url.startswith(PLC) else 'did:web:' + urllib.parse.urlsplit(url).hostname
            if did in self.overrides:
                self.calls.append(url)
                return 200, json.dumps(self.overrides[did]).encode()
            # FakePDS renders the same #atproto document regardless of DID method.
            return super().__call__(method, PLC + did, headers, body)
        return self.posts(method, url, headers, body)


class Host(World):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.append(DID, 'private-entry')

    def send(self, q):
        self.calls.append(q.copy())
        if q['op'] == 'bounds':
            return bounds()
        return super().send(q)


class Tokens:
    """Real method-bound service JWTs shared by the offline front tests."""

    def token(self, claims=None, header=None, key=None, high_s=False, omit=()):
        self.serial += 1
        body = {'iss': DID, 'aud': self.front.repo.did + '#delvetalk', 'exp': int(self.now[0]) + 60,
                'lxm': METHOD, 'jti': str(self.serial), **(claims or {})}
        for name in omit:
            body.pop(name, None)
        if key is None:
            issuer = body.get('iss')
            key = self.keys.get(issuer, self.keys[DID]) if isinstance(issuer, str) else self.keys[DID]
        head = {'typ': 'JWT', 'alg': 'ES256K' if key.private.curve.name == 'secp256k1' else 'ES256', **(header or {})}
        for name in omit:
            head.pop(name, None)
        message = (segment(head) + '.' + segment(body)).encode()
        sig = key.sign(message)
        if high_s:
            order = CURVES[key.private.curve.name][2]
            sig = sig[:32] + (order - int.from_bytes(sig[32:], 'big')).to_bytes(32, 'big')
        return message.decode() + '.' + base64.urlsafe_b64encode(sig).decode().rstrip('=')

    def verifier(self, **kwargs):
        return Verifier(self.front.repo.did, self.front.identity.client, self.front.st.serviceauth_ledger,
                        clock=lambda: self.now[0], limited=self.front.limited, **kwargs)

    def access_lines(self, count):
        """Wait for handle_one_request to append after the response bytes arrive."""
        path = self.front.st.access_log
        for _ in range(100):
            if path.exists() and len(path.read_text().splitlines()) >= count:
                break
            time.sleep(0.01)
        return path.read_text().splitlines()


class Verification(Tokens, unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now, self.serial = [1000.0], 0
        self.documents = Documents()
        self.keys = {did: Key(self.documents.repo(did)['key']) for did in (DID, OTHER)}
        self.front = SimpleNamespace(st=State(tmp.name, config=Config()), repo=SimpleNamespace(did='did:web:service.example'),
                                     identity=SimpleNamespace(client=delve.Client(self.documents)),
                                     hits={}, hits_lock=threading.Lock(), clock=lambda: self.now[0])
        self.front.limited = partial(Front.limited, self.front)
        self.front.serviceauth = self.verifier()

    def test_consumed_nonce_survives_a_second_verifier_and_audience_alias(self):
        token = self.token({'jti': 'restart'})
        self.assertEqual(self.front.serviceauth.authenticate(token, METHOD, '127.0.0.1'), DID)
        self.front.serviceauth = self.verifier()
        with self.assertRaises(Rejected) as e:
            self.front.serviceauth.authenticate(token, METHOD, '127.0.0.1')
        self.assertEqual(e.exception.reason, 'replay')
        alias = self.token({'jti': 'restart', 'aud': self.front.repo.did})
        with self.assertRaises(Rejected) as e:
            self.front.serviceauth.authenticate(alias, METHOD, '127.0.0.1')
        self.assertEqual(e.exception.reason, 'replay')

    def test_two_verifiers_admit_one_copy_and_compact_only_expired_nonces(self):
        a, b = self.verifier(capacity=2), self.verifier(capacity=2)
        token = self.token({'exp': 1001})
        def authenticate(v):
            try:
                return v.authenticate(token, METHOD, '127.0.0.1')
            except Rejected as e:
                return e.reason
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(authenticate, (a, b)), (DID, 'replay'))
        live = self.token({'jti': 'live', 'exp': 1200})
        self.assertEqual(a.authenticate(live, METHOD, '127.0.0.1'), DID)
        with self.assertRaises(Rejected) as e:
            b.authenticate(self.token(), METHOD, '127.0.0.1')
        self.assertEqual(e.exception.reason, 'nonce_capacity')
        self.now[0] = 1001
        self.assertEqual(b.authenticate(self.token(), METHOD, '127.0.0.1'), DID)
        rows = json.loads(self.front.st.serviceauth_ledger.read_text())
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row[3] > self.now[0] for row in rows))
        with self.assertRaises(Rejected) as e:
            a.authenticate(live, METHOD, '127.0.0.1')
        self.assertEqual(e.exception.reason, 'replay')

    def test_ledger_failure_never_accepts_and_invalid_signature_never_consumes_nonce(self):
        v = self.verifier()
        token = self.token({'jti': 'durable'})
        with mock.patch.object(State, 'write', side_effect=OSError('disk full')):
            with self.assertRaises(Rejected) as e:
                v.authenticate(token, METHOD, '127.0.0.1')
        self.assertEqual(e.exception.reason, 'nonce_store')
        with self.assertRaises(Rejected) as e:
            v.authenticate(self.token({'jti': 'durable'}, key=Key.generate()), METHOD, '127.0.0.1')
        self.assertEqual(e.exception.reason, 'signature')
        self.assertEqual(self.verifier().authenticate(token, METHOD, '127.0.0.1'), DID)

    def test_stalled_issuer_does_not_block_cached_issuer_and_one_issuer_shares_a_fetch(self):
        v = self.verifier()
        self.assertEqual(v.authenticate(self.token(), METHOD, 'warm'), DID)
        entered, release = threading.Event(), threading.Event()
        original = self.documents.__call__
        def gated(method, url, headers, body):
            if url == PLC + OTHER:
                entered.set()
                release.wait(3)
            return original(method, url, headers, body)
        v.client.document_transport = gated
        tokens = [self.token({'iss': OTHER}) for _ in range(8)]
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=9)
        try:
            pending = [pool.submit(v.authenticate, token, METHOD, 'cold') for token in tokens]
            self.assertTrue(entered.wait(1))
            warm = pool.submit(v.authenticate, self.token(), METHOD, 'warm')
            self.assertEqual(warm.result(timeout=0.5), DID)
        finally:
            release.set()
            pool.shutdown(wait=True)
        self.assertEqual([f.result() for f in pending], [OTHER] * 8)
        self.assertEqual(self.documents.calls.count(PLC + OTHER), 1)
        self.assertEqual(v.fetches, {})
        self.assertEqual(self.front.limited('serviceauth:cold', count=False), 1)

    def test_fetch_deadline_and_bounded_pending_table_do_not_accept_late_documents(self):
        v = self.verifier(document_timeout=0.05, fetch_capacity=1)
        entered, release = threading.Event(), threading.Event()
        original = self.documents.__call__
        def gated(*args):
            entered.set()
            release.wait(3)
            return original(*args)
        v.client.document_transport = gated
        try:
            start = time.monotonic()
            with self.assertRaises(Rejected) as e:
                v.authenticate(self.token(), METHOD, 'cold')
            self.assertEqual(e.exception.reason, 'document')
            self.assertTrue(entered.is_set())
            self.assertLess(time.monotonic() - start, 0.5)
            self.assertEqual(len(v.fetches), 1)
            with self.assertRaises(Rejected) as e:
                v.authenticate(self.token({'iss': OTHER}), METHOD, 'cold')
            self.assertEqual(e.exception.reason, 'document_capacity')
        finally:
            release.set()
        for _ in range(100):
            with v.lock:
                if not v.fetches:
                    break
            time.sleep(0.01)
        self.assertEqual(v.fetches, {})
        self.assertEqual(v.documents, {})
        self.assertFalse(self.front.st.serviceauth_ledger.exists())

    def test_uncached_sources_are_limited_before_fetch_and_cached_keys_bypass_that_bucket(self):
        v = self.verifier()
        self.assertEqual(v.authenticate(self.token(), METHOD, 'noisy'), DID)
        calls = len(self.documents.calls)
        for _ in range(RATE - 1):
            with self.assertRaises(Rejected) as e:
                v.authenticate(self.token({'iss': 'did:web:missing.example'}), METHOD, 'noisy')
            self.assertEqual(e.exception.reason, 'document')
        self.assertEqual(len(self.documents.calls), calls + RATE - 1)
        with self.assertRaises(Rejected) as e:
            v.authenticate(self.token({'iss': OTHER}), METHOD, 'noisy')
        self.assertEqual((e.exception.reason, e.exception.retry), ('document_rate', 60))
        self.assertEqual(len(self.documents.calls), calls + RATE - 1)
        self.assertEqual(v.authenticate(self.token(), METHOD, 'noisy'), DID)
        self.assertEqual(v.authenticate(self.token({'iss': OTHER}), METHOD, 'other-source'), OTHER)
        self.now[0] += 60
        self.assertEqual(v.authenticate(self.token(), METHOD, 'noisy'), DID)

    def test_file_and_directory_fsync_precede_acceptance_and_corrupt_ledgers_fail_closed(self):
        events = []
        original_sync, original_replace = os.fsync, os.replace
        def sync(fd):
            events.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
            original_sync(fd)
        def replace(*args):
            events.append('replace')
            original_replace(*args)
        with mock.patch('transport.serviceauth.os.fsync', side_effect=sync), \
                mock.patch('transport.state.os.replace', side_effect=replace):
            self.assertEqual(self.verifier().authenticate(self.token(), METHOD, 'source'), DID)
            events.append('accepted')
        self.assertEqual(events, ['directory', 'directory', 'file', 'replace', 'directory', 'accepted'])
        calls = len(self.documents.calls)
        for bad in ('{', '{}', '[[]]', '[["aud", "iss", "jti", true]]'):
            with self.subTest(ledger=bad):
                self.front.st.serviceauth_ledger.write_text(bad)
                with self.assertRaises(Rejected) as e:
                    self.verifier().authenticate(self.token(), METHOD, 'source')
                self.assertEqual(e.exception.reason, 'nonce_store')
        self.assertEqual(len(self.documents.calls), calls)

    def test_nonce_must_be_utf8_before_resolution_or_ledger_write(self):
        for nonce in ('\ud800', '\udfff'):
            with self.subTest(nonce=repr(nonce)), self.assertRaises(Rejected) as e:
                self.verifier().authenticate(self.token({'jti': nonce}), METHOD, 'source')
            self.assertEqual(e.exception.reason, 'nonce')
        self.assertEqual(self.documents.calls, [])
        self.assertFalse(self.front.st.serviceauth_ledger.exists())

    def test_directory_fsync_failure_refuses_even_after_atomic_replace(self):
        self.front.st.serviceauth_ledger.parent.mkdir(parents=True)
        original_sync = os.fsync
        def sync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError('directory fsync failed')
            original_sync(fd)
        token = self.token()
        with mock.patch('transport.serviceauth.os.fsync', side_effect=sync):
            with self.assertRaises(Rejected) as e:
                self.verifier().authenticate(token, METHOD, 'source')
        self.assertEqual(e.exception.reason, 'nonce_store')
        with self.assertRaises(Rejected) as e:
            self.verifier().authenticate(token, METHOD, 'source')
        self.assertEqual(e.exception.reason, 'replay')


class ServiceAuth(Tokens, unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now, self.serial = [1000.0], 0
        self.documents = Documents()
        self.keys = {did: Key(self.documents.repo(did)['key']) for did in (DID, OTHER, 'did:web:resident.example')}
        self.p256 = Key(ec.generate_private_key(ec.SECP256R1()))
        self.documents.repos[OTHER]['key'] = self.p256.private
        self.keys[OTHER] = self.p256
        self.host = Host()
        st = State(tmp.name, config=Config())
        ident = identity.Identity(st, delve.Client(self.documents), clock=lambda: self.now[0])
        self.front = serve(Front(st, self.host, ident, ('127.0.0.1', 0), clock=lambda: self.now[0]))
        self.addCleanup(self.front.server_close)
        self.addCleanup(self.front.shutdown)
        self.host.calls.clear()
        self.entry = self.host.entries[0]

    def request(self, token=None, nsid=METHOD, method='GET', **params):
        params = {'entry': self.entry['hash'], **params} if nsid == METHOD else params
        c = http.client.HTTPConnection(*self.front.server_address, timeout=10)
        c.request(method, '/xrpc/' + nsid + '?' + urllib.parse.urlencode(params),
                  headers={'Authorization': 'Bearer ' + token} if token is not None else {})
        r = c.getresponse()
        data, headers, status = r.read(), dict(r.getheaders()), r.status
        c.close()
        return status, data if headers['Content-Type'].startswith('application/vnd.ipld.car') else json.loads(data), headers

    def refused(self, token):
        self.host.calls.clear()
        status, body, _ = self.request(token)
        self.assertEqual((status, body['error']), (401, 'InvalidToken'), body)
        self.assertEqual(self.host.calls, [])

    def test_source_rate_limit_precedes_uncached_resolution_and_leaves_cached_issuer_available(self):
        self.assertEqual(self.request(self.token())[0], 200)
        calls = len(self.documents.calls)
        for _ in range(RATE - 1):
            self.refused(self.token({'iss': 'did:web:missing.example'}))
        self.assertEqual(len(self.documents.calls), calls + RATE - 1)
        status, body, headers = self.request(self.token({'iss': OTHER}))
        self.assertEqual((status, body['error']), (429, 'RateLimitExceeded'))
        self.assertIn('Retry-After', headers)
        self.assertEqual(len(self.documents.calls), calls + RATE - 1)
        self.assertEqual(self.request(self.token())[0], 200)
        self.now[0] += 60
        self.assertEqual(self.request(self.token({'iss': OTHER}))[0], 403)

    def test_wrong_audiences_and_methods_claim_types_and_times_never_call_host(self):
        cases = [{'aud': a} for a in (OTHER, self.front.repo.did + '#other', 'did:web:pds.delve.town',
                                      [self.front.repo.did], '', None)]
        cases += [{'lxm': NS + 'act'}, {'lxm': [METHOD]}, {'jti': ''}, {'jti': []},
                  {'exp': 999}, {'exp': 1000}, {'exp': 1301}, {'exp': True}, {'exp': 1060.0},
                  {'iat': 1031}, {'iat': True}, {'iat': 1000.0}, {'iat': 759},
                  {'iss': 'talkie.delve.town'}, {'iss': DID + '#atproto'}, {'iss': 'did:web:resident.example:path'},
                  {'iss': ['did:plc:a']}, {'iss': 'did:key:z123'}]
        for name, value in (('iss', DID), ('aud', self.front.repo.did), ('lxm', METHOD), ('jti', 'nonce')):
            cases += [{name: wrong} for wrong in ([value], {'value': value}, 17)]
        for name in ('exp', 'iat'):
            cases += [{name: wrong} for wrong in ([1060], {'value': 1060}, '1060')]
        for claims in cases:
            with self.subTest(claims=claims):
                self.refused(self.token(claims))
        for name in ('aud', 'exp', 'iss', 'lxm', 'jti', 'typ'):
            with self.subTest(missing=name):
                self.refused(self.token(omit=(name,)))

    def test_header_alg_curve_and_high_s_are_refused(self):
        for header, claims, key, high_s in (
                ({'typ': 'at+jwt'}, {}, None, False), ({'typ': None}, {}, None, False),
                ({'alg': 'none'}, {}, None, False), ({'alg': 'HS256'}, {}, None, False),
                ({'alg': ['ES256K']}, {}, None, False),
                ({'alg': 'ES256K'}, {'iss': OTHER}, self.p256, False),
                ({'alg': 'ES256'}, {}, None, False), ({}, {}, None, True),
                ({}, {'iss': OTHER}, self.p256, True)):
            with self.subTest(header=header, claims=claims, high_s=high_s):
                self.refused(self.token(claims, header, key, high_s))
        self.refused(self.token(omit=('alg',)))
        for name in ('typ', 'alg'):
            for value in (['JWT'], {'value': 'JWT'}, 17):
                with self.subTest(header_claim=name, value=value):
                    self.refused(self.token(header={name: value}))

    def test_unresolvable_issuer_missing_key_wrong_document_and_wrong_signer_are_refused(self):
        self.refused(self.token({'iss': 'did:plc:' + 'c' * 24}))
        for doc in ({'id': DID}, {'id': OTHER, 'verificationMethod': []},
                    {'id': DID, 'verificationMethod': [{'id': '#other', 'type': 'Multikey'}]}):
            with self.subTest(doc=doc):
                self.documents.overrides[DID] = doc
                self.refused(self.token())
        self.documents.overrides.clear()
        self.refused(self.token(key=Key.generate()))

    def test_malformed_segments_base64_json_and_signature_lengths_never_call_host(self):
        good = self.token().split('.')
        for token in ('bad', 'a.b', 'a.b.c.d', '..', '%%%.b.c', 'a.b.c',
                      '.'.join([good[0] + '=', *good[1:]]),
                      '.'.join([good[0], segment([]), good[2]]),
                      '.'.join([segment([]), *good[1:]]),
                      '.'.join([good[0], good[1], 'eA']),
                      '.'.join([good[0], good[1], 'eB']),
                      'a' * MAX_TOKEN + '.b.c'):
            with self.subTest(token=token[:40]):
                self.refused(token)

    def test_duplicate_claims_and_header_fields_are_refused_before_host(self):
        good = self.token().split('.')
        body = base64.urlsafe_b64decode(good[1] + '=' * (-len(good[1]) % 4))
        for index, raw in ((0, b'{"typ":"JWT","typ":"JWT","alg":"ES256K"}'),
                           (1, b'{"iss":"' + DID.encode() + b'",' + body[1:]),
                           (1, body[:-1] + b',"extra":NaN}')):
            parts = good.copy()
            parts[index] = base64.urlsafe_b64encode(raw).decode().rstrip('=')
            sig = self.keys[DID].sign((parts[0] + '.' + parts[1]).encode())
            parts[2] = base64.urlsafe_b64encode(sig).decode().rstrip('=')
            self.refused('.'.join(parts))

    def test_largest_token_within_byte_bound_is_accepted_and_one_character_more_refuses(self):
        lo, hi = 0, MAX_TOKEN
        while lo < hi:
            mid = (lo + hi + 1) // 2
            token = self.token({'jti': 'size-bound', 'padding': 'x' * mid})
            if len(token) <= MAX_TOKEN:
                lo = mid
            else:
                hi = mid - 1
        token = self.token({'jti': 'size-bound', 'padding': 'x' * lo})
        self.assertLessEqual(len(token), MAX_TOKEN)
        self.assertGreaterEqual(len(token), MAX_TOKEN - 1)
        self.assertEqual(self.request(token)[0], 200)
        too_big = self.token({'jti': 'size-above', 'padding': 'x' * (lo + 1)})
        self.assertGreater(len(too_big), MAX_TOKEN)
        self.refused(too_big)

    def test_bare_and_fragment_audiences_accept_the_same_body_and_return_one_hashing_block(self):
        for aud in (self.front.repo.did, self.front.repo.did + '#delvetalk'):
            self.front.serviceauth = self.verifier()
            status, data, headers = self.request(self.token({'aud': aud, 'jti': 'same-body-' + aud, 'exp': 1300, 'iat': 1000}))
            self.assertEqual(status, 200, data)
            self.assertEqual(headers['Content-Type'], 'application/vnd.ipld.car')
            roots, blocks = read_car(data)
            cid = CID.parse(self.entry['hash'])
            self.assertEqual((roots, blocks), ([cid], {cid: self.entry['bytes']}))
            self.assertEqual(block(self.entry_without_bytes())[0], cid)
        self.assertEqual(self.host.calls[-1], {'op': 'world-entry', 'principal': DID, 'hash': self.entry['hash'], 'bytes': True})

    def entry_without_bytes(self):
        return {k: v for k, v in self.entry.items() if k not in ('hash', 'bytes')}

    def test_p256_and_hostname_did_web_are_authenticated_then_host_decides(self):
        for did in (OTHER, 'did:web:resident.example'):
            status, body, _ = self.request(self.token({'iss': did}))
            self.assertEqual((status, body['error']), (403, 'Denied'))
            self.assertNotIn('bytes', json.dumps(body))
            self.assertEqual(self.host.calls[-1]['principal'], did)
        status, body, _ = self.request(self.token(), entry=str(block({'unknown': 1})[0]))
        self.assertEqual((status, body['error']), (400, 'RecordNotFound'))

    def test_replay_is_per_issuer_and_expired_entries_alone_are_pruned_at_capacity(self):
        self.front.serviceauth = self.verifier(capacity=2)
        first = self.token({'jti': 'shared', 'exp': 1001})
        self.assertEqual(self.request(first)[0], 200)
        self.refused(first)
        self.assertEqual(self.request(self.token({'iss': OTHER, 'jti': 'shared', 'exp': 1100}))[0], 403)
        blocked = self.token({'jti': 'third', 'exp': 1100})
        self.host.calls.clear()
        status, body, headers = self.request(blocked)
        self.assertEqual((status, body['error']), (429, 'RateLimitExceeded'))
        self.assertGreaterEqual(int(headers['Retry-After']), 1)
        self.assertEqual(self.host.calls, [])
        self.assertEqual(len(self.front.serviceauth.seen), 2)
        self.now[0] = 1001
        self.assertEqual(self.request(blocked)[0], 200)
        self.assertEqual(len(self.front.serviceauth.seen), 2)
        self.refused(self.token({'iss': OTHER, 'jti': 'shared', 'exp': 1100}))

    def test_concurrent_uses_of_one_jti_admit_exactly_one_host_call(self):
        token = self.token()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(lambda _: self.request(token)[0], range(8)))
        self.assertEqual(sorted(statuses), [200] + [401] * 7)
        self.assertEqual(len(self.host.calls), 1)

    def test_rotation_refetches_once_and_third_key_fails_after_exactly_one_refetch(self):
        self.assertEqual(self.request(self.token())[0], 200)
        self.assertEqual(len(self.documents.calls), 1)
        rotated = Key.generate()
        self.documents.repos[DID]['key'] = rotated.private
        self.assertEqual(self.request(self.token(key=rotated))[0], 200)
        self.assertEqual(len(self.documents.calls), 2)
        self.refused(self.token(key=Key.generate()))
        self.assertEqual(len(self.documents.calls), 3)
        self.now[0] += 61
        self.assertEqual(self.request(self.token(key=rotated))[0], 200)
        self.assertEqual(len(self.documents.calls), 4)

    def test_clock_skew_and_nonce_byte_bound_accept_the_boundary_and_refuse_one_over(self):
        self.assertEqual(self.request(self.token({'iat': 1030, 'jti': 'n' * 256}))[0], 200)
        self.refused(self.token({'jti': 'n' * 257}))
        self.refused(self.token({'jti': 'é' * 129}))

    def test_document_cache_is_bounded_and_expiry_refetches_without_losing_nonce_custody(self):
        self.front.serviceauth = self.verifier(document_capacity=1)
        first = self.token({'exp': 1200})
        self.assertEqual(self.request(first)[0], 200)
        self.assertEqual(self.request(self.token({'iss': OTHER}))[0], 403)
        self.assertEqual(len(self.front.serviceauth.documents), 1)
        self.assertEqual(len(self.documents.calls), 2)
        self.assertEqual(self.request(self.token())[0], 200)
        self.assertEqual(len(self.documents.calls), 3)
        self.refused(first)
        self.now[0] += 61
        self.assertEqual(self.request(self.token())[0], 200)
        self.assertEqual(len(self.documents.calls), 4)
        self.refused(first)

    def test_missing_token_world_parameter_and_projection_queries_require_credentials(self):
        status, body, _ = self.request()
        self.assertEqual((status, body['error']), (401, 'AuthRequired'))
        self.assertEqual(self.host.calls, [])
        for params in ({'world': 'elsewhere'}, {'world': ''}, {'entry': ''}, {'entry': 'not-a-cid'}):
            status, body, _ = self.request(self.token(), **params)
            self.assertEqual((status, body['error']), (400, 'InvalidRequest'))
        self.assertEqual(self.host.calls, [])
        self.assertEqual(self.request(self.token(), world='town')[0], 200)
        self.refused_on_other_route(self.token())

    def refused_on_other_route(self, token):
        self.host.calls.clear()
        status, body, _ = self.request(token, NS + 'getProjection', kind='receipt', key=self.entry['hash'])
        self.assertEqual((status, body['error']), (401, 'InvalidToken'))
        self.assertEqual(self.host.calls, [])

    def test_fresh_tokens_share_the_issuer_rate_limit_and_do_not_call_host_when_limited(self):
        for _ in range(RATE):
            self.assertEqual(self.request(self.token())[0], 200)
        self.host.calls.clear()
        status, body, headers = self.request(self.token())
        self.assertEqual((status, body['error']), (429, 'RateLimitExceeded'))
        self.assertIn('Retry-After', headers)
        self.assertEqual(self.host.calls, [])
        self.assertEqual(self.front.limited(DID, count=False), RATE + 1)

    def test_dt_agent_bearer_keeps_reading_records_and_did_document_advertises_service(self):
        ident = self.front.identity
        challenge = ident.challenge(HANDLE)
        self.documents.posts.texts[DID] = challenge['text']
        ident.verify(HANDLE, URI, challenge['credential'])
        status, body, _ = self.request(challenge['credential'], NS + 'getProjection', kind='receipt', key=self.entry['hash'])
        self.assertEqual((status, body['of']), (200, self.entry['hash']))
        self.assertEqual(self.host.calls[-1]['principal'], DID)
        self.refused(challenge['credential'])
        status, doc, _ = self.request(nsid='did.json')
        self.assertEqual(status, 200)
        self.assertIn({'id': '#delvetalk', 'type': 'DelvetalkWorld', 'serviceEndpoint': self.front.repo.origin}, doc['service'])

    def test_access_log_keeps_short_reason_and_authenticated_issuer_never_the_token(self):
        token = self.token({'aud': OTHER})
        self.refused(token)
        self.assertEqual(self.request(self.token())[0], 200)
        lines = self.access_lines(2)
        text = '\n'.join(lines)
        self.assertEqual(len(lines), 2)
        self.assertTrue(any(line.endswith('auth=audience') for line in lines))
        self.assertTrue(any(line.split()[5] == DID and line.split()[3] == '200' for line in lines))
        self.assertNotIn(token, text)
        self.assertNotIn('entry=', text)


if __name__ == '__main__':
    unittest.main()
