"""Hosted public request repositories (ATPROTO §4/L7), real keys, fake world.

Refuted by a principal/DID collision, another Host seeing a guest's document,
a forged proof becoming a turn, a wrong credential changing any file, a put
leaving the old leaf, a delete retaining it, or a restart changing the head.
No external network or Lean process is used.
"""
import concurrent.futures
import copy
import http.client
import json
import stat
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.host import serve
from tests.test_repo import signs
from tests.test_xrpc_acts import ActsWorld
from transport import bridge, delve, identity, observe
from transport.atproto.cbor import block, decode, from_json, read_car
from transport.atproto.mst import find
from transport.atproto.sign import Key, tid
from transport.config import Config
from transport.hosted import Accounts, MAX_REQUESTS, MAX_RECORD_BYTES, MAX_PAGE_BYTES, MAX_WRITE_BODY
from transport.http import Front
from transport.requests import COLLECTION, Poller, proven
from transport.state import State

HOST = 'gsb.fg-goose.online'
ORIGIN = 'https://' + HOST


def request(text='delvetalk diary write\ntext: rain', **more):
    return {'$type': COLLECTION, 'service': 'did:web:' + HOST, 'mode': 'act',
            'calls': [{'spell': text}], 'createdAt': '2026-10-12T10:00:00Z', **more}


class Mapping(unittest.TestCase):
    def test_guest_zulip_and_maximum_name_round_trip(self):
        for principal, did in [
            (f'guest:{HOST}:robin', f'did:web:robin.guest.{HOST}'),
            (f'guest:{HOST}:' + 'a' * 32, 'did:web:' + 'a' * 32 + '.guest.' + HOST),
            ('zulip:chat.example:42', f'did:web:42.chat.example.zulip.{HOST}')]:
            self.assertEqual(identity.hosted_identity(principal, HOST), did)
            self.assertEqual(identity.hosted_identity(did, HOST), principal)

    def test_malformed_and_foreign_principals_never_map(self):
        for bad in [f'guest:{HOST}:{name}' for name in ('', 'A', 'a.b', '../a', 'a' * 33, 'a_', 'a-') ] + [
            'guest:elsewhere.example:a', 'zulip:chat.example:01', 'zulip:chat.example:-1',
            'zulip:chat.example:0', 'zulip:chat..example:1', 'zulip:chat.example:1:2',
            f'did:web:a.guest.{HOST}:path', f'did:web:A.guest.{HOST}',
            f'did:web:1.chat.example.zulip.{HOST}.evil', 'did:plc:' + 'a' * 24, f'did:web:{HOST}']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                identity.hosted_identity(bad, HOST)


class HostedWorld(ActsWorld):
    def send(self, q):
        if q['op'] == 'bounds':
            return {'kernel': {'maxPackageBytes': 65536, 'maxModules': 16},
                    'host': {'listPage': 100, 'deliveriesPerCall': 8, 'mentionsAddressed': 8}}
        if q['op'] == 'world-publications':
            return {'status': 'publications', 'publications': [], 'more': False}
        return super().send(q)


@signs
class Hosted(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.st = State(tmp.name, config=Config(origin=ORIGIN, requests=True, repo_keys=str(Path(tmp.name) / 'repo')))
        self.now = [1000.0]
        self.host = HostedWorld()
        self.client = delve.Client(self.network)
        self.ident = identity.Identity(self.st, self.client, clock=lambda: self.now[0])
        self.addCleanup(self.ident.db.close)
        self.front = serve(Front(self.st, self.host, self.ident, ('127.0.0.1', 0), clock=lambda: self.now[0]))
        self.addCleanup(self.front.server_close)
        self.addCleanup(self.front.shutdown)
        self.robin = self.accept('robin')
        self.wren = self.accept('wren')
        self.did = identity.hosted_identity(self.robin['principal'], HOST)
        self.hostname = self.did[8:]
        self.accounts = Accounts(self.st)
        self.rkey = tid(1)

    def network(self, method, url, headers, body):
        nsid = urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1]
        if nsid == 'com.atproto.sync.listRepos':
            return 200, b'{"repos":[]}'
        if nsid in ('town.delve.feed.searchPosts', 'town.delve.feed.getFeed'):
            return 200, b'{"posts":[],"feed":[]}'
        raise AssertionError('hosted reads must be local: ' + url)

    def accept(self, name):
        code = self.ident.invite(name)['code']
        code, out = self.call('/AGENTS.md/accept', {'code': code}, hostname=HOST)
        self.assertEqual(code, 200, out)
        return out

    def call(self, path, body=None, token=None, hostname=None, method=None, raw=False):
        self.now[0] += 61
        c = http.client.HTTPConnection(*self.front.server_address, timeout=10)
        headers = {'Host': hostname or self.hostname, 'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        c.request(method or ('GET' if body is None else 'POST'), path,
                  None if body is None else json.dumps(body), headers)
        r = c.getresponse()
        status, data = r.status, r.read()
        c.close()
        return status, data if raw else json.loads(data)

    def rpc(self, nsid, body=None, **q):
        return self.call('/xrpc/com.atproto.' + nsid + '?' + urllib.parse.urlencode(q), body,
                         self.robin['credential'] if body is not None else None)

    def create(self, rkey=None, value=None):
        return self.rpc('repo.createRecord', {'repo': self.did, 'collection': COLLECTION,
                        'rkey': rkey or self.rkey, 'record': value or request()})

    def files(self):
        return {str(p.relative_to(self.st.home)): p.read_bytes() for p in self.st.hosted.rglob('*') if p.is_file()}

    def test_existing_verified_guest_gets_one_key_and_no_claimed_did_is_rehosted(self):
        principal = f'guest:{HOST}:existing'
        credential = 'dt_agent_' + 'a' * 43
        self.ident.db.execute("INSERT INTO challenges(nonce,handle,did,credential,state) VALUES(?,?,?,?,?)",
                              ('existing', 'existing', principal, identity.digest(credential), 'verified'))
        self.accounts.provision_guests()
        did = identity.hosted_identity(principal, HOST)
        self.assertIn(did, self.accounts.dids())
        key = self.st.hosted / 'existing.key'
        raw = key.read_bytes()
        self.accounts.provision_guests()
        self.assertEqual(key.read_bytes(), raw)
        self.assertEqual(self.ident.authenticate(credential)['did'], principal)
        self.assertNotIn('did:web:' + HOST, self.accounts.dids())

    def test_document_is_host_selected_only_and_account_key_proves_the_record(self):
        status, doc = self.call('/.well-known/did.json')
        self.assertEqual((status, doc['id'], doc['alsoKnownAs']), (200, self.did, ['at://' + self.hostname]))
        self.assertEqual(doc['service'][0]['serviceEndpoint'], ORIGIN)
        key = self.st.hosted / 'robin.key'
        self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o400)
        self.assertNotEqual(Key.load(key).did_key, Key.load(self.st.hosted / 'wren.key').did_key)
        for hostname in ('nobody.guest.' + HOST, self.hostname + '.evil', 'robin.guest.elsewhere.example'):
            self.assertEqual(self.call('/.well-known/did.json', hostname=hostname)[0], 400)
        self.assertEqual(self.call('/.well-known/did.json', hostname=HOST)[1]['id'], 'did:web:' + HOST)
        self.assertEqual(self.create()[0], 200)
        cid, value, handle = proven(self.accounts, self.did, self.rkey, doc)
        self.assertEqual((cid, value, handle), (str(block(from_json(request()))[0]), request(), self.hostname))

    def test_create_list_get_and_signed_sync_have_value_cids(self):
        status, made = self.create()
        self.assertEqual(status, 200, made)
        expected = {'uri': f'at://{self.did}/{COLLECTION}/{self.rkey}', 'cid': str(block(from_json(request()))[0]), 'value': request()}
        self.assertEqual(self.rpc('repo.listRecords', repo=self.did, collection=COLLECTION)[1]['records'], [expected])
        self.assertEqual(self.rpc('repo.getRecord', repo=self.did, collection=COLLECTION, rkey=self.rkey)[1], expected)
        self.assertEqual(self.rpc('repo.describeRepo', repo=self.did)[1]['collections'], [COLLECTION])
        status, raw = self.call('/xrpc/com.atproto.sync.getRecord?' + urllib.parse.urlencode(
            {'did': self.did, 'collection': COLLECTION, 'rkey': self.rkey}), raw=True)
        self.assertEqual(status, 200)
        self.assertEqual(raw, self.accounts.read(ORIGIN, 'com.atproto.sync.getRecord', raw=True,
                                                did=self.did, collection=COLLECTION, rkey=self.rkey))
        roots, blocks = read_car(raw)
        commit = decode(blocks[roots[0]])
        self.assertEqual(str(find(blocks, commit['data'], f'{COLLECTION}/{self.rkey}'.encode())), expected['cid'])
        self.assertEqual(self.rpc('sync.listRepos')[1]['repos'][0]['did'], self.did)

    def test_maximum_plan_record_budget_generated_key_and_paging(self):
        plan = request(mode='plan', calls=[{'spell': 'x' * 4096} for _ in range(8)])
        body = {'repo': self.did, 'collection': COLLECTION, 'record': plan}
        status, made = self.rpc('repo.createRecord', body)
        self.assertEqual(status, 200, made)
        self.assertRegex(made['uri'].rsplit('/', 1)[-1], r'^[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}$')
        base = request()
        overhead = len(block(from_json({**base, 'extra': ''}))[1])
        # A CBOR string of this size has a three-byte head rather than the empty string's one.
        maximum = {**base, 'extra': 'x' * (MAX_RECORD_BYTES - overhead - 2)}
        self.assertEqual(len(block(from_json(maximum))[1]), MAX_RECORD_BYTES)
        self.assertEqual(self.create(tid(3), maximum)[0], 200)
        baseline = self.files()
        self.assertEqual(self.create(tid(4), {**maximum, 'extra': maximum['extra'] + 'x'})[0], 400)
        self.assertEqual(self.files(), baseline)
        seen, cursor = [], None
        while True:
            page = self.rpc('repo.listRecords', repo=self.did, collection=COLLECTION, limit=1,
                            **({'cursor': cursor} if cursor else {}))[1]
            seen += [r['uri'] for r in page['records']]
            cursor = page.get('cursor')
            if not cursor:
                break
        self.assertEqual(len(set(seen)), 2)
        self.assertEqual(seen, sorted(seen))
        reverse = self.rpc('repo.listRecords', repo=self.did, collection=COLLECTION, reverse='true')[1]
        self.assertEqual([r['uri'] for r in reverse['records']], list(reversed(seen)))

    def test_control_character_records_page_within_front_reply_budget(self):
        value = request(extra='\x00' * 60000)
        for k in range(12):
            status, made = self.create(tid(k + 100), value)
            self.assertEqual(status, 200, made)
        page = self.rpc('repo.listRecords', repo=self.did, collection=COLLECTION, limit=100)[1]
        self.assertLess(len(delve.canonical(page).encode()), MAX_PAGE_BYTES)
        self.assertIn('cursor', page)
        second = self.rpc('repo.listRecords', repo=self.did, collection=COLLECTION, limit=100, cursor=page['cursor'])[1]
        self.assertEqual(len(page['records']) + len(second['records']), 12)
        self.assertEqual(len({r['uri'] for r in page['records'] + second['records']}), 12)

    def test_escaped_record_writes_have_a_bounded_body_without_raising_action_limits(self):
        from transport.http import MAX_BODY
        value = request(extra='\x00' * 60000)
        data = {'repo': self.did, 'collection': COLLECTION, 'rkey': self.rkey, 'record': value}
        self.assertLess(len(block(from_json(value))[1]), MAX_RECORD_BYTES)
        self.assertGreater(len(json.dumps(data).encode()), MAX_BODY)
        self.assertLess(len(json.dumps(data).encode()), MAX_WRITE_BODY)
        status, api = self.call('/AGENTS.md/api', hostname=HOST)
        self.assertEqual((status, api['limits']['bodyBytes'], api['limits']['hostedWriteBodyBytes']),
                         (200, MAX_BODY, MAX_WRITE_BODY))
        status, made = self.create(value=value)
        self.assertEqual(status, 200, made)
        baseline = self.files()
        status, refusal = self.create(tid(2), request(extra='x' * MAX_WRITE_BODY))
        self.assertEqual((status, refusal['error']), (400, 'InvalidRequest'))
        self.assertEqual(self.files(), baseline)
        status, refusal = self.call('/AGENTS.md/world/diary/write',
            {'intent': 'too-long', 'fields': {'text': 'x' * MAX_BODY}}, self.robin['credential'], hostname=HOST)
        self.assertEqual((status, refusal['class']), (413, 'bodyTooLarge'))
        self.assertEqual(self.files(), baseline)

    def test_full_export_has_every_node_for_present_and_absent_keys_after_deletes(self):
        for k in range(12):
            self.assertEqual(self.create(tid(k + 100))[0], 200)
        deleted = tid(105)
        self.assertEqual(self.rpc('repo.deleteRecord', {'repo': self.did, 'collection': COLLECTION, 'rkey': deleted})[0], 200)
        raw = self.accounts.read(ORIGIN, 'com.atproto.sync.getRepo', raw=True, did=self.did)
        roots, blocks = read_car(raw)
        data = decode(blocks[roots[0]])['data']
        stack, visited = [data], set()
        while stack:
            cid = stack.pop()
            if cid in visited:
                continue
            visited.add(cid)
            self.assertIn(cid, blocks)
            node = decode(blocks[cid])
            stack += [child for child in [node['l'], *(e['t'] for e in node['e'])] if child is not None]
        for k in range(12):
            found = find(blocks, data, f'{COLLECTION}/{tid(k + 100)}'.encode())
            if tid(k + 100) == deleted:
                self.assertIsNone(found)
            else:
                self.assertEqual(str(found), str(block(from_json(request()))[0]))
        status, refusal = self.rpc('sync.getRecord', did=self.did, collection=COLLECTION, rkey=deleted)
        self.assertEqual((status, refusal['error']), (400, 'RecordNotFound'))

    def test_swap_guards_and_duplicate_create_refuse_without_advancing_the_head(self):
        self.assertEqual(self.create()[0], 200)
        baseline = self.files()
        body = {'repo': self.did, 'collection': COLLECTION, 'rkey': self.rkey, 'record': request()}
        self.assertEqual(self.create()[1]['error'], 'RecordAlreadyExists')
        for method in ('repo.putRecord', 'repo.deleteRecord'):
            q = body if method.endswith('putRecord') else {k: v for k, v in body.items() if k != 'record'}
            for guard in ('swapRecord', 'swapCommit'):
                status, error = self.rpc(method, {**q, guard: str(block('another value')[0])})
                self.assertEqual((status, error['error']), (400, 'InvalidSwap'))
                self.assertEqual(self.files(), baseline)
        head = self.rpc('sync.getLatestCommit', did=self.did)[1]
        cid = str(block(from_json(request()))[0])
        self.assertEqual(self.rpc('repo.putRecord', {**body, 'swapCommit': head['cid'], 'swapRecord': cid})[0], 200)

    def test_origin_pds_routes_the_explicit_account_without_cross_host_aliasing(self):
        body = {'repo': self.did, 'collection': COLLECTION, 'rkey': self.rkey, 'record': request()}
        status, made = self.call('/xrpc/com.atproto.repo.createRecord', body, self.robin['credential'], hostname=HOST)
        self.assertEqual(status, 200, made)
        path = '/xrpc/com.atproto.repo.getRecord?' + urllib.parse.urlencode(
            {'repo': self.did, 'collection': COLLECTION, 'rkey': self.rkey})
        self.assertEqual(self.call(path, hostname=HOST)[1]['cid'], made['cid'])
        wren = identity.hosted_identity(self.wren['principal'], HOST)
        self.assertEqual(self.call(path, hostname=wren[8:])[0], 400)
        self.assertEqual(self.call('/xrpc/com.atproto.repo.createRecord',
            {**body, 'repo': 'did:web:nobody.guest.' + HOST}, self.robin['credential'], hostname=HOST)[0], 400)

    def test_wrong_credentials_bad_collection_and_invalid_records_change_no_files(self):
        baseline = self.files()
        body = {'repo': self.did, 'collection': COLLECTION, 'rkey': self.rkey, 'record': request()}
        for token in (None, 'dt_agent_' + 'x' * 43, self.wren['credential']):
            status, out = self.call('/xrpc/com.atproto.repo.createRecord', body, token)
            self.assertIn(status, (401, 403), out)
            self.assertEqual(self.files(), baseline)
        for change in ({'collection': COLLECTION + 'x'}, {'record': request(calls=[])},
                       {'record': request(calls=[{'spell': 'x' * 4097}])}, {'rkey': '../escape'},
                       {'record': request(createdAt='yesterday')}, {'record': request(service=42)}, {'record': request(calls=[{}])},
                       {'record': request(calls=[{'spell': 'x', 'object': 'diary', 'verb': 'write'}])},
                       {'record': request(calls=[{'object': 'diary', 'verb': 'write', 'fields': []}])},
                       {'record': request(**{'$type': COLLECTION + 'x'})},
                       {'record': request(extra='x' * MAX_RECORD_BYTES)},
                       {'record': request(extra={'$link': 'b'})}, {'record': request(extra={'$link': 7})},
                       {'record': request(extra=1.5)}, {'validate': False}):
            status, out = self.call('/xrpc/com.atproto.repo.createRecord', {**body, **change}, self.robin['credential'])
            self.assertEqual(status, 400, out)
            self.assertEqual(self.files(), baseline)
        self.ident.revoke(self.robin['credential'])
        self.assertEqual(self.call('/xrpc/com.atproto.repo.createRecord', body, self.robin['credential'])[0], 401)
        self.assertEqual(self.files(), baseline)

    def test_replace_delete_revision_chain_and_restart_are_deterministic(self):
        self.assertEqual(self.create()[0], 200)
        heads = [self.rpc('sync.getLatestCommit', did=self.did)[1]]
        changed = request('delvetalk diary write\ntext: sun')
        status, put = self.rpc('repo.putRecord', {'repo': self.did, 'collection': COLLECTION, 'rkey': self.rkey, 'record': changed})
        self.assertEqual(status, 200, put)
        heads.append(self.rpc('sync.getLatestCommit', did=self.did)[1])
        self.assertEqual(self.rpc('repo.getRecord', repo=self.did, collection=COLLECTION, rkey=self.rkey)[1]['value'], changed)
        with mock.patch('transport.hosted.time.time_ns', return_value=0):
            self.assertEqual(self.rpc('repo.deleteRecord', {'repo': self.did, 'collection': COLLECTION, 'rkey': self.rkey})[0], 200)
        heads.append(self.rpc('sync.getLatestCommit', did=self.did)[1])
        self.assertEqual([h['rev'] for h in heads], sorted({h['rev'] for h in heads}))
        self.assertEqual(self.rpc('repo.listRecords', repo=self.did, collection=COLLECTION)[1]['records'], [])
        self.assertEqual(self.rpc('repo.getRecord', repo=self.did, collection=COLLECTION, rkey=self.rkey)[0], 400)
        raw = self.accounts.read(ORIGIN, 'com.atproto.sync.getRepo', raw=True, did=self.did)
        baseline = self.files()
        fresh = Accounts(State(self.st.root, config=self.st.config))
        self.assertEqual(fresh.read(ORIGIN, 'com.atproto.sync.getRepo', raw=True, did=self.did), raw)
        self.assertEqual(self.files(), baseline)
        roots, blocks = read_car(raw)
        self.assertIn(decode(blocks[roots[0]])['data'], blocks)
        self.assertEqual(str(decode(blocks[roots[0]])['prev']), heads[-2]['cid'])
        self.assertIsNone(find(blocks, decode(blocks[roots[0]])['data'], f'{COLLECTION}/{self.rkey}'.encode()))

    def test_capacity_refuses_newest_without_evicting_oldest_and_put_delete_make_room(self):
        account = self.accounts.account(self.robin['principal'])
        body = lambda k: {'repo': self.did, 'collection': COLLECTION, 'rkey': tid(k), 'record': request()}
        for k in range(MAX_REQUESTS):
            self.assertEqual(account.serve(None, 'POST', 'com.atproto.repo.createRecord', body(k), self.robin['principal'])[0], 200)
        baseline = self.files()
        status, out, _ = account.serve(None, 'POST', 'com.atproto.repo.createRecord', body(MAX_REQUESTS), self.robin['principal'])
        self.assertEqual((status, out['error']), (400, 'RepoFull'))
        self.assertEqual(self.files(), baseline)
        self.assertIn(tid(0), [r['uri'].rsplit('/', 1)[-1] for r in account.list_records(None, {'repo': self.did, 'collection': COLLECTION, 'limit': '100'}, None)['records']])
        self.assertEqual(account.serve(None, 'POST', 'com.atproto.repo.putRecord', body(0), self.robin['principal'])[0], 200)
        self.assertEqual(account.serve(None, 'POST', 'com.atproto.repo.deleteRecord', {k: v for k, v in body(0).items() if k != 'record'}, self.robin['principal'])[0], 200)
        self.assertEqual(account.serve(None, 'POST', 'com.atproto.repo.createRecord', body(MAX_REQUESTS), self.robin['principal'])[0], 200)

    def test_two_managers_serialise_writes_and_reader_sees_new_head(self):
        accounts = [Accounts(self.st), Accounts(self.st)]
        def write(k):
            return accounts[k].account(self.robin['principal']).serve(None, 'POST', 'com.atproto.repo.createRecord',
                {'repo': self.did, 'collection': COLLECTION, 'rkey': tid(k + 10), 'record': request()}, self.robin['principal'])
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            self.assertEqual([r[0] for r in pool.map(write, range(2))], [200, 200])
        self.assertEqual(len(self.rpc('repo.listRecords', repo=self.did, collection=COLLECTION)[1]['records']), 2)

    def test_local_poll_proves_one_guest_request_turn_and_answer_and_refuses_forgery(self):
        self.assertEqual(self.create()[0], 200)
        poller = Poller(self.st, self.client)
        ob = observe.Observer(self.st, self.client, '2026-10-12T00:00:00Z', poller)
        self.addCleanup(ob.db.close)
        with mock.patch('transport.requests.proven', wraps=proven) as proof:
            first = bridge.run(self.st, self.host, ob, now=1000)
            self.assertEqual(first['failed'], [])
            self.assertTrue(proof.called)
            bridge.run(self.st, self.host, ob, now=1000)
        uri = f'at://{self.did}/{COLLECTION}/{self.rkey}'
        turns = [e for e in self.host.entries if e['identity'] == {'principal': self.did, 'intent': uri}]
        self.assertEqual(len(turns), 1)
        answer = json.loads(next(self.st.answers.glob('*.json')).read_text())
        self.assertEqual(answer['source']['request']['uri'], uri)
        self.assertEqual(len(self.st.observations()), 1)
        # Changing the stored public key invalidates the existing signature, including the refresh retry.
        self.assertEqual(self.create(tid(2))[0], 200)
        doc = copy.deepcopy(self.accounts.did_document(self.did))
        doc['verificationMethod'][0]['publicKeyMultibase'] = Key.generate().did_key.removeprefix('did:key:')
        with mock.patch.object(poller.local, 'did_document', return_value=doc):
            poller.documents.clear()
            poller.poll(ob)
        self.assertEqual(len(self.st.observations()), 1)

    def test_local_poller_reads_more_than_ten_shortened_pages(self):
        for k in range(12):
            self.assertEqual(self.create(tid(k + 100))[0], 200)
        poller = Poller(self.st, self.client)
        ob = observe.Observer(self.st, self.client, '2026-10-12T00:00:00Z')
        self.addCleanup(ob.db.close)
        # This budget fits one fixture row plus envelope, forcing twelve pages.
        with mock.patch('transport.hosted.MAX_PAGE_BYTES', 700):
            self.assertEqual(poller.poll(ob), [])
        self.assertEqual(len(self.st.observations()), 12)

    def test_zulip_account_has_same_proofs_without_importing_messages_or_links(self):
        account = self.accounts.account('zulip:chat.example:42', create=True)
        doc = self.call('/.well-known/did.json', hostname=account.handle)[1]
        self.assertEqual(doc['id'], account.did)
        self.assertEqual(self.accounts.read(ORIGIN, 'com.atproto.repo.listRecords', repo=account.did, collection=COLLECTION)['records'], [])
        self.assertEqual(doc['alsoKnownAs'], ['at://' + account.handle])

    def test_zulip_observation_provisions_account_but_publishes_no_request(self):
        from transport.zulip import ZulipObserver
        client = SimpleNamespace(realm='chat.example')
        ob = ZulipObserver(self.st, client, 'town')
        self.addCleanup(ob.db.close)
        message = {'id': 1, 'subject': 'a topic', 'sender_id': 42, 'sender_full_name': 'Robin',
                   'timestamp': 1791800000, 'content': 'delvetalk diary write\ntext: rain'}
        self.assertTrue(ob.store(message, {'user_id': 99, 'full_name': 'Delve Bot'}))
        account = self.accounts.account('zulip:chat.example:42')
        self.assertEqual(account.stored()['records'], {})
        self.assertEqual(len(self.st.observations()), 1)
        self.assertEqual(self.st.observations()[0]['author']['did'], 'zulip:chat.example:42')
        self.assertFalse(ob.store(message, {'user_id': 99, 'full_name': 'Delve Bot'}))

    def test_town_stays_read_only_and_other_writes_stay_unimplemented(self):
        body = {'repo': 'did:web:' + HOST, 'collection': COLLECTION, 'record': request()}
        for verb in ('createRecord', 'putRecord', 'deleteRecord'):
            self.assertEqual(self.call('/xrpc/com.atproto.repo.' + verb, body, self.robin['credential'], hostname=HOST)[0], 405)
        self.assertEqual(self.call('/xrpc/com.atproto.repo.applyWrites', {}, self.robin['credential'])[0], 501)
        self.assertEqual(self.rpc('repo.getRecord', repo='did:web:' + HOST, collection=COLLECTION, rkey=self.rkey)[0], 400)
        self.assertFalse(Config().requests)
