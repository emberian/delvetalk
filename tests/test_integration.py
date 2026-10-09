"""Kernel integration in the host: an argument that does not conform to the method's input is
the journaled class `typeMismatch`; `profile: true` on `world-turn` answers the tick breakdown of
the turn's activity segments; `inspect` answers the object's actions as forms derived from the
artifact's method table.

    python3 -W error -m unittest tests.test_integration -v
"""
import json
import unittest

from tests.test_reflection import PROBE, Reflection, probe_seed
from tests.test_turn_world import label, nat, record

# Calls PROBE.bump2 (input {n: Nat}) with {m: Nat}, and inspects objects.
CALLER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./Form.obend as Form
record State:
  seen: String
record Edits:
  seen: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, String>
sum Colour:
  silver: {}
  gold: {}
def initial() -> State:
  {seen: ""}
def said(context: Abi.Context, text: String) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {seen: Plans.Edit::<String, {}>.set({value: text})}})):
    case _: text
def poke(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.call({object: {world: "", object: input.target}, method: "bump2", argument: Data.of::<{m: Nat}>({m: 1n})})):
    case returned(r): said(context, r.result)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def look(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.inspect({object: {world: "", object: input.target}})):
    case inspected(i): said(context, actions(i.methods))
    case _: said(context, "other")
def actions(forms: Lists.List<Form.Form>) -> String:
  match forms:
    case nil(_): ""
    case cons(c): textConcat(c.head.action, textConcat("(", textConcat(fields(c.head.fields), textConcat(") ", actions(c.tail)))))
def fields(items: Lists.List<Form.Field>) -> String:
  match items:
    case nil(_): ""
    case cons(c): textConcat(c.head.name, textConcat(":", textConcat(kind(c.head.kind), textConcat(" ", fields(c.tail)))))
def kind(k: Form.Kind) -> String:
  match k:
    case text(_): "text"
    case natural(_): "natural"
    case choice(_): "choice"
def paint(state: State, input: {colour: Colour, note: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  said(context, input.note)
def tally(state: State, input: {items: Lists.List<String>}, context: Abi.Context) -> Activity<Plan, Response, String>:
  said(context, "tally")
"""


class Integration(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("probe", PROBE, probe_seed())
        self.make("caller", CALLER, record(seen=label("")))

    def test_a_turn_whose_argument_does_not_conform_is_refused_typeMismatch_and_binds(self):
        r = self.turn("probe", "bump2", record(m=nat(1)), identity="bad")
        self.assertEqual(r["status"], "refused", r)
        self.assertEqual(r["receipt"]["outcome"]["class"], "typeMismatch", r)
        self.assertEqual(r["receipt"]["outcome"]["object"], "probe", r)
        # typeMismatch is not transient: the same request returns the same receipt.
        again = self.turn("probe", "bump2", record(m=nat(1)), identity="bad")
        self.assertEqual(again["receipt"]["hash"], r["receipt"]["hash"])
        fine = self.turn("probe", "bump2", record(n=nat(2)))
        self.assertEqual(fine["status"], "admitted", fine)

    def test_a_call_whose_argument_does_not_conform_is_answered_refused_typeMismatch(self):
        r = self.turn("caller", "poke", record(target=label("probe")))
        self.assertEqual((r["status"], r["result"]), ("admitted", label("typeMismatch")), r)
        self.assertEqual(self.seen("probe"), "")

    def test_profile_answers_the_breakdown_and_is_not_part_of_the_request(self):
        r = self.host.send(op="world-turn", principal="ember", object="probe", method="bump",
                           argument=record(), identity="p1", profile=True)
        self.assertEqual(r["status"], "admitted", r)
        rows = r["profile"]
        self.assertTrue(rows and all({"kind", "steps", "ticks"} <= set(x) for x in rows), rows)
        ticks = [int(x["ticks"]) for x in rows]
        self.assertEqual(ticks, sorted(ticks, reverse=True))
        self.assertLessEqual(sum(ticks), int(r["ticksUsed"]))
        self.assertGreater(sum(ticks), 0)
        # The receipt is the same with or without profiling: a retry without it is the same turn.
        retry = self.host.send(op="world-turn", principal="ember", object="probe", method="bump",
                               argument=record(), identity="p1")
        self.assertEqual(retry["receipt"]["hash"], r["receipt"]["hash"])
        self.assertNotIn("profile", retry)
        plain = self.turn("probe", "bump")
        self.assertNotIn("profile", plain)
        self.assertFalse(any("profile" in json.loads(line) for line in self.lines()))
        bad = self.host.send(op="world-turn", principal="ember", object="probe", method="bump",
                             argument=record(), identity="p2", profile="yes")
        self.assertEqual(bad["status"], "error", bad)

    def test_inspect_answers_the_actions_as_forms_from_the_method_table(self):
        r = self.turn("caller", "look", record(target=label("caller")))
        self.assertEqual(r["status"], "admitted", r)
        text = r["result"]["value"]
        self.assertIn("poke(target:text )", text)
        self.assertIn("look(target:text )", text)
        # a closed sum of empty payloads is a choice
        self.assertIn("paint(", text)
        self.assertIn("colour:choice", text)
        # a list input has no form; helpers that are not methods are not actions
        self.assertNotIn("tally", text)
        self.assertNotIn("said", text)
        probe = self.turn("caller", "look", record(target=label("probe")))
        self.assertIn("bump2(n:natural )", probe["result"]["value"])
        self.assertIn("bump() ", probe["result"]["value"])
        op = self.host.send(op="world-inspect", principal="ember", object="caller")
        names = {m["name"] for m in op["methods"]}
        self.assertTrue({"poke", "look", "paint", "tally"} <= names, names)
        forms = op["forms"]
        self.assertEqual(forms["tag"], "variant")

    def test_methods_survive_replay(self):
        before = self.host.send(op="world-inspect", principal="ember", object="caller")
        self.reopen()
        after = self.host.send(op="world-inspect", principal="ember", object="caller")
        self.assertEqual(before["methods"], after["methods"])


if __name__ == "__main__":
    unittest.main()
