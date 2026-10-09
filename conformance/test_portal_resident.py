"""Portal/town readers use explicit backend APIs without a JSON lock around IPC."""
import copy
import fcntl
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import portal as p
import town


class ResidentConsumerRoutingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.database = self.directory / 'world.json'
        self.runtime = {'name': 'compiled', 'files': {}}
        self.root = {'protocol': {'name': 'Lantern', 'commands': {}}, 'state': {}, 'law': ['visitor'], 'version': 2}
        self.snapshot = {'objects': {'lamp': self.root}, 'receipts': []}
        p.save(self.directory / 'manifest.json', {'cafe': 'lamp', 'runtime': self.runtime})
        self.addCleanup(setattr, sys, 'dont_write_bytecode', sys.dont_write_bytecode)

    def read_without_world_lock(self, database):
        self.assertEqual(Path(database), self.database)
        # A native daemon may itself own this lock. Taking it here would conflict
        # if a consumer held the old JSON-world lock while requesting a snapshot.
        with open(str(database) + '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return copy.deepcopy(self.snapshot)

    def test_portal_accepts_logical_database_and_routes_snapshot_and_indexed_receipt(self):
        with patch.object(p.world, 'exists', return_value=True, create=True) as exists, patch.object(
                p.world, 'snapshot', side_effect=self.read_without_world_lock, create=True) as snapshot:
            app = p.Portal(self.directory, public_origin='https://delvetalk.example')
            self.assertFalse(self.database.exists())
            self.assertEqual(app.world()['objects'][0]['id'], 'lamp')
            exists.assert_called_once_with(self.database)
            snapshot.assert_called_once_with(self.database)
        request, receipt = {'intent': 'same'}, {'kind': 'committed'}
        with patch.object(p.world, 'retained_reply', return_value=receipt, create=True) as retained, patch.object(
                app, 'snapshot', side_effect=AssertionError('receipt lookup must not export history')):
            self.assertEqual(app._retained(request), receipt)
            retained.assert_called_once_with(self.database, request)

    def test_legacy_receipt_recovery_preserves_record_order_independence(self):
        request = {'op': 'invoke', 'object': 'lamp', 'principal': 'visitor', 'intent': 'same-turn',
                   'expected': self.root, 'command': 'touch', 'input': {}}
        receipt = {'kind': 'committed', 'data': {'result': 'kept'}}
        p.save(self.database, {'objects': {'lamp': self.root},
            'receipts': [{'request': request, 'receipt': receipt}]})
        app = p.Portal(self.directory, public_origin='https://delvetalk.example')
        self.assertEqual(app._retained(request), receipt)
        self.assertIsNone(app._retained({**request, 'command': 'different'}))

    def test_missing_logical_backend_still_refuses_without_creating_world(self):
        with patch.object(p.world, 'exists', return_value=False, create=True):
            with self.assertRaisesRegex(ValueError, 'World database is missing'):
                p.Portal(self.directory)
        self.assertFalse(self.database.exists())
        self.assertFalse((self.directory / 'portal-custody').exists())

    def test_town_views_read_logical_database_without_json_lock(self):
        operator = town.Town.__new__(town.Town)
        operator.clerk = SimpleNamespace(database=self.database)
        with patch.object(town.world, 'snapshot', side_effect=self.read_without_world_lock, create=True), patch.object(
                town.bootstrap, 'bound_room_artifact', return_value=None), patch.object(
                town.bootstrap.room, 'inspect_object', side_effect=lambda root, identity, artifact, **kw:
                {'root': root, 'object': identity, 'runtime': kw['expected_runtime']}):
            views = operator._views(['lamp'], self.runtime)
        self.assertEqual(views, [{'root': self.root, 'object': 'lamp', 'runtime': self.runtime}])
        self.assertFalse(self.database.exists())

    def test_town_child_capture_reads_fresh_logical_root_without_json_lock(self):
        operator = town.Town.__new__(town.Town)
        operator.clerk = SimpleNamespace(database=self.database)
        operator.state = self.directory
        book = Mock()
        book.card.return_value = {'view': {'object': 'index'}}
        book.metadata.return_value = {'runtime': self.runtime}
        book.capture.side_effect = lambda view, alias: {'alias': alias, 'view': view}
        descriptor = {'key': 'lamp', 'object': 'lamp', 'panel': 'main', 'label': 'The lantern'}
        with patch.object(operator, '_configuration', return_value=({'objects': ['lamp']}, book)), patch.object(
                town.town_cards.projection, 'child', return_value=descriptor), patch.object(
                town.world, 'snapshot', side_effect=self.read_without_world_lock, create=True), patch.object(
                town.bootstrap, 'bound_room_artifact', return_value=None), patch.object(
                town.bootstrap.room, 'inspect_object', side_effect=lambda root, identity, artifact, **kw:
                {'root': root, 'object': identity, 'mode': 'raw'}):
            captured = operator.capture_child('parent', 'lamp', alias='child')
        self.assertEqual(captured['status'], 'prepared')
        self.assertEqual(captured['card']['view']['root'], self.root)
        self.assertEqual(captured['card']['alias'], 'child')
        self.assertFalse(self.database.exists())


class NativeResidentPortalTest(unittest.TestCase):
    def test_authored_object_and_lost_local_reply_recover_exact_resident_receipt(self):
        from conformance.test_obend_view import SOURCE
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name).resolve()
        database = directory / 'world.json'
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {'lit': False},
            'commands': {'knock': {'require': [], 'set': {'lit': ['literal', True]},
                'result': ['literal', 'Welcome'], 'outbox': []}},
            'viewProgram': {'profile': 'delvetalk-obend-view-v1', 'package': {
                'modules': [{'name': 'Main', 'source': SOURCE}], 'entry': 'view'}}}
        p.save(directory / 'manifest.json', {'cafe': 'door', 'runtime': p.bootstrap.history.runtime('compiled')})
        p.world.configure_resident(database, profile='compiled')
        with p.world.resident_session(database):
            created = p.world.exchange(database, {'op': 'create', 'object': 'door', 'principal': 'maker',
                'intent': 'create-door', 'protocol': protocol, 'law': ['visitor']}, profile='compiled')
            self.assertEqual(created['kind'], 'committed', created)
            self.assertFalse(database.exists())
            previous_bytecode = sys.dont_write_bytecode
            self.addCleanup(setattr, sys, 'dont_write_bytecode', previous_bytecode)
            public = p.Portal(directory, public_origin='https://delvetalk.example')
            with patch.object(p.world.tempfile, 'NamedTemporaryFile',
                              side_effect=AssertionError('snapshot client must not create an export file')):
                self.assertEqual(public.world()['objects'][0]['id'], 'door')
            app = p.Portal(directory, principal='visitor', allow_local_actions=True)
            card = app.object('door')
            self.assertEqual(card['title'], 'The paper door')
            draft = app.prepare({'card': card['card'], 'action': 'a1'})
            reply = app.execute({'draft': draft['draft']})
            self.assertEqual(reply['kind'], 'committed', reply)
            saved = app._read('drafts', draft['draft'])
            saved.pop('reply')
            p.save(app.state / 'drafts' / (draft['draft'] + '.json'), saved)
        # The explicit resident selection never falls back to a file or starts a daemon.
        with self.assertRaises(RuntimeError):
            p.Portal(directory).snapshot()
        self.assertFalse(database.exists())
        # Restart both the resident process and the portal; no JSON mirror appears.
        with p.world.resident_session(database):
            restarted = p.Portal(directory, principal='visitor', allow_local_actions=True)
            with patch.object(restarted, 'snapshot', side_effect=AssertionError('indexed receipt lookup required')), patch.object(
                    restarted, '_pins', side_effect=AssertionError('recover receipt before checking replacement pins')), patch.object(
                    p.submission.worker, 'command', side_effect=AssertionError('no second admission')):
                self.assertEqual(restarted.execute({'draft': draft['draft']}), reply)
            snapshot = p.world.snapshot(database)
            self.assertEqual(snapshot['objects']['door']['version'], 1)
            self.assertEqual(len(snapshot['receipts']), 2)
            # Exercise Town's observation reader against the same daemon. Its
            # capture/enrollment authorization is separately tested by Town.
            reader = town.Town.__new__(town.Town)
            reader.clerk = SimpleNamespace(database=database)
            views = reader._views(['door'], p.bootstrap.history.runtime('compiled'))
            self.assertEqual(views[0]['root'], snapshot['objects']['door'])
            self.assertEqual(views[0]['data']['prose'], 'A lantern glows.')
            self.assertEqual(restarted.object('door')['prose'], 'A lantern glows.')
            self.assertEqual(restarted.detail(card['card'])['root']['version'], 0)
            self.assertFalse(database.exists())
