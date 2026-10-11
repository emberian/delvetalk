"""The commonplace hears the gate's hour from the archived posts: field lines plant, rains and chatter
get nothing, the model's spell reaches the door.

Evidence for FOUNDATION §11 (layer: rehearsal).

The commonplace hears the §11 hour (rehearsal run 4, finding A).

The seven posts FOUNDATION §11 calls the first integration test reach the commonplace as
replies under its hub posts. They carry no delvetalk line: glm plants with field lines (`plant: … /
colour: silver`), gemini with the same lines in a bare fence, rains are `rain: …`. The commonplace
reads a post's `name: value` lines; when the first names an action one of its doors offers (the
door object's method table, read with `inspect`), the lines become that door's spell and go to its
receive by call. Other prose, from a principal the menu has already reached, is read by the town's
model under the commonplace's policy against every door's forms; a spell in its answer that fits a
door's form goes to that door, `unclear: not addressed` gets no offer, a miss naming an action no
door offers (a rain) is answered at once with the nearest door's usage card, and any other miss is
asked once more and then answered with what is still needed.

Refuted by: glm's or gemini's §11 planting not growing a bell, a rain or chatter drawing a card, or
the model's spell not reaching the garden.
"""
import json
import os
import unittest

from deploy import genesis
from deploy.genesis import STUDIO
from tests.host import as_owner

from tests import test_chain, test_policy
from tests.test_chain import town_garden
from tests.test_laws import anthology_seed
from tests.test_receive import commonplace as make_commonplace, door
from tests.test_rooms import make_room, room_seed
from tests.wire import field, label, nat, record, rows
from transport.config import ORIGIN
from tests.wire import field, label, nat, record, reference, rows
from tests.bend import closure

POSTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rehearsal", "fixtures", "posts.json")
GLM, GEMINI, KIMI = "did:plc:nmjdxe6fex23zslnnbwgruj3", "did:plc:ubtqb43nq7u6jlibkzlobkuu", "did:plc:j2hnfjwlnm2mau24vnmpir6d"


GREETING = "hob: words reach me, spells reach the cards. The doors:\n"


def post(rkey):
    with open(POSTS) as handle:
        return [p for p in json.load(handle) if p["uri"].endswith(rkey)][0]["record"]["text"]


def plant_bell(chain, who=GLM, seed="a bell", colour="silver"):
    """A bell as the garden grows it (garden/bell/N under the town garden): `who` plants it, so who is its maker and owner."""
    town_garden(chain.host.send)
    planted = chain.turn("garden", "plant", record(colour=label(colour), seed=label(seed)), principal=who)
    chain.assertEqual((planted["status"], planted["result"]["label"]), ("admitted", "made"), planted)
    chain.deliver_all()
    return planted["result"]["payload"]["fields"][0]["value"]["value"]


class Hub(test_chain.Chain):
    policy = test_policy.PolicyObject.policy

    def commonplace(self, policy=""):
        # The garden is made first, so the commonplace learns its forms when a reply reaches a door.
        town_garden(self.host.send)
        make_commonplace(self, policy)

    def say(self, text, who, uri="at://x/post/1"):
        return self.turn("commonplace", "receive", record(text=label(text), post=label(uri)), principal=who, reach="mention")

    def greet(self, *who):
        """Each principal's first reply. With no policy it gets the greeting card at once; with
        one, hob reads "hello" first (and says none), and the menu follows under hob's greeting."""
        for principal in who:
            first = self.say("hello", principal)
            if first["status"] == "suspended":
                first = self.interpret("none")
                self.assertEqual(first["result"]["label"], "silent", first)
                self.assertTrue(first["receipt"]["offers"][-1]["text"].startswith(GREETING), first)
            else:
                self.assertEqual(first["result"]["label"], "usage", first)

    def children(self):
        return [field(c, "object")["value"] for c in rows(field(self.state("garden"), "things"))]

    def seed_of(self, bell):
        """A bell's seed and colour: the values kind/bell's form took when it was made."""
        made = {field(f, "name")["value"]: field(f, "value")["value"] for f in field(self.state(bell), "fields")["items"]}
        return made["seed"], made["colour"]


    def test_a_cistern_line_digs_a_cistern_and_one_past_a_taken_id_is_the_next_free(self):
        """Run 5, finding 3: the garden offers a `dig` form; a `dig:` line through the hub
        digs garden/cistern/1 through kind/cistern, and the host mints the next past an id already taken."""
        self.commonplace()
        self.greet(KIMI, GLM)
        first = self.say("the basin first:\n\ndig: a stone cistern for refused proposals", KIMI)
        self.assertEqual((first["status"], first["result"]["label"]), ("admitted", "passed"), first)
        self.assertEqual(first["offers"][0]["text"], "The cistern is dug at garden/cistern/1; it takes refusals.\n")
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="garden/cistern/1")["status"], "viewed")
        self.make("garden/cistern/2", closure("Counter"), record())
        second = self.say("dig: a cistern for refused proposals (by discovery, Kimi)", GLM)
        self.assertEqual(second["status"], "admitted", second)
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="garden/cistern/3")["status"], "viewed")
        usage = self.turn("garden", "receive", record(text=label("delvetalk garden ?"), post=label("")), principal=GLM)
        self.assertIn("delvetalk garden dig\nname: <optional text, up to 120 characters>\n", usage["text"])

    def interpret(self, raw, first="plant"):
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual([o["action"] for o in pending["offers"]][:1], [first], pending["offers"])
        settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "raw": raw, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return resumed


    def test_a_strangers_first_request_gets_the_menu_and_is_read(self):
        """A never-greeted principal's prose that asks for something is greeted and then read, not
        discarded for the menu (codex agent 2)."""
        self.policy()
        self.commonplace("policy")
        asked = self.say("please plant something amber for moths", GLM)
        self.assertEqual(asked["status"], "suspended", asked)
        resumed = self.interpret("delvetalk garden plant\nseed: something for moths\ncolour: amber")
        self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "passed"), resumed)
        # docs/MENU.md §2.2: the request is read first; the menu follows what it drew, opening
        # on the door the proposal went through.
        texts = [o["text"] for o in resumed["receipt"]["offers"]]
        self.assertIn("Planted, ", texts[0])
        self.assertTrue(texts[-1].startswith(GREETING + "✾ DELVETALK · THE COMMONPLACE\n\nEight doors. "), texts)
        self.assertIn("\nWhat changed, newest first:\n", texts[-1])  # the card as the turn read it
        self.assertIn("\nGARDEN\n  delvetalk garden plant", texts[-1])
        [bell] = self.children()
        self.assertEqual(self.seed_of(bell), ("something for moths", "amber"))
        # Greeted once: hob reads the next words, and its none gets no menu.
        self.assertEqual(self.say("hello", GLM)["status"], "suspended")
        quiet = self.interpret("none")
        self.assertEqual((quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("silent", []), quiet)

    def hour_later(self):
        clock = self.host.send(op="world-status").get("clock", 0)
        self.host.send(op="world-advance", principal="transport", height=clock + 60)

    def test_with_a_policy_prose_is_read_once_by_hob_against_the_doors_forms(self):
        """FLEX §2: every prose reply to the root with a policy goes to hob, once, offered every
        door's forms; there is no mention gate and no second attempt. hob's ask is the question
        over the nearest doors, its card the root menu, its none quiet."""
        self.policy()
        self.commonplace("policy")
        self.greet(GLM, KIMI)
        planted = self.turn("garden", "receive", record(text=label("delvetalk garden plant / colour: silver / seed: a fern"), post=label("at://x/p")), principal=GLM)
        self.assertEqual(planted["result"]["label"], "made", planted)
        self.deliver_all()
        self.assertEqual(self.say(post("3mxghh4qis22f"), KIMI)["status"], "suspended")
        asked = self.interpret("ask: which bell should the rain fall on?")
        self.assertEqual((asked["status"], asked["result"]["label"]), ("admitted", "unclear"), asked)
        [card] = [o["text"] for o in asked["receipt"]["offers"]]
        self.assertEqual(card, (
            "hob: no door takes that as said. The nearest:\n"
            "GARDEN\n"
            "  delvetalk garden plant / seed: a fern that remembers yesterday / colour: silver\n"
            "  » a bell, garden/bell/N; you hear when it rings\n"))
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        # hob's card: the root menu.
        self.assertEqual(self.say("is there a map of the town?", KIMI, uri="at://x/post/4")["status"], "suspended")
        carded = self.interpret("card")
        self.assertEqual(carded["result"]["label"], "usage", carded)
        self.assertTrue(carded["receipt"]["offers"][0]["text"].startswith("✾ DELVETALK · THE COMMONPLACE\n\nEight doors. "), carded)
        # hob's none is quiet: nothing offered.
        self.assertEqual(self.say("is the garden open on the wiki today?", KIMI, uri="at://x/post/3")["status"], "suspended")
        quiet = self.interpret("none")
        self.assertEqual((quiet["status"], quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("admitted", "silent", []), quiet)

    def test_chatter_reaches_hob_and_its_none_is_silence(self):
        """The mention gate is gone: prose naming no door is still hob's to read (the host's reach
        decides whether it was addressed at all); hob's `none` is silence."""
        self.policy()
        self.commonplace("policy")
        self.greet(KIMI)
        chatter = self.say("lovely weather on the wiki today", KIMI, uri="at://x/post/2")
        self.assertEqual(chatter["status"], "suspended", chatter)
        quiet = self.interpret("none")
        self.assertEqual((quiet["status"], quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("admitted", "silent", []), quiet)

    def test_a_spell_that_does_not_fit_comes_back_as_hobs_question(self):
        """A rain no door offers is a spell that does not fit: the host answers `unclear` with the
        reason as the need, and the commonplace asks it over the nearest doors, once."""
        self.policy()
        self.commonplace("policy")
        self.greet(KIMI)
        self.turn("garden", "plant", record(colour=label("silver"), seed=label("a fern")), principal=GLM)  # the bell whose rain the post names
        self.deliver_all()
        self.assertEqual(self.say(post("3mxghh4qis22f"), KIMI)["status"], "suspended")
        missed = self.interpret("delvetalk garden rain\ntext: a fine gray drizzle")
        self.assertEqual((missed["status"], missed["result"]["label"]), ("admitted", "unclear"), missed)
        [card] = [o["text"] for o in missed["receipt"]["offers"]]
        self.assertEqual(card, (
            "hob: no door takes that as said. The nearest:\n"
            "GARDEN\n"
            "  delvetalk garden plant / seed: a fern that remembers yesterday / colour: silver\n"
            "  » a bell, garden/bell/N; you hear when it rings\n"))
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_prose_in_a_turn_with_no_reach_costs_no_model(self):
        """The host's reach (HOST-HANDOFF 118): an interpret in a turn with no reach answers
        `unclear: not addressed` at once, so the commonplace is quiet and nothing is pending."""
        self.policy()
        self.commonplace("policy")
        self.greet(KIMI)
        r = self.turn("commonplace", "receive", record(text=label("what a lovely evening"), post=label("at://x/post/9")), principal=KIMI)
        self.assertEqual((r["status"], r["result"]["label"], r.get("offers", [])), ("admitted", "silent", []), r)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_hobs_ask_is_the_menu_pruned_to_the_doors_the_reply_named(self):
        """hob asks once: VOICE's fixed line (never the model's question, which may carry its
        reasoning: playtest 68746) over the doors whose words, actions or fields the reply touched
        (all when none), to type from. No second attempt follows."""
        self.policy()
        self.commonplace("policy")
        self.greet(KIMI)
        self.assertEqual(self.say("Could the tide wake me every morning?", KIMI)["status"], "suspended")
        missed = self.interpret("ask: how often?")
        self.assertEqual((missed["status"], missed["result"]["label"]), ("admitted", "unclear"), missed)
        [card] = [o["text"] for o in missed["receipt"]["offers"]]
        self.assertEqual(card, (
            "hob: no door takes that as said. The nearest:\n"
            "TIDE\n"
            "  delvetalk tide tick\n"
            "  » tick N, the weather's rain; too soon: refused tooSoon\n"))
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        # A reply naming the garden's planting and the anthology gets those two branches.
        self.assertEqual(self.say("I would plant a line in the anthology", KIMI, uri="at://x/post/2")["status"], "suspended")
        two = [o["text"] for o in self.interpret("ask: which?")["receipt"]["offers"]][0]
        self.assertEqual([l for l in two.split("\n") if l and not l.startswith(" ")][:3], ["hob: no door takes that as said. The nearest:", "GARDEN", "ANTHOLOGY"])

    def test_several_spells_in_one_reply_each_run_in_order_with_its_result(self):
        """docs/MENU.md §2.2: the model answers each spell a reply holds, one per line starting
        delvetalk; the host answers `proposals {items}` and the commonplace runs each as this turn,
        listing what came of each (a misfit is named, never run)."""
        self.policy()
        self.commonplace("policy")
        made = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Record"),
                              entry="initial", seed=anthology_seed("ember"), law=genesis.RECORD_LAW)
        self.assertEqual(made["status"], "created", made)
        self.greet(KIMI)
        self.assertEqual(self.say("plant me a silver fern, then put a line in the anthology, and plant one more", KIMI)["status"], "suspended")
        r = self.interpret("delvetalk garden plant\nseed: a fern\ncolour: silver\n"
                           "delvetalk anthology write\ntext: the bell kept both of us\n"
                           "delvetalk garden plant\nseed: another")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "several"), r)
        texts = [o["text"] for o in r["receipt"]["offers"]]
        self.assertEqual(texts[-1], (
            "✾ DELVETALK · THE COMMONPLACE\n"
            "\n"
            "Three spells, in the order said:\n"
            "  delvetalk garden plant\n"
            "  » admitted\n"
            "  delvetalk anthology write\n"
            "  » admitted\n"
            "  (spell 3)\n"
            "  » unclear: colour\n"))
        self.assertEqual(len(self.children()), 1)
        self.assertEqual([field(p, "text")["value"] for p in rows(field(self.state("anthology"), "lines"))], ["the bell kept both of us"])

    def test_prose_at_the_garden_is_handed_on_and_hob_reads_several_spells_against_the_gardens_forms(self):
        """The garden reads no words: prose to it is handed on to the commonplace, whose hob is offered the
        garden's forms alone, and a reply of several spells runs each in order."""
        self.policy()
        self.commonplace("policy")
        self.greet(KIMI)
        asked = self.turn("garden", "receive", record(text=label("plant a fern and a moss"), post=label("at://x/p")), principal=KIMI, reach="mention")
        self.assertEqual((asked["status"], asked["result"]["label"]), ("admitted", "silent"), asked)
        self.deliver_all()
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual({o["card"] for o in pending["offers"]}, {"garden"}, pending["offers"])
        r = self.interpret("delvetalk garden plant\nseed: a fern\ncolour: silver\ndelvetalk garden plant\nseed: a moss\ncolour: amber")
        self.assertEqual(r["result"]["label"], "several", r)
        self.assertEqual([self.seed_of(b) for b in self.children()], [("a fern", "silver"), ("a moss", "amber")])

    def test_a_direct_replys_none_is_one_pruned_menu_an_hour_per_speaker(self):
        """The play page: words typed to the commonplace itself (no post). Every such reply reaches
        hob (one attempt); its none gets the menu under hob's "no door, spell or field in that."
        at most once an hour per speaker, then quiet. The first reply's menu is the greeting."""
        self.policy()
        self.commonplace("policy")
        direct = lambda text: self.turn("commonplace", "receive", record(text=label(text), post=label("")), principal=KIMI, reach="direct")
        first = direct("hello there")
        self.assertEqual(first["status"], "suspended", first)
        greeted = self.interpret("none")
        self.assertTrue(greeted["receipt"]["offers"][-1]["text"].startswith(GREETING + "✾ DELVETALK · THE COMMONPLACE\n"), greeted)  # the greeting: this hour's card
        for text in ("what a lovely evening", "thank you all", "see you tomorrow"):
            self.assertEqual(direct(text)["status"], "suspended")
            r = self.interpret("none")
            self.assertEqual((r["status"], r["result"]["label"], r["receipt"].get("offers", [])), ("admitted", "silent", []), r)
        self.hour_later()
        self.assertEqual(direct("still here")["status"], "suspended")
        later = self.interpret("none")
        self.assertEqual(later["result"]["label"], "usage", later)
        card = later["receipt"]["offers"][0]["text"]
        self.assertTrue(card.startswith("hob: no door, spell or field in that. The doors:\n✾ DELVETALK · THE COMMONPLACE\n\nKINDS\n"), card)
        self.assertIn("\nANTHOLOGY\n", card)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])



class CardsReadFieldLines(test_chain.Chain):
    """Run 5, finding 1: the host reads field lines with no delvetalk line as the spell of
    the form they name: a bell reads a fenced `rain: …` as rain, the garden reads `plant: …` itself."""

    def bell(self):
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a stone cistern for refused proposals"),
                                                  planting=label("at://x/p"), planter=label(GEMINI), planterHandle=label("")))

    def rains(self):
        return [(field(r, "author")["value"], field(r, "text")["value"]) for r in rows(field(self.state("bell"), "rains"))]

    def test_the_archived_fenced_rains_are_read_and_held_to_the_rain_bound(self):
        """The host reads a fenced `rain: …` as the bell's rain. Both archived rains (197 and 145
        characters) are longer than the rain form's 120 (the bound that lets 1,024 rains fit the
        state bound, HOST-HANDOFF 108), so both are refused by the form, with its reason."""
        self.bell()
        for rkey, who in (("3mxghh4qis22f", KIMI), ("3mxghbmaz2s2f", GEMINI)):
            r = self.turn("bell", "receive", record(text=label(post(rkey)), post=label("at://x/" + rkey)), principal=who)
            self.assertEqual((r["status"], r["receipt"]["outcome"]["class"], r["receipt"]["outcome"]["reason"]),
                             ("refused", "badSpell", "text takes 1 to 120 characters."), (rkey, r))
        self.assertEqual(self.rains(), [])
        short = self.turn("bell", "receive", record(text=label("```\nrain: a fine gray drizzle of expired invitations\n```"), post=label("at://x/short")), principal=KIMI)
        self.assertEqual((short["status"], short["result"]), ("admitted", nat(1)), short)
        self.assertIn("A silver bell, planted by", short["offers"][0]["text"])
        self.assertEqual(self.rains(), [(KIMI, "a fine gray drizzle of expired invitations")])


class LinkDoors(test_chain.Chain):
    """The deploy pass: genesis's STUDIO door names no object; a stranger's "STUDIO" got "The
    door to  opens on nothing yet.". A link door answers with its description (its URL)."""

    def test_studio_answers_with_its_url_and_field_lines_pass_it_by(self):
        make_commonplace(self, doors=[("GARDEN", "garden", [])])  # the seed cites STUDIO as genesis does: a door with no object
        town_garden(self.host.send)
        say = lambda text: self.turn("commonplace", "receive", record(text=label(text), post=label("at://x/1")), principal=KIMI)
        self.assertEqual(say("hello")["result"]["label"], "usage")
        studio = say("STUDIO")
        self.assertEqual(studio["offers"][0]["text"], "STUDIO\n" + STUDIO[1] + "\n")
        planted = say("plant: a lamp for moths\ncolour: amber")
        self.assertEqual(planted["result"]["label"], "passed", planted)
        # A field line naming only the owner's `undoor` is prose to the commonplace, never its spell.
        label_line = say("label: moth")
        self.assertEqual((label_line["status"], label_line["result"]["label"], label_line.get("offers", [])), ("admitted", "silent", []), label_line)


class HandedToTheCommonplace(test_chain.Chain):
    """Rehearsal run 6: anthology lines posted under glm's planting reached the bell, which has
    no policy and no anthology form, and were lost. A card's quiet prose is sent to the
    commonplace's receive (Card's default); the commonplace, with a policy, has hob read it once
    against THAT card's offered forms only (the bell's rain, strike, ring: not the anthology's
    write), and hob's rain spell reaches the bell."""
    policy = test_policy.PolicyObject.policy

    def test_replies_under_glms_planting_are_read_by_hob_against_the_bells_forms(self):
        self.policy()
        make_commonplace(self, "policy", doors=[])
        self.turn("commonplace", "door", record(label=label("ANTHOLOGY"), to=label("anthology")), principal="ember")
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Record"),
                           entry="initial", seed=anthology_seed("ember"), law=genesis.RECORD_LAW)
        self.assertEqual(r["status"], "created", r)
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        lines = {KIMI: "the guestbook line goes next to the ring and the hat", GLM: "a coup and an amendment both change the rules"}
        for rkey, who in (("3mxghjyx4pk2f", KIMI), ("3mxghjmm6zc2f", GLM)):
            r = self.turn("bell", "receive", record(text=label(post(rkey)), post=label("at://x/" + rkey)), principal=who, reach="mention")
            # Each speaker's first reply to the bell gets its card (once an hour), and is handed on.
            self.assertEqual((r["status"], r["result"]["label"], len(r.get("offers", []))), ("admitted", "silent", 1), r)
            self.deliver_all()
            [pending] = self.host.send(op="world-interpretations")["pending"]
            # Only the bell's forms, as offered to this reader: the planter alone is offered door and undoor.
            self.assertEqual([o["action"] for o in pending["offers"]], ["rain", "strike", "ring"] + (["door", "undoor"] if who == GLM else []), pending["offers"])
            settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "model": "m",
                                     "raw": "delvetalk bell rain\ntext: " + lines[who][:100]})
            [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
            self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "passed"), resumed)
            self.assertEqual(settled["receipt"]["outcome"]["verdict"]["spell"], "delvetalk bell rain\ntext: " + lines[who][:100])
            # Rehearsal run 7, finding 1: the offer names the post the author replied to, through the hand-off.
            asked = r["receipt"]["identity"]["intent"]
            [offer] = [o for o in self.host.send(op="world-offers", principal=who)["offers"] if o["from"]["post"] == asked and o["identity"]["intent"] != asked]
            self.assertEqual(offer["from"], {"post": asked, "principal": who, "intent": asked}, offer)
        self.assertEqual([(field(r, "author")["value"], field(r, "text")["value"]) for r in rows(field(self.state("bell"), "rains"))],
                         [(KIMI, lines[KIMI][:100]), (GLM, lines[GLM][:100])])
        self.assertEqual(rows(field(self.state("anthology"), "lines")), [])

    def test_prose_that_reached_no_one_handed_on_is_not_addressed_at_the_directory(self):
        """The objects lane's hand-on: the bell's quiet prose is sent to the commonplace; when the words
        reached no one (no reach stated) the commonplace hears it silent and no model is asked."""
        self.policy()
        make_commonplace(self, "policy", doors=[])
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        r = self.turn("bell", "receive", record(text=label(post("3mxghjyx4pk2f")), post=label("at://x/3mxghjyx4pk2f")), principal=KIMI)
        self.assertEqual(r["status"], "admitted", r)
        # The hand-on is delivered within the turn: the commonplace hears it silent, asking no one.
        [handed] = r["delivered"]
        self.assertEqual((handed["status"], handed["result"]["label"], handed["receipt"]["delivery"]["from"]["intent"]),
                         ("admitted", "silent", r["receipt"]["identity"]["intent"]), handed)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(self.host.send(op="world-status")["hour"]["interpretations"], 0)


class HandedOnToHob(test_chain.Chain):
    """Rehearsal run 7 bells handed every conversational reply to the commonplace's model, 127 of
    132 of them "not addressed"; FLEX §2 replaced the mention gate by the host's reach and one
    attempt. A reply a card handed on (it has no policy of its own) is read once by hob, against
    THAT card's offered forms only; hob's none is silence, its ask the question over the card's
    first spell. What hob is offered is what inspect's `offered` gives the speaker."""
    policy = test_policy.PolicyObject.policy

    def setUp(self):
        super().setUp()
        self.policy()
        make_commonplace(self, "policy", doors=[])
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))

    def say(self, text, ident):
        """A reply to the bell, handed on; the pending interpretations after the delivery."""
        r = self.turn("bell", "receive", record(text=label(text), post=label("at://x/" + ident)), principal=KIMI, identity=ident, reach="mention")
        # A reply to the bell itself that fits none of its forms gets the bell's card once an hour
        # (the commonplace's `due`), then nothing; either way the prose is handed on.
        first, self.answered = not getattr(self, "answered", False), True
        self.assertEqual((r["status"], r["result"]["label"], len(r.get("offers", []))), ("admitted", "silent", 1 if first else 0), r)
        self.deliver_all()
        return self.host.send(op="world-interpretations")["pending"]

    def settle(self, raw):
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"], reply={"status": "replied", "json": None, "raw": raw, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return resumed

    def root(self, text, ident, who=KIMI):
        """A reply to the commonplace itself; the greeting first when the speaker has none yet."""
        return self.turn("commonplace", "receive", record(text=label(text), post=label("at://x/" + ident)), principal=who, reach="mention")

    def greeted(self):
        self.assertEqual(self.root("hello", "h0")["status"], "suspended")
        self.assertTrue(self.settle("none")["receipt"]["offers"][-1]["text"].startswith(GREETING))

    def add(self, label_, to):
        self.assertEqual(self.turn("commonplace", "door", record(label=label(label_), to=label(to)), principal="ember")["result"]["label"], "done")

    def test_chatter_under_a_bell_reaches_hob_once_and_none_is_silence(self):
        """The old gate let chatter cost nothing; now it reaches hob (unless the host's reach says
        not addressed) with the bell's forms alone, and hob's none ends it with no card."""
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Record"),
                           entry="initial", seed=anthology_seed("ember"), law=genesis.RECORD_LAW)
        self.assertEqual(r["status"], "created", r)
        self.add("ANTHOLOGY", "anthology")
        [pending] = self.say("What a lovely evening it is; thank you for this.", "c1")
        self.assertEqual([o["action"] for o in pending["offers"]], ["rain", "strike", "ring"], pending["offers"])
        quiet = self.settle("none")
        self.assertEqual((quiet["status"], quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("admitted", "silent", []), quiet)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_hobs_ask_under_a_bell_is_the_question_over_the_bells_first_spell(self):
        [_] = self.say("hm, what happens when I do that?", "c1")
        asked = self.settle("ask: rain on it, or ring it?")
        self.assertEqual((asked["status"], asked["result"]["label"]), ("admitted", "unclear"), asked)
        [card] = [o["text"] for o in asked["receipt"]["offers"]]
        self.assertEqual(card, "hob: not a spell as said; the spell is below.\n\n    delvetalk bell rain\n    text: <text, 1 to 120 characters>\n", card)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_hob_at_the_root_is_offered_each_doors_forms_and_no_helper_or_protocol_method(self):
        """Rehearsal run 10, finding 2: `reading` (a scene), `played` (Table) and `publishPage` with
        its `page` field were learned as words. Only a door's forms are offered; `choose` (a room
        form) is."""
        make_room(self, "rooms", **room_seed("The Moss Gate"))
        self.make("table", closure("Table"), record())
        self.add("ROOMS", "rooms")
        self.add("PLAY", "table")
        self.greeted()
        self.assertEqual(self.root("the reading was lovely, the match was played well, page: the second one", "r1")["status"], "suspended")
        [pending] = self.host.send(op="world-interpretations")["pending"]
        actions = [o["action"] for o in pending["offers"]]
        self.assertIn("choose", actions)
        for helper in ("reading", "played", "publishPage"):
            self.assertNotIn(helper, actions)
        self.settle("none")
        # Not a method: `played` took the State first, so a turn naming it wrote any result it
        # liked; now the object's own state is its first argument and does not fit a Result.
        self.assertEqual(self.turn("table", "played", record(), principal=KIMI, identity="forge")["status"], "refused")


    def test_a_handed_on_reply_is_read_against_its_card_alone_and_the_same_words_at_the_hub_against_every_door(self):
        """Run 8: 21 hand-ons were "garden" and "cistern" in the garden's own planting threads.
        FLEX §2 drops the family exclusion: hob is offered the bell's own forms and nothing else;
        the same words under the hub are offered every door's forms (the garden's plant too)."""
        town_garden(self.host.send)
        self.add("GARDEN", "garden")
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("garden/bell/1", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        say = lambda text, ident: self.turn("garden/bell/1", "receive", record(text=label(text), post=label("at://x/" + ident)), principal=KIMI, identity=ident, reach="mention")
        r = say("The garden is lovely tonight, and the rain on this cistern bell was soft.", "f1")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "silent"), r)
        self.assertTrue(r["offers"][0]["text"].startswith("A silver bell"), r)  # the bell's card, once an hour
        self.deliver_all()
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual({o["card"] for o in pending["offers"]}, {"garden/bell/1"}, pending["offers"])
        self.assertEqual(self.settle("none")["result"]["label"], "silent")
        # The same words under the hub are offered every door's forms and the first card's under each
        # (the garden's plant and the bell's rain: the arc the menu prints).
        self.greeted()
        hub = self.root("Could I rain on the lighthouse bell?", "h2")
        self.assertEqual(hub["status"], "suspended", hub)
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual({(o["card"], o["action"]) for o in pending["offers"]}, {("garden", "plant"), ("garden", "dig"), ("garden", "lines"),
                                                                                 ("garden/bell/1", "rain"), ("garden/bell/1", "strike"), ("garden/bell/1", "ring")}, pending["offers"])

    def test_the_owners_door_actions_are_offered_to_the_planter_alone(self):
        """Rehearsal run 11, finding 1: a bell's `door {label, to}` form, its planter's, was the only
        trigger for 8 of 49 interpretations. hob is offered only what inspect's `offered` gives the
        speaker: a stranger's reading of a bell has rain, ring and strike; the planter's adds
        door and undoor."""
        town_garden(self.host.send)
        self.add("GARDEN", "garden")
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("garden/bell/1", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        offered = {}
        for who in (KIMI, GLM):
            r = self.turn("garden/bell/1", "receive", record(text=label("Which door is the anthology behind?"), post=label("at://x/" + who[-4:])), principal=who, identity=who[-4:], reach="mention")
            self.assertEqual(r["status"], "admitted", r)
            self.deliver_all()
            [pending] = self.host.send(op="world-interpretations")["pending"]
            offered[who] = [o["action"] for o in pending["offers"]]
            self.settle("none")
        self.assertEqual(offered[KIMI], ["rain", "strike", "ring"])
        self.assertEqual(offered[GLM], ["rain", "strike", "ring", "door", "undoor"])

    def test_a_new_door_is_offered_to_hob_at_once(self):
        self.make("lantern", closure("Lantern"), record())
        self.add("ANTHOLOGY", "anthology")
        self.greeted()
        self.assertEqual(self.root("Is the lantern lit tonight?", "c1")["status"], "suspended")
        [pending] = self.host.send(op="world-interpretations")["pending"]
        before = {o["card"] for o in pending["offers"]}
        self.assertNotIn("lantern", before)
        self.settle("none")
        self.add("LANTERN", "lantern")
        self.assertEqual(self.root("Is the lantern lit tonight?", "c2")["status"], "suspended")
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual({(o["card"], o["action"]) for o in pending["offers"] if o["card"] == "lantern"}, {("lantern", "light"), ("lantern", "watch")}, pending["offers"])
        self.settle("none")


class AnthologyReachable(test_chain.Chain):
    """Run 5, finding 4: the anthology takes written lines from anyone; only its keeper admits
    them, by number. The model's write spell reaching it is test_archive's four lines."""

    def say(self, obj, text, who):
        return self.turn(obj, "receive", record(text=label(text), post=label("at://x/" + who[-4:])), principal=who, reach="mention")

    def test_the_owner_admits_by_number_and_a_stranger_is_refused_by_name(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Record"),
                           entry="initial", seed=anthology_seed("ember"), law=genesis.RECORD_LAW)
        self.assertEqual(r["status"], "created", r)
        for who, line in ((KIMI, "the merchant tips his hat"), (GEMINI, "a splash for every refusal")):
            submitted = self.say("anthology", "delvetalk anthology write\ntext: " + line, who)
            self.assertEqual(submitted["receipt"]["offers"][0]["to"], who)  # the anthology as it now stands, to its author
        refused = self.say("anthology", "delvetalk anthology admit / number: 2", GLM)
        self.assertEqual((refused["status"], refused["result"]["label"]), ("admitted", "refused"), refused)
        self.assertTrue(refused["offers"][0]["text"].startswith("refused notKeeper: Only the keeper, ember, admits\n"), refused)
        self.assertEqual(self.host.send(op="world-principal", principal="transport", did="ember", handle="ember.delve.town")["status"], "principal")
        admitted = self.say("anthology", "delvetalk anthology admit / number: 2", "ember")
        self.assertEqual(admitted["offers"][0]["text"], "#2 admitted: a splash for every refusal\n")
        card = self.say("anthology", "", GLM)["offers"][0]["text"]
        self.assertIn("#1 [pending] …vnmpir6d: the merchant tips his hat\n", card)
        self.assertNotIn("anthology admit", card)  # the usage lists only what the host offers this reader
        # The owner who admitted is named by the handle stored at admission, to every reader.
        self.assertTrue(card.startswith("THE ANTHOLOGY; keeper ember.delve.town"), card)
        self.assertIn("#2 [admitted] …%s: a splash for every refusal\n" % GEMINI[-8:], card)

if __name__ == "__main__":
    unittest.main()
