"""The workshop checks a fenced block or a target's source and offers diagnostics; a clean proposal
reprograms the target under the target's own law.

Evidence for FOUNDATION §8 forge (layer: objects).

The workshop: a model takes the reins from a post.

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
def card(diagnostics: String) -> String:
  Document.plain(Workshop.checkedCard(lines(diagnostics)))
def lines(text: String) -> Lists.List<String>:
  if text == "" then Lists.List::<String>.nil() else Lists.List::<String>.cons({head: textTake(text, textBreak(text, "|")), tail: lines(textDrop(text, textBreak(text, "|") + 1n))})
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


class Hints(unittest.TestCase):
    """The checker's hint line, when the host's check forwards one, shows under its problem."""

    def card(self, *diagnostics):
        out = run("card", "|".join(diagnostics))
        self.assertEqual(out["status"], "finished", out)
        return out["value"]["value"]

    def test_a_hint_is_indented_under_its_problem_and_not_counted(self):
        text = self.card("Probe:3: objective-source-parse: Error: expected )",
                         "Probe:3: hint: definitions are `def name(x: T) -> U:`; parameter and result types are required")
        self.assertEqual(text, "✾ WORKSHOP\n\nChecked: 1 problem.\n\n- Probe:3: objective-source-parse: Error: expected )\n"
                               "  hint: definitions are `def name(x: T) -> U:`; parameter and result types are required\n")

    def test_a_message_that_mentions_hint_elsewhere_is_a_problem(self):
        text = self.card("Probe:1: check: unknown name hint", "Probe:2: check: a: hint:less")
        self.assertIn("Checked: 2 problems.", text)
        self.assertNotIn("  hint:", text)


class Workshop(Chain):
    def make_workshop(self):
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))

    def say(self, text, obj="workshop"):
        return self.turn(obj, "receive", record(text=label(text), post=label("at://glm/p/1")), principal="glm")

    def card(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        return reply["offers"][0]["text"]

    def verdict(self, reply):
        return reply["result"]["label"]

    def refusal(self, reply):
        fields = {f["name"]: f["value"]["value"] for f in reply["result"]["payload"]["fields"]}
        return fields["clause"], fields["reading"]

    def test_prose_is_handed_on_and_a_blank_reply_gets_the_usage_card(self):
        self.make_workshop()
        reply = self.say("please make my bell louder")
        self.assertEqual((reply["status"], self.verdict(reply), reply.get("offers", [])), ("admitted", "silent", []), reply)
        blank = self.say("")
        self.assertEqual(self.verdict(blank), "usage")
        self.assertIn("delvetalk workshop check", self.card(blank))

    def test_a_check_with_neither_block_nor_target_and_a_wrong_card_are_refused_by_name(self):
        self.make_workshop()
        reply = self.say("delvetalk workshop check")
        self.assertEqual(self.refusal(reply), ("noSource", "Include a fenced obend block."))
        # A spell naming another card is the host's: an unknown card is refused by name.
        reply = self.say("delvetalk orchard check\n```obend\nx\n```")
        self.assertEqual((reply["status"], reply["receipt"]["outcome"]["class"], reply["receipt"]["outcome"]["clause"]), ("refused", "badSpell", "otherCard"), reply)
        reply = self.say("delvetalk workshop propose\n```obend\nx\n```")
        self.assertEqual(self.refusal(reply), ("noTarget", "Name a target to propose to."))

    def test_the_root_menus_source_block_is_checked(self):
        """The root menu teaches `source: <<BEND` … `BEND`."""
        self.make_workshop()
        reply = self.say("delvetalk workshop check\nsource: <<BEND\n%sBEND\n" % BLOCK)
        self.assertEqual(self.verdict(reply), "clean", reply)
        self.assertEqual(self.card(reply), "✾ WORKSHOP\n\nChecked: it compiles.\n")
        # An unclosed block is the host's refusal, by name.
        open_ = self.say("delvetalk workshop check\nsource: <<BEND\n%s" % BLOCK)
        out = open_["receipt"]["outcome"]
        self.assertEqual((open_["status"], out["class"], out["clause"]), ("refused", "badSpell", "unclosedBlock"), open_)
        self.assertIn("the block <<BEND for source is never closed by a line BEND", out["reason"])

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
        self.assertEqual(self.card(reply), (
            "✾ WORKSHOP\n"
            "\n"
            "Checked: 1 problem.\n"
            "\n"
            "- Checked:5: objective-source-type-proposal: unsupported source type Maybe<Nat> (nullary result type of Checked.initial is not resolvable)\n"
            "  hint: there is no Maybe builtin; declare `sum Maybe<T>:` with arms `none: {}` and `some: {value: T}`\n"))
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
        version = self.host.send(op="world-view", principal="glm", object="bell-1")["version"]
        reply = self.say("delvetalk workshop propose\ntarget: bell-1\n```obend\n%s```\n" % BLOCK)
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertEqual(self.verdict(reply), "reprogrammed")
        after = self.host.send(op="world-view", principal="glm", object="bell-1")["pin"]
        self.assertNotEqual(after, before)
        self.assertEqual(self.card(reply), (
            "✾ WORKSHOP\n"
            "\n"
            "Reprogrammed bell-1.\n"
            "Was: bell-1 v0\n"
            "Now: bell-1 v1\n"))
        self.assertIn("Reprogrammed bell-1.\nWas: bell-1 v%d\nNow: bell-1 v%d\n" % (version, version + 1), self.card(reply))
        self.assertEqual(self.host.send(op="world-view", principal="glm", object="bell-1")["version"], version + 1)
        writes = {w["object"]: w for w in reply["receipt"]["outcome"]["writes"]}
        self.assertEqual((writes["bell-1"]["callers"], writes["bell-1"]["kinds"]), (["workshop"], [1]))

    def test_a_strangers_proposal_is_refused_by_the_targets_law(self):
        self.make_workshop()
        before = self.counter()
        reply = self.turn("workshop", "receive", record(text=label("delvetalk workshop propose\ntarget: bell-1\n```obend\n%s```\n" % BLOCK),
                                                         post=label("at://kim/p/1")), principal="kimik3")
        # The target's law is asked in the turn: the workshop says it was refused, never
        # "Reprogrammed", and holds the proposal for the owner.
        held = self.card(reply)
        self.assertEqual(held, (
            "Not done: owner\n"
            "Held as #1 for the owner of bell-1 to adopt:\n"
            "\n"
            "    delvetalk workshop adopt\n"
            "    n: 1\n"
            "\n"))
        self.assertTrue(held.startswith("Not done: owner\nHeld as #1 for the owner of bell-1 to adopt:\n"), held)
        self.assertEqual(self.host.send(op="world-view", principal="glm", object="bell-1")["pin"], before)
        listing = self.say("")["offers"][0]["text"]
        self.assertIn("#1 for bell-1 from kimik3\n", listing)
        say = lambda text, who: self.turn("workshop", "receive", record(text=label(text), post=label("at://x/1")), principal=who)
        # Adopting is the target's owner's: the law judges the reprogram as the adopter's.
        stranger = say("delvetalk workshop adopt / n: 1", "zero")
        self.assertEqual(self.verdict(stranger), "refused")
        self.assertEqual(self.card(stranger), "Not done: Only the owner of bell-1 adopts #1 (refused owner)\n")
        notMine = say("delvetalk workshop withdraw / n: 1", "zero")
        self.assertEqual(self.card(notMine), "Not done: Only its proposer, kimik3, withdraws #1\n")
        adopted = say("delvetalk workshop adopt / n: 1", "glm")
        self.assertEqual(self.verdict(adopted), "reprogrammed", adopted)
        self.assertEqual(self.card(adopted), "✾ WORKSHOP\n\nAdopted #1 from kimik3: bell-1 is reprogrammed.\n")
        self.assertNotEqual(self.host.send(op="world-view", principal="glm", object="bell-1")["pin"], before)
        self.assertNotIn("#1 for bell-1", self.say("")["offers"][0]["text"])

    def test_a_proposer_withdraws_a_held_proposal(self):
        self.make_workshop()
        self.counter()
        propose = lambda who, ident: self.turn("workshop", "receive", record(text=label("delvetalk workshop propose\ntarget: bell-1\n```obend\n%s```\n" % BLOCK),
                                                                            post=label("at://x/" + ident)), principal=who, identity=ident)
        propose("kimik3", "p1")
        out = self.turn("workshop", "receive", record(text=label("delvetalk workshop withdraw / n: 1"), post=label("")), principal="kimik3")
        self.assertEqual(self.card(out), "✾ WORKSHOP\n\nWithdrew #1.\n")
        # Sixteen are held; a seventeenth drops the oldest with a line.
        for i in range(17):
            last = propose("kimik3", "q%d" % i)
        self.assertIn("The oldest held proposal, #2, was dropped.", self.card(last))

    def test_a_proposal_to_an_unknown_target_is_refused_by_name(self):
        self.make_workshop()
        reply = self.say("delvetalk workshop propose\ntarget: ghost\nmigration: keep\n```obend\n%s```\n" % BLOCK)
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertEqual(self.card(reply), "Not done: No object called ghost\n")


if __name__ == "__main__":
    unittest.main()
