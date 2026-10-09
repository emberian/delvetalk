"""Source-prepared clock → real Bell → real Door → real Lantern relationship."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_appointments as appointments
from test_appointments import ROOT, FIXTURES, native, wire, plain, law
import world
import source_offers
import clock_physical_driver as driver
import message_relay
import obend_object
import source_object
sys.path.insert(0, str(ROOT))
from scene import projection


def source(name, directory):
    return {'name': name, 'source': (directory / (name + '.obend')).read_text()}


def modules(name):
    common = [source(n, ROOT / 'world/lib/prelude') for n in ('List', 'Abi', 'Encounter', 'Preparation', 'Emissions')]
    if name in ('Clock', 'ScheduledBell'):
        common.append(source('Appointments', FIXTURES))
    if name == 'ScheduledBell':
        return common + [source('Bell', ROOT / 'protocols/resident-messages'), source(name, FIXTURES)]
    return common + [source(name, FIXTURES if name == 'Clock' else ROOT / 'protocols/resident-messages')]


class AppointmentRelationship(unittest.TestCase):
    programs = {}

    def setUp(self):
        self.fx = appointments.Appointments()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.fx.call({'op': 'messages-init', 'principal': 'bootstrap', 'intent': 'registry',
            'lineage': 'appointed-courtyard', 'pendingLimit': 128}, 'committed')
        for name in ('Clock', 'ScheduledBell', 'Door', 'Lantern'):
            if name not in self.programs:
                self.programs[name] = obend_object.lower_data_modules(modules(name))
        clock = copy.deepcopy(self.programs['Clock'])
        artifact = native({'op': 'compile', 'modules': modules('Clock'), 'entry': 'physical'})['artifact']
        initial = native({'op': 'run-data-v1', 'artifact': artifact,
            'arguments': [wire({'capacity': 16, 'epochMillis': 1000, 'quantumMillis': 1000})]})['value']
        clock['initial']['model'] = source_object.compact_state(clock, initial,
            entry='physical', path=['codomain'])
        self.fx.create('clock', clock, law({'quote': ['moss', 'iris'], 'request': ['moss', 'iris'],
            'cancel': ['moss', 'iris'], 'status': ['moss', 'iris'], 'sample': ['driver'], 'tick': ['driver'], 'page': ['moss']}))
        self.fx.create('bell', self.programs['ScheduledBell'], law({'arm': ['moss', 'iris'],
            'scheduled': ['moss', 'iris'], 'cancelled': ['moss', 'iris'], 'retired': ['moss', 'iris'], 'wake': ['relay']}))
        self.fx.create('door', self.programs['Door'], law({'hear': ['relay'], 'bind': ['moss']}))
        self.fx.create('lantern', self.programs['Lantern'], law({'glow': ['relay']}))
        self.relay = message_relay.MessageRelay(Path(self.fx.temp.name) / 'relay', self.fx.db, 'relay')

    def invitation(self, object, offer):
        owner = world.capture_roots(self.fx.db, [object], principal='moss', profile='compiled')
        view = projection.project(owner['roots'][object]['root'], object)
        capture = source_offers.capture_observations(view, owner, database=self.fx.db,
            principal='moss', profile='compiled')
        roots = {name: pair['root'] for name, pair in capture['roots'].items()}
        references = {name: pair['reference'] for name, pair in capture['roots'].items()}
        return source_offers.capture(view, roots, references=references)[offer]

    def prepare(self, object, offer, fields, principal='moss'):
        return source_offers.prepare_value(self.invitation(object, offer), principal,
            self.fx.intent(), fields, database=self.fx.db)

    def schedule(self, **fields):
        prepared = self.prepare('bell', 'schedule', {'due': 5, 'deadline': 10, 'chord': 'C E G', **fields})
        self.assertEqual(prepared['kind'], 'ready', prepared)
        receipt = self.fx.call(prepared['request'], 'committed')
        return prepared, receipt

    def sample(self, timestamp=6000, name='physical'):
        with patch.object(driver.time, 'time_ns', return_value=timestamp * 1_000_000):
            return driver.sample(self.fx.db, Path(self.fx.temp.name) / (name + '.json'),
                clock='clock', principal='driver', intent=name)

    def run_relay(self):
        report = self.relay.run(limit=16)
        self.assertEqual(report['errors'], [], report)
        return report

    def test_source_booking_survives_lost_sample_reply_and_rings_real_residents_once(self):
        bind = self.prepare('door', 'bind', {})
        self.fx.call(bind['request'], 'committed')
        invitation = self.invitation('bell', 'schedule')
        self.assertEqual({field['name'] for field in invitation['fields']}, {'due', 'deadline', 'chord'})
        prepared, booked = self.schedule()
        self.assertEqual(self.fx.state('bell')['generation'], 1)
        self.assertEqual(self.fx.state('bell')['phase'], 'queued')
        self.assertEqual(self.fx.call(prepared['request']), booked)
        self.assertEqual(self.fx.state()['size'], 1)
        exchange = driver.retained_invocation.world.exchange
        def lost_reply(database, request, **kwargs):
            receipt = exchange(database, request, **kwargs)
            if request['op'] == 'invoke' and request['command'] == 'sample':
                raise ConnectionError('lost after native commit')
            return receipt
        with patch.object(driver.retained_invocation.world, 'exchange', side_effect=lost_reply):
            with self.assertRaises(ConnectionError):
                self.sample()
        # A fresh driver process would use the same retained file. Its new physical
        # reading is irrelevant: replay preserves the admitted observation/root.
        with patch.object(driver.time, 'time_ns', side_effect=AssertionError('must not resample')):
            recovered = driver.sample(self.fx.db, Path(self.fx.temp.name) / 'physical.json',
                clock='clock', principal='driver', intent='physical')
        self.assertEqual(len(recovered['data']['messages']), 1)
        for _ in range(3):
            self.assertEqual(self.run_relay()['blocked'], [])
        self.assertEqual(self.fx.state('bell')['phase'], 'rang')
        self.assertEqual(self.fx.state('bell')['bell']['notes'], 1)
        self.assertEqual(self.fx.state('bell')['bell']['lastBy'], 'relay')
        self.assertEqual(self.fx.state('door')['heard'], 1)
        self.assertTrue(self.fx.state('door')['open'])
        light = self.fx.state('lantern')
        self.assertEqual(light['glows'], 1)
        self.assertEqual(light['lastRootPlayer'], 'driver')
        self.assertEqual(light['lastEmitterActor'], 'relay')
        self.assertEqual(light['lastDepth'], 2)
        self.assertEqual(light['lastRoot'], self.fx.state('bell')['lastRoot'])
        self.relay = message_relay.MessageRelay(Path(self.fx.temp.name) / 'relay', self.fx.db, 'relay')
        self.run_relay()
        self.assertEqual(self.sample(6000, 'equal-observation')['data'].get('messages', []), [])
        self.assertEqual(self.fx.state('lantern')['glows'], 1)

    def test_captured_reads_current_law_and_actual_completion_are_required(self):
        ready = self.prepare('bell', 'schedule', {'due': 5, 'deadline': 10, 'chord': 'C E G'})
        self.assertEqual(ready['kind'], 'ready', ready)
        before = self.fx.root('bell')
        forged = self.fx.invoke('bell', 'scheduled', {'status': 'queued', 'id': 'bell',
            'generation': 1, 'now': 0}, 'moss')
        self.fx.call(forged, 'refused')
        self.assertEqual(self.fx.root('bell'), before)
        self.fx.tick(1)
        self.assertEqual(self.fx.call(ready['request'], 'refused')['data'], 'stale read root')
        self.assertEqual(self.fx.root('bell'), before)
        denied = self.prepare('bell', 'schedule', {'due': 5, 'deadline': 10, 'chord': 'C E G'}, 'iris')
        self.assertEqual(denied['kind'], 'refused')
        clock = self.fx.root()
        revoked = {**clock['law'], 'invoke': {**clock['law']['invoke'], 'request': []}}
        self.fx.call({'op': 'law', 'object': 'clock', 'principal': 'steward', 'intent': self.fx.intent(),
            'expected': clock, 'law': revoked}, 'committed')
        ready = self.prepare('bell', 'schedule', {'due': 5, 'deadline': 10, 'chord': 'C E G'})
        self.fx.call(ready['request'], 'refused')
        self.assertEqual(self.fx.root('bell'), before)  # arm and quote roll back with refusal

    def test_atomic_source_cancellation_rebooks_generation_and_cannot_recall_a_send(self):
        self.schedule()
        cancelled = self.prepare('bell', 'cancel', {})
        self.fx.call(cancelled['request'], 'committed')
        self.assertEqual(self.fx.state('bell')['phase'], 'cancelled')
        self.assertEqual(self.fx.state()['size'], 0)
        self.schedule()
        self.assertEqual(self.fx.state('bell')['generation'], 2)
        stale_cancel = self.prepare('bell', 'cancel', {})
        self.sample()
        self.fx.call(stale_cancel['request'], 'refused')
        after_send = self.prepare('bell', 'cancel', {})
        refused = self.fx.call(after_send['request'], 'refused')
        self.assertIn('cannot be recalled', str(refused))
        self.assertEqual(self.fx.state('bell')['phase'], 'queued')
        self.run_relay()
        self.assertEqual(self.fx.state('bell')['phase'], 'rang')

    def test_revised_listener_refuses_descendant_atomically_and_retains_due_event(self):
        self.schedule()
        listener = self.fx.root('door')
        revised = {**listener['protocol'], 'revision': 2}
        self.fx.call({'op': 'reprogram', 'object': 'door', 'principal': 'builder',
            'intent': self.fx.intent(), 'expected': listener, 'protocol': revised,
            'state': listener['state']}, 'committed')
        sent = self.sample()
        before = self.fx.root('bell')
        refused = self.fx.call(self.fx.delivery(sent['data']['messages'][0], 'bell'), 'refused')
        self.assertIn('program changed', str(refused))
        self.assertEqual(self.fx.root('bell'), before)
        event = world.query(self.fx.db, {'op': 'message-event', 'principal': 'reader',
            'event': sent['data']['messages'][0]}, profile='compiled')['event']
        self.assertEqual(event['status'], 'pending')
        self.assertEqual(self.fx.state('door')['heard'], 0)
        retired = self.prepare('bell', 'retire', {})
        self.fx.call(retired['request'], 'committed')
        self.assertEqual(self.fx.state('bell')['phase'], 'retired')
        self.schedule(due=5)
        self.assertEqual(self.fx.state('bell')['generation'], 2)
        declined = self.fx.call(self.fx.delivery(sent['data']['messages'][0], 'bell'), 'committed')
        self.assertEqual(declined['data']['result']['status'], 'declined')
        self.assertEqual(declined['data'].get('messages', []), [])
        self.assertEqual(self.fx.state('bell')['phase'], 'queued')
        terminal = world.query(self.fx.db, {'op': 'message-event', 'principal': 'reader',
            'event': sent['data']['messages'][0]}, profile='compiled')['event']
        self.assertEqual(terminal['status'], 'consumed')
        self.sample(6000, 'replacement-pin')
        self.run_relay()
        self.run_relay()
        self.assertEqual(self.fx.state('door')['heard'], 1)

    def test_retired_generation_explicitly_declines_its_late_event(self):
        self.schedule()
        sent = self.sample()
        retired = self.prepare('bell', 'retire', {})
        self.fx.call(retired['request'], 'committed')
        late = self.fx.call(self.fx.delivery(sent['data']['messages'][0], 'bell'), 'committed')
        self.assertEqual(late['data']['result']['status'], 'declined')
        self.assertEqual(late['data'].get('messages', []), [])
        self.assertEqual(self.fx.state('bell')['phase'], 'retired')
        self.assertEqual(self.fx.state('bell')['bell']['notes'], 0)
        self.assertEqual(self.fx.state('door')['heard'], 0)
        terminal = world.query(self.fx.db, {'op': 'message-event', 'principal': 'reader',
            'event': sent['data']['messages'][0]}, profile='compiled')['event']
        self.assertEqual(terminal['status'], 'consumed')

    def test_expiry_is_retired_from_actual_clock_status_and_can_be_rebooked(self):
        self.schedule(deadline=5)
        before = self.fx.root('bell')
        forged = self.fx.invoke('bell', 'retired', {'status': 'absent', 'id': 'bell',
            'generation': 1, 'now': 6}, 'moss')
        self.fx.call(forged, 'refused')
        self.assertEqual(self.fx.root('bell'), before)
        premature = self.prepare('bell', 'retire', {})
        self.fx.call(premature['request'], 'refused')
        self.assertEqual(self.fx.state('bell')['phase'], 'queued')
        expired = self.sample(7000)
        self.assertEqual(expired['data'].get('messages', []), [])
        self.assertEqual(self.fx.state()['last']['status'], 'expired')
        retired = self.prepare('bell', 'retire', {})
        self.fx.call(retired['request'], 'committed')
        self.schedule(due=6, deadline=8)
        self.sample(7000, 'retry-after-expiry')
        self.run_relay()
        self.run_relay()
        self.assertEqual(self.fx.state('door')['heard'], 1)


class AppointmentRequiredInputs(unittest.TestCase):
    def test_source_required_fields_preserve_missing_wrong_kind_and_zero(self):
        material = modules('ScheduledBell') + [source('AppointmentsRequired',
            ROOT / 'conformance/fixtures/preparation')]
        compiled = native({'op': 'compile', 'modules': material, 'entry': 'checks'})
        self.assertEqual(compiled['status'], 'compiled', compiled)
        result = native({'op': 'run-data-v1', 'artifact': compiled['artifact'], 'arguments': []})
        self.assertEqual(result['status'], 'finished', result)
        for name, value in plain(result['value']).items():
            with self.subTest(check=name):
                self.assertTrue(value)


if __name__ == '__main__':
    unittest.main()
