"""Physical packaging custody; source meaning stays with the native parser."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_closure
import source_store


class SourceClosure(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = {}

    def module(self, name, source='edition ObjectiveBend 1\r\n'):
        path = self.root / (name + '.obend')
        path.write_bytes(source.encode('utf-8'))
        self.sources[name] = path
        return path

    def assemble(self, roots, edges):
        return source_closure.assemble(roots, list(self.sources.items()), root=self.root,
            parser=lambda modules: {m['name']: [{'path': path, 'alias': 'Alias'}
                for path in edges.get(m['name'], [])] for m in modules})

    def test_diamond_aliases_exact_bytes_and_manifest(self):
        for name in ('Entry', 'Right', 'Unused', 'Shared', 'Left'):
            self.module(name)
        edges = {'Entry': ['./Left.obend', './Right.obend'],
                 'Left': ['./Shared.obend'], 'Right': ['./Shared.obend', './Shared.obend']}
        result = self.assemble(['Entry'], edges)
        self.assertEqual([m['name'] for m in result['modules']], ['Shared', 'Left', 'Right', 'Entry'])
        self.assertEqual(result['modules'][0]['source'], 'edition ObjectiveBend 1\r\n')
        source_store.validate_manifest(result['manifest'])
        self.module('Shared', 'edition ObjectiveBend 1\n')
        self.assertNotEqual(result['manifest']['sha256'], self.assemble(['Entry'], edges)['manifest']['sha256'])

    def test_missing_dependency_and_non_package_paths(self):
        self.module('Entry')
        for path in ('./Missing.obend', '../Entry.obend', '/Entry.obend', './entry.obend'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'explicit allowlist'):
                self.assemble(['Entry'], {'Entry': [path]})

    def test_cycles_show_chain(self):
        self.module('A'); self.module('B')
        with self.assertRaisesRegex(ValueError, 'A -> B -> A'):
            self.assemble(['A'], {'A': ['./B.obend'], 'B': ['./A.obend']})

    def test_duplicate_names_and_path_aliases_refuse_before_parser(self):
        path = self.module('A')
        for allowed in ([('A', path), ('A', path)], [('A', path), ('B', path)]):
            with self.assertRaisesRegex(ValueError, 'duplicate|ambiguous'):
                source_closure.assemble(['A'], allowed, root=self.root,
                    parser=lambda _: self.fail('parser called before allowlist validation'))

    def test_outside_path_and_symlink_refuse_before_any_read(self):
        path = self.module('A')
        outside = self.root.parent / 'outside-source-does-not-need-to-exist.obend'
        (self.root / 'escape.obend').symlink_to(outside)
        for supplied in (outside, self.root / 'escape.obend'):
            with self.assertRaisesRegex(ValueError, 'escapes custody root'):
                source_closure.assemble(['A'], [('A', path), ('B', supplied)], root=self.root,
                    parser=lambda _: self.fail('parser called before path validation'))

    def test_bounded_regular_source_reads(self):
        oversized = self.module('A', 'x' * (512 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, 'byte bound'):
            source_closure.assemble(['A'], [('A', oversized)], root=self.root,
                parser=lambda _: self.fail('parser called with oversized source'))
        with patch.object(source_store.os, 'close', wraps=source_store.os.close) as close:
            with self.assertRaisesRegex(ValueError, 'regular file'):
                source_closure.assemble(['A'], [('A', self.root)], root=self.root,
                    parser=lambda _: self.fail('parser called with directory source'))
            close.assert_called_once()

    def test_root_order_and_entry_dependency_refusal(self):
        self.module('A'); self.module('B'); self.module('C')
        result = self.assemble(['B', 'A'], {'A': ['./C.obend']})
        self.assertEqual([m['name'] for m in result['modules']], ['B', 'C', 'A'])
        with self.assertRaisesRegex(ValueError, 'entry module'):
            self.assemble(['A', 'C'], {'A': ['./C.obend']})


class SourceMaterialOrder(unittest.TestCase):
    def test_exact_material_is_cloned_and_unreachable_sources_omitted(self):
        modules = [{'name': 'Scene', 'source': 'scene\r\n'},
                   {'name': 'Unused', 'source': 'unused'},
                   {'name': 'Library', 'source': 'library'}]
        def parser(supplied):
            return {m['name']: [{'path': './Library.obend', 'alias': 'L'}]
                    if m['name'] == 'Scene' else [] for m in supplied}
        ordered = source_closure.order(['Scene'], modules, parser=parser)
        self.assertEqual([m['name'] for m in ordered], ['Library', 'Scene'])
        self.assertEqual(ordered[-1]['source'], 'scene\r\n')
        ordered[-1]['source'] = 'changed'
        self.assertEqual(modules[0]['source'], 'scene\r\n')

    def test_duplicate_material_and_missing_root_refuse_before_parser(self):
        entry = {'name': 'Scene', 'source': 'scene'}
        for roots, modules in ((['Scene'], [entry, entry]), (['Missing'], [entry])):
            with self.assertRaisesRegex(ValueError, 'duplicate|missing'):
                source_closure.order(roots, modules,
                    parser=lambda _: self.fail('parser called before material validation'))

    def test_multiple_roots_preserve_requested_entry(self):
        modules = [{'name': name, 'source': name} for name in ('Scene', 'Handler', 'Library')]
        def parser(_):
            return {'Scene': [{'path': './Handler.obend'}],
                    'Handler': [{'path': './Library.obend'}], 'Library': []}
        self.assertEqual([m['name'] for m in source_closure.order(['Handler', 'Scene'], modules, parser=parser)],
                         ['Library', 'Handler', 'Scene'])


class NativeSourceClosure(unittest.TestCase):
    def test_editor_crlf_utf8_file_preimage_survives_native_package_and_custody(self):
        import hashlib
        import importlib.util
        import time
        spec = importlib.util.spec_from_file_location('exact_editor_source_reader', ROOT / 'protocols/editor/generate.py')
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        original = (ROOT / 'protocols/editor/Editor.obend').read_bytes().decode('utf-8')
        raw = (original.replace('\r\n', '\n').replace('\n', '\r\n') + '# café λ 🌱\r\n').encode('utf-8')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Editor.obend').write_bytes(raw)
            with patch.object(loader, 'HERE', root):
                source = loader.editor_source()
            ref = source_store.store_bytes(root / 'artifacts', source.encode('utf-8'), kind='source')
            self.assertEqual(ref['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(source_store.read_bytes(root / 'artifacts', ref, kind='source'), raw)
            # A repeat uses the original retained bytes; a normalized preimage is distinct.
            self.assertEqual(source_store.store_bytes(root / 'artifacts', raw, kind='source'), ref)
            self.assertNotEqual(source_store.reference(raw.replace(b'\r\n', b'\n')), ref)
            allowed = dict(source_closure.LIBRARY)
            allowed['Authority'] = 'world/lib/prelude/Authority.obend'
            modules = loader.source_object.read_modules([(name, ROOT / path) for name, path in allowed.items()])
            modules = source_closure.order(['Editor'], modules + [{'name': 'Editor', 'source': source}])
            reply = loader.source_object.adapter._native({'op': 'compile', 'modules': modules,
                'entry': 'describe'}, time.monotonic() + 30)
            self.assertEqual(reply['status'], 'compiled', reply)
            artifact = reply['artifact']
            self.assertEqual(artifact['modules'][-1]['source'].encode('utf-8'), raw)
            self.assertEqual(artifact['sourcesSha256'], hashlib.sha256(source_store.canonical(modules)).hexdigest())

    def test_forge_source_and_examples_retain_exact_utf8_crlf_references(self):
        import hashlib
        import importlib.util
        spec = importlib.util.spec_from_file_location('exact_forge_source_reader', ROOT / 'protocols/town-forge/generate.py')
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'syntaxes/examples').mkdir(parents=True)
            raw_source = 'edition ObjectiveBend 1\r\n# café λ\r\ndef entry() -> Nat:\r\n  7n\r\n'.encode('utf-8')
            raw_examples = '# retained examples café 🌱\r\n'.encode('utf-8')
            (root / 'syntaxes/examples/paper-door.obend').write_bytes(raw_source)
            for name in ('paper-door.examples', 'moon-challenge.examples'):
                (root / name).write_bytes(raw_examples)
            with patch.object(loader, 'ROOT', root), patch.object(loader, 'HERE', root):
                texts = [loader.spell_source(), loader.example_source(), loader.challenge_source()]
            for text, raw, kind in zip(texts, (raw_source, raw_examples, raw_examples), ('source', 'scenarios', 'scenarios')):
                ref = source_store.store_bytes(root / 'artifacts', text.encode('utf-8'), kind=kind)
                self.assertEqual(ref['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(source_store.read_bytes(root / 'artifacts', ref, kind=kind), raw)

    def test_actual_parser_preserves_aliases_and_compiler_accepts_order(self):
        import process_custody
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'dependency.obend').write_text('edition ObjectiveBend 1\ndef value() -> Nat:\n  7n\n')
            (root / 'entry.obend').write_text('edition ObjectiveBend 1\nimport ./A.obend as First\nimport ./A.obend as Second\ndef entry() -> Nat:\n  First.value()\n')
            allowed = [('Entry', root / 'entry.obend'), ('A', root / 'dependency.obend')]
            result = source_closure.assemble(['Entry'], allowed, root=root)
            self.assertEqual([m['name'] for m in result['modules']], ['A', 'Entry'])
            parsed = source_closure.native_imports(result['modules'])
            self.assertEqual([e['alias'] for e in parsed['Entry']], ['First', 'Second'])
            done = process_custody.run_native([str(ROOT / '.lake/build/bin/delvetalk-obend')],
                input=source_store.canonical({'op': 'compile', 'modules': result['modules'], 'entry': 'entry'}) + b'\n',
                cwd=ROOT, timeout=15, cpu_seconds=10, stdout_limit=8 * 1024 * 1024,
                stderr_limit=1024 * 1024, file_limit=8 * 1024 * 1024)
            self.assertEqual(source_store.loads(done.stdout).get('status'), 'compiled', done.stdout)

    def test_actual_parser_refuses_malformed_source(self):
        with self.assertRaisesRegex(ValueError, 'native source import parser refused'):
            source_closure.native_imports([{'name': 'Invalid', 'source': 'this is not Bend'}])

    def test_resident_loader_keeps_all_four_explicit_roots(self):
        import importlib.util
        import time
        spec = importlib.util.spec_from_file_location('closure_residents', ROOT / 'protocols/resident-messages/package.py')
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        for name in ('Bell', 'Door', 'Lantern', 'Loop'):
            with self.subTest(resident=name):
                modules = loader.sources(name)
                self.assertEqual(modules[-1]['name'], name)
                reply = loader.source_object.adapter._native({'op': 'compile', 'modules': modules,
                    'entry': 'describe'}, time.monotonic() + 30)
                self.assertEqual(reply['status'], 'compiled', reply)

    def test_six_major_loaders_retain_current_exact_native_dependencies(self):
        import importlib.util
        cases = [
            ('examples/evening-courtyard/package.py', {'afterglow': True}),
            ('protocols/root-directory/package.py', {'factory': True}),
            ('protocols/account-heap/generate.py', {}),
            ('protocols/shared-exhibition/package.py', {}),
            ('protocols/work-ticket/package.py', {}),
            ('game/table/protocol.py', {}),
        ]
        for index, (path, arguments) in enumerate(cases):
            with self.subTest(loader=path):
                spec = importlib.util.spec_from_file_location('closure_loader_' + str(index), ROOT / path)
                loader = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(loader)
                modules = loader.modules(**arguments)
                names = [m['name'] for m in modules]
                self.assertIn('List', names)
                parsed = source_closure.native_imports(modules)
                earlier = set()
                for module in modules:
                    for edge in parsed[module['name']]:
                        self.assertIn(edge['path'], {'./' + name + '.obend' for name in earlier})
                    earlier.add(module['name'])
                self.assertEqual(len(names), len(set(names)))
                import time
                reply = loader.source_object.adapter._native({'op': 'compile',
                    'modules': modules, 'entry': 'describe'}, time.monotonic() + 30)
                self.assertEqual(reply['status'], 'compiled', reply)


if __name__ == '__main__':
    unittest.main()
