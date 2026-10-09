"""Portal composition: real Lean effects, captured actions, and HTTP boundaries."""
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import portal as p


class PortalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.base = Path(cls.temp.name)
        cls.seed = cls.base / 'seed'
        p.bootstrap.run_bootstrap(cls.seed)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=self.base)
        self.addCleanup(self.tmp.cleanup)
        self.world = Path(self.tmp.name) / 'world'
        self.world.mkdir()
        for name in ('manifest.json', 'world.json'):
            shutil.copyfile(self.seed / name, self.world / name)
        (self.world / 'artifacts').symlink_to(self.seed / 'artifacts', target_is_directory=True)
        self.app = p.Portal(self.world)

    def interactive(self, principal='moss'):
        return p.Portal(self.world, principal=principal, allow_local_actions=True)

    def lamp(self, app=None):
        return (app or self.app).object(p.bootstrap.SIGN)

    def draft(self, app, card=None):
        card = card or self.lamp(app)
        return app.prepare({'card': card['card'], 'action': card['actions'][0]['id'], 'fields': {}})

    def test_read_only_card_source_token_proposal_and_no_world_write(self):
        before = (self.world / 'world.json').read_bytes()
        card = self.lamp()
        self.assertNotIn('root', card)
        self.assertNotIn('source', card)
        self.assertNotIn('sha256', json.dumps(card))
        token = card['actions'][0]['token']
        result = self.app.interpretation({'card': card['card'], 'text': token})
        self.assertEqual(result['status'], 'proposed')
        draft = self.draft(self.app, card)
        self.assertFalse(draft['canExecute'])
        self.assertEqual(draft['token'], token)
        self.assertNotIn('principal', draft['wire'])
        self.assertNotIn('intent', draft['wire'])
        with self.assertRaises(PermissionError):
            self.app.execute({'draft': draft['draft']})
        detail = self.app.detail(card['card'])
        self.assertIn('source', detail)
        self.assertEqual(detail['root']['version'], card['version'])
        self.assertTrue(detail['history'])
        self.assertEqual(before, (self.world / 'world.json').read_bytes())

    def test_repository_preparation_preserves_exact_draft_without_submission(self):
        draft = self.draft(self.app)
        before = (self.world / 'world.json').read_bytes()
        prepared = self.app.repository_prepare({'draft': draft['draft']})
        record = p.loads(prepared['recordJson'])
        self.assertEqual(p.loads(record['requestJson']), draft['wire'])
        self.assertEqual(prepared, self.app.repository_prepare({'draft': draft['draft']}))
        self.assertEqual(before, (self.world / 'world.json').read_bytes())
        self.assertIsNone(self.app.draft(draft['draft'])['outcome'])

    def test_exact_inspection_and_wire_survive_browser_number_limits(self):
        app = self.interactive()
        card = self.lamp(app)
        saved = app._read('cards', card['card'])
        huge = 10 ** 80 + 1
        saved['view']['root']['state']['large'] = huge
        p.save(app.state / 'cards' / (card['card'] + '.json'), saved)
        detail = app.detail(card['card'])
        self.assertIn(str(huge), detail['exact']['state'])
        self.assertEqual(p.loads(detail['exact']['root']), detail['root'])
        draft = self.draft(app, card)
        self.assertIn(str(huge), draft['wireJson'])
        self.assertEqual(p.loads(draft['wireJson']), draft['wire'])

    def test_stale_snapshot_refuses_and_restart_recovers_exact_receipt(self):
        app = self.interactive()
        old = self.lamp(app)
        first = self.draft(app, old)
        reply = app.execute({'draft': first['draft']})
        self.assertEqual(reply['kind'], 'committed', reply)
        before = (self.world / 'world.json').read_bytes()
        self.assertEqual(self.interactive().execute({'draft': first['draft']}), reply)
        self.assertEqual(before, (self.world / 'world.json').read_bytes())
        second = self.draft(app, old)
        stale = app.execute({'draft': second['draft']})
        self.assertEqual(stale['kind'], 'refused')
        self.assertEqual(stale['reply']['data'], 'stale read root')
        self.assertEqual(app.card(old['card']), old)
        # The prior card is still old even when the current world advances.
        self.assertGreater(self.lamp(app)['version'], old['version'])

    def test_authority_is_lean_not_the_offered_action(self):
        app = self.interactive('uninvited')
        draft = self.draft(app)
        result = app.execute({'draft': draft['draft']})
        self.assertEqual(result['kind'], 'refused')
        self.assertNotEqual(result['reply']['data'], 'stale read root')
        other = self.interactive('moss')
        with self.assertRaises(PermissionError):
            other.execute({'draft': draft['draft']})

    def test_uncertain_commit_recovery_precedes_changed_runtime_check(self):
        app = self.interactive()
        draft = self.draft(app)
        import worker
        original = worker.command
        def lose_reply(*args, **kwargs):
            original(*args, **kwargs)
            raise subprocess.TimeoutExpired('reply-lost', 1)
        with patch.object(worker, 'command', side_effect=lose_reply):
            result = app.execute({'draft': draft['draft']})
        self.assertEqual(result['kind'], 'uncertain')
        before = (self.world / 'world.json').read_bytes()
        with patch.object(p.bootstrap.history, 'runtime', side_effect=AssertionError('must recover first')):
            result = self.interactive().execute({'draft': draft['draft']})
        self.assertEqual(result['kind'], 'committed')
        self.assertEqual(before, (self.world / 'world.json').read_bytes())

    def test_pending_runtime_change_and_forged_overrides_refuse(self):
        app = self.interactive()
        card = self.lamp(app)
        with self.assertRaises(ValueError):
            app.prepare({'card': card['card'], 'action': card['actions'][0]['id'], 'principal': 'owner'})
        draft = self.draft(app, card)
        before = (self.world / 'world.json').read_bytes()
        with patch.object(p.bootstrap.history, 'runtime', return_value={}):
            with self.assertRaisesRegex(ValueError, 'Runtime pins'):
                app.execute({'draft': draft['draft']})
        self.assertEqual(before, (self.world / 'world.json').read_bytes())

    def test_http_assets_csrf_origin_host_and_duplicate_keys(self):
        server = p.make_server(self.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown(); server.server_close(); thread.join()
        self.addCleanup(close)
        def request(method, path, body=None, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            try:
                conn.request(method, path, body, headers or {})
                reply = conn.getresponse()
                return reply.status, reply.read(), dict(reply.getheaders())
            finally:
                conn.close()
        status, raw, headers = request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'DelveTalk', raw)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(request('GET', '/static/app.js')[0], 200)
        self.assertEqual(request('GET', '/static/style.css')[0], 200)
        self.assertEqual(request('GET', '/api/world', headers={'Host': 'evil.example'})[0], 403)
        card = self.lamp()
        body = json.dumps({'card': card['card'], 'action': card['actions'][0]['id']})
        headers = {'Content-Type': 'application/json'}
        self.assertEqual(request('POST', '/api/prepare', body, headers)[0], 403)
        headers['X-Delvetalk-CSRF'] = self.app.csrf
        headers['Origin'] = 'https://evil.example'
        self.assertEqual(request('POST', '/api/prepare', body, headers)[0], 403)
        del headers['Origin']
        self.assertEqual(request('POST', '/api/prepare', body, headers)[0], 200)
        self.assertEqual(request('POST', '/api/prepare', '{"card":"a","card":"b"}', headers)[0], 400)
        self.assertEqual(request('GET', '/../../world.json')[0], 404)
        self.assertEqual(request('GET', '/api/object?object=x&object=y')[0], 400)

    def test_short_token_cannot_silently_rebase_or_select_another_card(self):
        card = self.lamp()
        another = self.lamp()
        result = self.app.interpretation({'card': another['card'], 'text': card['actions'][0]['token']})
        self.assertEqual(result['status'], 'clarify')
        self.assertEqual(self.app.card(card['card'])['card'], card['card'])
        with self.assertRaises(ValueError):
            self.app.card('../world')


if __name__ == '__main__':
    unittest.main()
