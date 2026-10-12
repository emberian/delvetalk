"""An object's exposed fields are lenses: `set` writes one through its kind and its owner, `?` lists
every form and lens.

Evidence for FOUNDATION §5 Spell grammar (layer: objects).

Lenses: an object's exposed scalar fields, listed by `lenses()` as Form.Fields. The host answers
`delvetalk <card> set` with one `<field>: <value>` line by judging the value against the field's
kind and running the object's `set {field, value}` (which refuses a stranger by name; the law
judges the write); `delvetalk <card> ?` answers the usage card: every form, then every lens.
Policy's model and an Avatar's handle are lenses; Policy.setModel is gone.

Refuted by: a stranger's set changing the policy, a value outside its kind being written, a set of
two fields, a field without a lens, or `?` omitting a lens.
"""
import unittest

from tests import test_chain, test_policy
from tests.host import as_owner
from tests.test_rooms import avatar_seed
from tests.wire import cast_refusal, label, record
from tests.bend import closure

GLM = "did:plc:glm"


def heard(text):
    return record(text=label(text), post=label(""))


def why(reply):
    return cast_refusal(reply)[1]


class Lenses(test_chain.Chain):
    policy = test_policy.PolicyObject.policy

    def say(self, text, principal="ember", obj="policy"):
        r = self.turn(obj, "receive", heard(text), principal=principal)
        if r["status"] == "refused":  # the card's refusal of its own spell refuses the turn
            self.assertEqual(r["receipt"]["outcome"]["class"], "cardRefused", r)
        else:
            self.assertEqual(r["status"], "admitted", r)
        return r

    def misfit(self, text):
        """A misfit spell waits on hob (OVERHAUL §2.7); hob's `none` leaves the host's refusal of it."""
        r = self.turn("policy", "receive", heard(text), principal="ember")
        self.assertEqual(r["status"], "suspended", r)
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"], reply={"status": "replied", "json": None, "raw": "none", "model": "m"})
        return as_owner(self.host, settled["resumed"][0], "ember")

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
        self.assertEqual(self.version(), 1)

    def test_the_longest_model_is_written_and_one_more_character_is_refused(self):
        self.policy()
        self.assertEqual(self.say("delvetalk policy set\nmodel: " + "s" * 64)["result"]["label"], "done")
        self.assertEqual(len(self.field("model")), 64)
        # The host judges the value against the lens's kind (HOST-HANDOFF 5.54).
        over = self.misfit("delvetalk policy set\nmodel: " + "s" * 65)
        out = over["receipt"]["outcome"]
        self.assertEqual((out["tag"], out["class"], out["clause"], out["reason"]), ("refused", "badSpell", "badValue", "model takes 1 to 64 characters."), over)
        self.assertEqual(self.version(), 1)

    def test_a_stranger_a_bad_value_two_fields_and_an_unlensed_field_change_nothing(self):
        self.policy()
        # The owner's guard is the policy's; the value's kind and the lens's name are the host's.
        r = self.say("delvetalk policy set\nmodel: evil", principal="glm")
        self.assertEqual(why(r), "Only the policy's owner may change it; that is ember")
        self.assertEqual(r["receipt"]["outcome"]["reason"], "refused notOwner: Only the policy's owner may change it; that is ember")
        cases = [
            ("delvetalk policy set\nmodel: " + "m" * 65, "badValue"),
            ("delvetalk policy set\nmodel: a\nowner: b", "unknownField"),
            ("delvetalk policy set\nowner: glm", "unknownField"),
        ]
        for text, clause in cases:
            with self.subTest(text=text[:40]):
                r = self.misfit(text)
                self.assertEqual((r["receipt"]["outcome"]["tag"], r["receipt"]["outcome"]["class"], r["receipt"]["outcome"]["clause"]), ("refused", "badSpell", clause), r)
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
    """Lenses on the objects that had no owner: Thing (name, description);
    Workshop has nothing to set and says so. A Thing's law, not its code, refuses the write
    from anyone but its keeper (its owner while unclaimed), so a lent `set` runs. A room and the
    garden are records and have no lenses."""

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

    def test_a_things_owner_sets_its_fields_and_the_law_keeps_others_out(self):
        from tests.test_rooms import thing_seed
        self.make("stone", closure("Thing"), thing_seed("stone"))
        set_ = {"tag": "variant", "label": "set", "payload": record(value=label("mine now"))}
        for obj, kind, fields in (("stone", "thing", ["name", "description", "holder", "location"]),):
            r = self.turn(obj, "receive", heard("delvetalk %s set\nname: renamed" % obj), principal="glm")
            self.assertEqual((r["status"], r["receipt"]["outcome"].get("clause")), ("refused", "owner"), r)
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
