"""A slug names a CID for people: fixed per CID, resolved back to the one receipt, pin or state it
names, refused when ambiguous.

Evidence for FOUNDATION §2 Receipt (layer: host).

Slugs: names for people (HOST-HANDOFF §1). A slug is the proquint of the first 32 bits of a CID's
multihash digest, two words; receipts carry it beside `hash`, `inspected` carries `pinSlug`, a public
refusal carries its receipt's, and `world-resolve` finds the one CID a slug names. Refuted by a slug
that is not the fixed string for its CID, a resolve that does not round-trip, or an ambiguity answered.

    python3 -W error -m unittest tests.test_slug -v
"""
import base64
import unittest

from tests.test_reflection import PACKAGE, Reflection, source_seed
from tests.test_turn_world import nat, record
from tests.wire import cid_of

CONSONANTS, VOWELS = "bdfghjklmnprstvz", "aiou"


def slug_of(cid):
    """An independent encoder: base32 CID, skip version, codec, hash code and length, proquint 32 bits."""
    raw = base64.b32decode(cid[1:].upper() + "=" * (-len(cid[1:]) % 8))
    n = int.from_bytes(raw[4:8], "big")
    word = lambda x: (CONSONANTS[x >> 12 & 15] + VOWELS[x >> 10 & 3] + CONSONANTS[x >> 6 & 15] +
                      VOWELS[x >> 4 & 3] + CONSONANTS[x & 15])
    return word(n >> 16) + "-" + word(n & 0xFFFF)


# Two states whose CIDs share their first 32 digest bits (found by search): {count: 15108}, {count: 24636}.
COLLIDING, COLLISION_SLUG = (15108, 24636), "dudim-papat"


class Slugs(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()

    def test_a_known_cid_has_a_fixed_slug(self):
        state = record(count=nat(COLLIDING[0]))
        self.assertEqual(slug_of(cid_of(state)), COLLISION_SLUG)
        made = self.make("a", PACKAGE, record(count=nat(COLLIDING[0])))
        self.assertEqual(made["receipt"]["slug"], slug_of(made["receipt"]["hash"]))
        inspected = self.host.send(op="world-inspect", principal="ember", object="a")
        self.assertEqual(inspected["pinSlug"], slug_of(inspected["pin"]))
        resolved = self.host.send(op="world-resolve", principal="ember", slug=COLLISION_SLUG)
        self.assertEqual((resolved["status"], resolved["kind"], resolved["cid"]), ("resolved", "state", cid_of(state)), resolved)

    def test_resolve_round_trips_receipts_pins_and_states(self):
        made = self.make("a", PACKAGE, source_seed())
        bumped = self.turn("a", "bump")
        r = self.host.send(op="world-resolve", principal="ember", slug=bumped["receipt"]["slug"])
        self.assertEqual((r["status"], r["kind"], r["cid"], r["receipt"]["hash"]),
                         ("resolved", "receipt", bumped["receipt"]["hash"], bumped["receipt"]["hash"]), r)
        pin = made["receipt"]["outcome"]["pin"]
        r = self.host.send(op="world-resolve", principal="ember", slug=slug_of(pin))
        self.assertEqual((r["kind"], r["cid"]), ("pin", pin), r)
        state = bumped["receipt"]["outcome"]["writes"][0]["cid"]
        r = self.host.send(op="world-resolve", principal="ember", slug=slug_of(state))
        self.assertEqual((r["kind"], r["cid"]), ("state", state), r)
        unknown = self.host.send(op="world-resolve", principal="ember", slug="lusab-babad")
        self.assertEqual(unknown["status"], "unknown", unknown)
        self.assertEqual(self.host.send(op="world-resolve", principal="ember", slug="bafy")["status"], "error")

    def test_a_slug_naming_two_states_is_refused_as_ambiguous(self):
        for name, n in zip("ab", COLLIDING):
            self.make(name, PACKAGE, record(count=nat(n)))
        r = self.host.send(op="world-resolve", principal="ember", slug=COLLISION_SLUG)
        self.assertEqual((r["status"], r["matches"]), ("ambiguous", 2), r)
        self.assertEqual(r["message"], "ambiguous: 2 matches; cite the object and version")

    def test_a_public_refusal_carries_its_receipts_slug(self):
        self.make("a", PACKAGE, source_seed())
        stale = self.host.send(op="world-propose", principal="ann", identity="stale",
                               roots=[{"object": "a", "version": 7}], writes=[])
        self.assertEqual(stale["public"]["slug"] if "public" in stale else
                         self.host.send(op="world-receipt", principal="bob", identity="stale", of="ann")["slug"],
                         slug_of(stale["receipt"]["hash"]))


if __name__ == "__main__":
    unittest.main()
