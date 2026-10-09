"""Local source vocabulary completes actual typed placement; names grant no authority."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from conformance import test_containment as containment
compile_source = containment.compile_source
world = containment.world

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


source = module('room_composition_source', 'scripts/source_object.py')
package = module('room_composition_package', 'protocols/containment/package.py')


class RoomComposition(unittest.TestCase):
    send = containment.Containment.send
    root = containment.Containment.root
    create = containment.Containment.create
    invoke = containment.Containment.invoke
    enroll = containment.Containment.enroll
    act = containment.Containment.act
    movement = containment.Containment.movement
    rows = containment.Containment.rows

    @classmethod
    def setUpClass(cls):
        cls.lampSource = compile_source('Lamp')
        cls.relation = compile_source('Main')
        cls.room = compile_source('Room')
        cls.narrow = cls.room
        choices = source.variant('nil', source.record({}))
        for term, verb, identity in reversed([('reading room', 'enter', 'garden'),
                ('reading room', 'enter', 'study')]):
            choices = source.variant('cons', source.record({
                'head': source.data({'term': term, 'verb': verb, 'object': identity}), 'tail': choices}))
        cls.guide = package.load('Guide', source.record({
            'placement': source.data('habitat'), 'body': source.data('alice-body'), 'choices': choices}))

    def setUp(self):
        containment.Containment.setUp(self)
        self.create('route-book', self.guide, {'profile': 'delvetalk-scoped-law',
            'invoke': {'choose': ['alice'], 'bind': ['alice'], 'complete': ['alice']},
            'reprogram': ['curator'], 'law': ['curator']})
        portal = module('room_composition_portal', 'scripts/portal.py')
        runtime = module('room_composition_runtime', 'scripts/runtime_profile.py')
        portal.save(self.base / 'manifest.json', {'cafe': 'route-book',
            'runtime': {'name': 'compiled', 'files': runtime.file_hashes('compiled')}})
        self.app = portal.Portal(self.base)
        self.send(self.offer('bind', {}), 'alice')
        self.invoke('route-book', 'choose', {'term': 'reading room', 'verb': 'enter'})

    def offer(self, token, fields):
        card = self.app.object('route-book')
        self.assertEqual(card['mode'], 'projection', card)
        action = next(item for item in card['actions'] if item.get('offer') == token)
        self.serial += 1
        return self.app.captured_request(self.app._read('cards', card['card']), action['id'],
            'alice', 'route-' + str(self.serial), fields)

    def model(self):
        return source.plain(source.state_data(self.root('route-book')))

    def test_ambiguous_local_word_offers_known_choices_then_completes_real_arrival(self):
        card = self.app.object('route-book')
        self.assertEqual({child['object'] for child in card['children']}, {'garden', 'study'})
        self.assertNotIn('lamp', card['prose'])
        move = next(item for item in card['actions'] if item.get('offer') == 'move')
        import source_offers
        with self.assertRaises(source_offers.PreparationOutcome) as captured:
            self.app.captured_request(self.app._read('cards', card['card']), move['id'],
                'alice', 'ambiguous-choice', {'object': ''})
        question = captured.exception.outcome
        self.assertEqual(question.get('kind'), 'question', question)
        self.assertIn('garden', question['message'])
        self.assertIn('study', question['message'])
        request = self.offer('move', {'object': 'study'})
        self.assertEqual(set(request['reads']), {'route-book', 'habitat', 'study'})
        self.assertEqual([call.get('inputFrom') for call in request['calls']], [None, 0, 1, 2])
        done = self.send(request, 'alice')
        self.assertEqual(done['data']['results'][2],
            {'object': 'alice-body', 'destination': 'study', 'actor': 'alice'})
        self.assertEqual(done['data']['results'][3], 'Arrived in study')
        self.assertEqual(self.rows()['alice-body']['place'], 'study')
        self.assertEqual((self.model()['arrivals'], self.model()['lastRoom']), (1, 'study'))
        self.assertEqual(world.exchange(self.database, {'principal': 'alice', **request}, profile='compiled'), done)

    def test_spoof_and_obsolete_producer_refuse_without_partial_placement(self):
        copied = {'object': 'alice-body', 'destination': 'study', 'actor': 'alice'}
        self.invoke('route-book', 'complete', copied, kind='refused')
        before = self.root('route-book')
        for term, verb in [('worldwide missing room', 'enter'), ('reading room', 'rewrite')]:
            self.invoke('route-book', 'choose', {'term': term, 'verb': verb}, kind='refused')
            self.assertEqual(self.root('route-book'), before)
        prepared = self.offer('move', {'object': 'study'})
        current = self.root('habitat')
        revised = current['protocol'] | {'editionNote': 'a governed replacement'}
        self.send({'op': 'reprogram', 'object': 'habitat', 'expected': current,
            'protocol': revised, 'state': current['state']})
        self.send(prepared, 'alice', 'refused')
        # A fresh transaction with old bound source intention still cannot turn a
        # valid new placement result into a completion from the old exact program.
        roots = {name: self.root(name) for name in ('route-book', 'habitat', 'study')}
        fresh = {'op': 'transaction', 'reads': roots, 'calls': prepared['calls']}
        self.send(fresh, 'alice', 'refused')
        self.assertEqual(self.rows()['alice-body']['place'], '')
        self.assertEqual(self.model()['arrivals'], 0)
        self.send(self.offer('bind', {}), 'alice')
        self.send(self.offer('move', {'object': 'study'}), 'alice')
        self.assertEqual(self.model()['arrivals'], 1)

    def test_retained_reference_is_not_text_or_authority(self):
        import copy
        request = self.offer('move', {'object': 'study'})
        before = self.root('habitat')
        for index, replacement in enumerate(('study', {'profile': 'delvetalk-retained-root-v1',
                'object': 'study', 'key': '0' * 64})):
            forged = copy.deepcopy(request)
            forged['reads']['study'] = replacement
            forged['intent'] = 'forged-reference-' + str(index)
            self.send(forged, 'alice', 'refused')
            self.assertEqual(self.root('habitat'), before)
        # Reusing the same observed roots cannot delegate Alice's invocation law.
        copied = copy.deepcopy(request)
        copied['intent'] = 'copied-reference-bob'
        copied['principal'] = 'bob'
        self.send(copied, 'bob', 'refused')
        self.assertEqual(self.root('habitat'), before)
        self.send(request, 'alice')
        self.assertEqual(self.rows()['alice-body']['place'], 'study')
        current = self.root('route-book')
        revoked = copy.deepcopy(current['law'])
        revoked['invoke']['complete'] = []
        self.send({'op': 'law', 'object': 'route-book', 'expected': current, 'law': revoked})
        placed = self.root('habitat')
        self.send(self.offer('move', {'object': 'garden'}), 'alice', 'refused')
        self.assertEqual(self.root('habitat'), placed)


if __name__ == '__main__':
    unittest.main()
