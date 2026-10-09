"""Retained installed source revises both behavior and its offered interface.

The source Writing card inspects an exact captured definition before revision.
No checked-in source, host file or native executable changes during this journey.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import desk
import source_store
import compiler_queue


class SourceSelfRevision(unittest.TestCase):
    def test_installed_definition_examples_release_and_changed_affordance(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        client = desk.Desk(home / 'world.json', home / 'artifacts', profile='compiled')
        packaging = desk.module('self_revision_objects', 'protocols/factories/package.py')
        protocol = packaging.object()
        law = {'profile': 'delvetalk-scoped-law', 'invoke': {'write': ['inhabitant']},
               'reprogram': ['inhabitant'], 'law': ['inhabitant'], 'read': ['inhabitant', 'compiler']}
        created = client.exchange({'op': 'create', 'object': 'self', 'principal': 'inhabitant',
            'intent': 'make-self', 'protocol': protocol, 'law': law})
        self.assertEqual(created['kind'], 'committed', created)
        before = client.inspect('self', principal='inhabitant')
        self.assertEqual(before['state']['model']['format'], 'delvetalk-compact-state')
        captured = deepcopy(before)
        candidate_law = {'profile': 'delvetalk-scoped-law',
            'invoke': {'requestCheck': ['inhabitant'], 'submit': ['inhabitant'], 'compiled': ['compiler'],
                       'failed': ['compiler'], 'adopt': ['inhabitant']},
            'reprogram': [], 'law': ['inhabitant'], 'read': ['inhabitant', 'compiler']}
        candidate_modules = desk.source_object.read_closure([
            ('Candidate', 'protocols/editor/Candidate.obend')])
        # Compatible authored residents may change their behavior without
        # matching a repository-approved source fingerprint.
        candidate_modules[-1]['source'] = candidate_modules[-1]['source'].replace(
            'Compiler check requested.', 'This resident requests its source check.')
        candidate_program = desk.source_object.load(candidate_modules, syntax='objective-bend-object', constructor='initial',
            arguments=[desk.source_object.data({'editorMode': False})])
        candidate = client.exchange({'op': 'create', 'object': 'revision', 'principal': 'inhabitant',
            'intent': 'make-revision', 'protocol': candidate_program, 'law': candidate_law})['data']['root']
        writing = desk.module('self_revision_writing', 'protocols/source-desk/package.py')
        writer_program = writing.writing('revision', 'self', 'objective-bend-object')
        writer_created = client.exchange({'op': 'create', 'object': 'writing', 'principal': 'inhabitant',
            'intent': 'make-writing', 'protocol': writer_program,
            'law': {'profile': 'delvetalk-scoped-law', 'invoke': {}, 'law': ['inhabitant'],
                    'reprogram': ['inhabitant'], 'read': ['inhabitant']}})
        self.assertEqual(writer_created['kind'], 'committed', writer_created)
        writer = writer_created['data']['root']
        writer_view = desk.projection.project(writer, 'writing')
        offers = desk.source_offers.capture(writer_view, {'writing': writer, 'self': before,
                                                        'revision': candidate})
        inspected = desk.source_offers.prepare(offers['inspect'], 'inhabitant', 'inspect-own-definition', {},
                                              database=client.database)
        self.assertEqual(inspected['kind'], 'inspection', inspected)
        self.assertEqual(inspected['value']['object'], 'self')
        self.assertEqual(inspected['document']['kind'], 'quote')
        self.assertEqual(inspected['document']['attribution'], 'self')
        forged = {'op': 'prepare-retained', 'object': 'writing', 'root': writer,
            'entry': 'prepareInspect', 'contribution': {}, 'observations': offers['inspect']['observations'],
            'principal': 'inhabitant', 'intent': 'uncaptured-definition',
            'definitions': [{'object': 'uncaptured', 'package': 'resident'}]}
        with self.assertRaisesRegex(ValueError, 'not captured'):
            desk.world.query(client.database, forged)
        installed = [{'name': node['attribution'], 'source': node['body']['code']}
                     for node in inspected['document']['body']['items']]
        definition = next(module['source'] for module in installed if module['name'] == 'Object')
        self.assertIn('def write(', definition)
        before_view = desk.projection.project(before, 'self')
        self.assertEqual(before_view['data']['actions']['write']['text'], 'Write')
        # The inhabitant edits the actually captured installed module. The view
        # label/template, method interface and executable method change together.
        revised = definition.replace('result: input.text}', 'result: textConcat("Revised: ", input.text)}')
        revised = revised.replace('label: "Write"', 'label: "Write a revision"')
        revised = revised.replace('text: "Write"', 'text: "Write a revision"')
        examples = b"""examples DelveTalk 1
case revised method is the offered method
law inhabitant
as inhabitant
send write
  text: The new voice.
expect result (String): Revised: The new voice.
"""
        contribution = {'module': 'Object', 'source': revised, 'scenarios': examples.decode()}
        rejected = desk.source_offers.prepare(offers['revise'], 'inhabitant', 'unknown-source-module',
            {**contribution, 'module': 'Invented'}, database=client.database)
        self.assertEqual(rejected['kind'], 'refused', rejected)
        self.assertEqual(client.inspect('self', principal='inhabitant'), before)
        request = desk.source_offers.request(offers['revise'], 'inhabitant', 'retain-revision',
                                            contribution, database=client.database)
        submitted = client.exchange(request)
        self.assertEqual(submitted['kind'], 'committed', submitted)
        submitted_root = client.inspect('revision', principal='inhabitant')
        retained_proposal = desk.candidate_state(submitted_root)['proposal']
        self.assertEqual(retained_proposal['format'], source_store.INLINE_MODULE_PROPOSAL)
        expected_modules = [{'name': module['name'],
                             'source': revised if module['name'] == 'Object' else module['source']}
                            for module in installed]
        self.assertEqual(retained_proposal['modules'], expected_modules)
        queue = compiler_queue.CompilerQueue(home / 'compiler', client.database, client.artifact_store)
        self.assertIsNone(queue.enqueue_offered('revision', 'compiler'))
        self.assertIsNone(queue.enqueue_offered('revision', 'compiler', expected=submitted_root))
        pending = submitted_root
        pending_view = desk.projection.project(pending, 'revision')
        pending_offers = desk.source_offers.capture(pending_view, {'revision': pending})
        inspected_proposal = desk.source_offers.prepare(pending_offers['inspect'], 'inhabitant',
            'inspect-authored-examples', {}, database=client.database)
        self.assertEqual(inspected_proposal['kind'], 'inspection', inspected_proposal)
        self.assertEqual(inspected_proposal['document']['items'][1]['body']['code'], examples.decode())
        check_request = desk.projection.request(pending_view, 'check',
                                                'inhabitant', 'request-source-examples')
        requested = client.exchange(check_request)
        self.assertEqual(requested['kind'], 'committed', requested)
        requested_root = client.inspect('revision', principal='inhabitant')
        self.assertEqual(desk.candidate_state(requested_root)['checkGeneration'], 1)
        self.assertNotIn('check', desk.projection.project(requested_root, 'revision')['data']['actions'])
        duplicate = {'op': 'invoke', 'object': 'revision', 'principal': 'inhabitant',
            'intent': 'duplicate-source-check', 'expected': requested_root,
            'command': 'requestCheck', 'input': {}}
        self.assertEqual(client.exchange(duplicate)['kind'], 'refused')
        self.assertEqual(client.inspect('revision', principal='inhabitant'), requested_root)
        self.assertEqual(client.exchange(check_request), requested)
        stale_report = {'op': 'invoke', 'object': 'revision', 'principal': 'compiler',
            'intent': 'report-before-check-generation', 'expected': pending,
            'command': 'failed', 'input': {'artifact': '', 'diagnostics': []}}
        self.assertEqual(client.exchange(stale_report)['kind'], 'refused')
        self.assertEqual(client.exchange({**stale_report, 'principal': 'inhabitant',
            'intent': 'ungranted-compiler-report', 'expected': requested_root})['kind'], 'refused')
        with self.assertRaises(ValueError):
            queue.enqueue_offered('revision', 'ungranted-compiler')
        job = queue.enqueue_offered('revision', 'compiler', expected=requested_root)
        self.assertIsNotNone(job)
        self.assertEqual(queue.enqueue_offered('revision', 'compiler', expected=requested_root)['job'], job['job'])
        queued_work = compiler_queue.load_job(queue.job_path(job['job']))['work']
        with self.assertRaisesRegex(ValueError, 'another source work request'):
            queue.enqueue('revision', 'compiler', queued_work['intent'], requested_root,
                          work={**queued_work, 'target': 'forged-target'})
        with self.assertRaisesRegex(ValueError, 'another candidate/root'):
            queue.enqueue('revision', 'compiler', queued_work['intent'], pending)
        self.assertEqual(client.exchange({**duplicate, 'intent': 'duplicate-queued-check'})['kind'], 'refused')
        self.assertEqual(client.inspect('revision', principal='inhabitant'), requested_root)
        run = queue.run(limit=1, deadline_seconds=60)
        self.assertEqual(run['errors'], [], run)
        status = queue.inspect(job['job'])
        self.assertEqual(status['phase'], 'finished', status)
        self.assertEqual(status['receipt']['kind'], 'committed', status)
        queued = compiler_queue.load_job(queue.job_path(job['job']))
        self.assertEqual(queued['work']['proposal'], retained_proposal)
        self.assertEqual(queued['work']['intent'], 'source-compile:revision:1')
        completion = client.check_attempt(queued['inputs'])['request']
        self.assertEqual(completion['expected'], requested_root)
        self.assertEqual(completion['intent'], 'source-compile:revision:1')
        completed_build = desk.load_artifact(client.artifact_store, completion['input']['artifact'])
        self.assertEqual(completion['command'], 'compiled',
                         {key: completed_build.get(key) for key in ('diagnostics', 'report')})
        ready = client.inspect('revision', principal='inhabitant')
        self.assertEqual(desk.candidate_state(ready)['status'], 'ready', desk.candidate_state(ready))
        artifact = desk.load_artifact(client.artifact_store, desk.candidate_state(ready)['artifact'])
        self.assertEqual([{key: module[key] for key in ('name', 'source')}
                         for module in artifact['sourceMaterial']['modules']], expected_modules)
        self.assertEqual(artifact['compilerWork'], queued['work'])
        self.assertTrue(artifact['report']['passed'], artifact)
        view = desk.projection.project(ready, 'revision')
        offer = desk.source_offers.capture(view, {'revision': ready, 'self': before})['release']
        request = desk.source_offers.request(offer, 'inhabitant', 'adopt-revision', {})
        accepted = client.exchange(request)
        self.assertEqual(accepted['kind'], 'committed', accepted)
        after = client.inspect('self', principal='inhabitant')
        # Preserve the inhabitant's state through the checked replacement
        # schema, rather than copying compact bytes bearing the old packet pin.
        before_state = desk.source_object.state_data(before)
        after_state = desk.source_object.state_data(after)
        self.assertEqual(after_state, before_state)
        self.assertNotEqual(after['state']['model']['schema'], before['state']['model']['schema'])
        self.assertEqual(after['law'], before['law'])
        old_inspection = desk.source_offers.prepare(offers['inspect'], 'inhabitant',
            'inspect-retained-version', {}, database=client.database)
        self.assertEqual(old_inspection['document'], inspected['document'])
        after_view = desk.projection.project(after, 'self')
        self.assertEqual(after_view['data']['actions']['write']['text'], 'Write a revision')
        self.assertIn('Write a revision', str(after['protocol']))
        action = desk.projection.request(after_view, 'write', 'inhabitant', 'try-revision')
        action['input'] = {'text': 'Hello again.'}
        receipt = client.exchange(action)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['result'], 'Revised: Hello again.')
        # A previously offered action remains bound to its old definition.
        stale = desk.projection.request(before_view, 'write', 'inhabitant', 'stale-old-offer')
        stale['input'] = {'text': 'Old voice.'}
        self.assertEqual(client.exchange(stale)['kind'], 'refused')
        self.assertEqual(client.exchange(request), accepted)
        self.assertEqual(captured, before)
        current = client.inspect('self', principal='inhabitant')
        revoked_law = {**law, 'read': ['compiler']}
        revoked = client.exchange({'op': 'law', 'object': 'self', 'principal': 'inhabitant',
            'intent': 'revoke-definition-read', 'expected': current, 'law': revoked_law})
        self.assertEqual(revoked['kind'], 'committed', revoked)
        with self.assertRaises(ValueError):
            desk.source_offers.prepare(offers['inspect'], 'inhabitant',
                'refuse-retained-definition-after-revocation', {}, database=client.database)


if __name__ == '__main__': unittest.main()
