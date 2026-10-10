"""DelveTalk's own repository: the journal as AT Protocol records under did:web:<origin host>, read only.

Mounted by the front (transport/http.py) at /xrpc/<nsid> and /.well-known/did.json. Every record is a host
reply carried verbatim with `$type` added; the host decides what a reader sees: an unauthenticated request
reads as PUBLIC, a bearer credential as its principal. docs/REPO.md says what is served, what is not, and
the host ops it reads.
"""
import base64
import json
import re
import urllib.parse
from pathlib import Path

NS = 'town.delvetalk.'
COLLECTIONS = tuple(NS + c for c in ('receipt', 'object', 'source', 'publication', 'grant', 'law'))
PUBLIC = 'anonymous'  # the reader an unauthenticated request is; the front's object page reads as it too
LIMIT, MAX_LIMIT = 50, 100
CAR = 'application/vnd.ipld.car'
OBJECT_KEY = re.compile(r'([A-Za-z0-9._~:-]+)\.([0-9]+)')  # <object with / as ~>.<version>
SLUG = re.compile(r'(?:[bdfghjklmnprstvz][aiou]){2}[bdfghjklmnprstvz]-(?:[bdfghjklmnprstvz][aiou]){2}[bdfghjklmnprstvz]')
# Collections a host op pages by journal height: (op, the reply's list, the item's record key, the item's cid).
PAGED = {'receipt': ('world-entries', 'entries', 'slug', 'hash'), 'source': ('world-sources', 'sources', 'cid', 'cid'),
         'publication': ('world-publications', 'publications', 'id', 'hash'), 'grant': ('world-grants', 'grants', 'id', 'hash')}
ERRORS = {'unknown': (400, 'RecordNotFound'), 'denied': (403, 'Denied'), 'ambiguous': (400, 'AmbiguousSlug')}
XRPC_ERRORS = json.loads((Path(__file__).resolve().parent / 'static' / 'catalogue.json').read_text())['xrpcErrors']  # name -> {code, when}
NOT_SERVED = 'the chain is served entry by entry, not as a signed MST: page com.atproto.repo.listRecords?collection=' \
             'town.delvetalk.receipt, and fetch each entry\'s block with com.atproto.sync.getRecord'


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


def varint(n):
    out = bytearray()
    while True:
        out.append((n & 0x7f) | (0x80 if n > 0x7f else 0))
        n >>= 7
        if not n:
            return bytes(out)


def car(cid, block):
    """A CARv1 of one block: the header {roots: [cid], version: 1} in DAG-CBOR, then the block under its binary CID."""
    text = cid[1:]
    raw = base64.b32decode(text.upper() + '=' * (-len(text) % 8))
    link = b'\xd8\x2a\x58' + bytes([len(raw) + 1]) + b'\x00' + raw  # tag 42: a byte string, 0x00 then the binary CID
    header = b'\xa2\x65roots\x81' + link + b'\x67version\x01'
    return varint(len(header)) + header + varint(len(raw) + len(block)) + raw + block


def object_key(oid, tail):
    """`<object with / as ~>.<tail>`: a record key for every id the host creates (`[A-Za-z0-9._:/-]`)."""
    return f"{oid.replace('/', '~')}.{tail}"


class Repo:
    METHODS = {'com.atproto.repo.describeRepo': 'describe', 'com.atproto.repo.listRecords': 'list_records',
               'com.atproto.repo.getRecord': 'get_record', 'com.atproto.sync.getRecord': 'sync_record',
               'com.atproto.sync.getRepo': 'get_repo', 'com.atproto.identity.resolveHandle': 'resolve_handle'}

    def __init__(self, origin):
        self.origin = origin.rstrip('/')
        parts = urllib.parse.urlsplit(self.origin)
        self.handle, self.did = parts.hostname, 'did:web:' + parts.netloc.replace(':', '%3A')

    def did_document(self):
        return {'@context': ['https://www.w3.org/ns/did/v1'], 'id': self.did, 'alsoKnownAs': ['at://' + self.handle],
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
        if q.get('collection') not in COLLECTIONS:
            raise Refusal(400, 'InvalidRequest', 'collection must be one of ' + ', '.join(COLLECTIONS))
        return q['collection'][len(NS):]

    def record(self, collection, rkey, cid, item):
        return {'uri': f'at://{self.did}/{NS}{collection}/{rkey}', **({'cid': cid} if cid else {}),
                'value': {'$type': NS + collection, **item}}

    # ---- methods

    def describe(self, host, q, who):
        self.repo(q)
        return {'did': self.did, 'handle': self.handle, 'didDoc': self.did_document(), 'collections': list(COLLECTIONS),
                'handleIsCorrect': True}

    def resolve_handle(self, host, q, who):
        if (q.get('handle') or '').lower() != self.handle:
            raise Refusal(400, 'HandleNotFound', f'this server resolves one handle, {self.handle}')
        return {'did': self.did}

    def get_repo(self, host, q, who):
        raise Refusal(400, 'RepoNotServed', 'this repository has no Merkle search tree and no signed commit', hint=NOT_SERVED)

    def list_records(self, host, q, who):
        self.repo(q)
        collection, cursor, reverse = self.collection(q), q.get('cursor'), q.get('reverse') == 'true'
        limit = q.get('limit', str(LIMIT))
        if not (limit.isascii() and limit.isdigit()) or not 1 <= int(limit) <= MAX_LIMIT:
            raise Refusal(400, 'InvalidRequest', f'limit must be 1..{MAX_LIMIT}')
        if collection in PAGED:
            op, field, key, cid = PAGED[collection]
            if cursor is not None and not (cursor.isascii() and cursor.isdigit()):
                raise Refusal(400, 'InvalidRequest', 'the cursor is a journal height')
            page = {'before' if reverse else 'after': int(cursor)} if cursor else {}
            reply = host.send({'op': op, 'principal': who, 'limit': int(limit), **page, **({'reverse': True} if reverse else {})})
            if field not in reply:
                raise refused(reply)
            items = reply[field]
            return {'records': [self.record(collection, i.get(key), i.get(cid), i) for i in items],
                    **({'cursor': str(items[-1]['height'])} if reply.get('more') and items else {})}
        if reverse:  # objects and laws page by id in byte order, as world-objects lists them
            raise Refusal(400, 'InvalidRequest', f'{NS}{collection} pages by object id and has no reverse order')
        listed = host.send({'op': 'world-objects', 'principal': who, **({'after': cursor} if cursor else {})})
        if listed.get('status') != 'listed':
            raise refused(listed)
        records = []
        for oid in listed['ids']:
            item = self.object(host, oid, None, who)
            if collection == 'object':
                records.append(self.record('object', object_key(oid, item['version']), item.get('stateCid'), item))
            else:
                records += [self.record('law', object_key(oid, law['name']), None, law) for law in item.get('laws') or []]
        return {'records': records, **({'cursor': listed['ids'][-1]} if listed.get('more') and listed['ids'] else {})}

    def get_record(self, host, q, who):
        self.repo(q)
        collection, rkey = self.collection(q), q.get('rkey') or ''
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
        if self.collection(q) != 'receipt':
            raise Refusal(400, 'InvalidRequest', 'only receipts are blocks: an object, source or law record is a projection')
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
