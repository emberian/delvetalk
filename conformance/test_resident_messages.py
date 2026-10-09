#!/usr/bin/env python3
"""Real compiled admissions: independent source bell/door and retained messages."""
import copy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'protocols/resident-messages'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


world = module('resident_messages_world', 'scripts/world.py')
bundle = module('resident_messages_bundle', 'syntaxes/source_bundle.py')
history = module('resident_messages_history', 'scripts/history.py')


def source_protocol(name):
    return bundle.load(FIXTURES / (name.lower() + '.binding.json'), [(n, ROOT / 'world/lib/prelude' / (n + '.obend')) for n in ('Abi', 'Encounter')] + [(name, FIXTURES / (name + '.obend'))])


def law(command, actors):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': {command: actors},
            'reprogram': ['builder'], 'law': ['steward']}


class ResidentMessages(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'world.json'
        self.serial = 0

    def call(self, request, kind=None):
        reply = world.exchange(self.db, request, profile='compiled')
        if kind is not None:
            self.assertEqual(reply['kind'], kind, reply)
        return reply

    def intent(self):
        self.serial += 1
        return 'attempt-' + str(self.serial)

    def root(self, name):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def snapshot(self):
        return world.wire_loads(self.db.read_text())

    def setup_world(self, pending=128):
        self.call({'op': 'messages-init', 'principal': 'bootstrap', 'intent': 'init',
                   'lineage': 'courtyard-1', 'pendingLimit': pending}, 'committed')
        self.create('door', source_protocol('Door'), law('hear', ['relay']))
        self.create('bell', source_protocol('Bell'), law('play', ['moss', 'iris']))
        digest = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'hash': {
            'require': [], 'set': {}, 'outbox': [], 'result': ['program-digest', ['input', 'program']]}}}
        self.create('digest', digest, ['reader'])
        self.door_program = self.program_digest(self.root('door')['protocol'])

    def create(self, name, protocol, policy):
        return self.call({'op': 'create', 'principal': 'bootstrap', 'intent': 'create-' + name,
                          'object': name, 'protocol': protocol, 'law': policy}, 'committed')['data']['root']

    def program_digest(self, protocol):
        return self.call({'op': 'invoke', 'principal': 'reader', 'intent': self.intent(),
            'object': 'digest', 'expected': self.root('digest'), 'command': 'hash',
            'input': {'program': protocol}}, 'committed')['data']['result']

    def ring_request(self, voices=1, chord='C E G', principal='moss'):
        return {'op': 'invoke', 'principal': principal, 'intent': self.intent(), 'object': 'bell',
            'expected': self.root('bell'), 'command': 'play',
            'input': {'to': 'door', 'recipientProgram': self.door_program, 'chord': chord, 'voices': voices}}

    def ring(self, **kwargs):
        request = self.ring_request(**kwargs)
        receipt = self.call(request, 'committed')
        return request, receipt, receipt['data'].get('messages', [])

    def delivery(self, reference, **changes):
        return {'op': 'deliver', 'principal': 'relay', 'intent': self.intent(), 'object': 'door',
                'event': reference, 'expected': self.root('door')} | changes

    def policy(self, name, candidate):
        return self.call({'op': 'law', 'object': name, 'principal': 'steward', 'intent': self.intent(),
                          'expected': self.root(name), 'law': candidate}, 'committed')

    def reprogram(self, name, candidate):
        root = self.root(name)
        return self.call({'op': 'reprogram', 'object': name, 'principal': 'builder', 'intent': self.intent(),
            'expected': root, 'protocol': candidate, 'state': root['state']}, 'committed')

    def test_bell_door_joined_and_authentic_evidence(self):
        self.setup_world()
        request, receipt, refs = self.ring(principal='iris')
        self.assertEqual(receipt['data']['outbox'], [])
        event = self.snapshot()['messages']['events'][refs[0]['id']]
        self.assertEqual(event['status'], 'pending')
        evidence = event['evidence']
        self.assertEqual(evidence['sourcePreimage'], request['expected'])
        self.assertEqual(evidence['sourceProgram'], self.program_digest(request['expected']['protocol']))
        self.assertEqual(evidence['admission'], {'principal': 'iris', 'intent': request['intent']})
        self.assertEqual((evidence['call'], evidence['slot']), (0, 0))
        delivery = self.delivery(refs[0])
        done = self.call(delivery, 'committed')
        self.assertEqual(done['data']['result'], {'disposition': 'opened', 'heard': 1})
        state = self.root('door')['state']
        self.assertEqual((state['lastSource'], state['lastPlayer'], state['lastRelay']), ('bell', 'iris', 'relay'))
        self.assertEqual(state['lastEvent'], refs[0]['id'])
        self.assertEqual(self.snapshot()['messages']['pending'], {})
        self.assertEqual(self.call(delivery), done)
        self.call(self.delivery(refs[0]), 'refused')
        self.assertEqual(self.root('door')['state']['heard'], 1)

    def test_forgery_redirect_and_receive_only(self):
        self.setup_world()
        _, _, refs = self.ring()
        before = self.root('door')
        for request in [self.delivery({'lineage': 'courtyard-1', 'id': '0' * 64}),
                self.delivery(refs[0], object='bell'), self.delivery(refs[0], input={'chord': 'C E G'}),
                self.delivery(refs[0], principal='moss'),
                self.delivery(refs[0] | {'lineage': 'other'})]:
            self.call(request, 'refused')
        direct = {'op': 'invoke', 'principal': 'relay', 'intent': self.intent(), 'object': 'door',
                  'expected': before, 'command': 'hear', 'input': {'chord': 'C E G'}}
        self.assertIn('receive-only', self.call(direct, 'refused')['data'])
        direct['intent'] = self.intent()
        direct['eventFacts'] = {'source': 'bell'}
        self.call(direct, 'refused')
        self.assertEqual(self.root('door'), before)
        self.assertEqual(len(self.snapshot()['messages']['pending']), 1)

    def test_current_relay_law_source_revision_and_recipient_program_binding(self):
        self.setup_world()
        _, _, refs = self.ring()
        original = self.snapshot()['messages']['events'][refs[0]['id']]['evidence']
        self.policy('bell', law('play', []))
        revised = source_protocol('Bell') | {'revision': 'new source generation'}
        result = self.reprogram('bell', revised)['data']['result']
        self.assertEqual(result['program'], self.program_digest(revised))
        self.policy('door', law('hear', []))
        denied = self.delivery(refs[0])
        self.call(denied, 'refused')
        self.policy('door', law('hear', ['relay']))
        # A retained refusal remains that exact result even after permission returns.
        self.assertEqual(self.call(denied)['kind'], 'refused')
        accepted = self.delivery(refs[0])
        done = self.call(accepted, 'committed')
        self.assertEqual(self.root('door')['state']['lastProgram'], original['sourceProgram'])
        self.policy('door', law('hear', []))
        self.assertEqual(self.call(accepted), done)
        self.policy('bell', law('play', ['moss']))
        _, _, refs = self.ring()
        changed = source_protocol('Door') | {'revision': 2}
        self.reprogram('door', changed)
        self.assertIn('program changed', self.call(self.delivery(refs[0]), 'refused')['data'])
        self.assertIn(refs[0]['id'], self.snapshot()['messages']['pending'])

    def test_capacity_and_late_batch_refusal_roll_back_source_and_messages(self):
        self.setup_world(pending=2)
        initial = self.root('bell')
        too_many = self.ring_request(voices=3)
        self.assertIn('capacity', self.call(too_many, 'refused')['data'])
        self.assertEqual(self.root('bell'), initial)
        self.assertEqual(self.snapshot()['messages']['events'], {})
        a = self.ring_request(voices=2)
        b = self.ring_request(voices=1)
        batch = {'op': 'transaction', 'principal': 'moss', 'intent': self.intent(),
            'reads': {'bell': initial}, 'calls': [{k: r[k] for k in ('object', 'command', 'input')} for r in (a, b)]}
        self.call(batch, 'refused')
        self.assertEqual(self.root('bell'), initial)
        self.assertEqual(self.snapshot()['messages']['events'], {})
        _, _, refs = self.ring(voices=2)
        self.assertEqual(len(set(r['id'] for r in refs)), 2)
        for ref in refs:
            self.call(self.delivery(ref), 'committed')
        # Consumed evidence never exhausts the pending capacity.
        self.ring(voices=2)
        self.assertEqual(len(self.snapshot()['messages']['events']), 4)

    def test_batch_stamps_intermediate_source_root_and_distinct_call_identity(self):
        self.setup_world()
        initial = self.root('bell')
        item = {k: self.ring_request()[k] for k in ('object', 'command', 'input')}
        changed = source_protocol('Bell') | {'revision': 'after the sound'}
        request = {'op': 'transaction', 'principal': 'builder', 'intent': self.intent(),
            'reads': {'bell': initial}, 'calls': [item, item,
                {'op': 'reprogram', 'object': 'bell', 'protocol': changed, 'state': initial['state']}]}
        self.policy('bell', law('play', ['moss', 'builder']))
        request['reads']['bell'] = self.root('bell')
        receipt = self.call(request, 'committed')
        refs = receipt['data']['messages']
        events = self.snapshot()['messages']['events']
        first, second = [events[r['id']]['evidence'] for r in refs]
        self.assertEqual((first['call'], second['call']), (0, 1))
        self.assertEqual(first['sourcePreimage'], request['reads']['bell'])
        self.assertEqual(second['sourcePreimage']['state']['notes'], 1)
        self.assertEqual(second['sourcePreimage']['version'], first['sourcePreimage']['version'] + 1)
        self.assertEqual(first['sourceProgram'], second['sourceProgram'])
        self.assertNotEqual(first['sourceProgram'], receipt['data']['results'][2]['program'])
        self.call(self.delivery(refs[1]), 'committed')

    def test_refusal_stays_pending_explicit_decline_consumes(self):
        self.setup_world()
        _, _, refs = self.ring(chord='wrong chord')
        before = self.root('door')
        self.assertIn('source refused', self.call(self.delivery(refs[0]), 'refused')['data'])
        self.assertEqual(self.root('door'), before)
        self.assertIn(refs[0]['id'], self.snapshot()['messages']['pending'])
        _, _, declined = self.ring(chord='decline')
        receipt = self.call(self.delivery(declined[0]), 'committed')
        self.assertEqual(receipt['data']['result']['disposition'], 'declined')
        self.assertEqual(self.root('door')['state'], before['state'])
        self.assertNotIn(declined[0]['id'], self.snapshot()['messages']['pending'])

    def test_initialization_is_bootstrap_only_and_exact_digest_preserves_metadata(self):
        self.create('early', source_protocol('Door'), law('hear', ['relay']))
        request = {'op': 'messages-init', 'principal': 'late', 'intent': self.intent(),
                   'lineage': 'late', 'pendingLimit': 128}
        self.assertIn('bootstrap', self.call(request, 'refused')['data'])
        self.db = Path(self.temp.name) / 'second.json'
        self.setup_world()
        request['intent'] = self.intent()
        self.assertIn('already', self.call(request, 'refused')['data'])
        p = source_protocol('Door') | {'metadata': Decimal('1.0')}
        q = source_protocol('Door') | {'metadata': Decimal('1.00')}
        self.assertNotEqual(self.program_digest(p), self.program_digest(q))

    def test_all_disabled_effects_need_no_registry_but_still_validate_every_slot(self):
        self.create('bell', source_protocol('Bell'), law('play', ['moss']))
        self.door_program = '0' * 64  # Well-formed, deliberately no recipient or registry.
        before = self.root('bell')
        accepted = self.call(self.ring_request(voices=0), 'committed')
        self.assertEqual(accepted['data']['outbox'], [])
        self.assertNotIn('messages', accepted['data'])
        self.assertNotIn('messages', self.snapshot())
        current = self.root('bell')
        self.assertEqual(current['state']['notes'], before['state']['notes'] + 1)
        self.assertEqual(current['version'], before['version'] + 1)
        malformed = self.ring_request(voices=0)
        malformed['input']['recipientProgram'] = 'not-a-program-digest'
        self.assertIn('SHA256', self.call(malformed, 'refused')['data'])
        self.assertEqual(self.root('bell'), current)
        # Turning on one valid slot requires initialized delivery custody again.
        self.assertIn('messages', self.call(self.ring_request(voices=1), 'refused')['data'])
        self.assertEqual(self.root('bell'), current)
        self.assertNotIn('messages', self.snapshot())

    def test_per_recipient_capacity_disabled_validation_and_read_queries(self):
        self.setup_world()
        invalid = self.ring_request(voices=0)
        invalid['input']['recipientProgram'] = 'forged'
        before = self.root('bell')
        self.call(invalid, 'refused')
        self.assertEqual(self.root('bell'), before)
        for _ in range(8):
            self.ring(voices=4)
        before = self.root('bell')
        self.assertIn('emitter or recipient', self.call(self.ring_request(), 'refused')['data'])
        self.assertEqual(self.root('bell'), before)
        receipts = len(self.snapshot()['receipts'])
        pending = self.call({'op': 'messages-pending', 'principal': 'reader'})
        self.assertEqual(len(pending['pending']), 32)
        event_id = next(iter(pending['pending']))
        reference = {'lineage': pending['lineage'], 'id': event_id}
        event = self.call({'op': 'message-event', 'principal': 'reader', 'event': reference})
        self.assertEqual(event['event'], self.snapshot()['messages']['events'][event_id])
        self.assertEqual(event['root'], self.root('door'))
        self.assertEqual(len(self.snapshot()['receipts']), receipts)

    def test_actual_source_desk_adopts_typed_bell_and_door_then_delivers(self):
        desk_module = module('resident_messages_desk', 'scripts/desk.py')
        translate = module('resident_messages_translate', 'scripts/translate.py')
        self.setup_world()
        worker = desk_module.Desk(self.db, Path(self.temp.name) / 'artifacts', profile='compiled')
        for name in ('Door', 'Bell'):
            identity = name.lower()
            candidate = identity + '-source'
            store = module('resident_messages_store', 'scripts/source_store.py')
            paths = [(n, ROOT / 'world/lib/prelude' / (n + '.obend')) for n in ('Abi', 'Encounter')] + [(name, FIXTURES / (name + '.obend'))]
            entries = [{'name': n, 'sourceRef': store.store_bytes(worker.artifact_store, p.read_bytes(), kind='source')} for n, p in paths]
            manifest = store.seal_modules(entries)
            material = store.resolve_modules(worker.artifact_store, manifest)
            authored = translate.translate_modules('objective-bend-spell@3', material)['lowered']
            proposal = store.prepare_module_proposal(worker.artifact_store, manifest,
                (FIXTURES / (identity + '.scenarios.json')).read_bytes(), syntax='objective-bend-spell@3')
            root = worker.create(candidate, 'builder', 'create-' + candidate, ['builder'])['data']['root']
            pending = worker.submit_refs(candidate, 'builder', 'submit-' + candidate, root,
                proposal, authored['initial'], identity)['data']['root']
            checked = worker.check(candidate, 'builder', 'check-' + candidate, pending)
            self.assertEqual(checked['kind'], 'committed', checked)
            ready = checked['data']['root']
            self.assertEqual(ready['state']['status'], 'ready', ready['state'].get('diagnostics'))
            current = self.root(identity)
            adopted = worker.adopt(candidate, identity, 'builder', 'adopt-' + candidate, ready, current)
            self.assertEqual(adopted['kind'], 'committed', adopted)
            self.assertEqual(self.root(identity)['protocol'], authored)
            self.assertEqual(set(self.root(identity)['state']), {'model'})
        self.door_program = self.program_digest(self.root('door')['protocol'])
        _, sent, references = self.ring(principal='iris')
        self.assertEqual(sent['data']['result']['playedBy'], 'iris')
        heard = self.call(self.delivery(references[0]), 'committed')
        self.assertEqual(heard['data']['result'], {'disposition': 'opened', 'heard': 1})
        self.assertEqual(set(heard['data']['root']['state']), {'model'})
        self.assertEqual(self.snapshot()['messages']['events'][references[0]['id']]['status'], 'consumed')

    def test_killed_reply_recovery_and_export_restore(self):
        self.setup_world()
        _, _, refs = self.ring()
        request = self.delivery(refs[0])
        request_file = Path(self.temp.name) / 'request.json'
        request_file.write_text(json.dumps(request))
        # Kill custody process after atomic replacement, before it returns a reply.
        script = '''import importlib.util,json,os,signal,sys
spec=importlib.util.spec_from_file_location("custody",sys.argv[1]);w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
replace=w.os.replace
def committed(a,b):
 replace(a,b)
 os.kill(os.getpid(),signal.SIGKILL)
w.os.replace=committed
w.exchange(sys.argv[2],json.load(open(sys.argv[3])),profile="compiled")
'''
        child = subprocess.run([sys.executable, '-c', script, str(ROOT / 'scripts/world.py'),
                                str(self.db), str(request_file)], capture_output=True)
        self.assertEqual(child.returncode, -9, child.stderr)
        done = self.call(request, 'committed')
        self.assertEqual(self.root('door')['state']['heard'], 1)
        self.assertEqual(self.call(request), done)
        _, _, pending = self.ring(principal='iris')
        exported = Path(self.temp.name) / 'history'
        manifest = history.export_history(self.db, exported, profile='compiled', inline_reprogram=True)
        restored = Path(self.temp.name) / 'restored.json'
        history.verify_history(exported, expected_genesis=manifest['genesis'], expected_head=manifest['head'], output=restored)
        before = self.snapshot()
        self.db = restored
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.call(request), done)
        self.call(self.delivery(refs[0]), 'refused')
        self.call(self.delivery(pending[0]), 'committed')
        self.assertEqual(self.root('door')['state']['heard'], 2)


if __name__ == '__main__':
    unittest.main()
