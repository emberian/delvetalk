"""Current law guards admit actual typed source writes under one native ledger."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
import world
from conformance.test_obend_data_object import SOURCE

POLICY = '''edition ObjectiveBend 1
import ./Preparation.obend as P
def invariant(facts: P.Value, config: P.Value) -> Bool:
  match P.textField(facts, "op"):
    case missing(_): false
    case wrongKind(_): false
    case found(op):
      if op.value == "create" || op.value == "law" then true else if op.value == "invoke" then
        match P.lookupField(facts, "input"):
          case missing(_): false
          case wrongKind(_): false
          case found(input):
            match P.asText(config):
              case missing(_): false
              case wrongKind(_): false
              case found(expected):
                match P.textField(input.value, "object"):
                  case missing(_): false
                  case wrongKind(_): false
                  case found(actual): actual.value != expected.value
      else false
def predicate(facts: P.Value, config: P.Value) -> Bool:
  match P.asText(config):
    case missing(_): false
    case wrongKind(_): false
    case found(expected):
      match P.textField(facts, "principal"):
        case missing(_): false
        case wrongKind(_): false
        case found(actual): actual.value != expected.value
def refuse(facts: P.Value, config: P.Value) -> Bool:
  false
def wrong(facts: P.Value, config: P.Value) -> Nat:
  1n
'''


def policy(entry, config):
    return {'package': {'modules': [
        {'name': 'List', 'source': (ROOT / 'world/lib/prelude/List.obend').read_text()},
        {'name': 'List', 'source': (ROOT / 'world/lib/prelude/List.obend').read_text()}, {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
        {'name': 'Policy', 'source': POLICY}], 'entry': entry}, 'config': config}


class CurrentBoundary(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'world.json'
        self.serial = 0
        self.program = source_object.load([{'name': 'Shelf', 'source': SOURCE}], syntax='objective-bend-object')
        self.authority = {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker', 'forbidden']},
                          'reprogram': ['maker'], 'law': ['maker'],
                          'predicate': policy('predicate', 'forbidden'),
                          'invariant': policy('invariant', 'blocked')}

    def call(self, request):
        self.serial += 1
        return world.exchange(self.database, {'intent': str(self.serial), 'principal': 'maker', **request}, profile='compiled')

    def seed(self, authority=None):
        reply = self.call({'op': 'create', 'object': 'shelf', 'protocol': self.program,
                           'law': self.authority if authority is None else authority})
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply['data']['root']

    def root(self):
        return world.query(self.database, {'op': 'inspect', 'object': 'shelf', 'principal': 'maker'})

    def test_typed_state_guards_retry_current_authority_and_programming(self):
        root = self.seed()
        request = {'intent': 'retained', 'principal': 'maker', 'op': 'invoke', 'object': 'shelf',
                   'command': 'add', 'expected': root, 'input': {'object': 'ok'}}
        committed = self.call(request)
        self.assertEqual(committed['kind'], 'committed', committed)
        current = committed['data']['root']
        for principal, target in [('maker', 'blocked'), ('forbidden', 'ok')]:
            refused = self.call({**request, 'intent': principal, 'principal': principal,
                                 'expected': current, 'input': {'object': target}})
            self.assertEqual(refused['kind'], 'refused', refused)
            self.assertEqual(self.root(), current)
        refused = self.call({'op': 'reprogram', 'object': 'shelf', 'expected': current,
                             'protocol': self.program, 'state': current['state']})
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(self.root(), current)
        proposed = copy.deepcopy(self.authority)
        proposed['invariant'] = policy('refuse', '')
        refused = self.call({'op': 'law', 'object': 'shelf', 'expected': current, 'law': proposed})
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(self.root(), current)
        locked = copy.deepcopy(self.authority)
        locked['invoke'] = {}
        changed = self.call({'op': 'law', 'object': 'shelf', 'expected': current, 'law': locked})
        self.assertEqual(changed['kind'], 'committed', changed)
        self.assertEqual(self.call(request), committed)
        refused = self.call({**request, 'intent': 'new', 'expected': changed['data']['root']})
        self.assertEqual(refused['kind'], 'refused', refused)

    def test_guard_shape_and_result_kind_fail_closed(self):
        for entry in ('refuse', 'wrong'):
            authority = copy.deepcopy(self.authority)
            authority['invariant'] = policy(entry, '')
            reply = self.call({'op': 'create', 'object': entry, 'protocol': self.program, 'law': authority})
            self.assertEqual(reply['kind'], 'refused', reply)
        malformed = copy.deepcopy(self.authority)
        malformed['invariant']['extra'] = True
        reply = self.call({'op': 'create', 'object': 'malformed', 'protocol': self.program, 'law': malformed})
        self.assertEqual(reply['kind'], 'refused', reply)


if __name__ == '__main__':
    unittest.main()
