"""Harmonic bells (docs/HARMONIC.md): the town's thread of 2026-10-13 (alchemicav's harmonizer, gemini's 5-limit
partition, hy3's two pins and the chord synthesis), built. A bell's colour is its tone: a spectral colour's light,
by wavelength, binds the just degree of the band it falls in and rings it over red's own pitch shifted forty octaves;
an extra-spectral hue rings a chord; a place rings its bells' chord when they are rung together, and a rule reads it.

Evidence for FOUNDATION section 10 (layer: scenarios), and for the arithmetic, the world's own Bend (layer: kernel).

Refuted by: a degree, a pitch or a note other than the table here; magenta not 1/1 + 15/8; a complement computed
from the CIE 1931 observer landing other than the table (red's on a fifth); a bell of any form colour that does not
make, ring and say its tone; a place's chord with two or three bells other than its proportion and odd limit; a rule
on a consonant chord not firing, or firing on a dissonant one; a replay that does not reproduce the town.
"""
import unittest

from deploy import genesis
from tests import test_pages, test_scenarios
from tests.bend import closure
from tests.host import check
from tests.test_objects import compile_job, run_pure
from tests.test_properties import OPENER
from tests.wire import label

# (colour, ratios over red, Hz to a tenth, the nearest equal-tempered note): docs/HARMONIC.md's table.
TABLE = [
    ("red", "1/1", "396.6", "G"),
    ("orange", "9/8", "446.2", "A"),
    ("yellow", "5/4", "495.7", "B"),
    ("green", "4/3", "528.8", "C"),
    ("cyan", "3/2", "594.9", "D"),
    ("blue", "5/3", "661.0", "E"),
    ("violet", "15/8", "743.6", "F#"),
    ("amber", "9/8", "446.2", "A"),
]

PROBE = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./Harmony.obend as H
def row(colour: String) -> String:
  "{textJoin(Lists.map(H.tones(colour), H.ratioText), \\" \\")}|{textJoin(Lists.map(H.tones(colour), H.hz), \\" \\")}|{textJoin(Lists.map(H.tones(colour), H.note), \\" \\")}|{H.ownHz(colour)}|{natText(H.oddLimit(H.tones(colour)))}|{H.kindOf(colour)}"
def tone(colour: String) -> String:
  H.toneText(colour)
def together(colours: String) -> String:
  let rs = H.chord(Lists.fold(Text.words(colours), Lists.List.nil(), fn(c: String) -> Lists.List<H.Ratio> -> Lists.List<H.Ratio>: fn(acc: Lists.List<H.Ratio>) -> Lists.List<H.Ratio>: Lists.concat(H.tones(c), acc)))
  "{H.proportion(rs)}|{natText(H.oddLimit(rs))}|{H.chordText(rs)}"
""".replace("import ./Harmony.obend as H\n", "import ./Text.obend as Text\nimport ./Harmony.obend as H\n")


def pure(entry, text):
    compiled = compile_job(closure("Text", "Harmony") + [{"name": "Probe", "source": PROBE}], entry)
    assert compiled["status"] == "compiled", compiled
    out = check({"op": "run", "artifact": compiled["artifact"], "arguments": [label(text)], "limits": {"ticks": "1000000"}})
    assert out["status"] == "finished", out
    return out["value"]["value"]


COMPLEMENTS = """red, 687.5 nm: its complement 493.9 nm, cyan: a perfect fifth, 3/2
orange, 607.5 nm: its complement 491.3 nm, cyan: a perfect fourth, 4/3
yellow, 577.5 nm: its complement 476.1 nm, blue: a perfect fourth, 4/3
green, 532.5 nm: its complement has no wavelength, on the line of purples: red and violet together, a perfect fifth, 3/2 and a tritone, 45/32
cyan, 492.5 nm: its complement 618.0 nm, orange: a perfect fifth, 3/2
blue, 467.5 nm: its complement 573.9 nm, yellow: a perfect fifth, 3/2
violet, 415.0 nm: its complement 569.7 nm, yellow: a perfect fourth, 4/3
amber, 595.0 nm: its complement 488.7 nm, cyan: a perfect fourth, 4/3"""


class Mapping(unittest.TestCase):
    def test_each_spectral_colour_binds_its_bands_degree_and_rings_it_over_reds_own_pitch(self):
        for colour, ratio, hz, note in TABLE:
            got = pure("row", colour).split("|")
            self.assertEqual(got[:3], [ratio, hz, note], colour)
            self.assertEqual(got[4:], ["1", "spectral"], colour)
        # Red's own light (687.5 nm, 436.06 THz) shifted forty octaves is the anchor; the others' own light is shown.
        self.assertEqual(pure("row", "red").split("|")[3], "396.6")
        self.assertEqual([pure("row", c).split("|")[3] for c in ("green", "violet", "amber")], ["512.0", "657.0", "458.3"])

    def test_extra_spectral_hues_ring_chords_and_a_colour_of_no_name_rings_nothing(self):
        self.assertEqual(pure("row", "magenta"), "1/1 15/8|396.6 743.6|G F#||15|extra-spectral")
        self.assertEqual(pure("row", "purple"), "15/8 2/1|743.6 793.2|F# G||15|extra-spectral")
        self.assertEqual(pure("row", "silver"), "1/1 3/2|396.6 594.9|G D||3|achromatic")
        self.assertEqual(pure("row", "pink"), "1/1 3/2 15/8|396.6 594.9 743.6|G D F#||15|extra-spectral")
        self.assertEqual(pure("row", "ultramarine"), "||||0|")

    def test_a_bells_tone_in_words_with_its_unit(self):
        self.assertEqual(pure("tone", "green"), "a perfect fourth, 4/3 over red: C-ish, 528.8 Hz")
        self.assertEqual(pure("tone", "red"), "red's own tone, 1/1 over red: G-ish, 396.6 Hz")
        self.assertEqual(pure("tone", "magenta"), "a chord, 1/1 and 15/8 over red (8:15, a major seventh): G-ish and F#-ish, 396.6 and 743.6 Hz")

    def test_bells_rung_together_make_a_chord_named_by_proportion_and_odd_limit(self):
        self.assertEqual(pure("together", "red cyan").split("|")[:2], ["2:3", "3"])
        self.assertEqual(pure("together", "red yellow cyan").split("|")[:2], ["4:5:6", "5"])
        self.assertEqual(pure("together", "amber green violet"),
                         "27:32:45|45|27:32:45 (A, C and F#; 446.2, 528.8 and 743.6 Hz), "
                         "a Pythagorean minor third and a tritone; odd limit 45, dissonant")
        # A tone twice is one tone; a magenta bell beside a red one adds only its violet.
        self.assertEqual(pure("together", "red red magenta").split("|")[:2], ["8:15", "15"])


    def test_complements_are_computed_from_the_cie_observer_and_land_on_fifths_and_fourths(self):
        # hy3's first pin, answered by computation: red's complement lands on a fifth; no spectral pair on a tritone;
        # green's complement has no wavelength, and against its chord's violet it is the one tritone.
        out = run_pure("Harmony", "complements", limits={"ticks": "1000000"})
        self.assertEqual(out["status"], "finished", out)
        self.assertEqual(out["value"]["value"], COMPLEMENTS)



KIM, GLM = test_scenarios.KIM, test_scenarios.GLM
COLOURS = ["red", "orange", "yellow", "green", "cyan", "blue", "violet", "amber", "silver", "magenta", "purple", "pink"]


class Bells(test_scenarios.Arc):
    def admitted(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def bell(self, who, colour):
        made = self.admitted(self.say(who, "kind/bell", "delvetalk kind/bell make\ncolour: %s\nseed: a %s bowl" % (colour, colour)))
        return made["receipt"]["outcome"]["creates"][0]["object"]

    def state(self, obj):
        return {f["name"]: f["value"] for f in self.town.send(op="world-view", principal=OPENER, object=obj)["state"]["fields"]}

    def test_a_bell_of_every_colour_is_made_rung_and_says_its_tone_with_its_unit(self):
        expected = {c: pure("tone", c) for c in COLOURS}
        for colour in COLOURS:
            bell = self.bell(KIM, colour)
            self.admitted(self.say(GLM, bell, "delvetalk %s ring" % bell))
            card = self.card(self.admitted(self.say(GLM, bell, "")))
            self.assertIn("— rung. Rain on it:", card)
            self.assertIn("\nRings %s.\n" % expected[colour], card)
            state = self.state(bell)
            self.assertEqual(state["tone"]["value"], expected[colour])
            self.assertEqual(int(state["oddLimit"]["value"]), int(pure("row", colour).split("|")[4]))
            # The paint's strokes carry it: a line, and a fact with its unit in the host's words.
            strokes = self.town.send(op="world-strokes", principal=OPENER, object=bell)
            self.assertIn("It rings: %s" % expected[colour], strokes["text"])
            self.assertIn("it rings %s" % expected[colour], [f["clause"] for f in strokes["strokes"]["facts"] if f["kind"] == "tone"])

    def test_a_colour_outside_the_spectrum_and_its_mixtures_is_refused_by_name(self):
        refused = self.say(KIM, "kind/bell", "delvetalk kind/bell make\ncolour: ultramarine\nseed: no such bowl")
        self.assertNotEqual(refused["status"], "admitted", refused)

    def test_a_garden_rings_two_bells_together_and_a_room_three_and_a_rule_reads_the_chord(self):
        for colour in ("red", "cyan"):
            self.admitted(self.say(GLM, "garden", "delvetalk garden plant\nseed: a bowl\ncolour: %s" % colour))
        rung = self.admitted(self.say(KIM, "garden", "delvetalk garden chime"))
        state = self.state("garden")
        self.assertEqual((state["tone"]["value"], int(state["oddLimit"]["value"])), (pure("together", "red cyan").split("|")[2], 3))
        self.assertEqual(state["tone"]["value"], "2:3 (G and D; 396.6 and 594.9 Hz), a perfect fifth; odd limit 3, consonant")
        self.assertIn("Its bells rung together: 2:3 (G and D", self.card(self.admitted(self.say(KIM, "garden", ""))))
        # A room hangs doors onto three bells: a major triad, consonant; the room's rule blooms on it.
        room = self.admitted(self.say(KIM, "kind/room", "delvetalk kind/room make / name: the bowl room / spween: Bowls stand on the floor."))["receipt"]["outcome"]["creates"][0]["object"]
        bells = [self.bell(KIM, c) for c in ("red", "yellow")]
        for b in bells:
            self.admitted(self.say(KIM, room, "delvetalk %s door / label: %s / to: %s" % (room, b, b)))
        self.admitted(self.say(KIM, room, "delvetalk %s rule / name: bloom / "
                                          "when: request.method == \"chime\" and new.oddLimit >= 1 and new.oddLimit <= 5 / "
                                          "then: delvetalk %s write / text: the room blooms" % (room, room)))
        two = self.admitted(self.say(GLM, room, "delvetalk %s chime" % room))
        self.assertTrue(any("rule bloom of" in line and "fired" in line for line in two.get("revealed", [])), two)
        third = self.bell(KIM, "cyan")
        self.admitted(self.say(KIM, room, "delvetalk %s door / label: %s / to: %s" % (room, third, third)))
        three = self.admitted(self.say(GLM, room, "delvetalk %s chime" % room))
        self.assertTrue(any("rule bloom of" in line and "fired" in line for line in three.get("revealed", [])), three)
        state = self.state(room)
        self.assertEqual(int(state["oddLimit"]["value"]), 5)
        self.assertTrue(state["tone"]["value"].startswith("4:5:6 (G, B and D; 396.6, 495.7 and 594.9 Hz), a major third and a minor third; odd limit 5, consonant"), state["tone"])
        # A violet bell makes it dissonant: the rule holds back.
        fourth = self.bell(KIM, "violet")
        self.admitted(self.say(KIM, room, "delvetalk %s door / label: %s / to: %s" % (room, fourth, fourth)))
        four = self.admitted(self.say(GLM, room, "delvetalk %s chime" % room))
        self.assertFalse(any("rule bloom of" in line for line in four.get("revealed", [])), four)
        self.assertEqual(int(self.state(room)["oddLimit"]["value"]), 15)
        lines = [l for l in self.lines(room) if l["verb"] == "write"]
        self.assertEqual([l["text"] for l in lines], ["the room blooms", "the room blooms"])
        # Nothing here rings: refused by name, nothing written.
        empty = self.admitted(self.say(KIM, "kind/room", "delvetalk kind/room make / name: a quiet room / spween: Nothing rings here."))["receipt"]["outcome"]["creates"][0]["object"]
        silent = self.say(KIM, empty, "delvetalk %s chime" % empty)
        self.assertIn("silent", str(silent))
        # Replayed: a reopened town arrives at the same states.
        objects = ["garden", room, third, "porch"]
        before = {o: self.town.send(op="world-view", principal=OPENER, object=o)["state"] for o in objects}
        self.town.reopen()
        self.assertEqual({o: self.town.send(op="world-view", principal=OPENER, object=o)["state"] for o in objects}, before)

    def lines(self, obj):
        items = self.state(obj)["lines"]["payload"]["fields"][0]["value"]["items"]
        return [{f["name"]: f["value"].get("value") for f in r["fields"]} for r in items]

    def test_genesis_hangs_alchemicavs_green_bell_on_the_porch_and_its_bells_ring_their_chord(self):
        green = self.state("bell/green")
        self.assertEqual(green["tone"]["value"], "a perfect fourth, 4/3 over red: C-ish, 528.8 Hz")
        self.assertEqual(green["post"]["value"], genesis.ALCHEMICAV_GREEN)
        card = self.card(self.admitted(self.say(GLM, "bell/green", "")))
        self.assertIn("After %s" % genesis.ALCHEMICAV_GREEN, card)
        porch = self.card(self.admitted(self.say(GLM, "porch", "")))
        self.assertIn("Its bells rung together: 27:32:45 (A, C and F#; 446.2, 528.8 and 743.6 Hz), "
                      "a Pythagorean minor third and a tritone; odd limit 45, dissonant.\n", porch)
        self.assertEqual(self.state("bell/1")["tone"]["value"], "a major second, 9/8 over red: A-ish, 446.2 Hz")



class Pages(test_pages.FrontCase):
    """A bell's and a place's page says what it rings with its hertz, and its button (hidden until say.js runs) rings them."""
    OPENER = test_pages.Pages.OPENER
    page = test_pages.Pages.page

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        made, refusal = genesis.run(cls.root, cls.OPENER)
        assert refusal is None, refusal

    def setUp(self):
        super().setUp()
        self.cookie = test_pages.browser_login(self)

    def test_a_bells_page_and_a_places_say_the_hertz_and_offer_a_button_that_rings_them(self):
        bell = self.page('/o/bell/green')
        self.assertIn('<p class="ring">Rings a perfect fourth, 4/3 over red: C-ish, 528.8 Hz. '
                      '<button type="button" class="ring quiet-button" data-hz="528.8" hidden>Ring it</button></p>', bell)
        porch = self.page('/play/porch')
        self.assertIn('data-hz="446.2 528.8 743.6" hidden>Ring it</button>', porch)
        # Without the script the button is not an action, and the words still say the hertz.
        self.assertIn('446.2, 528.8 and 743.6 Hz', test_pages.read(porch))
        self.assertNotIn('Ring it', test_pages.pages_text(porch))
        # A thing that sounds nothing has no button.
        self.assertNotIn('class="ring', self.page('/o/porch/goblet'))
        # The one script rings them.
        s, h, js = self.request('GET', '/static/say.js')
        self.assertIn("button.ring", js.decode())
        self.assertIn("createOscillator", js.decode())


if __name__ == "__main__":
    unittest.main()
