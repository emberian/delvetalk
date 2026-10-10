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


    def test_the_source_is_left_out_unless_asked_for(self):
        whole = self.host.send(op="world-inspect", principal="kim", object="probe", source=True)
        bare = self.host.send(op="world-inspect", principal="kim", object="probe")
        self.assertEqual(self.host.send(op="world-inspect", principal="kim", object="probe", source=False), bare)
        self.assertIn("def bump2", whole["source"])
        self.assertNotIn("source", bare)
        self.assertEqual({k: v for k, v in whole.items() if k != "source"}, bare)
        self.assertEqual(self.host.send(op="world-inspect", principal="kim", object="probe", source=0)["status"], "error")

    def test_offered_names_the_actions_the_reader_is_offered(self):
        # `offeredTo`, the per-reader filter usage uses (5.103): ember is offered bump2, kim is not.
        offered = lambda who: self.host.send(op="world-inspect", principal=who, object="probe")["offered"]
        self.assertIn("bump2", offered("ember"))
        self.assertNotIn("bump2", offered("kim"))
        forms = self.host.send(op="world-inspect", principal="kim", object="probe")["forms"]
        self.assertEqual(offered("kim"), [next(x["value"]["value"] for x in f["fields"] if x["name"] == "action") for f in forms["items"]])


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
