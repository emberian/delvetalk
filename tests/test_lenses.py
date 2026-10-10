"""An object's exposed fields are lenses: `set` writes one through its kind and its owner, `?` lists
every form and lens.

Evidence for FOUNDATION §5 Spell grammar (layer: objects).

Lenses: an object's exposed scalar fields, listed by `lenses()` as Form.Fields. The host answers
`delvetalk <card> set` with one `<field>: <value>` line by judging the value against the field's
kind and running the object's `set {field, value}` (which refuses a stranger by name; the law
judges the write); `delvetalk <card> ?` answers the usage card: every form, then every lens.
Policy's model, escalate and system and an Avatar's handle are lenses; Policy.setModel is gone.

Refuted by: a stranger's set changing the policy, a value outside its kind being written, a set of
two fields, a field without a lens, or `?` omitting a lens.
"""
import json
import unittest

from tests import test_chain, test_policy
from tests.test_chain import nil
from tests.test_objects import closure, compile_job
from tests.test_places import avatar_seed
from tests.test_turn_world import label, record

GLM = "did:plc:glm"


def heard(text):
    return record(text=label(text), post=label(""))


def why(reply):
    return reply["result"]["payload"]["fields"][1]["value"]["value"]


class Lenses(test_chain.Chain):
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
        # The host judges the value against the lens's kind (HOST-HANDOFF 5.54).
        over = self.turn("policy", "receive", record(text=label("delvetalk policy set\nsystem: " + "s" * 1001), post=label("")), principal="ember")
        out = over["receipt"]["outcome"]
        self.assertEqual((over["status"], out["class"], out["clause"], out["reason"]), ("refused", "badSpell", "badValue", "system takes 1 to 1000 characters."), over)
        self.assertEqual(self.version(), 1)

    def test_a_stranger_a_bad_value_two_fields_and_an_unlensed_field_change_nothing(self):
        self.policy()
        # The owner's guard is the policy's; the value's kind and the lens's name are the host's.
        r = self.say("delvetalk policy set\nmodel: evil", principal="glm")
        self.assertEqual((r["result"]["label"], why(r)), ("refused", "Only the policy's owner may teach it; that is ember"))
        self.assertIn("refused notOwner: Only the policy's owner may teach it; that is ember", r["offers"][0]["text"])
        cases = [
            ("delvetalk policy set\nmodel: " + "m" * 65, "badValue"),
            ("delvetalk policy set\nmodel: a\nescalate: b", "unknownField"),
            ("delvetalk policy set\nowner: glm", "unknownField"),
        ]
        for text, clause in cases:
            with self.subTest(text=text[:40]):
                r = self.turn("policy", "receive", record(text=label(text), post=label("")), principal="ember")
                self.assertEqual((r["status"], r["receipt"]["outcome"]["class"], r["receipt"]["outcome"]["clause"]), ("refused", "badSpell", clause), r)
        # No field line: the reply reaches receive, which answers with the card.
        self.assertEqual(self.say("delvetalk policy set", principal="ember")["result"]["label"], "usage")
        self.assertEqual((self.version(), self.field("model"), self.field("owner")), (0, "claude-haiku", "ember"))

    def test_the_usage_card_lists_every_form_and_every_lens(self):
        self.policy()
        # `?` is the host's usage: every form, then every lens (HOST-HANDOFF 5.54).
        r = self.turn("policy", "receive", record(text=label("delvetalk policy ?"), post=label("")), principal="ember")
        self.assertEqual(r["status"], "usage", r)
        text = r["text"]
        # The policy is its owner's (`request.subject == new.owner`): a stranger is offered none of it
        # (codex agent 11).
        stranger = self.turn("policy", "receive", record(text=label("delvetalk policy ?"), post=label("")), principal="glm")
        self.assertNotIn("delvetalk policy teach", stranger.get("text", ""))
        self.assertNotIn("delvetalk policy set", stranger.get("text", ""))
        for spell in ("delvetalk policy teach\nutterance:", "delvetalk policy macro\nname:", "delvetalk policy confirm\naction:",
                      "delvetalk policy set\nmodel: <text, 1 to 64 characters>", "delvetalk policy set\nescalate-to: <text, 0 to 160 characters>",
                      "delvetalk policy set\nsystem: <text, 1 to 1000 characters>"):
            self.assertIn(spell, text)
        self.assertEqual(self.version(), 0)

    def test_an_object_without_lenses_answers_set_and_question_by_its_forms(self):
        """The lantern speaks the message dialect: the host answers `?` from its method table and
        refuses `set` on a card without lenses."""
        self.make("lantern", closure("Lantern"), record())
        r = self.turn("lantern", "receive", heard("delvetalk lantern ?"), principal="ember")
        self.assertEqual(r["status"], "usage", r)
        self.assertTrue(r["text"].startswith("Reply with a spell:\n\ndelvetalk lantern light\n\ndelvetalk lantern watch\nobject: "), r)
        r = self.turn("lantern", "receive", heard("delvetalk lantern set\nlit: yes"), principal="ember")
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"]), ("refused", "badSpell"), r)
        print("\n  set on a card without lenses:", out["clause"], out["reason"])

    def test_an_avatars_handle_is_its_principals_to_set(self):
        self.make(GLM, closure("Avatar"), avatar_seed("glm", "porch"))
        other = self.say("delvetalk %s set\nhandle: mallory" % GLM, principal="did:plc:kimik3", obj=GLM)
        self.assertEqual(why(other), "Only glm changes it.")
        self.assertEqual(self.say("delvetalk %s set\nhandle: glm.bsky" % GLM, principal=GLM, obj=GLM)["result"]["label"], "done")
        self.assertEqual(self.field("handle", GLM), "glm.bsky")

    def test_set_model_is_no_longer_a_policy_method(self):
        self.assertNotEqual(compile_job(closure("Policy"), "setModel")["status"], "compiled")


if __name__ == "__main__":
    unittest.main()


class OwnedLenses(test_chain.Chain):
    """Lenses on the objects that had no owner: Garden (confirm), Place and Thing (name,
    description); Workshop has nothing to set and says so. Garden, Place and Thing declare a law
    that refuses the same write from anyone but the owner."""

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
        usage = self.turn("garden", "receive", record(text=label("delvetalk garden ?"), post=label("")), principal="glm")
        self.assertEqual(usage["status"], "usage", usage)
        self.assertIn("delvetalk garden set\nconfirm: <yes, no>\n", usage["text"])
        r = self.say("garden", "delvetalk garden set\nconfirm: no", "glm")
        self.assertEqual(r["result"]["payload"]["fields"][1]["value"], label("Only the garden's owner sets it; that is ember"))
        r = self.say("garden", "delvetalk garden set\nconfirm: no", "ember")
        self.assertEqual(r["result"]["label"], "changed", r)
        # A real owner is named by the handle the seed gave, never a fragment of its DID.
        owner = "did:plc:6amo7col5h4ciq2gpm5eur7b"
        self.make("garden2", closure("Garden"), record(owner=label(owner), ownerHandle=label("ember.delve.town")))
        r = self.say("garden2", "delvetalk garden2 set\nconfirm: no", "glm")
        self.assertEqual(r["result"]["payload"]["fields"][1]["value"], label("Only the garden's owner sets it; that is ember.delve.town"))
        merge = self.turn("garden2", "receive", record(text=label("merge"), post=label("at://glm/m")), principal="glm")
        self.assertIn("Only the page's owner, ember.delve.town, merges it.", json.dumps(merge))
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
        set_ = {"tag": "variant", "label": "set", "payload": record(value=label("mine now"))}
        r = self.forged("porch", (["name", "description", "present", "things", "traces"], {"name": set_}))
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"], r["receipt"]["outcome"].get("clause")), ("refused", "lawRefused", "owner"), r)

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
        r = self.turn("workshop", "receive", record(text=label("delvetalk workshop set\ntitle: Forge"), post=label("")), principal="ember")
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out["clause"]), ("refused", "badSpell", "noAction"), r)
        usage = self.turn("workshop", "receive", record(text=label("delvetalk workshop ?"), post=label("")), principal="glm")
        self.assertEqual(usage["status"], "usage", usage)
        self.assertIn("delvetalk workshop check", usage["text"])
