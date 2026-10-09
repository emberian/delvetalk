"""Two makers inhabit a source-owned, separately governed evening courtyard."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_appointment_relationship as relationship
import test_appointments as appointments

ROOT = appointments.ROOT
sys.path.insert(0, str(ROOT / 'scripts'))
import affordances
import desk
import message_relay
import source_object
import source_offers
import source_store
import world
from scene import projection


def package(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


courtyard = package('courtyard_package', 'examples/evening-courtyard/package.py')
residents = package('courtyard_residents', 'protocols/resident-messages/package.py')
forge = package('courtyard_forge', 'protocols/town-forge/generate.py')
writing = package('courtyard_writing', 'protocols/source-desk/package.py')


def law(commands, managers=(), revisers=()):
    return {'profile': 'delvetalk-scoped-law', 'invoke': commands, 'read': 'public',
            'law': list(managers), 'reprogram': list(revisers)}


class EveningCourtyard(unittest.TestCase):
    def setUp(self):
        self.fx = appointments.Appointments()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.fx.call({'op': 'messages-init', 'principal': 'bootstrap', 'intent': 'registry',
                      'lineage': 'evening-courtyard', 'pendingLimit': 128}, 'committed')
        clock = source_object.load(relationship.modules('Clock'), syntax='objective-bend-object',
            constructor='physical', arguments=[source_object.data(
                {'capacity': 16, 'epochMillis': 1000, 'quantumMillis': 1000})])
        self.fx.create('clock', clock, law({'quote': ['moss'], 'request': ['moss'],
            'status': ['moss'], 'cancel': ['moss'], 'sample': ['driver'], 'tick': ['driver'],
            'page': ['moss', 'iris']}))
        bell = source_object.load(relationship.modules('ScheduledBell'), syntax='objective-bend-object',
            constructor='configured', arguments=[source_object.data({'object': 'moss/bell',
                'owner': 'moss', 'clock': 'clock', 'recipient': 'iris/door'})])
        door = residents.load('Door', {'source': 'moss/bell', 'recipient': 'lights/lantern'})
        lantern = residents.load('Lantern', {'source': 'iris/door'})
        for factory, maker, program, commands in [
                ('moss', 'moss', bell, ['arm', 'scheduled', 'cancelled', 'retired', 'wake']),
                ('iris', 'iris', door, ['bind', 'hear']),
                ('lights', 'iris', lantern, ['glow'])]:
            self.fx.create(factory, forge.object_factory(program, ['relay'], commands),
                           law({'make': [maker]}))
        self.make('moss', 'moss', 'bell')
        self.make('iris', 'iris', 'door')
        self.make('lights', 'iris', 'lantern')
        self.assertEqual(self.fx.state('iris/door')['recipient'], 'lights/lantern')
        self.relay = message_relay.MessageRelay(Path(self.fx.temp.name) / 'relay', self.fx.db, 'relay')
        places = [{'key': key, 'label': label, 'object': name, 'panel': 'main'} for key, label, name in [
            ('clock', 'The courtyard clock', 'clock'), ('bell', "Moss's bell", 'moss/bell'),
            ('door', "Iris's door", 'iris/door'), ('lantern', "Iris's lantern", 'lights/lantern')]]
        self.fx.create('courtyard', courtyard.book(places),
                       law({'note': ['moss', 'iris']}, ['steward'], ['steward']))

    def capture(self, name, invitation, principal):
        owner = world.capture_roots(self.fx.db, [name], principal=principal, profile='compiled')
        view = projection.project(owner['roots'][name]['root'], name)
        captured = source_offers.capture_observations(view, owner, database=self.fx.db,
            principal=principal, profile='compiled')
        return source_offers.capture(view,
            {key: item['root'] for key, item in captured['roots'].items()},
            references={key: item['reference'] for key, item in captured['roots'].items()})[invitation]

    def prepare(self, name, invitation, fields, principal):
        return source_offers.prepare_value(self.capture(name, invitation, principal), principal,
            self.fx.intent(), fields, database=self.fx.db)

    def make(self, factory, principal, name):
        offer = self.capture(factory, 'make', principal)
        request = source_offers.request(offer, principal, self.fx.intent(), {'name': name}, database=self.fx.db)
        receipt = self.fx.call(request, 'committed')
        self.assertEqual(self.fx.call(request), receipt)
        self.assertEqual(affordances.allocated_refs(receipt)[0]['object'], factory + '/' + name)
        if factory != 'proposals':
            self.assertEqual(self.fx.root(factory + '/' + name)['law']['reprogram'], [principal])

    def ready(self, object, invitation, fields, principal):
        prepared = self.prepare(object, invitation, fields, principal)
        self.assertEqual(prepared['kind'], 'ready', prepared)
        return prepared['request']

    def test_book_links_owned_objects_and_scheduled_visit_survives_restart(self):
        bound = self.ready('iris/door', 'bind', {}, 'iris')
        self.fx.call(bound, 'committed')
        light = self.fx.root('lights/lantern')
        private = {**light['law'], 'read': ['iris', 'relay']}
        self.fx.call({'op': 'law', 'object': 'lights/lantern', 'principal': 'iris',
            'intent': self.fx.intent(), 'expected': light, 'law': private}, 'committed')
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            self.fx.call({'op': 'inspect', 'object': 'lights/lantern', 'principal': 'moss'})
        # The shared document still offers a governed link, without acquiring
        # this neighbour's private state on behalf of its reader.
        public_book = projection.project(self.fx.root('courtyard'), 'courtyard')['data']
        self.assertIn('Iris', public_book['prose'])
        refused = self.prepare('moss/bell', 'schedule', {'due': 5, 'deadline': 10, 'chord': 'C E G'}, 'iris')
        self.assertEqual(refused['kind'], 'refused')
        arranged = self.ready('moss/bell', 'schedule', {'due': 5, 'deadline': 10, 'chord': 'C E G'}, 'moss')
        booked = self.fx.call(arranged, 'committed')
        self.assertEqual(self.fx.call(arranged), booked)
        # Every exchange is a fresh native receiver; restart the relay's custody.
        relationship.AppointmentRelationship.sample(self, 6000)
        for _ in range(3):
            report = self.relay.run(limit=16)
            self.assertEqual(report['errors'], [], report)
            self.assertEqual(report['blocked'], [], report)
        self.relay = message_relay.MessageRelay(Path(self.fx.temp.name) / 'relay', self.fx.db, 'relay')
        self.relay.run(limit=16)
        self.assertEqual(self.fx.state('moss/bell')['phase'], 'rang')
        self.assertEqual(self.fx.state('iris/door')['heard'], 1)
        light = source_object.plain(source_object.state_data(self.fx.call(
            {'op': 'inspect', 'object': 'lights/lantern', 'principal': 'iris'})))
        self.assertEqual(light['glows'], 1)
        self.assertEqual(light['lastRootPlayer'], 'driver')
        self.assertEqual(light['lastEmitterActor'], 'relay')
        self.assertEqual(light['lastDepth'], 2)
        self.assertEqual(light['lastRoot'], self.fx.state('moss/bell')['lastRoot'])
        for principal, line in [('moss', 'I arranged a chord for our return.'), ('iris', 'The light remembers its door.')]:
            self.fx.call(self.fx.invoke('courtyard', 'note', {'line': line}, principal), 'committed')
        book = self.fx.root('courtyard')
        view = projection.project(book, 'courtyard')['data']
        self.assertIn('I arranged a chord', view['prose'])
        self.assertIn('The light remembers', view['prose'])
        self.assertEqual(set(self.fx.state('courtyard')), {'conversation', 'places'})
        neighbor = self.fx.root('iris/door')
        denied = self.fx.call({'op': 'reprogram', 'object': 'iris/door', 'principal': 'moss',
            'intent': self.fx.intent(), 'expected': neighbor, 'protocol': neighbor['protocol'],
            'state': neighbor['state']}, 'refused')
        self.assertEqual(denied['data'], 'unauthorized')
        self.assertEqual(self.fx.root('iris/door'), neighbor)

    def test_shared_source_revision_requires_steward_and_preserves_living_book(self):
        self.fx.call(self.fx.invoke('courtyard', 'note', {'line': 'Our first evening.'}, 'moss'), 'committed')
        target = self.fx.root('courtyard')
        self.fx.create('proposals', writing.factory('compiler', ['moss'], reviewers=['steward']),
                       law({'make': ['moss']}))
        self.make('proposals', 'moss', 'afterglow')
        client = desk.Desk(self.fx.db, Path(self.fx.temp.name) / 'artifacts')
        candidate = self.fx.call({'op': 'inspect', 'object': 'proposals/afterglow', 'principal': 'moss'})
        entries = [{'name': item['name'], 'sourceRef': source_store.store_bytes(
                    client.artifact_store, item['source'].encode())}
                   for item in courtyard.modules(afterglow=True)]
        proposal = source_store.prepare_module_proposal(client.artifact_store,
            source_store.seal_modules(entries),
            (ROOT / 'examples/evening-courtyard/book.examples').read_bytes(),
            syntax='objective-bend-object')
        submitted = client.submit_refs('proposals/afterglow', 'moss', self.fx.intent(),
            candidate, proposal, target['state'], 'courtyard')
        self.assertEqual(submitted['kind'], 'committed', submitted)
        requested = self.fx.call({'op': 'invoke', 'object': 'proposals/afterglow',
            'principal': 'moss', 'intent': self.fx.intent(),
            'expected': submitted['data']['root'], 'command': 'requestCheck',
            'input': {}}, 'committed')['data']['root']
        work = desk.compiler_work(requested, 'proposals/afterglow', 'compiler', self.fx.db)
        self.assertIsNotNone(work)
        checked = client.check('proposals/afterglow', 'compiler', work['intent'], requested)
        self.assertEqual(checked['kind'], 'committed', checked)
        ready = checked['data']['root']
        self.assertEqual(desk.candidate_state(ready)['status'], 'ready', desk.candidate_state(ready))
        offer = self.capture('proposals/afterglow', 'release', 'steward')
        # The maker can read the proposal, but the target's current law
        # still rejects its release. Iris has no proposal read grant.
        self.fx.call(source_offers.request(offer, 'moss', self.fx.intent(), {},
            database=self.fx.db), 'refused')
        self.assertEqual(self.fx.root('courtyard'), target)
        self.assertEqual(self.fx.call({'op': 'inspect', 'object': 'proposals/afterglow',
            'principal': 'steward'}), ready)
        with self.assertRaisesRegex((ValueError, RuntimeError), 'read unauthorized'):
            source_offers.request(offer, 'iris', self.fx.intent(), {}, database=self.fx.db)
        request = source_offers.request(offer, 'steward', self.fx.intent(), {}, database=self.fx.db)
        accepted = self.fx.call(request, 'committed')
        self.assertEqual(self.fx.call(request), accepted)
        installed = self.fx.root('courtyard')
        self.assertEqual(source_object.state_data(installed), source_object.state_data(target))
        self.assertEqual(installed['law'], target['law'])
        view = projection.project(installed, 'courtyard')['data']
        self.assertIn('afterglow', view['prose'])
        self.assertIn('Our first evening.', view['prose'])
        self.assertEqual(installed['protocol'], desk.candidate_state(ready)['protocol'])

    def test_stale_observed_neighbor_pin_refuses_before_booking(self):
        arranged = self.ready('moss/bell', 'schedule', {'due': 5, 'deadline': 10, 'chord': 'C E G'}, 'moss')
        root = self.fx.root('iris/door')
        revised = {**root['protocol'], 'revision': 2}
        self.fx.call({'op': 'reprogram', 'object': 'iris/door', 'principal': 'iris',
            'intent': self.fx.intent(), 'expected': root, 'protocol': revised,
            'state': root['state']}, 'committed')
        before = self.fx.root('moss/bell')
        self.fx.call(arranged, 'refused')
        self.assertEqual(self.fx.root('moss/bell'), before)
        self.assertEqual(self.fx.state('clock')['size'], 0)


if __name__ == '__main__':
    unittest.main()
