"""Repeated source-owned editing: overlapping jobs, baseline drift and exact recovery.

Native hosts are prebuilt. No admission, compiler, observer or restoration is
mocked. Principals here are explicit local caller assertions; posts use the same
request shapes through manual intake.
"""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import compiler_queue
import editor
import source_store
import source_offers
import source_object
import workspace


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


generator = module('editor_generation_protocol', 'protocols/editor/generate.py')
desk = compiler_queue.desk
PACKAGE = ROOT / 'protocols/editor'
TARGET, EDITOR, FACTORY = 'instrument', 'editor', 'candidates'
MAKER, VISITOR, COMPILER = 'maker', 'visitor', 'compiler'
SOURCE = (PACKAGE / 'Counter.obend').read_text()
DOUBLE = SOURCE.replace('state.count + input.amount', 'state.count + 2 * input.amount')


class EditorGenerations(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='editor-generations-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / 'world'
        source_editor = generator.editor_artifact(TARGET, FACTORY)['protocol']
        seeds = [{'id': TARGET, 'syntax': 'objective-bend-spell@2', 'source': SOURCE.encode(),
            'law': {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'add': [MAKER, VISITOR]},
                    'reprogram': [MAKER], 'law': [MAKER]}},
            {'id': EDITOR, 'syntax': 'protocol-json@1', 'source': desk.canonical(source_editor),
             'law': generator.editor_law([MAKER])},
            {'id': FACTORY, 'syntax': 'protocol-json@1', 'source': desk.canonical(generator.factory(COMPILER, [MAKER])),
             'law': {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'make': [MAKER]},
                     'reprogram': [MAKER], 'law': [MAKER]}}]
        self.seed = workspace.initialize(self.home, seeds, principal='operator', profile='compiled',
            entry_objects=[EDITOR, TARGET], world_id='urn:test:repeatable-editor')
        self.client = desk.Desk(self.home / 'world.json', self.home / 'artifacts', profile='compiled')
        self.editor = editor.Editor(self.client, self.base / 'editor-custody')
        self.serial = 0

    def root(self, object_id):
        return self.client.inspect(object_id)

    def intent(self, label):
        self.serial += 1
        return label + ':' + str(self.serial)

    def phase(self):
        view = workspace.bootstrap.room.inspect_object(self.root(EDITOR), EDITOR, panel='phase')
        self.assertEqual(view['mode'], 'projection', view)
        return view['data']['prose']

    def invitation(self, key):
        snapshot = desk.world.snapshot(self.client.database)
        view = workspace.bootstrap.room.inspect_object(snapshot['objects'][EDITOR], EDITOR)
        self.assertEqual(view['mode'], 'projection', view)
        return source_offers.capture(view, snapshot['objects'], database=self.client.database)[key]

    def candidate_state(self, candidate):
        return desk.candidate_state(self.root(candidate))

    def prepared(self, name, source=SOURCE, examples='counter.examples'):
        baseline = copy.deepcopy(self.root(TARGET))
        invitation = self.invitation('make')
        intent = self.intent('make')
        if name == 'first':
            exchange = self.client.exchange
            def lost_allocation_reply(request):
                receipt = exchange(request)
                self.assertEqual(receipt['kind'], 'committed', receipt)
                raise RuntimeError('lost allocation reply after actual admission')
            with patch.object(self.client, 'exchange', side_effect=lost_allocation_reply):
                with self.assertRaisesRegex(RuntimeError, 'lost allocation reply'):
                    self.editor.interact(invitation, {'name': name}, MAKER, intent)
        allocation = self.editor.interact(invitation, {'name': name}, MAKER, intent)
        self.assertEqual(allocation['receipt']['kind'], 'committed', allocation)
        self.assertEqual(self.editor.interact(invitation, {'name': name}, MAKER, intent), allocation)
        plan = allocation['receipt']['data']['results'][2]
        candidate = next(iter(allocation['receipt']['data']['allocated']))
        submission = self.editor.interact(self.invitation('submit'),
            {'syntax': 'objective-bend-spell@2', 'source': source,
             'examples': (PACKAGE / examples).read_text()}, MAKER, self.intent('submit'))
        self.assertEqual(submission['receipt']['kind'], 'committed', submission)
        generation = {'candidate': candidate, 'generation': plan['generation'], 'baseline': baseline}
        self.assertEqual(self.candidate_state(candidate)['generation'], generation['generation'])
        self.assertEqual(self.candidate_state(candidate)['status'], 'pending')
        queue = compiler_queue.CompilerQueue(self.base / ('queue-' + name), self.client.database,
            self.client.artifact_store, profile='compiled')
        job = queue.enqueue(candidate, COMPILER, self.intent('check'), self.root(candidate))['job']
        return generation, queue, job

    def compile(self, generation, queue, job):
        outcome = queue.run(limit=1, deadline_seconds=60)
        self.assertEqual(outcome['errors'], [], outcome)
        self.assertEqual(outcome['blocked'], [], outcome)
        self.assertEqual(queue.inspect(job)['phase'], 'finished')
        return self.candidate_state(generation['candidate'])['status']

    def review(self, generation):
        if generation['candidate'] != self.current_candidate():
            # Adversarial stale report: source does not offer this recipe.
            return self.client.exchange({'op': 'transaction', 'principal': MAKER,
                'intent': self.intent('late-report'),
                'reads': {EDITOR: self.root(EDITOR), generation['candidate']: self.root(generation['candidate'])},
                'calls': [{'object': generation['candidate'], 'command': 'report', 'input': {}},
                          {'object': EDITOR, 'command': 'review', 'inputFrom': 0}]})
        result = self.editor.interact(self.invitation('review'), {}, MAKER, self.intent('review'))
        return result['receipt']

    def current_candidate(self):
        return source_object.plain(self.root(EDITOR)['state']['model'])['candidate']

    def adopt(self, generation):
        result = self.editor.interact(self.invitation('adopt'), {}, MAKER, self.intent('adopt'))
        if result['preparation']['kind'] != 'ready':
            return {'kind': result['preparation']['kind'], 'data': result['preparation']['message']}
        self.last_adoption_request = result['preparation']['request']
        return result['receipt']

    def play(self, amount=1):
        reply = self.client.exchange({'op': 'invoke', 'object': TARGET, 'principal': VISITOR,
            'intent': self.intent('play'), 'expected': self.root(TARGET), 'command': 'add', 'input': {'amount': amount}})
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply

    def test_substitute_reporter_cannot_replace_planned_candidate(self):
        made = self.editor.interact(self.invitation('make'), {'name': 'named'}, MAKER, self.intent('make-named'))
        self.assertEqual(made['receipt']['kind'], 'committed', made)
        plan = made['receipt']['data']['results'][2]
        expected_candidate = next(iter(made['receipt']['data']['allocated']))
        fake_protocol = {'profile': 'delvetalk-local-v1', 'initial': {},
            'commands': {'report': {'require': [], 'set': {}, 'outbox': [], 'result': ['literal',
                {'candidate': 'substitute', 'editor': EDITOR, 'generation': plan['generation'],
                 'target': TARGET, 'baselineVersion': plan['baselineVersion'], 'status': 'pending', 'program': ''}]}}}
        fake = self.client.exchange({'op': 'create', 'object': 'substitute', 'principal': MAKER,
            'intent': self.intent('create-substitute'), 'protocol': fake_protocol, 'law': [MAKER]})
        self.assertEqual(fake['kind'], 'committed', fake)
        before = {identity: self.root(identity) for identity in (EDITOR, expected_candidate, 'substitute')}
        report = self.client.exchange({'op': 'transaction', 'principal': MAKER, 'intent': self.intent('substitute-report'),
            'reads': {EDITOR: before[EDITOR], 'substitute': before['substitute']},
            'calls': [{'object': 'substitute', 'command': 'report', 'input': {}},
                      {'object': EDITOR, 'command': 'review', 'inputFrom': 0}]})
        self.assertEqual(report['kind'], 'refused', report)
        self.assertIn('Wrong generation', report['data'])
        for identity, root in before.items():
            self.assertEqual(self.root(identity), root)
        self.assertEqual(self.phase(), 'planned')

    def test_wrong_compiler_digest_rolls_back_entire_adoption(self):
        generation, _, _ = self.prepared('wrong-digest')
        candidate = generation['candidate']
        expected = self.root(candidate)
        build = desk.bounded_compile(expected, profile='compiled', artifact_store=self.client.artifact_store)
        self.assertTrue(build['passed'], build)
        inputs = {'object': candidate, 'principal': COMPILER, 'intent': self.intent('valid-check'), 'expected': expected}
        entry = self.client.prepare_check(inputs, build, desk.execution_profile('compiled'))
        wrong = copy.deepcopy(entry['request'])
        wrong['intent'] = self.intent('incorrect-compiler-digest')
        wrong['input']['program'] = 'a deliberately incorrect compiler digest'
        compiled = self.client.exchange(wrong)
        self.assertEqual(compiled['kind'], 'committed', compiled)
        self.assertEqual(self.review(generation)['kind'], 'committed')
        roots = {identity: self.root(identity) for identity in (EDITOR, TARGET, candidate)}
        refused = self.adopt(generation)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('actual approved reprogram', refused['data'])
        for identity, root in roots.items():
            self.assertEqual(self.root(identity), root, 'all staged approval/adopt/reprogram steps roll back')
        self.assertEqual(self.phase(), 'ready')

    def test_overlapping_jobs_rebase_adopt_restore_and_edit_again(self):
        initial_editor, initial_factory = self.root(EDITOR), self.root(FACTORY)
        unauthorized = self.client.exchange({'op': 'invoke', 'object': EDITOR, 'principal': VISITOR,
            'intent': self.intent('unauthorized-draft'), 'expected': initial_editor,
            'command': 'draft', 'input': {'name': 'uninvited'}})
        self.assertEqual(unauthorized['kind'], 'refused')
        self.assertEqual(self.root(EDITOR), initial_editor)
        forged_plan = self.client.exchange({'op': 'invoke', 'object': FACTORY, 'principal': MAKER,
            'intent': self.intent('copied-plan'), 'expected': initial_factory, 'command': 'make',
            'input': {'factory': FACTORY, 'name': 'copied', 'editor': EDITOR, 'generation': 1,
                      'target': TARGET, 'baselineVersion': self.root(TARGET)['version']}})
        self.assertEqual(forged_plan['kind'], 'refused')
        self.assertEqual(self.root(FACTORY), initial_factory)
        first, first_queue, first_job = self.prepared('first')
        second, second_queue, second_job = self.prepared('second', DOUBLE, 'double.examples')
        self.assertEqual(first['generation'], 1)
        self.assertEqual(second['generation'], 2)
        self.assertEqual(self.phase(), 'pending')
        editor_before_late = self.root(EDITOR)
        self.assertEqual(self.compile(first, first_queue, first_job), 'ready')
        self.assertEqual(self.root(EDITOR), editor_before_late, 'compiler completion changes only its immutable candidate')
        old_candidate = self.root(first['candidate'])
        late = self.review(first)
        self.assertEqual(late['kind'], 'refused')
        self.assertIn('Wrong generation', late['data'])
        self.assertEqual(self.root(EDITOR), editor_before_late)
        self.assertEqual(self.root(first['candidate']), old_candidate, 'late review rolls back its report too')
        self.assertEqual(self.compile(second, second_queue, second_job), 'ready')
        self.assertEqual(self.review(second)['kind'], 'committed')
        self.assertEqual(self.phase(), 'ready')

        # The target's actual current law and baseline remain separate from the
        # compiler. A normal visitor turn invalidates the reviewed migration.
        self.play()
        before_editor, before_candidate, before_target = self.root(EDITOR), self.root(second['candidate']), self.root(TARGET)
        drift = self.adopt(second)
        self.assertEqual(drift['kind'], 'refused')
        self.assertIn('target changed', drift['data'])
        self.assertEqual(self.root(EDITOR), before_editor)
        self.assertEqual(self.root(second['candidate']), before_candidate)
        self.assertEqual(self.root(TARGET), before_target)

        failed, failed_queue, failed_job = self.prepared('failed', DOUBLE, 'failure.examples')
        self.assertEqual(self.compile(failed, failed_queue, failed_job), 'failed')
        self.assertEqual(self.review(failed)['kind'], 'committed')
        self.assertEqual(self.phase(), 'failed')
        rebased, rebased_queue, rebased_job = self.prepared('rebased', DOUBLE, 'double.examples')
        self.assertEqual(self.compile(rebased, rebased_queue, rebased_job), 'ready')
        self.assertEqual(self.review(rebased)['kind'], 'committed')
        state_before = copy.deepcopy(self.root(TARGET)['state'])
        adopted = self.adopt(rebased)
        successful_adoption_request = copy.deepcopy(self.last_adoption_request)
        self.assertEqual(adopted['kind'], 'committed', adopted)
        self.assertEqual(self.phase(), 'adopted')
        def field(wire, name):
            return next(item['value'] for item in wire['fields'] if item['name'] == name)
        entries = field(self.root(EDITOR)['state']['model'], 'entries')
        adopted_entries = []
        while entries['label'] == 'cons':
            entry = field(entries['payload'], 'head')
            if field(entry, 'adopted')['value']:
                adopted_entries.append(field(entry, 'candidate')['value'])
            entries = field(entries['payload'], 'tail')
        self.assertEqual(adopted_entries, [rebased['candidate']])
        self.assertEqual(self.root(TARGET)['state'], state_before)
        actual = adopted['data']['results'][3]
        self.assertEqual(actual['object'], TARGET)
        self.assertEqual(actual['version'], self.root(TARGET)['version'])
        self.assertEqual(self.play()['data']['result'], 3)

        # Compiled code does not confer rights, and copied reprogram facts do not
        # acquire receiver-generated result provenance.
        forged = self.client.exchange({'op': 'invoke', 'object': EDITOR, 'principal': MAKER,
            'intent': self.intent('forged-finish'), 'expected': self.root(EDITOR), 'command': 'finish', 'input': actual})
        self.assertEqual(forged['kind'], 'refused')
        self.assertIn('actual approved reprogram', forged['data'])
        pending, _, _ = self.prepared('pending-after-adoption', SOURCE, 'counter.examples')
        self.assertEqual(pending['generation'], 5)
        self.assertEqual(self.phase(), 'pending')

        bundle, restored = self.base / 'history', self.base / 'restored'
        exported = workspace.bootstrap.export_bootstrap(self.home, bundle)
        workspace.bootstrap.restore_bootstrap(bundle, restored,
            expected_genesis=exported['genesis'], expected_head=exported['head'])
        self.assertEqual(desk.loads((restored / 'world.json').read_bytes()), desk.loads(self.client.database.read_bytes()))
        for generation, status in ((first, 'ready'), (second, 'ready'), (failed, 'failed'), (rebased, 'ready'), (pending, 'pending')):
            self.assertEqual(self.candidate_state(generation['candidate'])['status'], status)
        self.client = desk.Desk(restored / 'world.json', restored / 'artifacts', profile='compiled')
        self.editor = editor.Editor(self.client, self.base / 'restored-editor-custody')
        retry_before = self.client.database.read_bytes()
        # The old exact successful adoption survives newer editor generations.
        self.assertEqual(self.client.exchange(successful_adoption_request), adopted)
        self.assertEqual(self.client.database.read_bytes(), retry_before)
        continued, queue, job = self.prepared('continued', SOURCE, 'counter.examples')
        self.assertEqual(continued['generation'], 6)
        self.assertEqual(self.compile(continued, queue, job), 'ready')
        self.assertEqual(self.review(continued)['kind'], 'committed')
        self.assertEqual(self.adopt(continued)['kind'], 'committed')
        self.assertEqual(self.phase(), 'adopted')
        self.assertEqual(self.play()['data']['result'], 4)


if __name__ == '__main__':
    unittest.main()
