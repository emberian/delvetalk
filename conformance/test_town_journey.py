#!/usr/bin/env python3
"""Posts-only rehearsal: two authors, refreshed cards and governed view revision.

All publications are records in an in-memory fake PDS. The receiving transport,
installed garden protocol, pure views and admission engine are the real paths.
"""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import town_cards

fixture = clerk.module('town_journey_pds', 'conformance/test_clerk.py')
garden = clerk.module('town_journey_garden', 'protocols/town-garden/generate.py')
room = clerk.module('town_journey_room', 'scene/room.py')
history = clerk.module('town_journey_history', 'scripts/history.py')
A, B = fixture.A, fixture.B
ISSUER = 'did:plc:cccccccccccccccccccccccc'
SEED = 'A bell for lost moths'
RAIN = 'Rain carries the names of forgotten stars.'


class TownJourneyTests(unittest.TestCase):
    runtime_profile = 'world'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.pds = fixture.FakePDS()
        self.clerk = clerk.Clerk(self.base / 'clerk', self.pds)
        protocol = clerk.loads((ROOT / 'protocols/town-garden/protocol.json').read_bytes())
        self.law = garden.law([A, B], [A])
        seeded = self.clerk.bootstrap('garden', protocol, self.law, [A, B],
                                      runtime_profile=self.runtime_profile)
        self.assertEqual(seeded['kind'], 'committed', seeded)
        self.initial = seeded['data']['root']
        self.book = town_cards.CardBook.create(self.base / 'book', issuer_did=ISSUER,
            world_id='urn:test:posts-only-garden', runtime=history.runtime(self.runtime_profile),
            display_names={A: '@moss', B: '@iris'})
        self.clerk.upgrade(self.clerk.profile()['sha256'], town_cards={
            'path': str(self.book.path), 'issuers': [ISSUER], 'metadata': self.book.metadata()})

    def feed(self, author, key, text, parent=None):
        reference = {'uri': f'at://{author}/{clerk.FEED}/{key}', 'cid': 'cid-' + key}
        value = {'$type': clerk.FEED, 'text': text, 'createdAt': '2026-10-08T00:00:00Z'}
        if parent is not None:
            value['reply'] = {'root': getattr(self, 'welcome', parent), 'parent': parent}
        self.pds.records[reference['uri']] = (reference['cid'], value)
        return reference

    def fetch_publication(self, uri, cid):
        author, _, _ = clerk.parse_uri(uri, (clerk.FEED,))
        self.clerk.verify_repository(author)
        return self.clerk.fetch_record(uri, cid, (clerk.FEED,))

    def publish_fixture(self, key, body, cards, parent=None):
        """A test fixture stands in for explicit publication, then verifies binding."""
        self.assertNotIn('http://', body)
        self.assertNotIn('https://', body)
        reference = self.feed(ISSUER, key, body + '\n🜉✾', parent)
        for card in cards:
            self.book.bind(card['alias'], reference, self.fetch_publication)
        return reference

    def act(self, author, key, card, parent, command, fields):
        action = next(item for item in card['card']['actions'] if item['command'] == command)
        self.assertTrue(action['available'])
        selector = town_cards.action_word(action, card['card']['actions'])
        text = town_cards.spell(card['alias'], action, fields, selector=selector)
        self.assertIn(f'delvetalk {card["alias"]} {selector}\n', card['body'])
        self.assertEqual(town_cards.parse_reply(text)['syntax'], 'delvetalk-town-spell-v1')
        source = self.feed(author, key, text, parent)
        receipt = self.clerk.receive(source['uri'], source['cid'])
        self.assertEqual(self.clerk.execution_profile(receipt['request']), self.runtime_profile)
        return source, receipt

    def outcome(self, receipt, key, parent, root):
        """Freshness is an explicit caller observation, never a resolver substitution."""
        view = room.inspect_object(root, 'garden')
        self.assertEqual(view['mode'], 'projection')
        draft = self.book.prepare_outcome(receipt['reply'], [view])
        self.assertEqual(len(draft['cards']), 1)
        card = draft['cards'][0]
        self.assertEqual(card['view']['root'], root)
        self.assertEqual(len(card['panels']), 6)
        self.assertTrue(all(panel['view']['root'] == root for panel in card['panels']))
        # Preparation alone has not fabricated a publication binding.
        with self.assertRaisesRegex(ValueError, 'publication'):
            self.book.publication(card['alias'])
        source = self.publish_fixture(key, draft['body'], [card], parent)
        return draft, card, source

    def program(self, author, key, protocol, root, parent):
        payload = {'op': 'reprogram', 'object': 'garden', 'expected': root,
                   'protocol': protocol, 'state': root['state']}
        text = 'delvetalk-request v1\n```delvetalk-request\n' + clerk.world.wire_dumps(payload) + '\n```'
        source = self.feed(author, key, text, parent)
        receipt = self.clerk.receive(source['uri'], source['cid'])
        self.assertEqual(self.clerk.execution_profile(receipt['request']), self.runtime_profile)
        return source, receipt

    def test_two_authors_fresh_posts_retries_and_authorized_installed_view_revision(self):
        welcome_card = self.book.capture(room.inspect_object(self.initial, 'garden'), 'garden')
        self.welcome = self.publish_fixture('welcome', 'Welcome to the Night Garden.\n' + welcome_card['body'], [welcome_card])
        self.assertEqual([a['command'] for a in welcome_card['card']['actions']], ['plant'])
        self.assertIn('soil', welcome_card['body'])
        self.assertEqual(len(welcome_card['panels']), 6)

        planted_source, planted = self.act(A, 'moss-plants', welcome_card, self.welcome, 'plant',
                                          {'seed': SEED, 'colour': 'amber'})
        self.assertEqual(planted['reply']['kind'], 'committed', planted)
        planted_root = planted['reply']['data']['root']
        self.assertEqual(planted_root['state']['planter'], A)
        plant_draft, rain_card, rain_post = self.outcome(planted, 'plant-outcome', planted_source, planted_root)
        self.assertIn('committed', plant_draft['body'])
        self.assertIn(SEED, rain_card['body'])
        self.assertIn('@moss', rain_card['body'])
        self.assertEqual([a['command'] for a in rain_card['card']['actions']], ['rain'])

        competitor_source, competitor = self.act(B, 'iris-old-soil', welcome_card, self.welcome, 'plant',
                                                  {'seed': 'A competing silver ladder', 'colour': 'silver'})
        self.assertEqual(competitor['reply']['data'], 'stale read root')
        stale_draft = self.book.prepare_outcome(competitor['reply'])
        self.assertIn('refused', stale_draft['body'])
        self.assertIn('stale read root', stale_draft['body'])
        self.assertEqual(stale_draft['cards'], [])
        self.publish_fixture('stale-outcome', stale_draft['body'], [], competitor_source)
        self.assertEqual(self.clerk.snapshot('garden')['root'], planted_root)

        _, same_author = self.act(A, 'moss-self-rain', rain_card, rain_post, 'rain', {'line': 'One voice tries both roles.'})
        self.assertEqual(same_author['reply']['kind'], 'refused')
        rained_source, rained = self.act(B, 'iris-rains', rain_card, rain_post, 'rain', {'line': RAIN})
        self.assertEqual(rained['reply']['kind'], 'committed', rained)
        blooming_root = rained['reply']['data']['root']
        self.assertEqual(blooming_root['state']['lastCompleted'], {
            'seed': SEED, 'colour': 'amber', 'planter': A, 'rain': RAIN, 'rainmaker': B})
        _, bloom_card, bloom_post = self.outcome(rained, 'rain-outcome', rained_source, blooming_root)
        panels = {panel['id']: panel['view']['data']['prose'] for panel in bloom_card['panels']}
        self.assertIn('AMBER', panels['image'])
        self.assertEqual(panels['seed'], SEED)
        self.assertEqual(panels['rain'], RAIN)
        self.assertEqual(panels['planter'], A)
        self.assertEqual(panels['rainmaker'], B)
        self.assertIn('@moss', bloom_card['body'])
        self.assertIn('@iris', bloom_card['body'])
        self.assertEqual([a['command'] for a in bloom_card['card']['actions']], ['plant'])

        # Old URI/CID retries remain historical after later turns and a restart.
        calls = len(self.pds.calls)
        records = self.pds.records
        self.pds.records = {}
        restarted = clerk.Clerk(self.clerk.state, self.pds)
        self.assertEqual(restarted.receive(planted_source['uri'], planted_source['cid']), planted)
        self.assertEqual(restarted.receive(competitor_source['uri'], competitor_source['cid']), competitor)
        self.assertEqual(len(self.pds.calls), calls)
        self.pds.records = records
        self.assertEqual(self.clerk.snapshot('garden')['root'], blooming_root)

        successor = copy.deepcopy(blooming_root['protocol'])
        # Ordinary installed source changes only the main projection's title;
        # panel branches, action descriptors and all admitted contributions stay.
        result_fields = successor['viewProgram']['term'][1][1][1]
        self.assertEqual(result_fields[0][0], 'title')
        result_fields[0][1] = ['label', 'The Night Garden · a sign made together']
        _, forbidden = self.program(B, 'iris-program-proposal', successor, blooming_root, bloom_post)
        self.assertEqual(forbidden['reply']['data'], 'unauthorized')
        programmed_source, programmed = self.program(A, 'moss-installs-sign', successor, blooming_root, bloom_post)
        self.assertEqual(programmed['reply']['kind'], 'committed', programmed)
        changed_root = programmed['reply']['data']['root']
        self.assertEqual(changed_root['state'], blooming_root['state'])
        self.assertEqual(changed_root['law'], self.law)
        self.assertEqual(changed_root['version'], blooming_root['version'] + 1)
        _, revised_card, revised_post = self.outcome(programmed, 'program-outcome', programmed_source, changed_root)
        self.assertEqual(revised_card['card']['title'], 'The Night Garden · a sign made together')
        self.assertIn(SEED, revised_card['body'])
        self.assertIn(RAIN, revised_card['body'])
        self.assertIn('AMBER', revised_card['body'])
        self.assertEqual(revised_card['card']['prose'], RAIN)
        self.assertNotEqual(revised_card['alias'], bloom_card['alias'])
        self.assertEqual(town_cards.CardBook(self.book.path).card(bloom_card['alias']), bloom_card)

        _, next_season = self.act(B, 'iris-next-season', revised_card, revised_post, 'plant',
                                 {'seed': 'A quiet violet staircase', 'colour': 'violet'})
        self.assertEqual(next_season['reply']['kind'], 'committed')
        self.assertEqual(next_season['reply']['data']['root']['state']['lastCompleted'],
                         blooming_root['state']['lastCompleted'])
        self.assertEqual(self.clerk.receive(programmed_source['uri'], programmed_source['cid']), programmed)
        self.assertTrue(all(method == 'GET' and base == clerk.PDS for method, base, _, _ in self.pds.calls))
        self.assertTrue(all(nsid in ('com.atproto.repo.describeRepo', 'com.atproto.repo.getRecord')
                            for _, _, nsid, _ in self.pds.calls))


class CompiledTownJourneyTests(TownJourneyTests):
    runtime_profile = 'compiled'


if __name__ == '__main__':
    unittest.main()
