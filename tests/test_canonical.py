"""Canonical DAG-CBOR for Data and journal entries, and CID identity.

The decisive test is the first: records the AT Protocol AppView returned, with the CID it
gave each, encode through our encoder to exactly that CID.

    python3 -m unittest tests.test_canonical -v
"""
import json
import os
import tempfile
import time
import unittest

import subprocess

from tests.host import binary
from tests.test_turn_world import closure, label, nat, record
from tests.wire import cid_of

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "delve")


def records_with_cids(node, out):
    if isinstance(node, dict):
        if isinstance(node.get("record"), dict) and isinstance(node.get("cid"), str):
            out.append((node["record"], node["cid"]))
        for v in node.values():
            records_with_cids(v, out)
    elif isinstance(node, list):
        for v in node:
            records_with_cids(v, out)
    return out


class Host:
    """A host process whose replies are read raw: lists arrive as arrays."""

    def __init__(self):
        self.proc = subprocess.Popen([binary()], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1)

    def send(self, **request):
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=60)
        self.proc.stdout.close()


def list_wire(items):
    return {"tag": "list", "items": items}


def nil():
    return {"tag": "list", "items": []}


def chain_nil():
    return {"tag": "variant", "label": "nil", "payload": record()}


def chain_cons(head, tail):
    return {"tag": "variant", "label": "cons", "payload": record(head=head, tail=tail)}


def boolean(b):
    return {"tag": "boolean", "value": b}


class Canonical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = Host()
        cls.addClassCleanup(cls.host.close)

    def encode(self, **kw):
        return self.host.send(op="canonical-encode", **kw)

    def test_atproto_post_records_encode_to_the_cid_the_appview_returned(self):
        found = []
        for name in sorted(os.listdir(FIXTURES)):
            with open(os.path.join(FIXTURES, name)) as handle:
                records_with_cids(json.load(handle), found)
        self.assertGreater(len(found), 100)
        mismatched = []
        for rec, expected in found:
            got = self.encode(json=rec)
            if got.get("cid") != expected:
                mismatched.append((expected, got))
        print("AT Protocol fixture records matching their CID: %d/%d" % (len(found) - len(mismatched), len(found)))
        self.assertEqual(mismatched[:2], [])
        self.assertEqual(cid_of(found[0][0]), found[0][1])  # the independent encoder agrees

    def test_field_order_does_not_change_the_cid(self):
        a = record(x=nat(1), y=label("é"), z=boolean(True))
        b = record(z=boolean(True), x=nat(1), y=label("é"))
        c = record(y=label("é"), z=boolean(True), x=nat(1))
        cids = {self.encode(data=d)["cid"] for d in (a, b, c)}
        self.assertEqual(len(cids), 1)
        other = record(x=nat(2), y=label("é"), z=boolean(True))
        self.assertNotIn(self.encode(data=other)["cid"], cids)
        # the sort is by length first: "b" < "aa" although "aa" < "b" bytewise
        self.assertEqual(self.encode(data=record(aa=nat(1), b=nat(2)))["hex"],
                         "a2" "6162" "02" "626161" "01")

    def test_every_data_shape_has_the_expected_bytes_and_round_trips(self):
        cases = {
            "zero": (nat(0), "00"), "small": (nat(23), "17"), "one byte": (nat(24), "1818"),
            "two bytes": (nat(256), "190100"), "u64 max": (nat(2 ** 64 - 1), "1b" + "ff" * 8),
            "2^64 is a byte string": (nat(2 ** 64), "49" + "010000000000000000"),
            "false": (boolean(False), "f4"), "true": (boolean(True), "f5"),
            "empty label": (label(""), "60"), "unicode label": (label("é"), "62c3a9"),
            "empty record": (record(), "a0"), "record": (record(a=nat(1)), "a1" "6161" "01"),
            "empty list": (nil(), "80"), "list": (list_wire([nat(1), nat(2)]), "82" "01" "02"),
            "variant": ({"tag": "variant", "label": "ok", "payload": record()}, "a1" "626f6b" "a0"),
        }
        for name, (data, expected) in cases.items():
            with self.subTest(shape=name):
                got = self.encode(data=data)
                self.assertEqual(got["hex"], expected)
                back = self.host.send(op="canonical-decode", hex=got["hex"])
                self.assertEqual(back["status"], "decoded", back)
                # decoding and encoding again is the identity on bytes
                self.assertEqual(self.encode(data=back["data"])["hex"], expected)
        big = nat(2 ** 200 + 12345)
        self.assertEqual(self.host.send(op="canonical-decode", hex=self.encode(data=big)["hex"])["data"], big)
        nested = record(l=list_wire([record(a=list_wire([nat(1)])), list_wire([])]), s=label("x" * 300))
        hexed = self.encode(data=nested)["hex"]
        again = self.host.send(op="canonical-decode", hex=hexed)["data"]
        self.assertEqual(self.encode(data=again)["hex"], hexed)

    def test_a_decoded_one_key_map_is_a_record_and_a_list_stays_a_list(self):
        back = self.host.send(op="canonical-decode", hex="a1626f6ba0")
        self.assertEqual(back["data"], record(ok=record()))
        back = self.host.send(op="canonical-decode", hex="83010203")
        self.assertEqual(back["data"], list_wire([nat(1), nat(2), nat(3)]))

    def test_noncanonical_and_foreign_cbor_is_refused_by_name(self):
        refused = {
            "1800": "shortest form", "1900ff": "shortest form", "a2616201616101": "sorted",
            "a2616101616102": "sorted", "5f": "definite", "f90000": "Data model", "f6": "Data model",
            "c001": "Data model", "20": "Data model", "4101": "big natural", "01ff": "trailing",
            "62c328": "UTF-8", "8200": "truncated", "a1": "truncated", "a10101": "key is not text",
        }
        for hexed, why in refused.items():
            with self.subTest(bytes=hexed):
                r = self.host.send(op="canonical-decode", hex=hexed)
                self.assertEqual(r["status"], "error", r)
                self.assertIn(why.lower(), r["message"].lower())
        deep = "81" * 300 + "00"
        r = self.host.send(op="canonical-decode", hex=deep)
        self.assertIn("nesting", r["message"])

    def test_lists_cross_the_wire_as_arrays_and_a_nil_cons_chain_is_refused_by_name(self):
        b = self.encode(data=list_wire([nat(i) for i in range(5)]))
        back = self.host.send(op="canonical-decode", hex=b["hex"])["data"]
        self.assertEqual(back["tag"], "list")
        self.assertEqual(len(back["items"]), 5)
        chain = chain_nil()
        for i in reversed(range(5)):
            chain = chain_cons(nat(i), chain)
        refused = self.host.send(op="canonical-encode", data=chain)
        self.assertEqual((refused["status"], refused["message"]),
                         ("error", "cons chains are no longer accepted on the wire; send a list"), refused)
        tail_list = chain_cons(nat(0), list_wire([nat(1)]))          # a cons onto an array is a chain too
        self.assertEqual(self.host.send(op="canonical-encode", data=tail_list)["status"], "error")
        improper = chain_cons(nat(0), nat(1))                          # not a list: still an ordinary variant
        self.assertNotEqual(self.host.send(op="canonical-encode", data=improper).get("status"), "error")

    def test_a_long_list_is_bounded_by_element_nesting_not_by_length(self):
        items = [nat(i) for i in range(5000)]
        got = self.encode(data=list_wire(items))
        self.assertEqual(got["status"], "encoded", got)
        back = self.host.send(op="canonical-decode", hex=got["hex"])
        self.assertEqual(len(back["data"]["items"]), 5000)
        # nesting is what is bounded: 300 levels of one-element arrays is refused, 200 is not
        def nest(levels):
            d = nat(1)
            for _ in range(levels):
                d = list_wire([d])
            return d
        self.assertEqual(self.encode(data=nest(200))["status"], "encoded")
        r = self.host.send(op="canonical-decode", hex=self.encode(data=nest(200))["hex"])
        self.assertEqual(r["status"], "decoded", r)
        r = self.host.send(op="canonical-decode", hex=self.encode(data=nest(300))["hex"])
        self.assertEqual(r["status"], "error", r)

    def test_smoke_bound_encoding_a_1000_element_list_takes_under_20_ms(self):
        """The kernel's one wall-clock smoke bound, generous: measured 0.4 ms on hbox."""
        data = list_wire([record(n=nat(i), s=label("item %d" % i)) for i in range(1000)])
        def timed(repeat):
            best = None
            for _ in range(3):
                started = time.perf_counter()
                self.assertEqual(self.encode(data=data, repeat=repeat)["status"], "encoded")
                elapsed = time.perf_counter() - started
                best = elapsed if best is None else min(best, elapsed)
            return best
        base, many = timed(1), timed(401)
        per = (many - base) / 400
        print("canonical encode of a 1,000-element list: %.3f ms each" % (per * 1000))
        self.assertLess(per, 0.020)


class JournalCids(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "world.journal")
        self.hosts = []

    def spawn(self):
        h = Host()
        self.hosts.append(h)
        self.addCleanup(h.close)
        return h

    def entries(self):
        with open(self.path) as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def populate(self, host):
        self.assertEqual(host.send(op="world-open", path=self.path, sync="none")["status"], "opened")
        made = host.send(op="world-create", principal="ember", identity="mk", object="counter",
                         modules=closure("Counter"), entry="initial", seed=record(count=nat(5)))
        self.assertEqual(made["status"], "created", made)
        for n in range(3):
            turn = host.send(op="world-turn", principal="glm", object="counter", method="bump",
                             argument=record(), identity="b%d" % n)
            self.assertEqual(turn["status"], "admitted", turn)

    def test_entries_are_identified_by_the_cid_of_their_canonical_bytes_and_chain_by_cid(self):
        host = self.spawn()
        self.populate(host)
        entries = self.entries()
        self.assertEqual(len(entries), 4)
        previous = "0" * 64
        for entry in entries:
            body = {k: v for k, v in entry.items() if k != "hash"}
            self.assertEqual(entry["hash"], cid_of(body))   # independent encoder
            self.assertTrue(entry["hash"].startswith("bafyrei"), entry["hash"])
            self.assertEqual(entry["previous"], previous)
            previous = entry["hash"]
        status = host.send(op="world-status")
        self.assertEqual(status["head"], previous)

    def test_a_tampered_byte_breaks_the_chain_at_the_named_height(self):
        host = self.spawn()
        self.populate(host)
        host.close()
        with open(self.path) as handle:
            lines = handle.read().split("\n")
        entry = json.loads(lines[2])  # height 3
        self.assertEqual(entry["height"], 3)
        lines[2] = lines[2].replace('"glm"', '"gly"', 1)
        self.assertNotEqual(lines[2], json.dumps(entry))
        with open(self.path, "w") as handle:
            handle.write("\n".join(lines))
        broken = self.spawn().send(op="world-open", path=self.path)
        self.assertEqual(broken["status"], "error", broken)
        self.assertIn("journal broken at height 3", broken["message"])
        self.assertIn("hash mismatch", broken["message"])

    def test_a_replaced_entry_with_a_valid_hash_breaks_the_next_link(self):
        host = self.spawn()
        self.populate(host)
        host.close()
        with open(self.path) as handle:
            lines = handle.read().split("\n")
        entry = json.loads(lines[1])  # height 2: rewrite, resealed with a correct CID
        entry["ticksUsed"] = entry.get("ticksUsed", 0) + 1
        body = {k: v for k, v in entry.items() if k != "hash"}
        entry["hash"] = cid_of(body)
        lines[1] = json.dumps(entry)
        with open(self.path, "w") as handle:
            handle.write("\n".join(lines))
        broken = self.spawn().send(op="world-open", path=self.path)
        self.assertEqual(broken["status"], "error", broken)
        self.assertIn("journal broken at height 3", broken["message"])
        self.assertIn("does not chain", broken["message"])


if __name__ == "__main__":
    unittest.main()
