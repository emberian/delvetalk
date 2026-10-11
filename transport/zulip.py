"""The Zulip transport: an observer and a poster for one channel of the owner's own Zulip, a world whose bridge row
(`open --transport zulip`) names it.

The observer turns each message of the channel into the observation record observe.py produces for a Delve post
(principal `zulip:<realm>:<sender id>`, the sender's full name as handle, `replyTo` the previous message of the topic,
which is a thread), classified by observe.classify. The poster puts a draft into its topic as a message. Neither
decides anything: routing, quota and admission stay with the bridge and the host.
"""
import configparser
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from transport.delve import Failure, canonical, http_transport
from transport.observe import MAX_TEXT, TAG, Observer, classify
from transport.post import ledger, post_draft, reserve

BATCH = 100
MENTION = re.compile(r'@_?\*\*([^*|\n]+?)(?:\|\d+)?\*\*')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS zulip_topics(topic TEXT PRIMARY KEY, first_uri TEXT, last_id INTEGER, last_uri TEXT);
CREATE TABLE IF NOT EXISTS zulip_cursor(k INTEGER PRIMARY KEY CHECK(k=0), id INTEGER);
'''


def uri_of(stream, topic, mid):
    q = lambda s: urllib.parse.quote(str(s), safe='')
    return f'zulip://{q(stream)}/{q(topic)}/{mid}'


def parse_uri(uri):
    """-> (stream, topic, message id), or None for anything else."""
    parts = uri[8:].split('/') if isinstance(uri, str) and uri.startswith('zulip://') else []
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return urllib.parse.unquote(parts[0]), urllib.parse.unquote(parts[1]), int(parts[2])


class Client:
    """The Zulip REST API as the owner's `.zuliprc` (email, key, site) opens it. The file is read here and never printed."""

    def __init__(self, zuliprc, transport=http_transport):
        cp = configparser.ConfigParser()
        if not cp.read(Path(zuliprc).expanduser()):
            raise Failure('zuliprc_unreadable')
        try:
            api = cp['api']
            self.email, self.key, self.site = api['email'], api['key'], api['site'].rstrip('/')
        except KeyError:
            raise Failure('zuliprc_malformed', 'needs [api] email, key and site') from None
        self.transport = transport
        self.realm = urllib.parse.urlsplit(self.site).hostname or self.site  # the realm a principal names: zulip:<realm>:<user id>

    def call(self, method, path, params=None):
        import base64
        auth = base64.b64encode(f'{self.email}:{self.key}'.encode()).decode()
        headers, url, body = {'Authorization': 'Basic ' + auth}, f'{self.site}/api/v1/{path}', None
        encoded = urllib.parse.urlencode(params or {})
        if method == 'GET' and encoded:
            url += '?' + encoded
        elif method != 'GET':
            body, headers['Content-Type'] = encoded.encode(), 'application/x-www-form-urlencoded'
        status, raw = self.transport(method, url, headers, body)
        try:
            got = json.loads(raw)
        except ValueError:
            raise Failure('zulip_bad_reply', f'http {status}') from None
        if status != 200 or got.get('result') != 'success':
            raise Failure('zulip_refused', f"http {status}: {str(got.get('msg'))[:200]}")
        return got

    def me(self):
        return self.call('GET', 'users/me')

    def messages(self, stream, after=None, topic=None):
        """One page of the stream's messages (of one topic when `topic` is given) after message id `after` (the oldest page when None), oldest first."""
        narrow = [{'operator': 'channel', 'operand': stream}] + ([{'operator': 'topic', 'operand': topic}] if topic else [])
        params = {'anchor': 'oldest' if after is None else after, 'num_before': 0, 'num_after': BATCH,
                  'narrow': json.dumps(narrow), 'apply_markdown': 'false'}
        if after is not None:
            params['include_anchor'] = 'false'
        return self.call('GET', 'messages', params)

    def send(self, stream, topic, content):
        return self.call('POST', 'messages', {'type': 'stream', 'to': stream, 'topic': topic, 'content': content})

    def delete(self, mid):
        """Delete a message this bot sent; anyone else's is refused before the call."""
        got = self.call('GET', f'messages/{int(mid)}', {'apply_markdown': 'false'})
        if (got.get('message') or {}).get('sender_email') != self.email:
            raise Failure('not_ours', f'message {mid}')
        return self.call('DELETE', f'messages/{int(mid)}')

    def newest(self, stream):
        """The id of the stream's newest message (0 for none): the anchor a delivery is persisted with before it is sent."""
        got = self.call('GET', 'messages', {'anchor': 'newest', 'num_before': 1, 'num_after': 0, 'apply_markdown': 'false',
                                            'narrow': json.dumps([{'operator': 'channel', 'operand': stream}])})
        return max([m['id'] for m in got.get('messages') or []] or [0])

    def sent_after(self, stream, topic, content, after):
        """Our own message with this content in the topic after the anchor, or None: a send whose reply was lost."""
        narrow = [{'operator': 'channel', 'operand': stream}, {'operator': 'topic', 'operand': topic}, {'operator': 'sender', 'operand': self.email}]
        got = self.call('GET', 'messages', {'anchor': after, 'include_anchor': 'false', 'num_before': 0, 'num_after': BATCH,
                                            'narrow': json.dumps(narrow), 'apply_markdown': 'false'})
        return next((m['id'] for m in got.get('messages') or [] if m['content'].strip() == content.strip()), None)


def principal(realm, user_id):
    """A Zulip user as a principal: `zulip:<realm host>:<user id>`, so two realms' users never share a name
    (docs/FEDERATION.md section 1)."""
    return f'zulip:{realm}:{user_id}'


def created_at(message):
    """Zulip stamps seconds; the message id fills the microseconds so that order within a second is the stream's order."""
    when = datetime.fromtimestamp(message['timestamp'], tz=timezone.utc)
    return when.strftime('%Y-%m-%dT%H:%M:%S') + f".{message['id'] % 1000000:06d}Z"


class ZulipObserver(Observer):
    """Observer over one stream. Same tables as Observer (posts, observations, emitted); a topic's last message is
    kept for replyTo, and the owner's own messages (drafts we posted) extend the thread but are never observed."""

    def __init__(self, st, client, stream, since=None, topic=None):
        super().__init__(st, client, since)
        self.stream, self.topic, self.me = stream, topic, None
        self.db.executescript(SCHEMA)

    def observation(self, m, bot):
        uri = uri_of(self.stream, m['subject'], m['id'])
        row = self.db.execute('SELECT first_uri,last_uri FROM zulip_topics WHERE topic=?', (m['subject'],)).fetchone()
        parent = row[1] if row else None
        text = m['content']
        names = list(dict.fromkeys(n.strip().lower() for n in MENTION.findall(text)))
        mentions = [{'did': None, 'handle': n} for n in names]
        text = text.strip()
        tags = list(dict.fromkeys(TAG.findall(text)))
        return {'uri': uri, 'cid': str(m['id']), 'author': {'did': principal(self.client.realm, m['sender_id']), 'handle': m['sender_full_name']},
                'createdAt': created_at(m), 'text': text, 'replyTo': parent, 'root': row[0] if row and parent else None,
                'mentions': mentions, 'tags': tags, 'kind': classify(text, parent, mentions, tags, summon=bot)}

    def store(self, m, me):
        """Fold one message into its topic; observe it unless it is ours. True if new."""
        topic, uri = m['subject'], uri_of(self.stream, m['subject'], m['id'])
        self.db.execute('BEGIN IMMEDIATE')
        try:
            seen = self.db.execute('SELECT last_id FROM zulip_topics WHERE topic=?', (topic,)).fetchone()
            if seen and seen[0] >= m['id']:
                self.db.execute('COMMIT')
                return False
            fresh = False
            if m.get('sender_id') != me['user_id'] and not self.before_start(created_at(m)):  # older messages extend the thread, unobserved
                if len(m['content'].encode()) > MAX_TEXT:
                    self.refused.append(('post_body_too_large', uri))
                else:
                    obs = self.observation(m, me['full_name'].strip().lower())
                    self.db.execute('INSERT INTO posts VALUES(?,?,?,?)', (uri, obs['cid'], '', canonical(obs)))
                    self.db.execute('INSERT INTO observations(uri,json) VALUES(?,?)', (uri, canonical(obs)))
                    fresh = True
            self.db.execute('INSERT INTO zulip_topics VALUES(?,?,?,?) ON CONFLICT(topic) DO UPDATE SET last_id=excluded.last_id, last_uri=excluded.last_uri',
                            (topic, uri, m['id'], uri))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise
        return fresh

    def poll(self, *_):
        """Page the stream from the stored cursor to its newest message."""
        try:
            self.page_all()
        except Failure as f:  # a dropped connection costs a poll, not the daemon
            print(canonical({'error': f.code, 'detail': f.detail}), file=sys.stderr)

    def page_all(self):
        me = self.client.me()
        row = self.db.execute('SELECT id FROM zulip_cursor').fetchone()
        after = row[0] if row else None
        while True:
            page = self.client.messages(self.stream, after, self.topic)
            for m in page.get('messages') or []:
                self.store(m, me)
                after = m['id']
            if after is not None:
                self.db.execute('INSERT INTO zulip_cursor VALUES(0,?) ON CONFLICT(k) DO UPDATE SET id=excluded.id', (after,))
            if page.get('found_newest', True) or not page.get('messages'):
                return


def deliver(st, host, client, stream, topic, text, intent):
    """Post `text` to stream>topic once per intent (reserved with the host as a `zulip` post, which no quota holds: the
    hour's quota is delve.town etiquette). The stream's newest id is persisted before the send; a retry adopts our
    message with this text after it rather than sending again. -> {uri, cid}. Raises Failure."""
    path, got = ledger(st, intent)
    if got is None:
        reserve(host, intent, 'zulip')
        got = {'after': client.newest(stream)}
        st.write(path, got)
    if not got.get('result'):
        mid = client.sent_after(stream, topic, text, got['after']) or client.send(stream, topic, text)['id']
        got = dict(got, result={'uri': uri_of(stream, topic, mid), 'cid': str(mid)})
        st.write(path, got)
    return dict(got['result'])


def target(d, row):
    """(stream, topic) of a draft on the world `row` names: a reply goes to its post's topic; a page publication to a topic
    named for the page; a section edit waits until the bridge has given it its page's post to reply to. With a `topic` in
    the row the world lives in that one topic, and nothing is posted elsewhere."""
    where = parse_uri(d.get('replyTo'))
    if where:
        stream, topic = where[:2]
    elif 'publication' in d and not d['section']:
        stream, topic = row['channel'], row.get('topic') or d['page']
    else:
        raise Failure('waits_for_its_page')
    if row.get('topic') and topic != row['topic']:
        raise Failure('outside_topic')
    return stream, topic


def post_drafts(st, host, client):
    """Post every unposted draft with text, oldest first, with no hourly cap, each recorded with the host."""
    sent, held = [], []
    for path, d in st.unposted():
        try:
            sent += [post_draft(path, st, host, zulip=client)['uri']] if d['text'] else []
        except Failure as f:
            held += [] if f.code == 'waits_for_its_page' else [{'file': path.name, 'reason': f.code}]
    return {'posted': sent, **({'held': held} if held else {})}
