"""Bounded operator composition with actual Lean and fake GET-only repository transport."""
import copy
import fcntl
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import service as s
import source_store
import manage
import workspace

AUTHOR = s.clerk.delve.DID


class PDS:
    def __init__(self):
        self.records = {}
        self.calls = []

    def __call__(self, method, base, nsid, *, params=None, **kwargs):
        assert method == 'GET' and base == s.clerk.PDS and not kwargs
        self.calls.append(nsid)
        author = params['repo']
        if nsid.endswith('describeRepo'):
            return {'did': author, 'didDoc': {'id': author, 'service': [{
                'id': '#atproto_pds', 'type': 'AtprotoPersonalDataServer', 'serviceEndpoint': base}]}}
        assert nsid.endswith('getRecord')
        return copy.deepcopy(self.records[params['rkey']])


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.world = self.base / 'public'
        self.source = (ROOT / 'protocols/counter/protocol.json').read_bytes()
        raw = workspace.bootstrap.canonical(workspace.bootstrap.desk_module.module('service_candidate_package', 'protocols/source-desk/package.py').candidate())
        law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'submit': [AUTHOR],
            'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': ['reviewer']},
            'law': ['owner'], 'reprogram': []}
        self.seed = workspace.initialize(self.world, [
            {'id': 'target', 'syntax': 'protocol-json@1', 'source': self.source, 'law': ['reviewer']},
            {'id': 'candidate', 'syntax': 'protocol-json@1', 'source': raw, 'law': law}],
            entry_objects=['target'], principal='owner', profile='compiled')
        self.pds = PDS()
        self.clerk = s.clerk.Clerk(self.base / 'clerk', self.pds)
        roots = self.snapshot()['objects']
        self.clerk.attach(self.world, roots, [AUTHOR], expected_genesis=self.seed['genesis'],
                          expected_seed_head=self.seed['head'], runtime_profile='compiled')
        self.root = roots['candidate']
        self.app = s.Service(self.base / 'service', receiver=self.clerk.receive)
        self.app.initialize(self.world, self.clerk.state, 'compiler', public_genesis=self.seed['genesis'])
        self.initial_target = self.snapshot()['objects']['target']

    def snapshot(self):
        return s.loads((self.world / 'world.json').read_bytes())

    def submit(self, key='proposal', *, object_id='candidate', root=None):
        proposal = source_store.prepare_proposal(self.world / 'artifacts', 'protocol-json@1', self.source,
            (ROOT / 'protocols/counter/scenarios.json').read_bytes())
        wire = {'op': 'invoke', 'object': object_id, 'expected': self.root if root is None else root, 'command': 'submit',
                'input': {'proposal': proposal, 'migration': {'count': 7}, 'target': 'target'}}
        uri = 'at://' + AUTHOR + '/' + s.clerk.COLLECTION + '/' + key
        record = s.worker.receipts.encode('request', s.canonical(wire).decode())
        self.pds.records[key] = {'uri': uri, 'cid': 'cid-' + key, 'value': record}
        self.app.enqueue(uri, 'cid-' + key)
        return uri, 'cid-' + key

    def checked_tick(self, app=None):
        result = (app or self.app).tick()
        self.assertEqual(result['errors'], [], result)
        self.assertEqual(result['publication'], 'paused')
        return result

    def test_receive_compile_source_receipt_continuation_and_idempotent_restart(self):
        uri, cid = self.submit()
        result = self.checked_tick()
        self.assertEqual(result['status'], 'prepared-offline', result)
        self.assertEqual(workspace.bootstrap.desk_module.candidate_state(self.snapshot()['objects']['candidate'])['status'], 'ready')
        self.assertEqual(self.snapshot()['objects']['target'], self.initial_target)
        queue = self.app.compiler(self.app.config(), 2048)
        jobs = list((queue.state / 'jobs').glob('*.json'))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(queue.inspect(jobs[0].stem)['receipt']['kind'], 'committed')
        prepared = result['continuation']
        index = s.loads((Path(prepared['destination']) / 'index.json').read_bytes())
        self.assertEqual(len(index['receipts']), 1)
        self.assertEqual(index['receipts'][0]['receipt']['source']['uri'], uri)
        self.assertEqual(index['receipts'][0]['receipt']['source']['cid'], cid)
        self.assertEqual(index['receipts'][0]['receipt']['request']['principal'], AUTHOR)
        self.assertTrue(index['publicationArtifacts'])
        checked = s.continuation.verify(prepared['destination'], expected_genesis=self.seed['genesis'],
                                         expected_head=prepared['head'], base_head=self.seed['head'])
        self.assertEqual(checked['status'], 'verified-offline')
        world_bytes = (self.world / 'world.json').read_bytes()
        calls = list(self.pds.calls)
        restarted = s.Service(self.app.state, receiver=self.clerk.receive)
        self.assertEqual(self.checked_tick(restarted)['continuation'], prepared)
        self.assertEqual((self.world / 'world.json').read_bytes(), world_bytes)
        self.assertEqual(self.pds.calls, calls)
        # A later terminal refusal extends the anchored package without
        # rewriting the earlier source-bound receipt or compiler history.
        uri2 = 'at://' + AUTHOR + '/' + s.clerk.COLLECTION + '/later'
        wire = {'object': 'target', 'command': 'add', 'input': {'amount': 1}, 'expected': self.initial_target}
        self.pds.records['later'] = {'uri': uri2, 'cid': 'cid-later',
            'value': s.worker.receipts.encode('request', s.canonical(wire).decode())}
        restarted.enqueue(uri2, 'cid-later')
        extended = self.checked_tick(restarted)['continuation']
        old_manifest = s.loads((Path(prepared['destination']) / 'history/manifest.json').read_bytes())
        new_manifest = s.loads((Path(extended['destination']) / 'history/manifest.json').read_bytes())
        self.assertEqual(new_manifest['entries'][:len(old_manifest['entries'])], old_manifest['entries'])
        self.assertEqual(new_manifest['entries'][-1]['reply']['data'], 'unauthorized')
        s.continuation.verify(extended['destination'], expected_genesis=self.seed['genesis'],
                              expected_head=extended['head'], base_head=prepared['head'])

    def test_lost_receiving_reply_keeps_same_uri_and_reconciles_without_duplicate_admission(self):
        source = self.submit()
        def lost(uri, cid):
            self.clerk.receive(uri, cid)
            raise TimeoutError('lost receiving reply')
        self.app.receiver = lost
        first = self.checked_tick()
        self.assertEqual(first['status'], 'needs-attention')
        entry_path = self.app.receiving(self.app.config(), 2048).path(source[0])
        pending = s.loads(entry_path.read_bytes())
        self.assertEqual(pending['phase'], 'queued')
        self.assertEqual((pending['uri'], pending['cid']), source)
        count = len(self.snapshot()['receipts'])
        self.app.receiver = self.clerk.receive
        second = self.checked_tick()
        self.assertEqual(second['status'], 'prepared-offline')
        self.assertEqual(len(self.snapshot()['receipts']), count)
        self.assertEqual(s.loads(entry_path.read_bytes())['phase'], 'prepared')

    def test_lost_checkpoint_reply_resumes_same_snapshot_and_destination(self):
        self.submit()
        original = s.worker.command
        once = [True]
        def lose(arguments, *args, **kwargs):
            result = original(arguments, *args, **kwargs)
            if '_checkpoint' in arguments and once[0]:
                once[0] = False
                raise subprocess.TimeoutExpired('lost checkpoint reply', 1)
            return result
        with patch.object(s.worker, 'command', side_effect=lose):
            first = self.app.tick()
        self.assertEqual(first['status'], 'deadline')
        progress = s.loads((self.app.state / 'progress.json').read_bytes())
        plan = s.loads(Path(progress['checkpoint']).read_bytes())
        self.assertTrue((Path(plan['destination']) / 'index.json').exists())
        before = (self.world / 'world.json').read_bytes()
        second = self.checked_tick(s.Service(self.app.state, receiver=self.clerk.receive))
        self.assertEqual(second['continuation']['destination'], plan['destination'])
        self.assertEqual((self.world / 'world.json').read_bytes(), before)
        self.assertNotIn('checkpoint', s.loads((self.app.state / 'progress.json').read_bytes()))

    def test_epoch_drift_blocks_before_receiving_and_preserves_identity(self):
        source = self.submit()
        before = (self.world / 'world.json').read_bytes()
        with patch.object(s, 'epoch', return_value={'changed': True}):
            result = self.app.tick()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('epoch changed', result['errors'][0]['error'])
        self.assertEqual(self.pds.calls, [])
        self.assertEqual((self.world / 'world.json').read_bytes(), before)
        entry = s.loads(self.app.receiving(self.app.config(), 2048).path(source[0]).read_bytes())
        self.assertEqual((entry['uri'], entry['cid']), source)

    def test_wrong_public_genesis_and_wrong_database_refuse_configuration(self):
        app = s.Service(self.base / 'other-service')
        with self.assertRaisesRegex(ValueError, 'public genesis'):
            app.initialize(self.world, self.clerk.state, 'compiler', public_genesis='0' * 64)
        with self.assertRaisesRegex(ValueError, 'same|share exact'):
            app.initialize(self.base / 'different', self.clerk.state, 'compiler', public_genesis=self.seed['genesis'])
        self.assertFalse((app.state / 'service.json').exists())

    def test_bounded_batches_do_not_starve_later_candidates_after_refusal(self):
        law = copy.deepcopy(self.root['law'])
        law['invoke']['compiled'] = []
        law['invoke']['failed'] = []
        self.root = s.clerk.world.exchange(self.clerk.database, {'op': 'law', 'object': 'candidate',
            'principal': 'owner', 'intent': 'remove-compiler', 'expected': self.root, 'law': law},
            profile='compiled')['data']['root']
        later_law = copy.deepcopy(law)
        later_law['invoke']['compiled'] = ['compiler']
        later_law['invoke']['failed'] = ['compiler']
        added = manage.Management(self.clerk.state).add_object('later', AUTHOR, 'later-desk',
            'protocol-json@1', workspace.bootstrap.canonical(workspace.bootstrap.desk_module.module('service_candidate_package', 'protocols/source-desk/package.py').candidate()), later_law)
        later = added['reply']['data']['root']
        self.submit('first')
        self.submit('second', object_id='later', root=later)
        # Receive both source records once, then exercise a one-candidate budget.
        self.app.receiving(self.app.config(), 2048).run(limit=2)
        first = self.app.tick(limit=1)
        self.assertEqual(first['errors'], [], first)
        self.assertEqual(first['phases']['reconcile']['compiler'][0]['kind'], 'refused')
        second = s.Service(self.app.state, receiver=self.clerk.receive).tick(limit=1)
        self.assertEqual(second['errors'], [], second)
        self.assertEqual(workspace.bootstrap.desk_module.candidate_state(self.snapshot()['objects']['candidate'])['status'], 'pending')
        self.assertEqual(workspace.bootstrap.desk_module.candidate_state(self.snapshot()['objects']['later'])['status'], 'ready')
        self.assertEqual(self.snapshot()['objects']['target'], self.initial_target)

    def test_natural_language_discovery_is_not_an_authenticated_request(self):
        watch = self.base / 'watch'
        identity = 'a' * 64
        uri = 'at://' + AUTHOR + '/' + s.clerk.FEED + '/chat'
        s.save(watch / 'observations' / (identity + '.json'), {'uri': uri, 'cid': 'chat-cid',
            'record': {'$type': s.clerk.FEED, 'text': 'livedelvetalk.delve.town please compile this for me'}})
        s.save(watch / 'index.json', {'format': 'delvetalk-watch-index-v1', 'posts': {
            uri: {'observation': identity, 'cid': 'chat-cid', 'lastSeenAt': 'today'}}})
        app = s.Service(self.base / 'observing', receiver=self.clerk.receive)
        app.initialize(self.world, self.clerk.state, 'compiler', public_genesis=self.seed['genesis'], watch_state=watch)
        before = (self.world / 'world.json').read_bytes()
        result = self.checked_tick(app)
        self.assertEqual(result['phases']['discover']['skipped'], 1)
        self.assertEqual(result['phases']['receive']['processed'], [])
        self.assertEqual(result['phases']['enqueueCompilers']['examined'], 0)
        self.assertEqual(self.pds.calls, [])
        self.assertEqual((self.world / 'world.json').read_bytes(), before)

    def test_service_lock_deadline_and_bounds(self):
        with (self.app.state / 'service.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            started = time.monotonic()
            report = self.app.tick(deadline_seconds=0.05)
            self.assertEqual(report['status'], 'deadline')
            self.assertTrue(report['lockTimedOut'])
            self.assertLess(time.monotonic() - started, 1)
        for invalid in (0, 301, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.app.tick(deadline_seconds=invalid)

    def test_compiler_name_does_not_grant_completion_or_installation_authority(self):
        app = s.Service(self.base / 'unauthorized-service', receiver=self.clerk.receive)
        app.initialize(self.world, self.clerk.state, 'ungranted-compiler', public_genesis=self.seed['genesis'])
        source = self.submit()
        app.enqueue(*source)
        result = self.checked_tick(app)
        jobs = list((app.state / 'compiler/jobs').glob('*.json'))
        queue = app.compiler(app.config(), 2048)
        self.assertEqual(queue.inspect(jobs[0].stem)['receipt']['data'], 'unauthorized')
        self.assertEqual(workspace.bootstrap.desk_module.candidate_state(self.snapshot()['objects']['candidate'])['status'], 'pending')
        self.assertEqual(self.snapshot()['objects']['target'], self.initial_target)
        self.assertEqual(result['publication'], 'paused')
        self.assertEqual(result['status'], 'needs-attention')
        self.assertEqual(result['phases']['reconcile']['compiler'][0]['kind'], 'refused')


if __name__ == '__main__':
    unittest.main()
