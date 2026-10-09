#!/usr/bin/env python3
"""Source scene bounded representation and atomic rejection checks."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conformance.test_scene import SceneHarness, scene, parser, room, world
import unittest

class SceneAdversarialTests(SceneHarness):
    def test_signed_overflow_refuses_entire_entry(self):
        self.install(scene('=== a\n~ number = 9223372036854775807\n~ number += 1\nA.\n'))
        before=self.root
        reply,_=self.invoke('start')
        self.assertEqual(reply['kind'],'refused',reply)
        self.assertEqual(self.root,before)
    def test_source_guard_refuses_hidden_choice(self):
        self.install(scene('=== a\n~ ready = false\nA.\n* [Blocked] { ready == true }\n  -> END\n'))
        self.assertEqual(self.invoke('start')[0]['kind'],'committed')
        before=self.root
        reply,_=self.invoke('choose',0)
        self.assertEqual(reply['kind'],'refused',reply)
        self.assertEqual(self.root,before)
    def test_out_of_range_choice_refuses(self):
        self.install(scene('=== a\nA.\n'))
        self.invoke('start'); before=self.root
        reply,_=self.invoke('choose',255)
        self.assertEqual(reply['kind'],'refused',reply)
        self.assertEqual(self.root,before)
    def test_float_retained_by_parser_and_refused_as_source_data(self):
        source=scene('=== a\n~ x = 1.5\nA.\n')
        parsed=parser.bridge({'op':'parse','source':source})
        self.assertTrue(parsed['ok'],parsed)
        with self.assertRaisesRegex(ValueError,'Float'): room.compile_artifact(source)
    def test_duplicate_passages_rejected_by_source_validation(self):
        with self.assertRaisesRegex(ValueError,'unique'):
            room.compile_artifact(scene('=== a\nOne.\n=== a\nTwo.\n'))
    def test_late_choice_failure_rolls_back_state_and_outbox(self):
        initialized = world.exchange(self.db, {"op": "messages-init", "principal": "owner", "intent": "message-init", "lineage": "scene-rollback", "pendingLimit": 8}, profile="compiled")
        self.assertEqual(initialized["kind"], "committed", initialized)
        sends = '  ~ send "listener" "program" "chord"\n'
        self.install(scene('=== a\nA.\n* [Attempt]\n  ~ number = 9223372036854775807\n' + sends + '  ~ number += 1\n  -> END\n'))
        self.assertEqual(self.invoke('start')[0]['kind'], 'committed')
        before = self.root
        reply, _ = self.invoke('choose', 0)
        self.assertEqual(reply['kind'], 'refused', reply)
        self.assertEqual(self.root, before)
        self.assertEqual(world.query(self.db, {'op': 'messages-pending', 'principal': 'reader'}, profile='compiled')['pending'], {})

    def test_failed_destination_entry_does_not_keep_visit_or_emissions(self):
        initialized = world.exchange(self.db, {"op": "messages-init", "principal": "owner", "intent": "message-init", "lineage": "scene-rollback", "pendingLimit": 8}, profile="compiled")
        self.assertEqual(initialized["kind"], "committed", initialized)
        self.install(scene('=== a\nA.\n* [Attempt]\n  ~ send "listener" "program" "chord"\n  -> b\n=== b\n~ number = 9223372036854775807\n~ number += 1\nB.\n'))
        self.assertEqual(self.invoke('start')[0]['kind'], 'committed')
        before = self.root
        for _ in range(2):
            reply, _ = self.invoke('choose', 0)
            self.assertEqual(reply['kind'], 'refused', reply)
            self.assertEqual(self.root, before)
        self.assertEqual(world.query(self.db, {'op': 'messages-pending', 'principal': 'reader'}, profile='compiled')['pending'], {})
if __name__=='__main__': unittest.main()
