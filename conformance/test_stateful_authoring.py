"""Resident-owned state, post-only revision, current-law migration and exact recovery.

Only public repository GET transport is simulated. Native admission/compiler/view
hosts must already be built. No public message is sent by this journey.
"""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
_spec = importlib.util.spec_from_file_location('stateful_post_helpers', ROOT / 'conformance/test_town_forge_journey.py')
helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helpers)
import continuation
import workspace

PACKAGE = ROOT / 'protocols/stateful-workshop'
FIELDS = helpers.clerk.loads((PACKAGE / 'migration-fields.json').read_bytes())


def monotonic():
    context = ['bound', 0]
    count = lambda which: ['get', ['get', context, which], 'count']
    return ['lam', ['binary', 'lessEqual', count('state'), count('nextState')]]


class StatefulAuthoring(helpers.TownForgeJourneyTests):
    # Reuse the actual posts/queue harness, not the historical stateless journey.
    test_maker_checks_installs_and_revises_a_door_visitors_can_use = None

    def setUp(self):
        original = helpers.forge.build_stateful
        def configured(visitors, compiler):
            return original(visitors, compiler, methods=['light', 'douse'], state_fields=FIELDS)
        with patch.object(helpers.forge, 'build', side_effect=configured):
            super().setUp()

    def post(self, card, fields, *, action=None, **kwargs):
        if action is not None:
            action = next(item['id'] for item in card['card']['actions'] if item['command'] == action)
        return super().post(card, fields, action=action, **kwargs)

    def submit_revision(self, target, name, source_file, example_file, state):
        candidate, card = self.make('desks', name)
        fields = {'target': target, 'source': (PACKAGE / source_file).read_text(),
                  'scenarios': (PACKAGE / example_file).read_text(),
                  'migration_lit': state['lit'], 'migration_count': state['count']}
        source, response = self.reply(card, fields)
        self.committed(response)
        pending = self.root(candidate)
        self.assertEqual(pending['state']['proposal']['syntax'], 'objective-bend-spell@2')
        self.assertEqual(pending['state']['migration'], state)
        ready = self.check(candidate, source)
        self.assertEqual(ready['status'], 'ready', ready)
        return candidate, ready

    def revise_law(self, target, authority, name):
        self.sequence += 1
        uri = f'at://{helpers.MAKER}/{helpers.clerk.FEED}/law-{self.sequence}'
        cid = 'law-cid-' + str(self.sequence)
        self.pds.records[uri] = (cid, {'$type': helpers.clerk.FEED,
            'text': name})
        decision = {'status': 'act', 'interpreter': 'local journey operator',
            'basis': name, 'request': {'op': 'law', 'object': target,
            'expected': self.root(target), 'law': authority}}
        reply = self.operator.receive(uri, cid, interpretation=decision)
        self.committed(reply)
        return reply

    def test_two_residents_revise_preserve_refuse_migrate_restore_and_retry(self):
        target, _ = self.make('objects', 'moth-instrument')
        first_desk, ready = self.submit_revision(target, 'first-score',
            'Instrument.obend', 'instrument.examples', {'lit': False, 'count': 0})
        _, installed = self.reply(ready['cards'][0], {})
        self.committed(installed)
        law = copy.deepcopy(self.root(target)['law'])
        law.update(profile='delvetalk-scoped-law-v2', invariant=monotonic())
        self.revise_law(target, law, 'Keep the note count on every receiving write.')
        first_card = self.capture(target)
        self.assertIn('Light the lantern', first_card['body'])
        first_parent = self.publish([first_card])
        _, lit = self.reply(first_card, {}, action='light', author=helpers.MAKER, parent=first_parent)
        self.committed(lit)
        self.assertEqual(self.root(target)['state'], {'lit': True, 'count': 1})
        lit_card = self.capture(target)
        self.assertIn('Let it sleep', lit_card['body'])
        self.assertNotIn('Light the lantern', lit_card['body'])
        _, dark = self.reply(lit_card, {}, action='douse', author=helpers.VISITOR)
        self.committed(dark)

        preserved = copy.deepcopy(self.root(target)['state'])
        second_desk, second_ready = self.submit_revision(target, 'chorus-score',
            'Chorus.obend', 'chorus.examples', preserved)
        original_law = copy.deepcopy(self.root(target)['law'])
        _, adopted = self.reply(second_ready['cards'][0], {})
        self.committed(adopted)
        self.assertEqual(self.root(target)['state'], preserved)
        self.assertEqual(self.root(target)['law'], original_law)
        chorus_card = self.capture(target)
        self.assertIn('Moth chorus', chorus_card['body'])
        self.assertIn('Play the chorus', chorus_card['body'])
        # An old interface never silently becomes a request at a fresh root.
        _, stale = self.reply(first_card, {}, action='light', author=helpers.VISITOR, parent=first_parent)
        self.assertEqual(stale['receipt']['reply']['kind'], 'refused')
        self.assertEqual(stale['receipt']['reply']['data'], 'stale read root')

        incompatible, reset_ready = self.submit_revision(target, 'new-season',
            'Chorus.obend', 'chorus.examples', {'lit': False, 'count': 0})
        before_desk, before_target = self.root(incompatible), self.root(target)
        _, refused = self.reply(reset_ready['cards'][0], {})
        self.assertEqual(refused['receipt']['reply']['kind'], 'refused')
        self.assertEqual(refused['receipt']['reply']['data'], 'state invariant refused')
        self.assertEqual(self.root(incompatible), before_desk)
        self.assertEqual(self.root(target), before_target)
        # Management deliberately changes the rule, subject to the old guard.
        relaxed = copy.deepcopy(original_law)
        relaxed['invariant'] = ['lam', ['boolean', True]]
        self.revise_law(target, relaxed, 'The maker explicitly starts a new season.')
        fresh = self.book.capture_adoption(incompatible, self.root(incompatible),
            target, self.root(target), alias='new-season-current')
        _, reset = self.reply(fresh, {})
        self.committed(reset)
        self.assertEqual(self.root(target)['state'], {'lit': False, 'count': 0})
        self.revise_law(target, original_law, 'Restore retained-count protection for this season.')

        # Lose presentation after actual admission, then restart and recover exact reply.
        final_card = self.capture(target)
        source = self.post(final_card, {}, action='light', author=helpers.VISITOR)
        save = helpers.town.save
        def lost(path, value):
            if 'response' in value:
                raise OSError('lost presentation after real admission')
            return save(path, value)
        with patch.object(helpers.town, 'save', side_effect=lost), self.assertRaises(OSError):
            self.operator.receive(*source)
        before_recovery = self.clerk.database.read_bytes()
        self.operator = helpers.town.Town(self.clerk.state, request=self.pds)
        records, calls = self.pds.records, len(self.pds.calls)
        self.pds.records = {}
        recovered = self.operator.receive(*source)
        self.committed(recovered)
        self.assertEqual(self.operator.receive(*source), recovered)
        self.assertEqual(len(self.pds.calls), calls)
        self.assertEqual(self.clerk.database.read_bytes(), before_recovery)
        self.pds.records = records
        self.assertEqual(self.root(target)['state'], {'lit': True, 'count': 2})

        bundle = self.base / 'exported-history'
        prepared = workspace.bootstrap.export_bootstrap(self.home, bundle)
        continuation.prepare(bundle, self.base / 'continuation',
            expected_genesis=prepared['genesis'], expected_head=prepared['head'])
        restored = self.base / 'restored'
        workspace.bootstrap.restore_bootstrap(bundle, restored,
            expected_genesis=prepared['genesis'], expected_head=prepared['head'])
        self.assertEqual(helpers.clerk.loads((restored / 'world.json').read_bytes()),
                         helpers.clerk.loads(self.clerk.database.read_bytes()))
        for candidate in (first_desk, second_desk, incompatible):
            artifact = self.root(candidate)['state']['artifact']
            self.assertEqual((restored / 'artifacts/builds' / (artifact + '.json')).read_bytes(),
                             (self.home / 'artifacts/builds' / (artifact + '.json')).read_bytes())
        restored_client = helpers.compiler_queue.desk.Desk(restored / 'world.json',
            restored / 'artifacts', profile='compiled')
        restored_before = restored_client.database.read_bytes()
        self.assertEqual(restored_client.exchange(recovered['receipt']['request']),
                         recovered['receipt']['reply'])
        self.assertEqual(restored_client.database.read_bytes(), restored_before)
        view = workspace.bootstrap.room.inspect_object(restored_client.inspect(target), target)
        self.assertIn('Moth chorus', view['data']['title'])
        self.assertEqual(self.root(target)['law'], original_law)


if __name__ == '__main__':
    unittest.main()
