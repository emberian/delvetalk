"""Log in with delve.town (transport/oauth.py) against a fake PDS, PLC directory and authorization server over loopback:
discovery, PAR with PKCE and DPoP, the nonce challenge, the token exchange, a wrong `sub`, a late or replayed state, and
the client metadata document against the AT Protocol OAuth profile's required fields. No host binary: the front's host is
a recorder.

Evidence for FOUNDATION §12, authentication (layer: transport).
"""
import base64
import hashlib
import html
import http.client
import json
import secrets
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from tests.host import serve
from transport import delve, identity, oauth
from transport.hostd import CLOCK
from transport.http import Front

HANDLE, DID = 'talkie.delve.town', 'did:plc:' + 'a' * 24


def unb64(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


class Recorder:
    """The front's host: says yes to everything and remembers what it was told."""
    binary = __file__

    def __init__(self):
        self.sent = []

    def send(self, req):
        self.sent.append(req)
        return {}


class Town(ThreadingHTTPServer):
    """One loopback server as PLC directory, PDS and authorization server. It checks every DPoP proof (signature,
    htm, htu, unique jti, its current nonce, one key per login) and PKCE, as a real server would."""
    daemon_threads = True

    def __init__(self):
        super().__init__(('127.0.0.1', 0), TownHandler)
        self.base = f'http://127.0.0.1:{self.server_address[1]}'
        self.nonce, self.jtis, self.requests, self.codes, self.revoked, self.challenged = 'n0', set(), {}, {}, [], []
        self.sub, self.aka, self.oauth = DID, ['at://' + HANDLE], True

    def proof(self, h, method):
        """-> the proof key's thumbprint, or None after answering the nonce challenge."""
        jwt = h.headers.get('DPoP') or ''
        head, claims, sig = jwt.split('.')
        hd, cl = json.loads(unb64(head)), json.loads(unb64(claims))
        assert hd['typ'] == 'dpop+jwt' and hd['alg'] == 'ES256' and set(hd['jwk']) == {'kty', 'crv', 'x', 'y'}, hd
        x, y = (int.from_bytes(unb64(hd['jwk'][k]), 'big') for k in ('x', 'y'))
        raw = unb64(sig)
        try:
            ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key().verify(
                encode_dss_signature(int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big')), (head + '.' + claims).encode(), ec.ECDSA(hashes.SHA256()))
        except InvalidSignature:
            raise AssertionError('bad DPoP signature')
        assert cl['htm'] == method and cl['htu'] == self.base + h.path and cl['jti'] not in self.jtis, cl
        self.jtis.add(cl['jti'])
        if cl.get('nonce') != self.nonce:
            self.challenged.append(h.path)
            h.send(400, {'error': 'use_dpop_nonce'})
            return None
        jwk = hd['jwk']
        return hashlib.sha256(json.dumps({'crv': jwk['crv'], 'kty': jwk['kty'], 'x': jwk['x'], 'y': jwk['y']}, separators=(',', ':')).encode()).hexdigest()


class TownHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, headers=()):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('DPoP-Nonce', self.server.nonce)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        t, path = self.server, urllib.parse.urlsplit(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(path.query).items()}
        if path.path == '/plc/' + DID:
            return self.send(200, {'id': DID, 'alsoKnownAs': t.aka, 'service': [{'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer', 'serviceEndpoint': t.base}]})
        if path.path == '/.well-known/oauth-protected-resource' and t.oauth:
            return self.send(200, {'resource': t.base, 'authorization_servers': [t.base]})
        if path.path == '/.well-known/oauth-authorization-server':
            return self.send(200, {'issuer': t.base, 'authorization_endpoint': t.base + '/oauth/authorize', 'token_endpoint': t.base + '/oauth/token',
                                   'pushed_authorization_request_endpoint': t.base + '/oauth/par', 'revocation_endpoint': t.base + '/oauth/revoke',
                                   'require_pushed_authorization_requests': True, 'scopes_supported': ['atproto'], 'response_types_supported': ['code'],
                                   'code_challenge_methods_supported': ['S256'], 'dpop_signing_alg_values_supported': ['ES256'],
                                   'grant_types_supported': ['authorization_code', 'refresh_token'], 'token_endpoint_auth_methods_supported': ['none', 'private_key_jwt'],
                                   'authorization_response_iss_parameter_supported': True, 'client_id_metadata_document_supported': True})
        if path.path == '/oauth/authorize':  # the person approves at once
            req = t.requests[q['request_uri']]
            assert q['client_id'] == req['client_id']
            code = secrets.token_hex(8)
            t.codes[code] = req
            t.nonce = 'n1'  # rotated: the token request meets the challenge again
            to = req['redirect_uri'] + '?' + urllib.parse.urlencode({'code': code, 'state': req['state'], 'iss': t.base})
            self.send_response(303)
            self.send_header('Location', to)
            self.end_headers()
            return
        self.send(404, {'error': 'NotFound'})

    def do_POST(self):
        t = self.server
        form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode()).items()}
        jkt = t.proof(self, 'POST')
        if jkt is None:
            return
        if self.path == '/oauth/par':
            assert form['scope'] == 'atproto' and form['response_type'] == 'code' and form['code_challenge_method'] == 'S256', form
            assert form['login_hint'] == HANDLE and form['redirect_uri'].endswith('/oauth/callback') and 'code_verifier' not in form
            uri = 'urn:ietf:params:oauth:request_uri:' + secrets.token_hex(8)
            t.requests[uri] = {**form, 'jkt': jkt}
            return self.send(201, {'request_uri': uri, 'expires_in': 299})
        if self.path == '/oauth/token':
            req = t.codes.pop(form['code'])
            assert req['jkt'] == jkt, 'the token request is bound to the PAR key'
            assert base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'].encode()).digest()).rstrip(b'=').decode() == req['code_challenge']
            assert form['redirect_uri'] == req['redirect_uri'] and form['client_id'] == req['client_id']
            return self.send(200, {'access_token': 'at-' + secrets.token_hex(8), 'refresh_token': 'rt-' + secrets.token_hex(8), 'token_type': 'DPoP',
                                   'scope': 'atproto', 'sub': t.sub, 'expires_in': 300})
        if self.path == '/oauth/revoke':
            t.revoked.append(form['token'])
            return self.send(200, {})
        self.send(404, {'error': 'NotFound'})


class Login(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.town = serve(Town())
        self.addCleanup(self.town.server_close)
        self.addCleanup(self.town.shutdown)
        self.now = [1000.0]
        resolver = lambda method, url, headers, body: (200, json.dumps({'did': DID}).encode()) if HANDLE in url else (400, b'{"error":"InvalidHandle"}')
        self.ident = identity.Identity(self.tmp.name, delve.Client(resolver), clock=lambda: self.now[0])
        self.host = Recorder()
        self.front = serve(Front(('127.0.0.1', 0), self.host, self.ident, clock=lambda: self.now[0]))
        self.addCleanup(self.front.server_close)
        self.addCleanup(self.front.shutdown)
        self.port = self.front.server_address[1]
        self.origin = f'http://127.0.0.1:{self.port}'
        self.front.oauth = oauth.OAuth(self.origin, plc=self.town.base + '/plc', secure=False, clock=lambda: self.now[0])

    def get(self, url, cookie=''):
        p = urllib.parse.urlsplit(url)
        c = http.client.HTTPConnection(p.hostname, p.port, timeout=30)
        c.request('GET', p.path + ('?' + p.query if p.query else ''), headers={'Accept': 'text/html', **({'Cookie': cookie} if cookie else {})})
        r = c.getresponse()
        out = r.status, r.getheaders(), r.read().decode()
        c.close()
        return out

    def start(self, handle=HANDLE):
        """-> (binding cookie, the callback URL the authorization server sent the browser to)."""
        s, headers, body = self.get(f'{self.origin}/oauth/start?handle={handle}')
        self.assertEqual(s, 303, body)
        h = dict(headers)
        cookie = h['Set-Cookie'].split(';')[0]
        self.assertTrue(cookie.startswith(oauth.BIND + '='))
        s, headers, _ = self.get(h['Location'])
        self.assertEqual(s, 303)
        return cookie, dict(headers)['Location']

    def refused(self, out, line):
        s, headers, body = out
        self.assertEqual(s, 400)
        self.assertIn(line, html.unescape(body))
        self.assertFalse(any(k == 'Set-Cookie' and v.startswith('dt_credential=') for k, v in headers))

    def test_the_client_metadata_document_has_every_field_the_profile_requires(self):
        url = self.origin + '/oauth/client-metadata.json'
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        c.request('GET', '/oauth/client-metadata.json')
        r = c.getresponse()
        self.assertEqual(r.status, 200)  # 200, not another 2xx or a redirect
        self.assertTrue(r.getheader('Content-Type').startswith('application/json'))
        m = json.loads(r.read())
        self.assertEqual(m['client_id'], url)  # exactly the URL it was fetched from
        self.assertIn('authorization_code', m['grant_types'])
        self.assertIn('atproto', m['scope'].split())
        self.assertIn('code', m['response_types'])
        self.assertEqual(m['redirect_uris'], [self.origin + '/oauth/callback'])
        self.assertIs(m['dpop_bound_access_tokens'], True)
        self.assertIn(m.get('application_type', 'web'), ('web',))
        self.assertEqual(m['token_endpoint_auth_method'], 'none')  # public: no jwks, no private_key_jwt
        self.assertNotIn('jwks', m)
        self.assertNotIn('refresh_token', m['grant_types'])  # identity only: it never refreshes
        self.assertEqual(urllib.parse.urlsplit(m['client_uri']).hostname, urllib.parse.urlsplit(m['client_id']).hostname)

    def test_a_login_vouched_for_by_delve_town_logs_the_browser_in_and_keeps_nothing_else(self):
        cookie, callback = self.start()
        self.assertEqual(self.town.challenged, ['/oauth/par'])  # the first proof had no nonce; the retry carried it
        s, headers, body = self.get(callback, cookie)
        self.assertEqual(s, 200, body)
        self.assertEqual(self.town.challenged, ['/oauth/par', '/oauth/token'])
        self.assertIn('Claimed', body)
        self.assertIn(f'{HANDLE}: this browser is you', body)
        session = [v.split(';')[0] for k, v in headers if k == 'Set-Cookie' and v.startswith('dt_credential=')][0]
        self.assertEqual(self.ident.authenticate(session.split('=', 1)[1])['did'], DID)  # exactly as a claimed handle
        self.assertIn('ENTER THE WORLD', self.get(self.origin + '/', session)[2])
        self.assertIn({'op': 'world-arrive', 'principal': CLOCK, 'did': DID, 'handle': HANDLE}, self.host.sent)
        self.assertEqual(len(self.town.revoked), 2)  # both tokens handed back
        stored = open(f'{self.tmp.name}/identity.sqlite', 'rb').read()
        self.assertFalse(any(tok.encode() in stored for tok in self.town.revoked))
        self.assertEqual(self.front.oauth.pending, {})
        self.refused(self.get(callback, cookie), 'That login took too long; start again.')  # the state is spent

    def test_a_server_that_vouches_for_another_account_is_refused(self):
        self.town.sub = 'did:plc:' + 'b' * 24
        cookie, callback = self.start()
        self.refused(self.get(callback, cookie), 'delve.town did not vouch for that handle.')

    def test_a_login_older_than_ten_minutes_or_from_another_browser_is_refused(self):
        cookie, callback = self.start()
        self.now[0] += 601
        self.refused(self.get(callback, cookie), 'That login took too long; start again.')
        self.now[0] += 1
        cookie, callback = self.start()
        self.refused(self.get(callback, 'dt_oauth=someone-else'), 'That login took too long; start again.')

    def test_a_handle_its_did_document_does_not_claim_or_a_pds_without_oauth_is_refused_before_leaving(self):
        self.town.aka = ['at://other.delve.town']
        self.refused(self.get(f'{self.origin}/oauth/start?handle={HANDLE}'), 'delve.town did not vouch for that handle.')
        self.town.aka, self.town.oauth = ['at://' + HANDLE], False
        self.refused(self.get(f'{self.origin}/oauth/start?handle={HANDLE}'), f"{HANDLE}'s server does not offer this login.")
        self.refused(self.get(f'{self.origin}/oauth/start?handle=nobody.example.com'), 'is not a handle this town knows')
        self.assertEqual(self.town.requests, {})

    def test_the_home_page_offers_the_login_first_and_the_word_beneath(self):
        page = self.get(self.origin + '/')[2]
        self.assertLess(page.index('Log in with delve.town'), page.index('Give me a word'))
        self.assertIn('formaction="/oauth/start"', page)
