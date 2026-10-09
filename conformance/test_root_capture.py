"""Atomic native root/reference observations avoid full-preimage uploads."""
from contextlib import nullcontext
from decimal import Decimal
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('capture_world', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


class RootCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()

    def create(self, database, large=False):
        return world.exchange(database, {'op': 'create', 'object': 'counter', 'principal': 'p',
            'intent': 'create', 'law': ['p'], 'protocol': {
                'profile': 'delvetalk-local-v1',
                'initial': {'n': Decimal('1.2300'), 'padding': 'x' * (600000 if large else 1)},
                'commands': {'write': {'require': [], 'set': {'n': ['input', 'n']},
                    'result': ['input', 'n'], 'outbox': []}}}}, profile='compiled')['data']['root']

    def write(self, reference, intent='write', principal='p'):
        return {'op': 'invoke', 'object': 'counter', 'principal': principal, 'intent': intent,
            'expected': reference, 'command': 'write', 'input': {'n': 2}}

    def test_large_roots_paired_without_upload_and_readonly_for_both_backends(self):
        for backend in ('file', 'resident'):
            with self.subTest(backend=backend):
                database = self.directory / (backend + '.json')
                if backend == 'resident':
                    world.configure_resident(database)
                with world.resident_session(database) if backend == 'resident' else nullcontext():
                    root = self.create(database, large=True)
                    self.assertGreater(len(world.wire_dumps(root).encode()), 1024 * 1024)
                    before = world.snapshot_bytes(database)
                    requests = []
                    original = world.query
                    def record(database, request, **kwargs):
                        requests.append(request)
                        return original(database, request, **kwargs)
                    with patch.object(world, 'query', record), patch.object(world.tempfile, 'NamedTemporaryFile',
                            side_effect=AssertionError('capture client wrote a file')):
                        captured = world.capture_roots(database, ['counter', 'missing'])
                    self.assertEqual(captured['sequence'], 1)
                    self.assertIsNone(captured['roots']['missing'])
                    self.assertEqual(captured['roots']['counter']['root'], root)
                    self.assertEqual(captured['roots']['counter']['root']['state']['n'].as_tuple(), Decimal('1.2300').as_tuple())
                    self.assertLess(len(world.wire_dumps(requests[0]).encode()), 256)
                    self.assertEqual(world.snapshot_bytes(database), before)
                    reference = captured['roots']['counter']['reference']
                    denied = world.exchange(database, self.write(reference, 'denied', 'outsider'), profile='compiled')
                    self.assertEqual(denied['kind'], 'refused')
                    same = world.capture_roots(database, ['counter'], expected={'counter': reference})
                    self.assertEqual(same['sequence'], 2)  # Includes refused admissions.
                    self.assertEqual(same['roots']['counter']['reference'], reference)
                    reply = world.exchange(database, self.write(reference), profile='compiled')
                    self.assertEqual(reply['kind'], 'committed')
                    with self.assertRaisesRegex((ValueError, RuntimeError), 'stale capture root'):
                        world.capture_roots(database, ['counter'], expected={'counter': reference})

    def test_restart_capture_and_exact_retry_use_native_retained_roots(self):
        database = self.directory / 'restart.json'
        world.configure_resident(database)
        with world.resident_session(database):
            self.create(database, large=True)
            captured = world.capture_roots(database, ['counter'])
            request = self.write(captured['roots']['counter']['reference'])
            reply = world.exchange(database, request, profile='compiled')
            world._resident_rpc(database, world.resident_config(database), 'checkpoint')
        with world.resident_session(database):
            current = world.capture_roots(database, ['counter'])
            self.assertEqual(current['sequence'], 2)
            self.assertNotEqual(current['head'], captured['head'])
            self.assertEqual(world.exchange(database, request, profile='compiled'), reply)
            self.assertEqual(world.retained_reply(database, request), reply)

    def test_native_guard_types_absence_bounds_and_mutation_refusal(self):
        database = self.directory / 'guards.json'
        root = self.create(database)
        captured = world.capture_roots(database, ['counter'])
        reference = captured['roots']['counter']['reference']
        for expected in ({'counter': None}, {'counter': {**reference, 'object': 'other'}},
                         {'other': reference}):
            with self.assertRaises((ValueError, RuntimeError)):
                world.capture_roots(database, ['counter'], expected=expected)
        altered = {**root, 'state': {**root['state'], 'n': Decimal('1.23')}}
        with self.assertRaisesRegex((ValueError, RuntimeError), 'stale capture root'):
            world.capture_roots(database, ['counter'], expected={'counter': altered})
        self.assertIsNone(world.capture_roots(database, ['missing'], expected={'missing': None})['roots']['missing'])
        for objects in ([], ['counter', 'counter'], ['x' + str(i) for i in range(18)]):
            with self.assertRaises((ValueError, RuntimeError)):
                world.capture_roots(database, objects)


if __name__ == '__main__':
    unittest.main()
