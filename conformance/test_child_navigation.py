"""Town catalogue selection captures fresh independent child cards, without admission."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import town
import town_cards
import workspace
from conformance.test_obend_data_object import SOURCE
from conformance.test_typed_view import sequence, wire
from conformance.test_town_forge_journey import PublicRecords, MAKER, VISITOR, ISSUER


def peer():
    return {'profile': 'delvetalk-local-v1', 'name': 'A peer', 'initial': {},
            'commands': {'touch': {'require': [], 'set': {}, 'result': ['literal', 'hello'], 'outbox': []}},
            'affordances': {'touch': {'fields': {}}}}


class RecoveryInspection(unittest.TestCase):
    def test_failed_typed_overview_retains_source_state_without_actions_or_children(self):
        program = {'profile': town_cards.projection.DATA_MENU_PROFILE,
                   'package': {'modules': [{'name': 'Shelf', 'source': SOURCE}], 'entry': 'view'}}
        root = {'protocol': {'name': 'An injured shelf', 'commands': {'add': {}},
                'viewProgram': program, 'viewPanels': [{'id': 'details', 'label': 'Details'}],
                'affordances': {'add': {'fields': {'malformed': None}}}},
                'state': {'model': wire({'unexpected': False})}, 'law': ['maker'], 'version': 3}
        failed = Mock()
        failed.project.side_effect = ValueError('source view budget exhausted')
        with patch.object(town.bootstrap.room, 'module', return_value=failed):
            view = town.bootstrap.room.inspect_object(root, 'shelf', expected_runtime={})
        self.assertEqual(view['mode'], 'raw')
        self.assertEqual(failed.project.call_count, 1)
        # Unknown raw fields must not turn recovery into a fabricated menu.
        view.update(children=[{'key': 'forged', 'label': 'Forged child', 'object': 'elsewhere', 'panel': 'main'}],
                    rawData={'forged': True})
        with tempfile.TemporaryDirectory() as directory:
            book = town_cards.CardBook.create(Path(directory), issuer_did=ISSUER,
                world_id='urn:test:recovery', runtime={'name': 'compiled', 'files': {}})
            captured = book.capture(view, alias='shelf-recovery')
            self.assertEqual(captured['view']['root'], root)
            self.assertEqual(captured['card']['actions'], [])
            self.assertEqual(captured['panels'], [])
            self.assertEqual(town_cards.projection.children(captured['view']), [])
            self.assertIn('source view budget exhausted', captured['body'])
            self.assertNotIn('Forged child', captured['body'])
            self.assertNotIn('Reply here:', captured['body'])
            self.assertEqual(book.card('shelf-recovery'), captured)
            source = town.bootstrap.room.source_document(captured['view'])
            self.assertEqual(source['program'], program)
            self.assertEqual(source['root']['state'], root['state'])
            with self.assertRaisesRegex(ValueError, 'action ID'):
                town_cards.affordances.request(captured['view'], 'a1', 'maker', 'not-an-action', {})
            with self.assertRaisesRegex(ValueError, 'unknown captured child'):
                town_cards.projection.child(captured['view'], 'forged')
            # Reclassifying raw recovery as evaluated source still requires pins.
            with self.assertRaisesRegex(ValueError, 'expected compiled runtime'):
                town_cards.projection.assert_runtime({**view, 'mode': 'projection'}, {})


class ChildNavigation(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        home = self.base / 'world'
        seed = workspace.initialize(home, [
            {'id': 'shelf', 'syntax': 'objective-bend-spell@3', 'source': SOURCE.encode(), 'law': [MAKER]},
            *[{'id': name, 'syntax': 'protocol-json@1', 'source': clerk.canonical(peer()), 'law': [VISITOR]}
              for name in ('lantern', 'garden')]],
            entry_objects=['shelf'], principal=MAKER, profile='compiled', world_id='urn:test:children')
        self.pds = PublicRecords()
        self.receiver = clerk.Clerk(self.base / 'clerk', self.pds)
        roots = clerk.loads((home / 'world.json').read_bytes())['objects']
        self.receiver.attach(home, roots, [MAKER, VISITOR], expected_genesis=seed['genesis'],
            expected_seed_head=seed['head'], runtime_profile='compiled')
        self.book = town_cards.CardBook.create(self.base / 'cards', issuer_did=ISSUER,
            world_id='urn:test:children', runtime=workspace.bootstrap.history.runtime('compiled'))
        self.receiver.upgrade(self.receiver.profile()['sha256'], town_cards={
            'path': str(self.book.path.resolve()), 'issuers': [ISSUER], 'metadata': self.book.metadata()})
        self.operator = town.Town(self.receiver.state, request=self.pds)
        self.serial = 0
        for target in ('lantern', 'garden'):
            self.admit({'op': 'invoke', 'object': 'shelf', 'command': 'add', 'input': {'object': target}})
        self.parent = self.operator.capture('shelf', alias='gallery')

    def root(self, target):
        return self.receiver.snapshot(target)['root']

    def admit(self, request, principal=MAKER):
        self.serial += 1
        request = {**request, 'principal': principal, 'intent': 'local-' + str(self.serial),
                   'expected': self.root(request['object'])}
        reply = clerk.world.exchange(self.receiver.database, request, profile='compiled')
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply

    def replace_catalogue(self, entries):
        initial = self.root('shelf')
        state = {'model': {'tag': 'record', 'fields': [{'name': 'entries', 'value': sequence(entries)}]}}
        self.admit({'op': 'reprogram', 'object': 'shelf', 'protocol': initial['protocol'], 'state': state})
        return self.operator.capture('shelf')

    def test_navigation_reads_current_child_and_preserves_parent_and_child_authority(self):
        self.assertIn('Look around (read only):', self.parent['body'])
        before = self.receiver.database.read_bytes()
        selected = self.operator.capture_child('gallery', 'lantern', alias='first-lantern')
        self.assertEqual((selected['status'], selected['parent'], selected['key']), ('prepared', 'gallery', 'lantern'))
        first = selected['card']
        self.assertEqual(first['view']['object'], 'lantern')
        self.assertNotEqual(first['alias'], self.parent['alias'])
        self.assertEqual(self.receiver.database.read_bytes(), before)
        call = town_cards.affordances.request(first['view'], 'a1', MAKER, 'not-curator-authority', {})
        refusal = clerk.world.exchange(self.receiver.database, call, profile='compiled')
        self.assertEqual(refusal['data'], 'unauthorized')
        code = peer(); code['name'] = 'The revised lantern'
        self.admit({'op': 'reprogram', 'object': 'lantern', 'protocol': code, 'state': {}}, VISITOR)
        next_card = self.operator.capture_child('gallery', 'lantern')['card']
        self.assertEqual(next_card['card']['title'], 'The revised lantern')
        self.assertNotEqual(next_card['view']['root'], first['view']['root'])
        self.assertEqual(self.book.card(first['alias']), first)
        self.assertEqual(self.book.card('gallery')['view'], self.parent['view'])
        stale = {**call, 'principal': VISITOR, 'intent': 'stale-child'}
        self.assertEqual(clerk.world.exchange(self.receiver.database, stale, profile='compiled')['data'], 'stale read root')
        removed = self.replace_catalogue([])
        self.assertEqual(removed['view']['children'], [])
        self.assertEqual(self.operator.capture_child('gallery', 'lantern')['status'], 'prepared')
        with self.assertRaisesRegex(ValueError, 'distinct alias'):
            self.operator.capture_child('gallery', 'lantern', alias='gallery')
        with self.assertRaisesRegex(ValueError, 'already bound'):
            self.operator.capture_child('gallery', 'lantern', alias='first-lantern')
        # Reopened custody preserves the captured parent; no network publication.
        reopened = town.Town(self.receiver.state, request=self.pds)
        self.assertEqual(reopened.capture_child('gallery', 'garden')['card']['view']['object'], 'garden')
        self.assertEqual(self.pds.calls, [])

    def test_unenrolled_absent_bad_panel_and_failed_view_are_unavailable(self):
        descriptor = {'key': 'missing', 'label': 'A promised exhibit', 'object': 'unenrolled', 'panel': 'main'}
        card = self.replace_catalogue([descriptor])
        before = self.receiver.database.read_bytes()
        before_aliases = self.book.aliases()
        self.assertEqual(self.operator.capture_child(card['alias'], 'missing')['reason'], 'unenrolled')
        self.assertEqual(self.book.aliases(), before_aliases)
        self.assertEqual(self.receiver.database.read_bytes(), before)
        panel = self.replace_catalogue([{**descriptor, 'object': 'lantern', 'panel': 'invented'}])
        self.assertEqual(self.operator.capture_child(panel['alias'], 'missing')['reason'], 'panel-unavailable')
        malformed = peer()
        malformed['viewProgram'] = {'profile': 'unsupported-view'}
        self.admit({'op': 'reprogram', 'object': 'lantern', 'protocol': malformed, 'state': {}}, VISITOR)
        before_aliases = self.book.aliases()
        self.assertEqual(self.operator.capture_child('gallery', 'lantern')['reason'], 'view-unavailable')
        self.assertEqual(self.book.aliases(), before_aliases)
        # Fixture fault injection models an enrolled target no longer present.
        snapshot = clerk.loads(self.receiver.database.read_bytes())
        del snapshot['objects']['lantern']
        clerk.save(self.receiver.database, snapshot)
        self.assertEqual(self.operator.capture_child('gallery', 'lantern')['reason'], 'absent')
        self.assertEqual(self.operator.capture_child('gallery', 'garden')['status'], 'prepared')

    def test_cli_capture_child_is_local_read_only_and_reports_relation(self):
        before = self.receiver.database.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/town.py'), '--clerk-state',
            str(self.receiver.state), 'capture-child', 'gallery', 'lantern', '--alias', 'cli-child'],
            cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = clerk.loads(result.stdout)
        self.assertEqual((captured['parent'], captured['key']), ('gallery', 'lantern'))
        self.assertEqual(captured['card']['alias'], 'cli-child')
        self.assertEqual(self.receiver.database.read_bytes(), before)


if __name__ == '__main__': unittest.main()
