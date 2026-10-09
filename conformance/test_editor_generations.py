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
        source_editor = generator.editor_source(TARGET, FACTORY)
        seeds = [{'id': TARGET, 'syntax': 'objective-bend-spell@2', 'source': SOURCE.encode(),
            'law': {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'add': [MAKER, VISITOR]},
                    'reprogram': [MAKER], 'law': [MAKER]}},
            {'id': EDITOR, 'syntax': 'objective-bend-spell@3', 'source': source_editor.encode(),
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

    def prepared(self, name, source=SOURCE, examples='counter.examples', migration=None):
        proposal = source_store.prepare_proposal(self.client.artifact_store, 'objective-bend-spell@2',
            source.encode(), (PACKAGE / examples).read_bytes())
        args = (EDITOR, TARGET, FACTORY, name, MAKER, self.intent('generation'),
                self.root(EDITOR), self.root(TARGET), self.root(FACTORY), proposal,
                copy.deepcopy(self.root(TARGET)['state']) if migration is None else migration)
        if name == 'first':
            exchange = self.client.exchange
            def lost_allocation_reply(request):
                receipt = exchange(request)
                self.assertEqual(receipt['kind'], 'committed', receipt)
                raise RuntimeError('lost allocation reply after actual admission')
            with patch.object(self.client, 'exchange', side_effect=lost_allocation_reply):
                with self.assertRaisesRegex(RuntimeError, 'lost allocation reply'):
                    self.editor.generation(*args)
        generation = self.editor.generation(*args)
        self.assertEqual(generation['phase'], 'retained', generation)
        self.assertEqual(self.editor.generation(*args), generation)
        candidate = generation['candidate']
        self.assertEqual(self.root(candidate)['state']['generation'], generation['generation'])
        self.assertEqual(self.root(candidate)['state']['status'], 'pending')
        self.assertEqual(generation['baseline'], args[7])
        queue = compiler_queue.CompilerQueue(self.base / ('queue-' + name), self.client.database,
            self.client.artifact_store, profile='compiled')
        job = queue.enqueue(candidate, COMPILER, self.intent('check'), self.root(candidate))['job']
        return generation, queue, job

    def compile(self, generation, queue, job):
        outcome = queue.run(limit=1, deadline_seconds=60)
        self.assertEqual(outcome['errors'], [], outcome)
        self.assertEqual(outcome['blocked'], [], outcome)
        self.assertEqual(queue.inspect(job)['phase'], 'finished')
        return self.root(generation['candidate'])['state']['status']

    def review(self, generation):
        return self.editor.review(EDITOR, generation['candidate'], MAKER, self.intent('review'),
                                 self.root(EDITOR), self.root(generation['candidate']))

    def adopt(self, generation):
        self.last_adoption_request = editor.adoption_request(EDITOR, generation['candidate'], TARGET, MAKER,
            self.intent('adopt'), self.root(EDITOR), self.root(generation['candidate']), self.root(TARGET))
        return self.client.exchange(self.last_adoption_request)

    def play(self, amount=1):
        reply = self.client.exchange({'op': 'invoke', 'object': TARGET, 'principal': VISITOR,
            'intent': self.intent('play'), 'expected': self.root(TARGET), 'command': 'add', 'input': {'amount': amount}})
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply

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
        self.assertIn('Target drifted', drift['data'])
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
            self.assertEqual(self.root(generation['candidate'])['state']['status'], status)
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
