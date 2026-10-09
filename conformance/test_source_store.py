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
sys.path.insert(0, str(ROOT / 'scripts'))
import source_store as store


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

    def test_content_reference_does_not_copy_private_custody(self):
        import stat
        ref = store.store_bytes(self.artifacts, b'private proposal bytes')
        other = self.path / 'other-account' / 'artifacts'
        with self.assertRaises(FileNotFoundError):
            store.read_bytes(other, ref)
        self.assertEqual(store.read_bytes(self.artifacts, ref), b'private proposal bytes')
        self.assertEqual(stat.S_IMODE(store.blob_path(self.artifacts, ref['sha256']).stat().st_mode), 0o600)

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
                                 store.canonical(ref).decode()], capture_output=True, text=True, timeout=2)
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


if __name__ == '__main__': unittest.main()
