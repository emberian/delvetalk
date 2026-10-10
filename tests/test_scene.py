"""A Scene object: passages and choices as data, presence per principal, variables a choice sets.

The reader is the turn's principal (no method names one), a choice must be offered by the
reader's current passage, and a refused choice writes nothing (the version stays).

Refuted by: a choice moving a reader whose passage does not offer it, a refusal that writes,
one reader's choice moving another, a stranger's card equal to a reader's, a second enter
admitted, a seventeenth reader or variable admitted, or a full card past 1,400 characters."""
import unittest

from tests import test_chain
from tests.test_objects import closure
from tests.test_turn_world import label, record

GLM, KIM = "did:plc:glm", "did:plc:kimik3"


def heard(text=""):
    return record(text=label(text), post=label(""), slot=label(""))


def listing(items):
    return {"tag": "list", "items": list(items)}


def choice(text, to, key="", value=""):
    """A choice; a key sets that variable to value when it is taken (one `set` effect)."""
    effects = [record(key=label(key), op=label("set"), value=label(value))] if key else []
    return record(label=label(text), to=label(to), effects=listing(effects), guard=listing([]))


def passage(pid, text, choices):
    return record(id=label(pid), text=label(text), choices=listing(choices))


def scene_state(passages, start="gate", title="The Moss Gate"):
    return record(title=label(title), start=label(start), passages=listing(passages),
                  presence=listing([]), vars=listing([]), cooldown={"tag": "natural", "value": "0"},
                  requires=listing([]), left=listing([]))


GATE = [
    passage("gate", "A moss gate, ajar.", [choice("Open", "yard", "gate", "open"), choice("Wait", "gate")]),
    passage("yard", "A quiet yard.", [choice("Back", "gate"), choice("Knock", "yard", "knock", "twice")]),
]


def why(reply):
    """A refusal as `clause: reading`."""
    fields = {f["name"]: f["value"]["value"] for f in reply["result"]["payload"]["fields"]}
    return "%s: %s" % (fields["clause"], fields["reading"])


def plain(item):
    """A wire value as plain python: records to dicts, lists to lists, scalars to values."""
    tag = item["tag"]
    if tag == "record":
        return {f["name"]: plain(f["value"]) for f in item["fields"]}
    if tag == "list":
        return [plain(i) for i in item["items"]]
    return item["value"]


class Scenes(test_chain.Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

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

    def test_enter_then_choose_moves_the_reader_and_sets_a_variable(self):
        self.scene()
        stranger = self.card(GLM)
        print("\n--- stranger ---\n" + stranger)
        r = self.say("delvetalk scene enter")
        self.assertEqual(r["result"]["label"], "done")
        reader = self.card(GLM)
        print("--- reader at the gate ---\n" + reader)
        self.assertIn("you are at gate", reader)
        self.assertIn("A moss gate, ajar.", reader)
        self.assertIn("  * Open\n", reader)
        r = self.say("delvetalk scene choose\nchoice: Open")
        self.assertEqual(r["result"]["label"], "done", r)
        moved = self.card(GLM)
        print("--- reader in the yard ---\n" + moved)
        self.assertIn("you are at yard", moved)
        self.assertIn("gate = open\n", moved)
        _, state = self.view()
        self.assertEqual(state["presence"], [{"who": GLM, "at": "yard"}])
        self.assertEqual(state["vars"], [{"name": "gate", "value": "open"}])
        # Setting the same variable again amends it rather than adding.
        self.say("delvetalk scene choose\nchoice: Knock")
        self.say("delvetalk scene choose\nchoice: Knock")
        _, state = self.view()
        self.assertEqual(sorted(v["name"] for v in state["vars"]), ["gate", "knock"])
        self.say("delvetalk scene leave")
        self.assertEqual(self.view()[1]["presence"], [])

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
        print("--- refused card ---\n" + r["offers"][0]["text"])
        self.assertIn("refused notOffered: ", r["offers"][0]["text"])
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

    def test_a_strangers_card_differs_from_a_present_readers(self):
        self.scene()
        before = self.card("did:plc:nobody")
        self.say("delvetalk scene enter", GLM)
        stranger, reader = self.card("did:plc:nobody"), self.card(GLM)
        print("--- stranger after one entered ---\n" + stranger + "--- reader ---\n" + reader)
        self.assertNotEqual(stranger, reader)
        self.assertNotEqual(stranger, before)
        self.assertIn("1 here", stranger)
        self.assertIn("delvetalk scene enter", stranger)
        self.assertNotIn("A moss gate", stranger)
        self.assertNotIn("Choices:", stranger)
        world = self.host.send(op="world-card", principal="ember", object="scene")
        self.assertIn("1 here", world["text"])

    def test_entering_twice_is_refused(self):
        self.scene()
        self.say("delvetalk scene enter")
        self.say("delvetalk scene choose\nchoice: Open")
        version = self.view()
        r = self.say("delvetalk scene enter")
        self.assertEqual(r["result"]["label"], "refused")
        self.assertTrue(why(r).startswith("alreadyHere"), why(r))
        self.assertEqual(self.view(), version)
        self.assertIn("you are at yard", self.card(GLM))

    def test_a_scene_without_its_start_passage_admits_nobody(self):
        self.scene(start="nowhere")
        r = self.say("delvetalk scene enter")
        self.assertTrue(why(r).startswith("noStart"), why(r))
        self.assertEqual(self.view()[1]["presence"], [])

    def test_a_choice_to_a_missing_passage_is_refused_and_writes_nothing(self):
        self.scene([passage("gate", "Edge.", [choice("Jump", "void", "fell", "yes")])])
        self.say("delvetalk scene enter")
        before = self.view()
        r = self.say("delvetalk scene choose\nchoice: Jump")
        self.assertTrue(why(r).startswith("noPassage"), why(r))
        self.assertEqual(self.view(), before)

    def test_the_largest_scene_fills_every_bound_and_the_next_is_refused(self):
        # Sixteen passages of eight choices: seven set a variable and stay, one goes on.
        passages = [passage("p%d" % i, "Passage %d, " % i + "x" * 60,
                            [choice("s%d" % j, "p%d" % i, "v%d_%d" % (i, j), "on" + "y" * 40) for j in range(7)]
                            + [choice("next", "p%d" % ((i + 1) % 16))]) for i in range(16)]
        self.scene(passages, start="p0")
        for n in range(16):
            self.assertEqual(self.say("delvetalk scene enter", "did:plc:r%d" % n)["result"]["label"], "done")
        r = self.say("delvetalk scene enter", "did:plc:r16")
        self.assertTrue(why(r).startswith("sceneFull"), why(r))
        self.assertEqual(len(self.view()[1]["presence"]), 16)
        who = "did:plc:r0"
        for n in range(16):
            if n and n % 7 == 0:
                self.say("delvetalk scene choose\nchoice: next", who)
            self.assertEqual(self.say("delvetalk scene choose\nchoice: s%d" % (n % 7), who)["result"]["label"], "done")
        full = self.card(who)
        print("--- the full scene, sixteen readers and sixteen variables ---\n" + full)
        self.assertEqual(len(self.view()[1]["vars"]), 16)
        self.assertIn("you are at p2", full)
        self.assertIn("(16 here)", full)
        before = self.view()
        r = self.say("delvetalk scene choose\nchoice: s2", who)
        self.assertTrue(why(r).startswith("varsFull"), why(r))
        self.assertEqual(self.view(), before)
        # An existing variable is still settable when the variables are full.
        self.assertEqual(self.say("delvetalk scene choose\nchoice: s0", who)["result"]["label"], "done")
        # The reader moves on only by an offered choice.
        self.assertEqual(self.say("delvetalk scene choose\nchoice: next", who)["result"]["label"], "done")
        self.assertIn("you are at p3", self.card(who))

    def test_a_forged_principal_cannot_be_sent_and_a_labelled_choice_of_another_passage_does_nothing(self):
        self.scene()
        self.say("delvetalk scene enter", GLM)
        before = self.view()
        for text in ("delvetalk scene choose\nchoice: Open\nprincipal: " + KIM,
                     "delvetalk scene enter\nprincipal: " + KIM,
                     "delvetalk scene choose\nwho: " + KIM + "\nchoice: Open"):
            with self.subTest(text=text):
                r = self.say(text, GLM)
                print("--- forged ---\n" + r["offers"][0]["text"].split("\n", 1)[0])
                self.assertEqual(r["result"]["label"], "refused")
        self.assertEqual(self.view(), before)
        self.assertEqual([p["who"] for p in self.view()[1]["presence"]], [GLM])
        # The method has no principal field; the host refuses one outright.
        r = self.turn("scene", "choose", record(choice=label("Open"), who=label(KIM)), principal=GLM)
        self.assertNotEqual(r["status"], "admitted", r)
        self.assertEqual(self.view(), before)
        # Turn-level choose moves only the turn's principal.
        r = self.turn("scene", "choose", record(choice=label("Open")), principal=KIM)
        self.assertEqual(r["status"], "admitted")
        self.assertTrue(r["result"]["payload"]["fields"][0]["value"]["value"].startswith("notHere"))
        self.assertEqual(self.view(), before)


if __name__ == "__main__":
    unittest.main()
