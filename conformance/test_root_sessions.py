"""Fresh source sessions allocate under current law and retain exact post context."""
from functools import lru_cache
import importlib.util
from pathlib import Path
import tempfile
import unittest
from conformance.test_root_directory import ROOT, door, garden_protocol
from conformance.test_document_conversation import plain
from scene import projection
import resident_store
import source_offers

spec = importlib.util.spec_from_file_location('root_session_package', ROOT / 'protocols/root-directory/package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
IRIS, MOSS, SERVICE = 'did:plc:iris', 'did:plc:moss', 'session-service'


@lru_cache(maxsize=1)
def factory():
    return package.factory(package.entry(), [door()], welcome='welcome')


class RootSessions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'sessions.sqlite'
        self.receiver = resident_store.Resident(self.path)
        self.addCleanup(lambda: self.receiver.close())
        self.serial = 0
        for identity, program, law in [('sessions', factory(), [SERVICE]),
                                       ('garden', garden_protocol(), ['steward'])]:
            self.exchange({'op': 'create', 'object': identity, 'principal': 'operator',
                'intent': 'create-' + identity, 'protocol': program, 'law': law})

    def exchange(self, request, kind='committed'):
        result = self.receiver.exchange(request)
        self.assertEqual(result['kind'], kind, result)
        return result

    def root(self, identity):
        return self.receiver.exchange({'op': 'inspect', 'object': identity, 'principal': 'reader'})

    def offered(self, identity, token, actor, intent, fields):
        owner = self.root(identity)
        view = projection.project(owner, identity)
        roots = {identity: owner, 'garden': self.root('garden')}
        return source_offers.prepare(source_offers.capture(view, roots)[token], actor, intent, fields)

    def opening(self, actor=IRIS, key='first', intent='open-first', service=SERVICE):
        return self.offered('sessions', 'make', service, intent, {
            'author': actor, 'originUri': 'at://' + actor + '/app.bsky.feed.post/' + key,
            'originCid': 'bafyre' + key})

    def invoke(self, identity, command, fields, actor, kind='committed'):
        self.serial += 1
        return self.exchange({'op': 'invoke', 'object': identity, 'principal': actor,
            'intent': 'invoke-' + str(self.serial), 'expected': self.root(identity),
            'command': command, 'input': fields}, kind)

    def test_source_allocates_ready_session_exact_origin_and_selected_membership_followup(self):
        ready = self.opening()
        self.assertEqual(ready['kind'], 'ready')
        self.assertEqual([call['command'] for call in ready['request']['calls']], ['make', 'begin', 'setDoor'])
        receipt = self.exchange(ready['request'])
        self.assertEqual(set(receipt['data']['allocated']), {'sessions/session-1'})
        self.assertEqual(self.receiver.exchange(ready['request']), receipt)
        result = receipt['data']['results'][0]
        self.assertEqual(result['session'], 'sessions/session-1')
        self.assertEqual(result['followup'], {'enabled': True, 'object': 'welcome', 'offer': 'enroll',
                                            'fields': {'did': IRIS, 'proof': 'bafyrefirst'}})
        child = self.root(result['session'])
        state = plain(child['state']['model'])
        self.assertEqual(state['origin'], {key: result[key] for key in ('author', 'originUri', 'originCid')})
        self.assertEqual(state['directory']['home'], result['session'])
        view = projection.project(child, result['session'])
        self.assertEqual(view['children'], [{'key': 'garden', 'label': 'GARDEN', 'object': 'garden', 'panel': 'main'}])
        self.assertIn('SESSION FOR ' + IRIS, view['data']['prose'])
        self.assertIn(result['originUri'], view['data']['prose'])
        selection = self.offered(result['session'], 'choose', IRIS, 'choose-garden',
            {'door': 'garden', 'original': 'A silver fern, please.'})
        self.exchange(selection['request'])
        # Choosing a reference does not grant the participant shared garden rights.
        self.invoke('garden', 'plant', {'seed': 'Fern', 'colour': 'silver'}, IRIS, 'refused')
        self.invoke(result['session'], 'choose', {'door': 'garden', 'original': 'I am not Iris.'}, MOSS, 'refused')
        self.invoke(result['session'], 'begin', {}, SERVICE, 'refused')
        self.receiver.checkpoint()
        self.receiver.close()
        self.receiver = resident_store.Resident(self.path)
        self.assertEqual(self.receiver.exchange(ready['request']), receipt)

    def test_two_posts_independent_sessions_current_factory_law_and_stale_retry(self):
        first = self.opening()
        competing = self.opening(MOSS, 'second', 'open-second')
        receipt = self.exchange(first['request'])
        stale = self.exchange(competing['request'], 'refused')
        self.assertEqual(stale['data'], 'stale read root')
        self.assertEqual(self.receiver.exchange(competing['request']), stale)
        fresh = self.opening(MOSS, 'second', 'open-second-fresh')
        second = self.exchange(fresh['request'])
        self.assertEqual(set(second['data']['allocated']), {'sessions/session-2'})
        for identity, actor in [('sessions/session-1', IRIS), ('sessions/session-2', MOSS)]:
            self.assertEqual(plain(self.root(identity)['state']['model'])['origin']['author'], actor)
        forged = self.opening(MOSS, 'forged', 'forged', MOSS)
        before = self.root('sessions')
        self.exchange(forged['request'], 'refused')
        self.assertEqual(self.root('sessions'), before)
        changed = {**first['request'], 'calls': [dict(call) for call in first['request']['calls']]}
        changed['calls'][0] = {**changed['calls'][0], 'input': {**changed['calls'][0]['input'], 'originCid': 'edited'}}
        self.assertEqual(self.exchange(changed, 'refused')['data'], 'intent reused for different request')
        self.assertEqual(self.receiver.exchange(first['request']), receipt)

    def test_six_configured_sections_open_in_one_captured_source_turn(self):
        keys = ['garden', 'rooms', 'conversations', 'play', 'workshop', 'studio']
        program = package.factory(package.entry(), [door(key) for key in keys])
        self.exchange({'op': 'create', 'object': 'six-doors', 'principal': 'operator',
            'intent': 'create-six', 'protocol': program, 'law': [SERVICE]})
        ready = self.offered('six-doors', 'make', SERVICE, 'open-six', {
            'author': IRIS, 'originUri': 'at://' + IRIS + '/app.bsky.feed.post/six', 'originCid': 'bafyresix'})
        self.assertEqual(ready['kind'], 'ready')
        self.assertEqual(len(ready['request']['calls']), 8)
        self.assertEqual(set(ready['request']['reads']), {'six-doors', 'six-doors/session-1', 'garden'})
        receipt = self.exchange(ready['request'])
        self.assertFalse(receipt['data']['results'][0]['followup']['enabled'])
        view = projection.project(self.root('six-doors/session-1'), 'six-doors/session-1')
        self.assertEqual([item['key'] for item in view['children']], keys)
        self.assertNotIn('Not open in this directory yet.', view['data']['prose'])

    def test_configured_target_changes_are_captured_and_origin_cannot_be_rewritten(self):
        self.exchange(self.opening()['request'])
        identity = 'sessions/session-1'
        before = plain(self.root(identity)['state']['model'])['origin']
        prepared = self.offered(identity, 'choose', IRIS, 'old-card', {'door': 'garden', 'original': 'Let me try.'})
        self.invoke(identity, 'setDoor', door(available=False), SERVICE)
        self.exchange(prepared['request'], 'refused')
        self.invoke(identity, 'setDoor', {**door(), 'originCid': 'forged'}, SERVICE, 'refused')
        self.assertEqual(plain(self.root(identity)['state']['model'])['origin'], before)
        self.invoke(identity, 'setDoor', door(), SERVICE)
        fresh = self.offered(identity, 'choose', IRIS, 'fresh-card', {'door': 'garden', 'original': 'Let me try.'})
        self.exchange(fresh['request'])


if __name__ == '__main__': unittest.main()
