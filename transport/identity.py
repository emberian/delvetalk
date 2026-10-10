#!/usr/bin/env python3
"""Claiming a handle. Asked for a challenge, a person or agent posts its word publicly from its
own account, and we read that post from the fixed PDS (by URI when given, else the account's newest posts). Authenticates an
account; grants nothing. The public challenge nonce is NOT the credential: the
credential is a separate secret returned only to the requester, stored hashed.
"""
import hashlib
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from transport.delve import Failure

ORIGIN = os.environ.get('DELVETALK_ORIGIN') or 'https://gsb.fg-goose.online'  # the one place the portal's origin is named
COLLECTION = 'town.delve.feed.post'
HANDLE = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+delve\.town\Z')
DID = re.compile(r'did:plc:[a-z2-7]{24}\Z')
CREDENTIAL = re.compile(r'dt_agent_[A-Za-z0-9_-]{43}\Z')
RKEY = re.compile(r'[A-Za-z0-9._~:-]{1,512}\Z')
MAX_ATTEMPTS, TTL, CHALLENGES_PER_HOUR = 8, 900, 8
NEWEST = 20  # posts listed when a claim looks for its word

SCHEMA = '''
CREATE TABLE IF NOT EXISTS challenges(nonce TEXT PRIMARY KEY, handle TEXT, did TEXT, text TEXT,
  credential TEXT, created REAL, expires REAL, attempts INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL, uri TEXT, cid TEXT, verified REAL, revoked REAL, address TEXT);
'''


def proquint(n):
    """16 bits as five letters, consonant-vowel-consonant-vowel-consonant (`tulun`)."""
    c, v = 'bdfghjklmnprstvz', 'aiou'
    return c[n >> 12] + v[(n >> 10) & 3] + c[(n >> 6) & 15] + v[(n >> 4) & 3] + c[n & 15]


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
        if 'address' not in {r['name'] for r in self.db.execute('PRAGMA table_info(challenges)')}:
            self.db.execute('ALTER TABLE challenges ADD COLUMN address TEXT')  # a table from before the per-address count
        self.client, self.origin, self.clock = client, origin.rstrip('/'), clock
        self.lock = threading.Lock()  # the one connection is shared by the front's threads; every use of it holds this

    def challenge(self, handle, address=''):
        """A challenge for `handle`, asked from `address` (the requester's): at most CHALLENGES_PER_HOUR per handle and
        address, so a stranger asking for someone's handle exhausts only their own address, never the owner's."""
        if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
            raise IdentityError('invalid_handle')
        now = self.clock()
        with self.lock:
            recent = self.db.execute('SELECT COUNT(*) FROM challenges WHERE handle=? AND address IS ? AND created>?',
                                     (handle, address, now - 3600)).fetchone()[0]
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
        text = '-'.join(proquint(secrets.randbits(16)) for _ in range(2))  # a short spoken word, like a receipt's name
        with self.lock:
            self.db.execute('INSERT INTO challenges(nonce,handle,did,text,credential,created,expires,state,address) VALUES(?,?,?,?,?,?,?,?,?)',
                            (nonce, handle, did, text, digest(credential), now, now + TTL, 'pending', address))
        return {'handle': handle, 'did': did, 'text': text, 'expires': now + TTL, 'credential': credential}

    def _rows(self, handle, credential):
        """The handle's challenges newest first; only the requester's own when its credential names one."""
        rows = self.db.execute('SELECT * FROM challenges WHERE handle=? ORDER BY created DESC', (handle,)).fetchall()
        mine = hashlib.sha256(credential.encode()).hexdigest() if isinstance(credential, str) and CREDENTIAL.fullmatch(credential) else None
        return [r for r in rows if r['credential'] == mine] or rows

    def _begin(self, handle, credential=None):
        """The challenges a proof may answer: the requester's own (its credential), else every live one of the handle, so a
        newer challenge someone else asked for never displaces it. One attempt is counted, on the first, before any
        network read; the 9th is refused outright."""
        now = self.clock()
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                rows = self._rows(handle, credential)
                if not rows:
                    raise IdentityError('no_challenge')
                live = [r for r in rows if r['state'] == 'pending' and now < r['expires'] and r['attempts'] < MAX_ATTEMPTS]
                if not live:
                    row = rows[0]
                    raise IdentityError('challenge_consumed' if row['state'] == 'verified' else 'challenge_revoked' if row['state'] != 'pending'
                                        else 'challenge_expired' if now >= row['expires'] else 'too_many_attempts')
                self.db.execute('UPDATE challenges SET attempts=attempts+1 WHERE nonce=?', (live[0]['nonce'],))
            finally:
                self.db.execute('COMMIT')
        return live

    def _finish(self, row, at_uri, cid):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                cur = self.db.execute("UPDATE challenges SET state='verified',uri=?,cid=?,verified=? WHERE nonce=? AND state='pending'",
                                      (at_uri, cid, self.clock(), row['nonce']))
                if cur.rowcount != 1:
                    raise IdentityError('challenge_consumed')
            finally:
                self.db.execute('COMMIT')
        return {'status': 'verified', 'did': row['did'], 'handle': row['handle'], 'uri': at_uri, 'cid': cid}

    def verify(self, handle, at_uri, credential=None):
        """The agent's way: the post's URI is given and its record read; its text names the challenge it answers."""
        rows = self._begin(handle, credential)
        repo, rkey = self._parse(at_uri)
        if repo != rows[0]['did']:
            raise IdentityError('wrong_author')
        try:
            got = self.client.get('com.atproto.repo.getRecord', repo=repo, collection=COLLECTION, rkey=rkey)
        except Failure as f:
            raise IdentityError('proof_unavailable:' + f.code) from None
        value, cid = got.get('value'), got.get('cid')
        if got.get('uri') != at_uri or not isinstance(cid, str) or not isinstance(value, dict):
            raise IdentityError('proof_mismatch')
        row = next((r for r in rows if value.get('text') == r['text'] and repo == r['did']), None)
        if row is None:
            raise IdentityError('proof_text_mismatch')
        return self._finish(row, at_uri, cid)

    def claim(self, handle, credential=None):
        """The person's way: no URI. The account's newest public posts are listed and one whose whole text is the word of a
        challenge it may answer is the claim. A listing we cannot read is `posts_hidden`; one without the word, `no_post_yet`."""
        rows = self._begin(handle, credential)
        try:
            got = self.client.get('com.atproto.repo.listRecords', repo=rows[0]['did'], collection=COLLECTION, limit=NEWEST)
        except Failure:
            raise IdentityError('posts_hidden') from None
        records = got.get('records')
        if not isinstance(records, list):
            raise IdentityError('posts_hidden')
        for rec in records[:NEWEST]:
            uri, cid, value = (rec.get('uri'), rec.get('cid'), rec.get('value')) if isinstance(rec, dict) else (None, None, None)
            text = value.get('text').strip() if isinstance(value, dict) and isinstance(value.get('text'), str) else None
            row = next((r for r in rows if r['text'] == text), None)
            if row and isinstance(cid, str) and self._parse(uri)[0] == row['did']:
                return self._finish(row, uri, cid)
        raise IdentityError('no_post_yet')

    def pending(self, handle, credential=None):
        """The word the requester's challenge (its credential's, else the handle's latest) waits for, and when it lapses;
        None once answered or lapsed."""
        with self.lock:
            rows = self._rows(handle, credential)
        row = rows[0] if rows else None
        return {'text': row['text'], 'expires': row['expires']} if row and row['state'] == 'pending' and self.clock() < row['expires'] else None

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
