"""Optional source contribution codecs survive projection and captured custody."""
import copy
import http.client
import threading
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
import source_offers
import town_cards
from conformance.test_view_invitations import fixture, item
from conformance.test_typed_view import wire
from conformance.test_town_cards import ISSUER, ACTOR


def codec_fixture(codec='data'):
    invitation = item()
    invitation['fields'].append({'name': 'contributionCodec', 'value': wire(codec)})
    view = fixture({'gesture': invitation})
    metadata = {'request': 'interpretationRequest', 'prepare': 'prepareInterpretation', 'contributionCodec': codec}
    view['rawData']['fields'].append({'name': 'interpretation', 'value': wire(metadata)})
    view['interpretation'] = projection._typed_interpretation(view['rawData'])
    view.update(object='gallery', panel='main')
    return view


class CodecFraming(unittest.TestCase):
    def test_only_declared_modes_survive_and_legacy_shape_is_unchanged(self):
        self.assertNotIn('contributionCodec', projection.invitations(fixture())['gesture'])
        for codec in ('value', 'data'):
            with self.subTest(codec=codec):
                view = codec_fixture(codec)
                self.assertEqual(projection.invitations(view)['gesture']['contributionCodec'], codec)
                self.assertEqual(projection.interpretation(view)['contributionCodec'], codec)
                changed = projection.interpretation(view)
                changed['contributionCodec'] = 'other'
                self.assertEqual(projection.interpretation(view)['contributionCodec'], codec)
        for codec in ('json', '', True, 1, {'nested': 'data'}):
            with self.subTest(codec=codec), self.assertRaisesRegex(projection.ProjectionError, 'contributionCodec'):
                codec_fixture(codec)
        for codec in ('json', True):
            hidden = item(False)
            hidden['fields'].append({'name': 'contributionCodec', 'value': wire(codec)})
            with self.assertRaisesRegex(projection.ProjectionError, 'contributionCodec'):
                fixture({'hidden': hidden})

    def test_retained_codec_cannot_be_changed_or_added(self):
        for field, read in (('invitations', projection.invitations), ('interpretation', projection.interpretation)):
            view = codec_fixture()
            target = view[field]['gesture'] if field == 'invitations' else view[field]
            target['contributionCodec'] = 'value'
            with self.subTest(field=field), self.assertRaisesRegex(projection.ProjectionError, 'differ'):
                read(view)
        view = fixture()
        view['invitations']['gesture']['contributionCodec'] = 'data'
        with self.assertRaisesRegex(projection.ProjectionError, 'differ'):
            projection.invitations(view)

    def test_card_retains_codec_but_public_fields_cannot_select_typed_transport(self):
        view = codec_fixture()
        peer = {**view['root'], 'version': 1}
        roots = {'gallery': view['root'], 'peer': peer}
        references = {name: {'profile': 'delvetalk-retained-root-v1', 'object': name, 'key': digit * 64}
                      for name, digit in [('gallery', 'a'), ('peer', 'b')]}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            portal.save(directory / 'world.json', {'objects': roots, 'receipts': []})
            portal.save(directory / 'manifest.json', {'cafe': 'gallery', 'runtime': {'name': 'compiled', 'files': {}}})
            old_bytecode = sys.dont_write_bytecode
            self.addCleanup(setattr, sys, 'dont_write_bytecode', old_bytecode)
            app = portal.Portal(directory, public_origin='https://delvetalk.example')
            capture = {'roots': {name: {'root': root, 'reference': references[name]} for name, root in roots.items()},
                       'sequence': 0, 'head': None}
            with patch.object(app, '_view', return_value=view), patch.object(app, 'capture_roots', return_value=capture):
                card = app.object('gallery')
            saved = app._read('cards', card['card'])
            self.assertEqual(saved['offers']['o1']['contributionCodec'], 'data')
            self.assertEqual(card['interpretation']['contributionCodec'], 'data')
            self.assertEqual(card['actions'][0]['contributionCodec'], 'data')
            with patch.object(source_offers.world, 'query', side_effect=AssertionError('Do not guess typed form data')):
                with self.assertRaisesRegex(ValueError, 'explicit DataWire'):
                    app.prepare({'card': card['card'], 'action': 'o1', 'fields': {'gesture': 'wave'}})
            book = town_cards.CardBook.create(directory / 'cards', issuer_did=ISSUER,
                world_id='urn:test:codec', runtime={'name': 'compiled', 'files': {}})
            with patch.object(town_cards.projection, 'assert_runtime'):
                town = book.capture(view, alias='typed', roots=roots, references=references)
            self.assertEqual(book.card('typed')['offers']['a1']['contributionCodec'], 'data')
            self.assertEqual(town['card']['interpretation']['contributionCodec'], 'data')
            with patch.object(source_offers.world, 'query', side_effect=AssertionError('No admission')):
                with self.assertRaisesRegex(ValueError, 'explicit DataWire'):
                    town_cards.composite_offers.request(town['offers']['a1'], ACTOR, 'one', {}, database=app.database)


class NativeCodecCapture(unittest.TestCase):
    def test_actual_source_codec_capture_prepares_unchanged_typed_turn(self):
        import workspace
        from syntaxes import obend_object
        from conformance.test_preparation_data import SOURCE
        source = SOURCE.replace('sum Children:', '''record Invitation:
  visible: Bool
  text: String
  prepare: String
  fields: {}
  contributionCodec: String
  observations: P.Requests
sum Children:''').replace('actions: Actions, children: Children}:',
            'actions: Actions, children: Children, invitations: {choose: Invitation}}:').replace(
            'children: Children.nil()}', 'children: Children.nil(), invitations: {choose: {visible: true, text: "Choose", prepare: "prepareTyped", fields: {}, contributionCodec: "data", observations: P.Requests.cons({head: {object: "peer", inspectState: false, inspectLaw: false}, tail: P.Requests.nil()})}}}')
        protocol = obend_object.lower_data_modules([
            {'name': 'List', 'source': (ROOT / 'world/lib/prelude/List.obend').read_text()}, {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
            {'name': 'Gesture', 'source': source}])
        peer = copy.deepcopy(protocol)
        peer['commands']['choose']['transition']['inputCodec'] = 'data'
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'world'
            workspace.initialize(directory, [{'id': name, 'syntax': 'protocol-json@1',
                'source': portal.canonical(value), 'law': [ACTOR]} for name, value in [('gallery', protocol), ('peer', peer)]],
                entry_objects=['gallery'], principal='operator', profile='compiled', world_id='urn:test:codec')
            database = directory / 'world.json'
            peer_root = portal.world.snapshot(database)['objects']['peer']
            started = portal.world.exchange(database, {'op': 'invoke', 'object': 'peer', 'principal': ACTOR,
                'intent': 'start', 'command': 'start', 'input': {}, 'expected': peer_root}, profile='compiled')
            self.assertEqual(started['kind'], 'committed', started)
            old_bytecode = sys.dont_write_bytecode
            self.addCleanup(setattr, sys, 'dont_write_bytecode', old_bytecode)
            app = portal.Portal(directory, public_origin='https://delvetalk.example')
            before = {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob('*') if path.is_file()}
            server = portal.make_server(app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(thread.join)
            self.addCleanup(server.shutdown)
            def request(method, path, body=None):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
                headers = {'Host': 'delvetalk.example', 'Origin': 'https://delvetalk.example',
                           'Content-Type': 'application/json', 'X-Delvetalk-CSRF': app.csrf}
                connection.request(method, path, body=None if body is None else portal.canonical(body), headers=headers)
                response = connection.getresponse()
                status, result = response.status, portal.loads(response.read())
                connection.close()
                return status, result
            status, card = request('GET', '/api/object?object=gallery')
            self.assertEqual(status, 200, card)
            saved = app._read('cards', card['card'])
            offer = saved['offers']['o1']
            self.assertEqual(offer['contributionCodec'], 'data')
            data = wire({'choice': 12})
            prepared = source_offers.prepare_value(offer, ACTOR, 'native:typed', data, database=database)
            self.assertEqual(prepared['kind'], 'ready', prepared)
            self.assertEqual(prepared['request']['calls'][0]['input'], data)
            self.assertEqual(before, {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob('*') if path.is_file()})
            book = town_cards.CardBook.create(Path(temporary) / 'cards', issuer_did=ISSUER,
                world_id='urn:test:codec', runtime=app.runtime)
            captured = app.capture_roots(['gallery', 'peer'])
            retained = book.capture(saved['view'], alias='typed',
                roots={name: pair['root'] for name, pair in captured['roots'].items()},
                references={name: pair['reference'] for name, pair in captured['roots'].items()})
            town_offer = next(iter(retained['offers'].values()))
            self.assertEqual(source_offers.prepare_value(town_offer, ACTOR, 'native:typed', data, database=database), prepared)
            status, refused_form = request('POST', '/api/prepare', {'card': card['card'], 'action': 'o1', 'fields': {}})
            self.assertEqual(status, 400)
            self.assertIn('explicit DataWire', str(refused_form))
            unauthorized = {**prepared['request'], 'principal': 'outsider', 'intent': 'native:unauthorized'}
            self.assertEqual(portal.world.exchange(database, unauthorized, profile='compiled')['kind'], 'refused')
            admitted = portal.world.exchange(database, prepared['request'], profile='compiled')
            self.assertEqual(admitted['kind'], 'committed', admitted)
            self.assertEqual(portal.world.exchange(database, prepared['request'], profile='compiled'), admitted)
            stale = {**prepared['request'], 'intent': 'native:stale'}
            self.assertEqual(portal.world.exchange(database, stale, profile='compiled')['kind'], 'refused')


if __name__ == '__main__': unittest.main()
