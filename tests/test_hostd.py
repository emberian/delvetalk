import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from tests.host import Host, binary, start_hostd, stop_hostd
from tests.test_turn_world import counter_modules, nat, record
from transport import bridge
from transport.hostproc import HostClient

DID = 'did:plc:' + 'a' * 24
TALLY = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, Nat>
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
    case _: state.count + 1n
"""


class Hostd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)
        self.d = start_hostd(str(self.state))
        self.addCleanup(stop_hostd, self.d)
        self.sock = self.state / 'host.sock'
        self.client = HostClient(self.sock)
        made = self.client.send({'op': 'world-create', 'principal': 'e', 'identity': 'mk', 'object': 'c1',
                                 'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0))})
        self.assertEqual(made['status'], 'created', made)

    def turn(self, client, intent):
        return client.send({'op': 'world-turn', 'principal': 'e', 'object': 'c1', 'method': 'bump', 'argument': record(), 'identity': intent})

    def test_socket_is_private_and_the_pid_file_is_touched_per_op(self):
        self.assertEqual(stat.S_IMODE(os.stat(self.sock).st_mode), 0o600)
        pid = self.state / 'hostd.pid'
        os.utime(pid, (1, 1))
        self.client.send({'op': 'world-status'})
        self.assertGreater(pid.stat().st_mtime, 1000)

    def test_two_clients_issuing_turns_concurrently_leave_a_valid_chain(self):
        results = {}

        def work(tag):
            c = HostClient(self.sock)
            results[tag] = [self.turn(c, f'{tag}{i}')['status'] for i in range(30)]
        threads = [threading.Thread(target=work, args=(t,)) for t in 'ab']
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results, {'a': ['admitted'] * 30, 'b': ['admitted'] * 30})
        # deploy/verify.sh's logic: replay a copy of the journal in a throwaway host
        copy = self.state / 'copy.journal'
        shutil.copy(self.state / 'world.journal', copy)
        h = Host()
        try:
            opened = h.send(op='world-open', path=str(copy))
        finally:
            h.close()
        self.assertEqual(opened['status'], 'opened', opened)
        self.assertGreaterEqual(opened['height'], 61)  # create + 60 turns (+ what world-open journals), no gap, no duplicate height

    def test_a_second_instance_exits_75(self):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent.parent))
        p = subprocess.run([sys.executable, '-m', 'transport.hostd', '--state', str(self.state), '--journal', str(self.state / 'world.journal')],
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 75)
        self.assertIn('second writer', p.stderr)
        self.assertEqual(self.client.send({'op': 'world-status'})['status'], 'world')  # the first is untouched

    def test_host_death_mid_session_recovers_the_same_receipts(self):
        first = [self.turn(self.client, f'k{i}') for i in range(3)]
        self.d.shared.proc.kill()
        self.d.shared.proc.wait()
        again = [self.turn(self.client, f'k{i}') for i in range(3)]
        self.assertEqual([a['receipt'] for a in again], [f['receipt'] for f in first])
        self.assertEqual(self.client.send({'op': 'world-view', 'principal': 'e', 'object': 'c1'})['version'], 3)

    def test_heaps_and_stateless_are_separate_worlds_in_one_daemon(self):
        heap = HostClient(self.sock, heap=DID)
        self.assertEqual(heap.send({'op': 'world-view', 'principal': 'e', 'object': 'c1'})['status'], 'unknown')
        self.assertTrue((self.state / 'heaps' / f'{DID}.journal').exists())
        self.assertEqual(HostClient(self.sock, heap='../../etc/passwd').send({'op': 'world-status'})['status'], 'error')
        self.assertEqual(HostClient(self.sock).send({'op': 'world-status'})['objects'], 1)
        self.assertEqual(HostClient(self.sock, stateless=True).send({'op': 'compile', 'modules': [], 'entry': 'x'})['status'], 'error')

    def test_the_world_is_opened_with_the_configured_opener(self):
        import tempfile as tf
        with tf.TemporaryDirectory() as d2:
            opened = []
            from transport import hostproc
            real = hostproc.Host._exchange

            def spy(self, req):
                opened.append(req)
                return real(self, req)
            from unittest import mock
            with mock.patch.object(hostproc.Host, '_exchange', spy):
                dd = start_hostd(d2, opener=DID)
                try:
                    dd.shared.send({'op': 'world-status'})
                finally:
                    stop_hostd(dd)
        self.assertEqual([r.get('opener') for r in opened if r['op'] == 'world-open'][:1], [DID])

    def test_the_sealed_library_holds_the_packages_arrival_creates_from(self):
        import tempfile as tf
        from transport.hostproc import LIBRARY
        who = 'did:plc:' + 'q' * 24
        with tf.TemporaryDirectory() as d2:
            dd = start_hostd(d2, opener=DID, library=LIBRARY)
            try:
                got = HostClient(Path(d2) / 'host.sock').send({'op': 'world-arrive', 'principal': 'transport', 'did': who, 'handle': 'q.delve.town'})
                self.assertEqual([c['object'] for c in got.get('created', [])], [who, 'env/' + who, 'wake/' + who], got)
            finally:
                stop_hostd(dd)

    def test_the_library_is_sealed_so_one_module_imports_it_by_name_in_the_world_and_in_a_heap(self):
        import tempfile as tf
        from transport.hostproc import LIBRARY
        one = [{'name': 'Tally', 'source': TALLY}]
        with tf.TemporaryDirectory() as d2:
            dd = start_hostd(d2, opener=DID, library=LIBRARY)
            try:
                for client, who in ((HostClient(Path(d2) / 'host.sock'), DID), (HostClient(Path(d2) / 'host.sock', heap=DID), DID)):
                    made = client.send({'op': 'world-create', 'principal': who, 'identity': 'mk', 'object': 't',
                                        'modules': one, 'entry': 'initial', 'seed': record()})
                    self.assertEqual(made['status'], 'created', made)
                    self.assertTrue(made['receipt']['outcome']['compile']['library'])
                    turned = client.send({'op': 'world-turn', 'principal': who, 'object': 't', 'method': 'bump', 'argument': record(), 'identity': 'b'})
                    self.assertEqual((turned['status'], turned['result']), ('admitted', nat(1)), turned)
            finally:
                stop_hostd(dd)
        # without a library the same module names an import nobody supplied
        made = self.client.send({'op': 'world-create', 'principal': 'e', 'identity': 'mk2', 'object': 't', 'modules': one,
                                 'entry': 'initial', 'seed': record()})
        self.assertEqual(made['status'], 'error', made)

    def test_clients_report_a_missing_daemon_instead_of_raising(self):
        self.assertEqual(HostClient(self.state / 'nope.sock').send({'op': 'world-status'})['message'], 'hostd unavailable')

    def test_bridge_once_on_fresh_state_without_observe_does_not_crash(self):
        out = io.StringIO()
        fresh = self.state / 'fresh-state'
        code = bridge.main(['run', '--state', str(fresh), '--host-socket', str(self.sock), '--once'], out)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue()), {'turns': [], 'failed': []})


if __name__ == '__main__':
    unittest.main()
