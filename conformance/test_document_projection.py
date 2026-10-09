"""Source Document structure and exact captured bindings across Portal and Town."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from scene import projection
import portal
import town_cards
from conformance.test_typed_view import observation, wire
from conformance.test_view_invitations import names
from conformance.test_town_cards import ISSUER


def record(**fields):
    return {'tag': 'record', 'fields': [{'name': name, 'value': value} for name, value in fields.items()]}


def variant(kind, **fields):
    return {'tag': 'variant', 'label': kind, 'payload': record(**fields)}


def sequence(items):
    tail = variant('nil')
    for item in reversed(items):
        tail = variant('cons', head=item, tail=tail)
    return tail


def fixture():
    child = {'key': 'lantern', 'label': 'Lantern', 'object': 'objects/lantern', 'panel': 'main'}
    view = observation([child])
    view.update(object='gallery', panel='main')
    invitation = record(visible=wire(True), text=wire('Source offer'), prepare=wire('prepareAnswer'),
                        fields=wire({}), observations=names([]))
    view['rawData']['fields'].append({'name': 'invitations', 'value': record(answer=invitation)})
    view['invitations'] = projection._typed_invitations(view['rawData'])
    capture = {'object': 'gallery', 'revision': 2**80, 'meaning': 'source meaning', 'entry': 'prepareAnswer', 'token': 'answer'}
    doc = variant('sequence', items=sequence([
        variant('text', value=wire('<b>Source text</b>')),
        variant('offer', label=wire('Source offer'), capture=wire(capture)),
        variant('offer', label=wire('Source offer'), capture=wire({**capture, 'object': 'intruder'})),
        variant('offer', label=wire('Source offer'), capture=wire({**capture, 'entry': 'otherExport'})),
        variant('offer', label=wire('Source offer'), capture=wire({**capture, 'token': 'other'})),
        variant('fields', capture=wire(capture), values=sequence([
            record(name=wire('answer'), value=variant('natural', value=wire(2**80)))]), needs=names(['answer'])),
        variant('reference', **{key: wire(value) for key, value in child.items()}),
        variant('reference', **{key: wire(value) for key, value in {**child, 'object': 'intruder'}.items()}),
        variant('continuation', key=wire('page'), after=wire(2**80), limit=wire(8), label=wire('More')),
        variant('result', status=wire('question'), body=variant('quote', attribution=wire('Source'),
            body=variant('source', language=wire('Bend'), code=wire('literal bytes\n'), revision=wire('r1'))))]))
    view['rawData']['fields'].append({'name': 'document', 'value': doc})
    view['document'] = projection._document_data(doc)
    metadata = {'request': 'interpretationRequest', 'prepare': 'prepareInterpretation'}
    view['rawData']['fields'].append({'name': 'interpretation', 'value': wire(metadata)})
    view['interpretation'] = metadata
    return view


class DocumentFraming(unittest.TestCase):
    def test_exact_structure_and_binding_never_uses_display_label(self):
        view = fixture()
        actions = [{'id': 'o1', 'offer': 'answer', 'available': True}]
        offers = {'o1': {'object': 'gallery', 'entry': 'prepareAnswer'}}
        document = projection.bound_document(view, actions, offers)
        items = document['items']
        self.assertEqual(items[0]['value'], '<b>Source text</b>')
        self.assertEqual(items[1]['actionId'], 'o1')
        self.assertEqual(items[1]['capture']['revision'], str(2**80))
        for item in items[2:5]:
            self.assertNotIn('actionId', item)
        self.assertEqual(items[5]['actionId'], 'o1')
        self.assertEqual(items[5]['values'], [{'name': 'answer', 'value': {'kind': 'natural', 'value': str(2**80)}}])
        self.assertEqual(items[6]['childKey'], 'lantern')
        self.assertNotIn('childKey', items[7])
        self.assertNotIn('actionId', items[8])
        self.assertEqual(items[8]['after'], str(2**80))
        self.assertEqual(items[9]['body']['body']['code'], 'literal bytes\n')
        self.assertNotIn('actionId', view['document']['items'][1])
        self.assertNotIn('actionId', projection.bound_document(view, [{**actions[0], 'available': False}], offers)['items'][1])

    def test_raw_origin_shape_and_bounds_are_checked(self):
        view = fixture()
        forged = copy.deepcopy(view)
        forged['document']['items'][1]['capture']['token'] = 'other'
        with self.assertRaisesRegex(projection.ProjectionError, 'differs'):
            projection.document(forged)
        forged = copy.deepcopy(view)
        forged['interpretation']['prepare'] = 'otherExport'
        with self.assertRaisesRegex(projection.ProjectionError, 'differs'):
            projection.interpretation(forged)
        malformed = [variant('invented'), variant(['invalid']), variant('text', value=wire(True)),
                     variant('offer', label=wire('hi'), capture=wire({'object': 'x', 'revision': '0',
                         'meaning': '', 'entry': 'e', 'token': 't'})),
                     variant('sequence', items=sequence([variant('text', value=wire('x'))] * 257))]
        for doc in malformed:
            with self.subTest(doc=doc['label']), self.assertRaises(projection.ProjectionError):
                projection._document_data(doc)
        value = variant('text', value=wire('x'))
        for _ in range(33):
            value = variant('quote', attribution=wire('a'), body=value)
        with self.assertRaisesRegex(projection.ProjectionError, 'bound'):
            projection._document_data(value)
        malformed = copy.deepcopy(view['rawData'])
        malformed['fields'][-1]['value'] = wire({'request': '../bad', 'prepare': 'p'})
        with self.assertRaisesRegex(projection.ProjectionError, 'export'):
            projection._typed_interpretation(malformed)
        view['mode'] = 'raw'
        self.assertIsNone(projection.document(view))
        self.assertIsNone(projection.interpretation(view))

    def test_portal_and_town_retain_same_qualified_document(self):
        view = fixture()
        root = view['root']
        references = {'gallery': {'profile': 'delvetalk-retained-root-v1', 'object': 'gallery', 'key': 'a' * 64}}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            portal.save(directory / 'world.json', {'objects': {'gallery': root}, 'receipts': []})
            portal.save(directory / 'manifest.json', {'cafe': 'gallery', 'runtime': {'name': 'compiled', 'files': {}}})
            app = portal.Portal(directory)
            paired = {'roots': {'gallery': {'root': root, 'reference': references['gallery']}}, 'sequence': 0, 'head': None}
            with patch.object(app, '_view', return_value=view), patch.object(app, 'capture_roots', return_value=paired):
                card = app.object('gallery')
            self.assertEqual(app.card(card['card'])['document'], card['document'])
            self.assertEqual(card['document']['items'][1]['actionId'], 'o1')
            self.assertEqual(card['interpretation'], view['interpretation'])
            book = town_cards.CardBook.create(directory / 'cards', issuer_did=ISSUER,
                world_id='urn:test:document', runtime={'name': 'compiled', 'files': {}})
            with patch.object(town_cards.projection, 'assert_runtime'):
                town = book.capture(view, alias='document', roots={'gallery': root}, references=references)
            retained = book.card('document')
            self.assertEqual(retained['card']['document'], town['card']['document'])
            self.assertEqual(retained['card']['document']['items'][1]['actionId'], 'a1')
            self.assertEqual(retained['card']['interpretation'], card['interpretation'])
            self.assertEqual(town['view']['rawData'], view['rawData'])
            self.assertIn('Look around.', town['body'])  # Source-authored prose is the town fallback.


class NativeDocumentConsumers(unittest.TestCase):
    def test_real_notebook_document_and_invitations_share_portal_town_capture(self):
        import workspace
        from syntaxes import obend_object
        from conformance.test_document_conversation import modules
        protocol = obend_object.lower_data_modules(modules())
        moth = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {}}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'world'
            workspace.initialize(directory, [{'id': name, 'syntax': 'protocol-json@1',
                'source': portal.canonical(value), 'law': ['iris']} for name, value in
                [('conversation', protocol), ('moth:amber', moth), ('moth:silver', moth)]],
                entry_objects=['conversation'], principal='operator', profile='compiled', world_id='urn:test:document')
            old_bytecode = sys.dont_write_bytecode
            self.addCleanup(setattr, sys, 'dont_write_bytecode', old_bytecode)
            app = portal.Portal(directory, public_origin='https://delvetalk.example')
            before = {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob('*') if path.is_file()}
            card = app.object('conversation')
            self.assertEqual(card['mode'], 'projection')
            self.assertIn('document', card)
            self.assertEqual(card['interpretation'], {'request': 'interpretationRequest', 'prepare': 'prepareInterpretation'})
            self.assertTrue(any(action.get('preparation') for action in card['actions']))
            def nodes(node):
                yield node
                for child in node.get('items', []):
                    yield from nodes(child)
                if 'body' in node:
                    yield from nodes(node['body'])
            prepared = {action['id'] for action in card['actions'] if action.get('preparation')}
            self.assertTrue(any(node.get('actionId') in prepared for node in nodes(card['document'])))
            self.assertEqual({node['childKey'] for node in nodes(card['document']) if 'childKey' in node},
                             {child['key'] for child in card['children']})
            saved = app._read('cards', card['card'])
            book = town_cards.CardBook.create(Path(temporary) / 'cards', issuer_did=ISSUER,
                world_id='urn:test:document', runtime=app.runtime)
            captured = app.capture_roots(['conversation', 'moth:amber', 'moth:silver'])
            roots = {name: pair['root'] for name, pair in captured['roots'].items()}
            refs = {name: pair['reference'] for name, pair in captured['roots'].items()}
            retained = book.capture(saved['view'], alias='notebook', roots=roots, references=refs)
            self.assertEqual(book.card('notebook')['view']['document'], saved['view']['document'])
            self.assertEqual(retained['card']['interpretation'], card['interpretation'])
            self.assertEqual(before, {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob('*') if path.is_file()})


if __name__ == '__main__': unittest.main()
