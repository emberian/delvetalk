"""Method-bound service JWTs under the resident's #atproto key (ATPROTO §2(b)).

The resident signs an audience, not an HTTP forwarder. Bare and #delvetalk
audiences name this same service; neither authorizes any other method.
"""
import base64
import binascii
import json
import math
import re
import threading
import time
from collections import OrderedDict

from transport.atproto.sign import verify
from transport.delve import DID, Failure
from transport.repo import Refusal, XRPC_ERRORS
from transport.requests import atproto_key

SHAPE = re.compile(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\Z')
MAX_TOKEN = 16 * 1024
SEEN_CAPACITY, DOCUMENT_CAPACITY, DOCUMENT_TTL = 10_000, 1024, 60
ALGORITHMS = {'ES256K': 'secp256k1', 'ES256': 'secp256r1'}


def shaped(token):
    """Three nonempty base64url segments distinguish service JWTs from credentials."""
    return bool(SHAPE.fullmatch(token))


class Rejected(Refusal):
    def __init__(self, reason, error='InvalidToken', retry=0):
        super().__init__(XRPC_ERRORS[error]['code'], error, reason)
        self.reason, self.retry = reason, retry


def raw(segment):
    decoded = base64.b64decode(segment + '=' * (-len(segment) % 4), altchars=b'-_', validate=True)
    if base64.urlsafe_b64encode(decoded).decode().rstrip('=') != segment:
        raise ValueError('noncanonical base64url')
    return decoded


def unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate claim')
        out[key] = value
    return out


def object_of(segment):
    def constant(_):
        raise ValueError('non-JSON number')
    out = json.loads(raw(segment).decode('utf-8'), object_pairs_hook=unique,
                     parse_constant=constant)
    if not isinstance(out, dict):
        raise ValueError('not an object')
    return out


class Verifier:
    """One per front. Atomic replay admission; bounded documents and live nonce custody.

    A full replay set refuses new tokens until an expiry, never evicts a live nonce.
    The lock covers refresh and admission so concurrent copies cannot both pass.
    """
    def __init__(self, did, client, clock=time.time, capacity=SEEN_CAPACITY,
                 document_capacity=DOCUMENT_CAPACITY, document_ttl=DOCUMENT_TTL):
        if capacity < 1 or document_capacity < 1 or document_ttl <= 0:
            raise ValueError('service-auth bounds must be positive')
        self.did, self.client, self.clock = did, client, clock
        self.capacity, self.document_capacity, self.document_ttl = capacity, document_capacity, document_ttl
        self.seen, self.documents, self.lock = {}, OrderedDict(), threading.Lock()

    def key(self, iss, now, refresh=False):
        for did, (until, _) in list(self.documents.items()):
            if until <= now:
                del self.documents[did]
        if not refresh and iss in self.documents:
            self.documents.move_to_end(iss)
            return atproto_key(self.documents[iss][1], iss)
        doc = self.client.did_document(iss)
        if doc.get('id') != iss:
            raise Failure('did_document_mismatch', iss)
        key = atproto_key(doc, iss)
        self.documents[iss] = (now + self.document_ttl, doc)
        self.documents.move_to_end(iss)
        while len(self.documents) > self.document_capacity:
            self.documents.popitem(last=False)
        return key

    def authenticate(self, token, method):
        if not token:
            raise Rejected('missing', 'AuthRequired')
        try:
            if len(token) > MAX_TOKEN or not shaped(token):
                raise ValueError('shape')
            head_segment, body_segment, sig_segment = token.split('.')
            head, body, sig = object_of(head_segment), object_of(body_segment), raw(sig_segment)
        except (ValueError, TypeError, binascii.Error, RecursionError):
            raise Rejected('malformed') from None
        if head.get('typ') != 'JWT' or not isinstance(head.get('alg'), str) or head['alg'] not in ALGORITHMS:
            raise Rejected('header')
        alg = head['alg']
        iss, aud, exp, iat, lxm, jti = (body.get(k) for k in ('iss', 'aud', 'exp', 'iat', 'lxm', 'jti'))
        if not isinstance(iss, str) or not DID.fullmatch(iss):
            raise Rejected('issuer')
        if not isinstance(aud, str) or aud not in (self.did, self.did + '#delvetalk'):
            raise Rejected('audience')
        if not isinstance(lxm, str) or lxm != method:
            raise Rejected('method')
        if not isinstance(jti, str) or not jti or len(jti.encode('utf-8', 'surrogatepass')) > 256:
            raise Rejected('nonce')
        message = (head_segment + '.' + body_segment).encode('ascii')
        with self.lock:
            now = self.clock()
            if type(exp) is not int or not now < exp <= now + 300:
                raise Rejected('expiry')
            if 'iat' in body and (type(iat) is not int or iat > now + 30 or exp - iat > 300):
                raise Rejected('issued')
            for identity, until in list(self.seen.items()):
                if until <= now:
                    del self.seen[identity]
            identity = (iss, jti)
            if identity in self.seen:
                raise Rejected('replay')
            try:
                key = self.key(iss, now)
                matches = lambda k: k.curve.name == ALGORITHMS[alg] and verify(k, message, sig)
                if not matches(key) and not matches(self.key(iss, now, refresh=True)):
                    raise Rejected('signature')
            except (Failure, ValueError, KeyError, TypeError, AttributeError):
                raise Rejected('document') from None
            # Resolution can take time: expiry and capacity use the admission clock.
            now = self.clock()
            if exp <= now:
                raise Rejected('expiry')
            for identity_seen, until in list(self.seen.items()):
                if until <= now:
                    del self.seen[identity_seen]
            if len(self.seen) >= self.capacity:
                raise Rejected('nonce_capacity', 'RateLimitExceeded', max(1, math.ceil(min(self.seen.values()) - now)))
            self.seen[identity] = exp
        return iss
