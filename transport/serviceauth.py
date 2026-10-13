"""Method-bound service JWTs under the resident's #atproto key (ATPROTO §2(b)).

The resident signs an audience, not an HTTP forwarder. Bare and #delvetalk
audiences name this same service; neither authorizes any other method.
"""
import base64
import binascii
import fcntl
import json
import math
import os
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, TimeoutError as FetchTimeout
from contextlib import contextmanager
from pathlib import Path

from transport.atproto.sign import verify
from transport.delve import DID, Failure, TIMEOUT
from transport.repo import Refusal, XRPC_ERRORS
from transport.requests import atproto_key
from transport.state import State

SHAPE = re.compile(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\Z')
MAX_TOKEN = 16 * 1024
SEEN_CAPACITY, DOCUMENT_CAPACITY, DOCUMENT_TTL = 10_000, 1024, 60
FETCH_CAPACITY = 32
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
    """Bounded issuer fetches and durable, atomic replay admission."""
    def __init__(self, did, client, ledger, clock=time.time, capacity=SEEN_CAPACITY,
                 document_capacity=DOCUMENT_CAPACITY, document_ttl=DOCUMENT_TTL,
                 document_timeout=TIMEOUT, fetch_capacity=FETCH_CAPACITY, limited=None):
        if (capacity < 1 or document_capacity < 1 or document_ttl <= 0 or
                document_timeout <= 0 or fetch_capacity < 1):
            raise ValueError('service-auth bounds must be positive')
        self.did, self.client, self.ledger, self.clock = did, client, Path(ledger), clock
        self.capacity, self.document_capacity, self.document_ttl = capacity, document_capacity, document_ttl
        self.document_timeout, self.fetch_capacity, self.limited = document_timeout, fetch_capacity, limited
        self.seen, self.documents, self.fetches, self.lock = {}, OrderedDict(), {}, threading.Lock()

    @contextmanager
    def nonces(self):
        """The directory lock survives atomic ledger replacement and coordinates front instances."""
        with self.lock:
            try:
                missing, parent = [], self.ledger.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                self.ledger.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                for directory in reversed(missing):
                    parent_fd = os.open(directory.parent, os.O_RDONLY)
                    try:
                        os.fsync(parent_fd)
                    finally:
                        os.close(parent_fd)
                fd = os.open(self.ledger.parent, os.O_RDONLY)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    rows = json.loads(self.ledger.read_text()) if self.ledger.exists() else []
                    if not isinstance(rows, list):
                        raise ValueError('nonce ledger')
                    seen, now = {}, self.clock()
                    for row in rows:
                        if (not isinstance(row, list) or len(row) != 4 or
                                not all(isinstance(x, str) and x for x in row[:3]) or type(row[3]) is not int):
                            raise ValueError('nonce ledger')
                        audience, issuer, jti, exp = row
                        if exp > now:
                            seen[(audience, issuer, jti)] = exp
                    self.seen = seen
                    yield fd
                finally:
                    os.close(fd)
            except (OSError, ValueError):
                raise Rejected('nonce_store', 'HostUnavailable') from None

    def fetch(self, iss, pending, deadline):
        """Publish one fetch result; a timed-out worker retains its bounded slot until it exits."""
        key, error = None, None
        try:
            doc = self.client.did_document(iss)
            if doc.get('id') != iss:
                raise Failure('did_document_mismatch', iss)
            key = atproto_key(doc, iss)
        except Exception as got:
            error = got
        with self.lock:
            if time.monotonic() >= deadline:
                error = Failure('document_timeout')
            if error is None:
                self.documents[iss] = (self.clock() + self.document_ttl, key)
                self.documents.move_to_end(iss)
                while len(self.documents) > self.document_capacity:
                    self.documents.popitem(last=False)
            del self.fetches[iss]
            if error is None:
                pending.set_result(key)
            else:
                pending.set_exception(error)

    def key(self, iss, source, stale=None):
        with self.lock:
            now = self.clock()
            for did, (until, _) in list(self.documents.items()):
                if until <= now:
                    del self.documents[did]
            cached = self.documents.get(iss)
            if cached and (stale is None or cached[1] is not stale):
                self.documents.move_to_end(iss)
                return cached[1]
            if iss in self.fetches:
                deadline, pending = self.fetches[iss]
            else:
                if len(self.fetches) >= self.fetch_capacity:
                    raise Rejected('document_capacity', 'RateLimitExceeded', 1)
                wait = self.limited('serviceauth:' + source) if self.limited is not None else 0
                if wait:
                    raise Rejected('document_rate', 'RateLimitExceeded', wait)
                deadline, pending = time.monotonic() + self.document_timeout, Future()
                self.fetches[iss] = (deadline, pending)
                try:
                    threading.Thread(target=self.fetch, args=(iss, pending, deadline), daemon=True).start()
                except Exception:
                    del self.fetches[iss]
                    raise
        try:
            return pending.result(timeout=max(0, deadline - time.monotonic()))
        except FetchTimeout:
            raise Failure('document_timeout') from None

    def authenticate(self, token, method, source=''):
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
        try:
            if not isinstance(jti, str) or not jti or len(jti.encode('utf-8')) > 256:
                raise ValueError('nonce')
        except ValueError:
            raise Rejected('nonce') from None
        message = (head_segment + '.' + body_segment).encode('ascii')
        now = self.clock()
        if type(exp) is not int or not now < exp <= now + 300:
            raise Rejected('expiry')
        if 'iat' in body and (type(iat) is not int or iat > now + 30 or exp - iat > 300):
            raise Rejected('issued')
        identity = (self.did, iss, jti)
        with self.nonces():
            if identity in self.seen:
                raise Rejected('replay')
        try:
            key = self.key(iss, source)
            matches = lambda k: k.curve.name == ALGORITHMS[alg] and verify(k, message, sig)
            if not matches(key) and not matches(self.key(iss, source, stale=key)):
                raise Rejected('signature')
        except (Failure, ValueError, KeyError, TypeError, AttributeError):
            raise Rejected('document') from None
        with self.nonces() as fd:
            now = self.clock()
            if exp <= now:
                raise Rejected('expiry')
            if identity in self.seen:
                raise Rejected('replay')
            if len(self.seen) >= self.capacity:
                raise Rejected('nonce_capacity', 'RateLimitExceeded', max(1, math.ceil(min(self.seen.values()) - now)))
            consumed = {**self.seen, identity: exp}
            State.write(self.ledger, [[*nonce, until] for nonce, until in consumed.items()])
            os.fsync(fd)
            self.seen = consumed
        return iss
