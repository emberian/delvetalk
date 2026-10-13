"""ATPROTO L5 finding 9: service JWTs name a resident, never their HTTP forwarder.

Refuted by any invalid token reaching the host, a bare audience treated differently
from #delvetalk, a rotation needing two refreshes, or capacity forgetting a live jti.
Real k256/p256 signatures; offline DID documents and a fake host, no Lean process.
"""
import base64
import concurrent.futures
import http.client
import json
import tempfile
import time
import unittest
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
from transport.serviceauth import Verifier, MAX_TOKEN
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

    def access_lines(self, count):
        """Wait for handle_one_request to append after the response bytes arrive."""
        path = self.front.st.access_log
        for _ in range(100):
            if path.exists() and len(path.read_text().splitlines()) >= count:
                break
            time.sleep(0.01)
        return path.read_text().splitlines()


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
            self.front.serviceauth = Verifier(self.front.repo.did, self.front.identity.client, clock=lambda: self.now[0])
            status, data, headers = self.request(self.token({'aud': aud, 'jti': 'same-body', 'exp': 1300, 'iat': 1000}))
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
        self.front.serviceauth = Verifier(self.front.repo.did, self.front.identity.client,
                                         clock=lambda: self.now[0], capacity=2)
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
        self.front.serviceauth = Verifier(self.front.repo.did, self.front.identity.client,
                                         clock=lambda: self.now[0], document_capacity=1)
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
