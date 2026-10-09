"""Installed prompt source and its form are revised through the same source workshop."""
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import desk
import compiler_queue
import source_packages
import interpret

class NotebookSourceRevision(unittest.TestCase):
    def test_inspected_prompt_template_and_form_revision_changes_next_source_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            client = desk.Desk(home / 'world.json', home / 'artifacts')
            notebook = desk.module('notebook_revision_package', 'protocols/account-heap/generate.py')
            candidate = desk.module('notebook_revision_candidate', 'protocols/editor/generate.py')
            law = {'profile': 'delvetalk-scoped-law', 'invoke': {'note': ['inhabitant'],
                'reviseInterpretation': ['inhabitant']}, 'reprogram': ['inhabitant'],
                'law': ['inhabitant'], 'read': ['inhabitant', 'compiler']}
            created = client.exchange({'op': 'create', 'object': 'notebook', 'principal': 'inhabitant',
                'intent': 'make-notebook', 'protocol': notebook.notebook(), 'law': law})
            self.assertEqual(created['kind'], 'committed', created)
            before = client.inspect('notebook', principal='inhabitant')
            candidate_law = {'profile': 'delvetalk-scoped-law', 'invoke': {'submit': ['inhabitant'],
                'requestCheck': ['inhabitant'], 'adopt': ['inhabitant'], 'compiled': ['compiler'],
                'failed': ['compiler']}, 'reprogram': [], 'law': ['inhabitant'],
                'read': ['inhabitant', 'compiler']}
            created = client.exchange({'op': 'create', 'object': 'source-desk', 'principal': 'inhabitant',
                'intent': 'make-template-candidate', 'protocol': candidate.candidate(editor_mode=False), 'law': candidate_law})
            self.assertEqual(created['kind'], 'committed', created)
            pending = created['data']['root']
            def source_job(root):
                package = root['protocol']['viewProgram']['package']
                modules = source_packages.validate_tables(root['protocol'])[package['name']]['modules']
                wire = interpret.native('interpretationRequest', [desk.source_object.state_data(root),
                    desk.source_object.data('Keep this thought.'), desk.source_object.variant('nil', desk.source_object.record({})),
                    desk.source_object.data({'object': 'notebook', 'principal': 'inhabitant'})], modules=modules)
                return desk.source_object.plain(next(item['value'] for item in wire['fields'] if item['name'] == 'job'))
            initial_job = source_job(before)
            self.assertIn('Vocabulary:', initial_job['system'])
            view = desk.projection.project(before, 'notebook', panel='interpretation')
            offers = desk.source_offers.capture(view, {'notebook': before, 'source-desk': pending})
            inspected = desk.source_offers.prepare(offers['inspectTemplates'], 'inhabitant', 'inspect-installed-templates', {}, database=client.database)
            self.assertEqual(inspected['kind'], 'inspection', inspected)
            modules = [{'name': item['attribution'], 'source': item['body']['code']} for item in inspected['document']['body']['items']]
            definition = next(item['source'] for item in modules if item['name'] == 'Interpretation')
            changed = definition.replace('Vocabulary:', 'Local conventions:').replace('vocabulary: "vocabulary"', 'vocabulary: "Local conventions"')
            self.assertNotEqual(changed, definition)
            examples = '''examples DelveTalk 1
case source prompt policy remains editable
law inhabitant
as inhabitant
send reviseInterpretation
  revision (String): source-template-v2
  section (String): vocabulary
  text (String): Locally named references only.
expect committed
'''
            request = desk.source_offers.request(offers['reviseTemplates'], 'inhabitant', 'retain-template-revision',
                {'module': 'Interpretation', 'source': changed, 'scenarios': examples}, database=client.database)
            submitted = client.exchange(request)
            self.assertEqual(submitted['kind'], 'committed', submitted)
            pending = client.inspect('source-desk', principal='inhabitant')
            view = desk.projection.project(pending, 'source-desk')
            checked = client.exchange(desk.projection.request(view, 'check', 'inhabitant', 'request-template-check'))
            self.assertEqual(checked['kind'], 'committed', checked)
            pending = client.inspect('source-desk', principal='inhabitant')
            queue = compiler_queue.CompilerQueue(home / 'compiler', client.database, client.artifact_store)
            self.assertIsNotNone(queue.enqueue_offered('source-desk', 'compiler', expected=pending))
            completed = queue.run(limit=1, deadline_seconds=90)
            self.assertEqual(completed['errors'], [], completed)
            ready = client.inspect('source-desk', principal='inhabitant')
            self.assertEqual(desk.candidate_state(ready)['status'], 'ready', desk.candidate_state(ready))
            adopted = client.adopt('source-desk', 'notebook', 'inhabitant', 'adopt-template-revision', ready, before)
            self.assertEqual(adopted['kind'], 'committed', adopted)
            after = client.inspect('notebook', principal='inhabitant')
            self.assertEqual(desk.source_object.state_data(after), desk.source_object.state_data(before))
            changed_job = source_job(after)
            self.assertIn('Local conventions:', changed_job['system'])
            self.assertNotIn('Vocabulary:', changed_job['system'])
            after_view = desk.projection.project(after, 'notebook', panel='interpretation')
            options = after_view['data']['actions']['reviseInterpretation']['fields']['section']['options']
            self.assertEqual(options['vocabulary'], 'Local conventions')
            self.assertEqual(client.adopt('source-desk', 'notebook', 'inhabitant', 'adopt-template-revision', ready, before), adopted)

if __name__ == '__main__': unittest.main()
