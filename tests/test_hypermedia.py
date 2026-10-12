"""A stranger acts from the replies alone: every JSON reply carries `_links`, `_actions` are projected from
the host's method table and forms, every error is a named envelope, and the front survives bursts,
stalls and malformed input.

Evidence for FOUNDATION §7 (layer: transport).

The front's controls: `_links` on every JSON reply, `_actions` projected from the host's method table and forms.
"""
import http.client
import json
import random
import re
import socket
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

from tests.test_chain import town_garden
from tests.test_http import PEOPLE, REPL_COUNTER, FrontCase, StubHost
import transport.http
from transport.state import State
from transport import delve, identity
from transport.host import HostClient
from transport.http import CATALOGUE, ERRORS, EXAMPLES, GUIDE, REFUSALS, Front
from tests.bend import closure
from tests.host import bounds

LAWFUL = REPL_COUNTER + 'law nobody "only ember writes it": request.kind == 0 implies request.subject == "ember"\n'


def fill(spell):
    """Plain values for a spell template's fields, as any client would read them: a choice's first word, a natural's minimum."""
    values = {}
    for name, shown in re.findall(r'^(\w+): (.+)$', spell.partition('\n')[2], re.M):
        values[name] = re.split(r', ', shown[len('one of '):])[0] if shown.startswith('one of ') else \
            int(re.search(r'(\d+)\.\.', shown)[1]) if shown.startswith('<natural') else f"a {name} for strangers"
    return values


PURE = 'edition ObjectiveBend 1\ndef twice(n: Nat) -> Nat:\n  n + n\n'


def walk(call, handle, prove, module):
    """A stranger with only the catalogue and the controls in replies: challenge, verify, find something to plant in,
    plant, read the receipt by its slug, open a scratch world, make a thing in it and run it, run a REPL entry. `call(method, href, body,
    token)` -> (status, reply); `prove(text)` posts the challenge and returns the post's URI; `module` is the stranger's
    own Bend (a State with a `count` and a `bump` method). -> what it reached."""
    got = {}
    api = call('GET', '/AGENTS.md/api', None, None)[1]
    routes = {r['name']: r for r in api['routes']}
    ch = call('POST', routes['challenge']['href'], {'handle': handle}, None)[1]
    tok = ch['credential']
    v = call('POST', ch['_links']['verify']['href'], {'handle': handle, 'uri': prove(ch['text'])}, tok)[1]
    listing = call('GET', v['_links']['world']['href'], None, tok)[1]
    item = [i for i in listing['_links']['item'] if 'plant' in i.get('actions', ())][0]  # the listing names each object's methods
    spell = call('GET', item['href'], None, tok)[1]['_actions']['plant']
    planted = call('POST', f"{item['href']}/plant", {'intent': 'stranger-plant', 'fields': fill(spell)}, tok)[1]
    got['planted'] = (planted['status'], [c['name'] for c in planted['_links'].get('created', [])])
    receipt = call('GET', planted['_links']['receipt']['href'], None, tok)[1]
    got['receipt'] = (receipt['status'], receipt['receipt']['slug'] == planted['receipt']['slug'])
    opened = call('POST', routes['scratch']['href'], {'name': 'try'}, tok)[1]
    made = call('POST', opened['_links']['objects']['href'], {'intent': 'stranger-make', 'object': 'mine', 'entry': 'initial', 'source': module, 'seed': {}}, tok)[1]
    mine = call('GET', made['_links']['object']['href'], None, tok)[1]
    assert 'bump' in mine['_actions'], mine
    bumped = call('POST', mine['_links']['object']['href'] + '/bump', {'intent': 'stranger-bump', 'fields': {}}, tok)[1]
    result = call('GET', bumped['_links']['receipt']['href'], None, tok)[1]['receipt']['result']
    got['scratch'] = (made['status'], bumped['status'], result)
    ran = call('POST', routes['repl']['href'], {'source': PURE, 'entry': 'twice', 'arguments': [{'tag': 'natural', 'value': '21'}]}, tok)[1]
    got['repl'] = (ran['status'], ran['value'])
    return got


class Controls(FrontCase):
    fresh_world = True  # each test plants in a garden of its own and reads garden/bell/1
    independent = True  # so the runner may deal the class into chunks

    def setUp(self):
        super().setUp()
        town_garden(lambda **q: self.host.send(q))
        self.tok = self.login()

    def get(self, href):
        s, body = self.call('GET', href, token=self.tok)
        self.assertIn('_links', body, (href, body))
        self.assertEqual(body['_links']['self']['href'], href)
        return s, body


    def test_a_misfit_spells_refusal_keeps_the_hosts_hint(self):
        s, t = self.call('POST', '/AGENTS.md/world/garden/receive', {'intent': 'misfit-1', 'spell': 'delvetalk garden nosuch'}, self.tok)
        self.assertEqual((s, t['status']), (200, 'refused'), t)
        self.assertIn('delvetalk garden', t.get('hint', ''), t)  # the spells it has, to send again

    def test_acting_from_the_reply_alone(self):
        view = self.get('/AGENTS.md/world/garden')[1]
        spell = view['_actions']['plant']
        s, t = self.call('POST', '/AGENTS.md/world/garden/plant', {'intent': 'by-form', 'fields': fill(spell)}, self.tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        self.assertLess(len(json.dumps(t)), 1024, t)
        self.assertEqual(set(t) - {'revealed'}, {'status', 'line', 'offers', 'receipt', '_links'})  # revealed: what the act fired or opened, when anything
        self.assertTrue(t['line'].startswith('● admitted garden v'), t['line'])
        links = t['_links']
        self.assertEqual(links['receipt']['href'], '/AGENTS.md/receipt/' + t['receipt']['slug'])
        self.assertEqual(links['offers']['href'], f"/AGENTS.md/offers?after={t['receipt']['height'] - 1}")
        self.assertEqual(links['created'], [{'href': '/AGENTS.md/world/garden/bell/1', 'name': 'garden/bell/1'}])
        s, r = self.get(links['receipt']['href'])
        self.assertEqual((s, r['receipt']['slug']), (200, t['receipt']['slug']))
        self.assertIn('hash', r['receipt'])  # the whole receipt is here, not in the turn
        self.assertEqual(r['_links']['object']['href'], '/AGENTS.md/world/garden')
        s, bell = self.get(links['created'][0]['href'])
        self.assertEqual((s, bell['object']), (200, 'garden/bell/1'))
        self.assertTrue(all(t.startswith('delvetalk garden/bell/1 ') for t in bell['_actions'].values()), bell['_actions'])
        filled = view['_actions']['plant'].replace('one of amber, violet, silver', 'amber').replace('<text 1..80>', 'a spelled bell')
        s, t = self.call('POST', '/AGENTS.md/world/garden/receive', {'intent': 'by-spell', 'spell': filled}, self.tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        s, offers = self.get(links['offers']['href'])
        self.assertEqual(offers['_links']['next']['href'], f"/AGENTS.md/offers?after={offers['offers'][-1]['height']}&wait=30")

    def test_a_refusal_links_its_hint_and_the_usage_action(self):
        self.call('POST', '/AGENTS.md/scratch', {'name': 'try'}, self.tok)
        s, made = self.call('POST', '/AGENTS.md/scratch/try/objects', {'intent': 'mk-l', 'object': 'kept', 'entry': 'initial', 'seed': {},
                                                                'modules': [{'name': 'Kept', 'source': LAWFUL}]}, self.tok)
        self.assertEqual((s, made['status']), (200, 'created'), made)
        self.assertEqual(made['_links']['object']['href'], '/AGENTS.md/scratch/try/world/kept')
        s, t = self.call('POST', '/AGENTS.md/scratch/try/world/kept/bump', {'intent': 'no'}, self.tok)
        self.assertEqual((s, t['status'], t['class']), (200, 'refused', 'lawRefused'), t)
        self.assertTrue(t['line'].startswith('§ refused '), t['line'])
        self.assertEqual(t['_links']['hint']['href'], '/AGENTS.md/scratch/try/world/kept/source')  # the law is there
        # The law refuses this caller `bump` on a request-only clause (`admits`), so it is not offered again.
        self.assertNotIn('_actions', t)
        s, e = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': 7, 'intent': 'bad'}, self.tok)
        self.assertEqual((s, e['_links']['hint']['href'], list(e['_actions'])), (400, f'/AGENTS.md/world/{self.c}/source', ['bump']))
        self.turn(self.tok, 'dup')
        s, d = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'fields': {'a': 1}, 'intent': 'dup'}, self.tok)
        self.assertEqual((d['class'], d['_links']['hint']['href']), ('duplicateIdentity', '/AGENTS.md/receipt?intent=dup'), d)


    def test_a_stranger_walks_by_the_controls_alone(self):
        handle, did, log = 'mimo.delve.town', PEOPLE['mimo.delve.town'], []

        def call(method, href, body, token):
            s, h, data = self.request(method, href, body, token)
            log.append(len(data))
            self.assertLess(s, 400, (href, data))
            return s, json.loads(data)

        def prove(text):
            self.provider.texts[did] = text
            return f'at://{did}/town.delve.feed.post/3abc'
        got = walk(call, handle, prove, REPL_COUNTER)
        self.assertEqual(got, {'planted': ('admitted', ['garden/bell/1']), 'receipt': ('receipt', True),
                               'scratch': ('created', 'admitted', {'tag': 'natural', 'value': '1'}),
                               'repl': ('finished', {'tag': 'natural', 'value': '42'})})

    def test_a_strangers_read_of_a_refused_receipt_by_slug_keeps_its_object_and_recovery_links(self):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-kept', 'object': 'kept', 'entry': 'initial',
                            'modules': [{'name': 'Kept', 'source': LAWFUL}], 'seed': {'tag': 'record', 'fields': []}})
        self.assertEqual(r['status'], 'created', r)
        s, t = self.call('POST', '/AGENTS.md/world/kept/bump', {'intent': 'no'}, self.tok)
        self.assertEqual((s, t['class']), (200, 'lawRefused'), t)
        for reader in (self.tok, self.login('glm.delve.town')):  # mine, then someone else's public view of it
            s, got = self.call('GET', f"/AGENTS.md/receipt/{t['receipt']['slug']}", token=reader)
            links = {k: v['href'] for k, v in got['_links'].items() if k in ('object', 'source', 'hint')}
            self.assertEqual((s, links), (200, {'object': '/AGENTS.md/world/kept', 'source': '/AGENTS.md/world/kept/source',
                                                'hint': '/AGENTS.md/world/kept/source'}), got)


def raw(port, data):
    """Bytes as sent, the reply as received: for requests http.client will not form."""
    with socket.create_connection(('127.0.0.1', port), timeout=30) as c:
        c.sendall(data)
        out = b''
        while chunk := c.recv(65536):
            out += chunk
    head, _, body = out.partition(b'\r\n\r\n')
    return int(head.split()[1]), head.decode(), json.loads(body)


class Envelope(FrontCase):
    REMOTE = {'requestTimeout', 'hostTimeout', 'hostUnavailable', 'busy'}  # tests.test_hypermedia.Robust and test_http.Slow reach these

    def test_every_error_class_is_reachable_and_answers_the_one_envelope(self):
        tok, seen = self.login(), {}

        def saw(cls, got, headers=''):
            status, body = got[0], got[1]
            self.assertEqual((status, body['status'], body['class']), (ERRORS[cls]['code'], ERRORS[cls]['status'], cls), body)
            self.assertIsInstance(body['message'], str)
            self.assertEqual(body['_links']['api'], {'href': '/AGENTS.md/api'})
            seen[cls] = body
            return body
        port, c1 = self.port, f'/AGENTS.md/world/{self.c}/bump'
        post = lambda path, body=None, raw_=None, t=tok: self.call('POST', path, body, t, raw_)
        saw('badJson', post(c1, raw_=b'{nope'))
        saw('badJson', post(c1, raw_=b'[' * 60000))
        saw('badJson', post(c1, raw_=b'{"a":' * 300 + b'1' + b'}' * 300))
        saw('bodyTooLarge', post(c1, raw_=b'{"intent":"' + b'x' * 300000 + b'"}'))
        saw('bodyTooLarge', post('/AGENTS.md/challenge', raw_=b'{"handle":"' + b'x' * 70000 + b'"}', t=None))  # the anonymous bound is unchanged
        saw('badRequest', raw(port, b'POST /AGENTS.md/deliver HTTP/1.1\r\nAuthorization: Bearer ' + tok.encode() + b'\r\nContent-Length: ab\r\n\r\n')[::2])
        saw('badRequest', raw(port, b'GARBAGE\r\n\r\n')[::2])
        saw('httpVersion', raw(port, b'GET / HTTP/2.0\r\n\r\n')[::2])
        saw('uriTooLong', raw(port, b'GET /' + b'x' * 70000 + b' HTTP/1.1\r\n\r\n')[::2])
        saw('headersTooLarge', raw(port, b'GET / HTTP/1.1\r\nX: ' + b'a' * 70000 + b'\r\n\r\n')[::2])
        saw('notImplemented', self.call('BREW', '/AGENTS.md/world'))
        s, h, data = self.request('PUT', f'/AGENTS.md/world/{self.c}', token=tok)
        self.assertEqual(dict(h)['Allow'], 'GET, OPTIONS')
        saw('methodNotAllowed', (s, json.loads(data)))
        saw('unknownRoute', self.call('GET', '/AGENTS.md/nowhere', token=tok))
        self.assertEqual(saw('unknown', self.call('GET', '/AGENTS.md/world/nope', token=tok))['_links']['hint'], {'href': '/AGENTS.md/world'})
        saw('unauthenticated', self.call('GET', '/AGENTS.md/world'))
        saw('identity', post('/AGENTS.md/verify', {'handle': 'talkie.delve.town', 'uri': 'at://nothing'}, t=None))
        saw('badModules', post('/AGENTS.md/repl', {'modules': 'x'}))
        repl = self.front.repl.send
        self.front.repl.send = lambda req: {'status': 'error', 'message': 'checkpoint was not issued by this process'} if req['op'] == 'turn-resume' else repl(req)
        saw('replRestarted', post('/AGENTS.md/repl', {'modules': [{'name': 'Package', 'source': PURE}], 'entry': 'twice', 'checkpoint': {}, 'response': {}}))
        self.front.repl.send = repl
        post('/AGENTS.md/scratch', {'name': 'try'})
        saw('unspellable', post('/AGENTS.md/scratch/try/objects', {'object': 'coin box', 'intent': 'mk-cb'}))
        saw('moduleTooLarge', post('/AGENTS.md/check', {'modules': [{'name': 'Big', 'source': 'x' * 140000}]}))
        e = saw('hostRequest', post(c1, {'argument': 7, 'intent': 'seven'}))
        self.assertEqual((e['message'], e['_links']['hint']), ('String expected', {'href': f'/AGENTS.md/world/{self.c}/source'}))
        real = self.host.send
        stub = {'world-view': {'status': 'denied', 'message': 'not yours'}, 'world-resolve': {'status': 'ambiguous', 'matches': ['a', 'b'], 'message': 'two'}}
        self.host.send = lambda req: stub[req['op']] if req['op'] in stub else real(req)
        saw('denied', self.call('GET', f'/AGENTS.md/world/{self.c}', token=tok))
        self.assertEqual(saw('ambiguous', self.call('GET', '/AGENTS.md/receipt/babab-dabab', token=tok))['matches'], ['a', 'b'])
        stub['world-view'] = {'status': 'viewed', 'state': 'x' * 2000}
        limit, transport.http.MAX_REPLY = transport.http.MAX_REPLY, 1000
        try:
            saw('replyTooLarge', self.call('GET', f'/AGENTS.md/world/{self.c}', token=tok))
        finally:
            transport.http.MAX_REPLY = limit
        stub.clear()
        self.host.send = lambda req: 1 / 0 if req['op'] == 'world-view' else real(req)
        saw('internal', self.call('GET', f'/AGENTS.md/world/{self.c}', token=tok))
        self.host.send = real
        other = self.login('glm.delve.town')
        codes = [self.request('GET', '/AGENTS.md/pending', token=other) for _ in range(33)]
        self.assertEqual(dict(codes[-1][1])['Retry-After'], '60')
        saw('rateLimited', (codes[-1][0], json.loads(codes[-1][2])))
        self.assertEqual(set(seen), set(ERRORS) - self.REMOTE)

    def test_xrpc_errors_carry_the_envelope_beside_their_own_names(self):
        s, e = self.call('GET', '/xrpc/com.atproto.repo.describeRepo?repo=did:plc:other')
        self.assertEqual((s, e['error'], e['class'], e['status']), (400, 'RepoNotFound', 'RepoNotFound', 'error'))
        self.assertIn('self', e['_links'])


class Robust(FrontCase):
    def test_an_absent_or_mute_host_is_a_named_error(self):
        tok = self.login()
        self.front.host = HostClient(Path(self.tmp.name) / 'nobody.sock')
        s, e = self.call('GET', '/AGENTS.md/world', token=tok)
        self.assertEqual((s, e['class']), (503, 'hostUnavailable'), e)
        with socket.socket(socket.AF_UNIX) as mute:  # takes the connection, never answers
            mute.bind(str(Path(self.tmp.name) / 'mute.sock'))
            mute.listen(64)
            self.front.host = HostClient(Path(self.tmp.name) / 'mute.sock', timeout=1)
            s, e = self.call('GET', '/AGENTS.md/world', token=tok)
            self.assertEqual((s, e['status'], e['class']), (504, 'error', 'hostTimeout'), e)
            s, x = self.call('GET', f'/xrpc/com.atproto.repo.listRecords?repo={self.front.repo.did}&collection=town.delvetalk.receipt')
            self.assertEqual((s, x['error'], x['class']), (504, 'HostTimeout', 'HostTimeout'), x)

    def test_a_stalled_client_holds_only_its_own_connection_and_only_until_the_timeout(self):
        tok = self.login()
        self.front.request_timeout = 1
        stalled = socket.create_connection(('127.0.0.1', self.port))  # headers sent, the body promised and never sent
        stalled.sendall(f'POST /AGENTS.md/world/{self.c}/bump HTTP/1.1\r\nAuthorization: Bearer {tok}\r\nContent-Length: 100\r\n\r\n'.encode())
        half = socket.create_connection(('127.0.0.1', self.port))  # headers never finished
        half.sendall(b'GET /AGENTS.md/world HTTP/1.1\r\nHost: x\r\n')
        for _ in range(5):
            self.assertEqual(self.call('GET', '/AGENTS.md/api')[0], 200)
        self.assertEqual(self.turn(tok, 'beside')[1]['status'], 'admitted')
        stalled.settimeout(10)
        out = b''
        while chunk := stalled.recv(65536):
            out += chunk
        head, _, body = out.partition(b'\r\n\r\n')
        self.assertEqual((head.split()[1], json.loads(body)['class']), (b'408', 'requestTimeout'))
        half.settimeout(10)
        self.assertEqual(half.recv(65536), b'')  # dropped, nothing to answer
        stalled.close(), half.close()

    def test_a_burst_of_fifty_mixed_clients(self):
        toks = [self.login(h) for h in PEOPLE]
        height = self.host.send({'op': 'world-status'})['height']
        kinds = [('POST', f'/AGENTS.md/world/{self.c}/bump', None, 200), ('GET', f'/AGENTS.md/world/{self.c}', None, 200),
                 ('GET', '/AGENTS.md/api', None, 200), ('POST', f'/AGENTS.md/world/{self.c}/bump', b'{nope', 400), ('GET', '/AGENTS.md/world/nope', None, 404)]
        gate, got, errors = threading.Barrier(50), {}, []
        self.front.slots = threading.BoundedSemaphore(50)  # past the default 48 a client is told `busy` (test_http.Slow)

        def client(i):
            method, path, raw_, want = kinds[i % 5]
            try:
                gate.wait()
                body = {'intent': f'burst-{i}'} if raw_ is None and method == 'POST' else None
                s, r = self.call(method, path, body, toks[i % 4], raw_)
                got[i] = (s, r.get('status'), '_links' in r)
                assert s == want, (i, s, r)
            except BaseException as e:
                errors.append(repr(e))
        threads = [threading.Thread(target=client, args=(i,)) for i in range(50)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len(got), 50)
        self.assertTrue(all(links for _, _, links in got.values()))
        self.assertEqual(sorted(got[i][1] for i in range(0, 50, 5)), ['admitted'] * 10)
        self.assertEqual(self.host.send({'op': 'world-status'})['height'], height + 10)  # ten turns, each journaled once
        counted = [i for i in range(50) if i % 5 != 2]  # the catalogue needs no credential and spends none
        self.assertEqual([self.front.limited(t, count=False) for t in toks], [sum(1 for i in counted if i % 4 == k) for k in range(4)])
        self.assertEqual(self.call('GET', f'/AGENTS.md/world/{self.c}', token=toks[0])[1]['version'], 10)

    def test_malformed_input_on_every_route_answers_a_named_envelope_never_a_crash(self):
        rnd, tok = random.Random(7), self.login()
        ids = ['\u2603', 'a%2F..%2F..', '%00', '%ED%A0%80', 'x' * 300, '..', 'garden/../' + self.c, '%', '%zz', '<i>', '\u00b2']
        bodies = [b'', b'\x00\xff' * 50, bytes(rnd.randrange(256) for _ in range(300)), b'[' * 5000, b'{"a":' * 400 + b'1' + b'}' * 400,
                  json.dumps({'intent': '\ud800\u2603', 'spell': '\ud800', 'object': '\u2603/\ud800', 'handle': '\ud800'}).encode(),
                  b'{"modules": [1, "x", null], "source": 5, "entry": [], "arguments": {}, "fields": [1], "spell": 7, "seed": [[[]]], "checkpoint": "x"}',
                  b'{"handle": ["x"], "uri": {"a": 1}, "argument": {"tag": "record", "fields": "no"}, "intent": {"a": 1}}',
                  b'"string"', b'null', b'1e999999', b'{"intent": 123456789012345678901234567890, "fields": {"a": 1e308}}']
        queries = ['', '?after=%C2%B2&wait=%C2%B2&prefix=%E2%98%83&full=1&compact=1', '?cursor=%C2%B2&limit=%C2%B2&repo=x&collection=%00',
                   '?object=%ED%A0%80&after=-1&wait=99999999999999999999']
        crashes, n = [], 0
        for e in CATALOGUE:
            for oid in rnd.sample(ids, 4):
                path = re.sub(r'\{(\w+)\}', lambda m: urllib.parse.quote(oid, safe='/%') if m[1] == 'object' else 'try' if m[1] == 'name' else urllib.parse.quote(oid, safe=''), e['href'])
                for method in ('GET', 'POST'):
                    for body in (rnd.sample(bodies, 4) if method == 'POST' else [None]):
                        self.now[0] += 4  # under every rate limit: the fuzz is of input, not of the limiter
                        n += 1
                        s, h, data = self.request(method, path + rnd.choice(queries), token=tok, raw=body)
                        kind = dict(h).get('Content-Type', '')
                        if s >= 500 or (s >= 400 and kind.startswith('application/json') and 'class' not in json.loads(data)):
                            crashes.append((method, path, body and body[:60], s, data[:200]))
        self.assertEqual(crashes, [])
        self.assertGreater(n, 300)


class Catalogue(unittest.TestCase):
    """The catalogue against a stub host: routes as data, and the router that answers them is the one that describes them."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        st = State(self.tmp.name)
        self.front = Front(st, StubHost(), identity.Identity(st, delve.Client(lambda *a: (404, b''))), ('127.0.0.1', 0))
        threading.Thread(target=self.front.serve_forever, daemon=True).start()

    def tearDown(self):
        self.front.shutdown()
        self.front.server_close()
        self.tmp.cleanup()

    def call(self, method, path, headers=None, raw=None):
        c = http.client.HTTPConnection('127.0.0.1', self.front.server_address[1], timeout=30)
        c.request(method, path, raw, headers or {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, dict(r.getheaders()), data


    def test_the_login_routes_are_in_the_catalogue_and_options_describes_them(self):
        for path, name in (('/oauth/start', 'oauthStart'), ('/oauth/callback', 'oauthCallback'), ('/oauth/client-metadata.json', 'oauthClient')):
            s, h, raw = self.call('OPTIONS', path)
            self.assertEqual((s, [e['name'] for e in json.loads(raw)['routes']], h['Allow']), (200, [name], 'GET, OPTIONS'), path)
        count = re.match(r'# DelveTalk: (\w+) worked sessions', EXAMPLES.read_text())[1]  # the examples page names its own count
        self.assertTrue(next(e['does'] for e in CATALOGUE if e['name'] == 'examples').startswith(count + ' worked sessions'))

    def test_the_catalogue_is_served_as_data_and_the_guide_links_to_it(self):
        s, h, raw = self.call('GET', '/AGENTS.md/api')
        api = json.loads(raw)
        self.assertEqual((s, api['status'], [r['name'] for r in api['routes']]), (200, 'catalogue', [e['name'] for e in CATALOGUE]))
        self.assertEqual(set(api['errors']), set(ERRORS))
        self.assertEqual({k: v['transient'] for k, v in api['refusals'].items()}, {k: v['transient'] for k, v in REFUSALS.items()})
        self.assertEqual(api['limits']['bodyBytes'], 262144)
        s, h, raw = self.call('GET', '/AGENTS.md', {'Accept': 'application/json'})
        self.assertEqual({**json.loads(raw), '_links': None}, {**api, '_links': None})
        s, h, text = self.call('GET', '/AGENTS.md')
        self.assertEqual(h['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn(b'/api', text)

    def test_the_module_bounds_named_are_the_hosts(self):
        kernel = bounds()['kernel']
        s, h, raw = self.call('GET', '/AGENTS.md/api')
        limits = json.loads(raw)['limits']  # an agent may send a module up to the kernel's bound, as many as it takes
        self.assertEqual((limits['moduleBytes'], limits['modules']), (kernel['maxPackageBytes'], kernel['maxModules']))
        self.assertLess(limits['moduleBytes'], limits['bodyBytes'])  # so moduleTooLarge is reached before bodyTooLarge
        self.assertEqual(limits['deliverPerCall'], bounds()['host']['deliveriesPerCall'])

    def test_the_catalogues_refusals_are_the_hosts_closed_set_and_its_transient_ones(self):
        self.assertEqual(set(REFUSALS), set(bounds()['refusalClasses']))
        self.assertEqual({k for k, v in REFUSALS.items() if v['transient']}, set(bounds()['transientClasses']))
        host = Path(__file__).resolve().parent.parent / 'spec' / 'Delvetalk' / 'Host'
        spell, loop = (host / 'Spell.lean').read_text(), (host / 'TurnLoop.lean').read_text()
        named = set(re.findall(r'=> "(\w+)"', re.search(r'def Clause.name.*?\n\n', spell, re.S)[0])) - {'unclear'}  # unclear is a question, never a refusal
        literal = set(re.findall(r'\.refuse \w+ "(\w+)"|refuseSpell w req \w+ "(\w+)"', loop))
        clauses = named | {a or b for a, b in literal}
        listed = re.search(r'`clause` says which part \(([^);]*)', REFUSALS['badSpell']['means'])[1]
        self.assertEqual(set(listed.split(', ')), clauses)


    def test_every_class_the_guide_names_is_the_catalogues(self):
        guide = GUIDE.read_text()  # no class tables since the rewrite: the catalogue is the list, the guide names a few
        shown = set(re.findall(r'"class": "(\w+)"', guide))
        transient = set(re.findall(r'`(\w+)`', re.search(r'((?:`\w+`(?:, | and |,\s+))+`\w+`) are transient', guide)[1]))
        self.assertTrue(shown and transient, (shown, transient))
        self.assertLessEqual(shown, set(REFUSALS) | set(ERRORS))
        self.assertEqual({c for c in transient if REFUSALS.get(c, {}).get('transient')}, transient)


if __name__ == '__main__':
    unittest.main()
