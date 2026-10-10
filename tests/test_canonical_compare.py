"""`canonicalCompare(a, b)`: two values of one first-order type ordered by their canonical
DAG-CBOR bytes (0 less, 1 equal, 2 greater), written out from the type as Bend, so a
relation can be sorted and merged inside a turn in the host's own order. Refuted by any pair
of a hundred random records whose Bend order differs from the order of their bytes as the
host encodes them (`canonical-encode`).

    python3 -m unittest tests.test_canonical_compare -v
"""
import random
import unittest

from tests.test_turn import Host, library_modules

SOURCE = """edition ObjectiveBend 1
import ./List.obend as Lists
sum Shade:
  dark: {}
  light: {level: Nat}
  dim: {by: String}
record Row:
  name: String
  n: Nat
  ok: Bool
  tags: Lists.List<String>
  shade: Shade
  inner: {a: Nat, bb: String}
def order(a: Row, b: Row) -> Nat:
  canonicalCompare(a, b)
def numbers(a: Lists.List<Nat>, b: Lists.List<Nat>) -> Nat:
  canonicalCompare(a, b)
"""

TEXTS = ["", "a", "b", "ab", "ba", "é", "zz", "日本", "😀", "aaa", "Z", "a b"]


def lab(s):
    return {"tag": "label", "value": s}


def nat(n):
    return {"tag": "natural", "value": str(n)}


def rec(**fields):
    return {"tag": "record", "fields": [{"name": k, "value": v} for k, v in fields.items()]}


def row(r):
    shade = r.choice([{"tag": "variant", "label": "dark", "payload": rec()},
                      {"tag": "variant", "label": "light", "payload": rec(level=nat(r.choice([0, 1, 300])))},
                      {"tag": "variant", "label": "dim", "payload": rec(by=lab(r.choice(TEXTS)))}])
    return rec(name=lab(r.choice(TEXTS)), n=nat(r.choice([0, 1, 23, 24, 255, 256, 70000, 2 ** 64 - 1, 2 ** 64, 2 ** 70])),
               ok={"tag": "boolean", "value": r.random() < 0.5},
               tags={"tag": "list", "items": [lab(r.choice(TEXTS)) for _ in range(r.randrange(0, 4))]},
               shade=shade, inner=rec(a=nat(r.choice([1, 2])), bb=lab(r.choice(TEXTS))))


class CanonicalCompare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()
        cls.modules = library_modules("List") + [{"name": "Package", "source": SOURCE}]

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def compiled(self, entry):
        reply = self.h.send({"op": "compile", "entry": entry, "modules": self.modules})
        self.assertEqual(reply["status"], "compiled", reply)
        return reply["artifact"]

    def bytes_of(self, value):
        return bytes.fromhex(self.h.send({"op": "canonical-encode", "data": value})["hex"])

    def bend(self, art, a, b):
        reply = self.h.send({"op": "run-data-v1", "artifact": art, "arguments": [a, b]})
        self.assertEqual(reply["status"], "finished", reply)
        return int(reply["value"]["value"])

    def expected(self, a, b):
        x, y = self.bytes_of(a), self.bytes_of(b)
        return 0 if x < y else 1 if x == y else 2

    def test_a_hundred_random_records_order_as_their_canonical_bytes(self):
        art = self.compiled("order")
        r = random.Random(1010)
        rows = [row(r) for _ in range(100)]
        pairs = [(rows[i], rows[(i * 7 + 3) % 100]) for i in range(100)] + [(rows[5], rows[5])]
        for a, b in pairs:
            self.assertEqual(self.bend(art, a, b), self.expected(a, b), (a, b))

    def test_lists_order_by_length_first(self):
        art = self.compiled("numbers")
        short = {"tag": "list", "items": [nat(9)]}
        long = {"tag": "list", "items": [nat(1), nat(2)]}
        self.assertEqual(self.bend(art, short, long), 0)
        self.assertEqual(self.expected(short, long), 0)

    def test_data_values_are_refused_by_name(self):
        source = "edition ObjectiveBend 1\ndef order(a: Data, b: Data) -> Nat:\n  canonicalCompare(a, b)\n"
        reply = self.h.send({"op": "check-package", "entry": "order", "modules": [{"name": "Package", "source": source}]})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (canonical-compare): a Data value", reply["diagnostic"]["message"])


if __name__ == "__main__":
    unittest.main()
