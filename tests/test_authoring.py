"""Authoring (docs/AUTHORING.md): behaviour is a package layer, written at three distances (a clause, a verb body, a
kind body) through the workshop and checked by one checker. A fresh genesis, two residents casting spells by
`receive` as the bridge does (AUTHORING §1's harness); each test is a §5 step's control or a §6 build as typed.

Evidence for AUTHORING §5 (layer: objects). Refuted by: a layer the workshop cannot check over a kind or a thing; a
body that cannot compile admitted at `kinds make`, or refused without the checker's line; a kind over a kind whose
things do not run every body below it or are not judged by every text below it.

    python3 -W error -m unittest tests.test_authoring -v
"""
import contextlib
import tempfile
import unittest

from tests.town import Town

YUE, KES = "did:plc:yueyueyueyueyueyueyueyue", "did:plc:kestrelkestrelkestrelkes"

# AUTHORING §1's clicker: a layer over RECORD, one verb writing a numbered line.
CLICKER = """layer over ./Record.obend
edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Text.obend as Text
import ./Relation.obend as Relations
type State = Super.State
form click:
def click(state: State, context: Abi.Context) -> Activity<Nat>:
  Super.inscribe(state, "click", "click {natText(Relations.count(state.lines) + 1n)}", context)
def actions(state: State, context: Abi.Context) -> Lists.List<String>:
  Text.words("click write lines")
"""
# The same with §1's one bad reference, on line 11.
BROKEN = CLICKER.replace("Relations.count(state.lines)", "Super.Relations.count(state.lines)")


def told(reply):
    """What a reply says: its offers' text, or a usage's."""
    return "".join(o.get("text", "") for o in reply.get("offers") or []) or reply.get("text", "")


def outcome(reply):
    return (reply.get("receipt") or {}).get("outcome") or {}


class Authoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.said = 0
        for did, handle in ((YUE, "yue.delve.town"), (KES, "kestrel.delve.town")):
            cls.town.send(op="world-arrive", principal="transport", did=did, handle=handle)

    def say(self, who, card, text):
        type(self).said += 1
        from tests.wire import label, record
        return self.town.send(op="world-turn", principal=who, object=card, method="receive", identity="authoring-%d" % self.said,
                              argument=record(text=label(text), post=label("")))

    def admitted(self, who, card, text):
        r = self.say(who, card, text)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def check_over(self, over, source):
        return told(self.admitted(YUE, "workshop", "delvetalk workshop check\nover: %s\n```obend\n%s```\n" % (over, source)))

    # §5 step 2: a layer checked over what it would be laid on.
    def test_a_layer_is_checked_over_a_kinds_things_or_over_a_thing(self):
        self.assertIn("Checked: it compiles.", self.check_over("kind/record", CLICKER))
        self.assertIn("Checked: it compiles.", self.check_over("bell/1", CLICKER))
        broken = self.check_over("kind/record", BROKEN)
        self.assertIn("Checked: 1 problem.", broken)
        self.assertIn("- Layer1:11: objective-core-elaboration: missing imported declaration Record.Relations", broken)
        r = self.say(YUE, "workshop", "delvetalk workshop check\nover: nowhere/9\n```obend\n%s```\n" % CLICKER)
        self.assertEqual((outcome(r).get("clause"), outcome(r).get("reading")), ("noObject", "No kind or thing called nowhere/9"), r)

    # §5 step 3: a body that cannot compile is refused at `kinds make` with the checker's line; nothing is made.
    def test_a_kind_whose_body_cannot_compile_is_refused_with_the_checkers_line(self):
        r = self.say(YUE, "kinds", "delvetalk kinds make\nname: badclick\nof: record\nbody: <<BEND\n%sBEND\n" % BROKEN)
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "body"), r)
        self.assertIn("it does not compile over record, so nothing was made:\nLayer1:11: objective-core-elaboration: missing imported declaration Record.Relations",
                      outcome(r)["reason"])
        self.assertEqual(self.say(KES, "kind/badclick", "delvetalk kind/badclick ?")["status"], "refused")
        self.admitted(YUE, "kinds", "delvetalk kinds make\nname: clicker\nof: record\nform: what: text 1..80\nbody: <<BEND\n%sBEND\n" % CLICKER)
        self.admitted(KES, "kind/clicker", "delvetalk kind/clicker make / what: a clicker")
        self.assertIn("#1 is written: click 1", told(self.admitted(YUE, "clicker/1", "delvetalk clicker/1 click")))

    # §5 step 5: a kind of any kind is a layer stack, judged by every text below it.
    def test_a_kind_over_a_kind_runs_every_body_below_it_and_carries_every_text(self):
        self.admitted(YUE, "kinds", "delvetalk kinds make / name: rainbell / of: kind/bell")
        usage = told(self.say(KES, "kind/rainbell", "delvetalk kind/rainbell ?"))
        self.assertIn("delvetalk kind/rainbell make\ncolour: <amber, violet, silver>\nseed: <text, 1 to 80 characters>", usage)
        self.admitted(KES, "kind/rainbell", "delvetalk kind/rainbell make / colour: silver / seed: a bell over a bell")
        for i in range(6):
            self.assertEqual(outcome(self.admitted(YUE if i % 2 else KES, "rainbell/1", "delvetalk rainbell/1 rain / text: drop %d" % i)).get("fired"), None)
        seventh = self.admitted(YUE, "rainbell/1", "delvetalk rainbell/1 rain / text: the seventh")
        self.assertIn("rule seven of ember.delve.town fired: delvetalk rainbell/1 ring", seventh["revealed"][0])
        rules = told(self.say(KES, "rainbell/1", "delvetalk rainbell/1 rules"))
        self.assertIn("» seven (ember.delve.town, carried from kind/bell)", rules)
        # Three deep, with a body of its own over the bell's: both answer.
        chime = ("layer over ./Record.obend\nedition ObjectiveBend 1\nimport ./Abi.obend as Abi\nimport ./List.obend as Lists\nimport ./Form.obend as Form\n"
                 "type State = Super.State\nform chime:\ndef chime(state: State, context: Abi.Context) -> Activity<Nat>:\n"
                 "  Super.inscribe(state, \"chime\", \"chimed\", context)\n")
        self.admitted(YUE, "kinds", "delvetalk kinds make\nname: chimebell\nof: kind/rainbell\nbody: <<BEND\n%sBEND\n" % chime)
        self.admitted(KES, "kind/chimebell", "delvetalk kind/chimebell make / colour: amber / seed: three deep")
        self.assertIn("#1 is written: chimed", told(self.admitted(KES, "chimebell/1", "delvetalk chimebell/1 chime")))
        self.assertIn("yue.delve.town (yours): still a bell", told(self.admitted(YUE, "chimebell/1", "delvetalk chimebell/1 rain / text: still a bell")))
        # `of` names a kind, or is refused by name.
        for of, reading in (("bell/1", "bell/1 is no kind"), ("kinds", "kinds makes kinds")):
            r = self.say(YUE, "kinds", "delvetalk kinds make / name: stray / of: %s" % of)
            self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "of"), r)
            self.assertIn(reading, outcome(r)["reason"])


if __name__ == "__main__":
    unittest.main()
