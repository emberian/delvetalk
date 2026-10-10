"""The host's read ops for the AT repository façade (docs/REPO.md "Host ops"): one public reader name,
entries by hash and by page, an object as of a version, sources, grants and publications. Each case
names what would refute it.

    python3 -W error -m unittest tests.test_reads -v
"""
import json
import unittest

from tests.test_reflection import PACKAGE, Reflection, source_seed
from tests.test_turn_world import record

PUBLIC = ("anonymous", "")


class Reads(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.made = self.make("c", PACKAGE, source_seed())
        r = self.host.send(op="world-create", principal="ember", identity="mk-vault", object="vault", source=PACKAGE,
                           entry="initial", seed=source_seed(), read={"principals": ["ember"]})
        self.assertEqual(r["status"], "created", r)

    def test_anonymous_and_the_empty_string_are_the_public_reader_everywhere(self):
        for who in PUBLIC:
            self.assertEqual(self.host.send(op="world-objects", principal=who)["ids"], ["c"], who)
            self.assertEqual(self.host.send(op="world-inspect", principal=who, object="c")["status"], "inspected", who)
            self.assertEqual(self.host.send(op="world-view", principal=who, object="c")["status"], "viewed", who)
            self.assertEqual(self.host.send(op="world-view", principal=who, object="vault")["status"], "denied", who)
            self.assertEqual(self.host.send(op="world-history", principal=who, object="c")["status"], "history", who)


if __name__ == "__main__":
    unittest.main()
