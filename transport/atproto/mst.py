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

from transport.atproto.cbor import block, decode


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
        self.by_cid = {}  # the same cached blocks, addressed for inversion's partial-tree reads
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
            self.by_cid = {v[0]: v[1] for v in self.nodes.values()}
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
        self.by_cid[cid] = data
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


def find(blocks, root, key):
    """The value CID at `key` (bytes) in the tree rooted at `root`, walked through `blocks` ({CID: bytes}, each already
    checked against its CID, as `cbor.read_car` gives them); None when the walk shows the key absent. A node the walk
    needs and `blocks` lacks is a KeyError: a proof that does not reach the key proves nothing."""
    node = root
    while node is not None:
        here, prev = decode(blocks[node]), b''
        below = here['l']
        for e in here['e']:
            full = prev[:e['p']] + e['k']
            if full == key:
                return e['v']
            if key < full:
                break
            below, prev = e['t'], full
        node = below
    return None


class _Inverse:
    """Persistent edits on a partial MST. Reading a CID records the original node needed by a consumer;
    new nodes are local calculations. Opaque branches are only opened along edits, splits and merges.
    """
    def __init__(self, read):
        self.read, self.used, self.made = read, {}, {}

    def node(self, cid):
        if cid is None:
            return [], [None]
        data = self.made.get(cid)
        if data is None:
            data = self.used.setdefault(cid, self.read(cid))
        node, keys, previous = decode(data), [], b''
        for e in node['e']:
            previous = previous[:e['p']] + e['k']
            keys.append((previous, e['v']))
        return keys, [node['l'], *(e['t'] for e in node['e'])]

    def write(self, keys, children):
        if not keys and children[0] is None:
            return None
        entries, previous = [], b''
        for (key, value), child in zip(keys, children[1:]):
            p = common_prefix(previous, key)
            entries.append({'p': p, 'k': key[p:], 'v': value, 't': child})
            previous = key
        cid, data = block({'l': children[0], 'e': entries})
        self.made[cid] = data
        return cid

    def split(self, cid, key):
        if cid is None:
            return None, None
        keys, children = self.node(cid)
        i = bisect.bisect_left([k for k, _ in keys], key)
        left, right = self.split(children[i], key)
        return (self.write(keys[:i], [*children[:i], left]),
                self.write(keys[i:], [right, *children[i + 1:]]))

    def merge(self, left, right):
        if left is None or right is None:
            return right if left is None else left
        a, ac = self.node(left)
        b, bc = self.node(right)
        middle = self.merge(ac[-1], bc[0])
        return self.write(a + b, [*ac[:-1], middle, *bc[1:]])

    def edit(self, cid, key, value, level):
        keys, children = self.node(cid)
        i = bisect.bisect_left([k for k, _ in keys], key)
        if i < len(keys) and keys[i][0] == key:
            if value is None:
                middle = self.merge(children[i], children[i + 1])
                return self.write(keys[:i] + keys[i + 1:], [*children[:i], middle, *children[i + 2:]])
            keys[i] = key, value
        elif value is not None and layer(key) == level:
            a, b = self.split(children[i], key)
            keys.insert(i, (key, value))
            children[i:i + 1] = [a, b]
        else:
            if level < 0:
                raise ValueError('inverse operation does not reach its key')
            children[i] = self.edit(children[i], key, value, level - 1)
        return self.write(keys, children)

    def top(self, cid):
        keys, children = self.node(cid)
        return layer(keys[0][0]) if keys else (1 + self.top(children[0]) if children[0] else 0)

    def apply(self, root, op):
        key = op['path'].encode()
        value = None if op['action'] == 'create' else op['prev']
        level, target = self.top(root), layer(key)
        if value is not None and target > level:
            a, b = self.split(root, key)
            for _ in range(level + 1, target):
                a = self.write([], [a]) if a else None
                b = self.write([], [b]) if b else None
            root = self.write([(key, value)], [a, b])
        else:
            root = self.edit(root, key, value, level)
        while root:
            keys, children = self.node(root)
            if keys:
                break
            root = children[0]
        return root


def invert(tree, ops):
    """Undo ops against Tree's new root, returning (previous root or None, exactly the original node
    blocks read). Includes the new paths and neighbours touched by a merge or root collapse. Records
    for creates/updates are added by the event builder; inversion needs only their links, including `prev`.
    The journal Tree still only appends; general inverse edits are confined to this partial-tree walk.
    """
    root = tree.root()
    inverse = _Inverse(tree.by_cid.__getitem__)
    if not ops:
        keys, children = inverse.node(root)
        if not keys and children[0] is None:
            root = None
    for op in reversed(ops):
        if op['action'] not in ('create', 'update', 'delete'):
            raise ValueError('unknown record operation')
        root = inverse.apply(root, op)
    return root, list(inverse.used.items())
