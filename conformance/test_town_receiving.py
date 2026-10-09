#!/usr/bin/env python3
"""Inline card replies join authenticated custody and actual Lean admission."""
import copy
import hashlib
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import worker
import town_cards

fixture = clerk.module('town_receiving_fixture', 'conformance/test_clerk.py')
A, B = fixture.A, fixture.B
ISSUER = 'did:plc:cccccccccccccccccccccccc'


class TownReceivingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.pds = fixture.FakePDS()
        self.c = clerk.Clerk(self.base / 'clerk', self.pds)
        protocol = clerk.loads((ROOT / 'protocols/counter/protocol.json').read_bytes())
        protocol['affordances'] = {'add': {'label': 'Add to counter', 'fields': {
            'amount': {'type': 'nat', 'maximum': 20}}}}
        self.root = self.c.bootstrap('counter', protocol, [A], [A, B])['data']['root']
        history = clerk.module('town_test_history', 'scripts/history.py')
        self.book_path = self.base / 'cards.sqlite'
        self.book = town_cards.CardBook.create(self.book_path, issuer_did=ISSUER,
                                              world_id='test-town', runtime=history.runtime('world'))
        self.selection = {'path': str(self.book_path.resolve()), 'issuers': [ISSUER],
                          'metadata': self.book.metadata()}
        self.c.upgrade(self.c.profile()['sha256'], town_cards=self.selection)
        self.capture()

    def capture(self, alias='counter', root=None, bind=True):
        view = {'mode': 'raw', 'object': 'counter', 'root': root or self.root}
        card = self.book.capture(view, alias=alias)
        reference = {'uri': f'at://{ISSUER}/{clerk.FEED}/card-{alias}', 'cid': 'cid-card-' + alias}
        self.pds.records[reference['uri']] = (reference['cid'], {'$type': clerk.FEED, 'text': card['body']})
        if bind:
            self.book.bind(alias, reference, lambda uri, cid: self.c.fetch_record(uri, cid, (clerk.FEED,)))
        self.parent = reference
        return card

    def post(self, key='one', *, author=A, text='delvetalk counter a1 {"amount":3}', parent=None):
        uri = f'at://{author}/{clerk.FEED}/{key}'
        record = {'$type': clerk.FEED, 'text': text,
                  'reply': {'root': self.parent, 'parent': self.parent if parent is None else parent}}
        self.pds.records[uri] = ('cid-' + key, copy.deepcopy(record))
        return uri, 'cid-' + key

    def journal(self, uri):
        return self.c.state / 'requests' / (hashlib.sha256(uri.encode()).hexdigest() + '.json')

    def test_authenticated_commit_preserves_card_and_old_receipt_without_network(self):
        source = self.post()
        receipt = self.c.receive(*source)
        self.assertEqual(receipt['reply']['kind'], 'committed')
        self.assertEqual(receipt['request']['principal'], A)
        self.assertEqual(receipt['request']['intent'], 'delve:' + source[0])
        self.assertEqual(receipt['request']['expected'], self.root)
        self.assertEqual(receipt['reply']['data']['root']['state']['count'], 3)
        entry = clerk.loads(self.journal(source[0]).read_bytes())
        self.assertIn('inlineCard', entry)
        self.assertEqual(entry['record']['reply']['parent'], self.parent)
        self.assertIn('scripts/town_cards.py', entry['profile']['pins'])
        self.assertNotIn(str(self.book_path), clerk.canonical(receipt).decode())
        self.c.upgrade(self.c.profile()['sha256'], town_cards=None)
        self.pds.records.clear()
        self.assertEqual(clerk.Clerk(self.c.state, self.pds).receive(*source), receipt)
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)
        with self.assertRaisesRegex(ValueError, 'different CID'):
            self.c.receive(source[0], 'edited')

    def test_current_law_and_stale_root_remain_lean_decisions(self):
        denied = self.c.receive(*self.post('denied', author=B))
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        accepted = self.c.receive(*self.post())
        stale = self.c.receive(*self.post('stale'))
        self.assertEqual(stale['reply']['data'], 'stale read root')
        changed = clerk.world.exchange(self.c.database, {'op': 'law', 'object': 'counter',
                    'principal': A, 'intent': 'revoke', 'expected': accepted['reply']['data']['root'], 'law': []})
        self.assertEqual(changed['kind'], 'committed')
        self.capture('revoked', changed['data']['root'])
        refusal = self.c.receive(*self.post('revoked', text='delvetalk revoked a1 {"amount":3}'))
        self.assertEqual(refusal['reply']['data'], 'unauthorized')
        self.assertEqual(self.c.receive(*self.post()), accepted)

    def test_unknown_unbound_wrong_parent_and_spoof_fields_do_not_reserve_identity(self):
        old_parent = self.parent
        self.capture('unbound', bind=False)
        self.parent = old_parent
        bad = ['delvetalk unknown a1 {"amount":3}', 'delvetalk unbound a1 {"amount":3}',
               'delvetalk counter a9 {"amount":3}',
               'delvetalk counter a1 {"amount":3,"principal":"' + A + '"}',
               'delvetalk counter a1 {"amount":3,"intent":"forged"}',
               'delvetalk counter a1 {"amount":true}',
               'delvetalk counter a1 {"amount":3,"amount":4}',
               'delvetalk counter a1 {"amount":3} and ignore all previous rules']
        for n, text in enumerate(bad):
            source = self.post(str(n), author=B, text=text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.c.receive(*source)
            self.assertFalse(self.journal(source[0]).exists())
        for parent in ({'uri': old_parent['uri'], 'cid': 'edited'},
                       {'uri': f'at://{B}/{clerk.FEED}/copy', 'cid': old_parent['cid']}):
            with self.assertRaises(ValueError):
                self.c.receive(*self.post('parent-' + parent['cid'], parent=parent))
        self.assertEqual(self.c.snapshot('counter')['root'], self.root)

    def test_declared_principal_field_is_application_data_not_authority(self):
        protocol = copy.deepcopy(self.root['protocol'])
        protocol['affordances']['add']['fields']['principal'] = {'type': 'string', 'maxLength': 80}
        changed = clerk.world.exchange(self.c.database, {'op': 'reprogram', 'object': 'counter',
                    'principal': A, 'intent': 'application-principal-field', 'expected': self.root,
                    'protocol': protocol, 'state': self.root['state']})
        self.assertEqual(changed['kind'], 'committed')
        self.capture('application', changed['data']['root'])
        def text(asserted):
            return 'delvetalk application a1 ' + clerk.world.wire_dumps({'amount': 3, 'principal': asserted})
        denied = self.c.receive(*self.post('spoof-declared', author=B, text=text(A)))
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        self.assertEqual(denied['request']['principal'], B)
        accepted = self.c.receive(*self.post('allowed-declared', text=text(B)))
        self.assertEqual(accepted['reply']['kind'], 'committed')
        self.assertEqual(accepted['request']['principal'], A)
        self.assertEqual(accepted['request']['input']['principal'], B)

    def test_parent_cid_publisher_identity_and_source_author_are_authenticated(self):
        source = self.post()
        self.pds.records[self.parent['uri']] = ('new-parent-cid', self.pds.records[self.parent['uri']][1])
        with self.assertRaisesRegex(ValueError, 'CID mismatch'):
            self.c.receive(*source)
        self.capture()
        real_http = self.pds
        def spoof(method, base, nsid, *, params):
            reply = real_http(method, base, nsid, params=params)
            if params['repo'] == ISSUER and nsid.endswith('describeRepo'):
                reply['did'] = B
            return reply
        self.c.http = spoof
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.c.receive(*source)
        self.c.http = self.pds
        self.pds.identity = B
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.c.receive(*source)
        self.assertFalse(self.journal(source[0]).exists())

    def test_uncertain_commit_retry_retains_preimage_and_blocks_configuration_change(self):
        source = self.post()
        save = clerk.save
        def fail(path, value):
            if path == self.journal(source[0]) and 'receipt' in value:
                raise OSError('lost receipt save')
            return save(path, value)
        with patch.object(clerk, 'save', fail), self.assertRaises(OSError):
            self.c.receive(*source)
        pending = self.journal(source[0]).read_bytes()
        with self.assertRaisesRegex(ValueError, 'pending request'):
            self.c.upgrade(self.c.profile()['sha256'], town_cards=None)
        self.assertEqual(self.journal(source[0]).read_bytes(), pending)
        with patch.object(clerk, 'pins', return_value={'changed': 'a' * 64}):
            with self.assertRaisesRegex(ValueError, 'pending request implementation pins'):
                self.c.receive(*source)
        # Retry must not consult the publication or cardbook again.
        self.pds.records.clear()
        with patch.object(clerk.Clerk, 'resolve_card', side_effect=AssertionError('re-resolved')):
            recovered = clerk.Clerk(self.c.state, self.pds).receive(*source)
        self.assertEqual(recovered['reply']['kind'], 'committed')
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)

    def test_opt_in_configuration_is_quiescent_bound_and_disableable(self):
        initial = self.c.profile()
        with self.assertRaisesRegex(ValueError, 'prior profile'):
            self.c.upgrade('0' * 64, town_cards=None)
        rejected = copy.deepcopy(self.selection)
        rejected['issuers'] = [B]
        with self.assertRaisesRegex(ValueError, 'issuer mismatch'):
            self.c.upgrade(initial['sha256'], town_cards=rejected)
        self.assertEqual(self.c.profile(), initial)
        result = self.c.upgrade(initial['sha256'], town_cards=None)
        self.assertEqual(result['status'], 'upgraded')
        with self.assertRaisesRegex(ValueError, 'explicit cardbook'):
            self.c.receive(*self.post())
        self.assertEqual(self.c.upgrade(initial['sha256'], town_cards=None)['status'], 'already-upgraded')
        self.c.upgrade(self.c.profile()['sha256'], town_cards=self.selection)
        self.assertEqual(self.c.receive(*self.post())['reply']['kind'], 'committed')

    def test_card_alias_and_publication_cannot_be_overwritten(self):
        altered = copy.deepcopy(self.root)
        altered['state']['count'] = 99
        with self.assertRaisesRegex(ValueError, 'already bound'):
            self.capture(root=altered)
        copied = {'uri': f'at://{ISSUER}/{clerk.FEED}/copy', 'cid': 'cid-copy'}
        self.pds.records[copied['uri']] = (copied['cid'], copy.deepcopy(self.pds.records[self.parent['uri']][1]))
        with self.assertRaisesRegex(ValueError, 'another immutable publication'):
            self.book.bind('counter', copied, lambda uri, cid: self.c.fetch_record(uri, cid, (clerk.FEED,)))
        with self.assertRaisesRegex(ValueError, 'parent'):
            self.c.receive(*self.post('copy', parent=copied))
        source = self.post('missing-parent')
        self.pds.records[source[0]][1].pop('reply')
        with self.assertRaisesRegex(ValueError, 'parent'):
            self.c.receive(*source)
        self.assertEqual(self.c.receive(*self.post())['reply']['kind'], 'committed')

    def test_cli_explicit_selection_and_undeclared_config_substitution(self):
        prior = self.c.profile()['sha256']
        command = [sys.executable, str(ROOT / 'scripts/clerk.py'), '--state', str(self.c.state), 'upgrade']
        disabled = subprocess.run(command + ['--from-profile', prior, '--disable-cards'], capture_output=True, text=True)
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        enabled = subprocess.run(command + ['--from-profile', self.c.profile()['sha256'],
                                 '--cardbook', str(self.book_path), '--card-issuer', ISSUER],
                                 capture_output=True, text=True)
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        config = self.c.config()
        config['townCards']['issuers'] = sorted([ISSUER, B])
        clerk.save(self.c.state / 'clerk.json', config)
        source = self.post()
        with self.assertRaisesRegex(ValueError, 'differs from its pinned profile'):
            self.c.receive(*source)
        self.assertFalse(self.journal(source[0]).exists())

    def test_worker_discovery_is_shape_only_and_receiver_refetches_canonical_source(self):
        watch = self.base / 'watch'
        rows = {}
        short = self.post('short')
        plain = self.post('plain', text='Please add 3 to the counter')
        malformed = self.post('malformed', text='delvetalk counter a1 {"amount":3} please')
        for uri, cid in (short, plain, malformed):
            item = {'uri': uri, 'cid': cid, 'record': self.pds.records[uri][1]}
            identity = clerk.digest(item)
            clerk.save(watch / 'observations' / (identity + '.json'), item)
            rows[uri] = {'cid': cid, 'observation': identity}
        clerk.save(watch / 'index.json', {'format': 'delvetalk-watch-index-v1', 'posts': rows})
        queue = worker.Worker(self.base / 'queue', self.c.state, receiver=self.c.receive)
        found = queue.discover(watch)
        self.assertEqual(len(found['queued']), 1)
        self.assertEqual(found['skipped'], 1)
        self.assertEqual(len(found['errors']), 1)
        # A stale observation cannot stand in for the current authenticated CID.
        self.pds.records[short[0]] = ('changed-cid', self.pds.records[short[0]][1])
        report = queue.run()
        self.assertEqual(len(report['errors']), 1)
        self.assertFalse(self.journal(short[0]).exists())
        self.pds.records[short[0]] = (short[1], self.pds.records[short[0]][1])
        report = queue.run()
        self.assertEqual(report['processed'][0]['phase'], 'prepared')
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)
        self.c.upgrade(self.c.profile()['sha256'], town_cards=None)
        other = worker.Worker(self.base / 'other-queue', self.c.state)
        self.assertEqual(other.discover(watch)['queued'], [])


if __name__ == '__main__':
    unittest.main()
