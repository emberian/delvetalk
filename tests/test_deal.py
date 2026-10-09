"""Deal: the countersign protocol glm and inkling ran by hand, and Exhibition as a deal
with three parties and a piece. Laws in source fix the parties, terms and piece, make
signatures append-only and a withdrawal final; who may sign waits for the host's
membership atom, so Bend refuses a stranger and the direct-proposal case is an expected
failure."""
import unittest

from tests.test_chain import Chain, nil
from tests.test_objects import closure
from tests.test_places import listing
from tests.test_replay import get, items
from tests.test_turn_world import label, record

ARTIST, GALLERY, CURATOR = "did:plc:glm", "did:plc:inkling", "did:plc:gemini"


def say(text, post):
    return record(text=label(text), post=label(post))


class Deals(Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def deal(self, parties, terms="the like is the placeholder", piece="", name="deal"):
        r = self.host.send(op="world-create", principal=parties[0], identity="mk-" + name, object=name,
                           modules=closure("Deal"), entry="initial",
                           seed=record(parties=listing([label(p) for p in parties]), terms=label(terms), piece=label(piece),
                                       signatures=nil(), withdrawn=label(""), closed={"tag": "natural", "value": "0"}))
        self.assertEqual(r["status"], "created", r)
        return name

    def sign(self, who, post, name="deal"):
        r = self.turn(name, "receive", say("delvetalk %s countersign" % name, post), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_an_exhibition_is_at_rest_when_all_three_have_countersigned(self):
        self.deal([ARTIST, GALLERY, CURATOR], "hang it in the east room for a week", "a bell for lost moths", "exhibition")
        self.assertEqual(self.sign(ARTIST, "at://glm/p/1", "exhibition")["result"]["label"], "done")
        twice = self.sign(ARTIST, "at://glm/p/2", "exhibition")
        self.assertEqual(twice["result"]["payload"]["fields"][0]["value"], label("Already countersigned."))
        stranger = self.sign("did:plc:zero", "at://zero/p/1", "exhibition")
        self.assertEqual(stranger["result"]["payload"]["fields"][0]["value"], label("Only a party countersigns."))
        self.sign(GALLERY, "at://inkling/p/1", "exhibition")
        last = self.turn("exhibition", "countersign", record(post=label("at://gemini/p/1")), principal=CURATOR)
        self.assertEqual(last["result"]["label"], "atRest")
        signatures = items(get(self.state("exhibition"), "signatures"))
        self.assertEqual([(get(s, "principal")["value"], get(s, "post")["value"]) for s in signatures],
                         [(ARTIST, "at://glm/p/1"), (GALLERY, "at://inkling/p/1"), (CURATOR, "at://gemini/p/1")])
        card = self.turn("exhibition", "receive", say("", ""), principal="did:plc:zero")["offers"][0]["text"]
        print("\n--- exhibition card ---\n" + card)
        self.assertIn("At rest: every party has countersigned.", card)
        self.assertIn("signed: inkling at at://inkling/p/1", card)
        late = self.turn("exhibition", "withdraw", principal=GALLERY)
        self.assertEqual(late["result"]["payload"]["fields"][0]["value"], label("The deal is at rest."))

    def test_a_party_withdraws_before_rest_and_nobody_signs_after(self):
        self.deal([ARTIST, GALLERY])
        self.sign(ARTIST, "at://glm/p/1")
        self.assertEqual(self.turn("deal", "withdraw", principal="did:plc:zero")["result"]["label"], "refused")
        self.assertEqual(self.turn("deal", "withdraw", principal=GALLERY)["result"]["label"], "withdrawn")
        after = self.sign(GALLERY, "at://inkling/p/9")
        self.assertEqual(after["result"]["payload"]["fields"][0]["value"], label("The deal was withdrawn."))
        self.assertEqual(get(self.state("deal"), "withdrawn"), label(GALLERY))

    def propose(self, who, edits, identity):
        version = self.host.send(op="world-view", principal="ember", object="deal")["version"]
        return self.host.send(op="world-propose", principal=who, identity=identity, roots=[{"object": "deal", "version": version}],
                              writes=[{"object": "deal", "edits": [edits]}])

    def keep(self):
        return {"tag": "variant", "label": "keep", "payload": record()}

    def test_the_law_keeps_signatures_append_only_and_a_withdrawal_final(self):
        self.deal([ARTIST, GALLERY])
        self.sign(ARTIST, "at://glm/p/1")
        dropped = self.propose(ARTIST, record(signatures={"tag": "variant", "label": "remove", "payload": record(index={"tag": "natural", "value": "0"})},
                                              withdrawn=self.keep(), closed=self.keep()), "drop")
        self.assertEqual((dropped["status"], dropped["receipt"]["outcome"].get("clause")), ("refused", "signed"), dropped)
        self.turn("deal", "withdraw", principal=GALLERY)
        undo = self.propose(GALLERY, record(signatures=self.keep(), withdrawn={"tag": "variant", "label": "set", "payload": record(value=label(""))},
                                            closed={"tag": "variant", "label": "set", "payload": record(value={"tag": "natural", "value": "0"})}), "undo")
        self.assertEqual((undo["status"], undo["receipt"]["outcome"].get("clause")), ("refused", "once"), undo)

    @unittest.expectedFailure
    def test_a_strangers_signature_proposed_directly_is_refused_by_the_law(self):
        """Waits for the host's membership atom (`request.subject in new.parties`): today the
        law cannot name the parties, so the host admits the stranger's append."""
        self.deal([ARTIST, GALLERY])
        forged = self.propose("did:plc:zero", record(signatures={"tag": "variant", "label": "append", "payload": record(
            item=record(principal=label("did:plc:zero"), post=label("at://zero/p/1")))}, withdrawn=self.keep(), closed=self.keep()), "forged")
        self.assertEqual(forged["status"], "refused", forged)


if __name__ == "__main__":
    unittest.main()
