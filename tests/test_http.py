import http.client
import json
import tempfile
import threading
import time
import unittest
import urllib.parse
from pathlib import Path

from tests.test_turn_world import BINARY, closure, counter_modules, label, nat, record
from tests.test_turn import PLANS, variant
from transport import delve, identity
from transport.http import Front, Heaps, Host

HANDLE = 'talkie.delve.town'
DID = 'did:plc:' + 'a' * 24
URI = f'at://{DID}/town.delve.feed.post/3abc'


PEOPLE = {HANDLE: DID, 'glm.delve.town': 'did:plc:' + 'b' * 24, 'mimo.delve.town': 'did:plc:' + 'c' * 24,
          'selene.delve.town': 'did:plc:' + 'd' * 24}


class Provider:
    """Mocked PDS: resolves known handles, serves whatever proof text the test sets per DID."""
    def __init__(self):
        self.texts = {}

    def __call__(self, method, url, headers, body):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if 'resolveHandle' in url:
            return 200, json.dumps({'did': PEOPLE[q['handle'][0]]}).encode()
        repo = q['repo'][0]
        return 200, json.dumps({'uri': f'at://{repo}/town.delve.feed.post/3abc', 'cid': 'bafyx',
                                'value': {'text': self.texts[repo]}}).encode()


class HttpFront(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.provider = Provider()
        self.now = [1000.0]
        self.host = Host(str(Path(self.tmp.name) / 'world.journal'), BINARY)
        ident = identity.Identity(self.tmp.name, delve.Client(self.provider), clock=lambda: self.now[0])
        self.front = Front(('127.0.0.1', 0), self.host, ident, clock=lambda: self.now[0],
                          heaps=Heaps(Path(self.tmp.name) / 'heaps', size=2, binary=BINARY))
        self.port = self.front.server_address[1]
        threading.Thread(target=self.front.serve_forever, daemon=True).start()
        r = self.host.send({'op': 'world-create', 'principal': HANDLE, 'identity': 'mk', 'object': 'c1',
                            'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
        self.assertEqual(r['status'], 'created', r)

    def tearDown(self):
        self.front.shutdown()
        self.front.server_close()
        self.front.heaps.close()
        self.front.repl.close()
        self.host.close()
        self.tmp.cleanup()

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
        return self.call('POST', '/AGENTS.md/world/c1/bump', {'argument': record(), 'intent': intent}, tok)

    def test_guide(self):
        s, text = self.call('GET', '/AGENTS.md')
        self.assertEqual(s, 200)
        self.assertIn('/AGENTS.md/challenge', text)
        self.assertNotIn('{{origin}}', text)

    def test_unknown_route_points_at_guide(self):
        s, body = self.call('GET', '/nope')
        self.assertEqual(s, 404)
        self.assertEqual(body['status'], 'error')
        self.assertIn('/AGENTS.md', body['message'])

    def test_full_journey(self):
        tok = self.login()
        s, v = self.call('GET', '/AGENTS.md/world/c1', token=tok)
        self.assertEqual((s, v['status'], v['version']), (200, 'viewed', 0))
        s, t = self.turn(tok, 'i1')
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        s, r = self.call('GET', '/AGENTS.md/receipt/i1', token=tok)
        self.assertEqual(s, 200)
        self.assertEqual(r['receipt'], t['receipt'])
        self.assertEqual(self.call('GET', '/AGENTS.md/world/c1', token=tok)[1]['version'], 1)
        self.assertEqual(self.call('GET', '/AGENTS.md/pending', token=tok)[0], 200)
        self.assertEqual(self.call('POST', '/AGENTS.md/deliver', {}, tok)[0], 200)

    def test_host_refusal_passes_through_verbatim(self):
        tok = self.login()
        s, v = self.call('GET', '/AGENTS.md/world/nope', token=tok)
        self.assertEqual(v, self.host.send({'op': 'world-view', 'principal': HANDLE, 'object': 'nope'}))
        s, e = self.call('POST', '/AGENTS.md/world/c1/bump', {'argument': 7, 'intent': 'bad'}, tok)
        self.assertEqual(s, 400)
        self.assertEqual(e, self.host.send({'op': 'world-turn', 'principal': HANDLE, 'object': 'c1',
                                            'method': 'bump', 'argument': 7, 'identity': 'bad'}))

    def test_principal_cannot_be_forged_through_the_body(self):
        tok = self.login()
        s, t = self.call('POST', '/AGENTS.md/world/c1/bump',
                         {'argument': record(), 'intent': 'f1', 'principal': 'ember', 'identity': 'x'}, tok)
        self.assertEqual(t['status'], 'admitted', t)
        self.assertEqual(self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': 'f1'})['status'], 'receipt')
        self.assertNotEqual(self.host.send({'op': 'world-receipt', 'principal': 'ember', 'identity': 'f1'}).get('status'), 'receipt')
        self.assertNotEqual(self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': 'x'}).get('status'), 'receipt')

    def test_unverified_credential_is_401(self):
        s, ch = self.call('POST', '/AGENTS.md/challenge', {'handle': HANDLE})
        for tok in (ch['credential'], 'dt_agent_' + 'A' * 43, None):
            self.assertEqual(self.call('GET', '/AGENTS.md/world/c1', token=tok)[0], 401)

    def test_rate_limit_33rd_request(self):
        tok = self.login()
        codes = [self.call('GET', '/AGENTS.md/pending', token=tok)[0] for _ in range(33)]
        self.assertEqual(codes, [200] * 32 + [429])
        self.now[0] += 61
        self.assertEqual(self.call('GET', '/AGENTS.md/pending', token=tok)[0], 200)

    def test_body_limit(self):
        tok = self.login()
        s, e = self.call('POST', '/AGENTS.md/world/c1/bump', token=tok, raw=b'{"intent":"' + b'x' * (65 * 1024) + b'"}')
        self.assertEqual(s, 413)
        self.assertEqual(self.call('POST', '/AGENTS.md/world/c1/bump', token=tok, raw=b'{nope')[0], 400)

    def test_host_death_is_survived_with_state_intact(self):
        tok = self.login()
        for i in range(2):
            self.assertEqual(self.turn(tok, f'd{i}')[1]['status'], 'admitted')
        self.host.proc.kill()
        self.host.proc.wait()
        s, v = self.call('GET', '/AGENTS.md/world/c1', token=tok)
        self.assertEqual((s, v['status'], v['version']), (200, 'viewed', 2), v)
        self.assertEqual(self.turn(tok, 'd1')[1]['status'], 'admitted')  # retried identity: original receipt
        self.assertEqual(self.call('GET', '/AGENTS.md/world/c1', token=tok)[1]['version'], 2)

    def test_two_hundred_turns_under_ten_seconds(self):
        tok = self.login()
        t0 = time.time()
        for i in range(200):
            self.now[0] += 3  # stay under the rate limit; the clock is the limiter's, not the host's
            self.assertEqual(self.turn(tok, f'm{i}')[1]['status'], 'admitted')
        took = time.time() - t0
        self.assertLess(took, 10)
        self.assertEqual(self.call('GET', '/AGENTS.md/world/c1', token=tok)[1]['version'], 200)

    # ---- REPL

    BIND = {'object': 'c1', 'intent': 'repl-1', 'roots': [{'object': 'c1', 'version': 0}]}

    def repl(self, tok, **body):
        return self.call('POST', '/AGENTS.md/repl', body, tok)

    def test_repl_runs_a_pure_entry_and_passes_errors_through(self):
        tok = self.login()
        mods = [{'name': 'Package', 'source': PLANS}]
        s, r = self.repl(tok, modules=mods, entry='pure', arguments=[nat(1)])
        self.assertEqual((s, r['status'], r['value']), (200, 'finished', nat(2)), r)
        s, e = self.repl(tok, modules=mods, entry='nope')
        self.assertEqual((s, e['status']), (400, 'error'))
        self.assertIn('missing selected entry', e['message'])
        s, e = self.repl(tok, modules=[{'name': 'Big', 'source': 'x' * 8193}], entry='pure')
        self.assertEqual(s, 413)

    def test_repl_runs_counter_bump_as_an_activity(self):
        tok = self.login()
        context = record(world={'tag': 'label', 'value': ''}, object={'tag': 'label', 'value': 'c1'},
                         principal={'tag': 'label', 'value': HANDLE}, inputOrigin=record(
                             kind={'tag': 'label', 'value': 'request'}, object={'tag': 'label', 'value': ''},
                             command={'tag': 'label', 'value': ''}, program={'tag': 'label', 'value': ''},
                             immediatelyPrevious={'tag': 'boolean', 'value': False}))
        s, r = self.repl(tok, modules=closure('Counter'), entry='bump', turn=True, **self.BIND,
                         arguments=[record(count=nat(2)), context])
        self.assertEqual((s, r['status']), (200, 'yielded'), r)

    def test_repl_activity_round_trip_with_checkpoint(self):
        tok = self.login()
        mods = [{'name': 'Package', 'source': PLANS}]
        s, y = self.repl(tok, modules=mods, entry='bump', turn=True, arguments=[nat(3)], **self.BIND)
        self.assertEqual((s, y['status']), (200, 'yielded'), y)
        s, done = self.repl(tok, modules=mods, entry='bump', checkpoint=y['checkpoint'], response=variant('written'), **self.BIND)
        self.assertEqual((s, done['status'], done['value']), (200, 'finished', nat(4)), done)

    # ---- heaps

    def heap_create(self, tok, name='h1'):
        return self.call('POST', '/AGENTS.md/heap/objects', {'object': name, 'modules': counter_modules(), 'entry': 'initial',
                                                             'seed': record(count=nat(0)), 'intent': 'mk-' + name}, tok)

    def test_a_heap_is_private_and_missing_is_404_not_403(self):
        a, b = self.login(), self.login('glm.delve.town')
        s, r = self.heap_create(a)
        self.assertEqual((s, r['status']), (200, 'created'), r)
        s, t = self.call('POST', '/AGENTS.md/heap/world/h1/bump', {'argument': record(), 'intent': 't1'}, a)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        self.assertEqual(self.call('GET', '/AGENTS.md/heap/world/h1', token=a)[1]['version'], 1)
        s, v = self.call('GET', '/AGENTS.md/heap/world/h1', token=b)
        self.assertEqual((s, v['status']), (404, 'unknown'))
        self.assertEqual(self.call('GET', '/AGENTS.md/world/h1', token=a)[0], 404)  # the shared world never sees it
        self.assertEqual(self.call('GET', '/AGENTS.md/heap/receipt/t1', token=b)[1].get('status'), 'unknown')

    def test_pool_eviction_reopens_by_replay(self):
        names = ['glm.delve.town', 'mimo.delve.town', 'selene.delve.town']
        toks = [self.login(h) for h in names]
        for i, t in enumerate(toks[:2]):
            self.heap_create(t, 'h')
            self.call('POST', '/AGENTS.md/heap/world/h/bump', {'argument': record(), 'intent': 'b'}, t)
        pool = self.front.heaps.pool
        first = pool[PEOPLE[names[0]]]
        self.assertEqual(self.call('GET', '/AGENTS.md/heap/world/h', token=toks[2])[0], 404)  # third heap evicts the first
        self.assertNotIn(PEOPLE[names[0]], pool)
        self.assertIsNone(first.proc)
        self.assertEqual(len(pool), 2)
        s, v = self.call('GET', '/AGENTS.md/heap/world/h', token=toks[0])
        self.assertEqual((s, v['version']), (200, 1), v)

    # ---- me, revoke

    def test_me_and_revoke(self):
        tok = self.login()
        self.heap_create(tok)
        s, me = self.call('GET', '/AGENTS.md/me', token=tok)
        self.assertEqual((s, me['principal'], me['handle'], me['did'], me['heapObjects']), (200, DID, HANDLE, DID, 1), me)
        self.assertEqual(me['verified'], 1000.0)
        self.assertEqual(me['rateLimit'], {'limit': 32, 'windowSeconds': 60, 'remaining': 30})
        self.assertEqual(self.call('POST', '/AGENTS.md/revoke', {}, tok)[1], {'status': 'revoked'})
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=tok)[0], 401)

    # ---- human pages

    def test_html_card_and_spell_form(self):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-garden', 'object': 'garden',
                            'modules': closure('Garden'), 'entry': 'initial', 'seed': record(planted=nat(2), policy=record(world=label(""), object=label("")))})
        self.assertEqual(r['status'], 'created', r)
        s, headers, body = self.request('GET', '/')
        self.assertEqual(s, 200)
        self.assertIn(b'Log in', body)
        s, headers, _ = self.request('POST', '/AGENTS.md/challenge', raw='handle=' + HANDLE,
                                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
        cookie = [v for k, v in headers if k == 'Set-Cookie'][0].split(';')[0]
        self.assertTrue(cookie.startswith('dt_credential=dt_agent_'))
        ch = self.front.identity.db.execute('SELECT text FROM challenges').fetchone()['text']
        self.provider.texts[DID] = ch
        s, headers, _ = self.request('POST', '/AGENTS.md/verify', raw=f'handle={HANDLE}&uri={urllib.parse.quote(URI)}',
                                     headers={'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': cookie})
        self.assertEqual(s, 200)
        self.assertIn(cookie, [v for k, v in headers if k == 'Set-Cookie'][0])
        s, _, page = self.request('GET', '/o/garden', headers={'Cookie': cookie})
        self.assertEqual(s, 200)
        self.assertIn(b'The Night Garden: 2 planted', page)
        self.assertIn(b'prefers-color-scheme', self.request('GET', '/static/style.css')[2])
        before = self.host.send({'op': 'world-status'})['height']
        s, _, page = self.request('POST', '/o/garden/spell', raw='text=' + urllib.parse.quote('delvetalk garden plant'),
                                  headers={'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': cookie})
        self.assertEqual(s, 200)
        self.assertGreater(self.host.send({'op': 'world-status'})['height'], before)
        self.assertIn(b'Result', page)
        self.assertEqual(self.request('GET', '/o/nowhere')[0], 404)
        self.assertEqual(self.request('POST', '/o/garden/spell', raw='text=x',
                                      headers={'Content-Type': 'application/x-www-form-urlencoded'})[0], 401)

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


if __name__ == '__main__':
    unittest.main()
