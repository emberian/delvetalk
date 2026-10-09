"""Actual native acquisition gates, whole-admission history and retained facts."""
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import world
import portal


def law(read='public'):
    return {'profile': 'delvetalk-scoped-law', 'read': read,
            'invoke': {'touch': ['alice', 'bob']}, 'reprogram': ['alice'], 'law': ['alice']}


def protocol(secret):
    return {'profile': 'delvetalk-local-v1', 'initial': {'secret': secret},
            'commands': {'touch': {'require': [], 'set': {}, 'result': ['literal', 'touched'], 'outbox': []}}}


class GovernedReads(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.serial = 0

    def call(self, database, request):
        return world.exchange(database, request, profile='compiled')

    def create(self, database, name, read='public', source=None):
        reply = self.call(database, {'op': 'create', 'object': name, 'principal': 'alice',
            'intent': 'create-' + name, 'protocol': source or protocol(name + '-secret'), 'law': law(read)})
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply['data']['root']

    def revise(self, database, name, root, read):
        self.serial += 1
        request = {'op': 'law', 'object': name, 'principal': 'alice', 'intent': 'law-' + str(self.serial),
                   'expected': root, 'law': law(read)}
        reply = self.call(database, request)
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply['data']['root']

    def backends(self):
        for backend in ('file', 'resident'):
            database = self.path / (backend + '.json')
            if backend == 'resident': world.configure_resident(database)
            yield backend, database

    def test_acquisition_effect_receipt_and_exact_old_retry(self):
        for backend, database in self.backends():
            with self.subTest(backend=backend), world.resident_session(database) if backend == 'resident' else nullcontext():
                root = self.create(database, 'private', ['alice'])
                self.assertEqual(world.catalogue_page(database, principal='bob')['objects'], [])
                for request in ({'op': 'inspect', 'object': 'private', 'principal': 'bob'},
                    {'op': 'authorize-reads', 'objects': ['private'], 'principal': 'bob'}):
                    with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
                        world.query(database, request)
                with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
                    world.capture_roots(database, ['private'], principal='bob')
                captured = world.capture_roots(database, ['private'], principal='alice')['roots']['private']
                denied = self.call(database, {'op': 'invoke', 'object': 'private', 'principal': 'bob',
                    'intent': 'copied-root', 'expected': captured['reference'], 'command': 'touch', 'input': {}})
                self.assertEqual(denied['kind'], 'refused')
                self.assertNotIn('private-secret', world.wire_dumps(denied))
                original = {'op': 'invoke', 'object': 'private', 'principal': 'alice', 'intent': 'old-fact',
                            'expected': root, 'command': 'touch', 'input': {}}
                receipt = self.call(database, original)
                self.assertEqual(receipt['kind'], 'committed')
                self.revise(database, 'private', receipt['data']['root'], [])
                with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
                    world.capture_roots(database, ['private'], principal='alice')
                self.assertEqual(self.call(database, original), receipt)
                self.assertEqual(world.retained_reply(database, original), receipt)
                self.assertIsNone(world.retained_reply(database, {**original, 'principal': 'bob'}))

    def test_unused_transaction_read_cannot_leak_and_history_omits_whole_row(self):
        for backend, database in self.backends():
            with self.subTest(backend=backend), world.resident_session(database) if backend == 'resident' else nullcontext():
                public = self.create(database, 'public')
                private = self.create(database, 'private', ['alice'])
                batch = {'op': 'transaction', 'principal': 'alice', 'intent': 'joined',
                    'reads': {'public': public, 'private': private},
                    'calls': [{'object': 'public', 'command': 'touch', 'input': {}}]}
                done = self.call(database, batch)
                self.assertEqual(done['kind'], 'committed', done)
                public = done['data']['roots']['public']
                denied = self.call(database, {**batch, 'principal': 'bob', 'intent': 'unused-private',
                                              'reads': {'public': public, 'private': private}})
                self.assertEqual(denied['kind'], 'refused')
                self.assertNotIn('private-secret', world.wire_dumps(denied))
                for calls in ([{'op': 'observe', 'object': 'private'}], batch['calls']):
                    denied = self.call(database, {**batch, 'principal': 'bob', 'intent': str(calls),
                        'calls': calls, 'reads': {'public': public, 'private': private}})
                    self.assertEqual(denied['kind'], 'refused')
                before = world.capture_roots(database, ['public'], principal='bob')['sequence']
                request = {'op': 'object-history', 'principal': 'bob', 'object': 'public',
                           'before': before, 'offset': 0, 'limit': 32}
                visible = world.query(database, request)
                self.assertNotIn('private-secret', world.wire_dumps(visible))
                self.assertNotIn('joined', [entry['request']['intent'] for entry in visible['history']])
                trusted = world.query(database, {**request, 'principal': 'alice'})
                self.assertIn('joined', [entry['request']['intent'] for entry in trusted['history']])

    def test_portal_cached_card_and_detail_recheck_current_law_without_snapshot(self):
        database = self.path / 'world.json'
        root = self.create(database, 'public')
        private = self.create(database, 'private', ['alice'])
        batch = {'op': 'transaction', 'principal': 'alice', 'intent': 'joined',
                 'reads': {'public': root, 'private': private},
                 'calls': [{'object': 'public', 'command': 'touch', 'input': {}}]}
        receipt = self.call(database, batch)
        root = receipt['data']['roots']['public']
        portal.save(self.path / 'manifest.json', {'cafe': 'public',
                    'runtime': portal.bootstrap.history.runtime('compiled')})
        app = portal.Portal(self.path, principal='bob', allow_local_actions=True)
        card = app.object('public')
        with patch.object(app, 'snapshot', side_effect=AssertionError('participant history used full backup')):
            detail = app.detail(card['card'])
        self.assertNotIn('private-secret', world.wire_dumps(detail))
        self.revise(database, 'public', root, ['alice'])
        for access in (app.card, app.detail):
            with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
                access(card['card'])

    def test_authenticated_account_receipt_cannot_select_another_principal(self):
        import agent_heaps
        alice = {'accountId': 'a' * 32, 'did': 'did:plc:' + 'a' * 24}
        bob = {'accountId': 'b' * 32, 'did': 'did:plc:' + 'b' * 24}
        database = self.path / 'accounts.json'
        policy = law(['alice', alice['did']])
        policy['invoke']['touch'] = [alice['did'], bob['did']]
        root = self.call(database, {'op': 'create', 'object': 'private', 'principal': 'alice',
            'intent': 'seed-account', 'protocol': protocol('account-secret'), 'law': policy})['data']['root']
        request = {'op': 'invoke', 'object': 'private', 'intent': 'retained-account-fact',
                   'expected': root, 'command': 'touch', 'input': {}}
        with agent_heaps.HeapManager(self.path / 'accounts', database) as manager:
            receipt = manager.turn(alice, 'shared', request)
            self.assertEqual(receipt['kind'], 'committed')
            self.assertEqual(manager.receipt(alice, 'shared', request['intent']), receipt)
            self.assertIsNone(manager.receipt(bob, 'shared', request['intent']))
            # Even a foreign exact request copied into Bob's physical custody
            # cannot select Alice's retained native result.
            alice_dir = manager._context(alice, 'shared')[2]
            bob_dir = manager._context(bob, 'shared')[2]
            operation = manager._operation(alice_dir, 'shared', request['intent'])
            manager._operation(bob_dir, 'shared', request['intent'], operation)
            with self.assertRaisesRegex(ValueError, 'receipt account binding differs'):
                manager.receipt(bob, 'shared', request['intent'])
            copied = bob_dir / 'operations' / (agent_heaps.digest(['shared', request['intent']]) + '.json')
            copied.unlink()
            with self.assertRaisesRegex(ValueError, 'omit principal'):
                manager.turn(bob, 'shared', {**request, 'principal': alice['did']})
            denied = manager.turn(bob, 'shared', request)
            self.assertEqual(denied['kind'], 'refused')
            self.assertNotIn('account-secret', world.wire_dumps(denied))
            account_portal = manager._portal(alice, 'shared')
            framed = {**request, 'principal': alice['did']}
            draft = account_portal._store('drafts', {'interpretation': 'retained',
                'object': 'private', 'version': root['version'], 'summary': 'Touch', 'command': 'touch',
                'request': framed, 'localPrincipal': alice['did'], 'wire': account_portal.request_wire(framed),
                'runtime': account_portal.runtime})
            self.assertEqual(manager.reading(alice, 'shared', 'draft', draft)['outcome'], 'committed')
            self.revise(database, 'private', receipt['data']['root'], ['alice'])
            with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
                manager.reading(alice, 'shared', 'draft', draft)
            self.assertEqual(manager.execute(alice, 'shared', {'draft': draft})['reply'], receipt)
            self.assertEqual(manager.turn(alice, 'shared', request), receipt)
            self.assertEqual(manager.receipt(alice, 'shared', request['intent']), receipt)
            self.assertNotEqual(manager.receipt(bob, 'shared', request['intent']), receipt)

    def test_saved_derived_payloads_recheck_peers_but_exact_receipt_recovers(self):
        database = self.path / 'world.json'
        public = self.create(database, 'public')
        private = self.create(database, 'private', ['alice', 'bob', 'portal-preview'])
        portal.save(self.path / 'manifest.json', {'cafe': 'public',
                    'runtime': portal.bootstrap.history.runtime('compiled')})
        app = portal.Portal(self.path, principal='bob', allow_local_actions=True)
        card = app.object('public')
        request = {'op': 'transaction', 'principal': 'bob', 'intent': 'derived-peer',
                   'reads': {'public': public, 'private': private},
                   'calls': [{'object': 'public', 'command': 'touch', 'input': {}}]}
        draft = {'card': card['card'], 'object': 'public', 'request': request,
                 'wire': app.request_wire(request), 'interpretation': 'saved',
                 'localPrincipal': 'bob', 'runtime': app.runtime}
        alias = app._store('drafts', draft)
        preview = portal.Portal(self.path, public_origin='https://preview.example')
        preview_alias = preview._store('drafts', {**draft, 'request': app.request_wire(request)})
        preparation = app._store('preparations', {'card': card['card'], 'outcome': {'kind': 'question'}})
        memo = app._store('interpretations', {'input': {'card': card['card'], 'text': 'read'},
                  'result': {'draft': {'draft': alias}}})
        app.authorize_saved_request(draft)
        app.authorize_saved_request({'object': 'public',
            'request': {'reads': {'not-yet-created': {'expected': None}}}})
        receipt = self.call(database, request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        public = receipt['data']['roots']['public']
        self.revise(database, 'private', private, ['alice'])
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            app.draft(alias)
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            preview.draft(preview_alias)
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            app._read('interpretations', memo)
        self.assertEqual(app._retained(request), receipt)
        self.revise(database, 'public', public, ['alice'])
        self.assertEqual(app._retained(request), receipt)
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            app.preparation(preparation)

    def test_factory_read_policy_is_explicit_and_empty_has_no_maker_bypass(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('read_factories', ROOT / 'protocols/factories/package.py')
        package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(package)
        forge_spec = importlib.util.spec_from_file_location('read_forge', ROOT / 'protocols/town-forge/generate.py')
        forge = importlib.util.module_from_spec(forge_spec)
        forge_spec.loader.exec_module(forge)
        database = self.path / 'factory.json'
        for name, read in [('open', 'public'), ('private', ['alice']), ('locked', []), ('town', ['alice'])]:
            policy = law()
            policy['invoke'] = {'make': ['alice']}
            created = self.call(database, {'op': 'create', 'object': name, 'principal': 'alice',
                'intent': 'create-' + name, 'protocol': (forge.object_factory(package.object(), ['bob'], ['write'], read=read)
                    if name == 'town' else package.factory(read=read)), 'law': policy})
            self.assertEqual(created['kind'], 'committed', created)
            factory = created['data']['root']
            reply = self.call(database, {'op': 'invoke', 'object': name, 'principal': 'alice',
                'intent': 'make-' + name, 'expected': factory, 'command': 'make',
                'input': {'name': 'child'}, 'absent': [name + '/child']})
            self.assertEqual(reply['kind'], 'committed', reply)
            child = name + '/child'
            if read == []:
                for principal in ['alice', 'bob']:
                    with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
                        world.query(database, {'op': 'inspect', 'object': child, 'principal': principal})
            else:
                root = world.query(database, {'op': 'inspect', 'object': child, 'principal': 'alice'})
                self.assertEqual(root['law']['read'], read)
                self.assertEqual(root['law']['invoke']['write'], ['alice', 'bob'] if name == 'town' else ['alice'])
                if read != 'public':
                    with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
                        world.query(database, {'op': 'inspect', 'object': child, 'principal': 'bob'})

    def test_retained_preparation_uses_current_law_and_captured_execution(self):
        from conformance.test_preparation import NativePreparation
        NativePreparation.setUpClass()
        database = self.path / 'prepare.json'
        original = self.create(database, 'gallery', ['alice'], NativePreparation.protocol)
        peer = self.create(database, 'peer', ['alice'])
        capture = world.capture_roots(database, ['gallery', 'peer'], principal='alice')['roots']
        new_root = self.revise(database, 'gallery', original, ['alice', 'bob'])
        new_peer = self.revise(database, 'peer', peer, ['alice', 'bob'])
        request = {'op': 'prepare-retained', 'object': 'gallery', 'root': capture['gallery']['reference'],
            'principal': 'bob', 'intent': 'prepare-old-code', 'entry': 'prepareOwnerArgument', 'contribution': {},
            'observations': [{'object': 'peer', 'root': capture['peer']['reference'],
                              'inspectState': False, 'inspectLaw': False}]}
        # Old captured laws deny Bob; the newly granted current laws must decide.
        self.assertEqual(world.query(database, request)['kind'], 'question')
        self.revise(database, 'peer', new_peer, ['alice'])
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            world.query(database, request)
        self.revise(database, 'gallery', new_root, ['alice'])
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            world.query(database, {**request, 'observations': []})


if __name__ == '__main__': unittest.main()
