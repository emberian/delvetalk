"""The owner's console at /hand/ over a real front, with a stub host and a stub poster.

Evidence for FOUNDATION §7 (layer: transport).

The hand: the owner's console at /hand/, over a real front with a stub host and a stub poster.

    python3 -W ignore -m tests.run test_hand
"""
import http.client
import json
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

from tests.test_bridge import spell_post
from transport import delve, hand, identity, observe
from transport.bridge import write_atomic
from transport.http import Front

TOKEN = 'sekret-token'


class StubHost:
    def __init__(self):
        self.ops = []

    def send(self, req):
        self.ops.append(req)
        if req['op'] == 'world-status':
            return {'status': 'status', 'height': 41, 'postQuota': 16}
        if req['op'] == 'world-interpretations':
            return {'status': 'interpretations', 'pending': [{'id': 'x'}]}
        if req['op'] == 'world-resolve':
            return {'status': 'resolved', 'slug': req['slug'], 'kind': 'receipt', 'cid': 'c'}
        return {'status': 'ok'}


class Poster:
    def __init__(self):
        self.calls = []

    def __call__(self, path, state, host, credentials, text=None, object=None):
        self.calls.append((Path(path).stem, text, str(credentials)) + ((object,) if object else ()))
        return {'uri': 'at://did:plc:x/town.delve.feed.post/r1', 'cid': 'bafy'}


class HandCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        posts = [spell_post(1, 'garden-1', '2026-10-09T10:00:01Z'), spell_post(2, 'garden-1', '2026-10-09T10:00:02Z')]
        from tests.test_transport import Script
        ob = observe.Observer(self.state, delve.Client(Script(**{'town.delve.feed.searchPosts': lambda p: (200, {'posts': posts}),
                                                                 'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})))
        ob.poll()
        ob.db.close()
        self.uri = posts[0]['uri']
        write_atomic(self.state / 'outbox' / '7-aaaa.json', {
            'replyTo': self.uri, 'replyHandle': 'talkie.delve.town', 'principal': 'p', 'object': 'garden-1', 'slot': None,
            'receipt': {'slug': 'bofab-lukid', 'height': 7, 'outcome': {'tag': 'admitted'}}, 'text': 'planted <b>a</b>', 'posted': False})
        write_atomic(self.state / 'post-log.json', [__import__('time').time()] * 3)
        self.poster, self.host = Poster(), StubHost()
        self.hand = hand.Hand(self.state, self.host, TOKEN, '/creds.json', poster=self.poster)
        self.front = Front(('127.0.0.1', 0), self.host, identity.Identity(self.tmp.name, delve.Client(None)), hand=self.hand)
        threading.Thread(target=self.front.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.front.shutdown(), self.front.server_close()))

    def req(self, method, path, form=None, cookie=''):
        c = http.client.HTTPConnection('127.0.0.1', self.front.server_address[1])
        body = urllib.parse.urlencode(form) if form is not None else None
        c.request(method, path, body, {'Cookie': cookie, 'Content-Type': 'application/x-www-form-urlencoded'})
        r = c.getresponse()
        return r.status, r.read().decode(), dict(r.getheaders())

    def get(self, path='/hand/'):
        return self.req('GET', path, cookie=f'dt_hand={TOKEN}')

    def logged(self):
        return [json.loads(l) for l in (self.state / 'hand-log.jsonl').read_text().splitlines()]


class Hand(HandCase):
    def test_without_the_token_the_page_is_404_and_a_query_token_sets_the_cookie(self):
        self.assertEqual(self.req('GET', '/hand/')[0], 404)
        self.assertEqual(self.req('GET', '/hand/?token=wrong')[0], 404)
        self.assertEqual(self.req('POST', '/hand/draft/7-aaaa', {'do': 'post'})[0], 404)
        code, _, headers = self.req('GET', '/hand/?token=' + TOKEN)
        self.assertEqual(code, 302)
        self.assertIn('dt_hand=' + TOKEN, headers['Set-Cookie'])
        self.assertEqual(self.poster.calls, [])

    def test_a_front_without_the_token_does_not_serve_it(self):
        self.front.hand = None
        self.assertEqual(self.get()[0], 404)

    def test_inbox_outbox_and_status_render_from_state(self):
        code, page, _ = self.get()
        self.assertEqual(code, 200)
        self.assertIn('talkie.delve.town', page)
        self.assertIn('garden-1 / bofab-lukid / admitted', page)
        self.assertIn('not yet turned', page)  # the second post has no draft and no verdict
        self.assertIn('planted &lt;b&gt;a&lt;/b&gt;</textarea>', page)
        self.assertIn('delvetalk garden-1 plant', page)  # the original post beside the draft
        self.assertIn('41', page)
        self.assertIn('3 of 16', page)
        self.assertIn('1 (0 retrying)', page)
        self.assertNotIn('<script src="/hand', page)

    def test_search_by_slug_asks_the_host(self):
        _, page, _ = self.get('/hand/?slug=bofab-lukid')
        self.assertIn('resolved', page)
        self.assertEqual([o for o in self.host.ops if o['op'] == 'world-resolve'][0]['slug'], 'bofab-lukid')

    def test_post_calls_the_poster_once_with_the_edited_text_and_logs_it(self):
        code, _, headers = self.req('POST', '/hand/draft/7-aaaa', {'do': 'post', 'text': 'edited words'}, f'dt_hand={TOKEN}')
        self.assertEqual(code, 303)
        self.assertEqual(self.poster.calls, [('7-aaaa', 'edited words', '/creds.json')])
        (line,) = self.logged()
        self.assertEqual((line['what'], line['who'], line['draft'], line['edited']), ('post', 'owner', '7-aaaa', True))

    def test_skip_and_hold_never_post(self):
        self.req('POST', '/hand/draft/7-aaaa', {'do': 'hold'}, f'dt_hand={TOKEN}')
        self.assertEqual(self.poster.calls, [])
        self.assertIn('planted', self.get()[1])
        self.req('POST', '/hand/draft/7-aaaa', {'do': 'skip', 'reason': 'off topic'}, f'dt_hand={TOKEN}')
        self.assertEqual(self.poster.calls, [])
        d = json.loads((self.state / 'outbox' / '7-aaaa.json').read_text())
        self.assertEqual((d['posted'], d['skipped'], d['reason']), (False, True, 'off topic'))
        self.assertNotIn('rows="8"', self.get()[1])  # no draft left to edit
        self.assertEqual([l['what'] for l in self.logged()], ['hold', 'skip'])

    def test_post_draft_is_the_post_py_path_records_and_marks_posted(self):
        from transport import post

        class Writer:
            def __init__(self): self.sent = []
            def write(self, nsid, body, token=None):
                self.sent.append((nsid, body))
                return {'did': 'did:plc:x', 'accessJwt': 't'} if 'Session' in nsid else {'uri': 'at://did:plc:x/town.delve.feed.post/r9', 'cid': 'bafy9'}
            def record(self, uri): return {'uri': uri, 'cid': 'c', 'value': {}}
            def resolve_handle(self, h): return {}
        creds = self.state / 'creds.json'
        creds.write_text('{"identifier": "a", "password": "b"}')
        w, path = Writer(), self.state / 'outbox' / '7-aaaa.json'
        got = post.post_draft(path, self.state, self.host, creds, text='final', reader=w, client=w)
        self.assertEqual(w.sent[1][1]['record']['text'], 'final')
        self.assertEqual(w.sent[1][1]['record']['reply']['parent']['uri'], self.uri)
        self.assertEqual([o['uri'] for o in self.host.ops if o['op'] == 'world-posted'], [got['uri']])
        d = json.loads(path.read_text())
        self.assertEqual((d['posted'], d['text'], d['original']), (True, 'final', 'planted <b>a</b>'))
        with self.assertRaises(delve.Failure):
            post.post_draft(path, self.state, self.host, creds, reader=w, client=w)


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
            code = hand.main([*argv, '--state', str(self.state), '--credentials', str(self.state / 'creds.json')], out, self.host, self.poster)
        return code, out.getvalue()

    def js(self, *argv, **kw):
        code, text = self.cmd(*argv, '--json', **kw)
        self.assertEqual(code, 0, text)
        return json.loads(text)

    def logged_who(self):
        return {l['who'] for l in self.logged()}

    def test_reading_verbs_print_text_and_json_that_parses(self):
        rows = self.js('inbox')
        self.assertEqual([r['kind'] for r in rows], ['spell', 'spell'])
        fates = {r['uri']: r['fate'] for r in rows}
        self.assertEqual(fates[self.uri], 'garden-1 / bofab-lukid / admitted')
        self.assertEqual(self.js('inbox', '--kind', 'summon'), [])
        self.assertEqual(len(self.js('inbox', '--since', '7')), 1)  # the drafted one is at height 7
        code, text = self.cmd('inbox')
        self.assertIn('fate: garden-1 / bofab-lukid / admitted', text)
        (g,) = self.js('outbox')
        self.assertEqual((g['post'], g['original']['handle'], g['drafts'][0]['id']), (self.uri, 'talkie.delve.town', '7-aaaa'))
        self.assertIn('planted <b>a</b>', self.cmd('outbox')[1])
        shown = self.js('show', '7-aaaa')
        self.assertEqual((shown['receipt'], shown['text'], shown['original post']['handle']), ('receipt bofab-lukid: admitted', 'planted <b>a</b>', 'talkie.delve.town'))
        st = self.js('status')
        self.assertEqual((st['journal height'], st['posts this hour'], st['hostd pid']), (41, '3 of 16', 'none'))
        self.assertEqual(self.js('search', 'bofab-lukid')['status'], 'resolved')
        self.assertEqual(self.cmd('log')[1].strip(), '(nothing)')

    def test_edit_keeps_the_original_and_post_calls_the_poster_once_as_cli(self):
        f = self.state / 'new.txt'
        f.write_text('first edit')
        self.assertEqual(self.js('edit', '7-aaaa', '--text-file', str(f)), {'edited': '7-aaaa'})
        self.js('edit', '7-aaaa', '--stdin', stdin='second edit')
        d = json.loads((self.state / 'outbox' / '7-aaaa.json').read_text())
        self.assertEqual((d['text'], d['original']), ('second edit', 'planted <b>a</b>'))
        self.js('post', '7-aaaa', '--object', 'garden-1')
        self.assertEqual(self.poster.calls, [('7-aaaa', 'second edit', str(self.state / 'creds.json'), 'garden-1')])
        self.assertEqual([l['what'] for l in self.logged()], ['edit', 'edit', 'post'])
        self.assertEqual(self.logged_who(), {'cli'})

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
        (self.state / 'outbox' / '7-aaaa.json').unlink()
        (self.state / 'skipped.txt').write_text(self.uri + '\n')
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
        creds = self.state / 'creds.json'
        creds.write_text('{"identifier": "a", "password": "b"}')
        f = self.state / 'mine.txt'
        f.write_text('a word by hand')
        name = self.js('reply', self.uri, '--text-file', str(f), '--object', 'garden-1')['drafted']
        self.assertIn('-hand-', name)
        self.poster = partial(post.post_draft, reader=w, client=w)
        code, out = self.cmd('post', name)
        self.assertEqual(code, 0, out)
        self.assertEqual((w.sent[1][1]['record']['text'], w.sent[1][1]['record']['reply']['parent']['uri']), ('a word by hand', self.uri))
        self.assertEqual([(o['object'], o['uri']) for o in self.host.ops if o['op'] == 'world-posted'], [('garden-1', 'at://did:plc:x/town.delve.feed.post/r9')])
        self.assertEqual(self.cmd('reply', 'at://nope', '--text-file', str(f), '--object', 'x')[0], 1)

    def test_the_web_face_retries_and_replies_by_hand_through_the_same_operations(self):
        other = self.uri.replace('r000001', 'r000002')
        (self.state / 'skipped.txt').write_text(other + '\n')
        self.assertIn('Retry', self.get()[1])
        self.assertIn('reply by hand', self.get()[1])
        self.req('POST', '/hand/retry', {'uri': other}, f'dt_hand={TOKEN}')
        self.assertEqual((self.state / 'skipped.txt').read_text(), '')
        self.req('POST', '/hand/reply', {'uri': other, 'text': 'hi', 'object': 'garden-1'}, f'dt_hand={TOKEN}')
        self.assertEqual([l['what'] for l in self.logged()], ['retry', 'reply'])
        self.assertEqual({l['who'] for l in self.logged()}, {'owner'})


if __name__ == '__main__':
    unittest.main()
