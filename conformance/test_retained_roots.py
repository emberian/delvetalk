"""Compact guards exercise the actual file and persistent native receivers."""
import copy
from decimal import Decimal
import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('retained_world', ROOT / 'scripts/world.py')
world = importlib.util.module_from_spec(spec)
spec.loader.exec_module(world)


class RetainedRootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()

    def create(self, database, identity='counter'):
        return world.exchange(database, {'op': 'create', 'object': identity, 'principal': 'p',
            'intent': 'create-' + identity, 'law': ['p'], 'protocol': {
                'profile': 'delvetalk-local-v1', 'initial': {'n': Decimal('1.2300')},
                'commands': {'write': {'require': [], 'set': {'n': ['input', 'n']},
                    'result': ['input', 'n'], 'outbox': []}}}}, profile='compiled')['data']['root']

    def reference(self, database, root, identity='counter'):
        return world.query(database, {'op': 'retained-root', 'object': identity, 'root': root})

    def write(self, expected, intent='write'):
        return {'op': 'invoke', 'object': 'counter', 'principal': 'p', 'intent': intent,
                'expected': expected, 'command': 'write', 'input': {'n': 2}}

    def test_file_compact_identity_exactness_staleness_and_absence(self):
        database = self.directory / 'file.json'
        root = self.create(database)
        reference = self.reference(database, root)
        self.assertLess(len(world.wire_dumps(reference)), len(world.wire_dumps(root)))
        request = self.write(reference)
        reply = world.exchange(database, request, profile='compiled')
        self.assertEqual(reply['kind'], 'committed')
        self.assertEqual(world.snapshot(database)['receipts'][-1]['request'], request)
        self.assertEqual(world.exchange(database, request, profile='compiled'), reply)
        collision = world.exchange(database, self.write(root), profile='compiled')
        self.assertEqual(collision['kind'], 'refused')
        self.assertEqual(world.exchange(database, self.write(reference, 'stale'), profile='compiled')['kind'], 'refused')
        latest = self.reference(database, reply['data']['root'])
        transaction = {'op': 'transaction', 'principal': 'p', 'intent': 'absence',
            'reads': {'counter': latest, 'missing': None}, 'calls': [{'op': 'observe', 'object': 'counter'}]}
        self.assertEqual(world.exchange(database, transaction, profile='compiled')['kind'], 'committed')
        self.create(database, 'missing')
        self.assertEqual(world.exchange(database, {**transaction, 'intent': 'absence-stale'}, profile='compiled')['kind'], 'refused')

    def test_resident_checkpoint_restart_retry_before_current_law(self):
        database = self.directory / 'resident.json'
        world.configure_resident(database)
        with world.resident_session(database):
            root = self.create(database)
            reference = self.reference(database, root)
            request = self.write(reference)
            reply = world.exchange(database, request, profile='compiled')
            latest = self.reference(database, reply['data']['root'])
            law = world.exchange(database, {'op': 'law', 'object': 'counter', 'principal': 'p',
                'intent': 'lock', 'expected': latest, 'law': ['q']}, profile='compiled')
            self.assertEqual(law['kind'], 'committed')
            current = self.reference(database, law['data']['root'])
            config = world.resident_config(database)
            world._resident_rpc(database, config, 'checkpoint')
        with world.resident_session(database):
            self.assertEqual(self.reference(database, root), reference)
            self.assertEqual(world.exchange(database, request, profile='compiled'), reply)
            self.assertEqual(world.retained_reply(database, request), reply)
            self.assertEqual(world.exchange(database, self.write(current, 'denied'), profile='compiled')['kind'], 'refused')
            self.assertEqual(world.exchange(database, self.write(reference, 'old'), profile='compiled')['kind'], 'refused')

    def test_unknown_wrong_object_malformed_and_exact_decimal(self):
        database = self.directory / 'adversarial.json'
        root = self.create(database)
        reference = self.reference(database, root)
        for bad in ({**reference, 'key': '0' * 64}, {**reference, 'object': 'other'},
                    {**reference, 'extra': True}):
            reply = world.exchange(database, self.write(bad, world.wire_dumps(bad)), profile='compiled')
            self.assertEqual(reply['kind'], 'refused')
        changed = copy.deepcopy(root)
        changed['state']['n'] = Decimal('1.23')
        with self.assertRaises((ValueError, RuntimeError)):
            self.reference(database, changed)

    def test_compact_uncertain_commit_recovery_and_full_native_audit(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import resident_store
        from conformance.test_resident_store import create
        database = self.directory / 'audit.sqlite'
        with resident_store.Resident(database, profile='compiled') as resident:
            root = resident.exchange(create())['data']['root']
            reference = resident.query({'op': 'retained-root', 'object': 'room', 'root': root})
            request = {'op': 'invoke', 'object': 'room', 'principal': 'keeper', 'intent': 'write',
                'expected': reference, 'command': 'write', 'input': {'value': 7}}
            def fail(stage):
                if stage == 'after_commit':
                    raise OSError('lost durable reply')
            with patch.object(resident, '_boundary', fail):
                with self.assertRaises(OSError):
                    resident.exchange(request)
            reply = resident.recover()
            self.assertEqual(reply['kind'], 'committed')
            resident.checkpoint()
            self.assertEqual(resident.audit()['sequence'], 2)
            self.assertEqual(resident.retained_reply(request), reply)
        with resident_store.Resident(database, profile='compiled') as resident:
            self.assertEqual(resident.exchange(request), reply)
            self.assertEqual(resident.query({'op': 'retained-root', 'object': 'room', 'root': root}), reference)

    def test_file_queries_create_no_custody_files_and_reject_mutations(self):
        database = self.directory / 'readonly.json'
        root = self.create(database)
        before = database.read_bytes()
        # Query must work without the writer's lock file or any writable path.
        Path(str(database) + '.lock').unlink()
        names = set(self.directory.iterdir())
        with patch.object(world.tempfile, 'NamedTemporaryFile', side_effect=AssertionError('query created custody')):
            reference = self.reference(database, root)
            inspected = world.query(database, {'op': 'inspect', 'object': 'counter', 'principal': 'reader'})
            self.assertEqual(inspected, root)
            with self.assertRaisesRegex(ValueError, 'read-only file query refuses mutations'):
                world.query(database, self.write(reference))
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(set(self.directory.iterdir()), names)

    def test_actual_captured_source_preparation_is_compact_without_refresh(self):
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / 'scripts'))
        import source_offers
        from conformance.test_preparation import SOURCE
        from syntaxes import obend_object
        source = SOURCE.replace('textConcat("Offer ", gesture)', '"Offer gesture"')
        protocol = obend_object.lower_data_modules([
            {'name': 'Preparation', 'source': (ROOT / 'world/lib/prelude/Preparation.obend').read_text()},
            {'name': 'Gallery', 'source': source}])
        database = self.directory / 'preparation.json'
        world.configure_resident(database)
        with world.resident_session(database):
            roots = {}
            peer = {'profile': 'delvetalk-local-v1', 'initial': {'gesture': 'first', 'padding': 'x' * 150000},
                'commands': {'touch': {'require': [], 'set': {'gesture': ['input', 'gesture']},
                    'result': ['input', 'gesture'], 'outbox': []}}}
            for identity, protocol in [('gallery', protocol), ('peer', peer)]:
                reply = world.exchange(database, {'op': 'create', 'object': identity, 'principal': 'actor',
                    'intent': 'create-' + identity, 'law': ['actor'], 'protocol': protocol}, profile='compiled')
                self.assertEqual(reply['kind'], 'committed', reply)
                roots[identity] = reply['data']['root']
            invitation = {'format': source_offers.FORMAT, 'object': 'gallery',
                'root': self.reference(database, roots['gallery'], 'gallery'), 'entry': 'prepareGesture',
                'observations': [{'object': 'peer', 'root': self.reference(database, roots['peer'], 'peer')}],
                'title': 'Gallery', 'label': 'Gesture', 'fields': []}
            outcome = source_offers.prepare(invitation, 'actor', 'gesture', {'gesture': 'wave'}, database=database)
            self.assertLess(len(world.wire_dumps(outcome['request']).encode()), 1024)
            self.assertEqual(outcome['request']['reads']['peer'], invitation['observations'][0]['root'])
            moved = world.exchange(database, {'op': 'invoke', 'object': 'peer', 'principal': 'actor',
                'intent': 'move', 'expected': invitation['observations'][0]['root'], 'command': 'touch',
                'input': {'gesture': 'second'}}, profile='compiled')
            self.assertEqual(moved['kind'], 'committed')
            captured = source_offers.prepare(invitation, 'actor', 'after-move', {'gesture': 'wave'}, database=database)
            self.assertEqual(captured['request']['reads'], outcome['request']['reads'])
            refused = world.exchange(database, outcome['request'], profile='compiled')
            self.assertEqual(refused['kind'], 'refused')


if __name__ == '__main__':
    unittest.main()
