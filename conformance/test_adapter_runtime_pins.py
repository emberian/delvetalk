#!/usr/bin/env python3
"""Opt-in syntax runtimes share exact translation and source-custody dependencies."""
import copy
from native_support import load_script
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    return load_script(ROOT / path, name)


translate = module('runtime_pin_translate', 'scripts/translate.py')
store = module('runtime_pin_store', 'scripts/source_store.py')
runtime = module('runtime_pin_host', 'scripts/runtime_profile.py')
history = module('runtime_pin_history', 'scripts/history.py')


class AdapterRuntimePins(unittest.TestCase):
    def setUp(self):
        self.registry_path = ROOT / 'syntaxes/registry.json'
        self.registry = translate.load_json(self.registry_path.read_bytes())
        self.registry['syntaxes']['runtime-probe@1'] = {
            'reviewed': True, 'module': 'syntaxes/adapters.py', 'entry': 'json_value',
            'target': 'core-term-v1', 'runtimeProfile': 'compiled',
            'closure': ['spec/PackageMain.lean', '.lake/build/bin/delvetalk-obend']}

    def registry_bytes(self, registry=None):
        """Replace only registry reads; the actual repository stays untouched."""
        raw = translate.canonical(self.registry if registry is None else registry)
        read = Path.read_bytes
        return patch.object(Path, 'read_bytes', lambda path:
            raw if path.resolve() == self.registry_path else read(path))

    def test_opt_in_translation_and_source_custody_have_identical_full_pins(self):
        with self.registry_bytes():
            artifact = translate.translate('runtime-probe@1', b'["nat","1"]')
            pin = store.adapter_pin('runtime-probe@1')
        self.assertEqual(pin, artifact['translation'])
        expected = {*runtime.paths('compiled'), 'spec/PackageMain.lean', '.lake/build/bin/delvetalk-obend'}
        self.assertTrue(expected <= set(pin['files']))
        for name in expected:
            self.assertEqual(pin['files'][name], translate.digest((ROOT / name).read_bytes()))
        self.assertEqual(artifact['lowered'], ['nat', '1'])
        self.assertEqual(set(pin), {'syntax', 'adapter', 'validator', 'registry_sha256', 'files', 'pin'})

    def test_non_opted_adapter_keeps_declared_closure_and_pin_shape(self):
        syntax = 'core-json@1'
        adapter = self.registry['syntaxes'][syntax]
        validator = self.registry['targets'][adapter['target']]
        paths = set(self.registry['closure'] + adapter.get('closure', []) +
                    validator.get('closure', []) + ['scripts/translate.py'])
        with self.registry_bytes():
            artifact = translate.translate(syntax, b'["nat","1"]')
            pin = store.adapter_pin(syntax)
        self.assertEqual(pin, artifact['translation'])
        self.assertEqual(pin['files'], {name: translate.digest((ROOT / name).read_bytes()) for name in paths})
        self.assertNotIn('scripts/runtime_profile.py', pin['files'])

    def test_runtime_drift_during_translation_is_refused(self):
        opened, calls = Path.open, []
        binary = ROOT / '.lake/build/bin/delvetalk-obend'
        def changed(path, *args, **kwargs):
            if path.resolve() == binary:
                calls.append(path)
                return io.BytesIO(b'original' if len(calls) == 1 else b'changed')
            return opened(path, *args, **kwargs)
        # Dependency capture streams files; the JSON-only probe never executes
        # this binary. Change its observed bytes between the real hash captures.
        with self.registry_bytes(), patch.object(Path, 'open', changed), self.assertRaisesRegex(ValueError, 'changed during translation'):
            translate.translate('runtime-probe@1', b'["nat","1"]')
        self.assertEqual(len(calls), 2)

    def test_registry_drift_during_translation_is_refused(self):
        raw = translate.canonical(self.registry)
        read, calls = Path.read_bytes, []
        def changed(path):
            if path.resolve() == self.registry_path:
                calls.append(path)
                return raw if len(calls) == 1 else raw + b'\n'
            return read(path)
        with patch.object(Path, 'read_bytes', changed), self.assertRaisesRegex(ValueError, 'changed during translation'):
            translate.translate('runtime-probe@1', b'["nat","1"]')

    def test_unknown_runtime_and_escaping_extra_dependency_refuse_in_both_consumers(self):
        bad_profile = copy.deepcopy(self.registry)
        bad_profile['syntaxes']['runtime-probe@1']['runtimeProfile'] = 'missing'
        bad_closure = copy.deepcopy(self.registry)
        bad_closure['syntaxes']['runtime-probe@1']['closure'].append('../outside')
        for registry in (bad_profile, bad_closure):
            with self.subTest(registry=registry), self.registry_bytes(registry):
                with self.assertRaises(ValueError):
                    translate.translate('runtime-probe@1', b'["nat","1"]')
                with self.assertRaises(ValueError):
                    store.adapter_pin('runtime-probe@1')

    def test_historical_source_reference_read_does_not_require_current_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            proposal = store.prepare_proposal(temporary, 'core-json@1', b'["nat","1"]', b'[]')
            with patch.object(store, 'adapter_pin', side_effect=ValueError('current adapter unavailable')):
                self.assertEqual(store.validate_proposal(temporary, proposal, check_adapter=False),
                                 (b'["nat","1"]', b'[]'))
                with self.assertRaisesRegex(ValueError, 'unavailable'):
                    store.validate_proposal(temporary, proposal)

    def test_history_checks_shared_runtime_closure_and_retained_bytes_without_executing_them(self):
        self.registry['syntaxes']['runtime-probe@1']['target'] = 'local-protocol-v1'
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {}}
        with self.registry_bytes():
            artifact = translate.translate('runtime-probe@1', translate.canonical(protocol))
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            (bundle / 'blobs').mkdir()
            history.store_bytes(bundle, translate.canonical(self.registry))
            for name, sha in artifact['translation']['files'].items():
                self.assertEqual(history.store_file(bundle, ROOT / name), sha)
            self.assertEqual(history.lowered_protocol(artifact, bundle), protocol)
            # Today's profile may grow after this source was archived. Its
            # retained manifest, rather than today's path namespace, governs
            # verification; no future dependency is fabricated into history.
            current = runtime.load_manifest()
            current['groups']['common'].append('profiles/FutureHostDependency.lean')
            read = Path.read_bytes
            with patch.object(Path, 'read_bytes', lambda path:
                    translate.canonical(current) if path.resolve() == ROOT / runtime.MANIFEST else read(path)):
                self.assertIn('profiles/FutureHostDependency.lean', runtime.paths('compiled'))
                self.assertEqual(history.lowered_protocol(artifact, bundle), protocol)
            # A retained lowering is source custody, not a claim to have rerun
            # its compiler. Verification reads retained hashes, never today's
            # native executable bytes or any archived executable code.
            archived = copy.deepcopy(artifact)
            binary = '.lake/build/bin/delvetalk-obend'
            old_sha = history.store_bytes(bundle, b'retained historical binary bytes; never execute')
            archived['translation']['files'][binary] = old_sha
            archived['translation']['pin'] = history.digest({
                key: value for key, value in archived['translation'].items() if key != 'pin'})
            with patch.object(history.translate, 'closure_files', side_effect=AssertionError('current file hashes')):
                self.assertEqual(history.lowered_protocol(archived, bundle), protocol)
            # Removing even one runtime dependency cannot be concealed by
            # recomputing the self-contained translation identity.
            missing = copy.deepcopy(artifact)
            del missing['translation']['files']['spec/PackageMain.lean']
            missing['translation']['pin'] = history.digest({
                key: value for key, value in missing['translation'].items() if key != 'pin'})
            with self.assertRaisesRegex(ValueError, 'dependency closure'):
                history.lowered_protocol(missing, bundle)
            history.blob_path(bundle, old_sha).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'blob digest mismatch'):
                history.lowered_protocol(archived, bundle)
            manifest_sha = artifact['translation']['files'][runtime.MANIFEST]
            history.blob_path(bundle, manifest_sha).write_bytes(b'{"tampered":true}')
            with self.assertRaisesRegex(ValueError, 'blob digest mismatch'):
                history.lowered_protocol(artifact, bundle)

    def test_retained_manifest_refuses_escape_and_unknown_profile_without_source_execution(self):
        for path in ('../outside', '/absolute', 'nested/../escape', '.', 'a\\b', 'a//b'):
            manifest = runtime.load_manifest()
            manifest['groups']['common'].append(path)
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'repository path'):
                runtime.paths('compiled', manifest=manifest)
        with self.assertRaisesRegex(ValueError, 'unknown runtime profile'):
            runtime.paths('invented', manifest=runtime.load_manifest())

    def test_legacy_history_does_not_acquire_a_runtime_closure(self):
        protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {}}
        with self.registry_bytes():
            artifact = translate.translate('protocol-json@1', translate.canonical(protocol))
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            (bundle / 'blobs').mkdir()
            history.store_bytes(bundle, translate.canonical(self.registry))
            for name, sha in artifact['translation']['files'].items():
                self.assertEqual(history.store_file(bundle, ROOT / name), sha)
            with patch.object(history.translate.importlib.util, 'spec_from_file_location',
                              side_effect=AssertionError('historical source code must not execute')):
                self.assertEqual(history.lowered_protocol(artifact, bundle), protocol)


if __name__ == '__main__':
    unittest.main()
