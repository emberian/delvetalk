"""Typed participant actions through compiled Lean, including custody recovery."""
import importlib.util
import fcntl
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


p = load('participant_test', 'scripts/table_participant.py')
journey = load('participant_journey_test', 'scripts/table_journey.py')


class TableParticipant(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.db = self.base / 'world.json'
        self.table = 'table:participant'
        self.seats = ['alice', 'bob']
        created = p.desk.world.exchange(self.db,
            p.table.create_request(self.table, *self.seats, 'host', 'create'), profile='compiled')
        self.assertEqual(created['kind'], 'committed')
        self.players = [self.player(i) for i in (0, 1)]

    def player(self, seat, principal=None, directory=None):
        return p.Participant(self.db, directory or self.base / str(seat), self.table,
                             principal or self.seats[seat], seat)

    def act(self, seat, action, fields, intent):
        player = self.players[seat]
        card = player.observe()
        text = 'do ' + card['card'] + ' ' + action + ' ' + p.canonical(fields).decode()
        selected = p.interpret.interpret(text, card)
        self.assertEqual(selected['status'], 'proposed', selected)
        prepared = player.prepare(card['card'], selected['action'], selected['fields'], intent)
        reply = player.send(prepared['prepared'])
        self.assertEqual(reply['kind'], 'committed', reply)
        return prepared, reply

    def test_private_openings_lost_reply_and_full_round(self):
        alice, bob = self.players
        card = alice.observe()
        self.assertEqual([a['id'] for a in card['actions']], ['commit'])
        with self.assertRaisesRegex(ValueError, 'not offered'):
            alice.prepare(card['card'], 'reveal', {}, 'too-early')
        prepared = alice.prepare(card['card'], 'commit', {'source': 0, 'target': 5}, 'alice-seal')
        secret = p.loads(alice._opening(0).read_bytes())
        for public in (card, prepared):
            self.assertNotIn(secret['reveal']['nonce'], str(public))
            self.assertNotIn(secret['commit']['digest'], str(public))
            self.assertNotIn('expected', public)
        for path in alice.custody.rglob('*.json'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        # The host commits, but the caller sees no reply. No local receipt exists.
        exchange = p.desk.world.exchange

        def lost(database, request, **kwargs):
            exchange(database, request, **kwargs)
            raise OSError('simulated reply loss')

        with patch.object(p.desk.world, 'exchange', side_effect=lost):
            with self.assertRaisesRegex(OSError, 'reply loss'):
                alice.send(prepared['prepared'])
        self.assertNotIn(secret['reveal']['nonce'], self.db.read_text())
        before = self.db.read_bytes()
        restarted = self.player(0)
        self.assertEqual(restarted.prepare(card['card'], 'commit', {'source': 0, 'target': 5},
                                          'alice-seal'), prepared)
        recovered = restarted.send(prepared['prepared'])
        self.assertEqual(recovered['kind'], 'committed')
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(restarted.observe()['actions'], [])
        self.act(1, 'commit', {'source': 4, 'target': 9}, 'bob-seal')
        without_opening = self.player(0, directory=self.base / 'lost-custody').observe()
        self.assertEqual(without_opening['actions'], [])
        self.assertIn('Recover the original participant custody', without_opening['prose'])
        for seat in (0, 1):
            self.act(seat, 'reveal', {}, 'open-' + str(seat))
        _, resolved = self.act(0, 'resolve', {}, 'resolve')
        self.assertEqual(resolved['receiptView']['round'], 1)
        self.assertEqual(resolved['receiptView']['status'], 0)
        self.assertIn(secret['reveal']['nonce'], self.db.read_text())

    def test_stale_refusal_is_retained_new_intent_reuses_opening(self):
        alice, bob = self.players
        old = bob.observe()
        stale = bob.prepare(old['card'], 'commit', {'source': 4, 'target': 9}, 'stale')
        original = bob._opening(0).read_bytes()
        self.act(0, 'commit', {'source': 0, 'target': 5}, 'alice')
        refused = bob.send(stale['prepared'])
        self.assertEqual(refused['kind'], 'refused')
        self.assertEqual(refused['reason'], 'stale read root')
        self.assertEqual(self.player(1).send(stale['prepared']), refused)
        fresh = bob.observe()
        with self.assertRaisesRegex(ValueError, 'different choice'):
            bob.prepare(fresh['card'], 'commit', {'source': 4, 'target': 9}, 'stale')
        with self.assertRaisesRegex(ValueError, 'sealed move'):
            bob.prepare(fresh['card'], 'commit', {'source': 4, 'target': 8}, 'changed')
        prepared = bob.prepare(fresh['card'], 'commit', {'source': 4, 'target': 9}, 'fresh')
        self.assertEqual(bob.send(prepared['prepared'])['kind'], 'committed')
        self.assertEqual(bob._opening(0).read_bytes(), original)

    def test_fields_and_authority_remain_separate(self):
        forged = self.player(0, 'bob', self.base / 'forged')
        card = self.players[0].observe()
        for fields in ({'source': True, 'target': 9}, {'source': 0, 'target': 121},
                       {'source': 0, 'target': 5, 'principal': 'alice'}):
            with self.assertRaises(ValueError):
                self.players[0].prepare(card['card'], 'commit', fields, 'bad-fields')
        forbidden = forged.observe()
        self.assertEqual(forbidden['actions'], [])
        self.assertIn('does not hold this seat', forbidden['prose'])
        self.assertEqual(self.players[0].observe()['actions'][0]['id'], 'commit')
        with self.assertRaisesRegex(ValueError, 'custody differs'):
            self.player(0, 'bob')

    def test_conflicts_and_invalid_moves_still_resolve_in_lean(self):
        for number, moves, status in ((0, ((0, 5), (0, 1)), 1), (1, ((0, 5), (4, 9)), 2)):
            for seat in (0, 1):
                self.act(seat, 'commit', dict(zip(('source', 'target'), moves[seat])),
                         f'r{number}-seal{seat}')
            for seat in (0, 1):
                self.act(seat, 'reveal', {}, f'r{number}-open{seat}')
            _, reply = self.act(0, 'resolve', {}, f'r{number}-resolve')
            self.assertEqual(reply['receiptView']['status'], status)
            self.assertEqual(reply['receiptView']['round'], number + 1)
            self.assertEqual(reply['receiptView']['marks'], 1)
            self.assertIn('Marked cells: [0]', self.players[0].observe()['prose'])

    def test_runtime_does_not_silently_rebind(self):
        player = self.players[0]
        card = player.observe()
        prepared = player.prepare(card['card'], 'commit', {'source': 0, 'target': 5}, 'sealed')
        before = self.db.read_bytes()
        with patch.object(p.desk, 'execution_profile', return_value={'profile': 'changed'}):
            reopened = self.player(0)
            self.assertEqual(reopened.runtime, player.runtime)
            with self.assertRaisesRegex(ValueError, 'runtime changed'):
                reopened.send(prepared['prepared'])
            with self.assertRaisesRegex(ValueError, 'runtime changed'):
                reopened.observe()
            with self.assertRaisesRegex(ValueError, 'runtime changed'):
                reopened.prepare(card['card'], 'commit', {'source': 0, 'target': 5}, 'new-intent')
        self.assertEqual(self.db.read_bytes(), before)

    def test_runtime_change_preserves_cached_and_uncertain_receipts(self):
        cached, original = self.act(0, 'commit', {'source': 0, 'target': 5}, 'cached')
        bob = self.players[1]
        card = bob.observe()
        lost = bob.prepare(card['card'], 'commit', {'source': 4, 'target': 9}, 'lost-receipt-save')
        pending = bob.prepare(card['card'], 'commit', {'source': 4, 'target': 9}, 'still-pending')
        admitted = p.desk.world.exchange(self.db, bob._read('requests', lost['prepared'])['request'],
                                        profile='compiled')
        self.assertEqual(admitted['kind'], 'committed')
        self.assertFalse((bob.custody / 'receipts' / (lost['prepared'] + '.json')).exists())
        before = self.db.read_bytes()
        with patch.object(p.desk, 'execution_profile', return_value={'profile': 'changed'}), \
                patch.object(p.desk.world, 'exchange', side_effect=AssertionError('must not execute another runtime')):
            alice, restarted = self.player(0), self.player(1)
            with Path(str(self.db) + '.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(alice.send(cached['prepared']), original)
                with self.assertRaisesRegex(ValueError, 'receipt custody busy'):
                    restarted.send(lost['prepared'])
            recovered = restarted.send(lost['prepared'])
            self.assertEqual(recovered['kind'], 'committed')
            self.assertEqual(recovered['receiptView'], p.client.public_view(admitted['data']['root']))
            self.assertEqual(restarted.send(lost['prepared']), recovered)
            with self.assertRaisesRegex(ValueError, 'runtime changed'):
                restarted.send(pending['prepared'])
        self.assertEqual(self.db.read_bytes(), before)

    def test_bootstrap_match_export_and_reconstruction(self):
        directory = self.base / 'cafe'
        journey.bootstrap.run_bootstrap(directory, profile='compiled')
        manifest = journey.bootstrap.loads((directory / 'manifest.json').read_bytes())
        host = journey.bootstrap.desk_module.Desk(directory / 'world.json', directory / 'artifacts', profile='compiled')
        target = manifest['table']
        program = p.table.protocol(target, *self.seats)
        journey.bootstrap.preserve_lowering(directory, p.canonical(program))
        before = journey.bootstrap.inspect_view(directory)
        self.assertEqual(host.exchange({'op': 'reprogram', 'object': target,
            'principal': manifest['participants'][0], 'intent': 'participant-install',
            'expected': host.inspect(target), 'protocol': program, 'state': program['initial']})['kind'], 'committed')
        self.assertEqual(host.exchange({'op': 'law', 'object': target, 'principal': 'local-operator',
            'intent': 'participant-seats', 'expected': host.inspect(target),
            'law': p.table.law(*self.seats)})['kind'], 'committed')
        self.players = [p.Participant(directory / 'world.json', directory / ('seat-' + str(seat)),
                                     target, self.seats[seat], seat) for seat in (0, 1)]
        for number, moves in enumerate(journey.MATCH):
            for seat in (0, 1):
                self.act(seat, 'commit', dict(zip(('source', 'target'), moves[seat])),
                         f'round-{number}-commit-{seat}')
            for seat in (0, 1):
                self.act(seat, 'reveal', {}, f'round-{number}-reveal-{seat}')
            self.act(0, 'resolve', {}, f'round-{number}-resolve')
        final = host.inspect(target)
        self.assertEqual(p.client.state(final)['game']['winner'], 1)
        self.assertEqual(self.players[0].observe()['actions'], [])
        self.assertIn('game has finished', self.players[0].observe()['prose'])
        self.assertEqual(journey.bootstrap.inspect_view(directory), before)
        exported = journey.bootstrap.export_bootstrap(directory, self.base / 'bundle')
        restored = self.base / 'restored'
        evidence = journey.bootstrap.restore_bootstrap(self.base / 'bundle', restored,
            expected_genesis=exported['genesis'], expected_head=exported['head'])
        self.assertEqual(evidence['head'], exported['head'])
        rebuilt = p.loads((restored / 'world.json').read_bytes())
        self.assertEqual(rebuilt['objects'][target], final)
        self.assertEqual(journey.bootstrap.inspect_view(restored), before)


if __name__ == '__main__':
    unittest.main()
