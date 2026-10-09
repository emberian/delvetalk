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
ISSUER, VISITOR = 'did:plc:' + 'c' * 24, 'did:plc:' + 'd' * 24


class AutomataflCompanion(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.table = 'table:automatafl'
        self.pds = fixture.FakePDS()
        self.clerk = clerk.Clerk(self.base / 'clerk', self.pds)
        reply = self.clerk.bootstrap(self.table, generate.protocol(self.table),
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
        return self.clerk.snapshot(self.table)['root']

    def capture(self, alias):
        public = companion.capture(self.root(), self.table, self.book, alias)
        self.parent = {'uri': f'at://{ISSUER}/{clerk.FEED}/{alias}', 'cid': 'cid-' + alias}
        self.pds.records[self.parent['uri']] = (self.parent['cid'], {'$type': clerk.FEED, 'text': public['text']})
        self.book.bind(alias, self.parent, lambda uri, cid: self.clerk.fetch_record(uri, cid, (clerk.FEED,)))
        self.assertNotIn(NORTH, public['text'])
        self.assertNotIn(SOUTH, public['text'])
        return public, self.book.card(alias)['card']['actions']

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
        self.assertIn('  1 + . . . -', public['text'])
        self.assertIn('operator can see choices', public['text'])
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
                    self.assertNotIn(secret['commit']['digest'], public['text'])
                    self.assertNotIn(secret['reveal']['nonce'], public['text'])
            self.private(0, 'reveal', {}, f'r{number}-open-0')
            if number == 0:
                opened, actions = self.capture('north-open')
                self.assertEqual(actions, [])
                self.assertIn('North opened: A1 to C1', opened['text'])
                self.assertNotIn('South opened:', opened['text'])
            self.private(1, 'reveal', {}, f'r{number}-open-1')
            alias = 'resolve-' + str(number)
            public, actions = self.capture(alias)
            self.assertEqual([a['command'] for a in actions], ['resolve'])
            self.assertEqual(actions[0]['fields'], [])
            self.assertIn('delvetalk ' + alias + ' resolve', public['text'])
            if number == 0:
                denied = self.clerk.receive(*self.post('visitor', alias, VISITOR))
                self.assertEqual(denied['reply']['data'], 'unauthorized')
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
            self.assertEqual(receipt['request']['principal'], NORTH if number == 0 else SOUTH)
            stale = self.clerk.receive(*self.post('stale-' + str(number), alias))
            self.assertEqual(stale['reply']['data'], 'stale read root')
        self.assertEqual(self.root()['state']['game']['winner'], 1)
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
            self.assertEqual(self.root()['state']['game']['status'], status)
            self.assertIn('Marked: A1', public['text'])
            self.assertIn('last pair conflicted' if status == 1 else 'last pair was invalid', public['text'])

    def test_only_exact_qualified_core_and_companion_metadata_are_accepted(self):
        qualified = generate.table.protocol(self.table)
        program = generate.protocol(self.table)
        self.assertTrue(companion.client.same_game(qualified, qualified))
        self.assertTrue(companion.client.same_game(program, qualified))
        mutations = [lambda p: p['commands']['resolve']['set'].update(round=['literal', 99]),
                     lambda p: p['initial'].update(width=7),
                     lambda p: p['initial'].update(round=False),
                     lambda p: p.update(extraExecutionRoute={}),
                     lambda p: p['commands'].update(cheat=copy.deepcopy(p['commands']['resolve'])),
                     lambda p: p['viewProgram'].update(extra='unvalidated'),
                     lambda p: p['affordances'].update(cheat={'fields': {}}),
                     lambda p: p['viewPanels'].append({'id': 'unknown', 'label': 'Unknown'}),
                     lambda p: p.update(description=False)]
        for mutate in mutations:
            changed = copy.deepcopy(program)
            mutate(changed)
            self.assertFalse(companion.client.same_game(changed, qualified))
            with self.assertRaisesRegex(ValueError, 'unchanged qualified'):
                companion.capture({**self.root(), 'protocol': changed}, self.table, self.book)
        bare = {**self.root(), 'protocol': qualified}
        with self.assertRaisesRegex(ValueError, 'Install the companion'):
            companion.capture(bare, self.table, self.book)


if __name__ == '__main__':
    unittest.main()
