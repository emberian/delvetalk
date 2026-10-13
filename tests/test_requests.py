"""Acting by record (docs/ATPROTO.md §2, L1): a resident writes `online.fg-goose.gsb.request` in their own repository; the
poller proves it from the signed commit and the author's DID document, the bridge runs it as the same turn a post's
spell is, under the record's at-uri, and answers with an `online.fg-goose.gsb.answer` value the façade projects and the mirror
writes as a posting-account record byte for byte.

Evidence for docs/ATPROTO.md §2 (layer: transport), on a fake PDS here: repositories signed with real keys, served
over two loopback PDSes, listRepos, listRecords, getLatestCommit, sync.getRecord, PLC and did:web.

Refuted by: a request read twice making two entries; a record signed by a key other than its DID document's making a
turn; a stale `if` admitted; an answer whose CID differs between the façade and the mirror's write; a `try`, a request
to another service or one created before the world began observing being run; an answer carrying a private turn's
offers; a request whose key sorts below one already read being missed; a migrated participant reading stale state
or losing consumption; a key rotation refused without refreshing; an unsafe discovered PDS receiving a request.
"""
import dataclasses
import json
import socket
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from tests.host import served
from tests.test_bridge import DID, LOOPBACK, Stub, modules
from tests.test_chain import town_garden
from transport.lexicon import record_problems
from transport import bridge, delve, identity, mirror, observe
from transport.atproto.cbor import CID, block, car, encode, from_json
from transport.atproto.mst import Tree
from transport.atproto.sign import CURVES, multikey, tid
from transport.delve import canonical
from transport.host import HostClient
from transport.repo import Repo, world_did
from transport.requests import COLLECTION, Poller, proven
from transport.config import Config
from transport.state import State
from tests.wire import nat, record

SERVICE = world_did(LOOPBACK.origin)[0]
HANDLE = 'talkie.delve.town'
PLC = 'https://plc.directory/'


def sign(private, message):
    """ECDSA over sha-256, low-S, 64 raw bytes (randomized: the verifier is what is under test)."""
    r, s = decode_dss_signature(private.sign(message, ec.ECDSA(hashes.SHA256())))
    order = CURVES['secp256k1'][2]
    return r.to_bytes(32, 'big') + min(s, order - s).to_bytes(32, 'big')


class FakePDS:
    """pds.delve.town and plc.directory for the poller: each repository's records under a key of its own, its commits
    signed by `signer` (its DID document's key unless a test swaps it)."""

    def __init__(self, base=delve.PDS, documents=None):
        self.base, self.documents = base, documents if documents is not None else {}
        self.repos, self.calls, self.proof, self.listing = {}, [], None, None

    def repo(self, did, pds=delve.PDS):
        key = ec.generate_private_key(ec.SECP256K1())
        self.repos[did] = {'key': key, 'signer': key, 'records': {}, 'rev': 0, 'pds': pds}
        self.documents[did] = self.repos[did]
        return self.repos[did]

    def put(self, did, rkey, value):
        r = self.repos[did]
        r['records'][rkey] = value
        r['rev'] += 1

    def commit(self, did):
        r = self.repos[did]
        tree, blocks = Tree(), {}
        for rkey in sorted(r['records']):
            cid, data = block(from_json(r['records'][rkey]))
            blocks[rkey] = (cid, data)
            tree.append(f'{COLLECTION}/{rkey}'.encode(), cid)
        unsigned = {'did': did, 'version': 3, 'data': tree.root(), 'rev': tid(r['rev']), 'prev': None}
        return tree, blocks, block({**unsigned, 'sig': sign(r['signer'], encode(unsigned))})

    def __call__(self, method, url, headers, body):
        self.calls.append(url)
        parts = urllib.parse.urlsplit(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
        if url.startswith(PLC) or parts.path == '/.well-known/did.json':
            did = parts.path[1:] if url.startswith(PLC) else 'did:web:' + parts.hostname
            r = self.documents.get(did)
            if not r:
                return 404, b'{"error":"NotFound"}'
            doc = {'id': did, 'alsoKnownAs': [f'at://{HANDLE}'], 'service': [{'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer', 'serviceEndpoint': r['pds']}],
                   'verificationMethod': [{'id': did + '#atproto', 'type': 'Multikey', 'controller': did, 'publicKeyMultibase': multikey(r['key'].public_key())}]}
            return 200, json.dumps(doc).encode()
        nsid = parts.path.rsplit('/', 1)[-1]
        if nsid in ('town.delve.feed.searchPosts', 'town.delve.feed.getFeed'):
            return 200, b'{"posts":[],"feed":[]}'
        if nsid == 'com.atproto.sync.listRepos':
            return 200, json.dumps({'repos': [{'did': d, 'rev': tid(r['rev']), 'head': 'x', 'active': True} for d, r in self.repos.items()]}).encode()
        r = self.repos.get(q.get('repo') or q.get('did'))
        if nsid == 'com.atproto.sync.getLatestCommit':
            return 200, json.dumps({'rev': tid(r['rev']), 'cid': str(self.commit(q['did'])[2][0])}).encode()
        if nsid == 'com.atproto.repo.listRecords':
            _, blocks, _ = self.commit(q['repo'])
            records = [{'uri': f"at://{q['repo']}/{COLLECTION}/{k}", 'cid': str(blocks[k][0]), 'value': r['records'][k]}
                       for k in sorted(r['records'])]
            return 200, json.dumps({'records': self.listing(q, records) if self.listing else records}).encode()
        if nsid == 'com.atproto.sync.getRecord':
            tree, blocks, commit = self.commit(q['did'])
            at = sorted(r['records']).index(q['rkey'])
            raw = car(commit[0], [commit, *tree.proof(at), blocks[q['rkey']]])
            return 200, self.proof(q, raw) if self.proof else raw
        return 404, b'{"error":"NoSuchMethod"}'


class PDSHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        status, raw = self.server.pds('GET', self.headers['X-Fixture-URL'], {}, None)
        self.send_response(status)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class PDSPair:
    """Two loopback HTTP PDSes; injected routing preserves their HTTPS identities and a shared PLC/did:web source."""
    B = 'https://pds.resident.example'

    def __init__(self, cleanup):
        self.a = FakePDS()
        self.b = FakePDS(self.B, self.a.documents)
        self.servers = {}
        self.calls = []
        for pds in (self.a, self.b):
            server = ThreadingHTTPServer(('127.0.0.1', 0), PDSHandler)
            server.pds = pds
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cleanup(server.server_close)
            cleanup(thread.join)
            cleanup(server.shutdown)
            self.servers[pds.base] = server

    def __call__(self, method, url, headers, body):
        self.calls.append(url)
        parts = urllib.parse.urlsplit(url)
        base = urllib.parse.urlunsplit((parts.scheme, parts.netloc, '', '', ''))
        server = self.servers.get(base)
        if url.startswith(PLC) or parts.path == '/.well-known/did.json' or base == delve.APPVIEW:
            server = self.servers[delve.PDS]
        if server is None:
            raise AssertionError('unexpected destination ' + url)
        wire = f'http://127.0.0.1:{server.server_address[1]}' + parts.path + '?' + parts.query
        return delve.http_transport(method, wire, {**headers, 'X-Fixture-URL': url}, body)

    def count(self, base, nsid):
        return sum(url.startswith(base + '/xrpc/' + nsid + '?') for url in self.calls)

    def documents(self, did):
        target = PLC + did if did.startswith('did:plc:') else 'https://' + did[8:] + '/.well-known/did.json'
        return self.calls.count(target)


def request(spell=None, created='2026-10-12T10:00:00Z', service=SERVICE, **more):
    call = {'spell': spell} if spell is not None else more.pop('call')
    return {'$type': COLLECTION, 'service': service, 'mode': more.pop('mode', 'act'), 'calls': more.pop('calls', [call]), 'createdAt': created, **more}


PLANT = 'delvetalk garden-1 plant\nseed: a\ncolour: amber'


class RequestIdentity(unittest.TestCase):
    """Signed request proofs cannot consume a different repository's URI or another world's service address."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.st = State(Path(tmp.name) / 'state', config=dataclasses.replace(LOOPBACK, origin='https://world.example'))
        self.pds, self.host = FakePDS(), Stub()
        self.pds.repo(DID)
        self.client = delve.Client(self.pds)
        self.service = world_did(self.st.config.origin)[0]
        self.poller = Poller(self.st, self.client)

    def observer(self):
        ob = observe.Observer(self.st, self.client, '2026-10-12T00:00:00Z', self.poller)
        self.addCleanup(ob.db.close)
        return ob

    def step(self):
        ob = self.observer()
        return bridge.run(self.st, self.host, ob, now=observe.instant('2026-10-12T10:00:00Z'))

    def refused(self):
        return json.loads(self.st.requests.read_text())['refused']

    def test_a_signed_proof_with_b_uri_cannot_observe_answer_or_suppress_bs_request(self):
        other, rkey = 'did:plc:' + 'b' * 24, '3aaaaaaaaaaa2'
        uri = f'at://{other}/{COLLECTION}/{rkey}'
        self.pds.put(DID, rkey, request(PLANT, service=self.service))
        cid, value, _ = proven(self.client, DID, rkey, self.client.did_document(DID))
        self.assertEqual(value, request(PLANT, service=self.service))
        self.assertEqual(cid, str(block(from_json(value))[0]))
        self.pds.listing = lambda q, rows: [{**row, 'uri': uri} for row in rows] if q['repo'] == DID else rows
        ob = self.observer()
        with mock.patch.object(ob, 'seen', wraps=ob.seen) as seen:
            self.assertEqual(bridge.run(self.st, self.host, ob)['failed'], [])
        seen.assert_not_called()
        self.assertEqual(self.st.observations(), [])
        self.assertFalse(bridge.answer_path(self.st, bridge.request_source({'uri': uri, 'cid': cid})).exists())
        self.assertNotIn(uri, self.refused())
        self.assertEqual(self.refused(), {'listing:' + DID: {'why': 'bad_request_uri: ' + DID}})

        self.pds.repo(other)
        genuine = request('delvetalk garden-1 plant\nseed: b\ncolour: violet', service=self.service)
        self.pds.put(other, rkey, genuine)
        self.assertEqual(self.step()['failed'], [])
        (obs,) = self.st.observations()
        self.assertEqual((obs['uri'], obs['author']['did'], obs['cid']),
                         (uri, other, str(block(from_json(genuine))[0])))
        answer = json.loads(bridge.answer_path(self.st, bridge.request_source(obs)).read_text())
        self.assertEqual(answer['source']['request'], {'uri': uri, 'cid': obs['cid']})
        self.assertEqual(answer['outcome']['status'], 'admitted')
        self.assertEqual([(op['principal'], op['identity']) for op in self.host.ops if op['op'] == 'world-turn'], [(other, uri)])

        self.pds.listing = None
        self.pds.put(DID, rkey, value)
        self.assertEqual(self.step()['failed'], [])
        self.assertEqual({obs['uri'] for obs in self.st.observations()}, {uri, f'at://{DID}/{COLLECTION}/{rkey}'})

    def test_malformed_or_misaddressed_listings_are_refused_before_seen_or_proof_reads(self):
        rkey = '3aaaaaaaaaaa2'
        uri = f'at://{DID}/{COLLECTION}/{rkey}'
        invalid = [None, 42, {}, '', uri.replace('at://', 'https://'), uri.replace(DID, HANDLE),
                   uri.replace(COLLECTION, 'town.delve.feed.post'), uri + '/extra', uri + '?x=1', uri + '#fragment',
                   uri + '\n', uri.replace(rkey, ''), uri.replace(rkey, '%33aaaaaaaaaaa2')]
        ob = self.observer()
        for n, listed_uri in enumerate(invalid):
            with self.subTest(uri=listed_uri):
                self.pds.put(DID, rkey, request(PLANT, service=self.service, created=f'2026-10-12T10:00:{n:02d}Z'))
                self.pds.listing = lambda q, rows: [{**row, 'uri': listed_uri} for row in rows]
                before = sum('com.atproto.sync.getRecord?' in url for url in self.pds.calls)
                with mock.patch.object(ob, 'seen', wraps=ob.seen) as seen:
                    self.assertEqual(self.poller.poll(ob), [])
                seen.assert_not_called()
                self.assertEqual(sum('com.atproto.sync.getRecord?' in url for url in self.pds.calls), before)
                self.assertEqual(self.st.observations(), [])
                self.assertEqual(self.refused(), {'listing:' + DID: {'why': 'bad_request_uri: ' + DID}})
        self.assertTrue(all('bad_request_uri' in row['why'] for row in self.refused().values()))

    def test_signed_requests_with_invalid_record_keys_are_refused_without_proof_reads(self):
        invalid = ['', '.', '..', 'a' * 513, 'with space', 'with/slash', 'with%escape', 'with?query', 'with#fragment', 'é']
        for rkey in invalid:
            self.pds.put(DID, rkey, request(PLANT, service=self.service))
        ob = self.observer()
        with mock.patch.object(ob, 'seen', wraps=ob.seen) as seen:
            self.assertEqual(self.poller.poll(ob), [])
        seen.assert_not_called()
        self.assertEqual(self.st.observations(), [])
        self.assertEqual(self.refused(), {'listing:' + DID: {'why': 'bad_request_uri: ' + DID}})
        self.assertFalse(any('com.atproto.sync.getRecord?' in url for url in self.pds.calls))

    def test_malformed_listing_refusals_overwrite_one_bounded_entry_per_did(self):
        other = 'did:plc:' + 'b' * 24
        self.pds.repo(other)
        ob = self.observer()
        for n in range(3):
            for did in (DID, other):
                self.pds.put(did, f'3aaaaaaaaaaa{n + 2}', request(PLANT, service=self.service))
            self.pds.listing = lambda q, rows: [{**row, 'uri': row['uri'] + '?' + 'x' * 65536, 'cid': 'c' * 65536}
                                               for row in rows]
            why = 'bad_request_uri: ' + str(n) * 65536
            with mock.patch('transport.requests.request_uri', side_effect=delve.Failure('bad_request_uri', str(n) * 65536)):
                self.assertEqual(self.poller.poll(ob), [])
            self.assertEqual(self.refused(), {'listing:' + did: {'why': why[:256]} for did in (DID, other)})
            self.assertLess(len(canonical(self.refused())), 1024)
        self.assertEqual(self.st.observations(), [])
        self.assertFalse(any('com.atproto.sync.getRecord?' in url for url in self.pds.calls))

    def test_a_512_character_record_key_and_every_allowed_character_prove_and_are_seen_once(self):
        keys = ['a' * 512, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~:-', '_']
        for rkey in keys:
            self.pds.put(DID, rkey, request(PLANT, service=self.service))
        ob = self.observer()
        self.assertEqual(self.poller.poll(ob), [])
        self.assertEqual({obs['uri'] for obs in self.st.observations()}, {f'at://{DID}/{COLLECTION}/{rkey}' for rkey in keys})
        self.assertEqual(self.refused(), {})
        self.pds.put(DID, keys[0], request(PLANT, service=self.service))
        reads = sum('com.atproto.sync.getRecord?' in url for url in self.pds.calls)
        self.assertEqual(self.poller.poll(ob), [])
        self.assertEqual(sum('com.atproto.sync.getRecord?' in url for url in self.pds.calls), reads)
        self.assertEqual(len(self.st.observations()), len(keys))

    def test_a_ring_poller_runs_the_ring_service_request_and_refuses_the_town_service(self):
        self.st = State(self.st.root, world='ring', config=self.st.config)
        self.poller = Poller(self.st, self.client)
        ring = world_did(self.st.config.origin, 'ring')[0]
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT, service=ring, world='ring'))
        self.pds.put(DID, '3aaaaaaaaaaa3', request(PLANT, service=self.service, world='ring'))
        self.assertEqual(self.step()['failed'], [])
        (obs,) = self.st.observations()
        self.assertEqual(obs['uri'], f'at://{DID}/{COLLECTION}/3aaaaaaaaaaa2')
        self.assertEqual([(op['principal'], op['identity']) for op in self.host.ops if op['op'] == 'world-turn'], [(DID, obs['uri'])])
        self.assertEqual(self.refused(), {f'at://{DID}/{COLLECTION}/3aaaaaaaaaaa3':
                                        {'cid': str(block(from_json(request(PLANT, service=self.service, world='ring')))[0]),
                                         'why': 'addressed to another service'}})
        answer = json.loads(bridge.answer_path(self.st, bridge.request_source(obs)).read_text())
        self.assertEqual(answer['outcome']['status'], 'admitted')


class Requests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st = State(Path(self.tmp.name) / 'state', config=LOOPBACK)
        self.pair = PDSPair(self.addCleanup)
        self.pds = self.pair.a
        self.now = [0.0]
        self.client = delve.Client(self.pair)
        self.poller = Poller(self.st, self.client, clock=lambda: self.now[0])
        self.me = self.pds.repo(DID)
        serving = served(str(Path(self.tmp.name) / 'serve'), cleanup=self.addCleanup)
        self.host = HostClient(serving.sock)
        town_garden(lambda **q: self.host.send(q), id='garden-1')

    def step(self, since='2026-10-12T00:00:00Z'):
        """One bridge step over the fake PDS: observe (posts, then requests), turn, answer."""
        ob = observe.Observer(self.st, self.client, since, self.poller)
        try:
            return bridge.run(self.st, self.host, ob, now=observe.instant('2026-10-12T10:00:00Z'))
        finally:
            ob.db.close()

    def acts(self, principal='anonymous'):
        """Non-clock journal entries, including deliveries, as `principal` may read them."""
        entries, after = [], 0
        while True:
            got = self.host.send({'op': 'world-entries', 'principal': principal, 'after': after, 'limit': 100})
            entries += got['entries']
            if not got.get('more') or not got['entries']:
                return [e for e in entries if (e.get('identity') or {}).get('principal') != 'clock']
            after = got['entries'][-1]['height']

    def assert_plant_entries(self, entries, rkey, bell):
        """One request entry and its bell's `made` delivery, with no unrelated or repeated turn."""
        uri = f'at://{DID}/{COLLECTION}/{rkey}'
        self.assertEqual(len(entries), 2, entries)
        requests = [e for e in entries if e.get('identity') == {'principal': DID, 'intent': uri}]
        self.assertEqual(len(requests), 1, entries)
        request_entry = requests[0]
        self.assertEqual(request_entry['outcome']['tag'], 'admitted')
        self.assertEqual(len(request_entry['sends']), 1)
        sent = request_entry['sends'][0]
        self.assertEqual((sent['to'], sent['method']), (bell, 'made'))
        deliveries = [e for e in entries if e.get('identity') == {'principal': DID, 'intent': sent['id']}]
        self.assertEqual(len(deliveries), 1, entries)
        self.assertEqual(deliveries[0]['delivery']['id'], sent['id'])
        self.assertEqual(deliveries[0]['delivery']['from'], request_entry['identity'])
        self.assertEqual(deliveries[0]['outcome']['tag'], 'admitted')

    def answer(self, rkey, did=DID):
        path = self.st.answers / f'{did}.{rkey}.json'
        if not path.exists():
            return None
        value = json.loads(path.read_text())
        self.assertEqual(record_problems(value), [], value)  # every answer written checks against its lexicon
        return value

    def test_a_request_is_one_turn_under_its_uri_answered_once_however_often_it_is_read(self):
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT))
        ran = self.step()
        self.assertEqual(ran['failed'], [])
        uri = f'at://{DID}/{COLLECTION}/3aaaaaaaaaaa2'
        got = self.host.send({'op': 'world-receipt', 'principal': DID, 'identity': uri})
        self.assertEqual(got['receipt']['outcome']['tag'], 'admitted')
        a = self.answer('3aaaaaaaaaaa2')
        self.assertEqual(a['source']['request']['uri'], uri)
        self.assertEqual(a['receipt'], {'slug': got['receipt']['slug'], 'height': got['receipt']['height'], 'entry': {'$link': got['receipt']['hash']}})
        self.assertIn('Planted', a['offers'][0])
        self.assertIn({'object': 'garden-1', 'version': 1, 'stateCid': a['trace']['writes'][-1]['stateCid']}, a['trace']['writes'])
        acts, first = len(self.acts()), self.answer('3aaaaaaaaaaa2')
        self.pds.put(DID, '3aaaaaaaaaaa3', request('just words'))  # the repo's rev moves: the whole collection is read again
        self.step()
        (self.st.answers / f'{DID}.3aaaaaaaaaaa2.json').unlink()  # the bridge forgets it answered; the observer and host do not
        self.st.observed.unlink()
        self.st.requests.unlink()  # and the poller reads every repository afresh
        self.step()
        self.assertEqual(len(self.acts()), acts)
        self.assertEqual(self.answer('3aaaaaaaaaaa2'), first)  # the same receipt, the same bytes
        self.assertEqual(sum((e.get('identity') or {}).get('intent') == uri for e in self.acts()), 1)

    def test_a_record_signed_by_a_key_not_in_the_did_document_is_no_turn(self):
        self.me['signer'] = ec.generate_private_key(ec.SECP256K1())
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT))
        acts = len(self.acts())
        ran = self.step()
        self.assertEqual(len(self.acts()), acts)
        self.assertIsNone(self.answer('3aaaaaaaaaaa2'))
        refused = json.loads(self.st.requests.read_text())['refused']
        self.assertIn('bad_signature', refused[f'at://{DID}/{COLLECTION}/3aaaaaaaaaaa2']['why'])
        self.assertEqual(ran['turns'], [])
        self.me['signer'] = self.me['key']  # the same record, re-signed by its key under a new rev, proves and runs
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT, created='2026-10-12T10:00:01Z'))
        self.step()
        self.assertEqual(self.answer('3aaaaaaaaaaa2')['outcome']['status'], 'admitted')

    def test_a_try_another_services_request_and_one_from_before_observing_are_never_run(self):
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT, mode='try'))
        self.pds.put(DID, '3aaaaaaaaaaa3', request(PLANT, service='did:web:elsewhere.example'))
        self.pds.put(DID, '3aaaaaaaaaaa4', request(PLANT, created='2026-10-11T23:59:59Z'))
        self.pds.put(DID, '3aaaaaaaaaaa5', request(PLANT, world='ring'))
        self.pds.put(DID, '3aaaaaaaaaaa6', request('delvetalk try\n    ' + PLANT.replace('\n', '\n    ')))  # try by its spell
        acts = len(self.acts())
        self.step()
        self.assertEqual(len(self.acts()), acts)
        self.assertIn(f'at://{DID}/{COLLECTION}/3aaaaaaaaaaa6', self.st.words(self.st.skipped))
        self.assertFalse(any(self.st.answers.glob('*.json')) if self.st.answers.exists() else False)
        whys = {k.rsplit('/', 1)[-1]: v['why'] for k, v in json.loads(self.st.requests.read_text())['refused'].items()}
        self.assertEqual(whys, {'3aaaaaaaaaaa2': 'mode try is never run by record', '3aaaaaaaaaaa3': 'addressed to another service',
                                '3aaaaaaaaaaa4': 'created before this world began observing', '3aaaaaaaaaaa5': 'addressed to another world'})

    def test_a_request_whose_key_sorts_below_one_already_read_is_still_run(self):
        self.pds.put(DID, '3zzzzzzzzzzz2', request(PLANT))
        self.step()
        self.pds.put(DID, '3aaaaaaaaaaa2', request('delvetalk garden-1 plant\nseed: b\ncolour: violet'))
        self.step()
        self.assertEqual(self.answer('3aaaaaaaaaaa2')['outcome']['status'], 'admitted')

    def test_an_object_verb_call_and_a_malformed_one(self):
        self.pds.put(DID, '3aaaaaaaaaaa2', request(call={'object': 'garden-1', 'verb': 'plant', 'fields': {'seed': 'c', 'colour': 'silver'}}))
        self.pds.put(DID, '3aaaaaaaaaaa3', request(call={'object': 'garden-1', 'spell': PLANT}))
        self.pds.put(DID, '3aaaaaaaaaaa4', request('just words to the town'))
        self.step()
        self.assertEqual(self.answer('3aaaaaaaaaaa2')['outcome']['status'], 'admitted')
        self.assertEqual(self.answer('3aaaaaaaaaaa3')['outcome'], {'status': 'invalid', 'line': 'a call is a spell, or an object with a verb (and fields), not both'})
        self.assertEqual(self.answer('3aaaaaaaaaaa4')['outcome']['status'], 'unreached')
        self.assertNotIn('receipt', self.answer('3aaaaaaaaaaa4'))

    def test_a_plan_is_one_turn_of_its_spells_and_a_plan_of_a_verb_call_is_invalid(self):
        self.pds.put(DID, '3aaaaaaaaaaa2', request(call={'spell': PLANT}, mode='plan', calls=[
            {'spell': PLANT}, {'spell': 'delvetalk garden-1 plant\nseed: b\ncolour: violet'}]))
        self.pds.put(DID, '3aaaaaaaaaaa3', request(call={'spell': PLANT}, mode='plan', calls=[{'object': 'garden-1', 'verb': 'plant'}]))
        self.step()
        a, uri = self.answer('3aaaaaaaaaaa2'), f'at://{DID}/{COLLECTION}/3aaaaaaaaaaa2'
        self.assertEqual(a['outcome']['status'], 'admitted', a)
        self.assertEqual([e['height'] for e in self.acts() if (e.get('identity') or {}).get('intent') == uri], [a['height']])
        self.assertEqual([w['version'] for w in a['trace']['writes'] if w['object'] == 'garden-1'], [1])  # both plantings, one write
        self.assertEqual(len(a['offers']), 2)
        self.assertEqual(self.answer('3aaaaaaaaaaa3')['outcome'], {'status': 'invalid', 'line': 'a plan is spells only'})

    def test_an_answer_to_a_turn_on_a_private_thing_says_only_its_receipt(self):
        r = self.host.send({'op': 'world-create', 'principal': 'ember', 'identity': 'mk-diary', 'object': 'diary',
                            'modules': modules('''  match world.offer({to: "", document: Document.text("a secret")}):
    case offered(_): 1n
    case _: 0n'''), 'entry': 'initial', 'seed': record(seen=nat(5)), 'read': {'principals': [DID]}})
        self.assertEqual(r['status'], 'created', r)
        self.pds.put(DID, '3aaaaaaaaaaa2', request('delvetalk diary plant\nseed: a\ncolour: amber'))
        self.step()
        a = self.answer('3aaaaaaaaaaa2')
        self.assertEqual(set(a), {'$type', 'source', 'outcome', 'receipt', 'height'})
        self.assertNotIn('secret', canonical(a))
        self.assertNotIn('diary', canonical(a))

    def test_the_answers_cid_is_the_same_from_the_facade_and_in_the_mirrors_write(self):
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT))
        self.step()
        written = []
        mirror.run(self.st, self.host, lambda c, k, v: written.append((c, k, v)),
                   fetch=lambda *args: (400, b'{"error":"RepoNotServed"}', {}))
        (value,) = [v for c, k, v in written if c == bridge.ANSWER and k == f'{DID}.3aaaaaaaaaaa2']
        pds_cid = block(from_json(json.loads(canonical(value))))[0]  # the PDS hashes the JSON it is sent
        repo = Repo(LOOPBACK.origin, answers=self.st.answers)
        code, got, _ = repo.serve(self.host, 'GET', mirror.NS + 'getProjection',
                                  {'kind': 'answer', 'key': f'{DID}.3aaaaaaaaaaa2'}, None)
        self.assertEqual(code, 200, got)
        self.assertEqual((block(from_json(got['value']))[0], got['value']), (pds_cid, value))
        self.assertIsInstance(from_json(value)['receipt']['entry'], CID)  # a real link, as the lexicon's cid-link
        code, listed, _ = repo.serve(self.host, 'GET', mirror.NS + 'listProjections', {'kind': 'answer'}, None)
        self.assertEqual(code, 200, listed)
        self.assertEqual([block(from_json(r['value']))[0] for r in listed['projections']], [pds_cid])

    def participants(self, *dids):
        self.st.config = dataclasses.replace(self.st.config, participants=' '.join(dids))

    def test_a_configured_resident_on_b_is_admitted_once_without_being_listed_by_a(self):
        other = 'did:plc:' + 'b' * 24
        self.pair.b.repo(other, self.pair.B)
        self.pair.b.put(other, '3aaaaaaaaaaa2', request(PLANT))
        self.participants(other, other)  # the registry is a union
        self.assertEqual(self.step()['failed'], [])
        self.assertEqual(self.answer('3aaaaaaaaaaa2', other)['outcome']['status'], 'admitted')
        self.step()
        uri = f'at://{other}/{COLLECTION}/3aaaaaaaaaaa2'
        self.assertEqual(sum((e.get('identity') or {}).get('intent') == uri for e in self.acts()), 1)
        self.assertNotIn(other, self.pds.repos)
        self.assertEqual(self.pair.count(self.pair.B, 'com.atproto.repo.listRecords'), 1)
        self.assertEqual(self.pair.count(self.pair.B, 'com.atproto.sync.getLatestCommit'), 2)
        self.assertEqual(json.loads(self.st.requests.read_text())['revs'][other], {'pds': self.pair.B, 'rev': tid(1)})

    def test_a_verified_identity_did_on_b_is_polled_but_pending_and_guest_claims_are_not(self):
        other = 'did:plc:' + 'b' * 24
        self.pair.b.repo(other, self.pair.B)
        self.pair.b.put(other, '3aaaaaaaaaaa2', request(PLANT))
        ids = identity.Identity(self.st, self.client)
        try:
            for nonce, did, state in [('verified', other, 'verified'), ('pending', 'did:plc:' + 'c' * 24, 'pending'),
                                      ('guest', 'guest:local:guest', 'verified')]:
                ids.db.execute('INSERT INTO challenges(nonce,did,state) VALUES(?,?,?)', (nonce, did, state))
        finally:
            ids.db.close()
        self.assertEqual(self.step()['failed'], [])
        self.assertEqual(self.answer('3aaaaaaaaaaa2', other)['outcome']['status'], 'admitted')
        self.assertEqual(self.pair.documents('did:plc:' + 'c' * 24), 0)

    def test_migration_reads_b_in_full_preserves_consumption_and_never_reads_as_stale_copy(self):
        # Replaces the fixed-PDS refusal test: an old host's different bytes at the same rkey are never read.
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT))
        self.pds.put(DID, '3aaaaaaaaaaa4', request(PLANT, mode='try'))
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT))  # A and B have the same rev; PDS alone must defeat the skip
        self.step()
        first, before = self.answer('3aaaaaaaaaaa2'), self.acts(principal=DID)
        self.assertEqual(json.loads(self.st.requests.read_text())['revs'][DID]['rev'], tid(3))
        refused = json.loads(self.st.requests.read_text())['refused']
        moved = self.pair.b.repo(DID, self.pair.B)
        moved['key'] = moved['signer'] = self.me['key']  # the stale copy still has a valid signing key
        self.pair.b.put(DID, '3aaaaaaaaaaa2', request(PLANT))
        self.pair.b.put(DID, '3aaaaaaaaaaa3', request('delvetalk garden-1 plant\nseed: b\ncolour: violet'))
        self.pair.b.put(DID, '3aaaaaaaaaaa4', request(PLANT, mode='try'))
        self.me['pds'] = self.pair.B
        self.pds.put(DID, '3aaaaaaaaaaa2', request('delvetalk garden-1 plant\nseed: stale\ncolour: red'))
        self.pds.put(DID, '3aaaaaaaaaaa5', request('delvetalk garden-1 plant\nseed: stale-new\ncolour: red'))
        old_reads = self.pair.count(delve.PDS, 'com.atproto.repo.listRecords')
        old_proofs = self.pair.count(delve.PDS, 'com.atproto.sync.getRecord')
        self.now[0] = 600  # expire the cached identity, even though A still lists the repository
        self.assertEqual(self.step()['failed'], [])
        self.assertEqual(self.answer('3aaaaaaaaaaa2'), first)
        self.assertEqual(self.answer('3aaaaaaaaaaa3')['outcome']['status'], 'admitted')
        self.assertIsNone(self.answer('3aaaaaaaaaaa5'))
        after = self.acts(principal=DID)
        self.assert_plant_entries([e for e in after if e['height'] > before[-1]['height']],
                                  '3aaaaaaaaaaa3', 'garden-1/bell/2')
        identity = {'principal': DID, 'intent': first['source']['request']['uri']}
        consumed = [e for e in after if e.get('identity') == identity]
        self.assertEqual(len(consumed), 1)
        self.assertEqual(consumed, [e for e in before if e.get('identity') == identity])
        observations = {o['uri']: o['cid'] for o in self.st.observations()}
        self.assertEqual(observations, {first['source']['request']['uri']: first['source']['request']['cid'],
                                       self.answer('3aaaaaaaaaaa3')['source']['request']['uri']:
                                       self.answer('3aaaaaaaaaaa3')['source']['request']['cid']})
        self.assertEqual(self.pair.count(delve.PDS, 'com.atproto.repo.listRecords'), old_reads)
        self.assertEqual(self.pair.count(delve.PDS, 'com.atproto.sync.getRecord'), old_proofs)
        self.assertEqual(json.loads(self.st.requests.read_text())['refused'], refused)
        self.assertEqual(json.loads(self.st.requests.read_text())['revs'][DID], {'pds': self.pair.B, 'rev': tid(3)})
        self.assertEqual(self.step()['failed'], [])
        self.assertEqual(self.acts(principal=DID), after)
        self.assertEqual(self.answer('3aaaaaaaaaaa2'), first)

    def test_a_hostname_did_web_participant_on_b_is_admitted(self):
        other = 'did:web:resident.example'
        self.pair.b.repo(other, self.pair.B)
        self.pair.b.put(other, '3aaaaaaaaaaa2', request(PLANT))
        self.participants(other)
        self.assertEqual(self.step()['failed'], [])
        self.assertEqual(self.answer('3aaaaaaaaaaa2', other)['outcome']['status'], 'admitted')
        self.assertEqual(self.pair.documents(other), 1)

    def test_cached_key_rotation_refreshes_once_and_an_unknown_key_is_refused_once_without_a_storm(self):
        self.step()  # caches the original key
        key = ec.generate_private_key(ec.SECP256K1())
        self.me['key'] = self.me['signer'] = key
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT))
        docs = self.pair.documents(DID)
        self.step()
        self.assertEqual(self.pair.documents(DID), docs + 1)
        self.assertEqual(self.answer('3aaaaaaaaaaa2')['outcome']['status'], 'admitted')
        self.me['signer'] = ec.generate_private_key(ec.SECP256K1())
        for rkey in ('3aaaaaaaaaaa3', '3aaaaaaaaaaa4'):
            self.pds.put(DID, rkey, request(PLANT))
        docs, before = self.pair.documents(DID), len(self.acts())
        self.step()
        self.assertEqual(self.pair.documents(DID), docs + 1)  # one refresh for the participant, not per bad record
        refused = json.loads(self.st.requests.read_text())['refused']
        self.assertEqual(len(refused), 2)
        self.assertTrue(all('bad_signature' in row['why'] for row in refused.values()))
        self.assertEqual(len(self.acts()), before)
        proofs = self.pair.count(delve.PDS, 'com.atproto.sync.getRecord')
        self.step()
        self.pds.put(DID, '3aaaaaaaaaaa5', request(PLANT, mode='try'))
        self.step()
        self.assertEqual(self.pair.count(delve.PDS, 'com.atproto.sync.getRecord'), proofs + 2)
        self.assertEqual(json.loads(self.st.requests.read_text())['refused'], {**refused,
                         f'at://{DID}/{COLLECTION}/3aaaaaaaaaaa5': mock.ANY})

    def test_a_verification_refresh_that_moves_the_pds_restarts_listing_on_b(self):
        self.step()  # A's key and endpoint cached
        old_key = self.me['key']
        self.pds.put(DID, '3aaaaaaaaaaa2', request('delvetalk garden-1 plant\nseed: stale\ncolour: red'))
        moved = self.pair.b.repo(DID, self.pair.B)
        self.pair.b.put(DID, '3aaaaaaaaaaa2', request(PLANT))
        self.assertNotEqual(multikey(moved['key'].public_key()), multikey(old_key.public_key()))
        # The old proof's broken signature forces refresh before its stale value can be consumed.
        self.me['signer'] = ec.generate_private_key(ec.SECP256K1())
        docs, before = self.pair.documents(DID), self.acts(principal=DID)
        self.assertEqual(self.step()['failed'], [])
        self.assertEqual(self.pair.documents(DID), docs + 1)
        self.assertEqual(self.pair.count(self.pair.B, 'com.atproto.repo.listRecords'), 1)
        self.assertEqual(self.pair.count(self.pair.B, 'com.atproto.sync.getLatestCommit'), 1)
        self.assertEqual(self.answer('3aaaaaaaaaaa2')['outcome']['status'], 'admitted')
        self.assertEqual(self.answer('3aaaaaaaaaaa2')['source']['request']['cid'],
                         str(block(from_json(request(PLANT)))[0]))
        after = self.acts(principal=DID)
        self.assert_plant_entries([e for e in after if e['height'] > before[-1]['height']],
                                  '3aaaaaaaaaaa2', 'garden-1/bell/1')
        self.assertEqual(json.loads(self.st.requests.read_text())['refused'], {})
        self.assertEqual(self.step()['failed'], [])
        self.assertEqual(self.acts(principal=DID), after)

    def test_a_bad_car_and_a_missing_mst_path_refresh_once_before_being_refused(self):
        self.step()
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT))
        docs = self.pair.documents(DID)
        self.pds.proof = lambda q, raw: b'not a CAR'
        self.step()
        uri = f'at://{DID}/{COLLECTION}/3aaaaaaaaaaa2'
        self.assertEqual(self.pair.documents(DID), docs + 1)
        self.assertIn('bad_proof', json.loads(self.st.requests.read_text())['refused'][uri]['why'])
        self.assertIsNone(self.answer('3aaaaaaaaaaa2'))
        self.pds.put(DID, '3aaaaaaaaaaa3', request(PLANT))
        # Return a signed tree in which the listed rkey 3 is absent.
        records = self.me['records']
        self.me['records'] = {'3aaaaaaaaaaa2': records['3aaaaaaaaaaa2']}
        tree, blocks, commit = self.pds.commit(DID)
        self.me['records'] = records
        self.pds.proof = lambda q, raw: car(commit[0], [commit, *tree.proof(0), blocks['3aaaaaaaaaaa2']])
        docs = self.pair.documents(DID)
        self.step()
        self.assertEqual(self.pair.documents(DID), docs + 1)
        self.assertIn('not_in_commit', json.loads(self.st.requests.read_text())['refused'][
            f'at://{DID}/{COLLECTION}/3aaaaaaaaaaa3']['why'])
        self.assertIsNone(self.answer('3aaaaaaaaaaa3'))

    def test_unchanged_b_revision_skips_listing_and_identity_expires_at_ten_minutes(self):
        other = 'did:plc:' + 'b' * 24
        self.pair.b.repo(other, self.pair.B)
        self.participants(other)
        self.step()
        self.now[0] = 599
        self.step()
        self.assertEqual(self.pair.count(self.pair.B, 'com.atproto.sync.getLatestCommit'), 2)
        self.assertEqual(self.pair.count(self.pair.B, 'com.atproto.repo.listRecords'), 1)
        self.assertEqual(self.pair.documents(other), 1)
        self.now[0] = 600
        self.step()
        self.assertEqual(self.pair.documents(other), 2)
        self.assertEqual(self.pair.count(self.pair.B, 'com.atproto.repo.listRecords'), 1)

    def test_a_private_or_http_pds_is_a_problem_before_any_request_reaches_it(self):
        for endpoint in ('https://127.0.0.1', 'https://10.0.0.1', 'http://pds.resident.example', 'https://internal.example'):
            with self.subTest(endpoint=endpoint):
                self.me['pds'] = endpoint
                self.now[0] += 600
                self.client.document_transport = self.pair
                self.client.read_transport = lambda *args: delve.public_transport(*args, resolve=lambda *a, **k: [
                    (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('127.0.0.1', 443))])
                reads = self.pair.count(delve.PDS, 'com.atproto.repo.listRecords')
                ran = self.step()
                self.assertIn('not_public', canonical(ran['failed']))
                self.assertEqual(self.pair.count(delve.PDS, 'com.atproto.repo.listRecords'), reads)
                self.assertFalse(any(url.startswith(endpoint + '/xrpc/') for url in self.pair.calls))
                self.assertIsNone(self.answer('3aaaaaaaaaaa2'))

    def test_unsupported_config_dids_are_problems_and_never_resolved(self):
        bad = ['did:key:z123', 'did:web:resident.example:path', 'did:web:resident.example%3A443']
        self.participants(*bad)
        ran = self.step()
        self.assertTrue(all(did in canonical(ran['failed']) for did in bad))
        self.assertEqual(len(ran['failed']), len(bad))
        self.assertFalse(any('/did:key:' in url or '%3A443' in url for url in self.pair.calls))

    def test_256_other_pds_participants_are_read_and_overflow_is_reported(self):
        dids = [f'did:web:r{n:03d}.example' for n in range(257)]
        for did in dids:
            self.pair.b.repo(did, self.pair.B)
        self.participants(*dids)
        ran = self.step()
        self.assertEqual(self.pair.count(self.pair.B, 'com.atproto.sync.getLatestCommit'), 256)
        self.assertEqual(self.pair.count(self.pair.B, 'com.atproto.repo.listRecords'), 256)
        self.assertIn('participant_overflow', canonical(ran['failed']))
        self.assertIn(dids[-1], canonical(ran['failed']))
        self.assertEqual(len(ran['failed']), 1)

    def test_a_stale_if_is_answered_moved_with_what_moved_and_journals_nothing(self):
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT, **{'if': [{'object': 'garden-1', 'version': 0}]}))
        self.step()
        acts = len(self.acts())
        self.pds.put(DID, '3aaaaaaaaaaa3', request('delvetalk garden-1 plant\nseed: b\ncolour: amber', **{'if': [{'object': 'garden-1', 'version': 0}]}))
        self.step()
        a = self.answer('3aaaaaaaaaaa3')
        self.assertEqual(a['outcome']['status'], 'moved')
        self.assertEqual(a['outcome']['moved'], [{'object': 'garden-1', 'was': 0, 'now': 1}])
        self.assertNotIn('receipt', a)
        self.assertEqual(len(self.acts()), acts)



class Held(unittest.TestCase):
    """A request hob must read first (a misfit spell) is answered when its turn settles, once, never run again meanwhile."""

    def test_a_suspended_request_is_answered_when_it_settles_and_not_turned_again_while_it_waits(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        st, pds, host = State(Path(tmp.name) / 'state', config=LOOPBACK), FakePDS(), Stub()
        pds.repo(DID)
        host.suspending = {'garden-1'}
        uri = f'at://{DID}/{COLLECTION}/3aaaaaaaaaaa2'
        pds.put(DID, '3aaaaaaaaaaa2', request(PLANT))

        def step():
            client = delve.Client(pds)
            ob = observe.Observer(st, client, '2026-10-12T00:00:00Z', Poller(st, client))
            try:
                return bridge.run(st, host, ob)
            finally:
                ob.db.close()
        step()
        self.assertFalse(bridge.answer_path(st, bridge.request_source({'uri': uri, 'cid': 'unused'})).exists())
        turns = sum(o['op'] == 'world-turn' for o in host.ops)
        step()
        self.assertEqual(sum(o['op'] == 'world-turn' for o in host.ops), turns)
        host.offers[DID] = [{'height': 9, 'ordinal': 0, 'identity': {'principal': DID, 'intent': uri}, 'text': 'Planted.'},
                            {'height': 9, 'ordinal': 1, 'identity': {'principal': DID, 'intent': 'someone-else'}, 'text': 'not mine'}]
        self.assertEqual(step()['offered'], [uri])
        a = json.loads(bridge.answer_path(st, bridge.request_source({'uri': uri, 'cid': 'unused'})).read_text())
        self.assertEqual(record_problems(a), [])
        self.assertEqual((a['outcome']['status'], a['offers'], a['receipt']['slug']), ('admitted', ['Planted.'], 'lodif-rukuz'))
        self.assertNotIn('offered', step())



class Switch(unittest.TestCase):
    """The bridge reads participant requests only when the owner turns `requests` on."""

    def observer(self, **config):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        st = State(Path(tmp.name) / 'state', config=dataclasses.replace(LOOPBACK, **config))
        ob = bridge.delve_observer(st, '2026-10-12T00:00:00Z')
        self.addCleanup(ob.db.close)
        return ob

    def test_the_live_bridge_polls_no_request_records_until_requests_is_on(self):
        self.assertIsNone(self.observer().requests)
        self.assertIsInstance(self.observer(requests=True).requests, Poller)

    def test_fixture_posts_never_poll_the_pds(self):
        self.assertIsNone(self.observer(requests=True, delve_mock='fixtures').requests)

    def test_the_environment_turns_it_on(self):
        self.assertFalse(Config.load(environ={}).requests)
        self.assertTrue(Config.load(environ={'DELVETALK_REQUESTS': 'on'}).requests)
        self.assertEqual(Config.load(environ={}).participants, '')
        self.assertEqual(Config.load(environ={'DELVETALK_PARTICIPANTS': DID}).participants, DID)


class ParticipantReads(unittest.TestCase):
    def test_arbitrary_pds_reads_allow_exactly_three_endpoints_and_the_shared_parameter_bounds(self):
        calls = []
        client = delve.Client(lambda *args: calls.append(args) or (200, b'{}'))
        pds = PDSPair.B
        for nsid, params in [('com.atproto.repo.listRecords', {'repo': DID, 'collection': COLLECTION, 'limit': 100}),
                             ('com.atproto.sync.getRecord', {'did': DID, 'collection': COLLECTION, 'rkey': 'x'}),
                             ('com.atproto.sync.getLatestCommit', {'did': DID})]:
            self.assertEqual(client.read(pds, nsid, **params), {})
            self.assertTrue(calls[-1][1].startswith(pds + '/xrpc/' + nsid + '?'))
        self.assertEqual(client.read(pds, 'com.atproto.sync.getRecord', raw=True, did=DID), b'{}')
        self.assertEqual(calls[-1][2]['Accept'], 'application/vnd.ipld.car')
        before = len(calls)
        for nsid, params, code in [('com.atproto.sync.listRepos', {}, 'endpoint_not_allowed'),
                                   ('com.atproto.repo.getRecord', {}, 'endpoint_not_allowed'),
                                   ('com.atproto.repo.putRecord', {}, 'endpoint_not_allowed'),
                                   ('com.atproto.sync.getLatestCommit', {'repo': DID}, 'param_not_allowed'),
                                   ('com.atproto.sync.getLatestCommit', {'did': True}, 'param_invalid'),
                                   ('com.atproto.sync.getLatestCommit', {'did': 'x' * (delve.MAX_PARAM + 1)}, 'param_invalid')]:
            with self.assertRaises(delve.Failure) as failed:
                client.read(pds, nsid, **params)
            self.assertEqual(failed.exception.code, code)
        client.read(pds, 'com.atproto.sync.getLatestCommit', did='x' * delve.MAX_PARAM)
        self.assertEqual(len(calls), before + 1)

    def test_live_observer_uses_public_transport_for_documents_and_participant_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            st = State(directory, config=dataclasses.replace(LOOPBACK, requests=True))
            ob = bridge.delve_observer(st, None)
            try:
                self.assertIs(ob.client.document_transport, delve.public_transport)
                self.assertIs(ob.client.read_transport, delve.public_transport)
            finally:
                ob.db.close()


if __name__ == '__main__':
    unittest.main()
