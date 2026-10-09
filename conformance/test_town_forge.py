#!/usr/bin/env python3
"""Forge protocols allocate, compile and revise using the existing Lean host."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import affordances
import compiler_queue
import town_cards


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


forge = module('forge_package', 'protocols/town-forge/generate.py')
room = module('forge_room', 'scene/room.py')
desk = compiler_queue.desk


class ForgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.client = desk.Desk(self.path / 'world.json', self.path / 'artifacts', profile='compiled')
        self.queue = compiler_queue.CompilerQueue(self.path / 'queue', self.client.database,
            self.client.artifact_store, profile='compiled')
        self.serial = 0
        for name, protocol in forge.build(['visitor'], 'compiler').items():
            result = self.call({'op': 'create', 'object': name, 'principal': 'operator',
                'intent': 'seed-' + name, 'protocol': protocol,
                'law': forge.factory_law(['maker', 'visitor'], ['steward'])})
            self.assertEqual(result['kind'], 'committed', result)

    def call(self, request):
        return self.client.exchange(request)

    def inspect(self, name):
        return self.client.inspect(name)

    def view(self, name):
        return room.inspect_object(self.inspect(name), name)

    def invoke(self, name, command, fields, principal='maker', expected=None):
        self.serial += 1
        return self.call({'op': 'invoke', 'object': name, 'principal': principal,
            'intent': 'turn-' + str(self.serial), 'expected': expected or self.inspect(name),
            'command': command, 'input': fields})

    def allocate(self, factory, name, principal='maker'):
        self.serial += 1
        request = affordances.request(self.view(factory), 'a1', principal,
            'make-' + str(self.serial), {'name': name})
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(self.call(request), receipt)
        child = factory + '/' + name
        self.assertEqual(affordances.allocated_refs(receipt), [{'object': child, 'root': self.inspect(child)}])
        return child

    def submit(self, candidate, target, source, scenarios, principal='maker'):
        self.serial += 1
        request = affordances.request(self.view(candidate), 'a1', principal,
            'submit-' + str(self.serial), {'target': target,
                'source': source, 'scenarios': scenarios})
        result = self.call(request)
        self.assertEqual(result['kind'], 'committed', result)
        return result['data']['root']

    def compile(self, candidate, pending, principal='compiler'):
        self.serial += 1
        identity = self.queue.enqueue(candidate, principal, 'compile-' + str(self.serial), pending)['job']
        run = self.queue.run(limit=1, deadline_seconds=30)
        self.assertEqual(run['errors'], [], run)
        self.assertEqual(run['blocked'], [], run)
        result = self.queue.inspect(identity)
        self.assertEqual(result['phase'], 'finished', result)
        artifact = desk.load_artifact(self.client.artifact_store, result['artifact'])
        self.assertEqual(artifact['candidateRootSha256'], desk.digest(pending))
        return result['receipt'], artifact

    def test_generated_files_and_views_are_inline_and_bounded(self):
        for name, value in forge.files().items():
            self.assertEqual(json.loads((ROOT / 'protocols/town-forge' / name).read_text()), value)
        book = town_cards.CardBook.create(self.path / 'cards', issuer_did='did:plc:' + 'a' * 24,
            world_id='forge-test', runtime={'profile': 'compiled'})
        for factory in ('objects', 'desks'):
            opening = self.view(factory)
            self.assertEqual(opening['mode'], 'projection')
            card = affordances.card(opening)
            self.assertTrue(card['prose'])
            self.assertEqual(card['actions'][0]['command'], 'make')
            captured = book.capture(opening, alias=factory)
            self.assertNotIn('State:', captured['body'])
            self.assertIn('Nothing made here yet.', captured['body'])
        target = self.allocate('objects', 'paper')
        candidate = self.allocate('desks', 'spell')
        self.assertEqual(room.inspect_object(self.inspect('objects'), 'objects', panel='last')['data']['prose'], 'paper')
        source = forge.spell_source(1)
        scenarios = forge.example_source(1)
        pending = self.submit(candidate, target, source, scenarios)
        self.assertEqual(pending['state']['proposal'],
            {'syntax': forge.SPELL_SYNTAX, 'source': source, 'scenarios': scenarios})
        self.assertEqual(pending['state']['migration'], {})
        self.assertEqual(pending['state']['submitter'], 'maker')
        for panel, text in (('source', source), ('scenarios', scenarios), ('target', target)):
            view = room.inspect_object(pending, candidate, panel=panel)
            self.assertEqual(view['data']['prose'], text)
        self.assertEqual(affordances.card(self.view(candidate))['actions'], [])
        captured = book.capture(self.view(candidate), alias='spell')
        self.assertLessEqual(len(captured['body'].encode()), 12000)
        self.assertIn('Exact spell source', captured['body'])

    def test_creator_and_visitor_laws_are_real_and_do_not_follow_labels(self):
        target = self.allocate('objects', 'moon')
        original = self.inspect(target)
        self.assertEqual(original['law']['reprogram'], ['maker'])
        self.assertEqual(original['law']['law'], ['maker'])
        self.assertEqual(self.invoke(target, 'knock', {'word': 'hello'}, 'visitor')['kind'], 'committed')
        self.assertEqual(self.invoke(target, 'knock', {'word': 'hello', 'principal': 'maker'},
            'outsider')['data'], 'unauthorized')
        for who in ('compiler', 'visitor', 'steward'):
            result = self.call({'op': 'reprogram', 'object': target, 'principal': who,
                'intent': 'not-owner-' + who, 'expected': self.inspect(target),
                'protocol': forge.door(0), 'state': {}})
            self.assertEqual(result['data'], 'unauthorized', result)
        other = self.allocate('objects', 'visitor-door', 'visitor')
        self.assertEqual(self.inspect(other)['law']['reprogram'], ['visitor'])
        candidate = self.allocate('desks', 'spell')
        fields = {'source': 'not a spell', 'scenarios': 'not examples', 'target': target, 'principal': 'compiler'}
        self.assertEqual(self.invoke(candidate, 'submit', fields, 'visitor')['data'], 'unauthorized')
        accepted = self.invoke(candidate, 'submit', fields)
        self.assertEqual(accepted['data']['root']['state']['submitter'], 'maker')
        forged = self.invoke(candidate, 'compiled', {'artifact': 'a' * 64,
            'protocol': forge.door(0), 'roomArtifact': None}, 'maker')
        self.assertEqual(forged['data'], 'unauthorized')

    def test_raw_submission_guards_and_one_shot_candidate(self):
        candidate = self.allocate('desks', 'spell')
        root = self.inspect(candidate)
        fields = {'source': 'not a spell', 'scenarios': 'not examples', 'target': 'objects/door'}
        for key in fields:
            bad = dict(fields, **{key: ''})
            self.assertEqual(self.invoke(candidate, 'submit', bad)['kind'], 'refused')
            self.assertEqual(self.inspect(candidate), root)
        self.assertEqual(self.invoke(candidate, 'submit', fields)['kind'], 'committed')
        self.assertEqual(self.invoke(candidate, 'submit', fields)['data'], 'precondition failed')

    def test_queue_compile_then_explicit_revision_changes_actual_door_and_view(self):
        target = self.allocate('objects', 'paper')
        prior = self.inspect(target)
        for revision in (1, 2):
            candidate = self.allocate('desks', 'spell-' + str(revision))
            source = forge.spell_source(revision)
            pending = self.submit(candidate, target, source, forge.example_source(revision))
            receipt, artifact = self.compile(candidate, pending)
            self.assertEqual(receipt['kind'], 'committed', receipt)
            ready = receipt['data']['root']
            self.assertEqual(ready['state']['status'], 'ready')
            self.assertTrue(artifact['report']['passed'])
            self.assertEqual(artifact['sourceMaterial']['source'], source)
            self.assertEqual(artifact['sourceMaterial']['scenarios'], forge.example_source(revision))
            self.assertEqual(artifact['protocol']['commands']['knock']['result'][0], 'package')
            self.assertEqual(artifact['protocol']['commands']['knock']['result'][1]['modules'][0]['source'], source)
            self.assertEqual(self.inspect(target), prior)  # Compiling did not install.
            denied = self.client.adopt(candidate, target, 'compiler', 'compiler-adopt-' + str(revision), ready, prior)
            self.assertEqual(denied['kind'], 'refused')
            adopted = self.client.adopt(candidate, target, 'maker', 'adopt-' + str(revision), ready, prior)
            self.assertEqual(adopted['kind'], 'committed', adopted)
            self.assertEqual(self.inspect(target)['law'], prior['law'])
            card = affordances.card(self.view(target))
            self.assertIn('paper' if revision == 1 else 'silver', card['prose'])
            self.assertEqual(card['actions'][0]['fields'][0]['name'], 'word')
            word = 'please' if revision == 1 else 'moon'
            used = self.invoke(target, 'knock', {'word': word}, 'visitor')
            self.assertEqual(used['data']['result'], {
                1: 'The paper door swings open onto a tiny lantern-lit room.',
                2: 'The silver door opens into a room full of small moons.'}[revision])
            self.assertEqual(self.invoke(target, 'knock', {'word': word}, 'visitor', prior)['kind'], 'refused')
            prior = self.inspect(target)
        self.assertEqual(self.invoke(target, 'knock', {'word': 'please'}, 'visitor')['data'], 'precondition failed')

    def test_challenge_failure_is_grounded_and_cannot_be_adopted(self):
        target = self.allocate('objects', 'paper')
        original = self.inspect(target)
        candidate = self.allocate('desks', 'challenge', 'visitor')
        pending = self.submit(candidate, target, forge.spell_source(1),
            forge.challenge_source(), 'visitor')
        receipt, artifact = self.compile(candidate, pending)
        failed = receipt['data']['root']
        self.assertEqual(failed['state']['status'], 'failed')
        report = artifact['report']
        self.assertFalse(report['passed'])
        observed = report['outcomes'][0]
        self.assertEqual(observed['steps'][0]['receipt']['kind'], 'refused')
        self.assertEqual(observed['steps'][0]['receipt']['data'], 'precondition failed')
        self.assertIn({'at': 0, 'field': 'kind', 'expected': 'committed', 'actual': 'refused'}, observed['failures'])
        self.assertEqual(self.client.adopt(candidate, target, 'visitor', 'failed-adopt', failed, original)['kind'], 'refused')
        self.assertEqual(self.inspect(target), original)


if __name__ == '__main__':
    unittest.main()
