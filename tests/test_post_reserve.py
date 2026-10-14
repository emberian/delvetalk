"""Posting reservations and model retries are host facts (HOST-HANDOFF §5.5, §5.4).

Evidence for the host's decisions (layer: host): a `delve` post is reserved against the journaled
`postQuota` per clock hour before the network is touched, once per intent, and given back only by a
release; another source reserves without a count. A transient model failure is journaled `attempted`
with the clock the next attempt may be asked at, until the last attempt, whose failure is the verdict.
Refuted by a second slot for one intent, a delve reservation past the quota, a Zulip one refused, a
released slot not given back, a retry decision that does not survive a reopen, or a transient
failure settled before the last attempt.

    python3 -W error -m unittest tests.test_post_reserve -v
"""
import unittest

from tests.host import addressed
from tests.test_chain import Chain
from tests.wire import record
from tests.bend import closure

CLOCK = "transport"


class Reservations(Chain):
    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-open", path=self.path, clock=CLOCK, postQuota=2)
        self.assertEqual(r["status"], "opened", r)
        self.make("hub", closure("Counter"), record())

    def reserve(self, intent, source="delve"):
        return self.host.send(op="world-post-reserve", principal=CLOCK, intent=intent, source=source)

    def posts(self):
        return {s["source"]: s for s in self.host.send(op="world-status")["posts"]["sources"]}

    def test_the_quota_is_delves_counted_once_per_intent_and_given_back_by_a_release(self):
        a = self.reserve("a")
        self.assertEqual(a["status"], "reserved", a)
        height = self.host.send(op="world-status")["height"]
        self.assertEqual(self.reserve("a")["receipt"]["hash"], a["receipt"]["hash"])     # a retry takes no slot
        self.assertEqual(self.host.send(op="world-status")["height"], height)
        self.assertEqual(self.reserve("b")["status"], "reserved")
        full = self.reserve("c")
        self.assertEqual((full["status"], full["class"], full["next"]), ("refused", "quota", 60), full)
        for i in range(5):                                                              # Zulip has no quota
            self.assertEqual(self.reserve(f"z{i}", source="zulip")["status"], "reserved")
        self.assertEqual((self.posts()["delve"]["used"], self.posts()["delve"]["next"], self.posts()["zulip"]["used"]), (2, 60, 5))
        self.assertNotIn("quota", self.posts()["zulip"])
        # b never left: released, its slot goes to c.
        released = self.host.send(op="world-post-release", principal=CLOCK, intent="b", reason="credentials unreadable")
        self.assertEqual(released["status"], "released", released)
        self.assertEqual(self.reserve("c")["status"], "reserved")
        # a is posted: it settles the reservation, which no release undoes, and a second post of it is refused.
        posted = self.host.send(op="world-posted", principal=CLOCK, uri="at://did:plc:t/app.bsky.feed.post/a", cid="c1",
                                object="hub", intent="a")
        self.assertEqual(posted["status"], "posted", posted)
        self.assertEqual(posted["receipt"]["outcome"]["intent"], "a")
        self.assertEqual(self.host.send(op="world-post-release", principal=CLOCK, intent="a", reason="x")["status"], "error")
        again = self.host.send(op="world-posted", principal=CLOCK, uri="at://did:plc:t/app.bsky.feed.post/a2", cid="c2",
                               object="hub", intent="a")
        self.assertEqual(again["status"], "error", again)
        self.assertEqual(self.host.send(op="world-post-reserve", principal="mallory", intent="m", source="delve")["status"], "error")
        # Every post settles a reservation: one without an intent is refused by name.
        bare = self.host.send(op="world-posted", principal=CLOCK, uri="at://did:plc:t/app.bsky.feed.post/b", cid="c3", object="hub")
        self.assertEqual((bare["status"], bare["message"]), ("error", "a post settles a reservation; name its intent"), bare)
        before = self.posts()
        self.reopen()
        self.assertEqual(self.posts(), before)
        # The next clock hour has its own slots.
        self.host.send(op="world-advance", principal=CLOCK, height=60)
        self.assertEqual(self.reserve("d")["status"], "reserved")
        self.assertEqual(self.posts()["delve"]["used"], 1)

    def test_a_released_intent_is_reserved_anew(self):
        self.reserve("a")
        self.host.send(op="world-post-release", principal=CLOCK, intent="a", reason="refused before the network")
        again = self.reserve("a")
        self.assertEqual(again["status"], "reserved", again)
        self.assertEqual(again["receipt"]["identity"]["intent"], "post:a/1")
        self.assertEqual(self.posts()["delve"]["used"], 1)


class Shares(Chain):
    """One resident's replies take at most a quarter of the hour's posts (the astra posting review (6))."""

    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-open", path=self.path, clock=CLOCK, postQuota=8)
        self.assertEqual(r["status"], "opened", r)

    def reserve(self, intent, resident=None):
        return self.host.send(op="world-post-reserve", principal=CLOCK, intent=intent, source="delve", **({"for": resident} if resident else {}))

    def test_a_resident_takes_at_most_their_share_and_the_rest_of_the_hour_stays_for_others(self):
        self.assertEqual([self.reserve(f"g{i}", "did:plc:greedy")["status"] for i in range(2)], ["reserved"] * 2)
        over = self.reserve("g2", "did:plc:greedy")
        self.assertEqual((over["status"], over["class"], over["share"]), ("refused", "quota", True), over)
        self.assertIn("2 of the hour's 8 delve posts answer one resident", over["reason"])
        self.assertEqual(self.reserve("o0", "did:plc:other")["status"], "reserved")
        self.assertEqual(self.reserve("h0")["status"], "reserved")  # the hand's own: no share
        posts = {s["source"]: s for s in self.host.send(op="world-status")["posts"]["sources"]}["delve"]
        self.assertEqual((posts["used"], posts["share"], posts["residents"]), (4, 2, {"did:plc:greedy": 2, "did:plc:other": 1}))
        self.reopen()  # replayed: the share is the journal's
        self.assertEqual(self.reserve("g3", "did:plc:greedy")["class"], "quota")
        self.assertEqual(self.reserve("o1", "did:plc:other")["status"], "reserved")


class Unposted(Chain):
    """`unposted`: our own post deleted on Delve or Zulip leaves the town as a journaled fact."""
    def setUp(self):
        super().setUp()
        self.assertEqual(self.host.send(op="world-open", path=self.path, clock=CLOCK)["status"], "opened")
        self.make("hub", closure("Counter"), record())

    def test_an_unposted_post_says_so_and_a_post_never_made_is_refused(self):
        uri = "at://did:plc:t/app.bsky.feed.post/a"
        self.host.send(op="world-post-reserve", principal=CLOCK, intent="a", source="delve")
        self.assertEqual(self.host.send(op="world-posted", principal=CLOCK, uri=uri, cid="c1", object="hub", intent="a")["status"], "posted")
        never = self.host.send(op="world-posted", principal=CLOCK, uri=uri + "x", cid="c", object="hub", intent="a",
                               unposted=True, reason="wrong card")
        self.assertEqual(never["status"], "error", never)
        r = self.host.send(op="world-posted", principal=CLOCK, uri=uri, cid="c1", object="hub", intent="a",
                           unposted=True, reason="the wrong card")
        self.assertEqual((r["status"], r["receipt"]["outcome"]["tag"], r["receipt"]["outcome"]["reason"]),
                         ("unposted", "unposted", "the wrong card"), r)
        self.reopen()
        again = self.host.send(op="world-posted", principal=CLOCK, uri=uri, cid="c1", object="hub", intent="a",
                               unposted=True, reason="twice")
        self.assertEqual((again["status"], again["class"]), ("refused", "duplicateIdentity"), again)
        # The reservation stays settled: posted, never released.
        self.assertEqual(self.host.send(op="world-post-release", principal=CLOCK, intent="a", reason="x")["status"], "error")
        self.assertEqual(addressed(self.host, uri)["unposted"], "the wrong card")


if __name__ == "__main__":
    unittest.main()
