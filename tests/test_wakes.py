"""Env, Wake and Tide, the cards the town designed: senses owned by their DID, triggers only their
owner changes, a tide never too soon.

Evidence for FOUNDATION §8 claims (layer: objects).

The cards the town designed in reply to ember's status post: Env (inkling's senses),
Wake (mimo's reflex arc) and Tide (kimik3's cadence). Each declares its law in source,
so each is made with world-create and its whole state (a creator cannot import a module
that declares a law). Env and Wake are made by their owner: a law must admit an amendment
by the one who installs it, and theirs admit only the owner.
"""
import unittest

from tests.test_chain import Chain, boolean, nil, reference
from tests.test_objects import closure
from tests.test_places import avatar_seed
from tests.test_replay import get, items, relation, rows
from tests.test_turn_world import label, nat, record

OWNER, OTHER = "did:plc:inkling", "did:plc:kimik3"


def variant(tag, **fields):
    return {"tag": "variant", "label": tag, "payload": record(**fields)}


def event(kind="mention", actor="did:plc:mimo", text="hello", reply_to=""):
    return record(kind=label(kind), actor=label(actor), uri=label("at://x/p/1"), cid=label("bafy"), text=label(text),
                  replyTo=label(reply_to), at=nat(0), handle=label(""))


def heard(text):
    return record(text=label(text), post=label("at://p/1"))


class Wakes(Chain):

    def create(self, name, module, state, by="ember"):
        r = self.host.send(op="world-create", principal=by, identity="mk-" + name, object=name,
                           modules=closure(module), entry="initial", seed=state)
        self.assertEqual(r["status"], "created", r)

    def env(self):
        self.create("env/" + OWNER, "Env", record(owner=label(OWNER), buffer=relation(), seen=nat(0)), by=OWNER)
        return "env/" + OWNER

    def wake(self):
        # A Wake lives at wake/<owner>; the bare id `wake` is reserved (each speaker's own).
        self.create("wake/" + OWNER, "Wake", record(owner=label(OWNER), env=reference("env/" + OWNER), triggers=nil(), nextId=nat(1)), by=OWNER)
        return "wake/" + OWNER

    def avatar(self, did):
        self.make(did, closure("Avatar"), avatar_seed(Card_handle(did), "porch"))

    def inbox(self, did):
        return [(get(n, "from")["value"], get(n, "text")["value"]) for n in rows(get(self.state(did), "inbox"))]

    def label_of(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        return reply["result"]["label"]

    def version(self, name):
        return self.host.send(op="world-view", principal="ember", object=name)["version"]

    # --- Env -------------------------------------------------------------------------

    def test_env_publish_is_the_owners_and_observe_changes_nothing(self):
        env = self.env()
        self.assertEqual(self.label_of(self.turn(env, "publish", record(event=event()), principal=OTHER)), "refused")
        self.assertEqual(self.version(env), 0)
        first = self.turn(env, "publish", record(event=event(text="one")), principal=OWNER)
        self.assertEqual(self.label_of(first), "done")
        self.turn(env, "publish", record(event=event(kind="reply", text="two", reply_to="at://x/p/0")), principal=OWNER)
        buffer = rows(get(self.state(env), "buffer"))
        self.assertEqual([get(e, "text")["value"] for e in buffer], ["one", "two"])
        heights = [int(get(e, "at")["value"]) for e in buffer]
        self.assertLess(heights[0], heights[1])          # `at` is the host's height, not the client's 0
        before = self.version(env)
        look = self.turn(env, "observe", principal=OTHER)
        self.assertEqual(look["result"], nat(2))
        card = look["offers"][0]["text"]
        self.assertEqual(card, "ENV of inkling: 2 new since #0.\n")
        self.assertIn("2 new since #0", card)
        self.assertEqual(self.version(env), before)
        # The mark moves only by the owner's seen, and only forward.
        self.assertEqual(self.label_of(self.turn(env, "seen", record(at=nat(heights[0])), principal=OTHER)), "refused")
        self.assertEqual(self.label_of(self.turn(env, "seen", record(at=nat(heights[0])), principal=OWNER)), "done")
        self.assertEqual(self.turn(env, "observe", principal=OTHER)["result"], nat(1))
        back = self.turn(env, "seen", record(at=nat(0)), principal=OWNER)
        self.assertEqual(self.label_of(back), "refused")

    def test_an_env_is_named_by_its_did_in_a_spell_and_lives_at_env_slash_did(self):
        env = self.env()
        self.turn(env, "publish", record(event=event(text="one")), principal=OWNER)
        at = int(get(rows(get(self.state(env), "buffer"))[0], "at")["value"])
        r = self.turn(env, "receive", heard("delvetalk env/%s seen\nat: %d" % (OWNER, at)), principal=OWNER)
        self.assertEqual(self.label_of(r), "done")
        self.assertEqual(get(self.state(env), "seen"), nat(at))
        self.assertIn("    delvetalk env/did:plc:inkling seen\n", self.turn(env, "receive", heard(""), principal=OTHER)["offers"][0]["text"])
        # An env made at any other id takes nothing in.
        self.create("env/elsewhere", "Env", record(owner=label(OWNER), buffer=relation(), seen=nat(0)), by=OWNER)
        r = self.turn("env/elsewhere", "publish", record(event=event()), principal=OWNER)
        fields = {f["name"]: f["value"] for f in r["result"]["payload"]["fields"]}
        self.assertEqual(fields, {"clause": label("misplaced"), "reading": label("An env lives at env/did:plc:inkling")})
        self.assertEqual(self.version("env/elsewhere"), 0)

    def test_the_opener_creates_an_env_for_its_owner_who_alone_may_amend_it(self):
        """Rehearsal finding 10: genesis seeds each principal's Env as the world's opener."""
        self.assertEqual(self.host.send(op="world-open", path=self.path, opener="ember")["status"], "opened")
        seed = record(owner=label(OWNER), buffer=relation(), seen=nat(0))
        create = lambda by, ident: self.host.send(op="world-create", principal=by, identity=ident, object="env/" + OWNER,
                                                  modules=closure("Env"), entry="initial", seed=seed, owner=OWNER)
        stranger = create("mallory", "mk-m")
        self.assertEqual(stranger, {"status": "error", "message": "only the opener of the world may name an owner; that is ember"})
        made = create("ember", "mk-env")
        self.assertEqual(made["status"], "created", made)
        self.assertEqual((made["receipt"]["identity"]["principal"], made["receipt"]["outcome"]["owner"]), ("ember", OWNER))
        law = self.host.send(op="world-inspect", principal=OWNER, object="env/" + OWNER)["law"]
        amend = lambda by, ident: self.host.send(op="world-amend", principal=by, identity=ident, object="env/" + OWNER,
                                                 version=self.version("env/" + OWNER), law=law)
        refused = amend(OTHER, "am-other")
        self.assertEqual((refused["status"], refused["receipt"]["outcome"]["clause"]), ("refused", "owner"), refused)
        self.assertEqual(amend("ember", "am-ember")["status"], "refused")
        self.assertEqual(amend(OWNER, "am-owner")["status"], "admitted")
        # A seed that leaves `owner` out gets the named owner.
        other = self.host.send(op="world-create", principal="ember", identity="mk-other", object="env/" + OTHER,
                                modules=closure("Env"), entry="initial", seed=record(), owner=OTHER)
        self.assertEqual(other["status"], "created", other)
        self.assertEqual(get(self.state("env/" + OTHER), "owner"), label(OTHER))
        self.reopen()
        self.assertEqual(self.version("env/" + OWNER), 1)
        self.assertEqual(self.host.send(op="world-open", path=self.path, opener="glm")["status"], "error")

    def test_each_principal_creates_and_amends_their_own_env_and_wake(self):
        """Rehearsal finding 10: Env and Wake belong to their principal from creation (GENESIS):
        the owner creates them and may amend their laws; ember cannot seed them for another."""
        env = self.env()
        wake = self.wake()
        for obj in (env, wake):
            version = self.version(obj)
            r = self.host.send(op="world-amend", principal=OWNER, identity="am-" + obj, object=obj, version=version,
                               law="law owner: request.subject == new.owner")
            self.assertEqual(r["status"], "admitted", (obj, r))
            r = self.host.send(op="world-amend", principal=OTHER, identity="steal-" + obj, object=obj, version=version + 1,
                               law="law open: request.kind == 0 or request.subject == \"%s\"" % OTHER)
            self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "lawRefused"), (obj, r))
        r = self.host.send(op="world-create", principal="ember", identity="mk-w2", object="wake/x", modules=closure("Wake"), entry="initial",
                           seed=record(owner=label(OWNER), env=reference("env/" + OWNER), triggers=nil(), nextId=nat(1)))
        self.assertEqual(r["status"], "error", r)
        self.assertTrue(r["message"].startswith("law does not admit an amendment by its proposer ember: "), r)

    def test_an_env_installed_by_someone_else_is_refused_for_want_of_an_amendment_clause(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-x", object="env/x", modules=closure("Env"),
                           entry="initial", seed=record(owner=label(OWNER), buffer=relation(), seen=nat(0)))
        self.assertEqual(r["status"], "error", r)
        self.assertTrue(r["message"].startswith("law does not admit an amendment by its proposer ember: owner: "), r)

    def test_env_law_refuses_a_strangers_write_proposed_directly(self):
        env = self.env()
        keep = lambda: variant("keep")
        r = self.host.send(op="world-propose", principal=OTHER, identity="forged", roots=[{"object": env, "version": 0}],
                           writes=[{"object": env, "edits": [record(buffer=keep(), seen=variant("set", value=nat(9)))]}])
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"], r["receipt"]["outcome"].get("clause")),
                         ("refused", "lawRefused", "owner"), r)

    def test_env_publishes_to_wake_and_a_mention_notes_the_owners_avatar(self):
        env, wake = self.env(), self.wake()
        self.avatar(OWNER)
        # A trigger on an event subscribes the wake to its env's buffer.
        watch = self.turn(wake, "watch", record(event=variant("mention", actor=label("did:plc:mimo")), action=variant("notify")), principal=OWNER)
        self.assertEqual((self.label_of(watch), get(watch["result"]["payload"], "id")), ("watching", nat(1)))
        self.turn(env, "publish", record(event=event(actor="did:plc:mimo", text="are you awake?")), principal=OWNER)
        self.turn(env, "publish", record(event=event(actor="did:plc:zero", text="not for you")), principal=OWNER)
        self.deliver_all()
        self.assertEqual(self.inbox(OWNER), [(OWNER, "mention from mimo: are you awake?")])

    # --- Wake ------------------------------------------------------------------------

    def test_wake_triggers_are_the_owners_and_unwatch_finds_the_index_by_id(self):
        wake = self.wake()
        self.assertEqual(self.label_of(self.turn(wake, "watch", record(event=variant("keyword", term=label("moth")), action=variant("notify")), principal=OTHER)), "refused")
        for term in ("moth", "bell", "gate"):
            self.turn(wake, "watch", record(event=variant("keyword", term=label(term)), action=variant("notify")), principal=OWNER)
        gone = self.turn(wake, "unwatch", record(id=nat(2)), principal=OWNER)
        self.assertEqual(self.label_of(gone), "watching")
        ids = [get(t, "id") for t in items(get(self.state(wake), "triggers"))]
        self.assertEqual(ids, [nat(1), nat(3)])
        self.assertEqual(self.label_of(self.turn(wake, "unwatch", record(id=nat(2)), principal=OWNER)), "refused")
        # From a post: the owner's spell adds a trigger; a stranger's is refused.
        self.assertEqual(self.label_of(self.turn(wake, "receive", heard("delvetalk %s keyword\nterm: lantern" % wake), principal=OWNER)), "watching")
        stranger = self.turn(wake, "receive", heard("delvetalk %s keyword\nterm: x" % wake), principal=OTHER)
        self.assertEqual(self.label_of(stranger), "refused")
        card = self.turn(wake, "receive", heard(""), principal=OWNER)["offers"][0]["text"]
        self.assertEqual(card, (
            "WAKE of inkling (yours): 3 triggers. Add one: delvetalk wake mention / actor: <handle>, or delvetalk wake keyword / term: <word>; delvetalk wake unwatch / id: <number> removes it.\n"
            "#1 on the word moth: note me\n"
            "#3 on the word gate: note me\n"
            "#4 on the word lantern: note me\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk wake/did:plc:inkling mention\n"
            "    actor: <text, 1 to 128 characters>\n"
            "\n"
            "    delvetalk wake/did:plc:inkling keyword\n"
            "    term: <text, 1 to 64 characters>\n"
            "\n"
            "    delvetalk wake/did:plc:inkling unwatch\n"
            "    id: <a number from 1 to 1000000>\n"))
        self.assertIn("#4 on the word lantern: note me", card)
        # A stranger's card counts the triggers and shows none of them.
        seen = self.turn(wake, "receive", heard(""), principal=OTHER)["offers"][0]["text"]
        self.assertTrue(seen.startswith("WAKE of inkling: 3 triggers.\n"), seen)
        self.assertNotIn("lantern", seen)

    def test_a_keyword_inside_a_longer_text_fires_and_a_call_reaches_its_card(self):
        wake = self.wake()
        self.avatar(OWNER)
        self.avatar(OTHER)
        self.turn(wake, "watch", record(event=variant("keyword", term=label("moth")), action=variant("call", card=label(OTHER), method=label("note"))), principal=OWNER)
        fired = self.turn(wake, "sense", record(event=event(kind="post", text="the moths know the way")), principal=OWNER)
        self.assertEqual((self.label_of(fired), get(fired["result"]["payload"], "count")), ("fired", nat(1)))
        quiet = self.turn(wake, "sense", record(event=event(kind="post", text="mot h")), principal=OWNER)
        self.assertEqual(get(quiet["result"]["payload"], "count"), nat(0))
        self.deliver_all()
        self.assertEqual(self.inbox(OTHER), [(OWNER, "post from mimo: the moths know the way")])

    def triggers(self, wake):
        return [get(t, "id")["value"] for t in items(get(self.state(wake), "triggers"))]

    def test_a_schedule_recurs_every_n_clock_minutes_until_unwatched(self):
        """SEEDING §5: a schedule re-arms itself `every` minutes after it fires; each firing is the
        wake's own `due` turn, and unwatch ends it."""
        wake = self.wake()
        self.avatar(OWNER)
        r = self.turn(wake, "schedule", record(at=nat(0), every=nat(5), action=variant("notify")), principal=OWNER)
        self.assertEqual(self.label_of(r), "watching", r)
        self.deliver_all()
        self.assertEqual(self.triggers(wake), ["1"])
        self.host.send(op="world-advance", height=3)
        self.deliver_all()
        self.assertEqual(self.inbox(OWNER), [])
        for height in (6, 11, 16):   # an await until t resumes once the clock is past t
            self.host.send(op="world-advance", height=height)
            self.deliver_all()
        self.assertEqual(self.inbox(OWNER), [(OWNER, "scheduled at 5"), (OWNER, "scheduled at 10"), (OWNER, "scheduled at 15")])
        self.assertEqual(self.label_of(self.turn(wake, "unwatch", record(id=nat(1)), principal=OWNER)), "watching")
        self.host.send(op="world-advance", height=30)
        self.deliver_all()
        self.assertEqual(len(self.inbox(OWNER)), 3)
        # A forged `due` from the owner fires nothing: only the wake's own sends count.
        self.assertEqual(get(self.turn(wake, "due", record(id=nat(1), at=nat(31)), principal=OWNER)["result"]["payload"], "count"), nat(0))

    def test_a_clock_jump_fires_once_and_rearms_from_now(self):
        """Transport's clock is wall minutes: the first advance jumps by millions. Missed firings
        are not made up; the next is a period from the clock."""
        wake = self.wake()
        self.avatar(OWNER)
        self.turn(wake, "schedule", record(at=nat(0), every=nat(5), action=variant("notify")), principal=OWNER)
        self.deliver_all()
        self.host.send(op="world-advance", height=1000)
        self.deliver_all()
        self.assertEqual(self.inbox(OWNER), [(OWNER, "scheduled at 5")])
        self.host.send(op="world-advance", height=1006)
        self.deliver_all()
        self.assertEqual(self.inbox(OWNER), [(OWNER, "scheduled at 5"), (OWNER, "scheduled at 1005")])

    def test_a_once_schedule_fires_at_its_time_and_stands_down(self):
        wake = self.wake()
        self.avatar(OWNER)
        self.turn(wake, "schedule", record(at=nat(4), every=nat(0), action=variant("notify")), principal=OWNER)
        self.deliver_all()
        self.host.send(op="world-advance", height=6)
        self.deliver_all()
        self.assertEqual(self.inbox(OWNER), [(OWNER, "scheduled at 4")])
        self.assertEqual(self.triggers(wake), [])
        never = self.turn(wake, "schedule", record(at=nat(2), every=nat(0), action=variant("notify")), principal=OWNER)
        self.assertEqual(get(never["result"]["payload"], "clause"), label("never"))

    def test_a_wake_holds_at_most_eight_standing_schedules(self):
        wake = self.wake()
        for n in range(8):
            self.assertEqual(self.label_of(self.turn(wake, "schedule", record(at=nat(0), every=nat(60), action=variant("notify")), principal=OWNER)), "watching")
        ninth = self.turn(wake, "schedule", record(at=nat(0), every=nat(60), action=variant("notify")), principal=OWNER)
        self.assertEqual(get(ninth["result"]["payload"], "clause"), label("schedulesFull"))

    def test_the_flood_a_wake_hears_the_cistern_pass_forty(self):
        """SEEDING §4, the flood: the town pours, the level only rises (its law), and a wake
        watching `level` passing 40 acts once."""
        from deploy import genesis
        from tests.test_objects import run_pure
        law = run_pure("Cistern", "lawText", label("ember"))["value"]["value"]
        self.assertEqual(law, genesis.cistern_law("ember"))   # genesis passes the package's own law
        self.create("cistern", "Cistern", record(level=nat(0)))
        amended = self.host.send(op="world-amend", principal="ember", identity="cistern-law", object="cistern", version=0, law=law)
        self.assertEqual(amended["status"], "admitted", amended)
        wake = self.wake()
        self.avatar(OWNER)
        w = self.turn(wake, "watch", record(event=variant("writes", object=label("cistern"), field=label("level"), above=nat(40)), action=variant("notify")), principal=OWNER)
        self.assertEqual(self.label_of(w), "watching", w)
        for n, amount in enumerate((20, 20, 1, 5)):
            poured = self.turn("cistern", "pour", record(amount=nat(amount)), principal="did:plc:zero", identity="pour%d" % n)
            self.assertEqual(poured["status"], "admitted", poured)
            self.deliver_all()
        self.assertEqual((poured["result"]["label"], get(poured["result"]["payload"], "level")), ("poured", nat(46)))
        self.assertTrue(poured["offers"][0]["text"].startswith("Cistern, level 46. Pour: delvetalk cistern pour / amount: <1 to 20>.\n"), poured["offers"])
        self.assertEqual(self.inbox(OWNER), [(OWNER, "cistern.level is 41")])
        # 21 is past the pour form's declared 1..20: the host refuses it as the spell path does (codex host 12).
        big = self.turn("cistern", "pour", record(amount=nat(21)), principal="did:plc:zero", identity="big")
        self.assertEqual((big["status"], big["receipt"]["outcome"]["class"]), ("refused", "typeMismatch"), big)
        self.assertIn("amount takes 1 to 20", big["receipt"]["outcome"]["reason"])
        version = self.host.send(op="world-view", principal="ember", object="cistern")["version"]
        drained = self.host.send(op="world-propose", principal="ember", identity="drain", roots=[{"object": "cistern", "version": version}],
                                 writes=[{"object": "cistern", "edits": [record(entries={"tag": "variant", "label": "keep", "payload": record()},
                                                                                level={"tag": "variant", "label": "set", "payload": record(value=nat(0))})]}])
        self.assertEqual((drained["status"], drained["receipt"]["outcome"].get("clause")), ("refused", "level"), drained)

    # --- Tide ------------------------------------------------------------------------

    def tide(self, gap=3):
        self.create("tide", "Tide", record(ticks=nat(0), last=nat(0), gap=nat(gap), subs=relation()))

    def test_when_garden_planted_passes_10_the_wake_ticks_the_tide(self):
        """A Wake watches another object's writes: it subscribes to the garden's count, and the
        trigger fires once, as the count passes 10."""
        from tests.test_chain import garden_state
        self.tide()
        self.create("garden", "Garden", garden_state(planted=9))
        wake = self.wake()
        writes = {"tag": "variant", "label": "writes", "payload": record(object=label("garden"), field=label("planted"), above=nat(10))}
        call = {"tag": "variant", "label": "call", "payload": record(card=label("tide"), method=label("tick"))}
        r = self.turn(wake, "watch", record(event=writes, action=call), principal=OWNER)
        self.assertEqual(self.label_of(r), "watching")
        self.deliver_all()
        ticks = lambda: int(get(self.state("tide"), "ticks")["value"])
        for i in range(3):
            planted = self.turn("garden", "plant", record(colour=label("amber"), seed=label("bell %d" % i)), principal=OTHER)
            self.assertEqual(self.label_of(planted), "planted")
            self.deliver_all()
            # 10 does not pass 10; 11 does, once; 12 does not fire again.
            self.assertEqual(ticks(), [0, 1, 1][i], i)

    def test_a_rows_rule_on_a_bells_rains_ticks_the_tide_when_its_author_rains(self):
        """A Wake as a rule: When a row inserted into bell's rains has author OTHER, Wish a tick.
        The wake subscribes to the bell's rains; the host delivers each rain to its typed receiver."""
        from tests.test_replay import bell_seed
        self.tide()
        self.make("bell", closure("Bell"), bell_seed())
        wake = self.wake()
        where = {"tag": "list", "items": [{"tag": "variant", "label": "equals", "payload": record(column=label("author"), equals={"tag": "variant", "label": "text", "payload": record(value=label(OTHER))})}]}
        rule = {"tag": "variant", "label": "rows", "payload": record(object=label("bell"), field=label("rains"), where=where, atLeast=nat(1))}
        call = {"tag": "variant", "label": "call", "payload": record(card=label("tide"), method=label("tick"))}
        self.assertEqual(self.label_of(self.turn(wake, "watch", record(event=rule, action=call), principal=OWNER)), "watching")
        self.deliver_all()
        ticks = lambda: int(get(self.state("tide"), "ticks")["value"])
        for who, expected in ((OWNER, 0), (OTHER, 1)):
            r = self.turn("bell", "rain", record(text=label("a drizzle")), principal=who)
            self.assertEqual(r["status"], "admitted", r)
            self.deliver_all()
            self.assertEqual(ticks(), expected, who)
        card = self.turn(wake, "receive", heard(""), principal=OWNER)["offers"][0]["text"]
        self.assertIn("on 1 new rows of bell.rains where author = %s: call tide tick" % OTHER, card)

    def test_kimik3s_archived_spell_subscribes_and_every_answer_is_the_tide_card(self):
        """Rehearsal findings 1 and 9: the slash spell from the archive (3mxhg6achmc2f) subscribes,
        and subscribe, tick and a tick too soon each answer with what happened and the card."""
        self.tide()
        self.avatar(OTHER)
        post = ("delvetalk garden plant / colour: amber / seed: an example\nmine:\n"
                "delvetalk tide subscribe / every: 1 / note: WC-01, first light")
        sub = self.turn("tide", "receive", heard(post), principal=OTHER)
        self.assertEqual(self.label_of(sub), "subscribed")  # the method's own result
        card = sub["offers"][0]["text"]
        self.assertEqual(card, (
            "Subscribed, from tick 0.\n"
            "\n"
            "THE TIDE, tick 0. Last at clock 0; the next may come at clock 3. Subscribe yourself: delvetalk tide subscribe / every: <1 to 1000> / note: <1 to 140 characters>. Anyone may tick: delvetalk tide tick.\n"
            "kimik3 (yours) every 1 from tick 0: WC-01, first light\n"))
        self.assertTrue(card.startswith("Subscribed, from tick 0.\n\nTHE TIDE, tick 0"), card)
        self.assertIn("kimik3 (yours) every 1 from tick 0: WC-01, first light\n", card)   # the card as the write leaves it
        tick = self.turn("tide", "receive", heard("delvetalk tide tick"), principal=OWNER)
        self.assertEqual(tick["offers"][0]["text"], (
            "Tick 1: 1 note sent.\n"
            "\n"
            "THE TIDE, tick 1. Last at clock 0; the next may come at clock 3. Subscribe yourself: delvetalk tide subscribe / every: <1 to 1000> / note: <1 to 140 characters>. Anyone may tick: delvetalk tide tick.\n"
            "kimik3 every 1 from tick 0: WC-01, first light\n"))
        self.assertTrue(tick["offers"][0]["text"].startswith("Tick 1: 1 note sent.\n\nTHE TIDE, tick 1. Last at clock 0;"), tick["offers"])
        soon = self.turn("tide", "receive", heard("delvetalk tide tick"), principal=OWNER)
        self.assertTrue(soon["offers"][0]["text"].startswith("Too soon: the next tick may come at clock "), soon["offers"])

    def test_a_subscriber_is_shown_by_the_handle_the_host_knew_at_subscribe(self):
        self.tide()
        self.assertEqual(self.host.send(op="world-principal", principal="transport", did=OTHER, handle="inkling.delve.town")["status"], "principal")
        self.turn("tide", "receive", heard("delvetalk tide subscribe / every: 1 / note: first light"), principal=OTHER)
        [sub] = rows(get(self.state("tide"), "subs"))
        self.assertEqual(get(sub, "handle")["value"], "inkling.delve.town")
        card = self.turn("tide", "receive", heard(""), principal="did:plc:zero")["offers"][0]["text"]
        self.assertEqual(card, (
            "THE TIDE, tick 0. Last at clock 0; the next may come at clock 3. Subscribe yourself: delvetalk tide subscribe / every: <1 to 1000> / note: <1 to 140 characters>. Anyone may tick: delvetalk tide tick.\n"
            "inkling.delve.town every 1 from tick 0: first light\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk tide subscribe\n"
            "    every: <a number from 1 to 1000>\n"
            "    note: <text, 1 to 140 characters>\n"
            "\n"
            "    delvetalk tide tick\n"))
        self.assertIn("inkling.delve.town every 1 from tick 0: first light\n", card)

    def test_a_subscriber_is_the_turns_principal_and_a_tick_too_soon_is_refused_naming_the_next(self):
        self.tide()
        self.avatar(OTHER)
        self.avatar(OWNER)
        sub = self.turn("tide", "subscribe", record(every=nat(1), note=label("WC-01, first light")), principal=OTHER)
        self.assertEqual(self.label_of(sub), "subscribed")
        self.turn("tide", "receive", heard("delvetalk tide subscribe\nevery: 2\nnote: inkling's first tide"), principal=OWNER)
        subs = rows(get(self.state("tide"), "subs"))
        self.assertEqual([get(s, "who")["value"] for s in subs], [OTHER, OWNER])
        first = self.turn("tide", "tick", principal="did:plc:zero")
        self.assertEqual((self.label_of(first), get(first["result"]["payload"], "sent")), ("ticked", nat(1)))
        soon = self.turn("tide", "tick", principal="did:plc:zero")
        self.assertEqual(self.label_of(soon), "tooSoon")
        last = int(get(self.state("tide"), "last")["value"])
        self.assertEqual(get(soon["result"]["payload"], "next"), nat(last + 3))
        # The gap is in clock units: turns do not move it, world-advance does.
        for _ in range(4):
            self.turn("tide", "receive", heard(""), principal="did:plc:zero")
        self.assertEqual(self.label_of(self.turn("tide", "tick", principal="did:plc:zero")), "tooSoon")
        self.host.send(op="world-advance", height=last + 3)
        second = self.turn("tide", "tick", principal="did:plc:zero")
        self.assertEqual((self.label_of(second), get(second["result"]["payload"], "sent")), ("ticked", nat(2)))
        self.deliver_all()
        self.assertEqual(self.inbox(OTHER), [("did:plc:zero", "tide 1: WC-01, first light"), ("did:plc:zero", "tide 2: WC-01, first light")])
        self.assertEqual(self.inbox(OWNER), [("did:plc:zero", "tide 2: inkling's first tide")])
        card = self.turn("tide", "receive", heard(""), principal="did:plc:zero")["offers"][0]["text"]
        self.assertEqual(card, (
            "THE TIDE, tick 2. Last at clock 3; the next may come at clock 6. Subscribe yourself: delvetalk tide subscribe / every: <1 to 1000> / note: <1 to 140 characters>. Anyone may tick: delvetalk tide tick.\n"
            "kimik3 every 1 from tick 0: WC-01, first light\n"
            "inkling every 2 from tick 0: inkling's first tide\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk tide subscribe\n"
            "    every: <a number from 1 to 1000>\n"
            "    note: <text, 1 to 140 characters>\n"
            "\n"
            "    delvetalk tide tick\n"))


def Card_handle(did):
    return did.split(":")[-1]


if __name__ == "__main__":
    unittest.main()


LAW_PROBE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./Tide.obend as Tide
import ./Wake.obend as Wake
import ./Relation.obend as Relations
import ./Card.obend as Card
import ./Rows.obend as Rows
def request(principal: String, clock: Nat) -> Abi.Request:
  {context: {world: "", object: "tide", principal: principal, handle: "", caller: "", intent: "t", height: 0n, clock: clock, inputOrigin: {kind: "request", object: "", command: "", program: "", immediatelyPrevious: false, post: ""}}, method: "tick", argument: Plans.nothing(), kind: 0n, pin: "", reads: Lists.List::<Abi.Read>.nil()}
def verdict(v: Abi.Verdict) -> String:
  match v:
    case admitted(_): "admitted"
    case refused(r): textConcat("refused ", r.clause)
def subs(who: String) -> Lists.List<Tide.Sub>:
  Lists.List::<Tide.Sub>.cons({head: {who: who, every: 1n, note: "n", since: 0n, handle: ""}, tail: Lists.List::<Tide.Sub>.nil()})
def tide(ticks: Nat, last: Nat, who: String) -> Tide.State:
  {ticks: ticks, last: last, gap: 3n, subs: Relations.Relation.rows({items: if who == "" then Lists.List::<Tide.Sub>.nil() else subs(who)})}
def sub(who: String, every: Nat) -> Tide.Sub:
  {who: who, every: every, note: "n", since: 0n, handle: ""}
def tideOf(items: Lists.List<Tide.Sub>) -> Tide.State:
  {ticks: 0n, last: 0n, gap: 3n, subs: Relations.fromList(items, Tide.subKey)}
def two(a: Tide.Sub, b: Tide.Sub) -> Lists.List<Tide.Sub>:
  Lists.List.cons({head: a, tail: Lists.List.cons({head: b, tail: Lists.List.nil({})})})
def one(a: Tide.Sub) -> Lists.List<Tide.Sub>:
  Lists.List.cons({head: a, tail: Lists.List.nil({})})
def cell(text: String) -> Relations.Cell:
  Relations.text(text)
def row(author: String, n: Nat, text: String) -> Rows.Columns:
  Rows.one(Rows.text("author", author), Rows.one(Rows.nat("n", n), Rows.one(Rows.text("text", text), Rows.none())))
def by(author: String) -> Wake.Where:
  Wake.Where.equals({column: "author", equals: cell(author)})
def only(w: Wake.Where) -> Lists.List<Wake.Where>:
  Lists.List.cons({head: w, tail: Lists.List.nil({})})
def rule(field: String, where: Lists.List<Wake.Where>) -> Wake.On:
  Wake.On.rows({object: "bell", field: field, where: where, atLeast: 1n})
# Rows (kimik3 0 "a Moth drizzle", glm 1 "dry", kimik3 2 "moths") on bell.rains: how many
# match each rule.
def rowsMatched(which: Nat) -> Nat:
  let rows = Lists.List::<Rows.Columns>.cons({head: row("kimik3", 0n, "a Moth drizzle"), tail: Lists.List::<Rows.Columns>.cons({head: row("glm", 1n, "dry"), tail: Lists.List::<Rows.Columns>.cons({head: row("kimik3", 2n, "moths"), tail: Lists.List::<Rows.Columns>.nil()})})})
  if which == 0n then Wake.matched(rule("rains", only(by("kimik3"))), "bell", "rains", rows) else if which == 1n then Wake.matched(rule("rains", only(by("zero"))), "bell", "rains", rows) else if which == 2n then Wake.matched(rule("doors", only(by("kimik3"))), "bell", "rains", rows) else if which == 3n then Wake.matched(rule("rains", only(by("kimik3"))), "garden", "rains", rows) else moreMatched(which, rows)
def moreMatched(which: Nat, rows: Lists.List<Rows.Columns>) -> Nat:
  if which == 4n then Wake.matched(rule("rains", only(Wake.Where.above({column: "n", above: 0n}))), "bell", "rains", rows) else if which == 5n then Wake.matched(rule("rains", only(Wake.Where.below({column: "n", below: 2n}))), "bell", "rains", rows) else if which == 6n then Wake.matched(rule("rains", only(Wake.Where.contains({column: "text", contains: "moth"}))), "bell", "rains", rows) else Wake.matched(rule("rains", Lists.List.cons({head: by("kimik3"), tail: only(Wake.Where.above({column: "n", above: 0n}))})), "bell", "rains", rows)
# Each case: old subs, new subs, requester glm. "own" adds glm beside an unchanged kimik3;
# "theirs" changes kimik3's row; "drop" retracts kimik3's; "mine" replaces and drops glm's own.
def changedBy(which: Nat) -> String:
  if which == 0n then verdict(Tide.law(tideOf(one(sub("kimik3", 1n))), tideOf(two(sub("kimik3", 1n), sub("glm", 2n))), request("glm", 5n))) else if which == 1n then verdict(Tide.law(tideOf(two(sub("kimik3", 1n), sub("glm", 2n))), tideOf(two(sub("kimik3", 4n), sub("glm", 2n))), request("glm", 5n))) else if which == 2n then verdict(Tide.law(tideOf(two(sub("kimik3", 1n), sub("glm", 2n))), tideOf(one(sub("glm", 2n))), request("glm", 5n))) else verdict(Tide.law(tideOf(two(sub("kimik3", 1n), sub("glm", 2n))), tideOf(one(sub("kimik3", 1n))), request("glm", 5n)))
def tickAt(height: Nat) -> String:
  verdict(Tide.law(tide(1n, 10n, ""), tide(2n, height, ""), request("zero", height)))
def subscribeAs(principal: String) -> String:
  verdict(Tide.law(tide(0n, 0n, ""), tide(0n, 0n, "kimik3"), request(principal, 5n)))
"""


class LawPredicates(unittest.TestCase):
    """Tide's Bend law predicate and the Wake's row rules, run as pure functions."""

    def run_probe(self, entry, argument):
        from tests.test_objects import check, compile_job
        from tests.test_turn_world import closure as world_closure
        modules, seen = [], set()
        for name in ("Tide", "Wake"):
            world_closure(name, seen, modules)
        compiled = compile_job(modules + [{"name": "Probe", "source": LAW_PROBE}], entry)
        self.assertEqual(compiled["status"], "compiled", compiled)
        out = check({"op": "run", "artifact": compiled["artifact"], "arguments": [argument]})
        self.assertEqual(out["status"], "finished", out)
        return out["value"]["value"]

    def test_the_artifacts_record_a_law_predicate(self):
        from tests.test_objects import compile_job
        self.assertEqual(compile_job(closure("Tide"), "initial")["artifact"]["law"], {"present": True, "reads": False})
        # The Wake's law text refuses every write but its owner's, so it has no predicate.
        self.assertEqual(compile_job(closure("Wake"), "initial")["artifact"]["law"], {"present": False})

    def test_a_tick_sooner_than_the_gap_is_refused_tooSoon(self):
        self.assertEqual(self.run_probe("tickAt", nat(12)), "refused tooSoon")
        self.assertEqual(self.run_probe("tickAt", nat(13)), "admitted")

    def test_a_subscription_is_only_ever_the_requesters_own(self):
        self.assertEqual(self.run_probe("subscribeAs", label("kimik3")), "admitted")
        self.assertEqual(self.run_probe("subscribeAs", label("glm")), "refused self")

    def test_a_rows_rule_counts_the_rows_matching_its_patterns_on_its_object_and_field(self):
        # equals, a missing author, another field, another object; above 0, below 2, the whole
        # word "moth" (case aside; "moths" is another word), and two patterns at once.
        self.assertEqual([self.run_probe("rowsMatched", nat(n)) for n in range(8)], ["2", "0", "0", "0", "2", "2", "1", "1"])

    def test_the_changed_keys_of_a_subscription_write_are_the_requesters(self):
        self.assertEqual([self.run_probe("changedBy", nat(n)) for n in range(4)],
                         ["admitted", "refused self", "refused self", "admitted"])

