"""Places, things and avatars: the MUD floor as ordinary objects.

Compile-level types for every method, then turns through the real host.

The host implements the `remove` list edit, so leave, take, move and acquire run
end to end.
"""
import unittest

from tests.test_chain import Chain, boolean, nil, reference
from tests.test_objects import check, closure, compile_job, computation, row_names
from tests.test_turn_world import label, nat, record

NOBODY = reference("")


def listing(items):
    return {"tag": "list", "items": list(items)}


def place_seed(name, exits=(), present=(), things=(), owner="ember"):
    return record(owner=label(owner), name=label(name), description=label("about " + name),
                  exits=listing([record(label=label(l), to=reference(t)) for l, t in exits]),
                  present=listing([reference(p) for p in present]),
                  things=listing([reference(t) for t in things]))


def thing_seed(name, holder="", location="", owner="ember"):
    return record(owner=label(owner), name=label(name), description=label("a " + name), holder=reference(holder), location=reference(location))


def avatar_seed(handle, at="", holding=()):
    return record(handle=label(handle), at=reference(at), holding=listing([reference(h) for h in holding]))


def names(wire):
    return [[f["value"]["value"] for f in item["fields"] if f["name"] == "object"][0] for item in wire["items"]]


class Types(unittest.TestCase):
    METHODS = {"Place": ["enter", "leave", "take", "put", "receive"], "Thing": ["acquire", "drop", "offer", "withdraw", "transfer", "give", "receive"],
               "Avatar": ["move", "arrive", "note", "hold", "release", "accept", "receive"]}

    def test_every_method_is_an_activity_over_the_plan_library(self):
        for module, methods in self.METHODS.items():
            for method in methods:
                with self.subTest(method="%s.%s" % (module, method)):
                    reply = compile_job(closure(module), method)
                    self.assertEqual(reply["status"], "compiled", reply)
                    comp = computation(reply["artifact"]["type"])
                    self.assertEqual(row_names(comp["plan"]["row"])[:3], ["view", "write", "call"])

    def test_every_object_exports_initial(self):
        for module in self.METHODS:
            self.assertEqual(compile_job(closure(module), "initial")["status"], "compiled")


class Floor(Chain):
    test_ring_then_open_then_light = None  # inherited from Chain; not a floor test

    def world(self):
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm"]))
        self.make("garden", closure("Place"), place_seed("Garden", [("out", "porch")], things=["stone"]))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch"))
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))

    def card(self, name, principal="visitor"):
        """The card is what receive offers for an empty reply, here to someone not in the room."""
        reply = self.turn(name, "receive", record(text=label(""), post=label(""), slot=label("")), principal=principal)
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
        self.assertEqual(text, "Porch\nabout Porch\nHere: glm\nExit in to garden\n")
        self.assertEqual(self.card("garden"), "Garden\nabout Garden\nLying here: stone\nExit out to porch\n")

    def test_two_movers_in_one_place_both_appear_on_describe(self):
        self.make("porch", closure("Place"), place_seed("Porch", [("in", "garden")], present=["glm", "kimik3"]))
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: glm\nHere: kimik3\nExit in to garden\n")

    def test_enter_appends_in_order_and_a_second_entry_is_refused(self):
        self.make("porch", closure("Place"), place_seed("Porch"))
        for who in ("glm", "kimik3"):
            self.assertEqual(self.result_label(self.turn("porch", "enter", record(), principal=who)), "done")
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: glm\nHere: kimik3\n")
        before = self.version("porch")
        again = self.turn("porch", "enter", record(), principal="glm")
        self.assertEqual(self.refusal_reason(again), "Already here.")
        self.assertEqual(self.version("porch"), before)

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
        self.assertEqual((self.version("porch"), self.version("stone")), (0, 0))

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
        return self.turn("stone", "offer", record(to=reference(to), until=nat(until if until is not None else self.now() + 50)), principal=who)

    def accept(self, who="kimik3"):
        return self.turn(who, "accept", record(thing=reference("stone")), principal=who)

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
        print("\n--- stone, offered, read by kimik3 ---\n" + card)
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
        self.assertTrue(self.refusal_reason(self.offer(until=self.now())).startswith("until must be after the clock, now "))

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
        # At the current version the same move, not made by the offered avatar's call, is the law's to refuse.
        forged = self.host.send(op="world-propose", principal="kimik3", identity="forged", roots=[{"object": "stone", "version": self.version("stone")}],
                                writes=[{"object": "stone", "edits": [edits]}])
        self.assertEqual((forged["status"], forged["receipt"]["outcome"].get("clause")), ("refused", "notOffered"), forged)
        self.assertEqual((self.holder(), self.stone("offer")["label"]), ("glm", "open"))
        by_spell = self.turn("kimik3", "receive", record(text=label("delvetalk kimik3 accept / thing: stone"), post=label(""), slot=label("")), principal="kimik3")
        self.assertEqual(self.result_label(by_spell), "done", by_spell)
        self.assertEqual((self.holder(), self.holding("kimik3")), ("kimik3", ["stone"]))

    def test_give_is_an_offer_for_one_release(self):
        self.holders()
        h = self.now()
        self.assertEqual(self.result_label(self.turn("stone", "give", record(to=reference("kimik3")), principal="glm")), "done")
        until = [f["value"]["value"] for f in self.stone("offer")["payload"]["fields"] if f["name"] == "until"][0]
        self.assertGreaterEqual(int(until), h + 1000)
        self.assertEqual(self.holder(), "glm")
        self.assertIn("(give is now offer: the one you give it to accepts it from their avatar; give goes after one release.)", self.card("stone"))
        self.assertEqual(self.result_label(self.accept()), "done")

    def holding(self, name):
        return names([f["value"] for f in self.state(name)["fields"] if f["name"] == "holding"][0])

    def inbox(self, name):
        wire = [f["value"] for f in self.state(name)["fields"] if f["name"] == "inbox"][0]
        out = []
        for item in wire["items"]:
            note = {f["name"]: f["value"]["value"] for f in item["fields"]}
            out.append((note["from"], note["text"]))
        return out

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
        card = self.turn("stone", "receive", record(text=label(""), post=label(""), slot=label("")), principal="visitor")["offers"][0]["text"]
        self.assertTrue(card.startswith("stone\na stone\nNobody holds it.\n(give is now offer"), card)
        self.assertIn("\nReply with a spell:\n\n    delvetalk stone acquire\n", card)

    def test_a_place_with_64_things_renders_under_the_default_budget(self):
        things = ["thing%02d" % i for i in range(64)]
        self.make("hall", closure("Place"), place_seed("Hall", [("out", "porch")], present=["glm", "kimik3"], things=things))
        reply = self.turn("hall", "receive", record(text=label(""), post=label(""), slot=label("")), principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        text = reply["offers"][0]["text"]
        self.assertEqual(text.count("Lying here: "), 8)
        self.assertIn("… and 56 more\n", text)
        self.assertLess(len(text), 1400)
        print("\n  place with 64 things: describe turn %s ticks, card %d bytes" % (reply["ticksUsed"], len(text)))
        self.assertLess(reply["ticksUsed"], 100000)

    def test_an_avatar_with_a_full_inbox_describes_under_the_default_budget(self):
        """The inbox keeps the newest 64 notes (the mailbox's bound): 248 notes leave 64, and the
        card shows eight of them and counts the rest."""
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch"))
        for i in range(247):
            note = self.turn("glm", "note", record(text=label("note %03d" % i)), principal="kimik3")
            self.assertEqual(note["status"], "admitted", note)
        over = self.turn("glm", "note", record(text=label("one too many")), principal="kimik3")
        self.assertEqual(over["status"], "admitted", over)  # a full inbox drops its oldest
        reply = self.turn("glm", "receive", record(text=label(""), post=label(""), slot=label("")), principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        text = reply["offers"][0]["text"]
        self.assertEqual(text.count("kimik3: note "), 7)  # and "one too many", the newest
        self.assertLess(text.index("one too many"), text.index("kimik3: note 246"))  # newest first
        self.assertIn("… and 56 more\n", text)
        print("\n  avatar with 64 of 248 notes: describe turn %s ticks, card %d bytes" % (reply["ticksUsed"], len(text)))
        self.assertLess(reply["ticksUsed"], 100000)

    # --- paths through remove -----------------------------------------------------------

    def test_leave_removes_from_present(self):
        self.make("porch", closure("Place"), place_seed("Porch", present=["glm", "kimik3"]))
        reply = self.turn("porch", "leave", record(), principal="glm")
        self.assertEqual(self.result_label(reply), "done", reply["receipt"]["outcome"])
        self.assertEqual(self.card("porch"), "Porch\nabout Porch\nHere: kimik3\n")

    def test_take_removes_from_things_when_the_thing_asks_for_itself(self):
        self.make("garden", closure("Place"), place_seed("Garden", present=["glm"], things=["stone", "fern"]))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "garden"))
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))
        reply = self.turn("stone", "acquire", record(), principal="glm")
        self.assertEqual(self.result_label(reply), "done", reply["receipt"]["outcome"])
        self.assertEqual(self.card("garden"), "Garden\nabout Garden\nHere: glm\nLying here: fern\n")

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


if __name__ == "__main__":
    unittest.main()


class Scoped(Chain):
    """Scoped resolution: an avatar's principal says `acquire the stone`, `look`, `bump counter`;
    the avatar finds the object (a thing lying in its place by name, then id; else an object
    of that name) and sends it the matching form."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

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
        print("\n--- look ---\n" + look["offers"][0]["text"])
        self.assertEqual(look["offers"][0]["text"], "Porch\nabout Porch\nHere: glm\nHere: kimik3\nLying here: stone\nExit in to garden\nYou are here.\n")
        self.make("porch2", closure("Place"), place_seed("Porch", present=["glm"], things=["stone", "pebble"]))
        self.make("pebble", closure("Thing"), thing_seed("stone", location="porch2"))
        self.make("glm2", closure("Avatar"), avatar_seed("glm2", "porch2"))
        r = self.turn("glm2", "receive", record(text=label("acquire the stone"), post=label("at://x/2")), principal="glm2")
        self.assertEqual(r["offers"][0]["text"], "Which one: pebble, stone?\n")

    def test_an_object_named_by_a_word_takes_the_form_as_a_spell(self):
        self.make("counter", closure("Counter"), record())
        self.assertEqual(self.say("bump counter")["result"]["label"], "done")
        self.deliver_all()
        self.assertEqual([f["value"] for f in self.state("counter")["fields"] if f["name"] == "count"][0], nat(1))


class Talk(Chain):
    """say and emote offer a line to every avatar present; whisper to one; only someone here talks."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def setUp(self):
        super().setUp()
        self.make("porch", closure("Place"), place_seed("Porch", present=["glm", "kimik3"]))

    def say(self, text, who):
        r = self.turn("porch", "receive", record(text=label(text), post=label("at://x/1")), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_say_emote_and_whisper(self):
        said = self.say("delvetalk porch say / line: the lamp is lit", "glm")
        self.assertEqual(said["result"]["label"], "done", said)
        # The newest arrival first; each avatar's principal gets the line.
        offers = [(o["to"], o["text"]) for o in said["receipt"]["offers"]]
        self.assertEqual(offers, [("kimik3", "glm: the lamp is lit\n"), ("glm", "glm: the lamp is lit\n")])
        emoted = self.say("delvetalk porch emote / line: waves", "kimik3")
        self.assertEqual([o["text"] for o in emoted["receipt"]["offers"]], ["* kimik3 waves\n", "* kimik3 waves\n"])
        whispered = self.say("delvetalk porch whisper / to: kimik3 / line: psst", "glm")
        self.assertEqual([(o["to"], o["text"]) for o in whispered["receipt"]["offers"]], [("kimik3", "glm whispers: psst\n")])
        stranger = self.say("delvetalk porch say / line: hello?", "zero")
        self.assertEqual(stranger["result"]["label"], "refused")
        self.assertEqual(stranger["offers"][0]["text"], "Not done: only someone here can say.\n")


class Copies(Chain):
    """Copy as a right: a thing is copyable unless its owner says no; the Workshop's `create /
    like: stone` has the thing copy itself from its own package, without holder and offer."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

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
        print("\n--- copy ---\n%r" % texts)
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
