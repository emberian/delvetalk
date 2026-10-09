"""Helpers shared by the suites: an independent DAG-CBOR / CID encoder.

Lists cross the wire as `{"tag":"list","items":[...]}` in both directions; the host refuses a
`nil` / `cons` chain on input ("cons chains are no longer accepted on the wire; send a list").
"""
import base64
import hashlib


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
