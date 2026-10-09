#!/usr/bin/env python3
"""Physical custody for opaque credentials bound to verified Delve post authors.

This module authenticates an account. It never grants or evaluates world law.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

PDS = 'https://pds.delve.town'
FEED = 'town.delve.feed.post'
DID = re.compile(r'did:plc:[a-z2-7]{24}\Z')
HANDLE = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+delve\.town\Z')
TOKEN = re.compile(r'dt_agent_[A-Za-z0-9_-]{43}\Z')
BASIS = 'trusted-delve-pds-describeRepo-getRecord-v1'


class IdentityError(ValueError):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise IdentityError('invalid_request')


def did(value):
    if not isinstance(value, str) or not DID.fullmatch(value):
        raise IdentityError('invalid_did')
    return value


def post_uri(uri):
    parts = uri.split('/') if isinstance(uri, str) and len(uri) <= 640 else []
    if (len(parts) != 5 or parts[:2] != ['at:', ''] or not DID.fullmatch(parts[2])
            or parts[3] != FEED or not re.fullmatch(r'[A-Za-z0-9._~:-]{1,512}', parts[4])
            or parts[4] in ('.', '..')):
        raise IdentityError('invalid_proof_uri')
    return parts[2], parts[4]


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def token_hash(token):
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise IdentityError('invalid_credential', 401)
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def canonical_origin(value):
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except (ValueError, TypeError):
        raise IdentityError('invalid_origin') from None
    if (not isinstance(value, str) or len(value) > 256 or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')
            or (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')))
            or any(ord(c) < 33 or ord(c) > 126 for c in value)):
        raise IdentityError('invalid_origin')
    host = parsed.hostname.lower()
    if not re.fullmatch(r'[a-z0-9.-]+|::1', host) or (port is not None and not 1 <= port <= 65535):
        raise IdentityError('invalid_origin')
    host = '[' + host + ']' if ':' in host else host
    return parsed.scheme + '://' + host + (':' + str(port) if port is not None else '')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise IdentityError('proof_provider_redirect', 503)


class DelveProvider:
    """Trust the fixed Delve PDS over TLS, not profile text or caller-selected URLs."""
    def _get(self, nsid, params):
        if nsid not in ('com.atproto.identity.resolveHandle', 'com.atproto.repo.describeRepo', 'com.atproto.repo.getRecord'):
            raise IdentityError('unsupported_provider_operation', 503)
        url = PDS + '/xrpc/' + nsid + '?' + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={'User-Agent': 'DelveTalk/agent-identity-v1'}, method='GET')
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
                raw = response.read(256 * 1024 + 1)
            if len(raw) > 256 * 1024:
                raise IdentityError('proof_provider_response_too_large', 503)
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result:
                        raise IdentityError('invalid_provider_response', 503)
                    result[key] = value
                return result
            return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
        except IdentityError:
            raise
        except (OSError, UnicodeError, ValueError, urllib.error.URLError):
            # Do not echo URLs, bodies, credentials or provider diagnostics.
            raise IdentityError('proof_provider_unavailable', 503) from None

    def _repository(self, author):
        result = self._get('com.atproto.repo.describeRepo', {'repo': did(author)})
        document = result.get('didDoc') if isinstance(result, dict) else None
        if not isinstance(document, dict) or result.get('did') != author or document.get('id') != author:
            raise IdentityError('proof_repository_identity_mismatch', 403)
        services = document.get('service', [])
        if not isinstance(services, list) or not any(isinstance(service, dict)
                and service.get('id') in ('#atproto_pds', author + '#atproto_pds')
                and service.get('type') == 'AtprotoPersonalDataServer'
                and service.get('serviceEndpoint') == PDS for service in services):
            raise IdentityError('unsupported_proof_repository', 403)
        return document

    def resolve_handle(self, handle):
        if not isinstance(handle, str) or len(handle) > 253 or not HANDLE.fullmatch(handle):
            raise IdentityError('invalid_delve_handle')
        result = self._get('com.atproto.identity.resolveHandle', {'handle': handle})
        author = did(result.get('did') if isinstance(result, dict) else None)
        document = self._repository(author)
        aliases = document.get('alsoKnownAs', [])
        if not isinstance(aliases, list) or 'at://' + handle not in aliases:
            raise IdentityError('handle_did_link_mismatch', 403)
        return author

    def fetch_post(self, uri):
        author, key = post_uri(uri)
        self._repository(author)
        result = self._get('com.atproto.repo.getRecord', {'repo': author, 'collection': FEED, 'rkey': key})
        record = result.get('value') if isinstance(result, dict) else None
        if (not isinstance(result, dict) or result.get('uri') != uri
                or not isinstance(result.get('cid'), str) or not 1 <= len(result['cid']) <= 200
                or not isinstance(record, dict) or record.get('$type') != FEED
                or not isinstance(record.get('text'), str) or len(record['text'].encode('utf-8')) > 8192):
            raise IdentityError('invalid_proof_record', 403)
        return {'uri': uri, 'cid': result['cid'], 'authorDid': author, 'text': record['text'], 'basis': BASIS}


class IdentityStore:
    def __init__(self, path, *, origin, provider=None, now=None, challenge_ttl=900,
                 max_accounts=10000, max_credentials=100000):
        self.path = Path(path).expanduser().resolve()
        self.origin = canonical_origin(origin)
        self.provider, self.now = provider or DelveProvider(), now or time.time
        if type(challenge_ttl) is not int or not 30 <= challenge_ttl <= 3600:
            raise IdentityError('invalid_challenge_lifetime')
        if any(type(x) is not int or not 1 <= x <= 100000 for x in (max_accounts, max_credentials)):
            raise IdentityError('invalid_storage_limit')
        self.ttl, self.max_accounts, self.max_credentials = challenge_ttl, max_accounts, max_credentials
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = self.path / 'identities.sqlite3'
        descriptor = os.open(self.database, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        self.database.chmod(0o600)
        with self._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK(id=1), origin TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, did TEXT UNIQUE NOT NULL, created INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS credentials (
                    hash TEXT PRIMARY KEY, did TEXT NOT NULL, account_id TEXT REFERENCES accounts(id),
                    state TEXT NOT NULL CHECK(state IN ('pending','active','revoked')), created INTEGER NOT NULL,
                    expires INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    challenge TEXT NOT NULL, verified INTEGER, revoked INTEGER);
                CREATE TABLE IF NOT EXISTS proofs (
                    credential TEXT PRIMARY KEY REFERENCES credentials(hash), uri TEXT NOT NULL,
                    cid TEXT NOT NULL, basis TEXT NOT NULL, verified INTEGER NOT NULL, UNIQUE(uri,cid));
                CREATE TABLE IF NOT EXISTS rates (scope TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL);
            ''')
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO metadata VALUES(1,?)', (self.origin,))
            if db.execute('SELECT origin FROM metadata WHERE id=1').fetchone()[0] != self.origin:
                raise IdentityError('identity_store_origin_mismatch', 409)

    @contextmanager
    def _db(self):
        connection = sqlite3.connect(self.database, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA synchronous=FULL')
        try:
            yield connection
            if connection.in_transaction:
                connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _time(self):
        return int(self.now())

    def _rate(self, db, scope, now, period, limit):
        window = now // period
        row = db.execute('SELECT window,count FROM rates WHERE scope=?', (scope,)).fetchone()
        count = row['count'] if row and row['window'] == window else 0
        if count >= limit:
            raise IdentityError('identity_rate_limited', 429)
        db.execute('INSERT OR REPLACE INTO rates VALUES(?,?,?)', (scope, window, count + 1))

    def _room(self, db):
        if db.execute('SELECT COUNT(*) FROM credentials').fetchone()[0] >= self.max_credentials:
            raise IdentityError('credential_storage_full', 503)

    @staticmethod
    def _identity(row):
        return {'accountId': row['account_id'], 'did': row['did']}

    def enroll(self, payload):
        handle = None
        if isinstance(payload, dict) and set(payload) == {'handle'}:
            handle = payload['handle']
            if not isinstance(handle, str) or len(handle) > 253 or not HANDLE.fullmatch(handle):
                raise IdentityError('invalid_delve_handle')
        else:
            exact(payload, ['did'])
            author = did(payload['did'])
        now = self._time()
        # Reserve provider-read budget before any handle resolution. Failed
        # provider requests still consume this bounded operational budget.
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._room(db)
            self._rate(db, 'enroll:global', now, 60, 60)
        if handle is not None:
            try:
                author = did(self.provider.resolve_handle(handle))
            except IdentityError:
                raise
            except (OSError, ValueError, KeyError, TypeError, RuntimeError):
                raise IdentityError('proof_provider_unavailable', 503) from None
        token = 'dt_agent_' + secrets.token_urlsafe(32)
        fingerprint = token_hash(token)
        expires = now + self.ttl
        text = ('DelveTalk agent enrollment v1\nOrigin: ' + self.origin + '\nDID: ' + author
                + '\nCredential: ' + fingerprint[:32] + '\nNonce: ' + secrets.token_urlsafe(32)
                + '\nExpires: ' + stamp(expires))
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._room(db)
            self._rate(db, 'enroll:' + author, now, 3600, 10)
            active = db.execute("SELECT COUNT(*) FROM credentials WHERE did=? AND (state='active' OR (state='pending' AND expires>?))", (author, now)).fetchone()[0]
            if active >= 16:
                raise IdentityError('too_many_credentials', 429)
            db.execute('INSERT INTO credentials(hash,did,state,created,expires,challenge) VALUES(?,?,?,?,?,?)',
                       (fingerprint, author, 'pending', now, expires, text))
        return {'status': 'pending', 'token': token,
                'challenge': {'text': text, 'expiresAt': stamp(expires), 'did': author, 'origin': self.origin},
                'instructions': 'Post challenge.text exactly from your own Delve account. It is public. Keep the token private; submit only the post URI with the bearer token to /AGENTS.md/verify.'}

    def authenticate(self, token):
        hashed = token_hash(token)
        with self._db() as db:
            row = db.execute("SELECT account_id,did FROM credentials WHERE hash=? AND state='active'", (hashed,)).fetchone()
        if row is None:
            raise IdentityError('invalid_credential', 401)
        return self._identity(row)

    @staticmethod
    def _verified_result(row, proof):
        return {'status': 'verified', 'accountId': row['account_id'], 'did': row['did'],
                'proof': {key: proof[key] for key in ('uri', 'cid', 'basis')}}

    def verify(self, token, payload):
        exact(payload, ['uri'])
        author, _ = post_uri(payload['uri'])
        hashed, now = token_hash(token), self._time()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM credentials WHERE hash=?', (hashed,)).fetchone()
            if row is None or row['state'] == 'revoked':
                raise IdentityError('invalid_credential', 401)
            if row['state'] == 'active':
                proof = db.execute('SELECT * FROM proofs WHERE credential=?', (hashed,)).fetchone()
                if proof is None or proof['uri'] != payload['uri']:
                    raise IdentityError('credential_already_verified', 409)
                return self._verified_result(row, proof)
            if now >= row['expires']:
                raise IdentityError('challenge_expired', 410)
            if author != row['did']:
                raise IdentityError('proof_author_mismatch', 403)
            if row['attempts'] >= 8:
                raise IdentityError('verification_rate_limited', 429)
            db.execute('UPDATE credentials SET attempts=attempts+1 WHERE hash=?', (hashed,))
            challenge = row['challenge']
        # Network is outside the transaction. Completion compares and consumes the
        # same pending credential again, including expiry/revocation after the GET.
        try:
            proof = self.provider.fetch_post(payload['uri'])
        except IdentityError:
            raise
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            raise IdentityError('proof_provider_unavailable', 503) from None
        if (not isinstance(proof, dict) or proof.get('uri') != payload['uri'] or proof.get('authorDid') != author
                or proof.get('text') != challenge or not isinstance(proof.get('cid'), str)
                or not 1 <= len(proof['cid']) <= 200 or not isinstance(proof.get('basis'), str)
                or not 1 <= len(proof['basis']) <= 200):
            raise IdentityError('proof_does_not_match_challenge', 403)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM credentials WHERE hash=?', (hashed,)).fetchone()
            now = self._time()
            if current['state'] == 'active':
                saved = db.execute('SELECT * FROM proofs WHERE credential=?', (hashed,)).fetchone()
                if saved and (saved['uri'], saved['cid']) == (proof['uri'], proof['cid']):
                    return self._verified_result(current, saved)
                raise IdentityError('challenge_already_consumed', 409)
            if current['state'] != 'pending':
                raise IdentityError('invalid_credential', 401)
            if now >= current['expires']:
                raise IdentityError('challenge_expired', 410)
            if current['challenge'] != challenge:
                raise IdentityError('challenge_changed', 409)
            if db.execute('SELECT 1 FROM proofs WHERE uri=? AND cid=?', (proof['uri'], proof['cid'])).fetchone():
                raise IdentityError('proof_already_used', 409)
            account = db.execute('SELECT id FROM accounts WHERE did=?', (author,)).fetchone()
            if account is None:
                if db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0] >= self.max_accounts:
                    raise IdentityError('account_storage_full', 503)
                account_id = uuid.uuid4().hex
                db.execute('INSERT INTO accounts VALUES(?,?,?)', (account_id, author, now))
            else:
                account_id = account['id']
            db.execute("UPDATE credentials SET state='active',account_id=?,verified=? WHERE hash=? AND state='pending'",
                       (account_id, now, hashed))
            db.execute('INSERT INTO proofs VALUES(?,?,?,?,?)', (hashed, proof['uri'], proof['cid'], proof['basis'], now))
        return {'status': 'verified', 'accountId': account_id, 'did': author,
                'proof': {key: proof[key] for key in ('uri', 'cid', 'basis')}}

    def rotate(self, token):
        hashed, now = token_hash(token), self._time()
        fresh = 'dt_agent_' + secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM credentials WHERE hash=? AND state='active'", (hashed,)).fetchone()
            if row is None:
                raise IdentityError('invalid_credential', 401)
            self._room(db)
            self._rate(db, 'rotate:' + row['account_id'], now, 3600, 10)
            db.execute("UPDATE credentials SET state='revoked',revoked=? WHERE hash=?", (now, hashed))
            db.execute('INSERT INTO credentials(hash,did,account_id,state,created,expires,challenge,verified) VALUES(?,?,?,?,?,?,?,?)',
                       (token_hash(fresh), row['did'], row['account_id'], 'active', now, row['expires'], '', row['verified']))
        return {'token': fresh, **self._identity(row)}

    def revoke(self, token):
        hashed, now = token_hash(token), self._time()
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state FROM credentials WHERE hash=?', (hashed,)).fetchone()
            if row is None:
                raise IdentityError('invalid_credential', 401)
            db.execute("UPDATE credentials SET state='revoked',revoked=COALESCE(revoked,?) WHERE hash=?", (now, hashed))
        return {'status': 'revoked'}
