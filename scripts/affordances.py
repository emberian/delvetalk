#!/usr/bin/env python3
"""Small action cards over captured views; no evaluation, admission, or refresh.

Schema descriptions and physical framing perform no evaluation or admission.
Request factories load only for requests from an already captured view.
"""
from __future__ import annotations

import copy
import importlib.util
import math
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "delvetalk-action-card-v1"
MAX_FIELDS = 32
MAX_ACTIONS = 128
MAX_SAFE_NAT = (1 << 53) - 1


class AffordanceError(ValueError):
    pass


def _string(value, name, maximum=None, *, nonempty=False):
    if not isinstance(value, str) or (nonempty and not value):
        raise AffordanceError(name + " must be a" + (" nonempty" if nonempty else "") + " string")
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise AffordanceError(name + " contains a non-scalar Unicode value")
    if maximum is not None and len(value) > maximum:
        raise AffordanceError(name + " is too long")
    return value


def _integer(value, name, lower=0, upper=MAX_SAFE_NAT):
    if type(value) is not int or not lower <= value <= upper:
        raise AffordanceError(name + " must be an integer in the declared bounds")
    return value


def _normalize_field(name, specification):
    _string(name, "field name", 128, nonempty=True)
    if not isinstance(specification, dict): raise AffordanceError("field specification must be an object")
    kind = specification.get("type")
    common = {"type", "label", "example"}
    allowed = {"string": {"minLength", "maxLength"}, "nat": {"minimum", "maximum"},
               "bool": set(), "enum": {"options"}}
    if not isinstance(kind, str) or kind not in allowed or set(specification) - common - allowed[kind]:
        raise AffordanceError("unknown field type or attributes")
    field = {"name": name, "label": _string(specification.get("label", name), "field label", 256),
             "type": kind, "required": True}
    if kind == "string":
        maximum = _integer(specification.get("maxLength"), "maxLength", 0, 65536)
        field.update(minLength=_integer(specification.get("minLength", 0), "minLength", 0, maximum), maxLength=maximum)
    elif kind == "nat":
        maximum = _integer(specification.get("maximum"), "maximum")
        field.update(minimum=_integer(specification.get("minimum", 0), "minimum", 0, maximum), maximum=maximum)
    elif kind == "enum":
        options = specification.get("options")
        if not isinstance(options, list) or not 1 <= len(options) <= 32:
            raise AffordanceError("enum requires 1..32 options")
        for value in options: _string(value, "enum option", 256)
        if len(set(options)) != len(options): raise AffordanceError("enum options must be distinct")
        field["options"] = list(options)
    if "example" in specification:
        field["example"] = _validate_values([field], {name: specification["example"]})[name]
    return field


def _normalized_fields(fields):
    """Recheck normalized fields before accepting a root-free external card."""
    if not isinstance(fields, list) or len(fields) > MAX_FIELDS:
        raise AffordanceError("fields must be an array of at most 32 entries")
    result = []
    names = set()
    for field in fields:
        if not isinstance(field, dict) or field.get("required") is not True:
            raise AffordanceError("every field must explicitly be required")
        if "name" not in field: raise AffordanceError("field name missing")
        spec = {k: v for k, v in field.items() if k not in ("name", "required")}
        normalized = _normalize_field(field["name"], spec)
        if normalized["name"] in names: raise AffordanceError("duplicate field name")
        names.add(normalized["name"])
        result.append(normalized)
    return result


def validate_fields_schema(fields):
    """Validate externally supplied normalized field descriptions without values."""
    return _normalized_fields(fields)


def physical_values(values):
    """Frame bounded inert contribution data; source decides its meaning."""
    if not isinstance(values, dict):
        raise AffordanceError("contribution fields must be an object")
    pending = [(values, 0)]
    count = 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if count > 4096 or depth > 64:
            raise AffordanceError("contribution exceeds physical data limits")
        if isinstance(value, dict):
            if count + len(pending) + len(value) > 4096:
                raise AffordanceError("contribution exceeds physical data limits")
            for key, child in value.items():
                _string(key, "contribution key")
                pending.append((child, depth + 1))
        elif isinstance(value, list):
            if count + len(pending) + len(value) > 4096:
                raise AffordanceError("contribution exceeds physical data limits")
            pending.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            _string(value, "contribution string")
        elif isinstance(value, (float, Decimal)):
            if not (value.is_finite() if isinstance(value, Decimal) else math.isfinite(value)):
                raise AffordanceError("contribution number must be finite")
        elif value is not None and type(value) not in (bool, int):
            raise AffordanceError("contribution requires inert JSON data")
    # Use the actual transport spelling for the byte boundary, including Decimal.
    import world
    if len(world.wire_dumps(values).encode("utf-8")) > 65536:
        raise AffordanceError("contribution exceeds 64 KiB")
    return copy.deepcopy(values)


def _validate_values(fields, values, *, complete=True):
    if not isinstance(values, dict): raise AffordanceError("field values must be an object")
    names = {f["name"] for f in fields}
    if set(values) - names: raise AffordanceError("unknown field values")
    if complete and names - set(values): raise AffordanceError("missing required field values")
    for field in fields:
        name = field["name"]
        if name not in values: continue
        value = values[name]
        if field["type"] == "string":
            _string(value, name, field["maxLength"])
            if len(value) < field["minLength"]: raise AffordanceError(name + " is too short")
        elif field["type"] == "nat":
            _integer(value, name, field["minimum"], field["maximum"])
        elif field["type"] == "bool":
            if type(value) is not bool: raise AffordanceError(name + " must be a Boolean")
        else:
            _string(value, name)
            if value not in field["options"]: raise AffordanceError(name + " is not an enum option")
    return copy.deepcopy(values)


def validate_fields(action, fields):
    """Validate a normalized card action and exact supplied application fields.

    Useful to a token or language interpreter; this grants no ability to act.
    """
    if not isinstance(action, dict): raise AffordanceError("action must be an object")
    if "inspectOnly" in action and type(action["inspectOnly"]) is not bool:
        raise AffordanceError("inspectOnly must be a Boolean")
    if action.get("inspectOnly") is True or action.get("available") is not True:
        raise AffordanceError("action is inspect-only or cannot construct a request")
    schema = _normalized_fields(action.get("fields"))
    values = _validate_values(schema, fields)
    _child_values(action.get("children", []), schema, values)
    return values


def _child_name(value):
    _string(value, "child name", 64, nonempty=True)
    if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in value):
        raise AffordanceError("child name must contain only ASCII letters, digits, _ or -")
    return value


def validate_children_schema(children, fields):
    """Validate public child declarations against normalized, unbound fields."""
    fields = _normalized_fields(fields)
    if not isinstance(children, list) or len(children) > MAX_FIELDS:
        raise AffordanceError("children must be an array of at most 32 declarations")
    schema = {f["name"]: f for f in fields}
    names = set()
    for child in children:
        if not isinstance(child, dict) or set(child) not in ({"field"}, {"field", "value"}):
            raise AffordanceError("child declaration requires field and optional bound value")
        name = _string(child["field"], "child field", 128, nonempty=True)
        if name in names: raise AffordanceError("duplicate child field")
        names.add(name)
        if "value" in child:
            if name in schema: raise AffordanceError("bound child field cannot also be supplied")
            _child_name(child["value"])
        else:
            field = schema.get(name)
            if field is None or field["type"] != "string" or not 1 <= field["minLength"] <= field["maxLength"] <= 64:
                raise AffordanceError("child field must declare string bounds within 1..64")
            if "example" in field: _child_name(field["example"])
    return copy.deepcopy(children)


def _child_values(children, fields, values):
    """Check explicit form declarations, never inspect or evaluate the program."""
    return [_child_name(child["value"] if "value" in child else values[child["field"]])
            for child in validate_children_schema(children, fields)]


def _metadata(protocol):
    metadata = protocol.get("affordances", {})
    if not isinstance(metadata, dict) or len(metadata) > MAX_ACTIONS:
        raise AffordanceError("affordances must be a command metadata object")
    result = {}
    for command, entry in metadata.items():
        if command not in protocol["commands"]:
            raise AffordanceError("affordance metadata names an absent command")
        if not isinstance(entry, dict) or set(entry) - {"label", "fields", "children"} or "fields" not in entry:
            raise AffordanceError("command metadata requires fields and only optional label/children")
        fields = entry["fields"]
        if not isinstance(fields, dict) or len(fields) > MAX_FIELDS:
            raise AffordanceError("command fields must be an object of at most 32 entries")
        result[command] = {"label": _string(entry.get("label", command), "action label", 256),
                           "fields": [_normalize_field(k, fields[k]) for k in sorted(fields)]}
        if "children" in entry:
            children = entry["children"]
            if not isinstance(children, list) or not 1 <= len(children) <= MAX_FIELDS:
                raise AffordanceError("children requires 1..32 field names")
            for name in children: _string(name, "child field", 128, nonempty=True)
            declarations = [{"field": name} for name in children]
            result[command]["children"] = validate_children_schema(declarations, result[command]["fields"])
    return result


def _describe(view):
    if not isinstance(view, dict) or not isinstance(view.get("root"), dict):
        raise AffordanceError("captured view with an exact root required")
    _string(view.get("object"), "object", nonempty=True)
    root = view["root"]
    protocol = root.get("protocol")
    if not isinstance(protocol, dict) or not isinstance(protocol.get("commands"), dict):
        raise AffordanceError("captured protocol commands missing")
    if type(root.get("version")) is not int or root["version"] < 0:
        raise AffordanceError("captured version must be a natural number")
    program = protocol.get("viewProgram")
    if (view.get("mode") == "raw" and isinstance(program, dict)
            and program.get("profile") == "delvetalk-obend-data-menu-v1"):
        # A failed typed projection is a recovery surface, not a replacement
        # menu synthesized from method metadata. Even malformed metadata must
        # not prevent inspection of the retained program and state.
        return (_string(protocol.get("name", view["object"]), "card title"),
                _string(view.get("reason", "View unavailable; inspect its source and state."), "card prose"), [])
    metadata = _metadata(protocol)
    mode = view.get("mode")
    descriptions = []

    def add(key, label, command, kind, bound=None, observed=None):
        _string(key, "source action ID", nonempty=True)
        _string(command, "command", nonempty=True)
        _string(label, "action label")
        if command not in protocol["commands"]:
            raise AffordanceError("displayed action names an absent command")
        bound = {} if bound is None else copy.deepcopy(bound)
        if not isinstance(bound, dict): raise AffordanceError("bound action input must be an object")
        annotated = command in metadata
        fields = metadata[command]["fields"] if annotated else []
        if annotated: _validate_values(fields, bound, complete=False)
        public = {"id": "a" + str(len(descriptions) + 1),
                  "label": metadata[command]["label"] if annotated and kind == "raw" else label,
                  "command": command, "available": kind != "raw" or annotated,
                  "fields": [copy.deepcopy(f) for f in fields if f["name"] not in bound]}
        if kind == "raw" and not annotated: public["inspectOnly"] = True
        if annotated and "children" in metadata[command]:
            public["children"] = [({**child, "value": _child_name(bound[child["field"]])}
                                   if child["field"] in bound else dict(child))
                                  for child in metadata[command]["children"]]
        if observed is not None:
            if type(observed) is not bool: raise AffordanceError("observed availability must be Boolean")
            public["observedAvailable"] = observed
        descriptions.append({"public": public, "key": key, "kind": kind,
                             "bound": bound, "schema": fields if annotated else None})

    if mode == "room":
        title, prose = view["title"], "\n\n".join(p["text"] for p in view["prose"])
        for action in view["actions"]:
            if action["command"] != "start": raise AffordanceError("unknown room start action")
            add("start", action["text"], "start", "room")
        for choice in view["choices"]:
            add(choice["command"], choice["text"], choice["command"], "room", observed=choice["available"])
    elif mode == "projection":
        data = view["data"]
        title, prose = data["title"], data["prose"]
        if not isinstance(data["actions"], dict): raise AffordanceError("projected actions must be a record")
        spec = importlib.util.spec_from_file_location('affordances_projection', ROOT / 'scene/projection.py')
        projection = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(projection)
        for key in projection.action_order(view):
            action = data["actions"][key]
            if not isinstance(action, dict) or set(action) != {"text", "command", "input"}:
                raise AffordanceError("malformed projected action")
            add(key, action["text"], action["command"], "projection", action["input"])
    elif mode == "raw":
        title, prose = protocol.get("name", view["object"]), protocol.get("description", "")
        for command in sorted(protocol["commands"]): add(command, command, command, "raw")
    else:
        raise AffordanceError("unsupported captured view mode")
    if len(descriptions) > MAX_ACTIONS: raise AffordanceError("too many actions for a card")
    return _string(title, "card title"), _string(prose, "card prose"), descriptions


def card(view):
    """A root-free display; the transport must retain the captured view itself."""
    try:
        title, prose, actions = _describe(view)
        return {"format": FORMAT, "title": title, "prose": prose, "object": view["object"],
                "version": view["root"]["version"], "mode": view["mode"],
                "actions": [a["public"] for a in actions]}
    except AffordanceError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise AffordanceError("malformed captured view: " + str(error)) from error


def request(view, action_id, principal, intent, fields=None):
    """Construct from the retained observation; this function never reads state."""
    _string(principal, "principal", nonempty=True)
    _string(intent, "intent", nonempty=True)
    _, _, actions = _describe(view)
    chosen = next((a for a in actions if a["public"]["id"] == action_id), None)
    if chosen is None: raise AffordanceError("action ID does not belong to this captured card")
    supplied = validate_fields(chosen["public"], {} if fields is None else fields)
    payload = {**copy.deepcopy(chosen["bound"]), **supplied}
    if chosen["schema"] is not None: _validate_values(chosen["schema"], payload)
    if chosen["kind"] == "raw":
        result = {"op": "invoke", "object": view["object"], "principal": principal, "intent": intent,
                  "expected": copy.deepcopy(view["root"]), "command": chosen["public"]["command"], "input": payload}
    else:
        spec = importlib.util.spec_from_file_location("affordances_room", ROOT / "scene/room.py")
        room = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(room)
        result = room.view_request(view, chosen["key"], principal, intent)
        if result["input"] != chosen["bound"]:
            raise AffordanceError("existing request factory changed the captured input")
        result["input"] = payload
    if "children" in chosen["public"]:
        names = _child_values(chosen["public"]["children"], chosen["public"]["fields"], supplied)
        # Repeated values remain a program-level collision; Lean owns admission.
        result["absent"] = list(dict.fromkeys(view["object"] + "/" + name for name in names))
    return result


def allocated_refs(receipt):
    """Copy creation references from an actual committed receipt, without reads.

    These are creation roots, not a claim about the child's current state or law.
    Custody must authenticate the receipt; this pure display helper grants nothing.
    """
    if not isinstance(receipt, dict): raise AffordanceError("receipt must be an object")
    if receipt.get("kind") != "committed": return []
    data = receipt.get("data")
    if not isinstance(data, dict): raise AffordanceError("committed receipt data must be an object")
    allocated = data.get("allocated", {})
    if not isinstance(allocated, dict): raise AffordanceError("allocated roots must be an object")
    result = []
    for name in sorted(allocated):
        _string(name, "allocated object", nonempty=True)
        root = allocated[name]
        if not isinstance(root, dict) or set(root) != {"protocol", "state", "law", "version"} or type(root["version"]) is not int or root["version"] != 0:
            raise AffordanceError("allocated entry must be a creation root")
        result.append({"object": name, "root": copy.deepcopy(root)})
    return result
