"""What changed since a height, and the card listing (docs/METAPHYSICS.md §5; HOST-HANDOFF 5.129).

Evidence for `changed` and `delvetalk objects ?` (layer: host).

`world.changed {since, prefix, after}` answers the newest change of each object the asker may read
under the prefix, newest first, 64 a page, from the height index `record` derives (`World.changes`),
with the version reached, the height and who made it (a handle when known). `delvetalk objects ?`
lists the cards the asker may read by prefix, and every card's `?` ends with where. Refuted by a
private object listed to a stranger, an older change listed above a newer one, an object listed
twice, a change at or below `since` listed, a page past 64 or a page that loses an object, a
reopen that answers otherwise, or a listing that names a card the asker may not read.

    python3 -W error -m unittest tests.test_changed -v
"""
import unittest

from tests.test_chain import Chain
from tests.test_reflection import PROBE, Reflection, probe_seed
from tests.wire import label, nat, record
from tests.bend import closure, declared

WATCH = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def since(state: State, input: {since: Nat, prefix: String, after: String}, context: Abi.Context) -> Activity<String>:
  match world.changed({since: input.since, prefix: input.prefix, after: input.after}):
    case changed(c): if c.more then "{rows(c.items)} +" else rows(c.items)
    case denied(_): "denied"
def rows(items: Lists.List<World.Change>) -> String:
  textJoin(Lists.map(items, fn(i: World.Change) -> String: "{i.object.object} v{natText(i.version)} @{natText(i.height)} by {i.by}"), "; ")
""", "since")


class Changed(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("watch", WATCH, record(n=nat(0)))
        for name in ("garden/a", "garden/b"):
            self.make(name, PROBE, probe_seed())
        self.make("vault", PROBE, probe_seed(), read={"principals": ["ember"]})

    def since(self, since=0, prefix="", after="", who="kim"):
        r = self.turn("watch", "since", record(since=nat(since), prefix=label(prefix), after=label(after)), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r["result"]["value"]

    def height(self, r):
        self.assertEqual(r["status"], "admitted", r)
        return r["receipt"]["height"]

    def test_the_newest_change_of_each_readable_object_newest_first(self):
        a = self.height(self.turn("garden/a", "bump", principal="kim"))
        b = self.height(self.turn("garden/b", "bump"))
        v = self.height(self.turn("vault", "bump"))
        a2 = self.height(self.turn("garden/a", "bump", principal="kim"))
        self.assertEqual(self.since(prefix="garden/"), f"garden/a v2 @{a2} by kim; garden/b v1 @{b} by ember")
        self.assertEqual(self.since(since=b, prefix="garden/"), f"garden/a v2 @{a2} by kim")
        self.assertEqual(self.since(since=a2, prefix="garden/"), "")
        # The vault is ember's to read: a stranger never sees it change, its keeper does.
        self.assertNotIn("vault", self.since())
        self.assertIn(f"vault v1 @{v} by ember", self.since(who="ember"))
        # A creation is a change at version 0; every object once.
        whole = self.since(who="ember").split("; ")
        self.assertEqual(len(whole), len({row.split(" ")[0] for row in whole}), whole)
        self.assertEqual(whole[-1].split(" ")[:2], ["watch", "v0"], whole)
        self.assertLess(a, a2)
        # A handle, when the world knows one, stands for the principal.
        self.assertEqual(self.host.send(op="world-principal", principal="ember", did="kim", handle="kim.delve.town")["status"], "principal")
        self.assertEqual(self.since(since=b, prefix="garden/"), f"garden/a v2 @{a2} by kim.delve.town")
        # Derived by `record`: a reopen answers the same.
        before = self.since(who="ember")
        self.reopen()
        self.assertEqual(self.since(who="ember"), before)

    def test_sixty_four_a_page_and_after_continues(self):
        for i in range(65):
            self.make(f"p/{i:02d}", PROBE, probe_seed())
        first = self.since(prefix="p/").split("; ")
        self.assertTrue(first[-1].endswith(" +"), first[-1])
        self.assertEqual(len(first), 64)
        self.assertEqual(first[0].split(" ")[0], "p/64")
        last = first[-1].split(" ")[0]
        rest = self.since(prefix="p/", after=last)
        self.assertEqual(rest.split(" ")[0], "p/00", rest)
        self.assertFalse(rest.endswith(" +"), rest)


class Listing(Chain):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.host.send(op="world-open", path=self.path, clock="transport")["status"], "opened")
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.make("bell", closure("Bell"), record(colour=silver, seed=label("a bell"), planting=label("at://x/p"),
                                                  planter=label("glm"), planterHandle=label("")))
        for name in ("garden/a", "garden/b"):
            self.make(name, closure("Counter"), record())
        r = self.host.send(op="world-create", principal="ember", identity="mk-vault", object="garden/vault",
                           modules=closure("Counter"), entry="initial", seed=record(), read={"principals": ["ember"]})
        self.assertEqual(r["status"], "created", r)

    def ask(self, text, who="kim"):
        self.n = getattr(self, "n", 0) + 1
        return self.host.send(op="world-turn", principal=who, object="bell", method="receive", identity=f"q{self.n}",
                              argument=record(text=label(text), post=label(f"at://x/q{self.n}")))

    def test_objects_lists_the_readable_cards_by_prefix(self):
        r = self.ask("delvetalk objects ?\nprefix: garden/")
        self.assertEqual((r["status"], r["object"]), ("usage", "objects"), r)
        self.assertEqual(r["text"].split("\n\n")[0], "The cards under garden/ you may read:")
        self.assertIn("\ngarden/a\ngarden/b", r["text"])
        self.assertNotIn("vault", r["text"])
        self.assertIn("garden/vault", self.ask("delvetalk objects ?\nprefix: garden/", who="ember")["text"])
        self.assertIn("No card under moth/", self.ask("delvetalk objects ?\nprefix: moth/")["text"])
        # Every card's `?` ends with where the others are listed.
        self.assertIn("delvetalk objects ?", self.ask("delvetalk bell ?")["text"])

    def test_no_object_takes_the_listings_name(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-objects", object="objects",
                           modules=closure("Counter"), entry="initial", seed=record())
        self.assertEqual(r["status"], "error", r)


if __name__ == "__main__":
    unittest.main()
