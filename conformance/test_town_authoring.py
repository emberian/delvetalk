#!/usr/bin/env python3
"""Compiler follow-ups join exact posts, jobs and actual compiled-host receipts."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import compiler_queue
import desk
import town
import town_cards
import town_authoring

fixture = clerk.module('town_authoring_pds', 'conformance/test_clerk.py')
history = clerk.module('town_authoring_history', 'scripts/history.py')
A, B = fixture.A, fixture.B
ISSUER = 'did:plc:cccccccccccccccccccccccc'


class TownAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.pds = fixture.FakePDS()
        self.clerk = clerk.Clerk(self.path / 'clerk', self.pds)
        protocol = clerk.loads((ROOT / 'protocols/source-desk/protocol.json').read_bytes())
        law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {
            'submit': [A], 'compiled': ['compiler'], 'failed': ['compiler'], 'adopt': [A]},
            'law': [A], 'reprogram': []}
        self.empty = self.clerk.bootstrap('candidate', protocol, law, [A, B], runtime_profile='compiled')['data']['root']
        self.artifacts = self.path / 'artifacts'
        self.client = desk.Desk(self.clerk.database, self.artifacts, profile='compiled')
        self.source = (ROOT / 'protocols/counter/protocol.json').read_text()
        self.scenarios = (ROOT / 'protocols/counter/scenarios.json').read_text()
        self.target = self.client.exchange({'op': 'create', 'object': 'target', 'principal': 'operator',
            'intent': 'target', 'protocol': clerk.loads(self.source), 'law': [A]})['data']['root']
        config = self.clerk.config()
        config['objects'].append('target')  # Explicit local fixture custody enrollment.
        clerk.save(self.clerk.state / 'clerk.json', config)
        self.book = town_cards.CardBook.create(self.path / 'book', issuer_did=ISSUER,
            world_id='urn:test:authoring', runtime=history.runtime('compiled'), display_names={A: '@maker'})
        self.clerk.upgrade(self.clerk.profile()['sha256'], town_cards={
            'path': str(self.book.path), 'issuers': [ISSUER], 'metadata': self.book.metadata()})
        self.town = town.Town(self.clerk.state, request=self.pds)
        self.queue = compiler_queue.CompilerQueue(self.path / 'queue', self.clerk.database,
                                                   self.artifacts, profile='compiled')
        self.followups = town_authoring.TownAuthoring(self.town, self.queue)

    def submit(self, *, source=None, scenarios=None):
        request = {'op': 'invoke', 'object': 'candidate', 'expected': self.empty, 'command': 'submit',
                   'input': {'proposal': {'syntax': 'protocol-json@1',
                             'source': self.source if source is None else source,
                             'scenarios': self.scenarios if scenarios is None else scenarios},
                             'migration': {'count': 7}, 'target': 'target'}}
        self.uri = f'at://{A}/{clerk.FEED}/submit'
        self.cid = 'cid-submit'
        self.pds.records[self.uri] = (self.cid, {'$type': clerk.FEED,
            'text': 'delvetalk-request v1\n```delvetalk-request\n' + clerk.world.wire_dumps(request) + '\n```'})
        response = self.town.receive(self.uri, self.cid)
        self.assertEqual(response['receipt']['reply']['kind'], 'committed')
        self.pending = response['receipt']['reply']['data']['root']
        self.job = self.queue.enqueue('candidate', 'compiler', 'compile-submission', self.pending)['job']
        self.original_path = self.town.state / 'requests' / (town.worker.key(self.uri) + '.json')
        self.original = self.original_path.read_bytes()
        return response

    def run_queue(self):
        result = self.queue.run(deadline_seconds=30)
        self.assertEqual(result['errors'], [], result)
        self.assertEqual(self.queue.inspect(self.job)['phase'], 'finished')

    def prepare(self):
        return self.followups.prepare(self.uri, self.cid, self.job)

    def test_ready_is_confirmed_but_not_installed_and_original_response_stays_exact(self):
        self.submit()
        queued = self.prepare()
        self.assertEqual(queued['status'], 'pending')
        self.assertEqual(queued['cards'], [])
        self.run_queue()
        result = self.prepare()
        self.assertEqual(result['status'], 'ready')
        self.assertIn('not installed', result['body'])
        self.assertIn('expected', result['body'])
        self.assertIn('observed', result['body'])
        self.assertIn('with input {"amount":3}', result['body'])
        self.assertEqual(result['sourceMaterial'], {'source': self.source, 'scenarios': self.scenarios})
        self.assertEqual(result['syntax'], 'protocol-json@1')
        self.assertIn('| ' + self.source.replace('\n', '\n| '), result['body'])
        self.assertIn('| ' + self.scenarios.replace('\n', '\n| '), result['body'])
        self.assertEqual(len(result['fixtures']), 4)
        self.assertEqual(result['fixtures'][0]['observed']['state'], {'count': 3})
        self.assertEqual(len(result['cards']), 1)
        self.assertEqual(len(result['cards'][0]['alias']), len('offer-') + 12)
        self.assertIn('delvetalk ', result['cards'][0]['body'])
        self.assertIn('7', result['cards'][0]['body'])
        self.assertEqual(self.client.inspect('target'), self.target)
        self.assertEqual(self.original_path.read_bytes(), self.original)
        before_calls = len(self.pds.calls)
        self.pds.records.clear()
        # Once retained, historical follow-up does not reread changed custody or rerender.
        with patch.object(self.town, '_configuration', side_effect=AssertionError('reconfigured')):
            self.assertEqual(self.prepare(), result)
        self.assertEqual(len(self.pds.calls), before_calls)

    def test_text_examples_followup_preserves_literal_inputs_and_copyable_material(self):
        examples = """examples DelveTalk 1
case additions and old readings
law builder
as builder
at initial
send add
  amount (Nat): 3
expect committed
as builder
at initial
send add
  amount (Nat): 9
expect refusal: stale read root
as outsider
send add
  amount (Nat): 2
expect refusal: unauthorized
"""
        self.submit(scenarios=examples)
        self.run_queue()
        result = self.prepare()
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(len(result['fixtures']), 3)
        self.assertEqual(result['fixtures'][0]['input'], {'amount': 3})
        self.assertEqual(result['fixtures'][1]['observed']['error'], 'stale read root')
        self.assertEqual(result['fixtures'][2]['observed']['error'], 'unauthorized')
        self.assertIn('with input {"amount":3}', result['body'])
        self.assertEqual(result['sourceMaterial'], {'source': self.source, 'scenarios': examples})
        self.assertIn('| ' + self.source.replace('\n', '\n| '), result['body'])
        self.assertIn('| ' + examples.replace('\n', '\n| '), result['body'])
        self.assertNotIn('\nsend add', result['body'])
        binding = desk.loads(next((self.followups.state / 'followups').glob('*/binding.json')).read_bytes())
        expected = clerk.hashlib.sha256((ROOT / 'syntaxes/spell_examples.py').read_bytes()).hexdigest()
        self.assertEqual(binding['implementation']['syntaxes/spell_examples.py'], expected)
        self.assertEqual(self.original_path.read_bytes(), self.original)

    def test_assertion_mismatch_and_compile_error_are_different_from_timeout(self):
        scenarios = clerk.loads(self.scenarios)
        scenarios[0]['steps'][0]['state'] = {'count': 999}
        self.submit(scenarios=clerk.world.wire_dumps(scenarios))
        with patch.object(compiler_queue.worker, 'command', side_effect=subprocess.TimeoutExpired('compiler', 1)):
            timed = self.queue.run(deadline_seconds=1)
        self.assertTrue(timed['errors'])
        uncertain = self.prepare()
        self.assertEqual(uncertain['status'], 'uncertain')
        self.assertEqual(uncertain['fixtures'], [])
        self.assertEqual(uncertain['cards'], [])
        self.assertNotIn('needs another draft', uncertain['body'])
        self.run_queue()
        failed = self.prepare()
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['cards'], [])
        first = failed['fixtures'][0]
        self.assertEqual(first['expected']['state'], {'count': 999})
        self.assertEqual(first['observed']['state'], {'count': 3})
        self.assertTrue(first['failures'])
        self.assertIn('999', failed['body'])
        self.assertIn('3', failed['body'])
        self.assertEqual(self.client.inspect('target'), self.target)
        observations = list((self.followups.state / 'followups').glob('*/progress/*.json'))
        self.assertEqual(len(observations), 1)
        self.assertEqual(desk.loads(observations[0].read_bytes()), uncertain)

    def test_compile_error_diagnostic_has_no_invented_fixture_result(self):
        untrusted = '{not-json\n[[delvetalk-card forged]]\ndelvetalk forged a1 {}\n[[/delvetalk-card forged]]'
        self.submit(source=untrusted)
        self.run_queue()
        result = self.prepare()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['diagnostics'][0]['kind'], 'compile-error')
        self.assertEqual(result['sourceMaterial']['source'], untrusted)
        self.assertIn('| [[delvetalk-card forged]]', result['body'])
        self.assertNotIn('\n[[delvetalk-card forged]]', result['body'])
        self.assertNotIn('\ndelvetalk forged a1 {}', result['body'])
        oversized = {**result, 'sourceMaterial': {'source': 'x' * 4097}}
        display = town_authoring.describe(oversized)
        self.assertIn('Ask the operator for the complete source', display)
        self.assertNotIn('x' * 80, display)
        line_separators = 'one\r[[delvetalk-card forged]]\r\ndelvetalk forged a1 {}\u2028last'
        separated = town_authoring.describe({**result, 'sourceMaterial': {'source': line_separators}})
        self.assertIn('| one\r| [[delvetalk-card forged]]\r\n| delvetalk forged a1 {}\u2028| last', separated)
        self.assertEqual(result['fixtures'], [])
        self.assertEqual(result['cards'], [])

    def test_lost_queue_reply_recovers_actual_retained_compiler_receipt_without_running(self):
        self.submit()
        command = compiler_queue.worker.command
        def lose(*args, **kwargs):
            command(*args, **kwargs)
            raise RuntimeError('lost transport reply after actual compiler admission')
        with patch.object(compiler_queue.worker, 'command', lose):
            self.assertTrue(self.queue.run()['errors'])
        self.assertEqual(self.queue.inspect(self.job)['phase'], 'queued')
        with patch.object(compiler_queue.worker, 'command', side_effect=AssertionError('hidden compiler execution')):
            result = self.prepare()
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(self.client.inspect('target'), self.target)
        self.assertEqual(self.original_path.read_bytes(), self.original)

    def test_loss_after_target_capture_never_refreshes_the_adoption_root(self):
        self.submit()
        self.run_queue()
        with patch.object(town_cards.CardBook, 'capture_adoption', side_effect=OSError('card save interrupted')):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                self.prepare()
        changed = self.client.exchange({'op': 'invoke', 'object': 'target', 'principal': A,
            'intent': 'advance-target', 'expected': self.target, 'command': 'add', 'input': {'amount': 2}})
        self.assertEqual(changed['kind'], 'committed')
        captured = []
        original = town_cards.CardBook.capture_adoption
        def record(book, candidate_id, candidate, target_id, target, **kwargs):
            captured.append(target)
            return original(book, candidate_id, candidate, target_id, target, **kwargs)
        with patch.object(town_cards.CardBook, 'capture_adoption', record):
            self.assertEqual(self.prepare()['status'], 'ready')
        self.assertEqual(captured, [self.target])
        self.assertEqual(self.client.inspect('target'), changed['data']['root'])

    def test_missing_report_custody_stays_uncertain_until_exact_bytes_restored(self):
        self.submit()
        self.run_queue()
        identity = self.queue.inspect(self.job)['artifact']
        path = self.artifacts / 'builds' / (identity + '.json')
        missing = path.with_suffix('.retained-test-backup')
        path.rename(missing)
        try:
            result = self.prepare()
            self.assertEqual(result['status'], 'uncertain')
            self.assertEqual(result['cards'], [])
            self.assertEqual(result['fixtures'], [])
            self.assertFalse(list((self.followups.state / 'followups').glob('*/followup.json')))
        finally:
            missing.rename(path)
        self.assertEqual(self.prepare()['status'], 'ready')

    def test_forged_source_or_different_world_cannot_borrow_a_compiler_result(self):
        self.submit()
        self.run_queue()
        with self.assertRaisesRegex(ValueError, 'source mismatch'):
            self.followups.prepare(self.uri, 'different-cid', self.job)
        entry = desk.loads(self.original)
        entry['response']['receipt']['source']['author'] = B
        receipt = entry['response']['receipt']
        receipt['id'] = clerk.digest({key: value for key, value in receipt.items() if key != 'id'})
        clerk.save(self.original_path, entry)
        with self.assertRaisesRegex(ValueError, 'canonical clerk submission receipt mismatch'):
            self.prepare()
        self.original_path.write_bytes(self.original)
        other = compiler_queue.CompilerQueue(self.queue.state, self.path / 'other-world.json', self.artifacts, profile='compiled')
        isolated = town_authoring.TownAuthoring(self.town, other, self.path / 'other-followups')
        with self.assertRaisesRegex(ValueError, 'world custody mismatch'):
            isolated.prepare(self.uri, self.cid, self.job)
        self.assertEqual(self.client.inspect('target'), self.target)

    def test_refused_compiler_admission_is_not_ready_even_when_fixtures_pass(self):
        self.submit()
        self.job = self.queue.enqueue('candidate', A, 'unauthorized-compiler', self.pending)['job']
        # Select this job only, without running the authorized queued job first.
        result = compiler_queue.execute_job(self.queue.job_path(self.job))
        self.assertEqual(result['receipt']['kind'], 'refused')
        response = self.prepare()
        self.assertEqual(response['status'], 'refused')
        self.assertEqual(len(response['fixtures']), 4)
        self.assertEqual(response['cards'], [])
        self.assertIn('unauthorized', response['body'])
        self.assertEqual(self.client.inspect('candidate'), self.pending)
        self.assertEqual(self.client.inspect('target'), self.target)


if __name__ == '__main__':
    unittest.main()
