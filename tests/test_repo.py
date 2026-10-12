"""The journal as a read-only AT Protocol repository over a real `serve`: records by slug and CID agree
with the host, blocks hash to their CIDs, private records stay private.

Evidence for FOUNDATION §2 Journal, §7 (layer: transport).

The read-only AT Protocol repository (transport/repo.py, docs/REPO.md) against a real `serve`: a Garden, a
planting, a refusal, a publication and a private counter.

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
from transport.config import LIBRARY
from transport.atproto import sign
from transport.atproto.cbor import CID, block, decode, encode, read_car
from transport.atproto.mst import Tree, common_prefix, layer
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
NS = 'town.delvetalk.'


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
        return self.get(f'/xrpc/{nsid}?{urlencode(q)}', token, raw)

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


    def test_list_records_pages_receipts_by_height_both_ways(self):
        pages, cursor = [], None
        while True:
            s, page = self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'receipt', limit=2, **({'cursor': cursor} if cursor else {}))
            self.assertEqual(s, 200, page)
            self.assertLessEqual(len(page['records']), 2)
            pages.append(page['records'])
            cursor = page.get('cursor')
            if not cursor:
                break
        records = [r for p in pages for r in p]
        heights = [r['value']['height'] for r in records]
        self.assertEqual(heights, sorted(set(heights)), heights)
        self.assertGreater(len(pages), 2)
        self.assertLessEqual({r['hash'] for r in self.receipts.values()}, {r['cid'] for r in records})
        for r in records:
            self.assertEqual((r['value']['$type'], r['uri']), (NS + 'receipt', f"at://{REPO}/{NS}receipt/{r['value']['slug']}"))
        s, newest = self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'receipt', limit=3, reverse='true')
        s, older = self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'receipt', limit=100, reverse='true', cursor=newest['cursor'])
        self.assertEqual(newest['records'] + older['records'], records[::-1])
        self.assertEqual(self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'receipt', limit=0)[0], 400)

    def test_sources_sharing_one_entry_page_one_at_a_time_both_ways_and_none_is_skipped(self):
        def walk(**more):
            got, cursor = [], None
            while True:
                s, page = self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'source', limit=1, **more, **({'cursor': cursor} if cursor else {}))
                self.assertEqual(s, 200, page)
                got += page['records']
                cursor = page.get('cursor')
                if not cursor:
                    return got
        s, whole = self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'source', limit=100)
        heights = [r['value']['height'] for r in whole['records']]
        self.assertGreater(len(heights), len(set(heights)), 'the library entry holds several sources at one height')
        self.assertEqual([r['cid'] for r in walk()], [r['cid'] for r in whole['records']])
        self.assertEqual([r['cid'] for r in walk(reverse='true')], [r['cid'] for r in whole['records']][::-1])

    def test_get_record_by_slug_equals_by_cid_equals_world_receipt(self):
        tok = self.login()
        for intent in ('plant-1', 'miss', 'pub-1'):
            for token, reader in ((None, 'anonymous'), (tok, DID)):
                truth = self.receipt(intent, reader)
                truth = truth['receipt'] if truth['status'] == 'receipt' else {**truth, 'height': self.receipts[intent]['height'],
                                                                                 'hash': self.receipts[intent]['hash']}
                got = [self.xrpc('com.atproto.repo.getRecord', token, repo=REPO, collection=NS + 'receipt', rkey=k)
                       for k in (self.receipts[intent]['slug'], self.receipts[intent]['hash'])]
                for s, r in got:
                    self.assertEqual((s, r['cid']), (200, self.receipts[intent]['hash']), r)
                    self.assertEqual({k: v for k, v in r['value'].items() if k != '$type'}, truth)
                self.assertEqual(got[0][1]['value'], got[1][1]['value'])
        public = self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'receipt', rkey=self.receipts['miss']['slug'])[1]['value']
        self.assertEqual((public['status'], public['class'], public['root']), ('refused', 'unknownObject', {'object': 'nope'}))
        self.assertNotIn('identity', public)
        s, e = self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'receipt', rkey='babab-babab')
        self.assertEqual((s, e['error']), (400, 'RecordNotFound'), e)
        s, e = self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'receipt', rkey=self.receipts['miss']['slug'],
                         cid=self.receipts['pub-1']['hash'])
        self.assertEqual((s, e['error']), (400, 'RecordNotFound'))

    def test_sync_get_record_is_the_entrys_block_under_its_cid(self):
        tok = self.login()
        whole = self.receipt('plant-1', DID)['receipt']
        s, (car, ctype) = self.xrpc('com.atproto.sync.getRecord', tok, raw=True, did=REPO, collection=NS + 'receipt', rkey=whole['slug'])
        self.assertEqual((s, ctype), (200, 'application/vnd.ipld.car'), car)
        n, i = varint(car, 0)
        header, end = cbor(car, i)
        self.assertEqual(end, i + n)
        self.assertEqual(header, {'roots': [('cid', b'\x00' + cid_bytes(whole['hash']))], 'version': 1})
        n, i = varint(car, end)
        self.assertEqual(i + n, len(car))
        cid, block = car[i:i + 36], car[i + 36:i + n]
        self.assertEqual(cid, cid_bytes(whole['hash']))
        self.assertEqual(cid[:4], b'\x01\x71\x12\x20')  # CIDv1, dag-cbor, sha2-256, 32 bytes
        self.assertEqual(hashlib.sha256(block).digest(), cid[4:])
        value, used = cbor(block)
        self.assertEqual(used, len(block))
        self.assertEqual(value, {k: v for k, v in whole.items() if k not in ('hash', 'slug')})
        self.assertEqual(self.xrpc('com.atproto.sync.getRecord', tok, raw=True, did=REPO, collection=NS + 'receipt', rkey=whole['hash'])[1][0], car)
        s, e = self.xrpc('com.atproto.sync.getRecord', did=REPO, collection=NS + 'receipt', rkey=whole['slug'])
        self.assertEqual((s, e['error']), (403, 'Denied'), e)  # a projection is not the block its CID names

    def test_get_repo_a_write_and_a_bad_bearer_are_refused_by_name(self):
        s, e = self.xrpc('com.atproto.sync.getRepo', did=REPO)
        self.assertEqual((s, e['error']), (400, 'RepoNotServed'))
        self.assertIn('com.atproto.sync.getRecord', e['hint'])
        s, e = self.xrpc('com.atproto.repo.createRecord')
        self.assertEqual((s, e['error']), (501, 'MethodNotImplemented'))
        s, e = self.xrpc('com.atproto.repo.describeRepo', 'dt_agent_' + 'A' * 43, repo=REPO)
        self.assertEqual((s, e['error']), (401, 'InvalidToken'))  # a bad bearer is not the public reader

    @signs
    def test_signed_over_the_real_journal_every_leaf_names_its_entry(self):
        repo = Repo(ORIGIN, sign.Key.generate())
        code, car, _ = repo.serve(self.host, 'GET', 'com.atproto.sync.getRepo', {'did': REPO}, None)
        self.assertEqual(code, 200, car)
        [root], blocks = read_car(car)
        commit = decode(blocks[root])
        hashes = [e['hash'] for e in self.host.send({'op': 'world-entries', 'principal': 'anonymous', 'limit': 100})['entries']]
        self.assertEqual([decode(blocks[v])['entry'] for _, v in leaves(blocks, commit['data'])], [CID.parse(h) for h in hashes])
        whole = self.receipt('plant-1', DID)['receipt']
        code, proof, _ = repo.serve(self.host, 'GET', 'com.atproto.sync.getRecord', {'did': REPO, 'collection': NS + 'receipt', 'rkey': whole['slug']}, DID)
        self.assertEqual(decode(read_car(proof)[1][CID.parse(whole['hash'])])['height'], whole['height'])  # the host's own bytes, under its CID

    def test_a_private_objects_record_is_refused_to_the_public_and_served_to_its_owner(self):
        tok = self.login()
        s, e = self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'object', rkey='diary.0')
        self.assertEqual((s, e['error']), (403, 'Denied'), e)
        s, r = self.xrpc('com.atproto.repo.getRecord', tok, repo=REPO, collection=NS + 'object', rkey='diary.0')
        self.assertEqual(s, 200, r)
        self.assertEqual(self.xrpc('com.atproto.repo.getRecord', tok, repo=REPO, collection=NS + 'object', rkey='diary/0')[0], 400)  # the old <object>/<version> key is gone
        cid = self.host.send({'op': 'world-state-cid', 'principal': DID, 'object': 'diary', 'version': 0})['cid']
        pin = self.host.send({'op': 'world-inspect', 'principal': DID, 'object': 'diary'})['pin']
        self.assertEqual((r['uri'], r['cid'], r['value']['stateCid'], r['value']['pin']), (f'at://{REPO}/{NS}object/diary.0', cid, cid, pin))
        listed = lambda token=None: [x['value']['object'] for x in self.xrpc('com.atproto.repo.listRecords', token, repo=REPO, collection=NS + 'object')[1]['records']]
        self.assertNotIn('diary', listed())
        self.assertIn('diary', listed(tok))
        self.assertIn('garden/bell/1', listed())
        s, garden = self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'object', rkey='garden.1')
        self.assertEqual((s, garden['value']['object'], garden['value']['version']), (200, 'garden', 1), garden)
        s, bell = self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'object', rkey='garden~bell~1.0')
        self.assertEqual((s, bell['uri'], bell['value']['object']), (200, f'at://{REPO}/{NS}object/garden~bell~1.0', 'garden/bell/1'), bell)
        self.assertEqual(self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'object', rkey='garden/bell/1/0')[0], 400)  # the old <object>/<version> key is gone
        laws = self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'law')[1]['records']
        self.assertIn(f'at://{REPO}/{NS}law/garden~bell~1.kind', [x['uri'] for x in laws])  # under "kind/bell"
        self.assertNotIn('diary', [x['value']['object'] for x in laws])


    def test_objects_and_laws_page_by_limit_and_the_cursor_resumes_exactly(self):
        tok = self.login()
        for c in ('object', 'law'):
            lister = lambda **q: self.xrpc('com.atproto.repo.listRecords', tok, repo=REPO, collection=NS + c, **q)
            s, whole = lister(limit=100)
            keys, cursor, seen = [r['uri'] for r in whole['records']], None, []
            self.assertGreater(len(keys), 2, c)
            for _ in range(len(keys) + 1):
                s, page = lister(limit=2, **({'cursor': cursor} if cursor else {}))
                self.assertEqual(s, 200, page)
                self.assertLessEqual(len(page['records']), 2)
                seen += [r['uri'] for r in page['records']]
                cursor = page.get('cursor')
                if not cursor:
                    break
            self.assertEqual(seen, keys, c)

    def test_every_listed_record_key_is_in_record_key_syntax(self):
        tok = self.login()
        for c in ('receipt', 'object', 'source', 'publication', 'grant', 'law'):
            for token in (None, tok):
                s, page = self.xrpc('com.atproto.repo.listRecords', token, repo=REPO, collection=NS + c, limit=100)
                self.assertEqual(s, 200, page)
                for r in page['records']:
                    key = r['uri'].split(f'{NS}{c}/', 1)[1]
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
            self.assertEqual(Repo(ORIGIN, sign.Key.load(path)).did_document()['verificationMethod'][0]['publicKeyMultibase'],
                             sign.Key.load(path).did_key.removeprefix('did:key:'))

    def test_tids_sort_as_their_time(self):
        times = [0, 1, 1023, 1 << 40, 60_000_000 * 29_000_000 + 7, (1 << 53) - 1]
        tids = [sign.tid(t) for t in times]
        self.assertEqual(tids, sorted(tids))
        for t in tids:
            self.assertRegex(t, r'\A[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}\Z')


class World:
    """A fake host: a journal of DAG-CBOR entries chained by CID, read as the host's ops answer them."""

    def __init__(self, page=4):
        self.entries, self.page = [], page

    def append(self, principal, intent, tag='admitted'):
        h = len(self.entries) + 1
        body = {'height': h, 'identity': {'principal': principal, 'intent': intent}, 'turn': 0, 'roots': [],
                'outcome': {'tag': tag}, **({'previous': self.entries[-1]['hash']} if self.entries else {})}
        cid, data = block(body)
        self.entries.append({**body, 'hash': str(cid), 'bytes': data})

    def send(self, q):
        whole = lambda e: e['identity']['principal'] == q.get('principal')
        if q['op'] == 'world-entries':
            after, limit = q.get('after', 0), min(q.get('limit', 100), self.page)
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
        st = State(cls.tmp.name)
        ident = identity.Identity(st, delve.Client(Provider()), clock=lambda: cls.now[0])
        cls.front = Front(st, cls.world, ident, ('127.0.0.1', 0), clock=lambda: cls.now[0])
        cls.front.repo = Repo(ORIGIN, cls.key)
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
        self.assertIn('getRepo?since', e['hint'])
        twin = Repo(ORIGIN, self.key)  # another process with the same key signs the same chain
        self.assertEqual(twin.serve(self.world, 'GET', 'com.atproto.sync.getRepo', {'did': REPO}, None)[1], car)

    def test_get_record_proves_the_record_from_the_signed_root(self):
        s, car = self.xrpc('com.atproto.sync.getRepo', did=REPO)
        pairs = leaves(read_car(car)[1], decode(read_car(car)[1][read_car(car)[0][0]])['data'])
        entry = self.world.entries[6]
        rev = pairs[6][0].decode().split('/')[1]
        for collection, rkey in (('entry', rev), ('receipt', entry['hash']), ('receipt', rev)):
            s, proof = self.xrpc('com.atproto.sync.getRecord', did=REPO, collection=NS + collection, rkey=rkey)
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
                                               {'did': REPO, 'collection': NS + 'receipt', 'rkey': entry['hash']}, OWNER)
        blocks = read_car(owned)[1]
        self.assertEqual(blocks[CID.parse(entry['hash'])], entry['bytes'])  # the owner's proof carries the entry, hashing to its link
        self.assertEqual(self.xrpc('com.atproto.sync.getRecord', did=REPO, collection=NS + 'receipt', rkey='2222222222222')[0], 400)

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
