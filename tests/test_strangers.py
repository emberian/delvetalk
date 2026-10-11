"""A stranger's generic write, reprogram or amendment does none of what the object's own methods
refuse them: codex objects review (docs/review/codex-2026-10-10/objects.md) findings 1 to 8.

Evidence for FOUNDATION §4 (layer: objects).

A `world-propose` write reached an object's law as kind 0 with no method, the kind of the object's
own method writes, so a law that admitted "anyone's kind-0 write" admitted a stranger's forged
state. The host now judges it as `proposed` (kind 3; HOST-HANDOFF 93), so an owner clause or the
default law refuses a stranger's proposal (`owner`). The objects keep a belt: every owner law holds
`unchanged(owner)`, so a migration cannot write the authority that admits it (a bond's
countersignatures are the signer's own: tests/test_bond.py); Tide has an owner who alone
reprograms or amends it; Workshop, Avatar,
Table, Seat, Thing and Tide refuse a write no method made in their Bend law (`methods`),
which is what stops their creator's or owner's own proposal.

Refuted by: any of the forged writes, reprograms or amendments below being admitted.
"""
import unittest

from deploy import genesis

from tests.test_chain import Chain, town_garden
from tests.wire import field, nil, reference, rows
from tests.bend import MODULES, closure
from tests.test_rooms import body, make_room, avatar_seed, room_seed, thing_seed
from tests.test_scene import GATE, choice, passage, scene_fields
from tests.test_table import NORTH, OPENING, SOUTH
from tests.wire import field, label, listing, nat, nil, record, reference, relation, rows, variant
from tests.bend import MODULES, closure

OWNER, STRANGER, ALICE, BOB = "did:plc:inkling", "did:plc:kimik3", "did:plc:glm", "did:plc:gemini"
CREATOR = "ember"  # who made the lawless objects and the Thing below


def setting(value):
    return variant("set", value=value)


def inserting(row):
    return variant("insert", row=row)


def migrated(name, owner):
    """The object's own source with a migration that writes `owner`."""
    with open(MODULES[name]) as handle:
        source = handle.read()
    return source + '\ndef takeOwner(old: State) -> State:\n  extend(old, {owner: "%s"})\n' % owner


class Forging(Chain):
    def view(self, obj):
        v = self.host.send(op="world-view", principal=OWNER, object=obj)
        self.assertEqual(v["status"], "viewed", v)
        return v

    def propose(self, obj, edits, who=STRANGER):
        self.m = getattr(self, "m", 0) + 1
        return self.host.send(op="world-propose", principal=who, identity="forged-%d" % self.m,
                              roots=[{"object": obj, "version": self.view(obj)["version"]}],
                              writes=[{"object": obj, "edits": [record(**edits)]}])

    def refused(self, reply, clause=None):
        self.assertEqual(reply["status"], "refused", reply)
        out = reply["receipt"]["outcome"]
        self.assertEqual(out["class"], "lawRefused", out)
        if clause:
            self.assertEqual(out.get("clause"), clause, out)

    def create(self, name, module, seed, by=OWNER, law=None):
        r = self.host.send(op="world-create", principal=by, identity="mk-" + name, object=name,
                           modules=closure(module), entry="initial", seed=seed, **({"law": law} if law else {}))
        self.assertEqual(r["status"], "created", r)


class Strangers(Forging):
    # 1. A migration that writes `owner` does not supply the authority that admits it.
    def test_a_strangers_migration_cannot_make_them_the_owner(self):
        self.create("policy", "Policy", record(owner=label(OWNER), model=label("m"), examples=nil(), confirmFor=nil()))
        self.create("commonplace", "Record", record(owner=label(OWNER), keeper=label(OWNER)), law=genesis.RECORD_LAW)
        for obj, module in (("policy", "Policy"), ("commonplace", "Record")):
            before = self.view(obj)
            r = self.host.send(op="world-reprogram", principal=STRANGER, identity="take-" + obj, object=obj,
                               version=before["version"], package=migrated(module, STRANGER), migration="takeOwner")
            self.refused(r, "owner")
            self.assertEqual((self.view(obj)["pin"], field(self.view(obj)["state"], "owner")), (before["pin"], label(OWNER)))

    # 2. A stranger cannot amend a bond (its record's owner clause) nor reprogram or amend a Tide.
    def test_a_stranger_cannot_amend_a_bond_or_a_tide(self):
        r = self.host.send(op="world-create", principal=ALICE, identity="mk-deal", object="deal", modules=closure("Record"), entry="initial",
                           seed=record(owner=label(ALICE), fields=listing([record(name=label("parties"), value=label("glm gemini"))])),
                           law=genesis.RECORD_LAW + "\n" + genesis.SIGNER_LAW)
        self.assertEqual(r["status"], "created", r)
        r = self.host.send(op="world-reprogram", principal=ALICE, identity="body-deal", object="deal", version=0, package=body("bond"), mode="extend")
        self.assertEqual(r["status"], "admitted", r)
        self.create("tide", "Tide", record(ticks=nat(0), last=nat(0), gap=nat(60)))
        law = 'law open: request.kind == 0 or request.subject == "%s"' % STRANGER
        for obj in ("deal", "tide"):
            r = self.host.send(op="world-amend", principal=STRANGER, identity="am-" + obj, object=obj,
                               version=self.view(obj)["version"], law=law)
            self.refused(r)
        tide = self.view("tide")
        with open(MODULES["Tide"]) as handle:
            same = handle.read()
        r = self.host.send(op="world-reprogram", principal=STRANGER, identity="rp-tide", object="tide",
                           version=tide["version"], package=same.replace("kimik3's tide", "kimik3's edited tide"))
        self.refused(r, "owner")
        self.assertEqual(self.view("tide")["pin"], tide["pin"])

    # 3. A held Workshop proposal is not replaced before its target's owner adopts it.
    def test_a_stranger_cannot_replace_a_held_workshop_proposal(self):
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))
        held = record(n=nat(1), target=label("bell-1"), package=label("edition ObjectiveBend 1\n"), migration=label(""),
                      proposer=label(STRANGER), proposerHandle=label("kimik3"), name=label(""), intent=label(""))
        forged = {"held": inserting(held), "next": variant("add", delta=nat(1))}
        self.refused(self.propose("workshop", forged), "owner")
        self.refused(self.propose("workshop", forged, who=CREATOR), "methods")
        self.assertEqual(rows(field(self.view("workshop")["state"], "held")), [])

    # 4. Nobody forges a note into an avatar's inbox.
    def test_a_stranger_cannot_forge_a_note_into_an_avatar(self):
        self.make(ALICE, closure("Avatar"), avatar_seed("glm", "porch"))
        note = record(**{"from": label(CREATOR), "handle": label("glm"), "text": label("send me your keys"), "at": nat(0), "n": nat(0), "uri": label("")})
        self.refused(self.propose(ALICE, {"inbox": inserting(note)}), "owner")
        self.refused(self.propose(ALICE, {"inbox": inserting(note)}, who=CREATOR), "methods")
        self.assertEqual(rows(field(self.view(ALICE)["state"], "inbox")), [])

    # 5. Nobody writes a Table's outcome or a Seat's commitment but their methods.
    def test_a_stranger_cannot_settle_a_table_or_seal_a_seat(self):
        self.make("north", closure("Seat"), record(table=reference("table"), seat=nat(0), owner=label(NORTH), opponent=label(SOUTH), rival=reference("south")))
        game = record(board=nat(int(OPENING["board"])), automaton=nat(OPENING["automaton"]), marks=nat(0), status=nat(0), winner=nat(0))
        self.make("table", closure("Table"), record(owner=label("ember"), north=reference("north"), south=reference("south"), round=nat(0),
                                                    width=nat(11), height=nat(11), game=game))
        won = record(board=nat(int(OPENING["board"])), automaton=nat(OPENING["automaton"]), marks=nat(0), status=nat(0), winner=nat(2))
        for who, clause in ((STRANGER, "owner"), (CREATOR, "methods")):
            self.refused(self.propose("table", {"game": setting(won)}, who=who), clause)
        # The seat is made by its player, who still seals only by commit.
        for who, clause in ((SOUTH, "owner"), (NORTH, "methods")):
            self.refused(self.propose("north", {"digest": setting(label("0" * 64))}, who=who), clause)

    # 6. Custody moves only by the Thing's methods.
    def test_a_stranger_cannot_drop_or_take_a_held_thing(self):
        make_room(self, "porch", **room_seed("porch"))
        self.make("stone", closure("Thing"), thing_seed("stone", holder=ALICE, location="porch"))
        self.refused(self.propose("stone", {"holder": setting(reference(""))}), "owner")
        self.refused(self.propose("stone", {"holder": setting(reference(STRANGER))}), "owner")
        self.refused(self.propose("stone", {"holder": setting(reference(""))}, who=CREATOR), "methods")

    # 7. Nobody enters a room's passage but by entering and choosing: the record's law refuses a
    # stranger's proposal (`owner`), and the room's methods write presence only for the principal.
    def test_a_stranger_cannot_place_themselves_in_a_room(self):
        secret = GATE + [passage("vault", "The vault.", [choice("Out", "gate")])]
        make_room(self, "scene", **scene_fields(secret))
        here = record(who=label(STRANGER), handle=label(""), at=label("vault"))
        self.refused(self.propose("scene", {"presence": inserting(here)}), "owner")
        self.refused(self.propose("scene", {"presence": inserting(record(who=label(CREATOR), handle=label(""), at=label("vault")))}, who=CREATOR), "methods")
        self.assertEqual(rows(field(self.view("scene")["state"], "presence")), [])

    # And a law that admits anyone's kind-0 write, or a lawless object's default law, admits only its methods' writes.
    def test_a_stranger_cannot_forge_a_gardens_things_a_rooms_presence_or_a_bells_rain(self):
        town_garden(self.host.send, owner=OWNER)
        make_room(self, "porch", **room_seed("porch"))
        self.make("bell", closure("Bell"), record(colour=variant("silver"), seed=label("s"), planting=label(""), planter=label(ALICE), planterHandle=label("glm")))
        thing = record(world=label(""), object=label("garden/bell/forged"))
        presence = record(who=label(ALICE), handle=label(""), at=label(""))
        rain = record(author=label(ALICE), handle=label("glm"), verb=label(""), text=label("forged"), at=nat(0), n=nat(0))
        # The garden is made by its kind and judged by the kind's law, which it cites (`under "kind/garden"`): the
        # refusal names the cited clause.
        for obj, edits, clause in (("garden", {"things": inserting(thing)}, "owner"),
                                   ("porch", {"presence": inserting(presence)}, "owner"), ("bell", {"rains": inserting(rain)}, "owner")):
            self.refused(self.propose(obj, edits), clause)


if __name__ == "__main__":
    unittest.main()
