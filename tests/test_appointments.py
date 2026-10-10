"""A booking creates an Appointment that waits for its time in its own turn and then notes the
recipient; a cancelled one sends nothing.

Evidence for FOUNDATION §3 Time (layer: objects).

Appointments: a booking creates an Appointment that waits in its own turn (an await on
a slot nobody settles, resumed timedOut when the clock passes) and then notes its
recipient's Avatar. Cancelling writes the appointment, so the waiting turn resumes on a
stale root and sends nothing. Its owner, topic, target and time are `fixed` State fields: the
artifact lists them and no edit of its own names them. A proposed write naming one is not yet
refused by the host (expected failure, the host lane's: `world-propose` reads the artifact's `fixed`).
"""
import unittest

from tests.test_chain import Chain
from tests.test_objects import closure
from tests.test_places import avatar_seed
from tests.test_replay import get, rows
from tests.test_turn_world import label, nat, record

KIM = "did:plc:kimik3"


class Appointments(Chain):

    def setUp(self):
        super().setUp()
        self.make("book", closure("Appointments"), record())
        self.make(KIM, closure("Avatar"), avatar_seed("kimik3", "porch"))

    def inbox(self):
        return [(get(n, "from")["value"], get(n, "text")["value"]) for n in rows(get(self.state(KIM), "inbox"))]

    def book(self, topic="tea", after=5, who="glm"):
        r = self.turn("book", "receive", record(text=label("delvetalk book book\ntopic: %s\nto: %s\nafter: %d" % (topic, KIM, after)),
                                                post=label("at://p")), principal=who)
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "booked"), r)
        return r

    def status(self, name):
        return get(self.state(name), "status")["label"]

    def test_a_booking_waits_for_its_time_then_notes_the_recipient(self):
        booked = self.book()
        # wait is delivered in the booking's own settling pass, and suspends there.
        self.assertEqual([d["status"] for d in booked["delivered"]], ["suspended"], booked)
        self.assertEqual(self.status("book/1"), "booked")
        self.host.send(op="world-advance", height=3)
        self.assertEqual(self.inbox(), [])
        self.host.send(op="world-advance", height=20)
        self.deliver_all()
        self.assertEqual(self.status("book/1"), "kept")
        self.assertEqual(self.inbox(), [("glm", "appointment: tea")])
        self.assertEqual(get(self.state("book/1"), "owner"), label("glm"))

    def test_two_bookings_wait_independently(self):
        self.book("tea", 5)
        self.book("moths", 30)
        self.deliver_all()
        self.host.send(op="world-advance", height=10)
        self.deliver_all()
        self.assertEqual([self.status("book/1"), self.status("book/2")], ["kept", "booked"])
        self.host.send(op="world-advance", height=50)
        self.deliver_all()
        self.assertEqual(self.inbox(), [("glm", "appointment: tea"), ("glm", "appointment: moths")])

    def test_a_cancelled_appointment_sends_nothing_and_only_its_owner_cancels(self):
        self.book()
        self.deliver_all()
        stranger = self.turn("book/1", "cancel", principal=KIM)
        self.assertEqual(stranger["result"]["label"], "refused")
        self.assertEqual(self.turn("book/1", "cancel", principal="glm")["result"]["label"], "cancelled")
        resumed = self.host.send(op="world-advance", height=20)
        print("\n  resumed after cancel:", [r["receipt"]["outcome"] for r in resumed.get("resumed", [])])
        self.deliver_all()
        self.assertEqual(self.status("book/1"), "cancelled")
        self.assertEqual(self.inbox(), [])

    def test_the_booked_fields_are_fixed(self):
        artifact = self.host.send(op="compile", modules=closure("Appointment"), entry="initial")["artifact"]
        self.assertEqual(artifact["fixed"], ["owner", "topic", "to", "after"])

    @unittest.expectedFailure
    def test_a_proposed_write_naming_a_fixed_field_is_refused(self):
        self.book()
        version = self.host.send(op="world-view", principal="glm", object="book/1")["version"]
        keep = {"tag": "variant", "label": "keep", "payload": record()}
        edits = record(topic={"tag": "variant", "label": "set", "payload": record(value=label("moths"))}, status=keep)
        r = self.host.send(op="world-propose", principal="glm", identity="retopic", roots=[{"object": "book/1", "version": version}],
                           writes=[{"object": "book/1", "edits": [edits]}])
        self.assertEqual(get(self.state("book/1"), "topic"), label("tea"), r)


if __name__ == "__main__":
    unittest.main()
