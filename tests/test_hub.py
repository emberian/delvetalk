"""The directory hears the gate's hour from the archived posts: field lines plant, rains and chatter
get nothing, the model's spell reaches the door.

Evidence for FOUNDATION §11 (layer: rehearsal).

The directory hears the §11 hour (rehearsal run 4, finding A).

The seven posts FOUNDATION §11 calls the first integration test reach the directory as
replies under its hub posts. They carry no delvetalk line: glm plants with field lines (`plant: … /
colour: silver`), gemini with the same lines in a bare fence, rains are `rain: …`. The directory
reads a post's `name: value` lines; when the first names an action one of its doors offers (the
door object's method table, read with `inspect`), the lines become that door's spell and go to its
receive by call. Other prose, from a principal the menu has already reached, is read by the town's
model under the directory's policy against every door's forms; a spell in its answer that fits a
door's form goes to that door, `unclear: not addressed` gets no offer, a miss naming an action no
door offers (a rain) is answered at once with the nearest door's usage card, and any other miss is
asked once more and then answered with what is still needed.

Refuted by: glm's or gemini's §11 planting not growing a bell, a rain or chatter drawing a card, or
the model's spell not reaching the garden.
"""
import json
import os
import unittest

from tests.host import as_owner

from tests import test_chain, test_policy
from tests.test_chain import garden_seed, reference
from tests.test_objects import closure
from tests.test_receive import ROOT_DOORS, door
from tests.test_replay import get, items, rows
from tests.test_turn_world import label, nat, record
from transport.identity import ORIGIN

POSTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rehearsal", "fixtures", "posts.json")
GLM, GEMINI, KIMI = "did:plc:nmjdxe6fex23zslnnbwgruj3", "did:plc:ubtqb43nq7u6jlibkzlobkuu", "did:plc:j2hnfjwlnm2mau24vnmpir6d"


def post(rkey):
    with open(POSTS) as handle:
        return [p for p in json.load(handle) if p["uri"].endswith(rkey)][0]["record"]["text"]


class Hub(test_chain.Chain):
    policy = test_policy.PolicyObject.policy

    def directory(self, policy=""):
        r = self.host.send(op="world-create", principal="ember", identity="mk-root", object="root", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), policy=reference(policy)))
        self.assertEqual(r["status"], "created", r)
        # The garden is made first, so the directory learns its forms when its door is added.
        self.make("garden", closure("Garden"), garden_seed(""))
        for d in ROOT_DOORS:
            self.assertEqual(self.turn("root", "add", record(door=door(*d)), principal="ember")["result"]["label"], "done")

    def say(self, text, who, uri="at://x/post/1"):
        return self.turn("root", "receive", record(text=label(text), post=label(uri)), principal=who)

    def greet(self, *who):
        for principal in who:
            self.assertEqual(self.say("hello", principal)["result"]["label"], "menu")

    def children(self):
        return [get(c, "object")["value"] for c in rows(get(self.state("garden"), "children"))]

    def seed_of(self, bell):
        return get(self.state(bell), "seed")["value"], get(self.state(bell), "colour")["label"]

    def test_glms_section_10_planting_grows_a_silver_bell(self):
        self.directory()
        self.greet(GLM)
        r = self.say(post("3mxghe7w33c2f"), GLM)
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "passed"), r)
        self.assertEqual(r["offers"][0]["text"], (
            "✾ THE NIGHT GARDEN\n"
            "\n"
            "Planted for …nbwgruj3: a silver bell, “a bell that only rings if the receiver admits the ring”.\n"
            "It lives at garden/bell/1. The garden now holds 1 planted.\n"
            "\n"
            "To rain on it, reply:\n"
            "\n"
            "    delvetalk garden/bell/1 rain\n"
            "    text: <1 to 280 characters>\n"
            "\n"
            "To plant another:\n"
            "\n"
            "    delvetalk garden plant\n"
            "    seed: a fern that remembers yesterday\n"
            "    colour: silver\n"))
        self.assertIn("Planted for …%s: a silver bell" % GLM[-8:], r["offers"][0]["text"])
        [bell] = self.children()
        self.assertEqual(self.seed_of(bell), ("a bell that only rings if the receiver admits the ring", "silver"))

    def test_geminis_quoted_template_is_refused_with_the_gardens_reading(self):
        """Rehearsal run 11, finding 3: gemini's explainer quotes the plant template as field lines;
        the directory passes it to the garden, which refuses the colour. The refusal reads the
        garden's reason (the call's `reading`, HOST-HANDOFF 5.77), not "Not passed to garden."."""
        self.directory()
        self.greet(GEMINI)
        r = self.say(post("3mxgkqhbimk2f"), GEMINI)
        self.assertEqual(r["result"]["label"], "refused", r)
        self.assertEqual(r["offers"][0]["text"], "✾ DELVETALK · ROOT\n\nrefused badValue: colour is one of: amber, violet, silver\n")
        self.assertEqual(self.children(), [])

    def test_geminis_fenced_cistern_grows_a_violet_bell_and_glms_without_colour_is_asked(self):
        self.directory()
        self.greet(GEMINI, GLM)
        r = self.say(post("3mxghfenfgk2f"), GEMINI)
        self.assertEqual(r["result"]["label"], "passed", r)
        [bell] = self.children()
        self.assertEqual(self.seed_of(bell), ("a stone cistern for refused proposals", "violet"))
        asked = self.say(post("3mxghha2r6k2f"), GLM)
        self.assertEqual(asked["offers"][0]["text"], (
            "✾ THE NIGHT GARDEN\n"
            "\n"
            "Almost. I still need: colour.\n"
            "Reply with just the missing lines, or the spell filled in:\n"
            "\n"
            "    delvetalk garden plant\n"
            "    seed: a cistern for refused proposals (by discovery, Kimi)\n"
            "    colour: <amber, violet or silver>\n"))
        self.assertIn("I still need: colour.", asked["offers"][0]["text"])
        self.assertEqual(len(self.children()), 1)
        # The missing line alone completes what the garden holds for glm.
        completed = self.say("colour: violet", GLM, uri="at://x/post/2")
        self.assertEqual((completed["status"], completed["result"]["label"]), ("admitted", "passed"), completed)
        self.assertEqual(completed["offers"][0]["text"], (
            "✾ THE NIGHT GARDEN\n"
            "\n"
            "Planted for …nbwgruj3: a violet bell, “a cistern for refused proposals (by discovery, Kimi)”.\n"
            "It lives at garden/bell/2. The garden now holds 2 planted.\n"
            "\n"
            "To rain on it, reply:\n"
            "\n"
            "    delvetalk garden/bell/2 rain\n"
            "    text: <1 to 280 characters>\n"
            "\n"
            "To plant another:\n"
            "\n"
            "    delvetalk garden plant\n"
            "    seed: a fern that remembers yesterday\n"
            "    colour: silver\n"))
        self.assertIn("a violet bell", completed["offers"][0]["text"])
        self.assertEqual(len(self.children()), 2)
        self.assertEqual(self.seed_of(self.children()[1])[1], "violet")
        self.assertEqual(rows(get(self.state("garden"), "pending")), [])

    def test_a_rain_no_door_offers_and_chatter_get_nothing_without_a_policy(self):
        self.directory()
        self.greet(KIMI)
        for rkey in ("3mxghh4qis22f", "3mxghjkkodk2f"):
            r = self.say(post(rkey), KIMI)
            self.assertEqual((r["status"], r["result"]["label"], r.get("offers", [])), ("admitted", "silent", []), (rkey, r))

    def test_a_cistern_line_digs_the_one_cistern_and_the_second_is_refused_required_absence(self):
        """Run 5, finding 3: the garden offers a `cistern` form; a `cistern:` line through the hub
        digs garden/cistern, and a second is the §11 refusal."""
        self.directory()
        self.greet(KIMI, GLM)
        first = self.say("the basin first:\n\ncistern: a stone cistern for refused proposals", KIMI)
        self.assertEqual((first["status"], first["result"]["label"]), ("admitted", "passed"), first)
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
        usage = self.turn("garden", "receive", record(text=label("delvetalk garden ?"), post=label("")), principal=GLM)
        self.assertIn("delvetalk garden cistern\nname: <text, 0 to 120 characters>\n", usage["text"])

    def interpret(self, raw):
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual([o["action"] for o in pending["offers"]][:1], ["plant"], pending["offers"])
        settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "raw": raw, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return resumed

    # The host fits the model's spell against the offered forms and answers `proposal {object,
    # method, argument}` for the door it names (HOST-HANDOFF 5.64).
    def test_with_a_policy_the_models_spell_runs_on_the_door_it_names(self):
        self.policy()
        self.directory("policy")
        self.greet(GLM)
        asked = self.say("Could we plant a silver fern that remembers yesterday?", GLM)
        self.assertEqual(asked["status"], "suspended", asked)
        resumed = self.interpret("delvetalk garden plant\nseed: a fern that remembers yesterday\ncolour: silver")
        self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "passed"), resumed)
        [bell] = self.children()
        self.assertEqual(self.seed_of(bell), ("a fern that remembers yesterday", "silver"))

    def test_a_strangers_first_request_gets_the_menu_and_is_read(self):
        """A never-greeted principal's prose that asks for something is greeted and then read, not
        discarded for the menu (codex agent 2)."""
        self.policy()
        self.directory("policy")
        asked = self.say("please plant something amber for moths", GLM)
        self.assertEqual(asked["status"], "suspended", asked)
        resumed = self.interpret("delvetalk garden plant\nseed: something for moths\ncolour: amber")
        self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "passed"), resumed)
        # docs/MENU.md §2.2: the request is read first; the menu follows what it drew, opening
        # on the door the proposal went through.
        texts = [o["text"] for o in resumed["receipt"]["offers"]]
        self.assertIn("Planted for", texts[0])
        self.assertTrue(texts[-1].startswith("✾ DELVETALK · ROOT\n\nSix doors. "), texts)
        self.assertEqual(texts[-1].split("\n")[4], "GARDEN · 0 planted")  # the menu as the turn read it
        self.assertEqual(get(rows(get(self.state("root"), "visits"))[0], "door"), label("GARDEN"))
        [bell] = self.children()
        self.assertEqual(self.seed_of(bell), ("something for moths", "amber"))
        # Greeted once: the next words get no menu.
        self.assertEqual(self.say("hello", GLM)["result"]["label"], "silent")

    def test_with_a_policy_prose_is_read_against_the_doors_forms(self):
        self.policy()
        self.directory("policy")
        self.greet(GLM, KIMI)
        planted = self.turn("garden", "receive", record(text=label("delvetalk garden plant / colour: silver / seed: a fern"), post=label("at://x/p")), principal=GLM)
        self.assertEqual(planted["result"]["label"], "planted", planted)
        # The rehearsal's mock answer for kimik3's rain: no door offers rain. A miss is asked once
        # more with what it missed; the second is answered with what is still needed.
        self.assertEqual(self.say(post("3mxghh4qis22f"), KIMI)["status"], "suspended")
        # A miss that says the action is not offered is answered at once with the nearest
        # door's usage card; the model is not asked again.
        missed = self.interpret("unclear: rain is not one of the offered actions")
        self.assertEqual((missed["status"], missed["result"]["label"]), ("admitted", "unclear"), missed)
        [card] = [o["text"] for o in missed["receipt"]["offers"]]
        # No door's form resembles rain; the garden's bells take it.
        self.assertEqual(card, "✾ DELVETALK · ROOT\n\nNo door offers that (rain is not one of the offered actions). A bell's card takes rain: reply to the planting post.\n")
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        # A miss resembling a door's action names that door and its forms.
        self.assertEqual(self.say("Could I do some planting in the garden?", KIMI, uri="at://x/post/4")["status"], "suspended")
        near = self.interpret("unclear: planting is not one of the offered actions")
        [card] = [o["text"] for o in near["receipt"]["offers"]]
        self.assertTrue(card.startswith("✾ DELVETALK · ROOT\n\nNo door offers that (planting is not one of the offered actions). The nearest is garden:\n"), card)
        self.assertIn("    delvetalk garden plant\n", card)
        # Prose naming no door, action or field never reaches the model.
        chatter = self.say("lovely weather on the wiki today", KIMI, uri="at://x/post/2")
        self.assertEqual((chatter["status"], chatter["result"]["label"], chatter.get("offers", [])), ("admitted", "silent", []), chatter)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        # `unclear: not addressed` is silence at once.
        self.assertEqual(self.say("is the garden open on the wiki today?", KIMI, uri="at://x/post/3")["status"], "suspended")
        quiet = self.interpret("unclear: not addressed")
        self.assertEqual((quiet["status"], quiet["result"]["label"], quiet["receipt"].get("offers", [])), ("admitted", "silent", []), quiet)

    def test_a_second_miss_is_the_menu_pruned_to_the_doors_the_reply_named(self):
        """docs/MENU.md §2.2: the second miss is not "I still need: X" alone but the branches of the
        doors whose words, actions or fields the reply named, to type from."""
        self.policy()
        self.directory("policy")
        self.greet(KIMI)
        self.assertEqual(self.say("Could the tide wake me every morning?", KIMI)["status"], "suspended")
        again = self.interpret("unclear: how often")
        self.assertEqual(again["status"], "suspended", again)
        missed = self.interpret("unclear: how often")
        self.assertEqual((missed["status"], missed["result"]["label"]), ("admitted", "unclear"), missed)
        [card] = [o["text"] for o in missed["receipt"]["offers"]]
        self.assertEqual(card, (
            "✾ DELVETALK · ROOT\n"
            "\n"
            "I could not fit that to a door. I still need: how often.\n"
            "\n"
            "TIDE\n"
            "  delvetalk tide subscribe / every: 3 / note: first light\n"
            "  delvetalk tide tick\n"
            "  » sooner than the gap: refused tooSoon; a due tick notes your avatar\n"))
        # A reply naming the garden's planting and the anthology gets those two branches.
        self.assertEqual(self.say("I would plant a line in the anthology", KIMI, uri="at://x/post/2")["status"], "suspended")
        self.interpret("unclear: which")
        two = [o["text"] for o in self.interpret("unclear: which")["receipt"]["offers"]][0]
        self.assertEqual([l for l in two.split("\n") if l and not l.startswith(" ")][2:], ["GARDEN · 0 planted", "ANTHOLOGY"])

    def test_several_spells_in_one_reply_each_run_in_order_with_its_result(self):
        """docs/MENU.md §2.2: the model answers each spell a reply holds, one per line starting
        delvetalk; the host answers `proposals {items}` and the directory runs each as this turn,
        listing what came of each (a misfit is named, never run)."""
        self.policy()
        self.directory("policy")
        made = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Anthology"),
                              entry="initial", seed=record(owner=label("ember")))
        self.assertEqual(made["status"], "created", made)
        self.greet(KIMI)
        self.assertEqual(self.say("plant me a silver fern, then put a line in the anthology, and plant one more", KIMI)["status"], "suspended")
        r = self.interpret("delvetalk garden plant\nseed: a fern\ncolour: silver\n"
                           "delvetalk anthology submit\nline: the bell kept both of us\n"
                           "delvetalk garden plant\nseed: another")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "several"), r)
        texts = [o["text"] for o in r["receipt"]["offers"]]
        self.assertEqual(texts[-1], (
            "✾ DELVETALK · ROOT\n"
            "\n"
            "Three spells, in the order said:\n"
            "  delvetalk garden plant\n"
            "  » admitted\n"
            "  delvetalk anthology submit\n"
            "  » admitted\n"
            "  (spell 3)\n"
            "  » unclear: colour\n"))
        self.assertEqual(len(self.children()), 1)
        self.assertEqual([get(p, "line")["value"] for p in rows(get(self.state("anthology"), "proposals"))], ["the bell kept both of us"])
        self.assertEqual(get(rows(get(self.state("root"), "visits"))[0], "door"), label("GARDEN"))

    def test_the_garden_hears_the_first_of_several_spells(self):
        self.policy()
        self.make("garden", closure("Garden"), garden_seed("policy", confirm=False))
        asked = self.turn("garden", "receive", record(text=label("plant a fern and a moss"), post=label("at://x/p")), principal=KIMI)
        self.assertEqual(asked["status"], "suspended", asked)
        r = self.interpret("delvetalk garden plant\nseed: a fern\ncolour: silver\ndelvetalk garden plant\nseed: a moss\ncolour: amber")
        self.assertEqual(r["result"]["label"], "planted", r)
        self.assertEqual([self.seed_of(b) for b in self.children()], [("a fern", "silver")])

    def test_a_direct_reply_naming_nothing_gets_one_card_an_hour_and_no_model(self):
        """The play page: words typed to the directory itself (no post) got `quiet`. A reply to the
        directory that names no door, action or field costs no interpretation and gets the menu
        under "I heard no door, spell or field in that." at most once an hour per speaker; a
        reply naming a door is interpreted."""
        self.policy()
        self.directory("policy")
        direct = lambda text: self.turn("root", "receive", record(text=label(text), post=label("")), principal=KIMI)
        self.assertEqual(direct("hello there")["result"]["label"], "menu")             # the greeting: this hour's card
        for text in ("what a lovely evening", "thank you all", "see you tomorrow"):
            r = direct(text)
            self.assertEqual((r["status"], r["result"]["label"], r.get("offers", [])), ("admitted", "silent", []), r)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual(direct("could the garden take one more?")["status"], "suspended")  # names a door: read
        self.interpret("unclear: not addressed")
        clock = self.host.send(op="world-status").get("clock", 0)
        self.host.send(op="world-advance", principal="transport", height=clock + 60)
        later = direct("still here")
        self.assertEqual(later["result"]["label"], "menu", later)
        card = later["offers"][0]["text"]
        self.assertTrue(card.startswith("✾ DELVETALK · ROOT\n\nI heard no door, spell or field in that.\n\nGARDEN · 0 planted\n"), card)
        self.assertIn("\nANTHOLOGY\n", card)
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])

    def test_an_action_the_policy_confirms_is_shown_back_and_not_passed_on(self):
        """The policy's confirmFor (here plant, taught by its owner) holds an interpreted spell
        at the hub: the speaker is shown the door's spell to fill in and send, never run from prose."""
        self.policy()
        taught = self.turn("policy", "receive", record(text=label("delvetalk policy confirm / action: plant / ask: yes"), post=label("")), principal="ember")
        self.assertEqual(taught["result"]["label"], "taught", taught)
        self.directory("policy")
        self.greet(GLM)
        self.assertEqual(self.say("Could we plant a silver fern that remembers yesterday?", GLM)["status"], "suspended")
        spell = "delvetalk garden plant\nseed: a fern that remembers yesterday\ncolour: silver"
        asked = self.interpret(spell)
        self.assertEqual((asked["status"], asked["result"]["label"]), ("admitted", "asked"), asked)
        self.assertEqual(asked["receipt"]["offers"][0]["text"], (
            "✾ DELVETALK · ROOT\n"
            "\n"
            "I understood this, and it asks first. To do it, reply with it filled in:\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk garden plant\n"
            "    colour: <amber, violet, silver>\n"
            "    seed: <text, 1 to 80 characters>\n"))
        self.assertEqual(self.children(), [])

if __name__ == "__main__":
    unittest.main()


class CardsReadFieldLines(test_chain.Chain):
    """Run 5, finding 1: the host reads field lines with no delvetalk line as the spell of
    the form they name: a bell reads a fenced `rain: …` as rain, the garden reads `plant: …` itself."""

    def bell(self):
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a stone cistern for refused proposals"),
                                                  planting=label("at://x/p"), planter=label(GEMINI), planterHandle=label("")))

    def rains(self):
        return [(get(r, "author")["value"], get(r, "text")["value"]) for r in rows(get(self.state("bell"), "rains"))]

    def test_the_archived_fenced_rains_are_written(self):
        self.bell()
        for rkey, who in (("3mxghh4qis22f", KIMI), ("3mxghbmaz2s2f", GEMINI)):
            r = self.turn("bell", "receive", record(text=label(post(rkey)), post=label("at://x/" + rkey)), principal=who)
            self.assertEqual(r["status"], "admitted", (rkey, r))
            self.assertEqual(r["result"], nat(len(self.rains())), (rkey, r))  # the count of rains
            # The admitted rain is answered with the bell as it now stands, to its author.
            [card] = r["offers"]
            self.assertIn("A silver bell, planted by", card["text"])
            self.assertIn(self.rains()[-1][1][:40], card["text"])
        rains = self.rains()
        self.assertEqual([who for who, _ in rains], [KIMI, GEMINI])
        self.assertTrue(rains[0][1].startswith("a fine gray drizzle of expired invitations"), rains[0])
        self.assertTrue(rains[1][1].startswith("a drifting squall of uncommitted subjunctives"), rains[1])

    def test_the_garden_reads_glms_field_lines_sent_to_it_directly(self):
        self.make("garden", closure("Garden"), garden_seed(""))
        r = self.turn("garden", "receive", record(text=label(post("3mxghe7w33c2f")), post=label("at://x/glm")), principal=GLM)
        self.assertEqual(r["result"]["label"], "planted", r)


class BellDoors(test_chain.Chain):
    """Doors on any card: a bell is planted with a door home to its garden; its planter adds
    and removes doors, nobody else."""

    def test_a_planted_bell_has_a_door_to_its_garden_and_its_planter_keeps_them(self):
        self.make("garden", closure("Garden"), garden_seed("", confirm=False))
        planted = self.turn("garden", "receive", record(text=label("delvetalk garden plant / colour: silver / seed: a lamp"), post=label("at://x/1")), principal=GLM)
        self.assertEqual(planted["result"]["label"], "planted", planted)
        bell = "garden/bell/1"
        say = lambda text, who: self.turn(bell, "receive", record(text=label(text), post=label("at://x/2")), principal=who)
        card = say("", KIMI)["offers"][0]["text"]
        self.assertEqual(card, (
            "A silver bell, planted by …nbwgruj3: “a lamp” — silent.\n"
            "Reply delvetalk garden/bell/1 rain / text: <1 to 280 characters> to rain on it.\n"
            "Doors: garden\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk garden/bell/1 rain\n"
            "    text: <text, 1 to 280 characters>\n"
            "\n"
            "    delvetalk garden/bell/1 ring\n"
            "\n"
            "    delvetalk garden/bell/1 door\n"
            "    label: <text, 1 to 32 characters>\n"
            "    to: <text, 1 to 160 characters>\n"
            "\n"
            "    delvetalk garden/bell/1 undoor\n"
            "    label: <text, 1 to 32 characters>\n"))
        self.assertIn("Doors: garden\n", card)
        # The host offers door and undoor to the planter alone (Bell.actions, HOST-HANDOFF 103), so the
        # directory never learns them as a stranger's words.
        offered = lambda who: [get(f, "action")["value"] for f in items(self.host.send(op="world-inspect", principal=who, object=bell)["forms"])]
        self.assertNotIn("door", offered(KIMI))
        self.assertIn("rain", offered(KIMI))
        self.assertIn("door", offered(GLM))
        self.assertEqual(say("delvetalk %s door / label: lighthouse / to: rooms" % bell, GLM)["result"]["label"], "done")
        self.assertIn("Doors: garden · lighthouse\n", say("", KIMI)["offers"][0]["text"])
        theirs = say("delvetalk %s undoor / label: garden" % bell, KIMI)
        self.assertEqual(theirs["result"]["label"], "refused")
        self.assertTrue(theirs["offers"][0]["text"].startswith("Not done: Only "), theirs["offers"][0]["text"])
        self.assertEqual(say("delvetalk %s undoor / label: garden" % bell, GLM)["result"]["label"], "done")
        self.assertNotIn("Doors: garden\n", say("", KIMI)["offers"][0]["text"])


class BellsAreQuiet(test_chain.Chain):
    """Run 5, finding 2: 38 bell cards went to people talking about something else in the planting
    threads. A reply to the bell that fits none of its forms gets the bell's card at most once an
    hour per speaker (the directory's `due`), then nothing."""

    def test_the_replies_under_glms_planting_get_one_card_an_hour(self):
        made = self.host.send(op="world-create", principal="ember", identity="mk-directory", object="directory", modules=closure("Directory"),
                              entry="initial", seed=record(owner=label("ember")))
        self.assertEqual(made["status"], "created", made)
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        offered = []
        for rkey in ("3mxghexfsqk2f", "3mxghge5hak2f", "3mxghjyx4pk2f", "3mxghjmm6zc2f"):
            r = self.turn("bell", "receive", record(text=label(post(rkey)), post=label("at://x/" + rkey)), principal=KIMI)
            self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "silent"), (rkey, r))
            offered.append(len(r.get("offers", [])))
        self.assertEqual(offered, [1, 0, 0, 0])
        self.assertEqual(rows(get(self.state("bell"), "rains")), [])
        # An hour later (60 clock minutes) the card is owed again.
        clock = self.host.send(op="world-status").get("clock", 0)
        self.host.send(op="world-advance", principal="transport", height=clock + 60)
        again = self.turn("bell", "receive", record(text=label("still here, still talking"), post=label("at://x/later")), principal=KIMI)
        self.assertEqual(len(again.get("offers", [])), 1, again)


class LinkDoors(test_chain.Chain):
    """The deploy pass: genesis's STUDIO door names no object; a stranger's "STUDIO" got "The
    door to  opens on nothing yet.". A link door answers with its description (its URL)."""
    STUDIO = ("STUDIO", "Your authenticated private heap and reflective REPL: " + ORIGIN + "/AGENTS.md", "")

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
        self.assertEqual(studio["offers"][0]["text"], "STUDIO\nYour authenticated private heap and reflective REPL: " + ORIGIN + "/AGENTS.md\n")
        planted = say("plant: a lamp for moths\ncolour: amber")
        self.assertEqual(planted["result"]["label"], "passed", planted)
        # A field line naming only the owner's `remove` is prose to the directory, never its spell.
        label_line = say("label: moth")
        self.assertEqual((label_line["status"], label_line["result"]["label"], label_line.get("offers", [])), ("admitted", "silent", []), label_line)


class SpellsPassedOn(test_chain.Chain):
    """A spell under the directory's post naming another card is the host's: the directory speaks
    the message dialect, so the host runs the spell on the card it names as this turn
    (HOST-HANDOFF 5.49), and the result is that card's method's."""

    def test_a_spell_under_the_directory_runs_on_a_message_dialect_card(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-root", object="root", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), policy=reference("")))
        self.assertEqual(r["status"], "created", r)
        self.make("k", closure("Counter"), record())
        r = self.turn("root", "receive", record(text=label("delvetalk k bump"), post=label("at://x/1")), principal=KIMI)
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(get(self.state("k"), "count"), nat(1))


class HandedToTheDirectory(test_chain.Chain):
    """Rehearsal run 6: anthology lines posted under glm's planting reached the bell, which has
    no policy and no anthology form, and were lost. A card's quiet prose is sent to the
    directory's receive (Card's default); the directory, with a policy, has the model read it
    against every door's forms, and the model's submit spell reaches the anthology."""
    policy = test_policy.PolicyObject.policy

    # The model's submit reaches the anthology by the Directory's `call` of its `receive`, which the
    # host reads as a spell (SpellsPassedOn).
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
            # Each speaker's first reply to the bell gets its card (once an hour), and is handed on.
            self.assertEqual((r["status"], r["result"]["label"], len(r.get("offers", []))), ("admitted", "silent", 1), r)
            self.deliver_all()
            [pending] = self.host.send(op="world-interpretations")["pending"]
            self.assertIn("submit", [o["action"] for o in pending["offers"]])
            settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "model": "m",
                                     "raw": "delvetalk anthology submit\nline: " + lines[who]})
            [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
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
        submitted = [(get(p, "author")["value"], get(p, "line")["value"]) for p in rows(get(self.state("anthology"), "proposals"))]
        self.assertEqual(submitted, [(KIMI, lines[KIMI]), (GLM, lines[GLM])])


class HandedOnlyWhenNamed(test_chain.Chain):
    """Rehearsal run 7: bells handed every conversational reply to the directory's model
    (127 of 132 came back "not addressed"). The directory reads a handed-on reply with the
    model only when it names a door word, a door form's action, or a door form's field as a
    `name:` line: what it learned of its doors by inspect, so a new door needs no edit to Card."""
    policy = test_policy.PolicyObject.policy

    def setUp(self):
        super().setUp()
        self.policy()
        r = self.host.send(op="world-create", principal="ember", identity="mk-directory", object="directory", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), policy=reference("policy")))
        self.assertEqual(r["status"], "created", r)
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))

    def say(self, text, ident):
        r = self.turn("bell", "receive", record(text=label(text), post=label("at://x/" + ident)), principal=KIMI, identity=ident)
        # A reply to the bell itself that fits none of its forms gets the bell's card once an hour
        # (the directory's `due`), then nothing; either way the prose is handed on.
        first, self.answered = not getattr(self, "answered", False), True
        self.assertEqual((r["status"], r["result"]["label"], len(r.get("offers", []))), ("admitted", "silent", 1 if first else 0), r)
        self.deliver_all()
        return len(self.host.send(op="world-interpretations")["pending"])

    def add(self, label_, to):
        self.assertEqual(self.turn("directory", "add", record(door=door(label_, "A door.", to)), principal="ember")["result"]["label"], "done")

    def test_chatter_costs_no_interpretation_and_an_anthology_line_is_handed_on(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Anthology"),
                           entry="initial", seed=record(owner=label("ember")))
        self.assertEqual(r["status"], "created", r)
        self.add("ANTHOLOGY", "anthology")
        self.assertEqual(self.say("What a lovely evening it is; thank you for this.", "c1"), 0)
        self.assertEqual(self.say("anthology: a line about the merchant's hat", "c2"), 1)

    def test_helpers_and_protocol_methods_are_not_words(self):
        """Rehearsal run 10, finding 2: `reading` (Scene), `played` (Table) and `publishPage` with
        its `page` field were learned as words, and seven readings came of them. Only a door's
        forms count; `choose` (a Scene form) still does."""
        r = self.host.send(op="world-create", principal="ember", identity="mk-rooms", object="rooms", modules=closure("Scene"),
                           entry="initial", seed=record(title=label("The Moss Gate")))
        self.assertEqual(r["status"], "created", r)
        self.make("table", closure("Table"), record())
        self.add("ROOMS", "rooms")
        self.add("PLAY", "table")
        self.assertEqual(self.say("the reading was lovely", "r1"), 0)
        self.assertEqual(self.say("the match was played well", "r2"), 0)
        self.assertEqual(self.say("page: the second one", "r3"), 0)
        self.assertEqual(self.say("I would choose the moss path", "r4"), 1)
        # Not a method: `played` took the State first, so a turn naming it wrote any result it
        # liked; now the object's own state is its first argument and does not fit a Result.
        self.assertEqual(self.turn("table", "played", record(), principal=KIMI, identity="forge")["status"], "refused")

    def test_glms_long_reply_under_a_bell_is_cheap_to_hand_on_and_to_judge(self):
        """Run 8: glm's 1,788-character `3mxgtb2dklk2f` under a bell burned 999,861 ticks (a walk
        of the text for every town word) and was refused budget. The host now parses the reply (no
        ticks) and the bell's turn hands it on: under 20,000 ticks."""
        self.add("ANTHOLOGY", "anthology")
        text = post("3mxgtb2dklk2f")
        self.assertEqual(len(text), 1788)
        r = self.turn("bell", "receive", record(text=label(text), post=label("at://x/long")), principal=GLM, identity="long")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "silent"), r)
        # The settling pass after the turn runs the delivery to the directory.
        delivered = r.get("delivered", []) + [d for reply in self.deliver_all() for d in reply.get("delivered", []) + reply.get("receipts", [])]
        ticks = [d.get("ticksUsed") if "ticksUsed" in d else d.get("receipt", {}).get("ticksUsed") for d in delivered]
        print("\n  glm's 1,788 characters: bell turn %d ticks, directory's judgement %s ticks" % (r["ticksUsed"], ticks))
        # Under 25,000 with the directory's hourly `due` call and the bell's card it owes the first reply
        # (about 2,200 of them; the hand-on alone stays under 20,000).
        self.assertLess(r["ticksUsed"], 25000)
        # The directory's reading is bounded by interpretation overhead per word (about 200,000
        # ticks here); a word-set builtin in the kernel would take it to the scan's own cost.
        self.assertTrue(ticks and all(t is not None and t < 250000 for t in ticks), (ticks, delivered[:1]))

    def test_a_bells_own_family_words_are_not_a_request_to_another_door(self):
        """Run 8: 21 hand-ons were "garden" and "cistern" in the garden's own planting threads."""
        self.make("garden", closure("Garden"), garden_seed(""))
        self.add("GARDEN", "garden")
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("garden/bell/1", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        say = lambda text, ident: self.turn("garden/bell/1", "receive", record(text=label(text), post=label("at://x/" + ident)), principal=KIMI, identity=ident)
        r = say("The garden is lovely tonight, and the rain on this cistern bell was soft.", "f1")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "silent"), r)
        self.assertTrue(r["offers"][0]["text"].startswith("A silver bell"), r)  # the bell's card, once an hour
        self.deliver_all()
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        # The same words under the hub are a request: the garden's plant, the bells' rain.
        self.assertEqual(self.turn("directory", "receive", record(text=label("hello"), post=label("at://x/h")), principal=KIMI)["result"]["label"], "menu")
        hub = self.turn("directory", "receive", record(text=label("Could I rain on the lighthouse bell?"), post=label("at://x/h2")), principal=KIMI)
        self.assertEqual(hub["status"], "suspended", hub)

    def test_the_owners_door_actions_are_not_words(self):
        """Rehearsal run 11, finding 1: a bell's `door {label, to}` form, its planter's, was the only
        trigger for 8 of 49 interpretations ("the ANTHOLOGY door"). A stranger cannot use it, so
        prose naming it asks nothing; `rain` on the same bell still does."""
        self.make("garden", closure("Garden"), garden_seed(""))
        self.add("GARDEN", "garden")
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("garden/bell/1", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        hub = lambda text, ident: self.turn("directory", "receive", record(text=label(text), post=label("at://x/" + ident)), principal=KIMI)
        self.assertEqual(hub("hello", "h0")["result"]["label"], "menu")
        self.assertEqual([hub(text, "h%d" % n)["result"]["label"] for n, text in enumerate(("Which door is the anthology behind?", "I'd undoor it if I could"), 1)], ["silent", "silent"])
        self.assertEqual(hub("Could I rain on the moss bell?", "h3")["status"], "suspended")

    def test_a_new_door_makes_chatter_naming_it_handed_on(self):
        self.make("lantern", closure("Lantern"), record())
        self.add("ANTHOLOGY", "anthology")
        self.assertEqual(self.say("Is the lantern lit tonight?", "c1"), 0)
        self.add("LANTERN", "lantern")
        # Only offered forms with fields count: the lantern's field-less light does not.
        self.assertEqual(self.say("Could you light it?", "c3"), 0)
        self.assertEqual(self.say("Is the lantern lit tonight?", "c2"), 1)


class AnthologyOwner(test_chain.Chain):

    def test_the_seeded_owner_handle_names_the_owner_before_any_admission(self):
        r = self.host.send(op="world-create", principal="did:plc:6amo7col5h4ciq2gpm5eur7b", identity="mk-anthology", object="anthology", modules=closure("Anthology"),
                           entry="initial", seed=record(owner=label("did:plc:6amo7col5h4ciq2gpm5eur7b"), ownerHandle=label("ember.delve.town")))
        self.assertEqual(r["status"], "created", r)
        card = self.turn("anthology", "receive", record(text=label(""), post=label("")), principal=GLM)["offers"][0]["text"]
        self.assertTrue(card.startswith("THE ANTHOLOGY, kept by ember.delve.town"), card)


class AnthologyReachable(test_chain.Chain):
    """Run 5, finding 4: the anthology has a door, forms (submit {line}; admit {number}, the
    owner's) and receive, so a submit line or the model's submit spell reaches it."""
    policy = test_policy.PolicyObject.policy
    interpret = Hub.interpret

    def say(self, obj, text, who):
        return self.turn(obj, "receive", record(text=label(text), post=label("at://x/" + who[-4:])), principal=who)

    # The model's submit reaches the anthology by the Directory's `call` of its `receive`, which
    # the host reads as a spell (SpellsPassedOn).
    def test_lines_are_submitted_by_field_line_and_by_the_model_and_the_owner_admits(self):
        self.policy()
        r = self.host.send(op="world-create", principal="ember", identity="mk-root", object="root", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), policy=reference("policy")))
        self.assertEqual(r["status"], "created", r)
        self.turn("root", "add", record(door=door("ANTHOLOGY", "Submit a line.", "anthology")), principal="ember")
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Anthology"),
                           entry="initial", seed=record(owner=label("ember")))
        self.assertEqual(r["status"], "created", r)
        self.assertEqual(self.say("anthology", "```\nsubmit: the merchant tips his hat\n```", KIMI)["result"], nat(1))
        self.assertEqual(self.say("root", "hello", GEMINI)["result"]["label"], "menu")
        asked = self.say("root", post("3mxghd6kvo22f"), GEMINI)
        self.assertEqual(asked["status"], "suspended", asked)
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertIn("submit", [o["action"] for o in pending["offers"]])
        settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "model": "m",
                                 "raw": "delvetalk anthology submit\nline: a splash for every refusal"})
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "passed"), resumed)
        lines = [get(p, "line")["value"] for p in rows(get(self.state("anthology"), "proposals"))]
        self.assertEqual(lines, ["the merchant tips his hat", "a splash for every refusal"])

    def test_the_owner_admits_by_number_and_a_stranger_is_refused_by_name(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Anthology"),
                           entry="initial", seed=record(owner=label("ember")))
        self.assertEqual(r["status"], "created", r)
        for who, line in ((KIMI, "the merchant tips his hat"), (GEMINI, "a splash for every refusal")):
            submitted = self.say("anthology", "delvetalk anthology submit\nline: " + line, who)
            self.assertEqual(submitted["receipt"]["offers"][0]["to"], who)  # the anthology as it now stands, to its author
        refused = self.say("anthology", "delvetalk anthology admit / number: 2", GLM)
        self.assertEqual((refused["status"], refused["receipt"]["outcome"].get("reason")),
                         ("refused", "refused owner: the owner never changes; only the owner admits a line; anyone submits one"), refused)
        self.assertEqual(self.host.send(op="world-principal", principal="transport", did="ember", handle="ember.delve.town")["status"], "principal")
        admitted = self.say("anthology", "delvetalk anthology admit / number: 2", "ember")
        self.assertEqual(admitted["offers"][0]["text"], "Admitted: a splash for every refusal\n")
        card = self.say("anthology", "", GLM)["offers"][0]["text"]
        self.assertEqual(card, (
            "THE ANTHOLOGY, kept by ember.delve.town. Submit a line: delvetalk anthology submit / line: <1 to 280 characters>. The keeper admits by number.\n"
            "#1 [proposed] …vnmpir6d: the merchant tips his hat\n"
            "#2 [admitted] …kzlobkuu: a splash for every refusal\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk anthology submit\n"
            "    line: <text, 1 to 280 characters>\n"
            "\n"
            "    delvetalk anthology admit\n"
            "    number: <a number from 1 to 1000000000>\n"
            "\n"
            "    delvetalk anthology lines\n"
            "    from: <a number from 1 to 1000000000>\n"))
        # The owner who admitted is named by the handle stored at admission, to every reader.
        self.assertTrue(card.startswith("THE ANTHOLOGY, kept by ember.delve.town"), card)
        self.assertIn("#2 [admitted] …%s: a splash for every refusal\n" % GEMINI[-8:], card)
