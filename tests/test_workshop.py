"""The workshop: a model takes the reins from a post.

The host answers `check`, `inspect` and a `reprogram` of another object, judged by the
target's own law with request.caller = the workshop. A block must be a package with
`initial` (the host checks entry `initial`).
"""
import unittest

from tests.test_chain import Chain
from tests.test_objects import MODULES, check, closure, compile_job, computation, row_names
from tests.test_turn_world import closure as world_closure, label, nat, record

PROBE = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./Document.obend as Document
import ./Workshop.obend as Workshop
def kind(block: Workshop.Block) -> String:
  match block:
    case none(_): "none"
    case some(s): textConcat("some:", s.source)
def found(text: String) -> String:
  kind(Workshop.fenced(text))
def card(diagnostics: String) -> String:
  Document.plain(Workshop.checkedCard(lines(diagnostics)))
def lines(text: String) -> Lists.List<String>:
  if text == "" then Lists.List::<String>.nil() else Lists.List::<String>.cons({head: textTake(text, textBreak(text, "|")), tail: lines(textDrop(text, textBreak(text, "|") + 1n))})
def size(text: String) -> Nat:
  match Workshop.fenced(text):
    case none(_): 0n
    case some(s): textLength(s.source)
"""
BLOCK = "edition ObjectiveBend 1\nrecord State:\n  count: Nat\ndef initial() -> State:\n  {count: 0n}\n"


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


class Hints(unittest.TestCase):
    """The checker's hint line, when the host's check forwards one, shows under its problem."""

    def card(self, *diagnostics):
        out = run("card", "|".join(diagnostics))
        self.assertEqual(out["status"], "finished", out)
        return out["value"]["value"]

    def test_a_hint_is_indented_under_its_problem_and_not_counted(self):
        text = self.card("Probe:3: objective-source-parse: Error: expected )",
                         "Probe:3: hint: definitions are `def name(x: T) -> U:`; parameter and result types are required")
        print("\n--- hinted check ---\n" + text)
        self.assertEqual(text, "✾ WORKSHOP\n\nChecked: 1 problem.\n\n- Probe:3: objective-source-parse: Error: expected )\n"
                               "  hint: definitions are `def name(x: T) -> U:`; parameter and result types are required\n")

    def test_a_message_that_mentions_hint_elsewhere_is_a_problem(self):
        text = self.card("Probe:1: check: unknown name hint", "Probe:2: check: a: hint:less")
        self.assertIn("Checked: 2 problems.", text)
        self.assertNotIn("  hint:", text)


class Types(unittest.TestCase):
    def test_every_method_compiles_as_an_activity(self):
        for method in ("check", "propose", "receive"):
            with self.subTest(method=method):
                reply = compile_job(closure("Workshop"), method)
                self.assertEqual(reply["status"], "compiled", reply)
                self.assertEqual(row_names(computation(reply["artifact"]["type"])["plan"]["row"])[:3], ["view", "write", "call"])


class Workshop(Chain):
    def make_workshop(self):
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))

    def say(self, text, obj="workshop"):
        return self.turn(obj, "receive", record(text=label(text), post=label("at://glm/p/1"), slot=label("")), principal="glm")

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
        self.assertEqual(self.card(self.say("")), self.card(reply))

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

    def test_a_block_with_a_kernel_hint_shows_it(self):
        """The host's check forwards the kernel's hint as the next diagnostic (lane/host4 7361a6e)."""
        self.make_workshop()
        reply = self.say("delvetalk workshop check\n```obend\nedition ObjectiveBend 1\nrecord State:\n  count: Nat\ndef initial() -> Maybe<Nat>:\n  {count: 0n}\n```\n")
        print("\n--- check card ---\n" + self.card(reply))
        self.assertEqual(self.verdict(reply), "flawed")
        self.assertIn("\n  hint: there is no Maybe builtin", self.card(reply))

    def test_a_target_is_inspected_and_its_source_checked(self):
        self.make_workshop()
        self.make("bell-1", closure("Counter"), record())
        reply = self.say("delvetalk workshop check\ntarget: bell-1")
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertIn(self.verdict(reply), ("clean", "flawed"))

    def counter(self, owner="glm"):
        """A Counter whose law names its proposer: glm creates it, so the law admits glm's
        amendment and reprogram, and anyone's ordinary writes."""
        law = 'law owner: request.kind == 0 or request.subject == "%s"\n' % owner
        source = open(MODULES["Counter"]).read().replace("record State:", law + "record State:", 1)
        modules = world_closure("Counter", override={"Counter": source})
        r = self.host.send(op="world-create", principal=owner, identity="mk-bell-1", object="bell-1", modules=modules,
                           entry="initial", seed=record(count=nat(0)))
        self.assertEqual(r["status"], "created", r)
        return self.host.send(op="world-view", principal=owner, object="bell-1")["pin"]

    def test_a_clean_proposal_reprograms_another_object_under_its_law(self):
        self.make_workshop()
        before = self.counter()
        reply = self.say("delvetalk workshop propose\ntarget: bell-1\n```obend\n%s```\n" % BLOCK)
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertEqual(self.verdict(reply), "reprogrammed")
        after = self.host.send(op="world-view", principal="glm", object="bell-1")["pin"]
        self.assertNotEqual(after, before)
        print("\n--- reprogrammed card ---\n" + self.card(reply))
        self.assertIn("Reprogrammed bell-1.", self.card(reply))
        writes = {w["object"]: w for w in reply["receipt"]["outcome"]["writes"]}
        self.assertEqual((writes["bell-1"]["callers"], writes["bell-1"]["kinds"]), (["workshop"], [1]))

    def test_a_strangers_proposal_is_refused_by_the_targets_law(self):
        self.make_workshop()
        before = self.counter()
        reply = self.turn("workshop", "receive", record(text=label("delvetalk workshop propose\ntarget: bell-1\n```obend\n%s```\n" % BLOCK),
                                                         post=label("at://kim/p/1"), slot=label("")), principal="kimik3")
        # The target's law is asked in the turn: the workshop says it was refused, never "Reprogrammed".
        self.assertEqual(self.card(reply), "Not done: owner\n")
        self.assertEqual(self.host.send(op="world-view", principal="glm", object="bell-1")["pin"], before)

    def test_a_proposal_to_an_unknown_target_is_refused_by_name(self):
        self.make_workshop()
        reply = self.say("delvetalk workshop propose\ntarget: ghost\nmigration: keep\n```obend\n%s```\n" % BLOCK)
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertEqual(self.card(reply), "Not done: No object called ghost\n")


if __name__ == "__main__":
    unittest.main()
