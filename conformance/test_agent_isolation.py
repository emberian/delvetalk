"""Two proved accounts through HTTP and actual private native receiving heaps.

The only stand-in is the external proof provider; no network proof is fetched.
"""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import agent_api
import agent_heaps
import agent_identity
import portal


class ProofProvider:
    def __init__(self):
        self.posts = {}

    def fetch_post(self, uri):
        return dict(self.posts[uri])


def program(secret):
    return {'profile': 'delvetalk-local-v1', 'initial': {'secret': secret, 'count': 0},
            'affordances': {'touch': {'label': 'Touch', 'fields': {}}},
            'commands': {'touch': {'require': [], 'set': {'count': ['literal', 1]},
                                   'result': ['state', 'secret'], 'outbox': []}}}


class AgentIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.base = Path(cls.temp.name)
        cls.provider = ProofProvider()
        cls.identities = agent_identity.IdentityStore(cls.base / 'identity',
            origin='https://agents.example.invalid', provider=cls.provider)
        cls.heaps = agent_heaps.HeapManager(cls.base / 'heaps', cls.base / 'shared.json',
                                          timeout=10, max_active=2)
        cls.addClassCleanup(cls.heaps.close)
        cls.api = agent_api.AgentAPI(cls.identities, cls.heaps, origin='https://agents.example.invalid')
        cls.portal = SimpleNamespace(public=False, public_origin=None, principal='operator-must-stay-fixed')
        cls.server = portal.make_server(cls.portal, agents=cls.api)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        def close_server():
            cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        cls.addClassCleanup(close_server)
        cls.tokens, cls.accounts = {}, {}
        for name, symbol in [('alice', 'a'), ('bob', 'b')]:
            author = 'did:plc:' + symbol * 24
            enrollment = cls.identities.enroll({'did': author})
            uri = 'at://' + author + '/town.delve.feed.post/' + name
            cls.provider.posts[uri] = {'uri': uri, 'cid': 'test-cid-' + name,
                'authorDid': author, 'text': enrollment['challenge']['text'],
                'basis': 'isolated-test-provider'}
            cls.identities.verify(enrollment['token'], {'uri': uri})
            cls.tokens[name] = enrollment['token']
            cls.accounts[name] = cls.identities.authenticate(enrollment['token'])

    def http(self, method, suffix, token=None, payload=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=60)
        headers = {'Content-Type': 'application/json'}
        if token is not None: headers['Authorization'] = 'Bearer ' + token
        try:
            connection.request(method, '/AGENTS.md' + suffix,
                               body=None if payload is None else json.dumps(payload), headers=headers)
            response = connection.getresponse()
            value = json.loads(response.read())
            return response.status, value
        finally:
            connection.close()

    def turn(self, who, intent, request, realm='private'):
        return self.http('POST', '/turn', self.tokens[who],
                         {'realm': realm, 'intent': intent, 'request': request})

    def test_pending_credential_and_client_identity_cannot_select_a_heap(self):
        pending = self.identities.enroll({'did': 'did:plc:' + 'c' * 24})
        before = sorted(p.name for p in (self.base / 'heaps').iterdir() if p.is_dir())
        status, _ = self.http('GET', '/world', pending['token'])
        self.assertEqual(status, 401)
        after = sorted(p.name for p in (self.base / 'heaps').iterdir() if p.is_dir())
        self.assertEqual(after, before)
        for query in ('?accountId=' + self.accounts['alice']['accountId'],
                      '?realm=../identity', '?path=/etc/passwd', '?token=' + self.tokens['alice']):
            status, value = self.http('GET', '/world' + query, self.tokens['bob'])
            self.assertEqual(status, 400, value)
        status, _ = self.turn('bob', 'principal-override', {'op': 'inspect', 'object': 'notebook',
                            'principal': self.accounts['alice']['did']})
        self.assertEqual(status, 400)
        self.assertEqual(self.portal.principal, 'operator-must-stay-fixed')

    def test_concurrent_identical_names_intents_and_foreign_roots_stay_in_account(self):
        def create(who):
            return self.turn(who, 'same-create-intent', {'op': 'create', 'object': 'same-name',
                'protocol': program(who + '-private-sentinel'), 'law': [self.accounts[who]['did']]})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, ('alice', 'bob')))
        roots = {}
        for who, (status, value) in zip(('alice', 'bob'), results):
            self.assertEqual(status, 200, value)
            self.assertEqual(value['reply']['kind'], 'committed', value)
            roots[who] = value['reply']['data']['root']
            self.assertEqual(roots[who]['state']['secret'], who + '-private-sentinel')
            status, retained = self.http('GET', '/receipt?intent=same-create-intent', self.tokens[who])
            self.assertEqual(status, 200)
            self.assertEqual(retained['reply'], value['reply'])
        status, value = self.turn('bob', 'foreign-preimage', {'op': 'invoke', 'object': 'same-name',
            'expected': roots['alice'], 'command': 'touch', 'input': {}})
        self.assertEqual(status, 200, value)
        self.assertEqual(value['reply']['kind'], 'refused')
        self.assertNotIn('alice-private-sentinel', json.dumps(value))
        status, bob = self.http('GET', '/world?object=same-name', self.tokens['bob'])
        self.assertEqual(status, 200, bob)
        self.assertEqual(bob['root'], roots['bob'])
        status, alice_only = self.turn('alice', 'only-alice-create', {'op': 'create', 'object': 'alice-only',
            'protocol': program('unpublished-alice-source'), 'law': [self.accounts['alice']['did']]})
        self.assertEqual(status, 200, alice_only)
        status, missing = self.http('GET', '/world?object=alice-only', self.tokens['bob'])
        self.assertNotEqual(status, 200)
        self.assertNotIn('unpublished-alice-source', json.dumps(missing))
        self.assertNotIn(str(self.base), json.dumps(missing))
        status, missing_receipt = self.http('GET', '/receipt?intent=only-alice-create', self.tokens['bob'])
        self.assertEqual(status, 200)
        self.assertEqual(missing_receipt['status'], 'unknown')
        self.assertEqual(self.portal.principal, 'operator-must-stay-fixed')

    def test_private_authority_does_not_become_shared_authority(self):
        status, made = self.turn('alice', 'shared-create', {'op': 'create', 'object': 'shared-restricted',
            'protocol': program('deliberately-public'), 'law': [self.accounts['alice']['did']]}, realm='shared')
        self.assertEqual(status, 200, made)
        self.assertEqual(made['reply']['kind'], 'committed', made)
        status, visible = self.http('GET', '/world?realm=shared&object=shared-restricted', self.tokens['bob'])
        self.assertEqual(status, 200, visible)
        status, refused = self.turn('bob', 'shared-denied', {'op': 'invoke', 'object': 'shared-restricted',
            'expected': visible['root'], 'command': 'touch', 'input': {}}, realm='shared')
        self.assertEqual(status, 200, refused)
        self.assertEqual(refused['reply']['kind'], 'refused')
        self.assertEqual(refused['reply']['data'], 'unauthorized')
        status, private = self.http('GET', '/world?object=shared-restricted', self.tokens['bob'])
        self.assertNotEqual(status, 200, private)

    def test_foreign_card_and_draft_aliases_cannot_prepare_or_execute(self):
        status, made = self.turn('alice', 'card-object-create', {'op': 'create', 'object': 'card-object',
            'protocol': program('alice-card-secret'), 'law': [self.accounts['alice']['did']]})
        self.assertEqual(status, 200, made)
        status, card = self.http('GET', '/world?object=card-object&view=encounter', self.tokens['alice'])
        self.assertEqual(status, 200, card)
        action = card['actions'][0]['id']
        status, wrong = self.http('POST', '/turn', self.tokens['bob'],
            {'operation': 'prepare', 'card': card['card'], 'action': action, 'fields': {}})
        self.assertNotEqual(status, 200, wrong)
        self.assertNotIn('alice-card-secret', json.dumps(wrong))
        self.assertNotIn(str(self.base), json.dumps(wrong))
        status, draft = self.http('POST', '/turn', self.tokens['alice'],
            {'operation': 'prepare', 'card': card['card'], 'action': action, 'fields': {}})
        self.assertEqual(status, 200, draft)
        for who, realm in [('bob', 'private'), ('alice', 'shared')]:
            status, wrong = self.http('POST', '/turn', self.tokens[who],
                {'operation': 'execute', 'realm': realm, 'draft': draft['draft']})
            self.assertNotEqual(status, 200, wrong)
            self.assertNotIn('alice-card-secret', json.dumps(wrong))
            self.assertNotIn(str(self.base), json.dumps(wrong))
        status, first = self.http('POST', '/turn', self.tokens['alice'],
            {'operation': 'execute', 'draft': draft['draft']})
        self.assertEqual(status, 200, first)
        self.assertEqual(first['kind'], 'committed', first)
        status, again = self.http('POST', '/turn', self.tokens['alice'],
            {'operation': 'execute', 'draft': draft['draft']})
        self.assertEqual(status, 200)
        self.assertEqual(again['reply'], first['reply'])

    def test_repl_intent_cannot_alias_boolean_with_number_or_expose_other_notebook(self):
        payload = {'intent': 'bool-evaluation', 'modules': [{'name': 'Identity',
            'source': 'edition ObjectiveBend 1\ndef identity(value: Bool) -> Bool:\n  value\n'}],
            'entry': 'identity', 'arguments': [{'tag': 'boolean', 'value': True}]}
        status, first = self.http('POST', '/repl', self.tokens['alice'], payload)
        self.assertEqual(status, 200, first)
        self.assertEqual(first['evaluation']['status'], 'finished', first['evaluation'])
        self.assertEqual(first['receipt']['kind'], 'committed', first['receipt'].get('data'))
        changed = {**payload, 'arguments': [{'tag': 'boolean', 'value': 1}]}
        status, conflict = self.http('POST', '/repl', self.tokens['alice'], changed)
        self.assertEqual(status, 400, conflict)
        status, again = self.http('POST', '/repl', self.tokens['alice'], payload)
        self.assertEqual(status, 200)
        self.assertEqual(again['evaluation'], first['evaluation'])
        self.assertEqual(again['receipt'], first['receipt'])
        status, bob = self.http('GET', '/world?object=notebook', self.tokens['bob'])
        self.assertEqual(status, 200)
        self.assertEqual(bob['root']['state']['evaluations'], 0)

    def test_rotation_keeps_heap_identity_and_revokes_old_token(self):
        author = 'did:plc:' + 'd' * 24
        pending = self.identities.enroll({'did': author})
        uri = 'at://' + author + '/town.delve.feed.post/rotation'
        self.provider.posts[uri] = {'uri': uri, 'cid': 'rotation-cid', 'authorDid': author,
            'text': pending['challenge']['text'], 'basis': 'isolated-test-provider'}
        self.identities.verify(pending['token'], {'uri': uri})
        status, before = self.http('GET', '/world', pending['token'])
        self.assertEqual(status, 200, before)
        status, rotated = self.http('POST', '/token/rotate', pending['token'], {})
        self.assertEqual(status, 200, rotated)
        status, _ = self.http('GET', '/world', pending['token'])
        self.assertEqual(status, 401)
        status, after = self.http('GET', '/world', rotated['token'])
        self.assertEqual(status, 200, after)
        self.assertEqual(after['world'], before['world'])
        self.assertEqual(after['objects'], before['objects'])
        self.assertEqual(self.identities.authenticate(rotated['token'])['did'], author)


if __name__ == '__main__':
    unittest.main()
