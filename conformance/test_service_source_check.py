"""Actual Service epoch and source-offered compiler work receiving."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import service
import workspace
from conformance.source_custody_fixture import counter_source


class SourceServiceCheck(unittest.TestCase):
    def test_initialize_epoch_discovers_checks_and_reconciles_source_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            author = service.clerk.delve.DID
            public = base / 'public'
            law = {'profile': 'delvetalk-scoped-law', 'invoke': {'add': [author]},
                   'reprogram': [author], 'law': [author], 'read': 'public'}
            candidate_law = {'profile': 'delvetalk-scoped-law', 'invoke': {
                'submit': [author], 'requestCheck': [author], 'compiled': ['compiler'],
                'failed': ['compiler'], 'adopt': [author]}, 'reprogram': [], 'law': [author], 'read': 'public'}
            modules = service.desk.source_object.read_closure([
                ('Candidate', 'protocols/editor/Candidate.obend')])
            modules[-1]['source'] = modules[-1]['source'].replace(
                'initial({editorMode: true})', 'initial({editorMode: false})')
            seed = workspace.initialize(public, [{'id': 'target', 'syntax': 'objective-bend-object',
                'source': counter_source(), 'law': law}, {'id': 'candidate', 'syntax': 'objective-bend-object',
                'modules': modules, 'law': candidate_law}], entry_objects=['target'], principal=author)
            client = service.desk.Desk(public / 'world.json', public / 'artifacts')
            target = client.inspect('target', principal=author)
            candidate = client.inspect('candidate', principal=author)
            clerk = service.clerk.Clerk(base / 'clerk')
            clerk.attach(public, {'target': target, 'candidate': candidate}, [author], expected_genesis=seed['genesis'],
                         expected_seed_head=seed['head'], runtime_profile='compiled')
            operator = service.Service(base / 'service')
            operator.initialize(public, clerk.state, 'compiler', public_genesis=seed['genesis'])
            operator.check_epoch(operator.config())
            examples = service.canonical([{'name': 'source-add', 'law': ['player'], 'steps': [
                {'principal': 'player', 'command': 'add', 'input': {'amount': 3},
                 'root': 'initial', 'kind': 'committed', 'result': 3}]}])
            migration = {'model': service.desk.source_object.compact_state(target['protocol'],
                service.desk.source_object.data({'count': 7}), entry='describe', path=[{'field': 'initial'}])}
            submitted = client.submit('candidate', author, 'submit', candidate, 'objective-bend-object',
                                      counter_source(), examples, migration, 'target')['data']['root']
            view = service.desk.projection.project(submitted, 'candidate')
            request = service.desk.projection.request(view, 'check', author, 'request-check')
            self.assertEqual(client.exchange(request)['kind'], 'committed')
            requested = client.inspect('candidate', principal=author)
            result = operator.tick(deadline_seconds=120)
            self.assertEqual(result['errors'], [], result)
            jobs = result['phases']['enqueueCompilers']['jobs']
            self.assertEqual(len(jobs), 1, result)
            queue = operator.compiler(operator.config(), 2048)
            job = service.compiler_queue.load_job(queue.job_path(jobs[0]['job']))
            self.assertEqual(job['inputs']['expected'], requested)
            self.assertEqual(job['inputs']['intent'], 'source-compile:candidate:1')
            self.assertEqual(service.desk.candidate_state(client.inspect('candidate', principal=author))['status'], 'ready')
            self.assertEqual(client.inspect('target', principal=author), target)
            self.assertNotIn('candidateStatus', result['phases']['reconcile']['compiler'][0])
            operator.check_epoch(operator.config())
            again = operator.tick(deadline_seconds=120)
            self.assertEqual(again['errors'], [], again)
            self.assertEqual(len(list((queue.state / 'jobs').glob('*.json'))), 1)


if __name__ == '__main__': unittest.main()
