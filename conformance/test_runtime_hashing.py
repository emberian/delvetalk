"""Dependency captures deduplicate reads without caching across boundaries."""
import hashlib
from native_support import load_script
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    return load_script(ROOT / path, name)


runtime = module('hashing_runtime', 'scripts/runtime_profile.py')
queue = module('hashing_queue', 'scripts/compiler_queue.py')
projection = module('hashing_projection', 'scene/projection.py')


class RuntimeHashingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def write(self, name, data=b'fixture'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_streams_unique_paths_and_recaptures_changed_bytes(self):
        data = b'chunk' * 200000
        self.write('binary', data)
        self.write('source', b'source')
        original_open = Path.open
        opened = []
        def observe(path, *args, **kwargs):
            opened.append(path)
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', observe), patch.object(Path, 'read_bytes', side_effect=AssertionError('whole-file read')):
            first = runtime.hash_paths(['source', 'binary', 'binary'], root=self.root)
        self.assertEqual(opened, [self.root / 'binary', self.root / 'source'])
        self.assertEqual(first['binary'], hashlib.sha256(data).hexdigest())
        self.write('binary', data + b'changed')
        self.assertNotEqual(runtime.hash_paths(first, root=self.root)['binary'], first['binary'])

    def test_normalized_paths_and_escaping_symlinks_refuse(self):
        for name in ('../outside', '/outside', './source', 'source//child', 'source/../child', '.', '', 3, 'a\\b'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'normalized repository path'):
                runtime.hash_paths([name], root=self.root)
        outside = self.root.parent / (self.root.name + '-outside')
        outside.write_bytes(b'outside')
        self.addCleanup(outside.unlink)
        (self.root / 'escape').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes repository'):
            runtime.hash_paths(['escape'], root=self.root)
        with self.assertRaises(FileNotFoundError):
            runtime.hash_paths(['missing'], root=self.root)

    def test_queue_unions_paths_before_one_hash_capture(self):
        registry = {'syntaxes': {'fixture': {'target': 'fixture'}}, 'targets': {'fixture': {}}}
        self.write('syntaxes/registry.json', json.dumps(registry).encode())
        names = {'scripts/compiler_queue.py', 'scripts/worker.py', 'scripts/clerk.py',
                 'scripts/translate.py', 'syntaxes/registry.json', 'binary', 'desk', 'proposal', 'adapter'}
        for name in names - {'syntaxes/registry.json'}:
            self.write(name)
        original_open = Path.open
        opened = []
        def observe(path, *args, **kwargs):
            opened.append(path)
            return original_open(path, *args, **kwargs)
        proposal = SimpleNamespace(execution_paths=lambda profile: ('binary', 'proposal'))
        with patch.object(queue, 'ROOT', self.root), patch.object(queue.desk, 'module', return_value=proposal), \
             patch.object(queue.desk, 'execution_paths', return_value=('binary', 'desk')), \
             patch.object(queue.desk, 'execution_profile', side_effect=AssertionError('already hashed profile')), \
             patch.object(queue.desk.translate, 'closure_paths', return_value=('binary', 'adapter')), \
             patch.object(Path, 'open', observe):
            pins = queue.syntax_pins('compiled', 'fixture')
        self.assertEqual(set(pins['files']), names)
        self.assertEqual(opened.count(self.root / 'binary'), 1)
        self.assertEqual(pins['files']['binary'], hashlib.sha256(b'fixture').hexdigest())

    def project_with_pins(self, before, after):
        binary = '.lake/build/bin/delvetalk-compiled'
        self.write(binary)
        root = {'protocol': {'commands': {}, 'viewProgram': {'profile': projection.DATA_MENU_PROFILE,
                'package': {'modules': [{'name': 'Main', 'source': 'fixture'}], 'entry': 'view'}}},
                'state': {'model': {'tag': 'record', 'fields': []}}}
        reply = {'result': {'tag': 'record', 'fields': [
            {'name': 'title', 'value': {'tag': 'label', 'value': 'Title'}},
            {'name': 'prose', 'value': {'tag': 'label', 'value': 'Prose'}},
            {'name': 'actions', 'value': {'tag': 'record', 'fields': []}},
            {'name': 'children', 'value': {'tag': 'variant', 'label': 'nil',
                                         'payload': {'tag': 'record', 'fields': []}}}]}}
        with patch.object(projection, 'ROOT', self.root), \
             patch.object(projection.runtime_profile, 'file_hashes', side_effect=[before, after]) as capture, \
             patch.object(projection.world.process_custody, 'run_native',
                          return_value=subprocess.CompletedProcess([], 0, json.dumps(reply).encode(), b'')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('duplicate binary hash')):
            try:
                return projection.project(root, 'fixture')
            finally:
                self.assertEqual(capture.call_count, 2)

    def test_projection_reuses_each_boundary_binary_digest(self):
        pins = {'.lake/build/bin/delvetalk-compiled': 'b' * 64, 'source': 's' * 64}
        view = self.project_with_pins(pins, dict(pins))
        self.assertEqual(view['runtimeSha256'], pins['.lake/build/bin/delvetalk-compiled'])
        self.assertEqual(view['runtimeProfile']['files'], pins)

    def test_projection_still_refuses_binary_or_source_drift(self):
        before = {'.lake/build/bin/delvetalk-compiled': 'b' * 64, 'source': 's' * 64}
        for name, message in [('.lake/build/bin/delvetalk-compiled', 'runtime changed'), ('source', 'dependencies changed')]:
            with self.subTest(dependency=name), self.assertRaisesRegex(projection.ProjectionError, message):
                self.project_with_pins(before, {**before, name: '0' * 64})


if __name__ == '__main__':
    unittest.main()
