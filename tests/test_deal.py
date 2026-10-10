"""A Deal at rest, countersigned by every party, applies its amendment under the target's own law;
its own law keeps signatures append-only and a withdrawal final.

Evidence for FOUNDATION §8 governance (layer: objects).

Deal: the countersign protocol glm and inkling ran by hand, and Exhibition as a deal
with three parties and a piece. Laws in source fix the parties, terms and piece, make
signatures append-only and a withdrawal final, and admit only a party's change
(`request.subject in new.parties`). A countersignature is a reply: `countersign {}` cites the
post the spell came in (`context.inputOrigin.post`), and a turn from no post is refused `unposted`.
"""
import unittest

from tests.test_turn_world import relation
from tests.test_replay import rows
from tests.test_chain import Chain, nil
from tests.test_objects import closure
from tests.test_places import listing
from tests.test_replay import get, items
from tests.test_turn_world import label, record

ARTIST, GALLERY, CURATOR = "did:plc:glm", "did:plc:inkling", "did:plc:gemini"


def say(text, post):
    return record(text=label(text), post=label(post))


class Deals(Chain):

    def deal(self, parties, terms="the like is the placeholder", piece="", name="deal"):
        r = self.host.send(op="world-create", principal=parties[0], identity="mk-" + name, object=name,
                           modules=closure("Deal"), entry="initial",
                           seed=record(amendment=record(object=label(""), law=label("")), parties=listing([label(p) for p in parties]), terms=label(terms), piece=label(piece),
                                       signatures=relation(), withdrawn=label(""), closed={"tag": "natural", "value": "0"}))
        self.assertEqual(r["status"], "created", r)
        return name

    def sign(self, who, post, name="deal"):
        r = self.turn(name, "receive", say("delvetalk %s countersign" % name, post), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_three_countersignatures_amend_an_objects_law_and_a_stranger_is_refused(self):
        """A deal at rest applies its amendment by `amend`, the deal as caller, judged by the
        object's own law."""
        from tests.test_objects import MODULES
        from tests.test_turn_world import closure as world_closure
        law = 'law steward: request.subject == "ember" or request.caller == "deal"\n'
        source = open(MODULES["Counter"]).read().replace("record State:", law + "record State:", 1)
        r = self.host.send(op="world-create", principal="ember", identity="mk-ledger", object="ledger",
                           modules=world_closure("Counter", override={"Counter": source}), entry="initial", seed=record(count={"tag": "natural", "value": "0"}))
        self.assertEqual(r["status"], "created", r)
        new = 'law steward: request.caller == "deal" or request.subject == "did:plc:glm"'
        r = self.host.send(op="world-create", principal=ARTIST, identity="mk-deal", object="deal", modules=closure("Deal"), entry="initial",
                           seed=record(amendment=record(object=label("ledger"), law=label(new)), parties=listing([label(p) for p in (ARTIST, GALLERY, CURATOR)]),
                                       terms=label("glm stewards the ledger"), piece=label(""), signatures=relation(), withdrawn=label(""), closed={"tag": "natural", "value": "0"}))
        self.assertEqual(r["status"], "created", r)
        self.assertIn("At rest it amends ledger to:\n    " + new, self.turn("deal", "receive", say("", ""), principal="did:plc:zero")["offers"][0]["text"])
        stranger = self.sign("did:plc:zero", "at://zero/p/1")
        self.assertEqual(stranger["result"]["label"], "refused")
        self.assertEqual([self.sign(who, "at://%s/p" % who)["result"]["label"] for who in (ARTIST, GALLERY, CURATOR)], ["signed", "signed", "atRest"])
        inspected = self.host.send(op="world-inspect", principal="ember", object="ledger")
        self.assertIn('request.caller == "deal"', inspected["law"])
        self.assertIn('did:plc:glm', inspected["law"])

    def test_an_exhibition_is_at_rest_when_all_three_have_countersigned(self):
        self.deal([ARTIST, GALLERY, CURATOR], "hang it in the east room for a week", "a bell for lost moths", "exhibition")
        self.assertEqual(self.sign(ARTIST, "at://glm/p/1", "exhibition")["result"]["label"], "signed")
        twice = self.sign(ARTIST, "at://glm/p/2", "exhibition")
        self.assertEqual(twice["result"]["payload"]["fields"][1]["value"], label("Already countersigned."))
        stranger = self.sign("did:plc:zero", "at://zero/p/1", "exhibition")
        self.assertEqual(stranger["result"]["payload"]["fields"][1]["value"], label("Only a party countersigns."))
        self.sign(GALLERY, "at://inkling/p/1", "exhibition")
        # A countersign turn from no post signs nothing, even a party's; its reply cites one.
        unposted = self.turn("exhibition", "countersign", principal=CURATOR)
        self.assertEqual(unposted["result"]["payload"]["fields"][0]["value"], label("unposted"))
        self.assertEqual(self.sign(CURATOR, "at://gemini/p/1", "exhibition")["result"]["label"], "atRest")
        signatures = rows(get(self.state("exhibition"), "signatures"))
        signed = [(ARTIST, "at://glm/p/1"), (GALLERY, "at://inkling/p/1"), (CURATOR, "at://gemini/p/1")]
        self.assertEqual([(get(s, "principal")["value"], get(s, "post")["value"]) for s in signatures],
                         sorted(signed, key=lambda s: (len(s[0].encode()), s[0].encode())))   # key order
        card = self.turn("exhibition", "receive", say("", ""), principal="did:plc:zero")["offers"][0]["text"]
        self.assertEqual(card, (
            "DEAL for a bell for lost moths\n"
            "\n"
            "Terms: hang it in the east room for a week\n"
            "\n"
            "signed: glm at at://glm/p/1\n"          # in key order: the shorter DID first
            "signed: gemini at at://gemini/p/1\n"
            "signed: inkling at at://inkling/p/1\n"
            "At rest: every party has countersigned.\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk exhibition countersign\n"
            "\n"
            "    delvetalk exhibition withdraw\n"))
        self.assertIn("At rest: every party has countersigned.", card)
        self.assertIn("signed: inkling at at://inkling/p/1", card)
        late = self.turn("exhibition", "withdraw", principal=GALLERY)
        self.assertEqual(late["result"]["payload"]["fields"][1]["value"], label("The deal is at rest."))

    def test_a_party_withdraws_before_rest_and_nobody_signs_after(self):
        self.deal([ARTIST, GALLERY])
        self.sign(ARTIST, "at://glm/p/1")
        self.assertEqual(self.turn("deal", "withdraw", principal="did:plc:zero")["result"]["label"], "refused")
        self.assertEqual(self.turn("deal", "withdraw", principal=GALLERY)["result"]["label"], "withdrawn")
        after = self.sign(GALLERY, "at://inkling/p/9")
        self.assertEqual(after["result"]["payload"]["fields"][1]["value"], label("The deal was withdrawn."))
        self.assertEqual(get(self.state("deal"), "withdrawn"), label(GALLERY))

    def propose(self, who, edits, identity):
        version = self.host.send(op="world-view", principal="ember", object="deal")["version"]
        return self.host.send(op="world-propose", principal=who, identity=identity, roots=[{"object": "deal", "version": version}],
                              writes=[{"object": "deal", "edits": [edits]}])

    def keep(self):
        return {"tag": "variant", "label": "keep", "payload": record()}

    def test_the_law_keeps_signatures_insert_only_and_a_withdrawal_final(self):
        self.deal([ARTIST, GALLERY])
        self.sign(ARTIST, "at://glm/p/1")
        dropped = self.propose(ARTIST, record(signatures={"tag": "variant", "label": "retract", "payload": record(key=record(principal=label(ARTIST)))},
                                              withdrawn=self.keep(), withdrawnHandle=self.keep(), closed=self.keep()), "drop")
        self.assertEqual((dropped["status"], dropped["receipt"]["outcome"].get("clause")), ("refused", "signed"), dropped)
        self.turn("deal", "withdraw", principal=GALLERY)
        undo = self.propose(GALLERY, record(signatures=self.keep(), withdrawn={"tag": "variant", "label": "set", "payload": record(value=label(""))},
                                            withdrawnHandle=self.keep(), closed={"tag": "variant", "label": "set", "payload": record(value={"tag": "natural", "value": "0"})}), "undo")
        self.assertEqual((undo["status"], undo["receipt"]["outcome"].get("clause")), ("refused", "once"), undo)

    def test_a_strangers_signature_proposed_directly_is_refused_by_the_law(self):
        """The membership atom: `request.subject in new.parties`."""
        self.deal([ARTIST, GALLERY])
        forged = self.propose("did:plc:zero", record(signatures={"tag": "variant", "label": "insert", "payload": record(
            row=record(principal=label("did:plc:zero"), handle=label(""), post=label("at://zero/p/1")))}, withdrawn=self.keep(), withdrawnHandle=self.keep(), closed=self.keep()), "forged")
        self.assertEqual((forged["status"], forged["receipt"]["outcome"].get("clause")), ("refused", "members"), forged)


if __name__ == "__main__":
    unittest.main()
