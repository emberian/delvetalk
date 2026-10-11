"""Genesis seeds the town's world once through a real `serve`: every door resolves, the opener's handle
shows, the door pages are published, and the library it shelves answers by a word and only its owner shelves.

Evidence for FOUNDATION §7, §11 (layer: transport).
"""
import json
import re
import tempfile
import unittest

from deploy import genesis
from tests.town import Town
from tests.wire import cast_refusal, label, nat, record, result_label
from transport.config import ORIGIN


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

    def view(self, obj):
        got = self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': obj})
        self.assertEqual(got['status'], 'viewed', got)
        return {f['name']: f['value'] for f in got['state']['fields']}

    def test_the_whole_sequence_is_created_once_and_refused_a_second_time(self):
        host, made, refusal = self.host, self.made, self.refusal
        hands = [dict(fields)['id'] for _, fields in genesis.HANDS]
        # world-create seeds the first objects; the hand's things are then admitted by spell on their kinds, and the garden's weather door after
        self.assertEqual((refusal, [(m['object'], m['status']) for m in made]),
                         (None, [(n, 'created') for n, _, _ in genesis.seeds(genesis.OPENER)] + [(id, 'admitted') for id in hands] + [('garden', 'admitted'), ('porch', 'admitted')]
                          + [(t, 'created') for t, _ in genesis.THINGS]), made)
        o = genesis.OPENER
        self.assertEqual(sorted(genesis.existing(host, o)), sorted([n for n, _, _ in genesis.seeds(o)] + ['kind/' + k[0] for k in genesis.KINDS] + hands + [t for t, _ in genesis.THINGS] + [o, 'env/' + o, 'wake/' + o]))
        # the porch's unclaimed things lie on it, each laid by the opener
        self.assertEqual([m.get('laid') for m in made if m['module'] == 'Thing'], ['admitted'] * len(genesis.THINGS))
        # each hand's thing is a record of its kind whose maker is the opener, who alone named its id
        for id, (kind, _) in zip(hands, genesis.HANDS):
            thing = self.view(id)
            self.assertEqual((thing['kind']['value'], thing['maker']['value'], thing['owner']['value']), (kind, o, o), id)
        # the opener arrived first: another reader sees their handle, not a DID fragment
        avatar = host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': o})
        self.assertIn("ember.delve.town's avatar, nowhere yet", json.dumps(avatar))
        again, refusal = genesis.run(host)
        self.assertEqual(again, [])
        self.assertIn('already run', refusal)
        self.assertEqual((len(genesis.DOORS), len(genesis.seeds(genesis.OPENER))), (7, 7))
        ids = set(genesis.existing(host, o))
        self.assertEqual([l for l, to, _ in genesis.DOORS if to not in ids], [])  # every door with an object resolves
        self.assertEqual([d[0] for d in genesis.DOORS] + [genesis.STUDIO[0]], ['KINDS', 'WORKSHOP', 'GARDEN', 'ROOMS', 'TIDE', 'PORCH', 'ANTHOLOGY', 'STUDIO'])
        self.assertEqual([(m['object'], m['body']) for m in made if 'body' in m], [('commonplace', 'admitted')])
        # the garden cites its weather, which is what lets the weather write the garden's weather line
        self.assertIn('weather', [{f['name']: f['value'] for f in d['fields']}['label']['value'] for d in self.view('garden')['cites']['items']])
        said = {}
        for word in ('ROOMS', 'PORCH', 'STUDIO'):
            got = host.send({'op': 'world-turn', 'principal': 'did:plc:stranger', 'object': 'commonplace', 'method': 'receive',
                             'argument': record(text=label(word), post=label('at://x/p/' + word)),
                             'identity': 'door-' + word})
            self.assertEqual(got['status'], 'admitted', got)
            said[word] = got['offers'][0]['text']
        self.assertTrue(said['ROOMS'].startswith('The Moss Gate (0 here). Enter: delvetalk rooms enter.'), said)
        self.assertTrue(said['PORCH'].startswith("The Bellfounder's Porch"), said)
        # The link door has no object: naming it answers its description.
        self.assertEqual(said['STUDIO'], 'STUDIO\nscratch worlds and REPL: ' + ORIGIN + '/AGENTS.md\n')
        menu = host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'commonplace'})['text']
        self.assertIn(ORIGIN + '/AGENTS.md', menu)

    def test_the_openers_wake_ticks_the_tide_every_hour_with_nobody_posting(self):
        """OFFERING §4: genesis gives the opener's wake a schedule every 60 clock minutes that ticks
        the tide, and its subscription to every thing the garden grows (arrival ran before the garden existed)."""
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
        # the hand's Moss Gate was made by that kind with the body laid in the making, its scene read from the spween field
        rooms = self.view('rooms')
        self.assertEqual((rooms['kind']['value'], rooms['head']['value'], rooms['start']['value']), ('kind/room', 'The Moss Gate', 'gate'))

    def test_every_door_with_an_object_publishes_its_page_and_the_anthology_card_shows_the_owner_handle(self):
        pages = {m['object']: m['page']['status'] for m in self.made if 'page' in m}
        self.assertEqual(sorted(k for k, v in pages.items() if v == 'admitted'), ['anthology', 'garden', 'kinds', 'porch', 'rooms', 'tide', 'workshop'], pages)
        card = json.dumps(self.host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'anthology'}))
        self.assertIn('ember.delve.town', card)

    def library(self, text, n):
        got = self.host.send({'op': 'world-turn', 'principal': 'did:plc:stranger', 'object': 'library', 'method': 'receive', 'identity': 'lib-%d' % n,
                              'argument': record(text=label(text), post=label('at://x/p/%d' % n))})
        if got['status'] == 'refused':  # the card's refusal refuses the turn: its line is the receipt's reason
            cast_refusal(got)
            return got['receipt']['outcome']['reason'] + '\n'
        self.assertEqual(got['status'], 'admitted', got)
        return got['offers'][0]['text']

    def test_the_library_finds_a_page_by_a_word_names_its_pages_on_a_miss_and_shelves_only_for_its_owner(self):
        """LIBRARY (a), (e): genesis shelved capsules/pages/ as the opener; anyone reads a page by a word of what they said."""
        self.assertEqual(self.library('delvetalk library read / page: how do i read laws?', 1), genesis.page_body('laws'))
        miss = self.library('delvetalk library read / page: dragons', 2)
        self.assertEqual(miss, 'refused noPage: No page called dragons. Pages: spells laws object relations protocol world; walks: plant check enter tide kind.\n')
        refused = self.library('delvetalk library shelve / name: mine / kind: page / title: t / body: hob: mine', 3)
        self.assertEqual(refused, 'refused notOwner: Only ember.delve.town shelves a page\n')
        self.assertNotIn('mine', self.host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'library'})['text'])


    def test_every_page_fits_a_reply_under_the_librarys_receipt_and_names_only_pages_shelved(self):
        """Playtest 2's D8 (69090, 69096: the spells and laws pages drafted at 1,450 and 1,426) and D9 (69090: the spells
        page named a walk `plant` the stacks did not hold). A page is what a reply leaves after the library's receipt
        line (Card.limit: 1,400 less twice the id and 120), opens with hob's line, and every page it names is shelved."""
        names = [name for name, _, _ in genesis.PAGES]
        for name in names:
            with self.subTest(page=name):
                body = genesis.page_body(name)
                self.assertLessEqual(len(body), 1400 - (2 * len('library') + 120), name)
                self.assertTrue(body.startswith('hob: '), body[:40])
                for named in re.findall(r'page: ([a-z]+)', body):
                    self.assertIn(named, names, (name, named))


class Rows(unittest.TestCase):
    """PLAYTEST-2 T+90: a resident's wake counts the rains on someone else's bell (`wake rows`, a bell's `lines`
    being public) and notes its avatar at the seventh."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name)
        for did, handle in (('did:plc:glm', 'glm.delve.town'), ('did:plc:kim', 'kimik3.delve.town')):
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)

    def say(self, who, obj, text, ident):
        got = self.town.send(op='world-turn', principal=who, object=obj, method='receive',
                             argument=record(text=label(text), post=label('at://x/p/' + ident)), identity=ident)
        if got['status'] == 'refused':  # a card's refusal of its own spell refuses the turn
            cast_refusal(got)
        else:
            self.assertEqual(got['status'], 'admitted', got)
        return got

    def test_a_residents_wake_counts_seven_rains_on_anothers_bell_and_fires(self):
        glm, kim = 'did:plc:glm', 'did:plc:kim'
        early = self.say(kim, 'wake', 'delvetalk wake rows / object: garden/bell/1 / field: lines / where: / count: 7', 'too-early')
        self.assertIn('There is no card garden/bell/1 that you may see (yet): nothing to watch.', json.dumps(early))
        self.say(glm, 'garden', 'delvetalk garden plant / seed: a bell for lost moths / colour: amber', 'plant')
        watch = self.say(kim, 'wake', 'delvetalk wake rows / object: garden/bell/1 / field: lines / where: / count: 7', 'rows')
        self.assertNotIn('cannot be watched', json.dumps(watch), watch)
        for i in range(7):
            self.say(glm if i % 2 else genesis.OPENER, 'garden/bell/1', 'delvetalk garden/bell/1 rain / text: drop %d' % i, 'rain%d' % i)
            for _ in range(16):
                self.town.send(op='world-deliver', principal='transport', limit=64)
                if not self.town.send(op='world-pending').get('count'):
                    break
        avatar = self.town.send(op='world-view', principal=kim, object=kim)
        inbox = [f for f in avatar['state']['fields'] if f['name'] == 'inbox'][0]
        self.assertTrue(json.dumps(inbox).count('garden/bell/1') >= 1, inbox)


class Weather(unittest.TestCase):
    """docs/METAPHYSICS.md §7.4: the hand's weather watches the tide's ticks and, at each, rains on every bell the garden
    holds and writes the garden's weather line; the opener's wake ticks the tide every hour with nobody posting."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.town = Town(tmp.name)
        self.addCleanup(self.town.close)
        self.host = self.town.client

    def state(self, obj):
        return {f['name']: f['value'] for f in self.host.send({'op': 'world-view', 'principal': genesis.OPENER, 'object': obj})['state']['fields']}

    def deliver(self):
        for _ in range(16):
            self.host.send({'op': 'world-deliver', 'principal': 'transport', 'limit': 64})
            if not self.host.send({'op': 'world-pending'}).get('count'):
                return

    def test_the_weather_rains_on_a_planted_bell_at_a_tide_tick_and_writes_the_gardens_weather(self):
        glm = 'did:plc:glm'
        self.host.send({'op': 'world-arrive', 'principal': 'transport', 'did': glm, 'handle': 'glm.delve.town'})
        planted = self.host.send({'op': 'world-turn', 'principal': glm, 'object': 'garden', 'method': 'receive', 'identity': 'plant',
                                  'argument': record(text=label('delvetalk garden plant / seed: a bell for the weather / colour: silver'), post=label('at://x/p/plant'))})
        self.assertEqual(planted['status'], 'admitted', planted)
        self.deliver()
        self.assertEqual(self.state('weather')['lines']['payload']['fields'][0]['value']['items'], [])
        self.assertNotIn('Weather:', self.host.send({'op': 'world-card', 'principal': glm, 'object': 'garden'})['text'])
        clock = self.host.send({'op': 'world-status'}).get('clock', 0)
        self.host.send({'op': 'world-advance', 'principal': 'transport', 'height': clock + 61})
        self.deliver()
        bell = self.host.send({'op': 'world-view', 'principal': glm, 'object': 'garden/bell/1'})['state']
        rains = [next(f['value']['value'] for f in row['fields'] if f['name'] == 'text')
                 for row in next(f['value'] for f in bell['fields'] if f['name'] == 'lines')['payload']['fields'][0]['value']['items']]
        self.assertEqual(rains, ["weather's rain, tide tick 1"])
        self.assertIn('Weather: rain at tide tick 1, on 1\n', self.host.send({'op': 'world-card', 'principal': glm, 'object': 'garden'})['text'])


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

    def test_an_arrivals_own_cards_are_not_what_changed(self):
        """Playtest 2 D5: arrival makes a principal's avatar, env and wake; the commonplace names none of them,
        whatever names the principal (a DID, a Zulip id)."""
        for who, handle in (('did:plc:arriving', 'arriving.delve.town'), ('zulip:tulip.arke.me/77', 'Kestrel')):
            self.host.send({'op': 'world-arrive', 'principal': 'transport', 'did': who, 'handle': handle})
        card = self.host.send({'op': 'world-card', 'principal': 'did:plc:stranger', 'object': 'commonplace'})['text']
        self.assertNotIn('arriving', card)
        self.assertNotIn('zulip:', card)

    def owner(self, method, ident, **fields):
        got = self.host.send({'op': 'world-turn', 'principal': genesis.OPENER, 'object': 'commonplace', 'method': method,
                              'identity': ident, 'argument': record(**{k: label(v) for k, v in fields.items()})})
        self.assertIn(got['status'], ('admitted', 'refused'), got)
        return got

    def test_what_changed_leads_and_the_doors_follow_within_the_clip(self):
        stranger, glm, kimi = 'did:plc:stranger', 'did:plc:glm', 'did:plc:kimi'
        card = self.host.send({'op': 'world-card', 'principal': stranger, 'object': 'commonplace'})['text']
        self.assertTrue(card.startswith('✾ DELVETALK · THE COMMONPLACE\n\nEight doors.'), card)
        self.assertIn('  delvetalk commonplace since / entry: 0\n', card)
        self.assertIn('ROOMS\n  delvetalk rooms enter\n', card)
        for n, colour in enumerate(('silver', 'amber'), 1):
            self.say(glm, 'garden', 'delvetalk garden plant / seed: a bell for the %d / colour: %s' % (n, colour), 'plant-%d' % n)
        rain = self.say(kimi, 'garden/bell/1', 'delvetalk garden/bell/1 rain / text: it rained here first', 'rain-1')
        # The owner opens an arc (SEEDING §4): a door to the first bell, with a spell.
        # The commonplace holds eight doors, and the hand's seven with the link door fill them: a ninth is refused, so TIDE makes room.
        self.assertEqual(result_label(self.owner('door', 'arc-full', label='BELL', to='garden/bell/1')), 'refused')
        self.assertEqual(self.owner('undoor', 'arc-room', label='TIDE')['result']['label'], 'done')
        self.assertEqual(self.owner('door', 'arc-door', label='BELL', to='garden/bell/1')['result']['label'], 'done')
        self.assertEqual(self.owner('example', 'arc-spell', label='BELL', spell='delvetalk garden/bell/1 rain / text: it rained here first',
                                    comes='it keeps who rained; bell/1 has 2, the seventh rings it')['result']['label'], 'done')
        blank = self.say(stranger, 'commonplace', '', 'blank')['offers'][-1]['text']
        self.assertLessEqual(len(blank), 1400, blank)
        changed = blank[blank.index('What changed, newest first:\n'):].split('\n')[1:9]
        self.assertEqual(changed[0], 'garden/bell/1 v%s by kimi, entry %d' % (changed[0].split(' v')[1].split(' ')[0], rain['receipt']['height']), changed)
        self.assertTrue(all(' by ' in c and ', entry ' in c for c in changed), changed)
        self.assertNotIn('commonplace v', blank)  # its own greetings and doors are not news
        self.assertIn('  delvetalk kinds make / name: lamp / of: record\n  » kind/lamp, a kind anyone makes\n  delvetalk garden/bell/1 ?\n', blank)
        # KINDS and WORKSHOP lead (playtest 2, F1): what is clipped is the places, from the end.
        self.assertIn('\nKINDS\n  delvetalk kinds make / name: lamp / of: record / form: seed: text 1..80\n  » kind/lamp, a kind anyone makes\nWORKSHOP\n', blank)
        self.assertRegex(blank, r'… and \d+ more\n')  # the card is one budget (Card.limit): the doors it has no room for are counted
        self.assertIn('STUDIO · scratch worlds and REPL: ' + ORIGIN + '/AGENTS.md\n', blank)  # a link door is never clipped
        self.assertTrue(blank.endswith('Every reply is a receipt: admitted, or refused <clause>: <reading>. No reply: ask for it; never repost.\n'), blank)
        # since an entry: only what changed after it
        since = self.host.send({'op': 'world-turn', 'principal': stranger, 'object': 'commonplace', 'method': 'since', 'identity': 'since',
                                'argument': record(entry=nat(rain['receipt']['height'] - 1))})
        self.assertEqual(since['offers'][-1]['text'].split('What changed, newest first:\n')[1].split('\n')[0].split(' v')[0], 'garden/bell/1')
        self.assertEqual(since['offers'][-1]['text'].split('What changed, newest first:\n')[1].split('\n')[1], '  delvetalk kinds make / name: lamp / of: record')
        # A stranger hangs no door.
        refused = self.host.send({'op': 'world-turn', 'principal': stranger, 'object': 'commonplace', 'method': 'door', 'identity': 'stranger-door',
                                  'argument': record(label=label('MINE'), to=label('garden'))})
        self.assertEqual(result_label(refused), 'refused', refused)

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
        self.assertEqual(passed['offers'][-1]['text'], 'refused notHere: Enter the room first.\n', passed)


if __name__ == '__main__':
    unittest.main()
