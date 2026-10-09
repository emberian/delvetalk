"""Lenses (FOUNDATION section 13, row 2): an object's exposed scalar fields as Form.Lens {field,
form, put}. Card's answerLensed answers `delvetalk <card> set` with one `<field>: <value>` line by
judging the value against the lens's kind and writing the lens's put; `delvetalk <card> ?` answers
the usage card: every form, then every lens. Policy's model, escalate and system and an Avatar's
handle are lenses; Policy.setModel is gone.

Refuted by: a stranger's set changing the policy, a value outside its kind being written, a set of
two fields, a field without a lens, or `?` omitting a lens."""
import unittest

from tests import test_chain, test_policy
from tests.test_chain import nil
from tests.test_objects import closure, compile_job
from tests.test_places import avatar_seed
from tests.test_turn_world import label, record

GLM = "did:plc:glm"


def heard(text):
    return record(text=label(text), post=label(""), slot=label(""))


def why(reply):
    return reply["result"]["payload"]["fields"][0]["value"]["value"]


class Lenses(test_chain.Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None
    policy = test_policy.PolicyObject.policy

    def say(self, text, principal="ember", obj="policy"):
        r = self.turn(obj, "receive", heard(text), principal=principal)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def field(self, name, obj="policy"):
        return [f["value"]["value"] for f in self.state(obj)["fields"] if f["name"] == name][0]

    def version(self, obj="policy"):
        return self.host.send(op="world-view", principal="ember", object=obj)["version"]

    def test_the_owner_sets_a_field_through_its_lens(self):
        self.policy()
        r = self.say("delvetalk policy set\nmodel: claude-sonnet")
        self.assertEqual(r["result"]["label"], "done")
        self.assertEqual(r["offers"][0]["text"], "Set model to claude-sonnet.\n")
        self.assertEqual(self.field("model"), "claude-sonnet")
        self.assertEqual(self.say("delvetalk policy set escalate: claude-opus")["result"]["label"], "done")
        self.assertEqual(self.field("escalate"), "claude-opus")
        # escalate takes 0 characters: the empty value clears it.
        self.assertEqual(self.say("delvetalk policy set\nescalate:")["result"]["label"], "done")
        self.assertEqual(self.field("escalate"), "")
        self.assertEqual(self.version(), 3)

    def test_the_longest_system_is_written_and_one_more_character_is_refused(self):
        self.policy()
        self.assertEqual(self.say("delvetalk policy set\nsystem: " + "s" * 1000)["result"]["label"], "done")
        self.assertEqual(len(self.field("system")), 1000)
        over = self.say("delvetalk policy set\nsystem: " + "s" * 1001)
        self.assertEqual((over["result"]["label"], why(over)), ("refused", "system takes 1 to 1000 characters."))
        self.assertEqual(self.version(), 1)

    def test_a_stranger_a_bad_value_two_fields_and_an_unlensed_field_change_nothing(self):
        self.policy()
        cases = [
            ("delvetalk policy set\nmodel: evil", "glm", "Only the policy's owner may teach it; that is ember"),
            ("delvetalk policy set\nmodel: " + "m" * 65, "ember", "model takes 1 to 64 characters."),
            ("delvetalk policy set\nmodel: a\nescalate: b", "ember", "set takes one field: value line."),
            ("delvetalk policy set\nowner: glm", "ember", "No field called owner can be set here."),
            ("delvetalk policy set", "ember", "set takes one field: value line."),
        ]
        for text, who, reason in cases:
            with self.subTest(text=text[:40]):
                r = self.say(text, principal=who)
                self.assertEqual((r["result"]["label"], why(r)), ("refused", reason))
                self.assertIn("Not done: " + reason, r["offers"][0]["text"])
        self.assertEqual((self.version(), self.field("model"), self.field("owner")), (0, "claude-haiku", "ember"))

    def test_the_usage_card_lists_every_form_and_every_lens(self):
        self.policy()
        r = self.say("delvetalk policy ?", principal="glm")
        text = r["offers"][0]["text"]
        print("\n--- policy ? ---\n" + text)
        self.assertEqual(r["result"]["label"], "usage")
        self.assertEqual(text, "\nReply with a spell:\n\n    delvetalk policy teach\n    utterance: <text, 1 to 280 characters>\n"
                               "    spell: <text, 1 to 280 characters>\n\n    delvetalk policy define\n    word: <text, 1 to 64 characters>\n"
                               "    meaning: <text, 1 to 280 characters>\n\nTo change a field, reply (one field a spell):\n\n"
                               "    delvetalk policy set\n    model: <text, 1 to 64 characters>\n\n    delvetalk policy set\n"
                               "    escalate: <text, 0 to 64 characters>\n\n    delvetalk policy set\n    system: <text, 1 to 1000 characters>\n")
        self.assertEqual(self.version(), 0)

    def test_an_object_without_lenses_answers_set_and_question_by_its_forms(self):
        self.make("lantern", closure("Lantern"), record())
        r = self.say("delvetalk lantern ?", obj="lantern")
        self.assertEqual(r["offers"][0]["text"], "\nReply with a spell:\n\n    delvetalk lantern light\n")
        r = self.say("delvetalk lantern set\nlit: yes", obj="lantern")
        self.assertEqual((r["result"]["label"], why(r)), ("refused", "Nothing here can be set."))

    def test_an_avatars_handle_is_its_principals_to_set(self):
        self.make(GLM, closure("Avatar"), avatar_seed("glm", "porch"))
        other = self.say("delvetalk %s set\nhandle: mallory" % GLM, principal="did:plc:kimik3", obj=GLM)
        self.assertEqual(why(other), "Only the avatar's own principal changes it.")
        self.assertEqual(self.say("delvetalk %s set\nhandle: glm.bsky" % GLM, principal=GLM, obj=GLM)["result"]["label"], "done")
        self.assertEqual(self.field("handle", GLM), "glm.bsky")

    def test_set_model_is_gone(self):
        self.assertNotEqual(compile_job(closure("Policy"), "setModel")["status"], "compiled")


if __name__ == "__main__":
    unittest.main()
