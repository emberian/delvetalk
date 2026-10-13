"""Repository epochs (ATPROTO L3 finding 4), using test_repo's fake journal and CAR reader.

Refuted by a no-tick carried journal regressing its rev, a replacement key signing an old rev,
changed record keys at rotation, a delta losing post-cursor records, or a restart changing bytes.
No Lean host is needed; deterministic signing requires cryptography >= 43.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_repo import NS, ORIGIN, OWNER, REPO, World, leaves, signs
from transport.atproto import sign
from transport.atproto.cbor import decode, encode, read_car
from transport.atproto.mst import find
from transport.carry import copy_transport
from transport.repo import MINUTE, Repo
from transport.state import State


@signs
class RepositoryEpochs(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.st = State(tmp.name)
        self.a, self.b = sign.Key.generate(), sign.Key.generate()
        self.world = World(page=100)
        for i in range(103):  # crosses the host's maximum page length
            self.world.append(*(('clock', 'advance:29000000') if i == 2 else (OWNER, f'turn-{i}')))

    def repo(self, key, st=None):
        return Repo(ORIGIN, key, ledger=(st or self.st).repo_ledger)

    def read(self, repo, world=None, since=None):
        code, car, _ = repo.serve(world or self.world, 'GET', 'com.atproto.sync.getRepo',
                                  {'did': REPO, **({'since': since} if since else {})}, None)
        self.assertEqual(code, 200, car)
        [cid], blocks = read_car(car)
        return car, cid, decode(blocks[cid]), blocks

    def records(self, blocks):
        return [decode(b) for b in blocks.values() if decode(b).get('$type') == NS + 'entry']

    def test_carry_without_advance_starts_above_old_head_and_restart_is_identical(self):
        old = self.repo(self.a)
        _, _, before, _ = self.read(old)
        old_bytes = self.st.repo_ledger.read_bytes()
        carried = World(start=len(self.world.entries) + 7, page=1)
        carried.append(OWNER, 'carried', tag='carried')
        new_state = State(self.st.root / 'carried')
        copy_transport(self.st.root, new_state.root)
        self.assertEqual(new_state.repo_ledger.read_bytes(), old_bytes)
        new = self.repo(self.a, new_state)
        first_car, _, first, first_blocks = self.read(new, carried)
        self.assertGreater(first['rev'], before['rev'])
        self.assertIsNone(first['prev'])
        self.assertEqual([decode(first_blocks[v])['height'] for _, v in leaves(first_blocks, first['data'])], [111])
        ledger = json.loads(new_state.repo_ledger.read_text())
        self.assertEqual(ledger['base'], 110)
        self.assertEqual(ledger['epochs'], [{'height': 111, 'clock': 29000001, 'cause': 'carry'}])
        self.assertEqual(first['rev'], sign.tid(29000001 * MINUTE + 111))
        first_ledger_bytes = new_state.repo_ledger.read_bytes()
        self.assertEqual(self.read(self.repo(self.a, new_state), carried)[0], first_car)
        self.assertEqual(new_state.repo_ledger.read_bytes(), first_ledger_bytes)
        carried.append(OWNER, 'after-carry')
        car, cid, head, blocks = self.read(new, carried)
        self.assertEqual([decode(blocks[v])['height'] for _, v in leaves(blocks, head['data'])], [111, 112])
        self.assertEqual(head['prev'], read_car(first_car)[0][0])
        ledger_bytes = new_state.repo_ledger.read_bytes()
        twin = self.repo(self.a, new_state)
        self.assertEqual(self.read(twin, carried)[:3], (car, cid, head))
        self.assertEqual(new_state.repo_ledger.read_bytes(), ledger_bytes)

    def test_rotation_preserves_tree_and_old_since_then_append_chains_from_sync(self):
        old = self.repo(self.a)
        _, _, before, old_blocks = self.read(old)
        old_revs = [x.rev for x in old.signed.heights]
        new = self.repo(self.b)
        car, sync_cid, sync, blocks = self.read(new)
        self.assertGreater(sync['rev'], before['rev'])
        self.assertEqual(sync['rev'], sign.tid(29000001 * MINUTE))
        self.assertEqual(sync['data'], before['data'])
        self.assertIsNone(sync['prev'])
        unsigned = encode({k: v for k, v in sync.items() if k != 'sig'})
        self.assertTrue(sign.verify(sign.public_key(self.b.did_key), unsigned, sync['sig']))
        self.assertFalse(sign.verify(sign.public_key(self.a.did_key), unsigned, sync['sig']))
        self.assertEqual([x.rev for x in new.signed.heights], old_revs)
        self.assertTrue(all(x.commit is None for x in new.signed.heights))
        self.assertEqual(leaves(blocks, sync['data']), leaves(old_blocks, before['data']))
        # Only the sync commit is signed with B: old heights require A, which is no longer in hand.
        with patch.object(self.b, 'commit', wraps=self.b.commit) as commits:
            twin = self.repo(self.b)
            self.assertEqual(self.read(twin)[0], car)
            self.assertEqual(commits.call_count, 1)
        _, _, _, delta = self.read(new, since=old_revs[3])
        self.assertEqual([r['height'] for r in self.records(delta)], list(range(5, 104)))
        self.assertEqual(leaves({**old_blocks, **delta}, sync['data']), leaves(blocks, sync['data']))
        code, proof, _ = new.serve(self.world, 'GET', 'com.atproto.sync.getRecord',
                                  {'did': REPO, 'collection': NS + 'entry', 'rkey': old_revs[0]}, None)
        self.assertEqual(code, 200, proof)
        [root], proof_blocks = read_car(proof)
        self.assertEqual(root, sync_cid)
        self.assertEqual(find(proof_blocks, sync['data'], (NS + 'entry/' + old_revs[0]).encode()),
                         new.signed.heights[0].record[0])
        self.assertEqual(self.records(self.read(new, since=sync['rev'])[3]), [])
        code, _, _ = new.serve(self.world, 'GET', 'com.atproto.repo.getRecord',
                                {'repo': REPO, 'collection': NS + 'entry', 'rkey': sync['rev']}, None)
        self.assertEqual(code, 400)  # a sync rev is a delta cursor, not an entry record key
        self.world.append(OWNER, 'after-rotation')
        car, _, head, _ = self.read(new)
        self.assertEqual(head['prev'], sync_cid)
        self.assertGreater(head['rev'], sync['rev'])
        self.assertEqual([r['height'] for r in self.records(self.read(new, since=sync['rev'])[3])], [104])
        ledger_bytes = self.st.repo_ledger.read_bytes()
        self.assertEqual(self.read(self.repo(self.b))[0], car)
        self.assertEqual(self.st.repo_ledger.read_bytes(), ledger_bytes)

    def test_same_key_restart_writes_nothing_and_return_to_a_is_another_epoch(self):
        a = self.repo(self.a)
        car, _, head, _ = self.read(a)
        ledger_bytes = self.st.repo_ledger.read_bytes()
        commits = [x.commit for x in a.signed.heights]
        with patch.object(State, 'write', wraps=State.write) as writes:
            twin = self.repo(self.a)
            self.assertEqual(self.read(twin)[0], car)
            self.assertEqual([x.commit for x in twin.signed.heights], commits)
            self.read(twin)
            writes.assert_not_called()
        self.assertEqual(self.st.repo_ledger.read_bytes(), ledger_bytes)
        b = self.repo(self.b)
        _, _, second, _ = self.read(b)
        again = self.repo(self.a)
        car, _, third, _ = self.read(again)
        self.assertLess(head['rev'], second['rev'])
        self.assertLess(second['rev'], third['rev'])
        self.assertEqual(third['rev'], sign.tid(29000002 * MINUTE))
        ledger = json.loads(self.st.repo_ledger.read_text())
        self.assertEqual(ledger['key'], self.a.did_key)
        self.assertEqual(ledger['epochs'], [
            {'height': 103, 'clock': 29000001, 'cause': 'rotation'},
            {'height': 103, 'clock': 29000002, 'cause': 'rotation'}])
        self.assertEqual(self.read(self.repo(self.a))[0], car)
        self.assertEqual(self.records(self.read(again, since=second['rev'])[3]), [])

    def test_catch_up_without_new_entries_does_no_ledger_io_after_load_or_write(self):
        repo = self.repo(self.a)
        self.read(repo)
        twin = self.repo(self.a)
        self.read(twin)  # snapshots must be retained both after writing and after loading
        for signed in (repo.signed, twin.signed):
            head = signed.head
            with (patch.object(Path, 'read_text') as reads,
                  patch.object(Path, 'exists') as stats,
                  patch.object(State, 'write') as writes):
                self.assertEqual(signed.catch_up(self.world), head)
                reads.assert_not_called()
                stats.assert_not_called()
                writes.assert_not_called()
        self.world.append(OWNER, 'after-snapshot')
        with patch.object(State, 'write', wraps=State.write) as writes:
            self.read(twin)
            writes.assert_called_once()
            self.read(twin)
            writes.assert_called_once()  # advancing the snapshot prevents another write on the same head

    def test_rotation_before_catching_new_entries_places_sync_at_last_served_height(self):
        old = self.repo(self.a)
        self.read(old)
        old_records = [x.record for x in old.signed.heights]
        self.world.append(OWNER, 'not-yet-served')
        self.world.append('clock', 'advance:29000020')
        new = self.repo(self.b)
        car, _, head, _ = self.read(new)
        self.assertEqual([x.record for x in new.signed.heights[:103]], old_records)
        self.assertTrue(all(x.commit is None for x in new.signed.heights[:103]))
        first_after = decode(new.signed.heights[103].commit[1])
        sync_rev = sign.tid(29000001 * MINUTE)
        expected_sync = self.b.commit(REPO, decode(old.signed.head.commit[1])['data'], sync_rev, None)
        self.assertEqual(first_after['prev'], expected_sync[0])
        self.assertGreater(first_after['rev'], sync_rev)
        self.assertEqual(head['rev'], sign.tid(29000020 * MINUTE + 105))
        self.assertEqual([r['height'] for r in self.records(self.read(new, since=sync_rev)[3])], [104, 105])
        self.assertEqual(self.read(self.repo(self.b))[0], car)

    def test_empty_journal_initializes_ledger_but_cannot_change_a_served_chain(self):
        empty = World()
        repo = self.repo(self.a)
        self.assertIsNone(repo.signed.catch_up(empty))
        self.assertEqual(json.loads(self.st.repo_ledger.read_text()),
                         {'key': self.a.did_key, 'base': 0, 'epochs': [], 'head': None})
        car = self.read(repo)[0]
        ledger_bytes = self.st.repo_ledger.read_bytes()
        self.assertIsNone(self.repo(self.b).signed.catch_up(empty))
        self.assertEqual(self.st.repo_ledger.read_bytes(), ledger_bytes)
        self.assertEqual(self.read(self.repo(self.a))[0], car)

    def test_carry_with_a_replacement_key_is_one_epoch_over_only_carried_records(self):
        old = self.repo(self.a)
        _, _, before, _ = self.read(old)
        carried = World(start=110)
        carried.append(OWNER, 'carry-and-key')
        new = self.repo(self.b)
        car, _, head, blocks = self.read(new, carried)
        self.assertGreater(head['rev'], before['rev'])
        self.assertIsNone(head['prev'])
        self.assertEqual([decode(blocks[v])['height'] for _, v in leaves(blocks, head['data'])], [111])
        ledger = json.loads(self.st.repo_ledger.read_text())
        self.assertEqual(ledger['key'], self.b.did_key)
        self.assertEqual(ledger['epochs'], [{'height': 111, 'clock': 29000001, 'cause': 'carry'}])
        self.assertEqual(self.read(self.repo(self.b), carried)[0], car)

    def test_heads_increase_without_any_rev_naming_two_cids_across_carries_and_rotations(self):
        served = []
        def observe(repo, world):
            _, cid, head, _ = self.read(repo, world)
            served.append((head['rev'], cid))
            # Every public head route must name the sync commit when at an epoch boundary.
            code, latest, _ = repo.serve(world, 'GET', 'com.atproto.sync.getLatestCommit', {'did': REPO}, None)
            self.assertEqual((code, latest), (200, {'rev': head['rev'], 'cid': str(cid)}))
            self.assertEqual(repo.serve(world, 'GET', 'com.atproto.sync.getRepoStatus', {'did': REPO}, None)[1]['rev'], head['rev'])
            self.assertEqual(repo.serve(world, 'GET', 'com.atproto.sync.listRepos', {}, None)[1]['repos'][0]['head'], str(cid))
        repo, world = self.repo(self.a), self.world
        observe(repo, world)
        for key in (self.b, self.a):
            repo = self.repo(key)
            observe(repo, world)
        world = World(start=110)
        world.append(OWNER, 'carry-1')
        repo = self.repo(self.a)
        observe(repo, world)
        repo = self.repo(self.b)
        observe(repo, world)
        world.append('clock', 'advance:1')  # a tick below the epoch floor cannot lower it
        observe(repo, world)
        world = World(start=120)
        world.append(OWNER, 'carry-2')
        repo = self.repo(self.b)
        observe(repo, world)
        repo = self.repo(self.a)
        observe(repo, world)
        self.assertEqual(len({rev for rev, _ in served}), len(served))
        self.assertTrue(all(a[0] < b[0] for a, b in zip(served, served[1:])), served)
        self.assertEqual(self.read(self.repo(self.a), world)[1], served[-1][1])


if __name__ == '__main__':
    unittest.main()
