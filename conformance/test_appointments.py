#!/usr/bin/env python3
"""Actual authored collections, explicit logical time and native durable delivery."""
import copy
import importlib.util
import json
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
import affordances
import obend_object
import propose
import spell_examples


def load_driver():
    spec = importlib.util.spec_from_file_location('appointments_driver', FIXTURES / 'clock_driver.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def modules(name):
    return [{'name': n, 'source': path.read_text()} for n, path in [
        ('Abi', ROOT / 'world/lib/prelude/Abi.obend'),
        ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
        ('Appointments', FIXTURES / 'Appointments.obend'), (name, FIXTURES / (name + '.obend'))]]


def native(request):
    result = subprocess.run([str(ROOT / '.lake/build/bin/delvetalk-obend')],
        input=json.dumps(request) + '\n', capture_output=True, text=True, timeout=30, check=True)
    return json.loads(result.stdout)


def wire(value):
    if isinstance(value, dict):
        return {'tag': 'record', 'fields': [{'name': k, 'value': wire(v)} for k, v in value.items()]}
    return {'tag': 'natural' if isinstance(value, int) else 'label', 'value': str(value)}


def plain(value):
    if value['tag'] == 'record':
        return {field['name']: plain(field['value']) for field in value['fields']}
    if value['tag'] == 'variant':
        return {'label': value['label'], **plain(value['payload'])}
    if value['tag'] == 'natural':
        return int(value['value'])
    return value['value']


def entries(xs):
    result = []
    while xs['label'] == 'cons':
        result.append(xs['head'])
        xs = xs['tail']
    return result


def law(commands):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': commands,
            'reprogram': ['builder'], 'law': ['steward']}


class Appointments(unittest.TestCase):
    lowered = {}
    constructors = {}

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

    def active(self):
        queue = self.state()['queue']
        return entries(queue['front']) + list(reversed(entries(queue['back'])))

    def create(self, name, program, authority):
        return self.call({'op': 'create', 'object': name, 'principal': 'bootstrap',
                          'intent': 'create-' + name, 'protocol': program, 'law': authority}, 'committed')

    def program(self, name, **configuration):
        # Compile the exact sealed imports, then evaluate an authored constructor
        # on checked configuration data. No source/AST specialization in Python.
        if name not in self.lowered:
            material = modules(name)
            self.lowered[name] = obend_object.lower_data_modules(material)
            compiled = native({'op': 'compile', 'modules': material, 'entry': 'configured'})
            self.assertEqual(compiled['status'], 'compiled', compiled)
            self.constructors[name] = compiled['artifact']
        protocol = copy.deepcopy(self.lowered[name])
        config = {'capacity': 16} if name == 'Clock' else {'owner': 'moss', 'clock': 'clock'}
        config.update(configuration)
        result = native({'op': 'run-data-v1', 'artifact': self.constructors[name], 'arguments': [wire(config)]})
        self.assertIn('value', result, result)
        protocol['initial']['model'] = result['value']
        return protocol

    def setup_world(self, pending_capacity=128, capacity=16):
        self.call({'op': 'messages-init', 'principal': 'bootstrap', 'intent': 'init',
                   'lineage': 'appointments-journey', 'pendingLimit': pending_capacity}, 'committed')
        self.create('clock', self.program('Clock', capacity=capacity), law({'request': ['moss', 'iris'],
                    'cancel': ['moss', 'iris'], 'tick': ['driver'], 'page': ['moss', 'iris']}))
        self.create('garden-task', self.program('Task', owner='moss'), law({'wake': ['relay']}))
        self.create('lantern-task', self.program('Task', owner='iris'), law({'wake': ['relay']}))
        self.create('digest', {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
            'hash': {'require': [], 'set': {}, 'result': ['program-digest', ['input', 'protocol']],
                     'outbox': []}}}, ['reader'])
        self.programs = {}
        for name in ('garden-task', 'lantern-task'):
            self.programs[name] = self.call(self.invoke('digest', 'hash',
                {'protocol': self.root(name)['protocol']}, 'reader'), 'committed')['data']['result']

    def invoke(self, object, command, input, principal):
        return {'op': 'invoke', 'object': object, 'command': command, 'input': input,
                'principal': principal, 'intent': self.intent(), 'expected': self.root(object)}

    def booking(self, id='garden', owner='moss', to=None, generation=None, due=5, deadline=10, **changes):
        to = to or ('garden-task' if owner == 'moss' else 'lantern-task')
        generation = self.state()['nextGeneration'] if generation is None else generation
        return self.invoke('clock', 'request', {'id': id, 'generation': generation,
            'due': due, 'deadline': deadline, 'to': to, 'recipientProgram': self.programs[to],
            'topic': 'water the garden' if owner == 'moss' else 'light the lanterns', **changes}, owner)

    def book(self, **kwargs):
        return self.call(self.booking(**kwargs), 'committed')

    def tick_request(self, now, principal='driver'):
        return self.invoke('clock', 'tick', {'now': now}, principal)

    def tick(self, now):
        return self.call(self.tick_request(now), 'committed')

    def cancel(self, id='garden', generation=1, principal='moss'):
        return self.invoke('clock', 'cancel', {'id': id, 'generation': generation}, principal)

    def delivery(self, reference, target):
        return {'op': 'deliver', 'object': target, 'event': reference,
                'principal': 'relay', 'intent': self.intent(), 'expected': self.root(target)}

    def project(self, object='clock', panel='main'):
        spec = importlib.util.spec_from_file_location('appointment_projection', ROOT / 'scene/projection.py')
        projection = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(projection)
        return projection.project(self.root(object), object, panel=panel)

    def test_two_agents_deadlines_and_explicit_ticks_drive_independent_tasks(self):
        self.setup_world()
        self.book()
        self.book(id='lanterns', owner='iris', due=6, deadline=6)
        self.assertEqual(self.tick(4)['data'].get('messages', []), [])
        self.assertEqual(self.state()['size'], 2)
        garden = self.tick(5)['data']['messages']
        lanterns = self.tick(6)['data']['messages']
        for refs, target in [(garden, 'garden-task'), (lanterns, 'lantern-task')]:
            self.assertEqual(len(refs), 1)
            self.call(self.delivery(refs[0], target), 'committed')
            self.assertEqual(self.state(target)['runs'], 1)
        self.assertEqual(self.state('garden-task')['lastTopic'], 'water the garden')
        self.assertEqual(self.state('lantern-task')['lastTick'], 6)
        self.assertEqual(self.state()['size'], 0)
        self.assertEqual(self.active(), [])

    def test_authority_monotone_time_generation_and_owner_guards(self):
        self.setup_world()
        for principal in ['moss', 'iris', 'bootstrap', 'builder']:
            self.assertEqual(self.call(self.tick_request(5, principal), 'refused')['data'], 'unauthorized')
        self.book()
        before = self.root()
        self.call(self.cancel(principal='iris'), 'refused')
        self.call(self.cancel(generation=2), 'refused')
        self.call(self.booking(), 'refused')  # active id already used
        self.assertEqual(self.root(), before)
        self.call(self.cancel(), 'committed')
        self.call(self.booking(generation=1), 'refused')
        self.book(generation=2)
        self.tick(6)
        current = self.root()
        self.assertIn('backwards', self.call(self.tick_request(5), 'refused')['data'])
        self.assertEqual(self.root(), current)
        for changes in [dict(id=''), dict(due=5), dict(due=9, deadline=8), dict(generation=99)]:
            self.call(self.booking(**changes), 'refused')

    def test_cancellation_race_and_id_reuse_cannot_recall_or_cancel_a_later_generation(self):
        self.setup_world(capacity=1)
        self.book()
        stale_tick = self.tick_request(5)
        self.call(self.cancel(), 'committed')
        self.assertEqual(self.call(stale_tick, 'refused')['data'], 'stale read root')
        self.assertEqual(self.tick(5)['data'].get('messages', []), [])
        self.book(generation=2, due=5)
        stale_cancel = self.cancel(generation=2)
        ref = self.tick(5)['data']['messages'][0]
        self.assertEqual(self.call(stale_cancel, 'refused')['data'], 'stale read root')
        self.assertIn('cannot be recalled', self.call(self.cancel(generation=2), 'refused')['data'])
        self.tick(11)
        self.call(self.delivery(ref, 'garden-task'), 'committed')  # send deadline, not delivery deadline
        self.call(self.delivery(ref, 'garden-task'), 'refused')
        self.book(generation=3, due=12, deadline=15, owner='iris')
        self.call(self.cancel(generation=2), 'refused')  # fresh root still cannot target reused id
        self.call(self.cancel(generation=3), 'refused')  # current generation but previous owner
        self.assertEqual(self.active()[0]['owner'], 'iris')
        self.call(self.cancel(generation=3, principal='iris'), 'committed')
        self.assertEqual(self.state()['nextGeneration'], 4)
        self.assertEqual(self.active(), [])

    def test_four_entry_rotation_passes_future_work_and_new_bookings_cannot_jump_queue(self):
        self.setup_world()
        for number in range(12):
            self.book(id=str(number), owner='moss' if number < 8 else 'iris',
                      due=50 if number < 4 else 5, deadline=60)
        self.assertEqual(self.tick(5)['data'].get('messages', []), [])
        self.assertEqual([x['id'] for x in self.active()][:4], ['4', '5', '6', '7'])
        first = self.tick(5)
        self.assertEqual(len(first['data']['messages']), 4)
        self.book(id='late', due=5)
        second = self.tick(5)
        self.assertEqual(len(second['data']['messages']), 4)
        for receipt, target, start in [(first, 'garden-task', 4), (second, 'lantern-task', 8)]:
            for ordinal, ref in enumerate(receipt['data']['messages']):
                evidence = world.query(self.db, {'op': 'message-event', 'principal': 'reader', 'event': ref},
                                       profile='compiled')['event']['evidence']
                self.assertEqual(evidence['slot'], ordinal)
                self.assertEqual(evidence['payload']['id'], str(start + ordinal))
                self.call(self.delivery(ref, target), 'committed')
            self.assertEqual(self.state(target)['runs'], 4)
        self.assertEqual(self.tick(5)['data'].get('messages', []), [])  # future four rotate
        self.assertEqual(len(self.tick(5)['data']['messages']), 1)  # late now gets its turn
        self.assertEqual(self.state()['size'], 4)

    def test_configured_capacity_is_reclaimed_without_retaining_terminal_tombstones(self):
        self.setup_world(capacity=3)
        for number in range(3):
            self.book(id=str(number))
        before = self.root()
        self.call(self.booking(id='full'), 'refused')
        self.assertEqual(self.root(), before)
        self.call(self.cancel(id='1', generation=2), 'committed')
        self.book(id='1', generation=4)
        self.call(self.cancel(id='1', generation=2), 'refused')
        self.assertEqual(len(self.tick(5)['data']['messages']), 3)
        self.assertEqual(self.state()['size'], 0)
        self.assertEqual(self.active(), [])
        self.book(id='0', due=5)
        self.assertEqual(self.state()['nextGeneration'], 6)

    def test_twenty_four_entry_configuration_projects_pages_and_emits_a_bounded_batch(self):
        self.setup_world(capacity=24)
        for number in range(24):
            self.book(id=str(number))
        self.assertEqual(self.state()['size'], 24)
        self.assertEqual(len(self.project()['children']), 4)
        self.call(self.invoke('clock', 'page', {'offset': 20}, 'moss'), 'committed')
        self.assertEqual([c['key'] for c in self.project()['children']], ['20', '21', '22', '23'])
        self.call(self.booking(id='full'), 'refused')
        self.assertEqual(len(self.tick(5)['data']['messages']), 4)
        self.assertEqual(self.state()['size'], 20)
        self.assertEqual(self.state()['offset'], 0)

    def test_expired_work_emits_nothing_and_cancelled_bad_descriptor_cannot_poison_ticks(self):
        self.setup_world()
        self.book(deadline=5)
        self.assertEqual(self.tick(6)['data'].get('messages', []), [])
        self.assertEqual(self.state()['last'], {'id': 'garden', 'generation': 1, 'status': 'expired'})
        self.assertEqual(self.state()['size'], 0)
        self.book(due=6, recipientProgram='bad hash')
        before = self.root()
        self.call(self.tick_request(6), 'refused')
        self.assertEqual(self.root(), before)
        self.call(self.cancel(generation=2), 'committed')
        self.assertEqual(self.tick(6)['data'].get('messages', []), [])

    def test_pending_capacity_refuses_whole_batch_without_skipping_work(self):
        self.setup_world(pending_capacity=3)
        for number in range(4):
            self.book(id=str(number), owner='iris' if number == 3 else 'moss')
        before = self.root()
        self.assertIn('capacity', self.call(self.tick_request(5), 'refused')['data'])
        self.assertEqual(self.root(), before)
        self.assertEqual(world.query(self.db, {'op': 'messages-pending', 'principal': 'reader'},
                                    profile='compiled')['pending'], {})
        self.call(self.cancel(id='3', generation=4, principal='iris'), 'committed')
        refs = self.tick(5)['data']['messages']
        self.assertEqual(len(refs), 3)
        for ref in refs:
            self.call(self.delivery(ref, 'garden-task'), 'committed')
        self.assertEqual(self.state('garden-task')['runs'], 3)

    def test_recipient_revision_returns_exact_refusal_and_leaves_inspectable_queue(self):
        self.setup_world()
        self.book()
        original = self.root('garden-task')
        changed = {**original['protocol'], 'revision': 2}
        self.call({'op': 'reprogram', 'object': 'garden-task', 'principal': 'builder',
            'intent': self.intent(), 'expected': original, 'protocol': changed,
            'state': original['state']}, 'committed')
        request = self.tick_request(5)
        refused = self.call(request, 'refused')
        self.assertEqual(refused['data'], 'message recipient program changed before emission')
        self.assertEqual(self.call(request), refused)
        self.assertEqual(self.root(), request['expected'])
        view = self.project()
        self.assertIn('retained receipt', view['data']['prose'])
        self.assertEqual(view['data']['title'], 'Queued appointments')
        self.assertEqual(view['children'][0]['object'], 'garden-task')
        self.call(self.cancel(), 'committed')
        self.programs['garden-task'] = self.call(self.invoke('digest', 'hash', {'protocol': changed}, 'reader'), 'committed')['data']['result']
        self.book()
        self.call(self.delivery(self.tick(5)['data']['messages'][0], 'garden-task'), 'committed')

    def test_relay_current_authority_and_owner_binding_remain_separate_from_driver(self):
        self.setup_world()
        self.book(to='lantern-task')
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
        self.assertEqual(self.state()['size'], 0)
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

    def test_terminal_driver_retries_the_retained_tick_after_cancellation(self):
        self.setup_world()
        self.book()
        self.call(self.cancel(), 'committed')
        attempt = Path(self.temp.name) / 'terminal-tick.json'
        command = [sys.executable, str(FIXTURES / 'clock_driver.py'), str(self.db), str(attempt),
                   '--principal', 'driver', '--intent', 'terminal-5', '--now', '5']
        first = subprocess.run(command, capture_output=True, text=True, check=True, timeout=20)
        receipt = world.wire_loads(first.stdout)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(receipt['data'].get('messages', []), [])
        retained = attempt.read_bytes()
        self.book(due=5)
        second = subprocess.run(command, capture_output=True, text=True, check=True, timeout=20)
        self.assertEqual(world.wire_loads(second.stdout), receipt)
        self.assertEqual(attempt.read_bytes(), retained)
        self.assertEqual(self.state()['size'], 1)  # retry did not target the later generation

    def test_killed_tick_reply_recovers_without_duplicate_scheduled_send(self):
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
        self.assertEqual(self.state()['size'], 0)
        ref = receipt['data']['messages'][0]
        evidence = world.query(self.db, {'op': 'message-event', 'principal': 'reader', 'event': ref},
                               profile='compiled')['event']['evidence']
        self.assertEqual(evidence['sourcePreimage'], request['expected'])
        self.assertEqual(evidence['source'], 'clock')
        self.assertEqual(evidence['originatingPrincipal'], 'driver')
        self.assertEqual(evidence['payload']['owner'], 'moss')
        self.assertEqual(evidence['payload']['id'], 'garden')
        self.assertEqual(evidence['payload']['generation'], 1)
        self.assertEqual(evidence['payload']['tick'], 5)
        self.call(self.delivery(ref, 'garden-task'), 'committed')
        self.assertEqual(self.tick(5)['data'].get('messages', []), [])

    def test_source_menu_books_cancels_and_paginates_more_than_four_entries(self):
        self.setup_world()
        before = self.root()
        view = self.project()
        card = affordances.card(view)
        self.assertEqual(view['data']['actions']['book']['input'], {'generation': 1})
        self.assertEqual({f['name'] for f in card['actions'][0]['fields']},
                         {'id', 'due', 'deadline', 'to', 'recipientProgram', 'topic'})
        request = affordances.request(view, card['actions'][0]['id'], 'moss', self.intent(), {
            'id': 'night', 'due': 5, 'deadline': 8, 'to': 'garden-task',
            'recipientProgram': self.programs['garden-task'], 'topic': 'water the night garden'})
        self.assertEqual(self.root(), before)
        self.call(request, 'committed')
        for number in range(1, 7):
            self.book(id=str(number))
        first = self.project()
        self.assertEqual(len(first['children']), 4)
        next_action = next(a for a in affordances.card(first)['actions'] if a['command'] == 'page')
        self.call(affordances.request(first, next_action['id'], 'moss', self.intent()), 'committed')
        second = self.project()
        self.assertEqual([c['key'] for c in second['children']], ['4', '5', '6'])
        self.assertEqual(second['data']['actions']['a']['input'], {'id': '4', 'generation': 5})
        before = self.root()
        action = next(a for a in affordances.card(second)['actions'] if a['command'] == 'cancel')
        self.call(affordances.request(second, action['id'], 'iris', self.intent()), 'refused')
        self.assertEqual(self.root(), before)
        self.call(affordances.request(second, action['id'], 'moss', self.intent()), 'committed')
        self.assertEqual(self.state()['offset'], 0)
        self.assertEqual([x['id'] for x in self.active()], ['night', '1', '2', '3', '5', '6'])
        self.assertEqual(self.project()['data']['actions']['book']['input'], {'generation': 8})

    def test_task_view_exposes_activity_and_clock_without_direct_wake(self):
        self.setup_world()
        before = self.root('garden-task')
        waiting = self.project('garden-task')
        self.assertEqual(waiting['data']['title'], 'Waiting for an appointment')
        self.assertEqual(affordances.card(waiting)['actions'], [])
        self.assertEqual(waiting['children'][0]['object'], 'clock')
        self.assertEqual(self.project('garden-task', 'owner')['data']['prose'], 'moss')
        self.assertEqual(self.root('garden-task'), before)
        self.book()
        self.call(self.delivery(self.tick(5)['data']['messages'][0], 'garden-task'), 'committed')
        current = self.root('garden-task')
        active = self.project('garden-task', 'activity')
        self.assertEqual(active['data']['title'], 'Appointment received')
        self.assertEqual(active['data']['prose'], 'water the garden')
        self.assertEqual(active['data']['actions'], {})
        self.assertEqual(self.state('garden-task')['lastId'], 'garden')
        self.assertEqual(self.root('garden-task'), current)

    def test_examples_beside_source_run_through_receiving(self):
        outcomes = propose.run_scenarios(self.program('Clock'),
            spell_examples.parse((FIXTURES / 'Clock.examples').read_text()), profile='compiled')
        self.assertEqual([outcome['failures'] for outcome in outcomes], [[]])


if __name__ == '__main__':
    unittest.main()
