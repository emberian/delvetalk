"""Subscriptions and `changed` (WHOLENESS §3, host day 3): `world.subscribe({object, field})` records a
standing subscription of the running object under the frame's principal, who must be permitted to view
the object; after every admitted write that touches the field the subscriber is sent `changed {object,
field, version, inserted, retracted}`, journaled as `changes` beside `sends` and re-derived on replay;
at most 64 subscribers to an object; sends and changes together at most 32 per write, the rest named in
`unserved`; `unsubscribe` ends one.

Evidence for HOST-HANDOFF 5.50 (layer: host). Refuted by a write of a watched field that tells no
subscriber, a write of another field that does, a subscription that does not survive reopen, a
65th subscriber admitted, or changes past the per-write bound delivered.

    python3 -W error -m unittest tests.test_changes -v
"""
import json
import tempfile
import unittest

from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record
from tests.test_world_object import extended_library

EXTRA = ("  subscribe({object: Plans.Reference, field: String}) -> Subscribed\n"
         "  unsubscribe({object: Plans.Reference, field: String}) -> Subscribed\n"
         "sum Subscribed:\n  subscribed: {}\n  denied: {}\n  refused: {clause: String}\n")

BELL = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  rung: Nat
  names: Lists.List<String>
record Edits:
  rung: Plans.Edit<Nat, Nat>
  names: Plans.Entries<String, String>
def initial() -> State:
  {rung: 0n, names: Lists.List::<String>.nil({})}
def keep() -> Edits:
  {rung: Plans.Edit.keep({}), names: Plans.Entries.keep({})}
def ring(state: State, input: {}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {rung: add 1n}
  state.rung + 1n
def name(state: State, input: {who: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write::<Edits>({rung: Plans.Edit.keep({}), names: Plans.Entries.append({item: input.who})})
  0n
"""

WATCHER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  seen: Nat
  last: Nat
record Edits:
  seen: Plans.Edit<Nat, Nat>
  last: Plans.Edit<Nat, Nat>
def initial() -> State:
  {seen: 0n, last: 0n}
def watch(state: State, input: {target: String, field: String}, context: Abi.Context) -> Activity<String>:
  match world.subscribe({object: {world: "", object: input.target}, field: input.field}):
    case subscribed(_): "subscribed"
    case denied(_): "denied"
    case refused(r): r.clause
def unwatch(state: State, input: {target: String, field: String}, context: Abi.Context) -> Activity<String>:
  match world.unsubscribe({object: {world: "", object: input.target}, field: input.field}):
    case subscribed(_): "unsubscribed"
    case denied(_): "denied"
    case refused(r): r.clause
def changed(state: State, input: {object: Plans.Reference, field: String, version: Nat, inserted: Data, retracted: Data}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write::<Edits>({seen: Plans.Edit.add({delta: 1n}), last: Plans.Edit.set({value: input.version})})
  state.seen + 1n
"""


class Changes(Reflection):
    def setUp(self):
        super().setUp()
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.open_library(library=extended_library(scratch.name, EXTRA))
        self.make2("bell", BELL)

    def make2(self, name, source, **extra):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                           modules=[{"name": "Main", "source": source}],
                           entry="initial", seed=record(), **extra)
        self.assertEqual(r["status"], "created", r)

    def get(self, name, field):
        return {f["name"]: f["value"] for f in self.state(name)["fields"]}[field]

    def watch(self, watcher, target="bell", field="rung", principal="ann", method="watch"):
        return self.turn(watcher, method, record(target=label(target), field=label(field)), principal=principal)["result"]

    def entries(self):
        with open(self.path) as f:
            return [json.loads(line) for line in f.read().splitlines()]

    def test_a_watched_field_tells_its_subscriber_and_another_field_does_not(self):
        self.make2("w", WATCHER)
        self.assertEqual(self.watch("w"), label("subscribed"))
        self.assertEqual(self.watch("w"), label("subscribed"))  # once per (subscriber, object, field)
        rung = self.turn("bell", "ring", record())
        self.assertEqual(rung["status"], "admitted", rung)
        self.assertEqual([d["status"] for d in rung.get("delivered", [])], ["admitted"], rung)
        self.assertEqual((self.get("w", "seen"), self.get("w", "last")), (nat(1), nat(1)))
        entry = [e for e in self.entries() if e["identity"]["intent"] == rung["receipt"]["identity"]["intent"]][0]
        [change] = entry["changes"]
        self.assertEqual((change["to"], change["object"], change["field"], change["version"], change["principal"]),
                         ("w", "bell", "rung", 1, "ann"))
        argument = {f["name"]: f["value"] for f in change["argument"]["fields"]}
        self.assertEqual((argument["inserted"], argument["retracted"]),
                         ({"tag": "list", "items": [nat(1)]}, {"tag": "list", "items": [nat(0)]}))
        self.turn("bell", "name", record(who=label("kim")))
        self.assertEqual(self.get("w", "seen"), nat(1))
        # The subscription is derived from the journal: it stands after reopen, and the replayed
        # entries re-derive the changes they journaled.
        self.reopen()
        self.turn("bell", "ring", record())
        self.assertEqual((self.get("w", "seen"), self.get("w", "last")), (nat(2), nat(3)))

    def test_a_list_field_reports_items_added(self):
        self.make2("w", WATCHER)
        self.watch("w", field="names")
        named = self.turn("bell", "name", record(who=label("kim")))
        entry = [e for e in self.entries() if e["identity"]["intent"] == named["receipt"]["identity"]["intent"]][0]
        argument = {f["name"]: f["value"] for f in entry["changes"][0]["argument"]["fields"]}
        self.assertEqual((argument["inserted"], argument["retracted"]),
                         ({"tag": "list", "items": [label("kim")]}, {"tag": "list", "items": []}))

    def test_unsubscribe_ends_it(self):
        self.make2("w", WATCHER)
        self.watch("w")
        self.turn("bell", "ring", record())
        self.assertEqual(self.watch("w", method="unwatch"), label("unsubscribed"))
        self.turn("bell", "ring", record())
        self.assertEqual(self.get("w", "seen"), nat(1))
        self.reopen()
        self.turn("bell", "ring", record())
        self.assertEqual(self.get("w", "seen"), nat(1))

    def test_refusals_by_name(self):
        self.make2("w", WATCHER)
        self.assertEqual(self.watch("w", field="nope"), label("field"))
        self.make2("vault", BELL, read={"principals": ["ember"]})
        self.assertEqual(self.watch("w", target="vault"), label("denied"))
        self.assertEqual(self.watch("w", target="vault", principal="ember"), label("subscribed"))

    def test_64_subscribers_and_32_changes_a_write(self):
        for i in range(65):
            self.make2(f"w{i}", WATCHER)
        for i in range(64):
            self.assertEqual(self.watch(f"w{i}"), label("subscribed"), i)
        self.assertEqual(self.watch("w64"), label("subscribers"))
        rung = self.turn("bell", "ring", record())
        entry = [e for e in self.entries() if e["identity"]["intent"] == rung["receipt"]["identity"]["intent"]][0]
        self.assertEqual((len(entry["changes"]), len(entry["unserved"])), (32, 32))
        self.assertEqual(entry["unserved"][0], "w32")


if __name__ == "__main__":
    unittest.main()
