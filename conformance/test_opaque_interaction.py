"""Source-owned private encounter, exact opaque receiving and receipt recovery."""
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import agent_heaps
import source_object
import world
import test_agent_api as api_fixture

spec = importlib.util.spec_from_file_location('private_counter', ROOT / 'protocols/private-counter/package.py')
private_counter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(private_counter)


class OpaqueInteraction(unittest.TestCase):
    def test_source_view_current_invoke_exact_retry_and_private_custody(self):
        alice = {'accountId': 'a' * 32, 'did': 'did:plc:' + 'a' * 24}
        bob = {'accountId': 'b' * 32, 'did': 'did:plc:' + 'b' * 24}
        carol = {'accountId': 'c' * 32, 'did': 'did:plc:' + 'c' * 24}
        protocol = private_counter.counter()
        alternate = source_object.load([{'name': 'Counter', 'source':
            (ROOT / 'protocols/private-counter/Counter.obend').read_text().replace(
                'state.count + input.amount', 'state.count + input.amount + 10n')}], syntax='objective-bend-object')
        authority = private_counter.authority(alice['did'], bob['did'])
        self.assertEqual(authority['read'], [alice['did']])
        self.assertEqual(authority['view'], {'main': 'public'})
        for backend in ('file', 'resident'):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                database = home / 'world.json'
                if backend == 'resident': world.configure_resident(database)
                scope = world.resident_session(database) if backend == 'resident' else nullcontext()
                with scope:
                    created = world.exchange(database, {'op': 'create', 'object': 'counter',
                        'principal': alice['did'], 'intent': 'create', 'protocol': protocol, 'law': authority}, profile='compiled')
                    self.assertEqual(created['kind'], 'committed', created)
                    with agent_heaps.HeapManager(home / 'accounts', database) as accounts:
                        view = accounts.opaque_view(bob, 'shared', 'counter')
                        self.assertEqual(view['result']['prose'], 'Count: 0')
                        public = world.opaque_view(database, 'counter', principal=bob['did'],
                            audience='public', expected=view['reference'])
                        self.assertEqual(public['audience'], 'public')
                        offered = view['result']['actions']['add']
                        selected = world.query(database, {'op': 'opaque-select', 'object': 'counter',
                            'principal': bob['did'], 'intent': 'one', 'command': offered['command'], 'input': offered['input']})
                        request = world.opaque_request('counter', view['reference'], offered['command'], offered['input'],
                            principal=bob['did'], intent='one')
                        self.assertEqual(selected, request)
                        compact = {k: v for k, v in request.items() if k != 'principal'}
                        first = accounts.turn(bob, 'shared', compact)
                        self.assertEqual(first['kind'], 'committed', first)
                        self.assertEqual(first['data']['result'], {'count': 1})
                        forwarded = accounts.turn(carol, 'shared', compact)
                        self.assertEqual(forwarded['kind'], 'refused')
                        with self.assertRaises((ValueError, RuntimeError)):
                            world.opaque_view(database, 'counter', principal=bob['did'],
                                audience='public', expected=view['reference'])
                        for value in (view, first):
                            text = world.wire_dumps(value)
                            self.assertNotIn('private-counter-state-secret', text)
                            self.assertNotIn('private-counter-diagnostic-secret', text)
                            self.assertNotIn('"root"', text)
                            self.assertNotIn('"protocol"', text)
                        stale = accounts.turn(bob, 'shared', {**compact, 'intent': 'stale'})
                        self.assertEqual(stale['kind'], 'refused')
                        fresh = accounts.opaque_view(bob, 'shared', 'counter')
                        failed = accounts.turn(bob, 'shared', {**compact, 'intent': 'diagnostic',
                            'expected': fresh['reference'], 'input': {'amount': 101}})
                        self.assertEqual(failed['data'], 'opaque invocation refused')
                        for query in ({'op': 'inspect', 'object': 'counter', 'principal': bob['did']},
                            {'op': 'object-history', 'object': 'counter', 'principal': bob['did'],
                             'before': 3, 'offset': 0, 'limit': 32}):
                            with self.assertRaises((ValueError, RuntimeError)):
                                world.query(database, query)
                        with self.assertRaises((ValueError, RuntimeError)):
                            world.capture_roots(database, ['counter'], principal=bob['did'])
                        owner_root = accounts.inspect(alice, 'shared', 'counter')
                        closed_view = {**authority, 'view': {'main': []}}
                        changed = world.exchange(database, {'op': 'law', 'object': 'counter',
                            'principal': alice['did'], 'intent': 'close-view', 'expected': owner_root, 'law': closed_view}, profile='compiled')
                        self.assertEqual(changed['kind'], 'committed', changed)
                        with self.assertRaises((ValueError, RuntimeError)):
                            world.opaque_view(database, 'counter', principal=alice['did'], audience='public')
                        with self.assertRaises((ValueError, RuntimeError)):
                            accounts.opaque_view(bob, 'shared', 'counter')
                        blind = world.query(database, {'op': 'opaque-select', 'object': 'counter',
                            'principal': bob['did'], 'intent': 'without-view', 'command': 'add', 'input': {'amount': 1}})
                        blind_result = accounts.turn(bob, 'shared', {k: v for k, v in blind.items() if k != 'principal'})
                        self.assertEqual(blind_result['data']['result'], {'count': 2})
                        owner_root = accounts.inspect(alice, 'shared', 'counter')
                        old_code = world.query(database, {'op': 'opaque-select', 'object': 'counter',
                            'principal': bob['did'], 'intent': 'old-code', 'command': 'add', 'input': {'amount': 1}})
                        replaced = world.exchange(database, {'op': 'reprogram', 'object': 'counter',
                            'principal': alice['did'], 'intent': 'replace-source', 'expected': owner_root,
                            'protocol': alternate, 'state': owner_root['state']}, profile='compiled')
                        self.assertEqual(replaced['kind'], 'committed', replaced)
                        old_result = accounts.turn(bob, 'shared', {k: v for k, v in old_code.items() if k != 'principal'})
                        self.assertEqual(old_result['kind'], 'refused')
                        owner_root = accounts.inspect(alice, 'shared', 'counter')
                        self.assertEqual(source_object.plain(source_object.state_data(owner_root))['count'], 2)
                        revoked = {**authority, 'invoke': {'add': [alice['did']]}, 'view': {'main': []}}
                        changed = world.exchange(database, {'op': 'law', 'object': 'counter',
                            'principal': alice['did'], 'intent': 'revoke', 'expected': owner_root, 'law': revoked}, profile='compiled')
                        self.assertEqual(changed['kind'], 'committed', changed)
                        with self.assertRaises((ValueError, RuntimeError)):
                            accounts.opaque_view(bob, 'shared', 'counter')
                        denied = accounts.turn(bob, 'shared', {**compact, 'intent': 'revoked', 'expected': fresh['reference']})
                        self.assertEqual(denied['kind'], 'refused')
                        self.assertEqual(accounts.turn(bob, 'shared', compact), first)
                        self.assertEqual(world.retained_reply(database, {**request, 'principal': carol['did']}), forwarded)
                        self.assertNotEqual(forwarded, first)
                        self.assertIsNone(world.retained_reply(database, {**request, 'principal': 'did:plc:dddddddddddddddddddddddd'}))
                        private = world.snapshot(database)
                        self.assertIn('private-counter-state-secret', world.wire_dumps(private['opaqueCustody']))
                        self.assertIn('private-counter-diagnostic-secret', world.wire_dumps(private['opaqueCustody']))
                # Fresh physical process/account manager recovers the admitted projection.
                restart_scope = world.resident_session(database) if backend == 'resident' else nullcontext()
                with restart_scope, agent_heaps.HeapManager(home / 'accounts', database) as restarted:
                    self.assertEqual(restarted.turn(bob, 'shared', compact), first)
                    self.assertEqual(restarted.receipt(bob, 'shared', 'one'), first)


class OpaqueHTTP(unittest.TestCase):
    setUp = api_fixture.AgentHTTPTest.setUp
    request = api_fixture.AgentHTTPTest.request
    enroll = api_fixture.AgentHTTPTest.enroll
    turn = api_fixture.AgentHTTPTest.turn

    def test_verified_account_uses_private_source_encounter(self):
        authority = private_counter.authority(api_fixture.A, api_fixture.B)
        created = world.exchange(self.database, {'op': 'create', 'object': 'private-counter',
            'principal': api_fixture.A, 'intent': 'private-counter',
            'protocol': private_counter.counter(), 'law': authority}, profile='compiled')
        self.assertEqual(created['kind'], 'committed', created)
        token = self.enroll(api_fixture.B)
        path = '/AGENTS.md/world?realm=shared&object=private-counter&view=opaque'
        self.assertEqual(self.request('GET', path)[0], 403)
        status, view, _ = self.request('GET', path, token=token)
        self.assertEqual(status, 200, view)
        action = view['result']['actions']['add']
        status, result, _ = self.turn(token, 'opaque-http', {'op': 'opaque-invoke',
            'object': 'private-counter', 'expected': view['reference'],
            'command': action['command'], 'input': action['input']}, realm='shared')
        self.assertEqual(status, 200, result)
        self.assertEqual(result['reply']['data']['result'], {'count': 1})
        self.assertNotIn('private-counter-state-secret', world.wire_dumps(result))
        self.assertNotEqual(self.request('GET', '/AGENTS.md/world?realm=shared&object=private-counter', token=token)[0], 200)


if __name__ == '__main__':
    unittest.main()
