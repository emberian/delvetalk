"""The repository's Merkle search tree (atproto.com/specs/repository, "MST Structure"), grown by appending.

A key's layer is the count of leading zero bits of its sha-256, halved (fanout 4). A node at layer L holds the
keys of its range whose layer is L, in order, with links to layer L-1 subtrees for the gaps between them:
`{l, e: [{p, k, v, t}]}`, keys prefix-compressed within the node. The root is the node at the highest layer;
an empty tree is one node with no entries; empty intermediate nodes are kept.

The journal only appends, and its keys (TIDs) increase, so a key's position never moves: the subtree over
positions [i, j) at layer L is the same block for every later tree, and is cached under (L, i, j). A new key
recomputes only the nodes on the tree's right edge.
"""
import bisect
import hashlib

from transport.atproto.cbor import block


def layer(key):
    h, zeros = hashlib.sha256(key).digest(), 0
    for byte in h:
        if byte:
            zeros += 8 - byte.bit_length()
            break
        zeros += 8
    return zeros // 2


def common_prefix(a, b):
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


class Tree:
    def __init__(self):
        self.keys, self.values, self.layers = [], [], []
        self.at = {}  # layer -> the positions of the keys at that layer, ascending
        self.nodes = {}  # (L, i, j) -> (cid, bytes, child (L, i, j)s, the key count when it was made)
        self.live = 0

    def append(self, key, value):
        """Add `key` (bytes, after every key held) with `value` (a CID)."""
        if self.keys and key <= self.keys[-1]:
            raise ValueError('keys are appended in increasing order')
        self.keys.append(key)
        self.values.append(value)
        self.layers.append(layer(key))
        self.at.setdefault(self.layers[-1], []).append(len(self.keys) - 1)

    def top(self):
        return (max(self.layers), 0, len(self.keys)) if self.keys else (0, 0, 0)

    def root(self):
        """The root node's CID, caching every node made; nodes no longer in the tree are dropped now and then."""
        cid = self._node(*self.top())
        if len(self.nodes) > 2 * self.live + 64:
            keep = set(self._walk(self.top()))
            self.nodes = {k: v for k, v in self.nodes.items() if k in keep}
            self.live = len(self.nodes)
        return cid

    def _entries(self, L, i, j):
        """Positions of layer-L keys in [i, j)."""
        at = self.at.get(L, [])
        return at[bisect.bisect_left(at, i):bisect.bisect_left(at, j)]

    def _node(self, L, i, j):
        got = self.nodes.get((L, i, j))
        if got:
            return got[0]
        here, children, entries, prev = self._entries(L, i, j), [], [], b''

        def sub(a, b):
            if a == b:
                return None
            children.append((L - 1, a, b))
            return self._node(L - 1, a, b)
        left = sub(i, here[0] if here else j)
        for n, p in enumerate(here):
            key = self.keys[p]
            shared = common_prefix(prev, key)
            entries.append({'p': shared, 'k': key[shared:], 'v': self.values[p],
                            't': sub(p + 1, here[n + 1] if n + 1 < len(here) else j)})
            prev = key
        cid, data = block({'l': left, 'e': entries})
        self.nodes[(L, i, j)] = (cid, data, children, len(self.keys))
        return cid

    def _walk(self, start):
        stack = [start]
        while stack:
            k = stack.pop()
            yield k
            stack += self.nodes[k][2]

    def blocks(self, since=0):
        """Every node block of the current tree made after the tree held `since` keys, as (cid, bytes)."""
        self.root()
        return [self.nodes[k][:2] for k in self._walk(self.top()) if self.nodes[k][3] > since]

    def proof(self, position):
        """The node blocks from the root down to the node holding the key at `position`."""
        self.root()
        L, i, j = self.top()
        out = []
        while True:
            out.append(self.nodes[(L, i, j)][:2])
            here = self._entries(L, i, j)
            if position in here:
                return out
            n = bisect.bisect_left(here, position)
            i, j, L = (here[n - 1] + 1 if n else i), (here[n] if n < len(here) else j), L - 1
