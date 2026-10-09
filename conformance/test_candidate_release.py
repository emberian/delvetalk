"""The ordinary Candidate authors its release; the Editor keeps its approval gate."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_desk as fixture

D = fixture.desk_module


class CandidateRelease(unittest.TestCase):
    def setUp(self):
        self.custody = fixture.DeskTests()
        self.custody.setUp()
        self.addCleanup(self.custody.doCleanups)
        self.ready = self.custody.ready()

    def offer(self):
        view = D.projection.project(self.ready, 'candidate')
        return D.source_offers.capture(view, {'candidate': self.ready,
            'target': self.custody.target})['release']

    def test_source_preparation_retains_exact_reads_without_a_host_recipe(self):
        offer = self.offer()
        self.assertEqual(offer['entry'], 'prepareRelease')
        self.assertNotIn('calls', offer)
        self.assertEqual(offer['observations'][0]['root'], self.custody.target)
        request = D.source_offers.request(offer, 'reviewer', 'source-release', {})
        self.assertEqual(request['reads'], {'candidate': self.ready, 'target': self.custody.target})
        self.assertEqual(request['calls'], [
            {'object': 'candidate', 'command': 'adopt', 'input': {'target': 'target'}},
            {'op': 'reprogram', 'object': 'target', 'inputFrom': 0}])
        result = self.custody.desk.exchange(request)
        self.assertEqual(result['kind'], 'committed', result)
        self.assertEqual(self.custody.desk.exchange(request), result)

    def test_empty_form_rejects_hidden_fields_at_client_and_native_source_boundaries(self):
        offer = self.offer()
        before = self.custody.desk.database.read_bytes()
        for contribution in ({'principal': 'owner'}, {'migration': {}}, {'inputFrom': 0}):
            with self.subTest(contribution=contribution):
                with self.assertRaises(ValueError):
                    D.source_offers.request(offer, 'reviewer', 'hidden-fields', contribution)
                internal = D.source_offers.prepare_value(offer, 'reviewer', 'internal-hidden-fields', contribution)
                self.assertEqual(internal['kind'], 'refused', internal)
                outcome = D.world.query(self.custody.desk.database, {
                    'op': 'prepare-retained', 'object': 'candidate', 'root': self.ready,
                    'entry': 'prepareRelease', 'contribution': contribution,
                    'observations': offer['observations'], 'principal': 'reviewer',
                    'intent': 'raw-hidden-fields'})
                self.assertEqual(outcome['kind'], 'refused', outcome)
                self.assertIn('no additional fields', outcome['message'])
        self.assertEqual(self.custody.desk.database.read_bytes(), before)

    def test_lost_reply_recovers_original_request_before_current_compiler_or_pins(self):
        client = self.custody.desk
        exchange = client.exchange
        recovered = {}
        def lost(request):
            recovered['reply'] = exchange(request)
            raise OSError('response lost after native commit')
        with patch.object(client, 'exchange', side_effect=lost):
            with self.assertRaisesRegex(OSError, 'response lost'):
                client.adopt('candidate', 'target', 'reviewer', 'retained-release', self.ready, self.custody.target)
        restarted = D.Desk(client.database, client.artifact_store)
        with patch.object(D, 'execution_profile', side_effect=AssertionError('current pins consulted')), \
             patch.object(D.projection, 'project', side_effect=AssertionError('compiler unavailable')), \
             patch.object(D.source_offers, 'prepare', side_effect=AssertionError('reprepared')):
            self.assertEqual(restarted.adopt('candidate', 'target', 'reviewer', 'retained-release',
                self.ready, self.custody.target), recovered['reply'])
        with self.assertRaisesRegex(ValueError, 'different inputs'):
            restarted.adopt('candidate', 'target', 'reviewer', 'retained-release',
                self.ready, restarted.inspect('target'))

    def test_pending_attempt_refuses_changed_runtime_and_tampered_custody(self):
        client = self.custody.desk
        before = client.database.read_bytes()
        with patch.object(client, 'exchange', side_effect=OSError('not sent')):
            with self.assertRaises(OSError):
                client.adopt('candidate', 'target', 'reviewer', 'pending-release', self.ready, self.custody.target)
        with patch.object(D, 'execution_profile', return_value={'profile': 'changed'}), \
             patch.object(D.projection, 'project', side_effect=AssertionError('reprepared changed runtime')):
            with self.assertRaisesRegex(ValueError, 'runtime changed'):
                client.adopt('candidate', 'target', 'reviewer', 'pending-release', self.ready, self.custody.target)
        attempt = next((client.artifact_store / 'releases').glob('*.json'))
        entry = D.loads(attempt.read_bytes())
        entry['request']['calls'] = []
        attempt.write_bytes(D.canonical(entry))
        with self.assertRaisesRegex(ValueError, 'invalid retained'):
            client.adopt('candidate', 'target', 'reviewer', 'pending-release', self.ready, self.custody.target)
        self.assertEqual(client.database.read_bytes(), before)

    def test_source_encounter_links_target_and_bounds_compiler_diagnostics(self):
        view = D.projection.project(self.ready, 'candidate')
        self.assertEqual(D.projection.children(view)[0]['object'], 'target')
        failed = deepcopy(self.ready)
        for field in failed['state']['model']['fields']:
            if field['name'] == 'status':
                field['value'] = D.source_object.data('failed')
            elif field['name'] == 'diagnostics':
                field['value'] = D.source_object.value([{'message': 'The example expected another result.'}])
        view = D.projection.project(failed, 'candidate')
        self.assertIn('The example expected another result.', view['data']['prose'])
        for field in failed['state']['model']['fields']:
            if field['name'] == 'diagnostics':
                field['value'] = D.source_object.value([{'message': 'x' * 1025}])
        bounded = D.projection.project(failed, 'candidate')
        self.assertLess(len(bounded['data']['prose']), 200)
        self.assertIn('retained report', bounded['data']['prose'])

    def test_editor_mode_has_no_ordinary_release_and_source_refuses_direct_preparation(self):
        edited = deepcopy(self.ready)
        for field in edited['state']['model']['fields']:
            if field['name'] == 'editorMode':
                field['value'] = D.source_object.data(True)
        view = D.projection.project(edited, 'candidate')
        self.assertEqual(D.source_offers.capture(view, {'candidate': edited,
            'target': self.custody.target}), {})
        offer = self.offer()
        offer['root'] = edited
        outcome = D.source_offers.prepare(offer, 'reviewer', 'no-editor-bypass', {})
        self.assertEqual(outcome['kind'], 'refused', outcome)
        self.assertIn('editor', outcome['message'])
        self.assertEqual(self.custody.desk.inspect('candidate'), self.ready)


if __name__ == '__main__':
    unittest.main()
