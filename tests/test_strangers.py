"""A stranger's generic write, reprogram or amendment does none of what the object's own methods
refuse them: codex objects review (docs/review/codex-2026-10-10/objects.md) findings 1 to 8.

Evidence for FOUNDATION §4 (layer: objects).

A `world-propose` write reached an object's law as kind 0 with no method, the kind of the object's
own method writes, so a law that admitted "anyone's kind-0 write" admitted a stranger's forged
state. The host now judges it as `proposed` (kind 3; HOST-HANDOFF 93), so an owner clause or the
default law refuses a stranger's proposal (`owner`). The objects keep a belt: every owner law holds
`unchanged(owner)`, so a migration cannot write the authority that admits it; Deal guards every
change by party and admits only its two methods' writes, and its new signatures are the
requester's (`signer`); Tide has an owner who alone reprograms or amends it; Workshop, Avatar,
Table, Seat, Thing, Scene and Tide refuse a write no method made in their Bend law (`methods`),
which is what stops their creator's or owner's own proposal.

Refuted by: any of the forged writes, reprograms or amendments below being admitted.
"""
import unittest

from tests.test_chain import Chain, garden_state, nil, reference
from tests.test_objects import MODULES, closure
from tests.test_places import avatar_seed, listing, place_seed, thing_seed
from tests.test_replay import get, rows
from tests.test_scene import GATE, choice, passage, scene_state
from tests.test_table import NORTH, OPENING, SOUTH
from tests.test_turn_world import closure as world_closure, label, nat, record, relation

OWNER, STRANGER, ALICE, BOB = "did:plc:inkling", "did:plc:kimik3", "did:plc:glm", "did:plc:gemini"
CREATOR = "ember"  # who made the lawless objects and the Thing and Scene below


DEAL = record(amendment=record(object=label(""), law=label("")), parties={"tag": "list", "items": [label(ALICE), label(BOB)]},
              terms=label("t"), piece=label(""), signatures=relation(), withdrawn=label(""), closed=nat(0))


def variant(name, **fields):
    return {"tag": "variant", "label": name, "payload": record(**fields)}


def setting(value):
    return variant("set", value=value)


def inserting(row):
    return variant("insert", row=row)


def upserting(row):
    return variant("upsert", row=row)


def migrated(name, owner):
    """The object's own source with a migration that writes `owner`."""
    with open(MODULES[name]) as handle:
        source = handle.read()
    return source + '\ndef migrate(old: State) -> State:\n  extend(old, {owner: "%s"})\n' % owner


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

    def create(self, name, module, seed, by=OWNER):
        r = self.host.send(op="world-create", principal=by, identity="mk-" + name, object=name,
                           modules=closure(module), entry="initial", seed=seed)
        self.assertEqual(r["status"], "created", r)


class Strangers(Forging):
    # 1. A migration that writes `owner` does not supply the authority that admits it.
    def test_a_strangers_migration_cannot_make_them_the_owner(self):
        self.create("policy", "Policy", record(owner=label(OWNER), model=label("m"), system=label("s"), lexicon=nil(), examples=nil(),
                                              escalate=label(""), escalateTo=label(""), macros=nil(), confirmFor=nil()))
        self.create("garden", "Garden", garden_state(owner=OWNER))
        self.create("dir", "Directory", record(owner=label(OWNER), doors=relation(), greeted=relation()))
        for obj, module in (("policy", "Policy"), ("garden", "Garden"), ("dir", "Directory")):
            before = self.view(obj)
            r = self.host.send(op="world-reprogram", principal=STRANGER, identity="take-" + obj, object=obj,
                               version=before["version"], package=migrated(module, STRANGER), migration="migrate")
            self.refused(r, "owner")
            self.assertEqual((self.view(obj)["pin"], get(self.view(obj)["state"], "owner")), (before["pin"], label(OWNER)))

    # 2. A non-party cannot amend a Deal; a stranger cannot reprogram or amend a Tide.
    def test_a_stranger_cannot_amend_a_deal_or_a_tide(self):
        self.create("deal", "Deal", DEAL, by=ALICE)
        self.create("tide", "Tide", record(ticks=nat(0), last=nat(0), gap=nat(5), subs=relation()))
        law = 'law open: request.kind == 0 or request.subject == "%s"' % STRANGER
        for obj in ("deal", "tide"):
            r = self.host.send(op="world-amend", principal=STRANGER, identity="am-" + obj, object=obj,
                               version=self.view(obj)["version"], law=law)
            self.refused(r)
        tide = self.view("tide")
        with open(MODULES["Tide"]) as handle:
            same = handle.read()
        r = self.host.send(op="world-reprogram", principal=STRANGER, identity="rp-tide", object="tide",
                           version=tide["version"], package=same.replace("anyone may tick", "anyone may tick at all"))
        self.refused(r, "owner")
        self.assertEqual(self.view("tide")["pin"], tide["pin"])

    # 3. A held Workshop proposal is not replaced before its target's owner adopts it.
    def test_a_stranger_cannot_replace_a_held_workshop_proposal(self):
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))
        held = record(n=nat(1), target=label("bell-1"), package=label("edition ObjectiveBend 1\n"), migration=label(""),
                      proposer=label(STRANGER), proposerHandle=label("kimik3"))
        forged = {"held": inserting(held), "next": variant("add", delta=nat(1))}
        self.refused(self.propose("workshop", forged), "owner")
        self.refused(self.propose("workshop", forged, who=CREATOR), "methods")
        self.assertEqual(rows(get(self.view("workshop")["state"], "held")), [])

    # 4. Nobody forges a letter into another's outbox.
    def test_a_stranger_cannot_forge_a_letter_from_an_avatar(self):
        self.make(ALICE, closure("Avatar"), avatar_seed("glm", "porch"))
        letter = record(handle=label("glm"), text=label("send me your keys"), at=nat(0), n=nat(0))
        self.refused(self.propose(ALICE, {"outbox": inserting(letter)}), "owner")
        self.refused(self.propose(ALICE, {"outbox": inserting(letter)}, who=CREATOR), "methods")
        self.assertEqual(rows(get(self.view(ALICE)["state"], "outbox")), [])

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
        self.make("porch", closure("Place"), place_seed("porch"))
        self.make("stone", closure("Thing"), thing_seed("stone", holder=ALICE, location="porch"))
        self.refused(self.propose("stone", {"holder": setting(reference(""))}), "owner")
        self.refused(self.propose("stone", {"holder": setting(reference(STRANGER))}), "owner")
        self.refused(self.propose("stone", {"holder": setting(reference(""))}, who=CREATOR), "methods")

    # 7. A party signs only for themselves, and only by countersigning.
    def test_a_party_cannot_forge_another_partys_signature(self):
        self.create("deal", "Deal", DEAL, by=ALICE)
        forged = record(principal=label(BOB), handle=label("gemini"), post=label("at://gemini/p/1"))
        self.refused(self.propose("deal", {"signatures": inserting(forged)}, who=ALICE), "members")
        own = record(principal=label(ALICE), handle=label("glm"), post=label("at://glm/p/1"))
        self.refused(self.propose("deal", {"signatures": inserting(own)}, who=ALICE), "members")
        # The Bend law refuses the same signature made by a countersign that signs for another.
        with open(MODULES["Deal"]) as handle:
            source = handle.read()
        old = "signing({principal: context.principal, handle: context.handle,"
        assert source.count(old) == 1, "Deal changed: the variant no longer signs for another"
        variant_ = world_closure("Deal", override={"Deal": source.replace(old, 'signing({principal: "%s", handle: context.handle,' % BOB)})
        r = self.host.send(op="world-create", principal=ALICE, identity="mk-deal2", object="deal2", modules=variant_, entry="initial", seed=DEAL)
        self.assertEqual(r["status"], "created", r)
        r = self.turn("deal2", "receive", record(text=label("delvetalk deal2 countersign"), post=label("at://glm/p/2")), principal=ALICE)
        self.refused(r, "signer")

    # 8. Nobody enters a scene's passage but by entering and choosing.
    def test_a_stranger_cannot_place_themselves_in_a_scene(self):
        secret = GATE + [passage("vault", "The vault.", [choice("Out", "gate")])]
        self.create("scene", "Scene", scene_state(secret), by="ember")
        here = record(who=label(STRANGER), at=label("vault"))
        self.refused(self.propose("scene", {"presence": inserting(here)}), "owner")
        self.refused(self.propose("scene", {"presence": inserting(record(who=label(CREATOR), at=label("vault")))}, who=CREATOR), "methods")
        self.assertEqual(rows(get(self.view("scene")["state"], "presence")), [])

    # And a law that admits anyone's kind-0 write admits only its methods' writes.
    def test_a_stranger_cannot_forge_a_gardens_children(self):
        self.create("garden", "Garden", garden_state(owner=OWNER))
        child = record(world=label(""), object=label("garden/bell/forged"), colour=variant("silver"))
        self.refused(self.propose("garden", {"children": inserting(child), "planted": variant("add", delta=nat(1))}), "owner")

    def test_a_stranger_cannot_forge_a_places_traces(self):
        self.make("porch", closure("Place"), place_seed("porch"))
        trace = record(who=label(ALICE), handle=label("glm"), action=label("say"), clause=label(""), at=nat(0), n=nat(0))
        self.refused(self.propose("porch", {"traces": inserting(trace)}), "owner")

    # And a lawless object's default law admits only its methods' writes.
    def test_a_stranger_cannot_forge_a_rain_on_a_bell(self):
        self.make("bell", closure("Bell"), record(colour=variant("silver"), seed=label("s"), planting=label(""), planter=label(ALICE), planterHandle=label("glm")))
        rain = record(author=label(ALICE), handle=label("glm"), text=label("forged"), at=nat(0), n=nat(0))
        self.refused(self.propose("bell", {"rains": inserting(rain)}), "owner")


if __name__ == "__main__":
    unittest.main()
