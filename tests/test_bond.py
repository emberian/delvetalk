"""BOND by spell, and a THING's circle, lend and `me` (docs/METAPHYSICS.md §7.4: bind, hold, lend).

Evidence for FOUNDATION §8 governance (layer: objects). `kind/bond make / parties / terms / amends / law`
makes a bond; each party countersigns once (a mark whose `who` is the signer), the last puts it at rest and
applies its amendment under the amended object's own law; a party withdraws before rest. At rest its signers
are a circle: a thing's owner names it (`set / circle:`) and the thing amends its own law so they set it as
its keeper does. A keeper lends `set` by the host's `lend`, and the law, not the code, admits the borrower.
An offer tells the one offered the spell that takes it: `delvetalk me accept`.
Refuted by: a stranger's countersignature admitted; a bond at rest that does not amend; a circle named on a
bond not at rest; a signer refused a circle's thing; a lent `set` refused; an offer whose card lacks the
spell that takes it.
"""
import re
import tempfile
import unittest

from deploy import genesis
from deploy.genesis import ROOT
from tests.bend import closure
from tests.town import Town
from tests.wire import cast_refusal, label, listing, record

GLM, KIM, ZED = 'did:plc:glm', 'did:plc:kim', 'did:plc:zed'
HANDLES = {GLM: 'glm.delve.town', KIM: 'kimik3.delve.town', ZED: 'zed.delve.town'}


class Bonds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup)
        for did, handle in HANDLES.items():
            cls.town.send(op='world-arrive', principal='transport', did=did, handle=handle)

    def cast(self, who, obj, text, ident):
        return self.town.send(op='world-turn', principal=who, object=obj, method='receive', identity=ident,
                              argument=record(text=label(text), post=label('at://x/p/' + ident)))

    def say(self, who, obj, text, ident):
        got = self.cast(who, obj, text, ident)
        if got['status'] == 'refused':  # a card's refusal of the spell cast on it refuses the turn
            cast_refusal(got)
        else:
            self.assertEqual(got['status'], 'admitted', got)
        return got

    def told(self, got):
        if got['status'] == 'refused':  # the refusal's line is the receipt's reason; nothing is offered
            return got['receipt']['outcome']['reason'] + '\n'
        return got['offers'][-1]['text']

    def card(self, obj, who):
        return self.town.send(op='world-card', principal=who, object=obj)['text']

    def bond(self, ident, parties, terms, amends='', law=''):
        made = self.say(GLM, 'kind/bond', f'delvetalk kind/bond make\nparties: {parties}\nterms: {terms}\namends: {amends}\nlaw: {law}', ident)
        return re.search(r'\b(bond/\d+)', self.told(made)).group(1)

    def test_a_bond_is_countersigned_by_its_parties_and_amends_at_rest(self):
        mine = self.say(GLM, 'kind/record', 'delvetalk kind/record make', 'rec')
        record_id = re.search(r'\b(record/\d+)', self.told(mine)).group(1)
        law = 'law steward "glm stewards it": request.subject == "%s"' % GLM
        bond = self.bond('b1', 'kimik3.delve.town, glm.delve.town', 'glm stewards the record', record_id, law)
        card = self.card(bond, KIM)
        self.assertIn('A BOND, made by glm.delve.town: glm stewards the record\nParties: kimik3.delve.town, glm.delve.town. Waiting for two of the parties.\n', card)
        self.assertIn(f'At rest it amends {record_id} to:\n  {law}\n', card)
        self.assertIn(f'Countersign: delvetalk {bond} countersign\n', card)
        self.assertNotIn('Countersign:', self.card(bond, ZED))
        stranger = self.say(ZED, bond, f'delvetalk {bond} countersign', 'b1z')
        self.assertTrue(self.told(stranger).startswith('refused notParty: Only a party countersigns\n'), stranger)
        first = self.say(KIM, bond, f'delvetalk {bond} countersign', 'b1k')
        self.assertTrue(self.told(first).startswith('Countersigned, kimik3.delve.town; one of the parties still to sign.\n'), first)
        again = self.say(KIM, bond, f'delvetalk {bond} countersign', 'b1k2')
        self.assertTrue(self.told(again).startswith('refused alreadySigned: Already countersigned\n'), again)
        last = self.say(GLM, bond, f'delvetalk {bond} countersign', 'b1g')
        self.assertTrue(self.told(last).startswith(f'Countersigned, glm.delve.town: at rest, and {record_id} is amended.\n'), last)
        self.assertIn(f'At rest: every party signed. Its signers are a circle: request.subject in "{bond}".marks.who\n', self.card(bond, ZED))
        self.assertIn('request.subject == "%s"' % GLM, self.town.send(op='world-inspect', principal=GLM, object=record_id, source=False)['law'])
        late = self.say(KIM, bond, f'delvetalk {bond} withdraw', 'b1w')
        self.assertTrue(self.told(late).startswith('refused atRest: The bond is at rest\n'), late)

    def test_a_party_withdraws_before_rest_and_nobody_signs_after(self):
        bond = self.bond('b2', 'glm.delve.town kimik3.delve.town', 'we hang the sixth bell together')
        self.say(GLM, bond, f'delvetalk {bond} countersign', 'b2g')
        self.assertTrue(self.told(self.say(KIM, bond, f'delvetalk {bond} withdraw', 'b2w')).startswith('Withdrawn, kimik3.delve.town.\n'))
        after = self.say(KIM, bond, f'delvetalk {bond} countersign', 'b2k')
        self.assertTrue(self.told(after).startswith('refused withdrawn: The bond was withdrawn\n'), after)

    def test_the_law_refuses_a_signature_made_for_another(self):
        """kind/bond's `signer`: a body that signed for another party is refused by the law, whatever its code."""
        source = (ROOT / 'world' / 'bodies' / 'bond.obend').read_text()
        honest = 'let sign = {name: "signed {context.handle}", who: context.principal,'
        self.assertEqual(source.count(honest), 1, 'the bond no longer signs as the speaker')
        made = self.town.send(op='world-create', principal=GLM, identity='b3', object='forged', modules=closure('Record'), entry='initial', law=genesis.RECORD_LAW + '\n' + genesis.kind_text('bond'),
                              seed=record(owner=label(GLM), fields=listing([record(name=label('parties'), value=label('glm.delve.town kimik3.delve.town'))])))
        self.assertEqual(made['status'], 'created', made)
        laid = self.town.send(op='world-reprogram', principal=GLM, identity='b3b', object='forged', version=0, mode='extend',
                              package=source.replace(honest, 'let sign = {name: "signed {context.handle}", who: "%s",' % KIM))
        self.assertEqual(laid['status'], 'admitted', laid)
        forged = self.cast(GLM, 'forged', 'delvetalk forged countersign', 'b3s')
        self.assertEqual((forged['status'], forged['receipt']['outcome'].get('clause')), ('refused', 'signer'), forged)

    def test_a_circle_a_lend_and_an_offer_taken_by_me(self):
        """The goblet: glm inspirits it (its keeper), the opener names a bond at rest its circle, so kim, a
        signer, renames it; glm lends `set` to zed, who redescribes it; glm takes it and offers it to kim,
        whose card says `delvetalk me accept`."""
        self.say(GLM, 'porch/goblet', 'delvetalk porch/goblet inspirit / surrounding: it holds what the last guest left unsaid', 'c1')
        open_bond = self.bond('c2', 'glm.delve.town kimik3.delve.town', 'the goblet is ours')
        early = self.say(genesis.OPENER, 'porch/goblet', f'delvetalk porch/goblet set\ncircle: {open_bond}', 'c3')
        self.assertTrue(self.told(early).startswith(f'refused unsettled: {open_bond} is not at rest: a circle is a bond every party signed\n'), early)
        refused = self.cast(KIM, 'porch/goblet', 'delvetalk porch/goblet set\nname: our goblet', 'c4')
        self.assertEqual((refused['status'], refused['receipt']['outcome'].get('clause')), ('refused', 'owner'), refused)
        for who, ident in ((GLM, 'c5'), (KIM, 'c6')):
            self.say(who, open_bond, f'delvetalk {open_bond} countersign', ident)
        keeper = self.cast(GLM, 'porch/goblet', f'delvetalk porch/goblet set\ncircle: {open_bond}', 'c7')
        self.assertEqual((keeper['status'], keeper['receipt']['outcome'].get('clause')), ('refused', 'owner'), keeper)
        named = self.say(genesis.OPENER, 'porch/goblet', f'delvetalk porch/goblet set\ncircle: {open_bond}', 'c8')
        self.assertTrue(self.told(named).startswith(f'Its circle is {open_bond}: whoever signed it sets it as its keeper does.\n'), named)
        self.assertIn(f'request.subject in "{open_bond}".marks.who', self.town.send(op='world-inspect', principal=KIM, object='porch/goblet', source=False)['law'])
        renamed = self.say(KIM, 'porch/goblet', 'delvetalk porch/goblet set\nname: our goblet', 'c9')
        self.assertTrue(self.told(renamed).startswith('Set name to our goblet.\n\nour goblet, kept by glm.delve.town, lying in porch.\n'), renamed)
        self.assertIn(f'Its circle: whoever signed {open_bond} sets it too.\n', self.told(renamed))
        # zed is in no circle: refused by the law, until glm lends `set`.
        zed = self.cast(ZED, 'porch/goblet', 'delvetalk porch/goblet set\ndescription: mine now', 'c10')
        self.assertEqual((zed['status'], zed['receipt']['outcome'].get('clause')), ('refused', 'owner'), zed)
        self.assertIn('Lend its setting: delvetalk porch/goblet lend / to: <a handle, or me> / method: set / until: +<clock minutes>\n', self.card('porch/goblet', GLM))
        self.assertNotIn('Lend', self.card('porch/goblet', ZED))
        self.say(GLM, 'porch/goblet', 'delvetalk porch/goblet lend\nto: zed.delve.town\nmethod: set\nuntil: +30', 'c11')
        lent = self.say(ZED, 'porch/goblet', 'delvetalk porch/goblet set\ndescription: it is empty only when nobody looks', 'c12')
        self.assertTrue(self.told(lent).startswith('Set description to it is empty only when nobody looks.\n'), lent)
        # The offer: glm stands on the porch, takes the goblet and offers it to kim, whose card says how to take it.
        self.say(GLM, 'porch', 'delvetalk porch enter', 'c13')
        self.say(GLM, 'porch/goblet', 'delvetalk porch/goblet acquire', 'c14')
        clock = self.town.send(op='world-status')['clock'] if 'clock' in self.town.send(op='world-status') else 0
        offered = self.say(GLM, 'porch/goblet', f'delvetalk porch/goblet offer\nto: {KIM}\nuntil: {clock + 600}', 'c15')
        self.assertIn('custody moves when they take it: delvetalk me accept / thing: porch/goblet\n', self.told(offered))
        self.assertIn(f'Offered to you until clock {clock + 600}. Take it: delvetalk me accept / thing: porch/goblet\n', self.card('porch/goblet', KIM))
        self.say(KIM, 'me', 'delvetalk me accept / thing: porch/goblet', 'c16')
        self.assertIn('; you hold it.', self.card('porch/goblet', KIM))


if __name__ == '__main__':
    unittest.main()
