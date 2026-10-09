"""Captured workflow offers retain their root sets across Portal preparation."""
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
import composite_offers
import portal
import portal_bridge


class EditorPortalJourney(unittest.TestCase):
    """Actual HTTP framing, native admission and authenticated Town replies."""
    def setUp(self):
        from conformance import test_editor_generations as fixture
        from conformance import test_town_forge_journey as posts
        import clerk
        import town
        import town_cards
        self.fixture, self.posts = fixture, posts
        self.A, self.B, self.issuer = 'did:plc:' + 'a' * 24, 'did:plc:' + 'b' * 24, posts.ISSUER
        self.target, self.editor, self.factory = 'instrument', 'editor', 'candidates'
        temporary = tempfile.TemporaryDirectory(prefix='editor-portal-')
        self.addCleanup(temporary.cleanup)
        self.addCleanup(setattr, sys, 'dont_write_bytecode', sys.dont_write_bytecode)
        self.base = Path(temporary.name)
        self.home = self.base / 'world'
        makers = [self.A, self.B]
        seeds = [
            {'id': self.target, 'syntax': 'objective-bend-spell@2', 'source': fixture.SOURCE.encode(),
             'law': {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'add': makers},
                     'reprogram': makers, 'law': makers}},
            {'id': self.editor, 'syntax': 'objective-bend-spell@3',
             'source': fixture.generator.editor_source(self.target, self.factory).encode(),
             'law': fixture.generator.editor_law(makers)},
            {'id': self.factory, 'syntax': 'protocol-json@1',
             'source': fixture.desk.canonical(fixture.generator.factory('compiler', makers)),
             'law': {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'make': makers},
                     'reprogram': makers, 'law': makers}}]
        seed = fixture.workspace.initialize(self.home, seeds, principal='operator', profile='compiled',
            entry_objects=[self.editor, self.target], world_id='urn:test:editor-portal')
        self.client = fixture.desk.Desk(self.home / 'world.json', self.home / 'artifacts', profile='compiled')
        self.pds = posts.PublicRecords()
        self.receiver = clerk.Clerk(self.base / 'clerk', self.pds)
        self.receiver.attach(self.home, portal.world.snapshot(self.client.database)['objects'], makers,
            expected_genesis=seed['genesis'], expected_seed_head=seed['head'], runtime_profile='compiled')
        self.book = town_cards.CardBook.create(self.base / 'cards', issuer_did=self.issuer,
            world_id='urn:test:editor-portal', runtime=portal.bootstrap.history.runtime('compiled'))
        self.receiver.upgrade(self.receiver.profile()['sha256'], town_cards={
            'path': str(self.book.path.resolve()), 'issuers': [self.issuer], 'metadata': self.book.metadata()})
        self.operator = town.Town(self.receiver.state, request=self.pds)
        self.app = portal.Portal(self.home)
        self.serial = 0

    def root(self, name):
        return self.client.inspect(name)

    def next_key(self):
        self.serial += 1
        return 'turn-' + str(self.serial)

    def server(self, app):
        server = portal.make_server(app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def http(self, port, path, payload=None, public=False):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
        self.addCleanup(connection.close)
        headers = {'Host': 'delvetalk.example' if public else '127.0.0.1:' + str(port)}
        if payload is not None:
            headers.update({'Content-Type': 'application/json',
                            'Origin': 'https://delvetalk.example' if public else 'http://127.0.0.1:' + str(port)})
            headers['X-Delvetalk-CSRF'] = self.http(port, '/api/world', public=public)['csrf']
        connection.request('GET' if payload is None else 'POST', path,
            None if payload is None else portal.canonical(payload), headers)
        response = connection.getresponse()
        value = portal.loads(response.read())
        self.assertEqual(response.status, 200, value)
        return value

    def repository_turn(self, draft, author):
        bridge = portal_bridge.Bridge(self.app)
        prepared = bridge.prepare(draft['draft'])
        key = self.next_key()
        uri, cid = f'at://{author}/{portal_bridge.clerk.COLLECTION}/{key}', 'cid-' + key
        self.pds.records[uri] = (cid, prepared['record'])
        bridge.bind(draft['draft'], uri, cid)
        receipt = self.receiver.receive(uri, cid)
        outcome = bridge.reconcile(draft['draft'], self.receiver)
        self.assertEqual(outcome['receipt'], receipt)
        return receipt

    def draft(self, command, fields=None, *, card=None):
        card = card or self.app.object(self.editor)
        action = next(action for action in card['actions'] if action['command'] == command)
        self.assertIn('offer', action)
        return self.app.prepare({'card': card['card'], 'action': action['id'], 'fields': fields or {}})

    def compile_candidate(self, name):
        import compiler_queue
        queue = compiler_queue.CompilerQueue(self.base / ('queue-' + name), self.client.database,
            self.client.artifact_store, profile='compiled')
        candidate = self.factory + '/' + name
        job = queue.enqueue(candidate, 'compiler', self.next_key(), self.root(candidate))['job']
        result = queue.run(limit=1, deadline_seconds=60)
        self.assertEqual(result['errors'], [], result)
        self.assertEqual(result['blocked'], [], result)
        self.assertEqual(queue.inspect(job)['phase'], 'finished')
        self.assertEqual(self.root(candidate)['state']['status'], 'ready')

    def town_reply(self, captured, author):
        import town_cards
        key = self.next_key()
        parent = {'uri': f'at://{self.issuer}/{portal_bridge.clerk.FEED}/card-{key}', 'cid': 'card-' + key}
        self.pds.records[parent['uri']] = (parent['cid'], {'$type': portal_bridge.clerk.FEED, 'text': captured['body']})
        self.operator.bind(captured['alias'], parent['uri'], parent['cid'])
        uri = f'at://{author}/{portal_bridge.clerk.FEED}/{key}'
        action = composite_offers.action(captured['offer'])
        spell = town_cards.spell(captured['alias'], action, {}, selector=action['command'])
        self.pds.records[uri] = ('cid-' + key, {'$type': portal_bridge.clerk.FEED, 'text': spell,
            'reply': {'root': parent, 'parent': parent}})
        response = self.operator.receive(uri, 'cid-' + key)
        return response, (uri, 'cid-' + key)

    def test_two_authors_make_submit_review_rebase_adopt_and_retry(self):
        import subprocess
        import town
        import worker
        public = portal.Portal(self.home, public_origin='https://delvetalk.example')
        public_port = self.server(public)
        before = self.client.database.read_bytes()
        paths = sorted(str(path.relative_to(self.home)) for path in self.home.rglob('*'))
        card = self.http(public_port, '/api/object?object=editor', public=True)
        make = next(action for action in card['actions'] if action['command'] == 'make')
        preview = self.http(public_port, '/api/prepare',
            {'card': card['card'], 'action': make['id'], 'fields': {'name': 'first'}}, public=True)
        self.assertFalse(preview['canExecute'])
        self.assertEqual(preview['absence'], ['candidates/first'])
        self.assertEqual(set(preview['wire']['reads']), {'editor', 'instrument', 'candidates', 'candidates/first'})
        self.assertNotIn('principal', public._read('drafts', preview['draft'])['request'])
        self.assertEqual(self.client.database.read_bytes(), before)
        self.assertEqual(sorted(str(path.relative_to(self.home)) for path in self.home.rglob('*')), paths)

        private_port = self.server(self.app)
        first_card = self.http(private_port, '/api/object?object=editor')
        action = next(item for item in first_card['actions'] if item['command'] == 'make')
        first = self.http(private_port, '/api/prepare',
            {'card': first_card['card'], 'action': action['id'], 'fields': {'name': 'first'}})
        allocated = self.repository_turn(first, self.A)
        self.assertEqual(allocated['reply']['kind'], 'committed', allocated)
        self.assertIn('candidates/first', self.receiver.config()['objects'])
        stale = self.draft('make', {'name': 'other'}, card=first_card)
        refused = self.repository_turn(stale, self.B)
        self.assertEqual(refused['reply']['data'], 'stale read root')
        self.assertNotIn('candidates/other', self.app.snapshot()['objects'])

        fields = {'syntax': 'objective-bend-spell@2', 'source': self.fixture.DOUBLE,
                  'examples': (self.fixture.PACKAGE / 'double.examples').read_text()}
        submitted = self.repository_turn(self.draft('submit', fields), self.A)
        self.assertEqual(submitted['reply']['kind'], 'committed', submitted)
        retained = self.root('candidates/first')['state']['proposal']
        self.assertEqual(retained['source'], fields['source'])
        self.assertEqual(retained['scenarios'], fields['examples'])
        self.compile_candidate('first')
        review = self.operator.capture_offer(self.editor, 'review', alias='review-first')
        reviewed, review_source = self.town_reply(review, self.B)
        self.assertEqual(reviewed['receipt']['reply']['kind'], 'committed', reviewed)
        self.assertEqual(reviewed['receipt']['request']['principal'], self.B)

        # Ordinary use advances the baseline. The offered adoption is still
        # presented; actual Editor code refuses it and retains every object.
        played = self.client.exchange({'op': 'invoke', 'object': self.target, 'principal': self.B,
            'intent': self.next_key(), 'expected': self.root(self.target), 'command': 'add', 'input': {'amount': 1}})
        self.assertEqual(played['kind'], 'committed')
        drift = self.repository_turn(self.draft('adopt'), self.A)
        self.assertEqual(drift['reply']['kind'], 'refused')
        self.assertIn('Target drifted', drift['reply']['data'])

        rebased = self.repository_turn(self.draft('make', {'name': 'rebased'}), self.A)
        self.assertEqual(rebased['reply']['kind'], 'committed')
        self.assertEqual(self.repository_turn(self.draft('submit', fields), self.A)['reply']['kind'], 'committed')
        self.compile_candidate('rebased')
        review = self.operator.capture_offer(self.editor, 'review', alias='review-rebased')
        reviewed, _ = self.town_reply(review, self.B)
        self.assertEqual(reviewed['receipt']['reply']['kind'], 'committed', reviewed)
        adoption = self.operator.capture_offer(self.editor, 'adopt', alias='adopt-rebased')
        denied, _ = self.town_reply(adoption, self.B)
        self.assertEqual(denied['receipt']['reply']['kind'], 'refused', denied)

        # A lost process reply remains uncertain, then exact native receipt
        # recovery precedes new pins or any attempt to admit another request.
        local_state = self.base / 'local-maker'
        local = portal.Portal(self.home, state=local_state, principal=self.A, allow_local_actions=True)
        adopt_card = local.object(self.editor)
        action = next(item for item in adopt_card['actions'] if item['command'] == 'adopt')
        draft = local.prepare({'card': adopt_card['card'], 'action': action['id']})
        old_target = self.root(self.target)
        command = worker.command
        def lost_reply(*args, **kwargs):
            command(*args, **kwargs)
            raise subprocess.TimeoutExpired('simulated-lost-reply', 1)
        with patch.object(worker, 'command', side_effect=lost_reply):
            uncertain = local.execute({'draft': draft['draft']})
        self.assertEqual(uncertain['kind'], 'uncertain')
        restarted = portal.Portal(self.home, state=local_state, principal=self.A, allow_local_actions=True)
        with patch.object(restarted, '_pins', side_effect=AssertionError('receipt first')), patch.object(
                worker, 'command', side_effect=AssertionError('do not admit twice')):
            installed = restarted.execute({'draft': draft['draft']})
        self.assertEqual(installed['kind'], 'committed', installed)
        self.assertEqual(self.root(self.target)['state'], old_target['state'])
        self.assertNotEqual(self.root(self.target)['protocol'], old_target['protocol'])
        # Original authenticated reply still recovers after another generation
        # and the source change, without re-reading or reinterpreting its card.
        self.pds.records.clear()
        recovered = town.Town(self.receiver.state, request=self.pds).receive(*review_source)
        self.assertEqual(recovered['receipt']['reply']['kind'], 'committed')
        stale_after_install = self.repository_turn(self.draft('make', {'name': 'too-late'}, card=first_card), self.A)
        self.assertEqual(stale_after_install['reply']['data'], 'stale read root')
        self.assertEqual(self.root('candidates/first')['state']['status'], 'ready')
        self.assertEqual(self.root('candidates/rebased')['state']['status'], 'ready')


class CapturedWorkflowDrafts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.addCleanup(setattr, sys, 'dont_write_bytecode', sys.dont_write_bytecode)
        self.root = {'protocol': {'name': 'An authored object', 'commands': {
            'touch': {'require': [], 'set': {}, 'result': ['literal', 'ok'], 'outbox': []}}},
            'state': {}, 'law': ['maker'], 'version': 0}
        portal.save(self.home / 'manifest.json', {'cafe': 'editor', 'runtime': {'name': 'compiled', 'files': {}}})
        portal.save(self.home / 'world.json', {'objects': {'editor': self.root, 'target': self.root}, 'receipts': []})
        self.offer = {'format': composite_offers.FORMAT, 'title': 'A retained workflow',
            'label': 'Review both readings', 'command': 'review',
            'reads': {'editor': copy.deepcopy(self.root), 'target': copy.deepcopy(self.root)},
            'calls': [{'op': 'observe', 'object': 'target'},
                      {'object': 'editor', 'command': 'touch', 'inputFrom': 0}],
            'fields': [], 'bindings': []}

    def capture(self, app):
        # Exercise the common retained-offer boundary independently of the
        # Editor source discovery tested by the native journey below.
        action = composite_offers.action(self.offer)
        identity = app._store('cards', {'view': {'mode': 'raw', 'object': 'editor', 'root': self.root},
            'card': {'object': 'editor', 'version': 0, 'title': self.offer['title'],
                     'actions': [action], 'panel': 'main'},
            'offers': {action['id']: self.offer}, 'runtime': app.runtime, 'historyLength': 0})
        return identity

    def test_preparation_retains_both_roots_and_exports_existing_receiving_wire(self):
        app = portal.Portal(self.home)
        identity = self.capture(app)
        changed = copy.deepcopy(self.root)
        changed['version'] = 1
        portal.save(app.database, {'objects': {'editor': changed, 'target': changed}, 'receipts': []})
        draft = app.prepare({'card': identity, 'action': 'a1'})
        self.assertEqual(draft['object'], 'editor')
        self.assertEqual(draft['version'], 0)
        self.assertEqual(draft['reads'], [{'object': 'editor', 'version': 0}, {'object': 'target', 'version': 0}])
        self.assertEqual(draft['wire']['reads'], {key: {'expected': self.root} for key in ('editor', 'target')})
        self.assertEqual(app._read('drafts', draft['draft'])['request']['reads'], self.offer['reads'])
        self.assertEqual(portal.Portal(self.home).draft(draft['draft']), draft)
        with self.assertRaises(ValueError):
            app.prepare({'card': identity, 'action': 'a1', 'reads': {}})

    def test_public_offer_is_export_only_and_draft_survives_card_eviction(self):
        app = portal.Portal(self.home, public_origin='https://delvetalk.example')
        identity = self.capture(app)
        draft = app.prepare({'card': identity, 'action': 'a1'})
        self.assertFalse(draft['canExecute'])
        self.assertNotIn('principal', draft['wire'])
        self.assertNotIn('intent', draft['wire'])
        app.preview.records.pop(('cards', identity))
        self.assertEqual(app.draft(draft['draft'])['wire'], draft['wire'])
        with self.assertRaises(PermissionError):
            app.execute({'draft': draft['draft']})
        self.assertFalse(app.state.exists())

    def test_source_capture_uses_one_snapshot_and_missing_dependency_is_visible(self):
        from conformance.test_source_view_offers import offer_view
        view = offer_view()
        view['object'] = 'editor'
        app = portal.Portal(self.home)
        portal.save(app.database, {'objects': {'editor': view['root'], 'peer': self.root}, 'receipts': []})
        with patch.object(app, '_view', return_value=view), patch.object(app, 'snapshot', wraps=app.snapshot) as read:
            card = app.object('editor')
        read.assert_called_once()
        action = next(item for item in card['actions'] if item.get('offer') == 'touch')
        self.assertTrue(action['available'])
        draft = app.prepare({'card': card['card'], 'action': action['id']})
        self.assertEqual(set(draft['wire']['reads']), {'editor', 'peer'})
        portal.save(app.database, {'objects': {'editor': view['root']}, 'receipts': []})
        with patch.object(app, '_view', return_value=view):
            unavailable = app.object('editor')
        action = next(item for item in unavailable['actions'] if item.get('offer') == 'touch')
        self.assertFalse(action['available'])
        self.assertIn('peer', action['reason'])
        with self.assertRaises(ValueError):
            app.prepare({'card': unavailable['card'], 'action': action['id']})
        # Earlier capture remains complete despite the later missing dependency.
        self.assertEqual(app.draft(draft['draft'])['wire'], draft['wire'])


class CompositeRepositoryHandoff(unittest.TestCase):
    def test_exact_transaction_handoff_derives_author_and_reconciles_native_receipt(self):
        from conformance import test_portal_bridge as bridge_tests
        bridge_tests.PortalBridgeTest.setUp(self)
        self.receiver.upgrade(self.receiver.profile()['sha256'], runtime_profile='transactions')
        portal.save(self.receiver.state / 'manifest.json',
            {'runtime': portal.bootstrap.history.runtime('transactions'), 'cafe': 'counter'})
        app = portal.Portal(self.receiver.state, state=self.base / 'transaction-portal')
        root = app.snapshot()['objects']['counter']
        offer = {'format': composite_offers.FORMAT, 'title': 'Two steps', 'label': 'Add twice',
            'command': 'add-twice', 'reads': {'counter': root},
            'calls': [{'object': 'counter', 'command': 'add', 'input': {'amount': amount}} for amount in (1, 2)],
            'fields': [], 'bindings': []}
        card = app.object('counter')
        saved = app._read('cards', card['card'])
        saved['card']['actions'] = [composite_offers.action(offer)]
        saved['offers'] = {'a1': offer}
        identity = app._store('cards', saved)
        draft = app.prepare({'card': identity, 'action': 'a1'})
        bridge = portal_bridge.Bridge(app)
        prepared = bridge.prepare(draft['draft'])
        self.assertEqual(prepared['wire']['reads'], {'counter': {'expected': root}})
        uri, cid = 'at://' + bridge_tests.delve.DID + '/' + portal_bridge.clerk.COLLECTION + '/two', 'cid-two'
        self.pds.records['two'] = {'uri': uri, 'cid': cid, 'value': prepared['record']}
        bridge.bind(draft['draft'], uri, cid)
        receipt = self.receiver.receive(uri, cid)
        self.assertEqual(receipt['request']['reads'], {'counter': root})
        self.assertEqual(receipt['request']['principal'], bridge_tests.delve.DID)
        outcome = bridge.reconcile(draft['draft'], self.receiver)
        self.assertEqual(outcome['kind'], 'committed', outcome)
        self.assertEqual(outcome['receipt'], receipt)
        self.assertEqual(app.snapshot()['objects']['counter']['state']['count'], 3)
        self.assertEqual(outcome['links']['refresh'], '/api/object?object=counter')
        self.assertEqual(bridge.reconcile(draft['draft'], self.receiver), outcome)


if __name__ == '__main__':
    unittest.main()
