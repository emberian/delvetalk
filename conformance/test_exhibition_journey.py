#!/usr/bin/env python3
"""Real exhibition composition: source desk, queue, forms, consent and replay."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'protocols/shared-exhibition'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class ExhibitionSource(unittest.TestCase):
    def test_readable_authoring_matches_all_installed_source_files(self):
        author = module('exhibition_author', PACKAGE / 'generate.py')
        for name, expected in [('protocol.json', author.build()),
                               ('migration.json', author.build()['initial']),
                               ('scenarios.json', author.scenarios())]:
            self.assertEqual(json.loads((PACKAGE / name).read_text()), expected)


@unittest.skipUnless((ROOT / '.lake/build/bin/delvetalk-transactions').is_file()
                     and (ROOT / '.lake/build/bin/delvetalk-world').is_file(),
                     'requires prebuilt local transactions and projection hosts')
class ExhibitionJourney(unittest.TestCase):
    def test_three_roles_build_inhabit_and_export_their_exact_world(self):
        journey = module('exhibition_journey', PACKAGE / 'run.py')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'exhibition'
            result = journey.run(directory)
            self.assertTrue(result['state']['opened'])
            self.assertEqual(result['version'], 7)
            self.assertEqual(result['verification']['status'], 'verified-offline')
            self.assertEqual(result['verification']['objects'], 2)
            self.assertEqual(result['verification']['proofScope'], 'exact-artifact-replay')
            snapshot = json.loads((directory / 'world.json').read_text())
            refused = [item for item in snapshot['receipts'] if item['receipt']['kind'] == 'refused']
            self.assertEqual(len(refused), 5)
            self.assertEqual(result['continuation']['admissions'], len(snapshot['receipts']))
            build = next((directory / 'artifacts/builds').glob('*.json'))
            report = json.loads(build.read_text())['report']
            self.assertTrue(report['passed'])
            # Typed copied tokens rejected before admission leave private custody,
            # but they are deliberately absent from semantic admission history.
            events = [json.loads(path.read_text()) for path in (directory / 'events').glob('*.json')]
            malformed = next(item for item in events if item['event'] == 'typed-token-rejects-boolean-nat')
            self.assertEqual(malformed['result']['status'], 'clarify')


if __name__ == '__main__':
    unittest.main()
