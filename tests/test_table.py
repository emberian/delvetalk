"""The Automatafl table on commit-reveal seats: one opening round of the original 11x11
game, played through the host. Each seat is its own object; a reveal awaits the
opponent's commitment slot (the turn named Seats.commitIntent) and resumes when it is
admitted. The resolved board equals the qualified game's pure result for the same pair."""
import hashlib
import json
import os
import unittest

from tests.test_chain import Chain, reference
from tests.test_objects import check, compile_job
from tests.test_replay import get
from tests.test_turn_world import ROOT, closure, label, nat, record

NORTH, SOUTH = "did:plc:glm", "did:plc:kimik3"
OPENING = json.load(open(os.path.join(ROOT, "tests", "fixtures", "automatafl", "original-opening.json")))


def framed(text):
    return "%d:%s" % (len(text), text)


def digest(table, round_, seat, source, target, nonce):
    text = "".join(framed(t) for t in ("delvetalk.automatafl.commit.v2", table, str(round_), str(seat), str(source), str(target), nonce))
    return hashlib.sha256(text.encode()).hexdigest()


def pure_play(board, automaton, s0, t0, s1, t1):
    compiled = compile_job(closure("Validated"), "play")
    n = lambda v: {"tag": "natural", "value": str(v)}
    out = check({"op": "run", "artifact": compiled["artifact"], "arguments": [n(11), n(11), n(board), n(automaton), n(0), n(s0), n(t0), n(s1), n(t1)]})
    return {f["name"]: f["value"]["value"] for f in out["value"]["fields"]}


class Table(Chain):
    NONCE0, NONCE1 = "a" * 64, "b" * 64
    # North moves the attractor at C... (4,0) to (2,0); South the attractor at (4,10) to (2,10).
    MOVES = (4, 2, 114, 112)

    def setUp(self):
        super().setUp()
        self.make("north", closure("Seat"), record(table=reference("table"), seat=nat(0), owner=label(NORTH), opponent=label(SOUTH), rival=reference("south")))
        self.make("south", closure("Seat"), record(table=reference("table"), seat=nat(1), owner=label(SOUTH), opponent=label(NORTH), rival=reference("north")))
        game = record(board=nat(int(OPENING["board"])), automaton=nat(OPENING["automaton"]), marks=nat(0), status=nat(0), winner=nat(0))
        r = self.host.send(op="world-create", principal="ember", identity="mk-table", object="table", modules=closure("Table"),
                           entry="initial", seed=record(owner=label("ember"), north=reference("north"), south=reference("south"), round=nat(0),
                                                        width=nat(11), height=nat(11), game=game))
        self.assertEqual(r["status"], "created", r)

    def seal(self, seat, who, source, target, nonce, identity="table/0/commit", seat_index=None):
        index = 0 if seat == "north" else 1
        return self.turn(seat, "commit", record(round=nat(0), digest=label(digest("table", 0, index, source, target, nonce))),
                         principal=who, identity=identity)

    def open(self, seat, who, source, target, nonce):
        return self.turn(seat, "reveal", record(round=nat(0), source=nat(source), target=nat(target), nonce=label(nonce)), principal=who)

    def reason(self, reply):
        self.assertIn("result", reply, reply)
        return reply["result"]["payload"]["fields"][0]["value"]["value"]

    def test_the_owner_amends_the_table_and_a_stranger_may_not(self):
        version = self.host.send(op="world-view", principal="ember", object="table")["version"]
        law = 'law owner: request.kind == 0 or request.subject == "ember"'
        theirs = self.host.send(op="world-amend", principal=NORTH, identity="am-north", object="table", version=version, law=law)
        self.assertEqual((theirs["status"], theirs["receipt"]["outcome"].get("clause")), ("refused", "owner"), theirs)
        mine = self.host.send(op="world-amend", principal="ember", identity="am-ember", object="table", version=version, law=law)
        self.assertEqual(mine["status"], "admitted", mine)

    def test_one_opening_round(self):
        s0, t0, s1, t1 = self.MOVES
        wrong = self.seal("north", NORTH, s0, t0, self.NONCE0, identity="at://glm/p/1")
        self.assertEqual(self.reason(wrong), "Seal in the turn named table/0/commit")
        self.assertEqual(self.reason(self.seal("north", SOUTH, s0, t0, self.NONCE0, identity="at://kim/p/0")), "This seat is glm")
        self.assertEqual(self.seal("north", NORTH, s0, t0, self.NONCE0)["result"]["label"], "committed")
        early = self.turn("table", "resolve", principal="did:plc:zero")
        self.assertEqual(self.reason(early), "North has not opened this round.")
        # North opens before South has sealed: the reveal waits on South's slot.
        waiting = self.open("north", NORTH, s0, t0, self.NONCE0)
        self.assertEqual(waiting["status"], "suspended", waiting)
        sealed = self.seal("south", SOUTH, s1, t1, self.NONCE1)
        self.assertEqual(sealed["status"], "admitted", sealed)
        self.assertEqual(get(self.state("north"), "opened"), {"tag": "boolean", "value": True})
        lie = self.open("south", SOUTH, s1, t1 + 1, self.NONCE1)
        self.assertEqual(self.reason(lie), "The opening does not match the seal.")
        # South opens after North sealed: the await answers at once.
        self.assertEqual(self.open("south", SOUTH, s1, t1, self.NONCE1)["result"]["label"], "opened")
        resolved = self.turn("table", "resolve", principal="did:plc:zero")
        self.assertEqual(resolved["status"], "admitted", resolved["receipt"]["outcome"])
        self.assertEqual(resolved["result"]["label"], "resolved", resolved)
        print("\n  resolve turn: %s ticks" % resolved["ticksUsed"])
        expected = pure_play(int(OPENING["board"]), OPENING["automaton"], s0, t0, s1, t1)
        game = {f["name"]: f["value"]["value"] for f in get(self.state("table"), "game")["fields"]}
        self.assertEqual(game, expected)
        self.assertEqual(get(self.state("table"), "round"), nat(1))
        for seat in ("north", "south"):
            self.assertEqual((get(self.state(seat), "round"), get(self.state(seat), "digest")), (nat(1), label("")))
        card = self.turn("table", "receive", record(text=label(""), post=label(""), slot=label("")), principal="did:plc:zero")["offers"][0]["text"]
        print("--- table card ---\n" + card)
        self.assertTrue(card.endswith("-.+..-+...-\n"), card)    # row 10: the attractor moved from x=4 to x=2
        self.assertIn("\n-.+..-+...-\n-...+-+...-\n", card)      # row 0 likewise
        self.assertEqual(self.reason(self.turn("north", "next", principal=NORTH)), "Only the table moves the round.")


if __name__ == "__main__":
    unittest.main()
