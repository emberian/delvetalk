import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests.test_turn_world import BINARY, counter_modules, nat, record
from transport import delve, identity
from transport.http import Front, Host

HANDLE = 'talkie.delve.town'
DID = 'did:plc:' + 'a' * 24
URI = f'at://{DID}/town.delve.feed.post/3abc'


class Provider:
    """Mocked PDS: resolves the handle, serves whatever proof text the test sets."""
    def __init__(self):
        self.text = None

    def __call__(self, method, url, headers, body):
        if 'resolveHandle' in url:
            return 200, json.dumps({'did': DID}).encode()
        return 200, json.dumps({'uri': URI, 'cid': 'bafyx', 'value': {'text': self.text}}).encode()


class HttpFront(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.provider = Provider()
        self.now = [1000.0]
        self.host = Host(str(Path(self.tmp.name) / 'world.journal'), BINARY)
        ident = identity.Identity(self.tmp.name, delve.Client(self.provider), clock=lambda: self.now[0])
        self.front = Front(('127.0.0.1', 0), self.host, ident, clock=lambda: self.now[0])
        self.port = self.front.server_address[1]
        threading.Thread(target=self.front.serve_forever, daemon=True).start()
        r = self.host.send({'op': 'world-create', 'principal': HANDLE, 'identity': 'mk', 'object': 'c1',
                            'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
        self.assertEqual(r['status'], 'created', r)

    def tearDown(self):
        self.front.shutdown()
        self.front.server_close()
        self.host.close()
        self.tmp.cleanup()

    def call(self, method, path, body=None, token=None, raw=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        payload = raw if raw is not None else (json.dumps(body) if body is not None else None)
        c.request(method, path, payload, headers)
        r = c.getresponse()
        data = r.read()
        c.close()
        try:
            return r.status, json.loads(data)
        except ValueError:
            return r.status, data.decode()

    def login(self):
        s, ch = self.call('POST', '/AGENTS.md/challenge', {'handle': HANDLE})
        self.assertEqual(s, 200, ch)
        self.provider.text = ch['text']
        s, v = self.call('POST', '/AGENTS.md/verify', {'handle': HANDLE, 'uri': URI})
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
        self.assertEqual(self.host.send({'op': 'world-receipt', 'principal': HANDLE, 'identity': 'f1'})['status'], 'receipt')
        self.assertNotEqual(self.host.send({'op': 'world-receipt', 'principal': 'ember', 'identity': 'f1'}).get('status'), 'receipt')
        self.assertNotEqual(self.host.send({'op': 'world-receipt', 'principal': HANDLE, 'identity': 'x'}).get('status'), 'receipt')

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


if __name__ == '__main__':
    unittest.main()
