"""The agent API at /AGENTS.md over a real `serve`: proof-of-control login, turns and receipts, the
REPL, private heaps, pages for people, limits.

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
from tests.host import ServeCase, serve, served
from transport.host import HostClient
from transport.http import CATALOGUE, AccessLog, Front

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

    @classmethod
    def setUpClass(cls):
        if not cls.fresh_world:
            super().setUpClass()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        if self.fresh_world:
            from deploy.serve import LIBRARY
            self.state_dir = tempfile.TemporaryDirectory()
            self.addCleanup(self.state_dir.cleanup)
            self.server = served(self.state_dir.name, opener=self.OPENER, library=LIBRARY)
            self.addCleanup(self.server.stop)
            self.socket, self.root = self.server.sock, HostClient(self.server.root)
        self.provider = Provider()
        self.now = [1000.0]
        self.host = HostClient(self.socket)  # a test may replace its send
        ident = identity.Identity(self.tmp.name, delve.Client(self.provider), clock=lambda: self.now[0])
        self.outbox = Path(self.tmp.name) / 'outbox'  # the hand's: an HTTP turn that writes a public object drafts here
        self.front = serve(Front(('127.0.0.1', 0), self.host, ident, clock=lambda: self.now[0],
                                 heaps=Path(self.state_dir.name) / 'heaps', repl=HostClient(self.socket, stateless=True), outbox=self.outbox))
        self.addCleanup(self.front.server_close)
        self.addCleanup(self.front.shutdown)
        self.port = self.front.server_address[1]
        type(self).made += 1
        self.c = 'c%d' % self.made
        r = self.host.send({'op': 'world-create', 'principal': HANDLE, 'identity': 'mk-' + self.c, 'object': self.c,
                            'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
        self.assertEqual(r['status'], 'created', r)

    def heap_create(self, tok, name='h1'):
        # A bare counter: Counter's closure with Card and Spell (about 67 KB) exceeds the front's 64 KiB body.
        return self.call('POST', '/AGENTS.md/heap/objects', {'object': name, 'modules': closure('World') + [{'name': 'Counter', 'source': REPL_COUNTER}], 'entry': 'initial',
                                                             'seed': record(count=nat(0)), 'intent': 'mk-' + name}, tok)

    @property
    def BIND(self):
        return {'object': self.c, 'intent': 'repl-1', 'roots': [{'object': self.c, 'version': 0}]}

    def request(self, method, path, body=None, token=None, raw=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        headers = dict(headers or {})
        if token:
            headers['Authorization'] = 'Bearer ' + token
        payload = raw if raw is not None else (json.dumps(body) if body is not None else None)
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
        s, v = self.call('POST', '/AGENTS.md/verify', {'handle': handle, 'uri': f'at://{did}/town.delve.feed.post/3abc'})
        self.assertEqual((s, v['status']), (200, 'verified'), v)
        return ch['credential']

    def turn(self, tok, intent):
        return self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': record(), 'intent': intent}, tok)


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
        self.heap_create(tok)
        s, me = self.call('GET', '/AGENTS.md/me', token=tok)
        self.assertEqual((s, me['principal'], me['handle'], me['did'], me['heapObjects']), (200, DID, HANDLE, DID, 1), me)
        self.assertEqual(me['verified'], 1000.0)
        self.assertEqual(me['rateLimit'], {'limit': 32, 'windowSeconds': 60, 'remaining': 30})
        does = next(e['does'] for e in CATALOGUE if e['name'] == 'me')
        self.assertEqual([k for k in bare(me) if f'`{k}`' not in does and k != 'status'], [])  # the catalogue names what /me answers
        self.assertEqual(bare(self.call('POST', '/AGENTS.md/revoke', {}, tok)[1]), {'status': 'revoked'})
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=tok)[0], 401)


class Claim(FrontCase):
    """Claiming a handle in a browser: the word, then one button."""
    def word_page(self):
        s, headers, page = self.request('POST', '/AGENTS.md/challenge', raw='handle=' + HANDLE, headers={'Content-Type': FORM, 'Accept': 'text/html'})
        self.assertEqual(s, 200)
        return [v for k, v in headers if k == 'Set-Cookie'][0].split(';')[0], page.decode()

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
        self.assertIn(b'ENTER THE WORLD', self.request('GET', '/', headers={'Cookie': cookie, 'Accept': 'text/html'})[2])  # logged in
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
        self.front.access = AccessLog(log)
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
        self.assertEqual((me[3], me[5]), ('200', DID))
        self.assertGreater(int(me[4]), 50)
        self.assertEqual([l[3] for l in lines if l[2] == '/AGENTS.md/world/nowhere'], [str(s)])
        text = log.read_text()
        self.assertNotIn(tok, text)
        self.assertNotIn('secret-query', text)
        self.assertNotIn('Bearer', text)
        self.assertEqual(len(lines), 2 + 2 + 1, lines)  # api, challenge, verify, me, nowhere


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

    def test_a_turn_from_the_play_page_is_drafted_too(self):
        tok = self.login()
        s, _, _ = self.request('POST', f'/play/{self.c}', raw=b'method=bump', headers={'Cookie': f'dt_credential={tok}', 'Content-Type': FORM})
        self.assertEqual(s, 200)
        self.assertEqual([d['object'] for d in self.drafts()], [self.c])

    def test_a_private_object_a_refusal_and_a_heap_draft_nothing(self):
        tok = self.login()
        r = self.host.send({'op': 'world-create', 'principal': DID, 'identity': 'mk-p-' + self.c, 'object': 'p-' + self.c, 'modules': counter_modules(),
                            'entry': 'initial', 'seed': record(count=nat(0)), 'read': {'principals': [DID]}})
        self.assertEqual(r['status'], 'created', r)
        s, t = self.call('POST', f'/AGENTS.md/world/p-{self.c}/bump', {'argument': record(), 'intent': 'priv-1'}, tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        s, e = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': 7, 'intent': 'bad-1'}, tok)
        self.assertEqual(s, 400, e)
        self.assertEqual(self.heap_create(tok)[1]['status'], 'created')
        s, t = self.call('POST', '/AGENTS.md/heap/world/h1/bump', {'argument': record(), 'intent': 'heap-1'}, tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        self.assertEqual(self.drafts(), [])


class Forms(FrontCase):
    def test_a_browser_form_keeps_a_deliberately_blank_field_for_the_host(self):
        tok = self.login()
        real, sent = self.host.send, []
        self.host.send = lambda req: (sent.append(req) if req['op'] == 'world-turn' else None) or real(req)
        self.request('POST', f'/play/{self.c}', raw=b'method=bump&migration=&note=x',
                     headers={'Cookie': f'dt_credential={tok}', 'Content-Type': 'application/x-www-form-urlencoded'})
        (turn,) = sent
        self.assertEqual({f['name']: f['value']['value'] for f in turn['argument']['fields']}, {'migration': '', 'note': 'x'})


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


class Repl(FrontCase):
    def repl(self, tok, **body):
        return self.call('POST', '/AGENTS.md/repl', body, tok)

    def test_repl_runs_a_pure_entry_and_passes_errors_through(self):
        tok = self.login()
        mods = closure('World') + [{'name': 'Package', 'source': PLANS}]
        s, r = self.repl(tok, modules=mods, entry='pure', arguments=[nat(1)])
        self.assertEqual((s, r['status'], r['value']), (200, 'finished', nat(2)), r)
        s, e = self.repl(tok, modules=mods, entry='nope')
        self.assertEqual((s, e['status']), (400, 'error'))
        self.assertIn('missing selected entry', e['message'])
        s, e = self.repl(tok, modules=[{'name': 'Big', 'source': 'x' * 140000}], entry='pure')
        self.assertEqual(s, 413)


    def test_a_checkpoint_from_before_the_host_restarted_is_repl_restarted_never_a_500(self):
        tok = self.login()
        mods = closure('World') + [{'name': 'Package', 'source': PLANS}]
        s, y = self.repl(tok, modules=mods, entry='bump', turn=True, arguments=[nat(3)], **self.BIND)
        self.assertEqual((s, y['status']), (200, 'yielded'), y)
        from deploy.serve import LIBRARY
        self.server.stop()  # a restart of serve: a new stateless session, which issued nothing
        type(self).server = served(self.state_dir.name, opener=self.OPENER, library=LIBRARY)
        type(self).addClassCleanup(type(self).server.stop)
        s, e = self.repl(tok, modules=mods, entry='bump', checkpoint=y['checkpoint'], response=variant('written'), **self.BIND)
        self.assertEqual((s, e['class'], e['message'], e['_links']['repl']), (409, 'replRestarted', 'the REPL restarted; start the module again',
                                                                              {'href': '/AGENTS.md/repl'}), e)

    def test_repl_imports_the_library_by_name_and_starts_an_activity_from_its_type(self):
        tok = self.login()
        context = record(world=label(''), object=label(self.c), principal=label(DID), handle=label(''), caller=label(''),
                         intent=label('repl-2'), height=nat(0), clock=nat(0),
                         inputOrigin=record(kind=label('request'), object=label(''), command=label(''), program=label(''),
                                            immediatelyPrevious={'tag': 'boolean', 'value': False}, post={'tag': 'label', 'value': ''}))
        s, y = self.repl(tok, source=REPL_COUNTER, entry='bump', arguments=[record(count=nat(2)), context],
                         object=self.c, intent='repl-2', roots=[{'object': self.c, 'version': 0}])
        self.assertEqual((s, y['status']), (200, 'yielded'), y)
        self.assertIsInstance(y['checkpoint']['tokens'], list)  # the REPL's checkpoint goes back whole, to resume
        s, done = self.repl(tok, source=REPL_COUNTER, entry='bump', checkpoint=y['checkpoint'], response=variant('written'),
                            object=self.c, intent='repl-2', roots=[{'object': self.c, 'version': 0}])
        self.assertEqual((s, done['status'], done['value']), (200, 'finished', nat(3)), done)


    def test_a_stale_library_pin_is_re_read_once_and_the_compile_goes_through(self):
        tok = self.login()
        self.front.library = 'bafyreistale'
        s, y = self.repl(tok, source=REPL_COUNTER, entry='bump', arguments=[record(count=nat(2))], object=self.c, intent='repl-4',
                         roots=[{'object': self.c, 'version': 0}])
        self.assertEqual((s, y['status']), (200, 'yielded'), y)
        self.assertNotEqual(self.front.library, 'bafyreistale')
        self.front.hostd_pid = -1  # a changed pid is re-read before the request
        self.front.library = 'bafyreistale'
        s, y = self.repl(tok, source=REPL_COUNTER, entry='bump', arguments=[record(count=nat(2))], object=self.c, intent='repl-5',
                         roots=[{'object': self.c, 'version': 0}])
        self.assertEqual((s, y['status']), (200, 'yielded'), y)

    def test_check_and_compile_refusals_carry_the_hosts_hint(self):
        tok = self.login()
        habit = 'edition ObjectiveBend 1\nsum Light:\n  on: {}\n  off: {}\ndef flip(l: Light) -> Nat:\n  match l:\n    on(_) -> 1n\n    off(_) -> 0n\n'
        s, c = self.call('POST', '/AGENTS.md/check', {'source': habit, 'entry': 'flip'}, tok)
        self.assertEqual((s, c['status']), (200, 'refused'), c)
        self.assertIn('case label(x): body', c['hint'])
        s, e = self.repl(tok, source=habit, entry='flip')
        self.assertEqual((s, e['status']), (400, 'error'), e)
        self.assertIn('case label(x): body', e['hint'])
        self.assertIn('stage', e)
        s, ok = self.call('POST', '/AGENTS.md/check', {'source': REPL_COUNTER, 'entry': 'bump'}, tok)
        self.assertEqual((s, ok['status']), (200, 'checked'), ok)


class Heaps(FrontCase):
    def test_a_created_reply_shows_one_hash_by_default_and_all_of_them_with_full(self):
        import re
        tok = self.login()
        body = {'intent': 'mk-hash', 'object': 'hash1', 'modules': [{'name': 'Tally', 'source': REPL_COUNTER}], 'entry': 'initial', 'seed': {'count': 1}}
        s, _, raw = self.request('POST', '/AGENTS.md/heap/objects', body, tok)
        self.assertEqual(s, 200, raw)
        self.assertEqual(re.findall(rb'bafy\w+', raw), [json.loads(raw)['receipt']['hash'].encode()], raw)
        body['intent'], body['object'] = 'mk-hash-2', 'hash2'
        s, _, raw = self.request('POST', '/AGENTS.md/heap/objects?full=1', body, tok)
        self.assertGreater(len(re.findall(rb'bafy\w+', raw)), 3)
        s, v = self.call('GET', '/AGENTS.md/heap/world/hash1', token=tok)
        self.assertNotIn('pin', v)
        self.assertIn('pin', self.call('GET', '/AGENTS.md/heap/world/hash1/source', token=tok)[1])

    def test_a_heap_object_no_spell_can_address_is_refused_before_it_is_created(self):
        tok = self.login()
        for name in ('coin box', 'c' * 129):  # a space splits the spell's card from its action; past 128 bytes no card is read
            s, e = self.heap_create(tok, name)
            self.assertEqual((s, e['class']), (400, 'unspellable'), e)
            self.assertIn(f'delvetalk {name} ?', e['message'])
        self.assertEqual(self.call('GET', '/AGENTS.md/heap/world/coin%20box', token=tok)[0], 404)
        self.assertEqual(self.heap_create(tok, 'Coin_box')[0], 200)  # one rule names objects and spell cards


    def test_a_heap_is_private_and_missing_is_404_not_403(self):
        a, b = self.login(), self.login('glm.delve.town')
        s, r = self.heap_create(a)
        self.assertEqual((s, r['status']), (200, 'created'), r)
        s, t = self.call('POST', '/AGENTS.md/heap/world/h1/bump', {'argument': record(), 'intent': 't1'}, a)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        self.assertEqual(self.call('GET', '/AGENTS.md/heap/world/h1', token=a)[1]['version'], 1)
        s, v = self.call('GET', '/AGENTS.md/heap/world/h1', token=b)
        self.assertEqual((s, v['status'], v['class']), (404, 'refused', 'unknown'))
        self.assertEqual(self.call('GET', '/AGENTS.md/world/h1', token=a)[0], 404)  # the shared world never sees it
        self.assertEqual(self.call('GET', '/AGENTS.md/heap/receipt/t1', token=b)[1].get('class'), 'unknown')

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


FORM = 'application/x-www-form-urlencoded'


def browser_login(case, handle=HANDLE):
    """The login page's two forms, as a browser sends them: the challenge sets the session cookie, verify keeps it."""
    s, headers, _ = case.request('POST', '/AGENTS.md/challenge', raw='handle=' + handle, headers={'Content-Type': FORM})
    cookie = [v for k, v in headers if k == 'Set-Cookie'][0].split(';')[0]
    case.assertTrue(cookie.startswith('dt_credential=dt_agent_'))
    did = PEOPLE[handle]
    case.provider.texts[did] = case.front.identity.db.execute('SELECT text FROM challenges WHERE handle = ? ORDER BY created DESC', (handle,)).fetchone()['text']
    s, headers, _ = case.request('POST', '/AGENTS.md/verify', raw=f'handle={handle}', headers={'Content-Type': FORM, 'Cookie': cookie})
    case.assertEqual(s, 200)
    case.assertIn(cookie, [v for k, v in headers if k == 'Set-Cookie'][0])
    return cookie


class Play(FrontCase):
    """/play/ against the genesis town: the directory, the garden and its interpreter, as a verified browser sees them."""
    OPENER = 'did:plc:' + 'e' * 24

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from deploy import genesis
        made, refusal = genesis.run(cls.root, cls.OPENER)
        assert refusal is None, refusal

    def setUp(self):
        super().setUp()
        self.cookie = browser_login(self)

    def play(self, path, text=None, cookie=True):
        self.now[0] += 3  # under the per-credential rate
        headers = {'Cookie': self.cookie} if cookie else {}
        if text is None:
            return self.request('GET', path, headers=headers)
        return self.request('POST', path, raw='text=' + urllib.parse.quote(text), headers={**headers, 'Content-Type': FORM})

    def answer(self, spell):
        """The town's interpreter, by hand: the one pending request on the garden, answered with a spell."""
        for _ in range(300):
            pending = [p for p in self.host.send({'op': 'world-interpretations'}).get('pending') or [] if p['object'] == 'garden']
            if pending:
                break
            time.sleep(0.1)
        r = self.host.send({'op': 'world-interpretation', 'id': pending[-1]['id'],
                            'reply': {'status': 'replied', 'model': 'claude-haiku-5-5', 'json': None, 'raw': spell}})
        self.assertEqual(r['status'], 'interpreted', r)

    def test_without_the_session_cookie_play_redirects_to_the_login_page(self):
        for method_text in (None, 'delvetalk garden plant'):
            s, headers, _ = self.play('/play/', method_text, cookie=False)
            self.assertEqual((s, dict(headers)['Location']), (303, '/'))
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
                 'directory': self.play('/play/')[2], 'style': self.request('GET', '/style/')[2],
                 'the word': self.request('POST', '/AGENTS.md/challenge', raw='handle=' + HANDLE, headers={'Content-Type': FORM, 'Accept': 'text/html'})[2],
                 'a refusal': self.request('GET', '/o/nowhere', headers={'Accept': 'text/html'})[2]}
        for name, page in pages.items():
            self.assertIsNone(self.BANNED.search(self.words(page)), (name, self.BANNED.search(self.words(page))))
        self.assertIn('every thing a card, every reply a receipt', self.words(pages['home']))
        self.assertRegex(self.words(pages['home, logged in']), r'entry \d+')  # the shelf mark
        self.assertRegex(self.words(pages['home, logged in']), r'\d+ cards')
        self.assertIn('Receipts', self.words(pages['object']))


    def test_a_refused_receipt_with_no_roots_answers_on_the_receipt_turn_and_play_routes(self):
        """A spell with colour: gold, an undeclared method, a non-owner `directory add`: refused before any root was read."""
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
        self.assertIn(b'refused badValue: colour is one of: amber, violet, silver', page)

    def test_plant_by_spell_and_read_the_receipt(self):
        s, _, page = self.play('/play/garden', 'delvetalk garden plant\ncolour: amber\nseed: a bell for lost moths')
        self.assertEqual(s, 200, page)
        line = re.search(rb'admitted garden v(\d+), entry (\d+), receipt ([a-z-]+)', page)
        self.assertIsNotNone(line, page)
        self.assertIn(b', at garden/bell/', page)
        tok = self.cookie.split('=', 1)[1]  # the session is the credential: the agent API reads the same receipt
        s, r = self.call('GET', '/AGENTS.md/receipt/' + line[3].decode(), token=tok)
        self.assertEqual((s, r['receipt']['height']), (200, int(line[2])), r)

    def test_plant_by_prose_shows_the_interpreters_offer(self):
        out = {}
        t = threading.Thread(target=lambda: out.update(page=self.play('/play/garden', 'please plant me something violet for the owls')[2]))
        t.start()
        self.answer('delvetalk garden plant\nseed: a bell for the owls\ncolour: violet')
        t.join(60)
        self.assertIn(b'suspended, entry', out['page'])
        self.assertIn(b'a bell for the owls', out['page'])  # the interpreter's proposal, as the offer to this turn

    def test_a_suspended_turn_is_a_line_under_a_kilobyte_and_its_full_reply_elides_the_blocks(self):
        tok = self.cookie.split('=', 1)[1]
        self.front.sleep = lambda seconds: None
        s, t = self.call('POST', '/AGENTS.md/world/garden/receive', {'intent': 'wait-1', 'spell': 'something green perhaps'}, tok)
        self.assertEqual((s, t['status']), (200, 'suspended'), t)
        self.assertLess(len(json.dumps(t)), 1024, t)
        self.assertTrue(t['line'].startswith('… suspended, entry '), t['line'])
        s, whole = self.call('GET', '/AGENTS.md/receipt/' + t['receipt']['slug'], token=tok)
        self.assertNotIn('"blocks": [', json.dumps(whole))  # the receipt's blocks are counted, not shown
        self.answer('delvetalk garden plant\nseed: a bell\ncolour: violet')  # settle the pending interpretation for the next test


    def test_the_49th_prose_reply_in_an_hour_is_refused_by_quota_with_its_next_at(self):
        self.front.sleep = lambda seconds: None
        for i in range(48):
            self.play('/play/garden', f'something green, number {i}')
        s, _, page = self.play('/play/garden', 'one more')
        self.assertIn('<span class="stamp">§</span><span class="line">refused quota'.encode(), page)
        self.assertIn(b'next at', page)


class StubHost:
    def __init__(self):
        self.ops = []

    def send(self, req):
        self.ops.append(req['op'])
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
            ident = identity.Identity(tmp, delve.Client(provider))
            front = Front(('127.0.0.1', 0), host, ident, trust_proxy=True)
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
                    s2, v = call('POST', '/AGENTS.md/verify', i, {'handle': handle, 'uri': f'at://{did(i)}/town.delve.feed.post/3abc'})
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
            self.assertEqual([len(front.used(c)) for c in creds.values()], [1] * self.N)
            self.assertEqual(host.ops.count('world-arrive'), self.N)
            self.assertEqual(host.ops.count('world-view'), self.N)
            self.assertEqual(sorted(ident.authenticate(c)['did'] for c in creds.values()), sorted(did(i) for i in range(self.N)))


class Slow(unittest.TestCase):
    """Workers are bounded: one more connection is told busy."""
    def front(self, **kw):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        front = serve(Front(('127.0.0.1', 0), StubHost(), identity.Identity(tmp.name, delve.Client(None)), **kw))
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


if __name__ == '__main__':
    unittest.main()
