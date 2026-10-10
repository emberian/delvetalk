"""Laws in source (FOUNDATION section 2 and section 13's two tiers) on the objects.

Policy: `owner: (request.kind == 0 and request.method == "describe") or request.subject == new.owner`.
Directory: only its owner adds or removes a door. Anthology: anyone submits, only its owner admits.
Each is made with world-create (a lawful module cannot be imported by a creator) by its owner (a law
must admit an amendment by its installer).

Tide's and Wake's Bend predicates `law(old, new, request)`, which the host runs after the law text
admits a kind-0 write (lane/host4 14b5c89, merged in foundation 88b9534; before it these turns were
admitted). The tests write through a variant of the package whose method skips the Bend-side check
the real one makes (and, for Wake, whose law text admits any ordinary write, so only the predicate
stands); the refusal's clause is the predicate's: "self", "tooSoon", "owner".

Refuted by: a stranger's add, remove or admit committing; an owner's being refused; a stranger's
submit being refused; the variants committing once the host runs predicates."""
import unittest

from tests.test_chain import nil, reference
from tests.test_replay import get, items
from tests.test_turn_world import TurnWorld, closure, label, nat, record

OWNER, OTHER = "did:plc:inkling", "did:plc:kimik3"


def door(name):
    return record(label=label(name), description=label("a " + name), to=reference(name))


def heard(text):
    return record(text=label(text), post=label(""), slot=label(""))


class LawWorld(TurnWorld):
    def create(self, name, modules, seed, by=OWNER):
        r = self.host.send(op="world-create", principal=by, identity="mk-" + name, object=name,
                           modules=modules, entry="initial", seed=seed)
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
    def test_the_policy_law_is_the_one_the_handoff_named(self):
        self.create("policy", closure("Policy"), record(owner=label(OWNER), model=label("m"), system=label("s"),
                                                        lexicon=nil(), examples=nil(), escalate=label(""), escalateTo=label(""), macros=nil(), confirmFor=nil()))
        law = self.host.send(op="world-inspect", principal=OWNER, object="policy")["law"]
        self.assertIn('law owner: ((request.kind == 0) and (request.method == "describe")) or (request.subject == new.owner)', law)
        r = self.turn("policy", "receive", heard("delvetalk policy set\nmodel: n"), principal=OWNER)
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "done"), r)

    def test_only_the_directorys_owner_adds_or_removes_a_door(self):
        self.create("dir", closure("Directory"), record(owner=label(OWNER), doors=nil(), greeted=nil()))
        self.assertEqual(self.turn("dir", "add", record(door=door("garden")), principal=OWNER)["status"], "admitted")
        self.assertEqual(self.clause(self.turn("dir", "add", record(door=door("bazaar")), principal=OTHER)), "lawRefused/owner")
        self.assertEqual(self.clause(self.turn("dir", "remove", record(label=label("garden")), principal=OTHER)), "lawRefused/owner")
        self.assertEqual(self.version("dir"), 1)
        self.assertEqual(self.turn("dir", "remove", record(label=label("garden")), principal=OWNER)["status"], "admitted")
        self.assertEqual(items(get(self.state("dir"), "doors")), [])

    def test_a_directory_installed_for_someone_else_has_no_amendment_clause(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-d2", object="d2", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label(OWNER), doors=nil(), greeted=nil()))
        self.assertEqual(r["status"], "error", r)
        self.assertTrue(r["message"].startswith("law does not admit an amendment by its proposer ember: owner: "), r)

    def test_anyone_submits_and_only_the_owner_admits(self):
        self.create("anthology", closure("Anthology"), record(owner=label(OWNER), proposals=nil()))
        self.assertEqual(self.turn("anthology", "submit", record(line=label("moths")), principal=OTHER)["status"], "admitted")
        spelled = self.turn("anthology", "receive", heard("delvetalk anthology submit\nline: lamps"), principal="did:plc:glm")
        self.assertEqual((spelled["status"], spelled["result"]["label"]), ("admitted", "done"), spelled)
        self.assertEqual(self.clause(self.turn("anthology", "admit", record(index=nat(0)), principal=OTHER)), "lawRefused/owner")
        self.assertEqual(self.turn("anthology", "admit", record(index=nat(1)), principal=OWNER)["status"], "admitted")
        statuses = [get(p, "status")["label"] for p in items(get(self.state("anthology"), "proposals"))]
        self.assertEqual(statuses, ["proposed", "admitted"])
        card = self.turn("anthology", "receive", heard(""), principal=OWNER)["offers"][0]["text"]
        self.assertTrue(card.startswith("Anthology, admitted by inkling (yours)\n#1 [proposed] kimik3: moths\n"), card)


TIDE_SEED = record(ticks=nat(0), last=nat(0), gap=nat(5), subs=nil())


def tide_variant():
    """Tide whose subscribe writes another principal's subscription and whose tick skips the gap."""
    with open("world/objects/Tide.obend") as handle:
        source = handle.read()
    source = source.replace("{who: context.principal, every: every,", '{who: "did:plc:someone-else", every: every,', 1)
    source = source.replace("if state.ticks > 0n && context.clock < state.last + state.gap then", "if false then", 1)
    return closure("Tide", override={"Tide": source})


def wake_variant():
    """Wake whose law text admits any ordinary write and whose watch skips the owner check."""
    with open("world/objects/Wake.obend") as handle:
        source = handle.read()
    source = source.replace('law owner "only its owner writes it": request.subject == new.owner', "law owner: request.kind == 0 or request.subject == new.owner", 1)
    source = source.replace("if context.principal != state.owner then then(notOwner(state)) else if Lists.length(state.triggers) < 32n",
                            "if Lists.length(state.triggers) < 32n", 1)
    return closure("Wake", override={"Wake": source})


class Predicates(LawWorld):
    def test_the_variants_differ_from_the_real_packages(self):
        self.assertNotEqual(tide_variant()[-1]["source"], closure("Tide")[-1]["source"])
        self.assertNotEqual(wake_variant()[-1]["source"], closure("Wake")[-1]["source"])

    def test_tides_predicate_refuses_someone_elses_subscription(self):
        self.create("tide", tide_variant(), TIDE_SEED)
        r = self.turn("tide", "subscribe", record(every=nat(1), note=label("wake me")), principal=OTHER)
        self.assertEqual(self.clause(r), "lawRefused/self", r)

    def test_tides_predicate_refuses_a_tick_too_soon(self):
        self.create("tide", tide_variant(), TIDE_SEED)
        self.assertEqual(self.turn("tide", "tick", principal=OTHER)["status"], "admitted")
        r = self.turn("tide", "tick", principal=OTHER)
        self.assertEqual(self.clause(r), "lawRefused/tooSoon", r)

    def test_wakes_predicate_refuses_a_strangers_trigger(self):
        self.create("wake/" + OWNER, wake_variant(), record(owner=label(OWNER), env=reference("env/" + OWNER), triggers=nil(), nextId=nat(1)))
        r = self.turn("wake/" + OWNER, "watch", record(event={"tag": "variant", "label": "keyword", "payload": record(term=label("x"))},
                                               action={"tag": "variant", "label": "notify", "payload": record()}), principal=OTHER)
        self.assertEqual(self.clause(r), "lawRefused/owner", r)

    def test_the_owners_own_writes_pass_both_tiers(self):
        self.create("wake/" + OWNER, wake_variant(), record(owner=label(OWNER), env=reference("env/" + OWNER), triggers=nil(), nextId=nat(1)))
        r = self.turn("wake/" + OWNER, "watch", record(event={"tag": "variant", "label": "keyword", "payload": record(term=label("x"))},
                                               action={"tag": "variant", "label": "notify", "payload": record()}), principal=OWNER)
        self.assertEqual(r["status"], "admitted", r)
        self.create("tide", closure("Tide"), TIDE_SEED)
        self.assertEqual(self.turn("tide", "subscribe", record(every=nat(1), note=label("me")), principal=OTHER)["status"], "admitted")


if __name__ == "__main__":
    unittest.main()


class NoStrangerAmends(LawWorld):
    """A law that admits anyone's write leaving the guarded fields unchanged must still admit
    only the owner's reprogram and amendment (kind 1 and 2 change no field)."""

    def test_garden_thing_and_directory_refuse_a_strangers_amendment(self):
        from tests.test_chain import garden_state
        self.create("garden", closure("Garden"), garden_state(owner=OWNER))
        self.create("stone", closure("Thing"), record(owner=label(OWNER), name=label("stone"), description=label(""),
                                                      holder=reference(""), location=reference(""),
                                                      offer={"tag": "variant", "label": "none", "payload": record()}))
        self.create("dir", closure("Directory"), record(owner=label(OWNER), doors=nil(), greeted=nil()))
        for obj in ("garden", "stone", "dir"):
            version = self.version(obj)
            r = self.host.send(op="world-amend", principal=OTHER, identity="am-" + obj, object=obj, version=version,
                               law='law open: request.kind == 0 or request.subject == "%s"' % OTHER)
            self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "lawRefused"), (obj, r))
            mine = self.host.send(op="world-amend", principal=OWNER, identity="own-" + obj, object=obj, version=version,
                                  law='law owner: request.subject == new.owner')
            self.assertEqual(mine["status"], "admitted", (obj, mine))
