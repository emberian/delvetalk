"""Actual HTTP public-preview boundaries, ephemeral resources and local isolation."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import portal as p

ORIGIN = 'https://delvetalk.example'
HOST = 'delvetalk.example'


class PublicPortalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.addCleanup(setattr, sys, 'dont_write_bytecode', sys.dont_write_bytecode)
        protocol = {'profile': 'delvetalk-local-v1', 'name': 'A public counter',
            'initial': {'count': 0}, 'commands': {'add': {'require': [],
                'set': {'count': ['input', 'amount']}, 'result': ['literal', 'ok'], 'outbox': []}},
            'affordances': {'add': {'fields': {'amount': {'type': 'nat', 'maximum': 10}}}}}
        p.save(self.directory / 'world.json', {'objects': {'counter': {
            'protocol': protocol, 'state': {'count': 0}, 'law': ['moss'], 'version': 0}}, 'receipts': []})
        p.save(self.directory / 'manifest.json', {'cafe': 'counter',
            'runtime': p.bootstrap.history.runtime('transactions')})
        self.before = self.files()
        self.app = p.Portal(self.directory, public_origin=ORIGIN)
        self.server = p.make_server(self.app)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        def close():
            self.server.shutdown()
            self.server.server_close()
            thread.join()
        self.addCleanup(close)

    def files(self):
        return {str(path.relative_to(self.directory)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.directory.rglob('*') if path.is_file()}

    def request(self, method, path, payload=None, headers=None):
        selected = {'Host': HOST}
        body = None
        if payload is not None:
            body = json.dumps(payload)
            selected.update({'Content-Type': 'application/json', 'X-Delvetalk-CSRF': self.app.csrf,
                             'Origin': ORIGIN})
        selected.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=selected)
            response = connection.getresponse()
            raw = response.read()
            if method != 'HEAD' and response.getheader('Content-Type', '').startswith('application/json'):
                raw = p.loads(raw)
            return response.status, raw
        finally:
            connection.close()

    def card(self):
        status, card = self.request('GET', '/api/object?object=counter')
        self.assertEqual(status, 200, card)
        return card

    def prepare(self, card):
        status, draft = self.request('POST', '/api/prepare', {
            'card': card['card'], 'action': 'a1', 'fields': {'amount': 3}})
        self.assertEqual(status, 200, draft)
        return draft

    def test_https_origin_is_explicit_and_incompatible_with_authority(self):
        for origin in ('http://delvetalk.example', ORIGIN + '/', ORIGIN + '/path',
                       ORIGIN + '?x=1', 'https://user@delvetalk.example', 'https://DELVETALK.example',
                       'https://delvetalk.example:0', 'https://delvetalk.example:99999'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                p.Portal(self.directory, public_origin=origin)
        for kwargs in ({'principal': 'moss'}, {'allow_local_actions': True},
                       {'proposer': lambda *_: None}, {'state': self.directory / 'private'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                p.Portal(self.directory, public_origin=ORIGIN, **kwargs)
        self.assertEqual(self.files(), self.before)
        self.assertFalse((self.directory / 'portal-custody').exists())

    def test_host_origin_and_cross_site_entry_navigation(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        for headers in ({'Host': 'evil.example'}, {'Host': '127.0.0.1:' + str(self.server.server_port)},
                        {'Origin': 'http://' + HOST}, {'Origin': 'https://other.example'},
                        {'Host': 'wrong.example', 'X-Forwarded-Host': HOST, 'X-Forwarded-Proto': 'https'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('GET', '/api/world', headers=headers)[0], 403)
        navigate = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'document'}
        self.assertEqual(self.request('GET', '/?object=counter', headers=navigate)[0], 200)
        self.assertEqual(self.request('GET', '/api/object?object=counter', headers=navigate)[0], 403)
        self.assertEqual(self.request('GET', '/', headers={**navigate, 'Sec-Fetch-Dest': 'iframe'})[0], 403)
        self.assertEqual(self.request('GET', '/', headers={**navigate, 'Sec-Fetch-Mode': 'no-cors'})[0], 403)
        self.assertEqual(self.request('GET', '/static/app.js', headers={'Sec-Fetch-Site': 'same-origin'})[0], 200)
        self.assertEqual(self.request('GET', '/api/world', headers={'Origin': ORIGIN})[0], 200)
        self.assertEqual(self.request('HEAD', '/'), (200, b''))
        self.assertEqual(self.request('HEAD', '/api/world'), (200, b''))
        self.assertEqual(self.request('POST', '/api/prepare', {}, headers=navigate)[0], 403)
        self.assertEqual(self.files(), self.before)

    def test_public_routes_cannot_initialize_private_custody(self):
        prohibited = ['/api/execute', '/api/repository/prepare', '/api/authoring/source',
                      '/api/authoring/draft', '/api/authoring/status', '/api/authoring/prepare',
                      '/api/authoring/execute', '/api/authoring/run', '/api/compiler/jobs', '/api/clerk/status']
        for path in prohibited:
            for method in ('GET', 'POST'):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(method, path, {} if method == 'POST' else None)[0], 403)
        status, world = self.request('GET', '/api/world')
        self.assertEqual(status, 200)
        self.assertEqual(world['mode'], 'public-preview')
        self.assertEqual(world['custody']['kind'], 'ephemeral')
        self.assertEqual(world['capabilities'], {'execute': False, 'authoring': False, 'repository': False})
        self.assertIsNone(world['authoring'])
        self.assertIsNone(world['principal'])
        self.assertEqual(self.files(), self.before)
        self.assertFalse((self.directory / 'portal-custody').exists())
        self.assertFalse((self.directory / 'world.json.lock').exists())

    def test_exact_inspection_and_export_have_no_submission_identity_or_disk_effect(self):
        card = self.card()
        self.assertTrue(card['ephemeral'])
        self.assertLessEqual(card['expiresInSeconds'], p.PUBLIC_CACHE_TTL)
        status, detail = self.request('GET', '/api/detail?card=' + card['card'])
        self.assertEqual(status, 200)
        for key in ('source', 'state', 'law', 'root', 'history', 'runtime'):
            self.assertEqual(p.loads(detail['exact'][key]), detail[key])
        draft = self.prepare(card)
        self.assertTrue(draft['ephemeral'])
        self.assertFalse(draft['canExecute'])
        self.assertNotIn('execute', draft['links'])
        self.assertNotIn('principal', draft['wire'])
        self.assertNotIn('intent', draft['wire'])
        self.assertEqual(p.loads(draft['wireJson']), draft['wire'])
        saved = self.app._read('drafts', draft['draft'])
        self.assertNotIn('principal', saved['request'])
        self.assertNotIn('intent', saved['request'])
        self.assertNotIn('localPrincipal', saved)
        status, proposal = self.request('POST', '/api/interpret', {'card': card['card'], 'text': draft['token']})
        self.assertEqual(status, 200)
        self.assertEqual(proposal['status'], 'proposed')
        status, natural = self.request('POST', '/api/interpret', {'card': card['card'], 'text': 'add three please'})
        self.assertEqual(status, 200)
        self.assertEqual(natural['status'], 'escalate')
        self.assertEqual(natural['via'], 'none')
        self.assertEqual(self.files(), self.before)

    def test_cache_entry_and_byte_bounds_evict_without_persistent_growth(self):
        with patch.object(p, 'PUBLIC_CACHE_ENTRIES', 3):
            first = self.card()
            for _ in range(16):
                self.card()
            self.assertLessEqual(len(self.app.preview.records), 3)
            self.assertEqual(self.request('GET', '/api/card?card=' + first['card'])[0], 400)
        # Bound bytes independently of entry count. One card fits, two do not.
        size = len(next(iter(self.app.preview.records.values()))[1])
        with patch.object(p, 'PUBLIC_CACHE_BYTES', size + 1):
            latest = self.card()
            self.assertEqual(len(self.app.preview.records), 1)
            self.assertLessEqual(self.app.preview.bytes, size + 1)
            self.assertEqual(self.request('GET', '/api/card?card=' + latest['card'])[0], 200)
        with patch.object(p, 'PUBLIC_CACHE_BYTES', size - 1):
            status, result = self.request('GET', '/api/object?object=counter')
            self.assertEqual(status, 400)
            self.assertIn('byte bound', result['message'])
        with patch.object(p, 'PUBLIC_CACHE_ENTRIES', 1):
            draft = self.prepare(latest)
            self.assertEqual(self.request('GET', '/api/card?card=' + latest['card'])[0], 400)
            self.assertEqual(self.request('GET', '/api/draft?draft=' + draft['draft'])[0], 200)
        self.assertEqual(self.files(), self.before)

    def test_expired_and_restarted_aliases_refuse_instead_of_rebasing(self):
        with patch.object(p, 'PUBLIC_CACHE_TTL', 0.05):
            card = self.card()
            draft = self.prepare(card)
        time.sleep(0.06)
        for path in ('/api/card?card=' + card['card'], '/api/detail?card=' + card['card'],
                     '/api/draft?draft=' + draft['draft']):
            status, result = self.request('GET', path)
            self.assertEqual(status, 400)
            self.assertIn('expired', result['message'])
        self.assertEqual(self.request('POST', '/api/prepare', {'card': card['card'], 'action': 'a1',
                                                             'fields': {'amount': 3}})[0], 400)
        fresh = self.card()
        restarted = p.Portal(self.directory, public_origin=ORIGIN)
        with self.assertRaisesRegex(ValueError, 'expired or is unknown'):
            restarted.card(fresh['card'])
        self.assertEqual(self.files(), self.before)

    def test_local_durable_drafts_are_not_exposed_by_public_aliases(self):
        local = p.Portal(self.directory, principal='moss', allow_local_actions=True)
        card = local.object('counter')
        draft = local.prepare({'card': card['card'], 'action': 'a1', 'fields': {'amount': 3}})
        self.assertTrue(draft['canExecute'])
        self.assertEqual(local.world()['custody']['kind'], 'durable')
        restarted = p.Portal(self.directory, principal='moss', allow_local_actions=True)
        self.assertEqual(restarted.draft(draft['draft']), draft)
        before = self.files()
        for path in ('/api/card?card=' + card['card'], '/api/draft?draft=' + draft['draft']):
            status, result = self.request('GET', path)
            self.assertEqual(status, 400)
            self.assertNotIn('moss', json.dumps(result))
        self.assertEqual(self.files(), before)

    def test_interpreter_receives_portable_reference_and_child_contract(self):
        # This regression checks the composition boundary: a dropped children
        # declaration would let interpretation accept an invalid child name.
        card = self.card()
        saved = self.app._read('cards', card['card'])
        saved['card']['actions'][0]['children'] = [{'field': 'name'}]
        saved['card']['actions'][0]['fields'] = [{'name': 'name', 'label': 'name', 'type': 'string',
            'required': True, 'minLength': 1, 'maxLength': 64}]
        captured = self.app._store('cards', saved)
        object_ref = {'format': 'delvetalk-object-ref-v1', 'world': 'test-world', 'object': 'counter'}
        with patch.object(self.app, 'object_ref', return_value={'objectRef': object_ref}), \
                patch.object(p.interpret, 'interpret', wraps=p.interpret.interpret) as interpreting:
            status, bad = self.request('POST', '/api/interpret', {
                'card': captured, 'text': 'do ' + captured + ' a1 {"name":"nested/child"}'})
            self.assertEqual(status, 200)
            self.assertEqual(bad['status'], 'clarify')
            status, good = self.request('POST', '/api/interpret', {
                'card': captured, 'text': 'do ' + captured + ' a1 {"name":"direct-child"}'})
            self.assertEqual(status, 200)
            self.assertEqual(good['status'], 'proposed')
        self.assertEqual(interpreting.call_args.args[1]['objectRef'], object_ref)
        self.assertEqual(interpreting.call_args.args[1]['actions'][0]['children'], [{'field': 'name'}])


if __name__ == '__main__':
    unittest.main()
