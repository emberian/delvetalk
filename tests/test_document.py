"""Host-side Document projection: render-document, and the `offer` Plan.

`render` must equal Bend's Document.plain byte for byte and `lines` Document.lines.
Run from the repository root:  python3 -m unittest tests.test_document -v
"""
import json
import os
import random
import tempfile
import time
import unittest

from tests.test_chain import garden_state

from tests import host
from tests.host import HostCase
from tests.test_turn_world import closure, label, nat, record

ALPHABET = ["a", "b", " ", "\n", "é", "日本", "😀", "\\", '"', "x y", "\n\n", "tab\t", ""]


def variant(name, **fields):
    return {"tag": "variant", "label": name, "payload": record(**fields)}


def nil():
    return {"tag": "variant", "label": "nil", "payload": record()}


def cons(head, tail):
    return {"tag": "variant", "label": "cons", "payload": record(head=head, tail=tail)}


def as_list(items):
    out = nil()
    for item in reversed(items):
        out = cons(item, out)
    return out


# A document as a small Python tree; to_wire and to_bend are its two renderings.
def gen(rng, depth):
    kinds = ["text", "text", "reference", "offer", "fields", "source", "continuation"]
    if depth > 0:
        kinds += ["sequence", "sequence", "quote", "result"]
    kind = rng.choice(kinds)
    s = lambda: "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 4)))
    if kind == "sequence":
        return (kind, [gen(rng, depth - 1) for _ in range(rng.randint(0, 4))])
    if kind in ("quote", "result"):
        return (kind, s(), gen(rng, depth - 1))
    if kind == "reference":
        return (kind, s(), s(), s(), s())
    if kind == "offer":
        return (kind, s(), s(), rng.randint(0, 9), s(), s(), s())
    if kind == "fields":
        return (kind, [s() for _ in range(rng.randint(0, 2))])
    if kind == "source":
        return (kind, s(), s(), s())
    if kind == "continuation":
        return (kind, s(), rng.randint(0, 9), rng.randint(0, 9), s())
    return (kind, s())


def capture(o, r, m, e, t):
    return record(object=label(o), revision=nat(r), meaning=label(m), entry=label(e), token=label(t))


def to_wire(d):
    k = d[0]
    if k == "text":
        return variant("text", value=label(d[1]))
    if k == "sequence":
        return variant("sequence", items=as_list([to_wire(c) for c in d[1]]))
    if k == "quote":
        return variant("quote", attribution=label(d[1]), body=to_wire(d[2]))
    if k == "result":
        return variant("result", status=label(d[1]), body=to_wire(d[2]))
    if k == "reference":
        return variant("reference", key=label(d[1]), label=label(d[2]), object=label(d[3]), panel=label(d[4]))
    if k == "offer":
        return variant("offer", label=label(d[1]), capture=capture(*d[2:3], d[3], *d[4:]))
    if k == "fields":
        return variant("fields", capture=capture("", 0, "", "", ""), needs=as_list([label(x) for x in d[1]]))
    if k == "source":
        return variant("source", language=label(d[1]), code=label(d[2]), revision=label(d[3]))
    return variant("continuation", key=label(d[1]), after=nat(d[2]), limit=nat(d[3]), label=label(d[4]))


def lit(s):
    return json.dumps(s)


def to_bend(d):
    k = d[0]
    D = "Document.Document"
    if k == "text":
        return f"{D}.text({{value: {lit(d[1])}}})"
    if k == "sequence":
        items = "Document.Documents.nil()"
        for c in reversed(d[1]):
            items = f"Document.Documents.cons({{head: {to_bend(c)}, tail: {items}}})"
        return f"{D}.sequence({{items: {items}}})"
    if k == "quote":
        return f"{D}.quote({{attribution: {lit(d[1])}, body: {to_bend(d[2])}}})"
    if k == "result":
        return f"{D}.result({{status: {lit(d[1])}, body: {to_bend(d[2])}}})"
    if k == "reference":
        return f"{D}.reference({{key: {lit(d[1])}, label: {lit(d[2])}, object: {lit(d[3])}, panel: {lit(d[4])}}})"
    if k == "offer":
        return (f"{D}.offer({{label: {lit(d[1])}, capture: {{object: {lit(d[2])}, revision: {d[3]}n, "
                f"meaning: {lit(d[4])}, entry: {lit(d[5])}, token: {lit(d[6])}}}}})")
    if k == "fields":
        needs = "Document.Names.nil()"
        for x in reversed(d[1]):
            needs = f"Document.Names.cons({{head: {lit(x)}, tail: {needs}}})"
        return (f"{D}.fields({{capture: {{object: \"\", revision: 0n, meaning: \"\", entry: \"\", token: \"\"}}, "
                f"needs: {needs}}})")
    if k == "source":
        return f"{D}.source({{language: {lit(d[1])}, code: {lit(d[2])}, revision: {lit(d[3])}}})"
    return f"{D}.continuation({{key: {lit(d[1])}, after: {d[2]}n, limit: {d[3]}n, label: {lit(d[4])}}})"


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
        docs[1] = ("sequence", [("sequence", [("quote", "né\nw", ("sequence", [("text", "")]))]), ("text", "end\n")])
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

    def test_a_1025_rain_card_renders_in_the_host_under_50_ms(self):
        header = "A silver bell planted by glm: a bell for lost moths (silent)\n"
        line = "author: a line of rain\n"
        rains = [variant("text", value=label(line)) for _ in range(1025)]
        doc = variant("sequence", items=as_list([variant("text", value=label(header))] + rains))
        self.s.render(doc)  # warm the process
        best = None
        for _ in range(5):
            started = time.perf_counter()
            got = self.s.render(doc)
            elapsed = time.perf_counter() - started
            best = elapsed if best is None else min(best, elapsed)
        self.assertEqual(got["text"], header + line * 1025)
        self.assertEqual(len(got["lines"]), 1026)
        # a request of the same size that renders nothing isolates the host's JSON framing
        empty = variant("sequence", items=as_list([variant("fields", capture=capture("", 0, "", "", ""),
                                                           needs=nil()) for _ in range(1026)]))
        started = time.perf_counter()
        self.s.render(empty)
        framing = time.perf_counter() - started
        print("1025-rain card: render-document round trip %.1f ms (same-size request with no text: %.1f ms)"
              % (best * 1000, framing * 1000))
        self.assertLess(best, 0.050)

    def test_depth_65_is_refused_by_name_and_depth_64_renders(self):
        def nested(levels):
            d = variant("text", value=label("leaf"))
            for _ in range(levels - 1):
                d = variant("quote", attribution=label("q"), body=d)
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
        for bad in (nat(1), variant("nonsense"), variant("text", value=nat(1)), variant("quote", attribution=label("a"))):
            r = self.s.render(bad)
            self.assertEqual(r["status"], "error", r)
            self.assertIn("malformed document", r["message"])


class OfferTests(HostCase):
    def test_an_offer_turn_on_garden_returns_the_card_and_journals_only_the_count(self):
        made = self.host.send(op="world-create", principal="ember", identity="mk", object="garden",
                              modules=closure("Garden"), entry="initial", seed=garden_state(2))
        self.assertEqual(made["status"], "created", made)
        look = record(text=label(""), post=label("at://glm/p/look"))
        turn = self.host.send(op="world-turn", principal="glm", object="garden", method="receive",
                              argument=look, identity="look-1")
        self.assertEqual(turn["status"], "admitted", turn)
        self.assertEqual(len(turn["offers"]), 1)
        self.assertEqual(turn["offers"][0]["principal"], "glm")
        self.assertIn("2 planted, newest first:\n", turn["offers"][0]["text"])
        self.assertEqual(turn["receipt"]["offers"], 1)
        self.assertNotIn("2 planted", json.dumps(turn["receipt"]))
        # the journal file holds the count and no text
        with open(self.path) as handle:
            raw = handle.read()
        self.assertNotIn("2 planted", raw)
        # restart: replay reproduces the same offers count on the same receipt
        self.reopen()
        again = self.host.send(op="world-receipt", principal="glm", identity="look-1")
        self.assertEqual(again["status"], "receipt", again)
        self.assertEqual(again["receipt"]["offers"], 1)
        self.assertEqual(again["receipt"]["outcome"]["tag"], "admitted")
        # a retry of the same identity returns the same receipt
        retry = self.host.send(op="world-turn", principal="glm", object="garden", method="receive",
                               argument=look, identity="look-1")
        self.assertEqual(retry["receipt"], again["receipt"])

    def test_a_turn_without_an_offer_carries_no_offers_field(self):
        self.host.send(op="world-create", principal="ember", identity="mk", object="garden",
                       modules=closure("Garden"), entry="initial", seed=garden_state(0))
        turn = self.host.send(op="world-turn", principal="glm", object="garden", method="cistern",
                              argument=record(), identity="c1")
        self.assertNotIn("offers", turn)
        self.assertNotIn("offers", turn.get("receipt", {}))


if __name__ == "__main__":
    unittest.main()
