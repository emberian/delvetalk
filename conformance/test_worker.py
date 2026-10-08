"""Bounded worker journey: mock PDS, actual Lean, no external publication."""
import copy
import os
import subprocess
import time
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import worker
import clerk
import receipts
import delve

spec = importlib.util.spec_from_file_location('worker_live_fixture', ROOT / 'conformance/test_live_path.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.pds = live.PDS()
        self.clerk = clerk.Clerk(self.base / 'clerk', self.pds)
        protocol = clerk.loads((ROOT / 'protocols/counter/protocol.json').read_text())
        self.initial = self.clerk.bootstrap('counter', protocol, [delve.DID], [delve.DID])['data']['root']
        credentials = self.base / 'credentials.json'
        credentials.write_text('{"handle":"' + delve.HANDLE + '","app_password":"mock-password"}')
        self.publisher = receipts.Publisher(delve.Delve(self.base / 'publisher', credentials,
                                                       self.base / 'posts', self.pds))
        self.w = self.restart()

    def restart(self, **kwargs):
        return worker.Worker(self.base / 'worker', self.base / 'clerk', receiver=self.clerk.receive,
                             publisher=self.publisher.publish, **kwargs)

    def request(self, name='one', amount=3, root=None):
        payload = {'object': 'counter', 'command': 'add', 'input': {'amount': amount},
                   'expected': self.initial if root is None else root}
        publication = self.publisher.publish('request', clerk.world.wire_dumps(payload), name)
        return publication['uri'], publication['cid']

    def test_receive_prepare_restart_then_explicit_publication_reconciliation(self):
        uri, cid = self.request()
        self.w.enqueue(uri, cid)
        puts = self.pds.puts
        result = self.w.run()
        self.assertEqual(result['processed'][0]['phase'], 'prepared')
        self.assertEqual(self.pds.puts, puts)  # Default mode never sends.
        entry = clerk.loads(self.w.path(uri).read_text())
        self.assertEqual(entry['receipt']['reply']['data']['root']['state']['count'], 3)
        self.assertEqual(self.restart().run()['processed'], [])
        self.pds.lose_collection = receipts.RECEIPT
        lost = self.restart().run(allow_publication=True)
        self.assertEqual(len(lost['errors']), 1)
        self.assertEqual(clerk.loads(self.w.path(uri).read_text())['phase'], 'prepared')
        resumed = self.restart().run(allow_publication=True)
        self.assertEqual(resumed['processed'][0]['phase'], 'published')
        self.assertEqual(self.pds.puts, puts + 1)
        self.assertEqual(self.clerk.snapshot('counter')['root']['version'], 1)

    def test_crash_after_admission_before_worker_journal_replays_receipt(self):
        uri, cid = self.request()
        self.w.enqueue(uri, cid)
        save = clerk.save
        def crash(path, value):
            if path == self.w.path(uri) and value.get('phase') == 'prepared':
                raise KeyboardInterrupt('simulated process death')
            return save(path, value)
        with patch.object(clerk, 'save', crash):
            with self.assertRaises(KeyboardInterrupt):
                self.w.run()
        self.assertEqual(clerk.loads(self.w.path(uri).read_text())['phase'], 'queued')
        self.pds.records.clear()
        result = self.restart().run()
        self.assertEqual(result['processed'][0]['phase'], 'prepared')
        self.assertEqual(self.clerk.snapshot('counter')['root']['version'], 1)

    def test_discovery_only_exact_machine_shapes_and_retained_identity(self):
        watch_state = self.base / 'watch'
        items = []
        for key, text in [('plain', 'please add 3 to counter @livedelvetalk.delve.town'),
                          ('machine', 'delvetalk-request v1\n```delvetalk-request\n' + clerk.world.wire_dumps({
                              'object': 'counter', 'command': 'add', 'input': {'amount': 2}, 'expected': self.initial}) + '\n```'),
                          ('bad', 'delvetalk-request v1\n```delvetalk-request\n{"op":"law"}\n```')]:
            uri = f'at://{delve.DID}/{delve.POST}/{key}'
            item = {'uri': uri, 'cid': 'cid-' + key, 'record': {'$type': delve.POST, 'text': text}}
            identity = clerk.digest(item)
            clerk.save(watch_state / 'observations' / (identity + '.json'), item)
            items.append((uri, {'cid': item['cid'], 'observation': identity}))
        clerk.save(watch_state / 'index.json', {'format': 'delvetalk-watch-index-v1', 'posts': dict(items)})
        result = self.w.discover(watch_state)
        self.assertEqual(len(result['queued']), 1)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(self.w.discover(watch_state)['queued'], [])
        with self.assertRaisesRegex(ValueError, 'another CID'):
            self.w.enqueue(result['queued'][0]['uri'], 'changed')

    def test_bounds_transport_failures_and_explicit_retry(self):
        uri, cid = self.request()
        self.w.enqueue(uri, cid)
        def fail(uri, cid):
            raise RuntimeError('temporary PDS failure')
        self.w.receiver = fail
        self.assertEqual(len(self.w.run(max_attempts=1)['errors']), 1)
        self.assertEqual(len(self.w.run(max_attempts=1)['blocked']), 1)
        self.w.retry(uri)
        self.w.receiver = self.clerk.receive
        self.assertEqual(self.w.run(max_attempts=1)['processed'][0]['phase'], 'prepared')
        second = self.request('two', root=self.clerk.snapshot('counter')['root'])
        self.w.enqueue(*second)
        ticks = iter([0.0, 2.0, 2.0])
        bounded = self.restart(now=lambda: next(ticks)).run(deadline_seconds=1)
        self.assertTrue(bounded['deadlineReached'])
        self.assertEqual(bounded['processed'], [])
        with self.assertRaisesRegex(ValueError, 'different clerk'):
            worker.Worker(self.base / 'worker', self.base / 'other').enqueue(*second)

    @unittest.skipUnless(os.name == 'posix', 'POSIX process-group custody')
    def test_production_timeout_kills_the_running_grandchild(self):
        heartbeat = self.base / 'heartbeat'
        pidfile = self.base / 'grandchild.pid'
        script = self.base / 'spawn.py'
        child = ("import os,time,pathlib\n"
                 f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid()))\n"
                 f"f=open({str(heartbeat)!r},'ab',buffering=0)\n"
                 "while True:\n f.write(b'x'); time.sleep(0.025)\n")
        script.write_text('import subprocess,sys,time\nsubprocess.Popen([sys.executable, "-c", '
                          + repr(child) + '])\ntime.sleep(60)\n')
        with self.assertRaises(subprocess.TimeoutExpired):
            worker.command([str(script)], 2)
        self.assertTrue(pidfile.exists(), 'grandchild actually started')
        child_pid = int(pidfile.read_text())
        self.assertGreater(heartbeat.stat().st_size, 0, 'grandchild actually executed')
        stopped = heartbeat.read_bytes()
        time.sleep(0.15)
        self.assertEqual(heartbeat.read_bytes(), stopped, 'grandchild performs no work after timeout')
        status = subprocess.run(['ps', '-o', 'stat=', '-p', str(child_pid)], text=True, capture_output=True).stdout.strip()
        self.assertTrue(not status or status.startswith('Z'), 'descendant is gone or reaped-pending, never running: ' + status)

    @unittest.skipUnless(os.name == 'posix', 'POSIX resource limits')
    def test_production_process_receives_cpu_and_platform_memory_bounds(self):
        code = ('import json,resource; print(json.dumps({"cpu":resource.getrlimit(resource.RLIMIT_CPU),'
                '"memory":resource.getrlimit(resource.RLIMIT_AS)}))')
        result = worker.command(['-c', code], 3.2, memory_mib=128)
        self.assertEqual(result['cpu'], [4, 4])
        if sys.platform.startswith('linux'):
            self.assertEqual(result['memory'], [128 * 1024 * 1024] * 2)

    def test_stale_semantic_refusal_prepares_a_terminal_receipt(self):
        first, second = self.request('one'), self.request('two')
        self.w.enqueue(*first)
        self.w.enqueue(*second)
        result = self.w.run(limit=1)
        self.assertEqual(len(result['processed']), 1)
        self.w.run(limit=1)
        entries = [clerk.loads(path.read_text()) for path in (self.base / 'worker/queue').glob('*.json')]
        self.assertEqual(sorted(entry['receipt']['reply']['kind'] for entry in entries), ['committed', 'refused'])
        self.assertTrue(all(entry['phase'] == 'prepared' for entry in entries))


if __name__ == '__main__':
    unittest.main()
