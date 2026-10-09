"""Facilitated two-player play, private custody, public cards and real Lean admission."""
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
import table_participant as participant


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


companion = load('automatafl_companion_test', 'protocols/automatafl/companion.py')
generate = load('automatafl_generator_test', 'protocols/automatafl/generate.py')
journey = load('automatafl_journey_test', 'scripts/table_journey.py')
fixture = load('automatafl_pds_fixture', 'conformance/test_clerk.py')
NORTH, SOUTH = fixture.A, fixture.B
ORIGINAL = participant.loads((ROOT / 'game/automatafl/original-opening-qualification.json').read_bytes())
ISSUER, VISITOR = 'did:plc:' + 'c' * 24, 'did:plc:' + 'd' * 24


class AutomataflCompanion(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.table = 'table:automatafl'
        self.pds = fixture.FakePDS()
        self.clerk = clerk.Clerk(self.base / 'clerk', self.pds)
        reply = self.clerk.bootstrap(self.table, generate.protocol(self.table, NORTH, SOUTH),
            generate.table.law(NORTH, SOUTH), [NORTH, SOUTH, VISITOR], runtime_profile='compiled')
        self.assertEqual(reply['kind'], 'committed', reply)
        self.book = companion.town_cards.CardBook.create(self.base / 'cards', issuer_did=ISSUER,
            world_id='test-automatafl', runtime=companion.history.runtime('compiled'))
        self.clerk.upgrade(self.clerk.profile()['sha256'], town_cards={
            'path': str(self.book.path), 'issuers': [ISSUER], 'metadata': self.book.metadata()})
        self.players = [self.player(seat) for seat in (0, 1)]

    def player(self, seat):
        return participant.Participant(self.clerk.database, self.base / ('private-' + str(seat)),
                                       self.table, (NORTH, SOUTH)[seat], seat)

    def root(self):
        return self.clerk.snapshot(self.table, principal=NORTH)['root']

    def capture(self, alias):
        public = companion.capture(self.clerk.database, self.table, self.book, alias, principal=VISITOR)
        self.parent = {'uri': f'at://{ISSUER}/{clerk.FEED}/{alias}', 'cid': 'cid-' + alias}
        self.pds.records[self.parent['uri']] = (self.parent['cid'], {'$type': clerk.FEED, 'text': public['text']})
        self.book.bind(alias, self.parent, lambda uri, cid: self.clerk.fetch_record(uri, cid, (clerk.FEED,)),
                       database=self.clerk.database)
        self.assertNotIn(NORTH, public['text'])
        self.assertNotIn(SOUTH, public['text'])
        self.assertIn('K11 is 120', self.book.card(alias)['body'])
        return public, self.book.card(alias)['actions']

    def private(self, seat, action, fields, intent, lost_reply=False):
        player = self.players[seat]
        card = player.observe()
        proposed = participant.interpret.interpret('do ' + card['card'] + ' ' + action + ' ' +
                                                   participant.canonical(fields).decode(), card)
        self.assertEqual(proposed['status'], 'proposed', proposed)
        prepared = player.prepare(card['card'], proposed['action'], proposed['fields'], intent)
        preimage = player._read('requests', prepared['prepared'])
        if lost_reply:
            exchange = participant.desk.world.exchange

            def lose(*args, **kwargs):
                exchange(*args, **kwargs)
                raise OSError('simulated reply loss after admitted commit')

            with patch.object(participant.desk.world, 'exchange', side_effect=lose):
                with self.assertRaises(OSError):
                    player.send(prepared['prepared'])
            before = self.clerk.database.read_bytes()
            player = self.player(seat)
            self.players[seat] = player
            result = player.send(prepared['prepared'])
            self.assertEqual(self.clerk.database.read_bytes(), before)
            self.assertEqual(player._read('requests', prepared['prepared']), preimage)
        else:
            result = player.send(prepared['prepared'])
        self.assertEqual(result['kind'], 'committed', result)
        return prepared

    def post(self, key, alias, author=NORTH, natural=False):
        uri = f'at://{author}/{clerk.FEED}/{key}'
        text = 'Both moves are open; please resolve this round.' if natural else 'delvetalk ' + alias + ' resolve'
        self.pds.records[uri] = ('cid-' + key, {'$type': clerk.FEED, 'text': text,
            'reply': {'root': self.parent, 'parent': self.parent}})
        return uri, 'cid-' + key

    def test_full_match_private_choices_public_receiving_and_restart(self):
        public, actions = self.capture('start')
        self.assertEqual(actions, [])
        state = companion.client.state(self.root())
        self.assertEqual((state['width'], state['height'], state['game']['automaton']), (11, 11, 60))
        self.assertEqual(state['game']['board'], int(generate.table.OPENING['board']))
        self.assertIn('  1  - . . . + - + . . . -', public['text'])
        self.assertIn(' 11  - . . . + - + . . . -', public['text'])
        self.assertIn('K11 is 120', public['text'])
        self.assertIn('private move custody', public['text'])
        with self.assertRaisesRegex(ValueError, 'not offered'):
            self.players[0].prepare(self.players[0].observe()['card'], 'reveal', {}, 'too-early')
        receipt = source = None
        for number, moves in enumerate(journey.MATCH):
            for seat in (0, 1):
                self.private(seat, 'commit', dict(zip(('source', 'target'), moves[seat])),
                             f'r{number}-seal-{seat}', lost_reply=(number == 0 and seat == 0))
                nonce = participant.loads(self.players[seat]._opening(number).read_bytes())['reveal']['nonce']
                self.assertNotIn(nonce, self.clerk.database.read_text())
            if number == 0:
                public, actions = self.capture('both-sealed')
                self.assertEqual(actions, [])
                self.assertIn('Both moves are sealed', public['text'])
                self.assertNotIn('North opened:', public['text'])
                self.assertNotIn('South opened:', public['text'])
                for player in self.players:
                    secret = participant.loads(player._opening(number).read_bytes())
                    retained = companion.town_cards.canonical(self.book.card('both-sealed'))
                    self.assertNotIn(secret['commit']['digest'], retained)
                    self.assertNotIn(secret['reveal']['nonce'], retained)
                    self.assertNotIn(secret['commit']['digest'], public['text'])
                    self.assertNotIn(secret['reveal']['nonce'], public['text'])
            self.private(0, 'reveal', {}, f'r{number}-open-0')
            if number == 0:
                opened, actions = self.capture('north-open')
                self.assertEqual(actions, [])
                self.assertIn('North opened: F10 to F7', opened['text'])
                self.assertNotIn('South opened:', opened['text'])
            self.private(1, 'reveal', {}, f'r{number}-open-1')
            alias = 'resolve-' + str(number)
            public, actions = self.capture(alias)
            self.assertEqual([a['command'] for a in actions], ['resolve'])
            self.assertEqual(actions[0]['fields'], [])
            self.assertIn('delvetalk ' + alias + ' resolve', public['text'])
            if number == 0:
                denied = self.clerk.receive(*self.post('visitor', alias, VISITOR))
                self.assertEqual(denied['reply']['data'], 'opaque invocation refused')
                expected = self.root()
                source = self.post('manual-resolve', alias, natural=True)
                receipt = self.clerk.receive_interpreted(*source, {
                    'status': 'act', 'interpreter': 'test local operator',
                    'basis': 'North asks to resolve the two openings shown on the captured card.',
                    'request': {'object': self.table, 'command': 'resolve',
                                'input': {'round': number}, 'expected': expected}})
            else:
                source = self.post('resolve-' + str(number), alias, SOUTH)
                receipt = self.clerk.receive(*source)
            self.assertEqual(receipt['reply']['kind'], 'committed', receipt)
            self.assertEqual(companion.client.state(self.root())['game'],
                participant.table.source_object.plain(ORIGINAL['rounds'][number]['result']['value']))
            self.assertEqual(receipt['request']['principal'], NORTH if number == 0 else SOUTH)
            stale = self.clerk.receive(*self.post('stale-' + str(number), alias))
            self.assertEqual(stale['reply']['data'], 'opaque invocation refused')
        self.assertEqual(companion.client.state(self.root())['game']['winner'], 1)
        public, actions = self.capture('finished')
        self.assertEqual(actions, [])
        self.assertIn('North wins', public['text'])
        self.pds.records.clear()
        calls = len(self.pds.calls)
        self.assertEqual(clerk.Clerk(self.clerk.state, self.pds).receive(*source), receipt)
        self.assertEqual(len(self.pds.calls), calls)

    def test_conflict_and_invalid_rounds_remain_actual_game_results(self):
        for number, moves, status in ((0, ((0, 5), (0, 1)), 1), (1, ((0, 5), (4, 9)), 2)):
            for seat in (0, 1):
                self.private(seat, 'commit', dict(zip(('source', 'target'), moves[seat])), f'c{number}-{seat}')
            for seat in (0, 1):
                self.private(seat, 'reveal', {}, f'o{number}-{seat}')
            self.private(0, 'resolve', {}, f'resolve-{number}')
            public, actions = self.capture('result-' + str(number))
            self.assertEqual(actions, [])
            self.assertEqual(companion.client.state(self.root())['game']['status'], status)
            self.assertIn('Marked: A1', public['text'])
            self.assertIn('last pair conflicted' if status == 1 else 'last pair was invalid', public['text'])

    def test_public_source_capture_does_not_grant_private_read_and_current_law_gates_saved_card(self):
        object_id = 'table:public-capture'
        authority = generate.table.law(NORTH, SOUTH)
        authority['law'] = [NORTH]
        created = companion.world.exchange(self.clerk.database, {
            'op': 'create', 'object': object_id, 'principal': NORTH, 'intent': 'public-table',
            'protocol': generate.protocol(object_id, NORTH, SOUTH), 'law': authority})
        self.assertEqual(created['kind'], 'committed', created)
        with self.assertRaises((ValueError, RuntimeError)):
            companion.world.capture_roots(self.clerk.database, [object_id], principal=VISITOR)
        captured = companion.capture(self.clerk.database, object_id, self.book, 'public-table', principal=VISITOR)
        retained = self.book.card('public-table')
        self.assertEqual(retained['format'], 'delvetalk-town-public-card-v1')
        self.assertEqual(retained['projection']['audience'], 'public')
        self.assertNotIn('root', retained['projection'])
        self.assertNotIn('view', retained)
        self.assertNotIn(captured['reference']['key'], captured['text'])
        self.assertNotIn(NORTH, captured['text'])
        self.assertNotIn(SOUTH, captured['text'])
        current = companion.world.capture_roots(self.clerk.database, [object_id], principal=NORTH)['roots'][object_id]['root']
        changed = companion.world.exchange(self.clerk.database, {
            'op': 'law', 'object': object_id, 'principal': NORTH, 'intent': 'close-public-table',
            'expected': current, 'law': {**authority, 'view': {**authority['view'], 'main': [NORTH]}}})
        self.assertEqual(changed['kind'], 'committed', changed)
        with self.assertRaises((ValueError, RuntimeError)):
            companion.capture(self.clerk.database, object_id, self.book, principal=NORTH)
        with self.assertRaises((ValueError, RuntimeError)):
            self.book.check_public('public-table', self.clerk.database)

    def test_only_exact_qualified_core_and_companion_metadata_are_accepted(self):
        qualified = generate.table.protocol(self.table, NORTH, SOUTH)
        program = generate.protocol(self.table, NORTH, SOUTH)
        self.assertTrue(companion.client.same_game(qualified, qualified))
        self.assertTrue(companion.client.same_game(program, qualified))
        mutations = [lambda p: p['commands']['resolve']['transition']['package'].update(entry='commit0'),
                     lambda p: p['initial'].update(model=participant.table.source_object.data({**companion.client.state({'protocol': p, 'state': p['initial']}), 'width': 5, 'height': 5})),
                     lambda p: p['initial'].update(model=participant.table.source_object.data({**companion.client.state({'protocol': p, 'state': p['initial']}), 'round': False})),
                     lambda p: p.update(extraExecutionRoute={}),
                     lambda p: p['commands'].update(cheat=copy.deepcopy(p['commands']['resolve'])),
                     lambda p: p['viewProgram'].update(extra='unvalidated'),
                     lambda p: p['affordances'].update(cheat={'fields': {}}),
                     lambda p: p['viewPanels'].append({'id': 'unknown', 'label': 'Unknown'}),
                     lambda p: p.update(description=False),
                     lambda p: p['sourcePackages']['resident']['modules'][-1].update(source='edition ObjectiveBend 1')]
        for mutate in mutations:
            changed = copy.deepcopy(program)
            mutate(changed)
            self.assertFalse(companion.client.same_game(changed, qualified))
        self.assertEqual(program, qualified)
        # The ordinary table itself owns the public view; no optional Python layer.
        self.assertIn('viewProgram', qualified)


if __name__ == '__main__':
    unittest.main()
