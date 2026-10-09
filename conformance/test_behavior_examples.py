"""Inspectable authored examples compose native objects in disposable worlds."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import desk
import compiler_queue

PACKAGE = ROOT / 'protocols/behavior-examples'
examples = desk.module('behavior_spell_examples', 'syntaxes/spell_examples.py')
proposal_runner = desk.module('behavior_proposal_runner', 'scripts/propose.py')

class BehaviorExamples(unittest.TestCase):
    def test_transport_contract_keeps_explicit_targets_and_native_dataflow(self):
        cases = examples.parse((PACKAGE / 'relay.examples').read_text())
        proposal_runner.validate_scenarios(cases)
        self.assertEqual(cases[0]['fixtures'], ['peer'])
        first = cases[0]['steps'][0]
        self.assertEqual(first['calls'], [
            {'object': 'candidate', 'command': 'relay', 'input': {'amount': 2}},
            {'object': 'peer', 'command': 'relay', 'inputFrom': 0}])
        for source in [
                'fixture peer\nfixture peer\nlaw inhabitant\nas inhabitant\nsend count\nexpect committed',
                'law inhabitant\nas inhabitant\nsend absent/count\nexpect committed',
                'law inhabitant\nas inhabitant\ntransaction\ncall candidate/relay\nfrom previous\nexpect committed',
                'law inhabitant\nas inhabitant\ntransaction\ncall candidate/relay\n  amount (Nat): 1\ncall candidate/relay\nfrom previous\n  amount (Nat): 2\nexpect committed']:
            with self.assertRaises(ValueError):
                examples.parse('examples DelveTalk 1\ncase invalid\n' + source + '\n')
        malformed = deepcopy(cases)
        malformed[0]['steps'][0]['calls'][1]['inputFrom'] = 1
        with self.assertRaisesRegex(ValueError, 'earlier call'):
            proposal_runner.validate_scenarios(malformed)

    def test_inhabitant_inspects_revises_and_runs_examples_through_offered_candidate_check(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        client = desk.Desk(home / 'world.json', home / 'artifacts', profile='compiled')
        source = (PACKAGE / 'Relay.obend').read_text()
        modules = desk.source_object.read_closure([('Relay', PACKAGE / 'Relay.obend')])
        protocol = desk.source_object.load(modules, syntax='objective-bend-object')
        target_law = {'profile': 'delvetalk-scoped-law',
            'invoke': {'relay': ['inhabitant'], 'count': ['inhabitant']},
            'reprogram': ['inhabitant'], 'law': ['inhabitant'], 'read': ['inhabitant', 'compiler']}
        created = client.exchange({'op': 'create', 'object': 'hands', 'principal': 'inhabitant',
            'intent': 'create-hands', 'protocol': protocol, 'law': target_law})
        self.assertEqual(created['kind'], 'committed', created)
        target = created['data']['root']
        candidate_modules = desk.source_object.read_closure([('Candidate', 'protocols/editor/Candidate.obend')])
        candidate_protocol = desk.source_object.load(candidate_modules, syntax='objective-bend-object',
            constructor='initial', arguments=[desk.source_object.data({'editorMode': False})])
        candidate_law = {'profile': 'delvetalk-scoped-law',
            'invoke': {'submit': ['inhabitant'], 'requestCheck': ['inhabitant'],
                'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': ['inhabitant']},
            'reprogram': [], 'law': ['inhabitant'], 'read': ['inhabitant', 'compiler']}
        writing_package = desk.module('behavior_writing_package', 'protocols/source-desk/package.py')
        queue = compiler_queue.CompilerQueue(home / 'compiler', client.database, client.artifact_store)
        good_examples = (PACKAGE / 'relay.examples').read_text()
        failed_examples = good_examples.replace('expect result (Nat): 2', 'expect result (Nat): 99', 1)
        reports = []
        for iteration, authored_examples in enumerate([failed_examples, good_examples]):
            candidate_id, writing_id = 'variation-' + str(iteration), 'writing-' + str(iteration)
            made = client.exchange({'op': 'create', 'object': candidate_id, 'principal': 'inhabitant',
                'intent': 'create-' + candidate_id, 'protocol': candidate_protocol, 'law': candidate_law})
            self.assertEqual(made['kind'], 'committed', made)
            candidate = made['data']['root']
            writer_protocol = writing_package.writing(candidate_id, 'hands', 'objective-bend-object')
            made = client.exchange({'op': 'create', 'object': writing_id, 'principal': 'inhabitant',
                'intent': 'create-' + writing_id, 'protocol': writer_protocol,
                'law': {'profile': 'delvetalk-scoped-law', 'invoke': {}, 'reprogram': ['inhabitant'],
                    'law': ['inhabitant'], 'read': ['inhabitant']}})
            self.assertEqual(made['kind'], 'committed', made)
            writer = made['data']['root']
            view = desk.projection.project(writer, writing_id)
            offers = desk.source_offers.capture(view, {writing_id: writer, candidate_id: candidate, 'hands': target})
            inspected = desk.source_offers.prepare(offers['inspect'], 'inhabitant',
                'inspect-source-' + str(iteration), {}, database=client.database)
            self.assertEqual(inspected['kind'], 'inspection', inspected)
            retained = next(item['body']['code'] for item in inspected['document']['body']['items']
                            if item['attribution'] == 'Relay')
            self.assertEqual(retained, source)
            revised = retained.replace('A hand to hand relay', 'Two hands, one passage') if iteration else retained
            request = desk.source_offers.request(offers['revise'], 'inhabitant',
                'revise-source-and-examples-' + str(iteration),
                {'module': 'Relay', 'source': revised, 'scenarios': authored_examples}, database=client.database)
            submitted = client.exchange(request)
            self.assertEqual(submitted['kind'], 'committed', submitted)
            pending = client.inspect(candidate_id, principal='inhabitant')
            pending_view = desk.projection.project(pending, candidate_id)
            pending_offers = desk.source_offers.capture(pending_view, {candidate_id: pending})
            document = desk.source_offers.prepare(pending_offers['inspect'], 'inhabitant',
                'inspect-examples-' + str(iteration), {}, database=client.database)
            self.assertEqual(document['document']['items'][1]['body']['code'], authored_examples)
            check = desk.projection.request(pending_view, 'check', 'inhabitant', 'request-check-' + str(iteration))
            self.assertEqual(client.exchange(check)['kind'], 'committed')
            job = queue.enqueue_offered(candidate_id, 'compiler')
            self.assertIsNotNone(job)
            run = queue.run(limit=1, deadline_seconds=60)
            self.assertEqual(run['errors'], [], run)
            status = queue.inspect(job['job'])
            self.assertEqual(status['phase'], 'finished', status)
            self.assertEqual(status['receipt']['kind'], 'committed', status)
            root = client.inspect(candidate_id, principal='inhabitant')
            state = desk.candidate_state(root)
            self.assertEqual(state['checkRequester'], 'inhabitant')
            self.assertEqual(state['status'], 'failed' if iteration == 0 else 'ready', state)
            artifact = desk.load_artifact(client.artifact_store, state['artifact'])
            self.assertEqual(artifact['sourceMaterial']['scenarios'], authored_examples)
            self.assertEqual(artifact['compilerWork']['object'], candidate_id)
            self.assertEqual(artifact['compilerWork']['proposal'], state['proposal'])
            self.assertEqual(artifact['report']['passed'], iteration == 1, artifact)
            reports.append(artifact['report'])
            # Example identities exist only inside the disposable compiler world.
            self.assertEqual(client.inspect('hands', principal='inhabitant'), target)
            self.assertNotIn('peer', desk.world.snapshot(client.database)['objects'])
        self.assertTrue(reports[0]['outcomes'][0]['failures'])
        self.assertEqual(reports[1]['outcomes'][0]['failures'], [])
        receipts = reports[1]['outcomes'][0]['steps']
        self.assertEqual(receipts[0]['receipt']['data']['results'], [{'amount': 2}, {'amount': 2}])
        self.assertEqual(receipts[4]['receipt']['kind'], 'refused')
        self.assertEqual(receipts[5]['receipt']['data']['result'], 2)
        self.assertEqual(receipts[6]['receipt']['data']['result'], 5)
        self.assertEqual(receipts[7]['receipt']['data'], 'derived source result type differs from recipient input')
        self.assertEqual(receipts[8]['receipt']['data']['result'], 2)
        self.assertEqual(receipts[9]['receipt']['data']['result'], 5)

if __name__ == '__main__': unittest.main()
