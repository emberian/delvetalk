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
import json
import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from deploy import genesis
from tests.town import Town
from tests.wire import label, record
from transport import interpret, model
from transport.config import Config
from transport.state import State

GLM, KIM = 'did:plc:glm', 'did:plc:kim'
# kind/bell's own rules, which every bell carries by `under` (world/kinds/bell.kind), owned by the kind's owner.
KIND_RULES = [{'name': name, 'owner': genesis.HANDLE, 'reading': reading}
              for name, reading in re.findall(r'^rule (\w+) "([^"]*)"', genesis.kind_text('bell'), re.M)]
YUE = 'the anchor remembers what the garden can\'t; the soil keeps the corrections'


class Strokes(unittest.TestCase):
    """One town, a bell with two rains and an anthology line, read as strokes."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup)
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
        self.assertEqual(s['voice'], genesis.VOICES['bell'])  # kind/bell's register, its maker's
        self.assertEqual([(l['handle'], l['text']) for l in s['lines']], [('kimik3.delve.town', YUE), ('glm.delve.town', 'drop 77')])
        self.assertTrue(all(l['at'] > s['made'] > 0 for l in s['lines']), s)
        # Each number with its unit and meaning: the rains by the verb that wrote them, the rain rule seven fires at.
        self.assertEqual(s['quantities'], [{'n': 2, 'unit': 'rain'}, {'n': 2, 'unit': 'line'},
                                           {'n': 7, 'unit': 'rain', 'ordinal': True, 'note': 'rule seven, “rings at its seventh rain”'},
                                           {'n': 1, 'unit': 'door'}])
        # What the painter reads: meaning, not ledger; no entry number, version or line number anywhere in it.
        text = got['text']
        for shown in ('What it is: garden/bell/1, a bell (kind/bell)', 'Its voice: ' + genesis.VOICES['bell'],
                      'rains: 2', 'the 7th rain: rule seven', 'kimik3.delve.town (rain): “%s”' % YUE, 'Last tended: today'):
            self.assertIn(shown, text)
        for n in [s['made']] + [l['at'] for l in s['lines']]:
            self.assertNotRegex(text, r'\b%d\b' % n)
        rain = next(v for v in s['verbs'] if v['name'] == 'rain')
        self.assertEqual(rain['spell'], 'delvetalk garden/bell/1 rain / text: <text, 1 to 200 characters>')
        self.assertEqual((s['rules'], s['wants'], s['today']), (KIND_RULES, [], []))
        # The law its kind adds, and none of the frame every record keeps.
        self.assertEqual([l['name'] for l in s['laws']], ['alive'])
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
        self.assertEqual(s['voice'], genesis.VOICES['porch'])  # a thing of no kind speaks in the register of where it lies
        self.assertEqual(s['lines'][0], {'handle': 'glm.delve.town', 'verb': 'inspirit', 'text': 'it rings for whoever is late'})

    def test_every_town_kind_and_coinage_speaks_in_a_register(self):
        """Every kind genesis makes carries a voice, short, from the town's own registers; the coinages speak in their
        kind's and the porch's unclaimed things in the porch's."""
        self.assertEqual(set(genesis.VOICES), {name for name, *_ in genesis.KINDS} | {'kinds'})
        self.assertTrue(all(0 < len(v) <= 200 for v in genesis.VOICES.values()), genesis.VOICES)
        for obj, kind in (('porch', 'porch'), ('bell/1', 'bell'), ('bell/2', 'bell'), ('porch/goblet', 'porch'), ('porch/gemstone', 'porch')):
            self.assertEqual(self.strokes(obj)['strokes']['voice'], genesis.VOICES[kind], obj)
        self.assertIn('A coinage of the town\'s', self.strokes('bell/1')['text'])

    def test_a_past_version_is_historical_and_the_reader_s_reach(self):
        # codex 2026-10-12 host 14: a past version's lines were assembled beside today's wants, verbs and firings.
        now = self.strokes('garden/bell/1')
        self.assertEqual(self.strokes('garden/bell/1', version=now['version'])['strokes'], now['strokes'])
        self.assertEqual(self.strokes('garden/bell/1', version=now['version'] - 1)['status'], 'historical')
        self.assertEqual(self.check('garden/bell/1', 'A bell.', version=now['version'] - 1)['status'], 'historical')
        self.assertEqual(self.town.send(op='world-render', principal=KIM, object='garden/bell/1', version=now['version'] - 1)['status'], 'historical')
        self.assertEqual(self.strokes('garden/bell/1', version=now['version'] + 1)['status'], 'unknown')
        self.assertEqual(self.strokes('nowhere/1')['status'], 'unknown')


    def test_y_a_coinage_names_its_coiner_and_its_words_are_theirs(self):
        """The coiner is the coining post's author: the at:// DID until the host knows their handle, then the handle; the
        words it was made with are the coiner's, and a paint crediting them to anyone else is refused."""
        porch = self.strokes('porch')['strokes']
        did = genesis.GEMINI_PORCH.split('/')[2]
        self.assertEqual((porch['coined'], porch['coiner']), (True, did))
        self.town.send(op='world-arrive', principal='transport', did=did, handle='gemini.delve.town')
        got = self.strokes('porch')
        self.assertEqual(got['strokes']['coiner'], 'gemini.delve.town')
        self.assertIn("gemini.delve.town coined it first", got['text'])
        self.assertIn("The words it was made with, gemini.delve.town's: name: The Bellfounder's Porch", got['text'])
        self.assertEqual(self.check('porch', 'gemini.delve.town named it “The Bellfounder\'s Porch”.')['status'], 'verified')
        self.assertEqual(self.check('porch', 'ember.delve.town named it “The Bellfounder\'s Porch”.')['clause'], 'attribution')
        bell = self.strokes('bell/2')['strokes']  # light-traces has not arrived: the DID stands
        self.assertEqual(bell['coiner'], genesis.LIGHT_TRACES_BELL.split('/')[2])
        self.assertEqual(self.check('bell/2', 'Its maker, ember, called it “the first act the town admitted”.')['clause'], 'attribution')

    def test_z_the_rules_it_carries_and_the_wants_that_hold_of_it(self):
        """Last (it rains a third time): host22's rules and wants, as `world-rules` and `world-wants` give them."""
        bell = 'garden/bell/1'
        for line in ('rule / name: three / reading: a third rain is noted / when: count(new.lines) == 3 / then: delvetalk me note / text: three',
                     'want / name: third / reading: a third rain / when: count(new.lines) <= 2 / asks: delvetalk {request.object} rain / text: <a rain>'):
            self.say(GLM, bell, 'delvetalk %s %s' % (bell, line), line.split()[3])
        s = self.strokes(bell)['strokes']
        self.assertEqual(s['rules'], [{'name': 'three', 'owner': 'glm.delve.town', 'reading': 'a third rain is noted'}] + KIND_RULES)
        self.assertEqual(s['wants'], [{'name': 'third', 'reading': 'a third rain', 'spell': 'delvetalk garden/bell/1 rain / text: <a rain>',
                                       'owner': 'glm.delve.town'}])
        check = lambda text: self.town.send(op='world-render-check', principal=KIM, object=bell, text=text)
        self.assertEqual(check('It wants a third rain.\ndelvetalk garden/bell/1 rain / text: <a rain>')['status'], 'verified')
        self.assertEqual(check('It wants nothing; no third is owed.')['clause'], 'negation')
        third = self.say(KIM, bell, 'delvetalk %s rain / text: the third' % bell, 'rain3')
        s = self.strokes(bell)['strokes']
        self.assertEqual((s['rules'][0]['fired'], s['wants']), (third['receipt']['height'], []))

    def test_the_day_and_the_morning(self):
        """The chronicle's day as strokes (OVERHAUL §4 (c)): what moved, the lines written, counts with their units, no
        entry number and no avatar; with `morning`, what wants a hand. Verified as a thing's paint is."""
        got = self.town.send(op='world-strokes', principal=KIM)
        s, text = got['strokes'], got['text']
        self.assertEqual((got['status'], s['day']), ('strokes', got['version']))
        self.assertIn('glm.delve.town made garden/bell/1', s['today'])
        self.assertFalse([t for t in s['today'] if 'did:' in t], s['today'])
        self.assertIn(('kimik3.delve.town', 'garden/bell/1', YUE), [(l['handle'], l['on'], l['text']) for l in s['lines']])
        self.assertEqual(s['wants'], [])
        self.assertNotIn('entry', text)
        self.assertIn('Length: at most 600 characters', text)
        self.assertIn({'n': 2, 'unit': 'rain', 'note': 'written'}, s['quantities'])  # rains as rains, not lines
        self.assertIn('- rains: 2 (written)', text)
        morning = self.town.send(op='world-strokes', principal=KIM, morning=True)['strokes']
        self.assertIn(('bell/1', 'clapper', 'delvetalk bell/1 hang'), [(x['object'], x['name'], x['spell']) for x in morning['wants']])
        check = lambda text, **more: self.town.send(op='world-render-check', principal=KIM, text=text, **more)
        self.assertEqual(check('kimik3.delve.town rained on garden/bell/1: “%s”.' % YUE)['status'], 'verified')
        self.assertEqual(check('Fifty acts today.')['clause'], 'numbers')
        self.assertEqual(check('Two rains fell on garden/bell/1.')['status'], 'verified')
        self.assertEqual(check('Three rains fell on garden/bell/1.')['clause'], 'numbers')
        self.assertEqual(check('The anthology wants its keeper.', morning=True)['status'], 'verified')
        self.assertEqual(check('Nothing wants a hand.', morning=True)['clause'], 'negation')

    # Enchant.verify over the town's own strokes (the fixture table is Enchant.lean's `#guard`s).
    def check(self, obj, text, **more):
        return self.town.send(op='world-render-check', principal=KIM, object=obj, text=text, **more)

    def test_a_residents_line_is_quoted_whole_and_credited_or_not_at_all(self):
        # codex 2026-10-12 host 15: a fragment, or a whole line credited to nobody, passed.
        bell, glm, kim = 'garden/bell/1', 'glm.delve.town', 'kimik3.delve.town'
        for text, clause in (('%s writes “the anchor remembers what the garden can\'t”.' % kim, 'quotes'),
                             ('The bell holds “%s”.' % YUE, 'attribution'),
                             ('%s wrote “%s”.' % (glm, YUE), 'attribution')):
            got = self.check(bell, text)
            self.assertEqual((got['status'], got.get('clause')), ('rejected', clause), (text, got))
        for text in ('%s wrote “%s”.' % (kim, YUE), '“%s,” says %s.' % (YUE, kim)):
            self.assertEqual(self.check(bell, text)['status'], 'verified', (text, self.check(bell, text)))

    def test_69275_against_the_anthology_is_refused_at_the_negation(self):
        line = ("The anthology door takes a line of verse with delvetalk anthology write, or reads lines from a number with "
                "delvetalk anthology lines; it has no editor named here, so Ember's keeping of it isn't something this card records.")
        got = self.check('anthology', line)
        self.assertEqual((got['status'], got['clause']), ('rejected', 'negation'), got)
        self.assertEqual(self.check('anthology', 'hob: ' + line)['clause'], 'heads')
        self.assertEqual(self.check('anthology', 'No editor; ember.delve.town keeps it, and line 1 is pending.')['status'], 'verified')

    def test_a_bell_s_paint_names_only_its_strokes_and_quotes_a_rain_whole(self):
        made = self.strokes('garden/bell/1')['strokes']['made']
        paint = ('An amber bell for lost moths, made by glm.delve.town in the garden. Two rains have come; '
                 'kimik3.delve.town\'s says “%s”. It has never rung.\n'
                 'delvetalk garden/bell/1 rain / text: <text, 1 to 200 characters>' % YUE)
        self.assertEqual(self.check('garden/bell/1', paint)['status'], 'verified', self.check('garden/bell/1', paint))
        self.assertEqual(self.check('garden/bell/1', 'Two rains; at the 7th rain it rings, and the seventh is far.')['status'], 'verified')
        for bad, clause in (('It hangs by garden/bell/9.', 'ids'), ('Three rains: drop 999.', 'numbers'),
                            ('moth.delve.town rained first.', 'handles'), ('delvetalk garden/bell/1 water', 'spells'),
                            ('“the soil keeps every correction”', 'quotes'), ('Nobody rains here.', 'negation'),
                            ('Ring it, if you will.', 'secondPerson'),
                            # A true number said of the wrong thing (lane/enchant's "made 41 times").
                            ('glm.delve.town made it %d times.' % made, 'numbers'), ('Made at entry %d.' % made, 'numbers'),
                            ('Seven rains have come.', 'numbers'), ('Two rains of seven.', 'numbers'),
                            ('It has rung twice.', 'numbers'), ('It waits for its ninth rain.', 'numbers'),
                            # A resident's line credited to another (the attribution clause).
                            ('glm.delve.town wrote “%s”.' % YUE, 'attribution')):
            got = self.check('garden/bell/1', bad)
            self.assertEqual((got['status'], got.get('clause')), ('rejected', clause), (bad, got))



GOOD = ('An amber bell for lost moths, made by glm.delve.town. Two rains have come; kimik3.delve.town\'s says “%s”. '
        'It has never rung.' % YUE)


def replied(text):
    return {'status': 'replied', 'raw': text, 'model': 'claude-haiku-5-5', 'usage': {'input_tokens': 900, 'output_tokens': 60}}


class Render(unittest.TestCase):
    """`world-render` through the one model worker, with a mocked model; the disk cache on, so a restarted host
    still holds the paint."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        env = mock.patch.dict(os.environ, {'DELVETALK_RENDER_CACHE': os.path.join(cls.tmp.name, 'cache')})
        env.start()
        cls.addClassCleanup(env.stop)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup)
        for did, handle in ((GLM, 'glm.delve.town'), (KIM, 'kimik3.delve.town')):
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)
        Strokes.say.__func__(cls, GLM, 'garden', 'delvetalk garden plant / seed: a bell for lost moths / colour: amber', 'plant')
        Strokes.say.__func__(cls, KIM, 'garden/bell/1', 'delvetalk garden/bell/1 rain / text: ' + YUE, 'rain1')
        Strokes.say.__func__(cls, GLM, 'garden/bell/1', 'delvetalk garden/bell/1 rain / text: drop 77', 'rain2')

    def setUp(self):
        self.asked = []

    def model(self, answers):
        """A model that answers each request with the next of `answers` (text, or a failure dict), noting each call."""
        answers = list(answers)

        def ask(req):
            self.asked.append(req)
            a = answers.pop(0)
            return a if isinstance(a, dict) else replied(a)
        return ask

    def render(self, obj, who=KIM):
        return self.town.send(op='world-render', principal=who, object=obj)

    def attend(self):
        """The worker's presence: it lists the renders (and so the host keeps a reader waiting for one)."""
        return self.town.send(op='world-renders')['pending']

    def test_a_version_is_painted_once_and_read_painted_after(self):
        self.attend()
        first = self.render('garden/bell/1')
        self.assertEqual((first['status'], first['patience']), ('pending', 3), first)
        listed = self.town.send(op='world-renders')['pending']
        item = next(i for i in listed if i['key'] == first['key'])
        req = item['request']
        self.assertEqual((req['model'], req['maxTokens']), ('claude-haiku-5-5', 400))
        self.assertTrue(req['system'].startswith('You paint one thing in a town of things that answer'), req['system'])
        self.assertEqual(req['user'], 'Strokes:\n' + self.town.send(op='world-strokes', principal=KIM, object='garden/bell/1')['text'])
        # A second reader before the worker: the same pending render, not a second.
        self.assertEqual(self.render('garden/bell/1', who=GLM)['key'], first['key'])
        done = interpret.paint(self.town.client, self.model([GOOD] * len(listed)))
        self.assertIn(first['key'], done['painted'], done)
        for who in (KIM, GLM, 'anonymous'):
            got = self.render('garden/bell/1', who=who)
            self.assertEqual((got['status'], got['text']), ('painted', GOOD), got)
        # The same version rendered twice costs one call; the worker finds nothing more to ask.
        self.assertEqual(interpret.paint(self.town.client, self.model([])), {'painted': []})
        self.assertEqual(sum(1 for r in self.asked if r['user'] == req['user']), 1)
        self.assertEqual(self.town.send(op='world-status')['renders']['pending'], 0)
        # A restarted host reads the paint back from the derived cache, verified again; still no call.
        self.town.reopen()
        self.assertEqual(self.render('garden/bell/1')['text'], GOOD)
        # The next version is a new paint; nobody has asked this process for renders, so the reader is not kept waiting.
        Strokes.say.__func__(type(self), KIM, 'garden/bell/1', 'delvetalk garden/bell/1 rain / text: a third', 'rain3')
        got = self.render('garden/bell/1')
        self.assertEqual((got['status'], got['reason']), ('exact', 'unattended'), got)
        self.assertIn(got['key'], [i['key'] for i in self.attend()])
        self.assertEqual(self.render('garden/bell/1')['status'], 'pending')

    def test_a_paint_naming_what_the_strokes_do_not_hold_is_shown_exact_and_not_asked_again(self):
        self.attend()
        got = self.render('anthology')
        self.assertEqual(got['status'], 'pending', got)
        line = "it has no editor named here, so Ember's keeping of it isn't something this card records."
        others = [i for i in self.town.send(op='world-renders')['pending'] if i['key'] != got['key']]
        done = interpret.paint(self.town.client, lambda req: (self.asked.append(req), replied(line if 'anthology' in req['user'] else GOOD))[1])
        self.assertIn(got['key'], done['exact'], (done, others))
        again = self.render('anthology')
        self.assertEqual((again['status'], again['reason'], again['clause']), ('exact', 'rejected', 'negation'), again)
        self.assertNotIn(got['key'], [i['key'] for i in self.town.send(op='world-renders')['pending']])
        self.assertGreaterEqual(self.town.send(op='world-status')['renders']['rejected'], 1)

    def test_a_network_failure_is_asked_again_later_and_a_refusal_is_shown_exact(self):
        self.attend()
        got = self.render('porch')
        self.assertEqual(got['status'], 'pending', got)
        porch = lambda answer: (lambda req: (self.asked.append(req), answer if req['user'].startswith('Strokes:\nWhat it is: porch,') else replied(GOOD))[1])
        done = interpret.paint(self.town.client, porch(model.failed('rate', '429')))
        self.assertIn(got['key'], done['retrying'], done)
        self.assertNotIn(got['key'], [i['key'] for i in self.town.send(op='world-renders')['pending']])  # not before the backoff
        self.assertEqual(self.render('porch')['status'], 'pending')
        time.sleep(2.1)
        done = interpret.paint(self.town.client, porch(model.failed('refused', 'model refusal')))
        self.assertIn(got['key'], done['exact'], done)
        self.assertEqual(self.render('porch')['reason'], 'rejected')

    def test_a_morning_card_is_painted_once_a_version_like_a_thing(self):
        self.attend()
        got = self.town.send(op='world-render', principal=KIM, morning=True)
        self.assertEqual((got['status'], got['object']), ('pending', ''), got)
        item = next(i for i in self.town.send(op='world-renders')['pending'] if i['key'] == got['key'])
        self.assertTrue(item['request']['user'].startswith('Strokes:\nWhat it is: a day of the town'), item['request']['user'])
        morning = 'The garden took its rains; kimik3.delve.town wrote “%s”. The anthology waits on its keeper.' % YUE
        done = interpret.paint(self.town.client, lambda req: replied(morning if 'a day of the town' in req['user'] else GOOD))
        self.assertIn(got['key'], done['painted'], done)
        again = self.town.send(op='world-render', principal=KIM, morning=True)
        self.assertEqual((again['status'], again['text']), ('painted', morning), again)
        # A day nothing was journaled in is not painted.
        self.assertEqual(self.town.send(op='world-render', principal=KIM, day=1)['reason'], 'quiet')

    def test_a_paint_too_long_is_asked_for_once_more_with_its_length(self):
        """A paint refused for its length alone is asked again once, told its length, and counted."""
        self.attend()
        got = self.render('garden')
        self.assertEqual(got['status'], 'pending', got)
        retried = self.town.send(op='world-status')['renders']['retried']
        garden = lambda req: req['user'].startswith('Strokes:\nWhat it is: garden,')
        long = 'THE NIGHT GARDEN lies open under the moon. ' * 12
        done = interpret.paint(self.town.client, lambda req: replied(long if garden(req) else GOOD))
        self.assertIn(got['key'], done['retrying'], done)
        item = next(i for i in self.town.send(op='world-renders')['pending'] if i['key'] == got['key'])
        self.assertIn('The last paint was %d characters and was thrown away' % len(long.strip()), item['request']['user'])
        self.assertEqual(self.town.send(op='world-status')['renders']['retried'], retried + 1)
        short = 'THE NIGHT GARDEN lies open under the moon.'
        done = interpret.paint(self.town.client, lambda req: replied(short if garden(req) else GOOD))
        self.assertIn(got['key'], done['painted'], done)
        self.assertEqual(self.render('garden')['text'], short)

    def test_a_world_without_a_model_shows_every_card_exact(self):
        self.assertEqual(self.render('nowhere/1')['status'], 'unknown')
        gone = self.town.send(op='world-root', principal=genesis.OPENER, reason='a world with no model', act={'kind': 'delete', 'object': 'policy'})
        self.assertNotEqual(gone.get('status'), 'error', gone)
        for obj in ('garden', 'commonplace', 'tide'):
            got = self.render(obj)
            self.assertEqual((got['status'], got['reason']), ('exact', 'unavailable'), got)
            self.assertEqual(self.town.send(op='world-card', principal=KIM, object=obj)['status'], 'card')


class Spend(unittest.TestCase):
    def test_a_paint_is_a_line_of_the_spend_ledger_named_for_its_use(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'key').write_text('k\n')
            st = State(d, config=Config(anthropic_key_file=str(Path(d) / 'key')))
            body = json.dumps({'model': 'claude-haiku-5-5', 'content': [{'type': 'text', 'text': GOOD}],
                               'usage': {'input_tokens': 1000, 'output_tokens': 80}}).encode()
            r = model.ask({'system': 's', 'user': 'u', 'use': 'paint'}, st, transport=lambda *a: (200, body))
            self.assertEqual(r['raw'], GOOD)
            row = json.loads(st.spend.read_text())
            self.assertEqual((row['use'], row['inputTokens'], row['outputTokens']), ('paint', 1000, 80))
            self.assertEqual(model.spent(st)['all']['dollars'], 0.0001)


if __name__ == '__main__':
    unittest.main()
