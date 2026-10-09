"""Normal Town cards discover pure source preparations and retain conversation outcomes."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import history
import source_offers
import town
import town_cards
from syntaxes import obend_object
from conformance.test_preparation import SOURCE as SOURCE_WITH_TEXT
SOURCE = SOURCE_WITH_TEXT.replace('textConcat("Offer ", gesture)', '"Offer gesture"')
from conformance.test_town_receiving import fixture, A, B, ISSUER


class TownPreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = obend_object.lower_data_modules([
            {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
            {'name': 'Gallery', 'source': SOURCE}])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='town-preparation-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.pds = fixture.FakePDS()
        self.c = clerk.Clerk(self.base / 'clerk', self.pds)
        self.c.bootstrap('gallery', self.protocol, [A], [A, B], runtime_profile='compiled')
        peer = {'profile': 'delvetalk-local-v1', 'initial': {'touched': ''},
            'commands': {'touch': {'require': [], 'set': {'touched': ['input', 'gesture']},
                                   'result': ['input', 'gesture'], 'outbox': []}}}
        receipt = clerk.world.exchange(self.c.database, {'op': 'create', 'object': 'peer', 'principal': 'operator',
            'intent': 'create:peer', 'protocol': peer, 'law': [A]}, profile='compiled')
        self.assertEqual(receipt['kind'], 'committed', receipt)
        config = self.c.config()
        config['objects'].append('peer')
        clerk.save(self.c.state / 'clerk.json', config)
        path = self.base / 'cards.sqlite'
        self.book = town_cards.CardBook.create(path, issuer_did=ISSUER, world_id='urn:test:preparation',
                                               runtime=history.runtime('compiled'))
        self.c.upgrade(self.c.profile()['sha256'], town_cards={'path': str(path.resolve()),
                      'issuers': [ISSUER], 'metadata': self.book.metadata()})
        self.operator = town.Town(self.c.state, request=self.pds)
        self.card = self.operator.capture('gallery', alias='gallery')
        self.parent = {'uri': f'at://{ISSUER}/{clerk.FEED}/gallery', 'cid': 'gallery-card-cid'}
        self.pds.records[self.parent['uri']] = (self.parent['cid'], {'$type': clerk.FEED, 'text': self.card['body']})
        self.operator.bind('gallery', self.parent['uri'], self.parent['cid'])

    def post(self, key, text, author=A):
        uri = f'at://{author}/{clerk.FEED}/{key}'
        self.pds.records[uri] = ('cid-' + key, {'$type': clerk.FEED, 'text': text,
                                               'reply': {'root': self.parent, 'parent': self.parent}})
        return uri, 'cid-' + key

    def test_normal_encounter_question_refusal_ready_and_original_retry(self):
        self.assertIn('prepareGesture', self.card['body'])
        self.assertEqual(self.card['card']['actions'][-1]['command'], 'prepareGesture')
        before = self.c.database.read_bytes()
        binary = Path(os.environ.get('DELVETALK_PREPARATION_BINARY', source_offers.BINARY))
        with patch.object(source_offers, 'BINARY', binary):
            question_source = self.post('question', 'delvetalk gallery prepareGesture')
            question = self.operator.receive(*question_source)
            self.assertEqual(question['status'], 'question')
            self.assertEqual(question['body'], 'Which gesture would you like?')
            self.assertEqual(question['preparation']['needs'], ['gesture'])
            self.assertNotIn('request', question['receipt'])
            self.assertEqual(self.c.database.read_bytes(), before)
            refusal = self.operator.receive(*self.post('refuse', 'delvetalk gallery prepareGesture\ngesture: refuse'))
            self.assertEqual(refusal['status'], 'refused')
            self.assertEqual(refusal['body'], 'Choose another gesture.')
            self.assertEqual(self.c.database.read_bytes(), before)
            denied = self.operator.receive(*self.post('denied', 'delvetalk gallery prepareGesture\ngesture: wave', B))
            self.assertEqual(denied['receipt']['reply']['kind'], 'refused')
            self.assertEqual(denied['receipt']['reply']['data'], 'unauthorized')
            ready = self.operator.receive(*self.post('ready', 'delvetalk gallery prepareGesture\ngesture: wave'))
            self.assertEqual(ready['receipt']['reply']['kind'], 'committed', ready)
            self.assertEqual(ready['receipt']['request']['principal'], A)
            self.assertEqual(clerk.world.snapshot(self.c.database)['objects']['peer']['state']['touched'], 'wave')
        after = self.c.database.read_bytes()
        self.pds.records.clear()
        with patch.object(source_offers, 'prepare', side_effect=AssertionError('no source reevaluation on retained reply')):
            self.assertEqual(self.operator.receive(*question_source), question)
            self.assertEqual(self.c.receive(*question_source), question['receipt'])
        self.assertEqual(self.c.database.read_bytes(), after)


if __name__ == '__main__':
    unittest.main()
