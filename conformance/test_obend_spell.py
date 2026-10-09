#!/usr/bin/env python3
"""Actual Bend source through source custody, Lean admission and spell use."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


translate = module('spell_translate', 'scripts/translate.py')
world = module('spell_world', 'scripts/world.py')
desk = module('spell_desk', 'scripts/desk.py')
projection = module('spell_projection', 'scene/projection.py')


def source(name):
    return (ROOT / 'syntaxes/examples' / (name + '-door.obend')).read_bytes()


class ObjectiveBendSpell(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.database = self.path / 'world.json'

    def call(self, request):
        return world.exchange(self.database, request, profile='compiled')

    def install(self, raw, object_id='door'):
        artifact = translate.translate('objective-bend-spell@1', raw)
        receipt = self.call({'op': 'create', 'object': object_id,
            'principal': 'maker', 'intent': 'create-' + object_id,
            'protocol': artifact['lowered'], 'law': ['visitor', 'maker']})
        return artifact, receipt

    def knock(self, root, word, *, principal='visitor', intent='knock'):
        return self.call({'op': 'invoke', 'object': 'door', 'principal': principal,
            'intent': intent, 'expected': root, 'command': 'knock',
            'input': {'word': word}})

    def test_actual_source_controls_admission_result_and_inscription(self):
        for spelling, word, old_word, title, result in (
            ('paper', 'please', 'moon', 'The paper door',
             'The paper door swings open onto a tiny lantern-lit room.'),
            ('moon', 'moon', 'please', 'The moon door',
             'The silver door opens into a room full of small moons.'),
        ):
            with self.subTest(spelling=spelling), tempfile.TemporaryDirectory() as temporary:
                self.database = Path(temporary) / 'world.json'
                _, installed = self.install(source(spelling))
                self.assertEqual(installed['kind'], 'committed', installed)
                root = installed['data']['root']
                refusal = self.knock(root, old_word, intent='wrong')
                self.assertEqual((refusal['kind'], refusal['data']),
                                 ('refused', 'precondition failed'))
                spoof = self.knock(root, word, principal='outsider', intent='spoof')
                self.assertEqual((spoof['kind'], spoof['data']), ('refused', 'unauthorized'))
                received = self.knock(root, word)
                self.assertEqual(received['kind'], 'committed', received)
                self.assertEqual(received['data']['result'], result)
                self.assertEqual(received['data']['root']['state'], {})
                self.assertEqual(self.knock(root, word), received)
                view = projection.project(received['data']['root'], 'door')
                self.assertEqual(view['data']['title'], title)
                self.assertIn('Whisper ' + word, view['data']['prose'])
                self.assertEqual(view['actions']['knock']['command'], 'knock')

    def test_translation_keeps_exact_utf8_source_and_grants_no_authority(self):
        raw = ('# 雪 🜉\r\n' + source('paper').decode().replace('\n', '\r\n')).encode()
        artifact = translate.translate('objective-bend-spell@1', raw)
        self.assertEqual(artifact['source']['text'].encode(), raw)
        protocol = artifact['lowered']
        for expression in (protocol['commands']['knock']['require'][0][0],
                           protocol['commands']['knock']['result']):
            self.assertEqual(expression[1]['modules'][0]['source'].encode(), raw)
            self.assertNotIn('packet', expression[1])
        self.assertEqual(protocol['viewProgram']['package']['modules'][0]['source'].encode(), raw)
        self.assertNotIn('law', protocol)
        self.assertFalse(self.database.exists())

    def test_lean_refuses_invalid_source_before_installation(self):
        for raw in (b'not an Objective Bend module',
                    source('paper').replace(b'word == self.password', b'missingDefinition(word)'),
                    source('paper').replace(b'-> String:\n  fix(Paper, {}).knock(word)',
                                           b'-> Nat:\n  fix(Paper, {}).knock(word)')):
            with self.subTest(raw=raw[:50]):
                _, receipt = self.install(raw)
                self.assertEqual(receipt['kind'], 'refused', receipt)
                self.assertEqual(world.wire_loads(self.database.read_text())['objects'], {})

    def test_bad_argument_and_stale_read_cannot_change_live_state(self):
        _, installed = self.install(source('paper'))
        root = installed['data']['root']
        bad = self.knock(root, 7, intent='wrong-type')
        self.assertEqual(bad['kind'], 'refused')
        success = self.knock(root, 'please')
        stale = self.knock(root, 'please', intent='new-stale-request')
        self.assertEqual((stale['kind'], stale['data']), ('refused', 'stale read root'))
        current = self.call({'op': 'inspect', 'object': 'door', 'principal': 'reader'})
        self.assertEqual(current, success['data']['root'])

    def test_source_desk_checks_preserves_and_adopts_actual_bend_source(self):
        worker = desk.Desk(self.database, self.path / 'artifacts', profile='compiled')
        candidate = worker.create('candidate', 'maker', 'create-candidate', ['maker'])['data']['root']
        _, receipt = self.install(source('paper'))
        target = receipt['data']['root']
        examples = translate.canonical([{'name': 'moon-opens', 'law': ['visitor'], 'steps': [
            {'principal': 'visitor', 'command': 'knock', 'input': {'word': 'moon'},
             'root': 'current', 'kind': 'committed', 'state': {},
             'result': 'The silver door opens into a room full of small moons.'}]}])
        pending = worker.submit('candidate', 'maker', 'submit', candidate,
            'objective-bend-spell@1', source('moon'), examples, {}, 'door')['data']['root']
        checked = worker.check('candidate', 'maker', 'check', pending)
        self.assertEqual(checked['kind'], 'committed', checked)
        ready = checked['data']['root']
        self.assertEqual(ready['state']['status'], 'ready', ready)
        artifact = desk.load_artifact(self.path / 'artifacts', ready['state']['artifact'])
        self.assertEqual(artifact['sourceMaterial']['source'].encode(), source('moon'))
        self.assertEqual(worker.inspect('door'), target)
        adopted = worker.adopt('candidate', 'door', 'maker', 'adopt', ready, target)
        self.assertEqual(adopted['kind'], 'committed', adopted)
        current = worker.inspect('door')
        result = self.knock(current, 'moon')
        self.assertEqual(result['data']['result'], 'The silver door opens into a room full of small moons.')


if __name__ == '__main__':
    unittest.main()
