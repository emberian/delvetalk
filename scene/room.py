#!/usr/bin/env python3
"""Content-addressed scene artifacts and views of committed Lean room state."""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "delvetalk-room-artifact-v1"
VIEW = "delvetalk-room-view-v1"
PIN_PATHS = ("scene/parser.py", "scripts/process_custody.py", "scene/spween-bridge/Cargo.toml",
             "scene/spween-bridge/Cargo.lock", "scene/spween-bridge/src/main.rs")
SOURCE_PIN_PATHS = PIN_PATHS + ("scene/handlers.py",)
SOURCE_PROFILE = "spween-obend-handlers-i64-v1"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


parser = module("room_parser", "scene/parser.py")
world = module("room_world", "scripts/world.py")


class ArtifactError(ValueError):
    pass


def canonical(value):
    """The artifact identity encoding; exact source lives inside JSON strings."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def source_artifact(protocol, pins=None):
    """Retain exact parser custody around an already checked source protocol."""
    parsed = copy.deepcopy(protocol["spweenSource"])
    content = {**parsed, "pins": copy.deepcopy(pins if pins is not None else {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCE_PIN_PATHS})}
    artifact = {"format": FORMAT, "content": content, "protocol": copy.deepcopy(protocol)}
    validate_artifact(artifact)
    return artifact


def compile_artifact(source, *, profile=SOURCE_PROFILE):
    if profile != SOURCE_PROFILE:
        raise ArtifactError("scene compilation requires the source runtime profile")
    executable = ROOT / "scene/spween-bridge/target/debug/delvetalk-spween"
    binary_pin = hashlib.sha256(executable.read_bytes()).hexdigest()
    handlers = module("room_source_handlers", "scene/handlers.py")
    bundle = handlers.compile_source(source)
    if hashlib.sha256(executable.read_bytes()).hexdigest() != binary_pin:
        raise ArtifactError("Spween bridge executable changed during parsing")
    return source_artifact(bundle["protocol"])


def validate_artifact(artifact):
    """Validate internal bindings; returns canonical full-artifact SHA256.

    It does not execute source or compare historical pins to installed tools.
    """
    try:
        if set(artifact) != {"format", "content", "protocol"} or artifact["format"] != FORMAT:
            raise ArtifactError("unsupported room artifact envelope")
        content, protocol = artifact["content"], artifact["protocol"]
        if not isinstance(content, dict) or not isinstance(protocol, dict):
            raise ArtifactError("scene content and protocol must be objects")
        if content.get("profile") == SOURCE_PROFILE:
            if set(content) != {"source", "ast", "upstream", "profile", "pins"}:
                raise ArtifactError("incomplete source scene artifact")
            if content["upstream"] != parser.UPSTREAM or not isinstance(content["source"], str) or not isinstance(content["ast"], dict):
                raise ArtifactError("invalid source scene parser custody")
            pins = content["pins"]
            if not isinstance(pins, dict) or set(pins) != set(SOURCE_PIN_PATHS) or any(
                    not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in pins.values()):
                raise ArtifactError("invalid source scene compiler pins")
            if protocol.get("spweenSource") != {key: value for key, value in content.items() if key != "pins"}:
                raise ArtifactError("source scene differs from its checked protocol custody")
            if "sourcePackages" not in protocol or "viewProgram" not in protocol or "roomArtifact" in protocol:
                raise ArtifactError("source scene requires ordinary source methods and view")
            return digest(artifact)
        raise ArtifactError("scene artifacts require the ordinary source runtime")
    except ArtifactError:
        raise
    except (KeyError, TypeError, UnicodeError, ValueError) as error:
        raise ArtifactError("malformed room artifact: " + str(error)) from error


def artifact_path(store, artifact_id):
    if not isinstance(artifact_id, str) or not re.fullmatch(r"[0-9a-f]{64}", artifact_id):
        raise ArtifactError("invalid artifact ID")
    return Path(store) / (artifact_id + ".json")


def store_artifact(store, artifact):
    artifact_id = validate_artifact(artifact)
    data = canonical(artifact)
    directory = Path(store)
    directory.mkdir(parents=True, exist_ok=True)
    target = artifact_path(directory, artifact_id)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".room-", delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        try:
            # Atomic no-clobber publication: concurrent identical imports agree.
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != data:
                raise ArtifactError("existing artifact path contains different bytes")
        fd = os.open(directory, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    return artifact_id


def load_artifact(store, artifact_id):
    try:
        data = artifact_path(store, artifact_id).read_bytes()
        if hashlib.sha256(data).hexdigest() != artifact_id:
            raise ArtifactError("stored artifact byte digest mismatch")
        artifact = json.loads(data)
        if validate_artifact(artifact) != artifact_id or canonical(artifact) != data:
            raise ArtifactError("stored artifact is not canonical")
        return artifact
    except OSError as error:
        raise ArtifactError("room artifact unavailable: " + str(error)) from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ArtifactError("invalid stored artifact JSON") from error


def _raw(root, object_id, reason):
    return {"format": VIEW, "mode": "raw", "object": object_id,
            "root": copy.deepcopy(root), "reason": reason, "actions": []}


def room_view(root, artifact, object_id):
    """Evaluate the admitted pure view over captured state, without admission."""
    if artifact is None: return _raw(root, object_id, "Exact room artifact is unavailable")
    try:
        artifact_id = validate_artifact(artifact)
        if root["protocol"] != artifact["protocol"]:
            return _raw(root, object_id, "Artifact protocol differs from the committed root")
        if artifact["content"]["profile"] == SOURCE_PROFILE:
            projection = module("room_projection", "scene/projection.py")
            return projection.project(root, object_id)
        raise ArtifactError("scene view requires the ordinary source runtime")
    except (ArtifactError, KeyError, TypeError, IndexError, UnicodeError, ValueError) as error:
        return _raw(root, object_id, "Room rendering unavailable: " + str(error))


def choice_request(view, index, principal, intent):
    if view.get("mode") == "projection":
        projection = module("room_projection", "scene/projection.py")
        for key, action in view["data"]["actions"].items():
            if action["command"] == "choose" and action["input"].get("choice") == index:
                return projection.request(view, key, principal, intent)
        raise ArtifactError("choice is not displayed in this source view")
    raise ArtifactError("source projection required for scene choice")


def start_request(view, principal, intent):
    if view.get("mode") == "projection":
        projection = module("room_projection", "scene/projection.py")
        return projection.request(view, "start", principal, intent)
    raise ArtifactError("source projection required for scene start")


def inspect_object(root, object_id, artifact=None, panel="main", *, expected_runtime=None):
    """Join source-bound scenes and optional admitted pure view projections.

    A panel is presentation input, never a participant identity or cloned state.
    """
    protocol = root.get("protocol", {}) if isinstance(root, dict) else {}
    if "viewProgram" in protocol:
        try:
            projection = module("room_projection", "scene/projection.py")
            return projection.project(root, object_id, panel, expected_runtime=expected_runtime)
        except Exception as error:
            return _raw(root, object_id, "Pure view projection unavailable: " + str(error))
    return _raw(root, object_id, "No supported source-bound room or pure view program")


def view_request(view, action_id, principal, intent):
    """Turn a displayed descriptor into a request retaining its observed root."""
    if view.get("mode") == "projection":
        projection = module("room_projection", "scene/projection.py")
        return projection.request(view, action_id, principal, intent)
    raise ArtifactError("source projection required for action dispatch")


def source_document(view):
    """Expose retained source without looking up or refreshing the current root."""
    root = view["root"]
    protocol = root["protocol"]
    common = {"format": "delvetalk-object-source-v1", "object": view["object"],
              "root": copy.deepcopy(root)}
    if view.get("mode") == "projection" and view.get("source") != protocol.get("viewProgram"):
        raise ArtifactError("saved view source differs from its retained root")
    if "spweenSource" in protocol:
        text = protocol["spweenSource"]["source"]
        return {**common, "kind": "spween", "source": text,
                "sourceSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "sourcePackages": copy.deepcopy(protocol["sourcePackages"]),
                "program": copy.deepcopy(protocol["viewProgram"]),
                "spweenSource": copy.deepcopy(protocol["spweenSource"])}
    if "viewProgram" in protocol:
        source = {**common, "kind": "bend-view", "program": copy.deepcopy(protocol["viewProgram"])}
        for key in ('sourcePackages', 'spweenSource'):
            if key in protocol:
                source[key] = copy.deepcopy(protocol[key])
        if view.get("source", {}).get("profile") in ("delvetalk-obend-menu-v1", "delvetalk-obend-data-menu-v1"):
            source.update(rawViewData=copy.deepcopy(view["rawData"]),
                          publicViewData=copy.deepcopy(view["data"]))
            if view["source"]["profile"] in ("delvetalk-obend-data-menu-v1"):
                projection = module("room_projection", "scene/projection.py")
                source["children"] = projection.children(view)
                if "invitations" in view:
                    source["invitations"] = projection.invitations(view)
        return source
    return {**common, "kind": "protocol", "program": copy.deepcopy(protocol)}


def html_view(view):
    """Static escaped document; requests remain explicit machine-readable data."""
    if view.get("mode") == "projection":
        projection = module("room_projection", "scene/projection.py")
        return projection.html_view(view)
    escape = lambda x: html.escape(str(x), quote=True)
    title = view.get("title", "Raw room state")
    body = ["<!doctype html><html><head><meta charset=\"utf-8\">",
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
            "<title>" + escape(title) + "</title><style>body{max-width:58em;margin:3em auto;padding:0 1em;font:18px/1.55 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}li{margin:.6em 0}code{font-size:.85em}</style></head><body>",
            "<h1>" + escape(title) + "</h1>"]
    body.append("<p>" + escape(view["reason"]) + "</p>")
    body.append("<details><summary>Committed root</summary><pre>" + escape(world.wire_dumps(view["root"])) + "</pre></details>")
    body.append("</body></html>")
    return "".join(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="op", required=True)
    compile_cmd = commands.add_parser("compile")
    compile_cmd.add_argument("source", type=Path)
    compile_cmd.add_argument("store", type=Path)
    view_cmd = commands.add_parser("view")
    view_cmd.add_argument("database", type=Path)
    view_cmd.add_argument("object")
    view_cmd.add_argument("store", type=Path)
    view_cmd.add_argument("artifact_id")
    view_cmd.add_argument("--html", action="store_true")
    inspect_cmd = commands.add_parser("inspect")
    inspect_cmd.add_argument("database", type=Path)
    inspect_cmd.add_argument("object")
    inspect_cmd.add_argument("--store", type=Path)
    inspect_cmd.add_argument("--artifact-id")
    inspect_cmd.add_argument("--panel", default="main")
    inspect_cmd.add_argument("--html", action="store_true")
    source_cmd = commands.add_parser("source")
    source_cmd.add_argument("view", type=Path)
    source_cmd.add_argument("--raw", action="store_true", help="exact Spween text or admitted JSON program")
    request_cmd = commands.add_parser("request", aliases=["choose"])
    request_cmd.add_argument("view", type=Path)
    request_cmd.add_argument("principal")
    request_cmd.add_argument("intent")
    action = request_cmd.add_mutually_exclusive_group(required=True)
    action.add_argument("--start", action="store_true")
    action.add_argument("--choice", type=int)
    action.add_argument("--action", help="displayed action ID or exact scene command")
    args = parser.parse_args()
    if args.op == "compile":
        artifact = compile_artifact(args.source.read_bytes().decode("utf-8"))
        artifact_id = store_artifact(args.store, artifact)
        print(json.dumps({"artifactId": artifact_id, "path": str(artifact_path(args.store, artifact_id))}))
    elif args.op == "source":
        document = source_document(world.wire_loads(args.view.read_text()))
        if args.raw:
            sys.stdout.write(document["source"] if document["kind"] == "spween" else world.wire_dumps(document["program"]))
        else:
            print(world.wire_dumps(document))
    elif args.op in ("request", "choose"):
        view = world.wire_loads(args.view.read_text())
        request = (view_request(view, "start", args.principal, args.intent) if args.start else
                   view_request(view, args.action, args.principal, args.intent) if args.action is not None else
                   choice_request(view, args.choice, args.principal, args.intent))
        print(world.wire_dumps(request))
    else:
        root = world.exchange(args.database, {"op": "inspect", "object": args.object, "principal": "viewer"})
        try: artifact = load_artifact(args.store, args.artifact_id) if args.store and args.artifact_id else None
        except ArtifactError: artifact = None
        view = inspect_object(root, args.object, artifact, getattr(args, "panel", "main"))
        print(html_view(view) if args.html else world.wire_dumps(view))


if __name__ == "__main__":
    try: main()
    except (ArtifactError, parser.LoweringError, ValueError, OSError) as error:
        print("room: " + str(error), file=sys.stderr)
        raise SystemExit(1)
