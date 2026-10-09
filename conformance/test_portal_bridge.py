"""Offline draft-to-repository round trips through mocked PDS and actual Lean."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import delve
import portal
import portal_bridge

OTHER = 'did:plc:' + 'a' * 24


class ReadOnlyPDS:
    def __init__(self):
        self.records = {}
        self.forged = False
        self.calls = []

    def __call__(self, method, base, nsid, *, params=None, **kwargs):
        assert method == 'GET' and base == clerk.PDS and not kwargs
        self.calls.append(nsid)
        if nsid.endswith('describeRepo'):
            author = params['repo']
            return {'did': author, 'didDoc': {'id': OTHER if self.forged else author,
                'service': [{'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer',
                             'serviceEndpoint': clerk.PDS}]}}
        assert nsid.endswith('getRecord')
        value = self.records[params['rkey']]
        return copy.deepcopy(value)


class PortalBridgeTest(unittest.TestCase):
    def setUp(self):
        if not (ROOT / '.lake/build/bin/delvetalk-world').is_file():
            self.fail('Build delvetalk-world before running receiving-path tests')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.pds = ReadOnlyPDS()
        self.receiver = clerk.Clerk(self.base / 'receiver', self.pds)
        protocol = clerk.loads((ROOT / 'protocols/counter/protocol.json').read_bytes())
        protocol['affordances'] = {'add': {'label': 'Add an amount',
            'fields': {'amount': {'type': 'nat', 'maximum': 100}}}}
        self.receiver.bootstrap('counter', protocol, [delve.DID], [delve.DID, OTHER])
        # The portal is an explicitly pinned read-only view of this receiving world.
        clerk.save(self.receiver.state / 'manifest.json',
                   {'runtime': portal.bootstrap.history.runtime('world'), 'cafe': 'counter'})
        self.app = portal.Portal(self.receiver.state)
        self.bridge = portal_bridge.Bridge(self.app)

    def draft(self, amount=3):
        card = self.app.object('counter')
        return self.app.prepare({'card': card['card'], 'action': card['actions'][0]['id'],
                                 'fields': {'amount': amount}})['draft']

    def source(self, draft, key='request-1', author=delve.DID):
        prepared = self.bridge.prepare(draft)
        uri, cid = 'at://' + author + '/' + clerk.COLLECTION + '/' + key, 'cid-' + key
        self.pds.records[key] = {'uri': uri, 'cid': cid, 'value': prepared['record']}
        self.bridge.bind(draft, uri, cid)
        return uri, cid

    def journal(self, uri):
        return self.receiver.state / 'requests' / (hashlib.sha256(uri.encode()).hexdigest() + '.json')

    def test_card_draft_repository_clerk_receipt_round_trip_and_restart(self):
        draft = self.draft()
        before = self.receiver.database.read_bytes()
        prepared = self.bridge.prepare(draft)
        self.assertEqual(prepared, portal_bridge.Bridge(portal.Portal(self.receiver.state)).prepare(draft))
        self.assertEqual(self.receiver.database.read_bytes(), before)
        self.assertEqual(self.pds.calls, [])
        self.assertNotIn('principal', prepared['wire'])
        self.assertNotIn('intent', prepared['wire'])
        self.assertEqual(prepared['record']['requestJson'], prepared['requestJson'])
        source = self.source(draft)
        self.assertEqual(self.bridge.reconcile(draft, self.receiver)['kind'], 'uncertain')
        receipt = self.receiver.receive(*source)
        self.assertEqual(receipt['request']['principal'], delve.DID)
        self.assertEqual(receipt['request']['intent'], 'delve:' + source[0])
        outcome = self.bridge.reconcile(draft, self.receiver)
        self.assertEqual(outcome['kind'], 'committed')
        self.assertEqual(outcome['reply']['data']['root']['state']['count'], 3)
        self.assertEqual(outcome['receipt'], receipt)
        self.pds.records.clear()
        with patch.object(clerk, 'pins', side_effect=AssertionError('historical recovery must not repin')), \
                patch.object(portal_bridge.affordances, 'request', side_effect=AssertionError('must not reinterpret')):
            recovered = portal_bridge.Bridge(portal.Portal(self.receiver.state)).reconcile(draft, self.receiver)
        self.assertEqual(outcome, recovered)

    def test_stale_draft_is_terminal_refusal_without_rebase(self):
        stale = self.draft(9)
        fresh = self.draft(1)
        stale_wire = self.bridge.prepare(stale)['wire']
        self.receiver.receive(*self.source(fresh, 'first'))
        receipt = self.receiver.receive(*self.source(stale, 'stale'))
        self.assertEqual(receipt['reply']['data'], 'stale read root')
        outcome = self.bridge.reconcile(stale, self.receiver)
        self.assertEqual(outcome['kind'], 'refused')
        self.assertEqual(self.bridge.prepare(stale)['wire'], stale_wire)
        self.assertEqual(self.app.snapshot()['objects']['counter']['state']['count'], 1)

    def test_forged_repository_identity_and_wire_identity_refuse(self):
        draft = self.draft()
        source = self.source(draft)
        self.pds.forged = True
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.receiver.receive(*source)
        self.assertEqual(self.bridge.reconcile(draft, self.receiver)['kind'], 'uncertain')
        self.pds.forged = False
        prepared = self.pds.records['request-1']['value']
        wire = clerk.loads(prepared['requestJson'])
        wire['principal'] = delve.DID
        prepared['requestJson'] = clerk.canonical(wire).decode()
        with self.assertRaisesRegex(ValueError, 'unknown fields'):
            self.receiver.receive(*source)
        self.assertFalse(self.journal(source[0]).exists())

    def test_enrollment_does_not_grant_authority(self):
        draft = self.draft()
        receipt = self.receiver.receive(*self.source(draft, author=OTHER))
        self.assertEqual(receipt['request']['principal'], OTHER)
        self.assertEqual(self.bridge.reconcile(draft, self.receiver)['reply']['data'], 'unauthorized')

    def test_identity_rebinding_receipt_substitution_and_changed_draft_refuse(self):
        draft = self.draft()
        uri, cid = self.source(draft)
        with self.assertRaisesRegex(ValueError, 'another URI or CID'):
            self.bridge.bind(draft, uri, 'replacement')
        self.receiver.receive(uri, cid)
        path = self.journal(uri)
        entry = clerk.loads(path.read_bytes())
        entry['receipt']['request']['principal'] = OTHER
        entry['receipt']['id'] = clerk.digest({k: v for k, v in entry['receipt'].items() if k != 'id'})
        clerk.save(path, entry)
        with self.assertRaisesRegex(ValueError, 'receipt differs'):
            self.bridge.reconcile(draft, self.receiver)
        path = self.app.state / 'drafts' / (draft + '.json')
        changed = portal.loads(path.read_bytes())
        changed['wire']['input']['amount'] = 99
        clerk.save(path, changed)
        with self.assertRaisesRegex(ValueError, 'wire differs'):
            self.bridge.prepare(draft)

    def test_lost_clerk_reply_recovers_retained_world_admission_without_network(self):
        draft = self.draft()
        source = self.source(draft)
        original = clerk.save
        def lose_receipt(path, value):
            if 'receipt' in value and 'source' in value:
                raise OSError('simulated interrupted clerk receipt write')
            original(path, value)
        with patch.object(clerk, 'save', side_effect=lose_receipt):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                self.receiver.receive(*source)
        before = self.receiver.database.read_bytes()
        calls = list(self.pds.calls)
        outcome = self.bridge.reconcile(draft, self.receiver)
        self.assertEqual(outcome['kind'], 'committed')
        self.assertEqual(self.receiver.database.read_bytes(), before)
        self.assertEqual(self.pds.calls, calls)
        self.assertNotIn('receipt', clerk.loads(self.journal(source[0]).read_bytes()))
        self.assertEqual(self.receiver.receive(*source), outcome['receipt'])


if __name__ == '__main__':
    unittest.main()
