"""Source reference checks preserve the native retained-read authenticity boundary."""
import unittest
from conformance import test_preparation_accessors as accessors

class ResolvedReferences(unittest.TestCase):
    checks_modules = accessors.RequiredAccessors.checks_modules
    checks = accessors.RequiredAccessors.checks

    def test_checked_reference_preserves_text_and_observation_distinction(self):
        self.checks([('List', 'world/lib/prelude/List.obend'),
            ('Preparation', 'world/lib/prelude/Preparation.obend'),
            ('ResolvedReference', 'conformance/fixtures/preparation/ResolvedReference.obend')])
