#!/usr/bin/env python3
"""Original scene + textual convention through real portal tokens and Lean."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('scene_exchange_journey', ROOT / 'examples/scene-exchange/journey.py')
journey = importlib.util.module_from_spec(spec)
spec.loader.exec_module(journey)


class SceneExchangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name) / 'relay'
        cls.report = journey.run(cls.directory)
        cls.events = journey.history.loads((cls.directory / 'events.json').read_bytes())
        cls.snapshot = journey.history.loads((cls.directory / 'world.json').read_bytes())

    def test_original_sources_survive_proposal_installation_and_history(self):
        manifest = journey.history.loads((self.directory / 'history/manifest.json').read_bytes())
        for key, filename in [('relay', 'rain-relay.scene'), ('card', 'rain-card.md')]:
            with self.subTest(source=filename):
                original = (ROOT / 'examples/scene-exchange' / filename).read_bytes()
                self.assertEqual((self.directory / 'sources' / filename).read_bytes(), original)
                report = journey.history.loads((self.directory / 'artifacts' / (key + '-proposal.json')).read_bytes())
                self.assertTrue(report['passed'])
                self.assertEqual(report['candidate']['artifact']['source']['text'].encode(), original)
                entry = next(e for e in manifest['entries'] if e['request']['intent'] == 'create-' + key)
                sources = [journey.history.read_blob(self.directory / 'history', a['sha256']).read_bytes()
                           for a in entry['artifacts']]
                self.assertIn(original, sources)
        self.assertEqual(self.report['history']['worldSha256'], journey.history.digest(self.snapshot))
        self.assertEqual(self.report['verified']['worldSha256'], journey.history.digest(self.snapshot))
        self.assertEqual(self.report['rainName'], {'name': 'Threadsong', 'ink': 'silver', 'by': 'tavi'})

    def test_two_saved_observations_require_refresh_and_retry_keeps_history(self):
        free = next(e for e in self.events if e['draft']['summary'] == 'Free the roof vane'
                    and e['response']['kind'] == 'committed')
        stale = next(e for e in self.events if e['response'].get('reply', {}).get('data') == 'stale read root')
        self.assertEqual(stale['draft']['wire']['expected'], free['draft']['wire']['expected'])
        self.assertEqual(stale['principal'], 'tavi')
        self.assertTrue(self.report['retryRecovered'])
        self.assertEqual(len(self.snapshot['receipts']), len(self.events) + 2)
        refusals = [e['response']['reply']['data'] for e in self.events if e['response']['kind'] == 'refused']
        self.assertIn('unauthorized', refusals)
        self.assertIn('stale read root', refusals)
        self.assertEqual(len(refusals), 4)

    def test_final_room_agrees_with_pinned_spween_reference(self):
        source = (ROOT / 'examples/scene-exchange/rain-relay.scene').read_text()
        lower = journey.room.lower
        reference = lower.bridge({'op': 'replay', 'source': source,
                                  'actions': [{'choose': i} for i in [2, 0, 1, 2]]})
        self.assertTrue(reference['ok'], reference)
        expected = reference['trace'][-1]['snapshot']
        session = self.snapshot['objects']['scene:rain-relay']['state']['session']
        self.assertEqual(session['passage'], expected['state']['index'])
        self.assertFalse(session['ended'])
        self.assertEqual({k: lower.decode_value(v) for k, v in session['vars'].items()}, expected['vars'])
        self.assertEqual(lower.decode_sequence(session['choices']), expected['choices'])
        release = next(e for e in self.events if e['draft']['summary'] == 'Release the rain note'
                       and e['response']['kind'] == 'committed')
        calls = [call for batch in release['response']['reply']['data']['outbox']
                 for call in lower.decode_sequence(batch['calls'])]
        self.assertEqual([{'name': c['name'], 'args': [lower.decode_value(a)
                          for a in lower.decode_sequence(c['args'])]} for c in calls], expected['calls'])

    def test_copyable_tokens_and_typed_fields_reach_existing_admission(self):
        for event in self.events:
            self.assertEqual(event['interpretation']['via'], 'tokens')
            self.assertEqual(event['interpretation']['status'], 'proposed')
            self.assertTrue(event['token'].startswith('do ' + event['card']['card'] + ' '))
            self.assertNotIn('root', event['card'])
        self.assertEqual(self.report['fieldClarification'], 'clarify')
        name = next(e for e in self.events if e['draft']['summary'] == 'Name the rain'
                    and e['response']['kind'] == 'committed')
        self.assertEqual(name['draft']['wire']['input'], {'name': 'Threadsong', 'ink': 'silver'})
        self.assertEqual({field['type'] for field in name['card']['actions'][0]['fields']}, {'string', 'enum'})
        room = journey.history.loads((self.directory / 'final-room.json').read_bytes())
        self.assertEqual(room['mode'], 'room')
        self.assertIn('silver line trembles', room['prose'])


if __name__ == '__main__':
    unittest.main()
