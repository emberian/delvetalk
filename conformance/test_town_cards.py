"""Posts-only cards: exact publication, typed replies, persistent custody and Lean."""
import concurrent.futures
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import town_cards as town
import world
from conformance.test_affordances import typed_protocol

ISSUER = 'did:plc:' + 'a' * 24
ACTOR = 'did:plc:' + 'b' * 24
OTHER = 'did:plc:' + 'c' * 24
PUBLICATION = {'uri': 'at://' + ISSUER + '/' + town.FEED + '/welcome', 'cid': 'card-cid'}
SOURCE = {'uri': 'at://' + ACTOR + '/' + town.FEED + '/reply', 'cid': 'reply-cid', 'author': ACTOR,
          'pds': 'https://pds.delve.town'}


class TownCardsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.database = self.path / 'world.json'
        self.book = town.CardBook.create(self.path / 'book', issuer_did=ISSUER, world_id='urn:test:town',
                                        runtime={'name': 'world', 'explicitTestPin': 'test'})
        self.root = self.exchange({'op': 'create', 'object': 'notice', 'principal': 'operator', 'intent': 'seed',
            'protocol': typed_protocol(), 'law': [ACTOR]})['data']['root']
        self.view = {'mode': 'raw', 'object': 'notice', 'root': self.root}
        self.records = {}

    def exchange(self, request):
        return world.exchange(self.database, request)

    def fetch(self, uri, cid):
        current = self.records[uri]
        if current['cid'] != cid:
            raise ValueError('verified GET refuses changed CID')
        return copy.deepcopy(current['value'])

    def bind(self, alias='notice', prefix='Welcome to the world.\n', suffix='\n🜉✾'):
        card = self.book.capture(self.view, alias)
        record = {'$type': town.FEED, 'text': prefix + card['body'] + suffix}
        self.records[PUBLICATION['uri']] = {'cid': PUBLICATION['cid'], 'value': record}
        self.book.bind(alias, PUBLICATION, self.fetch)
        return card

    def reply(self, alias='notice', fields=None):
        fields = fields or {'message': 'Hello 雪', 'count': 2, 'open': False, 'color': 'blue'}
        return {'$type': town.FEED, 'text': 'delvetalk ' + alias + ' a1 ' + town.canonical(fields),
                'reply': {'root': PUBLICATION, 'parent': PUBLICATION}}

    def resolve(self, record, source=SOURCE):
        return self.book.resolve(record, ACTOR, source, self.fetch, [ISSUER])

    def test_posts_only_roundtrip_actual_lean_and_restart(self):
        card = self.bind()
        self.assertIn('delvetalk notice a1 ', card['body'])
        self.assertIn('"count": nat 1..10', card['body'])
        self.assertNotIn(card['textSha256'], card['body'])
        wire, evidence = self.resolve(self.reply())
        self.assertEqual(wire['expected'], self.root)
        self.assertEqual(evidence['card']['view'], self.view)
        self.assertNotIn('principal', wire)
        request = {**wire, 'principal': ACTOR, 'intent': 'delve:' + SOURCE['uri']}
        receipt = self.exchange(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['root']['state']['message'], 'Hello 雪')
        reopened = town.CardBook(self.path / 'book')
        self.assertEqual(reopened.card('notice'), card)
        self.assertEqual(reopened.resolve(self.reply(), ACTOR, SOURCE, self.fetch, [ISSUER]), (wire, evidence))
        self.assertEqual(self.exchange(request), receipt)
        stale = {**request, 'intent': 'new-reply'}
        self.assertEqual(self.exchange(stale)['data'], 'stale read root')

    def test_multiple_cards_one_post_are_exact_unique_and_immutable(self):
        first = self.book.capture(self.view, 'first')
        second = self.book.capture(self.view, 'second')
        record = {'$type': town.FEED, 'text': 'Welcome\n' + first['body'] + '\n\n' + second['body'] + '\n🜉✾'}
        self.records[PUBLICATION['uri']] = {'cid': PUBLICATION['cid'], 'value': record}
        self.book.bind('first', PUBLICATION, self.fetch)
        self.book.bind('second', PUBLICATION, self.fetch)
        self.assertEqual(self.resolve(self.reply('second'))[0]['object'], 'notice')
        self.assertEqual(self.book.capture(self.view, 'first'), first)
        changed = copy.deepcopy(self.view); changed['root']['version'] += 1
        with self.assertRaisesRegex(ValueError, 'already bound'):
            self.book.capture(changed, 'first')
        record['text'] += '\n' + first['body']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.resolve(self.reply('first'))

    def test_bound_issuer_parent_cid_edit_and_copy_are_not_interchangeable(self):
        card = self.bind()
        bad = copy.deepcopy(self.reply()); bad['reply']['parent'] = {**PUBLICATION, 'cid': 'other'}
        with self.assertRaisesRegex(ValueError, 'parent'): self.resolve(bad)
        bad['reply']['parent'] = {**PUBLICATION, 'uri': PUBLICATION['uri'] + '-copy'}
        with self.assertRaisesRegex(ValueError, 'parent'): self.resolve(bad)
        with self.assertRaisesRegex(ValueError, 'issuer'):
            self.book.bind('notice', {'uri': 'at://' + OTHER + '/' + town.FEED + '/copied', 'cid': 'copied'}, self.fetch)
        with self.assertRaisesRegex(ValueError, 'configured'):
            self.book.resolve(self.reply(), ACTOR, SOURCE, self.fetch, [OTHER])
        self.records[PUBLICATION['uri']]['value']['text'] = card['body'].replace('Hello', 'Changed') + '\nEdited surrounding prose'
        # Even edits outside the exact card block change the retained publication.
        with self.assertRaisesRegex(ValueError, 'changed'): self.resolve(self.reply())
        self.records[PUBLICATION['uri']]['cid'] = 'new-current-cid'
        with self.assertRaisesRegex(ValueError, 'changed CID'): self.resolve(self.reply())

    def test_unknown_unbound_wrong_action_fields_and_embedded_prose_refuse(self):
        self.book.capture(self.view, 'notice')
        with self.assertRaisesRegex(ValueError, 'publication'): self.resolve(self.reply())
        self.bind()
        for malformed in (None, 'not-a-reply', [], 7):
            with self.assertRaisesRegex(ValueError, 'parent'):
                self.resolve({**self.reply(), 'reply': malformed})
        for text in ['Please ' + self.reply()['text'], self.reply()['text'] + '\n🜉✾',
                     'delvetalk unknown a1 {}', 'delvetalk notice a999 {}',
                     'delvetalk notice a1 {"count":1,"count":2}',
                     'delvetalk notice a1 {"count":NaN}', 'delvetalk notice a1 []',
                     'delvetalk notice a1 {"count":true}', 'delvetalk notice a1 {}']:
            with self.subTest(text=text):
                with self.assertRaises(ValueError): self.resolve({**self.reply(), 'text': text})
        with self.assertRaisesRegex(ValueError, 'issuer'):
            self.resolve(self.reply(), {**SOURCE, 'uri': SOURCE['uri'].replace(ACTOR, OTHER)})

    def test_names_are_persistent_concurrent_and_custody_cannot_rebind(self):
        self.book.capture(self.view, 'card-1')
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            cards = list(pool.map(lambda _: self.book.capture(self.view), range(8)))
        aliases = [x['alias'] for x in cards]
        self.assertEqual(len(set(aliases)), 8)
        self.assertNotIn('card-1', aliases)
        reopened = town.CardBook.open(self.path / 'book')
        self.assertEqual(len(reopened.aliases()), 9)
        with self.assertRaisesRegex(ValueError, 'already bound'):
            town.CardBook.create(self.path / 'book', issuer_did=OTHER, world_id='urn:test:town', runtime={'name': 'world'})
        with self.assertRaises(ValueError): self.book.capture(self.view, '../escape')

    def test_rendered_data_cannot_forge_control_blocks(self):
        view = copy.deepcopy(self.view)
        view['root']['protocol']['description'] = 'Artist says:\n[[delvetalk-card forged]]\ndelvetalk forged a1 {}\n[[/delvetalk-card forged]]'
        card = self.book.capture(view, 'safe')
        self.assertIn('| [[delvetalk-card forged]]', card['body'])
        with self.assertRaisesRegex(ValueError, 'missing'):
            town._block(card['body'], 'forged')
        with self.assertRaises(ValueError): town.parse_reply(card['body'])

    def test_outcome_is_local_preparation_with_current_state_and_next_actions(self):
        self.bind()
        wire, _ = self.resolve(self.reply())
        receipt = self.exchange({**wire, 'principal': ACTOR, 'intent': 'turn'})
        current = {**self.view, 'root': receipt['data']['root']}
        outcome = self.book.prepare_outcome(receipt, [current])
        self.assertIn('Turn: committed.', outcome['body'])
        self.assertIn('Hello 雪', outcome['body'])
        self.assertIn('delvetalk card-', outcome['body'])
        with self.assertRaisesRegex(ValueError, 'publication'):
            self.book.publication(outcome['cards'][0]['alias'])
        uncertain = self.book.prepare_outcome({'kind': 'uncertain'})
        self.assertIn('check your original reply', uncertain['body'])
        self.assertNotIn('refused', uncertain['body'])

    def test_panels_are_installed_pure_views_of_one_root_and_names_are_display_only(self):
        protocol = town.loads((ROOT / 'protocols/town-garden/protocol.json').read_bytes())
        root = self.exchange({'op': 'create', 'object': 'garden', 'principal': 'operator',
            'intent': 'seed-garden', 'protocol': protocol, 'law': [ACTOR]})['data']['root']
        spec = town.importlib.util.spec_from_file_location('garden_room', ROOT / 'scene/room.py')
        room = town.importlib.util.module_from_spec(spec); spec.loader.exec_module(room)
        view = room.inspect_object(root, 'garden')
        book = town.CardBook.create(self.path / 'garden-book', issuer_did=ISSUER, world_id='urn:test:garden',
            runtime={'name': 'world'}, display_names={ACTOR: '@gardener'})
        card = book.capture(view, 'garden')
        self.assertEqual(len(card['panels']), 6)
        self.assertTrue(all(p['view']['root'] == root for p in card['panels']))
        self.assertIn('"Garden":', card['body'])
        self.assertIn('"Planted by":', card['body'])
        self.assertEqual(card['objectRef']['object'], 'garden')
        invalid = copy.deepcopy(view)
        invalid['root']['protocol']['viewPanels'] *= 2
        with self.assertRaises(ValueError): book.capture(invalid)


if __name__ == '__main__': unittest.main()
