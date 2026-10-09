"""Source-owned composite offers: explicit profile, retained output, no guessed plans."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from scene import projection
import affordances
from syntaxes import obend_object
from conformance.test_typed_view import observation, wire
from conformance.test_obend_data_object import SOURCE as BASE


def descriptor(visible=True):
    return {'visible': visible, 'title': 'A shared gesture', 'label': 'Touch the peer',
            'command': 'touchpeer', 'reads': {'peer': {'object': 'peer', 'child': ''}},
            'calls': {'c0': {'op': 'invoke', 'object': 'peer', 'command': 'touch',
                             'input': {}, 'fromResult': False, 'inputFrom': 0}},
            'fields': {}, 'bindings': {}, 'absentChildren': {}, 'captures': {}}


def offer_view(values=None):
    result = observation([])
    result['root']['protocol']['viewProgram']['profile'] = projection.DATA_OFFERS_PROFILE
    values = {'touch': descriptor()} if values is None else values
    result['rawData']['fields'].append({'name': 'offers', 'value': wire(values)})
    result['offers'] = {key: value for key, value in values.items() if value['visible']}
    return result


OFFER_TYPES = '''record ReadRef:
  object: String
  child: String
record Call:
  op: String
  object: String
  command: String
  input: {}
  fromResult: Bool
  inputFrom: Nat
record Offer:
  visible: Bool
  title: String
  label: String
  command: String
  reads: {peer: ReadRef}
  calls: {c0: Call}
  fields: {}
  bindings: {}
  absentChildren: {}
  captures: {}
'''
OFFER = '''{visible: true, title: "A shared gesture", label: "Touch the peer", command: "touchpeer", reads: {peer: {object: "peer", child: ""}}, calls: {c0: {op: "invoke", object: "peer", command: "touch", input: {}, fromResult: false, inputFrom: 0n}}, fields: {}, bindings: {}, absentChildren: {}, captures: {}}'''
SOURCE = BASE.replace('record View:', OFFER_TYPES + 'record View:').replace(
    '  children: Children\ndef describe', '  children: Children\n  offers: {touch: Offer}\ndef describe').replace(
    'children: state.entries}', 'children: state.entries, offers: {touch: ' + OFFER + '}}')


class SourceOfferFraming(unittest.TestCase):
    def test_explicit_profile_and_retained_copy(self):
        view = offer_view({'touch': descriptor(), 'hidden': descriptor(False)})
        self.assertEqual(projection.offers(view), {'touch': descriptor()})
        changed = projection.offers(view)
        changed['touch']['reads']['peer']['object'] = 'elsewhere'
        self.assertEqual(projection.offers(view)['touch']['reads']['peer']['object'], 'peer')
        self.assertEqual(projection.children(view), [])
        wrong = copy.deepcopy(view)
        wrong['offers']['touch']['command'] = 'other'
        with self.assertRaisesRegex(projection.ProjectionError, 'differ'):
            projection.offers(wrong)
        old = observation([])
        self.assertEqual(projection.offers(old), {})
        old['offers'] = {'touch': descriptor()}
        with self.assertRaisesRegex(projection.ProjectionError, 'explicit'):
            projection.offers(old)
        old['mode'] = 'raw'
        self.assertEqual(projection.offers(old), {})

    def test_failed_offer_view_is_inspection_only_even_with_injected_offers(self):
        raw = offer_view()
        raw.update(mode='raw', object='shelf', reason='source budget exhausted')
        self.assertTrue(projection.inspection_only(raw))
        self.assertEqual(projection.offers(raw), {})
        self.assertEqual(projection.children(raw), [])
        self.assertEqual(affordances.card(raw)['actions'], [])
        self.assertEqual(raw['reason'], affordances.card(raw)['prose'])

    def test_hidden_malformed_offer_is_not_removed_before_validation(self):
        bad = descriptor(False)
        bad['calls']['c0']['object'] = 'undeclared'
        with self.assertRaises(projection.ProjectionError):
            projection.offers(offer_view({'hidden': bad}))
        view = offer_view()
        view['root']['protocol']['viewProgram']['profile'] = projection.DATA_MENU_PROFILE
        with self.assertRaisesRegex(projection.ProjectionError, 'declared profile'):
            projection.children(view)
        missing = offer_view()
        missing['rawData']['fields'].pop()
        with self.assertRaisesRegex(projection.ProjectionError, 'declared profile'):
            projection.offers(missing)


class NativeSourceOffers(unittest.TestCase):
    def test_source_optional_field_selects_new_profile_and_native_output(self):
        protocol = obend_object.lower_data(SOURCE)
        self.assertEqual(protocol['viewProgram']['profile'], projection.DATA_OFFERS_PROFILE)
        root = {'protocol': protocol, 'state': protocol['initial'], 'version': 0, 'law': ['author']}
        view = projection.project(root, 'shelf')
        self.assertEqual(projection.offers(view), {'touch': descriptor()})
        self.assertEqual(set(view['data']), {'title', 'prose', 'actions'})
        self.assertEqual(set(projection._wire_record(view['rawData'])),
                         {'title', 'prose', 'actions', 'children', 'offers'})
        self.assertEqual(view['root'], root)

    def test_offer_type_rejects_non_boolean_visibility(self):
        wrong = SOURCE.replace('record Offer:\n  visible: Bool', 'record Offer:\n  visible: Nat').replace(
            'offers: {touch: {visible: true', 'offers: {touch: {visible: 1n')
        with self.assertRaisesRegex(ValueError, 'visible Bool'):
            obend_object.lower_data(wrong)


if __name__ == '__main__':
    unittest.main()
