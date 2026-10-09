"""Default scene custody reaches ordinary Bend methods and source migration."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object
import world


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


room = module('source_scene_room', 'scene/room.py')
bootstrap = module('source_scene_bootstrap', 'scripts/bootstrap.py')


class SourceScene(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db = Path(self.temporary.name) / 'world.json'
        self.serial = 0

    def send(self, request, expected='committed'):
        receipt = world.exchange(self.db, request, profile='compiled')
        self.assertEqual(receipt['kind'], expected, receipt)
        return receipt

    def intent(self):
        self.serial += 1
        return 'scene-' + str(self.serial)

    def root(self):
        return world.exchange(self.db, {'op': 'inspect', 'object': 'cafe', 'principal': 'iris'}, profile='compiled')

    def test_default_compiler_never_authors_legacy_transitions_and_actions_reach_source(self):
        source = (bootstrap.EXAMPLES / 'cafe.scene').read_text()
        self.assertFalse((ROOT / 'scene/lower.py').exists())
        artifact = room.compile_artifact(source)
        protocol = artifact['protocol']
        self.assertIn('sourcePackages', protocol)
        self.assertNotIn('roomArtifact', protocol)
        self.assertEqual(set(protocol['commands']), {'start', 'choose'})
        self.assertTrue(all(command['transition']['profile'] == 'delvetalk-source-transition'
                            for command in protocol['commands'].values()))
        self.send({'op': 'create', 'object': 'cafe', 'principal': 'operator', 'intent': 'create',
            'protocol': protocol, 'law': {'profile': 'delvetalk-scoped-law', 'read': 'public',
                'invoke': {'start': ['iris', 'moss'], 'choose': ['iris', 'moss']},
                'reprogram': ['moss'], 'law': ['operator']}})
        entry = room.room_view(self.root(), artifact, 'cafe')
        self.assertEqual(entry['mode'], 'projection', entry)
        self.send(room.start_request(entry, 'iris', self.intent()))
        shared = room.room_view(self.root(), artifact, 'cafe')
        aligned = self.send(room.choice_request(shared, 0, 'iris', self.intent()))
        self.send(room.choice_request(shared, 1, 'moss', self.intent()), 'refused')
        current = room.room_view(self.root(), artifact, 'cafe')
        wound = self.send(room.choice_request(current, 1, 'moss', self.intent()))
        self.assertNotEqual(wound['data']['root']['state'], aligned['data']['root']['state'])
        repaired = self.root()
        revision_source = bootstrap.cafe_proposal_source()
        migrated = bootstrap.cafe_migration(revision_source, repaired)
        improved = bootstrap.scene_workshop.lower(revision_source.decode())
        old = source_object.plain(source_object.state_data(repaired))
        new = source_object.plain(source_object.state_data({'protocol': improved, 'state': migrated}))
        self.assertNotEqual(new['scene'], old['scene'])
        self.assertNotIn('Score', {m['name'] for m in protocol['sourcePackages']['resident']['modules']})
        for key in ['passage', 'visited', 'started', 'ended']:
            self.assertEqual(new[key], old[key])
        self.assertEqual(new['handler']['members'], old['handler']['members'])
        self.assertEqual(new['handler']['repairs'], old['handler']['repairs'])
        # The source migration extends the exact list of prior variables.
        previous = old['handler']['variables']
        extended = new['handler']['variables']
        while previous['variant'] == 'cons':
            self.assertEqual(previous['payload']['head'], extended['payload']['head'])
            previous, extended = previous['payload']['tail'], extended['payload']['tail']
        self.assertEqual(extended['payload']['head'], {'name': 'chalk_star',
            'value': {'variant': 'boolean', 'payload': {'value': False}}})
        revised = self.send({'op': 'reprogram', 'object': 'cafe', 'principal': 'moss',
            'intent': self.intent(), 'expected': repaired, 'protocol': improved, 'state': migrated})
        revised_artifact = room.source_artifact(improved)
        installed = room.room_view(revised['data']['root'], revised_artifact, 'cafe')
        self.send(room.choice_request(shared, 1, 'moss', self.intent()), 'refused')
        self.send(room.choice_request(installed, 2, 'moss', self.intent()))
        window = room.room_view(self.root(), revised_artifact, 'cafe')
        self.assertIn('constellation', window['data']['prose'])
        self.send(room.choice_request(window, 0, 'iris', self.intent()))
        final = room.room_view(self.root(), revised_artifact, 'cafe')
        self.assertNotIn('choose', [action['command'] for action in final['data']['actions'].values()])
        stored = room.store_artifact(Path(self.temporary.name) / 'rooms', revised_artifact)
        restored = room.load_artifact(Path(self.temporary.name) / 'rooms', stored)
        self.assertEqual(restored, revised_artifact)
        changed = copy.deepcopy(restored)
        changed['content']['source'] += '\n'
        with self.assertRaises(room.ArtifactError):
            room.validate_artifact(changed)


class SourceBootstrap(unittest.TestCase):
    def test_actual_default_journey_retains_source_revisions_and_restores(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / 'home'
            report = bootstrap.run_bootstrap(home)
            self.assertEqual(report['finalView']['mode'], 'projection')
            self.assertIn('sourcePackages', report['finalView']['root']['protocol'])
            self.assertEqual(report['finalView']['root']['state'], bootstrap.inspect_view(home)['root']['state'])
            bundle = Path(temporary) / 'bundle'
            anchors = bootstrap.export_bootstrap(home, bundle)
            with patch.object(bootstrap.room, 'compile_artifact', side_effect=AssertionError('recompiled restore')):
                restored = bootstrap.restore_bootstrap(bundle, Path(temporary) / 'restored',
                    expected_genesis=anchors['genesis'], expected_head=anchors['head'])
            self.assertEqual(restored['worldSha256'], anchors['worldSha256'])
            self.assertEqual(bootstrap.inspect_view(Path(temporary) / 'restored')['root'], report['finalView']['root'])


if __name__ == '__main__':
    unittest.main()
