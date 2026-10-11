"""Rooms, things and avatars are ordinary objects: a room is a record with the room's body
(world/bodies/room.obend); entering, leaving, choosing, talking, taking and putting down, offering
and accepting, scoped commands and copies, each refused by name where it should be.

Evidence for docs/METAPHYSICS.md §7.2 (layer: objects).
"""
import os
import unittest

from deploy import genesis
from tests.test_chain import Chain
from tests.wire import boolean, label, listing, nat, record, reference, relation
from tests.bend import closure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOBODY = reference("")


def listing(items):
    return {"tag": "list", "items": list(items)}


def body(name):
    with open(os.path.join(ROOT, "world", "bodies", name + ".obend")) as handle:
        return handle.read()


def make_room(chain, name, owner="ember", **fields):
    """A room as kind/room makes one: a Record under its law (genesis.RECORD_LAW), the room's body laid over it."""
    r = chain.host.send(op="world-create", principal=owner, identity="mk-" + name, object=name, modules=closure("Record"),
                        entry="initial", seed=record(owner=label(owner), **fields), law=genesis.RECORD_LAW)
    chain.assertEqual(r["status"], "created", r)
    r = chain.host.send(op="world-reprogram", principal=owner, identity="body-" + name, object=name, version=0, package=body("room"), mode="extend")
    chain.assertEqual(r["status"], "admitted", r)


def room_seed(name, doors=(), present=(), things=()):
    """The fields of a room: its head, the doors it cites, who is in it, what lies in it."""
    return dict(head=label(name), cites=listing([record(label=label(l), to=reference(t), description=label(""), examples=listing([])) for l, t in doors]),
                presence=relation(*[record(who=label(p), handle=label(""), at=label("")) for p in keyed(present)]),
                things=relation(*[reference(t) for t in keyed(things)]))


def keyed(ids):
    """Object ids in the order of their key: canonical text order, length then bytes."""
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
        make_room(self, "porch", **room_seed("Porch", [("in", "garden")], present=["glm"]))
        make_room(self, "garden", **room_seed("Garden", [("out", "porch")], things=["stone"]))
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch"))
        self.make("stone", closure("Thing"), thing_seed("stone", location="garden"))

    def card(self, name, principal="visitor"):
        """The card is what receive offers for an empty reply, here to someone not in the room."""
        reply = self.turn(name, "receive", record(text=label(""), post=label("")), principal=principal)
        self.assertEqual(reply["status"], "admitted", reply)
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
        """A refusal names its clause beside its reading."""
        return reply["result"]["payload"]["fields"][0]["value"]["value"]

    # --- paths that do not need remove -------------------------------------------------


    def test_enter_in_key_order_and_a_second_entry_is_refused_writing_nothing(self):
        make_room(self, "porch", **room_seed("Porch"))
        for who in ("glm", "kimik3"):
            self.assertEqual(self.result_label(self.turn("porch", "enter", record(), principal=who)), "entered")
        self.assertIn("Porch (2 here). Enter: delvetalk porch enter.\nHere: glm, kimik3\n", self.card("porch"))
        before = self.version("porch")
        again = self.turn("porch", "enter", record(), principal="glm")
        self.assertEqual(self.refusal_reason(again), "Already here.")
        self.assertEqual(self.version("porch"), before)


    def test_who_is_here_is_named_by_handle(self):
        """Playtest 2's D10 (69110): a room listed a Zulip principal as `Here: zulip:tulip.arke.me:17`. Presence keeps
        the handle the reader entered under."""
        make_room(self, "porch", **room_seed("Porch"))
        zulip = "zulip:tulip.arke.me:17"
        self.assertEqual(self.host.send(op="world-principal", principal="ember", did=zulip, handle="Kestrel")["status"], "principal")
        self.turn("porch", "enter", record(), principal=zulip)
        self.assertIn("Porch (1 here). Enter: delvetalk porch enter.\nHere: Kestrel\n", self.card("porch"))

    def test_entering_answers_the_room_as_the_reader_finds_it_and_leaving_the_room_as_it_stands(self):
        make_room(self, "porch", **room_seed("Porch", present=["glm"]))
        entered = self.turn("porch", "enter", record(), principal="kimik3")
        self.assertEqual([o["text"] for o in entered["offers"]],
                         ["Porch (2 here), you are here.\nSay: delvetalk porch say / line: <text>. Leave: delvetalk porch leave.\nHere: glm, kimik3\n"])
        left = self.turn("porch", "leave", record(), principal="kimik3")
        self.assertEqual([o["text"] for o in left["offers"]], ["Porch (1 here). Enter: delvetalk porch enter.\nHere: glm\n"])

    def test_a_spells_turn_line_names_the_room_it_entered(self):
        """The second playtest's D10: entering a room was receipted as its kind (`kind/room v2`), the turn's first
        root. The host's reply names the card the turn ran on, and every turn line names it."""
        from transport import bridge
        make_room(self, "porch", **room_seed("Porch", present=["glm"]))
        entered = self.turn("porch", "receive", record(text=label("delvetalk porch enter"), post=label("")), principal="kimik3")
        self.assertEqual((entered["status"], entered["object"]), ("admitted", "porch"), entered)
        self.assertTrue(bridge.spell_line(entered).split(" ", 1)[1].startswith("admitted porch v"), bridge.spell_line(entered))

    def test_dropping_what_you_do_not_hold_or_where_you_are_not_is_refused_and_changes_nothing(self):
        make_room(self, "porch", **room_seed("Porch", present=["glm"]))
        self.make("stone", closure("Thing"), thing_seed("stone", holder="kimik3", location="garden"))
        reply = self.turn("stone", "drop", record(at=reference("porch")), principal="glm")
        self.assertEqual(self.refusal_reason(reply), "You are not holding it.")
        reply = self.turn("stone", "drop", record(at=reference("porch")), principal="kimik3")
        self.assertEqual(self.refusal_reason(reply), "Only someone here can put things down.")
        # Nothing moved.
        self.assertEqual((self.version("porch"), self.version("stone")), (1, 0))

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
        self.assertIn("Offered to you until clock 50. Take it: delvetalk me accept / thing: stone\n", card)
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


    def test_a_room_with_64_things_renders_under_the_default_budget(self):
        things = ["thing%02d" % i for i in range(64)]
        make_room(self, "hall", **room_seed("Hall", [("out", "porch")], present=["glm", "kimik3"], things=things))
        reply = self.turn("hall", "receive", record(text=label(""), post=label("")), principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        text = reply["offers"][0]["text"]
        self.assertIn("Unclaimed here: thing00, thing01, thing02, thing03, thing04, thing05, thing06, thing07. Inspirit one: delvetalk thing00 inspirit / surrounding: <1 to 400 characters>\n… and 56 more\n", text)
        self.assertLess(len(text), 1400)

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

    # --- paths through remove -----------------------------------------------------------


    def test_a_room_hears_take_and_put_only_from_the_thing_itself(self):
        make_room(self, "garden", **room_seed("Garden", present=["glm"], things=["stone"]))
        for method in ("take", "put"):
            reply = self.turn("garden", method, record(), principal="glm")
            self.assertEqual(self.refusal_reason(reply), "Only a thing can %s itself%s." % (("take", "") if method == "take" else ("put", " down")))
        self.assertEqual(self.version("garden"), 1)

    def test_an_avatar_walks_porch_to_garden_and_back_carrying_a_thing(self):
        self.world()
        moved = self.turn("glm", "move", record(exit=label("in")), principal="glm")
        self.assertEqual(self.result_label(moved), "moved", moved["receipt"]["outcome"])
        self.assertIn("Here: glm\n", self.card("garden"))
        self.assertNotIn("Here: glm", self.card("porch"))
        got = self.turn("stone", "acquire", record(), principal="glm")
        self.assertEqual(self.result_label(got), "done", got["receipt"]["outcome"])
        self.assertNotIn("Lying here", self.card("garden"))
        self.assertEqual(self.holding("glm"), ["stone"])
        back = self.turn("glm", "move", record(exit=label("out")), principal="glm")
        self.assertEqual(self.result_label(back), "moved", back["receipt"]["outcome"])
        dropped = self.turn("stone", "drop", record(at=reference("porch")), principal="glm")
        self.assertEqual(self.result_label(dropped), "done", dropped)
        self.assertIn("Unclaimed here: stone. Inspirit one: delvetalk stone inspirit", self.card("porch"))

    def test_an_avatar_from_nowhere_goes_to_a_room_and_then_walks_its_doors(self):
        """`go {to}` is that room's enter: from nowhere it enters by id and records it; from a room
        it leaves first; only the avatar's principal goes."""
        self.world()
        self.make("kimik3", closure("Avatar"), avatar_seed("kimik3"))
        self.assertEqual(self.refusal_clause(self.turn("kimik3", "move", record(exit=label("in")), principal="kimik3")), "nowhere")
        self.assertEqual(self.refusal_clause(self.turn("kimik3", "go", record(to=label("porch")), principal="glm")), "notMine")
        went = self.turn("kimik3", "go", record(to=label("porch")), principal="kimik3")
        self.assertEqual(self.result_label(went), "moved", went)
        self.assertIn("Here: glm, kimik3\n", self.card("porch"))
        self.assertEqual(self.result_label(self.turn("kimik3", "move", record(exit=label("in")), principal="kimik3")), "moved")
        self.assertIn("Here: kimik3\n", self.card("garden"))
        back = self.turn("kimik3", "go", record(to=label("porch")), principal="kimik3")
        self.assertEqual(self.result_label(back), "moved", back)
        self.assertNotIn("Here: kimik3", self.card("garden"))
        self.assertIn("Here: glm, kimik3\n", self.card("porch"))

    def test_a_reader_at_a_passage_of_long_choices_and_vars_sees_a_card_under_1400(self):
        from tests.test_scene import choice, passage
        long = [choice("c" * 60 + str(i), "gate") for i in range(8)]
        make_room(self, "well", head=label("W" * 120), start=label("gate"), passages=listing([passage("gate", "p" * 600, long)]),
                  vars=listing([record(name=label("v%02d" % i + "n" * 20), value=label("x" * 60)) for i in range(16)]))
        self.assertEqual(self.result_label(self.turn("well", "enter", record(), principal="glm")), "entered")
        card = self.card("well", principal="glm")
        self.assertLessEqual(len(card), 1400, (len(card), card))
        self.assertIn("Choices:\n  * " + "c" * 60 + "0\n", card)



class Scoped(Chain):
    """Scoped resolution: an avatar's principal says `acquire the stone`, `look`, `bump counter`;
    the avatar finds the object (a thing lying in its place by name, then id; else an object
    of that name) and sends it the matching form."""

    def setUp(self):
        super().setUp()
        make_room(self, "porch", **room_seed("Porch", [("in", "garden")], present=["glm", "kimik3"], things=["stone"]))
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


    # The avatar sends the spell as `receive {text, post}`; the host reads a delivered `receive` to a
    # message-dialect card (Counter) as a spell (HOST-HANDOFF 5.63).
    def test_an_object_named_by_a_word_takes_the_form_as_a_spell(self):
        self.make("counter", closure("Counter"), record())
        self.assertEqual(self.say("bump counter")["result"]["label"], "done")
        self.deliver_all()
        self.assertEqual([f["value"] for f in self.state("counter")["fields"] if f["name"] == "count"][0], nat(1))


class Talk(Chain):
    """say and emote offer a line to everyone in the room; whisper to one; only someone here talks."""

    def setUp(self):
        super().setUp()
        make_room(self, "porch", **room_seed("Porch", present=["glm", "kimik3"]))

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
        self.assertEqual([(o["to"], o["text"]) for o in whispered["receipt"]["offers"]],
                         [("kimik3", "glm whispers: psst\n"), ("glm", "Whispered to kimik3; no one else here hears it. Say to all: delvetalk porch say / line: <text>.\n")])
        stranger = self.say("delvetalk porch say / line: hello?", "zero")
        self.assertEqual(stranger["result"]["label"], "refused")
        self.assertEqual(stranger["offers"][0]["text"], "refused notPresent: Only someone here can say; enter first: delvetalk porch enter\n")


class Copies(Chain):
    """Copy as a right: a thing is copyable unless its owner says no; the Workshop's `create /
    like: stone` has the thing copy itself from its own package, without holder and offer."""

    def test_create_like_copies_a_thing_and_the_owner_may_forbid_it(self):
        make_room(self, "porch", **room_seed("Porch", present=["glm"], things=["stone"]))
        self.make("stone", closure("Thing"), thing_seed("stone", location="porch"))
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))
        ask = lambda who, ident: self.turn("workshop", "receive", record(text=label("delvetalk workshop create / like: stone"), post=label("at://x/" + ident)),
                                           principal=who, identity=ident)
        r = ask("glm", "c1")
        self.assertEqual(r["status"], "admitted", r)
        delivered = r.get("delivered", []) + [d for x in self.deliver_all() for d in x.get("delivered", []) + x.get("receipts", [])]
        texts = [o["text"] for d in delivered for o in d.get("receipt", d).get("offers", [])]
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
        self.assertIn("refused notCopyable: stone is not copyable; its owner, ember, decides\n", texts)

if __name__ == "__main__":
    unittest.main()
