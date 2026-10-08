#!/usr/bin/env python3
"""One integrated two-agent workshop through actual Lean host processes."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'examples/shared-workshop/run.py'
spec = importlib.util.spec_from_file_location('shared_workshop', ENTRY)
workshop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workshop)


class SharedWorkshop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        cls.report = workshop.run_workshop(cls.directory)
        cls.events = {event['label']: event for event in cls.report['events']}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def event(self, label):
        return self.events[label]

    def test_real_typed_function_is_used_for_offer_and_assignment(self):
        typed = self.report['typed']
        nat = {'tag': 'natural'}
        arrow = lambda a, b: {'tag': 'arrow', 'domain': a, 'codomain': b,
                              'parameter': 'unrestricted', 'reuse': 'reusable'}
        self.assertEqual(typed['receipt']['status'], 'accepted')
        self.assertEqual(typed['receipt']['type'], arrow(nat, arrow(nat, nat)))
        self.assertEqual(typed['receipt']['uses'], [])
        task = self.report['final'][workshop.TASK]
        offer = self.report['final'][workshop.OFFER]
        self.assertEqual(task['state']['quote'], 42)
        self.assertEqual(offer['state']['total'], 42)
        self.assertEqual(task['state']['worker'], 'moss')
        self.assertEqual(offer['state']['status'], 'accepted')
        accepted = self.event('Iris accepts the offer and assigns the task atomically')
        self.assertEqual(accepted['request']['calls'][1]['inputFrom'], 0)
        self.assertEqual(set(accepted['receipt']['data']['roots']), {workshop.TASK, workshop.OFFER})

    def test_late_failure_rolls_back_task_slots_and_outboxes(self):
        failed = self.event('Moss catches a misrouted answer with atomic rollback')
        self.assertEqual(failed['receipt']['kind'], 'refused')
        self.assertEqual(failed['receipt']['data'], 'precondition failed')
        self.assertEqual(self.report['before_completion'], self.report['after_rollback'])
        self.assertEqual(self.report['after_rollback'][workshop.TASK]['state']['phase'], 'assigned')
        for slot in workshop.SLOTS:
            self.assertIsNone(self.report['after_rollback'][slot]['state']['answer'])
            self.assertEqual(self.report['after_rollback'][slot]['version'], 0)

    def test_competing_completion_is_one_atomic_answer(self):
        candidates = [self.event(actor + ' competes to complete') for actor in workshop.LAW]
        self.assertEqual(sorted(e['receipt']['kind'] for e in candidates), ['committed', 'refused'])
        winner = next(e for e in candidates if e['receipt']['kind'] == 'committed')
        loser = next(e for e in candidates if e['receipt']['kind'] == 'refused')
        self.assertEqual(loser['receipt']['data'], 'stale read root')
        self.assertEqual(winner['request']['reads'], loser['request']['reads'])
        payload = {'task': workshop.TASK, 'answer': 42, 'by': winner['request']['principal']}
        self.assertEqual(winner['receipt']['data']['results'], [payload] * 3)
        self.assertEqual(winner['receipt']['data']['outbox'], [
            {'object': slot, 'step': index + 1,
             'payload': {'event': 'answer-ready', **payload}}
            for index, slot in enumerate(workshop.SLOTS)])
        for slot in workshop.SLOTS:
            self.assertEqual(self.report['completed'][slot]['state']['answer'], payload)
            self.assertEqual(self.report['completed'][slot]['version'], 1)
        duplicate = self.event('Fresh reference to the same answer slot cannot publish twice')
        self.assertEqual(duplicate['receipt']['data'], 'precondition failed')

    def test_replay_preserves_success_and_refusal_without_new_outbox(self):
        events = self.report['events']
        winner = next(e for e in events if e['label'].endswith('competes to complete')
                      and e['receipt']['kind'] == 'committed')
        loser = next(e for e in events if e['label'].endswith('competes to complete')
                     and e['receipt']['kind'] == 'refused')
        self.assertEqual(self.event('Exact successful completion retry')['receipt'], winner['receipt'])
        self.assertEqual(self.event('Exact losing completion retry')['receipt'], loser['receipt'])
        self.assertEqual(self.event('Historical completion retry survives lockout')['receipt'], winner['receipt'])
        stored = workshop.world.wire_loads((self.directory / 'world.json').read_text())
        for original in [winner, loser]:
            matches = [r for r in stored['receipts'] if r['request'] == original['request']]
            self.assertEqual(len(matches), 1)
        changed = copy.deepcopy(winner['request'])
        changed['calls'][0]['input']['answer'] = 99
        reply = workshop.world.exchange(self.directory / 'world.json', changed, profile='transactions')
        self.assertEqual(reply['data'], 'intent reused for different request')

    def test_versioned_proposal_installation_and_other_agent_use(self):
        evidence = workshop.world.wire_loads((self.directory / 'proposal-report.json').read_text())
        self.assertTrue(evidence['passed'])
        artifact = evidence['candidate']['artifact']
        self.assertEqual(artifact['source']['text'], (ENTRY.parent / 'task-v2.md').read_text())
        self.assertEqual(self.report['installed']['protocol'], artifact['lowered'])
        self.assertEqual(self.report['installed']['version'], self.report['pre_upgrade']['version'] + 1)
        self.assertEqual(self.report['installed']['law'], self.report['pre_upgrade']['law'])
        self.assertEqual(self.report['installed']['state'],
                         {**self.report['pre_upgrade']['state'], 'retrospective': None})
        unauthorized = self.event('Proposal evidence gives Eve no authority')
        self.assertEqual(unauthorized['receipt']['data'], 'unauthorized')
        stale = self.event('Moss concurrent protocol edit uses stale root')
        self.assertEqual(stale['receipt']['data'], 'stale read root')
        installed = self.event('Iris installs Moss proposal with explicit state migration')
        used = self.event('Moss uses the newly installed action')
        self.assertNotEqual(installed['request']['principal'], used['request']['principal'])
        self.assertEqual(used['request']['command'], 'reflect')
        self.assertEqual(self.report['final'][workshop.TASK]['state']['retrospective'],
                         'Pre-cut the boards before assembly.')

    def test_lockout_survives_reprogram_and_historical_retry(self):
        task = self.report['final'][workshop.TASK]
        self.assertEqual(task['law'], [])
        rescue = self.event('Former authority cannot reprogram through lockout')
        self.assertEqual(rescue['receipt']['data'], 'unauthorized')
        installed = self.event('Iris installs Moss proposal with explicit state migration')
        replayed = self.event('Historical installation retry survives lockout')
        self.assertEqual(replayed['receipt'], installed['receipt'])
        self.assertGreater(task['version'], installed['receipt']['data']['root']['version'])
        current = workshop.world.exchange(self.directory / 'world.json',
            {'op': 'inspect', 'object': workshop.TASK, 'principal': 'reader'}, profile='transactions')
        self.assertEqual(current, task)

    def test_cli_retains_reviewable_artifacts_and_refuses_overwrite(self):
        output = self.directory / 'cli-run'
        command = [sys.executable, str(ENTRY), '--output', str(output)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary['answer'], 42)
        self.assertEqual(summary['protocol_edition'], 2)
        self.assertEqual(summary['final_law'], [])
        before = (output / 'world.json').read_bytes()
        repeat = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(repeat.returncode, 0)
        self.assertEqual((output / 'world.json').read_bytes(), before)
        self.assertTrue((output / 'proposal-report.json').is_file())
        self.assertTrue((output / 'report.json').is_file())


if __name__ == '__main__':
    unittest.main()
