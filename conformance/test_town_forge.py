#!/usr/bin/env python3
"""Forge protocols allocate, compile and revise using the existing Lean host."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import affordances
import compiler_queue
import source_offers


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

    def prepared(self, name, fields, principal='maker', observations=None):
        self.serial += 1
        root = self.inspect(name)
        offers = source_offers.capture(room.inspect_object(root, name),
            {name: root, **(observations or {})}, database=self.client.database)
        invitation = next(iter(offers.values()))
        return source_offers.request(invitation, principal, 'prepare-' + str(self.serial),
            fields, database=self.client.database)

    def allocate(self, factory, name, principal='maker', **fields):
        request = self.prepared(factory, {'name': name, **fields}, principal)
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(self.call(request), receipt)
        child = factory + '/' + name
        self.assertEqual(affordances.allocated_refs(receipt), [{'object': child, 'root': self.inspect(child)}])
        return child

    def submit(self, candidate, target, source, scenarios, principal='maker'):
        writer = self.allocate('writers', 'write-' + str(self.serial), principal,
            candidate=candidate, target=target, syntax=forge.SPELL_SYNTAX)
        request = self.prepared(writer, {'source': source, 'scenarios': scenarios}, principal,
            {candidate: self.inspect(candidate), target: self.inspect(target)})
        result = self.call(request)
        self.assertEqual(result['kind'], 'committed', result)
        return self.inspect(candidate)

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

    def test_source_factories_offer_preparation_and_retain_exact_submission(self):
        for factory in ('objects', 'desks', 'writers'):
            opening = self.view(factory)
            self.assertEqual(opening['mode'], 'projection')
            self.assertTrue(source_offers.capture(opening, {factory: self.inspect(factory)},
                database=self.client.database))
        target = self.allocate('objects', 'paper')
        candidate = self.allocate('desks', 'spell')
        source, examples = forge.spell_source(), forge.example_source()
        pending = self.submit(candidate, target, source, examples)
        state = desk.candidate_state(pending)
        self.assertEqual(state['proposal'], {'syntax': forge.SPELL_SYNTAX, 'source': source, 'scenarios': examples})
        self.assertEqual(state['migration'], self.inspect(target)['state'])
        self.assertEqual(state['submitter'], 'maker')

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
        fields = {'proposal': {'syntax': forge.SPELL_SYNTAX, 'source': 'not a spell', 'scenarios': 'not examples'}, 'migration': {}, 'target': target, 'principal': 'compiler'}
        self.assertEqual(self.invoke(candidate, 'submit', fields, 'visitor')['data'], 'unauthorized')
        accepted = self.invoke(candidate, 'submit', fields)
        self.assertEqual(desk.candidate_state(accepted['data']['root'])['submitter'], 'maker')
        forged = self.invoke(candidate, 'compiled', {'artifact': 'a' * 64,
            'protocol': forge.door(0), 'roomArtifact': None}, 'maker')
        self.assertEqual(forged['data'], 'unauthorized')

    def test_source_writing_questions_and_candidate_one_shot(self):
        target = self.allocate('objects', 'door')
        candidate = self.allocate('desks', 'spell')
        writer = self.allocate('writers', 'write', candidate=candidate, target=target, syntax=forge.SPELL_SYNTAX)
        root = self.inspect(candidate)
        with self.assertRaises(source_offers.PreparationOutcome) as caught:
            self.prepared(writer, {'source': '', 'scenarios': ''}, observations={candidate: root, target: self.inspect(target)})
        self.assertEqual(caught.exception.outcome['kind'], 'question')
        self.assertEqual(self.inspect(candidate), root)
        self.submit(candidate, target, forge.spell_source(), forge.example_source())
        fields = {'proposal': {'syntax': forge.SPELL_SYNTAX, 'source': forge.spell_source(), 'scenarios': forge.example_source()}, 'migration': {}, 'target': target}
        self.assertEqual(self.invoke(candidate, 'submit', fields)['kind'], 'refused')

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
            self.assertEqual(desk.candidate_state(ready)['status'], 'ready')
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
        self.assertEqual(desk.candidate_state(failed)['status'], 'failed')
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
