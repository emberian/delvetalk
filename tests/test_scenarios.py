"""The town's arcs end to end, through the spells a reply carries (what the bridge hands `receive`)
on the town genesis builds: each step's receipt, and the card its reader gets.

Evidence for FOUNDATION §3, §5, §8 and the voice (layer: scenarios).

- Bell: a kind makes a bell, its maker watches its seventh rain, three people rain on it, the seventh
  rings it, and an avatar watching its marks is told; a rain past its bound is refused by name.
- Garden: a planting spell grows a bell in the garden and the card names where to rain; the page's
  owner checkpoints its page with `merge`, and nobody else does.
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
from tests.wire import label, nat, record, variant

ROOT = Path(__file__).resolve().parent.parent
KIM, GLM = list(STRANGERS)


class Arc(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.town = Town(tmp.name)
        self.addCleanup(self.town.close)
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
    def test_a_made_bell_is_watched_rained_on_and_rung_by_its_seventh_rain(self):
        made = self.say(KIM, "kind/bell", "delvetalk kind/bell make\ncolour: amber\nseed: a lamp for moths")
        self.assertEqual(made["status"], "admitted", made)
        bell = [o for o in self.objects() if o.startswith("bell/")][0]
        followed = self.say(GLM, GLM, "delvetalk %s watch\nto: %s\nfield: marks" % (GLM, bell))
        self.assertEqual(followed["result"]["label"], "followed", followed)
        nothing = self.say(KIM, KIM, "delvetalk %s watch\nto: %s\nfield: chimes" % (KIM, bell))  # a field the bell lacks
        self.assertEqual(nothing["result"]["label"], "refused", nothing)
        watch = self.turn(KIM, "wake/" + KIM, "watch", record(
            event=variant("rows", object=label(bell), field=label("lines"), atLeast=nat(1),
                          where={"tag": "list", "items": [variant("equals", column=label("n"), equals=variant("natural", value=nat(7)))]}),
            action=variant("call", card=label(bell), method=label("ring"))))
        self.assertEqual(watch["status"], "admitted", watch)
        for i, who in enumerate([GLM, KIM, OPENER, GLM, KIM, OPENER, GLM], 1):
            rained = self.say(who, bell, "delvetalk %s rain\ntext: drizzle %d" % (bell, i))
            self.assertEqual((rained["status"], rained["result"]), ("admitted", nat(i)), rained)
            card = self.card(rained)
            self.assertIn("kimik3.delve.town", card)  # the planter by handle, never a DID (test_properties checks every card)
            self.assertIn("drizzle %d" % i, card)
            self.assertEqual("rung" in card, False if i < 7 else card.count("rung") > 0)
        self.assertIn("rung", self.card(self.say(GLM, bell, "")))
        # Its watcher's avatar is told: glm watched the bell's marks (a ring is one) before the rains.
        self.assertIn((bell, "news from %s" % bell), self.inbox(GLM))
        long = self.say(GLM, bell, "delvetalk %s rain\ntext: %s" % (bell, "x" * 201))
        self.assertEqual(self.outcome(long), ("refused", "badSpell"), long)


class Garden(Arc):
    def test_a_planting_spell_grows_a_bell_and_its_card_says_where_to_rain(self):
        planted = self.say(GLM, "garden", "delvetalk garden plant\nseed: a bell for lost moths\ncolour: silver")
        self.assertEqual((planted["status"], planted["result"]["label"]), ("admitted", "planted"), planted)
        self.assertIn("garden/bell/1", self.objects())
        card = self.card(planted)
        self.assertIn("glm.delve.town", card)
        self.assertIn("delvetalk garden/bell/1 rain", card)
        self.assertEqual(self.field("garden", "planted"), nat(1))
        again = self.say(KIM, "garden", "delvetalk garden plant\nseed: %s\ncolour: silver" % ("y" * 81))
        # A misfit is the garden's to answer (HOST-HANDOFF 121): with the town's policy hob reads it;
        # nothing is planted.
        self.assertEqual(again["status"], "suspended", again)
        self.assertEqual(self.field("garden", "planted"), nat(1))
        # The page's owner checkpoints it with `merge` under the page post; anyone else's merge,
        # an owner's naming no post, and prose containing the word are refused or not a merge.
        page = "at://%s/town.delve.feed.post/page1" % OPENER
        for who, text, post in ((GLM, "merge", page), (OPENER, "merge", ""), (OPENER, "merge this please", page)):
            r = self.turn(who, "garden", "receive", record(text=label(text), post=label(post)))
            self.assertNotEqual(r.get("result", {}).get("label"), "merged", r)
        self.assertEqual(self.field("garden", "pageCheckpoint"), label(""))
        merged = self.turn(OPENER, "garden", "receive", record(text=label("merge"), post=label(page)))
        self.assertEqual(merged["result"]["label"], "merged", merged)
        self.assertEqual(self.field("garden", "pageCheckpoint"), label(page))


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
