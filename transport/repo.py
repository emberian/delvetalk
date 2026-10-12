"""DelveTalk's own repository: the journal as AT Protocol records under did:web:<the world's host>, read only, and,
with a signing key on the box, as a signed repository: commits per journal height and rotation sync commits
over a Merkle search tree of the entries' CIDs, ordered by durable chain epochs.

Mounted by the front (transport/http.py) at /xrpc/<nsid> and /.well-known/did.json. Projections are host
replies carried verbatim; the host decides what a reader sees: an unauthenticated request
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
from copy import deepcopy
from pathlib import Path

from transport.atproto.cbor import CID, block, decode, from_json
from transport.atproto.cbor import car as car_of
from transport.atproto.mst import Tree
from transport.atproto.sign import Key, multikey, tid
from transport.host import PUBLIC
from transport.identity import SLUG
from transport.mirror import NS
from transport.state import State

MIRRORED = ('card', 'page', 'index', 'answer')  # transport/mirror.py renders them, for the PDS and for this façade alike
COLLECTIONS = tuple(NS + c for c in MIRRORED)
PROJECTIONS = ('receipt', 'object', 'source', 'publication', 'grant', 'law')
ENTRY = NS + 'entry'  # the signed repository's one collection: an entry's CID and height under its rev
LIMIT, MAX_LIMIT = 50, 100
CAR = 'application/vnd.ipld.car'
OBJECT_KEY = re.compile(r'([A-Za-z0-9._~:-]+)\.([0-9]+)')  # <object with / as ~>.<version>
# Projections a host op pages by journal height: (op, reply list, key field, subject CID field).
PAGED = {'receipt': ('world-entries', 'entries', 'slug', 'hash'), 'source': ('world-sources', 'sources', 'cid', 'cid'),
         'publication': ('world-publications', 'publications', 'id', 'hash'), 'grant': ('world-grants', 'grants', 'id', 'hash')}
ERRORS = {'unknown': (400, 'RecordNotFound'), 'denied': (403, 'Denied'), 'ambiguous': (400, 'AmbiguousSlug')}
XRPC_ERRORS = json.loads((Path(__file__).resolve().parent / 'static' / 'catalogue.json').read_text())['xrpcErrors']  # name -> {code, when}
NOT_SERVED = f'no signing key on this box: read projections with {NS}getProjection and {NS}listProjections'
NOT_LIVE = 'no live subscription: poll com.atproto.sync.getLatestCommit, then com.atproto.sync.getRepo?since=<your rev>'
TID = re.compile(r'[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}')
MINUTE = 60_000_000  # microseconds: the world's clock counts minutes since the epoch
Height = namedtuple('Height', 'rev hash record commit')  # (CID, bytes); commit None before the current signing epoch


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
    under `online.fg-goose.gsb.entry/<rev>` and the commit {did, version: 3, data: <MST root>, rev, prev: <last commit>},
    rev = TID(clock minute * 60e6 + h), the clock the latest `advance:<minute>` entry set. Every input is in every
    reader's projection of the entry; signing is deterministic over (journal, key, ledger). Epochs raise the
    clock floor before a carry's first entry or after a rotation's height, without changing existing record keys.

    A carried journal continues the heights of the world before (HOST-HANDOFF 5.182): its first entry is height
    `base` + 1, not 1. `heights` and `revs` count positions in this journal (1 the first entry), and a height read
    from the host becomes a position by `position`."""

    def __init__(self, did, key, ledger):
        self.did, self.key, self.tree, self.heights, self.revs, self.clock, self.base = did, key, Tree(), [], {}, 0, 0
        self.ledger_path, self.ledger, self.head = Path(ledger), None, None
        self.written_ledger = None
        self.epochs, self.ready = [], False
        self.lock = threading.Lock()

    def prepare(self, base):
        """Detect chain changes once, using only the first journal height, signing key and durable ledger."""
        self.base = base
        ledger, head = self.ledger, self.ledger['head']
        if ledger['base'] != base:
            if head:
                ledger['epochs'].append({'height': base + 1, 'clock': head['clock'] + 1, 'cause': 'carry'})
            ledger['base'] = base
            # A carry starts an empty tree under the current key, including when both inputs changed.
            ledger['key'] = self.key.did_key
        elif ledger['key'] != self.key.did_key:
            if head:
                ledger['epochs'].append({'height': head['height'], 'clock': head['clock'] + 1, 'cause': 'rotation'})
            ledger['key'] = self.key.did_key
        self.epochs = [e for e in ledger['epochs'] if e['height'] > base]

    def persist(self):
        """Write only a changed ledger, after the signed head exists, while holding the chain lock."""
        if self.head:
            self.ledger['head'] = {'height': self.base + len(self.heights), 'rev': self.head.rev, 'clock': self.clock}
        if self.ledger != self.written_ledger:
            State.write(self.ledger_path, self.ledger)
            self.written_ledger = deepcopy(self.ledger)

    def position(self, height):
        return height - self.base if isinstance(height, int) else None

    def catch_up(self, host):
        """Append every entry past the last height seen; the journal only appends, so nothing else is recomputed."""
        with self.lock:
            while True:
                reply = host.send({'op': 'world-entries', 'principal': PUBLIC, 'after': self.base + len(self.heights), 'limit': MAX_LIMIT})
                if 'entries' not in reply:
                    raise refused(reply)
                if not self.ready:
                    entries = reply['entries']
                    base = entries[0].get('height') if entries else 1
                    if type(base) is not int or base < 1:
                        raise Refusal(503, 'HostUnavailable', 'the journal must begin at a positive height')
                    if self.ledger is None:
                        if self.ledger_path.exists():
                            self.ledger = json.loads(self.ledger_path.read_text())
                            self.written_ledger = deepcopy(self.ledger)
                        else:
                            self.ledger = {'key': self.key.did_key, 'base': base - 1, 'epochs': [], 'head': None}
                    if not entries:
                        self.persist()
                        return None  # no first height yet: an existing ledger cannot be reconciled with an empty page
                    self.prepare(base - 1)
                    self.ready = True
                for entry in reply['entries']:
                    self.add(entry)
                if not reply.get('more') or not reply['entries']:
                    self.persist()
                    return self.head

    def add(self, entry):
        h = self.base + len(self.heights) + 1
        if entry.get('height') != h or not isinstance(entry.get('hash'), str):
            raise Refusal(503, 'HostUnavailable', f"the journal's entry {entry.get('height')} is not height {h} with a hash")
        for epoch in self.epochs:
            if epoch['height'] == h and epoch['cause'] == 'carry':
                self.clock = max(self.clock, epoch['clock'])
        who = entry.get('identity') or {}
        intent = str(who.get('intent', ''))
        if who.get('principal') == 'clock' and intent.startswith('advance:') and intent[8:].isdigit():
            self.clock = max(self.clock, int(intent[8:]))
        rev = tid(self.clock * MINUTE + h)
        record = block({'$type': ENTRY, 'entry': CID.parse(entry['hash']), 'height': h})
        self.tree.append(f'{ENTRY}/{rev}'.encode(), record[0])
        root = self.tree.root()  # node creation heights must be identical even when old commits cannot be signed
        latest = self.epochs[-1] if self.epochs else None
        sign_height = not latest or h > latest['height'] or (h == latest['height'] and latest['cause'] == 'carry')
        commit = self.key.commit(self.did, root, rev, self.head.commit[0] if self.head else None) if sign_height else None
        self.heights.append(Height(rev, entry['hash'], record, commit))
        self.revs[rev] = len(self.heights)
        if commit:
            self.head = self.heights[-1]
        for epoch in self.epochs:
            if epoch['height'] == h and epoch['cause'] == 'rotation':
                self.clock = max(self.clock, epoch['clock'])
                sync_rev = tid(self.clock * MINUTE)
                self.revs[sync_rev] = len(self.heights)
                if epoch is latest:
                    self.head = Height(sync_rev, entry['hash'], record, self.key.commit(self.did, root, sync_rev, None))

    def repo(self, since=None):
        """The CAR of the head commit, the MST and the records; with `since` (a rev), what was added after it."""
        with self.lock:  # the head and the tree together: a catch-up between them would mix two commits
            start = self.revs.get(since, -1) if since else 0
            if start < 0:
                raise Refusal(400, 'InvalidRequest', f'since: no commit here has rev {since}')
            head, nodes = self.head, self.tree.blocks(start)
            return car_of(head.commit[0], [head.commit, *nodes, *(x.record for x in self.heights[start:])])

    def proof(self, h, extra=()):
        """The CAR proving height h's record: the head commit, the MST path to its key, the record (and `extra`)."""
        with self.lock:
            head, path = self.head, self.tree.proof(h - 1)
            return car_of(head.commit[0], [head.commit, *path, self.heights[h - 1].record, *extra])


def world_origin(origin, world):
    """The origin a world's repository is named by: the front's own for the town, else `<world>.<its host>`. An atproto
    did:web is a hostname and never a path (atproto.com/specs/did), so each world is a host of its own (docs/REPO.md)."""
    if world == 'town':
        return origin.rstrip('/')
    parts = urllib.parse.urlsplit(origin)
    return f'{parts.scheme}://{world}.{parts.netloc}'


def world_did(origin, world='town'):
    """-> (did, handle): the did:web of a world's repository and the hostname that is its handle."""
    parts = urllib.parse.urlsplit(world_origin(origin, world))
    return 'did:web:' + parts.netloc.replace(':', '%3A'), parts.hostname


def object_key(oid, tail):
    """`<object with / as ~>.<tail>`: a record key for every id the host creates (`[A-Za-z0-9._:/-]`)."""
    return f"{oid.replace('/', '~')}.{tail}"


class Repo:
    METHODS = {'com.atproto.repo.describeRepo': 'describe', 'com.atproto.repo.listRecords': 'list_records',
               'com.atproto.repo.getRecord': 'get_record', 'com.atproto.sync.getRecord': 'sync_record',
               'com.atproto.sync.getRepo': 'get_repo', 'com.atproto.identity.resolveHandle': 'resolve_handle',
               'com.atproto.sync.getLatestCommit': 'latest_commit', 'com.atproto.sync.getRepoStatus': 'repo_status',
               'com.atproto.sync.listRepos': 'list_repos', 'com.atproto.sync.listBlobs': 'list_blobs',
               'com.atproto.sync.subscribeRepos': 'subscribe',
               NS + 'getProjection': 'get_projection', NS + 'listProjections': 'list_projections'}

    def __init__(self, origin, key=None, world='town', answers=None, ledger=None):
        """`key`: a transport.atproto.sign.Key, or None for an unsigned repository; `world` names its host (`world_origin`);
        `answers` the bridge's answer directory (`State.answers`); `ledger` the durable chain epochs
        (`State.repo_ledger`), required when signing."""
        self.answers = answers
        self.origin = world_origin(origin, world)
        self.did, self.handle = world_did(origin, world)
        if key and ledger is None:
            raise ValueError('a signed repository requires State.repo_ledger')
        self.signed = Signed(self.did, key, ledger) if key else None

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

    def kind(self, q):
        if q.get('kind') not in PROJECTIONS:
            raise Refusal(400, 'InvalidRequest', 'kind must be one of ' + ', '.join(PROJECTIONS))
        return q['kind']

    def paging(self, q):
        limit = q.get('limit', str(LIMIT))
        digits = limit.lstrip('0')
        if not (limit.isascii() and limit.isdigit()) or len(digits) > 3 or not 1 <= int(digits or '0') <= MAX_LIMIT:
            raise Refusal(400, 'InvalidRequest', f'limit must be 1..{MAX_LIMIT}')
        return q.get('cursor'), int(digits), q.get('reverse') == 'true'

    def projection(self, host, kind, key, of, value):
        out = {'kind': kind, 'key': key, **({'of': of} if of else {}), 'value': value}
        if kind == 'receipt' and self.signed:
            self.head(host, {}, None)
            h = self.signed.position(value.get('height'))
            # A receipt retained across a carry need not have a record in this epoch's tree.
            if isinstance(h, int) and 1 <= h <= len(self.signed.heights):
                entry = self.signed.heights[h - 1]
                if entry.hash == of:
                    out['signed'] = f'at://{self.did}/{ENTRY}/{entry.rev}'
        return out

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

    def signed_height(self, host, rkey):
        """The journal position of the requested entry record's rev, excluding rotation sync revs."""
        self.head(host, {}, None)
        h = self.signed.revs.get(rkey) if TID.fullmatch(rkey) else None
        if not isinstance(h, int) or not 1 <= h <= len(self.signed.heights) or self.signed.heights[h - 1].rev != rkey:
            raise Refusal(400, 'RecordNotFound', f'no entry record here has rev {rkey}')
        return h

    def list_records(self, host, q, who):
        self.repo(q)
        collection = self.collection(q)
        cursor, limit, reverse = self.paging(q)
        if collection == 'entry':  # by height; the cursor is the last rev listed
            n, size = len(self.head(host, {}, None) and self.signed.heights), int(limit)
            at = self.signed.revs.get(cursor) if cursor else (n + 1 if reverse else 0)
            if at is None:
                raise Refusal(400, 'InvalidRequest', f'cursor: no commit here has rev {cursor}')
            hs = range(at - 1, max(at - 1 - size, 0), -1) if reverse else range(at + 1, min(at + size, n) + 1)
            more = len(hs) and (hs[-1] > 1 if reverse else hs[-1] < n)
            return {'records': [self.signed_record(h) for h in hs], **({'cursor': self.signed.heights[hs[-1] - 1].rev} if more else {})}
        return self.mirrored_page(host, collection, PUBLIC, cursor, limit, reverse)

    def list_projections(self, host, q, who):
        kind = self.kind(q)
        cursor, limit, reverse = self.paging(q)
        if kind in PAGED:
            op, field, key, cid = PAGED[kind]
            # The host's (height, item) cursor keeps projections sharing an entry from being skipped.
            reply = host.send({'op': op, 'principal': who, 'limit': int(limit), **({'cursor': cursor} if cursor else {}),
                               **({'reverse': True} if reverse else {})})
            if field not in reply:
                raise refused(reply)
            items = reply[field]
            return {'projections': [self.projection(host, kind, i.get(key), i.get(cid), i) for i in items],
                    **({'cursor': reply['cursor']} if reply.get('more') and reply.get('cursor') else {})}
        if reverse:  # objects and laws page by id in byte order, as world-objects lists them
            raise Refusal(400, 'InvalidRequest', f'{NS}{kind} pages by object id and has no reverse order')
        after, mid, k = (cursor or '').partition('#')  # an object id, or `<object id>#<laws of it already listed>` inside a law page
        if mid and not (kind == 'law' and k.isascii() and k.isdigit()):
            raise Refusal(400, 'InvalidRequest', 'cursor: not one this listing gave')
        try:
            skip = int(k or 0)
        except ValueError:
            raise Refusal(400, 'InvalidRequest', 'cursor: not one this listing gave')
        taken, last = [], None
        for oid, listed, record, ended in self.walk(host, who, kind, after, skip, bool(mid)):
            if len(taken) == int(limit):
                return {'projections': taken, 'cursor': last}
            taken.append(record)
            last = oid if ended else f'{oid}#{listed}'
        return {'projections': taken}

    def mirrored(self, host, collection, rkey, who):
        """A record the mirror writes to the PDS, as `who` reads it here (transport/mirror.py), or None."""
        from transport import mirror
        if collection == 'answer':
            return mirror.answer_records(self.answers).get(rkey)
        if collection == 'card':
            return mirror.card_record(host, rkey.replace('~', '/'), who)
        pages = mirror.library_pages(host, who)
        if collection == 'page':
            return next((mirror.page_record(p) for p in pages if p['name'] == rkey), None)
        if rkey != 'self':
            return None
        before = mirror.height(host)
        cards = {oid: c['version'] for oid in mirror.ids(host, who) if (c := mirror.card_record(host, oid, who, paint=False))}
        return mirror.index_record(cards, pages, before, mirror.height(host))

    def mirrored_page(self, host, collection, who, cursor, limit, reverse):
        """Cards by id and pages in shelf order, `limit` a page, the cursor the last key listed."""
        from transport import mirror
        if collection == 'index':
            keys = ['self']
        elif collection == 'answer':
            keys = sorted(mirror.answer_records(self.answers))
        elif collection == 'page':
            keys = [p['name'] for p in mirror.library_pages(host, who)]
        else:
            keys = [mirror.card_key(oid) for oid in mirror.ids(host, who)]
        keys = keys[::-1] if reverse else keys
        start = keys.index(cursor) + 1 if cursor in keys else 0
        if cursor and cursor not in keys:
            raise Refusal(400, 'InvalidRequest', 'cursor: not one this listing gave')
        out, at = [], start
        while at < len(keys) and len(out) < limit:
            value = self.mirrored(host, collection, keys[at], who)
            if value is not None:
                out.append({'uri': f'at://{self.did}/{NS}{collection}/{keys[at]}', 'cid': str(block(from_json(value))[0]), 'value': value})
            at += 1
        return {'records': out, **({'cursor': keys[at - 1]} if at < len(keys) else {})}

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
                    yield oid, 0, self.projection(host, 'object', object_key(oid, item['version']), item.get('stateCid'), item), True
                laws = item.get('laws') or [] if collection == 'law' else []
                for n in range(skip, len(laws)):
                    yield oid, n + 1, self.projection(host, 'law', object_key(oid, laws[n]['name']), None, laws[n]), n + 1 == len(laws)
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
            out = self.signed_record(self.signed_height(host, rkey))
        else:
            value = self.mirrored(host, collection, rkey, PUBLIC)
            if value is None:
                raise Refusal(400, 'RecordNotFound', f'no {NS}{collection} here is {rkey}')
            out = {'uri': f'at://{self.did}/{NS}{collection}/{rkey}', 'cid': str(block(from_json(value))[0]), 'value': value}
        if q.get('cid') and q['cid'] != out['cid']:
            raise Refusal(400, 'RecordNotFound', f"the record at {rkey} has cid {out['cid']}")
        return out

    def get_projection(self, host, q, who):
        kind, key = self.kind(q), q.get('key') or ''
        if not key:
            raise Refusal(400, 'InvalidRequest', 'key is required')
        if kind == 'receipt':
            value = self.entry(host, key, who)['receipt']
            out = self.projection(host, kind, key, value.get('hash'), value)
        elif kind == 'object':
            parsed = OBJECT_KEY.fullmatch(key)
            if not parsed:
                raise Refusal(400, 'InvalidRequest', 'an object projection key is <object with / as ~>.<version>')
            value = self.object(host, parsed[1].replace('~', '/'), int(parsed[2]), who)
            out = self.projection(host, kind, key, value.get('stateCid'), value)
        elif kind == 'source':
            reply = host.send({'op': 'world-source', 'principal': who, 'cid': key})
            if reply.get('status') != 'source':
                raise refused(reply)
            out = self.projection(host, kind, key, key, reply['record'])
        elif kind == 'law':
            oid, dot, name = key.rpartition('.')
            if not dot or not oid or not name:
                raise Refusal(400, 'InvalidRequest', 'a law projection key is <object with / as ~>.<clause>')
            value = self.object(host, oid.replace('~', '/'), None, who)
            clause = next((law for law in value.get('laws', []) if law['name'] == name), None)
            if clause is None:
                raise Refusal(400, 'RecordNotFound', f'no law here is {key}')
            out = self.projection(host, kind, key, None, clause)
        else:
            cursor = None
            while True:
                page = self.list_projections(host, {'kind': kind, 'limit': str(MAX_LIMIT), **({'cursor': cursor} if cursor else {})}, who)
                out = next((row for row in page['projections'] if row['key'] == key), None)
                if out is not None:
                    break
                cursor = page.get('cursor')
                if not cursor:
                    raise Refusal(400, 'RecordNotFound', f'no {kind} here is {key}')
        if q.get('cid') and q['cid'] != out.get('of'):
            raise Refusal(400, 'RecordNotFound', f"the projection at {key} is of {out.get('of')}")
        return out

    def sync_record(self, host, q, who):
        self.repo(q, 'did')
        if self.collection(q) != 'entry':
            raise Refusal(400, 'InvalidRequest', 'only entry records are in the signed tree')
        h = self.signed_height(host, q.get('rkey') or '')
        cid = self.signed.heights[h - 1].hash
        whole = host.send({'op': 'world-entry', 'principal': who, 'hash': cid, 'bytes': True}) if who != PUBLIC else {}
        return self.signed.proof(h, [(CID.parse(cid), bytes.fromhex(whole['bytes']))] if 'bytes' in whole else [])

    # ---- host reads

    def entry(self, host, rkey, who):
        """The host's receipt projection for a slug or entry CID."""
        if SLUG.fullmatch(rkey):
            found = host.send({'op': 'world-resolve', 'principal': who, 'slug': rkey})
            if found.get('status') == 'resolved' and found.get('kind') != 'receipt':
                found = {'status': 'unknown', 'message': f"{rkey} names a {found.get('kind')}, not a receipt"}
            if found.get('status') != 'resolved':
                raise refused(found)
            return {'status': 'receipt', 'receipt': found['receipt']}
        reply = host.send({'op': 'world-entry', 'principal': who, 'hash': rkey})
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
    by the running user and never overwritten; replacing a key starts a new signing epoch. -> its did:key."""
    key, path = Key.generate(curve), st.repo_key
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)  # FileExistsError: replacing a key is a deliberate act
    with os.fdopen(fd, 'wb') as f:
        f.write(key.pem())
        f.flush()
        os.fsync(f.fileno())
    return key.did_key
