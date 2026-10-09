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
PIN_PATHS = ("scene/lower.py", "scene/spween-bridge/Cargo.toml",
             "scene/spween-bridge/Cargo.lock", "scene/spween-bridge/src/main.rs")


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


lower = module("room_lower", "scene/lower.py")
world = module("room_world", "scripts/world.py")


class ArtifactError(ValueError):
    pass


def canonical(value):
    """The artifact identity encoding; exact source lives inside JSON strings."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def current_pins():
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in PIN_PATHS}


def wrap_bundle(bundle, pins=None):
    """Bind a previously compiled bundle to its installed protocol metadata.

    This does not recompile or certify compiler correctness. The caller supplies
    the compiler/translation result; the immutable identity makes substitution
    detectable when the renderer receives the admitted protocol's exact root.
    """
    required = {"source", "ast", "upstream", "profile", "provenance", "initialVars", "has", "protocol"}
    optional = {"bridge_binary_sha256"}
    if not isinstance(bundle, dict) or not required <= set(bundle) or set(bundle) - required - optional:
        raise ArtifactError("expected a complete Spween lowering bundle")
    content = copy.deepcopy({k: v for k, v in bundle.items() if k != "protocol"})
    content["pins"] = copy.deepcopy(current_pins() if pins is None else pins)
    protocol = copy.deepcopy(bundle["protocol"])
    if "roomArtifact" in protocol:
        raise ArtifactError("protocol already has a room artifact binding")
    protocol["roomArtifact"] = {"format": FORMAT, "contentSha256": digest(content)}
    artifact = {"format": FORMAT, "content": content, "protocol": protocol}
    validate_artifact(artifact)
    return artifact


def compile_artifact(source, initial_vars=None, has=None, *, profile=lower.CURRENT_PROFILE):
    executable = ROOT / "scene/spween-bridge/target/debug/delvetalk-spween"
    binary_pin = hashlib.sha256(executable.read_bytes()).hexdigest()
    document = lower.bridge({"op": "parse", "source": source})
    if hashlib.sha256(executable.read_bytes()).hexdigest() != binary_pin:
        raise ArtifactError("Spween bridge executable changed during parsing")
    bundle = lower.lower_document(document, initial_vars, has, profile=profile)
    bundle["bridge_binary_sha256"] = binary_pin
    return wrap_bundle(bundle)


def validate_artifact(artifact):
    """Validate internal bindings; returns canonical full-artifact SHA256.

    It does not execute source or compare historical pins to installed tools.
    """
    try:
        if set(artifact) != {"format", "content", "protocol"} or artifact["format"] != FORMAT:
            raise ArtifactError("unsupported room artifact envelope")
        content, protocol = artifact["content"], artifact["protocol"]
        required = {"source", "ast", "upstream", "profile", "provenance", "initialVars", "has", "pins"}
        if not required <= set(content) or set(content) - required - {"bridge_binary_sha256"}:
            raise ArtifactError("incomplete room artifact content")
        if "bridge_binary_sha256" in content and (not isinstance(content["bridge_binary_sha256"], str) or
                not re.fullmatch(r"[0-9a-f]{64}", content["bridge_binary_sha256"])):
            raise ArtifactError("invalid parser executable pin")
        if not isinstance(content["source"], str) or not isinstance(content["ast"], dict):
            raise ArtifactError("source and AST must be retained")
        if not isinstance(content["initialVars"], dict) or not isinstance(content["has"], dict):
            raise ArtifactError("handler configuration must be objects")
        if content["profile"] not in lower.SUPPORTED_PROFILES or content["upstream"] != lower.UPSTREAM:
            raise ArtifactError("unsupported scene profile or upstream revision")
        pins = content["pins"]
        if not isinstance(pins, dict) or set(pins) != set(PIN_PATHS) or any(
                not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in pins.values()):
            raise ArtifactError("missing or invalid compiler/parser pins")
        provenance = content["provenance"]
        if provenance["sourceSha256"] != hashlib.sha256(content["source"].encode("utf-8")).hexdigest():
            raise ArtifactError("source digest mismatch")
        if provenance["compilerSha256"] != pins["scene/lower.py"] or provenance["upstream"] != content["upstream"]:
            raise ArtifactError("compiler/upstream pin mismatch")
        if protocol["provenance"] != provenance or protocol["sceneProfile"] != content["profile"]:
            raise ArtifactError("protocol provenance mismatch")
        expected = {"format": FORMAT, "contentSha256": digest(content)}
        if protocol["roomArtifact"] != expected:
            raise ArtifactError("protocol does not bind this exact room content")
        return digest(artifact)
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


def _sequence(value):
    if not isinstance(value, dict) or set(value) != {"length", "items"} or type(value["length"]) is not int or value["length"] < 0:
        raise ArtifactError("invalid committed sequence")
    if not isinstance(value["items"], dict) or len(value["items"]) != value["length"] or set(value["items"]) != {str(i) for i in range(value["length"])}:
        raise ArtifactError("invalid committed sequence items")
    return lower.decode_sequence(value)


def _variables(values):
    if not isinstance(values, dict): raise ArtifactError("invalid committed variable record")
    result = {}
    for key, value in values.items():
        kind = value["kind"]
        fields = {"null": {"kind"}, "bool": {"kind", "value"},
                  "int": {"kind", "value"}, "string": {"kind", "value", "text"}}.get(kind)
        if fields is None or set(value) != fields:
            raise ArtifactError("invalid committed variable value")
        if kind == "bool" and type(value["value"]) is not bool:
            raise ArtifactError("invalid committed Boolean")
        if kind in ("int", "string") and (type(value["value"]) is not int or value["value"] < 0):
            raise ArtifactError("invalid committed numeric encoding")
        if kind == "int" and value["value"] > lower.MAX:
            raise ArtifactError("committed integer outside i64")
        if kind == "string" and not isinstance(value["text"], str):
            raise ArtifactError("invalid committed string")
        result[key] = lower.decode_value(value)
    return result


def room_view(root, artifact, object_id):
    """Project committed state only. Never parse, execute, start, or refresh it."""
    if artifact is None: return _raw(root, object_id, "Exact room artifact is unavailable")
    try:
        artifact_id = validate_artifact(artifact)
        if root["protocol"] != artifact["protocol"]:
            return _raw(root, object_id, "Artifact protocol differs from the committed root")
        session = root["state"]["session"]
        if type(session["started"]) is not bool or type(session["ended"]) is not bool:
            raise ArtifactError("invalid committed session flags")
        if type(session["requirements"]) is not bool:
            raise ArtifactError("invalid committed requirements flag")
        content = artifact["content"]
        ast = content["ast"]
        passage = None
        prose = []
        choices = []
        if session["started"] and not session["ended"]:
            index = session["passage"]
            if type(index) is not int or not 0 <= index < len(ast["passages"]):
                raise ArtifactError("committed passage is outside the retained AST")
            passage = ast["passages"][index]
            source_bytes = content["source"].encode("utf-8")
            for item in passage["content"]:
                if item["kind"] == "prose":
                    start, end = item["span"]
                    if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(source_bytes):
                        raise ArtifactError("invalid prose source span")
                    prose.append({"text": item["text"], "span": [start, end],
                                  "sourceSlice": source_bytes[start:end].decode("utf-8")})
            source_choices = [c for c in passage["content"] if c["kind"] == "choice"]
            committed_choices = _sequence(session["choices"])
            if len(source_choices) != len(committed_choices):
                raise ArtifactError("committed choice count differs from retained AST")
            for i, (source_choice, choice) in enumerate(zip(source_choices, committed_choices)):
                if type(choice["index"]) is not int or choice["index"] != i or choice["text"] != source_choice["text"] or type(choice["available"]) is not bool:
                    raise ArtifactError("committed choices do not match the retained AST")
                choices.append({"index": i, "text": choice["text"], "available": choice["available"],
                                "command": f"choose:{index}:{i}", "span": source_choice["span"]})
        elif _sequence(session["choices"]):
            raise ArtifactError("inactive scene has committed choices")
        return {"format": VIEW, "mode": "room", "object": object_id, "root": copy.deepcopy(root),
                "artifactId": artifact_id, "contentSha256": digest(content), "source": content["source"],
                "ast": copy.deepcopy(ast), "pins": copy.deepcopy(content["pins"]),
                "title": ast["meta"]["title"], "started": session["started"], "ended": session["ended"],
                "passage": None if passage is None else {"index": session["passage"], "name": passage["name"], "span": passage["span"]},
                "prose": prose, "choices": choices, "requirements": session["requirements"],
                "variables": _variables(session["vars"]),
                "actions": ([{"command": "start", "text": "Enter the room"}] if not session["started"] else [])}
    except (ArtifactError, KeyError, TypeError, IndexError, UnicodeError, ValueError) as error:
        return _raw(root, object_id, "Room rendering unavailable: " + str(error))


def _request(view, command, principal, intent):
    if view.get("mode") != "room": raise ArtifactError("raw views have no scene actions")
    if not all(isinstance(x, str) and x for x in (principal, intent, view.get("object"))):
        raise ArtifactError("principal, intent and object must be nonempty strings")
    return {"op": "invoke", "object": view["object"], "principal": principal, "intent": intent,
            "expected": copy.deepcopy(view["root"]), "command": command, "input": {}}


def choice_request(view, index, principal, intent):
    if type(index) is not int or index < 0 or index >= len(view.get("choices", [])):
        raise ArtifactError("choice is not displayed in this view")
    # Availability is displayed, not used here to grant or deny admission.
    return _request(view, view["choices"][index]["command"], principal, intent)


def start_request(view, principal, intent):
    if view.get("started") is not False: raise ArtifactError("this view does not display a start action")
    return _request(view, "start", principal, intent)


def inspect_object(root, object_id, artifact=None, panel="main", *, expected_runtime=None):
    """Join source-bound scenes and optional admitted pure view projections.

    A panel is presentation input, never a participant identity or cloned state.
    """
    protocol = root.get("protocol", {}) if isinstance(root, dict) else {}
    if "roomArtifact" in protocol:
        return room_view(root, artifact, object_id)
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
    if view.get("mode") != "room": raise ArtifactError("raw views have no actions")
    if action_id == "start": return start_request(view, principal, intent)
    for choice in view["choices"]:
        if choice["command"] == action_id:
            return choice_request(view, choice["index"], principal, intent)
    raise ArtifactError("action is not displayed in this view")


def source_document(view):
    """Expose retained source without looking up or refreshing the current root."""
    root = view["root"]
    protocol = root["protocol"]
    common = {"format": "delvetalk-object-source-v1", "object": view["object"],
              "root": copy.deepcopy(root)}
    if view.get("mode") == "room":
        source = view["source"]
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if source_hash != protocol["provenance"]["sourceSha256"]:
            raise ArtifactError("saved view source does not match its retained root")
        return {**common, "kind": "spween", "source": source, "sourceSha256": source_hash,
                "artifactId": view["artifactId"], "pins": copy.deepcopy(view["pins"])}
    if "viewProgram" in protocol:
        return {**common, "kind": "bend-view", "program": copy.deepcopy(protocol["viewProgram"])}
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
    if view["mode"] == "raw": body.append("<p>" + escape(view["reason"]) + "</p>")
    else:
        if view["ended"]: body.append("<p>This scene has ended.</p>")
        elif not view["started"]: body.append("<p>Enter the room with the start action.</p>")
        for prose in view["prose"]: body.append("<p>" + escape(prose["text"]) + "</p>")
        body.append("<ol>")
        for choice in view["choices"]:
            status = "available" if choice["available"] else "unavailable"
            body.append("<li>" + escape(choice["text"]) + " — " + status + " <code>" + escape(choice["command"]) + "</code></li>")
        body.append("</ol><details><summary>Exact scene source</summary><pre>" + escape(view["source"]) + "</pre></details>")
    body.append("<details><summary>Committed root</summary><pre>" + escape(world.wire_dumps(view["root"])) + "</pre></details>")
    body.append("</body></html>")
    return "".join(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="op", required=True)
    compile_cmd = commands.add_parser("compile")
    compile_cmd.add_argument("source", type=Path)
    compile_cmd.add_argument("store", type=Path)
    compile_cmd.add_argument("--state", type=Path)
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
        config = json.loads(args.state.read_text()) if args.state else {}
        artifact = compile_artifact(args.source.read_bytes().decode("utf-8"), config.get("vars"), config.get("has"))
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
    except (ArtifactError, lower.LoweringError, ValueError, OSError) as error:
        print("room: " + str(error), file=sys.stderr)
        raise SystemExit(1)
