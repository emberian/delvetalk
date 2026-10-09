"""Actual typed-source placement/custody, independent room policies, and replay."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'syntaxes'))
import obend_object
import world
import history

PACKAGE = ROOT / 'protocols/containment'


def compile_source(entry, **substitutions):
    source = (PACKAGE / (entry + '.obend')).read_text()
    for old, new in substitutions.items():
        source = source.replace(old, new)
    return obend_object.lower_data_modules([
        {'name': 'Relations', 'source': (PACKAGE / 'Relations.obend').read_text()},
        {'name': 'Main', 'source': source}])


def member_rows(root):
    # Evidence decoder only: admission and movement execute the authored source.
    def field(record, name):
        return next(v['value'] for v in record['fields'] if v['name'] == name)
    cursor = field(root['state']['model'], 'members')
    rows = {}
    while cursor['label'] == 'cons':
        row = field(cursor['payload'], 'head')
        values = {v['name']: v['value']['value'] for v in row['fields']}
        rows[values['object']] = values
        cursor = field(cursor['payload'], 'tail')
    return rows


class Containment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.relation = compile_source('Main')
        cls.room = compile_source('Room', **{'capacity: 4n': 'capacity: 3n'})
        cls.narrow = compile_source('Room', **{'capacity: 4n': 'capacity: 1n', 'A room': 'The quiet room'})

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.database = self.base / 'world.json'
        self.serial = 0
        people = ['alice', 'bob', 'curator']
        self.create('habitat', self.relation, {'profile': 'delvetalk-scoped-law-v1',
            'invoke': {k: people for k in ('enroll', 'act', 'plan', 'arrive')},
            'reprogram': ['curator'], 'law': ['curator']})
        room_law = {'profile': 'delvetalk-scoped-law-v1', 'invoke': {'admit': ['alice', 'bob']},
                    'reprogram': ['curator'], 'law': ['curator']}
        self.create('garden', self.room, room_law)
        self.create('study', self.narrow, room_law)
        self.lamp = {'profile': 'delvetalk-local-v1', 'initial': {'lit': False},
            'commands': {'shine': {'require': [], 'set': {'lit': ['literal', True]},
                'result': ['literal', 'The lamp shines.'], 'outbox': []}}}
        for name in ('alice-body', 'bob-body', 'lamp'):
            self.create(name, self.lamp, ['alice'] if name != 'bob-body' else ['bob'])
        for room in ('garden', 'study'):
            self.enroll(room, 'curator')
            self.act('room', room, who='curator')
        for who in ('alice', 'bob'):
            self.enroll(who + '-body', who)
            self.act('inhabit', who + '-body', who=who)
        self.enroll('lamp', 'alice')

    def send(self, request, who='curator', kind='committed'):
        self.serial += 1
        request = {'principal': who, 'intent': 'containment-' + str(self.serial), **request}
        result = world.exchange(self.database, request, profile='compiled')
        self.assertEqual(result['kind'], kind, result)
        return result

    def root(self, object='habitat'):
        return world.exchange(self.database, {'op': 'inspect', 'object': object, 'principal': 'curator', 'intent': 'inspect'}, profile='compiled')

    def create(self, object, protocol, law):
        return self.send({'op': 'create', 'object': object, 'protocol': protocol, 'law': law})

    def invoke(self, object, command, values, who='alice', kind='committed'):
        return self.send({'op': 'invoke', 'object': object, 'expected': self.root(object),
                          'command': command, 'input': values}, who, kind)

    def enroll(self, object, who, kind='committed'):
        return self.send({'op': 'transaction', 'reads': {'habitat': self.root(), object: self.root(object)},
            'calls': [{'op': 'observe', 'object': object},
                      {'object': 'habitat', 'command': 'enroll', 'inputFrom': 0}]}, who, kind)

    def act(self, action, object, to='', who='alice', kind='committed'):
        return self.invoke('habitat', 'act', {'action': action, 'object': object, 'to': to}, who, kind)

    def movement(self, object, to, who='alice', kind='committed', extra=None, roots=None):
        calls = [{'object': 'habitat', 'command': 'plan', 'input': {'object': object, 'to': to}},
                 {'object': to, 'command': 'admit', 'inputFrom': 0},
                 {'object': 'habitat', 'command': 'arrive', 'inputFrom': 1}]
        return self.send({'op': 'transaction', 'reads': roots or {'habitat': self.root(), to: self.root(to)},
                          'calls': calls + (extra or [])}, who, kind)

    def rows(self):
        return member_rows(self.root())

    def test_shipped_source_examples(self):
        import propose
        import spell_examples
        for protocol, filename in ((self.relation, 'relation.examples'), (self.room, 'room.examples')):
            report = propose.run_scenarios(protocol, spell_examples.parse((PACKAGE / filename).read_text()),
                                           profile='compiled')
            self.assertTrue(all(not case['failures'] for case in report), report)

    def test_acquire_give_drop_move_capacity_revision_and_restart(self):
        self.movement('alice-body', 'garden')
        self.movement('bob-body', 'garden', 'bob')
        self.assertEqual(self.rows()['lamp']['holder'], 'alice')
        self.movement('lamp', 'garden')
        self.assertEqual(self.rows()['lamp']['place'], 'garden')
        self.act('acquire', 'lamp', who='bob', kind='refused')
        self.act('acquire', 'lamp')
        self.act('accept', 'lamp', who='bob', kind='refused')
        self.act('offer', 'lamp', 'bob')
        self.act('accept', 'lamp', who='bob')
        self.assertEqual((self.rows()['lamp']['owner'], self.rows()['lamp']['holder']), ('bob', 'bob'))
        # Declared custody never rewrites the portable object's current ability law.
        self.invoke('lamp', 'shine', {}, 'bob', 'refused')
        self.invoke('lamp', 'shine', {}, 'alice')
        self.movement('bob-body', 'study', 'bob')
        self.assertEqual(self.rows()['lamp']['place'], '')
        self.assertEqual(self.rows()['bob-body']['place'], 'study')
        # The single-capacity room contains Bob; dropping a thing adds another occupant.
        before = self.root()
        self.movement('lamp', 'study', 'bob', 'refused')
        self.assertEqual(self.root(), before)
        self.movement('alice-body', 'study', kind='refused')
        # Independent room author revises its actual policy; relation source is unchanged.
        expanded = compile_source('Room', **{'capacity: 4n': 'capacity: 3n',
            'A room': 'The welcoming study', 's.open && i.occupancy':
            's.open && i.actor != "barred-visitor" && i.occupancy'})
        self.send({'op': 'reprogram', 'object': 'study', 'expected': self.root('study'),
                   'protocol': expanded, 'state': expanded['initial']})
        self.movement('lamp', 'study', 'bob')
        self.movement('alice-body', 'study')
        rows = self.rows()
        self.assertEqual(rows['lamp']['place'], 'study')
        self.assertEqual(rows['lamp']['holder'], '')
        # Every call used a fresh receiving process. Export/replay additionally rebuilds history.
        bundle = self.base / 'bundle'
        manifest = history.export_history(self.database, bundle, profile='compiled', inline_reprogram=True)
        restored = self.base / 'restored.json'
        history.verify_history(bundle, output=restored, expected_genesis=manifest['genesis'],
                               expected_head=manifest['head'])
        original = world.snapshot(self.database)
        self.assertEqual(world.snapshot(restored), original)
        self.database = restored
        self.act('acquire', 'lamp', who='bob')
        self.movement('bob-body', 'garden', 'bob')
        self.assertEqual(self.rows()['bob-body']['place'], 'garden')
        self.assertEqual(self.rows()['lamp']['holder'], 'bob')
        self.assertEqual(self.rows()['lamp']['place'], '')

    def test_forgery_staleness_double_placement_and_atomic_late_failure(self):
        self.invoke('habitat', 'enroll', {'object': 'lamp', 'version': 0}, kind='refused')
        self.enroll('lamp', 'bob', 'refused')
        self.act('room', 'lamp', kind='refused')
        self.movement('alice-body', 'garden')
        fake = {'object': 'alice-body', 'destination': 'study', 'previous': 'garden',
                'holder': '', 'occupancy': 0, 'actor': 'alice'}
        self.invoke('study', 'admit', fake, kind='refused')
        self.invoke('habitat', 'arrive', fake, kind='refused')
        before = self.root()
        self.movement('alice-body', 'study', extra=[{'object': 'habitat', 'command': 'act',
            'input': {'action': 'acquire', 'object': 'missing', 'to': ''}}], kind='refused')
        self.assertEqual(self.root(), before)
        self.movement('alice-body', 'study', extra=[{'object': 'habitat',
            'command': 'arrive', 'inputFrom': 1}], kind='refused')
        self.assertEqual(self.root(), before)
        relation = self.rows()
        self.invoke('habitat', 'plan', {'object': 'alice-body', 'to': 'study'})
        self.assertEqual(self.rows(), relation, 'a partial plan must not move anybody')
        stale = {'habitat': self.root(), 'study': self.root('study')}
        self.act('offer', 'lamp', 'bob')
        self.movement('alice-body', 'study', roots=stale, kind='refused')
        self.act('cancel', 'lamp')
        self.act('accept', 'lamp', who='bob', kind='refused')
        self.movement('alice-body', 'study')
        self.movement('alice-body', 'study', kind='refused')
        self.assertEqual(self.rows()['alice-body']['place'], 'study')
        self.assertEqual(sum(r['object'] == 'alice-body' for r in self.rows().values()), 1)
        # Admission is current-law controlled even for an already carried/owned thing.
        room = self.root('garden')
        law = copy.deepcopy(room['law'])
        law['invoke']['admit'] = ['bob']
        self.send({'op': 'law', 'object': 'garden', 'expected': room, 'law': law})
        self.movement('alice-body', 'garden', kind='refused')


if __name__ == '__main__':
    unittest.main()
