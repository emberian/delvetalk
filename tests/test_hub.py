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
door's form goes to that door, `unclear: not addressed` gets no offer, and a miss (a rain no door
offers, or a value missing) is answered once with hob's fixed line over the doors.

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
from tests.wire import cast_refusal, field, label, nat, record, reference, rows
from tests.bend import closure

POSTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rehearsal", "fixtures", "posts.json")
GLM, GEMINI, KIMI = "did:plc:nmjdxe6fex23zslnnbwgruj3", "did:plc:ubtqb43nq7u6jlibkzlobkuu", "did:plc:j2hnfjwlnm2mau24vnmpir6d"


ASKED = "hob: no door takes that as said. The doors:\nKINDS\n"


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


    def test_a_first_request_is_read_by_hob_and_runs_on_its_door(self):
        """A principal's first prose that asks for something is read by hob and plants; no menu follows it."""
        self.policy()
        self.commonplace("policy")
        asked = self.say("please plant something amber for moths", GLM)
        self.assertEqual(asked["status"], "suspended", asked)
        resumed = self.interpret("delvetalk garden plant\nseed: something for moths\ncolour: amber")
        self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "passed"), resumed)
        texts = [o["text"] for o in resumed["receipt"]["offers"]]
        self.assertEqual(len(texts), 1, texts)
        self.assertIn("Planted, ", texts[0])
        [bell] = self.children()
        self.assertEqual(self.seed_of(bell), ("something for moths", "amber"))
        self.assertEqual(self.say("hello", GLM)["status"], "suspended")
        quiet = self.interpret("none")
        self.assertEqual((quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("silent", []), quiet)

    def test_with_a_policy_prose_is_read_once_by_hob_against_the_doors_forms(self):
        """FLEX §2: every prose reply to the root with a policy goes to hob, once, offered every
        door's forms; there is no mention gate and no second attempt. hob's ask is the question
        over the doors, its none quiet."""
        self.policy()
        self.commonplace("policy")
        planted = self.turn("garden", "receive", record(text=label("delvetalk garden plant / colour: silver / seed: a fern"), post=label("at://x/p")), principal=GLM)
        self.assertEqual(planted["result"]["label"], "made", planted)
        self.deliver_all()
        self.assertEqual(self.say(post("3mxghh4qis22f"), KIMI)["status"], "suspended")
        asked = self.interpret("ask: which bell should the rain fall on?")
        self.assertEqual((asked["status"], asked["result"]["label"]), ("admitted", "unclear"), asked)
        [card] = [o["text"] for o in asked["receipt"]["offers"]]
        self.assertTrue(card.startswith(ASKED), card)
        self.assertIn(
            "\nGARDEN\n"
            "  delvetalk garden plant / seed: a fern that remembers yesterday / colour: silver\n"
            "  » a bell, garden/bell/N; you hear when it rings\n", card)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        # hob shows no card (docs/OVERHAUL.md §2: four answers): `card` is prose with no spell, silence.
        self.assertEqual(self.say("is there a map of the town?", KIMI, uri="at://x/post/4")["status"], "suspended")
        carded = self.interpret("card")
        self.assertEqual((carded["result"]["label"], carded["receipt"].get("offers", [])), ("silent", []), carded)
        # hob's none is quiet: nothing offered.
        self.assertEqual(self.say("is the garden open on the wiki today?", KIMI, uri="at://x/post/3")["status"], "suspended")
        quiet = self.interpret("none")
        self.assertEqual((quiet["status"], quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("admitted", "silent", []), quiet)

    def test_chatter_reaches_hob_and_its_none_is_silence(self):
        """The mention gate is gone: prose naming no door is still hob's to read (the host's reach
        decides whether it was addressed at all); hob's `none` is silence."""
        self.policy()
        self.commonplace("policy")
        chatter = self.say("lovely weather on the wiki today", KIMI, uri="at://x/post/2")
        self.assertEqual(chatter["status"], "suspended", chatter)
        quiet = self.interpret("none")
        self.assertEqual((quiet["status"], quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("admitted", "silent", []), quiet)

    def test_a_spell_that_does_not_fit_comes_back_as_hobs_question(self):
        """A rain no door offers is a spell that does not fit: the host answers `unclear` with the
        reason as the need, and the commonplace asks it over the doors, once."""
        self.policy()
        self.commonplace("policy")
        self.turn("garden", "plant", record(colour=label("silver"), seed=label("a fern")), principal=GLM)  # the bell whose rain the post names
        self.deliver_all()
        self.assertEqual(self.say(post("3mxghh4qis22f"), KIMI)["status"], "suspended")
        missed = self.interpret("delvetalk garden rain\ntext: a fine gray drizzle")
        self.assertEqual((missed["status"], missed["result"]["label"]), ("admitted", "unclear"), missed)
        [card] = [o["text"] for o in missed["receipt"]["offers"]]
        self.assertTrue(card.startswith(ASKED), card)
        self.assertIn(
            "\nGARDEN\n"
            "  delvetalk garden plant / seed: a fern that remembers yesterday / colour: silver\n"
            "  » a bell, garden/bell/N; you hear when it rings\n", card)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_prose_in_a_turn_with_no_reach_costs_no_model(self):
        """The host's reach (HOST-HANDOFF 118): an interpret in a turn with no reach answers
        `unclear: not addressed` at once, so the commonplace is quiet and nothing is pending."""
        self.policy()
        self.commonplace("policy")
        r = self.turn("commonplace", "receive", record(text=label("what a lovely evening"), post=label("at://x/post/9")), principal=KIMI)
        self.assertEqual((r["status"], r["result"]["label"], r.get("offers", [])), ("admitted", "silent", []), r)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_hobs_ask_is_the_fixed_line_over_every_door(self):
        """hob asks once: VOICE's fixed line (never the model's question, which may carry its
        reasoning: playtest 68746) over every door, to type from. No second attempt follows."""
        self.policy()
        self.commonplace("policy")
        self.assertEqual(self.say("Could the tide wake me every morning?", KIMI)["status"], "suspended")
        missed = self.interpret("ask: how often?")
        self.assertEqual((missed["status"], missed["result"]["label"]), ("admitted", "unclear"), missed)
        [card] = [o["text"] for o in missed["receipt"]["offers"]]
        self.assertTrue(card.startswith(ASKED), card)
        self.assertNotIn("how often", card)
        self.assertEqual([l for l in card.split("\n") if l and not l.startswith((" ", "hob"))][:3], ["KINDS", "PORCH", "WORKSHOP"])
        self.assertIn("\nTIDE\n  delvetalk tide rules\n  » what happens at each hourly tick\n", card)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_several_spells_in_one_reply_each_run_in_order_with_its_result(self):
        """docs/MENU.md §2.2: the model answers each spell a reply holds, one per line starting
        delvetalk; the host answers `proposals {items}` and the commonplace runs each as this turn,
        listing what came of each (a misfit is named, never run)."""
        self.policy()
        self.commonplace("policy")
        made = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Record"),
                              entry="initial", seed=anthology_seed("ember"), law=genesis.RECORD_LAW)
        self.assertEqual(made["status"], "created", made)
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

    def test_hob_reads_several_spells_against_the_doors_forms(self):
        """A reply of several spells runs each in order, hob offered the garden's forms."""
        self.policy()
        self.commonplace("policy")
        asked = self.say("plant a fern and a moss", KIMI)
        self.assertEqual(asked["status"], "suspended", asked)
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertIn("garden", {o["card"] for o in pending["offers"]}, pending["offers"])
        r = self.interpret("delvetalk garden plant\nseed: a fern\ncolour: silver\ndelvetalk garden plant\nseed: a moss\ncolour: amber")
        self.assertEqual(r["result"]["label"], "several", r)
        self.assertEqual([self.seed_of(b) for b in self.children()], [("a fern", "silver"), ("a moss", "amber")])

    def test_a_direct_replys_none_is_silence_every_time(self):
        """The play page: words typed to the commonplace itself (no post). Every such reply reaches
        hob (one attempt); its none is silence, whenever it is said and by whomever."""
        self.policy()
        self.commonplace("policy")
        direct = lambda text: self.turn("commonplace", "receive", record(text=label(text), post=label("")), principal=KIMI, reach="direct")
        for text in ("hello there", "what a lovely evening", "thank you all", "see you tomorrow"):
            self.assertEqual(direct(text)["status"], "suspended")
            r = self.interpret("none")
            self.assertEqual((r["status"], r["result"]["label"], r["receipt"].get("offers", [])), ("admitted", "silent", []), r)
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
        self.assertEqual(say("hello")["result"]["label"], "silent")
        studio = say("STUDIO")
        self.assertEqual(studio["offers"][0]["text"], "STUDIO\n" + STUDIO[1] + "\n")
        planted = say("plant: a lamp for moths\ncolour: amber")
        self.assertEqual(planted["result"]["label"], "passed", planted)
        # A field line naming only the owner's `undoor` is prose to the commonplace, never its spell.
        label_line = say("label: moth")
        self.assertEqual((label_line["status"], label_line["result"]["label"], label_line.get("offers", [])), ("admitted", "silent", []), label_line)


class BellsHearVerbsOrNothing(test_chain.Chain):
    """Rehearsal run 6 lost anthology lines posted under glm's planting; run 7 counted 127 of 132
    prose replies under bells "not addressed". A card hears a verb or nothing: prose at a bell gets
    no card, no offer and no hand-on, and no model is asked."""
    policy = test_policy.PolicyObject.policy

    def test_replies_under_glms_planting_are_silent_at_the_bell(self):
        self.policy()
        make_commonplace(self, "policy", doors=[])
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        for rkey, who in (("3mxghjyx4pk2f", KIMI), ("3mxghjmm6zc2f", GLM)):
            for reach in ("mention", None):
                r = self.turn("bell", "receive", record(text=label(post(rkey)), post=label("at://x/" + rkey)), principal=who, reach=reach)
                self.assertEqual((r["status"], r["result"]["label"], r.get("offers", []), r.get("delivered", [])), ("admitted", "silent", [], []), r)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(self.host.send(op="world-status")["hour"]["interpretations"], 0)
        self.assertEqual(rows(field(self.state("bell"), "rains")), [])


class RootReadsDoorForms(test_chain.Chain):
    """FLEX §2: prose at the commonplace is read once by hob, offered what inspect's `offered` gives
    the speaker of each door's card and of the first cards under it; hob's none is silence."""
    policy = test_policy.PolicyObject.policy

    def setUp(self):
        super().setUp()
        self.policy()
        make_commonplace(self, "policy", doors=[])
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))

    def settle(self, raw):
        [item] = self.host.send(op="world-interpretations")["pending"]
        settled = self.host.send(op="world-interpretation", id=item["id"], reply={"status": "replied", "json": None, "raw": raw, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return resumed

    def root(self, text, ident, who=KIMI):
        """A reply to the commonplace itself."""
        return self.turn("commonplace", "receive", record(text=label(text), post=label("at://x/" + ident)), principal=who, reach="mention")

    def add(self, label_, to):
        self.assertEqual(self.turn("commonplace", "door", record(label=label(label_), to=label(to)), principal="ember")["result"]["label"], "done")

    def test_hob_at_the_root_is_offered_each_doors_forms_and_no_helper_or_protocol_method(self):
        """Rehearsal run 10, finding 2: `reading` (a scene), `played` (Table) and `publishPage` with
        its `page` field were learned as words. Only a door's forms are offered; `choose` (a room
        form) is."""
        make_room(self, "rooms", **room_seed("The Moss Gate"))
        self.make("table", closure("Table"), record())
        self.add("ROOMS", "rooms")
        self.add("PLAY", "table")
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

    def test_the_root_offers_every_door_and_the_first_card_under_each(self):
        """hob is offered every door's forms and the first card's under each (the garden's plant
        and the bell's rain: the arc the menu prints)."""
        town_garden(self.host.send)
        self.add("GARDEN", "garden")
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("garden/bell/1", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        hub = self.root("Could I rain on the lighthouse bell?", "h2")
        self.assertEqual(hub["status"], "suspended", hub)
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual({(o["card"], o["action"]) for o in pending["offers"]}, {("garden", "plant"), ("garden", "dig"), ("garden", "lines"),
                                                                                 ("garden/bell/1", "rain"), ("garden/bell/1", "ring")}, pending["offers"])

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
            r = self.root("Which door is the anthology behind?", who[-4:], who)
            self.assertEqual(r["status"], "suspended", r)
            [pending] = self.host.send(op="world-interpretations")["pending"]
            offered[who] = [o["action"] for o in pending["offers"] if o["card"] == "garden/bell/1"]
            self.settle("none")
        self.assertEqual(offered[KIMI], ["rain", "ring"])
        self.assertEqual(offered[GLM], ["rain", "ring", "door", "undoor"])

    def test_a_new_door_is_offered_to_hob_at_once(self):
        self.make("lantern", closure("Lantern"), record())
        self.add("ANTHOLOGY", "anthology")
        self.assertEqual(self.root("Is the lantern lit tonight?", "c1")["status"], "suspended")
        [pending] = self.host.send(op="world-interpretations")["pending"]
        before = {o["card"] for o in pending["offers"]}
        self.assertNotIn("lantern", before)
        self.settle("none")
        self.add("LANTERN", "lantern")
        self.assertEqual(self.root("Is the lantern lit tonight?", "c2")["status"], "suspended")
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual({(o["card"], o["action"]) for o in pending["offers"] if o["card"] == "lantern"}, {("lantern", "light")}, pending["offers"])
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
        self.assertEqual(cast_refusal(refused), ("notKeeper", "Only the keeper, ember, admits"), refused)
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
