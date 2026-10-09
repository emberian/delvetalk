"""Actual source guards see canonical input/state; receipts retain physical input."""
import copy
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
import world
from conformance.test_obend_data_object import SOURCE

POLICY = '''edition ObjectiveBend 1
import ./Preparation.obend as P
record Child:
  key: String
  label: String
  object: String
  panel: String
sum Children:
  nil: {}
  cons: {head: Child, tail: Children}
record State:
  entries: Children
record AddInput:
  object: String
sum Commands:
  add: AddInput
sum OperationInput:
  none: {}
  invoke: Commands
record Facts:
  object: String
  principal: String
  op: String
  command: String
  state: State
  input: OperationInput
record CandidateFacts:
  object: String
  principal: String
  op: String
  command: String
  state: State
  input: OperationInput
  nextState: State
def inputAllowed(input: OperationInput, forbidden: String) -> Bool:
  match input:
    case none(_): true
    case invoke(command):
      match command:
        case add(value): value.object != forbidden
def allowed(input: OperationInput, config: P.Value) -> Bool:
  match P.asText(config):
    case missing(_): false
    case wrongKind(_): false
    case found(forbidden): inputAllowed(input, forbidden.value)
def guard(facts: Facts, config: P.Value) -> Bool:
  (facts.op == "create" || facts.op == "law" || facts.op == "invoke") && allowed(facts.input, config)
def invariant(facts: CandidateFacts, config: P.Value) -> Bool:
  (facts.op == "create" || facts.op == "law" || facts.op == "invoke") && allowed(facts.input, config)
'''


def policy(entry, config):
    return {'package': {'modules': [
        {'name': 'List', 'source': (ROOT / 'world/lib/prelude/List.obend').read_text()},
        {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
        {'name': 'CompactPolicy', 'source': POLICY}], 'entry': entry}, 'config': config}


class CompactPolicy(unittest.TestCase):
    def test_canonical_guards_exact_physical_retry_and_stale_root(self):
        adapter = source_object.adapter
        modules = [{'name': 'Shelf', 'source': SOURCE}]
        program = source_object.load(modules, syntax='objective-bend-object')
        artifact = adapter._native({'op': 'compile', 'modules': modules, 'entry': 'add',
                                    'limits': adapter.LIMITS}, time.monotonic() + 30)['artifact']
        authority = {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker']},
                     'reprogram': ['maker'], 'law': ['maker'],
                     'predicate': policy('guard', 'forbidden'), 'invariant': policy('invariant', 'blocked')}
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'world.json'
            expected_state = None
            for codec in ('plain', 'data', 'compact'):
                selected = copy.deepcopy(program)
                if codec != 'plain':
                    selected['commands']['add']['transition']['inputCodec'] = codec
                created = world.exchange(database, {'op': 'create', 'object': codec, 'principal': 'maker',
                    'intent': codec + '-create', 'protocol': selected, 'law': authority}, profile='compiled')
                self.assertEqual(created['kind'], 'committed', created)
                initial = created['data']['root']
                current = initial
                saved = None
                for text, expected in [('ok', 'committed'), ('forbidden', 'refused'), ('blocked', 'refused')]:
                    value = source_object.data({'object': text})
                    physical = {'object': text} if codec == 'plain' else value
                    if codec == 'compact':
                        encoded = adapter._native({'op': 'encode-compact', 'selection': {
                            'artifact': artifact, 'path': ['codomain', 'domain']}, 'value': value},
                            time.monotonic() + 30)
                        physical = {'schemaPacketSha256': artifact['packetSha256'], 'value': encoded['value']}
                    request = {'op': 'invoke', 'object': codec, 'principal': 'maker',
                        'intent': codec + '-' + text, 'command': 'add', 'expected': current, 'input': physical}
                    reply = world.exchange(database, request, profile='compiled')
                    self.assertEqual(reply['kind'], expected, reply)
                    if expected == 'committed':
                        current = reply['data']['root']
                        saved = (request, reply)
                    else:
                        self.assertEqual(world.query(database, {'op': 'inspect', 'object': codec,
                            'principal': 'maker'}) , current)
                self.assertEqual(current['state']['model']['format'], 'delvetalk-compact-state')
                materialized = source_object.state_data(current)
                if expected_state is None:
                    expected_state = materialized
                self.assertEqual(materialized, expected_state)
                stale = {**saved[0], 'intent': codec + '-stale', 'expected': initial}
                stale_reply = world.exchange(database, stale, profile='compiled')
                self.assertEqual(stale_reply['kind'], 'refused', stale_reply)
                self.assertIn('stale read root', str(stale_reply))
                lock = copy.deepcopy(authority)
                lock['invoke'] = {}
                changed = world.exchange(database, {'op': 'law', 'object': codec, 'principal': 'maker',
                    'intent': codec + '-lock', 'expected': current, 'law': lock}, profile='compiled')
                self.assertEqual(changed['kind'], 'committed', changed)
                self.assertEqual(world.exchange(database, saved[0], profile='compiled'), saved[1])
                stale = {**saved[0], 'intent': codec + '-fresh', 'expected': changed['data']['root']}
                self.assertEqual(world.exchange(database, stale, profile='compiled')['kind'], 'refused')
                retained = world.retained_reply(database, saved[0])
                self.assertEqual(retained, saved[1])
                altered = copy.deepcopy(saved[0])
                altered['input'] = source_object.data({'object': 'ok'}) if codec == 'compact' else {'value': 'ok'}
                self.assertIsNone(world.retained_reply(database, altered))


if __name__ == '__main__':
    unittest.main()
