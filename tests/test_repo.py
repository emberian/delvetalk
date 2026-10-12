"""The journal as a read-only AT Protocol repository over a real `serve`: projections by slug and CID agree
with the host, blocks hash to their CIDs, private records stay private.

Evidence for FOUNDATION §2 Journal, §7 (layer: transport).

The read-only AT Protocol repository (transport/repo.py, docs/REPO.md) against a real `serve`: a Garden, a
planting, a refusal, a publication and a private counter; projections keep the host's authority and cursors.

Refuted by: a receipt read by slug, by CID and by world-receipt differing; a sync CAR whose block does not
hash to the entry's CID (checked with this file's own DAG-CBOR decoder); a private object's record served to
the public reader or refused to its owner; a cursor that skips or repeats an entry; did.json naming another DID.

The signed repository (transport/atproto/, `Signed` in transport/repo.py) against the AT Protocol interop
vectors (tests/fixtures/atproto/, bluesky-social/atproto-interop-tests at 056e5741) and a fake world on
loopback. Refuted by: a vector's key layer, prefix, DAG-CBOR bytes, CID, MST root, did:key or signature verdict
differing; a getRepo CAR with a block not hashing to its CID, a commit whose signature the DID document's key
does not verify, an MST whose keys are out of order or at the wrong layer, or that a fresh tree over its leaves
does not reproduce; a getRecord proof that does not reach the record from the signed root; an entry block
served to the public; a commit chain whose prev is not the previous head, or that two processes sign differently.
"""
import base64
import hashlib
import http.client
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from tests.host import serve, served
from tests.test_chain import town_garden
from tests.test_http import DID, Provider
from transport.state import State
from transport import delve, identity
from transport.config import Config, LIBRARY
from transport.atproto import sign
from transport.atproto.cbor import CID, block, decode, encode, read_car
from transport.atproto.mst import Tree, common_prefix, layer, find
from transport.repo import Repo
from transport.host import HostClient
from transport.http import Front
from transport.config import ORIGIN
from tests.wire import label, nat, record
from tests.bend import counter_modules

# Signing is ECDSA with RFC 6979 nonces (`deterministic_signing`), which cryptography has from 43.0.0.
CRYPTOGRAPHY = tuple(int(x) for x in __import__('cryptography').__version__.split('.')[:2])
signs = unittest.skipIf(CRYPTOGRAPHY < (43, 0), 'deterministic ECDSA needs cryptography >= 43.0 (this is %d.%d); persvati has it' % CRYPTOGRAPHY)


HOST = urllib.parse.urlsplit(ORIGIN).netloc
REPO = 'did:web:' + HOST
NS = 'online.fg-goose.gsb.'


def cbor(data, i=0):
    """-> (value, next index): DAG-CBOR as a CAR header and an entry use it, refusing a non-canonical form."""
    major, info = data[i] >> 5, data[i] & 31
    i += 1
    n = info
    if 24 <= info <= 27:
        width = 1 << (info - 24)
        n = int.from_bytes(data[i:i + width], 'big')
        i += width
        assert n >= (24 if width == 1 else 1 << (4 * width)), 'a head is not in its shortest form'
    elif info > 27:
        raise ValueError('indefinite length')
    if major == 0:
        return n, i
    if major == 1:
        return -1 - n, i
    if major in (2, 3):
        raw = bytes(data[i:i + n])
        return (raw if major == 2 else raw.decode()), i + n
    if major == 4:
        out = []
        for _ in range(n):
            v, i = cbor(data, i)
            out.append(v)
        return out, i
    if major == 5:
        out = {}
        for _ in range(n):
            k, i = cbor(data, i)
            out[k], i = cbor(data, i)
        assert list(out) == sorted(out, key=lambda k: (len(k.encode()), k.encode())), 'map keys out of canonical order'
        return out, i
    if major == 6:
        assert n == 42, 'only the CID tag'
        v, i = cbor(data, i)
        return ('cid', v), i
    return {20: False, 21: True, 22: None}[n], i


def varint(data, i):
    n = shift = 0
    while True:
        b = data[i]
        i += 1
        n |= (b & 0x7f) << shift
        shift += 7
        if b < 0x80:
            return n, i


def cid_bytes(cid):
    return base64.b32decode(cid[1:].upper() + '=' * (-len(cid[1:]) % 8))


class Repository(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.provider = Provider()
        cls.server = served(cls.tmp.name, cleanup=cls.addClassCleanup, opener='did:plc:' + 'o' * 24, library=LIBRARY)  # DID is a resident the front logs in
        sock = cls.server.sock
        cls.host = HostClient(sock)
        cls.now, cls.token = [1000.0], None
        st = State(cls.tmp.name)
        ident = identity.Identity(st, delve.Client(cls.provider), clock=lambda: cls.now[0])
        cls.front = Front(st, cls.host, ident, ('127.0.0.1', 0), clock=lambda: cls.now[0])
        cls.port = cls.front.server_address[1]
        serve(cls.front)
        send = cls.host.send
        seeded = [
            town_garden(lambda **q: send(q)),
            send({'op': 'world-turn', 'principal': DID, 'object': 'garden', 'method': 'plant', 'identity': 'plant-1',
                  'argument': record(colour=label('amber'), seed=label('a moth bell'))}),
            send({'op': 'world-turn', 'principal': DID, 'object': 'nope', 'method': 'receive', 'argument': record(), 'identity': 'miss'}),
            send({'op': 'world-turn', 'principal': DID, 'object': 'garden', 'method': 'publishPage', 'argument': record(page=label('')), 'identity': 'pub-1'}),
            send({'op': 'world-create', 'principal': DID, 'identity': 'mk-d', 'object': 'diary', 'modules': counter_modules(),
                  'entry': 'initial', 'seed': record(count=nat(0)), 'read': {'principals': [DID]}})]
        assert [r['status'] for r in seeded] == ['admitted', 'admitted', 'refused', 'admitted', 'created'], seeded
        cls.receipts = {r['receipt']['identity']['intent']: r['receipt'] for r in seeded}

    @classmethod
    def tearDownClass(cls):
        cls.front.shutdown()
        cls.front.server_close()
        cls.server.stop()
        cls.tmp.cleanup()

    def get(self, path, token=None, raw=False):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=60)
        c.request('GET', path, None, {'Authorization': 'Bearer ' + token} if token else {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, (data, r.getheader('Content-Type')) if raw else json.loads(data)

    def xrpc(self, nsid, token=None, raw=False, **q):
        from urllib.parse import urlencode
        self.now[0] += 61  # past the front's rate window: these tests read far more than 32 times
        got = self.get(f'/xrpc/{nsid}?{urlencode(q)}', token, raw)
        if not raw and got[0] == 200 and nsid in (NS + 'getProjection', NS + 'listProjections'):
            from tests.test_lexicons import record_problems
            for value in (got[1]['projections'] if nsid.endswith('listProjections') else [got[1]]):
                self.assertEqual(record_problems(value), [], value)
        return got

    def login(self):
        if Repository.token:
            return Repository.token
        s, ch = self.call_post('/AGENTS.md/challenge', {'handle': 'talkie.delve.town'})
        self.provider.texts[DID] = ch['text']
        s, v = self.call_post('/AGENTS.md/verify', {'handle': 'talkie.delve.town', 'uri': f'at://{DID}/town.delve.feed.post/3abc'}, ch['credential'])
        self.assertEqual((s, v['status']), (200, 'verified'), v)
        Repository.token = ch['credential']
        return Repository.token

    def call_post(self, path, body, token=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=60)
        c.request('POST', path, json.dumps(body), {'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + token} if token else {})})
        r = c.getresponse()
        out = (r.status, json.loads(r.read()))
        c.close()
        return out

    def receipt(self, intent, reader='anonymous'):
        return self.host.send({'op': 'world-receipt', 'principal': reader, 'identity': intent, 'of': DID})


    def test_list_projections_pages_receipts_by_height_both_ways(self):
        pages, cursor = [], None
        while True:
            s, page = self.xrpc(NS + 'listProjections', kind='receipt', limit=2, **({'cursor': cursor} if cursor else {}))
            self.assertEqual(s, 200, page)
            self.assertLessEqual(len(page['projections']), 2)
            pages.append(page['projections'])
            cursor = page.get('cursor')
            if not cursor:
                break
        records = [r for p in pages for r in p]
        heights = [r['value']['height'] for r in records]
        self.assertEqual(heights, sorted(set(heights)), heights)
        self.assertGreater(len(pages), 2)
        self.assertLessEqual({r['hash'] for r in self.receipts.values()}, {r['of'] for r in records})
        for r in records:
            self.assertEqual((r['kind'], r['key']), ('receipt', r['value']['slug']))
            self.assertNotIn('$type', r['value'])
        s, newest = self.xrpc(NS + 'listProjections', kind='receipt', limit=3, reverse='true')
        s, older = self.xrpc(NS + 'listProjections', kind='receipt', limit=100, reverse='true', cursor=newest['cursor'])
        self.assertEqual(newest['projections'] + older['projections'], records[::-1])
        self.assertEqual(self.xrpc(NS + 'listProjections', kind='receipt', limit=0)[0], 400)

    def test_sources_sharing_one_entry_page_one_at_a_time_both_ways_and_none_is_skipped(self):
        def walk(**more):
            got, cursor = [], None
            while True:
                s, page = self.xrpc(NS + 'listProjections', kind='source', limit=1, **more, **({'cursor': cursor} if cursor else {}))
                self.assertEqual(s, 200, page)
                got += page['projections']
                cursor = page.get('cursor')
                if not cursor:
                    return got
        s, whole = self.xrpc(NS + 'listProjections', kind='source', limit=100)
        heights = [r['value']['height'] for r in whole['projections']]
        self.assertGreater(len(heights), len(set(heights)), 'the library entry holds several sources at one height')
        self.assertEqual([r['of'] for r in walk()], [r['of'] for r in whole['projections']])
        self.assertEqual([r['of'] for r in walk(reverse='true')], [r['of'] for r in whole['projections']][::-1])

    def test_get_projection_by_slug_equals_by_cid_equals_world_receipt(self):
        tok = self.login()
        for intent in ('plant-1', 'miss', 'pub-1'):
            for token, reader in ((None, 'anonymous'), (tok, DID)):
                truth = self.receipt(intent, reader)
                truth = truth['receipt'] if truth['status'] == 'receipt' else {**truth, 'height': self.receipts[intent]['height'],
                                                                                 'hash': self.receipts[intent]['hash']}
                got = [self.xrpc(NS + 'getProjection', token, kind='receipt', key=k)
                       for k in (self.receipts[intent]['slug'], self.receipts[intent]['hash'])]
                for s, r in got:
                    self.assertEqual((s, r['of']), (200, self.receipts[intent]['hash']), r)
                    self.assertEqual(r['value'], truth)
                self.assertEqual(got[0][1]['value'], got[1][1]['value'])
        public = self.xrpc(NS + 'getProjection', kind='receipt', key=self.receipts['miss']['slug'])[1]['value']
        self.assertEqual((public['status'], public['class'], public['root']), ('refused', 'unknownObject', {'object': 'nope'}))
        self.assertNotIn('identity', public)
        s, e = self.xrpc(NS + 'getProjection', kind='receipt', key='babab-babab')
        self.assertEqual((s, e['error']), (400, 'RecordNotFound'), e)
        s, e = self.xrpc(NS + 'getProjection', kind='receipt', key=self.receipts['miss']['slug'],
                         cid=self.receipts['pub-1']['hash'])
        self.assertEqual((s, e['error']), (400, 'RecordNotFound'))

    @signs
    def test_entry_sync_proof_carries_the_owners_canonical_entry_block(self):
        whole = self.receipt('plant-1', DID)['receipt']
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Repo(ORIGIN, sign.Key.generate(), ledger=State(tmp.name).repo_ledger)
        code, projection, _ = repo.serve(self.host, 'GET', NS + 'getProjection', {'kind': 'receipt', 'key': whole['slug']}, DID)
        self.assertEqual(code, 200, projection)
        rev = projection['signed'].rsplit('/', 1)[1]
        query = {'did': REPO, 'collection': NS + 'entry', 'rkey': rev}
        s, car, ctype = repo.serve(self.host, 'GET', 'com.atproto.sync.getRecord', query, DID)
        self.assertEqual((s, ctype), (200, 'application/vnd.ipld.car'), car)
        n, i = varint(car, 0)
        header, end = cbor(car, i)
        self.assertEqual(end, i + n)
        [root], blocks = read_car(car)
        self.assertEqual(header, {'roots': [('cid', b'\x00' + bytes(root))], 'version': 1})
        record_cid = find(blocks, decode(blocks[root])['data'], (NS + 'entry/' + rev).encode())
        self.assertEqual(decode(blocks[record_cid])['entry'], CID.parse(whole['hash']))
        cid = cid_bytes(whole['hash'])
        data = blocks[CID.parse(whole['hash'])]
        self.assertEqual(cid[:4], b'\x01\x71\x12\x20')
        self.assertEqual(hashlib.sha256(data).digest(), cid[4:])
        value, used = cbor(data)
        self.assertEqual(used, len(data))
        self.assertEqual(value, {k: v for k, v in whole.items() if k not in ('hash', 'slug')})
        code, by_cid, _ = repo.serve(self.host, 'GET', NS + 'getProjection', {'kind': 'receipt', 'key': whole['hash']}, DID)
        self.assertEqual(by_cid['signed'], projection['signed'])
        self.assertEqual(repo.serve(self.host, 'GET', 'com.atproto.sync.getRecord', query, DID)[1], car)
        s, public, _ = repo.serve(self.host, 'GET', 'com.atproto.sync.getRecord', query, None)
        self.assertEqual(s, 200, public)
        self.assertNotIn(CID.parse(whole['hash']), read_car(public)[1])

    def test_get_repo_a_write_and_a_bad_bearer_are_refused_by_name(self):
        s, e = self.xrpc('com.atproto.sync.getRepo', did=REPO)
        self.assertEqual((s, e['error']), (400, 'RepoNotServed'))
        self.assertIn(NS + 'getProjection', e['hint'])
        s, e = self.xrpc('com.atproto.repo.createRecord')
        self.assertEqual((s, e['error']), (501, 'MethodNotImplemented'))
        s, e = self.xrpc('com.atproto.repo.describeRepo', 'dt_agent_' + 'A' * 43, repo=REPO)
        self.assertEqual((s, e['error']), (401, 'InvalidToken'))  # a bad bearer is not the public reader
        s, e = self.xrpc(NS + 'getProjection', 'dt_agent_' + 'A' * 43, kind='object', key='diary.0')
        self.assertEqual((s, e['error']), (401, 'InvalidToken'))

    @signs
    def test_signed_over_the_real_journal_every_leaf_names_its_entry(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Repo(ORIGIN, sign.Key.generate(), ledger=State(tmp.name).repo_ledger)
        code, car, _ = repo.serve(self.host, 'GET', 'com.atproto.sync.getRepo', {'did': REPO}, None)
        self.assertEqual(code, 200, car)
        [root], blocks = read_car(car)
        commit = decode(blocks[root])
        hashes = [e['hash'] for e in self.host.send({'op': 'world-entries', 'principal': 'anonymous', 'limit': 100})['entries']]
        self.assertEqual([decode(blocks[v])['entry'] for _, v in leaves(blocks, commit['data'])], [CID.parse(h) for h in hashes])
        whole = self.receipt('plant-1', DID)['receipt']
        code, projected, _ = repo.serve(self.host, 'GET', NS + 'getProjection', {'kind': 'receipt', 'key': whole['slug']}, DID)
        self.assertEqual(code, 200, projected)
        code, proof, _ = repo.serve(self.host, 'GET', 'com.atproto.sync.getRecord', {'did': REPO, 'collection': NS + 'entry', 'rkey': projected['signed'].rsplit('/', 1)[1]}, DID)
        self.assertEqual(decode(read_car(proof)[1][CID.parse(whole['hash'])])['height'], whole['height'])  # the host's own bytes, under its CID

    def test_a_private_objects_projection_is_refused_to_the_public_and_served_to_its_owner(self):
        tok = self.login()
        s, e = self.xrpc(NS + 'getProjection', kind='object', key='diary.0')
        self.assertEqual((s, e['error']), (403, 'Denied'), e)
        s, r = self.xrpc(NS + 'getProjection', tok, kind='object', key='diary.0')
        self.assertEqual(s, 200, r)
        self.assertEqual(self.xrpc(NS + 'getProjection', tok, kind='object', key='diary/0')[0], 400)  # keys encode / as ~ and separate the version with a dot
        cid = self.host.send({'op': 'world-state-cid', 'principal': DID, 'object': 'diary', 'version': 0})['cid']
        pin = self.host.send({'op': 'world-inspect', 'principal': DID, 'object': 'diary'})['pin']
        self.assertEqual((r['kind'], r['key'], r['of'], r['value']['stateCid'], r['value']['pin']), ('object', 'diary.0', cid, cid, pin))
        listed = lambda token=None: [x['value']['object'] for x in self.xrpc(NS + 'listProjections', token, kind='object')[1]['projections']]
        self.assertNotIn('diary', listed())
        self.assertIn('diary', listed(tok))
        self.assertIn('garden/bell/1', listed())
        s, garden = self.xrpc(NS + 'getProjection', kind='object', key='garden.1')
        self.assertEqual((s, garden['value']['object'], garden['value']['version']), (200, 'garden', 1), garden)
        s, bell = self.xrpc(NS + 'getProjection', kind='object', key='garden~bell~1.0')
        self.assertEqual((s, bell['kind'], bell['key'], bell['value']['object']), (200, 'object', 'garden~bell~1.0', 'garden/bell/1'), bell)
        self.assertEqual(self.xrpc(NS + 'getProjection', kind='object', key='garden/bell/1/0')[0], 400)  # keys encode / as ~ and separate the version with a dot
        laws = self.xrpc(NS + 'listProjections', kind='law')[1]['projections']
        self.assertIn('garden~bell~1.kind', [x['key'] for x in laws])  # under "kind/bell"
        self.assertNotIn('diary', [x['value']['object'] for x in laws])


    def test_objects_and_laws_page_by_limit_and_the_cursor_resumes_exactly(self):
        tok = self.login()
        for c in ('object', 'law'):
            lister = lambda **q: self.xrpc(NS + 'listProjections', tok, kind=c, **q)
            s, whole = lister(limit=100)
            keys, cursor, seen = [r['key'] for r in whole['projections']], None, []
            self.assertGreater(len(keys), 2, c)
            for _ in range(len(keys) + 1):
                s, page = lister(limit=2, **({'cursor': cursor} if cursor else {}))
                self.assertEqual(s, 200, page)
                self.assertLessEqual(len(page['projections']), 2)
                seen += [r['key'] for r in page['projections']]
                cursor = page.get('cursor')
                if not cursor:
                    break
            self.assertEqual(seen, keys, c)

    def test_every_listed_projection_key_is_in_record_key_syntax(self):
        tok = self.login()
        for c in ('receipt', 'object', 'source', 'publication', 'grant', 'law'):
            for token in (None, tok):
                s, page = self.xrpc(NS + 'listProjections', token, kind=c, limit=100)
                self.assertEqual(s, 200, page)
                for r in page['projections']:
                    key = r['key']
                    self.assertRegex(key, r'\A[A-Za-z0-9._~:-]{1,512}\Z')
                    self.assertNotIn(key, ('.', '..'))


FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'atproto'
OWNER = 'did:plc:owner'


def vectors(name):
    return json.loads((FIXTURES / name).read_text())


def b64(text):
    return base64.b64decode(text + '=' * (-len(text) % 4))


def from_json(x):
    """The AT Protocol JSON form ({$link}, {$bytes}) as DAG-CBOR values."""
    if isinstance(x, dict):
        if set(x) == {'$link'}:
            return CID.parse(x['$link'])
        if set(x) == {'$bytes'}:
            return b64(x['$bytes'])
        return {k: from_json(v) for k, v in x.items()}
    return [from_json(v) for v in x] if isinstance(x, list) else x


def leaves(blocks, cid, depth=None):
    """Every (key, value) under MST node `cid`, as a reader with only the blocks walks it: keys ascending, each
    at its node's layer, children one layer down, no empty node but an empty root."""
    node = decode(blocks[cid])
    here = {layer(k) for k in node_keys(node)}
    assert len(here) <= 1 and (depth is None or not here or here == {depth}), (here, depth)
    depth = here.pop() if here else depth
    assert depth is not None or (not node['e'] and node['l'] is None), 'an empty node only at the root'
    out = leaves(blocks, node['l'], depth - 1) if node['l'] else []
    for key, e in zip(node_keys(node), node['e']):
        out.append((key, e['v']))
        out += leaves(blocks, e['t'], depth - 1) if e['t'] else []
    assert [k for k, _ in out] == sorted({k for k, _ in out}), 'keys ascending and distinct'
    return out


def node_keys(node):
    keys, prev = [], b''
    for e in node['e']:
        prev = prev[:e['p']] + e['k']
        keys.append(prev)
    return keys


class Vectors(unittest.TestCase):
    def test_key_layers_and_prefixes(self):
        for v in vectors('key_heights.json'):
            self.assertEqual(layer(v['key'].encode()), v['height'], v)
        for v in vectors('common_prefix.json'):
            self.assertEqual(common_prefix(v['left'].encode(), v['right'].encode()), v['len'], v)

    def test_data_model_bytes_and_cids(self):
        for v in vectors('data-model-fixtures.json'):
            value = from_json(v['json'])
            cid, data = block(value)
            self.assertEqual((data, str(cid)), (b64(v['cbor_base64']), v['cid']))
            self.assertEqual(decode(data), value)
        for bad in (b'\xf9\x3c\x00', b'\xa2a\x62\x01a\x61\x02', b'\x18\x01', b'\xc1\x01', b'\x9f\xff'):  # float, key order, long head, tag, indefinite
            self.assertRaises(ValueError, decode, bad)

    def test_mst_roots_and_proofs(self):
        for v in vectors('commit-proof-fixtures.json'):
            leaf = CID.parse(v['leafValue'])
            for keys, root in ((set(v['keys']), v['rootBeforeCommit']),
                               ((set(v['keys']) | set(v['adds'])) - set(v['dels']), v['rootAfterCommit'])):
                tree, keys = Tree(), sorted(keys)
                for k in keys:
                    tree.append(k.encode(), leaf)
                self.assertEqual(str(tree.root()), root, v['comment'])
            for added in v['adds']:
                self.assertLessEqual({str(c) for c, _ in tree.proof(keys.index(added))}, set(v['blocksInProof']), v['comment'])
            blocks = dict(tree.blocks())
            self.assertEqual([k.decode() for k, _ in leaves(blocks, tree.root())], keys)
        self.assertEqual(str(Tree().root()), 'bafyreie5737gdxlw5i64vzichcalba3z2v5n6icifvx5xytvske7mr3hpm')  # the empty tree

    @signs
    def test_did_keys_and_signatures(self):
        for v in vectors('w3c_didkey_K256.json'):
            key = sign.Key(sign.ec.derive_private_key(int(v['privateKeyBytesHex'], 16), sign.ec.SECP256K1()))
            self.assertEqual(key.did_key, v['publicDidKey'])
        for v in vectors('w3c_didkey_P256.json'):
            secret = int.from_bytes(sign.b58decode(v['privateKeyBytesBase58']), 'big')
            self.assertEqual(sign.Key(sign.ec.derive_private_key(secret, sign.ec.SECP256R1())).did_key, v['publicDidKey'])
        for v in vectors('signature-fixtures.json'):
            got = sign.verify(sign.public_key(v['publicKeyDid']), b64(v['messageBase64']), b64(v['signatureBase64']))
            self.assertEqual(got, v['validSignature'], v['comment'])
        for curve in sign.CURVES:
            key = sign.Key.generate(curve)
            sigs = {key.sign(b'%d' % i) for i in range(64)} | {key.sign(b'0')}
            self.assertEqual(len(sigs), 64)  # deterministic: the same message signs the same
            for i, sig in enumerate(sorted(sigs)):
                self.assertLessEqual(int.from_bytes(sig[32:], 'big'), sign.CURVES[curve][2] // 2)
            self.assertTrue(sign.verify(sign.public_key(key.did_key), b'7', key.sign(b'7')))

    def test_the_key_is_made_once_0400_and_never_printed(self):
        import contextlib
        import io
        import os
        from unittest import mock
        from transport.__main__ import main
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'DELVETALK_REPO_KEYS': d}):
            out = io.StringIO()
            self.assertEqual(main(['repokey', '--state', d], out), 0)
            path = Path(d) / 'town.key'
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o400)
            self.assertEqual(out.getvalue(), f'{path}: {sign.Key.load(path).did_key}\n')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['repokey', '--state', d], io.StringIO()), 1)
            self.assertEqual(Repo(ORIGIN, sign.Key.load(path), ledger=State(d).repo_ledger).did_document()['verificationMethod'][0]['publicKeyMultibase'],
                             sign.Key.load(path).did_key.removeprefix('did:key:'))

    def test_a_world_besides_the_town_is_a_did_web_of_its_own_host_never_a_path(self):
        ring = Repo('https://gsb.example', world='ring')
        doc = ring.did_document()
        self.assertEqual((ring.did, doc['id'], doc['alsoKnownAs']), ('did:web:ring.gsb.example',) * 2 + (['at://ring.gsb.example'],))
        self.assertEqual(doc['service'][0]['serviceEndpoint'], 'https://ring.gsb.example')
        self.assertEqual(Repo('https://gsb.example').did, 'did:web:gsb.example')  # the town keeps the front's own
        self.assertNotIn(':', ring.did.removeprefix('did:web:'))  # hostname-level only: a path would be a `:` segment

    def test_tids_sort_as_their_time(self):
        times = [0, 1, 1023, 1 << 40, 60_000_000 * 29_000_000 + 7, (1 << 53) - 1]
        tids = [sign.tid(t) for t in times]
        self.assertEqual(tids, sorted(tids))
        for t in tids:
            self.assertRegex(t, r'\A[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}\Z')


class World:
    """A fake host: a journal of DAG-CBOR entries chained by CID, read as the host's ops answer them."""

    def __init__(self, page=4, start=0):
        self.entries, self.page, self.start = [], page, start  # a carried journal's first height is start + 1

    def append(self, principal, intent, tag='admitted'):
        h = self.start + len(self.entries) + 1
        body = {'height': h, 'identity': {'principal': principal, 'intent': intent}, 'turn': 0, 'roots': [],
                'outcome': {'tag': tag}, **({'previous': self.entries[-1]['hash']} if self.entries else {})}
        cid, data = block(body)
        self.entries.append({**body, 'hash': str(cid), 'bytes': data})

    def send(self, q):
        whole = lambda e: e['identity']['principal'] == q.get('principal')
        if q['op'] == 'world-entries':
            after, limit = max(q.get('after', 0) - self.start, 0), min(q.get('limit', 100), self.page)
            shown = self.entries[after:after + limit]
            return {'status': 'entries', 'more': after + limit < len(self.entries),
                    'entries': [{k: e[k] for k in ('height', 'hash', 'identity')} for e in shown]}
        if q['op'] == 'world-entry':
            [e] = [e for e in self.entries if e['hash'] == q['hash']] or [None]
            if not e:
                return {'status': 'unknown', 'message': 'no such entry'}
            return {'status': 'receipt', 'receipt': {k: e[k] for k in ('height', 'hash')},
                    **({'bytes': e['bytes'].hex()} if q.get('bytes') and whole(e) else {})}
        return {'status': 'unknown', 'message': q['op']}


class ProjectionWorld(World):
    """Three entries and each projection kind, with opaque host cursors and multiple clauses per object."""

    def __init__(self):
        super().__init__(page=100)
        for i in range(3):
            self.append(OWNER, f'projection-{i}')
        self.rows = {'receipt': [{**{k: e[k] for k in ('height', 'hash', 'identity')}, 'slug': identity.slug(e['hash'])} for e in self.entries]}
        self.rows['source'] = [{'cid': e['hash'], 'name': f'M{i}', 'text': 'module', 'height': i + 1} for i, e in enumerate(self.entries)]
        self.rows['publication'] = [{'id': f'pub{i}', 'object': 'bell/1', 'page': 'bell', 'section': '', 'body': 'bell',
                                     'height': i + 1, 'hash': e['hash']} for i, e in enumerate(self.entries)]
        self.rows['grant'] = [{'id': f'grant{i}', 'grantor': OWNER, 'holder': 'bell/1', 'to': OWNER, 'object': 'bell/1',
                               'method': 'rain', 'until': 0, 'height': i + 1, 'hash': e['hash']} for i, e in enumerate(self.entries)]
        self.objects = {oid: {'object': oid, 'version': 0, 'pin': self.entries[0]['hash'], 'stateCid': self.entries[1]['hash'],
                              'laws': [{'object': oid, 'pin': self.entries[0]['hash'], 'name': name, 'clause': 'true'}
                                       for name in ('one', 'two', 'three')]}
                        for oid in ('bell/1', 'bell/2', 'diary')}

    def send(self, q):
        op = q['op']
        if op == 'world-entry':
            reply = super().send(q)
            if reply.get('status') == 'receipt':
                reply['receipt'] = next(r for r in self.rows['receipt'] if r['hash'] == q['hash'])
            return reply
        if op == 'world-resolve':
            row = next((r for r in self.rows['receipt'] if r['slug'] == q['slug']), None)
            return {'status': 'resolved', 'kind': 'receipt', 'receipt': row, 'cid': row['hash']} if row else {'status': 'unknown'}
        names = {'world-entries': ('receipt', 'entries'), 'world-sources': ('source', 'sources'),
                 'world-publications': ('publication', 'publications'), 'world-grants': ('grant', 'grants')}
        if op in names:
            kind, field = names[op]
            rows = self.rows[kind]
            if 'after' in q:
                rows = [r for r in rows if r['height'] > q['after']]
            rows = rows[::-1] if q.get('reverse') else rows
            at = int(q['cursor'].split(':')[1]) if q.get('cursor') else 0
            end = at + q.get('limit', 50)
            return {'status': field, field: rows[at:end], 'more': end < len(rows),
                    **({'cursor': f'host:{end}'} if end < len(rows) else {})}
        if op == 'world-source':
            row = next((r for r in self.rows['source'] if r['cid'] == q['cid']), None)
            return {'status': 'source', 'record': row} if row else {'status': 'unknown'}
        if op == 'world-objects':
            ids = [oid for oid in self.objects if oid != 'diary' or q.get('principal') == OWNER]
            return {'status': 'listed', 'ids': [oid for oid in ids if oid > q.get('after', '') and oid.startswith(q.get('prefix', ''))], 'more': False}
        if op == 'world-object':
            oid = q['object']
            if oid == 'diary' and q.get('principal') != OWNER:
                return {'status': 'denied'}
            return {'status': 'object', 'record': self.objects[oid]} if oid in self.objects else {'status': 'unknown'}
        return super().send(q)


@signs
class ProjectionBoundary(unittest.TestCase):
    """Refuted by an old collection accepted, a value CID mismatch, a wrong proof path, or a projection losing its subject."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.world = ProjectionWorld()
        self.repo = Repo(ORIGIN, sign.Key.generate(), ledger=State(self.tmp.name).repo_ledger)

    def call(self, method, endpoint=None, who=None, **q):
        code, body, _ = (endpoint or self.repo).serve(self.world, 'GET', method, q, who)
        return code, body

    def test_six_projection_collections_are_invalid_on_all_repository_record_methods(self):
        for repo in (self.repo, Repo(ORIGIN)):
            for kind in ('receipt', 'object', 'source', 'publication', 'grant', 'law'):
                for method in ('com.atproto.repo.getRecord', 'com.atproto.repo.listRecords', 'com.atproto.sync.getRecord'):
                    with self.subTest(kind=kind, method=method, signed=bool(repo.signed)):
                        code, body = self.call(method, endpoint=repo, **{'repo': REPO, 'did': REPO, 'collection': NS + kind, 'rkey': 'bell~1.0'})
                        self.assertEqual((code, body['error']), (400, 'InvalidRequest'), body)
                        self.assertTrue(body['message'].startswith('collection must be one of '), body)
            code, body = self.call('com.atproto.repo.describeRepo', endpoint=repo, **{'repo': REPO})
            self.assertEqual(body['collections'], [NS + c for c in ('card', 'page', 'index', 'answer')] + ([NS + 'entry'] if repo.signed else []))

    def test_every_served_collection_hashes_the_listed_and_fetched_value(self):
        from unittest.mock import patch
        from transport import mirror
        from tests.test_lexicons import record_problems
        pages = [{'name': 'bell', 'kind': 'page', 'title': 'Bell', 'body': 'rain', 'place': 0}]
        answer = {'$type': NS + 'answer', 'request': {'uri': 'at://did:plc:x/' + NS + 'request/r', 'cid': self.world.entries[0]['hash']},
                  'outcome': {'status': 'admitted', 'line': 'admitted'}, 'height': 1,
                  'receipt': {'slug': 'babab-babab', 'height': 1, 'entry': {'$link': self.world.entries[0]['hash']}}}
        def card(host, oid, reader='anonymous', **kw):
            self.assertEqual(reader, 'anonymous')
            return {'$type': NS + 'card', 'object': oid, 'version': 0, 'card': 'rain', 'wants': [], 'doors': []}
        with patch.object(mirror, 'card_record', card), patch.object(mirror, 'library_pages', return_value=pages), \
             patch.object(mirror, 'height', return_value=3), patch.object(mirror, 'answer_records', return_value={'did:plc:x.r': answer}):
            code, described = self.call('com.atproto.repo.describeRepo', **{'repo': REPO})
            self.assertEqual(code, 200)
            for collection in described['collections']:
                code, page = self.call('com.atproto.repo.listRecords', **{'repo': REPO, 'collection': collection, 'limit': '100'})
                self.assertEqual(code, 200, page)
                self.assertTrue(page['records'], collection)
                for listed in page['records']:
                    self.assertEqual(listed['cid'], str(block(from_json(listed['value']))[0]), listed)
                    self.assertEqual(record_problems(listed['value']), [], listed)
                    key = listed['uri'].rsplit('/', 1)[1]
                    for who in (None, OWNER):
                        code, got = self.call('com.atproto.repo.getRecord', who=who, **{'repo': REPO, 'collection': collection, 'rkey': key})
                        self.assertEqual((code, got), (200, listed))
                        self.assertEqual(got['cid'], str(block(from_json(got['value']))[0]))
                    code, wrong = self.call('com.atproto.repo.getRecord', **{'repo': REPO, 'collection': collection, 'rkey': key, 'cid': 'wrong'})
                    self.assertEqual((code, wrong['error']), (400, 'RecordNotFound'))
            self.assertEqual(set(described['collections']), {NS + c for c in ('entry', 'card', 'page', 'index', 'answer')})

    def test_entry_sync_proofs_find_exactly_the_requested_path(self):
        code, page = self.call('com.atproto.repo.listRecords', **{'repo': REPO, 'collection': NS + 'entry'})
        self.assertEqual(code, 200, page)
        for record in page['records']:
            key = record['uri'].rsplit('/', 1)[1]
            for who in (None, OWNER):
                code, proof = self.call('com.atproto.sync.getRecord', who=who, did=REPO, collection=NS + 'entry', rkey=key)
                self.assertEqual(code, 200, proof)
                [root], blocks = read_car(proof)
                self.assertEqual(find(blocks, decode(blocks[root])['data'], (NS + 'entry/' + key).encode()), CID.parse(record['cid']))
                entry = CID.parse(record['value']['entry']['$link'])
                self.assertEqual(entry in blocks, who == OWNER)
        for key in (self.world.entries[0]['hash'], self.world.rows['receipt'][0]['slug']):
            code, body = self.call('com.atproto.sync.getRecord', did=REPO, collection=NS + 'entry', rkey=key)
            self.assertEqual((code, body['error']), (400, 'RecordNotFound'))
        for kind in ('card', 'page', 'index', 'answer'):
            code, body = self.call('com.atproto.sync.getRecord', did=REPO, collection=NS + kind, rkey='self')
            self.assertEqual((code, body['error']), (400, 'InvalidRequest'))

    def test_all_projection_kinds_keep_keys_subjects_and_cursors(self):
        from tests.test_lexicons import record_problems
        for kind in ('receipt', 'object', 'source', 'publication', 'grant', 'law'):
            def walk(limit, reverse=False):
                rows, cursor = [], None
                while True:
                    code, page = self.call(NS + 'listProjections', who=OWNER, kind=kind, limit=str(limit),
                                           **({'cursor': cursor} if cursor else {}), **({'reverse': 'true'} if reverse else {}))
                    self.assertEqual(code, 200, page)
                    self.assertLessEqual(len(page['projections']), limit)
                    rows += page['projections']
                    cursor = page.get('cursor')
                    if not cursor:
                        return rows
            whole = walk(100)
            self.assertTrue(whole, kind)
            self.assertEqual(walk(1), whole)
            if kind not in ('object', 'law'):
                self.assertEqual(walk(1, True), whole[::-1])
            else:
                code, body = self.call(NS + 'listProjections', kind=kind, reverse='true')
                self.assertEqual((code, body['error']), (400, 'InvalidRequest'))
            for row in whole:
                self.assertEqual(row['kind'], kind)
                self.assertNotIn('$type', row['value'])
                self.assertEqual(record_problems(row), [], row)
                field = {'receipt': 'hash', 'object': 'stateCid', 'source': 'cid', 'publication': 'hash', 'grant': 'hash'}.get(kind)
                if field:
                    self.assertEqual(row['of'], row['value'][field])
                else:
                    self.assertNotIn('of', row)
                code, got = self.call(NS + 'getProjection', who=OWNER, kind=kind, key=row['key'])
                self.assertEqual((code, got), (200, row))
                if field:
                    code, got = self.call(NS + 'getProjection', who=OWNER, kind=kind, key=row['key'], cid=row['of'])
                    self.assertEqual((code, got), (200, row))
                code, body = self.call(NS + 'getProjection', who=OWNER, kind=kind, key=row['key'], cid='wrong')
                self.assertEqual((code, body['error']), (400, 'RecordNotFound'))
            for bad in ('0', '101', '-1', '²', 'no', '9' * 5000):
                code, body = self.call(NS + 'listProjections', kind=kind, limit=bad)
                self.assertEqual((code, body['error']), (400, 'InvalidRequest'))
        self.assertEqual(whole[0]['key'], 'bell~1.one')

    def test_projection_parameters_and_object_law_cursors_refuse_adversarial_inputs(self):
        for method in ('getProjection', 'listProjections'):
            for bad in ('', 'entry', 'card', 'receipt' * 100):
                code, body = self.call(NS + method, kind=bad, key='bell~1.0')
                self.assertEqual((code, body['error']), (400, 'InvalidRequest'))
        for kind in ('receipt', 'object', 'source', 'publication', 'grant', 'law'):
            code, body = self.call(NS + 'getProjection', kind=kind)
            self.assertEqual((code, body['error']), (400, 'InvalidRequest'))
        for kind in ('object', 'law'):
            for cursor in ('bell/1#x', 'bell/1#²', 'bell/1#' + '9' * 5000):
                code, body = self.call(NS + 'listProjections', kind=kind, cursor=cursor)
                self.assertEqual((code, body['error']), (400, 'InvalidRequest'))

    def test_maximum_pages_and_id_lookup_past_the_first_host_page(self):
        for kind in ('source', 'publication', 'grant'):
            first = self.world.rows[kind][0]
            key_field = 'cid' if kind == 'source' else 'id'
            keys = [str(block({'source': i})[0]) if kind == 'source' else f'key{i}' for i in range(103)]
            self.world.rows[kind] = [{**first, key_field: key, 'height': i + 1} for i, key in enumerate(keys)]
            code, page = self.call(NS + 'listProjections', kind=kind, limit='100')
            self.assertEqual(code, 200, page)
            self.assertEqual(len(page['projections']), 100)
            code, rest = self.call(NS + 'listProjections', kind=kind, limit='100', cursor=page['cursor'])
            self.assertEqual(code, 200, rest)
            self.assertEqual([r['key'] for r in page['projections'] + rest['projections']], keys)
            self.assertNotIn('cursor', rest)
            code, default = self.call(NS + 'listProjections', kind=kind)
            self.assertEqual(code, 200)
            self.assertEqual(len(default['projections']), 50)
            code, got = self.call(NS + 'getProjection', kind=kind, key=keys[-1])
            self.assertEqual((code, got['key'], got['of']), (200, keys[-1], keys[-1] if kind == 'source' else first['hash']))
            code, body = self.call(NS + 'getProjection', kind=kind, key='not-here')
            self.assertEqual((code, body['error']), (400, 'RecordNotFound'))

    def test_receipt_object_law_maximum_pages_resume_at_exact_boundary(self):
        for i in range(100):
            self.world.append(OWNER, f'maximum-{i}')
        self.world.rows['receipt'] = [{**{k: e[k] for k in ('height', 'hash', 'identity')}, 'slug': identity.slug(e['hash'])}
                                      for e in self.world.entries]
        base = self.world.objects['bell/1']
        self.world.objects = {f'bell/{i:03d}': {**base, 'object': f'bell/{i:03d}',
                                               'laws': [{**law, 'object': f'bell/{i:03d}'} for law in base['laws']]}
                              for i in range(103)}
        for kind in ('receipt', 'object', 'law'):
            code, page = self.call(NS + 'listProjections', kind=kind, limit='100')
            self.assertEqual(code, 200, page)
            self.assertEqual(len(page['projections']), 100)
            seen = page['projections']
            cursor = page['cursor']
            while cursor:
                code, page = self.call(NS + 'listProjections', kind=kind, limit='100', cursor=cursor)
                self.assertEqual(code, 200, page)
                self.assertLessEqual(len(page['projections']), 100)
                seen += page['projections']
                cursor = page.get('cursor')
            if kind == 'receipt':
                keys = [r['slug'] for r in self.world.rows[kind]]
            else:
                tails = ['0'] if kind == 'object' else ['one', 'two', 'three']
                keys = [f"{oid.replace('/', '~')}.{tail}" for oid in self.world.objects for tail in tails]
            self.assertEqual([r['key'] for r in seen], keys)

    def test_receipt_signed_link_is_findable_and_absent_on_an_unsigned_box(self):
        entry = self.world.rows['receipt'][0]
        for key in (entry['slug'], entry['hash']):
            code, row = self.call(NS + 'getProjection', kind='receipt', key=key)
            self.assertEqual((code, row['kind'], row['key'], row['of']), (200, 'receipt', key, entry['hash']))
            self.assertEqual(row['signed'], f'at://{REPO}/{NS}entry/{self.repo.signed.heights[0].rev}')
            rev = row['signed'].rsplit('/', 1)[1]
            code, proof = self.call('com.atproto.sync.getRecord', did=REPO, collection=NS + 'entry', rkey=rev)
            self.assertEqual(code, 200)
            [root], blocks = read_car(proof)
            value = find(blocks, decode(blocks[root])['data'], (NS + 'entry/' + rev).encode())
            self.assertEqual(decode(blocks[value])['entry'], CID.parse(row['of']))
            code, bare = self.call(NS + 'getProjection', endpoint=Repo(ORIGIN), kind='receipt', key=key)
            self.assertEqual(code, 200, bare)
            self.assertNotIn('signed', bare)
            self.assertEqual(bare['value'], row['value'])

    def test_private_object_projection_and_laws_stay_private(self):
        for kind, key in (('object', 'diary.0'), ('law', 'diary.one')):
            code, body = self.call(NS + 'getProjection', kind=kind, key=key)
            self.assertEqual((code, body['error']), (403, 'Denied'))
            code, row = self.call(NS + 'getProjection', who=OWNER, kind=kind, key=key)
            self.assertEqual((code, row['value']['object']), (200, 'diary'))
            code, public = self.call(NS + 'listProjections', kind=kind)
            self.assertEqual(code, 200)
            self.assertNotIn('diary', [r['value']['object'] for r in public['projections']])


@signs
class CarriedRepository(unittest.TestCase):
    """A carried journal begins at the height the world before reached (HOST-HANDOFF 5.182): the live v10 town's
    first entry is 447, and getRepo answered 503 "the journal's entry 447 is not height 1"."""

    def test_a_journal_whose_first_entry_is_447_is_a_whole_repository_and_since_reads_what_came_after(self):
        world, key = World(start=446), sign.Key.generate()
        for i in range(6):
            world.append(OWNER, f'turn-{i}')
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repo = Repo(ORIGIN, key, ledger=State(tmp.name).repo_ledger)
        code, car, _ = repo.serve(world, 'GET', 'com.atproto.sync.getRepo', {'did': REPO}, 'anonymous')
        self.assertEqual(code, 200, car)
        [root], blocks = read_car(car)
        commit = decode(blocks[root])
        pairs = leaves(blocks, commit['data'])
        self.assertEqual([decode(blocks[v])['height'] for _, v in pairs], list(range(447, 453)))
        code, latest, _ = repo.serve(world, 'GET', 'com.atproto.sync.getLatestCommit', {'did': REPO}, 'anonymous')
        world.append(OWNER, 'turn-after')
        code, newer, _ = repo.serve(world, 'GET', 'com.atproto.sync.getRepo', {'did': REPO, 'since': latest['rev']}, 'anonymous')
        self.assertEqual(code, 200, newer)
        [root], blocks = read_car(newer)
        records = [decode(b) for b in blocks.values() if isinstance(decode(b), dict) and decode(b).get('$type') == NS + 'entry']
        self.assertEqual([r['height'] for r in records], [453])
        code, listed, _ = repo.serve(world, 'GET', 'com.atproto.repo.listRecords', {'repo': REPO, 'collection': NS + 'entry', 'limit': '3'}, 'anonymous')
        self.assertEqual([r['value']['height'] for r in listed['records']], [447, 448, 449], listed)


@signs
class SignedRepository(unittest.TestCase):
    """Ten entries on a fake world, read through the front on loopback with a key."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.world, cls.key = World(), sign.Key.generate()
        for i in range(10):
            cls.world.append(*(('clock', 'advance:29000000') if i == 4 else (OWNER, f'turn-{i}')))
        cls.now = [1000.0]
        st = State(cls.tmp.name, config=Config(repo_keys=cls.tmp.name))
        st.repo_key.write_bytes(cls.key.pem())
        ident = identity.Identity(st, delve.Client(Provider()), clock=lambda: cls.now[0])
        cls.front = Front(st, cls.world, ident, ('127.0.0.1', 0), clock=lambda: cls.now[0])
        cls.port = cls.front.server_address[1]
        serve(cls.front)

    @classmethod
    def tearDownClass(cls):
        cls.front.shutdown()
        cls.front.server_close()
        cls.tmp.cleanup()

    def xrpc(self, nsid, **q):
        self.now[0] += 61
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=60)
        c.request('GET', f'/xrpc/{nsid}?{urllib.parse.urlencode(q)}')
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, (data if r.getheader('Content-Type') == 'application/vnd.ipld.car' else json.loads(data))

    def checked(self, car):
        """-> (commit, blocks): every block hashes to its CID, the root is a commit the DID document's key signed."""
        [root], blocks = read_car(car)
        commit = decode(blocks[root])
        self.assertEqual((commit['did'], commit['version'], sorted(commit)), (REPO, 3, ['data', 'did', 'prev', 'rev', 'sig', 'version']))
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=60)
        c.request('GET', '/.well-known/did.json')
        doc = json.loads(c.getresponse().read())
        c.close()
        [method] = doc['verificationMethod']
        self.assertEqual((method['id'], method['type'], method['controller']), (REPO + '#atproto', 'Multikey', REPO))
        unsigned = {k: v for k, v in commit.items() if k != 'sig'}
        self.assertTrue(sign.verify(sign.public_key(method['publicKeyMultibase']), encode(unsigned), commit['sig']))
        return root, commit, blocks

    def test_get_repo_is_a_signed_car_a_reader_can_walk_and_rebuild(self):
        s, car = self.xrpc('com.atproto.sync.getRepo', did=REPO)
        self.assertEqual(s, 200, car)
        root, commit, blocks = self.checked(car)
        pairs = leaves(blocks, commit['data'])
        self.assertEqual(len(pairs), len(self.world.entries))  # ten, and one more once the append test has run
        tree = Tree()
        for (key, value), entry in zip(pairs, self.world.entries):
            record = decode(blocks[value])
            self.assertEqual(record, {'$type': NS + 'entry', 'entry': CID.parse(entry['hash']), 'height': entry['height']})
            self.assertEqual(key.decode().split('/')[0], NS + 'entry')
            self.assertNotIn(CID.parse(entry['hash']), blocks)  # an entry's own bytes go only to whoever reads it whole
            tree.append(key, value)
        self.assertEqual(tree.root(), commit['data'])  # the tree is a function of its leaves
        revs = [k.decode().split('/')[1] for k, _ in pairs]
        self.assertEqual(commit['rev'], revs[-1])
        self.assertEqual(revs[:4], [sign.tid(h) for h in (1, 2, 3, 4)])  # no clock yet: the height alone
        self.assertEqual(revs[4:], [sign.tid(29_000_000 * 60_000_000 + h) for h in range(5, len(pairs) + 1)])
        self.assertEqual(self.xrpc('com.atproto.sync.getLatestCommit', did=REPO), (200, {'cid': str(root), 'rev': commit['rev']}))
        self.assertEqual(self.xrpc('com.atproto.sync.listRepos')[1]['repos'],
                         [{'did': REPO, 'head': str(root), 'rev': commit['rev'], 'active': True}])
        self.assertEqual(self.xrpc('com.atproto.sync.getRepoStatus', did=REPO)[1], {'did': REPO, 'active': True, 'rev': commit['rev']})
        self.assertEqual(self.xrpc('com.atproto.sync.listBlobs', did=REPO), (200, {'cids': []}))
        s, e = self.xrpc('com.atproto.sync.subscribeRepos')
        self.assertEqual((s, e['error']), (501, 'MethodNotImplemented'))
        self.assertIn('firehose_port', e['message'])
        twin = Repo(ORIGIN, self.key, ledger=self.front.st.repo_ledger)  # another process with the same inputs signs the same chain
        self.assertEqual(twin.serve(self.world, 'GET', 'com.atproto.sync.getRepo', {'did': REPO}, None)[1], car)

    def test_get_record_proves_the_record_from_the_signed_root(self):
        s, car = self.xrpc('com.atproto.sync.getRepo', did=REPO)
        pairs = leaves(read_car(car)[1], decode(read_car(car)[1][read_car(car)[0][0]])['data'])
        entry = self.world.entries[6]
        rev = pairs[6][0].decode().split('/')[1]
        s, proof = self.xrpc('com.atproto.sync.getRecord', did=REPO, collection=NS + 'entry', rkey=rev)
        self.assertEqual(s, 200, proof)
        root, commit, blocks = self.checked(proof)
        node, key = commit['data'], pairs[6][0]
        while True:  # down the path: only the blocks of the proof
            n = decode(blocks[node])
            keys = node_keys(n)
            if key in keys:
                value = n['e'][keys.index(key)]['v']
                break
            i = sum(k < key for k in keys)
            node = (n['e'][i - 1]['t'] if i else n['l'])
        self.assertEqual(decode(blocks[value])['entry'], CID.parse(entry['hash']))
        self.assertNotIn(CID.parse(entry['hash']), blocks)
        s, got = self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'entry', rkey=rev)
        self.assertEqual((s, got['uri'], got['cid'], got['value']), (200, f'at://{REPO}/{NS}entry/{rev}', str(value), {'$type': NS + 'entry', 'entry': {'$link': entry['hash']}, 'height': 7}))
        code, owned, _ = self.front.repo.serve(self.world, 'GET', 'com.atproto.sync.getRecord',
                                               {'did': REPO, 'collection': NS + 'entry', 'rkey': rev}, OWNER)
        blocks = read_car(owned)[1]
        self.assertEqual(blocks[CID.parse(entry['hash'])], entry['bytes'])  # the owner's proof carries the entry, hashing to its link
        self.assertEqual(self.xrpc('com.atproto.sync.getRecord', did=REPO, collection=NS + 'entry', rkey='2222222222222')[0], 400)

    def test_entry_records_list_by_height_both_ways(self):
        def walk(**more):
            got, cursor = [], None
            while True:
                s, page = self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'entry', limit=3, **more, **({'cursor': cursor} if cursor else {}))
                self.assertEqual(s, 200, page)
                got += page['records']
                cursor = page.get('cursor')
                if not cursor:
                    return got
        forward = walk()
        self.assertEqual([r['value']['height'] for r in forward], list(range(1, len(self.world.entries) + 1)))
        self.assertEqual(walk(reverse='true'), forward[::-1])
        self.assertEqual(self.xrpc('com.atproto.repo.describeRepo', repo=REPO)[1]['collections'][-1], NS + 'entry')

    def test_an_append_extends_the_chain_and_since_carries_only_the_difference(self):
        s, before = self.xrpc('com.atproto.sync.getLatestCommit', did=REPO)
        s, old = self.xrpc('com.atproto.sync.getRepo', did=REPO)
        self.world.append(OWNER, 'later')
        s, car = self.xrpc('com.atproto.sync.getRepo', did=REPO, since=before['rev'])
        root, commit, blocks = self.checked(car)
        self.assertEqual(commit['prev'], CID.parse(before['cid']))
        self.assertGreater(commit['rev'], before['rev'])
        records = [decode(b) for b in blocks.values() if decode(b).get('$type')]
        self.assertEqual([r['height'] for r in records], [len(self.world.entries)])
        self.assertLess(len(blocks), len(read_car(old)[1]))
        pairs = leaves({**read_car(old)[1], **blocks}, commit['data'])  # the old export and the difference: the whole new tree
        self.assertEqual(len(pairs), len(self.world.entries))
        self.assertEqual(self.xrpc('com.atproto.sync.getRepo', did=REPO, since='2222222222222')[0], 400)

    def test_without_a_key_the_signed_routes_are_refused_by_name(self):
        bare = Repo(ORIGIN)
        self.assertNotIn('verificationMethod', bare.did_document())
        for nsid in ('com.atproto.sync.getRepo', 'com.atproto.sync.getLatestCommit', 'com.atproto.sync.listRepos'):
            code, body, _ = bare.serve(self.world, 'GET', nsid, {'did': REPO}, None)
            self.assertEqual((code, body['error']), (400, 'RepoNotServed'), nsid)


if __name__ == '__main__':
    unittest.main()
