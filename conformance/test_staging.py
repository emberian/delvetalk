#!/usr/bin/env python3
"""Exact staging boundaries for persistent object updates and batched allocation."""
import copy
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHILD = {'profile': 'delvetalk-local-v1', 'initial': {'x': 0}, 'commands': {}}


def object_root(protocol=CHILD):
    return {'protocol': copy.deepcopy(protocol), 'state': copy.deepcopy(protocol['initial']),
            'law': ['a'], 'version': 0}


def factory(names, quota):
    return object_root({'profile': 'delvetalk-local-v1', 'initial': {'old': 0},
        'allocation': {'limit': quota}, 'commands': {'make': {'require': [],
        'set': {'old': ['literal', 1], 'new': ['literal', 2]}, 'result': ['state', 'old'],
        'outbox': [['literal', 'committed']], 'allocate': [
            {'name': ['literal', name], 'protocol': ['literal', CHILD], 'law': ['literal', ['a']]}
            for name in names]}}})


def fixture(names, quota, existing=()):
    parent = factory(names, quota)
    objects = {f'unrelated-{i:03d}': object_root() for i in range(128)}
    objects.update({key: object_root() for key in existing})
    objects['factory'] = parent
    request = {'op': 'invoke', 'object': 'factory', 'principal': 'a', 'intent': 'stage',
               'expected': parent, 'command': 'make', 'input': {},
               'absent': ['factory/' + name for name in dict.fromkeys(names)]}
    return {'world': {'objects': objects, 'receipts': []}, 'request': request}


def execute(frame, binary=None):
    binary = binary or ROOT / '.lake/build/bin/delvetalk-transactions'
    result = subprocess.run([str(binary)], input=json.dumps(frame) + '\n', text=True,
                            capture_output=True, timeout=30, check=True)
    return json.loads(result.stdout)


class Staging(unittest.TestCase):
    def test_batch_counts_only_direct_children_preserves_every_unrelated_root(self):
        frame = fixture(['one', 'two'], 3, ['factory/existing', 'factory/existing/grandchild', 'factory/one/deeper'])
        result = execute(frame)
        self.assertEqual(result['reply']['kind'], 'committed', result['reply'])
        roots = result['world']['objects']
        for key, root in frame['world']['objects'].items():
            if key != 'factory':
                self.assertEqual(roots[key], root)
        self.assertEqual(roots['factory']['state'], {'old': 1, 'new': 2})
        self.assertEqual(result['reply']['data']['result'], 0)  # all expressions see pre-state
        self.assertEqual(set(result['reply']['data']['allocated']), {'factory/one', 'factory/two'})
        self.assertEqual(roots['factory']['version'], 1)
        retry = execute({'world': result['world'], 'request': frame['request']})
        self.assertEqual(retry, result)

    def test_collision_before_quota_and_late_failure_rolls_back_batch(self):
        for names, expected in [(['one', 'one'], 'object exists'),
                                (['one', 'two'], 'factory child quota exhausted'),
                                (['one', 'bad/name'], 'invalid child name')]:
            with self.subTest(names=names):
                frame = fixture(names, 1)
                result = execute(frame)
                self.assertEqual(result['reply']['kind'], 'refused')
                self.assertEqual(result['reply']['data'], expected)
                self.assertEqual(result['world']['objects'], frame['world']['objects'])
                self.assertEqual(len(result['world']['receipts']), 1)
                retry = execute({'world': result['world'], 'request': frame['request']})
                self.assertEqual(retry, result)

    def test_second_factory_call_counts_children_created_by_first(self):
        frame = fixture(['one'], 1)
        changed = copy.deepcopy(frame['world']['objects']['factory']['protocol'])
        changed['commands']['second'] = copy.deepcopy(changed['commands']['make'])
        changed['commands']['second']['allocate'][0]['name'] = ['literal', 'two']
        frame['world']['objects']['factory'] = object_root(changed)
        frame['request'] = {'op': 'transaction', 'principal': 'a', 'intent': 'two-batches',
            'reads': {'factory': frame['world']['objects']['factory'], 'factory/one': None, 'factory/two': None},
            'calls': [{'object': 'factory', 'command': command, 'input': {}}
                      for command in ['make', 'second']]}
        result = execute(frame)
        self.assertEqual(result['reply']['data'], 'factory child quota exhausted')
        self.assertEqual(result['world']['objects'], frame['world']['objects'])
        self.assertEqual(len(result['world']['receipts']), 1)


if __name__ == '__main__':
    unittest.main()
