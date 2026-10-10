"""The hand: the owner's console at /hand/, over a real front with a stub host and a stub poster.

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

    def __call__(self, path, state, host, credentials, text=None):
        self.calls.append((Path(path).stem, text, str(credentials)))
        return {'uri': 'at://did:plc:x/town.delve.feed.post/r1', 'cid': 'bafy'}


class Hand(unittest.TestCase):
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
            'receipt': {'slug': 'bofab-lukid', 'outcome': {'tag': 'admitted'}}, 'text': 'planted <b>a</b>', 'posted': False})
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
        self.assertNotIn('<textarea', self.get()[1])
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


if __name__ == '__main__':
    unittest.main()
