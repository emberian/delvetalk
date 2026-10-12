"""Words a card heard (docs/OVERHAUL.md §2.7; docs/FOUNDATION.md §10; HOST-HANDOFF 5.163): words that reach a
card and run none of its spells go to the card's `receive`, and what it leaves `silent` the host gives hob for that
card, never the card's Bend: hob is offered the card's table (its forms and grown verbs) and its doors' (each door's
card and the first three under it), and its answer runs as the speaker's turn on that card under the suspension's
identity. A spell runs; `grow:` grows the verb and uses it in one turn; `ask:` naming a field offers what is still
needed; `none` is silence. Field lines that fit a door's form run at once, no model. A card answers what it reads
itself, and then hob is never asked.

Evidence for OVERHAUL §2.7 (layer: host). Refuted by prose to a card that reaches no model, a reading that runs as
anyone but the speaker or on another card than hob named, a `none` that writes or offers, a card's own answer
replaced by hob's, or a reading not counted by the interpretation quotas.

    python3 -W error -m unittest tests.test_heard -v
"""
import unittest

from tests.host import as_owner, bounds
from tests.test_reflection import Reflection
from tests.wire import field, label, listing, nat, record, reference
from tests.bend import declared

# A thing that rains and takes grown verbs, whose `receive` reads one phrase as its own and is silent to
# anything else, as `Card.answer` is to prose; `cites` are its doors.
BELL = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record Binding:
  name: String
  value: String
record Door:
  label: String
  to: Plans.Reference
record State:
  owner: String
  rains: Nat
  acts: Nat
  last: String
  verb: String
  noted: String
  cites: Lists.List<Door>
sum Heard:
  silent: {}
  noted: {}
def initial() -> State:
  {owner: "", rains: 0n, acts: 0n, last: "", verb: "", noted: "", cites: Lists.List::<Door>.nil({})}
def rain(state: State, input: {text: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {rains: add 1n, last: set input.text}
  state.rains + 1n
def act(state: State, input: {verb: String, text: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {acts: add 1n, last: set input.text, verb: set input.verb}
  state.acts + 1n
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Heard>:
  if input.text == "ring for me" then noting(input.text) else Heard.silent({})
def noting(text: String) -> Activity<Heard>:
  let written(_) = write {noted: set text}
  Heard.noted({})
""", "rain", "act", "receive")

# A room that says only for one who entered: its `say` reads the state its `enter` wrote.
ROOM = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record Binding:
  name: String
  value: String
record State:
  owner: String
  here: Nat
  said: String
sum Heard:
  silent: {}
def initial() -> State:
  {owner: "", here: 0n, said: ""}
def enter(state: State, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {here: add 1n}
  state.here + 1n
def say(state: State, input: {text: String}, context: Abi.Context) -> Activity<Nat>:
  if state.here == 0n then refuse("refused absent: nobody has entered") else saying(state, input.text)
def saying(state: State, text: String) -> Activity<Nat>:
  let written(_) = write {said: set "{natText(state.here)} here: {text}"}
  state.here
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Heard>:
  Heard.silent({})
""", "enter", "say", "receive")

# The world's policy, with what asks the speaker first.
POLICY = declared("""edition ObjectiveBend 1
import ./List.obend as Lists
record State:
  model: String
  system: String
  examples: String
  confirmFor: Lists.List<String>
def initial() -> State:
  {model: "", system: "", examples: "", confirmFor: Lists.List::<String>.nil({})}
""")


# The host's placing spells hob is offered on the card words reached, after its own forms (agent 10).
PLACING = ["rule", "want", "unrule", "unwant"]


class HeardCase(Reflection):
    opening = {}

    def setUp(self):
        super().setUp()
        self.open_library(**self.opening)
        self.make("policy", POLICY, record(model=label("m"), system=label(""), examples=label(""),
                                           confirmFor=listing([label("lock")])))
        self.make("bell", BELL, record(owner=label("ember")))
        self.make("square", BELL, record(owner=label("ember"), cites=listing([record(label=label("bells"), to=reference("bell"))])))

    def say(self, text, card="bell", who="glm", reach="direct", identity=None):
        return self.turn(card, "receive", record(text=label(text), post=label("")), principal=who, reach=reach, identity=identity)

    def value(self, name, card="bell"):
        return field(self.state(card), name)["value"]

    def pending(self):
        return self.host.send(op="world-interpretations")["pending"]

    def settle(self, raw, who="glm"):
        [item] = self.pending()
        settled = self.host.send(op="world-interpretation", id=item["id"],
                                 reply={"status": "replied", "model": "m", "json": None, "raw": raw})
        self.assertEqual(settled["status"], "interpreted", settled)
        return item, as_owner(self.host, settled["resumed"][0], who)


class Heard(HeardCase):
    def test_prose_to_a_card_is_read_by_hob_with_its_table_and_its_spell_runs_as_the_speakers_turn(self):
        asked = self.say("let it rain on the silver one", identity="post-1")
        self.assertEqual(asked["status"], "suspended", asked)
        item, ran = self.settle("delvetalk bell rain\ntext: let it rain on the silver one")
        self.assertEqual((item["object"], item["utterance"]), ("bell", "let it rain on the silver one"))
        self.assertEqual([o["action"] for o in item["offers"]], ["rain"] + PLACING)  # and the host's placing spells
        receipt = ran["receipt"]
        self.assertEqual((receipt["outcome"]["tag"], receipt["identity"]), ("admitted", {"principal": "glm", "intent": "post-1"}), ran)
        self.assertEqual((self.value("rains"), self.value("last")), ("1", "let it rain on the silver one"))
        # The identity is settled by the reading: a retry is answered from it.
        self.assertEqual(self.say("let it rain on the silver one", identity="post-1")["receipt"]["hash"], receipt["hash"])
        self.assertEqual(self.pending(), [])

    def test_none_is_silence_and_writes_and_offers_nothing(self):
        self.assertEqual(self.say("that line belongs in the report, verbatim")["status"], "suspended")
        _, ran = self.settle("none")
        receipt = ran["receipt"]
        self.assertEqual(receipt["outcome"], {"tag": "admitted", "writes": []}, ran)
        self.assertNotIn("offers", receipt)
        self.assertEqual(self.value("rains"), "0")

    def test_grow_at_a_card_grows_the_verb_and_uses_it_in_one_turn(self):
        self.say("I water the bell")
        _, ran = self.settle('grow: water "poured on by a hand"\ndelvetalk bell water\ntext: I water the bell')
        out = ran["receipt"]["outcome"]
        self.assertEqual(out["tag"], "admitted", ran)
        self.assertEqual(out["placements"], [{"object": "bell", "verb": "water", "reading": "poured on by a hand", "takes": "text"}])
        self.assertEqual((self.value("verb"), self.value("last"), self.value("acts")), ("water", "I water the bell", "1"))
        # The next "water it again" is the grown verb, offered to hob and read from the table.
        self.say("water it again")
        item, again = self.settle("delvetalk bell water\ntext: water it again")
        self.assertEqual([o["action"] for o in item["offers"]], ["rain", "water"] + PLACING)
        self.assertEqual((again["receipt"]["outcome"]["tag"], self.value("acts")), ("admitted", "2"))

    def test_a_question_hob_reads_nothing_into_is_answered_by_the_card_with_its_wants(self):
        """The v8 deploy's silent question: hob's `none` to a question is the card itself, exact, with what it wants;
        to other words it stays silence."""
        shown = BELL.replace("import ./World.obend as World", "import ./World.obend as World\nimport ./Document.obend as Document").replace(
            "def receive(", "def render(state: State, context: Abi.Context) -> Document.Document:\n"
                            "  Document.text(\"A brass bell, rained on {natText(state.rains)} times.\\n\")\ndef receive(")
        self.make("brass", shown, record(owner=label("ember")))
        placed = self.say("delvetalk brass want\nname: clapper\nreading: a bell with no clapper\nwhen: new.rains <= 0\n"
                          "asks: delvetalk {request.object} rain / text: <a clapper>", card="brass", who="ember")
        self.assertEqual(placed["status"], "admitted", placed)
        self.assertEqual(self.say("does the bell have a clapper?", card="brass")["status"], "suspended")
        _, answered = self.settle("none")
        carded = self.host.send(op="world-card", principal="glm", object="brass")
        self.assertEqual(carded["status"], "card", carded)
        card = carded["text"]
        self.assertIn("A brass bell, rained on 0 times.", card)
        [offer] = [o["text"] for o in answered["receipt"]["offers"]]
        self.assertEqual(offer, card)
        self.assertTrue(offer.endswith("\nwants clapper: a bell with no clapper: delvetalk brass rain / text: <a clapper>\n"), offer)
        self.assertEqual(answered["receipt"]["outcome"]["tag"], "admitted")
        self.say("lovely evening for it", card="brass", identity="talk")
        _, quiet = self.settle("none")
        self.assertNotIn("offers", quiet["receipt"])

    def test_hob_is_offered_the_hosts_placing_spells_the_law_admits_and_its_proposal_of_one_runs(self):
        """agent 10: hob was offered only a card's own forms, so words asking for a want or a rule got nothing it could
        answer with. The host's placing spells (`rule`, `want`, `unrule`, `unwant`) are offered for a speaker the thing's
        law admits, their fields `ruleLine`'s and `wantLine`'s with the spell last, and hob's proposal of one runs."""
        self.assertEqual(self.say("ask anyone who passes for a clapper while it has none", who="ember", identity="w")["status"], "suspended")
        [item] = self.pending()
        offered = {(o["card"], o["action"]): [f["name"] for f in o["fields"]] for o in item["offers"]}
        self.assertEqual((offered[("bell", "want")], offered[("bell", "rule")], offered[("bell", "unwant")]),
                         (["name", "when", "asks"], ["name", "when", "then"], ["name"]), offered)
        _, ran = self.settle("delvetalk bell want\nname: clapper\nwhen: new.rains <= 0\nasks: delvetalk bell rain / text: <a clapper>", who="ember")
        self.assertEqual(ran["receipt"]["outcome"]["tag"], "admitted", ran)
        rows = self.host.send(op="world-wants", principal="ember", object="bell")["rows"]
        self.assertEqual([r["name"] for r in rows], ["clapper"], rows)

    def long_card(self, name, size):
        """A bell whose `render` returns `size` characters."""
        source = BELL.replace("import ./World.obend as World", "import ./World.obend as World\nimport ./Document.obend as Document").replace(
            "def receive(", "def render(state: State, context: Abi.Context) -> Document.Document:\n"
                            "  Document.text(\"%s\")\ndef receive(" % ("x" * size))
        self.make(name, source, record(owner=label("ember")))

    def test_a_card_shows_at_most_the_bound_and_says_where_the_rest_is_read(self):
        """docs/AGENTS-API.md promises a card under the bound whoever wrote its `render`: at the bound it is whole, one
        over it is clipped to the bound with a closing line, on `world-card` and in the answer to a question hob read nothing into."""
        bound = bounds()["host"]["cardShownChars"]
        self.long_card("exact", bound)
        self.long_card("over", bound + 1)
        self.long_card("long", 2000)
        self.assertEqual(self.host.send(op="world-card", principal="glm", object="exact")["text"], "x" * bound)
        for name in ("over", "long"):
            text = self.host.send(op="world-card", principal="glm", object=name)["text"]
            self.assertEqual(len(text), bound, name)
            self.assertTrue(text.startswith("xxx") and text.endswith("world-inspect %s reads its source]\n" % name), text[-120:])
            self.assertIn("clipped at %d characters" % bound, text)
        want = "delvetalk long want\nname: tail\nreading: last\nwhen: new.rains <= 0\nasks: delvetalk {request.object} rain / text: <a rain>"
        self.assertEqual(self.say(want, card="long", who="ember")["status"], "admitted")
        text = self.host.send(op="world-card", principal="glm", object="long")["text"]
        self.assertEqual(len(text), bound)
        self.assertTrue(text.endswith("source]\nwants tail: last: delvetalk long rain / text: <a rain>\n"), text[-160:])
        self.assertEqual(self.say("does the bell have a clapper?", card="long")["status"], "suspended")
        _, answered = self.settle("none")
        [offer] = [o["text"] for o in answered["receipt"]["offers"]]
        self.assertEqual(offer, self.host.send(op="world-card", principal="glm", object="long")["text"])

    def test_each_of_hobs_spells_reads_the_card_as_the_ones_before_it_wrote_it(self):
        self.make("room", ROOM, record(owner=label("ember")))
        self.assertEqual(self.say("I come in and say hello", card="room")["status"], "suspended")
        _, ran = self.settle("delvetalk room enter\n\ndelvetalk room say\ntext: hello")
        self.assertEqual(ran["receipt"]["outcome"]["tag"], "admitted", ran)
        self.assertEqual((self.value("here", "room"), self.value("said", "room")), ("1", "1 here: hello"))

    def test_hob_may_answer_with_a_plan_that_runs_as_one_turn_and_stands_or_falls_whole(self):
        """HOST-HANDOFF 5.203: hob's spell answer may be a plan; its acts run in one turn read as they come, and a refused act
        refuses them all."""
        self.make("room", ROOM, record(owner=label("ember")))
        self.assertEqual(self.say("I come in, say hello, and it rains", card="room", identity="post-plan")["status"], "suspended")
        _, ran = self.settle("delvetalk plan\ndelvetalk room enter\ndelvetalk room say / text: hello\ndelvetalk bell rain / text: hello")
        self.assertEqual(ran["receipt"]["outcome"]["tag"], "admitted", ran)
        self.assertEqual([a["act"] for a in ran["receipt"]["plan"]["acts"]], [1, 2, 3])
        self.assertEqual((self.value("said", "room"), self.value("rains")), ("1 here: hello", "1"))
        self.say("again, and ring it", card="room")
        _, refused = self.settle("delvetalk plan\ndelvetalk room enter\ndelvetalk bell ring")
        self.assertEqual(refused["receipt"]["outcome"]["tag"], "refused", refused)
        self.assertTrue(refused["receipt"]["outcome"]["reason"].startswith("act 2 (delvetalk bell ring)"), refused)
        self.assertEqual(self.value("here", "room"), "1")

    def test_ask_naming_a_field_offers_what_is_still_needed_and_any_other_question_points_at_the_spells(self):
        self.say("rain on it")
        _, ran = self.settle("ask: what text should the rain carry?")
        self.assertTrue(ran["receipt"]["offers"][0]["text"].startswith("hob: that still needs text; send it filled:\n\n    delvetalk bell rain\n    text: <"), ran)
        self.assertEqual(self.value("rains"), "0")
        self.say("is it raining?")
        _, bare = self.settle("ask: do you mean the weather?")
        self.assertEqual([o["text"] for o in bare["receipt"]["offers"]], ["hob: none of bell's spells takes that; its spells: delvetalk bell ?\n"])
        self.assertEqual(bare["receipt"]["outcome"]["tag"], "admitted")

    def test_field_lines_naming_a_doors_form_run_on_that_door_at_once(self):
        grown = self.say('delvetalk bell grow\nname: water\nreading: poured on by a hand')
        self.assertEqual(grown["status"], "admitted", grown)
        r = self.say("water: from the square", card="square")
        self.assertEqual((r["status"], r["object"]), ("admitted", "square"), r)
        self.assertEqual(self.pending(), [])
        self.assertEqual((self.value("verb"), self.value("last"), self.value("acts", "square")), ("water", "from the square", "0"))

    def test_hob_at_a_card_with_doors_is_offered_the_doors_cards(self):
        self.say("a rain for the bells, please", card="square")
        item, ran = self.settle("delvetalk bell rain\ntext: for the bells")
        self.assertEqual([(o["card"], o["action"]) for o in item["offers"]], [("square", "rain")] + [("square", a) for a in PLACING] + [("bell", "rain")])
        self.assertEqual((ran["receipt"]["outcome"]["tag"], self.value("rains")), ("admitted", "1"))

    def test_a_card_answers_what_it_reads_itself_and_hob_is_not_asked(self):
        r = self.say("ring for me")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "noted"), r)
        self.assertEqual(self.pending(), [])

    def test_words_that_reached_no_card_and_a_spell_ask_no_model(self):
        self.assertEqual(self.say("let it rain", reach=None)["result"]["label"], "silent")
        self.assertEqual(self.say("delvetalk bell rain\ntext: exact")["status"], "admitted")
        self.assertEqual(self.pending(), [])

    def test_an_action_the_policy_asks_first_is_offered_back_and_not_run(self):
        self.say("lock it up")
        _, ran = self.settle('grow: lock "locked by a hand"\ndelvetalk bell lock\ntext: lock it up')
        self.assertTrue(ran["receipt"]["offers"][0]["text"].startswith("hob: that asks first; send it filled:\n\n    delvetalk bell grow\n    name: lock\n"), ran)
        self.assertEqual(self.value("acts"), "0")
        self.assertEqual(self.host.send(op="world-inspect", principal="glm", object="bell")["offered"], ["rain"])



class Quota(HeardCase):
    """A reading is counted by the speaker's hour's interpretations (`interpretQuota`)."""
    opening = {"interpretQuota": 1}

    def test_a_reading_past_the_hours_quota_is_refused_saying_when(self):
        self.assertEqual(self.say("rain on it")["status"], "suspended")
        over = self.say("and again")
        out = over["receipt"]["outcome"]
        self.assertEqual((out["tag"], out["class"]), ("refused", "quota"), over)
        self.assertIn("reply with the spell itself", out["reason"])

if __name__ == "__main__":
    unittest.main()
