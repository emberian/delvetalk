"""Source-plan framing controls: exact snapshots, bounded substitutions and reads."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import composite_offers
import source_offers
import transaction_intake

ROOT = {'law': ['maker'], 'protocol': {'commands': {}}, 'state': {'count': 7}, 'version': 3}


def descriptor():
    return {'visible': True, 'title': 'Workshop', 'label': 'Submit', 'command': 'submit',
        'reads': {'candidate': {'object': 'factory/first', 'child': ''},
                  'target': {'object': 'target', 'child': ''}},
        'calls': {'c0': {'op': 'invoke', 'object': 'candidate', 'command': 'submit',
            'input': {'proposal': {'source': ''}, 'migration': {}}, 'fromResult': False, 'inputFrom': 0}},
        'fields': {'source': {'type': 'string', 'label': 'Source', 'minLength': 1, 'maxLength': 32768}},
        'bindings': {'b0': {'field': 'source', 'call': 0, 'input': 'proposal.source'}},
        'captures': {'s0': {'read': 'target', 'call': 0, 'input': 'migration', 'rootField': 'state'}},
        'absentChildren': {}}


class SourceOfferCapture(unittest.TestCase):
    def capture(self, source=None):
        source = descriptor() if source is None else source
        source_offers.validate_descriptors({'submit': source})
        roots = {key: copy.deepcopy(ROOT) for key in ('editor', 'factory/first', 'target')}
        view = {'object': 'editor', 'root': copy.deepcopy(ROOT)}
        return source_offers.capture_descriptor(view, roots, source), roots

    def test_nested_exact_source_and_captured_migration_never_refresh(self):
        offer, roots = self.capture()
        before = copy.deepcopy(offer)
        roots['target']['state']['count'] = 999
        source = 'edition ObjectiveBend 1\r\n# exact λ\n' * 200
        request = composite_offers.request(offer, 'maker', 'intent', {'source': source})
        self.assertEqual(request['calls'][0]['input']['proposal']['source'], source)
        self.assertEqual(request['calls'][0]['input']['migration'], {'count': 7})
        self.assertEqual(request['reads']['editor'], ROOT)
        self.assertEqual(offer, before)
        self.assertEqual(composite_offers.request(offer, 'maker', 'intent', {'source': source}), request)
        transaction_intake.validate(composite_offers.wire(offer, {'source': source}))

    def test_source_field_and_total_request_bounds_both_apply(self):
        offer, _ = self.capture()
        with self.assertRaises(ValueError):
            composite_offers.request(offer, 'maker', 'intent', {'source': 'x' * 32769})
        offer['reads']['target']['state']['large'] = 'x' * 65536
        with self.assertRaisesRegex(ValueError, '64 KiB'):
            composite_offers.request(offer, 'maker', 'intent', {'source': 'x'})

    def test_absent_child_is_explicit_and_derived_without_refresh(self):
        offer, _ = self.capture()
        offer['fields'] = [{'name': 'name', 'type': 'string', 'label': 'Name', 'required': True,
                            'minLength': 1, 'maxLength': 64}]
        offer['calls'][0]['input'] = {'name': None}
        offer['bindings'] = [{'field': 'name', 'call': 0, 'input': 'name'}]
        offer['absentChildren'] = [{'factory': 'target', 'field': 'name'}]
        request = composite_offers.request(offer, 'maker', 'intent', {'name': 'fresh'})
        self.assertIsNone(request['reads']['target/fresh'])
        wire = composite_offers.wire(offer, {'name': 'fresh'})
        self.assertEqual(wire['reads']['target/fresh'], {'expected': None})
        transaction_intake.validate(wire)
        with self.assertRaises(ValueError):
            composite_offers.request(offer, 'maker', 'intent', {'name': '../escape'})

    def test_hidden_malformed_plan_and_different_owner_snapshot_refuse(self):
        source = descriptor()
        source['visible'] = False
        source['calls']['c0']['object'] = 'unbound'
        with self.assertRaises(ValueError):
            source_offers.validate_descriptors({'hidden': source})
        with self.assertRaisesRegex(ValueError, 'same exact owner'):
            source_offers.capture_descriptor({'object': 'editor', 'root': ROOT},
                {'editor': {**ROOT, 'version': 4}}, descriptor())

    def test_reprogram_and_law_steps_are_exact_native_shapes(self):
        offer, _ = self.capture()
        offer['calls'].append({'op': 'reprogram', 'object': 'target', 'inputFrom': 0})
        offer['calls'].append({'op': 'law', 'object': 'target', 'law': ['maker']})
        wire = composite_offers.wire(offer, {'source': 'source'})
        transaction_intake.validate(wire)
        injected = copy.deepcopy(wire)
        injected['calls'][2]['principal'] = 'operator'
        with self.assertRaises(ValueError): transaction_intake.validate(injected)
        offer['calls'][1]['inputFrom'] = 1
        with self.assertRaises(ValueError): composite_offers.validate(offer)


if __name__ == '__main__': unittest.main()
