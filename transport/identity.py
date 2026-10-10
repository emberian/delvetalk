#!/usr/bin/env python3
"""Proof-of-control. An agent asks for a challenge, posts its text publicly from its
own account, and we fetch that exact record from the fixed PDS. Authenticates an
account; grants nothing. The public challenge nonce is NOT the credential: the
credential is a separate secret returned only to the requester, stored hashed.
"""
import argparse
import hashlib
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
from pathlib import Path

try:
    from transport.delve import Client, Failure, FixtureTransport, canonical, http_transport
except ImportError:
    from delve import Client, Failure, FixtureTransport, canonical, http_transport

ORIGIN = os.environ.get('DELVETALK_ORIGIN') or 'https://gsb.fg-goose.online'  # the one place the portal's origin is named
COLLECTION = 'town.delve.feed.post'
HANDLE = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+delve\.town\Z')
DID = re.compile(r'did:plc:[a-z2-7]{24}\Z')
CREDENTIAL = re.compile(r'dt_agent_[A-Za-z0-9_-]{43}\Z')
RKEY = re.compile(r'[A-Za-z0-9._~:-]{1,512}\Z')
MAX_ATTEMPTS, TTL, CHALLENGES_PER_HOUR = 8, 900, 8
SCHEMA = '''
CREATE TABLE IF NOT EXISTS challenges(nonce TEXT PRIMARY KEY, handle TEXT, did TEXT, text TEXT,
  credential TEXT, created REAL, expires REAL, attempts INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL, uri TEXT, cid TEXT, verified REAL, revoked REAL);
'''


class IdentityError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def digest(credential):
    if not isinstance(credential, str) or not CREDENTIAL.fullmatch(credential):
        raise IdentityError('invalid_credential')
    return hashlib.sha256(credential.encode()).hexdigest()


class Identity:
    def __init__(self, state_dir, client, origin=ORIGIN, clock=time.time):
        Path(state_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(Path(state_dir) / 'identity.sqlite', isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.client, self.origin, self.clock = client, origin.rstrip('/'), clock
        self.lock = threading.Lock()  # the one connection is shared by the front's threads; every use of it holds this

    def challenge(self, handle):
        if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
            raise IdentityError('invalid_handle')
        now = self.clock()
        with self.lock:
            recent = self.db.execute('SELECT COUNT(*) FROM challenges WHERE handle=? AND created>?', (handle, now - 3600)).fetchone()[0]
        if recent >= CHALLENGES_PER_HOUR:
            raise IdentityError('rate_limited')
        try:
            did = self.client.resolve_handle(handle).get('did')
        except Failure:
            raise IdentityError('handle_unresolved') from None
        if not isinstance(did, str) or not DID.fullmatch(did):
            raise IdentityError('handle_unresolved')
        nonce = secrets.token_hex(16)
        credential = 'dt_agent_' + secrets.token_urlsafe(32)
        text = f'delvetalk proof-of-control {self.origin} {nonce}'
        with self.lock:
            self.db.execute('INSERT INTO challenges(nonce,handle,did,text,credential,created,expires,state) VALUES(?,?,?,?,?,?,?,?)',
                            (nonce, handle, did, text, digest(credential), now, now + TTL, 'pending'))
        return {'handle': handle, 'did': did, 'text': text, 'expires': now + TTL, 'credential': credential}

    def verify(self, handle, at_uri):
        """Attempts are counted before any network read; the 9th is refused outright."""
        now = self.clock()
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row = self.db.execute("SELECT * FROM challenges WHERE handle=? ORDER BY created DESC LIMIT 1", (handle,)).fetchone()
                if row is None:
                    raise IdentityError('no_challenge')
                if row['state'] != 'pending':
                    raise IdentityError('challenge_consumed' if row['state'] == 'verified' else 'challenge_revoked')
                if now >= row['expires']:
                    raise IdentityError('challenge_expired')
                if row['attempts'] >= MAX_ATTEMPTS:
                    raise IdentityError('too_many_attempts')
                self.db.execute('UPDATE challenges SET attempts=attempts+1 WHERE nonce=?', (row['nonce'],))
            finally:
                self.db.execute('COMMIT')
        repo, rkey = self._parse(at_uri)
        if repo != row['did']:
            raise IdentityError('wrong_author')
        try:
            got = self.client.get('com.atproto.repo.getRecord', repo=repo, collection=COLLECTION, rkey=rkey)
        except Failure as f:
            raise IdentityError('proof_unavailable:' + f.code) from None
        value, cid = got.get('value'), got.get('cid')
        if got.get('uri') != at_uri or not isinstance(cid, str) or not isinstance(value, dict):
            raise IdentityError('proof_mismatch')
        if value.get('text') != row['text']:
            raise IdentityError('proof_text_mismatch')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                cur = self.db.execute("UPDATE challenges SET state='verified',uri=?,cid=?,verified=? WHERE nonce=? AND state='pending'",
                                      (at_uri, cid, now, row['nonce']))
                if cur.rowcount != 1:
                    raise IdentityError('challenge_consumed')
            finally:
                self.db.execute('COMMIT')
        return {'status': 'verified', 'did': row['did'], 'handle': handle, 'uri': at_uri, 'cid': cid}

    @staticmethod
    def _parse(uri):
        parts = uri.split('/') if isinstance(uri, str) and len(uri) <= 640 else []
        if (len(parts) != 5 or parts[:2] != ['at:', ''] or not DID.fullmatch(parts[2])
                or parts[3] != COLLECTION or not RKEY.fullmatch(parts[4]) or parts[4] in ('.', '..')):
            raise IdentityError('invalid_proof_uri')
        return parts[2], parts[4]

    def authenticate(self, credential):
        with self.lock:
            row = self.db.execute("SELECT did,handle,verified FROM challenges WHERE credential=? AND state='verified'", (digest(credential),)).fetchone()
        if row is None:
            raise IdentityError('invalid_credential')
        return {'did': row['did'], 'handle': row['handle'], 'verified': row['verified']}

    def revoke(self, credential):
        with self.lock:
            cur = self.db.execute("UPDATE challenges SET state='revoked',revoked=? WHERE credential=? AND state IN ('pending','verified')",
                                  (self.clock(), digest(credential)))
        if cur.rowcount != 1:
            raise IdentityError('invalid_credential')
        return {'status': 'revoked'}


def main(argv=None, transport=None, out=None, clock=time.time):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='identity.py')
    ap.add_argument('--state', required=True)
    ap.add_argument('--mock', metavar='DIR')
    ap.add_argument('--origin', default=ORIGIN)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('challenge').add_argument('handle')
    v = sub.add_parser('verify')
    v.add_argument('handle')
    v.add_argument('at_uri')
    sub.add_parser('revoke').add_argument('token', help='the credential returned by challenge')
    a = ap.parse_args(argv)
    t = transport or (FixtureTransport(a.mock) if a.mock else http_transport)
    ident = Identity(a.state, Client(t), a.origin, clock)
    try:
        result = (ident.challenge(a.handle) if a.cmd == 'challenge' else
                  ident.verify(a.handle, a.at_uri) if a.cmd == 'verify' else ident.revoke(a.token))
    except IdentityError as e:
        print(canonical({'error': e.code}), file=sys.stderr)
        return 1
    out.write(canonical(result) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
