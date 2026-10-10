"""DAG-CBOR as the AT Protocol data model fixes it (atproto.com/specs/data-model): canonical form, CID links as
tag 42, no floats; CIDv1 (dag-cbor codec, sha-256 multihash); CAR v1 framing.

`encode` takes None, bool, int, str, bytes, list, dict with str keys, and CID; `decode` gives the same back and
refuses anything a canonical encoder could not have written.
"""
import base64
import hashlib

DAG_CBOR, SHA256 = 0x71, 0x12


class CID(bytes):
    """A binary CIDv1. str() is the base32 multibase form, `b...`."""

    @classmethod
    def of(cls, block, codec=DAG_CBOR):
        return cls(bytes([1, codec, SHA256, 32]) + hashlib.sha256(block).digest())

    @classmethod
    def parse(cls, text):
        if not text.startswith('b'):
            raise ValueError(f'not a base32 CID: {text!r}')
        raw = base64.b32decode(text[1:].upper() + '=' * (-len(text[1:]) % 8))
        if raw[0] != 1 or len(raw) != 36 or raw[2:4] != bytes([SHA256, 32]):
            raise ValueError(f'not a CIDv1 with a sha-256 multihash: {text!r}')
        return cls(raw)

    def __str__(self):
        return 'b' + base64.b32encode(self).decode().lower().rstrip('=')

    def __repr__(self):
        return f'CID({self})'


def _head(major, n):
    if n < 24:
        return bytes([major << 5 | n])
    for info, width in ((24, 1), (25, 2), (26, 4), (27, 8)):
        if n < 1 << (8 * width):
            return bytes([major << 5 | info]) + n.to_bytes(width, 'big')
    raise ValueError('integer out of range')


def _key(k):
    b = k.encode()
    return len(b), b


def encode(v):
    if v is None:
        return b'\xf6'
    if v is True or v is False:
        return b'\xf5' if v else b'\xf4'
    if isinstance(v, int):
        if not -(1 << 63) <= v < 1 << 64:
            raise ValueError('integer out of range')
        return _head(0, v) if v >= 0 else _head(1, -1 - v)
    if isinstance(v, CID):
        return b'\xd8\x2a' + _head(2, len(v) + 1) + b'\x00' + v
    if isinstance(v, (bytes, bytearray)):
        return _head(2, len(v)) + bytes(v)
    if isinstance(v, str):
        b = v.encode()
        return _head(3, len(b)) + b
    if isinstance(v, (list, tuple)):
        return _head(4, len(v)) + b''.join(map(encode, v))
    if isinstance(v, dict):
        if not all(isinstance(k, str) for k in v):
            raise ValueError('map keys must be strings')
        keys = sorted(v, key=_key)
        return _head(5, len(v)) + b''.join(encode(k) + encode(v[k]) for k in keys)
    raise ValueError(f'no DAG-CBOR form for {type(v).__name__}')


def decode(data):
    """The one value `data` holds, all of it."""
    v, i = _decode(memoryview(data), 0)
    if i != len(data):
        raise ValueError('trailing bytes')
    return v


def _decode(d, i):
    major, info = d[i] >> 5, d[i] & 31
    i += 1
    if info < 24:
        n = info
    elif info <= 27:
        width = 1 << (info - 24)
        n = int.from_bytes(d[i:i + width], 'big')
        i += width
        if n < (24 if width == 1 else 1 << (4 * width)):
            raise ValueError('a head not in its shortest form')
    else:
        raise ValueError('indefinite length or reserved head')
    if major == 0:
        return n, i
    if major == 1:
        return -1 - n, i
    if major in (2, 3):
        raw = bytes(d[i:i + n])
        if len(raw) != n:
            raise ValueError('truncated')
        return (raw if major == 2 else raw.decode()), i + n
    if major == 4:
        out = []
        for _ in range(n):
            v, i = _decode(d, i)
            out.append(v)
        return out, i
    if major == 5:
        out, last = {}, None
        for _ in range(n):
            k, i = _decode(d, i)
            if not isinstance(k, str) or (last is not None and _key(k) <= _key(last)):
                raise ValueError('map keys not strings in canonical order')
            out[k], i = _decode(d, i)
            last = k
        return out, i
    if major == 6:
        if n != 42:
            raise ValueError(f'tag {n}: only 42, a CID link')
        raw, i = _decode(d, i)
        if not isinstance(raw, bytes) or raw[:1] != b'\x00':
            raise ValueError('a CID link is a byte string starting 0x00')
        return CID(raw[1:]), i
    if n in (20, 21, 22):
        return {20: False, 21: True, 22: None}[n], i
    raise ValueError('floats and other simple values are not DAG-CBOR here')


def block(value):
    """-> (CID, bytes): a value's canonical block."""
    data = encode(value)
    return CID.of(data), data


def varint(n):
    out = bytearray()
    while True:
        out.append((n & 0x7f) | (0x80 if n > 0x7f else 0))
        n >>= 7
        if not n:
            return bytes(out)


def car(root, blocks):
    """A CAR v1: the header {roots: [root], version: 1}, then each (cid, bytes) block, in order."""
    header = encode({'roots': [root], 'version': 1})
    return varint(len(header)) + header + b''.join(varint(len(c) + len(b)) + c + b for c, b in blocks)


def read_car(data):
    """-> (roots, {CID: bytes}), checking each block hashes to its CID."""
    def uvarint(i):
        n = shift = 0
        while True:
            b = data[i]
            i += 1
            n |= (b & 0x7f) << shift
            shift += 7
            if b < 0x80:
                return n, i
    n, i = uvarint(0)
    header = decode(data[i:i + n])
    if header.get('version') != 1:
        raise ValueError('not a CAR v1')
    i += n
    blocks = {}
    while i < len(data):
        n, i = uvarint(i)
        cid, body = CID(data[i:i + 36]), bytes(data[i + 36:i + n])
        if CID.of(body, cid[1]) != cid:
            raise ValueError(f'block {cid} does not hash to its CID')
        blocks[cid] = body
        i += n
    return header['roots'], blocks
