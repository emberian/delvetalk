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
                             ("requirements", "yes"), ("vars", {"bad": {"kind": "int", "value": -1}})]:
            root = copy.deepcopy(self.root)
            root["state"]["session"][field] = value
            self.assertEqual(self.view(root=root)["mode"], "raw")


if __name__ == "__main__": unittest.main()
