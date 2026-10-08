#!/usr/bin/env python3
"""A source-bound room journey over actual local Lean receipts."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("room", ROOT / "scene/room.py")
room = importlib.util.module_from_spec(spec)
spec.loader.exec_module(room)


class RoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "scene/examples/repair-cafe.scene").read_bytes().decode("utf-8")
        cls.artifact = room.compile_artifact(cls.source)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name) / "artifacts"
        self.db = Path(self.tmp.name) / "world.json"
        self.artifact_id = room.store_artifact(self.store, self.artifact)
        created = room.world.exchange(self.db, {"op": "create", "object": "cafe", "principal": "owner",
                            "intent": "create", "protocol": self.artifact["protocol"], "law": ["visitor", "other"]})
        self.assertEqual(created["kind"], "committed", created)
        self.root = created["data"]["root"]

    def tearDown(self): self.tmp.cleanup()

    def view(self, root=None, artifact=None):
        return room.room_view(root or self.root, self.artifact if artifact is None else artifact, "cafe")

    def send(self, request):
        receipt = room.world.exchange(self.db, request)
        if receipt["kind"] == "committed": self.root = receipt["data"]["root"]
        return receipt

    def enter(self):
        receipt = self.send(room.start_request(self.view(), "visitor", "enter"))
        self.assertEqual(receipt["kind"], "committed", receipt)
        return receipt

    def test_repair_cafe_two_actions_shared_root_and_constellation(self):
        self.assertEqual(self.view()["actions"], [{"command": "start", "text": "Enter the room"}])
        self.enter()
        view = self.view()
        self.assertEqual(view["mode"], "room", view)
        self.assertEqual(view["source"], self.source)
        self.assertIn("mechanical moth", view["prose"][0]["text"])
        self.assertEqual([c["available"] for c in view["choices"]], [True, True, False])
        denied = self.send(room.choice_request(view, 2, "visitor", "too-soon"))
        self.assertEqual(denied["kind"], "refused")
        first = room.choice_request(view, 0, "visitor", "align")
        receipt = self.send(first)
        self.assertEqual(receipt["kind"], "committed", receipt)
        # Another participant's old view is stale; it cannot independently
        # consume a shared session transition using an old preimage.
        stale = self.send(room.choice_request(view, 1, "other", "old-wind"))
        self.assertEqual(stale["data"], "stale read root")
        view = self.view()
        self.assertEqual([c["available"] for c in view["choices"]], [False, True, False])
        self.assertEqual(self.send(room.choice_request(view, 1, "other", "wind"))["kind"], "committed")
        view = self.view()
        self.assertEqual([c["available"] for c in view["choices"]], [False, False, True])
        self.assertEqual(self.send(room.choice_request(view, 2, "visitor", "release"))["kind"], "committed")
        view = self.view()
        self.assertEqual(view["passage"]["name"], "window")
        self.assertIn("constellation", view["prose"][0]["text"])
        self.assertEqual(self.send(room.choice_request(view, 0, "other", "follow"))["kind"], "committed")
        self.assertEqual(self.view()["passage"]["name"], "constellation")
        self.assertEqual(room.world.exchange(self.db, first), receipt)

    def test_renderer_never_runs_parser_or_entry_effects(self):
        self.enter()
        before = self.db.read_bytes()
        with mock.patch.object(room.lower, "bridge", side_effect=AssertionError("parser rerun")), \
             mock.patch.object(room.lower, "lower_document", side_effect=AssertionError("compiler rerun")), \
             mock.patch.object(room.world, "exchange", side_effect=AssertionError("host rerun")):
            for _ in range(3):
                self.assertEqual(self.view()["mode"], "room")
                self.assertIn("Exact scene source", room.html_view(self.view()))
        self.assertEqual(self.db.read_bytes(), before)

    def test_artifact_missing_mismatched_tampered_and_immutable_store(self):
        self.assertEqual(room.load_artifact(self.store, self.artifact_id), self.artifact)
        self.assertEqual(room.store_artifact(self.store, self.artifact), self.artifact_id)
        path = room.artifact_path(self.store, self.artifact_id)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), self.artifact_id)
        self.assertEqual(room.room_view(self.root, None, "cafe")["mode"], "raw")
        changed = copy.deepcopy(self.artifact)
        changed["content"]["ast"]["meta"]["title"] = "Substituted title"
        self.assertEqual(room.room_view(self.root, changed, "cafe")["mode"], "raw")
        with self.assertRaises(room.ArtifactError): room.store_artifact(self.store, changed)
        other = copy.deepcopy(self.root)
        other["protocol"]["name"] = "different program"
        self.assertEqual(self.view(root=other)["mode"], "raw")
        path.write_bytes(b"{}"); damaged = path.read_bytes()
        with self.assertRaises(room.ArtifactError): room.load_artifact(self.store, self.artifact_id)
        with self.assertRaises(room.ArtifactError): room.store_artifact(self.store, self.artifact)
        self.assertEqual(path.read_bytes(), damaged)
        with self.assertRaises(room.ArtifactError): room.artifact_path(self.store, "../outside")

    def test_requests_keep_exact_view_root_and_lean_decides(self):
        self.enter()
        view = self.view()
        request = room.choice_request(view, 0, "intruder", "wrong-authority")
        self.assertEqual(request["expected"], view["root"])
        self.assertIsNot(request["expected"], view["root"])
        self.assertEqual(self.send(request)["data"], "unauthorized")
        forged = copy.deepcopy(view)
        forged["choices"][2]["available"] = True
        self.assertEqual(self.send(room.choice_request(forged, 2, "visitor", "forged-label"))["kind"], "refused")
        with self.assertRaises(room.ArtifactError): room.choice_request(room.room_view(self.root, None, "cafe"), 0, "visitor", "raw")

    def test_html_escapes_source_title_and_prose(self):
        source = self.source.replace("The Repair Cafe", "<script>bad()</script>").replace(
            "A mechanical moth", '<img src=x onerror="bad()"> A mechanical moth')
        artifact = room.compile_artifact(source)
        # Rendering binds to a root with this complete exact protocol. This test
        # uses the real initial state; no script or event handler is executable.
        root = {**self.root, "protocol": artifact["protocol"], "state": artifact["protocol"]["initial"]}
        rendered = room.html_view(room.room_view(root, artifact, "cafe"))
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&lt;img", rendered)
        self.assertIn("Content-Security-Policy", rendered)

    def test_source_spans_and_cli_machine_and_html_views(self):
        self.enter()
        view = self.view()
        raw = self.source.encode("utf-8")
        for prose in view["prose"]:
            a, z = prose["span"]
            self.assertEqual(prose["sourceSlice"], raw[a:z].decode("utf-8"))
        command = [sys.executable, str(ROOT / "scene/room.py"), "view", str(self.db), "cafe", str(self.store), self.artifact_id]
        result = subprocess.run(command, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), view)
        view_path = Path(self.tmp.name) / "view.json"
        view_path.write_text(result.stdout)
        request = subprocess.run([sys.executable, str(ROOT / "scene/room.py"), "request", str(view_path),
                                  "visitor", "cli-align", "--choice", "0"],
                                 text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(request.stdout), room.choice_request(view, 0, "visitor", "cli-align"))
        result = subprocess.run(command + ["--html"], text=True, capture_output=True, check=True)
        self.assertIn("The Repair Cafe", result.stdout)
        missing = subprocess.run(command[:-1] + ["0" * 64], text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(missing.stdout)["mode"], "raw")

    def test_malformed_migrated_state_degrades_to_raw(self):
        self.enter()
        for field, value in [("choices", {"length": -1, "items": {}}),
                             ("choices", {"length": 1 << 80, "items": {}}),
                             ("requirements", "yes"), ("vars", {"bad": {"kind": "int", "value": -1}})]:
            root = copy.deepcopy(self.root)
            root["state"]["session"][field] = value
            self.assertEqual(self.view(root=root)["mode"], "raw")

    def test_inspect_source_choose_retains_the_saved_scene(self):
        self.enter()
        view = room.inspect_object(self.root, "cafe", self.artifact)
        self.assertEqual(view, self.view())
        source = room.source_document(view)
        self.assertEqual(source["source"], self.source)
        self.assertEqual(source["root"], view["root"])
        saved = Path(self.tmp.name) / "saved.json"
        saved.write_text(room.world.wire_dumps(view))
        # Another transition occurs before the participant submits their saved
        # choice; source/choose must retain that observed version throughout.
        self.assertEqual(self.send(room.choice_request(view, 0, "other", "earlier"))["kind"], "committed")
        source_run = subprocess.run([sys.executable, str(ROOT / "scene/room.py"), "source", str(saved), "--raw"],
                                    capture_output=True, check=True)
        self.assertEqual(source_run.stdout, self.source.encode("utf-8"))
        request_run = subprocess.run([sys.executable, str(ROOT / "scene/room.py"), "choose", str(saved),
                                     "visitor", "saved-choice", "--action", "choose:0:1"],
                                    text=True, capture_output=True, check=True)
        request = json.loads(request_run.stdout)
        self.assertEqual(request["expected"], view["root"])
        self.assertEqual(self.send(request)["data"], "stale read root")
        forged = copy.deepcopy(view)
        forged["source"] += "\nSubstituted source"
        with self.assertRaises(room.ArtifactError): room.source_document(forged)

    def test_pure_projection_join_and_shared_panels(self):
        protocol = json.loads((ROOT / "scene/projections/sign-v1.json").read_text())
        created = room.world.exchange(self.db, {"op": "create", "object": "sign", "principal": "owner",
                    "intent": "create-sign", "protocol": protocol, "law": ["visitor"]})
        root = created["data"]["root"]
        before = self.db.read_bytes()
        main = room.inspect_object(root, "sign")
        details = room.inspect_object(root, "sign", panel="details")
        self.assertEqual(main["mode"], "projection", main)
        self.assertEqual(main["root"], details["root"])
        self.assertNotEqual(main["data"]["title"], details["data"]["title"])
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(room.source_document(main)["program"], root["protocol"]["viewProgram"])
        self.assertIn("Exact view program", room.html_view(main))
        request = room.view_request(details, "light", "visitor", "light-from-panel")
        self.assertEqual(request["object"], "sign")
        self.assertEqual(request["expected"], root)
        receipt = room.world.exchange(self.db, request)
        self.assertEqual(receipt["kind"], "committed", receipt)
        changed = room.inspect_object(receipt["data"]["root"], "sign")
        self.assertEqual(changed["data"]["prose"], "The lamp is lit.")
        stale = room.view_request(main, "light", "visitor", "stale-panel")
        self.assertEqual(room.world.exchange(self.db, stale)["data"], "stale read root")
        command = [sys.executable, str(ROOT / "scene/room.py"), "inspect", str(self.db), "sign", "--panel", "details"]
        output = subprocess.run(command, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(output.stdout)["mode"], "projection")

    def test_projection_failure_and_unsupported_object_keep_raw_source(self):
        protocol = json.loads((ROOT / "scene/projections/sign-v1.json").read_text())
        root = {"protocol": protocol, "state": protocol["initial"], "law": ["visitor"], "version": 0}
        root["protocol"]["viewProgram"]["term"] = ["lam", ["lam", ["perform", ["label", "forbidden"]]]]
        view = room.inspect_object(root, "bad-sign")
        self.assertEqual(view["mode"], "raw")
        self.assertIn("Pure view projection unavailable", view["reason"])
        self.assertEqual(room.source_document(view)["program"], root["protocol"]["viewProgram"])
        del root["protocol"]["viewProgram"]
        raw = room.inspect_object(root, "plain-sign")
        self.assertEqual(room.source_document(raw)["program"], root["protocol"])
        with self.assertRaises(room.ArtifactError): room.view_request(raw, "light", "visitor", "no-view")


if __name__ == "__main__": unittest.main()
