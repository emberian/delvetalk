"""Actual bounded catalogue consumers: no expanded history, exact root reads separate."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from conformance import test_agent_api as fixture
import portal
import resident_store
import world


class CatalogueConsumers(unittest.TestCase):
    def setUp(self):
        self.http = fixture.AgentHTTPTest(methodName='runTest')
        self.http.setUp()
        self.addCleanup(self.http.doCleanups)

    def test_account_pages_omit_roots_preserve_isolation_and_bind_revision(self):
        h = self.http
        token = h.enroll()
        secret = 'Private source and state are absent from catalogue rows.'
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {'secret': secret}, 'commands': {}}
        status, created, _ = h.turn(token, 'secret-create', {'op': 'create', 'object': 'private-object',
            'protocol': protocol, 'law': [fixture.A]})
        self.assertEqual(status, 200, created)
        self.assertEqual(created['reply']['kind'], 'committed')
        with patch.object(resident_store.Resident, '_snapshot', side_effect=AssertionError('history export')):
            status, first, _ = h.request('GET', '/AGENTS.md/world?limit=1', token=token)
            self.assertEqual(status, 200, first)
            self.assertEqual(len(first['objects']), 1)
            self.assertNotIn(secret, portal.canonical(first).decode())
            self.assertNotIn('root', first['objects'][0])
            self.assertEqual(portal.loads(first['exactJson'])['objects'], first['objects'])
            names = [first['objects'][0]['object']]
            page = first
            while page['links']['next']:
                status, page, _ = h.request('GET', page['links']['next'], token=token)
                self.assertEqual(status, 200, page)
                self.assertEqual(page['head'], first['head'])
                names.extend(row['object'] for row in page['objects'])
            self.assertEqual(names, ['notebook', 'private-object', 'source-desk'])
            self.assertEqual(h.inspect(token, 'private-object')['state']['secret'], secret)
            other = h.enroll(fixture.B)
            status, second, _ = h.request('GET', '/AGENTS.md/world', token=other)
            self.assertEqual(status, 200, second)
            self.assertNotIn('private-object', [row['object'] for row in second['objects']])
            root = h.inspect(token, 'private-object')
            status, refused, _ = h.turn(token, 'refusal-moves-head', {'op': 'invoke',
                'object': 'private-object', 'expected': root, 'command': 'missing', 'input': {}})
            self.assertEqual(status, 200, refused)
            self.assertEqual(refused['reply']['kind'], 'refused')
            status, stale, _ = h.request('GET', first['links']['next'], token=token)
            self.assertEqual(status, 400, stale)
            self.assertIn('stale catalogue cursor', str(stale))
            self.assertEqual(h.request('GET', first['links']['refresh'], token=token)[0], 200)
            for query in ('limit=0', 'limit=65', 'limit=wrong', 'cursor={}', 'object=notebook&limit=1'):
                self.assertEqual(h.request('GET', '/AGENTS.md/world?' + query, token=token)[0], 400)

    def test_public_pages_are_readonly_and_do_not_export_history(self):
        h = self.http
        for name in ('a', 'z'):
            response = world.exchange(h.database, {'op': 'create', 'object': name,
                'principal': 'operator', 'intent': 'create-' + name, 'protocol': h.protocol,
                'law': [fixture.A]}, profile='compiled')
            self.assertEqual(response['kind'], 'committed')
        before = h.database.read_bytes()
        with patch.object(world, 'snapshot', side_effect=AssertionError('expanded history')):
            status, first, _ = h.request('GET', '/api/world?limit=1')
            self.assertEqual(status, 200, first)
            self.assertEqual([row['id'] for row in first['objects']], ['a'])
            self.assertIsNotNone(first['next'])
            status, second, _ = h.request('GET', first['next'])
            self.assertEqual(status, 200, second)
            self.assertEqual([row['id'] for row in second['objects']], ['shared-counter'])
            self.assertNotIn('root', second['objects'][0])
            self.assertEqual(h.request('HEAD', '/api/world?limit=1')[0], 200)
        self.assertEqual(h.database.read_bytes(), before)


class NativeCatalogueBoundary(unittest.TestCase):
    def test_large_identity_budget_malformed_requests_and_checkpoint_cursor(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'resident.sqlite3'
            program = {'profile': 'delvetalk-local-v1', 'name': 'Ω' * 400,
                       'initial': {}, 'commands': {}}
            with resident_store.Resident(database, profile='compiled') as resident:
                for name in ('a' * 25000, 'b'):
                    reply = resident.exchange({'op': 'create', 'object': name,
                        'principal': 'reader', 'intent': name[:1], 'protocol': program, 'law': []})
                    self.assertEqual(reply['kind'], 'committed')
                page = world.catalogue_page(None, receiver=resident, limit=1)
                self.assertLessEqual(len(world.wire_dumps(page).encode()), 65536)
                self.assertEqual(page['objects'][0]['name'], 'Ω' * 256)
                self.assertTrue(page['objects'][0]['nameTruncated'])
                cursor = page['nextCursor']
                before = resident.sequence, resident.head
                good = {'op': 'catalogue-page', 'principal': 'reader', 'limit': 1, 'cursor': None}
                for changes in ({'limit': 0}, {'limit': 65}, {'limit': True}, {'limit': 1.5},
                                {'cursor': {}}, {'cursor': {'after': ''}}, {'principal': ''}, {'extra': 1}):
                    with self.subTest(changes=changes), self.assertRaises(ValueError):
                        resident.query({**good, **changes})
                self.assertEqual((resident.sequence, resident.head), before)
                resident.checkpoint()
            with resident_store.Resident(database, profile='compiled') as resident:
                page = world.catalogue_page(None, receiver=resident, cursor=cursor, limit=1)
                self.assertEqual([row['object'] for row in page['objects']], ['b'])
                self.assertIsNone(page['nextCursor'])
                reply = resident.exchange({'op': 'create', 'object': 'c' * 70000,
                    'principal': 'reader', 'intent': 'oversize', 'protocol': program, 'law': []})
                self.assertEqual(reply['kind'], 'committed')
                page = world.catalogue_page(None, receiver=resident, limit=2)
                with self.assertRaisesRegex(ValueError, 'catalogue identity response capacity'):
                    world.catalogue_page(None, receiver=resident, cursor=page['nextCursor'])


if __name__ == '__main__':
    unittest.main()
