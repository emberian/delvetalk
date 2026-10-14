"""The agent API at /AGENTS.md over a real `serve`: proof-of-control login, turns and receipts, the
REPL, scratch worlds, pages for people, limits.

Evidence for FOUNDATION §7 (layer: transport).
"""
import html
import http.client
import json
import re
import time
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from tests.wire import label, nat, record, variant
from tests.bend import closure, counter_modules, declared

PLANS = """edition ObjectiveBend 1
import ./World.obend as World
record Edit:
  field: Nat
  before: Nat
  after: Nat
def bump(count: Nat) -> Activity<Nat>:
  match world.write({field: 0n, before: count, after: count + 1n}):
    case written(_): count + 1n
    case refused(_): count
def pure(n: Nat) -> Nat:
  n + 1n
"""

REPL_COUNTER = declared('''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})):
    case _: state.count + 1n
''')
from transport import delve, identity
from tests.host import ServeCase, bounds, serve, served
from tests.keys import write_repo_key
from transport.host import HostClient
from transport.config import Config
from transport.http import CATALOGUE, AccessLog, Front, turn_view
from transport.state import State

HANDLE = 'talkie.delve.town'
DID = 'did:plc:' + 'a' * 24
URI = f'at://{DID}/town.delve.feed.post/3abc'


def bare(reply):
    """A reply without the front's controls: what the host said."""
    return {k: v for k, v in reply.items() if k not in ('_links', '_actions')} if isinstance(reply, dict) else reply


PEOPLE = {HANDLE: DID, 'glm.delve.town': 'did:plc:' + 'b' * 24, 'mimo.delve.town': 'did:plc:' + 'c' * 24,
          'selene.delve.town': 'did:plc:' + 'd' * 24}


class Provider:
    """Mocked PDS: resolves known handles, serves whatever proof text the test sets per DID."""
    def __init__(self):
        self.texts, self.hidden, self.older = {}, set(), {}

    def __call__(self, method, url, headers, body):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if 'resolveHandle' in url:
            return 200, json.dumps({'did': PEOPLE[q['handle'][0]]}).encode()
        repo = q['repo'][0]
        if 'listRecords' in url:  # the account's newest posts first: any older ones a test set, then the word if it has been posted
            if repo in self.hidden:
                return 403, b'{"error":"Forbidden"}'
            word = [{'uri': f'at://{repo}/town.delve.feed.post/3abc', 'cid': 'bafyx', 'value': {'text': self.texts[repo]}}] if repo in self.texts else []
            return 200, json.dumps({'records': word + self.older.get(repo, [])}).encode()
        return 200, json.dumps({'uri': f'at://{repo}/town.delve.feed.post/3abc', 'cid': 'bafyx',
                                'value': {'text': self.texts[repo]}}).encode()


class FrontCase(ServeCase):
    """One `serve` per class, opened by OPENER (not a person the front logs in: the opener speaks on the root socket)
    with the library sealed; each test gets its own front (identity database, rate limits, clock) and its own counter
    object. A class whose tests each need the world as genesis left it sets `fresh_world`: a `serve` per test."""
    OPENER = 'did:plc:' + 'o' * 24
    made = 0
    fresh_world = False
    hosted_accounts = False
    config = {}  # the front's config beyond its socket and key directory (an open town's door: tests/test_arrival.py)
    transport = None  # its bridge row's transport (`open --transport`): 'feed' is a town that speaks its own feed alone

    @classmethod
    def setUpClass(cls):
        if not cls.fresh_world:
            super().setUpClass()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        if self.fresh_world:
            from transport.config import LIBRARY
            self.state_dir = tempfile.TemporaryDirectory()
            self.addCleanup(self.state_dir.cleanup)
            self.server = served(self.state_dir.name, cleanup=self.addCleanup, opener=self.OPENER, library=LIBRARY)
            self.socket, self.root = self.server.sock, HostClient(self.server.root)
        self.provider = Provider()
        self.now = [1000.0]
        self.host = HostClient(self.socket)  # a test may replace its send
        st = State(self.tmp.name, config=Config(host_socket=self.socket, hosted_accounts=self.hosted_accounts, repo_keys=str(Path(self.tmp.name) / 'repo'), **self.config))
        if self.hosted_accounts:
            write_repo_key(st)
        if self.transport:
            st.write(st.row, {'world': st.world, 'transport': self.transport, 'realm': None, 'channel': None, 'zuliprc': None})
        ident = identity.Identity(st, delve.Client(self.provider), clock=lambda: self.now[0])
        self.outbox = st.outbox  # the hand's: an HTTP turn that writes a public object drafts here
        self.front = serve(Front(st, self.host, ident, ('127.0.0.1', 0), clock=lambda: self.now[0]))
        self.addCleanup(self.front.server_close)
        self.addCleanup(self.front.shutdown)
        self.port = self.front.server_address[1]
        type(self).made += 1
        self.c = 'c%d' % self.made
        r = self.host.send({'op': 'world-create', 'principal': HANDLE, 'identity': 'mk-' + self.c, 'object': self.c,
                            'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
        self.assertEqual(r['status'], 'created', r)

    def scratch_open(self, tok, name='try', **more):
        return self.call('POST', '/AGENTS.md/scratch', {'name': name, **more}, tok)

    def scratch_create(self, tok, name='h1', scratch='try'):
        # A bare counter: Counter's closure with Card and Spell (about 67 KB) exceeds the front's 64 KiB body.
        self.scratch_open(tok, scratch)  # already open is an error the create below does not need
        return self.call('POST', f'/AGENTS.md/scratch/{scratch}/objects', {'object': name, 'modules': closure('World') + [{'name': 'Counter', 'source': REPL_COUNTER}], 'entry': 'initial',
                                                             'seed': {'count': 0}, 'intent': 'mk-' + name}, tok)

    def request(self, method, path, body=None, token=None, raw=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        headers = dict(headers or {})
        if token:
            headers['Authorization'] = 'Bearer ' + token
        payload = raw if raw is not None else (json.dumps(body) if body is not None else None)
        if method == 'POST' and headers.get('Content-Type') == 'application/x-www-form-urlencoded' and not (payload or '').lstrip().startswith('{'):
            _, fields, page = self.request('GET', '/enter', headers={'Accept': 'text/html', 'Cookie': headers.get('Cookie', '')})
            csrf = re.search(rb'name="csrf" value="([^"]+)"', page)[1].decode()
            cookies = dict(part.strip().split('=', 1) for part in headers.get('Cookie', '').split(';') if '=' in part)
            for name, value in fields:
                if name == 'Set-Cookie':
                    key, value = value.split(';', 1)[0].split('=', 1)
                    cookies[key] = value
            headers['Cookie'] = '; '.join(key + '=' + value for key, value in cookies.items())
            headers.setdefault('Origin', self.front.origin)
            payload = (payload + '&' if payload else '') + urllib.parse.urlencode({'csrf': csrf})
        c.request(method, path, payload, headers)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, r.getheaders(), data

    def call(self, method, path, body=None, token=None, raw=None):
        status, _, data = self.request(method, path, body, token, raw)
        try:
            return status, json.loads(data)
        except ValueError:
            return status, data.decode()

    def login(self, handle=HANDLE):
        did = PEOPLE[handle]
        s, ch = self.call('POST', '/AGENTS.md/challenge', {'handle': handle})
        self.assertEqual(s, 200, ch)
        self.provider.texts[did] = ch['text']
        s, v = self.call('POST', '/AGENTS.md/verify', {'handle': handle, 'uri': f'at://{did}/town.delve.feed.post/3abc'}, ch['credential'])
        self.assertEqual((s, v['status']), (200, 'verified'), v)
        return ch['credential']

    def turn(self, tok, intent):
        return self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': record(), 'intent': intent}, tok)


class Intents(FrontCase):
    def test_a_refusal_says_its_intent_is_spent_and_the_same_request_again_says_it_was_answered(self):
        """Kestrel (obend 10-14): a refused receive spent its intent, and the corrected spell sent again under it got an
        answer that looked like a fresh refusal. The front's JSON carries the host's `spent` and `replayed`."""
        tok = self.login()
        s, r = self.call('POST', f'/AGENTS.md/world/{self.c}/nosuchmethod', {'argument': record(), 'intent': 'spend-1'}, tok)
        self.assertEqual((s, r['status'], r['class']), (200, 'refused', 'noMethod'), r)
        self.assertEqual(r['spent'], 'intent spend-1 is spent on this refusal: send the corrected spell under a new intent')
        s, again = self.call('POST', f'/AGENTS.md/world/{self.c}/nosuchmethod', {'argument': record(), 'intent': 'spend-1'}, tok)
        self.assertEqual(again['receipt'], r['receipt'])
        self.assertTrue(again['replayed'].startswith('already answered at entry %d:' % r['receipt']['height']), again)
        s, ok = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': record(), 'intent': 'spend-2'}, tok)
        self.assertEqual(ok['status'], 'admitted', ok)
        self.assertFalse({'spent', 'replayed'} & set(ok), ok)


class Arrival(FrontCase):
    def test_json_sent_as_curl_sends_it_is_json(self):
        s, _, data = self.request('POST', '/AGENTS.md/challenge', raw=json.dumps({'handle': HANDLE}),
                                  headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(s, 200, data)
        self.assertEqual(json.loads(data)['did'], DID)


    def test_unverified_credential_is_401(self):
        s, ch = self.call('POST', '/AGENTS.md/challenge', {'handle': HANDLE})
        for tok in (ch['credential'], 'dt_agent_' + 'A' * 43, None):
            self.assertEqual(self.call('GET', f'/AGENTS.md/world/{self.c}', token=tok)[0], 401)

    def test_the_33rd_request_in_a_minute_is_429_and_the_window_reopens_after_61_seconds(self):
        tok = self.login()
        codes = [self.call('GET', '/AGENTS.md/pending', token=tok)[0] for _ in range(33)]
        self.assertEqual(codes, [200] * 32 + [429])
        self.now[0] += 61
        self.assertEqual(self.call('GET', '/AGENTS.md/pending', token=tok)[0], 200)

    def test_a_body_over_256_kib_is_413_and_malformed_json_is_400(self):
        tok = self.login()
        s, e = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', token=tok, raw=b'{"intent":"' + b'x' * 300000 + b'"}')
        self.assertEqual(s, 413)
        s, e = self.call('POST', '/AGENTS.md/challenge', raw=b'{"handle":"' + b'x' * (65 * 1024) + b'"}')
        self.assertEqual((s, e['class']), (413, 'bodyTooLarge'))  # unauthenticated: still 64 KiB
        self.assertEqual(self.call('POST', f'/AGENTS.md/world/{self.c}/bump', token=tok, raw=b'{nope')[0], 400)

    def test_unauthenticated_routes_are_limited_per_client_ip(self):
        codes = [self.call('POST', '/AGENTS.md/challenge', {'handle': 'glm.delve.town'})[0] for _ in range(17)]
        self.assertEqual([c == 429 for c in codes], [False] * 16 + [True])  # per-handle limits may answer 400 first
        s, body = self.call('POST', '/AGENTS.md/verify', {'handle': HANDLE, 'uri': URI})
        self.assertEqual((s, body['status']), (429, 'error'))
        # X-Forwarded-For is ignored without --trust-proxy, honoured (last entry) with it
        self.assertEqual(self.request('POST', '/AGENTS.md/challenge', {'handle': HANDLE}, headers={'X-Forwarded-For': '9.9.9.9'})[0], 429)
        self.assertNotIn('ip:9.9.9.9', self.front.hits)
        self.front.trust_proxy = True
        self.assertNotEqual(self.request('POST', '/AGENTS.md/challenge', {'handle': HANDLE}, headers={'X-Forwarded-For': '1.1.1.1, 9.9.9.9'})[0], 429)  # keyed on 9.9.9.9, unspent
        self.assertEqual(self.front.hits.get('ip:9.9.9.9') and len(self.front.hits['ip:9.9.9.9']), 1)
        self.now[0] += 61
        self.assertNotEqual(self.call('POST', '/AGENTS.md/challenge', {'handle': HANDLE})[0], 429)

    def test_anonymous_pages_are_limited_per_address_before_any_host_request(self):
        real, asked = self.host.send, []
        self.host.send = lambda req: asked.append(req['op']) or real(req)
        codes = [self.request('GET', p)[0] for p in [f'/o/{self.c}'] * 20 + ['/'] * 13]
        self.assertEqual(codes, [200] * 32 + [429])
        before = len(asked)
        self.assertEqual(self.request('GET', f'/o/{self.c}')[0], 429)
        self.assertEqual(len(asked), before, 'a limited page asks the host nothing')
        self.now[0] += 61
        self.assertEqual(self.request('GET', f'/o/{self.c}')[0], 200)

    def test_me_reports_principal_and_rate_limit_and_revoke_ends_the_credential(self):
        tok = self.login()
        self.scratch_create(tok)
        s, me = self.call('GET', '/AGENTS.md/me', token=tok)
        self.assertEqual((s, me['principal'], me['handle'], me['did'], [r['world'] for r in me['scratches']]), (200, DID, HANDLE, DID, ['scratch/try']), me)
        self.assertEqual(me['verified'], 1000.0)
        self.assertEqual(me['rateLimit'], {'limit': 32, 'windowSeconds': 60, 'remaining': 29})
        does = next(e['does'] for e in CATALOGUE if e['name'] == 'me')
        self.assertEqual([k for k in bare(me) if f'`{k}`' not in does and k != 'status'], [])  # the catalogue names what /me answers
        self.assertEqual(bare(self.call('POST', '/AGENTS.md/revoke', {}, tok)[1]), {'status': 'revoked'})
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=tok)[0], 401)


class Claim(FrontCase):
    """Claiming a handle in a browser: the word, then one button."""
    def word_page(self):
        s, headers, page = self.request('POST', '/AGENTS.md/challenge', raw='handle=' + HANDLE, headers={'Content-Type': FORM, 'Accept': 'text/html'})
        self.assertEqual(s, 200)
        return next(v for k, v in headers if k == 'Set-Cookie' and v.startswith('dt_credential=')).split(';')[0], page.decode()

    def press(self, cookie):
        return self.request('POST', '/AGENTS.md/verify', raw='handle=' + HANDLE, headers={'Content-Type': FORM, 'Cookie': cookie, 'Accept': 'text/html'})


    def test_pressing_before_posting_says_so_and_pressing_after_logs_the_browser_in(self):
        cookie, _ = self.word_page()
        s, _, page = self.press(cookie)
        self.assertEqual(s, 200)
        self.assertIn(f'No post with that word from {HANDLE} yet. Post it, then press I posted it.', html.unescape(page.decode()))
        self.assertIn('I posted it', page.decode())  # the word and the button are still there
        self.provider.older[PEOPLE[HANDLE]] = [{'uri': f'at://{PEOPLE[HANDLE]}/town.delve.feed.post/2old', 'cid': 'bafyo', 'value': {'text': 'good morning'}}]
        self.provider.texts[PEOPLE[HANDLE]] = self.front.identity.pending(HANDLE)['text']
        s, headers, page = self.press(cookie)
        self.assertEqual(s, 200)
        self.assertIn(b'Claimed', page)
        self.assertIn(f'{HANDLE}: this browser is you'.encode(), page)
        self.assertNotIn(b'did:plc', page)
        self.assertIn(b'Enter the commonplace', self.request('GET', '/', headers={'Cookie': cookie, 'Accept': 'text/html'})[2])  # logged in
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=cookie.split('=', 1)[1])[1]['handle'], HANDLE)

    def test_someone_elses_newer_challenge_neither_shows_its_word_nor_displaces_mine(self):
        cookie, _ = self.word_page()
        word = self.front.identity.pending(HANDLE)['text']
        self.now[0] += 1
        theirs = self.call('POST', '/AGENTS.md/challenge', {'handle': HANDLE})[1]
        self.assertIn(f'<pre class="card">{word}</pre>', self.press(cookie)[2].decode())  # my word again, not theirs
        self.provider.texts[PEOPLE[HANDLE]] = word
        self.assertIn(b'Claimed', self.press(cookie)[2])
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=theirs['credential'])[0], 401)


class Access(FrontCase):
    def test_one_line_per_request_with_the_principal_and_never_a_token_or_a_body(self):
        log = Path(self.tmp.name) / 'access.log'
        self.front.access = AccessLog(log, 'town')
        self.request('GET', '/AGENTS.md/api')
        tok = self.login()
        self.call('GET', '/AGENTS.md/me?x=secret-query', token=tok)
        s, _ = self.call('GET', '/AGENTS.md/world/nowhere', token=tok)
        for _ in range(100):  # the line is written after the reply has gone out
            lines = [l.split() for l in log.read_text().splitlines()]
            if len(lines) >= 5:
                break
            time.sleep(0.02)
        api = [l for l in lines if l[2] == '/AGENTS.md/api']  # a line is written after its reply, so two requests may swap
        self.assertEqual([(l[1], l[3], l[5]) for l in api], [('GET', '200', '-')])
        me = [l for l in lines if l[2] == '/AGENTS.md/me'][0]
        self.assertEqual((me[3], me[5], me[6]), ('200', DID, 'town'))  # the world after the DID (docs/FEDERATION.md section 5)
        self.assertGreater(int(me[4]), 50)
        self.assertEqual([l[3] for l in lines if l[2] == '/AGENTS.md/world/nowhere'], [str(s)])
        text = log.read_text()
        self.assertNotIn(tok, text)
        self.assertNotIn('secret-query', text)
        self.assertNotIn('Bearer', text)
        self.assertEqual(len(lines), 2 + 2 + 1, lines)  # api, challenge, verify, me, nowhere

    def test_an_unhandled_error_is_a_500_and_one_stderr_line_naming_the_class_and_never_its_value(self):
        """Refuted by no stderr line, a traceback or the exception's message in it, or a 500 access line without `class=internal`."""
        import contextlib
        import io
        from transport.http import Handler
        log = Path(self.tmp.name) / 'access.log'
        self.front.access = AccessLog(log, 'town')
        err = io.StringIO()
        with mock.patch.object(Handler, 'route', side_effect=KeyError('secret-value')), contextlib.redirect_stderr(err):
            s, body = self.call('GET', '/AGENTS.md/api?x=secret-query')
            for _ in range(100):
                if log.exists() and log.read_text():
                    break
                time.sleep(0.02)
        self.assertEqual((s, body['class']), (500, 'internal'))
        lines = err.getvalue().splitlines()
        self.assertEqual(len(lines), 1, lines)
        self.assertRegex(lines[0], r'^front: 500 GET /AGENTS\.md/api KeyError \S+:\d+$')
        self.assertNotIn('secret', lines[0])
        self.assertTrue(log.read_text().split()[7:] == ['class=internal'], log.read_text())

    def test_the_compose_healthcheck_reads_the_home_pages_entry_and_refuses_entry_none(self):
        from transport import watch
        st = State(self.tmp.name, config=Config(host_socket=self.socket, http_port=self.port))
        self.assertTrue(watch.healthy(st, 'http'))  # the deploy of 5db9aa79: a redesigned home page left it red while serving
        real = self.host.send
        self.host.send = lambda req: {'status': 'refused'} if req.get('op') == 'world-status' else real(req)
        self.assertFalse(watch.healthy(st, 'http'))  # a refused world-open: the page shows `entry None`


class Guests(FrontCase):
    """An invitation accepted (POST /AGENTS.md/accept): the operator's code is the guest's credential once, and from then the
    guest is anyone to the host: it arrives (its avatar, its handle), its turns are judged as anyone's, and nothing is
    drafted for posting on its behalf. Refuted by a code that works twice, lapsed or revoked, a guest the host does not
    know by its handle, or a guest's turn in the hand's outbox."""
    hosted_accounts = True

    def invited(self, name=None, days=7):
        name = name or 'guest-' + self.c
        return name, 'guest:gsb.fg-goose.online:' + name, self.front.identity.invite(name, 'a test', days)['code']

    def accept(self, code):
        return self.call('POST', '/AGENTS.md/accept', {'code': code})

    def test_a_code_accepted_once_is_a_guest_who_arrives_and_turns_as_anyone_with_nothing_drafted(self):
        name, principal, code = self.invited()
        s, headers, raw = self.request('POST', '/AGENTS.md/accept', {'code': code})
        got = json.loads(raw)
        self.assertEqual((s, got['status'], got['principal'], got['handle']), (200, 'accepted', principal, name), got)
        tok = got['credential']
        self.assertIn(f'dt_credential={tok}', dict(headers)['Set-Cookie'])  # a browser holding it plays as the guest
        s, me = self.call('GET', '/AGENTS.md/me', token=tok)
        self.assertEqual((s, me['principal'], me['handle']), (200, principal, name))
        from transport.host import plain
        avatar = self.host.send({'op': 'world-view', 'principal': principal, 'object': principal})
        self.assertEqual((avatar['status'], plain(avatar['state'])['handle']), ('viewed', name), avatar)  # arrived, by its handle
        s, t = self.turn(tok, 'g-1')
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        r = self.host.send({'op': 'world-receipt', 'principal': principal, 'identity': 'g-1'})
        self.assertEqual(r['receipt']['identity']['principal'], principal)
        s, _, page = self.request('GET', f'/play/{self.c}', headers={'Cookie': f'dt_credential={tok}'})
        self.assertIn(name, page.decode())  # the play page knows the guest by its name
        self.assertEqual(list(self.outbox.glob('*.json')) if self.outbox.exists() else [], [])  # admitted public writes, drafted for nobody
        r = self.host.send({'op': 'world-create', 'principal': DID, 'identity': 'mk-g-' + self.c, 'object': 'g-' + self.c, 'modules': counter_modules(),
                            'entry': 'initial', 'seed': record(count=nat(0)), 'law': f'law maker "only its maker counts": request.subject == "{DID}"'})
        self.assertEqual(r['status'], 'created', r)
        s, t = self.call('POST', f'/AGENTS.md/world/g-{self.c}/bump', {'argument': record(), 'intent': 'g-2'}, tok)
        self.assertEqual((t['status'], t['class'], t['line']), ('refused', 'lawRefused', '§ refused maker: only its maker counts'), t)  # the law, as for anyone
        s, e = self.accept(code)
        self.assertEqual((s, e['class'], e['reason']), (400, 'identity', 'invitation_spent'), e)

    def test_a_code_lapsed_revoked_or_unknown_is_refused_by_name_and_revoking_ends_the_credential(self):
        _, _, code = self.invited('lapsed-' + self.c, days=1)
        self.now[0] += 86400
        self.assertEqual(self.accept(code)[1]['reason'], 'invitation_expired')
        name, _, code = self.invited('revoked-' + self.c)
        self.front.identity.revoke_invitation(name)
        self.assertEqual(self.accept(code)[1]['reason'], 'invitation_revoked')
        for wrong in ('dt_invite_' + 'x' * 32, 'nonsense', ''):
            s, e = self.accept(wrong)
            self.assertEqual((s, e['class'], e['reason']), (400, 'identity', 'invitation_unknown'))
        name, _, code = self.invited()
        tok = self.accept(code)[1]['credential']
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=tok)[0], 200)
        self.front.identity.revoke_invitation(name)
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=tok)[0], 401)
        entry = next(e for e in CATALOGUE if e['name'] == 'accept')
        self.assertEqual(set(entry['reasons']), {'invitation_unknown', 'invitation_spent', 'invitation_expired', 'invitation_revoked',
                                                 'name_required', 'invalid_guest_name', 'name_fixed', 'taken'})
        self.assertIn('name', entry['body'])

    def open_code(self):
        return self.front.identity.invite(None, 'open', 7)['code']

    def test_an_open_code_takes_the_name_the_guest_registers_and_the_guest_speaks_as_it(self):
        name = 'reg-' + self.c
        s, got = self.accept2(self.open_code(), name)
        self.assertEqual((s, got['status'], got['handle'], got['principal']), (200, 'accepted', name, 'guest:gsb.fg-goose.online:' + name), got)
        s, me = self.call('GET', '/AGENTS.md/me', token=got['credential'])
        self.assertEqual((s, me['principal'], me['handle']), (200, got['principal'], name))
        (row,) = [r for r in self.front.identity.invitations() if r['name'] == name]
        self.assertEqual(row['state'], 'accepted')

    def accept2(self, code, name):
        return self.call('POST', '/AGENTS.md/accept', {'code': code, 'name': name})

    def test_a_taken_name_is_refused_by_name_and_the_open_code_stays_usable_for_another(self):
        taken, _, _ = self.invited('held-' + self.c)  # a named invitation, unaccepted, holds its name
        code = self.open_code()
        s, e = self.accept2(code, taken)
        self.assertEqual((s, e['class'], e['reason']), (400, 'identity', 'taken'), e)
        other = self.accept2(self.open_code(), 'free-' + self.c)[1]
        self.assertEqual(other['status'], 'accepted')
        self.assertEqual(self.accept2(code, 'free-' + self.c)[1]['reason'], 'taken')  # by an accepted guest too
        s, got = self.accept2(code, 'later-' + self.c)
        self.assertEqual((s, got['handle']), (200, 'later-' + self.c), got)

    def test_a_bad_missing_or_mismatched_name_is_refused_and_the_code_stays_unused(self):
        code = self.open_code()
        for bad in ('Not A Name', '1abc', 'x' * 33, 'a.b', 7):
            self.assertEqual(self.accept2(code, bad)[1]['reason'], 'invalid_guest_name', bad)
        self.assertEqual(self.call('POST', '/AGENTS.md/accept', {'code': code})[1]['reason'], 'name_required')
        self.assertEqual(self.accept2(code, 'ok-' + self.c)[0], 200)
        name, _, named = self.invited()
        s, e = self.accept2(named, 'someone-else')
        self.assertEqual((s, e['reason']), (400, 'name_fixed'), e)
        self.assertEqual(self.accept2(named, name)[1]['handle'], name)  # its own name is fine

    def test_a_named_code_still_accepts_with_the_code_alone(self):
        name, principal, code = self.invited()
        self.assertEqual(self.accept(code)[1]['principal'], principal)


class Bearer(FrontCase):
    def test_html_and_text_reads_keep_the_bearer_principal_whatever_cookie_comes_with_them(self):
        tok, other = self.login(), self.login('glm.delve.town')
        real, seen = self.host.send, []
        self.host.send = lambda req: (seen.append(req.get('principal')) if req['op'] == 'world-view' else None) or real(req)
        for path, headers in ((f'/AGENTS.md/world/{self.c}', {'Accept': 'text/html'}), (f'/AGENTS.md/world/{self.c}?text=1', {}),
                              (f'/AGENTS.md/world/{self.c}', {'Accept': 'text/html', 'Cookie': f'dt_credential={other}'})):
            seen.clear()
            s, _, page = self.request('GET', path, token=tok, headers=headers)
            self.assertEqual((s, set(seen)), (200, {DID}), (path, headers))
            self.assertIn(HANDLE, page.decode())


class HttpDrafts(FrontCase):
    """The owner's rule (cracks R6, Q4): a turn made over HTTP that admits a write on a public object gets a draft in
    the hand, as a town reply does, so the operator chooses whether the town hears of it. Nothing is posted."""

    def drafts(self):
        return [json.loads(p.read_text()) for p in sorted(self.outbox.glob('*.json'))] if self.outbox.exists() else []

    def test_an_admitted_write_on_a_public_object_is_drafted_once_with_its_receipt(self):
        tok = self.login()
        s, t = self.turn(tok, 'pub-1')
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        (d,) = self.drafts()
        self.assertEqual((d['object'], d['principal'], d['posted'], d['replyTo'], d['http']), (self.c, DID, False, None, {'intent': 'pub-1'}))
        self.assertEqual(d['receipt']['slug'], t['receipt']['slug'])
        self.assertIn(f"admitted {self.c} v1, entry {t['receipt']['height']}, receipt {t['receipt']['slug']}", d['text'])
        self.assertEqual(t['line'], f"● admitted {self.c} v1, entry {t['receipt']['height']}, receipt {t['receipt']['slug']}")  # one line everywhere
        self.assertEqual(self.turn(tok, 'pub-1')[1]['receipt']['slug'], t['receipt']['slug'])  # the same intent again: the same receipt,
        self.assertEqual(len(self.drafts()), 1)  # and no second draft

    def test_a_private_object_a_refusal_and_a_scratch_turn_draft_nothing(self):
        tok = self.login()
        r = self.host.send({'op': 'world-create', 'principal': DID, 'identity': 'mk-p-' + self.c, 'object': 'p-' + self.c, 'modules': counter_modules(),
                            'entry': 'initial', 'seed': record(count=nat(0)), 'read': {'principals': [DID]}})
        self.assertEqual(r['status'], 'created', r)
        s, t = self.call('POST', f'/AGENTS.md/world/p-{self.c}/bump', {'argument': record(), 'intent': 'priv-1'}, tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        s, e = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': 7, 'intent': 'bad-1'}, tok)
        self.assertEqual(s, 400, e)
        self.assertEqual(self.scratch_create(tok)[1]['status'], 'created')
        s, t = self.call('POST', '/AGENTS.md/scratch/try/world/h1/bump', {'argument': record(), 'intent': 'scratch-1'}, tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        self.assertEqual(self.drafts(), [])


class Turns(FrontCase):
    def test_a_logged_in_agent_views_takes_a_turn_reads_its_receipt_and_sees_the_new_version(self):
        tok = self.login()
        s, v = self.call('GET', f'/AGENTS.md/world/{self.c}', token=tok)
        self.assertEqual((s, v['status'], v['version']), (200, 'viewed', 0))
        s, t = self.turn(tok, 'i1')
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        s, r = self.call('GET', '/AGENTS.md/receipt?intent=i1', token=tok)
        self.assertEqual(s, 200)
        self.assertEqual(r['receipt']['slug'], t['receipt']['slug'])
        self.assertEqual(r['receipt']['height'], t['receipt']['height'])
        self.assertEqual(self.call('GET', f'/AGENTS.md/world/{self.c}', token=tok)[1]['version'], 1)
        self.assertEqual(self.call('GET', '/AGENTS.md/pending', token=tok)[0], 200)
        self.assertEqual(self.call('POST', '/AGENTS.md/deliver', {}, tok)[0], 200)


    def test_host_refusal_passes_through_verbatim(self):
        tok = self.login()
        s, v = self.call('GET', '/AGENTS.md/world/nope', token=tok)
        self.assertEqual((s, v['status'], v['class'], v['object']), (404, 'refused', 'unknown', 'nope'))
        s, e = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': 7, 'intent': 'bad'}, tok)
        self.assertEqual(s, 400)
        self.assertEqual({k: v for k, v in bare(e).items() if k != 'class'}, self.host.send({'op': 'world-turn', 'principal': HANDLE, 'object': self.c,
                                            'method': 'bump', 'argument': 7, 'identity': 'bad'}))

    def test_principal_cannot_be_forged_through_the_body(self):
        tok = self.login()
        s, t = self.call('POST', f'/AGENTS.md/world/{self.c}/bump',
                         {'argument': record(), 'intent': 'f1', 'principal': 'ember', 'identity': 'x'}, tok)
        self.assertEqual(t['status'], 'admitted', t)
        self.assertEqual(self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': 'f1'})['status'], 'receipt')
        self.assertNotEqual(self.host.send({'op': 'world-receipt', 'principal': 'ember', 'identity': 'f1'}).get('status'), 'receipt')
        self.assertNotEqual(self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': 'x'}).get('status'), 'receipt')

    def test_a_slug_and_an_intent_are_two_routes_so_an_intent_spelled_like_an_old_slug_finds_its_own_turn(self):
        tok = self.login()
        older = self.turn(tok, 'sl1')[1]['receipt']['slug']
        mine = self.turn(tok, older)[1]['receipt']  # a new turn whose intent is the older receipt's spoken name
        by_slug = self.call('GET', f'/AGENTS.md/receipt/{older}', token=tok)[1]['receipt']
        by_intent = self.call('GET', f'/AGENTS.md/receipt?intent={older}', token=tok)[1]['receipt']
        self.assertEqual((by_slug['slug'], by_intent['slug']), (older, mine['slug']))
        self.assertEqual(self.call('GET', '/AGENTS.md/receipt?intent=sl1', token=tok)[1]['receipt']['slug'], older)
        s, e = self.call('GET', '/AGENTS.md/receipt/sl1', token=tok)  # a path names a slug, never an intent
        self.assertEqual((s, e['class'], e['_links']['hint']['href']), (404, 'unknown', '/AGENTS.md/receipt?intent=sl1'))


class TurnView(unittest.TestCase):
    def test_suspended_guidance_uses_the_receipts_intent_and_the_route_base(self):
        reply = {'status': 'suspended', 'waiting': {'behind': 2},
                 'receipt': {'height': 9, 'identity': {'intent': 'rain /?&☃'}, 'outcome': {'tag': 'suspended'}}}
        for base in ('/AGENTS.md', '/AGENTS.md/scratch/bell'):
            view = turn_view(reply, base=base)
            self.assertEqual(view['later'], 'hob is reading this; the outcome will reach your inbox (your avatar\'s notes), '
                             'or GET ' + base + '/receipt?intent=rain%20%2F%3F%26%E2%98%83')
            self.assertEqual(view['waiting'], reply['waiting'])
        self.assertEqual(turn_view({**reply, 'receipt': {'height': 9}})['later'],
                         "hob is reading this; the outcome will reach your inbox (your avatar's notes), or GET /AGENTS.md/receipt?intent=<intent>")

    def test_a_carried_receipt_route_answers_the_host_pointer_without_requiring_an_entry(self):
        from unittest.mock import Mock
        from transport.http import Handler
        found = {'status': 'resolved', 'kind': 'receipt', 'slug': 'nosap-hodaz', 'cid': 'old',
                 'carried': {'at': 1400, 'height': 1336, 'world': 'town'},
                 'message': 'entry 1336 of the world before the carry (town)'}
        handler = Handler.__new__(Handler)
        handler.path, handler.headers = '/AGENTS.md/receipt/nosap-hodaz', {'Authorization': 'Bearer legacy'}
        handler.server = Mock()
        handler.server.limited.return_value = 0
        handler.server.host.send.return_value = found
        handler.principal = Mock(return_value={'did': DID})
        handler.browser = Mock(return_value=False)
        handler.answer = Mock()
        handler.agents('receipt', None, found['slug'], None)
        handler.answer.assert_called_once_with(found)
        handler.server.host.send.assert_called_once_with({'op': 'world-resolve', 'principal': DID, 'slug': found['slug']})

    def test_the_default_view_says_what_the_act_fired_and_opened(self):
        """The host's `revealed` lines are the default view's, not only `?full=1`'s; a reply without them has none."""
        reply = {'status': 'admitted', 'revealed': ['garden/bell/1 now wants second: delvetalk garden/bell/1 rain'],
                 'receipt': {'slug': 'a-b-c', 'height': 9, 'outcome': {'tag': 'admitted', 'writes': [{'object': 'garden/bell/1', 'version': 2}]}}}
        view = turn_view(reply)
        self.assertEqual(view['revealed'], reply['revealed'])
        self.assertEqual(list(view), ['status', 'line', 'revealed', 'offers', 'receipt'])
        self.assertNotIn('revealed', turn_view({**reply, 'revealed': []}))


class ProcedureRetries(unittest.TestCase):
    def setUp(self):
        from transport.http import Handler
        from transport import bridge
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.front = Front.__new__(Front)
        self.front.st = State(tmp.name, config=Config())
        self.front.bounds = {'transientClasses': ['quota', 'quiet', 'newHostTransient']}
        self.front.host = mock.Mock()
        self.front.turn_lock = threading.Lock()
        self.front.draft_turn = mock.Mock()
        self.intent = 'é' * 128
        self.source = bridge.xrpc_source(DID, self.intent)
        self.path = bridge.answer_path(self.front.st, self.source)
        self.handler = Handler.__new__(Handler)
        self.handler.server = self.front
        self.handler.body = mock.Mock(return_value={'intent': self.intent, 'call': {'object': 'bell', 'verb': 'rain', 'fields': {}}})
        self.handler.reply = mock.Mock()

    def receipt(self, tag, height=1, **outcome):
        return {'status': tag, 'inPublic': True, 'receipt': {'hash': f'entry-{height}', 'slug': f'name-{height}',
                'height': height, 'identity': {'principal': DID, 'intent': self.intent},
                'roots': [{'object': 'bell', 'version': height}], 'outcome': {'tag': tag, **outcome}}}

    def procedure(self):
        self.handler.procedure('act', DID)
        code, raw = self.handler.reply.call_args.args
        self.assertEqual(code, 200)
        return json.loads(raw)

    def test_each_host_marked_transient_refusal_retries_at_the_maximum_intent_despite_a_saved_terminal_answer(self):
        from transport import bridge
        for cls in self.front.bounds['transientClasses']:
            with self.subTest(cls=cls):
                self.front.st.write(self.path, {'source': self.source, 'receipt': {'entry': {'$link': 'unrelated-terminal'}}})
                refused = self.receipt('refused', **{'class': cls})
                admitted = self.receipt('admitted', 2)
                self.front.host.send.reset_mock()
                self.front.host.send.side_effect = [refused, admitted]
                view = self.procedure()
                self.assertEqual(view['outcome']['status'], 'admitted')
                self.assertEqual([c.args[0]['op'] for c in self.front.host.send.call_args_list], ['world-receipt', 'world-turn'])
                self.assertEqual(json.loads(self.path.read_text())['receipt'], bridge.public_view(self.front.host, admitted)['receipt'])

    def test_a_settled_identity_replaces_a_suspended_answer_and_excludes_another_intents_offer(self):
        from transport import bridge
        bridge.write_answer(self.front.st, self.source, bridge.public_view(self.front.host, self.receipt('suspended')))
        settled = self.receipt('admitted', 3)
        self.front.host.send.side_effect = [settled, {'status': 'offers', 'offers': [
            {'identity': {'principal': DID, 'intent': self.intent}, 'text': 'Rang.'},
            {'identity': {'principal': DID, 'intent': 'another'}, 'text': 'another private answer'}]}]
        view = self.procedure()
        self.assertEqual((view['outcome']['status'], view['offers']), ('admitted', ['Rang.']))
        saved = json.loads(self.path.read_text())
        self.assertEqual((saved['outcome']['status'], saved['receipt']), ('admitted', view['receipt']))
        self.assertNotIn('another private answer', json.dumps(saved))
        self.assertEqual([c.args[0]['op'] for c in self.front.host.send.call_args_list], ['world-receipt', 'world-offers'])

    def test_an_unknown_identity_runs_and_a_host_timeout_never_runs_from_a_saved_answer(self):
        self.front.st.write(self.path, {'receipt': {'entry': {'$link': 'forged'}}})
        self.front.host.send.side_effect = [{'status': 'unknown'}, self.receipt('admitted', 2)]
        self.assertEqual(self.procedure()['outcome']['status'], 'admitted')
        self.front.host.send.reset_mock()
        self.front.host.send.side_effect = None
        self.front.host.send.return_value = {'status': 'error', 'class': 'hostTimeout'}
        reply = self.front.turn(self.front.host, DID, 'bell', 'rain', {'intent': self.intent}, first_receipt=True)
        self.assertEqual(reply['class'], 'hostTimeout')
        self.assertEqual([c.args[0]['op'] for c in self.front.host.send.call_args_list], ['world-receipt'])

    def test_a_current_suspension_and_a_terminal_refusal_never_rerun_a_changed_call(self):
        for tag, outcome in [('suspended', {}), ('refused', {'class': 'cardRefused'})]:
            with self.subTest(tag=tag):
                current = self.receipt(tag, **outcome)
                self.front.host.send.reset_mock()
                self.front.host.send.side_effect = [current] if tag == 'suspended' else [current, {'status': 'offers', 'offers': []}]
                self.handler.body.return_value['call'] = {'object': 'missing', 'verb': 'missing'}
                view = self.procedure()
                self.assertEqual(view['outcome']['status'], tag)
                self.assertEqual(view['receipt']['entry']['$link'], current['receipt']['hash'])
                self.assertFalse(any(c.args[0]['op'] == 'world-turn' for c in self.front.host.send.call_args_list))


class PlainFields(unittest.TestCase):
    def test_tag_named_fields_at_the_top_nested_and_in_lists_are_records_even_when_they_spell_data(self):
        from transport.host import typed
        fields = {'tag': 'blue', 'text': 'rain', 'nested': {'tag': 'label', 'value': 'ordinary'},
                  'list': [{'tag': 'record', 'fields': []}]}
        expected = record(tag=label('blue'), text=label('rain'), nested=record(tag=label('label'), value=label('ordinary')),
                          list={'tag': 'list', 'items': [record(tag=label('record'), fields={'tag': 'list', 'items': []})]})
        self.assertEqual(typed(fields), expected)
        self.assertEqual(typed({'nested': fields['nested']}), record(nested=record(tag=label('label'), value=label('ordinary'))))
        self.assertEqual(typed({'list': fields['list']}), record(list={'tag': 'list', 'items': [
            record(tag=label('record'), fields={'tag': 'list', 'items': []})]}))

    def test_tag_named_fields_at_the_body_limit_are_converted_and_explicit_typed_arguments_pass_directly(self):
        from transport.http import argument, MAX_BODY
        body = {'call': {'object': 'bell', 'verb': 'rain', 'fields': {'tag': 'blue', 'text': ''}}}
        body['call']['fields']['text'] = 'x' * (MAX_BODY - len(json.dumps(body).encode()))
        self.assertEqual(len(json.dumps(body).encode()), MAX_BODY)
        fields = body['call']['fields']
        self.assertEqual(argument({'fields': fields}), record(tag=label('blue'), text=label(fields['text'])))
        explicit = record(tag=label('blue'), text=label('rain'))
        self.assertIs(argument({'argument': explicit}), explicit)

    def test_the_create_route_converts_empty_tag_named_and_maximum_body_seeds_to_typed_records(self):
        from transport.http import Handler, MAX_BODY
        handler = Handler.__new__(Handler)
        handler.path, handler.headers = '/AGENTS.md/scratch/try/objects', {'Authorization': 'Bearer token'}
        handler.server = mock.Mock()
        handler.server.limited.return_value = 0
        handler.server.host.send.return_value = {'status': 'parsed', 'spell': {'card': 'bell'}}
        host = handler.server.host.at.return_value
        host.send.return_value = {'status': 'created'}
        handler.principal = mock.Mock(return_value={'did': DID})
        handler.browser = mock.Mock(return_value=False)
        handler.body = mock.Mock()
        handler.answer = mock.Mock()
        maximum = {'object': 'bell', 'intent': 'make', 'seed': {'text': ''}}
        maximum['seed']['text'] = 'x' * (MAX_BODY - len(json.dumps(maximum).encode()))
        self.assertEqual(len(json.dumps(maximum).encode()), MAX_BODY)
        for seed, expected in [({}, record()), ({'count': 0}, record(count=nat(0))),
                               ({'tag': 'label', 'nested': {'tag': 'blue'}}, record(tag=label('label'), nested=record(tag=label('blue')))),
                               (maximum['seed'], record(text=label(maximum['seed']['text'])))]:
            with self.subTest(keys=list(seed), size=len(json.dumps(seed))):
                handler.body.return_value = {'object': 'bell', 'intent': 'make', 'seed': seed}
                handler.agents('create', 'try', None, None)
                self.assertEqual(host.send.call_args.args[0]['seed'], expected)

    def test_the_scratch_create_helper_sends_a_plain_seed_to_the_api(self):
        front = FrontCase.__new__(FrontCase)
        front.scratch_open, front.call = mock.Mock(), mock.Mock()
        front.scratch_create('token')
        self.assertEqual(front.call.call_args.args[2]['seed'], {'count': 0})


class CurrentReceiptHost(ServeCase):
    OPENER = 'did:plc:' + 'r' * 24

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from deploy import genesis
        _, refusal = genesis.run(cls.root, cls.OPENER)
        assert refusal is None, refusal

    def setUp(self):
        from transport.http import Handler
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.front = Front.__new__(Front)
        self.front.st = State(tmp.name)
        self.front.host = self.host
        self.front.bounds = self.host.send({'op': 'bounds'})
        self.front.turn_lock = threading.Lock()
        self.front.draft_turn = mock.Mock()
        self.handler = Handler.__new__(Handler)
        self.handler.server = self.front
        self.handler.reply = mock.Mock()

    def procedure(self, body):
        self.handler.body = mock.Mock(return_value=body)
        self.handler.procedure('act', DID)
        code, raw = self.handler.reply.call_args.args
        self.assertEqual(code, 200)
        return json.loads(raw)

    def test_quota_zero_then_a_new_hour_and_quota_one_reruns_the_maximum_intent_at_the_host(self):
        from transport import bridge
        settings = lambda n: self.root.send({'op': 'world-settings', 'principal': self.OPENER,
                                             'reading': 'test interpretation quota', 'interpretQuota': n})
        self.addCleanup(settings, 48)
        self.assertEqual(settings(0)['status'], 'settings')
        body = {'intent': 'é' * 128, 'call': {'object': 'commonplace', 'verb': 'receive',
                                            'fields': {'text': 'something green', 'post': ''}}}
        refused = self.procedure(body)
        self.assertEqual((refused['outcome']['status'], refused['outcome']['class']), ('refused', 'quota'), refused)
        clock = self.host.send({'op': 'world-status'})['clock']
        advanced = self.host.send({'op': 'world-advance', 'principal': 'transport', 'height': (clock // 60 + 1) * 60})
        self.assertEqual(advanced['status'], 'advanced', advanced)
        self.assertEqual(settings(1)['status'], 'settings')
        retried = self.procedure(body)
        self.assertEqual(retried['outcome']['status'], 'suspended', retried)
        self.assertGreater(retried['receipt']['height'], refused['receipt']['height'])
        current = self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': body['intent']})['receipt']
        self.assertEqual(retried['receipt']['entry']['$link'], current['hash'])
        saved = json.loads(bridge.answer_path(self.front.st, bridge.xrpc_source(DID, body['intent'])).read_text())
        self.assertEqual(saved['receipt'], retried['receipt'])

    def test_a_suspended_strike_retries_without_a_turn_then_settlement_replaces_the_answer_even_for_a_changed_call(self):
        from tests.test_await import HUB, STRIKER
        from transport import bridge
        for name, source, seed in [('receipt-hub', HUB, record(count=nat(0))),
                                   ('receipt-striker', STRIKER, record(principal=label(DID), intent=label('receipt-answer')))]:
            made = self.root.send({'op': 'world-create', 'principal': self.OPENER, 'identity': 'make-' + name,
                                   'object': name, 'modules': closure('World', 'Card') + [{'name': 'Test', 'source': source}],
                                   'entry': 'initial', 'seed': seed})
            self.assertEqual(made['status'], 'created', made)
        body = {'intent': 'receipt-strike', 'call': {'object': 'receipt-striker', 'verb': 'strike'}}
        suspended = self.procedure(body)
        self.assertEqual(suspended['outcome']['status'], 'suspended', suspended)
        height = self.host.send({'op': 'world-status'})['height']
        self.assertEqual(self.procedure(body)['receipt'], suspended['receipt'])
        self.assertEqual(self.host.send({'op': 'world-status'})['height'], height)
        settled = self.host.send({'op': 'world-turn', 'principal': DID, 'identity': 'receipt-answer',
                                  'object': 'receipt-hub', 'method': 'receive', 'argument': record(text=label('yes'), post=label(''))})
        self.assertEqual(settled['status'], 'admitted', settled)
        height = self.host.send({'op': 'world-status'})['height']
        retried = self.procedure({**body, 'call': {'object': 'missing', 'verb': 'missing'}})
        self.assertEqual(retried['outcome']['status'], 'admitted', retried)
        self.assertNotEqual(retried['receipt'], suspended['receipt'])
        self.assertEqual(self.host.send({'op': 'world-status'})['height'], height)
        current = self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': body['intent']})['receipt']
        self.assertEqual(retried['receipt']['entry']['$link'], current['hash'])
        saved = json.loads(bridge.answer_path(self.front.st, bridge.xrpc_source(DID, body['intent'])).read_text())
        self.assertEqual((saved['outcome']['status'], saved['receipt']), ('admitted', retried['receipt']))

    def test_plain_top_and_nested_tag_fields_and_an_explicit_typed_argument_are_admitted_by_the_host(self):
        source = declared('''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def rain(state: State, input: {tag: String, nested: {tag: String, text: String}}, context: Abi.Context) -> Activity<String>:
  input.nested.text
''', 'rain')
        made = self.root.send({'op': 'world-create', 'principal': self.OPENER, 'identity': 'make-tag-fields',
                               'object': 'tag-fields', 'modules': counter_modules()[:-1] + [{'name': 'Test', 'source': source}],
                               'entry': 'initial', 'seed': record()})
        self.assertEqual(made['status'], 'created', made)
        body = {'intent': 'tag-plain', 'call': {'object': 'tag-fields', 'verb': 'rain',
                                             'fields': {'tag': 'blue', 'nested': {'tag': 'label', 'text': 'rain'}}}}
        answer = self.procedure(body)
        self.assertEqual(answer['outcome']['status'], 'admitted', answer)
        explicit = record(tag=label('blue'), nested=record(tag=label('label'), text=label('rain')))
        answer = self.front.turn(self.host, DID, 'tag-fields', 'rain', {'intent': 'tag-typed', 'argument': explicit})
        self.assertEqual(answer['status'], 'admitted', answer)


class Repl(FrontCase):
    fresh_world = True  # each test opens a scratch world of its own

    TWICE = 'edition ObjectiveBend 1\ndef twice(n: Nat) -> Nat:\n  n + n\n'
    SPOON = '''edition ObjectiveBend 1
record State:
  count: Nat
def rain(state: State) -> Nat:
  state.count + 1n
def initial() -> State:
  {count: 0n}
def receive(state: State) -> Nat:
  state.count
'''

    def test_scratch_check_spoon_example_defaults_to_initial_and_full_shows_the_artifact(self):
        """Refuted by the spoon check body without entry failing instead of checking initial."""
        tok = self.login()
        self.assertEqual(self.scratch_open(tok, 'lab')[1]['status'], 'scratch')
        paths = ('docs/AGENTS-API.md', 'capsules/pages/bend.txt', 'capsules/pages/check.txt')
        for path in paths:
            with self.subTest(page=path):
                text = (Path(__file__).resolve().parents[1] / path).read_text()
                example = json.loads(re.search(r'```json\n(.*?)\n```', text, re.S)[1])
                s, checked = self.call('POST', '/AGENTS.md/scratch/lab/check', example, tok)
                self.assertEqual((s, checked['status']), (200, 'checked'), checked)
                self.assertNotIn('artifact', checked)
        for body in (example, {'modules': example['modules']}, {'source': example['modules'][-1]['source']}):
            with self.subTest(body=body):
                s, checked = self.call('POST', '/AGENTS.md/scratch/lab/check?full=1', body, tok)
                self.assertEqual((s, checked['status']), (200, 'checked'), checked)
                self.assertEqual(checked['artifact']['entry'], 'initial', checked)

    def test_scratch_check_entry_spoon_teaches_definitions_of_the_last_module(self):
        """Refuted by entry spoon or check spoon giving no definition list or repair, or using an earlier module's defs."""
        tok = self.login()
        self.assertEqual(self.scratch_open(tok, 'lab')[1]['status'], 'scratch')
        modules = [
            {'name': 'Earlier', 'source': 'edition ObjectiveBend 1\ndef spoon() -> Nat:\n  9n\ndef earlierOnly() -> Nat:\n  0n\n'},
            {'name': 'spoon', 'source': self.SPOON},
        ]
        for entry in ('spoon', 'check spoon'):
            with self.subTest(entry=entry):
                s, refused = self.call('POST', '/AGENTS.md/scratch/lab/check', {'modules': modules, 'entry': entry}, tok)
                self.assertEqual((s, refused['status']), (200, 'refused'), refused)
                diagnostic = refused['diagnostic']
                self.assertTrue(diagnostic['message'].startswith('missing selected entry'), diagnostic)
                teaching = diagnostic['message'] + '\n' + (refused.get('hint') or diagnostic.get('hint') or '')
                self.assertIn('entry names a definition of the last module', teaching)
                self.assertRegex(teaching, r'initial,\s*rain,\s*receive')
                self.assertIn('entry: initial', teaching)
                self.assertNotIn('earlierOnly', teaching)

    def test_a_repl_takes_plain_json_arguments_as_well_as_typed_ones(self):
        """Refuted by `arguments: [21]` answering 400 `String expected` (the host reads `tag` off a bare number)."""
        tok = self.login()
        self.scratch_open(tok, 'lab')
        s, r = self.repl(tok, source=self.TWICE, entry='twice', arguments=[21])
        self.assertEqual((s, r.get('value')), (200, nat(42)), r)
        s, r = self.repl(tok, source=self.TWICE, entry='twice', arguments=[nat(21)])
        self.assertEqual((s, r.get('value')), (200, nat(42)), r)  # typed data goes through as it was

    def test_a_repl_or_check_body_that_lacks_what_the_host_reads_is_named_not_string_expected(self):
        """Refuted by a check with no source, a repl with no entry, a non-string source or non-list arguments answering the host's words."""
        tok = self.login()
        self.scratch_open(tok, 'lab')
        for kind, body, field in (('check', {'entry': 'twice'}, 'source'), ('check', {'source': ['edition']}, 'source'),
                                  ('repl', {'source': self.TWICE}, 'entry'), ('repl', {'source': self.TWICE, 'entry': 'twice', 'arguments': '21'}, 'arguments'),
                                  ('repl', {'source': {'a': 1}, 'entry': 'twice'}, 'source')):
            s, e = self.call('POST', f'/AGENTS.md/scratch/lab/{kind}', body, tok)
            self.assertEqual((s, e['class']), (400, 'badRequest'), (kind, body, e))
            self.assertIn(field, e['message'])

    def test_every_refusal_is_logged_with_its_class_and_never_its_words(self):
        """Refuted by a 4xx or 5xx line with no `class=`, by the host's stage missing from a compile refusal, or by the source text,
        a host message or a stage with a space or newline in it appearing in the log."""
        log = Path(self.tmp.name) / 'access.log'
        self.front.access = AccessLog(log, 'town')
        tok = self.login()
        self.scratch_open(tok, 'lab')
        habit = 'edition ObjectiveBend 1\nsum Light:\n  on: {}\n  off: {}\ndef flip(l: Light) -> Nat:\n  match l:\n    on(_) -> 1n\n    off(_) -> 0n\n# secret-words\n'
        self.assertEqual(self.repl(tok, source=habit, entry='flip')[0], 400)
        self.assertEqual(self.repl(tok, source=self.TWICE, entry='twice', arguments=[nat(1)])[0], 200)
        self.assertEqual(self.call('POST', '/AGENTS.md/scratch/lab/check', {'entry': 'x'}, tok)[0], 400)
        self.assertEqual(self.repl(tok, source='x' * 140000, entry='pure')[0], 413)
        self.assertEqual(self.call('GET', '/AGENTS.md/world/nowhere', token=tok)[0], 404)
        scratch = mock.Mock()
        scratch.send = lambda req: {'status': 'error', 'message': 'secret-message', 'stage': 'two words\nGET /x 200', 'clause': 'noSuchClause'}
        self.addCleanup(setattr, self.host, 'at', self.host.at)
        self.host.at = lambda world: scratch
        self.assertEqual(self.repl(tok, source=self.TWICE, entry='twice')[0], 400)
        for _ in range(200):  # a line follows its reply
            lines = log.read_text().splitlines()
            if any('noSuchClause' in l for l in lines):
                break
            time.sleep(0.02)
        rows = [l.split() for l in lines]
        tail = lambda path, i=0: [r for r in rows if r[2].endswith(path)][i]
        self.assertEqual(tail('/repl', 0)[7:], ['class=hostRequest:objective-source-parse'])
        self.assertEqual((tail('/repl', 1)[3], len(tail('/repl', 1))), ('200', 7))  # a success carries no class
        self.assertEqual(tail('/check')[7:], ['class=badRequest'])
        self.assertEqual((tail('/repl', 2)[3], tail('/repl', 2)[7:]), ('413', ['class=moduleTooLarge']))
        self.assertEqual(tail('/nowhere')[7:], ['class=unknown'])
        self.assertEqual(tail('/repl', 3)[7:], ['class=hostRequest:noSuchClause'])  # a stage with a space is dropped, the clause kept
        text = '\n'.join(lines)
        for secret in ('secret-words', 'secret-message', 'two words', tok, 'Bearer'):
            self.assertNotIn(secret, text)
        self.assertLess(max(map(len, lines)), 300)

    def test_a_label_is_a_fixed_identifier_or_nothing(self):
        """Refuted by a space, a newline, a quote, an over-long word or a non-string reaching the access log's class column."""
        from transport.http import named
        self.assertEqual(named('hostRequest', 'objective-typed-check'), 'hostRequest:objective-typed-check')
        self.assertEqual(named('hostRequest', None), 'hostRequest')
        for bad in ('a b', 'a\nb', "a'b", 'x' * 49, '', 7, ['a'], '1abc', 'a=b'):
            self.assertIsNone(named(bad), bad)
        self.assertEqual(named('x' * 48), 'x' * 48)

    def repl(self, tok, scratch='lab', full=False, **body):
        return self.call('POST', f'/AGENTS.md/scratch/{scratch}/repl' + ('?full=1' if full else ''), body, tok)

    def test_repl_runs_a_pure_entry_in_a_scratch_and_passes_errors_through(self):
        tok = self.login()
        self.assertEqual(self.scratch_open(tok, 'lab')[1]['status'], 'scratch')
        s, r = self.repl(tok, source=PLANS, entry='pure', arguments=[nat(1)])
        self.assertEqual((s, r['status'], r['value']), (200, 'finished', nat(2)), r)
        s, e = self.repl(tok, source=PLANS, entry='nope')
        self.assertEqual((s, e['status']), (400, 'error'))
        self.assertIn('missing selected entry', e['message'])
        self.assertEqual(self.repl(tok, source='x' * 140000, entry='pure')[0], 413)
        self.assertEqual(self.call('POST', '/AGENTS.md/repl', {'source': PLANS, 'entry': 'pure'}, tok)[0], 404)  # one REPL, a scratch's
        self.assertIn('no scratch/gone', self.repl(tok, scratch='gone', source=PLANS, entry='pure')[1]['message'])

    def test_an_activity_defines_an_object_in_the_scratch_that_keeps_its_state_across_requests_and_restarts(self):
        tok = self.login()
        self.scratch_open(tok, 'lab')
        s, first = self.repl(tok, full=True, source=REPL_COUNTER, entry='bump', intent='r1')
        self.assertEqual((s, first['status'], first['result'], first['defined']['outcome']['tag']), (200, 'admitted', nat(1), 'created'), first)
        self.assertEqual(self.repl(tok, full=True, entry='bump', intent='r2')[1]['result'], nat(2))  # no source: the object as it stands
        from transport.config import LIBRARY
        self.server.stop()  # the scratch is a world: what the REPL defined outlives the process
        self.server = served(self.state_dir.name, cleanup=self.addCleanup, opener=self.OPENER, library=LIBRARY)
        again = self.repl(tok, full=True, source=REPL_COUNTER, entry='bump', intent='r3')[1]
        self.assertEqual((again['result'], 'defined' in again), (nat(3), False), again)  # the same source is not made again
        s, seen = self.call('GET', '/AGENTS.md/scratch/lab/world/repl', token=tok)
        self.assertEqual(seen['state'], record(count=nat(3)), seen)
        self.assertEqual(self.host.send({'op': 'world-view', 'principal': DID, 'object': 'repl'})['status'], 'unknown')  # not the town's

    def test_check_and_compile_refusals_carry_the_hosts_hint(self):
        tok = self.login()
        self.scratch_open(tok, 'lab')
        habit = 'edition ObjectiveBend 1\nsum Light:\n  on: {}\n  off: {}\ndef flip(l: Light) -> Nat:\n  match l:\n    on(_) -> 1n\n    off(_) -> 0n\n'
        s, c = self.call('POST', '/AGENTS.md/scratch/lab/check', {'source': habit, 'entry': 'flip'}, tok)
        self.assertEqual((s, c['status']), (200, 'refused'), c)
        self.assertIn('case label(x): body', c['hint'])
        s, e = self.repl(tok, source=habit, entry='flip')
        self.assertEqual((s, e['status']), (400, 'error'), e)
        self.assertIn('case label(x): body', e['hint'])
        self.assertIn('stage', e)
        s, ok = self.call('POST', '/AGENTS.md/scratch/lab/check', {'source': REPL_COUNTER, 'entry': 'bump'}, tok)
        self.assertEqual((s, ok['status']), (200, 'checked'), ok)


class Scratch(FrontCase):
    fresh_world = True  # a principal holds two scratch worlds at most: each test opens its own
    def test_a_scratch_receipt_is_cited_in_the_town_and_its_owner_expires_it_with_the_world_spell(self):
        tok = self.login()
        made = self.scratch_create(tok)[1]
        s, cited = self.call('POST', '/AGENTS.md/scratch/try/cite', {'receipt': made['receipt']['hash']}, tok)
        self.assertEqual((s, cited['status'], cited['_links']['receipt']['href']), (200, 'cited', f"/AGENTS.md/receipt/{cited['receipt']['slug']}"), cited)
        self.assertEqual(self.call('POST', '/AGENTS.md/scratch/try/cite', {'receipt': 'bafy'}, tok)[0], 400)
        self.assertEqual(self.call('GET', '/AGENTS.md/scratch/try/pending', token=tok)[1]['status'], 'pending')  # the scratch is the caller's
        self.assertEqual(self.call('POST', '/AGENTS.md/scratch/try/deliver', {}, tok)[1]['status'], 'delivered')
        s, gone = self.call('POST', '/AGENTS.md/world/world/expire', {'fields': {'scratch': 'try'}}, tok)
        self.assertEqual((s, gone['status'], gone['scratch']['world']), (200, 'expired', 'scratch/try'), gone)
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=tok)[1]['scratches'], [])
        self.assertIn('expired', self.call('GET', '/AGENTS.md/scratch/try/world', token=tok)[1]['message'])

    def test_a_created_reply_shows_one_hash_by_default_and_all_of_them_with_full(self):
        import re
        tok = self.login()
        body = {'intent': 'mk-hash', 'object': 'hash1', 'modules': [{'name': 'Tally', 'source': REPL_COUNTER}], 'entry': 'initial', 'seed': {'count': 1}}
        self.scratch_open(tok)
        s, _, raw = self.request('POST', '/AGENTS.md/scratch/try/objects', body, tok)
        self.assertEqual(s, 200, raw)
        self.assertEqual(re.findall(rb'bafy\w+', raw), [json.loads(raw)['receipt']['hash'].encode()], raw)
        body['intent'], body['object'] = 'mk-hash-2', 'hash2'
        s, _, raw = self.request('POST', '/AGENTS.md/scratch/try/objects?full=1', body, tok)
        self.assertGreater(len(re.findall(rb'bafy\w+', raw)), 3)
        s, v = self.call('GET', '/AGENTS.md/scratch/try/world/hash1', token=tok)
        self.assertNotIn('pin', v)
        self.assertIn('pin', self.call('GET', '/AGENTS.md/scratch/try/world/hash1/source', token=tok)[1])

    def test_a_scratch_worlds_pending_and_deliver_are_its_owners(self):
        tok = self.login()
        self.scratch_open(tok)
        s, p = self.call('GET', '/AGENTS.md/scratch/try/pending', token=tok)
        self.assertEqual((s, p['status'], p['_links']['deliver']['href']), (200, 'pending', '/AGENTS.md/scratch/try/deliver'), p)
        s, d = self.call('POST', '/AGENTS.md/scratch/try/deliver', {}, tok)
        self.assertEqual(s, 200, d)

    def test_a_scratch_object_no_spell_can_address_is_refused_before_it_is_created(self):
        tok = self.login()
        for name in ('coin box', 'c' * 129):  # a space splits the spell's card from its action; past 128 bytes no card is read
            s, e = self.scratch_create(tok, name)
            self.assertEqual((s, e['class']), (400, 'unspellable'), e)
            self.assertIn(f'delvetalk {name} ?', e['message'])
        self.assertEqual(self.call('GET', '/AGENTS.md/scratch/try/world/coin%20box', token=tok)[0], 404)
        self.assertEqual(self.scratch_create(tok, 'Coin_box')[0], 200)  # one rule names objects and spell cards


    def test_a_scratch_world_is_private_and_missing_is_404_not_403(self):
        a, b = self.login(), self.login('glm.delve.town')
        s, r = self.scratch_create(a)
        self.assertEqual((s, r['status']), (200, 'created'), r)
        s, t = self.call('POST', '/AGENTS.md/scratch/try/world/h1/bump', {'argument': record(), 'intent': 't1'}, a)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        self.assertEqual(self.call('GET', '/AGENTS.md/scratch/try/world/h1', token=a)[1]['version'], 1)
        self.assertEqual(self.scratch_open(b)[1]['status'], 'scratch')
        s, v = self.call('GET', '/AGENTS.md/scratch/try/world/h1', token=b)
        self.assertEqual((s, v['status'], v['class']), (404, 'refused', 'unknown'))
        self.assertEqual(self.call('GET', '/AGENTS.md/world/h1', token=a)[0], 404)  # the shared world never sees it
        self.assertEqual(self.call('GET', '/AGENTS.md/scratch/try/receipt/t1', token=b)[1].get('class'), 'unknown')

    def test_opening_a_scratch_world_forking_the_town_and_the_limit_of_two(self):
        tok = self.login()
        s, e = self.call('GET', '/AGENTS.md/scratch/nope/world', token=tok)
        self.assertEqual((s, e['class']), (400, 'hostRequest'), e)
        self.assertIn('open one with world-scratch', e['message'])
        s, r = self.scratch_open(tok, 'try', **{'from': {'world': 'town'}})
        self.assertEqual((s, r['status'], r['world']), (200, 'scratch', 'scratch/try'), r)
        self.assertEqual(r['_links']['world']['href'], '/AGENTS.md/scratch/try/world')
        self.assertIn(self.c, json.dumps(self.call('GET', '/AGENTS.md/scratch/try/world', token=tok)[1]))
        self.assertEqual(self.scratch_open(tok, 'try')[0], 400)  # it exists
        s, e = self.scratch_open(tok, 'Bad')  # the name is the host's to judge
        self.assertEqual(s, 400, e)
        self.assertIn('a scratch name is', e['message'])
        self.assertEqual(self.scratch_open(tok, 'two')[1]['status'], 'scratch')
        s, r = self.scratch_open(tok, 'three')
        self.assertEqual(r['status'], 'refused', r)
        self.assertEqual(r['class'], 'capacity', r)
        self.assertEqual([x['world'] for x in self.call('GET', '/AGENTS.md/me', token=tok)[1]['scratches']], ['scratch/try', 'scratch/two'])

    def test_a_scratch_route_is_named_by_the_router_and_described_by_options(self):
        from transport.http import resolve
        self.assertEqual(resolve('POST', '/AGENTS.md/scratch')[0], 'scratch')
        self.assertEqual(resolve('GET', '/AGENTS.md/scratch/try/world/x/card')[1]['scratch'], 'try')
        self.assertEqual(resolve('POST', '/AGENTS.md/scratch/try/objects')[0], 'create')
        self.assertEqual(resolve('POST', '/AGENTS.md/objects')[0], None)
        self.assertEqual(resolve('POST', '/AGENTS.md/scratch/try/repl')[0], 'repl')
        self.assertEqual((resolve('POST', '/AGENTS.md/repl')[0], resolve('POST', '/AGENTS.md/check')[0]), (None, None))
        s, _, raw = self.request('OPTIONS', '/AGENTS.md/scratch/try/objects')
        self.assertEqual((s, [e['name'] for e in json.loads(raw)['routes']]), (200, ['create']))


class Pages(FrontCase):
    def test_page_uses_world_card_without_journaling_and_history_is_newest_first(self):
        for i in range(25):
            self.host.send({'op': 'world-turn', 'principal': DID, 'object': self.c, 'method': 'bump', 'argument': record(), 'identity': f'h{i}'})
        real, seen = self.host.send, []

        def send(req):
            seen.append(req['op'])
            if req['op'] == 'world-card':
                return {'status': 'card', 'text': 'CARD for ' + req['principal']}
            return real(req)
        self.host.send = send
        newest = real({'op': 'world-status'})['height']  # the last entry touching c1; verifying journals the handle after it
        tok = self.login()
        cookie = 'dt_credential=' + tok
        before = real({'op': 'world-status'})['height']
        s, _, page = self.request('GET', f'/o/{self.c}', headers={'Cookie': cookie})
        self.assertEqual(s, 200)
        self.assertIn(('CARD for ' + DID).encode(), page)
        self.assertEqual(real({'op': 'world-status'})['height'], before)  # no describe/present turn journaled
        heights = [int(x) for x in __import__('re').findall(rb'<span class="code">entry (\d+)</span>', page)]
        self.assertEqual(len(heights), 20)
        self.assertEqual(heights, sorted(heights, reverse=True))
        self.assertEqual(heights[0], newest)
        self.assertEqual(seen.count('world-history'), 1)  # the host pages newest first: one call, no widening window


FORM = 'application/x-www-form-urlencoded'


def browser_login(case, handle=HANDLE):
    """The login page's two forms, as a browser sends them: the challenge sets the session cookie, verify keeps it."""
    s, headers, _ = case.request('POST', '/AGENTS.md/challenge', raw='handle=' + handle, headers={'Content-Type': FORM})
    cookie = next(v for k, v in headers if k == 'Set-Cookie' and v.startswith('dt_credential=')).split(';')[0]
    case.assertTrue(cookie.startswith('dt_credential=dt_agent_'))
    did = PEOPLE[handle]
    case.provider.texts[did] = case.front.identity.db.execute('SELECT text FROM challenges WHERE handle = ? ORDER BY created DESC', (handle,)).fetchone()['text']
    s, headers, _ = case.request('POST', '/AGENTS.md/verify', raw=f'handle={handle}', headers={'Content-Type': FORM, 'Cookie': cookie})
    case.assertEqual(s, 200)
    case.assertIn(cookie, next(v for k, v in headers if k == 'Set-Cookie' and v.startswith('dt_credential=')))
    return cookie


class InTown(FrontCase):
    """A genesis town with its furnishings and a verified browser: a serve per class."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from deploy import genesis
        from tests.town import furnish
        made, refusal = genesis.run(cls.root, cls.OPENER)
        assert refusal is None, refusal
        furnish(cls.root, cls.OPENER)

    def setUp(self):
        super().setUp()
        self.cookie = browser_login(self)

    def play(self, path, text=None, cookie=True):
        self.now[0] += 3  # under the per-credential rate
        headers = {'Cookie': self.cookie} if cookie else {}
        if text is None:
            return self.request('GET', path, headers=headers)
        return self.request('POST', path, raw='text=' + urllib.parse.quote(text), headers={**headers, 'Content-Type': FORM})


class SceneFields(InTown):
    def test_rescene_unwraps_whole_blocks_and_keeps_embedded_markers(self):
        from transport.host import plain

        tok = self.login()
        s, made = self.call('POST', '/AGENTS.md/world/kind/room/make',
                            {'intent': 'block-room-' + self.c, 'fields': {'name': 'block room', 'spween': 'Before.'}}, tok)
        self.assertEqual((s, made['status']), (200, 'admitted'), made)
        room = made['_links']['created'][0]['name']
        short = '=== start\nThe scene starts here.'
        maximum = '=== start\n' + 'x' * 600 + '\n//'
        maximum += 'x' * (16384 - len(maximum))
        cases = []
        for size, scene, prose in (('short', short, 'The scene starts here.'), ('maximum', maximum, 'x' * 600)):
            for form, value in (('heredoc', '<<END\n' + scene + '\nEND'),
                                ('fence', '```spween\n' + scene + '\n```')):
                spell = 'delvetalk ' + room + ' rescene\n' + ('spween: ' + value if form == 'heredoc' else value)
                cases.append((size + '-' + form, value, spell, prose))
        for form, marker in (('heredoc', '<<END\nkept inside prose\nEND'),
                             ('fence', '```spween\nkept inside prose\n```')):
            prose = 'Before the marker.\n' + marker + '\nAfter the marker.'
            scene = '=== start\n' + prose
            cases.append(('embedded-' + form, scene,
                          'delvetalk ' + room + ' rescene\nspween: <<OUTER\n' + scene + '\nOUTER', prose))
        for name, value, spell, prose in cases:
            for path, body in (('spell', {'spell': spell}), ('fields', {'fields': {'spween': value}}),
                               ('argument', {'argument': record(spween=label(value))})):
                with self.subTest(case=name, path=path):
                    s, reply = self.call('POST', '/AGENTS.md/world/' + room + ('/receive' if path == 'spell' else '/rescene'),
                                         {'intent': self.c + '-' + name + '-' + path, **body}, tok)
                    self.assertEqual((s, reply['status']), (200, 'admitted'), reply)
                    state = plain(self.host.send({'op': 'world-view', 'principal': DID, 'object': room})['state'])
                    self.assertEqual((state['start'], [(p['id'], p['text']) for p in state['passages']]),
                                     ('start', [('start', prose)]), state)


class Play(InTown):
    """/play/ against the genesis town: the commonplace, the garden and its interpreter, as a verified browser sees them."""
    OPENER = 'did:plc:' + 'e' * 24

    def answer(self, spell):
        """The town's interpreter, by hand: the one pending request on the commonplace (hob's, for prose the garden hands on or
        a reply to the commonplace itself), answered with a spell."""
        for _ in range(300):
            pending = [p for p in self.host.send({'op': 'world-interpretations'}).get('pending') or [] if p['object'] == 'commonplace']
            if pending:
                break
            time.sleep(0.1)
        r = self.host.send({'op': 'world-interpretation', 'id': pending[-1]['id'],
                            'reply': {'status': 'replied', 'model': 'claude-haiku-5-5', 'json': None, 'raw': spell}})
        self.assertEqual(r['status'], 'interpreted', r)

    def test_without_the_session_cookie_play_redirects_to_the_door(self):
        for method_text in (None, 'delvetalk garden plant'):
            s, headers, _ = self.play('/play/', method_text, cookie=False)
            self.assertEqual((s, dict(headers)['Location']), (303, '/enter'))
        s, _, page = self.request('GET', '/')
        self.assertIn(b'Claim your handle', page)
        self.assertIn(b'action="/AGENTS.md/challenge"', page)

    BANNED = re.compile(r'at://|proof|ledger|chain|hash|\\bpins?\\b|\\bht\\.', re.I)

    def words(self, page):
        """What a person reads of a page: no markup, script, style or comment, and no card or code listing (those are the world's text)."""
        text = page.decode() if isinstance(page, bytes) else page
        text = re.sub(r'<(script|style|pre)\b.*?</\1>|<!--.*?-->', ' ', text, flags=re.S)
        return html.unescape(re.sub(r'<[^>]+>', ' ', text))

    def test_no_page_a_person_reads_sounds_like_a_cryptocurrency(self):
        pages = {'home': self.request('GET', '/')[2], 'home, logged in': self.request('GET', '/', headers={'Cookie': self.cookie})[2],
                 'object': self.request('GET', '/o/garden', headers={'Cookie': self.cookie})[2], 'play': self.play('/play/garden')[2],
                 'commonplace': self.play('/play/')[2], 'style': self.request('GET', '/style/')[2],
                 'the word': self.request('POST', '/AGENTS.md/challenge', raw='handle=' + HANDLE, headers={'Content-Type': FORM, 'Accept': 'text/html'})[2],
                 'a refusal': self.request('GET', '/o/nowhere', headers={'Accept': 'text/html'})[2]}
        for name, page in pages.items():
            self.assertIsNone(self.BANNED.search(self.words(page)), (name, self.BANNED.search(self.words(page))))
        self.assertIn('A town of things that answer.', self.words(pages['home']))
        self.assertRegex(self.words(pages['home, logged in']), r'entry \d+')  # the shelf mark
        self.assertRegex(self.words(pages['home, logged in']), r'\d+ cards')
        self.assertIn('journal, the newest', self.words(pages['object']))


    def test_a_refused_receipt_with_no_roots_answers_on_the_receipt_turn_and_play_routes(self):
        """A spell with colour: gold, an undeclared method, a non-owner `commonplace door`: refused before any root was read."""
        receipt = {'hash': 'h', 'height': 7, 'slug': 'tulun-huzif', 'identity': {'intent': 'x', 'principal': DID},
                   'outcome': {'tag': 'refused', 'class': 'badSpell', 'clause': 'badValue', 'object': 'garden', 'reason': 'colour is one of: amber, violet, silver'}}
        refused = {'status': 'refused', 'class': 'badSpell', 'receipt': receipt}
        real = self.host.send
        self.host.send = lambda req: {'world-turn': refused, 'world-resolve': {'status': 'resolved', 'receipt': receipt}}.get(req['op']) or real(req)
        tok = self.cookie.split('=', 1)[1]
        s, r = self.call('GET', '/AGENTS.md/receipt/tulun-huzif', token=tok)
        self.assertEqual((s, r['receipt']['slug']), (200, 'tulun-huzif'), r)
        self.assertEqual(r['_links']['object']['href'], '/AGENTS.md/world/garden')  # the refusal names the object, not a root
        s, t = self.call('POST', '/AGENTS.md/world/garden/receive', {'intent': 'gold-1', 'spell': 'delvetalk garden plant\ncolour: gold\nseed: a'}, tok)
        self.assertEqual((s, t['status']), (200, 'refused'), t)
        self.assertEqual(t['_links']['receipt']['href'], '/AGENTS.md/receipt/tulun-huzif')
        s, _, page = self.play('/play/garden', 'delvetalk garden plant\ncolour: gold\nseed: a')
        self.assertEqual(s, 200)
        self.assertIn('<p class="turn refused"><span class="stamp">§</span> refused badValue: colour is one of: amber, violet, silver'.encode(), page)  # never folded

    def test_a_turn_from_the_play_page_is_drafted_too(self):
        s, _, _ = self.play('/play/garden', 'delvetalk garden plant\ncolour: amber\nseed: a drafted bell')
        self.assertEqual(s, 200)
        drafts = [json.loads(p.read_text()) for p in sorted(self.outbox.glob('*.json'))] if self.outbox.exists() else []
        self.assertTrue([d for d in drafts if d['http']['intent'].startswith('play:')], drafts)  # cracks R6: a public write from the play page waits for Post

    def test_what_an_act_revealed_is_said_on_the_play_page(self):
        real = self.front.host.send
        said = 'rule seven fired: the bell rang at its seventh rain'

        def revealing(req):  # the host's revealed lines, as it writes them on an admitted reply
            got = real(req)
            return {**got, 'revealed': [said]} if req.get('op') == 'world-turn' and got.get('status') == 'admitted' else got
        with mock.patch.object(self.front.host, 'send', side_effect=revealing):
            s, _, page = self.play('/play/garden', 'delvetalk garden plant\ncolour: amber\nseed: a bell that says so')
        self.assertEqual(s, 200)
        self.assertIn(said, self.words(page))

    def test_plant_by_spell_and_read_the_receipt(self):
        s, _, page = self.play('/play/garden', 'delvetalk garden plant\ncolour: amber\nseed: a bell for lost moths')
        self.assertEqual(s, 200, page)
        line = re.search(rb'admitted garden v(\d+), entry (\d+), receipt ([a-z-]+)', page)
        self.assertIsNotNone(line, page)
        self.assertIn(b', at garden/bell/', page)
        tok = self.cookie.split('=', 1)[1]  # the session is the credential: the agent API reads the same receipt
        s, r = self.call('GET', '/AGENTS.md/receipt/' + line[3].decode(), token=tok)
        self.assertEqual((s, r['receipt']['height']), (200, int(line[2])), r)

    def test_a_reply_is_speech_its_spells_are_suggestions_and_its_receipt_waits_to_be_asked_for(self):
        """docs/WEB.md: what came back leads as prose; the line that introduces a spell labels it as a suggestion that only
        fills the box (?say=, with no script); the admitted line is folded under `receipt`; a refusal is never folded."""
        s, _, page = self.play('/play/garden', 'delvetalk garden plant\ncolour: violet\nseed: a bell that hums')
        page = page.decode()
        self.assertRegex(page, r'<p class="spoken">Planted, [^<]*a bell that hums')
        self.assertRegex(page, r'<details class="receipt"><summary>receipt</summary><p class="turn admitted"><span class="stamp">●</span> admitted garden')
        rain = re.search(r'<a class="say" href="(/play/garden\?say=([^"#]+)#say)">Rain on it</a>', page)
        self.assertIsNotNone(rain, page)
        spell = urllib.parse.unquote(rain[2])
        self.assertTrue(spell.startswith('delvetalk garden/bell/') and '\ntext: ' in spell, spell)
        self.assertEqual(page.count('<form'), 1)  # one box
        s, _, filled = self.play(html.unescape(rain[1]).split('#')[0])
        self.assertIn('>' + html.escape(spell) + '</textarea>', filled.decode())
        self.assertIn('>how to say it</a>', filled.decode())

    def test_the_paint_stands_above_the_exact_card_and_never_without_it(self):
        """OVERHAUL §4 (c): /play/ and /o/ show a card's verified paint above its exact card; with no worker attending, the
        exact card alone, at once; a refused paint never."""
        from transport import interpret
        frame = b'<pre class="card">'
        for path in ('/play/garden', '/play/'):
            s, _, page = self.play(path)
            self.assertEqual((s, page.count(b'class="paint"')), (200, 0))  # nobody paints: the exact card, unkept, and open
            self.assertIn(b'<details class="card" open><summary>the card</summary>' + frame, page)
        self.host.send({'op': 'world-renders'})  # the worker arrives, and finds both queued
        paint = 'Like moonlight through silk.'
        replied = lambda text: {'status': 'replied', 'json': None, 'raw': text, 'model': 'claude-haiku-5-5', 'usage': {}}
        done = interpret.paint(self.host, lambda req: replied(paint if req['user'].startswith('Strokes:\nWhat it is: garden,') else 'You are welcome here.'))
        self.assertTrue(done['painted'], done)
        for page in (self.play('/play/garden')[2], self.request('GET', '/o/garden', headers={'Cookie': self.cookie})[2],
                     self.request('GET', '/o/garden')[2]):
            at = page.find(b'<p class="paint">' + html.escape(paint).encode() + b'</p>')
            self.assertTrue(0 <= at < page.find(frame), page[:2000])
            self.assertIn(b'</p><details class="card" open><summary>the card</summary>' + frame, page)  # painted: current status and actions remain visible
        # A card whose paint the host refused (second person, a welcome) shows exact alone.
        s, _, page = self.play('/play/')
        self.assertEqual((s, page.count(b'class="paint"')), (200, 0))

    def test_entering_a_place_tells_what_happened_there_and_only_the_reader_sees_it(self):
        """A telling (docs/VOICE.md "A telling"): entering the porch on /play/ shows, above what came back, the host's
        frame and what happened there before the reader arrived: the paint when there is one, the exact lines it draws
        on folded beneath it (open in its place when there is none). The porch's own page tells it to a signed-in reader
        and to nobody else; the reply an agent gets carries none of it."""
        from transport import interpret
        glm = PEOPLE['glm.delve.town']
        self.root.send({'op': 'world-arrive', 'principal': 'transport', 'did': glm, 'handle': 'glm.delve.town'})
        for n, spell in enumerate(('delvetalk porch enter', 'delvetalk porch say / line: the lintel creaked at dusk', 'delvetalk porch leave')):
            r = self.root.send({'op': 'world-turn', 'principal': glm, 'object': 'porch', 'method': 'receive', 'identity': 'glm-porch-%d' % n,
                                'argument': record(text=label(spell), post=label(''))})
            self.assertEqual(r['status'], 'admitted', r)
        self.front.sleep = lambda seconds: None  # the paint is not waited for: the exact lines stand in its place
        self.host.send({'op': 'world-renders'})
        page = self.play('/play/porch', 'delvetalk porch enter')[2].decode()
        told = page.find('<section class="telling"><p class="frame">Before you arrived</p>')
        self.assertTrue(0 <= told < page.find('<section class="reply">'), page[:3000])
        self.assertIn('<details class="card" open><summary>what it draws on</summary>', page)
        self.assertIn('glm.delve.town (say): the lintel creaked at dusk', page)
        paint = 'glm.delve.town said “the lintel creaked at dusk”.'
        replied = lambda text: {'status': 'replied', 'json': None, 'raw': text, 'model': 'claude-haiku-5-5', 'usage': {}}
        done = interpret.paint(self.host, lambda req: replied(paint if 'a telling of porch' in req['user'] else 'A porch.'))
        self.assertTrue(done['painted'], done)
        page = self.request('GET', '/o/porch', headers={'Cookie': self.cookie})[2].decode()
        at = page.find('<section class="telling"><p class="frame">Before you arrived</p><p class="paint">' + html.escape(paint) + '</p>')
        self.assertTrue(0 <= at < page.find('<details class="card" open><summary>the card</summary>'), page[:3000])
        self.assertIn('<details class="card"><summary>what it draws on</summary>', page)  # painted: the lines folded, never gone
        self.assertNotIn('class="telling"', self.request('GET', '/o/porch')[2].decode())  # nobody signed in: nobody to tell
        self.assertNotIn('class="telling"', self.play('/play/porch')[2].decode())  # a look is not an arrival
        s, r = self.call('POST', '/AGENTS.md/world/porch/receive', {'intent': 'leave-porch', 'spell': 'delvetalk porch leave'},
                         self.cookie.split('=', 1)[1])
        self.assertEqual(s, 200, r)
        self.assertNotIn('Before you arrived', json.dumps(r))
        self.assertNotIn(paint, json.dumps(r))

    def test_plant_by_prose_shows_the_interpreters_offer(self):
        out = {}
        t = threading.Thread(target=lambda: out.update(page=self.play('/play/', 'please plant me something violet for the owls')[2]))
        t.start()
        self.answer('delvetalk garden plant\nseed: a bell for the owls\ncolour: violet')
        t.join(60)
        self.assertIn(b'suspended, entry', out['page'])
        self.assertIn(b'a bell for the owls', out['page'])  # the interpreter's proposal, as the offer to this turn

    def test_prose_at_a_card_on_the_play_page_is_hobs_with_that_cards_table(self):
        """The owner's question on /play/kinds (2026-10-11): words at a card go to hob (HOST-HANDOFF §5.4), who is offered
        that card's table; the turn waits as a pending interpretation on kinds, and hob's `none` is silence."""
        words = 'what is a kind? what is the things in a cistern?'
        self.front.sleep = lambda seconds: None
        page = self.play('/play/kinds', words)[2]
        self.assertRegex(self.words(page), r'suspended, entry \d+')
        self.assertNotIn('hob: ', page.decode())
        [item] = [p for p in self.host.send({'op': 'world-interpretations'}).get('pending') or [] if p['utterance'] == words]
        self.assertEqual((item['object'], [(o['card'], o['action']) for o in item['offers']][:1]), ('kinds', [('kinds', 'make')]), item)
        settled = self.host.send({'op': 'world-interpretation', 'id': item['id'],
                                  'reply': {'status': 'replied', 'model': 'm', 'json': None, 'raw': 'none'}})
        self.assertEqual(settled['status'], 'interpreted', settled)
        [resumed] = settled['resumed']
        self.assertEqual((resumed['status'], resumed['receipt']['outcome'].get('tag'), resumed['receipt'].get('offers', [])), ('admitted', 'admitted', []), resumed)

    def test_a_suspended_turn_is_a_line_under_a_kilobyte_and_its_full_reply_elides_the_blocks(self):
        tok = self.cookie.split('=', 1)[1]
        self.front.sleep = lambda seconds: None
        s, t = self.call('POST', '/AGENTS.md/world/commonplace/receive', {'intent': 'wait-1', 'spell': 'something green perhaps'}, tok)
        self.assertEqual((s, t['status']), (200, 'suspended'), t)
        self.assertLess(len(json.dumps(t)), 1024, t)
        self.assertTrue(t['line'].startswith('… suspended, entry '), t['line'])
        self.assertEqual(t['later'], "hob is reading this; the outcome will reach your inbox (your avatar's notes), "
                                    "or GET /AGENTS.md/receipt?intent=wait-1")
        s, whole = self.call('GET', '/AGENTS.md/receipt/' + t['receipt']['slug'], token=tok)
        self.assertNotIn('"blocks": [', json.dumps(whole))  # the receipt's blocks are counted, not shown
        self.answer('delvetalk garden plant\nseed: a bell\ncolour: violet')  # settle the pending interpretation for the next test



class GuestDoor(InTown):
    """/enter (docs/WEB.md "The guest door"): a person with an invitation and no delve.town account comes in from a
    browser with an open code and a name, plays as their avatar, signs out, and signs in again with the key shown once."""
    OPENER = 'did:plc:' + 'g' * 24
    hosted_accounts = True
    PAGE = {'Accept': 'text/html', 'Content-Type': FORM}

    def door(self, form, cookie=None):
        self.now[0] += 3
        return self.request('POST', '/enter', raw=urllib.parse.urlencode(form), headers={**self.PAGE, **({'Cookie': cookie} if cookie else {})})

    def test_an_open_code_and_a_name_let_a_person_in_to_play_and_out_and_in_again_with_the_key(self):
        s, _, page = self.request('GET', '/enter', headers={'Accept': 'text/html'})
        self.assertEqual(s, 200)
        for form in ('<form class="door-in" method="post" action="/enter">', 'name="code"', 'name="name"', 'name="credential"'):
            self.assertIn(form.encode(), page)
        self.assertNotIn(b'{"', page)
        self.assertIn(b'href="/enter"', self.request('GET', '/', headers={'Accept': 'text/html'})[2])  # linked from the front page
        code = self.front.identity.invite(None, 'little-claude asked')['code']
        robin = f'robin-{self.c}'
        s, headers, page = self.door({'code': code, 'name': robin})
        self.assertEqual(s, 200, page[:500])
        cookie = next(v for k, v in headers if k == 'Set-Cookie' and v.startswith('dt_credential='))
        self.assertIn('HttpOnly', cookie)
        key = cookie.split(';')[0].split('=', 1)[1]
        self.assertTrue(key.startswith('dt_agent_'))
        self.assertIn(f'<pre class="key">{key}</pre>'.encode(), page)  # shown once, to keep
        self.assertEqual(dict(headers)['Cache-Control'], 'private, no-store')
        self.assertIn(f'Welcome, {robin}'.encode(), page)
        jar = 'dt_credential=' + key
        # Playing every place as a resident does: the avatar, `me`, the book, trying first, acting.
        s, me = self.call('GET', '/AGENTS.md/me', token=key)
        self.assertEqual((me['handle'], me['did']), (robin, f'guest:gsb.fg-goose.online:{robin}'))
        s, _, page = self.request('GET', '/play/garden', headers={'Cookie': jar})
        self.assertEqual(s, 200)
        self.assertIn(f'href="/o/{robin}/book"'.encode(), page)
        s, _, page = self.request('POST', '/play/garden', raw=urllib.parse.urlencode({'text': 'delvetalk garden plant\ncolour: amber\nseed: a guest bell', 'try': '1'}),
                                  headers={'Cookie': jar, 'Content-Type': FORM})
        self.assertIn(b'preview, nothing done', page)
        s, _, page = self.request('POST', '/play/garden', raw=urllib.parse.urlencode({'text': 'delvetalk garden plant\ncolour: amber\nseed: a guest bell'}),
                                  headers={'Cookie': jar, 'Content-Type': FORM})
        self.assertRegex(page.decode(), r'admitted garden v\d+, entry \d+')
        self.assertIn(robin.encode(), page)
        s, _, page = self.request('GET', f'/o/{robin}/book', headers={'Cookie': jar, 'Accept': 'text/html'})
        self.assertEqual(s, 200, page[:300])
        # Signing out forgets the cookie; the key is not revoked.
        s, _, page = self.request('GET', '/leave', headers={'Cookie': jar, 'Accept': 'text/html'})
        self.assertIn(b'<form method="post" action="/leave">', page)
        s, headers, page = self.request('POST', '/leave', headers={'Cookie': jar, 'Content-Type': FORM})
        self.assertEqual(s, 200)
        self.assertIn(b'Signed out', page)
        self.assertIn('Max-Age=0', dict(headers)['Set-Cookie'])
        self.assertEqual(self.request('GET', '/play/')[1] and dict(self.request('GET', '/play/')[1])['Location'], '/enter')
        # A returning guest signs in with the key.
        s, headers, _ = self.door({'credential': key})
        self.assertEqual((s, dict(headers)['Location']), (303, '/play/'))
        self.assertEqual(dict(headers)['Set-Cookie'].split(';')[0], jar)
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=key)[1]['handle'], robin)
        [row] = [r for r in self.front.identity.invitations() if r['name'] == robin]
        self.assertEqual(row['state'], 'accepted')  # the hand's invitations page: taken, and by what name

    def test_what_goes_wrong_at_the_door_is_said_in_plain_words_and_keeps_what_was_typed(self):
        code = self.front.identity.invite(None, 'open')['code']
        for form, words in (({'code': code}, 'lets you choose your name'), ({'code': code, 'name': 'Robin!'}, '“Robin!” cannot be one. “robin” is in the box instead'),
                            ({'code': code, 'name': '42!'}, 'starts with a lowercase letter'),
                            ({'code': 'dt_invite_' + 'x' * 32, 'name': 'wren'}, 'does not match any invitation'),
                            ({'credential': 'dt_agent_' + 'x' * 43}, 'does not open anything'), ({}, 'Type the code')):
            s, _, page = self.door(form)
            text = html.unescape(page.decode())
            self.assertIn(s, (400, 401))
            self.assertIn(words, text, form)
            self.assertTrue(text.startswith('<!doctype html>'))
            self.assertNotIn('{"', text)
            if form.get('code'):
                self.assertIn(f'value="{form["code"]}"', text)
        s, _, page = self.door({'code': code, 'name': f'wren-{self.c}'})
        self.assertEqual(s, 200)  # the code was unused through every mistake
        s, _, page = self.door({'code': code, 'name': f'wren-{self.c}'})
        self.assertIn('has been used already', html.unescape(page.decode()))
        named = self.front.identity.invite(f'kit-{self.c}', 'named')['code']
        s, _, page = self.door({'code': named})  # a code that names its guest skips the name
        self.assertIn(f'Welcome, kit-{self.c}'.encode(), page)

    def test_an_agent_comes_in_by_the_same_door_as_json(self):
        code = self.front.identity.invite(None, 'agent')['code']
        s, headers, body = self.request('POST', '/enter', raw=json.dumps({'code': code, 'name': f'bot-{self.c}'}), headers={'Accept': 'application/json'})
        got = json.loads(body)
        self.assertEqual((s, got['status'], got['handle']), (200, 'accepted', f'bot-{self.c}'))
        s, headers, body = self.request('POST', '/enter', raw=json.dumps({'credential': got['credential']}), headers={'Accept': 'application/json'})
        self.assertEqual((s, json.loads(body)['status']), (200, 'signedIn'))


class Quota(InTown):
    """The interpreter's hour on a serve of its own: Play's prose replies spend the same host's quota."""
    OPENER = 'did:plc:' + 'q' * 24

    def test_the_49th_prose_reply_in_an_hour_is_refused_by_quota_with_its_next_at(self):
        self.front.sleep = lambda seconds: None
        self.front.play_wait = 0  # one look at each turn: the 48 wait on hob, whom nobody runs, and the quota is the point
        for i in range(48):
            self.play('/play/', f'something green, number {i}')
        s, _, page = self.play('/play/', 'one more')
        self.assertIn('<p class="turn refused"><span class="stamp">§</span> refused quota'.encode(), page)
        self.assertIn(b'next at', page)


class StubHost:
    def __init__(self):
        self.ops = []

    def send(self, req):
        self.ops.append(req['op'])
        if req['op'] == 'bounds':
            return bounds()
        return {'status': 'viewed', 'version': 0} if req['op'] == 'world-view' else {'status': 'ok'}


class Concurrent(unittest.TestCase):
    N = 20

    def test_twenty_threads_verify_and_view_without_a_tear(self):
        did = lambda i: 'did:plc:' + f'{i:024d}'.translate({48: 'a', 49: 'b', 50: 'c', 51: 'd', 52: 'e', 53: 'f', 54: 'g', 55: 'h', 56: 'i', 57: 'j'})
        texts = {}

        def provider(method, url, headers, body):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            if 'resolveHandle' in url:
                return 200, json.dumps({'did': did(int(q['handle'][0].split('.')[0][1:]))}).encode()
            return 200, json.dumps({'uri': f"at://{q['repo'][0]}/town.delve.feed.post/3abc", 'cid': 'bafyx',
                                    'value': {'text': texts[q['repo'][0]]}}).encode()
        with tempfile.TemporaryDirectory() as tmp:
            host = StubHost()
            st = State(tmp, config=Config(trust_proxy=True))
            ident = identity.Identity(st, delve.Client(provider))
            front = Front(st, host, ident, ('127.0.0.1', 0))
            port = front.server_address[1]
            serve(front)
            errors, creds = [], {}

            def call(method, path, i, body=None, token=None):
                c = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
                h = {'X-Forwarded-For': f'10.0.0.{i}', **({'Authorization': 'Bearer ' + token} if token else {})}
                c.request(method, path, json.dumps(body) if body is not None else None, h)
                r = c.getresponse()
                return r.status, json.loads(r.read())

            def person(i):
                try:
                    handle = f'h{i}.delve.town'
                    s, ch = call('POST', '/AGENTS.md/challenge', i, {'handle': handle})
                    texts[did(i)] = ch['text']
                    s2, v = call('POST', '/AGENTS.md/verify', i, {'handle': handle, 'uri': f'at://{did(i)}/town.delve.feed.post/3abc'}, ch['credential'])
                    s3, w = call('GET', '/AGENTS.md/world/x', i, token=ch['credential'])
                    creds[i] = ch['credential']
                    assert (s, s2, s3, v['status'], w['status']) == (200, 200, 200, 'verified', 'viewed'), (s, s2, s3, v, w)
                except BaseException as e:
                    errors.append(repr(e))
            threads = [threading.Thread(target=person, args=(i,)) for i in range(self.N)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            front.shutdown()
            front.server_close()
            self.assertEqual(errors, [])
            self.assertEqual(len(creds), self.N)
            self.assertEqual([front.limited(c, count=False) for c in creds.values()], [1] * self.N)
            self.assertEqual(host.ops.count('world-arrive'), self.N)
            self.assertEqual(host.ops.count('world-view'), self.N)
            self.assertEqual(sorted(ident.authenticate(c)['did'] for c in creds.values()), sorted(did(i) for i in range(self.N)))


class Slow(unittest.TestCase):
    """Workers are bounded: one more connection is told busy."""
    def front(self, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        st = State(tmp.name)
        front = serve(Front(st, StubHost(), identity.Identity(st, delve.Client(None)), ('127.0.0.1', 0), **kw))
        self.addCleanup(front.server_close)
        self.addCleanup(front.shutdown)
        return front

    def test_workers_are_bounded_and_one_more_connection_is_told_busy(self):
        import socket
        front = self.front(workers=2)
        idle = [socket.create_connection(front.server_address) for _ in range(2)]
        for s in idle:
            self.addCleanup(s.close)
            s.sendall(b'GET / HTTP/1.1\r\n')
        time.sleep(0.3)
        c = http.client.HTTPConnection('127.0.0.1', front.server_address[1], timeout=5)
        c.request('GET', '/AGENTS.md')
        r = c.getresponse()
        self.assertEqual((r.status, json.loads(r.read())['class'], r.getheader('Retry-After')), (503, 'busy', '1'))
        for s in idle:
            s.close()
        time.sleep(0.3)
        c = http.client.HTTPConnection('127.0.0.1', front.server_address[1], timeout=5)
        c.request('GET', '/AGENTS.md')
        self.assertEqual(c.getresponse().status, 200)



class Cookie(unittest.TestCase):
    def test_the_session_cookie_is_secure_on_an_https_origin(self):
        from types import SimpleNamespace
        from transport.http import Handler
        cookie = lambda origin: Handler.login_cookie(SimpleNamespace(server=SimpleNamespace(origin=origin)), 'dt_agent_x')[0][1]
        self.assertIn('; Secure', cookie('https://gsb.fg-goose.online'))
        self.assertNotIn('Secure', cookie('http://127.0.0.1:8765'))  # a loopback test front, which a browser reaches over http

class SpeechSpans(unittest.TestCase):
    def test_an_indented_source_heredoc_keeps_two_definitions_separated_by_a_blank_line(self):
        from transport import pages
        spell = 'delvetalk workshop draft\n  source: <<END\n    def first() -> Nat: 1n\n\n    def second() -> Nat: 2n\n  END'
        card = 'Draft it:\n\n' + '\n'.join('  ' + line if line else '' for line in spell.split('\n')) + '\n\nOutside prose.'
        prose, suggestions = pages.speech(card)
        self.assertEqual(suggestions, [('Draft it', spell)])
        self.assertIn('Outside prose.', prose)

    def test_an_indented_fence_preserves_blank_lines_and_never_consumes_the_next_spell_or_margin_prose(self):
        from transport import pages
        spell = 'delvetalk workshop draft\n  source:\n  ```obend\n  ' + 'x' * 65536 + '\n\n  delvetalk literal text\n  » literal result\n  ```'
        card = '\n'.join('  ' + line if line else '' for line in spell.split('\n')) + '\n\n  delvetalk workshop ?\n» result\n\nMargin prose.'
        _, suggestions = pages.speech(card)
        self.assertEqual([s for _, s in suggestions], [spell, 'delvetalk workshop ?'])

if __name__ == '__main__':
    unittest.main()
