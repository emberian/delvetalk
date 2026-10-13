"""Method-bound procedure transport, real JWT keys and an offline world.

Refuted by an invalid token calling the host, a retry writing twice, private
offers in a public answer, a preview leaving any durable trace, or a plan
being sent as several turns. Real host composition is in Requests and Try.
"""
import base64
import copy
import concurrent.futures
import hashlib
import http.client
import json
import tempfile
import unittest
from pathlib import Path

from tests.host import bounds, serve, served
from tests.test_bridge import modules
from tests.test_http import DID
from tests.test_lexicons import DOCS, record_problems, validate
from tests.test_repo import World
from tests.test_serviceauth import Documents, Tokens
from transport import bridge, delve, identity, mirror
from transport.atproto.cbor import block
from transport.atproto.sign import Key
from transport.config import Config
from transport.host import HostClient, plain
from transport.http import Front, MAX_BODY, RATE
from transport.repo import NS
from transport.state import State
from tests.wire import nat, record


class ActsWorld(World):
    """A private thing offering a card; the journal is World's canonical chain."""
    def __init__(self):
        super().__init__()
        self.calls, self.answers, self.version = [], {}, 0

    def send(self, q):
        self.calls.append(copy.deepcopy(q))
        op = q['op']
        if op == 'bounds':
            return bounds()
        if op == 'world-reach':
            return {'status': 'reached', 'object': 'diary', 'how': 'spell'}
        if op == 'world-view':
            return {'status': 'denied' if q['principal'] == 'anonymous' else 'viewed'}
        if op == 'world-receipt':
            return copy.deepcopy(self.answers.get((q['principal'], q['identity']), {'status': 'unknown'}))
        if op == 'world-entry':
            return copy.deepcopy(next((r for r in self.answers.values() if r['receipt']['hash'] == q['hash'] and
                                       r['receipt']['identity']['principal'] == q['principal']), {'status': 'unknown'}))
        if op == 'world-offers':
            return {'status': 'offers', 'offers': [o for r in self.answers.values() for o in r.get('offers', [])
                                                  if o['identity']['principal'] == q['principal'] and o['height'] > q.get('after', 0)]}
        if op not in ('world-turn', 'world-try'):
            return super().send(q)
        ident = (q['principal'], q.get('identity'))
        if op == 'world-turn' and ident in self.answers:
            return copy.deepcopy(self.answers[ident])
        if q.get('if') and q['if'][0]['version'] != self.version:
            return {'status': 'refused', 'class': 'moved', 'line': 'refused moved: diary moved',
                    'moved': [{'object': 'diary', 'was': q['if'][0]['version'], 'now': self.version}]}
        fields = plain(q['argument'])
        text = fields.get('text', '')
        refused = 'refuse-third' in text
        out = {'tag': 'refused', 'class': 'cardRefused', 'reason': 'refused third: stop'} if refused else {
            'tag': 'admitted', 'writes': [{'object': 'diary', 'version': self.version + 1, 'cid': str(block({'v': self.version + 1})[0])}]}
        entry = {'height': len(self.entries) + 1, 'identity': {'principal': q['principal'], 'intent': q.get('identity')},
                 'roots': [{'object': 'diary', 'version': self.version}], 'outcome': out}
        entry['hash'] = str(block(entry)[0])
        rc = {**entry, 'slug': identity.slug(entry['hash'])}
        offers = [] if refused else [{'text': 'a secret card\n', 'height': rc['height'], 'identity': entry['identity']}]
        reply = {'status': out['tag'], 'object': 'diary', 'receipt': rc, 'inPublic': False,
                 'offers': offers, 'revealed': ['private line']}
        if op == 'world-try':
            return {**reply, 'tried': True, 'against': {'height': len(self.entries)}}
        self.entries.append(entry)
        if not refused:
            self.version += 1
        self.answers[ident] = reply
        return copy.deepcopy(reply)


class ProcedureCase(Tokens, unittest.TestCase):
    def make_host(self, directory):
        return ActsWorld()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now, self.serial = [1000.0], 0
        self.documents = Documents()
        self.keys = {DID: Key(self.documents.repo(DID)['key'])}
        self.st = State(tmp.name, config=Config())
        self.host = self.make_host(tmp.name)
        ident = identity.Identity(self.st, delve.Client(self.documents), clock=lambda: self.now[0])
        self.front = serve(Front(self.st, self.host, ident, ('127.0.0.1', 0), clock=lambda: self.now[0]))
        self.addCleanup(self.front.server_close)
        self.addCleanup(self.front.shutdown)
        if hasattr(self.host, 'calls'):
            self.host.calls.clear()

    def request(self, proc='act', body=None, token=None, method='POST', raw=None, ctype='application/json'):
        nsid = NS + proc
        token = self.token({'lxm': nsid}) if token is None else token
        c = http.client.HTTPConnection(*self.front.server_address, timeout=10)
        c.request(method, '/xrpc/' + nsid, raw if raw is not None else json.dumps(body or {}),
                  {'Authorization': 'Bearer ' + token, 'Content-Type': ctype})
        r = c.getresponse()
        status, data, headers = r.status, json.loads(r.read()), dict(r.getheaders())
        c.close()
        return status, data, headers

    def act(self, intent='one', **more):
        return {'call': {'spell': 'delvetalk diary plant / seed: secret'}, 'intent': intent, **more}

    def view_valid(self, view, name='answerView'):
        doc = DOCS[NS + 'defs']
        self.assertEqual(validate(view, doc['defs'][name], doc), [], view)


class XrpcActs(ProcedureCase):
    def test_spell_identity_retry_returns_first_receipt_and_public_answer_is_anonymous(self):
        status, view, _ = self.request(body=self.act())
        self.assertEqual(status, 200, view)
        self.view_valid(view)
        self.assertEqual(view['outcome']['status'], 'admitted')
        self.assertEqual(view['offers'], ['a secret card\n'])
        self.assertIn('private line', view['trace']['revealed'])
        self.assertEqual([e['identity'] for e in self.host.entries], [{'principal': DID, 'intent': 'one'}])
        second = self.request(body={**self.act(), 'call': {'object': 'diary', 'verb': 'different', 'fields': {}}})[1]
        self.assertEqual(second['receipt'], view['receipt'])
        self.assertEqual(len(self.host.entries), 1)
        digest = base64.b32encode(hashlib.sha256(b'one').digest()).decode().lower()[:26]
        key = f'xrpc.{DID}.{digest}'
        public = mirror.answer_records(self.st.answers)[key]
        self.assertEqual(record_problems(public), [], public)
        self.assertEqual(public['source'], {'$type': NS + 'answer#provenance', 'iss': DID, 'intent': 'one'})
        self.assertNotIn('secret', json.dumps(public))
        self.assertNotIn('offers', public)
        self.assertNotIn('trace', public)
        self.assertEqual(self.front.repo.mirrored(self.host, 'answer', key, 'anonymous'), public)

    def test_invalid_tokens_never_call_host_or_write_entries(self):
        cases = [self.token({'lxm': NS + 'act', 'aud': 'did:web:wrong.example'}),
                 self.token({'lxm': NS + 'act', 'exp': 999}), self.token({'lxm': NS + 'try'}),
                 self.token({'lxm': NS + 'act'}, key=Key.generate()),
                 self.token({'lxm': NS + 'act'}, header={'alg': 'none'}), 'bad', '']
        for token in cases:
            with self.subTest(token=token[:24]):
                self.host.calls.clear()
                status, body, _ = self.request(body=self.act(), token=token)
                self.assertEqual(status, 401, body)
                self.assertEqual(self.host.calls, [])
                self.assertEqual(self.host.entries, [])
        token = self.token({'lxm': NS + 'act'})
        self.assertEqual(self.request(body=self.act(), token=token)[0], 200)
        self.host.calls.clear()
        status, body, _ = self.request(body=self.act(), token=token)
        self.assertEqual((status, body['error']), (401, 'InvalidToken'))
        self.assertEqual(self.host.calls, [])
        self.assertEqual(len(self.host.entries), 1)

    def test_try_is_exact_twin_act_without_a_receipt_files_or_body_log(self):
        twin = ActsWorld()
        body = self.act(intent='preview-secret')
        before = len(self.host.entries)
        status, preview, _ = self.request('try', body)
        self.assertEqual(status, 200, preview)
        self.view_valid(preview, 'previewView')
        self.assertEqual(preview['outcome']['status'], 'previewed')
        self.assertNotIn('receipt', preview)
        self.assertNotIn('slug', json.dumps(preview))
        self.assertEqual(len(self.host.entries), before)
        self.assertEqual(mirror.answer_records(self.st.answers), {})
        self.assertFalse(self.st.outbox.exists())
        [call] = [q for q in self.host.calls if q['op'] == 'world-try']
        done = twin.send({**call, 'op': 'world-turn'})
        self.assertEqual(preview['card'], done['offers'][0]['text'])
        self.assertEqual(preview['cardCid'], str(block(preview['card'])[0]))
        self.assertEqual(preview['trace']['writes'][0]['stateCid'], done['receipt']['outcome']['writes'][0]['cid'])
        acted = self.request(body=body)[1]
        for field in ('card', 'cardCid', 'offers', 'trace'):
            self.assertEqual(preview[field], acted[field])
        log = '\n'.join(self.access_lines(2))
        self.assertIn('POST /xrpc/' + NS + 'try 200', log)
        for secret in ('preview-secret', 'plant', 'seed', 'secret', 'card'):
            self.assertNotIn(secret, log)

    def test_plan_is_one_host_turn_and_third_refusal_writes_no_object(self):
        calls = [{'spell': 'delvetalk diary plant / seed: ' + s} for s in ('first', 'second', 'refuse-third')]
        status, view, _ = self.request('plan', {'calls': calls, 'intent': 'plan'})
        self.assertEqual(status, 200, view)
        self.assertEqual(view['outcome']['status'], 'refused')
        self.assertEqual(self.host.version, 0)
        self.assertEqual(len(self.host.entries), 1)
        [call] = [q for q in self.host.calls if q['op'] == 'world-turn']
        self.assertEqual(plain(call['argument'])['text'], 'delvetalk plan\n' + '\n'.join(c['spell'] for c in calls))
        self.view_valid(view)
        status, body, _ = self.request('plan', {'calls': [{'object': 'diary', 'verb': 'plant'}], 'intent': 'bad-plan'})
        self.assertEqual((status, body['error']), (400, 'InvalidRequest'))
        self.assertEqual(len(self.host.entries), 1)

    def test_stale_if_is_a_refused_moved_answer_without_an_entry(self):
        self.host.version = 2
        status, view, _ = self.request(body=self.act(**{'if': [{'object': 'diary', 'version': 1}]}))
        self.assertEqual(status, 200, view)
        self.assertEqual((view['outcome']['status'], view['outcome']['class']), ('refused', 'moved'))
        self.assertEqual(view['outcome']['moved'], [{'object': 'diary', 'was': 1, 'now': 2}])
        self.assertEqual(self.host.entries, [])
        self.assertNotIn('receipt', view)

    def test_wrong_http_methods_are_rejected_before_host(self):
        for proc, method in [('act', 'GET'), ('try', 'GET'), ('plan', 'GET'), ('getEntry', 'POST')]:
            with self.subTest(proc=proc):
                self.host.calls.clear()
                status, body, _ = self.request(proc, self.act(), method=method)
                self.assertIn(status, (400, 405), body)
                self.assertEqual(body['error'], 'InvalidRequest')
                self.assertEqual(self.host.calls, [])

    def test_malformed_body_budget_world_and_call_bounds(self):
        bad = [{}, self.act(intent=''), self.act(intent='x' * 257), self.act(call={'spell': 1}),
               self.act(call={'spell': 'x', 'object': 'diary', 'verb': 'plant'}),
               self.act(call={'object': 'diary', 'verb': 'plant', 'fields': []}),
               self.act(**{'if': [{'object': 'diary', 'version': True}]}),
               self.act(world='another'), self.act(world='scratch/../one')]
        for body in bad:
            with self.subTest(body=body):
                self.host.calls.clear()
                status, reply, _ = self.request(body=body)
                self.assertEqual((status, reply['error']), (400, 'InvalidRequest'))
                self.assertEqual(self.host.calls, [])
                if body.get('world') == 'scratch/../one':
                    self.assertIn('scratch/<name>', reply['message'])
        for raw in ('[1]', '{', '{"x":NaN}', '{"intent":"a","intent":"b"}', '{"call":{"object":"diary","verb":"plant","fields":{"x":"\\ud800"}},"intent":"x"}',
                    'x' * (MAX_BODY + 1)):
            status, body, _ = self.request(raw=raw)
            self.assertEqual((status, body['error']), (400, 'InvalidRequest'))
        status, body, _ = self.request(raw='call=secret', ctype='application/x-www-form-urlencoded')
        self.assertEqual((status, body['error']), (400, 'InvalidRequest'))
        self.assertEqual(self.host.entries, [])

    def test_maximum_plan_and_intent_and_issuer_rate_bucket(self):
        status, body, _ = self.request('plan', {'calls': [{'spell': 'delvetalk diary plant'}] * 8, 'intent': 'x' * 256, 'world': 'town'})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.request('plan', {'calls': [{'spell': 'x'}] * 9, 'intent': 'too-many'})[0], 400)
        for _ in range(RATE - 2):
            self.assertEqual(self.request('try', {'call': self.act()['call']})[0], 200)
        status, body, headers = self.request('try', {'call': self.act()['call']})
        self.assertEqual((status, body['error']), (429, 'RateLimitExceeded'))
        self.assertIn('Retry-After', headers)

    def test_spell_utf8_and_body_byte_budgets_are_enforced_at_the_boundary(self):
        prefix = 'delvetalk diary plant / seed: '
        spell = prefix + 'x' * (4096 - len(prefix))
        self.assertEqual(self.request('try', {'call': {'spell': spell}})[0], 200)
        for too_long in (spell + 'x', prefix + 'é' * 2048):
            status, body, _ = self.request('try', {'call': {'spell': too_long}})
            self.assertEqual((status, body['error']), (400, 'InvalidRequest'))
        body = {'call': {'object': 'diary', 'verb': 'plant', 'fields': {'padding': ''}}}
        overhead = len(json.dumps(body).encode())
        body['call']['fields']['padding'] = 'x' * (MAX_BODY - overhead)
        raw = json.dumps(body)
        self.assertEqual(len(raw.encode()), MAX_BODY)
        self.assertEqual(self.request('try', raw=raw)[0], 200)
        status, refused, _ = self.request('try', raw=raw + ' ')
        self.assertEqual((status, refused['error']), (400, 'InvalidRequest'))
        self.assertEqual(self.host.entries, [])
        self.assertEqual(mirror.answer_records(self.st.answers), {})

    def test_bare_audience_and_two_issuers_with_one_intent_have_distinct_entries(self):
        token = self.token({'lxm': NS + 'act', 'aud': self.front.repo.did})
        self.assertEqual(self.request(body=self.act(), token=token)[0], 200)
        other = 'did:plc:' + 'b' * 24
        self.keys[other] = Key(self.documents.repo(other)['key'])
        token = self.token({'iss': other, 'lxm': NS + 'act'})
        self.assertEqual(self.request(body=self.act(), token=token)[0], 200)
        self.assertEqual({e['identity']['principal'] for e in self.host.entries}, {DID, other})
        self.assertEqual(len(mirror.answer_records(self.st.answers)), 2)

    def test_concurrent_fresh_tokens_for_one_intent_make_one_entry_and_answer(self):
        tokens = [self.token({'lxm': NS + 'act'}) for _ in range(4)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda token: self.request(body=self.act(), token=token), tokens))
        self.assertEqual([r[0] for r in replies], [200] * 4, replies)
        self.assertEqual(len({r[1]['receipt']['entry']['$link'] for r in replies}), 1)
        self.assertEqual(len(self.host.entries), 1)
        self.assertEqual(len(mirror.answer_records(self.st.answers)), 1)

    def test_retry_keeps_the_first_public_projection_even_if_a_receipt_reread_lacks_offers(self):
        self.assertEqual(self.request(body=self.act())[0], 200)
        source = bridge.xrpc_source(DID, 'one')
        path = bridge.answer_path(self.st, source)
        first = json.loads(path.read_text())
        bridge.write_answer(self.st, source, {'outcome': {'status': 'admitted', 'line': 'changed'}, 'receipt': first['receipt']})
        self.assertEqual(json.loads(path.read_text()), first)


class XrpcHost(ProcedureCase):
    """The same front over a real host: private projection and plan composition."""
    def make_host(self, directory):
        serving = served(str(Path(directory) / 'serve'), cleanup=self.addCleanup)
        host = HostClient(serving.sock)
        made = host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-diary', 'object': 'diary',
                          'modules': modules('''  match world.offer({to: "", document: Document.text("a secret")}):
    case offered(_): 1n
    case _: 0n'''), 'entry': 'initial', 'seed': record(seen=nat(5)), 'read': {'principals': [DID]}})
        self.assertEqual(made['status'], 'created', made)
        return host

    def height(self):
        return self.host.send({'op': 'world-status'})['height']

    def test_private_spell_is_one_entry_and_caller_alone_gets_card_and_trace(self):
        before = self.height()
        body = {'call': {'spell': 'delvetalk diary plant\nseed: a\ncolour: amber'}, 'intent': 'private'}
        status, view, _ = self.request(body=body)
        self.assertEqual(status, 200, view)
        self.assertEqual(view['outcome']['status'], 'admitted', view)
        self.assertEqual(self.height(), before + 1)
        self.assertIn('a secret', view['card'])
        self.view_valid(view)
        [public] = mirror.answer_records(self.st.answers).values()
        self.assertEqual(record_problems(public), [], public)
        self.assertNotIn('secret', json.dumps(public))
        self.assertNotIn('diary', json.dumps(public))
        self.assertNotIn('trace', public)
        self.assertNotIn('offers', public)
        again = self.request(body={**body, 'call': {'object': 'diary', 'verb': 'different'}})[1]
        self.assertEqual(again['receipt'], view['receipt'])
        self.assertEqual(again.get('offers'), view.get('offers'))
        self.assertEqual(self.height(), before + 1)

    def test_real_try_leaves_no_entry_or_file_and_equals_the_act_at_the_same_head(self):
        body = {'call': {'object': 'diary', 'verb': 'plant', 'fields': {'seed': 'a', 'colour': 'amber'}}, 'intent': 'private-try'}
        before = self.height()
        status, preview, _ = self.request('try', body)
        self.assertEqual(status, 200, preview)
        self.view_valid(preview, 'previewView')
        self.assertEqual(preview['outcome']['status'], 'previewed')
        self.assertNotIn('receipt', preview)
        self.assertEqual(self.height(), before)
        self.assertEqual(mirror.answer_records(self.st.answers), {})
        self.assertFalse(self.st.outbox.exists())
        status, acted, _ = self.request(body=body)
        self.assertEqual(status, 200, acted)
        self.assertEqual(acted['outcome']['status'], 'admitted', acted)
        for k in ('card', 'cardCid', 'offers', 'trace'):
            self.assertEqual(preview[k], acted[k])
        self.assertNotIn('private-try', '\n'.join(self.access_lines(2)))

    def test_real_plan_third_refusal_discards_the_first_two_writes(self):
        from tests.test_chain import town_garden
        town_garden(lambda **q: self.host.send(q), id='garden-1')
        before = self.height()
        version = self.host.send({'op': 'world-view', 'principal': DID, 'object': 'garden-1'})['version']
        calls = [{'spell': 'delvetalk garden-1 plant\nseed: ' + s + '\ncolour: amber'} for s in ('one', 'two')]
        calls.append({'spell': 'delvetalk missing-card rain'})
        status, view, _ = self.request('plan', {'calls': calls, 'intent': 'atomic'})
        self.assertEqual(status, 200, view)
        self.assertEqual(view['outcome']['status'], 'refused', view)
        self.assertEqual(self.height(), before + 1)
        self.view_valid(view)
        self.assertEqual(self.host.send({'op': 'world-view', 'principal': DID, 'object': 'garden-1'})['version'], version)
        for obj in ('garden-1/bell/1', 'garden-1/bell/2'):
            self.assertEqual(self.host.send({'op': 'world-view', 'principal': DID, 'object': obj})['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
