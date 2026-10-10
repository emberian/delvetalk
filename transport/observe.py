#!/usr/bin/env python3
"""Read-only watcher: pages #gsb search and the feed, stores each post once, and
emits one canonical observation per new post. It classifies by surface form only.
"""
import argparse
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

try:
    from transport.delve import Client, Failure, FixtureTransport, canonical, http_transport
except ImportError:  # run as a script
    from delve import Client, Failure, FixtureTransport, canonical, http_transport

MAX_TEXT = 64 * 1024
AT_URI = re.compile(r'at://did:[a-z0-9]+:[A-Za-z0-9._:-]+/[A-Za-z0-9.]+/[A-Za-z0-9._~:-]+\Z')
SUMMON_HANDLE, SUMMON_TAG = 'livedelvetalk.delve.town', 'gsb'
EDIT = re.compile(r'edit:\s*(.+?)\s*›\s*(.+)')
DECISION = re.compile(r'(merge|reject)\b[:\s]*(.*)')
MENTION = re.compile(r'(?<![\w.])@((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,})', re.I)
TAG = re.compile(r'(?<![\w#])#([^\W\d_][\w-]*)')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS posts(uri TEXT PRIMARY KEY, cid TEXT, hash TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS observations(seq INTEGER PRIMARY KEY AUTOINCREMENT, uri TEXT UNIQUE,
  json TEXT, emitted INTEGER NOT NULL DEFAULT 0);
'''


WORD = re.compile(r'[\w-]+\Z')


def spell_card(text):
    """The card of the post's spell, following Spell.obend: the second word of the LAST unquoted line that
    begins `delvetalk`. A `>` line and a fence line are never spell lines; a line indented four spaces or a
    tab is quotation, used only when nothing else matches; a line without a well-formed card and action
    is no spell line. Fields (same line after ` / `, or on later lines) are Bend's to parse."""
    unquoted = quoted = None
    for line in text.split('\n'):
        body = line.lstrip(' \t')
        words = body.split()
        if (len(words) < 3 or words[0] != 'delvetalk' or not body.startswith(('delvetalk ', 'delvetalk\t'))
                or not WORD.match(words[1]) or not WORD.match(words[2])):
            continue
        if line.startswith(('    ', '\t')):
            quoted = words[1]
        else:
            unquoted = words[1]
    return unquoted or quoted


def classify(text, reply_to, mentions, tags, summon=SUMMON_HANDLE):
    """-> (kind, wiki, spell). Surface-form only; first match wins. `summon` is the handle whose mention summons."""
    first = text.strip().split('\n', 1)[0].strip()
    if first.startswith('wiki:') and first[5:].strip():
        return 'wiki-page', {'op': 'page', 'title': first[5:].strip(), 'section': None}, None
    m = EDIT.fullmatch(first)
    if m:
        return 'wiki-edit', {'op': 'edit', 'title': m[1], 'section': m[2]}, None
    m = DECISION.fullmatch(first)
    if m and reply_to:
        return 'wiki-merge', {'op': m[1], 'title': m[2].strip() or None, 'section': None}, None
    card = spell_card(text)
    if card:
        return 'spell', None, {'card': card}
    if summon in [x['handle'] for x in mentions] or SUMMON_TAG in [t.lower() for t in tags]:
        return 'summon', None, None
    return ('reply' if reply_to else 'post'), None, None


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


def observation(post):
    """Pure: validated postView -> observation dict. Raises Failure naming the refusal."""
    try:
        uri, cid, author, record = post['uri'], post['cid'], post['author'], post['record']
        text, created = record['text'], record['createdAt']
        did, handle = author['did'], author['handle']
    except (KeyError, TypeError):
        raise Failure('malformed_post') from None
    if not (isinstance(uri, str) and AT_URI.fullmatch(uri) and all(isinstance(x, str) for x in (cid, text, created, did, handle))):
        raise Failure('malformed_post', str(uri)[:100])
    if len(text.encode()) > MAX_TEXT:
        raise Failure('post_body_too_large', uri)
    parent = ((record.get('reply') or {}).get('parent') or {}).get('uri')
    root = ((record.get('reply') or {}).get('root') or {}).get('uri')
    mentions = mentions_of(text, record)
    text = text.strip()
    tags = list(dict.fromkeys(TAG.findall(text)))
    kind, wiki, spell = classify(text, parent, mentions, tags)
    return {'uri': uri, 'cid': cid, 'author': {'did': did, 'handle': handle}, 'createdAt': created,
            'text': text, 'replyTo': parent, 'root': root, 'mentions': mentions, 'tags': tags, 'kind': kind,
            'wiki': wiki, 'spell': spell}


def posts_of(page):
    for item in page.get('feed') or []:
        yield item.get('post') if isinstance(item, dict) else None
    yield from page.get('posts') or []


class Observer:
    def __init__(self, state_dir, client):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.dir / 'observe.sqlite', isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.executescript(SCHEMA)
        self.client, self.refused = client, []

    def store(self, post):
        """Store one post and its observation in one transaction. True if new."""
        try:
            obs = observation(post)
        except Failure as f:
            self.refused.append((f.code, f.detail))
            return False
        body = canonical({'uri': obs['uri'], 'cid': obs['cid'], 'author': obs['author'], 'record': post['record']})
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
        """Page search then feed; stop a source at its first page with nothing new."""
        sources = (lambda c: self.client.search(query, limit, c), lambda c: self.client.feed(limit, c))
        for fetch in sources:
            cursor = None
            for _ in range(pages):
                page = fetch(cursor)
                fresh = sum(self.store(p) for p in posts_of(page))
                cursor = page.get('cursor')
                if not cursor or not fresh:
                    break

    def drain(self, emit):
        """Emit every observation not yet emitted, marking each only after emit returns."""
        rows = self.db.execute('SELECT seq,json FROM observations WHERE emitted=0 ORDER BY seq').fetchall()
        for seq, js in rows:
            emit(js)
            self.db.execute('UPDATE observations SET emitted=1 WHERE seq=?', (seq,))
        return len(rows)


def main(argv=None, transport=None, out=None):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='observe.py', description='read-only delve.town watcher')
    ap.add_argument('--state', required=True)
    ap.add_argument('--mock', metavar='DIR')
    ap.add_argument('--query', default='#gsb')
    ap.add_argument('--pages', type=int, default=3)
    a = ap.parse_args(argv)
    t = transport or (FixtureTransport(a.mock) if a.mock else http_transport)
    ob = Observer(a.state, Client(t))
    try:
        ob.poll(a.query, a.pages)
    except Failure as f:
        print(canonical({'error': f.code, 'detail': f.detail}), file=sys.stderr)
    for code, detail in ob.refused:
        print(canonical({'refused': code, 'detail': detail}), file=sys.stderr)
    ob.drain(lambda js: (out.write(js + '\n'), out.flush()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
