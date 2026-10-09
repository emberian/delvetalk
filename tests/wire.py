"""Helpers shared by the suites: the legacy list shape and an independent DAG-CBOR / CID encoder.

`relist` turns the wire's `{"tag":"list","items":[...]}` back into the `nil` / `cons` chain that
older tests walk. The host emits arrays now and still accepts the chain on input for one release;
suites that read replies through a Host helper see the chain until they read arrays directly.
"""
import base64
import hashlib
import sys

sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))  # a legacy chain is one level per element


def relist(node):
    if isinstance(node, list):
        return [relist(x) for x in node]
    if not isinstance(node, dict):
        return node
    if node.get("tag") == "list" and isinstance(node.get("items"), list):
        out = {"tag": "variant", "label": "nil", "payload": {"tag": "record", "fields": []}}
        for item in reversed(node["items"]):
            out = {"tag": "variant", "label": "cons", "payload": {"tag": "record", "fields": [
                {"name": "head", "value": relist(item)}, {"name": "tail", "value": out}]}}
        return out
    return {k: relist(v) for k, v in node.items()}


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
