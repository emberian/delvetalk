"""History integrity/reconstruction uses the current source receiver."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import history as h
import translate
from test_authority import law, source_object


class History(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.database = cls.directory / 'world.json'
        cls.bundle = cls.directory / 'bundle'
        source = (ROOT / 'examples/current-objects/Counter.obend').read_bytes()
        artifact = translate.translate('objective-bend-object', source)
        protocol = artifact['lowered']
        cls.source = source
        def admit(request):
            return h.world.exchange(cls.database, request, profile='compiled')
        roots = {}
        for name in ('a', 'b'):
            roots[name] = admit({'op': 'create', 'object': name, 'principal': 'A',
                'intent': 'create-' + name, 'protocol': protocol, 'law': law(invoke={'add': ['A']}, reprogram=['A'], law=['A'])})['data']['root']
        transaction = {'op': 'transaction', 'principal': 'A', 'intent': 'both', 'reads': roots,
                       'calls': [{'object': 'a', 'command': 'add', 'input': {'amount': 3}},
                                 {'object': 'b', 'command': 'add', 'input': {'amount': 4}}]}
        changed = admit(transaction)
        refused = admit({**transaction, 'intent': 'stale'})
        assert refused['kind'] == 'refused'
        request = {'op': 'reprogram', 'object': 'a', 'principal': 'A', 'intent': 'program',
                   'expected': changed['data']['roots']['a'], 'protocol': protocol, 'state': {'model': source_object.data({'count': 9})}}
        admit(request)
        cls.journals = cls.directory / 'journals'
        cls.journals.mkdir()
        (cls.journals / 'program.json').write_bytes(h.canonical({
            'request': request, 'artifact': artifact,
            'inputs': {'syntax': 'objective-bend-object', 'source': source.decode(),
                       'stateSource': {'encoding': 'utf-8', 'text': h.canonical({'model': source_object.data({'count': 9})}).decode()}}}))
        cls.trusted = h.export_history(cls.database, cls.bundle, journals=cls.journals)
        cls.manifest = h.loads((cls.bundle / 'manifest.json').read_bytes())

    def setUp(self):
        self.temp_case = tempfile.TemporaryDirectory(dir=self.directory)
        self.addCleanup(self.temp_case.cleanup)
        self.case = Path(self.temp_case.name)

    def check(self, bundle=None, **kwargs):
        return h.verify_history(bundle or self.bundle, expected_genesis=self.trusted['genesis'],
                                expected_head=self.trusted['head'], **kwargs)

    def altered(self, mutate):
        bundle = self.case / 'bundle'
        shutil.copytree(self.bundle, bundle, copy_function=__import__('os').link)
        manifest = copy.deepcopy(self.manifest)
        mutate(manifest)
        (bundle / 'manifest.json').unlink()
        (bundle / 'manifest.json').write_bytes(h.canonical(manifest))
        return bundle

    def test_complete_reconstruction_and_multiobject_commit(self):
        output = self.case / 'restored.json'
        report = self.check(output=output)
        self.assertEqual(report['entries'], 5)
        self.assertEqual(h.canonical(h.loads(output.read_bytes())), h.canonical(h.loads(self.database.read_bytes())))
        commit = self.manifest['entries'][2]
        self.assertEqual(set(commit['reply']['data']['roots']), {'a', 'b'})
        self.assertEqual(commit['reply']['data']['roots']['a']['state'], {'model': source_object.data({'count': 3})})
        self.assertEqual(commit['reply']['data']['roots']['b']['state'], {'model': source_object.data({'count': 4})})
        self.assertTrue(self.manifest['entries'][-1]['artifacts'])
        before = output.read_bytes()
        with self.assertRaises(FileExistsError):
            self.check(output=output)
        self.assertEqual(output.read_bytes(), before)

    def test_reordering_gap_and_truncation_fail(self):
        mutations = [lambda m: m['entries'].reverse(),
                     lambda m: m['entries'].pop(1),
                     lambda m: m['entries'].pop()]
        for number, mutate in enumerate(mutations):
            with self.subTest(number=number):
                bundle = self.case / 'altered-' / str(number)
                bundle.mkdir(parents=True)
                (bundle / 'blobs').symlink_to(self.bundle / 'blobs', target_is_directory=True)
                manifest = copy.deepcopy(self.manifest)
                mutate(manifest)
                (bundle / 'manifest.json').write_bytes(h.canonical(manifest))
                with self.assertRaisesRegex(ValueError, 'order|gap|truncated|head'):
                    self.check(bundle)

    def test_receipt_tampering_and_rechaining_cannot_fool_lean(self):
        def tamper(manifest):
            manifest['entries'][2]['reply']['data']['roots']['a']['state'] = {'model': source_object.data({'count': 999})}
        with self.assertRaisesRegex(ValueError, 'commit digest'):
            self.check(self.altered(tamper))
        manifest = copy.deepcopy(self.manifest)
        tamper(manifest)
        previous = manifest['genesis']['id']
        for entry in manifest['entries']:
            entry['previous'] = previous
            entry['id'] = h.digest({key: value for key, value in entry.items() if key != 'id'})
            previous = entry['id']
        manifest['head'] = previous
        with self.assertRaisesRegex(ValueError, 'Lean receipt mismatch'):
            h.replay(manifest, self.bundle, self.case / 'untrusted.json',
                     expected_genesis=self.trusted['genesis'], expected_head=previous)

    def test_trusted_head_and_runtime_are_required(self):
        with self.assertRaisesRegex(ValueError, 'trusted head'):
            h.verify_history(self.bundle, expected_genesis=self.trusted['genesis'], expected_head='0' * 64)
        current = h.runtime('compiled')
        current['platform']['machine'] = 'different'
        with patch.object(h, 'runtime', return_value=current):
            with self.assertRaisesRegex(ValueError, 'runtime/source/platform'):
                self.check()

    def test_runtime_closure_uses_shared_complete_import_pins(self):
        paths = self.manifest['genesis']['profile']['files']
        self.assertIn('scripts/runtime_profile.py', paths)
        self.assertIn('profiles/TransactionsCore.lean', paths)
        self.assertIn('profiles/WorldCore.lean', paths)
        self.assertIn('profiles/Compiled.lean', paths)
        self.assertIn('spec/Delvetalk/Package.lean', paths)
        self.assertIn('spec/bend/Compiler/ObjectiveBendFrontEnd.lean', paths)

    def foreign_manifest(self, bundle):
        manifest = copy.deepcopy(self.manifest)
        runtime = manifest['genesis']['profile']
        runtime['platform'] = {'system': 'other-platform', 'machine': 'other-architecture'}
        binary = '.lake/build/bin/' + h.world.PROFILES[runtime['name']][0]
        # Deliberately not executable: the verifier must never run a bundle's binary.
        runtime['files'][binary] = h.store_bytes(bundle, b'foreign runtime artifact, not executable')
        return self.rechain(manifest)

    @staticmethod
    def rechain(manifest):
        genesis = manifest['genesis']
        genesis['id'] = h.digest({k: v for k, v in genesis.items() if k != 'id'})
        previous = genesis['id']
        for entry in manifest['entries']:
            entry['previous'] = previous
            entry['id'] = h.digest({k: v for k, v in entry.items() if k != 'id'})
            previous = entry['id']
        manifest['head'] = previous
        return manifest

    def test_same_sources_is_explicit_and_replays_with_local_runtime(self):
        bundle = self.altered(lambda m: None)
        manifest = self.foreign_manifest(bundle)
        (bundle / 'manifest.json').write_bytes(h.canonical(manifest))
        args = {'expected_genesis': manifest['genesis']['id'], 'expected_head': manifest['head']}
        with self.assertRaisesRegex(ValueError, 'runtime/source/platform'):
            h.verify_history(bundle, **args)
        result = h.verify_history(bundle, runtime_policy='same-sources', **args)
        self.assertEqual(result['runtimePolicy'], 'same-sources')
        self.assertEqual(result['proofScope'], 'source-matched-local-replay')
        self.assertEqual(result['localRuntime'], h.runtime('compiled'))
        self.assertNotEqual(result['localRuntimeSha256'], result['originRuntimeSha256'])
        # Even a coherently rehashed claimed receipt must reproduce in Lean.
        manifest['entries'][2]['reply']['data']['roots']['a']['state'] = {'model': source_object.data({'count': 999})}
        self.rechain(manifest)
        (bundle / 'manifest.json').write_bytes(h.canonical(manifest))
        with self.assertRaisesRegex(ValueError, 'Lean receipt mismatch'):
            h.verify_history(bundle, runtime_policy='same-sources',
                expected_genesis=manifest['genesis']['id'], expected_head=manifest['head'])

    def test_same_sources_still_requires_every_source_and_origin_binary_blob(self):
        bundle = self.altered(lambda m: None)
        manifest = self.foreign_manifest(bundle)
        binary = '.lake/build/bin/' + h.world.PROFILES['compiled'][0]
        origin_sha = manifest['genesis']['profile']['files'][binary]
        (bundle / 'manifest.json').write_bytes(h.canonical(manifest))
        (bundle / 'blobs' / origin_sha).write_bytes(b'changed origin bytes')
        with self.assertRaisesRegex(ValueError, 'blob digest mismatch'):
            h.verify_history(bundle, runtime_policy='same-sources',
                expected_genesis=manifest['genesis']['id'], expected_head=manifest['head'])
        manifest['genesis']['profile']['files']['profiles/WorldCore.lean'] = '0' * 64
        self.rechain(manifest)
        (bundle / 'manifest.json').write_bytes(h.canonical(manifest))
        with self.assertRaisesRegex(ValueError, 'sources/toolchain/closure'):
            h.verify_history(bundle, runtime_policy='same-sources',
                expected_genesis=manifest['genesis']['id'], expected_head=manifest['head'])


    def test_previously_known_head_must_be_a_history_prefix(self):
        self.check(base_head=self.manifest['entries'][1]['id'])
        with self.assertRaisesRegex(ValueError, 'known base head'):
            self.check(base_head='0' * 64)

    def test_export_preserves_anchored_prefix_despite_new_matching_artifacts(self):
        database = self.case / 'extended-world.json'
        shutil.copyfile(self.database, database)
        old = h.loads(database.read_bytes())
        result = h.world.exchange(database, {'op': 'invoke', 'object': 'b', 'principal': 'A',
            'intent': 'after-restoration', 'expected': old['objects']['b'], 'command': 'add',
            'input': {'amount': 2}}, profile='compiled')
        self.assertEqual(result['kind'], 'committed')
        # It lowers to the same protocol, but selects different source bytes.
        alternative = self.case / 'alternative.json'
        alternative.write_bytes(h.canonical(translate.translate('objective-bend-object', self.source + b'\n')))
        previous_request = self.manifest['entries'][-1]['request']
        bundle = self.case / 'extension'
        trusted = h.export_history(database, bundle,
            attachments={h.digest(previous_request): [alternative, self.case / 'now-absent-old-source']},
            prefix_bundle=self.bundle, expected_prefix_genesis=self.trusted['genesis'],
            expected_prefix_head=self.trusted['head'])
        manifest = h.loads((bundle / 'manifest.json').read_bytes())
        self.assertEqual(h.canonical(manifest['entries'][:5]), h.canonical(self.manifest['entries']))
        self.assertEqual(manifest['entries'][5]['previous'], self.trusted['head'])
        h.verify_history(bundle, expected_genesis=trusted['genesis'], expected_head=trusted['head'],
                         base_head=self.trusted['head'])

    def test_prefix_requires_anchors_matching_snapshot_and_provenance_policy(self):
        with self.assertRaisesRegex(ValueError, 'explicit trusted genesis and head'):
            h.export_history(self.database, self.case / 'no-anchor', prefix_bundle=self.bundle)
        with self.assertRaisesRegex(ValueError, 'trusted head'):
            h.export_history(self.database, self.case / 'wrong-anchor', prefix_bundle=self.bundle,
                expected_prefix_genesis=self.trusted['genesis'], expected_prefix_head='0' * 64)
        with self.assertRaisesRegex(ValueError, 'provenance policy'):
            h.export_history(self.database, self.case / 'changed-policy', prefix_bundle=self.bundle,
                expected_prefix_genesis=self.trusted['genesis'], expected_prefix_head=self.trusted['head'],
                inline_reprogram=True)
        changed = h.loads(self.database.read_bytes())
        changed['receipts'][0]['request']['principal'] = 'someone-else'
        database = self.case / 'changed-prefix.json'
        database.write_bytes(h.canonical(changed))
        with self.assertRaisesRegex(ValueError, 'does not match trusted prefix'):
            h.export_history(database, self.case / 'changed-prefix', prefix_bundle=self.bundle,
                expected_prefix_genesis=self.trusted['genesis'], expected_prefix_head=self.trusted['head'])

    def test_missing_source_blob_is_not_implicitly_read_from_workspace(self):
        bundle = self.altered(lambda m: None)
        sha = self.manifest['entries'][-1]['artifacts'][0]['sha256']
        (bundle / 'blobs' / sha).unlink()
        with self.assertRaises(FileNotFoundError):
            self.check(bundle)

    def test_export_rejects_missing_original_program_source(self):
        with self.assertRaisesRegex(ValueError, 'no matching source artifact'):
            h.export_history(self.database, self.case / 'no-source')

    def test_empty_or_tampered_source_envelopes_do_not_count_as_provenance(self):
        request = self.manifest['entries'][-1]['request']
        for field in ('artifact', 'record'):
            with self.subTest(field=field):
                forged = self.case / (field + '.json')
                forged.write_bytes(h.canonical({'request': request, field: {}}))
                with self.assertRaisesRegex(ValueError, 'no matching source artifact'):
                    h.export_history(self.database, self.case / ('forged-' + field),
                                     attachments={h.digest(request): [forged]})
        journal = h.loads((self.journals / 'program.json').read_bytes())
        journal['artifact']['source']['text'] += '\nchanged'
        forged = self.case / 'changed-source.json'
        forged.write_bytes(h.canonical(journal))
        with self.assertRaisesRegex(ValueError, 'source digest mismatch'):
            h.export_history(self.database, self.case / 'changed-source',
                             attachments={h.digest(request): [forged]})

    def test_declared_artifact_missing_and_unreplayable_snapshot_fail(self):
        request = self.manifest['entries'][0]['request']
        with self.assertRaises(FileNotFoundError):
            h.export_history(self.database, self.case / 'missing', journals=self.journals,
                             attachments={h.digest(request): [str(self.case / 'absent')]})
        altered = h.loads(self.database.read_bytes())
        altered['objects']['b']['state'] = {'model': source_object.data({'count': 1000})}
        database = self.case / 'mutated-world.json'
        database.write_bytes(h.canonical(altered))
        with self.assertRaisesRegex(ValueError, 'cannot be reconstructed'):
            h.export_history(database, self.case / 'unreconstructible', journals=self.journals)



if __name__ == '__main__':
    unittest.main()
