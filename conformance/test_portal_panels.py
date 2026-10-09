"""Authored panel discovery/capture and cheap catalogue presentation."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import portal as p


class PortalPanelsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.addCleanup(setattr, sys, 'dont_write_bytecode', sys.dont_write_bytecode)
        self.root = {'protocol': {'name': 'The paper door', 'commands': {'knock': {}},
            'viewProgram': {}, 'viewPanels': [{'id': 'ink & light', 'label': '<Ink & light>'}]},
            'state': {}, 'version': 0, 'law': ['visitor']}
        p.save(self.directory / 'world.json', {'objects': {'door': self.root}, 'receipts': []})
        p.save(self.directory / 'manifest.json', {'cafe': 'door',
            'runtime': {'name': 'compiled', 'files': {}}})
        self.app = p.Portal(self.directory, public_origin='https://delvetalk.example')

    def view(self, root, object_id, panel):
        return {'format': 'delvetalk-projection-view-v1', 'mode': 'projection', 'object': object_id, 'root': copy.deepcopy(root),
                'panel': panel, 'data': {'title': 'Door / ' + panel, 'prose': panel,
                'actions': {'knock': {'text': 'Knock', 'command': 'knock', 'input': {}}}}}

    def test_catalogue_names_do_not_evaluate_or_claim_a_projected_title(self):
        with patch.object(self.app, '_view', side_effect=AssertionError('catalogue must not evaluate')):
            self.assertEqual(self.app.world()['objects'][0]['title'], 'The paper door')
        for name, expected, truncated in ((None, 'door', False), ({}, 'door', False),
                                           ('x' * 257, 'x' * 256, True)):
            self.root['protocol']['name'] = name
            p.save(self.directory / 'world.json', {'objects': {'door': self.root}, 'receipts': []})
            row = self.app.world()['objects'][0]
            self.assertEqual(row['title'], expected)
            self.assertEqual(row['nameTruncated'], truncated)

    def test_selected_panel_is_retained_and_refreshable_without_world_mutation(self):
        before = (self.directory / 'world.json').read_bytes()
        with patch.object(self.app, '_view', side_effect=self.view):
            card = self.app.object('door', 'ink & light')
            self.assertEqual(card['panel'], 'ink & light')
            self.assertEqual(card['panels'], [{'id': 'main', 'label': 'Overview'},
                {'id': 'ink & light', 'label': '<Ink & light>'}])
            self.assertIn('panel=ink%20%26%20light', card['links']['refresh'])
            draft = self.app.prepare({'card': card['card'], 'action': 'a1'})
            self.assertEqual(draft['panel'], 'ink & light')
            self.assertEqual(draft['fields'], {})
            self.assertEqual(draft['wire']['expected'], self.root)
            self.assertNotIn('principal', draft['wire'])
            self.assertEqual(self.app.draft(draft['draft']), draft)
        self.assertEqual((self.directory / 'world.json').read_bytes(), before)
        self.assertFalse((self.directory / 'portal-custody').exists())

    def test_unknown_or_duplicate_panels_cannot_select_an_unoffered_view(self):
        with patch.object(self.app, '_view', side_effect=self.view) as evaluate:
            with self.assertRaisesRegex(ValueError, 'Unknown declared panel'):
                self.app.object('door', 'unoffered')
            evaluate.assert_not_called()
            for declared in ([{'id': 'same', 'label': 'One'}, {'id': 'same', 'label': 'Two'}],
                             [{'id': 'x', 'label': ''}], [{'id': 'x', 'label': 'x', 'url': 'https://evil'}],
                             [{'id': str(i), 'label': str(i)} for i in range(9)]):
                self.root['protocol']['viewPanels'] = declared
                p.save(self.directory / 'world.json', {'objects': {'door': self.root}, 'receipts': []})
                card = self.app.object('door')
                self.assertEqual(card['panels'], [{'id': 'main', 'label': 'Overview'}])
                self.assertTrue(card['panelWarning'])

    def test_raw_fallback_has_no_active_pure_panels(self):
        raw = {'mode': 'raw', 'root': self.root, 'object': 'door'}
        with patch.object(self.app, '_view', return_value=raw):
            self.assertEqual(self.app.object('door')['panels'], [{'id': 'main', 'label': 'Overview'}])
            with self.assertRaisesRegex(ValueError, 'no available pure view'):
                self.app.object('door', 'ink & light')

    def test_actual_source_view_uses_selected_panel_and_exact_captured_root(self):
        from conformance.test_obend_view import SOURCE
        self.root['protocol'].update(initial={'lit': False}, commands={'knock': {
            'require': [], 'set': {'lit': ['literal', True]},
            'result': ['literal', 'Welcome'], 'outbox': []}},
            viewProgram={'profile': 'delvetalk-obend-view-v1', 'package': {
                'modules': [{'name': 'Main', 'source': SOURCE}], 'entry': 'view'}},
            viewPanels=[{'id': 'details', 'label': 'Door details'}])
        self.root['state'] = {'lit': False}
        p.save(self.directory / 'world.json', {'objects': {'door': self.root}, 'receipts': []})
        p.save(self.directory / 'manifest.json', {'cafe': 'door',
            'runtime': p.bootstrap.history.runtime('compiled')})
        app = p.Portal(self.directory, public_origin='https://delvetalk.example')
        before = (self.directory / 'world.json').read_bytes()
        self.assertEqual(app.object('door')['title'], 'The paper door')
        card = app.object('door', 'details')
        self.assertEqual(card['title'], 'Door details')
        self.assertEqual(card['panel'], 'details')
        draft = app.prepare({'card': card['card'], 'action': 'a1'})
        self.assertEqual(draft['wire']['expected'], self.root)
        self.assertEqual((self.directory / 'world.json').read_bytes(), before)

    def test_main_label_may_be_authored_without_duplicate_overview(self):
        self.root['protocol']['viewPanels'] = [{'id': 'main', 'label': 'Come in'}]
        self.assertEqual(self.app.panels(self.root), [{'id': 'main', 'label': 'Come in'}])


if __name__ == '__main__':
    unittest.main()
