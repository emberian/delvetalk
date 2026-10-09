"""Actual native emissions and receiving; only lost transport replies are simulated."""
import copy
import fcntl
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import message_relay as relay

sys.path.insert(0, str(ROOT / 'syntaxes'))
import obend_object
import source_object

RECEIVE = '''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Preparation.obend as P
import ./Emissions.obend as E
record State:
  count: Nat
  accepting: Bool
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: E.CausalEvent
def receive(state: State, input: P.Value, context: Abi.Context, event: E.CausalEvent) -> Decision:
  {accepted: state.accepting, reason: if state.accepting then "" else "closed", state: {count: state.count + P.natural(P.get(input, "amount")), accepting: state.accepting}, result: event}
record Description:
  name: String
  initial: State
  methods: {receive: {label: String, fields: {}, inputCodec: String}}
  panels: {}
def describe() -> Description:
  {name: "Relay receiver", initial: {count: 0n, accepting: true}, methods: {receive: {label: "Receive", fields: {}, inputCodec: "value"}}, panels: {}}
'''
SEND = '''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Preparation.obend as P
import ./Emissions.obend as E
record State:
  count: Nat
record Input:
  program: String
record Decision:
  accepted: Bool
  reason: String
  state: State
  result: Nat
  emissions: E.Emissions
def send(state: State, input: Input, context: Abi.Context) -> Decision:
  {accepted: true, reason: "", state: {count: state.count + 1n}, result: state.count + 1n, emissions: E.one({to: "recipient", command: "receive", recipientProgram: input.program, payload: P.oneField("amount", P.Value.natural({value: 1n}))})}
record Description:
  name: String
  initial: State
  methods: {send: {label: String, fields: {program: Abi.StringField}}}
  panels: {}
def describe() -> Description:
  {name: "Relay sender", initial: {count: 0n}, methods: {send: {label: "Send", fields: {program: {type: "string", minLength: 64n, maxLength: 64n}}}}, panels: {}}
'''


def protocol(source):
    modules = [{'name': key, 'source': (ROOT / 'world/lib/prelude' / (key + '.obend')).read_text()}
               for key in ('List', 'Abi', 'Preparation', 'Emissions')]
    return obend_object.lower_data_modules(modules + [{'name': 'Actor', 'source': source}])


class MessageRelayTests(unittest.TestCase):
    backend = 'file'
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.database = self.path / 'world.json'
        self.serial = 0
        if self.backend == 'resident':
            relay.desk.world.configure_resident(self.database, profile='compiled')
            self.start_resident()
            self.addCleanup(lambda: self.session.__exit__(None, None, None))
        initialized = self.call({'op': 'messages-init', 'principal': 'owner', 'intent': 'lineage',
                                 'lineage': 'relay-test', 'pendingLimit': 128})
        self.assertEqual(initialized['kind'], 'committed', initialized)
        recipient = protocol(RECEIVE)
        hasher = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'digest': {
            'require': [], 'set': {}, 'result': ['program-digest', ['input', 'program']], 'outbox': []}}}
        made = self.call({'op': 'create', 'object': 'digest', 'principal': 'owner', 'intent': 'create-digest',
                         'protocol': hasher, 'law': ['owner']})
        self.assertEqual(made['kind'], 'committed', made)
        hashed = self.call({'op': 'invoke', 'object': 'digest', 'principal': 'owner', 'intent': 'recipient-digest',
            'expected': made['data']['root'], 'command': 'digest', 'input': {'program': recipient}})
        self.assertEqual(hashed['kind'], 'committed', hashed)
        self.program = hashed['data']['result']
        self.law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'receive': ['relay']},
                    'reprogram': ['owner'], 'law': ['owner']}
        for name, program, law in [('recipient', recipient, self.law),
                ('sender', protocol(SEND), ['author'])]:
            made = self.call({'op': 'create', 'object': name, 'principal': 'owner', 'intent': 'create-' + name,
                             'protocol': program, 'law': law})
            self.assertEqual(made['kind'], 'committed', made)
        self.relay = relay.MessageRelay(self.path / 'relay', self.database, 'relay')

    def start_resident(self):
        self.session = relay.desk.world.resident_session(self.database, profile='compiled')
        self.session.__enter__()

    def call(self, request):
        return relay.desk.world.exchange(self.database, request, profile='compiled')

    def root(self, name='recipient'):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def snapshot(self):
        return relay.desk.world.snapshot(self.database)

    def emit(self):
        self.serial += 1
        response = self.call({'op': 'invoke', 'object': 'sender', 'principal': 'author',
            'intent': 'emit-' + str(self.serial), 'expected': self.root('sender'),
            'command': 'send', 'input': {'program': self.program}})
        self.assertEqual(response['kind'], 'committed', response)
        return response['data']['messages'][0]['id']

    def entry(self, identity):
        return relay.loads(self.relay.event_path(identity).read_bytes())

    def change_law(self, law):
        self.serial += 1
        result = self.call({'op': 'law', 'object': 'recipient', 'principal': 'owner',
            'intent': 'law-' + str(self.serial), 'expected': self.root(), 'law': law})
        self.assertEqual(result['kind'], 'committed', result)

    def test_delivery_restart_deduplication_and_native_facts(self):
        identity = self.emit()
        self.assertEqual(self.relay.run()['errors'], [])
        entry = self.entry(identity)
        self.assertEqual(entry['status'], 'consumed')
        request = entry['attempts'][0]['request']
        self.assertEqual(set(request), {'op', 'object', 'principal', 'intent', 'event', 'expected'})
        receipt = entry['attempts'][0]['receipt']
        self.assertEqual(receipt['data']['result']['source'], 'sender')
        self.assertEqual(receipt['data']['result']['originatingPrincipal'], 'author')
        self.assertEqual(receipt['data']['result']['id'], identity)
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 1)
        before = self.snapshot()
        self.relay = relay.MessageRelay(self.relay.state, self.database, 'relay')
        self.assertEqual(self.relay.run()['processed'], [])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.call(request), receipt)

    def test_crash_after_commit_recovers_before_runtime_and_never_delivers_twice(self):
        identity = self.emit()
        original = relay.worker.command
        def lose(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt('lost committed reply')
        with patch.object(relay.worker, 'command', side_effect=lose):
            with self.assertRaises(KeyboardInterrupt):
                self.relay.run()
        exact = self.entry(identity)['attempts'][0]['request']
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 1)
        self.relay = relay.MessageRelay(self.relay.state, self.database, 'relay')
        with patch.object(self.relay, 'pins', side_effect=AssertionError('recover first')):
            self.assertEqual(self.relay.run()['errors'], [])
        self.assertEqual(self.entry(identity)['attempts'][0]['request'], exact)
        self.assertEqual(self.entry(identity)['status'], 'consumed')
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 1)

    def test_unknown_reply_retains_identity_until_confirmed_stale_then_traces_refresh(self):
        identity = self.emit()
        with patch.object(relay.worker, 'command', side_effect=TimeoutError('before transport')):
            self.assertTrue(self.relay.run()['errors'])
        first = self.entry(identity)['attempts'][0]['request']
        self.change_law(self.law)  # Exact root changes while the unknown attempt is pending.
        refused = self.relay.run()
        self.assertEqual(refused['blocked'][0]['reason'], 'stale read root')
        self.assertEqual(self.entry(identity)['attempts'][0]['request'], first)
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 0)
        self.assertEqual(self.relay.run()['errors'], [])
        attempts = self.entry(identity)['attempts']
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]['receipt']['kind'], 'refused')
        self.assertNotEqual(attempts[0]['request']['intent'], attempts[1]['request']['intent'])
        self.assertEqual(attempts[0]['request']['event'], attempts[1]['request']['event'])
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 1)

    def test_revocation_blocks_without_hotloop_and_explicit_retry_uses_current_law(self):
        identity = self.emit()
        revoked = copy.deepcopy(self.law); revoked['invoke']['receive'] = []
        self.change_law(revoked)
        self.assertEqual(self.relay.run()['blocked'][0]['reason'], 'unauthorized')
        self.assertEqual(self.snapshot()['messages']['events'][identity]['status'], 'pending')
        with patch.object(relay.worker, 'command', side_effect=AssertionError('blocked hot loop')):
            self.assertTrue(self.relay.run()['blocked'])
        self.change_law(self.law)
        self.relay.retry(identity)
        self.assertEqual(self.relay.run()['errors'], [])
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 1)

    def test_replaced_recipient_generation_and_source_refusal_leave_event_pending(self):
        identity = self.emit()
        root = self.root()
        replacement = copy.deepcopy(root['protocol']); replacement['description'] = 'new generation'
        self.assertEqual(self.call({'op': 'reprogram', 'object': 'recipient', 'principal': 'owner',
            'intent': 'replace', 'expected': root, 'protocol': replacement, 'state': root['state']})['kind'], 'committed')
        self.assertIn('program changed', self.relay.run()['blocked'][0]['reason'])
        self.assertEqual(self.snapshot()['messages']['events'][identity]['status'], 'pending')
        current = self.root()
        self.call({'op': 'reprogram', 'object': 'recipient', 'principal': 'owner', 'intent': 'restore-closed',
                   'expected': current, 'protocol': root['protocol'], 'state': {'model': source_object.data({'count': 0, 'accepting': False})}})
        self.relay.retry(identity)
        self.assertIn('closed', self.relay.run()['blocked'][0]['reason'])
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 0)
        self.assertEqual(self.snapshot()['messages']['events'][identity]['status'], 'pending')

    def test_relay_uses_current_read_principal_and_retires_settled_active_custody(self):
        identity = self.emit()
        self.change_law({**self.law, 'read': ['reader', 'relay', 'owner'],
                         'invoke': {'receive': ['relay'], '$messages-settle': ['owner']}})
        with patch.object(relay.worker, 'command', side_effect=TimeoutError('before transport')):
            self.assertTrue(self.relay.run()['errors'])
        reference = {'lineage': 'relay-test', 'id': identity}
        settled = self.call({'op': 'settle-message', 'object': 'recipient', 'principal': 'owner',
            'intent': 'retire-event', 'event': reference, 'expected': self.root(), 'reason': 'Retired generation.'})
        self.assertEqual(settled['kind'], 'committed', settled)
        result = self.relay.run()
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['blocked'], [])
        self.assertEqual(self.entry(identity)['status'], 'settled')
        self.assertEqual(self.relay.run()['processed'], [])
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 0)

    def test_batch_capacity_and_real_custody_deadline(self):
        for _ in range(17): self.emit()
        for limit in (0, 17):
            with self.assertRaises(ValueError): self.relay.run(limit=limit)
        self.relay.state.mkdir(parents=True, exist_ok=True)
        with (self.relay.state / 'relay.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            started = time.monotonic()
            self.assertTrue(self.relay.run(deadline_seconds=0.05)['lockTimedOut'])
            self.assertLess(time.monotonic() - started, 1)
        if self.backend == 'file':
            with Path(str(self.database) + '.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                started = time.monotonic()
                with self.assertRaises(TimeoutError): self.relay.run(deadline_seconds=0.05)
                self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(len(self.relay.run()['processed']), 16)
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 16)
        self.assertEqual(len(self.relay.run()['processed']), 1)
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 17)


class ResidentMessageRelayTests(MessageRelayTests):
    backend = 'resident'

    def test_daemon_restart_recovers_exact_receipt_without_history_expansion(self):
        identity = self.emit()
        original = relay.worker.command
        def lose(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt('lost committed reply')
        with patch.object(relay.worker, 'command', side_effect=lose):
            with self.assertRaises(KeyboardInterrupt):
                self.relay.run()
        request = self.entry(identity)['attempts'][0]['request']
        self.session.__exit__(None, None, None)
        self.start_resident()
        with patch.object(relay.desk.world, 'snapshot', side_effect=AssertionError('no history export for delivery')):
            result = self.relay.run()
            self.assertEqual(result['errors'], [], result)
            self.assertEqual(self.relay.run()['processed'], [])
        self.assertEqual(self.entry(identity)['attempts'][0]['request'], request)
        self.assertEqual(self.entry(identity)['attempts'][0]['receipt'], self.call(request))
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 1)
        self.assertFalse(self.database.exists(), 'resident backend must not create a legacy world dump')


class ResidentServiceJourneyTests(unittest.TestCase):
    call = MessageRelayTests.call
    root = MessageRelayTests.root
    snapshot = MessageRelayTests.snapshot
    start_resident = MessageRelayTests.start_resident

    def setUp(self):
        import service
        import workspace
        sys.path.insert(0, str(ROOT / 'conformance'))
        from test_service import PDS, AUTHOR
        self.service, self.author = service, AUTHOR
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.directory = self.path / 'workspace'
        self.database = self.directory / 'world.json'
        recipient = protocol(RECEIVE)
        hasher = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'digest': {
            'require': [], 'set': {}, 'result': ['program-digest', ['input', 'program']], 'outbox': []}}}
        self.seed = workspace.initialize(self.directory, [
            {'id': 'recipient', 'syntax': 'protocol-json@1', 'source': relay.canonical(recipient),
             'law': {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'receive': ['relay']},
                     'law': ['owner'], 'reprogram': ['owner']}},
            {'id': 'sender', 'syntax': 'protocol-json@1', 'source': relay.canonical(
                protocol(SEND)), 'law': [AUTHOR]},
            {'id': 'digest', 'syntax': 'protocol-json@1', 'source': relay.canonical(hasher), 'law': ['owner']}],
            entry_objects=['recipient', 'sender'], principal='owner', profile='compiled',
            backend='resident', messaging=True)
        self.start_resident()
        self.addCleanup(lambda: self.session.__exit__(None, None, None))
        hashed = self.call({'op': 'invoke', 'object': 'digest', 'principal': 'owner', 'intent': 'digest',
            'expected': self.root('digest'), 'command': 'digest', 'input': {'program': recipient}})
        self.assertEqual(hashed['kind'], 'committed', hashed)
        self.program = hashed['data']['result']
        self.initial_sender = self.root('sender')
        self.pds = PDS()
        self.clerk = service.clerk.Clerk(self.path / 'clerk', self.pds)
        self.enrollment = self.clerk.attach(self.directory, self.snapshot()['objects'], [AUTHOR],
            expected_genesis=self.seed['genesis'], expected_seed_head=self.seed['head'], runtime_profile='compiled')
        self.app = service.Service(self.path / 'service', receiver=self.clerk.receive)
        self.app.initialize(self.directory, self.clerk.state, 'compiler',
            public_genesis=self.seed['genesis'], relay_principal='relay')

    def record(self, key, *, root=None):
        wire = {'object': 'sender', 'command': 'send', 'input': {'program': self.program},
                'expected': self.initial_sender if root is None else root}
        uri = 'at://' + self.author + '/' + self.service.clerk.COLLECTION + '/' + key
        self.pds.records[key] = {'uri': uri, 'cid': 'cid-' + key,
            'value': self.service.worker.receipts.encode('request', relay.canonical(wire).decode())}
        return uri, 'cid-' + key

    def test_enrollment_receive_relay_continuation_and_restart(self):
        self.assertEqual(self.enrollment['status'], 'attached')
        source = self.record('send')
        self.app.enqueue(*source)
        result = self.app.tick()
        self.assertEqual(result['errors'], [], result)
        self.assertEqual(result['status'], 'prepared-offline', result)
        self.assertEqual(result['phases']['localMessages']['processed'][0]['status'], 'consumed')
        self.assertEqual(source_object.plain(self.root()['state']['model'])['count'], 1)
        receipt = self.clerk.receive(*source)
        event = receipt['reply']['data']['messages'][0]
        self.assertEqual(self.snapshot()['messages']['events'][event['id']]['status'], 'consumed')
        prepared = result['continuation']
        verified = self.service.continuation.verify(prepared['destination'], expected_genesis=self.seed['genesis'],
            expected_head=prepared['head'], base_head=self.seed['head'])
        self.assertEqual(verified['status'], 'verified-offline')
        before = self.snapshot()
        self.session.__exit__(None, None, None)
        self.start_resident()
        restarted = self.service.Service(self.app.state, receiver=self.clerk.receive)
        again = restarted.tick()
        self.assertEqual(again['errors'], [], again)
        self.assertEqual(again['continuation'], prepared)
        self.assertEqual(again['phases']['localMessages']['processed'], [])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.database.exists())

    def test_clerk_lost_reply_recovers_exact_admission_before_pins_then_stale_refuses(self):
        source = self.record('lost')
        original = self.service.clerk.world.exchange
        def lose(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt('lost resident admission reply')
        with patch.object(self.service.clerk.world, 'exchange', side_effect=lose):
            with self.assertRaises(KeyboardInterrupt):
                self.clerk.receive(*source)
        before = self.snapshot()
        with patch.object(self.service.clerk, 'pins', side_effect=AssertionError('retained reply before pins')):
            receipt = self.clerk.receive(*source)
        self.assertEqual(receipt['reply']['kind'], 'committed')
        self.assertEqual(self.snapshot(), before)
        stale = self.clerk.receive(*self.record('stale'))
        self.assertEqual(stale['reply']['kind'], 'refused')
        self.assertEqual(stale['reply']['data'], 'stale read root')
        self.assertEqual(source_object.plain(self.root('sender')['state']['model'])['count'], 1)


if __name__ == '__main__': unittest.main()
