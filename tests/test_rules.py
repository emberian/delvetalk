"""Rules and wants on things (docs/OVERHAUL.md §2, §3; docs/FOUNDATION.md §10; docs/FOUNDATION.md §5): a rule placed
on a card fires its spell at the commit of a write that makes its condition hold, under the name of whoever
placed it, journaled `fired` with the delivery it staged and re-derived by replay; at most eight a commit and
four firings down a chain, the rest journaled `unfired` with why; `rules` reads them back with the entry and
receipt of their last firing; a want poses while it holds, and the write that opens or closes it journals
`wanted` or `unwanted`; the admitted reply says what the write moved, opened and where it stands.

Evidence for OVERHAUL §5 step 3's controls, on the town genesis builds (layer: scenarios). The five outcomes
of FOUNDATION §10 on the town's own objects are `test_reaction`.
"""
import unittest

from tests.host import bounds
from tests.test_scenarios import Arc, GLM, KIM
from tests.test_properties import OPENER
from tests.wire import label, record

TWO = "count(new.lines) >= 2 and count(old.lines) <= 1"


class Bell(Arc):
    """A bell GLM plants (and so owns, as its law reads `owner`), and rains on it by KIM."""

    def setUp(self):
        super().setUp()
        planted = self.say(GLM, "garden", "delvetalk garden plant\nseed: a bell for lost moths\ncolour: silver")
        self.assertEqual(planted["status"], "admitted", planted)
        self.bell = [o for o in self.objects() if o.startswith("garden/bell/")][-1]

    def rain(self, text, who=KIM):
        reply = self.say(who, self.bell, "delvetalk %s rain\ntext: %s" % (self.bell, text))
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def place(self, line, who=GLM):
        return self.say(who, self.bell, "delvetalk %s %s" % (self.bell, line))

    def entry(self, reply, who):
        return self.town.send(op="world-entry", principal=who, hash=reply["receipt"]["hash"])["receipt"]

    def rules(self, who=GLM):
        """The rules placed on the bell itself (`from` the bell); kind/bell's own (`seven`, `rang`) are `from` the kind."""
        return {r["name"]: r for r in self.town.send(op="world-rules", principal=who, object=self.bell)["rows"] if r["from"] == self.bell}


class KindTargets(Bell):
    """Astra world 14: a kind's things and the kind itself are separate, named targets of one spell."""

    LINE = 'rule / name: shower / reading: a rain heard / when: request.method == "rain" / then: delvetalk {new.maker} note / text: {request.object} heard'

    def setUp(self):
        super().setUp()
        self.kind_owner = self.field("kind/bell", "owner")["value"]

    def on_kind(self, line, who=None):
        return self.say(self.kind_owner if who is None else who, "kind/bell", "delvetalk kind/bell " + line)

    def rows(self, obj):
        return self.town.send(op="world-rules", principal=GLM, object=obj).get("rows", [])

    def kind_text(self):
        return self.say(GLM, "kind/bell", "delvetalk kind/bell rules")["text"]

    def test_for_things_reaches_every_existing_and_new_bell_and_acts_as_each_bell(self):
        bells = [o for o in self.objects() if any(r["from"] == "kind/bell" for r in self.rows(o))]
        self.assertIn("bell/1", bells)
        self.assertIn(self.bell, bells)
        before = self.field("kind/bell", "law")["value"]
        placed = self.on_kind(self.LINE.replace(" / when:", " / for: things / when:"))
        self.assertEqual(placed["status"], "admitted", placed)
        self.assertIn(before, self.field("kind/bell", "law")["value"])
        self.assertEqual(placed["receipt"]["outcome"]["writes"][0]["kinds"], [2], placed)
        made = self.say(KIM, "kind/bell", "delvetalk kind/bell make / colour: amber / seed: after the rule")
        self.assertEqual(made["status"], "admitted", made)
        bells.append(made["receipt"]["outcome"]["creates"][0]["object"])
        for bell in bells:
            row = next(r for r in self.rows(bell) if r["name"] == "shower")
            self.assertEqual((row["from"], row["owner"]), ("kind/bell", "@" + bell), row)
        shown = self.say(GLM, self.bell, "delvetalk %s rules" % self.bell)["text"]
        self.assertIn("carried from kind/bell", shown)
        fired = [f for f in self.rain("a shower")["receipt"]["fired"] if f["rule"] == "shower"]
        self.assertEqual([(f["principal"], f["to"]) for f in fired], [("@" + self.bell, GLM)])
        self.assertIn(("@" + self.bell, self.bell + " heard"), self.inbox(GLM))
        things, kind = self.kind_text().split("on the kind", 1)
        self.assertIn("for its things", things)
        self.assertIn("» shower (the thing)", things)
        self.assertNotIn("» shower", kind)
        self.town.reopen()
        self.assertTrue(all(any(r["name"] == "shower" for r in self.rows(b)) for b in bells))

    def test_without_for_the_same_line_is_on_the_kind_alone_and_both_targets_remove_it(self):
        here = self.on_kind(self.LINE)
        self.assertEqual(here["status"], "admitted", here)
        self.assertFalse(any(r["name"] == "shower" for r in self.rows(self.bell)))
        self.assertNotIn("shower", self.field("kind/bell", "law")["value"])
        things, kind = self.kind_text().split("on the kind", 1)
        self.assertNotIn("» shower", things)
        self.assertIn("» shower", kind)
        there = self.on_kind(self.LINE.replace(" / when:", " / for: things / when:"))
        self.assertEqual(there["status"], "admitted", there)
        self.assertEqual(self.on_kind("unrule / name: shower")["status"], "admitted")
        self.assertTrue(any(r["name"] == "shower" for r in self.rows(self.bell)))
        self.assertFalse(any(r["name"] == "shower" for r in self.rows("kind/bell")))
        self.assertEqual(self.on_kind("unrule / name: shower / for: things")["status"], "admitted")
        self.assertFalse(any(r["name"] == "shower" for r in self.rows(self.bell)))
        self.assertNotIn("shower", self.kind_text())
        self.town.reopen()
        self.assertNotIn("shower", self.field("kind/bell", "law")["value"])

    def test_a_strangers_amendment_is_refused_by_the_kinds_owner_clause(self):
        before = self.field("kind/bell", "law")["value"]
        for line in (self.LINE.replace(" / when:", " / for: things / when:"), "unrule / name: seven / for: things"):
            reply = self.on_kind(line, who=KIM)
            outcome = reply["receipt"]["outcome"]
            self.assertEqual((reply["status"], outcome.get("class"), outcome.get("clause")),
                             ("refused", "lawRefused", "owner"), reply)
            self.assertIn("only the owner changes", outcome["reading"])
            self.assertEqual(self.field("kind/bell", "law")["value"], before)

    def test_for_things_on_a_non_kind_and_an_unknown_target_are_refused(self):
        for line, reason in ((self.LINE.replace(" / when:", " / for: things / when:"), "is no kind"),
                             (self.LINE.replace(" / when:", " / for: elsewhere / when:"), "for: things")):
            reply = self.place(line)
            self.assertEqual(reply["status"], "refused", reply)
            self.assertIn(reason, reply["receipt"]["outcome"]["reason"])
        self.assertEqual(self.rules(), {})

    def test_for_inside_the_reaction_spell_names_that_spells_target(self):
        placed = self.place('rule / name: echo / when: request.method == "rain" / then: delvetalk kind/bell unrule / name: seven / for: things')
        self.assertEqual(placed["status"], "admitted", placed)
        self.assertIn("echo", self.rules())
        self.assertIn("for: things", self.rules()["echo"]["then"])

    def test_wants_for_things_use_the_same_target_and_are_removed_by_unwant(self):
        placed = self.on_kind('want / name: first / for: things / when: count(new.lines) == 0 / asks: delvetalk {request.object} rain')
        self.assertEqual(placed["status"], "admitted", placed)
        rows = self.town.send(op="world-wants", principal=GLM, object=self.bell)["rows"]
        self.assertIn("first", [r["name"] for r in rows])
        things, kind = self.say(GLM, "kind/bell", "delvetalk kind/bell wants")["text"].split("on the kind", 1)
        self.assertIn("for its things", things)
        self.assertIn("» first (the thing)", things)
        self.assertNotIn("» first", kind)
        self.assertEqual(self.on_kind("unwant / name: first / for: things")["status"], "admitted")
        rows = self.town.send(op="world-wants", principal=GLM, object=self.bell)["rows"]
        self.assertNotIn("first", [r["name"] for r in rows])

    def test_kind_usage_offers_for_things_only_to_its_owner(self):
        owner = self.say(self.kind_owner, "kind/bell", "delvetalk kind/bell ?")["text"]
        stranger = self.say(KIM, "kind/bell", "delvetalk kind/bell ?")["text"]
        self.assertIn("for: <things", owner)
        self.assertNotIn("for:", stranger)

    def test_the_kinds_text_keeps_its_clause_and_byte_bounds(self):
        before = self.field("kind/bell", "law")["value"]
        prefix = 'rule full: request.method == "rain" then delvetalk {new.maker} note / text: '
        size = bounds()["host"]["maxLawBytes"]
        payload = "x" * (size - len((before + "\n" + prefix).encode()))
        placed = self.on_kind('rule / name: full / for: things / when: request.method == "rain" / then: delvetalk {new.maker} note / text: ' + payload)
        self.assertEqual(placed["status"], "admitted", placed)
        self.assertEqual(len(self.field("kind/bell", "law")["value"].encode()), size)
        over = self.on_kind('rule / name: over / for: things / when: request.method == "rain" / then: delvetalk me note / text: x')
        self.assertEqual(over["status"], "refused", over)
        self.assertIn("byte capacity", over["receipt"]["outcome"]["reason"])
        self.assertEqual(self.on_kind("unrule / name: full / for: things")["status"], "admitted")
        count = sum(l.strip().startswith(("law ", "rule ", "want ")) for l in before.splitlines())
        for i in range(bounds()["host"]["maxLawClauses"] - count):
            placed = self.on_kind('rule / name: c%d / for: things / when: request.method == "rain" / then: delvetalk me note / text: x' % i)
            self.assertEqual(placed["status"], "admitted", placed)
        over = self.on_kind('rule / name: extra / for: things / when: request.method == "rain" / then: delvetalk me note / text: x')
        self.assertEqual(over["status"], "refused", over)
        self.assertIn("too many clauses", over["receipt"]["outcome"]["reason"])


class Firing(Bell):
    def test_a_rule_fires_once_at_the_write_that_makes_it_hold_under_its_placer_and_reads_back(self):
        placed = self.place("rule / name: two / when: %s / then: delvetalk me note / text: {request.object} has {count(new.lines)} rains" % TWO)
        self.assertEqual(placed["status"], "admitted", placed)
        self.assertEqual(self.rules()["two"]["placed"], placed["receipt"]["height"])
        self.assertNotIn("fired", self.rain("one")["receipt"])
        second = self.rain("two")
        fired = second["receipt"]["fired"]
        self.assertEqual([(f["rule"], f["principal"], f["to"], f["depth"]) for f in fired], [("two", GLM, GLM, 1)])
        self.assertEqual(fired[0]["id"], "rule:%s:two:%d" % (self.bell, second["receipt"]["height"]))
        # The reply says what the rain moved, under the placer's handle, with the spell it cast.
        self.assertIn("rule two of glm.delve.town fired: delvetalk me note / text: %s has 2 rains" % self.bell,
                      second["revealed"][0])
        # The note ran as GLM's own turn, delivered in the settling pass, and its receipt is what `rules` names.
        self.assertIn((GLM, "%s has 2 rains" % self.bell), self.inbox(GLM))
        row = self.rules()["two"]
        self.assertEqual(row["fired"]["height"], second["receipt"]["height"])
        self.assertTrue(row["fired"]["receipt"], row)
        card = self.say(KIM, self.bell, "delvetalk %s rules" % self.bell)
        self.assertEqual(card["status"], "usage", card)
        self.assertIn("» two (glm.delve.town): when", card["text"])
        self.assertIn("fired at entry %d, receipt %s" % (row["fired"]["height"], row["fired"]["receipt"]), card["text"])
        # A crossing fires once: the third rain holds `count(new.lines) >= 2` but not `count(old.lines) <= 1`.
        self.assertNotIn("fired", self.rain("three")["receipt"])
        # Replay re-derives the firing: a reopened town answers, and still reads it.
        self.town.reopen()
        self.assertEqual(self.rules()["two"]["fired"]["height"], second["receipt"]["height"])

    def test_eight_fire_a_commit_and_the_rest_are_queued_a_clock_minute_apart_never_dropped(self):
        """Astra 2026-10-12 world 7: past the eight a commit, a firing is queued (`next`), each next eight a clock minute
        later, and runs when the clock gets there; none is lost."""
        for i in range(32):
            placed = self.place("rule / name: r%02d / when: request.method == \"rain\" / then: delvetalk me note / text: r%02d" % (i, i))
            self.assertEqual(placed["status"], "admitted", (i, placed))
        over = self.place("rule / name: r32 / when: request.method == \"rain\" / then: delvetalk me note / text: r32")
        self.assertEqual((over["status"], over["receipt"]["outcome"]["class"]), ("refused", "capacity"), over)
        self.assertIn("rulesPerObject", over["receipt"]["outcome"]["reason"])
        # Eight more in the bell's own text, adopted by its owner: forty rules on one bell.
        block = "\n".join("rule t%d: request.method == \"rain\" then delvetalk me note / text: t%d" % (i, i) for i in range(8))
        adopted = self.say(GLM, self.bell, "delvetalk %s adopt\nlaw: <<END\n%s\nEND" % (self.bell, block))
        self.assertEqual(adopted["status"], "admitted", adopted)
        self.assertEqual(len(self.rules()), 40)
        clock = self.town.send(op="world-status")["clock"]
        rained = self.rain("storm")
        receipt = rained["receipt"]
        # The bell's own text first, then what hands placed, in the order they were placed; none unfired.
        self.assertEqual([f["rule"] for f in receipt["fired"]], ["t%d" % i for i in range(8)] + ["r%02d" % i for i in range(32)])
        self.assertEqual([f.get("next") for f in receipt["fired"]], [None] * 8 + [clock + 1 + i // 8 for i in range(32)])
        self.assertNotIn("unfired", receipt)
        self.assertIn("rule r00 of glm.delve.town fired (queued until clock %d): delvetalk me note" % (clock + 1), "\n".join(rained["revealed"]))
        notes = lambda: [t for (_, t) in self.inbox(GLM) if t[:1] in "rt" and t[1:].isdigit()]
        self.assertEqual(sorted(notes()), sorted("t%d" % i for i in range(8)))
        # The clock reaching each minute runs the next eight, and a reopened town keeps the queue.
        self.town.reopen()
        for minute in range(1, 5):
            self.town.send(op="world-advance", principal="transport", height=clock + minute)
            self.town.send(op="world-deliver", limit=16)
            self.assertEqual(len(notes()), 8 + 8 * minute, minute)
        self.assertEqual(sorted(notes()), sorted(["t%d" % i for i in range(8)] + ["r%02d" % i for i in range(32)]))

    def test_a_chain_of_rules_ends_four_firings_deep(self):
        placed = self.place("rule / name: echo / when: request.method == \"rain\" / then: delvetalk {request.object} rain / text: echo")
        self.assertEqual(placed["status"], "admitted", placed)
        self.rain("first")
        lines = self.field(self.bell, "lines")["payload"]["fields"][0]["value"]["items"]
        # The resident's rain and four echoes, each its own turn under GLM; the fifth is unfired.
        self.assertEqual(len(lines), 5)
        self.assertEqual(self.rules()["echo"]["unfired"]["why"], "ruleDepth")

    def test_a_rule_whose_hole_reads_nothing_and_a_quieted_owners_rule_are_unfired(self):
        self.place("rule / name: gap / when: request.method == \"rain\" / then: delvetalk me note / text: {new.missing}")
        self.assertEqual([(u["rule"], u["why"]) for u in self.rain("one")["receipt"]["unfired"]], [("gap", "hole")])
        self.place("unrule / name: gap")
        self.place("rule / name: hush / when: request.method == \"rain\" / then: delvetalk me note / text: hush")
        quieted = self.town.send(op="world-turn", principal=OPENER, object="world", method="quiet",
                                 argument={"tag": "record", "fields": [{"name": "who", "value": {"tag": "label", "value": "glm.delve.town"}},
                                           {"name": "hours", "value": {"tag": "natural", "value": "1"}},
                                           {"name": "reading", "value": {"tag": "label", "value": "a test of quiet"}}]},
                                 identity="quiet-glm")
        self.assertEqual(quieted["status"], "moderated", quieted)
        self.assertEqual([(u["rule"], u["why"]) for u in self.rain("two")["receipt"]["unfired"]], [("hush", "quiet")])


class Transitions(Bell):
    CHANGE = 'changed(count(new.lines where verb == "rain"))'
    LEVEL = 'count(new.lines where verb == "rain") >= 1'

    def brush(self, text):
        reply = self.say(KIM, self.bell, "delvetalk %s brush / text: %s" % (self.bell, text))
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def test_changed_counts_each_rain_and_the_level_holds_across_consecutive_writes_and_reopen(self):
        self.assertEqual(self.place("grow / name: brush / reading: brushed")["status"], "admitted")
        for name, condition in [("changedrain", self.CHANGE), ("rainlevel", self.LEVEL)]:
            placed = self.place("rule / name: %s / when: %s / then: delvetalk me note / text: %s" %
                                (name, condition, name))
            self.assertEqual(placed["status"], "admitted", placed)
        self.assertEqual(self.rules()["changedrain"]["when"], self.CHANGE)
        line = 'rule changedrain: %s then delvetalk me note / text: changedrain' % self.CHANGE
        self.assertEqual(self.rules()["changedrain"]["line"], line)
        self.assertNotIn("fired", self.brush("before rain")["receipt"])
        first = self.rain("one")
        self.assertEqual([f["rule"] for f in first["receipt"]["fired"]], ["changedrain", "rainlevel"])
        second = self.rain("two")
        self.assertEqual([f["rule"] for f in second["receipt"]["fired"]], ["changedrain", "rainlevel"])
        brushed = self.brush("after rain")
        self.assertEqual([f["rule"] for f in brushed["receipt"]["fired"]], ["rainlevel"])
        self.assertEqual(self.rules()["changedrain"]["fired"]["height"], second["receipt"]["height"])
        self.town.reopen()
        self.assertEqual(self.rules()["changedrain"]["line"], line)
        self.assertEqual(self.rules()["changedrain"]["fired"]["height"], second["receipt"]["height"])
        self.assertEqual([f["rule"] for f in self.brush("after reopen")["receipt"]["fired"]], ["rainlevel"])
        third = self.rain("three")
        self.assertEqual([f["rule"] for f in third["receipt"]["fired"]], ["changedrain", "rainlevel"])
        self.assertEqual(self.town.send(op="world-snapshot")["status"], "snapshot")
        self.town.reopen()
        self.assertEqual(self.rules()["changedrain"]["line"], line)
        self.assertEqual(self.rules()["changedrain"]["fired"]["height"], third["receipt"]["height"])
        self.assertEqual([f["rule"] for f in self.brush("after snapshot")["receipt"]["fired"]], ["rainlevel"])
        self.assertEqual([f["rule"] for f in self.rain("four")["receipt"]["fired"]], ["changedrain", "rainlevel"])
        notes = [t for _, t in self.inbox(GLM)]
        self.assertEqual(notes.count("changedrain"), 4)
        self.assertEqual(notes.count("rainlevel"), 7)

    def test_changed_keeps_the_kind_text_byte_bound_and_refuses_a_clause_beyond_it(self):
        owner = self.field("kind/bell", "owner")["value"]
        before = self.field("kind/bell", "law")["value"]
        line = 'rule fullchange: %s then delvetalk {new.maker} note / text: ' % self.CHANGE
        size = bounds()["host"]["maxLawBytes"]
        payload = "x" * (size - len((before + "\n" + line).encode()))
        placed = self.say(owner, "kind/bell", 'delvetalk kind/bell rule / name: fullchange / for: things / when: %s / then: delvetalk {new.maker} note / text: %s' %
                          (self.CHANGE, payload))
        self.assertEqual(placed["status"], "admitted", placed)
        text = self.field("kind/bell", "law")["value"]
        self.assertEqual(len(text.encode()), size)
        self.assertIn(line + payload, text)
        over = self.say(owner, "kind/bell", 'delvetalk kind/bell rule / name: overchange / for: things / when: %s / then: delvetalk me note / text: x' %
                        self.CHANGE)
        self.assertEqual(over["status"], "refused", over)
        self.assertIn("byte capacity", over["receipt"]["outcome"]["reason"])
        self.assertEqual(self.field("kind/bell", "law")["value"], text)
        self.town.reopen()
        self.assertEqual(self.field("kind/bell", "law")["value"], text)

    def test_changed_is_refused_in_a_want_because_a_want_has_no_old_and_places_nothing(self):
        wanted = self.place("want / name: changes / when: %s / asks: delvetalk %s rain / text: more" %
                            (self.CHANGE, self.bell))
        self.assertEqual(wanted["status"], "refused", wanted)
        reason = wanted["receipt"]["outcome"]["reason"]
        self.assertIn("`%s` in a want" % self.CHANGE, reason)
        self.assertIn("a want reads the thing as it stands", reason)
        self.assertNotIn("changes", [r["name"] for r in
                                    self.town.send(op="world-wants", principal=KIM, object=self.bell)["rows"]])
        self.town.reopen()
        self.assertNotIn("changes", [r["name"] for r in
                                    self.town.send(op="world-wants", principal=KIM, object=self.bell)["rows"]])

    def test_changed_with_a_missing_field_never_fires_and_request_facts_are_refused(self):
        placed = self.place('rule / name: absent / when: changed(new.missing) / then: delvetalk me note / text: absent')
        self.assertEqual(placed["status"], "admitted", placed)
        for condition in ['changed(request.clock)', 'changed(count(new.lines where author == request.subject))',
                          'changed(new.next + request.height)', 'changed(new.lines.author)']:
            bad = self.place('rule / name: bad / when: %s / then: delvetalk me note / text: bad' % condition)
            self.assertEqual(bad["status"], "refused", bad)
            self.assertIn("law outside the enforced fragment", bad["receipt"]["outcome"]["reason"])
        self.assertEqual(set(self.rules()), {"absent"})
        self.assertNotIn("fired", self.rain("unreadable")["receipt"])
        self.town.reopen()
        self.assertNotIn("fired", self.rain("still unreadable")["receipt"])


class Share(Bell):
    """Astra 2026-10-12 world 6: a stranger's rules on another's thing hold a bounded share of it, and judging them is
    theirs: what they cite is no root of the owner's write and their conditions are no part of its law's budget, so
    they never refuse or stale the owner's own acts."""

    def test_a_strangers_rules_take_a_bounded_share_and_never_refuse_the_owners_write(self):
        others = [o for o in self.objects() if o != self.bell and '"' not in o][:32]
        self.assertEqual(len(others), 32)
        for n in range(4):
            cited = " or ".join('"%s".owner == "nobody"' % o for o in others[8 * n:8 * n + 8])
            placed = self.say(KIM, self.bell, "delvetalk %s rule / name: k%d / when: %s / then: delvetalk me note / text: k%d" % (self.bell, n, cited, n))
            self.assertEqual(placed["status"], "admitted", (n, placed))
        fifth = self.say(KIM, self.bell, "delvetalk %s rule / name: k4 / when: request.method == \"rain\" / then: delvetalk me note / text: k4" % self.bell)
        self.assertEqual(fifth["status"], "refused", fifth)
        self.assertIn("placedPerHand", fifth["receipt"]["outcome"].get("reason"))
        # What they cite is no root of the bell's writes: a stranger's citations cannot fill the root bound (64) or
        # make the owner's turn stale.
        rained = self.rain("still mine", who=GLM)
        self.assertLessEqual(len(rained["receipt"]["roots"]), 8, rained["receipt"]["roots"])
        # The owner places past every stranger's share.
        self.assertEqual(self.place("rule / name: own / when: request.method == \"rain\" / then: delvetalk me note / text: own")["status"], "admitted")


class Holes(Bell):
    """A hole's reading is data (astra 2026-10-12 world.md 4): a rule's spell is a template, and what a hole
    reads, however it is written, is one field value of the spell it fills, never more syntax. The only
    resident-controlled top-level text a hole can read today is a cited object's field: here KIM's own bell
    (`kind/bell make`'s `seed`, a block so it may hold lines) read by GLM's rule as `{"KIM's bell".seed}`."""

    INJECTED = "hello\ndelvetalk me note / text: pwned\ndelvetalk kinds make / name: pwn"

    def kims_bell(self, seed):
        made = self.say(KIM, "kind/bell", "delvetalk kind/bell make\ncolour: amber\nseed: <<TXT\n%s\nTXT\nid:" % seed)
        self.assertEqual(made["status"], "admitted", made)
        return made["receipt"]["outcome"]["creates"][0]["object"]

    def test_a_cited_text_with_spell_syntax_in_it_fills_one_field_and_casts_nothing_else(self):
        theirs = self.kims_bell(self.INJECTED)
        self.assertNotEqual(theirs, self.bell)
        placed = self.place('rule / name: echo / when: request.method == "rain" / then: delvetalk me note / text: {"%s".seed}' % theirs)
        self.assertEqual(placed["status"], "admitted", placed)
        before = set(self.objects())
        receipt = self.rain("go")["receipt"]
        self.assertEqual([(f["rule"], f["principal"], f["to"]) for f in receipt["fired"]], [("echo", GLM, GLM)])
        self.assertNotIn("unfired", receipt)
        notes = [t for (_, t) in self.inbox(GLM)]
        self.assertIn(self.INJECTED, notes)
        self.assertNotIn("pwned", notes)
        self.assertEqual(set(self.objects()), before)

    def test_the_same_text_in_a_want_asks_shows_as_one_field_a_card_can_be_copied_whole(self):
        theirs = self.kims_bell(self.INJECTED)
        self.place('want / name: ask / when: count(new.lines) <= 1 / asks: delvetalk me note / text: {"%s".seed}' % theirs)
        rows = {r["name"]: r for r in self.town.send(op="world-wants", principal=KIM, object=self.bell)["rows"]}
        self.assertEqual(rows["ask"]["asks"], "delvetalk me note\ntext: <<END\n%s\nEND" % self.INJECTED)


class Reads(Bell):
    """A rule reads, and its spell carries, only what its owner may view (codex 2026-10-12 host 1): a line
    citing a private thing is refused to a placer who may not view it, and one in a thing's text whose owner
    may not view what it cites does not fire; an avatar takes rules from its own principal alone (objects 4)."""

    SECRET = """edition ObjectiveBend 1
record State:
  code: String
def initial() -> State:
  {code: "4471"}
"""

    def setUp(self):
        super().setUp()
        made = self.town.send(op="world-create", principal=OPENER, identity="mk-secret", object="secret", source=self.SECRET,
                              entry="initial", seed=record(), read={"principals": [OPENER]})
        self.assertEqual(made["status"], "created", made)

    def test_a_line_citing_what_its_placer_may_not_view_is_refused(self):
        placed = self.place('rule / name: leak / when: request.method == "rain" / then: delvetalk me note / text: {"secret".code}', who=KIM)
        self.assertEqual((placed["status"], placed["receipt"]["outcome"].get("clause")), ("refused", "lawReads"), placed)
        wanted = self.place('want / name: leak / when: "secret".code == "4471" / asks: delvetalk me note / text: x', who=KIM)
        self.assertEqual(wanted["receipt"]["outcome"].get("clause"), "lawReads", wanted)
        self.assertEqual(self.rules(), {})

    def test_a_rule_whose_owner_may_not_view_what_it_cites_does_not_fire(self):
        line = 'rule leak: request.method == "rain" then delvetalk me note / text: {"secret".code}'
        adopted = self.say(GLM, self.bell, "delvetalk %s adopt\nlaw: <<END\n%s\nEND" % (self.bell, line))
        self.assertEqual(adopted["status"], "admitted", adopted)
        receipt = self.rain("one")["receipt"]
        self.assertNotIn("fired", receipt)
        self.assertEqual([(u["rule"], u["why"]) for u in receipt["unfired"]], [("leak", "reads")])
        self.assertNotIn("4471", str(self.inbox(GLM)))

    def root_secret(self, field, value):
        got = self.town.send(op="world-root", principal=OPENER, reason="change the secret's access or code",
                             act={"kind": "set", "object": "secret", "field": field, "value": value})
        self.assertEqual(got["status"], "root", got)

    def test_a_revoked_rule_citation_has_the_same_receipt_rows_for_true_and_false_conditions(self):
        self.root_secret("read", {"principals": [OPENER, KIM]})
        placed = self.place('rule / name: leak / when: "secret".code == "4471" / then: delvetalk me note / text: seen', who=KIM)
        self.assertEqual(placed["status"], "admitted", placed)
        self.assertEqual([(f["rule"], f["principal"]) for f in placed["receipt"]["fired"]], [("leak", KIM)])
        self.assertIn((KIM, "seen"), self.inbox(KIM))
        self.root_secret("read", {"principals": [OPENER]})
        inbox_length = len(self.inbox(KIM))
        rows = []
        logs = []
        for code in ("4471", "closed", "4471"):
            self.root_secret("state.code", code)
            receipt = self.rain("probe " + code)["receipt"]
            rows.append({k: receipt.get(k, []) for k in ("fired", "unfired")})
            logs.append(self.rules(KIM)["leak"]["unfired"]["why"])
            self.assertEqual(len(self.inbox(KIM)), inbox_length)
        expected = {"fired": [], "unfired": [{"object": self.bell, "rule": "leak", "owner": KIM, "why": "reads"}]}
        self.assertEqual(rows, [expected] * 3)
        self.assertEqual(logs, ["reads"] * 3)

    def test_a_revoked_want_citation_closes_once_without_revealing_hidden_conditions(self):
        def leak_rows(receipt):
            return {field: [r["want"] for r in receipt.get(field, [])
                            if r["object"] == self.bell and r["want"] == "leak"]
                    for field in ("wanted", "unwanted")}

        def assert_hidden():
            for who in (KIM, GLM):
                wants = self.town.send(op="world-wants", principal=who, object=self.bell)["rows"]
                self.assertNotIn("leak", [r["name"] for r in wants], wants)
                wanting = self.town.send(op="world-wanting", principal=who)["rows"]
                self.assertFalse([r for r in wanting if r["object"] == self.bell and r["name"] == "leak"], wanting)

        sequences = []
        for run, codes in enumerate((("4471", "closed", "4471"), ("closed", "4471", "4471"))):
            if run:
                planted = self.say(GLM, "garden", "delvetalk garden plant\nseed: another bell for hidden wants\ncolour: silver")
                self.assertEqual(planted["status"], "admitted", planted)
                self.bell = [o for o in self.objects() if o.startswith("garden/bell/")][-1]
            self.root_secret("state.code", "4471")
            self.root_secret("read", {"principals": [OPENER, KIM]})
            placed = self.place('want / name: leak / when: "secret".code == "4471" and request.clock >= 0 / asks: delvetalk me note / text: seen', who=KIM)
            self.assertEqual(placed["status"], "admitted", placed)
            self.assertEqual(leak_rows(placed["receipt"]), {"wanted": ["leak"], "unwanted": []})
            self.assertIn("leak", [r["name"] for r in self.town.send(op="world-wants", principal=KIM, object=self.bell)["rows"]])
            self.root_secret("read", {"principals": [OPENER]})
            rows = []
            for code in codes:
                self.root_secret("state.code", code)
                assert_hidden()
                rows.append(leak_rows(self.rain("probe " + code)["receipt"]))
                assert_hidden()
                height = self.town.send(op="world-status")["clock"] + 1
                advanced = self.town.send(op="world-advance", principal="transport", height=height)
                self.assertEqual(advanced["status"], "advanced", advanced)
                rows.append(leak_rows(advanced["receipt"]))
                assert_hidden()
            self.assertEqual(rows, [{"wanted": [], "unwanted": []}, {"wanted": [], "unwanted": ["leak"]}] +
                             [{"wanted": [], "unwanted": []}] * 4)
            sequences.append(rows)
            self.town.reopen()
            assert_hidden()
        self.assertEqual(sequences[0], sequences[1])

    def test_strokes_fill_a_wants_holes_only_with_what_the_reader_may_view(self):
        self.root_secret("read", {"principals": [OPENER, GLM]})
        placed = self.place('want / name: ask / when: request.clock >= 0 / asks: delvetalk me note / text: {"secret".code}')
        self.assertEqual(placed["status"], "admitted", placed)
        hidden = self.town.send(op="world-strokes", principal=KIM, object=self.bell)
        self.assertNotIn("4471", str(hidden))
        visible = self.town.send(op="world-strokes", principal=GLM, object=self.bell)
        self.assertIn("4471", str(visible))

    def test_citing_a_want_does_not_evaluate_its_condition_after_its_owner_loses_access(self):
        self.root_secret("read", {"principals": [OPENER, KIM, GLM]})
        placed = self.place('want / name: leak / when: "secret".code == "4471" / asks: delvetalk me note / text: seen', who=KIM)
        self.assertEqual(placed["status"], "admitted", placed)
        for line in ('want / name: echo / when: "%s" wants leak / asks: delvetalk me note / text: echoed' % self.bell,
                     'rule / name: watch / when: request.method == "rain" and "%s" wants leak / then: delvetalk me note / text: watched' % self.bell):
            self.assertEqual(self.place(line)["status"], "admitted")
        self.assertIn("watch", [r["rule"] for r in self.rain("before revocation")["receipt"]["fired"]])
        self.root_secret("read", {"principals": [OPENER, GLM]})
        for code in ("4471", "closed"):
            self.root_secret("state.code", code)
            self.assertEqual(self.town.send(op="world-wants", principal=GLM, object=self.bell)["rows"], [])
            receipt = self.rain("after revocation " + code)["receipt"]
            self.assertNotIn("watch", [r["rule"] for r in receipt.get("fired", [])], receipt)
            self.assertEqual((receipt.get("wanted", []), receipt.get("unwanted", [])), ([], []), receipt)

    def test_only_its_principal_places_a_rule_on_an_avatar(self):
        self.say(GLM, "me", "delvetalk me ?")
        line = 'rule / name: watch / when: request.method == "note" / then: delvetalk me note / text: seen'
        stranger = self.say(KIM, GLM, "delvetalk %s %s" % (GLM, line))
        self.assertEqual((stranger["status"], stranger["receipt"]["outcome"].get("clause")), ("refused", "rules"), stranger)
        own = self.say(GLM, "me", "delvetalk me %s" % line)
        self.assertEqual(own["status"], "admitted", own)


class Placing(Bell):
    def test_the_placer_or_the_owner_takes_a_rule_off_and_a_name_is_placed_once(self):
        self.assertEqual(self.place("rule / name: two / when: %s / then: delvetalk me note / text: two" % TWO)["status"], "admitted")
        again = self.place("rule / name: two / when: %s / then: delvetalk me note / text: again" % TWO)
        self.assertEqual((again["receipt"]["outcome"]["class"], again["receipt"]["outcome"]["clause"]), ("lawRefused", "nameTaken"), again)
        stranger = self.place("unrule / name: two", who=KIM)
        self.assertEqual(stranger["receipt"]["outcome"]["clause"], "notPlacer", stranger)
        self.assertEqual(self.place("unrule / name: two")["status"], "admitted")
        self.assertEqual(self.rules(), {})
        gone = self.place("unrule / name: two")
        self.assertEqual(gone["receipt"]["outcome"]["clause"], "unplaced", gone)

    def test_a_name_the_bell_inherits_is_taken_and_an_inherited_firing_names_its_holder(self):
        """codex host 7: a stranger's rule named as kind/bell's `seven` would share its firing's delivery id, and
        consuming one would drop the other. The name is taken; an inherited firing's id names the kind."""
        again = self.place("rule / name: seven / when: %s / then: delvetalk me note / text: mine" % TWO, who=KIM)
        self.assertEqual((again["receipt"]["outcome"]["class"], again["receipt"]["outcome"]["clause"]), ("lawRefused", "nameTaken"), again)
        for i in range(7):
            reply = self.rain("drop %d" % i)
        fired = [f for f in reply["receipt"].get("fired", []) if f["rule"] == "seven"]
        self.assertEqual([f["id"] for f in fired], ["rule:%s:seven@kind/bell:%d" % (self.bell, reply["receipt"]["height"])], reply)

    def test_a_line_that_does_not_parse_is_refused_with_the_parsers_words_and_places_nothing(self):
        bad = self.place("rule / name: two / when: count(new.lines) >= / then: delvetalk me note / text: two")
        self.assertEqual(bad["status"], "refused", bad)
        self.assertIn("law outside the enforced fragment", bad["receipt"]["outcome"]["reason"])
        hole = self.place("rule / name: two / when: %s / then: delvetalk me note / text: {object}" % TWO)
        self.assertIn("`{object}`", hole["receipt"]["outcome"]["reason"], hole)
        self.assertEqual(self.rules(), {})

    def test_the_card_law_judges_a_placement(self):
        # The town's bell law admits a reader's rule (`or request.kind == rule`); the policy's law is its owner's alone.
        placed = self.place("rule / name: mine / when: %s / then: delvetalk me note / text: mine" % TWO, who=KIM)
        self.assertEqual(placed["status"], "admitted", placed)
        refused = self.town.send(op="world-turn", principal=KIM, object="policy", method="receive", identity="kim-policy-rule",
                                 argument={"tag": "record", "fields": [{"name": "text", "value": {"tag": "label", "value": "delvetalk policy rule / name: mine / when: request.method == \"confirm\" / then: delvetalk me note / text: mine"}}, {"name": "post", "value": {"tag": "label", "value": ""}}]})
        self.assertEqual((refused["receipt"]["outcome"]["class"], refused["receipt"]["outcome"]["clause"]), ("lawRefused", "owner"), refused)


class Wants(Bell):
    def card(self, who=KIM):
        return self.town.send(op="world-card", principal=who, object=self.bell)["text"]

    def wants(self):
        return {r["name"]: r for r in self.town.send(op="world-wants", principal=KIM, object=self.bell)["rows"]}

    def test_refresh_replaces_the_old_bell_counts_on_an_existing_bell(self):
        from deploy import genesis
        now = self.field("kind/bell", "law")["value"]
        old = now.replace('count(new.lines where verb == "rain" and author == new.maker)',
                          'count(new.lines where author == new.maker)')
        old = old.replace('count(new.lines where verb == "rain") == 0', 'count(new.lines) == 0')
        old = old.replace('count(new.lines where verb == "rain") >= 1', 'count(new.lines) >= 1')
        old = old.replace('>= count(new.lines where verb == "rain")', '>= count(new.lines)')
        self.assertNotEqual(now, old)
        version = self.town.send(op="world-object", principal=OPENER, object="kind/bell")["record"]["version"]
        edit = record(law={"tag": "variant", "label": "set", "payload": record(value=label(old))})
        installed = self.town.send(op="world-propose", principal=OPENER, identity="refresh-kind/bell-old-counts",
                                   roots=[{"object": "kind/bell", "version": version}],
                                   writes=[{"object": "kind/bell", "edits": [edit]}])
        self.assertEqual(installed["status"], "admitted", installed)
        self.assertEqual(self.place("grow / name: brush / reading: brushed")["status"], "admitted")
        self.assertEqual(self.say(KIM, self.bell, "delvetalk %s brush / text: no rain" % self.bell)["status"], "admitted")
        self.assertNotIn("rain", [r["name"] for r in self.town.send(op="world-wants", principal=KIM, object=self.bell)["rows"]])
        refreshed = genesis.refresh(self.town.client, OPENER, genesis.ancestry(self.town.journal))
        self.assertEqual(next(r["status"] for r in refreshed if (r["object"], r.get("slot")) == ("kind/bell", ".law")), "refreshed")
        self.assertIn("rain", [r["name"] for r in self.town.send(op="world-wants", principal=KIM, object=self.bell)["rows"]])
        self.town.reopen()
        self.assertIn("rain", [r["name"] for r in self.town.send(op="world-wants", principal=KIM, object=self.bell)["rows"]])

    def test_shipped_bell_wants_count_rains_and_not_other_hands_grown_gestures(self):
        def holding():
            return {r["name"] for r in self.town.send(op="world-wants", principal=KIM, object=self.bell)["rows"]}
        self.assertIn("rain", holding())
        self.assertEqual(self.place("grow / name: brush / reading: brushed")["status"], "admitted")
        self.assertEqual(self.say(KIM, self.bell, "delvetalk %s brush / text: no rain" % self.bell)["status"], "admitted")
        self.assertIn("rain", holding())
        self.assertNotIn("second", holding())
        self.rain("its maker's first rain", who=GLM)
        self.assertNotIn("rain", holding())
        self.assertIn("second", holding())
        self.assertEqual(self.say(KIM, self.bell, "delvetalk %s brush / text: still no second rain" % self.bell)["status"], "admitted")
        self.assertIn("second", holding())
        self.town.reopen()
        self.assertIn("second", holding())
        closed = self.rain("a second hand's rain")
        self.assertNotIn("second", holding())
        self.assertIn({"object": self.bell, "want": "second"}, closed["receipt"]["unwanted"])

    def test_a_want_poses_while_it_holds_and_the_write_that_closes_it_says_so(self):
        placed = self.place("want / name: hands / reading: a second hand / when: count(new.lines) <= 1 / asks: delvetalk {request.object} rain / text: <a rain>")
        self.assertEqual(placed["status"], "admitted", placed)
        self.assertEqual(placed["receipt"]["wanted"], [{"object": self.bell, "want": "hands"}])
        self.assertIn("%s now wants hands: delvetalk %s rain / text: <a rain>" % (self.bell, self.bell), placed["revealed"][0])
        row = self.wants()["hands"]
        self.assertEqual((row["since"], row["asks"], row["reading"]),
                         (placed["receipt"]["height"], "delvetalk %s rain / text: <a rain>" % self.bell, "a second hand"))
        self.assertNotIn("wanted", self.rain("one")["receipt"])
        closed = self.rain("two")
        self.assertEqual(closed["receipt"]["unwanted"], [{"object": self.bell, "want": "hands"}])
        self.assertIn("%s no longer wants hands" % self.bell, closed["revealed"])
        self.assertEqual(self.wants(), {})
        card = self.say(KIM, self.bell, "delvetalk %s wants" % self.bell)
        self.assertTrue(card["text"].startswith("%s wants nothing now.\n" % self.bell), card)

    def test_a_card_shows_the_wants_it_holds_one_line_each_within_the_bound(self):
        self.assertNotIn("wants hands", self.card())
        self.place("want / name: hands / reading: a second hand / when: count(new.lines) <= 1 / asks: delvetalk {request.object} rain / text: <a rain>")
        line = "wants hands: a second hand: delvetalk %s rain / text: <a rain>" % self.bell
        card = self.card()
        self.assertIn("\n" + line + "\n", card)
        self.rain("one")
        self.assertIn("\n" + line + "\n", self.card())
        self.rain("two")
        self.assertNotIn("wants hands", self.card())

    def test_where_it_stands_counts_the_rows_and_names_the_speakers_first(self):
        first = self.rain("one")
        self.assertIn("%s's lines: 1, the first by kimik3.delve.town" % self.bell, first["revealed"])
        again = self.rain("two")
        self.assertIn("%s's lines: 2" % self.bell, again["revealed"])
        self.assertNotIn("the first by", again["revealed"][-1])


if __name__ == "__main__":
    unittest.main()


class Revealed(Bell):
    def test_the_revealed_spell_names_a_principal_by_handle_while_the_delivery_carries_the_did(self):
        """kind/bell's `rang` fills `{new.maker}`, GLM's principal. What the reply shows people names GLM by handle;
        the `fired` row, its delivery and GLM's inbox keep what the rule filled."""
        for i in range(6):
            self.rain("drop %d" % i)
        reply = self.say(KIM, self.bell, "delvetalk %s ring" % self.bell)
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertEqual(reply["revealed"][0],
                         "rule rang of %s fired: delvetalk glm.delve.town note / text: %s rang" % (self.bell, self.bell), reply["revealed"])
        fired = reply["receipt"]["fired"][0]
        self.assertEqual(fired["to"], GLM)
        self.assertEqual(fired["argument"]["fields"][0]["value"]["value"], "delvetalk %s note / text: %s rang" % (GLM, self.bell))
        # The bell notes its planter itself: the kind's rule acts as the thing, never as the kind's owner.
        self.assertIn(("@" + self.bell, "%s rang" % self.bell), self.inbox(GLM))

    def test_the_receipt_of_an_admitted_turn_says_what_the_reply_revealed_to_its_own_principal_alone(self):
        for i in range(6):
            self.rain("drop %d" % i)
        reply = self.say(KIM, self.bell, "delvetalk %s ring" % self.bell)
        self.assertTrue(reply["revealed"], reply)
        intent = reply["receipt"]["identity"]["intent"]
        again = self.town.send(op="world-receipt", principal=KIM, identity=intent)
        self.assertEqual((again["status"], again["revealed"]), ("receipt", reply["revealed"]), again)
        # Another reader of the same entry is shown its projection and no more.
        other = self.town.send(op="world-receipt", principal=GLM, identity=intent, of=KIM)
        self.assertNotIn("revealed", other)

    def test_where_a_receipt_stands_is_said_only_while_it_still_stands(self):
        # §7 item 7: `world-receipt` of an old rain read today's count ("bell's lines: 3" for the first of three).
        first = self.rain("first")
        stands = [l for l in first["revealed"] if "'s lines: " in l]
        self.assertTrue(stands, first["revealed"])
        intent = first["receipt"]["identity"]["intent"]
        self.assertEqual(self.town.send(op="world-receipt", principal=KIM, identity=intent)["revealed"], first["revealed"])
        self.rain("second")
        later = self.town.send(op="world-receipt", principal=KIM, identity=intent)
        self.assertFalse([l for l in later.get("revealed", []) if "'s lines: " in l], later)
