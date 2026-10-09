"""World-qualified identity remains distinct from aliases and permissions."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import references


class References(unittest.TestCase):
    def test_identity_is_exact_and_portable_without_normalizing_names(self):
        ref = references.object_reference('urn:uuid:world', 'room/é')
        self.assertEqual(references.validate_reference(ref), ref)
        self.assertEqual(references.local_object(ref, 'urn:uuid:world'), 'room/é')
        self.assertNotEqual(ref, references.object_reference('urn:uuid:world', 'room/e\u0301'))

    def test_foreign_world_is_not_resolved_by_matching_object_name(self):
        with self.assertRaisesRegex(ValueError, 'another world'):
            references.local_object(references.object_reference('foreign', 'room'), 'local')

    def test_no_authority_or_observation_can_be_smuggled_into_identity(self):
        ref = references.object_reference('world', 'room')
        for key in ('principal', 'law', 'root', 'url', 'label', 'grant'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                references.validate_reference({**ref, key: 'untrusted'})
        with self.assertRaises(ValueError):
            references.validate_reference({**ref, 'format': 'future-v2'})

    def test_invalid_or_unbounded_components_refuse(self):
        for value in ('', None, 1, 'x' * 257, 'x\n', '\ud800', '\x00'):
            for world, obj in ((value, 'room'), ('world', value)):
                with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                    references.object_reference(world, obj)


if __name__ == '__main__':
    unittest.main()
