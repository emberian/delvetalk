#!/usr/bin/env python3
"""Independent scene boundary checks against the actual pinned Rust runtime."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('scene_test_helpers', ROOT / 'conformance/test_scene.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
lower, world, scene = helpers.lower, helpers.world, helpers.scene


class SceneAdversarial(unittest.TestCase):
    # Reuse transport and oracle comparison, not the existing test cases.
    setUp = helpers.SceneTests.setUp
    tearDown = helpers.SceneTests.tearDown
    install = helpers.SceneTests.install
    invoke = helpers.SceneTests.invoke
    compare = helpers.SceneTests.compare
    replay = helpers.SceneTests.replay

    def test_implicit_end_refuses_further_choices_and_restart(self):
        source = scene('''=== opening
~ notify "entry"
* [Finish without arrow]
  ~ total = -1
  ~ notify "finished"
''')
        self.replay(source, [0, 0])
        self.assertTrue(self.root['state']['session']['ended'])
        self.assertEqual([c['args'][0][1] for c in self.calls], ['entry', 'finished'])
        before = copy.deepcopy(self.root)
        self.assertEqual(self.invoke('start')[0]['kind'], 'refused')
        self.assertEqual(self.root, before)

    def test_three_passage_call_order_and_type_changes(self):
        source = scene('''=== first
~ notify "first-entry"
~ value = "é"
* [Forward] { value > "é" }
  ~ notify "before-write"
  ~ value = true
  ~ value += 10
  ~ notify "after-write"
  -> second
=== second
~ notify "second-entry"
* [Bool is one] { value == 1 && value != 2 }
  ~ value = 0
  ~ notify "to-third"
  -> third
=== third
~ value -= 1
~ notify "third-entry"
* [Back] { value < 0 }
  ~ notify "back"
  -> first
* [Finish]
  -> END
''')
        # Reentry preserves the changed integer: first's string condition is
        # now false and must refuse without emitting calls or replaying entry.
        self.replay(source, [0, 0, 0, 0])
        self.assertEqual(lower.decode_value(self.root['state']['session']['vars']['value']), ['int', '-1'])
        self.assertEqual([c['args'][0][1] for c in self.calls],
                         ['first-entry', 'before-write', 'after-write', 'second-entry',
                          'to-third', 'third-entry', 'back'])

    def test_string_order_uses_scalars_not_utf16_or_normalization(self):
        strings = ['e\u0301', 'é', '\ue000', '🜉✾', '𐀀']
        for i, value in enumerate(strings):
            self.db = Path(self.tmp.name) / f'unicode-{i}.json'
            choices = '\n'.join(f'* [Compare {j}] {{ value < "{other}" }}\n  -> END'
                                for j, other in enumerate(strings))
            self.replay(scene('=== first\n' + choices), [],
                        {'vars': {'value': ['string', value]}})

    def test_requirements_remain_observations_after_final_effects(self):
        source = '''---
id: requirement-lifecycle
title: Requirements
weight: 1
cooldown: 0
requires: "ready == true"
---
=== a
~ ready = false
* [Finish]
  ~ ready = true
  -> END
'''
        self.replay(source, [0, 0])
        self.assertTrue(self.root['state']['session']['requirements'])
        self.assertTrue(self.root['state']['session']['ended'])

    def test_entry_overflow_rolls_back_choice_and_outbox(self):
        source = scene('''=== a
* [Go]
  ~ first_write = 5
  ~ notify "must-roll-back"
  -> b
=== b
~ lowest -= 1
~ lowest = 0
~ notify "never-visible"
''')
        self.install(source, {'vars': {'lowest': ['int', str(-(1 << 63))]}})
        self.assertEqual(self.invoke('start')[0]['kind'], 'committed')
        before = copy.deepcopy(self.root)
        response, request = self.invoke('choose:0:0')
        self.assertEqual(response['kind'], 'refused')
        self.assertEqual(self.root, before)
        self.assertEqual(self.calls, [])
        self.assertEqual(world.exchange(self.db, request), response)
        inspected = world.exchange(self.db, {'op': 'inspect', 'object': 'scene', 'principal': 'any'})
        self.assertEqual(inspected, before)

    def test_duplicate_passages_refuse_before_execution(self):
        parsed = lower.bridge({'op': 'parse', 'source': scene('=== a\nOne.\n=== a\nTwo.\n')})
        self.assertTrue(parsed['ok'], parsed)
        with self.assertRaisesRegex(lower.LoweringError, 'duplicate passage'):
            lower.lower_document(parsed)

    def test_malformed_initial_state_is_not_silently_defaulted(self):
        parsed = lower.bridge({'op': 'parse', 'source': scene('=== a\nHello.\n')})
        self.assertTrue(parsed['ok'], parsed)
        for invalid in [[], False, 0, '', [1], 'wrong']:
            with self.subTest(field='vars', value=invalid):
                with self.assertRaises(lower.LoweringError):
                    lower.lower_document(parsed, initial_vars=invalid)
            with self.subTest(field='has', value=invalid):
                with self.assertRaises(lower.LoweringError):
                    lower.lower_document(parsed, has=invalid)


if __name__ == '__main__':
    unittest.main()
