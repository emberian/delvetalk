"""Genesis seeds the town's world once through a real `serve`: every door resolves, the opener's handle
shows, the door pages are published, and the library it shelves answers by a word and only its owner shelves.

Evidence for FOUNDATION §7, §11 (layer: transport).
"""
import json
import tempfile
import unittest

from deploy import genesis
from tests.town import Town
from tests.wire import label, nat, record
from transport.identity import ORIGIN


class Genesis(unittest.TestCase):
    """One genesis per class: a `serve` opened by the opener with the library sealed, then
    deploy/genesis.py's whole sequence."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name)
        cls.addClassCleanup(cls.town.close)
        cls.host = cls.town.client  # genesis is the opener's: the root socket
        cls.made, cls.refusal = cls.town.made, cls.town.refusal

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
        self.assertEqual((len(genesis.DOORS), len(genesis.seeds(genesis.OPENER))), (6, 9))
        made_names = {m['object'] for m in made}
        self.assertEqual([l for l, to, _ in genesis.DOORS if to not in made_names], [])  # every door with an object resolves
        self.assertEqual([d[0] for d in genesis.DOORS] + [genesis.STUDIO[0]], ['GARDEN', 'ROOMS', 'WORKSHOP', 'TIDE', 'ANTHOLOGY', 'KINDS', 'STUDIO'])
        self.assertEqual([(m['object'], m['body']) for m in made if 'body' in m], [('commonplace', 'admitted'), ('rooms', 'admitted')])
        said = {}
        for word in ('ROOMS', 'STUDIO'):
            got = host.send({'op': 'world-turn', 'principal': 'did:plc:stranger', 'object': 'commonplace', 'method': 'receive',
                             'argument': record(text=label(word), post=label('at://x/p/' + word)),
                             'identity': 'door-' + word})
            self.assertEqual(got['status'], 'admitted', got)
            said[word] = got['offers'][0]['text']
        self.assertTrue(said['ROOMS'].startswith('The Moss Gate (0 here). Enter: delvetalk rooms enter.'), said)
        # The link door has no object: naming it answers its description.
        self.assertEqual(said['STUDIO'], 'STUDIO\nheap and REPL: ' + ORIGIN + '/AGENTS.md\n')
        menu = host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'commonplace'})['text']
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


    def test_the_room_kind_carries_the_record_law_and_the_rooms_body(self):
        from tests.test_objects import run_pure
        # Record declares no law (every kind imports the package it makes); genesis passes it with each record kind
        self.assertEqual(run_pure("Record", "lawText")["value"]["value"], genesis.RECORD_LAW)
        self.assertIn('room', [name for name, *_ in genesis.KINDS])
        state = {f['name']: f['value'] for f in self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': 'kind/room'})['state']['fields']}
        self.assertEqual((state['law']['value'], state['body']['value']), (genesis.RECORD_LAW, genesis.body_of('room')))
        rooms = next(m for m in self.made if m['object'] == 'rooms')
        self.assertEqual(rooms['body'], 'admitted')

    def test_every_door_with_an_object_publishes_its_page_and_the_anthology_card_shows_the_owner_handle(self):
        pages = {m['object']: m['page']['status'] for m in self.made if 'page' in m}
        self.assertEqual(sorted(k for k, v in pages.items() if v == 'admitted'), ['anthology', 'garden', 'kinds', 'rooms', 'tide', 'workshop'], pages)
        card = json.dumps(self.host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'anthology'}))
        self.assertIn('ember.delve.town', card)

    def library(self, text, n):
        got = self.host.send({'op': 'world-turn', 'principal': 'did:plc:stranger', 'object': 'library', 'method': 'receive', 'identity': 'lib-%d' % n,
                              'argument': record(text=label(text), post=label('at://x/p/%d' % n))})
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


class Commonplace(unittest.TestCase):
    """docs/METAPHYSICS.md §5, §7.5: the town's first card is the commonplace, a record the opener keeps. Its
    card says what changed in the town, newest first (World.changed, read when asked: nothing is kept to say
    it), each `<id> v<n> by <handle>, entry N`, then the first spells, then the doors the hand named, each
    with the spells it prints. A principal's first words get hob's greeting over it, opening on the door
    the words went through; the owner hangs an arc under a door with `door` and gives it a spell with
    `example`."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name)
        cls.addClassCleanup(cls.town.close)
        cls.host = cls.town.client  # genesis is the opener's: the root socket
        cls.made, cls.refusal = cls.town.made, cls.town.refusal

    def say(self, who, obj, text, ident):
        got = self.host.send({'op': 'world-turn', 'principal': who, 'object': obj, 'method': 'receive',
                              'argument': record(text=label(text), post=label('at://x/p/' + ident)), 'identity': ident})
        self.assertEqual(got['status'], 'admitted', got)
        self.deliver()
        return got

    def deliver(self):
        for _ in range(16):
            self.host.send({'op': 'world-deliver', 'principal': 'transport', 'limit': 64})
            if not self.host.send({'op': 'world-pending'}).get('count'):
                return

    def owner(self, method, ident, **fields):
        got = self.host.send({'op': 'world-turn', 'principal': genesis.OPENER, 'object': 'commonplace', 'method': method,
                              'identity': ident, 'argument': record(**{k: label(v) for k, v in fields.items()})})
        self.assertEqual(got['status'], 'admitted', got)
        return got

    def test_what_changed_leads_and_the_doors_follow_within_the_clip(self):
        stranger, glm, kimi = 'did:plc:stranger', 'did:plc:glm', 'did:plc:kimi'
        card = self.host.send({'op': 'world-card', 'principal': stranger, 'object': 'commonplace'})['text']
        self.assertTrue(card.startswith('✾ DELVETALK · THE COMMONPLACE\n\nSeven doors.'), card)
        self.assertIn('  delvetalk commonplace since / entry: 0\n', card)
        self.assertIn('ROOMS\n  delvetalk rooms enter\n', card)
        for n, colour in enumerate(('silver', 'amber'), 1):
            self.say(glm, 'garden', 'delvetalk garden plant / seed: a bell for the %d / colour: %s' % (n, colour), 'plant-%d' % n)
        rain = self.say(kimi, 'garden/bell/1', 'delvetalk garden/bell/1 rain / text: it rained here first', 'rain-1')
        # The owner opens an arc under the garden (SEEDING §4): its spell prints under GARDEN.
        self.owner('door', 'arc-door', label='BELL', to='garden/bell/1')
        self.owner('example', 'arc-spell', label='BELL', spell='delvetalk garden/bell/1 rain / text: it rained here first',
                   comes='it keeps who rained; bell/1 has 2, the seventh rings it')
        blank = self.say(stranger, 'commonplace', '', 'blank')['offers'][-1]['text']
        self.assertLessEqual(len(blank), 1400, blank)
        changed = blank[blank.index('What changed, newest first:\n'):].split('\n')[1:9]
        self.assertEqual(changed[0], 'garden/bell/1 v%s by kimi, entry %d' % (changed[0].split(' v')[1].split(' ')[0], rain['receipt']['height']), changed)
        self.assertTrue(all(' by ' in c and ', entry ' in c for c in changed), changed)
        self.assertNotIn('commonplace v', blank)  # its own greetings and doors are not news
        self.assertIn('  delvetalk kinds make / name: lamp / of: record\n  » kind/lamp, a kind anyone makes\n  delvetalk garden/bell/1 ?\n', blank)
        self.assertIn('GARDEN\n  delvetalk garden plant / seed: a fern that remembers yesterday / colour: silver\n'
                      '  » a bell, garden/bell/N; you hear when it rings\n'
                      '  delvetalk garden/bell/1 rain / text: it rained here first\n'
                      '  » it keeps who rained; bell/1 has 2, the seventh rings it\n', blank)
        self.assertIn('STUDIO · heap and REPL: ' + ORIGIN + '/AGENTS.md\n', blank)  # a link door is never clipped
        self.assertTrue(blank.endswith('Every reply is a receipt: admitted, or refused <clause>: <reading>. No reply: ask for it; never repost.\n'), blank)
        # since an entry: only what changed after it
        since = self.host.send({'op': 'world-turn', 'principal': stranger, 'object': 'commonplace', 'method': 'since', 'identity': 'since',
                                'argument': record(entry=nat(rain['receipt']['height'] - 1))})
        self.assertEqual(since['offers'][-1]['text'].split('What changed, newest first:\n')[1].split('\n')[0].split(' v')[0], 'garden/bell/1')
        self.assertEqual(since['offers'][-1]['text'].split('What changed, newest first:\n')[1].split('\n')[1], '  delvetalk kinds make / name: lamp / of: record')
        # A stranger hangs no door.
        refused = self.host.send({'op': 'world-turn', 'principal': stranger, 'object': 'commonplace', 'method': 'door', 'identity': 'stranger-door',
                                  'argument': record(label=label('MINE'), to=label('garden'))})
        self.assertEqual(refused['result']['label'], 'refused', refused)

    def test_first_words_get_hobs_greeting_once_and_a_field_line_goes_to_its_door(self):
        reader = 'did:plc:newcomer'
        greeting = self.say(reader, 'commonplace', 'hello', 'hello')['offers'][-1]['text']
        self.assertTrue(greeting.startswith('hob: words reach me, spells reach the cards. The doors:\n✾ DELVETALK · THE COMMONPLACE\n\n'), greeting)
        self.assertIn('What changed, newest first:\n', greeting)
        self.assertLessEqual(len(greeting), 1400)
        again = self.say(reader, 'commonplace', 'hello', 'again')
        self.assertFalse(any(o['text'].startswith('hob: words reach me') for o in again.get('offers') or []), again)
        # A field line naming a door's action goes to that door, whose card answers.
        passed = self.say(reader, 'commonplace', 'choose: Open', 'by-field-line')
        self.assertEqual(passed['result']['label'], 'passed', passed)
        self.assertTrue(passed['offers'][-1]['text'].startswith('The Moss Gate (0 here).'), passed)


if __name__ == '__main__':
    unittest.main()
