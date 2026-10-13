"""What wants a hand across the world (docs/OVERHAUL.md §5; HOST-HANDOFF 5.164, 5.165): `world.wanting {after,
limit}` and `world-wanting` read the wanting index `record` derives (`World.wanting`): each want that holds of its
thing as it stands, answerable by its reader; blocked wants are counted. Newest-first pages hold whole heights;
oldest-first discovery rotates daily and pages by offset. A want reads what
its thing stands at: `request.laws` (its law clauses, own and followed) and `request.refusedBy` (the writes its law
refused), and a law's refusal journals the wants it opens.

Evidence for the minimal genesis's "what wants a hand" and a seal's "a law and a second hand's try" (layer: host;
the Bend arm needs the pair's World.obend). Refuted by a want listed that no longer holds, a thing listed to a
reader who may not answer it, a newest-first page that splits a height, a discovery page past its bound, a
rotation that starves a held answerable want or loses a row across
`after`, a refusal that opens a want without saying so or that replay derives otherwise, or a read that writes or
answers otherwise after a reopen.
"""
import unittest
import os

from transport.journal import copy as copy_journal, entries as journal_entries, links

from tests.test_reflection import Reflection
from tests.test_verbs import STONE, THING
from tests.wire import cbor, cid_of, label, nat, record, write_journal
from tests.host import bounds
from tests.test_scenarios import Arc, GLM, KIM
from tests.test_properties import OPENER
from tests.bend import declared

ASK = "delvetalk {request.object} rain / text: again"

LIST = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def wants(state: State, input: {after: Nat, limit: Nat}, context: Abi.Context) -> Activity<String>:
  match world.wanting({after: input.after, limit: input.limit, oldest: false}):
    case wanting(w): "{rows(w.rows)}; waiting {natText(w.waiting)}; next {natText(w.next)}"
    case refused(r): "refused {r.clause}"
def rows(items: Lists.List<World.Want>) -> String:
  textJoin(Lists.map(items, fn(i: World.Want) -> String: "{i.object} {i.name} @{natText(i.since)}: {i.asks}"), "; ")
""", "wants")


class Things(Reflection):
    """Two bells and a stone only ember may view."""

    def setUp(self):
        super().setUp()
        self.open_library()
        for name in ("bell", "bell2"):
            self.make(name, THING, record(owner=label("ember")))
        self.make("stone", STONE, record(owner=label("ember")), read={"principals": ["ember"]})

    def say(self, card, text, who="glm"):
        r = self.turn(card, "receive", record(text=label(text), post=label("")), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r["receipt"]

    def want(self, card, name, when, who="glm"):
        return self.say(card, "delvetalk %s want\nname: %s\nwhen: %s\nasks: %s" % (card, name, when, ASK), who=who)

    def wanting(self, who="glm", **page):
        r = self.host.send(op="world-wanting", principal=who, **page)
        self.assertEqual(r["status"], "wanting", r)
        return [(x["object"], x["name"], x["since"]) for x in r["rows"]], r["more"]


class Wanting(Things):
    def test_the_index_newest_or_oldest_first_by_whole_heights_for_whom_may_view(self):
        # Two wants that one rain makes true at once, a want true where it is placed, one on a private stone.
        self.want("bell", "wet", "new.rains >= 1")
        self.want("bell", "damp", "new.rains >= 1")
        dry = self.want("bell2", "dry", "new.rains <= 0")["height"]
        hidden = self.want("stone", "dry", "new.rains <= 0", who="ember")["height"]
        rained = self.say("bell", "delvetalk bell rain\ntext: one", who="kimi")["height"]
        self.assertEqual(self.wanting(), ([("bell", "damp", rained), ("bell", "wet", rained), ("bell2", "dry", dry)], False))
        self.assertEqual(self.wanting(who="ember")[0], [("bell", "damp", rained), ("bell", "wet", rained),
                                                        ("stone", "dry", hidden), ("bell2", "dry", dry)])
        # A page of one row still holds its height whole; `after` its last `since` reads on without a gap.
        self.assertEqual(self.wanting(limit=1), ([("bell", "damp", rained), ("bell", "wet", rained)], True))
        self.assertEqual(self.wanting(after=rained, limit=1), ([("bell2", "dry", dry)], False))
        row = self.host.send(op="world-wanting", principal="glm", after=rained)["rows"][0]
        self.assertEqual(row["asks"], "delvetalk bell2 rain / text: again")
        # At clock day zero the rotation starts at the oldest; its cursor is a row offset, even within a height.
        self.assertEqual(self.wanting(oldest=True), ([("bell2", "dry", dry), ("bell", "damp", rained), ("bell", "wet", rained)], False))
        self.assertEqual(self.wanting(oldest=True, limit=1), ([("bell2", "dry", dry)], True))
        self.assertEqual(self.wanting(oldest=True, after=1, limit=1), ([("bell", "damp", rained)], True))
        # A want that stops holding leaves; reading writes nothing; a reopen and a snapshot answer the same.
        self.say("bell2", "delvetalk bell2 rain\ntext: one", who="kimi")
        height = self.host.send(op="world-status")["height"]
        listed = self.wanting()
        self.assertEqual(listed, ([("bell", "damp", rained), ("bell", "wet", rained)], False))
        self.assertEqual(self.host.send(op="world-status")["height"], height)
        self.reopen()
        self.assertEqual(self.wanting(), listed)
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(self.wanting(), listed)

    def test_a_refused_asked_spell_is_counted_for_the_stranger_and_listed_for_its_owner(self):
        self.make("owned", THING, record(owner=label("ember")),
                  law='law hand: request.method == "rain" implies request.subject == new.owner')
        self.want("owned", "dry", "new.rains == 0", who="ember")
        stranger = self.host.send(op="world-wanting", principal="glm")
        self.assertEqual((stranger["rows"], stranger["waiting"], stranger["more"]), ([], 1, False))
        owner = self.host.send(op="world-wanting", principal="ember")
        self.assertEqual([(r["object"], r["name"]) for r in owner["rows"]], [("owned", "dry")])
        self.assertEqual(owner["waiting"], 0)
        self.make("list", LIST, record(n=nat(0)))
        answer = self.turn("list", "wants", record(after=nat(0), limit=nat(1)), principal="glm")
        self.assertEqual(answer["result"], label("; waiting 1; next 0"), answer)
        self.reopen()
        self.assertEqual(self.host.send(op="world-wanting", principal="glm"), stranger)

    def test_wants_keeps_the_full_list_and_marks_each_in_one_line(self):
        self.make("owned", THING, record(owner=label("ember")),
                  law='law hand: request.method == "rain" implies request.subject == new.owner')
        self.want("owned", "dry", "new.rains == 0", who="ember")
        for who, status in (("glm", "waiting on other hands"), ("ember", "answerable")):
            reply = self.turn("owned", "receive", record(text=label("delvetalk owned wants"), post=label("")), principal=who)
            lines = [l for l in reply["text"].splitlines() if l.startswith("» dry")]
            self.assertEqual(len(lines), 1, reply)
            self.assertIn(status, lines[0])
            self.assertIn("delvetalk owned rain / text: again", lines[0])
            rows = self.host.send(op="world-wants", principal=who, object="owned")["rows"]
            self.assertEqual(rows[0]["answerable"], who == "ember")

    def test_missing_unoffered_and_unfilled_asks_are_held_but_never_work_for_the_reader(self):
        for name, asks in (("missing", "delvetalk gone rain"), ("unknown", "delvetalk bell nonexistent"),
                           ("hole", "delvetalk {new.absent} rain"), ("fieldhole", "delvetalk bell rain / text: {new.absent}"),
                           ("read", "delvetalk bell ?")):
            self.say("bell", "delvetalk bell want / name: %s / when: new.rains == 0 / asks: %s" % (name, asks), who="ember")
        got = self.host.send(op="world-wanting", principal="glm")
        self.assertEqual((got["rows"], got["waiting"]), ([], 5))
        self.assertEqual(len(self.host.send(op="world-wants", principal="glm", object="bell")["rows"]), 5)
        self.say("bell", "delvetalk bell unwant / name: missing", who="ember")
        self.assertEqual(self.host.send(op="world-wanting", principal="glm")["waiting"], 4)

    def test_actions_and_grown_verbs_use_the_same_filter_as_usage(self):
        guarded = THING.replace("def receive(", "def actions(state: State, context: Abi.Context) -> Lists.List<String>:\n"
                                '  if context.principal == state.owner then Lists.List.cons({head: "rain", tail: Lists.List.nil()}) else Lists.List.nil()\n'
                                "def receive(")
        self.make("guarded", guarded, record(owner=label("ember")))
        self.want("guarded", "dry", "new.rains == 0", who="ember")
        self.assertEqual(self.host.send(op="world-wanting", principal="glm")["waiting"], 1)
        self.assertEqual(len(self.host.send(op="world-wanting", principal="ember")["rows"]), 1)
        self.say("guarded", "delvetalk guarded grow / name: touch / reading: touched", who="ember")
        self.say("guarded", "delvetalk guarded want / name: touch / when: new.acts == 0 / asks: delvetalk guarded touch", who="ember")
        got = self.host.send(op="world-wanting", principal="glm")
        self.assertEqual([(r["object"], r["name"]) for r in got["rows"]], [("guarded", "touch")])
        self.assertEqual(got["waiting"], 1)

    def test_oldest_discovery_rotates_daily_and_the_cursor_wraps_without_repeating(self):
        for n in range(5):
            self.want("bell", "w%d" % n, "new.rains == 0", who="ember")
        seen, pages = set(), []
        for day in range(5):
            self.assertEqual(self.host.send(op="world-advance", height=day * 1440)["status"], "advanced")
            first = self.host.send(op="world-wanting", principal="glm", oldest=True, limit=2)
            names = [r["name"] for r in first["rows"]]
            pages.append(names)
            seen.update(names)
            self.assertEqual(names, ["w%d" % (day % 5), "w%d" % ((day + 1) % 5)])
            self.assertEqual((first["next"], first["more"], first["waiting"]), (2, True, 0))
            all_names, cursor = names[:], first["next"]
            while True:
                rest = self.host.send(op="world-wanting", principal="glm", oldest=True, limit=2, after=cursor)
                all_names += [r["name"] for r in rest["rows"]]
                cursor = rest["next"]
                if not rest["more"]:
                    break
            self.assertEqual(len(all_names), 5)
            self.assertEqual(set(all_names), {"w%d" % n for n in range(5)})
        self.assertEqual(len({tuple(p) for p in pages}), 5)
        self.assertEqual(seen, {"w%d" % n for n in range(5)})
        before = self.host.send(op="world-wanting", principal="glm", oldest=True, limit=2)
        self.reopen()
        self.assertEqual(self.host.send(op="world-wanting", principal="glm", oldest=True, limit=2), before)

    def test_rotated_pages_split_a_full_height_at_the_page_bound(self):
        cap = bounds()["host"]["listPage"]
        self.make("bell3", THING, record(owner=label("ember")))
        for card in ("bell", "bell2", "bell3"):
            for n in range(32):
                self.want(card, "w%02d" % n, "request.clock >= 1", who="ember")
        self.host.send(op="world-advance", height=1)
        first = self.host.send(op="world-wanting", principal="glm", oldest=True, limit=cap + 1)
        self.assertEqual(len(first["rows"]), min(cap, 96))
        got, cursor = first["rows"][:], first["next"]
        while len(got) < 96:
            page = self.host.send(op="world-wanting", principal="glm", oldest=True, limit=cap, after=cursor)
            self.assertTrue(page["rows"], page)
            got += page["rows"]
            cursor = page["next"]
        self.assertEqual(len({(r["object"], r["name"]) for r in got}), 96)
        beyond = self.host.send(op="world-wanting", principal="glm", oldest=True, after=1000000000, limit=1)
        self.assertEqual((beyond["rows"], beyond["next"], beyond["more"]), ([], 96, False))

    def test_a_body_reads_the_index_through_world_wanting(self):
        self.make("list", LIST, record(n=nat(0)))
        dry = self.want("bell2", "dry", "new.rains <= 0")["height"]
        self.want("stone", "dry", "new.rains <= 0", who="ember")
        r = self.turn("list", "wants", record(after=nat(0), limit=nat(0)), principal="glm")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(r["result"]["value"], "bell2 dry @%d: delvetalk bell2 rain / text: again; waiting 0; next %d" % (dry, dry))



SEAL_LAW = ('law open: request.kind == 0 or request.kind == rule or request.subject == "ember"\n'
            'law hands "only glm rains on it": request.method == "rain" implies request.subject == "glm"')


class Standing(Things):
    def test_a_law_and_a_second_hands_try_open_a_want_at_the_refusal(self):
        self.make("seal", THING, record(owner=label("ember")), law=SEAL_LAW)
        placed = self.say("seal", "delvetalk seal want\nname: tried\nreading: a law and a second hand's try\n"
                                  "when: request.laws >= 2 and request.refusedBy >= 1\n"
                                  "asks: delvetalk {request.object} rain / text: {request.refusedBy} of {request.laws}")
        self.assertNotIn("wanted", placed)
        self.assertEqual(self.say("seal", "delvetalk seal rain\ntext: mine")["outcome"]["tag"], "admitted")
        r = self.turn("seal", "receive", record(text=label("delvetalk seal rain\ntext: a try"), post=label("")), principal="kimi")
        refused = r["receipt"]
        self.assertEqual((refused["outcome"]["class"], refused["outcome"]["clause"]), ("lawRefused", "hands"), r)
        self.assertEqual(refused["wanted"], [{"object": "seal", "want": "tried"}])
        listed = self.host.send(op="world-wanting", principal="glm")["rows"]
        self.assertEqual([(x["object"], x["name"], x["since"], x["asks"]) for x in listed],
                         [("seal", "tried", refused["height"], "delvetalk seal rain / text: 1 of 2")])
        wants = self.host.send(op="world-wants", principal="glm", object="seal")["rows"]
        self.assertEqual([(x["name"], x["since"]) for x in wants], [("tried", refused["height"])])
        day = self.host.send(op="world-chronicle", principal="glm", day=0)["lines"]
        self.assertIn("seal came to want tried at entry %d" % refused["height"], day)
        # Replay derives the count and the opening again; so does a snapshot.
        self.reopen()
        self.assertEqual(self.host.send(op="world-wanting", principal="glm")["rows"], listed)
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(self.host.send(op="world-wanting", principal="glm")["rows"], listed)
        self.turn("seal", "receive", record(text=label("delvetalk seal rain\ntext: again"), post=label("")), principal="kimi")
        self.assertEqual(self.host.send(op="world-wanting", principal="glm")["rows"][0]["asks"], "delvetalk seal rain / text: 2 of 2")

    def test_a_law_reads_what_its_thing_stands_at(self):
        self.make("seal", THING, record(owner=label("ember")),
                  law=SEAL_LAW + '\nlaw patience "three refusals close it": request.refusedBy <= 2')
        for i in range(3):
            r = self.turn("seal", "receive", record(text=label("delvetalk seal rain\ntext: %d" % i), post=label("")), principal="kimi")
            self.assertEqual(r["receipt"]["outcome"]["clause"], "hands", r)
        closed = self.turn("seal", "receive", record(text=label("delvetalk seal rain\ntext: late"), post=label("")), principal="glm")
        self.assertEqual(closed["receipt"]["outcome"]["clause"], "patience", closed)


class Journaled(Things):
    """A want's flips are journaled wherever they come from: the clock's move, a write of what it cites."""

    def test_a_write_opens_and_closes_every_dependent_want_past_the_review_batch(self):
        cards = ["reader%03d" % n for n in range(65)]
        for card in cards:
            self.make(card, THING, record(owner=label("ember")))
            self.want(card, "wet", '"bell2".rains == 1', who="ember")
        opened = self.say("bell2", "delvetalk bell2 rain / text: one", who="ember")
        expected = {(card, "wet", opened["height"]) for card in cards}
        self.assertEqual(set(self.wanting()[0]), expected)
        transitions = [e for e in journal_entries(self.path) if e["height"] >= opened["height"]]
        self.assertEqual({(r["object"], r["want"]) for e in transitions for r in e.get("wanted", [])},
                         {(card, "wet") for card in cards})
        self.reopen()
        self.assertEqual(set(self.wanting()[0]), expected)
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(set(self.wanting()[0]), expected)
        closed = self.say("bell2", "delvetalk bell2 rain / text: two", who="ember")
        self.assertEqual(self.wanting(), ([], False))
        transitions = [e for e in journal_entries(self.path) if e["height"] >= closed["height"]]
        self.assertEqual({(r["object"], r["want"]) for e in transitions for r in e.get("unwanted", [])},
                         {(card, "wet") for card in cards})
        self.reopen()
        self.assertEqual(self.wanting(), ([], False))

    def test_outstanding_clock_flips_survive_a_snapshot_before_the_next_clock_closes_them(self):
        long_card = "clock" + "x" * (bounds()["host"]["maxObjectIdBytes"] - 5)
        self.make(long_card, THING, record(owner=label("ember")))
        cards = ("bell", "bell2", long_card)
        for card in cards:
            for n in range(32):
                self.want(card, "w%02d" % n, "request.clock >= 1 and request.clock <= 1", who="ember")
        advanced = self.host.send(op="world-advance", height=1)
        self.assertEqual(advanced["status"], "advanced", advanced)
        at = advanced["receipt"]["height"]
        partial = os.path.join(self.dir.name, "partial.journal")
        copy_journal(self.path, partial, height=at)
        self.release()
        self.path = partial
        self.host = self.spawn()
        self.assertEqual(self.host.send(op="world-open", path=self.path)["status"], "opened")
        expected = {(card, "w%02d" % n, at) for card in cards for n in range(32)}
        self.assertEqual(set(self.wanting()[0]), expected)
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(self.host.send(op="world-open", path=self.path, verify=True)["status"], "opened")
        self.assertEqual(set(self.wanting()[0]), expected)
        closed = self.host.send(op="world-advance", height=2)
        self.assertEqual((closed["status"], closed["clock"]), ("advanced", 2), closed)
        self.assertEqual(self.wanting(), ([], False))
        drained = [e for e in journal_entries(self.path) if e["outcome"]["tag"] == "wantReviewed"]
        opening = [e for e in drained if e.get("wanted")]
        self.assertTrue(opening, drained)
        self.assertEqual({(e["outcome"]["height"], e["outcome"]["clock"]) for e in opening}, {(at, 1)})
        self.assertEqual(sum(len(e.get("unwanted", [])) for e in journal_entries(self.path)), 96)
        self.reopen()
        self.assertEqual(self.wanting(), ([], False))

    def test_thirty_two_thousand_simultaneous_clock_wants_leave_the_clock_free_to_move(self):
        source = THING + "\n" + "\n".join(
            'want w%02d: request.clock >= 1500 and request.clock <= 1500 asks %s' % (n, ASK)
            for n in range(32))
        cards = ["clock%04d" % n + "x" * 111 for n in range(1000)]
        per_principal = bounds()["host"]["objectsPerPrincipal"]
        for n, card in enumerate(cards):
            principal = "clock-maker%d" % (n // per_principal)
            made = self.host.send(op="world-create", principal=principal, identity="mk-" + card, object=card,
                                  source=source, entry="initial", seed=record(owner=label(principal)))
            self.assertEqual(made["status"], "created", made)
        advanced = self.host.send(op="world-advance", height=1500)
        self.assertEqual((advanced["status"], advanced["clock"]), ("advanced", 1500), advanced)
        at = advanced["receipt"]["height"]
        rows = self.wanting()[0]
        self.assertEqual(set(rows), {(card, "w%02d" % n, at) for card in cards for n in range(32)})
        self.assertTrue(all(link["bytes"] <= bounds()["host"]["maxEntryBytes"] for link in links(self.path)))
        transitions = [e for e in journal_entries(self.path) if e["height"] >= at]
        flips = [r for e in transitions for r in e.get("wanted", [])]
        self.assertEqual(len(flips), 32000)
        self.assertGreater(len(cbor({"wanted": flips})), bounds()["host"]["maxEntryBytes"])
        drained = [e for e in transitions if e["outcome"]["tag"] == "wantReviewed"]
        self.assertTrue(drained, "the advance did not journal its outstanding want flips")
        self.assertEqual(sum(len(e.get("wanted", [])) for e in drained),
                         32000 - len(advanced["receipt"].get("wanted", [])))
        self.reopen()
        self.assertEqual(self.wanting()[0], rows)
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(self.wanting()[0], rows)
        later = self.host.send(op="world-advance", height=1501)
        self.assertEqual((later["status"], later["clock"]), ("advanced", 1501), later)
        self.assertEqual(self.wanting(), ([], False))
        self.reopen()
        self.assertEqual(self.wanting(), ([], False))

    def test_replay_refuses_a_want_drain_with_a_different_triggering_clock(self):
        source = THING + '\nwant late: request.clock >= 1 asks ' + ASK
        cap = bounds()["host"]["wantReviewed"]
        for n in range(cap + 1):
            self.make("clock%03d" % n, source, record(owner=label("ember")))
        advanced = self.host.send(op="world-advance", height=1)
        self.assertEqual(advanced["status"], "advanced", advanced)
        self.assertEqual(len(advanced["receipt"]["wanted"]), cap, advanced)
        entries = journal_entries(self.path)
        last = entries[-1]
        self.assertEqual(last["outcome"]["tag"], "wantReviewed", last)
        self.assertEqual(last["height"], advanced["receipt"]["height"] + 1, last)
        self.assertEqual(last["outcome"], {"tag": "wantReviewed", "height": advanced["receipt"]["height"],
                                           "clock": 1, "count": 1})
        self.assertEqual(last["wanted"], [{"object": "clock%03d" % cap, "want": "late"}])
        last["outcome"]["clock"] = 2
        del last["hash"]
        last["hash"] = cid_of(last)
        forged = os.path.join(self.dir.name, "forged.journal")
        write_journal(forged, entries)
        opened = self.spawn().send(op="world-open", path=forged)
        self.assertEqual(opened["status"], "error", opened)
        self.assertIn("want drain does not replay", opened["message"])

    def test_a_want_the_clock_alone_opens_is_in_the_index_and_the_chronicle(self):
        self.want("bell", "late", "request.clock >= 1441")
        self.assertEqual(self.wanting(), ([], False))
        advanced = self.host.send(op="world-advance", height=1500)
        self.assertEqual(advanced["status"], "advanced", advanced)
        at = advanced["receipt"]["height"]
        self.assertEqual(advanced["receipt"]["wanted"], [{"object": "bell", "want": "late"}])
        self.assertEqual(self.wanting(), ([("bell", "late", at)], False))
        self.assertEqual([x["since"] for x in self.host.send(op="world-wants", principal="glm", object="bell")["rows"]], [at])
        day = self.host.send(op="world-chronicle", principal="glm", day=0)["lines"]
        self.assertIn("bell came to want late at entry %d" % at, day)
        # Replay derives the flip again; so does a snapshot.
        self.reopen()
        self.assertEqual(self.wanting(), ([("bell", "late", at)], False))
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.reopen()
        self.assertEqual(self.wanting(), ([("bell", "late", at)], False))

    def test_a_write_of_what_a_want_cites_journals_the_flip_of_the_thing_that_wants(self):
        self.want("bell", "cited", '"bell2".rains >= 1')
        self.assertEqual(self.wanting(), ([], False))
        written = self.say("bell2", "delvetalk bell2 rain\ntext: one", who="kimi")
        self.assertEqual(written["wanted"], [{"object": "bell", "want": "cited"}])
        self.assertEqual(self.wanting(), ([("bell", "cited", written["height"])], False))
        day = self.host.send(op="world-chronicle", principal="glm", day=0)["lines"]
        self.assertIn("bell came to want cited at entry %d" % written["height"], day)
        self.reopen()
        self.assertEqual(self.wanting(), ([("bell", "cited", written["height"])], False))


class Shipped(Arc):
    def test_record_doors_and_pending_lines_wait_for_their_eligible_hands_on_the_commonplace(self):
        self.assertEqual(self.say(KIM, "anthology", "delvetalk anthology write / text: waiting")["status"], "admitted")
        held = self.town.send(op="world-wants", principal=KIM, object="anthology")["rows"]
        self.assertEqual({r["name"]: r["answerable"] for r in held}, {"pending": False, "door": False})
        stranger = self.town.send(op="world-wanting", principal=KIM)
        self.assertFalse([r for r in stranger["rows"] if r["object"] == "anthology"])
        self.assertGreaterEqual(stranger["waiting"], 2)
        card = self.town.send(op="world-card", principal=KIM, object="commonplace")["text"]
        self.assertIn("%d more wait on other hands" % stranger["waiting"], card)
        self.assertNotIn("anthology: a line waits", card)
        owner = self.town.send(op="world-wants", principal=OPENER, object="anthology")["rows"]
        self.assertEqual({r["name"]: r["answerable"] for r in owner}, {"pending": True, "door": True})
        self.assertEqual(self.say(OPENER, "anthology", "delvetalk anthology admit / number: 1")["status"], "admitted")
        self.assertEqual(self.say(OPENER, "anthology", "delvetalk anthology door / label: home / to: commonplace")["status"], "admitted")
        self.assertEqual(self.town.send(op="world-wants", principal=KIM, object="anthology")["rows"], [])


if __name__ == "__main__":
    unittest.main()
