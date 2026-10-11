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
from tests.test_chain import town_kinds
from tests.test_places import avatar_seed
from tests.wire import label, record
from tests.bend import closure

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


    def test_an_avatars_handle_is_its_principals_to_set(self):
        self.make(GLM, closure("Avatar"), avatar_seed("glm", "porch"))
        other = self.say("delvetalk %s set\nhandle: mallory" % GLM, principal="did:plc:kimik3", obj=GLM)
        self.assertEqual(why(other), "Only glm changes it.")
        self.assertEqual(self.say("delvetalk %s set\nhandle: glm.bsky" % GLM, principal=GLM, obj=GLM)["result"]["label"], "done")
        self.assertEqual(self.field("handle", GLM), "glm.bsky")



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
        town_kinds(self.host.send)
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

    def test_a_rooms_and_a_things_owner_sets_their_fields_and_the_law_keeps_others_out(self):
        from tests.test_places import make_place, place_seed, thing_seed
        make_place(self, "porch", place_seed("Porch"))
        self.make("stone", closure("Thing"), thing_seed("stone"))
        set_ = {"tag": "variant", "label": "set", "payload": record(value=label("mine now"))}
        for obj, kind, fields in (("porch", "room", ["name", "description", "present", "things", "traces"]),
                                  ("stone", "thing", ["name", "description", "holder", "location"])):
            r = self.say(obj, "delvetalk %s set\nname: renamed" % obj, "glm")
            self.assertEqual(r["result"]["payload"]["fields"][1]["value"], label("Only the %s's owner changes it; that is ember" % kind))
            self.assertEqual(self.say(obj, "delvetalk %s set\ndescription: moths" % obj, "ember")["result"]["label"], "done")
            self.assertEqual(self.say(obj, "delvetalk %s set\nname: renamed" % obj, "ember")["result"]["label"], "done")
            self.assertEqual((self.field(obj, "name"), self.field(obj, "description")), ("renamed", "moths"))
            r = self.forged(obj, (fields, {"name": set_}))
            self.assertEqual((r["status"], r["receipt"]["outcome"]["class"], r["receipt"]["outcome"].get("clause")), ("refused", "lawRefused", "owner"), r)

    def test_a_card_without_lenses_refuses_set_and_answers_question_with_its_forms(self):
        """The lantern speaks the message dialect; the workshop has nothing to set: the host answers
        `?` from the method table and refuses `set` by name."""
        self.make("lantern", closure("Lantern"), record())
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))
        for obj, form in (("lantern", "delvetalk lantern light"), ("workshop", "delvetalk workshop check")):
            r = self.turn(obj, "receive", heard("delvetalk %s set\ntitle: Forge" % obj), principal="ember")
            self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "badSpell"), r)
            usage = self.turn(obj, "receive", heard("delvetalk %s ?" % obj), principal="glm")
            self.assertEqual(usage["status"], "usage", usage)
            self.assertIn(form, usage["text"])

if __name__ == "__main__":
    unittest.main()
