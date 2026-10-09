"""Portal/Town retain presentation roots while native queries own compact guards."""
import copy
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import editor
import portal
import source_offers
import town_cards
from conformance.test_view_invitations import fixture
from conformance.test_town_cards import ISSUER, ACTOR, PUBLICATION, SOURCE


class ConsumerForwarding(unittest.TestCase):
    def test_local_and_public_capture_keep_full_display_and_prepare_exact_native_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            view = fixture()
            view.update(object='gallery', panel='main')
            roots = {'gallery': view['root'], 'peer': {**view['root'], 'state': {'large': 'x' * 20000}}}
            portal.save(home / 'world.json', {'objects': roots, 'receipts': []})
            portal.save(home / 'manifest.json', {'cafe': 'gallery', 'runtime': {'name': 'compiled', 'files': {}}})
            original = (home / 'world.json').read_bytes()
            original_bytecode = sys.dont_write_bytecode
            self.addCleanup(setattr, sys, 'dont_write_bytecode', original_bytecode)
            for public in (False, True):
                with self.subTest(public=public):
                    app = portal.Portal(home, **({'public_origin': 'https://delvetalk.example'} if public else
                        {'principal': ACTOR, 'allow_local_actions': True}))
                    refs = {name: {'profile': 'delvetalk-retained-root-v1', 'object': name, 'key': ('a' if name == 'gallery' else 'b') * 64} for name in roots}
                    calls = []
                    def query(database, request, **options):
                        self.assertEqual(database, app.database)
                        calls.append(copy.deepcopy(request))
                        if request['op'] == 'capture-roots':
                            self.assertNotIn('root', request)
                            self.assertLess(len(portal.world.wire_dumps(request)), 500)
                            self.assertEqual(request['expected'], {} if len(calls) == 1 else {'gallery': refs['gallery']})
                            return {'roots': {name: {'root': roots[name], 'reference': refs[name]}
                                for name in request['objects']}, 'sequence': 0, 'head': None}
                        self.assertEqual(request['op'], 'prepare-retained')
                        self.assertEqual(request['root'], refs['gallery'])
                        self.assertEqual(request['observations'], retained['offers']['o1']['observations'])
                        self.assertEqual(request['observations'][0]['root'], refs['peer'])
                        return {'kind': 'ready', 'summary': 'Gesture', 'request': {
                            'op': 'transaction', 'principal': request['principal'], 'intent': request['intent'],
                            'reads': refs, 'calls': [{'object': 'peer', 'command': 'touch', 'input': request['contribution']}]}}
                    with patch.object(app, '_view', return_value=view), patch.object(source_offers.world, 'query', side_effect=query):
                        card = app.object('gallery')
                        retained = app._read('cards', card['card'])
                        self.assertEqual(retained['view']['root'], roots['gallery'])
                        self.assertEqual(retained['offers']['o1']['root'], refs['gallery'])
                        with patch.object(app, 'snapshot', side_effect=AssertionError('No recapture during preparation')):
                            draft = app.prepare({'card': card['card'], 'action': 'o1', 'fields': {'gesture': 'wave'}})
                        self.assertEqual([row['version'] for row in draft['reads']], [None, None])
                        self.assertLess(len(draft['wireJson']), 1000)
                        self.assertEqual([item['op'] for item in calls], ['capture-roots', 'capture-roots', 'prepare-retained'])
                        self.assertEqual(calls[-1]['principal'], 'portal-preview' if public else ACTOR)
                        with patch.object(source_offers.world, 'query', side_effect=ValueError('unknown retained root')), patch.object(
                                source_offers.process_custody, 'run', side_effect=AssertionError('No isolated-root fallback')):
                            with self.assertRaisesRegex(ValueError, 'unknown retained root'):
                                app.prepare({'card': card['card'], 'action': 'o1', 'fields': {'gesture': 'again'}})
                        if public:
                            with self.assertRaises(PermissionError):
                                app.execute({'draft': draft['draft']})
                    self.assertEqual((home / 'world.json').read_bytes(), original)

    def test_editor_forwards_database_and_recovers_before_preparing_again(self):
        with tempfile.TemporaryDirectory() as temporary:
            client = Mock(database=Path(temporary) / 'world.json')
            client.exchange.return_value = {'kind': 'committed'}
            custody = editor.Editor(client, Path(temporary) / 'custody')
            outcome = {'kind': 'ready', 'request': {'principal': ACTOR, 'intent': 'one'}}
            with patch.object(source_offers, 'prepare', return_value=outcome) as prepare:
                first = custody.interact({'capture': 'opaque'}, {'gesture': 'wave'}, ACTOR, 'one')
                self.assertEqual(prepare.call_args.kwargs, {'database': client.database})
            with patch.object(source_offers, 'prepare', side_effect=AssertionError('receipt first')):
                self.assertEqual(custody.interact({'capture': 'opaque'}, {'gesture': 'wave'}, ACTOR, 'one'), first)
            client.exchange.assert_called_once_with(outcome['request'])


class NativeConsumerJourney(unittest.TestCase):
    def test_file_public_local_and_authenticated_town_use_exact_compact_preparations(self):
        self.journey('file')

    def test_resident_public_local_and_authenticated_town_use_exact_compact_preparations(self):
        self.journey('resident')

    def journey(self, backend):
        import clerk
        import town
        import workspace
        from syntaxes import obend_object
        from conformance.test_preparation import SOURCE as BEND
        from conformance.test_town_forge_journey import PublicRecords
        protocol = obend_object.lower_data_modules([
            {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
            {'name': 'Gallery', 'source': BEND}])
        peer = {'profile': 'delvetalk-local-v1', 'initial': {'gesture': 'initial', 'padding': 'x' * 600000},
                'commands': {'touch': {'require': [], 'set': {'gesture': ['input', 'gesture']},
                                      'result': ['input', 'gesture'], 'outbox': []}}}
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as active:
            base = Path(temporary)
            home = base / 'world'
            seed = workspace.initialize(home, [{'id': name, 'syntax': 'protocol-json@1',
                'source': clerk.canonical(value), 'law': [ACTOR]} for name, value in [('gallery', protocol), ('peer', peer)]],
                entry_objects=['gallery'], principal='operator', profile='compiled', backend=backend,
                world_id='urn:test:retained-consumer')
            database = home / 'world.json'
            if backend == 'resident':
                active.enter_context(portal.world.resident_session(database, profile='compiled'))
                self.assertFalse(database.exists())
            large_capture = portal.world.capture_roots(database, ['peer'])
            self.assertGreater(len(portal.world.wire_dumps(large_capture['roots']['peer']['root']).encode()),
                               portal.world.MAX_EXPANDED_REQUEST_BYTES)
            pds = PublicRecords()
            receiver = clerk.Clerk(base / 'clerk', request=pds)
            receiver.attach(home, portal.world.snapshot(database)['objects'], [ACTOR], expected_genesis=seed['genesis'],
                expected_seed_head=seed['head'], runtime_profile='compiled')
            book = town_cards.CardBook.create(base / 'cards', issuer_did=ISSUER,
                world_id='urn:test:retained-consumer', runtime=portal.bootstrap.history.runtime('compiled'))
            receiver.upgrade(receiver.profile()['sha256'], town_cards={'path': str(book.path),
                'issuers': [ISSUER], 'metadata': book.metadata()})
            operator = town.Town(receiver.state, request=pds)
            original_bytecode = sys.dont_write_bytecode
            self.addCleanup(setattr, sys, 'dont_write_bytecode', original_bytecode)
            public = portal.Portal(home, public_origin='https://delvetalk.example')
            project = public._view
            def advance_during_projection(root, object_id, panel):
                view = project(root, object_id, panel)
                changed = portal.world.exchange(database, {'op': 'law', 'object': object_id,
                    'principal': ACTOR, 'intent': 'owner-raced', 'expected': root, 'law': [ACTOR]}, profile='compiled')
                self.assertEqual(changed['kind'], 'committed')
                return view
            with patch.object(public, '_view', side_effect=advance_during_projection), self.assertRaises(ValueError):
                public.object('gallery')
            self.assertFalse(public.preview.records)
            before = {str(p.relative_to(home)): p.read_bytes() for p in home.rglob('*') if p.is_file()}
            card = public.object('gallery')
            draft = public.prepare({'card': card['card'], 'action': 'o1', 'fields': {'gesture': 'preview'}})
            self.assertLess(len(draft['wireJson']), 1500)
            self.assertEqual(before, {str(p.relative_to(home)): p.read_bytes() for p in home.rglob('*') if p.is_file()})
            with self.assertRaises(PermissionError):
                public.execute({'draft': draft['draft']})
            local = portal.Portal(home, principal=ACTOR, allow_local_actions=True)
            captured = local.object('gallery')
            pending = local.prepare({'card': captured['card'], 'action': 'o1', 'fields': {'gesture': 'local'}})
            native = local.execute({'draft': pending['draft']})
            self.assertEqual(native['kind'], 'committed', native)
            self.assertEqual(local.execute({'draft': pending['draft']}), native)
            stale = local.prepare({'card': captured['card'], 'action': 'o1', 'fields': {'gesture': 'stale'}})
            self.assertEqual(local.execute({'draft': stale['draft']})['kind'], 'refused')
            opening = operator.capture('gallery', alias='opening')
            invitation = next(iter(opening['offers'].values()))
            self.assertEqual(invitation['root']['profile'], 'delvetalk-retained-root-v1')
            self.assertIn('protocol', opening['view']['root'])
            pds.records[PUBLICATION['uri']] = (PUBLICATION['cid'], {'$type': clerk.FEED, 'text': opening['body']})
            operator.bind('opening', PUBLICATION['uri'], PUBLICATION['cid'])
            action = next(item for item in opening['card']['actions'] if item.get('preparation'))
            text = 'delvetalk opening ' + action['id'] + '\ngesture: town'
            pds.records[SOURCE['uri']] = (SOURCE['cid'], {'$type': clerk.FEED, 'text': text,
                'reply': {'root': PUBLICATION, 'parent': PUBLICATION}})
            # Lose response custody after native admission and follow-up capture,
            # then advance the world before recovering the original conversation.
            save = town.save
            def lose_response(path, value):
                if 'response' in value:
                    raise OSError('lost final response save')
                save(path, value)
            with patch.object(town, 'save', side_effect=lose_response), self.assertRaisesRegex(OSError, 'lost final response'):
                operator.receive(SOURCE['uri'], SOURCE['cid'])
            first_followup = book.card('reply-1-1')
            peer_root = portal.world.snapshot(database)['objects']['peer']
            self.assertEqual(peer_root['state']['gesture'], 'town')
            peer_reference = portal.world.capture_roots(database, ['peer'])['roots']['peer']['reference']
            advanced = portal.world.exchange(database, {'op': 'transaction', 'principal': ACTOR,
                'intent': 'advance-after-lost-response', 'reads': {'peer': peer_reference},
                'calls': [{'object': 'peer', 'command': 'touch', 'input': {'gesture': 'later'}}]}, profile='compiled')
            self.assertEqual(advanced['kind'], 'committed')
            reply = operator.receive(SOURCE['uri'], SOURCE['cid'])
            self.assertEqual(reply['cards'][0], first_followup)
            self.assertEqual(reply['receipt']['reply']['kind'], 'committed', reply)
            self.assertEqual(reply['receipt']['request']['principal'], ACTOR)
            self.assertLess(len(portal.world.wire_dumps(reply['receipt']['request'])), 1500)
            self.assertEqual(portal.world.snapshot(database)['objects']['peer']['state']['gesture'], 'later')
            followup = next(card for card in reply['cards'] if card.get('offers'))
            self.assertIn('protocol', followup['view']['root'])
            self.assertEqual(next(iter(followup['offers'].values()))['root']['profile'], 'delvetalk-retained-root-v1')
            if backend == 'resident':
                active.close()
                active.enter_context(portal.world.resident_session(database, profile='compiled'))
            restored_preview = public.prepare({'card': card['card'], 'action': 'o1', 'fields': {'gesture': 'preview'}})
            self.assertEqual(restored_preview['wire']['reads'], draft['wire']['reads'])
            pds.records.clear()
            recovered = town.Town(receiver.state, request=pds)
            with patch.object(recovered, '_capture_roots', side_effect=AssertionError('No recapture on retry')):
                self.assertEqual(recovered.receive(SOURCE['uri'], SOURCE['cid']), reply)


if __name__ == '__main__':
    unittest.main()
