"""Portal composition regressions using retained custody and the real Lean host."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import http.client
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import portal as p


class PortalAdversarial(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.database = self.directory / 'world.json'
        protocol = p.loads((ROOT / 'protocols/counter/protocol.json').read_bytes())
        protocol['affordances'] = {'add': {'label': 'Add to the counter', 'fields': {
            'amount': {'type': 'nat', 'minimum': 1, 'maximum': 10}}}}
        self.create('counter', protocol)
        p.save(self.directory / 'manifest.json', {
            'cafe': 'counter', 'runtime': p.bootstrap.history.runtime('transactions')})
        self.app = self.restart()

    def create(self, name, protocol):
        result = p.bootstrap.desk_module.world.exchange(self.database, {
            'op': 'create', 'object': name, 'principal': 'operator',
            'intent': 'create-' + name, 'protocol': protocol, 'law': ['moss']},
            profile='transactions')
        self.assertEqual(result['kind'], 'committed', result)

    def restart(self):
        return p.Portal(self.directory, principal='moss', allow_local_actions=True)

    def prepare(self, card=None):
        card = card or self.app.object('counter')
        return self.app.prepare({'card': card['card'], 'action': 'a1', 'fields': {'amount': 3}})

    def serve(self):
        server = p.make_server(self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(close)
        return server

    def test_foreign_get_cannot_allocate_durable_cards(self):
        server = self.serve()
        before = list((self.app.state / 'cards').iterdir())
        for headers in ({'Origin': 'https://unrelated.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                try:
                    connection.request('GET', '/api/object?object=counter', headers=headers)
                    response = connection.getresponse()
                    response.read()
                    self.assertEqual(response.status, 403)
                finally:
                    connection.close()
                self.assertEqual(list((self.app.state / 'cards').iterdir()), before)

    def test_busy_execute_custody_is_bounded_and_draft_remains_retryable(self):
        draft = self.prepare()
        before = self.database.read_bytes()
        # A second process/session can own the same custody lock. The HTTP
        # socket timeout cannot bound this wait inside the request handler.
        with (self.app.state / 'execute.lock').open('a') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with patch.object(p, 'LOCK_TIMEOUT', 0.05):
                started = time.monotonic()
                with self.assertRaises(TimeoutError):
                    self.app.execute({'draft': draft['draft']})
                self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(self.database.read_bytes(), before)
            self.assertIsNone(self.app.draft(draft['draft'])['outcome'])
        self.assertEqual(self.restart().execute({'draft': draft['draft']})['kind'], 'committed')

    def test_simultaneous_retry_of_one_draft_has_one_admission(self):
        draft = self.prepare()
        other = self.restart()
        before = len(self.app.snapshot()['receipts'])
        start = threading.Barrier(2)
        def send(app):
            start.wait(timeout=3)
            return app.execute({'draft': draft['draft']})
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(send, (self.app, other)))
        self.assertEqual(results[0]['kind'], 'committed')
        self.assertEqual(results[0], results[1])
        snapshot = self.app.snapshot()
        self.assertEqual(snapshot['objects']['counter']['state']['count'], 3)
        self.assertEqual(len(snapshot['receipts']), before + 1)
        self.assertEqual(self.restart().draft(draft['draft'])['outcome'], 'committed')

    def test_distinct_concurrent_drafts_do_not_rebase_each_other(self):
        card = self.app.object('counter')
        drafts = [self.prepare(card), self.prepare(card)]
        apps = [self.app, self.restart()]
        start = threading.Barrier(2)
        def send(index):
            start.wait(timeout=3)
            return apps[index].execute({'draft': drafts[index]['draft']})
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(send, range(2)))
        self.assertEqual(sorted(result['kind'] for result in results), ['committed', 'refused'])
        refusal = next(result for result in results if result['kind'] == 'refused')
        self.assertEqual(refusal['reply']['data'], 'stale read root')
        self.assertEqual(self.app.snapshot()['objects']['counter']['state']['count'], 3)
        self.assertEqual(self.app.card(card['card']), card)

    def test_prepared_action_faces_current_revoked_authority(self):
        draft = self.prepare()
        saved = self.app._read('drafts', draft['draft'])
        revoked = p.bootstrap.desk_module.world.exchange(self.database, {
            'op': 'law', 'object': 'counter', 'principal': 'moss', 'intent': 'revoke-moss',
            'expected': saved['request']['expected'], 'law': []}, profile='transactions')
        self.assertEqual(revoked['kind'], 'committed', revoked)
        reply = self.app.execute({'draft': draft['draft']})
        self.assertEqual(reply['kind'], 'refused')
        self.assertEqual(reply['reply']['data'], 'unauthorized')
        self.assertEqual(self.app.snapshot()['objects']['counter']['state']['count'], 0)
        self.assertEqual(self.restart().execute({'draft': draft['draft']}), reply)

    def test_interpretation_cannot_mutate_the_saved_catalogue_or_execute(self):
        card = self.app.object('counter')
        before = self.database.read_bytes()
        def malicious_proposer(text, public):
            public['actions'][0]['fields'][0]['maximum'] = 1000
            return {'action': 'a1', 'fields': {'amount': 1000}}
        self.app.proposer = malicious_proposer
        result = self.app.interpretation({'card': card['card'], 'text': 'add a thousand'})
        self.assertEqual(result['status'], 'clarify')
        self.assertEqual(self.app.card(card['card']), card)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(list((self.app.state / 'drafts').glob('*.json')), [])
        self.app.proposer = lambda *_: {'action': 'a1', 'fields': {'amount': 3}}
        proposal = self.app.interpretation({'card': card['card'], 'text': 'add three'})
        self.assertEqual(proposal['status'], 'proposed')
        self.assertEqual(self.database.read_bytes(), before)
        draft = self.app.prepare({'card': card['card'], 'action': proposal['action'], 'fields': proposal['fields']})
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.app.execute({'draft': draft['draft']})['kind'], 'committed')

    def test_token_from_large_valid_catalogue_remains_usable(self):
        names = ['touch-' + str(index) for index in range(65)]
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {},
            'commands': {name: {'require': [], 'set': {}, 'result': ['literal', 'ok'], 'outbox': []}
                         for name in names},
            'affordances': {name: {'fields': {}} for name in names}}
        self.create('many-actions', protocol)
        card = self.app.object('many-actions')
        self.assertEqual(len(card['actions']), 65)
        self.app.proposer = lambda *_: self.fail('Copied tokens must never require a model call')
        proposal = self.app.interpretation({'card': card['card'], 'text': card['actions'][-1]['token']})
        self.assertEqual(proposal['status'], 'proposed', proposal)
        self.assertEqual(proposal['action'], card['actions'][-1]['id'])
        draft = self.app.prepare({'card': card['card'], 'action': proposal['action'], 'fields': proposal['fields']})
        self.assertEqual(self.app.execute({'draft': draft['draft']})['kind'], 'committed')

    def test_full_custody_preserves_old_draft_and_receipt_recovery(self):
        card = self.app.object('counter')
        draft = self.prepare(card)
        with patch.object(p, 'MAX_SAVED', 1):
            with self.assertRaisesRegex(ValueError, 'custody is full'):
                self.app.object('counter')
            with self.assertRaisesRegex(ValueError, 'custody is full'):
                self.prepare(card)
            restarted = self.restart()
            self.assertEqual(restarted.card(card['card']), card)
            self.assertEqual(restarted.draft(draft['draft']), draft)
            reply = restarted.execute({'draft': draft['draft']})
            self.assertEqual(reply['kind'], 'committed')
            self.assertEqual(self.restart().execute({'draft': draft['draft']}), reply)


if __name__ == '__main__':
    unittest.main()
