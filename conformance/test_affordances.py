#!/usr/bin/env python3
"""Root-free cards and exact-observation requests against real Lean fixtures."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


a = module("test_affordances", "scripts/affordances.py")
room = module("affordance_test_room", "scene/room.py")
world = module("affordance_test_world", "scripts/world.py")


def record(fields): return ["record", [[k, v] for k, v in fields.items()]]
def label(value): return ["label", value]


def typed_protocol():
    names = ["message", "count", "open", "color"]
    return {"profile": "delvetalk-local-v1", "name": "A small notice",
            "description": "Leave a bounded notice on the shared table.",
            "initial": {"message": "", "count": 0, "open": False, "color": "blue"},
            "commands": {"write a notice": {"require": [], "set": {k: ["input", k] for k in names},
                "result": ["record", {k: ["input", k] for k in names}], "outbox": []}},
            "affordances": {"write a notice": {"label": "Leave a notice", "fields": {
                "message": {"type": "string", "label": "Your message", "minLength": 1, "maxLength": 80},
                "count": {"type": "nat", "minimum": 1, "maximum": 10},
                "open": {"type": "bool"}, "color": {"type": "enum", "options": ["blue", "amber"]}}}}}


class AffordanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = room.compile_artifact((ROOT / "scene/examples/repair-cafe.scene").read_text())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "world.json"

    def tearDown(self): self.tmp.cleanup()

    def create(self, protocol, object_id="object"):
        response = world.exchange(self.db, {"op": "create", "object": object_id, "principal": "operator",
                    "intent": "create-" + object_id, "protocol": protocol, "law": ["actor"]})
        self.assertEqual(response["kind"], "committed", response)
        return response["data"]["root"]

    def test_room_cards_have_small_ids_without_root_or_hashes(self):
        root = self.create(self.artifact["protocol"])
        view = room.room_view(root, self.artifact, "object")
        card = a.card(view)
        self.assertEqual(card["actions"], [{"id": "a1", "label": "Enter the room", "command": "start",
                                           "available": True, "fields": []}])
        self.assertEqual(set(card), {"format", "title", "prose", "object", "version", "mode", "actions"})
        self.assertNotIn("source", card)
        self.assertNotIn("root", card)
        self.assertNotIn("artifactId", card)
        started = world.exchange(self.db, a.request(view, "a1", "actor", "start"))
        self.assertEqual(started["kind"], "committed", started)
        view = room.room_view(started["data"]["root"], self.artifact, "object")
        card = a.card(view)
        self.assertEqual([x["id"] for x in card["actions"]], ["a1", "a2", "a3"])
        self.assertEqual([x["observedAvailable"] for x in card["actions"]], [True, True, False])
        # A descriptor is not admission. Even the currently false room guard can
        # be sent as an exact-root request; Lean returns the refusal.
        refused = world.exchange(self.db, a.request(view, "a3", "actor", "too-soon"))
        self.assertEqual(refused["kind"], "refused")
        denied = world.exchange(self.db, a.request(view, "a1", "stranger", "wrong-principal"))
        self.assertEqual(denied["data"], "unauthorized")

    def test_projection_uses_existing_factory_and_keeps_fixed_inputs(self):
        protocol = typed_protocol()
        protocol["viewProgram"] = {"profile": "delvetalk-bend-view-v1", "term": ["lam", ["lam", record({
            "title": label("A projected notice"), "prose": label("Choose your words."),
            "actions": record({"a name with spaces": record({"text": label("Write with blue ink"),
                "command": label("write a notice"), "input": record({"color": label("blue")})})})})]]}
        root = self.create(protocol)
        view = room.inspect_object(root, "object")
        self.assertEqual(view["mode"], "projection", view)
        action = a.card(view)["actions"][0]
        self.assertEqual(action["id"], "a1")
        self.assertEqual(action["label"], "Write with blue ink")
        self.assertNotIn("color", [f["name"] for f in action["fields"]])
        fields = {"message": "A shared cup of tea.", "count": 2, "open": True}
        request = a.request(view, "a1", "actor", "projected", fields)
        self.assertEqual(request["input"], {**fields, "color": "blue"})
        self.assertEqual(request["expected"], root)
        self.assertEqual(world.exchange(self.db, request)["kind"], "committed")
        with self.assertRaises(a.AffordanceError): a.request(view, "a1", "actor", "override", {**fields, "color": "amber"})

    def test_raw_annotation_accepts_typed_fields_and_preserves_stale_root(self):
        root = self.create(typed_protocol())
        view = room.inspect_object(root, "object")
        self.assertEqual(view["mode"], "raw")
        card = a.card(view)
        self.assertEqual(card, a.card(copy.deepcopy(view)))
        self.assertEqual(card["actions"][0]["label"], "Leave a notice")
        fields = {"message": "Meet by the moth.", "count": 3, "open": False, "color": "amber"}
        request = a.request(view, "a1", "actor", "first", fields)
        committed = world.exchange(self.db, request)
        self.assertEqual(committed["kind"], "committed", committed)
        self.assertEqual(committed["data"]["root"]["state"], fields)
        fields["message"] = "Changing caller data does not alter the retained request."
        self.assertEqual(request["input"]["message"], "Meet by the moth.")
        stale = a.request(view, "a1", "actor", "second", fields)
        self.assertEqual(stale["expected"], root)
        self.assertEqual(world.exchange(self.db, stale)["data"], "stale read root")
        self.assertEqual(world.exchange(self.db, request), committed)

    def test_unannotated_raw_commands_are_inspect_only(self):
        protocol = typed_protocol()
        del protocol["affordances"]
        root = self.create(protocol)
        view = room.inspect_object(root, "object")
        action = a.card(view)["actions"][0]
        self.assertEqual(action["label"], "write a notice")
        self.assertTrue(action["inspectOnly"])
        self.assertFalse(action["available"])
        with self.assertRaises(a.AffordanceError): a.request(view, "a1", "actor", "not-invented", {})
        with self.assertRaises(a.AffordanceError): a.validate_fields(action, {})

    def test_field_validation_is_strict_and_rejects_overrides(self):
        root = self.create(typed_protocol())
        view = room.inspect_object(root, "object")
        action = a.card(view)["actions"][0]
        valid = {"message": "hello", "count": 1, "open": True, "color": "blue"}
        for key, bad in [("message", ""), ("message", "x" * 81), ("message", 5), ("message", "\ud800"),
                         ("count", True), ("count", -1), ("count", 1.0), ("count", "1"), ("count", 11),
                         ("open", 1), ("open", "true"), ("color", "green"), ("color", False)]:
            with self.subTest(key=key, bad=repr(bad)):
                with self.assertRaises(a.AffordanceError): a.validate_fields(action, {**valid, key: bad})
        for extra in ("principal", "object", "root", "expected", "intent", "command"):
            with self.subTest(extra=extra):
                with self.assertRaises(a.AffordanceError): a.request(view, "a1", "actor", "safe", {**valid, extra: "override"})
        with self.assertRaises(a.AffordanceError): a.validate_fields(action, {"message": "missing the rest"})
        with self.assertRaises(a.AffordanceError): a.validate_fields(action, [])
        with self.assertRaises(a.AffordanceError): a.request(view, "write a notice", "actor", "no-alias", valid)

    def test_schema_validation_precedes_external_interpretation(self):
        field = {"name": "text", "label": "Text", "type": "string", "required": True, "minLength": 0, "maxLength": 5}
        self.assertEqual(a.validate_fields_schema([field]), [field])
        for changed in [{**field, "required": False}, {**field, "unknown": 1}, {**field, "maxLength": 5000},
                        {**field, "minLength": -1}, {**field, "type": "program"}]:
            with self.assertRaises(a.AffordanceError): a.validate_fields_schema([changed])
        with self.assertRaises(a.AffordanceError): a.validate_fields_schema([field, field])
        root = self.create(typed_protocol())
        view = room.inspect_object(root, "object")
        for bad in [{"type": "nat", "maximum": 1 << 64}, {"type": "string"},
                    {"type": "enum", "options": ["x", "x"]}, {"type": "enum", "options": [True]},
                    {"type": "bool", "default": True}]:
            changed = copy.deepcopy(view)
            changed["root"]["protocol"]["affordances"]["write a notice"]["fields"]["extra"] = bad
            with self.assertRaises(a.AffordanceError): a.card(changed)

    def test_authored_examples_survive_raw_and_projected_cards_without_becoming_defaults(self):
        protocol = typed_protocol()
        examples = {"message": "Meet under the lantern.", "count": 2, "open": False, "color": "amber"}
        for name, value in examples.items():
            protocol["affordances"]["write a notice"]["fields"][name]["example"] = value
        root = self.create(protocol)
        view = room.inspect_object(root, "object")
        action = a.card(view)["actions"][0]
        self.assertEqual({f["name"]: f["example"] for f in action["fields"]}, examples)
        self.assertEqual(a.validate_fields_schema(action["fields"]), action["fields"])
        with self.assertRaises(a.AffordanceError): a.request(view, "a1", "actor", "missing")
        with self.assertRaises(a.AffordanceError): a.validate_fields({**action, "available": False}, examples)
        with self.assertRaises(a.AffordanceError): a.validate_fields({**action, "inspectOnly": True}, examples)
        actual = {**examples, "message": "My own words."}
        denied = a.request(view, "a1", "stranger", "denied", actual)
        self.assertEqual(world.exchange(self.db, denied)["data"], "unauthorized")
        first = a.request(view, "a1", "actor", "first", actual)
        self.assertEqual(first["input"], actual)
        committed = world.exchange(self.db, first)
        self.assertEqual(committed["kind"], "committed", committed)
        stale = a.request(view, "a1", "actor", "stale", examples)
        self.assertEqual(stale["expected"], root)
        self.assertEqual(world.exchange(self.db, stale)["data"], "stale read root")
        self.assertEqual(world.exchange(self.db, first), committed)

        view.update(format="delvetalk-projection-view-v1", mode="projection", data={
            "title": "Blue notice", "prose": "", "actions": {"write": {
                "text": "Write in blue", "command": "write a notice", "input": {"color": "blue"}}}})
        projected = a.card(view)["actions"][0]
        self.assertNotIn("color", [f["name"] for f in projected["fields"]])
        self.assertEqual({f["name"]: f["example"] for f in projected["fields"]},
                         {k: v for k, v in examples.items() if k != "color"})
        supplied = {k: v for k, v in actual.items() if k != "color"}
        self.assertEqual(a.request(view, "a1", "actor", "projected", supplied)["input"],
                         {**supplied, "color": "blue"})
        with self.assertRaises(a.AffordanceError): a.request(view, "a1", "actor", "override", actual)
        view["root"]["protocol"]["affordances"]["write a notice"]["fields"]["color"]["example"] = "green"
        with self.assertRaises(a.AffordanceError): a.card(view)

    def test_examples_use_the_same_strict_value_validation_on_both_schema_paths(self):
        view = room.inspect_object(self.create(typed_protocol()), "object")
        action = a.card(view)["actions"][0]
        bad_examples = [("message", ""), ("message", "x" * 81), ("message", "\ud800"),
                        ("message", {}), ("message", None), ("count", True), ("count", 0),
                        ("count", 11), ("count", 1.0), ("count", "1"), ("open", 0),
                        ("open", "false"), ("color", "green"), ("color", ["blue"])]
        for name, example in bad_examples:
            with self.subTest(name=name, example=repr(example)):
                changed = copy.deepcopy(view)
                changed["root"]["protocol"]["affordances"]["write a notice"]["fields"][name]["example"] = example
                with self.assertRaises(a.AffordanceError): a.card(changed)
                fields = copy.deepcopy(action["fields"])
                next(f for f in fields if f["name"] == name)["example"] = example
                with self.assertRaises(a.AffordanceError): a.validate_fields_schema(fields)

    def test_markup_is_data_and_no_input_is_invented(self):
        protocol = typed_protocol()
        protocol["name"] = '<img src=x onerror="bad()">'
        protocol["description"] = '<script>not executable</script>'
        protocol["affordances"]["write a notice"]["label"] = '<b onclick="bad()">Notice</b>'
        view = room.inspect_object(self.create(protocol), "object")
        card = a.card(view)
        self.assertEqual(card["title"], protocol["name"])
        self.assertEqual(card["prose"], protocol["description"])
        self.assertNotIn("html", card)
        self.assertEqual(card["actions"][0]["id"], "a1")
        with self.assertRaises(a.AffordanceError): a.request(view, "a1", "actor", "no-guessed-values")
        # Explicit zero-field metadata is different from no metadata at all.
        protocol = {"profile": "delvetalk-local-v1", "initial": {}, "commands": {
            "touch": {"require": [], "set": {}, "result": ["literal", "ok"], "outbox": []}},
            "affordances": {"touch": {"fields": {}}}}
        root = self.create(protocol, "zero")
        empty = room.inspect_object(root, "zero")
        self.assertEqual(world.exchange(self.db, a.request(empty, "a1", "actor", "touch"))["kind"], "committed")


if __name__ == "__main__": unittest.main()
