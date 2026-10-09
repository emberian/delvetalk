"""Pure source invitation framing. Observation acquisition and preparation are separate."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from scene import projection
from syntaxes import obend_object
from conformance.test_typed_view import observation, wire
from conformance.test_view_action_lists import SOURCE as BASE


def names(values):
    tail = {'tag': 'variant', 'label': 'nil', 'payload': wire({})}
    for value in reversed(values):
        tail = {'tag': 'variant', 'label': 'cons', 'payload': {'tag': 'record', 'fields': [
            {'name': 'head', 'value': wire(value)}, {'name': 'tail', 'value': tail}]}}
    return tail


def item(visible=True):
    value = wire({'visible': visible, 'text': 'Offer a gesture', 'prepare': 'prepareGesture', 'fields': {}})
    value['fields'].append({'name': 'observations', 'value': names([{'object': 'peer', 'inspectState': False, 'inspectLaw': False}])})
    return value


def fixture(rows=None):
    view = observation([])
    raw = {'tag': 'record', 'fields': [{'name': key, 'value': value}
           for key, value in (rows or {'gesture': item()}).items()]}
    view['rawData']['fields'].append({'name': 'invitations', 'value': raw})
    view['invitations'] = projection._typed_invitations(view['rawData'])
    return view


EXTRA = '''record Invitation:
  visible: Bool
  text: String
  prepare: String
  fields: {}
  observations: P.Requests
'''
SOURCE = BASE.replace('sum Children:', EXTRA + 'sum Children:').replace(
    'actions: Actions, children: Children}', 'actions: Actions, children: Children, invitations: {gesture: Invitation}}').replace(
    'children: Children.nil()}', 'children: Children.nil(), invitations: {gesture: {visible: true, text: "Offer a gesture", prepare: "prepareGesture", fields: {}, observations: P.Requests.cons({head: {object: "peer", inspectState: false, inspectLaw: false}, tail: P.Requests.nil()})}}}')


SOURCE = SOURCE.replace('edition ObjectiveBend 1\n', 'edition ObjectiveBend 1\nimport ./Preparation.obend as P\n', 1)
SOURCE += '''def prepareGesture(state: State, contribution: P.Value, observations: P.Observations, context: P.Context) -> P.Preparation:
  P.Preparation.question({message: "Which gesture would you like?", needs: P.Names.cons({head: "gesture", tail: P.Names.nil()})})
'''


class InvitationFraming(unittest.TestCase):
    def test_retained_copy_filters_visibility_without_fetching_or_retargeting(self):
        view = fixture({'gesture': item(), 'hidden': item(False)})
        expected = {'gesture': {'visible': True, 'text': 'Offer a gesture', 'prepare': 'prepareGesture',
                               'fields': {}, 'observations': [{'object': 'peer', 'inspectState': False, 'inspectLaw': False}]}}
        self.assertEqual(projection.invitations(view), expected)
        copied = projection.invitations(view)
        copied['gesture']['observations'] = ['other']
        self.assertEqual(projection.invitations(view), expected)
        for key, changed in [('prepare', 'otherExport'), ('observations', ['other'])]:
            forged = copy.deepcopy(view)
            forged['invitations']['gesture'][key] = changed
            with self.assertRaisesRegex(projection.ProjectionError, 'differ'):
                projection.invitations(forged)
        self.assertEqual(projection.invitations(observation([])), {})
        view['mode'] = 'raw'
        self.assertEqual(projection.invitations(view), {})

    def test_observation_flags_are_exact_source_booleans(self):
        invitation = item()
        requested = [{'object': 'peer', 'inspectState': True, 'inspectLaw': False}]
        invitation['fields'][-1]['value'] = names(requested)
        self.assertEqual(projection.invitations(fixture({'gesture': invitation}))['gesture']['observations'], requested)
        for invalid in ('peer', {'object': 'peer'}, {'object': 'peer', 'inspectState': 1, 'inspectLaw': False}):
            invitation['fields'][-1]['value'] = names([invalid])
            with self.subTest(invalid=invalid), self.assertRaisesRegex(projection.ProjectionError, 'booleans'):
                fixture({'gesture': invitation})

    def test_hidden_metadata_and_duplicate_observations_are_checked(self):
        hidden = item(False)
        hidden['fields'][2]['value'] = wire('../not-an-export')
        with self.assertRaisesRegex(projection.ProjectionError, 'export name'):
            fixture({'hidden': hidden})
        hidden = item(False)
        hidden['fields'][-1]['value'] = names([{'object': 'peer', 'inspectState': False, 'inspectLaw': False}] * 2)
        with self.assertRaisesRegex(projection.ProjectionError, 'duplicate'):
            fixture({'hidden': hidden})
        hidden['fields'][-1]['value'] = names([{'object': str(i), 'inspectState': False, 'inspectLaw': False} for i in range(17)])
        with self.assertRaisesRegex(projection.ProjectionError, '16'):
            fixture({'hidden': hidden})


class NativeInvitations(unittest.TestCase):
    def test_source_invitations_use_current_typed_view_without_another_profile(self):
        protocol = obend_object.lower_data_modules([
            {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
            {'name': 'Gestures', 'source': SOURCE}])
        self.assertEqual(protocol['viewProgram']['profile'], projection.DATA_MENU_PROFILE)
        self.assertEqual(protocol['preparation'], {'profile': 'delvetalk-source-preparation-v1',
            'sourcePackage': projection.source_packages.NAME})
        root = {'protocol': protocol, 'state': protocol['initial'], 'version': 0, 'law': ['actor']}
        view = projection.project(root, 'gestures')
        self.assertEqual(projection.invitations(view)['gesture']['observations'], [{'object': 'peer', 'inspectState': False, 'inspectLaw': False}])
        self.assertEqual(projection.invitations(view)['gesture']['prepare'], 'prepareGesture')
        self.assertEqual(projection.action_order(view), ['z-start'])
        self.assertEqual(view['root'], root)


if __name__ == '__main__':
    unittest.main()
