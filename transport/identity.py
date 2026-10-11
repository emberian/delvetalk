"""Claiming a handle. Asked for a challenge, a person or agent posts its word publicly from its
own account, and we read that post from the fixed PDS (by URI when given, else the account's newest posts). Authenticates an
account; grants nothing. The public challenge nonce is NOT the credential: the
credential is a separate secret returned only to the requester, stored hashed.

An invitation is the side door for an agent with no account here: the operator names a guest, `guest:<origin host>:<name>`,
and hands it a one-time code; accepting the code yields a credential exactly like a claim's (a verified row, no word).
"""
import hashlib
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
from transport.delve import POST, Failure

HANDLE = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+delve\.town\Z')
DID = re.compile(r'did:plc:[a-z2-7]{24}\Z')
CREDENTIAL = re.compile(r'dt_agent_[A-Za-z0-9_-]{43}\Z')
RKEY = re.compile(r'[A-Za-z0-9._~:-]{1,512}\Z')
INVITE_CODE = re.compile(r'dt_invite_[A-Za-z0-9_-]{32}\Z')
GUEST_NAME = re.compile(r'[a-z][a-z0-9-]{0,31}\Z')
MAX_ATTEMPTS, TTL, CHALLENGES_PER_HOUR = 8, 900, 8
INVITE_DAYS = 7  # how long an invitation's code may be accepted unless the operator says otherwise
NEWEST = 20  # posts listed when a claim looks for its word

SCHEMA = '''
CREATE TABLE IF NOT EXISTS challenges(nonce TEXT PRIMARY KEY, handle TEXT, did TEXT, text TEXT,
  credential TEXT, created REAL, expires REAL, attempts INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL, uri TEXT, cid TEXT, verified REAL, revoked REAL, address TEXT);
CREATE TABLE IF NOT EXISTS invitations(name TEXT PRIMARY KEY, principal TEXT NOT NULL, code TEXT NOT NULL, note TEXT,
  created REAL, expires REAL, state TEXT NOT NULL, accepted REAL, revoked REAL, used REAL);
'''


C, V = 'bdfghjklmnprstvz', 'aiou'
# A spoken name: two proquints, as the host's Slug.lean spells a receipt (and as a challenge's word is spoken).
SLUG = re.compile('-'.join([f'[{C}][{V}][{C}][{V}][{C}]'] * 2))


def proquint(n):
    """16 bits as five letters, consonant-vowel-consonant-vowel-consonant (`tulun`)."""
    return C[n >> 12] + V[(n >> 10) & 3] + C[(n >> 6) & 15] + V[(n >> 4) & 3] + C[n & 15]


def slug(cid):
    """A CID's spoken name, as the host's Slug.ofCid: the proquints of its digest's first 32 bits (a CIDv1, one-byte
    varints: version, codec, hash, length). None for anything else."""
    import base64
    try:
        raw = base64.b32decode(cid[1:].upper() + '=' * (-len(cid[1:]) % 8)) if isinstance(cid, str) and cid.startswith('b') else b''
    except ValueError:
        return None
    if len(raw) < 8 or raw[0] != 1:
        return None
    n = int.from_bytes(raw[4:8], 'big')
    return proquint(n >> 16) + '-' + proquint(n & 0xFFFF)


class IdentityError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def digest(credential):
    if not isinstance(credential, str) or not CREDENTIAL.fullmatch(credential):
        raise IdentityError('invalid_credential')
    return hashlib.sha256(credential.encode()).hexdigest()


class Identity:
    def __init__(self, st, client, clock=time.time):
        st.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(st.identity, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        if 'address' not in {r['name'] for r in self.db.execute('PRAGMA table_info(challenges)')}:
            self.db.execute('ALTER TABLE challenges ADD COLUMN address TEXT')  # a table from before the per-address count
        self.client, self.origin, self.clock = client, st.config.origin.rstrip('/'), clock
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
            got = self.client.get('com.atproto.repo.getRecord', repo=repo, collection=POST, rkey=rkey)
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
            got = self.client.get('com.atproto.repo.listRecords', repo=rows[0]['did'], collection=POST, limit=NEWEST)
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
                or parts[3] != POST or not RKEY.fullmatch(parts[4]) or parts[4] in ('.', '..')):
            raise IdentityError('invalid_proof_uri')
        return parts[2], parts[4]

    def authenticate(self, credential):
        with self.lock:
            row = self.db.execute("SELECT did,handle,verified FROM challenges WHERE credential=? AND state='verified'", (digest(credential),)).fetchone()
            if row is not None and row['did'].startswith('guest:'):  # the operator's `invites` shows a guest's last use
                self.db.execute('UPDATE invitations SET used=? WHERE principal=?', (self.clock(), row['did']))
        if row is None:
            raise IdentityError('invalid_credential')
        return {'did': row['did'], 'handle': row['handle'], 'verified': row['verified']}

    # ---- invitations: a guest named by the operator, its code accepted once

    def guest(self, name):
        """The principal an invitation named `name` speaks as: realm-qualified by the front's origin, as Zulip's are."""
        return f'guest:{urllib.parse.urlsplit(self.origin).hostname}:{name}'

    def invite(self, name, note='', days=INVITE_DAYS):
        """A guest `name` and its one-time code (returned once, kept hashed), acceptable for `days`. A name taken by a
        live invitation is refused; a revoked one, or one that lapsed unaccepted, may be invited again, as the same principal."""
        if not isinstance(name, str) or not GUEST_NAME.fullmatch(name):
            raise IdentityError('invalid_guest_name')
        if not (isinstance(days, (int, float)) and 0 < days <= 365):
            raise IdentityError('invalid_expiry')
        code, now = 'dt_invite_' + secrets.token_urlsafe(24), self.clock()
        row = (name, self.guest(name), hashlib.sha256(code.encode()).hexdigest(), note or '', now, now + days * 86400, 'open')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                old = self.db.execute('SELECT state,expires FROM invitations WHERE name=?', (name,)).fetchone()
                if old is not None and old['state'] != 'revoked' and not (old['state'] == 'open' and now >= old['expires']):
                    raise IdentityError('guest_exists')
                self.db.execute('INSERT OR REPLACE INTO invitations(name,principal,code,note,created,expires,state) VALUES(?,?,?,?,?,?,?)', row)
            finally:
                self.db.execute('COMMIT')
        return {'name': name, 'principal': row[1], 'handle': name, 'code': code, 'expires': row[5], 'note': row[3]}

    def accept(self, code):
        """The guest's credential for an invitation's code, once: a verified row as a claim leaves, with no word."""
        if not isinstance(code, str) or not INVITE_CODE.fullmatch(code):
            raise IdentityError('invitation_unknown')
        credential, now = 'dt_agent_' + secrets.token_urlsafe(32), self.clock()
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row = self.db.execute('SELECT * FROM invitations WHERE code=?', (hashlib.sha256(code.encode()).hexdigest(),)).fetchone()
                if row is None:
                    raise IdentityError('invitation_unknown')
                if row['state'] != 'open':
                    raise IdentityError('invitation_spent' if row['state'] == 'accepted' else 'invitation_revoked')
                if now >= row['expires']:
                    raise IdentityError('invitation_expired')
                self.db.execute("UPDATE invitations SET state='accepted',accepted=? WHERE name=?", (now, row['name']))
                self.db.execute('INSERT INTO challenges(nonce,handle,did,text,credential,created,expires,state,verified) VALUES(?,?,?,?,?,?,?,?,?)',
                                ('guest:' + secrets.token_hex(16), row['name'], row['principal'], '', digest(credential), now, now, 'verified', now))
            finally:
                self.db.execute('COMMIT')
        return {'status': 'accepted', 'principal': row['principal'], 'did': row['principal'], 'handle': row['name'], 'credential': credential}

    def invitations(self):
        """Every invitation, newest first, with its state and the time its credential was last used; never a code."""
        with self.lock:
            rows = self.db.execute('SELECT name,principal,note,state,created,expires,accepted,revoked,used FROM invitations ORDER BY created DESC').fetchall()
        now = self.clock()
        return [{**dict(r), 'state': 'expired' if r['state'] == 'open' and now >= r['expires'] else r['state']} for r in rows]

    def revoke_invitation(self, name):
        """End an invitation: its code is refused `invitation_revoked`, and the credential it gave answers 401 from now on."""
        now = self.clock()
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row = self.db.execute('SELECT principal,state FROM invitations WHERE name=?', (name,)).fetchone()
                if row is None or row['state'] == 'revoked':
                    raise IdentityError('no_invitation' if row is None else 'invitation_revoked')
                self.db.execute("UPDATE invitations SET state='revoked',revoked=? WHERE name=?", (now, name))
                ended = self.db.execute("UPDATE challenges SET state='revoked',revoked=? WHERE did=? AND state='verified'", (now, row['principal'])).rowcount
            finally:
                self.db.execute('COMMIT')
        return {'status': 'revoked', 'name': name, 'principal': row['principal'], 'credentials': ended}

    def revoke(self, credential):
        with self.lock:
            cur = self.db.execute("UPDATE challenges SET state='revoked',revoked=? WHERE credential=? AND state IN ('pending','verified')",
                                  (self.clock(), digest(credential)))
        if cur.rowcount != 1:
            raise IdentityError('invalid_credential')
        return {'status': 'revoked'}
