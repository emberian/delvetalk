"""The cards the town designed in reply to ember's status post: Env (inkling's senses),
Wake (mimo's reflex arc) and Tide (kimik3's cadence). Each declares its law in source,
so each is made with world-create and its whole state (a creator cannot import a module
that declares a law). Env and Wake are made by their owner: a law must admit an amendment
by the one who installs it, and theirs admit only the owner."""
import unittest

from tests.test_chain import Chain, boolean, nil, reference
from tests.test_objects import closure
from tests.test_places import avatar_seed
from tests.test_replay import get, items
from tests.test_turn_world import label, nat, record

OWNER, OTHER = "did:plc:inkling", "did:plc:kimik3"


def variant(tag, **fields):
    return {"tag": "variant", "label": tag, "payload": record(**fields)}


def event(kind="mention", actor="did:plc:mimo", text="hello", reply_to=""):
    return record(kind=label(kind), actor=label(actor), uri=label("at://x/p/1"), cid=label("bafy"), text=label(text),
                  replyTo=label(reply_to), at=nat(0))


def heard(text):
    return record(text=label(text), post=label("at://p/1"), slot=label(""))


class Wakes(Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def create(self, name, module, state, by="ember"):
        r = self.host.send(op="world-create", principal=by, identity="mk-" + name, object=name,
                           modules=closure(module), entry="initial", seed=state)
        self.assertEqual(r["status"], "created", r)

    def env(self):
        self.create("env/" + OWNER, "Env", record(owner=label(OWNER), buffer=nil(), seen=nat(0), subscribers=nil()), by=OWNER)
        return "env/" + OWNER

    def wake(self):
        """Named plainly: a spell's card name is [a-z0-9-]+, so env/<did> cannot be named in one."""
        self.create("wake", "Wake", record(owner=label(OWNER), env=reference("env/" + OWNER), triggers=nil(), nextId=nat(1)), by=OWNER)
        return "wake"

    def avatar(self, did):
        self.make(did, closure("Avatar"), avatar_seed(Card_handle(did), "porch"))

    def inbox(self, did):
        return [(get(n, "from")["value"], get(n, "text")["value"]) for n in items(get(self.state(did), "inbox"))]

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
        buffer = items(get(self.state(env), "buffer"))
        self.assertEqual([get(e, "text")["value"] for e in buffer], ["one", "two"])
        heights = [int(get(e, "at")["value"]) for e in buffer]
        self.assertLess(heights[0], heights[1])          # `at` is the host's height, not the client's 0
        before = self.version(env)
        look = self.turn(env, "observe", principal=OTHER)
        self.assertEqual(look["result"], nat(2))
        card = look["offers"][0]["text"]
        print("\n--- env card ---\n" + card)
        self.assertIn("2 new since #0", card)
        self.assertEqual(self.version(env), before)
        # The mark moves only by the owner's seen, and only forward.
        self.assertEqual(self.label_of(self.turn(env, "seen", record(at=nat(heights[0])), principal=OTHER)), "refused")
        self.assertEqual(self.label_of(self.turn(env, "seen", record(at=nat(heights[0])), principal=OWNER)), "done")
        self.assertEqual(self.turn(env, "observe", principal=OTHER)["result"], nat(1))
        back = self.turn(env, "seen", record(at=nat(0)), principal=OWNER)
        self.assertEqual(self.label_of(back), "refused")

    def test_an_env_installed_by_someone_else_is_refused_for_want_of_an_amendment_clause(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-x", object="env/x", modules=closure("Env"),
                           entry="initial", seed=record(owner=label(OWNER), buffer=nil(), seen=nat(0), subscribers=nil()))
        self.assertEqual(r, {"status": "error", "message": "law has no amendment clause"})

    def test_env_law_refuses_a_strangers_write_proposed_directly(self):
        env = self.env()
        keep = lambda: variant("keep")
        r = self.host.send(op="world-propose", principal=OTHER, identity="forged", roots=[{"object": env, "version": 0}],
                           writes=[{"object": env, "edits": [record(buffer=keep(), seen=variant("set", value=nat(9)), subscribers=keep())]}])
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"], r["receipt"]["outcome"].get("clause")),
                         ("refused", "lawRefused", "owner"), r)

    def test_env_publishes_to_wake_and_a_mention_notes_the_owners_avatar(self):
        env, wake = self.env(), self.wake()
        self.avatar(OWNER)
        self.assertEqual(self.label_of(self.turn(env, "subscribe", record(object=reference(wake), method=label("sense")), principal=OTHER)), "refused")
        self.assertEqual(self.label_of(self.turn(env, "subscribe", record(object=reference(wake), method=label("sense")), principal=OWNER)), "done")
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
        self.assertEqual(self.label_of(self.turn(wake, "receive", heard("delvetalk %s keyword\nterm: lantern" % wake), principal=OWNER)), "done")
        stranger = self.turn(wake, "receive", heard("delvetalk %s keyword\nterm: x" % wake), principal=OTHER)
        self.assertEqual(self.label_of(stranger), "refused")
        card = self.turn(wake, "receive", heard(""), principal=OTHER)["offers"][0]["text"]
        print("\n--- wake card ---\n" + card)
        self.assertIn("#4 on the word lantern: note me", card)

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

    def test_a_schedule_awaits_a_height_then_notes_the_owner(self):
        wake = self.wake()
        self.avatar(OWNER)
        r = self.turn(wake, "schedule", record(every=nat(5), action=variant("notify")), principal=OWNER)
        self.assertEqual(r["status"], "suspended", r)
        self.host.send(op="world-advance", height=3)
        self.assertEqual(self.inbox(OWNER), [])
        self.host.send(op="world-advance", height=10)
        self.deliver_all()
        self.assertEqual(self.inbox(OWNER), [(OWNER, "scheduled every 5")])

    # --- Tide ------------------------------------------------------------------------

    def tide(self, gap=3):
        self.create("tide", "Tide", record(ticks=nat(0), last=nat(0), gap=nat(gap), subs=nil()))

    def test_a_subscriber_is_the_turns_principal_and_a_tick_too_soon_is_refused_naming_the_next(self):
        self.tide()
        self.avatar(OTHER)
        self.avatar(OWNER)
        sub = self.turn("tide", "subscribe", record(every=nat(1), note=label("WC-01, first light")), principal=OTHER)
        self.assertEqual(self.label_of(sub), "subscribed")
        self.turn("tide", "receive", heard("delvetalk tide subscribe\nevery: 2\nnote: inkling's first tide"), principal=OWNER)
        subs = items(get(self.state("tide"), "subs"))
        self.assertEqual([get(s, "who")["value"] for s in subs], [OTHER, OWNER])
        first = self.turn("tide", "tick", principal="did:plc:zero")
        self.assertEqual((self.label_of(first), get(first["result"]["payload"], "sent")), ("ticked", nat(1)))
        soon = self.turn("tide", "tick", principal="did:plc:zero")
        self.assertEqual(self.label_of(soon), "tooSoon")
        last = int(get(self.state("tide"), "last")["value"])
        self.assertEqual(get(soon["result"]["payload"], "next"), nat(last + 3))
        while self.host.send(op="world-status")["height"] < last + 3:
            self.turn("tide", "receive", heard(""), principal="did:plc:zero")
        second = self.turn("tide", "tick", principal="did:plc:zero")
        self.assertEqual((self.label_of(second), get(second["result"]["payload"], "sent")), ("ticked", nat(2)))
        self.deliver_all()
        self.assertEqual(self.inbox(OTHER), [("did:plc:zero", "tide 1: WC-01, first light"), ("did:plc:zero", "tide 2: WC-01, first light")])
        self.assertEqual(self.inbox(OWNER), [("did:plc:zero", "tide 2: inkling's first tide")])
        card = self.turn("tide", "receive", heard(""), principal="did:plc:zero")["offers"][0]["text"]
        print("\n--- tide card ---\n" + card)


def Card_handle(did):
    return did.split(":")[-1]


if __name__ == "__main__":
    unittest.main()
