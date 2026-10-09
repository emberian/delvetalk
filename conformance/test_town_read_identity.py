"""Town transport retains the selected actor for every captured observation."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import town


class TownReadIdentity(unittest.TestCase):
    def test_view_and_peer_observation_use_same_actor(self):
        operator = object.__new__(town.Town)
        operator.clerk = type('Clerk', (), {'database': Path('/unused/world')})()
        root = {'protocol': {}, 'state': {}}
        capture = {'roots': {'candidate': {'root': root, 'reference': {}}}}
        calls = []
        def capture_roots(database, objects, **kwargs):
            calls.append((objects, kwargs))
            return capture
        def observations(view, captured, *, capture_roots):
            capture_roots(['peer'], expected={'peer': 'exact-preimage'})
            return captured
        with patch.object(town.world, 'capture_roots', side_effect=capture_roots), \
             patch.object(town.bootstrap, 'bound_room_artifact', return_value=None), \
             patch.object(town.bootstrap.room, 'inspect_object', return_value={'object': 'candidate'}), \
             patch.object(town.town_cards.source_offers, 'capture_observations', side_effect=observations):
            operator._capture_view('candidate', {}, 'compiled', principal='did:plc:participant')
        self.assertEqual([call[1]['principal'] for call in calls], ['did:plc:participant'] * 2)
        self.assertEqual(calls[1][1]['expected'], {'peer': 'exact-preimage'})

    def test_native_read_refusal_propagates_before_rendering(self):
        operator = object.__new__(town.Town)
        operator.clerk = type('Clerk', (), {'database': Path('/unused/world')})()
        with patch.object(town.world, 'capture_roots', side_effect=ValueError('read refused')), \
             patch.object(town.bootstrap.room, 'inspect_object') as render:
            with self.assertRaisesRegex(ValueError, 'read refused'):
                operator._capture_view('candidate', {}, 'compiled', principal='outsider')
            render.assert_not_called()

    def test_generic_town_body_does_not_publish_private_state(self):
        card = {'title': 'Private candidate', 'prose': '', 'object': 'candidate', 'version': 1, 'actions': []}
        view = {'mode': 'raw', 'object': 'candidate', 'root': {'state': {'secret': 'never-publish-this'}}}
        with patch.object(town.town_cards.projection, 'children', return_value=[]):
            body = town.town_cards.render_card('private', card, view)
        self.assertNotIn('never-publish-this', body)
        self.assertNotIn('secret', body)
        self.assertIn('source-authored view', body)

    def test_source_chosen_summary_remains_visible(self):
        card = {'title': 'Candidate', 'prose': 'Ready for review', 'object': 'candidate', 'version': 1, 'actions': []}
        view = {'mode': 'projection', 'object': 'candidate'}
        with patch.object(town.town_cards.projection, 'children', return_value=[]):
            body = town.town_cards.render_card('review', card, view)
        self.assertIn('Ready for review', body)


if __name__ == '__main__':
    unittest.main()
