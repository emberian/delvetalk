"""Runtime closure coverage and pin invalidation, without building or running Lean."""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runtime_profile_test', ROOT / 'scripts/runtime_profile.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        for profile in runtime.PROFILES:
            for name in runtime.paths(profile):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture bytes for ' + name)
        (self.root / runtime.MANIFEST).write_bytes((ROOT / runtime.MANIFEST).read_bytes())

    def test_manifest_is_pinned_and_owns_profile_growth(self):
        before = runtime.file_hashes('compiled', root=self.root)
        manifest = runtime.load_manifest(root=self.root)
        manifest['groups']['package'].append('spec/Extra.lean')
        (self.root / 'spec/Extra.lean').write_text('new dependency')
        (self.root / runtime.MANIFEST).write_text(json.dumps(manifest))
        after = runtime.file_hashes('compiled', root=self.root)
        self.assertEqual(set(after) - set(before), {'spec/Extra.lean'})
        self.assertNotEqual(before[runtime.MANIFEST], after[runtime.MANIFEST])

    def test_transitive_local_compiled_sources_invalidate_pins(self):
        baseline = runtime.file_hashes('compiled', root=self.root)
        for name in ('spec/Delvetalk/Package.lean', 'spec/bend/Compiler/ObjectiveBendFrontEnd.lean',
                     'spec/bend/Compiler/ObjectiveBendElaborate.lean',
                     'profiles/TransactionsCore.lean', '.lake/build/bin/delvetalk-compiled',
                     'scripts/world.py', 'lean-toolchain', 'lakefile.toml'):
            with self.subTest(dependency=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b' changed')
                changed = runtime.file_hashes('compiled', root=self.root)
                self.assertEqual([key for key in baseline if baseline[key] != changed[key]], [name])
                path.write_bytes(original)

    def test_unrelated_docs_and_nonselected_host_do_not_change_profile(self):
        baseline = runtime.file_hashes('world', root=self.root)
        (self.root / 'README.md').write_text('unrelated documentation')
        (self.root / 'spec/Delvetalk/Package.lean').write_text('changed compiled-only dependency')
        self.assertEqual(runtime.file_hashes('world', root=self.root), baseline)
        self.assertNotIn('profiles/TransactionsCore.lean', baseline)
        self.assertIn('profiles/TransactionsCore.lean', runtime.file_hashes('transactions', root=self.root))

    def test_unknown_profile_missing_source_and_escaping_symlink_refused(self):
        with self.assertRaisesRegex(ValueError, 'unknown runtime'):
            runtime.file_hashes('../arbitrary', root=self.root)
        path = self.root / 'spec/bend/Theory/AxiomPin.lean'
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            runtime.file_hashes('world', root=self.root)
        outside = Path(self.temp.name) / 'outside'
        outside.write_text('outside repository')
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes repository'):
            runtime.file_hashes('world', root=self.root)

    def test_reviewed_closures_cover_actual_local_project_imports(self):
        # Check the maintained lists against this pinned project's simple import
        # declarations. This is a regression check, not a runtime module loader.
        for profile in runtime.PROFILES:
            selected = set(runtime.paths(profile))
            for name in sorted(selected):
                if not name.endswith('.lean'):
                    continue
                text = (ROOT / name).read_text()
                for declaration in re.findall(r'^import\s+([^\n]+)', text, re.M):
                    for module in declaration.split():
                        if module == 'Lean' or module.startswith(('Lean.', 'Std.', 'Init.')):
                            continue
                        if module.startswith(('Compiler.', 'Pred.', 'Theory.')):
                            imported = 'spec/bend/' + module.replace('.', '/') + '.lean'
                        elif module.startswith('Delvetalk.'):
                            imported = 'spec/' + module.replace('.', '/') + '.lean'
                        else:
                            imported = 'profiles/' + module.replace('.', '/') + '.lean'
                        self.assertIn(imported, selected, f'{profile}: {name} imports missing {imported}')


if __name__ == '__main__':
    unittest.main()
