"""Enchantment (docs/OVERHAUL.md §4): the strokes of a thing, exact data assembled by the host; `Enchant.verify`,
which admits a paint only when every id, number, handle, spell and quotation in it is a stroke's; `world-render`,
which hands the strokes to the one model worker once per version and answers the exact card until a verified paint
is cached.

Evidence for HOST-HANDOFF 5.160 (layer: host). Refuted by: strokes that hold a line, handle or number the store
does not; a strokes read that writes; a paint naming what the strokes do not hold that is cached; 69275's sentence
admitted against the anthology's strokes; one version rendered twice costing two model calls; a world with no
model showing anything but the exact card.

    python3 -W error -m unittest tests.test_enchant -v
"""
import tempfile
import unittest

from deploy import genesis
from tests.town import Town
from tests.wire import label, record

GLM, KIM = 'did:plc:glm', 'did:plc:kim'
YUE = 'the anchor remembers what the garden can\'t; the soil keeps the corrections'


class Strokes(unittest.TestCase):
    """One town, a bell with two rains and an anthology line, read as strokes."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name)
        cls.addClassCleanup(cls.town.close)
        for did, handle in ((GLM, 'glm.delve.town'), (KIM, 'kimik3.delve.town')):
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        cls.say(GLM, 'garden', 'delvetalk garden plant / seed: a bell for lost moths / colour: amber', 'plant')
        cls.say(KIM, 'garden/bell/1', 'delvetalk garden/bell/1 rain / text: ' + YUE, 'rain1')
        cls.say(GLM, 'garden/bell/1', 'delvetalk garden/bell/1 rain / text: drop 77', 'rain2')
        cls.say(KIM, 'anthology', 'delvetalk anthology write / text: the garden forgets; the gardeners don\'t.', 'line1')

    @classmethod
    def say(cls, who, obj, text, ident):
        got = cls.town.send(op='world-turn', principal=who, object=obj, method='receive',
                            argument=record(text=label(text), post=label('at://x/p/' + ident)), identity=ident)
        assert got['status'] == 'admitted', got
        return got

    def strokes(self, obj, who=KIM, **more):
        return self.town.send(op='world-strokes', principal=who, object=obj, **more)

    def test_a_bell_s_strokes_are_its_exact_lines_handles_and_spells(self):
        height = self.town.send(op='world-status')['height']
        got = self.strokes('garden/bell/1')
        self.assertEqual(got['status'], 'strokes', got)
        s = got['strokes']
        self.assertEqual((s['object'], s['kind'], s['maker'], s['around']), ('garden/bell/1', 'kind/bell', 'glm.delve.town', 'garden'))
        self.assertEqual(s['fields'], {'seed': 'a bell for lost moths', 'colour': 'amber'})
        self.assertEqual([(l['handle'], l['text']) for l in s['lines']], [('kimik3.delve.town', YUE), ('glm.delve.town', 'drop 77')])
        self.assertTrue(all(l['at'] > s['made'] > 0 for l in s['lines']), s)
        self.assertEqual(s['counts'], {'lines': 2, 'marks': 0})
        rain = next(v for v in s['verbs'] if v['name'] == 'rain')
        self.assertEqual(rain['spell'], 'delvetalk garden/bell/1 rain / text: <text, 1 to 200 characters>')
        self.assertIn('owner', [l['name'] for l in s['laws']])
        self.assertTrue(all(l.get('reading') for l in s['laws']), s['laws'])
        self.assertEqual((s['rules'], s['wants'], s['today']), ([], [], []))
        # A read: nothing is journaled.
        self.assertEqual(self.town.send(op='world-status')['height'], height)

    def test_the_anthology_holds_its_keeper_and_its_pending_line(self):
        s = self.strokes('anthology')['strokes']
        self.assertEqual(s['keeper'], genesis.HANDLE)
        self.assertEqual([(l['n'], l['state']) for l in s['lines']], [(1, 'pending')])
        self.assertIn('delvetalk anthology write / text: <text, 1 to 280 characters>', [v['spell'] for v in s['verbs']])

    def test_a_thing_s_surrounding_is_its_keeper_s_line(self):
        self.say(GLM, 'porch/ring', 'delvetalk porch/ring inspirit / surrounding: it rings for whoever is late', 'ring')
        s = self.strokes('porch/ring')['strokes']
        self.assertEqual((s['keeper'], s['around']), ('glm.delve.town', 'porch'))
        self.assertEqual(s['lines'][0], {'handle': 'glm.delve.town', 'verb': 'inspirit', 'text': 'it rings for whoever is late'})

    def test_an_earlier_version_and_the_reader_s_reach(self):
        now = self.strokes('garden/bell/1')
        then = self.strokes('garden/bell/1', version=now['version'] - 1)
        self.assertEqual([l['text'] for l in then['strokes']['lines']], [YUE])
        self.assertEqual(self.strokes('garden/bell/1', version=now['version'] + 1)['status'], 'unknown')
        self.assertEqual(self.strokes('nowhere/1')['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
