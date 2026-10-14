"""Read-only watcher: pages #gsb search and the feed and stores each post once with its canonical observation, which
the bridge reads. It classifies by surface form only.

What `observe.sqlite` keeps. A new observation is held whole until the bridge has answered it, then:
  - a post the host's `world-reach` skipped is dropped SKIP_MINUTES after it was written: its URI as an 8-byte hash
    (`gone`, so the next page of the feed never shows it again) and, if it is a reply, its (uri, author, replyTo) as a
    `chain` stub for CHAIN_DAYS, which is all `reach` needs of an ancestor (past that the host falls back to the root);
  - a post that reached a card, was turned or was answered is kept whole RETAIN_DAYS after it was written (the hand
    reads it, `reach` of its replies and the mention retry read it), then dropped to its hash;
  - a post still awaiting an interpretation or a draft is kept whole until it is answered.
A mention of an arrived resident is queued apart (`mentions`: the note itself, the post's URI, its author and their
handle, its first characters) from the run that first reads the post until the town tells it (bridge.tell_mentions), so
the post may be dropped first. Every author seen stays in `authors` (a mention resolves an @handle through it long after the author's posts are
gone). Nothing else of a post is kept: not the record (`posts.body` only repeated the observation). Ages are measured on
the town's own timeline (`timeline`).
"""
import hashlib
import re
import sqlite3
import time
from datetime import datetime, timezone

from transport import delve
from transport.delve import Failure, canonical

MAX_TEXT = 64 * 1024
RETAIN_DAYS = 7  # an answered observation is kept whole this long after it was written
SKIP_MINUTES = 15  # a skipped one this long: the hand lists, retries and replies to it by hand while it is fresh; then its hash
CHAIN_DAYS = 3  # a dropped reply's chain stub is kept this long: `reach` walks 32 hops, and past the stub the host falls back to the root
VERSION = 1  # observe.sqlite's user_version once migrated
SUMMON_TAG = 'gsb'
EDIT = re.compile(r'edit:\s*(.+?)\s*›\s*(.+)')
DECISION = re.compile(r'(?:merge|reject)\b.*')
MENTION = re.compile(r'(?<![\w.])@((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,})', re.I)
TAG = re.compile(r'(?<![\w#])#([^\W\d_][\w-]*)')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS posts(uri TEXT PRIMARY KEY, cid TEXT, hash TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS observations(seq INTEGER PRIMARY KEY AUTOINCREMENT, uri TEXT UNIQUE, json TEXT);
CREATE TABLE IF NOT EXISTS gone(h BLOB PRIMARY KEY) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS chain(uri TEXT PRIMARY KEY, author TEXT, reply_to TEXT, created REAL) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS authors(did TEXT PRIMARY KEY, handle TEXT, seen INTEGER) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS mentions(seq INTEGER PRIMARY KEY AUTOINCREMENT, uri TEXT, did TEXT, author TEXT, handle TEXT, text TEXT,
  queued REAL, UNIQUE(uri, did));
CREATE TRIGGER IF NOT EXISTS observed_author AFTER INSERT ON observations
WHEN json_extract(new.json,'$.author.did') IS NOT NULL BEGIN
  INSERT INTO authors(did,handle,seen) VALUES(json_extract(new.json,'$.author.did'), json_extract(new.json,'$.author.handle'), new.seq)
  ON CONFLICT(did) DO UPDATE SET handle=excluded.handle;
END;
'''


def wiki_target(text):
    """(page, section) of an agentwiki post, read off its first line: `wiki: <page>` is the whole page (section ""),
    `edit: <page> › <section>` one section; None for any other text. The one reading of the header: the observer
    classifies by it and the poster records a post's page by it."""
    first = text.strip().split('\n', 1)[0].strip()
    m = EDIT.fullmatch(first)
    if m:
        return m[1], m[2].strip()
    return (first[5:].strip(), '') if first.startswith('wiki:') and first[5:].strip() else None


def classify(text, reply_to, mentions, tags, summon):
    """-> kind. Surface form only, first match wins; `summon` is the handle whose mention summons (config
    `summon_handle`). Whether a post is a spell, and to which card, is the host's parser's answer (bridge.parsed),
    not this one's."""
    target = wiki_target(text)
    if target:
        return 'wiki-edit' if target[1] else 'wiki-page'
    if reply_to and DECISION.fullmatch(text.strip().split('\n', 1)[0].strip()):
        return 'wiki-merge'
    if summon in [x['handle'] for x in mentions] or SUMMON_TAG in [t.lower() for t in tags]:
        return 'summon'
    return 'reply' if reply_to else 'post'


def mentions_of(text, record):
    raw, found, seen = text.encode(), [], set()
    for facet in record.get('facets') or []:
        try:
            idx = facet['index']
            for ft in facet.get('features') or []:
                if str(ft.get('$type', '')).endswith('#mention'):
                    h = raw[idx['byteStart']:idx['byteEnd']].decode().lstrip('@').lower()
                    found.append({'did': ft['did'], 'handle': h})
                    seen.add(h)
        except (KeyError, TypeError, UnicodeDecodeError, AttributeError):
            continue
    for m in MENTION.finditer(text):
        h = m[1].lower()
        if h not in seen:
            seen.add(h)
            found.append({'did': None, 'handle': h})
    return found


LEADING_BLANK = re.compile(r'\A(?:[ \t]*\n)+')


def observation(post, summon=''):
    """Pure: validated postView -> observation dict, a mention of `summon` summoning. Raises Failure naming the refusal."""
    try:
        uri, cid, author, record = post['uri'], post['cid'], post['author'], post['record']
        text, created = record['text'], record['createdAt']
        did, handle = author['did'], author['handle']
    except (KeyError, TypeError):
        raise Failure('malformed_post') from None
    try:
        parsed = delve.parse_at_uri(uri)
        instant(created)
    except (Failure, ValueError):
        raise Failure('malformed_post', str(uri)[:100]) from None
    if not (parsed.repo.startswith('did:') and all(isinstance(x, str) for x in (cid, text, did, handle))):
        raise Failure('malformed_post', str(uri)[:100])
    if len(text.encode()) > MAX_TEXT:
        raise Failure('post_body_too_large', uri)
    parent = ((record.get('reply') or {}).get('parent') or {}).get('uri')
    root = ((record.get('reply') or {}).get('root') or {}).get('uri')
    mentions = mentions_of(text, record)
    text = LEADING_BLANK.sub('', text).rstrip()  # an indented first line keeps its indent: an indented spell is quoted, not cast
    tags = list(dict.fromkeys(TAG.findall(text)))
    return {'uri': uri, 'cid': cid, 'author': {'did': did, 'handle': handle}, 'createdAt': created, 'text': text,
            'replyTo': parent, 'root': root, 'mentions': mentions, 'tags': tags, 'kind': classify(text, parent, mentions, tags, summon)}


def posts_of(page):
    for item in page.get('feed') or []:
        yield item.get('post') if isinstance(item, dict) else None
    yield from page.get('posts') or []


def instant(stamp):
    """An ISO-8601 time as UNIX seconds."""
    if not isinstance(stamp, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', stamp):
        raise ValueError('not a timestamp')
    try:
        return datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
    except (OverflowError, OSError) as error:
        raise ValueError('not a timestamp') from error


def start_cursor(st, explicit=None, now=None):
    """The world's `since`: where its observing begins. An explicit time (a deliberate replay) is written and wins; else
    the file the world already holds; else, for a world that has observed nothing yet, now. A world that already has
    observations and no `since` predates the cursor and observes everything it is shown. -> ISO time or None."""
    path = st.since
    if explicit:
        instant(explicit)  # refuses what is not a time
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(explicit + '\n')
    elif not path.exists() and not st.observed.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') + '\n')
    return path.read_text().strip() if path.exists() else None


def uri_key(uri):
    return hashlib.sha256(uri.encode()).digest()[:8]


def connect(st):
    """The store, created and migrated: schema, then (once, idempotently) what an older store lacks. The old store held
    each post twice (`observations.json` and `posts.body`) and no author table: the authors are rebuilt from the
    observations (the first-seen order of the dids, the latest handle of each), the bodies emptied and the file compacted. The version is set
    only after the compaction, so a compaction the lock refused is tried again at the next open."""
    st.home.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(st.observed, isolation_level=None, timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=NORMAL')
    db.executescript(SCHEMA)
    if db.execute('PRAGMA user_version').fetchone()[0] < VERSION:
        db.execute('BEGIN IMMEDIATE')
        for did, handle, seq in db.execute("SELECT json_extract(json,'$.author.did'), json_extract(json,'$.author.handle'), seq "
                                           "FROM observations ORDER BY seq").fetchall():
            if did is not None:
                db.execute('INSERT INTO authors VALUES(?,?,?) ON CONFLICT(did) DO UPDATE SET handle=excluded.handle', (did, handle, seq))
        db.execute("UPDATE posts SET body='' WHERE body!=''")
        db.execute('COMMIT')
        try:
            db.execute('VACUUM')
            db.execute(f'PRAGMA user_version={VERSION}')
        except sqlite3.OperationalError:  # another process holds the file: the next open compacts
            pass
    return db


def read(st, sql, *args):
    """Rows of a read of the store; none when it does not exist or predates the table (the bridge also runs on stores
    other code wrote)."""
    if not st.observed.exists():
        return []
    db = sqlite3.connect(st.observed)
    try:
        return db.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        db.close()


def authors(st):
    """[(did, handle)] of every author ever observed, with the handle of their latest observation, in the order they were first observed."""
    return read(st, 'SELECT did, handle FROM authors ORDER BY seen')


def stubs(st):
    """{uri: observation-shaped stub} of the replies pruned within CHAIN_DAYS: the ancestor `reach` asks of an observation."""
    return {u: {'uri': u, 'author': {'did': a}, 'replyTo': r} for u, a, r in read(st, 'SELECT uri, author, reply_to FROM chain')}


def queue(st, uri, author, handle, text, dids, at):
    """Queue the post's note for each of `dids` (arrived residents it mentions), once a (post, resident), at `at`."""
    db = connect(st)
    try:
        db.execute('BEGIN IMMEDIATE')
        for did in dids:
            db.execute('INSERT OR IGNORE INTO mentions(uri, did, author, handle, text, queued) VALUES(?,?,?,?,?,?)',
                       (uri, did, author, handle, text, at))
        db.execute('COMMIT')
    finally:
        db.close()


def due(st, before):
    """{did: [{seq, uri, author, handle, text}] in the order queued} of each resident whose oldest queued note was queued
    at or before `before`."""
    rows = read(st, 'SELECT seq, uri, did, author, handle, text FROM mentions WHERE did IN '
                    '(SELECT did FROM mentions GROUP BY did HAVING MIN(queued) <= ?) ORDER BY seq', before)
    out = {}
    for seq, uri, did, author, handle, text in rows:
        out.setdefault(did, []).append({'seq': seq, 'uri': uri, 'author': author, 'handle': handle, 'text': text})
    return out


def told(st, seqs):
    """The notes `seqs` were told: -> the URIs none of whose notes wait any longer."""
    db = connect(st)
    try:
        db.execute('BEGIN IMMEDIATE')
        marks = ','.join('?' * len(seqs))
        uris = [u for (u,) in db.execute(f'SELECT DISTINCT uri FROM mentions WHERE seq IN ({marks})', seqs)]
        db.execute(f'DELETE FROM mentions WHERE seq IN ({marks})', seqs)
        done = [u for u in uris if not db.execute('SELECT 1 FROM mentions WHERE uri=?', (u,)).fetchone()]
        db.execute('COMMIT')
        return done
    finally:
        db.close()


def timeline(rows, now=None):
    """The instant ages are measured at: the newest post observed, never later than the clock (`now`, else the wall
    clock; a post dated in the future must not age everything out). A quiet town ages slowly, and a replayed one by its own
    time."""
    stamps = []
    for o in rows:
        try:
            stamps.append(instant(o['createdAt']))
        except (KeyError, ValueError):
            pass
    return min(max(stamps, default=0), time.time() if now is None else now)


def prune(st, skipped, answered, at, keep=()):
    """Drop what the bridge has answered, per the module docstring, as of `at` (`timeline`): `skipped` observations once
    written SKIP_MINUTES before it (an unparseable time is old), `answered` ones once written RETAIN_DAYS before it (an
    unparseable time is never old: only a request record can lack one). Each leaves its URI hash in `gone`; a skipped
    reply leaves its chain stub too; a URI in `keep` (the feed's, which `feed.waiting` asks the `posts` table about)
    keeps its emptied `posts` row. Stubs older than CHAIN_DAYS go. The file is compacted when a fifth of it is free.
    -> the count dropped."""
    if not st.observed.exists():
        return 0

    def written(o):
        try:
            return instant(o['createdAt'])
        except (KeyError, ValueError):
            return None

    older = lambda o, seconds, unknown: (unknown if written(o) is None else written(o) < at - seconds)
    drop = [(o, True) for o in skipped if older(o, SKIP_MINUTES * 60, True)] + \
           [(o, False) for o in answered if older(o, RETAIN_DAYS * 86400, False)]
    db = connect(st)
    try:
        db.execute('BEGIN IMMEDIATE')
        for o, skip in drop:
            uri = o['uri']
            db.execute('DELETE FROM observations WHERE uri=?', (uri,))
            db.execute('INSERT OR IGNORE INTO gone VALUES(?)', (uri_key(uri),))
            if uri in keep:
                db.execute("UPDATE posts SET cid='', hash='', body='' WHERE uri=?", (uri,))
            else:
                db.execute('DELETE FROM posts WHERE uri=?', (uri,))
            if skip and o.get('replyTo') and written(o) is not None and written(o) >= at - CHAIN_DAYS * 86400:
                db.execute('INSERT OR REPLACE INTO chain VALUES(?,?,?,?)', (uri, o['author']['did'], o['replyTo'], written(o)))
        db.execute('DELETE FROM chain WHERE created < ?', (at - CHAIN_DAYS * 86400,))
        db.execute('COMMIT')
        free, pages = db.execute('PRAGMA freelist_count').fetchone()[0], db.execute('PRAGMA page_count').fetchone()[0]
        if free * 5 >= pages and free * db.execute('PRAGMA page_size').fetchone()[0] >= 1 << 20:
            db.execute('VACUUM')
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    except sqlite3.OperationalError:  # locked by a reader or the hand: the same drops are made next run
        if db.in_transaction:
            db.execute('ROLLBACK')
        return 0
    finally:
        db.close()
    return len(drop)


class Observer:
    def __init__(self, st, client, since=None, requests=None):
        self.since = instant(since) if since else None  # posts created before it are not observed
        self.db = connect(st)
        self.client, self.summon = client, st.config.summon_handle
        self.requests, self.problems = requests, []  # a requests.Poller: residents' request records, proven

    def before_start(self, created):
        at = instant(created)
        return self.since is not None and at < self.since

    def store(self, post):
        """Store one post and its observation in one transaction. True if new."""
        try:
            obs = observation(post, self.summon)
        except Failure:  # malformed, or past MAX_TEXT: not an observation
            return False
        if self.before_start(obs['createdAt']):
            return False
        return self.insert(obs, post['record'])

    def seen(self, uri):
        """Whether `uri` was observed, here or before the bridge dropped it."""
        return bool(self.db.execute('SELECT 1 FROM posts WHERE uri=? UNION ALL SELECT 1 FROM gone WHERE h=?', (uri, uri_key(uri))).fetchone())

    def insert(self, obs, record):
        """Keep `obs` once per uri (the record it was read from is not kept: it only repeated `obs`). True if new."""
        body = canonical({'uri': obs['uri'], 'cid': obs['cid'], 'author': obs['author'], 'record': record})
        digest = hashlib.sha256(body.encode()).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.seen(obs['uri']):
                self.db.execute('COMMIT')
                return False
            self.db.execute("INSERT INTO posts VALUES(?,?,?,'')", (obs['uri'], obs['cid'], digest))
            self.db.execute('INSERT INTO observations(uri,json) VALUES(?,?)', (obs['uri'], canonical(obs)))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise
        return True

    def again(self, since, pages=64, limit=50):
        """The observations of the town's feed created at or after `since` (ISO), paged back until a page reaches past it
        or `pages` are read; nothing stored. For a deliberate replay of what the bridge already answered (`bridge
        --hear-again`): a dropped post is only its hash here."""
        at, cursor, out = instant(since), None, []
        for _ in range(pages):
            page = self.client.feed(limit, cursor)
            got = []
            for post in posts_of(page):
                try:
                    got.append(observation(post, self.summon))
                except Failure:
                    continue
            out += [o for o in got if instant(o['createdAt']) >= at]
            cursor = page.get('cursor')
            if not cursor or not got or min(instant(o['createdAt']) for o in got) < at:
                break
        return out

    def poll(self, query='#gsb', pages=3, limit=50):
        """Page search then feed, stopping a source at its first page with nothing new; then the request records
        (transport/requests.py)."""
        sources = (lambda c: self.client.search(query, limit, c), lambda c: self.client.feed(limit, c))
        for fetch in sources:
            cursor = None
            for _ in range(pages):
                page = fetch(cursor)
                fresh = sum(self.store(p) for p in posts_of(page))
                cursor = page.get('cursor')
                if not cursor or not fresh:
                    break
        if self.requests:
            self.problems = self.requests.poll(self)

