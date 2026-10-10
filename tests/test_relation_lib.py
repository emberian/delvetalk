"""world/lib/Relation.obend through the real checker: the key order (naturals before texts,
naturals by value, texts by length then bytes, as canonical DAG-CBOR bytes order them),
fromList's sort and dedupe, the queries, the merge join, and the Bend mirrors of the host's
insert, upsert and retract. A probe builds the relations and answers a String (`run` takes
no variants).
"""
import unittest

from tests.test_objects import check, closure, compile_job

PROBE = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./Relation.obend as Relations
record Row:
  who: String
  n: Nat
  note: String
record Pet:
  who: String
  kind: String
# The key {n, who}: canonical bytes put the shorter column name first, so n, then who.
def key(row: Row) -> {n: Nat, who: String}:
  {n: row.n, who: row.who}
def byWho(row: Row) -> {who: String}:
  {who: row.who}
# {who, kind}: who first (three letters before four), so pets sort by who, then kind.
def petKey(pet: Pet) -> {who: String, kind: String}:
  {who: pet.who, kind: pet.kind}
def petWho(pet: Pet) -> {who: String}:
  {who: pet.who}
def row(who: String, n: Nat, note: String) -> Row:
  {who: who, n: n, note: note}
def unsorted() -> Lists.List<Row>:
  Lists.List.cons({head: row("bo", 2n, "x"), tail: Lists.List.cons({head: row("al", 10n, "y"), tail: Lists.List.cons({head: row("al", 2n, "z"), tail: Lists.List.cons({head: row("bo", 2n, "dup"), tail: Lists.List.cons({head: row("c", 2n, "w"), tail: Lists.List.nil({})})})})})})
def rel() -> Relations.Relation<Row>:
  Relations.fromList(unsorted(), key)
def shown(items: Lists.List<Row>) -> String:
  textJoin(Lists.map(items, fn(r: Row) -> String: "{r.who}{natText(r.n)}{r.note}"), ",")
def t1(a: String, b: String) -> String:
  natText(Relations.compare(a, b))
def cmp(which: Nat) -> String:
  let a = natText(Relations.compare(9n, 10n))
  let b = natText(Relations.compare(key(row("zz", 1n, "")), key(row("a", 2n, ""))))
  let c = t1("b", "aa")
  let d = t1("ab", "aB")
  let e = t1("did:plc:x", "did:plc:x")
  let f = t1("a…", "az")
  let g = natText(Relations.compare(key(row("a", 1n, "")), key(row("a", 1n, "q"))))
  "{a},{b},{c},{d},{e},{f},{g}"
def fromListed(n: Nat) -> String:
  shown(Relations.rows(rel()))
def queried(n: Nat) -> String:
  let r = rel()
  let w = shown(Relations.rows(Relations.where(r, fn(x: Row) -> Bool: x.n == 2n)))
  let p = textJoin(Relations.project(r, fn(x: Row) -> String: x.who), ",")
  let e = if Relations.exists(r, fn(x: Row) -> Bool: x.who == "c") then "yes" else "no"
  let f = if Relations.exists(r, fn(x: Row) -> Bool: x.who == "zz") then "yes" else "no"
  "{w}|{p}|{natText(Relations.count(r))}|{e}{f}"
def found(m: Lists.Maybe<Row>) -> String:
  match m:
    case none(_): "none"
    case some(s): s.value.note
def looked(n: Nat) -> String:
  let a = found(Relations.lookup(rel(), key(row("al", 10n, "")), key))
  let b = found(Relations.lookup(rel(), key(row("al", 3n, "")), key))
  let c = found(Relations.lookup(rel(), key(row("zz", 99n, "")), key))
  "{a},{b},{c}"
def ordered(n: Nat) -> String:
  shown(Relations.order(rel(), byWho))
def grouped(n: Nat) -> String:
  textJoin(Lists.map(Relations.group(rel(), byWho), fn(g: Relations.Group<Row, {who: String}>) -> String: "{natText(Lists.length(Relations.groupRows(g)))}:{shown(Relations.groupRows(g))}"), ";")
def pets() -> Relations.Relation<Pet>:
  Relations.fromList(Lists.List.cons({head: {who: "bo", kind: "owl"}, tail: Lists.List.cons({head: {who: "al", kind: "cat"}, tail: Lists.List.cons({head: {who: "al", kind: "eel"}, tail: Lists.List.cons({head: {who: "dee", kind: "fox"}, tail: Lists.List.nil({})})})})}), petKey)
def people() -> Relations.Relation<Row>:
  Relations.fromList(Lists.List.cons({head: row("bo", 0n, "b"), tail: Lists.List.cons({head: row("al", 0n, "a"), tail: Lists.List.cons({head: row("c", 0n, "c"), tail: Lists.List.nil({})})})}), byWho)
def joined(n: Nat) -> String:
  textJoin(Lists.map(Relations.joinOn(people(), pets(), byWho, petWho), fn(j: Relations.Joined<Row, Pet>) -> String: pairText(j)), ",")
def pairText(j: Relations.Joined<Row, Pet>) -> String:
  match j:
    case pair(p): "{p.left.who}-{p.right.kind}"
def numbered(n: Nat) -> Lists.List<Row>:
  if n == 0n then Lists.List.nil({}) else Lists.List.cons({head: row("w", n, "x"), tail: numbered(n - 1n)})
# Rows already in key order, as the host stores a relation.
def stored(n: Nat) -> Relations.Relation<Row>:
  Relations.Relation.rows({items: Lists.reverse(numbered(n))})
def bigJoin(n: Nat) -> Nat:
  Lists.length(Relations.joinOn(stored(n), stored(n), key, key))
def bigSort(n: Nat) -> Nat:
  Relations.count(Relations.fromList(numbered(n), key))
def edited(n: Nat) -> String:
  let r = rel()
  let a = shown(Relations.rows(Relations.insert(r, row("al", 5n, "new"), key)))
  let b = shown(Relations.rows(Relations.insert(r, row("al", 10n, "other"), key)))
  let c = shown(Relations.rows(Relations.upsert(r, row("al", 10n, "other"), key)))
  let d = shown(Relations.rows(Relations.retract(r, key(row("bo", 2n, "")), key)))
  let e = shown(Relations.rows(Relations.retract(r, key(row("no", 1n, "")), key)))
  "{a}|{b}|{c}|{d}|{e}"
"""


def run(entry, n=0, limits=None):
    compiled = compile_job(closure("Relation") + [{"name": "Probe", "source": PROBE}], entry)
    assert compiled["status"] == "compiled", compiled
    request = {"op": "run", "artifact": compiled["artifact"], "arguments": [{"tag": "natural", "value": str(n)}]}
    if limits:
        request["limits"] = limits
    out = check(request)
    assert out["status"] == "finished", out
    return out


class RelationLibrary(unittest.TestCase):
    def value(self, entry, n=0):
        return run(entry, n)["value"]["value"]

    def test_keys_compare_as_canonical_bytes(self):
        # 9 < 10; {n, who} decides on n first; a shorter text first; 'B' (0x42) before 'b';
        # equal; '…' (three bytes) is longer than 'z'; equal keys whatever the rest of the row.
        self.assertEqual(self.value("cmp"), "0,0,0,2,1,2,1")

    def test_from_list_sorts_by_key_and_keeps_the_first_of_a_key(self):
        # key {n, who}: (2,c) (2,al) (2,bo) (10,al) (a shorter text first); the second (2,bo) is dropped.
        self.assertEqual(self.value("fromListed"), "c2w,al2z,bo2x,al10y")

    def test_where_project_count_exists(self):
        self.assertEqual(self.value("queried"), "c2w,al2z,bo2x|c,al,bo,al|4|yesno")

    def test_lookup_finds_by_key_and_stops_past_it(self):
        self.assertEqual(self.value("looked"), "y,none,none")

    def test_order_and_group_by_another_key(self):
        self.assertEqual(self.value("ordered"), "c2w,al2z,al10y,bo2x")
        self.assertEqual(self.value("grouped"), "1:c2w;2:al2z,al10y;1:bo2x")

    def test_join_on_merges_two_relations(self):
        # pets keyed {who, kind}; people keyed {who}: al has two pets, c none, dee no person.
        self.assertEqual(self.value("joined"), "al-cat,al-eel,bo-owl")

    def test_insert_upsert_retract_mirror_the_host_table(self):
        self.assertEqual(self.value("edited"), "|".join([
            "c2w,al2z,bo2x,al5new,al10y",   # insert of an absent key: placed in key order
            "c2w,al2z,bo2x,al10y",          # insert of a present key: unchanged
            "c2w,al2z,bo2x,al10other",      # upsert replaces
            "c2w,al2z,al10y",               # retract removes
            "c2w,al2z,bo2x,al10y",          # retract of an absent key: unchanged
        ]))

    def test_a_merge_join_of_two_stored_relations_is_linear(self):
        sort = run("bigSort", 64, limits={"ticks": "1000000", "heap": "1000000"})
        join = run("bigJoin", 200, limits={"ticks": "1000000", "heap": "1000000"})
        print("\n  fromList of 64 rows in reverse order: %s ticks; joinOn of two stored 200-row relations: %s ticks"
              % (sort.get("ticksUsed"), join.get("ticksUsed")))
        self.assertEqual(sort["value"]["value"], "64")
        self.assertEqual(join["value"]["value"], "200")


if __name__ == "__main__":
    unittest.main()
