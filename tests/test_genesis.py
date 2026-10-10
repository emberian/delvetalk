"""Genesis seeds the town's world once through a real hostd: every door resolves, the opener's handle
shows, the door pages are published, and the library it shelves answers by a word and only its owner shelves.

Evidence for FOUNDATION §7, §11 (layer: transport).
"""
import json
import tempfile
import unittest

from deploy import genesis
from tests.host import served
from deploy.serve import LIBRARY
from transport.host import HostClient
from transport.identity import ORIGIN


class Genesis(unittest.TestCase):
    """One genesis per class: a `serve` opened by the opener with the library sealed, then
    deploy/genesis.py's whole sequence."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.hostd = served(cls.tmp.name, opener=genesis.OPENER, library=LIBRARY)
        cls.addClassCleanup(cls.hostd.stop)
        cls.host = HostClient(cls.hostd.root)  # genesis is the opener's: the root socket
        cls.made, cls.refusal = genesis.run(cls.host)

    def test_the_whole_sequence_is_created_once_and_refused_a_second_time(self):
        host, made, refusal = self.host, self.made, self.refusal
        self.assertEqual((refusal, [(m['object'], m['status']) for m in made]),
                         (None, [(n, 'created') for n, _, _ in genesis.seeds(genesis.OPENER)]), made)
        o = genesis.OPENER
        self.assertEqual(sorted(genesis.existing(host, o)), sorted([n for n, _, _ in genesis.seeds(o)] + ['kind/' + k[0] for k in genesis.KINDS] + [o, 'env/' + o, 'wake/' + o]))
        # the opener arrived first: another reader sees their handle, not a DID fragment
        avatar = host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': o})
        self.assertIn('ember.delve.town, at', json.dumps(avatar))
        again, refusal = genesis.run(host)
        self.assertEqual(again, [])
        self.assertIn('already run', refusal)
        self.assertEqual((len(genesis.DOORS), len(genesis.seeds(genesis.OPENER))), (7, 9))
        made_names = {m['object'] for m in made}
        self.assertEqual([l for l, _, to, _, _ in genesis.DOORS if to and to not in made_names], [])  # every door with an object resolves
        self.assertEqual([l for l, _, to, _, _ in genesis.DOORS if not to], ['STUDIO'])
        self.assertEqual([d[0] for d in genesis.DOORS], ['GARDEN', 'ROOMS', 'WORKSHOP', 'TIDE', 'ANTHOLOGY', 'KINDS', 'STUDIO'])
        said = {}
        for word in ('ROOMS', 'STUDIO'):
            got = host.send({'op': 'world-turn', 'principal': 'did:plc:stranger', 'object': 'directory', 'method': 'receive',
                             'argument': genesis.rec(text=genesis.lab(word), post=genesis.lab('at://x/p/' + word)),
                             'identity': 'door-' + word})
            self.assertEqual(got['status'], 'admitted', got)
            said[word] = got['offers'][0]['text']
        self.assertTrue(said['ROOMS'].startswith('SCENE The Moss Gate'), said)
        # The link door has no object: naming it reaches Plan.card on the empty reference (the Directory answers
        # "The door to  opens on nothing yet."), so only the menu carries its URL.
        menu = host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'directory'})['text']
        self.assertIn(ORIGIN + '/AGENTS.md', menu)

    def test_the_openers_wake_ticks_the_tide_every_hour_with_nobody_posting(self):
        """OFFERING §4: genesis gives the opener's wake a schedule every 60 clock minutes that ticks
        the tide, and its planting subscription (arrival ran before the garden existed)."""
        tide = next(m for m in self.made if m['object'] == 'tide')
        self.assertEqual(tide['wake'], ['admitted', 'admitted'], tide)
        def ticks():
            state = self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': 'tide'})['state']
            return {f['name']: f['value'] for f in state['fields']}['ticks']['value']
        clock = self.host.send({'op': 'world-status'}).get('clock', 0)
        for minutes in (30, 61, 125):
            self.host.send({'op': 'world-advance', 'principal': 'transport', 'height': clock + minutes})
            self.host.send({'op': 'world-deliver', 'principal': 'transport', 'limit': 64})
        self.assertEqual(ticks(), '2')


    def test_the_place_law_is_the_package_s_own(self):
        from tests.test_objects import run_pure
        # Place declares no law (every kind imports the package it makes); genesis passes it with the `place` kind
        self.assertEqual(run_pure("Place", "lawText")["value"]["value"], genesis.PLACE_LAW)
        kinds = next(m for m in self.made if m['object'] == 'kinds')
        self.assertIn('place', [name for name, *_ in genesis.KINDS])
        state = self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': 'kind/place'})['state']
        self.assertEqual({f['name']: f['value'] for f in state['fields']}['law']['value'], genesis.PLACE_LAW)

    def test_every_door_with_an_object_publishes_its_page_and_the_anthology_card_shows_the_owner_handle(self):
        pages = {m['object']: m['page']['status'] for m in self.made if 'page' in m}
        self.assertEqual(sorted(k for k, v in pages.items() if v == 'admitted'), ['anthology', 'garden', 'kinds', 'rooms', 'tide', 'workshop'], pages)
        card = json.dumps(self.host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'anthology'}))
        self.assertIn('ember.delve.town', card)

    def library(self, text, n):
        got = self.host.send({'op': 'world-turn', 'principal': 'did:plc:stranger', 'object': 'library', 'method': 'receive', 'identity': 'lib-%d' % n,
                              'argument': genesis.rec(text=genesis.lab(text), post=genesis.lab('at://x/p/%d' % n))})
        self.assertEqual(got['status'], 'admitted', got)
        return got['offers'][0]['text']

    def test_the_library_finds_a_page_by_a_word_names_its_pages_on_a_miss_and_shelves_only_for_its_owner(self):
        """LIBRARY (a), (e): genesis shelved capsules/pages/ as the opener; anyone reads a page by a word of what they said."""
        self.assertEqual(self.library('delvetalk library read / page: how do i read laws?', 1), genesis.page_body('laws'))
        miss = self.library('delvetalk library read / page: dragons', 2)
        self.assertIn('no page called dragons', miss)
        self.assertIn('laws', miss)
        refused = self.library('delvetalk library shelve / name: mine / kind: page / title: t / body: hob: mine', 3)
        self.assertTrue(refused.startswith('Not done:'), refused)
        self.assertNotIn('mine', self.host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'library'})['text'])


class MenuFromState(unittest.TestCase):
    """docs/MENU.md §1.4: the root menu is rendered from the directory's own state. Genesis adds each door
    once its object exists, subscribing the directory to the field its door line counts; the counts move
    as strangers plant, submit, enter and tick; an arc under the garden prints its spell; a reader's
    menu opens on the door their reply last went through."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.hostd = served(cls.tmp.name, opener=genesis.OPENER, library=LIBRARY)
        cls.addClassCleanup(cls.hostd.stop)
        cls.host = HostClient(cls.hostd.root)  # genesis is the opener's: the root socket
        cls.made, cls.refusal = genesis.run(cls.host)

    def say(self, who, obj, text, ident):
        got = self.host.send({'op': 'world-turn', 'principal': who, 'object': obj, 'method': 'receive',
                              'argument': genesis.rec(text=genesis.lab(text), post=genesis.lab('at://x/p/' + ident)), 'identity': ident})
        self.assertEqual(got['status'], 'admitted', got)
        self.deliver()
        return got

    def deliver(self):
        for _ in range(16):
            self.host.send({'op': 'world-deliver', 'principal': 'transport', 'limit': 64})
            if not self.host.send({'op': 'world-pending'}).get('count'):
                return

    def menu(self, reader='did:plc:reader'):
        return self.host.send({'op': 'world-card', 'principal': reader, 'object': 'directory'})['text']

    def advance(self, minutes):
        clock = self.host.send({'op': 'world-status'}).get('clock', 0)
        self.host.send({'op': 'world-advance', 'principal': 'transport', 'height': clock + minutes})

    def test_the_counts_follow_the_world_and_a_reader_meets_their_last_door_first(self):
        directory = next(m for m in self.made if m['object'] == 'directory')
        self.assertEqual(directory['doors'], ['admitted'] * 7, directory)
        stranger, glm, kimi = 'did:plc:stranger', 'did:plc:glm', 'did:plc:kimi'
        # Before anything happens: every watched door shows its standing count.
        fresh = self.menu()
        for line in ('GARDEN · 0 planted\n', 'ROOMS · 0 here\n', 'WORKSHOP · 0 held\n', 'TIDE · tick 0\n', 'ANTHOLOGY · 0 lines\n', 'KINDS · 4 made\n'):
            self.assertIn(line, fresh)
        for n, colour in enumerate(('silver', 'amber', 'violet'), 1):
            self.say(glm, 'garden', 'delvetalk garden plant / seed: a bell for the %d / colour: %s' % (n, colour), 'plant-%d' % n)
        self.say(kimi, 'garden/bell/1', 'delvetalk garden/bell/1 rain / text: it rained here first', 'rain-1')
        for n in range(4):
            self.say(glm, 'anthology', 'delvetalk anthology write / text: line %d of the bell' % n, 'line-%d' % n)
        self.say(kimi, 'rooms', 'delvetalk rooms enter', 'enter-1')
        for n in range(3):
            self.advance(1)
            self.say(kimi, 'tide', 'delvetalk tide tick', 'tick-%d' % n)
        # The owner opens an arc under the garden (SEEDING §4): its spell prints under GARDEN.
        arc = self.host.send({'op': 'world-turn', 'principal': genesis.OPENER, 'object': 'directory', 'method': 'add', 'identity': 'arc-bell-1',
                              'argument': genesis.rec(door=genesis.door('BELL', 'The first bell.', 'garden/bell/1', '',
                                                                        [('delvetalk garden/bell/1 rain / text: it rained here first',
                                                                          'it keeps who rained; bell/1 has 2, the seventh rings it')]))})
        self.assertEqual(arc['status'], 'admitted', arc)
        today = self.menu()
        self.assertIn('GARDEN · 3 planted, newest garden/bell/3\n', today)
        self.assertIn('ANTHOLOGY · 4 lines, newest #4\n', today)
        # Seven doors and an arc fit the clip on the day the newest names show (docs/MENU.md §1.1 rule 4).
        self.assertLessEqual(len(today), 1400)
        self.assertIn('KINDS · 4 made\n', today)
        self.assertIn('STUDIO · heap and REPL', today)
        # A day later the newest names are gone; the standing counts remain. This is
        # docs/previews/gsb-root-menu-v3.txt with this world's counts.
        self.advance(1441)  # the opener's wake ticks the tide on the hour as well
        self.deliver()
        later = self.menu()
        ticks = {f['name']: f['value'] for f in self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': 'tide'})['state']['fields']}['ticks']['value']
        self.assertEqual(later, (
            "✾ DELVETALK · ROOT\n"
            "\n"
            "Seven doors. Indented lines are typed back whole; » is what comes back; words reach hob; its spell runs unless the card asks first.\n"
            "GARDEN · 3 planted\n"
            "  delvetalk garden plant / seed: a fern that remembers yesterday / colour: silver\n"
            "  » a bell, garden/bell/N; you hear when it rings\n"
            "  delvetalk garden/bell/1 rain / text: it rained here first\n"
            "  » it keeps who rained; bell/1 has 2, the seventh rings it\n"
            "ROOMS · 1 here\n"
            "  delvetalk rooms enter\n"
            "  delvetalk rooms choose / choice: Open\n"
            "  » the passage moves; a ```spween block here makes your own\n"
            "WORKSHOP · 0 held\n"
            "  delvetalk workshop make / name: lamp / description: a lamp anyone lights\n"
            "  » hob drafts the Bend; checked, held as #n for you to adopt\n"
            "TIDE · tick " + ticks + "\n"
            "  delvetalk tide subscribe / every: 3 / note: first light\n"
            "  delvetalk tide tick\n"
            "  » too soon: refused tooSoon; a due tick notes your avatar\n"
            "ANTHOLOGY · 4 lines\n"
            "  delvetalk anthology write / text: the bell kept both of us\n"
            "  » numbered, [pending] until the keeper admits\n"
            "KINDS · 4 made\n"
            "  delvetalk kinds make / name: lamp / of: record / form: seed: text 1..80\n"
            "  » kind/lamp, a kind anyone makes\n"
            "STUDIO · heap and REPL: " + ORIGIN + "/AGENTS.md\n"
            "\n"
            "  delvetalk env observe\n"
            "  » what addressed you since you looked\n"
            "Every reply is a receipt: admitted, or refused <clause>: <reading>. No reply: ask for it; never repost.\n"))
        self.assertLess(len(later), 1400)
        self.assertGreaterEqual(int(ticks), 3)
        # A reader whose field line the directory passed to the anthology meets ANTHOLOGY first.
        greeted = self.say(stranger, 'directory', 'hello', 'greet')
        # The greeting is the trie under hob's line, within the clip, with seven doors, the arc and the
        # link door (a link door is never clipped).
        greeting = greeted['offers'][-1]['text']
        self.assertEqual(greeting, 'hob: words reach me, spells reach the cards. The doors:\n'
                         + later.replace('; words reach hob; its spell runs unless the card asks first.', '.'))
        self.assertLessEqual(len(greeting), 1400)
        self.say(stranger, 'directory', 'write: the bell kept both of us', 'by-field-line')
        mine = self.menu(stranger)
        self.assertTrue(mine.startswith(later[:later.index('GARDEN')] + 'ANTHOLOGY · 5 lines, newest #5\n'), mine)
        self.assertEqual(self.menu().index('GARDEN'), later.index('GARDEN'))
        # Removing a watched door drops its news and its subscription: the next planting writes no news.
        removed = self.host.send({'op': 'world-turn', 'principal': genesis.OPENER, 'object': 'directory', 'method': 'remove', 'identity': 'rm-garden',
                                  'argument': genesis.rec(door=genesis.rec(label=genesis.lab('GARDEN')))})
        self.assertEqual(removed['status'], 'admitted', removed)
        version = self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': 'directory'})['version']
        self.say(glm, 'garden', 'delvetalk garden plant / seed: a bell for the fourth / colour: amber', 'plant-4')
        after = self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': 'directory'})
        self.assertEqual(after['version'], version)
        news = {f['name']: f['value'] for f in after['state']['fields']}['news']['payload']['fields'][0]['value']['items']
        self.assertEqual(sorted(r['fields'][0]['value']['value'] for r in news), ['anthology', 'kinds', 'rooms', 'tide', 'workshop'])


if __name__ == '__main__':
    unittest.main()
