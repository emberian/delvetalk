"""The Zulip playtest transport against a fake Zulip and a real `serve`: topics route as threads, the
hourly quota holds, the welcome is recorded.

Evidence for FOUNDATION §7 (layer: transport).

The Zulip transport against a fake Zulip server (users/me, GET and POST messages) on loopback, and a real `serve`.

    python3 -W ignore -m tests.run test_zulip
"""
import base64
import io
import json
import tempfile
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.host import serve, served
from tests.test_bridge import CARD, OFFERING
from transport import zulip
from transport.__main__ import main
from transport.host import HostClient
from transport.state import State
from transport.config import LIBRARY
from tests.wire import nat, record

OPENER = 'did:plc:' + 'o' * 24
BOT = {'user_id': 99, 'full_name': 'Delve Bot', 'email': 'bot@zulip.test'}
KEY = 'not-a-real-key'


class FakeZulip:
    """The three endpoints the transport uses, over real HTTP with basic auth, holding one list of messages."""

    def __init__(self):
        self.messages, self.calls, self.ids, self.lose, self.narrows = [], [], {}, 0, []
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
                if url.path.startswith('/api/v1/messages/') and method in ('GET', 'DELETE'):
                    mid = int(url.path.rsplit('/', 1)[1])
                    found = next((m for m in fake.messages if m['id'] == mid), None)
                    if found is None:
                        return self.reply(400, {'result': 'error', 'msg': 'no such message'})
                    if method == 'DELETE':
                        fake.messages.remove(found)
                    return self.reply(200, {'result': 'success', 'message': found})
                if (method, url.path) == ('GET', '/api/v1/messages'):
                    key = {'channel': 'display_recipient', 'topic': 'subject', 'sender': 'sender_email'}
                    narrow = json.loads(p['narrow'])
                    fake.narrows.append({n['operator']: n['operand'] for n in narrow})
                    inside = [m for m in fake.messages if all(m[key[n['operator']]] == n['operand'] for n in narrow)]
                    if p['anchor'] == 'newest':
                        page = inside[-int(p['num_before']):] if int(p['num_before']) else []
                        return self.reply(200, {'result': 'success', 'messages': page, 'found_newest': True})
                    if p['anchor'] != 'oldest':
                        inside = [m for m in inside if m['id'] > int(p['anchor'])]
                    page = inside[:int(p['num_after'])]
                    return self.reply(200, {'result': 'success', 'messages': page, 'found_newest': len(page) == len(inside)})
                if (method, url.path) == ('POST', '/api/v1/messages'):
                    mid = fake.add(p['topic'], BOT['email'], BOT['full_name'], p['content'], p['to'], BOT['user_id'])
                    if fake.lose:  # the message lands; its reply does not
                        fake.lose -= 1
                        return self.reply(502, {'result': 'error', 'msg': 'bad gateway'})
                    return self.reply(200, {'result': 'success', 'id': mid})
                return self.reply(404, {'result': 'error', 'msg': 'no such endpoint'})

            do_GET = lambda self: self.handle_any('GET')
            do_POST = lambda self: self.handle_any('POST')
            do_DELETE = lambda self: self.handle_any('DELETE')

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
        self.zulip = FakeZulip()
        self.addCleanup(self.zulip.close)
        self.rc = root / 'zuliprc'
        self.rc.write_text(f'[api]\nemail={BOT["email"]}\nkey={KEY}\nsite=http://127.0.0.1:{self.zulip.server.server_port}\n')
        self.server = served(str(root / 'serve'), cleanup=self.addCleanup, opener=OPENER, library=LIBRARY)
        self.sock = self.server.sock
        (root / 'state').mkdir()
        (root / 'state' / 'delvetalk.toml').write_text(f'host_socket = "{self.sock}"\n')
        self.state = State(root / 'state')
        self.host, self.root = HostClient(self.sock), HostClient(self.server.root)
        for name in ('garden-1', 'commonplace'):
            body = OFFERING.replace('"hello "', f'"{name} says "')
            r = self.root.send({'op': 'world-create', 'principal': OPENER, 'identity': 'mk-' + name, 'object': name,
                                'modules': [{'name': 'Echo', 'source': CARD % ('', body)}], 'entry': 'initial', 'seed': record(seen=nat(5))})
            self.assertEqual(r['status'], 'created', r)

    def bridge(self, *topic):
        """One bridge step on the world opened on the channel (or one topic of it) by its bridge row."""
        out = io.StringIO()
        if not self.state.row.exists():
            main(['open', '--state', str(self.state.root), '--transport', 'zulip', '--realm', '127.0.0.1', '--channel', 'delvetalk',
                  '--zuliprc', str(self.rc), *(('--topic', *topic) if topic else ())], io.StringIO())
        main(['bridge', '--once', '--state', str(self.state.root), '--since', '1970-01-01T00:00:00Z'], out)
        return json.loads(out.getvalue())

    def client(self):
        return zulip.Client(self.rc)

    def observed(self):
        return [json.loads(js) for js in (lambda o: (o.poll(), [r[0] for r in o.db.execute('SELECT json FROM observations ORDER BY seq')])[1])(zulip.ZulipObserver(self.state, self.client(), 'delvetalk'))]


class Observing(ZulipCase):
    def test_a_principal_carries_its_realm_so_two_realms_never_collide(self):
        self.zulip.say('t', 'Alice', 'hello')
        here = self.observed()[0]['author']['did']
        other = Path(self.tmp.name) / 'other-rc'
        other.write_text(self.rc.read_text().replace('http://127.0.0.1', 'http://localhost'))
        there = zulip.ZulipObserver(State(Path(self.tmp.name) / 'other-state'), zulip.Client(other), 'delvetalk', since='1970-01-01T00:00:00Z')
        there.poll()
        them = json.loads(there.db.execute('SELECT json FROM observations').fetchone()[0])['author']['did']
        self.assertEqual((here, them), ('zulip:127.0.0.1:1000', 'zulip:localhost:1000'))  # the same user id, two realms

    def test_the_bot_deletes_its_own_message_and_never_a_residents(self):
        theirs = self.zulip.say('t', 'Alice', 'mine')
        ours = self.zulip.add('t', BOT['email'], BOT['full_name'], 'the bot said this')
        client = self.client()
        with self.assertRaises(zulip.Failure):
            client.delete(theirs)
        client.delete(ours)
        self.assertEqual([m['id'] for m in self.zulip.messages], [theirs])

    def test_a_bad_credential_is_a_failure_not_a_crash(self):
        self.rc.write_text(self.rc.read_text().replace(KEY, 'wrong'))
        ob = zulip.ZulipObserver(self.state, self.client(), 'delvetalk')
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
        self.assertTrue(all(f"garden-1 says zulip:127.0.0.1:{ {'alice': '1000', 'bob': '1001'}[m['subject'].split()[0]]}\n● admitted " in m['content'] for m in mine), mine)
        self.assertTrue(mine[0]['content'].startswith('@**Alice**\n'))
        arrivals = self.root.send({'op': 'world-objects', 'principal': OPENER})['ids']
        self.assertIn('env/zulip:127.0.0.1:1000', arrivals)
        self.assertIn('env/zulip:127.0.0.1:1001', arrivals)
        for uri in got['posted']:  # every posted draft is recorded, so the host knows who it addresses
            self.assertEqual(self.host.send({'op': 'world-addressee', 'parent': uri})['object'], 'garden-1')
        self.assertEqual(self.bridge()['posted'], [], 'nothing is posted twice')
        used = {p['source']: p['used'] for p in self.host.send({'op': 'world-status'})['posts']['sources']}
        self.assertEqual((used['zulip'], used['delve']), (2, 0))  # each Zulip post reserved with the host, counted apart

    def test_replies_in_a_topic_route_to_the_object_the_first_message_addressed(self):
        self.zulip.say('t', 'Alice', SPELL)
        self.bridge()
        self.zulip.say('t', 'Alice', 'and some more words')
        self.zulip.say('t', 'Alice', 'and a last thought')  # past her own message to the world's
        self.zulip.say('t', 'Bob', 'me too')  # under Alice's: he answers her, so it reaches nothing (the second playtest's F4)
        got = self.bridge()
        self.assertEqual(len(got['turns']), 2, got)
        texts = [m['content'] for m in self.zulip.mine()]
        self.assertEqual(len(texts), 3, texts)
        self.assertTrue(all('garden-1 says' in t for t in texts), texts)


    def test_with_a_topic_the_bridge_reads_and_answers_only_there(self):
        self.zulip.say('mobo', 'Alice', SPELL)
        self.zulip.say('elsewhere', 'Bob', SPELL)
        got = self.bridge('mobo')
        self.assertEqual((len(got['turns']), len(got['posted'])), (1, 1), got)
        self.assertEqual([m['subject'] for m in self.zulip.mine()], ['mobo'])


    def test_a_mention_of_the_bot_summons_the_commonplace_and_a_follow_up_in_its_topic_is_read(self):
        self.zulip.say('new', 'Carol', f'@**{BOT["full_name"]}** I planted a fern, what colour is it?')
        got = self.bridge()
        self.assertEqual(len(got['posted']), 1, got)
        self.assertIn('commonplace says', self.zulip.mine()[0]['content'])
        self.zulip.say('new', 'Carol', 'and the moss too')  # in the topic the world answered: read, as a reply to the world's message
        self.zulip.say('new', 'Dana', '@**Carol** nice fern')  # to another resident only: not read
        self.zulip.say('new', 'Carol', 'thanks, Dana')  # under Dana's: answers her, reaches nothing
        from unittest import mock
        real, turns = HostClient.send, []
        with mock.patch.object(HostClient, 'send', lambda h, req: (turns.append(req) if req.get('method') == 'receive' else None) or real(h, req)):
            self.assertEqual(len(self.bridge()['turns']), 1)
        self.assertEqual(turns[0]['replyTo'], zulip.uri_of('delvetalk', 'new', self.zulip.mine()[0]['id']))

    def test_a_zulip_run_has_no_hourly_cap_so_the_seventeenth_draft_posts(self):
        self.assertEqual(self.host.send({'op': 'world-status'})['postQuota'], 16)  # the host has one; Zulip ignores it
        for n in range(17):
            self.zulip.say(f'topic {n}', f'P{n:02d}', SPELL)
        got = self.bridge()
        self.assertEqual((len(got['turns']), len(got['posted']), 'held' in got), (17, 17, False), got)
        self.assertEqual(len(self.zulip.mine()), 17)

    def test_a_send_whose_reply_was_lost_is_found_in_its_topic_not_sent_again(self):
        self.zulip.say('t', 'Alice', SPELL)
        self.zulip.lose = 1
        got = self.bridge()
        self.assertEqual((got['posted'], [h['reason'] for h in got['held']]), ([], ['zulip_refused']), got)
        self.assertEqual(len(self.zulip.mine()), 1)
        again = zulip.post_drafts(self.state, self.host, self.client())
        self.assertEqual(len(self.zulip.mine()), 1, 'the lost send is adopted, never repeated')
        self.assertEqual(again['posted'], [zulip.uri_of('delvetalk', 't', self.zulip.mine()[0]['id'])])
        self.assertEqual(self.host.send({'op': 'world-addressee', 'parent': again['posted'][0]})['object'], 'garden-1')


    def test_the_hands_post_goes_where_the_world_lives_its_zulip_topic(self):
        self.zulip.say('t', 'Alice', 'hello there')
        self.bridge()  # prose addressed to nobody: observed, no draft
        from transport.hand import Hand
        hand = Hand(self.state, self.host)
        uri = self.observed()[0]['uri']
        name = hand.reply(uri, 'a word by hand', 'garden-1')['drafted']
        got = hand.post(name)
        self.assertEqual([(m['subject'], m['content']) for m in self.zulip.mine()], [('t', '@**Alice**\na word by hand')])
        self.assertEqual(self.host.send({'op': 'world-addressee', 'parent': got['uri']})['object'], 'garden-1')

if __name__ == '__main__':
    unittest.main()
