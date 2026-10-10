"""The tariff, pinned: exact tick counts of workloads whose code lives in the test, so only a change
to the machine's charges moves them.

Evidence for FOUNDATION §2 Limits (layer: kernel).

The tariff, pinned: exact tick counts of workloads whose code is fixed in this file, so
only a change to the machine's charges can move them.

    python3 -m unittest tests.test_tariff -v

Conformance compares values, never costs, so these counts are the regression guard for
the tariff: a change to the machine or to `textStepCost` that moves one of them must
update the number here and say why. Workloads over world library code (a Bell card, a
spell parse) are bounded where that code is tested, never pinned here: their counts move
with every edit of the library.

| workload                                   | before  | after   |
| ------------------------------------------ | ------- | ------- |
| one `bump` turn (start 56 + resume 10)     | 66      | 66      |
| `Document.plain`, 1,025 leaves (with build)| 336,659 | 129,272 |
| the same document's `Document.size` walk   | 120,037 | 120,037 |

Before: `Document.plain` joined adjacent pairs in rounds (every byte copied about
log2(leaves) times); `textTake`/`textDrop` were charged 2 x min(B, 4n) bytes.
After: `plain` is one `textJoin` (charged by the bytes it appends), and take/drop
are charged by the exact bytes of the prefix they traverse.
"""
import unittest

from tests.test_turn import Host, PLANS, BINDING, nat, variant
from tests.test_objects import run_pure

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
    def test_a_bump_turn_costs_56_ticks_to_start_and_10_to_resume(self):
        h = Host()
        self.addCleanup(h.close)
        art = h.compile(PLANS, "bump")
        started = h.start(art, [nat(41)])
        resumed = h.resume(art, started["checkpoint"], variant("written"))
        print("\n  bump: start %d + resume %d ticks" % (started["ticksUsed"], resumed["ticksUsed"]))
        self.assertEqual((started["ticksUsed"], resumed["ticksUsed"]), (56, 10))

    def test_document_plain_over_1025_leaves_costs_its_pinned_ticks(self):
        flat = run_pure("Document", "flat", nat(1025), probe=DOCUMENT, limits=BIG)
        sized = run_pure("Document", "sized", nat(1025), probe=DOCUMENT, limits=BIG)
        print("\n  plain, 1,025 leaves: %d ticks (was 336,659); size walk %d; plain's own work %d"
              % (flat["ticksUsed"], sized["ticksUsed"], flat["ticksUsed"] - sized["ticksUsed"]))
        self.assertEqual(flat["value"]["value"], "8200")
        self.assertEqual(flat["ticksUsed"], 129272)
        self.assertEqual(sized["ticksUsed"], 120037)
        self.assertLess(flat["ticksUsed"] - sized["ticksUsed"], 50000)

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
