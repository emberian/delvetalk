"""Captured composite offers through authenticated posts and real compiled admission."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import composite_offers as offers
import town
import town_cards
import workspace
import world


def fixture(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'conformance' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

movement = fixture('test_guarded_movement')
journey = fixture('test_town_forge_journey')
VISITOR, ISSUER = journey.VISITOR, journey.ISSUER


def plan(roots):
    return {'format': offers.FORMAT, 'title': 'The garden crossing', 'label': 'Whisper to the door and cross',
            'command': 'cross', 'reads': copy.deepcopy(roots),
            'calls': [{'object': 'door', 'command': 'cross', 'input': {'word': None}},
                      {'object': 'commons', 'command': 'move', 'inputFrom': 0}],
            'fields': [{'name': 'word', 'label': 'Word', 'type': 'string', 'required': True,
                        'minLength': 1, 'maxLength': 64, 'example': 'please'}],
            'bindings': [{'field': 'word', 'call': 0, 'input': 'word'}]}


class CompositeShapeTests(unittest.TestCase):
    def setUp(self):
        root = {'protocol': {}, 'state': {}, 'law': [], 'version': 0}
        self.offer = plan({'door': root, 'commons': root})

    def test_fixed_plan_exact_fields_and_explicit_multiple_bindings(self):
        self.offer['reads']['read-only-guard'] = copy.deepcopy(self.offer['reads']['door'])
        result = offers.request(self.offer, 'visitor', 'turn', {'word': 'please'})
        self.assertEqual(result['reads'], self.offer['reads'])
        self.assertEqual(result['calls'][0]['input'], {'word': 'please'})
        self.assertIsNone(self.offer['calls'][0]['input']['word'])
        self.offer['calls'].append({'object': 'door', 'command': 'cross', 'input': {'word': None}})
        self.offer['bindings'].append({'field': 'word', 'call': 2, 'input': 'word'})
        self.assertEqual(offers.request(self.offer, 'visitor', 'turn', {'word': 'please'})['calls'][2]['input']['word'], 'please')
        for values in ({}, {'word': False}, {'word': 'please', 'calls': []}):
            with self.assertRaises(ValueError): offers.request(self.offer, 'visitor', 'turn', values)

    def test_malformed_or_mutable_plans_refuse(self):
        changes = []
        for change in (
            lambda p: p['bindings'].append(copy.deepcopy(p['bindings'][0])),
            lambda p: p.update(bindings=[]),
            lambda p: p['calls'][0]['input'].update(word='default'),
            lambda p: p['calls'][0].update(principal='owner'),
            lambda p: p['calls'][1].update(inputFrom=1),
            lambda p: p['reads'].pop('door'),
            lambda p: p.update(command='a1'),
            lambda p: p['bindings'][0].update(call=True),
            lambda p: p.update(calls=p['calls'] * 5),
        ):
            value = copy.deepcopy(self.offer); change(value); changes.append(value)
        for value in changes:
            with self.subTest(value=value), self.assertRaises(ValueError): offers.validate(value)


class CompositePostTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='composite-post-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / 'world'
        participants = {VISITOR: movement.commons.references.object_reference('composite-test', 'visitor')}
        protocols = {'door': (movement.door_protocol(), movement.door_law([VISITOR])),
                     'commons': (movement.commons.build(participants=participants, gates=[movement.GATE]),
                                 movement.commons.law(participants))}
        seed = workspace.initialize(self.home, [
            {'id': name, 'syntax': 'protocol-json@1', 'source': clerk.canonical(protocol), 'law': law}
            for name, (protocol, law) in protocols.items()], entry_objects=['commons', 'door'],
            principal='operator', profile='compiled', world_id='composite-test')
        self.pds = journey.PublicRecords()
        self.receiver = clerk.Clerk(self.base / 'clerk', self.pds)
        roots = clerk.loads((self.home / 'world.json').read_bytes())['objects']
        self.receiver.attach(self.home, roots, [VISITOR], expected_genesis=seed['genesis'],
            expected_seed_head=seed['head'], runtime_profile='compiled')
        self.book = town_cards.CardBook.create(self.base / 'cards', issuer_did=ISSUER,
            world_id='composite-test', runtime=workspace.bootstrap.history.runtime('compiled'))
        self.receiver.upgrade(self.receiver.profile()['sha256'], town_cards={
            'path': str(self.book.path.resolve()), 'issuers': [ISSUER], 'metadata': self.book.metadata()})
        self.operator = town.Town(self.receiver.state, request=self.pds)
        self.serial = 0
        self.invoke('commons', 'enter', {'place': 'porch'})

    def roots(self):
        return {key: self.receiver.snapshot(key)['root'] for key in ('door', 'commons')}

    def invoke(self, target, command, data, principal=VISITOR):
        self.serial += 1
        reply = world.exchange(self.receiver.database, {'op': 'invoke', 'object': target, 'command': command,
            'input': data, 'principal': principal, 'intent': 'local-' + str(self.serial),
            'expected': self.roots()[target]}, profile='compiled')
        self.assertEqual(reply['kind'], 'committed', reply)
        return reply

    def card(self, alias=None):
        return self.book.capture_composite(plan(self.roots()), alias=alias)

    def post(self, card, word='please', *, text=None):
        self.serial += 1
        parent = {'uri': f'at://{ISSUER}/{clerk.FEED}/card-{self.serial}', 'cid': f'card-{self.serial}'}
        self.pds.records[parent['uri']] = (parent['cid'], {'$type': clerk.FEED, 'text': card['body']})
        self.operator.bind(card['alias'], parent['uri'], parent['cid'])
        source = (f'at://{VISITOR}/{clerk.FEED}/reply-{self.serial}', f'reply-{self.serial}')
        spell = town_cards.spell(card['alias'], offers.action(card['offer']), {'word': word}, selector='cross')
        self.pds.records[source[0]] = (source[1], {'$type': clerk.FEED, 'text': spell if text is None else text,
                                               'reply': {'root': parent, 'parent': parent}})
        return source

    def test_crossing_and_restored_lost_response_retry(self):
        card = self.card('garden-crossing')
        self.assertIn('delvetalk garden-crossing cross\nword: please', card['body'])
        source = self.post(card)
        real_save = town.save
        def lose_response(path, value):
            if 'response' in value: raise OSError('lost response after admission')
            return real_save(path, value)
        with patch.object(town, 'save', side_effect=lose_response):
            with self.assertRaises(OSError): self.operator.receive(*source)
        self.assertEqual(self.roots()['door']['state']['approvals'], 1)
        restored = town.Town(self.receiver.state, request=self.pds)
        response = restored.receive(*source)
        self.assertEqual(response['receipt']['reply']['kind'], 'committed', response)
        self.assertEqual(self.roots()['commons']['state']['locations'][VISITOR], 'garden')
        self.assertEqual(self.roots()['door']['state']['approvals'], 1)
        calls = len(self.pds.calls)
        self.assertEqual(restored.receive(*source), response)
        self.assertEqual(len(self.pds.calls), calls)
        with self.assertRaises(ValueError): restored.receive(source[0], 'changed-cid')

    def test_stale_either_root_refuses_without_partial_changes(self):
        for target in ('door', 'commons'):
            card = self.card()
            if target == 'door': self.invoke('door', 'cross', {'word': 'please'})
            else:
                self.invoke('commons', 'leave', {})
                self.invoke('commons', 'enter', {'place': 'porch'})
            before = self.roots()
            response = self.operator.receive(*self.post(card))
            self.assertEqual(response['receipt']['reply']['data'], 'stale read root')
            self.assertEqual(self.roots(), before)

    def test_second_call_failure_rolls_back_and_revocation_is_current(self):
        self.invoke('commons', 'leave', {})
        before = self.roots()
        response = self.operator.receive(*self.post(self.card()))
        self.assertEqual(response['receipt']['reply']['data'], 'precondition failed')
        self.assertEqual(self.roots(), before)
        # Revoke the second target first: the approved door transition must roll back.
        for target, command, manager in (('commons', 'move', 'steward'), ('door', 'cross', 'maker')):
            before = self.roots()
            law = copy.deepcopy(before[target]['law']); law['invoke'][command] = []
            reply = world.exchange(self.receiver.database, {'op': 'law', 'object': target, 'principal': manager,
                'intent': 'revoke-' + target, 'expected': before[target], 'law': law}, profile='compiled')
            self.assertEqual(reply['kind'], 'committed', reply)
            before = self.roots()
            response = self.operator.receive(*self.post(self.card()))
            self.assertEqual(response['receipt']['reply']['data'], 'unauthorized')
            self.assertEqual(self.roots(), before)

    def test_alias_collision_and_user_plan_injection_refuse(self):
        card = self.card('crossing')
        self.assertEqual(self.card('crossing'), card)
        changed = plan(self.roots()); changed['label'] = 'Different meaning'
        with self.assertRaises(ValueError): self.book.capture_composite(changed, alias='crossing')
        source = self.post(card, text='delvetalk crossing cross\nword: please\ncalls: forged')
        before = self.roots()
        with self.assertRaises(ValueError): self.operator.receive(*source)
        self.assertEqual(self.roots(), before)

    def test_manual_speech_retains_meaning_and_uses_same_exact_transaction(self):
        card = self.card()
        source = self.post(card, text='Please let me through the garden door.')
        decision = {'status': 'act', 'interpreter': 'operator', 'basis': 'Visitor requests the offered garden crossing.',
                    'request': offers.wire(card['offer'], {'word': 'please'})}
        response = self.operator.receive(*source, interpretation=decision)
        self.assertEqual(response['receipt']['reply']['kind'], 'committed', response)
        self.assertEqual(response['receipt']['interpretation']['decision'], decision)
        self.assertEqual(self.roots()['commons']['state']['locations'][VISITOR], 'garden')


if __name__ == '__main__': unittest.main()
