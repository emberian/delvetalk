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
# AUTHORING §6.1: a tally over RECORD whose rule reads the maker's `ringAt` (the body with its header written out;
# `TALLY_SHORT` is it as §6.1 types it, the workshop writing the header).
TALLY = """delvetalk kinds make / name: tally / of: record / head: {maker}'s tally, ringing at {ringAt}
form: <<END
seed: text 1..80
ringAt: natural 1..768
END
law: <<END
rule chosen "rings at the number its maker chose": count(new.lines where verb == "rain") == new.ringAt and count(old.lines where verb == "rain") + 1 == new.ringAt then delvetalk {request.object} ring
law rung "it rings at its number, not before": not (request.method == "ring") or count(new.lines where verb == "rain") >= new.ringAt
END
body: <<BEND
layer over ./Record.obend
edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Text.obend as Text
type State = Super.State
form rain:
  text: text 1..200
form ring:
def rain(state: State, input: RainInput, context: Abi.Context) -> Activity<Nat>:
  Super.inscribe(state, "rain", input.text, context)
def ring(state: State, context: Abi.Context) -> Activity<Bool>:
  Super.mark(state, "rung", context)
def actions(state: State, context: Abi.Context) -> Lists.List<String>:
  Lists.concat(Super.actions(state, context), Text.words("rain ring"))
BEND"""
TALLY_SHORT = TALLY.replace("name: tally", "name: rainy").replace("""layer over ./Record.obend
edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Text.obend as Text
type State = Super.State
""", "").replace("""def actions(state: State, context: Abi.Context) -> Lists.List<String>:
  Lists.concat(Super.actions(state, context), Text.words("rain ring"))
""", "")
# AUTHORING §5 step 4's counter: what a resident types over kind/record.
COUNTER = """form bump:
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  Super.inscribe(state, "bump", "{context.handle}", context)
"""
# §1's first counter: a whole package with no `receive`, which compiles and no spell reaches.
BARE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Text.obend as Text
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
form bump:
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {count: add 1n}
  state.count + 1n
def methods() -> Lists.List<String>:
  Text.words("bump")
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


    # §5 step 6 and §6.1: a tally that rings at the number its maker chose, read from its form as `new.ringAt`.
    def test_a_clause_reads_a_form_field_its_maker_chose(self):
        tally = TALLY
        self.admitted(YUE, "kinds", tally)
        self.admitted(KES, "kind/tally", "delvetalk kind/tally make / seed: rains on the roost / ringAt: 3")
        for i in range(2):
            self.assertFalse(self.admitted(YUE, "tally/1", "delvetalk tally/1 rain / text: rain %d" % i).get("revealed", [""])[0].startswith("rule"))
        # Before its number, a hand that rings it is refused by the kind's law.
        r = self.say(KES, "tally/1", "delvetalk tally/1 ring")
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "rung"), r)
        third = self.admitted(YUE, "tally/1", "delvetalk tally/1 rain / text: the third")
        self.assertIn("rule chosen of yue.delve.town fired: delvetalk tally/1 ring", third["revealed"][0], third)
        [rang] = third["delivered"]
        self.assertEqual((rang["receipt"]["identity"]["intent"], rang["revealed"]), ("rule:tally/1:chosen:%d" % third["receipt"]["height"], ["tally/1's marks: 1"]), rang)

    # §5 step 4: the workshop writes the header; §1's counter is four lines, and a package no spell reaches is refused.
    def test_a_four_line_counter_drafted_over_a_kind_is_adopted_and_used_by_another(self):
        held = self.admitted(YUE, "workshop", "delvetalk workshop draft / name: counter / over: kind/record\n```obend\n%s```\n" % COUNTER)
        self.assertIn("Checked: it compiles. Held as #", told(held), held)
        n = told(held).split("Held as #")[1].split(";")[0]
        made = self.admitted(YUE, "workshop", "delvetalk workshop adopt / n: %s" % n)
        self.assertIn("Made counter from #%s; it is yours." % n, told(made))
        [create] = [c for c in outcome(made)["creates"] if c["object"] == "counter"]
        self.assertEqual(create["madeFrom"]["object"], "workshop")
        usage = told(self.say(KES, "counter", "delvetalk counter ?"))
        self.assertIn("delvetalk counter bump", usage)
        self.assertIn("#1 is written: kestrel.delve.town", told(self.admitted(KES, "counter", "delvetalk counter bump")))
        # A body over a kind with a mistake: the checker's line, and where the body's own lines start.
        r = self.admitted(YUE, "workshop", "delvetalk workshop draft / name: counter2 / over: kind/record\n```obend\n%s```\n"
                          % COUNTER.replace("context.handle", "context.hand"))
        self.assertIn("Layer1:18:", told(r))
        self.assertIn("Lines 1 to 15 are the header the workshop wrote; your first line is line 16.", told(r))
        # The bare counter of §1: it compiles, and nothing could ever cast a spell on it.
        r = self.say(YUE, "workshop", "delvetalk workshop draft / name: bare\n```obend\n%s```\n" % BARE)
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "noReceive"), r)
        self.assertIn("No spell reaches it: it has no receive.", told(self.admitted(YUE, "workshop", "delvetalk workshop check\n```obend\n%s```\n" % BARE)))

    # §6.1 as typed: the body is forms and defs, the workshop writing the header and `actions()`.
    def test_a_kind_body_of_forms_and_defs_alone_gets_the_workshops_header(self):
        self.admitted(YUE, "kinds", TALLY_SHORT)
        self.admitted(KES, "kind/rainy", "delvetalk kind/rainy make / seed: on the sill / ringAt: 2")
        usage = told(self.say(KES, "rainy/1", "delvetalk rainy/1 ?"))
        self.assertIn("delvetalk rainy/1 rain\ntext:", usage)
        self.admitted(KES, "rainy/1", "delvetalk rainy/1 rain / text: one")
        second = self.admitted(YUE, "rainy/1", "delvetalk rainy/1 rain / text: two")
        self.assertIn("rule chosen of yue.delve.town fired: delvetalk rainy/1 ring", second["revealed"][0], second)


    # D-imports: every library import a module lacks, named in one refusal (§1 took a round each for Plan and World).
    def test_the_checker_names_every_missing_import_at_once(self):
        lacking = BARE.replace("import ./Plan.obend as Plans\n", "").replace("import ./World.obend as World\n", "")
        got = told(self.admitted(YUE, "workshop", "delvetalk workshop check\n```obend\n%s```\n" % lacking))
        self.assertIn("this module needs 2 library imports it does not name; add them: import ./Plan.obend as Plans; import ./World.obend as World", got)
        self.assertIn("Checked: it compiles.", told(self.admitted(YUE, "workshop", "delvetalk workshop check\n```obend\n%s```\n" % BARE)))


    # §5 step 7: a kind forked through the workshop, credited on its card to the kind and hand it is after.
    def test_a_kind_forked_whole_or_with_a_new_body_says_what_it_is_after(self):
        tap = "form tap:\ndef tap(state: State, context: Abi.Context) -> Activity<Nat>:\n  Super.inscribe(state, \"tap\", \"tapped\", context)\n"
        self.admitted(YUE, "kinds", "delvetalk kinds make\nname: tapper\nof: record\nbody: <<BEND\n%sBEND\n" % tap)
        held = told(self.admitted(KES, "workshop", "delvetalk workshop draft / name: mytapper / from: kind/tapper"))
        n = held.split("Held as #")[1].split(";")[0]
        self.assertIn("Made kind/mytapper from #%s; it is yours." % n, told(self.admitted(KES, "workshop", "delvetalk workshop adopt / n: %s" % n)))
        made = self.town.send(op="world-inspect", principal=KES, object="kind/mytapper")
        self.assertEqual(made["madeFrom"]["object"], "kind/tapper", made)
        self.assertRegex(told(self.say(KES, "kind/mytapper", "delvetalk kind/mytapper ?")), r"After kind/tapper by yue\.delve\.town, entry \d+\.\n")
        self.admitted(KES, "kind/mytapper", "delvetalk kind/mytapper make")
        self.assertIn("#1 is written: tapped", told(self.admitted(YUE, "mytapper/1", "delvetalk mytapper/1 tap")))
        # A fork with a body of its own: checked as kinds checks a body, and its things run it.
        knock = tap.replace("tapped", "knocked").replace("tap", "knock")
        held = told(self.admitted(KES, "workshop", "delvetalk workshop draft / name: knocker / from: kind/tapper\n```obend\n%s```\n" % knock))
        n = held.split("Held as #")[1].split(";")[0]
        self.admitted(KES, "workshop", "delvetalk workshop adopt / n: %s" % n)
        self.admitted(YUE, "kind/knocker", "delvetalk kind/knocker make")
        self.assertIn("#1 is written: knocked", told(self.admitted(KES, "knocker/1", "delvetalk knocker/1 knock")))


    # §6.2: a guestbook that thanks each signer by name, one signature a hand.
    def test_a_guestbook_thanks_each_signer_by_name(self):
        sign = ("form sign:\n  text: text 1..200\n"
                "def sign(state: State, input: SignInput, context: Abi.Context) -> Activity<Nat>:\n"
                "  let title = Super.field(state, \"title\")\n"
                "  let written(_) = write {lines: insert {author: context.principal, handle: context.handle, verb: \"sign\", text: input.text, at: context.height, n: state.next}, next: add 1n}\n"
                "  Card.tell(state.next, Document.text(\"Thank you, {context.handle}. Signer {natText(state.next)} of {title}.\\n\"))\n")
        self.admitted(YUE, "kinds", "delvetalk kinds make / name: guestbook / of: record / head: {maker}'s guestbook / form: title: text 1..80\n"
                      "law: law once \"one signature a hand\": count(new.lines where author == request.subject) <= 1\nbody: <<BEND\n%sBEND\n" % sign)
        self.admitted(YUE, "kind/guestbook", "delvetalk kind/guestbook make / title: the roost")
        self.assertIn("Thank you, kestrel.delve.town. Signer 1 of the roost.", told(self.admitted(KES, "guestbook/1", "delvetalk guestbook/1 sign / text: here at dusk")))
        r = self.say(KES, "guestbook/1", "delvetalk guestbook/1 sign / text: again")
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "once"), r)
        self.assertIn("Thank you, yue.delve.town. Signer 2 of the roost.", told(self.admitted(YUE, "guestbook/1", "delvetalk guestbook/1 sign / text: mine")))

    # §6.3: a lamp that lights when two keys lie in one place: clauses and a grown verb, no Bend.
    def test_a_lamp_lights_when_two_keys_lie_in_one_place(self):
        self.admitted(YUE, "kinds", "delvetalk kinds make / name: lamp / of: record / head: a lamp")
        self.admitted(YUE, "kind/lamp", "delvetalk kind/lamp make")
        self.admitted(YUE, "kind/garden", "delvetalk kind/garden make / name: the keyring")
        self.admitted(YUE, "lamp/1", "delvetalk lamp/1 grow / name: light / reading: lit when both keys lie in the keyring / takes: text")
        self.admitted(YUE, "lamp/1", 'delvetalk lamp/1 adopt / law: law ruled "only its maker lights it": not (request.verb == "light") or request.subject == new.maker')
        self.admitted(YUE, "garden/1", 'delvetalk garden/1 rule / name: twokeys / reading: both keys here light lamp/1 / when: "garden/1/bell/1" in new.things.object and '
                      '"garden/1/bell/2" in new.things.object and not ("garden/1/bell/1" in old.things.object and "garden/1/bell/2" in old.things.object) / then: delvetalk lamp/1 light / text: both keys')
        self.admitted(YUE, "lamp/1", 'delvetalk lamp/1 want / name: dark / reading: unlit / when: count(new.lines where verb == "light") == 0 / asks: delvetalk garden/1 ?')
        self.assertIn("dark", [w["name"] for w in self.town.send(op="world-wants", principal=KES, object="lamp/1")["rows"]])
        r = self.say(KES, "lamp/1", "delvetalk lamp/1 light / text: by hand")
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "ruled"), r)
        self.assertNotIn("fired", str(self.admitted(KES, "garden/1", "delvetalk garden/1 plant / colour: amber / seed: the first key").get("revealed")))
        both = self.admitted(KES, "garden/1", "delvetalk garden/1 plant / colour: violet / seed: the second key")
        self.assertIn("rule twokeys of yue.delve.town fired: delvetalk lamp/1 light / text: both keys", both["revealed"][0], both)
        self.assertNotIn("dark", [w["name"] for w in self.town.send(op="world-wants", principal=KES, object="lamp/1")["rows"]])

    # §6.4: a stall that trades a thing for a promise: the promise is the buyer's line, the trade a rule, custody THING's.
    def test_a_stall_trades_a_thing_for_a_promise(self):
        self.admitted(YUE, "porch", "delvetalk porch enter")
        self.admitted(YUE, "porch/gemstone", "delvetalk porch/gemstone acquire")
        self.admitted(YUE, "kinds", "delvetalk kinds make / name: stall / of: record / head: {maker}'s stall: {wares} for a promise\n"
                      "form: <<END\nwares: text 1..80\nthing: text 1..128\nEND\nlaw: <<END\n"
                      'law promised "a promise is the buyer\'s own line, once": count(new.lines where author == request.subject) <= 1\n'
                      'rule trade "a promise buys the thing": request.verb == "promise" then delvetalk {new.thing} offer / to: {request.subject} / until: {request.clock + 1440}\nEND')
        self.admitted(YUE, "kind/stall", "delvetalk kind/stall make / wares: a gemstone that sometimes sparkles / thing: porch/gemstone")
        self.admitted(YUE, "stall/1", "delvetalk stall/1 grow / name: promise / reading: what you will bring, in your words / takes: text")
        promised = self.admitted(KES, "stall/1", "delvetalk stall/1 promise / text: three rains on your bell by Sunday")
        self.assertIn("rule trade of yue.delve.town fired: delvetalk porch/gemstone offer", promised["revealed"][0], promised)
        r = self.say(KES, "stall/1", "delvetalk stall/1 promise / text: and a fourth")
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "promised"), r)
        self.assertIn("porch/gemstone", told(self.admitted(KES, "me", "delvetalk me accept / thing: porch/gemstone")))
        view = self.town.send(op="world-view", principal=KES, object="porch/gemstone")["state"]["fields"]
        self.assertEqual([f["value"] for f in view if f["name"] == "holder"][0]["fields"][1]["value"]["value"], KES)

    # §6.5: a riddle box that opens for the right answer, kept as a hash.
    def test_a_riddle_box_opens_for_the_right_answer(self):
        box = ("form lock:\n  answer: text 1..80\nform answer:\n  text: text 1..80\n"
               "def lock(state: State, input: LockInput, context: Abi.Context) -> Activity<Nat>:\n"
               "  if context.principal != state.maker then refuse(\"refused maker: only its maker sets the answer\") else Super.inscribe(state, \"lock\", sha256Text(input.answer), context)\n"
               "def answer(state: State, input: AnswerInput, context: Abi.Context) -> Activity<Bool>:\n"
               "  if Lists.any(Relations.rows(state.lines), fn(l: Rows.Line) -> Bool: l.verb == \"lock\" && l.text == sha256Text(input.text)) then Super.mark(state, \"open\", context) else refuse(\"refused shut: the box stays shut\")\n")
        self.admitted(YUE, "kinds", "delvetalk kinds make / name: riddlebox / of: record / head: a riddle box: {riddle} / form: riddle: text 1..200\nbody: <<BEND\n%sBEND\n" % box)
        self.admitted(YUE, "kind/riddlebox", "delvetalk kind/riddlebox make / riddle: what keeps nothing and holds every phase?")
        r = self.say(KES, "riddlebox/1", "delvetalk riddlebox/1 lock / answer: a forgery")
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "maker"), r)
        self.admitted(YUE, "riddlebox/1", "delvetalk riddlebox/1 lock / answer: the moon")
        r = self.say(KES, "riddlebox/1", "delvetalk riddlebox/1 answer / text: the sun")
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "shut"), r)
        opened = self.admitted(KES, "riddlebox/1", "delvetalk riddlebox/1 answer / text: the moon")
        self.assertEqual(opened["result"], {"tag": "boolean", "value": True}, opened)


    # §3 (b): a verb grown with a body is a one-method layer the workshop writes, checks and lays; on another's
    # thing it is held for the owner. §4: the verb library is single-verb kinds laid by `become`, credited.
    def test_a_verb_grown_with_a_body_and_a_verb_kind_laid_by_become(self):
        water = 'Super.inscribe(state, "water", "{input.text} (watered by {context.handle})", context)'
        self.admitted(YUE, "kinds", "delvetalk kinds make / name: pot / of: record / head: a pot")
        self.admitted(YUE, "kind/pot", "delvetalk kind/pot make")
        grown = self.admitted(YUE, "pot/1", "delvetalk pot/1 grow / name: water / takes: text\nbody: <<BEND\n%s\nBEND" % water)
        self.assertIn("water grows on pot/1, with its body.", told(grown))
        self.assertIn("delvetalk pot/1 water\ntext:", told(self.say(KES, "pot/1", "delvetalk pot/1 ?")))
        self.assertIn("#1 is written: a cup (watered by kestrel.delve.town)", told(self.admitted(KES, "pot/1", "delvetalk pot/1 water / text: a cup")))
        # A body that does not compile names its line past what the workshop wrote.
        bad = told(self.admitted(YUE, "pot/1", "delvetalk pot/1 grow / name: spill / takes: nothing\nbody: <<BEND\nSuper.inscribe(state, \"spill\", nowhere, context)\nBEND"))
        self.assertIn("Checked: 1 problem.", bad)
        self.assertIn("Lines 1 to 17 are what the workshop wrote around your body; its first line is line 18.", bad)
        # On another's thing: held for its owner, who lays it.
        held = told(self.admitted(KES, "pot/1", "delvetalk pot/1 grow / name: pour / takes: nothing\nbody: <<BEND\nSuper.inscribe(state, \"pour\", \"poured\", context)\nBEND"))
        n = held.split("is held as #")[1].split(" ")[0]
        self.assertIn("for the owner of pot/1 to lay", held)
        r = self.say(KES, "workshop", "delvetalk workshop adopt / n: %s" % n)
        self.assertEqual(r["status"], "refused", r)
        self.assertIn("Laid #%s on pot/1." % n, told(self.admitted(YUE, "workshop", "delvetalk workshop adopt / n: %s" % n)))
        self.assertIn("#2 is written: poured", told(self.admitted(KES, "pot/1", "delvetalk pot/1 pour")))
        # A verb anyone may lay on a thing of theirs: a kind whose body is the one verb, laid by `become`.
        self.admitted(YUE, "kinds", "delvetalk kinds make / name: watering / of: record\nbody: <<BEND\nform water:\n  text: text 1..200\n"
                      "def water(state: State, input: WaterInput, context: Abi.Context) -> Activity<Nat>:\n  %s\nBEND" % water)
        self.admitted(KES, "kind/pot", "delvetalk kind/pot make")
        self.admitted(KES, "pot/2", "delvetalk pot/2 become / kind: kind/watering")
        self.assertRegex(told(self.say(YUE, "pot/2", "delvetalk pot/2 ?")), r"After kind/watering by yue\.delve\.town, entry \d+\.")
        self.assertIn("#1 is written: rain (watered by yue.delve.town)", told(self.admitted(YUE, "pot/2", "delvetalk pot/2 water / text: rain")))


if __name__ == "__main__":
    unittest.main()
