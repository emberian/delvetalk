"""DelveTalk's own repository: the journal as AT Protocol records under did:web:<origin host>, read only, and,
with a signing key on the box, as a signed repository: one commit per journal height over a Merkle search tree
of the entries' CIDs.

Mounted by the front (transport/http.py) at /xrpc/<nsid> and /.well-known/did.json. Every record is a host
reply carried verbatim with `$type` added; the host decides what a reader sees: an unauthenticated request
reads as PUBLIC, a bearer credential as its principal. The signed repository renders what every reader sees
(each entry's height and hash) and signs it with the world's key (`State.repo_key`, made once by `repokey`). docs/REPO.md says what
is served, what is signed, what is not, and the host ops it reads.
"""
import base64
import json
import os
import re
import threading
import urllib.parse
from collections import namedtuple
from pathlib import Path

from transport.atproto.cbor import CID, block, decode
from transport.atproto.cbor import car as car_of
from transport.atproto.mst import Tree
from transport.atproto.sign import Key, multikey, tid
from transport.host import PUBLIC
from transport.identity import SLUG

NS = 'town.delvetalk.'
COLLECTIONS = tuple(NS + c for c in ('receipt', 'object', 'source', 'publication', 'grant', 'law'))
ENTRY = NS + 'entry'  # the signed repository's one collection: an entry's CID and height under its rev
LIMIT, MAX_LIMIT = 50, 100
CAR = 'application/vnd.ipld.car'
OBJECT_KEY = re.compile(r'([A-Za-z0-9._~:-]+)\.([0-9]+)')  # <object with / as ~>.<version>
# Collections a host op pages by journal height: (op, the reply's list, the item's record key, the item's cid).
PAGED = {'receipt': ('world-entries', 'entries', 'slug', 'hash'), 'source': ('world-sources', 'sources', 'cid', 'cid'),
         'publication': ('world-publications', 'publications', 'id', 'hash'), 'grant': ('world-grants', 'grants', 'id', 'hash')}
ERRORS = {'unknown': (400, 'RecordNotFound'), 'denied': (403, 'Denied'), 'ambiguous': (400, 'AmbiguousSlug')}
XRPC_ERRORS = json.loads((Path(__file__).resolve().parent / 'static' / 'catalogue.json').read_text())['xrpcErrors']  # name -> {code, when}
NOT_SERVED = 'no signing key on this box, so no signed MST: page com.atproto.repo.listRecords?collection=' \
             'town.delvetalk.receipt, and fetch each entry\'s block with com.atproto.sync.getRecord'
NOT_LIVE = 'no live subscription: poll com.atproto.sync.getLatestCommit, then com.atproto.sync.getRepo?since=<your rev>'
TID = re.compile(r'[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}')
MINUTE = 60_000_000  # microseconds: the world's clock counts minutes since the epoch
Height = namedtuple('Height', 'rev hash record commit')  # record and commit are (CID, bytes)


class Refusal(Exception):
    def __init__(self, code, error, message, reply=None, hint=None):
        super().__init__(message)
        self.code = code
        self.body = {'error': error, 'message': message, **({'reply': reply} if reply else {}), **({'hint': hint} if hint else {})}


def refused(reply):
    """A host reply that is not a record, as the XRPC error that carries it."""
    host = {'hostUnavailable': 'HostUnavailable', 'hostTimeout': 'HostTimeout'}.get(reply.get('class'))
    code, error = (XRPC_ERRORS[host]['code'], host) if host else ERRORS.get(reply.get('status'), (400, 'InvalidRequest'))
    return Refusal(code, error, reply.get('message') or reply.get('status') or 'no reply', reply)


def car(cid, block):
    """A CARv1 of one block, rooted at it."""
    return car_of(CID.parse(cid), [(CID.parse(cid), block)])


def json_of(v):
    """A DAG-CBOR value in the AT Protocol's JSON form: a link as {$link}, bytes as {$bytes}."""
    if isinstance(v, CID):
        return {'$link': str(v)}
    if isinstance(v, bytes):
        return {'$bytes': base64.b64encode(v).decode().rstrip('=')}
    if isinstance(v, dict):
        return {k: json_of(x) for k, x in v.items()}
    return [json_of(x) for x in v] if isinstance(v, list) else v


class Signed:
    """The journal as a signed repository. Height h adds the record {$type: entry, entry: <hash link>, height: h}
    under `town.delvetalk.entry/<rev>` and the commit {did, version: 3, data: <MST root>, rev, prev: <commit h-1>},
    rev = TID(clock minute * 60e6 + h), the clock the latest `advance:<minute>` entry set. Every input is in every
    reader's projection of the entry; the key signs deterministically, so the chain is a function of the journal.

    A carried journal continues the heights of the world before (HOST-HANDOFF 5.182): its first entry is height
    `base` + 1, not 1. `heights` and `revs` count positions in this journal (1 the first entry), and a height read
    from the host becomes a position by `position`."""

    def __init__(self, did, key):
        self.did, self.key, self.tree, self.heights, self.revs, self.clock, self.base = did, key, Tree(), [], {}, 0, 0
        self.lock = threading.Lock()

    def position(self, height):
        return height - self.base if isinstance(height, int) else None

    def catch_up(self, host):
        """Append every entry past the last height seen; the journal only appends, so nothing else is recomputed."""
        with self.lock:
            while True:
                reply = host.send({'op': 'world-entries', 'principal': PUBLIC, 'after': self.base + len(self.heights), 'limit': MAX_LIMIT})
                if 'entries' not in reply:
                    raise refused(reply)
                for entry in reply['entries']:
                    self.add(entry)
                if not reply.get('more') or not reply['entries']:
                    return self.heights[-1] if self.heights else None

    def add(self, entry):
        if not self.heights and isinstance(entry.get('height'), int) and entry['height'] >= 1:
            self.base = entry['height'] - 1  # the journal's first entry, whatever height a carry began it at
        h = self.base + len(self.heights) + 1
        if entry.get('height') != h or not isinstance(entry.get('hash'), str):
            raise Refusal(503, 'HostUnavailable', f"the journal's entry {entry.get('height')} is not height {h} with a hash")
        who = entry.get('identity') or {}
        intent = str(who.get('intent', ''))
        if who.get('principal') == 'clock' and intent.startswith('advance:') and intent[8:].isdigit():
            self.clock = max(self.clock, int(intent[8:]))
        rev = tid(self.clock * MINUTE + h)
        record = block({'$type': ENTRY, 'entry': CID.parse(entry['hash']), 'height': h})
        self.tree.append(f'{ENTRY}/{rev}'.encode(), record[0])
        commit = self.key.commit(self.did, self.tree.root(), rev, self.heights[-1].commit[0] if self.heights else None)
        self.heights.append(Height(rev, entry['hash'], record, commit))
        self.revs[rev] = len(self.heights)

    def repo(self, since=None):
        """The CAR of the head commit, the MST and the records; with `since` (a rev), what was added after it."""
        start = self.revs.get(since, -1) if since else 0
        if start < 0:
            raise Refusal(400, 'InvalidRequest', f'since: no commit here has rev {since}')
        with self.lock:  # the head and the tree together: a catch-up between them would mix two commits
            head, nodes = self.heights[-1], self.tree.blocks(start)
        return car_of(head.commit[0], [head.commit, *nodes, *(x.record for x in self.heights[start:])])

    def proof(self, h, extra=()):
        """The CAR proving height h's record: the head commit, the MST path to its key, the record (and `extra`)."""
        with self.lock:
            head, path = self.heights[-1], self.tree.proof(h - 1)
        return car_of(head.commit[0], [head.commit, *path, self.heights[h - 1].record, *extra])


def object_key(oid, tail):
    """`<object with / as ~>.<tail>`: a record key for every id the host creates (`[A-Za-z0-9._:/-]`)."""
    return f"{oid.replace('/', '~')}.{tail}"


class Repo:
    METHODS = {'com.atproto.repo.describeRepo': 'describe', 'com.atproto.repo.listRecords': 'list_records',
               'com.atproto.repo.getRecord': 'get_record', 'com.atproto.sync.getRecord': 'sync_record',
               'com.atproto.sync.getRepo': 'get_repo', 'com.atproto.identity.resolveHandle': 'resolve_handle',
               'com.atproto.sync.getLatestCommit': 'latest_commit', 'com.atproto.sync.getRepoStatus': 'repo_status',
               'com.atproto.sync.listRepos': 'list_repos', 'com.atproto.sync.listBlobs': 'list_blobs',
               'com.atproto.sync.subscribeRepos': 'subscribe'}

    def __init__(self, origin, key=None):
        """`key`: a transport.atproto.sign.Key, or None for an unsigned repository."""
        self.origin = origin.rstrip('/')
        parts = urllib.parse.urlsplit(self.origin)
        self.handle, self.did = parts.hostname, 'did:web:' + parts.netloc.replace(':', '%3A')
        self.signed = Signed(self.did, key) if key else None

    def did_document(self):
        key = self.signed and self.signed.key.private.public_key()
        return {'@context': ['https://www.w3.org/ns/did/v1'] + (['https://w3id.org/security/multikey/v1'] if key else []),
                'id': self.did, 'alsoKnownAs': ['at://' + self.handle],
                **({'verificationMethod': [{'id': self.did + '#atproto', 'type': 'Multikey', 'controller': self.did,
                                            'publicKeyMultibase': multikey(key)}]} if key else {}),
                'service': [{'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer', 'serviceEndpoint': self.origin}]}

    def serve(self, host, method, nsid, query, principal):
        """-> (HTTP status, body, content type): body a dict to send as JSON, or the bytes of a CAR."""
        if nsid not in self.METHODS:
            return 501, {'error': 'MethodNotImplemented', 'message': f'{nsid} is not served here; read docs/REPO.md'}, 'application/json'
        if method != 'GET':
            return 405, {'error': 'InvalidRequest', 'message': 'this repository is read-only'}, 'application/json'
        try:
            out = getattr(self, self.METHODS[nsid])(host, query, principal or PUBLIC)
        except Refusal as r:
            return r.code, r.body, 'application/json'
        return 200, out, CAR if isinstance(out, bytes) else 'application/json'

    # ---- parameters

    def repo(self, q, key='repo'):
        if q.get(key) not in (self.did, self.handle):
            raise Refusal(400, 'RepoNotFound', f'this server holds one repository, {self.did}')

    def collection(self, q):
        if q.get('collection') not in COLLECTIONS + (ENTRY,):
            raise Refusal(400, 'InvalidRequest', 'collection must be one of ' + ', '.join(COLLECTIONS + (ENTRY,)))
        return q['collection'][len(NS):]

    def record(self, collection, rkey, cid, item):
        return {'uri': f'at://{self.did}/{NS}{collection}/{rkey}', **({'cid': cid} if cid else {}),
                'value': {'$type': NS + collection, **item}}

    # ---- methods

    def describe(self, host, q, who):
        self.repo(q)
        return {'did': self.did, 'handle': self.handle, 'didDoc': self.did_document(), 'collections': list(COLLECTIONS) + ([ENTRY] if self.signed else []),
                'handleIsCorrect': True}

    def resolve_handle(self, host, q, who):
        if (q.get('handle') or '').lower() != self.handle:
            raise Refusal(400, 'HandleNotFound', f'this server resolves one handle, {self.handle}')
        return {'did': self.did}

    def head(self, host, q, key='did'):
        if key:
            self.repo(q, key)
        if not self.signed:
            raise Refusal(400, 'RepoNotServed', 'this repository has no signing key, so no MST and no commit', hint=NOT_SERVED)
        head = self.signed.catch_up(host)
        if not head:
            raise Refusal(400, 'RepoNotFound', 'the journal is empty')
        return head

    def get_repo(self, host, q, who):
        self.head(host, q)
        return self.signed.repo(q.get('since'))

    def latest_commit(self, host, q, who):
        head = self.head(host, q)
        return {'cid': str(head.commit[0]), 'rev': head.rev}

    def repo_status(self, host, q, who):
        return {'did': self.did, 'active': True, 'rev': self.head(host, q).rev}

    def list_repos(self, host, q, who):
        head = self.head(host, q, None)
        return {'repos': [{'did': self.did, 'head': str(head.commit[0]), 'rev': head.rev, 'active': True}]}

    def list_blobs(self, host, q, who):
        self.repo(q, 'did')
        return {'cids': []}  # the journal holds no blobs: long text is a DAG-CBOR block (labelBlock), not a blob

    def subscribe(self, host, q, who):
        raise Refusal(501, 'MethodNotImplemented', 'com.atproto.sync.subscribeRepos is not served here', hint=NOT_LIVE)

    def signed_height(self, host, rkey, who):
        """The height a receipt key names: a rev (the signed record key), a slug or an entry CID."""
        head = self.head(host, {}, None)
        h = self.signed.revs.get(rkey) if TID.fullmatch(rkey) else self.signed.position(self.entry(host, rkey, who)['receipt'].get('height'))
        if not isinstance(h, int) or not 1 <= h <= len(self.signed.heights):
            raise Refusal(400, 'RecordNotFound', f'no receipt here is {rkey}')
        return h, head

    def list_records(self, host, q, who):
        self.repo(q)
        collection, cursor, reverse = self.collection(q), q.get('cursor'), q.get('reverse') == 'true'
        limit = q.get('limit', str(LIMIT))
        if not (limit.isascii() and limit.isdigit()) or not 1 <= int(limit) <= MAX_LIMIT:
            raise Refusal(400, 'InvalidRequest', f'limit must be 1..{MAX_LIMIT}')
        if collection == 'entry':  # by height; the cursor is the last rev listed
            n, size = len(self.head(host, {}, None) and self.signed.heights), int(limit)
            at = self.signed.revs.get(cursor) if cursor else (n + 1 if reverse else 0)
            if at is None:
                raise Refusal(400, 'InvalidRequest', f'cursor: no commit here has rev {cursor}')
            hs = range(at - 1, max(at - 1 - size, 0), -1) if reverse else range(at + 1, min(at + size, n) + 1)
            more = len(hs) and (hs[-1] > 1 if reverse else hs[-1] < n)
            return {'records': [self.signed_record(h) for h in hs], **({'cursor': self.signed.heights[hs[-1] - 1].rev} if more else {})}
        if collection in PAGED:
            op, field, key, cid = PAGED[collection]
            # The host's (height, item) cursor, opaque here and to clients: records sharing an entry are never skipped.
            reply = host.send({'op': op, 'principal': who, 'limit': int(limit), **({'cursor': cursor} if cursor else {}),
                               **({'reverse': True} if reverse else {})})
            if field not in reply:
                raise refused(reply)
            items = reply[field]
            return {'records': [self.record(collection, i.get(key), i.get(cid), i) for i in items],
                    **({'cursor': reply['cursor']} if reply.get('more') and reply.get('cursor') else {})}
        if reverse:  # objects and laws page by id in byte order, as world-objects lists them
            raise Refusal(400, 'InvalidRequest', f'{NS}{collection} pages by object id and has no reverse order')
        after, mid, k = (cursor or '').partition('#')  # an object id, or `<object id>#<laws of it already listed>` inside a law page
        if mid and not (collection == 'law' and k.isdigit()):
            raise Refusal(400, 'InvalidRequest', 'cursor: not one this listing gave')
        taken, last = [], None
        for oid, listed, record, ended in self.walk(host, who, collection, after, int(k or 0), bool(mid)):
            if len(taken) == int(limit):
                return {'records': taken, 'cursor': last}
            taken.append(record)
            last = oid if ended else f'{oid}#{listed}'
        return {'records': taken}

    def walk(self, host, who, collection, after, skip, inside):
        """(object id, its laws listed so far, record, whether that ends the object) in id order from `after` (exclusive; inside
        an object, that object past its first `skip` laws), following the host's pages as they are read."""
        def page(**q):
            listed = host.send({'op': 'world-objects', 'principal': who, **q})
            if listed.get('status') != 'listed':
                raise refused(listed)
            return listed['ids'], bool(listed.get('more'))
        ids, more = ([after] if after in page(prefix=after)[0] else [], True) if inside else page(**({'after': after} if after else {}))
        while True:
            for oid in ids:
                item = self.object(host, oid, None, who)
                if collection == 'object':
                    yield oid, 0, self.record('object', object_key(oid, item['version']), item.get('stateCid'), item), True
                laws = item.get('laws') or [] if collection == 'law' else []
                for n in range(skip, len(laws)):
                    yield oid, n + 1, self.record('law', object_key(oid, laws[n]['name']), None, laws[n]), n + 1 == len(laws)
                skip = 0
            if not more:
                return
            after = ids[-1] if ids else after
            ids, more = page(after=after)
            if not ids:
                return

    def signed_record(self, h):
        x = self.signed.heights[h - 1]
        return {'uri': f'at://{self.did}/{ENTRY}/{x.rev}', 'cid': str(x.record[0]), 'value': json_of(decode(x.record[1]))}

    def get_record(self, host, q, who):
        self.repo(q)
        collection, rkey = self.collection(q), q.get('rkey') or ''
        if collection == 'entry':
            h = self.signed_height(host, rkey, who)[0] if TID.fullmatch(rkey) else 0
            if not h:
                raise Refusal(400, 'RecordNotFound', f'an entry record key is a rev; {rkey} is not one here')
            out = self.signed_record(h)
            if q.get('cid') and q['cid'] != out['cid']:
                raise Refusal(400, 'RecordNotFound', f"the record at {rkey} has cid {out['cid']}")
            return out
        if collection == 'receipt':
            item = self.entry(host, rkey, who)['receipt']
            cid = item.get('hash')
        elif collection == 'object':
            key = OBJECT_KEY.fullmatch(rkey)
            if not key:
                raise Refusal(400, 'InvalidRequest', 'an object record key is <object with / as ~>.<version>')
            oid, version = key[1].replace('~', '/'), key[2]
            item = self.object(host, oid, int(version), who)
            cid, rkey = item.get('stateCid'), object_key(oid, version)
        elif collection == 'source':
            reply = host.send({'op': 'world-source', 'principal': who, 'cid': rkey})
            if reply.get('status') != 'source':
                raise refused(reply)
            item, cid = reply['record'], rkey
        else:
            raise Refusal(400, 'InvalidRequest', f'{NS}{collection} is listed, not fetched by key: use com.atproto.repo.listRecords')
        if q.get('cid') and q['cid'] != cid:
            raise Refusal(400, 'RecordNotFound', f'the record at {rkey} has cid {cid}')
        return self.record(collection, rkey, cid, item)

    def sync_record(self, host, q, who):
        self.repo(q, 'did')
        if self.collection(q) not in ('receipt', 'entry'):
            raise Refusal(400, 'InvalidRequest', 'only receipts are blocks: an object, source or law record is a projection')
        if self.signed or self.collection(q) == 'entry':  # the proof of the signed record; the entry's own block too when the reader sees it whole
            h, head = self.signed_height(host, q.get('rkey') or '', who)
            cid = self.signed.heights[h - 1].hash
            whole = host.send({'op': 'world-entry', 'principal': who, 'hash': cid, 'bytes': True}) if who != PUBLIC else {}
            return self.signed.proof(h, [(CID.parse(cid), bytes.fromhex(whole['bytes']))] if 'bytes' in whole else [])
        reply = self.entry(host, q.get('rkey') or '', who, whole=True)
        if 'bytes' not in reply:
            raise Refusal(403, 'Denied', "only the identity's own principal reads an entry whole; "
                                         'a projection is not the block its CID names', reply)
        return car(reply['receipt']['hash'], bytes.fromhex(reply['bytes']))

    # ---- host reads

    def entry(self, host, rkey, who, whole=False):
        """The host's {status: receipt, receipt, bytes?} for a slug or an entry CID."""
        if SLUG.fullmatch(rkey):
            found = host.send({'op': 'world-resolve', 'principal': who, 'slug': rkey})
            if found.get('status') == 'resolved' and found.get('kind') != 'receipt':
                found = {'status': 'unknown', 'message': f"{rkey} names a {found.get('kind')}, not a receipt"}
            if found.get('status') != 'resolved':
                raise refused(found)
            if not whole:
                return {'status': 'receipt', 'receipt': found['receipt']}
            rkey = found['cid']
        reply = host.send({'op': 'world-entry', 'principal': who, 'hash': rkey, **({'bytes': True} if whole else {})})
        if reply.get('status') != 'receipt':
            raise refused(reply)
        return reply

    def object(self, host, oid, version, who):
        reply = host.send({'op': 'world-object', 'principal': who, 'object': oid, **({} if version is None else {'version': version})})
        if reply.get('status') != 'object':
            raise refused(reply)
        return reply['record']


def make_key(st, curve='secp256k1'):
    """The world's signing key (docs/REPO.md "The key"), made once: a PKCS#8 PEM at `State.repo_key`, created mode 0400
    by the running user and never overwritten, since a new key re-signs every commit. -> the did:key it names."""
    key, path = Key.generate(curve), st.repo_key
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)  # FileExistsError: replacing a key is a deliberate act
    with os.fdopen(fd, 'wb') as f:
        f.write(key.pem())
        f.flush()
        os.fsync(f.fileno())
    return key.did_key
