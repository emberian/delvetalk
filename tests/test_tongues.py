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
import json
import os
import re
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


CODES = {'English': 'en', 'Japanese': 'ja', 'Chinese': 'zh', 'Spanish': 'es', 'Russian': 'ru', 'Arabic': 'ar'}
PAINT_OBEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'world', 'lib', 'Paint.obend')


def contract_examples(kind, facts):
    """Instantiate each worked example's numbered facts against the fixture's matching structured facts."""
    out = []
    with open(PAINT_OBEND, encoding='utf-8') as f:
        contract = json.loads(f.read().split('def contract() -> String:\n', 1)[1].strip())
    for part in contract.split('\n\n'):
        m = re.fullmatch(r'(%s), a %s\. Strokes: (.+)\nPaint:\n(.+)' % ('|'.join(CODES), kind), part, re.S)
        if not m:
            continue
        bound = {}
        for row in m[2].split('\nFacts:\n', 1)[1].split('\n'):
            fact_row = re.fullmatch(r'- (\d+): (\w+); ([^;]+); ([^;]+); clause: (.+)', row)
            if not fact_row:
                raise AssertionError((kind, m[1], row))
            fact = dict(zip(('kind', 'subject', 'value', 'clause'), fact_row.groups()[1:]))
            matches = [f for f in facts if all(f[k] == fact[k] for k in ('kind', 'subject', 'value', 'clause'))]
            if len(matches) != 1:
                raise AssertionError((kind, m[1], fact, facts))
            bound[int(fact_row[1])] = matches[0]
        source, rendered = [], []
        cited = set()
        for line in m[3].split('\n'):
            ids = re.fullmatch(r'\[\[([0-9,]+)\]\]', line)
            if ids:
                selected = [bound[int(n)] for n in ids[1].split(',')]
                cited.update(int(n) for n in ids[1].split(','))
                source.append('[[%s]]' % ','.join(str(f['id']) for f in selected))
                rendered.append('; '.join(f['clause'] for f in selected) + '.')
            else:
                source.append(line)
                rendered.append(line)
        if cited != set(bound):
            raise AssertionError((kind, m[1], cited, bound))
        out.append((CODES[m[1]], '\n'.join(source), '\n'.join(rendered)))
    return out


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


AR_PAINT = '[[{rain}]]\nمثل ضوء القمر عبر الحرير.\nقال kimik3.delve.town «%s».' % YUE
JA_PAINT = '[[{rain}]]\nまるで月光の絹。\nkimik3.delve.townが「%s」と言った。' % YUE
ES_PAINT = '[[{rain}]]\nComo seda bajo la luna.\nkimik3.delve.town dijo «%s».' % YUE
EN_PAINT = '[[{rain}]]\nLike moonlight through silk.\nkimik3.delve.town said “%s”.' % YUE


def expanded_paint(template):
    return template.replace('[[{rain}]]', '2 rains.')


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
                    return replied(self.source(text, req))
            return replied(self.source(by_tongue.get('English', EN_PAINT), req))
        return ask

    def render(self, who, **more):
        return self.town.send(op='world-render', principal=who, object=BELL, **more)

    def source(self, template, req=None):
        if '{rain}' not in template:
            return template
        if req is None:
            facts = self.town.send(op='world-strokes', principal=GLM, object=BELL)['strokes']['facts']
            count = next(f for f in facts if f['kind'] == 'count' and f['value'] == '2 rain')
            return template.format(rain=count['id'])
        count = re.search(r'^- (\d+): count; %s; 2 rain; clause: 2 rains$' % BELL, req['user'], re.M)
        self.assertIsNotNone(count, req['user'])
        return template.format(rain=count[1])

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
        self.assertIn('kimik3.delve.town (rain): 「%s」' % YUE, req['user'])  # a resident's line as written, never translated, in the marks a paint in it writes
        self.assertEqual(req['maxTokens'], 800)
        self.assertIn('When the strokes say "Paint in:" a language', req['system'])
        done = interpret.paint(self.town.client, self.model({'日本語': JA_PAINT}))
        self.assertEqual(sorted(done['painted']), sorted([ja['key'], en['key']]), done)
        self.assertEqual(self.render(KIM)['text'], expanded_paint(JA_PAINT))
        self.assertEqual(self.render(GLM)['text'], expanded_paint(EN_PAINT))
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
        self.assertEqual(self.render('anonymous', speaker=GLM, words='para quien llega tarde, sobre la campana')['text'], expanded_paint(ES_PAINT))

    def test_3_a_paint_in_another_tongue_than_asked_is_shown_exact(self):
        self.town.send(op='world-renders')
        ru = self.render(GLM, words='пусть на колокол прольётся дождь')
        # A refusal in another tongue is asked once more; the painter, still in English, is refused for good.
        self.assertEqual(interpret.paint(self.town.client, self.model({'русский': EN_PAINT}))['retrying'], [ru['key']])
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
        got = self.town.send(op='world-render-check', principal=GLM, object=BELL, tongue=tongue, text=self.source(text))
        return got.get('clause', '') if got['status'] == 'rejected' else got['status']

    def test_5_each_check_holds_in_each_tongue(self):
        cases = {
            'ja': (JA_PAINT, 'glm.delve.townが「%s」と書いた。' % YUE, '琥珀の鐘に五つの雨。', '鐘は訪問者を求めている。',
                   'まだ誰も雨を降らせていない。'),
            'zh': ('[[{rain}]]\n如月光穿过丝绸。\nkimik3.delve.town 说“%s”。' % YUE, 'glm.delve.town 写下“%s”。' % YUE,
                   '这口钟下过五场雨。', '这口钟想要访客。', '没有人在钟上下过雨。'),
            'es': (ES_PAINT, 'glm.delve.town escribió «%s» sobre la campana.' % YUE, 'Una campana de ámbar con cinco lluvias.',
                   'La campana quiere un visitante de la noche.', 'Nadie ha traído lluvia a la campana todavía.'),
            'ru': ('[[{rain}]]\nКак лунный свет сквозь шёлк.\nkimik3.delve.town сказал «%s».' % YUE,
                   'glm.delve.town написал «%s» о колоколе.' % YUE, 'На колоколе пять дождей.', 'Колокол хочет гостей.',
                   'Никто не приносил дождь колоколу.'),
            'ar': (AR_PAINT, 'كتب glm.delve.town «%s» على الجرس.' % YUE,
                   'على الجرس خمسة أمطار.', 'الجرس يريد زائرا.', 'لم يأت مطر على الجرس.'),
        }
        for tongue, (true, misattributed, miscounted, wanting, negated) in cases.items():
            with self.subTest(tongue=tongue):
                self.assertEqual(self.check(tongue, true), 'verified')
                self.assertEqual(self.check(tongue, misattributed), 'attribution')
                self.assertEqual(self.check(tongue, miscounted), 'numbers')
                self.assertEqual(self.check(tongue, wanting), 'wants')
                self.assertEqual(self.check(tongue, negated), 'negation')
        self.assertEqual(self.check('en', JA_PAINT), 'tongue')
        self.assertEqual(self.check('fr', 'Une cloche ambrée, deux pluies.'), 'tongue')


    def test_6_the_contracts_thing_examples_are_true_paints_of_the_real_strokes(self):
        facts = self.town.send(op='world-strokes', principal=GLM, object=BELL)['strokes']['facts']
        examples = contract_examples('thing', facts)
        self.assertEqual(sorted(t for t, _, _ in examples), ['ar', 'en', 'es', 'ja', 'ru', 'zh'])
        for tongue, paint, expanded in examples:
            with self.subTest(tongue=tongue):
                got = self.town.send(op='world-render-check', principal=GLM, object=BELL, tongue=tongue, text=paint)
                self.assertEqual((got['status'], got.get('text')), ('verified', expanded), got)

    def test_7_a_refusal_in_another_tongue_is_asked_once_more_with_its_reason(self):
        self.town.send(op='world-renders')
        ar = self.render(GLM, tongue='ar')
        asked = []
        replies = [replied('الجرس يريد زائرا.'), replied(self.source(AR_PAINT))]

        def ask(req):
            asked.append(req)
            return replies[len(asked) - 1]
        before = self.town.send(op='world-status')['renders']['retried']
        done = interpret.paint(self.town.client, ask)
        self.assertEqual({k: v for k, v in done.items() if k != 'verdicts'}, {'painted': [], 'retrying': [ar['key']]})
        self.assertEqual([v['clause'] for v in done['verdicts']], ['wants'], done)
        self.assertEqual(self.town.send(op='world-status')['renders']['retried'], before + 1)
        self.assertEqual(self.render(GLM, tongue='ar')['status'], 'pending')
        self.assertEqual(interpret.paint(self.town.client, ask), {'painted': [ar['key']]})
        # The second ask is the first with the refused clause, its reason and the refused paint, in plain words.
        first, second = asked
        self.assertEqual(first['system'], second['system'])
        self.assertTrue(second['user'].startswith(first['user'] + '\n\nThe last paint was thrown away whole: it claimed a want ('), second['user'])
        self.assertIn('the strokes hold no want', second['user'])
        self.assertIn('in Arabic', second['user'])
        self.assertTrue(second['user'].endswith('(the paint was: الجرس يريد زائرا.)'), second['user'])
        self.assertEqual(self.render(GLM, tongue='ar')['text'], expanded_paint(AR_PAINT))
        self.assertEqual(interpret.paint(self.town.client, ask), {'painted': []})  # painted: no third ask
        self.assertEqual(len(asked), 2)

    def test_8_a_second_refusal_is_final_and_asks_no_more(self):
        self.town.send(op='world-renders')
        zh = self.render(GLM, tongue='zh')
        asked = []
        replies = [replied('这口钟下过五场雨。'), replied('这口钟想要访客。')]

        def ask(req):
            asked.append(req)
            return replies[len(asked) - 1]
        done = interpret.paint(self.town.client, ask)
        self.assertEqual({k: v for k, v in done.items() if k != 'verdicts'}, {'painted': [], 'retrying': [zh['key']]})
        done = interpret.paint(self.town.client, ask)
        self.assertEqual({k: v for k, v in done.items() if k != 'verdicts'}, {'painted': [], 'exact': [zh['key']]})
        self.assertEqual([(v['status'], v['clause']) for v in done['verdicts']], [('exact', 'wants')], done)
        self.assertIn('a number was wrong (', asked[1]['user'])
        self.assertIn('in Chinese', asked[1]['user'])
        got = self.render(GLM, tongue='zh')
        self.assertEqual((got['status'], got['reason'], got['clause']), ('exact', 'rejected', 'wants'), got)
        self.assertEqual(interpret.paint(self.town.client, ask), {'painted': []})
        self.assertEqual(len(asked), 2)


class ExcerptPaint(Tongued):
    """Refuted by a stitched line passing, a lost credit, or an ellipsis changing any tongue's checks."""

    frames = {
        'en': '%s said “%s”.',
        'es': '%s dijo «%s».\nComo seda bajo la luna.',
        'ru': '%s сказал «%s».',
        'ar': 'قال %s «%s».',
        'ja': '%sが「%s」と言った。',
        'zh': '%s 说“%s”。',
    }

    def check(self, tongue, text):
        return self.town.send(op='world-render-check', principal=GLM, object=BELL, tongue=tongue, text=text)

    def test_excerpts_keep_their_author_in_every_tongue_through_render_submit(self):
        good = ('…the soil keeps the corrections', 'the anchor remembers…',
                'the anchor … the corrections', '… anchor … corrections …')
        bad = ('the anchor remembers', 'the corrections … the anchor',
               'the anchor remembers … remembers what', 'the anchor … garden … corrections',
               'the anchor … drop 77', 'the anchor … corr ections',
               'the anchor ... corrections', 'the anchor remembers...',
               '…', '… …', 'the anchor … … corrections')
        self.town.send(op='world-renders')
        for tongue, frame in self.frames.items():
            with self.subTest(tongue=tongue):
                for excerpt in good:
                    paint = frame % (HANDLES[KIM], excerpt)
                    got = self.check(tongue, paint)
                    self.assertEqual((got['status'], got.get('text')), ('verified', paint), got)
                for excerpt in bad:
                    got = self.check(tongue, frame % (HANDLES[KIM], excerpt))
                    self.assertEqual((got['status'], got.get('clause')), ('rejected', 'quotes'), got)
                for author in (HANDLES[GLM], ''):
                    got = self.check(tongue, frame % (author, good[2]))
                    self.assertEqual((got['status'], got.get('clause')), ('rejected', 'attribution'), got)

                queued = self.town.send(op='world-render', principal=GLM, object=BELL, tongue=tongue)
                self.assertEqual(queued['status'], 'pending', queued)
                # Mocked model replies go verbatim through the real host, including its one reasoned retry.
                refused = self.town.send(op='world-render-submit', key=queued['key'],
                                         reply=replied(frame % (HANDLES[KIM], 'the anchor … drop 77')))
                self.assertEqual((refused['status'], refused.get('clause')), ('retrying', 'quotes'), refused)
                retry = next(i['request'] for i in self.town.send(op='world-renders')['pending']
                             if i['key'] == queued['key'])
                self.assertIn('U+2026, never three ASCII dots', retry['user'])
                paint = frame % (HANDLES[KIM], good[2])
                fixed = self.town.send(op='world-render-submit', key=queued['key'], reply=replied(paint))
                self.assertEqual((fixed['status'], fixed.get('text')), ('painted', paint), fixed)
                cached = self.town.send(op='world-render', principal=GLM, object=BELL, tongue=tongue)
                self.assertEqual((cached['status'], cached.get('text')), ('painted', paint), cached)

    def test_maximum_length_excerpts_count_the_marker_as_a_character(self):
        self.act(KIM, BELL, 'delvetalk garden/bell/1 rain / text: ' + 'x' * 200)
        frame = self.frames['en']
        first = frame % (HANDLES[KIM], 'x' * 180 + '…')
        room = 400 - len(first) - 1 - len(frame % (HANDLES[KIM], '…'))
        self.assertTrue(0 < room < 200, room)
        paint = first + '\n' + frame % (HANDLES[KIM], '…' + 'x' * room)
        self.assertEqual(len(paint), 400)
        got = self.check('en', paint)
        self.assertEqual((got['status'], got.get('text')), ('verified', paint), got)
        longer = first + '\n' + frame % (HANDLES[KIM], '…' + 'x' * (room + 1))
        got = self.check('en', longer)
        self.assertEqual((got['status'], got.get('clause')), ('rejected', 'length'), got)

    def test_native_script_pieces_remain_quoted_with_adjacent_ellipsis(self):
        cases = {
            'en': ('I remember 999 moons; you remember none', 'I remember 999…you'),
            'es': ('Yo recuerdo 999 lunas; tú no recuerdas ninguna', 'Yo recuerdo 999…tú'),
            'ru': ('Я помню 999 лун; ты не помнишь ни одной', 'Я помню 999…ты'),
            'ar': ('أنا أتذكر ٩٩٩ قمرا وأنت لا تتذكر شيئا', 'أنا أتذكر ٩٩٩…أنت'),
            'ja': ('私は九百九十九の月を覚えているが、あなたは覚えていない', '私は九百九十九…あなた'),
            'zh': ('我记得九百九十九个月亮，你不记得任何一个', '我记得九百九十九…你'),
        }
        for tongue, (line, excerpt) in cases.items():
            with self.subTest(tongue=tongue):
                self.act(KIM, BELL, 'delvetalk garden/bell/1 rain / text: ' + line)
                # Numbers, negation and first/second person stay inside the quotation, as for a whole line.
                for quote in (line, excerpt, '…' + excerpt + '…'):
                    paint = self.frames[tongue] % (HANDLES[KIM], quote)
                    got = self.check(tongue, paint)
                    self.assertEqual((got['status'], got.get('text')), ('verified', paint), got)


class NumericPaint(Tongued):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.act(GLM, BELL, 'delvetalk garden/bell/1 rain / text: a third drop')
        cls.act(GLM, BELL, 'delvetalk garden/bell/1 rain / text: a fourth drop')

    def check(self, tongue, text):
        return self.town.send(op='world-render-check', principal=GLM, object=BELL, tongue=tongue, text=text)

    def test_a_numeric_token_is_rejected_whole_instead_of_counting_its_digit_prefix(self):
        for token in ('4,000', '4.000', '4.5', '.4', '4x', 'x4', '4th5', '4 000', '4 0', '٤٫٥', '۴٬۰۰۰', '4' + 'x' * 390):
            with self.subTest(token=token):
                got = self.check('en', token + ' rains.')
                self.assertEqual((got['status'], got.get('clause')), ('rejected', 'numbers'), got)

    def test_digits_and_each_tongues_ordinal_marks_still_reach_the_prose_check(self):
        for tongue, text in (('en', '4 rains.'), ('en', '４ rains.'), ('en', '٤ rains.'), ('en', '۴ rains.'),
                             ('en', 'At the 7th rain.'), ('es', 'La campana espera la 7.ª lluvia.'),
                             ('ru', 'На 7-й дождь.'), ('ar', 'على الجرس ٤ أمطار.'),
                             ('ar', 'على الجرس أربعة أمطار.'), ('ja', '鐘に四つの雨。'),
                             ('ja', '鐘に４つの雨。'), ('zh', '钟下过四场雨。')):
            with self.subTest(tongue=tongue, text=text):
                got = self.check(tongue, text)
                self.assertEqual((got['status'], got.get('clause')), ('rejected', 'imagery'), got)

    def test_an_unspaced_numeric_token_does_not_split_a_decimal_or_malformed_suffix_into_counts(self):
        for tongue, frame in (('ja', '鐘に%sつの雨。'), ('zh', '钟下过%s场雨。')):
            for token in ('4,000', '4.5', '.4', '4x', 'x4', '４．５', '四.五', '٤٫٥', '4 0'):
                with self.subTest(tongue=tongue, token=token):
                    got = self.check(tongue, frame % token)
                    self.assertEqual((got['status'], got.get('clause')), ('rejected', 'numbers'), got)


class CitationRetry(Tongued):
    render = Paint.render
    source = Paint.source

    def test_citation_and_imagery_refusals_have_one_reasoned_retry_in_the_requested_tongue(self):
        self.town.send(op='world-renders')
        for tongue, language, bad, clause, remedy, template in (
                ('ja', 'Japanese', '[[999]]', 'facts', 'use only ids from this paint', JA_PAINT),
                ('es', 'Spanish', 'La campana es cálida.', 'imagery', 'simile fragment', ES_PAINT)):
            with self.subTest(tongue=tongue):
                queued = self.render(GLM, tongue=tongue)
                self.assertEqual(queued['status'], 'pending', queued)
                original = next(i['request'] for i in self.town.send(op='world-renders')['pending'] if i['key'] == queued['key'])
                count = self.town.send(op='world-status')['renders']['retried']
                refused = self.town.send(op='world-render-submit', key=queued['key'], reply=replied(bad))
                self.assertEqual((refused['status'], refused.get('clause')), ('retrying', clause), refused)
                self.assertEqual(self.town.send(op='world-status')['renders']['retried'], count + 1)
                retry = next(i['request'] for i in self.town.send(op='world-renders')['pending'] if i['key'] == queued['key'])
                self.assertEqual(retry['system'], original['system'])
                self.assertTrue(retry['user'].startswith(original['user'] + '\n\n'), retry['user'])
                for reason in (clause, refused['detail'], remedy, '[[id,...]]', 'in ' + language):
                    self.assertIn(reason, retry['user'])
                self.assertTrue(retry['user'].endswith('(the paint was: %s)' % bad), retry['user'])
                fixed = self.town.send(op='world-render-submit', key=queued['key'], reply=replied(self.source(template, retry)))
                self.assertEqual((fixed['status'], fixed.get('text')), ('painted', expanded_paint(template)), fixed)
                self.assertEqual(self.render(GLM, tongue=tongue)['text'], expanded_paint(template))
                self.assertFalse([i for i in self.town.send(op='world-renders')['pending'] if i['key'] == queued['key']])


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

    def test_the_contracts_before_arrival_examples_are_true_paints_of_the_real_strokes(self):
        facts = self.town.send(op='world-strokes', principal=MOO, object='porch', telling={})['strokes']['facts']
        examples = contract_examples('telling before arrival', facts)
        self.assertEqual(sorted(t for t, _, _ in examples), ['ar', 'en', 'es', 'ja', 'ru', 'zh'])
        for tongue, paint, expanded in examples:
            with self.subTest(tongue=tongue):
                got = self.town.send(op='world-render-check', principal=MOO, object='porch', telling={}, tongue=tongue, text=paint)
                self.assertEqual((got['status'], got.get('text')), ('verified', expanded), got)

    def test_a_spanish_plural_in_e_is_its_unit(self):
        for count, clause in (('dos', 'imagery'), ('tres', 'numbers')):
            got = self.town.send(op='world-render-check', principal=MOO, object='porch', telling={}, tongue='es',
                                 text='El pueblo dejó porch/goblet sobre la pizarra. %s visitantes llegaron al umbral.' % count.capitalize())
            self.assertEqual((got['status'], got.get('clause')), ('rejected', clause), got)
        facts = self.town.send(op='world-strokes', principal=MOO, object='porch', telling={})['strokes']['facts']
        visitors = next(f for f in facts if f['kind'] == 'count' and f['value'] == '2 visitor')
        got = self.town.send(op='world-render-check', principal=MOO, object='porch', telling={}, tongue='es',
                             text='[[%d]]\nComo seda bajo la luna.' % visitors['id'])
        self.assertEqual((got['status'], got.get('text')), ('verified', '2 visitors.\nComo seda bajo la luna.'), got)

    def test_a_japanese_telling(self):
        self.town.send(op='world-renders')
        first = self.town.send(op='world-render', principal=MOO, object='porch', telling={})
        self.assertEqual((first['status'], first['telling']['frame']), ('pending', 'あなたが来る前に'), first)
        [req] = [i['request'] for i in self.town.send(op='world-renders')['pending'] if i['key'] == first['key']]
        self.assertIn('What it is: a telling of porch', req['user'])
        self.assertIn('Paint in: 日本語 (Japanese)', req['user'])
        self.assertIn('Frame: the page prints あなたが来る前に above the paint', req['user'])
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


class ContractHandles(unittest.TestCase):
    """obend 10-14: the painter wrote `yue.delve.town` and `claude.delve.town` on a town whose handles are bare guest names
    (`yue`), refused at the handles clause, because every handle the contract showed it had a `.delve.town` domain. The
    contract says a handle keeps the shape the strokes give it, and its quotation examples outside the worked examples
    (which are bound to a delve.town fixture) show a bare one."""

    def test_the_contract_keeps_a_handles_shape(self):
        with open(PAINT_OBEND, encoding='utf-8') as f:
            contract = json.loads(f.read().split('def contract() -> String:\n', 1)[1].strip())
        rules = contract.split('\n\nWorked examples', 1)[0]
        self.assertIn('a bare name such as yue stays bare: never add a domain such as .delve.town, nor drop one', rules)
        framed = re.findall(r'(\S+) said “', rules)
        self.assertTrue(framed)
        self.assertEqual([h for h in framed if '.' in h], [], framed)
