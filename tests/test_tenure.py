"""Tenure: a thing's owner keeps it, whatever its kind's owner writes, and a rule a thing inherits lends nobody's
authority (docs/review/astra-2026-10-12/world.md findings 1, 2, 3). A fresh genesis, three residents casting spells
by `receive` as the bridge does, and the owner's ops (`world-amend`, `world-propose`) as the transport sends them.

Evidence for FOUNDATION §4 (a thing's own text holds its owner's law; `under` adds to it, never replaces it, and
never refuses the owner's amendment) and §10 (a rule a thing inherits acts as the thing itself) (layer: objects).
Refuted by: a kind's law line that lets a stranger amend or propose on another's thing; a kind owner's amendment
that keeps an instance's owner from amending their own thing, or that lets a stranger in; resident code run by an
inherited rule under the kind owner's name.
"""
import tempfile
import unittest

from deploy import genesis
from tests.town import Town
from tests.wire import label, record

YUE, KES, GLM = "did:plc:yueyueyueyueyueyueyueyue", "did:plc:kestrelkestrelkestrelkes", "did:plc:glmglmglmglmglmglmglmglm"


def told(reply):
    return "".join(o.get("text", "") for o in reply.get("offers") or []) or reply.get("text", "")


def outcome(reply):
    return (reply.get("receipt") or {}).get("outcome") or {}


# A kind of record whose things toll at their first line: the kind's rule, and a body giving `toll`.
CHIME = """delvetalk kinds make / name: chime / of: record
law: <<END
rule toll "tolls at its first line": count(new.lines) >= 1 and count(old.lines) <= 0 then delvetalk {request.object} toll
END
body: <<BEND
form toll:
def toll(state: State, context: Abi.Context) -> Activity<Nat>:
  Super.inscribe(state, "toll", "tolled by {context.principal}", context)
BEND"""
# A resident's kind over the chime whose `toll` reaches for the chime's owner's record: run under the chime owner's
# name it would hang a door there, which only that owner may.
GRAB = """delvetalk kinds make / name: grab / of: kind/chime
body: <<BEND
import ./Card.obend as Card
import ./Plan.obend as Plans
import ./World.obend as World
form toll:
def toll(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.call::<Card.Replied>({object: {world: context.world, object: "yrec/1"}, method: "door", argument: {label: "grabbed", to: "commonplace"}}):
    case _: Super.inscribe(state, "toll", "grabbed by {context.principal}", context)
BEND"""


class Tenure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.n = 0
        for did, handle in ((YUE, "yue.delve.town"), (KES, "kestrel.delve.town"), (GLM, "glm.delve.town")):
            cls.town.send(op="world-arrive", principal="transport", did=did, handle=handle)

    def ident(self):
        type(self).n += 1
        return "tenure-%d" % self.n

    def say(self, who, card, text):
        return self.town.send(op="world-turn", principal=who, object=card, method="receive", identity=self.ident(),
                              argument=record(text=label(text), post=label("")))

    def admitted(self, who, card, text):
        r = self.say(who, card, text)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def version(self, obj):
        return int(self.town.send(op="world-object", principal=YUE, object=obj)["record"]["version"])

    def amend(self, who, obj, law):
        return self.town.send(op="world-amend", principal=who, identity=self.ident(), object=obj, version=self.version(obj), law=law)

    def propose(self, who, obj, **fields):
        edits = record(**{k: {"tag": "variant", "label": "set", "payload": record(value=label(v))} for k, v in fields.items()})
        return self.town.send(op="world-propose", principal=who, identity=self.ident(), roots=[{"object": obj, "version": self.version(obj)}],
                              writes=[{"object": obj, "edits": [edits]}])

    def made(self, reply):
        """The id a make made: the one object its entry created."""
        [created] = [c["object"] for c in outcome(reply).get("creates") or []]
        return created

    def law(self, obj):
        return self.town.send(op="world-object", principal=YUE, object=obj)["record"]["law"]

    def lines(self, obj):
        state = self.town.send(op="world-view", principal=YUE, object=obj)["state"]
        rows = next(f["value"] for f in state["fields"] if f["name"] == "lines")["payload"]["fields"][0]["value"]["items"]
        return [{f["name"]: f["value"].get("value") for f in r["fields"]} for r in rows]

    # Finding 3: a kind made with one law line of its maker's holds its things to it beside their owner's law.
    def test_a_kinds_law_line_adds_to_its_things_owner_law_and_never_replaces_it(self):
        self.admitted(YUE, "kinds", 'delvetalk kinds make / name: small / of: record\nlaw: law small "seven lines maximum": count(new.lines) <= 7')
        thing = self.made(self.admitted(KES, "kind/small", "delvetalk kind/small make"))
        # A stranger (the kind's own maker among them) neither amends, nor proposes a keeper, nor hangs a door.
        for who in (YUE, GLM):
            r = self.amend(who, thing, 'law mine "mine now": request.subject == "%s"' % who)
            self.assertEqual((r["status"], outcome(r).get("class")), ("refused", "lawRefused"), r)
            r = self.propose(who, thing, keeper=who)
            self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "owner"), r)
        self.assertTrue(self.law(thing).startswith(genesis.RECORD_LAW), self.law(thing))
        # The kind's line holds beside it: seven lines, and the eighth refused by the kind's clause.
        for i in range(7):
            self.admitted(GLM if i % 2 else KES, thing, "delvetalk %s write / text: line %d" % (thing, i))
        r = self.say(KES, thing, "delvetalk %s write / text: the eighth" % thing)
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "small"), r)
        # Its owner amends it, and the kind still holds.
        self.assertEqual(self.amend(KES, thing, self.law(thing) + '\nlaw quiet "no proposals": not (request.kind == proposed)')["status"], "admitted")

    # Finding 2: the kind's owner rewrites the text its things follow; the things' owners keep them.
    def test_a_kind_owner_neither_locks_an_owner_out_of_their_thing_nor_lets_a_stranger_in(self):
        self.admitted(YUE, "kinds", "delvetalk kinds make / name: bound / of: record")
        first = self.made(self.admitted(KES, "kind/bound", "delvetalk kind/bound make"))
        second = self.made(self.admitted(KES, "kind/bound", "delvetalk kind/bound make"))
        # The kind's owner locks its things to themselves: the kind's text binds them while they follow it.
        self.assertEqual(self.propose(YUE, "kind/bound", law='law lock "only its maker": request.subject == "%s"' % YUE)["status"], "admitted")
        r = self.say(KES, first, "delvetalk %s write / text: mine" % first)
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "lock"), r)
        # Its owner amends it out from under the kind: their own law, without the citation; then it is theirs again.
        own = self.law(first).split('\nlaw kind ')[0]
        self.assertEqual(self.amend(KES, first, own)["status"], "admitted")
        self.admitted(KES, first, "delvetalk %s write / text: mine again" % first)
        # The kind's owner opens the kind's text to anything: a stranger still neither amends nor proposes on the
        # thing that follows it, since its owner's law is its own.
        self.assertEqual(self.propose(YUE, "kind/bound", law='law open "anything": request.height >= 0')["status"], "admitted")
        r = self.amend(GLM, second, 'law mine "mine now": request.subject == "%s"' % GLM)
        self.assertEqual((r["status"], outcome(r).get("class")), ("refused", "lawRefused"), r)
        r = self.propose(YUE, second, keeper=YUE)
        self.assertEqual((r["status"], outcome(r).get("clause")), ("refused", "owner"), r)

    # Finding 1: a rule a thing inherits acts as the thing itself, so resident code it runs wields no person's name.
    def test_a_rule_a_thing_inherits_acts_as_the_thing_and_lends_its_kind_owner_nothing(self):
        yrec = self.made(self.admitted(YUE, "kind/record", "delvetalk kind/record make"))
        self.admitted(YUE, "kinds", CHIME)
        chime = self.made(self.admitted(KES, "kind/chime", "delvetalk kind/chime make"))
        first = self.admitted(GLM, chime, "delvetalk %s write / text: the first" % chime)
        [fired] = first["receipt"]["fired"]
        self.assertEqual((fired["rule"], fired["principal"]), ("toll", "@" + chime), fired)
        self.assertEqual([l["text"] for l in self.lines(chime)][-1], "tolled by @" + chime)
        # A resident's kind over the chime overrides `toll` to reach for YUE's record; the kind's rule runs it as the
        # thing, which may not hang a door there, and YUE's record is as it was.
        self.admitted(KES, "kinds", GRAB.replace("yrec/1", yrec))
        grab = self.made(self.admitted(KES, "kind/grab", "delvetalk kind/grab make"))
        self.admitted(GLM, grab, "delvetalk %s write / text: the first" % grab)
        self.assertEqual([l["text"] for l in self.lines(grab)][-1], "grabbed by @" + grab)
        state = self.town.send(op="world-view", principal=YUE, object=yrec)["state"]
        cites = next(f["value"] for f in state["fields"] if f["name"] == "cites")
        self.assertEqual(cites.get("items"), [], cites)


if __name__ == "__main__":
    unittest.main()
