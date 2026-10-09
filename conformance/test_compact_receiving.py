"""Canonical source guard parity at batch and retained-message receiving joins."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
import world
from conformance.test_compact_policy import policy, POLICY
from conformance.test_obend_data_object import SOURCE

EVENT = '''record CausalEvent:
  id: String
  source: String
  sourceProgram: String
  originatingPrincipal: String
  root: String
  parent: String
  depth: Nat
  rootPrincipal: String
'''
EMITTER = '''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Preparation.obend as P
import ./Emissions.obend as E
import ./Encounter.obend as Encounter
record State:
  sent: Nat
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: Nat
  emissions: E.Emissions
def send(state: State, input: P.Value, context: Abi.Context) -> Decision:
  {accepted: true, reason: "", state: {sent: state.sent + 1n}, result: state.sent + 1n, emissions: E.one({to: P.textOrEmpty(P.get(input, "to")), command: "add", recipientProgram: P.textOrEmpty(P.get(input, "program")), payload: P.get(input, "payload")})}
record Description:
  name: String
  initial: State
  methods: {send: {label: String, fields: {}, inputCodec: String}}
  panels: {}
def describe() -> Description:
  {name: "Physical envelope emitter", initial: {sent: 0n}, methods: {send: {label: "Send captured envelope", fields: {}, inputCodec: "value"}}, panels: {}}
record View:
  title: String
  prose: String
  actions: {}
  children: Encounter.Children
def view(state: State, panel: String) -> View:
  {title: "Envelope fixture", prose: "Source forwards bounded physical data.", actions: {}, children: Encounter.Children.nil()}
'''


VALUE_RECEIVER = '''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Preparation.obend as P
import ./Encounter.obend as Encounter
record State:
  first: String
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: String
def firstField(input: P.Value) -> String:
  match input:
    case record(r):
      match r.fields:
        case nil(_): ""
        case cons(c): c.head.name
    case _: ""
def add(state: State, input: P.Value, context: Abi.Context) -> Decision:
  {accepted: true, reason: "", state: {first: firstField(input)}, result: firstField(input)}
record Description:
  name: String
  initial: State
  methods: {add: {label: String, fields: {}, inputCodec: String}}
  panels: {}
def describe() -> Description:
  {name: "Native Value receiver", initial: {first: ""}, methods: {add: {label: "Accept Value", fields: {}, inputCodec: "value"}}, panels: {}}
record View:
  title: String
  prose: String
  actions: {}
  children: Encounter.Children
def view(state: State, panel: String) -> View:
  {title: "Value fixture", prose: state.first, actions: {}, children: Encounter.Children.nil()}
'''


class CompactReceiving(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / 'world.json'
        self.serial = 0
        self.adapter = source_object.adapter

    def call(self, request, expected=None):
        reply = world.exchange(self.database, request, profile='compiled')
        if expected:
            self.assertEqual(reply['kind'], expected, reply)
        return reply

    def intent(self):
        self.serial += 1
        return 'join-' + str(self.serial)

    def root(self, identity):
        return world.query(self.database, {'op': 'inspect', 'object': identity, 'principal': 'maker'}, profile='compiled')

    def create(self, identity, program, authority):
        return self.call({'op': 'create', 'object': identity, 'principal': 'maker',
            'intent': self.intent(), 'protocol': program, 'law': authority}, 'committed')['data']['root']

    def selected(self, codec, receiving=False):
        source = SOURCE
        if receiving:
            source = source.replace('record Decision:', EVENT + 'record Decision:')
            source = source.replace('def add(state: State, input: Input, context: Context)',
                                    'def add(state: State, input: Input, context: Context, event: CausalEvent)')
        modules = [{'name': 'Shelf', 'source': source}]
        program = source_object.load(modules, syntax='objective-bend-object')
        program['commands']['add']['transition']['inputCodec'] = codec
        artifact = self.adapter._native({'op': 'compile', 'modules': modules, 'entry': 'add',
            'limits': self.adapter.LIMITS}, time.monotonic() + 30)['artifact']
        authority = {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker']},
            'reprogram': ['maker'], 'law': ['maker'],
            'predicate': policy('guard', 'forbidden'), 'invariant': policy('invariant', 'blocked')}
        return program, artifact, authority

    def physical(self, codec, artifact, text):
        value = source_object.data({'object': text})
        if codec == 'data':
            return value
        encoded = self.adapter._native({'op': 'encode-compact', 'selection': {
            'artifact': artifact, 'path': ['codomain', 'domain']}, 'value': value}, time.monotonic() + 30)
        return {'schemaPacketSha256': artifact['packetSha256'], 'value': encoded['value']}

    def test_batch_guard_body_invariant_parity_and_exact_retry(self):
        for codec in ('data', 'compact'):
            program, artifact, authority = self.selected(codec)
            current = self.create(codec, program, authority)
            initial = current
            saved = None
            for text, expected in (('ok', 'committed'), ('forbidden', 'refused'), ('blocked', 'refused')):
                request = {'op': 'transaction', 'principal': 'maker', 'intent': self.intent(),
                    'reads': {codec: current}, 'calls': [{'object': codec, 'command': 'add',
                    'input': self.physical(codec, artifact, text)}]}
                reply = self.call(request, expected)
                self.assertEqual(self.call(request), reply)
                if expected == 'committed':
                    current = reply['data']['roots'][codec]
                    saved = (request, reply)
                else:
                    self.assertEqual(self.root(codec), current)
            stale = {**saved[0], 'intent': self.intent(), 'reads': {codec: initial}}
            self.assertIn('stale read root', self.call(stale, 'refused')['data'])
            locked = {**authority, 'invoke': {}}
            current = self.call({'op': 'law', 'object': codec, 'principal': 'maker', 'intent': self.intent(),
                'expected': current, 'law': locked}, 'committed')['data']['root']
            self.assertEqual(self.call(saved[0]), saved[1])
            self.call({**saved[0], 'intent': self.intent(), 'reads': {codec: current}}, 'refused')

    def test_native_typed_result_composes_into_compact_recipient_without_display_guessing(self):
        producer_source = SOURCE.replace('  result: String', '  result: Input').replace('result: "Exhibited"', 'result: input')
        producer = source_object.load([{'name': 'Producer', 'source': producer_source}], syntax='objective-bend-object')
        producer['commands']['add']['transition']['inputCodec'] = 'data'
        producer_root = self.create('producer', producer, {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker']}, 'reprogram': ['maker'], 'law': ['maker']})
        program, _, authority = self.selected('compact')
        recipient_root = self.create('recipient', program, authority)
        request = {'op': 'transaction', 'principal': 'maker', 'intent': self.intent(),
            'reads': {'producer': producer_root, 'recipient': recipient_root}, 'calls': [
                {'object': 'producer', 'command': 'add', 'input': source_object.data({'object': 'ok'})},
                {'object': 'recipient', 'command': 'add', 'inputFrom': 0}]}
        reply = self.call(request, 'committed')
        self.assertEqual(self.call(request), reply)
        self.assertEqual(reply['data']['results'], [{'object': 'ok'}, 'Exhibited'])
        # A P.Value can display the same object while retaining a different exact
        # checked semantic type. It cannot impersonate the record producer.
        dynamic_source = SOURCE.replace('edition ObjectiveBend 1\n', 'edition ObjectiveBend 1\nimport ./Preparation.obend as P\n')
        dynamic_source = dynamic_source.replace('  result: String', '  result: P.Value')
        dynamic_source = dynamic_source.replace('result: "Exhibited"', 'result: if input.object == "order" then P.Value.record({fields: P.Fields.cons({head: {name: "shadow", value: P.Value.text({value: "first"})}, tail: P.Fields.cons({head: {name: "object", value: P.Value.text({value: input.object})}, tail: P.Fields.nil()})})}) else P.oneField("object", P.Value.text({value: input.object}))')
        dynamic_source = dynamic_source.replace('  fields: {object: Field}', '  fields: {object: Field}\n  resultCodec: String')
        dynamic_source = dynamic_source.replace('maxLength: 64}}}', 'maxLength: 64}}, resultCodec: "value"}')
        modules = [{'name': name, 'source': (ROOT / 'world/lib/prelude' / (name + '.obend')).read_text()}
                   for name in ('List', 'Preparation')]
        dynamic = source_object.load(modules + [{'name': 'Dynamic', 'source': dynamic_source}], syntax='objective-bend-object')
        dynamic['commands']['add']['transition']['inputCodec'] = 'data'
        dynamic_root = self.create('dynamic', dynamic, {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker']}, 'reprogram': ['maker'], 'law': ['maker']})
        recipient_root = self.root('recipient')
        refused = {'op': 'transaction', 'principal': 'maker', 'intent': self.intent(),
            'reads': {'dynamic': dynamic_root, 'recipient': recipient_root}, 'calls': [
                {'object': 'dynamic', 'command': 'add', 'input': source_object.data({'object': 'ok'})},
                {'object': 'recipient', 'command': 'add', 'inputFrom': 0}]}
        rejection = self.call(refused, 'refused')
        self.assertIn('derived source result type differs', rejection['data'])
        self.assertEqual(self.call(refused), rejection)
        self.assertEqual(self.root('dynamic'), dynamic_root)
        self.assertEqual(self.root('recipient'), recipient_root)
        modules = [{'name': name, 'source': (ROOT / 'world/lib/prelude' / (name + '.obend')).read_text()}
                   for name in ('List', 'Abi', 'Preparation', 'Encounter')]
        value_program = source_object.load(modules + [{'name': 'ValueReceiver', 'source': VALUE_RECEIVER}], syntax='objective-bend-object')
        value_program['commands']['add']['transition']['inputCodec'] = 'compact'
        value_root = self.create('value', value_program, {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker']}, 'reprogram': ['maker'], 'law': ['maker']})
        composed = {'op': 'transaction', 'principal': 'maker', 'intent': self.intent(),
            'reads': {'dynamic': dynamic_root, 'value': value_root}, 'calls': [
                {'object': 'dynamic', 'command': 'add', 'input': source_object.data({'object': 'order'})},
                {'object': 'value', 'command': 'add', 'inputFrom': 0}]}
        accepted = self.call(composed, 'committed')
        self.assertEqual(self.call(composed), accepted)
        self.assertEqual(accepted['data']['results'][0], {'object': 'order', 'shadow': 'first'})
        # Presentation JSON sorts keys; exact native P.Fields retains shadow first.
        self.assertEqual(accepted['data']['results'][1], 'shadow')

    def test_delivery_guard_body_invariant_parity_retains_physical_payload(self):
        self.call({'op': 'messages-init', 'principal': 'maker', 'intent': self.intent(),
            'lineage': 'compact-joins', 'pendingLimit': 32}, 'committed')
        modules = [{'name': name, 'source': (ROOT / 'world/lib/prelude' / (name + '.obend')).read_text()}
                   for name in ('List', 'Abi', 'Preparation', 'Emissions', 'Encounter')]
        sender = source_object.load(modules + [{'name': 'Emitter', 'source': EMITTER}], syntax='objective-bend-object')
        self.create('emitter', sender, {'profile': 'delvetalk-scoped-law', 'invoke': {'send': ['maker']}, 'reprogram': ['maker'], 'law': ['maker']})
        for codec in ('data', 'compact'):
            program, artifact, authority = self.selected(codec, receiving=True)
            current = self.create(codec, program, authority)
            initial = current
            program_id = source_object.values('digest', [program])[0]
            saved = None
            for text, expected in (('ok', 'committed'), ('forbidden', 'refused'), ('blocked', 'refused')):
                physical = self.physical(codec, artifact, text)
                emitted = self.call({'op': 'invoke', 'object': 'emitter', 'principal': 'maker', 'intent': self.intent(),
                    'expected': self.root('emitter'), 'command': 'send',
                    'input': {'to': codec, 'program': program_id, 'payload': physical}}, 'committed')
                event = emitted['data']['messages'][0]
                observed = self.call({'op': 'message-event', 'principal': 'maker', 'event': event})
                self.assertEqual(observed['event']['evidence']['payload'], physical)
                request = {'op': 'deliver', 'object': codec, 'principal': 'maker', 'intent': self.intent(),
                    'expected': current, 'event': event}
                reply = self.call(request, expected)
                self.assertEqual(self.call(request), reply)
                if expected == 'committed':
                    current = reply['data']['root']
                    saved = (request, reply)
                else:
                    self.assertEqual(self.root(codec), current)
                    self.assertEqual(self.call({'op': 'message-event', 'principal': 'maker', 'event': event})['event']['status'], 'pending')
                    stale = {**request, 'intent': self.intent(), 'expected': initial}
                    self.assertIn('stale read root', self.call(stale, 'refused')['data'])
            locked = {**authority, 'invoke': {}}
            current = self.call({'op': 'law', 'object': codec, 'principal': 'maker', 'intent': self.intent(),
                'expected': current, 'law': locked}, 'committed')['data']['root']
            self.assertEqual(self.call(saved[0]), saved[1])
            denied = self.call({**request, 'intent': self.intent(), 'expected': current}, 'refused')
            self.assertIn('unauthorized', denied['data'])


    def test_native_settlement_guards_obsolete_retry_and_caller_marker(self):
        metadata = """record EventRef:
  lineage: String
  id: String
record Causal:
  root: String
  parent: String
  depth: Nat
record Settlement:
  event: EventRef
  reason: String
  source: String
  sourceProgram: String
  originatingPrincipal: String
  causal: Causal
"""
        source = POLICY.replace('sum OperationInput:', metadata + 'sum OperationInput:')
        source = source.replace('facts.op == \"create\" ||', 'facts.op == \"reprogram\" || facts.op == \"create\" ||')
        source = source.replace('  invoke: Commands', '  invoke: Commands\n  settlement: Settlement')
        source = source.replace('case add(value): value.object != forbidden', 'case add(value): false')
        source = source.replace('    case invoke(command):',
            '    case settlement(value): value.reason != forbidden && value.source == "emitter" && value.originatingPrincipal == "maker" && value.event.lineage == "settlement-joins" && value.event.id != "" && value.sourceProgram != "" && value.causal.root != "" && value.causal.parent == "" && value.causal.depth == 0n\n    case invoke(command):')
        def held(entry, forbidden):
            descriptor = policy(entry, forbidden)
            descriptor['package']['modules'][-1]['source'] = source
            return descriptor
        self.call({'op': 'messages-init', 'principal': 'maker', 'intent': self.intent(),
            'lineage': 'settlement-joins', 'pendingLimit': 32}, 'committed')
        modules = [{'name': name, 'source': (ROOT / 'world/lib/prelude' / (name + '.obend')).read_text()}
                   for name in ('List', 'Abi', 'Preparation', 'Emissions', 'Encounter')]
        sender = source_object.load(modules + [{'name': 'Emitter', 'source': EMITTER}], syntax='objective-bend-object')
        self.create('emitter', sender, {'profile': 'delvetalk-scoped-law', 'invoke': {'send': ['maker']}, 'reprogram': ['maker'], 'law': ['maker']})
        program, _, _ = self.selected('data', receiving=True)
        program['commands']['add']['transition'].pop('inputCodec', None)
        authority = {'profile': 'delvetalk-scoped-law', 'invoke': {'add': ['maker'], '$messages-settle': ['maker']},
            'reprogram': ['maker'], 'law': ['maker'], 'predicate': held('guard', 'guard-deny'),
            'invariant': held('invariant', 'invariant-deny')}
        current = self.create('target', program, authority)
        emitted = self.call({'op': 'invoke', 'object': 'emitter', 'principal': 'maker', 'intent': self.intent(),
            'expected': self.root('emitter'), 'command': 'send', 'input': {'to': 'target',
                'program': source_object.values('digest', [program])[0], 'payload': {'object': 'unused'}}}, 'committed')
        event = emitted['data']['messages'][0]
        revised = copy.deepcopy(program)
        revised['revision'] = 'retired-recipient'
        current = self.call({'op': 'reprogram', 'object': 'target', 'principal': 'maker', 'intent': self.intent(),
            'expected': current, 'protocol': revised, 'state': current['state']}, 'committed')['data']['root']
        request = {'op': 'settle-message', 'object': 'target', 'principal': 'maker', 'intent': self.intent(),
            'expected': current, 'event': event, 'reason': 'retired'}
        for reason in ('guard-deny', 'invariant-deny'):
            denied = dict(request, intent=self.intent(), reason=reason)
            reply = self.call(denied, 'refused')
            self.assertIn('source policy refused', reply['data'])
            self.assertEqual(self.call(denied), reply)
            self.assertEqual(self.root('target'), current)
        self.call(dict(request, intent=self.intent(), event=dict(event, forged='metadata')), 'refused')
        self.call(dict(request, intent=self.intent(), reason=''), 'refused')
        ordinary = {'op': 'invoke', 'object': 'target', 'principal': 'maker', 'intent': self.intent(),
            'expected': current, 'command': 'add', 'input': {'object': 'normal'},
            'settlementInput': {'reason': 'retired'}}
        self.assertIn('source policy refused', self.call(ordinary, 'refused')['data'])
        self.assertEqual(self.root('target'), current)
        locked = copy.deepcopy(authority)
        locked['invoke'].pop('$messages-settle')
        current = self.call({'op': 'law', 'object': 'target', 'principal': 'maker', 'intent': self.intent(),
            'expected': current, 'law': locked}, 'committed')['data']['root']
        self.assertIn('unauthorized', self.call(dict(request, intent=self.intent(), expected=current), 'refused')['data'])
        current = self.call({'op': 'law', 'object': 'target', 'principal': 'maker', 'intent': self.intent(),
            'expected': current, 'law': authority}, 'committed')['data']['root']
        self.call(dict(request, intent=self.intent()), 'refused')
        accepted_request = dict(request, intent=self.intent(), expected=current)
        accepted = self.call(accepted_request, 'committed')
        self.assertEqual(self.call(accepted_request), accepted)
        self.assertEqual(self.root('target'), current)
        observed = self.call({'op': 'message-event', 'principal': 'maker', 'event': event})
        self.assertEqual(observed['event']['status'], 'settled')
        self.assertEqual(observed['event']['consumption']['reason'], 'retired')


    def test_create_passive_exact_initial_schema_and_configuration(self):
        passive = SOURCE.replace('methods: {add: Method}', 'methods: {}')
        passive = passive.replace('methods: {add: {label: "Exhibit", fields: {object: {type: "string", minLength: 1, maxLength: 64}}}},', 'methods: {},')
        unrelated = """record Wrong:
  text: String
record WrongDecision:
  accepted: Bool
  reason: String
  state: Wrong
  result: String
def unrelated() -> Wrong:
  {text: "wrong-state"}
def wrongMethod(state: Wrong, input: Input, context: Context) -> WrongDecision:
  {accepted: true, reason: "", state: state, result: "wrong-state"}
"""
        passive += '\n' + unrelated
        modules = [{'name': 'Shelf', 'source': passive}]
        program = source_object.load(modules, syntax='objective-bend-object')
        self.assertEqual(program['commands'], {})
        authority = {'profile': 'delvetalk-scoped-law', 'invoke': {}, 'law': ['maker'], 'reprogram': ['maker']}
        current = self.create('passive', program, authority)
        self.assertEqual(source_object.state_data(current), source_object.state_data({'protocol': program, 'state': program['initial']}))
        configured = copy.deepcopy(program)
        model = source_object.record({'entries': source_object.list_data([source_object.data({
            'key': 'configured', 'label': 'Configured', 'object': 'peer', 'panel': 'main'})])})
        configured['initial'] = {'model': source_object.compact_state(program, model,
            entry='describe', path=[{'field': 'initial'}])}
        child = self.create('configured', configured, authority)
        self.assertEqual(source_object.state_data(child), model)
        self.assertEqual(child['state'], configured['initial'])
        forged = []
        for key in ('packetSha256', 'sourcesSha256'):
            altered = copy.deepcopy(program)
            altered['initial']['model']['schema'][key] = '0' * 64
            forged.append(altered)
        source_changed = copy.deepcopy(program)
        source_changed['sourcePackages']['resident'] = self.adapter.source_packages.table([
            {'name': 'Shelf', 'source': passive.replace('Choose an exhibit.', 'Different retained source.')}])
        forged.append(source_changed)
        malformed = copy.deepcopy(program)
        malformed['initial']['model']['value'] = 'not-a-record'
        forged.append(malformed)
        raw_wrong = copy.deepcopy(program)
        raw_wrong['initial'] = {'model': source_object.data({'entries': 'wrong-model'})}
        forged.append(raw_wrong)
        unrelated_schema = copy.deepcopy(program)
        unrelated_schema['initial'] = {'model': source_object.compact_state(program,
            source_object.data({'text': 'wrong-state'}), entry='unrelated', path=[])}
        forged.append(unrelated_schema)
        scalar_schema = copy.deepcopy(program)
        scalar_schema['initial'] = {'model': source_object.compact_state(program,
            source_object.data('wrong-state'), entry='describe', path=[{'field': 'name'}])}
        forged.append(scalar_schema)
        command_mismatch = source_object.load([{'name': 'Shelf', 'source': SOURCE + '\n' + unrelated}],
            syntax='objective-bend-object')
        command_mismatch['commands']['add']['transition']['package']['entry'] = 'wrongMethod'
        forged.append(command_mismatch)
        before = json.loads(self.database.read_text())['objects']
        for index, altered in enumerate(forged):
            request = {'op': 'create', 'object': 'forged-' + str(index), 'principal': 'maker',
                'intent': self.intent(), 'protocol': altered, 'law': authority}
            refused = self.call(request, 'refused')
            self.assertEqual(self.call(request), refused)
            self.assertEqual(json.loads(self.database.read_text())['objects'], before)


if __name__ == '__main__':
    unittest.main()
