"""Source-configured review connects distinct maker and shared-target authorities."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import desk
import source_store


def package(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

writing = package('shared_writing_package', 'protocols/source-desk/package.py')
objects = package('shared_object_package', 'protocols/factories/package.py')


def scoped(invoke, reprogram=(), managers=()):
    return {'profile': 'delvetalk-scoped-law', 'invoke': invoke,
            'reprogram': list(reprogram), 'law': list(managers)}


class SharedProposal(unittest.TestCase):
    def setUp(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        self.client = desk.Desk(Path(home.name) / 'world.json', Path(home.name) / 'artifacts')
        self.factory = self.create('desks', writing.factory('compiler', ['maker'], reviewers=['steward', 'maker']),
            scoped({'make': ['maker']}, managers=['steward']))
        self.target = self.create('shared', objects.object(),
            scoped({'write': ['steward']}, reprogram=['steward'], managers=['steward']))
        offer = self.capture('desks', self.factory, 'make', {})
        receipt = self.client.exchange(desk.source_offers.request(offer, 'maker', 'make-proposal', {'name': 'variation'}))
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.candidate = self.client.inspect('desks/variation', principal='maker')
        self.assertEqual(self.candidate['law']['invoke']['submit'], ['maker'])
        self.assertEqual(self.candidate['law']['invoke']['adopt'], ['maker', 'steward'])
        self.assertEqual(set(self.candidate['law']['read']), {'maker', 'compiler', 'steward'})

    def create(self, name, program, law):
        result = self.client.exchange({'op': 'create', 'object': name, 'principal': 'steward',
            'intent': 'create-' + name, 'protocol': program, 'law': law})
        self.assertEqual(result['kind'], 'committed', result)
        return result['data']['root']

    def capture(self, name, root, invitation, others):
        view = desk.projection.project(root, name)
        return desk.source_offers.capture(view, {name: root, **others})[invitation]

    def ready(self):
        entries = []
        for name, path in [('Abi', 'world/lib/prelude/Abi.obend'),
                           ('List', 'world/lib/prelude/List.obend'), ('Encounter', 'world/lib/prelude/Encounter.obend'),
                           ('Object', 'protocols/factories/Object.obend')]:
            source = (ROOT / path).read_bytes()
            if name == 'Object':
                source = source.replace(b'512n', b'511n').replace(b'512 characters', b'511 characters')
            entries.append({'name': name, 'sourceRef': source_store.store_bytes(self.client.artifact_store, source)})
        proposal = source_store.prepare_module_proposal(self.client.artifact_store,
            source_store.seal_modules(entries), (ROOT / 'protocols/factories/object.examples').read_bytes(),
            syntax='objective-bend-object')
        submitted = self.client.submit_refs('desks/variation', 'maker', 'retained-source-proposal',
            self.candidate, proposal, self.target['state'], 'shared')
        self.assertEqual(submitted['kind'], 'committed', submitted)
        checked = self.client.check('desks/variation', 'compiler', 'checked-source-proposal', submitted['data']['root'])
        self.assertEqual(checked['kind'], 'committed', checked)
        ready = checked['data']['root']
        self.assertEqual(desk.candidate_state(ready)['status'], 'ready', desk.candidate_state(ready))
        self.assertEqual(desk.candidate_state(ready)['proposal']['manifest'], proposal['manifest'])
        return ready

    def test_steward_accepts_retained_source_while_maker_and_neighbor_cannot(self):
        ready = self.ready()
        offer = self.capture('desks/variation', ready, 'release', {'shared': self.target})
        for principal in ['neighbor', 'maker']:
            request = desk.source_offers.request(offer, principal, 'refuse-' + principal, {})
            refused = self.client.exchange(request)
            self.assertEqual(refused['kind'], 'refused', refused)
            self.assertEqual(self.client.inspect('desks/variation', principal='maker'), ready)
            self.assertEqual(self.client.inspect('shared'), self.target)
        request = desk.source_offers.request(offer, 'steward', 'accept-shared-variation', {})
        accepted = self.client.exchange(request)
        self.assertEqual(accepted['kind'], 'committed', accepted)
        self.assertEqual(self.client.exchange(request), accepted)
        installed = self.client.inspect('shared')
        self.assertEqual(installed['state'], self.target['state'])
        self.assertEqual(installed['law'], self.target['law'])
        self.assertEqual(installed['protocol'], desk.candidate_state(ready)['protocol'])
        rejected = self.client.exchange({'op': 'invoke', 'object': 'shared', 'principal': 'steward',
            'intent': 'authored-bound-now-applies', 'expected': installed, 'command': 'write', 'input': {'text': 'x' * 512}})
        self.assertEqual(rejected['kind'], 'refused', rejected)

    def test_private_factory_does_not_grant_a_shared_reviewer(self):
        root = self.create('private-desks', writing.factory('compiler', ['maker']),
            scoped({'make': ['maker']}, managers=['maker']))
        offer = self.capture('private-desks', root, 'make', {})
        request = desk.source_offers.request(offer, 'maker', 'make-private-proposal', {'name': 'private'})
        receipt = self.client.exchange(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        child = self.client.inspect('private-desks/private', principal='maker')
        self.assertEqual(child['law']['invoke']['submit'], ['maker'])
        self.assertEqual(child['law']['invoke']['adopt'], ['maker'])
        self.assertNotIn('steward', child['law']['invoke']['adopt'])
        self.assertEqual(set(child['law']['read']), {'maker', 'compiler'})

    def test_current_target_revocation_and_stale_capture_keep_proposal_intact(self):
        ready = self.ready()
        offer = self.capture('desks/variation', ready, 'release', {'shared': self.target})
        stale = desk.source_offers.request(offer, 'steward', 'captured-before-revocation', {})
        law = scoped({'write': ['steward']}, managers=['steward'])
        changed = self.client.exchange({'op': 'law', 'object': 'shared', 'principal': 'steward',
            'intent': 'revoke-shared-acceptance', 'expected': self.target, 'law': law})
        self.assertEqual(changed['kind'], 'committed', changed)
        revoked = changed['data']['root']
        self.assertEqual(self.client.exchange(stale)['kind'], 'refused')
        current = self.capture('desks/variation', ready, 'release', {'shared': revoked})
        request = desk.source_offers.request(current, 'steward', 'current-revoked-acceptance', {})
        refused = self.client.exchange(request)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(self.client.inspect('desks/variation', principal='maker'), ready)
        self.assertEqual(self.client.inspect('shared'), revoked)


if __name__ == '__main__':
    unittest.main()
