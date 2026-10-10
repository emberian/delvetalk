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
from tests.test_objects import MODULES, check, closure, compile_job
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


    def test_a_check_with_neither_block_nor_target_and_a_wrong_card_are_refused_by_name(self):
        self.make_workshop()
        reply = self.say("delvetalk workshop check")
        self.assertEqual(self.refusal(reply), ("noSource", "Include a fenced obend block."))
        # A spell naming another card is the host's: an unknown card is refused by name.
        reply = self.say("delvetalk orchard check\n```obend\nx\n```")
        self.assertEqual((reply["status"], reply["receipt"]["outcome"]["class"], reply["receipt"]["outcome"]["clause"]), ("refused", "badSpell", "otherCard"), reply)
        reply = self.say("delvetalk workshop propose\n```obend\nx\n```")
        self.assertEqual(self.refusal(reply), ("noTarget", "Name a target to propose to."))
        reply = self.say("delvetalk workshop propose\ntarget: ghost\nmigration: keep\n```obend\n%s```\n" % BLOCK)
        self.assertEqual(self.card(reply), "Not done: No object called ghost\n")

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
        self.assertIn("The block <<BEND for source needs a last line that is exactly BEND.", out["reason"])


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
        self.assertIn("Reprogrammed bell-1.\nWas: bell-1 v%d\nNow: bell-1 v%d\n" % (version, version + 1), self.card(reply))
        self.assertEqual(self.host.send(op="world-view", principal="glm", object="bell-1")["version"], version + 1)
        writes = {w["object"]: w for w in reply["receipt"]["outcome"]["writes"]}
        self.assertEqual((writes["bell-1"]["callers"], writes["bell-1"]["kinds"]), (["workshop"], [1]))


    def test_a_package_the_target_cannot_take_is_refused_not_held_nor_blamed_on_adoption(self):
        """A different State with no migration is the package's fault (`stateType`), not the
        target law's: refused by name, not held; and an error adoption meets that is not the
        law's is named as it is, not as the adopter's lack of ownership (codex agent 5)."""
        self.make_workshop()
        self.counter()
        wide = "edition ObjectiveBend 1\nrecord State:\n  count: Nat\n  total: Nat\ndef initial() -> State:\n  {count: 0n, total: 0n}\n"
        propose = lambda block, who, ident: self.turn("workshop", "receive", record(text=label("delvetalk workshop propose\ntarget: bell-1\n```obend\n%s```\n" % block),
                                                                                  post=label("at://x/" + ident)), principal=who, identity=ident)
        wrong = propose(wide, "kimik3", "w1")
        self.assertEqual(self.card(wrong), "Not done: Its State is not bell-1's; name a migration from the old one.\n")
        self.assertEqual(self.refusal(wrong)[0], "stateType")
        self.assertNotIn("Held for", self.say("")["offers"][0]["text"])
        # A migration the package lacks is named with the host's reading, not the bare clause.
        missing = self.turn("workshop", "receive", record(text=label("delvetalk workshop propose\ntarget: bell-1\nmigration: nope\n```obend\n%s```\n" % wide),
                                                          post=label("at://x/m1")), principal="kimik3", identity="m1")
        self.assertEqual(self.refusal(missing)[0], "migration")
        self.assertTrue(self.card(missing).startswith("Not done: ") and "nope" in self.card(missing), self.card(missing))
        # Held while it fit; the owner then changes the target's State, so adopting meets stateType.
        held = propose(BLOCK, "kimik3", "w2")
        self.assertIn("held as #1", self.card(held))
        version = self.host.send(op="world-view", principal="glm", object="bell-1")["version"]
        moved = self.host.send(op="world-reprogram", principal="glm", identity="widen", object="bell-1", version=version,
                               package=wide.replace("{count: 0n, total: 0n}", "{count: 0n, total: 0n}\ndef migrate(old: {count: Nat}) -> State:\n  {count: old.count, total: 0n}"), migration="migrate")
        self.assertEqual(moved["status"], "admitted", moved)
        adopt = self.turn("workshop", "receive", record(text=label("delvetalk workshop adopt / n: 1"), post=label("at://x/a")), principal="glm")
        self.assertEqual(self.card(adopt), "Not done: #1 cannot be applied to bell-1: Its State is not bell-1's; name a migration from the old one.\n")

    def test_a_proposer_withdraws_a_held_proposal(self):
        self.make_workshop()
        self.counter()
        propose = lambda who, ident: self.turn("workshop", "receive", record(text=label("delvetalk workshop propose\ntarget: bell-1\n```obend\n%s```\n" % BLOCK),
                                                                            post=label("at://x/" + ident)), principal=who, identity=ident)
        propose("kimik3", "p1")
        self.assertIn("#1 for bell-1 from kimik3\n", self.say("")["offers"][0]["text"])
        notMine = self.turn("workshop", "receive", record(text=label("delvetalk workshop withdraw / n: 1"), post=label("")), principal="zero")
        self.assertEqual(self.card(notMine), "Not done: Only its proposer, kimik3, withdraws #1\n")
        out = self.turn("workshop", "receive", record(text=label("delvetalk workshop withdraw / n: 1"), post=label("")), principal="kimik3")
        self.assertEqual(self.card(out), "✾ WORKSHOP\n\nWithdrew #1.\n")
        # Twelve are held; a thirteenth drops the oldest with a line.
        for i in range(13):
            last = propose("kimik3", "q%d" % i)
        self.assertIn("The oldest held proposal, #2, was dropped.", self.card(last))


if __name__ == "__main__":
    unittest.main()
