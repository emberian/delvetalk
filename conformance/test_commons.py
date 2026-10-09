#!/usr/bin/env python3
"""Local declared presence, authored paths and exact admission through real Lean."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


g = module('commons_generator', 'protocols/commons/generate.py')
a = module('commons_affordances', 'scripts/affordances.py')
world = module('commons_world', 'scripts/world.py')


class CommonsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.profile = 'world'
        self.db = Path(self.tmp.name) / 'world.json'

    def call(self, request):
        return world.exchange(self.db, request, profile=self.profile)

    def seed(self, protocol=None, law=None):
        protocol = g.build() if protocol is None else protocol
        result = self.call({'op': 'create', 'object': 'commons', 'principal': 'operator',
                           'intent': 'seed', 'protocol': protocol, 'law': g.law() if law is None else law})
        self.assertEqual(result['kind'], 'committed', result)
        self.initial = result['data']['root']
        return self.initial

    def request(self, root, command, principal='moss', intent=None, place=None):
        view = {'mode': 'raw', 'object': 'commons', 'root': root}
        action = next(x['id'] for x in a.card(view)['actions'] if x['command'] == command)
        return a.request(view, action, principal, intent or command,
                         {} if place is None else {'place': place})

    def inspect(self):
        return self.call({'op': 'inspect', 'object': 'commons', 'principal': 'reader'})

    def test_enter_move_leave_returns_usable_place_and_entity_references(self):
        for profile in ('world', 'transactions', 'compiled'):
            with self.subTest(profile=profile):
                self.profile = profile
                self.db = Path(self.tmp.name) / profile
                root = self.seed()
                entered = self.call(self.request(root, 'enter', place='porch'))
                self.assertEqual(entered['kind'], 'committed', entered)
                result = entered['data']['result']
                self.assertEqual(result['locations'], {'moss': 'porch', 'iris': ''})
                self.assertEqual(result['entity'], g.default_participants()['moss'])
                self.assertEqual(result['place']['reference'], g.default_places()['porch']['reference'])
                self.assertEqual(result['place']['exits'], {'garden': g.default_places()['garden']['reference']})
                moved = self.call(self.request(entered['data']['root'], 'move', place='garden'))
                self.assertEqual(moved['data']['result']['from'], 'porch')
                self.assertEqual(moved['data']['result']['to'], 'garden')
                self.assertEqual(moved['data']['root']['state']['locations']['iris'], '')
                left = self.call(self.request(moved['data']['root'], 'leave'))
                self.assertEqual(left['data']['result']['place'], {})
                self.assertEqual(left['data']['root']['state'], root['state'])
                self.assertEqual(self.call(self.request(left['data']['root'], 'leave', intent='leave-twice'))['data'], 'precondition failed')

    def test_paths_entries_and_declared_principals_are_checked_in_lean(self):
        root = self.seed()
        self.assertEqual(self.call(self.request(root, 'move', place='garden'))['data'], 'precondition failed')
        forbidden_entry = self.request(root, 'enter', intent='tower', place='porch')
        forbidden_entry['input']['place'] = 'tower'  # bypass the presentation enum
        self.assertEqual(self.call(forbidden_entry)['data'], 'precondition failed')
        entered = self.call(self.request(root, 'enter', intent='enter', place='porch'))['data']['root']
        for place in ('tower', 'missing', 'porch', False):
            request = self.request(entered, 'move', intent='bad-' + str(place), place='garden')
            request['input']['place'] = place
            self.assertEqual(self.call(request)['kind'], 'refused')
            self.assertEqual(self.inspect(), entered)
        self.assertEqual(self.call(self.request(entered, 'enter', intent='enter-twice', place='porch'))['data'], 'precondition failed')
        # A grant is necessary, but cannot add a participant slot to this program.
        law = g.law(); law['invoke']['enter'].append('outsider')
        changed = self.call({'op': 'law', 'object': 'commons', 'principal': 'steward', 'intent': 'grant',
                             'expected': entered, 'law': law})['data']['root']
        self.assertEqual(self.call(self.request(changed, 'enter', principal='outsider', intent='outside', place='porch'))['data'], 'precondition failed')

    def test_current_law_impersonation_race_and_exact_restart_replay(self):
        root = self.seed()
        self.assertEqual(self.call(self.request(root, 'enter', principal='operator', intent='creator', place='porch'))['data'], 'unauthorized')
        moss = self.request(root, 'enter', intent='moss-enter', place='porch')
        iris = self.request(root, 'enter', principal='iris', intent='iris-stale', place='porch')
        committed = self.call(moss)
        self.assertEqual(self.call(iris)['data'], 'stale read root')
        iris = self.request(committed['data']['root'], 'enter', principal='iris', intent='iris-enter', place='porch')
        iris['input']['principal'] = 'moss'
        iris['input']['entity'] = g.default_participants()['moss']
        both = self.call(iris)
        self.assertEqual(both['data']['result']['principal'], 'iris')
        self.assertEqual(both['data']['result']['entity'], g.default_participants()['iris'])
        self.assertEqual(both['data']['root']['state']['locations'], {'moss': 'porch', 'iris': 'porch'})
        law = g.law(); law['invoke']['move'].remove('moss')
        locked = self.call({'op': 'law', 'object': 'commons', 'principal': 'steward', 'intent': 'revoke-move',
                            'expected': both['data']['root'], 'law': law})['data']['root']
        self.assertEqual(self.call(self.request(locked, 'move', intent='still-present', place='garden'))['data'], 'unauthorized')
        self.assertEqual(self.call(moss), committed)
        altered = copy.deepcopy(moss); altered['input']['place'] = 'garden'
        self.assertEqual(self.call(altered)['data'], 'intent reused for different request')
        # Replay a fresh custody transcript against another empty database.
        replay_db = Path(self.tmp.name) / 'replay.json'
        for retained in world.wire_loads(self.db.read_text())['receipts']:
            self.assertEqual(world.exchange(replay_db, retained['request']), retained['receipt'])

    def test_transaction_failure_rolls_back_movement_and_composed_calls_remain_local(self):
        self.profile = 'transactions'
        root = self.seed()
        request = {'op': 'transaction', 'principal': 'moss', 'intent': 'walk', 'reads': {'commons': root},
                   'calls': [{'object': 'commons', 'command': 'enter', 'input': {'place': 'porch'}},
                             {'object': 'commons', 'command': 'move', 'input': {'place': 'tower'}}]}
        self.assertEqual(self.call(request)['data'], 'precondition failed')
        self.assertEqual(self.inspect(), root)
        request['intent'] = 'valid-walk'; request['calls'][1]['input']['place'] = 'garden'
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data']['roots']['commons']['state']['locations']['moss'], 'garden')
        self.assertEqual(self.call(request), receipt)

    def test_presence_does_not_grant_authority_over_referenced_place(self):
        root = self.seed()
        target = self.call({'op': 'create', 'object': 'places/porch', 'principal': 'operator',
            'intent': 'place', 'law': [], 'protocol': {'profile': 'delvetalk-local-v1', 'initial': {},
            'commands': {'touch': {'require': [], 'set': {}, 'result': ['literal', 'touched'], 'outbox': []}}}})
        entered = self.call(self.request(root, 'enter', place='porch'))
        ref = entered['data']['result']['place']['reference']
        object_id = g.references.local_object(ref, 'commons-example')
        refused = self.call({'op': 'invoke', 'object': object_id, 'principal': 'moss',
            'intent': 'presence-is-not-grant', 'expected': target['data']['root'], 'command': 'touch', 'input': {}})
        self.assertEqual(refused['data'], 'unauthorized')

    def test_configured_upper_bound_and_generated_files_are_runnable(self):
        participants = {f'p{i}': g.references.object_reference('other-world', f'entity/{i}') for i in range(8)}
        places = {f'r{i}': {'title': f'Room {i}', 'description': 'An authored place.',
                  'reference': g.references.object_reference('other-world', f'place/{i}')} for i in range(8)}
        paths = [(f'r{i}', f'r{(i + delta) % 8}') for i in range(8) for delta in (1, 2)]
        protocol = g.build(participants, places, paths, entries=('r0',))
        root = self.seed(protocol, g.law(participants))
        root = self.call(self.request(root, 'enter', principal='p7', place='r0'))['data']['root']
        moved = self.call(self.request(root, 'move', principal='p7', place='r2'))
        self.assertEqual(moved['kind'], 'committed', moved)
        self.assertEqual(moved['data']['result']['entity']['world'], 'other-world')
        self.assertEqual(json.loads((ROOT / 'protocols/commons/protocol.json').read_text()), g.build())
        self.assertEqual(json.loads((ROOT / 'protocols/commons/law.json').read_text()), g.law())
        self.assertEqual(json.loads((ROOT / 'protocols/commons/migration.json').read_text()), g.build()['initial'])

    def test_malformed_authored_topology_refuses_without_authority_or_runtime(self):
        for changes in ({'participants': {}}, {'places': {}}, {'entries': ('missing',)},
                        {'entries': ('porch', 'porch')}, {'paths': [('porch', 'missing')]},
                        {'paths': [('porch', 'garden')] * 2}, {'paths': [('porch', 'garden')] * 17}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): g.build(**changes)
        participants = g.default_participants(); participants['iris'] = participants['moss']
        with self.assertRaises(ValueError): g.build(participants=participants)
        places = g.default_places(); places['porch']['reference']['authority'] = 'granted'
        with self.assertRaises(ValueError): g.build(places=places)


if __name__ == '__main__': unittest.main()
