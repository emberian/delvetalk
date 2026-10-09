"""Proof-of-control identity joins shared source roles without management rights."""
import copy
import fcntl
import hashlib
import time
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
import world
import source_offers
import source_store
import desk
import runtime_profile
from scene import room


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


generate = module('membership_package', 'protocols/membership/generate.py')
service = module('membership_service', 'protocols/membership/service.py')
garden = module('membership_garden', 'conformance/test_garden_source.py')
identity_fixture = module('membership_identity', 'conformance/test_agent_identity.py')
factory = module('membership_factory', 'protocols/factories/package.py')
desks = module('membership_desks', 'protocols/source-desk/package.py')
DID = identity_fixture.B
SERVICE = 'verified-welcome-service'
METHODS = ['plant', 'rain', 'visit', 'page', 'cutting']
TARGETS = [{'object': 'garden', 'commands': METHODS}, {'object': 'objects', 'commands': ['make']},
           {'object': 'desks', 'commands': ['make']},
           {'object': 'workshop/sandbox', 'commands': ['write'], 'reprogram': True}]


class Membership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.welcome_protocol = generate.welcome(SERVICE, TARGETS)
        cls.garden_protocol = garden.protocol()
        cls.factory_protocol = factory.factory()
        cls.desks_protocol = desks.factory('compiler', ['moss'])
        cls.sandbox_protocol = factory.object()
        modules = factory.source_object.read_modules([
            ('Abi', ROOT / 'world/lib/prelude/Abi.obend'),
            ('List', ROOT / 'world/lib/prelude/List.obend'), ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
            ('Object', ROOT / 'protocols/factories/Object.obend')])
        modules[-1]['source'] = modules[-1]['source'].replace('512n', '256n').replace('512 characters', '256 characters')
        cls.sandbox_revised = factory.source_object.load(modules, syntax='objective-bend-spell@3')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.database = self.base / 'shared.json'
        self.serial = 0
        self.provider = identity_fixture.FakeProvider()
        self.identities = identity_fixture.identity.IdentityStore(self.base / 'identity',
            origin=identity_fixture.ORIGIN, provider=self.provider)
        self.create('welcome', self.welcome_protocol, {'profile': 'delvetalk-scoped-law-v1',
            'invoke': {'enroll': [SERVICE]}, 'reprogram': ['builder'], 'law': ['builder']})
        for target, protocol in [('garden', self.garden_protocol), ('objects', self.factory_protocol),
                                 ('desks', self.desks_protocol), ('workshop/sandbox', self.sandbox_protocol)]:
            methods = METHODS if target == 'garden' else ['write'] if target == 'workshop/sandbox' else ['make']
            self.create(target, protocol, {'profile': 'delvetalk-scoped-law-v4',
                'invoke': {m: ['moss'] for m in methods}, 'reprogram': ['builder'],
                'law': ['builder', SERVICE], 'amendment': generate.amendment(SERVICE, methods, reprogram=target == 'workshop/sandbox')})
        self.create('restricted', self.garden_protocol, {'profile': 'delvetalk-scoped-law-v1',
            'invoke': {'plant': ['private-owner']}, 'reprogram': ['private-owner'], 'law': ['private-owner']})

    def send(self, request, principal='builder', kind='committed'):
        self.serial += 1
        reply = world.exchange(self.database, {'principal': principal,
            'intent': 'membership-' + str(self.serial), **request}, profile='compiled')
        self.assertEqual(reply['kind'], kind, reply)
        return reply

    def root(self, object):
        return world.query(self.database, {'op': 'inspect', 'object': object, 'principal': 'builder'})

    def create(self, object, protocol, law):
        return self.send({'op': 'create', 'object': object, 'protocol': protocol, 'law': law})

    def verified(self):
        pending = self.identities.enroll({'did': DID})
        proof = self.provider.post(pending)
        verified = self.identities.verify(pending['token'], proof)
        authenticated = self.identities.authenticate(pending['token'])
        self.assertEqual(authenticated['did'], verified['did'])
        return authenticated, verified['proof']

    def enroll(self, verified, proof, intent='verified-onboarding'):
        return service.enroll(self.database, 'welcome', SERVICE, verified['did'], proof, intent,
                              custody=self.base / 'welcome-custody')

    def invitation(self):
        capture = world.capture_roots(self.database, ['welcome'], principal=SERVICE)
        view = room.inspect_object(capture['roots']['welcome']['root'], 'welcome',
            expected_runtime={'name': 'compiled', 'files': runtime_profile.file_hashes('compiled')})
        roots = source_offers.capture_observations(view, capture, database=self.database, principal=SERVICE)['roots']
        return source_offers.capture(view, {k: v['root'] for k, v in roots.items()},
            references={k: v['reference'] for k, v in roots.items()})['enroll']

    def test_verified_new_did_contributes_creates_and_cannot_manage_or_cross_private_boundary(self):
        person, proof = self.verified()
        self.send({'op': 'invoke', 'object': 'garden', 'expected': self.root('garden'),
            'command': 'plant', 'input': {'seed': 'A listening fern', 'colour': 'silver'}}, DID, 'refused')
        result = self.enroll(person, proof)
        self.assertEqual(result['status'], 'committed', result)
        self.assertEqual(self.enroll(person, proof), result, 'same trusted observation recovers the exact receipt')
        self.send({'op': 'invoke', 'object': 'garden', 'expected': self.root('garden'),
            'command': 'plant', 'input': {'seed': 'A listening fern', 'colour': 'silver'}}, DID)
        self.assertEqual(garden.plantings(self.root('garden'))[0]['planter'], DID)
        self.send({'op': 'invoke', 'object': 'garden', 'expected': self.root('garden'),
            'command': 'rain', 'input': {'id': 1, 'line': 'The room remembers you.'}}, 'moss')
        current = self.root('objects')
        self.send({'op': 'transaction', 'reads': {'objects': current, 'objects/fern': None},
            'calls': [{'object': 'objects', 'command': 'make', 'input': {'name': 'fern'}}]}, DID)
        self.assertEqual(self.root('objects/fern')['law']['invoke']['write'], [DID])
        self.assertEqual(self.root('objects/fern')['law']['read'], 'public')
        self.send({'op': 'invoke', 'object': 'objects/fern', 'expected': self.root('objects/fern'),
            'command': 'write', 'input': {'text': 'Someone else owns this'}}, 'moss', 'refused')
        self.send({'op': 'transaction', 'reads': {'desks': self.root('desks'), 'desks/fern-draft': None},
            'calls': [{'object': 'desks', 'command': 'make', 'input': {'name': 'fern-draft'}}]}, DID)
        self.assertIn(DID, self.root('desks/fern-draft')['law']['invoke']['submit'])
        own = self.root('objects/fern')
        self.send({'op': 'reprogram', 'object': 'objects/fern', 'expected': own,
            'protocol': self.sandbox_protocol, 'state': self.sandbox_protocol['initial']}, DID)
        sandbox = self.root('workshop/sandbox')
        revised = self.sandbox_revised
        # The participant changes actual source behavior, not only prose.
        self.send({'op': 'reprogram', 'object': 'workshop/sandbox', 'expected': sandbox,
            'protocol': revised, 'state': revised['initial']}, DID)
        self.send({'op': 'invoke', 'object': 'workshop/sandbox',
            'expected': self.root('workshop/sandbox'), 'command': 'write',
            'input': {'text': 'x' * 300}}, DID, 'refused')
        self.send({'op': 'reprogram', 'object': 'workshop/sandbox', 'expected': sandbox,
            'protocol': revised, 'state': revised['initial']}, DID, 'refused')
        sandbox = self.root('workshop/sandbox')
        self.send({'op': 'law', 'object': 'workshop/sandbox', 'expected': sandbox,
            'law': [DID]}, DID, 'refused')
        shared = self.root('garden')
        proposal = source_store.prepare_proposal(self.base / 'artifacts', 'objective-bend-spell@2',
            (ROOT / 'syntaxes/examples/lantern.obend').read_bytes(),
            (ROOT / 'syntaxes/examples/lantern.examples').read_bytes())
        self.send({'op': 'invoke', 'object': 'desks/fern-draft',
            'expected': self.root('desks/fern-draft'), 'command': 'submit',
            'input': {'proposal': proposal, 'migration': {'lit': False}, 'target': 'garden'}}, DID)
        self.assertEqual(self.root('garden'), shared, 'retaining a proposal cannot install it')
        self.send({'op': 'invoke', 'object': 'desks/fern-draft',
            'expected': self.root('desks/fern-draft'), 'command': 'adopt',
            'input': {'target': 'garden'}}, DID, 'refused')
        client = desk.Desk(self.database, self.base / 'artifacts', profile='compiled')
        checked = client.check('desks/fern-draft', 'compiler', 'check-shared-proposal',
            self.root('desks/fern-draft'))
        self.assertEqual(checked['kind'], 'committed', checked)
        candidate = self.root('desks/fern-draft')
        self.assertEqual(desk.candidate_state(candidate)['status'], 'ready')
        attempted = client.adopt('desks/fern-draft', 'garden', DID, 'release-shared-proposal',
            candidate, shared)
        self.assertEqual(attempted['kind'], 'refused', attempted)
        self.assertEqual(self.root('desks/fern-draft'), candidate, 'failed target admission rolls back release')
        self.assertEqual(self.root('garden'), shared)
        target = self.root('garden')
        self.send({'op': 'law', 'object': 'garden', 'expected': target, 'law': [DID]}, DID, 'refused')
        self.send({'op': 'reprogram', 'object': 'garden', 'expected': target,
            'protocol': target['protocol'], 'state': target['state']}, DID, 'refused')
        self.send({'op': 'invoke', 'object': 'restricted', 'expected': self.root('restricted'),
            'command': 'plant', 'input': {'seed': 'Not mine', 'colour': 'silver'}}, DID, 'refused')
        # Physical private realms are selected from the authenticated account, never an ID supplied here.
        import agent_heaps
        with agent_heaps.HeapManager(self.base / 'heaps', self.database) as heaps:
            with self.assertRaises(ValueError):
                heaps.turn(person, 'private:someone-else', {'op': 'inspect', 'object': 'notebook', 'intent': 'cross-private'})
        self.assertEqual(self.root('garden')['law']['reprogram'], ['builder'])
        self.assertEqual(self.root('garden')['law']['law'], ['builder', SERVICE])

    def test_explicit_sandbox_role_permits_source_revision_but_not_law_or_neighbor(self):
        sandbox = self.root('workshop/sandbox')
        role = copy.deepcopy(sandbox['law'])
        role['invoke']['write'].append(DID)
        role['reprogram'].append(DID)
        self.send({'op': 'law', 'object': 'workshop/sandbox', 'expected': sandbox, 'law': role}, SERVICE)
        self.send({'op': 'invoke', 'object': 'workshop/sandbox',
            'expected': self.root('workshop/sandbox'), 'command': 'write',
            'input': {'text': 'x' * 300}}, DID)
        before = self.root('workshop/sandbox')
        self.send({'op': 'reprogram', 'object': 'workshop/sandbox', 'expected': before,
            'protocol': self.sandbox_revised, 'state': self.sandbox_revised['initial']}, DID)
        self.send({'op': 'invoke', 'object': 'workshop/sandbox',
            'expected': self.root('workshop/sandbox'), 'command': 'write',
            'input': {'text': 'x' * 300}}, DID, 'refused')
        self.send({'op': 'reprogram', 'object': 'workshop/sandbox', 'expected': before,
            'protocol': self.sandbox_protocol, 'state': self.sandbox_protocol['initial']}, DID, 'refused')
        current = self.root('workshop/sandbox')
        escalation = copy.deepcopy(current['law']); escalation['law'].append(DID)
        self.send({'op': 'law', 'object': 'workshop/sandbox', 'expected': current,
            'law': escalation}, SERVICE, 'refused')
        self.send({'op': 'reprogram', 'object': 'garden', 'expected': self.root('garden'),
            'protocol': self.sandbox_revised, 'state': self.sandbox_revised['initial']}, DID, 'refused')
        revoked = copy.deepcopy(current['law']); revoked['reprogram'].remove(DID)
        self.send({'op': 'law', 'object': 'workshop/sandbox', 'expected': current, 'law': revoked})
        self.send({'op': 'reprogram', 'object': 'workshop/sandbox',
            'expected': self.root('workshop/sandbox'), 'protocol': self.sandbox_protocol,
            'state': self.sandbox_protocol['initial']}, DID, 'refused')

    def test_service_amendment_is_narrow_and_late_failure_rolls_back_membership(self):
        current = self.root('garden')
        attempts = []
        for key in ('reprogram', 'law'):
            value = copy.deepcopy(current['law']); value[key].append(DID); attempts.append(value)
        value = copy.deepcopy(current['law']); value['invoke']['secret'] = [DID]; attempts.append(value)
        value = copy.deepcopy(current['law']); value.pop('amendment'); value['profile'] = 'delvetalk-scoped-law-v1'; attempts.append(value)
        value = copy.deepcopy(current['law']); value['amendment']['config']['service'] = DID; attempts.append(value)
        value = copy.deepcopy(current['law']); value['invoke']['plant'] = [DID]; attempts.append(value)
        value = copy.deepcopy(current['law'])
        for names in value['invoke'].values(): names.extend([DID, identity_fixture.A])
        attempts.append(value)
        for value in attempts:
            self.send({'op': 'law', 'object': 'garden', 'expected': current, 'law': value}, SERVICE, 'refused')
            self.assertEqual(self.root('garden'), current)
        legacy = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'plant': ['moss']},
                  'reprogram': ['builder'], 'law': ['builder']}
        self.create('legacy', self.garden_protocol, legacy)
        guarded = {**legacy, 'profile': 'delvetalk-scoped-law-v4', 'law': ['builder', SERVICE],
                   'amendment': generate.amendment(SERVICE, ['plant'])}
        self.send({'op': 'law', 'object': 'legacy', 'expected': self.root('legacy'), 'law': guarded})
        offer = self.invitation()
        prepared = source_offers.prepare(offer, SERVICE, 'rolled-back-join',
            {'did': DID, 'proof': 'verified-proof-digest'}, database=self.database)
        self.assertEqual(prepared['kind'], 'ready', prepared)
        request = copy.deepcopy(prepared['request'])
        before = self.root('welcome')
        request['calls'].append({'op': 'invoke', 'object': 'welcome', 'command': 'missing', 'input': {}})
        self.send(request, SERVICE, 'refused')
        self.assertEqual(self.root('welcome'), before)
        self.assertEqual(self.root('garden'), current)
        forged = source_offers.prepare(offer, DID, 'fake-verified-join',
            {'did': DID, 'proof': 'arbitrary-claim'}, database=self.database)
        self.assertEqual(forged['kind'], 'refused')
        stale = source_offers.prepare(offer, SERVICE, 'stale-join',
            {'did': DID, 'proof': 'verified-proof-digest'}, database=self.database)
        self.send({'op': 'invoke', 'object': 'garden', 'expected': current, 'command': 'plant',
                   'input': {'seed': 'Earlier gardener', 'colour': 'amber'}}, 'moss')
        self.send(stale['request'], SERVICE, 'refused')
        self.assertEqual(self.root('welcome'), before)
        current = self.root('garden')
        revoked = copy.deepcopy(current['law']); revoked['law'].remove(SERVICE)
        self.send({'op': 'law', 'object': 'garden', 'expected': current, 'law': revoked})
        fresh = source_offers.prepare(self.invitation(), SERVICE, 'service-revoked',
            {'did': DID, 'proof': 'verified-proof-digest'}, database=self.database)
        self.assertEqual(fresh['kind'], 'ready', fresh)
        self.send(fresh['request'], SERVICE, 'refused')
        self.assertEqual(self.root('welcome'), before)

    def test_lost_reply_restarts_exact_and_reverification_does_not_undo_revocation(self):
        person, proof = self.verified()
        real_exchange = service.world.exchange
        def uncertain(*args, **kwargs):
            real_exchange(*args, **kwargs)
            raise TimeoutError('reply lost after native admission')
        with patch.object(service.world, 'exchange', side_effect=uncertain):
            with self.assertRaises(TimeoutError): self.enroll(person, proof)
        result = self.enroll(person, proof)
        self.assertEqual(result['status'], 'committed', result)
        current = self.root('garden')
        revoked = copy.deepcopy(current['law'])
        for members in revoked['invoke'].values(): members.remove(DID)
        self.send({'op': 'law', 'object': 'garden', 'expected': current, 'law': revoked})
        self.assertEqual(self.enroll(person, proof), result)
        self.assertEqual(self.enroll(person, proof, 'fresh-verification')['status'], 'refused')
        self.assertNotIn(DID, self.root('garden')['law']['invoke']['plant'])
        sandbox = self.root('workshop/sandbox')
        revoked = copy.deepcopy(sandbox['law']); revoked['reprogram'].remove(DID)
        self.send({'op': 'law', 'object': 'workshop/sandbox', 'expected': sandbox, 'law': revoked})
        self.send({'op': 'reprogram', 'object': 'workshop/sandbox',
            'expected': self.root('workshop/sandbox'), 'protocol': self.sandbox_revised,
            'state': self.sandbox_revised['initial']}, DID, 'refused')


class MembershipCustody(unittest.TestCase):
    def test_busy_record_lock_times_out_without_starting_native_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            key = hashlib.sha256(world.wire_dumps({'principal': SERVICE, 'intent': 'busy'}).encode()).hexdigest()
            with (base / (key + '.lock')).open('a') as held:
                fcntl.flock(held, fcntl.LOCK_EX)
                started = time.monotonic()
                with patch.object(service.world, 'capture_roots') as capture:
                    with self.assertRaises(TimeoutError):
                        service.enroll(base / 'shared.json', 'welcome', SERVICE, DID,
                            {'uri': 'at://proof', 'cid': 'cid', 'basis': 'verified'}, 'busy',
                            custody=base, timeout=0.05)
                    capture.assert_not_called()
                self.assertLess(time.monotonic() - started, 1)


if __name__ == '__main__': unittest.main()
