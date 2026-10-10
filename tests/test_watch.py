"""deploy/watch.py: the probe against OPERATIONS' thresholds, one line per crossed condition, six hours between two
lines for one condition and one hour for the two that page.

Evidence for OPERATIONS section b (layer: transport).
"""
import io
import json
import tempfile
import unittest
from pathlib import Path

from deploy import watch


def probe(at=100000, **more):
    p = {'at': at, 'front': {'requests5m': 3, '5xx5m': 0, '5xxHour': 0}, 'hour': {'turns': 20, 'refused': {}},
         'model': {'hour': {'calls': 4, 'dollars': 0.001}, 'day': {'calls': 9, 'dollars': 0.002}},
         'reservations': {'source': 'delve', 'used': 2, 'quota': 16}, 'interpretations': {'pending': 0, 'maxAttempts': 0},
         'journal': {'height': 900, 'bytes': 1 << 20, 'medianSuspendedBytes': 4000}, 'clock': {'world': 1, 'behindMinutes': 0},
         'observed': 50, 'backup': {'newest': 'delvetalk-x.tar.gz', 'ageSeconds': 600, 'verify': 'ok'}, 'freeFraction': {'/data': 0.6}}
    for k, v in more.items():
        p[k] = {**p[k], **v} if isinstance(v, dict) else v
    return p


class Watch(unittest.TestCase):
    def test_a_healthy_probe_crosses_nothing_and_each_threshold_names_its_condition(self):
        self.assertEqual(watch.conditions(probe(), []), [])
        crossed = probe(front={'5xx5m': 2}, hour={'turns': 20, 'refused': {'capacity': 1, 'quota': 6, 'staleRoot': 3}},
                        model={'hour': {'calls': 121, 'dollars': 0.03}}, clock={'behindMinutes': 4},
                        interpretations={'pending': 21, 'maxAttempts': 8}, backup={'verify': 'broken', 'ageSeconds': 8 * 3600},
                        journal={'bytes': 201 << 20, 'medianSuspendedBytes': 9000}, freeFraction={'/data': 0.1})
        keys = [k for k, _, _ in watch.conditions(crossed, [], ['delvetalk-bridge'])]
        self.assertEqual(keys, ['unhealthy', '5xx', 'capacity', 'quota', 'staleRoot', 'model', 'journal', 'suspension', 'clock',
                                'interpretations', 'backup', 'disk:/data'])

    def test_the_hour_long_thresholds_read_the_history(self):
        full = {'reservations': {'used': 16}}
        history = [probe(at=100000 - 7200 + 300 * i, **full) for i in range(24)]
        self.assertIn('reservations', [k for k, _, _ in watch.conditions(probe(**full), history)])
        self.assertNotIn('reservations', [k for k, _, _ in watch.conditions(probe(**full), history[12:])])  # one hour is not two
        stalled = [probe(at=100000 - 3600, observed=40)]
        self.assertIn('stalled', [k for k, _, _ in watch.conditions(probe(), stalled)])

    def test_one_line_per_condition_per_six_hours_and_the_two_that_page_hourly(self):
        with tempfile.TemporaryDirectory() as d:
            sent, state = [], Path(d)
            run = lambda p: ((state / 'p.json').write_text(json.dumps(p)),
                             watch.main(['--state', d, '--probe', str(state / 'p.json'), '--unhealthy', 'delvetalk-hostd'], io.StringIO(), sent.append))
            run(probe(front={'5xx5m': 1}))
            self.assertEqual(sent, ['unhealthy: delvetalk-hostd (playbook A)', 'the front answered 1 5xx in five minutes (playbook A)'])
            run(probe(at=100000 + 3700, front={'5xx5m': 1}))
            self.assertEqual(sent[2:], ['unhealthy: delvetalk-hostd (playbook A)'])  # the host pages hourly; the 5xx waits six hours
            run(probe(at=100000 + 6 * 3600 + 1, front={'5xx5m': 1}))
            self.assertEqual(len(sent), 5)
            self.assertEqual(len((state / 'watch.jsonl').read_text().splitlines()), 3)


if __name__ == '__main__':
    unittest.main()
