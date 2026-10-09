"""Sealed shared source collections run through the actual Bend compiler/machine."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / '.lake/build/bin/delvetalk-obend'
SOURCE = (ROOT / 'world/lib/prelude/examples/Shelf.obend').read_text()


def call(request):
    return json.loads(subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
        capture_output=True, text=True, check=True, timeout=20).stdout)


class SourcePreludeTests(unittest.TestCase):
    def test_source_layers_compose_inspect_and_revise_shared_collection(self):
        modules = [{'name': 'List', 'source': (ROOT / 'world/lib/prelude/List.obend').read_text()}, {'name': 'Encounter', 'source': (ROOT / 'world/lib/prelude/Encounter.obend').read_text()},
                   {'name': 'Shelf', 'source': SOURCE}]
        for entry, expected in [('count', 2), ('bounded', 2), ('revised', 1)]:
            compiled = call({'op': 'compile', 'modules': modules, 'entry': entry})
            self.assertEqual(compiled['status'], 'compiled', compiled)
            result = call({'op': 'run', 'artifact': compiled['artifact'], 'arguments': []})
            self.assertEqual(result.get('value'), {'tag': 'natural', 'value': str(expected)}, result)
        missing = call({'op': 'compile', 'modules': modules[1:], 'entry': 'count'})
        self.assertNotEqual(missing['status'], 'compiled')
        self.assertIn('earlier supplied module', str(missing))


if __name__ == '__main__': unittest.main()
