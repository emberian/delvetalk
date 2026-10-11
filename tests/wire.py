"""Data on the wire, as every suite writes and reads it, and an independent DAG-CBOR / CID encoder.

Lists cross the wire as `{"tag":"list","items":[...]}` in both directions; the host refuses a
`nil` / `cons` chain on input ("cons chains are no longer accepted on the wire; send a list").
A relation is the variant `rows {items}` (world/lib/Relation.obend).
"""
import base64
import hashlib


def nat(n):
    return {"tag": "natural", "value": str(n)}


def label(s):
    return {"tag": "label", "value": s}


def boolean(value):
    return {"tag": "boolean", "value": value}


def record(**fields):
    return {"tag": "record", "fields": [{"name": k, "value": v} for k, v in fields.items()]}


def empty():
    return record()


def variant(name, payload=None, /, **fields):
    """A variant: its payload given whole, or as the fields of a record."""
    return {"tag": "variant", "label": name, "payload": payload if payload is not None else record(**fields)}


def listing(items):
    return {"tag": "list", "items": list(items)}


def nil():
    return listing([])


def reference(name):
    return record(world=label(""), object=label(name))


def relation(*items):
    """A relation, its rows given in key order."""
    return variant("rows", items=listing(items))


def field(wire, name):
    """The value of the named field of a record on the wire (a state, a row, a payload)."""
    return [f["value"] for f in wire["fields"] if f["name"] == name][0]


def rows(wire):
    """The rows of a relation on the wire, in key order."""
    assert wire["tag"] == "variant" and wire["label"] == "rows", wire
    return field(wire["payload"], "items")["items"]


def cbor_head(major, n):
    if n < 24:
        return bytes([major << 5 | n])
    for info, width in ((24, 1), (25, 2), (26, 4), (27, 8)):
        if n < 1 << (8 * width):
            return bytes([major << 5 | info]) + n.to_bytes(width, "big")
    raise ValueError(n)


def cbor(value):
    """DAG-CBOR of a JSON value: shortest heads, keys sorted by length then bytes."""
    if value is None:
        return b"\xf6"
    if value is True:
        return b"\xf5"
    if value is False:
        return b"\xf4"
    if isinstance(value, int):
        return cbor_head(0, value) if value >= 0 else cbor_head(1, -1 - value)
    if isinstance(value, str):
        raw = value.encode()
        return cbor_head(3, len(raw)) + raw
    if isinstance(value, list):
        return cbor_head(4, len(value)) + b"".join(cbor(v) for v in value)
    keys = sorted(value, key=lambda k: (len(k.encode()), k.encode()))
    return cbor_head(5, len(keys)) + b"".join(cbor(k) + cbor(value[k]) for k in keys)


def cid_of(value):
    """CIDv1, dag-cbor, sha2-256, base32 lower with the `b` prefix."""
    digest = hashlib.sha256(cbor(value)).digest()
    return "b" + base64.b32encode(bytes([1, 0x71, 0x12, 0x20]) + digest).decode().lower().rstrip("=")
