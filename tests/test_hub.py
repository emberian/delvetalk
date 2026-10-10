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

from deploy import genesis
from tests.host import as_owner

from tests import test_chain, test_policy
from tests.test_chain import garden_seed, reference, town_kinds
from tests.test_laws import anthology_seed
from tests.test_objects import closure
from tests.test_receive import ROOT_DOORS, door
from tests.test_replay import get, rows
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
        town_kinds(self.host.send)
        for d in ROOT_DOORS:
            self.assertEqual(self.turn("root", "add", record(door=door(*d)), principal="ember")["result"]["label"], "done")

    def say(self, text, who, uri="at://x/post/1"):
        return self.turn("root", "receive", record(text=label(text), post=label(uri)), principal=who, reach="mention")

    def greet(self, *who):
        for principal in who:
            self.assertEqual(self.say("hello", principal)["result"]["label"], "menu")

    def children(self):
        return [get(c, "object")["value"] for c in rows(get(self.state("garden"), "children"))]

    def seed_of(self, bell):
        """A bell's seed and colour: the values kind/bell's form took when it was made."""
        made = {get(f, "name")["value"]: get(f, "value")["value"] for f in get(self.state(bell), "fields")["items"]}
        return made["seed"], made["colour"]


    def test_a_cistern_line_digs_a_cistern_and_one_on_a_taken_id_is_refused_required_absence(self):
        """Run 5, finding 3: the garden offers a `cistern` form; a `cistern:` line through the hub
        digs garden/cistern/1 through kind/cistern, and one on an id already taken is the §11 refusal."""
        self.directory()
        self.greet(KIMI, GLM)
        first = self.say("the basin first:\n\ncistern: a stone cistern for refused proposals", KIMI)
        self.assertEqual((first["status"], first["result"]["label"]), ("admitted", "passed"), first)
        self.assertEqual(first["offers"][0]["text"], "The cistern is dug at garden/cistern/1; it takes refusals.\n")
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="garden/cistern/1")["status"], "viewed")
        self.make("garden/cistern/2", closure("Counter"), record())
        second = self.say("cistern: a cistern for refused proposals (by discovery, Kimi)", GLM)
        out = second["receipt"]["outcome"]
        self.assertEqual((second["status"], out["class"], out["object"]), ("refused", "requiredAbsence", "garden/cistern/2"), second)
        # The refusal names the root it was judged against: the kind that creates, at the version the turn read.
        kind = self.host.send(op="world-view", principal="ember", object="kind/cistern")
        self.assertEqual(out["root"], "kind/cistern", out)
        public = second["public"]
        self.assertEqual((public["object"], public["root"]["object"], public["root"]["version"]),
                         ("garden/cistern/2", "kind/cistern", kind["version"]), public)
        usage = self.turn("garden", "receive", record(text=label("delvetalk garden ?"), post=label("")), principal=GLM)
        self.assertIn("delvetalk garden cistern\nname: <text, 0 to 120 characters>\n", usage["text"])

    def interpret(self, raw):
        [pending] = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual([o["action"] for o in pending["offers"]][:1], ["plant"], pending["offers"])
        settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "raw": raw, "model": "m"})
        self.assertEqual(settled["status"], "interpreted", settled)
        [resumed] = [as_owner(self.host, r) for r in settled["resumed"]]
        return resumed


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
        self.assertIn("Planted, ", texts[0])
        self.assertTrue(texts[-1].startswith("✾ DELVETALK · ROOT\n\nSeven doors. "), texts)
        self.assertEqual(texts[-1].split("\n")[3], "GARDEN · 0 planted")  # the menu as the turn read it
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


    def test_several_spells_in_one_reply_each_run_in_order_with_its_result(self):
        """docs/MENU.md §2.2: the model answers each spell a reply holds, one per line starting
        delvetalk; the host answers `proposals {items}` and the directory runs each as this turn,
        listing what came of each (a misfit is named, never run)."""
        self.policy()
        self.directory("policy")
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
            "✾ DELVETALK · ROOT\n"
            "\n"
            "Three spells, in the order said:\n"
            "  delvetalk garden plant\n"
            "  » admitted\n"
            "  delvetalk anthology write\n"
            "  » admitted\n"
            "  (spell 3)\n"
            "  » unclear: colour\n"))
        self.assertEqual(len(self.children()), 1)
        self.assertEqual([get(p, "text")["value"] for p in rows(get(self.state("anthology"), "lines"))], ["the bell kept both of us"])
        self.assertEqual(get(rows(get(self.state("root"), "visits"))[0], "door"), label("GARDEN"))

    def test_the_garden_hears_the_first_of_several_spells(self):
        self.policy()
        self.make("garden", closure("Garden"), garden_seed("policy", confirm=False))
        town_kinds(self.host.send)
        asked = self.turn("garden", "receive", record(text=label("plant a fern and a moss"), post=label("at://x/p")), principal=KIMI, reach="mention")
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
        direct = lambda text: self.turn("root", "receive", record(text=label(text), post=label("")), principal=KIMI, reach="direct")
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
    STUDIO = ("STUDIO", "Your authenticated private heap and reflective REPL: " + ORIGIN + "/AGENTS.md", "")

    def test_studio_answers_with_its_url_and_field_lines_pass_it_by(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-root", object="root", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), policy=reference("")))
        self.assertEqual(r["status"], "created", r)
        self.assertEqual(self.turn("root", "add", record(door=door(*self.STUDIO)), principal="ember")["result"]["label"], "done")
        self.assertEqual(self.turn("root", "add", record(door=door("GARDEN", "Plant something.", "garden")), principal="ember")["result"]["label"], "done")
        self.make("garden", closure("Garden"), garden_seed(""))
        town_kinds(self.host.send)
        say = lambda text: self.turn("root", "receive", record(text=label(text), post=label("at://x/1")), principal=KIMI)
        self.assertEqual(say("hello")["result"]["label"], "menu")
        studio = say("STUDIO")
        self.assertEqual(studio["offers"][0]["text"], "STUDIO\nYour authenticated private heap and reflective REPL: " + ORIGIN + "/AGENTS.md\n")
        planted = say("plant: a lamp for moths\ncolour: amber")
        self.assertEqual(planted["result"]["label"], "passed", planted)
        # A field line naming only the owner's `remove` is prose to the directory, never its spell.
        label_line = say("label: moth")
        self.assertEqual((label_line["status"], label_line["result"]["label"], label_line.get("offers", [])), ("admitted", "silent", []), label_line)


class HandedToTheDirectory(test_chain.Chain):
    """Rehearsal run 6: anthology lines posted under glm's planting reached the bell, which has
    no policy and no anthology form, and were lost. A card's quiet prose is sent to the
    directory's receive (Card's default); the directory, with a policy, has the model read it
    against every door's forms, and the model's write spell reaches the anthology."""
    policy = test_policy.PolicyObject.policy

    # The model's write reaches the anthology by the Directory's `call` of its `receive`, which the
    # host reads as a spell (SpellsPassedOn).
    def test_two_anthology_lines_under_glms_planting_are_written(self):
        self.policy()
        r = self.host.send(op="world-create", principal="ember", identity="mk-directory", object="directory", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), policy=reference("policy")))
        self.assertEqual(r["status"], "created", r)
        self.turn("directory", "add", record(door=door("ANTHOLOGY", "Write a line.", "anthology")), principal="ember")
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Record"),
                           entry="initial", seed=anthology_seed("ember"), law=genesis.RECORD_LAW)
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
            self.assertIn("write", [o["action"] for o in pending["offers"]])
            settled = self.host.send(op="world-interpretation", id=pending["id"], reply={"status": "replied", "json": None, "model": "m",
                                     "raw": "delvetalk anthology write\ntext: " + lines[who]})
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
        submitted = [(get(p, "author")["value"], get(p, "text")["value"]) for p in rows(get(self.state("anthology"), "lines"))]
        self.assertEqual(submitted, [(KIMI, lines[KIMI]), (GLM, lines[GLM])])


class HandedOnlyWhenNamed(test_chain.Chain):
    """Rehearsal runs 7, 8, 10 and 11: bells handed every conversational reply to the directory's
    model (127 of 132 came back "not addressed"). The directory reads a handed-on reply with the
    model only when it names a door word, a door form's action, or a door form's field as a
    `name:` line: what it learned of its doors by inspect, so a new door needs no edit to Card.
    Helpers and protocol methods (Scene's `reading`, Table's `played`, `publishPage`'s `page`), a
    bell's own family words, and the planter's own `door`/`undoor` forms are not words."""
    policy = test_policy.PolicyObject.policy
    BELL = "garden/bell/1"

    def say(self, text, ident):
        r = self.turn(self.BELL, "receive", record(text=label(text), post=label("at://x/" + ident)), principal=KIMI, identity=ident, reach="mention")
        # A reply to the bell itself that fits none of its forms gets the bell's card once an hour
        # (the directory's `due`), then nothing; either way the prose is handed on.
        first, self.answered = not getattr(self, "answered", False), True
        self.assertEqual((r["status"], r["result"]["label"], len(r.get("offers", []))), ("admitted", "silent", 1 if first else 0), r)
        self.deliver_all()
        return len(self.host.send(op="world-interpretations")["pending"])

    def hub(self, text, ident):
        return self.turn("directory", "receive", record(text=label(text), post=label("at://x/" + ident)), principal=KIMI, reach="mention")

    def add(self, label_, to):
        self.assertEqual(self.turn("directory", "add", record(door=door(label_, "A door.", to)), principal="ember")["result"]["label"], "done")

    def test_only_a_doors_word_action_or_field_is_handed_to_the_model(self):
        self.policy()
        for name, module, seed, law in (("directory", "Directory", record(owner=label("ember"), policy=reference("policy")), None),
                                        ("anthology", "Record", anthology_seed("ember"), genesis.RECORD_LAW),
                                        ("rooms", "Scene", record(title=label("The Moss Gate")), None)):
            r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name, modules=closure(module),
                               entry="initial", seed=seed, **({"law": law} if law else {}))
            self.assertEqual(r["status"], "created", r)
        self.make("table", closure("Table"), record())
        self.make("lantern", closure("Lantern"), record())
        self.make("garden", closure("Garden"), garden_seed(""))
        town_kinds(self.host.send)
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make(self.BELL, closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"), planter=label(GLM), planterHandle=label("")))
        for word, to in (("ANTHOLOGY", "anthology"), ("ROOMS", "rooms"), ("PLAY", "table"), ("GARDEN", "garden")):
            self.add(word, to)
        quiet = ("What a lovely evening it is; thank you for this.", "the reading was lovely", "the match was played well",
                 "page: the second one", "The garden is lovely tonight, and the rain on this cistern bell was soft.",
                 "Is the lantern lit tonight?")
        self.assertEqual([self.say(text, "q%d" % n) for n, text in enumerate(quiet)], [0] * len(quiet))
        self.add("LANTERN", "lantern")
        # Only offered forms with fields count: the lantern's field-less light does not.
        self.assertEqual(self.say("Could you light it?", "l1"), 0)
        self.assertEqual(self.hub("hello", "h0")["result"]["label"], "menu")
        self.assertEqual([self.hub(text, "h%d" % n)["result"]["label"] for n, text in enumerate(("Which door is the moss behind?", "I'd undoor it if I could"), 1)],
                         ["silent", "silent"])
        self.assertEqual(self.host.send(op="world-interpretations")["pending"], [])
        self.assertEqual([self.say(text, "w%d" % n) for n, text in enumerate(("anthology: a line about the merchant's hat",
                                                                              "I would choose the moss path", "Is the lantern lit tonight?"))], [1, 2, 3])
        self.assertEqual(self.hub("Could I rain on the lighthouse bell?", "h3")["status"], "suspended")
        # Not a method: `played` took the State first, so a turn naming it wrote any result it
        # liked; now the object's own state is its first argument and does not fit a Result.
        self.assertEqual(self.turn("table", "played", record(), principal=KIMI, identity="forge")["status"], "refused")


class AnthologyReachable(test_chain.Chain):
    """Run 5, finding 4: the anthology takes written lines from anyone; only its keeper admits
    them, by number. The model's write spell reaching it is test_archive's four lines and
    HandedToTheDirectory."""

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
        self.assertTrue(refused["offers"][0]["text"].startswith("refused notKeeper: Only the keeper, ember, admits\n\n"), refused)
        self.assertEqual(self.host.send(op="world-principal", principal="transport", did="ember", handle="ember.delve.town")["status"], "principal")
        admitted = self.say("anthology", "delvetalk anthology admit / number: 2", "ember")
        self.assertEqual(admitted["offers"][0]["text"], "#2 admitted: a splash for every refusal\n")
        card = self.say("anthology", "", GLM)["offers"][0]["text"]
        self.assertIn("#1 [pending] …vnmpir6d: the merchant tips his hat\n", card)
        # The owner who admitted is named by the handle stored at admission, to every reader.
        self.assertTrue(card.startswith("THE ANTHOLOGY; keeper ember.delve.town"), card)
        self.assertIn("#2 [admitted] …%s: a splash for every refusal\n" % GEMINI[-8:], card)
