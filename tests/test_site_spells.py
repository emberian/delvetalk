"""The site's "Things people do here" (site/index.html `ul.tried`): every spell it shows is cast, in order, on a town as
genesis makes the live one (with the all-night station), and each is admitted, none refused badSpell; and every spell
its "From an older post" list names as old is one the town no longer takes as a spell. A newcomer copies these whole.

Evidence for site/README.md "Editing" (layer: transport).

Refuted by: a spell on the page that a card refuses or no longer has (a renamed verb, a dropped card, a field the form
does not take), or an old spell the town takes again under the same words.
"""
import html
import json
import re
import tempfile
import unittest
from pathlib import Path

from deploy import genesis
from tests.town import Town
from tests.wire import label, record

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "site" / "index.html").read_text()
WHO = "did:plc:newcomer"
POST = "at://did:plc:ubtqb43nq7u6jlibkzlobkuu/town.delve.feed.post/3mxcxqlydqi2a"  # gemini's porch, which the porch cites


def tried():
    """The spells of the page's `ul.tried`, one per line, as written (an indented line belongs to the `try` above it)."""
    block = re.search(r'<ul class="rows tried">(.*?)</ul>', PAGE, re.S).group(1)
    spells = []
    for pre in re.findall(r'<pre class="spell">(.*?)</pre>', block, re.S):
        for line in html.unescape(pre).split("\n"):
            if line.startswith("  ") and spells:
                spells[-1] += "\n" + line
            else:
                spells.append(line)
    return spells


def older():
    """The old spells the page's "From an older post" names, each a `delvetalk` line from a `dt`."""
    block = re.search(r'<dl class="was">(.*?)</dl>', PAGE, re.S).group(1)
    return [s.strip() for dt in re.findall(r"<dt>(.*?)</dt>", block, re.S)
            for s in html.unescape(dt).replace("·", "<br>").split("<br>") if s.strip().startswith("delvetalk")]


class SiteSpells(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, run_genesis=False, cleanup=cls.addClassCleanup)
        cls.host = cls.town.client
        made, refusal = genesis.run(cls.host, gas_station=True)
        assert refusal is None, refusal
        got = cls.host.send({"op": "world-arrive", "principal": "transport", "did": WHO, "handle": "newcomer.test"})
        assert got["status"] == "arrived", got
        cls.n = 0

    def cast(self, spell):
        type(self).n += 1
        card = spell.split()[1]
        reply = self.host.send({"op": "world-turn", "principal": WHO, "object": WHO if card == "me" else card, "method": "receive",
                                "identity": "site-%d" % self.n, "argument": record(text=label(spell), post=label("at://x/site-%d" % self.n))})
        return reply, "".join(o.get("text", "") for o in reply.get("offers", []))

    def test_every_spell_people_do_here_is_admitted_in_order(self):
        spells, bell = tried(), None
        self.assertGreaterEqual(len(spells), 10, spells)
        for spell in spells:
            spell = spell.replace("bell/N", bell or "bell/N").replace("<a post’s at:// address>", POST).replace(
                "<one question>", "where did the car at pump 3 come from?")
            with self.subTest(spell=spell):
                self.assertNotIn("<", spell)  # every blank on the page is filled here or written out
                reply, text = self.cast(spell)
                self.assertEqual(reply["status"], "admitted", json.dumps(reply)[:600])
                self.assertNotIn("badSpell", json.dumps(reply)[:4000], text)
                if bell is None and (m := re.search(r"Made, at (bell/\d+)", text)):
                    bell = m.group(1)

    def test_an_old_spell_is_no_longer_a_spell_here(self):
        old = older()
        self.assertGreaterEqual(len(old), 5, old)
        for spell in old:
            with self.subTest(spell=spell):
                reply, _ = self.cast(spell)
                self.assertNotEqual(reply["status"], "admitted", json.dumps(reply)[:600])


if __name__ == "__main__":
    unittest.main()
