"""Offline continuation adversaries, using the installed Lean transactions host."""
import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import continuation as c
import translate


class Continuation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.database = cls.directory / 'world.json'
        cls.bundle = cls.directory / 'history'
        protocol = c.loads((ROOT / 'protocols/counter/protocol.json').read_bytes())
        roots = {}
        for name in ('a', 'b'):
            request = {'op': 'create', 'object': name, 'principal': 'A', 'intent': 'create-' + name,
                       'protocol': protocol, 'law': ['A']}
            roots[name] = c.history.world.exchange(cls.database, request, profile='transactions')['data']['root']
        cls.request = {'op': 'transaction', 'principal': 'A', 'intent': 'both', 'reads': roots,
                       'calls': [{'object': 'a', 'command': 'add', 'input': {'amount': 3}},
                                 {'object': 'b', 'command': 'add', 'input': {'amount': 4}}]}
        reply = c.history.world.exchange(cls.database, cls.request, profile='transactions')
        cls.receipt = {'format': 'delvetalk-clerk-receipt-v1', 'request': cls.request, 'reply': reply,
                       'source': {'author': 'A', 'uri': 'at://did:plc:test/org.delvetalk.request/both', 'cid': 'test'},
                       'profile': {'name': 'test-local-source-claim'}}
        cls.receipt['id'] = c.history.digest(cls.receipt)
        cls.journals = cls.directory / 'journals'
        cls.journals.mkdir()
        (cls.journals / 'both.json').write_bytes(c.canonical({'request': cls.request, 'receipt': cls.receipt}))
        c.history.world.exchange(cls.database, {**cls.request, 'intent': 'stale'}, profile='transactions')
        request = {'op': 'reprogram', 'object': 'a', 'principal': 'A', 'intent': 'program',
                   'expected': reply['data']['roots']['a'], 'protocol': protocol, 'state': {'count': 8}}
        c.history.world.exchange(cls.database, request, profile='transactions')
        (cls.journals / 'source.json').write_bytes(c.canonical({'request': request,
            'artifact': translate.translate('protocol-json@1', c.canonical(protocol))}))
        cls.evidence = c.history.export_history(cls.database, cls.bundle, journals=cls.journals)
        cls.anchors = {'expected_genesis': cls.evidence['genesis'], 'expected_head': cls.evidence['head']}

    def setUp(self):
        self.temp_case = tempfile.TemporaryDirectory(dir=self.directory)
        self.addCleanup(self.temp_case.cleanup)
        self.case = Path(self.temp_case.name)
        self.destination = self.case / 'continuation'

    def prepare(self):
        return c.prepare(self.bundle, self.destination, **self.anchors)

    def index(self):
        return c.loads((self.destination / 'index.json').read_bytes())

    def test_replay_roots_source_custody_and_worker_heads(self):
        result = self.prepare()
        checked = c.verify(self.destination, **self.anchors)
        self.assertEqual(result['admissions'], 5)
        self.assertEqual(checked['objects'], 2)
        self.assertEqual(checked['proofScope'], 'exact-artifact-replay')
        index = self.index()
        self.assertEqual(index['roots'][0]['root']['state']['count'], 8)
        self.assertEqual(index['publicationArtifacts'], sorted(c.worker.publication_artifacts(self.receipt),
                         key=lambda item: (item['kind'], item['id'])))
        self.assertEqual((self.destination / 'history/manifest.json').read_bytes(),
                         (self.bundle / 'manifest.json').read_bytes())
        original = c.loads((self.bundle / 'manifest.json').read_bytes())
        for sha in c.required_blobs(original, self.bundle):
            self.assertEqual(c.history.read_blob(self.destination / 'history', sha).read_bytes(),
                             c.history.read_blob(self.bundle, sha).read_bytes())

    def test_omission_or_changed_roots_heads_and_receipts_refuse(self):
        self.prepare()
        original = self.index()
        for mutate in (lambda x: x['roots'].pop(),
                       lambda x: x['roots'][0]['root']['state'].update(count=999),
                       lambda x: x['publicationArtifacts'].pop(),
                       lambda x: x['receipts'].clear()):
            changed = copy.deepcopy(original)
            mutate(changed)
            (self.destination / 'index.json').write_bytes(c.canonical(changed))
            (self.destination / 'index.html').write_text(c.page(changed))
            with self.assertRaisesRegex(ValueError, 'omits or changes'):
                c.verify(self.destination, **self.anchors)

    def test_idempotent_after_lost_reply_and_rejects_different_head(self):
        expected = self.prepare()
        self.assertEqual(self.prepare(), expected)
        with self.assertRaisesRegex(ValueError, 'trusted head'):
            c.prepare(self.bundle, self.destination, expected_genesis=self.evidence['genesis'], expected_head='0' * 64)
        self.assertEqual(self.prepare(), expected)

    def test_interrupted_local_publication_recovers(self):
        with patch.object(c.bootstrap, '_publish_directory', side_effect=OSError('interrupted')):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                self.prepare()
        self.assertFalse(self.destination.exists())
        self.prepare()
        c.verify(self.destination, **self.anchors)

    def test_artifact_loss_and_truncated_history_refuse(self):
        self.prepare()
        manifest_path = self.destination / 'history/manifest.json'
        manifest = c.loads(manifest_path.read_bytes())
        sha = manifest['entries'][-1]['artifacts'][0]['sha256']
        artifact = c.history.blob_path(self.destination / 'history', sha)
        original = artifact.read_bytes()
        artifact.unlink()
        with self.assertRaises(OSError):
            c.verify(self.destination, **self.anchors)
        artifact.write_bytes(original)
        manifest['entries'].pop()
        manifest_path.write_bytes(c.canonical(manifest))
        with self.assertRaisesRegex(ValueError, 'truncated|head'):
            c.verify(self.destination, **self.anchors)

    def test_unanchored_receipt_cannot_add_a_source_claim(self):
        changed = copy.deepcopy(self.receipt)
        changed['source']['cid'] = 'another-cid'
        changed['id'] = c.history.digest({k: v for k, v in changed.items() if k != 'id'})
        with self.assertRaisesRegex(ValueError, 'not anchored'):
            c.prepare(self.bundle, self.destination, receipts=[changed], **self.anchors)
        self.assertFalse(self.destination.exists())

    def test_known_prefix_is_required_and_preserved(self):
        manifest = c.loads((self.bundle / 'manifest.json').read_bytes())
        known = manifest['entries'][2]['id']
        c.prepare(self.bundle, self.destination, base_head=known, **self.anchors)
        c.verify(self.destination, base_head=known, **self.anchors)
        with self.assertRaisesRegex(ValueError, 'known base head'):
            c.verify(self.destination, base_head='f' * 64, **self.anchors)

    def test_extension_retains_exact_old_entries_and_custody(self):
        database = self.case / 'world.json'
        shutil.copyfile(self.database, database)
        state = c.loads(database.read_bytes())
        c.history.world.exchange(database, {'op': 'invoke', 'object': 'b', 'principal': 'A',
            'intent': 'continue', 'expected': state['objects']['b'], 'command': 'add',
            'input': {'amount': 1}}, profile='transactions')
        extended = self.case / 'extended'
        evidence = c.history.export_history(database, extended, prefix_bundle=self.bundle,
            expected_prefix_genesis=self.evidence['genesis'], expected_prefix_head=self.evidence['head'])
        c.prepare(extended, self.destination, expected_genesis=evidence['genesis'], expected_head=evidence['head'],
                  base_head=self.evidence['head'])
        original = c.loads((self.bundle / 'manifest.json').read_bytes())
        current = c.loads((self.destination / 'history/manifest.json').read_bytes())
        self.assertEqual(c.canonical(current['entries'][:5]), c.canonical(original['entries']))
        self.assertEqual(self.index()['roots'][1]['root']['state']['count'], 5)


if __name__ == '__main__':
    unittest.main()
