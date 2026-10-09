"""Runtime closure coverage and pin invalidation, without building or running Lean."""
from native_support import load_script
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
runtime = load_script(ROOT / 'scripts/runtime_profile.py', 'runtime_profile_test')


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
        manifest['groups']['compiled'].append('spec/Extra.lean')
        (self.root / 'spec/Extra.lean').write_text('new dependency')
        (self.root / runtime.MANIFEST).write_text(json.dumps(manifest))
        after = runtime.file_hashes('compiled', root=self.root)
        self.assertEqual(set(after) - set(before), {'spec/Extra.lean'})
        self.assertNotEqual(before[runtime.MANIFEST], after[runtime.MANIFEST])

    def test_transitive_local_compiled_sources_invalidate_pins(self):
        baseline = runtime.file_hashes('compiled', root=self.root)
        for name in ('spec/Delvetalk/Package.lean', 'spec/bend/Compiler/ObjectiveBendFrontEnd.lean',
                     'spec/bend/Compiler/ObjectiveBendElaborate.lean',
                     'profiles/TransactionsCore.lean', 'profiles/SourceProjection.lean',
                     'profiles/SourceReflection.lean', 'spec/Delvetalk/Generics.lean', '.lake/build/bin/delvetalk-compiled',
                     'scripts/world.py', 'lean-toolchain', 'lakefile.toml'):
            with self.subTest(dependency=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b' changed')
                changed = runtime.file_hashes('compiled', root=self.root)
                self.assertEqual([key for key in baseline if baseline[key] != changed[key]], [name])
                path.write_bytes(original)

    def test_same_size_and_mtime_source_and_runner_changes_invalidate_capture(self):
        runner = '.lake/build/bin/delvetalk-obend'
        (self.root / runner).write_bytes(b'physical package runner')
        names = (*runtime.paths('compiled', root=self.root), runner)
        before = runtime.hash_paths(names, root=self.root)
        for name in ('spec/Delvetalk/Package.lean', runner):
            with self.subTest(dependency=name):
                path = self.root / name
                original = path.read_bytes()
                metadata = path.stat()
                changed = bytes([original[0] ^ 1]) + original[1:]
                try:
                    path.write_bytes(changed)
                    os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
                    self.assertEqual(path.stat().st_size, metadata.st_size)
                    self.assertEqual(path.stat().st_mtime_ns, metadata.st_mtime_ns)
                    after = runtime.hash_paths(names, root=self.root)
                    self.assertEqual([key for key in before if before[key] != after[key]], [name])
                finally:
                    path.write_bytes(original)
                    os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))

    def test_unrelated_docs_and_independent_evaluator_do_not_change_profile(self):
        baseline = runtime.file_hashes('compiled', root=self.root)
        (self.root / 'README.md').write_text('unrelated documentation')
        evaluator = self.root / 'impl/python/evaluator.py'
        evaluator.parent.mkdir(parents=True, exist_ok=True)
        evaluator.write_text('independent evaluator bytes')
        self.assertEqual(runtime.file_hashes('compiled', root=self.root), baseline)
        self.assertEqual(set(runtime.PROFILES), {'compiled'})
        self.assertIn('profiles/TransactionsCore.lean', baseline)
        self.assertNotIn('.lake/build/bin/delvetalk-world', baseline)
        self.assertNotIn('.lake/build/bin/delvetalk-transactions', baseline)

    def test_unknown_profile_missing_source_and_escaping_symlink_refused(self):
        with self.assertRaisesRegex(ValueError, 'unknown runtime'):
            runtime.file_hashes('../arbitrary', root=self.root)
        path = self.root / 'spec/bend/Theory/AxiomPin.lean'
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            runtime.file_hashes('compiled', root=self.root)
        outside = Path(self.temp.name) / 'outside'
        outside.write_text('outside repository')
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes repository'):
            runtime.file_hashes('compiled', root=self.root)

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


class NestedSourceCaptureTests(unittest.TestCase):
    def test_real_source_load_reuses_capture_and_both_boundaries_detect_byte_drift(self):
        # Each worker gets independent writable custody files and native copies;
        # fault injection never modifies the repository or a shared build.
        sys.path.insert(0, str(ROOT / 'scripts'))
        import source_store
        import process_custody
        names = set(source_store.adapter_pin('objective-bend-object')['files']) | {
            'syntaxes/registry.json', 'scripts/source_object.py', 'scripts/source_store.py',
            'scripts/translate.py', 'scripts/runtime_profile.py', 'scripts/runtime_profiles.json',
            'scripts/process_custody.py', 'scripts/affordances.py', 'scripts/source_closure.py',
            'scripts/source_packages.py', 'protocols/private-counter/Counter.obend'}
        worker = r'''import os,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path.cwd()/'scripts'))
import source_object
root=Path.cwd()
name=sys.argv[1]
path=root/name
metadata=path.stat()
original=source_object.adapter.runtime_profile.hash_paths
calls=[]
def after_native(names,**kwargs):
    calls.append(tuple(names))
    observed=original(names,**kwargs) if name=='scripts/source_packages.py' else None
    with path.open('r+b') as stream:
        first=stream.read(1)
        stream.seek(0)
        stream.write(bytes([first[0]^1]))
    os.utime(path,ns=(metadata.st_atime_ns,metadata.st_mtime_ns))
    assert path.stat().st_size==metadata.st_size
    assert path.stat().st_mtime_ns==metadata.st_mtime_ns
    return observed if observed is not None else original(names,**kwargs)
modules=[{'name':'Counter','source':(root/'protocols/private-counter/Counter.obend').read_bytes().decode('utf8')}]
try:
    with patch.object(source_object.adapter.runtime_profile,'hash_paths',side_effect=after_native):
        source_object.load(modules,syntax='objective-bend-object')
except ValueError as error:
    assert 'runtime changed' in str(error),str(error)
else:
    raise AssertionError('changed runtime was admitted')
assert len(calls)==1,'initial runtime subset was redundantly recaptured'
assert '.lake/build/bin/delvetalk-obend' in calls[0]
'''
        for changed in ('lean-toolchain', '.lake/build/bin/delvetalk-obend', 'scripts/source_packages.py'):
            with self.subTest(dependency=changed), tempfile.TemporaryDirectory() as directory:
                frozen = Path(directory)
                for name in sorted(names):
                    destination = frozen / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if sys.platform == 'darwin':
                        subprocess.run(['cp', '-c', str(ROOT / name), str(destination)], check=True)
                    else:
                        shutil.copy2(ROOT / name, destination)
                done = process_custody.run_native([sys.executable, '-c', worker, changed],
                    cwd=frozen, timeout=30, cpu_seconds=25, stdout_limit=1024 * 1024,
                    stderr_limit=1024 * 1024, file_limit=8 * 1024 * 1024)
                self.assertEqual(done.returncode, 0, done.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
