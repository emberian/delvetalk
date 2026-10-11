"""Inspiriting (docs/previews/pingwaves.txt #5): genesis lays three unclaimed THINGs on the porch, the goblet, the
ring and the gemstone; anyone inspirits one once with `inspirit / surrounding:`, which becomes what surrounds it, and
they its keeper; the porch has the line. A second inspiriting is refused by the law's `keeper`, and after it the
keeper alone redescribes it.

Evidence for FOUNDATION §8 law (layer: objects). Refuted by: a thing that takes a second keeper; a porch with no
line; an unclaimed thing the porch card does not offer; a keeper's lens open to the owner after inspiriting.
"""
import tempfile
import unittest

from deploy import genesis
from tests.town import Town
from tests.wire import label, record

GLM, KIM = 'did:plc:glm', 'did:plc:kim'


class Inspirit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name)
        cls.addClassCleanup(cls.town.close)
        for did, handle in ((GLM, 'glm.delve.town'), (KIM, 'kimik3.delve.town')):
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)

    def say(self, who, obj, text, ident):
        got = self.town.send(op='world-turn', principal=who, object=obj, method='receive',
                             argument=record(text=label(text), post=label('at://x/p/' + ident)), identity=ident)
        self.assertEqual(got['status'], 'admitted', got)
        return got

    def card(self, obj, who=GLM):
        return self.town.send(op='world-card', principal=who, object=obj)['text']

    def view(self, obj):
        got = self.town.send(op='world-view', principal=genesis.OPENER, object=obj)
        return {f['name']: f['value'] for f in got['state']['fields']}

    # Unittest runs these in name order: the porch is read whole before the ring is inspirited below.
    def test_a_porch_offers_its_unclaimed_things_and_one_is_inspirited_once(self):
        porch = self.card('porch')
        self.assertIn('Unclaimed here: porch/ring, porch/goblet, porch/gemstone. Inspirit one: delvetalk porch/ring inspirit / surrounding: <1 to 400 characters>\n', porch)
        goblet = self.card('porch/goblet')
        self.assertEqual(goblet, 'a goblet that is always full of something — unclaimed, lying in porch.\n'
                                 'Inspirit it: delvetalk porch/goblet inspirit / surrounding: <1 to 400 characters>\n'
                                 '» your words become what surrounds it, and you its keeper; once.\n')
        words = 'it holds whatever the last guest left unsaid'
        done = self.say(GLM, 'porch/goblet', 'delvetalk porch/goblet inspirit / surrounding: ' + words, 'g1')
        self.assertEqual(done['result']['label'], 'done', done)
        self.assertEqual(done['offers'][-1]['text'], 'Inspirited, glm.delve.town: you keep it.\n\n'
                         'a goblet that is always full of something, kept by glm.delve.town (yours), lying in porch.\n' + words + '\n'
                         'Lend its setting: delvetalk porch/goblet lend / to: <a handle, or me> / method: set / until: +<clock minutes>\n')
        state = self.view('porch/goblet')
        self.assertEqual((state['keeper']['value'], state['description']['value']), (GLM, words))
        porch = self.card('porch', KIM)
        self.assertIn('a goblet that is always full of something, inspirited by glm.delve.town: ' + words, porch)
        self.assertIn('Unclaimed here: porch/ring, porch/gemstone. ', porch)
        self.assertIn('Lying here: porch/goblet\n', porch)
        # A second resident's inspiriting is refused by name, and the law refuses the same write by `keeper`.
        again = self.say(KIM, 'porch/goblet', 'delvetalk porch/goblet inspirit / surrounding: mine now', 'g2')
        self.assertEqual((again['result']['label'], again['offers'][-1]['text']),
                         ('refused', 'refused keeper: Inspirited already, by glm.delve.town, who keeps it\n'), again)
        self.assertNotIn('inspirit', self.town.send(op='world-inspect', principal=KIM, object='porch/goblet')['offered'])
        # The keeper redescribes it; the owner, who made it, no longer may.
        kept = self.say(GLM, 'porch/goblet', 'delvetalk porch/goblet set\ndescription: it is empty only when nobody looks', 'g3')
        self.assertEqual(kept['result']['label'], 'done', kept)
        owner = self.town.send(op='world-turn', principal=genesis.OPENER, object='porch/goblet', method='receive', identity='g4',
                               argument=record(text=label('delvetalk porch/goblet set\ndescription: a plain cup'), post=label('at://x/p/g4')))
        self.assertEqual((owner['status'], owner['receipt']['outcome'].get('clause')), ('refused', 'owner'), owner)
        self.assertEqual(self.view('porch/goblet')['description']['value'], 'it is empty only when nobody looks')

    def test_the_law_refuses_a_second_keeper_whatever_the_code_says(self):
        """`law keeper`: writeOnce, and only the one who inspirits it is written as its keeper."""
        laws = {l['name']: l for l in self.town.send(op='world-inspect', principal=KIM, object='porch/ring')['laws']}
        self.assertIn('writeOnce(keeper)', str(laws['keeper']))
        first = self.say(KIM, 'porch/ring', 'delvetalk porch/ring inspirit / surrounding: a ring for a hand that went west', 'r1')
        self.assertEqual(first['result']['label'], 'done', first)
        version = self.town.send(op='world-view', principal=GLM, object='porch/ring')['version']
        proposed = self.town.send(op='world-propose', principal=GLM, identity='r2', roots=[{'object': 'porch/ring', 'version': version}],
                                  writes=[{'object': 'porch/ring', 'edits': {'tag': 'record', 'fields': [
                                      {'name': 'keeper', 'value': {'tag': 'variant', 'label': 'set', 'payload': record(value=label(GLM))}}]}}])
        self.assertEqual((proposed['status'], proposed['receipt']['outcome']['class']), ('refused', 'lawRefused'), proposed)
        self.assertEqual(self.view('porch/ring')['keeper']['value'], KIM)

    def test_the_law_a_circle_amends_is_the_packages_own(self):
        """Thing.lawText() (what naming a circle amends from) has the clauses and readings its package declares."""
        import re
        from tests.test_objects import run_pure
        text = run_pure("Thing", "lawText")["value"]["value"]
        declared = [(l['name'], l.get('reading')) for l in self.town.send(op='world-inspect', principal=KIM, object='porch/gemstone', source=False)['laws'] if not l.get('host')]
        self.assertEqual(re.findall(r'^law (\w+) "([^"]*)":', text, re.M), declared)

    def test_hob_is_told_the_word_and_shown_an_inspiriting(self):
        policy = self.view('policy')
        self.assertIn('surrounding', str(policy['lexicon']))
        self.assertIn('porch/goblet inspirit', str(policy['examples']))


if __name__ == '__main__':
    unittest.main()
