"""Source-plan framing controls: exact snapshots, bounded substitutions and reads."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import composite_offers
import source_offers
import transaction_intake
import town_cards

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

    def test_normal_town_card_discovers_and_resolves_source_plan(self):
        def wire(value):
            if isinstance(value, str): return {'tag': 'label', 'value': value}
            if type(value) is bool: return {'tag': 'boolean', 'value': value}
            if type(value) is int: return {'tag': 'natural', 'value': str(value)}
            return {'tag': 'record', 'fields': [{'name': key, 'value': wire(child)} for key, child in value.items()]}
        source = descriptor()
        owner = copy.deepcopy(ROOT)
        owner['protocol']['viewProgram'] = {'profile': town_cards.projection.DATA_OFFERS_PROFILE}
        raw = wire({'title': 'Workshop', 'prose': 'Submit a variation.', 'actions': {}, 'offers': {'submit': source}})
        raw['fields'].append({'name': 'children', 'value': {'tag': 'variant', 'label': 'nil', 'payload': wire({})}})
        pins = {'.lake/build/bin/delvetalk-compiled': 'framing-test'}
        view = {'object': 'editor', 'root': owner, 'mode': 'projection', 'rawData': raw,
                'data': {'title': 'Workshop', 'prose': 'Submit a variation.', 'actions': {}},
                'actions': {}, 'children': [], 'offers': {'submit': source},
                'runtimeProfile': {'profile': 'compiled', 'files': pins}, 'runtimeSha256': 'framing-test'}
        issuer, actor = 'did:plc:' + 'a' * 24, 'did:plc:' + 'b' * 24
        roots = {'editor': owner, 'target': copy.deepcopy(ROOT), 'factory/first': copy.deepcopy(ROOT)}
        with tempfile.TemporaryDirectory() as directory:
            book = town_cards.CardBook.create(Path(directory) / 'book', issuer_did=issuer,
                world_id='urn:test:source-offer', runtime={'name': 'compiled', 'files': pins})
            captured = book.capture(view, 'ordinary', roots=roots)
            self.assertIn('delvetalk ordinary submit', captured['body'])
            self.assertEqual(captured['card']['actions'][0]['command'], 'submit')
            self.assertEqual(set(captured['offers']), {'a1'})
            missing = book.capture(view, 'missing')
            self.assertFalse(missing['card']['actions'][0]['available'])
            self.assertNotIn('offers', missing)
            publication = {'uri': 'at://' + issuer + '/' + town_cards.FEED + '/card', 'cid': 'card-cid'}
            record = {'$type': town_cards.FEED, 'text': captured['body']}
            book.bind('ordinary', publication, lambda uri, cid: copy.deepcopy(record))
            roots['target']['state']['count'] = 999
            reply = {'$type': town_cards.FEED, 'text': 'delvetalk ordinary submit\nsource: exact bytes',
                     'reply': {'parent': publication}}
            reply_source = {'uri': 'at://' + actor + '/' + town_cards.FEED + '/reply', 'cid': 'reply-cid'}
            payload, _ = book.resolve(reply, actor, reply_source,
                lambda uri, cid: copy.deepcopy(record), [issuer])
            self.assertEqual(payload['op'], 'transaction')
            self.assertEqual(payload['calls'][0]['input']['proposal']['source'], 'exact bytes')
            self.assertEqual(payload['calls'][0]['input']['migration'], {'count': 7})
            transaction_intake.validate(payload)

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
