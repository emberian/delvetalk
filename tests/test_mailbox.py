"""The mailbox on Avatar (ported from main's protocols/resident-library/Mailbox.obend, its consent
and queue replaced by observers and the inbox): an avatar subscribes to an object (it sends the
object `observe` naming itself, and remembers following it); its principal's `send` tells every
observer, bounded by the host's sendsPerTurn (32: a turn past it is refused whole), so the mailing
list holds 32; the inbox keeps the newest 64.

Refuted by: a stranger sending from someone's avatar or adding an observer other than itself; a
33rd observer admitted; a send to 32 observers not sending 32; a 65th note not dropping the oldest."""
import unittest

from tests import test_chain
from tests.test_places import avatar_seed
from tests.test_replay import get, items
from tests.test_turn_world import closure, label, record

GLM, KIM = "did:plc:glm", "did:plc:kimik3"


def heard(text):
    return record(text=label(text), post=label(""), slot=label(""))


def observer(obj, method="note"):
    return record(object=record(world=label(""), object=label(obj)), method=label(method))


class Mailbox(test_chain.Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def setUp(self):
        super().setUp()
        for did, handle in ((GLM, "glm"), (KIM, "kimik3")):
            self.make(did, closure("Avatar"), avatar_seed(handle, "porch"))

    def say(self, obj, text, who):
        r = self.turn(obj, "receive", heard(text), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def inbox(self, did):
        return [(get(n, "from")["value"], get(n, "text")["value"]) for n in items(get(self.state(did), "inbox"))]

    def test_subscribe_then_send_reaches_the_follower(self):
        r = self.say(KIM, "delvetalk %s subscribe\nto: %s" % (KIM, GLM), KIM)
        self.assertEqual(r["result"]["label"], "done", r)
        self.deliver_all()
        observers = items(get(self.state(GLM), "observers"))
        self.assertEqual([(get(get(o, "object"), "object")["value"], get(o, "method")["value"]) for o in observers], [(KIM, "note")])
        self.assertEqual([get(f, "object")["value"] for f in items(get(self.state(KIM), "following"))], [GLM])
        sent = self.say(GLM, "delvetalk %s send\ntext: the moths are out" % GLM, GLM)
        self.assertEqual(sent["result"]["label"], "done", sent)
        self.deliver_all()
        self.assertEqual(self.inbox(KIM), [(GLM, "the moths are out")])
        card = self.say(KIM, "", KIM)["offers"][0]["text"]
        print("\n--- kimik3's own card ---\n" + card)
        self.assertIn("0 following, follows 1\nFollows: glm\n", card)
        self.assertIn("glm: the moths are out\n", card)
        # Unsubscribing removes both sides.
        self.assertEqual(self.say(KIM, "delvetalk %s unsubscribe\nto: %s" % (KIM, GLM), KIM)["result"]["label"], "done")
        self.deliver_all()
        self.assertEqual(items(get(self.state(GLM), "observers")), [])
        self.assertEqual(items(get(self.state(KIM), "following")), [])

    def test_a_bell_tells_its_follower_when_it_rings(self):
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("moths"), planting=label("p"), planter=label(GLM), planterHandle=label("")))
        self.assertEqual(self.say(KIM, "delvetalk %s subscribe\nto: bell" % KIM, KIM)["result"]["label"], "done")
        self.deliver_all()
        self.assertEqual(self.turn("bell", "ring", principal=GLM)["status"], "admitted")
        self.deliver_all()
        self.assertEqual(self.inbox(KIM), [("bell", "news from bell")])

    def test_strangers_neither_send_nor_add_others(self):
        r = self.say(GLM, "delvetalk %s send\ntext: forged" % GLM, KIM)
        self.assertEqual(r["result"]["payload"]["fields"][1]["value"], label("Only the avatar's own principal sends from it."))
        r = self.turn(GLM, "observe", observer("did:plc:victim"), principal="did:plc:mallory")
        self.assertEqual(r["result"]["payload"]["fields"][0]["value"], label("An observer adds only itself."))
        twice = self.say(KIM, "delvetalk %s subscribe\nto: %s" % (KIM, GLM), GLM)
        self.assertEqual(twice["result"]["payload"]["fields"][1]["value"], label("Only the avatar's own principal subscribes it."))
        self.assertEqual(items(get(self.state(GLM), "observers")), [])

    def test_thirty_two_observers_and_one_send_to_all_of_them(self):
        for i in range(32):
            r = self.turn(GLM, "observe", observer("did:plc:p%d" % i), principal="did:plc:p%d" % i)
            self.assertEqual(r["result"]["label"], "edit", r)
        over = self.turn(GLM, "observe", observer("did:plc:p32"), principal="did:plc:p32")
        self.assertEqual(over["result"]["payload"]["fields"][0]["value"], label("Too many observers."))
        r = self.turn(GLM, "send", record(text=label("all of you")), principal=GLM)
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(r["result"]["label"], "sent", r)
        self.assertEqual(get(r["result"]["payload"], "count")["value"], "32")
        print("\n  a send to 32 observers: %s ticks" % r.get("ticksUsed"))

    def test_the_inbox_keeps_the_newest_sixty_four(self):
        for i in range(65):
            self.assertEqual(self.turn(KIM, "note", record(text=label("n%d" % i)), principal=GLM)["status"], "admitted")
        notes = self.inbox(KIM)
        self.assertEqual((len(notes), notes[0], notes[-1]), (64, (GLM, "n1"), (GLM, "n64")))


if __name__ == "__main__":
    unittest.main()
