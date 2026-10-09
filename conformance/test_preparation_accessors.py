"""Required source fields preserve missing/wrong-kind and real zero/false values."""
import json
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RequiredAccessors(unittest.TestCase):
    def checks(self, paths):
        self.checks_modules([{'name': name, 'source': (ROOT / path).read_text()} for name, path in paths])

    def checks_modules(self, source_modules):
        def native(request):
            done = subprocess.run([Path(os.environ.get('DELVETALK_PACKAGE_BINARY', ROOT / '.lake/build/bin/delvetalk-obend'))],
                input=json.dumps(request) + '\n', text=True, capture_output=True,
                check=True, timeout=15)
            return json.loads(done.stdout)
        compiled = native({'op': 'compile', 'modules': source_modules,
            'entry': 'checks'})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        result = native({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertEqual(result['status'], 'finished', result)
        for field in result['value']['fields']:
            with self.subTest(check=field['name']):
                self.assertEqual(field['value'], {'tag': 'boolean', 'value': True})

    def test_native_required_values_and_actual_candidate_consumer(self):
        paths = [('Abi', 'world/lib/prelude/Abi.obend'),
                 ('List', 'world/lib/prelude/List.obend'), ('Preparation', 'world/lib/prelude/Preparation.obend'),
                 ('Encounter', 'world/lib/prelude/Encounter.obend'),
                 ('Document', 'world/lib/document/Document.obend'),
                 ('Candidate', 'protocols/editor/Candidate.obend'),
                 ('Interpretation', 'protocols/interpretation/Interpretation.obend'),
                 ('GrantPolicy', 'protocols/membership/GrantPolicy.obend'),
                 ('Welcome', 'protocols/membership/Welcome.obend'),
                 ('Required', 'conformance/fixtures/preparation/Required.obend')]
        self.checks(paths)

    def test_configured_offered_reference_and_required_observation(self):
        from conformance.test_document_conversation import modules
        # Retain the exact shared modules, replacing only the entry with the fixture.
        source_modules = modules()[:-1]
        self.checks_modules(source_modules + [{"name": "ConfiguredNotebook", "source": (ROOT / "conformance/fixtures/preparation/ConfiguredNotebook.obend").read_text()}])
