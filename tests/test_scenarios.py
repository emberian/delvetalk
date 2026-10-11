"""The town's arcs end to end, through the spells a reply carries (what the bridge hands `receive`)
on the town genesis builds: each step's receipt, and the card its reader gets.

Evidence for FOUNDATION §3, §5, §8 and the voice (layer: scenarios).

- Bell: a kind makes a bell, three people rain on it, the kind's rule rings it at the seventh and its
  other rule notes the maker; a rain past its bound is refused by name.
- Garden: a planting spell grows a bell in the garden (held among its `things`) and the card names where
  to rain; a planting that misfits the form is refused by its clause and plants nothing.
- Workshop: a flawed block is checked with a located diagnostic; a proposal to another's card is held
  for its owner; a stranger cannot adopt it; the owner adopts and the target runs the new source.
- Room: a reader enters, chooses, and moves; a stranger's card shows the room but not the reader's
  place; a choice the passage does not offer is refused and writes nothing.

The deal signed by two is `test_deal`; the claim of a handle and the login are `test_transport`
(Identity) and `test_oauth`; the archived hour through the real bridge is `test_archive`.
"""
import unittest
from pathlib import Path

from tests.host import card_texts
from tests.town import Town
from tests.test_properties import OPENER, STRANGERS
import tempfile
from tests.wire import label, nat, record

ROOT = Path(__file__).resolve().parent.parent
KIM, GLM = list(STRANGERS)


class Arc(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.town = Town(tmp.name, cleanup=self.addCleanup)
        for did, handle in STRANGERS.items():
            self.town.send(op="world-arrive", principal="transport", did=did, handle=handle)
        self.n = 0

    def turn(self, who, obj, method, argument):
        self.n += 1
        return self.town.send(op="world-turn", principal=who, object=obj, method=method, argument=argument, identity="t%d" % self.n)

    def say(self, who, obj, text):
        """A reply carrying `text` to card `obj`, as the bridge makes it."""
        return self.turn(who, obj, "receive", record(text=label(text), post=label("at://%s/post/%d" % (who, self.n + 1))))

    def card(self, reply):
        return "\n".join(dict.fromkeys(card_texts(reply)))

    def outcome(self, reply):
        return (reply.get("status"), ((reply.get("receipt") or {}).get("outcome") or {}).get("class"))

    def objects(self):
        return self.town.send(op="world-objects", principal=OPENER)["ids"]

    def pin(self, obj):
        return self.town.send(op="world-inspect", principal=OPENER, object=obj, source=False)["pin"]

    def inbox(self, did):
        rows = self.field(did, "inbox")["payload"]["fields"][0]["value"]["items"]
        return [tuple(next(f["value"]["value"] for f in r["fields"] if f["name"] == k) for k in ("from", "text")) for r in rows]

    def field(self, obj, name):
        state = self.town.send(op="world-view", principal=OPENER, object=obj)["state"]
        return next(f["value"] for f in state["fields"] if f["name"] == name)


class Bell(Arc):
    def test_a_made_bell_is_rained_on_and_rung_by_its_seventh_rain(self):
        made = self.say(KIM, "kind/bell", "delvetalk kind/bell make\ncolour: amber\nseed: a lamp for moths\nid:")
        self.assertEqual(made["status"], "admitted", made)
        bell = made["receipt"]["outcome"]["creates"][0]["object"]  # genesis holds bell/1, the porch's sixth bell
        for i, who in enumerate([GLM, KIM, OPENER, GLM, KIM, OPENER, GLM], 1):
            rained = self.say(who, bell, "delvetalk %s rain\ntext: drizzle %d" % (bell, i))
            self.assertEqual((rained["status"], rained["result"]), ("admitted", nat(i)), rained)
            card = self.card(rained)
            self.assertIn("kimik3.delve.town", card)  # the planter by handle, never a DID (test_properties checks every card)
            self.assertIn("drizzle %d" % i, card)
            self.assertEqual("rung" in card, False if i < 7 else card.count("rung") > 0)
        self.assertIn("rung", self.card(self.say(GLM, bell, "")))
        # Both are kind/bell's rules, carried to the bell by `under`: `seven` rang it, `rang` noted its maker.
        self.assertIn("%s rang" % bell, [text for _, text in self.inbox(KIM)])
        long = self.say(GLM, bell, "delvetalk %s rain\ntext: %s" % (bell, "x" * 201))
        # A bell reads no words (it names no policy): its misfit is the host's badSpell with the usage (HOST-HANDOFF 5.153).
        out = long["receipt"]["outcome"]
        self.assertEqual((long["status"], out["class"], out["clause"]), ("refused", "badSpell", "badValue"), long)
        self.assertIn("delvetalk %s rain" % bell, out["hint"])


class Garden(Arc):
    def test_a_planting_spell_grows_a_bell_and_its_card_says_where_to_rain(self):
        planted = self.say(GLM, "garden", "delvetalk garden plant\nseed: a bell for lost moths\ncolour: silver")
        self.assertEqual((planted["status"], planted["result"]["label"]), ("admitted", "made"), planted)
        self.assertIn("garden/bell/1", self.objects())
        card = self.card(planted)
        self.assertIn("glm.delve.town", card)
        self.assertIn("delvetalk garden/bell/1 rain", card)
        self.assertEqual(self.things(), ["garden/bell/1"])
        again = self.say(KIM, "garden", "delvetalk garden plant\nseed: %s\ncolour: silver" % ("y" * 81))
        # The garden reads no words (it names no policy): its misfit is the host's badSpell with the usage and
        # nothing is planted (HOST-HANDOFF 5.153). Prose, which is no spell, goes on to the commonplace, where hob reads it.
        self.assertEqual((again["status"], again["receipt"]["outcome"]["class"], again["receipt"]["outcome"]["clause"]), ("refused", "badSpell", "badValue"), again)
        self.assertEqual(self.things(), ["garden/bell/1"])

    def things(self):
        return [next(f["value"]["value"] for f in row["fields"] if f["name"] == "object") for row in self.field("garden", "things")["payload"]["fields"][0]["value"]["items"]]


class Workshop(Arc):
    def test_a_check_a_held_proposal_and_its_adoption_by_the_owner_only(self):
        flawed = self.say(KIM, "workshop", "delvetalk workshop check\n```obend\nedition ObjectiveBend 1\nrecord State:\n  count: Nat\n"
                                           "def initial() -> Maybe<Nat>:\n  {count: 0n}\n```\n")
        self.assertEqual((flawed["status"], flawed["result"]["label"]), ("admitted", "flawed"), flawed)
        self.assertRegex(self.card(flawed), r"Checked:\d+: ")  # the diagnostic names its line
        top = (ROOT / "world" / "objects" / "Library.obend").read_text()  # genesis made the library from it
        proposed = self.say(KIM, "workshop", "delvetalk workshop propose\ntarget: library\n```obend\n%s\n# kimik3 was here\n```\n" % top.rstrip("\n"))
        self.assertEqual(proposed["status"], "admitted", proposed)
        self.assertIn("#1", self.card(proposed))
        pin = self.pin("library")
        stranger = self.say(GLM, "workshop", "delvetalk workshop adopt / n: 1")
        self.assertEqual(self.pin("library"), pin, stranger)
        adopted = self.say(OPENER, "workshop", "delvetalk workshop adopt / n: 1")
        self.assertEqual(adopted["status"], "admitted", adopted)
        self.assertNotEqual(self.pin("library"), pin, adopted)


class Room(Arc):
    def test_a_reader_enters_and_chooses_and_a_stranger_sees_the_room_not_the_reader(self):
        entered = self.say(KIM, "rooms", "delvetalk rooms enter")
        self.assertEqual((entered["status"], entered["result"]["label"]), ("admitted", "entered"), entered)
        mine = self.card(self.say(KIM, "rooms", ""))
        self.assertIn("you are at gate", mine)
        choice = mine.split("Choices:\n")[1].split("\n")[0].strip("* ").strip()
        before = self.town.send(op="world-view", principal=OPENER, object="rooms")["version"]
        wrong = self.say(KIM, "rooms", "delvetalk rooms choose / choice: nowhere at all")
        self.assertEqual(self.town.send(op="world-view", principal=OPENER, object="rooms")["version"], before, wrong)
        chose = self.say(KIM, "rooms", "delvetalk rooms choose / choice: %s" % choice)
        self.assertEqual(chose["status"], "admitted", chose)
        self.assertNotIn("you are at gate", self.card(self.say(KIM, "rooms", "")))
        theirs = self.card(self.say(GLM, "rooms", ""))
        self.assertIn("The Moss Gate", theirs)
        self.assertNotIn("you are at", theirs)


if __name__ == "__main__":
    unittest.main()
