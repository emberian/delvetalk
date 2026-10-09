#!/usr/bin/env python3
"""Exact source references retain bytes while Lean owns proposal lifecycle/adoption."""
import copy
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('source_queue_tests', ROOT / 'scripts/compiler_queue.py')
queue_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue_module)
desk, store = queue_module.desk, queue_module.desk.source_store


class SourceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.artifacts = self.path / 'artifacts'

    def test_exact_utf8_and_idempotent_content_addressing(self):
        raw = '\ufeffhello\r\nκαλημέρα\n'.encode('utf-8')
        ref = store.store_bytes(self.artifacts, raw)
        self.assertEqual(ref['bytes'], len(raw))
        self.assertEqual(store.store_bytes(self.artifacts, raw), ref)
        self.assertEqual(store.ref_for(self.artifacts, ref['sha256']), ref)
        self.assertEqual(store.read_bytes(self.artifacts, ref), raw)
        self.assertEqual(len(list((self.artifacts / 'sources/blobs').iterdir())), 1)
        self.assertEqual(store.collect_references({'root': [ref, ref]}), [ref])

    def test_missing_tampered_malformed_and_escaping_references_refuse(self):
        ref = store.store_bytes(self.artifacts, b'source')
        for field, value in (('sha256', '../outside'), ('sha256', 'https://example.org/source'),
                             ('bytes', True), ('bytes', 7), ('encoding', 'latin-1')):
            altered = {**ref, field: value}
            with self.subTest(field=field, value=value), self.assertRaises((ValueError, OSError)):
                store.read_bytes(self.artifacts, altered)
        with self.assertRaises(ValueError):
            store.read_bytes(self.artifacts, {**ref, 'path': '/tmp/anything'})
        path = store.blob_path(self.artifacts, ref['sha256'])
        path.write_bytes(b'tamper')
        with self.assertRaises(ValueError):
            store.read_bytes(self.artifacts, ref)
        with self.assertRaises(ValueError):
            store.store_bytes(self.artifacts, b'source')
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            store.read_bytes(self.artifacts, ref)
        outside = self.path / 'outside'
        outside.write_bytes(b'source')
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            store.read_bytes(self.artifacts, ref)

    def test_fifo_custody_refuses_without_blocking(self):
        ref = store.store_bytes(self.artifacts, b'input')
        path = store.blob_path(self.artifacts, ref['sha256'])
        path.unlink()
        os.mkfifo(path)
        # Exercise in a child so a regression fails promptly instead of hanging
        # the suite inside os.open, before any byte/hash checks can run.
        code = """import json,sys
sys.path.insert(0,sys.argv[1])
import source_store
try:
    source_store.read_bytes(sys.argv[2],json.loads(sys.argv[3]))
except ValueError as error:
    assert 'regular file' in str(error), str(error)
else:
    raise AssertionError('FIFO accepted as source custody')
"""
        result = subprocess.run([sys.executable, '-c', code, str(ROOT / 'scripts'), str(self.artifacts),
                                 desk.canonical(ref).decode()], capture_output=True, text=True, timeout=2)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_and_scenario_byte_bounds_and_utf8_are_explicit(self):
        for kind in ('source', 'scenarios'):
            raw = b' ' * store.LIMITS[kind]
            ref = store.store_bytes(self.artifacts, raw, kind=kind)
            self.assertEqual(store.read_bytes(self.artifacts, ref, kind=kind), raw)
            with self.assertRaises(ValueError):
                store.store_bytes(self.artifacts, raw + b' ', kind=kind)
        with self.assertRaises(UnicodeDecodeError):
            store.store_bytes(self.artifacts, b'\xff')


@unittest.skipUnless((ROOT / '.lake/build/bin/delvetalk-transactions').is_file(), 'built transactions host required')
class SourceDeskReferenceTests(unittest.TestCase):
    def setUp(self):
        SourceStoreTests.setUp(self)
        self.client = desk.Desk(self.path / 'world.json', self.artifacts)
        self.queue = queue_module.CompilerQueue(self.path / 'queue', self.client.database, self.artifacts)
        self.law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {
            'submit': ['author'], 'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': ['reviewer']},
            'reprogram': [], 'law': ['owner']}
        self.initial = self.client.create('candidate', 'owner', 'create', self.law)['data']['root']
        protocol = desk.loads((ROOT / 'protocols/counter/protocol.json').read_bytes())
        self.target = self.client.exchange({'op': 'create', 'object': 'target', 'principal': 'owner',
                        'intent': 'create-target', 'protocol': protocol, 'law': ['reviewer']})['data']['root']
        self.source = b' \r\n' * 24000 + (ROOT / 'protocols/counter/protocol.json').read_bytes()
        self.scenarios = (ROOT / 'protocols/counter/scenarios.json').read_bytes()
        self.proposal = store.prepare_proposal(self.artifacts, 'protocol-json@1', self.source, self.scenarios)

    def submit(self, proposal=None):
        return self.client.submit_refs('candidate', 'author', 'submit', self.initial,
                                      self.proposal if proposal is None else proposal, {'count': 7}, 'target')

    def test_large_source_small_root_queue_compile_and_explicit_adoption(self):
        pending = self.submit()['data']['root']
        self.assertGreater(len(self.source), 64 * 1024)
        self.assertLess(len(desk.canonical(pending)), 16 * 1024)
        self.assertNotIn('source', pending['state']['proposal'])
        identity = self.queue.enqueue('candidate', 'compiler', 'compile', pending)['job']
        job = desk.loads(self.queue.job_path(identity).read_bytes())
        self.assertEqual(job['sourceBindings']['sourceRef'], self.proposal['sourceRef'])
        self.assertEqual(job['sourceBindings']['adapterPin'], self.proposal['adapterPin'])
        self.assertLess(self.queue.job_path(identity).stat().st_size, 32 * 1024)
        self.assertEqual(self.queue.run()['errors'], [])
        status = self.queue.inspect(identity)
        ready = status['receipt']['data']['root']
        build = desk.load_artifact(self.artifacts, status['artifact'])
        self.assertEqual(build['sourceBindings'], job['sourceBindings'])
        self.assertEqual(build['sourceMaterial']['source'].encode('utf-8'), self.source)
        self.assertTrue(build['passed'])
        self.assertEqual(self.client.inspect('target'), self.target)
        installed = self.client.adopt('candidate', 'target', 'reviewer', 'adopt', ready, self.target)
        self.assertEqual(installed['kind'], 'committed')
        self.assertEqual(self.client.inspect('target')['state'], {'count': 7})

    def test_retained_submit_and_compile_recover_before_missing_sources_and_builds(self):
        submitted = self.submit()
        pending = submitted['data']['root']
        identity = self.queue.enqueue('candidate', 'compiler', 'compile', pending)['job']
        self.assertEqual(self.queue.run()['errors'], [])
        status = self.queue.inspect(identity)
        store.blob_path(self.artifacts, self.proposal['sourceRef']['sha256']).unlink()
        (self.artifacts / 'builds' / (status['artifact'] + '.json')).unlink()
        self.assertEqual(self.submit(), submitted)
        self.assertEqual(self.client.check('candidate', 'compiler', 'compile', pending), status['receipt'])
        # Simulate losing queue status after the real immutable admission.
        self.queue.status_path(identity).write_bytes(desk.canonical({'phase': 'running', 'attempts': 1, 'errors': []}))
        self.assertEqual(self.queue.run()['errors'], [])
        self.assertEqual(self.queue.inspect(identity)['receipt'], status['receipt'])

    def test_missing_or_changed_source_blocks_pending_job_without_admission(self):
        pending = self.submit()['data']['root']
        identity = self.queue.enqueue('candidate', 'compiler', 'compile', pending)['job']
        path = store.blob_path(self.artifacts, self.proposal['sourceRef']['sha256'])
        path.write_bytes(b'changed')
        report = self.queue.run()
        self.assertTrue(report['errors'])
        self.assertEqual(self.queue.inspect(identity)['phase'], 'queued')
        self.assertEqual(self.client.inspect('candidate'), pending)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.client.check('candidate', 'compiler', 'missing-source', pending)
        self.assertEqual(self.client.inspect('candidate'), pending)

    def test_adapter_mismatch_refuses_and_pending_dependencies_are_preserved(self):
        changed = copy.deepcopy(self.proposal)
        changed['adapterPin']['files']['scripts/translate.py'] = '0' * 64
        identity = {key: value for key, value in changed['adapterPin'].items() if key != 'pin'}
        changed['adapterPin']['pin'] = desk.digest(identity)
        with self.assertRaisesRegex(ValueError, 'adapter pins changed'):
            self.submit(changed)
        self.assertEqual(self.client.inspect('candidate'), self.initial)
        for name, sha in store.declared_dependencies(self.proposal).items():
            self.assertEqual((self.artifacts / 'pins/blobs' / sha).read_bytes(), (ROOT / name).read_bytes())

    def test_reference_inputs_do_not_bypass_compiled_protocol_wire_limit(self):
        oversized = desk.loads((ROOT / 'protocols/counter/protocol.json').read_bytes())
        oversized['description'] = 'x' * (70 * 1024)
        self.proposal = store.prepare_proposal(self.artifacts, 'protocol-json@1', desk.canonical(oversized), self.scenarios)
        pending = self.submit()['data']['root']
        failed = self.client.check('candidate', 'compiler', 'too-large-output', pending)['data']['root']
        self.assertEqual(failed['state']['status'], 'failed')
        self.assertEqual(self.client.inspect('target'), self.target)
        self.assertTrue(failed['state']['diagnostics'])

    def test_failed_reference_program_retains_original_bytes_and_diagnostics(self):
        self.proposal = store.prepare_proposal(self.artifacts, 'protocol-json@1', b'{broken\r\n', self.scenarios)
        pending = self.submit()['data']['root']
        failed = self.client.check('candidate', 'compiler', 'bad-source', pending)['data']['root']
        build = desk.load_artifact(self.artifacts, failed['state']['artifact'])
        self.assertEqual(failed['state']['status'], 'failed')
        self.assertEqual(build['sourceMaterial']['source'].encode(), b'{broken\r\n')
        self.assertEqual(build['sourceBindings']['sourceRef'], self.proposal['sourceRef'])
        self.assertTrue(build['diagnostics'])


if __name__ == '__main__':
    unittest.main()
