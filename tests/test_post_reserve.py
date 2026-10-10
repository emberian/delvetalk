"""Posting reservations and model retries are host facts (HOST-HANDOFF 5.107; codex transport 9, 10).

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

from tests.test_chain import Chain
from tests.test_objects import closure
from tests import test_policy
from tests.test_turn_world import label, record

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


class Retries(Chain):
    policy = test_policy.PolicyObject.policy
    garden = test_policy.PolicyObject.garden
    say = test_policy.PolicyObject.say

    def submit(self, reply):
        [item] = self.host.send(op="world-interpretations")["pending"]
        return item, self.host.send(op="world-interpretation", id=item["id"], reply=reply)

    def test_transient_failures_are_the_hosts_to_retry_until_the_last_attempt(self):
        self.policy()
        self.garden("policy", confirm=False)
        self.say("Could we plant a silver fern that remembers?")
        failed = {"status": "failed", "reason": "transport", "model": "m"}
        nexts = []
        for attempt in range(1, 8):
            item, r = self.submit(failed)
            self.assertEqual(item["attempts"], attempt - 1)
            self.assertEqual((r["status"], r["attempt"]), ("retrying", attempt), r)
            nexts.append(r["next"])
            if attempt == 3:
                self.reopen()
        self.assertEqual(nexts, [1, 2, 4, 8, 16, 32, 60])
        [item] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual((item["attempts"], item["next"]), (7, 60))
        _, last = self.submit(failed)
        self.assertEqual(last["status"], "interpreted", last)
        self.assertEqual(last["receipt"]["outcome"]["verdict"], {"tag": "unclear", "needs": ["model: transport"]})
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_a_failure_that_is_not_transient_is_the_verdict_at_once(self):
        self.policy()
        self.garden("policy", confirm=False)
        self.say("Could we plant a silver fern that remembers?")
        _, r = self.submit({"status": "failed", "reason": "refused", "model": "m"})
        self.assertEqual(r["status"], "interpreted", r)


if __name__ == "__main__":
    unittest.main()
