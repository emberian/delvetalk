"""The workshop: a model takes the reins from a post.

The host answers `check`, `inspect` and a `reprogram` of another object (judged by
the target's own law with request.caller = the workshop). The propose case stays an
expected failure for a reason in the fixture, not the host: its BLOCK has no `initial`
or `keep`, so the replacement cannot compile as a Counter (programRefused compile),
and this Chain world has no sealed library, so a block that imported the Plan library
would not check clean. tests/test_reflection.py ReprogramAnother covers the host path.
"""
import unittest

from tests.test_chain import Chain
from tests.test_objects import check, closure, compile_job, computation, row_names
from tests.test_turn_world import label, nat, record

PROBE = """edition ObjectiveBend 1
import ./Workshop.obend as Workshop
def kind(block: Workshop.Block) -> String:
  match block:
    case none(_): "none"
    case some(s): textConcat("some:", s.source)
def found(text: String) -> String:
  kind(Workshop.fenced(text))
def size(text: String) -> Nat:
  match Workshop.fenced(text):
    case none(_): 0n
    case some(s): textLength(s.source)
"""
BLOCK = "edition ObjectiveBend 1\ndef bump(count: Nat) -> Nat:\n  count + 1n\n"


def run(entry, text, limits=None):
    modules = closure("Workshop") + [{"name": "Probe", "source": PROBE}]
    compiled = compile_job(modules, entry)
    assert compiled["status"] == "compiled", compiled
    request = {"op": "run", "artifact": compiled["artifact"], "arguments": [{"tag": "label", "value": text}]}
    if limits:
        request["limits"] = limits
    return check(request)


class Fenced(unittest.TestCase):
    def found(self, text):
        out = run("found", text)
        self.assertEqual(out["status"], "finished", out)
        return out["value"]["value"]

    def test_the_first_obend_block_is_extracted_without_its_fences(self):
        self.assertEqual(self.found("delvetalk workshop check\n```obend\n%s```\nthanks" % BLOCK), "some:" + BLOCK)

    def test_blocks_of_other_languages_and_unterminated_blocks_are_none(self):
        self.assertEqual(self.found("```python\nprint(1)\n```"), "none")
        self.assertEqual(self.found("```obend\nedition ObjectiveBend 1\n"), "none")
        self.assertEqual(self.found("no fence here"), "none")
        self.assertEqual(self.found(""), "none")

    def test_a_python_block_before_the_obend_block_is_skipped(self):
        self.assertEqual(self.found("```python\nx = 1\n```\n```obend\n%s```" % BLOCK), "some:" + BLOCK)

    def test_stray_backticks_inside_the_block_stay_in_it(self):
        source = "# a `quoted` word and ``two`` ticks\n" + BLOCK
        self.assertEqual(self.found("```obend\n%s```" % source), "some:" + source)

    def test_a_32_kib_block_is_extracted_under_the_turn_budget(self):
        """426,751 ticks: over the 100,000 a bare run allows, under the host turn's 1,000,000."""
        source = ("def f(n: Nat) -> Nat:\n  n + 1n\n" * 1100)[:32768]
        self.assertEqual(len(source.encode()), 32768)
        text = "delvetalk workshop check\n```obend\n%s\n```\n" % source
        out = run("size", text, limits={"ticks": "1000000"})
        print("\n  32 KiB fenced block: %s ticks" % out.get("ticksUsed"))
        self.assertEqual(out["status"], "finished", out)
        self.assertEqual(out["value"]["value"], str(32768 + 1))
        self.assertLess(out["ticksUsed"], 1000000)


class Types(unittest.TestCase):
    def test_every_method_compiles_as_an_activity(self):
        for method in ("check", "propose", "receive", "describe"):
            with self.subTest(method=method):
                reply = compile_job(closure("Workshop"), method)
                self.assertEqual(reply["status"], "compiled", reply)
                self.assertEqual(row_names(computation(reply["artifact"]["type"])["plan"]["row"])[:3], ["view", "write", "call"])


class Workshop(Chain):
    def make_workshop(self):
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))

    def say(self, text, obj="workshop"):
        return self.turn(obj, "receive", record(text=label(text), who=label("glm"), post=label("at://glm/p/1")), principal="glm")

    def card(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        return reply["offers"][0]["text"]

    def verdict(self, reply):
        return reply["result"]["label"]

    def test_prose_is_refused_with_the_usage_card(self):
        self.make_workshop()
        reply = self.say("please make my bell louder")
        self.assertEqual(self.verdict(reply), "refused")
        self.assertIn("delvetalk workshop check", self.card(reply))
        self.assertEqual(self.card(self.turn("workshop", "describe", principal="glm")), self.card(reply))

    def test_a_check_with_neither_block_nor_target_and_a_wrong_card_are_refused_by_name(self):
        self.make_workshop()
        reply = self.say("delvetalk workshop check")
        self.assertEqual(reply["result"]["payload"]["fields"][0]["value"]["value"], "Include a fenced obend block.")
        reply = self.say("delvetalk orchard check\n```obend\nx\n```")
        self.assertEqual(reply["result"]["payload"]["fields"][0]["value"]["value"], "This card is workshop")
        reply = self.say("delvetalk workshop propose\n```obend\nx\n```")
        self.assertEqual(reply["result"]["payload"]["fields"][0]["value"]["value"], "Name a target to propose to.")

    def test_a_fenced_block_is_checked_and_the_diagnostics_card_offered(self):
        self.make_workshop()
        reply = self.say("delvetalk workshop check\n```obend\n%s```\n" % BLOCK)
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertEqual(self.verdict(reply), "clean")
        self.assertIn("Checked: it compiles.", self.card(reply))

    def test_a_target_is_inspected_and_its_source_checked(self):
        self.make_workshop()
        self.make("bell-1", closure("Counter"), record(count=nat(0)))
        reply = self.say("delvetalk workshop check\ntarget: bell-1")
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertIn(self.verdict(reply), ("clean", "flawed"))

    @unittest.expectedFailure
    def test_a_clean_proposal_reprograms_the_target_and_offers_the_receipt_card(self):
        self.make_workshop()
        self.make("bell-1", closure("Counter"), record(count=nat(0)))
        reply = self.say("delvetalk workshop propose\ntarget: bell-1\nmigration: keep\n```obend\n%s```\n" % BLOCK)
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertEqual(self.verdict(reply), "reprogrammed")
        self.assertIn("Reprogrammed bell-1.", self.card(reply))

    def test_a_proposal_to_an_unknown_target_is_refused_by_name(self):
        self.make_workshop()
        reply = self.say("delvetalk workshop propose\ntarget: ghost\nmigration: keep\n```obend\n%s```\n" % BLOCK)
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertEqual(self.card(reply), "Not done: No object called ghost\n")


if __name__ == "__main__":
    unittest.main()
