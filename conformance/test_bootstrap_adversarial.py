#!/usr/bin/env python3
"""Composition failures across userspace release objects and atomic programming.

Tests execute the actual Lean receiving path. They never compile Lean or post.
"""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bootstrap_audit_world', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


def scoped(invoke, reprogram=(), law=('steward',)):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': invoke,
            'reprogram': list(reprogram), 'law': list(law)}


def room_protocol(marker):
    command = {'require': [], 'set': {'marker': ['literal', marker]},
               'result': ['record', {'observed': ['state', 'marker']}],
               'outbox': [['record', {'observed': ['state', 'marker']}]]}
    return {'profile': 'delvetalk-local-v1', 'initial': {'marker': 'unused-default'},
            'commands': {'run': command, 'new-admin': copy.deepcopy(command)}}


def release_protocol(program, migration):
    increment = ['bend', ['lam', ['binary', 'add', ['bound', 0], ['nat', '1']]],
                 [['state', 'releases']]]
    return {'profile': 'delvetalk-local-v1',
            'initial': {'protocol': program, 'migration': migration, 'releases': 0},
            'commands': {'release': {'require': [], 'set': {'releases': increment},
                'result': ['record', {'protocol': ['state', 'protocol'], 'state': ['state', 'migration']}],
                'outbox': [['literal', {'released': True}]]}}}


class BootstrapAdversarial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / 'world.json'
        self.old = room_protocol('old')
        self.new = room_protocol('new')
        self.room = self.create('room', self.old,
            scoped({'run': ['deployer', 'player']}, reprogram=['deployer']))
        self.source = self.create('release', release_protocol(self.new, {'marker': 'migrated'}),
            scoped({'release': ['deployer', 'player']}))

    def exchange(self, request):
        return world.exchange(self.database, request, profile='transactions')

    def create(self, name, protocol, law):
        receipt = self.exchange({'op': 'create', 'object': name, 'principal': 'creator',
            'intent': 'create-' + name, 'protocol': protocol, 'law': law})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        return receipt['data']['root']

    def inspect(self, name):
        return self.exchange({'op': 'inspect', 'object': name, 'principal': 'observer'})

    def adoption(self, intent='adopt', principal='deployer', followup='run'):
        calls = [{'object': 'release', 'command': 'release', 'input': {}},
                 {'op': 'reprogram', 'object': 'room', 'inputFrom': 0}]
        if followup:
            calls.append({'object': 'room', 'command': followup, 'input': {}})
        return {'op': 'transaction', 'principal': principal, 'intent': intent,
                'reads': {'release': self.source, 'room': self.room}, 'calls': calls}

    def assert_unchanged(self):
        self.assertEqual(self.inspect('release'), self.source)
        self.assertEqual(self.inspect('room'), self.room)

    def test_player_cannot_turn_release_data_into_programming_authority(self):
        request = self.adoption(principal='player')
        refused = self.exchange(request)
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertEqual(refused['data'], 'unauthorized')
        self.assert_unchanged()  # release state and outbox roll back too
        grant = self.exchange({'op': 'law', 'object': 'room', 'principal': 'steward',
            'intent': 'allow-player-programming', 'expected': self.room,
            'law': scoped({'run': ['deployer', 'player']}, reprogram=['deployer', 'player'])})
        self.assertEqual(grant['kind'], 'committed')
        self.assertEqual(self.exchange(request), refused)  # terminal refusal survives grant
        self.room = grant['data']['root']
        self.assertEqual(self.exchange(self.adoption('new-attempt', 'player'))['kind'], 'committed')

    def test_reprogram_then_invoke_sees_migration_and_preserves_current_law(self):
        receipt = self.exchange(self.adoption())
        self.assertEqual(receipt['kind'], 'committed', receipt)
        current = self.inspect('room')
        self.assertEqual(current['law'], self.room['law'])
        self.assertEqual(current['version'], self.room['version'] + 2)
        self.assertEqual(current['protocol'], self.new)
        self.assertEqual(current['state'], {'marker': 'new'})
        self.assertEqual(receipt['data']['results'][2], {'observed': 'migrated'})
        self.assertEqual([entry['step'] for entry in receipt['data']['outbox']], [0, 2])
        self.assertEqual(receipt['data']['outbox'][1]['payload'], {'observed': 'migrated'})

    def test_new_command_has_no_implicit_grant_and_rolls_back_reprogram(self):
        request = self.adoption(followup='new-admin')
        refusal = self.exchange(request)
        self.assertEqual(refusal['kind'], 'refused', refusal)
        self.assertEqual(refusal['data'], 'unauthorized')
        self.assert_unchanged()
        # A refusal has no provisional release result or externally usable outbox.
        self.assertIsInstance(refusal['data'], str)

    def test_candidate_only_change_invalidates_composite_adoption(self):
        request = self.adoption()
        released = self.exchange({'op': 'invoke', 'object': 'release',
            'principal': 'deployer', 'intent': 'standalone-release',
            'expected': self.source, 'command': 'release', 'input': {}})
        self.assertEqual(released['kind'], 'committed')
        self.assertEqual(self.inspect('room'), self.room)
        refusal = self.exchange(request)
        self.assertEqual(refusal['data'], 'stale read root')
        self.assertEqual(self.inspect('room'), self.room)
        self.assertEqual(self.inspect('release'), released['data']['root'])
        # Even identical compiled bytes do not erase candidate version identity.
        self.source = released['data']['root']
        self.assertEqual(self.exchange(self.adoption('fresh-candidate-root'))['kind'], 'committed')

    def test_empty_journal_artifact_does_not_establish_program_source(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        spec = importlib.util.spec_from_file_location('bootstrap_audit_empty_source', ROOT / 'scripts/history.py')
        history = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(history)
        request = {'op': 'reprogram', 'object': 'room', 'principal': 'deployer',
                   'intent': 'replace', 'expected': self.room, 'protocol': self.new,
                   'state': {'marker': 'migrated'}}
        bundle = Path(self.tmp.name) / 'fake-source'
        (bundle / 'blobs').mkdir(parents=True)
        for fake in [{'request': request, 'artifact': {}}, {'request': request, 'record': {}}]:
            sha = history.store_bytes(bundle, history.canonical(fake))
            with self.assertRaises(ValueError):
                history.verify_sources(request, [{'name': 'fake.json', 'sha256': sha}], bundle, False,
                                       {'kind': 'committed', 'data': {}})

    def test_history_transaction_programming_requires_source_or_explicit_inline(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        spec = importlib.util.spec_from_file_location('bootstrap_audit_history', ROOT / 'scripts/history.py')
        history = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(history)
        receipt = self.exchange(self.adoption())
        self.assertEqual(receipt['kind'], 'committed', receipt)
        with self.assertRaisesRegex(ValueError, 'source artifact'):
            history.export_history(self.database, Path(self.tmp.name) / 'missing-source',
                                   inline_reprogram=False)
        explicit = Path(self.tmp.name) / 'explicit-inline'
        trusted = history.export_history(self.database, explicit, inline_reprogram=True)
        verified = history.verify_history(explicit, expected_genesis=trusted['genesis'],
                                           expected_head=trusted['head'])
        self.assertEqual(verified['entries'], 3)

    def test_exact_retry_after_restart_program_change_and_lockout(self):
        request = self.adoption()
        receipt = self.exchange(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        changed = self.exchange({'op': 'reprogram', 'object': 'room',
            'principal': 'deployer', 'intent': 'later-program', 'expected': self.inspect('room'),
            'protocol': self.old, 'state': {'marker': 'later'}})
        self.assertEqual(changed['kind'], 'committed')
        locked = self.exchange({'op': 'law', 'object': 'room', 'principal': 'steward',
            'intent': 'lock-room', 'expected': changed['data']['root'],
            'law': scoped({}, reprogram=[], law=[])})
        self.assertEqual(locked['kind'], 'committed')
        process = subprocess.run([sys.executable, str(ROOT / 'scripts/world.py'),
            '--profile', 'transactions', str(self.database), '-'],
            input=json.dumps(request), capture_output=True, text=True, check=True, timeout=30)
        self.assertEqual(json.loads(process.stdout), receipt)
        self.assertEqual(self.inspect('room'), locked['data']['root'])
        self.assertEqual(self.inspect('release')['state']['releases'], 1)
        altered = copy.deepcopy(request)
        altered['calls'].pop()
        self.assertEqual(self.exchange(altered)['data'], 'intent reused for different request')


class SourceDeskAdversarial(unittest.TestCase):
    exchange = BootstrapAdversarial.exchange
    create = BootstrapAdversarial.create
    inspect = BootstrapAdversarial.inspect

    def setUp(self):
        BootstrapAdversarial.setUp(self)
        spec = importlib.util.spec_from_file_location('bootstrap_audit_desk', ROOT / 'scripts/desk.py')
        self.desk_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.desk_module)
        self.artifacts = Path(self.tmp.name) / 'artifacts'
        self.desk = self.desk_module.Desk(self.database, self.artifacts)
        law = scoped({'submit': ['author'], 'compiled': ['compiler'], 'failed': ['compiler'],
                      'adopt': ['deployer']}, reprogram=[])
        created = self.desk.create('candidate', 'creator', 'create-candidate', law)
        self.assertEqual(created['kind'], 'committed', created)
        self.source_bytes = (json.dumps(self.new, indent=2) + '\n').encode()
        scenarios = [{'name': 'new-behavior', 'law': ['tester'], 'steps': [
            {'principal': 'tester', 'command': 'run', 'input': {}, 'root': 'current',
             'kind': 'committed', 'state': {'marker': 'new'},
             'result': {'observed': 'unused-default'}}]}]
        submitted = self.desk.submit('candidate', 'author', 'submit-candidate', created['data']['root'],
            'protocol-json@1', self.source_bytes, json.dumps(scenarios).encode(),
            {'marker': 'migrated'}, 'room')
        self.assertEqual(submitted['kind'], 'committed', submitted)
        self.pending = submitted['data']['root']

    def checked(self):
        checked = self.desk.check('candidate', 'compiler', 'compile-candidate', self.pending)
        self.assertEqual(checked['kind'], 'committed', checked)
        ready = checked['data']['root']
        self.assertEqual(ready['state']['status'], 'ready', ready['state'].get('diagnostics'))
        return ready

    def test_compiled_artifact_binds_exact_source_root_program_and_migration(self):
        ready = self.checked()
        artifact = self.desk_module.load_artifact(self.artifacts, ready['state']['artifact'])
        self.assertEqual(artifact['candidateRootSha256'], self.desk_module.digest(self.pending))
        self.assertEqual(artifact['proposal']['source'].encode(), self.source_bytes)
        self.assertEqual(artifact['protocol'], ready['state']['protocol'])
        self.assertEqual(artifact['migration'], ready['state']['migration'])
        self.assertEqual(artifact['target'], 'room')
        self.assertEqual(ready['state']['compiler'], 'compiler')
        # The compiler identity is allowed to publish a checked artifact, not
        # to install code into the target or manage candidate authority.
        denied = self.desk.adopt('candidate', 'room', 'compiler', 'compiler-cannot-adopt', ready, self.room)
        self.assertEqual(denied['data'], 'unauthorized')
        self.assertEqual(self.inspect('candidate'), ready)
        self.assertEqual(self.inspect('room'), self.room)

    def test_author_cannot_forge_compiled_program_and_target_binding_is_checked(self):
        forged = self.exchange({'op': 'invoke', 'object': 'candidate', 'principal': 'author',
            'intent': 'forge-compiled', 'expected': self.pending, 'command': 'compiled',
            'input': {'artifact': 'forged', 'protocol': self.old, 'roomArtifact': None}})
        self.assertEqual(forged['data'], 'unauthorized')
        self.assertEqual(self.inspect('candidate'), self.pending)
        ready = self.checked()
        other = self.create('other-room', self.old, scoped({'run': ['deployer']}, reprogram=['deployer']))
        refused = self.desk.adopt('candidate', 'other-room', 'deployer', 'wrong-target', ready, other)
        self.assertEqual(refused['data'], 'precondition failed')
        self.assertEqual(self.inspect('candidate'), ready)
        self.assertEqual(self.inspect('other-room'), other)
        accepted = self.desk.adopt('candidate', 'room', 'deployer', 'correct-target', ready, self.room)
        self.assertEqual(accepted['kind'], 'committed', accepted)
        self.assertEqual(self.inspect('room')['protocol'], self.new)

    def test_compile_lost_reply_recovers_after_adoption_without_recompiling(self):
        real_exchange = self.desk.exchange
        captured = {}
        def lost_reply(request):
            receipt = real_exchange(request)
            if request.get('command') == 'compiled':
                captured['receipt'] = receipt
                raise OSError('lost reply after durable compile')
            return receipt
        with mock.patch.object(self.desk, 'exchange', side_effect=lost_reply):
            with self.assertRaisesRegex(OSError, 'lost reply'):
                self.desk.check('candidate', 'compiler', 'compile-candidate', self.pending)
        ready = self.inspect('candidate')
        self.assertEqual(ready['state']['status'], 'ready')
        accepted = self.desk.adopt('candidate', 'room', 'deployer', 'adopt-while-reply-lost', ready, self.room)
        self.assertEqual(accepted['kind'], 'committed', accepted)
        restored = self.desk_module.Desk(self.database, self.artifacts)
        with mock.patch.object(self.desk_module, 'bounded_compile', side_effect=AssertionError('must not compile again')):
            recovered = restored.check('candidate', 'compiler', 'compile-candidate', self.pending)
        self.assertEqual(recovered, captured['receipt'])
        self.assertEqual(self.inspect('candidate'), accepted['data']['roots']['candidate'])
        self.assertEqual(self.inspect('room'), accepted['data']['roots']['room'])


if __name__ == '__main__':
    unittest.main()
