"""Holder-scoped XRPC scratch worlds, real service keys, no network services.

Refuted by a scratch turn changing the town export, an issuer reading another
issuer's scratch, invalid auth reaching the host, an idle scratch surviving
home-clock expiry, or any response content appearing in the access log.
"""
import copy
import http.client
import json
import re
import urllib.parse
from pathlib import Path

from tests.host import served
from tests.test_http import DID
from transport.lexicon import DOCS, record_problems, validate
from tests.test_serviceauth import OTHER
from tests.test_xrpc_acts import ActsWorld, ProcedureCase
from tests.wire import nat, record
from tests.bend import counter_modules
from transport import mirror
from transport.atproto.cbor import block, from_json
from transport.atproto.sign import Key
from transport.host import HostClient
from transport.repo import NS, Repo


class SessionClient:
    def __init__(self, directory, world):
        self.directory, self.world = directory, world

    def send(self, q):
        return self.directory.send({'world': self.world, **q})

    def close(self):
        pass


class SessionsWorld(ActsWorld):
    """The serve envelope resolves scratches by (principal, name), then touches them."""
    def __init__(self):
        super().__init__()
        self.scratches, self.expired, self.clock = {}, {}, 0
        self.append(DID, 'town-genesis')

    def at(self, world):
        return SessionClient(self, world)

    def send(self, q):
        op = q['op']
        if op == 'world-scratch':
            self.calls.append(copy.deepcopy(q))
            name, who = q.get('name'), q['principal']
            if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9-]{0,31}', name):
                return {'status': 'error', 'message': 'a scratch name is [a-z][a-z0-9-]{0,31}'}
            key = who, 'scratch/' + name
            if key in self.scratches:
                return {'status': 'error', 'message': key[1] + ' exists'}
            if sum(k[0] == who for k in self.scratches) >= 2:
                return {'status': 'refused', 'class': 'capacity', 'reason': 'at most two scratches'}
            source = (q.get('from') or {}).get('world', 'town')
            if source.startswith('scratch/') and (who, source) not in self.scratches:
                return {'status': 'error', 'message': 'no ' + source + '; open one with world-scratch'}
            scratch = ActsWorld()
            self.scratches[key] = scratch, self.clock
            return {'status': 'scratch', 'world': key[1], 'height': 0, 'expires': self.clock + 360}
        if op == 'serve-status':
            self.calls.append(copy.deepcopy(q))
            return {'status': 'serving', 'scratches': [{'principal': who, 'world': world, 'expires': last + 360,
                                                       'lastTurn': last} for (who, world), (_, last) in self.scratches.items()]}
        if op == 'world-advance':
            self.calls.append(copy.deepcopy(q))
            self.clock = q['height']
            for key, (_, last) in list(self.scratches.items()):
                if last + 360 <= self.clock:
                    del self.scratches[key]
                    self.expired[key] = self.clock
            return {'status': 'advanced'}
        world = q.get('world', 'town')
        if world.startswith('scratch/'):
            self.calls.append(copy.deepcopy(q))
            key = q.get('principal'), world
            if key not in self.scratches:
                message = f'{world} expired at clock {self.expired[key]}' if key in self.expired else 'no ' + world
                return {'status': 'error', 'message': message + '; open one with world-scratch'}
            scratch, _ = self.scratches[key]
            self.scratches[key] = scratch, self.clock
            if op == 'world-status':
                return {'status': 'world', 'height': len(scratch.entries), 'clock': 0}
            if op == 'world-objects':
                names = getattr(scratch, 'names', ['diary'])
                ids = sorted(n for n in names if n > q.get('after', ''))[:4]
                return {'status': 'listed', 'ids': ids, 'more': any(n > (ids[-1] if ids else q.get('after', '')) for n in names)}
            if op == 'world-view':
                return {'status': 'viewed', 'version': scratch.version, 'state': record()}
            if op == 'world-card':
                return {'status': 'card', 'text': f'session-secret {q["object"]} version {scratch.version}\n'}
            reply = scratch.send(q)
            if op in ('world-turn', 'world-try'):
                reply['inPublic'] = True
            return reply
        if op == 'world-status':
            self.calls.append(copy.deepcopy(q))
            return {'status': 'world', 'height': len(self.entries), 'clock': self.clock}
        if op == 'world-objects':
            self.calls.append(copy.deepcopy(q))
            return {'status': 'listed', 'ids': [], 'more': False}
        return super().send(q)


class SessionCase(ProcedureCase):
    def make_host(self, directory):
        return SessionsWorld()

    def setUp(self):
        super().setUp()
        self.keys[OTHER] = Key(self.documents.repo(OTHER)['key'])
        self.front.repo = Repo(
            self.st.config.origin, Key.generate(), answers=self.st.answers, ledger=self.st.repo_ledger)
        self.count = 0
        self.st.firehose.parent.mkdir(parents=True, exist_ok=True)
        self.st.firehose.write_bytes(b'existing-event-bytes')

    def request(self, proc='openSession', body=None, token=None, method=None, raw=None, ctype='application/json', who=DID, **params):
        method = method or ('GET' if proc in ('getSession', 'listSessionRecords') else 'POST')
        token = self.token({'iss': who, 'lxm': NS + proc}) if token is None else token
        c = http.client.HTTPConnection(*self.front.server_address, timeout=10)
        path = '/xrpc/' + NS + proc + ('?' + urllib.parse.urlencode(params) if params else '')
        c.request(method, path, raw if raw is not None else json.dumps(body or {}),
                  {'Authorization': 'Bearer ' + token, 'Content-Type': ctype})
        r = c.getresponse()
        self.count += 1
        data, headers, status = r.read(), dict(r.getheaders()), r.status
        c.close()
        self.last_raw = data
        return status, json.loads(data), headers

    def open(self, name='lab', **extra):
        code, reply, _ = self.request(body={'name': name, **extra})
        self.assertEqual(code, 200, reply)
        self.assertEqual(reply['session'], 'scratch/' + name)
        self.output_valid('openSession', reply)
        return reply['session']

    def output_valid(self, name, reply):
        doc = DOCS[NS + name]
        self.assertEqual(validate(reply, doc['defs']['main']['output']['schema'], doc), [], reply)

    def public_state(self):
        code, car, _ = self.front.repo.serve(self.host, 'GET', 'com.atproto.sync.getRepo', {'did': self.front.repo.did}, None)
        self.assertEqual(code, 200, car)
        now = mirror.records(self.host, paint=False, answers=self.st.answers)
        def files(p):
            return (p.exists(), p.read_bytes() if p.is_file() else
                    {str(f.relative_to(p)): f.read_bytes() for f in p.rglob('*') if f.is_file()})
        return (len(self.host.entries), files(self.st.answers), mirror.plan(self.st, now), car,
                files(self.st.outbox), files(self.st.firehose), self.st.repo_ledger.read_bytes())

    def turn_body(self, session, intent='session-secret-intent'):
        return self.act(intent=intent, world=session)


class XrpcSessions(SessionCase):
    def test_open_act_list_changes_only_the_scratch_and_public_export_is_byte_identical(self):
        before = self.public_state()
        session = self.open(**{'from': {'world': 'town', 'height': 1}})
        status, view, _ = self.request('act', self.turn_body(session))
        self.assertEqual(status, 200, view)
        self.assertEqual(view['outcome']['status'], 'admitted')
        self.view_valid(view)
        first = view['receipt']
        retried = self.request('act', {**self.turn_body(session), 'call': {'object': 'diary', 'verb': 'changed'}})[1]
        self.assertEqual(retried['receipt'], first)
        status, listing, _ = self.request('listSessionRecords', session=session, collection=NS + 'card')
        self.assertEqual(status, 200, listing)
        self.output_valid('listSessionRecords', listing)
        [card] = listing['records']
        self.assertEqual((card['key'], card['value']['version']), ('diary', 1))
        self.assertIn('version 1', card['value']['card'])
        self.assertEqual(record_problems(card['value']), [])
        self.assertEqual(card['cid'], str(block(from_json(card['value']))[0]))
        self.assertEqual(self.public_state(), before)
        [opened] = [q for q in self.host.calls if q['op'] == 'world-scratch']
        self.assertEqual(opened['from'], {'world': 'town', 'height': 1})
        self.assertTrue(all(q['principal'] == DID and q['world'] == session for q in self.host.calls if q.get('world', '').startswith('scratch/')))

    def test_second_issuer_gets_identical_not_found_bytes_for_held_and_nonexistent_names(self):
        session = self.open()
        for proc in ('getSession', 'listSessionRecords', 'act', 'try', 'plan'):
            replies = []
            for name in (session, 'scratch/absent'):
                params = {'session': name, 'collection': NS + 'card'} if proc == 'listSessionRecords' else {'session': name}
                body = {'calls': [{'spell': 'delvetalk diary plant'}], 'intent': 'no', 'world': name} if proc == 'plan' else self.turn_body(name)
                status, reply, _ = self.request(proc, body, who=OTHER, **(params if proc in ('getSession', 'listSessionRecords') else {}))
                self.assertEqual((status, reply['error']), (404, 'RecordNotFound'))
                replies.append(self.last_raw)
            self.assertEqual(*replies)
        self.assertEqual(self.request('getSession', session=session)[0], 200)
        other = self.request(body={'name': 'lab'}, who=OTHER)
        self.assertEqual(other[0], 200, other[1])
        self.assertEqual(other[1]['session'], session)
        self.assertEqual(self.request('getSession', who=OTHER, session=session)[0], 200)

    def test_scratch_retry_ignores_public_answer_with_the_same_issuer_and_intent(self):
        self.assertEqual(self.request('act', self.act(intent='same'))[0], 200)
        public = mirror.answer_records(self.st.answers)
        session = self.open()
        status, answer, _ = self.request('act', self.turn_body(session, intent='same'))
        self.assertEqual(status, 200, answer)
        scratch = self.host.scratches[DID, session][0]
        self.assertEqual((len(scratch.entries), scratch.version), (1, 1))
        self.assertEqual(mirror.answer_records(self.st.answers), public)
        self.assertFalse(any(q['op'] == 'world-entry' for q in scratch.calls))
        self.assertEqual(self.request('act', self.turn_body(session, intent='same'))[1]['receipt'], answer['receipt'])
        self.assertEqual(len(scratch.entries), 1)

    def test_expiry_during_listing_is_not_an_empty_success_and_host_outage_is_503(self):
        session = self.open()
        send = self.host.send
        def expires(q):
            if q['op'] == 'world-objects' and q.get('world') == session:
                send({'op': 'world-advance', 'principal': 'transport', 'height': 360})
            return send(q)
        self.host.send = expires
        status, reply, _ = self.request('listSessionRecords', session=session, collection=NS + 'card')
        self.assertEqual((status, reply['error']), (404, 'RecordNotFound'))
        self.host.send = lambda q: {'status': 'error', 'class': 'hostUnavailable'}
        status, reply, _ = self.request('getSession', session=session)
        self.assertEqual((status, reply['error']), (503, 'HostUnavailable'))

    def test_wrong_audience_expiry_method_and_key_never_reach_any_session_host_op(self):
        for proc in ('openSession', 'getSession', 'listSessionRecords', 'act', 'try', 'plan'):
            for claims, key in [({'aud': 'did:web:wrong.example'}, None), ({'exp': 999}, None),
                                ({'lxm': NS + 'getEntry'}, None), ({}, Key.generate())]:
                token = self.token({'lxm': NS + proc, **claims}, key=key)
                self.host.calls.clear()
                status, reply, _ = self.request(proc, {'name': 'lab'}, token=token, session='scratch/lab', collection=NS + 'card')
                self.assertEqual((status, reply['error']), (401, 'InvalidToken'))
                self.assertEqual(self.host.calls, [])

    def test_holder_try_and_atomic_plan_use_the_scratch_without_public_answer_or_preview_write(self):
        session = self.open()
        before = self.public_state()
        status, preview, _ = self.request('try', self.turn_body(session))
        self.assertEqual(status, 200, preview)
        self.assertEqual(preview['outcome']['status'], 'previewed')
        self.view_valid(preview, 'previewView')
        self.assertNotIn('receipt', preview)
        scratch = self.host.scratches[DID, session][0]
        self.assertEqual((scratch.entries, scratch.version, scratch.answers), ([], 0, {}))
        self.assertEqual(self.public_state(), before)
        status, view, _ = self.request('plan', {'world': session, 'intent': 'atomic-secret',
                                               'calls': [{'spell': 'delvetalk diary plant'}] * 2 + [{'spell': 'refuse-third'}]})
        self.assertEqual(status, 200, view)
        self.assertEqual(view['outcome']['status'], 'refused')
        self.assertEqual(scratch.version, 0)
        self.assertEqual(len(scratch.entries), 1)
        self.assertEqual(len([q for q in scratch.calls if q['op'] == 'world-turn']), 1)
        self.assertEqual(self.public_state(), before)
        status, view, _ = self.request('plan', {'world': session, 'intent': 'admitted-plan',
                                               'calls': [{'spell': 'delvetalk diary plant'}] * 8})
        self.assertEqual(status, 200, view)
        self.assertEqual(view['outcome']['status'], 'admitted')
        self.assertEqual((scratch.version, len(scratch.entries)), (1, 2))
        self.assertEqual(self.public_state(), before)

    def test_home_clock_expiry_refuses_every_read_turn_and_fork_then_recreation_is_new(self):
        session = self.open()
        self.request('act', self.turn_body(session))
        self.host.send({'op': 'world-advance', 'principal': 'transport', 'height': 360})
        for proc in ('getSession', 'listSessionRecords', 'act', 'try', 'plan', 'openSession'):
            body = ({'name': 'fork', 'from': {'world': session}} if proc == 'openSession' else
                    {'world': session, 'intent': 'no', 'calls': [{'spell': 'delvetalk diary plant'}]} if proc == 'plan' else self.turn_body(session))
            params = {'session': session, **({'collection': NS + 'card'} if proc == 'listSessionRecords' else {})}
            status, reply, _ = self.request(proc, body, **(params if proc in ('getSession', 'listSessionRecords') else {}))
            self.assertEqual((status, reply['error']), (404, 'RecordNotFound'), (proc, reply))
        self.assertEqual(self.open(), session)
        self.assertEqual(self.request('act', self.turn_body(session))[1]['receipt']['height'], 1)

    def test_status_host_expiry_touch_and_paged_cards_entries_and_repl_objects_validate(self):
        session = self.open()
        self.host.send({'op': 'world-advance', 'principal': 'transport', 'height': 359})
        code, status, _ = self.request('getSession', session=session)
        self.assertEqual(code, 200, status)
        self.assertEqual((status['status'], status['expires']), ('world', 719))
        self.output_valid('getSession', status)
        scratch = self.host.scratches[DID, session][0]
        scratch.names = ['diary', 'repl'] + [f'thing/{i:03d}' for i in range(103)]
        keys, cursor = [], None
        while True:
            code, page, _ = self.request('listSessionRecords', session=session, collection=NS + 'card', limit=100,
                                         **({'cursor': cursor} if cursor else {}))
            self.assertEqual(code, 200, page)
            self.output_valid('listSessionRecords', page)
            self.assertLessEqual(len(page['records']), 100)
            keys += [r['key'] for r in page['records']]
            cursor = page.get('cursor')
            if not cursor:
                break
        self.assertEqual(keys, sorted(mirror.card_key(k) for k in scratch.names))
        self.request('act', self.turn_body(session))
        code, entries, _ = self.request('listSessionRecords', session=session, collection=NS + 'entry')
        self.assertEqual(code, 200, entries)
        self.output_valid('listSessionRecords', entries)
        [entry] = entries['records']
        self.assertEqual(record_problems(entry['value']), [])
        self.assertEqual(entry['value']['entry'], {'$link': scratch.entries[0]['hash']})
        self.assertEqual(entry['cid'], str(block(from_json(entry['value']))[0]))
        self.assertNotIn('uri', entry)

    def test_entry_pages_follow_host_heights_and_reject_unknown_or_oversized_cursors(self):
        session = self.open()
        scratch = self.host.scratches[DID, session][0]
        for i in range(105):
            scratch.append(DID, f'entry-{i}')
        heights, cursor = [], None
        while True:
            code, page, _ = self.request('listSessionRecords', session=session, collection=NS + 'entry', limit=100,
                                         **({'cursor': cursor} if cursor else {}))
            self.assertEqual(code, 200, page)
            self.output_valid('listSessionRecords', page)
            heights += [int(r['key']) for r in page['records']]
            cursor = page.get('cursor')
            if not cursor:
                break
        self.assertEqual(heights, list(range(1, 106)))
        for cursor in ('106', '-1', '01', '9' * 5000):
            code, body, _ = self.request('listSessionRecords', session=session, collection=NS + 'entry', cursor=cursor)
            self.assertEqual((code, body['error']), (400, 'InvalidRequest'), body)

    def test_maximum_name_and_adversarial_bodies_queries_methods_and_collection(self):
        self.open('a' * 32)
        for body in ({}, {'name': 'a' * 33}, {'name': '../other'}, {'name': 'lab', 'readers': [OTHER]},
                     {'name': 'lab', 'from': []}, {'name': 'lab', 'from': {'world': 'town', 'height': True}},
                     {'name': 'lab', 'from': {'world': 'town', 'height': 0}}, {'name': 'lab', 'from': {'world': 'town', 'extra': 1}}):
            status, reply, _ = self.request(body=body)
            self.assertEqual((status, reply['error']), (400, 'InvalidRequest'), reply)
        session = 'scratch/' + 'a' * 32
        for params in ({'session': '../lab'}, {'session': session, 'collection': NS + 'answer'},
                       {'session': session, 'collection': NS + 'card', 'limit': 101},
                       {'session': session, 'collection': NS + 'card', 'limit': 0},
                       {'session': session, 'collection': NS + 'card', 'limit': '9' * 5000},
                       {'session': session, 'collection': NS + 'card', 'cursor': 'not-returned'}):
            status, reply, _ = self.request('listSessionRecords', **params)
            self.assertEqual((status, reply['error']), (400, 'InvalidRequest'), reply)
        for proc, method in [('openSession', 'GET'), ('getSession', 'POST'), ('listSessionRecords', 'POST')]:
            self.host.calls.clear()
            self.assertEqual(self.request(proc, {'name': 'lab'}, method=method)[0], 405)
            self.assertEqual(self.host.calls, [])

    def test_access_file_contains_method_path_status_did_and_no_session_response(self):
        session = self.open()
        self.request('act', self.turn_body(session))
        self.request('getSession', session=session)
        self.request('listSessionRecords', session=session, collection=NS + 'card')
        text = '\n'.join(self.access_lines(self.count))
        self.assertIn('POST /xrpc/' + NS + 'openSession 200', text)
        self.assertIn('GET /xrpc/' + NS + 'listSessionRecords 200', text)
        self.assertIn(DID, text)
        for content in ('session-secret', session, 'expires', 'version', 'diary', 'cardCid', '?session=', 'Bearer'):
            self.assertNotIn(content, text)


class XrpcSessionHost(SessionCase):
    """The same service facade composed with serve's scratch expiry and fork."""
    def make_host(self, directory):
        self.serving = served(str(Path(directory) / 'serve'), cleanup=self.addCleanup)
        host = HostClient(self.serving.sock)
        self.addCleanup(host.close)
        made = host.send({'op': 'world-create', 'principal': DID, 'identity': 'make-tally', 'object': 'tally',
                          'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
        self.assertEqual(made['status'], 'created', made)
        return host

    def test_real_scratch_fork_act_preview_list_and_expiry_leave_town_repository_unchanged(self):
        code, car, _ = self.front.repo.serve(self.host, 'GET', 'com.atproto.sync.getRepo', {'did': self.front.repo.did}, None)
        self.assertEqual(code, 200, car)
        height = self.host.send({'op': 'world-status'})['height']
        before = mirror.plan(self.st, mirror.records(self.host, paint=False, answers=self.st.answers))
        session = self.open(**{'from': {'world': 'town', 'height': height}})
        body = {'world': session, 'call': {'object': 'tally', 'verb': 'bump', 'fields': {}}, 'intent': 'b1'}
        preview = self.request('try', body)
        self.assertEqual(preview[0], 200, preview[1])
        self.assertEqual(preview[1]['outcome']['status'], 'previewed')
        self.assertFalse(self.st.answers.exists())
        self.assertEqual(self.request('act', body)[1]['outcome']['status'], 'admitted')
        code, page, _ = self.request('listSessionRecords', session=session, collection=NS + 'card')
        self.assertEqual(code, 200, page)
        self.output_valid('listSessionRecords', page)
        [card] = [r for r in page['records'] if r['value']['object'] == 'tally']
        self.assertEqual(card['value']['version'], 1)
        mine = self.host.at(session)
        self.addCleanup(mine.close)
        self.assertEqual(mine.send({'op': 'world-view', 'principal': DID, 'object': 'tally'})['state'], record(count=nat(1)))
        self.assertEqual(self.host.send({'op': 'world-status'})['height'], height)
        self.assertEqual(mirror.plan(self.st, mirror.records(self.host, paint=False, answers=self.st.answers)), before)
        self.assertEqual(self.front.repo.serve(self.host, 'GET', 'com.atproto.sync.getRepo', {'did': self.front.repo.did}, None)[1], car)
        self.assertFalse(self.st.answers.exists())
        self.assertFalse(self.st.outbox.exists())
        self.host.send({'op': 'world-advance', 'principal': 'transport', 'height': 360})
        for proc in ('getSession', 'listSessionRecords', 'act', 'try', 'plan'):
            params = {'session': session, **({'collection': NS + 'card'} if proc == 'listSessionRecords' else {})}
            data = {'world': session, 'intent': 'p', 'calls': [{'spell': 'delvetalk tally bump'}]} if proc == 'plan' else body
            status, error, _ = self.request(proc, data, **(params if proc in ('getSession', 'listSessionRecords') else {}))
            self.assertEqual((status, error['error']), (404, 'RecordNotFound'), error)
        self.assertEqual(list((Path(self.serving.sock).parent / 'scratch' / DID).iterdir()), [])


if __name__ == '__main__':
    import unittest
    unittest.main()
