#!/usr/bin/env python3
"""The service accepts source-offered forge work and preserves exact builds."""
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
    def test_compiler_runtime_pins_include_source_custody_dependencies(self):
        pins = desk.execution_profile('compiled')['files']
        for path in desk.SOURCE_CANDIDATE_FILES:
            self.assertEqual(pins[path], service.history.file_hash(ROOT / path))

    def test_service_compiles_forge_and_continuation_restores_exact_builds(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            directory = base / 'world'
            modules = desk.source_object.read_closure([('Candidate', ROOT / 'protocols/editor/Candidate.obend')])
            modules[-1]['source'] = modules[-1]['source'].replace(
                'initial({editorMode: true})', 'initial({editorMode: false})')
            altered = copy.deepcopy(modules)
            altered[-1]['source'] = altered[-1]['source'].replace('title: "Candidate"', 'title: "Authored forge candidate"')
            self.assertNotEqual(altered, modules)
            law = forge.scoped({'submit': [AUTHOR], 'requestCheck': [AUTHOR], 'compiled': ['compiler'],
                'failed': ['compiler'], 'adopt': [AUTHOR]})
            seeds = [{'id': 'target', 'syntax': forge.SPELL_SYNTAX,
                      'source': (ROOT / 'protocols/town-forge/Chalk.obend').read_bytes(),
                      'law': forge.scoped({'knock': [AUTHOR]}, reprogram=[AUTHOR])}]
            seeds.extend({'id': name, 'syntax': 'objective-bend-object',
                          'modules': body, 'law': law}
                         for name, body in [('ready', modules), ('failed', modules), ('lookalike', altered)])
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
                    'input': {'target': 'target', 'proposal': {'syntax': forge.SPELL_SYNTAX, 'source': source, 'scenarios': scenario_texts[name]}, 'migration': {'model': desk.source_object.compact_state(forge.door(), desk.source_object.data({}), entry='describe', path=[{'field': 'initial'}])}}})
                self.assertEqual(result['kind'], 'committed', result)
                requested = client.exchange({'op': 'invoke', 'object': name, 'principal': AUTHOR,
                    'intent': 'request-' + name, 'expected': result['data']['root'], 'command': 'requestCheck', 'input': {}})
                self.assertEqual(requested['kind'], 'committed', requested)
                pending[name] = requested['data']['root']

            result = app.tick(deadline_seconds=120)
            self.assertEqual(result['errors'], [], result)
            self.assertEqual(result['status'], 'prepared-offline', result)
            discovered = result['phases']['enqueueCompilers']
            self.assertEqual(len(discovered['jobs']), 3)
            self.assertEqual(discovered['candidateCount'], 4)
            self.assertEqual(discovered['examined'], 4)
            self.assertEqual(desk.candidate_state(client.inspect('ready'))['status'], 'ready')
            self.assertEqual(desk.candidate_state(client.inspect('failed'))['status'], 'failed')
            self.assertEqual(desk.candidate_state(client.inspect('lookalike'))['status'], 'ready')
            self.assertEqual(client.inspect('target'), original)
            queue = app.compiler(app.config(), 2048)
            jobs = [desk.loads(path.read_bytes()) for path in (queue.state / 'jobs').glob('*.json')]
            self.assertEqual({job['inputs']['object'] for job in jobs}, {'ready', 'failed', 'lookalike'})
            for job in jobs:
                for path in desk.SOURCE_CANDIDATE_FILES:
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
            for name in ('ready', 'failed', 'lookalike'):
                identity = desk.candidate_state(client.inspect(name))['artifact']
                self.assertIn(identity, evidence['builds'])
                original_path = directory / 'artifacts/builds' / (identity + '.json')
                restored_path = restored / 'artifacts/builds' / (identity + '.json')
                self.assertEqual(restored_path.read_bytes(), original_path.read_bytes())
                build = desk.load_artifact(restored / 'artifacts', identity)
                self.assertEqual(build['candidateRootSha256'], desk.digest(pending[name]))
                self.assertEqual(build['sourceMaterial'], {'source': source, 'scenarios': scenario_texts[name]})
                self.assertEqual(build['report']['passed'], name != 'failed')
                for sha in service.history.declared_files(build).values():
                    self.assertEqual(service.history.read_blob(restored / 'artifacts/pins', sha).read_bytes(),
                                     service.history.read_blob(directory / 'artifacts/pins', sha).read_bytes())
            # Restart reuses the exact prepared continuation; no new compiler job/admission.
            before = client.database.read_bytes()
            restarted = service.Service(app.state).tick(deadline_seconds=120)
            self.assertEqual(restarted['errors'], [], restarted)
            self.assertEqual(restarted['continuation'], continuation)
            self.assertEqual(client.database.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
