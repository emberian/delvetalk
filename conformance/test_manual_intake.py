"""Local interpretation custody with GET-only mocks and actual Lean admission."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import town
from conformance import test_town_receiving as fixture


class ManualIntake(unittest.TestCase):
    def setUp(self):
        self.f = fixture.TownReceivingTests('test_current_law_and_stale_root_remain_lean_decisions')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.c = self.f.c

    def decision(self, root=None, amount=3):
        return {'status': 'act', 'interpreter': 'local operator: Ember/Codex',
                'basis': 'The participant asks to add three to the counter shown in the referenced card.',
                'request': {'object': 'counter', 'command': 'add', 'input': {'amount': amount},
                            'expected': self.f.root if root is None else root}}

    def post(self, key='natural', author=fixture.A):
        return self.f.post(key, author=author, text='Could you add three to that counter for me, please?')

    def test_natural_post_retained_separately_from_named_interpretation(self):
        source = self.post()
        original = copy.deepcopy(self.f.pds.records[source[0]][1])
        decision = self.decision()
        receipt = self.c.receive_interpreted(*source, decision)
        self.assertEqual(receipt['reply']['kind'], 'committed')
        self.assertEqual(receipt['reply']['data']['root']['state']['count'], 3)
        self.assertEqual(receipt['request']['principal'], fixture.A)
        self.assertEqual(receipt['request']['intent'], 'delve:' + source[0])
        self.assertEqual(receipt['interpretation']['decision'], decision)
        self.assertEqual(receipt['interpretation']['sourceRecordSha256'], clerk.digest(original))
        journal = clerk.loads(self.f.journal(source[0]).read_bytes())
        self.assertEqual(journal['record'], original)
        self.assertNotIn('delvetalk-request', journal['record']['text'])
        self.assertIn('not an authenticated account', receipt['interpretation']['scope'])
        self.f.pds.records.clear()
        self.assertEqual(self.c.receive_interpreted(*source, decision), receipt)
        self.assertEqual(self.c.receive(*source), receipt)
        changed = copy.deepcopy(decision)
        changed['basis'] += ' Revised.'
        with self.assertRaisesRegex(ValueError, 'different interpretation'):
            self.c.receive_interpreted(*source, changed)

    def test_clarification_and_escalation_never_reserve_semantic_intent(self):
        source = self.post()
        before = self.c.database.read_bytes()
        for status in ('clarify', 'escalate'):
            decision = {'status': status, 'interpreter': 'operator', 'basis': 'Two counters might be intended.',
                        'message': 'Which counter did you mean?'}
            review = self.c.receive_interpreted(*source, decision)
            self.assertEqual(review['status'], status)
            self.assertEqual(review['record']['text'], self.f.pds.records[source[0]][1]['text'])
            self.assertFalse(self.f.journal(source[0]).exists())
        self.assertEqual(self.c.database.read_bytes(), before)
        self.assertEqual(len(list((self.c.state / 'interpretations').glob('*.json'))), 2)
        receipt = self.c.receive_interpreted(*source, self.decision())
        self.assertEqual(receipt['reply']['kind'], 'committed')
        with self.assertRaisesRegex(ValueError, 'different interpretation'):
            self.c.receive_interpreted(*source, decision)

    def test_current_law_stale_root_and_transport_checks_remain_effective(self):
        denied = self.c.receive_interpreted(*self.post('denied', fixture.B), self.decision())
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        receipt = self.c.receive_interpreted(*self.post(), self.decision())
        stale = self.c.receive_interpreted(*self.post('stale'), self.decision())
        self.assertEqual(stale['reply']['data'], 'stale read root')
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)
        forged = self.decision(receipt['reply']['data']['root'])
        forged['request']['principal'] = fixture.A
        source = self.post('forged', fixture.B)
        with self.assertRaisesRegex(ValueError, 'unknown fields'):
            self.c.receive_interpreted(*source, forged)
        self.assertFalse(self.f.journal(source[0]).exists())
        self.f.pds.answer_cid = 'wrong-cid'
        with self.assertRaisesRegex(ValueError, 'CID mismatch'):
            self.c.receive_interpreted(*self.post('wrong-cid'), self.decision())

    def test_law_revision_uses_repository_identity_current_authority_and_exact_retry(self):
        def decision(root):
            return {'status': 'act', 'interpreter': 'local operator',
                'basis': 'The manager requests an explicit law revision.',
                'request': {'op': 'law', 'object': 'counter', 'law': [fixture.A], 'expected': root}}
        denied = self.c.receive_interpreted(*self.post('law-denied', fixture.B), decision(self.f.root))
        self.assertEqual(denied['reply']['data'], 'unauthorized')
        # Terminal refusal adds custody, but never changes the object's authority.
        self.assertEqual(self.c.snapshot('counter')['root'], self.f.root)
        source = self.post('law-authorized')
        chosen = decision(self.f.root)
        accepted = self.c.receive_interpreted(*source, chosen)
        self.assertEqual(accepted['reply']['kind'], 'committed')
        self.assertEqual(accepted['request']['principal'], fixture.A)
        self.assertEqual(accepted['request']['intent'], 'delve:' + source[0])
        self.assertEqual(accepted['reply']['data']['root']['law'], [fixture.A])
        stale = self.c.receive_interpreted(*self.post('law-stale'), decision(self.f.root))
        self.assertEqual(stale['reply']['data'], 'stale read root')
        retained = self.c.database.read_bytes()
        self.f.pds.records.clear()
        self.assertEqual(self.c.receive_interpreted(*source, chosen), accepted)
        self.assertEqual(self.c.database.read_bytes(), retained)

    def test_law_intake_rejects_identity_override_and_malformed_envelope(self):
        request = {'op': 'law', 'object': 'counter', 'law': [fixture.A], 'expected': self.f.root}
        for key, value in [('principal', fixture.A), ('intent', 'manager-chosen'), ('law', 'not-a-law')]:
            changed = {**request, key: value}
            source = self.post('law-forged-' + key, fixture.B)
            decision = {'status': 'act', 'interpreter': 'operator', 'basis': 'A proposed law edit.', 'request': changed}
            with self.assertRaisesRegex(ValueError, 'unknown fields|law must be'):
                self.c.receive_interpreted(*source, decision)
            self.assertFalse(self.f.journal(source[0]).exists())

    def test_machine_and_manual_routes_share_one_source_attempt(self):
        source = self.f.post('machine')
        receipt = self.c.receive(*source)
        with self.assertRaisesRegex(ValueError, 'different interpretation or machine'):
            self.c.receive_interpreted(*source, self.decision())
        self.assertEqual(self.c.receive(*source), receipt)
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)

    def test_pending_interpretation_recovers_without_network_or_rebinding(self):
        source, decision = self.post(), self.decision()
        save = clerk.save
        def die(path, value):
            if 'receipt' in value and 'source' in value:
                raise KeyboardInterrupt('after admission')
            return save(path, value)
        with patch.object(clerk, 'save', die), self.assertRaises(KeyboardInterrupt):
            self.c.receive_interpreted(*source, decision)
        self.assertEqual(self.c.snapshot('counter')['root']['version'], 1)
        changed = copy.deepcopy(decision)
        changed['request']['input']['amount'] = 9
        with self.assertRaisesRegex(ValueError, 'different interpretation'):
            self.c.receive_interpreted(*source, changed)
        self.f.pds.records.clear()
        receipt = self.c.receive_interpreted(*source, decision)
        self.assertEqual(receipt['reply']['data']['root']['version'], 1)
        self.assertEqual(receipt['interpretation']['decision'], decision)

    def test_town_prepares_interpretation_with_current_outcome_and_replays(self):
        operator = town.Town(self.c.state, request=self.f.pds)
        source, decision = self.post(), self.decision()
        response = operator.receive(*source, interpretation=decision)
        self.assertEqual(response['receipt']['reply']['kind'], 'committed')
        self.assertIn('Operator interpretation', response['body'])
        self.assertIn('asks to add three', response['body'])
        self.assertEqual(response['publication'], 'paused')
        self.f.pds.records.clear()
        self.assertEqual(operator.receive(*source, interpretation=decision), response)
        with self.assertRaisesRegex(ValueError, 'different interpretation'):
            operator.receive(*source, interpretation=self.decision(amount=4))

    def test_town_clarification_and_uncertain_outcome_stay_distinct(self):
        operator = town.Town(self.c.state, request=self.f.pds)
        source = self.post()
        review = {'status': 'clarify', 'interpreter': 'operator', 'basis': 'Target is ambiguous.',
                  'message': 'Which counter?'}
        result = operator.receive(*source, interpretation=review)
        self.assertEqual(result['status'], 'clarify')
        self.assertNotIn('receipt', result)
        receive = operator.clerk.receive_interpreted
        def lose(uri, cid, decision):
            receive(uri, cid, decision)
            raise OSError('reply lost')
        with patch.object(operator.clerk, 'receive_interpreted', lose):
            unknown = operator.receive(*source, interpretation=self.decision())
        self.assertEqual(unknown['status'], 'uncertain')
        self.assertNotIn('receipt', unknown)
        self.assertNotIn('Operator interpretation', unknown['body'])
        result = operator.receive(*source, interpretation=self.decision())
        self.assertEqual(result['receipt']['reply']['data']['root']['version'], 1)


if __name__ == '__main__':
    unittest.main()
