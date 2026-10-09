#!/usr/bin/env python3
"""Ordinary work tickets through real Lean, typed cards and retained receipts."""
import concurrent.futures
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'protocols/work-ticket'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


author = module('ticket_author', 'protocols/work-ticket/generate.py')
world = module('ticket_world', 'scripts/world.py')
room = module('ticket_room', 'scene/room.py')
affordances = module('ticket_affordances', 'scripts/affordances.py')
interpret = module('ticket_interpret', 'scripts/interpret.py')


class WorkTicket(unittest.TestCase):
    def setUp(self):
        for executable in ('delvetalk-transactions', 'delvetalk-world'):
            self.assertTrue((ROOT / '.lake/build/bin' / executable).is_file(), 'prebuilt host required')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'world.json'
        self.serial = 0
        self.create('ticket', author.build(), author.law())

    def call(self, request):
        return world.exchange(self.db, request, profile='transactions')

    def create(self, object_id, protocol, law):
        reply = self.call({'op': 'create', 'object': object_id, 'principal': 'operator',
            'intent': 'create-' + object_id, 'protocol': protocol, 'law': law})
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply['data']['root']

    def root(self, object_id='ticket'):
        return self.call({'op': 'inspect', 'object': object_id, 'principal': 'observer'})

    def request(self, who, command, data=None, expected=None):
        self.serial += 1
        return {'op': 'invoke', 'object': 'ticket', 'principal': who,
            'intent': 'turn-' + str(self.serial), 'expected': self.root() if expected is None else expected,
            'command': command, 'input': data or {}}

    def invoke(self, who, command, data=None, kind='committed', expected=None):
        result = self.call(self.request(who, command, data, expected))
        self.assertEqual(result['kind'], kind, result)
        return result

    def posted(self):
        self.invoke('requester', 'post', {'task': 'Inspect the moth wing.', 'author': 'forged'})
        self.assertEqual(self.root()['state']['author'], 'requester')
        return self.root()

    def submitted(self):
        self.posted()
        self.invoke('moss', 'claim', {'claimant': 'iris'})
        self.assertEqual(self.root()['state']['claimant'], 'moss')
        self.invoke('moss', 'submit', {'result': 'The wing is aligned.'})
        return self.root()

    def change_law(self, law):
        self.serial += 1
        reply = self.call({'op': 'law', 'object': 'ticket', 'principal': 'steward',
            'intent': 'law-' + str(self.serial), 'expected': self.root(), 'law': law})
        self.assertEqual(reply['kind'], 'committed', reply)

    def test_generated_sources_and_discovered_scenarios(self):
        for name, expected in [('protocol.json', author.build()), ('migration.json', author.build()['initial']),
                               ('law.json', author.law()), ('scenarios.json', author.scenarios())]:
            self.assertEqual(json.loads((PACKAGE / name).read_text()), expected)
        for index, scenario in enumerate(author.scenarios()):
            self.db = Path(self.temp.name) / ('scenario-' + str(index) + '.json')
            initial = self.create('ticket', author.build(), scenario['law'])
            for step in scenario['steps']:
                expected = initial if step['root'] == 'initial' else self.root()
                self.invoke(step['principal'], step['command'], step['input'], step['kind'], expected)

    def test_two_actual_callers_race_for_one_claim(self):
        root = self.posted()
        requests = [self.request(who, 'claim', expected=root) for who in ('moss', 'iris')]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(self.call, requests))
        self.assertEqual(sorted(r['kind'] for r in replies), ['committed', 'refused'])
        winner = next(request['principal'] for request, reply in zip(requests, replies) if reply['kind'] == 'committed')
        self.assertEqual(self.root()['state']['claimant'], winner)
        loser = 'iris' if winner == 'moss' else 'moss'
        self.invoke(loser, 'submit', {'result': 'Forged claim.'}, 'refused')
        self.assertEqual(self.root()['state']['status'], 'claimed')

    def test_authored_references_are_bounded_data_and_do_not_grant(self):
        reference = {'format': 'delvetalk-object-ref-v1', 'world': 'urn:uuid:fixture',
                     'object': 'room:moth'}
        links = {key: reference for key in ('context', 'about', 'replyTo')}
        self.db = Path(self.temp.name) / 'linked.json'
        root = self.create('ticket', author.build(links=links), author.law())
        self.assertEqual(root['state']['links'], links)
        self.invoke('room:moth', 'post', {'task': 'A link is not a role.'}, 'refused')
        self.posted()
        self.assertEqual(self.root()['state']['links'], links)
        for invalid in ({**reference, 'world': 'x' * 257}, {**reference, 'object': '\ud800'},
                        {**reference, 'object': 'bad\nname'}, {**reference, 'permissions': ['claim']},
                        {**reference, 'format': 'delvetalk-object-ref-v2'}):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(ValueError):
                    author.build(links={'context': invalid})
        with self.assertRaises(ValueError):
            author.build(links={'owner': reference})

    def test_current_law_revocation_and_requester_review(self):
        self.posted()
        self.invoke('moss', 'claim')
        law = author.law()
        law['invoke']['submit'] = ['iris']
        self.change_law(law)
        self.invoke('moss', 'submit', {'result': 'Revoked.'}, 'refused')
        self.invoke('iris', 'submit', {'result': 'Not claimant.'}, 'refused')
        self.change_law(author.law())
        self.invoke('moss', 'submit', {'result': 'Restored.'})
        law = author.law()
        law['invoke']['accept'] = ['iris', 'requester']
        self.change_law(law)
        self.invoke('iris', 'accept', {'review': 'Not requester.'}, 'refused')
        stale = self.root()
        self.invoke('requester', 'reject', {'review': 'Needs another attempt.'})
        self.invoke('requester', 'accept', {'review': 'Old view.'}, 'refused', stale)

    def test_late_call_rollback_and_accept_only_counterexample(self):
        ticket = self.submitted()
        target = self.create('target', {'profile': 'delvetalk-local-v1', 'initial': {'changed': False},
            'commands': {'change': {'require': [[['input', 'allow'], ['literal', True]]],
                'set': {'changed': ['literal', True]}, 'result': ['record', {}], 'outbox': []}}}, ['requester'])
        transaction = {'op': 'transaction', 'principal': 'requester', 'intent': 'atomic-review',
            'reads': {'ticket': ticket, 'target': target}, 'calls': [
                {'object': 'ticket', 'command': 'accept', 'input': {'review': 'Approved.'}},
                {'object': 'target', 'command': 'change', 'input': {'allow': False}}]}
        self.assertEqual(self.call(transaction)['kind'], 'refused')
        self.assertEqual(self.root(), ticket)
        self.assertEqual(self.root('target'), target)
        # Omitting a target call is legal. Acceptance means review, never evidence of that call.
        self.invoke('requester', 'accept', {'review': 'Accepted independently.'})
        self.assertEqual(self.root()['state']['status'], 'accepted')
        self.assertEqual(self.root('target'), target)

    def test_successful_composition(self):
        ticket = self.submitted()
        target = self.create('target', {'profile': 'delvetalk-local-v1', 'initial': {'changed': False},
            'commands': {'change': {'require': [], 'set': {'changed': ['literal', True]},
                                    'result': ['record', {}], 'outbox': []}}}, ['requester'])
        reply = self.call({'op': 'transaction', 'principal': 'requester', 'intent': 'both',
            'reads': {'ticket': ticket, 'target': target}, 'calls': [
                {'object': 'target', 'command': 'change', 'input': {}},
                {'object': 'ticket', 'command': 'accept', 'input': {'review': 'Received.'}}]})
        self.assertEqual(reply['kind'], 'committed', reply)
        self.assertEqual(reply['data']['roots']['ticket']['state']['status'], 'accepted')
        self.assertTrue(reply['data']['roots']['target']['state']['changed'])

    def test_lost_reply_retry_after_revocation_and_collision(self):
        self.submitted()
        request = self.request('requester', 'accept', {'review': 'Received.'})
        receipt = self.call(request)  # Transport loses this reply; retry in a fresh OS process.
        law = author.law()
        law['invoke']['accept'] = []
        self.change_law(law)
        process = subprocess.run([sys.executable, str(ROOT / 'scripts/world.py'), '--profile',
            'transactions', str(self.db), '-'], input=json.dumps(request), text=True,
            capture_output=True, check=True)
        self.assertEqual(json.loads(process.stdout), receipt)
        changed = copy.deepcopy(request)
        changed['input']['review'] = 'Different review.'
        self.assertEqual(self.call(changed)['data'], 'intent reused for different request')
        self.assertEqual(self.root()['state']['review'], 'Received.')

    def test_typed_tokens_preserve_source_and_exact_root(self):
        view = room.inspect_object(self.root(), 'ticket')
        card = affordances.card(view)
        action = card['actions'][0]
        public = {key: card[key] for key in ('object', 'title', 'prose')}
        public.update(card='ticket_card', actions=[{key: value for key, value in action.items()
            if key in ('id', 'label', 'available', 'inspectOnly', 'fields')}])
        token = 'do ticket_card ' + action['id']
        proposal = interpret.interpret(token + ' {"task":"Describe the wing."}', public)
        self.assertEqual(proposal['status'], 'proposed')
        request = affordances.request(view, proposal['action'], 'requester', 'from-token', proposal['fields'])
        self.assertEqual(request['expected'], view['root'])
        self.assertEqual(self.call(request)['kind'], 'committed')
        self.assertEqual(interpret.interpret(token + ' {"task":false}', public)['status'], 'clarify')
        self.assertEqual(interpret.interpret(token + ' ' + json.dumps({'task': 'x' * 2049}), public)['status'], 'clarify')
        stale = affordances.request(view, action['id'], 'requester', 'stale-card', {'task': 'Old view.'})
        self.assertEqual(self.call(stale)['kind'], 'refused')
        # Changing only family metadata cannot impersonate the captured program root.
        forged = copy.deepcopy(request)
        forged['intent'] = 'forged-source'
        forged['expected']['protocol']['description'] = 'Different program metadata'
        self.assertEqual(self.call(forged)['kind'], 'refused')

    def test_phase_cards_show_submission_before_review_and_terminal_review(self):
        def check(phase, prose, commands):
            root = self.root()
            view = room.inspect_object(root, 'ticket')
            card = affordances.card(view)
            self.assertEqual(card['title'], 'Work ticket · ' + phase.capitalize())
            self.assertEqual(card['prose'], prose)
            self.assertEqual([a['command'] for a in card['actions']], commands)
            self.assertEqual(view['root'], root)
            self.assertEqual(self.root(), root, 'projection must not admit an action')
        for terminal in ('accept', 'reject'):
            with self.subTest(terminal=terminal):
                self.db = Path(self.temp.name) / ('view-' + terminal + '.json')
                self.create('ticket', author.build(), author.law())
                check('draft', 'Post a task for another participant.', ['post'])
                self.invoke('requester', 'post', {'task': 'Describe the wing.'})
                check('open', 'Describe the wing.', ['claim'])
                self.invoke('moss', 'claim')
                check('claimed', 'Describe the wing.', ['submit'])
                self.invoke('moss', 'submit', {'result': 'Its upper edge is bent.'})
                check('submitted', 'Its upper edge is bent.', ['accept', 'reject'])
                self.invoke('requester', terminal, {'review': 'I read the submitted description.'})
                check('accepted' if terminal == 'accept' else 'rejected',
                      'I read the submitted description.', [])


if __name__ == '__main__':
    unittest.main()
