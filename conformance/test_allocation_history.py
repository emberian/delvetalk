"""Allocation/source custody composition through actual Lean admission and replay."""
from native_support import load_script
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import history
import translate
import world


def load_module(name, path):
    return load_script(ROOT / path, name)


fixture = load_module('allocation_history_fixture', 'conformance/test_allocation.py')


class AllocationHistory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.database = self.directory / 'world.json'
        self.factory = fixture.factory_protocol()
        # The caller supplies data; current factory authority chooses whether to
        # instantiate it. No separate child-source authorship is invented.
        self.factory['commands']['make']['allocate'][0]['protocol'] = ['input', 'program']
        self.creation = {'op': 'create', 'object': 'factory', 'principal': 'bootstrap',
                         'intent': 'factory-create', 'protocol': self.factory, 'law': fixture.factory_law()}
        self.root = self.call(self.creation)['data']['root']
        self.source = self.directory / 'factory-source.json'
        self.source.write_bytes(history.canonical(translate.translate('protocol-json@1', history.canonical(self.factory))))

    def call(self, request, database=None):
        return world.exchange(database or self.database, request, profile='transactions')

    def allocate(self, program, *, transaction=False, absent=None, intent='allocate'):
        if transaction:
            return {'op': 'transaction', 'principal': 'alice', 'intent': intent,
                    'reads': {'factory': self.root, 'factory/child': absent, 'factory/unused': None},
                    'calls': [{'object': 'factory', 'command': 'make',
                               'input': {'name': 'child', 'program': program}}]}
        return {'op': 'invoke', 'principal': 'alice', 'intent': intent, 'object': 'factory',
                'expected': self.root, 'command': 'make', 'absent': ['factory/child'],
                'input': {'name': 'child', 'program': program}}

    def export(self, name, attachments=None):
        bundle = self.directory / name
        links = {history.digest(self.creation): [self.source], **(attachments or {})}
        report = history.export_history(self.database, bundle, attachments=links)
        return bundle, report

    def test_dynamic_child_reconstructs_and_continues_from_factory_plus_exact_input(self):
        request = self.allocate(fixture.child_protocol(), transaction=True)
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertIsNone(receipt['data']['roots']['factory/unused'])
        restored = self.directory / 'restored.json'
        bundle, report = self.export('generated')
        history.verify_history(bundle, expected_genesis=report['genesis'], expected_head=report['head'], output=restored)
        child = world.wire_loads(restored.read_text())['objects']['factory/child']
        self.assertNotIn('factory/unused', world.wire_loads(restored.read_text())['objects'])
        changed = self.call({'op': 'invoke', 'object': 'factory/child', 'principal': 'alice',
            'intent': 'use-restored-child', 'expected': child, 'command': 'write', 'input': {'text': 'continued'}}, restored)
        self.assertEqual(changed['kind'], 'committed')
        self.assertEqual(changed['data']['root']['state']['text'], 'continued')
        self.assertEqual(self.call(request, restored), receipt)

    def test_missing_null_read_or_existing_child_refuses_without_ghost_allocation(self):
        request = self.allocate(fixture.child_protocol(), transaction=True)
        del request['reads']['factory/child']
        self.assertEqual(self.call(request)['data'], 'allocation target missing absence root')
        request = self.allocate(fixture.child_protocol(), transaction=True, intent='allocate-now')
        self.assertEqual(self.call(request)['kind'], 'committed')
        current = world.wire_loads(self.database.read_text())['objects']
        again = self.allocate(fixture.child_protocol(), transaction=True, intent='stale-absence')
        again['reads']['factory'] = current['factory']
        self.assertEqual(self.call(again)['data'], 'stale absence root')
        self.assertEqual(world.wire_loads(self.database.read_text())['objects'], current)

    def test_allocated_child_omitted_from_snapshot_cannot_replay(self):
        self.call(self.allocate(fixture.child_protocol()))
        snapshot = world.wire_loads(self.database.read_text())
        del snapshot['objects']['factory/child']
        self.database.write_text(world.wire_dumps(snapshot))
        with self.assertRaisesRegex(ValueError, 'cannot be reconstructed'):
            self.export('omitted-child')

    def test_bootstrap_export_does_not_invent_authored_source_for_generated_child(self):
        bootstrap = load_module('allocation_history_bootstrap', 'scripts/bootstrap.py')
        self.assertEqual(self.call(self.allocate(fixture.child_protocol(), transaction=True))['kind'], 'committed')
        artifact = history.loads(self.source.read_bytes())
        store = self.directory / 'artifacts/lowerings'
        store.mkdir(parents=True)
        (store / (history.digest(artifact) + '.json')).write_bytes(history.canonical(artifact))
        pins = self.directory / 'artifacts/pins'
        (pins / 'blobs').mkdir(parents=True)
        for name, sha in history.declared_files(artifact).items():
            self.assertEqual(history.store_file(pins, ROOT / name), sha)
        # Minimal export-only index; the independent full bootstrap suite tests
        # restoration of all named cafe/sign objects and their presentation.
        (self.directory / 'manifest.json').write_bytes(history.canonical({
            'format': 'delvetalk-inhabited-bootstrap-v1', 'runtime': history.runtime('transactions')}))
        bundle = self.directory / 'bootstrap-export'
        report = bootstrap.export_bootstrap(self.directory, bundle)
        history.verify_history(bundle, expected_genesis=report['genesis'], expected_head=report['head'])

    def test_room_allocation_requires_artifact_for_single_and_transaction(self):
        room = load_module('allocation_history_room', 'scene/room.py')
        artifact = room.compile_artifact('---\nid: allocated_room\n---\n=== start\nA room born here.\n* [Leave]\n  -> END\n')
        room_source = self.directory / 'room.json'
        room_source.write_bytes(room.canonical(artifact))
        initial = self.database.read_bytes()
        for transaction in (False, True):
            with self.subTest(transaction=transaction):
                self.database.write_bytes(initial)
                request = self.allocate(artifact['protocol'], transaction=transaction)
                self.assertEqual(self.call(request)['kind'], 'committed')
                with self.assertRaisesRegex(ValueError, 'missing or mismatched room artifact'):
                    self.export('missing-room-' + str(transaction))
                bundle, report = self.export('complete-room-' + str(transaction),
                    {history.digest(request): [room_source]})
                restored = self.directory / ('room-restored-' + str(transaction) + '.json')
                history.verify_history(bundle, expected_genesis=report['genesis'], expected_head=report['head'], output=restored)
                root = world.wire_loads(restored.read_text())['objects']['factory/child']
                view = room.room_view(root, artifact, 'factory/child')
                self.assertEqual(view['mode'], 'room')
                started = self.call(room.start_request(view, 'alice', 'enter-child'), restored)
                self.assertEqual(started['kind'], 'committed')

    def test_transient_allocated_room_preserves_original_content_obligation(self):
        room = load_module('allocation_history_transient_room', 'scene/room.py')
        artifact = room.compile_artifact('---\nid: transient_room\n---\n=== start\nA fleeting room.\n* [Leave]\n  -> END\n')
        room_source = self.directory / 'transient-room.json'
        room_source.write_bytes(room.canonical(artifact))
        replacement = fixture.child_protocol()
        lowering = self.directory / 'replacement.json'
        lowering.write_bytes(history.canonical(translate.translate('protocol-json@1', history.canonical(replacement))))
        request = self.allocate(artifact['protocol'], transaction=True)
        request['calls'].append({'op': 'reprogram', 'object': 'factory/child',
                                 'protocol': replacement, 'state': {'text': 'replaced'}})
        receipt = self.call(request)
        self.assertEqual(receipt['kind'], 'committed')
        self.assertEqual(receipt['data']['allocated']['factory/child']['protocol'], artifact['protocol'])
        self.assertEqual(receipt['data']['roots']['factory/child']['protocol'], replacement)
        with self.assertRaisesRegex(ValueError, 'missing or mismatched room artifact'):
            self.export('transient-missing', {history.digest(request): [lowering]})
        bundle, report = self.export('transient-complete', {history.digest(request): [lowering, room_source]})
        restored = self.directory / 'transient-restored.json'
        history.verify_history(bundle, expected_genesis=report['genesis'], expected_head=report['head'], output=restored)
        root = world.wire_loads(restored.read_text())['objects']['factory/child']
        self.assertEqual(root['state'], {'text': 'replaced'})


if __name__ == '__main__':
    unittest.main()
