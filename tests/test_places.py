"""Places, things and avatars are ordinary objects: moving, taking, offering and accepting, scoped
commands, talk, copies and traces, each refused by name where it should be.

Evidence for FOUNDATION §8 MUD floor (layer: objects).

Places, things and avatars: the MUD floor as ordinary objects.

Compile-level types for every method, then turns through the real host.

The host implements the `remove` list edit, so leave, take, move and acquire run
end to end.
"""
import unittest

from tests.test_turn_world import relation
from tests.test_chain import Chain, boolean, nil, reference
from tests.test_objects import check, closure, compile_job, computation, row_names
from tests.test_turn_world import label, nat, record

NOBODY = reference("")


def listing(items):
    return {"tag": "list", "items": list(items)}


def place_seed(name, exits=(), present=(), things=(), owner="ember"):
    return record(owner=label(owner), name=label(name), description=label("about " + name),
                  exits=listing([record(label=label(l), to=reference(t)) for l, t in exits]),
                  present=relation(*[reference(p) for p in keyed(present)]),
                  things=relation(*[reference(t) for t in keyed(things)]))


def keyed(ids):
    """Object ids in the order of their key {object}: canonical text order, length then bytes."""
    return sorted(ids, key=lambda i: (len(i.encode()), i.encode()))


def thing_seed(name, holder="", location="", owner="ember"):
    return record(owner=label(owner), name=label(name), description=label("a " + name), holder=reference(holder), location=reference(location))


def avatar_seed(handle, at="", holding=()):
    return record(handle=label(handle), at=reference(at), holding=listing([reference(h) for h in holding]))


def names(wire):
    rows = wire["payload"]["fields"][0]["value"]["items"] if wire.get("tag") == "variant" else wire["items"]
    return [[f["value"]["value"] for f in item["fields"] if f["name"] == "object"][0] for item in rows]


class Floor(Chain):

    def world(self):
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm"]))
        self.make("garden", closure("Place"), place_seed("Garden", [("out", "porch")], things=["stone"]))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch"))
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))

    def card(self, name, principal="visitor"):
        """The card is what receive offers for an empty reply, here to someone not in the room."""
        reply = self.turn(name, "receive", record(text=label(""), post=label("")), principal=principal)
        self.assertEqual(reply["status"], "admitted", reply)
        # The card without the spells it teaches (a place's are say, emote and whisper).
        return reply["offers"][0]["text"].split("\nReply with a spell:")[0]

    def version(self, name):
        return self.host.send(op="world-view", principal="ember", object=name)["version"]

    def result_label(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        return reply["result"]["label"]

    def refusal_reason(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertEqual(reply["result"]["label"], "refused", reply)
        fields = reply["result"]["payload"]["fields"]
        return fields[-1]["value"]["value"]

    def refusal_clause(self, reply):
        """A refusal names its clause (Thing.Why, Place.Why) beside its reading."""
        return reply["result"]["payload"]["fields"][0]["value"]["value"]

    # --- paths that do not need remove -------------------------------------------------

    def test_the_room_card_lists_who_is_here_and_the_exits(self):
        self.world()
        text = self.card("porch")
        self.assertEqual(text, "Porch\nabout Porch\nHere: glm\nExit in to garden\nSay: delvetalk porch say / line: <text>. Leave: delvetalk <your avatar> move / exit: <label>.\n")
        self.assertEqual(self.card("garden"), "Garden\nabout Garden\nLying here: stone\nExit out to porch\nSay: delvetalk garden say / line: <text>. Leave: delvetalk <your avatar> move / exit: <label>.\n")

    def test_two_movers_in_one_place_both_appear_on_describe(self):
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm", "kimik3"]))
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: glm\nHere: kimik3\nExit in to garden\nSay: delvetalk porch say / line: <text>. Leave: delvetalk <your avatar> move / exit: <label>.\n")

    def test_enter_appends_in_order_and_a_second_entry_is_refused(self):
        self.make("porch", closure("Place"), place_seed("Porch"))
        for who in ("glm", "kimik3"):
            self.assertEqual(self.result_label(self.turn("porch", "enter", record(), principal=who)), "done")
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: glm\nHere: kimik3\nSay: delvetalk porch say / line: <text>. Leave: delvetalk <your avatar> move / exit: <label>.\nTraces (the last eight, refusals too):\n  kimik3 enter\n  glm enter\n")
        before = self.version("porch")
        again = self.turn("porch", "enter", record(), principal="glm")
        self.assertEqual(self.refusal_reason(again), "Already here.")
        # The refusal changes who is here not at all, and leaves a trace.
        self.assertEqual(self.version("porch"), before + 1)
        self.assertIn("Traces (the last eight, refusals too):\n  glm enter: refused alreadyHere\n", self.card("porch"))

    def test_a_thing_held_in_the_garden_is_dropped_on_the_porch_and_seen_there(self):
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm"]))
        self.make("stone", closure("Thing"), thing_seed("stone", holder="glm", location="garden"))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch", holding=["stone"]))
        dropped = self.turn("stone", "drop", record(at=reference("porch")), principal="glm")
        self.assertEqual(self.result_label(dropped), "done", dropped)
        self.assertIn("Lying here: stone\n", self.card("porch"))
        view = self.state("stone")
        self.assertEqual(names(listing([[f for f in view["fields"] if f["name"] == "holder"][0]["value"]])), [""])
        self.assertEqual(self.version("porch"), 1)
        self.assertEqual(self.version("stone"), 1)
        self.assertEqual(self.holding("glm"), [])

    def test_dropping_what_you_do_not_hold_or_where_you_are_not_is_refused_and_changes_nothing(self):
        self.make("porch", closure("Place"), place_seed("Porch", present=["glm"]))
        self.make("stone", closure("Thing"), thing_seed("stone", holder="kimik3", location="garden"))
        reply = self.turn("stone", "drop", record(at=reference("porch")), principal="glm")
        self.assertEqual(self.refusal_reason(reply), "You are not holding it.")
        reply = self.turn("stone", "drop", record(at=reference("porch")), principal="kimik3")
        self.assertEqual(self.refusal_reason(reply), "Only someone here can put things down.")
        # Nothing moved; the porch keeps a trace of the refused put.
        self.assertEqual((self.version("porch"), self.version("stone")), (1, 0))
        self.assertIn("Traces (the last eight, refusals too):\n  kimik3 put: refused notPresent\n", self.card("porch"))

    # --- giving is offer and accept ------------------------------------------------------

    def holders(self):
        """glm holds the stone; kimik3 and mallory have avatars on the porch."""
        self.make("stone", closure("Thing"), thing_seed("stone", holder="glm", location="garden"))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch", holding=["stone"]))
        self.make("kimik3", closure("Avatar"), avatar_seed("kimik3", "porch"))
        self.make("mallory", closure("Avatar"), avatar_seed("mallory", "porch"))

    def now(self):
        """The world clock (context.clock), which only world-advance moves."""
        return self.host.send(op="world-status")["clock"]

    def offer(self, to="kimik3", until=None, who="glm"):
        return self.turn("stone", "offer", record(to=label(to), until=nat(until if until is not None else self.now() + 50)), principal=who)

    def accept(self, who="kimik3"):
        return self.turn(who, "accept", record(thing=label("stone")), principal=who)

    def stone(self, name):
        return [f for f in self.state("stone")["fields"] if f["name"] == name][0]["value"]

    def holder(self):
        return [f["value"]["value"] for f in self.stone("holder")["fields"] if f["name"] == "object"][0]

    def test_an_offer_leaves_custody_until_the_recipient_accepts(self):
        self.holders()
        self.assertEqual(self.refusal_reason(self.offer(who="kimik3")), "You are not holding it.")
        self.assertEqual(self.result_label(self.offer()), "done")
        self.assertEqual((self.holder(), self.stone("offer")["label"]), ("glm", "open"))
        second = self.refusal_reason(self.offer(to="mallory"))
        self.assertTrue(second.startswith("Already offered to kimik3 until "), second)
        self.assertEqual(self.refusal_reason(self.accept("mallory")), "It is offered to kimik3")
        card = self.card("stone", principal="kimik3")
        self.assertEqual(card, (
            "stone\n"
            "a stone\n"
            "Held by glm.\n"
            "Offered to kimik3 (you): accept it from your avatar until clock 50.\n"))
        self.assertIn("Offered to kimik3 (you): accept it from your avatar until clock ", card)
        self.assertEqual(self.result_label(self.accept()), "done")
        self.assertEqual((self.holder(), self.stone("offer")["label"]), ("kimik3", "none"))
        self.assertEqual((self.holding("glm"), self.holding("kimik3")), ([], ["stone"]))
        self.assertEqual(self.refusal_reason(self.accept()), "Nothing is offered.")

    def test_the_holder_withdraws_and_nobody_else_does(self):
        self.holders()
        self.offer()
        refused = self.turn("stone", "withdraw", principal="kimik3")
        self.assertEqual((self.refusal_clause(refused), self.refusal_reason(refused)), ("notHolder", "Only its holder withdraws an offer."))
        self.assertEqual(self.result_label(self.turn("stone", "withdraw", principal="glm")), "done")
        self.assertEqual(self.stone("offer")["label"], "none")
        self.assertEqual(self.refusal_reason(self.accept()), "Nothing is offered.")
        self.assertEqual(self.refusal_reason(self.turn("stone", "withdraw", principal="glm")), "Nothing is offered.")
        # At clock 0 an `until` of 0 is outside the offer form's declared 1..: the host refuses it
        # before the Thing's own check (codex host 12), as the spell path does.
        early = self.offer(until=self.now())
        self.assertEqual((early["status"], early["receipt"]["outcome"]["class"]), ("refused", "typeMismatch"), early)
        self.assertIn("until takes 1 to", early["receipt"]["outcome"]["reason"])

    def test_an_offer_past_its_clock_time_answers_expired_and_stays(self):
        self.holders()
        until = self.now() + 3
        self.assertEqual(self.result_label(self.offer(until=until)), "done")
        # Turns do not move the clock: many turns later the offer still stands.
        for _ in range(5):
            self.card("stone")
        self.host.send(op="world-advance", height=until - 1)
        self.assertEqual(self.stone("offer")["label"], "open")
        self.host.send(op="world-advance", height=until)
        self.assertEqual(self.refusal_reason(self.accept()), "The offer ran until clock %d" % until)
        self.assertEqual((self.holder(), self.stone("offer")["label"]), ("glm", "open"))

    def test_a_stale_transfer_leaves_the_offer_and_a_retry_takes_it(self):
        self.holders()
        before = self.version("stone")
        self.offer()
        keep = {"tag": "variant", "label": "keep", "payload": record()}
        edits = record(name=keep, description=keep, location=keep,
                       holder={"tag": "variant", "label": "set", "payload": record(value=reference("kimik3"))},
                       offer={"tag": "variant", "label": "set", "payload": record(value={"tag": "variant", "label": "none", "payload": record()})})
        stale = self.host.send(op="world-propose", principal="kimik3", identity="stale", roots=[{"object": "stone", "version": before}],
                               writes=[{"object": "stone", "edits": [edits]}])
        self.assertEqual((stale["status"], stale["receipt"]["outcome"]["class"]), ("refused", "staleRoot"), stale)
        # At the current version the same move, not made by the offered avatar's call, is the law's to
        # refuse: a proposal (kind 3) is no method's write, so the owner clause refuses it first.
        forged = self.host.send(op="world-propose", principal="kimik3", identity="forged", roots=[{"object": "stone", "version": self.version("stone")}],
                                writes=[{"object": "stone", "edits": [edits]}])
        self.assertEqual((forged["status"], forged["receipt"]["outcome"].get("clause")), ("refused", "owner"), forged)
        self.assertEqual((self.holder(), self.stone("offer")["label"]), ("glm", "open"))
        by_spell = self.turn("kimik3", "receive", record(text=label("delvetalk kimik3 accept / thing: stone"), post=label("")), principal="kimik3")
        self.assertEqual(self.result_label(by_spell), "done", by_spell)
        self.assertEqual((self.holder(), self.holding("kimik3")), ("kimik3", ["stone"]))

    def holding(self, name):
        return names([f["value"] for f in self.state(name)["fields"] if f["name"] == "holding"][0])

    def test_acquire_of_a_held_thing_is_refused_by_name(self):
        self.world()
        self.make("held", closure("Thing"), thing_seed("held", holder="kimik3", location="garden"))
        reply = self.turn("held", "acquire", record(), principal="glm")
        self.assertEqual(self.refusal_reason(reply), "Already held by kimik3")

    def test_a_move_through_a_nonexistent_exit_is_refused_and_changes_nothing(self):
        self.world()
        versions = {o: self.version(o) for o in ("porch", "garden", "glm", "stone")}
        reply = self.turn("glm", "move", record(exit=label("up")), principal="glm")
        self.assertEqual(self.refusal_reason(reply), "There is no exit named up")
        self.assertEqual({o: self.version(o) for o in versions}, versions)

    def test_thing_inspect_offers_its_card(self):
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))
        card = self.turn("stone", "receive", record(text=label(""), post=label("")), principal="visitor")["offers"][0]["text"]
        self.assertTrue(card.startswith("stone\na stone\nNobody holds it.\n\nReply with a spell:\n"), card)
        self.assertIn("\nReply with a spell:\n\n    delvetalk stone acquire\n", card)

    def test_a_place_with_64_things_renders_under_the_default_budget(self):
        things = ["thing%02d" % i for i in range(64)]
        self.make("hall", closure("Place"), place_seed("Hall", [("out", "porch")], present=["glm", "kimik3"], things=things))
        reply = self.turn("hall", "receive", record(text=label(""), post=label("")), principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        text = reply["offers"][0]["text"]
        self.assertEqual(text.count("Lying here: "), 8)
        self.assertIn("… and 56 more\n", text)
        self.assertLess(len(text), 1400)
        print("\n  place with 64 things: describe turn %s ticks, card %d bytes" % (reply["ticksUsed"], len(text)))
        self.assertLess(reply["ticksUsed"], 100000)

    def test_an_avatar_with_a_full_inbox_describes_under_the_default_budget(self):
        """The inbox keeps the newest 64 notes (the mailbox's bound): 65 notes leave 64, and the
        card shows eight of them and counts the rest."""
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch"))
        for i in range(64):
            note = self.turn("glm", "note", record(text=label("note %03d" % i)), principal="kimik3")
            self.assertEqual(note["status"], "admitted", note)
        over = self.turn("glm", "note", record(text=label("one too many")), principal="kimik3")
        self.assertEqual(over["status"], "admitted", over)  # a full inbox drops its oldest
        reply = self.turn("glm", "receive", record(text=label(""), post=label("")), principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        text = reply["offers"][0]["text"]
        self.assertEqual(text.count("kimik3: note "), 7)  # and "one too many", the newest
        self.assertLess(text.index("one too many"), text.index("kimik3: note 063"))  # newest first
        self.assertNotIn("note 000", text)
        self.assertIn("… and 56 more\n", text)
        print("\n  avatar with 64 of 65 notes: describe turn %s ticks, card %d bytes" % (reply["ticksUsed"], len(text)))
        self.assertLess(reply["ticksUsed"], 100000)

    # --- paths through remove -----------------------------------------------------------

    def test_leaving_removes_the_avatar_from_who_is_here_and_traces_the_leave(self):
        self.make("porch", closure("Place"), place_seed("Porch", present=["glm", "kimik3"]))
        reply = self.turn("porch", "leave", record(), principal="glm")
        self.assertEqual(self.result_label(reply), "done", reply["receipt"]["outcome"])
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: kimik3\nSay: delvetalk porch say / line: <text>. Leave: delvetalk <your avatar> move / exit: <label>.\nTraces (the last eight, refusals too):\n  glm leave\n")

    def test_take_removes_from_things_when_the_thing_asks_for_itself(self):
        self.make("garden", closure("Place"), place_seed("Garden", present=["glm"], things=["stone", "fern"]))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "garden"))
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))
        reply = self.turn("stone", "acquire", record(), principal="glm")
        self.assertEqual(self.result_label(reply), "done", reply["receipt"]["outcome"])
        self.assertEqual(self.card("garden"), "Garden\nabout Garden\nHere: glm\nLying here: fern\nSay: delvetalk garden say / line: <text>. Leave: delvetalk <your avatar> move / exit: <label>.\nTraces (the last eight, refusals too):\n  glm take\n")

    def test_a_place_hears_take_and_put_only_from_the_thing_itself(self):
        self.make("garden", closure("Place"), place_seed("Garden", present=["glm"], things=["stone"]))
        for method in ("take", "put"):
            reply = self.turn("garden", method, record(), principal="glm")
            self.assertEqual(self.refusal_reason(reply), "Only a thing can %s itself%s." % (("take", "") if method == "take" else ("put", " down")))
        self.assertEqual(self.version("garden"), 0)

    def test_an_avatar_walks_porch_to_garden_and_back_carrying_a_thing(self):
        self.world()
        moved = self.turn("glm", "move", record(exit=label("in")), principal="glm")
        self.assertEqual(self.result_label(moved), "moved", moved["receipt"]["outcome"])
        self.assertIn("Here: glm\n", self.card("garden"))
        self.assertNotIn("Here: glm\n", self.card("porch"))
        got = self.turn("stone", "acquire", record(), principal="glm")
        self.assertEqual(self.result_label(got), "done", got["receipt"]["outcome"])
        self.assertNotIn("Lying here", self.card("garden"))
        self.assertEqual(self.holding("glm"), ["stone"])
        back = self.turn("glm", "move", record(exit=label("out")), principal="glm")
        self.assertEqual(self.result_label(back), "moved", back["receipt"]["outcome"])
        dropped = self.turn("stone", "drop", record(at=reference("porch")), principal="glm")
        self.assertEqual(self.result_label(dropped), "done", dropped)
        self.assertIn("Lying here: stone\n", self.card("porch"))

    def test_an_avatar_from_nowhere_goes_to_a_place_and_then_walks_its_exits(self):
        """SEEDING §7: no public path set `at`, so an avatar from nowhere could never `move`. `go
        {place}` enters the place by id and records it; from a place it leaves first; only the
        avatar's principal goes."""
        self.world()
        self.make("kimik3", closure("Avatar"), avatar_seed("kimik3"))
        self.assertEqual(self.refusal_clause(self.turn("kimik3", "move", record(exit=label("in")), principal="kimik3")), "nowhere")
        self.assertEqual(self.refusal_clause(self.turn("kimik3", "go", record(place=label("porch")), principal="glm")), "notMine")
        went = self.turn("kimik3", "go", record(place=label("porch")), principal="kimik3")
        self.assertEqual(self.result_label(went), "moved", went)
        self.assertIn("Here: kimik3\n", self.card("porch"))
        self.assertEqual(self.result_label(self.turn("kimik3", "move", record(exit=label("in")), principal="kimik3")), "moved")
        self.assertIn("Here: kimik3\n", self.card("garden"))
        back = self.turn("kimik3", "go", record(place=label("porch")), principal="kimik3")
        self.assertEqual(self.result_label(back), "moved", back)
        self.assertNotIn("Here: kimik3\n", self.card("garden"))
        self.assertIn("Here: kimik3\n", self.card("porch"))


if __name__ == "__main__":
    unittest.main()


class Scoped(Chain):
    """Scoped resolution: an avatar's principal says `acquire the stone`, `look`, `bump counter`;
    the avatar finds the object (a thing lying in its place by name, then id; else an object
    of that name) and sends it the matching form."""

    def setUp(self):
        super().setUp()
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm", "kimik3"], things=["stone"]))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch"))
        self.make("kimik3", closure("Avatar"), avatar_seed("kimik3", "porch"))
        self.make("stone", closure("Thing"), thing_seed("stone", location="porch"))

    def say(self, text, who="glm"):
        r = self.turn(who, "receive", record(text=label(text), post=label("at://x/" + who)), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_acquire_the_stone_reaches_the_stone_lying_here(self):
        r = self.say("acquire the stone")
        self.assertEqual(r["result"]["label"], "done", r)
        self.deliver_all()
        holder = [f["value"] for f in self.state("stone")["fields"] if f["name"] == "holder"][0]
        self.assertEqual([f["value"]["value"] for f in holder["fields"] if f["name"] == "object"], ["glm"])

    def test_look_shows_the_place_and_two_of_a_name_are_asked_about(self):
        look = self.say("look")
        self.assertEqual(look["offers"][0]["text"], "Porch\nabout Porch\nHere: glm\nHere: kimik3\nLying here: stone\nExit in to garden\nSay: delvetalk porch say / line: <text>. Leave: delvetalk <your avatar> move / exit: <label>.\nYou are here.\n")
        self.make("porch2", closure("Place"), place_seed("Porch", present=["glm"], things=["stone", "pebble"]))
        self.make("pebble", closure("Thing"), thing_seed("stone", location="porch2"))
        self.make("glm2", closure("Avatar"), avatar_seed("glm2", "porch2"))
        r = self.turn("glm2", "receive", record(text=label("acquire the stone"), post=label("at://x/2")), principal="glm2")
        self.assertEqual(r["offers"][0]["text"], "Which one: pebble, stone?\n")

    # The avatar sends the spell as `receive {text, post}`; the host reads a delivered `receive` to a
    # message-dialect card (Counter) as a spell (HOST-HANDOFF 5.63).
    def test_an_object_named_by_a_word_takes_the_form_as_a_spell(self):
        self.make("counter", closure("Counter"), record())
        self.assertEqual(self.say("bump counter")["result"]["label"], "done")
        self.deliver_all()
        self.assertEqual([f["value"] for f in self.state("counter")["fields"] if f["name"] == "count"][0], nat(1))


class Talk(Chain):
    """say and emote offer a line to every avatar present; whisper to one; only someone here talks."""

    def setUp(self):
        super().setUp()
        self.make("porch", closure("Place"), place_seed("Porch", present=["glm", "kimik3"]))

    def say(self, text, who):
        r = self.turn("porch", "receive", record(text=label(text), post=label("at://x/1")), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_say_and_emote_reach_everyone_present_whisper_one_and_a_stranger_is_refused(self):
        said = self.say("delvetalk porch say / line: the lamp is lit", "glm")
        self.assertEqual(said["result"]["label"], "done", said)
        # In key order (who is here is keyed by object id); each avatar's principal gets the line.
        offers = [(o["to"], o["text"]) for o in said["receipt"]["offers"]]
        self.assertEqual(offers, [("glm", "glm: the lamp is lit\n"), ("kimik3", "glm: the lamp is lit\n")])
        emoted = self.say("delvetalk porch emote / line: waves", "kimik3")
        self.assertEqual([o["text"] for o in emoted["receipt"]["offers"]], ["* kimik3 waves\n", "* kimik3 waves\n"])
        whispered = self.say("delvetalk porch whisper / to: kimik3 / line: psst", "glm")
        self.assertEqual([(o["to"], o["text"]) for o in whispered["receipt"]["offers"]], [("kimik3", "glm whispers: psst\n")])
        stranger = self.say("delvetalk porch say / line: hello?", "zero")
        self.assertEqual(stranger["result"]["label"], "refused")
        self.assertEqual(stranger["offers"][0]["text"], "Not done: Only someone here can say.\n")


class Copies(Chain):
    """Copy as a right: a thing is copyable unless its owner says no; the Workshop's `create /
    like: stone` has the thing copy itself from its own package, without holder and offer."""

    def test_create_like_copies_a_thing_and_the_owner_may_forbid_it(self):
        self.make("porch", closure("Place"), place_seed("Porch", present=["glm"], things=["stone"]))
        self.make("stone", closure("Thing"), thing_seed("stone", location="porch"))
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))
        ask = lambda who, ident: self.turn("workshop", "receive", record(text=label("delvetalk workshop create / like: stone"), post=label("at://x/" + ident)),
                                           principal=who, identity=ident)
        r = ask("glm", "c1")
        self.assertEqual(r["status"], "admitted", r)
        delivered = r.get("delivered", []) + [d for x in self.deliver_all() for d in x.get("delivered", []) + x.get("receipts", [])]
        texts = [o["text"] for d in delivered for o in d.get("receipt", d).get("offers", [])]
        self.assertEqual(texts, ["Copied stone as stone/thing/1.\n"])
        self.assertTrue(any(t.startswith("Copied stone as ") for t in texts), (texts, delivered[:1]))
        copied = [t for t in texts if t.startswith("Copied stone as ")][0][len("Copied stone as "):-2]
        state = self.state(copied)
        fields = {f["name"]: f["value"] for f in state["fields"]}
        self.assertEqual((fields["name"], fields["copyable"]), (label("stone"), boolean(True)))
        self.assertEqual(fields["holder"], NOBODY)
        self.assertEqual(fields["owner"], label("glm"))           # the copy is the asker's
        # The owner switches it off; a second ask is refused by name.
        off = self.turn("stone", "receive", record(text=label("delvetalk stone set\ncopyable: no"), post=label("")), principal="ember")
        self.assertEqual(off["status"], "admitted", off)
        r = ask("glm", "c2")
        delivered = r.get("delivered", []) + [d for x in self.deliver_all() for d in x.get("delivered", []) + x.get("receipts", [])]
        texts = [o["text"] for d in delivered for o in d.get("receipt", d).get("offers", [])]
        self.assertIn("Not copied: stone is not copyable; its owner, ember, decides.\n", texts)


class Traces(Chain):
    """A place keeps the last eight things that happened in it, admitted or refused, with
    handles and clauses."""

    def test_the_last_eight_with_handles_and_clauses(self):
        self.make("porch", closure("Place"), place_seed("Porch"))
        self.assertEqual(self.host.send(op="world-principal", principal="transport", did="did:plc:glmglmglmglm", handle="glm.delve.town")["status"], "principal")
        for i in range(5):
            self.turn("porch", "enter", record(), principal="did:plc:glmglmglmglm", identity="e%d" % i)
            self.turn("porch", "leave", record(), principal="did:plc:glmglmglmglm", identity="l%d" % i)
        self.turn("porch", "leave", record(), principal="did:plc:glmglmglmglm", identity="l-again")
        card = self.turn("porch", "receive", record(text=label(""), post=label("")), principal="visitor")["offers"][0]["text"]
        self.assertEqual(card, (
            "Porch\n"
            "about Porch\n"
            "Say: delvetalk porch say / line: <text>. Leave: delvetalk <your avatar> move / exit: <label>.\n"
            "Traces (the last eight, refusals too):\n"
            "  glm.delve.town leave: refused notHere\n"
            "  glm.delve.town leave\n"
            "  glm.delve.town enter\n"
            "  glm.delve.town leave\n"
            "  glm.delve.town enter\n"
            "  glm.delve.town leave\n"
            "  glm.delve.town enter\n"
            "  glm.delve.town leave\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk porch say\n"
            "    line: <text, 1 to 280 characters>\n"
            "\n"
            "    delvetalk porch emote\n"
            "    line: <text, 1 to 280 characters>\n"
            "\n"
            "    delvetalk porch whisper\n"
            "    to: <text, 1 to 160 characters>\n"
            "    line: <text, 1 to 280 characters>\n"))
        lines = card.split("Traces (the last eight, refusals too):\n")[1].split("\nReply with a spell:")[0].strip("\n").split("\n")
        self.assertEqual(len(lines), 8)
        self.assertEqual(lines[0], "  glm.delve.town leave: refused notHere")
        self.assertEqual(lines[1], "  glm.delve.town leave")
