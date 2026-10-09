"""World kernel: object store, hash-chained journal, commit-on-roots, receipts.

Python only drives bytes over stdin/stdout; every decision is Lean's. Each case
is named by the defect that would make it fail.
"""
import json
import os
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from tests.host import binary
from tests.wire import cid_of, relist
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


class Host:
    def __init__(self):
        self.proc = subprocess.Popen([BINARY], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1)

    def send(self, **request):
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        return relist(json.loads(self.proc.stdout.readline()))

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=30)
        self.proc.stdout.close()


class WorldCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "world.journal")
        self.hosts = []
        self.host = self.spawn()
        self.assertEqual(self.host.send(op="world-open", path=self.path)["status"], "opened")

    def tearDown(self):
        for h in self.hosts:
            h.close()
        self.dir.cleanup()

    def spawn(self):
        h = Host()
        self.hosts.append(h)
        return h

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


class CreateAndView(WorldCase):
    def test_create_and_view_returns_seed_at_version_zero(self):
        r = self.create(count=3)
        self.assertEqual(r["status"], "created")
        v = self.view()
        self.assertEqual((v["status"], v["version"]), ("viewed", 0))
        self.assertEqual(v["state"], seed(3))
        self.assertTrue(v["pin"].startswith("bafyrei"), v["pin"])  # a CID: 59 characters
        self.assertEqual(r["receipt"]["outcome"]["pin"], v["pin"])

    def test_view_of_unknown_object_is_a_named_silence(self):
        self.assertEqual(self.view("nope")["status"], "unknown")

    def test_seed_not_conforming_to_the_entry_type_is_refused(self):
        bad = {"tag": "record", "fields": [{"name": "count", "value": nat(1)}]}
        r = self.host.send(op="world-create", principal="ember", identity="x", object="c1",
                           source=COUNTER, entry="initial", seed=bad)
        self.assertEqual(r["status"], "error")
        self.assertIn("conform", r["message"])
        self.assertEqual(self.host.send(op="world-status")["height"], 0)

    def test_entry_that_is_not_a_data_record_is_refused(self):
        src = "edition ObjectiveBend 1\ndef initial() -> Nat:\n  0n\n"
        r = self.host.send(op="world-create", principal="ember", identity="x", object="c1",
                           source=src, entry="initial", seed=nat(0))
        self.assertEqual(r["status"], "error")

    def test_creating_an_existing_object_under_a_new_identity_is_refused(self):
        self.create()
        r = self.create(identity="again")
        self.assertEqual(r["status"], "error")

    def test_ops_before_world_open_say_so(self):
        h = self.spawn()
        r = h.send(op="world-view", principal="ember", object="c1")
        self.assertEqual(r["status"], "error")
        self.assertIn("world-open", r["message"])


class Edits(WorldCase):
    def setUp(self):
        super().setUp()
        self.create(count=1)

    def test_add_set_and_keep_apply_per_field(self):
        r = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 2),
                         put("name", {"tag": "label", "value": "z"}), keep("open"))])
        self.assertEqual(r["status"], "admitted")
        v = self.view()
        self.assertEqual(v["version"], 1)
        self.assertEqual(v["state"], seed(3, True, "z"))
        self.assertEqual(r["receipt"]["outcome"]["writes"][0]["version"], 1)

    def test_add_on_a_boolean_is_a_type_mismatch(self):
        r = self.propose("p1", [root("c1", 0)], [write("c1", add("open", 1))])
        self.assertEqual(r["status"], "refused")
        self.assertEqual(r["receipt"]["outcome"]["class"], "typeMismatch")
        self.assertEqual(self.view()["version"], 0)

    def test_set_with_the_wrong_type_is_a_type_mismatch(self):
        r = self.propose("p1", [root("c1", 0)], [write("c1", put("count", {"tag": "boolean", "value": True}))])
        self.assertEqual(r["receipt"]["outcome"]["class"], "typeMismatch")

    def test_edit_of_an_undeclared_field_is_a_type_mismatch(self):
        r = self.propose("p1", [root("c1", 0)], [write("c1", add("ghost", 1))])
        self.assertEqual(r["receipt"]["outcome"]["class"], "typeMismatch")

    def test_duplicate_edit_of_one_field_is_a_malformed_request_not_a_receipt(self):
        r = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1), add("count", 1))])
        self.assertEqual(r["status"], "error")
        self.assertEqual(self.host.send(op="world-status")["height"], 1)

    def test_natural_add_is_exact_beyond_machine_words(self):
        big = 2 ** 80
        self.propose("p1", [root("c1", 0)], [write("c1", add("count", big))])
        self.assertEqual(self.view()["state"], seed(big + 1))


class Commit(WorldCase):
    def setUp(self):
        super().setUp()
        self.create()
        self.create("c2")

    def test_stale_root_is_refused_and_the_receipt_commits_to_the_version_it_saw(self):
        self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])
        r = self.propose("p2", [root("c1", 0)], [write("c1", add("count", 1))])
        self.assertEqual(r["status"], "refused")
        out = r["receipt"]["outcome"]
        self.assertEqual((out["class"], out["object"]), ("staleRoot", "c1"))
        self.assertEqual(r["receipt"]["roots"], [root("c1", 0)])
        self.assertEqual(self.view()["state"], seed(1))

    def test_a_stale_read_only_root_also_refuses_the_write_to_another_object(self):
        self.propose("p1", [root("c2", 0)], [write("c2", add("count", 1))])
        r = self.propose("p2", [root("c1", 0), root("c2", 0)], [write("c1", add("count", 1))])
        self.assertEqual(r["receipt"]["outcome"]["class"], "staleRoot")
        self.assertEqual(self.view("c1")["version"], 0)

    def test_a_proposal_writing_an_object_it_never_named_as_a_root_is_a_request_error(self):
        r = self.propose("p1", [root("c1", 0)], [write("c2", add("count", 1))])
        self.assertEqual(r["status"], "error")
        self.assertIn("not among the roots", r["message"])
        self.assertEqual(self.view("c2")["version"], 0)

    def test_unknown_object_in_roots_is_refused(self):
        r = self.propose("p1", [root("ghost", 0)], [])
        self.assertEqual(r["receipt"]["outcome"]["class"], "unknownObject")

    def test_a_multi_object_proposal_is_all_or_nothing(self):
        r = self.propose("p1", [root("c1", 0), root("c2", 0)],
                         [write("c1", add("count", 1)), write("c2", add("open", 1))])
        self.assertEqual(r["status"], "refused")
        self.assertEqual((self.view("c1")["version"], self.view("c2")["version"]), (0, 0))

    def test_two_different_identities_with_the_same_writes_both_admit_in_order(self):
        a = self.propose("pa", [root("c1", 0)], [write("c1", add("count", 1))])
        b = self.propose("pb", [root("c1", 1)], [write("c1", add("count", 1))])
        self.assertEqual((a["status"], b["status"]), ("admitted", "admitted"))
        self.assertEqual(b["receipt"]["height"], a["receipt"]["height"] + 1)
        self.assertEqual(b["receipt"]["previous"], a["receipt"]["hash"])
        self.assertEqual(self.view()["state"], seed(2))


class Laws(WorldCase):
    def test_monotone_law_refuses_a_decrement_and_names_the_clause(self):
        self.create(source=MONOTONE, count=5)
        ok = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])
        self.assertEqual(ok["status"], "admitted")
        bad = self.propose("p2", [root("c1", 1)], [write("c1", put("count", nat(2)))])
        out = bad["receipt"]["outcome"]
        self.assertEqual((bad["status"], out["class"], out["clause"]), ("refused", "lawRefused", "counter"))
        self.assertEqual(self.view()["state"], seed(6))

    def test_bound_law_admits_at_the_edge_and_refuses_past_it(self):
        self.create(source=BOUNDED, count=4)
        self.assertEqual(self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])["status"], "admitted")
        r = self.propose("p2", [root("c1", 1)], [write("c1", add("count", 1))])
        self.assertEqual(r["receipt"]["outcome"]["clause"], "ceiling")

    def test_law_reads_the_height_of_the_entry_it_judges(self):
        src = COUNTER.replace("def initial", "law early: request.height <= 3\ndef initial")
        self.create(source=src)
        a = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])  # height 2
        b = self.propose("p2", [root("c1", 1)], [write("c1", add("count", 1))])  # height 3
        c = self.propose("p3", [root("c1", 2)], [write("c1", add("count", 1))])  # height 4
        self.assertEqual([a["status"], b["status"], c["status"]], ["admitted", "admitted", "refused"])
        self.assertEqual(c["receipt"]["outcome"]["clause"], "early")

    def test_plain_compile_op_still_refuses_laws(self):
        r = self.host.send(op="compile", source=MONOTONE, entry="initial")
        self.assertEqual(r["status"], "error")
        self.assertIn("law adapter", r["message"])


class Retry(WorldCase):
    def setUp(self):
        super().setUp()
        self.create()

    def test_retry_of_the_same_identity_returns_the_identical_receipt_and_no_entry(self):
        first = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])
        height = self.host.send(op="world-status")["height"]
        again = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])
        self.assertEqual(again, first)
        self.assertEqual(self.host.send(op="world-status")["height"], height)
        self.assertEqual(self.view()["version"], 1)
        self.assertEqual(len(self.lines()), height)

    def test_retry_of_a_refusal_returns_the_same_refusal(self):
        first = self.propose("p1", [root("c1", 9)], [write("c1", add("count", 1))])
        self.assertEqual(self.propose("p1", [root("c1", 9)], [write("c1", add("count", 1))]), first)

    def test_same_identity_with_a_different_request_is_duplicate_identity_and_writes_nothing(self):
        first = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])
        height = self.host.send(op="world-status")["height"]
        other = self.propose("p1", [root("c1", 1)], [write("c1", add("count", 5))])
        self.assertEqual((other["status"], other["class"]), ("refused", "duplicateIdentity"))
        self.assertEqual(other["original"], first["receipt"]["hash"])
        self.assertEqual(self.host.send(op="world-status")["height"], height)

    def test_identity_is_per_principal(self):
        a = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))], principal="a")
        b = self.propose("p1", [root("c1", 1)], [write("c1", add("count", 1))], principal="b")
        self.assertEqual((a["status"], b["status"]), ("admitted", "admitted"))

    def test_receipt_lookup_by_identity_and_the_silence_for_an_unknown_one(self):
        first = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])
        got = self.host.send(op="world-receipt", principal="ember", identity="p1")
        self.assertEqual(got["receipt"], first["receipt"])
        self.assertEqual(self.host.send(op="world-receipt", principal="ember", identity="zzz"),
                         {"status": "unknown"})
        self.assertEqual(self.host.send(op="world-receipt", principal="other", identity="p1"),
                         {"status": "unknown"})


class History(WorldCase):
    def test_history_lists_only_admitted_entries_touching_the_object_bounded_and_paged(self):
        self.create()
        self.create("c2")
        for i in range(5):
            self.propose(f"a{i}", [root("c1", i)], [write("c1", add("count", 1))])
        self.propose("stale", [root("c1", 0)], [write("c1", add("count", 1))])
        self.propose("other", [root("c2", 0)], [write("c2", add("count", 1))])
        h = self.host.send(op="world-history", principal="ember", object="c1", limit=3)
        heights = [e["height"] for e in h["entries"]]
        self.assertEqual(heights, [1, 3, 4])  # creation, then two writes
        self.assertTrue(h["more"])
        rest = self.host.send(op="world-history", principal="ember", object="c1", after=heights[-1], limit=100)
        self.assertEqual([e["height"] for e in rest["entries"]], [5, 6, 7])
        self.assertFalse(rest["more"])
        self.assertEqual(self.host.send(op="world-history", principal="ember", object="ghost")["status"], "unknown")

    def test_a_history_limit_beyond_the_cap_or_malformed_is_refused_by_name(self):
        self.create()
        for bad in (10 ** 9, 0, "ten", -1):
            h = self.host.send(op="world-history", principal="ember", object="c1", limit=bad)
            self.assertEqual(h["status"], "error", (bad, h))
            self.assertIn("limit", h["message"])
        self.assertEqual(self.host.send(op="world-history", principal="ember", object="c1", after="x")["status"], "error")
        self.assertEqual(self.host.send(op="world-history", principal="ember", object="c1", limit=100)["status"], "history")


class Restart(WorldCase):
    def test_a_fresh_process_replays_to_identical_views_receipts_and_head(self):
        self.create(source=MONOTONE)
        self.create("c2")
        receipts = {}
        receipts["p1"] = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 2))])
        receipts["p2"] = self.propose("p2", [root("c1", 0)], [write("c1", add("count", 2))])  # stale
        receipts["p3"] = self.propose("p3", [root("c1", 1)], [write("c1", put("count", nat(0)))])  # law
        receipts["p4"] = self.propose("p4", [root("c1", 1), root("c2", 0)],
                                      [write("c2", put("name", {"tag": "label", "value": "q"}))])
        before = (self.view("c1"), self.view("c2"), self.host.send(op="world-status"))
        self.host.close()
        self.hosts.remove(self.host)
        fresh = self.spawn()
        opened = fresh.send(op="world-open", path=self.path)
        self.assertEqual(opened["status"], "opened")
        after = (self.view("c1", host=fresh), self.view("c2", host=fresh), fresh.send(op="world-status"))
        self.assertEqual(after, before)
        for ident, r in receipts.items():
            got = fresh.send(op="world-receipt", principal="ember", identity=ident)
            self.assertEqual(got["receipt"], r["receipt"])
        # The restarted world still judges: the law is rebuilt from the journal.
        bad = self.propose("p5", [root("c1", 1)], [write("c1", put("count", nat(0)))], host=fresh)
        self.assertEqual(bad["receipt"]["outcome"]["clause"], "counter")
        # And a retry across the restart is still a retry.
        self.assertEqual(self.propose("p1", [root("c1", 0)], [write("c1", add("count", 2))], host=fresh),
                         receipts["p1"])

    def test_the_new_chain_continues_the_old_head_after_restart(self):
        self.create()
        head = self.host.send(op="world-status")["head"]
        self.host.close()
        self.hosts.remove(self.host)
        fresh = self.spawn()
        fresh.send(op="world-open", path=self.path)
        r = self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))], host=fresh)
        self.assertEqual(r["receipt"]["previous"], head)


class Tamper(WorldCase):
    def build(self):
        self.create()
        for i in range(4):
            self.propose(f"p{i}", [root("c1", i)], [write("c1", add("count", 1))])
        self.host.close()
        self.hosts.remove(self.host)

    def open_fresh(self):
        h = self.spawn()
        return h.send(op="world-open", path=self.path)

    def rewrite(self, index, transform):
        lines = self.lines()
        lines[index] = transform(lines[index])
        with open(self.path, "w") as f:
            f.write("\n".join(lines) + "\n")

    def test_an_edited_write_refuses_open_and_names_the_height(self):
        self.build()
        self.rewrite(2, lambda l: l.replace('"value":"1"', '"value":"9"'))
        r = self.open_fresh()
        self.assertEqual(r["status"], "error")
        self.assertIn("height 3", r["message"])

    def test_a_tampered_hash_that_was_recomputed_still_breaks_the_next_link(self):
        self.build()

        def forge(line):
            entry = json.loads(line)
            entry["note"] = "forged"
            del entry["hash"]
            entry["hash"] = cid_of(entry)
            return json.dumps(entry, sort_keys=True, separators=(",", ":"))
        self.rewrite(1, forge)
        r = self.open_fresh()
        self.assertEqual(r["status"], "error")
        self.assertIn("height 3", r["message"])  # the chain, not the forged line, fails

    def test_a_deleted_line_refuses_open(self):
        self.build()
        lines = self.lines()
        del lines[2]
        with open(self.path, "w") as f:
            f.write("\n".join(lines) + "\n")
        r = self.open_fresh()
        self.assertEqual(r["status"], "error")
        self.assertIn("height 3", r["message"])

    def test_a_truncated_final_line_refuses_open(self):
        self.build()
        with open(self.path, "rb+") as f:
            f.seek(-5, 2)
            f.truncate()
        r = self.open_fresh()
        self.assertEqual(r["status"], "error")
        self.assertIn("height 5", r["message"])

    def test_garbage_line_names_its_height(self):
        self.build()
        self.rewrite(0, lambda l: "not json")
        self.assertIn("height 1", self.open_fresh()["message"])

    def test_a_failed_open_leaves_no_world_open(self):
        self.build()
        self.rewrite(2, lambda l: l.replace('"value":"1"', '"value":"9"'))
        h = self.spawn()
        h.send(op="world-open", path=self.path)
        self.assertEqual(h.send(op="world-view", principal="e", object="c1")["status"], "error")


class Maximum(WorldCase):
    def test_a_thousand_proposals_then_replay_under_ten_seconds(self):
        self.create()
        n = 1000
        t0 = time.time()
        for i in range(n):
            r = self.propose(f"p{i}", [root("c1", i)], [write("c1", add("count", 1))])
            self.assertEqual(r["status"], "admitted", r)
        build = time.time() - t0
        status = self.host.send(op="world-status")
        self.assertEqual(status["height"], n + 1)
        self.host.close()
        self.hosts.remove(self.host)
        fresh = self.spawn()
        t1 = time.time()
        opened = fresh.send(op="world-open", path=self.path)
        replay = time.time() - t1
        self.assertEqual(opened["status"], "opened")
        self.assertEqual(opened["head"], status["head"])
        self.assertEqual(self.view(host=fresh)["state"], seed(n))
        print(f"\n  1000 proposals {build:.2f}s, replay {replay:.2f}s")
        self.assertLess(build + replay, 10.0)
        self.assertLess(replay, 10.0)

    def test_oversized_identity_and_object_id_are_refused_before_the_journal(self):
        self.create()
        r = self.propose("x" * 257, [root("c1", 0)], [])
        self.assertEqual(r["status"], "error")
        r = self.propose("ok", [root("o" * 129, 0)], [])
        self.assertEqual(r["status"], "error")
        self.assertEqual(self.host.send(op="world-status")["height"], 1)

    def test_too_many_roots_are_refused_before_the_journal(self):
        self.create()
        r = self.propose("many", [root(f"o{i}", 0) for i in range(65)], [])
        self.assertEqual(r["status"], "error")

    def test_state_beyond_the_byte_capacity_is_capacity_not_a_type_mismatch(self):
        self.create()
        big = {"tag": "label", "value": "x" * 300000}
        r = self.propose("big", [root("c1", 0)], [write("c1", put("name", big))])
        self.assertEqual(r["receipt"]["outcome"]["class"], "capacity")


if __name__ == "__main__":
    unittest.main()
