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
import tempfile
import unittest

from tests.town import Town
from tests.wire import label, record

GLM, KIM, MOO = 'did:plc:glm', 'did:plc:kim', 'did:plc:moo'
HANDLES = {GLM: 'glm.delve.town', KIM: 'kimik3.delve.town', MOO: 'moth.delve.town'}


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
        self.assertEqual((s['verbs'], s['rules'], s['laws']), ([], [], []))
        self.assertTrue(all(not w.get('spell') for w in s['wants']), s['wants'])
        self.assertEqual(s['limit'], 500)
        for shown in ('What it is: a telling of porch', 'its past, told to one who arrives for the first time',
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
        good = ('glm.delve.town said “the lintel creaked at dusk”; later kimik3.delve.town took porch/goblet '
                'and found “it was empty after all”.')
        self.assertEqual(self.check(MOO, good).get('status'), 'verified', self.check(MOO, good))
        for bad, clause in (('moth2.delve.town came by at dusk.', 'handles'),
                            ('glm.delve.town said “the lintel creaked”.', 'quotes'),
                            ('kimik3.delve.town said “the lintel creaked at dusk”.', 'attribution'),
                            ('Nobody came here.', 'negation'),
                            ('Three visitors came.', 'numbers'),
                            ('While you were away, glm.delve.town left.', 'secondPerson')):
            got = self.check(MOO, bad)
            self.assertEqual((got['status'], got.get('clause')), ('rejected', clause), (bad, got))
        self.assertEqual(self.check(MOO, 'Two visitors came.')['status'], 'verified')

    def test_5_a_thing_nobody_enters_has_no_telling(self):
        self.assertEqual(self.telling(KIM, obj='bell/1')['status'], 'notAPlace')
        self.assertEqual(self.telling(KIM, obj='nowhere')['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
