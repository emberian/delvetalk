"""Shared adapter retains source once; native table and inline execution agree."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_packages
import translate
import world


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

adapter = module('shared_package_adapter', 'syntaxes/obend_object.py')
projection = module('shared_package_projection', 'scene/projection.py')


class SourceTableShapeTests(unittest.TestCase):
    def test_source_table_copies_exact_order_and_bytes_without_resolving_imports(self):
        modules = [{'name': 'Base', 'source': 'exact\r\n'}, {'name': 'Main', 'source': 'import ./Base.obend as Base\n'}]
        value = source_packages.table(modules)
        self.assertEqual(value['modules'], modules)
        modules[0]['source'] = 'different'
        self.assertEqual(value['modules'][0]['source'], 'exact\r\n')
        selector = source_packages.selector('act')
        self.assertEqual(source_packages.validate_selector(selector), selector)
        with self.assertRaises(ValueError): source_packages.validate_selector({**selector, 'path': '/tmp/source'})
        with self.assertRaises(ValueError): source_packages.validate_tables({'sourcePackages': {'resident': {'format': 'unknown', 'modules': []}}})


class NativeSharedPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='source-table-')
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'world.json'
        self.serial = 0

    def call(self, request):
        self.serial += 1
        return world.exchange(self.database, {'principal': 'visitor', 'intent': 'source-table-' + str(self.serial), **request}, profile='compiled')

    def create(self, name, protocol):
        return self.call({'op': 'create', 'object': name, 'protocol': protocol, 'law': ['visitor']})

    def root(self, name):
        return self.call({'op': 'inspect', 'object': name})

    def test_source_stored_once_and_inline_methods_views_remain_identical(self):
        source = (ROOT / 'syntaxes/examples/lantern.obend').read_bytes() + b'\n# ' + b'x' * 12000 + b'\n'
        protocol = translate.translate('objective-bend-spell@2', source)['lowered']
        encoded = translate.canonical(protocol)
        self.assertEqual(encoded.count(translate.canonical(source.decode())), 1)
        self.assertLess(len(encoded), len(source) + 8192)
        tables = source_packages.validate_tables(protocol)
        self.assertEqual(tables['resident']['modules'], [{'name': 'Main', 'source': source.decode()}])
        inline = copy.deepcopy(protocol)
        for command in inline['commands'].values():
            selected = command['transition']['package']
            command['transition']['package'] = {'modules': copy.deepcopy(tables[selected['name']]['modules']), 'entry': selected['entry']}
        selected = inline['viewProgram']['package']
        inline['viewProgram']['package'] = {'modules': copy.deepcopy(tables[selected['name']]['modules']), 'entry': selected['entry']}
        del inline['sourcePackages']
        for name, program in (('shared', protocol), ('inline', inline)):
            self.assertEqual(self.create(name, program)['kind'], 'committed')
        for command in ('light', 'douse'):
            outcomes = []
            for name in ('shared', 'inline'):
                reply = self.call({'op': 'invoke', 'object': name, 'expected': self.root(name), 'command': command, 'input': {}})
                self.assertEqual(reply['kind'], 'committed', reply)
                outcomes.append((reply['data']['result'], reply['data']['root']['state']))
            self.assertEqual(outcomes[0], outcomes[1])
        observed = [projection.project(self.root(name), name)['data'] for name in ('shared', 'inline')]
        self.assertEqual(observed[0], observed[1])

    def test_missing_selector_bad_source_and_reordered_imports_refuse_and_old_roots_stay_exact(self):
        source = (ROOT / 'syntaxes/examples/lantern.obend').read_bytes()
        protocol = translate.translate('objective-bend-spell@2', source)['lowered']
        missing = copy.deepcopy(protocol)
        missing['commands']['light']['transition']['package']['name'] = 'absent'
        self.assertEqual(self.create('missing', missing)['kind'], 'refused')
        bad = copy.deepcopy(protocol)
        bad['sourcePackages']['resident']['modules'][0]['source'] = 'broken source'
        self.assertEqual(self.create('broken', bad)['kind'], 'refused')
        modules = [{'name': name, 'source': (ROOT / 'protocols/peer-layers' / (name + '.obend')).read_text()}
                   for name in ('Base', 'Doubling', 'Main')]
        imported = adapter.lower_modules(modules)
        imported['sourcePackages']['resident']['modules'].reverse()
        self.assertEqual(self.create('reordered', imported)['kind'], 'refused')
        root = self.create('current', protocol)['data']['root']
        changed = copy.deepcopy(root)
        changed['protocol']['sourcePackages']['resident']['modules'][0]['source'] += '\n# other revision\n'
        reply = self.call({'op': 'invoke', 'object': 'current', 'expected': changed, 'command': 'light', 'input': {}})
        self.assertEqual(reply['kind'], 'refused')
        self.assertEqual(self.root('current'), root)


if __name__ == '__main__': unittest.main()
