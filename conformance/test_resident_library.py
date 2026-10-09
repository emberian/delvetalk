#!/usr/bin/env python3
"""Two independent @3 residents reuse actual Bend subscription/mailbox modules.

Every effect, delivery, refusal and retry uses the compiled receiving host. No
remote transport, Python semantic implementation or generated Bend source.
"""
import importlib.util
import json
import subprocess
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


def prelude():
    return [{'name': key, 'source': (ROOT / 'world/lib/prelude' / (key + '.obend')).read_text()}
            for key in ('List', 'Abi', 'Preparation', 'Encounter', 'Emissions')]


def sources(name):
    return prelude() + [
        {'name': key, 'source': (PACKAGE / (key + '.obend')).read_text()}
        for key in ('Consent', 'Mailbox', name)]


def authored(name):
    return adapter.lower_data_modules(sources(name))


def record_fields(wire):
    assert wire['tag'] == 'record', wire
    return {field['name']: field['value'] for field in wire['fields']}


def notes(root):
    """Read native DataWire for assertions; never decide admission."""
    queue = record_fields(record_fields(root['state']['model'])['notes'])
    def decode(current):
        result = []
        while current['label'] == 'cons':
            fields = record_fields(current['payload'])
            result.append({key: (int(value['value']) if value['tag'] == 'natural' else value['value'])
                           for key, value in record_fields(fields['head']).items()})
            current = fields['tail']
        assert current['label'] == 'nil', current
        return result
    result = decode(queue['front']) + list(reversed(decode(queue['rear'])))
    assert len(result) == int(queue['size']['value'])
    return result


def policy(name, relay=True):
    return {'profile': 'delvetalk-scoped-law',
            'invoke': {'configure': [name + '-keeper'], 'selectPeer': [name + '-keeper'], 'announce': [name + '-member'],
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

    def announce(self, source, topic='ready', units=1, kind='committed', after=0, limit=4):
        reply = self.invoke(source, 'announce', {'topic': topic, 'units': units, 'after': after, 'limit': limit}, kind=kind)
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

    def test_bounded_emission_collection_fanout_and_exact_target_program(self):
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
        self.configure('repair', 'circle', side='send', slot=65536, kind='refused')
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
        source = (PACKAGE / 'OutsideEmitter.obend').read_text()
        program = {'profile': 'delvetalk-local-v1', 'initial': {'model': {'tag': 'record', 'fields': []}}, 'commands': {'emit': {
            'transition': {'profile': 'delvetalk-source-transition', 'messages': {'emit': True, 'receive': False}, 'package': {
                'modules': prelude() + [{'name': 'Consent', 'source': (PACKAGE / 'Consent.obend').read_text()},
                            {'name': 'Outside', 'source': source}], 'entry': 'emit'}}}}}
        self.call({'op': 'create', 'object': 'outsider', 'principal': 'bootstrap',
                   'intent': 'create-outsider', 'protocol': program, 'law': ['outsider-member']})
        for generation in (0, 65536):
            event = self.invoke('outsider', 'emit', {'program': self.digests['circle'],
                                'generation': generation})['data']['messages'][0]
            self.assertEqual(self.deliver('circle', event)['data']['result'], 'declined-consent')
            self.assertNotIn(event['id'], self.pending())
        self.assertEqual(notes(self.root('circle')), [])

    def test_ordered_collection_pages_capacity_reclamation_and_native_fanout(self):
        self.configure('circle', 'repair', side='listen')
        # Keys are identities, not four storage positions; insertion order is irrelevant.
        keys = [160, 10, 90, 30, 70, 150, 20, 40, 60, 50, 140, 80, 130, 100, 120, 110]
        for key in keys:
            self.configure('repair', 'circle', side='send', slot=key)
        before = self.root('repair')
        self.configure('repair', 'circle', side='send', slot=170, kind='refused')
        self.assertEqual(self.root('repair'), before)
        # Replacement consumes no capacity. Removal really frees a collection entry.
        self.configure('repair', 'circle', side='send', slot=10)
        self.configure('repair', 'circle', side='send', slot=90, enabled=False)
        self.configure('repair', 'circle', side='send', slot=170)
        expected_keys = sorted((set(keys) - {90}) | {170})
        cursor = 0
        for offset in range(0, 16, 4):
            reply = self.invoke('repair', 'announce', {'topic': 'help', 'units': 1,
                                                     'after': cursor, 'limit': 4})
            page = reply['data']['result']
            self.assertEqual(page, {'next': expected_keys[offset + 3], 'count': 4, 'more': offset < 12})
            self.assertEqual(len(reply['data']['messages']), 4)
            for event in reply['data']['messages']:
                self.deliver('circle', event)
                self.assertEqual(notes(self.root('circle'))[0]['event'], event['id'])
                self.invoke('circle', 'acknowledge', {})
            cursor = page['next']
        self.announce('repair', after=cursor, kind='refused')
        self.announce('repair', limit=5, kind='refused')
        self.announce('repair', limit=0, kind='refused')
        self.assertEqual(self.pending(), {})

    def test_five_independent_sources_use_sparse_incoming_keys(self):
        for index in range(1, 6):
            name = 'neighbor-' + str(index)
            self.call({'op': 'create', 'principal': 'bootstrap', 'intent': self.identity(),
                       'object': name, 'protocol': self.programs['repair'], 'law': policy(name)})
            self.digests[name] = self.digests['repair']
            self.connect(name, 'circle', generation=index, listen_slot=index * 100)
        for index in range(1, 6):
            name = 'neighbor-' + str(index)
            event = self.announce(name)[0]
            self.deliver('circle', event)
            self.assertEqual(notes(self.root('circle'))[0]['source'], name)
            self.invoke('circle', 'acknowledge', {})
        # Removing a middle entry preserves the remaining source's older epoch.
        self.configure('circle', 'neighbor-3', side='listen', generation=6, slot=300, enabled=False)
        stale = self.announce('neighbor-3')[0]
        self.assertEqual(self.deliver('circle', stale)['data']['result'], 'declined-consent')
        self.deliver('circle', self.announce('neighbor-5')[0])
        self.assertEqual(notes(self.root('circle'))[0]['source'], 'neighbor-5')

    def test_peer_enrollment_captures_observed_identity_without_a_hash_form(self):
        portal = module('resident_library_portal', 'scripts/portal.py')
        runtime = module('resident_library_runtime', 'scripts/runtime_profile.py')
        portal.save(Path(self.temp.name) / 'manifest.json', {
            'cafe': 'repair', 'runtime': {'name': 'compiled', 'files': runtime.file_hashes('compiled')}})
        app = portal.Portal(Path(self.temp.name))
        for source, peer, side in [('circle', 'repair', 'listen'), ('repair', 'circle', 'send')]:
            self.invoke(source, 'selectPeer', {'side': side, 'slot': 1, 'enabled': True,
                'object': peer, 'generation': 1}, principal=source + '-keeper')
            card = app.object(source)
            self.assertEqual(card['mode'], 'projection', card)
            action = next(item for item in card['actions'] if item.get('offer') == 'configure')
            self.assertEqual(action['fields'], [])
            for offered in card['actions']:
                self.assertNotIn('program', {field['name'] for field in offered.get('fields', [])})
            request = app.captured_request(app._read('cards', card['card']), action['id'],
                source + '-keeper', self.identity(), {})
            self.assertEqual(set(request['reads']), {source, peer})
            self.assertEqual(request['calls'][0]['input']['program'], self.digests[peer])
            if side == 'listen':
                # A captured peer remains an exact read, including its current law.
                self.revise_grants(peer, relay=True)
                self.call(request, 'refused')
                card = app.object(source)
                action = next(item for item in card['actions'] if item.get('offer') == 'configure')
                request = app.captured_request(app._read('cards', card['card']), action['id'],
                    source + '-keeper', self.identity(), {})
            self.call(request)
        event = self.announce('repair')[0]
        self.deliver('circle', event)
        self.assertEqual(notes(self.root('circle'))[-1]['source'], 'repair')

    def test_authored_examples_use_real_source_receiving(self):
        proposal = module('resident_library_proposal', 'scripts/propose.py')
        examples = module('resident_library_examples', 'syntaxes/spell_examples.py')
        outcomes = proposal.run_scenarios(self.programs['repair'],
            examples.parse((PACKAGE / 'RepairBoard.examples').read_text()), profile='compiled')
        self.assertEqual([item['failures'] for item in outcomes], [[]])

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


@unittest.skipUnless((ROOT / '.lake/build/bin/delvetalk-obend').is_file(), 'prebuilt source runner required')
class ResidentCollections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = {}
        for entry in ('study', 'queue', 'subscriptions'):
            compiled = cls.native({'op': 'compile', 'modules': sources('CollectionStudy'), 'entry': entry})
            if compiled.get('status') != 'compiled':
                raise AssertionError(compiled)
            cls.artifacts[entry] = compiled['artifact']

    @staticmethod
    def native(request):
        process = subprocess.run([str(ROOT / '.lake/build/bin/delvetalk-obend')],
            input=json.dumps(request) + '\n', text=True, capture_output=True, check=True, timeout=15)
        return json.loads(process.stdout)

    def run_source(self, entry, size):
        return self.native({'op': 'run-data-v1', 'artifact': self.artifacts[entry],
                            'arguments': [{'tag': 'natural', 'value': str(size)}]})

    def test_collection_algorithms_scale_to_200_with_default_machine_budget(self):
        for size in (8, 32, 64, 128, 200):
            result = self.run_source('study', size)
            self.assertEqual(result['status'], 'finished', result)
            values = record_fields(result['value'])
            self.assertEqual(int(values['queued']['value']), size)
            self.assertEqual(int(values['total']['value']), size * (size + 1) // 2)
            self.assertEqual(int(values['selected']['value']), 4)
            self.assertEqual(int(values['next']['value']), size)
            self.assertFalse(values['more']['value'])
            self.assertTrue(values['absent']['value'])
            self.assertLess(result['ticksUsed'] + result['conversionNodes'], 100000)

    def test_representative_collections_materialize_without_a_fuel_override(self):
        for entry in ('queue', 'subscriptions'):
            for size in (8, 32, 64):
                result = self.run_source(entry, size)
                self.assertEqual(result['status'], 'finished', result)
                self.assertLess(result['ticksUsed'] + result['conversionNodes'], 100000)


if __name__ == '__main__':
    unittest.main()
