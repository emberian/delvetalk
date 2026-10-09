"""Pending source references require original bytes even without a compiler result."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workspace
import source_store

b = workspace.bootstrap
ROOT = Path(__file__).resolve().parents[1]


class SourceHistory(unittest.TestCase):
    def test_pending_source_and_adapter_bytes_are_required_by_plain_history_verifier(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'world'
            workspace.initialize(directory, [{'id': 'desk', 'syntax': 'protocol-json@1',
                'source': (ROOT / 'protocols/source-desk/protocol.json').read_bytes(),
                'law': ['author']}], entry_objects=['desk'], principal='builder')
            # Deliberately uncompiled: source availability is independent of success.
            proposal = source_store.prepare_proposal(directory / 'artifacts',
                'protocol-markdown@1', b'# Authored source\r\n' + b'opaque prose\n' * 6000, b'[]\n')
            desk = b.desk_module.Desk(directory / 'world.json', directory / 'artifacts')
            reply = desk.exchange({'op': 'invoke', 'object': 'desk', 'principal': 'author',
                'intent': 'pending-source', 'expected': desk.inspect('desk'), 'command': 'submit',
                'input': {'proposal': proposal, 'migration': {}, 'target': 'later'}})
            self.assertEqual(reply['kind'], 'committed')
            bundle = Path(temporary) / 'bundle'
            anchors = b.export_bootstrap(directory, bundle)
            def verify():
                return b.history.verify_history(bundle, expected_genesis=anchors['genesis'], expected_head=anchors['head'])
            verify()
            required = [proposal['sourceRef']['sha256'], proposal['scenariosRef']['sha256'],
                        next(iter(source_store.declared_dependencies(proposal).values()))]
            for sha in required:
                path = b.history.blob_path(bundle, sha)
                raw = path.read_bytes()
                with self.subTest(missing=sha):
                    path.unlink()
                    try:
                        with self.assertRaises((ValueError, OSError)):
                            verify()
                    finally:
                        path.write_bytes(raw)
            source_path = b.history.blob_path(bundle, proposal['sourceRef']['sha256'])
            raw = source_path.read_bytes()
            source_path.write_bytes(raw + b'substitution')
            with self.assertRaisesRegex(ValueError, 'length mismatch'):
                verify()


if __name__ == '__main__':
    unittest.main()
