#!/usr/bin/env python3
"""The operator service recognizes exact forge desks and preserves their builds."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import service
import workspace

spec = importlib.util.spec_from_file_location('forge_custody_package', ROOT / 'protocols/town-forge/generate.py')
forge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forge)
desk = service.desk
AUTHOR = service.clerk.delve.DID


class ForgeCustodyTests(unittest.TestCase):
    def test_catalog_is_exact_and_all_protocol_bodies_are_pinned(self):
        expected = ('protocols/source-desk/protocol.json', 'protocols/town-forge/source-desk.json',
                    'protocols/stateful-workshop/source-desk.json', 'protocols/editor/candidate.json',
                    'protocols/spween-handler-workshop/source-desk.json')
        self.assertEqual(desk.SOURCE_DESK_PROTOCOL_PATHS, expected)
        pins = desk.execution_profile('compiled')['files']
        for path in expected:
            protocol = desk.loads((ROOT / path).read_bytes())
            self.assertTrue(desk.is_source_desk_protocol(protocol))
            self.assertEqual(pins[path], service.history.file_hash(ROOT / path))
            spoof = copy.deepcopy(protocol)
            spoof['description'] = 'The same name and commands do not confer compiler eligibility.'
            self.assertFalse(desk.is_source_desk_protocol(spoof))
        self.assertFalse(desk.is_source_desk_protocol({'name': 'source-desk-v1'}))
        self.assertFalse(desk.is_source_desk_protocol(None))

    def test_service_compiles_forge_and_continuation_restores_exact_builds(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            directory = base / 'world'
            protocol = forge.source_desk()
            spoof = copy.deepcopy(protocol)
            spoof['description'] = 'Changed body, same name; not a catalogued desk.'
            law = forge.scoped({'submit': [AUTHOR], 'compiled': ['compiler'],
                'failed': ['compiler'], 'adopt': [AUTHOR]})
            seeds = [{'id': 'target', 'syntax': 'protocol-json@1',
                      'source': desk.canonical(forge.door(0)),
                      'law': forge.scoped({'knock': [AUTHOR]}, reprogram=[AUTHOR])}]
            seeds.extend({'id': name, 'syntax': 'protocol-json@1',
                          'source': desk.canonical(body), 'law': law}
                         for name, body in [('ready', protocol), ('failed', protocol), ('lookalike', spoof)])
            seed = workspace.initialize(directory, seeds, entry_objects=['target'],
                                        principal='operator', profile='compiled')
            client = desk.Desk(directory / 'world.json', directory / 'artifacts', profile='compiled')
            original = client.inspect('target')
            clerk = service.clerk.Clerk(base / 'clerk')
            snapshot = desk.loads(client.database.read_bytes())
            clerk.attach(directory, snapshot['objects'], [AUTHOR], expected_genesis=seed['genesis'],
                         expected_seed_head=seed['head'], runtime_profile='compiled')
            app = service.Service(base / 'service')
            app.initialize(directory, clerk.state, 'compiler', public_genesis=seed['genesis'])
            source = forge.spell_source(1)
            pending = {}
            scenario_texts = {}
            for name, fixtures in [('ready', forge.example_source(1)), ('failed', forge.challenge_source()),
                                   ('lookalike', forge.example_source(1))]:
                scenario_texts[name] = fixtures
                result = client.exchange({'op': 'invoke', 'object': name, 'principal': AUTHOR,
                    'intent': 'submit-' + name, 'expected': client.inspect(name), 'command': 'submit',
                    'input': {'target': 'target', 'source': source, 'scenarios': scenario_texts[name]}})
                self.assertEqual(result['kind'], 'committed', result)
                pending[name] = result['data']['root']

            result = app.tick(deadline_seconds=60)
            self.assertEqual(result['errors'], [], result)
            self.assertEqual(result['status'], 'prepared-offline', result)
            discovered = result['phases']['enqueueCompilers']
            self.assertEqual(discovered['pendingCandidates'], 2)
            self.assertEqual(discovered['examined'], 2)
            self.assertEqual(client.inspect('ready')['state']['status'], 'ready')
            self.assertEqual(client.inspect('failed')['state']['status'], 'failed')
            self.assertEqual(client.inspect('lookalike'), pending['lookalike'])
            self.assertEqual(client.inspect('target'), original)
            queue = app.compiler(app.config(), 2048)
            jobs = [desk.loads(path.read_bytes()) for path in (queue.state / 'jobs').glob('*.json')]
            self.assertEqual({job['inputs']['object'] for job in jobs}, {'ready', 'failed'})
            for job in jobs:
                for path in desk.SOURCE_DESK_PROTOCOL_PATHS:
                    self.assertEqual(job['runtime']['files'][path], service.history.file_hash(ROOT / path))
                    self.assertEqual(app.config()['epoch']['files'][path], service.history.file_hash(ROOT / path))

            continuation = result['continuation']
            destination = Path(continuation['destination'])
            checked = service.continuation.verify(destination, expected_genesis=seed['genesis'],
                expected_head=continuation['head'], base_head=seed['head'])
            self.assertEqual(checked['status'], 'verified-offline')
            restored = base / 'restored'
            evidence = service.bootstrap.restore_bootstrap(destination / 'history', restored,
                expected_genesis=seed['genesis'], expected_head=continuation['head'], base_head=seed['head'])
            self.assertEqual(desk.loads((restored / 'world.json').read_bytes()),
                             desk.loads(client.database.read_bytes()))
            for name in ('ready', 'failed'):
                identity = client.inspect(name)['state']['artifact']
                self.assertIn(identity, evidence['builds'])
                original_path = directory / 'artifacts/builds' / (identity + '.json')
                restored_path = restored / 'artifacts/builds' / (identity + '.json')
                self.assertEqual(restored_path.read_bytes(), original_path.read_bytes())
                build = desk.load_artifact(restored / 'artifacts', identity)
                self.assertEqual(build['candidateRootSha256'], desk.digest(pending[name]))
                self.assertEqual(build['sourceMaterial'], {'source': source, 'scenarios': scenario_texts[name]})
                self.assertEqual(build['report']['passed'], name == 'ready')
                for sha in service.history.declared_files(build).values():
                    self.assertEqual(service.history.read_blob(restored / 'artifacts/pins', sha).read_bytes(),
                                     service.history.read_blob(directory / 'artifacts/pins', sha).read_bytes())
            # Restart reuses the exact prepared continuation; no new compiler job/admission.
            before = client.database.read_bytes()
            restarted = service.Service(app.state).tick(deadline_seconds=60)
            self.assertEqual(restarted['errors'], [], restarted)
            self.assertEqual(restarted['continuation'], continuation)
            self.assertEqual(client.database.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
