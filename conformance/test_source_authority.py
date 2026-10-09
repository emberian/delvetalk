"""Configured IDs are typed; source owns roles, visibility, and lockout."""
import json
import os
from pathlib import Path
import subprocess
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import source_closure
import source_object

class SourceAuthority(unittest.TestCase):
    def native(self, request):
        binary = Path(os.environ.get('DELVETALK_PACKAGE_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))
        result = subprocess.run([binary], input=json.dumps(request) + '\n', text=True,
                                capture_output=True, timeout=30, check=True)
        return json.loads(result.stdout)

    def test_application_roles_and_explicit_visibility(self):
        allowed = dict(source_closure.LIBRARY)
        allowed.update({'Editor': 'protocols/editor/Editor.obend', 'Commons': 'protocols/commons/Commons.obend',
                        'Factory': 'protocols/editor/Factory.obend', 'Creation': 'protocols/factories/Creation.obend',
                        'ObjectFactory': 'protocols/town-forge/ObjectFactory.obend',
                        'Required': 'conformance/fixtures/authority/Required.obend'})
        binary = Path(os.environ.get('DELVETALK_PACKAGE_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))
        modules = source_closure.read(['Required'], list(allowed.items()),
            parser=lambda modules: source_closure.native_imports(modules, runner=binary))
        compiled = self.native({'op': 'compile', 'modules': modules, 'entry': 'checks'})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        result = self.native({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertEqual(result['status'], 'finished', result)
        for field in result['value']['fields']:
            with self.subTest(field=field['name']):
                self.assertEqual(field['value'], {'tag': 'boolean', 'value': True})

    def test_configuration_rejects_value_array_instead_of_typed_names(self):
        paths = [('List', 'world/lib/prelude/List.obend'), ('Preparation', 'world/lib/prelude/Preparation.obend'),
                 ('Authority', 'world/lib/prelude/Authority.obend')]
        compiled = self.native({'op': 'compile', 'modules': [{'name': name, 'source': (ROOT / path).read_text()}
            for name, path in paths], 'entry': 'configured'})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        fields = {name: source_object.list_data([]) for name in
                  ('commands', 'participants', 'managers', 'stewards', 'publicPanels')}
        fields['participants'] = source_object.value(['maker'])
        result = self.native({'op': 'run-data-v1', 'artifact': compiled['artifact'],
                              'arguments': [source_object.record(fields)]})
        self.assertNotEqual(result['status'], 'finished', result)
