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
import time
import unittest
import urllib.parse
from pathlib import Path

from tests.test_chain import garden_state
from tests.test_http import DID, PEOPLE, REPL_COUNTER, FrontCase, StubHost
import transport.http
from transport import delve, identity
from transport.hostproc import HostClient
from transport.http import CATALOGUE, ERRORS, GUIDE, REFUSALS, Front, resolve
from tests.test_turn_world import closure

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
    plant, read the receipt by its slug, make a thing in the heap and run it, run a REPL entry. `call(method, href, body,
    token)` -> (status, reply); `prove(text)` posts the challenge and returns the post's URI; `module` is the stranger's
    own Bend (a State with a `count` and a `bump` method). -> what it reached."""
    got = {}
    api = call('GET', '/AGENTS.md/api', None, None)[1]
    routes = {r['name']: r for r in api['routes']}
    ch = call('POST', routes['challenge']['href'], {'handle': handle}, None)[1]
    v = call('POST', ch['_links']['verify']['href'], {'handle': handle, 'uri': prove(ch['text'])}, None)[1]
    tok = ch['credential']
    listing = call('GET', v['_links']['world']['href'], None, tok)[1]
    item = [i for i in listing['_links']['item'] if 'plant' in i.get('actions', ())][0]  # the listing names each object's methods
    spell = call('GET', item['href'], None, tok)[1]['_actions']['plant']
    planted = call('POST', f"{item['href']}/plant", {'intent': 'stranger-plant', 'fields': fill(spell)}, tok)[1]
    got['planted'] = (planted['status'], [c['name'] for c in planted['_links'].get('created', [])])
    receipt = call('GET', planted['_links']['receipt']['href'], None, tok)[1]
    got['receipt'] = (receipt['status'], receipt['receipt']['slug'] == planted['receipt']['slug'])
    made = call('POST', routes['create']['href'], {'intent': 'stranger-make', 'object': 'mine', 'entry': 'initial', 'source': module, 'seed': {}}, tok)[1]
    mine = call('GET', made['_links']['object']['href'], None, tok)[1]
    assert 'bump' in mine['_actions'], mine
    bumped = call('POST', mine['_links']['object']['href'] + '/bump', {'intent': 'stranger-bump', 'fields': {}}, tok)[1]
    result = call('GET', bumped['_links']['receipt']['href'], None, tok)[1]['receipt']['result']
    got['heap'] = (made['status'], bumped['status'], result)
    ran = call('POST', routes['repl']['href'], {'source': PURE, 'entry': 'twice', 'arguments': [{'tag': 'natural', 'value': '21'}]}, tok)[1]
    got['repl'] = (ran['status'], ran['value'])
    return got


class Controls(FrontCase):
    fresh_world = True  # each test plants in a garden of its own and reads garden/bell/1
    independent = True  # so the runner may deal the class into chunks

    def setUp(self):
        super().setUp()
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-g', 'object': 'garden',
                            'modules': closure('Garden'), 'entry': 'initial', 'seed': garden_state(0)})
        self.assertEqual(r['status'], 'created', r)
        self.tok = self.login()

    def get(self, href):
        s, body = self.call('GET', href, token=self.tok)
        self.assertIn('_links', body, (href, body))
        self.assertEqual(body['_links']['self']['href'], href)
        return s, body

    def test_an_object_reply_carries_one_action_per_turnable_method_with_its_form(self):
        s, view = self.get('/AGENTS.md/world/garden')
        self.assertEqual((s, view['status']), (200, 'viewed'))
        self.assertEqual({k: v['href'] for k, v in view['_links'].items() if k != 'self'},
                         {'object': '/AGENTS.md/world/garden', 'card': '/AGENTS.md/world/garden/card', 'source': '/AGENTS.md/world/garden/source',
                          'world': '/AGENTS.md/world', 'offers': '/AGENTS.md/offers'})
        methods = self.host.send({'op': 'world-inspect', 'principal': DID, 'object': 'garden'})['methods']
        offered = {m['name'] for m in methods if m['context']}
        self.assertLessEqual(set(view['_actions']), offered)
        self.assertEqual(view['_actions']['plant'], 'delvetalk garden plant\ncolour: one of amber, violet, silver\nseed: <text 1..80>\n')
        self.assertTrue(all(t.startswith('delvetalk garden ') for t in view['_actions'].values()))
        self.assertNotIn('receive', view['_actions'])  # spells go to receive; it is not one
        self.assertNotIn('set', view['_actions'])  # no form: the host's type, and typed data
        self.assertLess(len(json.dumps(view['_actions'])), 800)
        for route in ('card', 'source'):
            self.assertEqual(self.get(f'/AGENTS.md/world/garden/{route}')[1]['_actions'], view['_actions'])

    def test_acting_from_the_reply_alone(self):
        view = self.get('/AGENTS.md/world/garden')[1]
        spell = view['_actions']['plant']
        s, t = self.call('POST', '/AGENTS.md/world/garden/plant', {'intent': 'by-form', 'fields': fill(spell)}, self.tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        self.assertLess(len(json.dumps(t)), 1024, t)
        self.assertEqual(set(t), {'status', 'line', 'offers', 'receipt', '_links'})
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
        s, made = self.call('POST', '/AGENTS.md/heap/objects', {'intent': 'mk-l', 'object': 'kept', 'entry': 'initial', 'seed': {},
                                                                'modules': [{'name': 'Kept', 'source': LAWFUL}]}, self.tok)
        self.assertEqual((s, made['status']), (200, 'created'), made)
        self.assertEqual(made['_links']['object']['href'], '/AGENTS.md/heap/world/kept')
        s, t = self.call('POST', '/AGENTS.md/heap/world/kept/bump', {'intent': 'no'}, self.tok)
        self.assertEqual((s, t['status'], t['class']), (200, 'refused', 'lawRefused'), t)
        self.assertTrue(t['line'].startswith('§ refused '), t['line'])
        self.assertEqual(t['_links']['hint']['href'], '/AGENTS.md/heap/world/kept/source')  # the law is there
        # The law refuses this caller `bump` on a request-only clause (`admits`), so it is not offered again.
        self.assertNotIn('_actions', t)
        s, e = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': 7, 'intent': 'bad'}, self.tok)
        self.assertEqual((s, e['_links']['hint']['href'], list(e['_actions'])), (400, f'/AGENTS.md/world/{self.c}/source', ['bump']))
        self.turn(self.tok, 'dup')
        s, d = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'fields': {'a': 1}, 'intent': 'dup'}, self.tok)
        self.assertEqual((d['class'], d['_links']['hint']['href']), ('duplicateIdentity', '/AGENTS.md/receipt?intent=dup'), d)

    def test_a_listing_links_each_id_and_its_next_page(self):
        s, listed = self.get('/AGENTS.md/world')
        self.assertEqual([i['name'] for i in listed['_links']['item']], listed['ids'])
        self.assertIn('garden', [i['name'] for i in listed['_links']['item']])
        self.assertIn('plant', next(i for i in listed['_links']['item'] if i['name'] == 'garden')['actions'])
        self.assertNotIn('next', listed['_links'])
        real = self.host.send
        self.host.send = lambda req: {'status': 'listed', 'ids': ['a', 'b/c'], 'more': True} if req['op'] == 'world-objects' else real(req)
        s, page = self.get('/AGENTS.md/world?prefix=b')
        self.assertEqual(page['_links']['next']['href'], '/AGENTS.md/world?prefix=b&after=b%2Fc')

    def test_every_json_reply_has_links(self):
        for method, path, body in (('GET', '/AGENTS.md/me', None), ('GET', '/AGENTS.md/pending', None), ('POST', '/AGENTS.md/deliver', {}),
                                   ('POST', '/AGENTS.md/check', {'source': REPL_COUNTER, 'entry': 'bump'}),
                                   ('GET', '/AGENTS.md/receipt/nothing', None), ('GET', '/AGENTS.md/offers', None)):
            s, r = self.call(method, path, body, self.tok)
            self.assertEqual(r['_links']['self']['href'], path, (path, r))
        s, ch = self.call('POST', '/AGENTS.md/challenge', {'handle': 'glm.delve.town'})
        self.assertEqual(ch['_links']['verify']['href'], '/AGENTS.md/verify')

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
                               'heap': ('created', 'admitted', {'tag': 'natural', 'value': '1'}),
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

    def test_host_ops_wanted_project_when_the_host_answers_them(self):
        """Stubs of docs/AGENTS-API.md "Host ops wanted": `admits` per method, `methods` per listed id."""
        real = self.host.send

        def send(req):
            r = real(req)
            if req['op'] == 'world-inspect' and r.get('status') == 'inspected':
                r['methods'] = [{**m, 'admits': m['name'] != 'plant' or {'clause': 'owner'}} for m in r['methods']]
            if req['op'] == 'world-objects':
                r['methods'] = {'garden': ['plant', 'receive']}
            return r
        self.host.send = send
        names = list(self.get('/AGENTS.md/world/garden')[1]['_actions'])
        self.assertNotIn('plant', names)
        items = self.get('/AGENTS.md/world')[1]['_links']['item']
        self.assertIn({'href': '/AGENTS.md/world/garden', 'name': 'garden', 'actions': ['plant', 'receive']}, items)

    def test_a_suspended_turn_links_its_offers_with_a_wait(self):
        from transport.http import receipt_links
        links = receipt_links('/AGENTS.md', {'status': 'suspended', 'receipt': {'slug': 'babab-dabab', 'height': 12,
                                                                                'roots': [{'object': 'garden', 'version': 3}]}})
        self.assertEqual(links['offers']['href'], '/AGENTS.md/offers?after=12&wait=30')
        self.assertEqual(links['object']['href'], '/AGENTS.md/world/garden')


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
        saw('bodyTooLarge', post(c1, raw_=b'{"intent":"' + b'x' * 65536 + b'"}'))
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
        saw('unspellable', post('/AGENTS.md/heap/objects', {'object': 'coin box', 'intent': 'mk-cb'}))
        saw('moduleTooLarge', post('/AGENTS.md/check', {'modules': [{'name': 'Big', 'source': 'x' * 16385}]}))
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
    def test_hostd_absent_or_mute_is_a_named_error_within_the_timeout(self):
        tok = self.login()
        self.front.host = HostClient(Path(self.tmp.name) / 'nobody.sock')
        s, e = self.call('GET', '/AGENTS.md/world', token=tok)
        self.assertEqual((s, e['class']), (503, 'hostUnavailable'), e)
        with socket.socket(socket.AF_UNIX) as mute:  # takes the connection, never answers
            mute.bind(str(Path(self.tmp.name) / 'mute.sock'))
            mute.listen(64)
            self.front.host = HostClient(Path(self.tmp.name) / 'mute.sock', timeout=1)
            t0 = time.time()
            s, e = self.call('GET', '/AGENTS.md/world', token=tok)
            self.assertEqual((s, e['status'], e['class']), (504, 'error', 'hostTimeout'), e)
            s, x = self.call('GET', f'/xrpc/com.atproto.repo.listRecords?repo={self.front.repo.did}&collection=town.delvetalk.receipt')
            self.assertEqual((s, x['error'], x['class']), (504, 'HostTimeout', 'HostTimeout'), x)
            self.assertLess(time.time() - t0, 5)

    def test_a_stalled_client_holds_only_its_own_connection_and_only_until_the_timeout(self):
        tok = self.login()
        self.front.request_timeout = 1
        stalled = socket.create_connection(('127.0.0.1', self.port))  # headers sent, the body promised and never sent
        stalled.sendall(f'POST /AGENTS.md/world/{self.c}/bump HTTP/1.1\r\nAuthorization: Bearer {tok}\r\nContent-Length: 100\r\n\r\n'.encode())
        half = socket.create_connection(('127.0.0.1', self.port))  # headers never finished
        half.sendall(b'GET /AGENTS.md/world HTTP/1.1\r\nHost: x\r\n')
        t0 = time.time()
        for _ in range(5):
            self.assertEqual(self.call('GET', '/AGENTS.md/api')[0], 200)
        self.assertEqual(self.turn(tok, 'beside')[1]['status'], 'admitted')
        self.assertLess(time.time() - t0, 1)
        stalled.settimeout(10)
        out = b''
        while chunk := stalled.recv(65536):
            out += chunk
        head, _, body = out.partition(b'\r\n\r\n')
        self.assertEqual((head.split()[1], json.loads(body)['class']), (b'408', 'requestTimeout'))
        half.settimeout(10)
        self.assertEqual(half.recv(65536), b'')  # dropped, nothing to answer
        self.assertLess(time.time() - t0, 5)
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
        self.assertEqual([len(self.front.used(t)) for t in toks], [sum(1 for i in counted if i % 4 == k) for k in range(4)])
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
                path = re.sub(r'\{(\w+)\}', lambda m: urllib.parse.quote(oid, safe='/%') if m[1] == 'object' else urllib.parse.quote(oid, safe=''), e['href'])
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
        self.front = Front(('127.0.0.1', 0), StubHost(), identity.Identity(self.tmp.name, delve.Client(lambda *a: (404, b''))))
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

    def test_every_route_resolves_from_its_template_to_its_own_entry(self):
        names = [e['name'] for e in CATALOGUE]
        self.assertEqual(len(names), len(set(names)))
        fill = {'object': 'garden%2Fbell%2F1', 'method': 'plant', 'intent': 'plant-1', 'slug': 'babab-dabab', 'nsid': 'com.atproto.repo.describeRepo', 'file': 'style.css'}
        for e in CATALOGUE:
            for href in (e['href'], e.get('heap')):
                if href:
                    self.assertEqual(resolve(e['method'], re.sub(r'\{(\w+)\}', lambda m: fill[m[1]], href))[0], e['name'], href)
                    if '/world/' in href:  # agents' routes also take an id's slashes as they are
                        self.assertEqual(resolve(e['method'], href.replace('{object}', 'garden/bell/1').replace('{method}', 'plant'))[0], e['name'])

    def test_the_catalogue_is_served_as_data_and_the_guide_links_to_it(self):
        s, h, raw = self.call('GET', '/AGENTS.md/api')
        api = json.loads(raw)
        self.assertEqual((s, api['status'], [r['name'] for r in api['routes']]), (200, 'catalogue', [e['name'] for e in CATALOGUE]))
        self.assertEqual(set(api['errors']), set(ERRORS))
        self.assertEqual({k: v['transient'] for k, v in api['refusals'].items()}, {k: v['transient'] for k, v in REFUSALS.items()})
        self.assertEqual(api['limits']['bodyBytes'], 65536)
        s, h, raw = self.call('GET', '/AGENTS.md', {'Accept': 'application/json'})
        self.assertEqual({**json.loads(raw), '_links': None}, {**api, '_links': None})
        s, h, text = self.call('GET', '/AGENTS.md')
        self.assertEqual(h['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn(b'/api', text)

    def test_the_catalogues_refusals_are_the_hosts_closed_set_and_its_transient_ones(self):
        ops = (Path(__file__).resolve().parent.parent / 'spec' / 'Delvetalk' / 'Host' / 'Ops.lean').read_text()
        names = lambda decl: set(re.findall(r'"(\w+)"', re.search(rf'def {decl} : List String :=\s*\[(.*?)\]', ops, re.S)[1]))
        self.assertEqual(set(REFUSALS), names('refusalClasses'))
        self.assertEqual({k for k, v in REFUSALS.items() if v['transient']}, names('transientClasses'))
        host = Path(__file__).resolve().parent.parent / 'spec' / 'Delvetalk' / 'Host'
        spell, loop = (host / 'Spell.lean').read_text(), (host / 'TurnLoop.lean').read_text()
        named = set(re.findall(r'=> "(\w+)"', re.search(r'def Clause.name.*?\n\n', spell, re.S)[0])) - {'unclear'}  # unclear is a question, never a refusal
        literal = set(re.findall(r'\.refuse \w+ "(\w+)"|refuseSpell w req \w+ "(\w+)"', loop))
        clauses = named | {a or b for a, b in literal}
        listed = re.search(r'`clause` says which part \(([^);]*)', REFUSALS['badSpell']['means'])[1]
        self.assertEqual(set(listed.split(', ')), clauses)

    def test_no_example_reply_carries_more_than_one_hash_except_a_source(self):
        """The guide's rule: one hash per reply (the receipt's own), `pin` only on /source. Outside the rule: the REPL
        checkpoint the client sends back whole, and a result or grant the method returned as its answer."""
        page = (Path(__file__).resolve().parent.parent / 'docs' / 'AGENTS-EXAMPLES.md').read_text()
        hashes = lambda v: len(re.findall(r'bafy', json.dumps(v)))
        bare = lambda v: {k: bare(x) for k, x in v.items() if k not in ('checkpoint', 'result', 'grants')} if isinstance(v, dict) else [bare(x) for x in v] if isinstance(v, list) else v
        seen = 0
        for command, status, body in re.findall(r'^    \$ (curl [^\n]*)\n    (\d{3}) (\{.*\})$', page, re.M):
            if re.search(r'/source"?$', command.split(' -H')[0].split(' -d')[0]):
                continue
            try:
                reply = json.loads(body)
            except ValueError:  # cut where marked: only the text before the cut is left
                reply = {'cut': body}
            reply = bare(reply)
            seen += 1
            self.assertLessEqual(hashes(reply), 1, (command[:80], re.findall(r'"(\w+)": "bafy', body)))
        self.assertGreater(seen, 20)

    def test_the_guides_class_tables_are_the_catalogues(self):
        guide = GUIDE.read_text()
        rows = set(re.findall(r'^\| ([a-zA-Z, ]+?) \|', guide, re.M))
        documented = {c.strip() for row in rows for c in row.split(',')}
        self.assertLessEqual(set(REFUSALS) - {'duplicateIdentity'}, documented)

    def test_options_answers_the_entries_of_a_path(self):
        s, h, raw = self.call('OPTIONS', '/AGENTS.md/world/garden/bell/1')
        self.assertEqual((s, [r['name'] for r in json.loads(raw)['routes']], h['Allow']), (200, ['object', 'action'], 'GET, POST, OPTIONS'))
        s, h, raw = self.call('OPTIONS', '/AGENTS.md/heap/objects')
        self.assertEqual([r['name'] for r in json.loads(raw)['routes']], ['create'])
        self.assertEqual(self.call('OPTIONS', '/AGENTS.md/nowhere')[0], 404)


if __name__ == '__main__':
    unittest.main()
