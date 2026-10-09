#!/usr/bin/env python3
"""Two independent @3 residents reuse actual Bend subscription/mailbox modules.

Every effect, delivery, refusal and retry uses the compiled receiving host. No
remote transport, Python semantic implementation or generated Bend source.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'protocols/resident-library'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


world = module('resident_library_world', 'scripts/world.py')
adapter = module('resident_library_adapter', 'syntaxes/obend_object.py')
projection = module('resident_library_projection', 'scene/projection.py')
relay_module = module('resident_library_relay', 'scripts/message_relay.py')


def authored(name):
    return adapter.lower_data_modules([
        {'name': key, 'source': (PACKAGE / (key + '.obend')).read_text()}
        for key in ('Consent', 'Mailbox', name)])


def record_fields(wire):
    assert wire['tag'] == 'record', wire
    return {field['name']: field['value'] for field in wire['fields']}


def notes(root):
    """Read native DataWire for assertions; never decide admission."""
    current = record_fields(root['state']['model'])['notes']
    result = []
    while current['label'] == 'cons':
        fields = record_fields(current['payload'])
        result.append({key: (int(value['value']) if value['tag'] == 'natural' else value['value'])
                       for key, value in record_fields(fields['head']).items()})
        current = fields['tail']
    assert current['label'] == 'nil', current
    return result


def policy(name, relay=True):
    return {'profile': 'delvetalk-scoped-law-v1',
            'invoke': {'configure': [name + '-keeper'], 'announce': [name + '-member'],
                       'receive': ['relay'] if relay else [], 'acknowledge': [name + '-member']},
            'reprogram': ['builder'], 'law': ['steward']}


@unittest.skipUnless((ROOT / '.lake/build/bin/delvetalk-compiled').is_file(), 'prebuilt compiled host required')
class ResidentLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.programs = {'repair': authored('RepairBoard'), 'circle': authored('ReadingCircle')}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'world.json'
        self.serial = 0
        self.call({'op': 'messages-init', 'principal': 'bootstrap', 'intent': 'init',
                   'lineage': 'resident-library', 'pendingLimit': 32})
        for name, program in self.programs.items():
            self.call({'op': 'create', 'principal': 'bootstrap', 'intent': 'create-' + name,
                       'object': name, 'protocol': program, 'law': policy(name)})
        self.call({'op': 'create', 'principal': 'bootstrap', 'intent': 'digest-create', 'object': 'digest',
                   'protocol': {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'hash': {
                       'require': [], 'set': {}, 'outbox': [], 'result': ['program-digest', ['input', 'program']]}}},
                   'law': ['reader']})
        self.digests = {name: self.invoke('digest', 'hash', {'program': protocol}, principal='reader')['data']['result']
                        for name, protocol in self.programs.items()}

    def identity(self):
        self.serial += 1
        return 'library-' + str(self.serial)

    def call(self, request, kind='committed'):
        reply = world.exchange(self.database, request, profile='compiled')
        if kind is not None:
            self.assertEqual(reply['kind'], kind, reply)
        return reply

    def root(self, name):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'}, None)

    def invoke(self, name, command, value, *, principal=None, kind='committed'):
        request = {'op': 'invoke', 'object': name, 'command': command, 'input': value,
                   'principal': principal or name + '-member', 'intent': self.identity(), 'expected': self.root(name)}
        return self.call(request, kind)

    def configure(self, name, peer, *, side, generation=1, enabled=True, slot=1, kind='committed', principal=None):
        return self.invoke(name, 'configure', {'side': side, 'slot': slot, 'enabled': enabled,
            'object': peer, 'program': self.digests[peer], 'generation': generation},
            principal=principal or name + '-keeper', kind=kind)

    def connect(self, source, target, generation=1, slot=1, listen_slot=1):
        self.configure(target, source, side='listen', generation=generation, slot=listen_slot)
        self.configure(source, target, side='send', generation=generation, slot=slot)

    def announce(self, source, topic='ready', units=1, kind='committed'):
        reply = self.invoke(source, 'announce', {'topic': topic, 'units': units}, kind=kind)
        return reply['data']['messages'] if kind == 'committed' else reply

    def delivery(self, target, event, principal='relay'):
        return {'op': 'deliver', 'object': target, 'event': event, 'principal': principal,
                'intent': self.identity(), 'expected': self.root(target)}

    def deliver(self, target, event, kind='committed'):
        return self.call(self.delivery(target, event), kind)

    def revise_grants(self, name, *, relay):
        self.call({'op': 'law', 'object': name, 'principal': 'steward', 'intent': self.identity(),
                   'expected': self.root(name), 'law': policy(name, relay)})

    def pending(self):
        return self.call({'op': 'messages-pending', 'principal': 'reader'}, None)['pending']

    def test_two_authored_objects_share_modules_and_exchange_native_notices(self):
        for source, target in [('repair', 'circle'), ('circle', 'repair')]:
            self.connect(source, target)
            event = self.announce(source, 'help', 2)[0]
            request = self.delivery(target, event)
            accepted = self.call(request)
            stored = notes(self.root(target))[-1]
            self.assertEqual(stored, {'topic': 'help', 'units': 2, 'event': event['id'],
                                      'source': source, 'author': source + '-member'})
            before = self.database.read_bytes()
            self.assertEqual(self.call(request), accepted)
            self.assertEqual(self.database.read_bytes(), before)
            self.deliver(target, event, 'refused')
        self.assertEqual(self.pending(), {})
        for name in ('repair', 'circle'):
            before = self.database.read_bytes()
            view = projection.project(self.root(name), name, panel='oldest')
            self.assertEqual(view['data']['prose'], 'help')
            self.assertIn('acknowledge', view['data']['actions'])
            self.assertNotIn('receive', view['data']['actions'])
            self.assertEqual(self.database.read_bytes(), before)
        # An authenticated but permanently unsupported notice is explicitly declined.
        event = self.announce('circle', 'reading', 1)[0]
        before = self.root('repair')
        declined = self.deliver('repair', event)
        self.assertEqual(declined['data']['result'], 'declined-notice')
        self.assertEqual(self.root('repair')['state'], before['state'])
        self.assertNotIn(event['id'], self.pending())
        self.announce('repair', 'reading', kind='refused')
        self.announce('repair', units=5, kind='refused')

    def test_bounded_mailbox_keeps_pressure_until_explicit_fifo_acknowledgement(self):
        self.connect('circle', 'repair')
        first = self.announce('circle', 'help')[0]
        second = self.announce('circle', 'ready')[0]
        waiting = self.announce('circle', 'help', 2)[0]
        self.deliver('repair', first)
        self.deliver('repair', second)
        before = self.root('repair')
        self.deliver('repair', waiting, 'refused')
        self.assertEqual(self.root('repair'), before)
        self.assertIn(waiting['id'], self.pending())
        ack = self.invoke('repair', 'acknowledge', {})
        self.assertEqual(ack['data']['result'], 'help')
        self.deliver('repair', waiting)
        self.assertEqual([n['event'] for n in notes(self.root('repair'))], [second['id'], waiting['id']])
        self.invoke('repair', 'acknowledge', {})
        self.invoke('repair', 'acknowledge', {})
        self.invoke('repair', 'acknowledge', {}, kind='refused')
        # The other independently authored layer inherits three slots, not two.
        self.connect('repair', 'circle')
        for _ in range(3):
            self.deliver('circle', self.announce('repair')[0])
        self.deliver('circle', self.announce('repair')[0], 'refused')
        self.assertEqual(len(notes(self.root('circle'))), 3)

    def test_recipient_withdrawal_generation_and_current_law_are_separate(self):
        self.connect('repair', 'circle')
        old = self.announce('repair')[0]
        self.configure('circle', 'repair', side='listen', generation=2, enabled=False)
        request = self.delivery('circle', old)
        declined = self.call(request)
        self.assertEqual(declined['data']['result'], 'declined-consent')
        self.configure('circle', 'repair', side='listen', generation=3)
        self.assertEqual(self.call(request), declined)
        self.configure('repair', 'circle', side='send', generation=3)
        current = self.announce('repair')[0]
        self.revise_grants('circle', relay=False)
        denied = self.delivery('circle', current)
        refusal = self.call(denied, 'refused')
        self.revise_grants('circle', relay=True)
        self.assertEqual(self.call(denied, 'refused'), refusal)
        self.deliver('circle', current)
        self.assertNotIn(old['id'], self.pending())
        self.configure('circle', 'repair', side='listen', generation=3, kind='refused')
        self.configure('repair', 'circle', side='send', generation=3, principal='circle-keeper', kind='refused')

    def test_direct_receive_and_forged_origin_cannot_replace_native_facts(self):
        self.connect('repair', 'circle')
        before = self.root('circle')
        self.invoke('circle', 'receive', {'topic': 'help', 'units': 1, 'generation': 1}, principal='relay', kind='refused')
        event = self.announce('repair')[0]
        forged = self.delivery('circle', event)
        forged['eventFacts'] = {'id': event['id'], 'source': 'repair',
                                'sourceProgram': self.digests['repair'], 'originatingPrincipal': 'circle-keeper'}
        self.call(forged, 'refused')
        self.assertEqual(self.root('circle'), before)
        self.deliver('circle', event)
        self.assertEqual(notes(self.root('circle'))[0]['author'], 'repair-member')

    def test_four_slot_effect_contract_fanout_and_exact_target_program(self):
        self.connect('repair', 'circle')
        self.configure('repair', 'circle', side='send', slot=2)
        self.configure('repair', 'repair', side='listen')
        self.configure('repair', 'repair', side='send', slot=3)
        self.configure('repair', 'repair', side='send', slot=4)
        references = self.announce('repair')
        self.assertEqual(len(references), 4)
        self.assertEqual(len({event['id'] for event in references}), 4)
        for target, event in zip(('circle', 'circle', 'repair', 'repair'), references):
            self.deliver(target, event)
        self.assertEqual(len(notes(self.root('circle'))), 2)
        self.assertEqual(len(notes(self.root('repair'))), 2)
        self.assertEqual(self.pending(), {})
        before = self.root('repair')
        self.configure('repair', 'circle', side='send', slot=5, kind='refused')
        self.assertEqual(self.root('repair'), before)
        # A changed program at the destination invalidates the stored subscription.
        current = self.root('circle')
        self.call({'op': 'reprogram', 'object': 'circle', 'principal': 'builder', 'intent': self.identity(),
            'expected': current, 'protocol': current['protocol'] | {'editionNote': 'new generation'},
            'state': current['state']})
        before = self.root('repair')
        self.announce('repair', kind='refused')
        self.assertEqual(self.root('repair'), before)

    def test_multiple_sources_reenroll_without_invalidating_other_slots_or_reusing_epochs(self):
        self.call({'op': 'create', 'principal': 'bootstrap', 'intent': 'create-annex',
                   'object': 'annex', 'protocol': self.programs['circle'], 'law': policy('annex')})
        self.digests['annex'] = self.invoke('digest', 'hash', {'program': self.programs['circle']},
                                           principal='reader')['data']['result']
        self.connect('repair', 'circle', generation=1, listen_slot=1)
        self.connect('annex', 'circle', generation=2, listen_slot=2)
        # Advancing the global epoch does not expire another still-active slot.
        self.deliver('circle', self.announce('repair', 'help')[0])
        self.deliver('circle', self.announce('annex', 'ready')[0])
        self.assertEqual([note['source'] for note in notes(self.root('circle'))], ['repair', 'annex'])
        withdrawn = self.announce('repair')[0]
        independent = self.announce('annex')[0]
        self.configure('circle', 'repair', side='listen', generation=3, enabled=False, slot=1)
        self.deliver('circle', independent)
        before = self.root('circle')['state']
        declined = self.deliver('circle', withdrawn)
        self.assertEqual(declined['data']['result'], 'declined-consent')
        self.assertEqual(self.root('circle')['state'], before)
        # Reusing the withdrawn identity in another slot cannot revive its old epoch.
        self.configure('circle', 'repair', side='listen', generation=1, slot=3, kind='refused')
        self.configure('circle', 'repair', side='listen', generation=3, slot=3, kind='refused')
        self.configure('circle', 'repair', side='listen', generation=4, slot=3)
        before = self.root('circle')
        self.configure('circle', 'annex', side='listen', generation=5, slot=4, kind='refused')
        self.assertEqual(self.root('circle'), before, 'duplicate source cannot reserve another slot or advance epoch')
        # Copying another source's current generation cannot forge its native facts.
        self.configure('annex', 'circle', side='send', generation=4)
        forgery = self.announce('annex')[0]
        self.assertEqual(self.deliver('circle', forgery)['data']['result'], 'declined-consent')
        self.configure('repair', 'circle', side='send', generation=4)
        current = self.announce('repair')[0]
        self.deliver('circle', current, 'refused')  # Consent is valid; capacity is temporary.
        self.invoke('circle', 'acknowledge', {})
        self.deliver('circle', current)
        self.assertEqual(notes(self.root('circle'))[-1]['source'], 'repair')
        self.configure('circle', 'repair', side='listen', generation=65536, slot=3, kind='refused')
        self.configure('circle', 'repair', side='listen', generation=5, slot=5, kind='refused')

    def test_future_consent_waits_but_impossible_consent_declines(self):
        self.configure('repair', 'circle', side='send', generation=2)
        future = self.announce('repair')[0]
        before = self.root('circle')
        self.deliver('circle', future, 'refused')
        self.assertEqual(self.root('circle'), before)
        self.assertIn(future['id'], self.pending())
        self.configure('circle', 'repair', side='listen', generation=2)
        self.deliver('circle', future)
        self.assertEqual(len(notes(self.root('circle'))), 1)
        self.configure('repair', 'circle', side='send', generation=1)
        obsolete = self.announce('repair')[0]
        self.assertEqual(self.deliver('circle', obsolete)['data']['result'], 'declined-consent')
        self.assertEqual(len(notes(self.root('circle'))), 1)

    def test_actual_relay_declines_obsolete_events_and_recovers_pending_quota(self):
        self.connect('repair', 'circle')
        for slot in (2, 3, 4):
            self.configure('repair', 'circle', side='send', slot=slot)
        references = []
        for _ in range(8):
            references.extend(self.announce('repair'))
        self.assertEqual(len(self.pending()), 32)
        before = self.root('repair')
        refused = self.announce('repair', kind='refused')
        self.assertIn('capacity', refused['data'])
        self.assertEqual(self.root('repair'), before)
        self.configure('circle', 'repair', side='listen', generation=2, enabled=False)
        relay = relay_module.MessageRelay(Path(self.temp.name) / 'relay', self.database, 'relay')
        for _ in range(2):
            report = relay.run(limit=16, deadline_seconds=60)
            self.assertEqual(report['errors'], [])
            self.assertEqual(report['blocked'], [])
            self.assertFalse(report['deadlineReached'])
            self.assertEqual(len(report['processed']), 16)
        self.assertEqual(self.pending(), {})
        self.assertEqual(notes(self.root('circle')), [])
        for event in references:
            retained = relay_module.loads(relay.event_path(event['id']).read_bytes())
            self.assertEqual(retained['status'], 'consumed')
            self.assertEqual(retained['attempts'][0]['receipt']['data']['result'], 'declined-consent')
        first = relay_module.loads(relay.event_path(references[0]['id']).read_bytes())['attempts'][0]
        self.configure('circle', 'repair', side='listen', generation=3)
        self.assertEqual(self.call(first['request']), first['receipt'])
        for slot in range(1, 5):
            self.configure('repair', 'circle', side='send', slot=slot, generation=3, enabled=slot == 1)
        recovered = self.announce('repair', 'help')[0]
        restarted = relay_module.MessageRelay(relay.state, self.database, 'relay')
        report = restarted.run(deadline_seconds=60)
        self.assertEqual(report['errors'], [])
        self.assertEqual(report['blocked'], [])
        self.assertEqual(notes(self.root('circle'))[0]['event'], recovered['id'])
        self.assertEqual(self.pending(), {})

    def test_external_emitter_cannot_strand_impossible_consent_generations(self):
        # A separately authored sender deliberately omits this library's generation
        # guard. Its admitted events still carry authentic native source facts.
        source = """edition ObjectiveBend 1
import ./Consent.obend as Consent
record Input:
  program: String
  generation: Nat
record Context:
  object: String
  principal: String
  inputOrigin: {kind: String, object: String, command: String, immediatelyPrevious: Bool}
record Effects:
  accepted: Bool
  reason: String
  state: {}
  result: {}
  emissions: Consent.Slots
def emit(state: {}, input: Input, context: Context) -> Effects:
  {accepted: true, reason: "", state: state, result: {}, emissions: Consent.emit({epoch: 0, inbound: Consent.peers(), outbound: {a: {enabled: true, object: "circle", program: input.program, generation: input.generation}, b: Consent.empty(), c: Consent.empty(), d: Consent.empty()}}, "ready", 1)}
"""
        program = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {'emit': {
            'transition': {'profile': 'delvetalk-source-effects-v1', 'package': {
                'modules': [{'name': 'Consent', 'source': (PACKAGE / 'Consent.obend').read_text()},
                            {'name': 'Outside', 'source': source}], 'entry': 'emit'}}}}}
        self.call({'op': 'create', 'object': 'outsider', 'principal': 'bootstrap',
                   'intent': 'create-outsider', 'protocol': program, 'law': ['outsider-member']})
        for generation in (0, 65536):
            event = self.invoke('outsider', 'emit', {'program': self.digests['circle'],
                                'generation': generation})['data']['messages'][0]
            self.assertEqual(self.deliver('circle', event)['data']['result'], 'declined-consent')
            self.assertNotIn(event['id'], self.pending())
        self.assertEqual(notes(self.root('circle')), [])

    def test_forms_use_the_assembled_behavior_limits(self):
        for name, maximum in [('repair', 4), ('circle', 6)]:
            program = self.programs[name]
            for method in ('announce', 'receive'):
                self.assertEqual(program['affordances'][method]['fields']['units']['maximum'], maximum)
            self.connect(name, name)
            event = self.announce(name, units=maximum)[0]
            self.deliver(name, event)
            self.assertEqual(notes(self.root(name))[0]['units'], maximum)
            self.announce(name, units=maximum + 1, kind='refused')


if __name__ == '__main__':
    unittest.main()
