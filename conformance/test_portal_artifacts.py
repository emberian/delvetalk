"""Bound room lookup isolates unrelated damage without weakening validation."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import portal


class PortalArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.store = self.directory / 'artifacts/rooms'
        room = portal.bootstrap.room
        # Lookup/rendering contract needs neither compilation nor world mutation.
        # This retained bundle uses the actual artifact wrapper and validator.
        source = 'A retained source, with exact newlines.\r\n'
        provenance = {'upstream': room.lower.UPSTREAM,
                      'sourceSha256': hashlib.sha256(source.encode()).hexdigest(),
                      'compilerSha256': room.current_pins()['scene/lower.py']}
        state = {'session': {'started': False, 'ended': False, 'passage': 0,
                            'choices': {'length': 0, 'items': {}}, 'requirements': False,
                            'vars': {}, 'visited': {'0': False}}}
        protocol = {'profile': 'delvetalk-local-v1', 'name': 'retained room',
                    'sceneProfile': room.lower.PROFILE, 'provenance': provenance,
                    'initial': state, 'commands': {}}
        bundle = {'profile': room.lower.PROFILE, 'source': source,
                  'ast': {'meta': {'title': 'Retained room'}, 'passages': []},
                  'upstream': room.lower.UPSTREAM, 'provenance': provenance,
                  'initialVars': {}, 'has': {}, 'protocol': protocol}
        self.artifact = room.wrap_bundle(bundle)
        self.identity = room.store_artifact(self.store, self.artifact)
        self.path = room.artifact_path(self.store, self.identity)
        self.root = {'protocol': self.artifact['protocol'], 'state': state, 'version': 0, 'law': []}
        self.app = object.__new__(portal.Portal)
        self.app.directory = self.directory

    def view(self): return self.app._view(self.root, 'room', 'main')

    def replace(self, artifact, *, correct_name=False):
        self.path.unlink()
        data = portal.bootstrap.room.canonical(artifact)
        name = hashlib.sha256(data).hexdigest() if correct_name else self.identity
        (self.store / (name + '.json')).write_bytes(data)

    def test_unrelated_corruption_does_not_block_bound_room_or_get_validated(self):
        (self.store / ('0' * 64 + '.json')).write_bytes(b'{broken')
        (self.store / ('1' * 64 + '.json')).write_bytes(b'{"protocol":{"roomArtifact":{"contentSha256":"unrelated"}}}')
        with patch.object(portal.bootstrap.room, 'load_artifact', wraps=portal.bootstrap.room.load_artifact) as load:
            view = self.view()
        self.assertEqual(view['mode'], 'room')
        self.assertEqual(view['source'], self.artifact['content']['source'])
        self.assertEqual(load.call_count, 1)
        self.assertEqual(load.call_args.args, (self.store, self.identity))

    def test_matching_source_corruption_refuses_even_with_valid_byte_identity(self):
        changed = copy.deepcopy(self.artifact)
        changed['content']['source'] += 'Substituted source.'
        self.replace(changed, correct_name=True)
        with self.assertRaisesRegex(ValueError, 'source digest mismatch'):
            self.view()

    def test_matching_filename_or_byte_identity_corruption_refuses(self):
        data = self.path.read_bytes()
        self.path.unlink()
        (self.store / ('f' * 64 + '.json')).write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'byte digest mismatch'):
            self.view()

    def test_matching_protocol_mismatch_is_not_accepted_as_alias(self):
        changed = copy.deepcopy(self.artifact)
        changed['protocol']['name'] = 'Different admitted program'
        self.replace(changed, correct_name=True)
        # Same content binding and valid full artifact, different program.
        with self.assertRaisesRegex(ValueError, 'Exact bound room artifact is unavailable'):
            self.view()

    def test_same_content_for_another_valid_program_does_not_block_exact_program(self):
        changed = copy.deepcopy(self.artifact)
        changed['protocol']['name'] = 'Another legitimate program over the same source'
        identity = portal.bootstrap.room.store_artifact(self.store, changed)
        self.assertNotEqual(identity, self.identity)
        self.assertEqual(changed['protocol']['roomArtifact'], self.artifact['protocol']['roomArtifact'])
        with patch.object(portal.bootstrap.room, 'load_artifact', wraps=portal.bootstrap.room.load_artifact) as load:
            view = self.view()
        self.assertEqual(view['mode'], 'room')
        self.assertEqual(view['root']['protocol'], self.root['protocol'])
        self.assertEqual(load.call_count, 1)
        self.assertEqual(load.call_args.args, (self.store, self.identity))

    def test_matching_corruption_is_not_hidden_by_another_valid_candidate(self):
        changed = copy.deepcopy(self.artifact)
        changed['content']['source'] += 'broken'
        data = portal.bootstrap.room.canonical(changed)
        (self.store / (hashlib.sha256(data).hexdigest() + '.json')).write_bytes(data)
        with self.assertRaises(ValueError): self.view()

    def test_missing_or_unreadable_bound_artifact_is_clear(self):
        self.path.write_bytes(b'{broken')
        with self.assertRaisesRegex(ValueError, 'Exact bound room artifact is unavailable'):
            self.view()
        self.root['protocol']['roomArtifact'] = {'format': 'wrong', 'contentSha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'Invalid admitted room artifact binding'):
            self.view()


if __name__ == '__main__': unittest.main()
