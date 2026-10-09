"""Explicit typed menu framing and real source evaluation; no guessed state catalogue."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import history
import translate
from conformance.test_obend_data_object import SOURCE

spec = importlib.util.spec_from_file_location('typed_projection', ROOT / 'scene/projection.py')
projection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(projection)


def wire(value):
    if isinstance(value, str): return {'tag': 'label', 'value': value}
    if type(value) is bool: return {'tag': 'boolean', 'value': value}
    if type(value) is int: return {'tag': 'natural', 'value': str(value)}
    return {'tag': 'record', 'fields': [{'name': name, 'value': wire(child)} for name, child in value.items()]}


def sequence(entries):
    tail = {'tag': 'variant', 'label': 'nil', 'payload': wire({})}
    for entry in reversed(entries):
        tail = {'tag': 'variant', 'label': 'cons', 'payload': {'tag': 'record', 'fields': [
            {'name': 'head', 'value': wire(entry)}, {'name': 'tail', 'value': tail}]}}
    return tail


def observation(entries):
    """Framing-only observation fixture; native evaluations are tested separately."""
    raw = wire({'title': 'The gallery', 'prose': 'Look around.', 'actions': {}})
    raw['fields'].append({'name': 'children', 'value': sequence(entries)})
    root = {'protocol': {'commands': {}, 'viewProgram': {'profile': projection.DATA_MENU_PROFILE}},
            'state': {}, 'law': [], 'version': 0}
    data, children = projection._typed_menu(raw, root)
    return {'mode': 'projection', 'root': root, 'rawData': raw, 'data': data,
            'actions': copy.deepcopy(data['actions']), 'children': children}


class TypedViewFraming(unittest.TestCase):
    def setUp(self):
        self.child = {'key': 'lantern', 'label': 'Lantern <&>', 'object': 'objects/lantern', 'panel': 'main'}
        self.view = observation([self.child])

    def test_roundtrip_exact_typed_children_and_no_legacy_guessing(self):
        self.assertEqual(projection.children(self.view), [self.child])
        saved = json.loads(json.dumps(self.view, sort_keys=True))
        self.assertEqual(projection.children(saved), [self.child])
        self.assertEqual(projection.child(saved, 'lantern'), self.child)
        projected = projection.children(saved)
        projected[0]['label'] = 'mutated copy'
        self.assertEqual(projection.child(saved, 'lantern')['label'], 'Lantern <&>')
        legacy = {'root': {'protocol': {}}, 'state': {'tag': 'variant', 'label': 'cons', 'payload': self.child}}
        self.assertEqual(projection.children(legacy), [])
        self.assertNotIn('children', legacy)
        legacy['children'] = [self.child]
        with self.assertRaisesRegex(projection.ProjectionError, 'explicit typed'):
            projection.children(legacy)

    def test_malformed_variants_rows_and_hidden_actions_refuse(self):
        variants = [wire({}), {'tag': 'variant', 'label': 'other', 'payload': wire({})},
                    {'tag': 'variant', 'label': 'nil', 'payload': wire({'extra': ''})},
                    {'tag': 'variant', 'label': 'cons', 'payload': wire({'head': self.child})}]
        for value in variants:
            view = copy.deepcopy(self.view)
            view['rawData']['fields'][-1]['value'] = value
            with self.subTest(value=value), self.assertRaises(projection.ProjectionError):
                projection.children(view)
        for extra in ({'name': 'children', 'value': sequence([])}, {'name': 'unknown', 'value': wire('')}):
            view = copy.deepcopy(self.view)
            view['rawData']['fields'].append(extra)
            with self.assertRaises(projection.ProjectionError): projection.children(view)
        view = copy.deepcopy(self.view)
        view['rawData']['fields'][2]['value'] = wire({'hidden': {
            'visible': False, 'text': 'Hidden', 'command': 'nonexistent', 'input': {}}})
        with self.assertRaisesRegex(projection.ProjectionError, 'absent command'):
            projection.children(view)

    def test_bounds_are_utf8_and_never_truncate(self):
        good = {**self.child, 'key': 'é' * 64, 'label': 'é' * 128, 'object': 'é' * 256, 'panel': 'é' * 64}
        self.assertEqual(projection.children(observation([good])), [good])
        for field in good:
            with self.subTest(field=field), self.assertRaises(projection.ProjectionError):
                observation([{**good, field: good[field] + 'é'}])
        with self.assertRaisesRegex(projection.ProjectionError, 'duplicate child'):
            observation([self.child, self.child])
        entries = [{**self.child, 'key': str(i)} for i in range(32)]
        self.assertEqual(len(projection.children(observation(entries))), 32)
        with self.assertRaisesRegex(projection.ProjectionError, '32'):
            observation(entries + [{**self.child, 'key': '33'}])
        with self.assertRaises(projection.ProjectionError): observation([{**self.child, 'command': 'invoke'}])

    def test_retained_forgery_and_undeclared_panels_refuse(self):
        for name in ('children', 'data', 'actions'):
            view = copy.deepcopy(self.view)
            view[name] = [] if name != 'children' else [{**self.child, 'object': 'different'}]
            with self.subTest(name=name), self.assertRaisesRegex(projection.ProjectionError, 'differs'):
                projection.children(view)
        root = {'protocol': {'viewProgram': {}, 'viewPanels': [{'id': 'labels', 'label': 'Labels'}]}}
        projection.validate_panel(root, 'main')
        projection.validate_panel(root, 'labels')
        with self.assertRaisesRegex(projection.ProjectionError, 'not declared'):
            projection.validate_panel(root, 'invented')
        root['protocol']['viewPanels'].append({'id': 'labels', 'label': 'Duplicate'})
        with self.assertRaisesRegex(projection.ProjectionError, 'duplicate'):
            projection.validate_panel(root, 'main')


class SourceTableFraming(unittest.TestCase):
    def test_projection_keeps_selector_and_own_table_for_native_resolution(self):
        view = observation([])
        package = projection.source_packages.selector('view')
        table = projection.source_packages.table([{'name': 'Gallery', 'source': 'exact source bytes'}])
        root = view['root']
        root['protocol']['viewProgram']['package'] = package
        root['protocol']['sourcePackages'] = {'resident': table}
        root['state'] = {'model': wire({})}
        binary = '.lake/build/bin/' + projection.runtime_profile.PROFILES['compiled'][0]
        pins = {binary: 'a' * 64}
        response = {'reply': {'kind': 'committed', 'data': {'result': view['rawData']}}}
        process = Mock(returncode=0, stdout=projection.world.wire_dumps(response))
        with patch.object(projection.runtime_profile, 'file_hashes', return_value=pins), \
                patch.object(projection.subprocess, 'run', return_value=process) as run:
            actual = projection.project(root, 'gallery')
        job = projection.world.wire_loads(run.call_args.kwargs['input'])
        synthetic = job['world']['objects']['projection']['protocol']
        self.assertEqual(synthetic['sourcePackages'], root['protocol']['sourcePackages'])
        expression = synthetic['commands']['project']['result']
        self.assertEqual(expression[:2], ['package-data-v1', package])
        self.assertNotIn('modules', expression[1])
        self.assertEqual(actual['source']['package'], package)
        self.assertEqual(actual['root'], root)
        self.assertIn('exact source bytes', projection.html_view(actual))

    def test_malformed_table_selector_refuses_before_execution(self):
        root = observation([])['root']
        root['state'] = {'model': wire({})}
        root['protocol']['viewProgram']['package'] = {
            **projection.source_packages.selector('view'), 'modules': []}
        with patch.object(projection.subprocess, 'run') as run:
            with self.assertRaisesRegex(projection.ProjectionError, 'selector'):
                projection.project(root, 'gallery')
            run.assert_not_called()


class NativeTypedViews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = translate.translate('objective-bend-spell@3', SOURCE.encode())['lowered']

    def test_real_typed_state_source_children_and_captured_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / 'world.json'
            call = lambda request: projection.world.exchange(database, request, profile='compiled')
            made = call({'op': 'create', 'object': 'shelf', 'principal': 'maker', 'intent': 'create',
                         'protocol': self.protocol, 'law': ['maker']})
            self.assertEqual(made['kind'], 'committed', made)
            root = made['data']['root']
            runtime = history.runtime('compiled')
            initial = projection.project(root, 'shelf', expected_runtime=runtime)
            self.assertEqual(projection.children(initial), [])
            for index, target in enumerate(('lantern', 'garden')):
                reply = call({'op': 'invoke', 'object': 'shelf', 'principal': 'maker', 'intent': str(index),
                    'expected': root, 'command': 'add', 'input': {'object': target}})
                self.assertEqual(reply['kind'], 'committed', reply)
                root = reply['data']['root']
            before = database.read_bytes()
            view = projection.project(root, 'shelf', expected_runtime=runtime)
            self.assertEqual([item['object'] for item in projection.children(view)], ['garden', 'lantern'])
            self.assertEqual(database.read_bytes(), before)
            self.assertEqual(projection.children(initial), [])
            self.assertEqual(set(view['data']), {'title', 'prose', 'actions'})
            self.assertEqual(view['source']['package'], projection.source_packages.selector('view'))
            self.assertEqual(view['root']['protocol']['sourcePackages']['resident']['modules'][0]['source'], SOURCE)
            projection.assert_runtime(view, runtime)
            request = projection.request(view, 'add', 'maker', 'retained')
            self.assertEqual(request['expected'], root)
            bad = copy.deepcopy(root)
            bad['state']['extra'] = False
            with self.assertRaisesRegex(projection.ProjectionError, 'exactly model'):
                projection.project(bad, 'shelf', expected_runtime=runtime)


if __name__ == '__main__': unittest.main()
