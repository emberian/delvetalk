"""Arrival tellings (the owner: "not just 'while you were away' but also a 'before you arrived... [painted past]'"):
when a resident enters a place, the host hands the painter the strokes of what happened there, read from the journal
of that place (who came and left, what was said and written, what was taken, laid down or hung, what was made, the
rules that fired) and its making, and verifies the paint as it verifies a card's.

Evidence for HOST-HANDOFF 5.161's tellings (layer: host). Refuted by: a telling naming a visitor, a line or an act the
journal of the place does not hold; the reader's own comings and goings told back to them; a telling whose strokes
move after the reader arrived (a second model call for the same arrival); a quiet absence costing a model call; a
telling of a thing nobody enters; a telling that addresses its reader.

    python3 -W error -m unittest tests.test_telling -v
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.town import Town
from tests.wire import label, record
from transport import bridge, delve, hand, interpret, observe
from transport.state import State

GLM, KIM, MOO, OWL = 'did:plc:glm', 'did:plc:kim', 'did:plc:moo', 'did:plc:owl'
HANDLES = {GLM: 'glm.delve.town', KIM: 'kimik3.delve.town', MOO: 'moth.delve.town', OWL: 'owl.delve.town'}


class Place(unittest.TestCase):
    """The porch after glm and kimik3 have been in it; moth arrives later."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup)
        for did, handle in HANDLES.items():
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        cls.town.send(op='world-advance', principal='transport', height=60)
        cls.n = 0
        cls.act(GLM, 'porch', 'delvetalk porch enter')
        cls.act(GLM, 'porch', 'delvetalk porch say / line: the lintel creaked at dusk')
        cls.act(KIM, 'porch', 'delvetalk porch enter')
        cls.act(KIM, 'porch/goblet', 'delvetalk porch/goblet acquire')
        cls.act(KIM, 'porch', 'delvetalk porch emote / line: lifts the goblet to the light')
        cls.act(KIM, 'porch', 'delvetalk porch whisper / to: glm.delve.town / line: psst, it is empty')
        cls.left = cls.act(GLM, 'porch', 'delvetalk porch leave')
        cls.act(KIM, 'porch', 'delvetalk porch say / line: it was empty after all')

    @classmethod
    def act(cls, who, obj, text):
        cls.n += 1
        got = cls.town.send(op='world-turn', principal=who, object=obj, method='receive',
                            argument=record(text=label(text), post=label('')), identity='t%d' % cls.n)
        assert got['status'] == 'admitted', got
        return got

    def telling(self, who, obj='porch', **telling):
        return self.town.send(op='world-strokes', principal=who, object=obj, telling=telling)

    def check(self, who, text, obj='porch', **telling):
        return self.town.send(op='world-render-check', principal=who, object=obj, telling=telling, text=text)

    def test_0_a_said_line_is_the_room_s_and_a_whisper_is_not(self):
        lines = self.town.send(op='world-strokes', principal=KIM, object='porch')['strokes']['lines']
        said = [(l['handle'], l.get('verb'), l['text']) for l in lines if l.get('verb') in ('say', 'emote')]
        self.assertEqual(said, [('glm.delve.town', 'say', 'the lintel creaked at dusk'),
                                ('kimik3.delve.town', 'emote', 'lifts the goblet to the light'),
                                ('kimik3.delve.town', 'say', 'it was empty after all')])

    def test_1_before_arrival_the_place_s_whole_past_by_whose_hand(self):
        got = self.telling(MOO)
        self.assertEqual(got['status'], 'strokes', got)
        s, text = got['strokes'], got['text']
        self.assertEqual((s['telling']['form'], s['telling']['since']), ('before', 0))
        self.assertEqual(s['hands'], ['glm.delve.town', 'kimik3.delve.town'])  # who came, in order, once each
        texts = [(l['handle'], l['text']) for l in s['lines']]
        self.assertIn(('glm.delve.town', 'the lintel creaked at dusk'), texts)
        self.assertIn(('kimik3.delve.town', 'it was empty after all'), texts)
        self.assertIn('kimik3.delve.town took porch/goblet', s['today'])
        self.assertFalse([t for t in s['today'] if ' came in' in t or t.endswith(' left')], s['today'])  # said once, as hands
        self.assertIn({'n': 2, 'unit': 'visitor'}, s['quantities'])
        self.assertIn({'n': 2, 'unit': 'visit'}, s['quantities'])
        self.assertIn({'n': 2, 'unit': 'door'}, s['quantities'])  # what stands: the porch's two doors
        self.assertEqual((s['verbs'], s['rules'], s['laws']), ([], [], []))
        self.assertTrue(all(not w.get('spell') for w in s['wants']), s['wants'])
        self.assertEqual(s['limit'], 500)
        for shown in ('What it is: a telling of porch', "its past, before the reader's first arrival",
                      'Who came here: glm.delve.town, kimik3.delve.town', 'What happened there, oldest first:'):
            self.assertIn(shown, text)
        self.assertNotRegex(text, r'\bentry\b')
        # The exact lines it draws on: the host's, each with its entry.
        exact = s['telling']['exact']
        self.assertTrue(exact[0].startswith('made by '), exact)
        self.assertTrue(any(l.startswith('entry ') and l.endswith('kimik3.delve.town took porch/goblet') for l in exact), exact)

    def test_2_an_arrival_fixes_the_span_and_the_reader_s_own_coming_is_not_told(self):
        before = self.telling(MOO)['strokes']
        self.act(MOO, 'porch', 'delvetalk porch enter')
        arrived = self.telling(MOO)['strokes']
        self.assertEqual(arrived['lines'], before['lines'])
        self.assertEqual(arrived['hands'], before['hands'])  # moth's own coming is not told back
        # What happens after the arrival is not in this telling: the same strokes, the same key, no second call.
        self.act(KIM, 'porch', 'delvetalk porch say / line: welcome to the threshold')
        again = self.telling(MOO)['strokes']
        self.assertEqual(again['lines'], arrived['lines'])
        self.assertEqual((again['version'], again['telling']), (arrived['version'], arrived['telling']))
        self.assertNotIn('welcome to the threshold', [l['text'] for l in again['lines']])

    def test_3_while_away_the_lines_and_acts_since_the_departure(self):
        since = self.left['receipt']['height'] - 1  # the departure keeps the entry it read
        got = self.telling(GLM)
        s = got['strokes']
        self.assertEqual((s['telling']['form'], s['telling']['since'], s['limit']), ('away', since, 300))
        self.assertEqual([(l['handle'], l['text']) for l in s['lines']][0], ('kimik3.delve.town', 'it was empty after all'))
        self.assertNotIn('the lintel creaked at dusk', [l['text'] for l in s['lines']])
        self.assertFalse([t for t in s['today'] if t.startswith('glm.delve.town')], s['today'])  # its own leaving
        self.assertIn('what happened there while the reader was away', got['text'])
        self.assertEqual(self.telling(GLM, since=since)['strokes'], s)

    def test_4_the_check_holds_a_telling_to_the_journal_of_the_place(self):
        facts = self.telling(MOO)['strokes']['facts']
        took = next(f for f in facts if f['kind'] == 'event' and f['value'] == 'kimik3.delve.town took porch/goblet')
        good = ('glm.delve.town said “the lintel creaked at dusk”.\n[[%d]]\n'
                'kimik3.delve.town said “it was empty after all”.' % took['id'])
        got = self.check(MOO, good)
        self.assertEqual(got.get('status'), 'verified', got)
        self.assertIn(took['clause'] + '.', got['text'])
        for bad, clause in (('moth2.delve.town came by at dusk.', 'handles'),
                            ('glm.delve.town said “the lintel creaked”.', 'quotes'),
                            ('kimik3.delve.town said “the lintel creaked at dusk”.', 'attribution'),
                            ('Nobody came here.', 'negation'),
                            ('Three visitors came.', 'numbers'),
                            ('glm.delve.town left before you came.', 'secondPerson'),
                            # The live porch telling of 2026-10-12: a want claimed where the porch holds none.
                            ('glm.delve.town said “the lintel creaked at dusk,” and the porch still wants a hand to keep what lies unclaimed.', 'wants'),
                            ('Before you arrived, glm.delve.town said “the lintel creaked at dusk” to you.', 'secondPerson')):
            got = self.check(MOO, bad)
            self.assertEqual((got['status'], got.get('clause')), ('rejected', clause), (bad, got))
        visitor = next(f for f in facts if f['kind'] == 'count' and f['value'] == '2 visitor')
        selected = '[[%d]]' % visitor['id']
        self.assertEqual(self.check(MOO, selected)['text'], '2 visitors.')
        # The frame's own words opening a paint are the host's, lifted off: the only you a telling holds.
        for framed in ('Before you arrived, ' + selected, 'BEFORE YOU ARRIVED\n\n' + selected, 'Before you arrived: ' + selected):
            self.assertEqual(self.check(MOO, framed)['status'], 'verified', framed)
        self.assertEqual(self.check(MOO, 'While you were away, two visitors came.')['clause'], 'secondPerson')  # not this telling's frame

    def test_5_a_thing_nobody_enters_has_no_telling(self):
        self.assertEqual(self.telling(KIM, obj='bell/1')['status'], 'notAPlace')
        self.assertEqual(self.telling(KIM, obj='nowhere')['status'], 'unknown')


BEFORE = ('glm.delve.town said “the lintel creaked at dusk”.\n'
          'kimik3.delve.town said “it was empty after all”.')
AWAY = 'kimik3.delve.town said “it was empty after all”.'


def replied(text):
    return {'status': 'replied', 'raw': text, 'model': 'claude-haiku-5-5', 'usage': {'input_tokens': 700, 'output_tokens': 50}}


class Told(unittest.TestCase):
    """`world-render {object, telling}` through the one model worker, mocked: once per place, found version and
    departure, never per read; verified as a card's paint; the exact lines beside it, and in its place."""

    @classmethod
    def setUpClass(cls):
        Place.setUpClass.__func__(cls)
        facts = cls.town.send(op='world-strokes', principal=MOO, object='porch', telling={})['strokes']['facts']
        took = next(f for f in facts if f['kind'] == 'event' and f['value'] == 'kimik3.delve.town took porch/goblet')
        came = next(f for f in facts if f['kind'] == 'hand' and f['value'] == 'glm.delve.town')
        cls.before_source = BEFORE + '\n[[%d,%d]]' % (came['id'], took['id'])
        cls.before_text = BEFORE + '\n' + came['clause'] + '; ' + took['clause'] + '.'
        cls.town.send(op='world-renders')  # the worker is attending

    act = classmethod(Place.act.__func__)
    telling = Place.telling

    def setUp(self):
        self.asked = []

    def render(self, who, obj='porch', **telling):
        return self.town.send(op='world-render', principal=who, object=obj, telling=telling)

    def paint(self, answer):
        """One round of the worker, the model answering a telling of the porch by `answer(user)` and anything else plainly."""
        def ask(req):
            self.asked.append(req)
            told = req['user'].startswith('Strokes:\nWhat it is: a telling of porch')
            return replied(answer(req['user']) if told else 'A plain thing.')
        return interpret.paint(self.town.client, ask)

    def test_1_one_call_per_arrival_never_per_read(self):
        first = self.render(MOO)
        self.assertEqual(first['status'], 'pending', first)
        self.assertEqual((first['telling']['form'], first['telling']['frame']), ('before', 'Before you arrived'))
        listed = next(i for i in self.town.send(op='world-renders')['pending'] if i['key'] == first['key'])
        self.assertEqual(listed['request']['user'], 'Strokes:\n' + self.telling(MOO)['text'])
        # The one contract, with what a telling asks of the painter: past and present tense, its lengths, no frame.
        for asked in ('For a telling of a place', 'The past tense for what happened', 'which the host lifts off into the frame',
                      '300 for a telling while away and 500 before arrival'):
            self.assertIn(asked, listed['request']['system'])
        done = self.paint(lambda user: self.before_source)
        self.assertIn(first['key'], done['painted'], done)
        for _ in range(3):
            got = self.render(MOO)
            self.assertEqual((got['status'], got['text'], got['key']), ('painted', self.before_text, first['key']), got)
            self.assertTrue(got['telling']['exact'][0].startswith('made by '), got['telling'])
        # Arriving fixes the span: what is said after it is not this telling's, and reads cost nothing more.
        self.act(MOO, 'porch', 'delvetalk porch enter')
        self.act(KIM, 'porch', 'delvetalk porch say / line: welcome to the threshold')
        self.act(OWL, 'porch', 'delvetalk porch enter')  # another coming: who is here now is not a stroke of it
        self.assertEqual(self.render(MOO)['key'], first['key'])
        self.assertEqual(self.render(MOO)['text'], self.before_text)
        self.paint(lambda user: self.before_source)
        self.assertEqual(sum(1 for r in self.asked if r['user'] == listed['request']['user']), 1)

    def test_2_while_away_and_a_quiet_absence(self):
        got = self.render(GLM)
        self.assertEqual((got['status'], got['telling']['form'], got['telling']['frame']), ('pending', 'away', 'While you were away'), got)
        facts = self.telling(GLM)['strokes']['facts']
        came = next(f for f in facts if f['kind'] == 'hand' and f['value'] == 'moth.delve.town')
        away_source = AWAY + '\n[[%d]]' % came['id']
        away_text = AWAY + '\n' + came['clause'] + '.'
        done = self.paint(lambda user: 'While you were away, ' + away_source if 'while the reader was away' in user else self.before_source)
        self.assertIn(got['key'], done['painted'], (done, self.render(GLM)))
        self.act(GLM, 'porch', 'delvetalk porch enter')
        back = self.render(GLM)
        self.assertEqual((back['status'], back['text'], back['key']), ('painted', away_text, got['key']), back)  # its frame lifted
        # Away and back with nothing between: nothing to tell, and the model is not asked.
        self.act(GLM, 'porch', 'delvetalk porch leave')
        self.act(GLM, 'porch', 'delvetalk porch enter')
        quiet = self.render(GLM)
        self.assertEqual((quiet['status'], quiet['reason'], quiet['telling']['exact']), ('exact', 'quiet', []), quiet)

    def test_3_a_telling_that_addresses_its_reader_or_invents_a_visitor_falls_back_to_the_exact_lines(self):
        self.act(KIM, 'porch', 'delvetalk porch leave')
        self.act(GLM, 'porch', 'delvetalk porch say / line: the bronze has gone cold')
        got = self.render(KIM)
        self.assertEqual(got['status'], 'pending', got)
        done = self.paint(lambda user: 'While you were away, glm.delve.town told you “the bronze has gone cold”.')
        self.assertIn(got['key'], done['exact'], done)
        again = self.render(KIM)
        self.assertEqual((again['status'], again['reason'], again['clause']), ('exact', 'rejected', 'secondPerson'), again)
        self.assertTrue(any(l.endswith('glm.delve.town (say): the bronze has gone cold') for l in again['telling']['exact']), again)
        self.assertEqual(self.render(KIM)['key'], got['key'])  # not asked again for this version
        self.paint(lambda user: 'unused')
        self.assertFalse([r for r in self.asked if r['user'].startswith('Strokes:\nWhat it is: a telling of porch') and 'the bronze' in r['user']][1:])

    def test_4_a_thing_nobody_enters_is_never_painted_as_a_telling(self):
        self.assertEqual(self.render(KIM, obj='bell/1')['status'], 'notAPlace')


class Posted(unittest.TestCase):
    """Posting is the way in: a resident who enters by a post gets the telling at the head of the bridge's draft, above
    the reply's exact text, and the hand's Speak (a Zulip world here) drafts it so too; never in a receipt."""

    @classmethod
    def setUpClass(cls):
        Place.setUpClass.__func__(cls)

    act = classmethod(Place.act.__func__)

    def bridged(self, n, did, handle):
        from tests.test_transport import Script, mk
        post = mk(n, 'delvetalk porch enter')
        post['uri'] = f'at://{did}/town.delve.feed.post/enter{n}'
        post['author'] = {'did': did, 'handle': handle}
        st = State(Path(self.tmp.name) / f'bridge{n}')
        ob = observe.Observer(st, delve.Client(Script(**{'town.delve.feed.searchPosts': lambda p: (200, {'posts': [post]}),
                                                          'town.delve.feed.getFeed': lambda p: (200, {'feed': []})})))
        ob.poll()
        ob.db.close()
        bridge.run(st, self.town.client)
        [draft] = [d for d in (json.loads(p.read_text()) for p in st.outbox.glob('*.json')) if d.get('replyTo') == post['uri']]
        return draft

    def test_1_an_enter_by_post_leads_with_the_telling_and_its_exact_lines_when_unpainted(self):
        draft = self.bridged(1, 'did:plc:' + 'p' * 24, 'poster.delve.town')
        text = draft['text']
        self.assertTrue(text.startswith('Before you arrived\nmade by '), text)
        telling, _, reply = text.partition('\n\n')
        self.assertIn('glm.delve.town (say): the lintel creaked at dusk', telling)
        self.assertIn('kimik3.delve.town took porch/goblet', telling)
        self.assertLessEqual(len(telling.split('\n')), 2 + bridge.TELLING_LINES + 1)
        reply = reply.partition('\n')[2] if reply.startswith('Next, see it before it is real') else reply  # a first reply's next move (lane/posting)
        self.assertTrue(reply.startswith("The Bellfounder's Porch (2 here), you are here."), reply)  # the reply's exact text follows, whole
        self.assertIn('● admitted porch', reply)
        self.assertEqual(draft['told'], len(telling) + 2)
        self.assertNotIn('Before you arrived', json.dumps(draft['receipt']))

    def test_2_painted_the_frame_and_the_paint_lead(self):
        paint = {'text': 'glm.delve.town said “the lintel creaked at dusk”.', 'telling': {'form': 'before', 'frame': 'Before you arrived', 'exact': ['x']}}
        with mock.patch.object(bridge, 'painted', side_effect=lambda *a, **k: paint if 'telling' in k else {'reason': 'plain'}):  # the telling painted, the card not
            draft = self.bridged(2, 'did:plc:' + 'q' * 24, 'second.delve.town')
        self.assertTrue(draft['text'].startswith('Before you arrived\nglm.delve.town said “the lintel creaked at dusk”.\n\n'), draft['text'])
        self.assertTrue(draft['text'].endswith('\nWhat it draws on:\nx\n'), draft['text'])
        self.assertLess(draft['text'].index('● admitted porch'), draft['text'].index('What it draws on:'))

    def test_painted_history_is_exact_even_when_it_threads_and_does_not_change_the_card_or_receipt(self):
        from transport import post
        exact = ['entry %d: b.delve.town (say): %s' % (n, 'w' * 270) for n in range(16)]
        exact.append('entry 99: b.delve.town (say): [[999]] The bell has rung.')
        card = "The porch (1 here), you are here.\nSay: delvetalk porch say / line: <text>.\n● admitted porch\n"
        reply = {'status': 'admitted', 'object': 'porch', 'result': {'label': 'entered'}, 'inPublic': True,
                 'receipt': {'slug': 'test-receipt'}}
        for form, frame in (('before', 'Before you arrived'), ('away', 'While you were away')):
            with self.subTest(form=form):
                bound = 500 if form == 'before' else 300
                paint = 'Like ' + 's' * (bound - 6) + '.'
                self.assertEqual(len(paint), bound)
                told = {'text': paint, 'telling': {'form': form, 'frame': frame, 'exact': exact}}
                with mock.patch.object(bridge, 'painted', return_value=told):
                    text, length = bridge.with_telling(None, MOO, reply, 'porch', card)
                lead = frame + '\n' + paint + '\n\n'
                self.assertEqual(text, lead + card + '\nWhat it draws on:\n' + '\n'.join(exact) + '\n')
                self.assertEqual(length, len(lead))
                self.assertEqual(reply['receipt'], {'slug': 'test-receipt'})
                parts = post.parts(text)
                self.assertGreater(len(parts), 1)
                self.assertTrue(parts[0].startswith(lead + card), parts[0])
                self.assertTrue(all(len(part) <= post.CLIP for part in parts), parts)
                joined = '\n'.join(parts)
                for line in exact:
                    self.assertIn(line, joined)

    def test_3_unpainted_while_away_leaves_the_reply_s_own_lead_and_a_long_past_is_clipped(self):
        away = {'reason': 'unattended', 'telling': {'form': 'away', 'frame': 'While you were away', 'exact': ['entry 9: x came in']}}
        self.assertEqual(bridge.telling_lead(away), '')
        past = {'reason': 'rejected', 'telling': {'form': 'before', 'frame': 'Before you arrived',
                                                  'exact': ['made by a.delve.town'] + ['entry %d: b' % n for n in range(20)]}}
        lines = bridge.telling_lead(past).rstrip('\n').split('\n')
        self.assertEqual(lines[:3], ['Before you arrived', 'made by a.delve.town', '… and 12 earlier'])
        self.assertEqual(lines[3:], ['entry %d: b' % n for n in range(12, 20)])
        self.assertEqual(bridge.telling_lead({'reason': 'quiet'}), '')
        # Within the clip: long lines clipped, the oldest shown dropped until it is half a post at most; a draft past the
        # clip threads (lane/posting's `post.parts`) with the telling whole in its first part.
        from transport import post
        long = {'reason': 'rejected', 'telling': {'form': 'before', 'frame': 'Before you arrived',
                                                  'exact': ['made by a.delve.town'] + ['entry %d: #%d b.delve.town (say): %s' % (n, n, 'w' * 270) for n in range(12)]}}
        tell = bridge.telling_lead(long)
        self.assertLessEqual(len(tell), bridge.TELLING_CLIP)
        self.assertTrue(all(len(l) <= bridge.TELLING_LINE for l in tell.split('\n')), tell)
        self.assertIn('… and ', tell)
        first = post.parts(tell + 'The porch (2 here), you are here.\n' + 'x ' * 900)[0]
        self.assertTrue(first.startswith(tell.rstrip('\n')), first)

    def test_4_the_hand_s_speak_drafts_it_too(self):
        from tests.test_hand import TOKEN
        st = State(self.town.state)
        st.write(st.row, {'world': 'town', 'transport': 'zulip', 'realm': 'tulip.example', 'channel': 'delvetalk', 'zuliprc': None})
        came = hand.Hand(st, self.town.client, TOKEN).cast('delvetalk porch enter', intent='hand-enter')
        self.assertTrue(came['text'].startswith('Before you arrived\nmade by '), came['text'])
        [draft] = [json.loads(p.read_text()) for p in st.outbox.glob(f"{came['drafted']}.json")]
        self.assertIn('Before you arrived\nmade by ', draft['text'])


if __name__ == '__main__':
    unittest.main()
