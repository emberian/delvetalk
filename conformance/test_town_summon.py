"""Verified original posts become source-owned sessions through explicit service custody."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import history
import town
import town_cards
import town_summon
import world
from conformance.test_clerk import FakePDS, A, B

package = clerk.module('summon_session_package', 'protocols/root-directory/package.py')
membership = clerk.module('summon_membership_package', 'protocols/membership/generate.py')
ISSUER = 'did:plc:' + 'c' * 24
SERVICE = 'town-session-service'
INTERPRETATION = {'interpreter': 'local operator', 'basis': 'The author asks for a fresh DelveTalk session.'}


class TownSummon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = package.factory(package.entry())
        cls.member_program = package.factory(package.entry(), welcome='welcome')
        cls.outside_program = package.factory(package.entry(), welcome='outside')
        cls.welcome_program = membership.welcome(SERVICE, [{'object': 'shared', 'commands': ['add']}])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.pds = FakePDS()
        self.clerk = clerk.Clerk(self.base / 'clerk', self.pds)
        self.law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'make': [SERVICE]},
                    'reprogram': ['steward'], 'law': ['steward']}
        program = self.program
        if self._testMethodName in ('test_membership_uses_source_policy_and_retry_never_regrants',
                'test_lost_membership_reply_recovers_separately_from_created_session',
                'test_lost_membership_reply_changed_runtime_recovers_both_receipts',
                'test_lost_final_presentation_changed_runtime_returns_recorded_receipts',
                'test_missing_or_out_of_scope_membership_preserves_real_session'):
            program = self.member_program
        elif self._testMethodName == 'test_source_followup_outside_configured_scope_never_runs':
            program = self.outside_program
        reply = self.clerk.bootstrap('sessions', program, self.law, [A], runtime_profile='compiled')
        self.assertEqual(reply['kind'], 'committed', reply)
        self.book = town_cards.CardBook.create(self.base / 'cards', issuer_did=ISSUER,
            world_id='town-sessions', runtime=history.runtime('compiled'))
        selection = {'path': str(self.book.path), 'issuers': [ISSUER], 'metadata': self.book.metadata()}
        self.clerk.upgrade(self.clerk.profile()['sha256'], town_cards=selection)
        self.operator = town.Town(self.clerk.state, request=self.pds)
        self.service = town_summon.Summoner(self.operator)
        self.service.configure(factory='sessions', offer='make', principal=SERVICE,
                               followups=[{'object': 'welcome', 'offer': 'enroll'}])

    def post(self, key='one', author=B, text='@livedelvetalk.delve.town #gsb A new session, please.'):
        uri, cid = f'at://{author}/{clerk.FEED}/{key}', 'cid-' + key
        self.pds.records[uri] = (cid, {'$type': clerk.FEED, 'text': text})
        return uri, cid

    def summon(self, source):
        return self.service.summon(*source, **INTERPRETATION)

    def test_source_owned_session_verified_author_and_exact_restart(self):
        source = self.post()
        self.assertNotIn(B, self.clerk.config()['repositories'])
        result = self.summon(source)
        self.assertEqual(result['status'], 'committed', result)
        self.assertEqual(result['request']['principal'], SERVICE)
        self.assertEqual(result['source']['author'], B)
        self.assertEqual(result['cards'][0]['view']['object'], 'sessions/session-1')
        child = result['cards'][0]['view']['root']
        self.assertEqual(child['law']['invoke']['choose'], [B])
        self.assertIn(B, self.clerk.config()['repositories'])
        self.assertIn('sessions/session-1', self.clerk.config()['objects'])
        self.assertEqual(result['publication'], 'paused')
        self.assertIn(source[0], result['body'])
        before = self.clerk.database.read_bytes()
        self.pds.records.clear()
        restarted = town_summon.Summoner(town.Town(self.clerk.state, request=self.pds))
        with patch.object(restarted.operator, '_configuration', side_effect=AssertionError('completed replay needs no current runtime')):
            self.assertEqual(restarted.summon(*source, **INTERPRETATION), result)
        self.assertEqual(self.clerk.database.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'different CID'):
            self.service.summon(source[0], 'edited', **INTERPRETATION)
        second = self.summon(self.post('another-original'))
        self.assertEqual(second['cards'][0]['view']['object'], 'sessions/session-2')

    def test_lost_native_reply_recovers_without_second_session_or_network(self):
        source = self.post('lost')
        exchange = town_summon.world.exchange
        def lose(*args, **kwargs):
            reply = exchange(*args, **kwargs)
            self.assertEqual(reply['kind'], 'committed', reply)
            raise OSError('native reply lost after committed allocation')
        with patch.object(town_summon.world, 'exchange', side_effect=lose):
            self.assertEqual(self.summon(source)['status'], 'uncertain')
        self.pds.records.clear()
        result = self.summon(source)
        self.assertEqual(result['status'], 'committed')
        self.assertEqual([card['view']['object'] for card in result['cards']], ['sessions/session-1'])
        self.assertNotIn('sessions/session-2', world.snapshot(self.clerk.database)['objects'])
        self.assertEqual(self.summon(source), result)

    def test_lost_native_reply_changed_runtime_recovers_before_configuration(self):
        source = self.post('lost-before-runtime-change')
        exchange = town_summon.world.exchange
        native = []
        def lose(*args, **kwargs):
            native.append(exchange(*args, **kwargs))
            raise OSError('reply lost after native commit')
        with patch.object(town_summon.world, 'exchange', side_effect=lose):
            self.assertEqual(self.summon(source)['status'], 'uncertain')
        self.assertEqual(native[0]['kind'], 'committed')
        before = self.clerk.database.read_bytes()
        self.pds.records.clear()
        restarted = town_summon.Summoner(town.Town(self.clerk.state, request=self.pds))
        with patch.object(town.clerk, 'pins', return_value={}), \
                patch.object(town_summon.world, 'exchange', side_effect=AssertionError('no new admission')), \
                patch.object(town_summon.source_offers, 'prepare', side_effect=AssertionError('no source re-interpretation')), \
                patch.object(restarted.operator, '_capture_view', side_effect=AssertionError('no new presentation')):
            recovered = restarted.summon(*source, **INTERPRETATION)
        self.assertEqual(recovered['status'], 'committed')
        self.assertEqual(recovered['reply'], native[0])
        self.assertEqual(recovered['presentation']['status'], 'unavailable')
        self.assertEqual(recovered['cards'], [])
        self.assertEqual(self.clerk.database.read_bytes(), before)
        self.assertNotIn(B, self.clerk.config()['repositories'], 'receipt recovery does not newly enroll under changed pins')
        # This fallback is not a terminal presentation: restoring the original
        # runtime can finish its exact request without losing the known effect.
        completed = restarted.summon(*source, **INTERPRETATION)
        self.assertEqual(completed['reply'], native[0])
        self.assertEqual(completed['cards'][0]['view']['object'], 'sessions/session-1')
        self.assertEqual(self.clerk.database.read_bytes(), before)

    def test_lost_reply_uses_original_database_after_clerk_binding_changes(self):
        source = self.post('lost-before-database-change')
        database = self.clerk.database
        exchange = town_summon.world.exchange
        native = []
        def lose(*args, **kwargs):
            native.append(exchange(*args, **kwargs))
            raise OSError('reply lost after native commit')
        with patch.object(town_summon.world, 'exchange', side_effect=lose):
            self.assertEqual(self.summon(source)['status'], 'uncertain')
        self.assertEqual(native[0]['kind'], 'committed')
        before = database.read_bytes()
        configuration = self.clerk.config()
        replacement = self.base / 'another-world.json'
        configuration['database'] = str(replacement.resolve())
        clerk.save(self.clerk.state / 'clerk.json', configuration)
        self.pds.records.clear()
        with patch.object(town_summon.world, 'exchange', side_effect=AssertionError('no replay into another world')), \
                patch.object(town_summon.source_offers, 'prepare', side_effect=AssertionError('no new preparation')):
            recovered = self.summon(source)
        self.assertEqual(recovered['reply'], native[0])
        self.assertEqual(recovered['presentation']['status'], 'unavailable')
        self.assertEqual(database.read_bytes(), before)
        self.assertFalse(replacement.exists())

    def test_uncommitted_attempt_does_not_run_under_changed_runtime(self):
        source = self.post('not-committed')
        with patch.object(town_summon.world, 'exchange', side_effect=OSError('not delivered')):
            self.assertEqual(self.summon(source)['status'], 'uncertain')
        before = self.clerk.database.read_bytes()
        self.pds.records.clear()
        with patch.object(town.clerk, 'pins', return_value={}), \
                patch.object(town_summon.world, 'exchange', side_effect=AssertionError('no new admission')):
            with self.assertRaisesRegex(ValueError, 'pins changed'):
                self.summon(source)
        self.assertEqual(self.clerk.database.read_bytes(), before)
        self.assertNotIn('sessions/session-1', world.snapshot(self.clerk.database)['objects'])

    def test_lost_membership_reply_changed_runtime_recovers_both_receipts(self):
        self.prepare_membership()
        source = self.post('lost-member-runtime-change')
        exchange = town_summon.world.exchange
        native = []
        def lose(database, request, **kwargs):
            reply = exchange(database, request, **kwargs)
            if request['intent'].endswith(':followup'):
                native.append(reply)
                raise OSError('membership reply lost after admission')
            return reply
        with patch.object(town_summon.world, 'exchange', side_effect=lose):
            first = self.summon(source)
        self.assertEqual(first['membership']['status'], 'uncertain')
        before = self.clerk.database.read_bytes()
        self.pds.records.clear()
        with patch.object(town.clerk, 'pins', return_value={}), \
                patch.object(town_summon.world, 'exchange', side_effect=AssertionError('no regrant')), \
                patch.object(town_summon.source_offers, 'prepare', side_effect=AssertionError('no new source call')):
            recovered = self.summon(source)
        self.assertEqual(recovered['reply'], first['reply'])
        self.assertEqual(recovered['membership']['status'], 'committed')
        self.assertEqual(recovered['membership']['receipt'], native[0])
        self.assertEqual(self.clerk.database.read_bytes(), before)

    def test_lost_final_presentation_changed_runtime_returns_recorded_receipts(self):
        self.prepare_membership()
        source = self.post('lost-final-presentation')
        save = town_summon.clerk.save
        def lose(path, value):
            if 'response' in value:
                raise OSError('final presentation save failed')
            return save(path, value)
        with patch.object(town_summon.clerk, 'save', side_effect=lose):
            with self.assertRaisesRegex(OSError, 'presentation'):
                self.summon(source)
        before = self.clerk.database.read_bytes()
        self.pds.records.clear()
        with patch.object(town.clerk, 'pins', return_value={}), \
                patch.object(town_summon.world, 'exchange', side_effect=AssertionError('no new effects')), \
                patch.object(town_summon.source_offers, 'prepare', side_effect=AssertionError('no new preparation')):
            recovered = self.summon(source)
        self.assertEqual(recovered['status'], 'committed')
        self.assertEqual(recovered['membership']['status'], 'committed')
        self.assertEqual(recovered['presentation']['status'], 'unavailable')
        self.assertEqual(self.clerk.database.read_bytes(), before)

    def test_repository_mismatch_and_false_author_quote_never_impersonate(self):
        source = self.post('spoof', text=f'Quoted {A}: @livedelvetalk.delve.town #gsb; principal={A}')
        before = self.clerk.database.read_bytes()
        self.pds.identity = A
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            self.summon(source)
        self.pds.identity = None
        self.pds.answer_cid = 'different'
        with self.assertRaisesRegex(ValueError, 'CID mismatch'):
            self.summon(source)
        self.assertEqual(self.clerk.database.read_bytes(), before)
        self.pds.answer_cid = None
        # Merely retaining/discovering tag text performs no action. Explicit operator
        # interpretation is required and cannot replace the authenticated author.
        with self.assertRaises(TypeError):
            self.service.summon(*source)
        result = self.service.summon(*source, interpreter='operator', basis='B separately requested their own session; quoted A is not authority.')
        child = result['cards'][0]['view']['root']
        self.assertEqual(child['law']['invoke']['choose'], [B])
        self.assertNotIn(A, child['law']['invoke']['choose'])

    def prepare_membership(self, *, create=True, program=None):
        program = self.member_program if program is None else program
        self.assertEqual(self.clerk.snapshot('sessions')['root']['protocol'], program)
        if create:
            counter = clerk.loads((ROOT / 'protocols/counter/protocol.json').read_bytes())
            law = {'profile': 'delvetalk-scoped-law-v4', 'invoke': {'add': []},
                   'reprogram': ['steward'], 'law': ['steward', SERVICE],
                   'amendment': membership.amendment(SERVICE, ['add'])}
            for identity, protocol, law in [('shared', counter, law), ('welcome', self.welcome_program,
                    {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'enroll': [SERVICE]},
                     'reprogram': ['steward'], 'law': ['steward']})]:
                reply = world.exchange(self.clerk.database, {'op': 'create', 'object': identity,
                    'principal': 'steward', 'intent': 'create-' + identity, 'protocol': protocol, 'law': law}, profile='compiled')
                self.assertEqual(reply['kind'], 'committed', reply)

    def test_membership_uses_source_policy_and_retry_never_regrants(self):
        self.prepare_membership()
        source = self.post('member')
        result = self.summon(source)
        self.assertEqual(result['status'], 'committed', result)
        self.assertEqual(result['membership']['status'], 'committed', result)
        root = world.query(self.clerk.database, {'op': 'inspect', 'object': 'shared', 'principal': 'reader'})
        self.assertEqual(root['law']['invoke']['add'], [B])
        revoked = copy.deepcopy(root['law'])
        revoked['invoke']['add'] = []
        reply = world.exchange(self.clerk.database, {'op': 'law', 'object': 'shared',
            'principal': 'steward', 'intent': 'later-revocation', 'expected': root, 'law': revoked}, profile='compiled')
        self.assertEqual(reply['kind'], 'committed', reply)
        before = self.clerk.database.read_bytes()
        self.pds.records.clear()
        self.assertEqual(self.summon(source), result)
        self.assertEqual(self.clerk.database.read_bytes(), before)
        self.assertEqual(world.query(self.clerk.database, {'op': 'inspect', 'object': 'shared',
            'principal': 'reader'})['law']['invoke']['add'], [])
        fresh = self.summon(self.post('fresh-session-after-revocation'))
        self.assertEqual(fresh['status'], 'committed')
        self.assertEqual(fresh['membership']['status'], 'refused')
        self.assertIn(fresh['membership']['preparation']['message'], fresh['body'])
        self.assertEqual(world.query(self.clerk.database, {'op': 'inspect', 'object': 'shared',
            'principal': 'reader'})['law']['invoke']['add'], [])

    def test_lost_membership_reply_recovers_separately_from_created_session(self):
        self.prepare_membership()
        source = self.post('lost-member')
        exchange = town_summon.world.exchange
        def lose(database, request, **kwargs):
            reply = exchange(database, request, **kwargs)
            if request['intent'].endswith(':followup'):
                self.assertEqual(reply['kind'], 'committed', reply)
                raise OSError('membership reply lost after admission')
            return reply
        with patch.object(town_summon.world, 'exchange', side_effect=lose):
            first = self.summon(source)
        self.assertEqual(first['status'], 'committed')
        self.assertEqual(first['membership']['status'], 'uncertain')
        self.pds.records.clear()
        second = self.summon(source)
        self.assertEqual(second['membership']['status'], 'committed')
        self.assertEqual(second['cards'], first['cards'])
        self.assertEqual(second['reply'], first['reply'])
        self.assertNotIn('sessions/session-2', world.snapshot(self.clerk.database)['objects'])

    def test_missing_or_out_of_scope_membership_preserves_real_session(self):
        self.prepare_membership(create=False)
        missing = self.summon(self.post('missing-welcome'))
        self.assertEqual(missing['status'], 'committed')
        self.assertEqual(missing['membership']['status'], 'unavailable')
        self.assertEqual(missing['cards'][0]['view']['object'], 'sessions/session-1')

    def test_source_followup_outside_configured_scope_never_runs(self):
        self.prepare_membership(create=False, program=self.outside_program)
        result = self.summon(self.post('outside-welcome'))
        self.assertEqual(result['status'], 'committed')
        self.assertEqual(result['membership']['status'], 'refused')
        self.assertEqual(result['cards'][0]['view']['object'], 'sessions/session-1')

    def test_current_service_law_can_refuse_without_enrolling_or_allocating(self):
        root = self.clerk.snapshot('sessions')['root']
        revoked = copy.deepcopy(self.law)
        revoked['invoke']['make'] = []
        result = world.exchange(self.clerk.database, {'op': 'law', 'object': 'sessions',
            'principal': 'steward', 'intent': 'revoke-service', 'expected': root, 'law': revoked}, profile='compiled')
        self.assertEqual(result['kind'], 'committed')
        result = self.summon(self.post('denied'))
        self.assertEqual(result['status'], 'refused', result)
        self.assertEqual(result['cards'], [])
        self.assertNotIn(B, self.clerk.config()['repositories'])
        self.assertNotIn('sessions/session-1', self.clerk.config()['objects'])


if __name__ == '__main__':
    unittest.main()
