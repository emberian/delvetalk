"""`delvetalk-obend serve` is the one writer of a directory of worlds (HOST-HANDOFF 5.125; docs/FEDERATION.md §1,
docs/ROOT.md §1.4): named worlds and the root socket beside the public one.

Evidence for FOUNDATION §7 (layer: host). Refuted by a socket others may open, a second writer that starts, a
chain broken under concurrent clients, a restart that answers a retried turn differently, a scratch world or the
stateless session that sees the world, a library without arrival's packages, a world opened under another name, or an
opener's op or a root op that the public socket takes. A test's serve outlives its test process: refuted by a serve
still running seconds after the process that started it died of SIGTERM or (Linux) SIGKILL.
"""
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import threading
import unittest
from pathlib import Path

from transport.journal import copy as journal_copy
from transport.journal import entries as journal_entries
from tests.host import Host, binary, served as Served
from tests.test_reflection import WORLD_LIBRARY
from transport.host import HostClient
from tests.wire import nat, record
from tests.bend import counter_modules, declared

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
        cls.server = Served(str(cls.state), cleanup=cls.addClassCleanup, opener=OPENER, library=WORLD_LIBRARY)
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
        pid = self.state / 'serve.pid'
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
        journal_copy(self.state / 'town.journal', copy)
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

    def test_scratch_worlds_are_separate_worlds_in_one_server_and_the_repl_runs_only_in_one(self):
        opened = self.client.send({'op': 'world-scratch', 'principal': DID, 'name': 'apart'})
        self.assertEqual((opened['status'], opened['world']), ('scratch', 'scratch/apart'), opened)
        scratch = HostClient(self.sock, world='scratch/apart')
        self.assertEqual(scratch.send({'op': 'world-view', 'principal': DID, 'object': self.c})['status'], 'unknown')
        self.assertTrue((self.state / 'scratch' / DID / 'apart.journal').exists())
        self.assertEqual(HostClient(self.sock, world='scratch/../../etc').send({'op': 'world-status', 'principal': DID})['status'], 'error')
        self.assertEqual(HostClient(self.sock, world='scratch/apart').send({'op': 'world-status', 'principal': '../x'})['status'], 'error')
        self.assertEqual(self.client.send({'op': 'world-view', 'principal': 'e', 'object': self.c})['status'], 'viewed')
        self.assertIn('scratch world', self.client.send({'op': 'world-repl', 'principal': DID, 'identity': 'r', 'entry': 'x'})['message'])
        for op in ('world-relay', 'world-cross'):  # serve's own, on neither socket
            self.assertIn("serve's own", self.client.send({'op': op, 'principal': DID})['message'])

    def test_the_town_is_opened_by_the_opener_with_arrivals_packages_sealed(self):
        who = 'did:plc:' + 'q' * 24
        got = self.client.send({'op': 'world-arrive', 'principal': 'transport', 'did': who, 'handle': 'q.delve.town'})
        self.assertEqual([c['object'] for c in got.get('created', [])], [who], got)
        settings = [e['outcome'] for e in journal_entries(self.state / 'town.journal')
                    if e['outcome'].get('tag') == 'settings']
        self.assertEqual(settings[0]['opener'], OPENER)

    def test_serve_status_names_the_library_and_the_town_compiles_by_its_pin(self):
        info = self.client.send({'op': 'serve-status'})
        replay = self.client.send({'op': 'world-status'})['replay']
        self.assertEqual((info['status'], info['pid'], info['replay']), ('serve', self.server.proc.pid, replay), info)
        self.assertRegex(info['hostSha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(self.client.send({'op': 'serve-status'})['hostSha256'], info['hostSha256'])
        town = next(w for w in info['worlds'] if w['name'] == 'town')
        self.assertEqual((town['replay'], town['snapshot']), (replay, {'resumed': 0, 'refused': []}), town)
        checked = self.client.send({'op': 'check-package', 'library': info['library'], 'entry': 'initial',
                                                             'modules': [{'name': 'Tally', 'source': TALLY}]})
        self.assertEqual(checked['status'], 'checked', checked)

    def test_the_library_is_sealed_so_one_module_imports_it_by_name_in_the_town_and_in_a_heap(self):
        one = [{'name': 'Tally', 'source': TALLY}]
        self.client.send({'op': 'world-scratch', 'principal': DID, 'name': 'sealed'})
        for client, who, name in ((HostClient(self.root), OPENER, 'tally-town'), (HostClient(self.sock, world='scratch/sealed'), DID, 't')):
            made = client.send({'op': 'world-create', 'principal': who, 'identity': 'mk-' + name, 'object': name,
                                'modules': one, 'entry': 'initial', 'seed': record()})
            self.assertEqual(made['status'], 'created', made)
            self.assertTrue(made['receipt']['outcome']['compile']['library'])

    def test_a_write_op_on_a_broken_connection_is_not_re_sent_but_a_read_is(self):
        client = HostClient(self.sock)
        client.send({'op': 'world-status'})
        client.local.conn[0].shutdown(2)
        self.assertTrue(client.send({'op': 'world-advance', 'principal': 'transport', 'height': 1})['message'].startswith(f'the host is unavailable at {self.sock} after '))
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
            server = Served(str(Path(d) / 'state'), cleanup=self.addCleanup, host_socket=sock, root_group=group)
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
            server = Served(state, cleanup=self.addCleanup)
            try:
                client = HostClient(server.sock)
                client.send({'op': 'world-create', 'principal': 'e', 'identity': 'mk', 'object': 'c',
                             'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
                bump = lambda i: client.send({'op': 'world-turn', 'principal': 'e', 'object': 'c', 'method': 'bump', 'argument': record(), 'identity': 'k%d' % i})
                first = [bump(i) for i in range(3)]
                held = client.local.conn[0]
                self.assertEqual(send(server.root, {'op': 'world-snapshot', 'principal': 'transport'})['status'], 'snapshot')
                height = client.send({'op': 'world-status'})['height']
            finally:
                server.stop()
            self.assertFalse(os.path.exists(server.sock))
            server = Served(state, cleanup=self.addCleanup)
            try:
                again = [bump(i) for i in range(3)]
                self.assertIsNot(client.local.conn[0], held)
                self.assertEqual([a['receipt'] for a in again], [f['receipt'] for f in first])
                self.assertEqual(client.send({'op': 'world-view', 'principal': 'e', 'object': 'c'})['version'], 3)
                # The live service says it opened from the snapshot: the height it resumed at.
                town = client.send({'op': 'serve-status'})['worlds'][0]
                self.assertEqual((town['name'], town['height'], town['snapshot']['resumed']), ('town', height, height), town)
                client.close()
            finally:
                server.stop()

    def test_a_journal_holding_another_name_is_not_opened_under_this_one(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / 'state'
            server = Served(str(state), cleanup=self.addCleanup)
            try:
                self.assertEqual(send(server.sock, {'op': 'world-status', 'world': 'ring'})['status'], 'world')
            finally:
                server.stop()
            journal_copy(state / 'ring.journal', state / 'moor.journal')
            server = Served(str(state), cleanup=self.addCleanup)
            try:
                r = send(server.sock, {'op': 'world-status', 'world': 'moor'})
                self.assertEqual(r['status'], 'error', r)
                self.assertIn('this journal is the world ring, not moor', r['message'])
            finally:
                server.stop()



class Startup(unittest.TestCase):
    """A town's first op waits for its serve (persvati at load 31: a second town's first request met a socket not yet up)."""

    def test_a_client_waits_for_a_socket_that_comes_up_and_names_one_that_does_not(self):
        import socket as sockets
        import time
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 'late.sock')

            def late():  # a server that binds half a second after the client first asks
                time.sleep(0.5)
                srv = sockets.socket(sockets.AF_UNIX)
                srv.bind(path)
                srv.listen(1)
                conn, _ = srv.accept()
                conn.makefile('rb').readline()
                conn.sendall(b'{"status": "serve"}\n')
                conn.close()
                srv.close()
            t = threading.Thread(target=late)
            t.start()
            self.assertEqual(HostClient(path).send({'op': 'serve-status'}), {'status': 'serve'})
            t.join()
            gone = HostClient(Path(d) / 'never.sock').send({'op': 'world-status'})
            self.assertRegex(gone['message'], r'^the host is unavailable at .*/never\.sock after [2-9]\.\d s$')

    def test_two_towns_started_together_on_a_slow_start_each_answer_their_first_op(self):
        with tempfile.TemporaryDirectory() as d:
            slow = Path(d) / 'slow-obend'  # the artificial delay: a second before serve itself starts
            slow.write_text(f'#!/bin/sh\nsleep 1\nexec {binary()} "$@"\n')
            slow.chmod(0o755)
            from deploy.serve import Served as Start
            answers, servers = {}, []

            def town(name):
                server = Start(Path(d) / name, slow, cleanup=self.addCleanup)
                servers.append(server)
                answers[name] = HostClient(server.sock).send({'op': 'world-status'}).get('status')
            threads = [threading.Thread(target=town, args=(n,)) for n in ('town', 'moor')]
            [t.start() for t in threads]
            [t.join() for t in threads]
            for server in servers:
                server.stop()
            self.assertEqual(answers, {'town': 'world', 'moor': 'world'})

ORPHAN = """
import os, signal, sys
from tests.host import binary, served
server = served(sys.argv[1], cleanup=lambda stop: None)
print(server.proc.pid, os.getsid(server.proc.pid) == server.proc.pid, os.path.dirname(binary()), flush=True)
os.kill(os.getpid(), getattr(signal, sys.argv[2]))
"""


class Orphan(unittest.TestCase):
    """A test process that starts serve and dies without its cleanups: serve dies too, within seconds."""

    def died(self, how):
        """(state, serve pid, copy dir) after a child Python started serve over `state` with its own binary copy and
        sent itself `how`; the child's exit is the signal's."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = os.path.join(tmp.name, 'state')
        env = {k: v for k, v in os.environ.items() if k != 'DELVETALK_OBEND_COPY'}
        env.update(DELVETALK_OBEND=binary(), PYTHONPATH=str(Path(__file__).resolve().parent.parent))
        child = subprocess.Popen([sys.executable, '-c', ORPHAN, state, how], env=env, stdout=subprocess.PIPE, text=True)
        pid, own_session, copy = child.stdout.readline().split()
        child.stdout.close()
        self.assertEqual(child.wait(timeout=120), -getattr(signal, how))
        self.assertEqual(own_session, 'True')
        return state, int(pid), copy

    def gone_within(self, pid, state, seconds=5):
        """Whether serve `pid` over `state` stops running within `seconds` (a zombie, or the PID reused, is gone)."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            ps = subprocess.run(['ps', '-o', 'stat=,args=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
            if not ps or ps.startswith('Z') or state not in ps:
                return True
            time.sleep(0.1)
        return False

    def test_a_serve_stops_and_the_copy_goes_when_its_test_process_is_terminated(self):
        state, pid, copy = self.died('SIGTERM')
        self.assertTrue(self.gone_within(pid, state))
        self.assertFalse(os.path.exists(os.path.join(state, 'served.pid')))
        self.assertFalse(os.path.exists(copy))

    @unittest.skipUnless(sys.platform.startswith('linux'), 'PR_SET_PDEATHSIG is Linux')
    def test_a_serve_stops_when_its_test_process_is_killed_and_the_next_copy_sweeps_the_dead_one(self):
        from tests.host import sweep_copies
        state, pid, copy = self.died('SIGKILL')
        self.assertTrue(self.gone_within(pid, state))
        with open(os.path.join(state, 'served.pid')) as f:  # nothing ran to remove it: the record of what was started
            self.assertEqual(int(f.read()), pid)
        self.assertTrue(os.path.exists(os.path.join(copy, 'owner.pid')))
        sweep_copies()
        self.assertFalse(os.path.exists(copy))


if __name__ == '__main__':
    unittest.main()
