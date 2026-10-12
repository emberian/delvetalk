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
import sqlite3
import threading
import time
import urllib.parse
from datetime import datetime, timezone

from transport import observe
from transport.atproto.sign import tid
from transport.delve import POST as COLLECTION, Failure, canonical
from transport.host import CLOCK
from transport.observe import MAX_TEXT, Observer
from transport.repo import world_origin

SCHEMA = '''
CREATE TABLE IF NOT EXISTS feed(seq INTEGER PRIMARY KEY AUTOINCREMENT, uri TEXT UNIQUE NOT NULL, cid TEXT NOT NULL,
  did TEXT NOT NULL, handle TEXT NOT NULL, created TEXT NOT NULL, text TEXT NOT NULL, parent TEXT, root TEXT,
  town INTEGER NOT NULL DEFAULT 0, answers TEXT, receipt TEXT, intent TEXT UNIQUE);
CREATE INDEX IF NOT EXISTS feed_root ON feed(root);
'''
PAGE = 30  # threads a page of the feed shows
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
        self.db.executescript(SCHEMA)
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

    def recent(self, did, since):
        with self.lock:
            return self.db.execute('SELECT COUNT(*) FROM feed WHERE did=? AND town=0 AND created>=?', (did, since)).fetchone()[0]

    def post(self, author, text, reply_to=None, now=None, town=False, answers=None, receipt=None, intent=None):
        """Keep one post -> its row. `reply_to` must be a post of this feed; the root is its parent's root, or the parent.
        With an `intent` (the town's), at most one post: a retry answers the post it made."""
        if intent:
            with self.lock:
                kept = self.db.execute('SELECT * FROM feed WHERE intent=?', (intent,)).fetchone()
            if kept is not None:
                return kept
        if not isinstance(text, str) or not text.strip():
            raise Failure('empty_post', 'say something')
        if len(text.encode()) > MAX_TEXT:
            raise Failure('post_body_too_large', f'at most {MAX_TEXT} bytes')
        parent = self.get(reply_to) if reply_to else None
        if reply_to and parent is None:
            raise Failure('unknown_post', f'{reply_to} is not a post of this feed')
        micros = int((time.time() if now is None else now) * 1e6)
        created = datetime.fromtimestamp(micros / 1e6, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                seq = (self.db.execute('SELECT COALESCE(MAX(seq), 0) FROM feed').fetchone()[0] or 0) + 1
                uri = f"at://{authority(self.origin, self.world)}/{COLLECTION}/{tid(micros, seq & 1023)}"
                cid = 'feed' + hashlib.sha256(canonical({'uri': uri, 'text': text, 'did': author['did']}).encode()).hexdigest()[:32]
                root = (parent['root'] or parent['uri']) if parent else None
                self.db.execute('INSERT INTO feed(uri,cid,did,handle,created,text,parent,root,town,answers,receipt,intent) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                                (uri, cid, author['did'], author['handle'], created, text, parent['uri'] if parent else None, root, int(town), answers, receipt, intent))
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
        return self.get(uri)

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

    def threads(self, before=None, limit=PAGE, thread=None):
        """The newest `limit` threads (a top-level post and every reply under it, in order), newest activity first, from
        before the thread whose root is `before`; or the one `thread`. -> ([(root row, [reply rows])], the next page's
        `before` or None)."""
        with self.lock:
            last = self.db.execute('SELECT COALESCE(root, uri) AS t, MAX(seq) AS s FROM feed GROUP BY t ORDER BY s DESC').fetchall()
        order = [r['t'] for r in last] if thread is None else [thread]
        start = order.index(before) + 1 if before in order else 0
        shown = order[start:start + limit]
        out = []
        for t in shown:
            with self.lock:
                rows = self.db.execute('SELECT * FROM feed WHERE uri=? OR root=? ORDER BY seq', (t, t)).fetchall()
            head = next((r for r in rows if r['uri'] == t), None)
            if head is not None:
                out.append((head, [r for r in rows if r['uri'] != t]))
        return out, (shown[-1] if start + limit < len(order) and shown else None)


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
    """Post every unposted draft that answers a feed post into the feed as the town, at once: each part (`post.parts`)
    under the one before, reserved with the host (`feed`) and recorded (`world-posted`) for the draft's object, so a reply
    under it reaches that card. A preview or a usage is posted and recorded like any reply. -> the uris posted."""
    from transport import post
    feed, parts = feed or Feed(st), parts or post.parts
    sent = []
    for path, d in st.unposted():
        if d.get('hand') or not is_feed(d.get('replyTo'), st.config.origin, st.world) or not d.get('text'):
            continue
        intent, obj, under, results = d.get('intent') or f'feed-{path.stem}', post.draft_object(d), d['replyTo'], []
        slug = (d.get('receipt') or {}).get('slug')
        for k, text in enumerate(parts(d['text']), 1):
            key = f'{intent}#{k}'
            got = host.send({'op': 'world-post-reserve', 'principal': CLOCK, 'intent': key, 'source': 'feed'})
            if got.get('status') != 'reserved':
                break
            row = feed.post(feed.town, text, under, town=True, answers=d['replyTo'], receipt=slug, intent=key)
            result = {'uri': row['uri'], 'cid': row['cid']}
            if obj:  # a retry's record is the host's to answer again (`world-posted` retains it)
                result['recorded'] = post.record_posted(host, result, obj, d.get('slot'), observe.wiki_target(text) if k == 1 else None, key)
            results.append(result)
            under = row['uri']
        if results and len(results) == len(parts(d['text'])):
            st.write(path, dict(d, posted=True, sent=results[-1], sentParts=results, intent=intent,
                                recorded={'status': 'recorded', 'parts': len(results)} if obj else None))
            sent += [r['uri'] for r in results]
    return sent
