#!/usr/bin/env python3
"""Explicit v1/v2 scene migration through the existing Lean host, without builds."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


lower = module('migration_lower', 'scene/lower.py')
room = module('migration_room', 'scene/room.py')
adapter = module('migration_adapter', 'syntaxes/spween.py')

OLD = '''---
id: ordering
title: Ordering
---
=== intro
~ word = "z"
* [Less than itself] { word < "z" }
  -> END
* [Equal to itself] { word == "z" }
  -> END
'''
NEW = OLD + '''
=== unused
~ unused = "a"
* [Finish]
  -> END
'''


def compile_source(source, profile=lower.PROFILE):
    return lower.lower_document(lower.bridge({'op': 'parse', 'source': source}), profile=profile)


def host(world, request):
    process = subprocess.run([str(ROOT / '.lake/build/bin/delvetalk-world')],
        input=json.dumps({'world': world, 'request': request}) + '\n',
        capture_output=True, text=True, check=True, timeout=10)
    result = json.loads(process.stdout)
    if 'error' in result: raise AssertionError(result)
    return result['world'], result['reply']


class SpweenMigrationTests(unittest.TestCase):
    def started(self, source=OLD):
        protocol = compile_source(source)['protocol']
        world, receipt = host({'objects': {}, 'receipts': []}, {
            'op': 'create', 'object': 'room', 'principal': 'owner', 'intent': 'create',
            'protocol': protocol, 'law': ['owner']})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        world, receipt = self.invoke(world, 'start', 'start')
        self.assertEqual(receipt['kind'], 'committed', receipt)
        return world

    def invoke(self, world, command, intent):
        return host(world, {'op': 'invoke', 'object': 'room', 'principal': 'owner',
            'intent': intent, 'expected': world['objects']['room'], 'command': command, 'input': {}})

    def migrate(self, world, source=NEW, profile=lower.CURRENT_PROFILE, state=None):
        bundle = compile_source(source, profile)
        world, receipt = host(world, {'op': 'reprogram', 'object': 'room', 'principal': 'owner',
            'intent': 'migrate', 'expected': world['objects']['room'], 'protocol': bundle['protocol'],
            'state': copy.deepcopy(world['objects']['room']['state']) if state is None else state})
        self.assertEqual(receipt['kind'], 'committed', receipt)
        return world, bundle

    def test_v1_counterexample_retained_v2_uses_meaning_after_actual_reprogram(self):
        original = self.started()
        encoded = original['objects']['room']['state']['session']['vars']['word']
        self.assertEqual(encoded, {'kind': 'string', 'text': 'z', 'value': 0})
        _, old = self.invoke(original, 'choose:0:0', 'old-less')
        self.assertEqual(old['kind'], 'refused')
        legacy, _ = self.migrate(original, profile=lower.PROFILE)
        _, wrong = self.invoke(legacy, 'choose:0:0', 'legacy-less')
        self.assertEqual(wrong['kind'], 'committed')  # Explicit historical behavior.
        fixed, bundle = self.migrate(original)
        self.assertEqual(bundle['profile'], 'spween-scene-i64-v2')
        final, correct = self.invoke(fixed, 'choose:0:0', 'fixed-less')
        self.assertEqual(correct['kind'], 'refused')
        self.assertEqual(final['objects'], fixed['objects'])

    def test_known_text_ignores_corrupted_cached_rank_for_all_ordering_operators(self):
        operators = {'<': False, '<=': True, '>': False, '>=': True}
        for op, should_commit in operators.items():
            source = OLD.replace('word < "z"', 'word ' + op + ' "z"')
            for rank in (0, 1, 1 << 100, 'not-a-rank', None):
                with self.subTest(op=op, rank=rank):
                    world = self.started(source)
                    state = copy.deepcopy(world['objects']['room']['state'])
                    # The host's general Bend boundary cannot convert null. Use
                    # only supported record values for this semantic test.
                    if rank is None:
                        del state['session']['vars']['word']['value']
                    else:
                        state['session']['vars']['word']['value'] = rank
                    fixed, _ = self.migrate(world, source, state=state)
                    _, reply = self.invoke(fixed, 'choose:0:0', 'compare')
                    self.assertEqual(reply['kind'] == 'committed', should_commit, reply)

    def test_unknown_migrated_text_refuses_ordering_but_equality_stays_exact(self):
        original = self.started()
        state = copy.deepcopy(original['objects']['room']['state'])
        state['session']['vars']['word'] = {'kind': 'string', 'text': 'm', 'value': 0}
        # Keep unknown text unreachable from the destination's availability
        # cache, so its plain equality choice can be exercised independently.
        equality_source = OLD.replace('word < "z"', 'word != "z"')
        fixed, _ = self.migrate(original, equality_source, state=state)
        _, reply = self.invoke(fixed, 'choose:0:0', 'not-equal')
        self.assertEqual(reply['kind'], 'committed', reply)
        fixed, _ = self.migrate(original, state=state)
        after, refused = self.invoke(fixed, 'choose:0:0', 'unknown-order')
        self.assertEqual(refused['kind'], 'refused')
        self.assertIn('stuck', refused['data'])
        self.assertEqual(after['objects'], fixed['objects'])

    def test_known_text_equality_survives_rank_change(self):
        fixed, _ = self.migrate(self.started())
        _, reply = self.invoke(fixed, 'choose:0:1', 'equal')
        self.assertEqual(reply['kind'], 'committed', reply)

    def test_v2_string_comparisons_match_pinned_runtime_in_closed_domain(self):
        literals = ['', 'a', 'z', '\U00010000']
        for value in ['a', 'ä', '\ue000', '\U00010000']:
            for op in ['<', '<=', '>', '>=', '==', '!=']:
                with self.subTest(value=value, op=op):
                    source = ('---\nid: compare\ntitle: Compare\n---\n=== intro\n' +
                        '\n'.join(f'* [Check {i}] {{ word {op} {json.dumps(text, ensure_ascii=False)} }}\n  -> END'
                                  for i, text in enumerate(literals)))
                    initial = {'word': ['string', value]}
                    oracle = lower.bridge({'op': 'replay', 'source': source, 'state': {'vars': initial}})
                    self.assertTrue(oracle['ok'], oracle)
                    parsed = lower.bridge({'op': 'parse', 'source': source})
                    protocol = lower.lower_document(parsed, initial, profile=lower.CURRENT_PROFILE)['protocol']
                    world, created = host({'objects': {}, 'receipts': []}, {
                        'op': 'create', 'object': 'room', 'principal': 'owner', 'intent': 'create',
                        'protocol': protocol, 'law': ['owner']})
                    self.assertEqual(created['kind'], 'committed', created)
                    _, started = self.invoke(world, 'start', 'start')
                    self.assertEqual(started['kind'], 'committed', started)
                    choices = lower.decode_sequence(started['data']['root']['state']['session']['choices'])
                    self.assertEqual(choices, oracle['trace'][0]['snapshot']['choices'])

    def test_v1_protocol_golden_structure_preserved_except_honest_compiler_pin(self):
        expected = {'door.scene': '490fc2f0058e641b6ce1c66c52a0960b55c7ee24ff0929ccd7558d57c6e7ca9b',
                    'repair-cafe.scene': 'fc65de2adbd8d0cb128bce74c94f1b6a25563d39a9b375546275afd8bb5c9750'}
        for filename, digest in expected.items():
            source = (ROOT / 'scene/examples' / filename).read_bytes().decode()
            bundle = compile_source(source, lower.PROFILE)
            bundle['protocol']['provenance']['compilerSha256'] = '<compiler-source-pin>'
            self.assertEqual(hashlib.sha256(room.canonical(bundle['protocol'])).hexdigest(), digest)
        self.assertEqual(compile_source(OLD)['profile'], lower.PROFILE)

    def test_adapters_room_validation_and_cli_preserve_named_versions(self):
        for produce, profile in [(adapter.lower, lower.PROFILE), (adapter.lower_v2, lower.CURRENT_PROFILE)]:
            bundle = produce(OLD)
            self.assertEqual(bundle['profile'], profile)
            adapter.protocol_shape(bundle)
            artifact = room.wrap_bundle(bundle)
            self.assertEqual(room.validate_artifact(artifact), room.digest(artifact))
            changed = copy.deepcopy(bundle)
            changed['protocol']['sceneProfile'] = 'wrong'
            with self.assertRaises(ValueError): adapter.protocol_shape(changed)
        path = ROOT / 'scene/examples/door.scene'
        command = [sys.executable, str(ROOT / 'scene/lower.py'), str(path)]
        current = subprocess.run(command, text=True, capture_output=True, check=True)
        legacy = subprocess.run(command + ['--profile', lower.PROFILE], text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(current.stdout)['profile'], lower.CURRENT_PROFILE)
        self.assertEqual(json.loads(legacy.stdout)['profile'], lower.PROFILE)
        with self.assertRaises(lower.LoweringError): compile_source(OLD, 'unknown-profile')


if __name__ == '__main__': unittest.main()
