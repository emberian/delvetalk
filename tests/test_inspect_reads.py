"""Hypermedia reads (docs/AGENTS-API.md "Host ops wanted"): `world-inspect` lists per turnable method
`admits: true | {clause, reading?}`, the text law's verdict on a kind-0 change by the asking principal
through that method on the unchanged state, `true` where the refusing clause reads the state (the
commit decides), and omits the module text under `source: false`; `world-objects {methods: true}` names each listed object's turnable methods.

Evidence for HOST-HANDOFF 5.55 to 5.57 (layer: host). Refuted by a method the law refuses its caller
listed `true` on a request-only clause, a permitted method listed refused, a clause that reads the state
answered as a refusal, `source: false` answering the source, or a listing whose methods name an object the reader may not view or a method a
turn cannot run.

    python3 -W error -m unittest tests.test_inspect_reads -v
"""
import unittest

from tests.test_reflection import PROBE, Reflection
from tests.test_turn_world import nat, record, label

LAWS = ('law owner "only ember bumps by two": request.method == "bump2" implies request.subject == "ember"\n'
        'law quiet: request.method == "fire" implies request.subject == "nobody"\n'
        'law cap: request.method == "bump" implies new.count <= 2\n')


class Admits(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("probe", PROBE + LAWS, record(count=nat(3), seen=label("")))

    def admits(self, principal):
        r = self.host.send(op="world-inspect", principal=principal, object="probe")
        self.assertEqual(r["status"], "inspected", r)
        return {m["name"]: m.get("admits") for m in r["methods"]}

    def test_each_turnable_method_carries_the_laws_verdict_for_the_reader(self):
        kim = self.admits("kim")
        self.assertEqual(kim["bump2"], {"clause": "owner", "reading": "only ember bumps by two"})
        self.assertEqual(kim["fire"], {"clause": "quiet"})
        self.assertIs(kim["ask"], True)
        # `cap` reads the state: the current count refuses it, but the change decides.
        self.assertIs(kim["bump"], True)
        ember = self.admits("ember")
        self.assertIs(ember["bump2"], True)
        self.assertEqual(ember["fire"], {"clause": "quiet"})
        # Every turnable method carries a verdict, and nothing else does.
        methods = self.host.send(op="world-inspect", principal="kim", object="probe")["methods"]
        self.assertEqual([m["name"] for m in methods if "admits" in m], [m["name"] for m in methods if m["context"]])
        # The verdict is the commit's for the request-only clauses.
        refused = self.turn("probe", "bump2", record(n=nat(1)), principal="kim")
        self.assertEqual((refused["receipt"]["outcome"]["class"], refused["receipt"]["outcome"]["clause"]), ("lawRefused", "owner"))


    def test_source_false_leaves_the_source_out(self):
        whole = self.host.send(op="world-inspect", principal="kim", object="probe")
        bare = self.host.send(op="world-inspect", principal="kim", object="probe", source=False)
        self.assertIn("def bump2", whole["source"])
        self.assertNotIn("source", bare)
        self.assertEqual({k: v for k, v in whole.items() if k != "source"}, bare)
        self.assertEqual(self.host.send(op="world-inspect", principal="kim", object="probe", source=0)["status"], "error")


class Listed(Reflection):
    def test_methods_true_names_each_listed_objects_turnable_methods(self):
        self.open_library()
        self.make("probe", PROBE, record(count=nat(0), seen=label("")))
        self.make("vault", PROBE, record(count=nat(0), seen=label("")), read={"principals": ["ember"]})
        plain = self.host.send(op="world-objects", principal="kim")
        self.assertNotIn("methods", plain)
        r = self.host.send(op="world-objects", principal="kim", methods=True)
        self.assertEqual(r["ids"], ["probe"], r)
        table = self.host.send(op="world-inspect", principal="kim", object="probe")["methods"]
        self.assertEqual(r["methods"], {"probe": [m["name"] for m in table if m["context"]]})
        self.assertEqual(set(self.host.send(op="world-objects", principal="ember", methods=True)["methods"]), {"probe", "vault"})
        self.assertEqual(self.host.send(op="world-objects", principal="kim", methods="yes")["status"], "error")


if __name__ == "__main__":
    unittest.main()
