"""A Relation field stays sorted by its key's canonical bytes with no key twice, within its limit,
and insert, upsert and retract commit or refuse by the nine-cell table.

Evidence for FOUNDATION §9 (layer: host).

Relations in objects (docs/RELATIONAL.md §2, §3): a `Relation<T>` field the package declares in
`relations()` is kept sorted by its key's canonical bytes with no key twice and at most its limit of
rows; `insert`, `upsert`, `retract` follow the nine-cell table. Each case names what would refute it.

    python3 -W error -m unittest tests.test_relation -v
"""
import unittest

from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record, declared

# The relation type and its edits are declared here as the library will declare them (Relation.obend,
# Plan.obend's Entries): the host reads labels, not type names.
PACKAGE = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record Rain:
  author: String
  at: Nat
  text: String
sum Relation<T>:
  rows: {items: Lists.List<T>}
record Decl:
  field: String
  key: Lists.List<String>
  limit: Nat
record Key:
  author: String
  at: Nat
record State:
  count: Nat
  rains: Relation<Rain>
def relations() -> Lists.List<Decl>:
  Lists.List.cons({head: {field: "rains", key: Lists.List.cons({head: "author", tail: Lists.List.cons({head: "at", tail: Lists.List.nil({})})}), limit: LIMIT}, tail: Lists.List.nil({})})
def initial() -> State:
  {count: 0n, rains: Relation.rows({items: Lists.List.nil({})})}
def edit(context: Abi.Context, e: Plans.Entries<Rain, Rain>) -> Activity<Nat>:
  match world.write(extend(keep(), {rains: e})):
    case written(_): 1n
    case refused(_): 0n
    case _: 2n
def insert(state: State, input: Rain, context: Abi.Context) -> Activity<Nat>:
  edit(context, Plans.Entries.insert({row: input}))
def upsert(state: State, input: Rain, context: Abi.Context) -> Activity<Nat>:
  edit(context, Plans.Entries.upsert({row: input}))
def retract(state: State, input: Key, context: Abi.Context) -> Activity<Nat>:
  edit(context, Plans.Entries.retract({key: input}))
def later(context: Abi.Context, e: Plans.Entries<Rain, Rain>) -> Activity<Nat>:
  match world.await({slot: {principal: "ann", intent: "go"}, patience: 50n}):
    case _: edit(context, e)
def laterInsert(state: State, input: Rain, context: Abi.Context) -> Activity<Nat>:
  later(context, Plans.Entries.insert({row: input}))
def laterUpsert(state: State, input: Rain, context: Abi.Context) -> Activity<Nat>:
  later(context, Plans.Entries.upsert({row: input}))
def laterRetract(state: State, input: Key, context: Abi.Context) -> Activity<Nat>:
  later(context, Plans.Entries.retract({key: input}))
""")


def rain(author, at, text):
    return record(author=label(author), at=nat(at), text=label(text))


def rows_of(state):
    rel = {f["name"]: f["value"] for f in state["fields"]}["rains"]
    items = {f["name"]: f["value"] for f in rel["payload"]["fields"]}["items"]
    out = []
    for item in items["items"]:
        f = {x["name"]: x["value"] for x in item["fields"]}
        out.append((f["author"]["value"], int(f["at"]["value"]), f["text"]["value"]))
    return out


def relation(*rains):
    return {"tag": "variant", "label": "rows", "payload": record(items={"tag": "list", "items": list(rains)})}


class RelationCase(Reflection):
    LIMIT = 4096

    def setUp(self):
        super().setUp()
        self.open_library()

    def make_bell(self, seed=None, name="b", limit=None):
        source = PACKAGE.replace("LIMIT", f"{limit if limit is not None else self.LIMIT}n")
        return self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name, source=source,
                              entry="initial", seed=seed or record())

    def rows(self, name="b"):
        return rows_of(self.host.send(op="world-view", principal="ember", object=name)["state"])

    def edit(self, method, arg, who="ann", ident=None, name="b"):
        self.n = getattr(self, "n", 0) + 1
        return self.host.send(op="world-turn", principal=who, object=name, method=method, argument=arg,
                              identity=ident or f"e{self.n}")



class Relations(RelationCase):
    def test_an_unsorted_seed_is_canonical_and_a_duplicate_key_is_refused(self):
        made = self.make_bell(record(rains=relation(rain("kim", 5, "late"), rain("ann", 9, "x"), rain("ann", 2, "early"))))
        self.assertEqual(made["status"], "created", made)
        # Ordered by the key's canonical DAG-CBOR bytes: map keys sort by length, so `at` leads.
        self.assertEqual(self.rows(), [("ann", 2, "early"), ("kim", 5, "late"), ("ann", 9, "x")])
        dup = self.make_bell(record(rains=relation(rain("ann", 2, "a"), rain("ann", 2, "b"))), name="d")
        self.assertEqual(dup["status"], "error", dup)
        self.assertIn("duplicateKey", dup["message"])

    def test_a_key_naming_a_missing_column_is_refused_at_creation(self):
        bad = PACKAGE.replace('Lists.List.cons({head: "at", tail', 'Lists.List.cons({head: "when", tail').replace("LIMIT", "0n")
        r = self.host.send(op="world-create", principal="ember", identity="mk-k", object="k", source=bad,
                           entry="initial", seed=record())
        self.assertEqual(r["status"], "error", r)
        self.assertIn("key: relation rains names column when, which its rows lack", r["message"])

    def test_insert_upsert_and_retract_follow_the_nine_cell_table_and_replay(self):
        self.assertEqual(self.make_bell()["status"], "created")
        result = lambda r: (r["status"], r.get("result", {}).get("value"), r["receipt"]["outcome"].get("class"))
        # insert: absent adds; same row is no change; other row is keyTaken.
        self.assertEqual(result(self.edit("insert", rain("ann", 1, "a"))), ("admitted", "1", None))
        self.assertEqual(result(self.edit("insert", rain("ann", 1, "a"))), ("admitted", "1", None))
        self.assertEqual(result(self.edit("insert", rain("ann", 1, "b")))[::2], ("refused", "keyTaken"))
        self.assertEqual(self.rows(), [("ann", 1, "a")])
        # upsert: absent adds; same row no change; other row replaces.
        self.edit("upsert", rain("kim", 1, "k"))
        self.edit("upsert", rain("kim", 1, "k"))
        self.edit("upsert", rain("ann", 1, "b"))
        self.assertEqual(self.rows(), [("ann", 1, "b"), ("kim", 1, "k")])
        # retract: absent is no change; present (whatever its row) removes.
        key = lambda a, t: record(author=label(a), at=nat(t))
        self.assertEqual(result(self.edit("retract", key("zed", 3))), ("admitted", "1", None))
        self.assertEqual(self.rows(), [("ann", 1, "b"), ("kim", 1, "k")])
        self.edit("retract", key("ann", 1))
        self.assertEqual(self.rows(), [("kim", 1, "k")])
        # The journal replays to the same rows.
        self.reopen()
        self.assertEqual(self.rows(), [("kim", 1, "k")])

    def test_a_declared_limit_drops_the_oldest_by_key_order(self):
        self.assertEqual(self.make_bell(limit=2)["status"], "created")
        for who, at in (("bo", 1), ("al", 1), ("cy", 1)):
            self.edit("insert", rain(who, at, who))
        self.assertEqual(self.rows(), [("bo", 1, "bo"), ("cy", 1, "cy")])
        self.reopen()
        self.assertEqual(self.rows(), [("bo", 1, "bo"), ("cy", 1, "cy")])

    def reprogram(self, source, ident, name="b"):
        version = self.host.send(op="world-view", principal="ember", object=name)["version"]
        return self.host.send(op="world-reprogram", principal="ember", identity=ident, object=name, version=version,
                              package=source.replace("LIMIT", f"{self.LIMIT}n"), migration="migrate")

    def test_a_migration_result_is_made_canonical_and_a_duplicate_key_refuses_it(self):
        # Refuted if the host journals the migration's rows in the order the migration wrote them,
        # or admits a migration whose rows share a key.
        self.assertEqual(self.make_bell()["status"], "created")
        cons = lambda a, t, rest: f'Lists.List.cons({{head: {{author: "{a}", at: {t}n, text: "m"}}, tail: {rest}}})'
        migrate = lambda rows: PACKAGE + "def migrate(old: State) -> State:\n  {count: old.count, rains: Relation.rows({items: " + rows + "})}\n"
        unsorted = cons("kim", 5, cons("ann", 9, cons("ann", 2, "Lists.List.nil({})")))
        r = self.reprogram(migrate(unsorted), "rp1")
        self.assertEqual(r["receipt"]["outcome"]["tag"], "admitted", r)
        self.assertEqual(self.rows(), [("ann", 2, "m"), ("kim", 5, "m"), ("ann", 9, "m")])
        self.reopen()
        self.assertEqual(self.rows(), [("ann", 2, "m"), ("kim", 5, "m"), ("ann", 9, "m")])
        dup = self.reprogram(migrate(cons("ann", 2, cons("ann", 2, "Lists.List.nil({})"))) + "# again\n", "rp2")
        self.assertEqual((dup["receipt"]["outcome"]["class"], dup["receipt"]["outcome"].get("clause")),
                         ("programRefused", "migration"), dup)
        reason = dup["receipt"]["outcome"]["reason"]
        self.assertTrue(reason.startswith("the package was refused at migration; the workshop's check shows where: "), reason)
        self.assertIn("duplicateKey", reason)
        self.assertEqual(self.rows(), [("ann", 2, "m"), ("kim", 5, "m"), ("ann", 9, "m")])

    def test_only_the_entry_modules_relations_count(self):
        # Refuted if a package whose imported module declares relations() but whose entry module
        # declares none is refused ("missing selected entry") or given that module's relations.
        helper = PACKAGE.replace("LIMIT", "0n")
        entry = """edition ObjectiveBend 1
import ./Rel.obend as Rel
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
"""
        r = self.host.send(op="world-create", principal="ember", identity="mk-e", object="e",
                           modules=[{"name": "Rel", "source": helper}, {"name": "Main", "source": entry}],
                           entry="initial", seed=record())
        self.assertEqual(r["status"], "created", r)

    def test_twenty_creations_compile_the_package_once(self):
        # Refuted if each creation compiles relations() anew (a creation then costs a compile).
        import time
        self.assertEqual(self.make_bell(name="b0")["status"], "created")
        start = time.monotonic()
        for i in range(1, 21):
            self.assertEqual(self.make_bell(name=f"b{i}")["status"], "created")
        self.assertLess(time.monotonic() - start, 3.0)
        self.reopen()
        self.edit("insert", rain("ann", 1, "a"), name="b20")
        self.assertEqual(self.rows("b20"), [("ann", 1, "a")])

    def test_relational_law_atoms_judge_writes(self):
        # Refuted if insertOnly/count/column membership refuse every write (or admit a retract).
        law = ('law grow: insertOnly(rains)\nlaw small: count(new.rains) <= 2\n'
               'law once: count(new.rains) <= count(old.rains) + 1\nlaw mine: request.subject in new.rains.author\n')
        source = PACKAGE.replace("LIMIT", "0n").replace("def relations()", law + "def relations()")
        r = self.host.send(op="world-create", principal="ember", identity="mk-l", object="l", source=source,
                           entry="initial", seed=record(rains=relation(rain("ember", 0, "seed"))))
        self.assertEqual(r["status"], "created", r)
        outcome = lambda r: (r["status"], r["receipt"]["outcome"].get("clause"))
        self.assertEqual(outcome(self.edit("insert", rain("ann", 1, "a"), who="ann", name="l")), ("admitted", None))
        self.assertEqual(outcome(self.edit("upsert", rain("ann", 1, "b"), who="ann", name="l")), ("refused", "grow"))
        self.assertEqual(outcome(self.edit("retract", record(author=label("ann"), at=nat(1)), who="ann", name="l")),
                         ("refused", "grow"))
        self.assertEqual(outcome(self.edit("insert", rain("kim", 2, "k"), who="bob", name="l")), ("refused", "small"))
        self.assertEqual(self.rows("l"), [("ember", 0, "seed"), ("ann", 1, "a")])

    def test_insert_only_does_not_count_the_rows_retention_drops(self):
        # Refuted if a full relation with a limit refuses an insert (its oldest row by key goes), or
        # if a retract or an upsert is admitted once the relation is full.
        source = PACKAGE.replace("LIMIT", "2n").replace("def relations()", "law grow: insertOnly(rains)\ndef relations()")
        r = self.host.send(op="world-create", principal="ember", identity="mk-r", object="r", source=source,
                           entry="initial", seed=record(rains=relation(rain("ember", 0, "seed"))))
        self.assertEqual(r["status"], "created", r)
        outcome = lambda r: (r["status"], r["receipt"]["outcome"].get("clause"))
        for i, who in enumerate(("ann", "kim", "eve"), 1):
            self.assertEqual(outcome(self.edit("insert", rain(who, i, who[0]), who=who, name="r")), ("admitted", None))
        self.assertEqual([a for a, _, _ in self.rows("r")], ["kim", "eve"])
        self.assertEqual(outcome(self.edit("upsert", rain("kim", 2, "changed"), who="kim", name="r")), ("refused", "grow"))
        self.assertEqual(outcome(self.edit("retract", record(author=label("kim"), at=nat(2)), who="kim", name="r")),
                         ("refused", "grow"))


def key(author, at):
    return record(author=label(author), at=nat(at))


class Moved(RelationCase):
    """Relations day 2 (RELATIONAL §3): a turn that waited commits its row edits against the
    relation as it is now. An insert commutes; an upsert or retract commutes with every change that
    left its key alone; a concurrent change of its key makes it staleRoot, and the waiting turn is
    re-run once from its request on the rows as they are now."""

    def pair(self, waiting, arg, concurrent, carg):
        """`waiting` suspends (kim's turn); ann's `concurrent` edit (identity go) moves the relation
        and releases it. Answers the waiting turn's resumption."""
        self.assertEqual(self.edit(waiting, arg, who="kim", ident="w")["status"], "suspended")
        r = self.edit(concurrent, carg, ident="go")
        self.assertEqual(r["status"], "admitted", r)
        [resumed] = r["resumed"]
        return resumed

    def setUp(self):
        super().setUp()
        self.assertEqual(self.make_bell(record(rains=relation(rain("old", 0, "o"))))["status"], "created")

    def test_insert_and_insert_of_other_keys_commute(self):
        resumed = self.pair("laterInsert", rain("kim", 1, "k"), "insert", rain("ann", 2, "a"))
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertNotIn("rerunOf", resumed)
        self.assertEqual(self.rows(), [("old", 0, "o"), ("kim", 1, "k"), ("ann", 2, "a")])
        self.reopen()
        self.assertEqual(self.rows(), [("old", 0, "o"), ("kim", 1, "k"), ("ann", 2, "a")])

    def test_an_insert_of_the_same_row_is_idempotent(self):
        resumed = self.pair("laterInsert", rain("ann", 2, "a"), "insert", rain("ann", 2, "a"))
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertEqual(self.rows(), [("old", 0, "o"), ("ann", 2, "a")])

    def test_two_inserts_of_one_key_with_different_rests_the_second_is_key_taken(self):
        resumed = self.pair("laterInsert", rain("ann", 2, "mine"), "insert", rain("ann", 2, "theirs"))
        self.assertEqual((resumed["status"], resumed["receipt"]["outcome"]["class"]), ("refused", "keyTaken"), resumed)
        self.assertNotIn("rerunOf", resumed)
        self.assertEqual(self.rows(), [("old", 0, "o"), ("ann", 2, "theirs")])

    def test_upsert_commutes_with_an_insert_of_another_key(self):
        resumed = self.pair("laterUpsert", rain("old", 0, "new"), "insert", rain("ann", 2, "a"))
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertNotIn("rerunOf", resumed)
        self.assertEqual(self.rows(), [("old", 0, "new"), ("ann", 2, "a")])
        self.reopen()
        self.assertEqual(self.rows(), [("old", 0, "new"), ("ann", 2, "a")])

    def test_retract_commutes_with_an_upsert_of_another_key(self):
        resumed = self.pair("laterRetract", key("old", 0), "upsert", rain("ann", 2, "a"))
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertNotIn("rerunOf", resumed)
        self.assertEqual(self.rows(), [("ann", 2, "a")])

    def test_insert_commutes_with_a_retract(self):
        resumed = self.pair("laterInsert", rain("kim", 1, "k"), "retract", key("old", 0))
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertEqual(self.rows(), [("kim", 1, "k")])

    def test_a_retract_of_a_key_changed_meanwhile_is_stale_and_the_rerun_reads_the_rows_now(self):
        # ann upserts the row kim waited to retract: kim's retract would silently remove a row it
        # never saw, so it is staleRoot (transient) and the turn is re-run on the rows now.
        resumed = self.pair("laterRetract", key("old", 0), "upsert", rain("old", 0, "changed"))
        self.assertIn("rerunOf", resumed)
        with open(self.path) as f:
            refused = [e for e in map(__import__("json").loads, f.read().splitlines()) if e["hash"] == resumed["rerunOf"]][0]
        self.assertEqual((refused["outcome"]["class"], refused["outcome"]["object"]), ("staleRoot", "b"))
        self.assertEqual((resumed["status"], resumed["receipt"].get("rerun")), ("admitted", True), resumed)
        # The re-run read the current row and retracted it.
        self.assertEqual(self.rows(), [])
        self.reopen()
        self.assertEqual(self.rows(), [])

    def test_an_upsert_of_a_key_retracted_meanwhile_is_stale(self):
        resumed = self.pair("laterUpsert", rain("old", 0, "mine"), "retract", key("old", 0))
        self.assertIn("rerunOf", resumed)
        self.assertEqual(self.rows(), [("old", 0, "mine")])


if __name__ == "__main__":
    unittest.main()
