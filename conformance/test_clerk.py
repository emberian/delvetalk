#!/usr/bin/env python3
"""Pinned-PDS transport adversaries with actual Lean admission and durable replay."""
import copy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('clerk_test', ROOT / 'scripts/clerk.py')
clerk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clerk)
A = 'did:plc:aaaaaaaaaaaaaaaaaaaaaaaa'
B = 'did:plc:bbbbbbbbbbbbbbbbbbbbbbbb'


class FakePDS:
    def __init__(self):
        self.records = {}
        self.calls = []
        self.service = clerk.PDS
        self.identity = None
        self.answer_cid = None

    def __call__(self, method, base, nsid, *, params):
        self.calls.append((method, base, nsid, params))
        assert method == 'GET' and base == clerk.PDS
        author = params['repo']
        if nsid.endswith('describeRepo'):
            return {'did': self.identity or author, 'didDoc': {'id': author, 'service': [{
                'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer', 'serviceEndpoint': self.service}]}}
        uri = f'at://{author}/{params["collection"]}/{params["rkey"]}'
        cid, value = self.records[uri]
        return {'uri': uri, 'cid': self.answer_cid or cid, 'value': value}


class ClerkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.pds = FakePDS()
        self.c = clerk.Clerk(self.state, self.pds)
        protocol = json.loads((ROOT / 'protocols/counter/protocol.json').read_text())
        result = self.c.bootstrap('counter', protocol, [A], [A, B])
        self.root = result['data']['root']

    def tearDown(self):
        self.temp.cleanup()

    def record(self, key='one', author=A, root=None, **extra):
        uri = f'at://{author}/{clerk.COLLECTION}/{key}'
        payload = {'object': 'counter', 'command': 'add', 'input': {'amount': 3},
                   'expected': root or self.root, **extra}
        self.pds.records[uri] = ('cid-' + key, {'$type': clerk.COLLECTION,
            'profile': 'delvetalk-live-v1', 'requestJson': clerk.world.wire_dumps(payload)})
        return uri, 'cid-' + key

    def test_commit_identity_binding_and_retry_without_network(self):
        uri, cid = self.record()
        receipt = self.c.receive(uri, cid)
        self.assertEqual(receipt['reply']['kind'], 'committed')
        self.assertEqual(receipt['reply']['data']['root']['state']['count'], 3)
        self.assertEqual(receipt['request']['principal'], A)
        self.assertEqual(receipt['source']['cid'], cid)
        self.assertEqual(receipt['request']['intent'], 'delve:' + uri)
        count = len(self.pds.calls)
        self.pds.records.clear()
        self.assertEqual(clerk.Clerk(self.state, self.pds).receive(uri, cid), receipt)
        self.assertEqual(len(self.pds.calls), count)
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)

    def test_stale_and_unauthorized_are_durable_lean_receipts(self):
        uri, cid = self.record()
        self.c.receive(uri, cid)
        stale = self.c.receive(*self.record('stale'))
        self.assertEqual(stale['reply']['data'], 'stale read root')
        denied = self.c.receive(*self.record('denied', author=B, root=self.c.snapshot('counter')['root']))
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        self.assertEqual(self.c.receive(*self.record('stale')), stale)

    def test_source_cannot_assert_principal_or_operation(self):
        for key, value in [('principal', A), ('op', 'law'), ('intent', 'forged')]:
            with self.subTest(key=key):
                uri, cid = self.record(key, author=B, **{key: value})
                with self.assertRaisesRegex(ValueError, 'unknown fields|unsupported remote operation'):
                    self.c.receive(uri, cid)
        self.assertEqual(self.c.snapshot('counter')['root'], self.root)

    def test_pinned_repository_identity_and_cid(self):
        uri, cid = self.record()
        self.pds.answer_cid = 'different'
        with self.assertRaisesRegex(ValueError, 'CID mismatch'):
            self.c.receive(uri, cid)
        self.pds.answer_cid = None
        self.pds.identity = B
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.c.receive(uri, cid)
        self.pds.identity = None
        self.pds.service = 'https://evil.invalid'
        with self.assertRaisesRegex(ValueError, 'pinned Delve PDS'):
            self.c.receive(uri, cid)
        self.assertEqual(self.c.snapshot('counter')['root'], self.root)

    def test_same_uri_edited_record_never_new_attempt(self):
        uri, cid = self.record()
        self.c.receive(uri, cid)
        with self.assertRaisesRegex(ValueError, 'different CID'):
            self.c.receive(uri, 'changed-cid')
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)

    def test_crash_after_world_commit_replays_retained_preimage(self):
        uri, cid = self.record()
        save = clerk.save
        calls = []
        def fail_receipt(path, value):
            if 'receipt' in value:
                calls.append(value)
                raise OSError('simulated receipt journal interruption')
            return save(path, value)
        with patch.object(clerk, 'save', fail_receipt):
            with self.assertRaisesRegex(OSError, 'interruption'):
                self.c.receive(uri, cid)
        self.pds.records.clear()
        recovered = self.c.receive(uri, cid)
        self.assertEqual(recovered, calls[0]['receipt'])
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)

    def test_unknown_repository_object_and_duplicate_members(self):
        uri, cid = self.record(author='did:plc:cccccccccccccccccccccccc')
        with self.assertRaisesRegex(ValueError, 'not configured'):
            self.c.receive(uri, cid)
        uri, cid = self.record('other', object='other')
        with self.assertRaisesRegex(ValueError, 'not configured'):
            self.c.receive(uri, cid)
        uri, cid = self.record('duplicate')
        self.pds.records[uri][1]['requestJson'] = '{"object":"counter","object":"other"}'
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.c.receive(uri, cid)

    def test_lossless_json_string_and_transport_constraints(self):
        value = Decimal('0.123456789012345678901234567890123456789')
        uri, cid = self.record('precise', input={'amount': 0, 'extra': value})
        receipt = self.c.receive(uri, cid)
        self.assertEqual(receipt['request']['input']['extra'], value)
        self.assertEqual(self.c.receive(uri, cid), receipt)
        with self.assertRaisesRegex(ValueError, 'only pinned'):
            clerk.PublicHTTP()('GET', 'https://evil.invalid', 'com.atproto.repo.getRecord')
        with self.assertRaisesRegex(ValueError, 'redirects'):
            clerk.NoRedirect().redirect_request(None, None, 302, '', {}, 'http://localhost')

    def root_record(self, key='root', root=None, author=None):
        envelope = self.c.snapshot('counter')
        if root is not None:
            envelope['root'] = root
            envelope['id'] = clerk.digest({key: value for key, value in envelope.items() if key != 'id'})
        raw = clerk.world.wire_dumps(envelope)
        uri = f'at://{author or clerk.delve.DID}/{clerk.ROOT_COLLECTION}/{key}'
        record = {'$type': clerk.ROOT_COLLECTION, 'profile': 'delvetalk-live-v1',
                  'object': 'counter', 'version': str(envelope['root']['version']),
                  'rootJson': raw, 'sha256': clerk.hashlib.sha256(raw.encode()).hexdigest()}
        self.pds.records[uri] = ('cid-' + key, record)
        return {'uri': uri, 'cid': 'cid-' + key}

    def feed_record(self, key, reference, text=None):
        payload = {'object': 'counter', 'command': 'add', 'input': {'amount': 2},
                   'expectedRootRef': reference}
        uri = f'at://{A}/{clerk.FEED}/{key}'
        text = text if text is not None else ('delvetalk-request v1\n```delvetalk-request\n'
                  + clerk.world.wire_dumps(payload) + '\n```\n🜉✾')
        self.pds.records[uri] = ('cid-' + key, {'$type': clerk.FEED, 'text': text,
                                             'createdAt': '2026-10-08T00:00:00Z'})
        return uri, 'cid-' + key

    def test_social_request_root_reference_and_retained_original(self):
        reference = self.root_record()
        uri, cid = self.feed_record('social', reference)
        receipt = self.c.receive(uri, cid)
        self.assertEqual(receipt['reply']['kind'], 'committed')
        self.assertEqual(receipt['request']['expected'], self.root)
        self.assertEqual(receipt['request']['principal'], A)
        journal = clerk.loads(next((self.state / 'requests').glob('*.json')).read_text())
        self.assertEqual(journal['record'], self.pds.records[uri][1])
        self.assertEqual(journal['resolvedRoot']['source']['cid'], reference['cid'])
        stale = self.c.receive(*self.feed_record('stale-social', reference))
        self.assertEqual(stale['reply']['data'], 'stale read root')
        self.assertEqual(self.c.snapshot('counter')['root']['state']['count'], 2)

    def test_oversized_resolved_request_never_reserves_journal_or_blocks_upgrade(self):
        oversized = copy.deepcopy(self.root)
        oversized['state']['large'] = 'x' * 65536
        reference = self.root_record(root=oversized)
        uri, cid = self.feed_record('oversized-ref', reference)
        self.assertLess(len(self.pds.records[uri][1]['text'].encode()), 1024)
        before = self.c.database.read_bytes()
        with self.assertRaisesRegex(ValueError, 'derived request exceeds 64 KiB'):
            self.c.receive(uri, cid)
        self.assertEqual(list((self.state / 'requests').glob('*.json')), [])
        self.assertEqual(self.c.database.read_bytes(), before)
        old = self.c.profile()
        with patch.object(clerk, 'pins', return_value={**old['profile']['pins'], 'test-new': 'a' * 64}):
            self.assertEqual(self.c.upgrade(old['sha256'])['status'], 'upgraded')

    def test_social_syntax_is_explicit_and_unambiguous(self):
        for index, text in enumerate(['ordinary prose', 'hello\ndelvetalk-request v1\n```delvetalk-request\n{}\n```',
                'delvetalk-request v1\nplease run this\n```delvetalk-request\n{}\n```',
                'delvetalk-request v1\n```json\n{}\n```',
                'delvetalk-request v1\n```delvetalk-request\n{}\n```\n```delvetalk-request\n{}\n```']):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, 'exact marker'):
                    self.c.receive(*self.feed_record(str(index), {}, text))

    def test_root_reference_custodian_checksum_and_ambiguity(self):
        ref = self.root_record(author=B)
        with self.assertRaisesRegex(ValueError, 'custodian'):
            self.c.receive(*self.feed_record('wrong-author', ref))
        ref = self.root_record()
        self.pds.records[ref['uri']][1]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            self.c.receive(*self.feed_record('bad-hash', ref))
        ref = self.root_record()
        uri, cid = self.record('two-roots', expectedRootRef=ref)
        with self.assertRaisesRegex(ValueError, 'unknown fields'):
            self.c.receive(uri, cid)
        self.assertEqual(self.c.snapshot('counter')['root'], self.root)

    def test_remote_reprogram_uses_actual_lean_current_law_and_root(self):
        protocol = copy.deepcopy(self.root['protocol'])
        protocol['commands']['double'] = {
            'require': [], 'set': {'count': ['bend', ['lam', ['binary', 'multiply', ['bound', 0], ['nat', '2']]], [['state', 'count']]]},
            'result': ['literal', 'doubled'], 'outbox': []}
        def program(key, author=A, root=None, program=None):
            uri = f'at://{author}/{clerk.COLLECTION}/{key}'
            value = {'op': 'reprogram', 'object': 'counter', 'protocol': protocol if program is None else program,
                     'state': {'count': 7}, 'expected': self.root if root is None else root}
            self.pds.records[uri] = ('cid-' + key, {'$type': clerk.COLLECTION, 'profile': 'delvetalk-live-v1',
                                                'requestJson': clerk.world.wire_dumps(value)})
            return self.c.receive(uri, 'cid-' + key)
        denied = program('denied-program', author=B)
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        accepted = program('program')
        self.assertEqual(accepted['reply']['kind'], 'committed')
        changed = accepted['reply']['data']['root']
        self.assertEqual(changed['law'], self.root['law'])
        self.assertEqual(changed['state'], {'count': 7})
        self.assertEqual(changed['version'], 1)
        self.assertEqual(program('stale-program')['reply']['data'], 'stale read root')
        invalid = program('invalid-program', root=changed, program={})
        self.assertEqual(invalid['reply']['kind'], 'refused')
        self.assertEqual(self.c.snapshot('counter')['root'], changed)
        invoked = self.c.receive(*self.record('double', root=changed, op='invoke', command='double', input={}))
        self.assertEqual(invoked['reply']['data']['root']['state']['count'], 14)
        self.assertEqual(program('program'), accepted)

    def test_boolean_version_is_not_numeric_preimage(self):
        receipt = self.c.receive(*self.record())
        altered = copy.deepcopy(receipt['reply']['data']['root'])
        self.assertEqual(altered['version'], 1)
        altered['version'] = True
        refused = self.c.receive(*self.record('boolean', root=altered))
        self.assertEqual(refused['reply']['data'], 'stale read root')
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)

    def test_explicit_upgrade_preserves_world_history_and_exact_old_profile(self):
        uri, cid = self.record()
        receipt = self.c.receive(uri, cid)
        old = self.c.profile()
        before_world = self.c.database.read_bytes()
        before_journal = {p.name: p.read_bytes() for p in (self.state / 'requests').glob('*.json')}
        new_pins = {**old['profile']['pins'], 'lean-toolchain': 'a' * 64}
        with patch.object(clerk, 'pins', return_value=new_pins):
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                self.c.upgrade('0' * 64)
            result = self.c.upgrade(old['sha256'])
            self.assertEqual(result['status'], 'upgraded')
            self.assertEqual(result['upgrade']['from'], old['profile'])
            self.assertEqual(result['upgrade']['worldSha256'], clerk.hashlib.sha256(before_world).hexdigest())
            self.assertEqual(self.c.database.read_bytes(), before_world)
            self.assertEqual({p.name: p.read_bytes() for p in (self.state / 'requests').glob('*.json')}, before_journal)
            self.assertEqual(self.c.receive(uri, cid), receipt)
            self.assertEqual(self.c.receive(uri, cid)['profile'], old['profile'])
            self.assertEqual(self.c.upgrade(old['sha256'])['status'], 'already-upgraded')
            new_receipt = self.c.receive(*self.record('after-upgrade', root=receipt['reply']['data']['root']))
            self.assertEqual(new_receipt['reply']['kind'], 'committed')
            self.assertEqual(new_receipt['profile']['pins'], new_pins)
            # Retry remains historical even after new state changes.
            self.assertEqual(self.c.upgrade(old['sha256'])['status'], 'already-upgraded')
            self.assertEqual(len(self.c.config()['upgrades']), 1)
            with patch.object(clerk, 'pins', return_value={**new_pins, 'next': 'b' * 64}):
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    self.c.upgrade(old['sha256'])

    def test_upgrade_refuses_pending_and_preserves_config(self):
        uri, cid = self.record()
        save = clerk.save
        def fail_receipt(path, value):
            if 'receipt' in value:
                raise OSError('simulated journal loss')
            return save(path, value)
        with patch.object(clerk, 'save', fail_receipt):
            with self.assertRaises(OSError):
                self.c.receive(uri, cid)
        before = (self.state / 'clerk.json').read_bytes()
        old = self.c.profile()
        with patch.object(clerk, 'pins', return_value={'new': 'a' * 64}):
            with self.assertRaisesRegex(ValueError, 'pending request'):
                self.c.upgrade(old['sha256'])
        self.assertEqual((self.state / 'clerk.json').read_bytes(), before)
        # Finish under the old implementation, then the boundary is quiescent.
        self.c.receive(uri, cid)
        with patch.object(clerk, 'pins', return_value={'new': 'a' * 64}):
            self.assertEqual(self.c.upgrade(old['sha256'])['status'], 'upgraded')

    def test_upgrade_accepts_exact_legacy_pin_map_without_normalizing_it(self):
        config = self.c.config()
        config['profile']['pins'].pop('lean-toolchain')
        config['profile']['pins'].pop('spec/upstream/Theory/AxiomPin.lean')
        clerk.save(self.state / 'clerk.json', config)
        old = self.c.profile()
        result = self.c.upgrade(old['sha256'])
        self.assertEqual(result['upgrade']['from'], old['profile'])
        self.assertNotIn('lean-toolchain', result['upgrade']['from']['pins'])
        self.assertIn('lean-toolchain', result['upgrade']['to']['pins'])

    def test_pin_change_refuses_admission_but_keeps_historical_receipt(self):
        uri, cid = self.record()
        receipt = self.c.receive(uri, cid)
        with patch.object(clerk, 'pins', return_value={'modified': 'yes'}):
            self.assertEqual(self.c.receive(uri, cid), receipt)
            with self.assertRaisesRegex(ValueError, 'pins changed'):
                self.c.receive(*self.record('next', root=receipt['reply']['data']['root']))


if __name__ == '__main__':
    unittest.main()
