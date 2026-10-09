#!/usr/bin/env python3
"""The same persistent journey can be inspected and acted upon through its CLI."""
import importlib.util
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inhabited_bootstrap', ROOT / 'scripts/bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class InhabitedBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        cls.report = bootstrap.run_bootstrap(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_two_participants_repair_then_use_admitted_improvement(self):
        report = self.report
        self.assertEqual(report['manifest']['participants'], ['iris', 'moss'])
        final = report['finalView']
        self.assertEqual(final['mode'], 'projection')
        self.assertIn('constellation', final['data']['prose'])
        self.assertEqual(final['root']['protocol']['spweenSource']['source'],
                         (ROOT / 'examples/inhabited-bootstrap/cafe-improved.scene').read_text())
        modules = {item['name']: item['source'] for item in final['root']['protocol']['sourcePackages']['resident']['modules']}
        self.assertEqual(modules['Scene'], (ROOT / 'examples/inhabited-bootstrap/CafeWindow.obend').read_text())
        repaired = bootstrap.loads((self.directory / 'observations/repaired-before-improvement.json').read_bytes())
        adopted = bootstrap.loads((self.directory / 'observations/after-adoption.json').read_bytes())
        self.assertEqual(adopted['root']['state'],
            bootstrap.desk_module.candidate_state(report['sourceProposalRoot'])['migration'])
        old = bootstrap.source_object.plain(bootstrap.source_object.state_data(repaired['root']))
        new = bootstrap.source_object.plain(bootstrap.source_object.state_data(adopted['root']))
        for field in ['passage', 'visited', 'started', 'ended']:
            self.assertEqual(new[field], old[field])
        self.assertNotEqual(final['root']['state'], adopted['root']['state'])
        world = bootstrap.loads((self.directory / 'world.json').read_bytes())
        records = {entry['request']['intent']: entry for entry in world['receipts']}
        self.assertEqual(records['align-wing']['request']['principal'], 'iris')
        self.assertEqual(records['wind-fresh']['request']['principal'], 'moss')
        self.assertEqual(records['propose-window']['request']['principal'], 'iris')
        self.assertEqual(records['compile-window']['request']['principal'], 'compiler')
        self.assertEqual(records['adopt-window']['request']['principal'], 'moss')
        self.assertEqual(records['chalk-star']['request']['principal'], 'moss')
        self.assertEqual(records['adopt-window']['request']['calls'][1]['inputFrom'], 0)
        self.assertEqual(records['adopt-window']['receipt']['kind'], 'committed')

    def test_old_roots_refuse_and_read_again_recovers(self):
        receipts = {entry['label']: entry['receipt'] for entry in self.report['events']}
        refused = [r for r in receipts.values() if r['kind'] == 'refused']
        self.assertEqual(len(refused), 3)
        self.assertTrue(all(r['data'] == 'stale read root' for r in refused))
        self.assertEqual(receipts['Moss reads again and winds the spring']['kind'], 'committed')
        self.assertEqual(receipts['Moss reads the new source-bound view and releases the moth']['kind'], 'committed')
        original = bootstrap.loads((self.directory / 'observations/shared-before-repair.json').read_bytes())
        current = bootstrap.inspect_view(self.directory)
        self.assertNotEqual(original['root']['protocol'], current['root']['protocol'])
        self.assertNotEqual(original['programSha256'], current['programSha256'])

    def test_source_artifacts_and_extension_slot_remain_available(self):
        report = self.report
        for name in ('initialCafeArtifact', 'currentCafeArtifact'):
            artifact = bootstrap.room.load_artifact(self.directory / 'artifacts/rooms', report['manifest'][name])
            self.assertIn('source', artifact['content'])
        self.assertIn('sourcePackages', report['tableRoot']['protocol'])
        table = bootstrap.room.inspect_object(report['tableRoot'], bootstrap.TABLE)
        self.assertIn('shared activity', table['data']['prose'])
        self.assertEqual(report['tableRoot']['protocol']['commands'], {})
        desk = bootstrap.desk_module.candidate_state(report['sourceProposalRoot'])
        self.assertEqual(desk['submitter'], 'iris')
        self.assertEqual(desk['compiler'], 'compiler')
        self.assertEqual(desk['lastRelease'], 'moss')
        artifact = bootstrap.desk_module.load_artifact(self.directory / 'artifacts', desk['artifact'])
        self.assertTrue(artifact['report']['passed'])
        self.assertEqual(artifact['sourceMaterial']['source'], bootstrap.cafe_proposal_source().decode())
        self.assertIn('Exact view program', (self.directory / 'cafe.html').read_text())

    def test_cli_reads_and_exact_retry_uses_retained_view(self):
        command = [sys.executable, str(ROOT / 'scripts/bootstrap.py')]
        current = subprocess.run(command + ['view', str(self.directory)], text=True, capture_output=True)
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertEqual(bootstrap.loads(current.stdout)['root'], self.report['finalView']['root'])
        repeated = subprocess.run(command + ['act', str(self.directory), '--view',
            str(self.directory / 'observations/shared-before-repair.json'), '--principal', 'moss',
            '--intent', 'old-program-view', '--choice', '1'], text=True, capture_output=True)
        self.assertEqual(repeated.returncode, 1, repeated.stderr)
        self.assertEqual(bootstrap.loads(repeated.stdout)['data'], 'stale read root')
        table = subprocess.run(command + ['view', str(self.directory), '--object', bootstrap.TABLE], text=True, capture_output=True)
        self.assertEqual(table.returncode, 0, table.stderr)
        self.assertEqual(bootstrap.loads(table.stdout)['object'], bootstrap.TABLE)

    def test_participant_replaces_pure_view_program_and_other_participant_uses_it(self):
        before = bootstrap.loads((self.directory / 'observations/sign-before-improvement.json').read_bytes())
        after = bootstrap.loads((self.directory / 'observations/sign-after-improvement.json').read_bytes())
        self.assertNotEqual(before['source'], after['source'])
        self.assertNotEqual(before['data']['prose'], after['data']['prose'])
        self.assertEqual(self.report['signFinalView']['data']['prose'], 'The lamp is lit.')
        self.assertEqual(bootstrap.desk_module.candidate_state(self.report['signProposalRoot'])['submitter'], 'moss')
        self.assertEqual(bootstrap.desk_module.candidate_state(self.report['signProposalRoot'])['lastRelease'], 'iris')
        final = bootstrap.inspect_view(self.directory, bootstrap.SIGN, 'details')
        self.assertEqual(final['data']['prose'], 'The lamp is lit.')
        self.assertEqual(final['mode'], 'projection')

    def test_existing_directory_is_never_reinitialized(self):
        before = (self.directory / 'world.json').read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'empty directory'):
            bootstrap.run_bootstrap(self.directory)
        self.assertEqual((self.directory / 'world.json').read_bytes(), before)


class InhabitedReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        original = cls.directory / 'original'
        bootstrap.run_bootstrap(original)
        cls.bundle = cls.directory / 'bundle'
        real_hash = bootstrap.history.file_hash
        def preserved_only(path):
            if Path(path).resolve() == (ROOT / 'syntaxes/adapters.py').resolve():
                raise AssertionError('export consulted mutable adapter source instead of preserved bytes')
            return real_hash(path)
        with mock.patch.object(bootstrap.history, 'file_hash', side_effect=preserved_only):
            cls.anchors = bootstrap.export_bootstrap(original, cls.bundle)
        # Remove only this test's own fixture. Reconstruction cannot consult it.
        shutil.rmtree(original)
        cls.restored = cls.directory / 'restored'
        with mock.patch.object(bootstrap.room, 'compile_artifact', side_effect=AssertionError('recompiled source')):
            cls.result = bootstrap.restore_bootstrap(cls.bundle, cls.restored,
                expected_genesis=cls.anchors['genesis'], expected_head=cls.anchors['head'])

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_complete_artifacts_restore_without_original_custody(self):
        self.assertFalse((self.directory / 'original').exists())
        self.assertEqual(self.result['worldSha256'], self.anchors['worldSha256'])
        self.assertEqual(len(self.result['rooms']), 2)
        self.assertEqual(len(self.result['builds']), 2)
        self.assertGreaterEqual(len(self.result['lowerings']), 2)
        view = bootstrap.inspect_view(self.restored)
        self.assertEqual(view['mode'], 'projection')
        self.assertIn('Iris has opened the window', view['root']['protocol']['spweenSource']['source'])
        self.assertIn('sourcePackages', view['root']['protocol'])
        self.assertEqual(bootstrap.inspect_view(self.restored, bootstrap.SIGN, 'details')['data']['prose'], 'The lamp is lit.')
        manifest = bootstrap.loads((self.bundle / 'manifest.json').read_bytes())
        self.assertIs(manifest['inlineReprogram'], False)
        adoption_entries = [entry for entry in manifest['entries'] if entry['request'].get('op') == 'transaction']
        self.assertEqual(len(adoption_entries), 2)
        self.assertTrue(all(entry['request']['calls'][1]['inputFrom'] == 0 for entry in adoption_entries))
        self.assertTrue(all(entry['artifacts'] for entry in adoption_entries))

    def test_separate_cli_consumer_acts_on_reconstructed_view_and_extends_known_prefix(self):
        command = [sys.executable, str(ROOT / 'scripts/bootstrap.py')]
        observed = subprocess.run(command + ['view', str(self.restored), '--object', bootstrap.SIGN],
                                  text=True, capture_output=True)
        self.assertEqual(observed.returncode, 0, observed.stderr)
        view = self.directory / 'consumer-view.json'
        view.write_text(observed.stdout)
        acted = subprocess.run(command + ['act', str(self.restored), '--view', str(view),
            '--principal', 'moss', '--intent', 'reconstructed-visitor', '--action', 'light'],
            text=True, capture_output=True)
        self.assertEqual(acted.returncode, 0, acted.stderr)
        self.assertEqual(bootstrap.loads(acted.stdout)['kind'], 'committed')
        # A new spelling of the old program must not rewrite old source links.
        sign_root = bootstrap.inspect_view(self.restored, bootstrap.SIGN)['root']
        bootstrap.preserve_lowering(self.restored, bootstrap.canonical(sign_root['protocol']) + b'\n')
        extended = self.directory / 'extended-bundle'
        anchors = bootstrap.export_bootstrap(self.restored, extended)
        self.assertNotEqual(anchors['head'], self.anchors['head'])
        checked = bootstrap.verify_bootstrap(extended, expected_genesis=anchors['genesis'],
            expected_head=anchors['head'], base_head=self.anchors['head'])
        self.assertEqual(checked['entries'], self.anchors['entries'] + 1)

    def test_wrong_anchors_and_existing_destination_refuse_without_publication(self):
        destination = self.directory / 'wrong-head'
        with self.assertRaisesRegex(ValueError, 'trusted head mismatch'):
            bootstrap.restore_bootstrap(self.bundle, destination,
                expected_genesis=self.anchors['genesis'], expected_head='0' * 64)
        self.assertFalse(destination.exists())
        existing = self.directory / 'existing-empty'
        existing.mkdir()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            bootstrap.restore_bootstrap(self.bundle, existing,
                expected_genesis=self.anchors['genesis'], expected_head=self.anchors['head'])
        self.assertEqual(list(existing.iterdir()), [])
        staging = self.directory / 'atomic-staging'
        staging.mkdir()
        (staging / 'kept').write_text('complete state')
        with self.assertRaises(OSError):
            bootstrap._publish_directory(staging, existing)
        self.assertTrue((staging / 'kept').exists())
        self.assertEqual(list(existing.iterdir()), [])

    def test_missing_source_blob_is_never_replaced_by_inline_program(self):
        copied = self.directory / 'missing-room-bundle'
        shutil.copytree(self.bundle, copied)
        room_identity = bootstrap.loads((self.restored / 'manifest.json').read_bytes())['initialCafeArtifact']
        # The initial room is a standalone source attachment, not only a nested build field.
        (copied / 'blobs' / room_identity).unlink()
        destination = self.directory / 'missing-room-output'
        with self.assertRaises((ValueError, OSError)):
            bootstrap.restore_bootstrap(copied, destination,
                expected_genesis=self.anchors['genesis'], expected_head=self.anchors['head'])
        self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
