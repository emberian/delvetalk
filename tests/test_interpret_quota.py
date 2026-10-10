"""`world-open {interpretQuota: n}` (default 48): interpretations one principal may start per clock hour
(the clock counts minutes, so an hour is `clock / 60`), counted from the journal's suspended entries
with an interpretation; the next is a journaled transient refusal of class `quota` whose public
projection carries the reason and `next`, the clock at which the count starts again; `world-status
{principal}` reports the cap and what the principal has left; the opener and the clock principal are
exempt.

Evidence for HOST-HANDOFF 5.60 (layer: host). Refuted by an interpretation past the cap that suspends,
one within it refused, a count that does not survive reopen or restart at the hour, a refusal that
binds the identity, or an exempt principal refused.

    python3 -W error -m unittest tests.test_interpret_quota -v
"""
import unittest

from tests.test_reflection import POLICY, PROBE, Reflection, probe_seed
from tests.test_turn_world import label, record


class InterpretQuota(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library(clock="clock", opener="ember", interpretQuota=3)
        self.make("policy", POLICY, record(model=label("m"), system=label(""), examples=label("")))
        self.make("probe", PROBE, probe_seed())

    def ask(self, principal="kim", identity=None):
        return self.turn("probe", "ask", record(utterance=label("ring it"), policy=label("policy")),
                         principal=principal, identity=identity)

    def advance(self, height):
        r = self.host.send(op="world-advance", principal="clock", identity=f"tick{height}", height=height)
        self.assertEqual(r["status"], "advanced", r)

    def test_the_fourth_in_an_hour_is_refused_naming_the_next_clock(self):
        self.advance(5)
        for i in range(3):
            self.assertEqual(self.ask(identity=f"a{i}")["status"], "suspended")
        self.assertEqual(self.host.send(op="world-status", principal="kim")["interpretations"], {"remaining": 0, "next": 60})
        r = self.ask(identity="a3")
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out["next"]), ("refused", "quota", 60), r)
        self.assertEqual(out["reason"], "the interpreter has read 3 this hour; reply with the spell itself, or wait.")
        public = self.host.send(op="world-receipt", principal="lee", identity="a3", of="kim")
        self.assertEqual((public["class"], public["next"], public["reason"]), ("quota", 60, out["reason"]), public)
        # Another principal has its own count; the opener is exempt.
        self.assertEqual(self.ask(principal="lee", identity="l0")["status"], "suspended")
        for i in range(4):
            self.assertEqual(self.ask(principal="ember", identity=f"e{i}")["status"], "suspended")
        self.assertEqual(self.host.send(op="world-status", principal="ember")["interpretations"], "exempt")
        # The count is the journal's: it stands after reopen, and starts again at the hour; the
        # refusal was transient, so the same identity runs again.
        self.reopen()
        self.assertEqual(self.ask(identity="a3")["receipt"]["outcome"]["class"], "quota")
        self.advance(60)
        self.assertEqual(self.host.send(op="world-status", principal="kim")["interpretations"], {"remaining": 3, "next": 120})
        self.assertEqual(self.ask(identity="a3")["status"], "suspended")

    def test_the_quota_is_settled_once(self):
        status = self.host.send(op="world-status")
        self.assertEqual(status["interpretQuota"], 3)
        other = self.host.send(op="world-open", path=self.path, interpretQuota=5)
        self.assertEqual(other["status"], "error", other)
        self.assertIn("interpretQuota 3", other["message"])


if __name__ == "__main__":
    unittest.main()
