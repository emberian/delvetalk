"""A state's relation arrives as stored cells: a turn fetches and pays for only the rows it
forces, answers what the quoted turn answers, and reports the rows it forced, by key, for the host
to record as roots (KERNEL-HANDOFF section 15).

Evidence for FOUNDATION §9 State model (layer: kernel).

Each test names what would refute it.
"""
import unittest

from tests.test_turn import PLANS_WORLD, BINDING, TurnCase
from tests.wire import nat

LIST = """edition ObjectiveBend 1
sum List<T>:
  nil: {}
  cons: {head: T, tail: List<T>}
sum Maybe<T>:
  none: {}
  some: {value: T}
"""

RELATION = """edition ObjectiveBend 1
import ./List.obend as Lists
sum Relation<T>:
  rows: {items: Lists.List<T>}
"""

RAINS = """edition ObjectiveBend 1
import ./World.obend as World
import ./List.obend as Lists
import ./Relation.obend as Relations
record Rain:
  n: Nat
  text: String
record Mark:
  n: Nat
  by: String
record State:
  count: Nat
  rains: Relations.Relation<Rain>
  marks: Relations.Relation<Mark>
def rowsOf(r: Relations.Relation<Rain>) -> Lists.List<Rain>:
  match r:
    case rows(x): x.items
def textAt(items: Lists.List<Rain>, k: Nat) -> String:
  match items:
    case nil(_): "none"
    case cons(c): if k == 0n then c.head.text else textAt(c.tail, k - 1n)
def nAt(items: Lists.List<Rain>, k: Nat) -> Nat:
  match items:
    case nil(_): 0n
    case cons(c): if k == 0n then c.head.n else nAt(c.tail, k - 1n)
def size(items: Lists.List<Rain>) -> Nat:
  match items:
    case nil(_): 0n
    case cons(c): 1n + size(c.tail)
def marksOf(r: Relations.Relation<Mark>) -> Lists.List<Mark>:
  match r:
    case rows(x): x.items
def total(items: Lists.List<Rain>) -> Nat:
  match items:
    case nil(_): 0n
    case cons(c): c.head.n + total(c.tail)
def pairs(a: Lists.List<Rain>, b: Lists.List<Mark>) -> Nat:
  match a:
    case nil(_): 0n
    case cons(x): pairsWith(x.head, x.tail, a, b)
def pairsWith(row: Rain, rest: Lists.List<Rain>, a: Lists.List<Rain>, b: Lists.List<Mark>) -> Nat:
  match b:
    case nil(_): 0n
    case cons(y): if row.n == y.head.n then 1n + pairs(rest, y.tail) else if row.n < y.head.n then pairs(rest, b) else pairs(a, y.tail)
def card(state: State) -> String:
  "{textAt(rowsOf(state.rains), 0n)} / {textAt(rowsOf(state.rains), 1n)}"
def scan(state: State) -> Nat:
  total(rowsOf(state.rains))
def joined(state: State) -> Nat:
  pairs(rowsOf(state.rains), marksOf(state.marks))
def bump(state: State) -> Activity<Nat>:
  match world.write({field: 0n, before: state.count, after: state.count + 1n}):
    case written(_): state.count + 1n
    case refused(_): state.count
def third(state: State) -> Activity<String>:
  match world.write({field: 0n, before: state.count, after: state.count + 1n}):
    case written(_): textAt(rowsOf(state.rains), 2n)
    case refused(_): "refused"
def counted(state: State) -> Activity<Nat>:
  match world.write({field: 0n, before: state.count, after: state.count + 1n}):
    case written(_): size(rowsOf(state.rains))
    case refused(_): 0n
def rainCount(state: State) -> Nat:
  relationCount(state.rains)
def rainAt(state: State, n: Nat) -> String:
  match relationLookup(state.rains, {n: n}):
    case some(s): s.value.text
    case none(_): "none"
def rainHere(state: State, n: Nat) -> Bool:
  match relationLookup(state.rains, {n: n}):
    case some(_): true
    case none(_): false
def rainByText(state: State, t: String) -> String:
  match relationLookup(state.rains, {text: t}):
    case some(s): natText(s.value.n)
    case none(_): "none"
def countedNow(state: State) -> Activity<Nat>:
  match world.write({field: 0n, before: state.count, after: state.count + 1n}):
    case written(_): relationCount(state.rains)
    case refused(_): 0n
def lookedUp(state: State) -> Activity<String>:
  match world.write({field: 0n, before: state.count, after: state.count + 1n}):
    case written(_): rainAt(state, 1500n)
    case refused(_): "refused"
def planned(state: State) -> Activity<Nat>:
  match world.write({field: 1n, before: nAt(rowsOf(state.rains), 1n), after: 0n}):
    case written(_): state.count
    case refused(_): 0n
"""

WRITTEN = {"tag": "variant", "label": "written", "payload": {"tag": "record", "fields": []}}
STORED = [{"field": "rains", "key": ["n"]}, {"field": "marks", "key": ["n"]}]


def relation(items):
    return {"tag": "variant", "label": "rows", "payload": {"tag": "record", "fields": [
        {"name": "items", "value": {"tag": "list", "items": items}}]}}


def state(rows, count=7, text=lambda i: f"rain {i}", marks=()):
    items = [{"tag": "record", "fields": [{"name": "n", "value": nat(i)},
                                          {"name": "text", "value": {"tag": "label", "value": text(i)}}]}
             for i in range(rows)]
    marked = [{"tag": "record", "fields": [{"name": "n", "value": nat(i)},
                                           {"name": "by", "value": {"tag": "label", "value": "glm"}}]} for i in marks]
    return {"tag": "record", "fields": [{"name": "count", "value": nat(count)},
                                        {"name": "rains", "value": relation(items)},
                                        {"name": "marks", "value": relation(marked)}]}


class StoredCase(TurnCase):
    artifacts = {}

    def artifact(self, entry):
        if entry not in self.artifacts:
            reply = self.host().send({"op": "compile", "entry": entry, "modules": [
                {"name": "World", "source": PLANS_WORLD}, {"name": "List", "source": LIST},
                {"name": "Relation", "source": RELATION}, {"name": "Package", "source": RAINS}]})
            self.assertEqual(reply["status"], "compiled", reply)
            self.artifacts[entry] = reply["artifact"]
        return self.artifacts[entry]



class StoredTurns(StoredCase):
    def start(self, entry, the_state, stored=True):
        request = {"op": "turn-start", "artifact": self.artifact(entry), "arguments": [the_state], **BINDING}
        if stored:
            request["stored"] = STORED
        return self.host().send(request)

    def resume(self, entry, reply, the_state, stored=True):
        request = {"op": "turn-resume", "artifact": self.artifact(entry), "checkpoint": reply["checkpoint"],
                   "response": WRITTEN, **BINDING}
        if stored:
            request.update(stored=STORED, state=the_state)
        return self.host().send(request)

    def run_through(self, entry, the_state, stored=True):
        first = self.start(entry, the_state, stored)
        self.assertEqual(first["status"], "yielded", first)
        return first, self.resume(entry, first, the_state, stored)

    def test_stored_and_quoted_turns_answer_alike(self):
        # Refuted if a stored state reads differently from the same state quoted.
        for entry in ("bump", "third", "counted", "planned"):
            with self.subTest(entry=entry):
                s = state(5)
                quoted = self.run_through(entry, s, stored=False)
                lazy = self.run_through(entry, s)
                self.assertEqual(lazy[0]["plan"], quoted[0]["plan"])
                self.assertEqual(lazy[1]["status"], quoted[1]["status"])
                self.assertEqual(lazy[1].get("value"), quoted[1].get("value"))

    def test_a_turn_forces_only_the_rows_it_reads(self):
        # Refuted if an unread row is reported, or a read one is not.
        _, done = self.run_through("third", state(6))
        self.assertEqual(done["value"], {"tag": "label", "value": "rain 2"})
        self.assertEqual(done["reads"]["rows"], [{"field": "rains", "key": {"tag": "record", "fields": [
            {"name": "n", "value": nat(2)}]}, "bytes": done["reads"]["rows"][0]["bytes"]}])
        self.assertEqual(done["reads"]["spans"], [{"field": "rains", "reach": 3}])
        _, bumped = self.run_through("bump", state(6))
        self.assertEqual(bumped["reads"], {"rows": [], "spans": []})

    def test_a_count_reads_the_key_set_and_no_row(self):
        _, done = self.run_through("counted", state(4))
        self.assertEqual(done["value"], nat(4))
        self.assertEqual(done["reads"], {"rows": [], "spans": [{"field": "rains", "reach": 5}]})

    def test_a_row_read_while_building_a_plan_is_reported_at_the_yield(self):
        first = self.start("planned", state(3))
        self.assertEqual([r["key"]["fields"][0]["value"] for r in first["reads"]["rows"]], [nat(1)])

    def test_a_relation_never_forced_costs_nothing_whatever_its_size(self):
        # Refuted if holding 2,048 rows costs ticks a turn that reads none of them.
        small = self.run_through("bump", state(0))
        large = self.run_through("bump", state(2048))
        self.assertEqual([r["ticksUsed"] for r in small], [r["ticksUsed"] for r in large])
        third_small = self.run_through("third", state(3))
        third_large = self.run_through("third", state(2048))
        self.assertEqual([r["ticksUsed"] for r in third_small], [r["ticksUsed"] for r in third_large])

    def test_a_forced_row_pays_its_canonical_bytes(self):
        # Refuted if a longer row read costs the same as a short one: 1 + 2 bytes a row.
        short = self.run_through("third", state(3, text=lambda i: "x"))[1]
        long = self.run_through("third", state(3, text=lambda i: "x" * 101))[1]
        self.assertEqual(long["reads"]["rows"][0]["bytes"] - short["reads"]["rows"][0]["bytes"], 101)
        self.assertEqual(long["ticksUsed"] - short["ticksUsed"], 2 * 101)

    def test_a_row_past_the_cell_bound_is_refused(self):
        big = state(3, text=lambda i: "y" * (262144 if i == 2 else 1))
        first = self.start("third", big)
        reply = self.resume("third", first, big)
        self.assertEqual(reply["status"], "error", reply)
        self.assertIn("exceeds the cell bound", reply["message"])
        # Rows the turn does not read are never measured.
        _, bumped = self.run_through("bump", big)
        self.assertEqual(bumped["status"], "finished", bumped)


class StoredReads(StoredCase):
    """A card render, a rows scan and a join over stored relations: pure entries, run natively."""

    def read(self, entry, the_state, stored=True):
        # Unstored: the same state wholly native (no relation stored).
        request = {"op": "run", "artifact": self.artifact(entry), "arguments": [the_state],
                   "stored": STORED if stored else []}
        return self.host().send(request)

    def keys(self, reply, field):
        return [int(r["key"]["fields"][0]["value"]["value"]) for r in reply["reads"]["rows"] if r["field"] == field]

    def test_reads_answer_as_the_unstored_run_does(self):
        for entry in ("card", "scan", "joined"):
            with self.subTest(entry=entry):
                s = state(6, marks=(2, 4))
                native = self.read(entry, s, stored=False)
                self.assertEqual(native["reads"], {"rows": [], "spans": []})
                self.assertEqual(self.read(entry, s)["value"], native["value"])

    def test_a_card_render_forces_the_rows_it_shows(self):
        reply = self.read("card", state(2048))
        self.assertEqual(reply["value"], {"tag": "label", "value": "rain 0 / rain 1"})
        self.assertEqual(self.keys(reply, "rains"), [0, 1])

    def test_a_scan_forces_every_row(self):
        reply = self.read("scan", state(6))
        self.assertEqual(reply["value"], nat(15))
        self.assertEqual(self.keys(reply, "rains"), list(range(6)))
        self.assertEqual(reply["reads"]["spans"], [{"field": "rains", "reach": 7}])

    def test_a_join_stops_where_the_shorter_relation_ends(self):
        # The merge reads rains up to the last mark's key and no further.
        reply = self.read("joined", state(6, marks=(2, 4)))
        self.assertEqual(reply["value"], nat(2))
        self.assertEqual(self.keys(reply, "rains"), [0, 1, 2, 3, 4])
        self.assertEqual(self.keys(reply, "marks"), [2, 4])


class RelationPrimitives(StoredCase):
    """`relationCount` and `relationLookup` (KERNEL-HANDOFF section 16 item 15): a stored relation
    answers a count from its handle and a lookup by its key with a binary search over its keys,
    fetching one row and only when it is read; any other relation is walked to the same answer."""

    def run_entry(self, entry, the_state, *rest, stored=True):
        request = {"op": "run", "artifact": self.artifact(entry), "arguments": [the_state, *rest],
                   "stored": STORED if stored else [], "limits": {"ticks": "1000000"}}
        return self.host().send(request)

    def keys(self, reply):
        return [int(r["key"]["fields"][0]["value"]["value"]) for r in reply["reads"]["rows"]]

    def test_stored_and_walked_relations_answer_alike(self):
        # Refuted if the stored path and the walk of the same rows disagree on any answer.
        s = state(40)
        for entry, rest in (("rainCount", ()), ("rainAt", (nat(17),)), ("rainAt", (nat(99),)),
                            ("rainHere", (nat(0),)), ("rainHere", (nat(40),))):
            with self.subTest(entry=entry, rest=rest):
                walked = self.run_entry(entry, s, *rest, stored=False)
                self.assertEqual(walked["status"], "finished", walked)
                self.assertEqual(self.run_entry(entry, s, *rest)["value"], walked["value"])

    def test_a_count_reads_no_row_and_costs_the_same_at_any_size(self):
        # Refuted if a count forces a row, reports less than the whole key set, or pays per row.
        replies = [self.run_entry("rainCount", state(n)) for n in (0, 5, 2048)]
        self.assertEqual([r["value"] for r in replies], [nat(0), nat(5), nat(2048)])
        self.assertEqual([r["reads"] for r in replies],
                         [{"rows": [], "spans": [{"field": "rains", "reach": n + 1}]} for n in (0, 5, 2048)])
        self.assertEqual(len({r["ticksUsed"] for r in replies}), 1)

    def test_a_count_is_one_tick(self):
        # Refuted if the count step itself costs more than one transition (the profile's frame).
        first = self.host().send({"op": "turn-start", "artifact": self.artifact("countedNow"),
                                  "arguments": [state(2048)], "stored": STORED, **BINDING})
        done = self.host().send({"op": "turn-resume", "artifact": self.artifact("countedNow"),
                                 "checkpoint": first["checkpoint"], "response": WRITTEN, "stored": STORED,
                                 "state": state(2048), "profile": True, **BINDING})
        self.assertEqual(done["value"], nat(2048))
        rows = {p["kind"]: p for p in done["profile"]}
        self.assertEqual((rows["returned.relationRows"]["steps"], rows["returned.relationRows"]["ticks"]), (1, 1))
        self.assertNotIn("fetch.row", rows)

    def test_a_lookup_fetches_the_one_row_it_reads(self):
        # Refuted if a hit over 2,048 rows fetches any row but its own or reports a span past it.
        reply = self.run_entry("rainAt", state(2048), nat(1500))
        self.assertEqual(reply["value"], {"tag": "label", "value": "rain 1500"})
        self.assertEqual(self.keys(reply), [1500])
        self.assertEqual(reply["reads"]["spans"], [{"field": "rains", "reach": 1501}])

    def test_a_lookup_pays_its_row_and_its_probes(self):
        # Refuted if the found row is not charged 1 + 2 bytes, or a search probes more than
        # log2(n) + 1 keys: twelve over 2,048 rows.
        first = self.host().send({"op": "turn-start", "artifact": self.artifact("lookedUp"),
                                  "arguments": [state(2048)], "stored": STORED, **BINDING})
        done = self.host().send({"op": "turn-resume", "artifact": self.artifact("lookedUp"),
                                 "checkpoint": first["checkpoint"], "response": WRITTEN, "stored": STORED,
                                 "state": state(2048), "profile": True, **BINDING})
        self.assertEqual(done["value"], {"tag": "label", "value": "rain 1500"})
        rows = {p["kind"]: p for p in done["profile"]}
        row = done["reads"]["rows"][0]["bytes"]
        self.assertEqual((rows["fetch.row"]["steps"], rows["fetch.row"]["ticks"]), (1, 1 + 2 * row))
        self.assertLessEqual(rows["fetch.key"]["steps"], 12)
        self.assertLess(done["ticksUsed"], 2000)

    def test_presence_reads_no_row(self):
        # Refuted if asking whether a key is present fetches its row.
        hit, miss = self.run_entry("rainHere", state(2048), nat(7)), self.run_entry("rainHere", state(2048), nat(5000))
        self.assertEqual((hit["value"], miss["value"]), ({"tag": "boolean", "value": True}, {"tag": "boolean", "value": False}))
        self.assertEqual((hit["reads"]["rows"], miss["reads"]["rows"]), ([], []))
        self.assertEqual(hit["reads"]["spans"], [{"field": "rains", "reach": 8}])
        self.assertEqual(miss["reads"]["spans"], [{"field": "rains", "reach": 2049}])

    def test_a_lookup_by_columns_that_are_not_the_key_is_refused(self):
        # Refuted if a stored relation searched by a non-key column answers (its rows are not in
        # that column's order); the walk of the same rows answers.
        reply = self.run_entry("rainByText", state(6), {"tag": "label", "value": "rain 3"})
        self.assertEqual((reply["status"], reply["reads"]["rows"]), ("refused", []), reply)
        walked = self.run_entry("rainByText", state(6), {"tag": "label", "value": "rain 3"}, stored=False)
        self.assertEqual(walked["value"], {"tag": "label", "value": "3"})


if __name__ == "__main__":
    unittest.main()
