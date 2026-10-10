"""The prelude's Maybe and list searches (find, filterMap, indexWhere, removeWhere) answer in order,
up to the 247-item cap.

Evidence for FOUNDATION §1 (layer: kernel).

The prelude's Maybe and list searches: find, filterMap, indexWhere, removeWhere.

`run` refuses variant arguments and recursive results, so a probe module builds the
lists in Bend and answers a String.
"""
import unittest

from tests.test_objects import check, closure, compile_job

PROBE = """edition ObjectiveBend 1
import ./List.obend as Lists
type Nats = Lists.List<Nat>
def nats(n: Nat) -> Nats:
  if n == 0n then Nats.nil() else Nats.cons({head: n, tail: nats(n - 1n)})
def shown(items: Nats) -> String:
  match items:
    case nil(_): "."
    case cons(c): textConcat(natText(c.head), textConcat(",", shown(c.tail)))
def maybe(found: Lists.Maybe<Nat>) -> String:
  match found:
    case none(_): "none"
    case some(s): textConcat("some ", natText(s.value))
def big(n: Nat) -> Bool:
  n > 3n
def is(k: Nat) -> Nat -> Bool:
  fn(n: Nat) -> Bool: n == k
def halfOfEven(n: Nat) -> Lists.Maybe<Nat>:
  if n == 2n || n == 4n || n == 6n then Lists.Maybe::<Nat>.some({value: n * 10n}) else Lists.Maybe::<Nat>.none({})
def findBig(n: Nat) -> String:
  maybe(Lists.find::<Nat>(nats(n), big))
def indexOf(k: Nat) -> String:
  maybe(Lists.indexWhere::<Nat>(nats(6n), is(k)))
def filterMapped(n: Nat) -> String:
  shown(Lists.filterMap::<Nat, Nat>(nats(n), halfOfEven))
def removed(k: Nat) -> String:
  shown(Lists.removeWhere::<Nat>(Lists.concat::<Nat>(nats(6n), nats(6n)), is(k)))
def indexAt(n: Nat) -> Nat:
  match Lists.indexWhere::<Nat>(nats(n), is(1n)):
    case none(_): 0n
    case some(s): s.value
"""


def run(entry, n, limits=None):
    compiled = compile_job(closure("List") + [{"name": "Probe", "source": PROBE}], entry)
    assert compiled["status"] == "compiled", compiled
    request = {"op": "run", "artifact": compiled["artifact"], "arguments": [{"tag": "natural", "value": str(n)}]}
    if limits:
        request["limits"] = limits
    out = check(request)
    assert out["status"] == "finished", out
    return out


class Searches(unittest.TestCase):
    def value(self, entry, n):
        return run(entry, n)["value"]["value"]

    def test_find_answers_the_first_match_or_none(self):
        self.assertEqual(self.value("findBig", 6), "some 6")
        self.assertEqual(self.value("findBig", 3), "none")
        self.assertEqual(self.value("findBig", 0), "none")

    def test_index_where_counts_from_zero_and_misses_with_none(self):
        # nats(6) is 6,5,4,3,2,1
        self.assertEqual(self.value("indexOf", 6), "some 0")
        self.assertEqual(self.value("indexOf", 1), "some 5")
        self.assertEqual(self.value("indexOf", 9), "none")

    def test_filter_map_keeps_order_and_drops_none(self):
        self.assertEqual(self.value("filterMapped", 7), "60,40,20,.")
        self.assertEqual(self.value("filterMapped", 1), ".")

    def test_remove_where_drops_every_match(self):
        self.assertEqual(self.value("removed", 4), "6,5,3,2,1,6,5,3,2,1,.")
        self.assertEqual(self.value("removed", 9), "6,5,4,3,2,1,6,5,4,3,2,1,.")

    def test_index_where_at_the_247_item_cap(self):
        out = run("indexAt", 247, limits={"ticks": "1000000"})
        print("\n  indexWhere over 247 items: %s ticks" % out.get("ticksUsed"))
        self.assertEqual(out["value"]["value"], "246")


if __name__ == "__main__":
    unittest.main()
