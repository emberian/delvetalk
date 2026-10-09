"""Real HTTP, verified credentials and native effects; only external PDS reads mocked."""
import copy
import http.client
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import agent_api
import agent_heaps
import agent_identity
import desk
import portal
import source_object
import world

ORIGIN = 'https://delvetalk.example'
A = 'did:plc:' + 'a' * 24
B = 'did:plc:' + 'b' * 24


class ProofProvider:
    def __init__(self):
        self.posts = {}

    def resolve_handle(self, handle):
        return {'alice.delve.town': A, 'bob.delve.town': B}[handle]

    def fetch_post(self, uri):
        return copy.deepcopy(self.posts[uri])


class AgentHTTPTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / 'public'
        self.directory.mkdir()
        self.database = self.directory / 'world.json'
        self.protocol = source_object.load([{'name': 'Counter', 'source':
            (ROOT / 'examples/current-objects/Counter.obend').read_text()}], syntax='objective-bend-object')
        self.counter_law = {'profile': 'delvetalk-scoped-law', 'invoke': {'add': [A]},
                            'read': 'public', 'reprogram': [A], 'law': [A]}
        created = world.exchange(self.database, {'op': 'create', 'object': 'shared-counter',
            'principal': 'fixture-creator', 'intent': 'open-shared', 'protocol': self.protocol, 'law': self.counter_law},
            profile='compiled')
        self.assertEqual(created['kind'], 'committed', created)
        portal.save(self.directory / 'manifest.json', {'cafe': 'shared-counter',
                    'runtime': portal.bootstrap.history.runtime('compiled')})
        self.addCleanup(setattr, sys, 'dont_write_bytecode', sys.dont_write_bytecode)
        self.preview = portal.Portal(self.directory, public_origin=ORIGIN)
        self.provider = ProofProvider()
        self.identities = agent_identity.IdentityStore(self.root / 'identity', origin=ORIGIN, provider=self.provider)
        self.heaps = agent_heaps.HeapManager(self.root / 'heaps', self.database, shared_profile='compiled')
        self.addCleanup(self.heaps.close)
        self.api = agent_api.AgentAPI(self.identities, self.heaps, origin=ORIGIN)
        self.server = portal.make_server(self.preview, agents=self.api)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        def close():
            self.server.shutdown()
            self.server.server_close()
            thread.join()
        self.addCleanup(close)

    def request(self, method, path, payload=None, token=None, headers=None, raw=None):
        selected = {'Host': 'delvetalk.example'}
        if token is not None:
            selected['Authorization'] = 'Bearer ' + token
        if payload is not None or raw is not None:
            selected.update({'Content-Type': 'application/json', 'Origin': ORIGIN})
        selected.update(headers or {})
        body = raw if raw is not None else portal.canonical(payload) if payload is not None else None
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=50)
        try:
            connection.request(method, path, body=body, headers=selected)
            response = connection.getresponse()
            content = response.read()
            mime = response.getheader('Content-Type', '')
            if method != 'HEAD' and mime.startswith('application/json'):
                content = portal.loads(content)
            return response.status, content, mime
        finally:
            connection.close()

    def enroll(self, author=A):
        status, pending, _ = self.request('POST', '/AGENTS.md', {'did': author})
        self.assertEqual(status, 201, pending)
        token = pending['token']
        uri = 'at://' + author + '/town.delve.feed.post/proof-' + str(len(self.provider.posts))
        self.provider.posts[uri] = {'uri': uri, 'cid': 'proof-cid-' + str(len(self.provider.posts)),
            'authorDid': author, 'text': pending['challenge']['text'], 'basis': agent_identity.BASIS}
        status, verified, _ = self.request('POST', '/AGENTS.md/verify', {'uri': uri}, token)
        self.assertEqual(status, 200, verified)
        self.assertEqual(verified['did'], author)
        return token

    def turn(self, token, key, request, realm='private'):
        return self.request('POST', '/AGENTS.md/turn', {'realm': realm, 'intent': key,
            'requestJson': portal.canonical(request).decode()}, token)

    def inspect(self, token, object_id, realm='private'):
        status, result, _ = self.request('GET', '/AGENTS.md/world?realm=' + realm + '&object=' + object_id, token=token)
        self.assertEqual(status, 200, result)
        self.assertEqual(portal.loads(result['rootJson']), result['root'])
        return result['root']

    def notebook_state(self, token):
        return source_object.plain(source_object.state_data(self.inspect(token, 'notebook')))

    def create_private(self, token, name='counter', initial=None):
        protocol = copy.deepcopy(self.protocol)
        if initial is not None:
            protocol['initial']['model'] = source_object.compact_state(protocol,
                source_object.data({'count': initial}), entry='describe', path=[{'field': 'initial'}])
        author = self.identities.authenticate(token)['did']
        law = {**self.counter_law, 'invoke': {'add': [author]}, 'reprogram': [author], 'law': [author]}
        status, result, _ = self.turn(token, 'create-' + name, {'op': 'create', 'object': name,
            'protocol': protocol, 'law': law})
        self.assertEqual(status, 200, result)
        self.assertEqual(result['reply']['kind'], 'committed', result)
        return result['reply']['data']['root']

    def test_guide_enrollment_proof_and_credential_lifecycle(self):
        status, guide, mime = self.request('GET', '/AGENTS.md', headers={
            'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'})
        self.assertEqual(status, 200)
        self.assertTrue(mime.startswith('text/markdown'))
        self.assertIn(b'private studio', guide)
        self.assertIn(b'operation', guide)
        self.assertEqual(self.request('GET', '/AGENTS.md?token=never-in-a-url')[0], 400)
        status, pending, _ = self.request('POST', '/AGENTS.md', {'handle': 'alice.delve.town'})
        self.assertEqual(status, 201)
        self.assertEqual(self.request('GET', '/AGENTS.md/me', token=pending['token'])[0], 401)
        wrong = 'at://' + B + '/town.delve.feed.post/wrong-author'
        self.assertEqual(self.request('POST', '/AGENTS.md/verify', {'uri': wrong}, pending['token'])[0], 403)
        token = self.enroll()
        status, me, _ = self.request('GET', '/AGENTS.md/me', token=token)
        self.assertEqual(status, 200)
        self.assertEqual(me['did'], A)
        self.assertEqual(me['defaultRealm'], 'private')
        self.assertNotIn('token', me)
        status, rotated, _ = self.request('POST', '/AGENTS.md/token/rotate', {}, token)
        self.assertEqual(status, 200)
        self.assertEqual(self.request('GET', '/AGENTS.md/me', token=token)[0], 401)
        self.assertEqual(self.request('GET', '/AGENTS.md/me', token=rotated['token'])[1]['accountId'], me['accountId'])
        self.assertEqual(self.request('POST', '/AGENTS.md/token/revoke', {}, rotated['token'])[0], 200)
        self.assertEqual(self.request('GET', '/AGENTS.md/me', token=rotated['token'])[0], 401)
        self.assertIsNone(self.preview.principal)
        self.assertFalse(self.preview.interactive)

    def test_origin_body_and_identity_overrides_fail_before_native_work(self):
        token = self.enroll()
        for headers in ({'Origin': 'https://other.example'}, {'Host': 'other.example'},
                        {'Sec-Fetch-Site': 'cross-site'}, {'Content-Type': 'text/plain'}):
            with self.subTest(headers=headers):
                self.assertIn(self.request('POST', '/AGENTS.md/turn', {}, token, headers)[0], (400, 403))
        self.assertEqual(self.request('POST', '/AGENTS.md/turn', {'intent': 'anonymous', 'request': {}})[0], 403)
        self.assertEqual(self.request('POST', '/AGENTS.md/turn', token=token,
            raw=b'{"intent":"x","intent":"y","request":{}}')[0], 400)
        for request in ({'op': 'inspect', 'object': 'shared-counter', 'principal': A},
                        {'op': 'inspect', 'object': 'shared-counter', 'principal': B},
                        {'op': 'inspect', 'object': 'shared-counter', 'intent': 'other'}):
            self.assertEqual(self.turn(token, 'override', request)[0], 400)
        self.assertEqual(self.request('POST', '/AGENTS.md/turn', {'intent': 'two', 'request': {},
            'requestJson': '{}'}, token)[0], 400)
        with patch.object(agent_api, 'MAX_INPUT', 8):
            self.assertEqual(self.request('POST', '/AGENTS.md/turn', {'intent': 'too-large'}, token)[0], 400)
        self.assertEqual(self.request('GET', '/AGENTS.md/world?realm=../../someone-else', token=token)[0], 400)
        self.assertEqual(self.request('GET', '/AGENTS.md/world?accountId=elsewhere', token=token)[0], 400)
        self.assertEqual(self.request('GET', '/api/world')[1]['mode'], 'public-preview')
        self.assertEqual(self.request('POST', '/api/execute', {'draft': 'anything'}, token)[0], 403)

    def test_welcome_failure_preserves_verified_identity_and_trusted_evidence(self):
        status, pending, _ = self.request('POST', '/AGENTS.md', {'did': A})
        self.assertEqual(status, 201)
        uri = 'at://' + A + '/town.delve.feed.post/welcome-proof'
        self.provider.posts[uri] = {'uri': uri, 'cid': 'verified-proof-cid', 'authorDid': A,
            'text': pending['challenge']['text'], 'basis': agent_identity.BASIS}
        with patch.object(self.heaps, 'welcome', side_effect=TimeoutError('interrupted source admission')) as welcome:
            status, result, _ = self.request('POST', '/AGENTS.md/verify', {'uri': uri}, pending['token'])
        self.assertEqual(status, 200, result)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['membership']['status'], 'pending')
        self.assertEqual(welcome.call_args.args, ({'accountId': result['accountId'], 'did': A},
            {'uri': uri, 'cid': 'verified-proof-cid', 'basis': agent_identity.BASIS}))
        self.assertEqual(self.request('GET', '/AGENTS.md/me', token=pending['token'])[1]['did'], A)
        with patch.object(self.heaps, 'welcome', side_effect=AssertionError('invalid proof must never reach source enrollment')):
            self.assertEqual(self.request('POST', '/AGENTS.md/verify', {'uri': uri, 'did': B}, pending['token'])[0], 400)
        status, unconfigured, _ = self.request('POST', '/AGENTS.md/verify', {'uri': uri}, pending['token'])
        self.assertEqual(status, 200, unconfigured)
        self.assertEqual(unconfigured['membership']['status'], 'unconfigured')

    def test_two_accounts_private_roots_and_shared_current_law(self):
        alice, bob = self.enroll(A), self.enroll(B)
        huge = 10 ** 80 + 1
        own = self.create_private(alice, 'alice-only', huge)
        inspected = self.inspect(alice, 'alice-only')
        self.assertEqual(inspected, own)
        self.assertEqual(source_object.plain(source_object.state_data(inspected))['count'], huge)
        status, other, _ = self.request('GET', '/AGENTS.md/world', token=bob)
        self.assertEqual(status, 200, other)
        self.assertNotIn('alice-only', [item['object'] for item in other['objects']])
        status, refused, _ = self.turn(bob, 'cannot-cross-private', {
            'op': 'invoke', 'object': 'alice-only', 'expected': own, 'command': 'add', 'input': {'amount': 1}})
        self.assertEqual(status, 200, refused)
        self.assertEqual(refused['reply']['kind'], 'refused')
        shared = self.inspect(alice, 'shared-counter', 'shared')
        status, denied, _ = self.turn(bob, 'identity-is-not-authority', {'op': 'invoke', 'object': 'shared-counter',
            'expected': shared, 'command': 'add', 'input': {'amount': 1}}, 'shared')
        self.assertEqual(status, 200, denied)
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        status, committed, _ = self.turn(alice, 'shared-allowed', {'op': 'invoke', 'object': 'shared-counter',
            'expected': shared, 'command': 'add', 'input': {'amount': 3}}, 'shared')
        self.assertEqual(status, 200, committed)
        self.assertEqual(committed['reply']['kind'], 'committed')
        fresh = self.inspect(alice, 'shared-counter', 'shared')
        status, revoked, _ = self.turn(alice, 'revoke-own-grant', {'op': 'law', 'object': 'shared-counter',
            'expected': fresh, 'law': {**self.counter_law, 'invoke': {}, 'reprogram': [], 'law': []}}, 'shared')
        self.assertEqual(status, 200, revoked)
        self.assertEqual(revoked['reply']['kind'], 'committed')
        status, denied, _ = self.turn(alice, 'old-view-after-revocation', {'op': 'invoke', 'object': 'shared-counter',
            'expected': fresh, 'command': 'add', 'input': {'amount': 1}}, 'shared')
        self.assertEqual(status, 200, denied)
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        self.assertEqual(source_object.plain(source_object.state_data(self.inspect(alice, 'alice-only')))['count'], huge)

    def test_uncertain_reply_keeps_exact_intent_and_account_receipt(self):
        alice, bob = self.enroll(A), self.enroll(B)
        root = self.create_private(alice)
        request = {'op': 'invoke', 'object': 'counter', 'expected': root, 'command': 'add', 'input': {'amount': 7}}
        original = self.heaps._exchange
        def lose_reply(*arguments):
            original(*arguments)
            raise TimeoutError('simulated reply interruption')
        with patch.object(self.heaps, '_exchange', side_effect=lose_reply):
            self.assertEqual(self.turn(alice, 'same-turn', request)[0], 503)
        status, retained, _ = self.request('GET', '/AGENTS.md/receipt?intent=same-turn', token=alice)
        self.assertEqual(status, 200, retained)
        self.assertEqual(retained['status'], 'retained')
        status, retried, _ = self.turn(alice, 'same-turn', request)
        self.assertEqual(status, 200, retried)
        self.assertEqual(retried['reply'], retained['reply'])
        self.assertEqual(source_object.plain(source_object.state_data(self.inspect(alice, 'counter')))['count'], 7)
        self.assertEqual(self.request('GET', '/AGENTS.md/receipt?intent=same-turn', token=bob)[1]['status'], 'unknown')
        self.assertEqual(self.request('GET', '/AGENTS.md/receipt?realm=shared&intent=same-turn', token=alice)[1]['status'], 'unknown')
        self.assertEqual(self.turn(alice, 'same-turn', {**request, 'input': {'amount': 8}})[0], 400)

    def test_native_repl_retains_source_and_retry_without_reexecution(self):
        alice, bob = self.enroll(A), self.enroll(B)
        source = 'edition ObjectiveBend 1\ndef answer() -> Nat:\n  6n * 7n\n'
        payload = {'intent': 'private-source-1', 'modules': [{'name': 'Main', 'source': source}],
                   'entry': 'answer', 'arguments': []}
        status, result, _ = self.request('POST', '/AGENTS.md/repl', payload, alice)
        self.assertEqual(status, 200, result)
        self.assertEqual(result['evaluation']['value'], {'tag': 'natural', 'value': '42'}, result)
        self.assertEqual(result['receipt']['kind'], 'committed', result)
        root = self.inspect(alice, 'notebook')
        contribution = source_object.plain(source_object.state_data(root))['contributions']['payload']['head']
        self.assertEqual(contribution['actor'], A)
        self.assertIn(source, portal.loads(contribution['proposal']['original'])['modules'][0]['source'])
        self.assertEqual(portal.loads(result['evaluationJson']), result['evaluation'])
        with patch.object(self.heaps, '_evaluate', side_effect=AssertionError('retry must not evaluate again')):
            self.assertEqual(self.request('POST', '/AGENTS.md/repl', payload, alice)[1], result)
        self.assertEqual(self.inspect(alice, 'notebook'), root)
        self.assertEqual(self.notebook_state(bob)['count'], 0)
        self.assertEqual(self.request('POST', '/AGENTS.md/repl', {**payload, 'realm': 'shared'}, alice)[0], 403)
        self.assertEqual(self.request('GET', '/AGENTS.md/receipt?intent=private-source-1', token=alice)[1]['reply'], result['receipt'])

    def test_source_authored_form_retained_draft_and_links_share_one_identity(self):
        alice, bob = self.enroll(A), self.enroll(B)
        status, card, _ = self.request('GET', '/AGENTS.md/world?object=notebook&view=encounter', token=alice)
        self.assertEqual(status, 200, card)
        self.assertEqual(card['title'], 'Your private notebook')
        action = next(action for action in card['actions'] if action['label'] == 'Keep a thought')
        self.assertEqual({field['name'] for field in action['fields']}, {'thought'})
        form = card['forms']['prepare']
        status, draft, _ = self.request(form['method'], form['href'], {**form['body'],
            'action': action['id'], 'fields': {'thought': 'An idea to return to.'}}, alice)
        self.assertEqual(status, 200, draft)
        self.assertTrue(draft['canExecute'])
        self.assertIn('intent', draft)
        self.assertEqual(self.request('GET', draft['links']['self'], token=alice)[1], draft)
        self.assertEqual(self.request('GET', draft['links']['self'], token=bob)[0], 400)
        self.assertEqual(self.notebook_state(alice)['count'], 0)
        form = draft['forms']['execute']
        status, executed, _ = self.request(form['method'], form['href'], form['body'], alice)
        self.assertEqual(status, 200, executed)
        self.assertEqual(executed['kind'], 'committed')
        contribution = self.notebook_state(alice)['contributions']['payload']['head']
        self.assertEqual(contribution['actor'], A)
        self.assertEqual(contribution['proposal']['original'], 'An idea to return to.')
        self.assertEqual(self.request('GET', executed['links']['receipt'], token=alice)[1]['reply'], executed['reply'])
        self.assertEqual(self.request('GET', card['links']['self'], token=alice)[1], card)
        status, detail, _ = self.request('GET', card['links']['details'], token=alice)
        self.assertEqual(status, 200, detail)
        self.assertEqual(source_object.plain(source_object.state_data(detail['root']))['count'], 0)
        self.assertEqual(self.notebook_state(bob)['count'], 0)

    def test_source_desk_checks_installs_and_plays_a_private_program(self):
        alice = self.enroll(A)
        target = self.create_private(alice, 'lantern')
        status, granted, _ = self.turn(alice, 'grant-lantern-methods', {'op': 'law',
            'object': 'lantern', 'expected': target, 'law': {**self.counter_law,
                'invoke': {'light': [A], 'douse': [A]}}})
        self.assertEqual(status, 200, granted)
        self.assertEqual(granted['reply']['kind'], 'committed', granted)
        candidate = self.inspect(alice, 'source-desk')
        source = (ROOT / 'conformance/fixtures/AccountLantern.obend').read_text()
        migration = source_object.load([{'name': 'Main', 'source': source}],
                                       syntax='objective-bend-object')['initial']
        examples = """examples DelveTalk 1
case light the lantern
law visitor
as visitor
send light
expect result (String): A small sun for lost moths.
"""
        status, submitted, _ = self.turn(alice, 'submit-source', {'op': 'invoke', 'object': 'source-desk',
            'expected': candidate, 'command': 'submit', 'input': {'proposal': {
                'syntax': 'objective-bend-object', 'source': source, 'scenarios': examples},
                'migration': migration, 'target': 'lantern'}})
        self.assertEqual(status, 200, submitted)
        self.assertEqual(submitted['reply']['kind'], 'committed')
        pending = submitted['reply']['data']['root']
        status, requested, _ = self.turn(alice, 'request-source-check', {'op': 'invoke',
            'object': 'source-desk', 'expected': pending, 'command': 'requestCheck', 'input': {}})
        self.assertEqual(status, 200, requested)
        self.assertEqual(requested['reply']['kind'], 'committed', requested)
        pending = requested['reply']['data']['root']
        status, checked, _ = self.request('POST', '/AGENTS.md/repl', {'operation': 'check',
            'intent': 'source-compile:source-desk:1', 'object': 'source-desk', 'expectedJson': portal.canonical(pending).decode()}, alice)
        self.assertEqual(status, 200, checked)
        self.assertEqual(checked['receipt']['kind'], 'committed', checked)
        ready = checked['receipt']['data']['root']
        self.assertEqual(desk.candidate_state(ready)['status'], 'ready')
        status, card, _ = self.request('GET', '/AGENTS.md/world?object=source-desk&view=encounter', token=alice)
        self.assertEqual(status, 200, card)
        release = next(action for action in card['actions'] if action['label'] == 'Release this checked variation')
        form = card['forms']['prepare']
        status, draft, _ = self.request(form['method'], form['href'],
            {**form['body'], 'action': release['id'], 'fields': {}}, alice)
        self.assertEqual(status, 200, draft)
        form = draft['forms']['execute']
        status, adopted, _ = self.request(form['method'], form['href'], form['body'], alice)
        self.assertEqual(status, 200, adopted)
        self.assertEqual(adopted['reply']['kind'], 'committed', adopted)
        self.assertEqual(self.request('GET', adopted['links']['receipt'], token=alice)[1]['reply'], adopted['reply'])
        lantern = self.inspect(alice, 'lantern')
        status, played, _ = self.turn(alice, 'light-source', {'op': 'invoke', 'object': 'lantern',
            'expected': lantern, 'command': 'light', 'input': {}})
        self.assertEqual(status, 200, played)
        self.assertEqual(played['reply']['kind'], 'committed')
        self.assertEqual(source_object.plain(source_object.state_data(played['reply']['data']['root'])), {'lit': True})
        self.assertEqual(self.request('GET', '/AGENTS.md/receipt?intent=light-source', token=alice)[1]['reply'], played['reply'])

    def test_source_interpretation_retains_exact_actor_context_and_provider_retry(self):
        alice, bob = self.enroll(A), self.enroll(B)
        calls = []
        def provider(body):
            calls.append(copy.deepcopy(body))
            return {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text':
                portal.canonical({'action': 'note', 'fields': {'thought': 'A small sun for lost moths.'}}).decode()}]}
        self.heaps.model_provider = provider
        status, card, _ = self.request('GET', '/AGENTS.md/world?object=notebook&view=encounter', token=alice)
        self.assertEqual(status, 200, card)
        self.assertEqual(calls, [])
        self.assertEqual(self.request('GET', card['links']['self'], token=alice)[0], 200)
        self.assertEqual(calls, [])
        payload = {'operation': 'interpret', 'card': card['card'], 'text': 'Keep a thought about moths.'}
        self.assertEqual(self.request('POST', '/AGENTS.md/turn', payload, bob)[0], 400)
        self.assertEqual(calls, [])
        status, proposed, _ = self.request('POST', '/AGENTS.md/turn', payload, alice)
        self.assertEqual(status, 200, proposed)
        self.assertEqual(proposed['status'], 'ready', proposed)
        self.assertEqual(proposed['via'], 'source')
        self.assertEqual(len(calls), 1)

        self.assertEqual(self.notebook_state(alice)['count'], 0)
        self.assertEqual(self.request('POST', '/AGENTS.md/turn', payload, alice)[1], proposed)
        self.assertEqual(len(calls), 1)
        status, saved, _ = self.request('GET', proposed['links']['self'], token=alice)
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved['input']['text'], payload['text'])
        self.assertEqual(self.request('GET', proposed['links']['self'], token=bob)[0], 400)
        form = proposed['draft']['forms']['execute']
        status, admitted, _ = self.request(form['method'], form['href'], form['body'], alice)
        self.assertEqual(status, 200, admitted)
        self.assertEqual(admitted['kind'], 'committed', admitted)
        contribution = self.notebook_state(alice)['contributions']['payload']['head']
        self.assertEqual(contribution['actor'], A)
        self.assertEqual(contribution['proposal']['original'], payload['text'])
        self.assertEqual(contribution['proposal']['policy'], 'notebook-policy-v2')
        self.assertEqual(self.notebook_state(bob)['count'], 0)
        status, current, _ = self.request('GET', '/AGENTS.md/world?object=notebook&view=encounter', token=alice)
        self.assertEqual(status, 200, current)
        offered = next(action for action in current['actions'] if action['label'] == 'Keep this thought')
        status, draft, _ = self.request('POST', '/AGENTS.md/turn', {'operation': 'prepare',
            'card': current['card'], 'action': offered['id'], 'fields': {}}, alice)
        self.assertEqual(status, 200, draft)
        form = draft['forms']['execute']
        status, completed, _ = self.request(form['method'], form['href'], form['body'], alice)
        self.assertEqual(status, 200, completed)
        self.assertEqual(completed['kind'], 'committed', completed)
        self.assertEqual(self.notebook_state(alice)['outcomes']['payload']['head']['status'], 'kept')
        self.assertEqual(len(calls), 1)

    def test_uncertain_provider_is_retained_and_literal_form_still_bypasses_it(self):
        alice = self.enroll()
        calls = []
        def unavailable(body):
            calls.append(body)
            raise TimeoutError('fixture provider lost its reply')
        self.heaps.model_provider = unavailable
        status, card, _ = self.request('GET', '/AGENTS.md/world?object=notebook&view=encounter', token=alice)
        self.assertEqual(status, 200, card)
        action = next(action for action in card['actions'] if action['label'] == 'Keep a thought')
        literal = {'operation': 'interpret', 'card': card['card'], 'text': action['token'] +
            ' ' + portal.canonical({'thought': 'Literal without a provider'}).decode()}
        status, selected, _ = self.request('POST', '/AGENTS.md/turn', literal, alice)
        self.assertEqual(status, 200, selected)
        self.assertEqual(selected['status'], 'proposed', selected)
        self.assertEqual(selected['via'], 'tokens')
        self.assertEqual(calls, [])
        payload = {'operation': 'interpret', 'card': card['card'], 'text': 'Keep this unfinished thought.'}
        status, uncertain, _ = self.request('POST', '/AGENTS.md/turn', payload, alice)
        self.assertEqual(status, 200, uncertain)
        self.assertEqual(uncertain['status'], 'uncertain', uncertain)
        self.assertNotIn('draft', uncertain)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.request('POST', '/AGENTS.md/turn', payload, alice)[1], uncertain)
        self.assertEqual(self.request('GET', uncertain['links']['self'], token=alice)[0], 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.notebook_state(alice)['count'], 0)


if __name__ == '__main__':
    unittest.main()
