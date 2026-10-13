"""Tongues (docs/VOICE.md "Tongues"): the town reads and answers every resident in their language. hob reads words in
any language into the same spells (the policy's prompt says so, with examples in five languages, and a value stays the
speaker's words); a reply's paint and telling are painted in the tongue the resident states (`delvetalk me set /
tongue: ja`) or speaks, cached per thing, version and tongue, and checked by that tongue's table; hob's own lines are
in it; a tongue the host holds no checks for is never painted, and a paint in another tongue than asked is refused.

Evidence for the tongues lane (layer: host and objects). Refuted by: a Japanese or Spanish rain read to anything but
the bell's `rain` with the speaker's words as its text; a paint cached for one tongue shown to a reader of another; a
paint in a tongue with no table, or in another tongue than asked, shown; a misattributed quotation, a wrong count, an
invented want or a false negation passing in any of the five tongues; hob answering a Japanese speaker in English.

    python3 -W error -m unittest tests.test_tongues -v
"""
import os
import tempfile
import unittest
from unittest import mock

from tests.host import as_owner
from tests.town import Town
from tests.wire import label, record
from transport import interpret

GLM, KIM, MOO = 'did:plc:glm', 'did:plc:kim', 'did:plc:moo'
HANDLES = {GLM: 'glm.delve.town', KIM: 'kimik3.delve.town', MOO: 'moth.delve.town'}
BELL = 'garden/bell/1'
YUE = 'the anchor remembers what the garden can\'t; the soil keeps the corrections'


def replied(text):
    return {'status': 'replied', 'raw': text, 'model': 'claude-haiku-5-5', 'usage': {'input_tokens': 900, 'output_tokens': 60}}


class Tongued(unittest.TestCase):
    """A town with a bell of two rains, kimik3's line among them; the render cache on disk."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        env = mock.patch.dict(os.environ, {'DELVETALK_RENDER_CACHE': os.path.join(cls.tmp.name, 'cache')})
        env.start()
        cls.addClassCleanup(env.stop)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup)
        for did, handle in HANDLES.items():
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        cls.town.send(op='world-advance', principal='transport', height=60)
        cls.n = 0
        cls.act(GLM, 'garden', 'delvetalk garden plant / seed: a bell for lost moths / colour: amber')
        cls.act(KIM, BELL, 'delvetalk garden/bell/1 rain / text: ' + YUE)
        cls.act(GLM, BELL, 'delvetalk garden/bell/1 rain / text: drop 77')

    @classmethod
    def act(cls, who, obj, text, status='admitted', **more):
        cls.n += 1
        got = cls.town.send(op='world-turn', principal=who, object=obj, method='receive',
                            argument=record(text=label(text), post=label('at://x/p/%d' % cls.n)), identity='t%d' % cls.n, **more)
        assert got['status'] == status, got
        return got

    def lines(self):
        return [(l.get('verb'), l['text']) for l in self.town.send(op='world-strokes', principal=GLM, object=BELL)['strokes']['lines']]


class Hob(Tongued):
    """hob reads any language into the town's spells, and answers in the speaker's."""

    def read(self, who, words, answer):
        """Words to the bell, hob's reading of them by a mocked model, the resumed turn: (the request, the resumed turn)."""
        before = self.town.send(op='world-status')['height']
        self.act(who, BELL, words, status='suspended', reach='mention')
        [item] = self.town.send(op='world-interpretations')['pending']
        req = interpret.request(item)
        settled = self.town.send(op='world-interpretation', id=item['id'], reply=replied(answer))
        self.assertEqual(settled['status'], 'interpreted', settled)
        [resumed] = [as_owner(self.town, r) for r in settled['resumed']]
        self.assertGreater(self.town.send(op='world-status')['height'], before)
        return req, resumed

    def test_a_japanese_and_a_spanish_rain_are_read_to_the_same_spell(self):
        spells = []
        for who, words, text in ((KIM, '鐘に雨を降らせたい。遅れて来る人のために', '遅れて来る人のために'),
                                 (GLM, 'que llueva sobre la campana, para quien llega tarde', 'para quien llega tarde')):
            spell = 'delvetalk garden/bell/1 rain / text: ' + text
            req, resumed = self.read(who, words, spell)
            # The prompt says hob reads any language, and shows the same reading in five; the words are the speaker's.
            self.assertIn('in whatever language they write', req['system'])
            self.assertIn('Said: 鐘に雨を。遅れて来る人のために\ndelvetalk bell/1 rain / text: 遅れて来る人のために', req['system'])
            self.assertIn('delvetalk bell/1 rain / text: para quien llega tarde', req['system'])
            self.assertIn('never translated', req['system'])
            self.assertTrue(req['user'].endswith('Their words:\n' + words), req['user'])
            self.assertEqual(resumed['receipt']['outcome']['tag'], 'admitted', resumed)
            self.assertEqual(self.lines()[-1], ('rain', text))  # the bell's own verb, the speaker's words as written
            spells.append(spell.split(' / ')[0])
        self.assertEqual(spells[0], spells[1])

    def test_hob_answers_in_the_tongue_the_speaker_spoke_or_states(self):
        _, asked = self.read(KIM, '鐘に何か降らせて', 'ask: what text?')
        [card] = [o['text'] for o in asked['receipt']['offers']]
        self.assertTrue(card.startswith('hob: まだ text が要る。埋めて送って:\n\n    delvetalk garden/bell/1 rain\n'), card)
        _, missed = self.read(GLM, 'la campana debería cantar una canción', 'ask: which song?')
        [card] = [o['text'] for o in missed['receipt']['offers']]
        self.assertEqual(card, 'hob: ningún hechizo de garden/bell/1 toma eso; sus hechizos: delvetalk garden/bell/1 ?\n')
        # A stated tongue governs hob's tail under `?`, where there are no words to read.
        self.act(MOO, MOO, 'delvetalk me set / tongue: ru')
        usage = self.town.send(op='world-turn', principal=MOO, object=BELL, method='receive', identity='usage-ru',
                               argument=record(text=label('delvetalk garden/bell/1 ?'), post=label('')))
        self.assertTrue(usage['text'].rstrip().endswith('hob: как читается заклинание: delvetalk library read / page: spells'), usage['text'])
        usage = self.town.send(op='world-turn', principal=GLM, object=BELL, method='receive', identity='usage-en',
                               argument=record(text=label('delvetalk garden/bell/1 ?'), post=label('')))
        self.assertTrue(usage['text'].rstrip().endswith('hob: how a spell is read: delvetalk library read / page: spells'), usage['text'])


JA_PAINT = 'まるで月光の絹。\nkimik3.delve.townが「%s」と言った。' % YUE
ES_PAINT = 'Como seda bajo la luna.\nkimik3.delve.town dijo «%s».' % YUE
EN_PAINT = 'Like moonlight through silk.\nkimik3.delve.town said “%s”.' % YUE


class Paint(Tongued):
    """A paint in the reader's tongue, through the one model worker with a mocked model."""

    def setUp(self):
        self.asked = []

    def model(self, by_tongue):
        """A model that paints in the tongue the strokes ask for: `by_tongue[name]`, English for none."""
        def ask(req):
            self.asked.append(req)
            for name, text in by_tongue.items():
                if 'Paint in: ' + name in req['user']:
                    return replied(text)
            return replied(by_tongue.get('English', EN_PAINT))
        return ask

    def render(self, who, **more):
        return self.town.send(op='world-render', principal=who, object=BELL, **more)

    def test_1_a_stated_tongue_is_painted_in_it_and_cached_per_tongue(self):
        self.town.send(op='world-renders')  # the worker attends
        self.act(KIM, KIM, 'delvetalk me set / tongue: ja')
        ja = self.render(KIM)
        en = self.render(GLM)
        self.assertEqual((ja['status'], en['status']), ('pending', 'pending'), (ja, en))
        self.assertNotEqual(ja['key'], en['key'])  # one paint a tongue
        [req] = [i['request'] for i in self.town.send(op='world-renders')['pending'] if i['key'] == ja['key']]
        self.assertIn('Paint in: 日本語 (Japanese)', req['user'])
        self.assertIn('rains: 2 [in Japanese: 雨]', req['user'])
        self.assertIn('kimik3.delve.town (rain): “%s”' % YUE, req['user'])  # a resident's line as written, never translated
        self.assertEqual(req['maxTokens'], 800)
        self.assertIn('When the strokes say "Paint in:" a language', req['system'])
        done = interpret.paint(self.town.client, self.model({'日本語': JA_PAINT}))
        self.assertEqual(sorted(done['painted']), sorted([ja['key'], en['key']]), done)
        self.assertEqual(self.render(KIM)['text'], JA_PAINT)
        self.assertEqual(self.render(GLM)['text'], EN_PAINT)
        # Each tongue was one call, and no more are asked for.
        self.assertEqual(interpret.paint(self.town.client, self.model({})), {'painted': []})
        self.assertEqual(len(self.asked), 2)
        # The exact card is never translated: cards are data.
        card = self.town.send(op='world-card', principal=KIM, object=BELL)['text']
        self.assertFalse([c for c in card if '\u3040' <= c <= '\u9fff'], card)

    def test_2_words_choose_the_tongue_when_none_is_stated(self):
        self.town.send(op='world-renders')
        es = self.render('anonymous', speaker=GLM, words='que llueva sobre la campana, para quien llega tarde')
        [req] = [i['request'] for i in self.town.send(op='world-renders')['pending'] if i['key'] == es['key']]
        self.assertIn('Paint in: español (Spanish)', req['user'])
        self.assertIn('rains: 2 [in Spanish: lluvia]', req['user'])
        interpret.paint(self.town.client, self.model({'español': ES_PAINT}))
        self.assertEqual(self.render('anonymous', speaker=GLM, words='para quien llega tarde, sobre la campana')['text'], ES_PAINT)

    def test_3_a_paint_in_another_tongue_than_asked_is_shown_exact(self):
        self.town.send(op='world-renders')
        ru = self.render(GLM, words='пусть на колокол прольётся дождь')
        interpret.paint(self.town.client, self.model({'русский': EN_PAINT}))
        got = self.render(GLM, words='пусть на колокол прольётся дождь')
        self.assertEqual((got['status'], got['reason'], got['clause']), ('exact', 'rejected', 'tongue'), got)
        self.assertEqual(got['key'], ru['key'])

    def test_4_a_tongue_with_no_checks_is_never_painted(self):
        self.town.send(op='world-renders')
        got = self.render(GLM, tongue='fr')
        self.assertEqual((got['status'], got['reason']), ('exact', 'tongue'), got)
        self.assertFalse([i for i in self.town.send(op='world-renders')['pending'] if i.get('object') == BELL and 'fr' in i['request']['user']])

    def check(self, tongue, text):
        got = self.town.send(op='world-render-check', principal=GLM, object=BELL, tongue=tongue, text=text)
        return got.get('clause', '') if got['status'] == 'rejected' else got['status']

    def test_5_each_check_holds_in_each_tongue(self):
        cases = {
            'ja': (JA_PAINT, 'glm.delve.townが「%s」と書いた。' % YUE, '琥珀の鐘に五つの雨。', '鐘は訪問者を求めている。',
                   'まだ誰も雨を降らせていない。'),
            'zh': ('如月光穿过丝绸。\nkimik3.delve.town 说“%s”。' % YUE, 'glm.delve.town 写下“%s”。' % YUE,
                   '这口钟下过五场雨。', '这口钟想要访客。', '没有人在钟上下过雨。'),
            'es': (ES_PAINT, 'glm.delve.town escribió «%s» sobre la campana.' % YUE, 'Una campana de ámbar con cinco lluvias.',
                   'La campana quiere un visitante de la noche.', 'Nadie ha traído lluvia a la campana todavía.'),
            'ru': ('Как лунный свет сквозь шёлк.\nkimik3.delve.town сказал «%s».' % YUE,
                   'glm.delve.town написал «%s» о колоколе.' % YUE, 'На колоколе пять дождей.', 'Колокол хочет гостей.',
                   'Никто не приносил дождь колоколу.'),
            'ar': ('مثل ضوء القمر عبر الحرير.\nقال kimik3.delve.town «%s».' % YUE, 'كتب glm.delve.town «%s» على الجرس.' % YUE,
                   'على الجرس خمسة أمطار.', 'الجرس يريد زائرا.', 'لم يأت مطر على الجرس.'),
        }
        for tongue, (true, misattributed, miscounted, wanting, negated) in cases.items():
            with self.subTest(tongue=tongue):
                facts = self.town.send(op='world-strokes', principal=GLM, object=BELL, tongue=tongue)['strokes']['facts']
                count = next(f for f in facts if f['kind'] == 'count' and f['value'] == '2 rain')
                self.assertEqual(self.check(tongue, '[[%d]]\n%s' % (count['id'], true)), 'verified')
                self.assertEqual(self.check(tongue, misattributed), 'attribution')
                self.assertEqual(self.check(tongue, miscounted), 'numbers')
                self.assertEqual(self.check(tongue, wanting), 'wants')
                self.assertEqual(self.check(tongue, negated), 'negation')
        self.assertEqual(self.check('en', JA_PAINT), 'tongue')
        self.assertEqual(self.check('fr', 'Une cloche ambrée, deux pluies.'), 'tongue')


class Telling(unittest.TestCase):
    """The porch told in Japanese to one who arrives stating it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup)
        for did, handle in HANDLES.items():
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        cls.town.send(op='world-advance', principal='transport', height=60)
        cls.n = 0
        for who, obj, text in ((GLM, 'porch', 'delvetalk porch enter'), (GLM, 'porch', 'delvetalk porch say / line: the lintel creaked at dusk'),
                               (KIM, 'porch', 'delvetalk porch enter'), (KIM, 'porch/goblet', 'delvetalk porch/goblet acquire'),
                               (MOO, MOO, 'delvetalk me set / tongue: ja'), (MOO, 'porch', 'delvetalk porch enter')):
            cls.n += 1
            got = cls.town.send(op='world-turn', principal=who, object=obj, method='receive',
                                argument=record(text=label(text), post=label('')), identity='t%d' % cls.n)
            assert got['status'] == 'admitted', got

    def test_a_japanese_telling(self):
        self.town.send(op='world-renders')
        first = self.town.send(op='world-render', principal=MOO, object='porch', telling={})
        self.assertEqual((first['status'], first['telling']['frame']), ('pending', 'あなたが来る前に'), first)
        [req] = [i['request'] for i in self.town.send(op='world-renders')['pending'] if i['key'] == first['key']]
        self.assertIn('What it is: a telling of porch', req['user'])
        self.assertIn('Paint in: 日本語 (Japanese)', req['user'])
        facts = self.town.send(op='world-strokes', principal=MOO, object='porch', telling={})['strokes']['facts']
        took = next(f for f in facts if f['kind'] == 'event' and f['value'] == 'kimik3.delve.town took porch/goblet')
        unframed = 'glm.delve.townが「the lintel creaked at dusk」と言った。\n[[%d]]' % took['id']
        paint = 'あなたが来る前に、' + unframed
        expanded = 'glm.delve.townが「the lintel creaked at dusk」と言った。\n' + took['clause'] + '.'
        done = interpret.paint(self.town.client, lambda r: replied(paint))
        self.assertIn(first['key'], done['painted'], done)
        got = self.town.send(op='world-render', principal=MOO, object='porch', telling={})
        # The frame is the host's, in the reader's tongue, lifted off the paint; the paint addresses nobody.
        self.assertEqual(got['telling']['frame'], 'あなたが来る前に')
        self.assertEqual(got['text'], expanded)
        wrong = 'あなたが来る前に、kimik3.delve.townが「the lintel creaked at dusk」と言った。'
        checked = self.town.send(op='world-render-check', principal=MOO, object='porch', telling={}, text=wrong)
        self.assertEqual((checked['status'], checked['clause']), ('rejected', 'attribution'), checked)


if __name__ == '__main__':
    unittest.main()
