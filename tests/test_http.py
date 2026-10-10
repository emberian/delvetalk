"""The agent API at /AGENTS.md over a real hostd: proof-of-control login, turns and receipts, the
REPL, private heaps, pages for people, limits.

Evidence for FOUNDATION §7 (layer: transport).
"""
import http.client
import json
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

from tests.test_chain import garden_state
from tests.test_turn_world import BINARY, closure, counter_modules, label, nat, record

REPL_COUNTER = '''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, Nat>
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
    case _: state.count + 1n
'''
from tests.test_turn import PLANS, variant
from transport import delve, identity
from tests.host import HostdCase, serve
from transport.hostproc import HostClient
from transport.http import Front, RemoteHeaps
from transport.identity import ORIGIN

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


class FrontCase(HostdCase):
    """One hostd per class, opened by the front's DID with the library sealed; each test gets its
    own front (identity database, rate limits, clock) and its own counter object."""
    OPENER = DID
    made = 0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hostd.heaps.size = 2

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.provider = Provider()
        self.now = [1000.0]
        self.host = HostClient(self.socket)  # a test may replace its send
        ident = identity.Identity(self.tmp.name, delve.Client(self.provider), clock=lambda: self.now[0])
        self.front = serve(Front(('127.0.0.1', 0), self.host, ident, clock=lambda: self.now[0],
                                 heaps=RemoteHeaps(self.socket, Path(self.hostd_dir.name) / 'heaps'), repl=HostClient(self.socket, stateless=True)))
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
        return self.call('POST', '/AGENTS.md/heap/objects', {'object': name, 'modules': closure('Plan') + [{'name': 'Counter', 'source': REPL_COUNTER}], 'entry': 'initial',
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
    def test_verify_announces_the_arrival_to_the_host(self):
        seen = []
        send = self.host.send
        self.host.send = lambda req, *a, **k: (seen.append(req), send(req, *a, **k))[1]
        self.login()
        arrive = {'op': 'world-arrive', 'principal': 'transport', 'did': DID, 'handle': HANDLE}
        self.assertEqual([r for r in seen if r['op'].startswith('world-arr') or r['op'] == 'world-principal'], [arrive])

    def test_the_agents_guide_and_its_examples_are_served_with_the_origin_filled_in(self):
        s, text = self.call('GET', '/AGENTS.md')
        self.assertEqual(s, 200)
        self.assertIn('O=' + ORIGIN + '/AGENTS.md\n', text)
        self.assertIn('$O/challenge', text)
        self.assertNotIn('{{origin}}', text)
        s, examples = self.call('GET', '/AGENTS.md/examples')
        self.assertEqual(s, 200)
        self.assertNotIn('{{origin}}', examples)

    def test_guide_names_the_host_binary(self):
        import hashlib
        s, headers, _ = self.request('GET', '/AGENTS.md')
        self.assertEqual(s, 200)
        self.assertEqual(dict(headers)['X-DelveTalk-Host-Sha256'], hashlib.sha256(Path(BINARY).read_bytes()).hexdigest())

    def test_json_sent_as_curl_sends_it_is_json(self):
        s, _, data = self.request('POST', '/AGENTS.md/challenge', raw=json.dumps({'handle': HANDLE}),
                                  headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(s, 200, data)
        self.assertEqual(json.loads(data)['did'], DID)

    def test_unknown_route_points_at_guide(self):
        s, body = self.call('GET', '/nope')
        self.assertEqual(s, 404)
        self.assertEqual(body['status'], 'error')
        self.assertIn('/AGENTS.md', body['message'])

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

    def test_a_body_over_64_kib_is_413_and_malformed_json_is_400(self):
        tok = self.login()
        s, e = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', token=tok, raw=b'{"intent":"' + b'x' * (65 * 1024) + b'"}')
        self.assertEqual(s, 413)
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

    def test_me_reports_principal_and_rate_limit_and_revoke_ends_the_credential(self):
        tok = self.login()
        self.heap_create(tok)
        s, me = self.call('GET', '/AGENTS.md/me', token=tok)
        self.assertEqual((s, me['principal'], me['handle'], me['did'], me['heapObjects']), (200, DID, HANDLE, DID, 1), me)
        self.assertEqual(me['verified'], 1000.0)
        self.assertEqual(me['rateLimit'], {'limit': 32, 'windowSeconds': 60, 'remaining': 30})
        self.assertEqual(self.call('POST', '/AGENTS.md/revoke', {}, tok)[1], {'status': 'revoked'})
        self.assertEqual(self.call('GET', '/AGENTS.md/me', token=tok)[0], 401)


class Turns(FrontCase):
    def test_a_logged_in_agent_views_takes_a_turn_reads_its_receipt_and_sees_the_new_version(self):
        tok = self.login()
        s, v = self.call('GET', f'/AGENTS.md/world/{self.c}', token=tok)
        self.assertEqual((s, v['status'], v['version']), (200, 'viewed', 0))
        s, t = self.turn(tok, 'i1')
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        s, r = self.call('GET', '/AGENTS.md/receipt/i1', token=tok)
        self.assertEqual(s, 200)
        self.assertEqual(r['receipt'], t['receipt'])
        self.assertEqual(self.call('GET', f'/AGENTS.md/world/{self.c}', token=tok)[1]['version'], 1)
        self.assertEqual(self.call('GET', '/AGENTS.md/pending', token=tok)[0], 200)
        self.assertEqual(self.call('POST', '/AGENTS.md/deliver', {}, tok)[0], 200)

    def test_compact_turn_reply_is_four_keys_and_the_default_stays_full(self):
        tok = self.login()
        s, full = self.turn(tok, 'k1')
        s, c = self.call('POST', f'/AGENTS.md/world/{self.c}/bump?compact=1', {'argument': record(), 'intent': 'k1'}, tok)  # same intent: the first receipt
        self.assertEqual(s, 200)
        self.assertEqual(c, {'status': 'admitted', 'outcome': full['receipt']['outcome'], 'offers': [o['text'] for o in full.get('offers') or []],
                             'receipt': {'object': self.c, 'version': 0, 'height': full['receipt']['height']}})
        self.assertIn('hash', full['receipt'])
        s, e = self.call('POST', f'/AGENTS.md/world/{self.c}/bump?compact=1', {'argument': 7, 'intent': 'bad2'}, tok)
        self.assertEqual((s, e['status']), (400, 'error'))  # a host error is not compacted

    def test_host_refusal_passes_through_verbatim(self):
        tok = self.login()
        s, v = self.call('GET', '/AGENTS.md/world/nope', token=tok)
        self.assertEqual(v, self.host.send({'op': 'world-view', 'principal': HANDLE, 'object': 'nope'}))
        s, e = self.call('POST', f'/AGENTS.md/world/{self.c}/bump', {'argument': 7, 'intent': 'bad'}, tok)
        self.assertEqual(s, 400)
        self.assertEqual(e, self.host.send({'op': 'world-turn', 'principal': HANDLE, 'object': self.c,
                                            'method': 'bump', 'argument': 7, 'identity': 'bad'}))

    def test_principal_cannot_be_forged_through_the_body(self):
        tok = self.login()
        s, t = self.call('POST', f'/AGENTS.md/world/{self.c}/bump',
                         {'argument': record(), 'intent': 'f1', 'principal': 'ember', 'identity': 'x'}, tok)
        self.assertEqual(t['status'], 'admitted', t)
        self.assertEqual(self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': 'f1'})['status'], 'receipt')
        self.assertNotEqual(self.host.send({'op': 'world-receipt', 'principal': 'ember', 'identity': 'f1'}).get('status'), 'receipt')
        self.assertNotEqual(self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': 'x'}).get('status'), 'receipt')

    def test_the_receipt_route_resolves_a_slug_to_the_same_receipt_as_the_intent(self):
        tok = self.login()
        s, made = self.turn(tok, 'sl1')
        by_intent = self.call('GET', '/AGENTS.md/receipt/sl1', token=tok)[1]
        real, seen = self.host.send, []
        def send(req, *a, **k):
            seen.append(req['op'])
            if req['op'] == 'world-resolve':
                return {'status': 'resolved', 'receipt': made['receipt']} if req['slug'] == 'babab-dabab' else {'status': 'error', 'message': 'no such slug'}
            return real(req, *a, **k)
        self.host.send = send
        by_slug = self.call('GET', '/AGENTS.md/receipt/babab-dabab', token=tok)
        self.assertEqual((by_slug[0], by_slug[1]), (200, by_intent))
        self.assertEqual(self.call('GET', '/AGENTS.md/receipt/sl1', token=tok)[1], by_intent)  # an intent never asks to resolve
        self.assertEqual(seen.count('world-resolve'), 1)

    def test_a_receipt_slug_resolves_to_the_same_receipt_hash_over_http(self):
        tok = self.login()
        receipt = self.turn(tok, 'sl2')[1]['receipt']
        s, r = self.call('GET', '/AGENTS.md/receipt/' + receipt['slug'], token=tok)
        self.assertEqual((s, r['receipt']['hash']), (200, receipt['hash']))

    def test_offers_wait_re_asks_until_an_offer_appears_or_time_runs_out(self):
        tok = self.login()
        asks, naps, real = [], [], self.host.send
        offer = {'height': 9, 'identity': {'principal': DID, 'intent': 'i'}, 'text': 'hello'}
        def send(req, *a, **k):
            if req['op'] != 'world-offers':
                return real(req, *a, **k)
            asks.append(req)
            return {'status': 'offers', 'offers': [offer] if len(asks) == 3 else [], 'more': False}
        self.host.send, self.front.sleep = send, naps.append
        s, r = self.call('GET', '/AGENTS.md/offers?wait=30&compact=1', token=tok)
        self.assertEqual((s, r, len(asks), naps), (200, {'status': 'offers', 'offers': ['hello'], 'height': 9}, 3, [1, 1]))
        asks.clear(), naps.clear()
        s, r = self.call('GET', '/AGENTS.md/offers?wait=99999', token=tok)  # bounded; the host never answers
        self.assertEqual((s, r['offers'], len(asks)), (200, [offer], 3))
        asks.clear(), naps.clear()
        self.host.send = lambda req, *a, **k: (asks.append(req), {'status': 'offers', 'offers': []})[1] if req['op'] == 'world-offers' else real(req, *a, **k)
        s, r = self.call('GET', '/AGENTS.md/offers?wait=99999', token=tok)
        self.assertEqual((len(asks), len(naps)), (31, 30))
        asks.clear()
        self.call('GET', '/AGENTS.md/offers', token=tok)
        self.assertEqual(len(asks), 1)

    def test_a_checkpoints_tokens_are_counted_unless_full(self):
        tok = self.login()
        real = self.host.send
        held = {'status': 'receipt', 'receipt': {'outcome': {'tag': 'suspended', 'activity': {'checkpoint': {'digest': 'd', 'tokens': [{'n': '1'}] * 5}}}}}
        self.host.send = lambda req: held if req['op'] == 'world-receipt' else real(req)
        s, r = self.call('GET', '/AGENTS.md/receipt/x', token=tok)
        self.assertEqual(r['receipt']['outcome']['activity']['checkpoint'], {'tokens': {'elided': 5}})  # the digest is a hash: omitted by default
        self.assertEqual(self.call('GET', '/AGENTS.md/receipt/x?full=1', token=tok)[1], held)


class Repl(FrontCase):
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
        s, e = self.repl(tok, modules=[{'name': 'Big', 'source': 'x' * 16385}], entry='pure')
        self.assertEqual(s, 413)

    def test_repl_runs_counter_bump_as_an_activity(self):
        tok = self.login()
        context = record(world={'tag': 'label', 'value': ''}, object={'tag': 'label', 'value': self.c},
                         principal={'tag': 'label', 'value': HANDLE}, handle={'tag': 'label', 'value': ''},
                         caller={'tag': 'label', 'value': ''}, intent={'tag': 'label', 'value': 'repl'}, height=nat(0), clock=nat(0),
                         inputOrigin=record(
                             kind={'tag': 'label', 'value': 'request'}, object={'tag': 'label', 'value': ''},
                             command={'tag': 'label', 'value': ''}, program={'tag': 'label', 'value': ''},
                             immediatelyPrevious={'tag': 'boolean', 'value': False}))
        # The REPL takes at most MAX_BODY: Counter's closure with Card exceeds it, so the REPL
        # runs the bare counter activity.
        s, r = self.repl(tok, modules=closure('Plan') + [{'name': 'Counter', 'source': REPL_COUNTER}], entry='bump', turn=True, **self.BIND,
                         arguments=[record(count=nat(2)), context])
        self.assertEqual((s, r['status']), (200, 'yielded'), r)

    def test_repl_activity_round_trip_with_checkpoint(self):
        tok = self.login()
        mods = [{'name': 'Package', 'source': PLANS}]
        s, y = self.repl(tok, modules=mods, entry='bump', turn=True, arguments=[nat(3)], **self.BIND)
        self.assertEqual((s, y['status']), (200, 'yielded'), y)
        s, done = self.repl(tok, modules=mods, entry='bump', checkpoint=y['checkpoint'], response=variant('written'), **self.BIND)
        self.assertEqual((s, done['status'], done['value']), (200, 'finished', nat(4)), done)

    def test_repl_imports_the_library_by_name_and_starts_an_activity_from_its_type(self):
        tok = self.login()
        context = record(world=label(''), object=label(self.c), principal=label(DID), handle=label(''), caller=label(''),
                         intent=label('repl-2'), height=nat(0), clock=nat(0),
                         inputOrigin=record(kind=label('request'), object=label(''), command=label(''), program=label(''),
                                            immediatelyPrevious={'tag': 'boolean', 'value': False}))
        s, y = self.repl(tok, source=REPL_COUNTER, entry='bump', arguments=[record(count=nat(2)), context],
                         object=self.c, intent='repl-2', roots=[{'object': self.c, 'version': 0}])
        self.assertEqual((s, y['status']), (200, 'yielded'), y)
        self.assertIsInstance(y['checkpoint']['tokens'], list)  # the REPL's checkpoint goes back whole, to resume
        s, done = self.repl(tok, source=REPL_COUNTER, entry='bump', checkpoint=y['checkpoint'], response=variant('written'),
                            object=self.c, intent='repl-2', roots=[{'object': self.c, 'version': 0}])
        self.assertEqual((s, done['status'], done['value']), (200, 'finished', nat(3)), done)

    def test_a_turn_start_fills_the_context_so_the_arguments_omit_it(self):
        tok = self.login()
        bind = dict(object=self.c, intent='repl-3', roots=[{'object': self.c, 'version': 0}])
        s, y = self.repl(tok, source=REPL_COUNTER, entry='bump', arguments=[record(count=nat(2))], **bind)
        self.assertEqual((s, y['status']), (200, 'yielded'), y)
        s, done = self.repl(tok, source=REPL_COUNTER, entry='bump', checkpoint=y['checkpoint'], response=variant('written'), **bind)
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

    def test_check_asks_the_world_and_sends_only_the_callers_modules(self):
        tok = self.login()
        seen, real = [], self.host.send
        def send(req, *a, **k):
            seen.append(req)
            return {'status': 'checked', 'entry': req['entry']} if req['op'] == 'world-check' else real(req, *a, **k)
        self.host.send = send
        s, ok = self.call('POST', '/AGENTS.md/check', {'source': REPL_COUNTER, 'entry': 'bump'}, tok)
        self.assertEqual((s, ok['status']), (200, 'checked'), ok)
        self.assertEqual(seen, [{'op': 'world-check', 'principal': DID, 'modules': [{'name': 'Package', 'source': REPL_COUNTER}], 'entry': 'bump'}])


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

    def test_a_heap_object_is_one_module_importing_the_library(self):
        tok = self.login()
        s, r = self.call('POST', '/AGENTS.md/heap/objects', {'object': 'tally', 'modules': [{'name': 'Tally', 'source': REPL_COUNTER}],
                                                             'entry': 'initial', 'seed': record(), 'intent': 'mk-tally'}, tok)
        self.assertEqual((s, r['status']), (200, 'created'), r)
        s, t = self.call('POST', '/AGENTS.md/heap/world/tally/bump', {'intent': 'b1'}, tok)
        self.assertEqual((s, t['status'], t['result']), (200, 'admitted', nat(1)), t)

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
        pool = self.hostd.heaps.pool
        first = pool[PEOPLE[names[0]]]
        self.assertEqual(self.call('GET', '/AGENTS.md/heap/world/h', token=toks[2])[0], 404)  # third heap evicts the first
        self.assertNotIn(PEOPLE[names[0]], pool)
        self.assertIsNone(first.proc)
        self.assertEqual(len(pool), 2)
        s, v = self.call('GET', '/AGENTS.md/heap/world/h', token=toks[0])
        self.assertEqual((s, v['version']), (200, 1), v)


class Pages(FrontCase):
    def test_list_card_source_offers_and_ids_with_slashes(self):
        tok = self.login()
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-g', 'object': 'garden',
                            'modules': closure('Garden'), 'entry': 'initial', 'seed': garden_state(0)})
        self.assertEqual(r['status'], 'created', r)
        s, listed = self.call('GET', '/AGENTS.md/world', token=tok)
        self.assertEqual((s, listed['ids']), (200, sorted(listed['ids'])), listed)
        self.assertLessEqual({self.c, DID, 'env/' + DID, 'garden', 'wake/' + DID}, set(listed['ids']))  # verify made the caller's avatar, env and wake
        self.assertEqual(self.call('GET', '/AGENTS.md/world?prefix=g', token=tok)[1]['ids'], ['garden'])
        s, card = self.call('GET', '/AGENTS.md/world/garden/card', token=tok)
        self.assertEqual((s, card['status']), (200, 'card'), card)
        self.assertIn('delvetalk garden plant', card['text'])
        self.assertNotIn('document', card)
        s, src = self.call('GET', '/AGENTS.md/world/garden/source', token=tok)
        self.assertEqual((s, src['status']), (200, 'inspected'), src)
        self.assertIn('def receive(', src['source'])
        self.assertIn('law owner:', src['law'])
        self.assertNotIn('methods', src)
        plant = [f for f in src['forms'] if f['action'] == 'plant'][0]
        self.assertEqual([f['name'] for f in plant['fields']], ['colour', 'seed'])
        self.assertIn('methods', self.call('GET', '/AGENTS.md/world/garden/source?full=1', token=tok)[1])
        # by spell, then by fields; the bell the garden makes has a slashed id, reached without escaping
        s, t = self.call('POST', '/AGENTS.md/world/garden/receive', {'intent': 'p1', 'spell': 'delvetalk garden plant\ncolour: amber\nseed: a moth bell'}, tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        self.assertIn('garden/bell/1', t['offers'][0]['text'])
        s, t = self.call('POST', '/AGENTS.md/world/garden/plant', {'intent': 'p2', 'fields': {'colour': 'silver', 'seed': 'a fern'}}, tok)
        self.assertEqual((s, t['status']), (200, 'admitted'), t)
        s, bell = self.call('GET', '/AGENTS.md/world/garden/bell/1', token=tok)
        self.assertEqual((s, bell['status'], bell['object']), (200, 'viewed', 'garden/bell/1'), bell)
        self.assertEqual(self.call('GET', '/AGENTS.md/world/garden%2Fbell%2F1', token=tok)[1]['object'], 'garden/bell/1')
        self.assertEqual(self.call('GET', '/AGENTS.md/world/garden/bell/2/card', token=tok)[1]['status'], 'card')
        s, offers = self.call('GET', '/AGENTS.md/offers', token=tok)
        mine = [o for o in offers['offers'] if o['identity']['intent'] in ('p1', 'p2')]  # the class's world holds other tests' offers too
        self.assertEqual((s, [o['identity']['intent'] for o in mine]), (200, ['p1', 'p2']), offers)
        after = mine[0]['height']
        self.assertIn('p1', [o['identity']['intent'] for o in offers['offers'] if o['height'] <= after])
        self.assertEqual([o['identity']['intent'] for o in self.call('GET', f'/AGENTS.md/offers?after={after}', token=tok)[1]['offers']][-1:], ['p2'])
        s, e = self.call('GET', '/AGENTS.md/nope', token=tok)
        self.assertEqual(s, 404)
        self.assertIn('world/<object>/source', e['hint'])

    def test_html_card_and_spell_form(self):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-plot', 'object': 'plot',
                            'modules': closure('Garden'), 'entry': 'initial', 'seed': garden_state(2)})
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
        s, _, page = self.request('GET', '/o/plot', headers={'Cookie': cookie})
        self.assertEqual(s, 200)
        self.assertIn(b'2 planted, newest first:', page)
        self.assertIn(b'prefers-color-scheme', self.request('GET', '/static/style.css')[2])
        before = self.host.send({'op': 'world-status'})['height']
        s, _, page = self.request('POST', '/o/plot/spell', raw='text=' + urllib.parse.quote('delvetalk plot plant'),
                                  headers={'Content-Type': 'application/x-www-form-urlencoded', 'Cookie': cookie})
        self.assertEqual(s, 200)
        self.assertGreater(self.host.send({'op': 'world-status'})['height'], before)
        self.assertIn(b'Result', page)
        self.assertEqual(self.request('GET', '/o/nowhere')[0], 404)
        self.assertEqual(self.request('POST', '/o/plot/spell', raw='text=x',
                                      headers={'Content-Type': 'application/x-www-form-urlencoded'})[0], 401)

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
        heights = [int(x) for x in __import__('re').findall(rb'<tr><td>(\d+)</td>', page)]
        self.assertEqual(len(heights), 20)
        self.assertEqual(heights, sorted(heights, reverse=True))
        self.assertEqual(heights[0], newest)


class StubHost:
    def __init__(self):
        self.ops = []

    def send(self, req):
        self.ops.append(req['op'])
        return {'status': 'viewed', 'version': 0} if req['op'] == 'world-view' else {'status': 'ok'}

    binary = BINARY


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


if __name__ == '__main__':
    unittest.main()
