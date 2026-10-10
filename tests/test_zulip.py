"""The Zulip playtest transport against a fake Zulip and a real hostd: topics route as threads, the
hourly quota holds, the welcome is recorded.

Evidence for FOUNDATION §7 (layer: transport).

The Zulip transport against a fake Zulip server (users/me, GET and POST messages) on loopback, and a real hostd.

    python3 -W ignore -m tests.run test_zulip
"""
import base64
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.host import serve, start_hostd, stop_hostd
from tests.test_bridge import CARD, OFFERING
from tests.test_http import BINARY
from tests.test_turn_world import nat, record
from transport import bridge, zulip
from transport.hostproc import HostClient
from tests.test_reflection import LIBRARY

OPENER = 'did:plc:' + 'o' * 24
BOT = {'user_id': 99, 'full_name': 'Delve Bot', 'email': 'bot@zulip.test'}
KEY = 'not-a-real-key'


class FakeZulip:
    """The three endpoints the transport uses, over real HTTP with basic auth, holding one list of messages."""

    def __init__(self):
        self.messages, self.calls, self.ids = [], [], {}
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass

            def reply(self, status, obj):
                raw = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def handle_any(self, method):
                want = 'Basic ' + base64.b64encode(f"{BOT['email']}:{KEY}".encode()).decode()
                if self.headers.get('Authorization') != want:
                    return self.reply(401, {'result': 'error', 'msg': 'bad credentials'})
                url = urllib.parse.urlsplit(self.path)
                size = int(self.headers.get('Content-Length') or 0)
                form = urllib.parse.parse_qs(self.rfile.read(size).decode() if size else url.query)
                p = {k: v[0] for k, v in form.items()}
                fake.calls.append((method, url.path))
                if (method, url.path) == ('GET', '/api/v1/users/me'):
                    return self.reply(200, {'result': 'success', **BOT})
                if (method, url.path) == ('GET', '/api/v1/messages'):
                    narrow = json.loads(p['narrow'])
                    inside = [m for m in fake.messages if m['display_recipient'] == narrow[0]['operand']]
                    if p['anchor'] != 'oldest':
                        inside = [m for m in inside if m['id'] > int(p['anchor'])]
                    page = inside[:int(p['num_after'])]
                    return self.reply(200, {'result': 'success', 'messages': page, 'found_newest': len(page) == len(inside)})
                if (method, url.path) == ('POST', '/api/v1/messages'):
                    return self.reply(200, {'result': 'success', 'id': fake.add(p['topic'], BOT['email'], BOT['full_name'], p['content'], p['to'], BOT['user_id'])})
                return self.reply(404, {'result': 'error', 'msg': 'no such endpoint'})

            do_GET = lambda self: self.handle_any('GET')
            do_POST = lambda self: self.handle_any('POST')

        self.server = serve(ThreadingHTTPServer(('127.0.0.1', 0), Handler))

    def add(self, topic, email, name, text, stream='delvetalk', sender_id=None):
        mid = len(self.messages) + 1
        self.messages.append({'id': mid, 'subject': topic, 'content': text, 'sender_email': email, 'sender_full_name': name,
                              'sender_id': sender_id or self.ids.setdefault(email, 1000 + len(self.ids)), 'timestamp': 1_790_000_000, 'display_recipient': stream})
        return mid

    def say(self, topic, who, text, stream='delvetalk'):
        return self.add(topic, f'{who.lower()}@people.test', who, text, stream)

    def mine(self):
        return [m for m in self.messages if m['sender_email'] == BOT['email']]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


SPELL = 'delvetalk garden-1 plant\nseed: a bell\ncolour: amber'


class ZulipCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.state, self.zulip = root / 'state', FakeZulip()
        self.addCleanup(self.zulip.close)
        self.rc = root / 'zuliprc'
        self.rc.write_text(f'[api]\nemail={BOT["email"]}\nkey={KEY}\nsite=http://127.0.0.1:{self.zulip.server.server_port}\n')
        self.hostd = start_hostd(str(root / 'hostd'), BINARY, opener=OPENER, library=LIBRARY)
        self.addCleanup(stop_hostd, self.hostd)
        self.sock = root / 'hostd' / 'host.sock'
        self.host = HostClient(self.sock)
        for name in ('garden-1', 'directory'):
            body = OFFERING.replace('"hello "', f'"{name} says "')
            r = self.host.send({'op': 'world-create', 'principal': OPENER, 'identity': 'mk-' + name, 'object': name,
                                'modules': [{'name': 'Echo', 'source': CARD % ('', body)}], 'entry': 'initial', 'seed': record(seen=nat(5))})
            self.assertEqual(r['status'], 'created', r)

    def bridge(self):
        out = io.StringIO()
        bridge.main(['run', '--once', '--state', str(self.state), '--host-socket', str(self.sock), '--source', 'zulip',
                     '--zuliprc', str(self.rc), '--since', '1970-01-01T00:00:00Z'], out)
        return json.loads(out.getvalue())

    def client(self):
        return zulip.Client(self.rc)

    def observed(self):
        return [json.loads(js) for js in (lambda o: (o.poll(), [r[0] for r in o.db.execute('SELECT json FROM observations ORDER BY seq')])[1])(zulip.ZulipObserver(self.state, self.client()))]


class Observing(ZulipCase):
    def test_a_message_becomes_the_observation_record_delve_posts_have(self):
        a = self.zulip.say('garden', 'Alice', SPELL)
        b = self.zulip.say('garden', 'Bob', 'lovely')
        c = self.zulip.say('hello', 'Carol', f'@**{BOT["full_name"]}** hi')
        d = self.zulip.say('chat', 'Dan', 'just talking')
        self.zulip.add('garden', BOT['email'], BOT['full_name'], 'planted', 'delvetalk', BOT['user_id'])
        first, second, summon, post = self.observed()
        uri = lambda topic, n: f'zulip://delvetalk/{topic}/{n}'
        self.assertEqual((first['author'], first['uri'], first['replyTo'], first['root'], first['kind'], first['spell']),
                         ({'did': 'zulip:1000', 'handle': 'Alice'}, uri('garden', a), None, None, 'spell', {'card': 'garden-1'}))
        self.assertEqual((second['replyTo'], second['root'], second['kind']), (uri('garden', a), uri('garden', a), 'reply'))
        self.assertEqual((summon['kind'], summon['replyTo']), ('summon', None))
        self.assertEqual((post['kind'], post['text']), ('post', 'just talking'))
        self.assertEqual(len(self.observed()), 4, 'polling again adds nothing, and the bot own message is never observed')
        later = self.zulip.say('garden', 'Alice', 'more')
        self.assertEqual(self.observed()[-1]['replyTo'], uri('garden', 5), 'the previous message of a topic includes the bot own')

    def test_a_bad_credential_is_a_failure_not_a_crash(self):
        self.rc.write_text(self.rc.read_text().replace(KEY, 'wrong'))
        ob = zulip.ZulipObserver(self.state, self.client())
        err = io.StringIO()
        import contextlib
        with contextlib.redirect_stderr(err):
            ob.poll()
        self.assertIn('zulip_refused', err.getvalue())
        self.assertNotIn('wrong', err.getvalue())


class Bridging(ZulipCase):
    def test_two_topics_are_two_routed_turns_and_two_posted_drafts(self):
        self.zulip.say('alice garden', 'Alice', SPELL)
        self.zulip.say('bob garden', 'Bob', SPELL)
        got = self.bridge()
        self.assertEqual(len(got['turns']), 2, got)
        self.assertEqual(len(got['posted']), 2, got)
        mine = self.zulip.mine()
        self.assertEqual(sorted(m['subject'] for m in mine), ['alice garden', 'bob garden'])
        self.assertTrue(all(m['content'].endswith('garden-1 says zulip:' + {'alice': '1000', 'bob': '1001'}[m['subject'].split()[0]]) for m in mine), mine)
        self.assertTrue(mine[0]['content'].startswith('@**Alice**\n'))
        arrivals = self.host.send({'op': 'world-objects', 'principal': OPENER})['ids']
        self.assertIn('env/zulip:1000', arrivals)
        self.assertIn('env/zulip:1001', arrivals)
        for uri in got['posted']:  # every posted draft is recorded, so the host knows who it addresses
            self.assertEqual(self.host.send({'op': 'world-addressee', 'parent': uri})['object'], 'garden-1')
        self.assertEqual(self.bridge()['posted'], [], 'nothing is posted twice')

    def test_replies_in_a_topic_route_to_the_object_the_first_message_addressed(self):
        self.zulip.say('t', 'Alice', SPELL)
        self.bridge()
        self.zulip.say('t', 'Alice', 'and some more words')
        self.zulip.say('t', 'Bob', 'me too')  # his parent is Alice's, which was never posted by us
        got = self.bridge()
        self.assertEqual(len(got['turns']), 2, got)
        texts = [m['content'] for m in self.zulip.mine()]
        self.assertEqual(len(texts), 3, texts)
        self.assertTrue(all('garden-1 says' in t for t in texts), texts)

    def test_a_bell_spell_in_a_new_topic_routes_to_the_bell(self):
        body = OFFERING.replace('"hello "', '"bell says "')
        r = self.host.send({'op': 'world-create', 'principal': OPENER, 'identity': 'mk-bell', 'object': 'garden/bell/1',
                            'modules': [{'name': 'Echo', 'source': CARD % ('', body)}], 'entry': 'initial', 'seed': record(seen=nat(5))})
        self.assertEqual(r['status'], 'created', r)
        self.zulip.say('fresh topic', 'Alice', 'delvetalk garden/bell/1 plant\nseed: a\ncolour: amber')
        got = self.bridge()
        self.assertEqual((len(got['turns']), len(got['posted'])), (1, 1), got)
        self.assertIn('bell says', self.zulip.mine()[0]['content'])

    def test_a_mention_of_the_bot_summons_the_directory(self):
        self.zulip.say('new', 'Carol', f'@**{BOT["full_name"]}** what is here?')
        got = self.bridge()
        self.assertEqual(len(got['posted']), 1, got)
        self.assertIn('directory says', self.zulip.mine()[0]['content'])

    def test_the_seventeenth_post_in_an_hour_is_refused_then_goes_when_the_hour_turns(self):
        quota = self.host.send({'op': 'world-status'})['postQuota']
        self.assertEqual(quota, 16)
        for n in range(17):
            self.zulip.say(f'topic {n}', f'P{n:02d}', SPELL)
        got = self.bridge()
        self.assertEqual((len(got['turns']), len(got['posted'])), (17, 16), got)
        self.assertEqual([h['reason'] for h in got['held']], ['rate_limited'])
        later = zulip.post_drafts(self.state, self.host, self.client(), 'delvetalk', now=time.time() + 3601)
        self.assertEqual((len(later['posted']), 'held' in later), (1, False), later)
        self.assertEqual(len(self.zulip.mine()), 17)

    def test_the_welcome_is_posted_and_recorded_so_replies_to_it_reach_the_directory(self):
        welcome = Path(__file__).resolve().parent.parent / 'docs' / 'previews' / 'zulip-welcome-v2.txt'
        out = io.StringIO()
        code = zulip.main(['post', '--state', str(self.state), '--zuliprc', str(self.rc), '--topic', 'welcome',
                           '--text-file', str(welcome), '--object', 'directory', '--host-socket', str(self.sock)], out)
        self.assertEqual(code, 0)
        posted = json.loads(out.getvalue())
        self.assertEqual(self.host.send({'op': 'world-addressee', 'parent': posted['uri']})['object'], 'directory')
        self.assertTrue(self.zulip.mine()[0]['content'].startswith('wiki: DelveTalk Welcome'))
        self.zulip.say('welcome', 'Erin', 'hello? what is this')
        got = self.bridge()
        self.assertEqual(len(got['turns']), 1, got)
        self.assertIn('directory says', self.zulip.mine()[-1]['content'])


if __name__ == '__main__':
    unittest.main()
