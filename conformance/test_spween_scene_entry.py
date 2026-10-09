"""An authored final Scene adds methods through the ordinary native source ABI."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from scene import handlers
from syntaxes import spween_workshop, obend_object
from conformance.test_spween_handlers import decoded, policy
import world

SOURCE = '''---
id: resonant-workshop
title: Resonant workshop
---
=== bench
A moth waits for the bell.
* [Follow the resonance] { inventory.resonance }
  -> END
'''


def document(entry):
    return ('spween handler workshop 1\n```spween\n' + SOURCE + '```\n```obend Handler\n'
            + (handlers.LIBRARY / 'Handler.obend').read_text() + '```\n```obend Scene\n' + entry + '```\n')


class SceneEntryFences(unittest.TestCase):
    def test_final_scene_and_dependencies_preserve_exact_source(self):
        entry = (handlers.RUNTIME / 'ResonantScene.obend').read_text().replace('\n', '\r\n')
        source = document(entry)
        helper = 'edition ObjectiveBend 1\ndef value() -> Nat:\n  1n\n'
        source = source.replace('```obend Scene\n', '```obend Tuning\n' + helper + '```\n```obend Scene\n')
        parsed = spween_workshop.parse_source(source)
        self.assertEqual(parsed['runtimeModules'], [])
        self.assertEqual(parsed['sceneModules'], [{'name': 'Tuning', 'source': helper}, {'name': 'Scene', 'source': entry}])
        modules = handlers.modules_for(handlers.bridge({'op': 'parse', 'source': SOURCE}),
            handler_modules=parsed['handlerModules'], scene_modules=parsed['sceneModules'])
        self.assertEqual([m['name'] for m in modules][-4:], ['Score', 'DefaultScene', 'Tuning', 'Scene'])
        self.assertEqual(modules[-1]['source'], entry)
        for malformed in (source + '\n```obend Tail\nextra\n```\n',
                          source.replace('obend Tuning', 'obend DefaultScene'),
                          source.replace('obend Handler', 'obend Scene')):
            with self.subTest(source=malformed[-60:]), self.assertRaises(ValueError):
                spween_workshop.parse_source(malformed)


class SceneEntry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = (handlers.RUNTIME / 'ResonantScene.obend').read_text()
        cls.protocol = spween_workshop.lower(document(cls.entry))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'world.json'
        self.serial = 0
        self.call({'op': 'messages-init', 'lineage': 'authored-scene', 'pendingLimit': 8,
                   'principal': 'author', 'intent': 'init'}, 'committed')
        law = policy(['start', 'choose', 'tune', 'hear'], ('player', 'relay'))
        law['reprogram'] = ['author', 'second-author']
        self.call({'op': 'create', 'object': 'scene', 'principal': 'author', 'intent': 'create',
                   'protocol': self.protocol, 'law': law}, 'committed')

    def call(self, request, expected=None):
        reply = world.exchange(self.path, request, profile='compiled')
        if expected: self.assertEqual(reply['kind'], expected, reply)
        return reply

    def intent(self):
        self.serial += 1
        return 'action-' + str(self.serial)

    def root(self, name='scene'):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def invoke(self, command, inputs, *, expected=None, kind='committed', principal='player', name='scene'):
        return self.call({'op': 'invoke', 'object': name, 'principal': principal, 'intent': self.intent(),
            'command': command, 'input': inputs, 'expected': self.root(name) if expected is None else expected}, kind)

    def variable(self, name):
        values = decoded(self.root()['state']['model'])['handler']['variables']
        while values[0] == 'cons':
            if values[1]['head']['name'] == name: return values[1]['head']['value']
            values = values[1]['tail']
        return None

    def test_added_typed_method_revision_and_restart_keep_exact_source(self):
        before = self.root()
        self.assertEqual(before['protocol']['spweenWorkshop']['modules'][-1],
                         {'name': 'Scene', 'source': self.entry})
        self.invoke('tune', {'amount': 3}, kind='refused')
        self.assertEqual(self.root(), before)
        self.invoke('start', {})
        started = self.root()
        self.invoke('tune', {'amount': 3}, principal='visitor', kind='refused')
        self.assertEqual(self.root(), started)
        for invalid in (0, 9, True, '3'):
            self.invoke('tune', {'amount': invalid}, kind='refused')
            self.assertEqual(self.root(), started)
        self.invoke('tune', {'amount': 3})
        self.assertEqual(self.variable('tuning'), ('integer', {'value': (1 << 63) + 3}))
        old = self.root()
        revised = self.entry.replace('5808n + input.amount', '5808n + input.amount + 1n')
        next_protocol = handlers.compile_source(SOURCE, scene_source=revised)['protocol']
        self.call({'op': 'reprogram', 'object': 'scene', 'principal': 'second-author', 'intent': self.intent(),
            'expected': old, 'protocol': next_protocol, 'state': old['state']}, 'committed')
        self.assertEqual(self.root()['state'], old['state'])
        self.invoke('tune', {'amount': 3}, expected=old, kind='refused')
        self.assertEqual(world.wire_loads(self.path.read_text())['objects']['scene'], self.root())
        self.invoke('tune', {'amount': 3})
        self.assertEqual(self.variable('tuning'), ('integer', {'value': (1 << 63) + 4}))
        self.assertEqual(self.root()['protocol']['spweenSource']['source'], SOURCE)
        packages = self.root()['protocol']['sourcePackages']
        modules = packages['resident']['modules']
        self.assertEqual(modules[-1], {'name': 'Scene', 'source': revised})
        self.assertIn('DefaultScene', [m['name'] for m in modules])

    def test_authored_receive_uses_event_evidence_and_unlocks_scene_guard(self):
        self.invoke('start', {})
        before = self.root()
        self.invoke('hear', {'chord': 'C E G'}, kind='refused', principal='relay')
        self.invoke('choose', {'choice': 0}, kind='refused')
        self.assertEqual(self.root(), before)
        # This helper asks the actual host for the receiver's exact program digest.
        helper = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'hash': {
            'require': [], 'set': {}, 'outbox': [], 'result': ['program-digest', ['input', 'program']]}}}
        self.call({'op': 'create', 'object': 'digest', 'principal': 'author', 'intent': self.intent(),
                   'protocol': helper, 'law': ['player']}, 'committed')
        digest = self.invoke('hash', {'program': self.protocol}, name='digest')['data']['result']
        bell = obend_object.lower_data_modules([{'name': n, 'source': (handlers.PRELUDE / (n + '.obend')).read_text()}
            for n in ('List', 'Abi', 'Preparation', 'Encounter', 'Emissions')] + [{'name': 'Bell', 'source': (ROOT / 'protocols/resident-messages/Bell.obend').read_text()}])
        self.call({'op': 'create', 'object': 'bell', 'principal': 'author', 'intent': self.intent(),
                   'protocol': bell, 'law': ['player']}, 'committed')
        sent = self.invoke('play', {'to': 'scene', 'recipientProgram': digest, 'chord': 'C E G', 'voices': 1}, name='bell')
        ref = sent['data']['messages'][0]
        request = {'op': 'deliver', 'object': 'scene', 'principal': 'relay', 'intent': self.intent(),
                   'expected': self.root(), 'event': ref}
        result = self.call(request, 'committed')
        self.assertEqual(result['data']['result'], {'source': 'bell', 'player': 'player'})
        self.assertEqual(self.call(request), result)
        self.invoke('choose', {'choice': 0})
        self.assertTrue(decoded(self.root()['state']['model'])['ended'])


if __name__ == '__main__': unittest.main()
