"""Actual Rust EffectHandler versus source-lowered native admission.

Successful synchronous turns agree. Upstream partial writes after an error are
recorded explicitly: the admitted profile deliberately rolls the whole turn back.
Async delivery/cancellation is a separate host extension, not Rust equivalence.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from scene import handlers, room
import world

ORACLE = Path(os.environ.get('DELVETALK_HANDLER_ORACLE', str(ROOT / 'scene/spween-bridge/target/release/examples/handler_oracle')))


def scene(body):
    return '---\nid: handler_oracle\ntitle: Handler oracle\n---\n' + body


def data(value):
    """Decode native Data only; do not execute scene/handler rules in Python."""
    tag = value['tag']
    if tag == 'record': return {f['name']: data(f['value']) for f in value['fields']}
    if tag == 'variant': return (value['label'], data(value['payload']))
    if tag == 'natural': return int(value['value'])
    if tag in ('boolean', 'label'): return value['value']
    raise AssertionError('unexpected native data tag: ' + tag)


def linked(value):
    items = []
    while value[0] == 'cons':
        items.append(value[1]['head']); value = value[1]['tail']
    assert value == ('nil', {}), value
    return items


def tagged(value):
    kind, payload = value
    if kind == 'null': return ['null']
    if kind == 'integer': return ['int', str(payload['value'] - (1 << 63))]
    return [{'boolean': 'bool', 'string': 'string'}[kind], payload['value']]


class HandlerOracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / 'world.json'
        self.serial = 0
        self.object_id = "scene"

    def rust(self, source, choices):
        if not ORACLE.is_file():
            self.fail('build Rust handler oracle: cargo build --release -j1 --example handler_oracle --manifest-path scene/spween-bridge/Cargo.toml')
        result = subprocess.run([str(ORACLE)], input=json.dumps({'source': source, 'choices': choices}),
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['upstream'], handlers.UPSTREAM)
        return value['trace']

    def install(self, source):
        protocol = handlers.compile_source(source)['protocol']
        if not self.database.exists():
            initialized = world.exchange(self.database, {'op': 'messages-init', 'principal': 'bootstrap',
                'intent': 'messages-init', 'lineage': 'oracle-world', 'pendingLimit': 32}, profile='compiled')
            self.assertEqual(initialized['kind'], 'committed', initialized)
        result = world.exchange(self.database, {'op': 'create', 'object': self.object_id, 'principal': 'owner',
            'intent': 'seed', 'protocol': protocol, 'law': ['player']}, profile='compiled')
        self.assertEqual(result['kind'], 'committed', result)
        self.root = result['data']['root']
        return self.invoke('start')

    def invoke(self, command='choose', choice=0):
        self.serial += 1
        request = {'op': 'invoke', 'object': self.object_id, 'principal': 'player', 'intent': str(self.serial),
                   'expected': self.root, 'command': command, 'input': {} if command == 'start' else {'choice': choice}}
        result = world.exchange(self.database, request, profile='compiled')
        self.root = world.exchange(self.database, {'op': 'inspect', 'object': self.object_id,
                                   'principal': 'reader'}, profile='compiled')
        if result['kind'] == 'committed': self.assertEqual(self.root, result['data']['root'])
        return result

    def model(self):
        return data(self.root['state']['model'])

    def compare(self, snapshot):
        model = self.model(); handler = model['handler']
        self.assertEqual({v['name']: tagged(v['value']) for v in linked(handler['variables'])}, snapshot['vars'])
        self.assertEqual(sorted([v['category'], v['key']] for v in linked(handler['members'])), snapshot['members'])
        self.assertEqual(handler['repairs'], snapshot['repairs'])
        self.assertEqual(model['ended'], snapshot['ended'])
        if not model['ended']: self.assertEqual(model['passage'], snapshot['passage'])
        view = room.inspect_object(self.root, self.object_id)
        self.assertEqual(view['mode'], 'projection', view.get('diagnostic'))
        offered = sorted(a['input']['choice'] for a in view['data']['actions'].values() if a['command'] == 'choose')
        self.assertEqual(offered, [c['index'] for c in snapshot['choices'] if c['available']])

    def replay(self, source, choices):
        trace = self.rust(source, choices)
        self.assertEqual(self.install(source)['kind'], 'committed')
        self.compare(trace[0]['snapshot'])
        for choice, expected in zip(choices, trace[1:]):
            actual = self.invoke(choice=choice)
            self.assertEqual(expected['kind'], 'ok', expected)
            self.assertEqual(actual['kind'], 'committed', actual)
            self.compare(expected['snapshot'])
        return trace

    def test_call_mutates_variables_members_later_guard_and_entry_runs_once(self):
        self.replay(scene('''=== intro
~ repair
~ work += 2
* [Visit] { work == 12 && inventory.moth }
  -> away
=== away
~ release
* [Return]
  -> intro
'''), [0, 0])
        self.assertEqual(self.model()['handler']['repairs'], 1)

    def test_ordered_set_modify_call_and_bool_int_rules(self):
        self.replay(scene('''=== intro
* [Work]
  ~ work = 1
  ~ work += 2
  ~ repair
  ~ work -= 4
  ~ flag = true
  ~ flag += 2
  ~ missing -= 3
  ~ word = "unchanged"
  ~ word += 5
  -> check
=== check
* [Equal] { work == 6 && flag == 1 && missing == -3 && inventory.moth }
  -> END
* [Bool is not ordered] { flag > 0 }
  -> END
* [String unchanged] { word == "unchanged" }
  -> END
'''), [0, 0])

    def test_upstream_partial_error_is_explicit_admitted_atomic_rollback(self):
        for final in ('reject', 'unknown', 'repair 1'):
            with self.subTest(call=final):
                self.database = Path(self.tmp.name) / (final.replace(' ', '-') + '.json')
                source = scene('=== intro\n* [Attempt]\n  ~ work = 2\n  ~ repair\n  ~ ' + final + '\n  -> END\n')
                trace = self.rust(source, [0])
                self.assertEqual(trace[1]['kind'], 'error')
                self.assertEqual(trace[1]['snapshot']['vars']['work'], ['int', '10'])
                self.assertEqual(trace[1]['snapshot']['repairs'], 1)
                self.assertEqual(self.install(source)['kind'], 'committed')
                before = copy.deepcopy(self.root)
                self.assertEqual(self.invoke()['kind'], 'refused')
                self.assertEqual(self.root, before)
                self.assertEqual(self.model()['handler']['repairs'], 0)

    def test_entry_failure_records_upstream_visit_but_admitted_world_rolls_back(self):
        source = scene('''=== intro
* [Visit]
  -> failing
=== failing
~ repair
~ reject
* [Return]
  -> intro
''')
        trace = self.rust(source, [0, 0, 0])
        self.assertEqual([t['kind'] for t in trace], ['ok', 'error', 'ok', 'ok'])
        self.assertEqual(trace[1]['snapshot']['passage'], 1)
        self.assertEqual(trace[-1]['snapshot']['repairs'], 1)  # Failed entry marked visited upstream.
        self.assertEqual(self.install(source)['kind'], 'committed')
        before = copy.deepcopy(self.root)
        self.assertEqual(self.invoke()['kind'], 'refused')
        self.assertEqual(self.root, before)
        self.assertEqual(self.invoke()['kind'], 'refused')
        self.assertEqual(self.root, before)

    def test_checked_i64_overflow_preserves_upstream_prefix_not_admitted_prefix(self):
        source = scene('''=== intro
* [Overflow]
  ~ work = 9223372036854775807
  ~ work += 1
  -> END
''')
        trace = self.rust(source, [0])
        self.assertEqual(trace[1]['kind'], 'panic')
        self.assertEqual(trace[1]['snapshot']['vars']['work'], ['int', '9223372036854775807'])
        self.assertEqual(self.install(source)['kind'], 'committed')
        before = copy.deepcopy(self.root)
        self.assertEqual(self.invoke()['kind'], 'refused')
        self.assertEqual(self.root, before)

    def test_fifth_emission_refuses_admitted_turn_without_retaining_first_four(self):
        sends = ''.join('  ~ send "listener" "program" "chord' + str(i) + '"\n' for i in range(5))
        source = scene('=== intro\n* [Too many]\n  ~ repair\n' + sends + '  -> END\n')
        trace = self.rust(source, [0])
        self.assertEqual(trace[1]['kind'], 'error')
        self.assertEqual(len(trace[1]['snapshot']['emissions']), 4)
        self.assertEqual(self.install(source)['kind'], 'committed')
        before = copy.deepcopy(self.root)
        refused = self.invoke()
        self.assertEqual(refused['kind'], 'refused')
        self.assertIn('at most four', refused['data'])
        self.assertEqual(self.root, before)
        self.assertNotIn('outbox', refused)

    def test_async_delivery_and_explicit_decline_are_separate_host_turns(self):
        # This is the host extension, not upstream Runtime equivalence: Rust
        # only observes the synchronous send callback and never delivers it.
        from conformance.test_resident_messages import source_protocol, law
        def call(request): return world.exchange(self.database, request, profile='compiled')
        def current(name): return call({'op': 'inspect', 'object': name, 'principal': 'reader'})
        self.assertEqual(call({'op': 'messages-init', 'principal': 'bootstrap', 'intent': 'init',
            'lineage': 'oracle-world', 'pendingLimit': 32})['kind'], 'committed')
        door = call({'op': 'create', 'object': 'door', 'principal': 'bootstrap', 'intent': 'door',
                     'protocol': source_protocol('Door'), 'law': law('hear', ['relay'])})['data']['root']
        digest_protocol = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'hash': {
            'require': [], 'set': {}, 'outbox': [], 'result': ['program-digest', ['input', 'program']]}}}
        digest_root = call({'op': 'create', 'object': 'digest', 'principal': 'bootstrap', 'intent': 'digest',
            'protocol': digest_protocol, 'law': ['reader']})['data']['root']
        identity = call({'op': 'invoke', 'object': 'digest', 'principal': 'reader', 'intent': 'hash',
            'expected': digest_root, 'command': 'hash', 'input': {'program': door['protocol']}})['data']['result']
        source = scene('=== intro\n* [Send]\n  ~ send "door" "' + identity + '" "C E G"\n'
                       '  ~ send "door" "' + identity + '" "decline"\n  -> END\n')
        trace = self.rust(source, [0])
        self.assertEqual(len(trace[1]['snapshot']['emissions']), 2)
        self.object_id = 'bell'  # The independently authored receiving door checks source identity.
        self.assertEqual(self.install(source)['kind'], 'committed')
        receipt = self.invoke()
        self.assertEqual(receipt['kind'], 'committed', receipt)
        references = receipt['data']['messages']
        self.assertEqual(len(references), 2)
        events = world.wire_loads(self.database.read_text())['messages']['events']
        for ref, expected in zip(references, trace[1]['snapshot']['emissions']):
            evidence = events[ref['id']]['evidence']
            self.assertEqual({key: evidence[key] for key in expected}, expected)
        self.assertEqual(current('door'), door)  # Emission alone does not execute the recipient.
        def deliver(ref, intent):
            request = {'op': 'deliver', 'object': 'door', 'principal': 'relay', 'intent': intent,
                       'event': ref, 'expected': current('door')}
            result = call(request)
            self.assertEqual(result['kind'], 'committed', result)
            self.assertEqual(call(request), result)  # Same attempt receipt, never another delivery.
            return result
        opened = deliver(references[0], 'relay-open')
        self.assertEqual(opened['data']['result']['disposition'], 'opened')
        before_decline = current('door')['state']
        declined = deliver(references[1], 'relay-decline')
        self.assertEqual(declined['data']['result']['disposition'], 'declined')
        self.assertEqual(current('door')['state'], before_decline)
        self.assertEqual(world.wire_loads(self.database.read_text())['messages']['pending'], {})
        refused = call({'op': 'deliver', 'object': 'door', 'principal': 'relay', 'intent': 'repeat-event',
                        'event': references[1], 'expected': current('door')})
        self.assertEqual(refused['kind'], 'refused')


if __name__ == '__main__': unittest.main()
