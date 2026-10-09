"""Captured source invitations: exact observations, no recipe interpretation."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import source_offers
from conformance.test_view_invitations import fixture


class InvitationCapture(unittest.TestCase):
    def setUp(self):
        self.view = fixture()
        self.view.update(object='owner', panel='main')
        self.peer = {'protocol': {'commands': {}}, 'law': [], 'version': 4, 'state': {'word': 'captured'}}
        self.roots = {'owner': self.view['root'], 'peer': self.peer,
                      'unrequested': {'state': {'private': 'not a preparation argument'}}}

    def test_capture_keeps_only_declared_observations_and_exact_owner(self):
        invitation = source_offers.capture(self.view, self.roots)['gesture']
        self.assertEqual(invitation['format'], source_offers.FORMAT)
        self.assertEqual(invitation['entry'], 'prepareGesture')
        self.assertEqual(invitation['object'], 'owner')
        self.assertEqual(invitation['root'], self.view['root'])
        self.assertEqual(invitation['observations'], [{'object': 'peer', 'root': self.peer, 'inspectState': False, 'inspectLaw': False}])
        self.assertNotIn('calls', invitation)
        self.assertNotIn('bindings', invitation)
        self.assertNotIn('captures', invitation)
        before = copy.deepcopy(invitation)
        self.peer['version'] += 1
        self.roots['owner'] = {**self.view['root'], 'version': 8}
        self.assertEqual(invitation, before)
        with self.assertRaisesRegex(ValueError, 'owner root'):
            source_offers.capture(self.view, self.roots)

    def test_missing_observation_disables_only_invitation_without_fetch(self):
        del self.roots['peer']
        result = source_offers.capture_available(self.view, self.roots)
        self.assertEqual(result['offers'], {})
        self.assertIn('peer', result['unavailable']['gesture']['reason'])
        self.assertEqual(result['unavailable']['gesture']['command'], 'prepareGesture')

    def test_tampered_descriptor_and_removed_recipe_language_refuse(self):
        changed = copy.deepcopy(self.view)
        changed['invitations']['gesture']['prepare'] = 'different'
        with self.assertRaisesRegex(ValueError, 'differ'):
            source_offers.capture(changed, self.roots)
        with self.assertRaisesRegex(ValueError, 'invitation'):
            source_offers.validate({'format': 'delvetalk-composite-offer-v1',
                                    'calls': [], 'bindings': [], 'captures': {}})


if __name__ == '__main__':
    unittest.main()
