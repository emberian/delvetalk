"""Law-held Bend guards consume typed facts, never serialized DataWire fields."""
import copy
import unittest
from conformance.test_current_source_contract import native, record, nat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '''edition ObjectiveBend 1
record State:
  count: Nat
  enabled: Bool
record AddInput:
  amount: Nat
record ToggleInput:
  enabled: Bool
record Origin:
  kind: String
  object: String
  command: String
  program: String
  immediatelyPrevious: Bool
record Context:
  object: String
  principal: String
  inputOrigin: Origin
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: Nat
def add(state: State, input: AddInput, context: Context) -> Decision:
  {accepted: true, reason: "", state: {count: state.count + input.amount, enabled: state.enabled}, result: state.count}
def toggle(state: State, input: ToggleInput, context: Context) -> Decision:
  {accepted: true, reason: "", state: {count: state.count, enabled: input.enabled}, result: state.count}
'''
GUARD = '''edition ObjectiveBend 1
import ./Preparation.obend as P
record State:
  count: Nat
  enabled: Bool
record AddInput:
  amount: Nat
record ToggleInput:
  enabled: Bool
sum Commands:
  add: AddInput
  toggle: ToggleInput
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
record Candidate:
  object: String
  principal: String
  op: String
  command: String
  state: State
  input: OperationInput
  nextState: State
def exactConfig(config: P.Value) -> Bool:
  match P.get(config, "decimal"):
    case number(n): n.encoded == "125e-2" && P.naturalOrZero(P.get(config, "natural")) == 9007199254740993n && P.booleanOrFalse(P.get(config, "enabled"))
    case _: false
def commandAllowed(facts: Facts) -> Bool:
  match facts.input:
    case none(_): facts.op == "law" || facts.op == "reprogram"
    case invoke(command):
      match command:
        case add(input): facts.command == "add" && input.amount <= 9007199254740993n
        case toggle(input): facts.command == "toggle" && input.enabled
def guard(facts: Facts, config: P.Value) -> Bool:
  exactConfig(config) && commandAllowed(facts)
def invariant(facts: Candidate, config: P.Value) -> Bool:
  exactConfig(config) && facts.nextState.enabled && facts.nextState.count <= 9007199254740993n
'''


def boolean(value):
    return {'tag': 'boolean', 'value': value}


def package(entry):
    return {'modules': [{'name': 'Body', 'source': SOURCE}], 'entry': entry}


def policy(entry):
    return {'package': {'modules': [{'name': n, 'source': (ROOT / ('world/lib/prelude/' + n + '.obend')).read_text()}
                                   for n in ('List', 'Preparation')] + [{'name': 'Guard', 'source': GUARD}],
                        'entry': entry}, 'config': {'decimal': 1.25, 'natural': 9007199254740993, 'enabled': True}}


class LogicalPolicy(unittest.TestCase):
    def setUp(self):
        self.world = {'objects': {}, 'receipts': []}
        self.serial = 0
        self.protocol = {'profile': 'delvetalk-local-v1',
                         'initial': {'model': record(count=nat(0), enabled=boolean(True))},
                         'commands': {name: {'transition': {'profile': 'delvetalk-source-transition',
                                      'package': package(name), 'inputCodec': 'data'}} for name in ('add', 'toggle')}}
        self.law = {'profile': 'delvetalk-scoped-law', 'invoke': {name: ['maker'] for name in ('add', 'toggle', 'unknown')},
                    'reprogram': ['maker'], 'law': ['maker'], 'predicate': policy('guard'), 'invariant': policy('invariant')}

    def call(self, **request):
        self.serial += 1
        response = native('delvetalk-compiled', {'world': self.world,
                          'request': {'principal': 'maker', 'intent': 'logical-' + str(self.serial), **request}})
        self.assertNotIn('error', response, response)
        self.world = response['world']
        return response['reply']

    def seed(self):
        made = self.call(op='create', object='counter', protocol=self.protocol, law=self.law)
        self.assertEqual(made['kind'], 'committed', made)
        return made['data']['root']

    def test_two_actual_input_types_and_administrative_none(self):
        root = self.seed()
        for command, value in [('add', record(amount=nat(9007199254740993))), ('toggle', record(enabled=boolean(True)))]:
            reply = self.call(op='invoke', object='counter', expected=root, command=command, input=value)
            self.assertEqual(reply['kind'], 'committed', reply)
            root = reply['data']['root']
        for op, fields in [('law', {'law': self.law}), ('reprogram', {'protocol': self.protocol, 'state': root['state']})]:
            reply = self.call(op=op, object='counter', expected=root, **fields)
            self.assertEqual(reply['kind'], 'committed', reply)
            root = reply['data']['root']
        refused = self.call(op='invoke', object='counter', expected=root, command='toggle', input=record(enabled=boolean(False)))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(self.world['objects']['counter'], root)

    def test_unknown_method_and_changed_state_schema_fail_closed(self):
        root = self.seed()
        revised = copy.deepcopy(self.protocol)
        revised['commands']['unknown'] = copy.deepcopy(revised['commands']['add'])
        updated = self.call(op='reprogram', object='counter', expected=root, protocol=revised, state=root['state'])
        self.assertEqual(updated['kind'], 'committed', updated)
        root = updated['data']['root']
        refused = self.call(op='invoke', object='counter', expected=root, command='unknown', input=record(amount=nat(1)))
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(self.world['objects']['counter'], root)
        wrong = copy.deepcopy(self.law)
        wrong['invariant']['package']['modules'][-1]['source'] = GUARD.replace('  count: Nat', '  count: String')
        refused = self.call(op='law', object='counter', expected=root, law=wrong)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(self.world['objects']['counter'], root)


if __name__ == '__main__':
    unittest.main()
