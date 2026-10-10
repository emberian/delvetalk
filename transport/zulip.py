#!/usr/bin/env python3
"""The Zulip transport: an observer and a poster for one stream of the owner's own Zulip.

The observer turns each message of the stream into the observation record observe.py produces for a Delve post
(principal `zulip:<sender id>`, the sender's full name as handle, `replyTo` the previous message of the topic,
which is a thread), classified by observe.classify. The poster puts a draft into its topic as a message. Neither
decides anything: routing, quota and admission stay with the bridge and the host.

    python3 -m transport.zulip observe --state DIR --zuliprc PATH [--stream delvetalk]
    python3 -m transport.zulip post --state DIR --zuliprc PATH --topic T --text-file F --object O --host-socket S
"""
import argparse
import configparser
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from transport.bridge import unposted, write_atomic
from transport.delve import Failure, canonical, http_transport
from transport.observe import MAX_TEXT, TAG, Observer, classify
from transport.post import quota_limit, record_posted, slot_record, take_slot, wiki_target

STREAM = 'delvetalk'
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

    def messages(self, stream, after=None):
        """One page of the stream's messages after message id `after` (the oldest page when None), oldest first."""
        params = {'anchor': 'oldest' if after is None else after, 'num_before': 0, 'num_after': BATCH,
                  'narrow': json.dumps([{'operator': 'channel', 'operand': stream}]), 'apply_markdown': 'false'}
        if after is not None:
            params['include_anchor'] = 'false'
        return self.call('GET', 'messages', params)

    def send(self, stream, topic, content):
        return self.call('POST', 'messages', {'type': 'stream', 'to': stream, 'topic': topic, 'content': content})


def created_at(message):
    """Zulip stamps seconds; the message id fills the microseconds so that order within a second is the stream's order."""
    when = datetime.fromtimestamp(message['timestamp'], tz=timezone.utc)
    return when.strftime('%Y-%m-%dT%H:%M:%S') + f".{message['id'] % 1000000:06d}Z"


class ZulipObserver(Observer):
    """Observer over one stream. Same tables as Observer (posts, observations, emitted); a topic's last message is
    kept for replyTo, and the owner's own messages (drafts we posted) extend the thread but are never observed."""

    def __init__(self, state_dir, client, stream=STREAM, since=None):
        super().__init__(state_dir, client, since)
        self.stream, self.me = stream, None
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
        kind, wiki, spell = classify(text, parent, mentions, tags, summon=bot)
        return {'uri': uri, 'cid': str(m['id']), 'author': {'did': 'zulip:' + str(m['sender_id']), 'handle': m['sender_full_name']},
                'createdAt': created_at(m), 'text': text, 'replyTo': parent, 'root': row[0] if row and parent else None,
                'mentions': mentions, 'tags': tags, 'kind': kind, 'wiki': wiki, 'spell': spell}

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
            page = self.client.messages(self.stream, after)
            for m in page.get('messages') or []:
                self.store(m, me)
                after = m['id']
            if after is not None:
                self.db.execute('INSERT INTO zulip_cursor VALUES(0,?) ON CONFLICT(k) DO UPDATE SET id=excluded.id', (after,))
            if page.get('found_newest', True) or not page.get('messages'):
                return


def deliver(state, host, client, stream, topic, text, obj=None, slot=None, now=None):
    """Post `text` to stream>topic within the host's hourly budget, then tell the host the post exists for `obj`
    (world-posted), so replies in the topic route to it. -> {uri, cid, recorded}. Raises Failure('rate_limited')."""
    limit, _ = quota_limit(host)
    take_slot(Path(state), time.time() if now is None else now, limit)
    sent = client.send(stream, topic, text)
    result = {'uri': uri_of(stream, topic, sent['id']), 'cid': str(sent['id'])}
    return {**result, 'recorded': record_posted(host, result, obj, slot, wiki_target(text)) if obj else None}


def post_drafts(state, host, client, stream, now=None):
    """Post every unposted draft with text, oldest first, until the hourly quota refuses; record each with the host.
    A reply draft goes to its post's topic, addressed to its author; a page publication to a topic named for the page
    (a section edit waits until its page is recorded and the bridge has given it the page post to reply to)."""
    sent, held = [], []
    for path in sorted((Path(state) / 'outbox').glob('*.json')):  # posted, but the host has not yet been told
        d = json.loads(path.read_text())
        obj = d.get('object') or (d.get('publication') or {}).get('object')
        if d['posted'] and obj and ((d.get('sent') or {}).get('recorded') or {}).get('status') == 'error':
            again = record_posted(host, d['sent'], obj, slot_record(d['slot']) if d.get('slot') else None, wiki_target(d['text']))
            write_atomic(path, dict(d, sent=dict(d['sent'], recorded=again)))
    for path, d in unposted(state):
        if not d['text']:
            continue
        if d.get('replyTo'):
            where = parse_uri(d['replyTo'])
            target = (where[0], where[1]) if where else None
            text = f"@**{d['replyHandle']}**\n{d['text']}" if 'publication' not in d else d['text']
        else:
            target, text = ((stream, d['page']) if 'publication' in d and not d['section'] else None), d.get('text')
        if target is None:
            continue
        obj = d.get('object') or (d.get('publication') or {}).get('object')
        try:
            got = deliver(state, host, client, target[0], target[1], text, obj, slot_record(d['slot']) if d.get('slot') else None, now)
        except Failure as f:
            held.append({'file': path.name, 'reason': f.code})
            if f.code == 'rate_limited':
                break
            continue
        write_atomic(path, dict(d, posted=True, sent=got))
        sent.append(got['uri'])
    return {'posted': sent, **({'held': held} if held else {})}


def main(argv=None, out=None, transport=http_transport):
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog='zulip.py')
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('observe', 'post'):
        p = sub.add_parser(name)
        p.add_argument('--state', required=True)
        p.add_argument('--zuliprc', required=True, metavar='PATH')
        p.add_argument('--stream', default=STREAM)
    p.add_argument('--topic', required=True)
    p.add_argument('--text-file', required=True)
    p.add_argument('--object', help='the object the post addresses: world-posted is called for it')
    p.add_argument('--slot', metavar='PRINCIPAL:INTENT')
    p.add_argument('--host-socket', metavar='PATH')
    a = ap.parse_args(argv)
    try:
        client = Client(a.zuliprc, transport)
        if a.cmd == 'observe':
            ob = ZulipObserver(a.state, client, a.stream)
            ob.poll()
            ob.drain(lambda js: (out.write(js + '\n'), out.flush()))
            return 0
        from transport.hostproc import HostClient
        host = HostClient(a.host_socket) if a.host_socket else None
        if a.object and not host:
            raise Failure('record_needs_journal')
        text = Path(a.text_file).read_text().replace('<bot name>', client.me()['full_name'])  # a card may name the bot it is posted by
        result = deliver(a.state, host, client, a.stream, a.topic, text, a.object,
                         slot_record(a.slot) if a.slot else None)
    except (Failure, OSError) as e:
        print(canonical({'error': getattr(e, 'code', type(e).__name__), 'detail': getattr(e, 'detail', '')}), file=sys.stderr)
        return 1
    out.write(canonical(result) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
