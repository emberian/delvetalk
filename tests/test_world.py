"""The world kernel: create and view, per-field edits, commit on current roots, laws, retries,
history, replay to the same head, and a tampered journal refused by height.

Evidence for FOUNDATION §2 (layer: host).

World kernel: object store, hash-chained journal, commit-on-roots, receipts.

Python only drives bytes over stdin/stdout; every decision is Lean's. Each case
is named by the defect that would make it fail.
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from tests.host import HostCase, binary
BINARY = binary()

COUNTER = """edition ObjectiveBend 1
record State:
  count: Nat
  open: Bool
  name: String
def initial() -> State:
  {count: 0n, open: true, name: "c"}
"""
MONOTONE = COUNTER.replace("def initial", "law counter: monotone(count)\ndef initial")
BOUNDED = COUNTER.replace("def initial", "law ceiling: new.count <= 5\ndef initial")


def nat(n):
    return {"tag": "natural", "value": str(n)}


def seed(count=0, open_=True, name="c"):
    return {"tag": "record", "fields": [
        {"name": "count", "value": nat(count)},
        {"name": "open", "value": {"tag": "boolean", "value": open_}},
        {"name": "name", "value": {"tag": "label", "value": name}}]}


def variant(label, **payload):
    return {"tag": "variant", "label": label, "payload": {"tag": "record", "fields": [
        {"name": k, "value": v} for k, v in payload.items()]}}


def add(field, n):
    return field, variant("add", delta=nat(n))


def put(field, value):
    return field, variant("set", value=value)


def keep(field):
    return field, variant("keep")


class WorldCase(HostCase):
    """One host process per class, a fresh journal per test (tests.host.HostCase)."""

    def let_go(self):
        """Close this test's hold on the journal, so another process may open it."""
        self.release()

    def create(self, obj="c1", source=COUNTER, count=0, identity=None, host=None):
        return (host or self.host).send(op="world-create", principal="ember",
                                        identity=identity or "create-" + obj, object=obj,
                                        source=source, entry="initial", seed=seed(count))

    def propose(self, identity, roots, writes, principal="ember", host=None):
        return (host or self.host).send(op="world-propose", principal=principal, identity=identity,
                                        roots=roots, writes=writes)

    def view(self, obj="c1", host=None):
        return (host or self.host).send(op="world-view", principal="ember", object=obj)

    def lines(self):
        with open(self.path) as f:
            return f.read().splitlines()


def root(obj, version):
    return {"object": obj, "version": version}


def write(obj, *edits):
    """One Edits record: a variant per field, as in world/lib/Plan.obend."""
    return {"object": obj, "edits": {"tag": "record", "fields": [
        {"name": f, "value": v} for f, v in edits]}}


class Requests(WorldCase):
    def test_malformed_creates_and_requests_are_errors_before_the_journal(self):
        h = self.spawn()
        self.assertIn("world-open", h.send(op="world-view", principal="ember", object="c1")["message"])
        self.assertEqual(self.view("nope")["status"], "unknown")
        # A partial seed is laid over initial() (test_receive); a field of the wrong type is refused.
        bad = {"tag": "record", "fields": [{"name": "count", "value": {"tag": "label", "value": "one"}}]}
        r = self.host.send(op="world-create", principal="ember", identity="x", object="c1", source=COUNTER, entry="initial", seed=bad)
        self.assertIn("conform", r["message"])
        r = self.host.send(op="world-create", principal="ember", identity="x", object="c1",
                           source="edition ObjectiveBend 1\ndef initial() -> Nat:\n  0n\n", entry="initial", seed=nat(0))
        self.assertEqual(r["status"], "error")
        self.assertIn("law adapter", self.host.send(op="compile", source=MONOTONE, entry="initial")["message"])
        self.assertEqual(self.host.send(op="world-status")["height"], 0)
        self.create()
        self.create("c2")
        for name, r in [("existing object", self.create(identity="again")),
                        ("duplicate field edit", self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1), add("count", 1))])),
                        ("write outside the roots", self.propose("p2", [root("c1", 0)], [write("c2", add("count", 1))])),
                        ("identity over 256", self.propose("x" * 257, [root("c1", 0)], [])),
                        ("object id over 128", self.propose("ok", [root("o" * 129, 0)], [])),
                        ("65 roots", self.propose("many", [root(f"o{i}", 0) for i in range(65)], []))]:
            self.assertEqual(r["status"], "error", name)
        self.assertEqual(self.host.send(op="world-status")["height"], 2)


class Edits(WorldCase):
    def setUp(self):
        super().setUp()
        self.create(count=1)

    def test_add_set_and_keep_apply_per_field_exactly_beyond_machine_words(self):
        r = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 2 ** 80),
                         put("name", {"tag": "label", "value": "z"}), keep("open"))])
        self.assertEqual(r["receipt"]["outcome"]["writes"][0]["version"], 1)
        self.assertEqual(self.view()["state"], seed(2 ** 80 + 1, True, "z"))

    def test_ill_typed_edits_are_type_mismatches_and_oversized_state_is_capacity(self):
        for edit, cls in [(add("open", 1), "typeMismatch"), (put("count", {"tag": "boolean", "value": True}), "typeMismatch"),
                          (add("ghost", 1), "typeMismatch"), (put("name", {"tag": "label", "value": "x" * 300000}), "capacity")]:
            r = self.propose("p-" + edit[0] + cls, [root("c1", 0)], [write("c1", edit)])
            self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", cls), edit)
        self.assertEqual(self.view()["version"], 0)


class Commit(WorldCase):
    def setUp(self):
        super().setUp()
        self.create()
        self.create("c2")

    def test_stale_root_is_refused_and_the_receipt_commits_to_the_version_it_saw(self):
        # A `set` does not commute; two `add`s against one root both commit (tests/test_commute.py).
        self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])
        r = self.propose("p2", [root("c1", 0)], [write("c1", put("count", nat(5)))])
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out["object"]), ("refused", "staleRoot", "c1"))
        self.assertEqual(r["receipt"]["roots"], [root("c1", 0)])
        self.assertEqual(self.view()["state"], seed(1))
        # A stale read-only root refuses the write to another object too.
        self.propose("p3", [root("c2", 0)], [write("c2", add("count", 1))])
        r = self.propose("p4", [root("c1", 1), root("c2", 0)], [write("c1", add("count", 1))])
        self.assertEqual(r["receipt"]["outcome"]["class"], "staleRoot")
        self.assertEqual(self.propose("p5", [root("ghost", 0)], [])["receipt"]["outcome"]["class"], "unknownObject")

    def test_a_multi_object_proposal_is_all_or_nothing(self):
        r = self.propose("p1", [root("c1", 0), root("c2", 0)],
                         [write("c1", add("count", 1)), write("c2", add("open", 1))])
        self.assertEqual(r["status"], "refused")
        self.assertEqual((self.view("c1")["version"], self.view("c2")["version"]), (0, 0))


class Laws(WorldCase):
    def test_monotone_law_refuses_a_decrement_and_names_the_clause(self):
        self.create(source=MONOTONE, count=5)
        self.assertEqual(self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])["status"], "admitted")
        bad = self.propose("p2", [root("c1", 1)], [write("c1", put("count", nat(2)))])
        out = bad["receipt"]["outcome"]
        self.assertEqual((bad["status"], out["class"], out["clause"]), ("refused", "lawRefused", "counter"))
        self.assertEqual(self.view()["state"], seed(6))

    def test_law_reads_the_height_of_the_entry_it_judges(self):
        self.create(source=COUNTER.replace("def initial", "law early: request.height <= 3\ndef initial"))
        got = [self.propose(f"p{i}", [root("c1", i)], [write("c1", add("count", 1))]) for i in range(3)]  # heights 2, 3, 4
        self.assertEqual([r["status"] for r in got], ["admitted", "admitted", "refused"])
        self.assertEqual(got[2]["receipt"]["outcome"]["clause"], "early")


class Retry(WorldCase):
    """The retained receipt and duplicateIdentity on direct turns are test_properties; these are the
    raw proposal's: a stale refusal binds nothing, identities are per principal, lookup by identity."""

    def setUp(self):
        super().setUp()
        self.create()

    def test_a_stale_refusal_does_not_bind_the_identity_and_the_reread_retry_commits(self):
        first = self.propose("p1", [root("c1", 9)], [write("c1", add("count", 1))])
        self.assertEqual(first["receipt"]["outcome"]["class"], "staleRoot")
        again = self.propose("p1", [root("c1", 9)], [write("c1", add("count", 1))])
        self.assertNotEqual(again["receipt"]["hash"], first["receipt"]["hash"])   # judged again, journaled again
        reread = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])
        self.assertEqual(reread["status"], "admitted", reread)
        self.assertEqual(self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))]), reread)
        other = self.propose("p1", [root("c1", 1)], [write("c1", add("count", 5))])
        self.assertEqual((other["class"], other["original"]), ("duplicateIdentity", reread["receipt"]["hash"]))
        self.assertEqual(self.host.send(op="world-receipt", principal="ember", identity="p1")["receipt"], reread["receipt"])
        self.assertEqual(self.host.send(op="world-receipt", principal="ember", identity="zzz"), {"status": "unknown"})
        self.assertEqual(self.host.send(op="world-receipt", principal="other", identity="p1"), {"status": "unknown"})

    def test_identity_is_per_principal(self):
        # The default law admits only the creator's proposals (kind 3, proposed); open them to anyone.
        opened = self.host.send(op="world-amend", principal="ember", identity="open", object="c1", version=0,
                                law='law open: request.kind == 0 or request.kind == 3 or request.subject == "ember"')
        self.assertEqual(opened["status"], "admitted", opened)
        a = self.propose("p1", [root("c1", 1)], [write("c1", add("count", 1))], principal="a")
        b = self.propose("p1", [root("c1", 2)], [write("c1", add("count", 1))], principal="b")
        self.assertEqual((a["status"], b["status"]), ("admitted", "admitted"))


class History(WorldCase):
    def test_history_lists_only_admitted_entries_touching_the_object_bounded_and_paged(self):
        self.create()
        self.create("c2")
        for i in range(5):
            self.propose(f"a{i}", [root("c1", i)], [write("c1", add("count", 1))])
        self.propose("stale", [root("c1", 0)], [write("c1", put("count", nat(1)))])
        self.propose("other", [root("c2", 0)], [write("c2", add("count", 1))])
        h = self.host.send(op="world-history", principal="ember", object="c1", limit=3)
        heights = [e["height"] for e in h["entries"]]
        self.assertEqual((heights, h["more"]), ([1, 3, 4], True))  # creation, then two writes
        rest = self.host.send(op="world-history", principal="ember", object="c1", after=heights[-1], limit=100)
        self.assertEqual(([e["height"] for e in rest["entries"]], rest["more"]), ([5, 6, 7], False))
        self.assertEqual(self.host.send(op="world-history", principal="ember", object="ghost")["status"], "unknown")
        for bad in (10 ** 9, 0, "ten", -1):
            self.assertIn("limit", self.host.send(op="world-history", principal="ember", object="c1", limit=bad)["message"], bad)
        self.assertEqual(self.host.send(op="world-history", principal="ember", object="c1", after="x")["status"], "error")


class Tamper(WorldCase):
    def test_a_damaged_journal_refuses_open_naming_the_height_and_a_restart_continues_the_head(self):
        self.create()
        for i in range(4):
            self.propose(f"p{i}", [root("c1", i)], [write("c1", add("count", 1))])
        head = self.host.send(op="world-status")["head"]
        self.let_go()
        good = self.lines()

        def opened(lines, cut=0):
            with open(self.path, "w") as f:
                f.write("\n".join(lines) + "\n")
            if cut:
                with open(self.path, "rb+") as f:
                    f.seek(-cut, 2)
                    f.truncate()
            h = self.spawn()
            return h, h.send(op="world-open", path=self.path)

        for name, lines, cut, height in [("deleted line", good[:2] + good[3:], 0, 3), ("truncated tail", good, 5, 5),
                                         ("garbage", ["not json"] + good[1:], 0, 1)]:
            h, r = opened(lines, cut)
            self.assertEqual(r["status"], "error", name)
            self.assertIn("height %d" % height, r["message"], name)
            self.assertEqual(h.send(op="world-view", principal="e", object="c1")["status"], "error", name)
        fresh, r = opened(good)
        self.assertEqual(r["status"], "opened")
        r = self.propose("p9", [root("c1", 4)], [write("c1", add("count", 1))], host=fresh)
        self.assertEqual(r["receipt"]["previous"], head)


if __name__ == "__main__":
    unittest.main()
