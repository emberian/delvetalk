"""An ordinary source directory joins exact references, one document and real offers."""
from functools import lru_cache
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from syntaxes import obend_object, spell_examples
from scene import projection
from conformance.test_garden_source import protocol as garden_protocol, plantings
from conformance.test_town_cards import ISSUER
import portal
import propose
import resident_store
import source_offers
import town_cards
import workspace
import world


def modules():
    return [{'name': name, 'source': (ROOT / path).read_text()} for name, path in [
        ('Abi', 'world/lib/prelude/Abi.obend'),
        ('List', 'world/lib/prelude/List.obend'), ('Preparation', 'world/lib/prelude/Preparation.obend'),
        ('Encounter', 'world/lib/prelude/Encounter.obend'),
        ('Document', 'world/lib/document/Document.obend'),
        ('Directory', 'protocols/root-directory/Directory.obend'),
        ('GSBWelcome', 'protocols/root-directory/GSBWelcome.obend')]]


@lru_cache(maxsize=1)
def protocol():
    return obend_object.lower_data_modules(modules())


LAW = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {
    'setDoor': ['steward'], 'choose': ['iris', 'moss']},
    'reprogram': ['steward'], 'law': ['steward']}


def door(key='garden', target='garden', **changes):
    return {'key': key, 'label': key.upper(), 'object': target, 'panel': 'main',
            'description': 'An actual configured encounter.',
            'example': 'A silver fern, please.', 'available': True, 'show': True, **changes}


def nodes(document):
    yield document
    for child in document.get('items', []):
        yield from nodes(child)
    if 'body' in document:
        yield from nodes(document['body'])


class RootDirectory(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'world.sqlite'
        self.receiver = resident_store.Resident(self.path)
        self.addCleanup(lambda: self.receiver.close())
        self.serial = 0
        for identity, program, law in [('root', protocol(), LAW), ('garden', garden_protocol(), ['iris', 'moss'])]:
            self.exchange({'op': 'create', 'object': identity, 'principal': 'operator',
                'intent': 'create-' + identity, 'protocol': program, 'law': law})

    def exchange(self, request, kind='committed'):
        result = self.receiver.exchange(request)
        self.assertEqual(result['kind'], kind, result)
        return result

    def root(self, identity='root'):
        return self.receiver.exchange({'op': 'inspect', 'object': identity, 'principal': 'reader'})

    def invoke(self, command, value, actor='steward', identity='root', kind='committed'):
        self.serial += 1
        return self.exchange({'op': 'invoke', 'object': identity, 'principal': actor,
            'intent': 'turn-' + str(self.serial), 'expected': self.root(identity),
            'command': command, 'input': value}, kind)

    def invitation(self):
        view = projection.project(self.root(), 'root')
        return source_offers.capture(view, {'root': self.root(), 'garden': self.root('garden')})['choose']

    def test_unavailable_then_configured_documents_and_open_ended_keys(self):
        view = projection.project(self.root(), 'root')
        self.assertEqual(view['children'], [])
        self.assertEqual(source_offers.capture(view, {'root': self.root()}), {})
        self.assertEqual(view['data']['prose'].count('Not open in this directory yet.'), 6)
        for key in ('garden', 'rooms', 'conversations', 'play', 'workshop', 'studio'):
            self.assertIn(key.upper(), view['data']['prose'])
        self.invoke('setDoor', door(), actor='moss', kind='refused')
        self.invoke('setDoor', door())
        self.invoke('setDoor', door('observatory'))
        self.invoke('setDoor', door('studio', target='', available=False, show=False))
        view = projection.project(self.root(), 'root')
        self.assertEqual([child['key'] for child in view['children']], ['garden', 'observatory'])
        self.assertNotIn('STUDIO', view['data']['prose'])
        invitation = self.invitation()
        self.assertEqual([item['object'] for item in invitation['observations']], ['garden'])
        question = source_offers.prepare(invitation, 'iris', 'which', {'original': 'Somewhere quiet.'})
        self.assertEqual(question['kind'], 'question')
        self.assertEqual(question['needs'], ['door'])
        for key in ('rooms', 'unknown', 'studio'):
            self.assertEqual(source_offers.prepare(invitation, 'iris', key,
                {'door': key, 'original': 'A suggestion is not a reference.'})['kind'], 'refused')
        self.invoke('setDoor', door('library'))
        before = self.root()
        self.invoke('setDoor', door('ninth'), kind='refused')
        self.assertEqual(self.root(), before)
        self.invoke('setDoor', door('observatory', description='A revised welcome.'))
        self.assertIn('A revised welcome.', projection.project(self.root(), 'root')['data']['prose'])
        self.invoke('setDoor', door('studio', target='', available=False, show=True))
        self.assertIn('STUDIO', projection.project(self.root(), 'root')['data']['prose'])

    def test_exact_selected_target_current_law_and_retained_retry(self):
        self.invoke('setDoor', door())
        before = self.root('garden')
        original = 'garden — a silver fern that remembers yesterday.'
        ready = source_offers.prepare(self.invitation(), 'iris', 'choose-iris', {'door': 'garden', 'original': original})
        self.assertEqual(ready['kind'], 'ready')
        self.assertEqual(set(ready['request']['reads']), {'root', 'garden'})
        self.assertEqual(ready['request']['calls'], [{'object': 'root', 'command': 'choose',
            'input': {'door': 'garden', 'original': original}}])
        receipt = self.exchange(ready['request'])
        self.assertEqual(self.root('garden'), before)
        self.assertIn(original, str(receipt))
        self.assertIn("'by': 'iris'", str(receipt))
        self.assertEqual(self.receiver.exchange(ready['request']), receipt)
        stale = source_offers.prepare(self.invitation(), 'moss', 'before-garden-change', {'door': 'garden', 'original': 'Let me join.'})
        self.invoke('plant', {'seed': 'A listening fern', 'colour': 'silver'}, 'iris', 'garden')
        rejected = self.exchange(stale['request'], 'refused')
        self.assertEqual(rejected['data'], 'stale read root')
        self.assertEqual(self.receiver.exchange(stale['request']), rejected)
        fresh = source_offers.prepare(self.invitation(), 'moss', 'after-garden-change', {'door': 'garden', 'original': 'Let me join.'})
        self.exchange(fresh['request'])
        self.assertEqual(len(plantings(self.root('garden'))), 1)
        # A separate target invitation/action is required to contribute there.
        self.invoke('rain', {'id': 1, 'line': 'Yesterday remembers the rain.'}, 'moss', 'garden')
        bloom = plantings(self.root('garden'))[0]
        self.assertEqual((bloom['planter'], bloom['rainmaker']), ('iris', 'moss'))
        old = source_offers.prepare(self.invitation(), 'iris', 'before-disable', {'door': 'garden', 'original': ''})
        self.invoke('setDoor', door(available=False))
        self.exchange(old['request'], 'refused')
        self.invoke('choose', {'door': 'garden', 'original': ''}, 'iris', kind='refused')
        self.invoke('setDoor', door())
        pending = source_offers.prepare(self.invitation(), 'iris', 'before-law', {'door': 'garden', 'original': ''})
        self.exchange({'op': 'law', 'object': 'root', 'principal': 'steward', 'intent': 'restrict',
            'expected': self.root(), 'law': {**LAW, 'invoke': {**LAW['invoke'], 'choose': ['moss']}}})
        self.exchange(pending['request'], 'refused')
        fresh = source_offers.prepare(self.invitation(), 'iris', 'after-law', {'door': 'garden', 'original': ''})
        self.exchange(fresh['request'], 'refused')
        self.receiver.checkpoint()
        self.receiver.close()
        self.receiver = resident_store.Resident(self.path)
        self.assertEqual(self.receiver.exchange(ready['request']), receipt)

    def test_authored_examples(self):
        cases = spell_examples.parse((ROOT / 'protocols/root-directory/root.examples').read_text())
        self.assertEqual([item['failures'] for item in propose.run_scenarios(protocol(), cases, profile='compiled')], [[]])


class RootDocumentConsumers(unittest.TestCase):
    def test_browser_and_town_share_the_source_document_and_real_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'world'
            workspace.initialize(directory, [{'id': name, 'syntax': 'protocol-json@1',
                'source': portal.canonical(value), 'law': law} for name, value, law in
                [('root', protocol(), LAW), ('garden', garden_protocol(), ['iris', 'moss'])]],
                entry_objects=['root'], principal='operator', profile='compiled', world_id='urn:test:root-directory')
            app = portal.Portal(directory)
            captured = app.capture_roots(['root'])
            receipt = world.exchange(app.database, {'op': 'invoke', 'object': 'root', 'principal': 'steward',
                'intent': 'open-garden', 'expected': captured['roots']['root']['root'],
                'command': 'setDoor', 'input': door()}, profile='compiled')
            self.assertEqual(receipt['kind'], 'committed', receipt)
            card = app.object('root')
            self.assertEqual(card['mode'], 'projection')
            self.assertEqual({node['childKey'] for node in nodes(card['document']) if 'childKey' in node}, {'garden'})
            action = next(item for item in card['actions'] if item.get('preparation'))
            self.assertEqual([node['actionId'] for node in nodes(card['document']) if 'actionId' in node], [action['id']])
            saved = app._read('cards', card['card'])
            self.assertEqual(card['prose'], saved['view']['data']['prose'])
            book = town_cards.CardBook.create(Path(temporary) / 'cards', issuer_did=ISSUER,
                world_id='urn:test:root-directory', runtime=app.runtime)
            paired = app.capture_roots(['root', 'garden'])['roots']
            town = book.capture(saved['view'], alias='welcome', roots={name: pair['root'] for name, pair in paired.items()},
                references={name: pair['reference'] for name, pair in paired.items()})
            self.assertEqual(town['view']['document'], saved['view']['document'])
            self.assertIn('GARDEN', town['body'])
            self.assertIn('Not open in this directory yet.', town['body'])
            request = app.captured_request(saved, action['id'], 'moss', 'portal-choice',
                {'door': 'garden', 'original': 'garden — something that listens.'})
            receipt = world.exchange(app.database, request, profile='compiled')
            self.assertEqual(receipt['kind'], 'committed', receipt)
            self.assertEqual(world.exchange(app.database, request, profile='compiled'), receipt)


if __name__ == '__main__': unittest.main()
