"""The host renders a Document byte for byte as Bend's Document.plain does, and an offer turn's card
is retained on its receipt and replayed.

Evidence for FOUNDATION §5 (layer: host).

Host-side Document projection: render-document, and the `offer` Plan.

`render` must equal Bend's Document.plain byte for byte and `lines` Document.lines.
Run from the repository root:  python3 -m unittest tests.test_document -v
"""
import json
import os
import random
import tempfile
import unittest

from tests.test_chain import garden_state

from tests import host
from tests.host import HostCase
from tests.test_turn_world import closure, label, nat, record

ALPHABET = ["a", "b", " ", "\n", "é", "日本", "😀", "\\", '"', "x y", "\n\n", "tab\t", ""]


def variant(name, **fields):
    return {"tag": "variant", "label": name, "payload": record(**fields)}


def nil():
    return {"tag": "list", "items": []}


def cons(head, tail):
    return {"tag": "list", "items": [head] + tail["items"]}


def as_list(items):
    return {"tag": "list", "items": list(items)}


# A document as a small Python tree; to_wire and to_bend are its two renderings.
def gen(rng, depth):
    kind = rng.choice(["text", "text", "sequence", "sequence"] if depth > 0 else ["text"])
    s = lambda: "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 4)))
    if kind == "sequence":
        return (kind, [gen(rng, depth - 1) for _ in range(rng.randint(0, 4))])
    return (kind, s())


def to_wire(d):
    if d[0] == "text":
        return variant("text", value=label(d[1]))
    return variant("sequence", items=as_list([to_wire(c) for c in d[1]]))


def lit(s):
    return json.dumps(s)


def to_bend(d):
    D = "Document.Document"
    if d[0] == "text":
        return f"{D}.text({{value: {lit(d[1])}}})"
    items = "Document.Documents.nil()"
    for c in reversed(d[1]):
        items = f"Document.Documents.cons({{head: {to_bend(c)}, tail: {items}}})"
    return f"{D}.sequence({{items: {items}}})"


class Session:
    host = host.Stateless()

    def close(self):
        pass

    def render(self, document):
        return self.host.send(op="render-document", document=document)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.s = Session()
        self.addCleanup(self.s.close)

    def bend(self, modules, entry):
        reply = self.s.host.send(op="compile", modules=modules, entry=entry)
        self.assertEqual(reply["status"], "compiled", reply)
        run = self.s.host.send(op="run", artifact=reply["artifact"], arguments=[])
        self.assertEqual(run["status"], "finished", run)
        return run["value"]["value"]

    def test_render_equals_bend_plain_and_lines_on_20_generated_documents(self):
        rng = random.Random(1025)
        docs = [("sequence", [])] + [gen(rng, 3) for _ in range(19)]
        docs[1] = ("sequence", [("sequence", [("text", "né\nw"), ("sequence", [("text", "")])]), ("text", "end\n")])
        defs = []
        for i, d in enumerate(docs):
            defs.append(f"def d{i}() -> Document.Document:\n  {to_bend(d)}\n"
                        f"def plain{i}() -> String:\n  Document.plain(d{i}())\n"
                        f"def lines{i}() -> String:\n  Lists.fold::<String, String>(Document.lines(d{i}()), \"\", "
                        f"fn(head: String) -> String -> String: fn(rest: String) -> String: "
                        f"textConcat(head, textConcat(\"\\u0001\", rest)))\n")
        probe = ("edition ObjectiveBend 1\nimport ./List.obend as Lists\nimport ./Document.obend as Document\n"
                 + "".join(defs))
        modules = closure("Document") + [{"name": "Probe", "source": probe}]
        for i, d in enumerate(docs):
            with self.subTest(document=i):
                expected_plain = self.bend(modules, f"plain{i}")
                expected_lines = self.bend(modules, f"lines{i}")
                got = self.s.render(to_wire(d))
                self.assertEqual(got["status"], "rendered", got)
                self.assertEqual(got["text"], expected_plain)
                self.assertEqual(got["bytes"], len(expected_plain.encode()))
                self.assertEqual("".join(x + "\u0001" for x in got["lines"]), expected_lines)

    def test_a_1025_rain_card_renders_whole_in_the_host(self):
        header = "A silver bell planted by glm: a bell for lost moths (silent)\n"
        line = "author: a line of rain\n"
        rains = [variant("text", value=label(line)) for _ in range(1025)]
        doc = variant("sequence", items=as_list([variant("text", value=label(header))] + rains))
        got = self.s.render(doc)
        self.assertEqual(got["text"], header + line * 1025)
        self.assertEqual(len(got["lines"]), 1026)

    def test_depth_65_is_refused_by_name_and_depth_64_renders(self):
        def nested(levels):
            d = variant("text", value=label("leaf"))
            for _ in range(levels - 1):
                d = variant("sequence", items=as_list([d]))
            return d
        ok = self.s.render(nested(64))
        self.assertEqual(ok["status"], "rendered", ok)
        refused = self.s.render(nested(65))
        self.assertEqual(refused["status"], "error", refused)
        self.assertIn("document depth exceeds 64", refused["message"])

    def test_node_and_byte_limits_and_malformed_documents_are_refused_by_name(self):
        import sys
        sys.setrecursionlimit(20000)
        inner = lambda: variant("sequence", items=as_list([variant("text", value=label(""))
                                                       for _ in range(200)]))
        many = variant("sequence", items=as_list([inner() for _ in range(200)]))
        r = self.s.render(many)
        self.assertIn("document exceeds 65536 nodes", r.get("message", ""), str(r)[:200])
        big = variant("sequence", items=as_list([variant("text", value=label("x" * 100000)) for _ in range(11)]))
        r = self.s.render(big)
        self.assertIn("document text exceeds 1048576 bytes", r.get("message", ""), str(r)[:200])
        for bad in (nat(1), variant("nonsense"), variant("text", value=nat(1)), variant("sequence"),
                    variant("quote", attribution=label("a"), body=variant("text", value=label("b")))):
            r = self.s.render(bad)
            self.assertEqual(r["status"], "error", r)
            self.assertIn("malformed document", r["message"])


class OfferTests(HostCase):
    def test_an_offer_turn_on_garden_returns_the_card_and_the_journal_retains_it(self):
        made = self.host.send(op="world-create", principal="ember", identity="mk", object="garden",
                              modules=closure("Garden"), entry="initial", seed=garden_state(2))
        self.assertEqual(made["status"], "created", made)
        look = record(text=label(""), post=label("at://glm/p/look"))
        turn = self.host.send(op="world-turn", principal="glm", object="garden", method="receive",
                              argument=look, identity="look-1")
        self.assertEqual(turn["status"], "admitted", turn)
        self.assertEqual(len(turn["offers"]), 1)
        self.assertEqual(turn["offers"][0]["principal"], "glm")
        text = turn["offers"][0]["text"]
        self.assertIn("2 planted, newest first:\n", text)
        self.assertEqual(turn["receipt"]["offers"], [{"to": "glm", "text": text}])
        # restart: replay reproduces the same offers on the same receipt
        self.reopen()
        again = self.host.send(op="world-receipt", principal="glm", identity="look-1")
        self.assertEqual(again["status"], "receipt", again)
        self.assertEqual(again["receipt"]["offers"], turn["receipt"]["offers"])
        self.assertEqual(again["receipt"]["outcome"]["tag"], "admitted")
        # a retry of the same identity returns the same receipt
        retry = self.host.send(op="world-turn", principal="glm", object="garden", method="receive",
                               argument=look, identity="look-1")
        self.assertEqual(retry["receipt"], again["receipt"])
        self.assertEqual(retry["offers"], turn["offers"])


if __name__ == "__main__":
    unittest.main()
