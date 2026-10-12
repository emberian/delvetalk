"""The library's six walks, cast as a resident would: each walk's spells in the order the page gives them, on a genesis
town as genesis makes it (no furnishing), with the `<...>` blanks filled from the replies before; each step's status and `»` claim are asserted, then the
`Changed:` line's end state. The spell text is read out of the page file itself, so a walk that names a spell the
cards no longer take fails here.

Evidence for docs/LIBRARY.md section (d) (layer: objects).

Refuted by: a walk longer than a reply's room (1,266 characters), one that does not open on hob's line, or one whose
spell is refused badSpell, or whose `»` line says what the card did not do.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path

from deploy import genesis
from tests.host import card_texts
from tests.town import Town
from tests.wire import label, record

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "capsules" / "pages"
WALKS = ("bell", "check", "enter", "scene", "tide", "kind")
WALKER, OTHER = "did:plc:walker", "did:plc:other"
LIMIT = 1266  # Library's shelve body bound: a reply's 1,400 less the library's receipt line

STEP = re.compile(r"^  (?:(other|after[^:]*): )?(delvetalk .*)$")


def walk(name):
    """(first line, steps, changed): a step is (prefix, spell text, claim), the spell's block lines dedented under it."""
    lines = (PAGES / (name + ".txt")).read_text().split("\n")
    steps, last = [], None
    for line in lines[1:]:
        if line.startswith("Changed: "):
            last = line[len("Changed: "):]
        elif (m := STEP.match(line)):
            steps.append([m.group(1) or "", [m.group(2)], []])
        elif line.startswith("  » "):
            steps[-1][2].append(line[4:])
        elif line.startswith("  ") and steps and not steps[-1][2]:
            steps[-1][1].append(line[2:])
    return lines[0], [(p, "\n".join(s) + "\n" if len(s) > 1 else s[0], " ".join(c)) for p, s, c in steps], last


class Walks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.host = cls.town.client
        cls.n = 0
        for did, handle in ((WALKER, "walker.test"), (OTHER, "other.test")):
            got = cls.host.send({"op": "world-arrive", "principal": "transport", "did": did, "handle": handle})
            assert got["status"] == "arrived", got

    def card_of(self, who, spell):
        """The card a spell line names: its second word; `me` is the speaker's own."""
        word = spell.split()[1]
        return who if word == "me" else word

    def cast(self, who, spell):
        """The spell as a reply to its card, as the bridge hands `receive`; (reply, offered text)."""
        type(self).n += 1
        reply = self.host.send({"op": "world-turn", "principal": who, "object": self.card_of(who, spell), "method": "receive",
                                "identity": "walk-%d" % self.n,
                                "argument": record(text=label(spell), post=label("at://x/walk-%d" % self.n))})
        return reply, "".join(o["text"] for o in reply.get("offers", []))

    def say(self, who, spell):
        """A spell whose reply must be admitted and not refused badSpell."""
        reply, text = self.cast(who, spell)
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertNotIn("badSpell", json.dumps(reply)[:4000], text)
        return reply, text

    def avatar(self, did):
        return "\n".join(dict.fromkeys(card_texts(self.host.send({"op": "world-card", "principal": did, "object": did}))))

    def view(self, obj, who=WALKER):
        got = self.host.send({"op": "world-view", "principal": who, "object": obj})
        self.assertEqual(got["status"], "viewed", got)
        return {f["name"]: f["value"] for f in got["state"]["fields"]}

    def steps(self, name):
        first, steps, changed = walk(name)
        return steps

    def fill(self, spell, **blanks):
        for key, value in blanks.items():
            spell = spell.replace("<%s>" % key, value)
        return spell

    # Every walk: the size bound, hob's line, the pages it names, and a claim for each spell.
    def test_every_walk_fits_a_reply_opens_on_hob_and_names_only_shelved_pages(self):
        shelved = {n for n, _, _ in genesis.PAGES}
        for name in WALKS:
            with self.subTest(walk=name):
                body = (PAGES / (name + ".txt")).read_text()
                first, steps, changed = walk(name)
                self.assertLessEqual(len(body), LIMIT)
                self.assertTrue(first.startswith("hob: "), first)
                self.assertLessEqual(len(first.split()), 20, first)
                self.assertTrue(changed, name)
                self.assertTrue(all(claim for _, _, claim in steps), steps)
                self.assertTrue(set(re.findall(r"page: (\w+)", body)) <= shelved, body)

    def test_make_a_bell_rain_on_it_place_a_rule_and_hear_the_ring(self):
        W, O = WALKER, OTHER
        (_, make, _), (_, rain, _), (_, rule, _), (_, theirs, _), (_, ring, _) = self.steps("bell")
        _, text = self.say(W, make)
        bell = re.search(r"Made, at (bell/\d+);", text).group(1)
        self.assertIn("planted by walker.test (yours)", self.card_text(W, bell))
        self.assertIn("rain", [w["name"] for w in self.wants(bell)])
        _, text = self.say(W, self.fill(rain, bell=bell))
        self.assertIn("#1 is written: it rained here first", text)
        self.assertEqual([w["name"] for w in self.wants(bell) if w["name"] in ("rain", "second")], ["second"])
        self.say(W, self.fill(rule, bell=bell))
        self.assertEqual([r["name"] for r in self.rules(bell) if r["name"] == "two"], ["two"])
        self.assertNotIn("a second rain", self.avatar(W))  # one hand's rain does not fire it
        _, text = self.say(O, self.fill(theirs, bell=bell))
        self.assertIn("#2 is written: and here", text)
        self.assertTrue(self.rules(bell, "two")["fired"], self.rules(bell))
        self.assertIn("a second rain", self.avatar(W))
        self.assertNotIn("rung", self.card_text(W, bell))
        self.say(W, self.fill(ring, bell=bell))
        self.assertIn("— rung.", self.card_text(W, bell))
        self.assertIn("%s rang" % bell, self.avatar(W))  # the kind's rule `rang` notes the planter

    def wants(self, obj, who=WALKER):
        got = self.host.send({"op": "world-wants", "principal": who, "object": obj})
        return got["rows"]

    def rules(self, obj, name=None, who=WALKER):
        got = self.host.send({"op": "world-rules", "principal": who, "object": obj})
        return {r["name"]: r for r in got["rows"]}[name] if name else got["rows"]

    def card_text(self, who, obj):
        got = self.host.send({"op": "world-card", "principal": who, "object": obj})
        self.assertNotIn("error", got.get("status", ""), got)
        return got.get("text", "")

    def test_check_a_source_a_draft_made_yours_and_another_proposal_held_for_you(self):
        W, O = WALKER, OTHER
        (_, tide, _), (_, flawed, _), (_, draft, _), (_, adopt, _), (_, propose, _) = self.steps("check")
        _, text = self.say(W, tide)
        self.assertIn("Checked: it compiles.", text)
        _, text = self.say(W, flawed)
        self.assertRegex(text, r"Checked: 1 problem\.\n\n- Checked:\d+: .*\n  hint: ")
        _, text = self.say(W, draft)
        n = re.search(r"Held as #(\d+); adopt it to make jar", text).group(1)
        self.assertIn("» jar, yours, made from #%s" % n, text)
        before = self.host.send({"op": "world-objects", "principal": W})["ids"]
        self.assertNotIn("jar", before)
        _, text = self.say(W, self.fill(adopt, n=n))
        self.assertIn("Made jar from #%s; it is yours." % n, text)
        self.assertIn("jar", self.host.send({"op": "world-objects", "principal": W})["ids"])
        _, text = self.say(O, propose)
        m = re.search(r"held as #(\d+) for the owner of jar to adopt", text).group(1)
        self.assertIn("refused owner", text)
        _, text = self.say(W, "delvetalk workshop adopt / n: %s" % m)
        self.assertIn("jar is reprogrammed", text)

    def test_enter_the_porch_say_make_a_room_of_your_own_under_it_and_choose(self):
        W = WALKER
        (_, enter, _), (_, say, _), (_, block, _), (_, nook, _), (_, listen, _) = self.steps("enter")
        _, text = self.say(W, enter)
        self.assertIn("The Bellfounder's Porch (1 here), you are here.", text)
        self.assertIn("Doors: mimo's bell · light-traces' bell", text)
        self.assertIn("Unclaimed here: porch/ring, porch/goblet, porch/gemstone.", text)
        _, text = self.say(W, say)
        self.assertIn("walker.test: the brass is warm", text)
        _, text = self.say(W, block)
        room = re.search(r"ROOM The Nook is at (porch/porch/\d+)", text).group(1)
        _, text = self.say(W, self.fill(nook, room=room))
        self.assertIn("The Nook (1 here), you are at nook", text)
        self.assertIn("* Sit", text)
        self.assertIn("* Listen", text)
        self.assertIn("Doors: porch", text)
        _, text = self.say(W, self.fill(listen, room=room))
        self.assertIn("you are at nook", text)
        self.assertIn("bells = heard", text)
        self.assertIn(room, self.host.send({"op": "world-objects", "principal": W})["ids"])

    def test_scene_make_a_room_from_a_scene_read_its_rule_enter_and_ring_a_bell_by_choosing(self):
        W = WALKER
        (_, make, _), (_, rules, _), (_, enter, _), (_, pull, _) = self.steps("scene")
        _, text = self.say(W, make)
        room = re.search(r"Made, at (room/\d+);", text).group(1)
        reply, _ = self.cast(W, self.fill(rules, room=room))
        self.assertEqual(reply["status"], "usage", reply)
        self.assertIn("rope_1", reply["text"])
        self.assertEqual(self.rules(room, "rope_1")["owner"], W)
        _, text = self.say(W, self.fill(enter, room=room))
        self.assertIn("you are at rope:\nA rope out of the dark. mimo's bell is somewhere above.\nChoices:\n  * Pull it\n", text)
        reply, text = self.say(W, self.fill(pull, room=room))
        self.assertIn("pulled = true", text)
        self.assertIn("rule rope_1 of walker.test fired: delvetalk bell/1 ring", reply["revealed"])
        self.host.send({"op": "world-deliver", "principal": "transport", "limit": 16})
        self.assertIn("rung", [m["fields"][0]["value"]["value"] for m in self.view("bell/1")["marks"]["payload"]["fields"][0]["value"]["items"]])
        self.assertNotIn("Pull it", self.card_text(W, room))

    def test_tide_rules_place_one_refuse_a_hands_tick_and_hear_it_fire_after_the_clock(self):
        W = WALKER
        (_, rules, _), (_, turned, _), (_, tick, _), (_, after, _) = self.steps("tide")
        reply, _ = self.cast(W, rules)  # a read: the host answers it with the rules, no turn
        self.assertEqual(reply["status"], "usage", reply)
        text = reply["text"]
        # Genesis's motion: the weather's rule and the porch's lamp's (tests/test_motion).
        self.assertIn("» weather (the town)", text)
        self.assertIn("» porch_slamp (the town)", text)
        self.say(W, turned)
        self.assertIn("turned", [r["name"] for r in self.rules("tide")])
        self.assertFalse(self.rules("tide", "turned").get("fired"))
        reply, _ = self.cast(W, tick)
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("itself", json.dumps(reply["receipt"]["outcome"]), reply)
        clock = self.host.send({"op": "world-status"})["clock"]
        got = self.host.send({"op": "world-advance", "principal": "transport", "height": clock + 61})
        self.assertEqual(got["status"], "advanced", got)
        reply, _ = self.cast(W, after)
        self.assertIn("» turned (", reply["text"])
        self.assertTrue(self.rules("tide", "turned")["fired"], self.rules("tide"))
        self.assertIn("the tide turned", self.avatar(W))

    def test_kind_make_a_kind_and_someone_else_uses_it_under_its_law(self):
        W, O = WALKER, OTHER
        (_, kind, _), (_, mine, _), (_, theirs, _), (_, trespass, _), (_, write, _) = self.steps("kind")
        _, text = self.say(W, kind)
        self.assertIn("Made, at kind/lamp;", text)
        _, text = self.say(W, mine)
        self.assertIn("Made, at lamp/1;", text)
        _, text = self.say(O, theirs)
        self.assertIn("Made, at lamp/2;", text)
        reply, _ = self.cast(O, trespass)
        self.assertEqual((reply["status"], reply["receipt"]["outcome"]["reason"]), ("refused", "refused maker: only its maker writes"), reply)
        self.assertEqual(reply["receipt"]["outcome"].get("writes", []), [], reply)
        _, text = self.say(W, write)
        self.assertIn("#1 is written: lit", text)
        cards = {obj: self.card_text(W, obj) for obj in ("lamp/1", "lamp/2")}
        self.assertIn("walker.test (yours): lit", cards["lamp/1"])
        self.assertNotIn("lit", cards["lamp/2"])
        _, text = self.say(O, "delvetalk lamp/2 write / text: owl")
        self.assertIn("#1 is written: owl", text)


if __name__ == "__main__":
    unittest.main()
