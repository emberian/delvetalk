"""Portal reads exact source roots; external custody does not choose behavior."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import portal


class PortalArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = '---\nid: portal_source\ntitle: Retained source room\n---\n=== start\nA quiet source room.\n* [Leave]\n  -> END\n'
        cls.artifact = portal.bootstrap.room.compile_artifact(cls.source)
        cls.revision = portal.bootstrap.room.compile_artifact(cls.source.replace('Retained source room', 'Revised source room'))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.database = self.directory / 'world.json'
        self.store = self.directory / 'artifacts/rooms'
        self.law = {'profile': 'delvetalk-scoped-law', 'read': ['alice'],
                    'invoke': {'start': ['alice'], 'choose': ['alice']},
                    'reprogram': ['alice'], 'law': ['alice']}
        created = self.exchange({'op': 'create', 'object': 'room', 'principal': 'alice', 'intent': 'create',
            'protocol': self.artifact['protocol'], 'law': self.law})
        self.assertEqual(created['kind'], 'committed', created)
        self.root = created['data']['root']
        self.identity = portal.bootstrap.room.store_artifact(self.store, self.artifact)
        self.path = portal.bootstrap.room.artifact_path(self.store, self.identity)
        portal.save(self.directory / 'manifest.json', {'cafe': 'room',
                    'runtime': portal.bootstrap.history.runtime('compiled')})
        self.app = portal.Portal(self.directory, principal='alice', allow_local_actions=True)

    def exchange(self, request):
        return portal.world.exchange(self.database, request, profile='compiled')

    def test_external_corruption_cannot_select_or_block_admitted_source(self):
        self.path.write_bytes(b'{broken')
        (self.store / ('0' * 64 + '.json')).write_bytes(b'{"source":"substituted"}')
        with patch.object(portal.bootstrap.room, 'load_artifact', side_effect=AssertionError('external artifact selected behavior')):
            card = self.app.object('room')
            detail = self.app.detail(card['card'])
        self.assertEqual(card['mode'], 'projection')
        self.assertEqual(detail['source']['source'], self.source)
        self.assertEqual(detail['root']['protocol'], self.artifact['protocol'])

    def test_exact_source_artifact_tampering_still_refuses_custody(self):
        changed = copy.deepcopy(self.artifact)
        changed['content']['source'] += 'Substituted source.'
        with self.assertRaises(portal.bootstrap.room.ArtifactError):
            portal.bootstrap.room.store_artifact(self.store, changed)
        self.assertEqual(self.app.detail(self.app.object('room')['card'])['source']['source'], self.source)

    def test_artifact_filename_identity_corruption_is_detected(self):
        raw = self.path.read_bytes()
        self.path.unlink()
        (self.store / ('f' * 64 + '.json')).write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'byte digest mismatch'):
            portal.bootstrap.room.load_artifact(self.store, 'f' * 64)
        self.assertEqual(self.app.object('room')['title'], 'Retained source room')

    def test_cached_source_retains_its_observation_after_source_revision(self):
        card = self.app.object('room')
        revised = self.exchange({'op': 'reprogram', 'object': 'room', 'principal': 'alice',
            'intent': 'revise', 'expected': self.root, 'protocol': self.revision['protocol'],
            'state': self.revision['protocol']['initial']})
        self.assertEqual(revised['kind'], 'committed', revised)
        captured = self.app.detail(card['card'])
        self.assertEqual(captured['root'], self.root)
        self.assertEqual(captured['source']['source'], self.source)
        self.assertEqual(self.app.object('room')['title'], 'Revised source room')

    def test_current_read_law_applies_to_cached_card_and_detail(self):
        card = self.app.object('room')
        revoked = {**self.law, 'read': []}
        changed = self.exchange({'op': 'law', 'object': 'room', 'principal': 'alice',
            'intent': 'lock-read', 'expected': self.root, 'law': revoked})
        self.assertEqual(changed['kind'], 'committed', changed)
        for access in (self.app.card, self.app.detail):
            with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
                access(card['card'])
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            self.app.object('room')

    def test_source_reference_does_not_grant_another_participant_read(self):
        other = portal.Portal(self.directory, state=self.directory / 'other-custody', principal='bob', allow_local_actions=True)
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            other.object('room')
        creator = self.exchange({'op': 'create', 'object': 'private', 'principal': 'alice',
            'intent': 'private', 'protocol': self.artifact['protocol'],
            'law': {**self.law, 'read': ['bob']}})
        self.assertEqual(creator['kind'], 'committed', creator)
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            self.app.object('private')

    def test_saved_view_source_cannot_be_substituted(self):
        card = self.app.object('room')
        saved = self.app._read('cards', card['card'])
        view = copy.deepcopy(saved['view'])
        view['source']['profile'] = 'substituted'
        with self.assertRaisesRegex(ValueError, 'saved view source differs'):
            portal.bootstrap.room.source_document(view)


if __name__ == '__main__':
    unittest.main()
