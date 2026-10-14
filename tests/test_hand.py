"""The owner's console at /hand/<world>/ over a real front, with a stub host and a stub poster; Speak against a real
`serve` after genesis: the plan's seeds cast as the opener, the invitations drafted, each post waiting for Post.

Evidence for FOUNDATION §7 and docs/PLAYTEST-2.md §2, §3 (layer: transport). Refuted by a page without the token, a post
without a click, a seed cast twice, a spell drafted that the host refused, or a hand draft the Zulip bridge posts itself.

    python3 -W ignore -m tests.run test_hand
"""
import contextlib
import html
import http.client
import io
import json
import tempfile
import threading
import unittest
import urllib.parse
from unittest import mock
from pathlib import Path

from transport.journal import records, size
from tests.host import addressed
from tests.keys import write_repo_key
from tests.test_bridge import spell_post
from tests.wire import write_journal
from transport import delve, hand, identity, observe, post, watch
from transport.__main__ import main
from transport.host import CLOCK
from transport.http import Front
from transport.state import State

TOKEN = 'sekret-token'


class StubHost:
    def __init__(self):
        self.ops = []

    def send(self, req):
        self.ops.append(req)
        if req['op'] == 'world-status':
            return {'status': 'status', 'height': 41, 'hour': {'hour': 0, 'turns': 2, 'refused': {'quota': 1}},
                    'posts': {'hour': 0, 'sources': [{'source': 'delve', 'used': 3, 'quota': 16, 'next': 60}]}}
        if req['op'] == 'world-post-reserve':
            return {'status': 'reserved'}
        if req['op'] == 'world-posted':
            return {'status': 'unposted' if req.get('unposted') else 'posted'}
        if req['op'] == 'world-interpretations':
            return {'status': 'interpretations', 'pending': [{'id': 'x'}]}
        if req['op'] == 'world-resolve':
            return {'status': 'resolved', 'slug': req['slug'], 'kind': 'receipt', 'cid': 'c'}
        if req['op'] == 'bounds':
            return {'status': 'bounds', 'host': {'maxHistoryLimit': 100}}
        return {'status': 'ok'}

    def at(self, world):
        return self


class PublicMorning(unittest.TestCase):
    def test_a_morning_draft_reads_the_chronicle_paint_and_eight_wants_as_the_public(self):
        from transport.config import Config
        from transport.host import PUBLIC
        with tempfile.TemporaryDirectory() as directory:
            st = State(directory, config=Config(opener='alice', hand_find=False))
            calls = []
            secret = 'Alice alone reads this wanting diary.'
            rows = [{'object': f'bell/{n}', 'name': 'rain', 'reading': 'r' * 200, 'asks': f'delvetalk bell/{n} rain'} for n in range(8)]
            class Host:
                def send(self, req):
                    calls.append(req)
                    private = req.get('principal') != PUBLIC
                    if req['op'] == 'world-chronicle':
                        return {'status': 'chronicled', 'day': 1, 'lines': [secret if private else 'A public day.']}
                    if req['op'] == 'world-render':
                        return {'status': 'painted', 'text': secret if private else 'A public painting.'}
                    if req['op'] == 'world-wanting':
                        return {'rows': [{'object': 'diary', 'name': 'secret', 'reading': secret, 'asks': 'delvetalk diary reveal'}] if private else rows}
                    return {'status': 'ok'}
            h = hand.Hand(st, Host(), sleep=lambda _: None)
            got = h.morning()
            text = h.draft(got['drafted'])[1]['text']
            self.assertNotIn(secret, text)
            self.assertNotIn('diary', text)
            self.assertTrue(text.startswith('A public painting.'))
            self.assertTrue(all(r['asks'] in text for r in rows))
            self.assertEqual([c['principal'] for c in calls], [PUBLIC] * 3)


class HistoryBound(unittest.TestCase):
    """§7 seen in passing: the transport restated `Limits.maxHistoryLimit` as `HISTORY_LIMIT`; a page of history asks for
    as many as the host's `bounds` allows."""

    def test_a_history_page_asks_for_at_most_the_hosts_bound(self):
        from transport import root
        sent = []
        host = type('H', (), {'send': lambda s, req: (sent.append(req), {'status': 'bounds', 'host': {'maxHistoryLimit': 7}}
                                                                          if req['op'] == 'bounds' else {'status': 'ok'})[1]})()
        root.modlog(host, 'did:plc:o', 'porch', tail=20)
        root.modlog(host, 'did:plc:o', tail=20)
        self.assertEqual([r['limit'] for r in sent if r['op'] in ('world-history', 'world-entries')], [7, 7], sent)


class Poster:
    def __init__(self):
        self.calls = []

    def __call__(self, path, st, host, text=None, object=None):
        self.calls.append((Path(path).stem, text, st.config.credentials) + ((object,) if object else ()))
        return {'uri': 'at://did:plc:x/town.delve.feed.post/r1', 'cid': 'bafy'}


class HandCase(unittest.TestCase):
    hosted_accounts = False
    listen = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # A world posting automatically: its credential file is there (tests/test_byhand.py is the world without one).
        (Path(self.tmp.name) / 'delvetalk.toml').write_text(f'credentials = "{self.tmp.name}/creds.json"\nbackups = "{self.tmp.name}/backups"\nhand_find = false\nrepo_keys = "{self.tmp.name}/repo"\n')
        (Path(self.tmp.name) / 'creds.json').write_text('{"identifier": "a", "password": "b"}')
        self.state = State(self.tmp.name)
        if self.hosted_accounts:
            write_repo_key(self.state)
        posts = [spell_post(1, 'garden-1', '2026-10-09T10:00:01Z'), spell_post(2, 'garden-1', '2026-10-09T10:00:02Z')]
        from tests.test_transport import Script
        ob = observe.Observer(self.state, delve.Client(Script(**{'town.delve.feed.searchPosts': lambda p: (200, {'posts': posts}),
                                                                 'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})))
        ob.poll()
        ob.db.close()
        self.uri = posts[0]['uri']
        self.state.write(self.state.outbox / '7-aaaa.json', {
            'replyTo': self.uri, 'replyHandle': 'talkie.delve.town', 'principal': 'p', 'object': 'garden-1', 'slot': None,
            'receipt': {'slug': 'bofab-lukid', 'height': 7, 'outcome': {'tag': 'admitted'}}, 'text': 'planted <b>a</b>', 'posted': False})
        self.poster, self.host = Poster(), StubHost()
        self.hand = hand.Hand(self.state, self.host, TOKEN, poster=self.poster)
        if not self.listen:
            return
        self.front = Front(self.state, self.host, identity.Identity(self.state, delve.Client(None)), ('127.0.0.1', 0), hand=self.hand)
        threading.Thread(target=self.front.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.front.shutdown(), self.front.server_close()))

    def req(self, method, path, form=None, cookie='', headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.front.server_address[1])
        body = urllib.parse.urlencode(form) if form is not None else None
        c.request(method, path, body, {'Cookie': cookie, 'Content-Type': 'application/x-www-form-urlencoded', **(headers or {})})
        r = c.getresponse()
        return r.status, r.read().decode(), dict(r.getheaders())

    def get(self, path='/hand/town/'):
        return self.req('GET', path, cookie=f'dt_hand={TOKEN}')

    def logged(self):
        return [json.loads(l) for l in self.state.hand_log.read_text().splitlines()]


class Hand(HandCase):
    def test_without_the_token_the_page_is_404_and_a_query_token_sets_the_cookie(self):
        self.assertEqual(self.req('GET', '/hand/')[0], 404)
        self.assertEqual(self.req('GET', '/hand/?token=wrong')[0], 404)
        self.assertEqual(self.req('POST', '/hand/town/draft/7-aaaa', {'do': 'post'})[0], 404)
        code, _, headers = self.req('GET', '/hand/?token=' + TOKEN)
        self.assertEqual(code, 302)
        self.assertIn('dt_hand=' + TOKEN, headers['Set-Cookie'])
        self.assertEqual(self.poster.calls, [])
        self.assertIn('The worlds', self.get('/hand/')[1])  # the hand opens on every world serve holds
        self.assertEqual(self.get('/hand/nowhere/')[0], 404)  # a world serve does not hold

    def test_behind_the_edge_the_token_comes_as_a_header_and_no_cookie_is_set(self):
        """The anchor's Caddy asks the owner's password and sets X-Delvetalk-Hand-Token itself: the hand opens on it alone,
        sets no cookie, and is never cached or framed; a wrong header is the tokenless 404."""
        edge = {'X-Delvetalk-Hand-Token': TOKEN, 'Host': 'gsb.example'}
        code, page, headers = self.req('GET', '/hand/', headers=edge)
        self.assertEqual(code, 200)
        self.assertIn('The worlds', page)
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual((headers['Cache-Control'], headers['X-Frame-Options']), ('no-store', 'DENY'))
        self.assertEqual(self.req('GET', '/hand/?token=' + TOKEN, headers=edge)[0], 200)  # the header outranks the query: no redirect
        self.assertEqual(self.req('GET', '/hand/', headers={'X-Delvetalk-Hand-Token': 'wrong'})[0], 404)
        self.assertEqual(self.req('GET', '/hand/town/overview', headers=edge)[0], 200)

    def test_a_form_another_site_posts_through_the_owners_password_is_refused(self):
        """The browser sends the edge's password with any page's form: the hand writes only from its own pages."""
        edge = {'X-Delvetalk-Hand-Token': TOKEN, 'Host': 'gsb.example'}
        form = {'do': 'post', 'text': 'from elsewhere'}
        for other in ({'Sec-Fetch-Site': 'cross-site', 'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'same-site', 'Origin': 'https://www.gsb.example'},
                      {'Origin': 'https://evil.example'}, {'Origin': 'null'}, {'Origin': 'null', 'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.req('POST', '/hand/town/draft/7-aaaa', form, headers={**edge, **other})[0], 403, other)
        self.assertEqual(self.poster.calls, [])
        mine = {**edge, 'Origin': 'null', 'Sec-Fetch-Site': 'same-origin'}  # the edge's no-referrer: a browser's own form
        self.assertEqual(self.req('POST', '/hand/town/draft/7-aaaa', form, headers=mine)[0], 303)
        self.assertEqual(self.req('POST', '/hand/town/draft/7-aaaa', {'do': 'hold'}, headers={**edge, 'Origin': 'https://gsb.example', 'Sec-Fetch-Site': 'same-origin'})[0], 303)
        self.assertEqual(len(self.poster.calls), 1)

    def test_post_calls_the_poster_once_with_the_edited_text_and_logs_it(self):
        code, _, headers = self.req('POST', '/hand/town/draft/7-aaaa', {'do': 'post', 'text': 'edited words'}, f'dt_hand={TOKEN}')
        self.assertEqual(code, 303)
        self.assertEqual(self.poster.calls, [('7-aaaa', 'edited words', f'{self.tmp.name}/creds.json')])
        (line,) = self.logged()
        self.assertEqual((line['what'], line['who'], line['draft'], line['edited']), ('post', 'owner', '7-aaaa', True))

    def test_skip_and_hold_never_post(self):
        self.req('POST', '/hand/town/draft/7-aaaa', {'do': 'hold'}, f'dt_hand={TOKEN}')
        self.assertEqual(self.poster.calls, [])
        self.assertIn('planted', self.get()[1])
        self.req('POST', '/hand/town/draft/7-aaaa', {'do': 'skip', 'reason': 'off topic'}, f'dt_hand={TOKEN}')
        self.assertEqual(self.poster.calls, [])
        d = json.loads((self.state.outbox / '7-aaaa.json').read_text())
        self.assertEqual((d['posted'], d['skipped'], d['reason']), (False, True, 'off topic'))
        self.assertNotIn('rows="8"', self.get()[1])  # no draft left to edit
        self.assertEqual([l['what'] for l in self.logged()], ['hold', 'skip'])


class Register(HandCase):
    """The hand's pages in the field notebook's register (docs/VOICE.md): its own shell and stylesheet on a listener that
    serves nothing else, a viewport for a phone, none of the words the town never says, and a plain-text view."""

    def test_every_page_is_the_hands_shell_with_its_stylesheet_and_a_phone_viewport(self):
        for path in ('/hand/', '/hand/town/', '/hand/town/speak', '/hand/town/watch', '/hand/town/measure', '/hand/town/root/', '/hand/town/overview'):
            code, page, _ = self.get(path)
            self.assertEqual(code, 200, path)
            self.assertTrue(page.startswith('<!doctype html>'), path)
            for part in ('name="viewport" content="width=device-width,initial-scale=1"', '.slip .foot {', 'hr.root {', '<a class="mark" href="/hand/">the hand</a>'):
                self.assertIn(part, page, (path, part))
            self.assertNotIn('/static/style.css', page)  # the hand's listener serves no /static/

    def test_the_hands_own_words_say_none_of_what_the_town_never_says(self):
        import re
        words = re.sub(r'<[^>]*>|\{[^}]*\}', ' ', '\n'.join(hand.H.values())).lower()
        for never in ('thanks', 'thank you', 'sorry', 'please', 'great', 'feel free', 'let me know', 'oops'):
            self.assertNotRegex(words, rf'\b{never}\b')

    def test_the_plain_text_view_is_every_action_as_its_form(self):
        code, text, headers = self.get('/hand/town/?text=1')
        self.assertEqual((code, headers['Content-Type'].split(';')[0]), (200, 'text/plain'))
        self.assertIn('# town', text)
        self.assertIn('POST /hand/town/draft/7-aaaa', text)


class Listener(unittest.TestCase):
    def test_the_hand_is_its_own_listener_and_the_public_front_has_no_hand(self):
        from unittest import mock
        made, stub = [], StubHost()
        stub.close = lambda: None
        with tempfile.TemporaryDirectory() as d, mock.patch.object(State, 'host', lambda self, **k: stub), \
                mock.patch.object(Front, 'serve_forever', lambda self, *a: made.append(self)):
            (Path(d) / 'token').write_text(TOKEN + '\n')
            (Path(d) / 'delvetalk.toml').write_text(f'http_bind = "127.0.0.2"\nhttp_port = 0\nhand_port = 0\nhand_token_file = "{d}/token"\n')
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(['http', '--state', d, '--hand-token', TOKEN])  # the front takes no hand
            main(['http', '--state', d])
            main(['hand', 'serve', '--state', d], host=stub)
        for f in made:
            self.addCleanup(f.server_close)
            threading.Thread(target=super(Front, f).serve_forever, daemon=True).start()
            self.addCleanup(f.shutdown)
        at = {f.server_address[0]: f for f in made}
        self.assertEqual(set(at), {'127.0.0.2', '127.0.0.1'})
        self.assertTrue(hasattr(at['127.0.0.2'], 'serviceauth'))
        self.assertFalse(hasattr(at['127.0.0.1'], 'serviceauth'))
        get = lambda f, path: (lambda c: (c.request('GET', path), c.getresponse().status)[1])(http.client.HTTPConnection(*f.server_address[:2]))
        self.assertEqual(get(at['127.0.0.2'], '/hand/?token=' + TOKEN), 404)  # the public port has no hand
        self.assertEqual(get(at['127.0.0.1'], '/hand/?token=' + TOKEN), 302)
        self.assertEqual(get(at['127.0.0.1'], '/AGENTS.md'), 404)  # and the hand's listener nothing else


class Unpost(HandCase):
    """`unpost` withdraws a post we made, on Delve or Zulip, and never anyone else's."""
    def posted(self, uri, cid='bafy9'):
        path = self.state.outbox / '7-aaaa.json'
        self.state.write(path, dict(json.loads(path.read_text()), posted=True, sent={'uri': uri, 'cid': cid}, intent='draft-7-aaaa'))
        return path

    def pds(self, did):
        class Pds:
            def __init__(self): self.sent = []
            def write(self, nsid, body, token=None):
                self.sent.append((nsid, body))
                return {'did': did, 'accessJwt': 't'} if 'Session' in nsid else {}
        return Pds()

    def test_a_delve_post_of_ours_is_deleted_and_the_host_told_the_draft_and_log_keep_it(self):
        path, pds = self.posted('at://did:plc:me/town.delve.feed.post/r9'), self.pds('did:plc:me')
        (self.state.root / 'creds.json').write_text('{"identifier": "a", "password": "b"}')
        self.assertEqual(self.hand.unpost('7-aaaa', 'wrong card', client=pds), {'unposted': 'at://did:plc:me/town.delve.feed.post/r9'})
        self.assertEqual(pds.sent[1], ('com.atproto.repo.deleteRecord', {'repo': 'did:plc:me', 'collection': 'town.delve.feed.post', 'rkey': 'r9'}))
        told = [o for o in self.host.ops if o['op'] == 'world-posted'][-1]
        self.assertEqual((told['unposted'], told['uri'], told['intent'], told['reason']), (True, 'at://did:plc:me/town.delve.feed.post/r9', 'draft-7-aaaa', 'wrong card'))
        self.assertEqual(json.loads(path.read_text())['unposted']['reason'], 'wrong card')
        self.assertEqual(self.logged()[-1]['what'], 'unpost')
        with self.assertRaises(hand.HandError):  # once
            self.hand.unpost('7-aaaa', 'again', client=pds)

    def test_anyone_elses_post_and_an_unposted_draft_are_refused_before_any_delete(self):
        self.posted('at://did:plc:someone/town.delve.feed.post/r9')
        (self.state.root / 'creds.json').write_text('{"identifier": "a", "password": "b"}')
        pds = self.pds('did:plc:me')
        with self.assertRaises(hand.HandError):
            self.hand.unpost('7-aaaa', 'x', client=pds)
        self.assertEqual([n for n, _ in pds.sent], ['com.atproto.server.createSession'])
        self.state.write(self.state.outbox / '7-aaaa.json', dict(json.loads((self.state.outbox / '7-aaaa.json').read_text()), posted=False))
        with self.assertRaises(hand.HandError):
            self.hand.unpost('7-aaaa', 'x', client=pds)

    def test_a_zulip_post_is_deleted_through_the_bots_client(self):
        self.posted('zulip://delvetalk/garden/42', '42')
        deleted = []
        zulip = type('Z', (), {'delete': lambda s, mid: deleted.append(mid)})()
        self.hand.unpost('7-aaaa', 'misread', zulip=zulip)
        self.assertEqual(deleted, [42])
        with self.assertRaises(hand.HandError):
            self.posted('zulip://delvetalk/garden/43', '43')
            self.state.write(self.state.outbox / '7-aaaa.json', {k: v for k, v in json.loads((self.state.outbox / '7-aaaa.json').read_text()).items() if k != 'unposted'})
            self.hand.unpost('7-aaaa', 'misread')  # the world has no Zulip bridge row


class Writer:
    """The delve.town side of post.post_draft: createSession and createRecord."""
    def __init__(self): self.sent = []
    def write(self, nsid, body, token=None):
        self.sent.append((nsid, body))
        return {'did': 'did:plc:x', 'accessJwt': 't'} if 'Session' in nsid else {'uri': 'at://did:plc:x/town.delve.feed.post/r9', 'cid': 'bafy9'}
    def record(self, uri): return {'uri': uri, 'cid': 'c', 'value': {}}
    def resolve_handle(self, h): return {}


class Cli(HandCase):
    def cmd(self, *argv, stdin=None):
        import contextlib, io, sys
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            if stdin is not None:
                stack.enter_context(__import__('unittest.mock').mock.patch.object(sys, 'stdin', io.StringIO(stdin)))
            code = main(['hand', *argv, '--state', str(self.state.root)], out, host=self.host, poster=self.poster)
        return code, out.getvalue()

    def js(self, *argv, **kw):
        code, text = self.cmd(*argv, '--json', **kw)
        self.assertEqual(code, 0, text)
        return json.loads(text)

    def logged_who(self):
        return {l['who'] for l in self.logged()}

    def test_status_json_is_the_one_monitoring_probe(self):
        import time as t
        now = t.time()
        stamp = lambda ago: t.strftime('%Y-%m-%dT%H:%M:%SZ', t.gmtime(now - ago))
        self.state.access_log.write_text(f'{stamp(60)} GET / 200 10 - town\n{stamp(120)} GET /o/x 500 9 - town\n{stamp(1800)} GET / 503 9 - town\n{stamp(7200)} GET / 500 9 - town\n')
        self.state.spend.write_text(''.join(json.dumps({'at': now - ago, 'inputTokens': 1000, 'outputTokens': 50}) + '\n'
                                                              for ago in (100, 200, 7200)))
        journal, backups = self.state.journal, self.state.root / 'backups'
        shown = [{'genesis': 1}] + [{'outcome': {'tag': 'suspended'}, 'pad': 'x' * n} for n in (10, 20, 30)]
        write_journal(journal, [dict(e, height=h, previous='p', hash='h%d' % h) for h, e in enumerate(shown, 1)])
        backups.mkdir()
        (backups / 'delvetalk-20261011T000000Z.tar.gz').write_bytes(b'x')
        (backups / 'last-verify').write_text('ok 20261011T000000Z\n')
        p = watch.probe(self.state, self.host)
        self.assertEqual(p['front'], {'requests5m': 2, '5xx5m': 1, '5xxHour': 2})
        self.assertEqual(p['hour'], {'hour': 0, 'turns': 2, 'refused': {'quota': 1}})  # the host's counters, as world-status gives them
        self.assertEqual((p['model']['hour']['calls'], p['model']['day']['calls']), (2, 3))
        self.assertEqual(p['reservations'], {'source': 'delve', 'used': 3, 'quota': 16, 'next': 60})
        self.assertEqual(p['interpretations'], {'pending': 1, 'maxAttempts': 0})
        self.assertEqual((p['journal']['height'], p['journal']['bytes'], p['journal']['medianSuspendedBytes']),
                         (41, size(journal), len(records(journal)[2][1])))  # the middle suspension's record
        self.assertEqual((p['backup']['newest'], p['backup']['verify']), ('delvetalk-20261011T000000Z.tar.gz', 'ok'))
        self.assertLess(p['backup']['ageSeconds'], 60)
        self.assertEqual(set(p) >= {'clock', 'observed', 'freeFraction', 'at'}, True)
        self.assertEqual(p['observed'], 2)


    def test_edit_keeps_the_original_and_post_calls_the_poster_once_as_cli(self):
        f = self.state.root / 'new.txt'
        f.write_text('first edit')
        self.assertEqual(self.js('edit', '7-aaaa', '--text-file', str(f)), {'edited': '7-aaaa'})
        self.js('edit', '7-aaaa', '--stdin', stdin='second edit')
        d = json.loads((self.state.outbox / '7-aaaa.json').read_text())
        self.assertEqual((d['text'], d['original']), ('second edit', 'planted <b>a</b>'))
        self.js('post', '7-aaaa', '--object', 'garden-1')
        self.assertEqual(self.poster.calls, [('7-aaaa', 'second edit', f'{self.tmp.name}/creds.json', 'garden-1')])
        self.assertEqual([l['what'] for l in self.logged()], ['edit', 'edit', 'post'])
        self.assertEqual(self.logged_who(), {'cli'})

    def test_draft_reads_one_draft_and_show_stays_the_power(self):
        self.assertEqual(self.js('draft', '7-aaaa')['text'], 'planted <b>a</b>')  # D11: `show` was the power and shadowed it
        code, req = self.cmd('show', '--object', 'garden', '--reading', 'back')[0], self.host.ops[-1]
        self.assertEqual((code, req['op'], req['method']), (0, 'world-turn', 'show'))

    def test_skip_hold_and_unknown_drafts(self):
        self.js('hold', '7-aaaa')
        self.js('skip', '7-aaaa', '--reason', 'noise')
        self.assertEqual(self.poster.calls, [])
        self.assertEqual(self.js('outbox'), [])
        self.assertEqual(self.js('outbox', '--all')[0]['drafts'][0]['state'], 'skipped')
        self.assertEqual(self.cmd('hold', 'nope')[0], 1)
        self.assertEqual([l['what'] for l in self.js('log', '--tail', '1')], ['skip'])

    def test_retry_makes_the_bridge_run_the_observation_again(self):
        from tests.test_bridge import Stub
        from transport import bridge
        (self.state.outbox / '7-aaaa.json').unlink()
        self.state.skipped.write_text(self.uri + '\n')
        stub = Stub()
        self.assertNotIn(self.uri, bridge.run(self.state, stub)['turns'])
        self.assertTrue(next(r for r in self.js('inbox') if r['uri'] == self.uri)['skipped'])
        self.assertEqual(self.js('retry', self.uri), {'requeued': self.uri})
        self.assertEqual(self.cmd('retry', 'at://nope')[0], 1)
        self.assertIn(self.uri, bridge.run(self.state, stub)['turns'])

    def test_reply_drafts_by_hand_then_posts_and_records_with_the_object(self):
        from functools import partial
        from transport import post
        w = Writer()
        creds = self.state.root / 'creds.json'
        creds.write_text('{"identifier": "a", "password": "b"}')
        f = self.state.root / 'mine.txt'
        f.write_text('a word by hand')
        name = self.js('reply', self.uri, '--text-file', str(f), '--object', 'garden-1')['drafted']
        self.assertIn('-hand-', name)
        self.poster = partial(post.post_draft, reader=w, client=w)
        code, out = self.cmd('post', name)
        self.assertEqual(code, 0, out)
        self.assertEqual((w.sent[1][1]['record']['text'], w.sent[1][1]['record']['reply']['parent']['uri']), ('a word by hand', self.uri))
        self.assertEqual([(o['object'], o['uri']) for o in self.host.ops if o['op'] == 'world-posted'], [('garden-1', 'at://did:plc:x/town.delve.feed.post/r9')])
        self.assertEqual(self.cmd('reply', 'at://nope', '--text-file', str(f), '--object', 'x')[0], 1)


class Guests(HandCase):
    """An invitation (transport/identity.py): the operator names a guest with no account here, `guest:<origin host>:<name>`,
    and hands it a code accepted once; `invites` lists them with their last use, `revoke-invite` ends code and credential.
    Refuted by a code listed or put in a URL, a second live invitation of one name, or a revoked guest still authenticated."""
    cmd, js = Cli.cmd, Cli.js
    hosted_accounts = True

    def ident(self):
        return identity.Identity(self.state, None)

    def test_invite_names_a_realm_qualified_guest_lists_it_without_its_code_and_revoke_ends_its_credential(self):
        got = self.js('invite', 'claude46', '--note', 'phencounting, asked by ember', '--expires', '3')
        self.assertEqual((got['name'], got['handle'], got['principal'], got['note']),
                         ('claude46', 'claude46', 'guest:gsb.fg-goose.online:claude46', 'phencounting, asked by ember'))
        self.assertRegex(got['code'], identity.INVITE_CODE)
        self.assertAlmostEqual(got['expires'] - __import__('time').time(), 3 * 86400, delta=60)
        self.assertEqual(self.cmd('invite', 'claude46')[0], 1)  # one live invitation a name
        self.assertEqual(self.cmd('invite', 'Not A Name')[0], 1)
        (row,) = self.js('invites')
        self.assertEqual((row['name'], row['state'], row['used']), ('claude46', 'open', None))
        self.assertNotIn(got['code'], json.dumps(self.js('invites')) + self.state.hand_log.read_text())
        cred = self.ident().accept(got['code'])['credential']
        self.assertEqual(self.ident().authenticate(cred)['did'], 'guest:gsb.fg-goose.online:claude46')
        (row,) = self.js('invites')
        self.assertEqual(row['state'], 'accepted')
        self.assertIsNotNone(row['used'])  # the last use is the credential's
        self.assertEqual(self.js('revoke-invite', 'claude46')['credentials'], 1)
        with self.assertRaises(identity.IdentityError):
            self.ident().authenticate(cred)
        self.assertEqual(self.cmd('revoke-invite', 'claude46')[0], 1)
        self.assertEqual(self.js('invite', 'claude46')['principal'], 'guest:gsb.fg-goose.online:claude46')  # revoked: invited again, the same guest
        self.assertEqual([l['what'] for l in self.logged()], ['invite-guest', 'revoke-invite', 'invite-guest'])

    def test_an_open_code_lists_as_open_then_with_the_name_chosen_and_count_mints_codes_one_per_line(self):
        got = self.js('invite', '--note', 'for whoever', '--expires', '14')
        self.assertEqual((got['name'], got['principal']), (None, None))
        self.assertAlmostEqual(got['expires'] - __import__('time').time(), 14 * 86400, delta=60)
        code, text = self.cmd('invite', '--count', '3')
        lines = text.split()
        self.assertEqual((code, len(lines), len(set(lines))), (0, 3, 3))
        self.assertTrue(all(identity.INVITE_CODE.fullmatch(l) for l in lines), text)
        self.assertEqual(self.cmd('invite', 'named', '--count', '2')[0], 1)
        rows = self.js('invites')
        self.assertEqual([r['name'] for r in rows], ['(open)'] * 4)
        cred = self.ident().accept(got['code'], 'chose-this')['credential']
        self.assertEqual(self.ident().authenticate(cred)['did'], 'guest:gsb.fg-goose.online:chose-this')
        self.assertEqual(sorted(r['name'] for r in self.js('invites')), ['(open)'] * 3 + ['chose-this'])
        self.assertNotIn(got['code'], json.dumps(self.js('invites')) + self.state.hand_log.read_text())
        self.assertEqual(self.cmd('invite', 'chose-this')[0], 1)  # the chosen name is held
        open_id = next(r['id'] for r in self.js('invites') if r['name'] == '(open)')
        self.assertEqual(self.js('revoke-invite', str(open_id))['credentials'], 0)
        self.assertEqual(sum(r['state'] == 'revoked' for r in self.js('invites')), 1)

    def test_two_accepts_of_names_on_one_open_code_race_and_exactly_one_wins(self):
        code = self.ident().invite(None)['code']
        barrier, results = threading.Barrier(2), {}

        def go(name):
            ident = self.ident()  # its own connection, as another process would have
            barrier.wait()
            try:
                results[name] = ident.accept(code, name)['handle']
            except identity.IdentityError as err:
                results[name] = err.code
        threads = [threading.Thread(target=go, args=(n,)) for n in ('left', 'right')]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sum(v in ('left', 'right') for v in results.values()), 1, results)
        self.assertEqual(sorted(v for v in results.values() if v not in ('left', 'right')), ['invitation_spent'], results)
        (row,) = self.js('invites')
        self.assertEqual(row['state'], 'accepted')
        self.assertIn(row['name'], ('left', 'right'))

    def test_a_table_from_before_open_codes_is_carried_over(self):
        import sqlite3
        db = sqlite3.connect(self.state.identity)
        db.executescript('DROP TABLE IF EXISTS invitations; CREATE TABLE invitations(name TEXT PRIMARY KEY, principal TEXT NOT NULL, code TEXT NOT NULL, note TEXT, created REAL, expires REAL, state TEXT NOT NULL, accepted REAL, revoked REAL, used REAL);'
                         "INSERT INTO invitations VALUES('old','guest:gsb.fg-goose.online:old','h','n',1,2,'accepted',1,NULL,NULL);")
        db.commit()
        db.close()
        (row,) = self.js('invites')
        self.assertEqual((row['name'], row['principal'], row['state']), ('old', 'guest:gsb.fg-goose.online:old', 'accepted'))
        self.assertEqual(self.js('invite')['name'], None)

    def test_the_worlds_page_invites_and_revokes_showing_the_code_once_on_the_page_never_in_a_url(self):
        code, page, headers = self.req('POST', '/hand/', {'guest': 'invite', 'name': 'claude46', 'note': 'phencounting'}, f'dt_hand={TOKEN}')
        self.assertEqual(code, 200)
        shown = __import__('re').search(r'dt_invite_[A-Za-z0-9_-]{32}', page)[0]
        self.assertNotIn('Location', headers)
        self.ident().accept(shown)
        page = self.get('/hand/')[1]
        self.assertIn('guest:gsb.fg-goose.online:claude46', page)
        self.assertIn('phencounting', page)
        self.assertNotIn(shown, page)
        self.assertEqual(self.req('POST', '/hand/', {'guest': 'invite', 'name': 'x'})[0], 404)  # without the token, nothing
        code, page, _ = self.req('POST', '/hand/', {'guest': 'revoke', 'name': 'claude46'}, f'dt_hand={TOKEN}')
        self.assertIn('revoked claude46: 1 credential ended', page)
        self.assertEqual(self.js('invites')[0]['state'], 'revoked')


class Plan(unittest.TestCase):
    """docs/PLAYTEST-2.md as the hand reads it at its start."""

    def test_the_plan_gives_every_seed_and_every_invitation_each_with_its_spells(self):
        """Counted against the file's own shape (§2's numbered spells, §3's table rows), so an edit of the plan is read, never
        broken: today four seeds and twelve invitations."""
        import re
        path = Path(__file__).resolve().parent.parent / 'docs' / 'PLAYTEST-2.md'
        p, text = hand.plan(path), path.read_text()
        two, three = hand.section(text, 2), hand.section(text, 3)
        self.assertEqual(len(p['seeds']), len(re.findall(r'^\d+\. `delvetalk ', two, re.M)))
        self.assertEqual([r['minute'] for r in p['invitations']], [int(m) for m in re.findall(r'^\| (\d+) \|', three, re.M)])
        self.assertGreater(len(p['seeds']) * len(p['invitations']), 0)
        self.assertTrue(all(s.startswith('delvetalk ') for s in p['seeds']))
        self.assertTrue(all(r['spells'] and r['answered'] for r in p['invitations']), p['invitations'])
        first = p['invitations'][0]
        zulip, delve = hand.invitation_text(first, 'zulip'), hand.invitation_text(first, 'delve')
        pinged = re.match(r'`((?:@\S+\s*)+)`', first['words'])
        if pinged:  # the residents it pings, as each transport mentions them
            self.assertTrue(zulip.startswith(' '.join(f'@**{n[1:]}**' for n in pinged[1].split())), zulip)
            self.assertTrue(delve.startswith(pinged[1].strip()), delve)
        self.assertIn('\n\n    ' + first['spells'][0], zulip)  # quoted: four spaces, so no bridge runs it
        self.assertEqual(hand.plan('/nonexistent'), {'path': '/nonexistent', 'seeds': [], 'invitations': []})


def observed(st, uri, did, handle, text, at='2026-10-11T10:00:00Z'):
    """An observation as the bridge stores one (observe.SCHEMA), for a turn the test makes under its uri."""
    import sqlite3
    st.home.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(st.observed)
    db.executescript(observe.SCHEMA)
    db.execute('INSERT INTO observations(uri,json) VALUES(?,?)', (uri, json.dumps({
        'uri': uri, 'author': {'did': did, 'handle': handle}, 'text': text, 'kind': 'post', 'createdAt': at, 'replyTo': None, 'mentions': [], 'root': None})))
    db.commit()
    db.close()


def cast(town, who, text, intent):
    """`text` as the bridge turns a post of `who`'s: `receive` on the card the host reads in it."""
    card = town.send(op='spell-parse', text=text)['spell']['card']
    return town.send(op='world-turn', principal=who, object=card, method='receive', identity=intent,
                     argument={'tag': 'record', 'fields': [{'name': 'text', 'value': {'tag': 'label', 'value': text}},
                                                           {'name': 'post', 'value': {'tag': 'label', 'value': intent}}]})


class Speak(unittest.TestCase):
    """Speak and Watch over a real `serve` after genesis, the world a Zulip channel: a seed is cast once as the opener,
    the card and receipt come back, and the post that says so waits for Post into its topic, recorded for the thing it
    made; the watch shows each turn as it was typed, by handle, with the card it offered and the draft it made."""

    @classmethod
    def setUpClass(cls):
        from tests.town import Town
        cls.dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.dir.cleanup)
        cls.town = Town(cls.dir.name, cleanup=cls.addClassCleanup)
        cls.st = State(cls.town.state)
        cls.st.write(cls.st.row, {'world': 'town', 'transport': 'zulip', 'realm': 'tulip.example', 'channel': 'delvetalk', 'zuliprc': None})
        cls.hand = hand.Hand(cls.st, cls.town.client, TOKEN)

    def test_a_seed_is_cast_once_as_the_opener_and_its_post_waits_for_post_in_its_topic(self):
        spell = self.hand.plan['seeds'][1]  # the garden's planting: a seed that makes a thing
        came = self.hand.cast(spell, intent=self.hand.seed_intent(spell))
        bell = came['object']
        self.assertEqual((came['outcome'], bell.startswith('garden/bell/')), ('admitted', True), came)
        self.assertIn(bell, came['text'])
        _, d = self.hand.draft(came['drafted'])
        self.assertEqual((d['topic'], d['replyTo'], d['object'], d['posted'], d['hand']), ('welcome', None, bell, False, True))
        self.assertTrue(d['text'].startswith('    ' + spell + '\n\n'), d['text'])
        entry = self.town.send(op='world-receipt', principal=self.hand.owner, identity=self.hand.seed_intent(spell))
        self.assertEqual(entry['receipt']['identity']['principal'], self.hand.owner)
        again = self.hand.cast(spell, intent=self.hand.seed_intent(spell))  # the same intent: the first receipt, the first draft
        self.assertEqual((again['height'], again['drafted']), (came['height'], came['drafted']))
        self.assertEqual(sum(1 for i, _, _ in self.hand.drafts() if '-speak-' in i), 1)
        seed = self.hand.spoken()['seeds'][1]
        self.assertEqual((seed['cast']['height'], seed['cast']['state']), (came['height'], 'waiting for Post'))
        from transport import zulip
        sent = []
        bot = type('Bot', (), {'newest': lambda s, stream: 0, 'sent_after': lambda s, *a: None,
                               'send': lambda s, stream, topic, text: sent.append((stream, topic, text)) or {'id': 501}})()
        self.assertEqual(zulip.post_drafts(self.st, self.town.client, bot), {'posted': []})  # the bridge leaves the hand's own
        h = hand.Hand(self.st, self.town.client, TOKEN, poster=lambda path, st, host, text=None: post.post_draft(path, st, host, text, zulip=bot))
        h.post(came['drafted'])
        self.assertEqual(sent[0][:2], ('delvetalk', 'welcome'))
        uri = json.loads((self.st.outbox / f"{came['drafted']}.json").read_text())['sent']['uri']
        self.assertEqual((addressed(self.town, uri) or {}).get('object'), bell)  # a reply to the post reaches the bell

    def test_a_refused_spell_drafts_nothing(self):
        came = self.hand.cast('delvetalk room/99 write / text: nobody here')
        self.assertEqual((came['outcome'], came['drafted']), ('unknownObject', None), came)
        with self.assertRaises(hand.HandError):
            self.hand.cast('  ')

    def test_a_question_mark_shows_the_cards_spells_journals_nothing_and_drafts_nothing(self):
        before = self.town.send(op='world-status')['height']
        came = self.hand.cast('delvetalk porch/goblet ?', intent='hand:speak:usage-1')  # the deploy of 5db9aa79: "hand: porch/goblet: usage"
        self.assertEqual((came['outcome'], came['drafted'], came['height']), ('usage', None, None), came)
        self.assertIn('delvetalk porch/goblet inspirit', came['text'])
        self.assertEqual(self.town.send(op='world-status')['height'], before)
        code, page, _ = self.hand.handle('GET', '/hand/town/speak?came=hand:speak:usage-1', f'dt_hand={TOKEN}')
        self.assertIn('porch/goblet inspirit', page)  # the page asks again: the log keeps the spell, not the answer

    def test_a_try_is_said_as_a_preview_names_no_receipt_journals_nothing_and_drafts_nothing(self):
        # The deploy of d943a90e: `hand speak` of a try said "admitted bell/2 v8, entry 1002, receipt nunuk-hilot", a
        # receipt no host issued, and drafted it for Post.
        before = self.town.send(op='world-status')['height']
        came = self.hand.cast('delvetalk try\n  delvetalk bell/1 rain / text: tried by the hand', intent='hand:speak:try-1')
        self.assertEqual((came['outcome'], came['drafted'], came['height'], came['slug']), ('preview', None, None, None), came)
        self.assertTrue(came['text'].startswith('preview, nothing done'), came['text'])
        self.assertIn('would be admitted', came['text'])
        self.assertNotIn('receipt', came['text'])
        self.assertEqual(self.town.send(op='world-status')['height'], before)
        code, page, _ = self.hand.handle('GET', '/hand/town/speak?came=hand:speak:try-1', f'dt_hand={TOKEN}')
        self.assertIn('preview, nothing done', page)

    def test_words_go_to_a_card_as_direct_prose_and_hobs_answer_comes_back(self):
        from transport import interpret
        model = lambda req: {'status': 'replied', 'json': None, 'raw': 'delvetalk library read / page: spells', 'model': 'mock', 'usage': {}}
        read = []  # hob reads while the hand waits: one interpreter round per wait
        h = hand.Hand(self.st, self.town.client, TOKEN, sleep=lambda s: read.append(interpret.run(self.st, self.town.client, model)))
        came = h.cast('what is this place?')  # no spell: to the commonplace, as the play page sends words
        self.assertEqual((came['card'], came['outcome'], came['drafted'], came['waiting']), ('commonplace', 'suspended', None, False), came)
        self.assertTrue(read and read[0]['settled'], read)
        self.assertTrue(came['text'].strip(), came)  # hob's answer, through the turns the words were handed on to
        turn = self.town.send(op='world-receipt', principal=h.owner, identity=came['intent'])['receipt']
        self.assertEqual(turn['identity']['principal'], h.owner)
        self.assertEqual(h.tail(1)[0]['what'], 'ask')
        # Words to the garden itself are hob's too, offered the garden's table; its answer runs on the card the spell names.
        read.clear()
        asked = lambda req: {'status': 'replied', 'json': None, 'raw': 'delvetalk garden plant / colour: violet / seed: a violet bell', 'model': 'mock', 'usage': {}}
        h2 = hand.Hand(self.st, self.town.client, TOKEN, sleep=lambda s: read.append(interpret.run(self.st, self.town.client, asked)))
        garden = h2.cast('could I have a violet bell', to='garden')
        self.assertEqual((garden['card'], garden['outcome']), ('garden', 'suspended'), garden)
        self.assertTrue(read and read[0]['settled'], read)
        self.assertTrue(garden['text'].startswith('Planted, '), garden)  # hob's spell ran as the speaker's turn on the garden
        self.assertRegex(garden['text'], r'at garden/bell/\d+;')
        code, _, headers = h.handle('POST', '/hand/town/speak', f'dt_hand={TOKEN}', {'spell': 'and the porch?', 'to': 'garden', 'intent': 'hand:ask:web'})
        came = urllib.parse.parse_qs(urllib.parse.urlsplit(dict(headers)['Location']).query)['came'][0]
        self.assertEqual(came, 'hand:ask:web')
        page = h.handle('GET', '/hand/town/speak?came=' + came, f'dt_hand={TOKEN}')[1]
        self.assertIn('Came back', page)

    def test_the_speak_page_offers_the_plan_and_a_cast_comes_back_on_it(self):
        cookie = f'dt_hand={TOKEN}'
        code, page, _ = self.hand.handle('GET', '/hand/town/speak', cookie)
        self.assertEqual(code, 200)
        plan = self.hand.plan
        for text in ("The hand's seeds", f"seed {len(plan['seeds'])}", f"T+{plan['invitations'][-1]['minute']}", 'answered when', 'Topic of #delvetalk', 'name="intent"'):
            self.assertIn(text, page)
        code, _, headers = self.hand.handle('POST', '/hand/town/speak', cookie, {'spell': 'delvetalk garden plant / colour: amber / seed: a speak test',
                                                                                'intent': 'hand:speak:test-1', 'topic': 'welcome'})
        self.assertEqual(code, 303)
        came = urllib.parse.parse_qs(urllib.parse.urlsplit(dict(headers)['Location']).query)['came'][0]
        code, page, _ = self.hand.handle('GET', '/hand/town/speak?came=' + came, cookie)
        self.assertIn('Came back', page)
        self.assertIn('garden/bell/', page)

    def test_the_watch_follows_the_journal_and_the_outbox_newest_first(self):
        resident, uri = 'did:plc:' + 'w' * 24, 'zulip://delvetalk/welcome/9001'
        self.town.send(op='world-arrive', principal=CLOCK, did=resident, handle='kestrel')
        observed(self.st, uri, resident, 'kestrel', 'look:\ndelvetalk garden plant / colour: violet / seed: a watched bell')
        planted = cast(self.town, resident, 'delvetalk garden plant / colour: violet / seed: a watched bell', uri)
        spell = 'delvetalk garden plant / colour: amber / seed: a bell the hand planted'
        came = self.hand.cast(spell, intent='hand:speak:watch-1')
        rows = self.hand.watch()
        heights = [r['height'] for r in rows if r['height']]
        self.assertEqual(heights, sorted(heights, reverse=True))  # newest first
        mine = next(r for r in rows if r['height'] == came['height'])
        self.assertEqual((mine['who'], mine['turn'], mine['tag']), ('the town', spell, 'admitted'))
        self.assertTrue(mine['first'] and mine['slug'] and mine['object'].startswith('garden/bell/'), mine)
        self.assertEqual([d['id'] for d in mine['drafts']], [came['drafted']])
        theirs = next(r for r in rows if r['height'] == planted['receipt']['height'])
        self.assertEqual((theirs['who'], theirs['turn']), ('kestrel', 'delvetalk garden plant / colour: violet / seed: a watched bell'))
        bell = mine['object']
        self.assertEqual([r['height'] for r in self.hand.watch(bell) if r['height']], [x['height'] for x in self.hand.entries(bell, 100)][:30])
        code, page, _ = self.hand.handle('GET', '/hand/town/watch', f'dt_hand={TOKEN}')
        self.assertIn('<meta http-equiv="refresh" content="5">', page)
        self.assertIn(f'/hand/town/root/?object={urllib.parse.quote(bell, safe="")}', page)
        self.assertIn(f"receipt {came['slug']}", page)
        self.assertNotIn('http-equiv="refresh"', self.hand.handle('GET', '/hand/town/watch?still=1', f'dt_hand={TOKEN}')[1])

    def test_came_follows_words_until_hob_answers_and_looks_again_while_it_waits(self):
        from transport import interpret
        model = lambda req: {'status': 'replied', 'json': None, 'raw': 'delvetalk library read / page: spells', 'model': 'mock', 'usage': {}}
        h, cookie = hand.Hand(self.st, self.town.client, TOKEN, sleep=lambda s: None), f'dt_hand={TOKEN}'  # nobody reads while the hand waits
        code, _, headers = h.handle('POST', '/hand/town/speak', cookie, {'spell': 'what lies behind the moss gate?', 'to': 'commonplace', 'intent': 'hand:ask:late'})
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(dict(headers)['Location']).query)['came'], ['hand:ask:late'])
        before = h.came('hand:ask:late')
        self.assertTrue(before['waiting'], before)  # words at the commonplace wait for hob, who has not read them yet
        page = h.handle('GET', '/hand/town/speak?came=hand:ask:late', cookie)[1]
        self.assertIn('<meta http-equiv="refresh" content="3">', page)
        self.assertIn('hob is reading', page)
        self.assertTrue(interpret.run(self.st, self.town.client, model)['settled'])  # hob answers, later
        after = h.came('hand:ask:late')
        self.assertFalse(after['waiting'], after)
        self.assertNotEqual(after['text'], before['text'])
        page = h.handle('GET', '/hand/town/speak?came=hand:ask:late', cookie)[1]
        self.assertNotIn('http-equiv="refresh"', page)
        self.assertIn(html.escape(after['text'].strip().split('\n')[0]), page)

    def test_a_paint_that_falls_back_keeps_the_hosts_reason_and_clause(self):
        """The hand's morning paint fell back (`painted: False` after a 117-token reply) and nothing said why: `painted`
        keeps the host's `exact` reason and the paint check's clause, and `fell_back` says them."""
        from transport import interpret
        from transport.host import fell_back, painted
        self.town.send(op='world-renders')  # the worker attends
        asked = self.town.send(op='world-render', principal=self.hand.owner, object='commonplace')
        self.assertEqual(asked['status'], 'pending', asked)
        reply = {'status': 'replied', 'json': None, 'raw': 'Like ' + 'x' * 900, 'model': 'claude-haiku-5-5', 'usage': {}}
        for _ in range(2):  # a paint refused for its length alone is asked for once more
            interpret.paint(self.town.client, lambda req: reply)
        got = painted(self.town.client, self.hand.owner, 'commonplace', sleep=lambda s: None)
        self.assertEqual((got.get('text'), got['reason']), (None, 'rejected'), got)
        self.assertEqual(got['clause'], 'length', got)
        self.assertTrue(fell_back(got).startswith(f"the paint fell back: rejected at its {got['clause']} clause"), fell_back(got))
        self.assertIsNone(fell_back({'text': 'a paint'}))

    def test_an_owner_private_want_never_enters_a_public_morning_draft(self):
        from deploy import genesis
        from deploy.seed import closure, modules_on_disk
        owner, obj = self.hand.owner, 'morning-private-diary'
        created = self.town.send(op='world-create', principal=owner, identity=obj, object=obj, entry='initial',
                                 modules=closure('Record', modules_on_disk()), law=genesis.RECORD_LAW, read={'principals': [owner]},
                                 seed=genesis.rec(owner=genesis.lab(owner), maker=genesis.lab(owner)))
        self.assertEqual(created['status'], 'created', created)
        spell = f'delvetalk {obj} want\nname: secret\nreading: the owner alone knows\nwhen: count(new.lines) == 0\nasks: delvetalk kind/bell make / seed: a bell / colour: silver'
        wanted = cast(self.town, owner, spell, 'morning-private-want')
        self.assertEqual(wanted['status'], 'admitted', wanted)
        rows = self.town.send(op='world-wanting', principal=owner)['rows']
        self.assertTrue(any(r['object'] == obj for r in rows), rows)
        h = hand.Hand(self.st, self.town.client, sleep=lambda _: None)
        got = h.morning(day=137)
        self.assertNotIn(obj, got['text'])
        self.assertNotIn('the owner alone knows', got['text'])

    def test_the_morning_card_is_painted_shown_and_drafted_once_a_day_never_posted(self):
        """`hand morning` (OVERHAUL §4 (c)): the day painted from its strokes with what wants a hand exact beneath, drafted
        once a day for Post; a day with no paint stands as the chronicle's exact lines."""
        from transport import interpret
        self.town.send(op='world-renders')  # the worker attends
        queued = self.town.send(op='world-render', principal='anonymous', morning=True)
        self.assertEqual(queued['status'], 'pending', queued)
        paint = 'Like moonlight through silk.'
        reply = {'status': 'replied', 'json': None, 'raw': paint, 'model': 'claude-haiku-5-5', 'usage': {}}
        done = interpret.paint(self.town.client, lambda req: reply if 'a day of the town' in req['user'] else dict(reply, raw='x' * 900))
        self.assertIn(queued['key'], done['painted'], done)
        got = self.hand.morning()
        _, d = self.hand.draft(got['drafted'])
        self.assertTrue(got['painted'])
        self.assertTrue(d['text'].startswith(paint + '\n\nWhat wants a hand, oldest first:\n'), d['text'])
        first = self.town.send(op='world-wanting', principal='anonymous', limit=8, oldest=True)['rows'][0]  # the longest waiting
        self.assertIn('%s: %s\n  %s' % (first['object'], first.get('reading') or first['name'], first['asks']), d['text'])
        self.assertEqual((d['speak'], d['posted'], d['topic']), ({'morning': got['day']}, False, 'welcome'))
        with self.assertRaises(hand.HandError):
            self.hand.morning()
        quiet = self.hand.morning(day=1)  # nothing journaled that day: no paint, the chronicle's exact line
        self.assertEqual((quiet['painted'], quiet['fellBack']), (False, 'the paint fell back: pending'), quiet)  # its wants are painted; no worker here
        self.assertIsNone(got['fellBack'])
        self.assertTrue(quiet['text'].startswith('day 1: nothing was journaled.\n\nWhat wants a hand'), quiet['text'])
        self.assertIn('morning card, day %d' % got['day'], [r['turn'] for r in self.hand.drafted()[2]])

    def test_an_invitation_is_drafted_once_with_its_spell_quoted(self):
        row = self.hand.plan['invitations'][-1]  # the plan's last: no other test drafts it
        got = self.hand.invite(row['minute'])
        _, d = self.hand.draft(got['drafted'])
        self.assertEqual((d['topic'], d['object'], d['speak']), ('welcome', None, {'invitation': row['minute']}))
        for spell in row['spells']:
            self.assertIn('\n    ' + spell, d['text'])
        with self.assertRaises(hand.HandError):
            self.hand.invite(row['minute'])
        with self.assertRaises(hand.HandError):
            self.hand.invite(row['minute'] + 1)
        self.assertEqual(next(r for r in self.hand.spoken()['invitations'] if r['minute'] == row['minute'])['draft']['state'], 'waiting for Post')


class Measure(unittest.TestCase):
    """docs/PLAYTEST-2.md §4 counted from a real journal: a short playtest in which two residents make kinds and things,
    use, cite and name each other's, one law refuses, the owner's own make is not a resident's, and the clock rains."""
    M0 = 29336333  # unix minutes: the bridge's clock
    A, B, OWNER = 'did:plc:' + 'k' * 24, 'did:plc:' + 'y' * 24, 'zulip:tulip.example:7'

    @classmethod
    def setUpClass(cls):
        from tests.town import Town
        cls.dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.dir.cleanup)
        cls.town = t = Town(cls.dir.name, cleanup=cls.addClassCleanup)
        (Path(t.state) / 'delvetalk.toml').write_text(f'owner_principals = "{cls.OWNER}"\n')
        cls.st, S0 = State(t.state), cls.M0 * 60
        cls.st.write(cls.st.row, {'world': 'town', 'transport': 'zulip', 'realm': 'tulip.example', 'channel': 'delvetalk', 'zuliprc': None})  # its posts are its bot's
        for did, handle in ((cls.A, 'kestrel'), (cls.B, 'yue'), (cls.OWNER, 'Hyphaed Biscuit')):
            t.send(op='world-arrive', principal=CLOCK, did=did, handle=handle)
        t.send(op='world-advance', principal=CLOCK, height=cls.M0)
        h = hand.Hand(cls.st, t.client, TOKEN, poster=lambda *a, **k: {'uri': 'zulip://delvetalk/welcome/1', 'cid': '1'}, clock=lambda: S0)
        h.post(h.invite(0)['drafted'])  # T0: the invitation's Post
        observed(cls.st, 'zulip://delvetalk/welcome/2', cls.A, 'kestrel', 'hello', time_of(S0 + 60))
        observed(cls.st, 'zulip://delvetalk/welcome/3', cls.B, 'yue', 'hi', time_of(S0 + 120))
        t.send(op='world-advance', principal=CLOCK, height=cls.M0 + 3)
        kind = lambda name, law='': f'delvetalk kinds make / name: {name} / of: record / form: text: text 1..80 / head: {name}: {{text}} / law: {law} / body:'
        for n, (who, text) in enumerate([
                (cls.A, kind('lamp')), (cls.A, 'delvetalk kind/lamp make / text: a small light'), (cls.B, 'delvetalk lamp/1 write / text: brighter'),
                (cls.B, kind('sealed', 'law maker "only its maker writes": request.subject == new.maker')), (cls.B, 'delvetalk kind/sealed make / text: mine'),
                (cls.A, 'delvetalk sealed/1 write / text: yours?'), (cls.B, 'delvetalk sealed/1 door / label: lamp / to: lamp/1'),
                (cls.A, 'delvetalk anthology write / text: seal: what sealed/1 keeps'), (cls.A, 'delvetalk kind/sealed make / text: hers'),
                (cls.B, 'delvetalk kind/lamp make / text: a second light'), (cls.OWNER, kind('hyphae'))]):
            cast(t, who, text, f'post-{n}')
        t.send(op='world-advance', principal=CLOCK, height=cls.M0 + 130)  # the tide's hour: the opener's wake ticks it
        cls.st.interpretations.mkdir(parents=True, exist_ok=True)
        for i, raw in enumerate(('delvetalk garden plant / colour: amber / seed: x', 'none')):
            (cls.st.interpretations / f'{i}.json').write_text(json.dumps({'id': str(i), 'object': 'garden', 'reply': {'status': 'replied', 'raw': raw}}))
        from transport import measure
        cls.m = measure.measures(cls.st)

    def test_things_made_are_the_residents_by_kind_and_maker(self):
        made = self.m['made']
        self.assertEqual([r['object'] for r in made['rows']], ['kind/lamp', 'lamp/1', 'kind/sealed', 'sealed/1', 'sealed/2', 'lamp/2'])
        self.assertEqual(made['byKind'], {'kind': 2, 'lamp': 2, 'sealed': 2})
        self.assertEqual(made['byMaker'], {'kestrel': 3, 'yue': 3})  # the owner's kind/hyphae is no resident's

    def test_use_by_another_citations_laws_and_refusals(self):
        used = {(r['object'], r['by']) for r in self.m['used']['rows'] if r['residentMade']}
        self.assertEqual(used, {('lamp/1', 'yue'), ('kind/sealed', 'kestrel'), ('kind/lamp', 'yue')})
        self.assertEqual((self.m['used']['makers'], self.m['goNoGo']), (2, {'used by another, at least 3 by at least 2 makers': True}))
        self.assertEqual([(r['object'], r['maker']) for r in self.m['laws']['written']], [('kind/sealed', 'yue')])
        self.assertTrue(self.m['laws']['written'][0]['law'].startswith('law maker "only its maker writes"'))
        self.assertEqual([(r['from'], r['to'], r['toResident']) for r in self.m['citations']['doors']], [('sealed/1', 'lamp/1', True)])
        self.assertEqual([(r['in'], r['names'], r['by']) for r in self.m['citations']['named']], [('anthology', 'sealed/1', 'kestrel')])
        self.assertEqual(self.m['refusals']['byClass'], {'lawRefused': 1})

    def test_time_rain_and_interpretations(self):
        self.assertEqual(self.m['T0'], time_of(self.M0 * 60))
        self.assertEqual(self.m['firstMade'], {'secondsFromT0': 180, 'byResident': {'kestrel': 120, 'yue': 60}})  # no post: the clock's minute stands in
        self.assertGreaterEqual(self.m['unposted']['count'], 1)
        self.assertIn('tide', [o for r in self.m['unposted']['rows'] for o in r['objects']])
        self.assertEqual((self.m['interpretations']['count'], self.m['interpretations']['byVerdict']), (2, {'none': 1, 'spell': 1}))

    def test_wants_answered_by_residents_prompted_or_not_and_wants_still_held(self):
        """docs/GENESIS.md "The measure": kestrel's kind closes the kinds' want "no kind made here yet but the town's own"
        within ten minutes after the T0 invitation, which names kinds, so it is prompted; yue's door on sealed/1 closes
        the record's own `door` want, which a kind's law line no longer takes from its things, unprompted; the opener's
        own doors close wants that are no resident's answer; the anthology's pending line still waits for its keeper."""
        w, name = self.m['wants'], lambda p: self.m['names'].get(p, p)
        self.assertEqual([(r['object'], r['want'], name(r['by'])) for r in w['prompted']], [('kinds', 'made', 'kestrel')])
        self.assertEqual([(r['object'], r['want'], name(r['by'])) for r in w['unprompted']], [('sealed/1', 'door', 'yue')])
        self.assertIn(('anthology', 'pending'), {(r['object'], r['want']) for r in w['ignored']})

    def test_a_want_closed_within_ten_minutes_after_a_hand_post_naming_its_thing_is_prompted(self):
        from transport import measure
        entries = [{'height': 1, 'identity': {'principal': 'o', 'intent': 'g'}, 'outcome': {'tag': 'created'}, 'wanted': [{'object': 'bell/1', 'want': 'rain'}]},
                   {'height': 2, 'identity': {'principal': 'a', 'intent': 'u'}, 'outcome': {'tag': 'admitted'}, 'unwanted': [{'object': 'bell/1', 'want': 'rain'}]}]
        split = lambda at, hand: tuple(len(measure.wants(entries, {'u': at}, hand)[k]) for k in ('prompted', 'unprompted', 'ignored'))
        self.assertEqual(split(1300, [(1000, 'a rain on bell/1, if you like')]), (1, 0, 0))
        self.assertEqual(split(1700, [(1000, 'a rain on bell/1, if you like')]), (0, 1, 0))  # past ten minutes
        self.assertEqual(split(1300, [(1000, 'a rain on bell/12')]), (0, 1, 0))  # another thing
        self.assertEqual(split(900, [(1000, 'a rain on bell/1')]), (0, 1, 0))  # before the post
        self.assertEqual(measure.wants(entries[:1], {}, [])['ignored'], [{'object': 'bell/1', 'want': 'rain', 'since': 1}])

    def test_the_page_status_and_harvest_read_the_same_numbers(self):
        out = io.StringIO()
        self.assertEqual(main(['status', '--state', self.town.state, '--playtest'], out), 0)
        self.assertEqual(json.loads(out.getvalue()), json.loads(json.dumps(self.m)))
        code, page, _ = hand.Hand(self.st, self.town.client, TOKEN).handle('GET', '/hand/town/measure', f'dt_hand={TOKEN}')
        self.assertEqual(code, 200)
        for text in ('things made by residents', 'by kind: kind 2, lamp 2, sealed 2', 'holds', 'sealed/1 -&gt; lamp/1 by yue'):
            self.assertIn(text, page)
        refused = next(r for r in hand.Hand(self.st, self.town.client, TOKEN).watch() if r['tag'] == 'refused' and not r['turn'].startswith('↳'))
        self.assertEqual((refused['who'], refused['turn'], refused['outcome']), ('kestrel', 'refused sealed/1', 'lawRefused'))  # whole, from the journal
        from deploy.ring import harvest
        r = harvest.harvest(self.dir.name)
        self.assertEqual(r['playtest']['made'], self.m['made'])
        self.assertIn('| things made by residents | 6 |', harvest.markdown(r))


class PlaytestTwo(unittest.TestCase):
    """The second Zulip playtest's state (run-20261011-063034, trimmed to what the measures read: the journal whole, the
    drafts, observations and readings slimmed) measured as docs/review/zulip-playtest-2.md D12 found it should be."""

    @classmethod
    def setUpClass(cls):
        import tarfile
        from transport import measure
        cls.dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.dir.cleanup)
        with tarfile.open(Path(__file__).resolve().parent / 'fixtures' / 'playtest-2' / 'state.tar.gz') as t:
            t.extractall(cls.dir.name, filter='data')
        cls.m = measure.measures(State(Path(cls.dir.name) / 'state'))

    def test_the_first_make_is_seconds_after_t0_in_wall_time_never_before_it(self):
        self.assertEqual(self.m['T0'], '2026-10-11T10:32:06Z')  # the Post of the T+0 invitation
        self.assertEqual(self.m['made']['rows'][0]['object'], 'garden/bell/2')
        self.assertEqual(self.m['firstMade'], {'secondsFromT0': 14, 'byResident': {'Kestrel': 5, 'Claude': 0, 'Yuè月': 0}})  # the post that made it

    def test_no_reply_is_the_summons_nothing_answered_not_residents_talking(self):
        self.assertEqual(self.m['noReply'], ['zulip://delvetalk/welcome/69103'])  # 69147 reached only avatars; 69140, 69141, 69159 were quiet by design

    def test_nobody_posting_rains_nothing_genesis_and_hob_are_not_the_clock(self):
        self.assertEqual(self.m['unposted'], {'count': 0, 'notes': 0, 'rows': []})  # not genesis's 67, 69, 70; not hob's 112


def time_of(seconds):
    import time
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(seconds))



class PartialPosting(unittest.TestCase):
    def setUp(self):
        from tests.test_transport import Recorder
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st, self.host = State(self.tmp.name), Recorder()
        self.hand = hand.Hand(self.st, self.host, TOKEN)
        self.path = self.st.outbox / '1-thread.json'
        self.ones = [{'uri': f'at://did:plc:me/town.delve.feed.post/r{k}', 'cid': str(k), 'part': k, 'intent': f'draft-1-thread#{k}', 'recorded': {'status': 'posted'}} for k in (1, 2)]
        self.st.write(self.path, {'text': 'old', 'posted': False, 'object': 'library', 'sentParts': self.ones, 'byHand': self.ones})

    def test_editing_a_draft_with_a_sent_part_is_refused_with_the_reason(self):
        with self.assertRaisesRegex(hand.HandError, 'parts.*posted|part.*sent'):
            self.hand.edit('1-thread', 'new')
        self.assertEqual(json.loads(self.path.read_text())['text'], 'old')

    def test_withdrawing_a_partial_thread_deletes_and_unregisters_each_distinct_uri(self):
        from unittest.mock import patch
        with patch.object(post, 'unsend') as delete:
            self.hand.unpost('1-thread', 'withdraw', client=object())
        self.assertEqual([c.args[0] for c in delete.call_args_list], [p['uri'] for p in self.ones])
        self.assertEqual([r['uri'] for r in self.host.posted], [p['uri'] for p in self.ones])
        d = json.loads(self.path.read_text())
        self.assertTrue(all(p['unposted']['recorded']['status'] == 'unposted' for p in d['sentParts']))
        self.assertEqual(len(d['sentParts']), 2)

    def test_withdrawal_resumes_a_failed_unregister_without_deleting_twice(self):
        from unittest.mock import patch
        self.host.fail = 1
        with patch.object(post, 'unsend') as delete:
            self.hand.unpost('1-thread', 'withdraw', client=object())
            self.hand.unpost('1-thread', 'withdraw', client=object())
        self.assertEqual(delete.call_count, 2)
        self.assertEqual([r['uri'] for r in self.host.posted], [self.ones[0]['uri'], self.ones[1]['uri'], self.ones[0]['uri']])

    def test_two_threads_updating_a_locked_draft_preserve_both_updates(self):
        from concurrent.futures import ThreadPoolExecutor
        def update(key):
            with self.st.draft_lock(self.path):
                d = json.loads(self.path.read_text())
                self.st.write(self.path, dict(d, **{key: True}))
        with ThreadPoolExecutor(2) as pool:
            for result in pool.map(update, ('left', 'right')): pass
        d = json.loads(self.path.read_text())
        self.assertTrue(d['left'] and d['right'])

    def test_two_atomic_writers_use_different_temporary_files(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        import os
        barrier, original = threading.Barrier(2), os.replace
        def replace(source, target):
            barrier.wait(timeout=5)
            original(source, target)
        path = self.st.home / 'atomic.json'
        with patch('transport.state.os.replace', side_effect=replace):
            with ThreadPoolExecutor(2) as pool:
                jobs = [pool.submit(self.st.write, path, {'writer': k, 'text': 'x' * post.MAX_TEXT}) for k in (1, 2)]
                for job in jobs: job.result()
        self.assertIn(json.loads(path.read_text())['writer'], (1, 2))
        self.assertEqual(json.loads(path.read_text())['text'], 'x' * post.MAX_TEXT)
        self.assertEqual(list(path.parent.glob('atomic.json.*.tmp')), [])

    def test_a_completed_thread_with_a_duplicate_manual_uri_withdraws_every_part_once(self):
        from unittest.mock import patch
        d = json.loads(self.path.read_text())
        self.st.write(self.path, dict(d, posted=True, sent=self.ones[-1]))
        with patch.object(post, 'unsend') as delete:
            self.hand.unpost('1-thread', 'withdraw', client=object())
        self.assertEqual(delete.call_count, 2)
        self.assertEqual(len(self.host.posted), 2)

    def test_withdrawing_a_part_whose_registration_failed_repairs_it_before_unregistering(self):
        from unittest.mock import patch
        from tests.test_transport import Recorder
        class Strict(Recorder):
            def __init__(self):
                super().__init__()
                self.active = set()
            def send(self, req):
                if req['op'] == 'world-posted' and req.get('unposted') and req['uri'] not in self.active:
                    return {'status': 'error', 'message': 'post was never recorded here'}
                got = super().send(req)
                if req['op'] == 'world-posted' and not req.get('unposted') and got['status'] == 'posted':
                    self.active.add(req['uri'])
                return got
        self.host = Strict()
        self.hand.host = self.host
        d = json.loads(self.path.read_text())
        for one in d['sentParts']: one['recorded'] = {'status': 'error'}
        d.pop('byHand')
        self.st.write(self.path, d)
        with patch.object(post, 'unsend'):
            self.hand.unpost('1-thread', 'withdraw', client=object())
        self.assertEqual(json.loads(self.path.read_text())['unposted']['recorded']['status'], 'unposted')

    def test_a_new_single_post_is_withdrawn_without_reusing_an_old_parts_withdrawal(self):
        from unittest.mock import patch
        old = {'uri': 'zulip://delvetalk/garden/42', 'cid': '42'}
        self.st.write(self.path, {'text': 'old', 'object': 'library', 'posted': True, 'sent': old, 'intent': 'draft-1-thread'})
        deleted = []
        bot = type('Bot', (), {'delete': lambda bot, mid: deleted.append(mid)})()
        self.hand.unpost('1-thread', 'old', zulip=bot)
        d = json.loads(self.path.read_text())
        d.update(posted=True, sent={'uri': 'zulip://delvetalk/garden/43', 'cid': '43'})
        d.pop('unposted')
        self.st.write(self.path, d)
        with self.assertRaisesRegex(hand.HandError, 'no zuliprc'):
            self.hand.unpost('1-thread', 'new')
        self.hand.unpost('1-thread', 'new', zulip=bot)
        self.assertEqual(deleted, [42, 43])
        d = json.loads(self.path.read_text())
        self.assertEqual([p['uri'] for p in d['sentParts']], [old['uri'], 'zulip://delvetalk/garden/43'])
        self.assertTrue(all(p['unposted']['recorded']['status'] == 'unposted' for p in d['sentParts']))

    def test_a_write_in_the_outbox_keeps_the_given_value_without_stamping_it(self):
        value = {'text': 'given', 'posted': False}
        self.st.write(self.path, value)
        self.assertEqual(json.loads(self.path.read_text()), value)

    def test_only_new_draft_stamps_creation_and_an_edit_preserves_it(self):
        self.st.new_draft(self.path, {'text': 'given', 'posted': False})
        d = json.loads(self.path.read_text())
        self.assertGreater(observe.instant(d['createdAt']), 0)
        self.st.write(self.path, dict(d, text='edited'))
        self.assertEqual(json.loads(self.path.read_text())['createdAt'], d['createdAt'])

    def test_draft_lock_files_are_outside_the_outbox_and_writes_leave_no_temporary_files(self):
        with self.st.draft_lock(self.path):
            self.st.write(self.path, json.loads(self.path.read_text()))
        self.assertEqual([p for p, _ in self.st.drafts()], [self.path])
        self.assertEqual(list(self.st.outbox.iterdir()), [self.path])

    def test_draft_lock_rejects_reentry_instead_of_blocking_the_same_thread(self):
        with self.st.draft_lock(self.path):
            with self.assertRaisesRegex(RuntimeError, 'already held'):
                with self.st.draft_lock(self.path):
                    self.fail('a draft lock cannot be entered twice')

    def test_a_crash_after_deletion_retries_only_registration_and_unregistering(self):
        from unittest.mock import patch
        with patch.object(post, 'unsend') as delete:
            with patch.object(self.host, 'send', side_effect=RuntimeError('crash')):
                with self.assertRaises(RuntimeError):
                    self.hand.unpost('1-thread', 'withdraw', client=object())
            self.hand.unpost('1-thread', 'withdraw', client=object())
        self.assertEqual(delete.call_count, 2)
        self.assertEqual(json.loads(self.path.read_text())['unposted']['recorded']['status'], 'unposted')

    def test_outbox_scans_ignore_lock_and_temporary_files_even_when_they_contain_invalid_json(self):
        artifacts = [self.path.with_suffix('.lock'), self.path.with_name(self.path.name + '.example.tmp')]
        for artifact in artifacts:
            artifact.write_text('not JSON')
            self.addCleanup(artifact.unlink, missing_ok=True)
        self.assertEqual([p for p, _ in self.st.drafts()], [self.path])
        self.assertEqual([p for p, _ in self.st.unposted()], [self.path])
        for artifact in artifacts: artifact.unlink()
        self.assertEqual(list(self.st.outbox.iterdir()), [self.path])

    def test_a_failed_atomic_replace_keeps_the_draft_and_cleans_its_temporary_file(self):
        from unittest.mock import patch
        before = json.loads(self.path.read_text())
        with patch('transport.state.os.replace', side_effect=OSError('replace failed')):
            with self.assertRaises(OSError):
                self.st.write(self.path, {'text': 'replacement', 'posted': False})
        self.assertEqual(json.loads(self.path.read_text()), before)
        self.assertEqual(list(self.st.outbox.iterdir()), [self.path])


if __name__ == '__main__':
    unittest.main()


class RouteCase(HandCase):
    """Real HTTP dispatch and form decoding, without opening a listener."""
    listen = False

    def req(self, method, path, form=None, cookie=''):
        from types import SimpleNamespace
        from transport.http import Handler
        h = Handler.__new__(Handler)
        h.server = SimpleNamespace(hand=self.hand)
        h.command, h.path = method, path
        raw = urllib.parse.urlencode(form or {}).encode()
        h.headers = {'Cookie': cookie, 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': str(len(raw))}
        h.rfile, h.wfile = io.BytesIO(raw), io.BytesIO()
        h.client_address, h.did, h.head = ('127.0.0.1', 1), None, False
        responses, headers = [], []
        h.send_response = responses.append
        h.send_header = lambda key, value: headers.append((key, value))
        h.end_headers = lambda: None
        h.dispatch(method)
        return responses[0], h.wfile.getvalue().decode(), dict(headers)


class Portal(RouteCase):
    """Every hand verb has a reachable form and exercises the same operation as the CLI.

    Refuted by a filter silently dropped, a control without a route, incomplete raw reads,
    a thread linked out of order, or a malformed form reaching the host.
    """
    def send_form(self, path, form):
        return self.req('POST', '/hand/town/' + path, form, f'dt_hand={TOKEN}')

    def test_parser_verbs_have_controls_and_routes_or_an_explicit_local_only_reason(self):
        import argparse
        from transport import root
        from html.parser import HTMLParser
        class Controls(HTMLParser):
            def __init__(self, page):
                super().__init__()
                self.actions, self.links, self.names, self.fields, self.textareas, self.current = set(), set(), set(), {}, {}, None
                self.feed(page)
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'form':
                    self.current = attrs.get('action')
                    self.actions.add(self.current)
                    self.fields.setdefault(self.current, set())
                    self.textareas.setdefault(self.current, set())
                if tag == 'a': self.links.add(attrs.get('href'))
                if tag in ('input', 'textarea', 'select'):
                    self.names.add(attrs.get('name'))
                    if self.current: self.fields[self.current].add(attrs.get('name'))
                    if self.current and tag == 'textarea': self.textareas[self.current].add(attrs.get('name'))
            def handle_endtag(self, tag):
                if tag == 'form': self.current = None
        pages = {p: Controls(self.get('/hand/town/' + p)[1]) for p in ('', 'speak', 'watch', 'root/', 'status')}
        worlds = Controls(self.get('/hand/')[1])
        read = pages['status']
        for verb in ('status', 'draft', 'log', 'spend', 'modlog', 'find'):
            self.assertIn('/hand/town/' + verb, read.actions, verb)
        for verb in ('root/dump', 'root/entries'):
            self.assertIn('/hand/town/' + verb, pages['root/'].actions)
        for face, specs in (('root', root.ROOT), ('mod', {**root.POWERS, 'settings': root.MOD_SETTINGS})):
            for verb, spec in specs.items():
                action = f'/hand/town/{face}/{verb}'
                self.assertIn(action, pages['root/'].actions)
                fields = spec[1] if face == 'mod' and verb != 'settings' else spec
                self.assertTrue({n for n, _ in fields} <= pages['root/'].fields[action])
        self.assertIn('text', pages['root/'].textareas['/hand/town/root/card'])
        for name in ('all', 'since', 'kind'):
            self.assertIn(name, pages[''].names)
        for name in ('spell', 'intent', 'to', 'replyTo', 'day'):
            self.assertIn(name, pages['speak'].names)
        self.assertIn('/hand/town/welcome', pages['speak'].actions)
        self.assertIn('/hand/town/morning', pages['speak'].actions)
        self.assertIn('limit', pages['watch'].names)
        self.assertIn('count', worlds.names)
        common = argparse.ArgumentParser(add_help=False)
        parser = argparse.ArgumentParser()
        hand.parser(parser, common)
        verbs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices
        covered = {'inbox', 'outbox', 'draft', 'edit', 'post', 'posted', 'match', 'skip', 'hold', 'unpost', 'status', 'search',
                   'retry', 'reply', 'log', 'spend', 'modlog', 'find', 'speak', 'morning', 'plan', 'watch', 'worlds',
                   'invite', 'invites', 'revoke-invite', 'welcome', 'root', *root.POWERS, 'settings',
                   'limits',  # an open town's root page, "Newcomers" (tests/test_newcomers.py)
                   'slow', 'held', 'let-in', 'turn-away', 'flag', 'unflag',  # the root page's slow, the worlds page's door (tests/test_moderation.py)
                   'overview', 'vacate',  # the overview page (read only); the root page's vacate (tests/test_moderation.py Gone)
                   'automod'}  # the automod page: its list, and restore, confirm and hide on each row (tests/test_automod.py)
        self.assertIn('/hand/town/vacate', pages['root/'].actions)
        self.assertIn('/hand/town/overview', pages[''].links)
        self.assertIn('/hand/town/automod', pages[''].links)
        self.assertEqual(set(verbs), covered | {'serve'})  # starts a listener; cannot run inside its own page

    def test_console_forwards_inbox_filters_and_all_outbox_without_hiding_finished_drafts(self):
        with mock.patch.object(self.hand, 'inbox', wraps=self.hand.inbox) as inbox, \
                mock.patch.object(self.hand, 'outbox', wraps=self.hand.outbox) as outbox:
            self.assertEqual(self.get('/hand/town/?since=6&kind=summon&all=1')[0], 200)
            inbox.assert_called_once_with(6, 'summon')
            outbox.assert_called_once_with(True)
        self.hand.skip('7-aaaa', 'noise')
        page = self.get('/hand/town/?all=1')[1]
        self.assertIn('7-aaaa', page)
        self.assertIn('/hand/town/draft?draft=7-aaaa', page)

    def test_read_controls_forward_every_option_and_show_complete_escaped_results(self):
        from transport import root
        payload = '<script>' + 'x' * post.MAX_TEXT + '</script>'
        cases = [('status', 'status', {}, (), {}), ('draft?draft=7-aaaa', 'view', {}, ('7-aaaa',), {}),
                 ('log?tail=1', 'tail', {}, (1,), {}), ('spend?month=2026-09', 'spend', {}, ('2026-09',), {}),
                 ('modlog?object=bell&tail=7', 'modlog', root, (self.host, self.hand.owner, 'bell', 7), {}),
                 ('find?query=bell', 'find', root, (self.host, self.hand.owner, 'bell'), {}),
                 ('root/dump?object=bell', 'dump', root, (self.host, self.hand.owner, 'bell'), {}),
                 ('root/entries?after=6&object=bell&principal=p&limit=7', 'entries', root,
                  (self.state, 6, 7, 'bell', 'p'), {})]
        for path, name, module, args, kwargs in cases:
            with self.subTest(path=path), mock.patch.object(module or self.hand, name, return_value={'value': payload}) as call:
                code, page, _ = self.get('/hand/town/' + path)
                self.assertEqual(code, 200)
                self.assertIn(html.escape(payload), page)
                self.assertNotIn(payload, page)
                if name == 'find':
                    self.assertEqual(call.call_args.args[:3], args)
                    self.assertEqual(list(call.call_args.args[3]), list(self.hand.observed().values()))
                else:
                    call.assert_called_once_with(*args, **kwargs)

    def test_search_retry_reply_and_edit_routes_use_real_hand_operations(self):
        self.get('/hand/town/?slug=bofab-lukid')
        self.assertEqual(self.host.ops[-1]['slug'], 'bofab-lukid')
        self.state.skipped.write_text(self.uri + '\n')
        self.assertEqual(self.send_form('retry', {'uri': self.uri})[0], 303)
        self.assertNotIn(self.uri, self.state.words(self.state.skipped))
        text = '<script>' + 'r' * (post.MAX_TEXT - 12)
        self.assertEqual(self.send_form('reply', {'uri': self.uri, 'object': 'garden-1', 'text': text})[0], 303)
        draft = self.hand.tail(1)[0]['draft']
        self.assertEqual(self.hand.draft(draft)[1]['text'], text)
        self.send_form('draft/7-aaaa', {'do': 'edit', 'text': text + '\r\nend'})
        self.assertEqual(self.hand.draft('7-aaaa')[1]['text'], text + '\nend')
        self.assertIn(html.escape(text), self.get()[1])
        self.assertNotIn(text, self.get()[1])

    def test_post_object_override_and_unpost_control_use_the_existing_methods(self):
        self.send_form('draft/7-aaaa', {'do': 'post', 'object': 'bell'})
        self.assertEqual(self.poster.calls[-1][-1], 'bell')
        Unpost.posted(self, 'at://did:plc:me/town.delve.feed.post/r9')
        with mock.patch.object(self.hand, 'unpost', return_value={'unposted': 'a'}) as withdraw:
            code, page, _ = self.get('/hand/town/?all=1')
            self.assertIn('value="unpost"', page)
            self.assertEqual(self.send_form('draft/7-aaaa', {'do': 'unpost', 'reason': 'withdraw'})[0], 303)
            withdraw.assert_called_once_with('7-aaaa', 'withdraw')

    def test_posted_threads_forward_links_in_order_and_match_uses_existing_finder(self):
        links = '\r\n'.join(f'at://did:plc:me/town.delve.feed.post/p{n}' for n in range(1, 4))
        self.assertIn('one a line, in order', self.get()[1])
        with mock.patch.object(self.hand, 'posted', return_value={'note': 'recorded'}) as record:
            self.assertEqual(self.send_form('draft/7-aaaa', {'do': 'posted', 'link': links})[0], 303)
            record.assert_called_once_with('7-aaaa', links)
        with mock.patch.object(self.hand, 'find_posts', return_value={'linked': [], 'offers': []}) as finder:
            self.assertEqual(self.send_form('match', {})[0], 303)
            finder.assert_called_once_with()

    def fixture_posts(self, text):
        """A read-only posting account repository; no request leaves the test."""
        from types import SimpleNamespace
        root_ref = {'uri': self.uri, 'cid': 'parent'}
        records = {self.uri: {'uri': self.uri, 'cid': 'parent', 'value': {'text': 'the parent'}}}
        uris, parent = [], root_ref
        for n, part in enumerate(post.parts(text), 1):
            uri = f'at://{self.state.config.poster}/town.delve.feed.post/part{n}'
            record = {'uri': uri, 'cid': str(n), 'value': {'text': part, 'createdAt': '2099-01-01T00:00:00Z',
                      'reply': {'parent': parent, 'root': root_ref}}}
            records[uri] = record
            uris.append(uri)
            parent = {'uri': uri, 'cid': str(n)}
        self.hand._reader = SimpleNamespace(record=lambda uri: records[uri],
                                           get=lambda *a, **kw: {'records': [records[u] for u in uris]})
        return uris

    def test_a_real_multi_link_thread_is_registered_in_order_and_wrong_order_is_refused(self):
        text = 'the bell rings ' * 180
        self.hand.edit('7-aaaa', text)
        uris = self.fixture_posts(text)
        self.assertGreater(len(uris), 1)
        _, _, headers = self.send_form('draft/7-aaaa', {'do': 'posted', 'link': uris[1]})
        self.assertIn('wrong_parent', urllib.parse.unquote_plus(headers['Location']))
        self.assertFalse(self.hand.draft('7-aaaa')[1]['posted'])
        self.assertEqual(self.send_form('draft/7-aaaa', {'do': 'posted', 'link': '\r\n'.join(uris)})[0], 303)
        d = self.hand.draft('7-aaaa')[1]
        self.assertTrue(d['posted'])
        self.assertEqual([one['uri'] for one in d['sentParts']], uris)
        self.assertEqual([r['uri'] for r in self.host.ops if r['op'] == 'world-posted'], uris)
        self.assertEqual(self.poster.calls, [])

    def test_real_match_links_a_thread_and_withdrawal_unregisters_each_part_once(self):
        text = 'the bell rings ' * 180
        self.hand.edit('7-aaaa', text)
        uris = self.fixture_posts(text)
        self.send_form('match', {})
        self.assertTrue(self.hand.draft('7-aaaa')[1]['posted'])
        page = self.get('/hand/town/?all=1')[1]
        self.assertIn('value="unpost"', page)
        with mock.patch.object(post, 'unsend') as delete:
            self.send_form('draft/7-aaaa', {'do': 'unpost', 'reason': 'wrong card'})
        self.assertEqual([c.args[0] for c in delete.call_args_list], uris)
        self.assertEqual([r['uri'] for r in self.host.ops if r['op'] == 'world-posted' and r.get('unposted')], uris)
        self.assertEqual(self.hand.draft('7-aaaa')[1]['unposted']['reason'], 'wrong card')
        self.assertNotIn('value="unpost"', self.get('/hand/town/?all=1')[1])

    def test_a_partly_posted_thread_can_be_withdrawn_and_cannot_be_edited(self):
        text = 'the bell rings ' * 180
        self.hand.edit('7-aaaa', text)
        uris = self.fixture_posts(text)
        self.send_form('draft/7-aaaa', {'do': 'posted', 'link': uris[0]})
        self.assertIn('value="unpost"', self.get()[1])
        _, _, headers = self.send_form('draft/7-aaaa', {'do': 'edit', 'text': 'changed'})
        self.assertIn('frozen', urllib.parse.unquote_plus(headers['Location']))
        self.assertEqual(self.hand.draft('7-aaaa')[1]['text'], text)
        with mock.patch.object(post, 'unsend') as delete:
            self.send_form('draft/7-aaaa', {'do': 'unpost', 'reason': 'partial'})
        delete.assert_called_once()
        self.assertEqual(delete.call_args.args[0], uris[0])

    def test_speak_all_options_seeds_and_invitations_reach_the_existing_operations(self):
        self.hand.plan = {'path': 'plan.md', 'seeds': ['delvetalk bell rain'], 'invitations': []}
        came = {'line': 'admitted', 'intent': 'i', 'drafted': 'd'}
        with mock.patch.object(self.hand, 'cast', return_value=came) as cast:
            self.send_form('speak', {'spell': 'words', 'intent': 'i', 'to': 'bell', 'topic': 't', 'replyTo': self.uri})
            cast.assert_called_once_with('words', 't', self.uri, 'i', 'bell', wait=0)
            cast.reset_mock()
            self.send_form('speak', {'seed': '1', 'topic': 't', 'replyTo': self.uri})
            cast.assert_called_once_with('delvetalk bell rain', 't', self.uri, self.hand.seed_intent('delvetalk bell rain'), wait=0)
        with mock.patch.object(self.hand, 'invite', return_value={'drafted': 'd'}) as invite:
            self.send_form('invite', {'minute': '9', 'topic': 't', 'replyTo': self.uri})
            invite.assert_called_once_with('9', 't', self.uri)
        self.assertEqual(self.get('/hand/town/plan')[0], 200)

    def test_seed_number_is_shared_with_the_cli_and_invalid_seeds_do_not_cast(self):
        import argparse
        self.hand.plan = {'path': 'plan.md', 'seeds': ['delvetalk bell rain'], 'invitations': []}
        args = argparse.Namespace(invitation=None, seed=1, topic='t', reply_to=self.uri)
        with mock.patch.object(self.hand, 'cast', return_value={'line': 'admitted', 'intent': 'i', 'drafted': 'd'}) as cast:
            hand.cli_speak(self.hand, args)
            cast.assert_called_once_with('delvetalk bell rain', 't', self.uri, self.hand.seed_intent('delvetalk bell rain'), wait=hand.WAIT_MAX)
            cast.reset_mock()
            for seed in ('0', '2', 'NaN', ' '):
                self.assertEqual(self.send_form('speak', {'seed': seed})[0], 303)
            cast.assert_not_called()

    def test_withdrawal_requires_a_reason_even_when_the_browser_form_is_bypassed(self):
        Unpost.posted(self, 'at://did:plc:me/town.delve.feed.post/r9')
        before = list(self.host.ops)
        with mock.patch.object(post, 'unsend') as delete:
            _, _, headers = self.send_form('draft/7-aaaa', {'do': 'unpost', 'reason': ' '})
        delete.assert_not_called()
        self.assertEqual(self.host.ops, before)
        self.assertIn('reason', urllib.parse.unquote_plus(headers['Location']))

    def test_morning_day_and_welcome_spell_topic_and_reply_target_are_forwarded(self):
        with mock.patch.object(self.hand, 'morning', return_value={'drafted': 'd'}) as morning:
            self.send_form('morning', {'day': '137', 'topic': 't', 'replyTo': self.uri})
            morning.assert_called_once_with(137, 't', self.uri)
            morning.reset_mock()
            self.send_form('morning', {})
            morning.assert_called_once_with(None, None, None)
        with mock.patch.object(self.hand, 'welcome', return_value={'drafted': 'd'}) as welcome:
            self.send_form('welcome', {'spell': 'delvetalk bell rain', 'topic': 't', 'replyTo': self.uri})
            welcome.assert_called_once_with('delvetalk bell rain', 't', self.uri)

    def test_morning_and_welcome_make_real_drafts_and_never_post_them(self):
        send = self.host.send
        def reply(req):
            if req['op'] == 'world-chronicle':
                return {'status': 'chronicled', 'day': req.get('day', 137), 'lines': ['A public day.']}
            if req['op'] == 'world-render':
                return {'status': 'painted', 'text': 'The morning paint.'}
            return send(req)
        with mock.patch.object(self.host, 'send', side_effect=reply):
            self.send_form('morning', {'day': '137', 'replyTo': self.uri})
        morning = self.hand.tail(1)[0]['draft']
        self.assertEqual(self.hand.draft(morning)[1]['speak'], {'morning': 137})
        self.assertEqual(self.hand.draft(morning)[1]['replyTo'], self.uri)
        self.assertEqual(self.hand.draft(morning)[1]['text'], 'The morning paint.')
        came = {'drafted': '7-aaaa', 'line': 'admitted', 'intent': 'i'}
        with mock.patch.object(self.hand, 'cast', return_value=came):
            self.send_form('welcome', {'spell': 'delvetalk bell rain', 'replyTo': self.uri})
        d = self.hand.draft('7-aaaa')[1]
        self.assertTrue(d['welcome'])
        self.assertIn('delvetalk bell rain', d['text'])
        self.assertFalse(d['posted'])
        self.assertEqual(self.poster.calls, [])

    def test_worlds_and_invites_are_read_on_the_worlds_page_and_forms_select_the_named_world(self):
        send = self.host.send
        def reply(req):
            if req['op'] == 'serve-status':
                return {'pid': 123, 'worlds': [{'name': w, 'objects': 2, 'height': 7, 'clock': 10, 'replay': 14} for w in ('town', 'pond')]}
            return send(req)
        pond_host = StubHost()
        with mock.patch.object(self.host, 'send', side_effect=reply), mock.patch.object(self.host, 'at', return_value=pond_host) as at:
            page = self.get('/hand/')[1]
            self.assertIn('/hand/pond/', page)
            self.assertIn('Guests', page)
            self.assertEqual(self.get('/hand/pond/status')[0], 200)
            at.assert_called_once_with('pond')
            self.req('POST', '/hand/pond/root/set', {'object': 'bell', 'field': 'colour', 'value': '"silver"', 'reason': 'repair'}, f'dt_hand={TOKEN}')
            self.assertEqual(pond_host.ops[-1]['act'], {'kind': 'set', 'object': 'bell', 'field': 'colour', 'value': 'silver'})
            self.assertEqual(self.hand.hands['pond'].tail(1)[0]['world'], 'pond')
            self.assertEqual(self.get('/hand/not-held/status')[0], 404)

    def test_added_readings_and_controls_are_also_available_as_plain_text(self):
        for path in ('status', 'log', 'spend', 'modlog', 'find?query=bell', 'root/dump?object=bell', 'root/entries', 'draft?draft=7-aaaa'):
            with self.subTest(path=path):
                code, text, headers = self.get('/hand/town/' + path + ('&' if '?' in path else '?') + 'text=1')
                self.assertEqual(code, 200)
                self.assertEqual(headers['Content-Type'].split(';')[0], 'text/plain')
                self.assertNotIn('<form', text)
                self.assertIn('GET /hand/town/', text)

    def test_watch_limit_and_zulip_destination_controls_are_present_and_forwarded(self):
        with mock.patch.object(self.hand, 'watch', return_value=[]) as watch:
            self.get('/hand/town/watch?object=bell&limit=7&still=1')
            watch.assert_called_once_with('bell', 7)
        self.state.write(self.state.row, {'world': 'town', 'transport': 'zulip', 'channel': 'delvetalk'})
        page = self.get('/hand/town/speak')[1]
        self.assertIn('name="topic"', page)
        self.assertIn('/hand/town/welcome', page)

    def test_every_root_act_and_moderation_power_posts_its_typed_fields_and_reason(self):
        from transport import root
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'Bell.obend').write_text('bell source')
            values = {'object': 'bell', 'field': 'owner', 'value': '"p"', 'principal': 'p', 'method': 'rain',
                      'argument': '{"n":1}', 'intent': 'i', 'clock': '20', 'postQuota': '30', 'interpretQuota': '40',
                      'modelQuota': '50', 'turnQuota': '60', 'objectQuota': '70', 'paintQuota': '80', 'dir': directory, 'height': '7', 'text': 'paint', 'hours': '2',
                      'grant': 'g', 'scratch': 's', 'who': 'p'}
            for face, specs in (('root', root.ROOT), ('mod', {v: spec for v, (_, spec) in root.POWERS.items()} | {'settings': root.MOD_SETTINGS})):
                for verb, spec in specs.items():
                    form = {n: values[n] for n, _ in spec} | {'reason' if face == 'root' else 'reading': 'because'}
                    with self.subTest(face=face, verb=verb):
                        self.assertEqual(self.send_form(f'{face}/{verb}', form)[0], 303)
                        expected = root.request(face, verb, form, self.hand.owner, self.hand.clock)
                        got = self.host.ops[-1]
                        # Identity is clock-derived; the root request's remaining fields are exact.
                        self.assertEqual({k: v for k, v in got.items() if k != 'identity'}, {k: v for k, v in expected.items() if k != 'identity'})
            self.assertEqual(len(self.logged()), len(root.ROOT) + len(root.POWERS) + 1)

    def test_root_editor_saves_only_changed_fields_and_shows_the_complete_dump(self):
        from transport import root
        dump = {'view': {'state': {'tag': 'text', 'value': 'x' * 8000}}, 'record': {'record': {'law': []}}, 'dump': {}, 'source': {}}
        with mock.patch.object(root, 'dump', return_value=dump):
            page = self.get('/hand/town/root/?object=bell')[1]
            self.assertIn(html.escape(json.dumps(dump, indent=1, sort_keys=True)), page)
        self.send_form('root/save', {'object': 'bell', 'shown': '{"state":0,"law":[]}', 'state': '1', 'law': '[]', 'reason': 'repair'})
        self.assertEqual(self.host.ops[-1]['act'], {'kind': 'set', 'object': 'bell', 'field': 'state', 'value': 1})

    def test_malformed_and_unauthenticated_controls_never_reach_the_host_or_poster(self):
        for path, form in [('root/set', {'object': 'bell', 'field': 'state', 'value': 'broken', 'reason': 'why'}),
                           ('root/save', {'object': 'bell', 'shown': 'broken', 'reason': 'why'}),
                           ('mod/quiet', {'who': 'p', 'hours': 'NaN', 'reading': 'why'}),
                           ('morning', {'day': 'NaN'}), ('draft/7-aaaa', {'do': 'unpost', 'reason': ''})]:
            before = list(self.host.ops)
            code, _, headers = self.send_form(path, form)
            self.assertEqual(code, 303, path)
            self.assertIn('note=', headers['Location'])
            self.assertEqual(self.host.ops, before)
        for path in ('log?tail=NaN', 'watch?limit=NaN', 'root/entries?after=NaN', '?since=NaN'):
            self.assertEqual(self.get('/hand/town/' + path)[0], 400)
        self.assertEqual(self.req('GET', '/hand/town/log')[0], 404)
        self.assertEqual(self.req('POST', '/hand/town/root/set', {'reason': 'x'})[0], 404)
        self.assertEqual(self.poster.calls, [])
        self.assertEqual(self.get('/hand/town/serve')[0], 404)
        self.assertEqual(self.get('/hand/town/root/edit?height=7')[0], 404)


class PortalGuests(RouteCase):
    hosted_accounts = True

    def test_open_batch_codes_are_one_per_line_shown_once_and_revoked_by_visible_id(self):
        code, page, headers = self.req('POST', '/hand/', {'guest': 'invite', 'count': '3', 'name': '', 'note': '<tag>', 'expires': '14'}, f'dt_hand={TOKEN}')
        self.assertEqual(code, 200)
        import re
        codes = re.findall(r'dt_invite_[A-Za-z0-9_-]{32}', page)
        self.assertEqual(len(set(codes)), 3)
        self.assertIn('\n'.join(codes), page)
        self.assertNotIn('Location', headers)
        rows = self.hand.guests()
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertIn(f'id {row["id"]}', page)
            self.assertIn(f'name="name" value="{row["id"]}"', page)
        self.assertIn('&lt;tag&gt;', page)
        later = self.get('/hand/')[1]
        self.assertTrue(all(c not in later + self.state.hand_log.read_text() for c in codes))
        self.req('POST', '/hand/', {'guest': 'revoke', 'name': str(rows[0]['id'])}, f'dt_hand={TOKEN}')
        self.assertEqual(sum(r['state'] == 'revoked' for r in self.hand.guests()), 1)

    def test_batch_limit_and_named_batch_refusals_create_no_invitations(self):
        for count, name in (('0', ''), ('101', ''), ('NaN', ''), ('2', 'named')):
            code, page, _ = self.req('POST', '/hand/', {'guest': 'invite', 'count': count, 'name': name}, f'dt_hand={TOKEN}')
            self.assertEqual(code, 200)
            self.assertEqual(self.hand.guests(), [])
        code, page, _ = self.req('POST', '/hand/', {'guest': 'invite', 'count': '100'}, f'dt_hand={TOKEN}')
        self.assertEqual(code, 200)
        self.assertEqual(len(self.hand.guests()), 100)
