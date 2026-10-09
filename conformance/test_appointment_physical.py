"""Physical observation custody and source-owned conversion, rollback and retry."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_appointments as appointments
from test_appointments import ROOT, world
import clock_physical_driver as driver


class PhysicalClock(unittest.TestCase):
    def setUp(self):
        self.fx = appointments.Appointments()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.fx.setup_world(physical={'epochMillis': 1000, 'quantumMillis': 1000})

    def sample(self, value, *, attempt='sample', principal='driver'):
        with patch.object(driver.time, 'time_ns', return_value=value * 1_000_000):
            return driver.sample(self.fx.db, Path(self.fx.temp.name) / (attempt + '.json'),
                clock='clock', principal=principal, intent=attempt)

    def test_source_converts_explicit_sample_and_same_observation_cannot_double_send(self):
        self.fx.book()
        receipt = self.sample(6000)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(self.fx.state()['now'], 5)
        self.assertEqual(self.fx.state()['observedMillis'], 6000)
        self.assertEqual(len(receipt['data']['messages']), 1)
        with patch.object(driver.time, 'time_ns', side_effect=AssertionError('retry must not resample')):
            recovered = driver.sample(self.fx.db, Path(self.fx.temp.name) / 'sample.json',
                clock='clock', principal='driver', intent='sample')
        self.assertEqual(recovered, receipt)
        repeated = self.sample(6000, attempt='same-observation-new-intent')
        self.assertEqual(repeated['kind'], 'committed', repeated)
        self.assertEqual(repeated['data'].get('messages', []), [])
        self.fx.call(self.fx.delivery(receipt['data']['messages'][0], 'garden-task'), 'committed')
        self.assertEqual(self.fx.state('garden-task')['runs'], 1)

    def test_rollback_is_source_refused_and_missed_deadline_expires_without_catchup(self):
        self.fx.book(deadline=5)
        receipt = self.sample(7000)
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(receipt['data'].get('messages', []), [])
        self.assertEqual(self.fx.state()['last']['status'], 'expired')
        before = self.fx.root()
        rollback = self.sample(6999, attempt='rollback')
        self.assertEqual(rollback['kind'], 'refused', rollback)
        self.assertIn('rolls backwards', rollback['data'])
        self.assertEqual(self.fx.root(), before)

    def test_equal_logical_time_drains_bounded_backlog_without_resampling(self):
        for i in range(6):
            self.fx.book(id=str(i), due=5, deadline=10)
        self.assertEqual(len(self.sample(6000)['data']['messages']), 4)
        self.assertEqual(self.fx.state()['size'], 2)
        self.assertEqual(len(self.fx.tick(5)['data']['messages']), 2)
        self.assertEqual(self.fx.state()['observedMillis'], 6000)

    def test_denied_driver_and_refused_recipient_preserve_observation_and_work(self):
        self.fx.book(recipientProgram='0' * 64)
        before = self.fx.root()
        denied = self.sample(6000, principal='moss', attempt='denied')
        self.assertEqual(denied['data'], 'unauthorized')
        refused = self.sample(6000, attempt='bad-recipient')
        self.assertEqual(refused['kind'], 'refused', refused)
        self.assertIn('program changed', refused['data'])
        self.assertEqual(self.fx.root(), before)
        self.assertEqual(self.fx.state()['observedMillis'], 1000)
        self.fx.call(self.fx.cancel(), 'committed')
        self.assertEqual(self.sample(6000, attempt='cancelled')['kind'], 'committed')

    def test_stale_retained_observation_never_refreshes_and_revocation_faces_current_law(self):
        # Stop after durable preparation but before admission, as a lost connection would.
        original = driver.retained_invocation.world.exchange
        def drop(database, request, **kwargs):
            if request['op'] == 'invoke':
                raise ConnectionError('before admission')
            return original(database, request, **kwargs)
        with patch.object(driver.retained_invocation.world, 'exchange', side_effect=drop):
            with self.assertRaises(ConnectionError):
                self.sample(6000, attempt='stale')
        path = Path(self.fx.temp.name) / 'stale.json'
        retained = path.read_bytes()
        self.fx.book()
        refused = self.sample(999999, attempt='stale')
        self.assertEqual(refused['data'], 'stale read root')
        self.assertEqual(path.read_bytes(), retained)
        root = self.fx.root()
        changed = {**root['law'], 'invoke': {**root['law']['invoke'], 'sample': []}}
        self.fx.call({'op': 'law', 'object': 'clock', 'principal': 'steward', 'intent': 'revoke-driver',
                      'expected': root, 'law': changed}, 'committed')
        denied = self.sample(6000, attempt='revoked')
        self.assertEqual(denied['data'], 'unauthorized')

    def test_process_death_after_commit_recovers_observation_and_due_event(self):
        self.fx.book()
        attempt = Path(self.fx.temp.name) / 'crashed-sample.json'
        script = """import os,signal,sys
sys.path.insert(0,sys.argv[1]);import clock_physical_driver as d
d.time.time_ns=lambda:6000000000
replace=d.world.os.replace
def crash(a,b):
 replace(a,b)
 if os.path.realpath(b)==os.path.realpath(sys.argv[2]):os.kill(os.getpid(),signal.SIGKILL)
d.world.os.replace=crash
d.sample(sys.argv[2],sys.argv[3],clock='clock',principal='driver',intent='crashed')
"""
        process = subprocess.run([sys.executable, '-c', script, str(ROOT / 'scripts'),
                                  str(self.fx.db), str(attempt)], capture_output=True)
        self.assertEqual(process.returncode, -9, process.stderr)
        with patch.object(driver.time, 'time_ns', side_effect=AssertionError('restart must not resample')):
            receipt = driver.sample(self.fx.db, attempt, clock='clock', principal='driver', intent='crashed')
        self.assertEqual(receipt['kind'], 'committed', receipt)
        self.assertEqual(len(receipt['data']['messages']), 1)
        request = world.wire_loads(attempt.read_text())['request']
        self.assertEqual(request['input'], {'unixMillis': 6000})
        self.assertEqual(self.fx.call(request), receipt)
        self.fx.call(self.fx.delivery(receipt['data']['messages'][0], 'garden-task'), 'committed')
        self.assertEqual(self.fx.state('garden-task')['runs'], 1)


if __name__ == '__main__':
    unittest.main()
