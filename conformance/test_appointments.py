#!/usr/bin/env python3
"""Source-owned logical time, bounded appointments and native message delivery."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'protocols/appointments'
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'syntaxes'))
import world
import source_bundle
import source_packages
import translate
import affordances


def load_driver():
    spec = importlib.util.spec_from_file_location('appointments_driver', FIXTURES / 'clock_driver.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def protocol(name, **initial):
    result = source_bundle.load(FIXTURES / (name.lower() + '.binding.json'),
                                [(name, FIXTURES / (name + '.obend'))])
    fields = result['initial']['model']['fields']
    for key, value in initial.items():
        next(field for field in fields if field['name'] == key)['value'] = {'tag': 'label', 'value': value}
    return result


def plain(value):
    if value['tag'] == 'record':
        return {field['name']: plain(field['value']) for field in value['fields']}
    if value['tag'] == 'natural':
        return int(value['value'])
    return value['value']


def law(commands):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': commands,
            'reprogram': ['builder'], 'law': ['steward']}


class Appointments(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / '.lake/build/bin/delvetalk-compiled').exists(),
                        'Build compiled host first; tests must not spawn native compilers')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'world.json'
        self.serial = 0

    def call(self, request, expected=None):
        receipt = world.exchange(self.db, request, profile='compiled')
        if expected is not None:
            self.assertEqual(receipt['kind'], expected, receipt)
        return receipt

    def intent(self):
        self.serial += 1
        return 'attempt-' + str(self.serial)

    def root(self, name='clock'):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def state(self, name='clock'):
        return plain(self.root(name)['state']['model'])

    def create(self, name, program, authority):
        return self.call({'op': 'create', 'object': name, 'principal': 'bootstrap',
                          'intent': 'create-' + name, 'protocol': program, 'law': authority}, 'committed')

    def program(self, name, **initial):
        return protocol(name, **initial)

    def setup_world(self, capacity=128):
        self.call({'op': 'messages-init', 'principal': 'bootstrap', 'intent': 'init',
                   'lineage': 'appointments-journey', 'pendingLimit': capacity}, 'committed')
        self.create('clock', self.program('Clock'), law({'request': ['moss', 'iris'],
                    'cancel': ['moss', 'iris'], 'tick': ['driver']}))
        self.create('garden-task', self.program('Task', owner='moss'), law({'wake': ['relay']}))
        self.create('lantern-task', self.program('Task', owner='iris'), law({'wake': ['relay']}))
        self.create('digest', {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
            'hash': {'require': [], 'set': {}, 'result': ['program-digest', ['input', 'protocol']],
                     'outbox': []}}}, ['reader'])
        self.programs = {}
        for name in ('garden-task', 'lantern-task'):
            r = self.invoke('digest', 'hash', {'protocol': self.root(name)['protocol']}, 'reader')
            self.programs[name] = self.call(r, 'committed')['data']['result']

    def invoke(self, object, command, input, principal):
        return {'op': 'invoke', 'object': object, 'command': command, 'input': input,
                'principal': principal, 'intent': self.intent(), 'expected': self.root(object)}

    def booking(self, slot=0, owner='moss', to=None, generation=1, due=5, deadline=10, **changes):
        to = to or ('garden-task' if owner == 'moss' else 'lantern-task')
        return self.invoke('clock', 'request', {'slot': slot, 'generation': generation,
            'due': due, 'deadline': deadline, 'to': to, 'recipientProgram': self.programs[to],
            'topic': 'water the garden' if owner == 'moss' else 'light the lanterns', **changes}, owner)

    def book(self, **kwargs):
        return self.call(self.booking(**kwargs), 'committed')

    def tick_request(self, now, principal='driver'):
        return self.invoke('clock', 'tick', {'now': now}, principal)

    def tick(self, now):
        return self.call(self.tick_request(now), 'committed')

    def cancel(self, slot=0, generation=1, principal='moss'):
        return self.invoke('clock', 'cancel', {'slot': slot, 'generation': generation}, principal)

    def delivery(self, reference, target):
        return {'op': 'deliver', 'object': target, 'event': reference,
                'principal': 'relay', 'intent': self.intent(), 'expected': self.root(target)}

    def test_two_agents_deadlines_and_explicit_ticks_drive_independent_tasks(self):
        self.setup_world()
        self.book(slot=0)
        self.book(slot=4, owner='iris', due=6, deadline=6)
        self.assertEqual(self.tick(4)['data'].get('messages', []), [])
        self.assertEqual(self.state()['a']['status'], 'queued')
        self.assertEqual(self.tick(5)['data'].get('messages', []), [])  # second half not yet due
        garden = self.tick(5)['data']['messages']
        self.assertEqual(len(garden), 1)
        lanterns = self.tick(6)['data']['messages']
        self.assertEqual(len(lanterns), 1)
        for refs, target in [(garden, 'garden-task'), (lanterns, 'lantern-task')]:
            self.call(self.delivery(refs[0], target), 'committed')
            self.assertEqual(self.state(target)['runs'], 1)
        self.assertEqual(self.state('garden-task')['lastTopic'], 'water the garden')
        self.assertEqual(self.state('lantern-task')['lastTick'], 6)
        self.assertEqual(self.state()['a']['status'], 'sent')
        self.assertEqual(self.state()['e']['status'], 'sent')

    def test_authority_monotone_time_generation_and_owner_guards(self):
        self.setup_world()
        for principal in ['moss', 'iris', 'bootstrap', 'builder']:
            self.assertEqual(self.call(self.tick_request(5, principal), 'refused')['data'], 'unauthorized')
        self.book()
        before = self.root()
        self.call(self.cancel(principal='iris'), 'refused')
        self.call(self.cancel(generation=2), 'refused')
        self.call(self.booking(generation=2), 'refused')
        self.assertEqual(self.root(), before)
        self.call(self.cancel(), 'committed')
        self.call(self.booking(generation=1), 'refused')
        self.book(generation=2)
        self.tick(6)
        current = self.root()
        self.assertIn('backwards', self.call(self.tick_request(5), 'refused')['data'])
        self.assertEqual(self.root(), current)
        for changes in [dict(slot=8), dict(due=5), dict(due=9, deadline=8)]:
            self.call(self.booking(slot=1, **{k: v for k, v in changes.items() if k != 'slot'})
                      if 'slot' not in changes else self.booking(**changes), 'refused')

    def test_cancellation_wins_before_send_and_cannot_recall_an_admitted_send(self):
        self.setup_world()
        self.book()
        stale_tick = self.tick_request(5)
        self.call(self.cancel(), 'committed')
        self.assertEqual(self.call(stale_tick, 'refused')['data'], 'stale read root')
        self.assertEqual(self.tick(5)['data'].get('messages', []), [])
        self.book(generation=2, due=5)
        self.tick(5)  # other half
        stale_cancel = self.cancel(generation=2)
        sent = self.tick(5)
        ref = sent['data']['messages'][0]
        self.assertEqual(self.call(stale_cancel, 'refused')['data'], 'stale read root')
        self.assertIn('cannot be recalled', self.call(self.cancel(generation=2), 'refused')['data'])
        self.tick(11)  # deadlines bound admission of sends, not later relay delivery
        self.call(self.delivery(ref, 'garden-task'), 'committed')
        self.assertEqual(self.state('garden-task')['runs'], 1)
        self.call(self.delivery(ref, 'garden-task'), 'refused')
        self.book(generation=3, due=12, deadline=15)
        self.call(self.cancel(generation=2), 'refused')
        self.assertEqual(self.state()['a']['status'], 'queued')

    def test_four_slot_batches_alternate_without_starving_the_second_half(self):
        self.setup_world()
        for slot in range(8):
            self.book(slot=slot, owner='moss' if slot < 4 else 'iris')
        first = self.tick(5)
        self.assertEqual(len(first['data']['messages']), 4)
        self.assertEqual(self.state()['cursor'], 4)
        # Rebooking an early slot cannot jump ahead of the later half.
        self.book(slot=0, generation=2, due=5)
        second = self.tick(5)
        self.assertEqual(len(second['data']['messages']), 4)
        self.assertEqual(self.state()['cursor'], 0)
        self.assertEqual(self.state()['a']['status'], 'queued')
        self.assertTrue(all(self.state()[key]['status'] == 'sent' for key in 'bcdefgh'))
        # All eight messages have distinct native identities and slot ordinals.
        for receipt, target, offset in [(first, 'garden-task', 0), (second, 'lantern-task', 4)]:
            self.assertEqual(len({ref['id'] for ref in receipt['data']['messages']}), 4)
            for ordinal, ref in enumerate(receipt['data']['messages']):
                evidence = world.query(self.db, {'op': 'message-event', 'principal': 'reader', 'event': ref},
                                       profile='compiled')['event']['evidence']
                self.assertEqual(evidence['slot'], ordinal)
                self.assertEqual(evidence['payload']['slot'], offset + ordinal)
                self.call(self.delivery(ref, target), 'committed')
            self.assertEqual(self.state(target)['runs'], 4)
        self.assertEqual(len(self.tick(5)['data']['messages']), 1)
        self.assertEqual(self.tick(5)['data'].get('messages', []), [])

    def test_explicit_migration_rejects_old_two_slot_cursor_before_emitting(self):
        self.setup_world()
        self.book(slot=7)
        for cursor in (2, 6):
            root = self.root()
            migrated = copy.deepcopy(root['state'])
            next(field for field in migrated['model']['fields'] if field['name'] == 'cursor')['value']['value'] = str(cursor)
            # The legacy inline root stays the exact preimage. Compact the
            # replacement's repeated source so explicit migration fits the wire.
            candidate = copy.deepcopy(root['protocol'])
            if 'sourcePackages' not in candidate:
                modules = candidate['commands']['tick']['transition']['package']['modules']
                candidate['sourcePackages'] = {'resident': source_packages.table(modules)}
                for command in candidate['commands'].values():
                    package = command['transition']['package']
                    command['transition']['package'] = source_packages.selector(package['entry'])
            self.call({'op': 'reprogram', 'object': 'clock', 'principal': 'builder',
                'intent': self.intent(), 'expected': root, 'protocol': candidate,
                'state': migrated}, 'committed')
            before = self.root()
            self.assertIn('migration requires cursor 0 or 4', self.call(self.tick_request(5), 'refused')['data'])
            self.assertEqual(self.root(), before)
            self.assertEqual(world.query(self.db, {'op': 'messages-pending', 'principal': 'reader'},
                                        profile='compiled')['pending'], {})
        root = self.root()
        migrated = copy.deepcopy(root['state'])
        next(field for field in migrated['model']['fields'] if field['name'] == 'cursor')['value']['value'] = '4'
        self.call({'op': 'reprogram', 'object': 'clock', 'principal': 'builder',
            'intent': self.intent(), 'expected': root, 'protocol': root['protocol'],
            'state': migrated}, 'committed')
        receipt = self.tick(5)
        self.assertEqual(len(receipt['data']['messages']), 1)
        self.assertEqual(self.state()['h']['status'], 'sent')

    def test_expired_work_emits_nothing_and_cancelled_bad_descriptor_cannot_poison_ticks(self):
        self.setup_world()
        self.book(deadline=5)
        expired = self.tick(6)
        self.assertEqual(expired['data'].get('messages', []), [])
        self.assertEqual(self.state()['a']['status'], 'expired')
        self.book(generation=2, due=6, recipientProgram='bad hash')
        self.tick(6)  # bad descriptor in other half is not inspected or emitted
        before = self.root()
        self.call(self.tick_request(6), 'refused')
        self.assertEqual(self.root(), before)
        self.call(self.cancel(generation=2), 'committed')
        self.assertEqual(self.tick(6)['data'].get('messages', []), [])

    def test_pending_capacity_refuses_the_whole_batch_without_skipping_work(self):
        self.setup_world(capacity=3)
        for slot in range(4):
            self.book(slot=slot, owner='iris' if slot == 3 else 'moss')
        before = self.root()
        self.assertIn('capacity', self.call(self.tick_request(5), 'refused')['data'])
        self.assertEqual(self.root(), before)
        pending = world.query(self.db, {'op': 'messages-pending', 'principal': 'reader'}, profile='compiled')
        self.assertEqual(pending['pending'], {})
        self.call(self.cancel(slot=3, principal='iris'), 'committed')
        refs = self.tick(5)['data']['messages']
        self.assertEqual(len(refs), 3)
        for ref in refs:
            self.call(self.delivery(ref, 'garden-task'), 'committed')
        self.assertEqual(self.state('garden-task')['runs'], 3)

    def test_recipient_revision_blocks_send_until_owner_cancels_and_rebooks(self):
        self.setup_world()
        self.book()
        original = self.root('garden-task')
        changed = copy.deepcopy(original['protocol'])
        changed['revision'] = 2
        self.call({'op': 'reprogram', 'object': 'garden-task', 'principal': 'builder',
            'intent': self.intent(), 'expected': original, 'protocol': changed,
            'state': original['state']}, 'committed')
        before = self.root()
        self.assertIn('program changed', self.call(self.tick_request(5), 'refused')['data'])
        self.assertEqual(self.root(), before)
        self.call(self.cancel(), 'committed')
        self.programs['garden-task'] = self.call(self.invoke('digest', 'hash', {'protocol': changed}, 'reader'), 'committed')['data']['result']
        self.book(generation=2)
        refs = self.tick(5)['data']['messages']
        self.call(self.delivery(refs[0], 'garden-task'), 'committed')

    def test_relay_authority_and_owner_binding_are_separate_from_driver_authority(self):
        self.setup_world()
        self.book(to='lantern-task')  # moss cannot make iris's task act on moss's appointment
        ref = self.tick(5)['data']['messages'][0]
        before = self.root('lantern-task')
        request = self.delivery(ref, 'lantern-task')
        request['principal'] = 'driver'
        self.assertEqual(self.call(request, 'refused')['data'], 'unauthorized')
        self.assertIn('source refused', self.call(self.delivery(ref, 'lantern-task'), 'refused')['data'])
        self.assertEqual(self.root('lantern-task'), before)

    def test_driver_retains_exact_tick_and_never_refreshes_a_stale_attempt(self):
        self.setup_world()
        self.book()
        driver = load_driver()
        attempt = Path(self.temp.name) / 'driver-tick.json'
        first = driver.tick(self.db, attempt, clock='clock', principal='driver', intent='driver-5', now=5)
        self.assertEqual(first['kind'], 'committed')
        self.assertEqual(driver.tick(self.db, attempt, clock='clock', principal='driver', intent='driver-5', now=5), first)
        self.assertEqual(self.state()['cursor'], 4)
        with self.assertRaisesRegex(ValueError, 'different custody or explicit inputs'):
            driver.tick(self.db, attempt, clock='clock', principal='driver', intent='driver-5', now=6)
        request = self.tick_request(6)
        stale = Path(self.temp.name) / 'stale-tick.json'
        stale.write_text(world.wire_dumps({'profile': 'compiled', 'database': str(self.db.resolve()), 'request': request}))
        self.tick(7)
        refused = driver.tick(self.db, stale, clock='clock', principal='driver', intent=request['intent'], now=6)
        self.assertEqual(refused['data'], 'stale read root')
        self.assertEqual(driver.tick(self.db, stale, clock='clock', principal='driver', intent=request['intent'], now=6), refused)
        self.assertEqual(world.wire_loads(stale.read_text())['request'], request)

    def test_killed_tick_reply_recovers_exact_request_without_duplicate_scheduled_send(self):
        self.setup_world()
        self.book()
        attempt = Path(self.temp.name) / 'durable-tick.json'
        script = """import os,signal,sys
sys.path.insert(0,sys.argv[1]);import clock_driver
replace=clock_driver.world.os.replace
def commit(a,b):
 replace(a,b)
 if os.path.realpath(b) == os.path.realpath(sys.argv[2]):
  os.kill(os.getpid(),signal.SIGKILL)
clock_driver.world.os.replace=commit
clock_driver.tick(sys.argv[2],sys.argv[3],clock='clock',principal='driver',intent='uncertain-tick',now=5)
"""
        child = subprocess.run([sys.executable, '-c', script, str(FIXTURES), str(self.db), str(attempt)], capture_output=True)
        self.assertEqual(child.returncode, -9, child.stderr)
        request = world.wire_loads(attempt.read_text())['request']
        receipt = load_driver().tick(self.db, attempt, clock='clock', principal='driver', intent='uncertain-tick', now=5)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(len(receipt['data']['messages']), 1)
        self.assertEqual(self.call(request), receipt)
        self.assertEqual(self.state()['cursor'], 4)
        ref = receipt['data']['messages'][0]
        observed = world.query(self.db, {'op': 'message-event', 'principal': 'reader', 'event': ref}, profile='compiled')
        evidence = observed['event']['evidence']
        self.assertEqual(evidence['sourcePreimage'], request['expected'])
        self.assertEqual(evidence['source'], 'clock')
        self.assertEqual(evidence['originatingPrincipal'], 'driver')
        self.assertEqual(evidence['payload']['owner'], 'moss')
        self.assertEqual(evidence['payload']['generation'], 1)
        self.assertEqual(evidence['payload']['tick'], 5)
        delivered = self.call(self.delivery(ref, 'garden-task'), 'committed')
        self.assertEqual(delivered['data']['result']['runs'], 1)
        for _ in range(4):
            self.assertEqual(self.tick(5)['data'].get('messages', []), [])


class AuthoredAppointmentMenus(Appointments):
    """Run the same receiving contract through actual @3 source-authored objects."""
    lowered_programs = {}

    def program(self, name, **initial):
        source = (FIXTURES / (name + '.obend')).read_text()
        if name == 'Task':
            source = source.replace('owner: "moss"', 'owner: "' + initial.get('owner', 'moss') + '"')
        key = (name, source)
        if key not in self.lowered_programs:
            self.lowered_programs[key] = translate.translate('objective-bend-spell@3', source.encode())['lowered']
        return copy.deepcopy(self.lowered_programs[key])

    def project(self, object='clock', panel='main'):
        spec = importlib.util.spec_from_file_location('appointment_projection', ROOT / 'scene/projection.py')
        projection = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(projection)
        return projection.project(self.root(object), object, panel=panel)

    def test_slot_panels_offer_exact_generation_booking_and_owner_cancellation(self):
        self.setup_world()
        before = self.root()
        view = self.project(panel='h')
        self.assertEqual(view['data']['title'], 'empty')
        self.assertEqual(view['data']['actions']['book']['input'], {'slot': 7, 'generation': 1})
        card = affordances.card(view)
        self.assertEqual({f['name'] for f in card['actions'][0]['fields']},
                         {'due', 'deadline', 'to', 'recipientProgram', 'topic'})
        request = affordances.request(view, card['actions'][0]['id'], 'moss', self.intent(), {
            'due': 5, 'deadline': 8, 'to': 'garden-task',
            'recipientProgram': self.programs['garden-task'], 'topic': 'water the night garden'})
        self.assertEqual(self.root(), before)  # pure view and request preparation
        self.call(request, 'committed')
        booked = self.root()
        # Exact numeric status remains independently available through read-only inspection.
        self.assertEqual({key: self.state()['h'][key] for key in ('generation', 'due', 'deadline', 'status')},
                         {'generation': 1, 'due': 5, 'deadline': 8, 'status': 'queued'})
        observed = self.project(panel='h')
        self.assertEqual(observed['data']['title'], 'queued')
        self.assertEqual(set(observed['data']['actions']), {'cancel'})
        self.assertEqual(observed['data']['actions']['cancel']['input'], {'slot': 7, 'generation': 1})
        self.assertEqual(observed['children'][0]['object'], 'garden-task')
        self.assertEqual(self.root(), booked)
        action = affordances.card(observed)['actions'][0]['id']
        self.call(affordances.request(observed, action, 'iris', self.intent()), 'refused')
        self.assertEqual(self.root(), booked)
        self.call(affordances.request(observed, action, 'moss', self.intent()), 'committed')
        cancelled = self.project(panel='h')
        self.assertEqual(cancelled['data']['title'], 'cancelled')
        self.assertEqual(cancelled['data']['actions']['book']['input'], {'slot': 7, 'generation': 2})

    def test_refused_tick_retains_exact_reason_and_menu_never_claims_a_send(self):
        self.setup_world()
        self.book()
        recipient = self.root('garden-task')
        changed = {**recipient['protocol'], 'revision': 2}
        self.call({'op': 'reprogram', 'object': 'garden-task', 'principal': 'builder',
            'intent': self.intent(), 'expected': recipient, 'protocol': changed,
            'state': recipient['state']}, 'committed')
        tick = self.tick_request(5)
        refusal = self.call(tick, 'refused')
        self.assertEqual(refusal['data'], 'message recipient program changed before emission')
        self.assertEqual(self.call(tick), refusal)
        view = self.project(panel='a')
        self.assertEqual(view['data']['title'], 'queued')
        self.assertIn('retained receipt', view['data']['prose'])
        self.assertEqual(view['children'][0]['object'], 'garden-task')
        self.assertEqual(self.root(), tick['expected'])
        self.assertEqual(world.query(self.db, {'op': 'messages-pending', 'principal': 'reader'},
                                    profile='compiled')['pending'], {})

    def test_task_view_exposes_activity_and_clock_without_offering_direct_wake(self):
        self.setup_world()
        before = self.root('garden-task')
        waiting = self.project('garden-task')
        self.assertEqual(waiting['data']['title'], 'Waiting for an appointment')
        self.assertEqual(affordances.card(waiting)['actions'], [])
        self.assertEqual(waiting['children'][0]['object'], 'clock')
        self.assertEqual(self.project('garden-task', 'owner')['data']['prose'], 'moss')
        self.assertEqual(self.root('garden-task'), before)
        self.book()
        ref = self.tick(5)['data']['messages'][0]
        self.call(self.delivery(ref, 'garden-task'), 'committed')
        current = self.root('garden-task')
        active = self.project('garden-task', 'activity')
        self.assertEqual(active['data']['title'], 'Appointment received')
        self.assertEqual(active['data']['prose'], 'water the garden')
        self.assertEqual(active['data']['actions'], {})
        self.assertEqual(self.state('garden-task')['lastGeneration'], 1)
        self.assertEqual(self.state('garden-task')['lastTick'], 5)
        self.assertEqual(self.root('garden-task'), current)


if __name__ == '__main__':
    unittest.main()
