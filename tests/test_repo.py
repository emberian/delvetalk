"""The journal as a read-only AT Protocol repository over a real hostd: records by slug and CID agree
with the host, blocks hash to their CIDs, private records stay private.

Evidence for FOUNDATION §2 Journal, §7 (layer: transport).

The read-only AT Protocol repository (transport/repo.py, docs/REPO.md) against a real hostd: a Garden, a
planting, a refusal, a publication and a private counter.

Refuted by: a receipt read by slug, by CID and by world-receipt differing; a sync CAR whose block does not
hash to the entry's CID (checked with this file's own DAG-CBOR decoder); a private object's record served to
the public reader or refused to its owner; a cursor that skips or repeats an entry; did.json naming another DID.
"""
import base64
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path

from tests.host import serve, start_hostd, stop_hostd
from tests.test_chain import garden_state
from tests.test_http import DID, PEOPLE, Provider
from tests.test_turn_world import BINARY, closure, counter_modules, label, nat, record
from transport import delve, identity
from transport.hostproc import LIBRARY, HostClient
from transport.http import Front, RemoteHeaps
from transport.identity import ORIGIN

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
        cls.hostd = start_hostd(cls.tmp.name, BINARY, opener=DID, library=LIBRARY)
        sock = Path(cls.tmp.name) / 'host.sock'
        cls.host = HostClient(sock)
        cls.now, cls.token = [1000.0], None
        ident = identity.Identity(cls.tmp.name, delve.Client(cls.provider), clock=lambda: cls.now[0])
        cls.front = Front(('127.0.0.1', 0), cls.host, ident, clock=lambda: cls.now[0],
                          heaps=RemoteHeaps(sock, Path(cls.tmp.name) / 'heaps'), repl=HostClient(sock, stateless=True))
        cls.port = cls.front.server_address[1]
        serve(cls.front)
        send = cls.host.send
        seeded = [
            send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-g', 'object': 'garden',
                  'modules': closure('Garden'), 'entry': 'initial', 'seed': garden_state(0)}),
            send({'op': 'world-turn', 'principal': DID, 'object': 'garden', 'method': 'plant', 'identity': 'plant-1',
                  'argument': record(colour=label('amber'), seed=label('a moth bell'))}),
            send({'op': 'world-turn', 'principal': DID, 'object': 'nope', 'method': 'receive', 'argument': record(), 'identity': 'miss'}),
            send({'op': 'world-turn', 'principal': DID, 'object': 'garden', 'method': 'publish', 'argument': record(), 'identity': 'pub-1'}),
            send({'op': 'world-create', 'principal': DID, 'identity': 'mk-d', 'object': 'diary', 'modules': counter_modules(),
                  'entry': 'initial', 'seed': record(count=nat(0)), 'read': {'principals': [DID]}})]
        assert [r['status'] for r in seeded] == ['created', 'admitted', 'refused', 'admitted', 'created'], seeded
        cls.receipts = {r['receipt']['identity']['intent']: r['receipt'] for r in seeded}

    @classmethod
    def tearDownClass(cls):
        cls.front.shutdown()
        cls.front.server_close()
        stop_hostd(cls.hostd)
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
        s, v = self.call_post('/AGENTS.md/verify', {'handle': 'talkie.delve.town', 'uri': f'at://{DID}/town.delve.feed.post/3abc'})
        self.assertEqual((s, v['status']), (200, 'verified'), v)
        Repository.token = ch['credential']
        return Repository.token

    def call_post(self, path, body):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=60)
        c.request('POST', path, json.dumps(body), {'Content-Type': 'application/json'})
        r = c.getresponse()
        out = (r.status, json.loads(r.read()))
        c.close()
        return out

    def receipt(self, intent, reader='anonymous'):
        return self.host.send({'op': 'world-receipt', 'principal': reader, 'identity': intent, 'of': DID})

    def test_the_did_document_names_the_repo_and_its_handle_resolves_to_it(self):
        s, doc = self.get('/.well-known/did.json')
        self.assertEqual((s, doc['id'], doc['alsoKnownAs']), (200, REPO, ['at://' + HOST]), doc)
        self.assertEqual(doc['service'], [{'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer',
                                           'serviceEndpoint': ORIGIN}])
        s, d = self.xrpc('com.atproto.repo.describeRepo', repo=REPO)
        self.assertEqual((s, d['did'], d['didDoc']), (200, REPO, doc))
        self.assertEqual(d['collections'], [NS + c for c in ('receipt', 'object', 'source', 'publication', 'grant', 'law')])
        self.assertEqual(self.xrpc('com.atproto.repo.describeRepo', repo=HOST)[1]['did'], REPO)
        self.assertEqual(self.xrpc('com.atproto.repo.describeRepo', repo='did:plc:other')[1]['error'], 'RepoNotFound')
        self.assertEqual(self.xrpc('com.atproto.identity.resolveHandle', handle=HOST), (200, {'did': REPO}))
        self.assertEqual(self.xrpc('com.atproto.identity.resolveHandle', handle='talkie.delve.town')[1]['error'], 'HandleNotFound')

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

    def test_get_repo_is_refused_by_name_with_a_hint(self):
        s, e = self.xrpc('com.atproto.sync.getRepo', did=REPO)
        self.assertEqual((s, e['error']), (400, 'RepoNotServed'))
        self.assertIn('com.atproto.sync.getRecord', e['hint'])
        s, e = self.xrpc('com.atproto.repo.createRecord')
        self.assertEqual((s, e['error']), (501, 'MethodNotImplemented'))

    def test_a_private_objects_record_is_refused_to_the_public_and_served_to_its_owner(self):
        tok = self.login()
        s, e = self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'object', rkey='diary.0')
        self.assertEqual((s, e['error']), (403, 'Denied'), e)
        s, r = self.xrpc('com.atproto.repo.getRecord', tok, repo=REPO, collection=NS + 'object', rkey='diary.0')
        self.assertEqual(s, 200, r)
        self.assertEqual(self.xrpc('com.atproto.repo.getRecord', tok, repo=REPO, collection=NS + 'object', rkey='diary/0'), (s, r))  # the old form, one release
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
        self.assertEqual(self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'object', rkey='garden/bell/1/0'), (s, bell))
        laws = self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'law')[1]['records']
        self.assertIn(f'at://{REPO}/{NS}law/garden~bell~1.owner', [x['uri'] for x in laws])
        self.assertNotIn('diary', [x['value']['object'] for x in laws])

    def test_sources_and_publications_are_records_and_no_grant_is_listed(self):
        s, sources = self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'source')
        self.assertIn('Garden', [x['value']['name'] for x in sources['records']])
        first = sources['records'][0]
        s, one = self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'source', rkey=first['cid'])
        self.assertEqual((s, one), (200, first))
        s, pubs = self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'publication')
        [pub] = pubs['records']
        self.assertEqual((pub['value']['page'], pub['cid']), ('garden', self.receipts['pub-1']['hash']))
        self.assertEqual(pub['uri'], f"at://{REPO}/{NS}publication/{pub['value']['id']}")
        self.assertEqual(self.xrpc('com.atproto.repo.listRecords', repo=REPO, collection=NS + 'grant'), (200, {'records': []}))
        s, e = self.xrpc('com.atproto.repo.getRecord', repo=REPO, collection=NS + 'grant', rkey='x')
        self.assertEqual((s, e['error']), (400, 'InvalidRequest'))

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

    def test_a_bad_bearer_is_401_not_the_public_reader(self):
        s, e = self.xrpc('com.atproto.repo.describeRepo', 'dt_agent_' + 'A' * 43, repo=REPO)
        self.assertEqual((s, e['error']), (401, 'InvalidToken'))


if __name__ == '__main__':
    unittest.main()
