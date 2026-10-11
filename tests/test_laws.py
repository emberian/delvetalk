"""The world's objects carry their laws in source: only owners change a record's doors and admit anthology
lines, and Tide's law refuse what their code would.

Evidence for FOUNDATION §4 (layer: objects).

Laws in source on the objects.

Policy: `owner: unchanged(owner) and request.subject == new.owner` (it has no `describe`, which an older law admitted).
The commonplace (a Record): only its owner hangs or removes a door. Anthology: anyone submits, only its owner admits.
Each is made with world-create (a lawful module cannot be imported by a creator) by its owner (a law
must admit an amendment by its installer).

Tide's law text (`tooSoon`), which the host runs on a kind-0 write. The test writes through a
variant of the package whose method skips the Bend-side checks the real one makes; the refusal's
clause is the law's ("tooSoon").

Refuted by: a stranger's door, undoor or admit committing; an owner's being refused; a stranger's
submit being refused; the variants committing once the host runs predicates.
"""
import unittest

from deploy import genesis
from tests.test_turn_world import TurnWorld
from tests.wire import cast_refusal, field, label, nat, record, reference, relation, result_label, rows
from tests.bend import closure

OWNER, OTHER = "did:plc:inkling", "did:plc:kimik3"


def cite(name):
    return record(label=label(name), to=reference(name), description=label("a " + name), examples={"tag": "list", "items": []})


def commonplace_seed(owner):
    return record(owner=label(owner), keeper=label(owner), keeperHandle=label(""), head=label("THE COMMONPLACE"))


def anthology_seed(owner, handle=""):
    return record(owner=label(owner), keeper=label(owner), keeperHandle=label(handle), head=label("THE ANTHOLOGY"))


def heard(text):
    return record(text=label(text), post=label(""))


class LawWorld(TurnWorld):
    def create(self, name, modules, seed, by=OWNER, law=None):
        r = self.host.send(op="world-create", principal=by, identity="mk-" + name, object=name,
                           modules=modules, entry="initial", seed=seed, **({"law": law} if law else {}))
        self.assertEqual(r["status"], "created", r)
        return r

    def version(self, name):
        return self.host.send(op="world-view", principal=OWNER, object=name)["version"]

    def state(self, name):
        return self.host.send(op="world-view", principal=OWNER, object=name)["state"]

    def clause(self, reply):
        if reply["status"] != "refused":
            return reply["status"]
        outcome = reply["receipt"]["outcome"]
        return outcome["class"] + "/" + outcome.get("clause", "")


class Laws(LawWorld):

    def test_only_the_commonplaces_owner_hangs_or_removes_a_door(self):
        self.create("commonplace", closure("Record"), commonplace_seed(OWNER), law=genesis.RECORD_LAW)
        hang = lambda name, who: self.turn("commonplace", "door", record(label=label(name), to=label(name)), principal=who)
        self.assertEqual(hang("garden", OWNER)["result"]["label"], "done")
        refused = hang("bazaar", OTHER)
        self.assertEqual((refused["status"], refused["receipt"]["outcome"].get("writes", [])), ("refused", []), refused)
        self.assertEqual(cast_refusal(refused)[0], "notOwner", refused)
        gone = self.turn("commonplace", "undoor", record(label=label("garden")), principal=OTHER)
        self.assertEqual(cast_refusal(gone)[0], "notOwner", gone)
        self.assertEqual(self.version("commonplace"), 1)
        self.assertEqual(self.turn("commonplace", "undoor", record(label=label("garden")), principal=OWNER)["result"]["label"], "done")
        self.assertEqual(field(self.state("commonplace"), "cites")["items"], [])

    def test_a_record_installed_for_someone_else_has_no_amendment_clause(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-d2", object="d2", modules=closure("Record"),
                           entry="initial", seed=commonplace_seed(OWNER), law=genesis.RECORD_LAW)
        self.assertEqual(r["status"], "error", r)
        self.assertTrue(r["message"].startswith("law does not admit an amendment by its proposer ember: owner: "), r)

    def test_anyone_writes_and_only_the_keeper_admits(self):
        self.create("anthology", closure("Record"), anthology_seed(OWNER), law=genesis.RECORD_LAW)
        self.assertEqual(self.turn("anthology", "write", record(text=label("moths")), principal=OTHER)["status"], "admitted")
        spelled = self.turn("anthology", "receive", heard("delvetalk anthology write\ntext: lamps"), principal="did:plc:glm")
        self.assertEqual((spelled["status"], spelled["result"]), ("admitted", nat(2)), spelled)  # the method's own result: the line's number
        # A stranger's admit is refused by name in Bend, with the card; so is a line that is not there.
        stranger = self.turn("anthology", "admit", record(number=nat(1)), principal=OTHER)
        self.assertEqual(cast_refusal(stranger)[0], "notKeeper", stranger)
        missing = self.turn("anthology", "admit", record(number=nat(9)), principal=OWNER)
        self.assertEqual(cast_refusal(missing)[0], "noLine", missing)
        self.assertEqual(self.turn("anthology", "admit", record(number=nat(2)), principal=OWNER)["result"]["label"], "done")
        admitted = [field(p, "n") for p in rows(field(self.state("anthology"), "admitted"))]
        self.assertEqual(admitted, [nat(2)])
        card = self.turn("anthology", "receive", heard(""), principal=OWNER)["offers"][0]["text"]
        self.assertIn("#1 [pending] kimik3: moths\n#2 [admitted] glm: lamps\n", card)

    def test_a_line_keeps_its_number_after_the_oldest_is_dropped(self):
        """The anthology keeps its newest 128 lines, which fit the host's state bytes at 280
        four-byte characters each; past them the oldest goes and every other keeps its number, so
        `admit / number: N` copied from a card admits that line (codex objects 13)."""
        self.create("anthology", closure("Record"), anthology_seed(OWNER), law=genesis.RECORD_LAW)
        poet = "did:plc:" + "p" * 24
        for i in range(1, 130):
            r = self.turn("anthology", "write", record(text=label("%04d" % i + "\U0001f319" * 276)), principal=poet)
            self.assertEqual(r["status"], "admitted", (i, r.get("receipt", {}).get("outcome")))
        lines = rows(field(self.state("anthology"), "lines"))
        self.assertEqual((len(lines), field(lines[0], "text")["value"][:4]), (128, "0002"))
        gone = self.turn("anthology", "admit", record(number=nat(1)), principal=OWNER)
        self.assertEqual(result_label(gone), "refused", gone)
        self.assertEqual(self.turn("anthology", "admit", record(number=nat(2)), principal=OWNER)["result"]["label"], "done")
        self.assertEqual([field(p, "n") for p in rows(field(self.state("anthology"), "admitted"))], [nat(2)])

    def test_the_ninth_line_is_in_its_acknowledgement_and_a_page_reaches_it(self):
        """The card shows eight lines; a write is acknowledged with its own number and line
        whatever the card shows, and `lines / from: N` shows them from N (codex agent 7)."""
        self.create("anthology", closure("Record"), anthology_seed(OWNER), law=genesis.RECORD_LAW)
        for i in range(1, 10):
            r = self.turn("anthology", "write", record(text=label("line %d" % i)), principal=OTHER)
        ack = r["offers"][0]["text"]
        self.assertTrue(ack.startswith("#9 is written: line 9\n\n"), ack)
        self.assertIn("… and 1 more: delvetalk anthology lines / from: 9\n", ack)
        page = self.turn("anthology", "receive", heard("delvetalk anthology lines / from: 9"), principal=OWNER)
        text = page["offers"][0]["text"]
        self.assertIn("#9 [pending] kimik3: line 9\n", text)
        self.assertNotIn("#8 ", text)

TIDE_SEED = record(ticks=nat(0), last=nat(0), gap=nat(60))


def tide_variant():
    """Tide whose tick skips its own checks (only the owner's first, and the gap), so only the law stands."""
    with open("world/objects/Tide.obend") as handle:
        source = handle.read()
    check = "if context.caller != context.object && (context.principal != state.owner || state.ticks > 0n) then"
    gap = "else if state.ticks > 0n && context.clock < state.last + state.gap then"
    assert check in source and gap in source, "Tide changed: the variant no longer skips its checks"
    source = source.replace(check, "if false then", 1).replace(gap, "else if false then", 1)
    return closure("Tide", override={"Tide": source})


def record_variant():
    """Record whose admit skips the keeper check, so only the law text stands."""
    with open("world/objects/Record.obend") as handle:
        source = handle.read()
    check = 'if state.keeper == "" || context.principal != state.keeper then refused({clause: "notKeeper", reading: keeperReading(state, context)}, context) else admitting(state, input.number, context)'
    assert check in source, "Record changed: the variant no longer skips its checks"
    return closure("Record", override={"Record": source.replace(check, "admitting(state, input.number, context)", 1)})


class FixedFields(LawWorld):
    """With Edits derived from the State, every field is writable by a write record; the fields
    nothing may change are kept by the law (unchanged), so a forged write of one is refused."""

    def forged(self, obj, fields, change):
        keep = {"tag": "variant", "label": "keep", "payload": record()}
        version = self.host.send(op="world-view", principal=OWNER, object=obj)["version"]
        edits = {name: keep for name in fields}
        edits.update(change)
        return self.host.send(op="world-propose", principal=OTHER, identity="forged-" + obj,
                              roots=[{"object": obj, "version": version}], writes=[{"object": obj, "edits": [record(**edits)]}])

    def test_a_forged_gap_is_refused_by_the_tides_law(self):
        self.create("tide", closure("Tide"), TIDE_SEED)
        r = self.forged("tide", ("ticks", "last", "gap"), {"gap": {"tag": "variant", "label": "set", "payload": record(value=nat(0))}})
        self.assertEqual(self.clause(r), "lawRefused/gap", r)


class Predicates(LawWorld):

    def test_tides_law_refuses_a_tick_too_soon(self):
        self.create("tide", tide_variant(), TIDE_SEED)
        self.assertEqual(self.turn("tide", "tick", principal=OTHER)["status"], "admitted")
        self.assertEqual(self.clause(self.turn("tide", "tick", principal=OTHER)), "lawRefused/tooSoon")

    def test_records_law_refuses_a_strangers_admission(self):
        self.create("anthology", record_variant(), anthology_seed(OWNER), law=genesis.RECORD_LAW)
        self.assertEqual(self.turn("anthology", "write", record(text=label("moths")), principal=OTHER)["status"], "admitted")
        self.assertEqual(self.clause(self.turn("anthology", "admit", record(number=nat(1)), principal=OTHER)), "lawRefused/kept")
        self.assertEqual(self.turn("anthology", "admit", record(number=nat(1)), principal=OWNER)["result"]["label"], "done")


class NoStrangerAmends(LawWorld):
    """A law that admits anyone's write leaving the guarded fields unchanged must still admit
    only the owner's reprogram and amendment (kind 1 and 2 change no field)."""

    def test_garden_thing_and_commonplace_refuse_a_strangers_amendment(self):
        from tests.test_chain import town_garden
        town_garden(self.host.send, owner=OWNER)
        self.create("stone", closure("Thing"), record(owner=label(OWNER), name=label("stone"), description=label(""),
                                                      holder=reference(""), location=reference(""),
                                                      offer={"tag": "variant", "label": "none", "payload": record()}))
        self.create("dir", closure("Record"), commonplace_seed(OWNER), law=genesis.RECORD_LAW)
        for obj in ("garden", "stone", "dir"):
            version = self.version(obj)
            r = self.host.send(op="world-amend", principal=OTHER, identity="am-" + obj, object=obj, version=version,
                               law='law open: request.kind == 0 or request.subject == "%s"' % OTHER)
            self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "lawRefused"), (obj, r))
            mine = self.host.send(op="world-amend", principal=OWNER, identity="own-" + obj, object=obj, version=version,
                                  law='law owner: request.subject == new.owner')
            self.assertEqual(mine["status"], "admitted", (obj, mine))

if __name__ == "__main__":
    unittest.main()
