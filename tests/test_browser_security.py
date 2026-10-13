"""Browser credential boundaries and response custody (FOUNDATION §7), without sockets or Lean."""
import html
import io
import json
import re
import tempfile
import threading
import unittest
import urllib.parse
from unittest import mock

from transport import delve, identity
from transport.config import Config
from transport.http import COOKIE, MAX_BODY, RATE, Front, Handler
from transport.state import State

FORM = 'application/x-www-form-urlencoded'
ORIGIN = 'https://town.example'
KEY = 'dt_agent_' + 'a' * 43
JAR = COOKIE + '=' + KEY
WHO = {'did': 'guest:town.example:robin', 'handle': 'robin', 'verified': True}
ROW = {'uri': 'at://town/feed/1', 'did': WHO['did'], 'handle': 'robin', 'created': '2026-10-12T00:00:00Z',
       'text': 'hello', 'parent': None, 'root': None, 'town': False, 'receipt': None}


class BrowserSecurity(unittest.TestCase):
    def setUp(self):
        self.front = Front.__new__(Front)
        self.front.origin, self.front.hand = ORIGIN, None
        self.front.clock, self.front.sleep = lambda: 1000, lambda _: None
        self.front.hits, self.front.hits_lock = {}, threading.Lock()
        self.front.csrf_secret = b's' * 32
        self.front.nonce, self.front.play_wait, self.front.trust_proxy = 'test', 0, False
        self.front.identity = mock.Mock()
        self.front.identity.authenticate.side_effect = lambda key: WHO if key == KEY else None
        self.front.identity.accept.return_value = {'status': 'accepted', 'principal': WHO['did'],
                                                   'handle': 'robin', 'credential': KEY}
        self.front.identity.challenge.return_value = {**WHO, 'text': 'word', 'credential': KEY}
        self.front.identity.claim.return_value = {**WHO, 'status': 'verified'}
        self.front.host = mock.Mock()
        self.front.host.send.side_effect = self.host_reply
        self.front.handles, self.front.town = lambda _: {}, lambda: ''
        self.front.draft_turn = mock.Mock()
        self.front._feed = mock.Mock()
        self.front._feed.recent.return_value = 0
        self.front._feed.post.return_value = ROW
        self.front._feed.threads.return_value = ([], None)
        self.front._feed.get.return_value = None
        self.addCleanup(mock.patch.stopall)
        mock.patch('transport.http.place', return_value={'status': 'place', 'card': 'hello', 'view': {}, 'paint': None, 'wants': []}).start()
        mock.patch('transport.http.painted', return_value={}).start()

    def host_reply(self, req):
        if req['op'] in ('world-turn', 'world-try'):
            return {'status': 'admitted', 'object': req['object'], 'receipt': {
                'height': 1, 'identity': {'principal': req['principal'], 'intent': req['identity']},
                'outcome': {'tag': 'admitted'}}}
        if req['op'] == 'world-receipt':
            return {'receipt': {'outcome': {'tag': 'admitted'}}}
        if req['op'] == 'world-surface':
            return {'status': 'surface', 'text': 'private book'}
        return {}

    def request(self, method, path, data=None, headers=None, raw=None):
        h = Handler.__new__(Handler)
        h.server, h.command, h.path = self.front, method, path
        h.headers = dict(headers or {})
        if raw is None:
            raw = urllib.parse.urlencode(data or {}).encode() if h.headers.get('Content-Type') == FORM else json.dumps(data or {}).encode()
        h.headers['Content-Length'] = str(len(raw))
        h.rfile, h.wfile = io.BytesIO(raw), io.BytesIO()
        h.client_address, h.did, h.head = ('127.0.0.1', 1), None, False
        response = []
        h.send_response = lambda code: response.append(code)
        fields = []
        h.send_header = lambda key, value: fields.append((key, value))
        h.end_headers = lambda: None
        h.dispatch(method)
        return response[0], fields, h.wfile.getvalue()

    def form(self, path='/enter', jar=JAR):
        _, headers, body = self.request('GET', path, headers={'Accept': 'text/html', 'Cookie': jar})
        token = re.search(rb'name="csrf" value="([^"]+)"', body)
        cookies = dict(part.split('=', 1) for part in jar.split('; ') if part)
        for key, value in headers:
            if key == 'Set-Cookie':
                name, value = value.split(';', 1)[0].split('=', 1)
                cookies[name] = value
        return token[1].decode() if token else '', '; '.join(k + '=' + v for k, v in cookies.items())

    def post(self, path, data=None, jar=JAR, **headers):
        return self.request('POST', path, data, {'Accept': 'text/html', 'Content-Type': FORM, 'Cookie': jar, **headers})

    def test_foreign_and_missing_origins_refuse_every_browser_write_before_effects(self):
        token, jar = self.form()
        for path in ('/enter', '/leave', '/feed', '/AGENTS.md/accept', '/play/garden', '/AGENTS.md/challenge', '/AGENTS.md/verify'):
            for origin in (None, 'https://evil.example', 'https://sibling.town.example', ORIGIN + '.evil.example', 'null', ORIGIN + '/'):
                with self.subTest(path=path, origin=origin):
                    self.front.hits.clear()
                    status, _, _ = self.post(path, {'credential': KEY, 'code': 'x', 'text': 'hello', 'csrf': token}, jar,
                                              **({'Origin': origin} if origin else {}))
                    self.assertEqual(status, 403)
        self.front.identity.accept.assert_not_called()
        self.front._feed.post.assert_not_called()
        self.assertFalse(any(c.args[0]['op'] == 'world-turn' for c in self.front.host.send.call_args_list))

    def test_the_exact_origin_and_session_token_admit_each_browser_write(self):
        token, jar = self.form()
        for path, data, expected in (('/enter', {'credential': KEY}, 303), ('/leave', {}, 200),
                                      ('/feed', {'text': 'hello'}, 303), ('/AGENTS.md/accept', {'code': 'x'}, 200),
                                      ('/play/garden', {'text': '?'}, 200), ('/AGENTS.md/challenge', {'handle': 'robin'}, 200),
                                      ('/AGENTS.md/verify', {'handle': 'robin'}, 200)):
            with self.subTest(path=path):
                self.assertEqual(self.post(path, {**data, 'csrf': token}, jar, Origin=ORIGIN)[0], expected)

    def test_referer_falls_back_to_its_exact_origin_but_never_overrides_a_foreign_origin(self):
        token, jar = self.form()
        for headers, expected in (({'Referer': ORIGIN + '/enter?from=door'}, 303),
                                  ({'Referer': ORIGIN + '.evil.example/enter'}, 403),
                                  ({'Origin': 'null', 'Referer': ORIGIN + '/enter'}, 403),
                                  ({'Origin': ORIGIN, 'Sec-Fetch-Site': 'cross-site'}, 403),
                                  ({'Origin': ORIGIN, 'Sec-Fetch-Site': 'same-site'}, 303)):
            with self.subTest(headers=headers):
                self.assertEqual(self.post('/enter', {'credential': KEY, 'csrf': token}, jar, **headers)[0], expected)

    def test_anonymous_login_uses_a_browser_token_and_another_sessions_token_is_refused(self):
        token, jar = self.form(jar='')
        self.assertTrue(token)
        self.assertEqual(self.post('/enter', {'credential': KEY, 'csrf': token}, jar, Origin=ORIGIN)[0], 303)
        for bad in ('', 'x' * 64, '☃' * 64, 'x' * (MAX_BODY - 200), token):
            with self.subTest(token_length=len(bad)):
                self.assertEqual(self.post('/feed', {'text': 'hello', 'csrf': bad}, JAR, Origin=ORIGIN)[0], 403)

    def test_json_cookie_writes_require_origin_and_bearer_and_json_login_remain_usable(self):
        for origin, expected in ((None, 403), ('https://evil.example', 403), (ORIGIN, 303)):
            headers = {'Cookie': JAR, 'Content-Type': 'application/json', **({'Origin': origin} if origin else {})}
            self.assertEqual(self.request('POST', '/feed', {'text': 'hello'}, headers)[0], expected)
        self.assertEqual(self.request('POST', '/AGENTS.md/feed', {'text': 'hello'},
                         {'Authorization': 'Bearer ' + KEY, 'Origin': 'https://evil.example', 'Cookie': JAR})[0], 200)
        self.assertEqual(self.request('POST', '/enter', {'credential': KEY}, {'Accept': 'application/json'})[0], 200)

    def test_json_labeled_as_a_curl_form_keeps_the_json_api_without_browser_state(self):
        self.front.identity.challenge.return_value = {'handle': 'robin', 'text': 'word', 'credential': KEY}
        status, _, body = self.request('POST', '/AGENTS.md/challenge', headers={'Content-Type': FORM}, raw=b'{"handle":"robin"}')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['credential'], KEY)

    def test_browser_metadata_cannot_hide_cookie_installation_behind_a_json_accept_header(self):
        for path in ('/enter', '/AGENTS.md/accept', '/AGENTS.md/challenge', '/AGENTS.md/verify'):
            with self.subTest(path=path):
                self.assertEqual(self.request('POST', path, {'credential': KEY, 'code': 'x', 'name': 'robin'},
                                 {'Accept': 'application/json', 'Content-Type': 'text/plain', 'Origin': 'https://evil.example'})[0], 403)

    def test_a_valid_bearer_on_a_browser_route_uses_its_own_principal_instead_of_the_cookie(self):
        other = {'did': 'guest:town.example:wren', 'handle': 'wren'}
        self.front.identity.authenticate.side_effect = lambda key: other if key == 'bearer-key' else WHO if key == KEY else None
        self.assertEqual(self.post('/feed', {'text': 'hello'}, Authorization='Bearer bearer-key', Origin='https://evil.example')[0], 303)
        self.assertEqual(self.front._feed.post.call_args.args[0], other)

    def test_a_forged_bearer_header_never_exempts_cookie_or_installing_writes(self):
        for path, data in (('/feed', {'text': 'hello'}), ('/play/garden', {'text': '?'}), ('/enter', {'credential': KEY})):
            with self.subTest(path=path):
                status, _, _ = self.post(path, data, Authorization='Bearer forged', Origin='https://evil.example')
                self.assertIn(status, (303, 403))
        self.front._feed.post.assert_not_called()
        self.assertFalse(any(c.args[0]['op'] == 'world-turn' for c in self.front.host.send.call_args_list))

    def test_the_maximum_feed_text_passes_with_the_session_token_and_a_maximum_foreign_origin_is_refused(self):
        token, jar = self.form()
        text = '&' * 65536
        self.assertEqual(self.post('/feed', {'text': text, 'csrf': token}, jar, Origin=ORIGIN)[0], 303)
        self.front._feed.post.assert_called_once()
        self.assertEqual(self.front._feed.post.call_args.args[1], text)
        self.assertEqual(self.post('/feed', {'text': text, 'csrf': token}, jar, Origin='https://' + 'a' * 65527)[0], 403)

    def test_cookie_pages_credential_json_invitation_errors_and_cookie_redirects_are_private_and_not_stored(self):
        token, jar = self.form()
        anonymous_token, anonymous = self.form(jar='')
        self.front.identity.accept.side_effect = identity.IdentityError('invalid_guest_name')
        responses = [self.request('GET', path, headers={'Cookie': jar}) for path in
                     ('/', '/o/robin', '/o/robin/book', '/history', '/map', '/play/garden', '/feed')]
        responses += [
                     self.request('POST', '/enter', {'credential': KEY}, {'Accept': 'application/json'}),
                     self.post('/enter', {'code': 'dt_invite_' + 'a' * 32, 'name': '<bad>', 'csrf': anonymous_token}, anonymous, Origin=ORIGIN),
                     self.post('/enter', {'credential': KEY, 'csrf': token}, jar, Origin=ORIGIN)]
        for _, headers, _ in responses:
            self.assertEqual([v for k, v in headers if k.lower() == 'cache-control'], ['private, no-store'])
            self.assertNotIn('Vary', dict(headers))
        self.assertNotIn('Cache-Control', dict(self.request('GET', '/static/say.js')[1]))

    def test_json_invitation_credentials_and_browser_welcomes_are_never_stored(self):
        token, jar = self.form(jar='')
        for status, headers, body in (self.request('POST', '/enter', {'code': 'x', 'name': 'robin'}),
                                     self.post('/enter', {'code': 'x', 'name': 'robin', 'csrf': token}, jar, Origin=ORIGIN)):
            self.assertEqual(status, 200)
            self.assertIn(KEY.encode(), body)
            self.assertEqual(dict(headers)['Cache-Control'], 'private, no-store')

    def test_installing_and_clearing_a_credential_rotate_the_browser_session_token(self):
        token, jar = self.form()
        for path, data in (('/enter', {'credential': KEY}), ('/leave', {})):
            status, headers, _ = self.post(path, {**data, 'csrf': token}, jar, Origin=ORIGIN)
            self.assertIn(status, (200, 303))
            browser = next(v.split(';', 1)[0] for k, v in headers if k == 'Set-Cookie' and v.startswith('dt_browser='))
            credential = next(v.split(';', 1)[0] for k, v in headers if k == 'Set-Cookie' and v.startswith(COOKIE + '='))
            next_token, _ = self.form(jar=browser + '; ' + credential)
            self.assertNotEqual(next_token, token)

    def test_the_33rd_feed_form_post_is_limited_before_insertion_and_bad_posts_also_count(self):
        token, jar = self.form()
        for _ in range(RATE):
            self.assertEqual(self.post('/feed', {'text': 'hello', 'csrf': token}, jar, Origin=ORIGIN)[0], 303)
        self.assertEqual(self.post('/feed', {'text': 'hello', 'csrf': token}, jar, Origin=ORIGIN)[0], 429)
        self.assertEqual(self.front._feed.post.call_count, RATE)
        self.front.hits.clear()
        for _ in range(RATE):
            self.assertEqual(self.post('/feed', {'text': 'hello'}, jar, Origin='https://evil.example')[0], 403)
        self.assertEqual(self.post('/feed', {'text': 'hello', 'csrf': token}, jar, Origin=ORIGIN)[0], 429)

    def test_an_external_leave_get_confirms_and_only_a_gated_post_reports_completion(self):
        for jar in ('', JAR):
            status, _, body = self.request('GET', '/leave', headers={'Cookie': jar, 'Accept': 'text/html'})
            self.assertEqual(status, 200)
            self.assertIn(b'action="/leave"', body)
            self.assertNotIn(b'Signed out', body)
        token, jar = self.form('/leave')
        status, headers, body = self.post('/leave', {'csrf': token}, jar, Origin=ORIGIN)
        self.assertEqual(status, 200)
        self.assertIn(b'Signed out', body)
        cookie = next(v for k, v in headers if k == 'Set-Cookie' and v.startswith(COOKIE + '='))
        for flag in ('Max-Age=0', 'HttpOnly', 'SameSite=Strict', 'Secure', 'Path=/'):
            self.assertIn(flag, cookie)

    def test_the_leave_confirmation_still_works_when_the_strict_credential_returns_on_the_same_origin_post(self):
        token, jar = self.form('/leave', jar='')
        status, _, body = self.post('/leave', {'csrf': token}, jar + '; ' + JAR, Origin=ORIGIN)
        self.assertEqual(status, 200)
        self.assertIn(b'Signed out', body)

    def test_a_keyless_open_invitation_has_the_same_503_explanation_in_html_and_json_and_stays_unused(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        st = State(tmp.name, config=Config(origin=ORIGIN))
        self.front.identity = identity.Identity(st, delve.Client(mock.Mock()), clock=self.front.clock)
        self.addCleanup(self.front.identity.db.close)
        code = self.front.identity.invite(None, 'open')['code']
        token, jar = self.form(jar='')
        status, headers, body = self.post('/enter', {'code': code, 'name': 'a' * 32, 'csrf': token}, jar, Origin=ORIGIN)
        js, _, raw = self.request('POST', '/AGENTS.md/accept', {'code': code, 'name': 'a' * 32})
        self.assertEqual((status, js), (503, 503))
        self.assertIn(json.loads(raw)['message'], html.unescape(body.decode()))
        self.assertIn(code.encode(), body)
        self.assertEqual(dict(headers)['Cache-Control'], 'private, no-store')
        self.assertEqual(self.front.identity.invitations()[0]['state'], 'open')

    def test_play_submits_and_drafts_once_through_the_shared_turn_operation(self):
        token, jar = self.form()
        turn = self.front.turn
        with mock.patch.object(self.front, 'turn', wraps=turn) as shared:
            status, _, _ = self.post('/play/garden', {'text': '?' , 'csrf': token}, jar, Origin=ORIGIN)
        self.assertEqual(status, 200)
        shared.assert_called_once()
        self.front.draft_turn.assert_called_once()

    def test_play_tries_keep_the_preview_and_never_draft_while_multiple_spells_draft_each_turn_once(self):
        token, jar = self.form()
        admitted = self.host_reply({'op': 'world-turn', 'object': 'garden', 'principal': WHO['did'], 'identity': 'first'})
        second = {**admitted, 'receipt': {**admitted['receipt'], 'identity': {'principal': WHO['did'], 'intent': 'second'}}}
        for reply, drafts in (({'status': 'spells', 'turns': [admitted, second]}, 2), ({'status': 'preview', 'tried': True}, 0)):
            self.front.host.send.side_effect = lambda req: reply if req['op'] == 'world-turn' else self.host_reply(req)
            self.front.draft_turn.reset_mock()
            with mock.patch('transport.http.bridge.preview_text', return_value='preview, nothing done'):
                status, _, body = self.post('/play/garden', {'text': '?', 'try': '1', 'csrf': token}, jar, Origin=ORIGIN)
            self.assertEqual(status, 200)
            self.assertEqual(self.front.draft_turn.call_count, drafts)
            if not drafts:
                self.assertIn(b'preview, nothing done', body)


if __name__ == '__main__':
    unittest.main()
