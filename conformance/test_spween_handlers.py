"""Real typed source scene/handler admission and durable addressed delivery."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from scene import handlers, room
from syntaxes import obend_object
import world


def decoded(value):
    if value['tag'] == 'record':
        return {f['name']: decoded(f['value']) for f in value['fields']}
    if value['tag'] == 'variant': return (value['label'], decoded(value['payload']))
    if value['tag'] == 'natural': return int(value['value'])
    return value['value']


def scene(body):
    return '---\nid: test\ntitle: Handler test\n---\n' + body


def policy(commands, actors=('player',)):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': {c: list(actors) for c in commands},
            'reprogram': ['author'], 'law': ['steward']}


class SpweenHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repair_source = (handlers.LIBRARY / 'repair.scene').read_text()
        cls.repair = handlers.compile_source(cls.repair_source)['protocol']

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'world.json'
        self.serial = 0
        self.call({'op': 'messages-init', 'lineage': 'spween-handlers', 'pendingLimit': 8,
                   'principal': 'author', 'intent': 'messages'}, 'committed')

    def call(self, request, kind=None):
        reply = world.exchange(self.path, request, profile='compiled')
        if kind is not None: self.assertEqual(reply['kind'], kind, reply)
        return reply

    def next(self):
        self.serial += 1
        return 'attempt-' + str(self.serial)

    def root(self, name='scene'):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def install(self, protocol=None, name='scene', law=None):
        return self.call({'op': 'create', 'object': name, 'principal': 'author', 'intent': self.next(),
                          'protocol': self.repair if protocol is None else protocol,
                          'law': policy(['start', 'choose']) if law is None else law}, 'committed')['data']['root']

    def invoke(self, command='choose', choice=0, *, name='scene', expected=None, principal='player', kind='committed'):
        return self.call({'op': 'invoke', 'object': name, 'principal': principal, 'intent': self.next(),
            'expected': self.root(name) if expected is None else expected, 'command': command,
            'input': {} if command == 'start' else {'choice': choice}}, kind)

    def model(self):
        return decoded(self.root()['state']['model'])

    def test_ordered_mutation_dynamic_membership_refusal_and_once_entry(self):
        self.install()
        self.invoke('start')
        before = self.root()
        view = room.inspect_object(before, 'scene')
        self.assertEqual([x['input']['choice'] for x in view['data']['actions'].values()], [0, 2, 3])
        self.invoke(choice=2, kind='refused')
        self.assertEqual(self.root(), before)
        self.invoke(choice=3, kind='refused')
        self.assertEqual(self.root(), before)
        self.invoke(choice=0)
        self.assertEqual(self.model()['handler']['repairs'], 1)
        view = room.inspect_object(self.root(), 'scene')
        self.assertEqual([x['input']['choice'] for x in view['data']['actions'].values()], [1, 2, 3])
        self.invoke(choice=1)
        self.invoke(choice=0)
        self.assertEqual(self.model()['handler']['repairs'], 1)
        # Returning does not execute entries += 1 again; no Python transition runs.
        variables = self.model()['handler']['variables']
        rows = {}
        while variables[0] == 'cons':
            rows[variables[1]['head']['name']] = variables[1]['head']['value']
            variables = variables[1]['tail']
        self.assertEqual(rows['entries'], ('integer', {'value': (1 << 63) + 1}))
        self.assertEqual(rows['work'], ('integer', {'value': (1 << 63) + 11}))
        self.invoke('start', kind='refused')

    def test_revision_restart_exact_roots_and_current_authority(self):
        self.install()
        self.invoke('start')
        old = self.root()
        source = (handlers.LIBRARY / 'Handler.obend').read_text().replace('repairs: step.state.repairs + 1n', 'repairs: step.state.repairs + 2n')
        revised = handlers.compile_source(self.repair_source, source)['protocol']
        changed = self.call({'op': 'reprogram', 'object': 'scene', 'principal': 'author',
            'intent': self.next(), 'expected': old, 'protocol': revised, 'state': old['state']}, 'committed')
        self.invoke(choice=0, expected=old, kind='refused')
        # A fresh process reconstructs from exact durable JSON history.
        self.assertEqual(world.wire_loads(self.path.read_text())['objects']['scene'], self.root())
        self.invoke(choice=0)
        self.assertEqual(self.model()['handler']['repairs'], 2)
        current = self.root()
        self.call({'op': 'law', 'object': 'scene', 'principal': 'steward', 'intent': self.next(),
                   'expected': current, 'law': policy(['start', 'choose'], ())}, 'committed')
        self.invoke(choice=1, kind='refused')
        self.assertEqual(self.model()['handler']['repairs'], 2)
        self.assertEqual(changed['data']['root']['protocol']['spweenSource']['source'], self.repair_source)

    def digest(self, protocol):
        helper = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'hash': {
            'require': [], 'set': {}, 'outbox': [], 'result': ['program-digest', ['input', 'program']]}}}
        root = self.install(helper, 'digest', ['reader'])
        return self.call({'op': 'invoke', 'object': 'digest', 'principal': 'reader', 'intent': self.next(),
            'expected': root, 'command': 'hash', 'input': {'program': protocol}}, 'committed')['data']['result']

    def test_addressed_message_source_evidence_current_delivery_law_and_retry(self):
        door_source = (ROOT / 'protocols/resident-messages/Door.obend').read_text().replace('event.source == "bell"', 'event.source == "scene"')
        door = obend_object.lower_data(door_source)
        self.install(door, 'door', policy(['hear'], ('relay',)))
        digest = self.digest(door)
        source = scene('=== bench\n* [Repair and ring]\n  ~ repair\n  ~ send "door" "' + digest + '" "C E G"\n  -> END\n')
        self.install(handlers.compile_source(source)['protocol'])
        self.invoke('start')
        before = self.root()
        done = self.invoke(choice=0)
        refs = done['data']['messages']
        self.assertEqual(len(refs), 1)
        self.assertEqual(done['data']['outbox'], [])
        event = world.wire_loads(self.path.read_text())['messages']['events'][refs[0]['id']]
        self.assertEqual(event['evidence']['sourcePreimage'], before)
        self.assertEqual(event['evidence']['admission']['principal'], 'player')
        root = self.root('door')
        self.call({'op': 'law', 'object': 'door', 'principal': 'steward', 'intent': self.next(),
                   'expected': root, 'law': policy(['hear'], ())}, 'committed')
        request = {'op': 'deliver', 'object': 'door', 'principal': 'relay', 'intent': self.next(),
                   'expected': self.root('door'), 'event': refs[0]}
        self.call(request, 'refused')
        self.call({'op': 'law', 'object': 'door', 'principal': 'steward', 'intent': self.next(),
                   'expected': self.root('door'), 'law': policy(['hear'], ('relay',))}, 'committed')
        request.update(intent=self.next(), expected=self.root('door'))
        delivered = self.call(request, 'committed')
        self.assertEqual(self.call(request), delivered)
        observed = decoded(self.root('door')['state']['model'])
        self.assertEqual((observed['heard'], observed['lastSource'], observed['lastPlayer']), (1, 'scene', 'player'))

    def test_bad_delivery_binding_and_fifth_emission_atomically_refuse(self):
        for count in (1, 5):
            with self.subTest(count=count):
                send = '~ send "missing" "' + '0' * 64 + '" "C E G"\n'
                prefix = '=== bench\n* [Try]\n  ~ repair\n'
                body = prefix + ('  ' + send) * (1 if count == 1 else 3)
                body += '  -> END\n' if count == 1 else '  -> ringing\n=== ringing\n' + send * 2
                source = scene(body)
                name = 'scene' + str(count)
                self.install(handlers.compile_source(source)['protocol'], name)
                self.invoke('start', name=name)
                before = self.root(name)
                denied = self.invoke(choice=0, name=name, kind='refused')
                if count == 5: self.assertIn('four addressed', denied['data'])
                self.assertEqual(self.root(name), before)
        self.assertEqual(world.wire_loads(self.path.read_text())['messages']['events'], {})

    def test_explicit_subset_and_module_boundaries(self):
        for source in [scene('=== p\n~ v = 1.5\n'), scene('=== p\n* [Order] { v < "a" }\n  -> END\n')]:
            with self.assertRaises(ValueError): handlers.compile_source(source)
        for modules in ([], [{'name': 'Kernel', 'source': 'anything'}], [{'name': 'Other', 'source': 'anything'}]):
            with self.assertRaises(ValueError): handlers.compile_source(self.repair_source, handler_modules=modules)
        bad = (handlers.LIBRARY / 'Handler.obend').read_text().replace('def has(state: State, category: String, key: String) -> Bool:', 'def has(state: State, category: String, key: String) -> Nat:')
        with self.assertRaises(ValueError): handlers.compile_source(self.repair_source, bad)


if __name__ == '__main__': unittest.main()
