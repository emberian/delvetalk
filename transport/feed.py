"""The town's own feed: a third transport beside delve.town and Zulip, so a playtest needs neither (docs/WEB.md "The town's own feed").

A signed-in resident (a guest by invitation, or a claimed delve.town handle) posts at `/feed` or `POST /AGENTS.md/feed`;
the post is kept here as a `town.delve.feed.post` record under the world's own did:web, threaded by `reply {parent,
root}` as a delve.town post is. The bridge observes it through observe.py exactly as it observes a delve.town post (one
observation, one pipeline: reach, hob, try, plans, tellings, receipts by post, the quota all the host's), and the town's
replies to feed posts are posted back into the feed by the bridge at once, each reserved (`feed`, a source the hour's
delve.town quota does not count) and recorded with the host (`world-posted`), so a reply under one reaches its card.
Nothing here decides anything: what a post reaches and what answers it are the host's.

Two differences from a delve.town post, both because the feed is the town's own room: a top-level post is said to the
town (it summons, as a delve.town post tagging the world does), and `@name` mentions a guest by the name they registered
(a delve.town handle is mentioned as there).
"""
import hashlib
import json
import sqlite3
import threading
import time
import urllib.parse
from datetime import datetime, timezone

from transport import observe, post
from transport.atproto.sign import tid
from transport.delve import POST as COLLECTION, Failure, canonical
from transport.observe import MAX_TEXT, Observer
from transport.repo import world_origin

SCHEMA = '''
CREATE TABLE IF NOT EXISTS feed(seq INTEGER PRIMARY KEY AUTOINCREMENT, uri TEXT UNIQUE NOT NULL, cid TEXT NOT NULL,
  did TEXT NOT NULL, handle TEXT NOT NULL, created TEXT NOT NULL, text TEXT NOT NULL, parent TEXT, root TEXT,
  town INTEGER NOT NULL DEFAULT 0, answers TEXT, receipt TEXT, intent TEXT UNIQUE);
CREATE INDEX IF NOT EXISTS feed_answers ON feed(parent, town);
CREATE INDEX IF NOT EXISTS feed_replies ON feed(root, seq);
CREATE INDEX IF NOT EXISTS feed_author_created ON feed(did, created) WHERE town=0;
CREATE TABLE IF NOT EXISTS feed_threads(root TEXT PRIMARY KEY, last_seq INTEGER NOT NULL UNIQUE);
'''
PAGE = 30  # total posts, including roots, in one response
PAGE_BYTES = 2 * 1024 * 1024
HOUR_POSTS = 60  # posts one resident may make to the feed in an hour (the town's own replies are not counted)
GUEST_MENTION = __import__('re').compile(r'(?<![\w.@])@([a-z][a-z0-9-]{0,31})\b(?![.\w])')


FEED_POLL = 2  # seconds the bridge looks at the feed between its whole steps: a feed post is answered within this


def exists(st):
    return (st.home / 'feed.sqlite').exists()


def waiting(st):
    """Whether the feed holds a resident's post the observer has not seen (the bridge's cue to step at once)."""
    if not exists(st):
        return False
    import sqlite3 as q
    db = q.connect(st.home / 'feed.sqlite', timeout=10)
    try:
        last = db.execute('SELECT uri FROM feed WHERE town=0 ORDER BY seq DESC LIMIT 1').fetchone()
    finally:
        db.close()
    if last is None or not st.observed.exists():
        return last is not None
    ob = q.connect(st.observed, timeout=10)
    try:
        return ob.execute('SELECT 1 FROM posts WHERE uri=?', (last[0],)).fetchone() is None
    finally:
        ob.close()


def authority(origin, world='town'):
    """The did:web the feed's posts are records of: the world's host (never a port, which an AT URI cannot carry)."""
    return 'did:web:' + (urllib.parse.urlsplit(world_origin(origin, world)).hostname or 'localhost')


def is_feed(uri, origin, world='town'):
    return isinstance(uri, str) and uri.startswith(f'at://{authority(origin, world)}/{COLLECTION}/')


class Feed:
    """The feed's store (`<world>/feed.sqlite`), shared by the front (residents' posts) and the bridge (the town's)."""

    def __init__(self, st):
        st.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.st, self.origin, self.world = st, st.config.origin, st.world
        self.db = sqlite3.connect(st.home / 'feed.sqlite', isolation_level=None, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
        columns = {r['name'] for r in self.db.execute('PRAGMA table_info(feed)')}
        for name in ('submission_key', 'payload_digest'):
            if name not in columns:
                self.db.execute(f'ALTER TABLE feed ADD COLUMN {name} TEXT')
        self.db.execute('CREATE UNIQUE INDEX IF NOT EXISTS feed_submission ON feed(did, submission_key)')
        if self.db.execute('PRAGMA user_version').fetchone()[0] == 0:
            self.db.execute('INSERT INTO feed_threads SELECT COALESCE(root, uri), MAX(seq) FROM feed GROUP BY COALESCE(root, uri)')
            self.db.execute('DROP INDEX IF EXISTS feed_root')
            self.db.execute('PRAGMA user_version=1')
        self.db.execute('COMMIT')
        self.lock = threading.Lock()

    def close(self):
        self.db.close()

    @property
    def town(self):
        """The feed's own author: the world's did:web, named as the town's address (`summon_handle`)."""
        return {'did': authority(self.origin, self.world), 'handle': self.st.config.summon_handle}

    def get(self, uri):
        with self.lock:
            return self.db.execute('SELECT * FROM feed WHERE uri=?', (uri,)).fetchone()

    def answered(self, uri):
        with self.lock:
            return self.db.execute('SELECT 1 FROM feed WHERE parent=? AND town=1 LIMIT 1', (uri,)).fetchone() is not None

    def post(self, author, text, reply_to=None, now=None, town=False, answers=None, receipt=None, intent=None,
             idempotency_key=None):
        """Persist a post, its retry identity and hourly admission in one writer transaction.
        Town drafts retain their intent; resident submissions bind a key to their text and parent."""
        if not isinstance(text, str) or not text.strip():
            raise Failure('empty_post', 'say something')
        try:
            size = len(text.encode())
        except UnicodeEncodeError:
            raise Failure('invalid_post', 'post text must be Unicode without lone surrogates')
        if size > MAX_TEXT:
            raise Failure('post_body_too_large', f'at most {MAX_TEXT} bytes')
        if reply_to is not None and not isinstance(reply_to, str):
            raise Failure('invalid_parent', 'reply_to must be a post URI')
        if idempotency_key is not None and (not isinstance(idempotency_key, str) or
                not 1 <= len(idempotency_key) <= 128 or not idempotency_key.isascii() or
                any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key)):
            raise Failure('invalid_idempotency_key', 'idempotencyKey must be 1 to 128 printable ASCII characters')
        digest = hashlib.sha256(canonical({'text': text, 'reply_to': reply_to or None}).encode()).hexdigest()
        now = time.time() if now is None else now
        micros = int(now * 1e6)
        created = datetime.fromtimestamp(micros / 1e6, tz=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        since = datetime.fromtimestamp(now - 3600, tz=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                kept = None
                if intent:
                    kept = self.db.execute('SELECT * FROM feed WHERE intent=?', (intent,)).fetchone()
                elif idempotency_key is not None:
                    kept = self.db.execute('SELECT * FROM feed WHERE did=? AND submission_key=?',
                                           (author['did'], idempotency_key)).fetchone()
                    if kept is not None and kept['payload_digest'] != digest:
                        raise Failure('idempotency_conflict', 'this author already used idempotencyKey with a different payload')
                if kept is None:
                    parent = self.db.execute('SELECT * FROM feed WHERE uri=?', (reply_to,)).fetchone() if reply_to else None
                    if reply_to and parent is None:
                        raise Failure('unknown_post', f'{reply_to} is not a post of this feed')
                    if not town and self.db.execute('SELECT COUNT(*) FROM feed WHERE did=? AND town=0 AND created>=?',
                                                    (author['did'], since)).fetchone()[0] >= HOUR_POSTS:
                        raise Failure('feed_quota', f'at most {HOUR_POSTS} posts an hour to the feed from one resident')
                    seq = self.db.execute('SELECT COALESCE(MAX(seq), 0) + 1 FROM feed').fetchone()[0]
                    uri = f"at://{authority(self.origin, self.world)}/{COLLECTION}/{tid(micros, seq & 1023)}"
                    cid = 'feed' + hashlib.sha256(canonical({'uri': uri, 'text': text, 'did': author['did']}).encode()).hexdigest()[:32]
                    root = (parent['root'] or parent['uri']) if parent else None
                    self.db.execute('INSERT INTO feed(uri,cid,did,handle,created,text,parent,root,town,answers,receipt,intent,submission_key,payload_digest) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                    (uri, cid, author['did'], author['handle'], created, text, parent['uri'] if parent else None,
                                     root, int(town), answers, receipt, intent, idempotency_key, digest))
                    self.db.execute('INSERT INTO feed_threads(root,last_seq) VALUES(?,?) ON CONFLICT(root) DO UPDATE SET last_seq=excluded.last_seq',
                                    (root or uri, seq))
                    kept = self.db.execute('SELECT * FROM feed WHERE uri=?', (uri,)).fetchone()
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
        return kept

    def record(self, row):
        """A post as delve.town's postView carries it: the same record the observer reads (and the archive keeps), a
        guest's `@name` a mention facet naming them, as a delve.town client's facet names a handle's DID."""
        names = {r['handle']: r['did'] for r in self.authors()}
        host = urllib.parse.urlsplit(self.origin).hostname  # a guest's principal, as transport/identity.py names it
        facets = []
        for m in GUEST_MENTION.finditer(row['text']):
            start = len(row['text'][:m.start()].encode())
            facets.append({'$type': 'town.delve.richtext.facet', 'index': {'byteStart': start, 'byteEnd': start + len(m[0].encode())},
                           'features': [{'$type': 'town.delve.richtext.facet#mention', 'did': names.get(m[1]) or f'guest:{host}:{m[1]}'}]})
        record = {'$type': COLLECTION, 'text': row['text'], 'createdAt': row['created'], **({'facets': facets} if facets else {})}
        if row['parent']:
            parent = self.get(row['parent'])
            record['reply'] = {'parent': {'uri': row['parent'], 'cid': parent['cid'] if parent else ''},
                               'root': {'uri': row['root'] or row['parent'], 'cid': (self.get(row['root']) or parent or {'cid': ''})['cid']}}
        return {'uri': row['uri'], 'cid': row['cid'], 'author': {'did': row['did'], 'handle': row['handle']}, 'record': record,
                'indexedAt': row['created']}

    def authors(self):
        with self.lock:
            return self.db.execute('SELECT DISTINCT did, handle FROM feed WHERE town=0').fetchall()

    def rows(self, after=0):
        with self.lock:
            return self.db.execute('SELECT * FROM feed WHERE seq>? ORDER BY seq', (after,)).fetchall()

    def threads(self, before=None, limit=PAGE, thread=None, replies_before=None):
        """SQL keyset pages, newest activity first; each thread has a root, newest replies in sequence order, and an
        earlier-replies cursor. `limit` counts every post. Text costs six bytes per raw UTF-8 byte (HTML entities and
        JSON escapes); metadata costs 32 times its bytes for repeated/quoted links, plus 4096 markup bytes per post.
        PAGE_BYTES leaves six MiB of the HTTP ceiling for the skeleton, composer and request-derived links."""
        def cursor(value):
            if value is None:
                return 9223372036854775807
            if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 19 or not 0 < int(value) <= 9223372036854775807:
                raise Failure('invalid_cursor', 'a feed cursor must be a positive 64-bit sequence')
            return int(value)
        before, replies_before = cursor(before), cursor(replies_before)
        if isinstance(limit, str) and limit.isascii() and limit.isdigit() and len(limit) <= 2:
            limit = int(limit)
        if type(limit) is not int or not 1 <= limit <= PAGE:
            raise Failure('invalid_limit', f'limit must be 1 to {PAGE} total posts')
        def cost(row):
            return 4096 + 6 * len(row['text'].encode()) + 32 * sum(len(v.encode()) for k, v in dict(row).items()
                                                                if k != 'text' and isinstance(v, str))
        out, more, remaining, budget = [], None, limit, PAGE_BYTES
        with self.lock:
            self.db.execute('BEGIN')
            try:
                if thread is None:
                    roots = self.db.execute('SELECT root,last_seq FROM feed_threads WHERE last_seq<? ORDER BY last_seq DESC LIMIT ?',
                                            (before, limit + 1)).fetchall()
                else:
                    roots = self.db.execute('SELECT root,last_seq FROM feed_threads WHERE root=?', (thread,)).fetchall()
                for index, root in enumerate(roots):
                    if remaining == 0:
                        break
                    head = self.db.execute('SELECT * FROM feed WHERE uri=?', (root['root'],)).fetchone()
                    if cost(head) > budget:
                        break
                    remaining, budget = remaining - 1, budget - cost(head)
                    candidates = self.db.execute('SELECT * FROM feed WHERE root=? AND seq<? ORDER BY seq DESC LIMIT ?',
                                                 (root['root'], replies_before, remaining + 1)).fetchall()
                    replies = []
                    for row in candidates:
                        if remaining == 0 or cost(row) > budget:
                            break
                        replies.append(row)
                        remaining, budget = remaining - 1, budget - cost(row)
                    earlier = str(replies[-1]['seq'] if replies else replies_before) if len(candidates) > len(replies) else None
                    out.append((head, list(reversed(replies)), earlier))
                    if thread is None and index + 1 < len(roots):
                        more = str(root['last_seq'])
                    else:
                        more = None
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
        return out, more


def observe_feed(st, feed=None):
    """Every feed post not yet observed, into the observer's store as the observation observe.py makes of a delve.town
    post (the town's own posts are never observed, as the hand's are not). A top-level post is said to the town: it
    summons. -> the posts observed now."""
    feed = feed or Feed(st)
    ob, fresh = Observer(st, None), []
    try:
        for row in feed.rows():
            if row['town'] or ob.seen(row['uri']):
                continue
            post = feed.record(row)
            try:
                obs = observe.observation(post, st.config.summon_handle)
            except Failure:
                continue
            if obs['kind'] == 'post':  # said in the town's own room, to the town
                obs['kind'] = 'summon'
            if ob.insert(obs, post['record']):
                fresh.append(row['uri'])
    finally:
        ob.db.close()
    return fresh


def post_drafts(st, host, feed=None, parts=None):
    """Send local-feed drafts through post.progress; the feed adapter only reserves and sends bytes."""
    feed, parts = feed or Feed(st), parts or post.parts
    sent = []
    for path, _ in st.unposted():
        with st.draft_lock(path):
            d = json.loads(path.read_text())
            if d.get('posted') or d.get('skipped') or d.get('unposted') or d.get('hand') or not is_feed(d.get('replyTo'), st.config.origin, st.world) or not d.get('text'):
                continue
            intent = d.get('intent') or f'feed-{path.stem}'
            def deliver(text, under, key):
                post.reserve(host, key, 'feed')
                row = feed.post(feed.town, text, under, town=True, answers=d['replyTo'], receipt=(d.get('receipt') or {}).get('slug'), intent=key)
                sent.append(row['uri'])
                return {'uri': row['uri'], 'cid': row['cid']}
            post.progress(path, d, st, host, d['text'], parts(d['text']), intent, 'feed', deliver)
    return sent
