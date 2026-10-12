"""ATPROTO L4 consumer control: real RFC 6455 sockets over test_repo's fake journal.

Refuted by any of 1,000 append events failing sparse inversion, a replay byte changing, a gap or
repeat at live handoff, a pinned HTTP worker, or downtime/rotation/carry reusing a sequence position.
Requires cryptography >= 43, no Lean host.
"""
import http.client
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tests.test_repo import World, OWNER, ORIGIN, REPO, Provider, signs
from tests.test_firehose import inverse
from tests.firehose_client import Consumer
from transport import delve, identity
from transport.atproto import sign
from transport.atproto.cbor import CID, decode, encode, read_car
from transport.carry import copy_transport
from transport.config import Config
from transport.firehose import EventLog, Firehose, ROUTE
from transport.http import Front
from transport.repo import Repo
from transport.state import State


@signs
class FirehoseConsumer(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.st = State(tmp.name)
        self.key = sign.Key.generate()
        self.world = World(page=100)
        self.world.append(OWNER, 'initial')
        self.repo = Repo(ORIGIN, self.key, ledger=self.st.repo_ledger)

    def start(self, repo=None, world=None, st=None):
        hose = Firehose(repo or self.repo, world or self.world, (st or self.st).firehose,
                        address=('127.0.0.1', 0), interval=0.01)
        hose.start()
        self.addCleanup(hose.close)
        return hose

    def client(self, hose, query=''):
        c = Consumer(hose.address, query)
        self.addCleanup(c.close)
        return c

    def wait_seq(self, hose, seq):
        deadline = time.monotonic() + 30
        while hose.log.tail < seq:
            self.assertIsNone(hose.error)
            if time.monotonic() >= deadline:
                self.fail(f'event {seq} not logged; tail {hose.log.tail}')
            time.sleep(0.01)

    def test_thousand_live_commits_sparse_inverse_continuity_and_exact_cursor_replay(self):
        hose = self.start()
        c = self.client(hose, '?cursor=1')
        _, initial = read_car(self.repo.signed.repo())
        head = decode(initial[self.repo.signed.head.commit[0]])
        previous, rev = head['data'], head['rev']
        def append():
            for i in range(1000):
                self.world.append(OWNER, f'live-{i}')
        writer = threading.Thread(target=append)
        writer.start()
        self.addCleanup(writer.join)
        saved = {}
        for seq in range(2, 1002):
            header, body, raw = c.event()
            self.assertEqual(header, {'op': 1, 't': '#commit'})
            self.assertEqual(body['seq'], seq)
            self.assertEqual((body['prevData'], body['since']), (previous, rev))
            self.assertFalse(body['rebase'])
            self.assertFalse(body['tooBig'])
            self.assertEqual(body['blobs'], [])
            [root], blocks = read_car(body['blocks'])
            self.assertEqual(root, body['commit'])
            commit = decode(blocks[root])
            self.assertEqual(commit['rev'], body['rev'])
            record = decode(blocks[body['ops'][0]['cid']])
            self.assertEqual(record, {'$type': 'online.fg-goose.gsb.entry', 'height': seq,
                                      'entry': CID.parse(self.world.entries[seq - 1]['hash'])})
            self.assertTrue(body['time'].endswith('Z'))
            self.assertEqual(inverse(blocks, commit['data'], body['ops']), previous)
            self.assertTrue(sign.verify(self.key.private.public_key(),
                                       encode({k: v for k, v in commit.items() if k != 'sig'}), commit['sig']))
            self.assertGreater(body['rev'], rev)
            self.assertEqual(body['ops'], [{'action': 'create', 'path': 'online.fg-goose.gsb.entry/' + body['rev'],
                                           'cid': self.repo.signed.heights[seq - 1].record[0]}])
            previous, rev = commit['data'], body['rev']
            saved[seq] = raw
            if seq == 500:
                c.close()
                c = self.client(hose, '?cursor=500')
        again = self.client(hose, '?cursor=500')
        for seq in range(501, 1002):
            _, body, raw = again.event()
            self.assertEqual((body['seq'], raw), (seq, saved[seq]))
        self.world.append(OWNER, 'handoff-live')
        self.assertEqual(again.event()[1]['seq'], 1002)
        writer.join()

    def test_first_append_to_an_empty_running_world_is_a_commit_from_empty_tree(self):
        self.world = World(page=100)
        hose = self.start()
        c = self.client(hose)
        self.world.append(OWNER, 'first-live')
        header, body, _ = c.event()
        self.assertEqual((header['t'], body['seq'], body['since'], body['prevData']), ('#commit', 1, None, None))
        [root], blocks = read_car(body['blocks'])
        self.assertIsNone(inverse(blocks, decode(blocks[root])['data'], body['ops']))

    def test_future_invalid_outdated_cursor_and_no_cursor_live_only(self):
        with patch('transport.firehose.WINDOW', 3):
            hose = self.start()
            live = self.client(hose)
            for i in range(8):
                self.world.append(OWNER, f'window-{i}')
            self.wait_seq(hose, 9)
            self.assertEqual(live.event()[1]['seq'], 2)
            for query, error in (('?cursor=999999999', 'FutureCursor'), ('?cursor=wat', 'InvalidRequest'),
                                 ('?cursor=1.5', 'InvalidRequest'), ('?cursor=', 'InvalidRequest'),
                                 ('?cursor=1&cursor=2', 'InvalidRequest'),
                                 ('?cursor=' + '9' * 5000, 'FutureCursor')):
                c = self.client(hose, query)
                h, b, _ = c.event()
                self.assertEqual((h, b['error']), ({'op': -1}, error))
                self.assertEqual(c.raw()[0], 8)
                with self.assertRaises(EOFError):
                    c.take(1)
            old = self.client(hose, '?cursor=0')
            h, b, _ = old.event()
            self.assertEqual((h, b), ({'op': 1, 't': '#info'}, {'name': 'OutdatedCursor'}))
            retained = hose.log.retained()
            for e in retained:
                self.assertEqual(old.event()[2], e.frame)

    def test_restart_downtime_rotation_identity_and_carried_log_continue_seq(self):
        hose = self.start()
        self.world.append(OWNER, 'running')
        self.wait_seq(hose, 2)
        original = hose.log.retained()
        hose.close()
        self.world.append(OWNER, 'down-1')
        self.world.append(OWNER, 'down-2')
        repo = Repo(ORIGIN, self.key, ledger=self.st.repo_ledger)
        restarted = self.start(repo)
        self.assertEqual(restarted.log.tail, 3)
        self.assertEqual(restarted.log.retained()[:2], original)
        c = self.client(restarted, '?cursor=2')
        h, b, _ = c.event()
        self.assertEqual((h['t'], b['seq'], b['rev']), ('#sync', 3, repo.signed.head.rev))
        self.assertEqual(len(read_car(b['blocks'])[1]), 1)
        restarted.close()
        unchanged = self.start(Repo(ORIGIN, self.key, ledger=self.st.repo_ledger))
        self.assertEqual(unchanged.log.tail, 3)
        unchanged.close()
        rotated_repo = Repo(ORIGIN, sign.Key.generate(), ledger=self.st.repo_ledger)
        rotated = self.start(rotated_repo)
        c = self.client(rotated, '?cursor=3')
        h, b, _ = c.event()
        self.assertEqual((h['t'], b['seq'], b['did'], b['handle']), ('#identity', 4, REPO, self.repo.handle))
        h, b, _ = c.event()
        self.assertEqual((h['t'], b['seq'], b['rev']), ('#sync', 5, rotated_repo.signed.head.rev))
        rotated.close()
        moved = State(self.st.root / 'new-state')
        copy_transport(self.st.root, moved.root)
        self.assertEqual(EventLog(moved.firehose).retained(), rotated.log.retained())
        carried = World(start=100)
        carried.append(OWNER, 'carry', tag='carried')
        new = self.start(Repo(ORIGIN, rotated_repo.signed.key, ledger=moved.repo_ledger), carried, moved)
        c = self.client(new, '?cursor=5')
        self.assertEqual((c.event()[0]['t'], new.log.tail), ('#sync', 6))
        carried.append(OWNER, 'after-carry')
        h, b, _ = c.event()
        self.assertEqual((h['t'], b['seq'], b['since']), ('#commit', 7, new.repo.signed.heights[0].rev))

    def test_ten_subscribers_leave_one_front_worker_free_and_controls_validate_masking(self):
        config = Config(repo_keys=str(self.st.root), firehose_port=1)
        st = State(self.st.root, config=config)
        st.repo_key.write_bytes(self.key.pem())
        ident = identity.Identity(st, delve.Client(Provider()))
        front = Front(st, self.world, ident, ('127.0.0.1', 0), workers=1,
                      firehose_address=('127.0.0.1', 0))
        self.addCleanup(front.server_close)
        thread = threading.Thread(target=front.serve_forever)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(front.shutdown)
        hose = front.firehose
        clients = [self.client(hose) for _ in range(10)]
        conn = http.client.HTTPConnection(*front.server_address, timeout=5)
        self.addCleanup(conn.close)
        conn.request('GET', '/xrpc/com.atproto.sync.getLatestCommit?did=' + REPO)
        reply = conn.getresponse()
        self.assertEqual(reply.status, 200, reply.read())
        conn.request('GET', ROUTE)
        reply = conn.getresponse()
        self.assertEqual(reply.status, 426, reply.read())
        self.assertEqual(reply.getheader('Upgrade'), 'websocket')
        self.world.append(OWNER, 'ten-subscribers')
        for c in clients:
            self.assertEqual(c.event()[1]['seq'], 2)
        c = clients[0]
        c.control(9, b'x' * 125)
        self.assertEqual(c.raw(), (10, b'x' * 125))
        c.control(10, b'pong')
        c.control(8, struct.pack('!H', 1000))
        self.assertEqual(c.raw()[0], 8)
        bad = clients[1]
        bad.control(9, b'unmasked', masked=False)
        self.assertEqual(bad.raw(), (8, struct.pack('!H', 1002)))


if __name__ == '__main__':
    unittest.main()
