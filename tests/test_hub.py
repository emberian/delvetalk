"""The directory hears the §10 hour (rehearsal run 4, finding A).

The seven posts FOUNDATION section 10 calls the first integration test reach the directory as
replies under its hub posts. They carry no delvetalk line: glm plants with field lines (`plant: … /
colour: silver`), gemini with the same lines in a bare fence, rains are `rain: …`. The directory
reads a post's `name: value` lines; when the first names an action one of its doors offers (the
door object's method table, read with `inspect`), the lines become that door's spell and go to its
receive by call. Other prose, from a principal the menu has already reached, is read by the town's
model under the directory's policy against every door's forms; a spell in its answer that fits a
door's form goes to that door, `unclear: not addressed` gets no offer, and a miss (a rain no door
offers) is asked once more and then answered with what is still needed.

Refuted by: glm's or gemini's §10 planting not growing a bell, a rain or chatter drawing a card, or
the model's spell not reaching the garden."""
import json
import os
import unittest

from tests import test_chain, test_policy
from tests.test_chain import garden_seed, reference
from tests.test_objects import closure
from tests.test_receive import ROOT_DOORS, door
from tests.test_replay import get, items
from tests.test_turn_world import label, record

POSTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rehearsal", "fixtures", "posts.json")
GLM, GEMINI, KIMI = "did:plc:nmjdxe6fex23zslnnbwgruj3", "did:plc:ubtqb43nq7u6jlibkzlobkuu", "did:plc:j2hnfjwlnm2mau24vnmpir6d"


def post(rkey):
    with open(POSTS) as handle:
        return [p for p in json.load(handle) if p["uri"].endswith(rkey)][0]["record"]["text"]


class Hub(test_chain.Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None
    policy = test_policy.PolicyObject.policy

    def directory(self, policy=""):
        r = self.host.send(op="world-create", principal="ember", identity="mk-root", object="root", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), policy=reference(policy)))
        self.assertEqual(r["status"], "created", r)
        for label_, description, to in ROOT_DOORS:
            self.assertEqual(self.turn("root", "add", record(door=door(label_, description, to)), principal="ember")["result"]["label"], "done")
        self.make("garden", closure("Garden"), garden_seed(""))

    def say(self, text, who, uri="at://x/post/1"):
        return self.turn("root", "receive", record(text=label(text), post=label(uri), slot=label("")), principal=who)

    def greet(self, *who):
        for principal in who:
            self.assertEqual(self.say("hello", principal)["result"]["label"], "menu")

    def children(self):
        return [get(c, "object")["value"] for c in items(get(self.state("garden"), "children"))]

    def seed_of(self, bell):
        return get(self.state(bell), "seed")["value"], get(self.state(bell), "colour")["label"]

    def test_glms_section_10_planting_grows_a_silver_bell(self):
        self.directory()
        self.greet(GLM)
        r = self.say(post("3mxghe7w33c2f"), GLM)
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "passed"), r)
        print("\n--- root, glm's field lines ---\n" + r["offers"][0]["text"])
        self.assertIn("Planted for …%s: a silver bell" % GLM[-8:], r["offers"][0]["text"])
        [bell] = self.children()
        self.assertEqual(self.seed_of(bell), ("a bell that only rings if the receiver admits the ring", "silver"))

    def test_geminis_fenced_cistern_grows_a_violet_bell_and_glms_without_colour_is_asked(self):
        self.directory()
        self.greet(GEMINI, GLM)
        r = self.say(post("3mxghfenfgk2f"), GEMINI)
        self.assertEqual(r["result"]["label"], "passed", r)
        [bell] = self.children()
        self.assertEqual(self.seed_of(bell), ("a stone cistern for refused proposals", "violet"))
        asked = self.say(post("3mxghha2r6k2f"), GLM)
        print("--- root, glm's cistern without a colour ---\n" + asked["offers"][0]["text"])
        self.assertIn("I still need: colour.", asked["offers"][0]["text"])
        self.assertEqual(len(self.children()), 1)
        # The missing line alone completes what the garden holds for glm.
        completed = self.say("colour: violet", GLM, uri="at://x/post/2")
        self.assertEqual((completed["status"], completed["result"]["label"]), ("admitted", "passed"), completed)
        print("--- root, glm's colour: violet ---\n" + completed["offers"][0]["text"])
        self.assertIn("a violet bell", completed["offers"][0]["text"])
        self.assertEqual(len(self.children()), 2)
        self.assertEqual(self.seed_of(self.children()[1])[1], "violet")
        self.assertEqual(items(get(self.state("garden"), "pending")), [])

    def test_a_rain_no_door_offers_and_chatter_get_nothing_without_a_policy(self):
        self.directory()
        self.greet(KIMI)
        for rkey in ("3mxghh4qis22f", "3mxghjkkodk2f"):
            r = self.say(post(rkey), KIMI)
            self.assertEqual((r["status"], r["result"]["label"], r.get("offers", [])), ("admitted", "silent", []), (rkey, r))

    def test_a_cistern_line_digs_the_one_cistern_and_the_second_is_refused_required_absence(self):
        """Run 5, finding 3: the garden offers a `cistern` form; a `cistern:` line through the hub
        digs garden/cistern, and a second is the §10 refusal."""
        self.directory()
        self.greet(KIMI, GLM)
        first = self.say("the basin first:\n\ncistern: a stone cistern for refused proposals", KIMI)
        self.assertEqual((first["status"], first["result"]["label"]), ("admitted", "passed"), first)
        print("\n--- root, kimik3's cistern ---\n" + first["offers"][0]["text"])
        self.assertEqual(first["offers"][0]["text"], "✾ THE NIGHT GARDEN\n\nThe cistern is dug at garden/cistern. It keeps refusals.\n")
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="garden/cistern")["status"], "viewed")
        second = self.say("cistern: a cistern for refused proposals (by discovery, Kimi)", GLM)
        out = second["receipt"]["outcome"]
        self.assertEqual((second["status"], out["class"], out["object"]), ("refused", "requiredAbsence", "garden/cistern"), second)
        # The refusal names the root it was judged against: the creating garden, at the version the turn read.
        garden = self.host.send(op="world-view", principal="ember", object="garden")
        self.assertEqual(out["root"], "garden", out)
        public = second["public"]
        self.assertEqual((public["object"], public["root"]["object"], public["root"]["version"]),
                         ("garden/cistern", "garden", garden["version"]), public)
        usage = self.turn("garden", "receive", record(text=label("delvetalk garden ?"), post=label("")), principal=GLM)["offers"][0]["text"]
        self.assertIn("    delvetalk garden cistern\n    name: <text, 0 to 120 characters>\n", usage)

    def interpret(self, raw):
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual([o["action"] for o in pending["offers"]][:1], ["plant"], pending["offers"])
        settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "raw": raw, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = settled["resumed"]
        return resumed

    def test_with_a_policy_prose_is_read_against_the_doors_forms(self):
        self.policy()
        self.directory("policy")
        self.greet(GLM, KIMI)
        asked = self.say("Could we plant a silver fern that remembers yesterday?", GLM)
        self.assertEqual(asked["status"], "suspended", asked)
        resumed = self.interpret("delvetalk garden plant\nseed: a fern that remembers yesterday\ncolour: silver")
        self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "passed"), resumed)
        [bell] = self.children()
        self.assertEqual(self.seed_of(bell), ("a fern that remembers yesterday", "silver"))
        # The rehearsal's mock answer for kimik3's rain: no door offers rain. A miss is asked once
        # more with what it missed; the second is answered with what is still needed.
        self.assertEqual(self.say(post("3mxghh4qis22f"), KIMI)["status"], "suspended")
        again = self.interpret("unclear: rain is not one of the offered actions")
        self.assertEqual(again["status"], "suspended", again)
        missed = self.interpret("unclear: rain is not one of the offered actions")
        self.assertEqual((missed["status"], missed["result"]["label"]), ("admitted", "unclear"), missed)
        self.assertEqual([o["text"] for o in missed["receipt"]["offers"]],
                         ["✾ DELVETALK · ROOT\n\nI could not fit that to a door. I still need: rain is not one of the offered actions.\n"])
        # `unclear: not addressed` is silence at once.
        self.assertEqual(self.say("lovely weather on the wiki today", KIMI, uri="at://x/post/2")["status"], "suspended")
        quiet = self.interpret("unclear: not addressed")
        self.assertEqual((quiet["status"], quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("admitted", "silent", []), quiet)

    def test_an_action_the_policy_confirms_is_shown_back_and_not_passed_on(self):
        """The policy's confirmFor (here plant, taught by its owner) holds an interpreted spell
        at the hub: it is shown to the speaker to send, never passed on from prose."""
        self.policy()
        taught = self.turn("policy", "receive", record(text=label("delvetalk policy confirm / action: plant / ask: yes"), post=label("")), principal="ember")
        self.assertEqual(taught["result"]["label"], "done", taught)
        self.directory("policy")
        self.greet(GLM)
        self.assertEqual(self.say("Could we plant a silver fern that remembers yesterday?", GLM)["status"], "suspended")
        spell = "delvetalk garden plant\nseed: a fern that remembers yesterday\ncolour: silver"
        asked = self.interpret(spell)
        self.assertEqual((asked["status"], asked["result"]["label"]), ("admitted", "asked"), asked)
        self.assertEqual(asked["receipt"]["offers"][0]["text"], "✾ DELVETALK · ROOT\n\nI understood this, and it asks first. To do it, reply with it:\n\n" + spell + "\n")
        self.assertEqual(self.children(), [])

if __name__ == "__main__":
    unittest.main()


class CardsReadFieldLines(test_chain.Chain):
    """Run 5, finding 1: every card reads field lines with no delvetalk line through Card.route
    (Spell.bare): a bell reads a fenced `rain: …` as rain, the garden reads `plant: …` itself."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def bell(self):
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a stone cistern for refused proposals"),
                                                  planting=label("at://x/p"), planter=label(GEMINI), planterHandle=label("")))

    def rains(self):
        return [(get(r, "author")["value"], get(r, "text")["value"]) for r in items(get(self.state("bell"), "rains"))]

    def test_the_archived_fenced_rains_are_written(self):
        self.bell()
        for rkey, who in (("3mxghh4qis22f", KIMI), ("3mxghbmaz2s2f", GEMINI)):
            r = self.turn("bell", "receive", record(text=label(post(rkey)), post=label("at://x/" + rkey)), principal=who)
            self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "done"), (rkey, r))
            # The admitted rain is answered with the bell as it now stands, to its author.
            [card] = r["offers"]
            self.assertIn("A silver bell planted by", card["text"])
            self.assertIn(self.rains()[-1][1][:40], card["text"])
        rains = self.rains()
        self.assertEqual([who for who, _ in rains], [KIMI, GEMINI])
        self.assertTrue(rains[0][1].startswith("a fine gray drizzle of expired invitations"), rains[0])
        self.assertTrue(rains[1][1].startswith("a drifting squall of uncommitted subjunctives"), rains[1])

    def test_the_garden_reads_glms_field_lines_sent_to_it_directly(self):
        self.make("garden", closure("Garden"), garden_seed(""))
        r = self.turn("garden", "receive", record(text=label(post("3mxghe7w33c2f")), post=label("at://x/glm")), principal=GLM)
        self.assertEqual(r["result"]["label"], "planted", r)


class BellsAreQuiet(test_chain.Chain):
    """Run 5, finding 2: 38 bell cards went to people talking about something else in the planting
    threads. A bell answers prose naming none of its forms with no offer."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def test_the_replies_under_glms_planting_get_nothing(self):
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        for rkey in ("3mxghexfsqk2f", "3mxghge5hak2f", "3mxghjyx4pk2f", "3mxghjmm6zc2f"):
            r = self.turn("bell", "receive", record(text=label(post(rkey)), post=label("at://x/" + rkey)), principal=KIMI)
            self.assertEqual((r["status"], r["result"]["label"], r.get("offers", [])), ("admitted", "silent", []), (rkey, r))
        self.assertEqual(items(get(self.state("bell"), "rains")), [])


class LinkDoors(test_chain.Chain):
    """The deploy pass: genesis's STUDIO door names no object; a stranger's "STUDIO" got "The
    door to  opens on nothing yet.". A link door answers with its description (its URL)."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None
    STUDIO = ("STUDIO", "Your authenticated private heap and reflective REPL: https://delvetalk.fg-goose.online/AGENTS.md", "")

    def test_studio_answers_with_its_url_and_field_lines_pass_it_by(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-root", object="root", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), policy=reference("")))
        self.assertEqual(r["status"], "created", r)
        self.assertEqual(self.turn("root", "add", record(door=door(*self.STUDIO)), principal="ember")["result"]["label"], "done")
        self.assertEqual(self.turn("root", "add", record(door=door("GARDEN", "Plant something.", "garden")), principal="ember")["result"]["label"], "done")
        self.make("garden", closure("Garden"), garden_seed(""))
        say = lambda text: self.turn("root", "receive", record(text=label(text), post=label("at://x/1")), principal=KIMI)
        self.assertEqual(say("hello")["result"]["label"], "menu")
        studio = say("STUDIO")
        print("\n--- STUDIO ---\n" + studio["offers"][0]["text"])
        self.assertEqual(studio["offers"][0]["text"], "STUDIO\nYour authenticated private heap and reflective REPL: https://delvetalk.fg-goose.online/AGENTS.md\n")
        planted = say("plant: a lamp for moths\ncolour: amber")
        self.assertEqual(planted["result"]["label"], "passed", planted)


class HandedToTheDirectory(test_chain.Chain):
    """Rehearsal run 6: anthology lines posted under glm's planting reached the bell, which has
    no policy and no anthology form, and were lost. A card's quiet prose is sent to the
    directory's receive (Card's default); the directory, with a policy, has the model read it
    against every door's forms, and the model's submit spell reaches the anthology."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None
    policy = test_policy.PolicyObject.policy

    def test_two_anthology_lines_under_glms_planting_are_submitted(self):
        self.policy()
        r = self.host.send(op="world-create", principal="ember", identity="mk-directory", object="directory", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), policy=reference("policy")))
        self.assertEqual(r["status"], "created", r)
        self.turn("directory", "add", record(door=door("ANTHOLOGY", "Submit a line.", "anthology")), principal="ember")
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Anthology"),
                           entry="initial", seed=record(owner=label("ember")))
        self.assertEqual(r["status"], "created", r)
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        lines = {KIMI: "the guestbook line goes next to the ring and the hat", GLM: "a coup and an amendment both change the rules"}
        for rkey, who in (("3mxghjyx4pk2f", KIMI), ("3mxghjmm6zc2f", GLM)):
            r = self.turn("bell", "receive", record(text=label(post(rkey)), post=label("at://x/" + rkey)), principal=who)
            self.assertEqual((r["status"], r["result"]["label"], r.get("offers", [])), ("admitted", "silent", []), r)
            self.deliver_all()
            [pending] = self.host.send(op="world-interpretations")["pending"]
            self.assertIn("submit", [o["action"] for o in pending["offers"]])
            settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "model": "m",
                                     "raw": "delvetalk anthology submit\nline: " + lines[who]})
            [resumed] = settled["resumed"]
            self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "passed"), resumed)
            # The submission is answered with the anthology as it now stands, to its author.
            card = resumed["receipt"]["offers"][-1]
            self.assertEqual(card["to"], who)
            self.assertIn(lines[who], card["text"])
            # Rehearsal run 7, finding 1: the offer names the post the author replied to, through the hand-off.
            asked = r["receipt"]["identity"]["intent"]
            [offer] = [o for o in self.host.send(op="world-offers", principal=who)["offers"] if lines[who] in o["text"]]
            self.assertNotEqual(offer["identity"]["intent"], asked)
            self.assertEqual(offer["from"], {"post": asked, "principal": who, "intent": asked}, offer)
        submitted = [(get(p, "author")["value"], get(p, "line")["value"]) for p in items(get(self.state("anthology"), "proposals"))]
        self.assertEqual(submitted, [(KIMI, lines[KIMI]), (GLM, lines[GLM])])


class AnthologyReachable(test_chain.Chain):
    """Run 5, finding 4: the anthology has a door, forms (submit {line}; admit {number}, the
    owner's) and receive, so a submit line or the model's submit spell reaches it."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None
    policy = test_policy.PolicyObject.policy
    interpret = Hub.interpret

    def say(self, obj, text, who):
        return self.turn(obj, "receive", record(text=label(text), post=label("at://x/" + who[-4:])), principal=who)

    def test_lines_are_submitted_by_field_line_and_by_the_model_and_the_owner_admits(self):
        self.policy()
        r = self.host.send(op="world-create", principal="ember", identity="mk-root", object="root", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), policy=reference("policy")))
        self.assertEqual(r["status"], "created", r)
        self.turn("root", "add", record(door=door("ANTHOLOGY", "Submit a line.", "anthology")), principal="ember")
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Anthology"),
                           entry="initial", seed=record(owner=label("ember")))
        self.assertEqual(r["status"], "created", r)
        self.assertEqual(self.say("anthology", "```\nsubmit: the merchant tips his hat\n```", KIMI)["result"]["label"], "done")
        self.assertEqual(self.say("root", "hello", GEMINI)["result"]["label"], "menu")
        asked = self.say("root", post("3mxghd6kvo22f"), GEMINI)
        self.assertEqual(asked["status"], "suspended", asked)
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertIn("submit", [o["action"] for o in pending["offers"]])
        settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "model": "m",
                                 "raw": "delvetalk anthology submit\nline: a splash for every refusal"})
        [resumed] = settled["resumed"]
        self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "passed"), resumed)
        lines = [get(p, "line")["value"] for p in items(get(self.state("anthology"), "proposals"))]
        self.assertEqual(lines, ["the merchant tips his hat", "a splash for every refusal"])
        refused = self.say("anthology", "delvetalk anthology admit / number: 2", GLM)
        self.assertEqual(refused["result"]["payload"]["fields"][1]["value"], label("Only the anthology's owner admits; that is ember"))
        admitted = self.say("anthology", "delvetalk anthology admit / number: 2", "ember")
        self.assertEqual(admitted["offers"][0]["text"], "Admitted: a splash for every refusal\n")
        card = self.say("anthology", "", GLM)["offers"][0]["text"]
        print("\n--- anthology ---\n" + card)
        self.assertIn("#2 [admitted] …%s: a splash for every refusal\n" % GEMINI[-8:], card)
