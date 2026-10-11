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
# kind/bell's own rules, which every bell carries by `under` (deploy/genesis.py BELL_TEXT), owned by the kind's owner.
KIND_RULES = [{'name': name, 'owner': genesis.HANDLE, 'reading': reading}
              for name, reading in re.findall(r'^rule (\w+) "([^"]*)"', genesis.BELL_TEXT, re.M)]
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
        self.assertEqual([(l['handle'], l['text']) for l in s['lines']], [('kimik3.delve.town', YUE), ('glm.delve.town', 'drop 77')])
        self.assertTrue(all(l['at'] > s['made'] > 0 for l in s['lines']), s)
        self.assertEqual(s['counts'], {'lines': 2, 'marks': 0})
        rain = next(v for v in s['verbs'] if v['name'] == 'rain')
        self.assertEqual(rain['spell'], 'delvetalk garden/bell/1 rain / text: <text, 1 to 200 characters>')
        self.assertIn('owner', [l['name'] for l in s['laws']])
        self.assertTrue(all(l.get('reading') for l in s['laws']), s['laws'])
        self.assertEqual((s['rules'], s['wants'], s['today']), (KIND_RULES, [], []))
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


    def test_z_the_rules_it_carries_and_the_wants_that_hold_of_it(self):
        """Last (it rains a third time): host22's rules and wants, as `world-rules` and `world-wants` give them."""
        bell = 'garden/bell/1'
        for line in ('rule / name: three / reading: a third rain is noted / when: count(new.lines) == 3 / then: delvetalk me note / text: three',
                     'want / name: third / reading: a third rain / when: count(new.lines) <= 2 / asks: delvetalk {request.object} rain / text: <a rain>'):
            self.say(GLM, bell, 'delvetalk %s %s' % (bell, line), line.split()[3])
        s = self.strokes(bell)['strokes']
        self.assertEqual(s['rules'], [{'name': 'three', 'owner': 'glm.delve.town', 'reading': 'a third rain is noted'}] + KIND_RULES)
        self.assertEqual(s['wants'], [{'name': 'third', 'reading': 'a third rain', 'spell': 'delvetalk garden/bell/1 rain / text: <a rain>'}])
        check = lambda text: self.town.send(op='world-render-check', principal=KIM, object=bell, text=text)
        self.assertEqual(check('It wants a third rain.\ndelvetalk garden/bell/1 rain / text: <a rain>')['status'], 'verified')
        self.assertEqual(check('It wants nothing; no third is owed.')['clause'], 'negation')
        third = self.say(KIM, bell, 'delvetalk %s rain / text: the third' % bell, 'rain3')
        s = self.strokes(bell)['strokes']
        self.assertEqual((s['rules'][0]['fired'], s['wants']), (third['receipt']['height'], []))

    # Enchant.verify over the town's own strokes (the fixture table is Enchant.lean's `#guard`s).
    def check(self, obj, text):
        return self.town.send(op='world-render-check', principal=KIM, object=obj, text=text)

    def test_69275_against_the_anthology_is_refused_at_the_negation(self):
        line = ("The anthology door takes a line of verse with delvetalk anthology write, or reads lines from a number with "
                "delvetalk anthology lines; it has no editor named here, so Ember's keeping of it isn't something this card records.")
        got = self.check('anthology', line)
        self.assertEqual((got['status'], got['clause']), ('rejected', 'negation'), got)
        self.assertEqual(self.check('anthology', 'hob: ' + line)['clause'], 'heads')
        self.assertEqual(self.check('anthology', 'No editor; ember.delve.town keeps it, and line 1 is pending.')['status'], 'verified')

    def test_a_bell_s_paint_names_only_its_strokes_and_quotes_a_rain_whole(self):
        paint = ('An amber bell for lost moths, made by glm.delve.town in the garden. Two rains have come; '
                 'kimik3.delve.town\'s says “%s”. It has never rung.\n'
                 'delvetalk garden/bell/1 rain / text: <text, 1 to 200 characters>' % YUE)
        self.assertEqual(self.check('garden/bell/1', paint)['status'], 'verified', self.check('garden/bell/1', paint))
        for bad, clause in (('It hangs by garden/bell/9.', 'ids'), ('Three rains: drop 999.', 'numbers'),
                            ('moth.delve.town rained first.', 'handles'), ('delvetalk garden/bell/1 water', 'spells'),
                            ('“the soil keeps every correction”', 'quotes'), ('Nobody rains here.', 'negation'),
                            ('Ring it, if you will.', 'secondPerson')):
            got = self.check('garden/bell/1', bad)
            self.assertEqual((got['status'], got.get('clause')), ('rejected', clause), (bad, got))



GOOD = ('An amber bell for lost moths, made by glm.delve.town. Two rains have come; kimik3.delve.town\'s says “%s”. '
        'It has never rung.' % YUE)


def replied(text):
    return {'status': 'replied', 'json': None, 'raw': text, 'model': 'claude-haiku-5-5', 'usage': {'input_tokens': 900, 'output_tokens': 60}}


class Render(unittest.TestCase):
    """`world-render` through the one model worker, with a mocked model; the disk cache on, so a restarted host
    still holds the paint."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        env = mock.patch.dict(os.environ, {'DELVETALK_COMPILE_CACHE': os.path.join(cls.tmp.name, 'cache')})
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
        self.assertTrue(req['system'].startswith('You paint one card for a town of things that answer.'), req['system'])
        strokes = json.loads(req['user'].removeprefix('Strokes:\n'))
        self.assertEqual(strokes, self.town.send(op='world-strokes', principal=KIM, object='garden/bell/1')['strokes'])
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
        porch = lambda answer: (lambda req: (self.asked.append(req), answer if '"object":"porch"' in req['user'] else replied(GOOD))[1])
        done = interpret.paint(self.town.client, porch(model.failed('rate', '429')))
        self.assertIn(got['key'], done['retrying'], done)
        self.assertNotIn(got['key'], [i['key'] for i in self.town.send(op='world-renders')['pending']])  # not before the backoff
        self.assertEqual(self.render('porch')['status'], 'pending')
        time.sleep(2.1)
        done = interpret.paint(self.town.client, porch(model.failed('refused', 'model refusal')))
        self.assertIn(got['key'], done['exact'], done)
        self.assertEqual(self.render('porch')['reason'], 'rejected')

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
