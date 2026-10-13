"""Read-only watcher: pages #gsb search and the feed and stores each post once with its canonical observation, which
the bridge reads. It classifies by surface form only.
"""
import hashlib
import re
import sqlite3
import time
from datetime import datetime, timezone

from transport import delve
from transport.delve import Failure, canonical

MAX_TEXT = 64 * 1024
SUMMON_TAG = 'gsb'
EDIT = re.compile(r'edit:\s*(.+?)\s*›\s*(.+)')
DECISION = re.compile(r'(?:merge|reject)\b.*')
MENTION = re.compile(r'(?<![\w.])@((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,})', re.I)
TAG = re.compile(r'(?<![\w#])#([^\W\d_][\w-]*)')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS posts(uri TEXT PRIMARY KEY, cid TEXT, hash TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS observations(seq INTEGER PRIMARY KEY AUTOINCREMENT, uri TEXT UNIQUE, json TEXT);
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


class Observer:
    def __init__(self, st, client, since=None, requests=None):
        st.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.since = instant(since) if since else None  # posts created before it are not observed
        self.db = sqlite3.connect(st.observed, isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.executescript(SCHEMA)
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
        return bool(self.db.execute('SELECT 1 FROM posts WHERE uri=?', (uri,)).fetchone())

    def insert(self, obs, record):
        """Keep `obs` and the record it was read from, once per uri. True if new."""
        body = canonical({'uri': obs['uri'], 'cid': obs['cid'], 'author': obs['author'], 'record': record})
        digest = hashlib.sha256(body.encode()).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute('SELECT 1 FROM posts WHERE uri=?', (obs['uri'],)).fetchone():
                self.db.execute('COMMIT')
                return False
            self.db.execute('INSERT INTO posts VALUES(?,?,?,?)', (obs['uri'], obs['cid'], digest, body))
            self.db.execute('INSERT INTO observations(uri,json) VALUES(?,?)', (obs['uri'], canonical(obs)))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise
        return True

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

