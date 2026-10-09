"""The tariff, measured: exact tick counts for three reference workloads, with the
counts before the kernel lane's tariff work for comparison.

    python3 -m unittest tests.test_tariff -v

Conformance compares values, never costs, so these counts are the regression
guard for the tariff: a change to the machine or to `textStepCost` that moves
one of them must update the number here and say why.

| workload                                   | before  | after   |
| ------------------------------------------ | ------- | ------- |
| one `bump` turn (start 56 + resume 10)     | 66      | 66      |
| spell parse, 4,096 bytes, 64 fields        | 97,355  | 56,957  |
| `Document.plain`, 1,025 leaves (with build)| 336,659 | 129,272 |
| the same document's `Document.size` walk   | 120,037 | 120,037 |
| Bell card, 1,025 rains                     | 848,680 | 333,209 |

Before: `Document.plain` joined adjacent pairs in rounds (every byte copied about
log2(leaves) times); `textTake`/`textDrop` were charged 2 x min(B, 4n) bytes.
After: `plain` is one `textJoin` (charged by the bytes it appends), and take/drop
are charged by the exact bytes of the prefix they traverse. No transition count
changed (the spell parse is 19,971 transitions either way).
"""
import unittest

from tests.test_turn import Host, PLANS, BINDING, nat, variant
from tests.test_objects import BELL_PROBE, run_pure
from tests import test_spell

BIG = {"ticks": "1000000"}

DOCUMENT = """edition ObjectiveBend 1
import ./Document.obend as Document
def leaves(n: Nat) -> Document.Documents:
  match n:
    case 0: Document.Documents.nil()
    case 1+p: Document.Documents.cons({head: Document.text("abcdefgh"), tail: leaves(p)})
def flat(n: Nat) -> Nat:
  textLength(Document.plain(Document.Document.sequence({items: leaves(n)})))
def sized(n: Nat) -> Nat:
  Document.size(Document.Document.sequence({items: leaves(n)}))
"""

STRINGS = """edition ObjectiveBend 1
import ./List.obend as Lists
def strings(n: Nat, word: String) -> Lists.List<String>:
  match n:
    case 0: Lists.List::<String>.nil()
    case 1+p: Lists.List::<String>.cons({head: word, tail: strings(p, word)})
def joined(n: Nat) -> String:
  textJoin(strings(n, "ab"), ", ")
def size(n: Nat) -> Nat:
  textLength(textJoin(strings(n, "x"), ""))
"""


class TariffTests(unittest.TestCase):
    def test_bump_turn(self):
        h = Host()
        self.addCleanup(h.close)
        art = h.compile(PLANS, "bump")
        started = h.start(art, [nat(41)])
        resumed = h.resume(art, started["checkpoint"], variant("written"))
        print("\n  bump: start %d + resume %d ticks" % (started["ticksUsed"], resumed["ticksUsed"]))
        self.assertEqual((started["ticksUsed"], resumed["ticksUsed"]), (56, 10))

    def test_spell_parse_of_64_fields(self):
        out = test_spell.run("fieldCount", test_spell.text(test_spell.Maximum().reply(44)))
        print("\n  spell, 64 fields: %d ticks (was 97,355)" % out["ticksUsed"])
        self.assertEqual(out["value"]["value"], "64")
        self.assertEqual(out["ticksUsed"], 56957)

    def test_plain_of_1025_leaves(self):
        flat = run_pure("Document", "flat", nat(1025), probe=DOCUMENT, limits=BIG)
        sized = run_pure("Document", "sized", nat(1025), probe=DOCUMENT, limits=BIG)
        print("\n  plain, 1,025 leaves: %d ticks (was 336,659); size walk %d; plain's own work %d"
              % (flat["ticksUsed"], sized["ticksUsed"], flat["ticksUsed"] - sized["ticksUsed"]))
        self.assertEqual(flat["value"]["value"], "8200")
        self.assertEqual(flat["ticksUsed"], 129272)
        self.assertEqual(sized["ticksUsed"], 120037)
        self.assertLess(flat["ticksUsed"] - sized["ticksUsed"], 50000)

    def test_bell_card_of_1025_rains(self):
        out = run_pure("Bell", "many", nat(1025), probe=BELL_PROBE, limits=BIG)
        print("\n  Bell card, 1,025 rains: %d ticks (was 848,680; 333,209 before the card showed eight)" % out["ticksUsed"])
        self.assertEqual(out["status"], "finished", out)
        self.assertEqual(out["ticksUsed"], 75830)

    def test_text_join_is_linear_in_its_output(self):
        # Refuted if a join re-reads its accumulator: doubling the elements would
        # then roughly quadruple the ticks.
        costs = [run_pure("Document", "size", nat(n), probe=STRINGS, limits=BIG)["ticksUsed"] for n in (2000, 4000, 8000)]
        print("\n  textJoin of 2,000 / 4,000 / 8,000 elements: %s ticks" % costs)
        self.assertLess(costs[2], 2.1 * costs[1])
        self.assertLess(costs[1], 2.1 * costs[0])

    def test_text_join_separates_and_refuses_a_non_list(self):
        joined = run_pure("Document", "joined", nat(3), probe=STRINGS)
        self.assertEqual(joined["value"]["value"], "ab, ab, ab")
        self.assertEqual(run_pure("Document", "joined", nat(0), probe=STRINGS)["value"]["value"], "")
        from tests.test_objects import compile_job
        refused = compile_job([{"name": "Package", "source":
            "edition ObjectiveBend 1\ndef f(n: Nat) -> String:\n  textJoin(n, \"\")\n"}], "f")
        self.assertNotEqual(refused["status"], "compiled", refused)


if __name__ == "__main__":
    unittest.main()
