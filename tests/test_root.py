"""Root and moderation (docs/ROOT.md §1, §2; HOST-HANDOFF 5.126).

Evidence (layer: host). Every root act is an entry marked `root` inside its hash, with the value it
replaced (`before`) and the value it laid (`after`), whole to every reader, and replay checks `before`
and applies `after` verbatim; an ignored entry replays as refused and a later entry that no longer
holds is shadowed and reported; the opener's powers are receipted turns. Refuted by a root act that
does not survive a reopen, a `before` that is not the replaced value, an ignore that leaves the store
as it was or breaks the journal, a snapshot from before an ignore resumed, a quieted turn admitted, a
retired card written, or a non-opener casting a power.

    python3 -W error -m unittest tests.test_root -v
"""
import os
import unittest

from tests.test_chain import Chain
from tests.wire import label, nat, record
from tests.bend import closure

OPENER = "did:plc:hand"
CLOCK = "clock"


class RootCase(Chain):
    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-open", path=self.path, clock=CLOCK, opener=OPENER)
        self.assertEqual(r["status"], "opened", r)
        self.make("counter", closure("Counter"), record())

    def root(self, act, reason="a test", principal=OPENER):
        return self.host.send(op="world-root", principal=principal, reason=reason, act=act)

    def view(self, obj="counter", principal="ember"):
        return self.host.send(op="world-view", principal=principal, object=obj)

    def count(self, obj="counter"):
        v = self.view(obj)
        self.assertEqual(v["status"], "viewed", v)
        return v["version"], int(v["state"]["fields"][0]["value"]["value"])


class Root(RootCase):
    def test_only_the_opener_acts_and_every_act_has_a_reason(self):
        self.assertEqual(self.root({"kind": "delete", "object": "counter"}, principal="ember")["status"], "error")
        self.assertEqual(self.root({"kind": "delete", "object": "counter"}, reason="")["status"], "error")
        self.assertEqual(self.root({"kind": "fly"})["status"], "error")
        self.assertEqual(self.count(), (0, 0))

    def test_set_state_journals_before_and_after_and_replays(self):
        self.assertEqual(self.turn("counter", "bump")["status"], "admitted")
        r = self.root({"kind": "set", "object": "counter", "field": "state", "value": record(count=nat(7))}, reason="fix a count")
        self.assertEqual(r["status"], "root", r)
        entry = r["receipt"]
        self.assertEqual((entry["root"], entry["reason"], entry["identity"]), (True, "fix a count", {"principal": OPENER, "intent": "root:1"}))
        o = entry["outcome"]
        self.assertEqual((o["tag"], o["kind"], o["object"], o["field"]), ("root", "set", "counter", "state"))
        self.assertEqual((o["before"], o["after"], o["version"]), (record(count=nat(1)), record(count=nat(7)), 2))
        self.assertEqual(self.count(), (2, 7))
        # Whole and public: another reader sees `before` too.
        seen = self.host.send(op="world-entry", principal="mallory", hash=entry["hash"])
        self.assertEqual(seen["receipt"]["outcome"]["before"], record(count=nat(1)), seen)
        # A turn that read the old version is stale; the bump after it counts from 7.
        self.assertEqual(self.turn("counter", "bump")["status"], "admitted")
        self.reopen()
        self.assertEqual(self.count(), (3, 8))

    def test_set_one_field_of_the_state_journals_that_field_and_replays(self):
        """`set` of `state.F` changes one field (a live town's kinds needed one, entry 129): typed data or a plain value
        of the field's kind, journaled as `state` is, its `before` and `after` that field's; a field the state lacks,
        a nested path and a value of another kind refuse."""
        self.assertEqual(self.turn("counter", "bump")["status"], "admitted")
        r = self.root({"kind": "set", "object": "counter", "field": "state.count", "value": 12}, reason="one field")
        self.assertEqual(r["status"], "root", r)
        o = r["receipt"]["outcome"]
        self.assertEqual((o["field"], o["before"], o["after"], o["version"]), ("state.count", nat(1), nat(12), 2))
        self.assertEqual(self.count(), (2, 12))
        typed = self.root({"kind": "set", "object": "counter", "field": "state.count", "value": nat(13)})
        self.assertEqual((typed["status"], self.count()), ("root", (3, 13)), typed)
        for field, value in (("state.missing", 1), ("state.count.x", 1), ("state.count", "twelve"), ("state.", 1)):
            self.assertEqual(self.root({"kind": "set", "object": "counter", "field": field, "value": value})["status"], "error", field)
        self.assertEqual(self.turn("counter", "bump")["status"], "admitted")
        self.reopen()
        self.assertEqual(self.count(), (4, 14))

    def test_the_other_fields_delete_and_card(self):
        law = "law owner: request.kind == 0"
        self.assertEqual(self.root({"kind": "set", "object": "counter", "field": "law", "value": law})["status"], "root")
        r = self.root({"kind": "set", "object": "counter", "field": "read", "value": {"principals": ["ember"]}})
        self.assertEqual(r["receipt"]["outcome"]["before"], "public", r)
        self.assertEqual(self.root({"kind": "set", "object": "counter", "field": "version", "value": 9})["status"], "root")
        self.assertEqual(self.root({"kind": "set", "object": "counter", "field": "supervisor", "value": "nobody"})["status"], "root")
        card = self.root({"kind": "card", "object": "counter", "text": "closed for repairs"})
        self.assertEqual(card["receipt"]["outcome"]["before"], None, card)
        def check():
            inspected = self.host.send(op="world-inspect", principal="ember", object="counter")
            self.assertEqual((inspected["law"], inspected["supervisor"]), (law, "nobody"), inspected)
            self.assertEqual(self.view(principal="mallory")["status"], "denied")
            self.assertEqual(self.count(), (9, 0))
            shown = self.host.send(op="world-card", principal="ember", object="counter")
            self.assertEqual((shown["text"], shown["override"]), ("closed for repairs", True), shown)
        check()
        self.reopen()
        check()
        self.assertEqual(self.root({"kind": "card", "object": "counter", "text": None})["receipt"]["outcome"]["before"],
                         "closed for repairs")
        self.assertNotIn("override", self.host.send(op="world-card", principal="ember", object="counter"))
        gone = self.root({"kind": "delete", "object": "counter"})
        self.assertEqual(gone["receipt"]["outcome"]["before"]["version"], 9, gone)
        self.assertEqual(self.view()["status"], "unknown")
        again = self.host.send(op="world-create", principal="ember", identity="mk-again", object="counter",
                               modules=closure("Counter"), entry="initial", seed=record())
        self.assertEqual(again["status"], "created", again)                             # the id is free again
        self.reopen()
        self.assertEqual(self.count(), (0, 0))

    def test_every_act_replays_with_its_before(self):
        """Each act once, then a reopen: replay checks every `before` against the store it rebuilt."""
        counter = closure("Counter")
        bump = counter[-1]["source"].replace("add 1n", "add 2n")
        acts = [
            ({"kind": "set", "object": "counter", "field": "ledger", "value": {"depth": 5, "work": 1000, "storage": 100}},
             {"depth": 100, "work": 10000000, "storage": 1048576}),
            ({"kind": "set", "object": "counter", "field": "readings", "value": [{"name": "owner", "reading": "mine"}]}, []),
            ({"kind": "set", "object": "counter", "field": "activities", "value": []}, []),
            ({"kind": "set", "object": "counter", "field": "program",
              "value": {"modules": counter[:-1] + [{"name": "Counter", "source": bump}]}}, None),
            ({"kind": "quiet", "principal": "mallory", "hours": 2}, None),
            ({"kind": "hide", "object": "counter"}, "public"),
            ({"kind": "show", "object": "counter"}, {"principals": [OPENER]}),
            ({"kind": "retire", "object": "counter"}, None),
            ({"kind": "unretire", "object": "counter"}, None),
            ({"kind": "library", "modules": [{"name": "Tiny", "source": "def tiny() -> Nat:\n  1n\n"}]}, ""),
        ]
        for act, before in acts:
            r = self.root(act)
            self.assertEqual(r["status"], "root", (act, r))
            if before is not None:
                self.assertEqual(r["receipt"]["outcome"]["before"], before, act)
        bumped = self.turn("counter", "bump")
        self.assertEqual((bumped["status"], self.count()[1]), ("admitted", 2), bumped)  # the program root set
        fixed = self.root({"kind": "set", "object": "counter", "field": "fixed", "value": ["count"]})
        self.assertEqual(fixed["receipt"]["outcome"]["before"], [], fixed)               # after program, which derives it
        self.reopen()
        self.assertEqual(self.count()[1], 2)
        self.assertEqual(self.turn("counter", "bump", principal="mallory")["receipt"]["outcome"]["class"], "quiet")
        self.assertEqual(self.host.send(op="world-inspect", principal="ember", object="counter")["fixed"], ["count"])

    def test_as_runs_a_judged_turn_under_another_principal(self):
        r = self.root({"kind": "as", "principal": "mallory",
                       "turn": {"object": "counter", "method": "bump", "argument": record(), "identity": "m1"}})
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(r["receipt"]["identity"], {"principal": "mallory", "intent": "m1"})
        self.assertEqual(r["receipt"]["root"], {"by": OPENER, "reason": "a test"})
        self.reopen()
        self.assertEqual(self.count(), (1, 1))

    def test_settings_move_the_clock_either_way(self):
        self.host.send(op="world-advance", principal=CLOCK, height=100)
        r = self.root({"kind": "settings", "clock": 40, "postQuota": 3, "modelQuota": 9})
        self.assertEqual(r["receipt"]["outcome"]["before"], {"clock": 100, "postQuota": 16, "modelQuota": 2000}, r)
        self.assertIn("suspensions", r)
        def check():
            s = self.host.send(op="world-status")
            self.assertEqual((s["clock"], s["postQuota"], s["modelQuota"]["quota"]), (40, 3, 9), s)
        check()
        self.reopen()
        check()

    def test_an_ignored_entry_replays_as_refused_and_a_later_one_is_shadowed(self):
        first = self.turn("counter", "bump")
        second = self.turn("counter", "bump")
        self.assertEqual(self.count(), (2, 2))
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        r = self.root({"kind": "ignore", "height": first["receipt"]["height"]})
        self.assertEqual(r["receipt"]["outcome"]["before"], {"ignored": False}, r)
        # The store is re-derived under the new set, and a snapshot of it written at once.
        self.assertEqual(r["snapshot"], {"height": r["receipt"]["height"]}, r)
        # The second bump read version 1, which no longer exists: shadowed, reported, never re-judged.
        shadowed = [{"height": second["receipt"]["height"], "by": first["receipt"]["height"]}]
        def check():
            s = self.host.send(op="world-status")
            self.assertEqual([{k: x[k] for k in ("height", "by")} for x in s["shadowed"]], shadowed, s)
            self.assertEqual(s["ignored"], [first["receipt"]["height"]])
            self.assertEqual(self.count(), (0, 0))
        check()
        self.release()
        self.host = self.spawn()
        opened = self.host.send(op="world-open", path=self.path)
        self.assertEqual(opened["status"], "opened", opened)
        self.assertEqual(opened["snapshot"]["resumed"], r["receipt"]["height"], opened)  # the one the ignore wrote
        check()
        # Without it, the snapshot from before the ignore is refused by name, and the journal replayed.
        self.release()
        os.remove(f"{self.path}.snapshot.{r['receipt']['height']}.cbor")
        self.host = self.spawn()
        opened = self.host.send(op="world-open", path=self.path)
        self.assertEqual(opened["snapshot"]["resumed"], 0, opened)
        self.assertIn("an ignore after it", opened["snapshot"]["refused"][0]["reason"])
        check()
        verified = self.host.send(op="world-open", path=self.path, verify=True)
        self.assertEqual(len(verified["shadowed"]), 1, verified)
        # Ignored, the identity is not bound: the same request runs again, as a new entry.
        again = self.turn("counter", "bump", identity=first["receipt"]["identity"]["intent"])
        self.assertEqual(again["status"], "admitted", again)
        self.assertEqual(self.count(), (1, 1))
        un = self.root({"kind": "unignore", "height": first["receipt"]["height"]})
        self.assertEqual(un["status"], "root", un)
        # Unignored, both bumps stand again and the retry, which read the store without them, is shadowed.
        def unignored():
            s = self.host.send(op="world-status")
            self.assertEqual(([x["height"] for x in s["shadowed"]], s["ignored"]), ([again["receipt"]["height"]], []), s)
            self.assertEqual(self.count(), (2, 2))
        unignored()
        self.reopen()
        unignored()

    def test_a_snapshot_after_the_ignore_carries_it(self):
        first = self.turn("counter", "bump")
        self.turn("counter", "bump")
        self.root({"kind": "ignore", "height": first["receipt"]["height"]})
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        s = self.host.send(op="world-status")
        self.assertEqual((len(s["shadowed"]), self.count()), (1, (0, 0)), s)


class Moderation(RootCase):
    def power(self, obj, method, principal=OPENER, identity=None, **fields):
        return self.turn(obj, method, record(**{k: (nat(v) if isinstance(v, int) else label(v)) for k, v in fields.items()}),
                         principal=principal, identity=identity)

    def test_quiet_refuses_until_the_clock_and_only_the_opener_casts_it(self):
        refused = self.power("world", "quiet", principal="ember", who="mallory", hours=1, reading="flood")
        self.assertEqual((refused["status"], refused["receipt"]["outcome"]["clause"]), ("refused", "opener"), refused)
        q = self.power("world", "quiet", who="mallory", hours=1, reading="flooding the counter")
        self.assertEqual((q["status"], q["receipt"]["outcome"]["tag"]), ("moderated", "moderated"), q)
        self.assertEqual(q["receipt"]["outcome"]["after"], {"until": 60, "reading": "flooding the counter"})
        self.reopen()
        quiet = self.turn("counter", "bump", principal="mallory", identity="m1")
        o = quiet["receipt"]["outcome"]
        self.assertEqual((quiet["status"], o["class"], o["clause"], o["next"]), ("refused", "quiet", "until clock 60", 60), quiet)
        self.assertIn("flooding the counter", o["reason"])
        self.assertEqual(self.turn("counter", "bump", principal="ember")["status"], "admitted")
        self.host.send(op="world-advance", principal=CLOCK, height=60)
        self.assertEqual(self.turn("counter", "bump", principal="mallory", identity="m1")["status"], "admitted")  # transient

    def test_retire_admits_only_the_opener_and_unretire_restores(self):
        r = self.power("counter", "retire", reading="it loops")
        self.assertEqual(r["status"], "admitted", r)
        self.assertIn("law retired", r["receipt"]["outcome"]["amendments"][0]["new"])
        bump = self.turn("counter", "bump")
        self.assertEqual((bump["receipt"]["outcome"]["class"], bump["receipt"]["outcome"]["clause"]), ("lawRefused", "retired"), bump)
        self.assertEqual(self.power("counter", "unretire", principal="ember", reading="mine")["receipt"]["outcome"]["clause"], "opener")
        self.reopen()
        self.assertEqual(self.power("counter", "unretire", reading="fixed")["status"], "admitted")
        self.assertEqual(self.turn("counter", "bump")["status"], "admitted")

    def test_the_opener_amends_any_law(self):
        locked = "law owner: request.kind == 0 or request.subject == \"ember\""
        self.assertEqual(self.host.send(op="world-amend", principal="mallory", identity="a0", object="counter", version=0,
                                        law=locked)["status"], "refused")
        r = self.host.send(op="world-amend", principal=OPENER, identity="a1", object="counter", version=0,
                           law="law owner: request.kind == 0")
        self.assertEqual(r["status"], "admitted", r)
        rows = self.host.send(op="world-inspect", principal="ember", object="counter")["laws"]
        self.assertEqual((rows[0]["name"], rows[0]["host"]), ("opener", True), rows)

    def test_hide_and_show(self):
        r = self.power("counter", "hide", reading="abusive text")
        self.assertEqual((r["status"], r["receipt"]["outcome"]["before"]), ("moderated", "public"), r)
        self.assertEqual(self.view(principal="mallory")["status"], "denied")
        self.assertEqual(self.view(principal=OPENER)["status"], "viewed")
        self.reopen()
        self.assertEqual(self.view(principal="mallory")["status"], "denied")
        self.assertEqual(self.power("counter", "show", reading="cleaned")["status"], "moderated")
        self.reopen()
        self.assertEqual(self.view(principal="mallory")["status"], "viewed")

    def test_world_settings_and_the_hour(self):
        r = self.host.send(op="world-settings", principal=OPENER, reading="a quiet week", modelQuota=500, interpretQuota=24)
        self.assertEqual(r["status"], "settings", r)
        self.assertEqual(self.host.send(op="world-settings", principal="ember", reading="x", modelQuota=1)["status"], "error")
        self.turn("counter", "bump")
        self.turn("counter", "nothing")
        def check():
            s = self.host.send(op="world-status")
            self.assertEqual((s["modelQuota"]["quota"], s["interpretQuota"]), (500, 24), s)
            self.assertEqual((s["hour"]["turns"], s["hour"]["refused"]), (2, {"noMethod": 1}), s)
        check()
        self.reopen()
        check()


if __name__ == "__main__":
    unittest.main()
