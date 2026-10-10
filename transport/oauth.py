"""Log in with delve.town: AT Protocol OAuth (https://atproto.com/specs/oauth) for identity only, scope `atproto`.

A public web client: the handle is resolved and checked both ways against its DID document, the PDS names its
authorization server, a pushed request carries PKCE (S256) and a DPoP proof (ES256), the browser goes there, and the
code comes back to /oauth/callback, where it is exchanged once. The `sub` the server returns must be the DID the handle
resolved to; then the browser gets the same session cookie `verify` sets. The tokens are revoked and dropped at once;
the pending login (state, verifier, DPoP key) lives in memory for ten minutes and is used once. The transport decides
nothing: it accepts what the account's own authorization server vouches.
"""
import base64
import hashlib
import html
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from transport import pages
from transport.delve import MAX_RESPONSE, TIMEOUT, Failure, _NoRedirect
from transport.identity import DID, HANDLE, digest

PLC = 'https://plc.directory'
TTL, KEEP, PENDING_MAX = 600, 2592000, 1024  # a pending login's life; the session's (the cookie's Max-Age); logins in flight
BIND = 'dt_oauth'  # the browser that started a login is the one that may finish it
LINES = {'unvouched': 'delve.town did not vouch for that handle.',
         'late': 'That login took too long; start again.',
         'unknown': '{handle} is not a handle this town knows. Check the spelling.',
         'no_oauth': "{handle}'s server does not offer this login. Claim it with a word instead."}


class Refused(Exception):
    def __init__(self, line, detail=''):
        self.line, self.detail = line, detail
        super().__init__(line + (': ' + detail if detail else ''))


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def fetch(method, url, headers=None, body=None):
    """-> (status, lower-cased headers, bytes). No redirects; size-capped; the transport's timeout."""
    req = urllib.request.Request(url, body, {'User-Agent': 'DelveTalk/2 oauth', 'Accept': 'application/json', **(headers or {})}, method=method)
    try:
        resp = urllib.request.build_opener(_NoRedirect).open(req, timeout=TIMEOUT)
    except urllib.error.HTTPError as error:
        resp = error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise Failure('network_error', type(error).__name__) from None
    with resp:
        raw = resp.read(MAX_RESPONSE + 1)
        return resp.status, {k.lower(): v for k, v in resp.headers.items()}, raw[:MAX_RESPONSE]


def as_json(status, raw, want=200):
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if status != want or not isinstance(data, dict):
        raise Refused('unvouched', f'{status}')
    return data


class DPoP:
    """One ES256 key per login (RFC 9449): a fresh proof per request, the server's nonce tracked and retried once."""
    def __init__(self):
        self.key, self.nonce = ec.generate_private_key(ec.SECP256R1()), None
        n = self.key.public_key().public_numbers()
        self.jwk = {'kty': 'EC', 'crv': 'P-256', 'x': b64(n.x.to_bytes(32, 'big')), 'y': b64(n.y.to_bytes(32, 'big'))}

    def proof(self, method, url):
        head = {'typ': 'dpop+jwt', 'alg': 'ES256', 'jwk': self.jwk}
        claims = {'jti': secrets.token_urlsafe(16), 'htm': method, 'htu': url.split('?')[0].split('#')[0], 'iat': int(time.time())}
        if self.nonce:
            claims['nonce'] = self.nonce
        signing = b64(json.dumps(head, separators=(',', ':')).encode()) + '.' + b64(json.dumps(claims, separators=(',', ':')).encode())
        r, s = decode_dss_signature(self.key.sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
        return signing + '.' + b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))

    def post(self, url, form):
        """A form POST with DPoP; a `use_dpop_nonce` refusal is answered once with the nonce it carried."""
        for _ in range(2):
            status, headers, raw = fetch('POST', url, {'Content-Type': 'application/x-www-form-urlencoded', 'DPoP': self.proof('POST', url)},
                                         urllib.parse.urlencode(form).encode())
            fresh = headers.get('dpop-nonce')
            if not fresh:
                raise Refused('unvouched', 'no DPoP-Nonce')  # the profile makes server nonces mandatory
            stale, self.nonce = self.nonce, fresh
            try:
                error = json.loads(raw).get('error')
            except (ValueError, AttributeError):
                error = None
            if status in (400, 401) and error == 'use_dpop_nonce' and fresh != stale:
                continue
            return status, raw
        return status, raw


class OAuth:
    def __init__(self, origin, plc=PLC, secure=True, clock=time.time):
        self.origin, self.plc, self.secure, self.clock = origin.rstrip('/'), plc.rstrip('/'), secure, clock
        self.client_id, self.redirect = self.origin + '/oauth/client-metadata.json', self.origin + '/oauth/callback'
        self.pending, self.lock = {}, threading.Lock()

    def metadata(self):
        return {'client_id': self.client_id, 'client_name': 'DelveTalk', 'client_uri': self.origin, 'application_type': 'web',
                'grant_types': ['authorization_code'], 'response_types': ['code'], 'redirect_uris': [self.redirect],
                'scope': 'atproto', 'token_endpoint_auth_method': 'none', 'dpop_bound_access_tokens': True}

    def url(self, value, root=False):
        """An https URL (http on loopback only in tests); with root, a bare origin, as the spec requires of servers."""
        p = urllib.parse.urlsplit(value) if isinstance(value, str) else None
        if not p or p.scheme not in (('https',) if self.secure else ('https', 'http')) or not p.hostname or p.username or \
                (root and (p.path not in ('', '/') or p.query or p.fragment)):
            raise Refused('unvouched', 'bad url')
        return value.rstrip('/') if root else value

    def discover(self, handle, resolve):
        """handle -> (did, authorization server metadata), the handle confirmed by its DID document."""
        if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
            raise Refused('unknown')
        try:
            did = resolve(handle).get('did')
        except Failure:
            raise Refused('unknown') from None
        if not isinstance(did, str) or not DID.fullmatch(did):
            raise Refused('unknown')
        doc = as_json(*fetch('GET', f'{self.plc}/{did}')[::2])
        if doc.get('id') != did or 'at://' + handle not in (doc.get('alsoKnownAs') or []):
            raise Refused('unvouched', 'handle not in DID document')
        pds = [s.get('serviceEndpoint') for s in doc.get('service') or [] if isinstance(s, dict) and s.get('id') in ('#atproto_pds', did + '#atproto_pds')]
        pds = self.url(pds[0] if pds else None, root=True)
        try:
            servers = as_json(*fetch('GET', pds + '/.well-known/oauth-protected-resource')[::2]).get('authorization_servers')
        except Refused:
            raise Refused('no_oauth') from None
        issuer = self.url(servers[0] if isinstance(servers, list) and len(servers) == 1 else None, root=True)
        meta = as_json(*fetch('GET', issuer + '/.well-known/oauth-authorization-server')[::2])
        if meta.get('issuer') != issuer or 'atproto' not in (meta.get('scopes_supported') or []) or \
                'S256' not in (meta.get('code_challenge_methods_supported') or []) or 'ES256' not in (meta.get('dpop_signing_alg_values_supported') or []) or \
                meta.get('client_id_metadata_document_supported') is not True or meta.get('authorization_response_iss_parameter_supported') is not True:
            raise Refused('no_oauth', 'authorization server outside the atproto profile')
        for k in ('pushed_authorization_request_endpoint', 'authorization_endpoint', 'token_endpoint'):
            self.url(meta.get(k))
        return did, meta

    def start(self, handle, resolve):
        """-> (state, the authorization URL to send the browser to)."""
        did, meta = self.discover(handle, resolve)
        dpop, verifier, state = DPoP(), secrets.token_urlsafe(48), secrets.token_urlsafe(24)
        status, raw = dpop.post(meta['pushed_authorization_request_endpoint'], {
            'client_id': self.client_id, 'response_type': 'code', 'redirect_uri': self.redirect, 'scope': 'atproto', 'state': state,
            'code_challenge': b64(hashlib.sha256(verifier.encode()).digest()), 'code_challenge_method': 'S256', 'login_hint': handle})
        request_uri = as_json(status, raw, 201 if status == 201 else 200).get('request_uri')
        if not isinstance(request_uri, str):
            raise Refused('unvouched', 'PAR gave no request_uri')
        now = self.clock()
        with self.lock:
            for k in [k for k, v in self.pending.items() if v['expires'] <= now]:
                del self.pending[k]
            if len(self.pending) >= PENDING_MAX:
                raise Refused('late', 'too many logins in flight')
            self.pending[state] = {'handle': handle, 'did': did, 'meta': meta, 'dpop': dpop, 'verifier': verifier, 'expires': now + TTL}
        return state, meta['authorization_endpoint'] + '?' + urllib.parse.urlencode({'client_id': self.client_id, 'request_uri': request_uri})

    def finish(self, query, bound):
        """The callback's query and the browser's binding cookie -> {handle, did}, or Refused. The state is spent here."""
        state = query.get('state', '')
        with self.lock:
            login = self.pending.pop(state, None) if state else None
        if login is None or login['expires'] <= self.clock() or not secrets.compare_digest(bound, state):
            raise Refused('late')
        meta = login['meta']
        if query.get('iss') != meta['issuer'] or query.get('error') or not query.get('code'):
            raise Refused('unvouched', query.get('error', 'no code'))
        status, raw = login['dpop'].post(meta['token_endpoint'], {
            'grant_type': 'authorization_code', 'code': query['code'], 'redirect_uri': self.redirect,
            'client_id': self.client_id, 'code_verifier': login['verifier']})
        tokens = as_json(status, raw)
        revoke = meta.get('revocation_endpoint')
        for kind in ('refresh_token', 'access_token'):  # identity only: nothing is kept, so nothing is left live at the PDS
            if revoke and isinstance(tokens.get(kind), str):
                try:
                    login['dpop'].post(self.url(revoke), {'token': tokens[kind], 'token_type_hint': kind, 'client_id': self.client_id})
                except (Refused, Failure):
                    pass
        if tokens.get('sub') != login['did'] or 'atproto' not in str(tokens.get('scope', '')).split() or str(tokens.get('token_type', '')).lower() != 'dpop':
            raise Refused('unvouched', 'sub, scope or token type')
        return {'handle': login['handle'], 'did': login['did']}


def admit(identity, handle, did):
    """A credential the front authenticates exactly as a claimed one: a row in the claim table, state `verified`, with no word."""
    credential, now = 'dt_agent_' + secrets.token_urlsafe(32), identity.clock()
    with identity.lock:
        identity.db.execute("INSERT INTO challenges(nonce,handle,did,text,credential,created,expires,state,verified) VALUES(?,?,?,?,?,?,?,?,?)",
                            (secrets.token_hex(16), handle, did, '', digest(credential), now, now + KEEP, 'verified', now))
    return credential


def route(h, method, path):
    """/oauth/* on the front: `h` is the request handler (its server, cookie, html and reply)."""
    o, query = h.server.oauth, {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(h.path).query).items()}
    refuse = lambda code, e: h.html(code, pages.refusal('log in', None, {
        'message': LINES[e.line].format(handle=query.get('handle', '')),
        '_links': {'claim': {'href': '/'}}}, 'login'), [('Set-Cookie', f'{BIND}=; Path=/oauth/; Max-Age=0')])
    if method != 'GET':
        return h.fail('methodNotAllowed', f'{path} takes GET', headers=[('Allow', 'GET, OPTIONS')])
    if path == '/oauth/client-metadata.json':
        return h.reply(200, json.dumps(o.metadata(), indent=1), headers=[('Cache-Control', 'max-age=300')])
    if path == '/oauth/start' and h.headers.get('Host') != urllib.parse.urlsplit(o.origin).netloc:
        return h.reply(303, '', 'text/plain', [('Location', o.origin + h.path)])  # the binding cookie must live on the origin's name
    if path == '/oauth/start':
        wait = h.server.limited('ip:' + h.client_ip(), 16)
        if wait:
            return h.fail('rateLimited', 'more than 16 logins a minute from one address', headers=[('Retry-After', str(wait))])
        try:
            state, to = o.start(query.get('handle', '').strip().lower(), h.server.identity.client.resolve_handle)
        except (Refused, Failure) as e:
            return refuse(400, e if isinstance(e, Refused) else Refused('unvouched'))
        secure = '; Secure' if o.origin.startswith('https:') else ''
        return h.reply(303, '', 'text/plain', [('Location', to), ('Set-Cookie', f'{BIND}={state}; Path=/oauth/; HttpOnly; SameSite=Lax; Max-Age={TTL}{secure}')])
    if path == '/oauth/callback':
        bound = next((v for k, _, v in (p.strip().partition('=') for p in (h.headers.get('Cookie') or '').split(';')) if k == BIND), '')
        try:
            who = o.finish(query, bound)
        except (Refused, Failure) as e:
            return refuse(400, e if isinstance(e, Refused) else Refused('unvouched'))
        h.server.record_handle(who['did'], who['handle'])
        credential = admit(h.server.identity, who['handle'], who['did'])
        return h.html(200, pages.page('claimed', who['handle'], pages.T['verified'].format(handle=html.escape(who['handle']))),
                      h.login_cookie(credential) + [('Set-Cookie', f'{BIND}=; Path=/oauth/; Max-Age=0')])
    return h.fail('unknownRoute', f'no route at {path}')
