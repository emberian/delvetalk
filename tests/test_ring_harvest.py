"""deploy/ring/harvest.py reads the front's access log (transport/http.py AccessLog) when the run has one."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('ring_harvest', ROOT / 'deploy' / 'ring' / 'harvest.py')
harvest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harvest)

LOG = '''2026-10-10T10:00:00Z GET /AGENTS.md/api 200 9000 -
2026-10-10T10:00:01Z POST /AGENTS.md/challenge 200 300 -
2026-10-10T10:00:02Z GET /AGENTS.md/world 200 4000 did:plc:aaaaaaaaaaaaaaaaaaaaaaaa
2026-10-10T10:00:03Z GET /AGENTS.md/world/nowhere 404 200 did:plc:aaaaaaaaaaaaaaaaaaaaaaaa
2026-10-10T10:00:04Z GET /AGENTS.md/world/nowhere 404 200 did:plc:bbbbbbbbbbbbbbbbbbbbbbbb
2026-10-10T10:00:05Z POST /AGENTS.md/world/garden/plant 429 100 did:plc:bbbbbbbbbbbbbbbbbbbbbbbb
2026-10-10T10:00:06Z POST /AGENTS.md/repl 500 120 did:plc:bbbbbbbbbbbbbbbbbbbbbbbb
2026-10-10T10:00:07Z GET /AGENTS.md/world 200 4000 did:plc:bbbbbbbbbbbbbbbbbbbbbbbb
not a log line
'''


class AccessRow(unittest.TestCase):
    def run_dir(self, **logs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = Path(tmp.name) / 'state'
        state.mkdir()
        for name, text in logs.items():
            (state / name.replace('_', '.')).write_text(text)
        return tmp.name

    def test_the_access_log_is_counted_by_class_and_the_500s_are_the_gate(self):
        r = harvest.harvest(self.run_dir(access_log=LOG, access_log_1=LOG.splitlines()[0] + '\n'))
        a = r['access']
        self.assertEqual((a['requests'], a['principals'], a['status500'], a['status5xx']), (9, 2, 1, 1))
        self.assertEqual(a['status4xx'], {'404': 2, '429': 1})
        self.assertEqual(dict(a['topPaths'])['/AGENTS.md/world'], 2)
        self.assertEqual(a['topBytes'][0], ['/AGENTS.md/api', 18000])
        text = harvest.markdown(r)
        self.assertIn('| front 5xx, of which 500 (the gate is zero) | 1, 1 |', text)
        self.assertIn('| front HTTP 404 | 2 |', text)

    def test_a_run_without_a_log_has_no_row(self):
        r = harvest.harvest(self.run_dir())
        self.assertIsNone(r['access'])
        self.assertNotIn('access.log', harvest.markdown(r))


if __name__ == '__main__':
    unittest.main()
