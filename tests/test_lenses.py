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
    return reply["result"]["payload"]["fields"][1]["value"]["value"]


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
            ("delvetalk policy set\nmodel: evil", "glm", "notOwner", "Only the policy's owner may teach it; that is ember"),
            ("delvetalk policy set\nmodel: " + "m" * 65, "ember", "badValue", "model takes 1 to 64 characters."),
            ("delvetalk policy set\nmodel: a\nescalate: b", "ember", "oneField", "set takes one field: value line."),
            ("delvetalk policy set\nowner: glm", "ember", "noField", "No field called owner can be set here."),
            ("delvetalk policy set", "ember", "oneField", "set takes one field: value line."),
        ]
        for text, who, clause, reason in cases:
            with self.subTest(text=text[:40]):
                r = self.say(text, principal=who)
                self.assertEqual((r["result"]["label"], why(r)), ("refused", reason))
                self.assertIn("refused %s: %s" % (clause, reason), r["offers"][0]["text"])
        self.assertEqual((self.version(), self.field("model"), self.field("owner")), (0, "claude-haiku", "ember"))

    def test_the_usage_card_lists_every_form_and_every_lens(self):
        self.policy()
        r = self.say("delvetalk policy ?", principal="glm")
        text = r["offers"][0]["text"]
        print("\n--- policy ? ---\n" + text)
        self.assertEqual(r["result"]["label"], "usage")
        self.assertEqual(text, "\nReply with a spell:\n\n    delvetalk policy teach\n    utterance: <text, 1 to 280 characters>\n"
                               "    spell: <text, 1 to 280 characters>\n\n    delvetalk policy define\n    word: <text, 1 to 64 characters>\n"
                               "    meaning: <text, 1 to 280 characters>\n\n    delvetalk policy macro\n    name: <text, 1 to 64 characters>\n"
                               "    pattern: <text, 1 to 280 characters>\n    expansion: <text, 1 to 280 characters>\n\n"
                               "    delvetalk policy confirm\n    action: <text, 1 to 64 characters>\n    ask: <yes, no>\n\nTo change a field, reply (one field a spell):\n\n"
                               "    delvetalk policy set\n    model: <text, 1 to 64 characters>\n\n    delvetalk policy set\n"
                               "    escalate: <text, 0 to 64 characters>\n\n    delvetalk policy set\n    escalate-to: <text, 0 to 160 characters>\n\n"
                               "    delvetalk policy set\n    system: <text, 1 to 1000 characters>\n")
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


class OwnedLenses(test_chain.Chain):
    """Lenses on the objects that had no owner: Garden (confirm), Place and Thing (name,
    description); Workshop has nothing to set and says so. Garden and Thing declare a law that
    refuses the same write from anyone but the owner; Place is imported by Thing and Avatar, so
    its guard is its code's alone."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def say(self, obj, text, who):
        r = self.turn(obj, "receive", heard(text), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def field(self, obj, name):
        return [f["value"]["value"] for f in self.state(obj)["fields"] if f["name"] == name][0]

    def listed(self, obj, name):
        return [i["value"] for i in [f["value"] for f in self.state(obj)["fields"] if f["name"] == name][0]["items"]]

    def forged(self, obj, edits):
        keep = {"tag": "variant", "label": "keep", "payload": record()}
        version = self.host.send(op="world-view", principal="ember", object=obj)["version"]
        fields = {name: keep for name in edits[0]}
        fields.update(edits[1])
        return self.host.send(op="world-propose", principal="did:plc:mallory", identity="forged-" + obj,
                              roots=[{"object": obj, "version": version}], writes=[{"object": obj, "edits": [record(**fields)]}])

    def test_the_gardens_owner_sets_confirm(self):
        from tests.test_chain import garden_seed
        self.make("garden", closure("Garden"), garden_seed())
        usage = self.say("garden", "delvetalk garden ?", "glm")["offers"][0]["text"]
        self.assertIn("    delvetalk garden set\n    confirm: <yes, no>\n", usage)
        r = self.say("garden", "delvetalk garden set\nconfirm: no", "glm")
        self.assertEqual(r["result"]["payload"]["fields"][1]["value"], label("Only the garden's owner sets it; that is ember"))
        r = self.say("garden", "delvetalk garden set\nconfirm: no", "ember")
        self.assertEqual(r["result"]["label"], "changed", r)
        self.assertEqual(self.listed("garden", "confirmFor"), [])
        r = self.say("garden", "delvetalk garden set\nconfirm: yes", "ember")
        self.assertEqual(self.listed("garden", "confirmFor"), ["plant"])
        append = {"tag": "variant", "label": "append", "payload": record(item=label("give"))}
        r = self.forged("garden", (["planted", "confirmFor", "pending", "children", "pageCheckpoint"], {"confirmFor": append}))
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"], r["receipt"]["outcome"].get("clause")), ("refused", "lawRefused", "owner"), r)

    def test_a_rooms_owner_renames_it(self):
        from tests.test_places import place_seed
        self.make("porch", closure("Place"), place_seed("Porch"))
        r = self.say("porch", "delvetalk porch set\nname: Back Porch", "glm")
        self.assertEqual(r["result"]["payload"]["fields"][1]["value"], label("Only the room's owner changes it; that is ember"))
        self.assertEqual(self.say("porch", "delvetalk porch set\ndescription: moths at the lamp", "ember")["result"]["label"], "done")
        self.assertEqual(self.say("porch", "delvetalk porch set\nname: Back Porch", "ember")["result"]["label"], "done")
        self.assertEqual((self.field("porch", "name"), self.field("porch", "description")), ("Back Porch", "moths at the lamp"))

    def test_a_things_owner_redescribes_it_and_the_law_keeps_others_out(self):
        from tests.test_places import thing_seed
        self.make("stone", closure("Thing"), thing_seed("stone"))
        r = self.say("stone", "delvetalk stone set\nname: pebble", "glm")
        self.assertEqual(r["result"]["payload"]["fields"][1]["value"], label("Only the thing's owner changes it; that is ember"))
        self.assertEqual(self.say("stone", "delvetalk stone set\ndescription: warm from the sun", "ember")["result"]["label"], "done")
        self.assertEqual(self.field("stone", "description"), "warm from the sun")
        set_ = {"tag": "variant", "label": "set", "payload": record(value=label("mine now"))}
        r = self.forged("stone", (["name", "description", "holder", "location"], {"name": set_}))
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"], r["receipt"]["outcome"].get("clause")), ("refused", "lawRefused", "owner"), r)

    def test_the_workshop_has_nothing_to_set_and_says_so(self):
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))
        r = self.say("workshop", "delvetalk workshop set\ntitle: Forge", "ember")
        self.assertEqual(r["offers"][0]["text"], "Not done: Nothing here can be set: the workshop keeps no settings of its own.\n")
        self.assertIn("delvetalk workshop check", self.say("workshop", "delvetalk workshop ?", "glm")["offers"][0]["text"])
