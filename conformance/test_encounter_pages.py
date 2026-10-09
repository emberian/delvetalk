"""Source-owned paged encounters, including a persisted native object/view journey."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from conformance.bench_source_collections import PAGE_MODULES, child, child_keys, fields, natural, page_keys, pages, text
import resident_store


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


adapter = load('pages_adapter', 'syntaxes/obend_object.py')
projection = load('pages_projection', 'scene/projection.py')
BINARY = ROOT / '.lake/build/bin/delvetalk-obend'


def call(request):
    result = subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
                            text=True, capture_output=True, timeout=30, check=True)
    return json.loads(result.stdout)


def gallery_modules():
    return [{'name': name, 'source': (ROOT / 'world/lib/prelude' / (name + '.obend')).read_text()}
            for name in ('List', 'Abi', 'Encounter', 'EncounterPages')] + [
                {'name': 'PageGallery', 'source': (ROOT / 'world/lib/prelude/examples/PageGallery.obend').read_text()}]


class EncounterPagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        modules = [{'name': name, 'source': (ROOT / path).read_text()} for name, path in PAGE_MODULES.items()]
        cls.artifacts = {}
        for entry in ('add', 'remove', 'listing', 'select', 'count'):
            result = call({'op': 'compile', 'modules': modules, 'entry': entry})
            assert result['status'] == 'compiled', result
            cls.artifacts[entry] = result['artifact']

    def run_source(self, entry, *arguments):
        result = call({'op': 'run-data-v1', 'artifact': self.artifacts[entry], 'arguments': list(arguments)})
        self.assertEqual(result['status'], 'finished', result)
        return result['value']

    def test_200_entry_roundtrip_duplicate_capacity_and_all_pages(self):
        state = pages(200)
        self.assertEqual(self.run_source('count', state), natural(200))
        self.assertEqual(self.run_source('select', state, text('k199'))['value'], True)
        listed = []
        for index in range(13):
            listed += child_keys(self.run_source('listing', state, natural(index)))
        self.assertEqual(listed, [f'k{i}' for i in range(200)])
        self.assertEqual(child_keys(self.run_source('listing', state, natural(13))), [])
        for extra, capacity, accepted in ((child(200), 201, True), (child(200), 200, False), (child(199), 201, False)):
            result = fields(self.run_source('add', state, extra, natural(capacity)))
            self.assertEqual(result['accepted']['value'], accepted)
            self.assertEqual(page_keys(result['pages']), listed + (['k200'] if accepted else []))
        removed = self.run_source('remove', state, text('k0'))
        self.assertEqual(page_keys(removed), listed[1:])
        self.assertEqual(self.run_source('remove', state, text('missing')), state)

    def test_remove_empty_page_and_append_preserve_order(self):
        state = pages(17)
        # Removing the singleton final page drops it. Removing the entire first
        # page promotes the remaining page without retaining an empty bucket.
        self.assertEqual(page_keys(self.run_source('remove', state, text('k16'))), [f'k{i}' for i in range(16)])
        for index in range(16):
            state = self.run_source('remove', state, text(f'k{index}'))
        self.assertEqual(page_keys(state), ['k16'])
        result = fields(self.run_source('add', state, child(17), natural(200)))
        self.assertEqual(child_keys(fields(result['pages']['payload'])['items']), ['k16', 'k17'])

    def test_gallery_persists_pages_projects_and_retries_after_restart(self):
        protocol = adapter.lower_data_modules(gallery_modules())
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'gallery.sqlite'
            with resident_store.Resident(database) as receiver:
                created = receiver.exchange({'op': 'create', 'object': 'gallery', 'principal': 'keeper',
                    'intent': 'create', 'protocol': protocol, 'law': ['keeper']})
                self.assertEqual(created['kind'], 'committed', created)
                root = created['data']['root']
                def invoke(command, value, intent, expected=None, kind='committed'):
                    nonlocal root
                    request = {'op': 'invoke', 'object': 'gallery', 'principal': 'keeper', 'intent': intent,
                        'expected': root if expected is None else expected, 'command': command, 'input': value}
                    reply = receiver.exchange(request)
                    self.assertEqual(reply['kind'], kind, reply)
                    root = receiver.exchange({'op': 'inspect', 'object': 'gallery', 'principal': 'reader'})
                    return request, reply
                for i in range(17):
                    invoke('offer', {'key': f'k{i}', 'label': f'Exhibit {i}', 'object': f'o{i}', 'panel': 'main'}, f'offer-{i}')
                first = projection.project(root, 'gallery')
                self.assertEqual(len(first['children']), 16)
                self.assertEqual(first['children'][0]['object'], 'o0')
                self.assertEqual(first['actions']['next']['input'], {'index': 1})
                self.assertNotIn('previous', first['actions'])
                before = root
                request, receipt = invoke('page', {'index': 1}, 'page-1')
                second = projection.project(root, 'gallery')
                self.assertEqual([item['object'] for item in second['children']], ['o16'])
                self.assertEqual(second['actions']['previous']['input'], {'index': 0})
                self.assertNotIn('next', second['actions'])
                invoke('page', {'index': 7}, 'bad-page', kind='refused')
                invoke('offer', {'key': 'k16', 'label': 'Again', 'object': 'other', 'panel': 'main'}, 'duplicate', kind='refused')
                invoke('page', {'index': 0}, 'stale', expected=before, kind='refused')
                receiver.checkpoint()
            with resident_store.Resident(database) as receiver:
                self.assertEqual(receiver.exchange(request), receipt)
                restored = receiver.exchange({'op': 'inspect', 'object': 'gallery', 'principal': 'reader'})
                self.assertEqual(restored, root)
                self.assertEqual([item['object'] for item in projection.project(restored, 'gallery')['children']], ['o16'])
                self.assertEqual(len(page_keys(fields(restored['state']['model'])['pages'])), 17)


if __name__ == '__main__': unittest.main()
