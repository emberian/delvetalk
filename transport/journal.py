"""A journal as the host writes it (HOST-HANDOFF §3): the chain, one link per line `{height, previous, hash,
at, bytes}`, and beside it `<journal>.blocks`, the block store, where each entry's canonical DAG-CBOR record
(the entry without `hash`, whose CID is the `hash`) lies at `at`. Read only: the host is the one writer, and
`delvetalk-obend` the one checker (`world-open {verify: true}`).
"""
import json
from pathlib import Path

from transport.atproto.cbor import decode


def links(path):
    """The chain's links, in height order; a torn final line is left out."""
    text = Path(path).read_text() if Path(path).exists() else ''
    return [json.loads(line) for line in text.split('\n')[:-1]]


def _plain(v):
    """A record's value as JSON: a big natural (a CBOR byte string) as the integer it is."""
    if isinstance(v, bytes):
        return int.from_bytes(v, 'big')
    if isinstance(v, list):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    return v


def records(path):
    """Each link with its record's bytes."""
    chain = links(path)
    if not chain:
        return []
    store = Path(str(path) + '.blocks').read_bytes()
    return [(link, store[link['at']:link['at'] + link['bytes']]) for link in chain]


def tail(path, n, before=None):
    """The newest `n` entries (below height `before`, when given), whole, oldest first: read from the end of the chain,
    and only their records from the store."""
    p = Path(path)
    if not p.exists():
        return []
    if before is None:
        size, window = p.stat().st_size, n * 512  # a link is under 300 bytes
        with open(p, 'rb') as f:
            f.seek(max(0, size - window))
            lines = f.read().split(b'\n')[:-1]
        if size > window:
            lines = lines[1:]  # the first may be a link cut by the seek
        chosen = [json.loads(l) for l in lines[-n:]]
    else:
        chosen = [l for l in links(p) if l['height'] < before][-n:]
    return read(path, chosen)


def read(path, chosen):
    """The entries `chosen` (links of the chain at `path`), whole, each record read from the store alone."""
    out = []
    with open(str(path) + '.blocks', 'rb') as store:
        for link in chosen:
            store.seek(link['at'])
            out.append(dict(_plain(decode(store.read(link['bytes']))), hash=link['hash'], bytes=link['bytes']))
    return out


def entries(path):
    """Every entry, whole, its `hash` restored."""
    return [dict(_plain(decode(raw)), hash=link['hash']) for link, raw in records(path)]


def size(path):
    """The journal's bytes: the chain and the block store."""
    return sum(p.stat().st_size for p in (Path(path), Path(str(path) + '.blocks')) if p.exists())


def copy(src, dst, height=None):
    """A copy of the journal at `src` (its chain and its block store) at `dst`; with `height`, only the chain's
    first `height` links (the store's later records are then bytes no link names, which nothing reads)."""
    chain = Path(src).read_text().split('\n')[:-1]
    if height is not None:
        chain = chain[:height]
    Path(str(dst) + '.blocks').write_bytes(Path(str(src) + '.blocks').read_bytes() if Path(str(src) + '.blocks').exists() else b'')
    Path(dst).write_text(''.join(line + '\n' for line in chain))
