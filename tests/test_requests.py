"""Acting by record (docs/ATPROTO.md §2, L1): a resident writes `town.delvetalk.request` in their own repository; the
poller proves it from the signed commit and the author's DID document, the bridge runs it as the same turn a post's
spell is, under the record's at-uri, and answers with a `town.delvetalk.answer` record the façade serves and the mirror
copies byte for byte.

Evidence for docs/ATPROTO.md §2 (layer: transport), on a fake PDS here: repositories signed with real keys, served
over listRepos, listRecords, sync.getRecord and plc.directory.

Refuted by: a request read twice making two entries; a record signed by a key other than its DID document's making a
turn; a stale `if` admitted; an answer whose CID differs between the façade and the mirror's write; a `try`, a request
to another service or one created before the world began observing being run; an answer carrying a private turn's
offers; a request whose key sorts below one already read being missed.
"""
import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from tests.host import served
from tests.test_bridge import DID, LOOPBACK, Stub, modules
from tests.test_chain import town_garden
from tests.test_lexicons import record_problems
from transport import bridge, delve, mirror, observe
from transport.atproto.cbor import CID, block, car, encode, from_json
from transport.atproto.mst import Tree
from transport.atproto.sign import CURVES, multikey, tid
from transport.delve import canonical
from transport.host import HostClient
from transport.repo import Repo, world_did
from transport.requests import COLLECTION, Poller
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

    def __init__(self):
        self.repos, self.calls = {}, []

    def repo(self, did, pds=delve.PDS):
        key = ec.generate_private_key(ec.SECP256K1())
        self.repos[did] = {'key': key, 'signer': key, 'records': {}, 'rev': 0, 'pds': pds}
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
        if url.startswith(PLC):
            did = parts.path[1:]
            r = self.repos.get(did)
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
        if nsid == 'com.atproto.repo.listRecords':
            _, blocks, _ = self.commit(q['repo'])
            return 200, json.dumps({'records': [{'uri': f"at://{q['repo']}/{COLLECTION}/{k}", 'cid': str(blocks[k][0]), 'value': r['records'][k]}
                                                for k in sorted(r['records'])]}).encode()
        if nsid == 'com.atproto.sync.getRecord':
            tree, blocks, commit = self.commit(q['did'])
            at = sorted(r['records']).index(q['rkey'])
            return 200, car(commit[0], [commit, *tree.proof(at), blocks[q['rkey']]])
        return 404, b'{"error":"NoSuchMethod"}'


def request(spell=None, created='2026-10-12T10:00:00Z', service=SERVICE, **more):
    call = {'spell': spell} if spell is not None else more.pop('call')
    return {'$type': COLLECTION, 'service': service, 'mode': more.pop('mode', 'act'), 'calls': more.pop('calls', [call]), 'createdAt': created, **more}


PLANT = 'delvetalk garden-1 plant\nseed: a\ncolour: amber'


class Requests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st = State(Path(self.tmp.name) / 'state', config=LOOPBACK)
        self.pds = FakePDS()
        self.me = self.pds.repo(DID)
        serving = served(str(Path(self.tmp.name) / 'serve'), cleanup=self.addCleanup)
        self.host = HostClient(serving.sock)
        town_garden(lambda **q: self.host.send(q), id='garden-1')

    def step(self, since='2026-10-12T00:00:00Z'):
        """One bridge step over the fake PDS: observe (posts, then requests), turn, answer."""
        client = delve.Client(self.pds)
        ob = observe.Observer(self.st, client, since, Poller(self.st, client))
        try:
            return bridge.run(self.st, self.host, ob)
        finally:
            ob.db.close()

    def acts(self):
        """The journal's entries that are not the clock's ticks."""
        entries, after = [], 0
        while True:
            got = self.host.send({'op': 'world-entries', 'principal': 'anonymous', 'after': after, 'limit': 100})
            entries += got['entries']
            if not got.get('more') or not got['entries']:
                return [e for e in entries if (e.get('identity') or {}).get('principal') != 'clock']
            after = got['entries'][-1]['height']

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
        self.assertEqual(a['request']['uri'], uri)
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
        self.assertEqual(set(a), {'$type', 'request', 'outcome', 'receipt', 'height'})
        self.assertNotIn('secret', canonical(a))
        self.assertNotIn('diary', canonical(a))

    def test_the_answers_cid_is_the_same_from_the_facade_and_in_the_mirrors_write(self):
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT))
        self.step()
        written = []
        mirror.run(self.st, self.host, lambda c, k, v: written.append((c, k, v)))
        (value,) = [v for c, k, v in written if c == bridge.ANSWER and k == f'{DID}.3aaaaaaaaaaa2']
        pds_cid = block(from_json(json.loads(canonical(value))))[0]  # the PDS hashes the JSON it is sent
        repo = Repo(LOOPBACK.origin, answers=self.st.answers)
        code, got, _ = repo.serve(self.host, 'GET', 'com.atproto.repo.getRecord',
                                  {'repo': repo.did, 'collection': bridge.ANSWER, 'rkey': f'{DID}.3aaaaaaaaaaa2'}, None)
        self.assertEqual((code, got['cid'], got['value']), (200, str(pds_cid), value))
        self.assertIsInstance(from_json(value)['receipt']['entry'], CID)  # a real link, as the lexicon's cid-link
        code, listed, _ = repo.serve(self.host, 'GET', 'com.atproto.repo.listRecords', {'repo': repo.did, 'collection': bridge.ANSWER}, None)
        self.assertEqual([r['cid'] for r in listed['records']], [str(pds_cid)])

    def test_a_repository_whose_did_document_names_another_pds_is_not_read_from_this_one(self):
        self.pds.repos[DID]['pds'] = 'https://pds.elsewhere.example'
        self.pds.put(DID, '3aaaaaaaaaaa2', request(PLANT))
        ran = self.step()
        self.assertIsNone(self.answer('3aaaaaaaaaaa2'))
        self.assertIn('repository_elsewhere', canonical(ran['failed']))

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
        self.assertFalse(bridge.answer_path(st, uri).exists())
        turns = sum(o['op'] == 'world-turn' for o in host.ops)
        step()
        self.assertEqual(sum(o['op'] == 'world-turn' for o in host.ops), turns)
        host.offers[DID] = [{'height': 9, 'ordinal': 0, 'identity': {'principal': DID, 'intent': uri}, 'text': 'Planted.'},
                            {'height': 9, 'ordinal': 1, 'identity': {'principal': DID, 'intent': 'someone-else'}, 'text': 'not mine'}]
        self.assertEqual(step()['offered'], [uri])
        a = json.loads(bridge.answer_path(st, uri).read_text())
        self.assertEqual(record_problems(a), [])
        self.assertEqual((a['outcome']['status'], a['offers'], a['receipt']['slug']), ('admitted', ['Planted.'], 'lodif-rukuz'))
        self.assertNotIn('offered', step())


if __name__ == '__main__':
    unittest.main()
