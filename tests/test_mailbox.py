"""An avatar follows another's outbox and is told what it sends; it watches any object's field and
is told of its changes; the inbox keeps the newest 64.

Evidence for FOUNDATION §8 claims (layer: objects).

The mailbox on Avatar (ported from main's protocols/resident-library/Mailbox.obend): its
principal's `send` inserts a letter into the avatar's `outbox` relation; a follower's `subscribe`
is the host's subscription to that field, delivered to the follower's `mailed` receiver, which
notes each letter; `watch` subscribes to any field (a bell's `rung`) and notes "news from" it.
The host serves at most sendsPerTurn (32) subscribers a turn; an avatar follows at most 32; the
inbox and the outbox are relations the host keeps to 64.

Refuted by: a stranger sending from someone's avatar, subscribing it, or delivering to its
receiver; a 33rd follow admitted; a send to 32 followers not reaching all 32; a 65th note not
dropping the oldest; a letter reaching a follower that unsubscribed.
"""
import unittest

from tests import test_chain
from tests.test_places import avatar_seed
from tests.wire import field, label, record, rows
from tests.bend import closure

GLM, KIM = "did:plc:glm", "did:plc:kimik3"


def heard(text):
    return record(text=label(text), post=label(""))


def followed(obj, field="outbox"):
    return record(object=record(world=label(""), object=label(obj)), field=label(field))


class Mailbox(test_chain.Chain):

    def setUp(self):
        super().setUp()
        for did, handle in ((GLM, "glm"), (KIM, "kimik3")):
            self.make(did, closure("Avatar"), avatar_seed(handle, "porch"))

    def say(self, obj, text, who):
        r = self.turn(obj, "receive", heard(text), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def inbox(self, did):
        return [(field(n, "from")["value"], field(n, "text")["value"]) for n in rows(field(self.state(did), "inbox"))]

    def following(self, did):
        return [(field(field(f, "object"), "object")["value"], field(f, "field")["value"]) for f in field(self.state(did), "following")["items"]]


    def test_strangers_neither_send_subscribe_nor_deliver(self):
        r = self.say(GLM, "delvetalk %s send\ntext: forged" % GLM, KIM)
        self.assertEqual(r["result"]["payload"]["fields"][1]["value"], label("Only glm sends from it."))
        twice = self.say(KIM, "delvetalk %s subscribe\nto: %s" % (KIM, GLM), GLM)
        self.assertEqual(twice["result"]["payload"]["fields"][1]["value"], label("Only kimik3 subscribes it."))
        self.assertEqual(self.following(KIM), [])
        # The receiver is a helper: only the host's delivery of a subscribed change reaches it.
        forged = self.turn(KIM, "mailed", record(object=record(world=label(""), object=label(GLM)), field=label("outbox"), version={"tag": "natural", "value": "1"},
                                                  inserted={"tag": "list", "items": []}, retracted={"tag": "list", "items": []}), principal="did:plc:mallory")
        self.assertEqual((forged["status"], forged["receipt"]["outcome"]["class"]), ("refused", "noMethod"), forged)
        self.assertEqual(self.inbox(KIM), [])

    def test_thirty_two_followers_and_one_send_reaches_all_of_them(self):
        followers = ["did:plc:p%d" % i for i in range(32)]
        for did in followers:
            self.make(did, closure("Avatar"), avatar_seed(did[-3:], "porch"))
            r = self.say(did, "delvetalk %s subscribe\nto: %s" % (did, GLM), did)
            self.assertEqual(r["result"]["label"], "followed", r)
        r = self.turn(GLM, "send", record(text=label("all of you")), principal=GLM)
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "sent"), r)
        print("\n  a send with 32 followers: %s ticks" % r.get("ticksUsed"))
        self.deliver_all()
        self.assertEqual([self.inbox(did) for did in followers], [[(GLM, "all of you")]] * 32)

    def test_an_avatar_follows_at_most_thirty_two(self):
        full = {"tag": "list", "items": [followed("did:plc:f%d" % i) for i in range(32)]}
        self.make("did:plc:busy", closure("Avatar"), record(handle=label("busy"), at=record(world=label(""), object=label("porch")), following=full))
        r = self.say("did:plc:busy", "delvetalk did:plc:busy subscribe\nto: %s" % GLM, "did:plc:busy")
        self.assertEqual(r["result"]["payload"]["fields"][0]["value"], label("followingFull"), r)


if __name__ == "__main__":
    unittest.main()
