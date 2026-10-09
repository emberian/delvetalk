"""Actual source chains whose equivalent row types have different presentations."""
import json
from native_support import load_script
import tempfile
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / '.lake/build/bin/delvetalk-obend'
SOURCE = '''edition ObjectiveBend 1
record Sections:
  heading: String -> String
  examples: String -> String
  body: String -> String
extension Base(self: Sections, super: {}) -> Sections:
  {heading: fn(s: String) -> String: s, examples: fn(s: String) -> String: s, body: fn(s: String) -> String: self.heading(s)}
extension Workshop[Self has {heading: String -> String, examples: String -> String, body: String -> String}, Super has {heading: String -> String, examples: String -> String, body: String -> String}](self: Self, super: Super) -> Super with {heading: String -> String, examples: String -> String}:
  extend(super, {heading: fn(s: String) -> String: textConcat("Workshop ", super.heading(s)), examples: fn(s: String) -> String: super.examples(s)})
def sections() -> Sections:
  fix(compose(Base, Workshop), {})
def entry() -> String:
  sections().body("moth")
def throughConditional() -> String:
  let value = if false then sections() else fix(compose(Base, Workshop), {}) in value.body("moon")
'''


def call(request):
    return json.loads(subprocess.run([str(BINARY)], input=json.dumps(request) + '\n',
        capture_output=True, text=True, timeout=30, check=True).stdout)


class OpenRowComposition(unittest.TestCase):
    def test_noncanonical_closed_and_open_closure_layers_execute(self):
        for entry, expected in [('entry', 'Workshop moth'), ('throughConditional', 'Workshop moon')]:
            compiled = call({'op': 'compile', 'source': SOURCE, 'entry': entry})
            self.assertEqual(compiled['status'], 'compiled', compiled)
            result = call({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
            self.assertEqual(result.get('value'), {'tag': 'label', 'value': expected}, result)

    def test_receiving_host_admits_and_replays_composed_source(self):
        world = load_script(ROOT / 'scripts/world.py', 'open_row_world')
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'world.json'
            protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'render': {
                'require': [], 'set': {}, 'outbox': [], 'result': ['package', {
                    'modules': [{'name': 'Sections', 'source': SOURCE}], 'entry': 'entry'}, []]}}}
            made = world.exchange(database, {'op': 'create', 'object': 'workshop', 'principal': 'maker',
                'intent': 'make', 'protocol': protocol, 'law': ['maker']}, profile='compiled')
            self.assertEqual(made['kind'], 'committed', made)
            request = {'op': 'invoke', 'object': 'workshop', 'principal': 'maker', 'intent': 'render',
                'expected': made['data']['root'], 'command': 'render', 'input': {}}
            receipt = world.exchange(database, request, profile='compiled')
            self.assertEqual(receipt['kind'], 'committed', receipt)
            self.assertEqual(receipt['data']['result'], 'Workshop moth')
            self.assertEqual(world.exchange(database, request, profile='compiled'), receipt)

    def test_missing_bounds_wrong_member_types_and_restricted_capture_refuse(self):
        for source in [SOURCE.replace('heading: String -> String, examples:', 'missing: Nat, heading: String -> String, examples:'),
                       SOURCE.replace('textConcat("Workshop ", super.heading(s))', '7n'),
                       SOURCE.replace('fn(s: String) -> String: textConcat', 'fn(affine s: String) -> String: textConcat')]:
            result = call({'op': 'compile', 'source': source, 'entry': 'entry'})
            self.assertEqual(result['status'], 'error', result)


if __name__ == '__main__': unittest.main()
