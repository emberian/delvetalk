#!/usr/bin/env python3
"""Authored Bend, desk adoption, gated commons movement, and exact restoration.

Every transition runs through the real compiled Lean host. Principals here are
explicit local caller assertions; authenticated posts are covered by the town
journey. No evaluator, compiler, world admission or custody operation is mocked.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import affordances
import compiler_queue
import workspace


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


forge = module('guarded_authoring_forge', 'protocols/town-forge/generate.py')
commons = module('guarded_authoring_commons', 'protocols/commons/generate.py')
room = module('guarded_authoring_room', 'scene/room.py')
bootstrap = workspace.bootstrap
desk = compiler_queue.desk
TARGET = 'objects/garden-door'
SOURCE = '''edition ObjectiveBend 1
record Crossing:
  place: String
  description: String
record Action:
  text: String
  command: String
  input: {}
record Actions:
  knock: Action
record View:
  title: String
  prose: String
  actions: Actions
record Door:
  password: String
  allowed: String -> Bool
  knock: String -> Crossing
extension Garden(self: Door, super: {}) -> Door:
  {password: "please", allowed: fn(word: String) -> Bool: word == self.password, knock: fn(word: String) -> Crossing: {place: "garden", description: "The path opens into the shared garden."}}
def allowed(word: String) -> Bool:
  fix(Garden, {}).allowed(word)
def knock(word: String) -> Crossing:
  fix(Garden, {}).knock(word)
def view(state: {}, panel: String) -> View:
  {title: "The garden door", prose: "Whisper please to cross into the garden.", actions: {knock: {text: "Ask the garden door", command: "knock", input: {}}}}
'''
REVISION = SOURCE.replace('password: "please"', 'password: "moon"').replace('Whisper please', 'Whisper moon')


def examples(word):
    return f'''examples DelveTalk 1
case the authored door admits a crossing
law visitor
as visitor
send knock
  word: {word}
expect committed
as visitor
send knock
  word: wrong
expect refusal: precondition failed
as outsider
send knock
  word: {word}
expect refusal: unauthorized
'''


class GuardedAuthoring(unittest.TestCase):
    def test_adopted_source_controls_crossing_and_survives_restore(self):
        with tempfile.TemporaryDirectory(prefix='guarded-authoring-') as temporary:
            base = Path(temporary)
            directory = base / 'world'
            participants = {who: commons.references.object_reference('guarded-authoring', 'people/' + who)
                            for who in ('maker', 'visitor')}
            places = {name: {'title': title, 'description': title,
                            'reference': commons.references.object_reference('guarded-authoring', 'places/' + name)}
                      for name, title in (('porch', 'The porch'), ('garden', 'The shared garden'))}
            gate = {'from': 'porch', 'to': 'garden', 'object': TARGET, 'command': 'knock'}
            presence = commons.build(participants, places,
                [('porch', 'garden'), ('garden', 'porch')], entries=('porch',), gates=[gate])
            seeds = [{'id': name, 'syntax': 'protocol-json@1', 'source': desk.canonical(protocol),
                      'law': forge.factory_law(['maker'])}
                     for name, protocol in forge.build(['visitor'], 'compiler').items()]
            seeds.append({'id': 'commons', 'syntax': 'protocol-json@1',
                'source': desk.canonical(presence), 'law': commons.law(participants, managers=('steward',))})
            seed = workspace.initialize(directory, seeds, entry_objects=['commons', 'objects', 'desks'],
                principal='operator', profile='compiled', world_id='guarded-authoring')
            client = desk.Desk(directory / 'world.json', directory / 'artifacts', profile='compiled')
            queue = compiler_queue.CompilerQueue(base / 'compiler', client.database,
                client.artifact_store, profile='compiled')
            serial = 0

            def invoke(object_id, command, fields, principal='visitor'):
                nonlocal serial
                serial += 1
                return client.exchange({'op': 'invoke', 'object': object_id, 'principal': principal,
                    'intent': 'invoke-' + str(serial), 'expected': client.inspect(object_id),
                    'command': command, 'input': fields})

            def make(factory, name):
                nonlocal serial
                serial += 1
                observed = room.inspect_object(client.inspect(factory), factory)
                request = affordances.request(observed, 'a1', 'maker', 'make-' + str(serial), {'name': name})
                receipt = client.exchange(request)
                self.assertEqual(receipt['kind'], 'committed', receipt)
                refs = affordances.allocated_refs(receipt)
                self.assertEqual([ref['object'] for ref in refs], [factory + '/' + name])
                return refs[0]['object']

            def crossing(word):
                nonlocal serial
                serial += 1
                return {'op': 'transaction', 'principal': 'visitor', 'intent': 'cross-' + str(serial),
                    'reads': {TARGET: client.inspect(TARGET), 'commons': client.inspect('commons')},
                    'calls': [{'object': TARGET, 'command': 'knock', 'input': {'word': word}},
                              {'object': 'commons', 'command': 'move', 'inputFrom': 0}]}

            self.assertEqual(make('objects', 'garden-door'), TARGET)
            self.assertEqual(invoke('commons', 'enter', {'place': 'porch'})['kind'], 'committed')
            original_commons_program = client.inspect('commons')['protocol']
            builds = []
            first_crossing = None
            for index, (source, word) in enumerate(((SOURCE, 'please'), (REVISION, 'moon')), 1):
                candidate = make('desks', 'spell-' + str(index))
                before_door, before_commons = client.inspect(TARGET), client.inspect('commons')
                observed = room.inspect_object(client.inspect(candidate), candidate)
                submitted = client.exchange(affordances.request(observed, 'a1', 'maker',
                    'source-' + str(index), {'target': TARGET, 'source': source, 'scenarios': examples(word)}))
                self.assertEqual(submitted['kind'], 'committed', submitted)
                pending = submitted['data']['root']
                self.assertEqual(pending['state']['proposal']['source'], source)
                self.assertEqual(pending['state']['proposal']['syntax'], 'objective-bend-spell@1')
                job = queue.enqueue(candidate, 'compiler', 'compile-' + str(index), pending)['job']
                checked = queue.run(limit=1, deadline_seconds=30)
                self.assertEqual(checked['errors'], [], checked)
                self.assertEqual(checked['blocked'], [], checked)
                finished = queue.inspect(job)
                self.assertEqual(finished['phase'], 'finished', finished)
                ready = finished['receipt']['data']['root']
                self.assertEqual(ready['state']['status'], 'ready', ready)
                build = desk.load_artifact(client.artifact_store, finished['artifact'])
                self.assertTrue(build['report']['passed'])
                self.assertEqual(build['report']['outcomes'][0]['steps'][0]['receipt']['data']['result']['place'], 'garden')
                builds.append((finished['artifact'], source, examples(word)))
                self.assertEqual(client.inspect(TARGET), before_door)
                self.assertEqual(client.inspect('commons'), before_commons)
                adopted = client.adopt(candidate, TARGET, 'maker', 'adopt-' + str(index), ready, before_door)
                self.assertEqual(adopted['kind'], 'committed', adopted)
                self.assertEqual(client.inspect('commons'), before_commons)
                self.assertEqual(client.inspect(TARGET)['law'], before_door['law'])
                self.assertIn('Whisper ' + word, room.inspect_object(client.inspect(TARGET), TARGET)['data']['prose'])

                # Directly supplying the same destination does not authenticate the gate.
                self.assertEqual(invoke('commons', 'move', {'place': 'garden', 'inputOrigin': {
                    'present': True, 'object': TARGET, 'command': 'knock', 'immediatelyPrevious': True}})['kind'], 'refused')
                wrong = crossing('wrong' if index == 1 else 'please')
                self.assertEqual(client.exchange(wrong)['kind'], 'refused')
                self.assertEqual(client.inspect('commons'), before_commons)
                self.assertEqual(client.inspect(TARGET), wrong['reads'][TARGET])
                request = crossing(word)
                receipt = client.exchange(request)
                self.assertEqual(receipt['kind'], 'committed', receipt)
                self.assertEqual(receipt['data']['results'][0]['place'], 'garden')
                self.assertEqual(receipt['data']['results'][1]['from'], 'porch')
                self.assertEqual(receipt['data']['results'][1]['to'], 'garden')
                self.assertEqual(client.inspect('commons')['state']['locations']['visitor'], 'garden')
                self.assertEqual(client.exchange(request), receipt)
                if first_crossing is None:
                    first_crossing = (request, receipt)
                self.assertEqual(invoke('commons', 'move', {'place': 'porch'})['kind'], 'committed')

            self.assertEqual(client.inspect('commons')['protocol'], original_commons_program)
            bundle = base / 'history'
            evidence = bootstrap.export_bootstrap(directory, bundle)
            restored = base / 'restored'
            reconstruction = bootstrap.restore_bootstrap(bundle, restored,
                expected_genesis=seed['genesis'], expected_head=evidence['head'], base_head=seed['head'])
            self.assertEqual(desk.loads((restored / 'world.json').read_bytes()), desk.loads(client.database.read_bytes()))
            for identity, source, fixture_text in builds:
                self.assertIn(identity, reconstruction['builds'])
                original_path = client.artifact_store / 'builds' / (identity + '.json')
                restored_path = restored / 'artifacts/builds' / (identity + '.json')
                self.assertEqual(restored_path.read_bytes(), original_path.read_bytes())
                build = desk.load_artifact(restored / 'artifacts', identity)
                self.assertEqual(build['sourceMaterial'], {'source': source, 'scenarios': fixture_text})

            client = desk.Desk(restored / 'world.json', restored / 'artifacts', profile='compiled')
            self.assertEqual(client.exchange(first_crossing[0]), first_crossing[1])
            self.assertEqual(client.inspect('commons')['state']['locations']['visitor'], 'porch')
            self.assertEqual(client.exchange(crossing('please'))['kind'], 'refused')
            after_restore = client.exchange(crossing('moon'))
            self.assertEqual(after_restore['kind'], 'committed', after_restore)
            self.assertEqual(client.inspect('commons')['state']['locations']['visitor'], 'garden')
            self.assertIn('Whisper moon', room.inspect_object(client.inspect(TARGET), TARGET)['data']['prose'])


if __name__ == '__main__':
    unittest.main()
