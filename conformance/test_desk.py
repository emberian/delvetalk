#!/usr/bin/env python3
"""Source proposal lifecycle and adoption stay inside Lean-owned objects."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('source_desk', ROOT / 'scripts/desk.py')
desk_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desk_module)


def scoped(invoke=None, reprogram=None, law=None):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': invoke or {},
            'reprogram': reprogram or [], 'law': law or []}


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.desk = desk_module.Desk(self.path / 'world.json', self.path / 'artifacts')
        self.source = (ROOT / 'protocols/counter/protocol.json').read_bytes()
        self.scenarios = (ROOT / 'protocols/counter/scenarios.json').read_bytes()
        self.law = scoped({'submit': ['author'], 'compiled': ['compiler'], 'failed': ['compiler'],
                           'adopt': ['reviewer']}, law=['owner'])
        self.candidate = self.desk.create('candidate', 'owner', 'create-candidate', self.law)['data']['root']
        target_law = scoped({'add': ['player']}, reprogram=['reviewer'], law=['owner'])
        self.target = self.desk.exchange({'op': 'create', 'object': 'target', 'principal': 'owner',
                        'intent': 'create-target', 'protocol': desk_module.loads(self.source), 'law': target_law})['data']['root']

    def submit(self, **changes):
        values = dict(object_id='candidate', principal='author', intent='submit', expected=self.candidate,
                      syntax='protocol-json@1', source=self.source, scenarios=self.scenarios,
                      migration={'count': 41}, target='target')
        values.update(changes)
        return self.desk.submit(**values)

    def ready(self):
        pending = self.submit()['data']['root']
        return self.desk.check('candidate', 'compiler', 'compile', pending)['data']['root']

    def test_complete_proposal_compile_adopt_and_retry(self):
        pending = self.submit()['data']['root']
        self.assertEqual(pending['state']['proposal']['source'].encode(), self.source)
        self.assertEqual(pending['state']['status'], 'pending')
        compiled = self.desk.check('candidate', 'compiler', 'compile', pending)
        self.assertEqual(compiled['kind'], 'committed')
        ready = compiled['data']['root']
        self.assertEqual(ready['state']['status'], 'ready')
        artifact = desk_module.load_artifact(self.desk.artifact_store, ready['state']['artifact'])
        self.assertTrue(artifact['report']['passed'])
        self.assertEqual(artifact['candidateRootSha256'], desk_module.digest(pending))
        # Resume after a lost worker reply must not compile again or change identity.
        with mock.patch.object(desk_module, 'bounded_compile', side_effect=AssertionError('recompiled')):
            self.assertEqual(self.desk.check('candidate', 'compiler', 'compile', pending), compiled)
        adopted = self.desk.adopt('candidate', 'target', 'reviewer', 'adopt', ready, self.target)
        self.assertEqual(adopted['kind'], 'committed')
        target = self.desk.inspect('target')
        self.assertEqual(target['state'], {'count': 41})
        self.assertEqual(target['law'], self.target['law'])
        self.assertEqual(target['protocol'], ready['state']['protocol'])
        self.assertEqual(self.desk.adopt('candidate', 'target', 'reviewer', 'adopt', ready, self.target), adopted)
        self.assertEqual(self.desk.inspect('candidate')['state']['status'], 'ready')

    def test_failed_compile_retained_and_cannot_adopt(self):
        pending = self.submit(source=b'{not JSON')['data']['root']
        receipt = self.desk.check('candidate', 'compiler', 'broken', pending)
        failed = receipt['data']['root']
        self.assertEqual(failed['state']['status'], 'failed')
        self.assertTrue(failed['state']['diagnostics'])
        artifact = desk_module.load_artifact(self.desk.artifact_store, failed['state']['artifact'])
        self.assertFalse(artifact['passed'])
        self.assertEqual(self.desk.check('candidate', 'compiler', 'broken', pending), receipt)
        self.assertEqual(self.desk.adopt('candidate', 'target', 'reviewer', 'no-adopt', failed, self.target)['kind'], 'refused')
        self.assertEqual(self.desk.inspect('target'), self.target)

    def test_roles_and_late_authority_failure_rollback(self):
        ready = self.ready()
        denied = self.desk.adopt('candidate', 'target', 'compiler', 'compiler-cannot-adopt', ready, self.target)
        self.assertEqual(denied['kind'], 'refused')
        # Reviewer may release a candidate but must still have target reprogram rights.
        revoked = self.desk.exchange({'op': 'law', 'object': 'target', 'principal': 'owner',
                    'intent': 'revoke', 'expected': self.target, 'law': scoped({'add': ['player']}, law=['owner'])})['data']['root']
        denied = self.desk.adopt('candidate', 'target', 'reviewer', 'reviewer-revoked', ready, revoked)
        self.assertEqual(denied['kind'], 'refused')
        self.assertEqual(self.desk.inspect('candidate'), ready)
        self.assertEqual(self.desk.inspect('target'), revoked)

    def test_exact_roots_and_changed_compiler_identity(self):
        pending = self.submit()['data']['root']
        compiled = self.desk.check('candidate', 'compiler', 'compile', pending)
        with self.assertRaisesRegex(ValueError, 'intent already bound'):
            self.desk.check('candidate', 'compiler', 'compile', compiled['data']['root'])
        altered = copy.deepcopy(pending)
        altered['state']['proposal']['source'] = altered['state']['proposal']['source'] + '\n'
        self.assertEqual(self.desk.check('candidate', 'compiler', 'stale-compile', altered)['kind'], 'refused')
        ready = self.desk.inspect('candidate')
        changed = self.desk.exchange({'op': 'invoke', 'object': 'target', 'principal': 'player',
                    'intent': 'play', 'expected': self.target, 'command': 'add', 'input': {'amount': 1}})['data']['root']
        self.assertEqual(self.desk.adopt('candidate', 'target', 'reviewer', 'stale-adopt', ready, self.target)['kind'], 'refused')
        self.assertEqual(self.desk.inspect('candidate'), ready)
        self.assertEqual(self.desk.inspect('target'), changed)

    def test_timeout_is_retained_as_failed_compilation(self):
        pending = self.submit()['data']['root']
        failure = {'format': 'delvetalk-desk-build-v1', 'candidateRootSha256': desk_module.digest(pending),
                   'passed': False, 'diagnostics': [{'kind': 'worker-timeout', 'seconds': 45}]}
        with mock.patch.object(desk_module, 'bounded_compile', return_value=failure):
            result = self.desk.check('candidate', 'compiler', 'timed-out', pending)
        self.assertEqual(result['data']['root']['state']['status'], 'failed')
        self.assertEqual(result['data']['root']['state']['diagnostics'], failure['diagnostics'])

    def test_actual_worker_wall_timeout(self):
        pending = self.submit()['data']['root']
        result = desk_module.bounded_compile(pending, timeout=0.001)
        self.assertFalse(result['passed'])
        self.assertEqual(result['diagnostics'][0]['kind'], 'worker-timeout')

    def test_spween_room_artifact_round_trip(self):
        source = b'---\nid: desk_room\n---\n=== intro\nHello from a source desk.\n* [Leave]\n  -> END\n'
        scenarios = desk_module.canonical([{'name': 'start', 'law': ['a'], 'steps': [
            {'principal': 'a', 'command': 'start', 'input': {}, 'root': 'initial', 'kind': 'committed'}]}])
        translated = desk_module.translate.translate('spween-scene-i64@1', source)
        migration = translated['lowered']['protocol']['initial']
        pending = self.submit(source=source, scenarios=scenarios, syntax='spween-scene-i64@1', migration=migration)['data']['root']
        ready = self.desk.check('candidate', 'compiler', 'scene-compile', pending)['data']['root']
        self.assertEqual(ready['state']['status'], 'ready', ready['state']['diagnostics'])
        self.assertIsNotNone(ready['state']['roomArtifact'])
        receipt = self.desk.adopt('candidate', 'target', 'reviewer', 'scene-adopt', ready, self.target)
        self.assertEqual(receipt['kind'], 'committed')
        room = desk_module.module('test_desk_room', 'scene/room.py')
        artifact = room.load_artifact(self.desk.artifact_store / 'rooms', ready['state']['roomArtifact'])
        view = room.room_view(self.desk.inspect('target'), artifact, 'target')
        self.assertIn('source', str(view))
        self.assertEqual(artifact['content']['source'].encode(), source)


if __name__ == '__main__':
    unittest.main()
