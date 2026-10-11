"""A Scene keeps passages, presence and variables per reader: only an offered choice moves its
reader, a refusal writes nothing, every bound is refused at its edge.

Evidence for FOUNDATION §8 (layer: objects).

A Scene object: passages and choices as data, presence per principal, variables a choice sets.

The reader is the turn's principal (no method names one), a choice must be offered by the
reader's current passage, and a refused choice writes nothing (the version stays).

Refuted by: a choice moving a reader whose passage does not offer it, a refusal that writes,
one reader's choice moving another, a stranger's card equal to a reader's, a second enter
admitted, a seventeenth reader or variable admitted, or a full card past 1,400 characters.
"""
import unittest

from tests import test_chain
from tests.wire import label, record, relation
from tests.bend import closure

GLM, KIM = "did:plc:glm", "did:plc:kimik3"


def heard(text=""):
    return record(text=label(text), post=label(""))


def listing(items):
    return {"tag": "list", "items": list(items)}


def choice(text, to, key="", value=""):
    """A choice; a key sets that variable to value when it is taken (one `set` effect)."""
    effects = [record(key=label(key), op={"tag": "variant", "label": "set", "payload": record()}, value=label(value))] if key else []
    return record(label=label(text), to=label(to), effects=listing(effects), guard=listing([]))


def passage(pid, text, choices):
    return record(id=label(pid), text=label(text), choices=listing(choices))


def scene_state(passages, start="gate", title="The Moss Gate", cooldown=0):
    return record(owner=label("ember"), title=label(title), start=label(start), passages=listing(passages),
                  presence=relation(), vars=listing([]), cooldown={"tag": "natural", "value": str(cooldown)},
                  requires=listing([]), left=relation())


GATE = [
    passage("gate", "A moss gate, ajar.", [choice("Open", "yard", "gate", "open"), choice("Wait", "gate")]),
    passage("yard", "A quiet yard.", [choice("Back", "gate"), choice("Knock", "yard", "knock", "twice")]),
]


def why(reply):
    """A refusal as `clause: reading`."""
    fields = {f["name"]: f["value"]["value"] for f in reply["result"]["payload"]["fields"]}
    return "%s: %s" % (fields["clause"], fields["reading"])


def plain(item):
    """A wire value as plain python: records to dicts, lists and relations to lists, a sum to its case, scalars to values."""
    tag = item["tag"]
    if tag == "variant" and item["label"] == "rows":
        return plain(item["payload"]["fields"][0]["value"])
    if tag == "variant":
        return item["label"]
    if tag == "record":
        return {f["name"]: plain(f["value"]) for f in item["fields"]}
    if tag == "list":
        return [plain(i) for i in item["items"]]
    return item["value"]


class Scenes(test_chain.Chain):

    def scene(self, passages=GATE, **kw):
        r = self.host.send(op="world-create", principal="ember", identity="mk-scene", object="scene",
                           modules=closure("Scene"), entry="initial", seed=scene_state(passages, **kw))
        self.assertEqual(r["status"], "created", r)

    def say(self, text="", principal=GLM):
        r = self.turn("scene", "receive", heard(text), principal=principal)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def card(self, principal):
        text = self.say("", principal)["offers"][0]["text"]
        self.assertLessEqual(len(text), 1400, text)
        return text

    def view(self):
        v = self.host.send(op="world-view", principal="ember", object="scene")
        self.assertEqual(v["status"], "viewed", v)
        return v["version"], plain(v["state"])

    def test_newer_departures_never_erase_an_unexpired_cooldown(self):
        """`left` keeps 64 departures; one that is still cooling is never the one dropped: an
        entry that could later push one out is refused `crowded` (codex objects 9)."""
        self.scene(cooldown=1000)
        self.assertEqual(self.say("delvetalk scene enter")["result"]["label"], "entered")
        self.assertEqual(self.say("delvetalk scene leave")["result"]["label"], "left")
        for i in range(63):
            who = "did:plc:walker%d" % i
            self.assertEqual(self.say("delvetalk scene enter", who)["result"]["label"], "entered")
            self.assertEqual(self.say("delvetalk scene leave", who)["result"]["label"], "left")
        crowded = self.say("delvetalk scene enter", "did:plc:walker63")
        self.assertEqual(why(crowded), "crowded: 64 left within the cooldown; enter again from clock 1000.")
        early = self.say("delvetalk scene enter")
        self.assertEqual(why(early), "cooldown: You left at clock 0; enter again from clock 1000.")
        self.host.send(op="world-advance", height=1000)
        self.assertEqual(self.say("delvetalk scene enter", "did:plc:walker63")["result"]["label"], "entered")


    def test_a_choice_the_passage_does_not_offer_is_refused_by_name_and_writes_nothing(self):
        self.scene()
        self.say("delvetalk scene enter")
        before = self.view()
        for text in ("Knock", "open", "Back", "Open the gate"):
            with self.subTest(choice=text):
                r = self.say("delvetalk scene choose\nchoice: " + text)
                self.assertEqual(r["result"]["label"], "refused")
                self.assertTrue(why(r).startswith("notOffered: gate does not offer"), why(r))
                self.assertEqual(self.view(), before)
        r = self.say("delvetalk scene choose\nchoice: Knock")
        self.assertIn("you are at gate:\nA moss gate, ajar.\nChoices:\n  * Open\n  * Wait\n\nrefused notOffered: gate does not offer Knock\n", r["offers"][0]["text"])
        # A principal who never entered has no passage to choose from.
        r = self.say("delvetalk scene choose\nchoice: Open", principal=KIM)
        self.assertTrue(why(r).startswith("notHere"), why(r))
        r = self.say("delvetalk scene leave", principal=KIM)
        self.assertTrue(why(r).startswith("notHere"), why(r))
        self.assertEqual(self.view(), before)

    def test_a_second_principals_presence_is_separate(self):
        self.scene()
        self.say("delvetalk scene enter", GLM)
        self.say("delvetalk scene enter", KIM)
        self.say("delvetalk scene choose\nchoice: Open", GLM)
        _, state = self.view()
        self.assertEqual(state["presence"], [{"who": GLM, "at": "yard"}, {"who": KIM, "at": "gate"}])
        self.assertIn("you are at gate", self.card(KIM))
        self.assertIn("you are at yard", self.card(GLM))
        self.assertIn("(2 here)", self.card(KIM))
        # KIM choosing a yard choice is refused though GLM stands in the yard.
        r = self.say("delvetalk scene choose\nchoice: Knock", KIM)
        self.assertTrue(why(r).startswith("notOffered"), why(r))
        self.say("delvetalk scene leave", GLM)
        self.assertEqual(self.view()[1]["presence"], [{"who": KIM, "at": "gate"}])


    def test_the_largest_scene_fills_every_bound_and_the_next_is_refused(self):
        # Sixteen passages of eight choices: seven set a variable and stay, one goes on.
        passages = [passage("p%d" % i, "Passage %d, " % i + "x" * 60,
                            [choice("s%d" % j, "p%d" % i, "v%d_%d" % (i, j), "on" + "y" * 40) for j in range(7)]
                            + [choice("next", "p%d" % ((i + 1) % 16))]) for i in range(16)]
        self.scene(passages, start="p0")
        for n in range(16):
            self.assertEqual(self.say("delvetalk scene enter", "did:plc:r%d" % n)["result"]["label"], "entered")
        r = self.say("delvetalk scene enter", "did:plc:r16")
        self.assertTrue(why(r).startswith("sceneFull"), why(r))
        self.assertEqual(len(self.view()[1]["presence"]), 16)
        who = "did:plc:r0"
        for n in range(16):
            if n and n % 7 == 0:
                self.say("delvetalk scene choose\nchoice: next", who)
            self.assertEqual(self.say("delvetalk scene choose\nchoice: s%d" % (n % 7), who)["result"]["label"], "moved")
        full = self.card(who)
        self.assertIn("v0_3 = on" + "y" * 40 + "\n… and 12 more\n", full)
        self.assertEqual(len(self.view()[1]["vars"]), 16)
        self.assertIn("you are at p2", full)
        self.assertIn("(16 here)", full)
        before = self.view()
        r = self.say("delvetalk scene choose\nchoice: s2", who)
        self.assertTrue(why(r).startswith("varsFull"), why(r))
        self.assertEqual(self.view(), before)
        # An existing variable is still settable when the variables are full.
        self.assertEqual(self.say("delvetalk scene choose\nchoice: s0", who)["result"]["label"], "moved")
        # The reader moves on only by an offered choice.
        self.assertEqual(self.say("delvetalk scene choose\nchoice: next", who)["result"]["label"], "moved")
        self.assertIn("you are at p3", self.card(who))

    def test_entering_twice_a_missing_start_and_a_choice_to_a_missing_passage_are_refused_and_write_nothing(self):
        for passages, start, spells, clause in ((GATE, "gate", ["enter", "choose\nchoice: Open", "enter"], "alreadyHere"),
                                                 (GATE, "nowhere", ["enter"], "noStart"),
                                                 ([passage("gate", "Edge.", [choice("Jump", "void", "fell", "yes")])], "gate", ["enter", "choose\nchoice: Jump"], "noPassage")):
            with self.subTest(clause=clause):
                self.host.send(op="world-open", path=self.path + clause)
                self.scene(passages, start=start)
                for spell in spells[:-1]:
                    self.say("delvetalk scene " + spell)
                before = self.view()
                r = self.say("delvetalk scene " + spells[-1])
                self.assertTrue(why(r).startswith(clause), why(r))
                self.assertEqual(self.view(), before)

    def test_a_forged_principal_cannot_be_sent_and_a_labelled_choice_of_another_passage_does_nothing(self):
        self.scene()
        self.say("delvetalk scene enter", GLM)
        before = self.view()
        for text in ("delvetalk scene choose\nchoice: Open\nprincipal: " + KIM,
                     "delvetalk scene enter\nprincipal: " + KIM,
                     "delvetalk scene choose\nwho: " + KIM + "\nchoice: Open"):
            with self.subTest(text=text):
                # The host fits the spell against the method's input: a field it lacks is refused by name.
                r = self.turn("scene", "receive", heard(text), principal=GLM)
                out = r["receipt"]["outcome"]
                self.assertEqual((r["status"], out["class"], out["clause"]), ("refused", "badSpell", "unknownField"), r)
        self.assertEqual(self.view(), before)
        self.assertEqual([p["who"] for p in self.view()[1]["presence"]], [GLM])
        # Turn-level choose moves only the turn's principal.
        r = self.turn("scene", "choose", record(choice=label("Open")), principal=KIM)
        self.assertEqual(r["status"], "admitted")
        self.assertTrue(r["result"]["payload"]["fields"][0]["value"]["value"].startswith("notHere"))
        self.assertEqual(self.view(), before)


if __name__ == "__main__":
    unittest.main()
