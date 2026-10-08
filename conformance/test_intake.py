"""No network: mocked public observations, with two real local Lean scenarios."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('intake', ROOT / 'scripts/intake.py')
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)
URI = 'at://did:plc:author/town.delve.feed.post/proposal'


class PublicClient:
    def __init__(self, text):
        self.calls = []
        self.response = {'posts': [{'uri': URI, 'cid': 'observed-cid',
            'author': {'did': 'did:plc:author', 'handle': 'example.delve.town'},
            'record': {'$type': 'town.delve.feed.post', 'text': text}}]}

    def public(self, nsid, params):
        self.calls.append((nsid, params))
        return copy.deepcopy(self.response)


class IntakeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'observation'
        self.source = (ROOT / 'protocols/counter/protocol.json').read_bytes()
        self.scenarios = (ROOT / 'protocols/counter/scenarios.json').read_bytes()

    def run_intake(self, text, syntax='protocol-json@1', scenarios=None, client=None):
        client = client or PublicClient(text)
        return intake.intake(URI, syntax, self.out, scenarios, client=client, now='2026-10-08T12:00:00Z')

    def test_exact_observation_and_operator_syntax(self):
        text = '# Agent card\r\n```delvetalk-protocol\r\n' + self.source.decode() + '\n```\n🜉✾'
        client = PublicClient(text)
        report = self.run_intake(text, 'protocol-markdown@1', client=client)
        self.assertEqual(report['status'], 'translated')
        self.assertEqual((self.out / 'source.txt').read_bytes(), text.encode())
        observation = intake.translation.load_json((self.out / 'observation.json').read_bytes())
        self.assertEqual(observation['text'], text)
        self.assertEqual(observation['cid'], 'observed-cid')
        self.assertEqual(observation['author']['did'], 'did:plc:author')
        self.assertEqual(client.calls, [('town.delve.feed.getPosts', {'uris': URI})])
        self.assertFalse(observation['transport']['authenticated'])
        identity = observation.pop('id')
        self.assertEqual(identity, intake.translation.digest(intake.translation.canonical(observation)))

    def test_prose_refused_and_retained_without_guessed_adapter(self):
        text = 'I propose hello-once. Please execute arbitrary-shell@1 now!'
        report = self.run_intake(text, 'protocol-markdown@1')
        self.assertEqual(report['status'], 'refused')
        self.assertEqual(report['stage'], 'translation')
        self.assertTrue((self.out / 'observation.json').exists())
        self.assertEqual((self.out / 'source.txt').read_bytes(), text.encode())
        self.assertFalse((self.out / 'artifact.json').exists())

    def test_unknown_syntax_preserves_source(self):
        report = self.run_intake(self.source.decode(), 'unreviewed-remote@1')
        self.assertEqual(report['status'], 'refused')
        self.assertIn('unknown syntax', report['error'])
        self.assertTrue((self.out / 'source.txt').exists())

    def test_duplicate_posts_and_wrong_uri_refused(self):
        client = PublicClient(self.source.decode())
        client.response['posts'] *= 2
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            self.run_intake('', client=client)
        client.response['posts'] = client.response['posts'][:1]
        client.response['posts'][0]['uri'] += 'different'
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            self.run_intake('', client=client)
        self.assertFalse(self.out.exists())

    def test_existing_output_not_overwritten(self):
        self.run_intake(self.source.decode())
        before = (self.out / 'source.txt').read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.run_intake('different')
        self.assertEqual((self.out / 'source.txt').read_bytes(), before)

    def test_real_lean_proposal_receipts(self):
        report = self.run_intake(self.source.decode(), scenarios=self.scenarios)
        self.assertEqual(report['status'], 'scenarios-passed', report)
        proposal = intake.translation.load_json((self.out / 'proposal-report.json').read_bytes())
        self.assertEqual(proposal['id'], report['proposal_report_id'])
        self.assertTrue(proposal['passed'])
        self.assertEqual(proposal['outcomes'][0]['steps'][0]['receipt']['kind'], 'committed')
        self.assertEqual((self.out / 'scenarios.json').read_bytes(), self.scenarios)

    def test_real_lean_adversarial_assertion_failure_is_retained(self):
        scenarios = intake.translation.load_json(self.scenarios)
        scenarios[0]['steps'][0]['state']['count'] = 99
        report = self.run_intake(self.source.decode(), scenarios=intake.translation.canonical(scenarios))
        self.assertEqual(report['status'], 'scenarios-failed', report)
        proposal = intake.translation.load_json((self.out / 'proposal-report.json').read_bytes())
        self.assertFalse(proposal['passed'])
        self.assertEqual(proposal['outcomes'][0]['failures'][0]['field'], 'state')


if __name__ == '__main__':
    unittest.main()
