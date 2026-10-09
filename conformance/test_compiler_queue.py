#!/usr/bin/env python3
"""Real local compiler/admission evidence; transport interruption is the only mock."""
import copy
import fcntl
import importlib.util
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('compiler_queue', ROOT / 'scripts/compiler_queue.py')
queue_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue_module)
desk = queue_module.desk


@unittest.skipUnless((ROOT / '.lake/build/bin/delvetalk-transactions').is_file(), 'build transactions host first')
class CompilerQueueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.client = desk.Desk(self.path / 'world.json', self.path / 'artifacts')
        self.queue = queue_module.CompilerQueue(self.path / 'queue', self.client.database, self.client.artifact_store)
        self.source = (ROOT / 'protocols/counter/protocol.json').read_bytes()
        self.scenarios = (ROOT / 'protocols/counter/scenarios.json').read_bytes()
        self.law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {
            'submit': ['author'], 'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': ['reviewer']},
            'law': ['owner'], 'reprogram': []}
        self.root = self.client.create('candidate', 'owner', 'create', self.law)['data']['root']
        self.target = self.client.exchange({'op': 'create', 'object': 'target', 'principal': 'owner',
            'intent': 'create-target', 'protocol': desk.loads(self.source), 'law': ['reviewer']})['data']['root']

    def submit(self, source=None):
        return self.client.submit('candidate', 'author', 'submit', self.root, 'protocol-json@1',
                                  self.source if source is None else source, self.scenarios,
                                  {'count': 42}, 'target')['data']['root']

    def enqueue(self, pending):
        return self.queue.enqueue('candidate', 'compiler', 'compile', pending)['job']

    def replace_job(self, identity, change):
        """Construct a formerly captured pin for mismatch/recovery tests, never edit runtime."""
        path = self.queue.job_path(identity)
        job = desk.loads(path.read_bytes())
        change(job)
        replacement = desk.digest(job)
        desk.immutable(self.queue.job_path(replacement), job)
        path.unlink()  # Only this test's disposable custody.
        return replacement

    def test_compile_is_restartable_exact_and_never_adopts(self):
        pending = self.submit()
        identity = self.enqueue(pending)
        self.assertEqual(self.enqueue(pending), identity)
        job = desk.loads(self.queue.job_path(identity).read_bytes())
        self.assertEqual(job['inputs']['expected'], pending)
        self.assertEqual(job['inputs']['expected']['state']['proposal']['source'].encode(), self.source)
        report = self.queue.run()
        self.assertEqual(report['errors'], [])
        result = self.queue.inspect(identity)
        self.assertEqual(result['phase'], 'finished')
        self.assertEqual(result['receipt']['data']['root']['state']['status'], 'ready')
        artifact = desk.load_artifact(self.client.artifact_store, result['artifact'])
        self.assertTrue(artifact['report']['passed'])
        self.assertEqual(artifact['candidateRootSha256'], desk.digest(pending))
        self.assertEqual(self.client.inspect('target'), self.target)
        with mock.patch.object(queue_module.worker, 'command', side_effect=AssertionError('recompiled')):
            self.assertEqual(self.queue.run()['processed'], [])
        altered = copy.deepcopy(pending)
        altered['state']['proposal']['source'] += '\n'
        with self.assertRaisesRegex(ValueError, 'intent already bound'):
            self.enqueue(altered)

    def test_failed_source_retains_diagnostics(self):
        identity = self.enqueue(self.submit(b'{invalid JSON'))
        self.assertEqual(self.queue.run()['errors'], [])
        result = self.queue.inspect(identity)
        self.assertEqual(result['receipt']['data']['root']['state']['status'], 'failed')
        artifact = desk.load_artifact(self.client.artifact_store, result['artifact'])
        self.assertFalse(artifact['passed'])
        self.assertTrue(artifact['diagnostics'])
        self.assertEqual(self.client.inspect('target'), self.target)

    def test_interrupted_preparation_reuses_build_without_mutating_compiler_api(self):
        pending = self.submit()
        identity = self.enqueue(pending)
        original = desk.bounded_compile
        with mock.patch.object(desk.Desk, 'prepare_check', side_effect=KeyboardInterrupt('lost preparation')):
            with self.assertRaises(KeyboardInterrupt):
                queue_module.execute_job(self.queue.job_path(identity))
        self.assertIs(desk.bounded_compile, original)
        self.assertEqual(self.client.inspect('candidate'), pending)
        compiled = self.queue.state / 'compiled' / (identity + '.json')
        saved = compiled.read_bytes()
        self.assertEqual(self.queue.run()['errors'], [])
        self.assertEqual(compiled.read_bytes(), saved)
        self.assertEqual(self.queue.inspect(identity)['phase'], 'finished')
        self.assertEqual(len(list((self.client.artifact_store / 'builds').glob('*.json'))), 1)

    def test_compiler_authority_is_still_decided_by_lean(self):
        pending = self.submit()
        identity = self.queue.enqueue('candidate', 'author', 'unauthorized-compile', pending)['job']
        self.assertEqual(self.queue.run()['errors'], [])
        result = self.queue.inspect(identity)
        self.assertEqual(result['phase'], 'finished')
        self.assertEqual(result['receipt']['kind'], 'refused')
        self.assertEqual(self.client.inspect('candidate'), pending)
        self.assertEqual(self.client.inspect('target'), self.target)

    def test_stale_candidate_does_not_compile(self):
        pending = self.submit()
        identity = self.enqueue(pending)
        self.client.exchange({'op': 'law', 'object': 'candidate', 'principal': 'owner', 'intent': 'change-law',
                              'expected': pending, 'law': self.law})
        report = self.queue.run(max_attempts=1)
        self.assertIn('candidate changed', report['errors'][0]['error'])
        self.assertFalse(list((self.client.artifact_store / 'builds').glob('*.json')))
        self.assertEqual(self.queue.run(max_attempts=1)['blocked'][0]['job'], identity)

    def test_runtime_mismatch_is_refused_before_compile(self):
        identity = self.enqueue(self.submit())
        identity = self.replace_job(identity, lambda job: job['runtime']['files'].update({'scripts/propose.py': '0' * 64}))
        report = self.queue.run()
        self.assertIn('runtime changed', report['errors'][0]['error'])
        self.assertFalse(list((self.client.artifact_store / 'builds').glob('*.json')))
        self.assertEqual(self.queue.inspect(identity)['phase'], 'queued')

    def test_lost_reply_recovers_even_after_runtime_and_candidate_change(self):
        identity = self.enqueue(self.submit())
        original = queue_module.worker.command
        def lost_reply(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt('reply lost after real durable admission')
        with mock.patch.object(queue_module.worker, 'command', side_effect=lost_reply):
            with self.assertRaises(KeyboardInterrupt):
                self.queue.run()
        self.assertEqual(self.queue.inspect(identity)['phase'], 'running')
        self.assertEqual(self.client.inspect('candidate')['state']['status'], 'ready')
        identity = self.replace_job(identity, lambda job: job['runtime']['files'].update({'scripts/propose.py': '0' * 64}))
        # Lost return cannot turn completed historical admission into new compilation.
        self.assertEqual(self.queue.run()['errors'], [])
        self.assertEqual(self.queue.inspect(identity)['phase'], 'finished')
        self.assertEqual(len(desk.loads(self.client.database.read_bytes())['receipts']), 4)

    def test_real_world_lock_timeout_is_bounded_and_retryable(self):
        identity = self.enqueue(self.submit())
        with open(str(self.client.database) + '.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            started = time.monotonic()
            report = self.queue.run(deadline_seconds=0.15, max_attempts=1)
            self.assertLess(time.monotonic() - started, 2)
            self.assertTrue(report['errors'])
            self.assertTrue(report['deadlineReached'])
        self.assertEqual(self.queue.run(max_attempts=1)['blocked'][0]['job'], identity)
        self.queue.retry(identity)
        self.assertEqual(self.queue.run()['errors'], [])
        self.assertEqual(self.queue.inspect(identity)['phase'], 'finished')

    def test_queue_lock_wait_and_enqueue_stale_are_bounded(self):
        pending = self.submit()
        self.queue.state.mkdir()
        with (self.queue.state / '.compiler.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            started = time.monotonic()
            self.assertTrue(self.queue.run(deadline_seconds=0.05)['lockTimedOut'])
            self.assertLess(time.monotonic() - started, 1)
            with self.assertRaises(TimeoutError):
                self.queue.enqueue('candidate', 'compiler', 'compile', pending, deadline_seconds=0.05)
        altered = copy.deepcopy(pending)
        altered['state']['proposal']['source'] += '\n'
        with self.assertRaisesRegex(ValueError, 'candidate changed'):
            self.enqueue(altered)
        self.assertFalse(list((self.queue.state / 'jobs').glob('*.json')))

    def test_nonfinite_budget_and_queue_rebinding_are_refused(self):
        self.enqueue(self.submit())
        for seconds in (float('nan'), float('inf'), 0, 301):
            with self.assertRaises(ValueError):
                self.queue.run(deadline_seconds=seconds)
        different = queue_module.CompilerQueue(self.queue.state, self.path / 'another.json', self.client.artifact_store)
        with self.assertRaisesRegex(ValueError, 'belongs to another'):
            different.run()


if __name__ == '__main__':
    unittest.main()
