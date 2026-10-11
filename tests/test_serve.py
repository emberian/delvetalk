"""`delvetalk-obend serve` is the one writer of a directory of worlds (HOST-HANDOFF 5.125; docs/FEDERATION.md §1,
docs/ROOT.md §1.4): what hostd.py's tests held, now against the Lean server, and its own: named worlds and the
root socket.

Evidence for FOUNDATION §7 (layer: host). Refuted by a socket others may open, a second writer that starts, a
chain broken under concurrent clients, a restart that answers a retried turn differently, a heap or the stateless
session that sees the world, a library without arrival's packages, a world opened under another name, or an
opener's op or a root op that the public socket takes.
"""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from tests.host import Host, binary, served as Served
from tests.test_reflection import WORLD_LIBRARY
from tests.test_turn_world import counter_modules, declared, nat, record
from transport.host import HostClient

DID = 'did:plc:' + 'a' * 24
OPENER = 'did:plc:' + 'o' * 24
TALLY = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})):
    case _: state.count + 1n
""")


def send(path, request):
    return HostClient(path).send(request)


class Serve(unittest.TestCase):
    """One server per class, its town opened by OPENER with the world library sealed."""
    made = 0

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.state = Path(cls.tmp.name) / 'state'
        cls.server = Served(str(cls.state), opener=OPENER, library=WORLD_LIBRARY)
        cls.addClassCleanup(cls.server.stop)
        cls.sock, cls.root = Path(cls.server.sock), Path(cls.server.root)

    def setUp(self):
        self.client = HostClient(self.sock)
        self.addCleanup(self.client.close)
        type(self).made += 1
        self.c = 'c%d' % self.made
        made = self.client.send({'op': 'world-create', 'principal': 'e', 'identity': 'mk-' + self.c, 'object': self.c,
                                 'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
        self.assertEqual(made['status'], 'created', made)

    def turn(self, client, intent):
        return client.send({'op': 'world-turn', 'principal': 'e', 'object': self.c, 'method': 'bump', 'argument': record(), 'identity': self.c + intent})

    def test_the_public_socket_is_private_the_root_socket_its_groups_and_the_pid_file_is_touched_per_op(self):
        self.assertEqual(stat.S_IMODE(os.stat(self.sock).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.root).st_mode), 0o660)
        pid = self.state / 'hostd.pid'
        os.utime(pid, (1, 1))
        self.client.send({'op': 'world-status'})
        self.assertGreater(pid.stat().st_mtime, 1000)
        self.assertEqual(int(pid.read_text()), self.server.proc.pid)

    def test_two_clients_issuing_turns_concurrently_leave_a_valid_chain(self):
        results = {}

        def work(tag):
            c = HostClient(self.sock)
            results[tag] = [self.turn(c, f'{tag}{i}')['status'] for i in range(30)]
            c.close()
        threads = [threading.Thread(target=work, args=(t,)) for t in 'ab']
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results, {'a': ['admitted'] * 30, 'b': ['admitted'] * 30})
        copy = self.state.parent / 'copy.journal'
        shutil.copy(self.state / 'town.journal', copy)
        h = Host()
        try:
            opened = h.send(op='world-open', path=str(copy))
        finally:
            h.close()
        self.assertEqual(opened['status'], 'opened', opened)
        self.assertEqual(opened['name'], 'town')
        self.assertGreaterEqual(opened['height'], 61)

    def test_a_second_instance_exits_75(self):
        p = subprocess.run([binary(), 'serve', '--state', str(self.state)], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 75)
        self.assertIn('second writer', p.stderr)
        self.assertEqual(self.client.send({'op': 'world-status'})['status'], 'world')

    def test_heaps_and_stateless_are_separate_worlds_in_one_server(self):
        heap = HostClient(self.sock, heap=DID)
        self.assertEqual(heap.send({'op': 'world-view', 'principal': 'e', 'object': self.c})['status'], 'unknown')
        self.assertTrue((self.state / 'heaps' / f'{DID}.journal').exists())
        self.assertEqual(HostClient(self.sock, heap='../../etc/passwd').send({'op': 'world-status'})['status'], 'error')
        self.assertEqual(self.client.send({'op': 'world-view', 'principal': 'e', 'object': self.c})['status'], 'viewed')
        self.assertEqual(HostClient(self.sock, stateless=True).send({'op': 'compile', 'modules': [], 'entry': 'x'})['status'], 'error')

    def test_the_town_is_opened_by_the_opener_with_arrivals_packages_sealed(self):
        who = 'did:plc:' + 'q' * 24
        got = self.client.send({'op': 'world-arrive', 'principal': 'transport', 'did': who, 'handle': 'q.delve.town'})
        self.assertEqual([c['object'] for c in got.get('created', [])], [who, 'env/' + who, 'wake/' + who], got)
        settings = [json.loads(l)['outcome'] for l in (self.state / 'town.journal').read_text().splitlines()
                    if json.loads(l)['outcome'].get('tag') == 'settings']
        self.assertEqual(settings[0]['opener'], OPENER)

    def test_the_stateless_session_holds_the_library_and_compiles_by_pin(self):
        info = self.client.send({'op': 'hostd-info'})
        self.assertEqual((info['status'], info['pid'], info['replay']), ('hostd', self.server.proc.pid, 3), info)
        self.assertRegex(info['hostSha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(self.client.send({'op': 'hostd-info'})['hostSha256'], info['hostSha256'])
        checked = HostClient(self.sock, stateless=True).send({'op': 'check-package', 'library': info['library'], 'entry': 'initial',
                                                             'modules': [{'name': 'Tally', 'source': TALLY}]})
        self.assertEqual(checked['status'], 'checked', checked)

    def test_the_library_is_sealed_so_one_module_imports_it_by_name_in_the_town_and_in_a_heap(self):
        one = [{'name': 'Tally', 'source': TALLY}]
        for client, who, name in ((HostClient(self.root), OPENER, 'tally-town'), (HostClient(self.sock, heap=DID), DID, 't')):
            made = client.send({'op': 'world-create', 'principal': who, 'identity': 'mk-' + name, 'object': name,
                                'modules': one, 'entry': 'initial', 'seed': record()})
            self.assertEqual(made['status'], 'created', made)
            self.assertTrue(made['receipt']['outcome']['compile']['library'])

    def test_a_write_op_on_a_broken_connection_is_not_re_sent_but_a_read_is(self):
        client = HostClient(self.sock)
        client.send({'op': 'world-status'})
        client.local.conn[0].shutdown(2)
        self.assertEqual(client.send({'op': 'world-advance', 'principal': 'transport', 'height': 1})['message'], 'hostd unavailable')
        client.send({'op': 'world-status'})
        client.local.conn[0].shutdown(2)
        self.assertEqual(client.send({'op': 'world-status'})['status'], 'world')
        client.close()

    def test_a_named_world_is_its_own_journal_and_names_are_held_to_the_rule(self):
        ring = send(self.sock, {'op': 'world-status', 'world': 'ring'})
        self.assertEqual(ring['status'], 'world', ring)
        self.assertTrue((self.state / 'ring.journal').exists())
        self.assertEqual(send(self.sock, {'op': 'world-view', 'principal': 'e', 'object': self.c, 'world': 'ring'})['status'], 'unknown')
        for bad in ('did', 'Ring', '9lives', 'a' * 33, '../town', 7):
            self.assertEqual(send(self.sock, {'op': 'world-status', 'world': bad})['status'], 'error', bad)
        names = [r['name'] for r in send(self.sock, {'op': 'serve-status'})['worlds']]
        self.assertIn('ring', names)
        self.assertIn('town', names)
        self.assertEqual(send(self.sock, {'op': 'world-open', 'path': '/tmp/x.journal'})['status'], 'error')

    def test_the_root_ops_speak_on_the_root_socket_only(self):
        for request in ({'op': 'world-root', 'principal': OPENER, 'reason': 'r', 'act': {'kind': 'unquiet', 'principal': 'e'}},
                        {'op': 'world-dump', 'principal': OPENER, 'object': self.c},
                        {'op': 'world-library', 'principal': 'e', 'path': WORLD_LIBRARY},
                        {'op': 'world-fork', 'principal': 'e', 'into': str(self.state.parent / 'f.journal')},
                        {'op': 'world-snapshot'}):
            r = send(self.sock, request)
            self.assertEqual((r['status'], r['message']), ('error', 'the opener speaks on the root socket'), request)
        self.assertEqual(send(self.root, {'op': 'world-status', 'principal': OPENER})['status'], 'world')
        snap = send(self.root, {'op': 'world-snapshot'})
        self.assertNotEqual(snap['status'], 'error', snap)

    def test_the_openers_ordinary_turns_are_the_public_sockets_and_its_privileges_the_roots(self):
        """The bridge submits the owner's own posts as resident turns without holding root (ROOT §1.4)."""
        bumped = send(self.sock, {'op': 'world-turn', 'principal': OPENER, 'object': self.c, 'method': 'bump',
                                  'argument': record(), 'identity': self.c + '-opener'})
        self.assertEqual(bumped['status'], 'admitted', bumped)
        # Amending another's thing is the opener's privilege: refused on the public socket, admitted on the root.
        amend = lambda sock, intent: send(sock, {'op': 'world-amend', 'principal': OPENER, 'identity': intent, 'object': self.c,
                                                 'version': send(sock, {'op': 'world-view', 'principal': 'e', 'object': self.c})['version'],
                                                 'law': 'law closed: request.kind == 2'})
        public = amend(self.sock, self.c + '-am1')
        self.assertEqual((public['status'], public['receipt']['outcome']['class']), ('refused', 'lawRefused'), public)
        self.assertEqual(amend(self.root, self.c + '-am2')['status'], 'admitted')
        # Naming an owner, and a forged mark on the root socket changes nothing there.
        owned = send(self.sock, {'op': 'world-create', 'principal': OPENER, 'identity': 'mk-own-' + self.c, 'object': self.c + 'o',
                                 'owner': 'e', 'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
        self.assertEqual(owned['status'], 'error', owned)
        self.assertIn('root socket', owned['message'])
        owned = send(self.root, {'op': 'world-create', 'principal': OPENER, 'identity': 'mk-own-' + self.c, 'object': self.c + 'o',
                                 'owner': 'e', 'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0)),
                                 'resident': True})
        self.assertEqual(owned['status'], 'created', owned)

    def test_unquiet_and_the_dump(self):
        quiet = send(self.root, {'op': 'world-root', 'principal': OPENER, 'reason': 'cool off', 'act': {'kind': 'quiet', 'principal': 'm', 'hours': 2}})
        self.assertEqual(quiet['status'], 'root', quiet)
        loud = send(self.root, {'op': 'world-root', 'principal': OPENER, 'reason': 'back', 'act': {'kind': 'unquiet', 'principal': 'm'}})
        self.assertEqual((loud['status'], loud['receipt']['outcome']['kind'], loud['receipt']['outcome']['after']), ('root', 'quiet', None), loud)
        bumped = send(self.sock, {'op': 'world-turn', 'principal': 'm', 'object': self.c, 'method': 'bump', 'argument': record(),
                                  'identity': self.c + '-m'})
        self.assertEqual(bumped['status'], 'admitted', bumped)
        dump = send(self.root, {'op': 'world-dump', 'principal': OPENER, 'object': self.c})
        self.assertEqual({k: dump[k] for k in ('status', 'object', 'owner', 'read', 'fixed', 'supervisor', 'activities')},
                         {'status': 'dump', 'object': self.c, 'owner': '', 'read': 'public', 'fixed': [], 'supervisor': '', 'activities': []}, dump)
        self.assertEqual(set(dump['ledger']), {'depth', 'work', 'storage'}, dump)
        self.assertEqual(send(self.root, {'op': 'world-dump', 'principal': 'e', 'object': self.c})['status'], 'error')


class Placement(unittest.TestCase):
    def test_the_public_socket_may_live_apart_and_the_root_socket_takes_a_group(self):
        import grp
        with tempfile.TemporaryDirectory() as d:
            group = grp.getgrgid(os.getgid()).gr_name
            sock = str(Path(d) / 'front' / 'host.sock')
            server = Served(str(Path(d) / 'state'), extra=('--socket', sock, '--root-group', group))
            try:
                self.assertEqual(send(sock, {'op': 'world-status'})['status'], 'world')
                self.assertFalse((Path(d) / 'state' / 'host.sock').exists())
                self.assertEqual(os.stat(server.root).st_gid, os.getgid())
            finally:
                server.stop()
            self.assertFalse(os.path.exists(sock))
            p = subprocess.run([binary(), 'serve', '--state', str(Path(d) / 'other'), '--root-group', 'no-such-group-here'],
                               capture_output=True, text=True, timeout=60)
            self.assertNotEqual(p.returncode, 0)


class Restart(unittest.TestCase):
    def test_a_restart_replays_to_the_same_receipts_and_a_held_connection_moves_to_the_new_server(self):
        with tempfile.TemporaryDirectory() as d:
            state = str(Path(d) / 'state')
            server = Served(state)
            try:
                client = HostClient(server.sock)
                client.send({'op': 'world-create', 'principal': 'e', 'identity': 'mk', 'object': 'c',
                             'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
                bump = lambda i: client.send({'op': 'world-turn', 'principal': 'e', 'object': 'c', 'method': 'bump', 'argument': record(), 'identity': 'k%d' % i})
                first = [bump(i) for i in range(3)]
                held = client.local.conn[0]
            finally:
                server.stop()
            self.assertFalse(os.path.exists(server.sock))
            server = Served(state)
            try:
                again = [bump(i) for i in range(3)]
                self.assertIsNot(client.local.conn[0], held)
                self.assertEqual([a['receipt'] for a in again], [f['receipt'] for f in first])
                self.assertEqual(client.send({'op': 'world-view', 'principal': 'e', 'object': 'c'})['version'], 3)
                client.close()
            finally:
                server.stop()

    def test_a_journal_holding_another_name_is_not_opened_under_this_one(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / 'state'
            server = Served(str(state))
            try:
                self.assertEqual(send(server.sock, {'op': 'world-status', 'world': 'ring'})['status'], 'world')
            finally:
                server.stop()
            shutil.copy(state / 'ring.journal', state / 'moor.journal')
            server = Served(str(state))
            try:
                r = send(server.sock, {'op': 'world-status', 'world': 'moor'})
                self.assertEqual(r['status'], 'error', r)
                self.assertIn('this journal is the world ring, not moor', r['message'])
            finally:
                server.stop()


if __name__ == '__main__':
    unittest.main()
