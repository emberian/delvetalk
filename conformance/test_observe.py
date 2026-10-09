#!/usr/bin/env python3
"""Actual staged observation, provenance and remote receiving; no real network."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import clerk
import delve
import manage
import receipts
import world


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


live = module('observe_live_fixture', 'conformance/test_live_path.py')
PLAIN = {'profile': 'delvetalk-local-v1', 'initial': {}, 'commands': {
    'echo': {'require': [], 'set': {}, 'result': ['literal', {'object': 'target', 'version': 0}], 'outbox': []},
    'origin': {'require': [], 'set': {}, 'result': ['input-origin'], 'outbox': []}}}
NONE = {'kind': 'none', 'object': '', 'command': '', 'immediatelyPrevious': False}
LEGACY_NONE = {'present': False, 'object': '', 'command': '', 'immediatelyPrevious': False}


def receiver(guard=False):
    accepted = ('context.inputOrigin.kind == "observe" && context.inputOrigin.immediatelyPrevious && '
                'context.inputOrigin.object == input.object') if guard else 'true'
    text = ('edition ObjectiveBend 1\nrecord Witness:\n  object: String\n  version: Nat\n'
        'record Origin:\n  kind: String\n  object: String\n  command: String\n  immediatelyPrevious: Bool\n'
        'record Context:\n  object: String\n  principal: String\n  inputOrigin: Origin\n'
        'record State:\n  count: Nat\nrecord Decision:\n  accepted: Bool\n  reason: String\n'
        '  state: State\n  result: Context\n'
        'def accept(state: State, input: Witness, context: Context) -> Decision:\n'
        '  let ok = ' + accepted + '\n'
        '  {accepted: ok, reason: if ok then "" else "observe the target first", '
        'state: {count: state.count + 1n}, result: context}\n')
    return {'profile': 'delvetalk-local-v1', 'initial': {'count': 0}, 'commands': {
        'accept': {'transition': {'profile': 'delvetalk-source-transition-v2',
            'package': {'modules': [{'name': 'Index', 'source': text}], 'entry': 'accept'}}}}}


class Observe(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.db = self.base / 'world.json'

    def call(self, request):
        return world.exchange(self.db, request, profile='compiled')

    def create(self, name, protocol=None, law=None):
        result = self.call({'op': 'create', 'object': name, 'principal': 'owner',
            'intent': 'create-' + name, 'protocol': protocol or PLAIN,
            'law': ['owner', 'visitor'] if law is None else law})
        self.assertEqual(result['kind'], 'committed', result)
        return result['data']['root']

    def inspect(self, name):
        return self.call({'op': 'inspect', 'object': name, 'principal': 'reader'})

    def transaction(self, reads, calls, intent='tx', principal='visitor'):
        return {'op': 'transaction', 'principal': principal, 'intent': intent, 'reads': reads, 'calls': calls}

    def test_public_observe_changes_no_target_and_does_not_execute_its_code(self):
        target = self.create('target', law=[])
        before = copy.deepcopy(target)
        request = self.transaction({'target': target}, [{'op': 'observe', 'object': 'target'}])
        result = self.call(request)
        self.assertEqual(result['kind'], 'committed', result)
        self.assertEqual(result['data']['results'], [{'object': 'target', 'version': 0}])
        self.assertEqual(result['data']['outbox'], [])
        self.assertEqual(self.inspect('target'), before)
        self.assertEqual(self.call(request), result)

    def test_observe_reads_staged_version_and_retained_retry_never_reverts_it(self):
        root = self.create('target')
        request = self.transaction({'target': root}, [
            {'object': 'target', 'command': 'echo', 'input': {}},
            {'op': 'observe', 'object': 'target'}])
        result = self.call(request)
        self.assertEqual(result['kind'], 'committed', result)
        self.assertEqual(result['data']['results'][1], {'object': 'target', 'version': 1})
        current = self.inspect('target')
        self.assertEqual(current['version'], 1)
        revised = self.call({'op': 'law', 'object': 'target', 'principal': 'owner',
            'intent': 'restrict', 'expected': current, 'law': []})['data']['root']
        self.assertEqual(self.call(request), result)
        self.assertEqual(self.inspect('target'), revised)

    def test_genuine_origin_distinguishes_direct_invoke_observe_and_nonadjacent(self):
        target = self.create('target')
        index = self.create('index', receiver())
        witness = {'object': 'target', 'version': 0}
        cases = [
            ([{'object': 'index', 'command': 'accept', 'input': witness}], NONE),
            ([{'object': 'target', 'command': 'echo', 'input': {}},
              {'object': 'index', 'command': 'accept', 'inputFrom': 0}],
             {'kind': 'invoke', 'object': 'target', 'command': 'echo', 'immediatelyPrevious': True}),
            ([{'op': 'observe', 'object': 'target'},
              {'object': 'index', 'command': 'accept', 'inputFrom': 0}],
             {'kind': 'observe', 'object': 'target', 'command': '', 'immediatelyPrevious': True}),
            ([{'op': 'observe', 'object': 'target'}, {'object': 'target', 'command': 'echo', 'input': {}},
              {'object': 'index', 'command': 'accept', 'inputFrom': 0}],
             {'kind': 'observe', 'object': 'target', 'command': '', 'immediatelyPrevious': False}),
        ]
        for number, (calls, origin) in enumerate(cases):
            result = self.call(self.transaction({'target': target, 'index': index}, calls, str(number)))
            self.assertEqual(result['kind'], 'committed', result)
            self.assertEqual(result['data']['results'][-1],
                {'object': 'index', 'principal': 'visitor', 'inputOrigin': origin})
            target, index = self.inspect('target'), self.inspect('index')

    def test_copied_witness_refuses_and_late_refusal_rolls_back_earlier_change(self):
        target = self.create('target')
        index = self.create('index', receiver(True))
        good = self.call(self.transaction({'target': target, 'index': index}, [
            {'op': 'observe', 'object': 'target'}, {'object': 'index', 'command': 'accept', 'inputFrom': 0}]))
        self.assertEqual(good['kind'], 'committed', good)
        index = self.inspect('index')
        forged = self.call(self.transaction({'target': target, 'index': index}, [
            {'object': 'target', 'command': 'echo', 'input': {}},
            {'object': 'index', 'command': 'accept', 'input': {'object': 'target', 'version': 0}}], 'copied'))
        self.assertEqual(forged['data'], 'source refused: observe the target first')
        self.assertEqual(self.inspect('target'), target)
        self.assertEqual(self.inspect('index'), index)

    def test_legacy_origin_row_and_invoke_only_meaning_are_unchanged(self):
        target = self.create('target')
        receiver_root = self.create('receiver')
        for number, first in enumerate(({'op': 'observe', 'object': 'target'},
                {'object': 'target', 'command': 'echo', 'input': {}})):
            receipt = self.call(self.transaction({'target': target, 'receiver': receiver_root}, [
                first, {'object': 'receiver', 'command': 'origin', 'inputFrom': 0}], str(number)))
            self.assertEqual(receipt['kind'], 'committed', receipt)
            expected = LEGACY_NONE if number == 0 else {
                'present': True, 'object': 'target', 'command': 'echo', 'immediatelyPrevious': True}
            self.assertEqual(receipt['data']['results'][1], expected)
            target, receiver_root = self.inspect('target'), self.inspect('receiver')

    def test_exact_initial_read_and_strict_shape_are_mandatory(self):
        target = self.create('target')
        cases = [({}, {'op': 'observe', 'object': 'target'}),
            ({'target': dict(target, version=9)}, {'op': 'observe', 'object': 'target'}),
            ({'missing': None}, {'op': 'observe', 'object': 'missing'})]
        cases.extend(({'target': target}, {'op': 'observe', 'object': 'target', key: value})
                     for key, value in [('input', {}), ('inputFrom', 0), ('command', 'echo'),
                                        ('principal', 'owner'), ('version', 0)])
        for number, (reads, call) in enumerate(cases):
            receipt = self.call(self.transaction(reads, [call], str(number)))
            self.assertEqual(receipt['kind'], 'refused', receipt)
            self.assertEqual(self.inspect('target'), target)

    def test_allocated_absence_is_not_an_existing_initial_read(self):
        factory = {'profile': 'delvetalk-local-v1', 'initial': {}, 'allocation': {'limit': 1},
            'commands': {'make': {'require': [], 'set': {}, 'result': ['literal', {}], 'outbox': [],
                'allocate': [{'name': ['literal', 'child'], 'protocol': ['literal', PLAIN],
                              'law': ['literal', ['visitor']]}]}}}
        root = self.create('factory', factory)
        result = self.call(self.transaction({'factory': root, 'factory/child': None}, [
            {'object': 'factory', 'command': 'make', 'input': {}},
            {'op': 'observe', 'object': 'factory/child'}]))
        self.assertEqual(result['data'], 'observe requires an existing exact read root')
        self.assertEqual(self.inspect('factory'), root)
        self.assertNotIn('factory/child', world.wire_loads(self.db.read_text())['objects'])

    def test_remote_clerk_enrollment_roots_receipt_and_restart(self):
        pds = live.PDS()
        custody = clerk.Clerk(self.base / 'clerk', pds)
        a = custody.bootstrap('a', PLAIN, [delve.DID], [delve.DID], runtime_profile='compiled')['data']['root']
        manage.Management(custody.state).add_object('b', delve.DID, 'create-b', 'protocol-json@1',
            clerk.canonical(PLAIN), [delve.DID])
        b = custody.snapshot('b')['root']
        credentials = self.base / 'credentials.json'
        credentials.write_text('{"handle":"' + delve.HANDLE + '","app_password":"mock-password"}')
        publisher = receipts.Publisher(delve.Delve(self.base / 'publication', credentials, self.base / 'posts', pds))
        snapshot = publisher.publish('root', clerk.world.wire_dumps(custody.snapshot('a')), 'root-a')
        payload = {'op': 'transaction', 'reads': {'a': {'expectedRootRef': {
            key: snapshot[key] for key in ('uri', 'cid')}}, 'b': {'expected': b}},
            'calls': [{'op': 'observe', 'object': 'a'}]}
        publication = publisher.publish('request', clerk.world.wire_dumps(payload), 'observe')
        received = custody.receive(publication['uri'], publication['cid'])
        self.assertEqual(received['reply']['kind'], 'committed', received)
        self.assertEqual(received['reply']['data']['results'], [{'object': 'a', 'version': 0}])
        self.assertEqual(set(received['reply']['data']['roots']), {'a', 'b'})
        self.assertEqual(custody.snapshot('a')['root'], a)
        self.assertEqual(custody.snapshot('b')['root'], b)
        encoded = receipts.encode('receipt', clerk.world.wire_dumps(received))
        self.assertEqual(encoded['objects'], ['a', 'b'])
        pds.records.clear()
        self.assertEqual(clerk.Clerk(custody.state, pds).receive(publication['uri'], publication['cid']), received)
        bad = {'op': 'transaction', 'reads': {'hidden': {'expected': a}},
               'calls': [{'op': 'observe', 'object': 'hidden'}]}
        publication = publisher.publish('request', clerk.world.wire_dumps(bad), 'hidden')
        with self.assertRaisesRegex(ValueError, 'not configured'):
            custody.receive(publication['uri'], publication['cid'])


if __name__ == '__main__':
    unittest.main()
